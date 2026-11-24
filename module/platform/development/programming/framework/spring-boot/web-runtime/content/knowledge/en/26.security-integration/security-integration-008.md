# Security Headers, HTTPS, and Preventing Data Leaks in Error Responses

> **Context:** Spring Boot web-runtime → **Security Integration**. This lesson uses **Java 17+, Spring Boot 3.3.x, and Spring Security 6.3.x** to explain **HTTP security response headers**, HTTPS/TLS on embedded servers or reverse proxies, and designing **error responses that do not leak internal details**. The focus is on coordinated defenses rather than a “just add a few headers and the system is safe” recipe. MVC examples use default Tomcat; WebFlux/Reactor Netty has dedicated notes.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **HTTP security headers**, **HTTPS/TLS**, **authentication/authorization**, **CORS**, **CSRF**, **input validation**, and **error handling**, and understand what problem each layer solves.
2. Explain the roles of `Strict-Transport-Security` (HSTS), `Content-Security-Policy` (CSP), `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, and `Cache-Control`.
3. Recognize **which headers Spring Security adds by default**, which headers must be configured explicitly, and the difference between HTTP and HTTPS requests.
4. Configure HTTPS using a **PEM SSL bundle** for the embedded Spring Boot server or place TLS termination at ingress, understanding the risks of `Forwarded`/`X-Forwarded-Proto` from untrusted proxies.
5. Design error responses with **accurate HTTP status codes**, stable schemas, safe messages, a `requestId` for investigation, and zero leaked stack traces, class names, SQL, internal URLs, tokens, or PII.
6. Run a Spring Boot MVC application with a `SecurityFilterChain`, CSP and security headers, and 400/404/500 errors using `ProblemDetail`, verified with curl and MockMvc.
7. Distinguish errors coming from controllers, Spring MVC exception resolvers, Spring Security authentication/authorization entry points, Servlet containers, and reverse proxies.
8. Test HTTP→HTTPS, HSTS, browser CSP enforcement, header consistency across 2xx/4xx/5xx, preventing caching of sensitive data, and avoiding breakage of legitimate functionality.

## 2. The Big Picture of Defense in Depth

An application may return responses through multiple components:

~~~text
Browser / Mobile Client / API Client
          |
          | HTTPS/TLS
          v
CDN / WAF / Ingress / Reverse Proxy
          |                 |
          | headers?        | TLS termination?
          v                 v
Embedded Tomcat / Reactor Netty
          |
          v
Spring Security Filter Chain
          |    authn/authz, CSRF, security headers
          v
Spring MVC / WebFlux Request Handling
          |    validation, exception resolution, ProblemDetail
          v
Service / Database / Downstream
          |
          v
Response 2xx / 4xx / 5xx
          |
          +--> headers + status + body + cookies
          |
          v
Browser enforces supported headers / Client sees error
~~~

Three main toolsets in this article:

- **HTTPS/TLS** protects connections from eavesdropping and tampering, verifying server identity via certificate chains and hostnames when clients validate properly. It **does not** eliminate SQL injection, excessive JSON fields, or authorization flaws.
- **Security response headers** tell browsers what restrictions to enforce when loading/running/embedding resources, caching responses, sending referrers, or upgrading HTTP to HTTPS. Effects depend on the header, browser, context, and intermediate proxies.
- **Error response hygiene** limits what information leaves the system on failure, while keeping needed diagnostic details in internal logs/traces with proper access control and retention.

**Core point:** TLS encrypts an error response; if that body itself contains a database connection string or access token, TLS faithfully delivers **that exact sensitive data to the client**. Conversely, a sanitized error body sent over plaintext HTTP can still be intercepted in transit. You need both.

## 3. What Are Security Headers and Where Are They Applied?

An HTTP response has a status line, headers, and body. Illustrative example (not every header is added by Spring automatically):

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Content-Security-Policy: default-src 'self'; object-src 'none'
Referrer-Policy: no-referrer
Permissions-Policy: camera=(), microphone=(), geolocation=()

{"status":"ok"}
~~~

Headers can be written by Spring Security, controllers, servlet filters, web servers, ingress, or CDNs. If multiple layers write the same header with conflicting values, behavior can be unpredictable or ignored by browsers. Assign a clear **header owner** and inspect responses through the real public URL.

### Security Headers Are Not Request Headers

| Group | Examples | Typically Set By | Purpose |
|---|---|---|---|
| Response security | CSP, HSTS, X-Frame-Options | Server/ingress | Browser enforcement policies for handling the response |
| Response caching | Cache-Control, Vary | Server/CDN | Controls caching and representations |
| Request context | Origin, Authorization, Cookie | Browser/client | Input for server decisions; not automatic permission |
| Proxy forwarding | Forwarded, X-Forwarded-Proto | Trusted proxy | Propagates original scheme/host/client across hops |
| Error body fields | title, status, detail, requestId | API error handler | Controlled error info, not mandatory HTTP headers |

Never stuff a stack trace into `X-Error-Detail` and consider the body clean. **Headers are also client-visible data** and can be logged by clients/proxies. Audit header values, redirects, cookies, bodies, filenames, caching, and trailers alike.

## 4. Which Headers Does Spring Security Provide by Default?

When Spring Security servlet/web security configuration keeps header defaults, the Security documentation lists this typical default set:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 0
Strict-Transport-Security: max-age=31536000 ; includeSubDomains
~~~

**HSTS is added only when the request is recognized as HTTPS/secure.** Over plaintext HTTP on localhost, not seeing HSTS is expected behavior. If requests reach Spring from ingress over HTTP while users connect over HTTPS on the internet, configure TLS termination and forwarded-header trust properly; otherwise the app may not treat requests as secure.

Key points to remember:

- **CSP is not generated by Spring Security by default**, because an appropriate policy depends on each application's actual resources.
- **Referrer-Policy is not automatically added with a one-size-fits-all value**; applications should set it explicitly based on risk.
- **Permissions-Policy** usually requires explicit configuration to restrict browser features.
- Defaults can change when you define a custom `SecurityFilterChain`, disable header writers, add other filters, or sit behind a proxy. **Inspect the effective response**, never rely solely on dependencies.
- Spring Security may omit its `Cache-Control` if the response already has an application-provided cache policy, allowing public static assets to be cached appropriately. This is why checking actual headers beats assuming Security “overrides everything”.
- `X-XSS-Protection: 0` is not a security bug: legacy browser XSS filters are obsolete and could introduce vulnerabilities; modern XSS defense prioritizes **output encoding, CSP, and sanitization**, not re-enabling old XSS auditors.

**Do not drop defaults just to add one header.** In the DSL, add CSP and Referrer-Policy while keeping the remaining writers, instead of calling `headers.disable()` or turning off security filters.

## 5. HSTS: Instructing Browsers to Prefer HTTPS for a Hostname

`Strict-Transport-Security` instructs browsers to remember that a hostname must only be accessed over HTTPS for a given duration, once received in a valid HTTPS context.

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Meaning:

- `max-age=31536000`: policy lifetime of one year in seconds per HSTS semantics.
- `includeSubDomains`: extends HSTS to subdomains; enable only when **every relevant subdomain** reliably supports HTTPS.
- `preload`: signals eligibility for browser preload lists; this is a domain administration commitment and **does not** automatically place a domain into every browser's preload list.

### Why Does HSTS Matter Even with HTTP→HTTPS Redirects?

When a client first visits `http://example.test`, that initial HTTP hop can be intercepted or tampered with by an attacker **before** receiving the 301/308 redirect to HTTPS. Once a browser knows HSTS or the domain is preloaded, it upgrades requests to HTTPS proactively from the start, reducing downgrade/SSL-stripping opportunities.

Yet HSTS **does not replace**:

- Valid certificates with proper hostnames/SANs and trusted CA chains.
- HTTP→HTTPS redirects for clients without an HSTS policy yet.
- Securing proxy hops when TLS terminates before the backend.
- `Secure`, `HttpOnly`, and `SameSite` cookies as needed.
- Checking mixed content/CSP, since an HTTPS page can still attempt to load insecure subresources.

### HSTS Is Ignored Over HTTP

If a server returns `Strict-Transport-Security` in a plaintext HTTP response, compliant browsers ignore it as an untrusted source for establishing HSTS. Spring Security adds HSTS only on **HTTPS requests** by default; adding a filter to force HSTS onto HTTP responses will not provide the intended protection.

### Production Rollout Strategy

Before enabling `includeSubDomains` and especially `preload`, inventory all subdomains, certificate expirations, custom ports, legacy admin ports, and legacy environments. An overly broad policy can lock out legitimate access on hosts not yet ready for HTTPS. You can roll out a short `max-age` first to validate, then increase it once all hosts are verified compatible. Browser-cached HSTS entries **cannot be instantly revoked across all clients**.

## 6. Content-Security-Policy (CSP): Restricting Resource Sources and Behavior

CSP tells browsers where scripts/styles/images/connections/frames may originate, and can restrict iframe embedding, form submissions, base URIs, and related behaviors. It helps limit XSS impact, though **it does not replace output encoding or input validation**.

Example of a relatively strict policy for a page using only same-origin resources:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

Breakdown:

| Directive | Meaning | Notes |
|---|---|---|
| `default-src 'self'` | Fallback source list for resource types governed by default-src | Does not constrain every directive automatically; some must be declared explicitly |
| `script-src 'self'` | Only loads/runs scripts from listed sources in standard scenarios | Inline scripts are blocked unless valid nonces/hashes are used |
| `object-src 'none'` | Disallows plugin-style object/embed elements | Generally good practice since legacy plugin content carries risk |
| `base-uri 'self'` | Restricts URLs in HTML `<base>` tags | Reduces unexpected relative URL hijacking |
| `frame-ancestors 'none'` | Prevents the page from being embedded in any ancestor frame | Modern clickjacking defense; not covered by default-src |
| `form-action 'self'` | Restricts form submission targets | Not a general same-origin policy for all fetches |
| `connect-src 'self'` | Restricts targets for `fetch`/WebSocket/XHR | May need allowlisting for cross-origin APIs; **does not replace CORS** |
| `img-src 'self' data:` | Restricts image sources, allowing data URLs if needed | Do not grant broader access than the app uses |
| `upgrade-insecure-requests` | Advises browsers to upgrade insecure resource URLs per CSP semantics | Does not replace TLS configuration or HSTS for the hostname |

**Every application must design CSP around its actual needs.** An SPA loading scripts from a CDN, using inline styles, and calling cross-origin APIs can break if you blindly copy `default-src 'self'`. Inventory asset endpoints, fonts, WebSockets, analytics, and third-party widgets before enabling an enforcing policy.

### Why Should You Avoid Casual Use of `unsafe-inline`?

Allowing `'unsafe-inline'` in `script-src` weakens part of CSP's XSS defense. If inline scripts are unavoidable, consider per-response CSP nonces/hashes rather than a static nonce reused across requests. Dynamic nonce-based CSP must coordinate closely with HTML rendering and caching; a static nonce provides none of the security benefits of properly managed random nonces.

### Testing with Content-Security-Policy-Report-Only

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'
~~~

Report-only mode lets you observe violations without blocking under that policy, making it suitable for migrations. A response can carry both an **enforcing CSP** and a **report-only CSP** simultaneously; the two headers do not cancel each other out. Any reporting endpoint must enforce auth/rate-limiting/privacy/retention controls since reports may contain URLs or sensitive details.

Especially for pure JSON APIs, a CSP on JSON responses **does not replace** CSP on the frontend HTML documents executing scripts. Place CSP on the **actual document responses rendered by browsers**, typically frontend HTML, and verify in a browser. A CSP on a JSON controller does not prove the UI is protected by CSP.

## 7. X-Frame-Options and frame-ancestors Against Clickjacking

**Clickjacking** tricks users into clicking real UI controls hidden or overlaid inside a frame on another page. Two basic options:

~~~http
X-Frame-Options: DENY
~~~

Browsers must not render the page in a frame. `SAMEORIGIN` permits same-origin framing per header semantics. For many admin applications, `DENY` is a safe default; Spring Security sets this value by default.

CSP `frame-ancestors 'none'` or an explicit allowlist is the modern, more flexible mechanism. Do not rely on `X-Frame-Options` for arbitrary hostname lists—the legacy header has limitations. If the app genuinely needs to be embedded in an authorized portal, configure a `frame-ancestors` allowlist and evaluate `SAMEORIGIN`/container behavior rather than disabling protection everywhere to fix one iframe.

**Do not confuse `frame-ancestors` with `frame-src`:** the former controls who may embed the *current page*, while the latter controls which frames the *current page* may load.

## 8. X-Content-Type-Options: nosniff

This header tells browsers not to guess MIME types for certain requests in ways that could create vulnerabilities from polyglot files:

~~~http
X-Content-Type-Options: nosniff
~~~

Important prerequisite: **the server must also return accurate `Content-Type` headers.** Serving JavaScript as `text/plain` with `nosniff` enabled causes browsers to refuse executing the script; that is the policy working as intended, not a random cache glitch. For user-uploaded content, avoid serving untrusted files on the same origin that holds cookies/JS privileges without isolation, accurate MIME types, `Content-Disposition`, and proper validation.

`nosniff` does not replace malware scanning, file type validation, CSP, output encoding, or origin isolation for user-generated content.

## 9. Referrer-Policy and Permissions-Policy

### Referrer-Policy

This header controls how much information from the current URL browsers may send in the `Referer` header when navigating or loading resources, depending on context.

~~~http
Referrer-Policy: no-referrer
~~~

Choose `no-referrer` when minimizing URL disclosure. In many apps, `strict-origin-when-cross-origin` offers a good balance: withholding full paths/query strings cross-origin while providing appropriate referrers same-origin. Choose based on privacy requirements and real analytics needs; never put API keys or access tokens in URL query parameters even when `no-referrer` is set.

### Permissions-Policy

This header restricts specific browser capabilities in a document/iframe, for example:

~~~http
Permissions-Policy: camera=(), microphone=(), geolocation=()
~~~

The `()` syntax disables the feature; browser support varies by feature and version. **Do not think `Permissions-Policy` grants or denies backend API authorization.** It governs browser capabilities; user consent and OS/browser permission prompts still apply via separate protocols.

When a page needs the camera to scan QR codes or geolocation for maps, do not blindly apply an all-denying policy to that page. Scope policies per route/application and iframe `allow` attributes properly while checking permissions before accessing user data.

## 10. Cache-Control: Preventing Storage of Sensitive Responses

For responses containing personal info or session-bound data:

~~~http
Cache-Control: no-store
~~~

`no-store` instructs compliant HTTP caches not to store the response, which is appropriate for sensitive data. `no-cache` **does not** forbid storing; it allows caching yet requires revalidation before reuse. `private` prevents shared caches from storing responses under standard semantics, though private browser caches may still store them if permitted.

Spring Security defaults typically include:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
~~~

These are compatibility/default headers protecting private content. However:

- Not every response holds personal data; content-hashed JS/CSS assets should usually be cached long-term as immutable.
- Controllers, static resource handlers, or proxies can set their own `Cache-Control`.
- `no-store` **does not delete data already displayed to a user**, does not prevent screen capture, logs, or browser extensions, and is not an access control.
- An error response can include a `requestId`, path info, or sensitive metadata; consider `no-store` for private API errors.
- CDNs may apply custom caching rules; verify behavior end-to-end, not just origin headers.

## 11. HTTPS: Transport Encryption Before Requests Enter Spring

### Simple TLS Flow

~~~text
Client opens https://api.example.test
  |
  | DNS + TCP + TLS ClientHello (SNI/ALPN)
  v
Server/proxy presents X.509 certificate chain
  |
  | Client checks trust chain, SAN/hostname, validity
  | Key exchange establishes protected channel
  v
Encrypted HTTP request/response
  |
  v
Spring controller and filters
~~~

HTTPS protects **each TLS hop**. If a CDN/ingress terminates TLS and forwards plaintext HTTP to Spring Boot, the client-facing hop is HTTPS while the ingress→app hop is unencrypted. That setup may be acceptable inside a trusted network with explicit policy, or internal HTTPS/mTLS may be required by security policy.

### Approach 1: TLS Termination at Ingress

~~~text
Browser --HTTPS:443--> Trusted ingress --HTTP:8080--> Spring Boot
                            |
                            +-- can set HSTS at the public edge
~~~

The application does not necessarily hold the public domain's private key. HSTS and redirect policies may live at ingress, though you must inspect headers on the **actual responses reaching browsers**—across 200, 302, and 4xx/5xx. For request schemes inside Spring, trust only forwarded headers managed by a trusted proxy.

### Approach 2: TLS Directly on the Embedded Server

~~~text
Browser --HTTPS:8443--> Embedded Tomcat / Netty
                            |
                            v
                        Spring Security
~~~

Spring Boot 3.3 supports PEM SSL bundles and key-store bundles. You can configure:

~~~properties
server.port=8443
spring.ssl.bundle.pem.webserver.keystore.certificate=classpath:tls/localhost.crt
spring.ssl.bundle.pem.webserver.keystore.private-key=classpath:tls/localhost.key
server.ssl.bundle=webserver
~~~

In the lab, the key sits on the classpath for convenience; **production must never package private keys inside JARs**. Use mounted files/secrets, least-privilege permissions, automated certificate issuance/renewal, and lifecycle management. Do not mix `server.ssl.bundle` directly with `server.ssl.key-store` or `server.ssl.certificate-private-key` properties.

## 12. HSTS and Forwarded Headers Behind a Reverse Proxy

Suppose a browser visits `https://shop.example.test` while ingress forwards to `http://internal-app:8080`. From Tomcat's socket view, the request looks like HTTP. If Spring Security is not configured to recognize trusted external HTTPS, HSTS may be omitted at the backend because the request appears insecure.

Spring Boot supports:

~~~properties
# Use ONLY when a trusted reverse proxy handles and controls headers
server.forward-headers-strategy=framework
~~~

Another option is `native` when appropriate for the web server/container. `framework` uses Spring Framework's forwarded-header filter; the right choice depends on ingress, container, and network topology. **Never blindly trust `X-Forwarded-*` headers sent directly by clients.** If an attacker can inject `X-Forwarded-Proto: https`, `X-Forwarded-Host`, or `Forwarded: host=...` and the app trusts them unchecked, it can enable URL poisoning, bad redirects, wrong cookie/security decisions, or misleading logs.

The right setup has ingress **strip/overwrite** client-supplied forwarded headers, forward only headers produced by the trusted hop, restrict the backend to accept traffic solely from ingress, and configure trusted proxies properly.

### Do Not Mix Up Redirects and HSTS

- **Redirect** `http://...` → `https://...` steers clients that start on HTTP.
- **HSTS** is a browser policy applied to future visits after receiving it over HTTPS.
- **`server.ssl.bundle`** enables Spring Boot's TLS listener when applied to the embedded server.
- **Forwarded headers** tell the backend the external scheme/host through a trusted proxy.
- **CSP** governs document resources/iframes, not TLS.
- **Secure cookies** require cookies to travel only over secure connections per browser rules, without enabling a TLS listener themselves.

Each concept is a separate piece; never treat one property as a cure-all.

## 13. The Problem of Leaking Data Through Error Responses

An error is more than a status code. Failure responses can accidentally expose:

- **Stack traces**, fully-qualified Java class names, internal packages, source file paths/line numbers.
- **SQL queries/SQLSTATE**, table/column names, JDBC URLs, hostnames, and database clusters.
- **Tokens, API keys, JWTs**, passwords, session IDs, private header values, and cookies.
- **PII**: emails, phone numbers, addresses, customer IDs, health/financial data.
- **Filesystem paths**, internal hostnames, service ports, infrastructure topology, tenant IDs.
- **Raw library exception messages**: `e.getMessage()` can embed user input, URLs, secrets, or downstream responses.
- **Full request bodies**, especially on login, upload, payment/card, or password reset endpoints.
- **Debug headers** or error pages from reverse proxies, WAFs, servlet containers, or database gateways.

Unsafe design example:

~~~java
// UNSAFE ILLUSTRATIVE CODE - DO NOT USE
@ExceptionHandler(Exception.class)
ResponseEntity<String> leak(Exception ex) {
    return ResponseEntity.internalServerError()
            .body(ex.toString() + " | " +
                  java.util.Arrays.toString(ex.getStackTrace()));
}
~~~

This code sends the exception type, message, and stack to the client. Putting `ex.getMessage()` into a `ProblemDetail`'s `detail` **can be the exact same bug**. Never convert internal exceptions into HTTP 200 with `{"success":false}` just to avoid returning 500; that breaks semantics, distorts monitoring, and misleads caches/clients.

### Designing Purpose-Built Error Responses

A client-facing error response needs:

1. **Accurate status code**: 400 bad input, 401 unauthenticated, 403 forbidden, 404 missing, 409 conflict, 429 rate limit, 500 unexpected fault, 503 dependency temporarily unavailable.
2. **Stable public message**, mentioning no secrets/SQL/implementation details. For example, “Unable to process the request at this time.”
3. **Domain error code** if clients branch on errors, such as `INVALID_QUANTITY`; never expose exception class names directly as public codes.
4. **`requestId`/`correlationId`** so operators can look up internal logs/traces.
5. **Explicit `Content-Type`**, such as `application/problem+json` per RFC 9457 when using `ProblemDetail`.
6. **Cache policy** such as `Cache-Control: no-store` when error payloads relate to a user/session.
7. **Safe logging policy**: internal logs have access control, retention, and redaction, avoiding raw secrets/PII. Never push diagnostics out to clients.

## 14. Spring Boot Error Properties: Watch Out for Debug Flags

Spring Boot 3.3 provides key properties for Servlet error handling:

~~~properties
server.error.include-message=never
server.error.include-binding-errors=never
server.error.include-stacktrace=never
server.error.include-exception=false
~~~

These align with Boot 3.3's conservative defaults, yet **explicitly declaring them in the production profile** makes intent clear to operators. Options like `on_param` or `always` can let clients trigger extra disclosure if misconfigured. In particular:

~~~properties
# Do NOT use in production for client-side debugging:
server.error.include-stacktrace=on_param
server.error.include-message=always
~~~

When stack traces or exception messages are exposed via `/error`, a single failing request or query parameter lets clients inspect internal details. Never run production with debug-oriented error flags relying on firewalls or obscurity to keep users from finding them.

### Do `server.error.*` Properties Fix Every Error?

No. These properties mainly govern how **Boot's error attributes / default error handling** output details. They **do not automatically sanitize**:

- Custom `@ExceptionHandler` methods returning `exception.getMessage()`;
- Custom Spring Security `AuthenticationEntryPoint` / `AccessDeniedHandler`;
- Errors forwarded verbatim from downstream services or REST gateways;
- Reverse proxy/gateway error pages;
- Filters writing response bodies before the error resolver runs;
- Serialization errors occurring after headers/body are committed;
- SSE, streaming uploads, or WebSocket frames.

Audit **every path that produces an error response** and test end-to-end. No single property guarantees every library stops leaking sensitive data.

### ProblemDetail and RFC 9457

Spring Framework 6.x provides `org.springframework.http.ProblemDetail` for standard HTTP error representation. Example response:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Server error",
  "status": 500,
  "detail": "Unable to process the request at this time.",
  "requestId": "random-id"
}
~~~

`title`, `status`, and `detail` have standard semantics, while `requestId` is an application-supplied extension property. `ProblemDetail` **does not strip secrets automatically** if you assign an exception message to `detail`; a clean schema with unsafe content is still dangerous.

Spring Boot 3.3 offers `spring.mvc.problemdetails.enabled` to enable Problem Details for built-in MVC exceptions. When enabling it alongside a custom `@ControllerAdvice`, understand resolver ordering so Boot's built-in handlers do not conflict with your application's handlers. The lab below constructs `ProblemDetail` explicitly for domain errors without relying on that property to convert all exceptions.

## 15. Runnable Example: Spring MVC + Spring Security + Safe Errors

We will build a lab application featuring:

- `GET /api/health` returning public 200 data.
- `GET /api/items/1` returning a public item; `/api/items/2` raising a domain-specific 404.
- `GET /api/quantity?value=0` raising a 400 without exposing raw validation/exception messages.
- `GET /api/failure` simulating an internal database error and returning a 500 `ProblemDetail` **containing no backend details**.
- Spring Security retaining default headers while adding CSP, Referrer-Policy, and Permissions-Policy.
- HTTPS enabled via an SSL bundle under profile `https` to verify HSTS over HTTPS.

**Important:** the demo sets `permitAll()` on requests to focus on header/error behavior, not production authorization. All endpoints use GET only; the demo keeps Spring Security's default CSRF enabled (never disabled). In production, every private data endpoint requires authn/authz.

### 15.1. Project Structure

~~~text
security-headers-demo/
  pom.xml
  src/main/java/example/securityheaders/SecurityHeadersApplication.java
  src/main/resources/application.properties
  src/main/resources/application-https.properties
  src/main/resources/tls/localhost.crt
  src/main/resources/tls/localhost.key
  src/test/java/example/securityheaders/SecurityHeadersTests.java
~~~

The files under `tls/` only need to be created when trying the HTTPS profile. Never commit or package production private keys the way the lab does.

### 15.2. Complete `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>security-headers-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>security-headers-demo</name>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The Spring Boot 3.3.13 Maven parent manages compatible dependency versions. The Spring Boot plugin enables running with `mvn spring-boot:run` and packaging an executable JAR. `spring-boot-starter-web` uses embedded Tomcat by default; Spring Security is activated via the starter and custom `SecurityFilterChain` in code.

### 15.3. Complete Java File

Place at `src/main/java/example/securityheaders/SecurityHeadersApplication.java`:

~~~java
package example.securityheaders;

import java.util.Map;
import java.util.NoSuchElementException;
import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;
import org.springframework.security.web.header.writers.StaticHeadersWriter;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@SpringBootApplication
public class SecurityHeadersApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityHeadersApplication.class, args);
    }

    public record Item(long id, String name) { }

    @Configuration
    static class SecurityConfiguration {
        @Bean
        SecurityFilterChain securityFilterChain(HttpSecurity http)
                throws Exception {

            // permitAll is for lab demo only: no private data here.
            // Never copy this policy into a production API.
            http.authorizeHttpRequests(auth ->
                    auth.anyRequest().permitAll());

            // Keep default security headers; only ADD policies.
            http.headers(headers -> headers
                    .contentSecurityPolicy(csp -> csp
                            .policyDirectives(
                                    "default-src 'self'; " +
                                    "script-src 'self'; " +
                                    "base-uri 'self'; " +
                                    "object-src 'none'; " +
                                    "frame-ancestors 'none'"))
                    .referrerPolicy(ref -> ref.policy(
                            ReferrerPolicyHeaderWriter
                                    .ReferrerPolicy.NO_REFERRER))
                    .addHeaderWriter(new StaticHeadersWriter(
                            "Permissions-Policy",
                            "camera=(), microphone=(), " +
                            "geolocation=()")));

            return http.build();
        }
    }

    @RestController
    static class DemoApi {
        @GetMapping("/api/health")
        public Map<String, String> health() {
            return Map.of("status", "ok");
        }

        @GetMapping("/api/items/{id}")
        public Item item(@PathVariable long id) {
            if (id != 1L) {
                throw new NoSuchElementException(
                        "Internal catalog key=" + id);
            }
            return new Item(1L, "Demo public item");
        }

        @GetMapping("/api/quantity")
        public Map<String, Integer> quantity(
                @RequestParam int value) {
            if (value < 1 || value > 100) {
                throw new IllegalArgumentException(
                        "Private business rule: value=" + value);
            }
            return Map.of("accepted", value);
        }

        @GetMapping("/api/failure")
        public Map<String, String> failure() {
            // Illustrative data ONLY inside internal exception;
            // clients must never receive this content.
            throw new IllegalStateException(
                    "INTERNAL_DB_HOST=db.private.lan");
        }
    }

    @RestControllerAdvice
    static class ApiErrors {
        private static final Logger LOG =
                LoggerFactory.getLogger(ApiErrors.class);

        @ExceptionHandler(NoSuchElementException.class)
        public ResponseEntity<ProblemDetail> notFound(
                NoSuchElementException ex) {
            return response(HttpStatus.NOT_FOUND,
                    "Resource not found",
                    "The requested resource does not exist.",
                    UUID.randomUUID().toString());
        }

        @ExceptionHandler(IllegalArgumentException.class)
        public ResponseEntity<ProblemDetail> badInput(
                IllegalArgumentException ex) {
            return response(HttpStatus.BAD_REQUEST,
                    "Invalid request",
                    "The requested value is invalid.",
                    UUID.randomUUID().toString());
        }

        @ExceptionHandler(IllegalStateException.class)
        public ResponseEntity<ProblemDetail> internalFailure(
                IllegalStateException ex) {
            String requestId = UUID.randomUUID().toString();

            // Log here does NOT record ex.getMessage(), raw headers,
            // request bodies, or secret values.
            LOG.error("Simulated internal error, requestId={}",
                    requestId);

            return response(HttpStatus.INTERNAL_SERVER_ERROR,
                    "Server error",
                    "Unable to process the request at this time.",
                    requestId);
        }

        private ResponseEntity<ProblemDetail> response(
                HttpStatus status, String title,
                String detail, String requestId) {

            ProblemDetail body =
                    ProblemDetail.forStatusAndDetail(status, detail);
            body.setTitle(title);
            body.setProperty("requestId", requestId);

            return ResponseEntity.status(status)
                    .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                    .cacheControl(CacheControl.noStore())
                    .body(body);
        }
    }
}
~~~

**Runnability notes:** this is **one complete Java file** in the matching package path, using APIs available in Spring Boot 3.3 / Spring Security 6.x and Java 17 records. The nested configuration, controller, and advice are static types picked up by Spring component scanning. No database or separate record file is needed.

### 15.4. Why Not Use `@ExceptionHandler(Exception.class)` Broadly?

A sloppy catch-all handler can turn 400, 404, type-conversion errors, method-not-allowed, or framework exceptions into 500, breaking HTTP semantics. The demo handles **three explicit exception types** to illustrate error mapping. Other exceptions fall back to default Spring MVC/Boot error handling alongside the configured `server.error.*` flags.

In large products, if you need a real catch-all, master `ResponseEntityExceptionHandler`, `ErrorResponse`, `@ControllerAdvice` ordering, and framework exception handling, preserving built-in exception statuses instead of treating everything as 500.

Why not return `ex.getMessage()`? In the demo code, exceptions intentionally contain `Internal catalog key=...`, `Private business rule: ...`, or `INTERNAL_DB_HOST=db.private.lan` to prove nothing leaks. The `detail` string is **fixed per domain error**, never copied from the throwable. `requestId` lets operators correlate responses with logs/traces without revealing stack contents.

In production apps, logs may need stack traces for debugging yet must enforce redaction, access control, retention, and a secure logging pipeline. Do not simply drop all logs out of fear of leaks: the key is **never exposing them to clients** while securing internal logs.

### 15.5. application.properties

Create `src/main/resources/application.properties`:

~~~properties
server.port=8080

# Explicitly declare Boot 3.3 error-disclosure restriction policy
server.error.include-message=never
server.error.include-binding-errors=never
server.error.include-stacktrace=never
server.error.include-exception=false

# No need to disable SSL/headers in the HTTP profile:
# default Spring Security headers are still emitted,
# except HSTS only appears on HTTPS/secure requests.
~~~

When the `https` profile is inactive, the server runs local HTTP on port 8080. Never claim an HTTP test verified HSTS/TLS. Separating the two profiles makes it clear how HSTS differs from the other headers.

### 15.6. Running Local HTTP and Testing Statuses

Inside the project directory with Maven and JDK 17:

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -i http://localhost:8080/api/health
curl -i http://localhost:8080/api/items/1
curl -i http://localhost:8080/api/items/2
curl -i "http://localhost:8080/api/quantity?value=0"
curl -i http://localhost:8080/api/failure
~~~

Expected **by semantics**:

| URL | Status | Main Body | What to Observe |
|---|---|---|---|
| `/api/health` | 200 | JSON `{"status":"ok"}` | nosniff, X-Frame-Options, CSP, Referrer-Policy, and Permissions-Policy |
| `/api/items/1` | 200 | Item JSON id 1 | No login needed only because lab uses permitAll |
| `/api/items/2` | 404 | Public ProblemDetail | Does not contain `Internal catalog key` |
| `/api/quantity?value=0` | 400 | Public ProblemDetail | Does not contain `Private business rule` |
| `/api/failure` | 500 | Public ProblemDetail | Does not contain `db.private.lan` |

Sample 500 error response (illustrative; actual ID changes):

~~~json
{
  "type": "about:blank",
  "title": "Server error",
  "status": 500,
  "detail": "Unable to process the request at this time.",
  "requestId": "6fb8a742-62d2-4b77-99ec-3e64a0c1b019"
}
~~~

Do not assert exact JSON field ordering or header ordering, as serializers/containers can vary. `requestId` is randomized per error; never use it as a secret or access token. When running under the HTTP profile, **HSTS should not be relied upon**; test the HTTPS profile in the next section.

### 15.7. Do Framework 404/400 Errors Look Identical to Advice?

Specific domain errors are mapped by `@ExceptionHandler`. However, unmapped URLs, missing request parameters, or type-conversion failures may go through default MVC/Boot error handling and not necessarily share the demo handler's JSON format. **Distinguish**:

- **Domain exceptions**: explicitly created by the app with mapped status/detail.
- **MVC framework exceptions**: mapping/argument binding/validation/content negotiation.
- **Security exceptions**: authentication/authorization filters, which may return 401/403 before the controller.
- **Container/proxy errors**: 400/413/502/503/504 generated by another layer; Advice never runs.

A consistent product error contract must deliberately standardize **all of these sources** rather than assuming one advice handles everything.

## 16. Running HTTPS with a PEM SSL Bundle

### 16.1. Generating a Self-Signed Cert for Localhost

Inside the project directory, create the folder:

~~~bash
mkdir -p src/main/resources/tls
~~~

On PowerShell, you can use `New-Item -ItemType Directory -Force src/main/resources/tls`. Requires OpenSSL 1.1.1+ with `-addext` support.

Generate a PKCS#8 private key and certificate with SAN:

~~~bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out src/main/resources/tls/localhost.key

openssl req -new -x509 -sha256 -days 7 \
  -key src/main/resources/tls/localhost.key \
  -out src/main/resources/tls/localhost.crt \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
~~~

On Windows, run commands on a single line instead of Unix line continuations or use equivalent PowerShell syntax. This self-signed certificate **is not trusted by browsers by default**; never use it as a production certificate. In the lab, the private key sits under resources for convenience, yet **never commit private key files to repositories** or distribute JARs containing real secrets.

### 16.2. application-https.properties

Create `src/main/resources/application-https.properties`:

~~~properties
server.port=8443

spring.ssl.bundle.pem.webserver.keystore.certificate=classpath:tls/localhost.crt
spring.ssl.bundle.pem.webserver.keystore.private-key=classpath:tls/localhost.key
server.ssl.bundle=webserver

# Enable HTTP/2 only when runtime/clients support it and tested separately:
# server.http2.enabled=true
~~~

Note the two layers:

- `spring.ssl.bundle.pem.webserver...` **defines the bundle** named `webserver`.
- `server.ssl.bundle=webserver` **applies the bundle** to the embedded server.

Do not mix bundles with standalone `server.ssl.key-store` / `server.ssl.certificate-private-key` in the same configuration. Spring Security headers in the example still run in the filter chain; the only difference is that requests are now HTTPS, so default HSTS can appear.

Run the HTTPS profile separately:

~~~bash
mvn -Dspring-boot.run.profiles=https spring-boot:run
~~~

When `https` is active, `application.properties` is still loaded and overridden with `server.port=8443` plus the SSL bundle. If the HTTP app is still running on 8080, you can run both simultaneously on two ports **as two separate processes**, though the simplest lab setup is stopping the HTTP process first to avoid confusion. The `https` profile **does not automatically add an HTTP 8080 → HTTPS 8443 redirect listener**; configure redirects separately at the proxy/container if desired.

### 16.3. Verifying HTTPS Without Disabling Verification

~~~bash
curl --cacert src/main/resources/tls/localhost.crt \
  -i https://localhost:8443/api/health

curl --cacert src/main/resources/tls/localhost.crt \
  -i https://localhost:8443/api/failure
~~~

Expected successful requests, status 200/500 per endpoint, security response headers, and over HTTPS `Strict-Transport-Security` when Spring Security recognizes the connection as secure. `--cacert` explicitly trusts the lab's self-signed cert; it differs from `curl -k` / `--insecure` because it does not turn off certificate verification.

To inspect the certificate SAN/chain:

~~~bash
openssl x509 -in src/main/resources/tls/localhost.crt \
  -noout -subject -issuer -dates -ext subjectAltName
~~~

To test the TLS handshake:

~~~bash
openssl s_client -connect localhost:8443 \
  -servername localhost \
  -CAfile src/main/resources/tls/localhost.crt \
  -verify_hostname localhost
~~~

Exact output varies by OpenSSL, JDK, server, and certificate; check the exit code/verification status, hostname, and connection. Never treat `curl -k` as proof that HTTPS **verified server identity**.

### 16.4. Comparing Headers Between HTTP and HTTPS

Run:

~~~bash
curl -s -D - -o /dev/null http://localhost:8080/api/health
~~~

and while running the HTTPS profile:

~~~bash
curl --cacert src/main/resources/tls/localhost.crt \
  -s -D - -o /dev/null https://localhost:8443/api/health
~~~

`-o /dev/null` is Unix syntax; on Windows you can use `curl.exe -I` for HEAD when endpoints support it appropriately, or `-o NUL`. Use `curl -i` when inspecting both status and body.

Typically you will see CSP/nosniff/frame options/referrer/permissions in both environments, while HSTS appears only on HTTPS/secure requests. Behind a proxy, test the public URL because edge vs backend headers can differ.

## 17. Integration Tests with MockMvc and Spring Security

### 17.1. Setting Up Test Dependencies

The POM in Section 15 already includes `spring-boot-starter-test` and `spring-security-test` in test scope. No manual versions are needed thanks to the Spring Boot BOM.

Create `src/test/java/example/securityheaders/SecurityHeadersTests.java`:

~~~java
package example.securityheaders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityHeadersTests {
    @Autowired
    MockMvc mvc;

    @Test
    void defaultHeadersAndCspExist() throws Exception {
        mvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"))
                .andExpect(header().string(
                        "X-Frame-Options", "DENY"))
                .andExpect(header().exists(
                        "Content-Security-Policy"))
                .andExpect(header().string(
                        "Referrer-Policy", "no-referrer"))
                .andExpect(header().exists(
                        "Permissions-Policy"));
    }

    @Test
    void hstsAppliesToSecureRequests() throws Exception {
        mvc.perform(get("/api/health").secure(true))
                .andExpect(status().isOk())
                .andExpect(header().exists(
                        "Strict-Transport-Security"));
    }

    @Test
    void internalFailureIsSanitized() throws Exception {
        mvc.perform(get("/api/failure"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.detail").value(
                        "Unable to process the request at this time."))
                .andExpect(jsonPath("$.requestId").exists())
                .andExpect(content().string(
                        not(containsString("db.private.lan"))))
                .andExpect(header().string(
                        "Cache-Control", "no-store"));
    }

    @Test
    void validationErrorIsSanitized() throws Exception {
        mvc.perform(get("/api/quantity")
                    .param("value", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string(
                        not(containsString("Private business rule"))));
    }
}
~~~

Run:

~~~bash
mvn test
~~~

`MockMvc` simulates requests inside the JVM; `secure(true)` marks the request as secure to test HSTS header writer behavior, **not a real TLS handshake**. The HSTS test here only verifies the Security filter on a secure request; you still must test the real HTTPS endpoint with `curl --cacert` to verify certificates and TLS. Behind a reverse proxy, add end-to-end tests through the real ingress.

### 17.2. Why Test Error Responses Too?

Security headers added on success responses by filters can go missing when:

- An exception is handled by a filter before/while committing the response.
- The error dispatcher generates its own body or resets the response.
- A reverse proxy emits 502/503 instead of Spring.
- A downstream API gateway overwrites `Content-Type` or caching policies.
- A custom filter sends a redirect/error directly.

Therefore, integration tests should cover **2xx, 3xx, 4xx, and 5xx** wherever possible rather than checking only `/api/health`. Verify bodies, cookies, headers, and real product error routes.

## 18. Spring Security: Authentication and Authorization Have Separate Error Paths

`@RestControllerAdvice` handles exceptions in the Spring MVC controller/resolver flow. Yet Spring Security often rejects requests **before the controller**, for example:

- **401 Unauthorized**: client unauthenticated or invalid credentials, depending on authentication scheme.
- **403 Forbidden**: authenticated without enough permission, or certain CSRF/access-denied scenarios.
- **302 redirect to login**: valid behavior for form login, though unsuitable as a contract for most REST APIs.
- **429 Too Many Requests**: may come from a rate-limit filter/gateway rather than a controller.

For REST APIs using Bearer tokens, Spring Security Resource Server provides dedicated integration for bearer authentication entry points and standard `WWW-Authenticate` headers. **Do not strip valid protocol headers** just to hide details; at the same time, never put raw exceptions, stack traces, or tokens into headers.

An **illustrative** snippet, not a standalone compiling extension:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated());
~~~

When enabling real auth, supply provider/resource-server config, token validation, and permissions. When writing custom error handlers:

- `AuthenticationEntryPoint` handles unauthenticated requests.
- `AccessDeniedHandler` handles denied authenticated requests or access-denied cases per chain.
- Controller advice handles domain/service exceptions.
- Default Boot MVC error handling covers route/binding/framework exceptions if no specific handler applies.

A catch-all `ErrorHandler` catching `Exception.class` and returning 500 cannot replace this architecture and can turn 401/403 into the wrong error. In Spring WebFlux, the equivalents are reactive `ServerAuthenticationEntryPoint` / `ServerAccessDeniedHandler` and `SecurityWebFilterChain`, not Servlet types.

## 19. WebFlux: Do Security Headers and Error Bodies Differ?

Spring Security WebFlux also provides security headers and customization via `ServerHttpSecurity` / `SecurityWebFilterChain`. Spring WebFlux supports `ProblemDetail`, `ErrorResponse`, `@RestControllerAdvice`, and reactive error handling.

Configuration snippet strictly for WebFlux apps already having `spring-boot-starter-webflux` and `spring-boot-starter-security`:

~~~java
@Bean
SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .pathMatchers("/api/public/**").permitAll()
            .anyExchange().authenticated())
        .headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(
                    "default-src 'self'; object-src 'none'")))
        .build();
}
~~~

This snippet needs imports from `org.springframework.security.config.web.server.ServerHttpSecurity`, `org.springframework.security.web.server.SecurityWebFilterChain`, `@Bean`, and an application class in a reactive project. It is **not** a complete Spring Boot app; protected endpoints still need appropriate identity/auth configuration. Never copy Servlet `SecurityFilterChain`/`HttpSecurity` classes into WebFlux expecting them to apply.

Important difference: WebFlux uses a reactive request pipeline and can return `Mono<ProblemDetail>` or `Mono<ResponseEntity<ProblemDetail>>`. Yet this **does not make error payloads safe automatically**; never publish `Throwable.toString()` or remote stack traces in the body. When an error occurs after a reactive response stream has already emitted partial data, headers/status may **already be committed**, preventing conversion into a clean 500 `ProblemDetail`. Design streaming error handling carefully and observe client disconnects.

Across both Servlet and reactive runtimes, proxies/WAFs can generate error responses outside Spring. Testing against the public ingress URL is mandatory whenever guaranteeing security headers and zero information disclosure.

## 20. Data Leaks via Logs, Traces, Headers, and Frontend UI

Sanitizing error JSON alone is insufficient if:

- **Access logs** record raw query strings containing emails or reset tokens.
- **Request logging filters** capture bodies containing passwords or card numbers.
- **Tracing spans** record `Authorization`/`Cookie` headers or full SQL with PII.
- **APM dashboards** are open to unauthorized users or keep excessive retention.
- **Proxy error pages** display upstream hostnames/IPs/stacks/nginx debug info.
- **Frontend UI** displays raw `response.text()` of a 500 error to users.
- **Debug actuator endpoints** such as `env`/`configprops`/`heapdump` are publicly exposed.
- **Support tickets** contain raw curl transcripts with JWTs/tokens, cookies, and private endpoints.

Design logs with **allowlisted fields**, secret redaction, and trace correlation IDs. Do not rely solely on find/replace patterns like `password=`, since secrets appear under many names and encodings. Access control, data classification, encryption at rest, and deletion policies are all part of the solution.

### Example Safe Frontend Error Contract

When receiving a 500 `ProblemDetail`:

~~~javascript
async function fetchItem(id) {
  const response = await fetch("/api/items/" + encodeURIComponent(id));
  if (!response.ok) {
    let requestId = null;
    try {
      const problem = await response.json();
      if (typeof problem.requestId === "string") {
        requestId = problem.requestId;
      }
    } catch (_) {
      // Errors from proxy/network may not return JSON.
    }
    throw new Error(
      "Unable to complete the request."
      + (requestId ? " Support ID: " + requestId : "")
    );
  }
  return response.json();
}
~~~

This is a JavaScript snippet for a real frontend with a matching API; it is not standalone in a browser without calling the function. It does not render raw HTML from error bodies with `innerHTML` and never displays internal stack traces or messages. For 401/403 statuses, frontends should distinguish login vs permission flows instead of turning everything into “please try again” if that breaks UX.

Never log full error responses to production consoles alongside token/user context, especially when third-party scripts or telemetry tools read console output.

## 21. Diagnosing Common Security/Header Issues

| Symptom | Possible Cause | Action |
|---|---|---|
| HTTPS works yet HSTS is missing | Header writer disabled, backend sees HTTP, proxy strips header | Compare backend vs ingress directly, check `isSecure` and trusted forwarded headers |
| HSTS on HTTP response yet browser ignores it | HSTS must arrive over valid HTTPS | Fix certificate/HTTPS; do not force header on HTTP |
| UI loses JS/CSS after enabling CSP | `script-src`/`style-src` too strict, inline scripts blocked | Inspect CSP violations, use nonces/hashes/proper allowlists |
| CSP on JSON API yet frontend still runs unsafe scripts | Policy not placed on HTML documents / relevant responses | Set CSP on rendered HTML documents and encode output |
| Page fails to load inside iframe | `X-Frame-Options: DENY` or `frame-ancestors 'none'` | Design an embed allowlist rather than disabling globally |
| JS rejected due to MIME type | `nosniff` + wrong `Content-Type` | Fix MIME type; do not remove `nosniff` just to make it run |
| Error response contains stack trace | `server.error.include-stacktrace` too broad or handler returns stack | Set `never`, fix advice/error body |
| 500 body leaks JDBC URL | `ex.getMessage()` used as `detail` | Fixed public message + `requestId`; redacted internal logs |
| API sends `no-store` yet CDN caches it | Proxy caching override, tested wrong endpoint | Check edge response and actual cache rules |
| 403 error response lacks CSP | Security entry point/filter/gateway uses different path from controller | Configure security/error handlers and test 4xx |
| User hits HTTP then redirect gets intercepted | HSTS not yet established, missing TLS policy | HTTPS, redirects, HSTS rollout/preload when ready |
| Cookies sent over wrong connection | Missing `Secure`/`HttpOnly`/`SameSite` or wrong proxy scheme | Fix cookie policy, TLS termination, and trusted forwards |
| Local HTTP test expects HSTS | Environment lacks HTTPS secure request | Test `.secure(true)` in MockMvc and real HTTPS |
| Duplicate or conflicting CSP headers | Both app and nginx/CDN write policy | Pick one owner; check browser evaluation of multiple policies |
| CORS error mistaken for CSP | Browser Console reports `connect-src` vs `Access-Control-Allow-Origin` | Read exact error and check both policies |
| HTTP 200 returned for internal errors | Exceptions swallowed, failure body with success status | Map proper 4xx/5xx rather than masking errors |

### Note on Security Headers on Error Responses

HSTS, CSP, and `X-Frame-Options` primarily govern browser response security contexts, yet not every response goes through the same filters. For instance, a 502 generated by nginx never touches Spring Security. Before claiming “all errors include headers”, test **a representative set of error cases through the public ingress**, not just MockMvc.

## 22. Decision Framework and Production Checklist

Before deploying a web-runtime API, answer:

1. **Where does TLS terminate?** Client→CDN→ingress→app, which hops use HTTPS/mTLS, who holds private keys?
2. **Are certificates valid?** CA chain, SAN, expiry, rotation, TLS versions/ciphers, private key permissions.
3. **Where is HSTS applied?** Header from trusted HTTPS responses, `max-age` rollout, `includeSubDomains`/preload prepared carefully.
4. **Who owns security headers?** Spring Security or ingress? Any duplicate/conflicting headers?
5. **Is frontend HTML CSP accurate?** Scripts/styles/fonts/APIs/WebSockets allowlisted minimally without abusing `unsafe-inline`.
6. **Are Content-Type + nosniff accurate?** Prevent untrusted user uploads from sharing a privileged origin.
7. **Is there an error response contract?** Accurate statuses, stable `ProblemDetail` or DTO, `requestId`, safe messages, `no-store` where needed.
8. **Are built-in errors covered?** Binding, invalid JSON, no handler, method mismatch, serialization failures.
9. **Are security errors covered?** 401/403/CSRF/token failures, entry points, and redirects leaking no user existence/secrets.
10. **Are proxy error pages covered?** 413/429/502/503/504, WAF blocks, timeouts, CDN caching.
11. **Have logging/tracing passed privacy review?** Redaction of Authorization/Cookies/PII/SQL secrets, access control, and retention.
12. **Are cookie/session policies right?** `Secure`, `HttpOnly`, `SameSite`, CSRF, and permissions.
13. **Do static resources have a different cache policy from private JSON?** Content-hashed/versioned assets cached appropriately; private data `no-store`.
14. **Do tests cover both HTTP and HTTPS?** HTTP covers only some headers; HSTS needs secure requests and real TLS verification.
15. **Is incident monitoring in place?** Security header drift, cert expiry, TLS failures, error rates, 401/403/5xx spikes, stack-leak regressions, and WAF events.

### A Safe Rollout Strategy

- **Development:** baseline defaults, CSP Report-Only for complex frontends, unit/integration tests for error responses.
- **Staging:** trusted HTTPS, gradually enforce CSP per real assets, verify CDN/proxy and target browsers; test bad inputs and fault injection.
- **Production:** automated certificates, mounted private key secrets, HSTS after subdomain audit, clear header ownership, log redaction, and alerts.
- **Post-release:** periodically audit headers, monitor expirations, watch policy violations, and verify 4xx/5xx responses across every layer. Update baselines as libraries and browser standards evolve.

**Do not enable HPKP (HTTP Public Key Pinning) on new systems.** It has been deprecated by major browsers and risks locking out users if key rotation goes wrong. Never treat legacy headers like `X-XSS-Protection: 1; mode=block` as modern XSS protection.

## 23. Self-Check Questions with Answers

**1. Once HTTPS is enabled, do we still need to sanitize error responses?**  
Yes. HTTPS protects data in transit, yet if the server puts stack traces/tokens/SQL in the body, the client itself still receives that sensitive data.

**2. Does Spring Security automatically add an optimal CSP for every application?**  
No. CSP depends on actual JS/CSS/API/iframe sources and must be designed and tested per application.

**3. Why does localhost HTTP show CSP and nosniff, yet no HSTS?**  
Spring Security adds HSTS only on secure/HTTPS requests by default. Even if sent over HTTP, browsers ignore HSTS headers on plaintext responses.

**4. Do HSTS and HTTP→HTTPS redirects serve the exact same purpose?**  
No. Redirects steer a single request; HSTS is remembered by the browser and enforced on future visits per policy.

**5. What does `X-Frame-Options: DENY` protect against?**  
Primarily clickjacking via framing. It does not replace authorization or a full CSP.

**6. Can `X-Content-Type-Options: nosniff` rescue a server returning wrong MIME types?**  
No. It may cause browsers to refuse loading the resource because of the wrong MIME type; fix `Content-Type` instead.

**7. Is `Cache-Control: no-cache` the same as `no-store`?**  
No. `no-cache` allows storing yet requires revalidation before use; `no-store` forbids storing under HTTP caching semantics.

**8. Is an API returning 500 with `detail=exception.getMessage()` safe if the exception came from JDBC?**  
Not by default. Exception messages can contain hosts, SQL, credentials, keys, or PII. Return a fixed public detail and `requestId`.

**9. Does `server.error.include-stacktrace=never` prevent custom advice from returning a stack trace?**  
No. That property mainly governs Boot's built-in error handling; application code must sanitize its own outputs.

**10. Does `ProblemDetail` automatically protect all sensitive fields?**  
No. It only defines a schema; field contents populated by the app must be checked explicitly.

**11. Will a 401 error from Spring Security definitely reach `@RestControllerAdvice`?**  
No. Security filters can reject before the controller, using dedicated `AuthenticationEntryPoint`/`AccessDeniedHandler`.

**12. After TLS terminates at nginx, does Spring automatically know the original request was HTTPS?**  
Not necessarily. You need trusted forwarded headers/appropriate container configuration or HSTS emitted at the edge.

**13. Why should clients not be allowed to control `X-Forwarded-Proto`?**  
Because it allows spoofing external schemes/hosts, causing bad redirects and security decisions. Trust only controlled proxies.

**14. Does `Referrer-Policy: no-referrer` prevent the app from logging tokens in URLs?**  
No. It governs the `Referer` header sent by browsers in certain contexts; logging still must be controlled separately.

**15. Are CSP `frame-ancestors` and `frame-src` the same?**  
No. `frame-ancestors` controls who can embed the current page; `frame-src` controls which frames the current page can load.

**16. Does MockMvc `secure(true)` verify the certificate chain like curl HTTPS?**  
No. It only simulates a secure request to test header logic; real TLS handshakes are required to verify certificates.

**17. If a proxy returns 502 with a stack trace, is fixing `@ExceptionHandler` enough?**  
No. That response was generated by the proxy; fix proxy error pages/logging/security headers at that layer.

**18. Why is testing 2xx responses insufficient?**  
4xx/5xx/redirect flows can take different code paths, leak data, or drop headers.

**19. Should you enable `includeSubDomains` and `preload` immediately when moving a site to HTTPS?**  
Not hastily. Audit all subdomains, certificates, infrastructure, and rollback feasibility first, since cached HSTS cannot be immediately cleared.

**20. If an application uses pure JSON `@RestController` endpoints, does CSP replace CORS or CSRF?**  
No. CSP mainly governs browser document resource behavior; CORS governs cross-origin response reads and CSRF protects mutations that could use auto-sent credentials.

## 24. Official References

- [Spring Security – Default Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/features/exploits/headers.html): default headers, HSTS over HTTPS only, no default CSP, protections, and `X-XSS-Protection`.
- [Spring Security – Servlet Security Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): Java DSL for Cache-Control, HSTS, CSP, Referrer-Policy, Frame Options, and custom header writers.
- [Spring Security – Reactive Security Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html): corresponding configurations in WebFlux.
- [Spring Boot 3.3 – Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `server.error.include-*`, `server.forward-headers-strategy`, TLS, and web server settings.
- [Spring Boot 3.3 – Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): SSL bundles and running behind a front-end proxy.
- [Spring Boot 3.3 – SSL](https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html): PEM SSL bundles and TLS lifecycle.
- [Spring Framework – Error Responses in MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse`, `ResponseEntityExceptionHandler`, and exception handling.
- [Spring Framework – Error Responses in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html): equivalent error response contracts on the reactive stack.
- [OWASP – HTTP Security Response Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html): designing security headers and avoiding pitfalls.
- [OWASP – Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html): preventing information disclosure and unsafe logging.
- [MDN – Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP): CSP directives, nonces/hashes, report-only.
- [MDN – HTTP Strict Transport Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security): HSTS policy and differences from redirects.
- [RFC 6797 – HTTP Strict Transport Security](https://www.rfc-editor.org/rfc/rfc6797): HSTS semantics.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): statuses, headers, and HTTP semantics.
- [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): current standard for problem details.