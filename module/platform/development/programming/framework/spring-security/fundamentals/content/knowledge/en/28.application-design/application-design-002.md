# Session-Based Web Apps, Token-Based APIs, and Hybrid Architectures

> **Scope:** Spring Security on **Servlet/Spring MVC**, Java 17+, Spring Boot 3.x / Spring Security 6.x. Part of **Application Design**. The goal is to properly understand and choose between **web session + cookie**, **API Bearer access token**, and **hybrid architecture** (multiple `SecurityFilterChain` beans or Backend for Frontend), covering authentication lifecycle, CSRF, CORS, JWT, authorization, and testing.

## 1. The design problem

Suppose a product has:

- An **employee interface** opened in a browser, accessing `/web/**`, needing form login or OIDC redirect and staying signed in across multiple requests.
- **APIs for mobile/partners**, accessing `/api/**`, sending `Authorization: Bearer ...` on every request.
- **A hybrid application** hosting both web UI and APIs, or a **BFF** mediating between browsers and resource servers.

Although all three require authentication and authorization, **you should not use the same credential transport mechanism for every path**. For example:

- If a token-only API is configured with `formLogin`, an unauthenticated request may receive a **302 HTML login redirect** instead of a **401 Bearer challenge**.
- If `SessionCreationPolicy.STATELESS` is applied to web form login as well, the app may fail to retain login state across two requests.
- If CSRF is disabled across the entire system because "the API uses tokens," web actions where the browser automatically sends cookies may lack protection.
- If the API implicitly accepts session cookies despite being designed as token-only, a browser session could cross an authentication boundary the team never intended.
- If API Bearer access tokens are automatically accepted by the web chain, this can create an unintended entry path or complicate logout and session security boundaries.
- If `securityMatcher` and paths like `/login`, `/logout`, or OAuth2 callbacks are misconfigured, login/redirects may fail to run or fall into redirect loops.

### Learning objectives

1. Trace the path of credentials and `SecurityContext` in session-based web apps and Bearer APIs.
2. Choose stateful, stateless, or BFF based on client type and threat model; explain trade-offs around scale, logout, XSS/CSRF, and token storage.
3. Configure **multiple `SecurityFilterChain`** beans with distinct `securityMatcher`, `@Order`, entry points, session policies, and CSRF policies.
4. Protect JWTs via signature, algorithm, issuer, audience, expiry, and scopes; never use an ID token to call a resource server.
5. Write tests proving: a web session does **not** automatically grant access to a Bearer API; a Bearer token does **not** automatically create a web session.
6. Know when live HTTP/browser tests are needed beyond MockMvc.

## 2. Core terminology

### 2.1. A session cookie is not an access token

For a traditional web application:

```text
Browser                            Spring Security + Servlet container
   |                               |
   | POST /login + form + CSRF     |
   |------------------------------>|
   |  authentication succeeds      |
   |  save SecurityContext/session |
   |<---- 302 + Set-Cookie --------|
   |                               |
   | GET /web/home                 |
   | Cookie: JSESSIONID=...        |
   |------------------------------>|
   |  read session -> Authentication|
   |<---- 200 (data/HTML) ---------|
```

The session identifier typically resides in the `JSESSIONID` cookie. The cookie does not necessarily contain the user's name or permissions; the server uses the session ID to look up session state. `SecurityContextHolder` holds the request's authentication, typically via a thread-local; `SecurityContextRepository` determines how the context is restored/persisted across requests.

**Note:** Spring Security 6 uses explicit `SecurityContext` saving in custom authentication flows. A custom controller that only calls `SecurityContextHolder.getContext().setAuthentication(...)` is not enough to guarantee subsequent requests stay logged in; an appropriate authentication flow and repository must be used. Using standard `formLogin` or `oauth2Login` avoids re-implementing session management steps manually.

### 2.2. A Bearer token differs from a session identifier

The API receives:

```http
GET /api/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...
Accept: application/json
```

The resource server validates the access token and builds an `Authentication` for that request. For JWTs, validation covers appropriate checks such as trusted signature/algorithm, issuer `iss`, audience `aud`, `exp`/`nbf` timestamps, scopes, and business policies.

- **JWT:** typically self-contained with claims; **the payload is not encrypted by default**, even when signed. Do not place secrets or unnecessary PII in claims.
- **Opaque token:** the resource server typically validates it via token introspection; trade-offs include network calls, caching, and revocation responsiveness.
- **Access token:** a credential intended for a resource server; not interchangeable with an OIDC **ID token**. An ID token may be valid for the client yet lack the API's audience.
- **Refresh token:** used with the authorization server/client in its proper role; should not be sent to a resource server as an access token.
- **Scopes:** claims/token authorities representing capabilities such as `reports.read`; they do not replace per-tenant/owner/record permissions.

`SessionCreationPolicy.STATELESS` directs the API not to create or use `HttpSession` as the storage for security context. It does not mean the system has zero state in databases, caches, quotas, revocation lists, or key rotation.

### 2.3. Authentication does not replace authorization

An API Bearer token with a valid signature that lacks `SCOPE_reports.read` must be rejected. A logged-in web session may still lack `ROLE_ADMIN`. Even with a READ scope, a user is not automatically allowed to read another tenant's documents; object-level authorization must be enforced at the service/query layer.

```text
Authentication: who is the caller?
  Web: SecurityContext loaded from session.
  API: verified JWT/opaque token.

Authorization: what is the caller allowed to do?
  Request: hasAuthority, hasRole, URL/method.
  Service: tenant, owner, data, state, business rules.
```

## 3. Decision comparison table

| Criterion | Web session/cookie | Bearer API | Hybrid |
| --- | --- | --- | --- |
| Typical clients | Server-rendered browser, admin portal | Mobile, machine-to-machine, API consumer | Web + mobile/partner; SPA + BFF |
| Credential on request | Cookie holding session ID, auto-sent by browser per policy | `Authorization: Bearer` attached explicitly by client | Per boundary, never implicitly mixed |
| Authentication state | Typically stored server-side | Typically validated on every request | Stateful web, stateless API |
| Unauthenticated | Typically 302 to login | Typically 401 + `WWW-Authenticate: Bearer` | Response matches client/chain type |
| CSRF | Typically required for cookie-backed actions | May not be needed if using only Bearer header and no auto-sent credentials | Enabled for web/BFF cookies; evaluate API separately |
| XSS | Can issue requests within session; HttpOnly limits cookie reads | Tokens in JS-accessible storage can be stolen via XSS | BFF avoids exposing tokens to JS but does not eliminate XSS |
| Logout | Destroys session and context | JWT may remain valid until expiry without revocation | Web, token, and SSO logout are separate operations |
| Scaling | Shared session store/sticky routing across instances | Offline JWT validation can reduce lookups | Operating multiple policies or multiple services |
| What to protect | Cookie flags, session fixation, timeout, CSRF | Signature, issuer, audience, scope, expiry, token storage | Matchers, trust boundaries, CSRF/CORS, forwarding |
| Key tests | Session persistence, cookies, CSRF | Bearer validation and scopes | **Cross-credential isolation** |

There is no single right architecture. Choose based on whether the browser auto-sends credentials, client trust level, login flows, API scope, immediate logout needs, and operations.

## 4. Design A — web session

### 4.1. Login flow

A Spring MVC website using `formLogin` or `oauth2Login` sends unauthenticated users to a login page or identity provider. After authentication, Spring Security performs appropriate session handling: session fixation protection, `SecurityContext` persistence, and handler-driven redirects.

```text
GET /web/home (anonymous)
   -> 302 /login
GET /login
   -> 200 login form + CSRF field
POST /login (credentials + CSRF)
   -> authentication filter -> success handler
   -> session created/ID rotated per policy
   -> 302 /web/home
GET /web/home + Cookie
   -> server loads Authentication from session
   -> 200
```

This is a typical flow; not every app uses the exact `/login` path or 302 status. With OIDC, requests pass through the authorization server and callback; protecting `state`/`nonce`, redirect URIs, and cookies during cross-site redirects is also critical.

### 4.2. Cookie configuration

- `Secure`: sends the cookie only over HTTPS; requires proper proxy/TLS termination.
- `HttpOnly`: JavaScript cannot read the cookie directly; **does not prevent XSS from triggering actions** with auto-attached cookies.
- `SameSite`: affects CSRF and SSO redirects; `Lax`, `Strict`, and `None` must match real browser behavior, and `None` typically requires `Secure`.
- `Path`/`Domain`: limits scope; if misconfigured, the cookie is not sent on post-login requests, causing redirect loops.
- Timeout, session concurrency, invalid-session handling, and the session store must align with policy.
- Never log raw session IDs or put session IDs in query strings.

When scaling across multiple instances, you need session affinity or a shared session store (such as Spring Session + Redis) if sessions must be readable on any node. Account for session data across rolling deployments, idle/absolute timeouts, and session revocation when an account is disabled.

### 4.3. CSRF for web is a critical boundary

Browsers typically **automatically attach** session cookies to matching requests per cookie policy. A malicious site can trick the browser into sending a POST; if the backend relies solely on cookies, the request may be treated as a user action. Therefore, state-changing operations over cookies generally require CSRF protection.

With forms, `CsrfToken` is placed in an appropriate hidden input/header. With a session-backed SPA, the token can be sent in a custom header. Spring Security 6 provides deferred CSRF tokens and BREACH protection, and old tokens are typically cleared on login/logout. Clients may need to **fetch a fresh token after those two events**.

Do not disable CSRF application-wide just because another namespace hosts a Bearer API.

## 5. Design B — OAuth2 Resource Server for APIs

An ideal resource server does not mint tokens itself from a business username/password endpoint. It trusts an authorization server/IdP to issue access tokens, while the resource server solely **validates tokens and makes access decisions**.

```text
OAuth2/OIDC authorization server
      |
      | access token with issuer, audience, scope, exp
      v
Mobile / partner / permitted SPA client
      |
      | Authorization: Bearer ...
      v
Spring Security Resource Server
      |
      +-- BearerTokenAuthenticationFilter
      +-- JwtDecoder or opaque introspection
      +-- authorities / method authorization
      v
Controller -> service -> tenant-scoped repository
```

### 5.1. Common production configuration

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/product
          audiences:
            - https://api.example.org
```

This is a **template**: replace issuer/audience with values provided by your IdP. With `issuer-uri`, Resource Server can fetch metadata/JWKS published by the issuer to select public keys and verify JWTs. Verify trust configuration, key rotation, network availability, algorithms, and JWKS endpoint security in production.

**Issuer and audience are distinct:** a valid token issued by issuer A might be intended for resource server B; if your API does not check the audience, it could mistakenly accept a valid token meant for a different API. After validation, verify `scope`, tenant/owner, and custom rules.

### 5.2. JWT is not a drop-in replacement for every session

- A stolen token can be used until it expires unless a rejection/revocation mechanism exists.
- Claims may become stale if a user loses permissions after the token was issued.
- Signing key rotation and clock skew must be handled.
- A JWT signature does not encrypt the payload; do not store passwords, secrets, or unnecessary sensitive data in claims.
- `SCOPE_reports.read` does not automatically grant `SCOPE_reports.write` or access to records outside the tenant.
- Never leave access tokens in URLs, HTML logs, analytics, or arbitrary `localStorage`; assess XSS and credential storage in your threat model.

### 5.3. When can an API omit CSRF?

If **the API only accepts Bearer tokens in the Authorization header**, does not authenticate via cookies or any other browser auto-sent credential, and clients explicitly attach the token, cookie-session CSRF risks may not apply. In that case, CSRF can be disabled **within that specific API `SecurityFilterChain`**.

If later the API allows session cookies, cookie-based bearer tokens, browser-cached HTTP Basic credentials, or automatic refresh tokens via cookies, that initial assumption no longer holds. **Stateless does not automatically make CSRF harmless**; the real question is whether the browser auto-sends credentials on cross-site requests.

## 6. Design C — hybrid architectures

### C1. One Spring Boot app, two SecurityFilterChain beans

```text
                       +--> /web/** + /login + /logout
Browser + cookie ------|      SecurityFilterChain WEB
                       |      formLogin, session IF_REQUIRED, CSRF ON
                       |
Spring Boot Servlet ---+
                       |
Mobile/partner --------|----> /api/**
Bearer token           |      SecurityFilterChain API
                       |      oauth2ResourceServer(jwt), STATELESS
                       |      CSRF OFF only when Bearer-header only
                       |
                       +--> fallback denyAll()
```

A `FilterChainProxy` holds multiple `SecurityFilterChain` beans. A request passes through **the first chain whose `securityMatcher` matches**. Bean `@Order` and matcher scope are part of the security design.

| Endpoint | Chain | When unauthenticated | CSRF |
| --- | --- | --- | --- |
| `GET /web/home` | Web | 302 to `/login` | Filter present; GET normally needs no token |
| `GET /login` | Web | 200 form | Supplies token for POST |
| `POST /login` | Web | Processes form login | **Yes** |
| `POST /logout` | Web | Cleanup and redirect | **Yes** |
| `GET /api/reports` | API | 401 Bearer challenge | Not applicable for GET |
| `POST /api/reports` | API | 401 if JWT missing, 403 if scope missing | Conditionally disabled on token-only API |
| Unmatched paths | Fallback | Deny | Per fallback |

**Important:** `securityMatcher(...)` decides **which filter chain applies**, whereas `requestMatchers(...)` inside `authorizeHttpRequests` decides **rules inside that chain**. If you configure the web chain matcher for `/web/**` only while the login filter processes `POST /login`, the login POST may **never reach that filter**.

### C2. Backend for Frontend (BFF)

```text
Browser (HttpOnly cookie only)
       |
       | session + CSRF
       v
BFF (stateful; tokens kept server-side)
       |
       | Authorization: Bearer access token
       v
OAuth2 Resource Server -> business API -> DB
```

A BFF is useful when you want to keep access tokens out of browser JavaScript and centralize refresh, token relay, and session policy. The BFF **still must** protect against CSRF and XSS, and manage its token store securely. The resource server must still independently verify JWTs and permissions; never blindly trust requests just because they come from the BFF.

A BFF adds operational overhead (session store, scaling, availability, auth callbacks, logout, and token lifecycle). For a small traditional MVC website, a web session may be simpler; for a complex SPA, a BFF is worth considering.

### C3. Separate deployables

You can split the web/BFF and API resource server into two separate applications or keep them in one app with two chains. Splitting services creates a clear deployment boundary, but **does not automatically guarantee** correct token audiences/scopes, proper data-level authorization, or cookie protection.

## 7. Principles you should not break

1. **Every route has one clear credential policy.** Never let a token-only API implicitly accept web sessions.
2. **Every chain has clear matchers and order.** A broad `/**` chain ordered first can hijack requests meant for specific chains.
3. **Web sessions and Bearer APIs have different entry points:** 302 login vs. 401 Bearer; missing permissions typically return 403.
4. **Enable CSRF for cookie-authenticated areas,** exempting only areas that fit the threat model.
5. **CORS does not replace CSRF or authorization.** Browser preflight requests carry no session, and CORS must run before security when cross-origin is needed.
6. **JWTs must be verified**, not merely parsed; check issuer/audience/time/algorithm/scopes.
7. **An ID token is not an access token** for resource servers.
8. **Never use a demo shared HS256 key in production** without an approved signing/issuing architecture; prefer IdP/JWKS/asymmetric signing when appropriate.
9. **Never hard-code real passwords or tokens.** Never log raw `Authorization` headers or `JSESSIONID`.
10. **Data requires its own authorization:** tenant, owner, record, action; scopes/roles are only part of the decision.
11. **Web logout does not revoke every JWT**; you need TTL, revocation, and refresh token policies.
12. **Test credential boundaries in both directions** and use live HTTP when verifying browsers/proxies/cookies.

## 8. Java 17 demo: web session + API JWT in one application

To make the demo **run self-contained tests without depending on an external IdP**, the API uses an HS256 JWT signed with a secret from an environment variable; tests use a fixed test key. This is **strictly for local/lab use**, not guidance to freely mint access tokens in production systems. In production, use a standard `issuer-uri`/JWKS/Authorization Server and remove shared-secret decoders if your architecture forbids them.

### 8.1. File structure

```text
hybrid-security-demo/
  settings.gradle
  build.gradle
  src/main/java/com/example/hybrid/
    HybridApplication.java
    SecurityConfig.java
    DemoController.java
  src/test/java/com/example/hybrid/
    HybridSecurityTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'hybrid-security-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Pinning plugin versions helps study a consistent Boot 3.3/Security 6 API; **it is not a recommendation for the latest production version**. Use a patched release maintained by your organization. This code requires JDK 17+ and a compatible Gradle/wrapper.

### 8.2. `HybridApplication.java`

```java
package com.example.hybrid;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HybridApplication {

    public static void main(String[] args) {
        SpringApplication.run(HybridApplication.class, args);
    }
}
```

### 8.3. `SecurityConfig.java` — three chains and decoder

```java
package com.example.hybrid;

import java.util.Base64;

import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

import jakarta.servlet.DispatcherType;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    public static final String DEMO_ISSUER =
        "https://issuer.example.test";
    public static final String DEMO_AUDIENCE = "hybrid-api";

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers(HttpMethod.POST, "/api/reports")
                    .hasAuthority("SCOPE_reports.write")
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .requestCache(cache -> cache.disable())
            // Allow only Bearer tokens in the Authorization header;
            // do not accept session cookies as API credentials.
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/web/**", "/login", "/logout", "/")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .loginPage("/login")
                .defaultSuccessUrl("/web/home", true)
                .permitAll()
            )
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
                .permitAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            )
            .csrf(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
            .anyRequest().denyAll()
        );
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        var user = User.withUsername("web-user")
            .password(encoder.encode("web-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(user);
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${DEMO_JWT_SECRET_BASE64}") String base64Secret) {

        byte[] bytes = Base64.getDecoder().decode(base64Secret);
        if (bytes.length < 32) {
            throw new IllegalArgumentException(
                "Demo HS256 key must contain at least 32 bytes"
            );
        }

        SecretKey key = new SecretKeySpec(bytes, "HmacSHA256");
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withSecretKey(key)
            .macAlgorithm(MacAlgorithm.HS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceCheck = jwt ->
            jwt.getAudience().contains(DEMO_AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(new OAuth2Error(
                    "invalid_token", "Invalid audience", null
                ));

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(DEMO_ISSUER),
            audienceCheck
        ));

        return decoder;
    }
}
```

**Each decision is intentional:**

- `apiChain` comes first and matches only `/api/**`. No form login or Basic auth on the API; Bearer tokens are handled by `oauth2ResourceServer`.
- `apiChain` enforces `STATELESS`. A web session cookie will not authenticate the API, even when both share the same domain.
- `apiChain` disables CSRF **solely under the token-only header assumption**, not because APIs are inherently safe.
- `webChain` matches `/web/**` **and** `/login`/`/logout`. The form/login/logout filters actually see the paths they need to process.
- `webChain` uses `IF_REQUIRED` and keeps CSRF enabled; authentication is stored in the session per Spring Security's mechanism.
- `fallbackChain` blocks all other paths; never use `anyRequest().permitAll()` as a fallback. `ERROR` dispatch is permitted for error processing; evaluate production error policies separately.
- The JWT decoder checks the HS256 secret, `iss`, `aud`, and validity timestamps. The secret is read from the environment; the demo **does not mint tokens from an API endpoint**.
- `SCOPE_reports.read` and `SCOPE_reports.write` separate the two capabilities. Spring Resource Server maps `scope=reports.read` to the `SCOPE_reports.read` authority by default.
- An HS256 JWT sharing a key between issuer/test and resource server is purely illustrative. Production should use issuer/JWKS and verify key rotation, trust boundaries, logging, and official issuer/audience values.

### 8.4. `DemoController.java`

```java
package com.example.hybrid;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String index() {
        return "hybrid demo";
    }

    @GetMapping(value = "/login", produces = MediaType.TEXT_HTML_VALUE)
    public String login(CsrfToken csrf) {
        return """
            <!doctype html>
            <html lang="en">
              <body>
                <form method="post" action="/login">
                  <input name="username">
                  <input name="password" type="password">
                  <input type="hidden" name="%s" value="%s">
                  <button type="submit">Sign in</button>
                </form>
              </body>
            </html>
            """.formatted(csrf.getParameterName(), csrf.getToken());
    }

    @GetMapping("/web/home")
    public String home(Authentication authentication) {
        return "web:" + authentication.getName();
    }

    @GetMapping("/web/csrf")
    public CsrfToken webCsrf(CsrfToken csrf) {
        return csrf;
    }

    @GetMapping("/api/reports")
    public String reports(Authentication authentication) {
        return "reports:" + authentication.getName();
    }

    @PostMapping("/api/reports")
    @ResponseStatus(HttpStatus.CREATED)
    public String createReport(Authentication authentication) {
        return "created:" + authentication.getName();
    }
}
```

`GET /login` is minimal HTML for the demo, not a production template. In a real system, use a template engine with HTML escaping and proper UI design. `CsrfToken` is provided by Spring Security; the form submits `_csrf` via a hidden input on POST.

`GET /web/csrf` is useful if a session-backed SPA needs to fetch a fresh token after login/logout; this endpoint requires authentication in the example. There is no `/api/login` controller issuing tokens, because a resource server is not responsible for minting tokens by default.

### 8.5. Startup commands

On Bash/local (assuming a Gradle wrapper and openssl are available):

```bash
# Generate a 32-byte demo key and pass it via environment variable.
export DEMO_JWT_SECRET_BASE64="$(openssl rand -base64 32)"
./gradlew bootRun
```

If the app runs without `DEMO_JWT_SECRET_BASE64`, the decoder bean will fail to initialize — **fail closed**. Do not commit this key to repos/logs or use it as a production secret. With PowerShell, you can generate a random Base64 value using the JDK/.NET cryptographic generator and assign it to the corresponding environment variable.

Observe the web flow with a cookie jar:

```bash
# Anonymous accessing private web path: expects 302 /login.
curl -i http://localhost:8080/web/home

# GET login form, keeping session cookie.
curl -i -b cookies.txt -c cookies.txt \
  http://localhost:8080/login
```

To submit a real login with curl, extract the hidden CSRF token from the HTML and keep the same cookie jar. On a shell with sed:

```bash
HTML=$(curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/login)

TOKEN=$(printf '%s\n' "$HTML" |
  sed -n 's/.*name="_csrf" value="\([^"]*\)".*/\1/p')

curl -i -b cookies.txt -c cookies.txt \
  --data-urlencode "username=web-user" \
  --data-urlencode "password=web-pass" \
  --data-urlencode "_csrf=$TOKEN" \
  http://localhost:8080/login

# With web session -> 200.
curl -i -b cookies.txt -c cookies.txt \
  http://localhost:8080/web/home

# Web session cookie is not accepted by Bearer-only API -> 401.
curl -i -b cookies.txt -c cookies.txt \
  http://localhost:8080/api/reports
```

These commands use **demo passwords**; never use `-u user:password` or print real cookies/tokens into CI logs. The sed parser here assumes the sample form HTML and is not meant for parsing complex production HTML.

To call the real API, you need an **access token issued by a trusted issuer** with matching signature, `iss`, `aud`, `exp`, and scopes. The demo has no real IdP, so no pre-generated valid token exists outside tests:

```bash
# ACCESS_TOKEN must be issued by an appropriate authorization server.
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/reports
```

Do not add a public `/api/dev/issue-token` endpoint just to make curl easier. The next test section signs JWTs inside **test sources** with a test key to verify that the decoder genuinely rejects and accepts the corresponding tokens.

## 9. Testing exact boundaries with MockMvc

File `src/test/java/com/example/hybrid/HybridSecurityTest.java`. Tests sign HS256 access tokens with a fixed 32-byte test key; the app receives the key via `@TestPropertySource`. The test key can be public, **never use it in real environments**.

```java
package com.example.hybrid;

import java.time.Instant;
import java.util.Base64;
import java.util.List;

import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

import com.nimbusds.jose.jwk.source.ImmutableSecret;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties =
    "DEMO_JWT_SECRET_BASE64=MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
class HybridSecurityTest {

    private static final String TEST_SECRET =
        "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=";

    @Autowired
    MockMvc mvc;

    private String token(
            String issuer, String audience, String scope, Instant expiry) {

        SecretKey key = new SecretKeySpec(
            Base64.getDecoder().decode(TEST_SECRET),
            "HmacSHA256"
        );
        JwtEncoder encoder = new NimbusJwtEncoder(
            new ImmutableSecret<>(key)
        );

        Instant now = Instant.now();
        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject("api-reader")
            .audience(List.of(audience))
            .issuedAt(expiry.isBefore(now)
                ? now.minusSeconds(1000) : now)
            .expiresAt(expiry)
            .claim("scope", scope)
            .build();

        JwsHeader header = JwsHeader
            .with(MacAlgorithm.HS256)
            .build();

        return encoder.encode(
            JwtEncoderParameters.from(header, claims)
        ).getTokenValue();
    }

    private String readToken() {
        return token(
            SecurityConfig.DEMO_ISSUER,
            SecurityConfig.DEMO_AUDIENCE,
            "reports.read",
            Instant.now().plusSeconds(300)
        );
    }

    @Test
    void anonymousWebRedirectsToLogin() throws Exception {
        mvc.perform(get("/web/home"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location",
                org.hamcrest.Matchers.endsWith("/login")
            ));
    }

    @Test
    void loginPageIsPublic() throws Exception {
        mvc.perform(get("/login"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                org.hamcrest.Matchers.containsString("<form")
            ));
    }

    @Test
    void formLoginCreatesSessionButDoesNotAuthenticateApi() throws Exception {
        MvcResult result = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "web-user")
                .param("password", "web-pass"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/web/home").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("web:web-user"));

        mvc.perform(get("/api/reports").session(session))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate",
                org.hamcrest.Matchers.containsString("Bearer")
            ));
    }

    @Test
    void apiWithoutBearerGets401() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().exists("WWW-Authenticate"));
    }

    @Test
    void bearerWithReadScopeGets200() throws Exception {
        mvc.perform(get("/api/reports")
                .header("Authorization", "Bearer " + readToken()))
            .andExpect(status().isOk())
            .andExpect(content().string("reports:api-reader"));
    }

    @Test
    void signedTokenMissingScopeGets403() throws Exception {
        String jwt = token(
            SecurityConfig.DEMO_ISSUER,
            SecurityConfig.DEMO_AUDIENCE,
            "reports.write",
            Instant.now().plusSeconds(300)
        );
        mvc.perform(get("/api/reports")
                .header("Authorization", "Bearer " + jwt))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidAudienceGets401() throws Exception {
        String jwt = token(
            SecurityConfig.DEMO_ISSUER,
            "another-api",
            "reports.read",
            Instant.now().plusSeconds(300)
        );
        mvc.perform(get("/api/reports")
                .header("Authorization", "Bearer " + jwt))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongIssuerGets401() throws Exception {
        String jwt = token(
            "https://attacker.invalid",
            SecurityConfig.DEMO_AUDIENCE,
            "reports.read",
            Instant.now().plusSeconds(300)
        );
        mvc.perform(get("/api/reports")
                .header("Authorization", "Bearer " + jwt))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void expiredJwtGets401() throws Exception {
        String jwt = token(
            SecurityConfig.DEMO_ISSUER,
            SecurityConfig.DEMO_AUDIENCE,
            "reports.read",
            Instant.now().minusSeconds(600)
        );
        mvc.perform(get("/api/reports")
                .header("Authorization", "Bearer " + jwt))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void bearerWriteScopeCanPost() throws Exception {
        String jwt = token(
            SecurityConfig.DEMO_ISSUER,
            SecurityConfig.DEMO_AUDIENCE,
            "reports.write",
            Instant.now().plusSeconds(300)
        );
        mvc.perform(post("/api/reports")
                .header("Authorization", "Bearer " + jwt))
            .andExpect(status().isCreated())
            .andExpect(content().string("created:api-reader"));
    }

    @Test
    void bearerDoesNotLogUserIntoWeb() throws Exception {
        mvc.perform(get("/web/home")
                .header("Authorization", "Bearer " + readToken()))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location",
                org.hamcrest.Matchers.endsWith("/login")
            ));
    }
}
```

### What is proven?

| Test | Status/result | Verifies |
| --- | --- | --- |
| Web anonymous | 302 login | Web entry point |
| GET login public | 200 | Prevents redirect loop from blocking the login page |
| Real form login + session | 302 then web 200 | Spring form login + session persistence |
| **Web session only sent to API** | **401** | API does not accept cookies as Bearer |
| API anonymous | 401 | Bearer entry point |
| Valid JWT + `reports.read` | 200 | Decoder + scope |
| Valid JWT missing GET scope | 403 | Authorization differs from authentication |
| JWT with wrong `iss` or `aud` | 401 | Trust boundary |
| Expired JWT | 401 | Token timestamp validation |
| JWT `reports.write` POST | 201 | Write permission separated from read; separate CSRF policy |
| **Bearer JWT header only sent to web** | **302 login** | Bearer does not become a web session |

`with(jwt())` in `spring-security-test` is convenient for mocking a JWT authentication when testing authorization/controllers, but **it does not verify real signatures/decoders**. This test suite attaches a header containing a real test-signed JWT so requests pass through the resource-server filter and decoder. For production tests, add tests with valid IdP/JWKS, key rotation, other algorithms, malformed tokens, tenant policies, and revocation rules.

### Running the tests

```bash
# When the project has a Gradle wrapper:
./gradlew test

# Try a real servlet container:
./gradlew bootRun
```

If there is no wrapper, use a compatible Gradle version or generate the wrapper per project workflow. MockMvc does not fully simulate browser cookie policies, proxies/TLS, or CORS preflight, so live HTTP tests are needed when behavior depends on those layers. The tests have no fixed stdout; status/body assertions are the expected outcomes.

## 10. CSRF and CORS in hybrid architectures

### 10.1. CSRF depends on how credentials are sent

The most useful question: **does the browser automatically send the credential when another website triggers a request?**

- `JSESSIONID` session cookie: typically auto-sent per cookie policy ⇒ needs CSRF protection for unsafe methods.
- Bearer access token placed only in the `Authorization` header explicitly attached by JavaScript/native clients ⇒ cookie CSRF pattern may not apply.
- Bearer token placed **in a cookie** that the browser auto-sends ⇒ must evaluate CSRF just like a cookie-authenticated request.
- Browser-cached HTTP Basic credentials also have auto-send behavior depending on context ⇒ never conclude "no session means no CSRF."
- A BFF receiving browser cookies ⇒ the BFF needs CSRF, even when downstream APIs only accept Bearer tokens.

With session-cookie SPAs, the CSRF token can be provided via an endpoint/CSRF cookie and returned in a custom header. Spring Security 6 has BREACH token encoding/deferred CSRF tokens; when using `CookieCsrfTokenRepository`, configure the appropriate handler and refresh the token after login/logout rather than merely calling `withHttpOnlyFalse()` and considering it done.

### 10.2. CORS is a browser origin policy

If a frontend at `https://app.example.org` calls an API at `https://api.example.org`, the browser may send an OPTIONS preflight before a request carrying an `Authorization` header. Spring Security recommends handling CORS **before security** because preflight requests carry no session cookie.

Do not carelessly configure `allowedOrigins("*")` together with credentialed CORS. Only allow the required origins, methods, and headers. CORS **does not** create authentication, is not data authorization, and does not block curl/server-side clients.

With a same-origin BFF, the browser usually calls only the BFF and rarely needs CORS to the resource server; tokens between the BFF and API must still be verified.

### 10.3. Cookies protect both privacy and consistency

When web login succeeds yet the next private GET returns 302 back to login, inspect `Set-Cookie`/`Cookie`, `Secure`/`SameSite`/`Domain`/`Path`, TLS termination, shared session stores, and trusted forwarded headers. An API token does not fix a web session login loop.

## 11. Logout and revocation

**Web logout** is typically handled by `LogoutFilter` together with `LogoutHandler` clearing `HttpSession` and `SecurityContext`; POST logout depends on CSRF policy. `LogoutSuccessHandler` decides the redirect/response body after cleanup. Never write a custom controller returning 200 and calling `session.invalidate()` while skipping remember-me/CSRF/context cleanup.

**API JWT:** the client dropping the token from memory does not guarantee the token is invalidated across all resource servers. If immediate logout/revocation is required, choose short token TTLs, refresh token rotation, introspection/denylists, or revocation policies provided by the authorization server. With OAuth2/OIDC, logging out of the web app and ending the SSO session at the IdP are two distinct actions.

**BFF:** logout must clear the browser session, server-side token store, refresh tokens, and/or IdP session per policy. Avoid returning `LOGOUT_OK` while tokens in the server store can still be used by an old session.

## 12. Scaling, failures, and operations

### Web session

- Multiple servers require sticky sessions or a shared session store if the same session must be read across different nodes.
- Consider session fixation, timeouts, concurrent sessions, remote logout, and how to update permissions for users with active sessions.
- Losing the session store can log users out or cause service errors; fail closed rather than opening access.
- Misconfigured cookies/paths/domains behind a proxy can cause login loops.

### Bearer API

- JWT verification may not call the IdP on every request, yet JWKS/key rotation, the token issuer, and network caching remain dependencies.
- Already-issued tokens may contain stale permissions; immediate revocation may require adding state.
- Rate limiting, auditing, object-level authorization, request validation, and monitoring remain mandatory.
- Never share HS256 secrets haphazardly between issuers and production resource servers; select signing/verification keys per your trust model.

### Hybrid

- Clear ownership is required for every URL, login/logout endpoint, OAuth2 callback, static resource, health check, and error dispatch.
- Unify response statuses so APIs never unexpectedly receive 302 HTML and web routes never unexpectedly receive Bearer challenges.
- Log enough to identify which chain matched, without logging tokens/cookies/passwords.
- Test status **and** side effects; rejected requests must not mutate data.

## 13. Mistakes to avoid

1. **Using `SessionCreationPolicy.STATELESS` on web form login** and then trying to persist sessions manually in code.
2. **Disabling CSRF application-wide** just because there is a Bearer API.
3. **Mixing cookie sessions and Bearer tokens into the same chain** without a clear policy for CSRF/entry points.
4. **Configuring only `requestMatchers` while forgetting `securityMatcher`** when intending to separate two chains.
5. **Leaving a fallback chain as `permitAll()`** and unintentionally exposing new routes.
6. **Leaving `/login` outside the web matcher** so the form login filter never receives POSTs.
7. **Using `@WithMockUser` to claim login/password authentication was verified**.
8. **Using `with(jwt())` to claim JWT signatures were verified**.
9. **Skipping audience validation** because issuer validation was already performed.
10. **Sending an OIDC ID token to an API** instead of an access token with the right audience.
11. **Trusting `SCOPE_reports.read` to allow reading every tenant**.
12. **Putting JWTs in URLs/logs/localStorage** without evaluating XSS and leakage.
13. **Mistaking CORS for authentication or CSRF protection**.
14. **Assuming session logout revokes all JWTs**.
15. **Deploying demo keys/passwords to production**.
16. **Testing only with MockMvc** without testing real browser cookies, CORS, or proxies/TLS.
17. **Replacing a Bearer entry point with a 302 HTML redirect** for APIs without an explicit contract.
18. **Leaving error dispatch, OAuth2 callbacks, logout, and data download links unprotected** in chain policies.

## 14. Pre-decision architecture checklist

- [ ] Identified all clients: web browser, SPA, mobile, BFF, machine/partner.
- [ ] Selected the right credential: session cookie, Bearer access token, or both with explicit boundaries.
- [ ] Assigned every URL to a specific chain, rule, and `@Order`.
- [ ] Web login/logout/callbacks are actually handled by the web chain.
- [ ] Token-only APIs do not accept web session cookies as authentication.
- [ ] Web routes do not automatically accept Bearer tokens as sessions, unless explicitly designed.
- [ ] Web/BFF enables CSRF; Bearer-only APIs exempt CSRF only when the threat model holds.
- [ ] CORS preflight is handled properly before security when cross-origin is needed.
- [ ] JWT checks signature, algorithm, issuer, audience, validity timestamps, and scopes.
- [ ] Access tokens, ID tokens, and refresh tokens are never misused for one another.
- [ ] Cookies have Secure, HttpOnly, SameSite, Path, and Domain matching the deployment.
- [ ] Logout/revocation, session timeouts, JWT TTLs, and key rotation are defined.
- [ ] Authorization by tenant, owner, action, and data is enforced at the service/repository layer.
- [ ] Tests cover anonymous, authenticated, wrong scope, wrong issuer/audience, and expired tokens.
- [ ] Tests cover **session-only → API 401** and **Bearer-only → web redirect**.
- [ ] Tests cover session lifecycle and CSRF with form login/logout.
- [ ] Live HTTP/browser tests verify proxies, CORS, cookies, and login redirects.
- [ ] Secrets/tokens never appear in source code, logs, or production URLs.

### Self-check questions

1. Why shouldn't a session cookie be treated as a Bearer access token?
2. When can CSRF be disabled for an API, and when does an API still need CSRF?
3. Why does a token-only API usually return 401 instead of redirecting to an HTML login page?
4. How do `securityMatcher` and `requestMatchers` differ?
5. Why must `/login` and `/logout` be included in the web chain matcher if those URLs are outside `/web/**`?
6. Why does `STATELESS` not mean there is no DB/cache or revocation?
7. After verifying JWT signature and issuer, why must you still verify the audience?
8. Why does `with(jwt())` not replace testing with a genuinely signed token?
9. How does a BFF mitigate token theft via XSS, and what must still be defended against?
10. Why does session logout not automatically invalidate already-issued JWTs?
11. May a JWT with a READ scope view documents belonging to another tenant?
12. Should a logged-in web session be accepted by a token-only API?

**Hints:** (1) a cookie is an ID for server state, while a Bearer token is an API credential requiring verification; (2) depends on whether the browser auto-sends credentials; (3) different contract/client expectations; (4) selects the filter chain vs. selects authorization rules; (5) login/logout filters must see the requests; (6) stateless only refers to request security context/sessions; (7) a valid token for another API can share the same issuer; (8) mock bypasses the decoder; (9) tokens stay on the server, yet CSRF/XSS still exist; (10) self-contained JWTs remain valid until `exp` unless revoked; (11) no, object-level authorization is required; (12) no under a token-only policy.

## Official documentation

- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security — Servlet Security Architecture / FilterChainProxy: https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security — Form Login: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
- Spring Security — CSRF, including SPA considerations: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security — CORS: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security — Logout: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Security — Testing OAuth2 Resource Server with MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/oauth2.html
- Spring Boot 3.3 — Testing Spring Boot applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
