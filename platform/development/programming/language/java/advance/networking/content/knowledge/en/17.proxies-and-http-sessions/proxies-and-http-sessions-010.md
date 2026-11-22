# Redirecting to a Different Target Host and Limiting Credential Sharing

## 1. The Core Problem: HTTP Redirects Can Change the Recipient of Secrets

A Java HTTP client calls `https://api.example.com/v1/orders` and includes `Authorization: Bearer ...`, a login session cookie, or a header containing an API key. The server returns `302 Location: https://files.example.net/new-path`. If the client follows the redirect automatically, **the next request may go to a different server**, using a different hostname, port, TLS certificate, and authentication scope. The fact that the first server was trusted **does not automatically grant permission** for the new server to receive the first server's token.

This lesson belongs to the **Proxies and HTTP Sessions** group: it is necessary to distinguish three types of identity — **origin server**, **proxy**, and **user session/cookie** — and then restrict credential sharing to the appropriate party. Java `java.net.http.HttpClient` has redirect policies `NEVER`, `NORMAL`, and `ALWAYS`, but **that is not the entire secret-control mechanism**.

After this lesson, you should be able to:
1. Explain how redirecting to a different hostname, different port, or different scheme changes the **origin** and can change the **protection space**.
2. Distinguish between `Authorization`, `Proxy-Authorization`, `Cookie`, and custom headers such as `X-Api-Key`.
3. Know that Java 17 `HttpClient.Redirect.NORMAL` blocks HTTPS → HTTP but **is not a hostname allowlist**.
4. Understand why you should not assume by default that the client will automatically strip every header containing secrets when following `Location`.
5. Use `Redirect.NEVER` and validate the URI before building the next request, adding credentials only when the destination is allowed.
6. Recognize risks of cross-host redirects, SSRF, cross-origin auth leaks, POST body replay, and session confusion.
7. Run two Java 17+ programs on loopback yourself: one program that **observes automatic behavior** and one program that **prevents sending tokens to another origin**.

**Core principle:** Only send credentials to **the destination that the credential is authorized for**. A redirect from one server is not consent from the token owner to forward the token to another server.

## 2. A Redirect Chain Can Change Host, Port, and Scheme

Example:

```http
GET /account HTTP/1.1
Host: api.example.com
Authorization: Bearer <token-for-api.example.com>

HTTP/1.1 302 Found
Location: https://partner.example.net/account
```

If followed automatically, the next request may go to:

```http
GET /account HTTP/1.1
Host: partner.example.net
```

The `Authorization` line **should not** be copied automatically just because the initial request had it; the original token may have been issued specifically for `api.example.com`. In the example, the angle-bracket value is an explanatory placeholder, not a real token.

Types of redirects:

| Source → Target | Notable change | Conclusion on token sharing permission |
| --- | --- | --- |
| `https://api.example.com/a` → `https://api.example.com/b` | Same scheme, host, default port | May be the same origin, but realm/path/application scope still applies |
| `https://api.example.com/a` → `https://cdn.example.com/b` | Hostname changed | Different origin, **do not automatically forward origin A's token** |
| `https://api.example.com/a` → `https://api.example.com:8443/b` | Port changed | Different origin, do not assume credentials are shared by default |
| `https://api.example.com/a` → `http://api.example.com/b` | HTTPS → HTTP downgrade | Loses TLS protection on the new hop, **do not send secrets** |
| `http://api.example.com/a` → `https://api.example.com/b` | HTTP → HTTPS upgrade | Still changes origin; new HTTPS does not automatically allow resending the token |
| `https://api.example.com/a` → `https://api.example.com.evil.test/b` | Different host despite similar prefix | Do not trust by string prefix |
| `https://api.example.com/a` → `https://user@api.example.com/b` | Has URI userinfo | Should be rejected/have a clear policy to avoid host/credential confusion |

The "same hostname" condition is weaker than "same origin", and **same origin** does not mean "every credential is allowed for every resource". Authentication realm, endpoint permissions, resource scope, and token audience are also independent policy layers.

## 3. Origin Consists of Scheme + Host + Port

In HTTP, an **origin** is typically defined by the tuple:

```text
origin = (scheme, host, effective port)

https://api.example.com/v1      => (https, api.example.com, 443)
https://api.example.com:443/v2  => (https, api.example.com, 443)
https://api.example.com:8443/v2 => (https, api.example.com, 8443)
http://api.example.com/v2       => (http, api.example.com, 80)
https://files.example.com/v2    => (https, files.example.com, 443)
```

Here, **effective port** is the declared port, or if the URI omits a port, defaults to 443 for HTTPS and 80 for HTTP. The path, query, and fragment **do not create a new origin**, though they still matter for **resource-level authorization**.

Why does the port matter? Two services on the same host on 443 and 8443 may be managed by two different teams. DNS returning the same IP also does not make two URLs the same origin. Conversely, `localhost` and `127.0.0.1` may point to the same machine but **have different hostnames** when comparing origins.

For offline testing, the programs later in this lesson use two loopback servers with source address `127.0.0.1` and target `localhost`. **Do not call that environment two different physical machines**: these are two **different hostnames/origins** simulating a cross-host redirect without sending tokens over the Internet.

### Origin vs. Protection Space

HTTP Basic/Digest authentication has the concept of **protection space**: a scope that typically combines the **origin** with the **realm**, and may also include detailed rules for each authentication scheme. OAuth/Bearer tokens also have audience, scope, expiration, and resource server policy.

Therefore:
- Same origin but a different realm or endpoint may not reuse credentials.
- A different origin must be treated as a new destination, unless the issuer/application explicitly designed the credential to be valid for both.
- **Do not** decide to reuse a token by comparing host prefixes or matching DNS IPs.

## 4. How Do Redirects Work in Java HttpClient?

Java SE 17 `HttpClient.Redirect` has three options:

| Policy | Automatic follow | HTTPS → HTTP | Checks host allowlist? |
| --- | --- | --- | --- |
| `NEVER` | No | Does not follow automatically | **No**, but the app is allowed to check manually |
| `NORMAL` | May follow valid 3xx | **No** | **Does not automatically become an allowlist** |
| `ALWAYS` | May follow valid 3xx | May follow | **No** |

`HttpClient.newHttpClient()` defaults to `Redirect.NEVER`. Choose `NORMAL` when you want auto-follow while avoiding one form of downgrade. However, `NORMAL` **can go from HTTPS hostname A to HTTPS hostname B** when the `Location` response is valid and the client decides to follow. Having valid TLS with hostname B **does not** prove that a token issued for A is authorized to appear at B.

Configuration example:

```java
HttpClient automatic = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();

HttpClient controlled = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
```

This is a **code snippet**; import `java.net.http.HttpClient`. `NORMAL` only specifies basic follow behavior. `NEVER` is appropriate when the application needs to inspect the entire redirect chain **before** sending the next byte.

### Do Not Confuse Redirects with Proxy Forwarding

A client may use a **proxy** for connections to an origin; a `302` response still means changing the target URI of the logical HTTP request. Proxy routing, proxy authentication, and origin authentication are three things that must be considered separately. A `ProxySelector` may choose a different proxy for the new target URI. Do not take proxy credentials meant for proxy P1 and send them directly to origin B or proxy P2.

## 5. Different Types of Secrets Must Not Be Treated as One

| Header/Data | Valid recipient | Rule to remember |
| --- | --- | --- |
| `Authorization: Bearer ...` | **Origin resource server** matching audience/scope | Do not copy to another origin without a security decision |
| `Authorization: Basic ...` | Corresponding protection space/realm of the origin | Basic is only Base64-encoded, requires TLS and exact scope |
| `Proxy-Authorization: ...` | **Proxy** the client is authenticating to | Do not send as an origin credential, do not send to an unknown proxy |
| `Cookie: session=...` | Requests matching domain/path/secure policy of the cookie jar | Cookie scope differs from origin; requires proper CookieHandler/cookie policy |
| `X-Api-Key: ...` | API/service issued the key | **Just a custom header** to a generic HTTP implementation |
| `X-Auth-Token: ...` | Authorized service | Do not assume the library knows this is a secret |
| URL query like `?token=...` | If allowed by design, only the exact endpoint | Easily leaked via logs/redirects/history; avoid putting tokens in URLs |
| mTLS client certificate/private key | Explicitly configured TLS endpoint/service | Do not treat mTLS as permission to share Bearer tokens with any host |

**Important practical point:** An HTTP library may have internal rules for handling standard headers like `Authorization` and `Cookie`, but it **cannot know** that a name like `X-Api-Key` or `X-Internal-Secret` carries business-sensitive values. Do not use a "header not named Authorization" to bypass policy; it may be forwarded automatically.

Even after removing `Authorization`, other types of secrets still need to be reviewed: cookies re-emitted from a cookie jar, custom API keys, signed query strings, POST bodies, and application-generated headers.

## 6. What Does RFC 9110 Recommend When Auto-Redirecting?

RFC 9110, in the section on **redirection**, states the changes a user agent should make when automatically sending a new request following `Location`:

1. Replace the target URI with the URI from `Location` after resolving it relative to the previous request URI.
2. Remove/adjust headers that were **generated by the implementation** and may no longer be appropriate at the new destination: connection-specific headers, proxy-specific headers (e.g., `Proxy-Authorization`), origin-specific headers (e.g., `Host`), cache validators, and resource-specific headers (e.g., `Authorization`/`Cookie` when generated automatically).
3. **Consider removing headers actively added by the caller as well** if there is a security risk, including `Authorization` and `Cookie`.
4. Adjust the method when the redirect status requires it; if changing to GET/HEAD, drop content-specific headers that are no longer appropriate.
5. Detect redirect loops and intervene instead of following infinitely.

Here, **SHOULD** is a recommendation level in the standard, **not a guarantee** that every library/JDK will remove every custom header for every redirect path. The standard does not define the meaning of `X-Api-Key` as something required to be stripped automatically.

**Security consequence:** The app must **establish its own credential-sharing policy**. Auto-follow is convenient, not a complete trust boundary. A safe policy might be: **do not follow cross-origin redirects** by default, or only follow after the destination is on an allowlist and **credentials dedicated to that destination** are issued.

## 7. Java 17 Test: Observing Which Headers Follow a Redirect to Another Hostname

The first program creates two HTTP servers **on loopback only**:
- The source server handles `/jump` at `127.0.0.1:<port A>`.
- It returns `302 Location: http://localhost:<port B>/receive`.
- The target server receives the request and returns only **flags indicating presence/absence of headers**, without printing secret values.
- The initial request contains dummy values `Bearer fake-example-only`, `sid=fake`, `X-Api-Key: fake-key`.
- Clients `NEVER` and `NORMAL` are run separately for comparison.

Save to the file **`CrossHostRedirectObservation.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

public class CrossHostRedirectObservation {
    private static void respond(HttpExchange e, int code, String body)
            throws IOException {
        byte[] b = body.getBytes(StandardCharsets.UTF_8);
        e.sendResponseHeaders(code, b.length);
        try (var out = e.getResponseBody()) { out.write(b); }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        HttpServer target = HttpServer.create(new InetSocketAddress(loopback, 0), 0);
        AtomicInteger targetHits = new AtomicInteger();
        target.createContext("/receive", e -> {
            targetHits.incrementAndGet();
            respond(e, 200, "auth=" + (e.getRequestHeaders().getFirst("Authorization") != null)
                    + ",cookie=" + (e.getRequestHeaders().getFirst("Cookie") != null)
                    + ",apiKey=" + (e.getRequestHeaders().getFirst("X-Api-Key") != null));
        });
        target.start();

        HttpServer source = HttpServer.create(new InetSocketAddress(loopback, 0), 0);
        int targetPort = target.getAddress().getPort();
        source.createContext("/jump", e -> {
            e.getResponseHeaders().add(
                    "Location", "http://localhost:" + targetPort + "/receive");
            respond(e, 302, "Moved");
        });
        source.start();

        try {
            URI from = URI.create("http://127.0.0.1:"
                    + source.getAddress().getPort() + "/jump");
            HttpRequest request = HttpRequest.newBuilder(from)
                    .header("Authorization", "Bearer fake-example-only")
                    .header("Cookie", "sid=fake")
                    .header("X-Api-Key", "fake-key").GET().build();
            HttpResponse<String> never = HttpClient.newBuilder()
                    .followRedirects(HttpClient.Redirect.NEVER).build()
                    .send(request, HttpResponse.BodyHandlers.ofString());
            System.out.println("NEVER status=" + never.statusCode()
                    + " targetHits=" + targetHits.get());
            HttpResponse<String> normal = HttpClient.newBuilder()
                    .followRedirects(HttpClient.Redirect.NORMAL).build()
                    .send(request, HttpResponse.BodyHandlers.ofString());
            System.out.println("NORMAL status=" + normal.statusCode()
                    + " finalHost=" + normal.uri().getHost()
                    + " body=" + normal.body());
            System.out.println("targetHits=" + targetHits.get());
        } finally {
            source.stop(0);
            target.stop(0);
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac CrossHostRedirectObservation.java
java CrossHostRedirectObservation
```

**Verified stdout on this lesson's JDK 17 API environment:**

```text
NEVER status=302 targetHits=0
NORMAL status=200 finalHost=localhost body=auth=false,cookie=false,apiKey=true
targetHits=1
```

### Reading the Results Without Drawing Wrong Conclusions

- `NEVER status=302 targetHits=0`: no automatic follow request was sent to the target.
- `NORMAL status=200 finalHost=localhost`: the client automatically followed `Location` to a different hostname and received a successful response.
- `auth=false,cookie=false`: in **the tested implementation/JDK build**, `Authorization` and `Cookie` added directly to the request **were not sent to the cross-host destination**.
- `apiKey=true`: in the same test, **the custom header `X-Api-Key` still appeared at the new destination**.
- `targetHits=1`: the target received one request after running `NORMAL`.

**Limitation to remember:** This is **an observed result for one specific version/implementation**, not an API contract guaranteeing that every JDK/HTTP library will strip those exact headers in all situations. The fact that auth/cookie were dropped in the test **does not justify** allowing automatic redirects for all URLs containing secrets. Observing the custom header travel with the request is enough to prove that an assumption like "the client automatically knows how to strip all secrets" is unsafe.

**Do not run the example with real credentials.** It intentionally sends a dummy `X-Api-Key` to another hostname for testing. All servers bind to local loopback; there is no Internet traffic. The address `localhost` must resolve to IPv4 `127.0.0.1` in the test environment; if the system prefers IPv6 `::1` while the listener only binds IPv4, the connection may fail. When testing IPv6 independently, configure the hostname/address accordingly.

## 8. Why Are Custom Headers More Dangerous Than Standard Names?

HttpClient sees headers:
- `Authorization` has clear semantics in HTTP authentication.
- `Cookie` is known as the HTTP session mechanism, and many clients have specific policies for it.
- `X-Api-Key` is just an extension header name string; the API cannot know it is a secret without business configuration.

A system might use:
- `X-Api-Key` for a REST API key.
- `X-Session-Token` for a custom bearer token.
- `X-Internal-Signature` for a per-request signature.
- `X-Tenant-Secret` for a multi-tenant secret.
- `X-User-JWT` for a JWT.
- `X-Correlation-ID` for a non-sensitive ID.

You cannot assume every header starting with `X-` must be deleted: some headers only carry public metadata. However, the **conservative default** when changing origin is **not to copy any caller-provided header** except for a classified list permitted for the new destination. `Accept`/`User-Agent` (usually less sensitive) and headers that could reveal tenant, user identity, internal addresses, or secret data should be evaluated separately.

A header whitelist for copying, built **at the application layer**, is safer than a blacklist containing only `Authorization`/`Cookie` because a blacklist easily misses new custom secret names added later.

## 9. Same-Origin Rules Are Not Enough for All Authentication Schemes

Suppose on the same origin `https://api.example.com`:
- `/public` allows anonymous access.
- `/admin` requires credentials with an admin role.
- `/billing` requires a billing audience/scope token.
- `/tenant/A` and `/tenant/B` may be tenant-isolated.

A token accessing `/billing` **is not automatically valid** to send to `/admin`, even with the same scheme/host/port. HTTP `realm` or OAuth token audience/scope must be enforced. **Origin comparison** is only a useful minimum boundary for redirects, not a complete **authorization decision**.

With Basic auth: the server may send `401 WWW-Authenticate: Basic realm="zone-a"`. Other resources in the realm may share credentials according to the rules of the authentication scheme. If switching to a new host or realm, the client must not assume the original username/password is always right or permitted.

With OAuth 2.0/Bearer: issue **an access token for the resource server with the right audience**; check scope/permissions, expiration, and token binding if applicable. Do not reuse a token from service A for service B just because both services belong to the same organization.

## 10. Separating Origin 401 from Proxy 407

In an architecture with an HTTP proxy:

```text
Java HttpClient
   │
   │  Credentials for proxy P if P requires them
   ▼
Proxy P ──────────────────► Origin A
   │                            │
   │                            ├── 401 WWW-Authenticate
   │                            │      client -> Authorization to origin A
   │                            │
   └── 407 Proxy-Authenticate
          client -> Proxy-Authorization to proxy P
```

| Component | Challenge | Credential header | Sharing boundary |
| --- | --- | --- | --- |
| **Origin server** | `401 Unauthorized` + `WWW-Authenticate` | `Authorization` | By origin, realm, and authentication policy |
| **HTTP proxy** | `407 Proxy Authentication Required` + `Proxy-Authenticate` | `Proxy-Authorization` | By proxy / proxy's protection space |
| **Cookie session** | `Set-Cookie` from origin; client sends back `Cookie` when appropriate | `Cookie` | By cookie domain/path/Secure and cookie policy |

**Never** take credentials answering a `407` for a proxy and put them into `Authorization` sent to the origin. Nor copy an origin's bearer token into `Proxy-Authorization`. The two types of credentials have different recipients.

In Java, `HttpClient.Builder.proxy(ProxySelector)` chooses how to use proxies, while `HttpClient.Builder.authenticator(Authenticator)` can supply credentials for the matching challenge. Proxy selection may change between target URIs after a redirect; the application must not **hardcode** one proxy password for every connection after the origin changes.

### HTTPS Through a Proxy

With an HTTP proxy and an HTTPS target, the client typically uses `CONNECT` to establish a tunnel to the origin and then performs TLS to the origin through the tunnel. Proxy credentials authenticate to the proxy; the origin's TLS certificate must still be verified against the exact target hostname. The proxy can observe the CONNECT destination and network metadata; if the environment has organization-configured TLS inspection, observability may differ. Do not treat the proxy as an origin permitted to read application tokens just because it forwards requests.

## 11. Session Cookies Have Their Own Scope, Not Identical to Origin

A cookie has a common structure:

```http
Set-Cookie: sid=example-value; Path=/; Secure; HttpOnly; SameSite=Lax
```

Attributes:
- **Domain**: if omitted, the cookie is typically host-only; if `Domain=example.com` is present, it may apply to matching subdomains according to cookie rules.
- **Path**: restricts which request paths are eligible to receive the cookie; not as strong a security isolation mechanism as origin.
- **Secure**: requires sending the cookie over a suitable secure transport; does not mean it should be sent to every HTTPS hostname.
- **HttpOnly**: restricts accessing the cookie via scripting APIs in supported environments; does not prevent an HTTP client from sending the cookie when valid.
- **SameSite**: an important attribute for browser cross-site request contexts; **do not assume** Java `CookieManager` enforces the exact same rule set as modern browsers.

**Cookie scope can be broader than origin with respect to port/subdomain.** For example, a cookie for `example.com` may be sent to another service on a matching subdomain even if the origins do not match. Cookie domain/path/Secure must therefore be considered separately when the client follows redirects.

### Java CookieHandler

`HttpClient.Builder.cookieHandler(CookieHandler)` allows using a cookie handler, typically `CookieManager`, to store `Set-Cookie` and supply cookies for requests matching the policy. On a redirect, the cookie jar can decide **which cookies match the scope of the new destination**, rather than blindly forwarding a `Cookie` header added manually by the caller.

Example creating a cookie manager (**non-standalone code snippet**):

```java
CookieManager cookies = new CookieManager(
        null, CookiePolicy.ACCEPT_ORIGINAL_SERVER);
HttpClient client = HttpClient.newBuilder()
        .cookieHandler(cookies)
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
```

Imports `java.net.CookieManager`, `CookiePolicy`, and `java.net.http.HttpClient`. The `ACCEPT_ORIGINAL_SERVER` policy does not replace reviewing session design; especially when multiple tenants/auth contexts share a client/cookie jar, cookie stores must be separated or scope explicitly managed.

**Do not put a single shared CookieManager for independent users** if cookie sessions need to be isolated. Connection pooling/concurrency reuse does not equate to sharing user sessions.

## 12. Another HTTPS Destination Can Still Receive the Wrong Data

The statement "redirecting to HTTPS is still safe" is missing conditions.

```text
https://api.example.com/private
       │ 302 Location
       ▼
https://evil.example/collect
```

The certificate of `evil.example` may be completely valid for that hostname itself. TLS protects **the connection to evil.example**; it does not confirm that **evil.example is authorized to receive api.example.com's token**.

You must separate:
1. **Transport authentication:** TLS has verified that the server matches **the hostname the client intended to connect to**.
2. **Application authorization:** Is that server allowed to receive credentials, data, request bodies, and user actions?

Successful TLS only solves the first part. When a redirect changes the host, the second policy must be checked using an allowlist and token scoping.

### HTTPS → HTTP Downgrade

`Redirect.NORMAL` blocks automatic redirects from HTTPS to HTTP; `Redirect.ALWAYS` does not block under that policy. Sending Authorization, cookies, or sensitive bodies over plaintext HTTP can expose them in transit. For APIs with secrets, **forbid downgrades** even when doing manual redirects, unless there is a specially controlled requirement with no sensitive data.

## 13. Redirects Can Forward POST Bodies and Methods

Not only headers can leak; a request carrying **a body containing PII, financial data, keys, or uploads** is also at risk of being sent to the new destination.

| Status | Common semantics | Risk to check |
| --- | --- | --- |
| `301 Moved Permanently` | Long-term redirect | Java HttpClient may change POST → GET; URL/headers still need control |
| `302 Found` | Historically temporary redirect | Java HttpClient may change POST → GET; target may change host |
| `303 See Other` | Read result from another URI (usually GET) | May change method; should not carelessly copy content headers |
| `307 Temporary Redirect` | Preserves method and body semantics | **POST/upload body may be resent to another host** |
| `308 Permanent Redirect` | Preserves method and body semantics | **Body is replayed**, requires checking idempotency and target permissions |

In Java 17, `HttpClient.Redirect` explicitly states that 301/302 turn POST into GET when auto-following. Meanwhile, 307/308 aim to preserve the method; if the body publisher is not replayable, the operation may fail. Do not rely on this table to assume every HTTP library behaves identically in all situations.

When performing manual redirects for requests with side effects:
- Do not automatically replay `POST` to another target just because the status is 307/308.
- Check token/audience, body replayability, and destination permissions.
- Use an idempotency key and retry policy if supported by the server.
- Unless explicitly required, reject cross-origin redirects for write operations.

## 14. Safe Java 17+ Example: Follow Redirects Only on the Same Origin

The second program simulates:
- Server **origin A** at `127.0.0.1:<port A>`.
- `/to-same` returns `302 Location: /same`; the new URI has the **same origin**. The client re-attaches a dummy token for the new request after validation.
- `/to-other` returns `302 Location: http://localhost:<port B>/landing`; the new URI has a **different host/port**. The client **does not send a request** to server B.
- `HttpClient` uses `Redirect.NEVER`, so there is **no automatic follow** outside the application's control.

The program performs only **one redirect hop** and does not allow outbound Internet requests. The token value is dummy and contains no real secret.

Save to the exact file **`ScopedRedirectDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

public class ScopedRedirectDemo {
    private static void reply(HttpExchange e, int code, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        e.sendResponseHeaders(code, bytes.length);
        try (var out = e.getResponseBody()) { out.write(bytes); }
    }

    private static int effectivePort(URI uri) {
        if (uri.getPort() >= 0) return uri.getPort();
        if ("https".equalsIgnoreCase(uri.getScheme())) return 443;
        if ("http".equalsIgnoreCase(uri.getScheme())) return 80;
        return -1;
    }

    private static boolean sameOrigin(URI a, URI b) {
        return a.getHost() != null && b.getHost() != null
                && a.getScheme() != null && b.getScheme() != null
                && a.getScheme().equalsIgnoreCase(b.getScheme())
                && a.getHost().equalsIgnoreCase(b.getHost())
                && effectivePort(a) == effectivePort(b)
                && b.getRawUserInfo() == null
                && b.getRawFragment() == null;
    }

    private static HttpResponse<String> oneHop(
            HttpClient client, URI from, String token) throws Exception {
        HttpRequest first = HttpRequest.newBuilder(from)
                .header("Authorization", "Bearer " + token)
                .timeout(Duration.ofSeconds(5)).GET().build();
        HttpResponse<Void> initial = client.send(first,
                HttpResponse.BodyHandlers.discarding());
        if (initial.statusCode() != 302) {
            throw new IOException("Expected a 302 for this demo");
        }
        String location = initial.headers().firstValue("Location")
                .orElseThrow(() -> new IOException("No Location"));
        URI next = initial.uri().resolve(location);
        if (!sameOrigin(from, next)) {
            System.out.println("cross-target-allowed=false");
            return null;
        }
        System.out.println("same-target=" + next.getPath());
        HttpRequest second = HttpRequest.newBuilder(next)
                .header("Authorization", "Bearer " + token)
                .timeout(Duration.ofSeconds(5)).GET().build();
        return client.send(second, HttpResponse.BodyHandlers.ofString());
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        AtomicInteger targetHits = new AtomicInteger();
        HttpServer external = HttpServer.create(new InetSocketAddress(loopback, 0), 0);
        external.createContext("/landing", e -> {
            targetHits.incrementAndGet();
            reply(e, 200, "external");
        });
        external.start();
        HttpServer origin = HttpServer.create(new InetSocketAddress(loopback, 0), 0);
        origin.createContext("/to-same", e -> {
            e.getResponseHeaders().add("Location", "/same");
            reply(e, 302, "redirect");
        });
        origin.createContext("/same", e -> reply(e, 200,
                "auth=" + (e.getRequestHeaders().getFirst("Authorization") != null)));
        origin.createContext("/to-other", e -> {
            e.getResponseHeaders().add("Location", "http://localhost:"
                    + external.getAddress().getPort() + "/landing");
            reply(e, 302, "redirect");
        });
        origin.start();
        try {
            HttpClient client = HttpClient.newBuilder()
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .build();
            URI base = URI.create("http://127.0.0.1:"
                    + origin.getAddress().getPort());
            HttpResponse<String> same = oneHop(
                    client, base.resolve("/to-same"), "fake-local-only");
            System.out.println("same-response=" + same.statusCode()
                    + "," + same.body());
            oneHop(client, base.resolve("/to-other"), "fake-local-only");
            System.out.println("target-hits=" + targetHits.get());
        } finally {
            origin.stop(0);
            external.stop(0);
        }
    }
}
```

Compile and run:

```bash
javac ScopedRedirectDemo.java
java ScopedRedirectDemo
```

Verified stdout with Java 17:

```text
same-target=/same
same-response=200,auth=true
cross-target-allowed=false
target-hits=0
```

### Step-by-Step Explanation

1. `HttpClient.Redirect.NEVER` ensures the first `send` **does not auto-follow**; it returns `302` for the application to inspect.
2. `Location` is resolved relative to `initial.uri()`. For example, `/same` stays on the same origin.
3. `sameOrigin(...)` compares **scheme, hostname, effective port**, and rejects URIs with userinfo or a fragment. It uses `equalsIgnoreCase` for hostname/scheme following standard semantics.
4. If same-origin, the program **builds a new second request** and **explicitly adds** the dummy Authorization for the confirmed origin, without copying all headers.
5. For `Location` pointing to `localhost:<port B>`, `sameOrigin(...)` returns false because the hostname/port differ. The program does not call `send` a second time, so server B has `target-hits=0`.
6. Both servers are bound to loopback and stopped in `finally`.

### This Is Not Yet a Complete Production Anti-SSRF Suite

The `sameOrigin` function in the demo is **a minimum condition for the exercise**. To deploy a network client that may receive arbitrary external URLs, you need to add:
- Mandatory HTTPS and valid certificate/hostname verification for production.
- A managed allowlist of hostname/port/service ID; compare against the **originally allowed origin**, not just the previous hop's origin.
- Credential scoping by exact realm/audience/path; same-origin alone is not enough.
- Controlled DNS resolution, IP range/egress filtering, and protection against DNS rebinding/TOCTOU via network-level policy.
- Limits on hop count, total time, response size, request methods, and request bodies.
- Managing another approved origin with **a separate token for that origin**.
- Isolating proxy credentials/cookie jars across different sessions/tenants.

The demo code **does not** block every URL exploitation path in a complex Internet environment; it clearly illustrates where **the decision must be placed** before forwarding credentials to another destination.

## 15. Manual Redirects with Multiple Hops: Validate Every Step

A server might return:

```text
api.example.com/old
   └─ 302 → api.example.com/current
               └─ 307 → partner.example.net/upload
                           └─ 200
```

If you only validate the first hop and then enable auto-follow for the next request, the app can still reach the partner. You must validate **every redirect hop**.

Conceptual flow:

```text
originalAllowedOrigin = origin the application is allowed to call
currentUri = initialUri
redirectCount = 0

loop:
  validate currentUri, network destination, scheme, and policy
  choose credentials *for currentUri*, not for the previous host
  send exactly one HTTP request using Redirect.NEVER
  if response is not a supported redirect:
      return response
  extract Location; reject if missing or malformed
  nextUri = response.uri().resolve(Location)
  validate nextUri AGAIN against originalAllowedOrigin/allowlist
  decide method/body replay and safe headers for next hop
  if redirectCount exceeds max: abort
  currentUri = nextUri
```

This is **pseudocode**, not complete Java. Design points:
- `Redirect.NEVER` keeps decision authority in the application.
- Only build the next request after the URI has been **resolved and validated**.
- Do not take all headers from the initiating request and apply them to every hop.
- Each hop has timeouts, deadlines, and audit metadata.
- If moving from A to B is required and both are allowed, supply **credentials specifically approved for B**, rather than reusing A's by assumption.
- For POST/PUT/PATCH, check the request body and idempotency before resending.

**Do not** validate the target hostname using only `endsWith("example.com")`: `notexample.com` and internationalized domain/punycode variants, trailing dots, and host normalization can cause simple string checks to fail. Use standard URI parsing and a normalized allowlist combined with network constraints.

## 16. Why Is Host Comparison Not Enough to Prevent SSRF?

An open redirect can be used to make a server-side Java client call:
- `127.0.0.1`/`localhost`, local administrative services.
- RFC 1918/private IPv4 ranges, unique-local IPv6.
- Link-local `169.254.0.0/16` or `fe80::/10`.
- Cloud instance metadata endpoints.
- Internal Kubernetes/service mesh endpoints the application is not authorized to access.
- An attacker-controlled domain pointing to an internal IP after DNS rebinding.

If the Java process has broad network access, a redirect from a public URL can become **SSRF** even if the body carries no token. With tokens/headers, SSRF also risks leaking credentials.

Layers of defense:
1. Do not follow redirects automatically when URL input is untrusted.
2. Allowlist scheme, hostname, port, and protocol; reject userinfo/fragment when unnecessary.
3. Resolve DNS through a controlled mechanism and ensure **the address actually connected to** does not violate policy. Calling `InetAddress.getAllByName()` before `HttpClient.send` alone does not fully solve DNS rebinding/time-of-check/time-of-use.
4. Use egress firewalls, service identity/mTLS, and proxy rules at the infrastructure layer.
5. Segregate network permissions and credentials by service/tenant.
6. Limit redirects, timeouts, response bytes, and connection counts.

**Forbidding credential forwarding to an unauthorized origin** is only one layer; you must also block **sending requests to unauthorized internal destinations** even when the request carries no secrets.

## 17. ProxySelector, Authenticator, and Token Scope

Java `HttpClient.Builder` has these configurations:

```java
HttpClient client = HttpClient.newBuilder()
        .proxy(proxySelector)
        .authenticator(authenticator)
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
```

This is a **code snippet**; you must provide `ProxySelector proxySelector` and `Authenticator authenticator` along with imports. `ProxySelector` decides the proxy for URIs according to policy; `Authenticator` returns credentials based on the challenge/context (e.g., requestor type PROXY or SERVER). You should not have an `Authenticator` return the same username/password for **every hostname and every requestor type**.

When implementing `Authenticator`:
- Check `getRequestorType()` to distinguish `PROXY` from `SERVER`.
- For `SERVER`, verify protocol/host/port/realm/authentication scheme against an allowlist; do not return service A's password when service B asks for `401`.
- For `PROXY`, verify proxy address/port/realm against configuration; do not give proxy credentials to an origin server.
- Do not store passwords in string literals/logs/source repositories.
- Do not assume all forms of Bearer tokens will be managed automatically by `Authenticator`. Java's built-in `HttpClient` has authentication scheme limitations; applications using custom Bearer headers need their own policy.

Some JDK security configurations may restrict Basic authentication over proxy tunnels via properties. Do not remove the policy just to send passwords over unprotected channels; proxy and scheme configuration must be verified against the actual runtime documentation.

### Why Might Proxy Auth Change After a Redirect?

The new target URL may have a different scheme, hostname, or port; `ProxySelector` may choose **a different proxy or a direct connection**. If the app arbitrarily copies `Proxy-Authorization` from the old request to the new request, it may send proxy P1's credentials to the wrong party. Let the framework handle challenge/proxy state and verify that the `Authenticator` configuration is properly scoped.

## 18. Cookie/Session Fixation and User Isolation

An `HttpClient` can be reused across many requests, but if it shares a `CookieManager` among **multiple independent users**, user A's cookies can accompany user B's requests when host/path scopes overlap. Redirects can make that bug more visible when crossing an origin with a shared cookie jar.

For multi-tenant applications:
- Have **a separate cookie jar per user/session/security principal** or choose an architecture that does not use automatic cookies in the backend.
- Do not put user A's session cookies into requests initiated by user B.
- Distinguish application session IDs from HTTP connection reuse; the two concepts are **not identical**.
- An overly broad cookie `Domain` can allow untrusted subdomains to receive cookies. Evaluate domains that may be independently controlled.
- Set `Secure`/`HttpOnly`/`SameSite` appropriately on the web side, but **do not** assume Java CookieManager behaves identically to a browser.

A related topic is **session fixation**: if an untrusted origin can control the session identifier used by the client, the application may be bound to an unwanted session. Limiting redirects and sharing cookies only within the proper scope reduces some attack paths, though server-side session rotation, binding, and authorization checks are still required.

## 19. Location Is Not Proof of a Trusted Destination

`Location` is **data supplied by the responding server**. It can be:

```http
Location: /new
Location: https://cdn.example.net/file
Location: //partner.example.org/upload
Location: https://api.example.com:8443/next
Location: http://127.0.0.1:8080/admin
```

These forms are not equivalent:
- `/new` is an absolute path, which normally resolves to the same origin.
- `https://cdn.example.net/file` changes the hostname.
- `//partner.example.org/upload` inherits the scheme but **changes the authority/host**.
- `:8443` changes the port, changing the origin.
- `http://127.0.0.1:8080` may lead to an unauthorized local destination.

With manual redirects, use `response.uri().resolve(location)` and then validate the resolved URI. **Do not concatenate URLs as strings**; do not treat `Location` as a "trusted" string just because it appeared in a TLS-authenticated response. TLS only authenticates the source server; it does not turn every path the source suggests into a destination authorized to receive data.

### Query Strings and Fragments

Queries can contain access codes/signed URLs; redirects can cause leaks via logs or other destinations. Fragments are typically not sent to the origin in the HTTP request-target, but they matter for URI resolution and application policy. The demo rejects `getRawFragment()!=null` to keep scope simple. In production, decide fragment policy per protocol, and do not use fragments as a secret-keeping mechanism.

## 20. Do Not Automatically Copy All Headers When Building a Redirected Request

What **not** to do:

```java
HttpRequest.Builder next = HttpRequest.newBuilder(targetUri);
// DESIGN ERROR: copies all headers from the old request,
// then sends them without evaluating the scope of each header.
originalRequest.headers().map().forEach(
        (name, values) -> values.forEach(
                value -> next.header(name, value)));
```

This is a **counterexample snippet** depending on `targetUri`, `originalRequest`, and imports, and **does not run standalone**. It can copy Authorization, Cookie, X-Api-Key, X-Tenant, signed authorization, or custom headers to another origin. Certain headers restricted by the Java HTTP implementation can also cause the program to error.

A safer policy:

```text
Is target allowlisted and has the right identity?
  No -> reject, do not send

If allowed:
  - Build a new HttpRequest from the validated URI.
  - Only add headers that are truly needed and permitted for the target.
  - Choose the exact credential issued for the target; do not copy old tokens by default.
  - Choose method/body according to status semantics and replay policy.
  - Use a cookie store matching the user + scope; do not copy Cookie manually.
  - Do not copy Proxy-Authorization; let the proxy/auth framework manage it.
```

**Good strategy:** **rebuild from minimal trusted inputs** instead of **copy then delete secrets**. A blacklist can miss a secret header name added later by another team.

## 21. Client Automatic Rules Differ from Application Security Rules

HTTP libraries may choose to strip or keep headers based on many conditions:
- Hostname change.
- Port change.
- HTTPS → HTTP.
- Presence of `Authenticator` or `CookieHandler`.
- Whether the header was generated by the client or **set manually by the application**.
- `401/407` authentication challenges, proxy routing.
- JDK version and implementation.

Therefore, avoid two overstatements:
- **"Java HttpClient always copies Authorization when redirecting to another host."** Not true for the verified Java 17 environment.
- **"Java HttpClient always strips all credentials on redirect."** Also not true; custom `X-Api-Key` in the test was still forwarded.

The right conclusion: **the application must not treat an HTTP library's implicit header-forwarding policy as a complete security boundary**. You need to test the specific implementation and apply guardrails at the app/network layers.

If another framework such as Apache HttpClient, OkHttp, curl, a browser, or a new JDK version is used, you must check the semantics of **that client**. The local Java 17 results in this lesson do not automatically generalize to other clients.

## 22. Redirecting to the Same Host on a Different Port Is Still a Problem

Example:

```text
https://api.example.com/v1
    -> 302 Location: https://api.example.com:8443/admin
```

It is still the hostname `api.example.com`, but the new destination has a **different port**, so it is a **different origin**. Port 8443 might be an admin service operated by another department. Do not use the condition:

```java
boolean allowed = from.getHost().equalsIgnoreCase(next.getHost());
```

to decide whether to re-supply Authorization; that condition ignores scheme/port. The `sameOrigin` demo in section 14 checks all three components.

In the case of cookies, domain/path attributes generally **do not isolate by port**; this is another reason not to treat cookie scope as identical to the origin boundary. If multiple services with different security levels run on different ports of the same host, session/cookie scoping must be designed very carefully.

## 23. Redirecting to a Proxy or New Proxy Does Not Mean Arbitrary Credential Forwarding

A normal redirect changes the **target URI**; it does not directly say "send Proxy-Authorization to proxy X". The proxy decision is made by `ProxySelector` or network configuration for each request. After a redirect:
1. The new target URI is resolved.
2. Client/proxy configuration selects the appropriate routing.
3. If the proxy requires authentication, handle `407` with credentials for that exact proxy.
4. If the origin requires authentication, handle `401` with credentials for that exact origin.
5. Credentials must not be reused across protection spaces without a valid policy.

Example:
- The initial request `https://internal.example` goes through internal proxy P1.
- A redirect to `https://partner.example.net` goes through proxy P2 per routing policy.
- The password used for P1 **is not** the default password for P2 or the partner.

**Proxy-Authorization differs from Authorization** in both where it is used and who is authorized. When using proxy authentication via `Authenticator`, check `RequestorType.PROXY` and the requested proxy attributes; do not return the same password for every challenge.

## 24. Logging and Observability Without Leaking Tokens

When investigating cross-host redirects, log:
- Correlation/request ID (containing no secrets).
- Normalized initial origin, **without logging userinfo/tokens**.
- Destination origin of each hop.
- Redirect status code and hop count.
- Policy (NEVER/NORMAL/ALWAYS or manual).
- Allow/deny decision and reason at the metadata level.
- Whether scheme, hostname, port, proxy, or realm changed.
- Only the header category names to observe, **never log the values** of `Authorization`, `Cookie`, `X-Api-Key`.
- Timeout/network/cert/error metrics.

Safe log example:

```text
requestId=abc-123
hop=1
fromOrigin=https://api.example.com:443
toOrigin=https://cdn.example.net:443
redirectStatus=302
decision=DENY_CROSS_ORIGIN
credentialReused=false
```

Do not log full URLs if query/path contains sensitive information, do not record raw response headers containing `Set-Cookie`/signed URLs, and do not print API keys to stdout in tests. The two demo programs only return true/false flags to illustrate forwarding behavior without exposing the dummy secret.

### Practical Testing Requires Protecting Logs

If enabling HTTP client debug logs or using packet capture, use a test environment with dummy tokens. Remember that HTTPS to the origin can protect data between client and origin, but TLS-inspecting proxies/CDNs/edges may be able to view requests at legitimate TLS termination points. Do not use production credentials for testing.

## 25. Regression Testing for Redirect Safety

| Scenario | Security expectation |
| --- | --- |
| Valid same-origin/path redirect | Can follow after confirming resource-level credential scope |
| Redirect to non-allowlisted different hostname | **Do not send request**, or stop before supplying credentials |
| Redirect to same hostname but different port | Do not share token by default |
| HTTPS → HTTP | Do not forward secrets, normally reject |
| HTTP → HTTPS new host | Do not share token by default even with TLS |
| `Location: //evil.example/path` | Resolve to different hostname then reject per policy |
| Missing/invalid `Location` | Do not guess target; report error |
| Cross-host response 302s back to original origin | Do not consider history safe if an unauthorized hop already occurred |
| 307/308 with sensitive POST body | Do not automatically replay to an unauthorized destination |
| 302 POST → GET | Do not forward inappropriate content-specific headers |
| Custom `X-Api-Key` on original request | Do not auto-copy cross-origin; test proves the rule |
| Shared cookie jar for two users | Do not share session cookies across user contexts |
| Proxy changes after redirect | Do not forward old proxy's credentials to the new proxy |
| 401 origin vs 407 proxy | Credentials go to the right recipient, headers are not swapped |
| Host points to private/link-local IP | Egress policy blocks if app may only access public Internet |
| DNS rebinding between validation and connection | Network-level controls must block unauthorized connects |
| Redirect loop of hundreds of hops | Max redirects/deadline, no infinite hang |

For each test, verify **whether the target server actually received a request**, not just the final HTTP status. In the manual demo, `target-hits=0` is concrete proof that the request to the unauthorized origin **was not sent**.

## 26. Common Mistakes and Fixes

1. **Checking only the HTTPS scheme.** TLS does not decide whether the resource server is authorized to receive the token. Check allowlist/credential audience as well.
2. **Comparing only the hostname.** Misses scheme and port changes; compare normalized origins.
3. **Believing `Redirect.NORMAL` prevents cross-host.** NORMAL mainly prevents HTTPS → HTTP downgrades; it is **not** a list of allowed target hosts.
4. **Believing `Redirect.ALWAYS` "guarantees connection success".** Limits/certificate errors still apply and dangerous downgrades can occur.
5. **Using one custom `X-Api-Key` header for all requests.** Business headers may be forwarded automatically to a new origin; bind them per target.
6. **Copying all headers in a loop.** Can carry Authorization/Cookie/proxy tokens; rebuild from a whitelist.
7. **Reusing A's OAuth token for B.** Audience/scope/issuer policies may not allow it.
8. **Treating Basic realm as a global credential.** Protection space is scoped by origin/realm; do not apply the password to every server.
9. **Copying `Proxy-Authorization` when following.** Proxy credentials are not origin credentials.
10. **Using the same CookieManager for all users.** Can mix sessions across tenants; isolate cookie jars.
11. **Assuming cookies are irrelevant because Authorization was removed.** CookieHandler may attach its own cookies matching the target.
12. **Ignoring 307/308.** POST bodies can be resent, not just headers.
13. **Assuming 302 only changes the path.** `Location` can be an absolute URI, changing host/port/scheme.
14. **Using unnormalized host `endsWith(...)`.** Easily fooled by domain suffixes, IDN/punycode, and similar names.
15. **Validating DNS only once.** DNS rebinding or connection resolution differing from validation causes TOCTOU; egress controls are needed.
16. **Not limiting redirects.** Can cause loops, multi-hop SSRF, or exhaustion.
17. **Ignoring credential source.** Headers added manually by the application and headers generated by the client/authenticator may be handled differently.
18. **Logging tokens for debugging.** Easily leaks via logs/APM/tracing; log only allow/deny info and status.
19. **Putting tokens in URIs.** Query/userinfo can travel through redirects, logs, or browser history.
20. **Seeing Java 17 strip Authorization in a test and concluding general safety.** Other implementations/headers behave differently; the X-Api-Key test shows guardrails are needed.

## 27. Self-Check Questions

**Q1.** `https://api.example.com/a` redirects to `https://cdn.example.com/b`. Does both being HTTPS mean the token can be reused?  
**Answer:** No. The two URLs have different hostnames/origins. The CDN's TLS certificate does not prove the CDN is authorized to receive the Bearer token for the API.

**Q2.** Do `https://api.example.com:443` and `https://api.example.com` have the same origin?  
**Answer:** Yes, if the hostname/scheme match, explicit port 443 and default HTTPS port 443 are equivalent. Realm/resource scope must still be checked.

**Q3.** `https://api.example.com` redirects to `https://api.example.com:8443`. Can Authorization be shared by default?  
**Answer:** No; different effective port means a different origin.

**Q4.** Which type of redirect does `HttpClient.Redirect.NORMAL` explicitly block in the Java 17 API?  
**Answer:** HTTPS → HTTP downgrade. It does not prevent all cross-host redirects.

**Q5.** If a test shows `Authorization` is stripped cross-host, what about `X-Api-Key`?  
**Answer:** There is no guarantee the library knows this custom header name contains a secret; the Java 17 test showed it was forwarded to the target.

**Q6.** Does `Proxy-Authorization` have the same purpose as `Authorization`?  
**Answer:** No. Proxy-Authorization is for the proxy (typically after 407); Authorization is for the origin server (typically after 401).

**Q7.** Are cookies scoped strictly by the origin tuple?  
**Answer:** Not completely. Cookie scope is mainly by domain/path/Secure and other rules; port does not create cookie isolation like origin does, and Java CookieManager has its own semantics.

**Q8.** Why is `Redirect.NEVER` useful for security?  
**Answer:** It returns the 3xx so the app can resolve/validate each Location before building a new request and deciding credentials per target.

**Q9.** Can `Location: //other.example.com/x` be mistaken for a same-host path?  
**Answer:** Yes. It is a network-path reference, which can change the hostname when resolved.

**Q10.** How does the `ScopedRedirectDemo` demo check a different-origin destination?  
**Answer:** It compares scheme/host/effective port and does not send the follow request when they do not match. `target-hits=0` proves the target received no request.

**Q11.** Can using a shared `X-Tenant-Id` across multiple tenants leak in a redirect?  
**Answer:** Possibly. Even though it is not a standard credential, it can still reveal the tenant or control access permissions; headers should be classified and whitelisted per destination.

**Q12.** If a server returns 307 to a new storage host, should a POST body containing internal documents be resent?  
**Answer:** Only if the storage target is allowed, the body/credentials are right for the target, and the replay policy is approved. The safe default is to reject.

**Q13.** Does using `InetAddress.getAllByName` to filter IPs before calling `HttpClient.send` completely block SSRF?  
**Answer:** No. Resolution at connection time may differ from the check; egress controls and proper destination-binding mechanisms are required.

**Q14.** Who should receive credentials in response to HTTP 401 and 407?  
**Answer:** 401 + WWW-Authenticate is for the origin; 407 + Proxy-Authenticate is for the proxy; do not swap them.

**Q15.** Why shouldn't the same cookie jar be used for multiple user sessions in a Java backend?  
**Answer:** Automatic cookies can be shared across requests from different users, causing session confusion and privilege leaks.

## 28. Operational Checklist

When designing a Java HTTP client with authentication and redirect capability:
1. Use HTTPS with valid certificate/hostname verification for all destinations.
2. Identify the **origin and protection space** each token/cookie/password belongs to.
3. Choose `Redirect.NEVER` if strict cross-host/SSRF/credential scoping is required.
4. Resolve and validate **every Location** against the original allowlist.
5. Forbid HTTPS → HTTP downgrades with sensitive data.
6. Use a cookie jar matching the user/session; do not manually copy `Cookie` from the old request.
7. Separate proxy authentication from origin authentication; `Authenticator` returns credentials matching requestor/realm.
8. Do not copy `Authorization`/`X-Api-Key`/custom auth headers to a new destination.
9. If the target is allowed but on a different origin, supply credentials dedicated to that target.
10. Check POST/307/308 and replay/idempotency before resending a body.
11. Enforce deadlines/max hops/max response size to prevent redirect loops.
12. Use network egress rules to block out-of-scope internal/metadata addresses.
13. Test the auto-follow behavior of the actual runtime used, but **do not rely on luck** of a single implementation.
14. Log sanitized decisions/status/hosts without logging secrets.
15. Re-test after every upgrade to the JDK, HTTP library, proxy, cookie handler, or auth scheme.

**Conclusion:** Redirects can change hostname, port, scheme, and even the selected proxy. Each destination has its own trust boundary. Limits on credential sharing must be decided **at the application and infrastructure layers**; `HttpClient`'s auto-follow policy is a convenience utility, not a comprehensive protection mechanism for all custom credentials.

## 29. Official Documentation and References

- RFC 9110 — HTTP Semantics; redirection `15.4`, header handling and origin/protection space `11.5`, 401/407: https://www.rfc-editor.org/rfc/rfc9110
- Java SE 17 `HttpClient` — default Redirect.NEVER, send/sendAsync, proxy/authenticator integration: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Java SE 17 `HttpClient.Redirect` — NEVER, NORMAL, ALWAYS: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Redirect.html
- Java SE 17 `HttpClient.Builder` — followRedirects, proxy, authenticator, cookieHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html
- Java SE 17 `HttpResponse` — status, URI, headers, and previousResponse: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html
- Java SE 17 `ProxySelector` — proxy selection by URI: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ProxySelector.html
- Java SE 17 `Authenticator` — RequestorType PROXY/SERVER and credential challenges: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Authenticator.html
- Java SE 17 `CookieManager` and `CookiePolicy` — cookie store and acceptance policy: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/CookieManager.html
- RFC 6265 — HTTP State Management Mechanism; cookie scope and attributes: https://www.rfc-editor.org/rfc/rfc6265
- OWASP — SSRF Prevention Cheat Sheet, redirect/DNS/egress validation: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
