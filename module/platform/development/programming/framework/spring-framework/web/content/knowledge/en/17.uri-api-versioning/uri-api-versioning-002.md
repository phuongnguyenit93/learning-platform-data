# Encoding a URI Exactly Once and Distinguishing Data from Delimiters in Spring MVC

## 1. Learning objectives

A URI is an address for identifying a resource and also a **syntactic structure**. Within the same URI string, `/`, `?`, `#`, `&`, `=`, or `:` can serve as delimiters; they can also appear as **data** in document names, search keywords, or identifiers. A character acting in a grammatical role must be preserved; the same character, when acting as data inside a specific component, needs to be represented via percent-encoding whenever there is a risk of it being interpreted as syntax.

This lesson applies to **Spring Framework 6.x, Spring MVC on the Servlet stack, Spring Boot 3.x, and Java 17+**, focusing on:

- Understanding URI structure per RFC 3986: scheme, authority, path, query, and fragment.
- Distinguishing **reserved**, **unreserved** characters, and `%HH` in UTF-8.
- Accurately understanding “**encode once at the boundary creating a URI from raw values; parse structure first and decode in the right context at the receiving boundary**”.
- Avoiding double encoding `%2F → %252F`, double decoding `%252E%252E → %2E%2E → ..`, and changing the meaning of `/`, `?`, `&`, `=`, `+`.
- Using `UriComponentsBuilder` and URI template variables safely, and knowing the difference between `UriComponentsBuilder#encode()` and `UriComponents#encode()`.
- Not calling `URLDecoder` indiscriminately on `@RequestParam` or `@PathVariable` already bound by MVC.
- Distinguishing regular URL queries from the `application/x-www-form-urlencoded` convention, especially plus signs and spaces.
- Knowing the limits of encoded slashes in paths across Servlet containers, gateways, and Spring Security.
- Building a runnable Java 17+ example with a Spring Boot controller, `curl`, and MockMvc; designing safe URL versioning.

**Do not apply mechanically to Spring WebFlux**: reactive URL handling and the filter stack may differ. Special URL encoding scenarios should be tested through the exact gateway, Servlet container, Spring Security, and Spring MVC of the deployed system.

## 2. What parts make up a URI?

Example:

```text
https://api.example.test:8443/api/v1/items/abc-42?q=a%2Bb%20%26%20c%2Fd#details
|--- scheme --|----- authority ----|---------- path ----------|----- query ------|fragment
```

To clarify the general syntax:

```text
scheme ":" "//" authority path [ "?" query ] [ "#" fragment ]
                  |             |
                  |             +-- path uses / for segments
                  +-- host and port of the example

Example:
https://example.test/api/v1/items/42?sort=createdAt&order=desc#top
                    ^ path        ^ query                ^ fragment
```

- **Scheme**: `https` or `http`; not arbitrary data chosen by the client when you are constructing internal URLs.
- **Authority**: host/port and related syntax; in particular, you must control the host if the URL is used for redirects, server-side HTTP requests, or callbacks.
- **Path**: usually consists of segments separated by `/`; with Spring MVC, the route `/api/v1/items/{id}` distinguishes real slashes from data inside a segment.
- **Query**: begins after `?`; on the web, many frameworks accept the `name=value&name2=value2` convention. RFC 3986 defines query more broadly than this key-value convention.
- **Fragment**: begins with `#` in a user-facing URI; **not sent in the HTTP request target to the server**. Browsers handle fragments on the client.

The fact that a Spring controller only sees `/api/v1/items/42` or `?q=...` does not mean you should mix all of these parts into a single unparsed string.

## 3. Reserved, unreserved, and percent-encoding

Per RFC 3986:

```text
unreserved = A-Z a-z 0-9 "-" "." "_" "~"

gen-delims = ":" "/" "?" "#" "[" "]" "@"
sub-delims = "!" "$" "&" "'" "(" ")" "*" "+" "," ";" "="

reserved = gen-delims / sub-delims
```

A reserved character **can** act as a delimiter in a given context; in another context it may be allowed as data. You cannot make a rule like “always encode `/` in every URL” because `/` is a path segment delimiter, whereas inside a query keyword `a/b` it is usually data.

**Percent-encoding** replaces a *byte* with `%HH` (two hexadecimal digits). To encode Unicode, first obtain the UTF-8 bytes and then represent the bytes that need escaping. For example:

| Data value | Bytes and representation when encoding is needed |
| --- | --- |
| Space | `%20` in URI percent-encoding |
| `+` | `%2B` if it must avoid being interpreted as space per form query rules |
| `/` | `%2F` when it is segment data, not a delimiter |
| `&` | `%26` if it is data inside a parameter value |
| `=` | `%3D` if it is data and risks acting as a key/value delimiter |
| `#` | `%23` if a client must send the `#` character as data |
| `%` | `%25` for a literal percent sign |
| `é` | `%C3%A9` (UTF-8 bytes C3 A9) |
| `?` | `%3F` if it is data that must avoid being treated as the start of a query |

Uppercase/lowercase hex digits are generally equivalent in escapes (`%2f` and `%2F`), but systems should emit a consistent casing. Percent-encoding is for **values within the appropriate URI component**, not a blind transformation over the entire string. For example, encoding `:` and `/` of `https://` as data breaks the structure.

### Why parse first and decode afterward?

RFC 3986 emphasizes splitting components and subcomponents according to syntax before decoding escapes belonging to that component. If you decode a raw request target before splitting segments, `%2F` can turn into a `/` controlling routing; `%26` can turn into `&` and be treated by the query parser as a new parameter. Some parts such as percent-encoded unreserved characters can be normalized more safely, but **you must never turn a reserved data byte into a delimiter** arbitrarily.

```text
Conceptually right order:
raw URI -> parse scheme/authority/path/query/fragment
        -> parse query keys / delimiters at the right layer
        -> decode each component's data once
        -> validate canonical application value

Wrong:
raw URI -> decode all %HH first -> split on "/" or "&"
                                        (data can become a delimiter)
```

In the Spring MVC Servlet stack, part of parsing/decoding is already done by the container/framework. A controller receiving `@RequestParam` and `@PathVariable` **usually already receives data values**, not raw URL strings to decode again.

## 4. What does “encoding exactly once” actually mean?

It is helpful to distinguish three forms:

1. **Raw logical value**: the business string `"a+b & c/d"`, unencoded.
2. **Encoded URI component**: `a%2Bb%20%26%20c%2Fd` when placed into a parameter value under a strict encoding policy.
3. **Complete URI**: `/api/v1/search?q=a%2Bb%20%26%20c%2Fd`, where `?` and `=` carry syntactic meaning.

Correct URI construction flow:

```text
Raw data:            a+b & c/d
URI template:        /api/v1/search?q={term}
Strict expand:       /api/v1/search?q=a%2Bb%20%26%20c%2Fd
HTTP request:        send generated URI (do not re-encode the whole URL)
MVC @RequestParam:   a+b & c/d
```

If your raw data is literal `"%2F"` (three characters: percent, 2, F), **encoding once** can produce `%252F`, because `%` in data must be escaped as `%25`. That is **not a double-encoding bug**: it accurately represents the literal content the user wants to search for.

Conversely, if `"%2F"` is already the percent-encoded URI component of `/`, passing it into an API expecting **raw data** and encoding again creates `"%252F"`, which is **double encoding caused by confusing data state**.

### Two situations that look alike but are fundamentally different

| Value the business logic actually wants | Input to the URI builder | Correct wire encoding |
| --- | --- | --- |
| Slash character `/` | Raw `/` in the right component | `%2F` if it is data inside a single path segment |
| Three literal characters `%2F` | Raw `%2F` | `%252F` |
| Plus character `+` in form query | Raw `+` | `%2B` |
| A space in query | Raw space | `%20` (URI strict); may be `+` per form convention |
| `&` belonging to a search term | Raw `&` | `%26` |
| `&` separating two query params | URI structure, not a value | Keep literal `&` in query syntax |

To avoid double encoding, **never store raw logical values and already-encoded URIs in the same contractless variable**. Name variables `rawTerm`, `encodedUrl`, `URI uri` so readers know the state.

## 5. Distinguishing data from delimiters

### 5.1. `/` in path

```text
/api/v1/items/a/b        -> two path segments "a" and "b"
/api/v1/items/a%2Fb      -> intended to hold "a/b" in a single segment
```

In theory, a percent-encoded slash represents a slash as data. **In practice on the Servlet stack**, reverse proxies/Tomcat/Spring Security may reject `%2F`, normalize it to a slash before mapping, or apply a different policy. Therefore, do not rely on encoded slashes in `@PathVariable` as a portable solution.

**Usually a safer design:** use URL-safe IDs such as `item_42`, UUID, *unpadded* Base64url when appropriate and security-reviewed, or place data containing slashes into a query param/JSON body rather than forcing “a free-form path variable containing any character”.

### 5.2. `?` and `#` in data

```text
/api/v1/search?q=what?now
/api/v1/search?q=what%3Fnow
```

RFC 3986 allows `?` in the query component, yet some parser layers/URL builders handle URL templates differently. For opaque business data, strict URI variable encoding usually uses `%3F` to eliminate ambiguity.

With `#`:

```text
https://example.test/api/v1/search?q=C#section
```

Everything after `#` is the fragment and **does not travel to the server**; the `q` parameter may only receive `C`. If searching for `"C#section"`, encode the value to `C%23section` before constructing the URI.

### 5.3. `&` and `=` in query

```text
?q=a&role=admin             -> normally two params q and role
?q=a%26role%3Dadmin        -> one value for q: "a&role=admin"
```

If you concatenate strings:

```java
String url = "/api/v1/search?q=" + userInput;
```

and `userInput="a&role=admin"`, you accidentally create **query parameter injection**. Not quite SQL injection, yet it can alter filtering, paging, or authorization semantics if the application reads the injected params.

Instead use a URI builder with **queryParam and opaque template variables**. If the application lets users choose dynamic query parameter names, validate names separately; do not build syntax from arbitrary data.

### 5.4. `;` and matrix/path parameters

The `;` character has special meaning in some frameworks/path-segment conventions. Spring MVC supports matrix variables when configured accordingly, while Spring Security `StrictHttpFirewall` typically rejects semicolons in the URL path by default due to the risk of bypassing security rules.

Do not assume `;` inside a free-form `@PathVariable` will survive intact through every proxy/container/firewall. If an application genuinely uses matrix params, evaluate routing + authorization + firewall configuration holistically rather than flipping a single property to “allow everything”.

## 6. Plus `+` and space: differences between URI and form encoding

This is the most common source of bugs with `@RequestParam`.

**In RFC 3986 generic URIs**, `+` does not automatically mean space. However, under the **`application/x-www-form-urlencoded`** convention used by web forms/parsers for query parameters, `+` is commonly interpreted as a space. Many Servlet parameter parsers apply this convention to the query string.

| Sent URL query | Value `@RequestParam("q")` usually receives |
| --- | --- |
| `?q=a+b` | `"a b"` |
| `?q=a%2Bb` | `"a+b"` |
| `?q=a%20b` | `"a b"` |
| `?q=a%2Bb%20c` | `"a+b c"` |
| `?q=100%25` | `"100%"` |
| `?q=%252F` | `"%2F"` |
| `?q=%2F` | `"/"` |

Distinguish:

- `java.net.URI.getQuery()` percent-decodes the query, yet **does not automatically turn every literal `+` into a space** per form convention.
- `java.net.URLDecoder` is for `application/x-www-form-urlencoded`, **not a generic “decode entire URL” utility**; it turns `+` into space.
- `@RequestParam` on Servlet MVC usually receives a parameter already decoded by servlet request parameter parsing according to convention.
- Do not run `URLDecoder.decode(q, UTF_8)` a second time on an already-bound `q`: a literal `+` can become space, and a literal `%2F` can turn into a slash.

### When should URLEncoder be used?

Java's `URLEncoder` implements **HTML form encoding**. It turns space → `+` and plus → `%2B`; it is suitable for form-urlencoded name/value pairs, not for directly encoding path segments or entire URLs.

Standalone runnable Java 17 example:

File `FormEncodingDemo.java`:

```java
import java.net.URI;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

public class FormEncodingDemo {
    public static void main(String[] args) {
        String raw = "a+b c/d&x=1";

        String encoded =
                URLEncoder.encode(raw, StandardCharsets.UTF_8);
        String decoded =
                URLDecoder.decode(encoded, StandardCharsets.UTF_8);

        System.out.println("form=" + encoded);
        System.out.println("decoded=" + decoded);

        URI uri = URI.create("/api/v1/search?q=a%2Bb");
        System.out.println("rawQuery=" + uri.getRawQuery());
        System.out.println("uriQuery=" + uri.getQuery());
    }
}
```

Compile and run:

```bash
javac FormEncodingDemo.java
java FormEncodingDemo
```

**Exact stdout** on Java 17:

```text
form=a%2Bb+c%2Fd%26x%3D1
decoded=a+b c/d&x=1
rawQuery=q=a%2Bb
uriQuery=q=a+b
```

The difference between `getRawQuery()`/`getQuery()` on `java.net.URI` shows that percent-decoding is not synonymous with form decoding. To build HTTP URIs in Spring, prefer `UriComponentsBuilder`/`UriBuilder` per component rather than trying to use `URLEncoder` for the whole path.

## 7. Spring UriComponentsBuilder: encoding at the right time

According to the Spring Framework documentation, there are **two distinct encoding approaches**:

1. `UriComponentsBuilder.encode()`: encodes the URI template, then **strictly encodes URI variables upon expansion**. This is usually the better choice when values inserted into the template are **opaque data**.
2. `UriComponents.encode()`: expands variables first and then encodes **illegal** characters in each URI component, yet **does not necessarily escape reserved chars that are valid in that component** (for example `;` in a path). When URI variables contain data with delimiters, semantics can differ.

Safe example for a query value:

```java
String term = "a+b & c/d";

String url = UriComponentsBuilder
        .fromPath("/api/v1/search")
        .queryParam("q", "{term}")
        .encode()
        .buildAndExpand(term)
        .toUriString();

System.out.println(url);
```

In a Spring Web project, expected output:

```text
/api/v1/search?q=a%2Bb%20%26%20c%2Fd
```

This is a Java snippet inside a method that already imports `org.springframework.web.util.UriComponentsBuilder`, not a standalone `javac` program because it requires Spring dependencies.

**Key point:** `queryParam("q", "{term}")` places a **URI variable** in the value position, and calling `encode()` before `buildAndExpand(...)` causes the value to be strictly encoded. Do not place user values into the query string via manual concatenation:

```java
// DO NOT DO THIS:
String url = "/api/v1/search?q=" + rawTerm;

// ALSO ERROR-PRONE when rawTerm is already encoded:
String encodedOnce = URLEncoder.encode(rawTerm, UTF_8);
String url2 = UriComponentsBuilder
    .fromPath("/api/v1/search")
    .queryParam("q", "{term}")
    .encode()
    .buildAndExpand(encodedOnce) // % gets encoded into %25
    .toUriString();
```

These anti-pattern snippets only illustrate logic, not standalone compilable files. The builder API expects **raw values** when strict-expanding, not an already percent-encoded string.

### Why are builder.encode() and components.encode() not identical?

Suppose a path variable contains `"a;b"`:

```java
String strict = UriComponentsBuilder
        .fromPath("/items/{id}")
        .encode()
        .buildAndExpand("a;b")
        .toUriString();

String componentEncoded = UriComponentsBuilder
        .fromPath("/items/{id}")
        .buildAndExpand("a;b")
        .encode()
        .toUriString();
```

Example in Spring 6.x:

```text
strict:           /items/a%3Bb
componentEncoded: /items/a;b
```

`;` is syntactically valid in a path at the URI component level, yet can carry reserved meaning for routers/matrix params. **Strict URI-variable encoding** is usually appropriate for user data inputs. With `/` inside a single segment, the strict builder can produce `%2F`, though **that does not mean a Servlet server is guaranteed to accept that request**.

### DefaultUriBuilderFactory and HTTP clients

`DefaultUriBuilderFactory.EncodingMode` provides options such as:

- `TEMPLATE_AND_VALUES`: pre-encodes the template and strictly encodes variables.
- `VALUES_ONLY`: strictly encodes variables without pre-encoding the template in the same way.
- `URI_COMPONENT`: expands and then encodes URI components, keeping valid reserved chars in the component.
- `NONE`: does not encode.

Different HTTP client versions have different default encoding modes (for example, `RestTemplate` historically had legacy compatibility behavior). Do not rely on “the framework will encode it automatically” and skip checking the output. Set a consistent policy for HTTP clients and test with `+`, `&`, `/`, `%`, and Unicode.

## 8. Query parameters: using structured APIs instead of string concatenation

A query with three parameters:

```text
/api/v1/search?q=Java%20%26%20Spring&page=2&sort=createdAt
```

`?` separates the path and query; `&` **outside encoded values** separates params; `=` separates key/value in the convention.

Building with the builder:

```java
String result = UriComponentsBuilder
    .fromPath("/api/v1/search")
    .queryParam("q", "{term}")
    .queryParam("page", "{page}")
    .queryParam("sort", "createdAt")
    .encode()
    .buildAndExpand(
        java.util.Map.of("term", "Java & Spring", "page", 2))
    .toUriString();
```

Expected result:

```text
/api/v1/search?q=Java%20%26%20Spring&page=2&sort=createdAt
```

This is a code snippet with Spring dependencies. `Map.of` does not allow nulls, so handle nullable/optional params before expanding. Do not try to pass an entire string `"q=a&role=admin"` into `queryParam` as a parameter name; the API must distinguish **param name** and **param value**.

### Are param names also user input?

If a program lets clients pick arbitrary parameter names, a name like `q&role` can cause ambiguity if strings are concatenated. Normally, **query param names are code constants** defined by the server/client developer; if dynamic names are needed, validate against an allowlist and use component-aware APIs. Do not “sanitize” by stripping a few characters and pretending the input is safe in every context.

### Repeated parameters

```text
?tag=java&tag=spring
```

Spring MVC can bind repeated values with `@RequestParam List<String> tag` or `MultiValueMap<String,String>`. Do not use `Map<String,String>` if the contract requires keeping every value. If the API expects a single value, define duplicate handling and validate explicitly to prevent HTTP parameter pollution between the gateway/security layer and the application.

## 9. Path segments, @PathVariable, and API versioning

A versioned API often has a route:

```java
@GetMapping("/api/v1/items/{id}")
public ItemResponse one(@PathVariable String id) {
    return new ItemResponse(id);
}
```

Here `/api/v1/items/` is the **fixed path structure**, while `{id}` is a **single segment value**. If a real ID contains a slash, encoding it as `%2F` **may be rejected at the proxy/container/StrictHttpFirewall**, and Spring path matching/servlet request URI handling varies by configuration.

Recommendations:

- Design IDs using URL-safe characters like `A–Z`, `a–z`, `0–9`, `_`, `-`, and where appropriate `~`.
- Use UUIDs or opaque server-generated IDs when possible; do not use raw filesystem paths as route IDs.
- If free-form data such as “folder/a/b” is a search term, put it in an encoded query param or JSON body instead of forcing it into a single-segment `@PathVariable`.
- If API versioning uses `/api/v1`, keep `v1` as **route structure**, rather than injecting a string like `v1/users` as an ID variable expecting it to form a new route.
- When accepting IDs from users, validate business format in the controller/service after binding; do not assume URL encoding replaces input validation or authorization.

### URI encoding is not file path escaping

If `id` is `"../../secret"` or a string decoded from `%2e%2e%2f`, **do not** use it as a filesystem path. You cannot conclude path traversal is blocked merely because the URI was encoded. Take a server-owned key → look up metadata/authorized mapping → access storage safely; validate the canonical path at the actual filesystem operation site.

## 10. Encoded slashes, percent signs, and Spring Security

Spring Security `StrictHttpFirewall` is designed to block many suspicious request targets. By default it restricts cases such as:

- Encoded slashes `%2F` and encoded double slashes in the **URL path**.
- Encoded percent `%25` in the path (associated with double-decode bypasses).
- Semicolon `;`, backslash, encoded periods, and certain suspicious characters depending on version.
- Unnormalized URLs, e.g., dot segments that can be interpreted differently across layers.

Reason: the Servlet API, reverse proxies, and firewalls sometimes disagree on whether a path has already been decoded or normalized. If a security rule inspects one path while the dispatcher evaluates another, there is a risk of **authorization bypass**.

**Do not disable StrictHttpFirewall or turn on `setAllowUrlEncodedSlash(true)` everywhere just because an `/items/a%2Fb` test fails.** Choose safe IDs or an appropriate query/body endpoint, and test the full path end-to-end. For cases that genuinely require an escaped reserved character in the path, audit container/proxy/security config + MVC mapping + logging/canonicalization rather than flipping a single property.

### Data states prone to bypasses

```text
Raw URI             /assets/%252e%252e%252fsecret
1st decode          /assets/%2e%2e%2fsecret
2nd decode          /assets/../secret
Normalized path     /secret   (system-dependent)
```

If a security layer blocks `../` while the string is still encoded and the application layer decodes again and opens a file, a directory traversal path can emerge. For security decisions, layers must agree on a single canonical interpretation and avoid uncontrolled extra decoding.

## 11. Preventing double-encoding and double-decoding

### 11.1. Double encoding

```text
Data to represent:    "/"       (slash character)
Encode component:     "%2F"
Re-encode string:     "%252F"
Server decodes once:  "%2F"     (literal, no longer a slash)
```

If the business logic genuinely wants literal `"%2F"`, the result after a single decode is right. The bug lies in **not knowing whether the input is already encoded or not**.

Bug symptoms:

- The UI displays `%20` instead of a space.
- The server receives `%2F` instead of the slash the user entered.
- A redirect contains `%252F` even though the client only sent a slash.
- A URL contains `%252525` sequences from consecutive encoding layers.

### 11.2. Double decoding

```text
Raw query:            ?q=%252F
Servlet parameter:    "%2F"
Wrong: URLDecoder(q): "/"
```

If a user searches for the exact three characters `"%2F"`, an extra decode turns it into a slash and alters the data. If the string later becomes a path/filename, the bug can become a security vulnerability.

Do not write:

```java
@GetMapping("/search")
public String bad(@RequestParam String q) {
    return java.net.URLDecoder.decode(
        q, java.nio.charset.StandardCharsets.UTF_8);
}
```

This is an anti-pattern in Spring MVC Servlet: `q` has already been bound/decoded by request parameter handling. Similarly, do not decode `@PathVariable` a second time once the framework has produced the logical value, and do not take `getRequestURI()` and call `URLDecoder` on the whole string before routing/authorizing.

### 11.3. What form should be logged?

For debugging purposes, you can log **the normalized URI path/route and allowed parameter names**, with masking/redaction. Do not automatically log the entire raw URI when the query contains tokens, passwords, email/PII; URLs also appear in reverse proxies, browser history, and metrics. If you need to investigate an encoding bug in a test environment, log the raw target and the bound value separately, using dummy data, to verify single-pass decoding.

## 12. UTF-8, Unicode, and normalization

URI percent-encoding operates on **bytes**. When strings are Unicode, use UTF-8 consistently between client and server. For example, `é` encodes in UTF-8 to bytes `C3 A9`, so its URI representation can be `%C3%A9`. Vietnamese has many multi-byte characters, so you cannot take each Java UTF-16 `char` and turn it into a single `%HH`.

Besides encoding, Unicode can also have multiple normalization forms, such as precomposed accented characters vs. base letter + combining mark. Two visually identical strings can have different code point sequences. URI encoding **does not automatically** decide Unicode normalization rules. If IDs/searches/filenames require consistent comparison:

1. Determine normalization needs and rules (for example NFC) per business requirements.
2. Apply normalization **on the raw logical value** at the appropriate layer, rather than repeatedly decoding on the URI wire string.
3. Do not unexpectedly normalize secrets/passwords/signatures; some protocols require byte identity.
4. For case-insensitive IDs, define explicit case folding and locale (avoiding policy-less `toLowerCase()`).
5. Test Vietnamese Unicode, emoji surrogate pairs, combining marks, and non-ASCII characters.

Do not use URI canonicalization as a “strip all dangerous characters” substitute for validation. Whether data such as `/` or `&` is permitted depends on the exact context; it may be valid in a search query yet invalid in an internal path key.

## 13. HTTP clients, browsers, HTML forms, and URL queries

### Browser form GET

```html
<form action="/api/v1/search" method="get">
  <input name="q" value="a+b c/d">
  <button type="submit">Search</button>
</form>
```

When a browser submits a GET form, it builds the query per form rules, typically `q=a%2Bb+c%2Fd` or an equivalent escaping, and Spring MVC receives `"a+b c/d"`. Do not take the query string sent by an HTML form and re-encode the entire string again.

### Browser fetch/JavaScript

JavaScript `URLSearchParams` typically uses form-style rules for query params (space as `+`); `encodeURIComponent` uses different percent-encoding rules and should only encode **one value**, not an entire URL. Despite differences in wire spelling, as long as the client and Servlet parser follow the same convention, the business value matches.

Do not mix encoders arbitrarily:

- A URL built with a component-aware builder is already considered encoded; do not run `URLEncoder.encode(entireUrl,...)`.
- Form bodies `application/x-www-form-urlencoded` have their own serializer; do not confuse them with JSON bodies.
- Do not call `decodeURIComponent` twice on the frontend or `URLDecoder.decode` twice on the backend “to be sure it is decoded”.
- If a URL already has a query, use structured parameter-adding APIs rather than manually concatenating `?`/`&` when unsure of the URL state.

### Inputs worth testing

| Logical value | Why it matters |
| --- | --- |
| `a+b` | Literal plus differs from space in form decoders |
| `a b` | Space may become `%20` or `+` |
| `a&b=c` | Easily turns into extra params |
| `a/b` | Slash is valid in query, sensitive in path segments |
| `100%` | Literal percent needs `%25` |
| `%2F` | Exposes double encode/decode bugs |
| `C#` | Fragment delimiter must be encoded if it is data |
| `a?b` | Query delimiter easily concatenated wrongly |
| `Tôi học Java` | UTF-8, Unicode |
| `../secret` | Must not let URI decoding turn into file traversal |
| `a;b` | Matrix params/semicolon firewall |
| `"emoji 🚀"` | Multi-byte UTF-8 and UTF-16 surrogates |

## 14. Spring Boot 3 Java 17+ application: URL builder and MVC binding

The demo application has three endpoints:

- `GET /api/v1/search?q=...`: receives bound query; returns the logical value for learning (echoing input is for demo only).
- `GET /api/v1/items/{id}`: receives a URL-safe path segment ID.
- `POST /api/v1/links`: receives JSON containing **raw** `term` and `id`, building a URL with `UriComponentsBuilder.encode().buildAndExpand(...)`.

To run it, create a Maven Spring Initializr project with **Java 17+, Spring Boot 3.x**, selecting dependencies: **Spring Web**, **Validation**, **Spring Boot Test**. Use package `com.example.demo` for all Java files.

### 14.1. DemoApplication.java

File `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 14.2. UriDemoController.java

File `src/main/java/com/example/demo/UriDemoController.java`:

```java
package com.example.demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

@RestController
@RequestMapping("/api/v1")
public class UriDemoController {

    @GetMapping(path = "/search",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public SearchResponse search(@RequestParam("q") String q) {
        // q is a value ALREADY processed by the request parameter binder.
        // DO NOT call URLDecoder.decode(q, ...) again.
        return new SearchResponse(q);
    }

    @GetMapping(path = "/items/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public ItemResponse item(@PathVariable("id") String id) {
        // Demo expects URL-safe IDs only, e.g. "item_42".
        // A real application must look up the resource and authorize.
        return new ItemResponse(id);
    }

    @PostMapping(path = "/links",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<LinkResponse> makeLink(
            @Valid @RequestBody LinkRequest input) {

        // input.term() is RAW logical data from JSON, not yet URI-encoded.
        String url = UriComponentsBuilder
                .fromPath("/api/v1/items/{id}")
                .queryParam("q", "{term}")
                .encode()
                .buildAndExpand(Map.of(
                    "id", input.id(),
                    "term", input.term()))
                .toUriString();

        return ResponseEntity.ok(new LinkResponse(url));
    }

    public record SearchResponse(String q) {}

    public record ItemResponse(String id) {}

    public record LinkResponse(String url) {}

    public record LinkRequest(
            @NotBlank
            @Pattern(
                regexp = "[A-Za-z0-9_-]+",
                message = "id must use URL-safe characters")
            String id,

            @NotBlank
            @Size(max = 200)
            String term) {}
}
```

**Why use @Pattern for ID?** The demo API decides `id` is a single-segment “opaque URL-safe token”, not a free-form path. Input like `"a/b"` is rejected by Bean Validation at the link-creation endpoint instead of generating a URL path with an encoded slash that the container might reject. Restricting the character set also reduces ambiguity across URL routing, authorization, and logging. Production can choose UUIDs or another ID scheme.

**Why not call URLEncoder?** `UriComponentsBuilder` receives the raw term and strictly encodes it upon expansion. If a client sends literal `"%2F"` as the term, the generated URL will contain `%252F` in the query, which is correct because it preserves the three literal characters after Servlet parameter decoding.

**Why must GET item still check permissions?** Encoding only helps produce syntactically valid URLs; a user knowing or guessing ID `item_42` does not mean they are allowed to read that resource. The demo controller echoes the ID without querying a DB solely to teach binding, not to demonstrate authorization.

### 14.3. Running the application

Maven wrapper on macOS/Linux:

```bash
./mvnw spring-boot:run
```

Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Spring Boot files require the dependency classpath; `UriDemoController.java` cannot be compiled standalone with `javac` without the Spring libraries. After startup, the default port is usually 8080 unless `server.port` is configured otherwise.

## 15. Practical curl: comparing data and delimiters

### 15.1. Literal plus differs from space

```bash
curl -s 'http://localhost:8080/api/v1/search?q=a+b'
```

On a Servlet request parameter parser following form query rules, expected JSON output:

```json
{"q":"a b"}
```

Next:

```bash
curl -s 'http://localhost:8080/api/v1/search?q=a%2Bb'
```

Expected JSON:

```json
{"q":"a+b"}
```

It is the same plus sign in the raw business value, yet if the client sends a bare `+` in a form-style query, the server can receive a space. Clients wanting a literal plus must encode it as `%2B`.

### 15.2. Are `&` and `=` one value or multiple params?

```bash
curl -s 'http://localhost:8080/api/v1/search?q=a&role=admin'
```

The endpoint is expected to receive `q="a"`, while `role` becomes another parameter (unused by the demo controller). To search for the exact string `"a&role=admin"`:

```bash
curl -s 'http://localhost:8080/api/v1/search?q=a%26role%3Dadmin'
```

Expected JSON:

```json
{"q":"a&role=admin"}
```

This illustrates why you **never concatenate raw input into a query string**.

### 15.3. Literal percent and encoded slash in query

```bash
curl -s 'http://localhost:8080/api/v1/search?q=%2F'
```

Output:

```json
{"q":"/"}
```

Whereas:

```bash
curl -s 'http://localhost:8080/api/v1/search?q=%252F'
```

Output:

```json
{"q":"%2F"}
```

Do not run `URLDecoder.decode(q)` an extra time in the controller, because then the second case turns into `"/"`. Note that these URLs encode the slash inside the **query value**, without requiring the container to support encoded slashes in the **path**.

### 15.4. Using curl to encode parameters automatically

A way to avoid counting `%HH` manually when testing many characters:

```bash
curl -sG 'http://localhost:8080/api/v1/search' \
  --data-urlencode 'q=a+b & c/d'
```

Curl constructs the query value using encoding suitable for form-style parameters; expected JSON response:

```json
{"q":"a+b & c/d"}
```

Do not pass an already percent-encoded value to `--data-urlencode` if you intend to start from a raw logical value, as `%` may be encoded a second time.

### 15.5. Building a URL with Spring UriComponentsBuilder

```bash
curl -s -X POST 'http://localhost:8080/api/v1/links' \
  -H 'Content-Type: application/json' \
  -d '{"id":"item_42","term":"a+b & c/d"}'
```

Expected JSON body:

```json
{"url":"/api/v1/items/item_42?q=a%2Bb%20%26%20c%2Fd"}
```

The query preserves a single logical value containing `+`, space, `&`, and slash. The path keeps `/api/v1/items/` as delimiters, while the ID is validated to be URL-safe. If you create a link with `term="%2F"`, the JSON output will contain `q=%252F` (correct when the term is literal percent-2-F).

### 15.6. Fragments do not reach the server

```bash
curl -s 'http://localhost:8080/api/v1/search?q=C#section'
```

By URI construction and HTTP semantics, `#section` is the fragment and is not sent in the request target; query `q` is only `C`. To have the server receive `C#section`:

```bash
curl -s 'http://localhost:8080/api/v1/search?q=C%23section'
```

Expected:

```json
{"q":"C#section"}
```

### 15.7. Encoded slashes in paths are not portable

Trying `GET /api/v1/items/a%2Fb` may yield HTTP 400, be rejected by a firewall, or have the path interpreted differently depending on the gateway/Servlet/Spring Security. **Do not assume a specific status/JSON for this test**. An endpoint using `item_42` is safer. If a logical ID must contain slashes, consider query/body rather than enabling unrestricted encoded slashes as a quick fix.

## 16. MockMvc testing (Spring Boot 3)

`MockMvc` lets you test controller binding and URL builders. However, **MockMvc does not fully prove real Servlet container percent-decoding/normalization**. In particular, `.param("q", raw)` supplies the parameter value directly in the mock request; do not conclude from it that a raw URI `?q=a+b` will decode identically under Tomcat's parser.

File `src/test/java/com/example/demo/UriDemoControllerTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UriDemoControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void binderPassesRawLogicalQueryValueToController()
            throws Exception {
        mvc.perform(get("/api/v1/search")
                .param("q", "a+b & c/d"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.q").value("a+b & c/d"));
    }

    @Test
    void builderStrictlyEncodesOpaqueQueryVariable()
            throws Exception {
        mvc.perform(post("/api/v1/links")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                  "{\"id\":\"item_42\",\"term\":\"a+b & c/d\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.url").value(
                "/api/v1/items/item_42?q=a%2Bb%20%26%20c%2Fd"));
    }

    @Test
    void percentSequenceLiteralMustRemainLiteral()
            throws Exception {
        mvc.perform(post("/api/v1/links")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"id\":\"x\",\"term\":\"%2F\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.url").value(
                "/api/v1/items/x?q=%252F"));
    }

    @Test
    void rejectsSlashInOpaquePathIdentifier()
            throws Exception {
        mvc.perform(post("/api/v1/links")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"id\":\"a/b\",\"term\":\"java\"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void ordinarySafePathVariableIsReadable()
            throws Exception {
        mvc.perform(get("/api/v1/items/item_42"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value("item_42"));
    }
}
```

Run:

```bash
./mvnw test
```

Windows PowerShell:

```powershell
.\mvnw.cmd test
```

This is a **test code sample** for a Spring Boot 3 project with the corresponding dependencies; it is not output already run inside a specific repository. If Spring Security is enabled, the POST test may need `spring-security-test`, a mock identity, and `csrf()`; a request without a CSRF token may receive 403 **before** reaching the controller.

### Which tests require real HTTP?

Use `@SpringBootTest(webEnvironment = RANDOM_PORT)`/an HTTP client or `curl` through embedded Tomcat and a proxy to verify:

- Raw `?q=a+b` vs. `?q=a%2Bb`.
- `?q=%252F` remaining a literal percent sequence after parameter binding.
- How paths containing `%2F`, `%25`, `%2E`, `;` are handled across the firewall/container.
- Path normalization before/after authorization does not diverge.
- Non-ASCII Unicode, invalid percent triplets (`%ZZ`), slashes/backslashes, and double encoding.
- Whether the reverse proxy re-normalizes URLs or alters `Location` headers/redirects.

MockMvc does not go through every detail of a real connector/Servlet request parser, so URI-building unit tests **and** HTTP-wire integration tests should complement each other.

## 17. Already-encoded URIs: when to use build(true)?

`UriComponentsBuilder.build(true)` tells the builder that the passed components are already **validly percent-encoded**. It is not a “please encode once for me” switch or a fix for double-encoding on data of unknown state.

Two scenarios:

- **Raw user data:** use template variables, `.encode().buildAndExpand(raw)`.
- **Already-encoded URI components with clear provenance and validation:** only when you truly know components are already encoded in the right context should you use “already encoded” APIs like `build(true)` to avoid re-encoding.

Do not use `build(true)` to pass raw `"a&role=admin"` into the query expecting Spring to protect delimiters automatically. If you already have a complete encoded URI from a trusted source, keep it as a `URI` type or use the appropriate parsing API; do not turn a completely encoded URL into a “raw variable” and encode it again.

### When replacing the query on an existing URL

If the initial URL already contains a query and fragment, use `UriComponentsBuilder.fromUri(...)` with a properly parsed input `URI` and structured query-replacement methods instead of concatenating `"?q=" + value`. Depending on builder state, a builder from `URI` already holds encoded components: check the docs for adding raw values/encoded components and encoding modes, and test the resulting URL in practice. Do not call encode again on an already percent-encoded string if the API expects an “already encoded URI”.

## 18. Redirects, Location, and open redirects

An endpoint may build a `Location` header or return a redirect:

```java
URI location = UriComponentsBuilder
        .fromPath("/api/v1/items/{id}")
        .encode()
        .buildAndExpand("item_42")
        .toUri();
```

This snippet is safe with a URL-safe ID. With Spring MVC, the controller can return `ResponseEntity.created(location)...` for a resource-creating POST. If the public URL sits behind a proxy, configure trusted forwarded headers rather than inferring the host from client headers.

**Do not accept a full redirect URL from untrusted input and redirect directly**. URI encoding does not replace scheme/host/path validation on redirect URLs; a user can supply a URL pointing to a phishing site or `javascript:`/an invalid protocol in a dangerous context.

If the server performs an HTTP fetch to a client-supplied URL, **SSRF** can occur; component-aware encoding only handles syntax, not blocking internal access, DNS rebinding, or restricting schemes/hosts. For redirects/callbacks/fetches, use an allowlist of hosts/schemes and appropriate network policies.

## 19. URI, form body, JSON, and HTML output are different contexts

| Context | Right-layer encoder/decoder | What to avoid |
| --- | --- | --- |
| URI path variable | URI template + strict variable encoding | Concatenating raw `/`, relying on encoded slash |
| URI query parameter value | `queryParam` + strict variable encoding | Concatenating raw `&`, `=`, or `#` |
| HTML form query/body | Form serializer/`URLEncoder` | Using as a generic whole-URL encoder |
| JSON request body | JSON serializer/Jackson | Manually URL-encoding JSON strings for no reason |
| HTML text/attribute | HTML escaping/template engine | Assuming URI encoding prevents XSS |
| SQL parameter | Prepared statements/bind variables | Assuming percent-encoding prevents SQL injection |
| Filesystem path | Server-generated key/canonical path policy | Assuming `%2E%2E` is already “safe” |
| HTTP redirect target | URI creation + allowlist schemes/hosts | Open redirect/SSRF from trusting raw URLs |

**A string can pass through multiple contexts**, yet each context requires its own escaping. “Encode exactly once” is a rule against repeated encode/decode **at the same URI boundary**, not a reason to skip HTML escaping when rendering data from a URI onto a web page.

## 20. Common implementation mistakes

1. **Using `URLEncoder.encode(wholeUrl)`**: corrupts scheme, slashes, question marks, and delimiters.
2. **Concatenating a raw search term after `?q=`**: `&` can inject extra parameters.
3. **Not encoding a literal plus `+` in a form query**: the server receives a space.
4. **Decoding `@RequestParam` again with URLDecoder**: loses literal pluses/percent sequences.
5. **Decoding a raw path before splitting segments**: encoded slashes turn into delimiters.
6. **Passing a percent-encoded value into a strict URI variable builder**: re-encodes `%` into `%25`.
7. **Treating literal `%2F` as always meaning a slash**: the client may genuinely want the three characters.
8. **Using `UriComponents#encode()` as strict encoding for arbitrary user data**: valid reserved chars in the component may go unescaped.
9. **Assuming an encoded slash in @PathVariable is always accepted by the container**: depends on connector/firewall/path matching.
10. **Disabling StrictHttpFirewall so encoded slashes work** without checking authorization bypasses.
11. **Inconsistent path normalization between proxy and application**: security and routing see two different resources.
12. **Mistaking `#fragment` for data sent to the server**: fragments are absent from the HTTP request target.
13. **Using a path value as a filename**: URI escaping does not prevent path traversal after decoding.
14. **Assuming JSON/HTML/SQL all need URL encoding**: context-sensitive escaping differs.
15. **Logging raw URIs including tokens in access logs**: leaks credentials/PII.
16. **Putting secrets in URL queries**: easily leaked via history/logs/referrer; use an appropriate transport.
17. **Not constraining ID shape**: URL versioning/path routing becomes unpredictable with encoded slashes/semicolons/periods.
18. **Believing upper/lowercase hex represents different values**: `%2f` and `%2F` are the same byte, though normalizer policies must be consistent.
19. **Decoding a URI multiple times to “fix” input**: turns data into unintended syntactic characters.
20. **Using UTF-16 Java chars as individual percent-escapes**: non-ASCII requires UTF-8 bytes.
21. **Passing an already-encoded URL through a client framework with a different encoding mode**: `%2520` appears or reserved chars disappear.
22. **Thinking MockMvc.param proves wire encoding is right**: mock parameters are already values; real HTTP tests are required.
23. **Trusting @PathVariable contains decoded user input so skipping validation**: encoding does not replace authz/format validation.
24. **Not checking duplicate query parameters**: gateway and app may pick different values.
25. **Allowing untrusted full URLs in Location or HTTP fetches**: encoding does not stop open redirect/SSRF.
26. **Building raw URLs with string formatting in multiple places**: the same data goes through different encoders; centralize URI construction in clear APIs.
27. **Not checking Unicode normalization**: IDs may look identical while differing in bytes/code points.
28. **Not testing proxies/CDNs**: the edge may decode/normalize/rewrite URLs before Spring.

## 21. Code review and testing checklist

### Creating URIs

- [ ] Is it clear which raw logical values are data and which literals are delimiters?
- [ ] Are URIs built using components/templates rather than raw string concatenation?
- [ ] Are URI variables holding opaque data strictly encoded **at expansion time**, rather than pre-encoded and encoded again?
- [ ] Is `%` in raw values preserved accurately: literal `%2F` → wire `%252F`?
- [ ] Are query param values containing `+`, `&`, `=`, `#`, `/` tested?
- [ ] If a URL is already encoded, is there a clear contract so it is not re-encoded as a raw variable?
- [ ] Are API path IDs URL-safe and independent of filesystem paths?
- [ ] Do public/Location URIs behind a proxy use trusted scheme/host?

### Receiving URIs

- [ ] Are Spring MVC @RequestParam/@PathVariable already decoded by the framework, with no second URLDecoder call?
- [ ] Is parsing a raw URI via split/double-decode before identifying components avoided?
- [ ] Are container, Spring Security, and gateway consistent on encoded slashes/periods/percent signs?
- [ ] Are repeated/unknown query params handled according to the API contract?
- [ ] Is data from URIs still validated, authorized, and escaped for other HTML/SQL/filesystem contexts?

### Testing

- [ ] Do Java unit tests demonstrate the difference between form encoding and URI raw/decoded queries?
- [ ] Is URI builder output asserted with plus, space, ampersand, slash, and literal percent?
- [ ] Does MockMvc test bound values and generated URLs properly?
- [ ] Does real HTTP test `?q=a+b` separately from `?q=a%2Bb`?
- [ ] Does real HTTP test that `%252F` is not double-decoded by the backend?
- [ ] Is the path firewall tested with `%2F`, `%25`, `%2E`, and `;` in a realistic environment?
- [ ] Are Vietnamese Unicode/emoji and required canonicalization forms tested?
- [ ] Are redirects/external URLs reviewed for SSRF/open redirect and ensuring no secrets leak in queries/logs?

## 22. Self-check your knowledge

**1.** In `/items/a/b`, what is the second slash?

**Answer:** A path segment delimiter. If an ID genuinely contains a slash, component-appropriate encoding is needed, yet on the Servlet stack encoded slashes can be rejected; prefer URL-safe IDs or query/body.

**2.** Why is `?q=a&role=admin` different from `?q=a%26role%3Dadmin`?

**Answer:** The former can be two params; the latter holds a single value for `q` containing literal `&` and `=` after binding.

**3.** In a form-style query, what do `?q=a+b` and `?q=a%2Bb` yield?

**Answer:** Usually `"a b"` and `"a+b"`, respectively. A literal plus requires `%2B`.

**4.** If the business value is literal `"%2F"`, why does the builder produce `"%252F"`?

**Answer:** The percent sign is data that must encode to `%25`; after a single decode, the backend receives the exact literal `%2F`. Do not arbitrarily decode further.

**5.** What is the key difference between `UriComponentsBuilder.encode()` and `UriComponents.encode()`?

**Answer:** The builder encodes the template first and strictly encodes expanded variable values; `UriComponents.encode()` encodes after expansion, keeping some reserved chars that are valid in the component.

**6.** `@RequestParam q` is already a logical value; should you call `URLDecoder.decode(q)`?

**Answer:** No. It can double-decode percent sequences and turn literal pluses into spaces.

**7.** Does a URL fragment `#section` reach the Spring MVC controller?

**Answer:** No. If you want data containing `#` in a query, use `%23`.

**8.** Why shouldn't you arbitrarily enable the firewall to allow encoded slashes?

**Answer:** Proxy/container/security/MVC may interpret the path differently, causing route authorization bypasses.

**9.** Does URI encoding replace HTML escaping or prepared SQL?

**Answer:** No. Each output context has its own escaping rules; URL encoding solves URI structure.

**10.** Why does MockMvc `.param("q","a+b")` not prove the behavior of a raw URL `?q=a+b`?

**Answer:** `.param` sets the logical parameter value directly on the mock request. To test raw URI decoding, you must send real HTTP through a Servlet container.

**11.** With API versioning like `/api/v1`, does `v1` belong to raw business values or path structure?

**Answer:** It is intentional route structure; do not encode all of `/api/v1` as a single variable.

**12.** Why do you need to know whether data is already percent-encoded before calling the builder?

**Answer:** Raw logical values and encoded components have different contracts. Re-encoding an already-encoded string causes double encoding, while skipping encoding on a raw string can turn data into delimiters.

## 23. References

- RFC 3986 — URI Generic Syntax, percent-encoding, reserved/unreserved, parse before decode: https://www.rfc-editor.org/rfc/rfc3986.html
- RFC 3987 — Internationalized Resource Identifiers: https://www.rfc-editor.org/rfc/rfc3987.html
- WHATWG URL Standard — URL parsing/form-urlencoded conventions: https://url.spec.whatwg.org/
- Spring Framework — URI Links and encoding modes: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html
- Spring Framework — `UriComponentsBuilder` API: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/web/util/UriComponentsBuilder.html
- Spring Framework — `UriUtils` API: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/web/util/UriUtils.html
- Spring Framework — Spring MVC Path Matching: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework — `@RequestParam`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html
- Spring Security — StrictHttpFirewall and request matching: https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html
- Java 17 — `java.net.URI`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html
- Java 17 — `java.net.URLEncoder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLEncoder.html
- Java 17 — `java.net.URLDecoder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLDecoder.html
- RFC 9110 — HTTP Semantics and request targets: https://www.rfc-editor.org/rfc/rfc9110.html
