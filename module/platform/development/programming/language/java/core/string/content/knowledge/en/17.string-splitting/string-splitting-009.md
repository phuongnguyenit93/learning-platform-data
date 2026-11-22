# Why simple `String.split()` is not enough to parse quoted CSV

## 1. The core problem

CSV (Comma-Separated Values) typically uses commas to separate fields, but **a comma is not always a delimiter**. A field enclosed in double quotes (`"..."`) can contain commas, newlines, and double quotes escaped as two consecutive double quotes (`""`). Therefore, you cannot treat every comma in a string as a field boundary.

For example, the record:

~~~csv
101,"Nguyễn, An","Nói ""xin chào""",active
~~~

has exactly **4 fields**, namely:

1. `101`
2. `Nguyễn, An`
3. `Nói "xin chào"`
4. `active`

If you use `line.split(",")`, Java also splits on the comma **inside** `"Nguyễn, An"`, producing the wrong field count and misaligned data. `split` only finds positions matching a regular expression; it does not track the context of "inside or outside quotes".

CSV is not a single format with one variant: RFC 4180 describes one common convention, whereas real-world data may use semicolons, different whitespace rules, or different escaping. When processing CSV, you need to know the **dialect** (formatting convention) of the data source.

## 2. Situations where `split` gets it wrong

| Input CSV line | Fields expected | Problem when splitting on comma |
| --- | --- | --- |
| `a,b,c` | `a`, `b`, `c` | Simple case: `split` works |
| `1,"Lan, An",3` | `1`, `Lan, An`, `3` | Comma inside quoted field is wrongly split |
| `1,"a""b",3` | `1`, `a"b`, `3` | `split` does not unescape `""` into `"` |
| `a,b,` | `a`, `b`, empty field | `split(",")` drops trailing empty fields by default |
| `"Dòng 1\nDòng 2",ok` | First field contains a real newline character; next field is `ok` | Reading one physical line at a time can split a single record in half |

In the last row of the table, `\n` is used to **represent** a newline character inside quotes; an actual CSV file may contain the next physical line right in the middle of this field.

### How do `split(",")` and `split(",", -1)` differ?

In Java, `String.split(regex)` is equivalent to `String.split(regex, 0)`: empty fields at the **end** of the result are discarded. Using `limit = -1` keeps them, but it **does not** solve commas inside quotes or unescaping double quotes.

~~~java
import java.util.Arrays;

public class SplitLimitDemo {
    public static void main(String[] args) {
        System.out.println(Arrays.toString("a,b,".split(",")));
        System.out.println(Arrays.toString("a,b,".split(",", -1)));

        String csv = "1,\"Lan, An\",3";
        String[] wrong = csv.split(",", -1);
        System.out.println(wrong.length);
        System.out.println(wrong[1]);
        System.out.println(wrong[2]);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 SplitLimitDemo.java
java SplitLimitDemo
~~~

Exact output:

~~~text
[a, b]
[a, b, ]
4
"Lan
 An"
~~~

Preserving trailing empty fields is part of CSV handling, yet using `-1` still produces **4 pieces** instead of **3 fields** for `1,"Lan, An",3`. Also remember that the first argument to `split` is a **regex**, not a literal delimiter string; even using `Pattern.quote(delimiter)` properly does not make it understand CSV quoting rules.

## 3. Rules for recognizing a CSV field

For the common variant using commas and double quotes:

- **Outside quotes:** a comma ends the field; a newline ends the record.
- **Inside quotes:** commas and newlines are **data** belonging to the same field.
- **Two consecutive quotes** `""` inside a quoted field represent **one** `"` character in the value.
- **After a closing quote:** under a strict parser, the only valid next characters are a comma, a record terminator, or end-of-input. Input such as `"abc"x` is invalid.
- **Empty fields:** `a,,b` has an empty second field; `a,b,` has an empty trailing field; `""` is a quoted field whose value is empty.
- **Record terminators:** `\r\n` is common in RFC 4180-style CSV; some sources use `\n` or `\r`. The parser must distinguish newlines outside quotes from newlines inside quotes.

A valid parser must **maintain state** character by character or use a library that implements those rules; you cannot decide based on the comma character alone.

You can picture four states:

| State | Meaning | Main handling |
| --- | --- | --- |
| `START` | Start of field, no content yet | `"` opens a quoted field; a comma creates an empty field |
| `UNQUOTED` | Reading an unquoted field | A comma or end-of-record ends the field; `"` mid-field is an error under strict rules |
| `QUOTED` | Reading a quoted field | Accepts commas, `\r`, and `\n` as data; `""` appends one `"` |
| `AFTER_QUOTE` | Closing quote has been read | Only allows a comma, end-of-record, or EOF |

## 4. Java 17+ example: correctly parsing quotes, newlines, and empty fields

The example below is a **complete program** using a state scanner for a specific CSV variant: `,` delimiter, `"` quote character, `""` quote escaping, `CRLF`/`LF`/`CR` allowed as record boundaries, and no whitespace allowed after a closing quote. The goal is to show the mechanism clearly; for large files or untrusted data, use a well-tested CSV library.

Save as `CsvExample.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class CsvExample {
    private enum State { START, UNQUOTED, QUOTED, AFTER_QUOTE }

    public static List<List<String>> parse(String input) {
        List<List<String>> records = new ArrayList<>();
        List<String> record = new ArrayList<>();
        StringBuilder field = new StringBuilder();
        State state = State.START;
        boolean lastWasRecordSeparator = false;

        for (int i = 0; i < input.length(); i++) {
            char ch = input.charAt(i);

            if (state == State.QUOTED) {
                if (ch == '"') {
                    if (i + 1 < input.length()
                            && input.charAt(i + 1) == '"') {
                        field.append('"');
                        i++; // Two quotes in CSV produce one quote.
                    } else {
                        state = State.AFTER_QUOTE;
                    }
                } else {
                    field.append(ch); // Includes commas and newlines.
                }
                lastWasRecordSeparator = false;
                continue;
            }

            if (ch == ',') {
                record.add(field.toString());
                field.setLength(0);
                state = State.START;
                lastWasRecordSeparator = false;
            } else if (ch == '\r' || ch == '\n') {
                record.add(field.toString());
                records.add(record);
                record = new ArrayList<>();
                field.setLength(0);
                state = State.START;
                lastWasRecordSeparator = true;

                // Outside quotes, CRLF ends only one record.
                if (ch == '\r' && i + 1 < input.length()
                        && input.charAt(i + 1) == '\n') {
                    i++;
                }
            } else if (state == State.AFTER_QUOTE) {
                throw new IllegalArgumentException(
                        "Character after closing quote at position " + i);
            } else if (state == State.START && ch == '"') {
                state = State.QUOTED;
                lastWasRecordSeparator = false;
            } else if (ch == '"') {
                throw new IllegalArgumentException(
                        "Invalid quote at position " + i);
            } else {
                field.append(ch);
                state = State.UNQUOTED;
                lastWasRecordSeparator = false;
            }
        }

        if (state == State.QUOTED) {
            throw new IllegalArgumentException("Missing closing quote");
        }

        // Do not create a spurious record after a file-ending newline.
        // Still keep the final empty field if the file ends with ','.
        if (!input.isEmpty() && !lastWasRecordSeparator) {
            record.add(field.toString());
            records.add(record);
        }

        return records;
    }

    public static void main(String[] args) {
        String csv =
                "id,name,quote,note\r\n" +
                "1,\"Nguyễn, An\",\"Nói \"\"xin chào\"\"\","
                        + "\"Dòng 1\nDòng 2\"\r\n" +
                "2,Bình,,\r\n";

        List<List<String>> rows = parse(csv);
        System.out.println(rows.size());
        System.out.println(rows.get(1).get(1));
        System.out.println(rows.get(1).get(2));
        System.out.println(
                rows.get(1).get(3).replace("\n", "\\n"));
        System.out.println(rows.get(2).size());
        System.out.println(rows.get(2).get(3).isEmpty());
    }
}
~~~

Compile and run (terminal with JDK 17 or later):

~~~bash
javac -encoding UTF-8 CsvExample.java
java CsvExample
~~~

`stdout`:

~~~text
3
Nguyễn, An
Nói "xin chào"
Dòng 1\nDòng 2
4
true
~~~

Explanation:

1. There are **3 logical records**: one header and two data records. The `note` field of the first record contains a real `\n` without creating an extra record.
2. The `name` field keeps its comma intact: `Nguyễn, An`.
3. CSV's two double quotes `""` are unescaped into a single quote in `Nói "xin chào"`.
4. The second record still has **4 fields**, including the two trailing empty fields.

The parser above is intentionally **strict**: it reports errors for unclosed quotes, quotes appearing inside an unquoted field, or invalid characters immediately after a closing quote. It reads the entire `String` into memory, does not flag inconsistent column counts, does not handle BOMs, and does not allow customizing the delimiter or escape style; those are explicit limitations of a **teaching example for the mechanism**, not a general production CSV parser.

## 5. Why reading line-by-line then calling `split` is also wrong

A **logical CSV record** can span multiple **physical lines**:

~~~csv
id,comment,status
1,"Starts here
and continues on the next line",done
2,"Single line",pending
~~~

There are only three records here (including the header). If you call `BufferedReader.readLine()` and parse each line as an independent record, the `comment` value for id `1` gets cut in half. `readLine()` strips line terminators, so it also risks losing the original newline characters of multi-line fields.

To process large streams, a parser must read from a `Reader` and track quote state **across reads and physical lines**. When using a library, prefer an API that reads one logical CSV record at a time. The "accumulate lines until an even number of quotes is counted" trick also breaks easily if `""` escaping and malformed inputs are not handled properly.

## 6. When is `split` enough and when should you use a library?

`split` is suitable if **the input is guaranteed** to be simple delimited text that never contains delimiters in values, does not use CSV quoting/escaping syntax, has no multi-line records, and has a well-defined empty-field policy. That is an assumption about the **input format**, which cannot be inferred merely from a `.csv` file extension.

For user-uploaded CSVs, CSVs exported from Excel or other systems, files with free-form fields such as names/addresses/descriptions, or data requiring high reliability, use a dedicated library such as **Apache Commons CSV** or **uniVocity Parsers**. Explicitly configure the delimiter, quote character, escape character, record separator, header handling, and error policy for the data source; do not assume all CSV files are identical.

When integrating CSV into a real application, also consider:

- **Encoding and BOM:** decode with the right charset (usually UTF-8); if a BOM is present at the start of the file, decide how to strip it before matching column names.
- **Headers and column counts:** check expected column counts, duplicate/missing header names, and records with unusual field counts; a syntactically valid parse does not guarantee business-valid data.
- **Empty vs. missing:** `,,`, `""`, and an absent field in a short record may carry different meanings; define how they map to Java objects.
- **Whitespace:** `" abc "` preserves spaces inside quotes; automatic `trim()` can alter data. Some dialects allow spaces after a closing quote, though the Java example above does not.
- **Malformed lines and size limits:** choose a policy to fail or skip bad records, and cap field lengths and file sizes to prevent excessive memory usage.
- **Exporting CSV:** when generating CSV to be opened in spreadsheet applications, values starting with `=`, `+`, `-`, or `@` may be interpreted as formulas. This is a security concern at **spreadsheet import/export time**, separate from parsing CSV correctly.

## 7. Self-check checklist

At a minimum, a CSV parser should be tested against these inputs:

| Input | Expected result |
| --- | --- |
| `a,b,c` | One record, 3 fields |
| `a,,c` | Middle field is empty |
| `a,b,` | Trailing empty field preserved |
| `"a,b",c` | First field is `a,b` |
| `"a""b",c` | First field is `a"b` |
| `"a\nb",c` (actual newline inside quotes) | One record; first field contains newline |
| `a,b\r\nc,d` | Two records with CRLF |
| `"abc` | Error for unclosed quote |
| `"abc"x,y` | Error for character after closing quote |
| `a"b,c` | Error for quote inside unquoted field |

**Conclusion:** `String.split(",")` sees commas; a CSV parser must understand **comma context** and **quote state**. `split(",", -1)` only fixes losing trailing empty fields on a line; it cannot replace parsing CSV with quotes, escapes, and multi-line records.