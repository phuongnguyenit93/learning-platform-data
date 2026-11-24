# Distinguishing CORS, authentication, authorization, and CSRF in Spring MVC

## 1. Goal: four mechanisms answering four different questions

Suppose a frontend at `https://app.example.test` calls a Spring Boot API at `https://api.example.test`. A user is logged in, the browser wants to create a new document, the server only allows the `EDITOR` role to perform the operation, and an attacker has another website attempting to submit commands on the user's behalf.

In this scenario, there are **four security decisions** to keep separate:

1. **CORS (Cross-Origin Resource Sharing):** JavaScript from **which origin** is permitted by the browser to read the API response and perform CORS requests according to Fetch rules?
2. **Authentication:** Which **identity** is the request coming from, and is the login proof valid?
3. **Authorization:** What **is that identity permitted to do** with the specific endpoint, object, and data?
4. **CSRF (Cross-Site Request Forgery):** How do we prevent another website from **triggering a state-changing request** using credentials the browser might automatically attach on the user's behalf?

**Key insight:** CORS is not authentication, does not decide whether a user has permission to edit data, and **does not replace CSRF protection**. Authentication does not automatically permit every action; authorization does not automatically protect against forged requests from an authenticated browser.

This lesson includes threat model diagrams, HTTP headers, preflight requests, cookies/credentials, CSRF tokens, plus a **Spring Boot 3.3.x / Java 17 / Spring Security 6.x** application configuring CORS + authentication + authorization + CSRF alongside MockMvc tests. The code runs on the Servlet MVC stack, differing from the corresponding WebFlux APIs.

## 2. Quick comparison table

| Mechanism | Question answered | Where mainly enforced? | Deciding evidence | If it fails |
| --- | --- | --- | --- | --- |
| **CORS** | May JavaScript from another origin read the response and send CORS requests per browser protocol? | Browser, using server response policies | `Origin`, `Access-Control-*`, method, headers, credentials | Browser blocks JS from reading response or skips sending actual request after preflight fails |
| **Authentication** | Who are you? | Server/API/security filter | Session, cookie, HTTP Basic, bearer token, mTLS… | Typically **401** for APIs requiring login; exceptions vary by flow |
| **Authorization** | Are you allowed to do this on this resource? | Server/API, method/service/data layer | Principal, role/authority, ownership, tenant, policy | Typically **403** when authenticated yet lacking permission; sometimes intentional **404** to hide existence |
| **CSRF protection** | Did this state-changing request genuinely originate from a trusted flow? | Server and browser client together | CSRF token, Origin/Referer, SameSite, Fetch Metadata, and session policy | Typically **403** if token is missing/wrong when Spring Security CSRF is enabled |

A request can **pass CORS yet fail authentication**, or **pass authentication and have the right role yet fail CSRF**. Never guess the cause from 403 alone; locate the exception/handler and see which check rejected it.

## 3. Same-Origin Policy and CORS: the browser is the enforcer

An **origin** is defined by the combination of **scheme + host + port**.

| URL | Origin compared to `https://app.example.test` |
| --- | --- |
| `https://app.example.test/home` | Same origin |
| `https://app.example.test/api` | Same origin |
| `http://app.example.test/home` | Different origin: different scheme |
| `https://app.example.test:8443/home` | Different origin: different port |
| `https://api.example.test/home` | Different origin: different host |
| `https://evil.example.test/home` | Different origin: different host |

**Same-Origin Policy (SOP)** restricts the ability of JavaScript from one origin to read data from another origin. CORS is the mechanism allowing a server to **explicitly share certain responses with another origin** via HTTP headers. The rules are enforced by the browser; cURL, Postman, or backend scripts are **not browsers** and do not normally apply the same CORS restrictions.

### 3.1. Simple CORS request and response

Frontend:

```javascript
fetch("https://api.example.test/api/public", {
  method: "GET"
}).then(r => r.json()).then(console.log);
```

The browser automatically adds, in applicable contexts:

```http
GET /api/public HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
```

The server allows this frontend to read the response:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
Content-Type: application/json

{"status":"ok"}
```

If the response does **not** allow that origin, the server **may still** have processed the request and returned HTTP 200, yet the browser blocks JavaScript from accessing the response. The console usually shows a CORS error. This does not mean "the API returned 403." A CORS error can originate from **the browser itself** even though the server processed the request.

At the same time:

- An HTML form on another website can still send requests that the browser allows to be sent cross-origin.
- Images/scripts/links/navigations have their own resource-loading rules; do not oversimplify by thinking every resource goes through fetch CORS.
- Never use the `Origin` request header as proof of identity: non-browser clients can spoof the header.
- CORS does not stop someone from calling the API directly with cURL if server-side authentication/authorization is missing.

### 3.2. What is OPTIONS preflight?

CORS requests that fall outside what the browser treats as safelisted usually must **preflight** first. For example, the frontend sends JSON with Authorization and a CSRF header:

```javascript
fetch("https://api.example.test/api/documents", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ title: "Spring MVC" })
});
```

The browser may ask the server first:

```http
OPTIONS /api/documents HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

A valid preflight may receive:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: Content-Type,X-CSRF-TOKEN,Authorization
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
```

This is an **illustrative** response, not a byte-for-byte default header string. Only if preflight succeeds does the browser **send the actual POST**; that POST must then pass authentication, authorization, CSRF, and validation as usual.

**Preflight is not a login and does not carry the actual request's CSRF token.** Under Fetch, preflight does not send credentials like session cookies; therefore Spring Security must process CORS before login checks so OPTIONS is not rejected for lacking a session. Nor does preflight prove the user holds the `EDITOR` role.

### 3.3. Why is a form-style POST still dangerous when CORS is denied?

A malicious page can contain:

```html
<form action="https://bank.example.test/transfer" method="post">
  <input type="hidden" name="to" value="attacker">
  <input type="hidden" name="amount" value="100">
  <button type="submit">Submit</button>
</form>
```

This is a **threat-modeling** example, not a recommended API to implement. If the user is logged into `bank.example.test` and the browser automatically attaches valid cookies in that context, a server lacking CSRF protection can receive and execute the POST. The attacker **does not need to read the response** to trigger a money transfer.

Many simple requests (in the traditional phrasing) **need no preflight**. CORS restricts **reading responses** by cross-origin scripts, rather than acting as a blanket barrier stopping all requests with side effects. `SameSite` cookies can block cookies in certain cross-site scenarios, but that is no reason to remove CSRF checks.

## 4. Credentialed CORS requests: specific origin, no wildcard

Credentials can include cookies and HTTP authentication. For a cross-origin frontend wanting the browser to send cookies, depending on context it needs:

```javascript
fetch("https://api.example.test/api/documents/1", {
  method: "GET",
  credentials: "include"
});
```

The server permits that origin to read responses with credentials:

```http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
```

**Do not combine `Access-Control-Allow-Origin: *` with a credentialed request.** The browser will refuse to let JavaScript read the response. When multiple trusted origins exist, the server must check an allowlist and return **one specific origin matching the request**, rather than reflecting arbitrary `Origin` headers unchecked.

Important notes:

1. `credentials: "include"` is a frontend-side choice; it **does not replace** server authentication and does not create a cookie if the browser/session does not already have one.
2. `Access-Control-Allow-Credentials: true` only lets JavaScript receive the credentialed response when the origin is also valid. It **does not grant roles**.
3. Cross-site cookies are also subject to `SameSite`, `Secure`, domain/path, HTTPS, and browser third-party cookie restrictions. CORS succeeding **does not guarantee cookies are sent**.
4. `Access-Control-Allow-Origin: null` is not a safe wildcard; `null` origins can arise from sandboxes, file/data URLs, and untrusted environments.
5. If caches store responses that vary by origin, `Vary: Origin` is required. If responses also vary by cookie/login, appropriate `Cache-Control` must be applied to avoid leaking personal data via shared caches.
6. Avoid `allowedOriginPatterns("*")` combined with `allowCredentials=true` for private content: even though the framework can reflect origins, it effectively acts as an unsafe policy **allow-all**.

**Distinguish origin and site:** `https://app.example.com` and `https://api.example.com` are **different origins**, yet may share the same "site" under cookie policies. `SameSite` and SOP/CORS do not measure the same boundary; an untrusted subdomain can alter the CSRF risk analysis.

## 5. Authentication: who is sending the request?

Authentication verifies the identity of a client/user using a specific mechanism, for example:

- Session cookie: browser sends session ID; server resolves the session to a principal.
- HTTP Basic: `Authorization: Basic ...` header carries account credentials via Base64 encoding (not encryption). **Use only over real HTTPS.**
- Bearer token: `Authorization: Bearer <token>` header; server validates signature, expiration, issuer, audience, or introspection per design.
- OAuth2/OIDC login: protocols with tokens/flows and verification steps; do not conflate with authorization.
- mTLS/client certificates: authenticates client identity at the TLS layer.

After authentication, Spring Security holds an `Authentication` containing the `principal` and a set of `GrantedAuthority` instances. Controllers can read it:

```java
@GetMapping("/api/me")
Map<String, String> me(Authentication authentication) {
    return Map.of("username", authentication.getName());
}
```

*This is an illustrative snippet in a Spring Security–protected controller; appropriate imports are required.*

If a request lacks credentials or has invalid ones when authentication is required, HTTP Basic/Bearer APIs typically respond with **401 Unauthorized** and an appropriate challenge. With form login, the server may **redirect to a login page** instead of returning a 401 JSON response. Do not assume 401 vs. 302 solely from a missing cookie; it depends on the `AuthenticationEntryPoint` and request context.

**Do not equate HTTP 401 with CORS:** a frontend may see a CORS error if the API sends 401 without cross-origin read headers; fix CORS and authentication integration separately. Never set `/**` to permitAll just to "make the CORS error go away."

### 5.1. Successful authentication grants no permissions by itself

A user authenticated as `reader` only holds role `READER`. They can view documents yet **cannot** create or delete them if the policy requires `EDITOR`. Authentication only answers "who are you"; actions must still pass authorization.

## 6. Authorization: who is allowed to do what?

Authorization checks policies on **endpoints**, **methods**, **resources**, and sometimes **fields**:

```text
Principal: reader
Authorities: ROLE_READER
GET /api/documents/1        → allowed
POST /api/documents         → denied

Principal: editor
Authorities: ROLE_EDITOR
GET /api/documents/1        → allowed
POST /api/documents         → allowed if CSRF and other conditions pass
```

Spring Security provides `authorizeHttpRequests`:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/documents/**")
        .hasAnyRole("READER", "EDITOR")
    .requestMatchers(HttpMethod.POST, "/api/documents")
        .hasRole("EDITOR")
    .anyRequest().denyAll()
);
```

*Illustrative snippet for SecurityFilterChain; full example in section 10.*

`hasRole("EDITOR")` maps by default to authority `ROLE_EDITOR`, not the string `EDITOR`, unless the role prefix is customized. `requestMatchers` only protects matching HTTP paths/methods; controllers/services still need ownership and tenant checks.

### 6.1. Endpoint authorization is not enough for object authorization

Suppose two users both have role `READER`. API:

```text
GET /api/invoices/101
GET /api/invoices/202
```

If invoice 202 belongs to someone else, a `hasRole("READER")` policy alone is **insufficient**. You must look up the invoice scoped to the user/tenant and verify permissions on the specific object. This is the **Broken Object Level Authorization (BOLA/IDOR)** risk.

A pattern in the service/repository layer:

```java
// Idea; not a standalone program.
Invoice invoice = repository.findById(invoiceId)
        .orElseThrow(NotFoundException::new);
authorizationService.assertCanRead(currentUser, invoice);
return invoice;
```

In multi-tenant systems, it is often better to query data **already filtered by tenant/user** in the DB rather than fetching another user's object and checking afterward, to reduce metadata leakage. Returning 404 instead of 403 when hiding existence is a security/product decision; never use 404 as a substitute for actual permission checks.

### 6.2. 403 does not mean only one kind of error

Both authorization failures **and CSRF token failures** commonly result in HTTP 403. Logs/metrics should distinguish `AccessDeniedException` due to missing authority from `MissingCsrfTokenException` or `InvalidCsrfTokenException`. Never conclude a user lacks a role from status 403 alone.

If the CSRF filter runs before authorization logic and a POST lacks a token, it can return 403 **even when the user is unauthenticated**. To test authentication separately, try a protected GET or a state-changing request with a valid token.

## 7. CSRF: forging requests via browser-attached credentials

CSRF is when another website/app causes a logged-in user's browser to send a **state-changing request** to a target application, exploiting the browser's automatic attachment of cookies, HTTP authentication, or certain other credentials.

Form-style attack flow:

```text
Victim logs into https://bank.example
    │
    ├─ Browser stores valid session cookie
    │
    ▼
Victim opens malicious site https://evil.example
    │
    ├─ Malicious page creates a form POST to bank.example
    ├─ Browser may attach session credential per cookie rules
    ▼
bank.example server receives POST
    ├─ Authentication: victim is valid
    ├─ Authorization: victim has permission to transfer funds
    ├─ If CSRF protection is missing:
    │     → executes transfer without user's intentional action
    └─ If CSRF token is wrong/missing:
          → rejects before changing state
```

**CSRF does not require the attacker to read the bank's response.** The attacker only needs to trigger a successful request. That is why CORS cannot stop all CSRF. This is why tokens or equivalent protections should be required on create, update, and delete methods when authentication relies on automatically attached credentials.

### 7.1. How does a CSRF token work?

In the synchronizer token model:

1. The server generates/stores an unpredictable token bound to the session or security context.
2. The **legitimate** frontend obtains the token via HTML form/meta/API endpoint protected by SOP and strict CORS policies.
3. When sending POST/PUT/PATCH/DELETE, the frontend includes the token in a hidden field or header such as `X-CSRF-TOKEN`.
4. The server compares/verifies the token against the expected token. Wrong or missing → request rejected.

Example request:

```http
POST /api/documents HTTP/1.1
Cookie: JSESSIONID=<session-cookie>
X-CSRF-TOKEN: <issued-token>
Content-Type: application/json

{"title":"New document"}
```

An attack website can make the browser send a session cookie in some contexts, yet normally **cannot read the secret token from the target origin** when SOP, CORS, XSS protections, and token issuance are properly maintained. A token is not authentication: holding a token without a valid identity still grants no business permissions.

### 7.2. Which methods does Spring Security protect by default?

With default Spring Security Servlet settings, CSRF protection is enabled for **unsafe HTTP methods**, typically everything except:

- `GET`
- `HEAD`
- `OPTIONS`
- `TRACE`

Thus `POST`, `PUT`, `PATCH`, and `DELETE` normally require a CSRF token when the CSRF filter is enabled. Safe methods **must not mutate business state**: if a server uses GET to delete data, an attacker can trigger it via an image/link URL even though CSRF configuration treats GET as safe.

"OPTIONS preflight does not need CSRF" does **not** mean "actual POST does not need CSRF." The two requests differ in purpose and credentials.

### 7.3. Is CSRF needed for stateless JWT/Bearer APIs?

It depends on **how credentials are transmitted**, not merely on the words "JWT," "REST," or "stateless":

| Design | Does the browser auto-send credentials cross-site? | CSRF assessment |
| --- | --- | --- |
| Session cookie used for login | Possibly, per cookie policy | **CSRF protection required** for state changes |
| HTTP Basic where browser caches credentials and auto-sends | Possibly | **Do not disable CSRF by default** |
| JWT stored in an auto-attached cookie | Possibly | **CSRF risk still exists** |
| Access token attached explicitly by JS in `Authorization: Bearer ...`, with no ambient cookie/basic auth | Attacker sites normally lack the token to attach a valid header | Classic CSRF risk is greatly reduced; disabling CSRF can be considered **for APIs truly meeting this assumption** |
| Mixed-mode: Bearer header + session cookie on other endpoints | Has an automatic credential path | Classify per security chain/endpoint; do not disable globally |

If a token is stored by JS in `localStorage` or memory, **XSS/token theft** is a separate risk; "no CSRF needed" does not mean "safe in every aspect." A refresh token in a cookie can also create a CSRF surface even if the access token lives in memory.

### 7.4. SameSite and additional layers

`SameSite=Lax`/`Strict` cookies reduce many cross-site cookie-sending cases, however:

- SameSite and **same-origin** are different; subdomains on the same site are not automatically trustworthy.
- Some flows require cross-site cookies, typically demanding `SameSite=None; Secure` and HTTPS, while being governed by browser third-party cookie policies.
- Navigation/redirect behaviors, legacy browsers, and login paths have distinct properties.
- For requests with sensitive credentials, combine tokens, strict origin policies, secure cookies, and appropriate defenses.

Beyond tokens, you can inspect `Origin`/`Referer`, Fetch Metadata headers such as `Sec-Fetch-Site`, and apply custom request protections; never use an arbitrary header easily spoofed by non-browser clients in place of authentication.

### 7.5. Double-submit cookie vs. session token

Some SPAs use a cookie holding the CSRF token where JavaScript reads the value and echoes it in a header. This must be properly designed (binding/HMAC or a framework strategy) to avoid cookie injection/subdomain attacks. In Spring Security, `CookieCsrfTokenRepository` serves some of these patterns. However, Spring Security 6 uses **deferred tokens** and **XOR masking** to protect against BREACH in rendering; exposing tokens to an SPA requires understanding `CsrfTokenRequestHandler`, not simply "copying the XSRF-TOKEN cookie into a header" for every configuration.

The demo in section 10 intentionally uses the **default session-based CSRF token** and a GET endpoint issuing the token to a trusted frontend, avoiding the claim that specialized SPA/cookie setups work out of the box without configuring handlers.

## 8. Outcome matrix: one request, multiple security gates

Consider the endpoint:

```text
POST /api/documents
Origin: https://app.example.test
Required role: EDITOR
CSRF protection: enabled
CORS allowlist: https://app.example.test
```

| Scenario | CORS | Authentication | Authorization | CSRF | Typical outcome |
| --- | --- | --- | --- | --- | --- |
| Allowed frontend origin, editor logged in, valid CSRF token | Pass | Pass | Pass | Pass | 201 Created |
| Allowed origin, no credentials, protected GET endpoint | Pass | Fail | — | N/A for GET | 401 / login flow |
| Allowed origin, reader has valid CSRF token, tries POST | Pass | Pass | Fail | Pass | 403 |
| Allowed origin, editor tries POST without CSRF token | Pass | Pass | Pass by role | Fail | 403, no data created |
| Unknown origin, POST CORS preflight disallowed | Fail | Identity not evaluated on preflight | — | — | Browser skips actual POST; server preflight may return 403 |
| Unknown origin, simple form POST with auto-sent credentials | Browser blocks reading response | May pass | May pass | Fail if CSRF protects properly | Server blocks state-changing request |
| CORS allow-all public endpoint, no login required | Pass | N/A | Public | N/A if read-only | Client can read public response |

**You cannot determine a single fixed status** for the entire matrix without knowing the entry point, filter order, preflight type, CSRF policy, resource rules, and browser cookie behavior. The matrix is an explanatory model for a typical application, not a mandatory rule for every Spring Security app.

### 8.1. How do 401, 403, and CORS failures differ?

**401** means the server requires valid credentials for the resource. Often includes `WWW-Authenticate` with Basic/Bearer.

**403** means the server understood the request but refuses it; this can be due to missing authority, invalid CSRF token, or another filter. Unauthenticated requests can also receive 403 in certain flows, notably when CSRF checks unsafe methods.

**CORS failure** means the browser blocked access to the response or skipped the actual request because preflight failed. There does not have to be an HTTP 403: the server may return 200 without CORS headers and JavaScript still sees an error. Network tab and backend logs distinguish them.

## 9. SecurityFilterChain: processing order matters

Spring Security Servlet is implemented via a filter chain (`FilterChainProxy`). MVC controllers are invoked **after** checks in the security filters as the request traverses the chain.

Conceptual flow:

```text
Browser
  → Servlet container
    → Spring Security FilterChainProxy
       → CORS processed before auth (when integrated properly)
       → Authentication filters / SecurityContext
       → CSRF token validation for unsafe methods
       → Authorization decisions
       → DispatcherServlet
          → Spring MVC controller
          → HTTP response
```

In reality Spring Security contains many filters and the exact order depends on version/security chains; the diagram does **not** guarantee every app uses exactly those four filters in that exact order. Use Spring Security configuration rather than creating multiple competing Servlet Filters manually.

### 9.1. Why must CORS be processed before authentication?

Preflight does not send authentication cookies. If the application demands login/session on preflight, the browser cannot execute legitimate cross-origin POSTs. Spring Security recommends integrating CORS via a `CorsConfigurationSource` (such as `UrlBasedCorsConfigurationSource`) and `http.cors(...)`, so preflight is processed properly before authentication.

**Note:** Never solve this by disabling authentication for all endpoints. Only handle CORS preflight independently; actual requests still require credentials/roles/CSRF per policy.

### 9.2. Spring MVC @CrossOrigin and Security configuration

`@CrossOrigin` can declare CORS on an MVC controller/method. `WebMvcConfigurer#addCorsMappings` declares general CORS at the Spring MVC layer. However, when using Spring Security, especially with preflight, CORS must be properly integrated into the Security filter chain. An explicit `CorsConfigurationSource` unifies policy at the filter layer.

Example:

```java
@CrossOrigin(origins = "https://app.example.test")
@GetMapping("/api/public")
String example() { return "public"; }
```

This is an illustrative snippet; **it does not grant access** to a protected endpoint. If `SecurityFilterChain` rejects the request for lacking auth, adding `@CrossOrigin` does not make the user authenticated. When declaring multiple CORS sources, check whether policies conflict or override each other.

## 10. Spring Boot 3 + Java 17 app: integrating all four layers

The demo uses:

- HTTP Basic to provide easily observable identities `reader` and `editor`. `{noop}` passwords are **for demo only**, never for production.
- URL authorization: GET documents for READER or EDITOR; POST create document only for EDITOR.
- CORS allowlist for one origin `https://app.example.test`; credentialed responses carry the explicit origin.
- CSRF **enabled by default** on unsafe methods; demo issues a CSRF token via GET in the same session.
- `MockMvc` to demonstrate 401, role-based 403, CSRF-based 403, 201 success, allowed/rejected preflight, and allowed-origin responses.
- Temporary ConcurrentHashMap repository to avoid database setup; illustrates security behavior only.

### 10.1. Project structure

```text
cors-auth-csrf-demo/
├── pom.xml
└── src/
    ├── main/java/example/
    │   ├── WebSecurityDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DocumentController.java
    └── test/java/example/
        └── SecurityBoundaryTest.java
```

### 10.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>cors-auth-csrf-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
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
            <artifactId>spring-boot-starter-validation</artifactId>
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
```

### 10.3. WebSecurityDemoApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSecurityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebSecurityDemoApplication.class, args);
    }
}
```

### 10.4. SecurityConfig.java

```java
package example;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .cors(Customizer.withDefaults())
                // CSRF is enabled by default; declared explicitly
                // so REST APIs are not mistakenly assumed to disable CSRF.
                .csrf(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers(
                            HttpMethod.GET, "/api/csrf")
                        .authenticated()
                    .requestMatchers(
                            HttpMethod.GET, "/api/documents/**")
                        .hasAnyRole("READER", "EDITOR")
                    .requestMatchers(
                            HttpMethod.POST, "/api/documents")
                        .hasRole("EDITOR")
                    .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of(
                "https://app.example.test"));
        config.setAllowedMethods(List.of(
                "GET", "POST", "OPTIONS"));
        config.setAllowedHeaders(List.of(
                "Authorization", "Content-Type", "X-CSRF-TOKEN"));
        config.setAllowCredentials(true);
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}reader-pass")
                .roles("READER")
                .build();

        UserDetails editor = User.withUsername("editor")
                .password("{noop}editor-pass")
                .roles("EDITOR")
                .build();

        return new InMemoryUserDetailsManager(reader, editor);
    }
}
```

**Component breakdown:**

- `http.cors(Customizer.withDefaults())` integrates CORS into Spring Security. The `UrlBasedCorsConfigurationSource` bean defines the mapping under `/api/**`.
- `setAllowedOrigins(...)` accepts only the declared origin; no wildcard when `allowCredentials=true`.
- `setAllowedMethods(...)` lists methods accepted by CORS, yet is **not** HTTP method authorization; POST still requires role EDITOR.
- `setAllowedHeaders(...)` lets the browser preflight the headers it actually needs to send.
- `setMaxAge(3600L)` is how long the browser may cache the preflight result, not login or CSRF token expiration.
- `requestMatchers(GET,...).hasAnyRole(...)` and `requestMatchers(POST,...).hasRole(...)` establish **authorization policy**, independent of CORS.
- `.csrf(...)` retains default CSRF protection; an EDITOR's POST still gets 403 when missing the token.
- `httpBasic(...)` provides simple authentication. Browsers can automatically resend cached Basic credentials, so do not skip CSRF just because it says "Basic."
- `{noop}` plaintext passwords are **for this lesson only**, never for real use. Production requires strong password encoders, secret handling, TLS, rate limiting, and real identity management.

### 10.5. DocumentController.java

```java
package example;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

record CreateDocumentRequest(@NotBlank String title) {}

record DocumentResponse(long id, String title) {}

@RestController
public class DocumentController {

    private final AtomicLong nextId = new AtomicLong(2);
    private final Map<Long, DocumentResponse> documents =
            new ConcurrentHashMap<>();

    public DocumentController() {
        documents.put(1L, new DocumentResponse(1L, "Public sample"));
    }

    @GetMapping("/api/documents/{id}")
    ResponseEntity<DocumentResponse> read(@PathVariable long id) {
        DocumentResponse found = documents.get(id);
        return found == null
                ? ResponseEntity.notFound().build()
                : ResponseEntity.ok(found);
    }

    @PostMapping("/api/documents")
    ResponseEntity<DocumentResponse> create(
            @Valid @RequestBody CreateDocumentRequest request) {

        long id = nextId.getAndIncrement();
        DocumentResponse doc =
                new DocumentResponse(id, request.title());

        documents.put(id, doc);
        return ResponseEntity.status(HttpStatus.CREATED).body(doc);
    }

    @GetMapping("/api/csrf")
    Map<String, String> csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken) request.getAttribute(
                CsrfToken.class.getName());

        // Touch getToken() so the deferred token is generated/saved.
        return Map.of(
                "token", token.getToken(),
                "headerName", token.getHeaderName());
    }
}
```

The `GET /api/csrf` endpoint **requires login** per URL policy and returns the token to a trusted frontend. The token is generated by the server in the session when accessed, and the browser must retain the session cookie to send with POST. In Spring Security 6, the default token mechanism can use **deferred loading and XOR masking**; the frontend should send **the token value received from the endpoint** in the header named by the endpoint, rather than reading a cookie independently.

**Note:** this endpoint can be read via JavaScript from an **allowlisted origin** when valid credentials and proper CORS headers are present. Do not cache the token via CDN, and never log tokens in analytics/logs/URLs. This models backend+frontend flow, not production account/session lifecycles, cookie configuration, or persistence.

### 10.6. Running with Maven and testing with cURL

Use JDK 17+ and Maven:

```bash
mvn test
mvn spring-boot:run
```

GET without authentication:

```bash
curl -i http://localhost:8080/api/documents/1
```

Expected **401 Unauthorized** per the HTTP Basic demo. GET with reader account:

```bash
curl -i -u reader:reader-pass \
  http://localhost:8080/api/documents/1
```

Expected 200, body:

```json
{"id":1,"title":"Public sample"}
```

POST as editor **without a CSRF token**:

```bash
curl -i -u editor:editor-pass \
  -H "Content-Type: application/json" \
  -d '{"title":"New document"}' \
  http://localhost:8080/api/documents
```

Expected **403 Forbidden** due to CSRF; editor has the right role, yet that does not waive the token requirement.

Fetch the session-bound token and reuse it. Example on a POSIX shell with Python 3:

```bash
curl -sS -u editor:editor-pass -c cookies.txt \
  http://localhost:8080/api/csrf > csrf.json

TOKEN=$(python3 -c \
  'import json; print(json.load(open("csrf.json"))["token"])')

curl -i -u editor:editor-pass -b cookies.txt \
  -H "X-CSRF-TOKEN: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"New document"}' \
  http://localhost:8080/api/documents
```

Expected **201 Created** with a body containing the assigned `id` and submitted title. IDs may vary across runs/tests, so do not hardcode a single number across all requests. On Windows PowerShell, use `curl.exe`, PowerShell variable syntax, and PowerShell JSON parsing instead of the POSIX shell commands above.

**Important:** cURL **does not enforce CORS like a browser**. If you manually send `Origin: https://evil.example.test` with cURL and still see a response/status, that does not prove a browser is allowed to read it. To test CORS, verify preflight/actual response headers and test from the corresponding browser origin.

### 10.7. Illustrative frontend fetch

Suppose the trusted website already has an appropriate authentication method and the browser holds the required credentials. Client logic can look like:

```javascript
const api = "https://api.example.test";

const csrfResponse = await fetch(api + "/api/csrf", {
  credentials: "include"
});
if (!csrfResponse.ok) throw new Error("Cannot read CSRF token");

const csrf = await csrfResponse.json();

const saveResponse = await fetch(api + "/api/documents", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    [csrf.headerName]: csrf.token
  },
  body: JSON.stringify({ title: "New document" })
});
if (!saveResponse.ok) throw new Error("Cannot create document");
```

**This is frontend flow pseudocode**, not a complete automatic HTTP Basic login browser demo. The browser must be authenticated beforehand; cross-site cookie environments must satisfy SameSite/Secure policies; with HTTP Basic, appropriate login/challenge/Authorization handling may be needed. Do not conclude from this example that merely adding `credentials: "include"` creates a session or logs a user in.

In pages running on the same origin as the API, CORS is usually **not needed**. CORS only applies when scheme/host/port differ. Never open CORS broadly just because you use fetch.

## 11. MockMvc: testing the four security gates separately

File `src/test/java/example/SecurityBoundaryTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityBoundaryTest {

    @Autowired
    MockMvc mvc;

    @Test
    void protectedGetWithoutAuthenticationIs401() throws Exception {
        mvc.perform(get("/api/documents/1")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCanReadDocument() throws Exception {
        mvc.perform(get("/api/documents/1")
                    .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(1))
            .andExpect(jsonPath("$.title").value("Public sample"));
    }

    @Test
    void readerCannotPostEvenWithValidCsrf() throws Exception {
        mvc.perform(post("/api/documents")
                    .with(httpBasic("reader", "reader-pass"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Forbidden document\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorCannotPostWithoutCsrf() throws Exception {
        mvc.perform(post("/api/documents")
                    .with(httpBasic("editor", "editor-pass"))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Missing CSRF\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorCanPostWithCsrf() throws Exception {
        mvc.perform(post("/api/documents")
                    .with(httpBasic("editor", "editor-pass"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Allowed document\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.title").value("Allowed document"));
    }

    @Test
    void allowedPreflightDoesNotRequireLogin() throws Exception {
        mvc.perform(options("/api/documents")
                    .header(HttpHeaders.ORIGIN,
                            "https://app.example.test")
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                            "POST")
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                            "authorization,content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                    "https://app.example.test"))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                    "true"));
    }

    @Test
    void deniedOriginFailsPreflight() throws Exception {
        mvc.perform(options("/api/documents")
                    .header(HttpHeaders.ORIGIN,
                            "https://evil.example.test")
                    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                            "POST"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void allowedOriginStillNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/documents/1")
                    .header(HttpHeaders.ORIGIN,
                            "https://app.example.test")
                    .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void allowedOriginCanReadAuthenticatedResponse() throws Exception {
        mvc.perform(get("/api/documents/1")
                    .with(httpBasic("reader", "reader-pass"))
                    .header(HttpHeaders.ORIGIN,
                            "https://app.example.test"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                    "https://app.example.test"));
    }

    @Test
    void csrfEndpointNeedsLoginAndReturnsToken() throws Exception {
        mvc.perform(get("/api/csrf"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/csrf")
                    .with(httpBasic("editor", "editor-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.headerName").value("X-CSRF-TOKEN"))
            .andExpect(jsonPath("$.token").isNotEmpty());
    }
}
```

**What each test teaches:**

- `protectedGetWithoutAuthenticationIs401`: **authentication** failure, not CORS.
- `readerCannotPostEvenWithValidCsrf`: insufficient role → **authorization** failure; a token does not grant privileges.
- `editorCannotPostWithoutCsrf`: valid identity/role yet missing **CSRF token** → 403.
- `editorCanPostWithCsrf`: all relevant conditions satisfied → 201.
- `allowedPreflightDoesNotRequireLogin`: **CORS OPTIONS** can succeed even without a session/login.
- `deniedOriginFailsPreflight`: CORS policy rejects the origin; does not imply anything about authentication of the actual request.
- `allowedOriginStillNeedsAuthentication`: allowlisting an origin does not authenticate the user.
- `csrfEndpointNeedsLoginAndReturnsToken`: token issuance through a protected endpoint.
- The GETs with `Origin` verify CORS headers while preserving authentication/authorization policies.

**Limitations:** MockMvc does not execute browser SOP/CORS enforcement. It verifies **server response headers and Spring Security decisions**, rather than fully simulating how a browser blocks JavaScript from reading responses. For end-to-end integration tests, use a real browser across two origins, proxy/HTTPS, and production-like cookie settings.

## 12. Disable CSRF only with a clear justification

Sometimes developers copy:

```java
http.csrf(csrf -> csrf.disable());
```

thinking "REST uses JSON, so CSRF isn't needed." **This is a false conclusion:** a JSON endpoint can still rely on session cookies, browser HTTP Basic, or a JWT inside a cookie. The JSON media type does not decide CSRF risk; attacks via simple requests, content-type coercion, upload/form routes, login/logout endpoints, or misconfigurations can still cause side effects.

Only consider disabling CSRF on a **truly stateless security chain/endpoint** when you confirm credentials are **never automatically attached by the browser** and cross-site requests cannot inherit user privileges. Even then, keep authentication/authorization, HTTPS, token validation, sensible CORS allowlists, and XSS protection.

Illustrative **separate** configuration example for an OAuth2 Resource Server API:

```java
// Suitable only if requests do not accept ambient credentials
// and auth strictly requires a properly issued Bearer header.
http.securityMatcher("/stateless/**")
    .csrf(csrf -> csrf.disable())
    .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()));
```

*Do not paste this into the runnable Boot project in section 10. Running it requires the OAuth2 Resource Server dependency, JwtDecoder/issuer configuration, and a complete authorization policy.* When using multiple `SecurityFilterChain` beans, understand each chain's matcher/order so you do not accidentally leave an endpoint unprotected.

## 13. Common design mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating CORS as authentication | Allowed origin lets anonymous callers hit the API if permitAll | Protect endpoints with authentication |
| Treating a CORS allowlist as authorization | Underprivileged user can still attempt edits | Check roles/authorities/ownership on the server |
| Treating CORS as CSRF prevention | Form/simple requests can mutate state even if script cannot read response | Keep CSRF protection when ambient credentials exist |
| Blocking OPTIONS preflight with login | Browser never sends actual POST even for logged-in users | Integrate CORS before Security auth |
| Setting `Access-Control-Allow-Origin: *` + credentials | Browser rejects credentialed response | Specific origin from allowlist; proper policy |
| Reflecting any Origin with `Access-Control-Allow-Credentials: true` | Any origin can read credentialed data | Strict allowlist, never reflect arbitrarily |
| Assuming 403 always means missing role | CSRF failures also often return 403 | Separate Missing/InvalidCsrfToken from authorization denials |
| Assuming a CORS error means the API returned 403 | Server may return 200 yet JS cannot read it | Inspect Network tab, OPTIONS/actual response headers |
| Protecting `/api/**` by role only | IDOR/BOLA against other users' data | Enforce per-object/tenant permission checks |
| Storing JWT in a cookie and disabling CSRF | Browser auto-sends the JWT cookie | Protect against CSRF just like session cookies |
| Using HTTP Basic assuming it is stateless and CSRF-safe | Browser may cache and auto-send credentials | Analyze browser credential behavior; keep CSRF when needed |
| Using `{noop}` for real passwords | Passwords exposed if config/DB is read | Hash with strong encoder, TLS, secret policy |
| Client sends `credentials:"include"` yet no cookie appears | SameSite/Secure/third-party cookie policy | Check cookies, HTTPS, and domain/path |
| Letting GET mutate state | GET normally skips CSRF checks and is easy to trigger | Move side effects to unsafe methods |
| Trusting `Origin` request header as identity | Non-browser clients can spoof headers | Authenticate independently with credentials |
| Relying solely on SameSite when untrusted subdomains exist | Same-site differs from same-origin; can be exploited | Tokens, origin policies, trust boundaries |
| Exposing CSRF tokens in logs, URLs, or CDNs | Attackers can reuse tokens | Never log/shared-cache/expose; control issuance |
| Disabling CSRF globally to get a 201 in tests | Strips production protection | Use `with(csrf())` in tests and fix client token flow |
| Adding CORS headers to errors while forgetting auth | Frontend can read 401/403 yet data isn't secured | CORS, auth, and authorization are separate layers |
| Putting bearer tokens in localStorage claiming zero risk | XSS can steal access tokens | XSS hardening, CSP, token rotation, minimal scopes |
| Allowing arbitrary methods/headers/origins | Overly wide cross-origin attack surface | Allowlist only required origins/methods/headers |

## 14. Practical deployment checklist

1. **Threat model**: browser app or machine-to-machine? Are credentials attached automatically?
2. **Endpoint classification**: public GET, authenticated read, write, admin, object ownership, upload, login/logout.
3. **Choose authentication**: session+form login, OIDC, internal HTTP Basic, Bearer JWT/OAuth2, mTLS…; do not mix uncontrollably.
4. **Authorization**: deny-by-default URL policy plus service-level tenant/ownership checks; enforce method/object/field controls.
5. **CORS**: only trusted origins, needed methods/headers; never `*` for credentialed origins; preflight runs before auth.
6. **CSRF**: keep protection for browsers using cookies/ambient credentials; client fetches and sends tokens securely.
7. **HTTP semantics**: GET/HEAD create no state; unsafe methods have validation, transactions, and auditing.
8. **Cookies and sessions**: `HttpOnly`, `Secure`, `SameSite`, session fixation/logout, cookie scope, third-party cookie policies.
9. **Headers and caching**: `Vary: Origin`, private/no-store for personal data/CSRF tokens; HTTPS and appropriate HSTS.
10. **XSS**: CSRF tokens do not stop XSS; escape HTML, avoid unsafe eval/inline scripts, enforce CSP.
11. **Tests**: 401 anonymous, 403 reader write, 403 missing CSRF, 201 editor+token, allowed/denied preflight, origin vs. role, object-level ownership.
12. **Observability**: log request ID, endpoint, authenticated principal/authorities per privacy policy, and policy failure type; never log tokens, passwords, or session cookies.
13. **Deployment**: HTTPS at the reverse proxy with accurate scheme/origin; configure forwarded headers properly so CORS/redirects/cookies do not drift.
14. **Real browser**: test credentialed fetch, OPTIONS, and SameSite cookies on real domains; MockMvc alone is not enough to conclude browser behavior.

## 15. Knowledge check

**1.** A frontend at `https://app.example.test` calls `https://api.example.test` — is this cross-origin?  
**Answer:** Yes, different host; even though they may be same-site under some cookie policies.

**2.** The server returns HTTP 200 without `Access-Control-Allow-Origin`; can browser JS read the body?  
**Answer:** Not under CORS if cross-origin. The server may still have processed the request.

**3.** Does allowing CORS for origin X automatically log in users from X?  
**Answer:** No. Authentication requires valid credentials.

**4.** An authenticated user lacks the EDITOR role while CORS and CSRF are both valid; can a POST create a document?  
**Answer:** No. Authorization must reject it.

**5.** An editor is logged in and permitted to create documents yet lacks a CSRF token; what is the result in the demo?  
**Answer:** HTTP 403, no document created.

**6.** Does OPTIONS preflight need a session cookie?  
**Answer:** Normally it carries no credentials under browser CORS preflight, so CORS must be processed before auth.

**7.** Why does CORS not replace CSRF?  
**Answer:** The browser can still send certain cross-origin requests causing side effects even when the attacker cannot read the response.

**8.** Are `Access-Control-Allow-Origin: *` and `Access-Control-Allow-Credentials: true` valid for credentialed fetch?  
**Answer:** No, browsers reject a wildcard origin on credentialed responses.

**9.** The browser sends cookies automatically and the API uses a JWT inside a cookie. Can CSRF still exist?  
**Answer:** Yes, because a JWT inside a cookie still exhibits ambient credential behavior.

**10.** If a Bearer header is attached explicitly by JS and the server never uses cookies or basic credentials, is session-style CSRF needed?  
**Answer:** Classic CSRF risk is reduced/unneeded in that threat model, yet authentication, authorization, CORS, XSS, and token security remain essential.

**11.** Does a successful POST CORS preflight prove the user has permission to POST?  
**Answer:** No. The actual POST still needs login/role/token.

**12.** Is HTTP 403 always an authorization error?  
**Answer:** No. CSRF failures and other policy violations can also produce 403.

**13.** What does a protected GET with wrong authentication usually return in an HTTP Basic API?  
**Answer:** 401, typically with `WWW-Authenticate`.

**14.** Is URL rule `hasRole("READER")` enough to prevent reading another user's invoice?  
**Answer:** No; object-level/tenant ownership authorization is required.

**15.** Does `SameSite=Lax` automatically make every cross-origin request safe?  
**Answer:** No; SameSite differs from SOP/CORS, behavior depends on navigation/context, and other risks remain.

**16.** Why should cURL not be used to "prove the browser has no CORS error"?  
**Answer:** cURL does not enforce browser SOP and CORS.

**17.** In Spring Security tests, why use `with(csrf())` on POST?  
**Answer:** To simulate a valid CSRF token so the test reaches authorization/controller logic instead of being rejected earlier by the filter.

**18.** If logged in with HTTP Basic yet creating a document returns 403, what should you check?  
**Answer:** CSRF token and role/policy, then validation and exception logs; not just CORS.

**19.** Is `X-CSRF-TOKEN` a bearer access token?  
**Answer:** No. A CSRF token proves a request conforms to anti-forgery policy; it does not replace authentication.

**20.** If the CORS allowlist only contains `https://app.example.test`, can a malicious site still call the API via a backend script?  
**Answer:** Yes, HTTP requests can be sent outside a browser; the server must use authentication/authorization to protect itself rather than relying on CORS.

## 16. Official sources worth reading

- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): CORS before Spring Security, integration with `UrlBasedCorsConfigurationSource`.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): token repositories, deferred tokens, request handlers, and testing.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `authorizeHttpRequests`, URL/method rules, and authorities.
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `Authentication`, principal, authorities, and SecurityContext.
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `SecurityMockMvcRequestPostProcessors.csrf()`.
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): CORS in Spring MVC.
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): origins, preflight, credentials, and browser enforcement.
- [MDN — Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy): scheme/host/port boundaries.
- [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): synchronizer/double-submit tokens, SameSite, origin checks.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny-by-default and object-level permissions.

**Final rule:** **CORS** decides which browser JS origins may share responses; **authentication** establishes identity; **authorization** verifies concrete permissions; **CSRF protection** checks whether state-changing requests were forged by another site using auto-sent credentials. Proper web security is **all four working together**, never enabling a single header and assuming the other layers are done.
