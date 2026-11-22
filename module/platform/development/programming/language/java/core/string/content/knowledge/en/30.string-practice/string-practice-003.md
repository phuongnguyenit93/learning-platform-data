# Building Text Reports with `StringBuilder` or `StringJoiner`

## Practice goal

In Java programs, a text report may consist of headers, data rows, aligned table columns, notes, totals, and lists of names or statuses. Two utilities in `java.lang` and `java.util` support these kinds of assembly:

- `StringBuilder` fits when you **build a string step by step**, interleaving fixed text, data fields, conditionals, headers, newlines, and formatted lines.
- `StringJoiner` fits when you **join a list of elements** with a consistent delimiter, optionally adding a `prefix` and `suffix`.

After this lesson, you will build a sales report with columns, quantities, and totals; build an owners list using `StringJoiner`; handle empty/`null` lists; control newlines, locale, and escaping; and choose the right tool for each part of a report.

## 1. Understanding the roles of the two APIs

### `StringBuilder`: building content sequentially

`StringBuilder` maintains a mutable sequence of characters. You can append values with `append()`, insert with `insert()`, replace ranges with `replace()`, or adjust length. `append()` returns the builder itself for chained calls:

```java
StringBuilder report = new StringBuilder();
report.append("REPORT").append('\n');
report.append("Items: ").append(3).append('\n');
String result = report.toString();
```

`result` contains:

```text
REPORT
Items: 3
```

In this example, `'\n'` is an intentional LF newline. If a report is internal text on the current OS, you may use `System.lineSeparator()`; if a report needs exact comparison across environments or is transmitted over a protocol requiring LF, specify `"\n"` explicitly.

The builder has `length()` (number of UTF-16 code units currently held) and `capacity()` (storage capacity before expansion is needed). It **does not automatically align columns**, insert delimiters between elements, or escape data. You must write the formatting rules yourself.

### `StringJoiner`: one element, one delimiter

`StringJoiner` has two constructors:

```java
new StringJoiner(delimiter)
new StringJoiner(delimiter, prefix, suffix)
```

Example:

```java
import java.util.StringJoiner;

StringJoiner names = new StringJoiner(", ", "[", "]");
names.add("An").add("Binh").add("Chi");
System.out.println(names); // [An, Binh, Chi]
```

`", "` appears only **between** elements; there is no trailing comma. `prefix` and `suffix` wrap the entire result. A `StringJoiner` also provides `length()`, `setEmptyValue()`, `merge()`, and `toString()`.

`StringJoiner` is well suited for member names, tags, code lists, a CSV row whose cells are already escaped, or lines/records separated by a fixed newline. It has no API for column alignment, summing totals, or managing complex multi-block layouts.

### Comparing before choosing

| Criterion | `StringBuilder` | `StringJoiner` |
| --- | --- | --- |
| Unit appended | A text fragment, number, character, or object | One `CharSequence` element |
| Delimiter between elements | Added manually with `append` or conditionals | Added automatically on `add` |
| Prefix/suffix for whole list | Appended manually | Supported directly in constructor |
| Multi-section report, headers, totals | Flexible and usually easier to read | Can be used for individual lists inside sections |
| Empty list | Result determined by caller logic | Has `setEmptyValue` |
| Aligning columns/numbers/dates | Combined with `String.format` or `Formatter` | Format each element before calling `add` |
| Pre-sizing capacity | `new StringBuilder(initialCapacity)`, `ensureCapacity` | No public capacity constructor |
| Thread safety under concurrent edits | Not guaranteed | Not guaranteed |

Both can produce the final `String`. Do not pick a tool assuming one is always faster in every case; data structure and assembly volume determine the sensible choice.

## 2. Designing the output before writing code

Suppose a sales report needs the following fields:

- Header `SALES REPORT`.
- Table with columns for name, quantity, unit price, and amount.
- Each row's amount equals `quantity × unitPrice`.
- Grand total of all rows.
- Left-aligned names and right-aligned numbers.
- Consistent decimal point so the example runs identically on every machine.

Expected output:

```text
SALES REPORT
-----------------
Name     Qty    Price     Amount
Book       2    12.50      25.00
Pen        3     1.20       3.60
TOTAL: 28.60
```

To keep monetary amounts in exact decimal form, use `BigDecimal` instead of relying on `double` addition and hoping binary representation errors do not occur. To format numbers consistently, use `Locale.ROOT`. In real applications that need grouping separators or local currency symbols, choose the locale per product requirements.

## 3. Practice 1: multi-column report with `StringBuilder`

Save the complete program as **`SalesReportDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.Locale;

public class SalesReportDemo {
    record Sale(String name, int quantity, BigDecimal unitPrice) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("Book", 2, new BigDecimal("12.50")),
                new Sale("Pen", 3, new BigDecimal("1.20"))
        );

        StringBuilder report = new StringBuilder(256);
        report.append("SALES REPORT\n");
        report.append("-----------------\n");
        report.append(String.format(
                Locale.ROOT,
                "%-8s %3s %8s %10s",
                "Name", "Qty", "Price", "Amount"
        )).append('\n');

        BigDecimal total = BigDecimal.ZERO;

        for (Sale sale : sales) {
            BigDecimal amount = sale.unitPrice().multiply(
                    BigDecimal.valueOf(sale.quantity()));
            total = total.add(amount);

            report.append(String.format(
                    Locale.ROOT,
                    "%-8s %3d %8.2f %10.2f",
                    sale.name(),
                    sale.quantity(),
                    sale.unitPrice(),
                    amount
            )).append('\n');
        }

        report.append(String.format(
                Locale.ROOT, "TOTAL: %.2f", total)).append('\n');

        System.out.print(report.toString());
    }
}
```

Compile and run with Java 17+:

```bash
javac SalesReportDemo.java
java SalesReportDemo
```

Stdout (line contents):

```text
SALES REPORT
-----------------
Name     Qty    Price     Amount
Book       2    12.50      25.00
Pen        3     1.20       3.60
TOTAL: 28.60
```

### Explaining each detail

**Data model.** `record Sale` holds name, quantity, and unit price. `BigDecimal` is constructed from decimal strings `"12.50"` and `"1.20"`; avoid initializing monetary values from `double` literals when exact decimal representation is intended.

**Computation decoupled from presentation.** `amount` is computed with `unitPrice.multiply(BigDecimal.valueOf(quantity))`; `total` is accumulated as `BigDecimal`. You only format currency to strings when inserting into the report, so subsequent math still operates on numbers.

**Column alignment.** In `"%-8s %3d %8.2f %10.2f%n"`:

- `%-8s`: left-aligned string, minimum width 8.
- `%3d`: right-aligned integer, minimum width 3.
- `%8.2f`: right-aligned decimal number, minimum width 8, displaying two digits after the decimal point.
- `%10.2f`: similar decimal number, minimum width 10.
- After each formatted part, `append('\n')` adds a consistent LF newline.

**Width is only a minimum.** If `sale.name()` is longer than 8 format units, `Formatter` does not truncate it by default and instead widens the field. Tables can lose alignment when real data is long, contains emoji, combining marks, or characters with different display widths. `Formatter` widths are not a visual column-width calculation for every terminal; when strict Unicode tables are needed, add truncation/escaping/display-width measurement policies or a dedicated renderer.

**Initial capacity 256.** This is an estimate, not a report length cap. If the report exceeds capacity, the builder grows automatically. For small reports, the default constructor `new StringBuilder()` is usually sufficient. When total data size is predictable, estimating from the sum of part lengths and formatting helps reduce resizing; avoid allocating excessively large capacities.

**Newlines.** This program uses `'\n'` on **all lines**, including after `String.format`. As a result, the in-memory output has consistent LF across Windows and Unix, convenient for tests or LF-required files. If the report targets a terminal using platform conventions, you can choose `%n` or `System.lineSeparator()` consistently, but do not mix newline styles within the same output format.

### When to use `Formatter` directly with a builder?

`String.format(...)` creates an intermediate `String` and then appends it to the builder. For large reports with many rows, `Formatter` can format directly into a `StringBuilder`:

```java
import java.util.Formatter;
import java.util.Locale;

StringBuilder out = new StringBuilder(256);
try (Formatter formatter = new Formatter(out, Locale.ROOT)) {
    formatter.format("%-8s %3d%n", "Book", 2);
    formatter.format("%-8s %3d%n", "Pen", 3);
}
String report = out.toString();
```

This is an **illustrative snippet**, not a standalone Java file; it can be placed inside a method. `Formatter` accepts the builder as an `Appendable` and writes directly into it. `StringBuilder` is not closed by `Formatter.close()` because it is not a closeable resource itself. Even so, avoiding an intermediate `String` does not automatically guarantee faster execution across all workloads; measure if this is a critical path.

## 4. Practice 2: lists, prefixes, and suffixes with `StringJoiner`

Save as **`JoinerReportDemo.java`**:

```java
import java.util.StringJoiner;

public class JoinerReportDemo {
    public static void main(String[] args) {
        StringJoiner people = new StringJoiner(", ", "Owners: ", ".");
        people.add("An").add("Binh").add("Chi");
        System.out.println(people);

        StringJoiner empty = new StringJoiner(", ", "Owners: ", ".");
        System.out.println("empty-default=" + empty);
        empty.setEmptyValue("Owners: (none).");
        System.out.println("empty-custom=" + empty);

        StringJoiner tasks = new StringJoiner(
                "\n", "TASK LIST\n", "\nEND");
        tasks.add("1. Read data");
        tasks.add("2. Create report");
        System.out.println(tasks);
    }
}
```

Run:

```bash
javac JoinerReportDemo.java
java JoinerReportDemo
```

Stdout:

```text
Owners: An, Binh, Chi.
empty-default=Owners: .
empty-custom=Owners: (none).
TASK LIST
1. Read data
2. Create report
END
```

Before `add()` is called, `StringJoiner` returns `prefix + suffix` by default: in the case above, `"Owners: ."`, even with no people added. `setEmptyValue` allows specifying a replacement string **only while the joiner is still empty**. Once an element is added, the value is built from `prefix + elements-with-delimiter + suffix`; `setEmptyValue` does not insert elements on its own.

`StringJoiner.length()` measures the length of the current string representation, including prefix/suffix or the empty value accordingly. Do not use `StringJoiner.length() == 0` to check "no elements added yet": an empty joiner with a prefix/suffix still has length greater than 0. In custom flows, keep a separate item counter if you need to know the element count.

### Each element can be a formatted line

If each record is formatted beforehand into a complete `String` line, `StringJoiner("\n")` can join the lines without checking first/last elements:

```java
StringJoiner rows = new StringJoiner("\n");
rows.add("Book,2,25.00");
rows.add("Pen,3,3.60");

String body = rows.toString(); // two lines, no trailing newline after the last line
```

Conversely, for multi-section reports needing different characters at the start/end of each block or summary lines, `StringBuilder` usually makes the layout clearer. They can be **combined**: `StringJoiner` produces a tag line, and `StringBuilder` appends that line into the main report.

## 5. Combining both in one report

A report can include a header, body, total, and owners list. Use a builder for the overall layout and a joiner for a homogeneous list of elements:

```java
import java.util.List;
import java.util.StringJoiner;

public class MixedReportDemo {
    public static void main(String[] args) {
        List<String> reviewers = List.of("An", "Binh", "Chi");
        StringJoiner reviewerList = new StringJoiner(", ");
        reviewers.forEach(reviewerList::add);

        StringBuilder report = new StringBuilder();
        report.append("REPORT\n");
        report.append("Reviewers count: ").append(reviewers.size()).append('\n');
        report.append("Reviewers: ").append(reviewerList).append('\n');

        System.out.print(report);
    }
}
```

Run:

```bash
javac MixedReportDemo.java
java MixedReportDemo
```

Stdout:

```text
REPORT
Reviewers count: 3
Reviewers: An, Binh, Chi
```

Here `StringJoiner` eliminates tracking commas between names; `StringBuilder` controls section order, labels, and newlines. For an existing simple list, `String.join(", ", reviewers)` is even more concise, but when building elements one by one, or needing a prefix/suffix or custom empty value, `StringJoiner` is often more convenient.

## 6. `null` elements, empty data, and input order

### `null` values are not skipped automatically

`StringBuilder.append((String) null)` appends the text `"null"`. `StringJoiner.add(null)` also adds the `"null"` representation. `String.join` with a `null` element can insert the literal `"null"` into the output. That is API behavior, not necessarily how an application wants to represent missing data.

Instead of printing `null` in reports by default, **set an explicit display policy**:

```java
String rawName = null;
String safeName = rawName == null ? "(no name)" : rawName;

StringJoiner names = new StringJoiner(", ");
names.add(safeName);
```

This is an illustrative snippet inside a method. In business reports, a missing value might need to display `"N/A"`, remain intentionally blank, or trigger a validation error; these choices have different meanings.

An empty element `""` is still **an added element**. For example, a joiner with an empty element and `"B"` can return `", B"`. `setEmptyValue` does not apply once `add("")` has been called. If empty elements should be excluded, filter before adding:

```java
for (String name : namesFromInput) {
    if (name != null && !name.isBlank()) {
        joiner.add(name);
    }
}
```

`namesFromInput` and `joiner` are assumed to be already declared. `isBlank()` differs from `isEmpty()`: strings made entirely of Unicode whitespace are also treated as blank. Do not filter when empty field positions carry meaning, such as the third column of a CSV row.

### Preserving meaningful order

`StringJoiner` respects `add` order. However, if source data comes from an unordered collection such as `HashSet` or `HashMap`, the report can have different ordering across runs. When reproducible reports are required, sort or use an ordered structure before joining; do not expect the joiner to sort automatically.

Data values inserted directly into a report may contain newlines, tabs, or delimiters, altering the layout. If the report is used for auditing or structured data exchange, define explicit escaping and validation policies.

## 7. A delimiter is not escaping: CSV example

`StringJoiner(",")` only inserts commas between elements. If a field contains a comma, double quote, or newline, calling `add(value)` verbatim **does not produce valid CSV**. For CSV, each cell must be escaped per format rules: fields containing commas, double quotes, LF, or CR should be wrapped in double quotes; double quotes inside the value are doubled.

Save the program **`CsvJoinerDemo.java`**:

```java
import java.util.StringJoiner;

public class CsvJoinerDemo {
    public static void main(String[] args) {
        String[] columns = {
                "An",
                "Note, important",
                "Said \"A\""
        };

        StringJoiner row = new StringJoiner(",");
        for (String value : columns) {
            row.add(csvCell(value));
        }

        System.out.println(row);
    }

    private static String csvCell(String value) {
        if (value == null) {
            return "";
        }

        boolean quote = value.indexOf(',') >= 0
                || value.indexOf('"') >= 0
                || value.indexOf('\n') >= 0
                || value.indexOf('\r') >= 0;

        if (!quote) {
            return value;
        }
        return "\"" + value.replace("\"", "\"\"") + "\"";
    }
}
```

Run:

```bash
javac CsvJoinerDemo.java
java CsvJoinerDemo
```

Stdout:

```text
An,"Note, important","Said ""A"""
```

In this example, **escaping happens inside `csvCell`**; `StringJoiner` only joins the processed fields. This demonstrates common CSV rules and does not replace a battle-tested CSV library when full format specs, charsets/BOM, newline styles, quoting policies, or untrusted input must be handled.

Similarly, never hand-assemble JSON using `StringBuilder.append("{\"name\":\"").append(value)...` with arbitrary data; use a JSON serializer to handle quotes, slashes, and control characters properly. A human-readable report and a structured data payload require different contracts.

## 8. Formatting choices that affect report output

### Newline and charset conventions

If the output is only printed to the console, `System.out.print(report)` writes the string verbatim; `System.out.println(report)` adds a trailing newline. If the report already ends with a newline, `println` can create an unintended blank line. `Formatter`'s `%n` uses the platform newline, whereas `"\n"` is always LF.

When writing to a text file, specify UTF-8 explicitly:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("report.txt");
Files.writeString(path, report.toString(), StandardCharsets.UTF_8);
```

The snippet above is illustrative code inside a method that handles or declares `IOException`. `report` is assumed to exist. The reader should use the same charset: `Files.readString(path, StandardCharsets.UTF_8)`. Writing to a file does not mutate the original `StringBuilder` content.

### Locale and numbers

`String.format(Locale.ROOT, "%.2f", amount)` provides stable formatting for examples. If a report for Vietnamese users needs grouping separators, currency symbols, and local conventions, choose `NumberFormat` or `DecimalFormat` with the appropriate locale, and specify rounding rules explicitly. For machine-readable reports, it is best to have a protocol separating data from presentation.

For tabular data, `%-8s` only sets the **minimum width of the formatted field**, not the guaranteed display width of Vietnamese text, emoji, or character clusters. If a name is longer than the column, it is not truncated by default and can break layout. Do not treat space-aligned text tables as unambiguous data transfer; when exchanging data between systems, use CSV/JSON or a dedicated format.

### Length limits and capacity

When the row count is large, `StringBuilder` may resize multiple times. You can estimate upfront from row count and average size: `new StringBuilder(estimatedUnits)`, where `estimatedUnits` is the number of **UTF-16 units**, not UTF-8 bytes. Without a reliable estimate, start with the default and optimize only when a profiler/benchmark shows it is needed.

Do not build a giant report entirely in RAM if size is unbounded. For very large datasets, writing sequentially to a `BufferedWriter` or `OutputStream` is more appropriate. `StringBuilder` and `StringJoiner` are for constructing one result in memory; streaming output is a different resource problem.

## 9. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Manually calling `append(", ")` after every element | Trailing comma at the end | Use `StringJoiner` or check `i > 0` |
| Mixing `println`, `%n`, and `\n` arbitrarily | Inconsistent newline bytes or blank lines | Standardize output newlines once |
| Using `double` for critical monetary calculations | Binary precision errors can accumulate | Use `BigDecimal` and explicit rounding rules |
| Assuming `StringJoiner` drops `null`/`""` automatically | Outputs literal `null` or empty elements | Validate/filter/map according to policy |
| Joining CSV cells with commas alone | Commas/quotes in data break structure | Escape cells or use a CSV library |
| Using spaces and `%8s` for arbitrary Unicode tables | Terminals may render misaligned columns | Use string measurement/truncation policies or a table renderer |
| Calling `toString()` inside every loop iteration to keep concatenating | Creates many intermediate strings | Keep the builder until the end |
| Not stabilizing source data order | Report order changes unexpectedly | Sort or use an ordered collection |
| Modifying one builder concurrently from multiple threads | Race conditions, corrupted output | Keep per-thread/task ownership or synchronize properly |

Both `StringBuilder` and `StringJoiner` are mutable and **not thread-safe**. For independent report generation tasks, it is usually best to create them as local variables inside a method. `StringBuffer` has synchronized methods but does not by itself solve multi-step access logic; there is no need to switch to it when there is no sharing requirement.

## 10. Follow-up exercises

**Exercise 1 — Choosing a tool.** A report only needs the line `"Tags: java, core, string"` from a dynamic list of tag names. Which tool should be used? If there are no tags yet, it must display `"Tags: (empty)"` — how should you handle that?

**Exercise 2 — Summary report.** Add a total `quantity` accumulator to `SalesReportDemo`, then add the line `"TOTAL QUANTITY: 5"` after the grand total line. Keep integer summation and currency arithmetic separate.

**Exercise 3 — Preserving column positions.** Given a data array containing `"A"`, `""`, and `"C"`. If these are three CSV columns, should empty elements be filtered out before joining? Why?

**Exercise 4 — Stable ordering.** A list of names comes from a `HashSet`. How do you produce a lexicographically sorted tag string so two runs with the same data yield identical results?

**Exercise 5 — Predicting exact output.** Read the code:

```java
StringJoiner j = new StringJoiner(" | ", "<", ">");
System.out.println(j);
j.setEmptyValue("(empty)");
System.out.println(j);
j.add("x").add("y");
System.out.println(j);
```

Answers in order:

```text
<>
(empty)
<x | y>
```

**Hints:** (1) `StringJoiner(", ", "Tags: ", "")`; to display a custom empty state, call `setEmptyValue("Tags: (empty)")`. (2) Maintain `int quantityTotal` and update it inside the loop. (3) No, because empty fields occupy valid column positions and must be preserved. (4) Copy to a `List` and `sort` or use an already ordered source; define an appropriate comparator. (5) `setEmptyValue` only takes effect when no elements have been added yet.

### References

- [`StringBuilder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html)
- [`StringJoiner` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/StringJoiner.html)
- [`Formatter` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html)
- [`BigDecimal` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)