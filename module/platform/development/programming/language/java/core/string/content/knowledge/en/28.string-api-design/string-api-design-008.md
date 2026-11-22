# Keeping Encoding and Escaping Responsibilities at the Right Boundaries in Java String API Design

## 1. The core problem

The same **String** can travel across many systems: HTTP requests, Java services, databases, JSON, HTML, URLs, logs, or OS commands. The business value may be identical everywhere, yet **its safe and valid representation** differs at each boundary.

For example, a user enters:

~~~text
Coffee & tea "special"
~~~

Each layer has its own rules:

- On a byte transport, we need a **charset**, such as UTF-8, to convert characters into bytes and decode them back.
- Inside JSON content, double quotes and control characters must be represented according to JSON syntax by a **JSON serializer**.
- Inside HTML text, **&** and **<** must be handled by an **HTML text encoder** according to HTML rules.
- Inside a URL query parameter value, spaces, **&**, **+**, and reserved characters must be encoded by a **component encoder** according to the URL component type.
- Inside a SQL statement, data values should pass through **query parameters**, not string concatenation with manual SQL escaping.

**There is no single universal escape function safe for every destination.** Common bugs happen when escaping too early in the business layer, letting another layer escape a second time, or applying one context's escaping in a different context.

Lesson goals: determine **who is responsible for conversion**, **at which boundary conversion happens**, **what form of data the API holds**, and **how to avoid double encoding** without losing the original content.

## 2. Distinguishing four commonly conflated concepts

| Concept | Question to Answer | Java & Application Examples |
| --- | --- | --- |
| **Charset encoding/decoding** | Which charset converts characters to bytes and back? | **getBytes(StandardCharsets.UTF_8)**, **new String(bytes, UTF_8)** |
| **Syntax/context escaping** | Which characters must be represented differently when embedded in a target language? | JSON string escaping, HTML text/attribute escaping, Java string literals |
| **URL percent/form encoding** | Which URL position does the data occupy and how must characters be represented? | **URLEncoder.encode(value, UTF_8)** for form data |
| **Parameter binding or structured APIs** | Can data be passed separately from syntax to avoid string concatenation? | JDBC **PreparedStatement.setString(...)**, JSON serializers, HTML template engines |

Specifically:

- **Encoding** has multiple meanings depending on context. "UTF-8 encoding" converts characters to bytes; "URL encoding" usually refers to percent-encoding. These two operations are not interchangeable.
- **Escaping** represents characters according to a target syntax's rules. For example, Java source code writes **"A\nB"** to include a newline character in a String, while a JSON serializer must emit a JSON string token with proper quotes and escapes.
- **Base64** represents bytes using an ASCII alphabet, useful for transporting binary data in certain protocols. **Base64 is not a safe escaping mechanism for HTML/SQL/URL**, nor does it encrypt data for confidentiality.
- **Validation** checks whether a value is valid under business rules. **Escaping/parameter binding** ensures data does not become syntax in the target language. These two responsibilities complement rather than replace each other.

For instance, a display name containing **<** may be permitted by business rules, yet still must be HTML-escaped when inserted into an **HTML text context**. There is no need to turn the business value into an escaped string upon ingestion.

## 3. Principle: preserve semantic data, convert when crossing boundaries

A controllable design:

~~~text
HTTP input (bytes + protocol rules)
        |
        v
HTTP framework decodes once into String
        |
        v
Controller -> Service -> Domain: semantic String
        |
        +--> JDBC parameter binding -> Database
        |
        +--> JSON serializer -> HTTP application/json
        |
        +--> HTML template engine -> HTML text/attribute
        |
        +--> URL component encoder -> corresponding query/path value
        |
        +--> Logger with dedicated display/logging policy
~~~

**"Semantic"** does not mean skipping validation or retaining raw bytes. It means the String inside the service represents the user's value, such as **Coffee & tea**, rather than escape sequences tailored to an unchosen output format.

Responsibilities are typically divided as follows:

1. **Input adapter** knows the charset/protocol and decodes input into Java values; checks size limits, data format, and API contracts.
2. **Service/domain** processes the meaning of the value. Do not embed HTML entities or percent-encoded query components into domain fields just for "general safety".
3. **Output adapter/serializer** knows the target context and performs the corresponding escaping/encoding at output time.
4. **Database adapter** uses query parameters rather than relying on manually escaped data.
5. **API interfaces and contract docs** must state clearly when a parameter is a raw semantic value and when it is a string already encoded under a specific standard.

This is a **default design rule**, not an absolute ban on every encoded data type. A system may deliberately store **sanitized HTML** or content already formatted as a **JSON document**; in that case, use a dedicated model/API type, clear policies, and never confuse it with plain text.

## 4. Java String is not bytes: charset is an I/O boundary responsibility

A Java **String** represents character content using UTF-16 per the Java API; it should not be called a "UTF-8-ified String". UTF-8 is a representation used when converting character content into bytes.

~~~java
import java.nio.charset.StandardCharsets;

String value = "Cà phê";
byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);

System.out.println(restored.equals(value)); // true
~~~

This is a round trip **between String and bytes** via UTF-8. If encoding uses UTF-8 while decoding uses a mismatched charset, accented characters can become garbled (mojibake).

**Practical rules:**

- When an API accepts or returns **byte[]**, explicitly specify the charset at the boundary converting to/from String.
- When handling text files, use APIs with a charset argument, such as **Files.readString(path, StandardCharsets.UTF_8)** and **Files.writeString(path, text, StandardCharsets.UTF_8)** when the contract requires UTF-8.
- For HTTP requests/responses, configure and follow Content-Type/charset and framework rules; avoid re-decoding a value the framework already decoded.
- Do not call **new String(bytes)** or **getBytes()** without arguments when communication correctness requires a specific charset.
- Do not assume **String.length()** equals UTF-8 byte count or Unicode code point count. Java String counts UTF-16 units.

**Keep separate:** converting to UTF-8 does **not** make content suitable for direct insertion into HTML, JSON strings, SQL, or URLs. Those are subsequent boundaries with their own grammars.

## 5. URL encoding: encode only the data component in its proper position

URLs have multiple components: scheme, host, path, query, fragment. The same character can mean different things in different components. For example, **/** typically separates path segments; **&** separates query parameter pairs under common conventions; **+** has special meaning under **application/x-www-form-urlencoded**.

In Java:

~~~java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

String keyword = "cà phê & trà";
String encoded = URLEncoder.encode(keyword, StandardCharsets.UTF_8);

String url = "https://example.org/search?q=" + encoded;
~~~

**URLEncoder** is designed for **application/x-www-form-urlencoded** rules, typically used for **form/query parameter values**. It encodes spaces as **+**. Therefore, **do not use URLEncoder to encode an entire URL**, a URL path, or an already-assembled query string.

In the example above, only **keyword** is the data value to encode. Structural URL characters such as **?**, **=**, and **&** between parameters must be produced by a URL builder or code with an explicit contract.

### 5.1. Query values differ from full paths

~~~text
Intended:
  https://example.org/search?q=<form-encoded value of q>

Unintended:
  form-encode the entire "https://example.org/search?q=..." and treat it as a URL
~~~

For **path segments**, do not equate spaces needing percent-encoding with **+** from form encoding. Use a framework or HTTP library URI/URL builder with an explicit **encode path segment** method. A single function for "all of a URL" easily alters delimiters and semantics.

Note: percent-encoding represents data for a URL; it **does not by itself prevent path traversal** or grant access permissions. File/resource paths must still be validated, normalized, and checked against allowed scopes where they are used.

### 5.2. Double encoding and double decoding

A common bug:

~~~java
String raw = "A&B";
String once = URLEncoder.encode(raw, StandardCharsets.UTF_8);
String twice = URLEncoder.encode(once, StandardCharsets.UTF_8);

System.out.println(once);  // A%26B
System.out.println(twice); // A%2526B
~~~

In **twice**, the **%** from the already percent-encoded data gets encoded into **%25**. If the receiver decodes once, the value remains **A%26B** instead of **A&B**.

Design solutions:

- The method accepts **rawQueryValue** and **takes responsibility itself** for encoding exactly once.
- Or the method accepts **encodedQueryComponent** with a clear contract and **does not re-encode**. Avoid leaving a single String parameter ambiguous as to which state it is in.
- Do not automatically decode every string containing **%**. The string **"50% off"** has a legitimate percent sign as normal data.
- Do not decode repeatedly "until readable", as it can change meaning, bypass validation, and cause errors in other layers.

## 6. JSON: delegate to a serializer rather than manual string concatenation

A JSON string is a token with its own syntax. Data containing double quotes, backslashes, newlines, or control characters must be validly represented by a serializer.

**Do not concatenate manually:**

~~~java
// UNSAFE/INCORRECT when userName contains quotes or newlines:
String json = "{\"name\":\"" + userName + "\"}";
~~~

Suppose **userName** is **A" B**; direct concatenation can break the JSON string. The solution is not writing a naive character-replacement list for all cases; use the application environment's JSON serializer, such as Jackson in projects with that dependency.

Example **illustrative snippet requiring the Jackson library** (not a standalone Java SE program):

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

record Profile(String displayName) {}

ObjectMapper mapper = new ObjectMapper();
Profile value = new Profile("A\"B\nC");
String json = mapper.writeValueAsString(value);

// The serializer handles quotes, backslashes, and newlines in JSON.
~~~

When reading JSON, a **JSON parser** turns the JSON string token back into the corresponding Java value. The service should work with semantic String **displayName** without manually adding backslash escapes to store ordinary data.

**Distinguish source literals from runtime data:**

- In **Java source code**, **"A\nB"** is syntax representing a String containing an LF character.
- In **JSON text**, a newline inside a JSON string must be represented per JSON syntax, such as the character sequence **\n** in JSON wire text.
- Never take a Java source literal and assume it is already valid JSON.

When JSON data is embedded into **HTML**, the HTML/script boundary introduces additional rules. A JSON serializer alone does not guarantee safety for embedding content inside **<script>**. Good design returns JSON via an **application/json** response and lets the frontend parse it; if embedding into HTML is genuinely required, use an escaping solution tailored to that exact embedding context.

## 7. HTML: escape by context; there is no one-size-fits-all "HTML escape"

HTML has multiple contexts: **text node**, **attribute**, **URL attribute**, JavaScript inside script, CSS inside style. Escaping rules and risks differ.

Example business data:

~~~text
A&B <Admin>
~~~

If placed into an **HTML text node**, syntactically significant characters like **&** and **<** must be safely represented so users see the exact data without the content becoming an HTML tag.

Principles:

1. When generating HTML, use a **template engine with context-appropriate auto-escaping** or DOM APIs with **textContent** when inserting text.
2. For **HTML attributes**, use escaping specifically meant for attributes; do not take a function meant only for HTML text and assume it is safe everywhere.
3. For **href/src**, beyond HTML attribute escaping, you also must **restrict the URL scheme and target origin**. Escaping quotes does not neutralize a URL with a dangerous scheme.
4. For **JavaScript/CSS contexts**, avoid embedding dynamic strings directly; use separate data-passing mechanisms or encoders dedicated to the exact context.
5. If the goal is to **allow limited HTML content**, you need a **sanitization** pipeline using an explicit allowlist and policy. Full escaping renders markup as plain text; sanitization has a different goal.

**Preventing XSS via output encoding is the renderer's responsibility.** A Java service should not turn every username into a string containing HTML entities and then use that string for email, JSON, SQL, and logs.

### 7.1. Double escaping in HTML

If the service layer replaces **&** with **&amp;**, and then the template engine escapes **&** again, the user may see **&amp;** instead of **&**.

That is not a "missing unescape on the frontend" bug; the design flaw is **two layers both assuming they own escaping responsibility**.

Maintain this model:

~~~text
Domain String:       "A&B"
Template receives:   "A&B"
HTML renderer emits: "A&amp;B"
Browser displays:    A&B
~~~

If safe rich HTML must be stored, model it distinctly from plain-text Strings, and explicitly declare whether the renderer may emit it as markup or must escape it as text.

## 8. SQL: use parameter binding, never manually escape values

SQL operators and syntax must be kept separate from user-supplied data. **Do not** build queries by string concatenation:

~~~java
// Example not to use:
String sql = "SELECT id FROM users WHERE email = '" + email + "'";
~~~

This creates SQL injection risk and quote-handling bugs. The right way is using JDBC parameters:

~~~java
// Illustrative snippet: assumes java.sql.Connection connection exists.
String sql = "SELECT id FROM users WHERE email = ?";

try (java.sql.PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, email);
    try (java.sql.ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("id");
            // Process the record per business logic.
        }
    }
}
~~~

**PreparedStatement.setString(...)** passes the value as data, preventing quotes in **email** from becoming SQL syntax. It also avoids writing database-specific manual escaping.

Remember:

- Parameters can replace **data values**, not table names, column names, or SQL keywords. If a column name must be chosen dynamically, use an **identifier allowlist** and build syntax from trusted choices.
- A **LIKE** condition also has SQL pattern characters such as **%** and **_**. Parameter binding prevents SQL syntax injection, but **does not automatically turn them into literal characters inside a LIKE pattern**; if you want to search for a literal **%**, apply LIKE escaping rules and database-appropriate **ESCAPE** syntax.
- Data sent to the database may still contain **<**, **&**, or quotes. Do not HTML-escape to "prevent SQL injection"; those are two different boundaries.

A column holding a username should store the **semantic username**. When the application reads it and places it into an HTML page, the HTML renderer handles HTML escaping.

## 9. Regex, shell, CSV, and logs have their own boundaries

When accepting a **keyword for literal search**, \`Pattern.compile(input)\` can turn \`.\` or \`*\` into regex operators. If still using the regex API, quote the data portion properly:

~~~java
String literalText = "a.b";
java.util.regex.Pattern pattern =
        java.util.regex.Pattern.compile(
                java.util.regex.Pattern.quote(literalText));
System.out.println(pattern.matcher("x a.b y").find()); // true
System.out.println(pattern.matcher("x acb y").find()); // false
~~~

When invoking processes, pass the executable and individual arguments via \`ProcessBuilder\`, guarding against arguments interpreted as options by the target tool; avoid passing input into string-concatenated shell scripts. When writing CSV, use a CSV writer with dialect-appropriate quoting/escaping, and consider **formula injection** if the file will be opened in spreadsheets. When logging, let the logging sink handle structural log escaping and control CR/LF, control characters, and sensitive data; parameterized log messages do not implicitly strip every character that can cause log injection.

Common thread: \`Pattern.quote\` is only for regex, a CSV writer is only for CSV, and a logging formatter is only for logs. Those transformations are **not** values to write back into a domain \`String\` and reuse for another destination. Detailed syntax explanations and parser/serializer examples are in the two lessons on structured text and format processing.

## 10. Standalone Java 17+ example: right boundaries, avoiding double encoding

Create the file **EncodingBoundaryDemo.java**:

~~~java
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.regex.Pattern;

public class EncodingBoundaryDemo {
    public static void main(String[] args) {
        String raw = "cà phê & trà";

        byte[] utf8 = raw.getBytes(StandardCharsets.UTF_8);
        String restored = new String(utf8, StandardCharsets.UTF_8);
        System.out.println("UTF-8 round trip: " + restored.equals(raw));

        String formValue = URLEncoder.encode(raw, StandardCharsets.UTF_8);
        System.out.println("Form value: " + formValue);
        System.out.println("Form round trip: "
                + URLDecoder.decode(formValue, StandardCharsets.UTF_8).equals(raw));

        String twice = URLEncoder.encode(formValue, StandardCharsets.UTF_8);
        System.out.println("Double encoding contains %25: "
                + twice.contains("%25"));

        String base64 = Base64.getEncoder().encodeToString(utf8);
        byte[] decodedBytes = Base64.getDecoder().decode(base64);
        System.out.println("Base64 round trip: "
                + new String(decodedBytes, StandardCharsets.UTF_8).equals(raw));

        String keyword = "a.b";
        Pattern literal = Pattern.compile(Pattern.quote(keyword));
        System.out.println("Regex literal matches dot: "
                + literal.matcher("x a.b y").find());
        System.out.println("Regex literal rejects wildcard match: "
                + !literal.matcher("x acb y").find());
    }
}
~~~

Compile and run:

~~~bash
javac EncodingBoundaryDemo.java
java EncodingBoundaryDemo
~~~

Output:

~~~text
UTF-8 round trip: true
Form value: c%C3%A0+ph%C3%AA+%26+tr%C3%A0
Form round trip: true
Double encoding contains %25: true
Base64 round trip: true
Regex literal matches dot: true
Regex literal rejects wildcard match: true
~~~

Explanation:

1. **UTF-8** converts String to bytes and back. It does not escape for HTML/SQL.
2. **URLEncoder** converts a form/query parameter value; spaces become **+**, and **&** in the value becomes **%26**.
3. **URLDecoder** accepts properly typed **form-encoded values** and decodes back to the semantic String.
4. Re-encoding **formValue** turns percent signs in **%XX** sequences into **%25**: this is the signature of double encoding, not an extra layer of protection.
5. **Base64** converts bytes into ASCII text and decodes back. It is not HTML/SQL escaping.
6. **Pattern.quote** preserves the literal meaning of the dot in regex.

**Only pass an encoded String to the exact position and protocol it was created for.** Never assign **formValue** to a domain field named **displayName** and then persist it to a database or return it in JSON as a username.

## 11. An error-prone API design and how to fix it

### 11.1. Design prone to double escaping

~~~java
// Illustrative bad pattern:
String saveDisplayName(String submittedName) {
    return submittedName.replace("&", "&amp;");
}
~~~

If the result is stored as the display name, HTML pages may escape it a second time; JSON APIs may return names mangled into **&amp;**; and username searches will no longer match against semantic data.

### 11.2. Design with clearer responsibilities

Keep the original value in the business API:

~~~java
record UserProfile(String displayName) {}

UserProfile profile = new UserProfile("A&B");
~~~

When outputting data:

- HTTP JSON response: **JSON serializer** reads **profile.displayName()** and produces valid JSON text.
- HTML view: **template engine** places the value in a text/attribute context with appropriate output encoding.
- Query to another service: **HTTP client/URI builder** encodes the value in the exact URL component.
- JDBC: **PreparedStatement.setString(...)** passes the string as data.
- Logging: **logger** serializes/formats per sink, with its own rules against log injection and data leakage.

**Do not create a single escapedDisplayName variable shared across all output destinations.**

If an API genuinely accepts or returns encoded text, express that in its name and contract, such as distinguishing **rawQueryValue** from **encodedFormComponent**, along with charset/dialect rules. In large projects, dedicated value objects/wrapper types can prevent mixing states.

## 12. Do not over-decode on input

The principle "escape on output" does not mean "decode everything multiple times on input".

Distinguish clearly:

- HTTP frameworks usually already decode query parameters per protocol. Controllers receive a **String parameter** and must not call **URLDecoder.decode(...)** again.
- JSON parsers already decode escapes inside JSON strings. Services receive the parsed String value and must not manually **unescape JSON**.
- HTML entities in a user string may be **the literal text they intended to enter**. Do not automatically turn **&amp;** into **&** just because it looks like an HTML entity.
- If an endpoint **intentionally** accepts an entire form-encoded payload in raw form, the adapter handles parsing/decoding **exactly once** per the defined Content-Type and charset.

Decoding multiple times can bypass validation or create new delimiter characters only after the second decode pass. Therefore, **the API contract must define the data state at every step** and never use "keep decoding until no special characters remain".

A controlled example:

~~~text
Raw HTTP request: q=A%26B
Framework parses query: parameter q = "A&B"
Service receives: "A&B"
Service does NOT call URLDecode(q) again
~~~

If the data genuinely contains a percent sign, it is still valid data. Validation must inspect the value according to the API contract, not guess that every percent symbol is always an escape.

## 13. Validation, canonicalization, and boundary defense

Context-appropriate encoding/escaping **cannot replace** other checks:

- **Length and type limits:** check before processing to reject invalid input and prevent excessive resource usage.
- **Unicode normalization:** sometimes NFC/NFKC is needed for consistent identity comparison/search, but it requires a business policy; normalization is not a form of HTML escaping.
- **Authorization:** URL encoding does not make a path or ID a resource the user is authorized to access.
- **Path validation:** normalize and verify paths within the root directory, accounting for symbolic links/race conditions; percent-encoding does not replace these checks.
- **HTML sanitization:** required when allowing a subset of external markup; full HTML escaping displays markup as text.
- **SQL parameterization:** used for values; dynamic table/column names require an allowlist.
- **Content-Type:** set the proper media type so the receiver knows which parser and encode/decode rules apply.

A clean control sequence can be: **parse per protocol → construct typed data → validate meaning and authorization → execute business logic → serialize/encode for the exact output context**. Do not lump these operations into one generic function named **sanitizeString** called at every layer.

## 14. Boundary-focused test design

To verify that the system truly assigns responsibilities properly, test with Strings containing "tricky" characters:

~~~text
A&B
A<B
A"B
A'B
a+b
a%2Bb
Line 1
Line 2
cà phê
中文
😀
~~~

Valuable tests:

1. **UTF-8 round-trip:** an arbitrary Unicode String converted to bytes and back to String equals the input.
2. **Form encoding round-trip:** values containing **&**, **+**, spaces, and **%** are encoded/decoded **exactly once** at the right parser.
3. **JSON round-trip:** serializing and parsing back produces the exact same String value, including double quotes, backslashes, and newlines.
4. **HTML rendering:** values containing **<** render as text without creating unintended HTML elements; attributes and URLs are tested in their own contexts.
5. **SQL parameter binding:** values containing single quotes are stored/queried as data without altering SQL statement structure.
6. **No-double-escape:** the renderer receives **A&B** from the service and displays **A&B**, not **&amp;**.
7. **Input framework:** endpoints do not decode a second time a parameter the framework already parsed.
8. **Cross-layer contract:** a value read from the database, returned via JSON, and rendered in HTML retains the exact same **meaning**, even though byte and escape representations differ.

Note: comparing wire content must inspect **the right layer**. A JSON string may contain backslash escaping that the parsed String value does not contain. HTML source may contain entities that the rendered visible text does not contain.

## 15. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Storing HTML-escaped usernames in domain/database | Double escaping or corrupted names in JSON/email | Store semantic String values; escape in the HTML view |
| Using **URLEncoder** on an entire URL | Structural delimiters get wrongly encoded | Encode query/form values or path segments separately with an appropriate builder |
| Encoding a query value twice | **%** turns into **%25**, displaying wrong results | Clearly distinguish raw values from encoded components |
| Calling **URLDecoder** on a framework-parsed parameter | Double decode, altering meaning/validation | Let the input adapter decode exactly once |
| Concatenating quotes into JSON via String concatenation | Invalid JSON or corrupted data | Use a JSON serializer |
| Using HTML escaping to prevent SQL injection | Does not mitigate SQL risk | JDBC PreparedStatement/parameterized SQL |
| Manually replacing single quotes in SQL | Error-prone across dialects/configs | Parameter binding, identifier allowlists |
| Using JSON escaping for HTML text/attributes | Does not guarantee HTML context safety | Context-appropriate HTML encoder/template engine |
| Treating Base64 as security encryption | Provides neither confidentiality nor authentication | Use dedicated security mechanisms when needed |
| Treating Java **String.length()** as UTF-8 byte length | Wrong transmission size limits | Measure on bytes encoded with the right charset |
| Using **Pattern.compile(userInput)** for literal search | Regex characters turn into operators | Use **Pattern.quote(userInput)** |
| Using a generic **escape()** across all layers | Unclear context, prone to double escaping | APIs named and contracted per boundary |

## 16. Code review checklist

- [ ] Does data in the domain/service layer still carry **semantic values**, or has it already been encoded for a specific output?
- [ ] Does the input API clearly state whether data is a raw String or already in a specific encoding/format?
- [ ] Is the charset at the byte/String boundary explicitly specified and matched on both ends?
- [ ] Do JSON and HTML have serializers/renderers responsible for the appropriate **context**?
- [ ] Are URLs encoding only the required **data components**, without encoding the whole string or encoding twice?
- [ ] Does SQL use parameter binding? Are dynamic identifiers restricted by an allowlist?
- [ ] Are values already parsed by the framework protected from being decoded a second time?
- [ ] Are there round-trip tests and tests for content containing **&**, **+**, **%**, quotes, newlines, and Unicode?
- [ ] Are validation, authorization, and data structure checked independently of output encoding?
- [ ] If an encoded string must be retained, do its type, variable name, and contract make that state unambiguous?

## 17. Takeaways

**A String is not inherently "safe" for every destination.** Values in the business layer should preserve their semantic meaning; when crossing into bytes, HTML, JSON, URLs, SQL, regex, or logs, use **destination-specific converters** at the actual boundary:

- **Bytes/String:** specified charset, e.g., UTF-8.
- **JSON:** JSON serializer and parser.
- **HTML:** encoder/template matching text, attribute, URL, or corresponding context.
- **URL:** encoder for the specific query value/path segment; decode once per protocol.
- **SQL:** parameter binding and identifier control.
- **Regex:** **Pattern.quote** when data is literal.
- **Log/CSV/shell:** structured APIs or serializers suited to the target format/command.

This approach preserves accurate data while minimizing **double encoding**, **double escaping**, syntax errors, and injection risks caused by misplaced responsibilities.

### References

- Java SE 17, **java.lang.String** and **java.nio.charset.StandardCharsets**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html
- Java SE 17, **java.net.URLEncoder**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLEncoder.html
- Java SE 17, **java.net.URLDecoder**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLDecoder.html
- Java SE 17, **java.sql.PreparedStatement**: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html
- Java SE 17, **java.util.regex.Pattern**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html
- OWASP, **Cross Site Scripting Prevention Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
- OWASP, **SQL Injection Prevention Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html