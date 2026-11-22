# Comparing URIs, URLs, and the Risk of Unintended Name Resolution When Comparing URLs in Java

A Java program might only want to check whether two addresses are the same, yet calling `URL.equals()`, `URL.hashCode()`, or `URL.sameFile()` **can trigger hostname resolution**. This is especially surprising when a `URL` is used as a `HashMap` key, a `HashSet` element, or in address deduplication logic. The result can depend on DNS and incur network wait time even when the program does not call `openConnection()` or `openStream()`.

This lesson focuses on the difference between **syntactic comparison of `java.net.URI`** and **semantic comparison of `java.net.URL`**, why URL comparison has side effects, and how to choose the right comparison without accidentally querying domain names.

## 1. What do URI and URL represent in Java?

**URI (Uniform Resource Identifier)** is a string identifying a resource according to a syntax. `java.net.URI` parses components such as scheme, authority, host, port, path, query, and fragment. A URI can be absolute (`https://example.com/a`), relative (`../a`), hierarchical, or opaque (`mailto:team@example.com`). `URI` is immutable; parsing, `equals`, `hashCode`, `compareTo`, `normalize`, and `resolve` are syntax-based operations and **do not query DNS for comparison**.

**URL (Uniform Resource Locator)** is a type of identifier that specifies how to locate/access a resource. `java.net.URL` represents an absolute address paired with a protocol-specific `URLStreamHandler`. It provides operations such as `openConnection()` and `openStream()`. In particular, URL's `equals`/`hashCode` rules can use the **host's Internet address** to determine equivalence, which requires name resolution.

| Criterion | `java.net.URI` | `java.net.URL` |
| --- | --- | --- |
| Primary role | Representing, parsing, and manipulating identifier syntax | Resource address with protocol handler and connection API |
| Absolute / relative | Supports both | A complete URL object requires a protocol; can accept a relative string via a context URL |
| `equals()` | Compares syntactic components per URI rules | May determine host equivalence via DNS-resolved IP |
| `hashCode()` | Based on URI components, no DNS resolution | May block waiting for hostname resolution |
| `compareTo()` | Yes, according to URI syntactic order | Does not implement `Comparable<URL>` |
| `normalize()` / `resolve()` | Normalizes dot-segments / resolves relative URI references purely syntactically | URL handles relative addresses through its handler; not identical to the URI API |
| Opening connections | No `openStream()` | Has `openConnection()` / `openStream()` |

Note: the word “resolve” in `URI.resolve(...)` means **combining a relative reference with a base URI**, which is completely different from “DNS resolution” (looking up an IP from a hostname).

## 2. Which structure is actually compared?

Example:

~~~text
https://user@example.com:443/docs/guide?lang=vi#intro
└https┘ └─ authority ────────┘└─path─────┘└query┘└fragment┘
scheme     userinfo + host + port
~~~

The corresponding methods are `getScheme()`, `getRawUserInfo()`, `getHost()`, `getPort()`, `getRawPath()`, `getRawQuery()`, and `getRawFragment()`. The `getRaw...` variants preserve percent-encoding; the corresponding `get...` variants may return decoded data. For example, `getRawPath()` can be `/a%2Fb` while `getPath()` is `/a/b`. The two representations should not be arbitrarily interchanged when building cache keys, checking permissions, or determining paths.

- **Scheme**: `https`, `http`, `file`, `mailto`. `URI.equals` compares schemes case-insensitively.
- **Authority/host**: the host of a server-based URI is compared case-insensitively; userinfo is not ignored by default.
- **Port**: an unspecified port has the value `-1` in `URI`; `:443` is a present value, so the two URIs differ even though they have the same “effective HTTPS port” in HTTP terms.
- **Path, query, fragment**: participate in `URI.equals`; path/query/fragment are not automatically reordered, stripped, or lowercased.
- **Percent escapes**: the two hex digits in `%hh` encoding are compared case-insensitively (`%2f` and `%2F` are equivalent within the same component); **`%2F` and a literal `/` are not equivalent by default**.

The key point is that `URI.equals` checks **URI syntactic** equality; it does not prove that two HTTP requests will return the same content or hit the same server.

## 3. `URI.equals()` and `URI.hashCode()`: comparison without DNS

For two server-based hierarchical URIs, Java compares scheme and host case-insensitively; for other components, it applies URI equality rules, in which the fragment is also considered. `URI.hashCode()` is consistent with `equals()` and does not require domain name lookups.

| URI Pair | `URI.equals` Result | Why |
| --- | --- | --- |
| `https://EXAMPLE.com/a` and `https://example.com/a` | `true` | Host is case-insensitive |
| `https://example.com/a#one` and `https://example.com/a#two` | `false` | Fragments differ |
| `https://example.com/a` and `https://example.com:443/a` | `false` | Port `-1` differs from `443` |
| `https://example.com/x/./y` and `https://example.com/x/y` | `false` before `normalize()` | Dot-segment is still part of the path |
| `https://example.com/a%2Fb` and `https://example.com/a/b` | `false` | Encoded slash differs from path separator |

`URI.normalize()` processes path segments such as `.` or `..`; it does **not** remove fragments, does not automatically convert default ports, does not turn every percent-encoding into its raw character, and does not guarantee normalization according to each HTTP server's specific rules.

If the requirement is **exact character-by-character comparison of input**, use `String.equals` on the raw string. If **syntactic URI comparison** is needed, use `URI.equals`. If **same HTTP origin comparison** is needed, a dedicated policy for scheme/host/effective port is required; an example is provided below. Do not use `URL.equals` as a substitute for any of these three requirements.

## 4. Why can `URL.equals()` query DNS?

The Java SE 17 documentation for `URL.equals(Object)` specifies that two URLs are equal if their protocol, equivalent host, port, file, and fragment are respectively equal. Two hosts can be considered equivalent if their hostnames resolve to the same IP address; when they cannot be resolved, case-insensitive hostname comparison is used. The documentation explicitly notes that comparing hosts requires name resolution, so the operation can be **blocking**.

Conceptual flow for URLs using the default HTTP(S) handler:

~~~text
url1.equals(url2)
       |
       v
URLStreamHandler compares protocol / host / port / file / fragment
       |
       v
Host comparison may require an IP address
       |
       +-- host already has a matching cached result --> use cached result
       |
       +-- lookup needed --> resolver (hosts file / JVM / OS / DNS ...)
                                 |
                                 v
                     continue computing equals result
~~~

**Not every `equals` call sends a DNS packet**: there are early-exit comparison branches, caches, IP literals, data from the hosts file, or custom protocol handlers. However, code calling `URL.equals` **must not be treated as a pure string operation**, because the API allows network resolution to be requested.

Important consequences:

1. Two different names such as `a.example` and `b.example` can be considered equivalent hosts if they resolve to the same IP and other URL components match. That **does not prove the two HTTP virtual hosts are the same website, have the same access permissions, or share the same TLS certificate**.
2. DNS, hosts files, returned addresses, caches, and network state can change. Comparison behavior depends on the environment, making latency or return values hard to predict when running on different machines or at different times.
3. Lookups can block waiting on the resolver when the network has issues; “just checking equality” can cause request threads, collection processing, or coordination code to stall unexpectedly.
4. If a URL originates from external input, comparing or hashing it can trigger **unintended DNS lookups** for externally specified hostnames. This is a form of network side effect; **it does not mean `equals` itself sends an HTTP request**.

Behavioral details can be customized by a custom protocol handler; the points above are especially important warnings for common HTTP(S) URLs.

## 5. Even `hashCode()`, `sameFile()`, and collections require attention

`URL.hashCode()` is based on the components involved in `URL.equals`; the Javadoc also confirms this operation can be blocking. This is a very common trap:

~~~java
// RISK ILLUSTRATION SNIPPET, do not run without a controlled DNS environment.
// These lines are a fragment for use inside a method with "throws Exception".
URL first = URI.create("https://a.example/report").toURL();
URL second = URI.create("https://b.example/report").toURL();

boolean equal = first.equals(second);  // May resolve hostname.
boolean same = first.sameFile(second); // Ignores fragment, but can still resolve host.

Set<URL> set = new HashSet<>();
set.add(first);                         // HashSet calls URL.hashCode().
Map<URL, String> map = new HashMap<>();
map.put(second, "report");              // HashMap also calls URL.hashCode().
~~~

The snippet above requires `import java.net.URI;`, `import java.net.URL;`, `import java.util.*;`; it illustrates an **anti-pattern**, not something to run to complete the lesson. `URL.sameFile` ignores the fragment, but checking whether URLs refer to the same file still involves protocol/host/port/file via the handler. Do not assume that ignoring the fragment also eliminates the DNS risk.

Even without hash collisions, `HashSet.add` or `HashMap.put` already needs to compute the key's hash. Operations like `contains`, `get`, `remove`, or collection initialization can also invoke `hashCode`/`equals`. If the goal is to index or deduplicate addresses syntactically, replace `URL` with `URI` as the key after defining the required normalization policy.

**Correctness warning:** URL hash/equality is affected by host resolution; do not design long-lived keys based on DNS data that can change over time. A host address pointing to the same IP today does not mean immutable resource identity. URL also does not implement `Comparable<URL>` to provide an ordering equivalent to URI.

## 6. Java 17+ example: safe comparison, deterministic results

The following program **does not call `URL.equals()` or `URL.hashCode()`**. All comparisons and map keys rely on `URI`; `URL` only appears at the final conversion step. Create the exact file `UriComparisonDemo.java`:

~~~java
import java.net.URI;
import java.net.URL;
import java.util.HashMap;
import java.util.Map;

public class UriComparisonDemo {
    public static void main(String[] args) throws Exception {
        URI first = URI.create("https://EXAMPLE.com/manual/guide#top");
        URI same = URI.create("https://example.com/manual/guide#top");
        URI otherFragment = URI.create(
                "https://example.com/manual/guide#bottom");
        URI withDot = URI.create(
                "https://example.com/manual/./guide#top");
        URI explicitPort = URI.create(
                "https://example.com:443/manual/guide#top");

        System.out.println("scheme-host-case: " + first.equals(same));
        System.out.println("fragment-matters: "
                + first.equals(otherFragment));
        System.out.println("dot-before-normalize: "
                + withDot.equals(same));
        System.out.println("dot-after-normalize: "
                + withDot.normalize().equals(same));
        System.out.println("implicit-vs-explicit-port: "
                + same.equals(explicitPort));

        Map<URI, String> index = new HashMap<>();
        index.put(first, "manual");
        System.out.println("map-value: " + index.get(same));

        URL target = same.toURL();
        System.out.println("host: " + target.getHost());
        System.out.println("round-trip: "
                + target.toURI().equals(same));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac UriComparisonDemo.java
java UriComparisonDemo
~~~

Deterministic output of the example:

~~~text
scheme-host-case: true
fragment-matters: false
dot-before-normalize: false
dot-after-normalize: true
implicit-vs-explicit-port: false
map-value: manual
host: example.com
round-trip: true
~~~

**Explanation:** `first` and `same` differ only in host letter case, so the URIs are equal; differing fragments or differing port declarations make URIs unequal. `normalize()` removes the `.` segment from the path. `Map<URI, String>` uses purely syntactic hashing, so no hostname resolution is needed. `same.toURL()` converts a valid HTTP(S) URI into a URL, while `getHost()` simply reads the parsed host; these lines do not require issuing DNS queries for comparison. With custom handlers, the handler's specific behavior must be evaluated separately.

**Do not confuse:** printing `host: example.com` does not prove that the host exists or is reachable; this program intentionally performs no network connectivity checks.

## 7. Comparing “same HTTP origin” is a different problem from `URI.equals`

In HTTP, **origin** considers the combination of **scheme + hostname + effective port**. For example, `https://example.com/docs` and `https://example.com:443/other` share the same conventional origin, yet `URI.equals` returns `false` because the port and path differ. Conversely, two hosts with different names pointing to the same IP **are not automatically the same origin**.

A syntactic way to determine origin without calling DNS (standalone Java 17+ example):

File `HttpOriginDemo.java`:

~~~java
import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;

public class HttpOriginDemo {
    record Origin(String scheme, String host, int port) {}

    static Origin from(URI input) throws URISyntaxException {
        URI uri = input.parseServerAuthority();
        String scheme = uri.getScheme();
        String host = uri.getHost();

        if (scheme == null || host == null ||
                uri.isOpaque() || uri.getRawUserInfo() != null) {
            throw new IllegalArgumentException(
                    "Expected absolute HTTP(S) URI with a host");
        }

        scheme = scheme.toLowerCase(Locale.ROOT);
        if (!scheme.equals("http") && !scheme.equals("https")) {
            throw new IllegalArgumentException("Not HTTP(S)");
        }

        int port = uri.getPort();
        if (port == -1) {
            port = scheme.equals("https") ? 443 : 80;
        }
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("Invalid HTTP port");
        }

        return new Origin(
                scheme, host.toLowerCase(Locale.ROOT), port);
    }

    public static void main(String[] args) throws Exception {
        URI left = URI.create("HTTPS://Example.COM/docs");
        URI right = URI.create("https://example.com:443/docs");

        System.out.println("uri-equals: " + left.equals(right));
        System.out.println("same-origin: "
                + from(left).equals(from(right)));
    }
}
~~~

~~~bash
javac HttpOriginDemo.java
java HttpOriginDemo
~~~

~~~text
uri-equals: false
same-origin: true
~~~

The `from` method calls `parseServerAuthority()` to validate a server-based authority, rejecting non-HTTP(S) URIs, missing hosts, userinfo, and invalid ports. It then maps the default port and compares the record by value. **This is a syntactic origin comparison for ordinary ASCII hosts**, not a complete URL canonicalizer for all IDN/Unicode/IPv6 standards, and certainly not a network connection approval mechanism. Real-world applications must define policies for IDN, trailing dots, IPv6, ports, userinfo, and proxies as needed.

## 8. Choosing the comparison method based on real requirements

| Need | Appropriate approach | Notes |
| --- | --- | --- |
| Are two input strings literally identical? | `rawA.equals(rawB)` | Case-sensitive and sensitive to encoding differences |
| Are two URIs equal under Java rules? | `uriA.equals(uriB)` | Purely syntactic; fragment is considered |
| Using URIs as map/set keys? | `Map<URI, ...>` / `Set<URI>` | Define a `normalize()` policy before storing if needed |
| Comparing same HTTP origin? | Build a scheme + host + effective port key per policy | Do not equate differently named hosts just because DNS returns the same IP |
| Treating two URLs differing only in fragment as “same request target”? | Design a comparison that strips fragment on URI | Do not call `URL.sameFile` just to ignore the fragment |
| Verifying that a host actually has an IP or is reachable? | Resolve/connect **explicitly**, with timeouts and error handling | This is intentional I/O activity, distinct from syntactic comparison |
| Wanting to perform HTTP GET/POST? | Validate the URI, then use an HTTP client or URL at the I/O layer | URI comparison does not replace outbound security checks |

In particular, the fragment (`#...`) is normally not sent as part of an HTTP request target, yet it remains a component of `URI.equals`. If “same downloadable resource” is defined to ignore the fragment, make that decision explicit and construct a new key according to a consistent rule; do not assume all other components can be stripped or reordered.

## 9. Parsing, normalizing, and converting URI ↔ URL in the right place

**Parsing external input:**

~~~java
// Illustrative fragment inside a method; URI.create throws IllegalArgumentException
// if the string does not conform to URI syntax.
URI uri = URI.create("https://example.com/docs");
URI normalized = uri.normalize(); // Only processes path dot-segments
~~~

If you want checked parse errors, use `new URI(text)` and catch `URISyntaxException`. `URI.create(text)` is suitable for controlled constants/configs, as syntax errors are reported via `IllegalArgumentException`.

**Creating a URL when a network-access API is genuinely needed:**

~~~java
// Illustrative fragment inside a method with "throws Exception".
URI uri = URI.create("https://example.com/docs");
URL url = uri.toURL();         // Converts the object, does not perform a GET.
URI back = url.toURI();       // May throw URISyntaxException if the URL
                              // contains syntax invalid for a URI.
~~~

`URI.toURL()` requires an absolute URI and a handler supporting the scheme; not every URI (such as a relative URI or an arbitrary URN) can be converted into a URL for opening a connection. In **Java 20+**, the traditional `URL` constructors are marked deprecated; use `URI` to parse/validate and `toURL()` to convert when needed. This approach also works on Java 17.

**Do not over-“normalize”:** blindly lowercasing the entire path, decoding `%2F` into `/`, sorting query parameters, stripping trailing `/`, or merging all hosts that share an IP can change resource semantics. For APIs requiring HMAC signatures, the path and query may even need to be preserved in exact raw form. `URI.normalize()` is not a comprehensive, universally safe canonicalizer.

## 10. Performance, stability, and security implications

**Performance:** A function that deduplicates a list of URLs looks CPU-only, yet it can still wait on DNS. If the list is processed inside an HTTP request handler or event loop, it increases latency and can block the processing thread. Use `Set<URI>` when the goal is syntactic deduplication.

**Determinism:** DNS returning multiple addresses, IP changes, caching, and resolver failures make resolution-based behavior hard to reproduce. Host → IP changes do not change at the same time as URI values; `URI.equals` therefore offers better predictability for keys and syntactic deduplication.

**Security:** A user-supplied URL can contain an unintended domain name. If an application specifies “no network access” but puts URLs into a `HashSet`, `HashMap`, or `equals`, it can still trigger DNS queries. This differs from SSRF via an HTTP connection, but it is still network activity that must be controlled if a policy blocks lookups.

**Do not treat `URI.equals` as an SSRF solution:** when the application **actually** connects to a user-supplied URI, it must validate scheme, authority, userinfo, hostname, port, redirects, DNS rebinding, and the resolved destination IPs (including loopback/private/link-local addresses depending on policy). Two differently named hosts sharing the same IP can still be two different HTTP origins with different virtual hosts/TLS. Do not rely on `URL.equals` for allowlist checks, authorization, same-origin checks, or resource access control.

**Network boundary:** `URI.equals()` does not resolve hostnames. Conversely, when calling `InetAddress.getByName(host)`, `HttpClient.send(...)`, or `URL.openStream()`, the application has crossed into the I/O layer; timeouts, retries, and address controls must be explicitly defined. `URL.openConnection()` creates a `URLConnection`, while the actual connection may start at access/read methods depending on the handler; do not use it as an example of “pure comparison”.

## 11. Experiment to verify DNS side effects (in a controlled environment)

If you want to observe the side effects of `URL.equals`/`hashCode`, use hostnames you control, a DNS resolver, or a test environment with query logging. **Do not treat a single timing result from a public machine as universal proof.**

1. Choose two test hostnames and record the resolver configuration, JDK version, and existing cache. Ensure no sensitive internal names/addresses need to be kept confidential.
2. In a fresh JVM, create `URI` instances from the hostnames and call `equals`, `hashCode`, and `compareTo`; note that these are syntactic operations. Check the DNS logs to confirm the environment records no lookups from these comparisons.
3. In a separate run, switch to `URL` and call `equals`, `hashCode`, or add them as `HashMap` keys; observe the resolver and latency. Note that URL handlers, JVM/OS caches, hosts files, and DNS servers can cause the number of observed queries to vary.
4. Test a failing/slow resolver or change IPs only in the test environment; compare latency and output. Do not use “`URL.equals` was fast this time” to conclude that the API does not perform DNS.
5. Replace all indexing/dedup logic back with `URI` and verify business behavior. Then perform resolution/connection only at the I/O layer with explicit controls.

The experiment must separate two things: **the API can cause lookups** (confirmed by the Javadoc) and **whether a specific run generates a DNS packet on the wire** (which depends on caches, resolvers, and comparison branches). Do not claim that “every `equals` call generates a DNS packet”.

## 12. Common misconceptions and self-check questions

**Misconception 1 — “`URL.equals` just compares two strings.”** False: it can compare hosts via IP addresses and block waiting for name resolution.

**Misconception 2 — “I don't call `URL.equals`, I only put URLs into a `HashMap`.”** `HashMap` still calls `URL.hashCode`; `URL.hashCode` can also be blocking.

**Misconception 3 — “`URL.sameFile` ignores the fragment, so it doesn't need DNS.”** URL host comparison can still perform name resolution.

**Misconception 4 — “Two hostnames resolving to the same IP are the same HTTP origin.”** False: origin is based on scheme, hostname, and effective port, not the IP returned by DNS.

**Misconception 5 — “`URI.equals` automatically normalizes all equivalent ways of writing a URL.”** False: default ports, dot-segments, encoded slashes, queries, and fragments each have their own rules; only normalize what the business logic actually permits.

**Misconception 6 — “Comparing URIs guarantees there is no SSRF risk later.”** False: the application must still control the actual resolution and connection steps.

Self-check:

- **Question 1:** Why can `HashSet<URL>.add(url)` wait on DNS? **Answer:** because `HashSet` calls `url.hashCode()`, and the `URL` Javadoc allows using host resolution results when computing the hash.
- **Question 2:** Does `URI.create("https://a.example/x").equals(URI.create("https://b.example/x"))` perform a DNS lookup? **Answer:** no; `URI` compares syntactically, so it returns `false` even if the two hosts share the same IP.
- **Question 3:** Does `URI.resolve("../x")` resolve an IP? **Answer:** no; it combines and normalizes the path against the URI context.
- **Question 4:** Should syntactic comparison strip the fragment before storing in a map? **Answer:** only if the business key definition allows it; by default, `URI.equals` considers the fragment.
- **Question 5:** When should you convert to `URL`? **Answer:** when you genuinely need an API that works with URLs/handlers/connections; continue using `URI` for keys and syntactic checks.

## Official documentation

- Java SE 17 — `java.net.URI`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html
- Java SE 17 — `java.net.URL`, especially `equals()`, `hashCode()`, and `sameFile()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URL.html
- Java SE 17 — `java.net.URLStreamHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLStreamHandler.html
- Java SE 20 — notes on deprecated `URL` constructors and `URI.toURL()`: https://docs.oracle.com/en/java/javase/20/docs/api/java.base/java/net/URL.html
- RFC 3986 — URI syntax and normalization/security considerations: https://www.rfc-editor.org/rfc/rfc3986
