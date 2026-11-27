# Tokens Are Sensitive Data: Avoid URLs, Logs, and Error Messages

In a **Spring Security OAuth 2.0 / OIDC Resource Server** system, a **Bearer Access Token** is sensitive information because any party holding a valid token can generally use it to call the API within its granted permissions. The Bearer mechanism is based on **token possession**: if a token is copied, someone else can replay it to request resources until it expires or is invalidated, unless the system adds sender-constraining mechanisms such as DPoP or mutual TLS.

Therefore, even when the Resource Server accurately verifies JWT signatures, issuer, audience, expiration, and scopes, the application can still suffer incidents if it **puts tokens in URLs, writes tokens to logs, or exposes tokens and internal details in error messages**.

## 1. Why must tokens be treated as secrets?

Related token types serve different purposes, yet all require careful handling:

| Information type | Purpose | Risk if leaked |
|---|---|---|
| **Access Token** | Used by clients to access the Resource Server. | Others can call APIs with the token's permissions while it remains valid. |
| **Refresh Token** | Used by clients to request new Access Tokens when allowed. | Can sustain access longer than a single Access Token; typically especially sensitive. |
| **ID Token** | Used by an OIDC Client to confirm user login information. | Can expose identity and personal claims; must not be used instead of an Access Token to call APIs. |
| **Client Secret / API Key** | Authenticates a client or accesses a service per a dedicated mechanism. | Can allow client impersonation or unauthorized service calls. |

**A JWT is not encrypted merely because it has three dot-separated segments.** Common JWTs are digitally signed (JWS): the signature verifies integrity and issuer, while the Base64url payload can be decoded to read claims. Never put passwords, secret keys, or unnecessary data inside claims.

A JWT shown truncated on screen (e.g., **eyJ...**) should still never be recorded in full in any other input or output. There is no such thing as a “safe log location” merely because only internal staff can view it; logs are routinely replicated to observability tools, backups, analytics systems, and support tickets.

## 2. Never pass Bearer Access Tokens in URLs

### 2.1. Bad examples

The following patterns create risk:

~~~http
GET /api/orders?access_token=eyJhbGciOi... HTTP/1.1
Host: api.example.test
~~~

~~~http
GET /api/download/eyJhbGciOi... HTTP/1.1
Host: api.example.test
~~~

Tokens appearing in a URL's **query string** or **path** can be captured in many places:

1. **Access logs of reverse proxies, gateways, load balancers, and web servers.** Many logs record the full request target, including path and query.
2. **Browser history, bookmarks, address-bar suggestions, and screenshots.** Users can accidentally share URLs containing tokens.
3. **Monitoring, APM, and distributed tracing.** Attributes such as full URLs may be recorded in spans or events.
4. **`Referer` headers when browsers navigate elsewhere.** Referrer policies may alter leakage scope; never rely on referrer policies to protect tokens placed in URLs.
5. **Caches, analytics tools, error-tracking systems, and support tickets.** URLs are commonly treated as “non-secret” data and copied freely.
6. **Redirects, emails, chat messages, and documentation.** A link pasted to ask for support can disclose credentials.

**Fragments** after **#** are usually not sent by browsers to servers in HTTP requests, yet can still appear in history, be read by JavaScript, or get shared. They are also not an appropriate place to store tokens in URLs.

OAuth 2.0 defines methods for carrying Bearer tokens via form parameters or URI query parameters in RFC 6750 with specific constraints; **for modern APIs, the standard and preferred approach is the Authorization header**. Avoid designing new APIs that require Bearer Access Tokens in URLs.

### 2.2. Good example: Authorization header

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN
Accept: application/json
~~~

For APIs, pass the token via:

**Authorization: Bearer ACCESS_TOKEN**

The header separates credentials from the URL, reducing exposure in browser history, URL access logs, and path analytics tools. However, **headers are not automatically completely safe**: if a proxy or application logs all headers, the token still leaks. The API must run over **HTTPS/TLS** to protect credentials in transit.

JavaScript client example:

~~~javascript
const response = await fetch("https://api.example.test/api/orders", {
  headers: {
    Authorization: "Bearer " + accessToken,
    Accept: "application/json"
  }
});

if (!response.ok) {
  throw new Error("Failed to load orders");
}

const orders = await response.json();
~~~

In this example, **accessToken** is a value the client obtained and manages legitimately. Do not call **console.log(accessToken)**, do not attach the token to query strings, and do not display the token in user-facing errors. Browser-side token management must also account for XSS risks, storage scope, and token lifetime; a BFF pattern keeping tokens server-side may fit web applications well.

### 2.3. Download or shareable links

Some systems want clickable URLs to download files. **Do not use long-lived OAuth Access Tokens as download parameters**. Consider one of these designs depending on your system:

- Download through an endpoint authenticated via headers or an appropriate session.
- A Backend for Frontend accepts a session cookie, checks permissions, and retrieves the resource using a server-side token.
- If a temporary access URL is strictly required, issue a **separately signed, narrowly scoped, short-lived or single-use ticket**, and treat that URL as a sensitive credential: minimize logging, restrict caching, exclude from analytics, and apply strict referrer policies.

A signed URL can still act as a **Bearer credential**: anyone holding the URL can use it while valid. Giving it a short lifetime does not turn the URL into public data.

## 3. Logs are where tokens leak unintentionally

During operations, tokens can end up in logs even if developers never wrote an explicit “log token” statement.

| Origin | Risky pattern | Mitigation |
|---|---|---|
| **Reverse proxy / API gateway** | Logging full URLs, all request headers. | Do not log credentials; configure logs using an explicit field allowlist. |
| **Spring filter / interceptor** | Logging the full HttpServletRequest or Authorization header. | Log only method, status code, route template, and a safe correlation ID. |
| **Exception handler** | Logging raw requests or exceptions carrying credentials. | Log standardized error categories using controlled exception handling. |
| **HTTP clients calling other services** | Wire logging or debug printing of request headers. | Disable or mask sensitive fields in request/response logging. |
| **Distributed tracing / APM** | Recording **url.full**, request headers, or payloads in spans. | Filter data at the source, collector, and exporter per real config. |
| **Metrics** | Using tokens, URLs with queries, or subjects as metric labels. | Use fixed route/operation names and bounded-cardinality labels. |
| **Alerts, emails, tickets, crash reports** | Copying stack traces and raw requests containing tokens. | Sanitize content before publishing or sharing. |

### 3.1. Code patterns to avoid

~~~java
// DO NOT: log credentials.
String authorization = request.getHeader("Authorization");
log.info("Authorization header: {}", authorization);

// DO NOT: URLs may contain tokens or sensitive data.
log.info("Request URL: {}", request.getRequestURL());
log.info("Query: {}", request.getQueryString());

// DO NOT: return raw exception messages to clients.
return ResponseEntity.status(401).body(exception.getMessage());
~~~

Beyond Authorization, headers such as **Cookie**, **Set-Cookie**, **Proxy-Authorization**, **X-API-Key**, and custom credential headers must also be protected. Avoid logging entire request bodies: bodies may contain passwords, authorization codes, refresh tokens, API keys, or personal data.

In particular, **request.getRequestURI()** cannot be assumed safe if the system permits secrets in paths. **request.getQueryString()** is even more likely to hold secrets. Prefer fixed **route templates** obtained from the router or known business identifiers, such as **GET /api/orders/{orderId}**, ensuring dynamic parameter values are excluded.

### 3.2. Selective logging pattern

Example Spring MVC filter that logs only HTTP method and status code:

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class SafeRequestLogFilter extends OncePerRequestFilter {

    private static final Logger log =
        LoggerFactory.getLogger(SafeRequestLogFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {
        try {
            chain.doFilter(request, response);
        } finally {
            log.info(
                "http_request method={} status={}",
                request.getMethod(),
                response.getStatus());
        }
    }
}
~~~

This snippet intentionally **omits URL, query, Authorization, Cookie, body, and tokens**. It is a minimal example of field selection; production systems can add server-generated request IDs, controlled route templates, latency, or standardized business error codes. Never put tokens, raw JWT claims, or sensitive data into **MDC** where they automatically propagate into all log lines.

Do not print entire **Jwt**, **Authentication**, **OAuth2AuthorizedClient**, or **TokenResponse** objects via **toString()** without knowing exactly what will be emitted. An object's log output can expose claims, token values, or personal information.

### 3.3. Configuring Spring Boot to limit error detail exposure

Example production configuration:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.security: INFO

server:
  error:
    include-message: never
    include-binding-errors: never
    include-stacktrace: never
    include-exception: false
~~~

The **server.error** properties restrict data included in Spring Boot's default error responses; the **INFO** log level avoids excessive debug output. However, **this does not automatically scrub tokens from all logs**. Custom loggers, proxy access logs, header logging filters, APMs, and error trackers must be controlled independently.

When debugging, avoid leaving **TRACE/DEBUG** enabled for Spring Security, HTTP clients, servlet containers, or proxies in environments carrying real tokens. If investigation in a controlled environment is necessary, use non-production test data, allowlist-based logging, and purge data afterward.

### 3.4. Reverse proxy example

Some default Nginx access log formats use **$request**, which includes the request line and query string. If a client sends an Access Token in the query, the token goes straight into the access log.

Example minimal log format intentionally **excluding URLs and headers**:

~~~nginx
log_format api_safe
    'method=$request_method status=$status '
    'request_time=$request_time';

access_log /var/log/nginx/api-access.log api_safe;
~~~

This is only an Nginx configuration example. Also inspect ingress controllers, CDNs, WAFs, gateways, and log collectors; changing one access log does not eliminate every place a token might be written. Fields such as **$request_uri**, **$args**, or request headers must be controlled separately.

### 3.5. Do not mistake “masking a few characters” for full protection

Practices like “log only the first 10 characters of the JWT” or “use the token as a correlation ID” can still create unnecessary tracking identifiers, increase identity leakage risk, and give a false sense of security. Normally, logs should use a **server-generated request ID** and error category, not a substring of a token.

If a business requirement genuinely needs to correlate events to the same token, design a dedicated solution covering security, access controls, retention, guessing risks, and preventing token reconstruction from logged data. Never automatically log hashes of Access Tokens in every log line.

## 4. Authentication error messages must be helpful without disclosing credentials

The Resource Server needs to distinguish at least two situations:

- **401 Unauthorized:** No suitable credential was provided, or the Access Token cannot be accepted (expired, invalid signature, wrong issuer, wrong audience, etc.).
- **403 Forbidden:** The request was authenticated, but lacks sufficient permissions to access the resource.

The API can return standard status and error codes so the client can decide whether to prompt re-login, refresh tokens per client policy, or report insufficient permissions. **Never return the token, part of the token, JWT strings, signing key details, stack traces, or internal messages from authentication libraries.**

### 4.1. What level of detail should HTTP responses return?

Example when credentials are missing:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Content-Type: application/json

{"code":"unauthorized","message":"Authentication is required."}
~~~

Example when the Access Token is invalid:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Content-Type: application/json

{"code":"invalid_token","message":"Unable to authenticate the request."}
~~~

Example when authenticated but lacking permissions:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
Content-Type: application/json

{"code":"forbidden","message":"Insufficient permissions to access the resource."}
~~~

**WWW-Authenticate** is the challenge header used by OAuth 2.0 Bearer Tokens. Depending on the case, the specification allows attributes such as **realm**, **scope**, or **error_description**; send only information genuinely needed by clients and explicitly vetted. Never reflect tokens or internal exceptions into **error_description**.

Responses like the following are inappropriate:

~~~json
{
  "error": "JWT eyJhbGciOi... failed: expected issuer https://internal-idp.example.test, stack trace ..."
}
~~~

This illustrates a **response to avoid**, as it exposes credentials and internal system details. Client-facing error descriptions should be stable, concise, and free of request-specific secret data.

### 4.2. Spring Security Resource Server handles errors in the filter chain

With a JWT Resource Server configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Spring Security uses **BearerTokenAuthenticationFilter** to extract the Bearer token, then validates it with **JwtDecoder** and configured validators. When authentication fails or permissions are missing, the security chain's **AuthenticationEntryPoint** and **AccessDeniedHandler** produce the appropriate response.

**Do not rely solely on @RestControllerAdvice** to handle JWT errors from the filter chain, since these errors occur **before the request reaches a controller**. By default, Resource Server provides **BearerTokenAuthenticationEntryPoint** and **BearerTokenAccessDeniedHandler** for standard responses. If your product needs standardized JSON error bodies, configure error handling at the appropriate security layer.

The **csrf(...disable)** line in the example is suitable only for pure Bearer-header APIs that do not use session cookies for authentication. If the backend also serves cookie-based web login, design CSRF protection and separate security chains appropriate to the architecture.

### 4.3. Example customizing errors without leaking tokens

If the API requires a consistent JSON body, you can configure an entry point and access-denied handler emitting only generic details:

~~~java
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiErrorSecurityConfig {

    @Bean
    SecurityFilterChain protectedApi(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
                .authenticationEntryPoint((request, response, ex) -> {
                    response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                    response.setHeader(HttpHeaders.WWW_AUTHENTICATE, "Bearer");
                    response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                    response.getWriter().write(
                        "{\"code\":\"unauthorized\"}");
                })
                .accessDeniedHandler((request, response, ex) -> {
                    response.setStatus(HttpServletResponse.SC_FORBIDDEN);
                    response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                    response.getWriter().write(
                        "{\"code\":\"forbidden\"}");
                }));

        return http.build();
    }
}
~~~

This example is an **alternative configuration** to section 4.2; do not declare both beans with the same **/api/** matcher in a single application. It returns minimal JSON errors and avoids calling **ex.getMessage()**, **request.getHeader("Authorization")**, or putting tokens in the response.

In production, if **WWW-Authenticate** needs **invalid_token**, **insufficient_scope**, or missing-scope details per RFC 6750, use or customize Spring Security's handlers so standard semantics are preserved without leaking sensitive information. Response detail level is a design choice, never a reason to send raw exceptions to clients.

## 5. Controlling where the Resource Server accepts Bearer tokens

Spring Security Servlet uses **DefaultBearerTokenResolver** to extract tokens from requests. In its standard default configuration, it reads Bearer tokens from the **Authorization header** and **disables URI query parameter token extraction**. Do not enable URL token extraction merely for integration convenience.

To express this policy explicitly in configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

@Bean
BearerTokenResolver bearerTokenResolver() {
    DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
    resolver.setAllowUriQueryParameter(false);
    resolver.setAllowFormEncodedBodyParameter(false);
    return resolver;
}
~~~

And register the resolver in the API's **SecurityFilterChain**:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenResolver(bearerTokenResolver())
    .jwt(Customizer.withDefaults()))
~~~

These two snippets illustrate how to define the bean and wire it into a full Java configuration. Do not place a standalone **.oauth2ResourceServer(...)** call by itself in a Java file.

These settings control only **accepted input locations**. They do not erase URLs already logged at the proxy layer, nor do they protect headers if the application logs full requests.

## 6. Designing error handling and logging across layers

To avoid blind spots, trace a request's entire path:

~~~text
Client
  |
  | Authorization: Bearer <token>
  | HTTPS
  v
CDN / Load Balancer / WAF
  |      Access logs: avoid URLs with secrets, avoid sensitive headers
  v
API Gateway / Reverse Proxy
  |      Audit/trace: select only safe fields
  v
Spring Security Resource Server
  |      Bearer token resolver -> JWT validation / introspection
  |      Error handler: 401 / 403, never return tokens
  v
Controller / Service
  |      Business logs: never log Jwt, Authentication, raw requests
  v
Database / Downstream API
         HTTP client tracing: never log Authorization or refresh tokens

Log collector / APM / Error tracker
         Receives data with credentials stripped from the start
~~~

If the application calls downstream APIs, do not blindly forward the client's **Authorization** header to another service. The Access Token must match the target API's **audience** and delegation policy. Even when forwarding is legitimate, HTTP client logging must avoid printing the token.

**Cache-Control: no-store** on sensitive responses and restrictive **Referrer-Policy** settings can serve as defense-in-depth measures. They do not replace the rule **never put Bearer Access Tokens in URLs**.

## 7. Real-world scenarios and how to spot them

### Scenario A — API exposes the JWT in an error response

A client sends an expired JWT. A developer writes:

~~~java
log.warn("JWT invalid: {}", token);
return ResponseEntity.status(401)
    .body(Map.of("error", "Invalid token: " + token));
~~~

Result: the token is logged and returned in the response body. Even if that token was expired, this pattern will leak live valid tokens in other failure cases.

**How to fix:** use standardized error codes such as **invalid_token** or **unauthorized**. Log a safe error category/operation and an independent request ID; never log the token. For authentication errors in the Spring Security filter chain, handle them at the entry point rather than expecting a controller to catch them.

### Scenario B — Copying a URL to ask for support

The frontend has a URL:

~~~text
https://api.example.test/api/export?access_token=eyJ...
~~~

A staff member pastes the URL into internal chat. Even in a private channel, the token has now been copied into another system and may appear in notification emails, chat history, and search indexes.

**How to fix:** change the API to use the Bearer header and eliminate token-bearing URLs from support workflows. When describing a request, share **method, route template, timestamp, and request ID**, never real credentials.

### Scenario C — Enabling trace logging to debug a 401

To investigate 401 errors, operations enables HTTP wire logging at the gateway. The gateway writes every request's Authorization header to centralized storage.

**How to fix:** collect only necessary fields like status codes and categorized error reasons; verify redaction actually works before enabling capture. Turn off capture afterward and lock down collected logs.

### Scenario D — Metrics containing full URLs

Latency instrumentation uses **url.full** as a metric label. Requests to URLs with tokens generate distinct labels, exploding cardinality and writing tokens into metrics data.

**How to fix:** use **route template** and method as labels, such as **GET /api/orders/{id}**, after ensuring dynamic parameter values are excluded from labels. Never use raw URLs, JWTs, or user-supplied tokens as metric names or labels.

## 8. If you suspect a token has leaked

Treat a leaked token as a credential incident, scaled to severity and the issuing system:

1. **Stop the leak source:** remove the token from URL parameters, log statements, traces, error messages, or dashboards recording it.
2. **Assess scope:** token type, permissions, audience, issuance time and lifetime, where it was copied, and who could access it; avoid duplicating the token during investigation.
3. **Invalidate where possible:** revoke the token, revoke related sessions/refresh tokens, disable client credentials, or restrict access per the Authorization Server's capabilities. Self-contained JWTs may **not be immediately revocable** in every system without revocation, denylist, or short-lifetime designs.
4. **Check for abuse:** inspect abnormal API activity using safe audit logs, permissions, and timestamps rather than sharing raw credentials.
5. **Limit persistence of exposed data:** follow security procedures for logs, traces, snapshots, error reports, and copies under organizational control; account for backups and retention.
6. **Prevent recurrence:** use allowlist log filters, standardized error responses, secure gateway configs, and dummy test tokens in development environments.

**Shortening Access Token lifetimes and issuing minimal scopes** narrows blast radius if a token leaks, but does not replace keeping tokens out of logs and URLs.

## 9. Rules you can apply immediately

| Area | Avoid | Prefer |
|---|---|---|
| Sending tokens to APIs | **?access_token=...** or tokens in paths. | **Authorization: Bearer ...** over HTTPS. |
| Logging | Logging full requests, headers, JWTs, or raw exceptions. | Logging allowlisted fields, route templates, and independent request IDs. |
| HTTP 401 | Returning tokens, stack traces, signing key details, or exception messages. | Returning status, challenge, and concise, stable error codes. |
| HTTP 403 | Returning full claims or internal policy contents. | Returning an appropriate permission-denied code without disclosing secrets. |
| Debugging | Enabling wire logs in environments with live credentials. | Using dummy test data, redaction, and investigating by request ID. |
| Monitoring | Using full URLs or tokens as metric labels. | Using operation, route template, and bounded labels. |
| OAuth tokens in download URLs | Using long-lived Access Tokens. | Header/session-protected endpoints, or dedicated tightly scoped tickets. |
| Leaked token | Deleting a log line in just one app. | Tracking down copies, revoking/limiting tokens, and handling the incident by scope. |

## 10. Takeaways in Spring Security Resource Server

1. **A Bearer Access Token is a credential.** Whoever holds it can typically use it; never treat JWTs as public data.
2. **The Authorization header over HTTPS is the standard way to send tokens to HTTP APIs.** Keep Access Tokens out of query strings, paths, fragments, and redirect URLs.
3. **Never log credentials at any layer.** Spring application logs, proxy access logs, HTTP clients, APMs, error trackers, and metric labels can all leak tokens.
4. **Do not reflect authentication library errors back to clients.** The Resource Server must return appropriate 401/403 responses and challenges without leaking tokens or internal details.
5. **Design against leaks from the start.** Log only allowlisted fields, restrict log access, limit retention, and use short-lived, least-privilege tokens.

When an authentication error occurs, the system must answer **“was the request authenticated and authorized?”** without revealing **“what was the actual credential in the request?”**. This is a critical security boundary between authentication mechanisms and observability, support, and error handling systems.

## References

- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700).
- [Spring Security — OAuth 2.0 Resource Server: Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html).
- [Spring Security — OAuth 2.0 Resource Server: JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [OWASP Cheat Sheet — Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
