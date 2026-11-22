# Formatting Numbers with Field Positions Using FieldPosition and AttributedCharacterIterator in Java

## 1. When a Formatted String Is Not Enough

`NumberFormat.format(...)` is commonly used to turn a number into a `Locale`-appropriate string, such as `1234567.89` into `1,234,567.89` with `Locale.US`. Sometimes, however, an application needs to know the **positions of individual parts within the resulting string** to style colors, place a cursor, expose segments to assistive technologies, or split integer and fractional parts without guessing by comma or period characters.

Java provides two ways to obtain positional metadata:

- **`java.text.FieldPosition`:** requests a `[beginIndex, endIndex)` range for one specific field while formatting into a `StringBuffer`. Useful when you only need a single field, such as the integer or fractional part.
- **`java.text.AttributedCharacterIterator`:** iterates over the entire string along with **attributes** attached to each character span; useful when you need multiple fields, fields appearing multiple times, or overlapping attributes.

For number formatting, attributes are declared in `NumberFormat.Field`, such as `INTEGER`, `FRACTION`, `GROUPING_SEPARATOR`, `DECIMAL_SEPARATOR`, `SIGN`, `CURRENCY`, `PERCENT`, and `EXPONENT`.

Note: `FieldPosition` and `AttributedCharacterIterator` **do not define formatting rules themselves**. `NumberFormat` or `DecimalFormat` chooses separators, digit grouping, currency symbols, and digits according to `Locale`; those two APIs let you identify **which field lies where** in the formatted result.

## 2. Components That Can Appear in a Formatted Number

With `Locale.US` and a format showing two digits after the decimal point, consider:

```text
1,234,567.89
```

It can be broken down into fields:

| Text segment | `NumberFormat.Field` field | Range in string |
|---|---|---|
| `1,234,567` | `INTEGER` | `[0,9)` |
| First `,` | `GROUPING_SEPARATOR` | `[1,2)` |
| Second `,` | `GROUPING_SEPARATOR` | `[5,6)` |
| `.` mark | `DECIMAL_SEPARATOR` | `[9,10)` |
| `89` | `FRACTION` | `[10,12)` |

**Fields can overlap.** Grouping commas lie within the `INTEGER` span, while each comma also carries its own `GROUPING_SEPARATOR` attribute. Therefore, do not imagine every attribute partitions the string into disjoint segments.

From this arise two distinct needs:

1. If you only need the **entire integer part** `1,234,567`, a single `FieldPosition(NumberFormat.Field.INTEGER)` suffices.
2. If you need to highlight **each individual comma** as well as the fractional part, `AttributedCharacterIterator` is more suitable because the same attribute can have multiple runs.

Ranges here are measured in **Java UTF-16 character indices** (`String`/`StringBuffer`), starting at `0` and ending **exclusively** at `endIndex`. They are not UTF-8 byte offsets and are not guaranteed to match user-perceived grapheme indices.

## 3. FieldPosition: One Field and a Start/End Index Pair

A `FieldPosition` is created for the field of interest:

```java
FieldPosition position =
        new FieldPosition(NumberFormat.Field.INTEGER);
```

Then pass it into the three-argument formatting overload:

```java
StringBuffer buffer = new StringBuffer();
formatter.format(1234567.89, buffer, position);
```

When formatting completes, read:

- `position.getBeginIndex()` — start index, **inclusive** of this character.
- `position.getEndIndex()` — end index, **exclusive** of the character at this index.

Use `buffer.substring(begin, end)` to extract the located portion. Because the end is exclusive, the span's length is `end - begin`.

### Standalone Java 17+ Example

Create `NumberFieldPositionDemo.java`:

```java
import java.text.FieldPosition;
import java.text.NumberFormat;
import java.util.Locale;

public class NumberFieldPositionDemo {
    public static void main(String[] args) {
        NumberFormat formatter =
                NumberFormat.getNumberInstance(Locale.US);
        formatter.setMinimumFractionDigits(2);
        formatter.setMaximumFractionDigits(2);

        FieldPosition integerPosition =
                new FieldPosition(NumberFormat.Field.INTEGER);
        StringBuffer integerBuffer = new StringBuffer();

        formatter.format(1234567.89, integerBuffer, integerPosition);
        System.out.println("text=" + integerBuffer);
        System.out.printf(
                "integer=[%d,%d) value=%s%n",
                integerPosition.getBeginIndex(),
                integerPosition.getEndIndex(),
                integerBuffer.substring(
                        integerPosition.getBeginIndex(),
                        integerPosition.getEndIndex()));

        FieldPosition fractionPosition =
                new FieldPosition(NumberFormat.Field.FRACTION);
        StringBuffer fractionBuffer = new StringBuffer();

        formatter.format(1234567.89, fractionBuffer, fractionPosition);
        System.out.printf(
                "fraction=[%d,%d) value=%s%n",
                fractionPosition.getBeginIndex(),
                fractionPosition.getEndIndex(),
                fractionBuffer.substring(
                        fractionPosition.getBeginIndex(),
                        fractionPosition.getEndIndex()));
    }
}
```

Compile and run:

```bash
javac NumberFieldPositionDemo.java
java NumberFieldPositionDemo
```

Verified output on the JDK:

```text
text=1,234,567.89
integer=[0,9) value=1,234,567
fraction=[10,12) value=89
```

`FieldPosition` does not create a new result string; the formatted text is appended to the passed `StringBuffer`. Thus, to locate an additional field, create another `FieldPosition` and call `format` again. A single call only updates the bounds of the **requested field**.

## 4. Index Meaning When StringBuffer Already Has a Prefix

A common mistake is assuming `beginIndex` always starts counting from the newly appended number. In reality, it is the **index within the complete resulting `StringBuffer`**, including content already present before formatting.

Example:

```java
StringBuffer buffer = new StringBuffer("PRE:");
FieldPosition position =
        new FieldPosition(NumberFormat.Field.INTEGER);
formatter.format(1234567.89, buffer, position);
```

This snippet assumes `formatter` is created and configured as in the previous example. After running:

```text
buffer  = PRE:1,234,567.89
integer = [4,13)
```

The four characters `PRE:` occupy indices `0` through `3`. The integer part begins at `4`. If an application builds up a message incrementally and wants to style the integer portion of a number, it should use the indices returned by `FieldPosition` directly, **rather than subtracting or guessing the prefix length**.

Note that there are two ways to distinguish `FieldPosition` via constructor overloads:

- `new FieldPosition(NumberFormat.Field.INTEGER)`: uses the attribute object defined in `NumberFormat.Field`.
- `new FieldPosition(NumberFormat.INTEGER_FIELD)` or `new FieldPosition(NumberFormat.FRACTION_FIELD)`: legacy usage based on `int` constants.

For new code, prefer `NumberFormat.Field` because it has clearer semantics and covers more fields. Do not equate `NumberFormat.INTEGER_FIELD` (an `int` field ID) with `NumberFormat.Field.INTEGER` (an attribute object).

## 5. Limitations of FieldPosition

### One FieldPosition Tracks One Field Type

`FieldPosition` does not return all fields in a single formatting call. If you need the integer part, fractional part, negative sign, and every grouping separator, you must perform the necessary format calls or switch to `AttributedCharacterIterator`.

### Repeated Fields: Only One Occurrence Is Recorded

For instance, `1,234,567.89` has **two** `,` marks. With:

```java
FieldPosition grouping =
        new FieldPosition(NumberFormat.Field.GROUPING_SEPARATOR);
StringBuffer output = new StringBuffer();
formatter.format(1234567.89, output, grouping);
```

`FieldPosition` is designed for **one** pair of indices, and standard formatters report the position of the first occurrence of the field. On Java 17+ `NumberFormat` with `Locale.US`, the result for the grouping separator is `[1,2)`; it **does not return a list** of `[1,2)` and `[5,6)`. This is why you use an iterator when repeated positions are needed.

### Absent Fields

For example, when formatting a regular number without a currency symbol, querying `NumberFormat.Field.CURRENCY` may yield `beginIndex=0` and `endIndex=0`. In practice, that is the conventional signal for "field not found," not a useful text span.

Do not call `substring(begin, end)` assuming every empty span is valid. For fields expected to have characters, check `end > begin` before styling. If you need certainty about whether an attribute is present, use `AttributedCharacterIterator` to inspect the attribute directly.

### Careful When Reusing

`FieldPosition` is a mutable object because the formatter writes indices into it. Creating a fresh object for each positioning request is clearer than reusing one across formatting calls. Similarly, `StringBuffer` is appended to; if you do not want to retain previous output, create a new buffer.

Do not share a mutable `NumberFormat` across threads without synchronization or a proper instance management strategy; Java does not guarantee thread safety for these formatters.

## 6. AttributedCharacterIterator: Inspecting All Fields in One Pass

`NumberFormat.formatToCharacterIterator(Object)` returns an `AttributedCharacterIterator`: it iterates over the formatted characters while reporting which **`AttributedCharacterIterator.Attribute`** instances apply to each span.

```java
AttributedCharacterIterator iterator =
        formatter.formatToCharacterIterator(1234567.89);
```

Attributes can be read using:

- `iterator.getAttribute(NumberFormat.Field.INTEGER)`: the attribute value at the current position, or `null` if absent.
- `iterator.getAttributes()`: map of attributes at the current position.
- `iterator.getRunStart(attribute)` / `iterator.getRunLimit(attribute)`: the largest contiguous range where **that specific attribute's value does not change**.
- `iterator.getRunStart()` / `iterator.getRunLimit()`: the range where the **entire set of attributes** does not change.
- `iterator.first()`, `next()`, `setIndex(index)`, `getBeginIndex()`, and `getEndIndex()`: character navigation APIs.

A *run* does not necessarily correspond to a linguistic unit; it is a contiguous span of indices sharing the same attribute or set of attributes under inspection.

### Why Is getRunLimit(attribute) Useful?

If an `INTEGER` span crosses grouping separators, `getRunLimit(NumberFormat.Field.INTEGER)` can return one large span covering the entire integer part. Meanwhile, `getRunLimit(NumberFormat.Field.GROUPING_SEPARATOR)` isolates each comma individually because the grouping attribute is only present at the grouping separator itself.

When styling a specific field, **query run limits using that specific attribute**. If you use the zero-argument `getRunLimit()`, changes in **any attribute** split a run; for example, the integer part would be fragmented at every grouping separator.

## 7. Standalone Java 17+ Example: Iterating Over All Digit-Grouping Positions

Create `NumberAttributedDemo.java`:

```java
import java.text.AttributedCharacterIterator;
import java.text.CharacterIterator;
import java.text.NumberFormat;
import java.util.Locale;

public class NumberAttributedDemo {
    public static void main(String[] args) {
        NumberFormat formatter =
                NumberFormat.getNumberInstance(Locale.US);
        formatter.setMinimumFractionDigits(2);
        formatter.setMaximumFractionDigits(2);

        AttributedCharacterIterator iterator =
                formatter.formatToCharacterIterator(1234567.89);

        StringBuilder builder = new StringBuilder();
        for (char c = iterator.first();
             c != CharacterIterator.DONE;
             c = iterator.next()) {
            builder.append(c);
        }
        String text = builder.toString();

        System.out.println("text=" + text);
        showField(iterator, text,
                NumberFormat.Field.INTEGER, "integer");
        showField(iterator, text,
                NumberFormat.Field.FRACTION, "fraction");
        showField(iterator, text,
                NumberFormat.Field.GROUPING_SEPARATOR, "grouping");
        showField(iterator, text,
                NumberFormat.Field.DECIMAL_SEPARATOR, "decimal");
    }

    private static void showField(
            AttributedCharacterIterator iterator,
            String text,
            AttributedCharacterIterator.Attribute field,
            String name) {

        for (int index = iterator.getBeginIndex();
             index < iterator.getEndIndex();) {
            iterator.setIndex(index);
            int limit = iterator.getRunLimit(field);

            if (iterator.getAttribute(field) != null) {
                System.out.printf(
                        "%s [%d,%d) = <%s>%n",
                        name, index, limit,
                        text.substring(index, limit));
            }

            index = limit;
        }
    }
}
```

Compile and run:

```bash
javac NumberAttributedDemo.java
java NumberAttributedDemo
```

Verified output:

```text
text=1,234,567.89
integer [0,9) = <1,234,567>
fraction [10,12) = <89>
grouping [1,2) = <,>
grouping [5,6) = <,>
decimal [9,10) = <.>
```

The program performs these steps:

1. Uses `formatToCharacterIterator(...)` to produce the formatted string with attribute metadata.
2. Iterates from `first()` until `CharacterIterator.DONE` to build the display string.
3. For each target attribute, walks runs via `getRunLimit(field)`.
4. Prints only runs where `getAttribute(field) != null`.
5. Advances `index` to `limit` on each step so no character range is skipped or repeated.

The example uses an iterator created by `NumberFormat`, which has `getBeginIndex() == 0`, so indices work directly with `String.substring`. For a general `AttributedCharacterIterator` with a non-zero begin index, adjust indices when copying into a new 0-based string.

### Why Are Grouping Separators Still Inside INTEGER?

Observe that `integer [0,9)` encompasses both commas, while `grouping` has two separate runs. A single character can simultaneously belong to the integer part and act as a grouping separator. Having both attributes is not contradictory; one describes the **overall integer span**, while the other denotes the **grouping separator** role.

## 8. Combining Attributes for Display Styling

Suppose a UI screen wants to:

- Render the integer part `1,234,567` in bold.
- Color the grouping commas `,` differently.
- Render the fractional part `89` in a smaller font.

Using only `FieldPosition.INTEGER`, you know the integer range but **have no list of grouping separators**. With `AttributedCharacterIterator`, at each character you can inspect `iterator.getAttributes()` to apply multiple style layers at once.

In `1,234,567.89`, example positions:

| Index | Character | Primary attributes |
|---:|---|---|
| 0 | `1` | `INTEGER` |
| 1 | `,` | `INTEGER` and `GROUPING_SEPARATOR` |
| 2–4 | `234` | `INTEGER` |
| 5 | `,` | `INTEGER` and `GROUPING_SEPARATOR` |
| 6–8 | `567` | `INTEGER` |
| 9 | `.` | `DECIMAL_SEPARATOR` |
| 10–11 | `89` | `FRACTION` |

You can build a list of spans and apply them in a GUI, document, or rich-text API. However, you must define precedence rules when spans **overlap**—for instance, the comma color overriding the whole-integer color.

An illustrative snippet checking attributes at a known index (inside a method with `iterator` from the example above):

```java
iterator.setIndex(1); // first ',' character
boolean integer = iterator.getAttribute(
        NumberFormat.Field.INTEGER) != null;
boolean grouping = iterator.getAttribute(
        NumberFormat.Field.GROUPING_SEPARATOR) != null;
System.out.println(integer && grouping); // true
```

This is an **illustrative snippet**, not a standalone program. It demonstrates that a grouping separator can carry two attributes simultaneously. Do not attempt to write styles into the iterator itself; it is for **reading**. Rendering code should translate runs/attributes into whatever format the actual UI library supports.

## 9. Attributes for Negative Numbers, Currency, and Percentages

Besides `INTEGER`, `FRACTION`, `GROUPING_SEPARATOR`, and `DECIMAL_SEPARATOR`, `NumberFormat.Field` describes other components depending on formatter style:

| Attribute | Role |
|---|---|
| `SIGN` | Plus or minus sign when present in output |
| `CURRENCY` | Currency symbol/code span when formatting currency |
| `PERCENT` | Percent sign |
| `PERMILLE` | Permille sign |
| `EXPONENT` | Exponent digits |
| `EXPONENT_SIGN` | Exponent sign |
| `EXPONENT_SYMBOL` | Symbol introducing the exponent part |

Example:

```java
NumberFormat currency =
        NumberFormat.getCurrencyInstance(Locale.US);
String text = currency.format(-1234.5);
```

Under typical US conventions, the result might look like `-$1,234.50`; minus-sign placement, currency symbol, and separators depend on locale, locale data, and formatter configuration. Instead of searching for `"$"` with `indexOf` or assuming `-` is always at index 0, inspect `SIGN` and `CURRENCY` on the attributed iterator of the **formatted output**.

Similarly, `NumberFormat.getPercentInstance(Locale.US)` may place the percent sign in a different position than other locales. Percentages also apply the multiply-by-100 rule during formatting; the `PERCENT` attribute only identifies the symbol span without altering calculation rules.

For fields **absent** from the output, the iterator will contain no runs with that attribute. Handle this case gracefully rather than accessing the first element of an empty list.

## 10. Comparing FieldPosition and AttributedCharacterIterator

| Criterion | `FieldPosition` | `AttributedCharacterIterator` |
|---|---|---|
| Main API | `format(number, StringBuffer, position)` | `formatToCharacterIterator(number)` |
| Primary output | A `beginIndex/endIndex` pair for one field | Character sequence with attributes and multiple runs |
| Fields per pass | One requested field type | Multiple fields traversable |
| Repeated fields like grouping | Usually records only one position | Retrieves all spans |
| Overlapping attributes | Cannot express completely | Can read multiple attributes at the same position |
| Usage overhead | Simple for a single span | More complex, yet richer information |
| Use cases | Selecting integer/fraction portion | Styling, highlighting multiple separators, rich-text rendering |

Choose according to your needs rather than always picking the more complex tool. If you only need the string, `formatter.format(number)` suffices. If you only need one span for cursor placement, `FieldPosition` is simple. If you need multiple components or overlapping attributes, use `AttributedCharacterIterator`.

## 11. What to Test When Changing Locale or Configuration

Results like `1,234,567.89` and the offsets above were verified with `Locale.US`, grouping enabled, and two decimal places. Do not apply those exact indices to other locales:

- `de-DE` typically uses `.` for grouping and `,` for decimal.
- `fr-FR` may use a non-breaking space or narrow non-breaking space for grouping; the character and length may vary across JDKs/locale data.
- Some numbering systems use non-ASCII digit characters.
- Currencies may place signs and symbols before or after the numeric part.
- `setMaximumFractionDigits(...)`, `setMinimumFractionDigits(...)`, and `setGroupingUsed(false)` affect the text and presence of fields.

Therefore, **format once using the actual locale and read the metadata from that very result**. Never compute offsets from raw digit counts or split on assumed separator characters.

### UTF-16 and Display Considerations

`beginIndex` and `endIndex` are Java UTF-16 indices. Characters outside the BMP can occupy two code units; combining characters or complex graphemes can span multiple code points. For substring extraction within the same Java string, these indices fit directly. However, when passing offsets to UI APIs measured in UTF-8 bytes, Unicode code points, or grapheme clusters, convert index systems properly.

### Multithreaded Behavior

`NumberFormat` and `DecimalFormat` instances are typically mutable and not designed to be shared concurrently across threads without synchronization. When a server formats per user/locale, create a formatter per request or use a thread-safe instance management strategy. `FieldPosition` and iterators also hold mutable positional state while being written/read, so never reuse them carelessly across concurrent tasks.

## 12. Common Mistakes

1. **Treating `endIndex` as inclusive.** In fact, the range is `[begin,end)`; call `substring(begin,end)` without adding 1.
2. **Assuming indices are relative to the newly appended portion.** `FieldPosition` counts indices across the full `StringBuffer`, including any existing prefix.
3. **Assuming `INTEGER` contains only digits.** In many formatters, grouping separators also fall inside the `INTEGER` span while carrying `GROUPING_SEPARATOR`.
4. **Using `FieldPosition` to find all commas.** It does not hold a list of repeated positions; use an attributed iterator.
5. **Calling zero-argument `getRunLimit()` expecting a single `INTEGER` span.** The run can be split by changes in other attributes. Use `getRunLimit(NumberFormat.Field.INTEGER)` when you only care about that attribute.
6. **Assuming every attribute is always present.** If there is no fraction, currency, or negative sign, the corresponding run will not exist.
7. **Slicing strings with hardcoded US offsets.** Locale, grouping rules, and fractional digit counts change offsets.
8. **Using `split` or `indexOf(',')` to infer fields.** Grouping and decimal marks vary by locale; formatter metadata is accurate.
9. **Ignoring leading offsets from minus signs or currency symbols.** The `INTEGER` span may start after a minus sign or currency symbol.
10. **Confusing `FieldPosition` with `NumberFormat.Field`.** `FieldPosition` holds a positional result; `NumberFormat.Field` identifies the field type.
11. **Reusing a `StringBuffer`/`FieldPosition` as if it were completely fresh.** Buffers append and positions mutate; create fresh instances to avoid wrong offsets or cross-call leakage.
12. **Forgetting UTF-16 indexing.** Java indices do not automatically match byte offsets or grapheme indices of external systems.

## 13. Practice Exercises

**Exercise 1.** Given the text `1,234,567.89` with 0-based indexing, what is the `FRACTION` span?

Answer: `[10,12)`, text `89`. The decimal point `.` at `[9,10)` is not part of `FRACTION`.

**Exercise 2.** For the text above, what does `FieldPosition(NumberFormat.Field.INTEGER)` return?

Answer: `[0,9)`, corresponding to `1,234,567`; grouping separators are included in this span.

**Exercise 3.** Why does `AttributedCharacterIterator` detect both commas while a single `FieldPosition(GROUPING_SEPARATOR)` does not return two ranges?

Answer: `FieldPosition` holds one begin/end pair; the attributed iterator records attributes per position and can walk multiple `GROUPING_SEPARATOR` runs.

**Exercise 4.** If a `StringBuffer` already contains the prefix `PRE:`, what are the indices of the integer part of `1,234,567.89`?

Answer: `[4,13)`, because the four prefix characters precede the number.

**Exercise 5.** In the iterator, at a `,` character of the US string, which two attributes can be present simultaneously?

Answer: `NumberFormat.Field.INTEGER` and `NumberFormat.Field.GROUPING_SEPARATOR`.

**Exercise 6.** When switching to a locale with different grouping rules, can you keep `[1,2)` and `[5,6)` unchanged?

Answer: No. You must format using the new locale, then read the runs and indices from the new output.

## 14. Key Takeaways

- `FieldPosition` provides a single `[begin,end)` span when you **already know the one field you want to locate**. It pairs easily with `NumberFormat.format(..., StringBuffer, FieldPosition)`.
- `AttributedCharacterIterator` provides **attributed spans across the entire string**, supporting multiple occurrences, multiple fields, and overlapping attributes.
- Positions are computed on the **actual formatted string**, so `Locale`, numeric symbols, currency, and format settings all apply.
- `getRunLimit(field)` traverses the exact span of a single attribute; `getRunLimit()` considers all attributes, which can split spans into smaller segments.
- When rendering or processing individual parts of a localized number, relying on formatter metadata is far more reliable than manually splitting on `.` or `,`.

**Official Documentation:** [Java SE 17 — FieldPosition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/FieldPosition.html) · [Java SE 17 — AttributedCharacterIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/AttributedCharacterIterator.html) · [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html) · [Java SE 17 — NumberFormat.Field](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.Field.html).