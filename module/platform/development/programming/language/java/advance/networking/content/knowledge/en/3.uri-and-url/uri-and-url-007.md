# URLEncoder and URLDecoder: encoding form data, not every URL component

In Java Networking, the names **URLEncoder** and **URLDecoder** are very misleading. They are not tools to “encode an entire URL” or “decode any URI”. The primary contract of **java.net.URLEncoder** and **java.net.URLDecoder** is to handle data according to the **application/x-www-form-urlencoded** convention — the format commonly used for HTML form data and for *query parameter values* in many web services.

If you use **URLEncoder.encode(...)** on a path, spaces become plus signs **+**; however, in a normal URI path, a plus sign is a literal character and does not mean a space. If you call **URLDecoder.decode(...)** on an entire URL, plus signs in a path or query with different semantics can also be turned into spaces, and percent-encoded delimiters can be turned back into structural characters.

Lesson goals: understand form encoding rules, distinguish each URI component, build and parse queries properly, spot double encoding/decoding bugs, and choose the right API for the context.

## 1. A URI consists of multiple components with different rules

Consider the following address:

~~~text
https://example.org/docs/a%20b?q=c%2B%2B+tips&lang=vi#overview
|https|   |example.org| |/docs/a%20b| |q=c%2B%2B+tips&lang=vi| |overview|
 scheme     authority      path                query             fragment
~~~

- **Scheme**: https — identifies the URI type/protocol; do not pass the entire string into URLEncoder.
- **Authority/host/port**: example.org — has its own rules for domain names, IPv6, ports, and userinfo.
- **Path**: /docs/a%20b — **/** separates segments; **%20** represents a space byte. A **+** in a normal path does not automatically turn into a space.
- **Query**: q=c%2B%2B+tips&lang=vi — under the *form-encoded* interpretation, **q** has the value “c++ tips”; **&** separates parameter pairs and **=** joins name and value. However, general URI syntax does not require every query to follow this form rule.
- **Fragment**: overview — client-side anchor, typically not sent in the HTTP request target to the server.

**Percent encoding** represents bytes as **%HH** (two hex digits). For Unicode data, bytes are typically produced using **UTF-8**; for example, the character **é** in UTF-8 is two bytes **C3 A9**, represented as **%C3%A9**. Percent encoding is the general URI mechanism, whereas the **space ↔ +** convention is specific to *application/x-www-form-urlencoded*.

Do not conflate them: a **URL** (resource locator) is an application case of URI; **java.net.URI** supports URI structure and syntax handling, while **URLEncoder/URLDecoder** carry “URL” in their names but primarily serve form encoding.

## 2. What exactly do URLEncoder and URLDecoder do?

With **URLEncoder.encode(value, StandardCharsets.UTF_8)** on Java 17:

1. Converts characters to be encoded into bytes using UTF-8.
2. Keeps ASCII letters, digits, and safe characters according to Java's form rule set (including period, hyphen, underscore, and asterisk).
3. Replaces ordinary spaces (U+0020) with **+**.
4. Represents remaining bytes as **%HH**.

**URLDecoder.decode(encoded, StandardCharsets.UTF_8)** does the reverse: **+** becomes space, **%HH** sequences become bytes and are decoded using UTF-8. A literal **+** character in data must be sent as **%2B** to distinguish it from a space.

| Original value | Form-encoded | Meaning |
|---|---|---|
| a b | a+b | Space becomes + |
| a+b | a%2Bb | Literal plus sign is encoded |
| a&b=c | a%26b%3Dc | Delimiter-like characters are just data |
| café | caf%C3%A9 | UTF-8 first, then percent-encode |
| 100% | 100%25 | Literal % becomes %25 |
| a/b | a%2Fb | / is encoded inside a *form value* |
| a~b | a%7Eb | Java's form encoder has a different safe-character set from RFC 3986 |

The last point is very important: Java's form encoder safe-character set is not identical to the **unreserved** set in RFC 3986. For instance, **~** belongs to URI unreserved characters, yet URLEncoder may encode it as **%7E**. In many APIs the result is semantically equivalent, but signatures/canonicalization may require byte-for-byte exactness.

**Use the Charset-accepting overload** instead of the legacy version without a charset. UTF-8 must be agreed upon between sender and receiver. Percent-encoding does not automatically normalize Unicode (for example, an accented character represented in two canonically equivalent Unicode forms with different bytes); if the protocol requires normalization, do it separately according to the protocol's contract.

## 3. Proper usage for form-style queries: encode each name and value

Suppose you need to build a request:

- Parameter name **q** with value “café + Java”.
- Two **tag** parameters with values “a&b=c” and “x y”.

The right way is to encode **each key and each value**, and only then join with **=** between key/value and **&** between pairs:

~~~text
q=caf%C3%A9+%2B+Java&tag=a%26b%3Dc&tag=x+y
~~~

Do **not** encode the entire query string “q=...&tag=...”: if you do, the **=** and **&** used to separate pairs also become data. Nor should you concatenate user values directly without encoding: a value containing **&** or **=** will be misinterpreted as query structure.

### Complete Java 17 example: building and parsing a form query

File **FormQueryDemo.java**:

~~~java
import java.net.URI;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class FormQueryDemo {
    static String pair(String key, String value) {
        return URLEncoder.encode(key, StandardCharsets.UTF_8)
                + "="
                + URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    static Map<String, List<String>> parseFormQuery(String rawQuery) {
        Map<String, List<String>> result = new LinkedHashMap<>();
        if (rawQuery == null || rawQuery.isEmpty()) {
            return result;
        }

        // Split delimiters in the RAW string before decoding.
        for (String field : rawQuery.split("&", -1)) {
            if (field.isEmpty()) {
                continue; // Example-specific convention: skip empty pairs.
            }

            int equalIndex = field.indexOf('=');
            String rawKey = equalIndex < 0
                    ? field : field.substring(0, equalIndex);
            String rawValue = equalIndex < 0
                    ? "" : field.substring(equalIndex + 1);

            String key = URLDecoder.decode(
                    rawKey, StandardCharsets.UTF_8);
            String value = URLDecoder.decode(
                    rawValue, StandardCharsets.UTF_8);

            result.computeIfAbsent(key, ignored -> new ArrayList<>())
                    .add(value);
        }
        return result;
    }

    public static void main(String[] args) {
        String query = String.join("&",
                pair("q", "café + Java"),
                pair("tag", "a&b=c"),
                pair("tag", "x y"));

        // Fixed base with no existing query or fragment.
        URI uri = URI.create("https://example.org/search?" + query);
        Map<String, List<String>> data =
                parseFormQuery(uri.getRawQuery());

        System.out.println("URL: " + uri.toASCIIString());
        System.out.println("Raw query: " + uri.getRawQuery());
        System.out.println("q: " + data.get("q").get(0));
        System.out.println("tag 1: " + data.get("tag").get(0));
        System.out.println("tag 2: " + data.get("tag").get(1));
        System.out.println("tag count: " + data.get("tag").size());
    }
}
~~~

Run in the directory containing the file (Java 17+):

~~~bash
javac -encoding UTF-8 FormQueryDemo.java
java FormQueryDemo
~~~

Output:

~~~text
URL: https://example.org/search?q=caf%C3%A9+%2B+Java&tag=a%26b%3Dc&tag=x+y
Raw query: q=caf%C3%A9+%2B+Java&tag=a%26b%3Dc&tag=x+y
q: café + Java
tag 1: a&b=c
tag 2: x y
tag count: 2
~~~

**Explanation of each decision:**

1. **pair(...)** encodes only the name and value; the two delimiters are joined outside. As a result, “a&b=c” in the data preserves its meaning after decoding.
2. **URI.create(...)** is used here only because we know the fixed base is “https://example.org/search” with no existing query or fragment, and the query part is already validly constructed. For a dynamic base URI that may have a query/fragment, do not blindly append **?**; use a builder that understands each component properly.
3. **getRawQuery()** preserves the percent-encoded string so the parser can split pairs before decoding. If you use **getQuery()**, Java's URI has already percent-decoded it, causing **%26** in a value to reappear as **&**. Splitting then breaks the data.
4. **split("&", -1)** splits on the real **&** delimiters of the query. **indexOf('=')** uses only the first **=** as the key/value boundary; additional **=** characters can appear inside the value. Although the example accepts a field without an equals sign as an empty value, a real API should specify this policy explicitly.
5. **Map<String, List<String>>** preserves repeated keys (**tag** appears twice). Forcing it into Map<String, String> easily loses data or inadvertently picks the first/last value, causing logic bugs.

This is an **illustrative parser for application/x-www-form-urlencoded queries**. It intentionally skips empty fields, does not enforce a canonical order, and does not impose size limits, key counts, or per-value length limits. In an application accepting untrusted input, you must bound input size before splitting/decoding, handle malformed data, and follow your system or framework's duplicate-key policy.

## 4. Why not decode the whole URL or an already-decoded query?

Look at two independent URIs:

~~~text
https://example.org/files/a+b
https://example.org/search?q=a+b
~~~

- In the **path** of the first URI, “a+b” normally means character **a**, plus sign **+**, character **b**. Calling **URLDecoder.decode("a+b", UTF_8)** turns it into “a b” and alters the resource name.
- In the **query** of the second URI, if the server defines the query as **form encoding**, “q=a+b” is interpreted as “a b”. If the protocol uses a standard RFC 3986 query where **+** is a literal plus, blindly using URLDecoder alters the data.

Another bug involves **decoding first and splitting afterward**:

~~~text
RAW query:      item=a%26b%3Dc&mode=short
decode whole:   item=a&b=c&mode=short
~~~

If you split the second line on **&**, the parser mistakes the value **a&b=c** for two parameter pairs. Therefore, when handling form-style queries, operate on **getRawQuery()**, parse boundaries on the raw string, and only then decode names and values separately.

**URI.getQuery() is not the same as URLDecoder.decode(...):** **getQuery()** percent-decodes escapes in the query but does **not** apply the form rule that turns **+** into a space. Thus it is even worse to “take getQuery(), split it, and decode again” when the data contains **%26**, **%3D**, **%25**.

## 5. Encoding a URI path: space is %20, not +

**URLEncoder** is not an encoder for a path segment. In a path, **/** is the segment separator, **?** can start a query, **#** starts a fragment, and **+** is usually a literal plus. Path percent-encoding rules must know which characters are data and which are intentional delimiters.

### Java 17 example: using the URI constructor for a delimited path

File **UriPathDemo.java**:

~~~java
import java.net.URI;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

public class UriPathDemo {
    public static void main(String[] args) throws Exception {
        URI uri = new URI(
                "https", null, "example.org", -1,
                "/files/a b", null, "part 1");

        System.out.println("URI: " + uri.toASCIIString());
        System.out.println("Raw path: " + uri.getRawPath());
        System.out.println("Path: " + uri.getPath());
        System.out.println("Form value: "
                + URLEncoder.encode("a b", StandardCharsets.UTF_8));

        URI plusInPath = URI.create("https://example.org/files/a+b");
        System.out.println("Path with plus: " + plusInPath.getPath());
        System.out.println("Wrong form decode: "
                + URLDecoder.decode(
                        plusInPath.getPath(), StandardCharsets.UTF_8));
    }
}
~~~

~~~bash
javac -encoding UTF-8 UriPathDemo.java
java UriPathDemo
~~~

~~~text
URI: https://example.org/files/a%20b#part%201
Raw path: /files/a%20b
Path: /files/a b
Form value: a+b
Path with plus: /files/a+b
Wrong form decode: /files/a b
~~~

Here, the **URI** constructor takes an unescaped path string and quotes the necessary characters, such as space into **%20**. It is **not** a function that understands “a user-entered segment”. If a segment's data contains **/**, concatenating it directly into the path lets **/** act as a segment separator. In that case, you must use a **path-segment encoder** or a URI builder with a dedicated path-segment API, and verify the server's rules.

Especially for file/router paths, sequences like **.**, **..**, encoded slashes (**%2F**), backslashes, and percent signs must not be assumed safe merely because they were escaped; proxies/routers/servers may normalize or decode at different layers. Authorization and actual path validation must be applied after the server resolves the resource under consistent rules.

**Fragment** has its own encoding rules and is not sent as part of the HTTP request target. **Host** also has its own rules (such as internationalized domain names, IPv6), and is not input for URLEncoder. **Headers, cookies, and JSON bodies** do not use the form encoder unless the protocol explicitly specifies a form-encoded value inside them.

## 6. The same encoder can be used for a POST form body

The **application/x-www-form-urlencoded** type originally served form data, so it is also used as an **HTTP request body**. The core difference is where the string is placed:

- For **GET form/query**, the encoded pairs typically follow **?** in the URI if the endpoint specifies a form-style query.
- For a **POST form body**, the encoded key/value string goes into the body; the header **Content-Type: application/x-www-form-urlencoded; charset=UTF-8** describes the format. Charset and handling must match the receiving side.
- For file uploads or multi-part data, **multipart/form-data** is typically needed; do not use URLEncoder to encode file contents.
- For a JSON body, use a JSON serializer and **application/json**; do not URL-encode the entire JSON as a form unless the API requires it.

The **FormBodyDemo.java** file below only **builds** an HttpRequest and does not call **HttpClient.send()**, so it makes no network connection:

~~~java
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;

public class FormBodyDemo {
    public static void main(String[] args) {
        String body = "name="
                + URLEncoder.encode("Lê An", StandardCharsets.UTF_8)
                + "&message="
                + URLEncoder.encode("a+b & c=d", StandardCharsets.UTF_8);

        HttpRequest request = HttpRequest.newBuilder(
                        URI.create("https://example.org/form"))
                .header("Content-Type",
                        "application/x-www-form-urlencoded; charset=UTF-8")
                .POST(HttpRequest.BodyPublishers.ofString(
                        body, StandardCharsets.UTF_8))
                .build();

        System.out.println("Body: " + body);
        System.out.println("Content-Type: "
                + request.headers().firstValue("Content-Type").orElse(""));
    }
}
~~~

~~~bash
javac -encoding UTF-8 FormBodyDemo.java
java FormBodyDemo
~~~

~~~text
Body: name=L%C3%AA+An&message=a%2Bb+%26+c%3Dd
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
~~~

If you actually send the request, you also need to handle HTTP responses, timeouts, error statuses, authentication, and body size limits. Do not put passwords, access tokens, or sensitive secrets in the URL/query where they may appear in logs, browser history, or monitoring systems.

## 7. Double encoding and double decoding traps

**Double encoding** happens when an already percent-encoded value is encoded a second time:

~~~text
Original data:           a/b
Form encode 1st time:    a%2Fb
Form encode 2nd time:    a%252Fb
Decode 1st time:         a%2Fb
Decode 2nd time:         a/b
~~~

The reason: the **%** in **%2F** gets encoded as **%25**, producing **%252F**. If a system has multiple layers that decode independently under different rules, a string can take on a new meaning after each pass. This can be a bug and can become a vulnerability in routers or path-checking logic.

Short Java example:

~~~java
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

public class DoubleEncodingDemo {
    public static void main(String[] args) {
        String original = "a/b";
        String once = URLEncoder.encode(
                original, StandardCharsets.UTF_8);
        String twice = URLEncoder.encode(
                once, StandardCharsets.UTF_8);

        System.out.println("once: " + once);
        System.out.println("twice: " + twice);
        System.out.println("decode once: "
                + URLDecoder.decode(twice, StandardCharsets.UTF_8));
        System.out.println("decode twice: "
                + URLDecoder.decode(
                        URLDecoder.decode(
                                twice, StandardCharsets.UTF_8),
                        StandardCharsets.UTF_8));
    }
}
~~~

~~~bash
javac -encoding UTF-8 DoubleEncodingDemo.java
java DoubleEncodingDemo
~~~

~~~text
once: a%2Fb
twice: a%252Fb
decode once: a%2Fb
decode twice: a/b
~~~

**Design rule:** define whether data at each boundary is **raw** or **already encoded**; perform encoding when emitting into a URI/form component, and decode exactly once at the receiving boundary according to the protocol. Do not “decode just to be clean” at every layer, and do not mix encoded strings with unencoded strings in the same builder.

### Be careful with URI constructors

**URI.create(fullEncodedUri)** parses a URI string that already has valid percent-escapes. Meanwhile, multi-argument **URI** constructors typically accept **unquoted** component strings and quote the necessary characters themselves.

If you pass the output of **URLEncoder.encode(...)** (which already contains **%**) into the **query** parameter of a constructor like **new URI(scheme, authority, path, query, fragment)**, the **%** can be quoted again into **%25**. The safe approach depends on the builder's contract:

- **Builder accepting raw values:** pass raw keys/values so the builder encodes each component properly once.
- **API accepting already-encoded raw strings:** pass encoded keys/values and do not let the API encode again.
- **URI.create on a complete, properly constructed string:** use only when you control the structure, delimiters, and presence of query/fragment; do not concatenate untrusted data into a whole URI.

Do **not** mix both strategies without clearly knowing which data form the builder expects.

## 8. Validation, decoding errors, and security

**URLDecoder.decode(...)** can throw **IllegalArgumentException** if an escape sequence is invalid, such as **%** not followed by two hex digits. For byte sequences that are invalid under the chosen charset, the error-handling behavior should be checked against the decoder/Java version contract; if the system requires **strict UTF-8 validation**, design a byte-decoding layer with **CharsetDecoder** that reports errors explicitly, rather than relying on URLDecoder to always reject every case.

In addition:

1. **Bound input before parsing:** total query/body size, number of pairs, length of each key/value, and occurrences of a single key; otherwise, very long inputs or many **&** characters can create memory/CPU pressure.
2. **Duplicate-key policy:** for **role=user&role=admin**, the authorization layer and the business layer must pick the same policy; do not let the validation layer take the first value while the consumer takes the last value.
3. **Do not treat encoding as escaping for every output:** you still need HTML escaping when rendering into HTML, parameterized SQL for SQL queries, JSON serialization for JSON, and resource access-control checks.
4. **Do not use URLEncoder to validate host/URL:** a user-provided scheme/host can cause SSRF or open redirect if used arbitrarily; restrict origin, scheme, host/port, and apply proper redirect rules.
5. **Do not reorder or normalize values when signatures are involved:** an API that signs queries may require specific percent-encoding, key ordering, space handling, or **~** handling different from Java's form encoder. Follow that API's specific canonicalization standard.
6. **Test Unicode and delimiters:** Vietnamese characters, plus signs, spaces, **%**, **&**, **=**, **/**, empty strings, duplicate keys, and invalid inputs.
7. **Do not confuse URI parsing with business validation:** constructing a valid URI does not prove the path is safe, access is authorized, or the endpoint is allowed.

## 9. Choose the API based on where the data goes

| Component or task | Use | Avoid |
|---|---|---|
| A **key** or **value** in a form-style query | **URLEncoder.encode(key/value, UTF_8)**; join delimiters afterward | Encoding the entire URL/query and then splitting |
| Parsing a **form-encoded** query | **getRawQuery()**, split raw key/value, **URLDecoder.decode(..., UTF_8)** each part | **getQuery()** then splitting or decoding the whole string first |
| **application/x-www-form-urlencoded** body | Encode each field, send proper Content-Type and charset | Encoding the whole body at once or using it for file uploads |
| **Path** or **path segment** | **java.net.URI** with appropriate raw components, or a builder that encodes *segments* with clear rules | Passing a path into **URLEncoder** |
| **Host**, port, scheme | Dedicated APIs/validation for authority, domain names, IPv6, and scheme | URLEncoder on the whole host/authority |
| **Fragment** | Appropriate URI component/builder | Treating fragment as data sent to the HTTP server |
| Query of a custom-signed/canonical protocol | That protocol's encoder and canonicalization rules | Assuming form encoding works everywhere |
| JSON, XML, HTTP headers, cookies | Format-appropriate serializer/codec | Defaulting to URLEncoder for every string |

## 10. Exercises and self-check questions

### Exercise 1 — Distinguish the plus sign

Predict the output without running the code:

~~~java
System.out.println(URLEncoder.encode("a b", StandardCharsets.UTF_8));
System.out.println(URLEncoder.encode("a+b", StandardCharsets.UTF_8));
System.out.println(URLDecoder.decode("a+b", StandardCharsets.UTF_8));
System.out.println(URLDecoder.decode("a%2Bb", StandardCharsets.UTF_8));
~~~

**Answer:**

~~~text
a+b
a%2Bb
a b
a+b
~~~

In a normal path context, **a+b** remains **a+b**; do not use the third line's behavior to decode a path.

### Exercise 2 — Split the raw query first, then decode

Given the raw query:

~~~text
topic=Java%26Networking&name=L%C3%AA+An&tag=a%3Db&tag=x%2By
~~~

Write a parser that preserves repeated keys. Expected result: **topic = Java&Networking**, **name = Lê An**, list **tag = [a=b, x+y]**. Try replacing the raw query with the string from **URI.getQuery()** before splitting to observe why “Java&Networking” gets split incorrectly.

### Exercise 3 — Write boundary test cases

Test with: empty string, a single plus sign, a single space, a percent sign, accented Unicode, multiple **=** signs, two duplicate keys, and **%ZZ**. Verify the property **decode(encode(x)) = x** when both sides use UTF-8 and the input string is valid. Add length and pair-count limits before parsing.

### Exercise 4 — Design a URI with proper components

A user names a file **report a+b.txt**. Construct a URI to a path with a path segment carrying this name without turning the space into **+** or losing the literal plus sign. Then test filenames containing **/** or **..**; explain why segment rules and path checks are still necessary even after percent-encoding.

### Frequently asked questions

**Can URLEncoder be used for all query strings?** No. Only when the query is specified or agreed upon by both sides as form-style. Many HTTP APIs interpret queries that way, but others require RFC 3986/canonical encoding or a custom parser.

**Does URLDecoder decode %20?** Yes: with the appropriate charset, **%20** becomes a space. However, it also turns **+** into a space, so do not use it arbitrarily on paths or every percent-encoded value.

**Should I call URLDecoder.decode(uri.toString())?** No. It can alter the structure, path, and escaped data. Read each component with the appropriate URI API, then decode according to that component's rules.

**Why is URI.getRawQuery() important?** It preserves **%26**, **%3D**, and other escapes so the parser can still distinguish real delimiters from data bytes. Split boundaries first, decode afterward.

**Is encoded data safe against injection?** Not yet. Proper encoding preserves data structure at a specific boundary; validation, authorization, SSRF protection, output escaping, and canonicalization handling are separate responsibilities.

**Remember:** **URLEncoder/URLDecoder = codec for application/x-www-form-urlencoded form data**. Encode **key/value** separately, decode only **after splitting the raw query**, use **component-aware URI/builders** for path/fragment/authority, and strictly avoid double encoding/decoding across layers.