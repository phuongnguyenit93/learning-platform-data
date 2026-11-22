# HTTPS, Origin, Redirects, and Credentials

## 1. The Big Picture: Four Questions That Must Be Separated

A Java HTTP client does not just need to know "can it connect?". It also has to resolve:

1. **HTTPS:** Is the request traveling over a TLS connection that authenticates the right server, encrypts the traffic, and protects data integrity on that hop?
2. **Origin:** Do the current URL and the target URL share the same **(scheme, host, effective port)** triple?
3. **Redirects:** When receiving an HTTP 3xx and `Location`, should a new request be created; is the method/body preserved or changed?
4. **Credentials:** Are `Authorization`, cookies, API keys, or login data in the body allowed to go to the new origin?

**Core takeaway:** HTTPS does not automatically make a cross-origin redirect safe. A new URL with a valid certificate can still belong to a recipient that is **not authorized** to receive the original URL's token. Java `HttpClient.Redirect.NORMAL` blocks transitions from HTTPS to HTTP, but **is not a same-origin-only policy**.

The safe, verifiable approach for sensitive requests is **`Redirect.NEVER` → inspect each Location/URI → only create the next request after policy approval → re-attach the right credentials for the right target**. Validation does not stop at origin: you must also check scheme, URL, trust boundaries, request body, DNS/IP if the URL is untrusted, and hop limits.

~~~text
Java HTTP request
   |
   +--> URI + method + headers + body
   |        |
   |        +--> HTTPS/TLS authenticates server and protects transport
   |
   +--> HTTP response
            |
            +-- 200 / 204: process response
            +-- 401 / 403 / 407: evaluate authentication/authorization
            +-- 3xx + Location:
                     |
                     +--> resolve target URI
                     +--> compare origin, scheme, method, body, credentials
                     +--> check policy and hop limit
                                |
                                +-- deny --> stop
                                +-- allow --> create a NEW request to target
~~~

Even when requests are sent to the same server, authentication and authorization remain two separate jobs: **identifying who is calling** and **deciding whether that caller is allowed to use the resource**.

## 2. What Do HTTPS and TLS Protect?

HTTPS is HTTP carried over an appropriate TLS security channel. With HTTP/1.1 and HTTP/2, that is usually HTTP over TLS/TCP; HTTP/3 uses QUIC with integrated TLS. You should not equate all HTTPS with a single type of TCP socket.

In a standard HTTPS connection, the client verifies the certificate chain against its trust configuration and the server name against the certificate SAN/hostname, establishes TLS keys, and then exchanges HTTP over the encrypted channel. Typical properties:

| Property | What HTTPS/TLS protects | What HTTPS does **not** guarantee |
|---|---|---|
| **Confidentiality** | Hides HTTP header/body contents from eavesdroppers on the TLS hop | Does not hide contents from the server itself, TLS proxies, logs, or storage |
| **Integrity** | Detects unauthorized tampering on the TLS channel | Does not validate whether business logic/JSON is correct or user permissions are valid |
| **Server authentication** | Verifies DNS hostname identity via a trusted certificate | Does not prove the user is logged in, or whether the server is entitled to receive another token |
| **MITM protection on the TLS channel** | With proper certificate/hostname checks, makes traffic injection difficult | Becomes ineffective if a wrong CA is trusted or TLS verification is intentionally bypassed |
| **Protecting credentials in transit** | `Authorization` and `Cookie` are encrypted inside the HTTPS request | Does not prevent leaks via URLs, improper redirects, client code, logs, or decrypted proxies |

The certificate of `https://b.example.test` only proves that the client is talking to **b.example.test** according to the TLS trust configuration; it does not prove that b.example.test is authorized to receive an `Authorization` header originally intended for **a.example.test**.

### 2.1. TLS Termination and "End-to-End Encryption"

A reverse proxy or load balancer can terminate TLS and then forward the request to another upstream. HTTPS protects **client → TLS terminator**; the proxy → backend hop needs separate protection (HTTPS/mTLS/private transport and operational policies). There is no default guarantee that data in a database, on disk, or in logs is encrypted or properly redacted.

### 2.2. Do Not Fix SSL Errors by Disabling Checks

If Java encounters an `SSLHandshakeException` or hostname mismatch, inspect the CA/truststore, certificate SAN, hostname, system clock, proxy, and TLS policy. **Do not** use a trust-all certificate manager, disable hostname verification, or automatically fall back to HTTP in production. Doing so destroys the HTTPS guarantees the system relies on.

## 3. Origin = Scheme + Host + Effective Port

According to RFC 6454, the origin of an HTTP(S) URI is typically the triple:

~~~text
origin = (scheme, host, effective port)

https://api.example.test:8443/v1/orders?page=1#section
          \______host____/ \port/
scheme = https
port   = 8443
origin = (https, api.example.test, 8443)
~~~

`https` defaults to port **443**; `http` defaults to **80**. If a URI omits the port, the effective port for the scheme must be used. **Path/query/fragment are not part of the origin triple**. Scheme/host are normalized according to URL rules; comparing raw URL strings is insufficient.

| URL A | URL B | Same-origin? | Explanation |
|---|---|---|---|
| `https://api.example.test/a` | `https://api.example.test/b?x=2` | **Yes** | Only path/query differ |
| `https://api.example.test` | `https://api.example.test:443/v2` | **Yes** | HTTPS effective port is 443 |
| `http://api.example.test` | `http://api.example.test:80/a` | **Yes** | HTTP effective port is 80 |
| `https://api.example.test` | `http://api.example.test` | **No** | Different **scheme** |
| `https://api.example.test` | `https://api.example.test:8443` | **No** | Different **port** |
| `https://api.example.test` | `https://auth.example.test` | **No** | Different **host** |
| `https://example.test` | `https://EXAMPLE.TEST/path` | **Yes**, after normalization | Host is case-insensitive |
| `https://example.test` | `https://sub.example.test` | **No** | A separate subdomain is a different host |

**Same IP address does not mean same origin.** Two different hostnames can resolve to the same IP (CDN, virtual hosts). The same hostname can change IP via DNS while remaining the same origin. Anti-SSRF techniques must evaluate DNS/network destination **alongside** origin, not use them interchangeably.

### 3.1. Origin, Site, and Cookie Scope Are Three Different Things

- **Same-origin** is based on scheme, host, and port.
- **Same-site** in the cookie/SameSite context is typically based on scheme and registrable domain; two subdomains can be same-site while having different origins.
- **Cookie scope** is determined by Domain, Path, Secure, SameSite, and user agent policy; a cookie can be sent to another origin if permitted by cookie policy.

Therefore, saying "cookies only stay within same-origin" is **false**. Nor can you infer that "same-site means two subdomains share the same right to receive a bearer token".

### 3.2. Origin Header and CORS

The `Origin` header describes the origin that initiated the request according to browser/protocol rules, which may differ from the target URL's origin. This header may **be absent** in many requests or have special values depending on context. For example:

~~~http
Origin: https://app.example.test
~~~

In a request to `https://api.example.test`, this is cross-origin. CORS governs whether **JavaScript running in a browser** is allowed to read certain cross-origin responses; it is not authentication, it is not a backend firewall, and **it does not stop Java `HttpClient` from calling another host**. The server must still authenticate and authorize every request; never trust a self-declared Origin header as proof of identity.

`Host`, HTTP/2 `:authority`, TLS SNI, and `Origin` serve different roles. Changing the redirect URI may require the client to set the proper authority and TLS server name for the new endpoint; you should not blindly copy headers that depend on the old origin.

## 4. How Do 3xx Redirects Work?

A server can return:

~~~http
HTTP/1.1 302 Found
Location: /v2/items
Content-Length: 0
~~~

The client **may** send a follow-up request to the URL in `Location` if policy allows. A redirect is an **HTTP response with a navigation instruction**, not a sign that the server has already accepted credentials at the new endpoint.

`Location` can be **relative** or **absolute**. Given the request `https://api.example.test/v1/items`:

~~~text
Location: /v2/items
  -> https://api.example.test/v2/items
     same origin, different path

Location: ../status
  -> https://api.example.test/status
     same origin

Location: https://files.example.test/object
  -> https://files.example.test/object
     different host/origin

Location: http://api.example.test/v2
  -> http://api.example.test/v2
     different scheme/origin, HTTPS downgraded
~~~

Java `URI.resolve(...)` resolves a relative URI against the base URI; it **does not evaluate the security of the target URL**. For untrusted input, in addition to `URI.resolve` you must check scheme, host, userinfo, port, URL normalization, DNS/IP, allowlists, and loop limits.

### 4.1. Not Every 3xx Response Should Be Followed

| Status | Meaning | Method/body when the client follows |
|---|---|---|
| **301 Moved Permanently** | Resource address moved permanently | For POST, client **may** change to GET |
| **302 Found** | Resource address moved temporarily | For POST, client **may** change to GET |
| **303 See Other** | View result/resource at another URL | Typically uses GET (or HEAD as appropriate) to retrieve target |
| **307 Temporary Redirect** | Temporary redirect that **preserves method** | Must not change method; body may need to be resent |
| **308 Permanent Redirect** | Permanent redirect that **preserves method** | Must not change method; body may need to be resent |
| **304 Not Modified** | Conditional cache | **Not** a redirect to a new URI |

These semantics are based on RFC 9110. The historical behavior of 301/302 for POST differs from 307/308. The Java 17 `HttpClient.Redirect` Javadoc states that when auto-redirecting 301/302, **POST is changed to GET** in the Java implementation.

**Do not automatically replay a body containing passwords or sensitive information over 307/308** to another origin just because a Location header is present. Because the method/body is preserved, a redirect can forward form passwords or secret data to an untrusted destination. RFC 9700 (OAuth 2.0 Security BCP) specifically warns about the 307 redirect trap in login flows, and notes 303 as an option where appropriate.

### 4.2. Redirect, Retry, and Caching Are Not the Same

- **Redirect:** the server specifies a new target URL via status/Location; the client must decide whether to follow.
- **Retry:** the client resends the request due to errors/timeouts/rate limits, not necessarily with a Location.
- **304:** responds to a cache-related conditional request, not asking to send a request to a new Location URL.

For non-idempotent POSTs, both method-preserving redirects and retries can cause duplicate side effects if the endpoint already processed part of the request. Designs need idempotency keys or transaction semantics when necessary.

## 5. Credentials Must Not Follow Redirects Blindly

An HTTP request can contain:

| Location | Example | Risk |
|---|---|---|
| `Authorization` | `Bearer access-token`, Basic auth | Token/password sent to another host |
| `Cookie` | `session=opaque-session-id` | Cookie sent out of intended scope or copied via manual policy |
| Custom header | `X-API-Key` | Auto-copying custom headers can leak the key |
| POST body | Form password or JSON token | 307/308 may resend the exact body |
| Query/URL | `?access_token=...` | Easily ends up in logs, browser history, analytics, Referer |
| `Proxy-Authorization` | Proxy credentials | Not intended for origin servers |

A **bearer token** typically grants capabilities to whoever possesses it; therefore, do not forward it across redirects without checking target, audience, scope, and policy. `Authorization: Basic ...` only uses Base64 for user:password: **Base64 is not security encryption**, so HTTPS must be used and logging avoided.

A sensible policy:

1. **Same-origin redirect:** you may consider keeping credentials appropriate for the resource, though same origin **does not automatically prove** same scope/audience.
2. **Cross-origin redirect:** by default **do not forward** Authorization, Cookie, API keys, or sensitive body from the old origin; if following is required, attach **separate** credentials for an allowlisted target.
3. **HTTPS → HTTP:** reject for sensitive data. Do not fall back to HTTP.
4. **Every hop:** re-verify on each hop, not just the first one.
5. **Logging:** log only status, sanitized URL, redirect count, and policy reason; **never log tokens/cookies/passwords**.

Java library behavior for sensitive headers can depend on how the request is built, the implementation, and cookie/authenticator configuration; do not rely on a blanket assumption that **every custom credential is automatically stripped properly**.

## 6. Java 17 HttpClient.Redirect: NEVER, NORMAL, ALWAYS

`java.net.http.HttpClient` lets you choose a policy:

| Policy | Java 17 Javadoc | Security note |
|---|---|---|
| `HttpClient.Redirect.NEVER` | Never auto-redirect; return the 3xx response to caller | **Easy to control** credential source/target and method |
| `HttpClient.Redirect.NORMAL` | Auto-redirect **except** HTTPS URL → HTTP URL | Prevents direct downgrade, **does not guarantee same-origin** |
| `HttpClient.Redirect.ALWAYS` | Auto-redirect including HTTPS → HTTP per policy | Unsuitable for requests with credentials without extra safeguards |

**The default for `HttpClient.newHttpClient()` and the builder when `followRedirects` is not configured is `Redirect.NEVER`.** Java does not default to browser-like behavior that automatically follows every 3xx.

~~~java
HttpClient secureClient = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .connectTimeout(Duration.ofSeconds(5))
        .build();
~~~

This is a **configuration snippet**; it requires importing `HttpClient` and `Duration`. `Redirect.NORMAL` can still follow from `https://a.example.test` to `https://b.example.test`, both using HTTPS yet **different origins**. `Redirect.ALWAYS` does not guarantee confidentiality when dropping to HTTP. For sensitive requests, **NEVER + manual validation** is more transparent.

### 6.1. HTTPS Downgrade, HTTP→HTTPS Redirects, and HSTS

An initial HTTP request **is not retroactively protected** when the server returns a 301/302 redirecting to HTTPS. On the Internet, an attacker can read/modify the first HTTP hop. If HTTPS is required, set the initial URL to `https://` right in the application.

In a **browser**, stored/preloaded HSTS can upgrade a request before any real HTTP traffic is sent. Java `HttpClient` does not use a browser's HSTS cache by default. Likewise, browser `Secure` cookies and SameSite policies do not replace Java's TLS trust configuration.

## 7. Authentication Differs from Authorization

### 7.1. Common HTTP Status Codes

| Status | General meaning | Proper response |
|---|---|---|
| **200 OK** | Request succeeded per server semantics | Parse body and validate business logic |
| **301/302/303/307/308** | May navigate to another URL | Check Location, method/body, and credential policy |
| **401 Unauthorized** | Missing/invalid authentication for resource; often includes `WWW-Authenticate` | Select credentials matching server/realm/scope |
| **403 Forbidden** | Server understood request but refuses access | Check permissions/scope; do not retry passwords indefinitely |
| **407 Proxy Authentication Required** | Proxy requires authentication | Use proxy auth; do not copy to origin server |
| **404 Not Found** | Resource missing or server hides its existence | Do not assume it is definitely a TLS/auth/redirect issue |
| **429 Too Many Requests** | Rate limited | Back off according to policy; do not treat as redirect |

**TLS server authentication** identifies the server via certificate; **HTTP authentication** identifies the user/client; **authorization** decides which operations are permitted. All three concepts can appear together in a single request, but they do not replace one another.

### 7.2. HttpClient Authenticator and CookieHandler

Java 17 `HttpClient.Builder.authenticator(...)` configures a `java.net.Authenticator` to handle appropriate authentication challenges, such as HTTP `401` or proxy `407`. It is not a mechanism to automatically grant access across all cross-origin redirects.

`HttpClient.Builder.cookieHandler(...)` can configure a `CookieManager` or `CookieHandler` to automatically manage cookies according to the handler's rules. Java `HttpClient` **is not a browser**: do not assume Chrome's `SameSite`, third-party restrictions, CORS preflight, or HSTS rules all apply.

~~~java
// Snippet: use a cookie jar when the application truly needs session cookies.
CookieManager cookies = new CookieManager();
HttpClient client = HttpClient.newBuilder()
        .cookieHandler(cookies)
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
~~~

`CookieManager` is `java.net.CookieManager`. For service-to-service APIs using bearer tokens, the design should avoid accidentally copying `Cookie` or `Authorization` from a previous request to a new target URL. A server must still authenticate the user/token on the receiving side; **CORS is not an authentication layer**.

## 8. Cookies and Same-Origin: Beware of Different Scopes

Browsers send cookies based on multiple attributes:

| Cookie attribute | Role |
|---|---|
| `Domain` | Host-only if omitted; Domain can include matching subdomains |
| `Path` | Restricts URL paths that receive the cookie; **not a strong security boundary** |
| `Secure` | Cookie is only sent in secure transport contexts per user agent rules |
| `HttpOnly` | Prevents ordinary JavaScript from reading the cookie via `document.cookie`, though the browser still sends it when appropriate |
| `SameSite=Strict` | Strictly restricts cross-site requests |
| `SameSite=Lax` | Allows certain top-level navigations based on criteria; does not block all CSRF |
| `SameSite=None; Secure` | Allows certain cross-site contexts depending on browser configuration and third-party policy |

**Cookies are not partitioned by exact scheme-host-port like the same-origin policy.** Subdomains sharing a registrable domain can have different origins yet still receive a cookie with a matching `Domain`. Conversely, a cookie `Path` can restrict requests even within a single origin. Thus, you cannot assume "same origin means send every cookie" or "different origin means no cookie is ever sent".

For browsers, CORS restricts JavaScript's access to responses; the browser may still automatically send certain cookies per policy on cross-site requests. On a Java backend, you must examine how the specific `CookieHandler` manages cookies and protects tokens.

## 9. Rules for URLs/Locations Controlled by Untrusted Parties

`URI.resolve` is a parser/resolver, **not a URL security validator**. For redirects that an attacker might control:

- **Allowlist schemes:** `https` only in production for sensitive data; explicit exceptions for local testing.
- **Allowlist host/port and origin:** compare canonical host, effective port, and trust purpose; do not use `endsWith("example.test")` without label boundaries.
- **Reject userinfo in URLs** such as `https://user:password@host`.
- **Keep secrets out of query strings**; URLs can appear in logs/history/Referrer/analytics.
- **Limit redirect count**, URL loops, and total timeout.
- **Control method/body replay:** especially `307/308` and POSTs with side effects.
- **Evaluate destination DNS and IP** if the URL is untrusted: block loopback, link-local, metadata IPs, unauthorized internal networks, DNS rebinding, and IP changes after validation (TOCTOU), using appropriate network-layer controls.
- **Do not copy custom headers by inertia**; construct a new request from permitted data.
- **Enforce TLS validation** on every HTTPS hop, not just the first hop.

This is an **SSRF** issue if a Java server accepts arbitrary URLs and fetches them across redirects. Same-origin comparison alone is not enough to prevent SSRF; however, if the policy is **same-origin only with a trusted initial URL**, it serves as an appropriate risk-reduction layer for that API.

## 10. Safer Manual Redirect-Following Workflow

For an HTTP client that manages credentials itself:

~~~text
initial request (valid URL/scheme and token scope)
    |
    v
HttpClient.Redirect.NEVER -> response
    |
    +-- status != supported redirect --> handle final status/body
    |
    +-- status is a supported redirect:
            |
            +-- Location present, parse URI
            +-- resolve target against current URI
            +-- validate scheme, host, effectivePort, allowlist
            +-- check whether target changes origin
            +-- check method and replayable body
            +-- filter/re-attach properly scoped credentials
            +-- check hop count/deadline; send new request if allowed
~~~

RFC 9110 advises caution when automatically following unsafe methods and recommends considering stripping sensitive headers such as `Authorization` and `Cookie` when a request is redirected. Each hop can change the URL, method, and headers, so do not preserve every field verbatim. Certain headers like `Host`/`Origin`/`Referer`/cache validators have their own constraints on the new request.

With sensitive URLs and tokens, **deny by default** prevents sending secrets before discovering an untrusted target. Once a redirect is approved, only re-send credentials when identity/scope rules and policy permit.

## 11. Complete Java 17+ Example Running on Loopback

This example creates a local HTTP server using the JDK `jdk.httpserver` module and Java `HttpClient`; no Internet access is required. It demonstrates **redirect logic**, **not real TLS testing**, because TLS requires a valid certificate. The token `Bearer LOCAL_DEMO` is completely dummy and only sent over loopback HTTP in this example; **never use real tokens over HTTP**.

Scenario:

1. `/start` returns `302 Location: /final`. The client uses `Redirect.NEVER` and resolves the URL itself; because it is **same-origin**, the program explicitly re-sends the dummy token to `/final`.
2. `/external` returns `302 Location: https://other.example.invalid/landing`. The client detects a different origin and **makes no request to that host**.
3. Uses `sameOrigin(...)` to compare scheme/host/effective port; demonstrates that HTTP and HTTPS on the same hostname still have different origins.

The `sameOrigin` method in this example **only illustrates controlled HTTP(S) URIs**; it lacks full canonicalization/IDN, DNS/IP checking, or trust policy to serve as a production redirect/SSRF filter. It also rejects userinfo as an extra safety policy; userinfo is not part of the origin triple.

Create **`HttpOriginRedirectDemo.java`**:

~~~java
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
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;

public class HttpOriginRedirectDemo {
    private static int effectivePort(URI uri) {
        if (uri.getPort() != -1) return uri.getPort();
        if ("https".equalsIgnoreCase(uri.getScheme())) return 443;
        if ("http".equalsIgnoreCase(uri.getScheme())) return 80;
        return -1;
    }

    private static boolean sameOrigin(URI a, URI b) {
        return a.getScheme() != null && b.getScheme() != null
                && a.getHost() != null && b.getHost() != null
                && a.getScheme().equalsIgnoreCase(b.getScheme())
                && a.getHost().equalsIgnoreCase(b.getHost())
                && effectivePort(a) == effectivePort(b)
                && a.getUserInfo() == null && b.getUserInfo() == null;
    }

    private static void redirect(HttpExchange exchange, String location)
            throws IOException {
        exchange.getResponseHeaders().set("Location", location);
        exchange.sendResponseHeaders(302, -1);
        exchange.close();
    }

    private static void respond(HttpExchange exchange, String text)
            throws IOException {
        byte[] body = text.getBytes(StandardCharsets.US_ASCII);
        exchange.sendResponseHeaders(200, body.length);
        try (var output = exchange.getResponseBody()) {
            output.write(body);
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        AtomicBoolean receivedCredential = new AtomicBoolean(false);
        server.createContext("/start",
                ex -> redirect(ex, "/final"));
        server.createContext("/final", ex -> {
            receivedCredential.set("Bearer LOCAL_DEMO".equals(
                    ex.getRequestHeaders().getFirst("Authorization")));
            respond(ex, "OK");
        });
        server.createContext("/external",
                ex -> redirect(ex, "https://other.example.invalid/landing"));
        server.start();
        try {
            URI base = new URI("http", null, loopback.getHostAddress(),
                    server.getAddress().getPort(), "/", null, null);
            HttpClient client = HttpClient.newBuilder()
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            HttpResponse<String> first = client.send(
                    HttpRequest.newBuilder(base.resolve("start"))
                            .timeout(Duration.ofSeconds(3))
                            .header("Authorization", "Bearer LOCAL_DEMO")
                            .GET().build(),
                    HttpResponse.BodyHandlers.ofString());
            URI next = first.uri().resolve(
                    first.headers().firstValue("Location").orElseThrow());
            boolean same = sameOrigin(first.uri(), next);
            if (first.statusCode() != 302 || !same) {
                throw new IOException("Unsafe or unexpected redirect");
            }
            HttpResponse<String> finalResponse = client.send(
                    HttpRequest.newBuilder(next)
                            .timeout(Duration.ofSeconds(3))
                            .header("Authorization", "Bearer LOCAL_DEMO")
                            .GET().build(),
                    HttpResponse.BodyHandlers.ofString());

            HttpResponse<String> external = client.send(
                    HttpRequest.newBuilder(base.resolve("external"))
                            .timeout(Duration.ofSeconds(3))
                            .header("Authorization", "Bearer LOCAL_DEMO")
                            .GET().build(),
                    HttpResponse.BodyHandlers.ofString());
            URI other = external.uri().resolve(
                    external.headers().firstValue("Location").orElseThrow());
            boolean blocked = !sameOrigin(external.uri(), other);

            System.out.println("redirectPolicy=" + client.followRedirects());
            System.out.println("initialStatus=" + first.statusCode());
            System.out.println("sameOrigin=" + same);
            System.out.println("finalStatus=" + finalResponse.statusCode());
            System.out.println("sameOriginAuth=" + receivedCredential.get());
            System.out.println("crossOriginBlocked=" + blocked);
            System.out.println("httpsDiffersFromHttp=" + !sameOrigin(
                    URI.create("http://example.test/"),
                    URI.create("https://example.test/")));
        } finally {
            server.stop(0);
        }
    }
}
~~~

Compile and run with JDK 17+ (`jdk.httpserver` module):

~~~bash
javac --release 17 --add-modules jdk.httpserver HttpOriginRedirectDemo.java
java --add-modules jdk.httpserver HttpOriginRedirectDemo
~~~

**Exact stdout verified on OpenJDK 24 with `--release 17`:**

~~~text
redirectPolicy=NEVER
initialStatus=302
sameOrigin=true
finalStatus=200
sameOriginAuth=true
crossOriginBlocked=true
httpsDiffersFromHttp=true
~~~

Result breakdown:

- `redirectPolicy=NEVER`: Java does not auto-follow 3xx; the program itself handles Location.
- `initialStatus=302`: `/start` request returned a redirect, not the final result yet.
- `sameOrigin=true`: target `/final` shares the same scheme/host/effective port.
- `finalStatus=200`: after verification, the client sent a new request and the server returned success.
- `sameOriginAuth=true`: the server received the header containing the **dummy token** at the same-origin endpoint.
- `crossOriginBlocked=true`: URL `other.example.invalid` was detected as a different origin so no `client.send` was made to the external host; **no Internet access required**.
- `httpsDiffersFromHttp=true`: a different scheme is a different origin.

The demo only checks same-origin before following; in production you must also restrict the target scheme to HTTPS, allowlist hosts, validate credential path/scope, check DNS/IP, guard against redirect loops, and control method/body replay. Do not use the demo's `sameOrigin` as a complete SSRF firewall.

## 12. Cookie Flows, OAuth Redirects, and Token Audience

Cross-origin redirects are sometimes **intentional by design**:

~~~text
Browser -> https://app.example.test/profile
     <- redirect to https://login.example.test/authorize
Browser -> login.example.test
     <- redirect back to registered callback at app.example.test
App     -> verify state + PKCE/flow then process authorization code
~~~

In OAuth/OIDC flows, the redirect URI must be registered/validated strictly per policy, `state` binds the request and mitigates CSRF, PKCE protects the authorization code in applicable flows, and issuer/audience/scope and token validation must still follow the standard. **Do not send the app's access token to every `Location` URL just because it is a redirect step in login.**

A `SameSite` cookie can affect whether the browser sends a session cookie during a cross-site flow, but that does not turn CORS into authentication. A Java backend does not automatically enforce browser policies unless explicitly implemented/configured.

**Origin** is a URL concept; **audience** is the valid intended recipient of a token; **scope/permission** is what actions are allowed. All three must be evaluated independently.

## 13. Common Debugging Pitfalls

| Symptom / false claim | What to understand | How to handle |
|---|---|---|
| "HTTPS has a valid certificate, so the redirect is safe" | The certificate authenticates the new host, not its right to receive old credentials | Allowlist targets and match token scope |
| "NORMAL only follows same-origin" | NORMAL only blocks HTTPS→HTTP downgrades | Use NEVER/manual for sensitive requests |
| "Same domain = same origin" | Subdomains/ports/schemes can differ | Compare scheme-host-effective port |
| "Same IP = same origin" | Origin uses the hostname from the URL | Separate DNS/IP checks from URL identity |
| "Cookies are only sent within one origin" | Cookie scope differs from origin; Domain can cover subdomains | Inspect Domain/Path/Secure/SameSite |
| "CORS protects the server from Java HttpClient" | CORS is a browser response-access policy | Server must check auth and permissions |
| "301/302 preserves every POST" | Clients may convert POST to GET | Follow RFC/client semantics |
| "307/308 drops the body on redirect" | Must preserve method; body may be replayed | Block replaying sensitive bodies |
| "304 is a redirect to Location" | 304 is for conditional caching | Do not treat it like 302 |
| "Removing Authorization alone is enough" | Secrets can also live in Cookie/custom headers/body/query | Build a new request from an allowlist |
| "401 is the same as 403" | 401 is usually authentication, 403 is authorization | Handle separately |
| "Basic auth is encrypted because of Base64" | Base64 is encoding, not encryption | Use only over TLS; avoid logging |
| "HTTP→HTTPS 301 makes the first HTTP hop safe" | The initial HTTP hop can still be observed/modified | Start directly with HTTPS |
| "URI.resolve blocks bad redirects automatically" | Resolve only constructs a new URI | Validate each hop and prevent SSRF |
| "Tokens in URL queries are safe because of HTTPS" | URLs can appear in logs/histories/referrers | Keep secrets out of URLs |

## 14. Design and Code Review Checklist

**Before the request:** Is the initial URL HTTPS when security is needed? Are certificate/hostname validations enabled? Does the token have the right audience/scope? Are timeout, proxy, CookieHandler, and redirect policy explicitly configured? Is auto-redirect truly needed?

**On 3xx:** Which status code? Is `Location` relative or absolute? Does the target share the same scheme/host/effective port? Is there an HTTPS downgrade? Are host/port/IP on the allowlist? Is the method/body changed or replayed? Are there Authorization, Cookie, custom API keys, query tokens, or POST passwords? Are there a hop limit and an overall deadline?

**After the response:** What are the final status and actual URL processed (e.g., `HttpResponse.uri()`)? Are there any unhandled 401/403/407 responses? Are cookies properly scoped? Does CORS involve a browser caller? Did logs accidentally record tokens/passwords/sensitive query URLs?

## 15. Self-Check

**1. Do `https://example.test/a` and `https://example.test/b` have the same origin?** Yes, only the path differs.

**2. What about `https://example.test` and `https://example.test:8443`?** No, because effective port 443 differs from 8443.

**3. `http://example.test` and `https://example.test`?** No, different schemes.

**4. Does HTTPS authenticate the end user by default?** No. TLS server authentication is different from HTTP authentication.

**5. Does Java 17 HttpClient follow redirects automatically by default?** No, the default is `Redirect.NEVER`.

**6. Does `Redirect.NORMAL` block redirects to a different HTTPS host?** No. It blocks HTTPS→HTTP, but has no same-origin restriction.

**7. May a POST 307 be changed to GET?** No. A 307 redirect preserves the method, so be careful with the body.

**8. Can a POST 302 in Java 17 become a GET when auto-following?** Yes, per the Java 17 implementation note.

**9. Is `Location: /v2` an absolute URL?** No; it must be resolved against the base URI.

**10. How does 401 differ from 403?** 401 usually requires valid authentication; 403 means access permission is denied.

**11. Do cookies follow the same origin rules as CORS?** No; cookies follow Domain/Path/SameSite rules, which differ.

**12. Is a Java backend blocked by browser CORS when using HttpClient?** No; it decides on its own which URLs to call and which credentials to send.

**13. Should you copy an old bearer token when redirecting to another host?** Not by default; only attach credentials appropriate for the target after policy/authorization checks.

**14. What happens if a 307 redirects a body containing a password to another host?** There is a risk of leaking the password if followed; you must block it or strictly verify target/method/body.

**15. Does the demo connect to `other.example.invalid`?** No. It only resolves Location and refuses to follow cross-origin.

## 16. References

- [Java SE 17 – HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): client builder, SSL context, Authenticator/CookieHandler, default redirect behavior.
- [Java SE 17 – HttpClient.Redirect](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Redirect.html): `NEVER`, `NORMAL`, `ALWAYS`, and notes on POST/301/302 methods.
- [Java SE 17 – HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): request builder, headers, method, timeout.
- [Java SE 17 – HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): URI, status, headers, and body.
- [Java SE 17 – URI](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html): URI parser, scheme/host/port, `resolve`.
- [Java SE 17 – HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): loopback demo server.
- [RFC 6454 – The Web Origin Concept](https://www.rfc-editor.org/rfc/rfc6454): the scheme-host-port triple.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): redirects, Location, authentication, and HTTP status codes.
- [RFC 9700 – OAuth 2.0 Security BCP](https://www.rfc-editor.org/rfc/rfc9700): redirects with credential data.
- [MDN – Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Same-origin_policy): origin and browser policy.
- [MDN – Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): Domain/Path/Secure/HttpOnly/SameSite.

**Remember:** HTTPS protects the **TLS connection**, not the trustworthiness of every redirect. Origin is **scheme + host + effective port**, not just hostname or IP. HTTP 3xx can change the origin, method, or whether the body is resent. Credentials must only be used at the right destination and permission scope. In Java 17, `HttpClient.Redirect.NEVER` and per-`Location` validation help prevent blindly forwarding tokens; `Redirect.NORMAL` blocks HTTPS→HTTP downgrades but **is not a same-origin policy**.
