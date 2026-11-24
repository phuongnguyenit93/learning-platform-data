# Distinguishing CORS from CSRF to Choose the Right Defenses

> **Spring Security fundamentals → CORS.** CORS (*Cross-Origin Resource Sharing*) and CSRF (*Cross-Site Request Forgery*) both arise in browser applications, yet they **solve two different problems**. CORS is a policy allowing or restricting **JavaScript from another origin to access resources/read responses** via the browser. CSRF is protection so that **an untrusted page cannot abuse credentials automatically sent by the browser to perform state changes**. This lesson helps determine **when CORS is needed, when CSRF is needed, and when both are needed**, configure Spring Security 6 / Spring Boot 3.x / Java 17+, and test both mechanisms independently.

## 1. Opening question: why doesn't enabling CORS solve CSRF?

Suppose:

- The official frontend is at `https://app.example.test`.
- The user-data API is at `https://api.example.test`.
- The browser holds the API's login cookie, so when sending qualifying requests, the browser may attach the cookie per policy.
- The user occasionally opens a page at `https://evil.example.net`, an untrusted origin.

There are two independent scenarios.

**Scenario A — the official frontend wants to read data from the API:**

```javascript
const response = await fetch("https://api.example.test/api/profile", {
  credentials: "include"
});
const data = await response.json();
```

JavaScript running on `app.example.test` is calling an API on `api.example.test`. That is a **cross-origin fetch**. The browser requires the API to have a CORS policy permitting the frontend to read the response. If the browser sees no matching CORS headers, the script usually cannot read the response, even if the network request was sent.

**Scenario B — an untrusted page tries to modify data:**

```html
<form action="https://api.example.test/api/email" method="post">
  <input name="newEmail" value="attacker@example.net">
  <button type="submit">Continue</button>
</form>
```

A traditional HTML form can **send a cross-origin request without needing CORS permission to read the response**. If the login cookie is automatically sent by the browser and the API requires no anti-CSRF proof, the operation can execute even though the external site **can never read the response**. A strict CORS policy is a useful defense layer, yet cannot replace evaluating **CSRF for auto-sent credentials**, designing safe HTTP methods, and enforcing access controls.

**Short takeaway:** CORS asks “Which origin's JavaScript may use/read this resource through the browser?”; CSRF asks “Did this state-changing request genuinely originate from a user-authorized flow, rather than being triggered alongside cookies by another website?”.

## 2. Origin and site: two concepts that are not synonymous

### 2.1. Origin is the tuple of scheme, host, port

An origin is defined by **scheme + host + port**. Compare:

| URL A | URL B | Same origin? | Explanation |
|---|---|---|---|
| `https://shop.example.test` | `https://shop.example.test/cart` | Yes | Same scheme, host, port |
| `https://shop.example.test` | `https://api.example.test` | No | Different hostname |
| `https://shop.example.test` | `http://shop.example.test` | No | Different scheme |
| `https://shop.example.test:443` | `https://shop.example.test` | Yes under URL standards when using default port | Explicit/default port equivalent |
| `https://shop.example.test` | `https://shop.example.test:8443` | No | Different port |
| `http://localhost:3000` | `http://localhost:8080` | No | Different port |

Browsers use the **Same-Origin Policy** as a baseline. CORS is a mechanism for **relaxing cross-origin script response-reading in a controlled way**, not a user identity system.

### 2.2. Site is not origin

`SameSite` cookies use the concept of **site** (in modern browsers, typically scheme plus registrable domain) rather than origin. Two subdomains `https://app.example.test` and `https://api.example.test` can be **cross-origin yet same-site**. Therefore:

- A request may **require CORS** even while remaining same-site.
- `SameSite=Lax` or `Strict` does not turn subdomains into the same origin.
- Cookie policy may allow sending cookies by “site” while CORS still decides whether scripts may read responses.
- If frontend and API are genuinely cross-site (different registrable domains), `SameSite=None; Secure` cookies or another identity design may be needed, though browsers also apply third-party cookie policies; CORS **does not force browsers to send cookies**.

**Do not conclude “CORS error = missing cookie” or “SameSite enabled = no need to consider CSRF”.** Both mechanisms evaluate different boundaries.

## 3. Comparison table: CORS and CSRF

| Property | CORS | CSRF |
|---|---|---|
| Full name | Cross-Origin Resource Sharing | Cross-Site Request Forgery |
| Core problem | Cross-origin JavaScript permission to access/read responses | Forged requests sent with browser-attached credentials |
| Primary enforcement | Browser inspects `Origin` and CORS response headers; server/framework can reject Origin | Server verifies CSRF token or equivalent proof on unsafe requests |
| Primary signals | `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` | `_csrf` in forms, `X-CSRF-TOKEN`/`X-XSRF-TOKEN` in headers, session/cookie repository |
| Common response headers | `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`, `Access-Control-Allow-Methods` | No “Access-Control-Allow-CSRF”; tokens are issued via views/APIs/cookies by design |
| Relevant to GET? | Yes, cross-origin JSON GETs are very common | Normally no token required for safe GETs |
| Relevant to POST? | Yes; cross-origin POSTs may need preflight or be simple requests | Yes; state-changing POSTs normally require tokens with cookie auth |
| Does enabling one replace the other? | No | No |
| Does CORS authenticate users? | No | No |
| Does a CSRF token grant object read access? | No | No |
| Machine-to-machine APIs | Browser CORS usually does not apply | Browser-cookie CSRF usually does not apply if no auto-sent credentials |
| Typical error | Browser reports blocked by CORS; Spring may return 403 for disallowed Origin | Spring `CsrfFilter` typically returns 403 on missing/invalid token |

**Key nuance:** CORS can cause Spring Security/Spring MVC to reject requests with a disallowed Origin **right on the server**. Yet the standardized protection of CORS is primarily browser access control; you cannot infer “no side effects occurred” from “frontend could not read the response”. A cross-site form can still be dispatched; moreover, non-browser clients are not bound by browser CORS policies. To stop forged requests in cookie-based apps, define a proper CSRF policy per your threat model.

## 4. How does CORS work?

### 4.1. Simple requests: may have no preflight

Some **CORS-safelisted** requests can be sent directly, such as an ordinary GET or a POST with `Content-Type: application/x-www-form-urlencoded` and no unusual custom headers.

```http
GET /api/profile HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Cookie: JSESSIONID=<browser-cookie>
```

If the API allows the official origin and returns an appropriate response:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
Content-Type: application/json

{"username":"alice"}
```

The browser may let scripts at `app.example.test` read the response when request/response and credential policies align. If the API returns `Access-Control-Allow-Origin: https://evil.example.net` to an attacker, JavaScript at that origin can read data for which the browser attaches matching cookies; that represents a very high level of trust.

**Not every response must carry these exact headers**; this is a credentialed sample. For a public non-credentialed resource, the policy can differ. CORS headers do not replace authentication/authorization, so private data still needs the usual protection layers.

### 4.2. Non-simple requests: browser sends OPTIONS preflight

A frontend wants to send JSON with a custom header:

```javascript
fetch("https://api.example.test/api/theme", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ theme: "dark" })
});
```

Before sending the actual POST, the browser usually issues a preliminary check:

```http
OPTIONS /api/theme HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

The server replies, if policy agrees:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: content-type,x-csrf-token
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
Vary: Origin
```

Only then does the browser send the **actual POST** per policy. Preflight is a safe `OPTIONS` request asking permission for **origin, method, and headers**, not a state-changing request, and it carries no POST CSRF token. CORS preflight typically **sends no login cookies**; Spring Security must integrate CORS handling early enough that this OPTIONS request is not treated as an anonymous request needing login.

### 4.3. The actual request still needs security checks

After preflight succeeds, the actual POST still passes through:

```text
Browser -> OPTIONS preflight -> CORS policy permits
                      |
                      v
Browser -> actual POST (credential + CSRF header)
                      |
                      v
           CORS checks Origin
                      |
                      v
           CSRF token validation
                      |
                      v
           Authentication + Authorization
                      |
                      v
           Controller + service + data scope
```

Passing preflight **does not mean the POST is permitted to modify data**. CORS does not validate CSRF tokens; CSRF does not identify the user; authentication does not prove the user has rights on another tenant's record. Each layer has its own responsibility.

### 4.4. Why a CORS “block” does not guarantee the request never reached the server

A safelisted GET or POST can **be sent by the browser before the browser knows whether the response may be read**. Without matching CORS headers, the browser prevents JavaScript from **reading the response**, without automatically rolling back side effects that occurred. CORS-enabled server frameworks can reject actual requests with a wrong Origin, yet that is a server-side policy/filter behavior, **not a guarantee that any system using only CORS is fully protected against CSRF**.

This is why GET must be kept safe, CSRF tokens enforced on cookie-based POSTs, and data protection rules applied. A payment endpoint using GET is a severe design flaw even if CORS is locked down.

## 5. CORS with credentials: never use wildcards arbitrarily

### 5.1. Browser credentials and `fetch`

In `fetch`:
- `credentials: "same-origin"` (the common default) sends cookies only on same-origin requests.
- `credentials: "include"` allows attaching credentials per browser policy on cross-origin requests.
- `credentials: "omit"` uses no credentials.

`include` **does not force the browser past SameSite, Secure, third-party cookie restrictions, Partitioned cookies, or cookie-blocking policies**. CORS `Access-Control-Allow-Credentials: true` is likewise only one condition for the browser to let scripts read credentialed responses; it neither issues cookies nor logs users in.

### 5.2. `Access-Control-Allow-Origin: *` and credentials

For credentialed CORS responses, **never use `Access-Control-Allow-Origin: *`** to open all origins. Browsers reject this wildcard pattern with credentialed requests. In Spring Framework, `CorsConfiguration#setAllowCredentials(true)` forbids `allowedOrigins=["*"]` as a valid combination; `allowedOriginPatterns` exists when patterns are genuinely needed, yet overly broad patterns can expose private data to unintended domains.

Good design:

```java
config.setAllowedOrigins(
    List.of("https://app.example.test"));
config.setAllowCredentials(true);
```

Only controlled frontend origins receive credentialed CORS responses. Do not use `https://*.example.test` as a default allowlist if subdomains may be managed by third parties, host user-generated content, or be vulnerable to takeover.

### 5.3. Public responses can have a different policy

A CDN serving fonts or a public non-cookie/non-auth catalog can use:

```http
Access-Control-Allow-Origin: *
```

This is **not automatically suitable** for `/api/me`, `/admin`, `/csrf`, or personal resources. Separate CORS configs by endpoint/chain, avoiding a shared wildcard across all paths.

### 5.4. `Origin: null`, regex, and echoing Origin

Do not trust `Origin: null` simply because it is a concrete string; it can appear in sandboxed documents, local files, and opaque-origin contexts. Never write a filter like:

```java
// Anti-pattern: do not deploy in production.
response.setHeader(
    "Access-Control-Allow-Origin",
    request.getHeader("Origin"));
response.setHeader(
    "Access-Control-Allow-Credentials", "true");
```

This is a **dangerous illustrative Java snippet**, not a standalone config. It echoes every Origin with credential support, letting untrusted websites read private content. Replace it with exact allowlists, restricted methods/headers, and negative tests.

## 6. How does CSRF work?

### 6.1. Synchronizer token pattern

In session cookie-based apps, Spring Security normally generates an expected CSRF token and stores it in `HttpSession` via `HttpSessionCsrfTokenRepository`. The legitimate UI receives the token when rendering a form or calling a bootstrap endpoint and sends it back in a **hidden input** or **custom HTTP header**. The filter compares the request token against the expected token from the repository.

```html
<form action="/api/theme" method="post">
  <input type="hidden" name="theme" value="dark">
  <input type="hidden" name="_csrf"
         value="SERVER_RENDERED_TOKEN">
  <button type="submit">Save</button>
</form>
```

The placeholder value has no effect; Spring Security must issue a real per-session token. When the client sends the token, the server matches it:

```http
POST /api/theme HTTP/1.1
Cookie: JSESSIONID=<session-cookie>
Content-Type: application/x-www-form-urlencoded

theme=dark&_csrf=<valid-token-for-this-session>
```

If an attacker uses only an HTML form on an external origin, they normally cannot read the valid token from the UI or cross-origin responses due to Same-Origin Policy/CORS. A request carrying a cookie without the right token must be rejected.

### 6.2. Using a CSRF header for JavaScript

A trusted frontend can fetch the token from `GET /csrf` on the API in an allowed CORS environment and then send:

```http
POST /api/theme HTTP/1.1
Origin: https://app.example.test
Cookie: JSESSIONID=<session-cookie>
Content-Type: application/x-www-form-urlencoded
X-CSRF-TOKEN: <masked-token-from-csrf-endpoint>

theme=dark
```

With `HttpSessionCsrfTokenRepository` and the default handler, the common header name is `X-CSRF-TOKEN`. With `CookieCsrfTokenRepository`, the header is usually `X-XSRF-TOKEN`; when JavaScript reads the **raw token** from a cookie, Spring Security 6 has specific guidance regarding masked tokens/BREACH, so an appropriate SPA request handler must be used. Never let arbitrary browsers read another user's CSRF token via a CORS wildcard.

### 6.3. Token rotation at login/logout boundaries

Spring Security can clear CSRF tokens after authentication success/logout. A tab or SPA holding a stale token can receive 403 on the next unsafe request; the client must re-fetch the token in the current session. A 403 error does not necessarily mean CORS—inspect the actual request, session cookie, token, and authority.

### 6.4. CSRF applies to unsafe HTTP methods

Spring Security Servlet enables CSRF by default for `POST`, `PUT`, `PATCH`, and `DELETE` per the standard matcher. GET/HEAD/OPTIONS/TRACE are considered safe, yet **the backend must ensure GET performs no mutations**. The CSRF filter has no effect on requests exempted by configuration; verify the active filter chain and matchers.

### 6.5. A CSRF token is not an authentication token

A valid CSRF token does not say whether the user is Alice or Bob, nor does it grant arbitrary account access. Authentication/session identifies the subject; authorization checks roles/authorities/tenants/owners; CSRF solely stops one class of forged requests. All steps must work together rather than using one control to replace all three.

## 7. Selection rules: when do you need CORS, CSRF, or both?

| Architecture / scenario | CORS | CSRF | Why |
|---|---|---|---|
| Server-rendered form monolith, UI and backend same origin, session cookie | Usually **no** cross-origin config needed | **Needed** for unsafe methods | Browser auto-sends session cookie; UI is not cross-origin |
| SPA `app.example.test` calling cookie API `api.example.test` | **Needed** so JS can read responses | **Needed** for unsafe requests | Cross-origin + auto-sent credentials |
| SPA same origin as API, using session cookie | No extra CORS needed for same origin | **Needed** | Auto-sent cookies and unsafe forms/fetches |
| Cross-origin SPA using Bearer in JS `Authorization`, API uses no cookie auth | **Needed** if cross-origin browser | Traditional CSRF may **not be needed** for bearer-only endpoints | JS explicitly attaches Bearer header; evaluate XSS, storage, and refresh cookies |
| Machine-to-machine JSON bearer-only API | Not browser-related | Cookie-based CSRF typically not applicable | No browser Same-Origin Policy or auto cookies |
| Refresh/logout endpoint using HttpOnly cookie, even if access token is Bearer | Depends on frontend origin | **Needs evaluation/protection** | Refresh cookie is auto-sent by browser |
| Public font/asset API with no credentials | Can use wildcard CORS | No mutations | Public data, browser needs to read resources |
| Private admin session API, no cross-origin frontends allowed | Do not open cross-origin CORS | **Keep CSRF** | No JS cross-origin access, yet browser session exists |
| OAuth2/OIDC redirects/callbacks | CORS depends on protocol/flow; many redirects are not CORS fetches | Login CSRF, `state`/nonce, and standard callback validation | Do not treat allowOrigins as OAuth2 transaction binding |
| Server-to-server partner webhooks | No CORS needed | Cookie-based CSRF typically not applicable | Need webhook signatures, replay prevention, proper auth |

**Quickest decision guide:**

```text
Does the app have browser JS calling a different origin?
    |
    +-- No  → No CORS needed just for having an API.
    |
    +-- Yes → Configure CORS strictly for trusted origins/methods/headers.

Can the request modify state?
    |
    +-- No (safe GET) → No CSRF needed under default matcher,
    |                   yet still verify auth/permissions.
    |
    +-- Yes
          |
          +-- Does the browser auto-attach credentials? (session/refresh cookie,
          |   browser Basic auth, hybrid credentials)
          |       |
          |       +-- Yes → Enforce CSRF token or equivalent
          |       |         threat-modeled defense.
          |       |
          |       +-- No → Evaluate CSRF by architecture
          |                  and protect Bearer/XSS/replay/authorization.
          |
          +-- With or without CORS, never skip permission checks.
```

In practice, Origin/Sec-Fetch-Site checks, SameSite cookies, and custom headers can serve as defense-in-depth. However, **never quietly drop synchronizer tokens** in a cookie-auth browser app just because CORS is configured.

## 8. Runnable Spring Boot 3.x / Spring Security 6 / Java 17+ sample

We build a Servlet API with:
- Trusted frontend: `https://app.example.test`.
- Hypothetical API at `https://api.example.test` (code runs locally on port 8080; test Origin headers simulate the deployed environment).
- Only the trusted frontend may call `/api/**` and `/csrf` cross-origin.
- Cookie-based form login (demo in-memory user).
- `GET /csrf` for the frontend to fetch the session's CSRF token.
- `GET /api/theme` requires login and modifies no state.
- `POST /api/theme` requires **both login and a CSRF token**, even though CORS already allows the origin.
- Rejects unknown origins in preflight and actual CORS requests.

### 8.1. Gradle dependencies

Create a Spring Initializr project, Spring Boot 3.x, Java 17+, with Spring Web and Spring Security. In `build.gradle`, Boot plugins, repositories, and toolchain are already present:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is a **dependencies block**, not a full Gradle build file. Use Boot-managed BOM/versions; do not mix incompatible standalone Security versions.

### 8.2. Complete application

Place at `src/main/java/example/corscsrf/CorsCsrfDemoApplication.java`:

```java
package example.corscsrf;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@SpringBootApplication
public class CorsCsrfDemoApplication {

    static final String FRONTEND = "https://app.example.test";

    public static void main(String[] args) {
        SpringApplication.run(CorsCsrfDemoApplication.class, args);
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of(FRONTEND));
        cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(List.of(
            "Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        source.registerCorsConfiguration("/csrf", cors);
        return source;
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/csrf").permitAll()
                .requestMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/theme")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/theme")
                    .authenticated()
                .anyRequest().denyAll())
            .formLogin(form -> form.permitAll())
            .build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}demo123")
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }
}

@RestController
class DemoController {
    private final Map<String, String> themes =
        new ConcurrentHashMap<>();

    @GetMapping("/public/ping")
    String ping() {
        return "ok";
    }

    @GetMapping("/csrf")
    ResponseEntity<Map<String, String>> csrf(CsrfToken token) {
        // Body may only be read from the trusted origin.
        // Cache-Control helps prevent accidental caching of tokens by shared caches.
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "headerName", token.getHeaderName(),
                "parameterName", token.getParameterName(),
                "token", token.getToken()));
    }

    @GetMapping("/api/theme")
    Map<String, String> read(Authentication auth) {
        return Map.of(
            "user", auth.getName(),
            "theme", themes.getOrDefault(auth.getName(), "unset"));
    }

    @PostMapping("/api/theme")
    Map<String, String> update(
            @RequestParam String theme, Authentication auth) {
        if (!"dark".equals(theme) && !"light".equals(theme)) {
            throw new org.springframework.web.server.ResponseStatusException(
                org.springframework.http.HttpStatus.BAD_REQUEST,
                "Unsupported theme");
        }
        themes.put(auth.getName(), theme);
        return Map.of("user", auth.getName(), "theme", theme);
    }
}
```

**Important components:**

1. `UrlBasedCorsConfigurationSource` is the CORS config source integrated with Spring Security via `http.cors(...)`. Use an exact origin allowlist; never reflect the `Origin` received from the browser.
2. `setAllowCredentials(true)` is dedicated to the trusted frontend, combined with `setAllowedOrigins(List.of(FRONTEND))`; never add `"*"`.
3. `allowedMethods`/`allowedHeaders` permit only actual requirements; do not open all methods/headers just to silence preflight errors.
4. CORS applies only to `/api/**` and `/csrf`; do not expose cross-origin data across all controllers. `/csrf` is allowlisted solely because the trusted frontend needs to obtain the token.
5. `http.cors(Customizer.withDefaults())` integrates CORS early enough that OPTIONS preflight is not blocked as an anonymous request.
6. `http.csrf(Customizer.withDefaults())` preserves CSRF protection for POSTs in browser/session flows. Spring Security typically uses `HttpSessionCsrfTokenRepository` on Servlet.
7. `GET /csrf` returns the request CSRF token per Spring Security 6's handler; the rendered token may be masked. The frontend must send the exact received value via the header named by `headerName`, within the same session.
8. `/api/theme` GET and POST require authenticated users; a valid CSRF token **does not** replace login. If the user is not logged in, responses typically redirect to login via the form-login entry point.
9. `{noop}` is for local demos only and **does not hash passwords**; production requires a password encoder, TLS, identity provider, session hardening, and business permission policies.
10. `ConcurrentHashMap` is an in-memory demo only, not multi-instance/multi-tenant persistence.

**Security warning:** Although the config lets the cross-origin frontend read `/csrf`, that frontend must be trusted on par with being authorized to use the session. If the frontend suffers XSS or origin takeover, token readability becomes a risk; CSRF does not protect when an attacker executes scripts on a trusted origin. Never expose `/csrf` to every Origin or through a public CDN.

### 8.3. Cross-origin frontend flow with session cookies

JavaScript running at `https://app.example.test`, calling API at `https://api.example.test`:

```javascript
const api = "https://api.example.test";

async function changeTheme(theme) {
  // Login/session cookie must exist per product flow.
  // Obtain CSRF token via a CORS credentialed request.
  const boot = await fetch(api + "/csrf", {
    credentials: "include",
    cache: "no-store"
  });
  if (!boot.ok) {
    throw new Error("Cannot load CSRF token");
  }
  const csrf = await boot.json();

  const result = await fetch(api + "/api/theme", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      [csrf.headerName]: csrf.token
    },
    body: new URLSearchParams({ theme })
  });
  if (!result.ok) {
    throw new Error("POST rejected");
  }
  return result.json();
}
```

**Both mechanisms work together:**

- CORS permits browser JavaScript at origin `app.example.test` to read the token and responses from origin `api.example.test`.
- CSRF verifies that the POST request carries the token matching the session.
- Authentication/authorization determines which user can update the theme.
- `credentials: "include"` does not override cookie restrictions; SameSite/Secure/Domain/Path, login flows, and third-party cookie restrictions must be verified in real deployments.

In a local demo, the script above will not run verbatim unless you deploy the API at `https://api.example.test` with TLS and matching cookies. To test CORS mechanics locally, the integration tests below send hypothetical `Origin` headers and verify HTTP headers. Do not assume MockMvc tests simulate full browser cookie policies.

## 9. Integration tests: verifying CORS and CSRF **independently**

Place at `src/test/java/example/corscsrf/CorsCsrfDemoApplicationTest.java`:

```java
package example.corscsrf;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class CorsCsrfDemoApplicationTest {

    static final String TRUSTED =
        CorsCsrfDemoApplication.FRONTEND;
    static final String UNTRUSTED =
        "https://evil.example.net";

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;

    @Test
    void preflightWorksBeforeAuthentication() throws Exception {
        // No session or user attached: OPTIONS preflight
        // is still handled by CORS.
        mvc.perform(options("/api/theme")
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, TRUSTED))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"));
    }

    @Test
    void untrustedPreflightIsRejected() throws Exception {
        mvc.perform(options("/api/theme")
                .header(HttpHeaders.ORIGIN, UNTRUSTED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type,x-csrf-token"))
            .andExpect(status().isForbidden());
    }

    @Test
    void allowedOriginDoesNotSkipAuthentication() throws Exception {
        mvc.perform(get("/api/theme")
                .header(HttpHeaders.ORIGIN, TRUSTED))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void allowedOriginDoesNotSkipCsrf() throws Exception {
        mvc.perform(post("/api/theme")
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .with(user("alice"))
                .param("theme", "dark"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfHeaderAllowsAuthenticatedPost()
            throws Exception {
        mvc.perform(post("/api/theme")
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .with(user("alice"))
                .with(csrf().asHeader())
                .param("theme", "dark"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, TRUSTED))
            .andExpect(jsonPath("$.theme").value("dark"));
    }

    @Test
    void validCsrfDoesNotOverrideCors() throws Exception {
        mvc.perform(post("/api/theme")
                .header(HttpHeaders.ORIGIN, UNTRUSTED)
                .with(user("alice"))
                .with(csrf().asHeader())
                .param("theme", "dark"))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidCsrfIsRejectedEvenFromTrustedOrigin()
            throws Exception {
        mvc.perform(post("/api/theme")
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .with(user("alice"))
                .with(csrf().useInvalidToken())
                .param("theme", "dark"))
            .andExpect(status().isForbidden());
    }

    @Test
    void csrfEndpointTokenWorksWithSameSession()
            throws Exception {
        MvcResult bootstrap = mvc.perform(get("/csrf")
                .header(HttpHeaders.ORIGIN, TRUSTED))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, TRUSTED))
            .andReturn();

        JsonNode tokenJson = mapper.readTree(
            bootstrap.getResponse().getContentAsString());
        String name = tokenJson.path("headerName").asText();
        String value = tokenJson.path("token").asText();
        assertThat(value).isNotBlank();

        MockHttpSession session = (MockHttpSession)
            bootstrap.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(post("/api/theme")
                .session(session)
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .header(name, value)
                .with(user("alice"))
                .param("theme", "light"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.theme").value("light"));
    }

    @Test
    void readOnlyGetNeedsNoCsrf() throws Exception {
        mvc.perform(get("/api/theme")
                .header(HttpHeaders.ORIGIN, TRUSTED)
                .with(user("alice")))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, TRUSTED));
    }
}
```

Run tests with Gradle Wrapper:

```bash
./gradlew test
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
```

**Interpreting the test matrix:**

| Case | Expected status | Proves |
|---|---:|---|
| Trusted origin preflight, not logged in | 200 | CORS handles OPTIONS before authentication |
| Untrusted origin preflight | 403 | CORS denies origin |
| Trusted origin GET yet anonymous | Login redirect (3xx) | CORS grants no identity |
| Trusted origin + authenticated POST missing CSRF | 403 | CORS does not replace CSRF |
| Trusted origin + authenticated POST valid CSRF | 200 | Both CORS and CSRF satisfied |
| Untrusted origin + valid CSRF POST | 403 | CSRF does not unlock CORS |
| Trusted origin + invalid CSRF | 403 | Server verifies token |
| `GET /csrf` then POST in same session | 200 | Real token from endpoint works |
| Trusted origin + authenticated GET | 200 | Safe GET needs no CSRF |

`with(user("alice"))` mocks an authenticated principal in tests, keeping authentication constant while testing CORS/CSRF. It does not prove browser login works, session persistence/cookie settings are right, or CORS behaves properly through a real proxy. `csrf().asHeader()` also creates a CSRF token in tests; `csrfEndpointTokenWorksWithSameSession` adds retrieving the token from the endpoint and sending it with the same `MockHttpSession`. End-to-end browser tests are needed when a product implements cross-origin cookie authentication.

### 9.1. Valuable negative tests to add

Also verify:
- `Origin: null` or origin from a sandboxed iframe: reject if not on the allowlist.
- Preflight requesting `DELETE` when the allowlist only allows GET/POST: reject.
- Preflight requesting a disallowed custom header: reject.
- Authenticated POST with a token from another session: reject.
- Token cleared after login/logout then POST: accept only the new token.
- Multiple filter chains with different CORS configs: right chain and exact Origin.
- Bearer JWT request missing scope even if CORS/CSRF pass: 403 at authorization.
- Real browser with `credentials: include` where cookies are blocked by SameSite/third-party policies: login/session failure independent of CORS.
- Compromised trusted origin: treat as supply-chain/XSS risk; never trust an Origin header as proof of user intent.

## 10. When does CORS preflight fail?

Some symptoms:

| Symptom in browser | High likelihood | How to check |
|---|---|---|
| “No Access-Control-Allow-Origin header” | Server did not enable CORS for endpoint/origin, or error response lacks headers | Inspect preflight/actual responses and filter chain |
| Preflight returns 401/login redirect | CORS not processed before authentication | Integrate `http.cors` and proper `CorsConfigurationSource` |
| Preflight returns 403 | Origin, method, or header disallowed; server security filter rejected | Check Access-Control-Request-Method/Headers, status |
| ACAO is `*` while fetch uses credentials | Browser rejects wildcard credentialed CORS | Use specific trusted origin + proper ACAC |
| Network shows 200 yet script reports CORS | Browser blocked reading due to invalid CORS headers | Cross-check Origin, ACAO, ACAC, redirects, and browser console |
| SameSite cookie not sent | Cookie/site policy, not merely missing ACAO | Inspect Cookie and Set-Cookie, Secure, Domain, SameSite |
| Only POST reports CORS, GET works | POST has JSON/custom header → preflight, or POST returns 403 CSRF | Separate OPTIONS vs actual, check CSRF |
| One route works, another fails | Different CORS mappings/chains | Check `/api/**`, `/csrf`, and proxy paths |
| Requests through proxy fail, localhost passes | Proxy strips Origin/headers or trusted forwards misconfigured | Compare requests at edge and backend |

**Do not fix this by adding `@CrossOrigin(origins="*")` to every controller or calling `cors.disable()`.** Identify where preflight is blocked, which origin policy is granted, and which methods/headers the client genuinely needs.

## 11. When does a CSRF failure look like CORS?

A cross-origin request that passed preflight yet gets a 403 on the actual POST can cause the browser to display a CORS message if the error response lacks sufficient ACAO headers. The true cause may be **a missing/invalid CSRF token or expired authentication**.

Debug in order:

1. Did the browser send an OPTIONS preflight? What status and CORS headers did OPTIONS return?
2. Did the browser send the actual POST? If not, it is usually CORS/preflight.
3. If the POST was sent, do server logs show `MissingCsrfTokenException` or `InvalidCsrfTokenException`? Log the error type, never raw tokens.
4. Did JS send `X-CSRF-TOKEN`/`X-XSRF-TOKEN` matching the active repository?
5. Was the token obtained in **the same session/cookie** and after the most recent login/logout?
6. Is a mismatch caused by deferred CSRF tokens, XOR masking, or cookie raw tokens?
7. Did the browser send the session cookie? Check `credentials`, SameSite, Secure, and third-party restrictions.
8. Are filter chains mixed where one has `csrf.disable()` and another enables CSRF?
9. Is 403 caused by CSRF or by `hasAuthority`/ownership? Test independently with valid CSRF.
10. Is an HTTP endpoint mutating on GET, or is a client sending JSON POST while the server enforces a different Content-Type/redirect?
11. Is the edge/proxy stripping Origin, preflight headers, cookies, or the CSRF header?
12. Does the backend emit CORS headers consistently on error responses inside the filter flow?

A good test technique is **keeping the same user and Origin while changing only the CSRF token**, and then **keeping the same user and token while changing only the Origin**. Those two cases prove the system enforces both policies.

## 12. Cookies, SameSite, XSS, and defense-in-depth

### 12.1. SameSite is defense-in-depth

`SameSite=Lax` or `Strict` can limit cookie sending on cross-site requests, mitigating many CSRF vectors. However:
- Do not use SameSite as the sole reason to omit CSRF checks when products must protect unsafe requests.
- Same-site yet cross-origin requests (subdomains) can still send cookies per policy.
- A trusted site with partner-controlled subdomains requires risk review.
- If a cross-site frontend needs cookies, `SameSite=None; Secure` may be necessary, raising security and browser-compatibility requirements.
- CORS does not govern SameSite; browsers evaluate both independently.

### 12.2. XSS can bypass CSRF tokens

If an attacker runs JavaScript within a trusted origin via XSS or a compromised dependency, the script can read tokens from the DOM or call `/csrf` if that origin is allowed. Hence CSRF tokens do not replace **output encoding, CSP, dependency scanning, Content Security Policy, HttpOnly cookies**, and authorization.

### 12.3. CSRF token exposure is a trust decision

A cross-origin frontend allowed by CORS to read `/csrf` is nearly granted the ability to perform requests with that token whenever the browser also sends session cookies. Allow only origins you administer and secure commensurately. Never cache CSRF token responses on a public CDN or print raw tokens in logs.

### 12.4. Custom headers and CORS preflight

A JS-added `X-CSRF-TOKEN` header can cause requests to require preflight. That adds friction against untrusted sites, yet **CSRF protection is not merely “having preflight”**: the server must validate the token and session state. If CORS accidentally lets an attacker origin read tokens or accepts credentials broadly, preflight will not stop an attacker at an allowed origin.

## 13. Multiple security chains and WebFlux

### 13.1. Servlet with multiple `SecurityFilterChain` beans

An application might have:
- A form-login web chain at `/web/**`, using cookies/sessions and CSRF.
- A bearer-only API chain at `/api/**`, stateless and configured with CORS for a trusted SPA.
- A fallback chain denying remaining routes.

When using multiple chains, inspect `securityMatcher`/`@Order` to know which chain handles which requests. `anyRequest().denyAll()` inside one chain applies only to requests matched by that chain; CORS configs and CSRF matchers must also be defined for the right chain.

Specifically, a preflight `OPTIONS /api/orders` must match the right chain and be processed by CORS before auth; do not declare matchers for GET/POST only and inadvertently let OPTIONS fall out of the security chain or get blocked before CORS.

If there are multiple `CorsConfigurationSource` beans, Spring Security does not necessarily know which source to select; you can pass a specific source via `http.cors(cors -> cors.configurationSource(source))` for each chain. Avoid creating redundant CorsFilters or duplicating CORS across proxies, servlet filters, and MVC annotations without knowing which rule wins.

### 13.2. WebFlux uses different APIs

Spring WebFlux uses `ServerHttpSecurity`, `SecurityWebFilterChain`, and typically integrates `CorsWebFilter`/reactive CORS configuration rather than copying Servlet `HttpSecurity`, `HttpSession`, `CorsFilter`, or `CsrfFilter`. Reactive CSRF uses `ServerCsrfTokenRepository` and matching reactive components.

**Yet the architectural decisions do not change:** cross-origin browser JS needs a CORS policy; browser auto-sent cookies on mutations need CSRF protection per threat model; neither replaces authentication/authorization. With WebFlux, test using WebTestClient and browser E2E on the right stack, never mixing Servlet code into a reactive service.

### 13.3. Reverse proxies and gateways

If TLS terminates at a gateway or the external URL differs from Spring Boot's context path, check:
- Trusted proxies handle `Host` and `X-Forwarded-*` properly; never trust spoofed headers from the Internet.
- Whether the gateway strips/adds `Origin`, `Access-Control-Request-*`, or `Access-Control-Allow-*`.
- Whether multiple layers emit ACAO, causing duplicate headers or conflicts.
- Login redirects target the exact HTTPS API domain without losing cookies.
- The CORS allowlist uses the **browser-visible origin**, not internal hostnames between services.
- CORS on `/csrf` suffices for the trusted frontend to fetch tokens without letting attacker origins read them.
- 401/403 error responses pass through CORS integration consistently so the browser can distinguish errors.

## 14. Anti-patterns and fixes

| Anti-pattern | Consequence | Replacement |
|---|---|---|
| Enabling CORS then calling `csrf.disable()` on a session-cookie app | Opens CSRF when browsers auto-send cookies | Keep CSRF tokens on unsafe requests |
| “CORS blocked it, so POST definitely never happened” | Safelisted requests can already be sent | Do not rely on unreadable responses; guard mutations |
| `Access-Control-Allow-Origin: *` + credentials | Browser rejects; or invalid server config | Exact trusted origins + ACAC only when needed |
| Reflecting `Origin` into ACAO | Lets untrusted frontends read private responses | Fixed origin allowlist |
| `@CrossOrigin("*")` on all endpoints | Widens data-reading surface | Narrow mappings per API use case |
| Allowing all headers/methods just to clear preflight errors | Grants far more capability than needed | List actual methods/headers |
| Setting `withHttpOnlyFalse()` on session cookies | Increases risk of JS reading credentials | If needed, only make CSRF cookie readable |
| Using SameSite as a complete token replacement | Misses flows and policies | Combine defense-in-depth with CSRF |
| Passing CSRF token in URL query | Leaks via history/logs | Header or hidden form field |
| Checking only `hasRole` while skipping tenant/owner | IDOR/BOLA | Service/data-layer authorization |
| Turning every POST into GET to avoid 403 | Mutations easily triggered | Use unsafe HTTP methods + CSRF |
| Treating JSON parse failure as a CORS error | May be 401/403/HTML login redirect | Check network method/status/content-type |
| Disabling CORS in Security to “turn off browser protection” | Cross-origin browser calls break; does not bypass SOP | Configure CORS properly |
| Using CSRF tokens to authenticate bearer-only APIs | Wrong token role | Authenticate with Bearer, authorize by permissions |
| Copying WebFlux code into Servlet | Wrong class/filter semantics | Use the right web stack |
| Testing only 200 happy paths | Misses overly open Origin/token handling | Negative tests for both |
| Exposing CSRF response to all origins | Breaks trust boundary | Only approved frontends, no-store |
| Skipping tests of browser credential flags | MockMvc passes, production browser fails | E2E with HTTPS/cookies/proxy |

## 15. Review and testing checklist

### CORS

- [ ] Identify actual **origins** of frontend and API (scheme, hostname, port).
- [ ] Verify genuine cross-origin need; same-origin apps do not need extra CORS opened.
- [ ] `allowedOrigins` is a specific list; never reflect untrusted `Origin` values.
- [ ] `allowCredentials=true` only when cookies/credentials from a trusted frontend are required.
- [ ] Methods/headers/path mappings are restricted; do not open all endpoints.
- [ ] OPTIONS preflight needs no login cookies and runs before authorization.
- [ ] Permitted responses include ACAO with exact origin and ACAC when credentialed.
- [ ] Untrusted origins/`Origin: null`/disallowed methods/headers are rejected.
- [ ] CORS headers on error responses are verified; gateway/proxy introduces no conflicts.
- [ ] Browser `credentials`, SameSite/Secure/Domain/Path policies have been tested for real.

### CSRF

- [ ] Are credentials auto-sent by the browser on unsafe requests?
- [ ] Form POSTs have hidden `_csrf` from the server matching the current session.
- [ ] Fetch/AJAX includes `X-CSRF-TOKEN` or `X-XSRF-TOKEN` per repository/handler.
- [ ] `CsrfFilter` stays enabled for cookie-auth chains; do not disable just to silence errors.
- [ ] Tokens are re-fetched after login/logout when the framework clears old tokens.
- [ ] Cookie-based SPAs distinguish raw tokens from XOR-masked tokens per Spring Security version.
- [ ] `GET /csrf` is exposed only to same-origin/trusted origins and never shared-cached.
- [ ] Authenticated user POSTs with missing/invalid tokens are blocked before mutation.
- [ ] Cross-session tokens and session timeouts are tested.
- [ ] GET/HEAD have no side effects; state-changing methods follow proper semantics.
- [ ] Authentication and authorization (role/owner/tenant/ACL) remain enforced.

### Integrated QA

- [ ] Negative tests isolate CORS deny, CSRF deny, and authorization deny by holding other factors constant.
- [ ] Test preflight without cookies and actual requests with cookies when browser permits.
- [ ] When encountering 403, identify which filter/handler emitted it; never look solely at status.
- [ ] Run browser E2E tests behind reverse proxy and HTTPS with the real frontend.
- [ ] Never log session IDs, CSRF tokens, authorization headers, or private response bodies.
- [ ] Review differences among OAuth2 login, bearer access tokens, refresh cookies, and stateless APIs.
- [ ] Revisit CORS/CSRF when upgrading Spring Security versions or changing frontend domains.

## 16. Reasoning exercises

**Question 1.** A React SPA running at `https://app.example.test` calls an API at `https://api.example.test` using session cookies. What is needed?

**Answer:** A CORS allowlist for the frontend origin so JS can read responses, and CSRF tokens on unsafe methods because the browser auto-sends cookies. Afterwards, authentication and per-resource permissions must still be checked.

**Question 2.** A cross-site POST cannot read the response due to CORS; does that mean the backend definitely did not modify data?

**Answer:** No. Safelisted requests can be sent first, with the browser only blocking the script from reading the response. A server-side CORS filter may reject Origin, yet it cannot be treated as a universal guarantee replacing CSRF across all environments.

**Question 3.** An OPTIONS preflight to a private API lacks `JSESSIONID`. Should it get 401 for not being logged in?

**Answer:** No; if Origin/method/headers are valid, CORS must process preflight without login cookies. The subsequent actual POST then goes through authentication/authorization/CSRF.

**Question 4.** Can `Access-Control-Allow-Origin: *` and `Access-Control-Allow-Credentials: true` be used for a cookie API?

**Answer:** Not a valid credentialed CORS configuration for browsers; choose specific trusted origins, ACAC when needed, and proper cookie policies.

**Question 5.** Does a valid CSRF token allow user Alice to edit Bob's order?

**Answer:** No. CSRF proves a request was not forged under the system's pattern; it does not decide business permissions. Owner/tenant/ACL checks must happen in the service/repository.

**Question 6.** A machine-to-machine API uses only Bearer tokens in the Authorization header, with no browser. Must CORS be enabled?

**Answer:** No. CORS is a browser mechanism. The API still needs HTTPS, signature/issuer/audience/scope validation, rate limits, and authorization.

**Question 7.** Frontend `app.example.test` is on the CORS allowlist, yet POST still returns 403. What could be wrong?

**Answer:** Possible missing CSRF token, session cookie not sent, stale token after login, missing role/permission, or disallowed CORS method/header. Inspect OPTIONS then actual POST, safe server logs, and use negative tests to isolate the cause.

**Question 8.** Is using CORS enough to restrict who can call an API using curl?

**Answer:** No. Non-browser HTTP clients can send requests without being governed by browser Same-Origin Policy. Authentication, authorization, validation, and appropriate server-side security controls are required.

## 17. Official documentation

- [Spring Security 6.5 — CORS (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html): CORS preflight before authentication, `UrlBasedCorsConfigurationSource`, multiple chains.
- [Spring Security 6.5 — CSRF (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): CSRF request filters, `CsrfTokenRepository`, tokens for forms/JS, BREACH, and SPAs.
- [Spring Framework — Spring MVC CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): `CorsConfiguration`, `allowedOrigins`, `allowCredentials`, preflight/actual requests.
- [Spring Security — MockMvc CSRF Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html): `csrf()`, `csrf().asHeader()`, invalid-token tests.
- [Spring Security — WebFlux CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): CORS in the reactive stack and `CorsWebFilter`.
- [Spring Security — WebFlux CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): reactive CSRF repository and filter equivalents.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF threat model, synchronizer tokens, SameSite, and defense-in-depth.
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): browser requests, preflight, safelisted requests, and CORS response headers.

**Conclusion:** Do not choose CORS *or* CSRF as mutually exclusive options. If **JavaScript accesses a cross-origin API**, configure exact CORS for trusted frontends. If **the browser auto-sends cookies/credentials to state-changing endpoints**, enforce CSRF protection matching the flow. For applications that are both cross-origin and session-based, **both are required**, while still maintaining authentication, authorization, and data security.
