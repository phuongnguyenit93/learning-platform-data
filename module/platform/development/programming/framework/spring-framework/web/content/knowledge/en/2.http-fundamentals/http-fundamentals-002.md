# URI, Path, Query Parameters, and Encoding Rules in Spring Web

## Learning Objectives

After this lesson, you can:

- Distinguish URI, URL, path, query parameter, and fragment.
- Read, design, and assemble URIs while respecting boundaries between components.
- Explain UTF-8 percent-encoding, the difference between `%20` and `+`, as well as syntactically meaningful characters.
- Receive path/query data in Spring MVC and safely build URIs with `UriComponentsBuilder`.
- Identify double-encoding bugs, premature decoding, invalid input, and differences across proxies, servlet containers, and Spring MVC.

## 1. What Is a URI? Which Components Form a Web Address?

A **URI (Uniform Resource Identifier)** is a string used to identify a resource according to a scheme. A **URL (Uniform Resource Locator)** is the common term for a URI that provides a location/access mechanism, such as `https://...`. Not every URI is an HTTP address: `urn:isbn:...` is an example of a URN.

General syntax of a hierarchical URI per RFC 3986:

```text
scheme ":" hier-part [ "?" query ] [ "#" fragment ]

https://api.example.com:8443/products/42?q=c%C3%A0%20ph%C3%AA&tag=java#reviews
└─┬─┘   └────────┬────────┘ └─────┬────┘ └───────────┬───────────┘ └──┬──┘
scheme       authority           path                query           fragment
              host + port
```

| Component | Example | Meaning |
|---|---|---|
| Scheme | `https` | Access/identification convention; the HTTP(S) scheme establishes the web exchange context. |
| Authority | `api.example.com:8443` | Authority section; for HTTP URLs it usually contains host and optional port. URI syntax allows userinfo, but credentials should not be placed in URLs. |
| Path | `/products/42` | Hierarchical path, typically mapped to a resource or route. |
| Query | `q=c%C3%A0%20ph%C3%AA&tag=java` | Portion after `?`, used to pass criteria/options per application conventions. |
| Fragment | `reviews` | Portion after `#`, indicating a client-side location/reference within the representation. The fragment **is not sent** in the HTTP request-target to the server. |

Note: `?` introducing the query and `#` introducing the fragment are URI delimiters; `&` and `=` commonly separate key/value pairs in *application-level query interpretation*, not mandatory structure for every URI under RFC 3986. For example, `?filter=status:open` can be a completely valid query.

### Absolute URIs and relative references

- Absolute URI: `https://example.com/docs/setup?lang=vi`, includes a scheme.
- Relative reference: `../setup?lang=vi` or `/docs/setup`, requires a base URI to determine the target.
- A path starting with `/` is usually an absolute path within the current authority; a path not starting with `/` is usually relative to the base URI's directory.
- `.` and `..` are dot-segments in a path; the standard defines normalization rules. Do not strip or decode them arbitrarily when handling untrusted URL input.

Example: from base `https://example.com/docs/java/intro`, the reference `../spring?lang=vi` resolves to `https://example.com/docs/spring?lang=vi`. Distinguish **resolving a relative URI** from string concatenation; string concatenation easily corrupts `/`, `?`, and `#`.

## 2. Path: Locating and Mapping Endpoints

A path is a sequence of *segments* separated by `/`. In `/api/v1/products/42`, the segments are `api`, `v1`, `products`, `42`. The slash serves as the hierarchy separator; `42` can be a route variable, whereas `products` is a static segment.

```text
GET /api/v1/products/42 HTTP/1.1
Host: shop.example.com
```

In Spring MVC, routes are commonly declared with `@RequestMapping`, `@GetMapping`, `@PostMapping`,… and path placeholders.

```java
@RestController
@RequestMapping("/api/v1/products")
class ProductController {

    @GetMapping("/{id}")
    Map<String, Object> getOne(@PathVariable long id) {
        return Map.of("id", id, "status", "ok");
    }
}
```

This is a **code snippet inside a Spring Web application with the Spring MVC dependency**, not a standalone Java file. When a client calls `GET /api/v1/products/42`, Spring binds `id = 42` (`long`) and can return JSON containing `"id": 42`, `"status": "ok"` if the application has a JSON message converter. JSON property ordering is not part of this example's contract.

Points to distinguish:

1. `/products` and `/products/` are syntactically two different paths; redirect/route matching for trailing slashes depends on framework and server configuration, so do not assume they are equivalent by default.
2. Case sensitivity, separators, and handling of `;` can affect routing. Design endpoints consistently and define clear conventions.
3. `@PathVariable` is for values **inside the path template**; `@RequestParam` is for parameters extracted by Spring from the query (and potentially form data depending on the Servlet API).
4. A path segment containing `/` as data, such as product code `cup/blue`, is tricky: if encoded as `cup%2Fblue`, a reverse proxy or servlet container may reject or decode it before Spring routes it. Do not assume encoded slashes behave identically across every layer. Consider IDs without slashes or pass special strings via query/body.
5. A path is part of a URI, not automatically an operating system file path. If you later map it to the filesystem, you must check decoding, dot-segments, and block path traversal.

### Designing path and query by role

| Need | Example | Reason |
|---|---|---|
| Fetch a single resource by ID | `GET /products/42` | The ID identifies the resource. |
| Filter a list | `GET /products?category=book` | Query criteria determine the result set. |
| Pagination | `GET /products?page=2&size=20` | List viewing options. |
| Search | `GET /search?q=spring%20mvc` | The search string is a query value. |
| Select a sub-resource | `GET /products/42/reviews/9` | Nested structure expresses resource relationships. |

These are common REST conventions, not mandatory rules of the URI standard. Query parameters **can change the retrieved resource or the cache key**; do not treat queries as purely decorative data.

## 3. Query String: Names, Values, and Repeated Parameters

Consider the example:

```text
GET /products?q=c%C3%A0%20ph%C3%AA&tag=java&tag=web&sort=price%3Aasc&page=2 HTTP/1.1
```

Under common web application parsing:

- `q` has the decoded value `cà phê`.
- `tag` appears **twice**: `java` and `web`. The server may collect them into a list, pick one, or retain multiple values; define the behavior in the API contract.
- `sort` has the value `price:asc`; the `:` character is encoded in the value position as `%3A`.
- `page` is the text `"2"` on the wire; the framework can convert it to an integer if the controller declares `int`.
- `?flag`, `?flag=`, and omitting `flag` can differ semantically; the application needs to decide explicitly.
- Query parameter order should not carry meaning unless specified by the protocol/API; the order of **repeated values for the same key** may matter for some APIs.

Spring MVC example reading path and query together:

```java
@RestController
@RequestMapping("/api")
class SearchController {

    @GetMapping("/products/{category}")
    Map<String, Object> search(
            @PathVariable String category,
            @RequestParam(name = "q", defaultValue = "") String keyword,
            @RequestParam(name = "tag", required = false) List<String> tags,
            @RequestParam(defaultValue = "1") int page) {

        return Map.of(
                "category", category,
                "keyword", keyword,
                "tags", tags == null ? List.of() : tags,
                "page", page);
    }
}
```

With `GET /api/products/books?q=c%C3%A0%20ph%C3%AA&tag=java&tag=web&page=2`, Spring can bind `category = "books"`, `keyword = "cà phê"`, `tags = ["java", "web"]`, `page = 2`. The example is a controller snippet used in Spring MVC; the corresponding annotations and classes must be imported. Failed numeric binding or missing required values typically results in a client error (such as HTTP 400, depending on exception handling configuration).

Query data can appear in browser history, server logs, proxies, or analytics tools. **Do not place passwords, access tokens, or sensitive data in the query string** merely because the connection uses HTTPS.

## 4. Percent-encoding: Encoding Bytes Within Each Component

URIs under RFC 3986 reserve a character set for syntax. When representing an unsuitable byte or a delimiter acting as *data*, use percent-encoding: `%` followed by **two hexadecimal digits**. For example, space has ASCII byte `0x20`, so it becomes `%20`.

### Important character groups

- **Unreserved**: `A-Z a-z 0-9 - . _ ~`. Typically left unencoded.
- **Reserved**: `:/?#[]@!$&'()*+,;=`. A character may act as a syntax delimiter in one component while being allowed as data in another.
- **Non-ASCII**: for Unicode content on the web, strings are typically converted to **UTF-8** bytes, and then bytes requiring encoding are percent-encoded. For example, `à` is UTF-8 bytes `C3 A0`, hence `%C3%A0`.
- **Literal `%` as data**: must be represented as `%25`; the sequence `%20` is three characters encoding the space byte, not literal `%20` text from the original input.

| Data to represent | Typical representation as component data | Why |
|---|---|---|
| Space | `%20` | Space is not in the allowed URI character set. |
| Plus sign `+` | `%2B` | Avoid confusion with form convention, where `+` represents space. |
| Slash `/` inside **one segment** | `%2F` | Prevent the slash from acting as a segment separator. |
| Question mark `?` in a value | `%3F` | Avoid unintentionally starting a query. |
| Hash `#` in a value | `%23` | Avoid unintentionally starting a fragment. |
| Ampersand `&` in a key/value query value | `%26` | Avoid splitting into another parameter. |
| Equals `=` in a key/value query value | `%3D` | Avoid being parsed as a key/value separator. |
| Percent `%` | `%25` | Avoid creating an invalid escape sequence. |
| String `cà phê` in query | `c%C3%A0%20ph%C3%AA` | Encodes the two accented characters in UTF-8 and the space. |

**Key rule: split into components first, then encode the data of each component.** Do not encode an entire URI with a function intended for a single data string; doing so turns structural `:`, `/`, `?`, `&` into data. Conversely, never concatenate unencoded data with `+` into a query or path and hope the server guesses right.

### Step-by-step example with UTF-8

The search string `cà phê & trà` is converted to UTF-8 bytes. When used as **a query value**, the percent-encoded form chosen here is:

```text
Data:             cà phê & trà
Query value:      c%C3%A0%20ph%C3%AA%20%26%20tr%C3%A0
URI:              /search?q=c%C3%A0%20ph%C3%AA%20%26%20tr%C3%A0
Server receives:  q = "cà phê & trà"
```

If you write `/search?q=cà phê & trà` directly, the `&` risks being split into a new query param by a key/value parser. Spaces and Unicode characters are not represented in standard ASCII URI form; browsers may auto-correct them, but library behaviors are not guaranteed to match.

### Why is space sometimes `+` instead of `%20`?

`application/x-www-form-urlencoded` is a **form data encoding convention**: space becomes `+`; a literal `+` must become `%2B`. Under this convention:

```text
Data:                     cà phê + C++
Form-encoded value:       c%C3%A0+ph%C3%AA+%2B+C%2B%2B
Percent-encoded spaces:   c%C3%A0%20ph%C3%AA%20%2B%20C%2B%2B
```

Both results represent the same data when decoded by the **matching mechanism**. In pure URI syntax, `+` does not inherently mean space. Form-convention query decoders commonly interpret `+` as a space; therefore, a literal plus sign in a search term such as `C++` must be encoded as `C%2B%2B`.

## 5. Java 17+: Parsing URIs and Distinguishing Form Encoders

Standard Java provides `java.net.URI` for parsing URIs and `java.net.URLEncoder` for the `application/x-www-form-urlencoded` convention. They serve two different needs.

Standalone file `UriBasics.java`:

```java
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

public class UriBasics {
    public static void main(String[] args) {
        URI uri = URI.create(
            "https://api.example.com:8443/items/42?q=c%C3%A0%20ph%C3%AA&tag=C%2B%2B#info");

        System.out.println(uri.getScheme());
        System.out.println(uri.getAuthority());
        System.out.println(uri.getRawPath());
        System.out.println(uri.getRawQuery());
        System.out.println(uri.getQuery());
        System.out.println(uri.getFragment());

        String formValue = URLEncoder.encode(
            "cà phê + C++", StandardCharsets.UTF_8);
        System.out.println(formValue);
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 UriBasics.java
java UriBasics
```

Exact stdout:

```text
https
api.example.com:8443
/items/42
q=c%C3%A0%20ph%C3%AA&tag=C%2B%2B
q=cà phê&tag=C++
info
c%C3%A0+ph%C3%AA+%2B+C%2B%2B
```

Explanation:

- `getRawQuery()` returns the query with escape sequences intact; `getQuery()` returns the percent-decoded form.
- `getRawPath()` lets you inspect the path string before percent-decoding; `getPath()` returns the percent-decoded path. The difference matters when `%2F`, `%2E`, or data requiring security validation is present.
- `URI` is not an HTTP client; creating a `URI` does not send a request.
- `URLEncoder` **is not a general-purpose URI path encoder**. It serves form payloads: spaces become `+`; slashes can be encoded as `%2F` even when you want them to separate segments.
- `URLDecoder` also follows form rules; do not apply it to an entire URI/path and treat the result as a valid URI.

When assembling complex paths and queries in a Spring application, prefer component-based builders over `String.format()`/string concatenation/`URLEncoder` on the entire URI.

## 6. Building URIs in Spring Web with `UriComponentsBuilder`

`UriComponentsBuilder` belongs to `spring-web` and helps assemble paths/queries and encode contextually.

Java example in a project with the Spring Web dependency (this snippet uses Spring libraries and will not compile with plain JDK alone):

```java
import java.net.URI;
import java.util.Map;
import org.springframework.web.util.UriComponentsBuilder;

public class SpringUriExample {
    public static void main(String[] args) {
        URI uri = UriComponentsBuilder
            .fromUriString("https://api.example.com")
            .pathSegment("products", "{sku}")
            .queryParam("q", "{keyword}")
            .queryParam("tag", "{tag}")
            .encode()
            .buildAndExpand(Map.of(
                "sku", "cup/blue",
                "keyword", "cà phê & trà",
                "tag", "C++"))
            .toUri();

        System.out.println(uri);
    }
}
```

Expected URI output when using the builder's **strictly encode URI variables** rule:

```text
https://api.example.com/products/cup%2Fblue?q=c%C3%A0%20ph%C3%AA%20%26%20tr%C3%A0&tag=C%2B%2B
```

Here `.pathSegment(...)` specifies segments, and `.queryParam(...)` specifies key/value pairs. `{sku}`, `{keyword}`, and `{tag}` are *URI template variables*. Calling `.encode()` on the **builder before expanding** encodes reserved characters inside variables as well, such as `/`, `&`, and `+`, when they act as data. Producing a URI with `%2F` still does not guarantee the server will accept an encoded slash as a path variable; that is a separate request-handling constraint.

### Two non-equivalent encoding modes in Spring

| Method | Mechanism | When to use |
|---|---|---|
| `UriComponentsBuilder.encode()` then expand variables | Encodes the template, then **strictly encodes** variable values, including reserved characters with syntactic meaning. | Default choice when variables hold opaque user data. |
| `UriComponents.encode()` after expand | Encodes characters invalid in each component, but may keep valid reserved characters within the component. | When you intentionally want reserved characters in a variable to carry meaning inside the component, and understand the consequences. |

For path and query encoding, there is no **single** arbitrary string-encoding function that works everywhere. Let the builder manage delimiters, pass data into path segments or query values, and encode only once.

## 7. Real-World Request Flow: Client, Server, Spring

```text
User value: "cà phê & trà"
        |
        v
Client builds URI by component with UTF-8 percent-encoding
        |
        v
GET /search?q=c%C3%A0%20ph%C3%AA%20%26%20tr%C3%A0 HTTP/1.1
        |
        v
Reverse proxy / HTTP server / servlet container processes request-target
        |
        v
Spring MVC selects handler, binds @RequestParam q = "cà phê & trà"
        |
        v
Controller validates data against business contract -> response
```

This is a conceptual flow; layers may enforce their own rules for `%2F`, `%25`, malformed escapes, double dots, semicolons, control characters, and path normalization. Therefore:

- **Do not manually percent-decode again** strings bound by `@RequestParam`/`@PathVariable` without an exact reason. Extra decoding can alter values or introduce vulnerabilities.
- Validate input **after knowing clearly whether the API/framework returns raw or decoded data**; do not guess by visually inspecting the request in a browser.
- If a proxy and the application interpret URIs differently, routing, authentication, or caching can be bypassed; test end-to-end with the real deployment configuration.
- Percent-encoding is a **data representation mechanism**, not security encryption, authentication, authorization, or protection against SQL injection/XSS.

### When used in logs, request signatures, and caches

A URI can form part of a cache key, canonical request, or HMAC signature. If the systems involved normalize differently (query order, hex uppercase/lowercase, `%2F` vs `/`, double-encoding, repeated params), signatures or caches can mismatch. You must agree on **one clearly published canonicalization rule**, rather than arbitrarily decoding/re-encoding a URI. Specific rules depend on the protocol/API.

## 8. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
|---|---|---|
| `"/search?q=" + keyword` with `keyword = "a&b"` | The `&` can be parsed as a new parameter. | Use builder `.queryParam("q", "{q}").encode()` and expand data. |
| Using `URLEncoder` to encode the whole URI | `:`, `/`, `?` become data; broken URI. | Split scheme, path, query, then encode the proper component. |
| Putting `C++` in query but forgetting to encode `+` | Form-style decoders may read it as `C  `. | Encode literal plus signs as `%2B`. |
| Encoding a `%20` string a second time | Becomes `%2520`; server may receive literal `%20` instead of space. | Track whether data is raw or already encoded; one owner encodes. |
| Decoding the entire URI before splitting components | `%26`, `%2F`, `%3F` can turn into delimiters. | Parse structure first, decode per component exactly once. |
| Treating `#fragment` as a server parameter | Backend does not receive the fragment in the HTTP request-target. | If the backend needs data, send it via a well-designed path/query/body. |
| Assuming `%2F` is always a character inside a path variable | Proxy/container may reject or decode the slash. | Use IDs without slashes; test routes through the full infrastructure. |
| Building outbound HTTP URLs from arbitrary user input | May reach unintended hosts (SSRF) or cause open redirects. | Validate scheme/host/port against an allowlist and assemble only permitted components. |

### Checklist when developing a new endpoint

1. Clearly define resources (path segments) and search/filter options (query); document repeated, empty, default parameters, and data types.
2. When generating URIs, pass data into the **right component** via a builder; use UTF-8 and strict encoding for template variables from input.
3. When receiving requests, validate bound values in Spring; check format, size, value range, and resource access permissions.
4. Test with space, `+`, `&`, `#`, `%`, Unicode, `/` in IDs, repeated queries, empty queries, and malformed escape inputs.
5. Test with the same proxy/container and routing configuration used in production, especially for encoded slashes and normalization.

## 9. Self-Check Questions

**1. `/items/12?lang=vi#section-2`: which parts does the server receive?** The HTTP request to the origin contains path `/items/12` and query `lang=vi`; the fragment `section-2` is kept by the client and not transmitted in the request-target.

**2. When a user searches for `C++ & Java`, can you concatenate it verbatim into `?q=...`?** No. In a key/value query value, `+` and `&` must be encoded as data rather than syntax characters, for example `q=C%2B%2B%20%26%20Java` using percent-encoding.

**3. Is `/files/a%2Fb` guaranteed to match a route variable `a/b`?** No. Even though `%2F` represents a slash at the byte level, proxy/container/framework layers may block or interpret it differently. Choose suitable IDs and verify with the actual configuration.

**4. Should you use `URLEncoder` or `UriComponentsBuilder` to build Spring API URLs?** For multi-component URIs, prefer `UriComponentsBuilder` and encode variables in the right positions. `URLEncoder` is for data following the `application/x-www-form-urlencoded` convention, especially form values; do not encode an entire URI with it.

## References

- RFC 3986 — *Uniform Resource Identifier (URI): Generic Syntax*: https://www.rfc-editor.org/rfc/rfc3986
- Spring Framework Reference — *URI Links / URI Encoding*: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html
- Java SE — `java.net.URI` and `java.net.URLEncoder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html and https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLEncoder.html
