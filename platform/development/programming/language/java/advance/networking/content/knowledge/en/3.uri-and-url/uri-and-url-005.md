# `resolve`, `relativize`, and `normalize` When Combining Resource Paths Using Java URI

In Java applications, the path to a resource is often not fixed: an HTML document links to images, CSS, or another document; a REST client builds URLs from a root endpoint; a site generator builds relative links between pages. String concatenation like `base + "/" + child` is error-prone when the base already has or does not have a `/` character, when the reference contains `../`, or when the path starts with `/`, `?`, `#`, or `//`.

`java.net.URI` provides three important syntactic operations:

- **`resolve`:** transforms a reference URI into a resulting URI based on a base URI.
- **`relativize`:** finds a relative URI against a base URI if the two URIs have compatible structures.
- **`normalize`:** normalizes `.` and `..` segments in the *path* of a hierarchical URI.

These three operations **do not access the network, do not check whether the resource exists, and do not automatically guarantee safety when input is untrusted**. To use them properly, you must understand URI structure, how to choose a base URI, and the limitations of each operation.

## 1. A URI is a structure, not just a string with `/`

A hierarchical URI typically has the form:

~~~text
scheme://authority/path/to/resource?query#fragment
https://docs.example.test/guide/page.html?lang=vi#examples
│       │                 │              │       │
scheme  authority         path           query   fragment
~~~

In Java:

~~~java
URI uri = URI.create("https://docs.example.test/guide/page.html?lang=vi#examples");
System.out.println(uri.getScheme());   // https
System.out.println(uri.getAuthority()); // docs.example.test
System.out.println(uri.getPath());     // /guide/page.html
System.out.println(uri.getQuery());    // lang=vi
System.out.println(uri.getFragment()); // examples
~~~

This is an **illustrative snippet** placed inside a Java method with `import java.net.URI;`, not a standalone program. `scheme` such as `https`, `file`; `authority` may include userinfo, host, port; `path` uses `/` to separate segments; `query` and `fragment` are separate components. Therefore, you cannot process a URI properly by arbitrarily stripping strings containing `?` or `#`.

Reference types to recognize:

| Reference | Example | Meaning when used with an HTTP base URI |
| --- | --- | --- |
| Absolute URI with scheme | `https://cdn.example.test/a.svg` | Already has its own target; `resolve` preserves it |
| Relative URI with path | `img/logo.svg`, `../style.css` | Combined with the directory of the base path and then normalized |
| Root-relative reference | `/assets/a.svg` | Keeps the base scheme/authority, replaces the path from root |
| Authority-relative reference | `//cdn.example.test/a.svg` | Inherits the base scheme but replaces the authority |
| Fragment-only | `#section2` | Keeps the base path and other components, replaces the fragment per Java's contract |
| Query-only | `?lang=vi` | Need to check specific `URI.resolve` behavior; Java has cases whose results differ from browser intuition |

An **absolute URI** is determined by having a *scheme* (`isAbsolute()`), not by whether the path has a leading `/` character. `mailto:help@example.test` is also an absolute URI, but it is an **opaque URI**, different from a hierarchical URI; do not mechanically apply path combination to it. For `URI.create("mailto:help@example.test")`, `isOpaque()` is `true`.

`URI` is immutable: every operation returns a `URI` object; calling `uri.normalize();` and discarding the return value will not modify the `uri` variable.

## 2. `resolve`: combining a reference with a base URI

Syntax:

~~~java
URI result = base.resolve(referenceUri);
URI result2 = base.resolve("images/icon.svg");
~~~

The overload accepting a `String` parses the string into a `URI` via `URI.create(...)` and then applies `resolve`. A syntactically invalid string throws `IllegalArgumentException`. If the reference URI is already absolute, the result keeps that URI. If the base is an opaque URI, `resolve` also returns the reference URI according to the specification.

### 2.1. A trailing `/` on the base is a critical decision

Consider three bases:

~~~text
https://docs.example.test/guide/
https://docs.example.test/guide
https://docs.example.test/guide/start.html
~~~

When calling `resolve("img/logo.svg")`:

| Base | Result |
| --- | --- |
| `https://docs.example.test/guide/` | `https://docs.example.test/guide/img/logo.svg` |
| `https://docs.example.test/guide` | `https://docs.example.test/img/logo.svg` |
| `https://docs.example.test/guide/start.html` | `https://docs.example.test/guide/img/logo.svg` |

Explanation: the algorithm replaces the **last segment** of the base path when appending a relative path. A trailing `/` at the end of a path means the next location lies inside the `guide/` directory; whereas `/guide` without a trailing slash is treated as a resource segment and replaced by `img/logo.svg`. A path ending in `start.html` also has its `start.html` segment replaced.

This is a very easy place to introduce bugs in programs that read `baseUrl` from a configuration file. If the configuration represents a *resource directory*, normalize the **semantics** of the configuration into a base ending with `/`, such as `https://docs.example.test/guide/`. Do not blindly append a slash to the URL of a document that is `.../index.html`, because that would turn it into a different path.

### 2.2. Not all reference types simply append to the end

Take `base = https://docs.example.test/guide/`:

| Reference | Result of `base.resolve(reference)` | Reason |
| --- | --- | --- |
| `img/logo.svg` | `https://docs.example.test/guide/img/logo.svg` | Relative path |
| `../shared/style.css` | `https://docs.example.test/shared/style.css` | `..` moves up one level and then normalizes |
| `/public/logo.svg` | `https://docs.example.test/public/logo.svg` | Absolute path within the same origin |
| `//cdn.example.test/x.svg` | `https://cdn.example.test/x.svg` | New authority, inherits `https` scheme |
| `https://other.example.test/x.svg` | `https://other.example.test/x.svg` | Reference is already absolute |
| `#toc` | `https://docs.example.test/guide/#toc` | Fragment-only, preserves the base path |

Do not write `URI.create("/public/logo.svg")` and assume it is an absolute URI: it **has no scheme**. `/public/logo.svg` only has an *absolute path*, so when `resolve` is called, it still takes the scheme/authority from the base.

### 2.3. Query-only and empty string cases in Java

With `baseFile = https://docs.example.test/guide/start.html`:

~~~text
baseFile.resolve("#section2")
  => https://docs.example.test/guide/start.html#section2

baseFile.resolve("?lang=vi")
  => https://docs.example.test/guide/?lang=vi

baseFile.resolve("")
  => https://docs.example.test/guide/
~~~

The last two cases are surprising if readers assume they necessarily reference `start.html` itself. The Java 17 Javadoc describes the relative path resolution rule as taking the base path **excluding the last segment**; fragment-only references are handled specially. Run the example on your target JDK before designing an operation that only modifies the query of a document. If the goal is to keep the path unchanged and only replace the query, **rebuild the URI from its parsed components** using an appropriate constructor, while checking escaping rules; do not rely on the assumption that `resolve("?x=1")` will preserve the filename path.

### 2.4. Operational rules

When building paths from a directory, a sound structure is:

~~~text
baseDirectoryUri (ending with /)
         │
         ├── resolve(relativeResource)
         │           │
         │           └── process ., .. according to URI rules
         │
         └── resulting URI
~~~

Avoid string concatenation `base.toString() + resource`. It will produce `...guideimg/logo.svg` when a slash is missing, or `...guide//img/logo.svg` when there is an extra slash, or leave `..` segments in unexpected ways. Additionally, `resolve` already includes a path normalization step when resolving relative references; call `normalize()` explicitly when you need to express a canonical path policy for other inputs/URIs.

## 3. `normalize`: collapsing `.` and `..` in the path

`URI.normalize()` applies to **hierarchical URIs**:

1. Remove segments equal to `.`.
2. If a `..` segment has a preceding segment that is not `..`, remove that pair of segments and continue.
3. For a relative path whose first segment contains a colon, a leading `.` may be prepended so that it is not misparsed as a scheme when re-parsed.

Example:

~~~text
https://docs.example.test/a/b/../c/./d
         normalize()
https://docs.example.test/a/c/d
~~~

This is a collapse **according to URI syntax**, not an operation on actual files or a directory system. It does not perform DNS lookups, does not know about symlinks, does not resolve access permissions, and does not confirm that the paths point to the same resource on the server.

| Input | Result / what to remember |
| --- | --- |
| `/a/b/../c` | `/a/c` |
| `/a/./b` | `/a/b` |
| `../up/./a` | `../up/a` — keeps leading `..` when there is no preceding segment to cancel it out |
| `https://x.test/a/%2E%2E/b` | Still contains `%2E%2E` — `normalize` **does not** decode percent-escapes before processing segments |
| `https://x.test/a/../b?x=./y#./z` | Only the path changes; `?x=./y` and `#./z` are not path segments |
| `mailto:team@example.test` | Opaque URI, `normalize` makes no changes |

In the path illustration table, strings like `/a/c` represent the path component and do not require a scheme. For URIs with a trailing slash, check directory/file semantics carefully; `normalize` is not responsible for deciding whether a resource is a directory or a file.

It is necessary to distinguish three concepts often loosely called “normalize”:

- **Path syntax normalization:** `URI.normalize()` processes `.` / `..` according to URI syntax.
- **Encoding/decoding:** `%2E`, `%2F`, `%20`, and UTF-8 characters belong to octet representation; `normalize` does not convert them into characters to further canonicalize them. `getRawPath()` preserves escaping, while `getPath()` returns the decoded path.
- **Resource canonicalization:** host, route, filesystem, symlinks, redirects, URL rewrites, query ordering, and server policies can make two URIs point to the same resource or different resources; `URI.normalize()` cannot confirm this.

Important security example:

~~~java
URI input = URI.create("https://files.example.test/public/%2e%2e/private.txt");
System.out.println(input.normalize());
System.out.println(input.getRawPath());
System.out.println(input.getPath());
~~~

Output (when run inside a valid Java method):

~~~text
https://files.example.test/public/%2e%2e/private.txt
/public/%2e%2e/private.txt
/public/../private.txt
~~~

The result shows that `normalize()` is **not** a path traversal prevention mechanism: a downstream processing layer may decode `%2e%2e` into `..`. If using URIs to control resource scope, you must validate and restrict input **before** combining; understand the web server's decoding behavior and do not allow arbitrary changes to authority/scheme/path.

## 4. `relativize`: obtaining a relative path when sharing a base

Syntax:

~~~java
URI relative = base.relativize(target);
~~~

For two hierarchical URIs, if the scheme and authority are compatible, and the base path is a **prefix** of the target path, `relativize` strips the base path prefix to produce a relative URI, preserving the target's query and fragment if present. If **not satisfied**, it returns the target URI itself instead of constructing a `../...` path.

~~~text
base   = https://docs.example.test/guide/
target = https://docs.example.test/guide/img/logo.svg
result = img/logo.svg
~~~

However:

~~~text
base   = https://docs.example.test/guide/
target = https://docs.example.test/shared/site.css
result = https://docs.example.test/shared/site.css
~~~

`relativize` should not be described as an algorithm for finding the shortest relative path between two directories. It **does not automatically generate** `../shared/site.css` in the second case. To build relative links between locations without a prefix relationship, you need to choose an appropriate common parent base or resolve according to application routing rules; do not expect `relativize` to compute the tree automatically.

For consistent logic, common practice is to normalize **both base and target** when comparing paths known to be valid:

~~~java
URI normalizedBase = base.normalize();
URI normalizedTarget = target.normalize();
URI relative = normalizedBase.relativize(normalizedTarget);
~~~

When the prefix relationship matches and the URIs are normalized, you can verify the round-trip:

~~~java
URI restored = normalizedBase.resolve(relative);
System.out.println(restored.equals(normalizedTarget));
~~~

If `relativize` returns an absolute URI due to differing origins or path prefixes, calling `resolve` afterwards can still return the target, but in that case **there is no relative link**. Check `relative.isAbsolute()` (and authority if needed) if your application contract requires producing a relative URI.

**Do not use `relativize` to prove access permissions.** It operates on syntactic structure and can be affected by differences in path representation (encoding, slashes, letter casing). For security enforcement, you need a separate policy and an understanding of the URL the server will actually process.

## 5. Runnable Java 17+ program: observing all three operations

Create the file **`UriOperationsDemo.java`**:

~~~java
import java.net.URI;

public class UriOperationsDemo {
    public static void main(String[] args) {
        URI baseFile = URI.create(
                "https://docs.example.test/guide/start.html");
        URI baseDir = URI.create(
                "https://docs.example.test/guide/");
        URI baseWithoutSlash = URI.create(
                "https://docs.example.test/guide");

        URI target = baseDir.resolve("img/../css/site.css").normalize();

        System.out.println("file: "
                + baseFile.resolve("img/logo.svg"));
        System.out.println("dir: "
                + baseDir.resolve("img/logo.svg"));
        System.out.println("no slash: "
                + baseWithoutSlash.resolve("img/logo.svg"));
        System.out.println("up: "
                + baseDir.resolve("../shared/style.css"));
        System.out.println("root: "
                + baseDir.resolve("/public/logo.svg"));
        System.out.println("new authority: "
                + baseDir.resolve("//cdn.example.test/x.svg"));
        System.out.println("normalized: " + target);
        System.out.println("relative: " + baseDir.relativize(target));
        System.out.println("different tree: " + baseDir.relativize(
                URI.create("https://docs.example.test/shared/site.css")));
        System.out.println("query only: "
                + baseFile.resolve("?lang=vi"));
        System.out.println("fragment: "
                + baseFile.resolve("#section2"));
    }
}
~~~

Compile/run with JDK 17 or higher:

~~~bash
javac --release 17 UriOperationsDemo.java
java UriOperationsDemo
~~~

Exact stdout:

~~~text
file: https://docs.example.test/guide/img/logo.svg
dir: https://docs.example.test/guide/img/logo.svg
no slash: https://docs.example.test/img/logo.svg
up: https://docs.example.test/shared/style.css
root: https://docs.example.test/public/logo.svg
new authority: https://cdn.example.test/x.svg
normalized: https://docs.example.test/guide/css/site.css
relative: css/site.css
different tree: https://docs.example.test/shared/site.css
query only: https://docs.example.test/guide/?lang=vi
fragment: https://docs.example.test/guide/start.html#section2
~~~

The entire example only parses and transforms URIs **in memory**, without sending HTTP requests; the `example.test` hosts are illustrative data, not endpoints to access. The results show:

- `baseDir` and `baseFile` produce the same link `img/logo.svg` because they share the same parent directory.
- `baseWithoutSlash` produces a different result because `guide` is treated as the last segment to be replaced.
- `../` moves up one level; `/public/...` sets the path from root; `//cdn...` replaces the authority.
- `normalize` turns `img/../css` into `css`.
- `relativize` only shortens the path when the target path lies under the base prefix; a target under `shared` keeps the absolute URI.
- `?lang=vi` and `#section2` behave differently with `baseFile`.

You can use this example as a regression test when upgrading the JDK or changing base URL conventions in your system.

## 6. Choosing the right operation for real-world scenarios

| Need | Approach |
| --- | --- |
| From a document directory, create relative image/CSS links | Base **ending with `/`**, call `base.resolve(relativeRef)` |
| From an HTML page, create links to another page/image | Use the page's full URI as the base; remember the file's last segment will be replaced |
| Collapse `a/./b/../c` | `URI.normalize()`, understanding that it only normalizes syntactic paths |
| Create a relative link from a directory to a resource underneath it | `base.normalize().relativize(target.normalize())`, check whether the result is actually relative |
| Change scheme/authority | Use a URI with the target scheme/authority or a constructor designed for components; do not assume a reference always belongs to the same host |
| Add or replace query parameters | Use a component-aware URI builder/constructor; do not concatenate `?` strings or apply `resolve("?x=1")` by intuition |
| Work with files on disk | Use `java.nio.file.Path.resolve` / `Path.normalize`; convert via `Path.toUri()` / `Path.of(fileUri)` when a file URI is actually needed |
| Protect a resource directory or outbound HTTP origin | Validate input, enforce scheme/host/port/path policies, and account for downstream decoding; `normalize` is not a standalone security measure |

### 6.1. `URI` and `Path` are not identical

`URI.resolve` operates on URI components according to URI resolution rules; `Path.resolve` operates on filesystem paths according to the provider/OS. For actual files, the following Java snippet is more appropriate than concatenating a `file:` URL from `Path.toString()`:

~~~java
import java.nio.file.Path;

Path root = Path.of("docs", "guide");
Path file = root.resolve("images").resolve("logo.svg").normalize();
System.out.println(file);
~~~

This is an **illustrative snippet**, and no fixed stdout is stated because path separators and working directories depend on the OS. When you need a file URI, use `file.toAbsolutePath().toUri()`; when you need to create a `Path` from a valid file URI, use `Path.of(fileUri)`. Do not use `URI.create(path.toString())` to infer a file URI from an OS path, especially on Windows with drive letters and `\` characters. `Path.normalize` is also only syntactic normalization and does **not** automatically resolve symlinks; if checking containment for real files, you must consider `toRealPath()`, permissions, filesystem changes, and race conditions.

### 6.2. Character escaping: `getRawPath()` differs from `getPath()`

Take a URI containing encoded characters:

~~~java
URI uri = URI.create("https://docs.example.test/assets/a%2Fb.svg");
System.out.println(uri.getRawPath()); // /assets/a%2Fb.svg
System.out.println(uri.getPath());    // /assets/a/b.svg
~~~

`getRawPath()` preserves percent-escape sequences; `getPath()` decodes them. If you need to preserve segment boundaries or inspect the raw string, do not unwittingly replace `getRawPath` with `getPath`. The receiving side might decode it again, leading to routing and security discrepancies.

`URI.create("https://docs.example.test/my report.pdf")` is **syntactically invalid** because it contains an unescaped space, throwing `IllegalArgumentException`. Component-based constructors can quote invalid characters:

~~~java
URI uri = new URI(
        "https", "docs.example.test", "/my report.pdf", null, null);
System.out.println(uri); // https://docs.example.test/my%20report.pdf
~~~

This snippet requires a context with `throws java.net.URISyntaxException` or catching the exception. Component constructors may escape existing `%` characters; do not pass an already percent-encoded path into the constructor in a way that double-encodes it. For **individual query parameter values**, URI constructors do not automatically understand “this is a single value”: `&` and `=` have parameter-separating meaning. Use a builder library that understands query parameters, or encode properly according to the target protocol. `URLEncoder` is intended for form encoding (`application/x-www-form-urlencoded`), not as a tool for encoding an entire URL or path.

## 7. Example of combining resource URIs with restricted input

`resolve` can change the scheme/host when the reference is an absolute URI or starts with `//`, and `../` can escape the base path. Therefore, when accepting a resource name from user input, **do not allow an arbitrary URI reference** and rely on `normalize` to “sanitize” it.

Simple scenario: the server only allows image names consisting of Latin letters, digits, `_`, `-`, and a `.png` or `.svg` extension, rejecting `/`, `%`, `?`, `#`, spaces, or `..`. Define an explicit naming policy, then `resolve` and re-check the scope.

Create the file **`AssetUriBuilder.java`**:

~~~java
import java.net.URI;

public class AssetUriBuilder {
    private static final URI ROOT =
            URI.create("https://static.example.test/media/");

    public static URI assetUri(String fileName) {
        if (fileName == null
                || !fileName.matches("[A-Za-z0-9_-]+\\.(?:png|svg)")) {
            throw new IllegalArgumentException("Invalid asset file name");
        }

        URI result = ROOT.resolve(fileName).normalize();

        if (!"https".equalsIgnoreCase(result.getScheme())
                || !"static.example.test".equalsIgnoreCase(result.getHost())
                || result.getPort() != -1
                || result.getRawUserInfo() != null
                || !result.getRawPath().startsWith(ROOT.getRawPath())) {
            throw new IllegalArgumentException("Asset outside allowed root");
        }

        return result;
    }

    public static void main(String[] args) {
        System.out.println(assetUri("logo.svg"));
        System.out.println(assetUri("chart_2026.png"));

        for (String candidate : new String[] {
                "../secret.svg",
                "//evil.example.test/logo.svg",
                "team logo.svg"
        }) {
            try {
                assetUri(candidate);
            } catch (IllegalArgumentException ex) {
                System.out.println("Rejected: " + candidate);
            }
        }
    }
}
~~~

~~~bash
javac --release 17 AssetUriBuilder.java
java AssetUriBuilder
~~~

Exact stdout:

~~~text
https://static.example.test/media/logo.svg
https://static.example.test/media/chart_2026.png
Rejected: ../secret.svg
Rejected: //evil.example.test/logo.svg
Rejected: team logo.svg
~~~

The takeaway here is a **strict whitelist for a single filename**: do not allow the caller to pass a full URI, a multi-segment path, or an already encoded string; adding a scope check serves as an additional line of defense. This is **not a general-purpose URI sanitizer**. If the problem requires Unicode, subdirectories, percent-escapes, dynamic queries, or full user-controlled URLs, you must build a different policy, encode per component, and verify against the same decoding/redirect behavior that the final consuming layer will perform. When an HTTP client automatically follows redirects, the post-redirect destination also needs a corresponding policy if outbound connections are restricted.

In an internal application generating static URLs from trusted resource names, it can be simpler: just `ROOT.resolve("logo.svg")` is enough. Do not add unrelated defensive code if the input is completely controlled by source code.

## 8. Common mistakes and how to fix them

**Mistake 1 — Forgetting the trailing slash on a base directory.** `URI.create("https://x.test/api").resolve("users")` produces `https://x.test/users`. If you want `/api/users`, change the base to `https://x.test/api/`.

**Mistake 2 — Thinking `resolve` only appends paths.** A `/users` reference wipes out the base path; `//other.test/users` changes the authority; `https://other.test/users` brings an entirely new URI. Do not use arbitrary input in a client whose policy is to call only one host.

**Mistake 3 — Assuming `relativize` will always return a relative URI.** When origins differ or paths lack a prefix relationship, it can return the intact target URI. Check the result instead of using it directly as a mandatory relative path.

**Mistake 4 — Using `normalize` as path traversal defense.** `%2e%2e`, symlinks, path decoding in proxies/servers, and URL redirects are outside the responsibility of `URI.normalize`. Validate inputs, origins, and downstream semantics.

**Mistake 5 — Forgetting that query and fragment are two separate components.** Using `resolve("?lang=vi")` while expecting it to always preserve the base file, or concatenating strings without encoding query values, leads to invalid URLs. Separate path, query, and fragment and rebuild according to the proper contract.

**Mistake 6 — Using `Path` as a URI or vice versa.** `Path.resolve` follows the filesystem; `URI.resolve` follows the URI hierarchy. An OS path is not automatically a valid URI string.

**Mistake 7 — Calling methods and ignoring the return value.** `base.resolve(ref)`, `base.normalize()`, and `base.relativize(target)` all return a new `URI`; assign the result when you intend to use it.

**Mistake 8 — Confusing encoded and decoded paths.** `getPath()` can contain extra `/` characters from `%2F`; `getRawPath()` preserves escaping. Do not use them interchangeably when classifying segments or validating input.

## 9. Self-check exercises

**Exercise 1.** `base = https://docs.example.test/a/b/`. What is the result of `base.resolve("../c.svg")`?  
**Answer:** `https://docs.example.test/a/c.svg`.

**Exercise 2.** Why does `URI.create("https://x.test/a").resolve("b")` differ from `URI.create("https://x.test/a/").resolve("b")`?  
**Answer:** base `/a` treats `a` as the last segment to be replaced → `https://x.test/b`; base `/a/` treats the insertion point as inside the directory path → `https://x.test/a/b`.

**Exercise 3.** What does `URI.create("https://x.test/a/b/../c").normalize()` return?  
**Answer:** `https://x.test/a/c`. Only path dot-segments are collapsed.

**Exercise 4.** What does `URI.create("https://x.test/a/").relativize(URI.create("https://x.test/b/y"))` return?  
**Answer:** The intact target URI `https://x.test/b/y`; it does not automatically generate `../b/y`.

**Exercise 5.** Does `base.resolve("//other.test/img.svg")` keep the original host?  
**Answer:** No. It uses the `other.test` authority, inheriting the scheme from the base.

**Exercise 6.** Does `URI.create("https://x.test/public/%2e%2e/admin").normalize()` prevent escaping the `public` directory?  
**Answer:** No. Percent-encoded dot segments are not decoded; this is not proof of containment.

**Exercise 7.** If you want to modify the query of `https://x.test/a/page.html` while keeping `/a/page.html` intact, should you default to `resolve("?x=1")`?  
**Answer:** No. On Java `URI`, that operation can return `https://x.test/a/?x=1`. You need to build the URI from its components to preserve the path as required.

## 10. Checklist when designing resource path combination

1. **Identify the base type:** Does the URI point to a *directory* or a *file*? If it is a directory, the base must have a trailing `/`.
2. **Classify the input:** Relative path, absolute path, authority-relative, or absolute URI? Is changing the scheme/host allowed?
3. **Choose the operation:** `resolve` to create a target; `normalize` to remove path dot-segments; `relativize` to shorten a path by prefix when possible.
4. **Preserve components accurately:** Path, query, fragment, raw/decoded encoding; do not concatenate strings when components have syntactic meaning.
5. **Validate the output:** Origin, port, allowed path, prefix conditions; do not treat syntactic normalization as security validation.
6. **Test edge cases:** With/without trailing slash, `../`, `/`, `//`, `#`, `?`, percent-escapes, and cross-origin targets.
7. **Distinguish I/O:** `URI` only performs syntactic transformations; fetching resources happens in an HTTP client, URL handler, or separate filesystem API.

## Official documentation

- [Java SE 17 — `java.net.URI`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html): sections **Operations on URI instances**, **normalize**, **resolve**, **relativize**, escaping, and URI versus URL. This is the primary contract for verifying the examples.
- [Java SE 21 — `java.net.URI`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URI.html): use when the project runs JDK 21 and you want to compare the contract with Java 17.
- [Java SE 17 — `java.nio.file.Path`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): distinguishes local file paths from URI hierarchies; `resolve`, `normalize`, `toUri`, and `toRealPath`.
- [RFC 3986 — Reference Resolution](https://www.rfc-editor.org/rfc/rfc3986#section-5.2): foundation for understanding URI resolution in modern web systems. **Note:** The `java.net.URI` Javadoc describes the algorithm based on RFC 2396 and Java-specified deviations; when concluding Java behavior, prioritize the Javadoc and testing on the target JDK.

Core mindset: **clearly define the base URI and the structure of each component, use the right operation for its purpose, and then verify that the output matches your application's scope.**
