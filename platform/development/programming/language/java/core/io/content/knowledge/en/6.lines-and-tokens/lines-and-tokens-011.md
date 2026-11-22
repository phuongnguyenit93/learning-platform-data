# Limits of Line Splitting and `split()` When Reading Formats with Complex Escaping

When reading text data, two common operations are **splitting into lines** (`BufferedReader.readLine()`, `Files.lines()`) and **splitting into tokens** (`String.split(regex)`, `Scanner`). This works well for simple data: one line equals one record, delimiters never appear inside values, and there is no quoting or escaping.

For formats with complex escaping, both assumptions can break:

- A single logical record can **span multiple physical lines**, such as a quoted CSV field containing `\n`.
- A delimiter can appear as **actual data**, such as a comma inside `"Hà Nội, Việt Nam"` or `\|` in a `|`-delimited format.
- Quotes and backslashes can follow **custom escaping rules**; delimiter characters carry structural meaning only after accounting for parser state.
- Nested formats such as JSON require understanding brackets, strings, and escapes; splitting on `,`, `:`, or newlines is insufficient to understand structure.

**Main point:** Splitting a string solely by delimiter is a simple lexical operation. Whenever delimiters can be escaped, appear inside quoted strings, or sit inside nested structures, you need a **parser that understands the format's rules**. There is no universal `split()` formula that accurately parses every complex format.

## 1. Physical Lines, Logical Records, and Data Fields Differ

Suppose a CSV file contains:

```csv
id,note
1,"Thành phố Hồ Chí Minh, Việt Nam"
2,"Dòng thứ nhất
Dòng thứ hai"
3,"Anh ấy nói ""Xin chào"""
```

We must distinguish:

| Concept | Meaning | In the Example |
| --- | --- | --- |
| Physical line | Text separated by line terminators in the file | Record `id=2` spans **two** physical lines. |
| Logical record | One complete data unit per format syntax | This CSV has one header record and three data records. |
| Field | One value inside a record | `Thành phố Hồ Chí Minh, Việt Nam` is one field even though it contains a comma. |
| Delimiter | Character carrying structural meaning in valid context | Commas **outside** quotes separate fields; a comma **inside** quotes is data. |
| Escape | Syntax representing a special character without changing structure | CSV commonly uses `""` to represent a literal `"` character inside a quoted field. |

`BufferedReader.readLine()` returns one **physical line** and strips the line terminator; it **does not know** whether a newline sits inside a quoted CSV field. Likewise, `String.split(",")` does not know whether a comma sits inside quotes. Running both in sequence still does not create a CSV parser.

### Example 1 — Illustrating the Failure with a Java 17+ Program

```java
// NaiveSplitDemo.java
public class NaiveSplitDemo {
    public static void main(String[] args) {
        String csv =
                "id,note\n"
                + "1,\"Hello, world\"\n"
                + "2,\"Dòng thứ nhất\nDòng thứ hai\"\n";

        String[] physicalLines = csv.split("\\R");
        String[] wrongFields = "1,\"Hello, world\"".split(",", -1);

        System.out.println("physicalLines=" + physicalLines.length);
        System.out.println("naiveFields=" + wrongFields.length);
        System.out.println("logicalRecordsExpected=3");
        System.out.println("fieldsPerRecordExpected=2");
    }
}
```

Run:

```bash
javac -encoding UTF-8 NaiveSplitDemo.java
java NaiveSplitDemo
```

Output:

```text
physicalLines=4
naiveFields=3
logicalRecordsExpected=3
fieldsPerRecordExpected=2
```

The actual data has **three logical records**, yet `split("\\R")` yields four parts because the third record contains a newline inside quotes. The second line has **two fields**, yet `split(",")` yields three parts because of the comma inside `"Hello, world"`. `split()` behaves properly according to its regex rules; what is **wrong** is assuming comma/newline regexes capture full CSV syntax.

## 2. Specific Limitations of `String.split()`

`String.split(String regex)` takes a **regular expression**, not a plain literal delimiter string. Results depend on regex matches and the `limit` parameter, rather than inferring input quoting or escaping.

### 2.1. Delimiters Containing Special Regex Characters

Characters such as `.`, `|`, `*`, `+`, `?`, `[`, `]`, `(`, and `)` carry special meaning in regex. Thus:

```java
String[] parts = "a|b|c".split("|");  // Wrong intent: | is the regex alternation operator
```

This illustrates a bug in **delimiter-splitting intent**, not uncompilable Java syntax. To split on literal `|`, use `"\\|"` or `Pattern.quote("|")`.

### 2.2. Dropping Trailing Empty Fields by Default

`split(regex)` is equivalent to `split(regex, 0)`: it discards empty strings **at the end of the result**. When trailing empty columns matter, specify a negative `limit`:

```java
// SplitSemanticsDemo.java
import java.util.Arrays;
import java.util.regex.Pattern;

public class SplitSemanticsDemo {
    public static void main(String[] args) {
        String line = "one|two||";

        System.out.println(Arrays.toString(line.split("\\|")));
        System.out.println(Arrays.toString(line.split("\\|", -1)));
        System.out.println(line.split(Pattern.quote("|"), -1).length);
    }
}
```

```bash
javac SplitSemanticsDemo.java
java SplitSemanticsDemo
```

Output:

```text
[one, two]
[one, two, , ]
4
```

`Pattern.quote()` escapes a delimiter for **regex**, yet does not solve escaping/quoting **inside the data**. For instance, `one\|two|three` still cannot be split properly under the rule "`\|` is a literal `|` inside content" using only `split("\\|")`.

### 2.3. Regex Can Fit Simple Formats, but Does Not Understand Grammars

Regex is useful when rules are unambiguous, there is no nesting, and delimiters definitely cannot appear inside fields; for example, splitting consecutive spaces via `split("\\s+")`. Regex can express intricate conditions, yet a simple split regex:

- Cannot track whether a CSV field is currently inside or outside quotes across multiple lines.
- Cannot verify escape counts, quote doubling, or where records end.
- Cannot reliably detect all syntax errors such as unclosed quotes or invalid escapes.
- Cannot fully parse JSON/XML/YAML structures with their own rules for strings, nesting, and character representations.

A carefully crafted regex may handle a **subset** of a format; clear validation rules and tests are required. Do not treat a few-character `split()` pattern as a general-purpose CSV/JSON parser.

## 3. Escaping Is Not Just "Having a Preceding `\`"

The word "escape" does not have a single universal meaning across all formats:

| Format / Convention | Sample Data | Rule to Understand |
| --- | --- | --- |
| Double-quote escaped CSV | `"He said ""Hi"""` | Two `""` inside a quoted field represent one literal `"` character. |
| Backslash-style string | `a\|b|c` | Assuming `\|` represents content `|`; only an unescaped `|` separates fields. |
| JSON | `{"message":"a,\"b\""}` | In real JSON text, `\"` sits inside the string; commas inside strings do not split properties. |
| JSON with Unicode escapes | `"\u0041"` | A JSON parser must process escapes per JSON grammar; never use `split()` to decode manually. |
| URL-encoded form | `name=An%20Nguyen` | `%20` follows percent-encoding rules; split/decode order matters greatly. |
| Logs with quotes or metadata | `"GET /a,b HTTP/1.1" 200` | Splitting on spaces breaks the quoted request apart. |

**JSON examples in the table use illustrative syntax**, not Java string literals. When writing such strings directly in Java source code, account for **two layers of escaping**: Java string literals and the data format stored inside the Java string. For instance, Java `"\\n"` holds two characters backslash + `n` at runtime, whereas Java `"\n"` is an actual newline character. Confusing these two layers breaks parser tests right at the input data.

### 3.1. Consecutive Backslashes Can Change Meaning

In a grammar using backslashes for escaping, you must know exactly **which backslash escapes which character**. For example, if a convention lets `\|` be a literal `|` and `\\` be a literal backslash:

- Input `a\|b|c` must yield two tokens: `a|b` and `c`.
- Input `a\\|b` has one literal backslash followed by a real delimiter, so it yields `a\` and `b`.

A naive rule like "ignore any `|` immediately preceded by a backslash" fails when two or more consecutive backslashes appear. Calling `replace("\\|", "|")` **before splitting** also destroys knowledge of which delimiter was originally escaped. The safe approach is a sequential parser maintaining escape state, or a library that understands the exact grammar.

### Example 2 — Small Parser for a Custom Format Supporting `\|` and `\\`

This is an **illustrative format we define**, not CSV: the delimiter is `|`; the only two valid escapes are `\|` and `\\`; any other escape must raise an error. It demonstrates why each character must be examined in context.

```java
// BackslashDelimitedDemo.java
import java.util.ArrayList;
import java.util.List;

public class BackslashDelimitedDemo {
    static List<String> parse(String input) {
        List<String> fields = new ArrayList<>();
        StringBuilder field = new StringBuilder();
        boolean escaped = false;

        for (int i = 0; i < input.length(); i++) {
            char c = input.charAt(i);

            if (escaped) {
                if (c != '|' && c != '\\') {
                    throw new IllegalArgumentException(
                            "Unsupported escape: \\" + c);
                }
                field.append(c);
                escaped = false;
            } else if (c == '\\') {
                escaped = true;
            } else if (c == '|') {
                fields.add(field.toString());
                field.setLength(0);
            } else {
                field.append(c);
            }
        }

        if (escaped) {
            throw new IllegalArgumentException("Trailing backslash");
        }

        fields.add(field.toString());
        return fields;
    }

    public static void main(String[] args) {
        List<String> fields = parse("alpha\\|beta|gamma\\\\delta||");
        System.out.println("count=" + fields.size());
        System.out.println("first=" + fields.get(0));
        System.out.println("second=" + fields.get(1));
        System.out.println("emptyThird=" + fields.get(2).isEmpty());
        System.out.println("emptyFourth=" + fields.get(3).isEmpty());
    }
}
```

```bash
javac BackslashDelimitedDemo.java
java BackslashDelimitedDemo
```

Output:

```text
count=4
first=alpha|beta
second=gamma\delta
emptyThird=true
emptyFourth=true
```

The parser maintains an `escaped` flag; upon hitting a backslash, the next character is treated as data under the two permitted escapes. It also preserves trailing empty fields and throws an error if input ends mid-escape. This is still only a **tiny single-layer grammar**: to support Unicode escapes, quotes, nesting, size limits, error line/column numbers, etc., extend the parser intentionally rather than silently accepting out-of-contract syntax.

## 4. CSV: Quotes Determine Whether Commas and Newlines Are Delimiters

In CSV using `"` for quoted fields and `""` to escape quotes:

1. Outside quoted fields, commas separate fields; CR/LF or CRLF ends a record.
2. Inside quoted fields, commas and newlines are **field data**.
3. `""` inside a quoted field represents a single `"` character in the value.
4. Valid opening/closing quotes depend on position; a misplaced quote is a syntax error.
5. A record ends at a newline only when the parser is **not inside a quoted field**.

This rule explains why `BufferedReader.readLine()` is a physical-line reader that **cannot determine CSV record boundaries on its own**. A parser must retain state across newlines.

### 4.1. State Machine Model

A strict CSV parser can use four states:

| State | Meaning | Typical Transitions |
| --- | --- | --- |
| `START` | At the beginning of a field | `"` → `QUOTED`; ordinary char → `PLAIN`; `,` → ends empty field. |
| `PLAIN` | Inside an unquoted field | `,` → ends field; newline → ends record; `"` → error. |
| `QUOTED` | Inside a quoted field | Delimiter/newline becomes data; `""` appends one quote; closing quote → `AFTER_QUOTE`. |
| `AFTER_QUOTE` | Just closed a quoted field | Accepts only comma, newline, or EOF; other chars → error in strict mode. |

The parser can read from a `Reader` character by character. `PushbackReader` lets it peek one character ahead upon seeing `"` without losing the next character.

### Example 3 — Illustrative CSV Parser Supporting Quoted Newlines and `""`

The example below supports a **well-defined CSV subset**: delimiter `,`, quote `"`, quote escape `""`, unquoted newlines end records, CRLF counts as a single record terminator, and newlines inside quotes are preserved. The parser **does not** strip whitespace around quotes and does not support other CSV dialects; its goal is to illustrate the state machine.

```java
// QuotedCsvDemo.java
import java.io.IOException;
import java.io.PushbackReader;
import java.io.Reader;
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;

public class QuotedCsvDemo {
    enum State { START, PLAIN, QUOTED, AFTER_QUOTE }

    static List<List<String>> parse(Reader source) throws IOException {
        PushbackReader input = new PushbackReader(source, 1);
        List<List<String>> records = new ArrayList<>();
        List<String> record = new ArrayList<>();
        StringBuilder field = new StringBuilder();
        State state = State.START;
        boolean recordStarted = false;
        int value;

        while ((value = input.read()) != -1) {
            char c = (char) value;

            if (state == State.QUOTED) {
                if (c == '"') {
                    int next = input.read();
                    if (next == '"') {
                        field.append('"');
                    } else {
                        state = State.AFTER_QUOTE;
                        if (next != -1) {
                            input.unread(next);
                        }
                    }
                } else {
                    field.append(c);
                }
                continue;
            }

            if (state == State.AFTER_QUOTE
                    && c != ',' && c != '\r' && c != '\n') {
                throw new IOException("Unexpected char after closing quote");
            }

            if (c == ',') {
                record.add(field.toString());
                field.setLength(0);
                state = State.START;
                recordStarted = true;
            } else if (c == '\r' || c == '\n') {
                if (c == '\r') {
                    int next = input.read();
                    if (next != '\n' && next != -1) {
                        input.unread(next);
                    }
                }

                record.add(field.toString());
                records.add(record);
                record = new ArrayList<>();
                field.setLength(0);
                state = State.START;
                recordStarted = false;
            } else if (c == '"' && state == State.START) {
                state = State.QUOTED;
                recordStarted = true;
            } else if (c == '"') {
                throw new IOException("Quote inside unquoted field");
            } else {
                field.append(c);
                state = State.PLAIN;
                recordStarted = true;
            }
        }

        if (state == State.QUOTED) {
            throw new IOException("Unterminated quoted field");
        }

        if (recordStarted || !record.isEmpty()) {
            record.add(field.toString());
            records.add(record);
        }

        return records;
    }

    public static void main(String[] args) throws Exception {
        String csv =
                "id,note\n"
                + "1,\"Hello, world\"\n"
                + "2,\"line one\nline two\"\n"
                + "3,\"He said \"\"Hi\"\"\"\n";

        try (Reader source = new StringReader(csv)) {
            List<List<String>> records = parse(source);
            System.out.println("records=" + records.size());

            for (List<String> row : records) {
                System.out.println(row.get(0) + " | "
                        + row.get(1).replace("\n", "\\n"));
            }
        }
    }
}
```

```bash
javac QuotedCsvDemo.java
java QuotedCsvDemo
```

Output:

```text
records=4
id | note
1 | Hello, world
2 | line one\nline two
3 | He said "Hi"
```

In the third record, the literal `\n` sits **inside the quoted field**, is preserved in the field, and is only converted to the two visible characters `\` + `n` at `println` time for readable output. The result has four records (one header, three data), even though the raw text spans five physical lines.

This illustrative parser does not call `input.close()` inside `parse` because the `Reader` is **passed in by the caller**; the caller retains closing ownership via `try-with-resources`. `PushbackReader` is local to the method and not retained; when the caller closes the source, the underlying resource is released. This clarifies resource-ownership boundaries when moving from line-by-line processing to a sequential parser.

**Limitations of this example:** it keeps newlines inside quotes verbatim (including `\r\n` if present), has no backslash-escape option, disallows whitespace after a closing quote, does not enforce a fixed column count, and lacks size limits or line/column error reporting. A production CSV parser must also decide these dialects and requirements. When the format is real-world CSV from diverse sources, a dedicated CSV library is usually safer and easier to maintain than hand-rolling one.

## 5. Beyond CSV: JSON, XML, Logs, and Nested Data

### JSON

In JSON, commas separate array elements/object properties **only at the appropriate structural nesting level**. Commas inside strings or nested objects/arrays do not carry the same role.

JSON example:

```json
{
  "name": "Lan, An",
  "tags": ["java", "io"],
  "meta": {"message": "Có dấu phẩy, và escape \""}
}
```

Strings contain `\"` (a quote escaped per JSON syntax), arrays/objects nest, and values may contain Unicode escapes. Blindly running `text.split(",")`, `text.split(":")`, or `replace("\\\"", "\"")` breaks structure or corrupts values. Use a **JSON parser** (such as Jackson or an appropriate JSON API in your project) to parse into a tree or stream tokens. Never use `String.split()` to fake a JSON parser.

For **JSON Lines/NDJSON**, the contract typically mandates that *each physical line contains exactly one complete JSON value*; under that contract, reading line by line and passing each line to a **JSON parser** is reasonable. Yet that is a guarantee of the NDJSON format, not proof that arbitrary JSON can be split on newlines.

### XML/HTML

`>` can appear inside quoted attribute values; entities such as `&amp;` and CDATA sections have specialized semantics. `split("<")` / `split(">")` does not understand the DOM, namespaces, or encodings. For XML, use an appropriate XML parser (`SAX`, `StAX`, or `DOM`); especially with untrusted input, configure the parser to guard against external entities and resource exhaustion.

### Logs with Quotes

A log formatted like:

```text
127.0.0.1 "GET /search?q=a,b HTTP/1.1" 200
```

Using `split(" ")` splits the request into fragmented tokens. If the format specifies quoted strings and escapes, parse according to the exact quote grammar, or use an appropriate log parser. Do not apply CSV rules to logs merely because both use quotation marks.

### URL/Form Encoding

Characters `%2C`, `%26`, or `%3D` are percent-encoded, not backslash/CSV syntax. The order of splitting **key/value pairs** and decoding changes meaning whenever `&` or `=` appears inside encoded data. Use a standardized URL/form parser rather than `split("&")` with ad-hoc decoding on arbitrary input.

## 6. Which Tool Should You Use in Java?

| Data Shape | Appropriate Approach | When Is `split()` Sufficient? |
| --- | --- | --- |
| Every line truly is one record and delimiters cannot appear in fields | `BufferedReader.readLine()` then `split(Pattern.quote(delimiter), -1)` | Yes, if splitting rules are genuinely simple. |
| CSV files with quoted fields, embedded commas, or embedded newlines | Dialect-aware CSV parser; e.g., Apache Commons CSV or equivalent | Only for a tightly controlled CSV subset without quoting/escaping. |
| TSV with escapes, quotes, or multiline values | Parser matching the actual TSV spec; TSV has no single universal escape grammar | Only when delimiters and newlines are guaranteed absent from data. |
| JSON / NDJSON | JSON parser (e.g., Jackson). For NDJSON, read line by line then parse each value. | Never use split to parse JSON structure. |
| XML | Properly configured SAX/StAX/DOM | Never use split to parse XML. |
| Length-prefixed binary/record protocols | Read byte/char counts per framing, then parse payload | Do not rely on newlines as boundaries unless specified by the protocol. |
| Custom format with `\` escapes | Small stateful parser with contract and tests | Only for unescaped delimiters; once escapes exist, state is required. |

`Scanner` also relies on regex delimiters for splitting operations. `Scanner.useDelimiter(...)` changes the delimiter, yet **does not turn `Scanner` into a CSV or JSON parser**. `Files.lines()` supplies a stream of **physical lines**, not automatically assembled multiline CSV records. When streaming parsing is required, structure a parser that reads incrementally from `Reader`/`InputStream` and emits logical records at proper boundaries.

There is no built-in CSV library in Java SE covering every dialect; when picking an external dependency, align on version/dialect, charset, quotes, escaping, headers, whitespace, empty-line handling, and data errors per project requirements.

## 7. Syntactic Differences to Define Before Parsing

For formats with escaping, a parser needs an **explicit contract**, rather than guessing:

1. **Charset:** are input bytes UTF-8 or another encoding? Is a BOM allowed? How does the decoder handle malformed byte sequences?
2. **Record boundary:** do physical newlines always end records? Are `\n`, `\r\n`, or `\r` expected? Are newlines inside quoted fields preserved or normalized?
3. **Delimiter:** comma, tab, `|`, semicolon, or multi-character sequence? When is a delimiter structurally active?
4. **Quote:** which characters open/close quotes? Are quotes allowed inside unquoted fields? Is whitespace before/after quotes valid?
5. **Escape:** `""`, `\"`, `\\`, `%xx`, or another mechanism? Do malformed escapes raise an error or stay literal?
6. **Empty fields:** how many fields does `a,,` represent? Does an empty record have one empty field or get skipped? Do `""` and an unquoted empty field mean the same thing?
7. **Limits:** maximum bytes, characters, nesting depth, fields, and records? The parser must block oversized input from untrusted sources.
8. **Schema:** is the field count per record fixed? Is a header mandatory? Are numeric/date types validated after splitting fields?
9. **Errors:** where should unclosed quotes, trailing escapes at EOF, or extra chars after a closing quote be reported? Should a bad record be recovered and skipped or fail fast?
10. **Ownership:** will the caller or the parser close `Reader`/`InputStream`? Document this clearly so the parser does not unexpectedly close a shared stream.

Never unescape an entire string **before** determining structure: that step can turn data-literal delimiters into real delimiters. The right sequence depends on the format, yet generally involves **stateful structural parsing followed by field-content decoding** once the grammar is clear.

## 8. Handling Streaming, Errors, and Character Boundaries

A large-data parser usually needs incremental reading instead of loading the whole file with `Files.readString()`:

- **Preserve state across reads:** an opening quote at the end of one chunk may close only in the next chunk; likewise an escape `\` can land right on a buffer boundary.
- **Never assume one `Reader.read(buffer)` equals one record:** how many `char`s `read` returns depends on buffering; chunk boundaries do not determine logical boundaries.
- **Count the right units:** `Reader` yields UTF-16 code units; protocol payloads sometimes measure length in bytes, so decode and parse in the right order.
- **Track error locations:** line, column, record, and field numbers help pinpoint corrupt input. With quoted multiline fields, physical line numbers do not match record counts.
- **Enforce resource bounds:** bound quoted-field length, element counts/nesting depth, and network timeouts as needed. An unclosed quoted field can cause a parser to buffer data indefinitely.
- **Manage sources:** close the reader with `try-with-resources` at the owning layer and handle `IOException` properly. If a parser method receives a borrowed reader, do not close the source unless the contract specifies it.

### Testing to Avoid a Parser That Looks Right Yet Still Fails

For CSV, at minimum test: `a,b`, `a,,b`, `a,b,`, `"a,b",c`, `"a\nb",c`, `"He said ""Hi""",x`, empty files, `\r\n` endings, unclosed quotes, and extra chars after a closing quote. For backslash escaping, test escaped delimiters, single and double backslashes, trailing escape at EOF, invalid escapes, and consecutive delimiters. For JSON, test commas/colons inside strings, escaped quotes, nested arrays/objects, and truncated JSON missing closing brackets.

Do not check only **token counts**; verify exact **post-unescape values**, distinguish empty fields from empty records, and ensure malformed data produces errors instead of being silently misinterpreted.

## 9. Common Mistakes and Consequences

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Reading CSV with `readLine()` then `split(",")` | Breaks multiline records and fields containing commas | Use a CSV parser aware of quotes and record boundaries. |
| Assuming `split()` takes a literal delimiter | `|` or `.` gets interpreted as regex | Use `Pattern.quote(delimiter)` when grammar is simple. |
| Omitting `limit=-1` when trailing fields can be empty | Drops trailing empty fields | Use `split(regex, -1)` for split-appropriate data. |
| Unescaping before splitting | Escaped data delimiters turn into real delimiters | Parse structure first, then decode fields per grammar. |
| Peeking only one character before a delimiter | Fails on consecutive backslashes | Track escape state and character counts. |
| Writing custom regexes for general JSON/XML | Fails on quotes, nesting, entities, and escapes | Use a dedicated parser. |
| Treating each chunk from `Reader` as one line/record | Splits quotes, escapes, or Unicode mid-sequence | Maintain parser state across reads. |
| Silently accepting unclosed quotes | Corrupt data gets treated as valid | Report syntax errors with location where possible. |
| Leaving fields unbounded on external input | Can exhaust RAM/CPU | Enforce size, depth, record-count limits, and error policies. |

## 10. Self-Check

**Question 1.** Why can `readLine()` fail when extracting individual CSV records?

**Answer:** A quoted CSV field can contain newlines; one logical record can span multiple physical lines.

**Question 2.** Into how many parts does `split(",")` split `"a,b",c`, and how many fields does a proper CSV parser produce?

**Answer:** `split(",")` yields three parts because of the comma inside quotes; a proper CSV parser produces two fields: `a,b` and `c`.

**Question 3.** Does `"x|y||".split("\\|")` preserve the two trailing empty fields?

**Answer:** No; use `split("\\|", -1)` when trailing empty fields must be retained.

**Question 4.** Does `Pattern.quote("|")` make `String.split()` understand `a\|b|c` under backslash-escape rules?

**Answer:** No. It only escapes `|` **inside the regex**, without adding an escape grammar for the input content.

**Question 5.** Why do `\|` and `\\|` require tracking state rather than just inspecting the character right before `|`?

**Answer:** Under the example convention, `\|` represents a literal data delimiter; `\\|` represents a literal backslash followed by a real delimiter.

**Question 6.** What approach should you use to read JSON with nested objects and escaped quotes?

**Answer:** Use a JSON parser that understands structure and escaping. If input is valid NDJSON, you can read physical lines and then parse **each JSON value**.

**Question 7.** If reading from a `Reader` and an opening quote appears at the end of a buffer, may the parser end the record?

**Answer:** No; it must retain the quoted state into the next read and end the record only when the grammar allows.

**Principle to remember:** `readLine()` splits on physical newlines and `split()` splits by regex; **neither method automatically understands record boundaries, escaping, quotes, or nesting**. Use them for data with simple, controlled grammars; use a stateful parser or format-appropriate library when structure and escaping are complex.
