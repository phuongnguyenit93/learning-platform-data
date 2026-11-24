# Spring MVC — CorsFilter, allowed origins, credentials, and wildcard restrictions

## 1. Objectives and real-world problem

An application has a frontend running at `https://app.example.com`, a Spring MVC API at `https://api.example.com`, and an admin UI at `https://admin.example.com`. These are **different origins**. Browsers enforce the *same-origin policy* and only allow JavaScript to read responses from a cross-origin API if the API declares appropriate CORS permissions.

A common configuration mistake is enabling:

~~~java
configuration.addAllowedOrigin("*");
configuration.setAllowCredentials(true);
~~~

This is **invalid** in Spring Framework 6.2: when credentials are allowed, `allowedOrigins` must not contain `"*"` because browsers reject combining `Access-Control-Allow-Origin: *` with a credentialed CORS response. Spring validates the configuration and rejects that combination. Switching to a broad pattern like `allowedOriginPatterns("*")` may make the configuration technically valid yet **still dangerous as a policy**: nearly any website gets its origin echoed so JavaScript can read credentialed data if cookie and browser conditions permit.

This lesson helps you:

- Distinguish `CorsFilter`, `CorsConfiguration`, `CorsConfigurationSource`, `UrlBasedCorsConfigurationSource`, and `DefaultCorsProcessor`.
- Understand **allowed origins** precisely by scheme/host/port; distinguish `allowedOrigins` from `allowedOriginPatterns`.
- Know when to use `allowCredentials(true)` and the requirements for `Access-Control-Allow-Origin` / `Access-Control-Allow-Credentials`, cookies, and `fetch(credentials: "include")`.
- Explain the differences among wildcards in **origins**, **origin patterns**, **allowed methods**, **allowed headers**, and **exposed headers**.
- Configure CORS at the Servlet filter boundary, integrate properly with Spring Security, and avoid overlapping configurations.
- Practice with Spring Boot 3.5.0, Java 17, `CorsFilter`, explicit allowlists, and testing preflight/actual requests with MockMvc and a browser.
- Identify false CORS errors caused by HTTP 401/403/500, blocked preflights, unsent cookies, proxies/CDNs, and wrong response headers.

**Scope:** Spring Framework 6.2, Spring MVC **Servlet stack**, HTTP(S) origins, and modern browsers. For Spring WebFlux, the corresponding type is `CorsWebFilter` — do not mistakenly use the servlet `CorsFilter`.

## 2. Revisiting CORS at the Servlet Filter processing boundary

An HTTP(S) **Origin** is the triple of scheme + hostname + effective port. A page at `https://app.example.com` calling `https://api.example.com` is cross-origin; changing the path on the same scheme/host/port does not create a different origin. `http://localhost:5173` and `http://localhost:8080` are different origins even on the same host.

**What is new in this lesson is the processing location:** the browser enforces the Same-Origin Policy and checks CORS responses, whereas `CorsFilter` runs in the **server-side Servlet filter chain, before the MVC controller** when registered and ordered accordingly. The filter selects a `CorsConfiguration` for the request, checks preflight or actual requests, and can terminate the request before any handler runs. It does not by itself grant identity, business permissions, or a CSRF token.

For example, the browser sends `Origin: https://app.example.com` to `/api/orders`. If the policy allows it, the CORS response can carry `Access-Control-Allow-Origin: https://app.example.com` with `Vary: Origin`; if not, the frontend cannot read the body under the CORS mechanism, even if the actual HTTP request reached the server. **A valid set of response headers does not prove authentication/authorization is valid**.

The previous lesson explained origin and preflight syntax; the sections below focus on `CorsFilter`/`CorsConfigurationSource`, wildcards with credentials, filter ordering, and risks of overly broad policies. For standalone reading, just remember that `curl` does not enforce browser CORS limits, and same-site cookies **do not mean** same-origin.

## 3. Where does CORS preflight happen?

A cross-origin JavaScript request may **not require OPTIONS** yet still need the actual response to be permitted by CORS.

For example, a GET using only safelisted headers:

~~~javascript
fetch("https://api.example.com/api/status");
~~~

Usually the browser sends GET directly (no preflight). The response still needs an appropriate ACAO for JavaScript to read it.

Conversely, a JSON POST:

~~~javascript
fetch("https://api.example.com/api/orders", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({productId: 10, quantity: 2})
});
~~~

is typically checked by the browser with a preflight first:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
~~~

If the configuration permits it:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type
Access-Control-Max-Age: 1800
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

then the browser can send the actual POST next. The method in `Access-Control-Request-Method` is **the method of the actual request**, not OPTIONS. Therefore `allowedMethods` normally declares GET/POST/PUT that the client needs to execute; **there is no need to add OPTIONS just because preflight uses OPTIONS**.

Some conditions that typically trigger preflight:

| Script-initiated request | Typical preflight |
| --- | --- |
| GET without custom request headers | No |
| POST `application/x-www-form-urlencoded` with safelisted headers | No |
| POST `multipart/form-data` under safelisted conditions | No |
| POST `application/json` | Yes |
| PUT/PATCH/DELETE | Yes |
| GET with `Authorization` | Yes |
| GET adding `X-API-Key` or `X-Request-ID` | Yes |
| POST with custom header `X-Tenant-ID` | Yes |

Safelisted rules also include header value/length limits and special cases per Fetch/browsers; the table above covers common scenarios, not the full standard algorithm.

**If preflight fails**, the browser usually **does not send the actual request**. If GET has no preflight yet the response lacks ACAO, the server may have already processed the request and only reading the response is blocked. Distinguish these two cases when debugging.

## 4. CorsFilter in the Spring Servlet stack

`org.springframework.web.filter.CorsFilter` is Spring Framework's servlet filter; it can run before `DispatcherServlet` and before handlers/controllers execute, depending on registration order. It uses a `CorsConfigurationSource` to pick the configuration for a request, then uses a `CorsProcessor` (defaulting to `DefaultCorsProcessor`) to handle the CORS protocol.

Model:

~~~text
Browser
  |
  v
Servlet Filter Chain
  |
  +-- CorsFilter
  |     |
  |     +-- CorsConfigurationSource -> selects policy by request URL
  |     |
  |     +-- CorsProcessor -> checks Origin, method, requested headers
  |           |
  |           +-- valid preflight: writes CORS headers and ends OPTIONS
  |           +-- invalid: rejects, does not proceed to controller
  |           +-- valid actual request: adds CORS headers, continues chain
  |
  +-- Security filters (if integrated/ordered properly)
  |
  v
DispatcherServlet -> Controller -> Service
  |
  v
HTTP response
~~~

### 4.1. Classes and responsibilities

| Component | Role | Example |
| --- | --- | --- |
| `CorsFilter` | Servlet filter performing CORS processing in the filter chain | Bean/filter registration |
| `CorsConfiguration` | Policy data: origins, methods, headers, credentials, maxAge | `config.setAllowedOrigins(...)` |
| `CorsConfigurationSource` | Selects a `CorsConfiguration` for each request | Custom source or URL mapping |
| `UrlBasedCorsConfigurationSource` | Maps URL patterns to CORS policies | `registerCorsConfiguration("/api/**", config)` |
| `CorsProcessor` | Algorithm that evaluates CORS requests and writes headers | `DefaultCorsProcessor` |
| `WebMvcConfigurer#addCorsMappings` | Configures CORS on MVC handler mappings | Does not necessarily create a separate CorsFilter |
| `@CrossOrigin` | Configures CORS at controller/method level | Endpoint scope |
| `http.cors(...)` | Spring Security integrates CORS processing in the filter chain | Used when Security is enabled |

**You do not need to implement an `OPTIONS` endpoint on each controller** just to answer preflight if filter/MVC CORS processing is configured properly. Opening all OPTIONS requests to "fix CORS errors" is no substitute for an origin/method/header policy.

### 4.2. What happens to an actual request without an Origin?

An ordinary HTTP request without an `Origin` header may not require CORS processing: the filter lets the request pass without blocking on origin. For instance, `curl http://localhost:8080/api/status` still receives an HTTP response even if the CORS policy has a narrow allowlist. This is expected behavior: server authorization must be checked **separately**.

When an `Origin` is present and not permitted by policy, `DefaultCorsProcessor` usually rejects the CORS request (e.g., HTTP 403). Test the actual behavior of your version and filter setup, and never treat Origin as an authentication credential.

### 4.3. Filter vs. CORS on HandlerMapping

Spring MVC CORS can also be defined on `HandlerMapping` via `@CrossOrigin` and `WebMvcConfigurer#addCorsMappings`. However, if the Spring Security filter chain blocks preflight before the request reaches MVC, policies placed on handler mappings may not be applied in time. `CorsFilter` or Security CORS integration handles it earlier.

**Choose one primary place to manage the policy**, instead of simultaneously registering a `CorsFilter`, calling `http.cors(...)`, and adding multiple `@CrossOrigin("*")` annotations without controlling how they combine. Overlapping configurations can create duplicate ACAO headers, wrong responses, or unintended permissions.

## 5. allowedOrigins: exact origin list

`CorsConfiguration#setAllowedOrigins(...)` is used when you know the permitted frontend origins:

~~~java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of(
        "https://app.example.com",
        "https://admin.example.com",
        "http://localhost:5173"
));
~~~

**Origin consists of scheme + host + port**. `http://localhost:5173` does not automatically include `http://localhost:3000`. Likewise `https://example.com` does not automatically allow `https://app.example.com`.

### 5.1. Valid and invalid allowed origins

| Configuration value | Interpretation |
| --- | --- |
| `https://app.example.com` | Allows the exact app origin |
| `http://localhost:5173` | Allows local dev frontend on exact port |
| `https://app.example.com:8443` | Allows exact HTTPS host and port 8443 |
| `*` | Wildcard origin when policy does not use credentialed mode |
| `https://*.example.com` in **allowedOrigins** | **Not** hostname wildcard syntax like `allowedOriginPatterns` |
| `https://app.example.com/path` | Conceptual error: origins have no path |
| `https://app.example.com, https://admin.example.com` in one HTTP ACAO header | Not a valid multi-origin ACAO format |

Spring may accept a comma-separated configuration string in `setAllowedOrigins(...)`, which is convenient when resolving property placeholders. However, **the HTTP `Access-Control-Allow-Origin` header should only express a single selected origin or `*`**, not a CSV list.

### 5.2. Do not use hand-rolled prefix, contains, or suffix checks

Counter-example:

~~~java
// Not a safe way to check origin.
if (origin.startsWith("https://app.example.com")) {
    response.setHeader("Access-Control-Allow-Origin", origin);
}
~~~

The value `https://app.example.com.attacker.test` also starts with the prefix above yet is a different host. Similar bugs happen with `contains("example.com")`, poorly anchored regexes, or comparing domains while ignoring scheme/port.

Use Spring `CorsConfiguration` with **exact origins** or security-reviewed patterns. For multi-tenant or dynamic trusted origins, require an explicit approval policy, verify identity/ownership of registered origins, and prevent attackers from registering an origin to read sensitive data of another tenant.

### 5.3. Default deny and applyPermitDefaultValues

A fresh `new CorsConfiguration()` instance **allows no origins by default**; you must configure it. However:

~~~java
cors.applyPermitDefaultValues();
~~~

applies a fairly permissive set of defaults to unset fields: origin `*`, methods GET/HEAD/POST, allowed headers `*`, max age 1800 seconds. For sensitive APIs, **do not call this method without understanding its defaults**; configure each field explicitly per your needs.

## 6. allowedOriginPatterns: conditional hostname/port wildcards

Spring provides:

~~~java
cors.setAllowedOriginPatterns(List.of(
        "https://*.example.com",
        "http://localhost:[5173,3000]"
));
~~~

`allowedOriginPatterns` supports hostname and port patterns. Examples from Spring Framework 6.2 Javadoc:

~~~text
https://*.example.com
https://*.example.com:[8080,8081]
https://*.example.com:[*]
~~~

Note that `http://localhost:[5173,3000]` is appropriate only if all those dev origins are permitted; do not use `:[*]` in production if you want to restrict ports. Verify the actual policy by exact scheme/host/port and allow/deny test suites.

### 6.1. Why does allowedOriginPatterns work with credentials?

When a request Origin matches a pattern, Spring returns:

~~~http
Access-Control-Allow-Origin: https://tenant-a.example.com
~~~

instead of returning the wildcard pattern `https://*.example.com` or `*`. Thus `allowedOriginPatterns` can be combined with `allowCredentials(true)` at the API level.

However, that only solves the **ACAO format**, not **origin trustworthiness**. If an attacker controls `evil.example.com`, the pattern `https://*.example.com` can still allow the attacker's origin if it matches. That can enable reading credentialed responses in a user's browser, depending on cookies and other controls.

### 6.2. How dangerous is allowedOriginPatterns("*")?

~~~java
cors.setAllowedOriginPatterns(List.of("*"));
cors.setAllowCredentials(true);
~~~

This configuration can pass the wildcard check applied to `allowedOrigins("*")`, because Spring **echoes the actual matched origin** into ACAO. Yet in practice it opens **credentialed CORS** to arbitrary unknown origins, an especially severe risk if the API uses cookie sessions.

**Conclusion:** "Spring accepts the syntax" does not mean "it is safe." For user data, prefer explicit allowlists, tenant domain controls, and tests for malicious origins.

### 6.3. Wildcards should not replace a trust policy

Often-overlooked risks:

- Outsiders may register subdomains within an organization via subdomain-creating services.
- DNS takeover can turn an old subdomain into an attacker-controlled host.
- Preview deployment environments have dynamic URLs and are not trusted origins for production data.
- A wildcard may admit both HTTPS/HTTP origins or many ports if the pattern is not tightly constrained.
- Domains with Unicode/punycode/uppercase/special ports make manual string comparison error-prone.

When dynamic per-tenant origins are required, maintain a curated allowlist and normalize origins strictly; never use `allowedOriginPatterns("*")` to avoid maintaining a list.

## 7. Credentials: cookies, authentication, and the browser

`CorsConfiguration#setAllowCredentials(true)` controls whether the CORS response permits the browser to expose the result of a request using credentials.

Frontend example:

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
  credentials: "include"
});
const me = await response.json();
~~~

The server typically needs:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

**Do not** use:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

The browser will not let script read a credentialed response. Spring's `CorsConfiguration#validateAllowCredentials()` checks the corresponding wildcard origin rule.

### 7.1. CORS credentials are not login

Enabling `allowCredentials(true)` **does not authenticate a user**, does not set cookies, and does not grant an external page access to an API if backend authorization denies it. It is only one part of the browser's response-sharing mechanism.

You still need:

- Authentication (session, JWT, OIDC, etc.) and authorization checking permissions per user/resource/tenant.
- CSRF protection if the browser uses cookie/session auth for state-changing operations.
- Appropriate cookie policies: `Secure`, `HttpOnly`, `SameSite`, Domain, and Path.
- TLS/HTTPS in production.
- A sufficiently narrow and reviewed CORS allowlist.

### 7.2. Will cookies actually be sent?

`fetch(..., {credentials:"include"})` only **allows** the browser to send eligible cookies under qualifying conditions. Whether cookies are actually sent still depends on domain/path, Secure, SameSite, third-party cookie blocking/partitioning, and browser policies.

| Scenario | Key point |
| --- | --- |
| `app.example.com` calls `api.example.com` | Cross-origin, usually same-site if schemes match |
| `app.example.com` calls `api.other.test` | Cross-origin and cross-site |
| Cookie `SameSite=Lax` | Not automatically sent in cross-site fetch |
| Cookie `SameSite=None; Secure` | Usually required for certain cross-site cookie flows, still subject to browser policies |
| Fetch's default `credentials: "same-origin"` | Does not automatically send credentials to another origin |
| `credentials: "include"` | Allows sending credentials per browser cookie rules |

Valid CORS headers while cookies are not sent result in a backend 401; the console may report a CORS error if the 401 response lacks valid CORS headers. You must debug **cookie transmission**, **server authorization**, and **CORS responses** together.

### 7.3. Cookie session + CORS does not prevent CSRF

Cross-origin form submissions or requests requiring no preflight can still trigger state-changing operations if the server relies on cookies without CSRF protection. CORS mainly governs **permission to read responses**, not CSRF defense.

Do not disable CSRF for all POSTs just because an SPA frontend calls the API. With cookie/session authentication, use CSRF tokens and proper cookie policies; if the application uses bearer tokens in frontend-controlled headers, the CSRF surface differs yet still requires design analysis.

### 7.4. Preflight does not require an authenticated session

CORS preflight normally does not carry the actual request's cookies. If the security filter chain requires login immediately on OPTIONS, preflight gets 401/403 before any controller runs and the actual POST is never sent.

Therefore **CORS processing must run before security authentication checks**. Spring Security supports this out of the box when you provide a `CorsConfigurationSource` and enable `http.cors(...)`. Never solve this by stripping authentication policies or opening all OPTIONS endpoints indiscriminately.

## 8. Wildcards in methods, headers, and exposedHeaders

The `*` symbol across different properties **does not mean the same thing**.

| Property | Example | Meaning | Recommendation |
| --- | --- | --- | --- |
| `allowedOrigins` | `*` | Allows any origin; forbidden with credentials=true | Public non-credentialed resources if genuinely meant to be public |
| `allowedOriginPatterns` | `https://*.example.com` | Matches origins by hostname/port pattern | Only if every matching host is trusted |
| `allowedOriginPatterns` | `*` | Very broad origin-matching pattern that can echo origins | Do not use for cookie-based private APIs |
| `allowedMethods` | `GET,POST` | Actual methods permitted for CORS | List only methods actually needed |
| `allowedMethods` | `*` | Spring may reflect the requested method in preflight, especially in credentials mode | Avoid if high-risk methods exist |
| `allowedHeaders` | `Content-Type,Authorization` | Script is allowed to send these request headers | Explicit allowlist |
| `allowedHeaders` | `*` | May reflect requested headers per Spring handling in credentials mode | Do not open unconditionally |
| `exposedHeaders` | `X-Request-ID` | Lets JavaScript read non-safelisted response headers | Expose only needed headers |
| `exposedHeaders` | `*` | Has spec/browser caveats when credentials are enabled | List explicitly for portability |
| `maxAge` | `1800` | Preflight cache lifetime (seconds); browsers may cap it | Use when policy is relatively stable |

**Spring subtlety:** with `allowedMethods("*")` or `allowedHeaders("*")` and credentials enabled, Spring may write the specific requested method/headers into the preflight response instead of literal `*`. With `exposedHeaders("*")`, Spring Framework may still emit literal `*` even when credentials are enabled due to when response headers are built. However, given CORS/Fetch semantics and browser differences, do not rely on wildcard expose in credentialed flows; list explicit header names.

Do not mistake `allowedHeaders` for an **authorization field allowlist**: it only controls which request headers the browser may send; the backend must still validate content, tokens, scopes, and business permissions.

### 8.1. Explicit configuration is safer

~~~java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of("https://app.example.com"));
cors.setAllowedMethods(List.of("GET", "POST"));
cors.setAllowedHeaders(List.of("Content-Type", "Authorization", "X-Request-ID"));
cors.setExposedHeaders(List.of("X-Request-ID", "Location"));
cors.setAllowCredentials(true);
cors.setMaxAge(1800L);
cors.validateAllowCredentials();
~~~

Here `allowCredentials(true)` can be appropriate if you genuinely need cookie credentials and the origin is verified as trusted. For public/cookieless APIs, set `allowCredentials(false)` or leave it disabled.

### 8.2. allowPrivateNetwork and private network access

Spring Framework 6.2 provides `setAllowPrivateNetwork(...)` for user agents that enforce rules restricting access to private/local networks. This is an **additional policy area**, not a general flag for fixing all localhost issues. Spring has separate validation preventing unsafe combinations with `allowedOrigins("*")` when private-network permission is enabled.

If a public origin needs to call an API on a private network, analyze SSRF-like browser pivots, origin trustworthiness, browser support, and the threat model. Never add `allowPrivateNetwork(true)` alongside wildcards just to make preflight pass.

## 9. CorsFilter and URL-based configuration

A pure Java configuration:

~~~java
import java.util.List;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.filter.CorsFilter;

CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of("https://app.example.com"));
cors.setAllowedMethods(List.of("GET", "POST"));
cors.setAllowedHeaders(List.of("Content-Type", "Authorization"));
cors.setAllowCredentials(true);
cors.setMaxAge(1800L);

UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
source.registerCorsConfiguration("/api/**", cors);

CorsFilter corsFilter = new CorsFilter(source);
~~~

This snippet is an **illustrative fragment** constructing the objects; if exposed as a `@Bean` in a Spring Boot servlet app, the filter is registered in the filter chain according to the corresponding configuration.

### 9.1. Why restrict URL paths?

An application may have:

~~~text
/api/public/**
/api/account/**
/api/admin/**
/actuator/**
/internal/**
~~~

Do not apply the same wildcard policy to all of them. For example:

- Public APIs can allow a few non-credentialed origins.
- Session-based account APIs need explicit trusted origins and a credentials policy.
- Admin APIs need a strict allowlist, authentication/authorization, and CSRF policy.
- Internal actuator/admin endpoints should not inherit CORS from `/**` by default.
- Internal endpoints usually do not need to be readable by arbitrary browser origins.

When using `UrlBasedCorsConfigurationSource`, you can register **different path patterns** with different configurations. Ensure proper ordering/specificity and pattern matching; test matching URLs and out-of-scope URLs. If a proxy rewrites paths, compare the policy against the actual path the backend sees.

### 9.2. Do you need FilterRegistrationBean?

Spring Boot servlet automatically registers a `Filter` bean as a Servlet filter. When you have specific ordering, dispatcher types, or URL pattern requirements, you can use `FilterRegistrationBean<CorsFilter>` **instead of** letting a CorsFilter bean auto-register uncontrollably.

Illustrative example:

~~~java
@Bean
FilterRegistrationBean<CorsFilter> corsRegistration(
        UrlBasedCorsConfigurationSource source) {
    FilterRegistrationBean<CorsFilter> reg =
            new FilterRegistrationBean<>(new CorsFilter(source));
    reg.setOrder(Ordered.HIGHEST_PRECEDENCE);
    reg.addUrlPatterns("/api/*");
    return reg;
}
~~~

Requires imports `org.springframework.boot.web.servlet.FilterRegistrationBean`, `org.springframework.core.Ordered`, `org.springframework.context.annotation.Bean`. If you choose this approach, avoid registering **another `CorsFilter` bean** that would run twice; register a single appropriate path and test request filter order.

### 9.3. Do not overlook ERROR/ASYNC dispatches

`CorsFilter` inherits `OncePerRequestFilter` behavior. Depending on filter registration and Servlet dispatch type, behavior on `REQUEST`, `ASYNC`, and `ERROR` can differ. If a 500 response is handled on an ERROR dispatch and ACAO is missing, the browser may only show a CORS error instead of the error body. When async/streaming/security/proxies are involved, write integration tests on an embedded server to verify CORS headers are still safely applied.

Do not randomly add ACAO manually in multiple places (filter, error handler, reverse proxy) because responses may end up with duplicate or incompatible headers.

## 10. Three CORS integration strategies in Spring Boot

### 10.1. Spring MVC only (no Spring Security)

For a straightforward Servlet MVC application, you can choose:

- `@CrossOrigin` on controller/method; or
- `WebMvcConfigurer#addCorsMappings` for URL groups; or
- `CorsFilter` with `UrlBasedCorsConfigurationSource` when you want CORS handled at the servlet filter boundary.

All are valid depending on your needs. However, if you are practicing `CorsFilter`, implement one clear filter and focus on testing its policy rather than configuring all three simultaneously.

### 10.2. With Spring Security: prefer Security CORS integration

Spring Security recommends providing a `UrlBasedCorsConfigurationSource` bean and enabling CORS integration so CORS is processed before security checks requiring authentication:

~~~java
@Configuration
class SecurityCorsConfiguration {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of(
                "Content-Type", "Authorization", "X-CSRF-TOKEN"));
        cors.setExposedHeaders(List.of("X-Request-ID"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/**").authenticated()
                        .anyRequest().permitAll())
                .build();
    }
}
~~~

Required imports:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
~~~

This fragment is an **independent alternative**; do not add it alongside the runnable `CorsFilter` configuration in section 11. It requires the `spring-boot-starter-security` dependency, authentication config, and an appropriate CSRF token flow if using cookie sessions. Do not copy this snippet as a complete production security setup.

Crucially: **do not register both a global `CorsFilter` bean and a separate `http.cors(...)` configuration** without understanding their ordering and responsibilities. Use one authoritative `CorsConfigurationSource`, test preflight inside the security filter chain, verify 401/403 carry CORS headers, and avoid widening CORS casually.

### 10.3. When a gateway handles CORS

A gateway/CDN can handle preflight and ACAO before requests reach Spring. If the gateway is the primary owner of CORS, the backend must align with that policy and avoid emitting duplicate ACAOs. Still, the backend requires its own authentication/authorization; never treat the gateway's ACAO as a signal that the user is trusted.

Test the entire request path from browser through gateway to backend, especially when the gateway returns 502/503/504 or the app returns 401/403, since those responses also need consistent CORS headers if the frontend is allowed to read error details.

## 11. Runnable project: CorsFilter, credentials, and origin allowlist

Demo application:

- Spring Boot 3.5.0, Java 17+, Maven.
- Backend running at `http://localhost:8080`.
- Demo frontend running at `http://localhost:5173`; also allows origin `https://app.example.com`.
- Only `/api/**` URLs receive this CORS policy.
- No `@CrossOrigin` or `WebMvcConfigurer#addCorsMappings` to avoid double configuration.
- `allowCredentials(true)` enabled to demonstrate ACAO with an **exact origin** and `Access-Control-Allow-Credentials: true`. **The demo has no login/cookies**, so this does not turn the API into an authenticated application; see the security notes below.
- Includes GET `/api/hello`, JSON POST `/api/echo`, custom response header `X-Request-ID`, and tests.

### 11.1. Structure

~~~text
cors-filter-demo/
├── pom.xml
├── src/
│   ├── main/java/demo/CorsFilterApplication.java
│   └── test/java/demo/CorsFilterApiTest.java
└── web-client/
    └── index.html
~~~

### 11.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>cors-filter-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
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
            <artifactId>spring-boot-starter-test</artifactId>
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

### 11.3. CorsFilterApplication.java

Save all Java code below into `src/main/java/demo/CorsFilterApplication.java`. Only one top-level class is public; the remaining classes/records are package-private, so Java permits placing them in the same file.

~~~java
package demo;

import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.filter.CorsFilter;

@SpringBootApplication
public class CorsFilterApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsFilterApplication.class, args);
    }
}

@Configuration
class CorsFilterConfig {
    @Bean
    CorsFilter corsFilter() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of(
                "http://localhost:5173",
                "https://app.example.com"
        ));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of(
                "Content-Type",
                "Authorization",
                "X-Request-ID"
        ));
        cors.setExposedHeaders(List.of("X-Request-ID", "Location"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        // Fail fast on invalid wildcard origins + credentials combination.
        cors.validateAllowCredentials();

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return new CorsFilter(source);
    }
}

record EchoRequest(String message) {
}

record EchoResponse(String echo) {
}

@RestController
@RequestMapping("/api")
class DemoApiController {
    @GetMapping(path = "/hello",
                produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Map<String, String>> hello() {
        return ResponseEntity.ok()
                .header("X-Request-ID", UUID.randomUUID().toString())
                .body(Map.of("message", "Hello from Spring MVC"));
    }

    @PostMapping(path = "/echo",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<EchoResponse> echo(
            @RequestBody EchoRequest request) {
        return ResponseEntity.ok()
                .header("X-Request-ID", UUID.randomUUID().toString())
                .body(new EchoResponse("Echo: " + request.message()));
    }
}
~~~

**Why is it configured this way?**

- `CorsFilter` is a bean that Spring Boot auto-registers in the servlet environment; you do not have to write an `OPTIONS` controller yourself.
- `UrlBasedCorsConfigurationSource` applies the policy only to `/api/**`, not automatically to Actuator/admin/internal endpoints.
- `setAllowedOrigins(...)` contains **two exact origins**, with no wildcards.
- `allowCredentials(true)` makes responses require ACAO with a specific matched origin, plus `Access-Control-Allow-Credentials: true`.
- `setAllowedMethods(List.of("GET","POST"))` suffices for actual GET/POST; the preflight method OPTIONS does not need to be added to the list.
- `setAllowedHeaders` allows JSON Content-Type and two request headers if the frontend needs them; it does not open `*`.
- `setExposedHeaders` lets browser JavaScript read `X-Request-ID` or `Location` when present on the response.
- `maxAge=1800` lets the browser cache preflight up to browser limits.
- `validateAllowCredentials()` catches invalid configurations early. If origins are replaced with `*` while keeping credentials true, the app should fail to start with that policy.

**Important:** The demo sets `allowCredentials(true)` to observe CORS response semantics, yet the API has **no login or private data**. When deploying real APIs, enable credentials only if origins are verified as trusted and authentication/authorization/CSRF/cookie policies are completely designed.

### 11.4. Test frontend web-client/index.html

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>CorsFilter demo</title>
</head>
<body>
  <h1>Test CORS credentials + allowlist</h1>
  <button id="get">GET /api/hello</button>
  <button id="post">POST JSON /api/echo</button>
  <pre id="result"></pre>
  <script>
    const base = "http://localhost:8080";
    const output = document.querySelector("#result");

    async function request(path, options = {}) {
      try {
        const response = await fetch(base + path, {
          credentials: "include",
          ...options
        });
        const requestId = response.headers.get("X-Request-ID");
        const body = await response.json();
        output.textContent = JSON.stringify({
          httpStatus: response.status,
          requestId,
          body
        }, null, 2);
      } catch (error) {
        output.textContent =
          "Cannot read response: " + error.message
          + ". Check DevTools Network/Console.";
      }
    }

    document.querySelector("#get").onclick = () =>
      request("/api/hello");

    document.querySelector("#post").onclick = () =>
      request("/api/echo", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({message: "Hello"})
      });
  </script>
</body>
</html>
~~~

Although `credentials: "include"` is declared, the demo does not create cookies or sessions. Therefore you are checking **whether the CORS response permits credentials mode**, not testing real login yet. If integrating cookie sessions later, account for `SameSite`, CSRF tokens, browser third-party cookie policies, and Spring Security.

### 11.5. Running

Terminal 1 in the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Terminal 2:

~~~bash
python -m http.server 5173 --directory web-client
~~~

Open in a browser:

~~~text
http://localhost:5173
~~~

In DevTools/Network:

1. GET /api/hello normally sends an actual GET without preflight when there are no custom request headers.
2. POST JSON /api/echo normally sends an OPTIONS preflight before the actual POST.
3. Returned headers contain exact ACAO `http://localhost:5173`, ACAC true, and `Access-Control-Expose-Headers` for X-Request-ID.
4. Moving the frontend to another port (e.g., 5174) without updating allowed origins causes cross-origin scripts from there to be rejected.

Equivalent GET response:

~~~json
{"message":"Hello from Spring MVC"}
~~~

Equivalent POST response:

~~~json
{"echo":"Echo: Hello"}
~~~

The `X-Request-ID` UUID changes on each actual API request. Preflight responses are handled by the filter before the controller and thus do not carry controller-generated `X-Request-ID`; this is expected demo behavior.

### 11.6. Curl: distinguishing actual and preflight

Actual request from a trusted origin:

~~~bash
curl -i 'http://localhost:8080/api/hello' \
  -H 'Origin: http://localhost:5173'
~~~

Typical headers:

~~~http
HTTP/1.1 200
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
Access-Control-Expose-Headers: X-Request-ID, Location
Vary: Origin
Content-Type: application/json
~~~

JSON POST preflight:

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/echo' \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
~~~

A successful preflight may return:

~~~http
HTTP/1.1 200
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
~~~

Commas, casing, and header ordering may vary depending on Spring/container; do not compare raw HTTP text to verify policy correctness.

Using an origin not on the allowlist:

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/echo' \
  -H 'Origin: https://evil.example' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
~~~

Spring Framework 6.2's `DefaultCorsProcessor` typically returns **403 Invalid CORS request**. The browser will not send the actual POST if preflight is rejected. Yet `curl` still prints the HTTP response despite no ACAO because curl does not enforce SOP.

### 11.7. MockMvc tests for allowlist, credentials, and wildcard limits

File `src/test/java/demo/CorsFilterApiTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.cors.CorsConfiguration;

import java.util.List;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsFilterApiTest {
    @Autowired
    MockMvc mvc;

    @Test
    void trustedOriginCanReadActualResponseWithCredentials() throws Exception {
        mvc.perform(get("/api/hello")
                .header("Origin", "http://localhost:5173"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    "Access-Control-Allow-Origin", "http://localhost:5173"))
            .andExpect(header().string(
                    "Access-Control-Allow-Credentials", "true"))
            .andExpect(header().string(
                    "Access-Control-Expose-Headers",
                    containsString("X-Request-ID")))
            .andExpect(jsonPath("$.message").value("Hello from Spring MVC"));
    }

    @Test
    void secondExactTrustedOriginIsAllowed() throws Exception {
        mvc.perform(get("/api/hello")
                .header("Origin", "https://app.example.com"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    "Access-Control-Allow-Origin", "https://app.example.com"));
    }

    @Test
    void requestsWithoutOriginStillWork() throws Exception {
        mvc.perform(get("/api/hello"))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(
                    "Access-Control-Allow-Origin"));
    }

    @Test
    void approvedJsonPostPreflightDoesNotRunController()
            throws Exception {
        mvc.perform(options("/api/echo")
                .header("Origin", "http://localhost:5173")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers", "content-type"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    "Access-Control-Allow-Origin", "http://localhost:5173"))
            .andExpect(header().string(
                    "Access-Control-Allow-Methods", containsString("POST")))
            .andExpect(header().string(
                    "Access-Control-Allow-Headers",
                    containsString("content-type")))
            .andExpect(header().string(
                    "Access-Control-Allow-Credentials", "true"));
    }

    @Test
    void unknownOriginPreflightIsRejected() throws Exception {
        mvc.perform(options("/api/echo")
                .header("Origin", "https://evil.example")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers", "content-type"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                    "Access-Control-Allow-Origin"));
    }

    @Test
    void unapprovedMethodIsRejected() throws Exception {
        mvc.perform(options("/api/hello")
                .header("Origin", "http://localhost:5173")
                .header("Access-Control-Request-Method", "DELETE"))
            .andExpect(status().isForbidden());
    }

    @Test
    void unapprovedHeaderIsRejected() throws Exception {
        mvc.perform(options("/api/echo")
                .header("Origin", "http://localhost:5173")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers", "X-Private-Admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    void wildcardOriginCannotBeCombinedWithCredentials() {
        CorsConfiguration invalid = new CorsConfiguration();
        invalid.setAllowedOrigins(List.of("*"));
        invalid.setAllowCredentials(true);
        assertThrows(IllegalArgumentException.class,
                invalid::validateAllowCredentials);
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The tests verify allowed origins, rejected origins, allowed methods/headers, and wildcard configuration validation. Preflight tests confirm the CORS protocol executes before the actual controller flow; the controller only has GET and POST, so there is no business OPTIONS handler.

**Limitations:** MockMvc does not replace a browser when testing actual cookie policies, third-party cookie restrictions, CSRF/authentication filters, and gateways. For production verification, add embedded-server/browser E2E tests with cookies and Spring Security.

## 12. Using allowedOriginPatterns in practice

Suppose all subdomains of `trusted.example.com` are genuinely controlled by the same organization:

~~~java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOriginPatterns(List.of(
        "https://*.trusted.example.com"
));
cors.setAllowedMethods(List.of("GET"));
cors.setAllowedHeaders(List.of("Authorization"));
cors.setAllowCredentials(true);
~~~

Spring returns ACAO set to the **matched request Origin**. This can fit internal hosts owned by the organization, but only after evaluating domain takeover, tenant isolation, and cookies.

### 12.1. Testing patterns directly

Use `CorsConfiguration#checkOrigin` to verify:

~~~java
CorsConfiguration config = new CorsConfiguration();
config.setAllowedOriginPatterns(List.of(
        "https://*.trusted.example.com"));
config.setAllowCredentials(true);

String matched =
        config.checkOrigin("https://team.trusted.example.com");
String rejected =
        config.checkOrigin("https://attacker.example");
~~~

Here `matched` is typically the concrete origin value, while `rejected == null`. This is a **fragment** inside a class/method with appropriate Java imports, not a standalone program. If business policy requires exact hosts, still prefer `setAllowedOrigins` over patterns.

### 12.2. Do not misuse allowOriginPatterns with allowCredentials=false

Some developers switch to `allowedOriginPatterns` merely to dodge wildcard validation errors even when the API does not need credentials. If the API is genuinely a public non-credentialed resource, `allowedOrigins("*")` can be an intentional choice; if the API is private, use explicit origins aligned with your trust boundary. Do not use complex patterns simply because "Spring supports them."

### 12.3. Multiple trusted origins

An API serving separate user and admin frontends:

~~~java
cors.setAllowedOrigins(List.of(
        "https://app.example.com",
        "https://admin.example.com"
));
~~~

Spring evaluates the incoming `Origin` and responds with **one matched origin**, not an ACAO header containing a CSV string of both origins. When responses vary by origin, `Vary: Origin` is needed so CDNs/proxies do not cache the wrong ACAO.

Specifically, if the admin page has separate authentication/authorization, including the admin origin in the allowlist still does not grant regular users permission to read admin data.

## 13. Debugging CORS and common configuration errors

| Symptom | Possible cause | Verification step |
| --- | --- | --- |
| "CORS policy blocked", Network shows 200 | Actual response missing/wrong ACAO | Compare Origin and ACAO, status/body |
| OPTIONS returns 401/403 and no POST follows | CORS filter runs after Security or allowlist is wrong | Filter order, `http.cors(...)`, preflight headers |
| Error enabling `allowCredentials(true)` with origin `*` | Invalid wildcard configuration | Use exact origins or vetted patterns |
| Browser rejects wildcard ACAO with cookies | ACAO `*` + credentialed fetch | Return matched origin + ACAC true |
| HTTP 200 yet JS cannot read `X-Request-ID` | Missing `Access-Control-Expose-Headers` | Expose the required header |
| GET works, JSON POST fails | POST uses preflight, config lacks POST/Content-Type | Inspect OPTIONS preflight |
| GET from local 5173 works, local 5174 fails | Different origin due to port | Add exact trusted dev origin if needed |
| CORS valid yet /api/me returns 401 | Cookie/token not sent or invalid | Credentials mode, SameSite, auth logs |
| CORS error when backend throws 500 exception | Error response lacks ACAO or proxy returns error | Check backend error handling/gateway |
| Intermittent CORS behind CDN | CDN caches ACAO for wrong origin | Check `Vary: Origin` and cache policy |
| Two different ACAO headers present | Gateway + app or multiple filters adding headers | Pick one place to own CORS |
| Preflight fails when sending X-API-Key | Header not in allowedHeaders | Review policy and add needed header |
| Security still blocks POST after preflight OK | Actual request needs auth/CSRF | Do not confuse preflight approval with authorization |
| `Origin: null` blocked | Opaque origin not allowed | Use a dev HTTP server instead of file:// |
| Curl reads data while JS fails | Curl does not enforce SOP/CORS | Test in browser/DevTools |

### 13.1. Recommended debugging order

1. Determine exact `window.location.origin` on the frontend and the API URL.
2. Distinguish whether the request involves OPTIONS or not.
3. If OPTIONS exists, inspect preflight `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`.
4. Verify the server returns appropriate ACAO/ACAM/ACAH/ACAC; with credentials, ACAO must be a specific origin.
5. If the actual request reached the server, check HTTP status, backend logs, and response ACAO. A backend 500 is not "merely a CORS error."
6. Check fetch credentials mode and cookie policy if sessions are used.
7. Check `/api/**` URL path matching and whether multiple CORS configurations exist.
8. If Security is enabled, ensure CORS processing runs before preflight authentication; then still check authorization/CSRF on the actual request.
9. If behind a proxy/CDN, check whether headers are stripped/duplicated and cached properly by Origin.
10. Verify with MockMvc/embedded server and a browser, not only with curl/Postman.

### 13.2. Avoid mode:"no-cors"

Counter-example:

~~~javascript
fetch("https://api.example.com/private", {
  mode: "no-cors"
});
~~~

This **does not grant permission to read JSON**. The browser normally returns an **opaque response** to script, preventing reading body/status like a regular API response. Never treat this as a fix for server configuration.

### 13.3. Do not disable browser security for development

Launching Chrome/Firefox with flags disabling web security hides policy mistakes and exposes your browsing session to risk. Use a dev proxy or configure CORS properly for the frontend origin instead.

## 14. Security review for credentialed CORS

For cookie-based APIs, ask yourself:

- **Which exact origins** does CORS allow? Who controls DNS/domains for each origin?
- Are there any tenant/user-created subdomains? Any dangling DNS or uncontrolled preview domains?
- Are cookies needed cross-site, and does the browser actually send them?
- How are CSRF tokens sent/validated? Are state-mutating API endpoints protected?
- Do 401/403/500 errors carry valid CORS headers for trusted origins without leaking sensitive details?
- Is there a separate policy for admin/internal endpoints?
- Does the trust scope of wildcard hostname patterns exceed the security boundary?
- Can third-party scripts on an allowed frontend origin read user-specific API data? CORS trusts the **origin**, without distinguishing individual JS scripts running within that origin.
- Are XSS/CSP defenses in place on the frontend? If a trusted origin suffers XSS, same-origin attacker scripts inherit its CORS permissions.
- Could protected data be shared-cached by a CDN after responses carry ACAO/ACAC? Dedicated `Cache-Control` is required.
- Is there a review, logging, and audit process for changing allowed origins rather than letting clients register unverified origins?

Proper CORS is only one layer in the security architecture. Especially with `allowCredentials(true)`, treat adding an origin as **expanding the trust boundary** requiring review.

## 15. Self-practice exercises

**Exercise 1 — Allowed origins:** Page `https://app.example.com` calls API `https://api.example.com`. Write a `CorsConfiguration` allowing only app, HTTP methods GET/POST, Content-Type/Authorization, and no wildcards. Why is `https://app.example.com.attacker.test` rejected?

**Exercise 2 — Wildcard credentials:** Explain why `allowedOrigins("*") + allowCredentials(true)` is rejected and why replacing it with `allowedOriginPatterns("*") + allowCredentials(true)` runs yet is unsafe.

**Exercise 3 — Domain patterns:** An organization has `a.trusted.example.com` and `b.trusted.example.com`, plus a user-created subdomain. Should you use `https://*.trusted.example.com` for credentialed CORS? Propose an exact allowlist.

**Exercise 4 — Preflight:** A frontend sends a JSON POST with an Authorization header. Write the OPTIONS request with Origin, Access-Control-Request-Method, and Access-Control-Request-Headers. Distinguish OPTIONS from actual POST in allowedMethods.

**Exercise 5 — Security:** CORS preflight returns 401 when Spring Security uses session authentication. Explain why preflight has no cookie and write `http.cors(Customizer.withDefaults())` + `CorsConfigurationSource` to handle it in the right order.

**Exercise 6 — Cookies:** Why can `fetch(credentials:"include")` + valid ACAO/ACAC still get 401? Analyze SameSite, Secure, Domain, Path, and browser third-party cookie policies.

**Exercise 7 — Expose headers:** The API returns X-Request-ID yet `response.headers.get("X-Request-ID")` is null. What server configuration do you need? Does it also make X-Request-ID an allowed request header?

**Exercise 8 — Tests:** Write MockMvc preflight tests allowing origin `http://localhost:5173`, denying `https://evil.example`, allowing POST, and rejecting DELETE.

**Exercise 9 — Error responses:** A valid origin receives a 500 from upstream yet the browser only reports CORS. Which layers can drop ACAO? Why is opening ACAO "*" not a real fix?

**Exercise 10 — Architecture:** Design policies for `/api/public/**` (no credentials), `/api/account/**` (credentials + exact origins), and `/api/admin/**` (strict allowlist + authorization). Choose CorsFilter/MVC/Security integration without overlapping policies.

## 16. Summary

- **`CorsFilter`** processes CORS at the Servlet filter boundary via `CorsConfigurationSource` and `CorsProcessor`; well-suited when CORS must run early, especially ahead of Spring Security.
- **`allowedOrigins`** should list exact origins (scheme, host, port). Never use `"*"` when `allowCredentials(true)`.
- **`allowedOriginPatterns`** supports hostname/port wildcards and can work with credentials because Spring echoes the matched origin; however, overly broad patterns introduce major risks.
- **Credentials are not authentication**, and CORS does not replace CSRF protection, authorization, or cookie security.
- **Wildcards in methods/headers/exposedHeaders** follow different rules than origin wildcards; prefer explicit allowlists to minimize semantic/browser surprises.
- **OPTIONS preflight** must be handled before authentication; actual requests must still pass appropriate authentication/authorization/CSRF checks.
- In a Spring MVC project, maintain **one CORS policy with clear ownership**, testing positive/negative origins, methods, headers, credentials, and error responses.
- When the browser reports a CORS error, inspect network, status, cookies, security filter chain, and proxies — never just add `@CrossOrigin("*")`.

## 17. Official references

- [Spring Framework 6.2 — CORS in Spring MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-cors.html).
- [Spring Framework 6.2 — CorsConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/cors/CorsConfiguration.html): `allowedOrigins`, `allowedOriginPatterns`, `allowCredentials`, and validation.
- [Spring Framework 6.2 — CorsFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/CorsFilter.html).
- [Spring Framework 6.2 — DefaultCorsProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/cors/DefaultCorsProcessor.html).
- [Spring Security — CORS Servlet Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html).
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): preflight, headers, credentials.
- [MDN — Access-Control-Allow-Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin).
- [WHATWG Fetch Standard](https://fetch.spec.whatwg.org/): normative CORS protocol, credentials, and response tainting.
