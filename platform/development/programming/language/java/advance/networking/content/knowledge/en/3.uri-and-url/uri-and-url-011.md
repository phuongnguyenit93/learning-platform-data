# Checking Scheme, Target Host, Port, and Path Before Opening a Connection

## 1. Why Must You Check a URI/URL Before Connecting?

Suppose a Java application receives a URL string from a user to call an API, download a resource, or forward a request. If the application only checks that the string "looks like a URL" and then calls `HttpClient.send(...)` or `URL.openStream()`, it may send a connection to the wrong protocol, wrong host, wrong port, or wrong path. Even a syntactically valid URL may **not be permitted by the application's policy**.

This lesson focuses on one specific operation: **validating URL/URI input and deciding the connection target before an action that causes network I/O**, in the context of Java Advanced Networking. The necessary defense layers when the target is controlled by an external party are also explained, especially when preventing Server-Side Request Forgery (SSRF).

After this lesson, you should be able to:
- Decompose a URI into **scheme**, **authority/host**, **port**, **path**, **query**, and **fragment** without relying on arbitrary string manipulation.
- Design an **explicit allowlist** for scheme, host, port, and path; detect user-info, malformed authority, and unexpectedly encoded/normalized paths.
- Use `java.net.URI` to validate input before opening a connection with `java.net.http.HttpClient`; understand the difference between **checking a URI string** and **controlling the actual host connected to after DNS**.
- Properly handle relative URLs, redirects, DNS rebinding, proxies, IPv4/IPv6, timeouts, and common errors.

**Principle:** "URL parsing succeeded" only proves part of the syntax; "URL is approved" must mean that all policies for the **specific target and resource** have been checked. Opening a socket still requires the corresponding network controls.

## 2. Anatomy of a URL Address

Consider the string:

```text
https://api.example.com:8443/v1/items/42?lang=vi#details
└─┬─┘ └──────┬─────┘ └┬─┘ └─────┬────┘ └──┬──┘ └──┬──┘
scheme       host     port      path       query   fragment
```

| Component | Meaning | API in `java.net.URI` | Issues to Check |
| --- | --- | --- | --- |
| Scheme | Protocol/way of interpreting the resource, e.g., `https` | `getScheme()` | Only allow protocols that the application intentionally supports |
| Authority | The part after `//`, which may contain user-info, host, and port | `getRawAuthority()` | Do not trust the raw authority string as-is or split on `:` manually |
| Host | DNS name or IP literal | `getHost()` | Host must be present, parseable, and in the list of valid targets |
| User-info | The part before `@` in authority | `getRawUserInfo()` | Usually reject; easily misleads readers and leaks credentials |
| Port | Target TCP port | `getPort()` | `-1` means not explicitly declared; it does **not** mean port -1 will be connected to |
| Path | Resource path on the server | `getRawPath()` / `getPath()` | Check exact route, dot-segments, percent-encoding, and decoding rules |
| Query | Parameters after `?` | `getRawQuery()` | Not the path; can affect business logic so needs its own policy |
| Fragment | The part after `#` | `getRawFragment()` | Not sent as part of the HTTP request-target; usually unnecessary in backend URLs |

A `URI` can be **absolute** (`https://...`) or **relative** (`../items`, `//other.example/path`). An absolute URI can also be **opaque** like `mailto:name@example.com`. A typical HTTP request requires an **absolute, hierarchical** URI with a valid scheme and host.

`URI` methods only perform syntactic parsing; they **do not send requests on their own**. Many invalid/disallowed URIs can be checked without generating any network connections.

## 3. Building a Policy from Actual Connection Needs

Before writing code, answer four questions:

1. **Which schemes are allowed?** For example, if a service only calls HTTPS, accept only `https`. There is no reason to automatically allow `http`, `file`, `jar`, `ftp`, `gopher`, or any other protocol.
2. **Which target hosts are allowed?** For example, strictly one host `api.example.com`; if multiple hosts are allowed, list them explicitly instead of accepting a string that "contains example.com".
3. **Which ports are allowed?** If calling standard HTTPS, the effective port is 443. Distinguish between a URL omitting the port and a URL specifying 443; reject 80, 8080, 8443, etc. if the system does not allow them.
4. **Which paths are allowed?** For example, only call `/v1/items` and `/v1/items/<id>` with a constrained `id`. Do not use an overly broad condition like `path.startsWith("/v1")` because it can also match `/v1-admin`.

For an application with only a few trusted targets, an **allowlist by (scheme, host, port, path)** is usually clearer and safer than a blacklist of "dangerous" names/addresses. The policy must be defined by business requirements; the example below intentionally uses a narrow policy to make it easy to demonstrate.

A sensible check sequence:

```text
Input string
    │
    ▼
URI parse (no network I/O)
    │
    ├── Invalid / relative / opaque ────────────────► REJECT
    ▼
Scheme in allowlist?
    │
    ├── No ─────────────────────────────────────────► REJECT
    ▼
Host parseable? No user-info? Host allowed?
    │
    ├── No ─────────────────────────────────────────► REJECT
    ▼
Effective port allowed?
    │
    ├── No ─────────────────────────────────────────► REJECT
    ▼
Path + query + fragment match policy?
    │
    ├── No ─────────────────────────────────────────► REJECT
    ▼
URI passes syntax/business checks
    │
    ▼
DNS, target IP, proxy, redirect, egress controls
    │
    ▼
Only then let HTTP client create connection
```

The diagram shows **independent check layers**. Passing the URI string checks does not mean the DNS/IP or network control steps are complete.

## 4. Checking the Scheme Properly

A URI scheme may be written in different letter cases syntactically, so use `equalsIgnoreCase` or normalize before comparing.

```java
URI uri = URI.create("HTTPS://api.example.com/v1/items");
boolean allowed = "https".equalsIgnoreCase(uri.getScheme());
```

The snippet above only illustrates scheme comparison; it is **not sufficient** to approve a URL. The following inputs have completely different meanings:

| Input | Assessment |
| --- | --- |
| `https://api.example.com/v1/items` | Valid candidate for an HTTPS policy |
| `http://api.example.com/v1/items` | Must be rejected if HTTPS is required |
| `file:///etc/hosts` | Different scheme; not used as an HTTP endpoint |
| `mailto:user@example.com` | Absolute URI but **opaque**, has no HTTP host |
| `//api.example.com/v1/items` | Network-path reference URI, **has no scheme** |
| `/v1/items` | Relative URI, needs a trusted base if business logic allows it |
| `javascript:...` | Different scheme, not an HTTP server address the application is allowed to open |

Do not use `startsWith("https")` to verify the scheme: a string could just happen to start with those characters. Parse with `URI` and then inspect `getScheme()`, `isAbsolute()`, and `isOpaque()`.

**HTTPS alone does not solve all risks:** an `https` request can still go to a disallowed internal host, redirect elsewhere, or pick an out-of-policy target due to DNS/proxy. HTTPS protects the transport and verifies the name when configured properly; it does not replace target control.

## 5. Checking Host, Authority, and Target Host Identity

### 5.1. Use `getHost()`, Do Not Split the URL as a String

Examples:

```text
https://api.example.com.evil.test/v1/items
https://api.example.com@evil.test/v1/items
https://user:secret@api.example.com/v1/items
https://api.example.com:badport/v1/items
https://[::1]:443/v1/items
```

- The first string only **contains** the trusted domain at the beginning; the actual host is `api.example.com.evil.test`.
- The second string has `api.example.com` as **user-info**; the actual host is `evil.test`.
- The third string actually points to `api.example.com`, but including user-info can cause confusion or leak passwords through logs/history or other handling paths. Typical API policies should reject user-info.
- The fourth string has an authority that cannot be parsed into a valid server-based host/port in Java `URI`; `getHost()` may return `null`. You must not treat `getPort() == -1` on this string as "valid missing port" and accept it.
- The last string is an IPv6 loopback literal. The colons belong to the IPv6 address syntax inside `[...]`; do not split host/port using `split(":")`.

Use `getRawAuthority()` for diagnostics, but **do not** compare the entire authority as a host. Use `getHost()` to get the host recognized by the URI parser, `getRawUserInfo()` to reject credentials in the URL, and `getPort()` to determine the explicit port.

### 5.2. Exact Host Matching

- DNS names are case-insensitive: you can normalize with `toLowerCase(Locale.ROOT)` and then match exactly against the allowlist. `Locale.ROOT` avoids JVM locale-specific lowercasing differences.
- **Do not** use `contains("example.com")` or `endsWith("example.com")` if the policy only allows `api.example.com`.
- If the policy allows subdomains of `example.com`, you must precisely define accepting the domain itself and/or a suffix with a **dot boundary**, such as `.example.com`; you need to consider uncontrolled subdomains, wildcard DNS, and subdomain takeover risks.
- FQDNs with a trailing dot, IP literals, IPv6 in `[]` brackets, internationalized hostnames (IDN/punycode), and internal names all require clear policies. Do not arbitrarily strip trailing dots, convert IDN, or change IPv6 formatting in a way that is inconsistent with the connection layer.
- `URI.getHost()` can be `null` for an authority that is not in the server-based host form recognized by Java; **fail closed (reject)** in policies requiring an HTTP(S) host.

Internationalized names can be represented via **Punycode** (`xn--...`). Java has `java.net.IDN.toASCII(...)`, but if the system wants to support Unicode domains, the Unicode normalization/IDNA process, character restrictions, and canonical matching must be designed consistently with the HTTP client and DNS. The hands-on example below intentionally **allowlists only one ASCII hostname**; it does not automatically convert or accept other spellings of the name.

### 5.3. A Syntactically Valid Host Does Not Guarantee an Allowed Target IP

A DNS name can point to multiple A/AAAA records; records can change over time, by resolver, and by network location. A valid name can unexpectedly resolve to a loopback, link-local, private/ULA IP, or a sensitive internal network. Conversely, an IP can be written in multiple ways and interpreted differently by parsers/resolvers.

For URLs supplied arbitrarily by users (webhooks, image fetchers, URL previews, proxies), treat this as an **SSRF** problem: control the target IP at connection time, not just by checking the host string. Read Section 10 to see why calling `InetAddress.getAllByName(...)` and then letting `HttpClient` re-resolve a few milliseconds later is **not a complete measure**.

## 6. Checking Port and Default Ports

`URI.getPort()` returns:
- An integer when the URL declares a port recognized by the parser, e.g., `https://host:8443/a` → 8443.
- `-1` when **no port is declared**, e.g., `https://host/a` → -1.

To determine the effective port for standard HTTP:

```text
http://host/a       -> effective port 80
https://host/a      -> effective port 443
https://host:443/a  -> effective port 443
https://host:8443/a -> effective port 8443
```

Always check the **scheme** before applying the default port rule; the default port is a rule of the protocol/client, not a hardcoded number for every URI. When writing the policy, explicitly state whether an explicit port matching the default is allowed.

For a general TCP/UDP socket, valid target ports are **1..65535**; port 0 is typically used in the context of **binding a local ephemeral port**, not a useful target port to call a service. The URI parser does not necessarily reject every out-of-range port case just because the port syntax consists of digits. For example, `https://host:99999/a` can still return `getPort() == 99999`, so a policy check is needed.

In this lesson's example allowing only HTTPS 443:
- `getPort() == -1` or `getPort() == 443` → may proceed.
- Any other port → reject.
- Malformed authority causing `getHost() == null` → reject at the host step, do not fall through to the "default 443" branch.

Do not check the port using `endsWith(":443")` on the entire URL: it could appear in the path, query, user-info, or different IPv6 notation.

## 7. Checking the Path: Raw, Decoded, and Normalized

### 7.1. Raw Path Differs from Decoded Path

Java provides:
- `getRawPath()`: preserves percent-encoded sequences (e.g., `%2F`, `%2e`).
- `getPath()`: returns the path with percent-encoding decoded.
- `normalize()`: normalizes some dot-segments *according to URI syntax*, but is **not a general-purpose security filter**.

Example:

```text
URI:      https://api.example.com/v1/%2e%2e/admin
raw path: /v1/%2e%2e/admin
path:     /v1/../admin
```

If an application only checks `getRawPath().startsWith("/v1/")`, it might accept a path that the server/proxy, after decoding, treats as `/admin`. Even `uri.normalize()` does not by itself replace checking percent-encoded dot segments. Forms like `%2e`, `%2f`, `%5c`, and nested encoded sequences can be handled differently across proxies, routers, and backends.

A broad prefix check like `path.startsWith("/public")` also accepts `/public-admin` or `/publicity`. Paths can contain `/./`, `/../`, `//`, `\`, percent-encoding, complex dots, or Unicode normalization issues. Processing rules must be consistent with the **final component receiving the request**.

### 7.2. Choosing the Right Path Policy for the Use Case

There are two main approaches:

1. **APIs with a narrow set of routes:** allow only the exact raw path patterns the application uses, such as `/v1/items` or `/v1/items/<id>` with an ID matching an ASCII regex. This is the approach demonstrated in Section 8; it *actively rejects all percent-encoding in the path*, so encoded variants cannot bypass the matcher.
2. **Applications allowing flexible paths:** must explicitly define whether encoded slashes, Unicode, dots, or multiple decodes are accepted; canonicalize in one way consistent with the target host, and verify again after resolve/redirect steps. Do not arbitrarily use `URLDecoder` for paths: it is designed for form encoding and can interpret `+` as a space, which is incorrect in many URL path contexts.

**Important:** No single `normalize()` call or generic regex solves all path traversal and authorization issues. When a path represents a private resource, the backend must still perform **authorization on the final resource**, in addition to the client's URL check.

### 7.3. Query and Fragment Are Not the Path

`https://host/v1/items?limit=10#section` has path `/v1/items`, query `limit=10`, and fragment `section`. If the API only allows `limit` from 1 to 50, a valid path **does not mean** a valid query. Fragments are normally not sent to the HTTP server; in backend requests, they can be rejected to avoid ambiguity.

Example rule: accept an empty query, or strictly one parameter `limit=<1..50>`; reject other parameters, invalid values, multiple parameters, or fragments. This policy is **intentionally very narrow** and only serves to illustrate specific pre-connection checks.

## 8. Java 17+ Example: Checking the Entire URI Without Network Access

**Problem:** a service may only make HTTPS calls to host `api.example.com`, port 443, with one of two path forms:
- `/v1/items`
- `/v1/items/<id>`, where `id` has 1–32 ASCII letters, digits, `_`, or `-`.

Allow an empty query or `limit=1..50`; disallow user-info, fragments, percent-encoding in the path, or relative URLs. The example uses plain `URI`, **without resolving DNS and without opening a socket**. It checks the URL string part against a specific policy; the remaining network controls are presented in Sections 10–11.

Save the file `UrlPreflight.java`:

```java
import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Pattern;

public class UrlPreflight {
    private static final Set<String> HOSTS = Set.of("api.example.com");
    private static final Pattern PATH =
            Pattern.compile("/v1/items(?:/[A-Za-z0-9_-]{1,32})?");
    private static final Pattern QUERY =
            Pattern.compile("limit=(?:[1-9]|[1-4][0-9]|50)");

    public record Approved(URI uri, String host, int port, String rawPath) { }

    public static Approved validate(String input) {
        if (input == null || input.length() > 2048) {
            throw new IllegalArgumentException("input");
        }
        final URI uri;
        try {
            uri = new URI(input);
        } catch (URISyntaxException ex) {
            throw new IllegalArgumentException("syntax");
        }
        if (!uri.isAbsolute() || uri.isOpaque()) {
            throw new IllegalArgumentException("absolute URI");
        }
        if (!"https".equalsIgnoreCase(uri.getScheme())) {
            throw new IllegalArgumentException("scheme");
        }
        if (uri.getRawUserInfo() != null) {
            throw new IllegalArgumentException("userinfo");
        }
        String host = uri.getHost();
        if (host == null || !HOSTS.contains(host.toLowerCase(Locale.ROOT))) {
            throw new IllegalArgumentException("host");
        }
        int explicitPort = uri.getPort();
        if (explicitPort != -1 && explicitPort != 443) {
            throw new IllegalArgumentException("port");
        }
        if (uri.getRawFragment() != null) {
            throw new IllegalArgumentException("fragment");
        }
        String rawPath = uri.getRawPath();
        if (rawPath == null || !PATH.matcher(rawPath).matches()) {
            throw new IllegalArgumentException("path");
        }
        String rawQuery = uri.getRawQuery();
        if (rawQuery != null && !QUERY.matcher(rawQuery).matches()) {
            throw new IllegalArgumentException("query");
        }
        return new Approved(uri, host.toLowerCase(Locale.ROOT), 443, rawPath);
    }

    public static void main(String[] args) {
        String[] samples = {
            "https://api.example.com/v1/items",
            "HTTPS://API.EXAMPLE.COM:443/v1/items/Ab_7",
            "https://api.example.com/v1/items?limit=10",
            "http://api.example.com/v1/items",
            "https://api.example.com:8443/v1/items",
            "https://api.example.com.evil.test/v1/items",
            "https://user@api.example.com/v1/items",
            "https://api.example.com/v1/items/../admin",
            "https://api.example.com/v1/%2e%2e/admin",
            "https://api.example.com/v1/items/abc%2Fdef",
            "https://api.example.com/v1/items?limit=100",
            "//api.example.com/v1/items",
            "file:///tmp/private",
            "https://api.example.com/v1/items#section"
        };
        for (int i = 0; i < samples.length; i++) {
            try {
                Approved approved = validate(samples[i]);
                System.out.printf("%02d ACCEPT %s:%d %s%n",
                        i + 1, approved.host(), approved.port(), approved.rawPath());
            } catch (IllegalArgumentException ex) {
                System.out.printf("%02d REJECT %s%n", i + 1, ex.getMessage());
            }
        }
    }
}
```

Run with JDK 17 or later:

```bash
javac UrlPreflight.java
java UrlPreflight
```

Exact stdout with the sample data:

```text
01 ACCEPT api.example.com:443 /v1/items
02 ACCEPT api.example.com:443 /v1/items/Ab_7
03 ACCEPT api.example.com:443 /v1/items
04 REJECT scheme
05 REJECT port
06 REJECT host
07 REJECT userinfo
08 REJECT path
09 REJECT path
10 REJECT path
11 REJECT query
12 REJECT absolute URI
13 REJECT scheme
14 REJECT fragment
```

### Explanation of Each Test Group

- **01–03 accepted:** scheme/host are case-insensitive; port can be omitted if defaulting to 443; query `limit=10` is in the allowlist.
- **04 rejected scheme:** HTTP is different from HTTPS.
- **05 rejected port:** an HTTPS server on 8443 is not in the policy.
- **06 rejected host:** the string `api.example.com.evil.test` does not equal `api.example.com`.
- **07 rejected user-info:** `@` is not accepted in the input URL.
- **08–10 rejected path:** `..`, `%2e%2e`, and `%2F` all fail to match the defined raw path pattern.
- **11 rejected query:** `limit=100` is outside the allowed range.
- **12 rejected relative URI:** missing scheme; does not automatically borrow a scheme from elsewhere.
- **13 rejected file scheme:** `file:///tmp/private` is not HTTPS.
- **14 rejected fragment:** the `#section` part serves no purpose in the request business logic.

The example intentionally avoids DNS; therefore the result is always deterministic and independent of the network. An `ACCEPT` result here means **it passed this URI filter**, **not a guarantee of permission to connect**. Before deploying, replace the placeholder allowlist with the real host owned/managed by the application and apply the DNS/IP/egress policies in Section 10.

### Why Is the Path Pattern So Strict?

`Pattern.compile("/v1/items(?:/[A-Za-z0-9_-]{1,32})?")` only accepts paths consisting of the listed characters and matching the exact route structure. Because `matches()` matches the entire string, variants like `/v1/items-extra`, `/v1/items/123/../../admin`, and `/v1/items/%2e%2e` are rejected. In applications where IDs contain Unicode or escapes, you must define how to canonicalize and verify against the final route, **not loosen the regex arbitrarily**.

`URI` and `Approved` in the example are immutable; the caller can pass `approved.uri()` to the HTTP API after other policies have completed. Avoid validating a string and then concatenating a path/query from untrusted input **after** validation.

## 9. Handling Relative URLs and `URI.resolve`

A relative URL such as `/v1/items` does not determine the target host on its own. If the business logic accepts relative URLs, only resolve against a **configured and trusted base URI**, and then run the **entire policy on the resulting URI**. Do not resolve a user-supplied string against a base and assume the target still remains within the previous scope.

Example:

```java
import java.net.URI;

public class ResolveDemo {
    public static void main(String[] args) {
        URI base = URI.create("https://api.example.com/v1/");
        System.out.println(base.resolve("items/42"));
        System.out.println(base.resolve("../admin"));
        System.out.println(base.resolve("//other.example/v1/items"));
    }
}
```

```bash
javac ResolveDemo.java
java ResolveDemo
```

```text
https://api.example.com/v1/items/42
https://api.example.com/admin
https://other.example/v1/items
```

The latter two examples can escape the root path or change the host even though the input is a **relative reference**. Apply `UrlPreflight.validate(resolved.toString())` to the result; those two URIs will be rejected by Section 8's policy. If only one path branch is allowed, check the **path after resolve**, not just the path the user entered before resolve.

Note that `normalize()` does not authorize resources and does not resolve all encoding forms. A URI does not prevent structural changes performed later by a backend or proxy, so policies must be consistent across layers.

## 10. DNS, Target IP, and SSRF: String Checks Are Not Enough

### 10.1. An Allowed Host Can Resolve to a Forbidden IP

Suppose the application allows a certain hostname. At check time, DNS returns a public IP; immediately afterward, when the HTTP client creates a socket, the resolver returns `127.0.0.1`, `10.x.x.x`, `169.254.x.x`, IPv6 loopback, or ULA. This is a form of **DNS rebinding / TOCTOU** (time of check versus time of use). A single `InetAddress.getAllByName(host)` call followed by letting the HTTP client **re-resolve on its own** does not bind the checked IP to the IP the socket will use.

With features that accept untrusted URLs, an attacker may try to steer the server's request internally, such as to an admin port, loopback, cloud metadata address, or non-public services. The risk persists if the app checks `https` and a domain regex but **does not control the target at the actual connection**.

### 10.2. Multi-Layered Defense Approach

1. **Prefer fixed targets:** if the application only calls a partner's API, let the user choose a resource ID/parameter instead of entering a URL host; configure the target URL on the server side.
2. **Allowlist scheme/host/port/path:** as in the Section 8 example, accept only what the use case needs. If IP literals are allowed, use a standard IP validator, checking both IPv4/IPv6 and allowed network ranges.
3. **Post-resolution DNS/IP control:** inspect **all** candidate IPs (A/AAAA, CNAME when relevant), not just the first IP; block disallowed ranges such as loopback, private/ULA, link-local, multicast, unspecified, and other special blocks per system policy. Using only `isSiteLocalAddress()` is insufficient, as it does not fully recognize IPv6 ULA and many reserved ranges.
4. **Bind the approved IP to the connection:** use a transport/client or network mechanism that ensures the socket actually goes to the allowed IP, while still verifying TLS against the proper hostname (Host, SNI, certificate). **Do not** simply replace the URL with an IP and skip certificate/TLS verification.
5. **Block at the network layer:** egress firewall, network policy, private subnet ACL, controlled proxy, restricting connections from workloads to management/cloud metadata networks. This is a critical defense layer if URI code is bypassed.
6. **Re-check on every redirect, retry, and fallback:** host/IP/port can change between requests.

**Important note:** Standard Java `HttpClient` does not provide a simple API to "validate DNS A/AAAA and then pin those exact IPs for this request" across all HTTPS, proxy, and redirect scenarios. Do not treat a snippet calling `getAllByName` as a complete SSRF-resistant implementation. Applications requiring strong SSRF protection need properly managed transport/egress, along with TLS controls.

### 10.3. When Can a Simple Hostname Allowlist Be Used?

For a service that only calls **an endpoint owned by the organization** over trusted DNS, an exact allowlist and restricted egress are usually a good solution. For "arbitrary Internet" URLs submitted by users, the attack surface is much wider; strict IP, redirect, DNS, and network layers are required. Do not infer a "public host" just because it does not match the three private IPv4 ranges.

## 11. Redirects and When the Connection Is Actually Opened

In Java 17, `java.net.http.HttpClient` only sends a request when calling `send(...)` or `sendAsync(...)`, not when creating `HttpRequest`. `URL.openConnection()` only returns a `URLConnection` object; the actual connection usually happens when calling `connect()` or an I/O operation like `getInputStream()`. Therefore, the policy must be run **before** those actions.

An HTTP `301`/`302`/`303`/`307`/`308` response can contain a `Location` pointing to another URL:
- `https://api.example.com/v1/items` → `https://internal.example/admin`
- `https://api.example.com/v1/items` → `http://api.example.com:8080/debug`
- `https://api.example.com/v1/items` → `//other.example/private`

Checking the initial URL **does not** automatically check the redirected URLs.

Java `HttpClient.Redirect.NEVER` disables automatic redirect following (this is also the default policy of the Java 17 builder). When using sensitive input URLs, explicitly configure `NEVER`; if business logic requires following redirects, handle them step by step, limit the redirect count, and re-run the **full** policy. Note that relative redirects must be resolved against the current URI before validating.

### Illustrative Code Snippet for the HTTP Call Step

The following snippet is **code inside a method**, using the `UrlPreflight` class from Section 8; it is not a standalone Java file. It shows the correct order of validate → build request → connect, without sending a request in this lesson's example.

```java
UrlPreflight.Approved approved =
        UrlPreflight.validate(userSuppliedUrl);

// Additional DNS/IP/egress policies must be enforced by
// the transport/network before connecting if the URL is untrusted.
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(approved.uri())
        .timeout(Duration.ofSeconds(10))
        .GET()
        .build();

HttpResponse<Void> response =
        client.send(request, HttpResponse.BodyHandlers.discarding());

// If the business logic allows redirects, you must manually extract Location,
// currentUri.resolve(location), validate the new target URI,
// check DNS/IP/egress again, and limit the number of redirects.
```

Required imports for the snippet: `java.net.http.HttpClient`, `HttpRequest`, `HttpResponse`, `java.time.Duration`. The `userSuppliedUrl` variable is provided by the caller. A real implementation must handle `IOException`/`InterruptedException`, HTTP status, response size, timeouts, request cancellation, and appropriate logging; the snippet above mainly explains **where to place the preflight step**.

**Note on proxies:** The HTTP client may use a default or configured proxy. The proxy may be the point performing actual DNS/routing; the host/IP control policy must align with the **path through the proxy**, not just the application's local resolver.

## 12. Special Edge Cases to Decide by Policy

### 12.1. Host Is an IP Literal

`https://127.0.0.1/...`, `https://[::1]/...`, `https://169.254.169.254/...`, or a private IP does not automatically mean "allowed" just because it parses cleanly. An application that only allows host `api.example.com` should reject all IP literals. If the application must support IP literals, validate the **canonical IP form and allowed ranges**, including IPv4-mapped IPv6, scope identifiers, and special addresses; do not rely on string blacklists like `"127."`.

### 12.2. Internationalized Domains, Trailing Dots, and Lookalike Names

`api.example.com.` may be an absolute DNS spelling of the same name in some systems, but the example's exact host matcher will **reject** it because it does not equal `api.example.com`. A policy may intentionally choose to normalize trailing dots, but must ensure corresponding behavior in the resolver/TLS and logging. Unicode homographs, IDNs, and lookalike domains need separate handling; do not "trust by eye".

### 12.3. Paths Containing `?`, `#`, or Multiple Layers of Encoding

`?` separates the query and `#` separates the fragment in URI syntax; if you want those characters as path data, they must be percent-encoded. However, when percent-encoding appears, servers/proxies may decode it; route authorization must share the same interpretation. The policy example in Section 8 keeps it simpler by **disallowing percent-encoding in the path**.

### 12.4. Distinguishing HTTP URLs from File Paths

`file:///var/log/app.log` is a URI with scheme `file`, not an HTTP URL. Never turn an arbitrary input URL into a file read operation just because `toURL()` or `openStream()` can be called. If the business logic is to load files from the filesystem, build a dedicated filesystem policy: allowed root directory, symbolic link handling, real path, and file permissions.

### 12.5. Length, Query, Request, and Resource Limits

Limit URL length, parameter count, HTTP method types, request body, and response size according to the use case; set timeouts and retry limits. The preflight step is only one part of resource limiting. The 2,048-character input limit in Section 8 is an illustrative choice, **not a universal standard** for every system.

## 13. Implementation Workflow with Clear Errors

A preflight function should take a URL string and return:
- An **approved object** containing the URI and confirmed host/port/path information; or
- An **error with a clear code** (scheme/host/port/path/query…), so the caller rejects before I/O.

Do not:
- Validate a URL and then **append** a user-controlled path string afterward without re-validating.
- Use a regex covering the entire URL without a URI parser to separate components.
- Return raw URL contents (which may contain secret tokens/queries) into logs or exceptions; prefer logging the rejection reason code and sanitized information.
- Automatically rewrite `http` to `https` or replace an invalid host/port/path with a "safe" value and continue without clear business rules.
- Allow the HTTP client to follow all redirects automatically while only checking the first URL.
- Disable TLS/certificate verification to "fix" a connection error.

Suggested layered testing approach:

| Test | Input | Expected |
| --- | --- | --- |
| Scheme | `http://api.example.com/v1/items` | Reject |
| Lookalike host | `https://api.example.com.evil.test/v1/items` | Reject |
| User-info | `https://api.example.com@evil.test/v1/items` | Reject (actual host is evil.test) |
| Out-of-policy port | `https://api.example.com:8443/v1/items` | Reject |
| Default HTTPS port | `https://api.example.com/v1/items` | Accept with effective port 443 |
| Valid path | `https://api.example.com/v1/items/abc_2` | Accept |
| Confusing prefix | `https://api.example.com/v1/items-extra` | Reject |
| Dot segment | `https://api.example.com/v1/items/../admin` | Reject |
| Encoded dot/slash | `https://api.example.com/v1/%2e%2e/admin` | Reject |
| Out-of-policy query | `https://api.example.com/v1/items?limit=999` | Reject |
| Host changes on redirect | `Location: //other.example/secret` | Re-validate target URI; reject by host |
| DNS changes after check | hostname initially public then resolves to private | Must be blocked at IP/transport/egress, **cannot be proven solely by Section 8 function** |

To test DNS/redirects without accessing the real Internet, you can use a mock HTTP server or controlled DNS in an integration environment, while checking the **actual target socket**, not just the URL value returned by the preflight function.

## 14. Common Mistakes and How to Diagnose Them

1. **"`new URI(input)` did not throw, so it is safe to make a network call."** Wrong: the parser does not verify whether the target is in the allowlist or authorized.
2. **"Host contains the trusted string, so it is fine."** Wrong: `api.example.com.evil.test` is a different host; `user@host` also makes parsing differ from visual expectation.
3. **"`getPort() == -1` is always an invalid port."** Wrong: omitting an explicit port can use the scheme's default port. However, an unparseable authority must be rejected at the host step.
4. **"Path starts with the required prefix, so it is okay."** Wrong without a path segment boundary; `/v1/items-admin`, `..`, or percent-encoding can lead to other resources.
5. **"`normalize()` handles all path traversals."** Wrong: percent-encoding, double decoding, and differences between proxy/backend can produce unexpected results.
6. **"Checked the IP from DNS before `send`, so the socket is guaranteed to hit that IP."** Wrong if the client resolves again; this is TOCTOU/DNS rebinding.
7. **"Blocked private IPv4, so it definitely cannot reach internal networks."** Wrong: there are still IPv6 loopback/ULA/link-local, IPv4-mapped addresses, shared/reserved ranges, proxies, and other network architectures.
8. **"Only the initial URL needs to be checked."** Wrong if the client follows HTTP redirects or the caller resolves a relative URI and changes the target.
9. **"HTTPS guarantees the URL is safe."** Wrong: HTTPS does not decide whether the hostname is permitted by policy, nor does it protect against all SSRF if connecting to an unwanted host.
10. **"Switching from `URL` to `URI` automatically solves SSRF."** Wrong: URI provides clear parsing, whereas SSRF requires target policies and enforcement at connection time.

When encountering a connection error, identify the **post-resolve/redirect URL** and its scheme, host, port, and path components first; then check DNS, routing, proxy, TLS certificate, firewall, and timeouts. Do not use a network connection failure to infer that the input URL had invalid syntax, nor use successful parsing to infer that the target host is reachable.

## 15. Self-Check Questions

**Question 1.** Why is checking `input.startsWith("https://api.example.com")` not enough?  
**Answer:** the string `https://api.example.com.evil.test` still matches the prefix, but the actual host is different. You must parse the `URI` and match the full host against an allowlist.

**Question 2.** `https://api.example.com/v1/items` has `getPort() == -1`. Is that an error?  
**Answer:** no. For HTTPS, 443 is the default port. If the policy only allows 443, the URL can be valid after the other components are approved.

**Question 3.** Why must `getRawPath()` and `getPath()` be distinguished?  
**Answer:** the raw path preserves percent-encoding; the decoded path may reveal `..`, `/`, or other characters. You must not assume the proxy and backend interpret it the same way as a prefix check on the raw string.

**Question 4.** What does `URI.resolve("../admin")` on base `https://api.example.com/v1/` return? Is it within the example's policy?  
**Answer:** it returns `https://api.example.com/admin`; it is rejected because the path is not in the allowed set of routes.

**Question 5.** Why does calling `InetAddress.getAllByName(host)` followed by `HttpClient.send` not prevent DNS rebinding?  
**Answer:** the client may re-resolve and use a different IP when opening the socket. You must control the actual target (connection binding/transport/egress), all candidate IPs, redirects, and retries.

**Question 6.** How is a redirect `Location: //other.example/v1/items` handled?  
**Answer:** resolving against the current URI produces a URL with host `other.example`, then the scheme/host/port/path and DNS/IP/egress policies are re-run. Under the example's `api.example.com` allowlist, it must be rejected.

## 16. References

- Java SE 17 `URI` (parser, raw/decoded components, normalize, resolve): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html
- Java SE 17 `URL` and `URLConnection` (when a connection is opened): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URL.html
- Java SE 17 `HttpClient` (redirect policy, send): https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Java SE 17 `HttpClient.Builder` (default redirect NEVER, timeout): https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html
- OWASP Server-Side Request Forgery Prevention Cheat Sheet (allowlist, DNS rebinding, and egress): https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
- RFC 3986, Uniform Resource Identifier: Generic Syntax: https://www.rfc-editor.org/rfc/rfc3986
