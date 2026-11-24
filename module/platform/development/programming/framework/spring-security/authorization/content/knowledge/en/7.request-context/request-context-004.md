# CORS Preflight, OPTIONS, and Their Relationship with Authorization Rules in Spring Security

## 1. The Problem: Why Does OPTIONS Get 401/403 Before PATCH Is Sent?

Suppose a project management system's UI runs at `https://app.example.test`, while the Spring Boot API runs at `https://api.example.test`. A logged-in user wants to edit a project using JavaScript:

```javascript
await fetch("https://api.example.test/api/projects/p7", {
  method: "PATCH",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer <access-token>"
  },
  body: JSON.stringify({ name: "Project Seven" })
});
```

The browser sees this is a **cross-origin request** using the `PATCH` method and headers not belonging to the *CORS-safelisted* set. Before sending the actual PATCH, it usually automatically asks the server using an **OPTIONS preflight** request. Preflight carries neither an access token in `Authorization` nor a user session cookie per CORS rules. If Spring Security requires `authenticated()` or `hasAuthority("project:edit")` **before** processing CORS, OPTIONS can be rejected. The browser will not send the actual PATCH and will display a CORS error.

Developers sometimes fix this incorrectly by adding:

```java
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
```

This rule can let all OPTIONS pass authorization, yet **does not configure** allowed origins, allowed methods, allowed headers, credentials, or CORS responses. It also gives ordinary OPTIONS requests on every endpoint an overly broad rule. The right approach in Spring Security Servlet is to **integrate proper CORS handling before the authorization step**, and continue requiring permissions for the **actual request**.

This lesson guides you to:

1. Distinguish **origin**, cross-origin, preflight, ordinary OPTIONS, and actual requests.
2. Correctly read `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`, and response headers.
3. Understand the order in which Spring Security handles CORS, authentication, and authorization.
4. Configure `CorsConfigurationSource`/`CorsFilter` or Spring MVC CORS with `http.cors(...)`.
5. Know why permitting CORS does **not** equal permission to access a resource or bypass CSRF.
6. Build separated tests: preflight is accepted; actual requests with sufficient permission are processed; insufficient permission is still denied.
7. Handle multiple SecurityFilterChains, gateways, session cookies, Bearer tokens, Vary, and preflight caching.

**Scope:** Spring Security on **Servlet/Spring MVC**, Java 17+, examples use `SecurityFilterChain` instead of the deprecated `WebSecurityConfigurerAdapter` API. Spring WebFlux uses `SecurityWebFilterChain`/`CorsWebFilter` and requires separate configuration. When copying code, verify against your project's actual Spring Security/Spring Framework versions.

## 2. What Is an Origin? Cross-Origin Differs from Cross-Site

### 2.1. An Origin Consists of Scheme, Host, and Port

Under the web security model, an origin is defined by the tuple **scheme + hostname + port**. Examples:

| Access address | Compared to `https://app.example.test` |
| --- | --- |
| `https://app.example.test/dashboard` | Same-origin — different path does not change origin |
| `https://api.example.test/projects` | Cross-origin — different hostname |
| `http://app.example.test/dashboard` | Cross-origin — different scheme |
| `https://app.example.test:8443/dashboard` | Cross-origin — different port |
| `https://app.example.test:443/dashboard` | Usually same-origin with an HTTPS URL using default port 443 |
| `https://another.example.test` | Cross-origin — different hostname |

**CORS** (*Cross-Origin Resource Sharing*) is the mechanism letting browsers decide whether JavaScript from one origin may access responses from another origin. The server declares policy via response headers. The browser enforces most of that mechanism.

**Cross-origin is not synonymous with cross-site.** Two subdomains can be cross-origin yet same-site under modern site rules; meanwhile, `SameSite` cookies and CSRF relate to the site concept. Do not assume "different origin" always requires `SameSite=None` cookies in every situation, or that CORS alone solves CSRF.

### 2.2. CORS Is Not an Authentication Mechanism

Three independent questions:

- **CORS:** Does the browser allow JavaScript running from `https://app.example.test` to send/read a cross-origin request to the API per server policy?
- **Authentication:** Does the actual request carry valid proof of login? A session cookie, Bearer token, or another mechanism.
- **Authorization:** Does the authenticated principal have `project:edit` permission on project `p7` of the current tenant?

You can have:

```text
CORS allow origin/method/headers = true
Valid Authentication           = false
Authorization project:edit      = false

=> Valid preflight, yet the actual request is still denied.
```

Conversely, a user with the ADMIN role whose origin is not accepted by CORS may have the **browser** block the frontend application from reading the response. A non-browser client unrestricted by CORS such as `curl` can still call the server; **do not treat Origin as a security role**.

## 3. What Is Preflight and When Does the Browser Send It?

Preflight is an HTTP `OPTIONS` request with CORS-specific headers to ask the server **before sending an actual request** whose method/headers fall outside the simple-request criteria. Browsers normally generate preflight automatically; frontend JavaScript does not need to send `OPTIONS` manually.

### 3.1. Signs Identifying a CORS Preflight

Example:

```http
OPTIONS /api/projects/p7 HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: authorization, content-type
```

Meaning:

| Field | Role |
| --- | --- |
| HTTP method `OPTIONS` | Method of the **preflight**, not yet the edit operation |
| `Origin` | Origin of the page/script making the cross-origin request |
| `Access-Control-Request-Method` | Method of the request that **will** be sent, e.g., PATCH |
| `Access-Control-Request-Headers` | List of non-safelisted header names that will appear in the actual request |
| `Authorization` | **Does not send a Bearer token on preflight** merely because the actual request has Authorization |
| `Cookie` | Preflight normally carries no user cookies, even when the actual request needs cookies |

Specifically: `Access-Control-Request-Headers: authorization` only states "the upcoming request intends to include an Authorization header", and **contains no token value**. Nor does it mean the user has `project:edit` permission.

An `OPTIONS` request **without** `Origin` and `Access-Control-Request-Method` may just be an ordinary HTTP OPTIONS request, not a CORS preflight. Never assume "all OPTIONS are unconditionally allowed preflights".

### 3.2. Requests That Commonly Trigger Preflight

Common examples:

- Cross-origin `PATCH`, `PUT`, `DELETE`.
- `POST` with `Content-Type: application/json`.
- `GET` with an `Authorization: Bearer ...` header added by JavaScript.
- Requests with custom headers like `X-Request-Id`, `X-CSRF-TOKEN`, or `X-Tenant-Id`, depending on safelist rules.
- Certain other Fetch/CORS behaviors per the specification and browser policies.

For instance, `GET` does not automatically skip preflight if it sends an `Authorization` header. And `POST` does not automatically require preflight: some POSTs with headers, content type, and conditions within the CORS-safelisted set can be sent directly.

### 3.3. Simple Requests Without Preflight Are Still Subject to CORS

Cross-origin JavaScript example:

```javascript
await fetch("https://api.example.test/api/public/catalog");
```

A GET request without custom headers may **not require preflight**, yet the response must still carry appropriate CORS headers for JavaScript at the calling origin to read the response. If `Access-Control-Allow-Origin` is missing, the browser may block the script from reading the result; **the server may have already received and processed the GET**.

Therefore, you cannot measure backend security by "the browser displayed a CORS error". Especially for requests with side effects, a non-preflighted request can reach the server before the browser decides not to let the frontend read the response. Authentication, authorization, and CSRF remain mandatory.

## 4. Two HTTP Steps: Preflight and Actual Request

### 4.1. Step 1 — Preflight OPTIONS

Suppose the server allows only origin `https://app.example.test` to call `GET`/`POST`/`PATCH`, using headers `Authorization`, `Content-Type`, and `X-CSRF-TOKEN`.

Request:

```http
OPTIONS /api/projects/p7 HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: authorization, content-type
```

Valid illustrative response:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET, POST, PATCH
Access-Control-Allow-Headers: authorization, content-type
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
```

**Note:** this is an **illustrative response**. A CORS processor may return `200` or `204`, header ordering/values may vary, and `Access-Control-Allow-Methods`/`Access-Control-Allow-Headers` may reflect the requested subset rather than printing the entire server-allowed list. `Access-Control-Allow-Credentials: true` is appropriate only if the application intends to support credentialed cross-origin requests and configuration permits it.

The browser checks: is the origin allowed? Is the intended actual method allowed? Are the intended headers allowed? If not, it usually **does not proceed to send the actual request**.

**Preflight does not grant permission to edit `p7`.** It is strictly a cross-origin negotiation step in the browser.

### 4.2. Step 2 — Actual PATCH

Once preflight succeeds, the browser sends the actual request:

```http
PATCH /api/projects/p7 HTTP/1.1
Origin: https://app.example.test
Authorization: Bearer <access-token>
Content-Type: application/json

{"name":"Project Seven"}
```

Spring Security needs to evaluate:

1. Does the CORS actual request have an allowed origin?
2. Is the token/session valid?
3. Does the principal have `project:edit` (or the corresponding business permission)?
4. Is the principal allowed to edit **project `p7` specifically** (tenant/owner/membership/state)?
5. If the app uses cookies/sessions, is the CSRF token valid on the write operation?

The request can fail with 401/403 or a business error even after preflight succeeded. On the actual response, the browser also checks CORS response headers before exposing content to the script.

### 4.3. Distinguishing Outcome Types

| Situation | Preflight | Actual request | Conclusion |
| --- | --- | --- | --- |
| Allowed origin, allowed method/headers, valid token and sufficient permissions | Passes | Processed | Valid flow |
| Correct origin, request needs `project:edit` yet principal has only `project:read` | Passes | Denied by authorization | **Not a preflight error** |
| Wrong origin | Rejected by CORS processor | Browser usually does not send actual | Origin configuration/policy error |
| Header `x-internal-secret` not allowed by CORS | Rejected by CORS | Actual not sent | Allowed headers error |
| `PATCH` not in allowed methods | Rejected by CORS | Actual not sent | Allowed methods error |
| Non-preflighted cross-origin GET, backend returns missing CORS headers | No preflight | Server may have processed GET | Browser prevents JS from reading response |
| OPTIONS without CORS preflight headers | Not a true CORS preflight | Handled as ordinary OPTIONS | Do not open all routes automatically |
| Preflight passes yet cookie not sent by browser on actual | Passes | May be unauthenticated | Check `credentials`/cookie/SameSite |
| Preflight passes yet POST lacks CSRF token | Passes | May be rejected by CsrfFilter | CORS does not replace CSRF |

A browser log often only shows "CORS policy blocked" without telling you whether the actual request was sent. In DevTools, inspect the **two separate network entries** and each one's response headers before changing rules.

## 5. Spring Security Must Process CORS Before the Step Requiring Authentication

Spring Security documentation explicitly states that preflight does not carry the `JSESSIONID` session cookie. If authentication/authorization occurs before CORS processes preflight, it can evaluate OPTIONS as an unauthenticated request and return 401/403. The supported approach on the Servlet stack is integrating CORS processing, typically via `CorsFilter`/`CorsConfigurationSource` or via Spring MVC CORS configuration used by Spring Security.

### 5.1. Desired Processing Flow

```text
Browser OPTIONS (preflight, no user credential)
   │
   ▼
SecurityFilterChain selects matching chain for /api/**
   │
   ▼
CORS processing handles request before authorization requiring login
   ├─ Invalid origin/method/header → CORS rejection
   └─ Valid → returns preflight response, does not invoke API action

Browser PATCH (actual request, with token/cookie as applicable)
   │
   ▼
CORS actual request processing
   │
   ▼
Authentication: Bearer/session...
   │
   ▼
AuthorizationFilter: project:edit
   │
   ▼
Method/domain authorization: tenant/owner/state...
   │
   ▼
Controller/service executes the update
```

The diagram simplifies the mechanism and is not an exact filter list across every version or custom filter. The mandatory requirement is that **valid preflights must be handled without demanding a user token**, while **actual requests must go through authentication and authorization normally**.

### 5.2. No Need to Declare permitAll for All OPTIONS Once CORS Is Integrated Properly

In many configurations:

```java
http
    .cors(Customizer.withDefaults())
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.PATCH, "/api/projects/*")
            .hasAuthority("project:edit")
        .anyRequest().denyAll()
    );
```

A properly configured CORS processor intercepts and handles **CORS preflight** before `AuthorizationFilter` demands `project:edit` for the actual PATCH. Valid OPTIONS requests can receive a preflight response even while `anyRequest().denyAll()` remains in place. That is the core advantage of CORS integration.

If the app has custom filters, multiple chains, or a gateway rejecting OPTIONS before Spring, merely adding `http.cors(...)` to one chain may be insufficient. Verify where preflight is blocked and the actual processing order.

## 6. Spring Boot Servlet Configuration Example with CorsConfigurationSource

This is an **integration pattern inside a Spring Boot MVC project** with `spring-boot-starter-web`, `spring-boot-starter-security`, and Java 17+. The sample assumes the API serves a fixed frontend `https://app.example.test`; hostnames are illustrative, not production domains. Authentication sources (JWT/session) and controllers must be added to the project. Do not run this class directly with plain `javac` alone.

Create `ApiCorsSecurityConfig.java`:

```java
package com.example.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiCorsSecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();

        // Allow the exact trusted frontend origin.
        config.setAllowedOrigins(List.of("https://app.example.test"));

        // These are methods OF THE ACTUAL REQUEST, not just OPTIONS.
        config.setAllowedMethods(List.of("GET", "POST", "PATCH"));

        // Allow the frontend to request sending these header names.
        config.setAllowedHeaders(List.of(
                "Authorization", "Content-Type", "X-CSRF-TOKEN"));

        // Enable true only when the application needs credentialed cross-origin requests.
        config.setAllowCredentials(true);

        // Browser may cache preflight result, unit: seconds.
        config.setMaxAge(1800L);

        // A business response header JS is allowed to read if the server actually sends it.
        config.setExposedHeaders(List.of("X-Request-Id"));

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();

        // CORS applies to the API, does not automatically open the entire system.
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth

                        // Admin branch requires role.
                        .requestMatchers("/api/admin/**")
                            .hasRole("ADMIN")

                        // Read and edit actions have separate permissions.
                        .requestMatchers(
                                HttpMethod.GET,
                                "/api/projects", "/api/projects/*")
                            .hasAuthority("project:read")
                        .requestMatchers(
                                HttpMethod.PATCH, "/api/projects/*")
                            .hasAuthority("project:edit")

                        // Without a matching rule, access is denied.
                        .anyRequest().denyAll()
                )
                .build();
    }
}
```

### 6.1. What the Configuration Actually Does

- `UrlBasedCorsConfigurationSource` stores the CORS policy for `/api/**`.
- `http.cors(Customizer.withDefaults())` instructs Spring Security to use CORS integration; `CorsFilter` is ordered appropriately so preflight is processed before authorization when a matching configuration is chosen.
- Origins other than `https://app.example.test` are disallowed by this configuration.
- Only **actual methods** `GET`, `POST`, `PATCH` are permitted at the CORS layer; **POST is not automatically permitted at the authorization layer**, because there is no role/authority rule for POST projects and the fallback is deny.
- Having `Authorization` in allowed headers means the browser is permitted to send that header on the actual request; it does **not** mean the token is valid or a role has been granted.
- `hasRole("ADMIN")` by default convention requires authority `ROLE_ADMIN`.
- `hasAuthority("project:edit")` requires the exact authority `project:edit`. A role `ROLE_EDITOR` does not automatically generate that permission unless the app maps it.
- `anyRequest().denyAll()` protects undeclared URLs/methods.
- `setAllowCredentials(true)` is chosen in the sample to illustrate a credentialed flow; **keep it true only if the real product needs it**. For a Bearer-only frontend using no cookies/credentialed fetch, consider reducing this privilege and selecting an appropriate config.

**Do not skip:** the sample does not configure an authentication provider, resource server, session policy, CSRF, or JSON exception handlers. Add them per your real architecture. If using sessions/cookies, write operations may require CSRF tokens; never disable CSRF just to fix a CORS error.

### 6.2. Why Does the Bean Return UrlBasedCorsConfigurationSource?

Modern Spring Security documentation states that Spring Security auto-configures CORS from an available `UrlBasedCorsConfigurationSource` bean when using the DSL; if **multiple** `CorsConfigurationSource` beans exist, the framework may not know which bean to pick and needs an explicit source configured per chain.

To avoid ambiguity, you can specify the source explicitly:

```java
http.cors(cors -> cors
        .configurationSource(corsConfigurationSource()));
```

The line above sits inside the config class when `corsConfigurationSource()` is present, yet if the project has different @Bean configs or multiple chains, prefer injecting a specific source into each chain builder method. Do not create multiple stacked `CorsFilter`s without checking their order and response headers.

### 6.3. Configuration Choices to Decide Explicitly

| Decision | Suggestion |
| --- | --- |
| Which frontend origins are allowed? | Specific allowlist by scheme, host, port |
| Which APIs need CORS? | `/api/**` or a smaller scope per contract |
| Which actual methods are needed? | Only GET/POST/PATCH/PUT/DELETE actually supported |
| Which headers are needed? | `Authorization`, `Content-Type`, CSRF header per app |
| Send cookies cross-origin? | Enable credentials only when needed with explicit trust |
| Does frontend read custom response headers? | Use `exposedHeaders` when needed |
| Cache preflight? | `maxAge` balancing performance with policy-change agility |
| Multiple chains? | Configure CORS for the right chain; have a safe fallback chain |
| JWT Bearer? | Verify token/authorities on **actual request**, not preflight |
| Cookie session? | Verify session, CSRF, and cookie attributes on **actual request** |

## 7. Configuring CORS with Spring MVC or @CrossOrigin

Spring MVC supports CORS in `HandlerMapping`. If a project already uses Spring MVC and does not supply an explicit `CorsConfigurationSource` to Spring Security, you can enable `http.cors(...)` integration so Spring Security uses the CORS configuration provided by MVC.

### 7.1. Global Configuration Example via WebMvcConfigurer

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcCorsConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.test")
                .allowedMethods("GET", "POST", "PATCH")
                .allowedHeaders(
                        "Authorization", "Content-Type", "X-CSRF-TOKEN")
                .allowCredentials(true)
                .maxAge(1800);
    }
}
```

For Spring Security to handle CORS using the MVC configuration, enable it in the security chain:

```java
http.cors(Customizer.withDefaults());
```

**Choose one policy source with clear ownership.** The sample in section 6 uses a `UrlBasedCorsConfigurationSource` bean; the sample in section 7 uses MVC. You do not need both at once just because you saw two tutorials. In real apps, multiple inconsistent CORS sources can cause duplicate headers, chains picking the wrong source, or preflight being blocked before reaching MVC.

### 7.2. @CrossOrigin on Controllers

Example:

```java
@RestController
@RequestMapping("/api/catalog")
@CrossOrigin(origins = "https://app.example.test")
public class CatalogController {

    @GetMapping
    public List<ItemView> catalog() {
        return catalogService.publicItems();
    }
}
```

This is a **fragment** requiring real `ItemView` and `catalogService`. `@CrossOrigin` is a way to declare CORS for a handler; it **does not** replace `hasRole`/`hasAuthority`/`@PreAuthorize` and does not prove the catalog can be read by any user.

If both global CORS config and `@CrossOrigin` exist, Spring MVC has **combination** rules; many list-valued attributes can be merged. Review carefully so you do not accidentally expose extra origins/methods beyond intent.

### 7.3. When to Use Which Style?

- **One API and one stable frontend:** either a `UrlBasedCorsConfigurationSource` bean or global MVC CORS is suitable if integrated properly.
- **Controller-specific origins:** `@CrossOrigin` can be convenient, but review declarations alongside global policy.
- **Multiple SecurityFilterChains with different CORS policies:** specify each chain's CORS source explicitly when needed.
- **CORS handled at a gateway:** know which headers the backend still receives, whether the proxy adds/overwrites CORS headers, and who holds final ownership.
- **WebFlux:** do not copy Servlet `HttpSecurity`/`CorsFilter` verbatim.

## 8. OPTIONS in Spring Security: When Is permitAll Right?

### 8.1. Do Not Equate Every OPTIONS with Preflight

Two requests both using the OPTIONS method carry different meanings:

```http
OPTIONS /api/projects/p7 HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: PATCH
```

This is a **preflight** per CORS if the remaining conditions are valid.

```http
OPTIONS /api/projects/p7 HTTP/1.1
Host: api.example.test
```

This is an ordinary OPTIONS without CORS preflight headers. It can be handled per the server's HTTP contract, by an `OPTIONS` handler, or rejected depending on configuration. It should not automatically pass a broad public rule.

### 8.2. Why Opening All OPTIONS Does Not Solve CORS

Suppose the configuration is:

```java
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
.anyRequest().denyAll()
```

The first rule may allow OPTIONS at the **authorization step**, yet the browser still needs:

- `Access-Control-Allow-Origin` matching the requesting origin.
- `Access-Control-Allow-Methods` containing the intended actual method.
- `Access-Control-Allow-Headers` accepting the headers intended to be sent.
- `Access-Control-Allow-Credentials` when it is a credentialed request.
- A semantically valid preflight response not erroneously blocked by a filter/gateway.

Without CORS processing, `permitAll` does not generate these response headers on its own. The outcome can still be a CORS error. Meanwhile, opening all OPTIONS can mask misdesigned routes or security rules.

### 8.3. When Is an Explicit OPTIONS Rule Needed?

It may be needed when:

- The API **genuinely provides an OPTIONS endpoint** per contract and you want separate authorization for it.
- A gateway/legacy CORS layer handles preflight outside Spring Security and requires an explicitly tested compatibility rule.
- There is a clearly analyzed HTTP protocol requirement.

Even then, scope the matcher to **paths that need it**, rather than opening `/**` out of habit. With modern Spring Security Servlet CORS integration, **prefer letting the CORS processor handle preflight** instead of writing an authorization rule for all OPTIONS.

### 8.4. First-Match-Wins and Rule Order

In `authorizeHttpRequests`, the first matching matcher is used. Thus:

```java
// DANGEROUS: broad rule shadows the admin branch on actual requests.
.requestMatchers("/api/**").permitAll()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

CORS does not fix this bug. If using `securityMatcher("/api/**")` to select a filter chain, ensure admin requests (both OPTIONS preflight and actual methods) reach the right chain. A fallback chain protecting routes outside the API chain is necessary when an app has multiple filter chains.

## 9. CORS, Authorization, and CSRF Are Three Distinct Protection Layers

### 9.1. An Allowed Origin Does Not Prove a Trusted User

A browser sending `Origin: https://app.example.test` only helps the server identify the **JavaScript source** in CORS; it is not a credential. Non-browser clients can set `Origin` arbitrarily. Users still need valid authentication and permission on the resource.

**Never write policies like:**

```java
// Anti-pattern: DO NOT use Origin as a substitute for authorization.
if ("https://app.example.test".equals(request.getHeader("Origin"))) {
    // Allow deleting resource regardless of principal.
}
```

Properly: CORS checks origin, while `SecurityFilterChain`/services check roles, permissions, tenant, owner, and state.

### 9.2. CSRF Remains Important with Cookies/Sessions

Example of a cross-origin frontend using session cookies:

```javascript
await fetch("https://api.example.test/api/projects/p7", {
  method: "PATCH",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ name: "Updated" })
});
```

The application must handle separately:

1. **CORS:** allow trusted origin, PATCH, Content-Type, and X-CSRF-TOKEN.
2. **Cookie/session:** is the browser allowed to send the session cookie on the actual request, given cookie attributes and browser policies?
3. **CSRF:** the token must be issued/read/submitted per the `CsrfTokenRepository` and Spring Security mechanism chosen by the project.
4. **Authorization:** does the session user have permission to edit that specific project?

For **cross-site** cookie requests, `SameSite=None; Secure` may be necessary under browser models; yet browsers may restrict third-party cookies. For cross-origin yet **same-site** requests, SameSite reasoning can differ. CORS `allowCredentials(true)` **does not automatically enable cookie sending** or bypass cookie policies.

### 9.3. Bearer Token Is Not Synonymous with CORS Authorization

With `Authorization: Bearer ...`, browsers usually require preflight because the Authorization header is not safelisted. Yet preflight carries no token. The backend verifies the token only on the actual request; `JwtAuthenticationConverter` or other providers must supply real authorities for `hasAuthority(...)`.

For backends using only JS-supplied Bearer tokens, clarify whether cookies are used elsewhere and whether CSRF protection is needed. Never disable CSRF **just because you saw a CORS error**. If the app uses both sessions and Bearer tokens, the threat model must assess each credential mechanism.

### 9.4. Simple Requests and Side Effects

A cross-origin request of a type needing no preflight can reach the server, even causing mutations if the server omits CSRF/authorization checks. The browser preventing scripts from reading the response does not mean the server did no work. Hence, never rely on CORS as the sole barrier blocking write operations or preventing CSRF.

## 10. Credentials, Wildcards, and Headers to Get Right

### 10.1. Access-Control-Allow-Origin Cannot Use "*" with Credentials

When the server permits credentialed requests with `Access-Control-Allow-Credentials: true`, you should not and cannot configure `Access-Control-Allow-Origin: *` for credentialed requests per browser CORS rules. Spring Framework also disallows `allowOrigins("*")` when `allowCredentials(true)`; use an explicit origin list or carefully designed `allowedOriginPatterns`.

Good example:

```text
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
```

Bad example for credentialed browser access:

```text
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

For genuinely public read-only APIs using no credentials, wildcard can be valid and simpler; that is a separate decision based on resource publicity. Do not choose wildcard just to clear console warnings.

### 10.2. Origin Can Have Value "null"

An `Origin: null` header can come from sandboxed documents or opaque-origin sources. Never add `"null"` to an allowlist just because you saw it in logs. Evaluate the actual source and trust level; `null` is not a verified hostname.

### 10.3. Allowed Headers Differ from Exposed Headers

| Attribute | Direction of effect | Example |
| --- | --- | --- |
| `allowedHeaders` | Browser may **send** declared request headers | Authorization, Content-Type, X-CSRF-TOKEN |
| `exposedHeaders` | JS may **read** selected response headers beyond safelisted ones | X-Request-Id, X-RateLimit-Remaining |
| `allowedMethods` | Which actual methods browser may use in cross-origin requests | GET, POST, PATCH |
| `allowCredentials` | Allows browser to use credentialed CORS responses per policy | true/false |
| `allowedOrigins` | Which origins are accepted | https://app.example.test |
| `maxAge` | Duration browser may cache preflight result | 1800 seconds |

`setExposedHeaders(List.of("X-Request-Id"))` does **not** mean the server automatically adds the `X-Request-Id` response header; the app must actually emit it. Likewise, `setAllowedHeaders("Authorization")` does not create an authorization token.

### 10.4. Use Only a Trusted Allowlist

Do not reflect every request `Origin` into `Access-Control-Allow-Origin` while enabling credentials. With sessions/cookies, that can allow scripts at untrusted origins to read private responses. Dynamic per-tenant allowlists must be tightly governed and validated so users cannot register malicious origins into trusted lists.

**CORS does not replace data authorization**, yet an overly broad CORS configuration can expand the set of websites permitted to interact with and read sensitive information of logged-in users.

## 11. Preflight Cache, Vary, and Bugs When Changing Policies

### 11.1. Access-Control-Max-Age

`Access-Control-Max-Age` tells the browser how long it may cache a preflight result; the browser's preflight cache is **separate** from ordinary HTTP caching and has per-browser caps. Example:

```http
Access-Control-Max-Age: 1800
```

means the server suggests 1,800 seconds. Browsers may enforce a lower cap. If you change origin/method/header policy, cached preflight results can still have an effect for some time. Do not equate "disabling browser cache" with changing reverse-proxy caching.

**Preflight caching does not cache the authorization outcome of actual requests.** A user's `project:edit` permission can be revoked, and the subsequent actual request must still be denied even if the browser skips sending OPTIONS during the cache window.

### 11.2. Vary and Shared HTTP Caches

When CORS responses vary by `Origin` or preflight headers, systems may need:

```http
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
```

so shared caches/CDNs do not mistakenly serve one origin/method/header's response headers to another. Spring's CORS processor normally manages Vary appropriately; if a proxy alters cache headers, verify end-to-end.

For personalized content, avoid publicly caching responses containing session data. That is a separate HTTP cache/security concern, not automatically solved by CORS.

### 11.3. A 200/204 Response Is Not Enough to Conclude Success

A `200` or `204` preflight is insufficient if the browser needs allow-origin/methods/headers headers that the response lacks. Conversely, an actual request returning `401` or `403` with proper CORS headers can be a normal authorization outcome, not a preflight bug.

**Check both status and headers**, for the right request type.

## 12. Multiple SecurityFilterChains, Gateways, and Reverse Proxies

### 12.1. securityMatcher and requestMatchers Differ

In Servlet:

- `http.securityMatcher("/api/**")` decides whether a **chain** is selected for a request.
- `authorizeHttpRequests(...requestMatchers(...))` decides **authorization rules** within that chain.
- `http.cors(...)` configures **CORS integration** for the appropriate chain.

If an application has multiple chains (JWT API, web session, actuator), ensure both OPTIONS and actual requests reach the **right chain**, and that chain has proper CORS processing. A chain matching only `/api/**` does not protect URLs outside that scope by default; a fallback chain is needed when whole-application protection is required.

### 12.2. Per-Chain CORS Policy

A design might look like:

```java
// Fragment: SecurityFilterChain for /api/**
http.securityMatcher("/api/**")
    .cors(cors -> cors
        .configurationSource(apiCorsConfigurationSource))
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated());
```

This snippet only illustrates how to **select an explicit CORS source** for the API chain; `apiCorsConfigurationSource` must be a defined bean/object, not a built-in API. Configure authentication, other chains, and fallbacks accordingly. If multiple `CorsConfigurationSource` beans exist, make explicit which bean each chain uses; do not rely on ambiguous auto-detection.

### 12.3. Gateways Can Block OPTIONS Before Spring

A reverse proxy/WAF/API gateway can:

- Reject the OPTIONS method.
- Fail to forward `Origin` or `Access-Control-Request-*`.
- Return its own preflight response unseen by the backend.
- Add CORS headers differing from the backend, creating duplicate/conflicting headers.
- Cache responses under keys excluding Origin or method.
- Redirect HTTP→HTTPS or canonical URLs, causing preflight failures depending on browser/client.

In such systems, editing `SecurityFilterChain` alone will not fix every error. Identify the **CORS owner** (gateway vs. backend), the effective policy, and the request path.

### 12.4. Localhost Frontends and Ports

During development, `http://localhost:3000`, `http://localhost:5173`, and `http://127.0.0.1:5173` are distinct origins. Setting `allowedOrigins("http://localhost:5173")` grants only that exact origin; other ports are not automatically allowed.

Never relax to `*.example.com` or `*` in production just because frontend dev servers switch ports. Use explicit environment-specific configurations and review production policy separately.

## 13. Standalone Java 17 Example: Preflight Does Not Authorize the Actual Request

To see the principle without loading Spring, the program below **simulates** two separate decisions:

- `preflight(...)` checks only origin, intended method, and intended header list.
- `actual(...)` checks origin together with the user's real permissions/roles for the specific action.

This **is not Spring's CorsFilter/AuthorizationFilter**; it does not implement an HTTP parser, cookies, JWT, CSRF, browsers, or object permissions. It only clarifies why a passing preflight does not mean PATCH is authorized.

Create file `CorsAuthorizationConceptDemo.java`:

```java
import java.util.Locale;
import java.util.Set;

public class CorsAuthorizationConceptDemo {

    private static final String TRUSTED_ORIGIN =
            "https://app.example.test";

    private static final Set<String> CORS_METHODS =
            Set.of("GET", "POST", "PATCH");

    private static final Set<String> CORS_HEADERS =
            Set.of("authorization", "content-type", "x-csrf-token");

    record Preflight(
            String origin,
            String requestedMethod,
            Set<String> requestedHeaders) {}

    static String preflight(Preflight request) {
        if (request == null || !TRUSTED_ORIGIN.equals(request.origin())) {
            return "CORS_REJECT";
        }
        if (!CORS_METHODS.contains(request.requestedMethod())) {
            return "CORS_REJECT";
        }
        if (request.requestedHeaders() == null) {
            return "CORS_REJECT";
        }
        for (String header : request.requestedHeaders()) {
            if (header == null
                    || !CORS_HEADERS.contains(header.toLowerCase(Locale.ROOT))) {
                return "CORS_REJECT";
            }
        }
        return "PREFLIGHT_OK";
    }

    static String actual(
            String origin, String method,
            String path, Set<String> authorities) {

        if (!TRUSTED_ORIGIN.equals(origin)) {
            return "CORS_REJECT";
        }
        if (method == null || path == null) {
            return "AUTHZ_DENY";
        }

        String required;
        if (method.equals("PATCH") && path.matches("/api/projects/[^/]+")) {
            required = "project:edit";
        } else if (method.equals("GET")
                && path.matches("/api/projects/[^/]+")) {
            required = "project:read";
        } else if (method.equals("GET")
                && path.equals("/api/admin/users")) {
            required = "ROLE_ADMIN";
        } else {
            return "AUTHZ_DENY";
        }

        return authorities != null && authorities.contains(required)
                ? "ALLOW" : "AUTHZ_DENY";
    }

    public static void main(String[] args) {
        Preflight valid = new Preflight(
                TRUSTED_ORIGIN, "PATCH",
                Set.of("Authorization", "Content-Type"));
        Preflight wrongOrigin = new Preflight(
                "https://untrusted.example.test", "PATCH",
                Set.of("Authorization", "Content-Type"));
        Preflight wrongMethod = new Preflight(
                TRUSTED_ORIGIN, "DELETE",
                Set.of("Authorization"));
        Preflight wrongHeader = new Preflight(
                TRUSTED_ORIGIN, "PATCH",
                Set.of("X-Internal-Secret"));

        Set<String> viewer = Set.of("project:read");
        Set<String> editor = Set.of("project:read", "project:edit");
        Set<String> admin = Set.of("ROLE_ADMIN");

        System.out.println("valid-preflight=" + preflight(valid));
        System.out.println("wrong-origin-preflight="
                + preflight(wrongOrigin));
        System.out.println("wrong-method-preflight="
                + preflight(wrongMethod));
        System.out.println("wrong-header-preflight="
                + preflight(wrongHeader));

        System.out.println("viewer-patch="
                + actual(TRUSTED_ORIGIN, "PATCH",
                        "/api/projects/p7", viewer));
        System.out.println("editor-patch="
                + actual(TRUSTED_ORIGIN, "PATCH",
                        "/api/projects/p7", editor));
        System.out.println("anonymous-patch="
                + actual(TRUSTED_ORIGIN, "PATCH",
                        "/api/projects/p7", Set.of()));
        System.out.println("viewer-get="
                + actual(TRUSTED_ORIGIN, "GET",
                        "/api/projects/p7", viewer));
        System.out.println("viewer-admin="
                + actual(TRUSTED_ORIGIN, "GET",
                        "/api/admin/users", viewer));
        System.out.println("admin-admin="
                + actual(TRUSTED_ORIGIN, "GET",
                        "/api/admin/users", admin));
        System.out.println("unknown-route="
                + actual(TRUSTED_ORIGIN, "POST",
                        "/api/projects/p7", editor));
        System.out.println("untrusted-editor="
                + actual("https://untrusted.example.test", "PATCH",
                        "/api/projects/p7", editor));
    }
}
```

Run with **JDK 17 or higher**:

```bash
javac CorsAuthorizationConceptDemo.java
java CorsAuthorizationConceptDemo
```

Expected stdout:

```text
valid-preflight=PREFLIGHT_OK
wrong-origin-preflight=CORS_REJECT
wrong-method-preflight=CORS_REJECT
wrong-header-preflight=CORS_REJECT
viewer-patch=AUTHZ_DENY
editor-patch=ALLOW
anonymous-patch=AUTHZ_DENY
viewer-get=ALLOW
viewer-admin=AUTHZ_DENY
admin-admin=ALLOW
unknown-route=AUTHZ_DENY
untrusted-editor=CORS_REJECT
```

**Key analysis:**

1. `valid-preflight=PREFLIGHT_OK` **contains no principal**; it only confirms origin/method/headers fit the CORS policy.
2. Viewer and editor share **the same preflight** for PATCH, yet viewer gets `AUTHZ_DENY` and editor gets `ALLOW` due to different authorities.
3. Admin requires `ROLE_ADMIN`; having `project:read` is insufficient.
4. An undeclared URL/method receives `AUTHZ_DENY` under the demo policy.
5. An untrusted origin is simulated returning `CORS_REJECT` even when the user has permission. This does not turn Origin into a credential; in a real backend, non-browser clients can still send arbitrary requests so authorization is always mandatory.
6. The program does not yet check tenant, owner, state, cookies, CSRF, or body; all real operations still require domain policies.

Strings `PREFLIGHT_OK`, `CORS_REJECT`, and `AUTHZ_DENY` are **custom educational labels**, not standard Spring Security classes or HTTP statuses.

## 14. Testing: Test Preflight and Actual Requests Separately

### 14.1. Case Matrix

| Request | Origin | Token/session/authority | Layer-accurate expectation |
| --- | --- | --- | --- |
| OPTIONS preflight PATCH with valid headers | Trusted | **No user credential** | CORS accepts preflight |
| OPTIONS preflight PATCH from unknown origin | Untrusted | None | CORS rejects |
| OPTIONS preflight DELETE when CORS allows only GET/POST/PATCH | Trusted | None | CORS rejects method |
| OPTIONS preflight with disallowed header | Trusted | None | CORS rejects header |
| Actual PATCH after preflight | Trusted | `project:edit` | Passes functional authorization; object policy still applies |
| Actual PATCH | Trusted | Only `project:read` | **403/deny** per API config, not a preflight error |
| Actual PATCH | Trusted | Unauthenticated | Authentication challenge/deny per entry point |
| Actual GET with `project:read` | Trusted | `project:read` | Passes functional permission |
| Actual GET to admin API | Trusted | Only `project:read` | Rejected by role rule |
| Ordinary OPTIONS missing preflight headers | Missing/incomplete | Any | Follows HTTP route/security policy; not treated as CORS preflight |
| POST with session yet missing CSRF | Trusted | Logged in | May be rejected by CsrfFilter |
| Simple non-preflighted cross-origin GET | Trusted | Depends on route | Browser still checks CORS response; backend still checks authz |
| Preflight cached, user permission just revoked | Trusted | Actual permission expired | Actual request must be denied |

"Passes functional authorization" is only the HTTP security step; controllers, business rules, and object-level policies can still return errors. Tests should not force every case to `200` or `403` if the system redirects to login or lacks a handler.

### 14.2. MockMvc Test for Preflight Without User

This is a **test fragment** needing Spring Security Test, `MockMvc`, application context, the CORS/security configuration from section 6, and appropriate imports:

```java
@Test
void preflightPatchWorksWithoutAuthentication() throws Exception {
    mockMvc.perform(options("/api/projects/p7")
            .header("Origin", "https://app.example.test")
            .header("Access-Control-Request-Method", "PATCH")
            .header("Access-Control-Request-Headers",
                    "authorization, content-type"))
        .andExpect(status().isOk())
        .andExpect(header().string(
                "Access-Control-Allow-Origin",
                "https://app.example.test"));
}
```

With the sample configuration's default `CorsFilter`/`DefaultCorsProcessor`, valid preflights typically return 200 and CORS headers. If a gateway or custom processor validly returns 204, test status per that contract. Most importantly: **no `@WithMockUser` is needed**, and no PATCH controller is invoked when the browser only preflights.

### 14.3. MockMvc Test for CORS Rejection

```java
@Test
void preflightWrongOriginIsRejected() throws Exception {
    mockMvc.perform(options("/api/projects/p7")
            .header("Origin", "https://untrusted.example.test")
            .header("Access-Control-Request-Method", "PATCH")
            .header("Access-Control-Request-Headers", "authorization"))
        .andExpect(status().isForbidden());
}
```

Status 403 is the typical outcome of Spring's `DefaultCorsProcessor` when CORS policy rejects a request, though it can differ if handled by a proxy/custom processor. The test goal is that an unknown origin **never receives a valid allow-origin for itself**, and the request never reaches sensitive handlers.

### 14.4. MockMvc Test for Actual Request Lacking Permission

```java
@Test
@WithMockUser(authorities = "project:read")
void preflightAllowedButActualPatchDenied() throws Exception {
    mockMvc.perform(patch("/api/projects/p7")
            .header("Origin", "https://app.example.test")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"name\":\"Not Allowed\"}")
            .with(csrf()))
        .andExpect(status().isForbidden());
}
```

This snippet assumes the project tests with a mock user having `project:read` without `project:edit`, and if CSRF is enabled, `with(csrf())` avoids getting 403 merely for a missing token. This is an **in-project fragment**, not standalone Java. If the production app is Bearer-only with a different CSRF config, tests must reflect that security chain.

### 14.5. Testing Actual Request with Sufficient Permission and Object Policy

```java
@Test
@WithMockUser(authorities = "project:edit")
void editorCanReachPatchHandler() throws Exception {
    mockMvc.perform(patch("/api/projects/p7")
            .header("Origin", "https://app.example.test")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"name\":\"Edited\"}")
            .with(csrf()))
        .andExpect(status().isOk());
}
```

Testing `200` is accurate only if a PATCH controller exists, fixture `p7` is valid, tenant/owner/state policies permit it, and the handler actually returns 200. If the controller returns 204, use `isNoContent()`; if the service enforces additional rules, prepare a permitting fixture before asserting. A good security test separates **having sufficient authority** from **all business conditions succeeding**.

### 14.6. Testing with curl: Distinguishing the Two Requests

Simulated preflight:

```bash
curl -i -X OPTIONS "https://api.example.test/api/projects/p7" \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: PATCH" \
  -H "Access-Control-Request-Headers: authorization, content-type"
```

Actual request:

```bash
curl -i -X PATCH "https://api.example.test/api/projects/p7" \
  -H "Origin: https://app.example.test" \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  --data '{"name":"Updated"}'
```

**Limitation:** `curl` is not browser CORS enforcement, so it can send actual requests even when preflight fails or without sending preflight; therefore use curl to **inspect HTTP headers and server behavior**, not as proof a browser will accept it. Never leave real tokens in shell history/logs; use test environments or placeholders instead of sensitive data.

## 15. Diagnosing CORS and 403 Errors Accurately

| Symptom | Possible cause | How to investigate |
| --- | --- | --- |
| OPTIONS returns 401/login redirect | Preflight handled by authentication before CORS | Check `http.cors(...)`, `CorsFilter`, chain selection |
| OPTIONS returns 403 "Invalid CORS request" | Origin/method/header not in allowlist | Compare request headers against CorsConfiguration |
| OPTIONS returns 200 yet browser still reports CORS | Missing `Access-Control-Allow-Origin`/Methods/Headers or mismatched credentials | Inspect OPTIONS response headers |
| OPTIONS succeeds, PATCH returns 403 | User lacks permission or CSRF/object policy | Check actual request; **do not blindly relax CORS** |
| OPTIONS succeeds, PATCH returns 401 | Missing token/cookie or invalid authentication | Check actual Authorization/session |
| Same-origin works, cross-origin fails | Different origin/port/scheme or browser CORS enforcement | Compare exact origin and CORS headers |
| Non-preflighted GET fails for browser reading response | Missing/wrong response CORS headers | Inspect actual GET response |
| JS has Bearer token yet preflight 401 | Backend wrongly requires token on preflight | Preflight only names header authorization |
| Using `allowCredentials(true)` with `allowedOrigins("*")` errors | Invalid config for credentials | Choose exact origins or controlled patterns |
| Session cookie not sent on actual | `credentials`, cookie attributes, SameSite, third-party policies | Inspect request cookies and browser policies |
| CSRF rejects POST despite valid CORS | Missing CSRF token with session/cookie | Check repository, header, test `with(csrf())` |
| Admin API called from unknown origin via curl | CORS does not block non-browser clients | Always enforce authentication/authorization |
| Only some URLs have CORS | `registerCorsConfiguration` path mapping or different chains | Check matched path and chain |
| Fails through proxy yet works on localhost | Gateway handles/rewrites OPTIONS or CORS headers | Inspect at each hop |
| Preflight occasionally absent | Browser cached `Access-Control-Max-Age` or request needed no preflight | Check DevTools and cache behavior |
| One origin allowed yet another API fails | Per-handler `@CrossOrigin` and global rules combine differently | Review MVC/bean/CorsFilter config |

### Five-Step Debugging Procedure

1. **Verify URL/origin:** including scheme, host, port; inspect exact `Origin` and request-target.
2. **Isolate preflight:** look for the `OPTIONS` request carrying `Access-Control-Request-Method`. If absent, do not assume the browser had to send one.
3. **Read CORS response:** status plus `Access-Control-Allow-Origin`, Methods, Headers, Credentials, Vary.
4. **Read actual request:** is bearer/cookie sent; where do `hasRole`/`hasAuthority`/`@PreAuthorize`/CSRF/object policies block?
5. **Verify deployment layers:** gateway in front of backend, which filter chain is selected, which CORS source takes effect, and whether preflight caching applies.

Never fix errors by adding `permitAll("/api/**")` or disabling `csrf`/`cors` wholesale. Those strip away security barriers without fixing the true cause.

## 16. Common Design Mistakes and Fixes

### 16.1. Mistake: "Preflight OPTIONS Needs the Same Role as PATCH"

Incorrect. Preflight carries no user credentials, so you usually cannot and should not check the `EDITOR` role there. It only asks **whether the browser may send PATCH with the intended headers from this origin**. Enforcing `project:edit` belongs on the actual PATCH.

### 16.2. Mistake: "Opening OPTIONS Means Enabling CORS"

Incorrect. CORS requires response headers. In modern Spring Security, integrating `http.cors(...)` with a proper configuration source is superior to a broad `OPTIONS /** permitAll` rule.

### 16.3. Mistake: "CORS Is Enough to Protect an API"

Incorrect. CORS primarily restricts JavaScript behavior inside browsers. Non-browser clients are not bound by it. Attackers can send requests with forged `Origin` headers. Authentication/authorization must be enforced on the server.

### 16.4. Mistake: "If CORS Is Allowed, the Frontend Can Read Any Data"

Incorrect. CORS only allows the browser to use cross-origin responses; domain policies still check the specific user, tenant, owner, state, and permissions. An actual request can be denied even when preflight passed.

### 16.5. Mistake: "Every 403 Incident Is a CORS Error"

Incorrect. `403` can come from the CORS processor, CSRF, HTTP permissions, method security, or object policies. Check which request returned the error and which filter handled it.

### 16.6. Mistake: "Just Set allowedOrigins in the Controller"

Not necessarily. When Spring Security sits ahead of MVC, preflight can be blocked by filters before reaching the controller. Ensure CORS is processed early via Spring Security integration or properly ordered filters.

### 16.7. Mistake: "Origin Is the User's Identity"

Incorrect. Origin describes the page/script source under browser policy, not user identity. Never grant admin rights simply because the Origin header matches the frontend.

### 16.8. Mistake: "allowedMethods(GET, POST, PATCH) Authorizes POST"

Incorrect. It only constrains **actual methods at the CORS layer**. If `authorizeHttpRequests` has a deny fallback for POST, actual POST requests remain denied.

### 16.9. Mistake: "Preflight Caching Also Caches User Permissions"

Incorrect. Preflight caching does not replace authentication/authorization checks on actual requests. If a user loses a role, the next actual PATCH must still be denied.

### 16.10. Mistake: "One Chain with CORS Suffices for All Requests"

Incorrect in applications with multiple `SecurityFilterChain`s. Each request is handled by one matching chain; OPTIONS and actual requests must route properly; URLs outside chains must have fallback/protection.

## 17. Durable Implementation Workflow for CORS and Authorization

**Step 1 — List official origins.** Include scheme, hostname, and port of frontends in dev/staging/production. Do not lump `http://localhost:3000` and `http://localhost:5173` together as the same origin.

**Step 2 — List actual requests.** For each route: HTTP method, request headers, cookie or Bearer token usage, CSRF, and who is allowed to call it. This drives allowed methods/headers and security permissions.

**Step 3 — Choose CORS ownership.** CORS can be handled in Spring MVC/Spring Security or at the gateway. Avoid two layers emitting conflicting headers; if the gateway handles preflight, the backend must still authenticate/authorize actual requests.

**Step 4 — Configure CORS explicitly.** Use `CorsConfigurationSource`/`CorsFilter` or MVC CORS combined with `http.cors(...)`, exact origins if using credentials, sufficient allowed methods/headers, and sensible max age.

**Step 5 — Keep actual-request authorization strict.** Separate `project:read` and `project:edit`, protect `/api/admin/**` with roles, use deny fallbacks; services check tenant/owner/resource.

**Step 6 — Define cookie/CSRF strategy.** If using sessions: handle `credentials: "include"`, cookie flags, and CSRF tokens. If Bearer-only, establish token policies and assess CSRF per your threat model.

**Step 7 — Test preflight without a user.** Valid OPTIONS returns proper CORS headers; invalid origin/method/headers are rejected; never require user roles on OPTIONS.

**Step 8 — Test actual requests with and without permissions.** Only `project:edit` passes functional PATCH; missing permissions or another tenant must be blocked. Never infer actual pass from preflight pass.

**Step 9 — Test browser and gateway.** Use DevTools to inspect requests/responses; try `curl` to read headers; verify CORS through the same production proxy and context path.

**Step 10 — Review policy changes.** When adding methods, headers, frontend origins, or SecurityFilterChains, update the CORS allowlist, authorization, CSRF assumptions, and integration tests together.

## 18. Self-Check Questions

**Question 1.** Preflight is `OPTIONS` while the actual request is `PATCH`. Where should `hasAuthority("project:edit")` apply?

**Answer:** On the actual PATCH request (and business service). Preflight is only evaluated by the CORS processor for origin/method/headers and carries no user token to confirm `project:edit`.

**Question 2.** Does `Access-Control-Request-Headers: authorization` in preflight mean the browser already sent the access token?

**Answer:** No. It only indicates the actual request **intends** to carry an Authorization header. The token is sent on the actual request when the frontend and browser execute according to configuration.

**Question 3.** Does adding `requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()` automatically fix all CORS errors?

**Answer:** No. The browser still needs `Access-Control-Allow-Origin`/Methods/Headers and matching credentials policies. Use early CORS integration rather than merely opening authorization for OPTIONS.

**Question 4.** Preflight succeeded, PATCH returned 403. Should you change allowedOrigins right away?

**Answer:** Do not rush to. Preflight was already accepted; check authentication, `project:edit`, CSRF, tenant/owner, and service policy on the actual request.

**Question 5.** With `allowCredentials(true)`, should you return `Access-Control-Allow-Origin: *`?

**Answer:** No. Credentialed cross-origin requests require an explicit allowed origin per browser/Spring contract. Use an exact allowlist or carefully controlled patterns.

**Question 6.** `curl` calling `PATCH /api/admin/data` directly succeeds even though an unknown website hits a CORS error. Which conclusion is right?

**Answer:** CORS does not restrict curl like a browser. If PATCH succeeds when the user lacks permission, that is a server-side authorization flaw; fix roles/permissions/object policies instead of relying on CORS.

**Question 7.** Does a non-preflighted cross-origin GET mean GET is exempt from CORS?

**Answer:** No. The browser still checks CORS headers on the actual response. "No preflight" only means the request qualified to be sent directly.

**Question 8.** A user is logged in at `api.example.test`, yet OPTIONS lacks `JSESSIONID`. Is the browser broken?

**Answer:** No. CORS preflight normally omits user cookies. Spring Security must process preflight without requiring login; cookies/sessions are checked on the actual request if credentials are permitted.

**Question 9.** Does allowing `X-CSRF-TOKEN` in `allowedHeaders` mean CSRF has already been validated?

**Answer:** Not yet. It only lets the browser send that header. `CsrfFilter`/the repository must validate the token value on the actual request per application policy.

**Question 10.** The browser did not send a second OPTIONS, yet PATCH was still denied because the user lost permission. Why is that valid?

**Answer:** The browser may cache preflight per `Access-Control-Max-Age`, while authorization of the actual PATCH must still check current permissions. CORS cache is not a permission cache.

**Question 11.** There are multiple `SecurityFilterChain`s; one chain enabled `cors()`. Why does preflight on another URL still fail?

**Answer:** Because chains are selected by `securityMatcher`/`@Order`. CORS on one chain does not automatically apply to other chains or out-of-scope URLs. Configure and test the actual chain.

**Question 12.** Does `allowedMethods(List.of("GET", "POST", "PATCH"))` allow a user lacking roles to send an admin POST to the server?

**Answer:** CORS may accept cross-origin conditions for POST, yet HTTP authorization must still evaluate admin roles/permissions; lacking permission, the request is denied. Permission to use a method under CORS does not equal permission to perform the action.

**Conclusion:** **Preflight is a browser CORS negotiation, not a business permission request.** Process CORS early so valid OPTIONS requests are not blocked for lacking cookies/tokens; keep roles, authorities, CSRF, and object permissions on actual requests. When debugging, always separate origin/method/header policies from authentication/authorization, then inspect each hop from browser to backend.

## References

- Spring Security — CORS, preflight before authentication, CorsConfigurationSource, Spring MVC integration, multiple chains: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security — Authorize HttpServletRequests, hasAuthority, requestMatchers, denyAll: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — Java configuration and multiple SecurityFilterChains: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Framework — CORS in Spring MVC, credentials and configuration: https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html
- Spring Framework — CorsConfiguration Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/cors/CorsConfiguration.html
- MDN — Cross-Origin Resource Sharing (CORS): https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- MDN — Preflight request: https://developer.mozilla.org/en-US/docs/Glossary/Preflight_request
- MDN — CORS errors: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors
- MDN — Fetch credentials: https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials
