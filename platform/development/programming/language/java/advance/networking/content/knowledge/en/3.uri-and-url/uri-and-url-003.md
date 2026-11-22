# Absolute, Relative, Hierarchical, and Opaque URIs in Java

**Topic:** Java Advance - networking  
**Knowledge Group:** URI and URL

A URI (**Uniform Resource Identifier**) is a string used to **identify** a resource or object according to a scheme. A URI can describe a location for access (for example, an HTTP endpoint), a name not directly tied to a network location (for example, a URN), or a reference interpreted relative to a base URI. In Java, **java.net.URI** helps parse, construct, normalize, and combine URIs syntactically; merely creating or parsing a URI does **not** by itself perform DNS resolution, open a socket, or send an HTTP request.

The four terms **absolute**, **relative**, **hierarchical**, and **opaque** describe **two different classification axes** in the Java API, not four mutually exclusive categories. Understanding these two axes properly is the foundation for calling **URI.resolve(...)**, **URI.relativize(...)**, **URI.normalize(...)**, handling path, query, and fragment, and avoiding confusion when combining URLs from user input.

## 1. What is a URI? Distinguishing identification from network access

The following strings can all be represented by **java.net.URI**:

~~~text
https://example.org/docs/guide.html?lang=vi#syntax
mailto:hello@example.org
urn:isbn:9780134685991
../images/logo.svg
/help
//cdn.example.org/assets/app.js
#overview
~~~

- **https://...** has a scheme indicating a common access protocol, authority (host), path, query, and fragment.
- **mailto:...** identifies a mail address under the mailto scheme; not every URI is an HTTP URL.
- **urn:...** identifies by URN, typically without an HTTP host/path structure.
- The strings **../images/logo.svg**, **/help**, **//cdn.example.org/...**, and **#overview** have no scheme; they are relative references and require a context/base URI to determine the full target when needed.

**URI** is the concept of resource identification and reference syntax. **URL** is a way of pointing to a resource via a locating/access mechanism. In Java, **URI** is an immutable syntactic object, whereas **URL** is tied to protocol handling mechanisms. **URI.toURL()** is only appropriate when the URI is absolute and the scheme can be handled as a URL. A **urn:isbn:...** is completely valid as a URI but does not necessarily have a way to be opened directly over the network by a URL handler. Calling **URL.openConnection()** or an HTTP client is what can initiate I/O activity depending on the API and configuration.

## 2. Two independent classification axes in java.net.URI

### Axis A: absolute or relative?

In **java.net.URI**, **isAbsolute() == true** if and only if the URI has a **scheme** (such as **https:**, **file:**, **mailto:**, **urn:**). If there is no scheme, **isAbsolute() == false**, which Java calls a relative URI. Every opaque URI is absolute; every relative URI is hierarchical according to Java's classification.

**Do not confuse a leading /** with absoluteness. The string **/docs/api** has a path starting at the root of an authority but **has no scheme**, so Java still reports **isAbsolute() == false**. Similarly, **//cdn.example.org/a.js** has an authority but lacks a scheme, so it is still relative.

### Axis B: hierarchical or opaque?

According to **java.net.URI**, an **opaque** URI is an **absolute** URI whose **scheme-specific part** (the part after **scheme:**, before the fragment) **does not begin with /**. Java does not split this part into authority/path/query in a hierarchical structure; interpreting it requires understanding the specific scheme.

A **hierarchical** URI is either a relative URI, or an absolute URI whose scheme-specific part begins with **/**. It can be decomposed into **authority**, **path**, **query**, and **fragment** components and supports appropriate path operations.

| Example | isAbsolute() | isOpaque() | Interpretation in Java |
| --- | --- | --- | --- |
| **https://example.org/a** | true | false | Absolute, hierarchical |
| **file:/tmp/data.txt** | true | false | Absolute, hierarchical |
| **mailto:hello@example.org** | true | true | Absolute, opaque |
| **urn:isbn:9780134685991** | true | true | Absolute, opaque |
| **https:report** | true | true | Absolute, opaque **according to Java**, even though this is not a normal HTTPS address |
| **docs/page.html** | false | false | Relative, hierarchical |
| **../img/logo.svg** | false | false | Relative, hierarchical |
| **/help** | false | false | Relative, hierarchical; path begins with / |
| **//cdn.example.org/app.js** | false | false | Relative, hierarchical; has authority, no scheme yet |
| **?page=2** or **#part** | false | false | Relative, hierarchical; reference only changes query/fragment depending on resolution |

**There is no URI that is both relative and opaque under Java's definition.** “Absolute” refers to **whether a scheme is present**; “hierarchical/opaque” refers to **how the scheme-specific part is parsed**. Therefore, one cannot simply say “an absolute URI is hierarchical” or “opaque is relative”.

**Note on standard terminology:** **RFC 3986** has a separate **absolute-URI** syntax that does not include a fragment, whereas the Java method **URI.isAbsolute()** only checks for a scheme and still returns **true** for **https://example.org/a#part**. When comparing standard specifications with the Java API, be clear whether you are referring to the RFC grammar or the Java predicate.

## 3. Structure of a hierarchical URI

An easily recognizable form is:

~~~text
[scheme:][//authority]path[?query][#fragment]

https://user@example.org:8443/docs/a.html?lang=vi#part
└scheme┘└──────authority──────┘└──path───┘└query┘└fragment┘
~~~

In the form with an authority, **authority** can include **userinfo@host:port**. Components are commonly accessed via the API:

| Component | Example | API |
| --- | --- | --- |
| Scheme | **https** | **getScheme()** |
| Authority | **user@example.org:8443** | **getAuthority()**, **getRawAuthority()** |
| Userinfo | **user** | **getUserInfo()** |
| Host | **example.org** | **getHost()** |
| Port | **8443** | **getPort()**, returns **-1** if undefined |
| Path | **/docs/a.html** | **getPath()**, **getRawPath()** |
| Query | **lang=vi** | **getQuery()**, **getRawQuery()** |
| Fragment | **part** | **getFragment()**, **getRawFragment()** |

In the URI **https://example.org/docs/a.html?lang=vi#part**, **?** begins the query and **#** begins the fragment. The fragment is used to point to a part within a resource representation; it is normally **not sent in an HTTP request-target**. The query belongs to the URI, though not every scheme uses the query the way HTTP does. **getHost()** can return **null** even if the string has an authority if the authority cannot be parsed as a server-based authority; when a standard host/port is required, see **parseServerAuthority()** or validate the structure explicitly.

You must distinguish **raw** from **decoded**:

~~~java
URI uri = URI.create("https://example.org/a%20b?q=x%2Fy");
// uri.getRawPath()  -> "/a%20b"
// uri.getPath()     -> "/a b"
// uri.getRawQuery() -> "q=x%2Fy"
// uri.getQuery()    -> "q=x/y"
~~~

The snippet above consists of illustrative expressions, not a standalone Java program. **getRawPath()** preserves the percent-encoding of the path; **getPath()** returns the decoded part. Do not concatenate decoded data directly back into a URI string without properly encoding and parsing each component.

Some easily overlooked points:

- **Host** can be a domain name, IPv4, or IPv6 in square brackets (for example **https://[2001:db8::1]:8443/a**).
- **Authority** is not always present; the hierarchical absolute URI **file:/tmp/a** has a path without needing a host.
- **A path starting with /** and **a URI having a scheme** are two different things.
- A **:** in the first segment of a relative path can be interpreted as a scheme. **notes:today.txt** is treated by Java as absolute/opaque with scheme **notes**; use **./notes:today.txt** if you genuinely want a relative path containing a colon.
- **URI** only parses syntax; **InetAddress**, DNS, and network connections belong to separate operations.

## 4. Opaque URIs: the part after the scheme is not a hierarchical path

Examples:

~~~text
mailto:hello@example.org?subject=Welcome
urn:isbn:9780134685991
news:comp.lang.java
~~~

In Java, **URI.create("mailto:hello@example.org?subject=Welcome")** has:

- **getScheme()** is **mailto**.
- **isAbsolute()** is **true** and **isOpaque()** is **true**.
- **getSchemeSpecificPart()** is **hello@example.org?subject=Welcome**.
- **getPath()**, **getQuery()**, and **getHost()** are **null** because Java does not parse an opaque URI into hierarchical components, even though the mailto scheme itself has its own rules for interpreting **?**.

You should use **getSchemeSpecificPart()** or **getRawSchemeSpecificPart()** to retrieve the scheme-specific part, then process it according to the scheme's rules; do **not** look for a mail address using **getHost()**, and do **not** assume that a **?** in an opaque URI will appear in **getQuery()**.

Path-based transformations do not have the same meaning for opaque URIs: **normalize()** does not alter opaque content; if you call **opaqueBase.resolve(relativeReference)**, Java returns the passed-in reference rather than inferring a directory tree for a mail address or URN. Opaqueness is a **parsing rule of java.net.URI**, not a claim that every scheme lacks internal structure. For example, the **mailto** scheme still has its own structure, just not the generic authority/path/query structure of the Java API.

## 5. Relative URIs and resolving against a base

A relative reference is only fully meaningful when the **base URI** is known. For example, the current document is:

~~~text
https://example.org/docs/guide/index.html?old=1
~~~

A relative path without a leading **/** is normally appended to the **containing directory** of the base document, rather than appended to the end of the filename. With **java.net.URI.resolve(...)**, the following cases yield:

| Reference | base.resolve(reference) | Meaning |
| --- | --- | --- |
| **chapter.html** | **https://example.org/docs/guide/chapter.html** | Same base directory |
| **../img/logo.svg** | **https://example.org/docs/img/logo.svg** | Up one directory level |
| **/help** | **https://example.org/help** | Root-path of the same authority |
| **//cdn.example.org/app.js** | **https://cdn.example.org/app.js** | Replace authority, keep **https** scheme |
| **#intro** | **https://example.org/docs/guide/index.html?old=1#intro** | Replace fragment, keep base path and query |
| **https://other.example/a** | **https://other.example/a** | Already an absolute URI; not combined with base |
| **?page=2** | **https://example.org/docs/guide/?page=2** | Specific result of **java.net.URI.resolve** for a query-only reference in this example |

**Note on the query-only case:** Java's **URI.resolve("?page=2")** per the **java.net.URI** implementation and documentation can differ from the result produced by a browser or the **RFC 3986** resolution algorithm for the same base. With a base having filename **index.html**, Java returns the directory path **/docs/guide/** in the example above. Do not extrapolate from browser rules; test the actual API and JDK being used. Similarly, an empty relative reference (**""**) should not be assumed by default to be a query-replacement operation intended by the application.

Resolving only **computes a new URI**, without querying the network or checking whether the target exists. **base.resolve("https://other.example/a")** returns the absolute reference as-is even if the host is different. If the reference data is user-supplied, this can change the target domain and create a redirect/SSRF vulnerability if the program uses the result to open a connection without validation.

### Easily confused terms in relative references

- **Relative-path reference**: **assets/app.js**, **../img.png**, **./notes.txt** — depends on the base directory.
- **Absolute-path reference**: **/api/users** — path measured from the authority root, **does not** carry a scheme, so the URI is still relative.
- **Network-path reference**: **//cdn.example.org/app.js** — specifies an authority, inherits the scheme.
- **Query-only/fragment-only reference**: **?lang=vi**, **#summary** — affects the corresponding component according to resolver rules.

“Absolute-path” is a term about the **path**, not synonymous with **absolute URI**.

## 6. normalize() and relativize(): how do they differ from resolve()?

**normalize()** processes **.** and **..** path segments in a hierarchical URI, for example:

~~~text
https://example.org/a/./b/../c
                    ↓ normalize()
https://example.org/a/c
~~~

**normalize()** does not query a server, does not check whether a file exists, does not follow redirects, does not automatically upgrade to HTTPS, does not automatically eliminate all percent-encoding differences, and is not a complete path-traversal prevention tool. For opaque URIs, normalization does not change the scheme-specific part along a path tree. Do not trust normalizing an untrusted string as sufficient to grant file access or select a safe origin.

**relativize(target)** attempts to shorten a target URI into a relative reference with respect to a base. Java only does this when conditions match, specifically when **the scheme and authority match** and the base path is a proper prefix of the target path. For example:

~~~text
base:    https://example.org/docs/
target:  https://example.org/docs/api/start.html
result:  api/start.html
~~~

If the conditions are not met, **relativize(...)** may return the target unchanged. It is **not** a general algorithm that always produces the shortest **../...** string. In particular, you should normalize intentionally and then inspect the result, and never use relativize as an access control check or a guarantee that two URIs point to the same resource.

Quick comparison:

| Method | Input and role | Example |
| --- | --- | --- |
| **isAbsolute()** | Checks whether a scheme is present | **https://x/a** → true |
| **isOpaque()** | Checks Java opaque classification | **mailto:a@b** → true |
| **resolve(ref)** | Combines base and reference | **https://x/dir/** + **a** → **https://x/dir/a** |
| **normalize()** | Collapses dot-segments in a hierarchical path | **/a/./b/../c** → **/a/c** |
| **relativize(target)** | Strips a matching prefix relative to base | **https://x/dir/** → **https://x/dir/a** becomes **a** |

## 7. Complete illustrative Java 17+ program

Create the file **UriKindsDemo.java**:

~~~java
import java.net.URI;

public class UriKindsDemo {
    public static void main(String[] args) {
        URI absolute = URI.create("https://example.org/docs/guide.html?lang=vi#intro");
        URI relative = URI.create("../img/logo.svg");
        URI opaque = URI.create("mailto:hello@example.org?subject=Hi");
        URI base = URI.create("https://example.org/docs/guide/index.html?old=1");

        describe("HTTP", absolute);
        describe("Relative", relative);
        describe("Mail", opaque);

        System.out.println("Resolve file: " + base.resolve("../img/logo.svg"));
        System.out.println("Resolve root: " + base.resolve("/help"));
        System.out.println("Resolve authority: " + base.resolve("//cdn.example.org/app.js"));
        System.out.println("Resolve fragment: " + base.resolve("#intro"));
        System.out.println("Resolve query-only: " + base.resolve("?page=2"));
        System.out.println("Normalize: " +
                URI.create("https://example.org/a/./b/../c").normalize());
        System.out.println("Relativize: " +
                URI.create("https://example.org/docs/")
                        .relativize(URI.create("https://example.org/docs/api/start.html")));
    }

    private static void describe(String label, URI uri) {
        System.out.printf("%s: absolute=%s, opaque=%s, scheme=%s, path=%s, query=%s%n",
                label, uri.isAbsolute(), uri.isOpaque(), uri.getScheme(),
                uri.getPath(), uri.getQuery());
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac --release 17 -encoding UTF-8 UriKindsDemo.java
java UriKindsDemo
~~~

**Expected stdout, verified with JShell on JDK 24:**

~~~text
HTTP: absolute=true, opaque=false, scheme=https, path=/docs/guide.html, query=lang=vi
Relative: absolute=false, opaque=false, scheme=null, path=../img/logo.svg, query=null
Mail: absolute=true, opaque=true, scheme=mailto, path=null, query=null
Resolve file: https://example.org/docs/img/logo.svg
Resolve root: https://example.org/help
Resolve authority: https://cdn.example.org/app.js
Resolve fragment: https://example.org/docs/guide/index.html?old=1#intro
Resolve query-only: https://example.org/docs/guide/?page=2
Normalize: https://example.org/a/c
Relativize: api/start.html
~~~

**Explanation of key points in the output:**

1. **HTTP** has scheme **https** and a scheme-specific part starting with **/**, so it is absolute/hierarchical; **getPath()** and **getQuery()** work normally.
2. **Relative** has no scheme, yet is still hierarchical; a path containing **..** remains unresolved path data.
3. **Mail** is absolute/opaque; **getPath()** and **getQuery()** return **null**, even though **?** is present in the mailto scheme-specific part.
4. **Resolve file/root/authority** demonstrate, respectively, replacing a path segment relative to base, taking a path from root, and using a new authority with the existing scheme.
5. **Resolve query-only** illustrates a specific nuance of the Java API to watch out for when working with a reference that has a query and an empty path.
6. **Normalize** only processes dot-segments; **Relativize** strips the matching prefix and returns **api/start.html**.

The values in the demo are only parsed and combined **in memory**, with no sockets created, no HTTP requests sent, and no DNS queries made.

## 8. Creating URIs and percent-encoding properly

**URI.create(String)** is suitable for a URI string that already has valid syntax; if syntactically invalid, it throws **IllegalArgumentException** (usually caused by **URISyntaxException**). When processing input where syntax errors need to be handled, you can use **new URI(String)** and catch **URISyntaxException**. For example, **https://example.org/a b** contains a raw space, so it is invalid as a URI string and needs encoding.

Multi-argument **URI** constructors support escaping characters within individual components. Illustrative example (placed in a method declaring **throws URISyntaxException** or handling the exception):

~~~java
URI search = new URI("https", null, "example.org", -1,
        "/search", "q=a b", null);
System.out.println(search); // https://example.org/search?q=a%20b
~~~

The above is a **snippet**, not a standalone program. When you already have a percent-encoded URI string, do not automatically re-encode the entire string, as this easily causes double encoding (for example, **%20** becomes **%2520**). **URLEncoder** is intended for the **application/x-www-form-urlencoded** format (typically for form/query parameters), not as an API to encode an entire URL/URI including scheme, slashes, host, query, and fragment.

Distinguish the operations:

- **getRawPath() / getRawQuery()**: preserve percent escapes from the URI.
- **getPath() / getQuery()**: retrieve components after decoding as defined by the API.
- **toString()**: text representation of the URI; may preserve Unicode characters as-is depending on the URI.
- **toASCIIString()**: representation using ASCII characters, percent-encoding non-ASCII characters as needed.

Do not use manual string concatenation to assemble untrusted components, such as **"https://" + host + "/" + path**. Proper construction requires handling scheme, authority, path, query, and fragment separately.

## 9. Using URIs in Java networking without opening the wrong destination

The fact that a URI parses **does not mean that URI is allowed to be accessed**. In an application that receives user-supplied URIs and uses them to make HTTP calls, redirect, or read resources, separate three layers:

1. **Syntax**: Is the string valid with **new URI(...)** or **URI.create(...)**?
2. **Policy**: Is the scheme allowed (typically **https**), are the host/port permitted, and is there any unusual **userinfo** or suspicious authority or opaque form?
3. **Actual access**: Do DNS, target IP address, proxy, redirects, TLS, firewall, and HTTP response match expectations?

A reasonable input validation pattern when requiring an absolute HTTP URL is: **isAbsolute() == true**, **isOpaque() == false**, the scheme is in a defined allowlist, **getHost() != null**, plus further policies on host/port, credentials, redirects, and network destination. Checking only **isAbsolute()** is wrong: **mailto:x@y** or **https:report** are also absolute. Checking only **getAuthority()** also does not guarantee that a server-based host was parsed.

With relative URI references, **URI.resolve(...)** can return a URI on a **different host** if the reference is absolute or starts with **//**. For example, an internal HTTPS base resolved with **//untrusted.example/path** becomes an HTTPS URI on the untrusted host. Therefore, **re-validate the final result after resolve**, and validate every redirect before actually connecting. If SSRF prevention is required, checking scheme/host is only the first step; you also need to handle DNS/internal IPs, redirects, and proxies according to the application's threat model.

**Do not use URI.normalize() as a path-traversal filter.** Percent-encoding, filesystem path rules, server/proxy normalization, and decoding at different layers can produce equivalent or dangerous representations. You must validate and restrict access rights on the actual target path, using the API of the storage/filesystem or routing framework in use.

## 10. Common mistakes and self-check

| Misconception | Reality in Java |
| --- | --- |
| **/api** is an absolute URI | False: the path is absolute, but it lacks a scheme so **isAbsolute() == false** |
| **//host/path** has a scheme | False: an authority may be present, but no scheme yet |
| Every URI with a scheme is hierarchical | False: **mailto:...**, **urn:...**, **https:report** are all opaque according to **java.net.URI** |
| **getQuery()** always sees the part after **?** | False for opaque URIs: that part belongs to the scheme-specific part |
| **URI.resolve()** always appends the reference after the base | False: it can replace the path, replace the authority, return an absolute reference as-is, or have specific behavior for query-only references |
| **normalize()** checks whether a URI exists or is safe | False: it only transforms hierarchical path syntax; it is not network/security validation |
| **relativize()** always produces **../...** | False: if path/prefix, scheme, or authority do not match, it may return the target unchanged |
| **URI.create(...)** opens a connection | False: it only parses in memory |
| **URL** and **URI** can always be converted back and forth | False: not every URI scheme has a suitable URL handler |
| Percent-encode an entire URI with **URLEncoder** | False: it can turn scheme/path delimiters into data |

**Short self-check exercises:**

1. How does Java classify **/docs/v1**, **https://example.org/docs**, **mailto:x@y**, and **https:notes** along the two axes **isAbsolute/isOpaque**?
2. What URIs does the base **https://example.org/a/b/index.html** resolve **../img.png**, **/support**, and **//cdn.example.org/js/app.js** to?
3. If you want to accept an HTTPS URL for an HTTP client, why is checking only **isAbsolute()** insufficient?
4. Why does **mailto:x@y?subject=Hello** contain **?** yet **getQuery()** still returns **null**?
5. When a URI is used to redirect to a specified host, why must the result be validated **after** resolving?

**Remember:**  
- **Absolute/relative** answers “**does it have a scheme?**”.  
- **Hierarchical/opaque** answers “**can Java parse a generic authority/path/query structure?**”.  
- **resolve** combines a reference with a base; **normalize** handles dot-segments; **relativize** shortens a matching path-prefix.  
- **URI is syntax/identification**; security validation and executing network I/O are separate responsibilities.

**Standard references:** [java.net.URI (Java SE 21 Javadoc)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URI.html) and [RFC 3986 — Uniform Resource Identifier: Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986). When the two sources differ on a resolution detail, prioritize checking the behavior of **java.net.URI** if your code uses this API.