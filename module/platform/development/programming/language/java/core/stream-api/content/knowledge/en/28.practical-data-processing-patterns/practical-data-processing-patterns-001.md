# Cleaning, Normalization, and Filtering Out Invalid Data

In real-world applications, data rarely enters a system in a clean, ready-to-use form. An order record may contain a product code with trailing whitespace, a quantity stored as a string, a non-existent calendar date, a malformed monetary amount, or a duplicate identifier key. Before using that data for aggregation, grouping, or database persistence, it is necessary to **clean, normalize, validate, and decide how to handle invalid records**.

The **Java Stream API** helps express this process as a declarative pipeline made of *lazy* intermediate operations such as `map`, `filter`, and `flatMap`, triggered by a terminal operation such as `collect`. However, a short pipeline is not automatically safe: `filter` discards information about rejected data, arbitrary normalization can alter business meaning, and parsing directly inside `map` can allow a single bad record to abort an entire batch.

This lesson belongs to the **Practical Data Processing Patterns** chapter. The goal is to build a clear, testable processing flow that favors pure functions, separates valid records from rejected ones, and preserves rejection reasons for reconciliation.

## 1. Define the Contract Before Writing the Pipeline

Suppose the input consists of raw orders with five fields: order ID, product SKU, quantity, unit price, and order date. Users may enter all of them as strings.

| Record | Order ID | SKU | Quantity | Unit Price | Date | Expected Result |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `" a-001 "` | `" sku-01 "` | `"2"` | `"15.50"` | `"2026-03-05"` | Valid after normalization. |
| 2 | `"A-002"` | `"SKU-02"` | `"0"` | `"4.50"` | `"2026-03-05"` | Rejected: quantity must be positive. |
| 3 | `"A-003"` | `"SKU-03"` | `"1"` | `"7.20"` | `"2026-02-30"` | Rejected: invalid date. |
| 4 | `"A-004"` | `"SKU-04"` | `"3"` | `"7.20"` | `"2026-03-06"` | Valid. |
| 5 | `"A-005"` | `"SKU-05"` | `"1"` | `"oops"` | `"2026-03-06"` | Rejected: malformed unit price. |

**Assumed business rules for this exercise:** order IDs and SKUs are case-insensitive and contain only `A–Z`, digits, or hyphens; quantity is a positive integer of at most six digits; price is non-negative with at most two decimal places; dates use ISO `yyyy-MM-dd`. These are **example rules**, not universal definitions for every commerce system.

A solid pipeline must clarify:

1. **What is the input data?** Java objects, CSV/JSON text, or a file stream? Who is responsible for splitting fields?
2. **What is normalization allowed to change?** May leading/trailing whitespace be stripped and characters uppercased?
3. **Which conditions count as errors?** Blank values, wrong types, out-of-range values, invalid dates, duplicate keys, or catalog mismatches?
4. **How should an invalid record be handled?** Rejected with a reason, returned for correction, held in *quarantine*, or used to halt the entire batch?
5. **Who needs the output?** A clean list for calculation, an error list for display, or both for auditing?

## 2. Distinguish Cleaning, Normalization, Validation, and Rejection

These steps are related, not synonymous:

| Step | Example | Purpose |
| --- | --- | --- |
| **Cleaning** | Stripping leading/trailing whitespace from an order ID. | Remove permitted input noise. |
| **Normalization** | `"sku-01"` → `"SKU-01"`. | Bring equivalent representations into one canonical form. |
| **Validation** | Checking that quantity is greater than 0 and the date exists. | Confirm the data satisfies the rules. |
| **Parsing** | `"2"` → `int 2`; `"15.50"` → `BigDecimal`. | Convert storage format into domain types. |
| **Rejection/Quarantine** | Returning reason `quantity must be positive`. | Prevent bad data from entering reports without losing error trails. |

A recommended processing flow:

```text
Raw data source
       |
       v
Split records and fields according to the source format
       |
       v
Controlled cleaning / normalization
       |
       v
Check required fields, format, and value domain
       |
       v
Type parsing and cross-field rule validation
       |
       v
Classification result: Valid(order) or Invalid(reason)
       |                                   |
       v                                   v
Valid list                            Error list
       |                                   |
       +--> stats, grouping, DB            +--> reporting, data repair
```

Not every step has to be a separate `map` or `filter` call. For data that may be malformed, a `parseAndValidate` function returning **either a value or an error** is usually clearer than scattering hard-to-follow `try/catch` blocks across multiple lambdas.

## 3. String Normalization Must Respect Field Semantics

Example of normalizing a case-insensitive identifier (Java 11+):

```java
import java.util.Locale;

static String normalizeBusinessKey(String raw) {
    return raw == null
        ? null
        : raw.strip().toUpperCase(Locale.ROOT);
}

System.out.println(normalizeBusinessKey("  sku-01 ")); // SKU-01
```

`strip()` removes leading and trailing whitespace according to Java's `Character.isWhitespace` rules; `trim()` uses older rules based on characters with code points no greater than `U+0020`. They are **not completely equivalent**, and neither solves every Unicode whitespace character. If a source includes non-breaking spaces or special control characters, define an explicit policy.

`Locale.ROOT` prevents case conversion from depending on the machine's default locale. However, **you must not automatically uppercase every field**:

- SKUs defined as case-insensitive can be normalized to uppercase.
- Passwords, digital signatures, or secret tokens must follow their own authentication rules; altering them arbitrarily can break their meaning.
- Email addresses do not always allow treating the **entire address** as case-insensitive; local-part rules depend on the receiving mail system.
- Display names should preserve the representation appropriate for language and UI requirements.

### Normalize Unicode Only When Truly Needed

Two visually identical strings can use different sequences of Unicode code points. Java provides `Normalizer`:

```java
import java.text.Normalizer;

String canonical = Normalizer.normalize(
    inputText, Normalizer.Form.NFC
);
```

`NFC` is one Unicode normalization form, useful when the domain treats combining-character equivalents as the same value. However, Unicode normalization does not automatically resolve business aliases, strip Vietnamese diacritics, disambiguate identities, or fix typos. Do not use `replaceAll("\\s+", "")` to remove all whitespace in personal names, addresses, or data where separators carry meaning.

**Principle:** normalization must be **intentional and tested on representative data**; never discard information just to boost the "valid" record rate.

## 4. Validate Format and Domain Range Before Parsing

A regex can verify **string shape**, but it does not replace full validation.

```java
import java.util.regex.Pattern;

Pattern quantityFormat = Pattern.compile("[0-9]{1,6}");

System.out.println(quantityFormat.matcher("123").matches()); // true
System.out.println(quantityFormat.matcher("-1").matches());  // false
System.out.println(quantityFormat.matcher("2.5").matches()); // false
System.out.println(quantityFormat.matcher("0").matches());   // true
```

The string `"0"` matches the regex yet is **invalid in value range** if quantity must be greater than 0. Therefore, you need both:

```java
if (!quantityFormat.matcher(text).matches()) {
    // Invalid input shape.
} else {
    int quantity = Integer.parseInt(text);
    if (quantity <= 0) {
        // Valid shape, but violates the business rule.
    }
}
```

In this example, capping at six digits guarantees `Integer.parseInt` will not overflow. In systems supporting larger numbers, check bounds explicitly or catch `NumberFormatException` intentionally.

### Dates Must Exist, Not Just Match a Pattern

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;

try {
    LocalDate date = LocalDate.parse(
        "2026-02-30", DateTimeFormatter.ISO_LOCAL_DATE
    );
} catch (DateTimeParseException ex) {
    System.out.println("Invalid date");
}
```

`2026-02-30` looks like a valid `yyyy-MM-dd` shape, yet does not exist. `ISO_LOCAL_DATE` uses strict date resolution rules. If the source is a timestamp with a time zone, do not arbitrarily convert it to `LocalDate` before establishing the business time zone.

### Monetary Amounts Should Not Pass Through `double` When Decimal Precision Matters

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal price = new BigDecimal("15.50")
    .setScale(2, RoundingMode.UNNECESSARY);

System.out.println(price); // 15.50
```

Construct `BigDecimal` from a validated decimal string rather than `new BigDecimal(0.1)` when exact decimal representation of `0.1` is required. For currencies with specific rounding rules or special subunits, design explicit precision limits, scale, and rounding policies.

## 5. When to Use `filter`, `map`, and `flatMap`?

`map` represents transforming **one element into one result**; `filter` only retains matching elements. If a line only needs checking for non-`null` and non-empty, these two methods are enough:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

List<String> values = Arrays.asList("  A  ", null, " ", " B ");

List<String> cleaned = values.stream()
    .filter(Objects::nonNull)
    .map(String::strip)
    .filter(s -> !s.isEmpty())
    .collect(Collectors.toList());

System.out.println(cleaned); // [A, B]
```

This is valid when **discarding all blank data without recording a reason is permitted**. When data requires reconciliation, knowing which rows were dropped and why matters: plain `filter` **cannot preserve that information**.

A better ingestion design uses a result type:

```text
parseAndValidate(raw)
       |
       +-- Valid(data)
       |
       +-- Invalid(rowNumber, field, reason)
```

Afterward, you can choose to collect both branches, or take only the valid branch when business rules allow.

## 6. Complete Project: Importing Orders While Preserving Both Valid Data and Errors

The example below uses **Java 17+** for `record` and `Collectors.teeing` (`teeing` itself has existed since Java 12). `RawOrder` represents data *already split into fields by a source-format parser*. If the source is CSV, use a CSV parser that supports quotes and escapes; never assume `line.split(",")` suffices for real-world CSV data.

Example policy:

- `id`, `sku`: ASCII strings of 1–20 characters containing letters, digits, and `-`; leading/trailing whitespace is stripped via `strip()`, and codes are normalized to uppercase.
- `units`: 1–6 digits, value must be greater than 0.
- `unitPrice`: non-negative, 1–9 integer digits and at most 2 decimal places.
- `orderedOn`: a real, existing ISO date.
- Each record produces exactly one `Parsed`: either an `Order`, or a `Reject` with row number and reason.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public final class CleanOrderImport {
    private static final Pattern KEY =
        Pattern.compile("[A-Z0-9-]{1,20}");
    private static final Pattern UNITS =
        Pattern.compile("[0-9]{1,6}");
    private static final Pattern PRICE =
        Pattern.compile("[0-9]{1,9}(\\.[0-9]{1,2})?");

    record RawOrder(
        String id,
        String sku,
        String units,
        String unitPrice,
        String orderedOn
    ) {}

    record Order(
        String id,
        String sku,
        int units,
        BigDecimal unitPrice,
        LocalDate orderedOn
    ) {}

    record Reject(int rowNumber, String field, String reason) {}

    record Parsed(Order order, Reject rejection) {
        static Parsed valid(Order order) {
            return new Parsed(order, null);
        }
        static Parsed invalid(int row, String field, String reason) {
            return new Parsed(null, new Reject(row, field, reason));
        }
        boolean isValid() {
            return order != null;
        }
    }

    record ImportReport(List<Order> accepted, List<Reject> rejected) {
        ImportReport {
            accepted = List.copyOf(accepted);
            rejected = List.copyOf(rejected);
        }
    }

    private CleanOrderImport() {}

    static String stripOrNull(String text) {
        return text == null ? null : text.strip();
    }

    static String canonicalKey(String text) {
        String stripped = stripOrNull(text);
        return stripped == null
            ? null
            : stripped.toUpperCase(Locale.ROOT);
    }

    static Parsed parseRow(int rowNumber, RawOrder raw) {
        if (raw == null) {
            return Parsed.invalid(rowNumber, "row", "Null record");
        }

        String id = canonicalKey(raw.id());
        String sku = canonicalKey(raw.sku());
        String unitsText = stripOrNull(raw.units());
        String priceText = stripOrNull(raw.unitPrice());
        String dateText = stripOrNull(raw.orderedOn());

        if (id == null || !KEY.matcher(id).matches()) {
            return Parsed.invalid(
                rowNumber, "id", "Order ID is empty or malformed"
            );
        }
        if (sku == null || !KEY.matcher(sku).matches()) {
            return Parsed.invalid(
                rowNumber, "sku", "Malformed SKU"
            );
        }
        if (unitsText == null ||
                !UNITS.matcher(unitsText).matches()) {
            return Parsed.invalid(
                rowNumber, "units", "Quantity is not a valid integer"
            );
        }
        int units = Integer.parseInt(unitsText);
        if (units <= 0) {
            return Parsed.invalid(
                rowNumber, "units", "Quantity must be greater than 0"
            );
        }

        if (priceText == null ||
                !PRICE.matcher(priceText).matches()) {
            return Parsed.invalid(
                rowNumber, "unitPrice", "Price must be non-negative with at most 2 decimal places"
            );
        }
        BigDecimal unitPrice = new BigDecimal(priceText)
            .setScale(2, RoundingMode.UNNECESSARY);

        if (dateText == null || dateText.isEmpty()) {
            return Parsed.invalid(
                rowNumber, "orderedOn", "Missing order date"
            );
        }
        LocalDate orderedOn;
        try {
            orderedOn = LocalDate.parse(
                dateText, DateTimeFormatter.ISO_LOCAL_DATE
            );
        } catch (DateTimeParseException ex) {
            return Parsed.invalid(
                rowNumber, "orderedOn", "Non-existent date or invalid ISO format"
            );
        }

        return Parsed.valid(
            new Order(id, sku, units, unitPrice, orderedOn)
        );
    }

    static ImportReport importOrders(List<RawOrder> rawRows) {
        return IntStream.range(0, rawRows.size())
            .mapToObj(i -> parseRow(i + 1, rawRows.get(i)))
            .collect(Collectors.teeing(
                Collectors.filtering(
                    Parsed::isValid,
                    Collectors.mapping(
                        Parsed::order, Collectors.toList()
                    )
                ),
                Collectors.filtering(
                    result -> !result.isValid(),
                    Collectors.mapping(
                        Parsed::rejection, Collectors.toList()
                    )
                ),
                ImportReport::new
            ));
    }

    public static void main(String[] args) {
        List<RawOrder> input = List.of(
            new RawOrder(
                " a-001 ", " sku-01 ", "2", "15.50", "2026-03-05"
            ),
            new RawOrder(
                "A-002", "SKU-02", "0", "4.50", "2026-03-05"
            ),
            new RawOrder(
                "A-003", "SKU-03", "1", "7.20", "2026-02-30"
            ),
            new RawOrder(
                "A-004", "SKU-04", "3", "7.20", "2026-03-06"
            ),
            new RawOrder(
                "A-005", "SKU-05", "1", "oops", "2026-03-06"
            )
        );

        ImportReport report = importOrders(input);

        System.out.println("Accepted: " + report.accepted().size());
        System.out.println("Rejected: " + report.rejected().size());
        // Accepted: 2
        // Rejected: 3

        report.rejected().forEach(System.out::println);

        BigDecimal total = report.accepted().stream()
            .map(order -> order.unitPrice().multiply(
                BigDecimal.valueOf(order.units())
            ))
            .reduce(BigDecimal.ZERO, BigDecimal::add);

        System.out.println(total); // 52.60
    }
}
```

### Analysis of How the Code Is Structured

1. **Normalization happens before code validation:** `" a-001 "` becomes `"A-001"`, then format validation runs.
2. **Parsing runs only after structural validation:** the regex bounds the digit count, so `Integer.parseInt` cannot overflow within the defined data domain.
3. **Data errors are represented as values:** an invalid date produces a `Reject` rather than letting an exception escape and halt the entire pipeline.
4. **Each row is parsed once:** `IntStream.range` supplies the row index, and `mapToObj` creates one `Parsed` per input.
5. **`teeing` collects two outputs in a single terminal operation:** the first branch retains `Order`, and the second branch retains `Reject`. Both downstream collectors receive each `Parsed` result without reading or re-parsing the source twice.
6. **Results are unmodifiable at the list level:** `List.copyOf` prevents adding or removing elements in the report lists. `Order` and `Reject` are records containing only immutable types in this example; `BigDecimal` and `LocalDate` values are also immutable.
7. **Revenue is computed only on accepted data:** `BigDecimal` avoids binary floating-point rounding errors in the exercise's decimal monetary summation.

This result **does not yet handle duplicate order IDs across rows**, SKU catalog lookups, policy price caps, or transactional database writes. Those are **dataset/system-level** validation rules that require a separate step and cannot be inferred from each individual row being valid.

## 7. No Error Report Needed? Intentionally Extract Only Valid Data

In applications where invalid data only needs to be skipped **by business contract**, you can turn parse results into `Optional<T>` and use `flatMap(Optional::stream)` (Java 9+):

```java
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

// Assume tryParse takes a String and returns Optional<Integer>.
List<Integer> values = rawTexts.stream()
    .map(this::tryParse)
    .flatMap(Optional::stream)
    .collect(Collectors.toList());
```

This is an **illustrative snippet** inside a class where `tryParse` and `rawTexts` are defined; it is not a standalone program. `Optional.empty()` represents the absence of a value, and `flatMap` drops that case from the result.

The advantage is a short pipeline without using `null` to represent failure. The downside is **losing the reason data was invalid**. If importing batches of orders, payments, or records that require audit trails, keep error objects like `Reject` instead of silently dropping rows.

On Java 16+, `mapMulti` can also emit 0 or 1 valid results without creating many sub-streams. Use it only when the output shape and traceability fit; a shorter approach is not always a better design.

## 8. Duplicate Keys After Normalization: Define an Explicit Policy

Cleaning and normalization can cause **two different raw values to become the same key**:

```text
" a-001 " ---> "A-001"
"A-001"   ---> "A-001"
```

Do not simply call `distinct()` or `toMap(..., (first, second) -> first)` and assume duplicates have been handled properly. Sometimes the business wants to keep the newest record, sometimes it must reject **both** for reconciliation, and sometimes it wants to merge quantities.

If you want to detect order IDs that appear multiple times among parsed `Order` objects:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

// orders is a List<Order> whose Order.id() values are already normalized.
Map<String, Long> frequency = orders.stream()
    .collect(Collectors.groupingBy(
        Order::id, Collectors.counting()
    ));

List<Order> onlyUniqueIds = orders.stream()
    .filter(order -> frequency.get(order.id()) == 1L)
    .collect(Collectors.toList());
```

This pattern **excludes all records with duplicate IDs** from the accepted list. In a real application, you should create **error records including the row position of each duplicate**, rather than merely dropping them and losing the reason. `Order` in the full example does not store row index; you can store the index alongside the parse result or place it in an import DTO with metadata.

If you choose `toMap`, the overload without a merge function throws `IllegalStateException` on duplicate keys. The merge function must be chosen based on business semantics, not merely to make the exception disappear. With parallel streams, the merge function must also have appropriate semantics when combination order changes.

## 9. Normalization Must Be Stable, Reproducible, and Nearly Idempotent

A good normalization function is typically **idempotent**: normalizing again does not change an already-normalized result.

```java
import java.util.Locale;

static String normalize(String value) {
    return value.strip().toUpperCase(Locale.ROOT);
}

String once = normalize("  sku-01 ");
String twice = normalize(once);
System.out.println(once.equals(twice)); // true
```

This makes the pipeline easy to test and prevents dependence on how many times data passes through an ETL step. However, normalization idempotence **does not guarantee** the entire import is idempotent: saving the same order twice can still create two transactions without an idempotency key or a uniqueness constraint at the write layer.

The `parseRow` and `canonicalKey` functions in the project do not log to shared variables, make network calls, or depend on the current time. Therefore, given the same input and the same rules, they produce the same output. Rules may depend on **catalog versions, currencies, time zones, or languages**; when they do, pass them explicitly as configuration data and record version markers to reproduce results.

## 10. Safety Rules When Switching to a Parallel Stream

A data-cleaning pipeline **can** run in parallel when elements are independent, the source is splittable, and lambdas obey the Stream contract. Yet parallel processing may not be faster if each record is trivial or most time is spent waiting on I/O.

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

// Illustrated in a scope with parseRow and rawRows as in the program above.
List<Parsed> results = IntStream.range(0, rawRows.size())
    .parallel()
    .mapToObj(i -> parseRow(i + 1, rawRows.get(i)))
    .collect(Collectors.toList());
```

Conditions for correct results:

- **Do not modify the source** while the stream iterates; avoid adding or removing elements of `rawRows` while the task runs.
- **Do not write to an external `ArrayList`** inside `parallel().forEach(list::add)`; use `collect` or design a proper result type.
- **Do not let the parser write to shared mutable counters or annotations**. If error statistics are needed, aggregate them from `Parsed` afterward or use a compliant collector.
- **Do not rely on lambda invocation order**. If row numbers are needed, derive indices from an ordered source like `IntStream.range` and attach the index to the result.
- **Do not use exceptions as arbitrary control flow** for predictable errors. Use success/failure result values so readers understand rejection conditions.
- **Measure performance before enabling parallelism**. For small inputs, task-splitting and combining overhead often outweighs any gain.

A `List` source is ordered, and `Collectors.toList()` preserves encounter order in the result even during parallel execution; the **actual execution order of lambdas** does not need to match that order. If you switch to an `UNORDERED` collector or an unordered source, re-evaluate the result ordering contract.

## 11. Cases Where You Should Not Silently "Fix to Make Valid"

Not all bad data can be repaired automatically:

| Data | Risk of Auto-Fixing | Recommendation |
| --- | --- | --- |
| Date `2026-02-30` | Shifting into the next month can alter business timing. | Reject and ask the submitter to confirm. |
| Price `1.234,50` | Usage of `.`/`,` depends on locale; mis-parsing changes the amount. | Define the locale/format contract before converting. |
| Price `12.345` with 2-decimal scale | Automatic rounding can change the amount due. | Apply an approved rounding rule or reject. |
| Negative quantity `-3` | May represent returned goods rather than a typo. | Distinguish sales orders from return transactions. |
| Accented email/person names | Stripping accents or uppercasing can wrongly merge identities. | Normalize per field and identity policy. |
| Duplicate order ID | Dropping one record may lose a real transaction. | Use a reconciliation policy and uniqueness keys. |
| Missing identifier | Generating uncontrolled dummy IDs breaks traceability. | Use a contracted ID generator or report an error. |

A good pipeline distinguishes **"can normalize without changing meaning"** from **"insufficient information to auto-fix"**. That distinction is often more important than how many `map` calls you can write.

## 12. Collecting Data-Quality Metrics

When both valid results and error results are preserved, you can compute metrics to monitor ingestion quality:

```java
import java.util.Map;
import java.util.stream.Collectors;

// report is the ImportReport produced in the complete example.
Map<String, Long> rejectedByField = report.rejected().stream()
    .collect(Collectors.groupingBy(
        Reject::field,
        Collectors.counting()
    ));

System.out.println(rejectedByField);
// Example: {units=1, unitPrice=1, orderedOn=1}
```

Beyond per-field error counts, reports can track total rows received, accepted rows, rejection rate, duplicate-key frequency, parse duration, and common reasons. **Do not treat the row count retained by `filter` as the clean-data count** if validation has not yet checked all business constraints.

When exporting error details, avoid dumping entire raw records containing personal data, tokens, or payment details into public logs. Log only necessary fields, and consider masking sensitive data, read permissions, and retention policies.

## 13. Testing Boundary Data and Invariants

A minimal test suite should include:

| Case | Expectation |
| --- | --- |
| Strings with leading/trailing whitespace | Cleaned according to policy. |
| Codes differing in case | Same normalized form if the identifier rule allows. |
| Required field is `null` or blank | Rejected with the field name. |
| Quantity `0` or negative | Rejected per the order contract. |
| Overlong quantity | Rejected before `parseInt`. |
| Negative price, wrong decimal separator, or >2 decimal places | Rejected or handled per explicit policy. |
| Non-existent or non-ISO date | Rejected with reason. |
| Two IDs colliding after normalization | Handled by an explicit batch-level duplicate-key policy. |
| Empty batch | Both accepted and rejected lists are empty. |
| Re-processing the same data | Same accepted records and error reasons, independent of execution schedule. |

For every input of `n` rows, if the result model has only two states and each row is processed exactly once, this invariant holds:

\[
\text{acceptedCount} + \text{rejectedCount} = n
\]

In exercises, this invariant can be checked with `assert` or test assertions. If one row has **multiple errors** and the system chooses to store all of them, the total error count can be **greater than** the rejected record count; in that case, distinguish *rejected row count* from *detected error count*.

When using a parallel stream, the result must still yield the same set of accepted and rejected records. Lambda execution order does not need to match, but **row indices and error reasons** must stay bound to the right input.

## 14. Performance and Resource Considerations for Cleaning Pipelines

Main costs usually depend on **source format and validation logic**, not merely Stream method names:

- **Regex:** precompile `Pattern` instances to avoid recompiling per record; avoid overly complex regexes that can trigger expensive backtracking on untrusted input.
- **Unicode normalization:** allocates new strings; apply it only to fields that genuinely need it.
- **Date and currency parsing:** use explicit formats rather than creating formatters or arbitrary locale configs per element.
- **Memory:** `toList` retains all results; for very large batches, consider chunking into batches and controlled error storage/quarantine.
- **Laziness and short-circuiting:** `map`/`filter` only run when requested by a terminal operation; `findFirst` or `limit` may not process all records.
- **I/O:** `Files.lines` must be closed with `try-with-resources`. A terminal operation does not replace closing the stream.
- **Parallelism:** worth benchmarking on sufficiently large data with pure parsers; when work involves DB or network calls, bound concurrency and coordinate tasks separately.

Example of processing file lines when reading once:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> nonEmptyLines(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.map(String::strip)
            .filter(s -> !s.isEmpty())
            .collect(Collectors.toList());
    }
}
```

This snippet only cleans **text lines**; do not pretend each line has already been parsed and validated into an order. For CSV with quoted fields, embedded newlines, or complex encodings, use an appropriate parser before normalizing fields. Do not feed `Files.lines` into an infinite pipeline or assume the file cannot change while being read.

## 15. Common Pitfalls

| Mistake | Consequence | Better Approach |
| --- | --- | --- |
| `map(Integer::parseInt)` directly on raw input | A single bad string throws `NumberFormatException` and aborts the batch. | Validate format and range, and represent errors per record. |
| `filter(x -> isValid(x))` discarding all bad records | No visibility into which rows failed or why. | Use `Parsed`/`Reject` or a `Result` model. |
| Stripping all whitespace and Unicode diacritics | Can alter names, keys, or meaningful data. | Normalize per field according to contract. |
| Using `double` for exact money | Introduces representation rounding errors. | Use `BigDecimal` or smallest integer currency units where appropriate. |
| Treating a matching date regex as a valid date | Can accept non-existent calendar dates. | Parse strictly using date/time APIs. |
| Deduplicating keys with `distinct()` without reconciliation | Can silently lose valid business records. | Build a duplicate-key detection and handling policy. |
| Writing to an external `ArrayList` in `parallel().forEach` | Races, missing data, or corrupted order. | Collect via `collect` or a compliant collector. |
| Using `peek` to log every record | Some pipelines may optimize or short-circuit and skip actions. | Collect results and errors explicitly. |
| Assuming `List.copyOf` deep-copies elements | Mutable objects inside can still be mutated. | Use immutable value types or copy at element level. |
| Lacking tests for empty or boundary data | Bugs surface only on real production data. | Test missing fields, number/date errors, duplicates, and empty batches. |

## 16. Practice Exercises

**Exercise 1 — Controlled cleaning.** Given a `List<String>` containing `"  SKU-01 "`, `"sku-01"`, `null`, and `" SKU 02 "`. Normalize under the rule that SKUs contain only letters, digits, and `-`. Which values are valid? Which must be rejected? Why should `"SKU 02"` not automatically have its inner space removed to become a different code unless the business allows it?

**Exercise 2 — Preserving errors.** Refactor the pipeline `map(String::strip).filter(...).map(Integer::parseInt)` so each element produces a `Result<Integer, Error>` (or two equivalent records), with the error including the row number. Do not let a single bad row halt the batch.

**Exercise 3 — Date validation.** Use `DateTimeFormatter.ISO_LOCAL_DATE` to process `"2026-02-28"`, `"2026-02-29"`, and `"2026-02-30"`. Predict which values are accepted and explain leap years.

**Exercise 4 — Currency.** Given price strings `"12.30"`, `"0"`, `"5.123"`, and `"-1.00"`. Write a validator for a non-negative contract with at most two decimal places; sum the valid prices with `BigDecimal` and explain why `double` should not be used.

**Exercise 5 — Duplicate records.** After normalization, two orders share ID `A-001`. Use `groupingBy(Order::id, counting())` to detect duplicate IDs, propose a handling policy, and explain how to retain error row numbers.

**Exercise 6 — Quality report.** Using the `CleanOrderImport` example, count total records, valid records, and rejected records, and group `Reject` entries by field name. Verify the invariant `accepted + rejected = input.size()`.

**Exercise 7 — Parallel stream.** Run the same parse function on `IntStream.range(...).parallel()`. Compare results by row number between sequential and parallel runs. Explain why using an `AtomicInteger` to assign row numbers in lambda-call order is inappropriate.

**Exercise 8 — Project extension.** Add validation for SKUs against an allowed catalog, detect prices exceeding a cap, and separate fixable errors from blocking errors. Write to the database only orders satisfying all required rules, with idempotency and reconciliation mechanisms to prevent duplicate imports on rerun.

## 17. Pre-Production Checklist

- [ ] Contracts exist for required fields, numeric types, units, date formats, and locale.
- [ ] Only fields permitted by business rules are normalized, without silently altering meaning.
- [ ] Both shape **and** value range are validated before parsing.
- [ ] Every record yields either a success result or an error with clear location/reason.
- [ ] Bad records are not silently dropped if the process requires traceability.
- [ ] Policies exist for duplicate keys and dataset-level rules.
- [ ] No shared mutable state is used inside parallel lambdas.
- [ ] Empty batches, `null` fields, boundary values, number/date errors, and large batches are tested.
- [ ] Monetary reports use appropriate numeric types and rounding rules.
- [ ] Policies protect sensitive data in error messages and logs.
- [ ] If the source is I/O-based, the stream is properly closed via its lifecycle.
- [ ] Performance optimizations are benchmarked without breaking processing semantics.

**Key takeaway:** For real-world data, a `map`–`filter`–`collect` pipeline is just a tool; what determines quality is **your normalization contract, validation checks, and ability to explain every rejected record**. Separate data cleaning from business rules, use accurate numeric and date types, preserve error outcomes instead of erasing trails, and only then optimize or parallelize. A "clean" dataset must be **trustworthy and reconcilable**, not merely whatever happened to survive a `filter`.
