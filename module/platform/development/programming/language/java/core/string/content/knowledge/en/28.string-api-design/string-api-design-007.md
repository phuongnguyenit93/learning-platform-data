# Using Format-Specific Processors for JSON, CSV, Paths, or URIs

## 1. A String can contain many different data languages

In Java, the `String` type merely stores a sequence of characters. It **does not by itself tell you** whether that sequence is JSON, a CSV record, a file path, or a URI. Each format has **its own grammar and escaping rules**. If you use general-purpose string operations such as `split`, `substring`, `replace`, or regex in place of a format parser, the result will usually only work for simple inputs.

Consider four strings that appear easy to handle:

```text
{"message":"Lan said \"Hello\"","count":2}
"Lan, A.","First line
Second line"
reports/2026/../summary.csv
https://example.com/search?q=Java%20%26%20Spring#results
```

- JSON has quoted strings, escape characters, number types, `null`, arrays, and objects.
- CSV has delimiters **inside quoted fields**, double quotes escaped by two consecutive quotes, and a field can even contain a newline.
- Paths have segments, relative/absolute rules, file-system semantics, and `.`, `..` symbols.
- URIs have scheme, authority, path, query, fragment, percent-encoding, and reserved characters.

A good API must clearly state **which format the input belongs to**, use the appropriate processor to produce structured data types, and only then execute business logic. Do not turn everything into `String.split(...)` merely because every input starts out as a string.

## 2. API selection table by data type

| Data | Appropriate Java Tool | Expected Output | Avoid Doing |
| --- | --- | --- | --- |
| JSON | Jackson `ObjectMapper`, Gson, or a compatible JSON library | Object/record, JSON tree, or token stream | Manually splitting on commas, colons, or braces |
| CSV | Apache Commons CSV, OpenCSV, or a dialect-configured parser | Records and fields, including empty values | Blindly calling `split(",")` or `split("\n")` |
| File path | `java.nio.file.Path`, `Files` | Path segments, file access handle | Manually concatenating paths with `"/"` or `"\\"` |
| URI | `java.net.URI` and an appropriate URI builder | Scheme, host, path, query, fragment | Slicing strings based on `"://"`, `"/"`, `"?"`, `"&"` |
| Form query parameters | Context-appropriate URL/form encoder or URI builder | Properly encoded query values | Using `URLEncoder` for every URI component |

**Choosing a parser is part of the API contract**, not merely a matter of convenience. It helps handle complex valid data accurately, distinguish malformed inputs, and avoid double encoding or information loss.

## 3. JSON: parsers understand structure, data types, and escaping

### 3.1. Why splitting on commas or colons fails

Example:

```json
{
  "name": "Lan, A.",
  "address": {"city": "Hanoi"},
  "tags": ["Java", "Spring"],
  "enabled": true,
  "note": null
}
```

If you call `split(",")`, the comma inside `"Lan, A."` will be treated as a field separator, even though it is just **string content**. Commas between array elements are also not at the same level as commas between object properties. Likewise, `split(":")` cannot distinguish property colons from colons inside string values.

JSON also has escapes `\"`, `\\`, `\n`, `\uXXXX`; it distinguishes `42` (number) from `"42"` (string), `true` (boolean), `null`, and absent fields. Writing a chain of `replace` calls rarely covers all cases.

### 3.2. Parsing with Jackson

In applications with Jackson Databind on the classpath, JSON can be mapped to a Java type:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

record Product(String sku, int quantity) {}

ObjectMapper mapper = new ObjectMapper();
String json = """
        {"sku":"SKU-01","quantity":3}
        """;

Product product = mapper.readValue(json, Product.class);
System.out.println(product.sku());      // SKU-01
System.out.println(product.quantity()); // 3

String serialized = mapper.writeValueAsString(product);
System.out.println(serialized); // {"sku":"SKU-01","quantity":3}
```

**This is an illustrative snippet to place inside a Java class/method**, not a standalone file. You must declare the `com.fasterxml.jackson.core:jackson-databind` dependency at an appropriate project-managed version; Java 17 **does not bundle Jackson in the JDK**. Records require a Jackson version that supports Java records.

Jackson also supports `JsonNode` for flexible JSON traversal, or a streaming API for large inputs. When data has a fixed schema, converting to a record/class gives business logic clear types; when the structure is dynamic, a JSON tree is often more suitable.

Note: **successful deserialization does not replace business validation**. For example, `quantity` may need to be greater than 0; valid JSON syntax does not guarantee valid values. Jackson options for missing fields, unknown fields, and coercion must align with the API contract; do not rely on primitive default values and silently accept missing fields.

### 3.3. Generating JSON with a serializer, not by concatenating quotes

Manual string concatenation:

```java
String json = "{\"message\":\"" + userText + "\"}";
```

will break when `userText` contains double quotes, backslashes, or control characters. If the data source is untrusted, broken JSON assembly can also corrupt data or alter structure.

Instead, let the serializer handle escaping:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;

ObjectMapper mapper = new ObjectMapper();
String result = mapper.writeValueAsString(
        Map.of("message", "Lan said \"Hello\"")
);
// result is valid JSON with quotes inside the value properly escaped.
```

This is also an illustrative snippet requiring the Jackson dependency. When output must conform to a schema, combine the serializer with schema validation or domain checks before sending.

## 4. CSV: splitting records and fields according to the proper dialect

### 4.1. A comma is not always a delimiter

CSV is often briefly described as "comma-separated values", yet a field enclosed in double quotes can **contain commas, newlines, or quotes**. The following CSV example has one header line and one data line:

```csv
name,note
"Lan, A.","Said ""hello"""
```

The data record has **two fields**:

1. `Lan, A.`
2. `Said "hello"`

`split(",")` will split the first field incorrectly. Another example:

```csv
id,note
1,"First line
Second line"
```

The `note` field contains a newline, yet still belongs to **one CSV record**. Therefore, calling `split("\n")` to count lines and then `split(",")` to extract fields is not a general CSV reader.

Files with a `.csv` extension may also use semicolons `;`, tabs, custom escapes, encodings, and different header rules. You must determine the **dialect** (delimiter, quote, escape, header, record separator, empty-cell policy) from the data source.

### 4.2. Parsing with Apache Commons CSV

When the project includes the `org.apache.commons:commons-csv` dependency, you can use:

```java
import java.io.StringReader;
import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.apache.commons.csv.CSVRecord;

String input = """
        name,note
        "Lan, A.","Said ""hello"""
        """;

try (CSVParser parser =
             CSVFormat.RFC4180.parse(new StringReader(input))) {
    for (CSVRecord record : parser) {
        System.out.println(record.get(0) + " | " + record.get(1));
    }
}
```

This is an **illustrative snippet** placed inside a method that can handle `IOException`, and requires the Commons CSV library on the classpath. It reads the header line as the first record; if you want to access columns by **header name**, configure headers according to the API of the Commons CSV version in use.

Proper configuration depends on the CSV source: not every file conforms to RFC 4180, and you should not assume every `;` or tab in data is an error.

### 4.3. Writing CSV with a printer and preserving all fields

When exporting CSV, use the library's writer to quote and escape fields. Do not concatenate manually:

```java
String line = name + "," + note; // Can corrupt the CSV.
```

Dedicated CSV writers know when to add quotes and turn internal `"` characters into `""`. If the column count is fixed, validate the number of fields after parsing, including trailing empty fields.

For example, `A,B,` represents **three fields** in a literal-delimiter CSV model: `A`, `B`, and an empty final field. Calling `"A,B,".split(",")` in Java drops the trailing empty field; `split(",", -1)` preserves it for **extremely simple CSV**, yet still **does not handle** quoted fields, embedded commas, or newlines. `-1` does not turn `split` into a CSV parser.

When exporting CSV for spreadsheet applications, consider user data starting with `=`, `+`, `-`, or `@`: some software may interpret them as **formulas** upon opening the file. Syntactically quoted CSV does not automatically mean safe rendering in spreadsheets; apply an export policy tailored to the target application to mitigate formula execution risk.

## 5. Paths: use Path instead of string concatenation

### 5.1. A path is a file-system structure

In Java 17, `java.nio.file.Path` represents file paths according to the active **file-system provider**. It supports segments, resolving, normalizing, extracting file names, and operations via `Files`:

```java
import java.nio.file.Path;

Path root = Path.of("reports");
Path target = root.resolve(Path.of("2026", "summary.csv"));

System.out.println(target.getFileName()); // summary.csv
```

Avoid manual concatenation:

```java
String path = rootText + "/" + fileName;
```

because separators and drive/root representations depend on the platform; multiple `/`, `\\`, absolute paths, or `..` segments can also alter the path's meaning unexpectedly.

The same path can be written in multiple text forms. `Path.normalize()` removes `.` components and resolves `name/..` segment pairs **syntactically**, without accessing the file system.

### 5.2. Use resolve and normalize for the right purpose

```java
Path root = Path.of("documents").toAbsolutePath().normalize();
Path relative = Path.of("2026", "report.csv");
Path target = root.resolve(relative).normalize();

System.out.println(target.getFileName()); // report.csv
System.out.println(target.startsWith(root)); // true
```

If a user supplies `../secret.txt` and the application only permits files under `root`, check:

```java
Path attempt = root.resolve(Path.of("..", "secret.txt")).normalize();
boolean inside = attempt.startsWith(root);
System.out.println(inside); // false
```

`Path.startsWith(Path)` compares **path components**, unlike `String.startsWith`. For example, `/data/reports-other` is not inside root `/data/reports` even though the character strings share a prefix.

**Important security note:** checking `normalize()`/`startsWith(root)` is only a **syntactic path structure check**. It does not prevent a symlink inside root from pointing to an outside location, and does not by itself resolve race conditions between checking and opening the file. For strict access containment, design an appropriate filesystem workflow: verify the real path via `toRealPath` when the file exists, handle symlinks and permissions, and consider directory-handle/secure-directory-stream operations depending on the filesystem. Never treat a single text check as proof against "all path traversal".

### 5.3. File Path is not equivalent to URI

`Path.of("data", "report.csv")` is a relative file path. `URI.create("https://example.com/report.csv")` is an HTTPS URI. They have different syntaxes and access mechanisms.

`Path.of(uri)` is used for URIs targeting a supported file-system provider, commonly `file:`, **not to convert HTTP/HTTPS URLs into local paths**. If you need to fetch an HTTP resource, use an HTTP client (`java.net.http.HttpClient`) or suitable library, then save the result via `Files` under an application-controlled `Path`.

## 6. URI: parse components and encode by context

### 6.1. URIs have their own structure

Example:

```text
https://example.com/search?q=Java%20%26%20Spring#results
└scheme └authority┘ └path┘ └────query─────┘ └fragment
```

Each component has a distinct purpose:

| Component | Purpose |
| --- | --- |
| Scheme | `https`, `http`, `file`, etc. |
| Authority | May contain user info, host, and port. |
| Path | Resource segments. |
| Query | Portion after `?` per service syntax. |
| Fragment | Portion after `#`; normally not part of the request path sent to the server. |

Java provides `java.net.URI` to parse and work with URI syntax:

```java
import java.net.URI;

URI uri = URI.create(
        "https://example.com/search?q=Java%20%26%20Spring#results");

System.out.println(uri.getScheme());    // https
System.out.println(uri.getHost());      // example.com
System.out.println(uri.getPath());      // /search
System.out.println(uri.getRawQuery());  // q=Java%20%26%20Spring
System.out.println(uri.getFragment());  // results
```

`getRawQuery()` preserves percent-encoding; `getQuery()` returns query data decoded per `URI` rules. However, `URI` **does not automatically turn a query into a multi-parameter map according to application-specific conventions**.

### 6.2. Encoding a query value differs from encoding a path segment

In `?q=Java%20%26%20Spring`, `%26` represents the `&` character belonging to the **parameter value**, not a separator between two parameters. If you concatenate `?q=` with arbitrary unencoded text, an `&` in the data may be interpreted as query syntax.

For **query values encoded as application/x-www-form-urlencoded**, you can use:

```java
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

String queryValue = "Java & Spring";
String encoded = URLEncoder.encode(queryValue, StandardCharsets.UTF_8);
URI search = URI.create("https://example.com/search?q=" + encoded);

System.out.println(search.getRawQuery());
// q=Java+%26+Spring
```

Spaces are form-encoded as `+`, and `&` becomes `%26`. This encoding is appropriate for **form-style query parameter values**; do not use `URLEncoder` for an entire URL or an entire path. In a URI path, `+` can carry literal meaning, while `/` separates path segments. To construct URIs with arbitrary path segments and query params, use a reliable URI builder that encodes **each component for its proper context**.

If using `new URI(scheme, authority, path, query, fragment)`, you still must distinguish reserved characters that have meaning inside a component: the constructor encodes illegal characters but cannot guess whether `/` inside a path string is data belonging to **one segment** or a segment separator. Encoding according to **component semantics** remains the responsibility of the calling API.

### 6.3. URI.resolve: building relative paths, while checking the target

```java
URI base = URI.create("https://example.com/api/");
URI userEndpoint = base.resolve("users/42");

System.out.println(userEndpoint.getPath());
// /api/users/42
```

A trailing `/` on base affects how relative paths resolve. If base is `https://example.com/api` (without a trailing slash), `users/42` may replace the `api` segment instead of being appended beneath it.

**Do not call `base.resolve(userSuppliedUri)` and assume the target remains on the same host.** Input starting with `https://...` or `//other-host/...` can resolve to a different target URI. When constructing URLs for outbound requests, validate scheme, host, port, path, and access policies after resolution; when following redirects, re-check the new target as well. Successful `URI` parsing does not guarantee the URL is safe for network calls.

## 7. Standalone Java 17 example without external libraries

Create the file `StructuredFormatDemo.java`:

```java
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public class StructuredFormatDemo {
    public static void main(String[] args) {
        String userInput = "Java & Spring";
        String encoded =
                URLEncoder.encode(userInput, StandardCharsets.UTF_8);
        URI search = URI.create(
                "https://example.com/search?q=" + encoded);

        URI base = URI.create("https://example.com/api/");
        URI endpoint = base.resolve("users/42");

        Path root = Path.of("documents")
                .toAbsolutePath().normalize();
        Path safe = root.resolve(
                Path.of("2026", "report.csv")).normalize();
        Path escape = root.resolve(
                Path.of("..", "secret.txt")).normalize();

        System.out.println("query: " + search.getRawQuery());
        System.out.println("path: " + endpoint.getPath());
        System.out.println("file name: " + safe.getFileName());
        System.out.println("inside root: " + safe.startsWith(root));
        System.out.println("escape rejected: " +
                !escape.startsWith(root));
        System.out.println("uri absolute: " + search.isAbsolute());

        String tricky = "Lan,\"said \"\"hello\"\"\"";
        System.out.println("naive CSV parts: " +
                tricky.split(",").length);
    }
}
```

Compile and run:

```bash
javac StructuredFormatDemo.java
java StructuredFormatDemo
```

Output:

```text
query: q=Java+%26+Spring
path: /api/users/42
file name: report.csv
inside root: true
escape rejected: true
uri absolute: true
naive CSV parts: 2
```

The first lines confirm context-appropriate query value encoding and use of `URI.resolve` and `Path.resolve`/`normalize`. The last line intentionally shows that `split(",")` produces two pieces because it encounters a comma outside the quoted string; for valid CSV `Lan,"said ""hello"""`, the comma is the delimiter, yet the raw pieces left by `split` **have not had quotes/escapes unquoted** and are not true CSV field values. For a quoted field containing a comma like `"Lan, A.","hello"`, `split(",")` even produces **the wrong number of fields**.

The `escape rejected: true` example only demonstrates **syntactic** path checking; checking real paths on a file system still requires accounting for symlinks and access issues mentioned in section 5.

## 8. API design: accept meaningful data, return structured types

Minimize forcing business layers to guess the format of a generic string.

Instead of a vague API like:

```java
void process(String data);
```

design a clear pipeline, for example:

```text
HTTP body JSON --JSON parser--> OrderRequest --validation--> domain command
CSV upload ----CSV parser----> CSV records ---mapping-----> domain rows
Path input ----Path/Files-----> normalized/checkable file path
URI input -----URI parser-----> URI components -> validated outbound request
```

At system boundaries, separate into steps:

1. **Identify the format** from the contract, Content-Type, or trusted configuration—do not guess with `contains(",")` or `startsWith("{")`.
2. **Parse with the right processor** to respect quoting, escaping, nested structures, and component syntax.
3. **Validate structure and business rules**: required fields, types, column count, length limits, value ranges, root path, or destination host.
4. **Use meaningful data types** throughout the rest of the program instead of passing raw strings everywhere.
5. **Serialize/encode on output** with the proper tool for the target format; avoid manually reassembling data with delimiters.

During parsing, convert errors into clear messages for the caller, such as "JSON syntax error", "CSV missing columns", "path outside allowed directory", or "URI has disallowed scheme". Never swallow exceptions and return an empty string, because an empty string can sometimes be valid data.

## 9. Common design pitfalls

### 9.1. Using a single regex for nested structured formats

Regex remains useful for checking **simple patterns**, finding tokens, or validating a text field with a narrow pattern. However, JSON has nested objects/arrays and escapes; CSV has quotes/newlines and parser state; URIs have multiple independent components. When the task is **parsing an entire format**, choose a parser rather than endlessly patching a regex for each counterexample.

### 9.2. Confusing one format's escaping with another's

- JSON escapes `"` and `\` according to JSON rules.
- CSV escapes `"` inside quoted fields using `""` in common dialects.
- URIs percent-encode per component position and rules.
- File paths use file-system segment rules; characters valid on one OS may be invalid on another.

`String.replace("\"", "\\\"")` handles only one case of JSON and does not make a complete JSON serializer; `URLEncoder` does not produce valid file paths; `Pattern.quote` is only for regex literals and does not produce valid CSV or JSON.

### 9.3. Confusing successful parsing with trustworthy data

A parsed JSON object can still contain invalid values; a structurally valid CSV can still contain formulas when opened in a spreadsheet; a parsed `Path` can still point outside an allowed region; a valid `URI` can still point to a forbidden network destination.

A parser answers "**is the syntax understandable?**". Whether the data is permitted to be processed is a **subsequent validation decision** based on business contracts and access policies.

### 9.4. Failing to control size and resources

Very large JSON/CSV inputs can exhaust memory, CPU time, and I/O resources. Set limits on input size, field/column count, nesting depth, and processing time as needed; for large streams prefer streaming parsers. When opening readers, parsers, or files, use `try-with-resources` if the object holds closeable resources.

### 9.5. Guessing based on file extensions or URL prefixes

A `.json` or `.csv` filename does not prove the content matches the format. File extensions are only hints and do not replace parsing and validation. Likewise, text-checking `url.startsWith("https://trusted.example")` can conflate a legitimate host with `trusted.example.evil.test`. Parse the URI, compare host/scheme structurally, and apply appropriate connection policies.

## 10. Practice exercises

**Exercise 1 — JSON:** Create a record `Order(String id, int quantity)`; use a JSON parser to read valid JSON, then test a negative `quantity`, a missing field, and a string containing quotes/Unicode. Distinguish parse errors from business errors.

**Exercise 2 — CSV:** Use a CSV parser to read a record containing `"Lan, A."`, a `"said ""hello"""` field, and a field containing a newline. Print the **exact column count** along with unquoted values. Try a file with headers and a trailing empty field.

**Exercise 3 — Path:** Accept a user-entered relative filename, resolve it against a fixed root, check segment structure, and then discuss how symlinks affect real access checks. Test `summary.csv`, `2026/summary.csv`, `../outside.txt`, and an absolute path.

**Exercise 4 — URI:** Build a search URI from the keyword `"Java & Spring"` and verify `&` resides inside the query **value**. Try resolving a relative path and an absolute URI; verify the resulting scheme/host before sending a request.

## 11. Takeaways

- **String is merely a medium for holding characters; the format determines how to parse it**.
- JSON needs a JSON parser/serializer; CSV needs a CSV parser/printer configured with the right dialect.
- File paths use `Path`, `resolve`, `normalize`, `Files`; syntactic root checks alone do not eliminate symlink risks.
- URIs use `URI` and appropriate **per-component** URI builders/encoders; `URLEncoder` is for form-style query values, not entire URLs.
- `split` and `replace` are useful for simple strings but do not replace tools that understand quoting, escaping, nested structures, encoding, or format semantics.
- After parsing, business validation, resource limits, and access policies are still required; when outputting data, use the serializer/encoder matching the target format.