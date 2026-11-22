# `String.charAt()` and Valid Index Conditions in Java

## 1. Lesson objectives

`String.charAt(int index)` is the way to read **a single UTF-16 code unit (`char`)** at a position in a `String`. To use it properly, you need to understand 0-based indexing, the condition `0 <= index < length()`, how to handle empty strings and out-of-bounds indices, as well as the limitation of `charAt` for Unicode characters requiring two UTF-16 units.

After this lesson, you will be able to:

- Determine valid start/end indices in a `String` and write loops that do not go out of bounds.
- Explain how `String.length()`, `charAt(0)`, and `charAt(length() - 1)` behave with empty and non-empty strings.
- Validate inputs before accessing or proactively handle exceptions where appropriate.
- Distinguish `charAt` from `codePointAt` when strings contain emoji, supplementary characters, or surrogate pairs.

## 2. Syntax and contract of `charAt`

Method on `java.lang.String`:

~~~java
public char charAt(int index)
~~~

- **Input:** `index` is the **index of a UTF-16 code unit** in the string.
- **Output:** a `char` value at that position. A `char` is 16 bits wide and does not necessarily represent a complete Unicode code point.
- **Valid index:** for a string `s` of length `n = s.length()`, `index` must satisfy **`0 <= index && index < n`**.
- **Out of bounds:** the API specifies throwing `IndexOutOfBoundsException`; in common Java `String` implementations, the actual exception is the subclass `StringIndexOutOfBoundsException`.
- **Null reference:** calling `s.charAt(index)` when `s == null` causes a `NullPointerException` before the string's content can even be inspected.

Example:

~~~java
String s = "Java";  // length() == 4
char a = s.charAt(0); // 'J'
char b = s.charAt(1); // 'a'
char c = s.charAt(2); // 'v'
char d = s.charAt(3); // 'a'
~~~

Diagram:

~~~text
String:    J   a   v   a
Index:     0   1   2   3
length():  4
Valid range: [0, 4) = 0, 1, 2, 3
~~~

The notation `[0, 4)` means **inclusive of `0` and exclusive of `4`**. `length()` is the length, **not the last index**.

| Expression on `"Java"` | Result | Why? |
| --- | --- | --- |
| `s.charAt(0)` | `'J'` | First valid index |
| `s.charAt(3)` | `'a'` | Last valid index |
| `s.charAt(s.length() - 1)` | `'a'` | `4 - 1 = 3` |
| `s.charAt(-1)` | Out-of-bounds exception | Negative index |
| `s.charAt(4)` | Out-of-bounds exception | `4 == length()` |
| `s.charAt(100)` | Out-of-bounds exception | Far past the end of the string |

**Core formula:**

~~~java
boolean valid = index >= 0 && index < s.length();
~~~

This condition applies when `s != null`. Do not check only `index < s.length()`, because negative values still slip through; also do not use `index <= s.length()`, because `length()` is already out of range.

## 3. First element, last element, and empty strings

For a **non-empty** `String`:

~~~java
String name = "Java";
char first = name.charAt(0);
char last = name.charAt(name.length() - 1);
~~~

Both reads above are only safe when `name.length() > 0`. If `name` is `""`:

- `name.length()` equals `0`.
- **No valid index exists** because there is no integer `i` satisfying `0 <= i < 0`.
- `name.charAt(0)` is out of bounds.
- `name.charAt(name.length() - 1)` becomes `name.charAt(-1)` and is also out of bounds.

Example of checking before getting the last character:

~~~java
String text = "";

if (!text.isEmpty()) {
    char last = text.charAt(text.length() - 1);
    System.out.println(last);
} else {
    System.out.println("Empty string: no last character");
}
~~~

`String.isEmpty()` is equivalent to checking `length() == 0`. If the variable may be `null`, `text.isEmpty()` itself also throws `NullPointerException`; you can use `text != null && !text.isEmpty()` or require non-null inputs from the start as part of the method's contract.

### Is a string containing spaces empty?

~~~java
String spaces = "   ";
System.out.println(spaces.length()); // 3
System.out.println(spaces.isEmpty()); // false
~~~

`"   "` is not empty: it has three space code units, so `charAt(0)` is valid. If a problem asks whether a string *contains only whitespace*, that is a different question; you can consider `isBlank()`, but do not use `isBlank()` in place of a valid-index check. An empty string and a whitespace-only string are two different cases.

## 4. Loops that access each `char` within bounds

Basic loop pattern:

~~~java
String text = "Java";

for (int i = 0; i < text.length(); i++) {
    char current = text.charAt(i);
    System.out.println(i + ": " + current);
}
~~~

`stdout`:

~~~text
0: J
1: a
2: v
3: a
~~~

The condition `i < text.length()` stops the loop before `i == 4`. For an empty string, the loop does not execute at all, so `charAt` is never called with an invalid index.

Common mistake pattern:

~~~java
// WRONG: if text = "Java", the final iteration will call charAt(4).
for (int i = 0; i <= text.length(); i++) {
    char current = text.charAt(i);
}
~~~

Change `<=` to `<`. Similarly, if iterating backward, start from `length() - 1` and stop at `i >= 0`:

~~~java
for (int i = text.length() - 1; i >= 0; i--) {
    System.out.println(text.charAt(i));
}
~~~

This backward `char`-iteration pattern is also safe for empty strings because `i` starts at `-1`, so the condition `i >= 0` is immediately false. However, both loops iterate over **UTF-16 code units**; with supplementary Unicode code points, they step through the two surrogate halves separately.

## 5. Complete Java 17+ example: valid, out-of-bounds, and Unicode

Save the file **`CharAtBoundsDemo.java`**:

~~~java
public class CharAtBoundsDemo {
    public static void main(String[] args) {
        String word = "Java";
        System.out.println("length=" + word.length());
        System.out.println("first=" + word.charAt(0));
        System.out.println("last=" + word.charAt(word.length() - 1));

        for (int i = 0; i < word.length(); i++) {
            System.out.println("charAt[" + i + "]=" + word.charAt(i));
        }

        printIfValid(word, 2);
        printIfValid(word, 4);
        printIfValid("", 0);

        showInvalid(word, -1);
        showInvalid(word, word.length());
        showInvalid("", 0);

        String mixed = "A" + Character.toString(0x1F600) + "B";
        System.out.println("mixed.length=" + mixed.length());
        for (int i = 0; i < mixed.length(); i++) {
            System.out.printf("mixed[%d]=U+%04X%n", i, (int) mixed.charAt(i));
        }
        System.out.printf("codePointAt(1)=U+%X%n", mixed.codePointAt(1));
        System.out.println("codePointCount="
                + mixed.codePointCount(0, mixed.length()));
    }

    private static void printIfValid(String text, int index) {
        if (index >= 0 && index < text.length()) {
            System.out.println("safe[" + index + "]=" + text.charAt(index));
        } else {
            System.out.println("out of range: index=" + index
                    + ", length=" + text.length());
        }
    }

    private static void showInvalid(String text, int index) {
        try {
            text.charAt(index);
        } catch (StringIndexOutOfBoundsException e) {
            System.out.println("caught: " + e.getClass().getSimpleName()
                    + " (index=" + index + ", length=" + text.length() + ")");
        }
    }
}
~~~

Run on Java 17+:

~~~bash
javac -encoding UTF-8 CharAtBoundsDemo.java
java CharAtBoundsDemo
~~~

Verified `stdout` obtained by compiling and running the program:

~~~text
length=4
first=J
last=a
charAt[0]=J
charAt[1]=a
charAt[2]=v
charAt[3]=a
safe[2]=v
out of range: index=4, length=4
out of range: index=0, length=0
caught: StringIndexOutOfBoundsException (index=-1, length=4)
caught: StringIndexOutOfBoundsException (index=4, length=4)
caught: StringIndexOutOfBoundsException (index=0, length=0)
mixed.length=4
mixed[0]=U+0041
mixed[1]=U+D83D
mixed[2]=U+DE00
mixed[3]=U+0042
codePointAt(1)=U+1F600
codePointCount=3
~~~

**Output analysis:**

1. `"Java"` has `length() == 4` and indices `0..3`, so reading the first/last characters succeeds.
2. `printIfValid` checks both bounds before accessing; index `4` and index `0` of the empty string only print a message without throwing an exception.
3. `showInvalid` intentionally calls three invalid indices to demonstrate the exception class thrown by `String.charAt`. This exception-catching example is **only for demonstration and boundary testing**, and does not mean you should overuse exceptions inside ordinary loops.
4. `mixed` contains `"A"`, an emoji `U+1F600`, and `"B"`. The emoji requires **two UTF-16 `char`s**: `U+D83D` and `U+DE00`. Thus `mixed.length()` equals `4`, even though there are **three code points**.
5. `charAt(1)` and `charAt(2)` return the two code units of the emoji; `codePointAt(1)` returns the full code point `0x1F600`.

## 6. Exceptions: when to check, when to catch?

There are two ways to control indices, depending on the API contract and input data.

### Approach A — check before reading

Suitable when the index comes from a user, configuration, or external data:

~~~java
static boolean isValidCharIndex(String text, int index) {
    return text != null && index >= 0 && index < text.length();
}
~~~

Usage:

~~~java
String text = "Java";
int index = 2;

if (isValidCharIndex(text, index)) {
    System.out.println(text.charAt(index));
} else {
    System.out.println("Cannot access requested index");
}
~~~

Here the valid case prints `v`. Putting `text != null` first with the **short-circuit** `&&` operator prevents calling `length()` on `null`. The validation function must reflect the business policy: when `null` is a programming bug, you may choose to reject it immediately with `Objects.requireNonNull` instead of silently treating it as an invalid index.

### Approach B — rely on the contract and let it throw

If a method requires the caller to always supply a valid index, you can call it directly:

~~~java
static char requiredCharAt(String text, int index) {
    return text.charAt(index);
}
~~~

If an invalid index is passed, the exception exposes the bug where it originates. When handling errors from **untrusted input**, checking beforehand usually helps return a meaningful message. Avoid using `try/catch` for each iteration of a loop whose bounds you already know via `length()`.

**Distinguishing two kinds of errors:**

| Case | Cause | Typical exception |
| --- | --- | --- |
| `"Java".charAt(-1)` | Negative index | `StringIndexOutOfBoundsException` |
| `"Java".charAt(4)` | Index equals `length()` | `StringIndexOutOfBoundsException` |
| `"".charAt(0)` | Empty string, no valid index | `StringIndexOutOfBoundsException` |
| `((String) null).charAt(0)` | Method call through a `null` reference | `NullPointerException` |

`String` itself does not convert out-of-bounds indices into a default character, does not return `null`, and does not “wrap around” negative indices. If a default-value mechanism is desired, the application must define it explicitly.

## 7. Unicode: a valid index can still fall in the middle of an emoji

`charAt(index)` reads exactly **one UTF-16 code unit**, even when the index is valid. Many code points outside the BMP (such as 😀) are encoded as a **high surrogate** followed by a **low surrogate**, so reading individual `char`s can retrieve only one half of the pair.

```java
String text = "A" + Character.toString(0x1F600) + "B";
System.out.printf("%04X%n", (int) text.charAt(1)); // D83D
System.out.printf("%04X%n", (int) text.charAt(2)); // DE00
System.out.printf("%X%n", text.codePointAt(1));    // 1F600
```

Both indices 1 and 2 are valid for `charAt` but do not correspond to two Unicode code points. `codePointAt(1)` recognizes the surrogate pair because it starts at the high surrogate; `codePointAt(2)` starts at the low surrogate so it returns `0xDE00` and does not look backward to assemble the full emoji.

When you need to iterate over Unicode code points, start at a proper boundary and advance by `Character.charCount(codePoint)` or use `codePoints()`. The next lesson, **codePointAt and codePointBefore**, goes deeper into reading code points in both directions. With combining accents and multi-component joined emoji, even a single code point may not be a complete visible character.
## 8. `charAt`, `substring`, and splitting across a surrogate pair

`substring(beginIndex, endIndex)` uses two **UTF-16 indices**, with `beginIndex` inclusive and `endIndex` exclusive. The corresponding validity condition is `0 <= beginIndex <= endIndex <= length()`. Unlike `charAt`, `substring(length(), length())` is a **valid empty string** because no elements are taken.

However, an index that is **arithmetically valid** is not necessarily a code point boundary. With `"A😀B"`, the following statement does not cause an index error, but it cuts between the high and low surrogates:

~~~java
String text = "A" + Character.toString(0x1F600) + "B";
String broken = text.substring(0, 2); // 'A' + unpaired high surrogate
~~~

Do not treat `broken` as the complete “first two Unicode characters”. If you want the first two **code points**:

~~~java
int end = text.offsetByCodePoints(0, 2); // 3, UTF-16 index
String firstTwoCodePoints = text.substring(0, end); // "A😀"
~~~

The `charAt` contract only guarantees reading a single `char`; display or Unicode interchange contracts may additionally require checking surrogate pairs and code point boundaries.

## 9. Common mistakes and how to fix them

1. **Using `<= length()` in a loop.** For `charAt`, the upper bound is **strictly less than** `length()`. Write `for (int i = 0; i < s.length(); i++)`.
2. **Calling `charAt(length())` to get the last character.** The last index is `length() - 1`, and before that you must ensure the string is non-empty.
3. **Checking only `index < length()`.** Negative indices still satisfy that condition; add `index >= 0`.
4. **Confusing `null` with `""`.** An empty string is a valid `String` object with `length() == 0`; `null` means there is no object to call methods on.
5. **Assuming `charAt(i)` always reads a whole Unicode character.** For supplementary code points, each call reads only one surrogate half; choose `codePointAt` and advance by `Character.charCount` when you need to read code points.
6. **Using a code point count as if it were a UTF-16 index.** `codePointCount` returns a count and does not automatically convert to a `charAt` position. Use `offsetByCodePoints` to convert.
7. **Catching `StringIndexOutOfBoundsException` at every step when processing data whose bounds could have been checked.** When iterating by `length()`, write the bounds correctly. Only catch the exception if you genuinely have a recovery strategy or need to inform the caller.
8. **Assuming an index stays guaranteed valid before the string changes.** `String` is immutable; however, a variable can be reassigned to a different `String` object. If you validate against `a` and later call `charAt` on a new, different value, the old check no longer holds. Use the same stable string reference in both the check and the access.

## 10. Self-check exercises

**Question 1.** Given `String s = "Core";`, which indices are valid and what does `s.charAt(s.length())` return?

**Answer:** `0, 1, 2, 3` are valid. `length()` equals `4`; `charAt(4)` throws an out-of-bounds exception.

**Question 2.** Why are both `"".charAt(0)` and `"".charAt("".length() - 1)` wrong?

**Answer:** `length() == 0`, so there is no valid index. The two access expressions use `0` and `-1`, respectively.

**Question 3.** Is the check `i < s.length()` sufficient?

**Answer:** No, because `i` could be negative. You need `i >= 0 && i < s.length()`, as well as `s != null` if the data can be null.

**Question 4.** How do `"A😀B".length()`, `charAt(1)`, and `codePointAt(1)` differ?

**Answer:** the length is **4 UTF-16 code units**; `charAt(1)` is the **high surrogate U+D83D**; `codePointAt(1)` is the **code point U+1F600** because it combines the valid high/low surrogate pair.

**Question 5.** Given `String s = "ab";`, where is the bug in `for (int i = 0; i <= s.length(); i++)`?

**Answer:** the iteration `i == 2` calls `charAt(2)`, exceeding the upper bound. Change `<=` to `<`.

**Question 6.** Is `substring(s.length(), s.length())` valid in the same way as `charAt(s.length())`?

**Answer:** No. `substring` with both bounds equal to `length()` validly returns an empty string; `charAt(length())` is always out of bounds because it must read an actual element.

## 11. References

- [Oracle Java SE 17 — `String.charAt(int)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#charAt(int)): return type, index conditions, exceptions.
- [Oracle Java SE 17 — `String.length()`, `isEmpty()`, `codePointAt()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): UTF-16 length and working with code points.
- [Oracle Java SE 17 — `Character`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): `char`, surrogate pairs, `charCount`, and character checks.
- [Java Language Specification §3.10.5 — String Literals](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.5): string literals in Java source code.

**Remember:** `charAt(index)` is valid only when **`0 <= index < s.length()`** and `s` is non-null. `String.length()` and `charAt` operate in **UTF-16 code units**. If the problem truly requires **Unicode code points**, use the `codePoint...` APIs with appropriate index boundaries.