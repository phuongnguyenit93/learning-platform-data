# Distinguishing HTTP Authentication, Application Tokens, and TLS Certificate Authentication

## Lesson Objectives

A Java system calling APIs through a proxy and HTTPS may simultaneously encounter **HTTP Basic authentication**, **Bearer access tokens**, **session cookies**, **TLS server certificates**, and **TLS client certificates (mTLS)**. They are all related to security, yet they **do not prove the same identity**, **are not sent to the same party**, and **do not operate at the same stage**.

Core takeaway: **“HTTP authentication” is the mechanism framework at the HTTP layer; an application Bearer token can itself be the credential of an HTTP authentication scheme.** Therefore, HTTP authentication and tokens are not two mutually exclusive layers. Meanwhile, TLS certificate authentication is an operation of the **TLS handshake** (before HTTP application data is exchanged over the protected connection).

After this lesson, you will be able to:

- Distinguish **authentication** (identifying the peer/user/service), **authorization** (checking permissions), and **confidentiality/integrity** (secrecy/integrity in transit).
- Understand **401 + WWW-Authenticate + Authorization** for an *origin server* and **407 + Proxy-Authenticate + Proxy-Authorization** for a *forward proxy*.
- Distinguish **HTTP Basic** from **HTTP Bearer**; Basic uses Base64, **not encryption**; a bearer token allows the holder of the token to exercise permissions within its scope.
- Understand **access tokens**, **ID tokens**, **refresh tokens**, session cookies, opaque tokens, and JWT tokens; do not equate a three-part JWT with a verified token.
- Explain **TLS server certificate** validation (client verifies CA/truststore + name/SAN) and **mTLS** (server adds the step of requesting and verifying the client certificate).
- Understand **proxy CONNECT**, reverse proxy/TLS termination, and the limitations of forwarding client identity via headers.
- Properly configure Java 17+ APIs: `HttpClient`, `HttpRequest`, `com.sun.net.httpserver.BasicAuthenticator`, `SSLContext`, `KeyManagerFactory`, `TrustManagerFactory`, and `SSLSocket`.
- Run two standalone programs: **HTTP Basic/Bearer on loopback** and **TLS 1.3 mTLS with test certificates** verified with a JDK 17-compatible compiler.

**Scope:** HTTP and proxies in the Java networking module. The key/password/token examples are **mock values dedicated to 127.0.0.1** and must not be used to operate a real service. HTTPS/TLS, certificate validation, secret management, and authorization must be implemented properly when handling sensitive data.

## 1. Three Different Security Questions

| Question | Term | Examples |
|---|---|---|
| “Who are you, and how do you prove it?” | **Authentication — AuthN** | Password via Basic, session, Bearer token, client certificate |
| “Is that identity allowed to call this API?” | **Authorization — AuthZ** | Role, scope `orders:read`, ACL, per-resource policy |
| “Is data in transit being read/modified?” | **Confidentiality / integrity** | HTTPS/TLS protects application data in a channel |

**AuthN does not automatically grant AuthZ.** A client certificate trusted by an internal CA can confirm that the peer is a specific service, but that does not mean that service is allowed to call every endpoint. A valid access token may only allow reading, not deleting. Conversely, merely succeeding with TLS encryption to a server does **not** prove that an application token has been accepted by the server.

### Protocol Layers and Authentication Targets

~~~text
Java client
   │
   │ 1. May need PROXY authentication to be allowed to forward the connection
   ├── HTTP proxy authentication: 407 ↔ Proxy-Authorization
   │
   │ 2. Establish a TLS session to the actual HTTPS endpoint
   ├── TLS server certificate validation (client verifies server)
   ├── [depending on configuration] mTLS client certificate validation
   │
   │ 3. Exchange HTTP requests inside the TLS tunnel/session
   └── Authorization: Basic ... / Bearer ...
             or Cookie: session=...
                    │
                    ▼
              Origin/API server
              AuthN → AuthZ → business logic processing
~~~

The steps in the diagram are conceptual. When a **reverse proxy terminates TLS**, the TLS endpoint may be the proxy rather than the backend. When a **forward HTTP proxy performs CONNECT**, the TLS part to the origin normally runs **inside the tunnel**; the proxy only forwards TLS bytes and is not a regular HTTPS decrypting endpoint.

**Differences in scope:**

- The TLS handshake authenticates the peer at the **TLS connection level**.
- `Authorization` or `Cookie` is tied to an **HTTP request/application session**.
- Proxy credentials are presented to the **selected proxy**, not to the origin.
- HTTP/2 can use multiple requests/streams over a single TLS connection; a TLS certificate does not turn every request into a single application permission.

## 2. HTTP Authentication Framework: Challenges and Credentials

HTTP defines a **challenge–response** framework between a client and a server requiring authentication. An origin server protecting a resource may return:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="private"
Cache-Control: no-store
Content-Length: 0
~~~

A client with matching credentials can retry:

~~~http
GET /private HTTP/1.1
Host: api.example.org
Authorization: Basic ZGVtbzpwb3Nz
~~~

The Base64 string here is only an **illustrative value of mock credentials**, not a real password. Another challenge might use `Bearer` or another authentication scheme.

**`401 Unauthorized` in practice relates to missing or unaccepted authentication credentials**, even though the word “Unauthorized” in the name can be misleading. According to RFC 9110, an origin server sending `401` **must** include `WWW-Authenticate` with at least one valid challenge for the resource.

After the client has been authenticated but has **insufficient permissions**, the origin server usually returns `403 Forbidden`. An application may intentionally use `404 Not Found` to avoid disclosing the existence of a resource in some cases.

### Is HTTP Auth Actually “Logging In”?

The HTTP authentication framework helps the server request authentication via schemes and headers, but **does not force every application to use Basic**. One can use:
- `Basic` with username/password.
- `Bearer` with an access token issued by an application/OAuth system.
- Other schemes supported by the HTTP client/server according to configuration.
- Cookies/sessions or application authentication mechanisms **outside** the traditional challenge header framework.

A web application that displays a login form and then creates a session cookie may not use the `Authorization` header for every request. That does not make the cookie “become a TLS certificate.” It is an **application session maintenance** mechanism.

### Header Names Are Case-Insensitive

`Authorization` and `authorization` refer to the same HTTP field name. However, the **authentication scheme** name, credential syntax, realm, token, and usage policy belong to each individual scheme. Do not naively parse complex challenges by simple comma splitting: many schemes have parameters or multiple challenges in a single field.

## 3. HTTP Basic: Username/Password Credentials, Base64 Is Not Encryption

RFC 7617 defines HTTP Basic. The client sends a value roughly of the form:

~~~http
Authorization: Basic ZGVtby11c2VyOmRlbW8tcGFzcw==
~~~

For the example `demo-user:demo-pass`, the part after `Basic` is the Base64 encoding of the string `username:password`. **Base64 is a representational encoding to convert bytes into ASCII characters, not encryption.** Anyone intercepting the header can decode the credentials.

**Why does Basic need TLS?** If Basic is sent over plaintext HTTP on a real network, an eavesdropper can capture the password; even over HTTPS, passwords can still be leaked via logs, decrypting reverse proxies, client memory, dumps, or mishandled code. Basic provides no replay protection for the credential per request once the header is stolen.

Rules:
1. Only use Basic over a protected connection (HTTPS/TLS with proper certificate/hostname verification), except for demos on **loopback**.
2. Do not put real credentials into repositories, command-line history, logs, or URLs.
3. Do not assume every request after login carries a `Basic` header; this depends on the client and the realm/credential reuse policy.
4. The server needs a proper password storage policy (password hash + salt and protection mechanisms), not storing literal passwords as in the illustrative program.
5. If permissions change, the server must still evaluate **authorization** for each resource; a valid password does not mean every resource is accessible.

In Java `HttpClient`, `HttpClient.Builder.authenticator(Authenticator)` can assist the authentication process for schemes supported by the implementation, including appropriate origin/proxy cases. **Do not** infer that every proxy scheme and every JDK version automatically supports it; policy/security properties may restrict Basic over HTTPS proxy tunneling. The complete Java example in section 11 uses **mock headers on loopback** so learners can clearly see the data boundary rather than relying on a credential prompting flow.

### Basic Auth Is Not a Session Token

A Basic header describes **username/password credentials** sent for an HTTP resource/protection space. Meanwhile, a session cookie usually contains a random **session identifier** (without the original password), and a Bearer token is an **issued credential** with its own lifecycle/permissions. Although all three can be used for application authentication, their lifecycles, exposure risks, and revocation methods differ.

## 4. Proxy Auth: 407 Is Not 401

A forward proxy may require the client to authenticate **before allowing forwarding**. When proxy credentials are missing:

~~~http
HTTP/1.1 407 Proxy Authentication Required
Proxy-Authenticate: Basic realm="office-proxy"
Content-Length: 0
~~~

The client can resend the appropriate request with:

~~~http
Proxy-Authorization: Basic ZGVtbzpwcm94eQ==
~~~

The `Basic` bytes here are illustrative only and are not a real password/host.

| Property | Origin authentication | Forward-proxy authentication |
|---|---|---|
| Party requesting authentication | Origin/API server | Forward proxy |
| Challenge response | `401 Unauthorized` | `407 Proxy Authentication Required` |
| Challenge header | `WWW-Authenticate` | `Proxy-Authenticate` |
| Credentials header | `Authorization` | `Proxy-Authorization` |
| Target | Authenticate to the target resource/API | Authenticate the right to **use the proxy** |
| Trust scope | Origin, realm, application | Specific proxy / managed proxy chain |
| Sufficient to access the API? | Depends on AuthZ | **No**; proxy acceptance does not mean origin acceptance |

**Note:** A proxy must not arbitrarily alter the origin request's `Authorization`. The `Proxy-Authorization` header is for the proxy, while `Authorization` is for the origin. Do not send the same bearer access token to both parties just to “try to get through.”

### HTTPS Through a Forward HTTP Proxy and CONNECT

A typical sequence when a client connects to `https://api.example.org` through a forward HTTP proxy:

~~~text
Java HttpClient             Forward proxy                  Origin
      │                          │                            │
      ├─ CONNECT api.example.org:443 ─────►│                  │
      │  (may receive 407 and perform proxy auth)             │
      │◄──────── 200 Connection Established ───┤              │
      │                          │                            │
      ├══════════ TLS ClientHello ════════►│═══════════════►│
      │◄═════════ TLS server certificate ═│════════════════┤
      │  client verifies origin's cert/hostname               │
      ├══════ HTTP Authorization (TLS encrypted) ══════════►│
      │◄══════ HTTP response inside TLS ════════════════════┤
~~~

This diagram depicts a **tunnel-forwarding forward proxy**, not a TLS-decrypting proxy. The proxy can know the `CONNECT` target, IP/port, and timing/traffic metadata; the origin HTTP headers/body after TLS is established are not visible to a regular tunneling proxy.

If a proxy implements **TLS interception** and the client trusts the CA that the proxy uses to issue certificates on behalf of the origin, the proxy **becomes the TLS endpoint** and can see plaintext HTTP. This is a **different** trust boundary requiring clear organizational policy; do not call it an end-to-end TLS tunnel to the origin.

**Common misconception:** a request to a proxy failing with `407` cannot be solved by adding `Authorization: Bearer <origin-token>`. You must use the proper proxy credentials/policy; if the origin subsequently returns `401`, that is a **separate** issue.

## 5. Bearer Access Token: An Application-Issued HTTP Credential

A Bearer token typically appears as:

~~~http
GET /orders HTTP/1.1
Host: api.example.org
Authorization: Bearer eyJ...<redacted>
~~~

`<redacted>` here is a notation for a **hidden value**, not a real token and not meant as a runnable example. RFC 6750 specifies the **Bearer authentication scheme** in HTTP. Bearer means **anyone who possesses a valid token** can present it to exercise the permissions it grants, unless additional bindings exist (proof-of-possession or other policies).

Importantly, **a Bearer token is itself a form of HTTP authentication** when transmitted via `Authorization: Bearer ...`. “Application token” describes **the type of credential and how it is issued/managed**, whereas “HTTP authentication” describes **how the credential enters the request/challenge**. These are two perspectives, not two mutually exclusive choices.

### Access Tokens Differ from Passwords and Session Cookies

| Credential | Who issues it? | How is it usually transmitted? | What needs to be checked |
|---|---|---|---|
| Username/password Basic | Account/identity system | `Authorization: Basic ...` | Credentials, realm, password policy |
| Bearer access token | Authorization server / application | `Authorization: Bearer ...` | Validity, issuer/audience, expiry, scope/policy |
| Opaque session ID | Application session service | `Cookie: session=...` or custom header | Active session, user, expiry, CSRF if browser cookie |
| Client TLS certificate | Managed PKI / CA | In the **TLS handshake**, not HTTP body | Chain, private key possession, policy mapping |
| Proxy credential | Proxy/identity system | `Proxy-Authorization` | Permission to use proxy, not origin API permission |

**A token is not necessarily a JWT.** A Bearer access token can be:
- **Opaque token:** a non-self-describing string; the resource server verifies it via a session store/introspection/authorization service.
- **JWT signed token (JWS):** a token with a signed claims structure that the resource server can verify for signature and claims according to policy; a JWT is usually **only signed, not encrypted**, so the payload can be decoded by anyone who sees the token.
- Another format defined by the authorization system, as long as it is compatible with the system's protection/verification mechanism.

**An ID token does not replace an access token:** in OpenID Connect, an ID token provides **user authentication information to the client**; it must not automatically be used in place of an access token to call an arbitrary API. A **refresh token** is used according to its issued mechanism to obtain new access tokens and usually has stricter protection; do not send a refresh token in `Authorization: Bearer` to a resource server unless the API explicitly specifies it.

### Bearer Challenge Examples

Missing token:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders"
Cache-Control: no-store
~~~

A submitted token that is expired/invalid may receive:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
Cache-Control: no-store
~~~

A valid token with insufficient scope may often receive:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders", error="insufficient_scope", scope="orders:write"
Cache-Control: no-store
~~~

These are **syntax examples**, not a guarantee that every API returns these exact error descriptions. Statuses and challenges must follow the API contract, RFC 9110, and RFC 6750 requirements where applicable.

**Do not use query parameters to carry access tokens** in new systems: URLs can be saved in browser history, server/proxy logs, and analytics. Choose HTTPS, properly scoped `Authorization`, log redaction, short token lifetimes, and rotation/revocation strategies. If using browser cookies, additionally evaluate `Secure`, `HttpOnly`, `SameSite`, CSRF, and session fixation.

## 6. Token Verification and Authorization at the Resource Server

**Observing a Bearer header does not prove the token is valid.** The resource server must validate the credential and construct a security principal according to its policy, and only then does **authorization** decide which actions are allowed.

### For JWT Signed Tokens

A common JWT format has three parts separated by dots:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

This is the **common JWS Compact representation**; not every token is a JWT, and it does not mean the payload is encrypted.

Important checks:
1. **Valid signature** with a trusted key and a configured **allowlisted** algorithm; never accept the `none` algorithm or disallowed variants just because the token declares them.
2. **Issuer (`iss`)** matches the expected authorization server; do not fetch keys from an arbitrary URL inside the token without a trust policy.
3. **Audience (`aud`)** includes this resource server/API — a token intended for API A must not be automatically accepted at API B.
4. **Expiry (`exp`)**, **not-before (`nbf`)**, system time, and clock skew policy; expired tokens must be rejected.
5. **Subject/client identity**, scopes/roles/permissions, and per-route/per-resource constraints.
6. **Key rotation**, token lifetime limits, and handling revocation or changed claims when needed.
7. **Do not confuse signature validity with permissions:** a properly signed token with only the `orders:read` scope must not be allowed to delete orders.

Use a **maintained JWT/OAuth library** in accordance with the protocol and organizational policy; do not write your own parser/cryptographic verification using simple string splitting and `Base64.getDecoder()`. A JWT can contain sensitive data in its readable payload; do not log raw tokens.

### For Opaque Tokens

The resource server can call a **token introspection endpoint** or check an internal token/session store, receiving the active status, subject, audience/scope, and expiry. You must protect the connection/resource server credentials during introspection, cache results for a reasonable duration, and handle revocation as required.

A **stolen Bearer token** can usually be reused by another party within its validity period. There are **token binding** mechanisms such as OAuth mTLS certificate-bound access tokens (RFC 8705) or DPoP to reduce the replayability of leaked tokens. However, **plain mTLS does not automatically bind every Bearer token to the client certificate**; that binding must be designed and verified at the authorization layer.

## 7. TLS Server Certificate: Client Authenticates the HTTPS Endpoint

When Java calls `https://api.example.org`, the TLS handshake occurs **before** delivering the HTTP application request over the channel. In the standard server authentication model:
1. The server presents its certificate chain (usually X.509) and proves possession of the matching private key during the handshake.
2. The client verifies the **certificate path/trust anchor**, validity period, and cryptographic policy.
3. The client checks whether the certificate represents the **expected hostname** (typically via a matching SAN DNS/IP).
4. If successful, the client derives traffic keys and begins exchanging data via encrypted/authenticated TLS records.
5. **At this point, the server does not yet necessarily know the identity of the application user/client.**

Examples:
- A valid certificate for `shop.example.org` does **not** automatically match when the client expects `api.example.org`.
- Connecting to an IP literal requires checking the identity against an IP in the SAN, not accepting an arbitrary DNS name.
- `SNI` helps the server select a certificate by hostname in virtual hosting deployments; SNI **does not replace** hostname validation.
- Proper certificate trust does not mean the server is a “business-trusted” service, or that the JSON response is guaranteed to be right.

**Java raw SSLSocket:** when creating a client `SSLSocket` manually instead of using the HTTPS-aware `HttpClient`, you must configure endpoint identification (for example, `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` for the expected name) along with a valid TrustManager. Standard HTTPS `HttpClient` enforces server identity verification per TLS/HTTPS policy; **do not disable validation** just because a test certificate is invalid.

Do not create an `X509TrustManager` that trusts all certificates or a `HostnameVerifier` that always returns true as a “fix.” When a certificate mismatches or is expired, fix the hostname/SAN, trust anchor, chain, or PKI configuration properly.

## 8. TLS Client Certificate and mTLS: Server Authenticates the Peer at Handshake

**Mutual TLS (mTLS)** requires **both sides** to validate certificates according to policy:
- The client verifies the **server certificate** just as in regular HTTPS.
- The server is configured to require a **client certificate**, verifying the certificate chain/key possession and necessary constraints.
- The TLS handshake fails if a required certificate is not provided or not trusted, **before any regular HTTP 401/403 exists at the application layer**.

JSSE example:
- The server uses `KeyManagerFactory` with its **private key + server certificate**.
- The server uses `TrustManagerFactory` with the CA/certificates of **trusted clients**.
- The server sets `SSLServerSocket.setNeedClientAuth(true)` to mandate a client certificate.
- The client uses `KeyManagerFactory` with its **private key + client certificate**.
- The client uses `TrustManagerFactory` with the CA/certificates of **trusted servers**.
- The client still verifies the server's **hostname/SAN** (the server certificate's CN/SAN serves a different role from the client certificate).
- After the handshake, the application retrieves the validated peer identity and **maps it to a principal/permissions** separately.

**mTLS is not “user login” by default.** In service-to-service architectures, a certificate may identify a workload/service/machine; the user-facing identity may still reside in an access token or session. A server may accept the certificate of `billing-service` while only allowing that service to call `/billing`, not `/admin`.

**Server-auth TLS differs from mTLS:** standard HTTPS may authenticate only the server; the client does not need to present a certificate. Seeing a successful HTTPS connection does not imply the server authenticated the client via a certificate.

**`setWantClientAuth(true)` differs from `setNeedClientAuth(true)`:** “want” only **requests it if the client has one**; “need” makes it mandatory, and the handshake fails if the client does not provide suitable authentication. For APIs requiring mTLS, use need and a proper trust policy.

## 9. Quick Comparison Table by Layer, Credential, and Timing

| Criterion | HTTP Basic to origin | Application Bearer token | TLS server certificate | mTLS client certificate | HTTP proxy authentication |
|---|---|---|---|---|---|
| Primary layer | HTTP request/challenge | HTTP request/application | TLS handshake | TLS handshake | HTTP proxy exchange |
| Who authenticates to whom? | Client/user to origin | Client/user/service to API | Server to client | Client to server (and server to client) | Client to forward proxy |
| Credential | Base64 username/password | Opaque/JWT access token... | Server certificate + proof of private key | Client certificate + private key | Proxy credential |
| Header/path | `Authorization: Basic` | `Authorization: Bearer` or other app mechanism | TLS handshake, **not** `Authorization` | TLS handshake, **not** `Authorization` | `Proxy-Authorization` |
| Typical challenge/error | `401 + WWW-Authenticate` | `401` / `403` depending on validity/scope | `SSLHandshakeException` on TLS validation failure | TLS handshake failure if cert missing/rejected | `407 + Proxy-Authenticate` |
| Scope | HTTP protection space / account | Audience/scope/expiry/resource | Hostname + trust anchor of TLS endpoint | Client principal/server trust policy | Proxy/realm, not origin |
| Automatic business permissions? | **No** | Only granted permissions accepted by policy | **No** | **No** | **No** |
| Must be protected on the network? | **Yes**, via HTTPS | **Yes**, via HTTPS; avoid token leakage | TLS itself creates the protected channel | TLS itself; private key must be protected | Needs protection policy for connection to proxy |

**Worth remembering:**
- Basic and Bearer are both **HTTP authentication schemes**, but their credentials differ fundamentally.
- A TLS server certificate verifies the **server endpoint**; mTLS adds verification of the **client certificate**.
- `401` is not `407`, and `Authorization` is not `Proxy-Authorization`.
- A server can require **both mTLS and a Bearer token**: the certificate authenticates the workload, and the token describes the user/scopes. The policy combining both identities must be clearly defined.
- A valid certificate, a valid token, and permission for an operation are **three different questions**.

## 10. Proxies, TLS Termination, and HTTP Sessions: Trust Boundaries

### Regular Forward Proxy

The client authenticates to the proxy using proxy credentials; afterward (with an HTTPS CONNECT tunnel) it performs TLS to the origin. Here, the proxy credential and the origin Bearer token have **different recipients**. A misconfiguration that sends the origin's Bearer token to the proxy or the wrong host can leak the token.

### Reverse Proxy Terminating TLS

~~~text
Client -- TLS --► Gateway / Reverse Proxy -- HTTP or new TLS --► Backend
             (TLS handshake and decryption at gateway)
~~~

If the gateway terminates TLS:
- The certificate the **client sees** is the gateway's certificate representing the external hostname.
- If mTLS is enabled at the outer edge, the gateway can verify the **client certificate** and see the peer principal.
- The backend **does not automatically see the same TLS client certificate handshake** just because the gateway forwards HTTP; a mechanism is needed to pass the verified identity and protect it under a trust contract.
- If the gateway → backend hop is plaintext HTTP, the outer TLS does **not** protect the internal hop. If that hop needs protection, establish **separate** TLS/mTLS for the downstream hop.
- Headers such as `X-Forwarded-Client-Cert`, `X-Client-Cert`, or `Forwarded` **do not prove identity by themselves**; public clients can forge these headers. The gateway must **strip/overwrite** untrusted headers; the backend only accepts identities authenticated by a trusted gateway and transmitted over a controlled channel.

### Session Cookie After Login

Another application flow:

~~~text
Browser -- TLS --> POST /login  → app verifies credentials
Browser <-- TLS -- Set-Cookie: session=...; Secure; HttpOnly; SameSite=...
Browser -- TLS --> Cookie: session=... → app checks session store
~~~

This is **application-layer session authentication**: the cookie typically holds a session ID, not a TLS certificate. Sessions have lifetimes, logout/revocation, and permission policies. Cookies are vulnerable to CSRF in a browser context if poorly designed; `SameSite` is a supporting mechanism but does not replace all CSRF protection. Do not treat TLS as a solution for XSS, session fixation, or business authorization.

### A Request May Pass Through Multiple Authentication Layers

Example of a sensible enterprise API design:

1. The proxy requires its own credentials to access the internal network.
2. The TLS client verifies the HTTPS server/gateway.
3. The gateway requires mTLS and verifies the calling service's certificate.
4. The HTTP request carries an access token audience-bounded to the API.
5. The gateway/backend validates the token, checks scopes, and enforces route/resource policies.
6. Only then is the business operation processed.

**Each layer solves a distinct problem.** Missing one step can create a vulnerability even if the others work. Conversely, not every system needs all five layers — requirements depend on the threat model and architecture.

## 11. Java 17 Example A: HTTP Basic and Bearer on Loopback

This is a **complete program** to observe HTTP authentication. Both server and client run on `127.0.0.1` with a dynamic port; there are no external network connections. It uses **mock values** `demo-user`, `demo-pass`, and `demo-only-token`. Plaintext HTTP is only acceptable for **internal testing on loopback**; never send real credentials this way over a network.

Purpose:
- `GET /basic` without credentials → `401` with `WWW-Authenticate: Basic ...`.
- With valid `Authorization: Basic ...` → `200`.
- `GET /bearer` without a token → `401` with `WWW-Authenticate: Bearer ...`.
- With valid `Authorization: Bearer ...` → `200`.

Complete file **`AuthLayersHttpDemo.java`**:

~~~java
import com.sun.net.httpserver.BasicAuthenticator;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;

public class AuthLayersHttpDemo {
    static void reply(HttpExchange exchange, int status, String message)
            throws IOException {
        byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
            "Content-Type", "text/plain; charset=utf-8");
        exchange.getResponseHeaders().set("Cache-Control", "no-store");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        } finally {
            exchange.close();
        }
    }

    static void bearer(HttpExchange exchange) throws IOException {
        String header = exchange.getRequestHeaders()
            .getFirst("Authorization");
        String expected = "Bearer demo-only-token";
        boolean valid = header != null
            && MessageDigest.isEqual(
                header.getBytes(StandardCharsets.US_ASCII),
                expected.getBytes(StandardCharsets.US_ASCII));
        if (!valid) {
            exchange.getResponseHeaders().set("WWW-Authenticate",
                "Bearer realm=\"demo\", error=\"invalid_token\"");
            reply(exchange, 401, "bearer: unauthorized");
            return;
        }
        reply(exchange, 200, "bearer: accepted");
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
            new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        var basic = server.createContext("/basic", exchange -> {
            reply(exchange, 200, "basic: accepted");
        });
        basic.setAuthenticator(new BasicAuthenticator("demo") {
            @Override public boolean checkCredentials(
                    String username, String password) {
                return "demo-user".equals(username)
                    && "demo-pass".equals(password);
            }
        });
        server.createContext("/bearer", AuthLayersHttpDemo::bearer);
        server.start();
        try {
            URI base = URI.create("http://127.0.0.1:"
                + server.getAddress().getPort());
            HttpClient client = HttpClient.newHttpClient();
            HttpRequest basicWithout = HttpRequest.newBuilder(
                base.resolve("/basic")).GET().build();
            HttpResponse<String> noBasic = client.send(
                basicWithout, HttpResponse.BodyHandlers.ofString());
            System.out.println("Basic without: " + noBasic.statusCode());

            String encoded = Base64.getEncoder().encodeToString(
                "demo-user:demo-pass".getBytes(StandardCharsets.UTF_8));
            HttpRequest basicWith = HttpRequest.newBuilder(
                base.resolve("/basic"))
                .header("Authorization", "Basic " + encoded)
                .GET().build();
            HttpResponse<String> yesBasic = client.send(
                basicWith, HttpResponse.BodyHandlers.ofString());
            System.out.println("Basic with: " + yesBasic.statusCode()
                + " " + yesBasic.body());

            HttpRequest bearerWithout = HttpRequest.newBuilder(
                base.resolve("/bearer")).GET().build();
            HttpResponse<String> noBearer = client.send(
                bearerWithout, HttpResponse.BodyHandlers.ofString());
            System.out.println("Bearer without: " + noBearer.statusCode());

            HttpRequest bearerWith = HttpRequest.newBuilder(
                base.resolve("/bearer"))
                .header("Authorization", "Bearer demo-only-token")
                .GET().build();
            HttpResponse<String> yesBearer = client.send(
                bearerWith, HttpResponse.BodyHandlers.ofString());
            System.out.println("Bearer with: " + yesBearer.statusCode()
                + " " + yesBearer.body());

            System.out.println("Basic challenge: "
                + noBasic.headers().firstValue("WWW-Authenticate")
                    .map(h -> h.split(" ", 2)[0]).orElse("missing"));
            System.out.println("Bearer challenge: "
                + noBearer.headers().firstValue("WWW-Authenticate")
                    .map(h -> h.split(" ", 2)[0]).orElse("missing"));
        } finally {
            server.stop(0);
        }
    }
}
~~~

### Compiling and Running

In the directory containing the Java file, use **JDK 17+**:

~~~bash
javac --release 17 -encoding UTF-8 AuthLayersHttpDemo.java
java AuthLayersHttpDemo
~~~

Empirically verified stdout:

~~~text
Basic without: 401
Basic with: 200 basic: accepted
Bearer without: 401
Bearer with: 200 bearer: accepted
Basic challenge: Basic
Bearer challenge: Bearer
~~~

### Reading the Code Properly

1. `BasicAuthenticator` is part of `com.sun.net.httpserver`, automatically handling the HTTP Basic challenge/credentials for the `/basic` context. `checkCredentials` in the demo only compares two mock literals and does **not** represent a real password management system.
2. `Base64.getEncoder()` only produces a representation of `username:password`, not secure encryption; that is why the demo intentionally binds to **loopback**.
3. `/bearer` reads the `Authorization` header and compares it against **a mock token**. `MessageDigest.isEqual` avoids naive byte array comparison in the example, but **does not perform JWT signature, audience, expiry, scope, or revocation checks**. A real system needs an authentication provider/token validator.
4. `401` is returned with `WWW-Authenticate` in both schemes. The code prints the **challenge name** instead of printing the Base64 password/token to avoid developing a habit of logging secrets.
5. Although `GET /basic` and `GET /bearer` are two different endpoints, they both use **HTTP authentication**, while their credential formats and validation logic are completely different.
6. The demo **does not simulate a forward proxy** and does not send `Proxy-Authorization`. `407` is part of the protocol knowledge in section 4; a `401` from a local server must not be mistaken for a proxy error.
7. Use `HttpResponse.statusCode()` to distinguish successful/unauthorized responses; do not assume HTTP `401` automatically turns into a network exception. `HttpClient.send(...)` normally returns a regular response with status 401.
8. `server.stop(0)` stops the HTTP listener used for the test; it is unrelated to authentication or the lifecycle of real access tokens.

**Why not create a JWT token in the demo?** The goal of the lesson is to distinguish layers and credential types; creating a fake JWT with Base64 without a valid signature easily gives the wrong impression that the token has been validated. The demo simulates token matching to clearly show header semantics, while emphasizing that a real identity provider/validator must be used in production.

## 12. Java 17 Example B: TLS 1.3 mTLS and Certificate Identity

To see that **a TLS certificate is not an HTTP Authorization header**, the second example **does not use HTTP**; instead it uses `SSLSocket` to send two lines `PING` / `PONG` over TLS 1.3 on TCP loopback. Both ends have their own keystore and truststore:

~~~text
server.p12                     server-trust.p12
(server private key + cert)    (trusts client cert)
        │                            │
        ▼                            ▼
   SSLServerSocket ------ TLS 1.3 mTLS ------ SSLSocket
        ▲                                          ▲
        │                                          │
server requires client cert              client.p12 + client-trust.p12
                                         (client private key + cert; trusts server)
~~~

**Trust model:**
- The client validates the certificate of **server `localhost`** and the hostname `localhost` (SAN DNS).
- The server uses `setNeedClientAuth(true)` and a truststore that trusts only the test certificate `demo-client`.
- After the handshake, each side can read `SSLSession.getPeerPrincipal()`; they display the certificate identity in the demo, but **no application authorization step** is written.
- `PING/PONG` is a **TCP payload over TLS**, not an HTTP request, with no `Authorization` or `Proxy-Authorization`.

### 12.1. Creating Two Certificates and Two Truststores with keytool

Run in a **temporary practice directory, do not commit to Git**. The commands use JDK `keytool`, and the password `changeit` is for testing only. Self-signed certificates are valid for 2 days and are not suitable for production.

~~~bash
keytool -genkeypair -alias server -keyalg RSA -keysize 2048 -keystore server.p12 -storetype PKCS12 -storepass changeit -keypass changeit -validity 2 -dname "CN=localhost" -ext "SAN=DNS:localhost,IP:127.0.0.1" -ext "EKU=serverAuth" -noprompt
keytool -genkeypair -alias client -keyalg RSA -keysize 2048 -keystore client.p12 -storetype PKCS12 -storepass changeit -keypass changeit -validity 2 -dname "CN=demo-client" -ext "EKU=clientAuth" -noprompt
keytool -exportcert -alias server -rfc -keystore server.p12 -storepass changeit -file server.crt
keytool -exportcert -alias client -rfc -keystore client.p12 -storepass changeit -file client.crt
keytool -importcert -noprompt -alias server -file server.crt -keystore client-trust.p12 -storetype PKCS12 -storepass changeit
keytool -importcert -noprompt -alias client -file client.crt -keystore server-trust.p12 -storetype PKCS12 -storepass changeit
~~~

**Distinguishing the files:** `server.p12` and `client.p12` contain **private keys**; do not share them with partners or treat them as public files. `server.crt`/`client.crt` are public certificates. `client-trust.p12` is only used by the client to trust the server; `server-trust.p12` is only used by the server to trust the client. Do not swap them or install a trust-all manager for convenience.

Using command-line passwords as above is **only** for isolated testing. In real applications, you need proper PKI provisioning, private key protection, restricted file permissions, avoiding passwords in terminal history/CI logs, and managing expiry/rotation and revocation.

### 12.2. Complete Source Code `MtlsIdentityDemo.java`

~~~java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.KeyStore;
import java.util.concurrent.*;
import javax.net.ssl.*;

public class MtlsIdentityDemo {
    private static final char[] PASSWORD = "changeit".toCharArray();

    static SSLContext tlsContext(Path keyStorePath, Path trustStorePath)
            throws Exception {
        KeyStore keys = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(keyStorePath)) {
            keys.load(in, PASSWORD);
        }
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
            KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(keys, PASSWORD);

        KeyStore trusted = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(trustStorePath)) {
            trusted.load(in, PASSWORD);
        }
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trusted);

        SSLContext tls = SSLContext.getInstance("TLS");
        tls.init(kmf.getKeyManagers(), tmf.getTrustManagers(), null);
        return tls;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            System.out.println(
                "Usage: java MtlsIdentityDemo server.p12 server-trust.p12"
                + " client.p12 client-trust.p12");
            return;
        }
        SSLContext serverTls = tlsContext(
            Path.of(args[0]), Path.of(args[1]));
        SSLContext clientTls = tlsContext(
            Path.of(args[2]), Path.of(args[3]));

        ExecutorService workers = Executors.newSingleThreadExecutor();
        try (SSLServerSocket listener = (SSLServerSocket)
                serverTls.getServerSocketFactory().createServerSocket(
                    0, 8, InetAddress.getByName("127.0.0.1"))) {
            listener.setNeedClientAuth(true);
            listener.setEnabledProtocols(new String[] {"TLSv1.3"});

            Future<String> serverTask = workers.submit(() -> {
                try (SSLSocket peer = (SSLSocket) listener.accept()) {
                    peer.setSoTimeout(5_000);
                    peer.startHandshake();
                    String clientIdentity =
                        peer.getSession().getPeerPrincipal().getName();
                    BufferedReader in = new BufferedReader(
                        new InputStreamReader(peer.getInputStream(),
                            StandardCharsets.UTF_8));
                    if (!"PING".equals(in.readLine())) {
                        throw new IOException("Unexpected request");
                    }
                    peer.getOutputStream().write(
                        "PONG\n".getBytes(StandardCharsets.UTF_8));
                    peer.getOutputStream().flush();
                    return clientIdentity;
                }
            });

            try (SSLSocket client = (SSLSocket)
                    clientTls.getSocketFactory().createSocket(
                        "localhost", listener.getLocalPort())) {
                client.setSoTimeout(5_000);
                client.setEnabledProtocols(new String[] {"TLSv1.3"});
                SSLParameters params = client.getSSLParameters();
                params.setEndpointIdentificationAlgorithm("HTTPS");
                client.setSSLParameters(params);
                client.startHandshake();
                System.out.println("client sees server: "
                    + client.getSession().getPeerPrincipal().getName());

                client.getOutputStream().write(
                    "PING\n".getBytes(StandardCharsets.UTF_8));
                client.getOutputStream().flush();
                BufferedReader in = new BufferedReader(
                    new InputStreamReader(client.getInputStream(),
                        StandardCharsets.UTF_8));
                System.out.println("response: " + in.readLine());
            }
            System.out.println("server sees client: "
                + serverTask.get(5, TimeUnit.SECONDS));
        } finally {
            workers.shutdownNow();
        }
    }
}
~~~

### 12.3. Compiling/Running

After generating all PKCS12 files using the commands above:

~~~bash
javac --release 17 -encoding UTF-8 MtlsIdentityDemo.java
java MtlsIdentityDemo server.p12 server-trust.p12 client.p12 client-trust.p12
~~~

Verified actual output:

~~~text
client sees server: CN=localhost
response: PONG
server sees client: CN=demo-client
~~~

**Output explanation:**

1. The client checks the truststore and `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`, ensuring the certificate identity matches `localhost` according to the applied TLS/HTTPS rules.
2. The server checks the client certificate because of `setNeedClientAuth(true)`; the server's truststore contains the test client's certificate.
3. `getPeerPrincipal().getName()` reads the identity authenticated via the TLS session from the certificate information. In the test, the CNs are `localhost` and `demo-client`.
4. The line `response: PONG` proves that the payload was exchanged after a successful handshake; **there is no HTTP 200/401 status** in this TLS program.
5. The program tests TLS 1.3 by enabling only `TLSv1.3` on both sides; it will fail if the platform does not support it. The output above assumes JDK support and non-expired certificates.

**A useful negative test:** if the client lacks `client.p12` or the server truststore does not trust the client certificate, the mandatory mTLS handshake fails (typically via `SSLHandshakeException`). If the client truststore does not trust the server or the SAN does not match the hostname, the client handshake fails. This is a **pre-HTTP TLS error**, not using `401` to notify the peer when the TLS handshake cannot complete.

**Demo limitations:** self-signed certs, hard-coded password, single connection only, no application AuthZ, not an HTTPS REST server, and no real internal CA management. The program intentionally does **not** send an HTTP token to prove that the TLS layer is distinct from HTTP authentication mechanisms.

## 13. Using Java HttpClient with Proxies, Tokens, and Certificates

### 13.1. Configuring the HTTPS Client at the Right Layer

Java 17 sample:

~~~java
HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(5))
    .followRedirects(HttpClient.Redirect.NEVER)
    .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.org/v1/data"))
    .timeout(Duration.ofSeconds(10))
    .header("Authorization", "Bearer " + accessToken)
    .GET()
    .build();

HttpResponse<String> response = client.send(
    request, HttpResponse.BodyHandlers.ofString());
~~~

This is a **snippet**, requiring imports for `java.net.URI`, `java.net.http.*`, and `java.time.Duration`; `accessToken` is a valid token obtained from a secret/identity service, not hard-coded. **Do not run the example directly** because the illustrative hostname is not a real API. Standard Java HTTP client handles TLS certificate/hostname verification for HTTPS, while `Authorization` on the request is an **application credential** and does not replace TLS validation.

Why use `Redirect.NEVER` in the snippet? To avoid automatically forwarding a request carrying credentials to another origin without a control policy. The client must choose an appropriate redirect policy according to the trust boundary; do not treat all redirects as safe.

### 13.2. Proxy Selector and Proxy Credentials

An example of configuring a forward proxy location (not sending a request yet):

~~~java
ProxySelector proxy = ProxySelector.of(
    new InetSocketAddress("127.0.0.1", 8080));

HttpClient clientViaProxy = HttpClient.newBuilder()
    .proxy(proxy)
    .connectTimeout(Duration.ofSeconds(5))
    .build();
~~~

This is an **illustrative snippet**, requiring imports for `java.net.ProxySelector`, `java.net.InetSocketAddress`, `java.net.http.HttpClient`, and `java.time.Duration`. No proxy is started on port 8080 in the demo programs; if you use this configuration without a real proxy, the request will fail.

For a proxy requiring authentication, you can configure `HttpClient.Builder.authenticator(Authenticator)` with an appropriate credential provider/policy; do not arbitrarily assign the origin token to `Proxy-Authorization`. Some Basic proxy authentication scenarios, especially HTTPS tunneling, are affected by **JDK security properties regarding disabled schemes**; do not modify them to weaken security just to “get past 407.”

**Caution on `Authenticator` credential reuse:** when sharing a client across multiple destinations/realms, you must distinguish origin and proxy credentials, URL, host/port/realm, and never return the same username/password for every challenge. Protect secrets in memory, logs, and scope.

### 13.3. Client Certificate for Java HttpClient

If you want Java `HttpClient` to present a client certificate in mTLS, build an `SSLContext` from:
- `KeyManagerFactory` containing the **client private key + certificate**.
- `TrustManagerFactory` containing the **server's CA/trust anchor**.
- Pass `sslContext(context)` to `HttpClient.Builder`.

Connection logic example:

~~~java
SSLContext context = buildApprovedClientTlsContext();

HttpClient client = HttpClient.newBuilder()
    .sslContext(context)
    .build();
~~~

This is an illustrative snippet; `buildApprovedClientTlsContext()` is an **application function you must implement** to load keys/trust and policy (not included in the JDK). The `tlsContext` source in `MtlsIdentityDemo` shows basic KeyManager/TrustManager operations, but production requires stricter CA management, private key protection, and secret handling. Do not use a custom trust-all manager.

**Do not confuse them:** setting an `sslContext` with a client key to support mTLS **does not automatically send an application Bearer token**. To send a Bearer token, you must add `Authorization` to the request (or use the app's auth mechanism) and validate the token at the origin resource server.

## 14. Combining AuthN and AuthZ in Real Architectures

### Scenario A — Browser to Website

- The browser validates the certificate of the HTTPS endpoint.
- The user logs in via a form/SSO.
- The website issues a `Secure`, `HttpOnly`, `SameSite` session cookie according to policy.
- Each request to the backend uses the cookie/session to identify the user and then checks permissions.
- There is no requirement for the browser to present a client certificate, unless the product intentionally enforces mTLS client authentication.

**Conclusion:** an HTTPS server certificate is not equivalent to user login. TLS protects the channel; the session/auth system identifies the user.

### Scenario B — Service Calling a REST API Through a Proxy

- The service authenticates to the forward proxy via **proxy credentials** if needed.
- The TLS handshake authenticates `api.example.org`.
- The service sends `Authorization: Bearer access-token` with an audience/scope intended for the API.
- The API validates the token and then checks route/resource authorization.
- Proxy credentials, TLS truststores, and application tokens **cannot be used interchangeably**.

**Conclusion:** proxy 407, origin 401, and TLS handshake failures occur in three different places and must be handled separately in logging/diagnostics.

### Scenario C — Internal Service Requiring mTLS + Bearer

- The gateway requires a client certificate to identify the `orders-service` workload.
- The client sends an access token representing the user and the `orders:read` scope.
- Policy may require that **the workload is permitted to call the route on behalf of the user**.
- If the token is stolen and the system wants to prevent replay outside the workload, it can apply **certificate-bound access tokens** or an appropriate proof-of-possession mechanism.
- The backend only accepts identities from a trusted gateway or validates them itself, never trusting raw headers added by a public caller.

**Conclusion:** the two mechanisms can **complement each other**, but you must define who authenticates what, who grants which permissions, and where the TLS boundary lies.

### Scenario D — Client Receives 401 Even Though TLS Succeeded

This is **not contradictory**:
- The TLS server identity was validated.
- The application credential (password/token/session) may be missing, expired, or invalid.
- The server returned HTTP `401` after reading a valid request inside the TLS channel.
- There is no need to “replace the certificate” just because of a `401`, unless the API actually requires mTLS and the error occurred during the TLS stage.

## 15. Troubleshooting Errors in the Right Order

| Symptom | Typical layer | What to check |
|---|---|---|
| `ConnectException` or connect timeout | TCP/proxy/network | Host, port, proxy selector, firewall, routing |
| HTTP `407` + `Proxy-Authenticate` | Forward proxy | Proxy credentials/policy; do not use origin token |
| `SSLHandshakeException` due to trust/cert/hostname | TLS | Truststore, chain, SAN/hostname, expiry, protocol, client cert if mTLS |
| HTTP `401` + `WWW-Authenticate: Basic` | Origin HTTP Auth | Whether Basic credentials are correct; whether TLS is proper |
| HTTP `401` + `WWW-Authenticate: Bearer` | Origin/API token | Whether token is missing/expired/wrong audience/issuer/signature |
| HTTP `403`, valid token | Authorization | Scope/role/resource ACL, policies |
| HTTP `429` | Rate limiting | Retry-After/backoff, do not automatically swap credentials |
| HTTP `502`/`504` via reverse proxy | Gateway/upstream | Backend health, timeout, internal network |
| mTLS client missing certificate | TLS handshake | Client KeyManager, server needClientAuth, trust chain |
| mTLS succeeded but still HTTP `403` | Application layer | Identity mapping and permission checks |
| Client has Bearer but proxy still returns 407 | Proxy | Confusing `Authorization` with `Proxy-Authorization` |
| Proxy received certificate but backend does not know identity | Trust boundary after TLS termination | Trusted identity propagation mechanism; do not trust client-supplied headers |

### Do Not Let Logging Become a Credential Leak

**Never print** verbatim headers: `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`. Do not log private keys, passwords, or full JWTs in exceptions/traces. In the demo in section 11, the program only prints **status codes, scheme names, and non-sensitive sample bodies**.

For production observability, use request/correlation IDs, route names, status classes, latency, and error categories; redact queries containing secrets, sensitive headers, and certificate private material. TLS debugging in real environments also requires restricting who can read logs.

### Do Not Try to Bypass Security Errors by Disabling Checks

Dangerous “quick fixes”:
- Empty `X509TrustManager.checkServerTrusted` to accept any cert.
- Disabling hostname verification.
- Putting an access token in a URL query or sending tokens to arbitrary redirect hosts.
- Using Basic passwords over plaintext HTTP outside loopback.
- Having a proxy pass raw client-provided `X-Client-Cert` and letting the backend trust it as an mTLS-authenticated certificate.
- Accepting a JWT with a non-allowlisted `alg` or skipping `aud`/`iss`/`exp`.
- Turning HTTP `401`/`407` errors into “success” just so the flow does not crash.

The right approach is to identify **which layer rejected the request**, fix the credential/trust/policy at that exact layer, and check permissions at the business enforcement point.

## 16. Secure Implementation Checklist

1. **Identify who is the origin and who is the proxy.** If there is a forward proxy, keep proxy credentials separate from origin tokens/passwords.
2. **Mandate HTTPS for real credentials.** Enable certificate path/hostname validation and modern TLS. Never use trust-all.
3. **Determine user/service identity.** HTTP Basic, Bearer, session cookies, and client TLS certificates have different issuers, lifetimes, and boundaries.
4. **Separate AuthN from AuthZ.** A valid token/cert does not prove permission to call an endpoint; check scopes/roles/ACLs.
5. **Perform full token validation.** Key trust, allowed algorithms, issuer, audience, exp/nbf, issuer rotation, and replay/revocation policies.
6. **Use short-lived tokens and limit scopes.** Avoid sharing tokens across resource servers with different audiences; never send secrets via URLs/logs.
7. **Secure session cookies.** `Secure`, `HttpOnly`, `SameSite`, CSRF protection, and timeout/rotation/logout per use case.
8. **Use mTLS in its proper role.** Server requires client authentication when mandatory, has a server truststore for client certs; client still validates server hostname/trust.
9. **Keep TLS termination clear.** When a gateway decrypts, the hop to the backend needs protection; sanitize identity headers and trust the gateway in a controlled manner.
10. **Observe proxy CONNECT separately.** `407` before the tunnel differs from `401` inside the HTTPS origin.
11. **Enforce client redirect policies.** Do not send app tokens/credentials to other hosts without permission; prevent downgrades.
12. **Do not hard-code real private keys/passwords/tokens.** Use clear keystores/certificate/key rotation, secret managers, and access controls.
13. **Write negative tests.** Missing password, expired token, wrong audience, missing cert, SAN mismatch, proxy 407, user lacking scope.
14. **Keep secrets out of audit logs.** Log status/error layer/trace ID instead of auth headers.
15. **Protect resources.** Set timeouts, request size limits, rate limiting, and input validation; TLS/HTTP auth does not replace DoS protection or prevent application bugs.

## 17. Self-Check Exercises

1. An HTTP request going through a forward proxy receives status **407**. Which challenge header and credential header belong to the proxy?
2. An origin API returns **401** for a resource. Which header must be present according to the HTTP authentication framework?
3. Does HTTP Basic protecting a password with Base64 mean end-to-end encryption? Why is HTTPS needed?
4. Is `Authorization: Bearer ...` outside the HTTP authentication framework? Explain why the statement “application tokens are completely different from HTTP authentication” is misleading.
5. A server has a valid HTTPS certificate, yet `GET /profile` still returns 401. Did TLS fail?
6. A valid access token signed for the audience `billing-api` is sent to `reports-api`. Should Reports API accept it?
7. Why does a decodable JWT payload not mean the token is trustworthy?
8. Distinguish **ID token**, **access token**, and **refresh token** by recipient and purpose.
9. A server returns HTTP 403 for a token with `orders:read` when the route requires `orders:write`. Is this AuthN or AuthZ?
10. State two ways a session cookie differs from a client TLS certificate.
11. A server enables `setWantClientAuth(true)` instead of `setNeedClientAuth(true)`. Does it mandate that the client send a certificate?
12. A server uses `setNeedClientAuth(true)` but the client has no matching KeyManager/certificate. Does the error usually happen **before or after** the HTTP request?
13. A raw `SSLSocket` client trusts a valid CA but does not check the hostname. What could go wrong?
14. A forward proxy only forwards a TLS CONNECT tunnel to the origin. Can the proxy read `Authorization: Bearer ...` inside HTTPS if it does not terminate TLS?
15. If a reverse proxy terminates TLS and sends plaintext HTTP to the backend, is the final hop still protected by the Internet-facing TLS?
16. A backend receives `X-Client-Cert: CN=admin` from a public caller. Can it treat this as an authenticated mTLS identity?
17. What statuses does the Basic/Bearer Java demo return when credentials are missing and when mock credentials are valid? Why not test with real passwords/tokens?
18. The JSSE demo code calls `SSLSession.getPeerPrincipal()` after the handshake. What does it prove, and what does it **not** prove?
19. Can a Bearer token and a client TLS certificate be used simultaneously for the same request? Which type of identity/permission does each mechanism bind to?
20. If an API allows a stolen bearer token to be reused on another machine, is there a way to bind the token to a key/certificate to reduce replay?

**Answer hints:**
(1) `Proxy-Authenticate` and `Proxy-Authorization`; (2) `WWW-Authenticate`; (3) no, Base64 is decodable, TLS is needed; (4) Bearer is a scheme of HTTP authentication, while the token describes the credential/app policy; (5) not necessarily, the app layer lacks credentials; (6) no; (7) signature/issuer/audience/expiry have not been verified; (8) authenticate user for client / call resource server / obtain new token; (9) AuthZ; (10) cookies manage HTTP-layer sessions, TLS certs belong to the handshake and keys/certificates; (11) no; (12) during the handshake before HTTP; (13) may trust the wrong host; (14) no, unless TLS interception is performed; (15) no; (16) no, a trusted gateway must authenticate/sanitize it; (17) 401 then 200, all credentials are mock; (18) peer TLS identity, not business permissions; (19) yes, typically the certificate identifies the workload and the access token represents the user/scopes; (20) appropriate certificate-bound token / proof-of-possession.

## 18. Summary

- **HTTP Authentication:** `401 + WWW-Authenticate` and `Authorization` are for the origin; **proxy authentication:** `407 + Proxy-Authenticate` and `Proxy-Authorization` are for the forward proxy. Do not swap them.
- **A Bearer token is an HTTP auth scheme when used in `Authorization`.** It differs from Basic in credential source, lifecycle, permissions, and revocation; tokens can be opaque or JWT, and are not inherently secure just because of a special format.
- **A TLS server certificate** is verified by the client during the handshake to authenticate the right HTTPS endpoint and establish a confidential/integrity-protected channel; it does not replace user/session authentication.
- **An mTLS client certificate** is requested/verified by the server during the handshake and typically identifies the client workload/service; authentication does not automatically equal authorization.
- **Proxies/TLS termination change trust boundaries:** HTTPS CONNECT tunnels, reverse proxies, and gateways can see or not see different credentials; forwarded identity headers are only trustworthy if set by an authenticated proxy.
- **Java 17 in practice:** `BasicAuthenticator` illustrates HTTP 401/Basic; `HttpRequest.header` illustrates Bearer; `SSLContext`/`KeyManagerFactory`/`TrustManagerFactory` and `setNeedClientAuth(true)` illustrate TLS mTLS.
- **Safety:** always use HTTPS and proper validation, never log tokens/passwords/keys, validate audience/scope/claims, manage session cookies and authorization separately, and test failure branches at every layer.

### References

- [RFC 9110 — HTTP Semantics, Authentication, 401/403/407](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 7617 — The Basic HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html)
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446.html)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705.html)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html)
- [Oracle Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html)
- [Oracle Java SE 17 — BasicAuthenticator](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/BasicAuthenticator.html)
- [Oracle Java SE 17 — SSLServerSocket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLServerSocket.html)
- [Oracle Java SE 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html)
- [Oracle Java SE 17 — SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html)
