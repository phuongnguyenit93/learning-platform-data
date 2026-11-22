# Finding and Extracting Fields from Simply Structured Strings in Java

## 1. Goal and scope

Much real-world data has a lightweight structure yet is passed as a single `String`: `id=42;name=Lan;active=true`, `INFO|user_1|125ms`, `2026-10-23 | INFO | Started`, or `code:200;message:OK`. This lesson shows how to identify field boundaries, extract values, check for errors, and convert data into appropriate Java types while preserving the meaning of each field.

After this lesson, you will be able to:
- Choose between `indexOf`, `substring`, `split`, or `Pattern`/`Matcher` depending on input structure.
- Distinguish delimiters between **fields** from separators between **keys and values**; preserve valid delimiters located inside values.
- Detect missing required fields, duplicate keys, trailing/extra input, wrong types, and empty values.
- Build standalone runnable Java 17+ examples with verifiable output; design tests for both valid and invalid inputs.
- Recognize the limits of manual splitting: JSON, quoted CSV, URL queries, and arbitrary logs need specification-compliant parsers.

**Important scope:** examples use strings with an **explicit format contract**. Input data is text already decoded into a Java `String`. This lesson does not attempt automatic byte-encoding detection and does not build a general-purpose parser for every format.

## 2. Reading the structure before writing code

Consider the record:

```text
orderId=42;item=book;quantity=3;note=a=b
```

We define a simple contract:

| Component | Rule |
| --- | --- |
| Field delimiter | Semicolon `;` |
| Key/value separator | The **first** equals sign `=` in each field |
| Key | ASCII letters A–Z/a–z at the start; followed by letters, digits, or `_` |
| Value | Any string not containing `;`; may contain additional `=` |
| Whitespace | Stripped from both ends of key and value using `strip()` |
| Required fields | `orderId`, `item`, `quantity` |
| Optional field | `note` |
| Duplicate keys | Reject so values are not silently overwritten by mistake |
| Numeric values | `orderId` and `quantity` are positive integers |

Under that contract, `note=a=b` means **key `note` with value `a=b`**, not three equal parts. We must split fields on `;` and only search for the first `=` within each field.

Before writing a parser, answer five questions:
1. Which characters are structural delimiters? Are they allowed to appear inside values?
2. Do fields have a fixed positional order or are they identified by key name?
3. Which whitespace is meaningful? Is an empty value valid?
4. When a field is missing, duplicated, or has the wrong type, should an error be reported or a default value used?
5. Does the input have quoting/escaping/nesting? If so, simple `split` may not be enough.

A good parser turns those rules into explicit validation checks. If the source format has not been agreed upon yet, picking an algorithm first usually leads to wrong assumptions.

## 3. `indexOf` and `substring`: finding exact boundaries

`String.indexOf(char)` finds the first index of a character or returns `-1` if not found. `String.indexOf(String)` searches for a substring; overloads with `fromIndex` search starting from a given position. `lastIndexOf` finds the last occurrence. `substring(beginIndex, endIndex)` extracts `[beginIndex, endIndex)`, meaning inclusive of the start and exclusive of the end.

Standalone runnable Java 17+ example, save as `IndexExtractDemo.java`:

```java
public class IndexExtractDemo {
    public static void main(String[] args) {
        String input = "status=OK;detail=a=b";
        int delimiter = input.indexOf(';');
        if (delimiter < 0) {
            throw new IllegalArgumentException("Missing ;");
        }

        String left = input.substring(0, delimiter);
        String right = input.substring(delimiter + 1);

        int leftEquals = left.indexOf('=');
        int rightEquals = right.indexOf('=');
        if (leftEquals < 1 || rightEquals < 1) {
            throw new IllegalArgumentException("Field missing key or =");
        }

        String status = left.substring(leftEquals + 1);
        String detail = right.substring(rightEquals + 1);
        System.out.println("status=" + status);
        System.out.println("detail=" + detail);
    }
}
```

```bash
javac -encoding UTF-8 IndexExtractDemo.java
java IndexExtractDemo
```

```text
status=OK
detail=a=b
```

In the `detail=a=b` case, finding the **first** `=` and taking the right-hand side preserves `a=b`. If `lastIndexOf('=')` were used to separate key and value, the result would violate the contract.

**Check before slicing:** `indexOf` can return `-1`; never pass that index directly to `substring` or `charAt`. Exceptions like `StringIndexOutOfBoundsException` indicate boundary-handling bugs, not a desirable data validation policy.

Indices on `String` are measured in **UTF-16 code units**. `indexOf(String)` and `substring` are still valid on Unicode data, but you should not assume each `char` corresponds to one user-perceived character.

## 4. Using `split` when field boundaries are simple

`String.split(regex)` takes a **regex**; when an application-supplied delimiter is a literal character like `|` or `.`, use `Pattern.quote(delimiter)` to avoid misinterpreting special characters. If trailing empty fields must be preserved, choose `split(regex, -1)`, because `split(regex)` is equivalent to `split(regex, 0)` and discards trailing empty fields.

For a `key=value` pair, split only at the first `=` if the value content can contain additional `=`:

```java
String[] pair = "note=a=b".split("=", 2);
System.out.println(pair[0]); // note
System.out.println(pair[1]); // a=b
```

Verify `pair.length == 2`, a non-empty key, and the whitespace handling contract. In the parser in the next section, `indexOf('=')` makes the check clearer; `split(";", -1)` preserves the trailing empty field so a stray `;` can be caught. When you need to preserve every exact delimiter and reconstruct the original string, see the lesson **"Splitting Data with Empty Elements and Preserving Exact Delimiters"**, which explains `limit`, regex delimiters, and `Matcher` in full.

## 5. Comprehensive example: parsing `key=value` fields

The following example extracts fields, validates keys and data types, detects duplicate keys, preserves `=` inside values, and prints the results. Save as `SimpleRecordParser.java`:

```java
import java.util.LinkedHashMap;
import java.util.Map;

public class SimpleRecordParser {
    private static Map<String, String> parse(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException("Empty record");
        }

        Map<String, String> fields = new LinkedHashMap<>();

        for (String rawEntry : input.split(";", -1)) {
            String entry = rawEntry.strip();
            int equalsIndex = entry.indexOf('=');
            if (equalsIndex <= 0) {
                throw new IllegalArgumentException(
                        "Field missing key or =: " + entry);
            }

            String key = entry.substring(0, equalsIndex).strip();
            String value = entry.substring(equalsIndex + 1).strip();

            if (!key.matches("[A-Za-z][A-Za-z0-9_]*")) {
                throw new IllegalArgumentException("Invalid key: " + key);
            }
            if (fields.containsKey(key)) {
                throw new IllegalArgumentException("Duplicate key: " + key);
            }
            fields.put(key, value);
        }
        return fields;
    }

    private static String required(Map<String, String> fields, String key) {
        String value = fields.get(key);
        if (value == null || value.isEmpty()) {
            throw new IllegalArgumentException("Missing value: " + key);
        }
        return value;
    }

    private static int positiveInt(Map<String, String> fields, String key) {
        String raw = required(fields, key);
        final int value;
        try {
            value = Integer.parseInt(raw);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    key + " must be an integer", ex);
        }
        if (value <= 0) {
            throw new IllegalArgumentException(key + " must be > 0");
        }
        return value;
    }

    public static void main(String[] args) {
        String input = "orderId=42;item=book;quantity=3;note=a=b";
        Map<String, String> fields = parse(input);

        int orderId = positiveInt(fields, "orderId");
        String item = required(fields, "item");
        int quantity = positiveInt(fields, "quantity");
        String note = fields.getOrDefault("note", "");

        System.out.println("orderId=" + orderId);
        System.out.println("item=" + item);
        System.out.println("quantity=" + quantity);
        System.out.println("note=" + note);
        System.out.println("fieldCount=" + fields.size());
    }
}
```

```bash
javac -encoding UTF-8 SimpleRecordParser.java
java SimpleRecordParser
```

```text
orderId=42
item=book
quantity=3
note=a=b
fieldCount=4
```

### How it works

1. `split(";", -1)` keeps the trailing empty segment so an input like `a=1;` is not silently treated as valid: the empty trailing segment violates `equalsIndex <= 0`.
2. `indexOf('=')` picks only the first separator. Everything after it, including `=`, belongs to the value.
3. `strip()` removes Unicode whitespace at both ends per `Character.isWhitespace`; if leading/trailing whitespace is meaningful data, **do not strip values**.
4. The expression `[A-Za-z][A-Za-z0-9_]*` defines **ASCII keys** for this example's contract. It does not implicitly represent all valid Unicode identifiers.
5. `containsKey` catches duplicate keys. Calling `Map.put` directly would let a later field silently overwrite an earlier one.
6. `required(...)` distinguishes keys that must have content from optional keys. `positiveInt(...)` checks invalid number syntax, `int` range overflow, and non-positive numbers.
7. `LinkedHashMap` preserves insertion order when fields need to be reviewed in source order. If order is unnecessary, `HashMap` can be chosen; never rely on `HashMap` iteration order.

**Explicit limitations:** this parser does not forbid unknown keys outside `orderId`, `item`, `quantity`, and `note`; does not handle escaping for `;`; does not enforce string/value size limits; and only illustrates a small schema. Real applications should add limits per the data contract, a key allowlist if needed, length checks, safe logging policies, and corresponding error tests.

### Invalid input cases

| Input | Behavior of the parser above |
| --- | --- |
| `orderId=42;quantity=3;item=book` | Valid, optional `note` is empty |
| `orderId=42;item=book;quantity=3;` | Fails because there is a trailing empty field |
| `orderId=42;orderId=99;item=book;quantity=3` | Fails on duplicate key `orderId` |
| `=42;item=book;quantity=3` | Fails on field missing a key |
| `orderId=42;item=book;quantity=zero` | Fails when calling `positiveInt` for `quantity` |
| `orderId=42;item=book` | Fails on missing `quantity` value when required |
| `orderId=42;item=;quantity=3` | Fails when calling `required` for `item` |
| `orderId=42;item=book;quantity=3;note=a=b` | Valid, `note` preserves `a=b` |

Note: `parse(...)` splits and validates **field syntax**, while `required(...)`/`positiveInt(...)` validate **schema and types** after splitting. Separating these two responsibilities makes testing clearer and logic easier to reuse.

## 6. Extracting positional fields from a fixed-delimiter record

Not every structured string has keys. For example, a simple log is defined as **three fields** separated by ` | `:

```text
2026-10-23 | INFO | Started successfully
```

You can find the first two delimiters and slice each part. This preserves the delimiter ` | ` if it happens to appear inside the trailing message, because the message is the entire remainder.

Save as `FixedFieldsDemo.java`:

```java
public class FixedFieldsDemo {
    private static final String SEPARATOR = " | ";

    public static void main(String[] args) {
        String line = "2026-10-23 | INFO | Started | background task";

        int first = line.indexOf(SEPARATOR);
        int second = first < 0
                ? -1 : line.indexOf(SEPARATOR, first + SEPARATOR.length());

        if (first < 0 || second < 0) {
            throw new IllegalArgumentException("Missing log field");
        }

        String date = line.substring(0, first);
        String level = line.substring(
                first + SEPARATOR.length(), second);
        String message = line.substring(second + SEPARATOR.length());

        if (date.isBlank() || level.isBlank() || message.isBlank()) {
            throw new IllegalArgumentException("Required field is blank");
        }

        System.out.println("date=" + date);
        System.out.println("level=" + level);
        System.out.println("message=" + message);
    }
}
```

```bash
javac -encoding UTF-8 FixedFieldsDemo.java
java FixedFieldsDemo
```

```text
date=2026-10-23
level=INFO
message=Started | background task
```

This approach fits when **the first two fields are fixed and the final part is allowed to contain the delimiter**. Conversely, if the leading part may contain the delimiter and the trailing part has a fixed structure, you must define another boundary or search from the end with `lastIndexOf` per the contract.

`String.split(" \\| ", 3)` can also split into at most three parts, but `indexOf` makes the boundaries and missing-delimiter condition explicit. If date, level, or message have their own rules, validate them after extracting the fields, e.g., `LocalDate.parse(date)` for ISO dates or an allowed set of levels.

## 7. Using regex when matching a pattern and extracting multiple fields at once

When a structure has fixed text, numbers, optional spaces, or a valid value set, regex can both validate the entire string and extract groups. `Pattern` represents a compiled regex; `Matcher` is the matching engine for a given input string.

Example format contract: `LEVEL|userName|durationMs`, where:
- `LEVEL` is `INFO`, `WARN`, or `ERROR`.
- `userName` starts with an ASCII letter followed by letters, digits, or underscores.
- Duration is one or more decimal digits followed by `ms`.
- The whole line must match; arbitrary prefixes/suffixes are not accepted.

Save as `RegexFieldsDemo.java`:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class RegexFieldsDemo {
    private static final Pattern LINE = Pattern.compile(
            "(?<level>INFO|WARN|ERROR)\\|"
            + "(?<user>[A-Za-z][A-Za-z0-9_]*)\\|"
            + "(?<duration>\\d+)ms");

    public static void main(String[] args) {
        String input = "INFO|linh_2|125ms";
        Matcher matcher = LINE.matcher(input);

        if (!matcher.matches()) {
            throw new IllegalArgumentException("Invalid log line format");
        }

        String level = matcher.group("level");
        String user = matcher.group("user");
        int duration = Integer.parseInt(matcher.group("duration"));

        System.out.println("level=" + level);
        System.out.println("user=" + user);
        System.out.println("durationMs=" + duration);
    }
}
```

```bash
javac -encoding UTF-8 RegexFieldsDemo.java
java RegexFieldsDemo
```

```text
level=INFO
user=linh_2
durationMs=125
```

`\\|` in a Java string literal creates the regex `\|` to match a literal pipe character. `\\d+` creates the regex for one or more digits. `(?<level>...)` declares a **named capturing group**; `group("level")` extracts the corresponding part after `matches()` succeeds.

### Difference between `matches()` and `find()`

- `matcher.matches()` requires **the entire input string** to match the pattern. Use it when validating a complete record.
- `matcher.find()` searches for **a matching substring** starting from the current scan position. Suitable for extracting multiple occurrences in longer text; calling `find()` again continues scanning.
- `matcher.group(...)` is only valid after a successful match. Calling `group` before `matches()`/`find()` succeeds throws a `Matcher` state exception.

Example solely to illustrate `find()` syntax (snippet placed inside a Java method):

```java
Matcher m = Pattern.compile("id=(\\d+)").matcher("id=10; id=20");
while (m.find()) {
    System.out.println(m.group(1));
}
```

```text
10
20
```

For complex data or untrusted input, avoid regexes with nested greedy quantifiers that can cause heavy backtracking costs. `Pattern` is immutable and reusable; `Matcher` holds mutable state and should not be shared across threads.

## 8. Choosing `indexOf`, `split`, or regex?

| Input structure | Recommended choice | Example |
| --- | --- | --- |
| Get content after the first `=` | `indexOf` + `substring` | `message=a=b=c` |
| Split a few parts by a fixed delimiter | `split` with escaped regex; or `indexOf` | `red;green;blue` |
| Need to preserve trailing empty fields | `split(regex, -1)` | `A|B|` |
| Split into at most two parts | `split(regex, 2)` or `indexOf` | `key=value=extra` |
| Positional record where the tail contains the delimiter | Two `indexOf` calls or `split(regex, 3)` | `date | level | long message` |
| Pattern with names, numbers, simple enum set | `Pattern` + `Matcher.matches` | `INFO|user_1|23ms` |
| Scan multiple matches embedded in text | `Matcher.find` | `id=10; id=20` |
| CSV with quoted fields / JSON / URL query | Dedicated parser | `"Lan, Nguyễn",21`, JSON, or percent-encoded query |

No single method is right for all strings by default. Choose the simplest approach that fully satisfies the input contract, error conditions, and delimiters inside values.

## 9. Validating data after extraction

**Splitting a string does not mean the data is valid.** After extracting a value, validate it against the expected type:

- **Integers:** `Integer.parseInt(...)` throws `NumberFormatException` if the string is not a valid decimal integer or overflows `int`. If larger numbers are needed, consider `Long.parseLong` or `BigInteger`.
- **Booleans:** `Boolean.parseBoolean(...)` returns `true` only for strings case-insensitively equal to `"true"`; everything else, even typos like `"tru"`, returns `false`. If input must be valid `true/false`, validate **before** converting.
- **ISO dates:** `LocalDate.parse(...)` validates syntax and calendar validity and throws `DateTimeParseException` when invalid. Do not just check dates with `\d{4}-\d{2}-\d{2}` and assume the calendar date is valid.
- **Optional fields:** distinguish clearly between *absent key*, *key with empty value*, and *key with default value*. For instance, `Map.getOrDefault` only returns the default when the key does not exist; if the key exists with an empty value, the result is still an empty string.
- **Identifiers:** enforce character and length limits per business requirements; do not assume `trim` or `strip` replaces format validation.

Strict boolean example (standalone method snippet that can be placed inside a class):

```java
static boolean parseStrictBoolean(String raw) {
    if ("true".equalsIgnoreCase(raw)) {
        return true;
    }
    if ("false".equalsIgnoreCase(raw)) {
        return false;
    }
    throw new IllegalArgumentException("Invalid boolean value: " + raw);
}
```

Similarly, if `quantity` must be greater than 0, a successful `parseInt` is not enough: range validation is still required after conversion.

## 10. Common mistakes and how to avoid them

### 10.1. Confusing a literal delimiter with a regex

`"A|B|C".split("|")` does not split literally on the pipe character because `|` has special meaning in regex. Use `split("\\|")` or `split(Pattern.quote("|"))`.

Similarly, `split(".")` does not split on a literal dot; use `split("\\.")` or `Pattern.quote(".")`. This bug can silently produce unwanted elements or an empty array.

### 10.2. Using `split("=")` for values containing `=`

`note=a=b` must be split at the first `=`. Use `indexOf('=')` and `substring`, or `split("=", 2)`. If the format has complex escaping, neither simple approach may suffice.

### 10.3. Accessing array elements without checking

Code like `input.split(";")[1]` can throw `ArrayIndexOutOfBoundsException` when a delimiter is missing. Always verify field count and empty-field policy before indexing.

### 10.4. Dropping trailing empty fields

`"A;B;".split(";")` drops the trailing empty segment by default. If the data strictly has three columns and an empty third column is meaningful information, use `split(";", -1)`.

### 10.5. Reading values without checking keys

With `"name=Lan;role=admin"`, if the `role` field is required, do not assume "the second element" is definitely `role` unless fixed order is part of the contract. Data with reordered keys should still read accurately by key name when the source specifies a keyed structure.

### 10.6. Overwriting duplicate keys

`id=1;id=2` raises a question: take the first value, take the last value, or reject? Without an explicit policy, `Map.put` can mask malformed data. The comprehensive example chooses to reject duplicate keys.

### 10.7. Treating every comma-separated string as simple CSV

The CSV line `"Nguyen, Lan",21` has a comma **inside a quoted value**. `split(",")` splits it incorrectly; CSV also has quote escaping and newlines inside fields. Use a CSV library/parser conforming to the exact dialect instead of a quick regex.

### 10.8. Hand-rolling parsers for query strings or JSON

URL query strings can have percent-encoding, escaped `=`/`&` in data, duplicate keys, and encoding rules. JSON has string escapes, nested brackets, and data types. Use APIs or parsers built for those formats. This lesson applies to simple structures **controlled by the application**.

### 10.9. Not bounding input size

When given a huge string or millions of fields, `split` and regex can consume significant time and memory. Limit input length, field count, and value length per contract; log only necessary details and avoid leaking private data. For large streams, consider a streaming parser.

### 10.10. Extracting fields successfully while ignoring trailing junk

Regex with `find()` can match a valid segment inside an invalid line. When a record **must match in full**, use `matches()`, verify the exact field count, or check explicit termination conditions.

## 11. Designing tests for a simple parser

Test at least the following categories. A parser returning the right output on one clean example does not prove robustness.

| Category | Example input | What to verify |
| --- | --- | --- |
| Normal | `id=12;name=Lan` | Exact two fields and values |
| Reordered keys | `name=Lan;id=12` | Key-based lookup is order-independent |
| Empty entire string | `""` | Rejected or handled per contract |
| Missing pair separator | `id12` | Clear error reported with reason |
| Empty key | `=12` | Rejected |
| Empty value | `name=` | Handled differently from absent key per schema |
| Value containing `=` | `note=a=b` | Does not lose the `=b` segment |
| Trailing empty field | `id=12;` | Not silently ignored |
| Duplicate key | `id=12;id=13` | Detected according to policy |
| Wrong type | `quantity=three` | Conversion error handled |
| Out-of-range number | `quantity=99999999999999` | Does not silently overflow |
| Unicode characters | `name=Hà Nội` | Correct Unicode string and whitespace policy |
| Very long string | Many fields / long values | Resource limits enforced |
| Delimiter in data | `note=a;b` | Rejected under simple format or moved to escaped syntax |

Divide tests into three levels: **syntax splitting** tests, **schema/type validation** tests, and **application behavior** tests when a record is invalid. In particular, avoid swallowing exceptions by returning an empty string or `0` when that could be mistaken for real data.

## 12. Practice exercises

**Exercise 1 — key/value:** write `extractValue(String record, String wantedKey)` for the format `a=1;b=2;c=3`. Return `Optional<String>` or a value with a clear "not found" policy. Handle `note=a=b` and key `a` vs `aa` properly. Do not use a naive `contains("a=")` check because it can false-match.

**Exercise 2 — fixed record:** parse `"2026-10-23|WARN|Disk nearly full"` into date, level, and message. Find the first two delimiters, validate the date with `LocalDate.parse`, and ensure level belongs to an allowed set of values.

**Exercise 3 — numeric validation:** from `"user=linh;age=21;active=true"`, extract the fields and convert types. Reject `age=-3`, `age=abc`, and `active=maybe` when business rules require non-negative age and an explicit boolean.

**Exercise 4 — Regex:** write a `Pattern` to match the full string `"HTTP 200 /health"`, extracting the three-digit status code and the path starting with `/`. Compare `matches()` and `find()` behavior when invalid text is prepended to the line.

**Exercise 5 — limits of `split`:** test `"id=1;note=red;blue"`. Because `;` in the value is not escaped, a simple parser cannot tell accurately where the boundary is. Propose a **new data contract** (e.g., escaping, field length prefixing, or a standard format like JSON) and explain why a dedicated parser is required for that contract.

## 13. Key takeaways

Start with the **input contract**: what the delimiter is, whether values may contain delimiters, which fields are required, and when to report errors. For small fixed structures, `indexOf` and `substring` are clear. For uniformly delimited lists, `split` is convenient but remember regex rules and the `limit` parameter. For patterns with multiple conditions and capturing groups, `Pattern`/`Matcher` is helpful; `matches()` validates the whole record while `find()` scans substrings.

Always check indices before slicing, check field counts before accessing elements, avoid accidentally overwriting duplicate keys, and validate types after splitting. When data follows a complex specification such as CSV, URL query strings, or JSON, choose a spec-compliant parser instead of stretching a chain of `split` calls.