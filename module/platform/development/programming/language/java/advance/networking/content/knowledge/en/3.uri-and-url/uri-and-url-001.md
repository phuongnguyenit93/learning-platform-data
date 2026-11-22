# URI and URL: Distinguishing Resource Identification from Accessibility

## 1. The Problem: Knowing What a Resource Is Differs from Knowing Where to Access It

A network application must answer two related but distinct questions:

- **Identification:** Which string allows parties to refer to the same resource? For example, “Java guide documentation”, “a book by ISBN”, “record number 42”.
- **Location/Access:** Given the available information, what mechanism can the application use to find, access, or interact with the resource? For example, HTTPS to a specific host and path.

**URI (Uniform Resource Identifier)** is the overarching concept: a sequence of characters used to **identify a resource** according to a generic syntax. **URL (Uniform Resource Locator)** is the familiar term for **the group of URIs that contain information about the access mechanism/location of a resource**, such as `https://docs.example.org/guide`. According to the distinction in RFC 3986, a URL is **a subset of a URI**. Therefore, an HTTPS web address is typically **both a URI and a URL**; these are not mutually exclusive types.

A **resource** can be a web page, API endpoint, image, service, document, or an abstract concept. A URI identifies a resource, but **does not necessarily** contain the resource's content, and does not guarantee that anyone can currently access that resource. A URL remains a URL even if the server is temporarily down, the resource requires login, returns a 404 error, or redirects to another address.

Goals after this lesson:

1. Distinguish URI from URL by **identification purpose** and **access information**, without conflating the two terms.
2. Analyze scheme, authority, host, path, query, and fragment in common URIs.
3. Distinguish absolute URIs, relative URI references, and URNs.
4. Use `java.net.URI` and `java.net.URL` in their proper roles; know when network communication actually occurs.
5. Avoid errors in encoding handling, path concatenation, and using URIs/URLs from untrusted data.

## 2. Four Concepts Easily Confused

| Concept | Main Question | Example | Key Point |
|---|---|---|---|
| **Resource** | “Which object is being referred to?” | A Java guide page, an order | A resource is the identified object; the returned content may be a **representation** of the resource |
| **URI** | “Which name/string is used to identify the object?” | `urn:isbn:9780134685991` or `https://docs.example.org/guide` | A URI can identify by name or by location information |
| **URL** | “What access method/location does this URI specify?” | `https://docs.example.org/guide` | Usually has an access scheme and location information; **does not guarantee** successful access |
| **URN** (Uniform Resource Name) | “What is the identifying name within a namespace?” | `urn:isbn:9780134685991` | A type of URI focused on a persistent identifying name; the URN string itself does not state which server to send HTTP requests to |

**Example:** `urn:isbn:9780134685991` identifies a publication within the ISBN namespace; it does not provide a specific HTTP host to download the content. Meanwhile, `https://catalog.example.org/books/9780134685991` both identifies the resource in the catalog system and indicates the HTTPS method and access location that a client can attempt to use.

You should not state “a URI is only a logical name, a URL is only a physical address”: a URL **is also an identifier**, and the host/path in a URL can be a logical address sitting in front of a reverse proxy, load balancer, or dynamic routing system. A “web address” does not necessarily correspond to a single fixed physical server.

### Examples to Classify

| String | Reasonable Classification | Explanation |
|---|---|---|
| `https://example.org/articles/42` | Absolute URI; commonly called a URL | HTTPS scheme + host/path location information |
| `http://localhost:8080/api/books` | Absolute URI; URL | HTTP to port 8080 of the machine running the client; not necessarily accessible outside that machine |
| `urn:isbn:9780134685991` | Absolute URI, URN form | Has `urn` scheme and namespace-based name; not a web URL |
| `mailto:team@example.org` | Absolute URI with `mailto` scheme | Indicates how to interpret an email address; not an HTTP endpoint and has no host following the HTTPS URI structure |
| `../images/logo.svg` | Relative URI reference | Has no scheme; requires a base URI to resolve |
| `/api/orders/42` | URI reference with path starting with `/` | Path starts from the root of the current authority, yet **still not an absolute URI in the sense of having a scheme** |
| `#faq` | Fragment-only reference | Points to a section/context within the base resource |
| `example.org/docs` | String that may be interpreted as a relative path | Not an HTTPS URL on its own; browsers automatically prepending `https://` is a UI policy, not a general URI rule |

In Java, `URI.isAbsolute()` checks **whether a scheme is present or not**. Thus, `https://example.org/x` and `urn:isbn:...` are both absolute; whereas `/api/x` and `../x` are both relative URI references.

## 3. Structure of a Hierarchical URI

For a common web URL:

```text
https://user@example.org:8443/docs/java/index.html?lang=vi&mode=short#install
\___/   \__/ \_________/ \__/ \__________________/ \________________/ \_____/
scheme userinfo  host    port         path               query       fragment
        \___________________ authority ___________________/
```

The commonly used general structure of a hierarchical URI is:

```text
scheme ":" "//" authority path [ "?" query ] [ "#" fragment ]
```

**This is a common form, not the entire URI syntax.** Not every URI has `//authority`: `urn:isbn:...` and `mailto:...` are examples that have a scheme without the host/path structure like HTTPS.

- **Scheme:** the initial label of the URI before the `:` character, such as `https`, `http`, `ftp`, `urn`, `mailto`. The scheme determines how the rest is interpreted; **having a scheme does not mean it is immediately reachable over the network**.
- **Authority:** the part after `//` (if present), usually containing `[userinfo@]host[:port]`. For HTTP(S), the host represents a domain name or server address; the port selects the service endpoint. Putting a username/password in a URL is an insecure practice and should be avoided.
- **Path:** identifies a path within the authority's space, such as `/docs/java/index.html`. A path is not necessarily a physical file path on the server; it can be routed to a controller/handler.
- **Query:** the part after `?`, such as `lang=vi&mode=short`. The key/value pair format joined by `&` is **a common web convention**, not a requirement that every URI query must follow. The server decides the meaning of the query.
- **Fragment:** the part after `#`, such as `install`. It identifies a part or position within a resource representation; for standard HTTP, **the fragment is not sent in the request-target to the server**.
- **User info:** an optional part of the authority; many modern APIs do not use it, and embedding credentials in a URL should be avoided.

### Same URL, Different Layers May Handle Different Parts

When opening `https://docs.example.org/guide?lang=vi#install`, the browser uses the host to find the endpoint, communicates over HTTPS, and requests the resource corresponding to the path + query. The fragment `install` is typically handled on the client to navigate within the received content. Conceptually, the HTTP/1.1 request looks like:

```http
GET /guide?lang=vi HTTP/1.1
Host: docs.example.org
Accept: text/html

```

The request line **does not contain** `#install`. In practice, HTTP/2 and HTTP/3 represent messages differently from HTTP/1.1, but the fragment is still not part of the request-target sent over HTTP.

**Do not equate a URL with a single response:** the same URL can return HTML/JSON, different languages, or different data depending on the `Accept` header, user permissions, time, or server state. A URI identifies a resource; the response is a **representation** at a given time/context.

## 4. Absolute URIs, Relative References, and Resolution

An **absolute URI** has a scheme, such as `https://docs.example.org/guide`. A **relative reference** such as `chapter/1` or `../intro.html` relies on a **base URI** to form the final target. This mechanism appears in HTML links, API links, static resources, and document processing.

Suppose the base is `https://docs.example.org/guides/java/`:

| Reference | Result When Resolved Against Base | Why |
|---|---|---|
| `../intro.html` | `https://docs.example.org/guides/intro.html` | `..` moves up one path level |
| `examples/demo.html` | `https://docs.example.org/guides/java/examples/demo.html` | Appended under the current directory |
| `/about` | `https://docs.example.org/about` | Path starts from the root of the authority |
| `?lang=vi` | May replace the query based on the current path; need to check the semantics of the API being used | Query-only references have their own resolution rules, not “string concatenation” |
| `https://another.example.org/start` | `https://another.example.org/start` | Reference already has a scheme, does not inherit the base's host |

**A technical note in Java:** `URI.resolve` follows the implementation rules of `java.net.URI`; for special reference forms (especially query-only), do not assume intuitive string concatenation logic. When building critical requests, inspect the resulting URI using `getScheme()`, `getHost()`, `getRawPath()`, `getRawQuery()`, and test your application's edge cases.

### Do Not Concatenate URIs with Arbitrary String Addition

For example, base `https://api.example.org/v1` and path `users`:

- Direct string concatenation can produce `https://api.example.org/v1users`.
- If the base is `https://api.example.org/v1` (without a trailing `/`), resolving the relative reference `users` may replace the `v1` segment, producing `https://api.example.org/users`.
- If the target is the `/v1/` directory, the base should be explicitly defined as `https://api.example.org/v1/`; then resolving `users` will yield `https://api.example.org/v1/users`.

The trailing slash in a base URI **is significant**. `URI.normalize()` helps process `.` and `..` segments in the path, but it does not “know” which business route is correct; nor is it a security filter for untrusted input.

## 5. URI and URL in the Java Standard Library

The two familiar classes are `java.net.URI` and `java.net.URL`. They solve different tasks:

| `java.net.URI` | `java.net.URL` |
|---|---|
| Represents and manipulates **URI identification/syntax** | Represents a URL with a scheme/protocol supported by the runtime |
| Can hold relative references or schemes like `urn` | Suitable when passing to APIs that operate on URLs/connections |
| Has `parse/create`, `resolve`, `normalize`, `getScheme`, `getHost`, `getPath`, `getRawQuery`, `getFragment` | Has `getProtocol`, `getHost`, `getPort`, and connection APIs like `openConnection` |
| Creating/parsing a `URI` **does not trigger network access** | Creating/converting a `URL` does not download the resource; **opening a connection/reading data** is what can cause I/O |
| `equals/hashCode` are defined based on URI syntax (with certain normalization comparison rules) | `URL.equals/hashCode` has historical behavior that may involve host resolution, making it unsuitable as a stable web identifier key |

In modern Java code, you usually **keep `URI` for parsing, validating, storing, and passing to the HTTP client**. When a `URL` is needed for legacy APIs, convert from a valid URI via `uri.toURL()`. For the modern HTTP client (Java 11+), `java.net.http.HttpRequest` accepts a `URI`; there is no need to convert to `URL`.

**Three different operations:**

1. `URI.create("https://example.org/a")`: creates an object and checks syntax (invalid syntax throws an error), sends no network request.
2. `uri.toURL()`: converts to a URL if valid and the protocol is supported; this operation itself downloads no content.
3. `HttpClient.send(...)` or `URL.openStream()`: performs communication/reads data; may encounter DNS failure, connection refused, timeout, TLS errors, error HTTP status codes…

A syntactically valid URI does not guarantee an accessible URL. In particular, `URI.create("urn:isbn:...")` is a valid URI, but it cannot be treated as an HTTP URL and sent directly using `HttpClient`.

## 6. Java 17+: Complete Example, Running Completely Offline

The following program only creates, resolves, and parses URIs/URLs; **it does not connect to the Internet**. This helps clearly see the boundary between identification and access.

Create the file **`UriUrlDemo.java`**:

```java
import java.net.URI;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

public class UriUrlDemo {
    public static void main(String[] args) throws Exception {
        URI base = URI.create("https://docs.example.org/guides/java/");
        URI relative = URI.create("../intro.html?lang=vi#toc");
        URI resolved = base.resolve(relative).normalize();

        System.out.println("Relative absolute: " + relative.isAbsolute());
        System.out.println("Resolved: " + resolved);
        System.out.println("Scheme: " + resolved.getScheme());
        System.out.println("Host: " + resolved.getHost());
        System.out.println("Path: " + resolved.getPath());
        System.out.println("Query: " + resolved.getQuery());
        System.out.println("Fragment: " + resolved.getFragment());

        URI urn = URI.create("urn:isbn:9780134685991");
        System.out.println("URN absolute: " + urn.isAbsolute());
        System.out.println("URN opaque: " + urn.isOpaque());

        URL url = resolved.toURL(); // type conversion only, does not open a connection
        System.out.println("URL protocol: " + url.getProtocol());

        URI escaped = URI.create(
                "https://docs.example.org/search?q=caf%C3%A9%20Java");
        System.out.println("Raw query: " + escaped.getRawQuery());
        System.out.println("Decoded query: " + escaped.getQuery());

        String encodedFormValue = URLEncoder.encode(
                "cà phê", StandardCharsets.UTF_8);
        System.out.println("Form value: " + encodedFormValue);
    }
}
```

Run with JDK 17 or newer:

```bash
javac -encoding UTF-8 UriUrlDemo.java
java UriUrlDemo
```

Output:

```text
Relative absolute: false
Resolved: https://docs.example.org/guides/intro.html?lang=vi#toc
Scheme: https
Host: docs.example.org
Path: /guides/intro.html
Query: lang=vi
Fragment: toc
URN absolute: true
URN opaque: true
URL protocol: https
Raw query: q=caf%C3%A9%20Java
Decoded query: q=café Java
Form value: c%C3%A0+ph%C3%AA
```

**Part-by-part explanation:**

- `relative.isAbsolute()` is `false` because the reference `../intro.html?lang=vi#toc` does not have a scheme yet.
- `base.resolve(relative)` resolves `..` relative to the base's path, resulting in an absolute HTTPS URI. `normalize()` processes any remaining `.`, `..` path segments according to URI semantics.
- `getScheme()` returns `https`; `getHost()` returns the host in the authority; `getPath()` is the path (without query/fragment).
- `getFragment()` is `toc`. It exists in the URI processed by the client, not as part of the standard HTTP request-target.
- `urn.isAbsolute()` is `true` because it has the `urn:` scheme; `urn.isOpaque()` is `true` because it is a non-hierarchical URI according to the Java API. “Absolute” **does not** mean “web URL”.
- `toURL()` creates the corresponding URL object, **does not download** `intro.html`.
- `getRawQuery()` preserves percent-encoding, while `getQuery()` returns the decoded string. Therefore, the raw and decoded query values differ even when only one resource is identified.
- `URLEncoder` serves the `application/x-www-form-urlencoded` rules for **form/query values**: spaces become `+`, UTF-8 characters are represented using percent-encoding. Do not use `URLEncoder` output for an entire URL or an entire path.

### When Does Network Access Actually Occur?

The next example is **integration demonstration code**, not part of the offline program above; it requires an endpoint that actually exists and allows the client to access it.

```java
// Inside a method that can throw IOException,
// InterruptedException; uri must be an accessible HTTP(S) URI.
java.net.http.HttpClient client =
        java.net.http.HttpClient.newHttpClient();
java.net.http.HttpRequest request =
        java.net.http.HttpRequest.newBuilder(uri).GET().build();
java.net.http.HttpResponse<String> response = client.send(
        request,
        java.net.http.HttpResponse.BodyHandlers.ofString());
int status = response.statusCode();
String body = response.body();
```

Here, `newBuilder(uri)` describes the request; `client.send(...)` is the operation that performs network communication. Typically, timeouts, error handling, authentication, and resource limits need to be configured depending on the application. The service may return `404`/`401`/`500`; having a syntactically valid URI does not prevent those outcomes.

## 7. Encoding: The Boundary Between the Displayed String and the Transmitted String

A URI has restricted syntax for reserved characters such as `/`, `?`, `#`, `&`, `=`, `%`. When data contains spaces or Unicode characters, it must be encoded properly for the **component** being constructed.

**Percent encoding** represents a byte as `%HH` (hex). For example, the character `é` in UTF-8 becomes the bytes `C3 A9`, written in a URI as `%C3%A9`. In a query, `q=caf%C3%A9%20Java` has raw text different from the decoded value `q=café Java`.

| What You Want to Do | Recommended Approach |
|---|---|
| Read the verbatim encoded component | `getRawPath()`, `getRawQuery()`, `getRawFragment()` |
| Get the value already decoded by Java | `getPath()`, `getQuery()`, `getFragment()` |
| Create a URI from **unencoded** components | Consider the multi-argument constructor `new URI(scheme, userInfo, host, port, path, query, fragment)` or a reliable URI builder |
| Encode a **form value** | `URLEncoder.encode(value, UTF_8)`; only then assemble according to the corresponding form/query rules |
| Encode an entire URL with `URLEncoder` | **Wrong purpose:** it can turn `:`, `/`, `?`, `&` of the URI structure into form data |

**Two very common mistakes:**

1. **Double encoding:** data that already has `%20` gets encoded again into `%2520` because `%` turns into `%25`. Avoid mixing “already-encoded strings” with “unencoded component values”; choose one URI building API and a consistent input convention.
2. **Confusing query and path encoding:** in form encoding, spaces use `+`; in a URI path, spaces typically use `%20`. Do not use `URLEncoder` to build a path segment and then assume every server will decode `+` as a space.

Also remember that `getQuery()` returns **the entire decoded query**, without automatically splitting key/value pairs. If data contains `&`, `=`, or percent-encoding, naively calling `split("&")`/`split("=")` can lose information. Use a parser or library that conforms to the query/form standard required by your application.

## 8. Distinguishing Resource Identity from Representation and Execution Endpoint

In an API, `https://api.example.org/orders/42` is a URL that can be used to identify the resource “order 42”. However:

- `GET /orders/42` may read a representation of the resource, such as JSON.
- `PUT /orders/42` may request replacing the resource's state according to the API contract.
- `DELETE /orders/42` may request deleting the resource.
- The same URL can be handled differently depending on the **HTTP method** and user permissions; the URL itself does not contain all business semantics.
- If the server returns a `301`/`302`/`307`/`308` redirect, the subsequent access path may differ from the original address; this still does not mean the original URL “is not a URL”.

**The URL determines where/how the client attempts to communicate; the API contract determines the supported operations and returned content.** Knowing whether an endpoint is actually reachable requires runtime conditions: DNS, routing, TCP/QUIC, TLS, access permissions, service status, and HTTP response. That is a different matter from parsing a URI/URL string.

When designing, prioritize stable canonical URIs and limit arbitrary identifier changes; if a location needs to change, use redirects or an appropriate address discovery mechanism. However, do not assume a URL will exist forever, or that the same URL will always return the exact same content bytes.

## 9. Validation and Security When Receiving External URIs/URLs

A string can be **syntactically valid as a URI** while still being **invalid according to application policy**. For example, an application is only allowed to call HTTPS to `api.example.org`; in that case, you must validate the scheme, host, port, path, and actual target before sending the request.

Practical principles:

1. **Parse first, check each component:** use `URI` and then check `getScheme()`, `getHost()`, `getPort()`; do not just compare `startsWith("https://api.example.org")` because `https://api.example.org.attacker.invalid` still has the same prefix.
2. **Separate data from URI structure:** encode data in the right component; do not insert unchecked input into `host`, `path`, or `query` strings.
3. **Do not assume normalization is a security check:** dot segments, percent-encoding, encoded slashes, and how proxies/servers interpret paths can differ. Security checks must be aligned with the exact component that will process the request.
4. **Watch out for redirects and DNS:** validating the initial URL is not enough if the HTTP client automatically follows redirects to another host; for sensitive tasks, you must control each destination after redirection and network resolution results to prevent SSRF.
5. **Do not put secrets in URIs:** URLs often appear in history, logs, monitoring, analytics, referers, or error messages. Avoid placing sensitive passwords/tokens in the path/query if suitable alternatives exist.
6. **Set timeouts and handle errors by layer:** URI parse errors, DNS errors, connection/TLS errors, and HTTP status errors are different types of failures; do not lump them all together as “bad URL”.

This is why **“valid URI”**, **“allowed URL”**, and **“successful request”** are three distinct checks.

## 10. Common Mistakes and Accurate Explanations

| Misconception | Accurate Understanding |
|---|---|
| “A URI is a URL without a domain.” | URI is the overarching concept; an HTTPS URI can contain a domain and simultaneously be a URL. |
| “Every URI can be called over HTTP.” | `urn:`, `mailto:`, and relative references are not HTTP(S) endpoints on their own. |
| “A URL differs from a URI because a URL can be called while a URI cannot.” | A URL is a URI for location/access; actual connectivity also depends on infrastructure, permissions, and service state. |
| “`/api/users` is an absolute URI because it starts with `/`.” | It is an absolute path within an authority, but according to `URI.isAbsolute()` it is not absolute because it has no scheme. |
| “Fragment `#intro` is sent to the server for routing.” | Standard HTTP request-targets do not send fragments; the client typically handles the fragment itself. |
| “`new URL(...)` or `uri.toURL()` automatically downloads data.” | Creating/converting an object does not send an HTTP request; I/O occurs when opening a connection and reading/sending data. |
| “Simply concatenating `base + path` or `URLEncoder` on the whole string is right.” | Relative references must be resolved according to rules and each component encoded separately. |
| “A string passing `URI.create` is safe.” | Syntactic validity says nothing about access policies, SSRF, auth, or whether the resource exists. |

## 11. Self-Check Exercises

1. **Is `https://example.org/a?x=1#top` a URI or a URL?** Both. It is an absolute URI with the HTTPS scheme and has location information, so it is commonly called a URL. The fragment `top` is not included in the HTTP request-target.
2. **Does `urn:isbn:9780134685991` have `isAbsolute()==true`? Can it be opened with `HttpClient` right away?** It has the `urn:` scheme so it is absolute, but it is not an HTTP(S) endpoint for `HttpClient` to send a request to.
3. **What does Base `https://example.org/docs/java/` + `../overview.html` become?** `https://example.org/docs/overview.html`. Because `..` steps back to the `/docs/` directory.
4. **If `URI.create(urlString)` does not report an error, is downloading the resource guaranteed to succeed?** No. DNS/connectivity/security/permissions/an active server and an appropriate response are required.
5. **How do `getQuery()` and `getRawQuery()` differ?** The former is the percent-decoded form according to the URI API, while the latter keeps the raw text. To parse form parameters, you also need the rules of the query format being used.
6. **Why is `https://api.example.org.attacker.invalid` dangerous if using `startsWith("https://api.example.org")`?** The string has the same prefix, but the host is a different domain; you must parse first, then compare the host component exactly, and control redirects/actual network destinations.

## 12. Takeaways to Apply

- **URI = resource identifier. URL = a case of URI describing access mechanism/location**; they have a subset relationship, not an opposing one.
- **Resource name is distinct from transport path and access state.** A syntactically valid URI does not guarantee an endpoint, permissions, or a successful response.
- **In Java, prefer `URI` to parse, resolve, normalize, and validate;** only convert to `URL` when an API requires it. `HttpClient` accepts `URI` to actually send HTTP(S).
- **Resolution and encoding depend on the component.** A trailing `/` on the base, `?query`, `#fragment`, and percent-encoding all have their own semantics; avoid uncontrolled string concatenation.
- **Checking accessibility is a runtime and security concern.** Correct URI parsing is only the first step when building a reliable client–server application.

References: *RFC 3986 – Uniform Resource Identifier (URI): Generic Syntax*; JDK API `java.net.URI`, `java.net.URL`, `java.net.http.HttpClient`.