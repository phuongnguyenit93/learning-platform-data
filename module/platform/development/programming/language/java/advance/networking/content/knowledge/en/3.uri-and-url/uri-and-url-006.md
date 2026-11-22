# Percent-encoding, Unicode, and the Difference Between Raw and Decoded Components

## Lesson Objectives

When working with URIs/URLs in Java, you must separate two questions: **what components does this string consist of?** and **how is the data within each component encoded?** After this lesson, you will:

- Understand percent-encoding as `%xy`, converting Unicode to UTF-8 and then encoding byte by byte.
- Distinguish URI delimiter characters from percent-encoded data characters.
- Correctly read `getRawPath()`/`getPath()`, `getRawQuery()`/`getQuery()`, and the raw/decoded method pairs of `java.net.URI`.
- Distinguish `URI` percent-decoding from the HTML form format of `URLEncoder`/`URLDecoder`, especially how the `+` sign is handled.
- Know when to use an escaped URI string, when to use a constructor that takes unescaped components, and why double-encoding/double-decoding changes semantics.

Examples use Java 17+ and fixed data so they do not depend on DNS or network connectivity.

## 1. URI Structure and the Role of Delimiters

A hierarchical URI may consist of:

~~~text
https://example.org/caf%C3%A9/notes?name=Vi%E1%BB%87t&tag=a%26b#overview
\___/   \_________/ \_____________/ \______________________/\______/
scheme   authority       path                  query           fragment
~~~

- **Scheme**: `https`, `http`, `file`… identifies the type of URI.
- **Authority**: may contain user-info, host, and port; in the example, it is `example.org`.
- **Path**: the path; unescaped `/` characters separate path segments.
- **Query**: the part after `?`, before `#` if present; representing key/value pairs using `&` and `=` is an application/protocol convention.
- **Fragment**: the part after `#`. For typical HTTP, the fragment is handled client-side and is not included in the request target sent to the server.

An `&` inside a **value** may be written as `%26`, and a `/` inside **a segment's data** may be written as `%2F`. Distinguishing "delimiters" from "data" is why you need to inspect the **raw** form before decoding.

Not every URI has all of the parts above. A URI can be **opaque**, such as a form of `mailto:name@example.org`. In that case, `URI.getPath()` and `getRawPath()` can be `null`; inspect `getSchemeSpecificPart()`/`getRawSchemeSpecificPart()` according to the scheme semantics. In a hierarchical URI, a missing component can also be `null`; an empty component and a completely absent component are not necessarily the same.

## 2. Percent-encoding Operates on Bytes

A percent-escape writes **one byte** as three characters: `%` and two hex digits, commonly denoted `%xy`. For example:

| Data | Hex byte | Percent-encoding |
|---|---|---|
| space | `20` | `%20` |
| `/` character | `2F` | `%2F` |
| `&` character | `26` | `%26` |
| `+` character | `2B` | `%2B` |
| `#` character | `23` | `%23` |
| `%` character | `25` | `%25` |

`%2f` and `%2F` represent the same byte; uppercase hex notation is usually easier to keep consistent. The `%` character must always be escaped as `%25` when it **is data** rather than the start of an escape.

**Unreserved** characters in RFC 3986 consist of ASCII letters, digits, and `- . _ ~` (written together as `-._~`). These characters are usually kept as-is. **Reserved** characters include those that can carry syntactic meaning such as `:`, `/`, `?`, `#`, `@`, `&`, `=`, `+`, and other characters listed in RFC 3986. There is no rule to "always escape every reserved character": you must first know **which component** the character is in and whether it acts as a **delimiter** or **data**.

For example:
- In `/a/b`, the slash separates two segments `a` and `b`.
- In `/a%2Fb`, `%2F` is not a delimiter slash; it is an encoded byte inside **one** segment.
- In `?x=1&y=2`, the `&` character separates two fields according to query convention.
- In `?note=a%26b`, the `&` character is part of the value `a&b`, not a new query pair.

### Unicode Must Be Converted to UTF-8 Before Percent-encoding

Do not percent-encode by directly taking a Java `char` as a single byte. Unicode has code points that differ from UTF-8 bytes, and Java `char` is a UTF-16 code unit. Use UTF-8 to produce a **byte sequence**, then escape each byte that needs to be represented.

| Character | UTF-8 in hex | URI form |
|---|---|---|
| `é` | `C3 A9` | `%C3%A9` |
| `đ` | `C4 91` | `%C4%91` |
| `日` | `E6 97 A5` | `%E6%97%A5` |
| `🙂` | `F0 9F 99 82` | `%F0%9F%99%82` |

The string `café` has three unreserved ASCII characters, so its common representation is `caf%C3%A9`. The string `%E9` **is not the UTF-8 of `é`**: it is just a single byte with value `E9`, which does not form a valid UTF-8 sequence for that character.

There is also a difference in **Unicode normalization**: the letter `é` can be represented as U+00E9 or as `e` (U+0065) + combining acute accent (U+0301). Both forms may look identical, but their UTF-8 encodings are `%C3%A9` and `e%CC%81` respectively. Percent-decoding does not automatically perform NFC/NFD normalization. If business logic requires unifying them, define and apply a separate, deliberate `java.text.Normalizer` policy.

## 3. Raw and Decoded in `java.net.URI`

`URI` provides the following method pairs:

| Component | Raw form | Decoded form |
|---|---|---|
| User info | `getRawUserInfo()` | `getUserInfo()` |
| Authority | `getRawAuthority()` | `getAuthority()` |
| Path | `getRawPath()` | `getPath()` |
| Query | `getRawQuery()` | `getQuery()` |
| Fragment | `getRawFragment()` | `getFragment()` |
| Scheme-specific part | `getRawSchemeSpecificPart()` | `getSchemeSpecificPart()` |

**Raw**: does not interpret `%xy` sequences, preserving existing escapes. **Decoded**: decodes percent-escaped sequences using UTF-8; reserved characters are also decoded. For example, `%2F` can become `/`, `%26` can become `&`.

Two things to remember:
1. **Raw does not mean ASCII-only.** Java can keep Unicode characters directly in a URI string; a raw getter can contain both Unicode and percent-escapes. Use `toASCIIString()` if you want an ASCII-only URI representation.
2. **Decoded is decoded data, not necessarily safe input for re-parsing structure.** `getPath()` has already replaced `%2F` with `/`; `getQuery()` has already replaced `%26` with `&`. If you split the decoded string by those delimiters, you may produce spurious segments or parameters.

`getHost()`/`getScheme()` are extracted separately by the parser; there is no corresponding `getRawHost()`/`getRawScheme()` getter pair. `URI` also does not automatically build a map of query parameters from `getQuery()`.

### Observing a Fixed URI

Consider the URI:

~~~text
https://example.org/caf%C3%A9/%E6%97%A5%E6%9C%AC?note=a%26b&plus=a+b#r%C3%A9sum%C3%A9
~~~

| Getter | Value |
|---|---|
| `getRawPath()` | `/caf%C3%A9/%E6%97%A5%E6%9C%AC` |
| `getPath()` | `/café/日本` |
| `getRawQuery()` | `note=a%26b&plus=a+b` |
| `getQuery()` | `note=a&b&plus=a+b` |
| `getRawFragment()` | `r%C3%A9sum%C3%A9` |
| `getFragment()` | `résumé` |

`getQuery()` decodes `%26` into `&`, but does not turn `+` into a space. If you take the string `note=a&b&plus=a+b` and call `split("&")`, you will mistakenly treat `b` as a separate parameter. Here the value of `note` is actually `a&b`.

## 4. Runnable Java 17+ Example and Verifiable Output

Save the following code to **`UriEncodingDemo.java`**:

~~~java
import java.net.URI;
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

public class UriEncodingDemo {
    public static void main(String[] args) {
        URI uri = URI.create(
            "https://example.org/caf%C3%A9/%E6%97%A5%E6%9C%AC"
            + "?note=a%26b&plus=a+b#r%C3%A9sum%C3%A9"
        );

        System.out.println("raw path: " + uri.getRawPath());
        System.out.println("path: " + uri.getPath());
        System.out.println("raw query: " + uri.getRawQuery());
        System.out.println("query: " + uri.getQuery());
        System.out.println("raw fragment: " + uri.getRawFragment());
        System.out.println("fragment: " + uri.getFragment());

        String form = URLEncoder.encode(
            "café + trà", StandardCharsets.UTF_8
        );
        System.out.println("form: " + form);
        System.out.println("decoded form: " +
            URLDecoder.decode(form, StandardCharsets.UTF_8));

        URI tricky = URI.create("https://example.org/a%2Fb/%252F");
        System.out.println("path2 raw: " + tricky.getRawPath());
        System.out.println("path2: " + tricky.getPath());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 UriEncodingDemo.java
java UriEncodingDemo
~~~

**Exact stdout** (verified in the Java runtime, no network used):

~~~text
raw path: /caf%C3%A9/%E6%97%A5%E6%9C%AC
path: /café/日本
raw query: note=a%26b&plus=a+b
query: note=a&b&plus=a+b
raw fragment: r%C3%A9sum%C3%A9
fragment: résumé
form: caf%C3%A9+%2B+tr%C3%A0
decoded form: café + trà
path2 raw: /a%2Fb/%252F
path2: /a/b/%2F
~~~

Three key takeaways from the output:
- `%C3%A9` and other UTF-8 bytes are decoded by `URI.getPath()` into Unicode.
- `%26` in the query is decoded into `&`, so the decoded query **no longer has enough boundary information** to be split again by `&`.
- `/a%2Fb/%252F` becomes `/a/b/%2F`: `%2F` has become a slash; `%252F` after **one** decode becomes only `%2F`. Decoding a second time changes the meaning of the data.

## 5. Specific Rules of `URLEncoder` and `URLDecoder`

The name `URLEncoder` is misleading. In Java, this class encodes data using the **`application/x-www-form-urlencoded`** format, commonly used for **form field values or queries that follow this convention**. It is not a general-purpose encoder for a complete URI.

With form encoding:
- Spaces become `+`.
- Literal `+` characters in data become `%2B`.
- Unsafe characters are converted into bytes according to a charset—prefer `StandardCharsets.UTF_8`—and then escaped.
- `URLDecoder.decode(value, UTF_8)` performs the reverse process and **turns `+` into a space**.

| Call / data | Result |
|---|---|
| `URLEncoder.encode("a b", UTF_8)` | `a+b` |
| `URLEncoder.encode("a+b", UTF_8)` | `a%2Bb` |
| `URLDecoder.decode("a+b%2Bc", UTF_8)` | `a b+c` |
| `URI.create("https://e.test/?q=a+b%2Bc").getQuery()` | `q=a+b+c` |

The last row illustrates that `URI.getQuery()` only percent-decodes `%2B` into `+`, and does **not** interpret a literal `+` as a space. Therefore, do not run `URLDecoder` on an entire path or full URL: it can alter `+` characters that were valid data.

### Encode Each Query Parameter First, Then Join with Delimiters

If a service uses form-style queries:

~~~java
String query = "term=" +
        URLEncoder.encode("cà phê & trà", StandardCharsets.UTF_8)
        + "&page=1";
URI request = URI.create("https://example.org/search?" + query);
~~~

This is an **illustrative snippet placed inside a method/class** that imports `URI`, `URLEncoder`, and `StandardCharsets`; it is not a standalone Java program. The resulting raw query part is:

~~~text
term=c%C3%A0+ph%C3%AA+%26+tr%C3%A0&page=1
~~~

The `&` belonging to the **value** is encoded as `%26`; the `&` that actually separates the two parameters is preserved. Do not call `URLEncoder.encode` on the complete string `https://example.org/search?term=...`: it will also escape structural characters such as `:`, `/`, `?`, `&`.

### Split the Raw Query Before Decoding Values

When you know the query follows `application/x-www-form-urlencoded`, the correct order is:
1. Get `uri.getRawQuery()`.
2. Split on the `&` delimiters actually present in the raw query.
3. Within each pair, split on the first `=`.
4. Call `URLDecoder.decode(..., UTF_8)` on **each name and value**.

Example **illustrative method**, placed in a Java class that imports `java.net.URI`, `java.net.URLDecoder`, `java.nio.charset.StandardCharsets`, `java.util.ArrayList`, `java.util.List`:

~~~java
static List<String[]> parseFormPairs(URI uri) {
    String raw = uri.getRawQuery();
    if (raw == null || raw.isEmpty()) {
        return List.of();
    }

    List<String[]> result = new ArrayList<>();
    for (String entry : raw.split("&", -1)) {
        String[] fields = entry.split("=", 2);
        String key = URLDecoder.decode(
            fields[0], StandardCharsets.UTF_8);
        String value = URLDecoder.decode(
            fields.length == 2 ? fields[1] : "",
            StandardCharsets.UTF_8);
        result.add(new String[] { key, value });
    }
    return result;
}
~~~

For `note=a%26b&tag=1`, this approach yields two pairs with values `a&b` and `1`; it does not create a spurious `b` parameter. `List` also preserves multiple parameters with the same name (for example `tag=A&tag=B`), avoiding data loss unlike putting them directly into a `Map<String,String>`.

The method above is a **minimal parser assuming form encoding**. A real application needs to define handling for empty keys, missing `=`, empty pairs, charset, duplicate parameters, size limits, and malformed escape sequences. Do not use `URLDecoder` indiscriminately for generic queries where the protocol does not define `+` as space.

## 6. Escaped URI Strings and Component Constructors

Java has two groups of ways to create a URI that must be distinguished.

**Complete escaped URI string:**

~~~java
URI uri = URI.create(
    "https://example.org/files/a%2Fb?name=Vi%E1%BB%87t"
);
~~~

`URI.create(String)` parses the entire string and preserves `%2F`, `%E1...` in the raw getters. `new URI(String)` also parses the string, but declares the checked exception `URISyntaxException`; `URI.create` wraps syntax errors into `IllegalArgumentException`.

**Unescaped components:**

~~~java
URI uri = new URI(
    "https", null, "example.org", -1,
    "/café Việt Nam", null, null
);
System.out.println(uri.getRawPath());
System.out.println(uri.toASCIIString());
~~~

This is an illustrative snippet using the 7-argument constructor, requiring `import java.net.URI` and handling/declaring `URISyntaxException`. The two printed lines:

~~~text
/café%20Việt%20Nam
https://example.org/caf%C3%A9%20Vi%E1%BB%87t%20Nam
~~~

Multi-argument constructors automatically quote illegal characters within components; Unicode characters may remain as-is in the **raw path**. `toASCIIString()` converts the entire URI to ASCII form, percent-encoding Unicode characters when needed. `toString()` may keep Unicode directly.

**Double-encoding trap:** if you pass the path `"/a%2Fb"` into a multi-argument constructor, the `%` character will be quoted into `%25`, producing `"/a%252Fb"` in the raw getter. Reason: the constructor takes **component data**, and does not treat the `%2F` sequence in the input as an escape to preserve. Decide whether the input is already percent-encoded before calling the API; do not mix the two styles arbitrarily.

The constructor also does not know whether the query `"term=a&b"` has two parameters or one value containing `&`. For HTTP queries, use a URI builder library that has a query parameter concept or proactively encode **each value** according to the protocol before joining with delimiters.

### Unicode Hostnames Differ from Unicode Paths/Queries

Internationalized domain names in DNS use **IDNA/Punycode**. Java has `java.net.IDN.toASCII(host)` for certain situations to convert a Unicode hostname to ASCII form for resolution. Do not use `URLEncoder` for an entire hostname, and do not assume percent-encoding a Unicode host is enough for DNS to interpret it correctly. When accessing HTTPS, the client library must apply hostname rules and verify the appropriate TLS certificate.

## 7. What Bugs Does Premature Percent-decoding Cause?

### Path Segments Split Incorrectly

~~~text
Raw URI path: /files/a%2Fb
Decoded path: /files/a/b
~~~

In raw form, `a%2Fb` is a single data segment, even though it contains an escape for a slash. If a router or piece of code calls `getPath()` and then `split("/")`, it may misinterpret it as two segments `a` and `b`. How escaped slashes are handled depends on the server/framework; this is why gateway, routing, and application layers must agree on how to handle them.

### Queries with Spurious Delimiters

~~~text
Raw query:     note=a%26b&sort=asc
Decoded query: note=a&b&sort=asc
~~~

If you split the decoded query, the application thinks there are three items: `note=a`, `b`, and `sort=asc`. Splitting the raw query first and then decoding each field preserves `note=a&b`.

### Double-encoding and Double-decoding

~~~text
/a%252Fb  --decode once-->  /a%2Fb  --decode again-->  /a/b
~~~

`%252F` represents an escaped `%` plus the two characters `2F`. **One** decode produces `%2F`. If another system component continues decoding uncontrollably, the data becomes a slash again, altering routing, file paths, or cache keys.

In a system with browsers, reverse proxies, frameworks, and backends, you need a clear contract on the **input/output format at each boundary**. Only decode according to the protocol, at the right time, and avoid re-decoding an already decoded string. When checking file/path access permissions, apply rules to the representation actually used for access; do not assume a single `URI.normalize()` call is sufficient.

### Invalid Escape Characters

`URI.create("https://example.org/a%G1")` or a lone `%` will be rejected due to invalid percent-escape syntax. A `%xx` sequence may be syntactically valid while its bytes are not valid UTF-8; Java `URI` may insert the replacement character `U+FFFD` in the decoded part. `URLDecoder` may throw `IllegalArgumentException` when encountering an invalid escape. For untrusted input, handle errors explicitly, check length limits, and do not treat decoded-only logs as the original.

## 8. Relationship Between URI, URL, and Types of Normalization

`java.net.URI` is an object representing URI syntax; parsing and calling raw/decoded getters does not open a socket or perform an HTTP request. `java.net.URL` is tied to a protocol/resource locator and has APIs for opening connections, but `URL.getPath()` and `URL.getQuery()` do not provide raw/decoded pairs like `URI`. When syntax analysis is needed, work with `URI` or an appropriate URL library instead of guessing that `URLDecoder` will handle every component correctly.

The following three operations are **not synonymous**:
- **Percent-decoding**: converts `%xx` sequences into bytes and interprets characters; can decode reserved characters into delimiters.
- **`URI.normalize()`**: resolves `.` and `..` path segments according to URI syntax; it is not a "sanitize all input" function.
- **Unicode normalization**: unifies Unicode code point forms (NFC/NFD…) using `java.text.Normalizer` when business logic requires it.

Comparing/canonicalizing URIs, signing URLs, setting cache keys, or checking access permissions should clearly specify raw/decoded form, normalization level, and allowed characters. Do not arbitrarily decode reserved characters or reconstruct a URI from decoded getters as if those strings still preserved syntax.

## 9. Common Misconceptions

| Misconception | Correct understanding |
|---|---|
| "One Unicode character corresponds to one `%xx`." | A single character may require multiple UTF-8 bytes and multiple escapes. |
| "`getRawPath()` is always ASCII." | Raw only preserves escaped octets; a raw string can still contain Unicode directly. |
| "Splitting `getPath()` by slash is always right." | `%2F` has already decoded to `/`, which can change segment boundaries. |
| "Call `getQuery()` then split at `&`." | `%26` in values has also become `&`; split the raw form first. |
| "The `+` sign is always a space." | Only under form encoding convention; `URI.getQuery()` does not turn `+` into a space. |
| "`URLEncoder` is for encoding an entire URL." | It is for HTML form data; encoding an entire URI will break delimiters. |
| "Component constructors preserve `%2F`." | They quote `%` into `%25`, creating `%252F`. |
| "Decoding one more time is safe." | `%252F` can change meaning into a slash when decoded twice. |
| "Two identical-looking letters produce the same URI bytes." | Unicode NFC/NFD forms can differ; normalization is a separate step. |
| "A valid URI is a safe path/hostname." | Valid syntax does not replace validation/authorization/host policy. |

## 10. Self-Practice

1. Explain why `/image/a%2Fb` has a different segment structure from `/image/a/b` even though the two strings may look the same after `getPath()`.
2. For `?note=a%26b&tag=A&tag=B`, write the correct result when parsing as a form query; why is it necessary to keep duplicate `tag` values?
3. UTF-8 encode into percent-escapes for `é`, `đ`, and `日`, then explain why `%E9` cannot replace `%C3%A9`.
4. Compare `URLEncoder.encode("a b", UTF_8)` and `URLEncoder.encode("a+b", UTF_8)`; how do they differ after form-decoding?
5. For the 7-argument constructor receiving the path `"/a%2Fb"`, what does `getRawPath()` return? When should `URI.create(String)` be used instead?
6. For `%252F`, what do you get after one percent-decode? Why does decoding twice risk affecting routing and path checks?
7. Compare `toString()` and `toASCIIString()` for a path containing `"café Việt Nam"`; are raw getter values required to be ASCII-only?

**Key answers:** (1) raw keeps `%2F` as data, decoded has a slash; (2) `note=a&b` and two values `tag=A`, `tag=B`; (3) `%C3%A9`, `%C4%91`, `%E6%97%A5`; (4) `a+b` and `a%2Bb`; (5) `/a%252Fb`; (6) `%2F`, decoding again produces a slash; (7) `toASCIIString()` escapes Unicode, while raw getters can still contain Unicode.

## 11. Technical Summary

- Percent-encoding is **byte → `%xx`**; for Unicode text, it is typically **Unicode → UTF-8 → percent-encoding**.
- Java `URI.getRaw*()` returns the non-percent-decoded representation; `URI.get*()` returns the decoded representation, which may contain delimiters that were previously escaped.
- Use **raw query/path to determine structure**, then decode data according to the protocol rules. Do not re-split decoded text as if it were the original URI.
- `URLEncoder`/`URLDecoder` use the HTML form convention: **space ↔ `+`**; do not use them indiscriminately for a whole URL/path.
- Multi-argument constructors may quote `%` and cause double-encoding. For already-escaped URI strings, use the appropriate parser; when ASCII is needed, use `toASCIIString()`.
- For Unicode hostnames, consider IDNA; for Unicode text comparison, consider normalization; for security/routing, standardize the order of parse/decode/validate.

### References

- [Oracle Java SE 21 — URI, escaped octets, raw/decoded getters, constructors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URI.html)
- [Oracle Java SE 21 — URLEncoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLEncoder.html)
- [Oracle Java SE 21 — URLDecoder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLDecoder.html)
- [RFC 3986 — Uniform Resource Identifier: Generic Syntax, section 2](https://www.rfc-editor.org/rfc/rfc3986.html)
