# URI/URL Structure: scheme, authority, host, port, path, query, and fragment

## 1. Objectives and Scope

In Java network programming, an address like `https://example.org:8443/docs?id=7#intro` is not just an arbitrary string: the `:`, `//`, `/`, `?`, and `#` characters serve to delimit its components. Understanding the structure correctly helps you build URLs safely, route requests, encode Unicode, handle relative links, and avoid confusing query with fragment.

After this lesson, you will be able to:

- Parse a URI into **scheme, authority, user-info, host, port, path, query, fragment** and recognize which components are absent.
- Distinguish **URI** (an identifier/reference for a resource using a general syntax) from **URL** (a URI that provides a way to locate/access a resource according to a scheme); know when to use `java.net.URI` and `java.net.URL`.
- Use `getRaw...()` and `get...()` properly; understand that `%20`, `+`, `?`, and `#` are not equivalent.
- Construct, resolve, and normalize URIs in Java 17+ without arbitrary string concatenation.
- Identify common pitfalls regarding default ports, IPv6, query parameters, relative references, and untrusted input data.

**Scope limitation:** here we read and construct *addresses*. Details about HTTP request bodies, TCP sockets, DNS, or server implementations belong to other layers. In particular, **parsing a `URI` does not perform any network connection by itself**.

## 2. Overall Diagram of a Hierarchical URI

Running example:

~~~text
https://reader@example.org:8443/docs/java%20networking?lang=vi&tag=uri#basics
└─┬─┘  └───────────┬───────────┘└───────────┬──────────┘└──────┬──────┘└──┬──┘
scheme         authority                path               query         fragment
                │
            reader@example.org:8443
              │       │         │
           user-info  host      port
~~~

General structure (simplified for common hierarchical URIs):

~~~text
scheme ":" "//" authority path [ "?" query ] [ "#" fragment ]
                 │
               [userinfo "@"] host [":" port]
~~~

Not every URI contains all parts. For example, `mailto:team@example.org` is an **opaque URI**: it has the `mailto` scheme, but no authority/host/path like a hierarchical HTTP URL. A relative reference such as `../images/logo.png` has a path but no scheme.

| Component | Part taken from the example | Meaning |
| --- | --- | --- |
| **scheme** | `https` | Syntax/usage convention for the resource; precedes the first colon |
| **authority** | `reader@example.org:8443` | Region describing the naming authority, starting after `//` and ending before path/query/fragment |
| **user-info** | `reader` | Optional part before `@` in the authority; should not contain secrets |
| **host** | `example.org` | Domain name, IPv4, or syntactically valid IPv6 literal |
| **port** | `8443` | Explicit port after the host; may be omitted |
| **path** | `/docs/java%20networking` | Path following the hierarchical structure of the URI |
| **query** | `lang=vi&tag=uri` | String after `?` and before `#`; key/value interpretation is an application convention |
| **fragment** | `basics` | Reference to a location/sub-resource within the resource depending on the scheme/media type context |

The `:` after the scheme, `//` before the authority, `?`, and `#` are **delimiters**. They are not part of the content strings returned by `getScheme()`, `getRawQuery()`, or `getRawFragment()`. Authority is only part of a hierarchical URI when the `//authority` form is present. The path in the example starts with `/`, though not every path does.

## 3. Scheme: How a URI Is Interpreted

The scheme precedes the `:` and typically selects the rules for interpreting the remainder. A scheme name must start with a letter and may continue with letters, digits, `+`, `-`, or `.`. Some examples:

- `https://example.org`: HTTP over TLS under the `https` scheme.
- `http://example.org`: plain HTTP under the `http` scheme.
- `file:///home/user/readme.txt`: a file URI reference; the three slashes `/` reflect an empty authority and an absolute path.
- `mailto:team@example.org`: a mail address under the `mailto` scheme, without an HTTP-style `//host`.
- `urn:isbn:...`: a form of URN identifier, assuming no server.

`URI.getScheme()` returns `null` for a relative reference. To check whether an address is syntactically an absolute URI, check `uri.isAbsolute()`; this **only indicates that a scheme is present**, and does not guarantee that the address has a valid host, is reachable, or uses the HTTP protocol.

Schemes are generally compared case-insensitively according to URI syntax; however, when checking application policies, normalize or compare explicitly such as `"https".equalsIgnoreCase(uri.getScheme())`. Do not infer the scheme merely by checking a string prefix like `startsWith("https")`.

## 4. Authority: user-info, host, and port

### 4.1. Authority is a unit; host is only a part of it

For `https://reader@example.org:8443/docs`:

~~~text
authority = reader@example.org:8443
user-info = reader
host      = example.org
port      = 8443
~~~

An authority usually has the form `[userinfo@]host[:port]` for a **server-based authority**. Never assume the authority string is always equal to the host: the authority may contain `userinfo` and `port`; some URIs also allow a **registry-based authority** from which `getHost()` cannot extract a normal hostname.

In Java:

- `getRawAuthority()` returns the form without decoding percent-encoding, or `null` if there is no authority.
- `getAuthority()` returns the authority string after decoding percent-encoding (if present).
- `getRawUserInfo()` / `getUserInfo()` return the optional user-info.
- `getHost()` returns the host when the URI has a valid server-based authority; it may return `null`, even when `getRawAuthority()` is not `null`.
- `getPort()` returns the explicit port as an `int`; returns `-1` when unspecified.

**Do not use user-info to embed passwords in a URL.** For instance, `https://name:password@example.org/` is easily leaked through logs, history, analytics, error messages, or shared links. Modern HTTP clients do not necessarily accept or use user-info as a valid authentication mechanism.

### 4.2. Host and IPv6

A host can be a domain name (`api.example.org`), IPv4 (`192.0.2.10`), or an IPv6 literal. In a URI string, **an IPv6 literal must be enclosed in square brackets** to distinguish colons inside the address from the port delimiter:

~~~text
https://[2001:db8::1]:8443/health
          └──IPv6───┘ └port┘
~~~

`https://2001:db8::1:8443/` is not an equivalent representation. When working with internationalized Unicode hostnames, apply an appropriate IDN conversion policy (e.g., `IDN.toASCII(...)` for ASCII/punycode form) and validate input; do not insert unverified Unicode names and guess what `getHost()` will return.

`getHost()` **does not perform a DNS lookup**; it only parses the string syntax. A host present in a URI does not prove that the server exists. If an application requires a strict server-based authority, `parseServerAuthority()` can help detect cases where the authority cannot be parsed into user-info/host/port; this method can throw `URISyntaxException`.

### 4.3. Explicit port vs. default port

Compare:

~~~text
https://example.org/docs
https://example.org:443/docs
https://example.org:8443/docs
~~~

- `URI.getPort()` on the first line returns **`-1`**, because the URI does not specify a port; it does not automatically return `443`.
- The second line writes `443` explicitly.
- The third line writes `8443` explicitly.

For HTTPS, port 443 is the default port typically chosen by clients when unspecified; that is a **protocol/client rule**, not a number added automatically by `URI`. When validating a port for actual networking, check the valid port range and application policy. A value of `-1` does not mean a "negative port on the network".

## 5. Path: Path, Segments, `/`, and Dot-Segments

The path typically describes a hierarchical location within a resource:

~~~text
https://example.org/
https://example.org/docs/java
https://example.org/docs/java%20networking
https://example.org/a/b/../c
~~~

Slashes `/` separate path segments. `/` (root) is **different** from an empty path in terms of the URI string, even though an HTTP server may choose to treat them equivalently. A path may also not exist as such in an opaque URI.

`getRawPath()` preserves the percent-encoded form, whereas `getPath()` decodes percent-encoding:

~~~text
raw path     = /docs/java%20networking
decoded path = /docs/java networking
~~~

`%20` is the encoded form of a space byte. **Do not use `java.net.URLDecoder` to decode paths**: `URLDecoder` follows HTML form rules, turning `+` into a space, whereas `+` can be a valid path character. For applications that need to parse segments, note that `%2F` can become `/` when decoded; decoding too early can lose the distinction between an original delimiter and an encoded character. For request signatures, cache keys, or routers, define and consistently maintain the raw/canonical form used by the system.

**Dot-segments** `.` and `..` carry relative path semantics. `URI.normalize()` removes redundant segments like `.` and `..` in hierarchical URIs according to Java's rules; for example, `/a/./b/../c` typically normalizes to `/a/c`. This is a **syntactic** transformation; it does not access the filesystem, does not verify that a resource exists, and does not replace server-side security checks.

## 6. Query: The Part After `?` Is an Application-Convention String

Consider `https://example.org/search?q=java&tag=network&tag=uri#result`:

~~~text
raw query = q=java&tag=network&tag=uri
fragment  = result
~~~

The URI standard only defines a **query string**; it does not require the query to be a key/value map. Using `&` to separate pairs and `=` to separate names/values is very common on the web, but it is an **application/HTTP form convention**, not a feature that `URI.getQuery()` parses automatically. In Java, `URI` does not have `getQueryParameter("q")`.

Things to keep in mind:

1. Parameter names can repeat: `tag=network&tag=uri`. Converting everything into a simple `Map<String,String>` can lose values.
2. Parameter order may matter for signatures, caches, or applications. Do not reorder them unless the protocol specifies it.
3. An empty value (`x=`) is different from a key not being passed; how `x` (without `=`) is handled also depends on the application.
4. `getRawQuery()` retains `%` with its encoding; `getQuery()` decodes percent-encoding, but **does not automatically turn `+` into a space** per form rules. Do not decode the entire query before splitting pairs/values: `%26` could be turned into `&` and then split erroneously.
5. The first `?` delimits the query of a hierarchical URI; reserved characters intended as *data* must be encoded appropriately for the context.

Example with a parameter having the value `C++ & Java` in `application/x-www-form-urlencoded` format:

~~~text
Original value:     C++ & Java
Form-encoded value: C%2B%2B+%26+Java
Query:              q=C%2B%2B+%26+Java
~~~

Here `%2B` is a literal plus sign, `+` represents a space **according to form rules**, and `%26` is the `&` character inside the **value**, not a separator between two parameters. Java's `URLEncoder`/`URLDecoder` are intended for this form format; they are **not** general-purpose encode/decode functions for an entire URI, path, or fragment.

## 7. Fragment: The Part After `#`, Usually for the Client

In `https://example.org/docs?lang=vi#installation`:

- `query` = `lang=vi`.
- `fragment` = `installation`.

A fragment can help a browser jump to a position in HTML or allow a client application to locate a part of a resource by its own convention. When a browser accesses a typical HTTP(S) URL, **the fragment is not included in the HTTP request-target sent to the server**. The server receives the corresponding path/query, while the browser uses the fragment within the document context. Therefore, do not design server features that depend on receiving the fragment via the request URL.

`URI.getRawFragment()` keeps the encoded form; `getFragment()` decodes it. A fragment may be absent (`null`) or written empty in the string. If you want the `#` character to appear in a **query/path value**, you must encode it for the respective component (typically `%23`), otherwise everything after it will be interpreted as the fragment.

Note: a fragment can still appear in history, client-side logs, or JavaScript code. Do not treat the fact that fragments are not sent in the HTTP request-target as an absolute guarantee of secrecy.

## 8. Hierarchical URIs, Opaque URIs, Absolute URIs, and Relative References

Two independent questions should be separated:

- **Absolute or relative?** Is there a scheme or not? `https://example.org/docs` is an absolute URI; `../docs` and `//cdn.example.org/lib.js` are relative references when used with a base URI. A reference starting with `//` has an authority but no scheme.
- **Hierarchical or opaque?** `https://example.org/docs` is hierarchical; `mailto:team@example.org` is opaque according to `java.net.URI` classification. In an opaque URI, the part after `:` is treated as the scheme-specific part rather than being parsed into host/port/path like an HTTP URL.

| Example | Characteristics to remember |
| --- | --- |
| `https://example.org/a?q=1#p` | Absolute, hierarchical, has authority/query/fragment |
| `/a/b` | Relative reference with an absolute path relative to the server root, no scheme |
| `../b` | Relative path reference, requires a base to determine the target |
| `//cdn.example.org/a.js` | Reference with authority but no scheme; inherits the scheme from the base when resolved |
| `#part` | Reference that only replaces the fragment when resolved in the context of a base |
| `mailto:team@example.org` | Absolute but opaque; does not extract a host like HTTPS |
| `urn:isbn:9780000000000` | Absolute, opaque according to Java URI structure |

### 8.1. Resolve and normalize

With base `https://example.org/docs/guide/index.html`:

~~~text
resolve("lesson.html") -> https://example.org/docs/guide/lesson.html
resolve("../api.html") -> https://example.org/docs/api.html
resolve("/assets/x.css") -> https://example.org/assets/x.css
~~~

A base ending with a filename is handled differently from a base ending with `/`. For example, with `https://example.org/docs/guide/`, `resolve("lesson.html")` goes to `/docs/guide/lesson.html`. Always test both with and without a trailing slash when designing paths.

`resolve()` combines URIs according to reference resolution rules, and `normalize()` simplifies certain segments; neither **makes HTTP/DNS calls**. If the base or reference comes from an untrusted source, the result of `resolve()` can still switch to a different host via a `//attacker.example/...` reference or a new absolute URI. Do not assume it preserves the same domain.

## 9. Java 17+: Reading All Components and Building Queries Properly

Java has two key types:

- `java.net.URI` represents a URI/reference syntactically; used for parsing, comparing, resolving, normalizing, inspecting, and creating URIs. `URI.create(String)` throws `IllegalArgumentException` if the string is invalid (typically wrapping a `URISyntaxException`); `new URI(String)` throws the checked `URISyntaxException`.
- `java.net.URL` is tied to a resource access mechanism via a scheme/handler. Calling `uri.toURL()` only makes sense for absolute URIs with a supported handler; not every URI can become a network-accessible URL. Only operations using a connection/stream from a URL can perform I/O. When only analyzing structure, prefer `URI`.

### 9.1. Complete runnable example

Create the file **UriPartsDemo.java** in UTF-8:

~~~java
import java.net.URI;
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

public class UriPartsDemo {
    public static void main(String[] args) {
        URI uri = URI.create(
                "https://reader@example.org:8443/docs/java%20networking"
                + "?lang=vi&tag=uri#basics");

        System.out.println("scheme         = " + uri.getScheme());
        System.out.println("authority      = " + uri.getRawAuthority());
        System.out.println("user-info      = " + uri.getRawUserInfo());
        System.out.println("host           = " + uri.getHost());
        System.out.println("port           = " + uri.getPort());
        System.out.println("path(raw)      = " + uri.getRawPath());
        System.out.println("path(decoded)  = " + uri.getPath());
        System.out.println("query(raw)     = " + uri.getRawQuery());
        System.out.println("fragment(raw)  = " + uri.getRawFragment());

        URI base = URI.create("https://example.org/guide/");
        System.out.println("resolved       = " + base.resolve("intro.html"));

        // URLEncoder is for *form parameter values*, not paths.
        String term = "C++ & Java";
        String encoded = URLEncoder.encode(term, StandardCharsets.UTF_8);
        URI search = URI.create(
                "https://example.org/search?q=" + encoded);
        System.out.println("query(form)    = " + search.getRawQuery());

        // Only decode the VALUE extracted from the raw query.
        String rawValue = search.getRawQuery().substring("q=".length());
        System.out.println("form decoded   = " + URLDecoder.decode(
                rawValue, StandardCharsets.UTF_8));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 UriPartsDemo.java
java UriPartsDemo
~~~

Stdout:

~~~text
scheme         = https
authority      = reader@example.org:8443
user-info      = reader
host           = example.org
port           = 8443
path(raw)      = /docs/java%20networking
path(decoded)  = /docs/java networking
query(raw)     = lang=vi&tag=uri
fragment(raw)  = basics
resolved       = https://example.org/guide/intro.html
query(form)    = q=C%2B%2B+%26+Java
form decoded   = C++ & Java
~~~

Explanation of key points in the output:

1. `getRawAuthority()` includes user-info, host, and port; `getHost()` retrieves only the host.
2. `getRawPath()` keeps `%20`, whereas `getPath()` returns a string with a space. **The decoded form is no longer a safe URI string to copy verbatim into a new URL/path.**
3. `getRawQuery()` does not contain `?`; `getRawFragment()` does not contain `#`.
4. `resolve()` uses a base ending with `/`, so it appends `intro.html` right after the `/guide/` directory.
5. `URLEncoder` encodes each value in form format; `URLDecoder` restores it from the exact extracted value. Neither sockets nor Internet access are needed to run this program.

### 9.2. Constructing a URI from components, avoiding arbitrary string concatenation

When you have **unencoded** components (not yet percent-encoded), the component-based constructor helps avoid errors with spaces or unintended special characters:

~~~java
// Illustrative snippet assuming java.net.URI is imported.
URI built = new URI(
        "https",              // scheme
        null,                 // userInfo
        "example.org",        // host
        8443,                 // port
        "/tai lieu/huong dan",// unencoded path
        "lang=vi",            // unencoded query
        "muc 1"               // unencoded fragment
);
System.out.println(built.toASCIIString());
~~~

The snippet above uses the 7-argument constructor, which can throw `URISyntaxException`; when placing it in a `main` method, you must declare/handle the exception. The constructor automatically quotes invalid characters according to each component's context. **Do not pass already percent-encoded strings arbitrarily**: `%` signs may get double-encoded into `%25`. In particular, a query with multiple parameters must have **each name and value** encoded according to the application's data standard before joining with `&`/`=`, rather than expecting the constructor to understand a parameter map.

When you need an HTTP URL from a validated URI, you can use `uri.toURL()` and then pass it to an appropriate HTTP library. With the Java 11+ HTTP client, `HttpRequest.newBuilder(uri)` accepts `URI` directly; production HTTP code still needs to validate scheme, host, port, timeouts, redirects, and security policies before making network calls.

## 10. Percent-Encoding, Unicode, and the Raw/Decoded Difference

URIs have a restricted syntactic character set. Percent-encoding represents each **byte** as `%HH` (two hex digits), for example:

| Data or character | Common form | What to understand |
| --- | --- | --- |
| Space in path | `%20` | Do not use raw spaces in a URI string |
| `#` intended as data | `%23` | A raw `#` starts the fragment |
| `?` intended as data in path | `%3F` | A raw `?` switches to the query |
| `&` in a form value | `%26` | Prevents being mistaken for a pair delimiter |
| Literal `+` in a form value | `%2B` | Prevents being treated as a space when form-decoding |
| Literal `%` | `%25` | Avoids invalid percent sequences |

For Unicode characters such as `ữ` or emoji, they must typically be converted to UTF-8 bytes and then the bytes that cannot be written directly in an ASCII URI are percent-encoded; you cannot simply replace a character with a single `%HH` escape if its UTF-8 representation has multiple bytes. `URI.toASCIIString()` is useful when you need an ASCII representation of a URI containing valid international characters.

You must distinguish three layers:

1. **Raw URI string:** contains delimiters and percent-encoded bytes, e.g., `/a%2Fb`.
2. **Component value after percent-decoding:** may become `/a/b`; if decoded before splitting segments, `%2F` loses the indication that "it was originally encoded".
3. **Protocol/application-specific semantics:** some servers/routers choose to handle encoded slashes, dots, repeated keys, and query parameters in their own way.

A dangerous bug is **double decoding**: `%252F` is percent-decoded once to `%2F`; decoded a second time, it becomes `/`. If security layers and routers decode differently, data can be interpreted unexpectedly. The design must agree on when and how many times decoding occurs, and validate against the exact form that the routing system actually uses.

## 11. Edge Cases and Common Pitfalls

| Case | Correct interpretation | Common mistake |
| --- | --- | --- |
| `https://example.org` | No explicit port; path is not automatically `/` in the input string | Assuming `getPort() == 443` |
| `https://example.org:8443/p` | Authority has host and port | Comparing the entire authority to a hostname |
| `https://[2001:db8::1]:443/p` | IPv6 literal in square brackets | Splitting host and port with `split(":")` |
| `https://example.org/p?q=%23#t` | Query has `%23`; fragment is `t` | Treating `%23` as the `#` delimiter |
| `https://example.org/a%2Fb` | Raw path has an encoded slash | Decoding the path and splitting slashes without following policy |
| `https://example.org/search?q=a+b` | In raw query, `+` is literal; in form convention, `+` means space | Thinking `URI.getQuery()` automatically form-decodes |
| `https://example.org/a#top` | Fragment is for the client/resource context | Expecting the HTTP server to receive `#top` |
| `mailto:user@example.org` | Opaque URI with no HTTP host/path | Calling `getHost()` and assuming it is non-null |
| `../image.png` | Relative reference, requires a base | Using it as an absolute URL without context |
| `https://user:secret@example.org/` | User-info risks leaking credentials | Logging or sharing the full URI |

**Do not parse URIs using `split("://")`, `split("@")`, `split(":")`, or simple regexes.** For example, IPv6 has multiple colons, user-info has escape syntax, and some schemes do not use `//`. Use `URI`, and then inspect the components relevant to your protocol.

**Do not treat `URI.normalize()` as full canonicalization.** It does not normalize hostnames to a single DNS form, does not strip default ports, does not sort queries, and does not enforce application-specific rules. When comparing URIs for cache keys or signatures, specify canonicalization explicitly across all parties.

**Do not use `URI.getHost() != null` as the sole URL safety check.** For user-supplied URLs and server-side resource fetching features, you must restrict schemes, hosts/ports, resolved IP addresses, internal networks, redirects, and actual request paths. Do not check the host using a substring of the authority or `startsWith("https://trusted.example")`; a string like `https://trusted.example.attacker.invalid` can bypass flawed checks. Logs should redact user-info, query tokens, and sensitive data.

## 12. Self-Check Practice Exercises

### Exercise 1: Split a URI into seven parts

Given:

~~~text
https://api.example.org:9443/v1/items/42?include=price&lang=vi#details
~~~

Identify the scheme, authority, host, port, path, query, and fragment. Answer:

| Component | Value |
| --- | --- |
| scheme | `https` |
| authority | `api.example.org:9443` |
| host | `api.example.org` |
| port | `9443` |
| path | `/v1/items/42` |
| query | `include=price&lang=vi` |
| fragment | `details` |

There is no user-info. Note that an HTTP client does not send `#details` as part of the request-target.

### Exercise 2: Distinguish path and form query

Given the search value `a+b & c`, create parameter `q` using `URLEncoder.encode(value, UTF_8)` and put it into a query. The encoded value is `a%2Bb+%26+c`. If `+` is a literal character but left unencoded in a form query string, `URLDecoder` will misinterpret it as a space.

### Exercise 3: Predict Java output

~~~java
URI base = URI.create("https://example.org/docs/start.html");
System.out.println(base.resolve("next.html"));
System.out.println(base.resolve("../home.html"));
System.out.println(URI.create("https://example.org").getPort());
~~~

This is an illustrative snippet placed inside a program that has imported `java.net.URI`. Expected output:

~~~text
https://example.org/docs/next.html
https://example.org/home.html
-1
~~~

Solution: a relative reference not starting with `/` replaces the last segment of the base path; `..` goes up to the parent directory; there is no explicit port so `getPort()` returns `-1`.

## 13. Checklist for Using URI/URL in Java Applications

- [ ] Have allowed schemes been specified and does the URI match the required **absolute/hierarchical** form?
- [ ] Is **authority** separated from **host**, and are user-info, IPv6, and explicit/default ports handled properly?
- [ ] Is the path handled consistently in raw/decoded form without decoding slashes or dot-segments multiple times?
- [ ] Are query parameters encoded **per value** according to the service's convention, handling repeated keys and `&`, `=`, `+` characters?
- [ ] Is the fragment understood as client-side data, without expecting the HTTP backend to receive it?
- [ ] Are relative references resolved against an appropriate base, including bases with/without a trailing slash?
- [ ] Are URIs constructed via appropriate component APIs/encoders, avoiding double-encoding `%`?
- [ ] If the URI comes from an untrusted source, have host/port/IP/redirects been validated and sensitive info redacted?

Key takeaway: **URIs have a common delimiter syntax, but the semantics of each part depend on the scheme and application protocol.** Once you master the boundaries between scheme, authority, host, port, path, query, and fragment, you will read network addresses accurately, use `java.net.URI` effectively, and avoid subtle bugs in Java programming.