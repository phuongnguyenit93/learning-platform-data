# Requests, responses, HTTP methods, and security-related status codes

HTTP is the protocol for exchanging requests and responses between a client and a server. Spring Security makes authentication, authorization, and many defense decisions based on **information in the HTTP request**, and then expresses the result using **HTTP status, response headers, and response body**. Understanding this foundational layer accurately helps distinguish access errors, configure the right permissions for each method, avoid information leakage, and write meaningful security tests.

This lesson focuses on HTTP semantics directly related to security in Spring Boot/Spring Security applications. The illustrative examples use REST APIs; how an application handles a request may depend on the authentication configuration, client type, proxy/gateway, and business policy.

## 1. Lifecycle of an HTTP request/response

A client sends a request to ask for a resource or an action. The server returns a response with a status reporting the result, headers describing how to handle the response, and optionally a body.

~~~text
Browser / mobile / API client
          |
          |  HTTP request
          |  method + target + headers + optional body
          v
     Reverse proxy / gateway (if present)
          |
          v
   Spring Security filter chain
       |                 |
       | denied          | allowed
       v                 v
  401 / 403 / ...     DispatcherServlet
                         |
                         v
                    Controller
                         |
                         v
                    Service / DB
                         |
                         v
                    HTTP response
          |
          v
Client receives status + response headers + optional body
~~~

In HTTP/1.1, an example request looks like this:

~~~http
GET /api/orders/42?includeItems=true HTTP/1.1
Host: shop.example.test
Accept: application/json
Authorization: Bearer <access-token>
X-Request-Id: req-123

~~~

The first line consists of the **method**, **request target**, and protocol version. The headers provide metadata such as Host, Accept, and Authorization; the blank line ends the header section. The GET example has no body. The syntax above is illustrative; the string <access-token> is a placeholder, not a valid token.

If the request is accepted, the response may be:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
X-Content-Type-Options: nosniff

{"id":42,"ownerId":"customer-17","status":"PAID"}
~~~

**Status 200** only indicates that the server processed the request successfully according to HTTP semantics; it does not by itself prove that the caller is **properly authorized**, that the returned data **belongs to the right owner**, or that the response is **safe to cache**. Those are determined by the security system and business logic.

HTTP is fundamentally a stateless protocol across requests. Maintaining a login happens through a session cookie, token, or another mechanism; the server needs to check credentials and permissions for each request according to the chosen model. You must not infer that because a previous request was allowed, all subsequent requests are automatically allowed.

### 1.1. Request components to identify

| Component | Example | Security significance |
| --- | --- | --- |
| Scheme/transport | https:// | HTTPS/TLS protects data in transit; plain HTTP risks eavesdropping/tampering on the wire. |
| Method | GET, POST, DELETE | Expresses operation semantics and affects access policies, CSRF, and caching. |
| Path | /api/orders/42 | Serves as input for routing and many URL authorization rules. |
| Query string | ?includeItems=true | May appear in history/logs/analytics; avoid placing passwords or access tokens here. |
| Headers | Authorization, Cookie, Origin | May contain credentials, content negotiation information, or client-supplied metadata. |
| Body | JSON, form, multipart file | Must be checked for schema, size, data type, and permission to perform the business operation. |
| Network context | Client IP, proxy chain | Only trust IP information supplied according to a trusted proxy configuration. |

Path, query, header, body, and cookie **are all inputs that must be controlled**, even when a normal UI client does not let users edit them. An API caller can use a custom HTTP client and craft requests directly.

### 1.2. Response components to identify

| Component | Example | What to check |
| --- | --- | --- |
| Status | 200, 401, 403, 404 | Accurately reflects authentication, authorization, data, and error outcomes. |
| Content-Type | application/json | Ensures the client interprets the content type correctly; pair with MIME sniffing protection when appropriate. |
| Cache-Control | no-store | Prevents compliant caches from storing sensitive responses. |
| Set-Cookie | session=...; Secure; HttpOnly; SameSite=Lax | Governs how the browser stores/sends the session cookie; attributes must match the usage model. |
| WWW-Authenticate | Bearer ... / Basic ... | Announces the authentication scheme/conditions when the server returns a challenge. |
| Location | /api/orders/42 | Used in resource-creation/redirect responses; the returned URL must be constructed safely. |
| Security headers | HSTS, CSP, nosniff ... | Supports browser-side defense, depending on response type and environment. |
| Body | JSON or error HTML | Must not leak stack traces, secrets, order contents, or unnecessary authentication details. |

In HTTP/2 and HTTP/3, the wire representation differs from HTTP/1.1, but the concepts of method, target, headers, status, and body remain foundational for Spring applications.

## 2. HTTP methods: what do safe and idempotent mean?

Distinguish two important properties:

- **Safe:** a method defined for reading purposes, not requesting that the client cause business state changes on the server. Examples are GET and HEAD. The system may still write logs/metrics or perform side effects not requested by the client.
- **Idempotent:** executing the same request multiple times has the **same intended effect on server state** as executing it once. GET, HEAD, PUT, DELETE, and safe methods are idempotent according to HTTP semantics. POST and PATCH are not idempotent by default.

Idempotent **does not mean** that every response is identical, that no additional logs are written, or that the operation can be called arbitrarily many times without consuming resources.

| Method | Safe? | Semantically idempotent? | Common use | Security questions |
| --- | --- | --- | --- | --- |
| GET | Yes | Yes | Read a resource | Is data leaked by ID, query, role, or cache? |
| HEAD | Yes | Yes | Retrieve metadata like GET without returning a response body | Does it expose metadata or have authorization differences compared to GET? |
| OPTIONS | Yes | Yes | Query supported capabilities, CORS preflight | Are CORS and preflight permissions configured properly? |
| POST | No | Not by default | Create a resource/execute a business command | Are there CSRF protection, duplicate-request prevention, input limits, and rate limits? |
| PUT | No | Yes | Create or replace resource state at a URI | Is permission checked for updating the right ID/fields and concurrency conditions? |
| PATCH | No | Not by default | Partial update | Are there mass assignment, forbidden field updates, or data conflicts? |
| DELETE | No | Yes | Request deletion of a resource | Are object permissions, condition checks, and auditing enforced? |
| TRACE | Yes per HTTP spec | Yes | Echoes the request for diagnostics | Usually does not need to be enabled on public APIs; review server/proxy policy. |
| CONNECT | No | Not by default | Requests establishing a tunnel through a proxy | If enabled in the wrong context, it can create an unintended access path to destinations. |

Some systems can design an idempotent POST using an **idempotency key** and storing the processing result, for example to avoid creating two transactions when a client retries. That is an application-layer design, not something that makes all POST requests idempotent by default.

### 2.1. Why should GET not perform sensitive actions?

GET is commonly used by browsers, crawlers, prefetchers, link previews, monitoring, and caches. If **GET /api/payments/confirm?id=42** changes payment state, opening a link or an automated agent accessing the URL can cause unintended effects.

GET is also not a safe place to put secret information: the URI and query can appear in history, proxy logs, bookmarks, or telemetry. Do not use paths like **/reset-password?secret=...** without carefully considering secret lifecycle, log redaction, expiration, and single-use mechanisms. A token in an activation link is typically a special case requiring its own protection policy.

A **safe method** does not replace authorization: GET /api/orders/42 must still verify owner and tenant permissions.

### 2.2. Idempotency and repeated effects

- PUT /api/profile/42 sending the same content can bring the resource to the same final state, but requires permission for the rightful owner. Repeating a request does not grant an unauthorized subject extra permissions.
- DELETE /api/items/42 may return 204 the first time and 404 the next time. Two different response statuses **do not invalidate** the idempotency of the delete effect.
- POST /api/payments can create a new transaction if sent repeatedly; duplicate prevention, unique constraints, and idempotency keys are needed when the business logic requires them.
- PATCH can be idempotent if expressed as "set value = 5", but not idempotent if expressed as "increment value by 5"; do not infer the property solely from the method name.

For operations that create/modify data, it is typically necessary to control **authentication, authorization, CSRF when appropriate, input validation, concurrency, replay, and audit**.

## 3. HTTP status groups and their relationship to security

Status codes are protocol semantics emitted by the server. Choosing the right code helps clients distinguish between needing to log in again, lacking permissions, malformed requests, exceeding limits, and backend errors.

| Group | General meaning | Points to note |
| --- | --- | --- |
| 1xx | Interim information | For example, 100 Continue; does not represent the final authorization result. |
| 2xx | Request processed successfully | 200/201/204 must still be accompanied by proper permissions and proper data. |
| 3xx | Redirection or using a cached copy | Redirects can expose/change the method or affect credentials/cookies. |
| 4xx | Client-side request issue per HTTP semantics | Commonly seen when missing authentication, lacking permissions, wrong method/format, or rate limited. |
| 5xx | Server or dependent system could not fulfill the request | Do not return stack traces/secrets; requires monitoring and controlled error handling. |

### 3.1. 2xx: Success does not mean proper authorization

| Status | When commonly used | Security notes |
| --- | --- | --- |
| **200 OK** | Read/update succeeded and returns data | Verify data belongs to the right principal, do not leak sensitive fields; set an appropriate cache policy. |
| **201 Created** | Resource created, may include Location | Only return the ID/URL and data the caller is allowed to see; avoid creating resources on behalf of others. |
| **202 Accepted** | Accepted for asynchronous processing, not yet completed | Do not interpret as "paid/processed"; the task/queue still needs permissions and duplicate protection. |
| **204 No Content** | Succeeded with no body | Suitable for delete/update; a 204 response contains no body. |
| **206 Partial Content** | Returns part of the content based on Range | For private files, check permissions before serving any bytes; do not let Range leak data. |

An endpoint returning 200 to an insufficiently privileged user does not prove the API is "error-free"; it can be a **serious authorization bug**. Security tests must check both **data and side effects**, not just status.

### 3.2. 3xx: Redirects must be controlled

| Status | Semantics | Risks/things to remember |
| --- | --- | --- |
| **301 Moved Permanently** | Resource moved permanently | May be cached; be careful with URLs containing sensitive data. |
| **302 Found** | Temporary redirect; user agent may convert POST to GET | In web apps using form login, unauthenticated clients may receive a 302 to the login page. |
| **303 See Other** | Directs the client to perform GET to another resource after the request | Useful with the POST/Redirect/GET flow. |
| **307 Temporary Redirect** | Temporary redirect that preserves method/body | Do not accidentally redirect a POST containing credentials or sensitive body to an untrusted target. |
| **308 Permanent Redirect** | Permanent redirect that preserves method/body | Carefully review the target and client/cache policy. |
| **304 Not Modified** | Use cached copy per conditional request | Not a 3xx redirect; access permissions and caching mechanisms still need protection for sensitive resources. |

When an application accepts **returnUrl/redirectUri/next** from the client, it must validate an allowlist/valid destination to prevent **open redirect** and data leakage via URL. With OAuth/OIDC, the redirect URI must be validated strictly according to the authentication flow specification.

**HTTP → HTTPS redirect** helps move users to a secure connection, but the first request over HTTP may already expose data if the client sent credentials. Use HTTPS from the start, configure secure cookies and HSTS when the system is ready; do not rely solely on redirects to protect secrets.

### 3.3. 4xx: Error codes directly related to security

| Status | When appropriate | What to distinguish |
| --- | --- | --- |
| **400 Bad Request** | Request is syntactically invalid or cannot be processed due to the client | Distinct from 401: a malformed request does not necessarily mean missing login. |
| **401 Unauthorized** | Missing or invalid authentication proof for a protected resource | Misleading name: the focus is **authentication**; includes a WWW-Authenticate challenge when applicable. |
| **403 Forbidden** | Server understood the request but refuses to allow it | May be due to missing permissions, CSRF, or another policy; does not always mean the user is logged in. |
| **404 Not Found** | Resource not found or existence intentionally hidden | Can be used for a resource not owned by the user if policy intentionally avoids information disclosure. |
| **405 Method Not Allowed** | URI exists but does not support that method | Response must include an Allow header listing supported methods for the target. |
| **406 Not Acceptable** | Cannot produce an acceptable representation per Accept | Distinct from 415 regarding the format of the submitted body. |
| **408 Request Timeout** | Server did not receive the full request within an acceptable time | Does not replace rate limiting or authentication checks. |
| **409 Conflict** | Request conflicts with resource state | For example, optimistic locking or an invalid business state transition. |
| **411 Length Required** | Server requires Content-Length | Can be useful in upload flows; not synonymous with exceeding size limits. |
| **413 Content Too Large** | Request content exceeds server limits | Limit body/file size to prevent resource exhaustion. |
| **415 Unsupported Media Type** | Request Content-Type is not supported | Do not confuse with 406 (response Accept). |
| **422 Unprocessable Content** | Body has valid syntax but content cannot be processed per rules | For example, semantically invalid data; choose 400/422 consistently per API contract. |
| **429 Too Many Requests** | Exceeded request rate limit | May include Retry-After; rate limiting is an additional defense, not a replacement for authorization. |
| **431 Request Header Fields Too Large** | Headers are too large | May relate to abnormal cookies/headers; needs limits at proxy/server. |

**401 and 403 are the most easily confused pair.** Both their semantics and the server's specific configuration must be understood:

- **401:** the client has not provided valid credentials to authenticate. With HTTP Basic, the response may include **WWW-Authenticate: Basic realm="api"**; with Bearer, the challenge and error info may follow the configured Bearer token mechanism.
- **403:** the request is understood but forbidden. Commonly occurs when a valid principal lacks the required authority or a POST is blocked by CSRF. A server can also deny a request due to another policy when there is no authenticated principal yet.
- **404:** may be used instead of a response revealing that someone else's resource exists. However, leakage through timing differences, body, or related endpoints must be avoided if hiding existence is required.

Expected examples in an API using HTTP Basic with properly configured accounts:

| Request | Condition | Typical status |
| --- | --- | --- |
| GET /api/me | No credentials | 401 |
| GET /api/me | Wrong or expired credentials | 401 |
| GET /api/admin | Logged in with role USER, but only ADMIN can access | 403 |
| GET /api/admin | Valid ADMIN login | 200 |
| GET /api/orders/42 | User A requests B's order; Service checks owner | 403 or 404 per policy |
| POST /api/orders | User has permission but lacks CSRF token in a cookie-based session | May be 403 |
| POST /api/orders | Malformed body | 400 or 415 depending on the error |
| GET /api/orders/42 | Resource does not exist and no information to leak | 404 |

The table shows **configuration-dependent** examples, not hard rules for every system. In particular, browser apps using form login typically return a **302 redirect to the login page** for some unauthenticated requests, whereas REST APIs using HTTP Basic/Bearer typically use 401.

### 3.4. 5xx: Server errors and how to avoid information leakage

| Status | Typical meaning | Safe handling |
| --- | --- | --- |
| **500 Internal Server Error** | Unexpected internal error | Return minimal error info; store details in controlled logs. |
| **502 Bad Gateway** | Gateway received an invalid response from upstream | Check logs/tracing by request ID; do not expose internal endpoints. |
| **503 Service Unavailable** | Overloaded/maintenance/temporarily unavailable | Can add Retry-After; protect against retry storms. |
| **504 Gateway Timeout** | Gateway did not receive a timely response from upstream | Design timeouts, circuit breakers, and bounded retries. |

Do not turn every permission error into **500** to "hide details." Doing so causes clients to retry incorrectly, obscures security metrics, and makes diagnosis harder. At the same time, do not return stack traces, SQL, connection strings, JWTs, API keys, or internal filenames to clients just for debugging convenience. Use short messages, application error codes, and request/correlation IDs.

## 4. HTTP headers that impact security

### 4.1. Request headers

**Authorization** carries credentials for several authentication mechanisms:

~~~http
Authorization: Bearer <access-token>
~~~

A Bearer token is a **credential bearing authority**: whoever holds a valid token can use the permissions attached to the token within the granted scope, so it must be protected in storage/transit, and its signature or appropriate validation method, issuer/audience/expiry must be verified per configuration. Merely decoding a JWT string is not enough to trust claims.

HTTP Basic takes the form **Authorization: Basic ...**; the credentials part is Base64, **not encryption**. Do not send Basic over plain HTTP; use TLS and manage passwords properly.

**Cookie** sends cookies matching domain/path/policy. For sessions:

~~~http
Cookie: SESSION=<opaque-session-id>
~~~

A session ID is a secret. If stolen, it can be used to hijack the session depending on the design. The server must manage session lifecycle, logout/invalidation, expiration, and session fixation; the client must have HTTPS/Secure and appropriate cookie attributes.

Remaining headers:

- **Content-Type:** the data type the client actually sends, e.g. application/json or multipart/form-data. The server must validate the content rather than blindly trusting the header.
- **Accept:** the response type the client can accept. Do not use it as proof of access permission.
- **Origin:** browser origin of certain requests; helps handle CORS and can participate in CSRF defense depending on context, though non-browser clients can set this header themselves.
- **Host:** target host of the request; when used to build absolute URLs or reset links, Host header injection must be prevented via trusted host/proxy configuration.
- **X-Forwarded-For / Forwarded / X-Forwarded-Proto:** proxy metadata; **only trust when a trusted proxy controls and normalizes them**. Clients can send forged values if the server accepts them unconditionally.
- **Range / If-None-Match / If-Match:** control partial content or preconditions/caching; do not reduce the requirement to check permissions before returning data.
- **X-CSRF-TOKEN** or the corresponding CSRF header: one way to pass the token when the client uses configured CSRF protection; the header name may vary.

### 4.2. Response headers

**WWW-Authenticate:** used to send a challenge to the client, especially when returning 401. Choose the right authentication scheme instead of arbitrarily returning 401 without the information required by the protocol.

Illustrative **Set-Cookie**:

~~~http
Set-Cookie: SESSION=<opaque-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- **Secure:** the browser only sends the cookie over a secure connection per applicable rules.
- **HttpOnly:** reduces the risk of JavaScript directly reading the cookie; does not mean protection against all XSS or CSRF.
- **SameSite:** affects whether the browser sends the cookie in cross-site contexts; choose Lax/Strict/None according to the actual flow. SameSite=None requires Secure in modern browsers.
- **Path/Domain:** determines cookie scope; overly broad configuration can increase the exposure surface.

**Cache-Control** for sensitive data:

~~~http
Cache-Control: no-store
~~~

No-store instructs compliant caches not to store the response; it does not replace authorization, encryption, or data storage policies in the application itself. Be cautious with shared caches, CDNs, reverse proxies, and responses with **Vary** by content/credentials. Do not rely on clients always obeying it to protect top-secret data.

Some common browser headers:

| Header | Role | Limitations |
| --- | --- | --- |
| **Strict-Transport-Security** | HSTS instructs browsers to use HTTPS for subsequent visits per policy | Must be sent over HTTPS and rolled out carefully before applying includeSubDomains/preload. |
| **Content-Security-Policy** | Restricts script/style/resource sources and certain browser behaviors | Does not fix server-side XSS or eliminate the need for escaping/input validation. |
| **X-Content-Type-Options: nosniff** | Restricts MIME sniffing in supported contexts | Does not replace a proper Content-Type or upload content verification. |
| **Referrer-Policy** | Reduces URL data sent as referrer | Does not permit putting secrets in query strings since other leak paths exist. |
| **Permissions-Policy** | Restricts certain browser features | Not an API authentication or authorization mechanism. |
| **X-Frame-Options** or CSP frame-ancestors | Reduces clickjacking risk when content is embedded | Does not replace controls on sensitive actions. |

Spring Security supports many security headers by default or via configuration, but the specific policy must be checked against the Spring Security version and resource type. Do not assume library defaults satisfy all frontend/browser policies for every application.

## 5. How do authentication, authorization, and HTTP status go together?

### 5.1. Authentication: requiring a valid identity

Example calling an API that requires login:

~~~http
GET /api/profile HTTP/1.1
Host: shop.example.test
Accept: application/json

~~~

For an API configured with HTTP Basic, the response might look like:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="api"
Cache-Control: no-store

~~~

The client can send valid credentials on a subsequent request. With OAuth2 Resource Server/Bearer tokens, the challenge is typically Bearer and has its own rules for missing, invalid, or insufficient-scope tokens. With form login, instead of 401, the application may **302** to the login page. These are different entry point choices, not HTTP contradictions.

**Unauthenticated** and **authenticated but lacking permission** are two states that must be tested separately.

### 5.2. Authorization: a valid identity may still not be allowed

Suppose the authenticated principal is USER. Calling an ADMIN-only API:

~~~http
GET /api/admin/reports HTTP/1.1
Host: shop.example.test
Authorization: Bearer <valid-user-token>

~~~

The response might be:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json
Cache-Control: no-store

{"error":"forbidden"}
~~~

Key point: the server needs to verify credentials properly, determine trustworthy authorities/roles, check policies on method+path, and check **permissions on specific data** when needed. Do not read a role from an arbitrary client-sent header and trust it as proof.

**URL-level authorization is not enough for IDOR/BOLA:** if GET /api/orders/{id} is permitted for any logged-in user, the Service still needs to check whether that order belongs to the current principal/tenant. Status 403/404 must be tied to an actual denial decision, never allowing data to leak in the body or side effects to occur before returning the error.

### 5.3. Error codes are an API contract, not the sole defense layer

You cannot "secure" an API merely by always returning 404 instead of 403. If the endpoint already read/wrote data without authorization before returning 404, the risk still exists. An API using uniform error messages also needs to guard against leakage via body, headers, response time, and cache when required by the threat model.

Distinguishing status codes lets the client act appropriately: 401 may trigger login/refresh per policy; 403 typically requires granting permission or changing the operation; 400/422 fixing data; 429 waiting per rate limit; 503 temporary bounded retry. Do not infinitely retry state-changing requests.

## 6. CORS, CSRF, cookies, and the OPTIONS method

**CORS** (Cross-Origin Resource Sharing) controls whether the browser is allowed to let JavaScript at one origin read responses from another origin. The server returns appropriate CORS headers, such as **Access-Control-Allow-Origin**. For some cross-origin requests, the browser sends an **OPTIONS preflight** first to ask whether the method/headers are permitted.

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type

~~~

A successful preflight may be answered with:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: authorization,content-type
Vary: Origin

~~~

The example only illustrates the necessary headers for a specific scenario; if CORS credentials are enabled, an exact policy must be configured and wildcard origins must not be used together with credentials. **CORS does not authenticate identity, does not block curl or non-browser HTTP tools, and does not prevent CSRF on its own.** The server must always check permissions even if the browser allows reading the response.

**CSRF** (Cross-Site Request Forgery) is the risk that a browser is tricked into sending a request with side effects to an application where the user has an active authenticated session, especially when the browser automatically sends cookies/credentials in context. Therefore:

- State-changing methods (POST, PUT, PATCH, DELETE) typically need CSRF protection when the application uses cookie-sessions or browser-auto-sent credentials. Spring Security has a CSRF mechanism to configure for this model.
- If a truly stateless API only accepts bearer tokens explicitly attached by the client in Authorization and does not accept auto-sent cookies/credentials, CSRF design differs; XSS, token theft, CORS, and other auth paths still need evaluation.
- **GET/HEAD/OPTIONS must retain safe semantics.** If the server uses GET to delete data, default method-based CSRF protection may not block that action because GET is considered safe.
- Preflight OPTIONS requests sometimes arrive **without a session cookie**, so CORS configuration and filter ordering must support valid preflights before requiring authentication for business requests.

**SameSite cookies**, CSRF tokens, and Origin/Referer checks are different supporting tools; one should not claim a single mechanism solves every case.

## 7. HTTPS/TLS, proxies, and client addresses

HTTPS protects confidentiality/integrity while data traverses a TLS connection between TLS endpoints. In a system with a reverse proxy, TLS may terminate at the gateway and then travel to the backend over another connection; **the gateway → backend path still needs to be protected according to the network model and data sensitivity**.

Some common mistakes:

1. **Sending passwords/tokens over HTTP and expecting a redirect to HTTPS to protect them**: the first request may already be exposed.
2. **Directly trusting X-Forwarded-For sent by the client** to enforce an IP allowlist or rate limit: the header can be spoofed if the proxy does not sanitize/overwrite it.
3. **Trusting Host/Forwarded to generate sensitive links** (password reset, OAuth redirect) without validating allowed hosts: can lead to host-header injection.
4. **Configuring Secure cookies inconsistently with TLS termination at the proxy**, or the backend misjudging the request scheme: framework and trusted proxy must be configured properly.
5. **Equating HTTPS with authorization**: TLS prevents tampering on the wire, but user A over a valid HTTPS connection still cannot read user B's orders.

Request headers are not proof of "safety" merely because they were forwarded by a reverse proxy. Header provenance and proxy authority must be explicitly configured.

## 8. HTTP in the Spring Security (Servlet) flow

In a Spring MVC application using Spring Security, the Servlet filter chain processes the request before it reaches the Controller. Some key parts:

- **SecurityFilterChain** defines the set of filters and security rules applied.
- **Authentication** represents the identity and authorities after the authentication mechanism succeeds.
- **Authorization** decides whether the principal is allowed to access the path/method; Spring Security supports requestMatchers, authenticated, hasRole, hasAuthority, and custom rules.
- **AuthenticationEntryPoint** is responsible for initiating authentication when needed, such as returning 401/challenge or redirecting to login depending on the mechanism.
- **AccessDeniedHandler** handles permission denials in the appropriate flow, typically returning 403.
- **ExceptionTranslationFilter** helps translate certain authentication/authorization exceptions in the filter chain into corresponding HTTP handling.

This is the high-level picture; actual filter order, exception handlers, and concrete outcomes depend on configuration. Beyond filters, a Controller, Service, exception handler, or gateway can still actively return a response.

Illustrative configuration for a modern Spring Security application, **placed in a @Configuration class with full Spring Web/Spring Security dependencies**, not a standalone runnable Java file:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .requestMatchers("/api/orders/**").authenticated()
        .anyRequest().denyAll()
    ).httpBasic(Customizer.withDefaults());

    return http.build();
}
~~~

Here HttpSecurity, SecurityFilterChain, Customizer, and HttpMethod are types from Spring Security/Spring Framework; appropriate imports are needed. This configuration only describes some **URL access rules** and selects HTTP Basic. It does not create a user store by itself, does not define how passwords are stored, does not check ownership of individual orders, and does not provide other business rules.

Pay attention to **method + path**: GET /api/public/item is permitAll, but POST /api/public/item does not match the GET matcher; with the configuration above, the request may fall through to denyAll if no other rule matches. Adding new endpoints also requires explicit policies, rather than accidentally exposing them via overly broad URL patterns.

If using **multiple SecurityFilterChains**, you must understand which chain matches a request, chain ordering, and have an appropriate fallback chain; a filter chain applied only to /api/** does not prove that all management/actuator endpoints elsewhere are protected.

**Role-based authorization** does not replace **object/tenant-based authorization**. For a request that has passed authenticated(), the Service must still verify the principal is allowed to read/modify the specific resource. With method security such as @PreAuthorize, @EnableMethodSecurity must be enabled and Spring proxy behavior, including self-invocation, must be understood.

## 9. Java 17 practice: run an HTTP server and observe statuses

The following example **runs standalone with JDK 17+**, using only the Java standard library. It intentionally simulates four scenarios: no credentials → 401; valid credentials but not admin → 403; admin → 200; wrong HTTP method → 405. This is an **HTTP semantics simulation for learning**, not a real authentication mechanism: the demo tokens are constant string comparisons, with no signature, expiry, user database, session, or HTTPS. Do not expose this illustrative server on the Internet.

Save as **HttpSecuritySemanticsDemo.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

public class HttpSecuritySemanticsDemo {

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0
        );
        server.createContext("/api/admin", HttpSecuritySemanticsDemo::handle);
        server.start();

        try {
            URI uri = URI.create(
                "http://127.0.0.1:" + server.getAddress().getPort()
                + "/api/admin"
            );
            HttpClient client = HttpClient.newHttpClient();

            System.out.println(
                "anonymous GET: " + call(client, uri, "GET", null)
            );
            System.out.println(
                "user GET: " + call(client, uri, "GET", "user-demo")
            );
            System.out.println(
                "admin GET: " + call(client, uri, "GET", "admin-demo")
            );
            System.out.println(
                "admin POST: " + call(client, uri, "POST", "admin-demo")
            );
        } finally {
            server.stop(0);
        }
    }

    private static void handle(HttpExchange exchange) throws IOException {
        try {
            String method = exchange.getRequestMethod();

            if (!"GET".equals(method)) {
                exchange.getResponseHeaders().set("Allow", "GET");
                exchange.sendResponseHeaders(405, -1);
                return;
            }

            String auth = exchange.getRequestHeaders()
                .getFirst("Authorization");

            boolean isUser = "Bearer user-demo".equals(auth);
            boolean isAdmin = "Bearer admin-demo".equals(auth);

            if (!isUser && !isAdmin) {
                exchange.getResponseHeaders().set(
                    "WWW-Authenticate", "Bearer realm=\"demo\""
                );
                exchange.sendResponseHeaders(401, -1);
                return;
            }

            if (!isAdmin) {
                exchange.sendResponseHeaders(403, -1);
                return;
            }

            byte[] bytes = "admin".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8"
            );
            exchange.sendResponseHeaders(200, bytes.length);
            exchange.getResponseBody().write(bytes);
        } finally {
            exchange.close();
        }
    }

    private static int call(
        HttpClient client, URI uri, String method, String token
    ) throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder(uri);

        if (token != null) {
            builder.header("Authorization", "Bearer " + token);
        }
        if ("POST".equals(method)) {
            builder.POST(HttpRequest.BodyPublishers.noBody());
        } else {
            builder.GET();
        }

        return client.send(
            builder.build(),
            HttpResponse.BodyHandlers.discarding()
        ).statusCode();
    }
}
~~~

**Compile and run commands:**

~~~bash
javac --add-modules jdk.httpserver HttpSecuritySemanticsDemo.java
java --add-modules jdk.httpserver HttpSecuritySemanticsDemo
~~~

**Exact expected stdout:**

~~~text
anonymous GET: 401
user GET: 403
admin GET: 200
admin POST: 405
~~~

Explanation:

1. The server binds **127.0.0.1** on a random OS-assigned port; the client in the same program retrieves the exact port automatically, so the output contains no unstable port number.
2. **GET without Authorization** receives 401 and a WWW-Authenticate header, simulating the need for authentication.
3. **GET with user-demo** is recognized as a test identity but lacks admin permissions, so it returns 403.
4. **GET with admin-demo** returns 200 with body admin, though the client in the example only prints the status.
5. **POST** is rejected with 405 because the illustrative endpoint only supports GET, with header Allow: GET. The example checks the method **before** credentials to teach semantics; Spring Security may return a different code if an authentication/authorization filter blocks the request earlier.

**Limitation to remember:** string comparison of Bearer tokens in the example is not token verification. When building a real API, use Spring Security's standard authentication mechanisms (e.g., HTTP Basic suitable for demos or OAuth2 Resource Server for tokens) and HTTPS, then check permissions by function and data. Do not apply hardcoded token logic in production Controllers.

## 10. Inspecting HTTP with curl and DevTools

For an existing API, use observation tools to inspect the **actual request** and **actual response**. The following example commands are illustrative for a server running on localhost:8080 with corresponding endpoints:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/profile
curl -i -u reader:demo-password http://localhost:8080/api/profile
curl -i -u reader:demo-password http://localhost:8080/api/admin
curl -I http://localhost:8080/api/public
curl -i -X OPTIONS http://localhost:8080/api/orders
~~~

- **-i** displays the status line and headers along with the body.
- **-I** requests HEAD (in typical curl usage); HEAD returns metadata, not the response body.
- **-u** lets curl construct HTTP Basic Authorization. Only use demo credentials in permitted environments and appropriate secure channels; do not enter real passwords into command history/log captures.
- **-X OPTIONS** only changes the method; if you want to test **CORS preflight**, you must add Origin and Access-Control-Request-Method, possibly with Access-Control-Request-Headers.
- **curl -L** follows redirects. When debugging 302/307/308, observe whether a redirect occurs and which target/method is used; do not automatically send credentials to untrusted targets.

In the browser, the **Network** tab displays request URL/method, request headers, response status/headers, preflight, redirects, and timing. Avoid sharing recordings containing Cookie, Authorization, query tokens, or private content. If an application uses HTTPS on its public UI but calls an HTTP API, the browser may block it or create mixed content issues.

### 10.1. Testing across four dimensions

An HTTP security test should vary in a controlled way at the same time:

1. **Identity:** anonymous, regular user, admin, invalid/expired token.
2. **Method:** GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS per the API contract.
3. **Resource:** own resource, another user's resource, different tenant, non-existent ID.
4. **Payload and context:** malformed JSON, oversized body, missing CSRF token, different Origin, repeated requests, concurrent updates.

Example matrix:

| Scenario | Expectation from illustrative policy |
| --- | --- |
| Anonymous reads /api/me | 401 for challenge-based APIs; 302 if form login is chosen |
| Regular user calls /api/admin | 403 |
| User A reads B's order | Do not return B's data; 403/404 per policy |
| User sends POST to a GET-only API | 405 if the request reaches the resource handler and is not blocked earlier by filters |
| POST with wrong content type | 415 when media type handling policy rejects |
| Request exceeds quota | 429 or rejection mechanism per policy |
| File request exceeds limit | 413 or appropriate error code from gateway/app |
| State-changing method missing CSRF token when CSRF applies | 403 when CSRF filter blocks |
| Valid, fully authorized request | Success status and proper body/side effects |

When testing, **checking only the status is not enough**: an API might return 403 yet still write to the DB, publish a message, or leak data via headers/body. You must verify that data **was not modified**, events were not erroneously emitted, and the response contains no forbidden fields.

## 11. Common HTTP security mistakes

### 11.1. Checking only the URL, forgetting the method

Allowing **GET /api/resources/** for reading does not mean every POST/DELETE on the same URL is safe. Protect by method when needed, set clear rules, and have a fallback. Conversely, using overly narrow matchers while leaving other endpoints unprotected can unintentionally open an attack surface.

### 11.2. Confusing 401 and 403

Missing or invalid credentials is generally a 401 issue; having a principal but lacking permission is generally 403. However, depending on the login mechanism, filter order, exception handler, and Resource Server policy, the result should be verified against the actual configuration.

### 11.3. Returning 200 and hiding errors inside JSON

For example, returning 200 for every result with body {"error":"forbidden"} confuses clients, caches, monitoring, and HTTP tests. For denied requests, use a status reflecting the appropriate reason with a concise, consistent body.

### 11.4. Trusting header or query data to decide permissions

Headers like X-Role: ADMIN, parameter userId=..., Origin, or spoofed IPs do not prove permissions on their own. Permissions must be derived from the authenticated identity and checked per resource, tenant, and operation. Proxy metadata is only trusted along a controlled proxy chain.

### 11.5. Mis-caching private data

A successful GET response can be stored by browsers/CDNs/proxies if the policy is inappropriate. Determine which resources may be cached, whether they are user-specific, whether no-store is required, and whether cache keys properly isolate identity/tenant. 304 responses must also be understood in the context of conditional requests and authorization.

### 11.6. Mistaking CORS for API security

Browsers may block JavaScript from reading responses due to CORS; requests can still be sent and non-browser tools can still call the API. CORS does not replace authentication, authorization, CSRF protection, or side-effect controls.

### 11.7. Accidentally leaking credentials via URLs, logs, and redirects

Do not put access tokens or passwords in URLs/queries if safer alternatives exist. Authorization/Cookie logs must be masked/redacted, and redirect targets must be controlled. Debug/HTTP tracing configurations should not write raw secrets to production logs.

### 11.8. Exposing detailed errors or improper security headers

Do not return stack traces, DB errors, system paths, or internal accounts to clients. Appropriate security headers are needed for HTML/UI and APIs, while also avoiding mechanical configurations that break authentication flows or grant unchecked permissions.

## 12. Checklist when designing an endpoint

Before putting an endpoint into service, you can do a quick check:

- **Method:** Are GET/HEAD read-only? Do POST/PUT/PATCH/DELETE have accurate semantics, duplicate handling, and concurrency control? Do OPTIONS/CORS need support?
- **Identity:** How is authentication done (cookie, Basic, Bearer)? How are tokens/sessions verified, transmitted, and expired?
- **Permissions:** Who can call the method/path, and who can operate on the specific resource/tenant? Are there negative tests?
- **Request:** Do path/query/header/body/file have proper validation and size limits? Which proxy data can be trusted?
- **CSRF/CORS:** Is the client a browser or another machine; are credentials auto-sent by the browser; is preflight right?
- **Response:** Appropriate status? Correct cache/cookie/security headers? Does the body avoid leaking data on error?
- **Infrastructure:** Where does HTTPS start and end; does the gateway rewrite URL/method/headers; are management endpoints outside the chain?
- **Observability:** Logs do not leak secrets; request IDs, audit, rate limits, timeouts, and retries match the risk level.

### Self-check

1. At which layer should a logged-in user trying to read another user's order be handled, and what status might be returned? **Hint:** Service/object-level authorization; 403 or 404 depending on policy.
2. Why can DELETE return 204 the first time and 404 the next time and still be idempotent? **Hint:** idempotency refers to the intended effect, not requiring identical responses.
3. Why can a GET that changes an account balance be dangerous even when login is required? **Hint:** safe-method semantics, browser prefetch/link navigation, and CSRF.
4. Does CORS blocking the browser from reading a response mean the server did not receive the request? **Hint:** no; separate browser response-reading policy from server controls.
5. Why does HTTP Basic in the Authorization header still require HTTPS? **Hint:** Basic uses Base64, which provides no secret encryption.
6. Is an API that returns 403 after having performed an unauthorized data write safe? **Hint:** no; check side effects and enforce permissions before operations.
7. When does 302 typically appear instead of 401 in Spring Security? **Hint:** form login uses an AuthenticationEntryPoint that redirects to the login page.

## Conclusion

Reading **method, URL, headers, body, status, and response headers** accurately is the foundation for understanding Spring Security. **Authentication** establishes the principal; **authorization** determines which actions the principal may perform and which data it may access; **HTTP status** communicates the outcome to the client. Safe/idempotent methods, the 2xx/3xx/4xx/5xx groups, CORS/CSRF, cookies, caching, and HTTPS all directly impact security design. A secure system must enforce permissions before side effects, return consistent statuses, protect credentials, and prove denial cases with tests.
