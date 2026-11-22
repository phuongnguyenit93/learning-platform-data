# Parsing, Building URIs by Component, and Handling `URISyntaxException` in Java

In Java, `java.net.URI` helps represent, parse, combine, and normalize **resource identifiers** according to URI syntax. A URI can be an HTTP(S) URL, a relative path, `mailto:`, `urn:`, or another identifier. **Creating a `URI` does not open a network connection and does not check whether the resource exists.** The focus of this lesson is accurately reading each component, building URIs without mixing up data boundaries, and handling `URISyntaxException` deliberately.

For example, the same requirement has two easily confused approaches:

~~~text
"Already have a complete URI string, need to validate syntax"
   -> new URI(fullText)                   // may throw URISyntaxException

"Already have separate scheme, host, path, query, fragment"
   -> new URI(scheme, userInfo, host, port, path, query, fragment)
                                          // automatically quotes some illegal characters
~~~

The two approaches **are not equivalent in how they handle spaces, percent characters, and delimiter characters**. Understanding this difference helps avoid double-encoded URIs or queries carrying unintended meanings.

## 1. Lesson Objectives

After this lesson, you will be able to:

- Read URI structure including `scheme`, `authority` (`userInfo`, `host`, `port`), `path`, `query`, `fragment`; recognize absolute, relative, hierarchical, and opaque URIs.
- Choose `getRawPath()/getPath()`, `getRawQuery()/getQuery()`, and other accessors in the right context.
- Create URIs using the single-string constructor or multi-component constructors, explaining `null`, port `-1`, percent-encoding `%XX`, spaces, and reserved characters.
- Distinguish `new URI(...)` throwing checked `URISyntaxException` from `URI.create(...)` throwing unchecked `IllegalArgumentException`.
- Use `normalize()`, `resolve()`, `relativize()`, and `parseServerAuthority()` for their intended purposes.
- Know when `URLEncoder`/`URLDecoder` are needed and why they are **not** general-purpose URI encoding tools.
- Write a standalone Java 17+ program to build and parse URIs and display the error reason/index.

## 2. The URI Model and Reading Each Component

### 2.1. Syntax of a Hierarchical URI

For a typical HTTP(S) URI:

~~~text
scheme://[userInfo@]host[:port]/path?query#fragment
https://guest@example.org:8443/docs/java?lang=vi&page=2#install
^^^^^   ^^^^^ ^^^^^^^^^^^ ^^^^ ^^^^^^^^^^ ^^^^^^^^^^^^^^ ^^^^^^^
scheme  user   host        port path       query           fragment
~~~

The characters `:`, `//`, `/`, `?`, and `#` define syntax boundaries. **Delimiters are different from data**: `#` is the character that starts the fragment, whereas `%23` in the path is data representing the `#` character. Similarly, `?` starts the query in a hierarchical URI, whereas `%3F` inside the path is a question mark belonging to the path name.

`authority` is the part between `//` and the next `/`, `?`, or `#`; a server-based authority can be parsed into `userInfo`, `host`, and `port`. **Not every URI has a host.** Some URIs have an authority in a form that cannot be parsed into a host, so `getRawAuthority()` has a value while `getHost()` may return `null`.

For the example above:

| Method call | Expected value |
| --- | --- |
| `getScheme()` | `"https"` |
| `getRawAuthority()` | `"guest@example.org:8443"` |
| `getUserInfo()` | `"guest"` |
| `getHost()` | `"example.org"` |
| `getPort()` | `8443` |
| `getPath()` | `"/docs/java"` |
| `getQuery()` | `"lang=vi&page=2"` |
| `getFragment()` | `"install"` |

> Do not put passwords, access tokens, or secrets into `userInfo`, query, or fragment and then log the full URI. Those parts may be stored in browser history, telemetry, or logs unintentionally.

### 2.2. Absolute, Relative, Hierarchical, and Opaque

There are **two different classification axes**:

- `isAbsolute()` is `true` if the URI has a **scheme** (for example `https:`, `mailto:`). It does not mean the URI has a host or is a connectable URL.
- `isOpaque()` is `true` if the URI is **absolute** and its scheme-specific part does not begin with `/`. `mailto:team@example.org` and `urn:isbn:...` are opaque examples; they do not have a path/query according to the hierarchical model like HTTP.
- A **relative** URI has no scheme, for example `../images/icon.svg`, `/docs`, `?lang=vi`, `#toc`.
- A hierarchical URI can be absolute (`https://example.org/a`) or relative (`../a`).

An illustrative snippet, run inside a method:

~~~java
URI http = URI.create("https://example.org/docs");
URI mail = URI.create("mailto:team@example.org");
URI relative = URI.create("../images/logo.svg");

System.out.println(http.isAbsolute());     // true
System.out.println(http.isOpaque());       // false
System.out.println(mail.isAbsolute());     // true
System.out.println(mail.isOpaque());       // true
System.out.println(relative.isAbsolute()); // false
~~~

This snippet requires `import java.net.URI;`. The comments record the result of each call. For `mailto:`, you can read `getSchemeSpecificPart()`; do not expect `getHost()` or `getPath()` as with an HTTP URI.

### 2.3. `null`, Empty Strings, and `-1` Are Very Different

- `getScheme()`, `getQuery()`, `getFragment()`, and `getHost()` may return `null` if the component is **not defined**.
- `getPort()` returns `-1` when no port is specified. Omitting the port in a URI **does not automatically fill in 80 or 443**; the application may infer a default based on the scheme.
- `https://example.org/a` has a **non-existent** query (`getQuery() == null`); `https://example.org/a?` has a **declared but empty** query (`getQuery().equals("")`).
- `#` can start an empty fragment; `getFragment() == null` and `getFragment().isEmpty()` are not always equivalent.
- Do not use `uri.getQuery().split("&")` without checking for `null` and especially without considering percent-encoding semantics.

## 3. Parsing a URI from a Complete String

### 3.1. `new URI(String)`: Parse and Throw Checked Exception

~~~java
import java.net.URI;
import java.net.URISyntaxException;

public class UriParseFragment {
    static URI parse(String input) throws URISyntaxException {
        return new URI(input);
    }
}
~~~

The `URI(String)` constructor parses **the exact string provided**. If the string is syntactically invalid, it throws `URISyntaxException`, which is a **checked exception**: you must `catch` it or declare `throws`.

~~~java
URI good = new URI("https://example.org/a%20b?x=1#top"); // valid
URI bad  = new URI("https://example.org/a b");           // URISyntaxException
~~~

The two lines above are **illustrative of the outcome**: if placed consecutively in a program without exception handling, the program stops at the second line. With `URI(String)`, a raw space in the path is illegal; `%20` is a valid escape representing a space.

The parser does **not** check DNS, connectivity, HTTP status, destination safety, or resource reachability. It only handles syntactic validity according to what `java.net.URI` supports.

### 3.2. `URI.create(String)`: Suitable for Constants Known to Be Valid

~~~java
URI base = URI.create("https://example.org/api/");
~~~

`URI.create(input)` behaves like `new URI(input)`, but if parsing fails it wraps `URISyntaxException` in `IllegalArgumentException` (**unchecked exception**). The JDK intends this approach for strings already known to be valid, such as developer-controlled configuration/constants.

| Data source | Usually appropriate usage | Reason |
| --- | --- | --- |
| Verified literal URI constant | `URI.create("https://...")` | Invalid syntax is a programming/configuration bug |
| User-entered URI string | `new URI(input)` + `catch URISyntaxException` | Can report structured errors to the user |
| Separate `scheme/host/path/query` components | Multi-parameter constructor | Preserves structural boundaries when building |
| String provided by an external service | `new URI(input)` and semantic validation | Input is not fully trusted |
| Path/query with dynamic data | Encode **each component/value** before assembling in context | Prevents injection and double-encoding |

Do not replace every `new URI(input)` with `URI.create(input)` just to avoid declaring `throws`; doing so loses the ability to handle checked errors at the input boundary.

### 3.3. Reading `URISyntaxException` Details

A `URISyntaxException` provides:

- `getReason()`: describes the reason, such as `Illegal character in path`. This is diagnostic information; do **not** match exact reason strings as business logic, because wording may vary by implementation/version.
- `getIndex()`: the **0-based** error position in the input, or `-1` if unknown.
- `getInput()`: the entire rejected input.
- `getMessage()`: a combined message with the reason, index (if available), and input.

Example handling at the input boundary:

~~~java
try {
    URI uri = new URI(userInput);
    // Continue validating scheme/host/port according to application rules.
} catch (URISyntaxException e) {
    int index = e.getIndex();
    String explanation = e.getReason();
    System.err.println("Invalid URI, index: " + index);
    System.err.println("Reason: " + explanation);
}
~~~

This is an **in-method code fragment**: `userInput` must be a pre-existing `String` variable, and `import java.net.URI;`, `import java.net.URISyntaxException;` are required. Do not log `getInput()` unconditionally because the URI may contain sensitive information. Also do not arbitrarily "fix" the entire input by replacing every space with `%20`: path, query, and userInfo have different rules; invalid input may need to be rejected.

## 4. Building a URI from Components

### 4.1. The Seven-Parameter Constructor

~~~java
URI uri = new URI(
    "https",             // scheme
    null,                // userInfo
    "example.org",       // host
    8443,                // port (-1 means no port declared)
    "/ho so/cv",         // path
    "q=java uri&sort=asc", // query
    "muc 1"              // fragment
);
~~~

This is an illustrative snippet inside a method with `throws URISyntaxException` or `catch`; it requires `import java.net.URI;`. Result:

~~~text
https://example.org:8443/ho%20so/cv?q=java%20uri&sort=asc#muc%201
~~~

The seven-parameter constructor `URI(String scheme, String userInfo, String host, int port, String path, String query, String fragment)` creates a **hierarchical URI**, places delimiters in the right positions, and **quotes illegal characters for each component**. For instance, spaces in path/query/fragment are turned into `%20`. After assembling the string, the constructor still validates syntax and may throw `URISyntaxException`.

Some rules to remember:

1. Pass `null` when a component is **absent**, or `-1` when **no port is specified**.
2. If both scheme and path are present, the path must be empty or **start with `/`**; passing a relative path like `"docs/a"` together with a scheme can throw `URISyntaxException`.
3. Do not manually prepend `?` or `#` to `query` or `fragment`: the constructor inserts the delimiters automatically.
4. Path takes the **path**, query takes the **part after `?`**; `/` characters in the path are preserved to separate segments.
5. Passing `userInfo` is generally unnecessary for modern HTTP; do not put credentials in a URI.
6. The constructor does not check whether the service exists and does not automatically understand **query parameter** boundaries (`&` and `=` can still be valid structural characters in a query).

### 4.2. Related Constructors and How to Choose

| Constructor | When it is useful |
| --- | --- |
| `new URI(String full)` | Parse a complete URI string without auto-quoting invalid characters |
| `new URI(scheme, userInfo, host, port, path, query, fragment)` | Build a server-based hierarchical URI with explicit host/port |
| `new URI(scheme, authority, path, query, fragment)` | When authority is provided as a separate form |
| `new URI(scheme, host, path, fragment)` | Shorter variant without query/port/userInfo |
| `new URI(scheme, schemeSpecificPart, fragment)` | When an identifier based on a scheme-specific part is needed, including opaque URIs |

Do not confuse the fifth three-parameter constructor (`scheme, schemeSpecificPart, fragment`) with `scheme, host, path`. It does **not** mean the three usual HTTP components.

### 4.3. Hostnames, IPv6, and IDN

- Use `getHost()` or a constructor taking `host`, **do not split hostnames with `split(":")`.** IPv6 literals contain `:`; the typical HTTP URI form is `https://[2001:db8::1]:8443/`.
- For internationalized hostnames, `java.net.IDN.toASCII(name)` converts domain labels according to the IDN rules supported by Java before using them in the `host` field. You must still apply the application's host allowlist rules; conversion does not replace security policy or DNS checks.
- Port `-1` in `URI` means "not declared", not connecting to a negative port.

Example of creating a URI with an IPv6 host accepted by the API:

~~~java
URI local = new URI("http", null, "::1", 8080, "/health", null, null);
// The string form of the URI will put square brackets around the IPv6 literal if needed.
~~~

This snippet can be used in a method that declares/handles `URISyntaxException`. Not every URI with `getRawAuthority()` has a non-`null` `getHost()`. When a specific protocol requires a server-based authority, use `parseServerAuthority()` to report an error if the authority cannot be parsed.

## 5. `getRawXxx()` and `getXxx()`: Reading Percent-Encoding Correctly

A URI can represent a character using UTF-8 bytes in `%HH` form (escape/percent-encoding). For example, `%20` is an ASCII space. `URI` provides both **raw** accessors and **decoded** accessors:

| Component | Raw (preserves `%HH`) | Decoded (decodes escapes) |
| --- | --- | --- |
| Path | `getRawPath()` | `getPath()` |
| Query | `getRawQuery()` | `getQuery()` |
| Fragment | `getRawFragment()` | `getFragment()` |
| User info | `getRawUserInfo()` | `getUserInfo()` |
| Authority | `getRawAuthority()` | `getAuthority()` |
| Scheme-specific part | `getRawSchemeSpecificPart()` | `getSchemeSpecificPart()` |

With `https://example.org/ho%20so?q=a%26b#phan%201`:

~~~text
getRawPath()     -> "/ho%20so"
getPath()        -> "/ho so"
getRawQuery()    -> "q=a%26b"
getQuery()       -> "q=a&b"
getRawFragment() -> "phan%201"
getFragment()    -> "phan 1"
~~~

**Important pitfall:** if you call `getQuery()` first and then `split("&")`, the value of `q` in the example above is mistakenly split into two parts because `%26` was already decoded into `&`. When you actually need to parse query parameter pairs, split the structure on `getRawQuery()` **first**, then decode names/values according to the endpoint's encoding convention.

Similarly, `getPath()` can decode `%2F` into `/`. That is a significant change for routers and segment splitting: **do not split the path after decoding** if the protocol distinguishes `/` as a delimiter from an encoded slash inside a segment.

`toString()` preserves a URI representation that may contain Unicode; `toASCIIString()` outputs an ASCII form using UTF-8 percent-encoding when needed. Do not treat `URI.toString()` or `toASCIIString()` as an input-sanitization mechanism against attacks.

## 6. Avoiding Double-Encoding and Query Bugs

### 6.1. An Already Encoded String Differs from an Unencoded Component

The two examples below are **different**:

~~~java
URI parsed = new URI("https://example.org/a%20b");
URI rebuilt = new URI(
        "https", null, "example.org", -1, "/a%20b", null, null);

System.out.println(parsed.getRawPath());   // /a%20b
System.out.println(rebuilt.getRawPath());  // /a%2520b
~~~

This is an illustrative snippet inside a method declaring `throws URISyntaxException`, not a standalone program. When using a multi-component constructor, `%` is quoted into `%25` to preserve it as **data**. Therefore, passing `"/a%20b"` into the `path` field produces `"/a%2520b"`. Do not mix already percent-encoded segments with constructors meant for component inputs.

Practical rules:

- If the input is a **properly encoded complete URI string**, parse it with `new URI(full)`.
- If the input consists of **raw unencoded components**, build the URI with the appropriate constructor and inspect the resulting structure.
- Do not encode an entire URI string as a single piece of data; `:`, `/`, `?`, `&`, and `#` have contextual meaning.
- Do not decode and then arbitrarily re-encode, especially for paths/queries that already contain escapes.

### 6.2. Queries Have Two Levels of Structure

In general URI syntax, a query is just **a single string** after `?`. The `key=value&key2=value2` convention is how many HTTP applications represent parameters, **not an automatic feature of `URI`**.

Suppose a search value is `"a+b & c"`, containing `+`, space, and `&`. If concatenated directly into `q=...`, `&` may be interpreted by the server as starting a new parameter.

For an endpoint **using the form query convention** (`application/x-www-form-urlencoded`), you can encode **each value**:

~~~java
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

public class QueryValueFragment {
    static URI searchUri(String userText) {
        String encoded = URLEncoder.encode(userText, StandardCharsets.UTF_8);
        return URI.create("https://example.org/search?q=" + encoded);
    }
}
~~~

With `userText = "a+b & c"`, `encoded` is `a%2Bb+%26+c`; the resulting URI has raw query `q=a%2Bb+%26+c`. **The `+` sign in form encoding represents a space**; a literal plus sign is encoded as `%2B`. On the receiving side, `URLDecoder` applies the corresponding semantics when the endpoint uses form encoding.

Things to avoid:

- `URLEncoder`/`URLDecoder` are for **HTML form encoding**, not encoders/decoders for every part of a URI. Do not use `URLEncoder` to encode an entire URI or an entire path; it can turn `/` into `%2F` and spaces into `+` (not the desired syntax for paths).
- For endpoints specifying RFC 3986 percent-encoding rather than form encoding, use an encoding mechanism that matches **the endpoint's specification**, especially for handling `+`.
- If you already used `URLEncoder` to obtain `q=a%2Bb+%26+c`, do not pass that already-encoded string into the `query` field of a multi-component constructor, because `%` will be encoded a second time.
- Do not arbitrarily append a `#...` fragment to the query; component constructors have a separate `fragment` argument.

### 6.3. Parsing Raw Queries Without Breaking Boundaries

For the form query convention, the basic workflow is:

1. Get `uri.getRawQuery()`; if `null`, there is no query.
2. Split on **undecoded** `&`; there may be parameters without `=`, empty values, or multiple parameters with the same name.
3. For each pair, find the **first** `=` to separate name/value, rather than splitting on every `=`.
4. Decode each part according to application rules (`URLDecoder` only when it is actually form encoding); validate charset, malformed escapes, duplicate keys, and length limits.

That is an **application-protocol workflow**, not a promise that all HTTP endpoints use the same query semantics. If you use an HTTP library or web framework with a suitable query parameter builder/parser, it is usually better to use that API rather than writing a complex custom parser.

## 7. `normalize`, `resolve`, and `relativize` Do Not Replace Each Other

### 7.1. `normalize()`: Collapsing Dot Segments in a Path

~~~java
URI uri = URI.create("https://example.org/a/./b/../c");
System.out.println(uri.normalize()); // https://example.org/a/c
~~~

`normalize()` processes certain `.` and `..` segments in the **path** and `URI`'s path normalization rules; it does not access the network, does not validate resources, does not decode all escapes, and does not guarantee that two URLs point to the same application content. For example, `%2e%2e` is not necessarily treated like literal `..` during normalization. Do not rely solely on `normalize()` to prevent path traversal.

### 7.2. `resolve(reference)`: Resolving a Relative Reference Against a Base

~~~java
URI base = URI.create("https://example.org/docs/java/page.html");
URI other = URI.create("../images/logo.svg");
URI absolute = base.resolve(other);
System.out.println(absolute); // https://example.org/docs/images/logo.svg
~~~

The base path ends with `page.html`, so a relative reference not starting with `/` is resolved against **the directory containing the document**, and then `..` is processed. If you want `base` to act as a **directory**, ensure a trailing `/` as needed. A reference that is an absolute URI or has its own authority can change the target origin; `resolve` **does not confine references within a directory**.

### 7.3. `relativize(target)`: Finding the Relative Part When Applicable

~~~java
URI root = URI.create("https://example.org/docs/");
URI page = URI.create("https://example.org/docs/java/uri.html");
System.out.println(root.relativize(page)); // java/uri.html
~~~

If the scheme/authority/path do not meet the relativize conditions, the result may remain the original target instead of becoming a relative URI. Do not treat `relativize` as a perfect inverse for every `resolve`.

All of these APIs return a **new URI** (or keep the same object when no change is needed); `URI` is immutable.

## 8. Verifying Server-Based Authority and Application Semantics

A URI can be valid in **general syntax** yet unsuitable for an HTTP request or application policy.

~~~java
URI candidate = new URI(userInput).parseServerAuthority();

if (!"https".equalsIgnoreCase(candidate.getScheme())
        || candidate.isOpaque()
        || candidate.getHost() == null
        || candidate.getUserInfo() != null) {
    throw new IllegalArgumentException("Only HTTPS URIs with a host are accepted");
}
~~~

This is an **illustrative snippet inside a method** with a pre-existing `userInput` variable and `URISyntaxException` declared/handled. `parseServerAuthority()` requires the authority (if present) to be parseable into a server-based authority, while checking `getHost()` confirms the HTTP(S) URI has a host. Additional application-specific rules typically include allowed hosts/ports, path prefixes, redirects, and network restrictions.

**Do not confuse syntax validation with security:** checking scheme/host on the string before sending a request is still not enough to prevent SSRF. Depending on the threat model, you must guard against redirects to unlisted hosts, DNS rebinding, internal IPs/metadata services, unexpected proxies, and hostname resolution changes; enforce these at the HTTP client, DNS, network egress, and system policy layers.

### Common Parsing Errors

| Symptom | Reason | How to handle |
| --- | --- | --- |
| `new URI("https://example.org/a b")` throws an error | Raw space in path | Build from raw components or properly encode the path |
| `URI.create(userInput)` throws `IllegalArgumentException` | It wraps `URISyntaxException` | Use the checked constructor for untrusted input |
| `getHost() == null` even though authority is present | Authority could not be parsed as a server-based host, or URI has no host | Inspect syntax/context, use `parseServerAuthority()` when needed |
| Built URI contains `%2520` | `%20` was already encoded, then passed to a component constructor | Do not double-encode; distinguish raw input from encoded URI |
| Query split incorrectly when `%26` is present | Decoded before splitting on `&` | Split the raw query before decoding |
| `URLEncoder` turns spaces into `+` | That is form encoding | Use only when the endpoint specifies form queries |
| Resolved URI points to a different host/path than base | Reference may be absolute, have `//host`, or `../` | Validate the final URI; do not use resolve as a sandbox |
| `normalize()` does not remove `%2e` escapes | Normalization is not a security filter | Validate paths according to server/filesystem rules |
| `uri.equals(other)` yet server returns different results, or vice versa | URI equality is syntactic, not HTTP resource identity | Do not use equality in place of business canonicalization logic |
| Lost context of `#` | Fragment is not sent as part of a normal HTTP request target | Extract fragment via the API; do not embed it in query/path |

## 9. Complete Runnable Java 17+ Program

The example below works strictly with URIs in memory; **no network, DNS, external libraries, or server are required**. It demonstrates building from components, reading raw/decoded values, resolving, normalizing, and catching syntax errors.

Create the file **`UriStudy.java`**:

~~~java
import java.net.URI;
import java.net.URISyntaxException;

public class UriStudy {
    public static void main(String[] args) throws URISyntaxException {
        URI built = new URI("https", null, "example.org", 8443,
                "/ho so/cv", "q=java uri&sort=asc", "muc 1");

        System.out.println("uri=" + built);
        System.out.println("host=" + built.getHost());
        System.out.println("port=" + built.getPort());
        System.out.println("rawPath=" + built.getRawPath());
        System.out.println("path=" + built.getPath());
        System.out.println("rawQuery=" + built.getRawQuery());

        URI base = new URI("https://example.org/docs/java/page.html");
        System.out.println("resolved=" + base.resolve("../images/logo.svg"));

        System.out.println("normalized="
                + new URI("https://example.org/a/./b/../c").normalize());

        try {
            new URI("https://example.org/a b");
        } catch (URISyntaxException error) {
            System.out.println("errorIndex=" + error.getIndex());
            System.out.println("errorReason=" + error.getReason());
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 UriStudy.java
java UriStudy
~~~

Actual stdout when run with OpenJDK 24 (structural values and error index also match Java 17/21 for this example):

~~~text
uri=https://example.org:8443/ho%20so/cv?q=java%20uri&sort=asc#muc%201
host=example.org
port=8443
rawPath=/ho%20so/cv
path=/ho so/cv
rawQuery=q=java%20uri&sort=asc
resolved=https://example.org/docs/images/logo.svg
normalized=https://example.org/a/c
errorIndex=21
errorReason=Illegal character in path
~~~

Reading the output:

1. Spaces from `"/ho so/cv"` and `"q=java uri&sort=asc"` were quoted into `%20` by the component constructor.
2. `getRawPath()` retains the `%20` escape; `getPath()` decodes it to a space.
3. `resolve("../images/logo.svg")` moves the path up from `/docs/java/` to `/docs/`, resulting in `/docs/images/logo.svg`.
4. `normalize()` collapses literal dot segments `.` and `..`.
5. The raw space in `https://example.org/a b` at **index 21** triggers `URISyntaxException`. Indices are 0-based; the reason from the JDK is `Illegal character in path`.

The `errorReason` result is for observing the error; do not hard-code production logic depending on the exact message text. With other inputs, `getIndex()` may be `-1`.

## 10. Scenario-Based Test Matrix

Do not stop at "happy path" examples: a parser/URI builder handling external data should also be tested with these cases:

| Input/scenario | What to verify |
| --- | --- |
| `https://example.org/a%20b` | Parses successfully; raw path keeps `%20`; decoded path has space |
| `https://example.org/a b` | `new URI` throws checked `URISyntaxException`; `URI.create` throws `IllegalArgumentException` |
| `https://example.org/a?` | Empty query is distinct from absent query |
| `https://example.org/a#` | Empty fragment is distinct from absent fragment |
| `https://example.org/a?q=a%26b` | Do not split query after decoding |
| `mailto:team@example.org` | Absolute but opaque; no HTTP host/path |
| `../pictures/cover.png` | Relative URI, becomes absolute only after resolving with a suitable base |
| `https://[2001:db8::1]:8443/` | IPv6 host, do not split string by colons |
| `https://example.org/../admin` | Normalize/resolve changes path; does not imply access permission |
| `https://example.org/a%2520b` | Two layers of escaping; decoded path contains literal `%20`, not a space |
| Query fields containing `&`, `=`, `+`, Unicode | Encode/decode per endpoint convention without losing parameter boundaries |
| URL containing credentials/secrets | Do not log the full error string; have a policy to reject/redact data |

When writing unit tests, compare individual components as well as `getRaw...` when encoding matters, rather than checking only `uri.toString()`.

## 11. Exercises with Solutions

### Exercise 1 — Parse and Identify Errors

Input is `"https://example.org/a b"`. Which method throws a checked exception? If using `URI.create`, what exception type is thrown?

**Answer:** `new URI(input)` throws `URISyntaxException`, whereas `URI.create(input)` throws `IllegalArgumentException` (wrapping the syntax error). In the example program, the space is at index 21.

### Exercise 2 — Build a URI from Raw Components

You need to create `https://example.org/docs/hello%20world?lang=vi#part%201` from the components `"https"`, `"example.org"`, `"/docs/hello world"`, `"lang=vi"`, `"part 1"`. Choose the constructor.

**Answer:**

~~~java
URI uri = new URI("https", null, "example.org", -1,
                  "/docs/hello world", "lang=vi", "part 1");
~~~

This is a snippet inside a method with `throws URISyntaxException`/catch. The constructor automatically adds `?`, `#`, and quotes spaces. Do not pass `"/docs/hello%20world"` as a raw path.

### Exercise 3 — Choosing Raw vs. Decoded

For the URI `https://example.org/search?q=a%26b`, why is `uri.getQuery().split("&")` dangerous?

**Answer:** `getQuery()` decodes `%26` into `&`; data inside the value is mistaken for a separator. Use `getRawQuery()` to split the structure first, then decode each value according to form query rules if applicable.

### Exercise 4 — Does an Absolute URI Have a Host?

`URI.create("mailto:team@example.org").isAbsolute()` returns true. Must `getHost()` be non-`null`?

**Answer:** No. It has the `mailto` scheme so it is absolute, but it is opaque, not a hierarchical URI with a server-based authority. `isAbsolute()` does not prove a host is present.

### Exercise 5 — Logic Bugs Despite a Valid URI

An application receives a user URI and calls an HTTP client. The URI passed `new URI(input)` without throwing an exception. Is that enough to send the request safely?

**Answer:** Not yet. You must check scheme, host, port, userInfo, redirects, network egress policy, and other security constraints. **Valid syntax** does not mean **permitted access** or a **safe destination**.

## 12. Checklist for Real Code

- [ ] I know whether the input is a **complete URI** or **raw components**.
- [ ] I decided between `new URI(...)` and `URI.create(...)` based on whether the input can be syntactically invalid.
- [ ] I do not mix already percent-encoded components into an auto-quoting constructor.
- [ ] I use raw accessors when I need to preserve path/query boundaries; I decode in the right context.
- [ ] I do not use `URLEncoder` for paths or entire URIs.
- [ ] I distinguish `null`, empty strings, and port `-1`.
- [ ] I handle `URISyntaxException` and do not leak inputs containing secrets in messages/logs.
- [ ] If the URI goes to the network, I also validate semantic and security rules.
- [ ] I have tests for spaces, `%HH`, encoded separators, fragments, relative URIs, IPv6, and invalid inputs.

## 13. Official Documentation

- [Java SE 21 — `java.net.URI`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URI.html): grammar, constructors, raw/decoded accessors, normalize, resolve, relativize, parseServerAuthority.
- [Java SE 21 — `java.net.URISyntaxException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URISyntaxException.html): `getReason()`, `getIndex()`, `getInput()`, `getMessage()`.
- [Java SE 21 — `java.net.URLEncoder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLEncoder.html): `application/x-www-form-urlencoded` convention.
- [Java SE 21 — `java.net.URLDecoder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLDecoder.html): decoding according to form encoding.
- [Java SE 21 — `java.net.IDN`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/IDN.html): converting internationalized domain names.
- [RFC 3986 — Uniform Resource Identifier: Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986): general semantics of syntax/percent-encoding/delimiters; when working in Java, cross-check against the specific `java.net.URI` contract.

**Takeaway:** `URI(String)` **parses**, multi-parameter constructors **build from components and quote when needed**, `URISyntaxException` **reports syntax errors**, and business/security validation is a separate step. Keeping those three responsibilities distinct will help you avoid most URI bugs in Java Networking.
