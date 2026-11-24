# Coordinating CORS with Session Cookies, CSRF, and Bearer Tokens in Spring Security Reactive

> **Module:** Spring Security - reactive  
> **Knowledge group:** CORS Configuration  
> **Learning goal:** Distinguish CORS, authentication, cookies/sessions, and CSRF; properly configure preflight, origins, credentials, and headers for both client patterns; verify with Spring WebFlux, Spring Security, `WebTestClient`, and real-world failure scenarios.

## 1. Why Is This Problem Easy to Misconfigure?

Suppose you have a frontend at `http://localhost:5173` and a Spring WebFlux API at `http://localhost:8080`. The two addresses have different **origins** due to different ports, even on the same host. The frontend uses two interaction styles:

1. **Web app logged in with a session cookie:** the browser holds the `SESSION` cookie and attaches it automatically when calling the API, e.g., `POST /session/notes`. State-changing requests must also carry a valid **CSRF token**, not just the cookie.
2. **API client attaching a Bearer access token:** JavaScript explicitly sends `Authorization: Bearer ...` on each request, e.g., `POST /token/notes`. The browser typically sends a **CORS preflight** because the `Authorization` header is not a simple request header. The JWT Resource Server must validate the token itself.

Common mistakes:

- Enabling `Access-Control-Allow-Origin: *` with `Access-Control-Allow-Credentials: true` for session cookies, causing the browser to reject the response.
- Confusing CORS with an authentication mechanism, thinking blocking unknown origins alone makes an API safe against `curl` or other servers.
- Disabling CSRF simply because CORS is enabled; a malicious request can still **cause side effects** even when the attacker cannot read the response.
- Letting an authentication filter block `OPTIONS` preflight because preflight carries neither session cookies nor Bearer tokens.
- Permitting session cookies on the very API where CSRF was disabled because "the API uses JWT".
- Forgetting to allow `Authorization` or `X-CSRF-TOKEN` in `Access-Control-Allow-Headers`, causing the browser to block requests before reaching the controller.
- Sending Bearer tokens in response URLs/logs or storing them long-term in JavaScript-accessible areas vulnerable to XSS theft.

**Principle:** CORS is the policy governing *when a browser may read cross-origin responses and send requests*. Authentication proves identity, authorization grants permissions, and CSRF protects operations using credentials that the browser may attach automatically. None of these components replaces another.

## 2. Origin Differs from Site; Cookies Depend on Both

An **origin** is the tuple `scheme + hostname + port`. `https://app.example.com` and `https://api.example.com` are different origins due to hostname, yet may be **same-site** for cookie evaluation (depending on scheme and registrable domain). `http://localhost:5173` and `http://localhost:8080` are different origins due to port, yet are normally treated as same-site.

| Frontend | API | Same origin? | Key takeaway |
| --- | --- | --- | --- |
| `http://localhost:5173` | `http://localhost:8080` | No | CORS due to different port; local cookies may be same-site |
| `https://app.example.com` | `https://api.example.com` | No | CORS; cookie domain/path and site require separate evaluation |
| `https://app.example.net` | `https://api.example.com` | No | Cross-site; `SameSite=None; Secure` cookies may be needed if design relies on third-party cookies |
| `https://api.example.com` | `https://api.example.com` | Yes | No CORS needed, yet CSRF may still be required when using auto-sent credentials |

**SameSite is not CORS.** Whether the browser sends a cookie depends on `SameSite`, `Secure`, `Path`, `Domain`, and browser privacy controls; whether the frontend can read the response depends on Same-Origin Policy/CORS. CORS cannot force the browser to send cookies blocked by `SameSite` or third-party cookie policies.

When the website and API can share the same origin, a **Backend-for-Frontend (BFF)** or same-origin reverse proxy typically simplifies cookies and CSRF. Using cross-site cookies involves more than adding two HTTP headers: you must account for browser protections, HTTPS, privacy restrictions, and client compatibility.

## 3. CORS and CSRF Mitigate Two Different Threats

**CORS:** the browser inspects response headers such as `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, and `Access-Control-Allow-Credentials` to decide whether a script from another origin may access the response and send requests requiring preflight.

**CSRF:** a malicious page tricks a victim's browser into sending requests to a site where the victim is logged in, exploiting **automatically sent** cookies or credentials. The server must prove the action was not merely triggered by the browser on an attacker's behalf: CSRF tokens in forms/headers, appropriate `Origin`/`Referer` checks, `SameSite`, and proper HTTP verb design.

A plain cross-site form can trigger a **POST** even when the server does not enable CORS for the attacker. The browser prevents the attacker's script from reading the response, yet the server-side side effect **may already have occurred**. Thus a tight CORS configuration **does not replace CSRF protection**.

~~~mermaid
flowchart TD
    A["Browser sends cross-origin request"] --> B{"Does request require preflight?"}
    B -->|"Yes"| C["OPTIONS + Origin + Access-Control-Request-*"]
    C --> D{"Does server CORS allow it?"}
    D -->|"No"| E["Browser blocks actual request"]
    D -->|"Yes"| F["Actual request"]
    B -->|"No"| F
    F --> G["Authentication: session cookie or Bearer"]
    G --> H["CSRF if relying on auto-sent credentials"]
    H --> I["Authorization by role/scope/object"]
    I --> J["Controller / service"]
    J --> K["Response + CORS response headers"]
    K --> L["Browser decides whether script may read response"]
~~~

**CORS is not an API firewall.** Non-browser clients such as `curl`, backend services, or bots can send HTTP requests regardless of CORS. Nor is the `Origin` header proof of login: many HTTP clients can set this value freely.

## 4. What Does an OPTIONS Preflight Contain and Omit?

A JSON request carrying `Authorization` or a custom CSRF header usually requires a preflight:

~~~http
OPTIONS /token/notes HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

A server that permits it may respond:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: Authorization,Content-Type
Vary: Origin,Access-Control-Request-Method,Access-Control-Request-Headers
~~~

Status 200 is illustrative; a compliant handler may return 204. **What matters is returning the right CORS headers**, not forcing 200 on preflight across every implementation.

Preflight **does not send session cookies or Bearer access tokens like a normal request**. If a security filter demands Authentication before CORS runs, `OPTIONS` easily fails with 401 or redirects to `/login`, causing the browser to report an error. Spring Security documentation requires CORS to be processed before security authentication; WebFlux can use `CorsWebFilter` or integrate CORS into `ServerHttpSecurity.cors(...)` with a `CorsConfigurationSource`.

**Do not "fix" this with `OPTIONS /** permitAll` while ignoring CORS policy.** You must still govern allowed origins/methods/headers; prioritize a properly ordered CORS filter/integration, then test preflight **without** sending credentials.

## 5. Essential CORS Headers

| Header | Sender | Effect |
| --- | --- | --- |
| `Origin` | Browser request | Origin requesting access |
| `Access-Control-Request-Method` | Browser preflight | Method of the upcoming actual request |
| `Access-Control-Request-Headers` | Browser preflight | Non-safelisted headers, such as authorization |
| `Access-Control-Allow-Origin` | Server response | Origin permitted to read the response |
| `Access-Control-Allow-Credentials` | Server response | Allows browser to expose credentialed cross-origin responses when true |
| `Access-Control-Allow-Methods` | Server preflight response | Permitted methods |
| `Access-Control-Allow-Headers` | Server preflight response | Permitted request headers |
| `Access-Control-Expose-Headers` | Server response | Extra response headers JS may read; unrelated to sending request headers |
| `Access-Control-Max-Age` | Server preflight response | TTL for which browser may cache preflight |
| `Vary` | Server/proxy response | Prevents mis-serving cached responses across different Origins/methods/headers |

When using cookie credentials, return a **specific origin** rather than `*` in `Access-Control-Allow-Origin`, along with `Access-Control-Allow-Credentials: true`. In Spring, `setAllowedOrigins(List.of("http://localhost:5173"))` and `setAllowCredentials(true)` express that intent. Never use `allowedOriginPatterns("*")` as a workaround; reflecting every origin lets any website read credentialed responses whenever the browser attaches cookies.

**The `Authorization` header is not an exposed header.** `Access-Control-Allow-Headers: Authorization` lets the frontend *send* `Authorization`. `Access-Control-Expose-Headers` governs only *reading response headers*, not sending request headers.

## 6. Model A — Session Cookies and CSRF

~~~mermaid
sequenceDiagram
    participant F as Frontend origin :5173
    participant B as Browser
    participant API as WebFlux :8080
    F->>B: Frontend initiates API call
    B->>API: OPTIONS /session/notes (if JSON/CSRF header)
    API-->>B: CORS response for allowed Origin
    B->>API: GET /session/csrf + cookie (if any)
    API-->>B: CSRF token + session cookie (if needed)
    B->>API: POST /login + CSRF + credentials
    API-->>B: Establishes authenticated session
    B->>API: POST /session/notes + SESSION + X-CSRF-TOKEN
    API->>API: Authenticate session + verify CSRF + authorize
    API-->>B: 200 and Access-Control-Allow-Origin
~~~

In WebFlux, the session ID usually lives in the `SESSION` cookie (not named `JSESSIONID` by default as in Servlet). `WebSessionServerSecurityContextRepository` stores the `SecurityContext` in `WebSession`. Subsequent requests carrying a valid cookie load `Authentication` from the session; the cookie is a **reference**, not a password or JWT.

CSRF protection is essential for **POST/PUT/PATCH/DELETE** requests sent by browsers with auto-attached cookies. Spring Security WebFlux **enables CSRF protection by default**. By default, the expected token is stored in `WebSession` via `WebSessionServerCsrfTokenRepository`, and the token is placed into exchange attributes. Spring Security 6 defaults to `XorServerCsrfTokenRequestAttributeHandler` to help mitigate BREACH.

In the lab, `GET /session/csrf` returns the token provided by the request handler, and the frontend sends it back in the `X-CSRF-TOKEN` header. This avoids confusion between the raw `XSRF-TOKEN` cookie and the XOR-masked token.

**After login/logout**, the CSRF token may rotate or be cleared per configuration. The SPA should fetch a fresh token whenever session state changes; never persist stale tokens in `localStorage` or shared caches.

## 7. Model B — Authorization Bearer Header

~~~mermaid
sequenceDiagram
    participant JS as SPA :5173
    participant B as Browser
    participant API as Resource Server :8080
    JS->>B: fetch with Authorization: Bearer
    B->>API: OPTIONS /token/notes (no Bearer)
    API-->>B: Allows origin + Authorization,Content-Type
    B->>API: POST /token/notes + Bearer access token
    API->>API: Verify JWT + scope (every request)
    API-->>B: 200 + Access-Control-Allow-Origin
~~~

For a **header-only Bearer API** that accepts no session cookies, HTTP Basic, or other browser auto-attached credentials for authentication, you can typically disable CSRF on **that API's** security chain after threat modeling. You must **not** apply that conclusion to an application storing JWTs inside cookies: whenever the browser automatically sends a JWT cookie, CSRF risk remains.

A JWT Resource Server does not rely on CORS to authenticate tokens. It must verify signature, issuer, expiry/nbf, appropriate audience, and scopes. Spring Security JWT typically converts scopes into authorities prefixed with `SCOPE_`. Default issuer validation does not guarantee the right audience for every API; add an audience validator per contract.

A valid access token does not guarantee permission to read or write every resource. Route-level scope checks must be followed by object/tenant ownership checks in the service layer.

## 8. Lab Design: Two Mutually Exclusive Spring Profiles

We create **one Maven project** with two profiles, enabling **only one per run**:

- `session`: CORS for `http://localhost:5173` + credentials, form login, `WebSession`, and default CSRF; GET token, GET user, POST notes.
- `bearer`: CORS allowing only origin and Bearer headers without credentialed CORS; JWT resource server authenticating each request without storing a `WebSession` security context; CSRF disabled **only** on the Bearer-only chain.
- Both security chains share the default scope yet belong to separate profiles; never enable both simultaneously. That avoids accidentally using a session to authenticate an endpoint with CSRF disabled.
- The controller merely echoes data to observe security behavior. There is no database repository in the lab; **CSRF is verified by whether requests reach the controller**, not by committing real transactions.

Requires Java 17+, Maven, and Spring Boot `3.3.13` as the lab baseline compatible with Spring Security 6.x. The Boot 3.3 branch has ended OSS support, so new production projects must choose a currently supported version. JWT configuration in the `bearer` profile needs a real issuer/OIDC provider for real tokens; tests using `mockJwt()` do **not** verify signatures or issuers.

~~~text
cors-security-reactive/
├── pom.xml
└── src/
    ├── main/java/example/cors/
    │   ├── CorsApplication.java
    │   ├── SecurityConfiguration.java
    │   └── ApiController.java
    ├── main/resources/
    │   └── application.yml
    └── test/java/example/cors/
        ├── SessionCorsTest.java
        └── BearerCorsTest.java
~~~

### 8.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>cors-security-reactive</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
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

Do not add `spring-boot-starter-web`. `spring-security-test` provides `WebTestClient` mutators such as `csrf()`, `mockUser()`, and `mockJwt()`. Mock security tests validate filter/authorization behavior; they do **not** prove the JWT decoder verifies signatures.

### 8.2. CorsApplication.java

~~~java
package example.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsApplication.class, args);
    }
}
~~~

### 8.3. application.yml

~~~yaml
server:
  port: 8080
~~~

To run the `bearer` profile with real tokens, you must also configure an active issuer via Spring Boot's standard environment variable:

~~~bash
export SPRING_SECURITY_OAUTH2_RESOURCESERVER_JWT_ISSUER_URI=https://issuer.example.com/issuer
~~~

The command above is a template; `issuer.example.com` must be replaced with a real issuer serving valid metadata and a JWK Set. In Windows PowerShell, set the environment variable using PowerShell syntax for that terminal session. Never sign tokens with a hardcoded secret in source code or accept unverified tokens.

## 9. SecurityConfiguration: Two CORS Policies and Two Profile-Separated Chains

File `src/main/java/example/cors/SecurityConfiguration.java`:

~~~java
package example.cors;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    private static final String FRONTEND = "http://localhost:5173";

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        // Cookie session: allow only the explicit origin and credentials.
        CorsConfiguration session = new CorsConfiguration();
        session.setAllowedOrigins(List.of(FRONTEND));
        session.setAllowCredentials(true);
        session.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        session.setAllowedHeaders(
            List.of("Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"));
        session.setMaxAge(1800L);

        // Header-only Bearer: do not use cookie credentials.
        CorsConfiguration bearer = new CorsConfiguration();
        bearer.setAllowedOrigins(List.of(FRONTEND));
        bearer.setAllowCredentials(false);
        bearer.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        bearer.setAllowedHeaders(
            List.of("Authorization", "Content-Type"));
        bearer.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/session/**", session);
        source.registerCorsConfiguration("/login", session);
        source.registerCorsConfiguration("/logout", session);
        source.registerCorsConfiguration("/token/**", bearer);
        return source;
    }

    @Bean
    @Profile("session")
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    @Profile("session")
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails student = User.withUsername("student")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(student);
    }

    @Bean
    @Profile("session")
    SecurityWebFilterChain sessionChain(
            ServerHttpSecurity http,
            CorsConfigurationSource corsSource) {

        var repo = new WebSessionServerSecurityContextRepository();

        return http
            .cors(cors -> cors.configurationSource(corsSource))
            .securityContextRepository(repo)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/session/csrf").permitAll()
                .pathMatchers("/login", "/logout").permitAll()
                .pathMatchers("/session/**").authenticated()
                .anyExchange().denyAll()
            )
            .formLogin(form -> form.securityContextRepository(repo))
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .csrf(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Profile("bearer")
    SecurityWebFilterChain bearerChain(
            ServerHttpSecurity http,
            CorsConfigurationSource corsSource) {

        var noOp = NoOpServerSecurityContextRepository.getInstance();

        return http
            .cors(cors -> cors.configurationSource(corsSource))
            .securityContextRepository(noOp)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/token/me")
                    .authenticated()
                .pathMatchers(HttpMethod.POST, "/token/notes")
                    .hasAuthority("SCOPE_notes.write")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .requestCache(ServerHttpSecurity.RequestCacheSpec::disable)
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
    }
}
~~~

**Review each decision carefully:**

1. `CorsConfigurationSource` is configured *per path*, not globally for every origin/method. Both `session` and `bearer` permit only the explicit frontend origin; only `session` sets `allowCredentials(true)`.
2. `sessionChain` enables CORS at the right position via `ServerHttpSecurity.cors(...configurationSource...)`, so preflight is not treated as an anonymous request and blocked ahead of CORS.
3. `session` uses `WebSessionServerSecurityContextRepository` and form login; CSRF stays enabled by default. Cookies/sessions are server-managed; to enforce HTTPS/cookie flags in production, configure the `WebSession` cookie policy accordingly.
4. `bearerChain` uses a JWT Resource Server, disables form login, Basic auth, and session authentication, and uses `NoOpServerSecurityContextRepository`. **Only because this chain is strictly header-only** is CSRF disabled in the lab.
5. For real tokens, the Resource Server needs a trusted issuer/JWKS, JWT signature/timestamp/issuer validation, and an audience matching the API. It **does not issue tokens**; tokens come from the Authorization Server/IdP.
6. `hasAuthority("SCOPE_notes.write")` protects only the route; service methods mutating real data must still check owner/tenant/business rules.
7. `anyExchange().denyAll()` blocks undeclared URLs. Under the `session` profile, `/token` is not open; under the `bearer` profile, `/session` and `/login` are not active.
8. If both a session UI and a Bearer API must coexist in one deployment, do not copy both profile chains verbatim and enable them simultaneously. Configure **URL-partitioned `securityMatcher`s, explicit `@Order`, and separate repositories/auth mechanisms/CSRF per chain**, and test that neither chain accepts unintended credentials.

### Why Not Use a CORS Wildcard for Sessions?

When `allowCredentials(true)`, browsers reject `Access-Control-Allow-Origin: *`. Spring also validates against wildcard allowed origins paired with credentials. Using `allowedOriginPatterns("*")` to echo every `Origin` does not eliminate the risk: an attacker's origin would be echoed as a trusted origin. Allowlist only the frontend origins genuinely required, including scheme and port, and manage them via environment-specific configuration.

### Standalone CorsWebFilter vs. Security Integration?

Spring Security WebFlux can integrate CORS from a `CorsConfigurationSource` as shown above; documentation also describes `CorsWebFilter` for running preflight ahead of security. Never install **two competing CORS filters** hoping headers merge properly. Pick one strategy, test all preflight and actual responses, and verify whether an API gateway or reverse proxy also injects CORS headers.

## 10. ApiController: CSRF Token and Two Protected APIs

File `src/main/java/example/cors/ApiController.java`:

~~~java
package example.cors;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

record NoteInput(String value) {}

@RestController
public class ApiController {

    @GetMapping("/session/csrf")
    public Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> supplied =
            exchange.getAttribute(CsrfToken.class.getName());

        if (supplied == null) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "CSRF protection not configured"));
        }

        return supplied.map(token -> Map.of(
            "headerName", token.getHeaderName(),
            "token", token.getToken()
        ));
    }

    @GetMapping("/session/me")
    public Mono<Map<String, String>> sessionMe() {
        return me();
    }

    @GetMapping("/token/me")
    public Mono<Map<String, String>> tokenMe() {
        return me();
    }

    private Mono<Map<String, String>> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> Map.of(
                "user", ctx.getAuthentication().getName()));
    }

    @PostMapping("/session/notes")
    public Mono<Map<String, String>> sessionWrite(
            @RequestBody Mono<NoteInput> body) {
        return body.map(input -> Map.of("accepted", input.value()));
    }

    @PostMapping("/token/notes")
    public Mono<Map<String, String>> tokenWrite(
            @RequestBody Mono<NoteInput> body) {
        return body.map(input -> Map.of("accepted", input.value()));
    }
}
~~~

**Note that this code intentionally echoes input without writing to a database.** Its purpose is distinguishing which requests pass CORS, authentication, CSRF, and authorization. When adapting to real updates, enforce data constraints and permissions in the service layer.

Endpoint `GET /session/csrf` reads `Mono<CsrfToken>` from the exchange attribute populated by `CsrfWebFilter`. In Spring Security 6, the XOR handler is enabled by default to protect tokens rendered in responses; the frontend must return the exact token value received from this endpoint using the returned header name (typically `X-CSRF-TOKEN`).

Never expose this endpoint to all origins: even though the token does not replace authentication, a faulty CORS allowlist paired with credentialed responses can leak unnecessary state. Set `Cache-Control: no-store` on token responses or configure appropriate cache headers in production; never let a public proxy cache a user's token.

## 11. Browser: Calling the Session API Properly

**Step 1 — log in:** in this simplified lab, open `http://localhost:8080/login` in the browser and log in with `student` / `demo-pass`. Spring Security's default form login page includes its own CSRF token. The browser stores the session cookie if cookie policies allow it.

**Step 2 — SPA fetches the token after login and then POSTs:** JavaScript inside the `http://localhost:5173` frontend:

~~~javascript
const API = "http://localhost:8080";

// Already logged in via browser; allow cookies on cross-origin fetch.
const csrfResponse = await fetch(API + "/session/csrf", {
  credentials: "include",
  cache: "no-store"
});

if (!csrfResponse.ok) {
  throw new Error("Cannot obtain CSRF token");
}

const csrf = await csrfResponse.json();

const result = await fetch(API + "/session/notes", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    [csrf.headerName]: csrf.token
  },
  body: JSON.stringify({value: "hello-session"})
});

if (!result.ok) {
  throw new Error("Session request rejected");
}

console.log(await result.json());
~~~

JSON output from the endpoint once authenticated and CSRF-validated:

~~~json
{"accepted":"hello-session"}
~~~

**Important:** `credentials: "include"` tells `fetch` to send/accept cookies per browser policy, yet never overrides `SameSite`, `Secure`, or third-party cookie restrictions. The server must return `Access-Control-Allow-Credentials: true` and `Access-Control-Allow-Origin` equal to the exact frontend origin (never `*`).

Before login, `GET /session/csrf` may issue a token for an anonymous session **without granting Authentication**. If login rotates the session/token, fetch a new CSRF token after login. In real form-login/redirect flows, cross-origin AJAX login requires careful handling of redirects, cookies, and CSRF; a same-origin BFF/login flow is usually much easier to operate.

**If the frontend cannot read a CSRF cookie due to differing hosts**, returning the token via JSON as shown above is simpler than double-submit with a raw cookie. If you choose `CookieServerCsrfTokenRepository.withHttpOnlyFalse()` so JavaScript reads `XSRF-TOKEN`, Spring Security 6 defaults to the XOR request handler, so verify how tokens are resolved when sending the raw cookie token via `X-XSRF-TOKEN`—do not assume Servlet SPA handler examples work identically in WebFlux. Disable `HttpOnly` on the CSRF cookie only when JavaScript genuinely must read it, and never disable `HttpOnly` on the session cookie.

## 12. Browser: Calling the Bearer API Properly

The frontend obtains an access token through a proper OAuth2/OIDC flow (Authorization Code + PKCE for public clients, or a BFF managing tokens server-side). Attach the token directly in the `Authorization` header:

~~~javascript
const API = "http://localhost:8080";

// accessToken obtained via a valid OAuth2 flow.
const result = await fetch(API + "/token/notes", {
  method: "POST",
  credentials: "omit",
  headers: {
    "Authorization": "Bearer " + accessToken,
    "Content-Type": "application/json"
  },
  body: JSON.stringify({value: "hello-bearer"})
});

if (!result.ok) {
  throw new Error("Bearer request rejected");
}

console.log(await result.json());
~~~

JSON output when the token is valid and holds scope `notes.write`:

~~~json
{"accepted":"hello-bearer"}
~~~

The browser triggers a preflight because of `Authorization` and JSON `Content-Type`. The CORS config must allow `Authorization` and `Content-Type`, yet **preflight carries no Bearer token**. Only the actual request carries the token, which the Resource Server verifies. Never put `Authorization` in URL query strings or logs, and never send refresh tokens to APIs that do not need them.

**Why `credentials: "omit"`?** In this example the `bearer` chain accepts tokens only from the header and does not need browser cookies. That reduces reliance on auto-sent credentials. Do not take it as a claim that Bearer tokens are immune to XSS: malicious script running on the frontend origin can still use or exfiltrate tokens stored in JS-accessible storage. CSP, output escaping, token lifetimes, and storage design remain essential.

## 13. Testing Session Mode: CORS Preflight + CSRF + Cookies

File `src/test/java/example/cors/SessionCorsTest.java`:

~~~java
package example.cors;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest
@ActiveProfiles("session")
@AutoConfigureWebTestClient
class SessionCorsTest {

    private static final String FRONTEND = "http://localhost:5173";

    @Autowired
    WebTestClient client;

    @Test
    void anonymousPreflightIsAcceptedBeforeAuthentication() {
        client.options()
            .uri("/session/notes")
            .header(HttpHeaders.ORIGIN, FRONTEND)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "content-type,x-csrf-token")
            .exchange()
            .expectStatus().is2xxSuccessful()
            .expectHeader()
            .valueEquals(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND)
            .expectHeader()
            .valueEquals(HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true");
    }

    @Test
    void untrustedOriginIsNotAllowed() {
        client.options()
            .uri("/session/notes")
            .header(HttpHeaders.ORIGIN, "https://evil.invalid")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .exchange()
            .expectHeader()
            .doesNotExist(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void csrfBlocksAuthenticatedPostWithoutToken() {
        client.mutateWith(mockUser("student"))
            .post()
            .uri("/session/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "test"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void csrfAllowsAuthenticatedPostWithValidToken() {
        client.mutateWith(mockUser("student"))
            .mutateWith(csrf())
            .post()
            .uri("/session/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "test"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.accepted").isEqualTo("test");
    }

    @Test
    void formLoginCreatesReusableSessionCookie() {
        EntityExchangeResult<byte[]> login = client.mutateWith(csrf())
            .post()
            .uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "username", "student").with("password", "demo-pass"))
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectBody()
            .returnResult();

        ResponseCookie session =
            login.getResponseCookies().getFirst("SESSION");
        assertNotNull(session);

        client.get()
            .uri("/session/me")
            .cookie("SESSION", session.getValue())
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.user").isEqualTo("student");
    }
}
~~~

**Meaning and limits:**

- `OPTIONS` preflight **without cookies** still receives CORS success; this verifies CORS runs ahead of security.
- Unknown origins receive no `Access-Control-Allow-Origin` for that origin. In Spring's default filter, invalid CORS requests typically return 403; the test does not depend on error body content.
- `mockUser()` only simulates Authentication to isolate CSRF testing; it does not prove real login.
- `csrf()` supplies a valid test CSRF token; it does not replace a production browser fetching a token from the server.
- The separate login test verifies the server issues `SESSION` and a subsequent GET uses that cookie. The cookie name matches the lab's default WebFlux session resolver; if you customize the resolver, update the test.
- When testing for production, also verify cookie `Secure`, `HttpOnly`, `SameSite`, HTTPS, expiry, and server-side logout invalidation.

## 14. Testing Bearer Mode: Preflight and Scope Independent of CSRF

File `src/test/java/example/cors/BearerCorsTest.java`:

~~~java
package example.cors;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@ActiveProfiles("bearer")
@AutoConfigureWebTestClient
class BearerCorsTest {

    private static final String FRONTEND = "http://localhost:5173";

    @Autowired
    WebTestClient client;

    @MockBean
    ReactiveJwtDecoder decoder;

    @Test
    void preflightWithAuthorizationHeaderNeedsNoBearerToken() {
        client.options()
            .uri("/token/notes")
            .header(HttpHeaders.ORIGIN, FRONTEND)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "authorization,content-type")
            .exchange()
            .expectStatus().is2xxSuccessful()
            .expectHeader()
            .valueEquals(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND)
            .expectHeader()
            .doesNotExist(HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS);
    }

    @Test
    void missingBearerCannotReadPrivateEndpoint() {
        client.get().uri("/token/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void mockJwtWithWriteScopeMayPostWithoutCsrfToken() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_notes.write")))
            .post()
            .uri("/token/notes")
            .header(HttpHeaders.ORIGIN, FRONTEND)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "test-token"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.accepted").isEqualTo("test-token");
    }

    @Test
    void authenticatedJwtWithoutWriteScopeIsForbidden() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_notes.read")))
            .post()
            .uri("/token/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("value", "denied"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void untrustedOriginDoesNotGetCorsPermission() {
        client.options()
            .uri("/token/notes")
            .header(HttpHeaders.ORIGIN, "https://evil.invalid")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .exchange()
            .expectHeader()
            .doesNotExist(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }
}
~~~

**Key point to understand:** `mockJwt()` creates an Authentication for `WebTestClient`; it **skips fetching JWKS and verifying the signature/issuer of a real JWT**. It is suitable for checking route/scope/CORS/CSRF behavior, yet must be supplemented with integration tests against a real issuer/decoder or dedicated token-validator tests to prove cryptographic authentication and audience validation.

In the `bearer` profile, `@MockBean ReactiveJwtDecoder` supplies a mock decoder for the Spring test context; **never ship this bean to production**. In test scope, the `Authorization` header does not need a real signed JWT because Security Test injects the authentication context.

## 15. Running Tests and Starting Each Profile Separately

In the Maven project directory:

~~~bash
mvn clean test
~~~

Both `SessionCorsTest` and `BearerCorsTest` suites are expected to pass. Assertions focus on **origin/credential pairs**, scope permissions, CSRF, and session persistence. Tests do not prove real browser CORS enforcement; verify with Chrome DevTools/Network against a real frontend when deploying.

Run `session` mode:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=session
~~~

Open `http://localhost:8080/login` and sign in with demo account `student`/`demo-pass`. Afterward, call `/session/me` in the browser to see the principal. Use the frontend at `localhost:5173` to run the fetch code in section 11.

Stop the process before switching modes. Run `bearer` mode **after supplying a valid issuer**:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=bearer
~~~

The Resource Server uses the issuer/JWKS from the environment. Without a real IdP/token, run only the `mockJwt()` tests; never use `example.com` as a real issuer or craft unsigned tokens to "bypass" authentication.

### 15.1. Checking Preflight with curl

The commands below send headers equivalent to a preflight; `curl` **does not enforce browser CORS policies**, serving only to inspect responses:

~~~bash
curl -i -X OPTIONS "http://localhost:8080/session/notes" \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

When running in `session` mode, the preflight response must include `Access-Control-Allow-Origin: http://localhost:5173` and `Access-Control-Allow-Credentials: true`. No cookie is needed for `OPTIONS`.

Switch to `bearer` mode and try:

~~~bash
curl -i -X OPTIONS "http://localhost:8080/token/notes" \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type"
~~~

The Bearer preflight has no `Authorization` token yet must still be accepted by the CORS handler. An actual `POST /token/notes` without a Bearer token must be rejected by the resource server even though preflight succeeded.

### 15.2. Observing Browser Errors

In Chrome/Firefox DevTools → Network, inspect **both requests**: the `OPTIONS` preflight and the actual request. Note `Origin`/`Access-Control-Request-Headers`, CORS response headers, cookie policies, `X-CSRF-TOKEN`, HTTP status, and console errors. Never expose secret tokens or cookies in public reports or screen recordings.

## 16. Expected Behavior Matrix

| Scenario | Session + CSRF | Bearer header-only |
| --- | --- | --- |
| Preflight from allowlisted origin, no auth | **CORS success** | **CORS success** |
| Preflight from unknown origin | No CORS permission granted | No CORS permission granted |
| Actual GET without cookie/token | Prompted to log in (typically redirect) | **401** |
| Actual GET with valid session cookie | Authenticated | Cookie not used for authentication |
| Actual GET with valid Bearer token | No Resource Server in `session` profile | Authenticated via JWT |
| POST with session cookie, missing CSRF | **403** if authenticated and route allowed | Does not accept session for auth |
| POST with valid cookie + CSRF | Processed if authorized | Not applicable |
| POST with valid Bearer, write scope, no CSRF | Bearer auth not used in `session` profile | Processed |
| POST with valid Bearer lacking write scope | Bearer auth not used | **403** |
| JWT placed in a cookie | Requires CSRF due to auto-sent credential | **Outside guarantees of Bearer-only chain** |
| `Access-Control-Allow-Origin: *` with credentials | Misconfiguration | Valid only on non-credentialed public APIs if evaluated |
| Disallowed origin yet valid token via curl | curl not blocked by browser CORS | Authentication/authorization still govern |

**Note on 401/403/302:** form login typically redirects anonymous requests, whereas Bearer APIs typically return 401. A 403 can also stem from CSRF or insufficient permissions depending on the request. Distinguish HTTP entry point, authentication, CSRF, and authorization before editing rules.

## 17. Cookie Flags, SameSite, and Deployment Environments

For session-based browser apps:

- **`Secure`:** sends cookies only over HTTPS (except browser-permitted localhost/test exceptions). Production deployments must enforce HTTPS and proper forwarded headers/trusted proxies.
- **`HttpOnly`:** blocks JavaScript from reading the session cookie directly, reducing ID leakage via XSS; does not prevent XSS from issuing requests on the user's behalf.
- **`SameSite=Lax`/`Strict`:** mitigates certain cross-site auto-send scenarios; does not replace CSRF tokens for all risks.
- **`SameSite=None; Secure`:** used when architecture genuinely requires cross-site cookies, yet browsers may block them as third-party cookies. Test under real browsers/ITP and consider a BFF.
- **Domain/Path:** scope cookies tightly, avoiding overly broad parent domains that accidentally share sessions with untrusted subdomains.
- **Session timeout and logout:** must invalidate the server-side `WebSession`; deleting only the client cookie does not revoke stolen ID copies.
- **CSRF token lifecycle:** tokens may need refreshing after login/logout or session rotation; never store CSRF responses in shared proxies or public caches.

WebFlux's `WebSession` cookie config differs from `CookieCsrfTokenRepository`; do not confuse the two cookies. Using `CookieServerCsrfTokenRepository.withHttpOnlyFalse()` lets JS read the **CSRF cookie**—it does **not** mean disabling `HttpOnly` on the `SESSION` cookie.

## 18. XSS, CORS, and OAuth2: Trust Boundaries

CORS does not protect against XSS executing inside an allowed frontend origin; malicious scripts on that frontend can call the API just like legitimate code and read responses. Therefore XSS defenses, Content Security Policy, dependency hygiene, output escaping, code reviews, and avoiding long-lived access tokens in JS-readable storage all remain vital.

With Bearer tokens, an allowlisted frontend origin **does not prove** the token came from that frontend. The Resource Server must verify the token, matching audience, issuer, and scopes. An access token could be replayed to the wrong-audience API if the API omits `aud` checks; CORS neither detects nor fixes that.

When using a **BFF**, OAuth2 tokens can stay server-side while the browser holds only a session cookie to the BFF. Even if the BFF calls downstream services with Bearer tokens, the browser–BFF boundary is **cookie/session + CSRF**. Never "disable CSRF because the BFF calls downstream with Bearer"; evaluate credentials at the **exact HTTP boundary**.

### Differences Between Fetch Credential Modes

- `credentials: "include"`: browser considers sending cookies cross-origin and exposes credentialed CORS responses to JS only if the server agrees; never overrides cookie restrictions.
- `credentials: "omit"`: does not rely on browser auto-sent cookies; an `Authorization` header **explicitly set** by JavaScript remains a request header requiring CORS permission.
- `mode: "no-cors"` is not a CORS bypass: responses become opaque, custom headers/methods are restricted, Authentication/CSRF are unsolved, and scripts cannot read JSON API responses.

## 19. Common Mistakes

1. **Allowing `*` with `allowCredentials=true`:** browsers reject credentialed responses; use an explicit origin allowlist.
2. **Reflecting all Origins via wildcard `allowedOriginPatterns`:** lets malicious websites read logged-in users' responses.
3. **Blocking `OPTIONS` with a login filter:** preflight carries no credentials; run CORS before auth.
4. **Setting `OPTIONS permitAll` without a `CorsConfigurationSource`:** browser still misses CORS response headers.
5. **Disabling CSRF app-wide because JWT is present:** session/cookie endpoints become vulnerable to CSRF.
6. **Thinking a JWT in a cookie needs no CSRF:** browsers auto-attach cookies regardless of whether a JWT is inside.
7. **Calling POST with cookies without `X-CSRF-TOKEN`:** Spring Security returns 403 when CSRF is enabled.
8. **Using `Access-Control-Expose-Headers` instead of `Allow-Headers`:** does not permit the `Authorization` request header.
9. **Forgetting exact Origin scheme/port:** `localhost:3000` differs from `localhost:5173`; HTTP differs from HTTPS.
10. **Assuming curl proves CORS protects the API:** curl has no browser SOP; CORS is not authentication.
11. **Failing to distinguish 401/403/302:** may stem from login redirects, CSRF, or scopes, not only CORS.
12. **Letting both a reverse proxy and Spring emit conflicting CORS headers:** browsers see multiple `Access-Control-Allow-Origin` values and reject.
13. **Omitting `Vary` when responses depend on Origin:** shared caches can serve the wrong CORS response.
14. **Letting unknown Origins hit CSRF endpoints with credentials:** unnecessary response exposure.
15. **Putting Bearer tokens in query strings/URLs or logs:** exposure via browser history, proxy logs, and `Referer`.
16. **Omitting the audience validator for JWTs:** a token valid for service A may be misused against service B.
17. **Ignoring third-party cookie blocking:** CORS passes yet the browser drops the `SESSION` cookie.
18. **Reusing CSRF tokens across logout/rotation:** stale tokens are rejected; refresh after authentication state changes.
19. **Confusing CORS with data authorization:** logged-in users still need owner/tenant checks.
20. **Merging session and Bearer into one chain with CSRF disabled:** cookie-authenticated requests can hit unprotected endpoints.

## 20. Ordered Troubleshooting Guide

When the frontend reports a "CORS error", follow this sequence:

1. Verify the exact frontend and API URLs: **scheme, host, port**.
2. DevTools → Network → is there an **`OPTIONS`** request? Which `Origin`/`Access-Control-Request-*` headers did it send? Any cookies/tokens? (Standard preflight carries no actual-request credentials.)
3. Does the preflight response carry the right `Access-Control-Allow-Origin`, allowed methods, allowed headers, and status?
4. For session credentialed fetches, is `Access-Control-Allow-Credentials: true` present? Did the browser actually send the cookie, or was it blocked by `SameSite`, `Secure`, or third-party rules?
5. If the actual request was sent, what status did the server return? 302 login redirect, 401 missing JWT, 403 CSRF/role, 404 route, 5xx app error? Inspect server logs safely (never log cookies or tokens).
6. If a session POST failed, was the CSRF token fetched for the **current session**? Was it sent using the exact header name and token returned?
7. If a Bearer POST failed, was the `Authorization` header present on the actual request? Was the token signed and validated for the right issuer/audience/scope?
8. Check whether proxies/WAFs rewrite `Origin`, `Location`, `Set-Cookie`, `Vary`, or CORS headers; test in real production browsers, not just curl.
9. Once you identify the failing layer, make the minimal fix at that layer; never disable security/CSRF or open all origins as a workaround.

**Important:** Browsers can display "CORS error" when the real response is 401/403/500 missing CORS headers. Fix the underlying authentication/CSRF/authorization cause and ensure error responses pass through proper CORS integration rather than adding ACAO only to success responses.

## 21. Applied Exercises

**Exercise A — Unauthenticated preflight:** test `OPTIONS /session/notes` without cookies and `OPTIONS /token/notes` without Bearer. Both must return CORS success for trusted origins; verify unknown origins are denied.

**Exercise B — CSRF under session:** use `mockUser()` to POST JSON without a token (expect 403); add `csrf()` (expect 200). Explain why a GET body or preflight does not replace a CSRF token.

**Exercise C — Bearer scope:** use `mockJwt()` with `SCOPE_notes.read` to call POST (expect 403); switch to `SCOPE_notes.write` (expect 200). Note that this mock does not verify signatures or audiences.

**Exercise D — JWT in a cookie:** modify the hypothetical system so the browser sends tokens automatically via a cookie; analyze why CSRF must be enabled instead of copying `csrf.disable()` from the `bearer` profile.

**Exercise E — `allowCredentials` wildcard:** test changing the session origin to `*` with `allowCredentials(true)`; observe the configuration/browser error and restore the allowlist. Explain why `allowedOriginPatterns("*")` is unsafe.

**Exercise F — Cross-site frontend:** change the hypothetical frontend to `https://app.example.net` and API to `https://api.example.com`. Tabulate cookie `SameSite`/`Secure`/`Domain`/`Path`, CORS allowlist, CSRF token lifecycle, and third-party browser policies. Propose a same-origin BFF if cookies prove brittle.

**Exercise G — Reverse proxy:** suppose a CDN injects ACAO while Spring does too. Write tests/inspections to catch duplicate headers, missing `Vary`, altered `Set-Cookie` attributes, and divergent preflight caches across origins.

**Exercise H — Object authorization:** replace the echo API with a POST updating a real record; add a test where a user has valid cookies/tokens yet lacks tenant/owner rights. Prove CORS + CSRF + authentication still do not grant data access.

### Completion Criteria

- [ ] Distinguish origin, site, cookie policies, and CORS.
- [ ] Explain why CORS does not replace authentication, authorization, or CSRF.
- [ ] Uncredentialed preflight without cookies/Bearer is handled before security.
- [ ] Session credentialed CORS uses an explicit origin allowlist and `allowCredentials(true)`.
- [ ] Session POST requires a CSRF token; tested 403 without token and 200 with token.
- [ ] Bearer header is allowed in CORS and JWT is validated on every request.
- [ ] CSRF is disabled only on header-only APIs accepting no auto-sent credentials after threat modeling.
- [ ] JWTs in cookies are still evaluated for CSRF like any other cookie credential.
- [ ] Understand that `mockJwt()` does not prove cryptographic JWT validation.
- [ ] Understand cookie `Secure`/`HttpOnly`/`SameSite`, browser privacy rules, and BFF alternatives.
- [ ] Verified origins/headers/statuses/redirects/caching without leaking tokens in logs.
- [ ] Negative tests exist for forbidden origins, missing scopes, missing CSRF, and anonymous requests.

## 22. Self-Check Questions

1. Are `localhost:5173` and `localhost:8080` same-origin? Are they necessarily cross-site?
2. If CORS blocks an unknown origin from reading the response, can a simple POST still cause side effects?
3. Why must `OPTIONS` preflight not require a session cookie or Bearer token?
4. When using session cookies, why is `Access-Control-Allow-Origin: *` incompatible with credentials?
5. Which header lets the frontend send `Authorization`? Which header lets JS read extra response headers?
6. Does `credentials: include` bypass `SameSite` and browser third-party cookie policies?
7. After form login completes, why might an SPA need to fetch a fresh CSRF token?
8. If a JWT is stored in an `HttpOnly` cookie, can CSRF be omitted just because the JWT is signed?
9. What does `mockJwt()` test, and what does it **not** test?
10. Why must a Resource Server verify issuer, expiry, audience, and scopes in addition to the CORS allowlist?
11. If the browser reports a CORS error, why must you also check 401/403/302 statuses in Network/server?
12. Why doesn't CORS protect an API from `curl` or from scripts running on a trusted origin compromised by XSS?

## 23. References

- [Spring Security — CORS for WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html): CORS before security, `CorsWebFilter`, and `CorsConfigurationSource`.
- [Spring Security — CSRF for WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html): `WebSessionServerCsrfTokenRepository`, `CookieServerCsrfTokenRepository`, and XOR handler.
- [Spring Security — Testing CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html): `WebTestClient` `csrf()`.
- [Spring Security — Testing OAuth2](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html): `mockJwt()` and authority testing.
- [Spring Security — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html): signature, issuer, exp/nbf, scope, and audience validation.
- [Spring Framework — CORS in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): origin, headers, preflight, and response behavior.
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): preflight and credentialed requests.
- [MDN — Fetch Request.credentials](https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials): `include`, `omit`, `same-origin`.
- [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): synchronizer token, double-submit, `SameSite`, Origin validation.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookie flags, session fixation, logout.

**Conclusion:** CORS decides **under which policy a browser may interact cross-origin and read responses**; session cookies and Bearer headers decide **how authentication credentials are sent**; CSRF decides **whether requests carrying browser-attached credentials are allowed to cause side effects**. In Spring Security Reactive, process CORS before authentication, allowlist explicit origins and headers, keep CSRF enabled for cookie sessions, and disable CSRF only in cleanly isolated header-only Bearer chains. Finally, still enforce token, scope, and object permissions—CORS is not authorization.