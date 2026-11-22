# Converting URI to URL; Legacy URL Constructors and Usage Guidelines by Java Version

## 1. When Should You Convert `URI` to `URL`?

In `java.net`, **`URI` (Uniform Resource Identifier)** represents the syntax for identifying a resource; **`URL` (Uniform Resource Locator)** is additionally tied to a mechanism for accessing the resource through a *protocol handler*. Therefore, not every `URI` can be turned into a `URL`.

- A `URI` can be **relative**, such as `docs/intro.html`, or **absolute**, such as `https://example.com/docs/intro.html`. An absolute URI has a `scheme`; a relative URI does not.
- A `URI` can be an **opaque URI** such as `urn:example:widget`; Java can still parse the URI syntax, but there is usually no `URLStreamHandler` for that scheme.
- A `URL` must have a protocol recognized by Java through a handler. Legacy ways of creating a URL from a string may process or validate data inconsistently depending on the handler and are **not a complete URI validator**.
- Creating a `URI` or calling `URI.toURL()` **does not fetch the web page by itself**; network activity happens when you call an API to open a connection, send an HTTP request, or read data. Certain other operations on `URL` (especially `equals`/`hashCode`) may trigger hostname resolution.

**Recommended workflow:** accept/compose the URL as a `URI` → validate syntax, scheme, and authority as needed → resolve relative paths if any → **only call `toURL()` at the boundary of an API that actually requires `URL`**.

```text
URL string / components
       |
       v
  new URI(...) or URI.create(...)
       |
       +--> validate scheme / host / userinfo / path
       +--> baseUri.resolve(relativeUri), if needed
       |
       v
  absolute URI with an appropriate protocol handler
       |
       v
       uri.toURL() --------------------> URL
                                            |
                                            +--> legacy API requiring URL/URLConnection
                                            +--> openStream(), connect... if I/O is actually needed
```

For HTTP in Java 11 and later, `java.net.http.HttpRequest.newBuilder(URI)` accepts **`URI` directly**; many applications do not need to convert to `URL`.

## 2. Guidelines by Java Version

| Environment | API Status | Usage Guidelines |
| --- | --- | --- |
| Java 8–19, including **Java 17** | Traditional `new URL(...)` constructors are still used and **have not been marked deprecated** in the API of these versions. `URI.toURL()` has existed for a long time. | For new code, prefer `URI` and `uri.toURL()` to proactively parse and validate URIs; keep legacy constructors when compatibility is needed and migration is not yet possible. |
| **Java 20** | All **public constructors** of `java.net.URL` are annotated with `@Deprecated(since="20")`. Java 20 adds `URL.of(URI, URLStreamHandler)`. | Avoid writing new `new URL(...)` calls; use `URI.toURL()` for standard cases, and consider `URL.of(...)` when a custom handler must be specified. |
| **Java 21 and later** | Guidance from Java 20 still applies: legacy constructors remain marked deprecated in modern JDKs. | Continue using `URI` as the standard input; resolve deprecation warnings by replacing the URL creation mechanism while testing for differences in parsing/encoding. |

**Deprecated ≠ removed:** a deprecated constructor can still compile and run, but new code should not rely on it. Do not claim that all `URL` constructors have been removed from JDK 20/21; the main change is the warning and the replacement direction. Also, **do not call `URL.of(...)` in a project built with `--release 17`**, as this API only appeared in Java 20.

In Java 20+, `URL.of(uri, null)` uses the default handler if available, but `uri.toURL()` remains the standard path and is compatible with Java 17. `URL.of(uri, customHandler)` is for custom handler needs, not a mandatory step for every conversion.

## 3. Complete Example: Parse, Compose, Resolve, Then Convert to URL (Java 17+)

**`UriToUrlDemo.java`**

```java
import java.net.MalformedURLException;
import java.net.URI;
import java.net.URISyntaxException;
import java.net.URL;

public final class UriToUrlDemo {
    public static void main(String[] args)
            throws URISyntaxException, MalformedURLException {

        // 1. String with spaces already encoded as %20.
        URI parsed =
                new URI("https://example.com/a%20b?q=java%20networking");
        URL fromParsed = parsed.toURL();

        System.out.println("parsed: " + fromParsed);
        System.out.println("host: " + parsed.getHost());
        System.out.println("raw query: " + parsed.getRawQuery());
        System.out.println("decoded query: " + parsed.getQuery());

        // 2. Compose components; the URI constructor automatically quotes
        // invalid characters (such as spaces in the path/query).
        URI composed = new URI("https", null, "example.com", 443,
                "/learn/java basics", "lang=vi VN", null);
        System.out.println("composed: " + composed.toURL());

        // 3. A relative URI can only be converted after resolving
        // against an absolute base URI.
        URI relative = URI.create("guide/intro.html");
        URI base = URI.create("https://example.com/docs/");
        System.out.println("resolved: " + base.resolve(relative).toURL());

        // 4. Validate the authority against server host/port syntax.
        URI strict = new URI("https://example.com:8443/health")
                .parseServerAuthority();
        System.out.println("server host: " + strict.getHost());

        // 5. Distinguish between three error categories.
        try {
            relative.toURL();
        } catch (IllegalArgumentException e) {
            System.out.println("relative URI: rejected");
        }

        try {
            new URI("https://example.com/a b");
        } catch (URISyntaxException e) {
            System.out.println("raw space: rejected");
        }

        try {
            URI.create("urn:example:widget").toURL();
        } catch (MalformedURLException e) {
            System.out.println("unsupported scheme: rejected");
        }
    }
}
```

Compile/run (this example does not access the network):

```bash
javac --release 17 UriToUrlDemo.java
java UriToUrlDemo
```

Output on a standard JDK (without an application-installed handler for the `urn` scheme):

```text
parsed: https://example.com/a%20b?q=java%20networking
host: example.com
raw query: q=java%20networking
decoded query: q=java networking
composed: https://example.com:443/learn/java%20basics?lang=vi%20VN
resolved: https://example.com/docs/guide/intro.html
server host: example.com
relative URI: rejected
raw space: rejected
unsupported scheme: rejected
```

Key takeaways:

1. `new URI("https://example.com/a%20b?...")` parses a complete URI string. `%20` is already a valid escape sequence, so it is preserved in its raw form.
2. `getRawQuery()` preserves `%20`; `getQuery()` returns the decoded content. If you need to send it as-is, do not take the decoded value and concatenate strings manually.
3. The multi-component constructor `new URI(scheme, userInfo, host, port, path, query, fragment)` quotes **invalid characters** such as spaces. This is safer than manually inserting spaces into a raw URL.
4. `resolve` resolves the path relative to the base URL. The trailing `/` in `https://example.com/docs/` makes it clear that this is a base directory for appending `guide/intro.html`.
5. `parseServerAuthority()` verifies that the authority can be parsed into host/port/userInfo according to server syntax; it **does not verify that the server actually exists**, does not check access permissions, and does not replace security policies.
6. `toURL()` requires an absolute URI. An absolute URI like `urn:...` can still fail because there is no corresponding protocol handler.

## 4. Migrating Legacy URL Constructors to URI by Scenario

Below are **reference snippets for migration** (not a standalone Java class). For examples using `new URI(...)`, the enclosing method must handle `URISyntaxException`; `toURL()` conversions must handle `MalformedURLException`.

| Legacy API | Original Intent | Recommended Replacement |
| --- | --- | --- |
| `new URL(String spec)` | Parse a complete URL from a string | `new URI(spec).toURL()` or `URI.create(spec).toURL()` when the string is trusted to be valid |
| `new URL(String protocol, String host, String file)` | Combine protocol + host + path/file | Create `new URI(scheme, null, host, -1, path, query, fragment)` then `toURL()` |
| `new URL(String protocol, String host, int port, String file)` | Combine host and port | `new URI(scheme, null, host, port, path, query, fragment).toURL()` |
| `new URL(URL context, String spec)` | Resolve a relative URL | `baseUri.resolve(relativeUri).toURL()` |
| Constructors with a `URLStreamHandler` parameter | Specify a handler for the protocol | Java 20+: `URL.of(uri, handler)`; if Java 17 is required, see the separate compatibility guidance below |

### 4.1. Complete URL

**Before (legacy; produces warnings starting in Java 20):**

```java
URL endpoint = new URL("https://example.com/search?q=java%20uri");
```

**After (Java 17+):**

```java
URI endpointUri =
        new URI("https://example.com/search?q=java%20uri");
URL endpoint = endpointUri.toURL();
```

When input is user-supplied, `new URI(rawInput)` lets the application handle **`URISyntaxException` explicitly**. `URI.create(rawInput)` is a shorthand for constants or already-validated input: if the syntax is invalid, it throws `IllegalArgumentException` (wrapping the underlying `URISyntaxException`).

### 4.2. Scheme/Host/Port/Path/Query Components

**Before:**

```java
URL endpoint = new URL(
        "https", "example.com", 8443, "/api/items?name=java%20net");
```

**After (Java 17+):**

```java
URI endpointUri = new URI(
        "https",          // scheme
        null,             // userInfo
        "example.com",    // host
        8443,             // port
        "/api/items",     // path
        "name=java net",  // query (unencoded component)
        null              // fragment
);
URL endpoint = endpointUri.toURL();
```

**Beware of double encoding:** the component-based constructor expects *unescaped* characters; passing `"name=java%20net"` into the component `query` parameter can cause `%` to be quoted as `%25`, producing `java%2520net`. Conversely, when using `new URI(fullString)`, the full string must already have valid escaping. Choose **one** consistent encoding approach.

Do not assume the URI constructor will automatically encode every special character in **query parameter values**: `&` and `=` are delimiter characters in a query and may be preserved as-is. If an input is an arbitrary value containing `&`, `+`, or `=`, use an appropriate encoder for the value part according to the expected query format to avoid manual concatenation altering semantics. `URLEncoder`/`URLDecoder` is for *form encoding* (`application/x-www-form-urlencoded`), not a general-purpose full-URI encoder/decoder.

### 4.3. Relative URL Based on a Base URL

**Before:**

```java
URL baseUrl = new URL("https://example.com/docs/");
URL chapter = new URL(baseUrl, "chapter-2.html");
```

**After (Java 17+):**

```java
URI baseUri = URI.create("https://example.com/docs/");
URI chapterUri = baseUri.resolve("chapter-2.html");
URL chapter = chapterUri.toURL();
```

When `baseUri` is `https://example.com/docs/index.html`, `resolve("chapter-2.html")` also produces `https://example.com/docs/chapter-2.html`, because it replaces the last segment of the file path. However, with a base of `https://example.com/docs` **without a trailing slash**, `docs` is treated as a file segment and the result becomes `https://example.com/chapter-2.html`. That is standard URI resolution behavior, not a `toURL()` bug.

### 4.4. URLs Referring to Local Files

**Avoid** creating `file:` URLs by concatenating OS file path strings, because Windows uses `\` and filenames may contain spaces or Unicode characters.

```java
import java.nio.file.Path;
import java.net.URL;

// Inside a method that handles MalformedURLException:
Path report = Path.of("reports", "bao cao.txt").toAbsolutePath();
URL fileUrl = report.toUri().toURL();
```

`Path.toUri()` creates a file URI appropriate for the running environment; `toURL()` only converts the representation and **does not guarantee the file exists**. Starting in Java 20, this approach also avoids deprecated `URL` constructors.

## 5. Differences Between Exceptions

| Scenario | API | Primary Exception | Solution |
| --- | --- | --- | --- |
| Malformed URI string, such as raw spaces | `new URI(raw)` | `URISyntaxException` (checked) | Validate input source / escape properly |
| Malformed URI string when using convenience factory | `URI.create(raw)` | `IllegalArgumentException` (unchecked) | Use only with constants or already-validated input |
| Relative URI such as `"guide.html"` | `relative.toURL()` | `IllegalArgumentException` | `base.resolve(relative).toURL()` |
| Absolute URI with a scheme that has no URL handler | `uri.toURL()` | `MalformedURLException` (checked) | Convert only supported / actually needed protocols |
| Legacy URL created with ambiguous structure | `new URL(...)` | Possibly `MalformedURLException`, but validation depends on handler | Parse with `URI`, check authority/scheme, then convert |
| Converting a legacy URL back to URI | `url.toURI()` | `URISyntaxException` (checked) | Handle non-standard URLs created by legacy APIs |

**Do not conflate the two error categories:** `URI.toURL()` can throw both `IllegalArgumentException` (non-absolute URI) and `MalformedURLException` (unsupported scheme / rejected by handler). Simply using `catch (MalformedURLException)` **will not** catch a relative URI.

A successfully constructed `URL` does not prove the endpoint is reachable: DNS, TLS, HTTP status, and I/O are subsequent runtime steps.

## 6. Java 20+: The `URL.of(URI, URLStreamHandler)` API

Java 20 introduces the following factory method:

```java
public static URL of(URI uri, URLStreamHandler handler)
        throws MalformedURLException
```

- With `handler == null`, Java uses the scheme's default handler (if available); this case behaves similarly to `uri.toURL()`.
- With a custom `handler`, the application can attach a custom protocol handler according to platform rules. An invalid or disallowed handler may cause an error; creating a custom handler is an advanced topic and is unnecessary for standard HTTP/HTTPS.
- **Compiles only on Java 20+**. In libraries that must remain compatible with Java 17, continue using `URI.toURL()` for standard protocols.

**`UrlFactoryDemo.java`** (Java 20+ only):

```java
import java.net.URI;
import java.net.URL;

public final class UrlFactoryDemo {
    public static void main(String[] args) throws Exception {
        URI uri = URI.create("https://example.com/v1");
        URL url = URL.of(uri, null);
        System.out.println("factory: " + url);
    }
}
```

```bash
javac --release 20 UrlFactoryDemo.java
java UrlFactoryDemo
```

```text
factory: https://example.com/v1
```

Do not confuse `URL.of(uri, handler)` with `URI.of(...)`: **Java 17 does not have a `URL.of(...)` method**, whereas `URI.create(...)`/`new URI(...)` is the common choice across versions.

## 7. Keep `URI` Until `URL` Is Actually Needed

### 7.1. Modern HTTP Clients Accept `URI` Directly

In Java 11+ (including Java 17+), the `java.net.http.HttpRequest` API allows configuring a URI directly:

```java
import java.net.URI;
import java.net.http.HttpRequest;

// Request configuration snippet; does not send HTTP yet.
URI endpoint = URI.create("https://example.com/api/items");
HttpRequest request = HttpRequest.newBuilder(endpoint).GET().build();
```

There is no need to create an intermediate `URL`. Calling `HttpClient.send(...)` or `sendAsync(...)` is what triggers the HTTP operation; the API and connection policies belong to the HTTP client layer.

### 7.2. `URI` Is Suitable for Comparison, Map Keys, or Path Normalization

`URI.equals`/`hashCode` compares based on URI content according to the rules of the `URI` class, without performing DNS lookups. In contrast, `URL.equals`/`hashCode` may depend on the host's IP address, causing lookups and performance/stability issues. Therefore:

- Keep `URI` for identifiers, configuration, and keys in collections.
- Use `uri.normalize()` to resolve `.`/`..` segments if those are the semantics you need; do not assume `normalize` solves all canonicalization or security issues.
- Convert to `URL` when a legacy library requires a `URL` parameter or when the `URLConnection` API is needed.

In particular, `URI.toString()`, `URI.toASCIIString()`, `getRawPath()`, and `getPath()` **are not completely equivalent**: `getPath` returns the decoded form, `getRawPath` preserves percent-escaped `%` sequences, and `toASCIIString` may escape non-ASCII characters. Avoid decoding and re-encoding arbitrarily.

## 8. Validate Input Before Using External URLs

`new URI(raw)` validates general URI syntax; `parseServerAuthority()` enforces hostname/port parsing. For applications that only allow HTTP/HTTPS, you also need specific policies for scheme, hostname, userInfo, and port.

Example **in-class snippet** (Java 17+, method declaring checked exceptions):

```java
import java.net.MalformedURLException;
import java.net.URI;
import java.net.URISyntaxException;
import java.net.URL;

static URL requireHttpUrl(String raw)
        throws URISyntaxException, MalformedURLException {
    URI uri = new URI(raw).parseServerAuthority();
    String scheme = uri.getScheme();

    if (scheme == null
            || !(scheme.equalsIgnoreCase("http")
                 || scheme.equalsIgnoreCase("https"))
            || uri.isOpaque()
            || uri.getHost() == null
            || uri.getUserInfo() != null
            || (uri.getPort() != -1
                && (uri.getPort() < 1 || uri.getPort() > 65535))) {
        throw new IllegalArgumentException("Invalid HTTP(S) endpoint");
    }
    return uri.toURL();
}
```

This is **only a minimal syntax and policy filter**, not a complete SSRF prevention solution. For untrusted URLs, you also need to control DNS and resolved target IPs, redirects, proxies, network boundaries, timeouts, TLS, and cases where DNS results change between validation and connection.

**Common migration mistakes:**

1. Blindly replacing `new URL(raw)` with `URI.create(raw).toURL()` without reviewing exception handling: a malformed URI can change from `MalformedURLException` to `IllegalArgumentException`.
2. Calling `toURL()` on a relative URI, or assuming **having any scheme means the URL is usable**.
3. Manually concatenating strings containing spaces, `#`, `?`, `&`, or existing percent-encoding, leading to broken paths or queries.
4. Using `new URL(base, child)` on JDK 20+ when `URI.resolve(child)` is all that is needed.
5. Assuming an API marked `@Deprecated` has disappeared from the runtime, or using `URL.of` in a project still targeting `--release 17`.
6. Assuming `URL` is required for modern HTTP clients or using `URL.equals` as a cheap, pure comparison.

## 9. Exercises and Application Checklist

1. Given `https://example.com/docs/` and `quick-start.html`, create the `URL` of the child page **without using a `URL` constructor**.
2. Explain why `URI.create("/docs/quick-start.html").toURL()` throws `IllegalArgumentException` even though the URI is syntactically valid.
3. Explain the difference between `new URI("https://example.com/a b")` and `new URI("https", null, "example.com", -1, "/a b", null, null)`.
4. A Java 17 project needs to build and run immediately; should `new URL(...)` be replaced with `URL.of(uri, null)`?
5. Does a modern HTTP service using `HttpRequest.newBuilder(URI)` need to convert `URI` to `URL` first?

**Suggested answers:** (1) `URI.create("https://example.com/docs/").resolve("quick-start.html").toURL()`; (2) this is a **relative** URI without a scheme; (3) the single-string constructor rejects raw spaces, while the component-based constructor quotes spaces as `%20`; (4) no, `URL.of` is only available starting in Java 20, so use `uri.toURL()`; (5) no, because `HttpRequest` already accepts `URI`.

**Migration takeaway:** construct and process structured URIs first, resolve relative parts, validate application constraints, and then call `toURL()` where integration with legacy APIs is needed. Across Java 17 and Java 20+, this `URI → URL` path keeps code consistent in design and avoids introducing deprecated constructors.

## 10. Official Documentation

- [Java SE 17: `java.net.URI`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html) — constructors, `URI.create`, `parseServerAuthority`, `resolve`, `toURL`.
- [Java SE 17: `java.net.URL`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URL.html) — legacy URL prior to the deprecation change.
- [Java SE 20: `java.net.URL`](https://docs.oracle.com/en/java/javase/20/docs/api/java.base/java/net/URL.html) — `@Deprecated(since="20")`, `URL.of(URI, URLStreamHandler)`, and migration guidance.
- [JDK 20 Release Notes](https://www.oracle.com/java/technologies/javase/20-relnote-issues.html) — confirmation of URL constructor deprecation.
- [Java SE 17: `java.net.http.HttpRequest`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html) — building HTTP requests from a URI.
