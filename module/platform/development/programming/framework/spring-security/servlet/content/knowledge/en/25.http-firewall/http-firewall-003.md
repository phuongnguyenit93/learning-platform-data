# HttpFirewall: Allowed HTTP Methods, Headers, Hostnames, and Conditions in Spring Security Servlet

## 1. Which HTTP Boundary Does HttpFirewall Protect?

In a Spring Security **Servlet** application, a request contains more than just a path. It also carries an **HTTP method**, headers, hostname, query string, parameters, and numerous URL representations that can introduce ambiguity. When two components in the system interpret the same request differently, an attacker can exploit that discrepancy to bypass routing rules, permission checks, or data validation.

Spring Security's **`HttpFirewall`** is the request-control checkpoint at the HTTP layer before security filters and `RequestMatcher`s handle the request normally. The standard implementation is **`StrictHttpFirewall`**. The firewall can reject requests that fail its conditions or provide a `FirewalledRequest` so downstream components observe the request more consistently.

For example, the system expects only `GET`, `POST`, and a few standard methods, yet a client sends `TRACE` or an arbitrary method; or the host received by the application is not among the expected public hosts. The firewall can block such requests right at the HTTP boundary.

Do not conflate control layers:

- **`HttpFirewall`**: decides whether a request is sufficiently valid at the HTTP level and satisfies firewall conditions such as method, header names/values, hostname, and URL.
- **`SecurityFilterChain` / `authorizeHttpRequests`**: authenticates and decides who has permission to access a valid URL/method.
- **Spring MVC mapping**: maps method/URL to a controller, potentially returning `405 Method Not Allowed` if no matching handler exists.
- **Web server, reverse proxy, servlet container**: may reject malformed requests before they ever reach Spring Security.
- **Controller/service**: validates business data and per-resource permissions.

A request that **passes the firewall** is not automatically authenticated, authorized, or safe in payload content. Conversely, a request rejected by the firewall may never reach the controller or authorization layer.

## 2. Processing Flow and Configuration Placement

In a standard Servlet setup, Spring Security's `FilterChainProxy` uses an `HttpFirewall` before applying the appropriate security filters. `StrictHttpFirewall` is used by default in common Spring Security configurations; if an application replaces the firewall with another implementation, you must inspect that specific implementation.

~~~text
Client
  │ HTTP request: method + path + Host + headers + body
  ▼
Web server / reverse proxy / Servlet container
  │ may reject malformed requests first
  ▼
Spring Security FilterChainProxy
  │
  ├─ HttpFirewall / StrictHttpFirewall
  │    ├─ is method allowed?
  │    ├─ is URL/path rejected for dangerous representations?
  │    └─ do hostname, header, parameter satisfy predicates?
  │
  ├─ If no: RequestRejectedException → rejection handler
  │
  └─ If yes: FirewalledRequest → SecurityFilterChain
                                   │
                                   └─ authentication → authorization → MVC/controller
~~~

The diagram is a conceptual model: some header/parameter checks execute **when code accesses that data through the wrapped request**, rather than necessarily scanning everything upfront on receipt. Therefore, when testing custom header predicates, you must ensure the application actually reads the header or iterates header names.

Do not configure `StrictHttpFirewall` via `http.headers(...)`: that configures **security headers sent in responses**, whereas `setAllowedHttpMethods`, `setAllowedHeaderNames`, `setAllowedHeaderValues`, and `setAllowedHostnames` govern **incoming requests**.

## 3. Allowed HTTP Method Conditions

### 3.1. StrictHttpFirewall Default Allowlist

By default, `StrictHttpFirewall` restricts requests to the following standard methods (matching method names):

| Allowed by Default | Typical HTTP Meaning |
| --- | --- |
| `GET` | Read a resource; should have no side effects |
| `HEAD` | Same metadata as GET, no response body |
| `OPTIONS` | Query resource capabilities; used for CORS preflight |
| `POST` | Submit data or perform an action |
| `PUT` | Create/replace resource state per API contract |
| `PATCH` | Partial update |
| `DELETE` | Delete a resource |

Methods such as `TRACE`, `TRACK`, `CONNECT`, and WebDAV `PROPFIND` are not in the default set. A request rejected by firewall policy may trigger `RequestRejectedException` before reaching the controller. Servers or proxies sometimes block methods earlier, so the observed HTTP status depends on where the block occurs.

Example:

~~~http
TRACE /api/orders HTTP/1.1
Host: api.example.test
~~~

Even if the application has no controller for `TRACE`, eliminating unwanted methods right at the firewall is useful. However, **allowing a method** does not create an endpoint: having `PUT` in the default firewall does not mean `PUT /api/orders` exists or is authorized.

### 3.2. When Should You Change the List?

Expand the allowlist only when the system genuinely needs a non-standard method—for example, a WebDAV application intentionally supporting `PROPFIND`. Evaluate support across the proxy, container, CORS, routing, Spring Security method authorization, and controllers; adding a method to the firewall **does not automatically satisfy** those layers.

If an API is read-only, you can narrow the allowlist, but be careful not to drop `HEAD` and `OPTIONS` if clients, health checks, or CORS preflight rely on them. Passing `OPTIONS` through the firewall does not automatically allow all origins: CORS must be configured separately.

`StrictHttpFirewall#setAllowedHttpMethods(List<String>)` lets you configure an application-specific list. Avoid `setUnsafeAllowAnyHttpMethod(true)` just to make one non-standard request "work": doing so removes the built-in method restriction and fails to address other configuration causes.

### 3.3. Distinguishing Three Sequential Decisions

| Scenario | Deciding Layer | Example Outcome |
| --- | --- | --- |
| Client sends `TRACE` not accepted by firewall | Firewall | Rejected before controller; often mapped to a 400-style error response |
| Client sends valid `PATCH` with no PATCH mapping | MVC/router | Usually `405 Method Not Allowed` |
| Client sends valid `DELETE`, controller exists, insufficient permission | Authorization | Usually `403 Forbidden`, or `401` if unauthenticated, depending on config |
| Client sends valid session-backed `POST` missing CSRF token | CSRF filter | Usually `403 Forbidden` |
| Client sends valid `GET` and is authorized | Multiple layers pass | Controller executes; outcome depends on business logic |

Do not use the firewall as a substitute for `@PreAuthorize`, `authorizeHttpRequests`, CSRF, or business validation.

## 4. Header Name and Header Value Conditions

HTTP requests can carry many headers: `Host`, `Authorization`, `Accept`, `Content-Type`, `Cookie`, `Origin`, `X-CSRF-TOKEN`, `User-Agent`, trace headers, `Forwarded`, and `Sec-Fetch-*`. Header names are **case-insensitive** in HTTP semantics: `authorization` and `Authorization` refer to the same field.

Spring Security exposes customizable predicates on `StrictHttpFirewall`:

- **`setAllowedHeaderNames(Predicate<String>)`**: returns `true` if the header name is accepted; `false` if it must be rejected.
- **`setAllowedHeaderValues(Predicate<String>)`**: returns `true` if the header value is accepted; `false` if it must be rejected.

Both are conditions applied to the request wrapped by the firewall. They do not define required request headers, do not guarantee headers are unspoofed, and do not replace business parsing/validation.

### 4.1. Designing a Header Name Predicate

Suppose an internal application mandates never accepting an `X-Internal-Override` header from clients. Illustrative predicate:

~~~java
firewall.setAllowedHeaderNames(name ->
    name != null
        && !name.equalsIgnoreCase("X-Internal-Override"));
~~~

This is a **firewall configuration excerpt**, not a standalone Java file. The forbidden header name is rejected when the firewall inspects that header. Using `equalsIgnoreCase` avoids blocking only `X-Internal-Override` while missing `x-internal-override`.

Do not create a tiny allowlist of two or three familiar headers and assume every request will work: browsers, proxies, load balancers, OAuth2, CSRF, observability, and HTTP/2 may require other headers. If you use a strict allowlist, inventory legitimate traffic across environments before deploying, and add tests so you do not accidentally break login, preflight, or tracing.

In particular, never treat the mere presence of a custom header as trustworthy proof of authority: clients can send arbitrary headers. Access rights must rely on authentication and authorization, while reverse-proxy-generated headers must be handled via a **trusted proxy** model.

### 4.2. Designing a Header Value Predicate

Header values should not contain dangerous control characters such as CR/LF under modern HTTP policy; request splitting/header injection is typically already partially mitigated by servers and containers. An illustrative predicate might be:

~~~java
firewall.setAllowedHeaderValues(value ->
    value != null
        && value.indexOf('\r') < 0
        && value.indexOf('\n') < 0);
~~~

This snippet expresses an application condition; it **does not guarantee prevention of every form of header injection**. The system still needs controls when generating response headers, proxy forwarding, parsers, and other encodings. Overly strict character or length rules can break `Authorization`, tokens, filenames, `User-Agent`, or valid metadata.

**Important testing note:** header checks may be triggered when code invokes `getHeader(...)`, `getHeaders(...)`, or `getHeaderNames()` on the firewall-wrapped request. A request carrying a disallowed header that the controller/framework **never reads** might not produce the rejection signal you expect. Write tests that exercise header access, or add explicit validation at the proxy/application layer if policy must be enforced on **every header immediately upon request arrival**.

### 4.3. A Valid Header Can Still Be Untrusted Data

For example, `X-Forwarded-Host: admin.example.test` passing a character-level predicate does not mean its content is trustworthy. For proxy-owned headers, configure the proxy to **strip/overwrite client-supplied values** and allow the application to trust headers only from verified proxies. Never let clients declare themselves as coming through a trusted gateway/host.

Similarly, an `Authorization` header whose characters pass the firewall does not necessarily carry valid credentials; authentication filters must verify the signature/token, issuer, audience, expiry, or secret.

## 5. Allowed Hostname Conditions

### 5.1. What Host Does the Firewall See?

`StrictHttpFirewall#setAllowedHostnames(Predicate<String>)` sets a condition on the hostname seen by the application via the request (per `HttpServletRequest#getServerName()`). If `getServerName()` returns a value rejected by the predicate, the firewall can reject the request.

In public-facing systems, the host is part of the routing boundary: requests can arrive at an IP or reverse proxy with an unexpected `Host` header. If an application uses the host to build password-reset links, redirects, callback URLs, or tenant routing, an untrusted host can lead to vulnerabilities such as **Host header injection** and URL poisoning.

**The default is not your application's domain list.** Configure a hostname allowlist matching your architecture and also verify virtual-host selection rules at the reverse proxy/web server.

Example policy logic: accept only `api.example.test` in production and `localhost` in dev/test environments. Avoid naive `endsWith("example.test")` matching: `attackerexample.test` also ends with that string. For subdomains, enforce dot boundaries, canonicalization, and an explicit subdomain management policy.

### 5.2. With Load Balancers, Reverse Proxies, or Forwarded Headers

The relationship between the client-sent `Host` header, `X-Forwarded-Host`/`Forwarded`, and `getServerName()` depends on the servlet container, proxy, and forwarded-header filters. An application behind a gateway may see an **internal hostname** instead of the public hostname, or a host normalized by a filter. Therefore:

1. Determine which `Host` actually reaches the server and what `getServerName()` Spring Security observes.
2. At the **trusted reverse proxy**, reject hosts outside the permitted domain list and strip/overwrite externally supplied forwarded headers.
3. Configure header forwarding only from trusted hops, then set a hostname allowlist matching the check point inside the application.
4. Test access via the real domain, internal health checks, local/test setups, and spoofed hosts; never relax the allowlist to `.*` merely because proxy settings are not properly configured yet.

Using `setAllowedHostnames` is a helpful request guard; it is not a DNS resolver, does not control outbound/SSRF requests, does not prove the hostname was TLS-authenticated, and does not single-handedly defeat all forwarded-header spoofing techniques.

## 6. Complete Configuration for Spring Security Servlet (Java 17+, Security 6+)

The example is the configuration class **`FirewallConfig.java`** in a Spring Boot 3.x project with `spring-boot-starter-security` and Spring Web. It is invoked by the Spring container, **not a standalone Java program with `main()` to run via `javac FirewallConfig.java`**.

~~~java
package com.example.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;
import org.springframework.security.web.firewall.HttpFirewall;
import org.springframework.security.web.firewall.StrictHttpFirewall;

@Configuration
public class FirewallConfig {

    @Bean
    HttpFirewall httpFirewall() {
        StrictHttpFirewall firewall = new StrictHttpFirewall();

        // Methods the API actually intends to accept.
        // Keep OPTIONS if browser CORS preflight is used.
        firewall.setAllowedHttpMethods(List.of(
            "GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"
        ));

        // Production may need only one public hostname.
        // localhost is only for illustrating dev/test environments.
        firewall.setAllowedHostnames(host ->
            host != null
                && (host.equalsIgnoreCase("api.example.test")
                    || host.equalsIgnoreCase("localhost")));

        // Illustrates an additional header-name policy.
        // Ordinary headers are still permitted by this predicate.
        firewall.setAllowedHeaderNames(name ->
            name != null
                && !name.equalsIgnoreCase("X-Internal-Override"));

        // Illustrates value validation; the container/proxy still needs
        // independent HTTP syntax and normalization policies.
        firewall.setAllowedHeaderValues(value ->
            value != null
                && value.indexOf('\r') < 0
                && value.indexOf('\n') < 0);

        return firewall;
    }

    @Bean
    WebSecurityCustomizer webSecurityCustomizer(HttpFirewall firewall) {
        return web -> web.httpFirewall(firewall);
    }
}
~~~

**Explanation of each choice:**

- `new StrictHttpFirewall()` retains the other strict path/URL checks of `StrictHttpFirewall`; the example adjusts only the policies relevant to this topic.
- `setAllowedHttpMethods(...)` uses the default set for illustration so you see the accepted conditions. An application can narrow it if genuinely needed.
- `setAllowedHostnames(...)` restricts hosts to an illustrative set; substitute domains for your real environment rather than copying `api.example.test` verbatim into production.
- `setAllowedHeaderNames(...)` and `setAllowedHeaderValues(...)` illustrate predicates. They are **not a complete HTTP allowlist for every system**. Tune them to your protocol and business requirements.
- `WebSecurityCustomizer` attaches the firewall directly to `WebSecurity`. Declaring only a `StrictHttpFirewall` bean without confirming the system uses it can cause confusion in some setups; this snippet wires it explicitly.
- If the application already defines a `WebSecurityCustomizer`, merge configurations cleanly to avoid overrides or overlapping logic. When multiple `SecurityFilterChain`s share `FilterChainProxy`, the firewall applies at the proxy boundary before chain selection.

For most applications, `StrictHttpFirewall`'s default configuration combined with a well-configured proxy/container provides a solid baseline. Add custom predicates only when there is a specific requirement and a test suite demonstrating they block the unwanted traffic.

### 6.1. SecurityFilterChain Example Distinguishing Firewall From Authorization

The snippet below can live in a separate Security configuration class in the same project; it illustrates only the **authorization** layer:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
        .anyRequest().authenticated());
    return http.build();
}
~~~

The corresponding imports are `org.springframework.context.annotation.Bean`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.http.HttpMethod`, and `org.springframework.security.web.SecurityFilterChain`. This snippet **does not compile standalone unless placed in a class with imports**; it emphasizes that permitting `GET` at the firewall and making a URL public are two separate decisions. Other methods accepted by the firewall must still pass the chain's authentication/authorization/CSRF checks.

### 6.2. URL Conditions Still Apply Even Though This Lesson Focuses on Method/Header/Hostname

`StrictHttpFirewall` also enforces strict rules on ambiguous URL/path representations such as semicolons, control characters, dangerous encoded characters, and unnormalized paths. Do not enable `setAllow...` flags wholesale just to "fix" URL errors. Usually you should fix the frontend/client to send canonical URLs and identify the exact rejection reason; relax a single rule only if a legitimate requirement exists and after assessing request smuggling/path matching risks.

A URL with a valid path **can still be blocked due to method or hostname**, and a request with a valid method/host **can still be blocked due to URL**. Predicates do not replace one another.

## 7. Testing: Method, Header, Hostname, and Processing Layers

### 7.1. Direct Unit Tests on StrictHttpFirewall

The following **JUnit 5** example lives at `src/test/java/com/example/security/FirewallConfigTest.java` in a project with `spring-boot-starter-test` and `spring-security-test`. It invokes the firewall configuration directly without starting a web server. Class/package names match `FirewallConfig.java` in Section 6.

~~~java
package com.example.security;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.firewall.HttpFirewall;
import org.springframework.security.web.firewall.RequestRejectedException;

class FirewallConfigTest {
    private final HttpFirewall firewall =
        new FirewallConfig().httpFirewall();

    private MockHttpServletRequest request(
        String method, String host) {
        MockHttpServletRequest request =
            new MockHttpServletRequest(method, "/api/example");
        request.setServerName(host);
        return request;
    }

    @Test
    void acceptsExpectedMethodAndHost() {
        assertDoesNotThrow(() ->
            firewall.getFirewalledRequest(
                request("GET", "api.example.test")));
    }

    @Test
    void rejectsUnexpectedMethod() {
        assertThrows(RequestRejectedException.class, () ->
            firewall.getFirewalledRequest(
                request("TRACE", "api.example.test")));
    }

    @Test
    void rejectsUnexpectedHost() {
        assertThrows(RequestRejectedException.class, () ->
            firewall.getFirewalledRequest(
                request("GET", "untrusted.example.test")));
    }
}
~~~

Because this is a **unit test with Spring dependencies**, it does not run on bare JDK alone. With Maven/Gradle and a properly configured sample project, run `./mvnw test` or `./gradlew test` (on Windows use `mvnw.cmd test` / `gradlew.bat test`). The three tests are designed to pass when the Section 6 configuration is applied; exact test runner output depends on the build tool and environment, so no stdout is fabricated here.

**Testing headers** requires remembering that validation may trigger when code calls accessors on the wrapped request. You can build a `MockHttpServletRequest` with a disallowed header, obtain the `FirewalledRequest` via `firewall.getFirewalledRequest(...)`, and call `getHeaderNames()`/`getHeader(...)` matching real code paths. Do not simply add a header to a MockMvc request and assume every header is always eagerly scanned by the firewall. Integration tests confirm how the container, filter chain, and application actually consume headers.

### 7.2. Real HTTP Checks With curl and Browser

Assuming the app is running at `localhost:8080`, the proxy forwards `Host: api.example.test` to the test instance, and endpoint `/api/example` exists:

~~~bash
# Normal method/host request:
curl -i -H "Host: api.example.test" \
  http://localhost:8080/api/example

# Method outside default allowlist:
curl -i -X TRACE -H "Host: api.example.test" \
  http://localhost:8080/api/example

# Host failing the illustrative allowlist:
curl -i -H "Host: untrusted.example.test" \
  http://localhost:8080/api/example
~~~

These commands are **illustrative test scenarios only**, with no fixed stdout or HTTP status because no specific environment/proxy/controller is provided. For instance, `TRACE` may be blocked at the web server before reaching the firewall. The host check might be rejected earlier by a virtual-host router, or a `ForwardedHeaderFilter` might alter `serverName`. Use controlled logs and integration tests to pinpoint which layer blocked the request.

With browsers, remember to test `OPTIONS` preflight for cross-origin SPAs if CORS is enabled; do not strip `OPTIONS` from the allowlist when browsers need it. The actual request HTTP method, the host observed by the servlet, and headers forwarded by the proxy are the values to inspect.

### 7.3. Handling Expectations for Rejected Requests

Spring Security uses `RequestRejectedException` for requests rejected by the firewall. In many modern configurations, `RequestRejectedHandler` translates these into **HTTP 400 Bad Request** error responses; observed behavior may differ if a server, proxy, container, or custom handler returns its own code.

A firewall-rejected request is **not equivalent** to `401` (unauthenticated), `403` (forbidden/CSRF), or `405` (MVC method not mapped). During debugging, locate the rejection point and ensure abnormal requests do not become 500 responses or expose detailed stack traces to clients.

Logging should capture enough reason and request classification for investigation, while **never logging full Authorization/Cookie values or sensitive data**; log rate-limiting can also prevent malicious requests from flooding logs.

## 8. Common Design and Configuration Mistakes

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| CORS preflight blocked after setting method allowlist | Dropped `OPTIONS` from the list | Re-evaluate policy, keep OPTIONS if browsers need it, and configure CORS properly |
| WebDAV `PROPFIND` rejected | Method is not in the default set | Add PROPFIND only if genuinely supported; test proxy, security, and MVC |
| Requests with unexpected Host rejected after production deploy | Proxy forwards internal host or domain differs from test | Check `request.getServerName` at the right layer; adjust trusted proxy and allowlist |
| Unwanted Host still gets through gateway | Gateway fails to enforce Host or forwarded headers from internet | Filter at proxy and configure trusted hops; app allowlist acts as defense in depth |
| Browser login, CSRF, or tracing breaks after tightening header names | Predicate too narrow, blocking Cookie/Origin/Authorization/trace headers | Inventory legitimate traffic, test end-to-end, and adjust predicate |
| Strange header added yet request is not blocked | Header accessor never invoked by code; or header stripped by proxy | Test the actual header access path and request-receiving layer |
| PUT allowed at firewall yet API returns 403 or 405 | Authorization, CSRF, or MVC blocked independently | Inspect each layer in order with its corresponding status/logs |
| App uses `setUnsafeAllowAnyHttpMethod(true)` to "fix" error | Loosened the entire policy instead of fixing one requirement | Revert to the minimal method allowlist required by business logic |
| Using `http.headers(...)` to control request headers | Confused response security headers with request firewall predicates | Configure `HttpFirewall`/`WebSecurityCustomizer` at the proper layer |
| Testing Spring only on localhost, skipping proxy | Production Host and headers differ | Test real paths through LB/CDN, error paths, and preflight |

### Deployment Checklist

- [ ] Confirm the system uses `StrictHttpFirewall` and know where it attaches to `FilterChainProxy`/`WebSecurity`.
- [ ] Enumerate actually required methods; do not open `TRACE`/`CONNECT`/exotic methods without valid justification.
- [ ] Retain `OPTIONS` when browsers need CORS preflight; manage CORS separately.
- [ ] Constrain header names/values per real requirements without accidentally breaking valid headers or treating custom headers as authorization proof.
- [ ] Trust forwarded headers only from controlled reverse proxies; verify `getServerName()` and Host allowlist.
- [ ] Test invalid methods, spoofed hosts, invalid headers, malformed URLs, and valid requests via **both** unit tests and real proxy/container.
- [ ] Observe and handle `RequestRejectedException` cleanly without logging sensitive credentials.
- [ ] Preserve authentication, authorization, CSRF, MVC validation, and upload/URL policies; they are independent layers from the firewall.

**Key takeaway:** `StrictHttpFirewall` checks **whether an HTTP request is acceptable for further processing**; `setAllowedHttpMethods` defines the method list, `setAllowedHeaderNames/Values` define header predicates, and `setAllowedHostnames` defines the predicate for the servlet-observed hostname. Customizations at this boundary must reflect real clients, proxies, and application needs; passing the firewall is only the first gate, never an authorization grant.
