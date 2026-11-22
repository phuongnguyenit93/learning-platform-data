# `String.substring()`: Inclusive Start, Exclusive End in Java

The `substring()` method is used to **extract a portion of text** from a `String`. The core rule of the two-parameter overload is: **take characters from position `beginIndex` (inclusive) to right before position `endIndex` (exclusive)**.

```java
String text = "ABCDE";
String part = text.substring(1, 4); // "BCD"
```

`String` indices start at **0**. In `"ABCDE"`, indices 1, 2, and 3 correspond to `B`, `C`, and `D` respectively; position 4 (`E`) is the end boundary and is **not included in the result**. The range can be described using half-open interval notation **`[beginIndex, endIndex)`**.

This is the foundational rule for slicing strings accurately, avoiding off-by-one errors and preventing exceptions when processing data.

## 1. The Two Overloads of `substring()`

| API | Extracted Range | Example with `"ABCDE"` |
| --- | --- | --- |
| `substring(int beginIndex)` | From `beginIndex` (inclusive) **to the end of the string** | `substring(2)` → `"CDE"` |
| `substring(int beginIndex, int endIndex)` | From `beginIndex` (inclusive) to **before** `endIndex` | `substring(1, 4)` → `"BCD"` |

`substring(beginIndex)` is equivalent **in content** to `substring(beginIndex, text.length())`. Both return a `String`; the original `String` is not modified because `String` in Java is **immutable**.

### Visualizing Indices

```text
Chars:       A    B    C    D    E
Positions:   0    1    2    3    4    5
             |----|----|----|----|----|
substring(1, 4)
                  B    C    D
             [    1 ------------ 4    )
```

For `"ABCDE"`, `length() == 5`. Index **5** is the position right **after** the last character, completely valid as an **end boundary**; it is not the index of a character you can pass to `charAt(5)`.

## 2. Exact Rules for the Range `[beginIndex, endIndex)`

For a string `s` with `n = s.length()`, the two indices of the two-parameter overload must satisfy:

```text
0 <= beginIndex <= endIndex <= n
```

- **Inclusive start:** the character at `beginIndex` is included, provided the range is non-empty.
- **Exclusive end:** the character at `endIndex` is not included.
- **Result length:** always equals `endIndex - beginIndex`, counted in **UTF-16 code units**.
- **Equal bounds:** `substring(k, k)` returns the empty string `""` for every `k` in the range `0..n`.
- **Take the whole string:** `substring(0, n)` has the same content as `s`.
- **Take to the end:** `substring(k, n)` or `substring(k)`.
- **Take one code unit at `i`:** `substring(i, i + 1)` if `0 <= i < n`.

For the single-parameter overload, the condition is **`0 <= beginIndex <= n`**. Thus `s.substring(s.length())` is valid and returns an empty string; `s.substring(s.length() + 1)` is invalid.

### Why Is an Exclusive End Convenient?

The half-open rule makes working with indices possible without adding or subtracting 1 in many situations:

- **Counting units in a range:** `end - begin`.
- **Empty range:** `begin == end`.
- **Adjacent splitting:** `s.substring(0, k)` and `s.substring(k, s.length())` cover the entire string without overlap and without losing any code unit.
- **Slicing to the end:** no need to guess the index of the last character; use `s.length()` as the end boundary.
- **Looping over a range:** matches the common convention `for (int i = begin; i < end; i++)`.

For example, `"ABCDE".substring(0, 2)` takes `"AB"` and `"ABCDE".substring(2, 5)` takes `"CDE"`. The split point **2** is the start of the second segment and the exclusive end of the first.

## 3. Standalone Runnable Java 17+ Example

Save the following content to `SubstringBasics.java`:

```java
public class SubstringBasics {
    public static void main(String[] args) {
        String text = "ABCDE";

        System.out.println(text.substring(1, 4));
        System.out.println(text.substring(0, 1));
        System.out.println(text.substring(4, 5));

        System.out.println(text.substring(2, 2).isEmpty());
        System.out.println(text.substring(text.length()).isEmpty());

        System.out.println(text.substring(2));
        System.out.println(text.equals("ABCDE"));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 SubstringBasics.java
java SubstringBasics
```

Exact output:

```text
BCD
A
E
true
true
CDE
true
```

Explanation:

1. `substring(1, 4)` takes `B`, `C`, `D`, **not** `E`.
2. `substring(0, 1)` takes the single element at index 0.
3. `substring(4, 5)` takes the single element at index 4, which is also the last code unit.
4. `substring(2, 2)` takes a length-0 slice, so `isEmpty()` is `true`.
5. `substring(text.length())` starts right after the last element, also returning an empty string.
6. `substring(2)` takes the entire remaining portion (`CDE`).
7. The original `text` remains `"ABCDE"`; `substring()` does not delete, move, or alter characters in `text`.

## 4. Index Errors and Exceptions

When bounds violate the valid conditions, `substring()` throws `IndexOutOfBoundsException`; in OpenJDK, you typically see the specific subclass `StringIndexOutOfBoundsException`. The exception message can differ across JDKs, so applications should not rely on the exact message text.

Examples of **invalid** calls on `"ABCDE"`:

| Call | Cause |
| --- | --- |
| `substring(-1, 2)` | Negative `beginIndex` |
| `substring(2, 6)` | `endIndex` greater than `length() == 5` |
| `substring(4, 3)` | `beginIndex > endIndex` |
| `substring(6)` | Start boundary greater than length |
| `substring(0, -1)` | Negative end boundary |

An empty slice **is not an error** when both bounds are equal and within the valid range: `substring(5, 5)` is valid for a string of length 5. Likewise, `substring(0, 0)` returns an empty string.

### Checking Before Slicing

When indices are supplied by users or external APIs, validate them first:

```java
public static String slice(String text, int begin, int end) {
    if (text == null) {
        throw new IllegalArgumentException("text must not be null");
    }
    if (begin < 0 || end < begin || end > text.length()) {
        throw new IllegalArgumentException("invalid substring bounds");
    }
    return text.substring(begin, end);
}
```

This is an **illustrative method** meant to be placed inside a class; it is not a standalone `main` program. If `text` is `null`, calling `text.substring(...)` directly causes `NullPointerException`; therefore, `null` checking is separate from range checking.

Two common handling policies are:

- **Reject invalid bounds:** throw a meaningful exception when the API requires an exact slice.
- **Clamp within valid bounds:** do this only when business logic accepts truncation, such as taking a preview of at most three code units with `text.substring(0, Math.min(3, text.length()))` on a non-`null` string.

Do not silently use `Math.min` to patch every invalid `endIndex`, because programming bugs can be hidden and the returned data may differ from what was expected.

## 5. Application: Extracting Fixed-Width Fields

Half-open intervals are especially useful when data specifies a **starting position and the number of code units** to extract. If a field starts at `start` and has `count` code units, the end boundary is `start + count`. Before adding, check `count <= text.length() - start` to avoid out-of-bounds errors or integer overflow.

For example, the string `"20261023ACTIVE"` contains an eight-digit date followed by a six-letter status. Save as `FixedFieldSliceDemo.java`:

```java
public class FixedFieldSliceDemo {
    static String field(String text, int start, int count) {
        if (start < 0 || start > text.length()
                || count < 0 || count > text.length() - start) {
            throw new IndexOutOfBoundsException("Invalid fixed-width field");
        }
        return text.substring(start, start + count);
    }

    public static void main(String[] args) {
        String record = "20261023ACTIVE";
        System.out.println("date=" + field(record, 0, 8));
        System.out.println("status=" + field(record, 8, 6));
        System.out.println("empty=" + field(record, record.length(), 0).isEmpty());
    }
}
```

```bash
javac -encoding UTF-8 FixedFieldSliceDemo.java
java FixedFieldSliceDemo
```

```text
date=20261023
status=ACTIVE
empty=true
```

This example directly illustrates the formula `end = start + count` and the reason for the exclusive end boundary. When fields are defined in terms of **Unicode characters** or graphemes instead of code units, boundaries must be converted before calling `substring`.

## 6. Important Note: `substring()` Indices Are UTF-16

`length()` and both bounds of `substring` are measured in **UTF-16 code units**. Non-BMP emojis typically occupy two code units; hence `"A😀B".length() == 4` even though the string has three code points. `substring(1, 3)` extracts the whole emoji, whereas `substring(1, 2)` keeps only the high surrogate.

If the requirement is to slice by code points, find boundaries using `offsetByCodePoints` before passing the results to `substring`. If combining marks or multi-code-point emojis must be preserved intact, grapheme boundaries are needed; arithmetic checks `0 <= begin <= end <= length` only protect offsets and do not guarantee that display clusters are not split.

## 7. Common Mistakes

1. **Assuming the end boundary is included:** `"ABCDE".substring(1, 4)` is `"BCD"`, not `"BCDE"`.
2. **Incorrectly taking one character:** extract the code unit at index `i` using `substring(i, i + 1)`, not `substring(i, i)` (empty string). With Unicode, consider code points/graphemes.
3. **Subtracting 1 when taking the whole string:** `substring(0, length() - 1)` **drops the last character**. To take the whole string, use `substring(0, length())`.
4. **Thinking `endIndex == length()` is wrong:** this is valid and very common.
5. **Confusing character count with end index:** to take `count` code units from `start`, the end boundary is `start + count` (when within bounds). For example, taking three code units starting at index 2 uses `substring(2, 5)`, not `substring(2, 3)`.
6. **Forgetting to check `indexOf() == -1`:** if the separator does not exist, using `-1` as a slice index easily leads to errors.
7. **Confusing `substring()` with `split()`:** `split()` uses a regex and returns a string array; `substring()` uses index boundaries and returns a single string. Splitting on a simple delimiter can often combine `indexOf` and `substring`.
8. **Thinking `substring()` modifies the original string:** `String` is immutable; the returned result is assigned to a new variable or reassigned to an existing one without changing the original `String` object's content.
9. **Using `substring()` with user-entered indices without bounds checking:** negative, reversed, or greater-than-`length()` values can all cause exceptions.
10. **Slicing Unicode strings at code unit boundaries:** can break surrogate pairs or user-perceived character clusters. Choose the counting unit based on requirements.

## 8. Quick Check Exercises

Suppose `s = "ABCDEFG"` (`length() == 7`). Predict each result before reading the answer.

| Expression | Result | Reason |
| --- | --- | --- |
| `s.substring(0, 3)` | `"ABC"` | Includes 0, 1, 2; excludes 3 |
| `s.substring(3, 7)` | `"DEFG"` | Takes from D to the end; boundary 7 is valid |
| `s.substring(3)` | `"DEFG"` | Single-parameter overload takes the tail |
| `s.substring(0, 0)` | `""` | Equal bounds give an empty slice |
| `s.substring(7, 7)` | `""` | Empty slice at the end of the string |
| `s.substring(3, 2)` | Exception | Start boundary is greater than end boundary |
| `s.substring(0, 8)` | Exception | End boundary exceeds length 7 |

Notably, `s.substring(0, 3).length()` equals **3**, which is `3 - 0`. If you extract two slices `left = s.substring(0, 3)` and `right = s.substring(3, s.length())`, then `left + right` has the same content as `s`.

## 9. Checklist When Using `substring()`

1. Determine whether the slice uses **UTF-16 indices** or Unicode code points/graphemes.
2. Choose the two bounds `begin` and `end`; remember **start inclusive, end exclusive**.
3. Verify `0 <= begin <= end <= text.length()`.
4. Use `substring(begin, end)` for a two-ended range or `substring(begin)` for the remainder.
5. If bounds are computed from a delimiter, check the `indexOf`/`lastIndexOf` result before using it.
6. Test edge cases: empty string, `begin == end`, `end == length()`, delimiter not found, and multi-code-unit Unicode.

**Key takeaway:** `substring(beginIndex, endIndex)` extracts the range **`[beginIndex, endIndex)`**. The start boundary is **inclusive** and the end boundary is **exclusive**, so the slice length is always **`endIndex - beginIndex`** in `String` UTF-16 units.
