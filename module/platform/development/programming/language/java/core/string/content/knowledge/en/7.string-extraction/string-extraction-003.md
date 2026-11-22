# Empty String When Both Bounds Are Equal: `String.substring(beginIndex, endIndex)`

When extracting a segment of a `String` in Java, the two parameters `beginIndex` and `endIndex` define the range of characters to take. If **both bounds are equal and within the valid range**, the selected segment has length 0, so `substring(beginIndex, endIndex)` returns the **empty string `""`**. This is valid behavior according to the API contract—neither an error nor `null`.

Example:

```java
String text = "Java";
String empty = text.substring(2, 2);

System.out.println(empty.length());  // 0
System.out.println(empty.isEmpty()); // true
System.out.println(empty.equals("")); // true
```

`substring(2, 2)` selects no characters, even though position 2 is a boundary in the middle of a non-empty string. Distinguish this from an **invalid** range such as `substring(5, 5)` on `"Java"` of length 4: having two equal numbers does not rescue out-of-bounds indices.

## 1. Rule of the Two Bounds: Inclusive Start, Exclusive End

Method signature:

```java
public String substring(int beginIndex, int endIndex)
```

The method takes the UTF-16 code units at indices in the range **`[beginIndex, endIndex)`**:

- `beginIndex` is the starting index, **included** in the result.
- `endIndex` is the ending index, **excluded** from the result.
- The number of UTF-16 code units in the result is `endIndex - beginIndex`.
- It must simultaneously satisfy `0 <= beginIndex <= endIndex <= text.length()`.

For the string `"Java"`, the characters have indices 0, 1, 2, and 3, while there are **five boundary positions** from 0 to 4:

```text
Boundary pos: 0   1   2   3   4
              | J | a | v | a |
Char index:     0   1   2   3
```

Range examples:

| Call | Selected Range | Result | Length |
| --- | --- | --- | ---: |
| `text.substring(0, 2)` | `[0, 2)` | `"Ja"` | 2 |
| `text.substring(2, 4)` | `[2, 4)` | `"va"` | 2 |
| `text.substring(1, 3)` | `[1, 3)` | `"av"` | 2 |
| `text.substring(0, 0)` | `[0, 0)` | `""` | 0 |
| `text.substring(2, 2)` | `[2, 2)` | `""` | 0 |
| `text.substring(4, 4)` | `[4, 4)` | `""` | 0 |

When `beginIndex == endIndex`, the half-open interval has **zero elements**, so no characters are placed into the resulting string. This rule is consistent with how Java describes ranges using an inclusive start index and an exclusive end index.

## 2. Complete Example: Every Valid Boundary Position Can Produce an Empty String

Create the file `EmptySubstringDemo.java`:

```java
public class EmptySubstringDemo {
    public static void main(String[] args) {
        String text = "Java";

        String atStart = text.substring(0, 0);
        String inMiddle = text.substring(2, 2);
        String atEnd = text.substring(text.length(), text.length());
        String fromEnd = text.substring(text.length());

        System.out.println("start=[" + atStart + "]");
        System.out.println("middle=[" + inMiddle + "]");
        System.out.println("end=[" + atEnd + "]");
        System.out.println("fromEnd=[" + fromEnd + "]");
        System.out.println("length=" + inMiddle.length());
        System.out.println("isEmpty=" + inMiddle.isEmpty());
        System.out.println("equalsEmpty=" + inMiddle.equals(""));
    }
}
```

Compile/run on JDK 17 or later:

```bash
javac -encoding UTF-8 EmptySubstringDemo.java
java EmptySubstringDemo
```

Exact output:

```text
start=[]
middle=[]
end=[]
fromEnd=[]
length=0
isEmpty=true
equalsEmpty=true
```

The square brackets in the output are **explicitly concatenated** by the program to make the boundaries visible; they are not part of the empty string. If you write `System.out.println(inMiddle);`, the program simply prints a blank line.

The cases `atStart`, `inMiddle`, and `atEnd` all return a value equal to `""`. Likewise, the single-parameter overload `substring(beginIndex)` means taking from `beginIndex` to the end of the string; therefore calling `text.substring(text.length())` also returns an empty string.

## 3. Equal Bounds Must Still Be Within Valid Range

The critical condition is:

```text
0 <= beginIndex <= endIndex <= text.length()
```

If `beginIndex == endIndex == k`, the call is valid **only if** `0 <= k <= text.length()`.

| Example with `text = "Java"`, `length() = 4` | Valid? | Why |
| --- | --- | --- |
| `substring(0, 0)` | Yes | Both bounds are 0, within [0, 4] |
| `substring(2, 2)` | Yes | Boundary 2 is within [0, 4] |
| `substring(4, 4)` | Yes | End boundary 4 equals `length()` and is allowed |
| `substring(-1, -1)` | No | Negative bounds |
| `substring(5, 5)` | No | Bound 5 is greater than `length()` |
| `substring(3, 2)` | No | Start bound is greater than end bound |

With invalid arguments, `String.substring` throws `StringIndexOutOfBoundsException` (a subclass of `IndexOutOfBoundsException`). You should not depend on the exact exception message text because the wording can vary across JDK versions or implementations.

The file `EmptyRangeValidation.java` demonstrates success/failure behavior without relying on the exception message:

```java
public class EmptyRangeValidation {
    public static void main(String[] args) {
        String text = "Java";
        int[][] ranges = {
            {0, 0},
            {2, 2},
            {4, 4},
            {-1, -1},
            {5, 5},
            {3, 2}
        };

        for (int[] range : ranges) {
            int begin = range[0];
            int end = range[1];

            try {
                String part = text.substring(begin, end);
                System.out.printf("[%d,%d) -> length=%d%n",
                        begin, end, part.length());
            } catch (IndexOutOfBoundsException ex) {
                System.out.printf("[%d,%d) -> invalid%n", begin, end);
            }
        }
    }
}
```

Save with the exact file name and run:

```bash
javac -encoding UTF-8 EmptyRangeValidation.java
java EmptyRangeValidation
```

Output:

```text
[0,0) -> length=0
[2,2) -> length=0
[4,4) -> length=0
[-1,-1) -> invalid
[5,5) -> invalid
[3,2) -> invalid
```

The case `[4,4)` is valid even though the string only has **character** indices from 0 to 3, because `endIndex` represents the **boundary position right after the last character**. Conversely, `[5,5)` is not an existing boundary in a string of length 4.

## 4. An Empty Source String Also Has One Valid Extraction Range

With `String emptySource = "";`, `emptySource.length() == 0`. The only valid range for the two-parameter overload is `[0, 0)`:

```java
String emptySource = "";

System.out.println(emptySource.substring(0, 0).isEmpty()); // true
System.out.println(emptySource.substring(0).isEmpty());    // true
// emptySource.substring(1, 1); // Exception because it exceeds length() = 0
```

The statements above are illustrative snippets inside a Java method, not a standalone program. An empty source has **no special exception**: the boundary rules and validity conditions remain the same as for non-empty strings.

## 5. Empty String Is Neither `null` Nor a String Containing a Space

Three values must be distinguished:

- `""`: a `String` object with length `0`, `isEmpty() == true`.
- `" "`: a string containing one regular space character, `length() == 1`, `isEmpty() == false`.
- `null`: a reference that **points to no `String` object**; `length()` or `isEmpty()` cannot be called directly on it.

`substring(k, k)` with a valid `k` always returns a `String` value with empty content. The method does not return `null` to represent “no characters selected”.

Example:

```java
String text = "A B";
String part = text.substring(1, 1);

System.out.println(part == null);   // false
System.out.println(part.length());  // 0
System.out.println(part.isEmpty()); // true

String space = text.substring(1, 2);
System.out.println(space.length());  // 1
System.out.println(space.isEmpty()); // false
```

The snippet above consists of illustrative statements placed inside a method. Although `part` and `space` might both look “blank” when printed to the console, they have different values and lengths.

If you need to compare extracted content against an empty string, use `part.isEmpty()` or `part.equals("")`. Do not use `part == ""` to rely on object identity: even if an implementation happens to reuse a reference to the empty string, the contract that matters is **content equality**.

## 6. Application: Extracting Parts Before/After a Delimiter

An empty string is often a **valid** result when the delimiter lies right at the start or end of the data. For example, strings in `key=value` format:

- `"=value"` has an empty key before `=`.
- `"key="` has an empty value after `=`.
- `"="` has both parts empty.
- `"name=Lan"` has both key and value non-empty.

File `DelimiterExtraction.java`:

```java
public class DelimiterExtraction {
    static void showParts(String line) {
        int separator = line.indexOf('=');

        if (separator < 0) {
            System.out.println("No separator: " + line);
            return;
        }

        String key = line.substring(0, separator);
        String value = line.substring(separator + 1, line.length());

        System.out.println("key=[" + key + "], value=[" + value + "]");
    }

    public static void main(String[] args) {
        showParts("name=Lan");
        showParts("=value");
        showParts("key=");
        showParts("=");
        showParts("missing");
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 DelimiterExtraction.java
java DelimiterExtraction
```

Output:

```text
key=[name], value=[Lan]
key=[], value=[value]
key=[key], value=[]
key=[], value=[]
No separator: missing
```

Closer explanation of two important cases:

- When `line = "=value"`, `separator == 0`, so `line.substring(0, separator)` is `substring(0, 0)`: an **empty key**, not an error.
- When `line = "key="`, `separator == line.length() - 1`, so the value starts at `separator + 1 == line.length()`; equal bounds at the end of the string produce an empty value.

Checking `separator < 0` is necessary: `indexOf('=')` returns `-1` if not found; using that value directly as a bound for `substring` can cause an error or misparse the data. For business rules where key/value **must not be empty**, validate further after extraction; do not expect the API to automatically treat an empty string as an exception.

## 7. Applying in Algorithms Using a `[begin, end)` Window

Many text-scanning algorithms maintain a pair of indices `begin` and `end`, where `begin` is the start of the current segment and `end` is the position right after the last scanned character. When the two indices are equal, the window has length 0.

For example, a function extracting the segment between two boundary positions:

```java
static String extractWindow(String text, int begin, int end) {
    return text.substring(begin, end);
}
```

With `extractWindow("ABCDE", 3, 3)`, the result is `""`. There is no need to write a separate condition `if (begin == end) return "";` to avoid an exception: if both bounds are **valid**, `substring` already handles it properly. However, if the algorithm expects **at least one character**, the condition `begin == end` may signal that the window contains no data yet; business rules must be checked separately.

Common situations:

1. **Extracting a prefix** with `substring(0, boundary)`: if `boundary == 0`, the prefix is empty.
2. **Extracting a suffix** with `substring(boundary, length())`: if `boundary == length()`, the suffix is empty.
3. **Extracting between two markers** with `substring(left, right)`: if both markers coincide, there are no characters between them.
4. **Loop or scan step consuming no new characters**: a window `[cursor, cursor)` can be valid, but you must decide whether the algorithm should advance or stop to avoid an infinite loop.

The last point is very important: a `substring` returning an empty string does not advance `cursor` on its own. If a loop design relies on each iteration advancing by at least one character, ensure the index update handles that properly.

## 8. `substring` Indices Are Measured in UTF-16 Code Units

An empty range `[k, k)` extracts no code units at all, **even when `k` lies between the two halves of a surrogate pair**. For instance, with `"A😀B"`, `substring(2, 2)` still returns `""`, whereas `substring(1, 2)` takes only the first half of the emoji and does not represent a complete code point.

Having equal bounds answers the question “is there any data in the range?”; when the range is **non-empty** and contains supplementary Unicode, choose appropriate code point or grapheme boundaries for the business requirement.

## 9. `substring` vs. `subSequence` and Empty Segments

`String` implements `CharSequence`, so `text.subSequence(k, k)` also produces a sequence of length `0` for valid `k`. Example:

```java
String text = "Java";
CharSequence empty = text.subSequence(3, 3);
System.out.println(empty.isEmpty()); // true
```

`substring` is declared to return `String`, whereas `subSequence` is declared to return `CharSequence`. This is a difference in API type; on a `String` source, both express an empty segment following the half-open rule.

## 10. Common Pitfalls

- **Is `substring(k, k)` always valid?** No: `k` must still be in `[0, length()]`. `substring(5, 5)` on `"Java"` of four code units still throws an exception.
- **Does an empty slice mean `null`?** No: `""` has `length() == 0` and supports `isEmpty()`; `null` is not a `String` object.
- **Is a single space empty?** No: `" "` has length one and `isEmpty() == false`. `isBlank()` asks a different question about whitespace content.
- **Should you compare with `== ""`?** No: `==` compares identity; use `isEmpty()` or `equals("")` for content.
- **Loop failing to advance due to empty result?** `substring` does not move the cursor; the algorithm must guarantee progress or a separate stopping condition.

## 11. Self-Check Questions

**Question 1.** Given `String s = "abc";`, what are the results of `s.substring(1, 1)` and `s.substring(3, 3)`?

**Answer:** Both are `""`, because both bounds are equal and both `1` and `3` lie within the valid boundary range `[0, 3]`.

**Question 2.** Does `s.substring(4, 4)` with `s = "abc"` return an empty string?

**Answer:** No. The method throws an exception because `4 > s.length() == 3`. Equal bounds alone are not enough for a range to be valid.

**Question 3.** What does `"abc".substring("abc".length())` return?

**Answer:** `""`. The single-parameter overload takes from the start index to the end of the string; starting right at the end boundary leaves no characters.

**Question 4.** For the string `"x="`, how long is the part after the equals sign when extracted with `substring(separator + 1, length())`?

**Answer:** `0`. The `=` is at the end, so `separator + 1 == length()`; valid equal bounds produce an empty string.

**Question 5.** Does `substring(k, k)` at a position between a high surrogate and a low surrogate cause an unpaired surrogate?

**Answer:** No, because no code units are taken. Only when extracting a non-empty slice that splits a surrogate pair is there a risk of creating a UTF-16 string containing an unpaired surrogate.

**Key takeaway:** With `String.substring(beginIndex, endIndex)`, if `0 <= beginIndex == endIndex <= length()`, the result is always **`""`** with **length 0**. The indices must be valid; an empty string is the normal result of a `[k, k)` range, neither `null` nor an exception.
