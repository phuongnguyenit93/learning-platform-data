# CORS does not replace identity verification or CSRF protection

## 1. Objectives: distinguishing three different protection layers

In a Spring Boot application, developers frequently encounter all three questions:

1. **Which origins are allowed to let JavaScript in the browser read responses from my server?** This is the **Cross-Origin Resource Sharing (CORS)** problem.
2. **Who is sending this request, and have they logged in or proven identity?** This is Spring Security's **authentication** problem.
3. **Was a request using an active login session genuinely initiated by the user, or did another website trick the browser into sending it?** This is the **Cross-Site Request Forgery (CSRF)** problem.

A very common wrong answer is: "I configured CORS only for the frontend domain, so the API is safe and no longer needs Spring Security login or CSRF." **False.** CORS does not verify passwords, access tokens, sessions, user roles, or CSRF tokens. CORS is primarily a browser-enforced policy deciding **whether JavaScript from another origin can read the response**, and for preflighted requests whether the browser will dispatch the main request. The server must still authenticate, authorize, and protect state-changing actions itself.

After this lesson, you will be able to:

- Distinguish *same-origin* vs *same-site*, a CORS *preflight* vs actual request, authentication vs authorization, and CORS vs CSRF.
- Interpret three flows: **origin allowed but not logged in**; **active session but missing CSRF token**; **both valid session and valid CSRF token**.
- Configure Spring Security Servlet with `http.cors(...)`, `CorsConfigurationSource`, `authorizeHttpRequests(...)`, and `csrf(...)` without letting the three layers substitute for one another.
- Use `CsrfToken` via a `/csrf` endpoint and understand why tokens need refreshing after login/logout.
- Test scenarios with MockMvc: preflight, origin allowlist, unauthenticated access, POST missing CSRF, POST with CSRF.
- Spot dangerous configurations such as wildcard origin + credentials, blindly reflecting every `Origin`, disabling CSRF just to avoid 403, or returning 200 merely because preflight passed.
- Choose appropriately for **cookie-based browser apps** vs **non-cookie bearer-token APIs**.

This lesson covers Spring Security **Servlet/Spring MVC**. For WebFlux, the corresponding types and chain are `SecurityWebFilterChain`, `CorsWebFilter`, and reactive CSRF; you cannot copy Servlet config verbatim into WebFlux.

## 2. Comparison table: CORS, authentication, authorization, CSRF

| Mechanism | Core question | Data/components | What it cannot do |
| --- | --- | --- | --- |
| **CORS** | Can browser script at origin A access responses from origin B? | `Origin`, `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Credentials`, `CorsFilter` | Does not prove who calls the API; does not grant roles; does not replace CSRF |
| **Authentication** | Who is calling? Are credentials valid? | `JSESSIONID`/`SecurityContext`, password, bearer token, mTLS, API key… | Does not by itself decide whether the user may edit every object |
| **Authorization** | Does this principal have permission for the action/object? | `Authentication`, authorities, policies, `AuthorizationFilter` | Does not check which website originated the request or user intent |
| **CSRF protection** | Does a state-changing request using ambient credentials carry valid anti-forgery proof? | CSRF token, Origin/Referer/Fetch Metadata policy, SameSite, and server-side checks | Does not verify identity instead of sessions/login; does not let JS read cross-origin responses |

For example, a single request can be:

- **CORS accepted but unauthenticated:** trusted frontend script is permitted by the browser to receive the response, yet the server still returns a login redirect or 401 due to no session.
- **Authenticated but blocked by CSRF:** browser sends a valid session cookie and the user has permission, yet `POST` lacks a token so the server returns 403.
- **Valid authentication and CSRF, but CORS disallows the current origin:** the backend may execute auth/CSRF checks and produce a response, yet JavaScript at a disallowed origin will be barred by the browser from reading it; if preflight is rejected, the browser will not even send the main request.
- **CORS allowed and authentication succeeded, but authorization failed:** user is logged in and request is valid, yet lacks `ROLE_ADMIN` → 403 per policy.

**CORS success does not mean "logged in". `Origin` is not a credential. Nor does a CSRF token turn an anonymous user into an authenticated principal.**

## 3. How do origin and site differ?

In Web security, an **origin** is defined by **scheme + hostname + port**. Same-site (as browsers define *schemeful site*) typically relies on scheme and registrable domain, not meaning same-origin.

Suppose:

```text
Frontend: https://app.example.com
Backend:  https://api.example.com
Attacker: https://evil.example.net
```

- Frontend and backend have **different origins** because their hostnames differ. `fetch("https://api.example.com/...")` from the frontend may require CORS.
- Frontend and backend are typically considered **same-site** (HTTPS and same registrable domain `example.com`), despite differing origins. This is crucial when analyzing `SameSite` cookies.
- The attacker on `evil.example.net` differs in both origin and site. If the browser holds a session cookie permitted by policy, some request types can be triggered from that site even though attacker script cannot read the response.
- `https://app.example.com` and `http://app.example.com` differ in origin due to scheme; under schemeful site, they are also cross-site.
- `https://app.example.com:443` and `https://app.example.com:8443` differ in origin due to port.

An origin **excludes** path, query, and fragment. Therefore:

```text
https://app.example.com/dashboard
https://app.example.com/settings
```

share the exact same origin.

**Do not use naive regexes like `endsWith("example.com")` to validate origins**, because spoofed hostnames or unexpected ports/schemes can slip past. If the app consumes proxy info, trust forwarded headers only from managed reverse proxies; never treat client-supplied `Origin` or `Host` as trusted identity.

## 4. Why is CORS not authentication?

A browser API request may carry:

```http
GET /api/me HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
```

If the backend allows that origin, the response can include:

```http
HTTP/1.1 302 Found
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Location: /login
```

Valid CORS headers **do not turn the HTTP status into 200**. In a Spring `formLogin` example using session cookies, an unauthenticated request still redirects to the login page.

Specifically, `Origin: https://app.example.com` only indicates the origin **declared by the browser** when creating the request. Outside browsers, `curl`, Postman, and custom clients can set any `Origin` header freely. So never write:

```java
// WRONG - counter-example snippet, do not use:
if ("https://app.example.com".equals(
        request.getHeader("Origin"))) {
    // Treat as logged-in user and allow operation
}
```

Authentication must verify credentials from a trusted system—such as a session established after password/OIDC login, a validly signed JWT matching issuer/audience, a verified API key, an mTLS client certificate, or similar mechanisms.

**Authorization also differs from authentication.** A logged-in user may lack permission to modify another tenant's record. Enforce `hasRole(...)`, `hasAuthority(...)`, and object ownership checks at the service layer. Having the frontend in the allowlist does not remove these checks.

## 5. Why is CORS not CSRF protection?

CSRF targets **actions executed under a user's authority without the user intentionally requesting them**. In session-cookie web apps, browsers can auto-attach session cookies to a request when cookie/SameSite conditions permit.

Scenario:

1. User logs into `https://bank.example.com` and holds a session cookie.
2. User opens the attacker's site `https://evil.example.net`.
3. The attacker's page induces the browser to submit a POST to an endpoint that changes info/performs a transaction.
4. If the backend only checks the session and lacks intent verification via CSRF protection, the action may run under the user's identity.
5. Even though CORS bars attacker script from **reading** the response, simple requests like an HTML form POST may already have been sent and processed. Blocking response reading **does not undo changes** already committed.

Diagram:

```text
Attacker site                     Browser with existing session
      |                                      |
      | -- induces browser to send form POST --> |
                                             |
                                             | POST /settings/update
                                             | Cookie: JSESSIONID=...
                                             v
                                       Spring backend
                                             |
                                      Authentication
                                             |
                                      Logged in? Yes.
                                             |
                                      CSRF validation
                                      /      \
                            Valid token?     Missing/invalid token
                               |                 |
                        request proceeds     403 Forbidden
                               |
                         Authorization
                               |
                        can execute action

CORS: browser may block attacker from reading response.
CSRF: server must block forged action.
```

**Be careful with SameSite cookies:** `SameSite=Lax/Strict` can prevent cookies in certain cross-site contexts and is a useful risk-reduction layer. Yet *same-site is not same-origin*: if a same-site subdomain is compromised or an endpoint has side effects on GET, relying solely on SameSite may fall short. For session-cookie apps, keep CSRF protection aligned with your threat model and OWASP/Spring Security guidance.

**CORS preflight is not a CSRF token.** A request with a custom header typically triggers preflight; that helps when CORS policy is strict and the server rejects simple content types. However, the token verified by Spring Security remains a separate defense. Never drop `CsrfFilter` merely because preflight tests pass.

## 6. Simple requests and preflights: two different flows

### 6.1. Requests without preflight

Certain cross-origin requests meeting CORS *safelisted* criteria can be dispatched **directly** by the browser without calling OPTIONS first. For example, an HTML form using `POST` with `application/x-www-form-urlencoded` (subject to relevant HTTP/browser rules).

```http
POST /api/settings HTTP/1.1
Host: api.example.com
Origin: https://evil.example.net
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=...
 
displayName=attacker-choice
```

The cookie is attached only if the browser's credential/cookie policy permits; the example above illustrates a context with matching ambient credentials. **CORS can stop JS from reading responses, yet does not guarantee the request never reached the server.** If the endpoint mutates state without verifying CSRF/Origin, that is a vulnerability.

### 6.2. Preflighted requests

Browsers typically preflight when requests use non-safelisted methods, custom headers, or non-safelisted content types—such as a JSON POST with `X-CSRF-TOKEN`.

```http
OPTIONS /api/settings HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

Response when origin, method, and headers are allowed:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: content-type,x-csrf-token
Access-Control-Allow-Credentials: true
Vary: Origin
```

Header combinations/order/casing may vary across frameworks and browsers; this is a **structural example**, not a byte-for-byte guarantee. Preflight **does not send session cookies**, and 200 here only confirms the *cross-origin policy* for the upcoming request—**it does not prove the user is logged in**.

Only afterward does the browser send the main request:

```http
POST /api/settings HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Cookie: JSESSIONID=...
Content-Type: application/json
X-CSRF-TOKEN: <token-issued-for-session>

{"displayName":"Lan"}
```

At this point the backend must still verify:

- Is the session cookie/auth token valid?
- Does the user have permission to edit that account's settings?
- Does `X-CSRF-TOKEN` match the token bound to the server's session/CSRF strategy?
- Is the JSON valid and does the action comply with business policies?

**Remember:** browsers can cache preflight results via `Access-Control-Max-Age`, yet every actual request still needs proper authentication, authorization, and CSRF. A preflight success is not an access token.

### 6.3. Why must CORS run before Spring Security?

Official Spring Security documentation explains that preflights do not carry `JSESSIONID`. If authentication/authorization handles preflight like a normal protected request before CORS, it can mistakenly return 401/302/403, causing browsers to report CORS errors.

Configuring `http.cors(Customizer.withDefaults())` with a `UrlBasedCorsConfigurationSource` integrates CORS processing in the proper order inside Spring Security. It does **not** mean waiving protection on actual requests.

## 7. Three independent conditions model for an API

Suppose `POST /api/settings` modifies user settings. A sound policy can be expressed as:

```text
Browser cross-origin read permission:
    Origin in allowlist?
       Yes -> browser may read response per CORS if all conditions hold
       No -> browser cannot read; may not send main request
        
Server request validity:
    Valid authentication?
       No -> 401/login redirect
       Yes -> continue
    Valid CSRF proof for unsafe method and session?
       No -> 403
       Yes -> continue
    User has role/ownership to modify data?
       No -> 403
       Yes -> process action and return response
```

These checks do not necessarily execute in literal text order in every filter chain due to Spring Security's filter ordering and exception handling, yet **the security conditions never substitute for one another**.

Scenario comparison table:

| Origin in allowlist | Session valid | CSRF token valid | Business permission | Conclusion |
| --- | --- | --- | --- | --- |
| Yes | No | No | Not evaluated | Browser permitted CORS origin-wise; **action denied** |
| Yes | Yes | No | Yes | State-changing request **blocked by CSRF** |
| Yes | Yes | Yes | No | Auth/CSRF valid; **blocked by authorization** |
| Yes | Yes | Yes | Yes | Request can be processed |
| No | Yes | No | Yes | Browser cannot read response; server must still **block CSRF itself** |
| No | Yes | Yes | Yes | For browser-sent requests, CORS blocks reading response; server decision still depends on other policies |

**Do not use this table to infer one fixed HTTP status:** Spring Security form login may 302 redirect, bearer APIs usually return 401, and rejected CORS preflights typically get 403 with the browser reporting a network/CORS error. Exact HTTP codes depend on mechanisms, filter ordering, and handlers; verify with real requests.

## 8. Spring Boot 3.5 / Java 17 example: keeping CORS, authentication, and CSRF separate

The example below is a Spring Boot **3.5.16, Java 17+, Servlet MVC** application with:

- Trusted frontend expected at `https://app.example.com`; backend at `https://api.example.com`.
- CORS allows **strictly** that frontend, permitting session cookies when browsers configure `credentials: "include"`.
- Authentication via Spring Security **formLogin + HTTP session**. Sample data is for local development only.
- CSRF **enabled by default** for POST/PUT/PATCH/DELETE; uses `GET /csrf` for the frontend to fetch tokens.
- `GET /api/me` requires authentication.
- `POST /api/settings` requires `ROLE_USER` and must still pass the CSRF filter.
- Controller demonstrates authentication/authorization without **writing to a database**; the response confirms the payload was accepted.

This is an educational demo: replace origins, accounts, passwords, session store, TLS, account policies, and CSRF/login UX in real deployments.

### 8.1. Structure

```text
cors-csrf-security-demo/
├── pom.xml
├── src/main/java/demo/security/CorsCsrfApplication.java
└── src/test/java/demo/security/CorsCsrfApplicationTests.java
```

### 8.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>cors-csrf-security-demo</artifactId>
    <version>1.0.0</version>

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
```

`spring-boot-starter-security` supplies Spring Security config/web and password encoder implementations. `spring-security-test` is used for MockMvc. No separate "CORS security" dependency is needed: Spring Web MVC and Spring Security already include the required classes.

### 8.3. `CorsCsrfApplication.java`

```java
package demo.security;

import java.security.Principal;
import java.util.List;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@SpringBootApplication
public class CorsCsrfApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsCsrfApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder passwords) {
        UserDetails learner = User.withUsername("learner")
            .password(passwords.encode("local-learning-only"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        // Do not use "*" or reflect every caller's Origin.
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(List.of(
            "Content-Type", "X-CSRF-TOKEN"));

        // Allow credentialed requests from allowed origin.
        // This does NOT grant login or waive CSRF checks.
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            // Integrate CorsFilter before Spring authentication logic.
            .cors(Customizer.withDefaults())

            // Keep CSRF protecting unsafe methods using session cookies.
            .csrf(Customizer.withDefaults())

            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                    "/", "/public", "/csrf").permitAll()
                .requestMatchers(HttpMethod.GET,
                    "/api/me").authenticated()
                .requestMatchers(HttpMethod.POST,
                    "/api/settings").hasRole("USER")
                .anyRequest().denyAll())

            // Form login uses session; login URL is permitAll.
            .formLogin(form -> form
                .defaultSuccessUrl("/public", true)
                .permitAll())
            .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/")
    Map<String, String> index() {
        return Map.of(
            "csrfEndpoint", "/csrf",
            "loginPage", "/login",
            "protectedEndpoint", "/api/me");
    }

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/csrf")
    CsrfToken csrf(CsrfToken csrfToken) {
        return csrfToken;
    }

    @GetMapping("/api/me")
    Map<String, String> whoAmI(Principal principal) {
        return Map.of("name", principal.getName());
    }

    @PostMapping("/api/settings")
    Map<String, String> requestSettingsChange(
            @RequestBody DisplayNameRequest input,
            Principal principal) {
        // Do not write DB; only shows request passed SecurityFilterChain.
        return Map.of(
            "status", "accepted",
            "user", principal.getName(),
            "requestedDisplayName", input.displayName());
    }

    record DisplayNameRequest(String displayName) {}
}
```

**What does each part protect?**

- `corsConfigurationSource()` enforces an **exact origin** allowlist matching scheme/host/port. `setAllowCredentials(true)` enables credentialed CORS from that origin if browser and cookie policies also allow it.
- `http.cors(...)` ensures CORS runs before Spring authentication, accommodating preflights that carry no session cookie.
- `csrf(...)` stays enabled. Spring Security by default validates unsafe HTTP methods like POST with a valid CSRF token; CORS does not replace this step.
- `authorizeHttpRequests(...)` requires identity at `/api/me` and adds `ROLE_USER` on `POST /api/settings`. Changing the origin cannot grant user roles.
- `formLogin(...)` provides the login page/processing filter and session-based authentication. `permitAll()` applies to Spring-managed login endpoints, not `permitAll()` for the whole application.
- `CsrfToken` is issued and stored per the `CsrfTokenRepository` strategy (session-backed by default in this config). GET `/csrf` exposes the token to the frontend.
- `Map.of(...)` in the controller only returns JSON without updating a real system. When adding a DB, verify ownership/validation in the service layer rather than relying solely on `ROLE_USER`.

**Important:** `https://app.example.com` is an illustrative production origin, not a frontend built by this project. To test from a dev frontend like `http://localhost:5173`, change the allowlist to **that exact dev origin** and keep that config strictly in the dev environment. When testing the backend directly on `http://localhost:8080`, CORS does not apply if requests are same-origin or lack `Origin` like browser cross-origin requests.

## 9. Browser sequence with CSRF token and session

Assume the real frontend runs at `https://app.example.com` and the backend at `https://api.example.com` has TLS and routing configured per the example. Because the backend uses **session cookies**, the frontend needs `credentials: "include"` on cross-origin fetches, while cookies remain subject to SameSite, Secure, and browser policies.

### 9.1. Fetching the CSRF token before sending POST

```javascript
const API_BASE = "https://api.example.com";

async function obtainCsrf() {
  const response = await fetch(API_BASE + "/csrf", {
    credentials: "include"
  });
  if (!response.ok) {
    throw new Error("Cannot obtain CSRF token");
  }
  const csrf = await response.json();
  return { name: csrf.headerName, value: csrf.token };
}

// On a page whose origin is allowed by the server:
const csrfBeforeLogin = await obtainCsrf();
console.log(csrfBeforeLogin.name);  // Usually "X-CSRF-TOKEN"
// Never print real tokens to logs/console in production.
```

The `/csrf` endpoint permits anonymous access to fetch a token bound to the initial session. **Obtaining a CSRF token does not prove the user is logged in.** An unauthenticated client can still fetch a token if the product permits it; the server must still enforce authentication on protected resources.

### 9.2. Login and refreshing the token

Spring Security Form Login's default processing endpoint is POST `/login`. A frontend can submit form-encoded credentials + CSRF header via fetch:

```javascript
async function login(username, password) {
  const csrf = await obtainCsrf();

  const response = await fetch(API_BASE + "/login", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      [csrf.name]: csrf.value
    },
    body: new URLSearchParams({ username, password })
  });

  // Form login may redirect to /public or /login?error.
  // Real apps should verify login state via an API.
  if (!response.ok) {
    throw new Error("Login request failed or was rejected");
  }

  // BY DEFAULT, Spring refreshes the CSRF token after authentication.
  return obtainCsrf();
}
```

**Do not rely on `response.ok` alone to conclude "password correct"**: browser fetch usually follows redirects, and the final response might be the error login page returning HTTP 200. After login, call `/api/me` to verify authenticated status, or design a JSON login API with an explicit contract.

After login or logout, Spring Security can clear old CSRF tokens via `CsrfAuthenticationStrategy` / `CsrfLogoutHandler`. **The frontend must fetch a fresh token**, otherwise subsequent POSTs may fail with 403 even with a valid new session. Never put CSRF tokens in URL queries, unbounded localStorage, or logs.

### 9.3. Sending requests with both session and CSRF token

```javascript
async function requestDisplayNameChange(newName) {
  const csrf = await obtainCsrf();

  const response = await fetch(API_BASE + "/api/settings", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      [csrf.name]: csrf.value
    },
    body: JSON.stringify({ displayName: newName })
  });

  if (!response.ok) {
    throw new Error("Settings request rejected: " + response.status);
  }
  return response.json();
}
```

In a real frontend, you do not necessarily have to call `GET /csrf` before *every* POST: you can manage tokens per session lifecycle and refresh after login/logout or expiration. Calling it again here keeps the flow simple to demonstrate, not an optimized traffic pattern.

Because the request carries `Content-Type: application/json` and custom `X-CSRF-TOKEN`, the browser triggers a preflight on cross-origin calls. After preflight succeeds, Spring still requires **a valid session cookie and valid CSRF token** to process the POST.

**Two origins that are same-site yet cross-origin** like `app.example.com` and `api.example.com` can share session cookies per browser policy. If the frontend lives on a completely different site, account for third-party cookie blocking and `SameSite=None; Secure`; prefer a same-site reverse proxy/BFF when appropriate. Never "fix" cookie errors by opening `Access-Control-Allow-Origin: *`.

## 10. Testing Spring Security with MockMvc

In Spring Boot 3.5, `spring-boot-starter-test` and `spring-security-test` provide `MockMvc` and `user(...)`/`csrf()` helpers. The tests below **require no real frontend** and directly verify the protection layers.

Create `src/test/java/demo/security/CorsCsrfApplicationTests.java`:

```java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

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
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsCsrfApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void allowedOriginPreflightDoesNotRequireLogin() throws Exception {
        mvc.perform(options("/api/settings")
                .header(HttpHeaders.ORIGIN, "https://app.example.com")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.com"));
    }

    @Test
    void disallowedOriginPreflightIsRejected() throws Exception {
        mvc.perform(options("/api/settings")
                .header(HttpHeaders.ORIGIN, "https://evil.example.net")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
            .andExpect(status().isForbidden());
    }

    @Test
    void allowedOriginDoesNotAuthenticateAnonymousUser()
            throws Exception {
        mvc.perform(get("/api/me")
                .header(HttpHeaders.ORIGIN, "https://app.example.com"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void authenticatedUserMayReadSafeEndpointWithoutCsrf()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(user("learner").roles("USER"))
                .header(HttpHeaders.ORIGIN, "https://app.example.com"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("learner"));
    }

    @Test
    void authenticatedUserCannotPostWithoutCsrf() throws Exception {
        mvc.perform(post("/api/settings")
                .with(user("learner").roles("USER"))
                .header(HttpHeaders.ORIGIN, "https://app.example.com")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Lan\"}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedUserWithCsrfMayPost() throws Exception {
        mvc.perform(post("/api/settings")
                .with(user("learner").roles("USER"))
                .with(csrf().asHeader())
                .header(HttpHeaders.ORIGIN, "https://app.example.com")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Lan\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("accepted"))
            .andExpect(jsonPath("$.user").value("learner"))
            .andExpect(jsonPath("$.requestedDisplayName").value("Lan"));
    }

    @Test
    void csrfEndpointReturnsTokenToClient() throws Exception {
        mvc.perform(get("/csrf"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.token").isString())
            .andExpect(jsonPath("$.headerName").isString());
    }
}
```

Run:

```bash
mvn test
```

If the environment has Java 17+ and resolves dependencies, **7 tests are expected to pass**. The code was statically checked without pretending Maven ran inside Google Sheet. These tests prove:

- OPTIONS preflight from an allowed origin receives CORS permission **without needing a session**.
- OPTIONS from an unknown origin is blocked by CORS.
- A valid `Origin` **does not bypass authentication**.
- GET with a mocked user is permitted without a CSRF token because GET is treated as a safe method.
- POST with a mocked user but missing CSRF → 403.
- POST with user, role, and CSRF → controller returns JSON.
- Backend provides a CSRF token via a session-backed endpoint.

**Important regarding test scope:** `with(user(...))` creates a mock authentication for the request without verifying real passwords; `with(csrf())` supplies a test token without proving browsers protect cookies in production. Real integration tests through reverse proxies, browser cookie policies, and TLS are still needed.

## 11. Quick checks with curl and DevTools

Start the project:

```bash
mvn spring-boot:run
```

### 11.1. Inspecting CORS preflight responses

```bash
curl -i -X OPTIONS http://localhost:8080/api/settings \
  -H 'Origin: https://app.example.com' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-csrf-token'
```

Expected: success status (typically 200) with `Access-Control-Allow-Origin: https://app.example.com`. Preflight **requires no login**.

Replace `Origin` with `https://evil.example.net`:

```bash
curl -i -X OPTIONS http://localhost:8080/api/settings \
  -H 'Origin: https://evil.example.net' \
  -H 'Access-Control-Request-Method: POST'
```

Expected: rejected by the CORS processor, typically HTTP 403. These curl checks only confirm **which headers the server returns**; curl does not enforce browser CORS policies, so it does not prove how all browsers behave.

### 11.2. Origin allowed but unauthenticated request

```bash
curl -i http://localhost:8080/api/me \
  -H 'Origin: https://app.example.com'
```

Expected with `formLogin` configured: **302 redirect to login**, never automatic 200. CORS does not create a session.

### 11.3. POST needs CSRF even with an active session

With session cookies, the real sequence must be:

1. `GET /csrf`, keep the cookie jar and token.
2. `POST /login` sending username/password with the CSRF header and received cookie.
3. Fetch a new CSRF token after login.
4. `POST /api/settings` sending the cookie and CSRF header.
5. Omit the CSRF header on an identical POST: expect 403.

In `curl` shells, you can persist cookies with `-c cookies.txt -b cookies.txt` and parse JSON with an appropriate tool. **Do not hardcode sample tokens**: real tokens are generated by the server and must be taken from the exact response of the same cookie session. Never commit cookie/token files to Git.

Browser DevTools lets you inspect:

- `Network → OPTIONS`: `Origin`, `Access-Control-Request-Method`, and response headers.
- Actual POST request: is `Cookie` present, is `X-CSRF-TOKEN` present, is the real status 401/302/403/200?
- Cookies: Domain, Path, SameSite, Secure, and expiry.
- Console: a CORS error means JavaScript was blocked from reading the response; **never infer the backend did not receive the request**.
- Redirect chains: requests redirected to HTML login pages can cause frontends to perceive CORS errors because the final response lacks headers or differs in origin.

## 12. Secure CORS configuration: dos and don'ts

### 12.1. Never combine wildcards with credentials

The configuration below violates the browser CORS contract when sending credentials:

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

Browsers refuse to share responses with credentialed requests in this case. Never work around it by disabling browser security or using `mode: "no-cors"`: that yields an unreadable *opaque* response and does not make the API any safer.

Instead, for a trusted frontend:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

If multiple origins are allowed, the server should echo the **allowlist-matched** origin and set `Vary: Origin` whenever responses vary by Origin to prevent cache poisoning.

### 12.2. Never blindly reflect any Origin

Counter-example:

```java
// WRONG: accepts any Origin without checking allowlist.
response.setHeader("Access-Control-Allow-Origin",
    request.getHeader("Origin"));
response.setHeader("Access-Control-Allow-Credentials", "true");
```

When an attacker site visits with credentials, the server may allow that site to **read user data**. This is not merely missing authentication; it creates an exfiltration risk whenever the user is authenticated.

Allow **only origins you genuinely own and operate**; check for subdomain takeovers, preview deployments/third-party widgets, and XSS policies. An allowlisted origin effectively receives broad permission to read data via fetch, especially when `allowCredentials=true`.

### 12.3. Do not over-expose methods, headers, or paths

- Allow only methods the frontend needs: GET, POST, PATCH…; never allow everything for convenience.
- `setAllowedHeaders(...)` should list required request headers; when allowing custom headers, remember attackers control JS on any allowed origin.
- Scope CORS mappings strictly to endpoints requiring cross-origin access, such as `/api/**`, `/csrf`, `/login`. If the frontend is same-origin, CORS may not be needed at all.
- Never accidentally let staging/dev origin allowlists leak into production.
- Check CORS at both the reverse proxy/gateway **and** Spring: conflicting headers from two layers can break browsers or open access too wide.

In the example, `/**` was used because form login and the CSRF endpoint also serve a cross-origin frontend. Real products should narrow scope to actual existing routes.

## 13. CSRF across different authentication models

The practical question: **Does the API rely on browser-auto-sent credentials, or must clients explicitly attach credentials on every request?**

| Model | How should CSRF be evaluated? |
| --- | --- |
| **Form login + `JSESSIONID` cookie** | CSRF risk exists on unsafe methods; keep tokens/server-side CSRF protection |
| **OIDC login followed by session cookie** | Still needs CSRF for app mutations; OIDC login state/nonce does not replace CSRF tokens on POSTs |
| **JWT/access token stored in auto-sent cookie** | Still carries CSRF risk like a session cookie, even though the token is signed |
| **Browser-auto-sent HTTP Basic credentials** | Must evaluate CSRF because browsers can auto-attach credentials from auth caches/policies |
| **Bearer JWT attached by JS via `Authorization: Bearer ...`, no cookies/sessions** | Classic browser CSRF is generally lower because attackers cannot attach the victim's bearer header; still need XSS/token-theft defense and architecture verification |
| **API key sent in header by server-to-server clients** | CORS largely does not govern non-browser clients; CSRF generally does not apply the same way if browsers do not auto-send credentials |
| **mTLS or client cert auto-selected by browser** | Must analyze browser/credential auto-attachment and action types; never assume "mTLS means no CSRF" |

**Never decide `csrf.disable()` just because a path starts with `/api/`.** A "REST" API using session cookies still faces CSRF risk. Conversely, a genuinely stateless OAuth2 Resource Server accepting only client-attached `Authorization` bearer headers may disable CSRF on **that specific chain**, provided the condition is verified rather than guessed.

### 13.1. Multiple SecurityFilterChains and boundaries

In hybrid applications, you can separate:

```text
/api/bearer/**:
    Stateless SecurityFilterChain
    OAuth2 Resource Server / bearer authentication
    CSRF policy based on absence of ambient credentials
/web/**:
    Stateful SecurityFilterChain
    formLogin or OAuth2 Login + JSESSIONID
    CSRF protection for unsafe methods
```

Each chain needs appropriate CORS configuration if called cross-origin; mind `@Order` and `securityMatcher(...)`: requests match **the first matching chain**, not all chains. Never design `permitAll` or no-CSRF matchers that accidentally cover stateful routes.

Example snippet **not a standalone runnable class**:

```java
// Illustrates scope only after designing the auth mechanism:
http.securityMatcher("/api/bearer/**")
    .sessionManagement(session ->
        session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
    .csrf(csrf -> csrf.disable())
    .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()));
```

Use only when this chain **does not rely on session cookies or auto-attached credentials** and validates JWT issuer/audience/signature per real configuration. Never carry `csrf.disable()` from here into the form login chain.

## 14. SameSite, custom headers, and secondary defensive layers

### 14.1. SameSite does not equal Origin

A cookie may look like:

```http
Set-Cookie: JSESSIONID=opaque-value; Secure; HttpOnly; SameSite=Lax; Path=/
```

- `HttpOnly` reduces ordinary JavaScript cookie access, yet does not stop browsers from auto-sending cookies.
- `Secure` requires HTTPS (loopback/browser exceptions vary); does not replace authentication.
- `SameSite=Lax/Strict` restricts cookies on some cross-site requests, yet an attacker-controlled same-site subdomain is still same-site despite differing in origin.
- `SameSite=None; Secure` enables certain cross-site cookie scenarios, yet widens CSRF surface and remains subject to third-party cookie blocking.
- Overly broad cookie domains (e.g., sharing across all subdomains) elevate risk when subdomains are untrusted. Prefer host-only cookies or prefixes like `__Host-` where appropriate.

### 14.2. Custom headers are not magic

One Ajax API CSRF strategy requires a custom header that cross-origin attackers cannot set via browsers when preflight is denied. OWASP notes this works when **strictly allowing trusted origins**, rejecting simple request bodies that could bypass, and having no non-browser clients violating restrictions.

However, **an arbitrary custom header checked solely for presence** is weaker than session-bound CSRF tokens in many threat models: if a trusted origin suffers XSS or the CORS allowlist is too broad, attackers can send that header. In the example, Spring Security **validates an issued token**, not merely the presence of an `X-CSRF-TOKEN` header.

### 14.3. Defense in depth

Beyond CSRF tokens, consider:

- **Origin/Referer verification** for unsafe methods when policy allows; missing or `null` `Origin` must never be treated as trusted by default.
- **Fetch Metadata** (e.g., `Sec-Fetch-Site`) to block unwanted cross-site requests; verify browser support and documented exceptions.
- **Content Security Policy** and XSS prevention: if attackers execute JS on the frontend origin, tokens can be stolen or actions triggered from the trusted origin.
- **Strict HTTPS/HSTS**, session fixation protection, timeouts, and logout.
- **Idempotency and business constraints** on critical mutations; never use GET to modify data.
- **Rate limiting** and logging/auditing with sensitive data redacted.

CSRF tokens do not stop a user from intentionally performing an unauthorized action: authorization and business validation remain mandatory. CORS does not replace any link in this chain.

## 15. Common Spring Security pitfalls

| Symptom | Possible cause | Check/fix |
| --- | --- | --- |
| Browser reports CORS despite `@CrossOrigin` on API | Security chain handles preflight before MVC; CORS source not wired or gateway drops headers | Enable `http.cors(...)` and configure source; inspect OPTIONS/responses at ingress |
| OPTIONS returns 302 to `/login` | Preflight carries no cookie and auth filter blocks before CORS | Let CORS handle preflight first; do not disable auth on real requests |
| Preflight 200 but GET/POST returns 401 or login redirect | CORS allows origin, yet request lacks valid credentials | Check `Cookie`/Bearer, session, SameSite, and login |
| GET with session returns 200, POST with same session returns 403 | CSRF token missing, invalid, expired, or rotated after login/logout | Fetch fresh token, send via proper header/param; check `CsrfTokenRepository` |
| POST 403 despite `X-CSRF-TOKEN` | Header exists but token mismatches session; repo expects another token | Verify token issued for that exact session and cookie |
| `Access-Control-Allow-Origin: *` with credentials fails | Browsers forbid wildcards with credentialed CORS | Use explicit origin allowlist; never reflect `Origin` blindly |
| Postman/curl succeeds while browser fails CORS | Non-browser clients ignore browser CORS read restrictions | Inspect browser `Origin`/preflight; never treat Postman passing as proof of CORS |
| App returns sensitive data to attacker origin | CORS reflects `Origin` or allowlist includes a hijacked site | Lock down allowlist, audit subdomain takeover, check session/authorization |
| Cookie not sent by frontend | `fetch` omits `credentials: include`, wrong SameSite/Secure/domain/path, or third-party cookie policy | Inspect `Cookie`/`Set-Cookie` in DevTools and site relationship |
| Session valid, yet first POST after login gets 403 | Old CSRF token cleared/rotated on auth success | Re-fetch `GET /csrf` after login |
| CSRF disabled to "fix CORS" | Misplaced responsibility, potentially opening request-forgery holes | Re-enable CSRF; debug preflight, cookies, and tokens separately |
| Every request from trusted frontend becomes admin | Code treats `Origin` as username/authority | Authenticate strictly via credentials and server-side roles |
| API emits two conflicting CORS headers | Proxy, MVC, and Security overlap configs | Establish clear ownership and test through real ingress |
| Frontend uses `mode: no-cors`, cannot read JSON | Opaque response per Fetch spec; does not fix server CORS | Remove `no-cors`; configure CORS for valid origins/methods/headers |
| CORS allows exact origin yet still blocked | Scheme/port mismatch; request uses disallowed header/method | Compare full origin and `Access-Control-Request-*` |
| GET mutates data without requiring CSRF | GET is not protected by CSRF filters like unsafe methods | Move mutations to POST/PUT/PATCH/DELETE and keep CSRF |

### 15.1. Interpreting statuses in context

A `403` response can come from several places: CORS processor, CSRF validation, `AuthorizationFilter`/AccessDeniedHandler, or business policies. Never conclude "insufficient permissions" from status code alone.

Debugging order:

1. In DevTools, is there an OPTIONS preflight? Was it rejected before the main request?
2. Does the response include matching `Access-Control-Allow-Origin` and `Access-Control-Allow-Credentials` when needed?
3. Does the main request carry the session cookie/access token?
4. Did Spring Security build the right `Authentication` and authorities?
5. Does the unsafe-method request include a session-matching CSRF token?
6. Do the controller/service enforce roles and ownership?
7. Do proxies/cookie domains/SameSite/redirects alter behavior across local/staging/production?

You can temporarily raise Spring Security logging in a dedicated dev environment to see which filter rejected the request. **Never enable logging of full request headers/cookies/tokens in production**.

## 16. Self-check questions

1. **Does CORS allowing `https://app.example.com` prove who called the API?** No. Origin is a browser read-access boundary, not a principal.
2. **Why can CORS preflight return 200 while the subsequent request gets 401?** Because OPTIONS only checks method/origin/headers, whereas the actual request must authenticate.
3. **If CORS blocks the attacker from reading the response, is the server guaranteed not to execute the action?** No. Simple requests can still be sent; CSRF protects state changes.
4. **Does a CORS preflight carry `JSESSIONID`?** No; therefore CORS must run before authentication on actual requests.
5. **Do GET and POST have the same CSRF requirements?** By default Spring Security protects unsafe methods like POST; GET must have no side effects and still needs auth/authorization if protected.
6. **Why refresh the CSRF token after login/logout?** Spring Security may clear/rotate tokens per its authentication/logout strategy.
7. **Do `Access-Control-Allow-Origin: *` and `Allow-Credentials: true` let browsers send cookies and read responses?** No; credentialed CORS rejects wildcards.
8. **Do SameSite cookies block cross-origin requests that are same-site?** Not guaranteed; same-site is broader than same-origin.
9. **If a JWT is stored in an auto-sent cookie, do you still need to consider CSRF?** Yes; JWT does not change ambient-credential behavior.
10. **If an API key is sent in a header by a server-to-server client, does CORS govern that client?** Mostly no; CORS is a browser policy, and the server must still validate the API key.
11. **If an authenticated user lacks `ROLE_ADMIN`, does enabling CORS permit admin actions?** No; authorization must deny them.
12. **Should CSRF be disabled globally just because an SPA uses `fetch`?** No; check whether the SPA relies on cookies/sessions and protect each chain accordingly.
13. **When do custom headers help against CSRF?** When browser preflight and CORS allowlists are strictly locked down and the server prevents simple-request bypasses; pair with tokens per threat model.
14. **Does a test using `with(user(...))` verify password login end-to-end?** No. It mocks `Authentication` to focus on authorization/CSRF.
15. **If the trusted frontend has an XSS flaw, can CORS stop it?** No. Scripts on the trusted origin can send allowed requests; prevent XSS and guard tokens/sessions.
16. **To tell whether a POST was blocked by CORS or CSRF, what should you inspect?** Preflight, main request, response, cookies, CSRF header, and Spring Security filter logs in a safe environment.

## 17. Pre-production checklist

- [ ] Exact origin allowlist; no arbitrary reflection or wildcard with credentials.
- [ ] CORS runs **before authentication** for preflights; OPTIONS never bypasses security on actual requests.
- [ ] Sensitive APIs always enforce server-side authentication and authorization.
- [ ] Cookie/session-based unsafe requests are protected by CSRF tokens or an equivalent designed, tested, and audited mechanism.
- [ ] CORS allows strictly the HTTP methods, request headers, and routes actually needed.
- [ ] CSRF tokens refresh properly on login/logout; frontend stores and transmits them over proper channels.
- [ ] Cookie `HttpOnly`, `Secure`, `SameSite`, `Domain`, `Path`, and proxy trust match the real architecture.
- [ ] Zero GET endpoints mutate state.
- [ ] Tested same-origin, cross-origin allow, cross-origin deny, missing auth, missing CSRF, invalid CSRF, wrong role, and valid requests.
- [ ] Evaluated CSRF for JWT-in-cookie, Basic Auth, and mTLS/browser credentials; never relied solely on the label "REST API".
- [ ] Logging/APM never writes CSRF tokens, session cookies, passwords, or raw bearer tokens.
- [ ] Evaluated XSS/CSP, Origin/Referer/Fetch Metadata checks, rate limits, and session expiration.
- [ ] Integration tests run through the real reverse proxy/gateway; avoid conflicting CORS headers across two layers.
- [ ] Clearly documented the security owner, origins, authentication mode, CSRF mode, and endpoints of every `SecurityFilterChain`.

## 18. Official references

- Spring Security – CORS (Servlet): https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security – CSRF (Servlet): https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security – Servlet Security Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security – Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security – Servlet Testing, MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Framework – CORS support: https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html
- MDN – Cross-Origin Resource Sharing: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS
- MDN – CSRF attack and defenses: https://developer.mozilla.org/en-US/docs/Web/Security/Attacks/CSRF
- MDN – Access-Control-Allow-Credentials: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Credentials
- OWASP – Cross-Site Request Forgery Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP – Cross-Site Scripting Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
