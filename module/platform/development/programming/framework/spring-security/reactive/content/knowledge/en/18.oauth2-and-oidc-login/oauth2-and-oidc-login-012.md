# RP-Initiated OIDC Logout and Federated Logout Limitations

## 1. Context and Learning Outcomes

This lesson belongs to the **OAuth2/OIDC Login** section of **Spring Security - reactive / WebFlux**. For an application logging in with OpenID Connect (OIDC), a **Sign out** button can mean several different things: ending the current application's session, asking the identity provider to terminate its SSO session, or asking other linked applications to terminate their sessions too. These three outcomes **are not automatically synonymous**.

**RP-Initiated Logout** (client-initiated logout) is the standard flow in **OpenID Connect RP-Initiated Logout 1.0**. Your application (the Relying Party — **RP**) handles local logout and then directs the user's browser to the **Logout Endpoint** at the OIDC provider (OpenID Provider — **OP**). Spring Security WebFlux supports this step via `OidcClientInitiatedServerLogoutSuccessHandler`.

Objectives:

1. Distinguish **local logout**, **RP-initiated logout**, **OP-initiated front-channel**, **OP-initiated back-channel**, and “sign out everywhere”.
2. Understand the differences among **RP WebSession**, **OP session**, **other RP sessions**, access tokens, and refresh tokens.
3. Read `end_session_endpoint` in discovery metadata, and understand `id_token_hint`, `post_logout_redirect_uri`, `state`, and registered URI rules.
4. Properly configure `ReactiveClientRegistrationRepository`, `ServerHttpSecurity.oauth2Login(...)`, `logout(...)`, and the reactive logout success handler.
5. Keep **POST /logout protected by CSRF**, while clearing the local `SecurityContext` and `WebSession` before sending the browser to the OP.
6. Build a Java 17+, Spring Boot 3.3.5/WebFlux example with a logout form and real OP configuration.
7. Write **unit tests without a real OP** for how the handler builds the redirect URI, and distinguish them from E2E tests requiring an OP.
8. State limitations accurately: redirecting to the OP **does not prove the OP logged out**, and OP logout **does not guarantee all RPs logged out or tokens were revoked**.

This lesson focuses on **OIDC Login and RP-Initiated Logout on the reactive client side**. It does not implement an OP itself, and never confuses Servlet's `OidcClientInitiatedLogoutSuccessHandler` with reactive's `OidcClientInitiatedServerLogoutSuccessHandler`.

## 2. Three Places Holding Sessions and Their Security Implications

Suppose a browser has logged into applications A and B through a single OP:

```text
Browser
  |
  +-- RP A session cookie ----> App A / WebSession A
  |
  +-- RP B session cookie ----> App B / Session B
  |
  +-- OP cookie --------------> Identity Provider / OP session
                                      |
                                      +-- Issuer of ID Token
                                      +-- May have issued Access Token
                                      +-- May have issued Refresh Token
```

These are three independent state domains:
- **RP A** manages security context, session ID, cookies, and business state belonging to A.
- **OP** manages its own SSO session, potentially alongside remember-me or a session with an upstream Identity Provider.
- **RP B** manages its own `WebSession`; it does not automatically receive A's logout event without an appropriate notification mechanism.

RP A cannot directly delete cookies belonging to the OP or RP B because cookie scopes/domains differ. If the OP supports multiple devices, logging out one browser session does not automatically terminate sessions on a phone.

### Logout Classification

| Type | Initiated By? | Direct Effect | What It Does Not Automatically Guarantee |
| --- | --- | --- | --- |
| **Local logout** | User at RP A | Clears authentication/session A | That OP or RP B logged out |
| **RP-initiated logout** | RP A → browser → OP | Asks OP to terminate SSO session | That OP complied, or RP B received notification |
| **Front-channel logout** | OP via browser | OP calls/embeds logout endpoints of RP(s) | That browser always sends required cookies |
| **Back-channel logout** | OP → RP server | RP receives Logout Token and invalidates matching session | That RP is configured or has full session mapping |
| **Global logout / sign out everywhere** | Product/OP policy | Revokes sessions/credentials within designed scope | Being available by default from a single HTTP redirect |

**Key observation:** If you perform local logout on A, revisit A, and immediately get logged back in without entering a password, local logout is not necessarily broken. The OP may still hold an active **SSO session** and silently re-authenticate the user. To avoid this, A can initiate RP-Initiated Logout, provided the OP genuinely supports and processes it.

## 3. RP-Initiated Logout Flow in Spring Security Reactive

```text
Browser currently logged into RP A
        |
        | POST /logout + session cookie + CSRF token
        v
Spring Security LogoutWebFilter at RP A
        |
        +--> ServerLogoutHandler:
        |      clear SecurityContext
        |      clear CSRF token
        |      invalidate WebSession
        |
        v
OidcClientInitiatedServerLogoutSuccessHandler
        |
        +--> Receive pre-logout Authentication
        +--> Identify OIDC principal / registrationId
        +--> ReactiveClientRegistrationRepository
        +--> Read end_session_endpoint metadata
        +--> Build OP redirect URL, including id_token_hint,
        |    post_logout_redirect_uri when configured
        |
        v
HTTP redirect to OP Logout Endpoint
        |
        v
Browser navigates to OP (typically via GET)
        |
        +--> OP handles logout or shows confirmation
        +--> OP may emit notifications to other RPs
        |
        v
OP may redirect back to registered /signed-out URI at RP A
```

**Two operations never to confuse:**
1. **`POST /logout`** to the **RP** is a state-changing request from the browser to Spring Security. When the app uses session/cookies and CSRF is enabled, the POST must include a valid CSRF token. `GET /logout` should never directly log out.
2. The HTTP redirect (usually GET) from the browser to the **OP `end_session_endpoint`** happens **after** local logout. The OP decides how to execute the request and responds per its protocol support.

`OidcClientInitiatedServerLogoutSuccessHandler` is solely a **`ServerLogoutSuccessHandler`**: it decides where to redirect after local logout. It is **not** a handler that hunts down and deletes every RP session; local cleanup belongs to `ServerLogoutHandler`.

A 302 status from the RP proves it **built and issued the redirect instruction**—it does not prove the browser reached the OP, the OP cleared its session, RP B logged out, or access tokens were revoked.

## 4. OIDC Parameters You Must Understand

### 4.1. `end_session_endpoint` from OP Discovery

An OIDC Provider may publish metadata, for example:

```json
{
  "issuer": "https://idp.example.test",
  "authorization_endpoint": "https://idp.example.test/authorize",
  "token_endpoint": "https://idp.example.test/token",
  "jwks_uri": "https://idp.example.test/jwks",
  "end_session_endpoint": "https://idp.example.test/connect/endsession"
}
```

These URLs use an **illustrative** domain with no live OP assumed. On an OP supporting RP-Initiated Logout and Discovery, `end_session_endpoint` tells the RP where to send OP logout requests. Spring Security can read this metadata via `issuer-uri` when building `ClientRegistration` through discovery.

**Never guess that every OP has `/logout`**; some OPs do not publish an end-session endpoint, or use proprietary/vendor-specific URLs. Check the OP's documentation and capabilities.

Comparison:
- `authorization_endpoint`: initiates login/authorization.
- `token_endpoint`: exchanges authorization code for tokens.
- `end_session_endpoint`: requests the OP to terminate its session.
- `revocation_endpoint` (if supported by OP): **token revocation** mechanism, distinct from terminating an OP session.

### 4.2. `id_token_hint`

`id_token_hint` (RECOMMENDED in RP-Initiated Logout) is the **ID Token** previously issued by the OP to the RP, hinting which session/user/client the OP should log out.

Example URL after URL-encoding:

```http
GET /connect/endsession?id_token_hint=ID_TOKEN_TEST
    &post_logout_redirect_uri=https%3A%2F%2Fapp.example.test%2Fsigned-out
HTTP/1.1
Host: idp.example.test
```

Real HTTP requests put the URI on **one line**; it is wrapped here for readability. `ID_TOKEN_TEST` is a dummy string explaining syntax.

ID Token:
- Carries authentication/identity claims issued for the RP.
- **Is not** an Access Token for calling resource servers.
- **Is not** a Refresh Token for obtaining new access tokens.
- Sending it as a hint to the OP **does not automatically revoke** still-valid access/refresh tokens.

An ID Token can contain user information, and some OPs' logout URL logs capture query strings. Therefore, **never record raw `Location` headers containing `id_token_hint`, tokens, cookies, or token-bearing URLs in logs/APM/analytics/support tickets**. Use HTTPS and proper proxy/query redaction.

### 4.3. `post_logout_redirect_uri`

This is where the OP **may** redirect the browser after completing logout:

```text
https://app.example.test/signed-out
```

The OP requires this URI to **match a registered URI exactly** for the RP per the specification. It is **different** from the login callback:

| URI | Purpose |
| --- | --- |
| `https://app.example.test/login/oauth2/code/training` | OIDC authorization-code callback after login |
| `https://app.example.test/signed-out` | Callback displaying post-logout status |
| `https://idp.example.test/connect/endsession` | OP Logout Endpoint |

A common mistake is registering the login callback while **forgetting** to register the post-logout URI; the OP can refuse to redirect back even for a valid logout request.

Spring Security supports the `{baseUrl}` template:

```java
handler.setPostLogoutRedirectUri("{baseUrl}/signed-out");
```

Applications behind a reverse proxy must compute the right **public scheme/host/port**, e.g., `https://app.example.test` rather than `http://localhost:8080`. Trust `Forwarded`/`X-Forwarded-*` headers only from controlled proxies; never use user-controlled URLs to create open redirects.

### 4.4. `state`, `logout_hint`, and `client_id`

Per RP-Initiated Logout 1.0:
- `state`: optional, opaque value allowing the RP to correlate logout requests and callbacks; if used by the RP, verify response state matches the session and prevent replay.
- `logout_hint`: optional, OP-specific hint about the user/session; may contain email/username so consider privacy.
- `client_id`: optional when the OP needs to identify the client, though it does not replace `id_token_hint` or registered URI rules.

**Do not assume the reactive handler in Spring Security 6.3 automatically generates and validates `state` across all workflows**; if the app implements logout return correlation, design and test it explicitly.

### 4.5. GET Redirect vs. Form POST at the OP

`OidcClientInitiatedServerLogoutSuccessHandler` traditionally uses an HTTP redirect so the browser sends a GET to the OP. Some OPs/framework versions may support Form POST logout and customizable redirect strategies. **Never blindly use newer APIs on Spring Security 6.3**; check your exact version before adding options. The demo uses the default redirect matching the documentation.

## 5. Reactive APIs to Use

### `ReactiveClientRegistrationRepository`

Spring Boot can auto-create the repository from `spring.security.oauth2.client.registration.*` and `spring.security.oauth2.client.provider.*`:

- `registrationId`: internal client name, e.g., `training`.
- `client-id`, `client-secret`, and client authentication method.
- `authorization-grant-type: authorization_code`.
- `scope: openid,profile` to use OIDC principal/ID Token.
- `redirect-uri` for login callback.
- `issuer-uri` for provider discovery, which can yield `end_session_endpoint`.

The **reactive** repository differs from Servlet's `ClientRegistrationRepository`. Importing the Servlet type causes a constructor mismatch on the reactive handler.

### `OidcClientInitiatedServerLogoutSuccessHandler`

Class:

```java
import org.springframework.security.oauth2.client.oidc.web.server.logout.OidcClientInitiatedServerLogoutSuccessHandler;
```

Configuration fragment:

```java
OidcClientInitiatedServerLogoutSuccessHandler oidcLogout =
        new OidcClientInitiatedServerLogoutSuccessHandler(
                clientRegistrationRepository);
oidcLogout.setPostLogoutRedirectUri("{baseUrl}/signed-out");
```

Here `clientRegistrationRepository` is of type `ReactiveClientRegistrationRepository`, injected by Spring. The handler uses the pre-logout authentication to construct the redirect URI for an OIDC user.

If a user logged in via form/Basic or lacks sufficient OIDC data, the handler can fall back to a **local fallback success URL** instead of sending a contextless OP logout request. Test this fallback whenever the app allows multiple login methods.

### `ServerLogoutHandler` and Cleanup

In WebFlux:
- `SecurityContextServerLogoutHandler`: clears the security context stored at the RP.
- `WebSessionServerLogoutHandler`: invalidates the current `WebSession`.
- `CsrfServerLogoutHandler`: clears the CSRF token in its repository.
- `DelegatingServerLogoutHandler`: composes multiple handlers.

Configuring a custom `logoutHandler(...)` is a **cleanup** decision, not merely attaching an extra redirect. Make sure you do not forget to invalidate `WebSession`, especially if security context/session repositories are customized.

### WebFlux vs. Servlet

| WebFlux reactive | Servlet |
| --- | --- |
| `ServerHttpSecurity` | `HttpSecurity` |
| `SecurityWebFilterChain` | `SecurityFilterChain` |
| `ReactiveClientRegistrationRepository` | `ClientRegistrationRepository` |
| `OidcClientInitiatedServerLogoutSuccessHandler` | `OidcClientInitiatedLogoutSuccessHandler` |
| `WebSession` | `HttpSession` |
| `ServerLogoutHandler` | `LogoutHandler` |

**Never copy imports from Servlet examples** and expect them to work in a WebFlux app.

## 6. Java 17 + Spring Boot 3.3.5 WebFlux Project

The demo below runs as an **OIDC Relying Party** once you have a test provider supporting discovery/end-session and a client registration. The **unit tests in section 9 need no network OP**, whereas **real login and logout** require an OP/IdP. That is a protocol requirement, not a mock service you can spin up with plain Java.

Structure:

```text
reactive-oidc-logout/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/dev/example/oidclogout/
    │   │   ├── OidcLogoutApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── DemoController.java
    │   └── resources/application.yml
    └── test/java/dev/example/oidclogout/
        └── OidcLogoutHandlerTests.java
```

### 6.1. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'reactive-oidc-logout'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'dev.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Use only the WebFlux starter so the app selects the reactive stack. Adding `spring-boot-starter-web` causes Spring Boot to prefer Servlet/MVC, breaking alignment with this example.

### 6.2. Main Class

`src/main/java/dev/example/oidclogout/OidcLogoutApplication.java`:

```java
package dev.example.oidclogout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OidcLogoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(OidcLogoutApplication.class, args);
    }
}
```

### 6.3. Provider Configuration in `application.yml`

`src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          training:
            provider: training
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          training:
            issuer-uri: ${OIDC_ISSUER_URI}
```

You must supply the 3 environment variables `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, and `OIDC_ISSUER_URI` from a **real/test OIDC provider**. Never store real client secrets in Git, screenshots, or shell history. These are mandatory runtime settings to contact the OP, not values to guess.

At the OP, register **two separate URIs**:
- Login callback: `http://localhost:8080/login/oauth2/code/training` (when OP permits local HTTP) or a public HTTPS URI.
- Post-logout return: `http://localhost:8080/signed-out` (when OP permits local HTTP) or `https://app.example.test/signed-out`.

Do not assume every OP accepts HTTP localhost; many OPs allow HTTPS only or impose strict callback restrictions. The OP's documentation is authoritative.

**Startup may require network discovery** from `issuer-uri`. If the OP is unreachable or DNS/TLS fails, the app may fail to boot or log in. Unit tests in section 9 use a mock client registration so they run without these environment variables.

### 6.4. Spring Security Reactive and Logout Handlers

`src/main/java/dev/example/oidclogout/SecurityConfig.java`:

```java
package dev.example.oidclogout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.server.logout.OidcClientInitiatedServerLogoutSuccessHandler;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.ServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;
import org.springframework.security.web.server.csrf.CsrfServerLogoutHandler;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRepository;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveClientRegistrationRepository registrations) {

        ServerCsrfTokenRepository csrfRepository =
                new WebSessionServerCsrfTokenRepository();

        ServerLogoutHandler cleanup = new DelegatingServerLogoutHandler(
                new SecurityContextServerLogoutHandler(),
                new CsrfServerLogoutHandler(csrfRepository),
                new WebSessionServerLogoutHandler());

        OidcClientInitiatedServerLogoutSuccessHandler oidcLogout =
                new OidcClientInitiatedServerLogoutSuccessHandler(
                        registrations);
        oidcLogout.setPostLogoutRedirectUri("{baseUrl}/signed-out");

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/", "/signed-out", "/login")
                            .permitAll()
                        .anyExchange().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .csrf(csrf -> csrf.csrfTokenRepository(csrfRepository))
                .logout(logout -> logout
                        .logoutUrl("/logout")
                        .logoutHandler(cleanup)
                        .logoutSuccessHandler(oidcLogout))
                .build();
    }
}
```

**Explanation:**

1. `@EnableWebFluxSecurity` and `ServerHttpSecurity` configure the reactive application.
2. `oauth2Login(...)` enables OIDC login when `ClientRegistration` has scope `openid` and the OP supports it.
3. `ReactiveClientRegistrationRepository` is created by Boot from `application.yml`; the handler uses the repository matching the OP.
4. `csrfRepository` is shared between the CSRF filter and `CsrfServerLogoutHandler`, avoiding one verifying token A while another deletes token B.
5. `SecurityContextServerLogoutHandler` clears the context; `WebSessionServerLogoutHandler` invalidates the local session; `CsrfServerLogoutHandler` clears the old token.
6. `DelegatingServerLogoutHandler` keeps local cleanup steps explicit when customizing the logout handler.
7. `OidcClientInitiatedServerLogoutSuccessHandler` is a **success handler** that generates the redirect to the OP after cleanup; it does not itself terminate all federated sessions.
8. `{baseUrl}/signed-out` must be registered **exactly** with the OP. Never accept arbitrary post-logout URIs from request queries.
9. `/signed-out` is public because the browser returns from the OP after the local `WebSession` has been destroyed.
10. Never disable CSRF or turn logout into GET to avoid 403 errors.
11. If production uses Spring Session Redis or a custom session resolver, verify real invalidation in the session store and cookie name/Path/Domain.

Spring Security WebFlux supports default local logout at `/logout`; this code explicitly declares cleanup handlers so learners see which steps run. Never interpret a redirect success handler as “every session everywhere has been revoked”.

### 6.5. Controller with CSRF-Protected POST Logout Form

`src/main/java/dev/example/oidclogout/DemoController.java`:

```java
package dev.example.oidclogout;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.util.HtmlUtils;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    @GetMapping("/")
    public Mono<String> home() {
        return Mono.just(
                "OIDC WebFlux demo: /oauth2/authorization/training "
              + "-> /profile -> /logout-form");
    }

    @GetMapping("/profile")
    public Mono<Map<String, String>> profile(
            @AuthenticationPrincipal OidcUser user) {
        return Mono.just(Map.of("subject", user.getSubject()));
    }

    @GetMapping(value = "/logout-form",
            produces = MediaType.TEXT_HTML_VALUE)
    public Mono<String> logoutForm(ServerWebExchange exchange) {
        Mono<CsrfToken> tokenPublisher =
                exchange.getAttribute(CsrfToken.class.getName());

        if (tokenPublisher == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF token unavailable"));
        }

        return tokenPublisher.map(token -> """
                <!doctype html>
                <html lang="en">
                <head><meta charset="UTF-8"><title>Sign out</title></head>
                <body>
                  <h1>Sign out of the application and request logout at the OP</h1>
                  <form action="/logout" method="post">
                    <input type="hidden" name="%s" value="%s">
                    <button type="submit">Sign out</button>
                  </form>
                </body>
                </html>
                """.formatted(
                    HtmlUtils.htmlEscape(token.getParameterName()),
                    HtmlUtils.htmlEscape(token.getToken())));
    }

    @GetMapping("/signed-out")
    public Mono<String> signedOut() {
        return Mono.just(
                "The local application session has ended. "
              + "OP and federated application logout "
              + "depend on protocol results and configuration.");
    }
}
```

- `/profile` requires an OIDC session and displays only `subject`, **never returning raw ID Tokens/access tokens/refresh tokens**.
- `/logout-form` requires authentication due to `anyExchange().authenticated()`, reads `Mono<CsrfToken>` from the exchange attribute, and renders the hidden field.
- The browser performs a **form `POST /logout`** (full-page navigation), which handles redirects to the OP domain better than `fetch("/logout")`, which follows redirects inside fetch.
- `/signed-out` is public; when returning from the OP without the old session, requiring auth would cause a login loop.
- HTML escaping the hidden input helps when rendering attributes; in real apps, prefer a template engine with safe escaping and appropriate security headers.

## 7. Running with a Real OP and Interpreting Results Accurately

### Preparing the OP

1. Create an OIDC client in a test OP that genuinely supports **RP-Initiated Logout 1.0**.
2. Register both the login callback and post-logout redirect URI.
3. Supply `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, and `OIDC_ISSUER_URI` securely.
4. Verify discovery metadata includes `end_session_endpoint` and TLS/certificates validate cleanly.
5. In production, use HTTPS; never put client secrets or `id_token_hint` into URLs/logs that could be shared.

Run:

```bash
gradle bootRun
```

If using the Gradle Wrapper, run `./gradlew bootRun` or `gradlew.bat bootRun`. Without a real OP, **section 9 unit tests still run standalone**, though end-to-end OIDC login cannot be verified.

### Execution

1. Open `http://localhost:8080/oauth2/authorization/training` or the corresponding HTTPS URL. The browser goes to the OP to log in.
2. When the OP authenticates and returns an authorization code, Spring Security completes OIDC login at `/login/oauth2/code/training`.
3. Open `/profile` and receive the logged-in user's `subject`.
4. Open `/logout-form`. The browser receives the active session's CSRF token.
5. Click **Sign out**. The browser sends `POST /logout` with the `WebSession` cookie and CSRF token.
6. Inspect Network: the RP returns a redirect response with `Location` pointing to the OP's `end_session_endpoint`. **Do not copy the live URL because it contains `id_token_hint`.**
7. The browser reaches the OP. The OP may display a confirmation prompt or process logout and redirect to the registered `/signed-out`.
8. After logout, revisit `/profile`; the old local RP session is no longer accepted.
9. Observe whether the OP still performs instant single sign-on; if so, check the OP's session/logout behavior rather than assuming the RP's local logout failed.
10. If RP B exists in the lab, test B's actual session directly instead of inferring it from RP A's redirect status.

### POST Missing CSRF

Sending `POST /logout` without a token in a browser-session app with CSRF enabled normally returns **403 Forbidden**, and logout does not occur. Never “fix” this by disabling CSRF or switching to GET logout.

### If the OP Does Not Support End-Session

If discovery metadata lacks `end_session_endpoint`, the app cannot assume RP-Initiated Logout works. The handler can fall back locally; the product should clearly state “application session ended” while SSO at the OP may persist. Check provider docs for vendor-specific endpoints rather than constructing an unverified vendor logout URL from untrusted input.

## 8. Designing Tests for Independent Scopes

| Scenario | Expectation | What It Proves |
| --- | --- | --- |
| Unauthenticated user hits `/profile` | Login required | HTTP security |
| OIDC login succeeds | Profile returns `subject` | OIDC login at RP |
| `POST /logout` missing CSRF | 403 | RP CSRF guard |
| Valid `POST /logout` | Redirects to OP end-session | RP **requested** OP logout |
| Redirect includes `id_token_hint` | Matching ID Token hint present | Redirect built from OIDC authentication |
| Registered return URI | OP can return browser to `/signed-out` | Post-logout navigation |
| Reusing old RP session ID | Cannot access profile as old user | Local session invalidation |
| Re-login after OP logout | Depends on OP auth policy | Whether OP session actually remains |
| RP B lacks notification support | Session B may remain active | Federated logout limits |
| RP B has back-channel | RP B validates Logout Token and destroys session | Federated session propagation |
| Old access token still valid | Depends on expiration/revocation/introspection | Token lifecycle is **separate** |
| Multi-device sessions | Depends on OP and global logout policy | Does not default to signing out all devices |

**QA principle:** Handler unit tests can verify the **`Location` URL**, but cannot verify that the OP actually logged out. E2E tests require a test OP, a real browser, or an HTTP client compatible with the OIDC flow and session store.

When testing local session invalidation:
- Log in with a test account and save the RP session ID in a secure test environment.
- `POST /logout` with a valid CSRF token.
- Send a protected request with the **old session ID** from an independent client.
- Verify the server **does not recognize the old identity**, even if a browser kept the cookie.
- For distributed sessions, test across multiple instances.

Never test with real production session IDs/tokens or publish Network traces containing secrets.

## 9. Unit Tests for the Reactive Logout Handler Without a Network OP

These tests use a **mock** `ClientRegistration` with OP metadata containing a test `end_session_endpoint`, build a mock `OidcUser`/`OidcIdToken`, and invoke `OidcClientInitiatedServerLogoutSuccessHandler` directly. Hence they **do not depend on `issuer-uri`, a test OP server, a browser, or `application.yml`**.

File `src/test/java/dev/example/oidclogout/OidcLogoutHandlerTests.java`:

```java
package dev.example.oidclogout;

import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.client.oidc.web.server.logout.OidcClientInitiatedServerLogoutSuccessHandler;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;
import org.springframework.security.web.server.WebFilterExchange;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OidcLogoutHandlerTests {

    private ClientRegistration testRegistration() {
        return ClientRegistration.withRegistrationId("training")
                .clientId("test-client-only")
                .clientSecret("test-secret-only")
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri(
                        "{baseUrl}/login/oauth2/code/{registrationId}")
                .scope("openid", "profile")
                .authorizationUri("https://idp.example.test/authorize")
                .tokenUri("https://idp.example.test/token")
                .jwkSetUri("https://idp.example.test/jwks")
                .issuerUri("https://idp.example.test")
                .providerConfigurationMetadata(Map.of(
                        "end_session_endpoint",
                        "https://idp.example.test/connect/endsession"))
                .build();
    }

    private OidcClientInitiatedServerLogoutSuccessHandler handler() {
        var repo = new InMemoryReactiveClientRegistrationRepository(
                testRegistration());
        var handler =
                new OidcClientInitiatedServerLogoutSuccessHandler(repo);
        handler.setPostLogoutRedirectUri("{baseUrl}/signed-out");
        handler.setLogoutSuccessUrl(URI.create("/signed-out"));
        return handler;
    }

    private Authentication oidcAuth(String tokenValue) {
        OidcIdToken token = OidcIdToken.withTokenValue(tokenValue)
                .subject("test-user")
                .claim("iss", "https://idp.example.test")
                .build();

        var principal = new DefaultOidcUser(
                List.of(new OidcUserAuthority(token)), token);

        return new OAuth2AuthenticationToken(
                principal, principal.getAuthorities(), "training");
    }

    private URI redirect(
            OidcClientInitiatedServerLogoutSuccessHandler handler,
            Authentication authentication) {

        MockServerWebExchange exchange = MockServerWebExchange.from(
                MockServerHttpRequest
                        .post("https://app.example.test/logout").build());

        WebFilterExchange webFilterExchange =
                new WebFilterExchange(exchange, e -> Mono.empty());

        StepVerifier.create(
                handler.onLogoutSuccess(webFilterExchange, authentication))
                .verifyComplete();

        URI location = exchange.getResponse()
                .getHeaders().getLocation();
        assertNotNull(location);
        return location;
    }

    private String decodedQuery(URI redirect) {
        assertNotNull(redirect.getRawQuery());
        return URLDecoder.decode(
                redirect.getRawQuery(), StandardCharsets.UTF_8);
    }

    @Test
    void redirectsToTheConfiguredProviderEndSessionEndpoint() {
        URI location = redirect(handler(), oidcAuth("id-token-one"));

        assertEquals("https", location.getScheme());
        assertEquals("idp.example.test", location.getHost());
        assertEquals("/connect/endsession", location.getPath());
    }

    @Test
    void sendsCurrentIdTokenAsHint() {
        URI location = redirect(handler(), oidcAuth("id-token-two"));
        assertTrue(decodedQuery(location)
                .contains("id_token_hint=id-token-two"));
    }

    @Test
    void includesRegisteredPostLogoutReturnUri() {
        URI location = redirect(handler(), oidcAuth("id-token-three"));
        assertTrue(decodedQuery(location).contains(
                "post_logout_redirect_uri=https://app.example.test/signed-out"));
    }

    @Test
    void differentUsersTokensYieldDifferentRedirects() {
        URI first = redirect(handler(), oidcAuth("test-token-A"));
        URI second = redirect(handler(), oidcAuth("test-token-B"));

        assertNotEquals(first, second);
        assertTrue(decodedQuery(first).contains(
                "id_token_hint=test-token-A"));
        assertTrue(decodedQuery(second).contains(
                "id_token_hint=test-token-B"));
    }

    @Test
    void nonOidcAuthenticationUsesLocalFallback() {
        Authentication local =
                UsernamePasswordAuthenticationToken.authenticated(
                        "local-user", "not-real-password", List.of());

        URI location = redirect(handler(), local);
        assertEquals("/signed-out", location.toString());
    }
}
```

Run:

```bash
gradle test --tests dev.example.oidclogout.OidcLogoutHandlerTests
```

**Expected:** 5 tests pass with the dependencies in section 6, **without calling an OP**. This is the expected outcome based on the API and example structure, **not a claim that Gradle was executed on your machine**.

The tests verify:
- OP logout host/path/scheme comes accurately from metadata.
- `id_token_hint` comes from the OIDC principal rather than a hardcoded ID token.
- `post_logout_redirect_uri` is built from the right base URL.
- Different ID Tokens produce different hints.
- Non-OIDC users hit the local fallback.

**Suite limitations:** It does not run the real Spring Boot security chain, nor does it test POST CSRF, `WebSession` invalidation, cookies, OP responses, RP B notifications, token revocation, or multi-device logout. For production, add `WebTestClient` integration tests with `mockOidcLogin()` or browser/OP E2E tests per scope, and test session invalidation using the old session ID.

## 10. What Are the Limitations of Federated Logout?

### 10.1. RP A Logout Has No Authority to Terminate RP B

Even when OP logout succeeds, RP B may still retain its old session. Only if both the OP and B support **front-channel/back-channel notifications** or another session registry mechanism will B know to invalidate its session.

**Front-channel logout:** notifications travel through the browser. It can fail when browsers block third-party cookies, iframes, network calls, or frame restrictions. Never use A's redirect result as proof that B logged out.

**Back-channel logout:** the OP sends a **Logout Token** server-to-server to the RP; the RP must verify signature, issuer/audience, logout event, `sid`/`sub`, and replay controls. It requires an endpoint/registry and OP–RP session correlation. It is not “automatically included” just by configuring RP-initiated logout.

**Framework versions:** Modern Spring Security docs support reactive back-channel logout, though DSLs/requirements may have been added after Spring Security 6.3. This lesson uses Boot 3.3.5 / Security 6.3.x for RP-initiated logout; when implementing back-channel logout, choose a version that actually supports it and verify exact APIs, cookie names, and session registries.

### 10.2. OP Logout Does Not Necessarily Revoke Bearer Tokens

OIDC end-session normally targets the **SSO session**. Previously issued OAuth2 access tokens may remain valid at resource servers until expiry or until introspected/revoked depending on the OP. Refresh tokens also need their own lifecycle/revocation policy. If the product requires logout to immediately invalidate API credentials, implement token revocation or token introspection/denylists accordingly.

`id_token_hint` **is not** an access/refresh token revocation request. Never write in documentation that “OP logout revokes every JWT”.

### 10.3. Does Not Automatically Log Out All Devices

A session on browser A differs from mobile device B. RP-initiated logout does not automatically instruct the OP to terminate all of the user's sessions across all devices. Global sign-out requires policy, session indexing, token revocation, and notifications to the relevant RP(s).

### 10.4. The OP May Not Redirect Back to the RP

Per specification, the OP may prompt the user for confirmation; if `post_logout_redirect_uri` does not match a registered URI, the OP **must not** redirect to it. Therefore:
- An RP 302 redirect does not confirm logout at the OP.
- The browser not returning to `/signed-out` does not automatically mean local logout failed.
- During an OP outage, UX should state “Application session ended; identity provider logout not confirmed.”
- Never wait for the OP to redirect back before clearing state that the RP should have cleared **before** redirecting.

### 10.5. Logged Back In Without Entering a Password After Logout

The SSO source could be the OP session, an upstream SAML/IdP session, remember-me, a browser credential manager, or another device's session. Investigate:
1. Did local `WebSession.invalidate()` execute?
2. Did the browser actually navigate to the OP's `end_session_endpoint`?
3. Did the OP process/log out or just show a page?
4. Does the OP have an upstream authentication session still active?
5. Did the user re-enter the app and get auto-issued a new session per OP auth policy?

Seeing “immediately logged back in” **is not enough** to pinpoint whether the issue lies in the RP or the OP.

## 11. Security Considerations in Real Configurations

### CSRF

Keep `POST /logout` with a CSRF token for browser apps using `WebSession`/cookies. Never create a state-changing `GET /logout` endpoint. If tokens expire due to session timeout, design clean UX instead of disabling CSRF.

### Redirects and Open Redirects

`post_logout_redirect_uri` must be registered at the OP and controlled by the RP. Never forward raw `returnTo` or callbacks from user-supplied queries. When using `{baseUrl}` behind a reverse proxy, trust forwarded headers only from managed proxies, pinning the public host and HTTPS scheme.

### Tokens and Logs

The ID Token can appear in the OP redirect URI via `id_token_hint`; never log raw `Location` headers, full URLs, or request headers containing tokens. Also scrub `Authorization`, cookies, client secrets, and refresh tokens in gateways, APM, and support artifacts. Use HTTPS and limit referrer leakage and third-party assets on transition pages.

### Local Session Invalidation

Deleting the browser cookie does not prove the server session is invalidated. Test an old session with an independent HTTP client; with distributed Spring Session backends, test across multiple nodes. `WebSessionServerLogoutHandler` handles the current session and does not destroy other sessions without global logout design.

### SSO UX

Never claim “Signed out of all applications” when you only perform an RP-initiated redirect. Accurate wording is: “You have signed out of this application; sign-out status at the identity provider and linked applications depends on system configuration.”

## 12. Common Errors Table

| Error/Symptom | Cause | How to Investigate |
| --- | --- | --- |
| `POST /logout` → 403 | Missing/wrong CSRF token | Obtain token from current `WebSession`; never disable CSRF |
| Logout redirects only locally | Not an OIDC principal or OP lacks end-session | Check `openid` scope and metadata |
| OP rejects post-logout URI | Callback not registered or not an exact match | Register exact scheme/host/port/path |
| `{baseUrl}` becomes HTTP/localhost | Misconfigured reverse proxy forwarded headers | Configure trusted proxy, public HTTPS URL |
| OP reports invalid ID token | Hint for wrong client/issuer or expired context | Use the ID Token from the current OIDC login |
| Redirect contains token in logs | Access logging captures queries/`Location` | Redact token-bearing URLs |
| RP A logs out, RP B stays active | No OP notification or B lacks support | Design front/back-channel logout separately |
| JWT still works | Logout does not revoke access tokens | Token lifecycle/revocation |
| Browser cookie remains while session logged out | Client cookie cleanup differs from server invalidation | Try reusing old server session ID |
| Cookie named `SESSION` not `JSESSIONID` | WebFlux/Spring Session differs from Servlet | Check `WebSessionIdResolver`/cookie config |
| `/signed-out` redirects back to login | Callback protected by `authenticated` rule | Permit public access to callback |
| Logout via `fetch` doesn't navigate page | Fetch redirect is not top-level navigation | Use HTML form POST / full-page navigation |
| OP lacks `end_session_endpoint` | Standard unsupported or metadata missing | Do not guess URLs; consult provider docs |
| OP does not return to RP | OP requires confirmation, wrong URI, or network | Local logout may still have succeeded |
| Global logout doesn't work | Missing session registry/notifications/token revocation | Design explicit scope |
| Unit test `Location` passes, OP session remains | Only tested redirect builder | Run OP/browser E2E tests |

## 13. Implementation Checklist

1. OIDC client registered with OP using exact issuer, `openid` scope, and redirect URIs.
2. OP publishes `end_session_endpoint` or has a documented logout mechanism.
3. Client credentials managed via a secret manager, never hardcoded.
4. Login callback and post-logout redirect URI registered **separately** with exact matching.
5. Correct **WebFlux** security stack: `ServerHttpSecurity` + `SecurityWebFilterChain`.
6. Handler uses `ReactiveClientRegistrationRepository` and `OidcClientInitiatedServerLogoutSuccessHandler`.
7. `POST /logout` enforces CSRF token; no state-changing GET endpoints.
8. Local `SecurityContext` is cleared and `WebSession` is genuinely invalidated.
9. Callback is public, causing no login loop.
10. Public URL uses HTTPS and trusted host behind reverse proxies.
11. Raw ID Tokens, client secrets, cookies, and token-bearing `Location` headers are never logged.
12. Never use client-controlled redirect URLs.
13. Fallback behavior tested for non-OIDC users.
14. Both RP handler status/`Location` tests **and** E2E OP behavior tested.
15. Reusing old session IDs after logout tested and rejected.
16. If RP B logout is required, notification mechanism is supported, registered, and verified.
17. If global sign-out is required, session registry/multi-device/token revocation are designed.
18. UI reflects only the **proven logout scope**, without overstating guarantees.
19. Failure cases tested: OP downtime, session timeout, callback URI mismatch, reverse proxy redirects, blocked browser cookies.
20. Spring Security version confirmed for RP-initiated/back-channel support; never copy APIs from other version docs.

## 14. Self-Check Questions

**1. What is RP-Initiated Logout?**  
The RP requests the OP to log out the user via the browser, typically after clearing the local session.

**2. Which WebFlux class supports this flow?**  
`OidcClientInitiatedServerLogoutSuccessHandler`.

**3. Which repository does it use?**  
`ReactiveClientRegistrationRepository`, not the Servlet repository.

**4. Where does `end_session_endpoint` come from?**  
From the OIDC Provider's discovery metadata if the OP supports it.

**5. Is `id_token_hint` an access token?**  
No, it is the issued ID Token, used as a hint for the OP.

**6. Is `post_logout_redirect_uri` the login callback?**  
No. It is the URI the browser returns to after OP logout, registered separately.

**7. Does RP-initiated logout require POST?**  
The RP app normally uses `POST /logout` with CSRF; the OP endpoint is typically invoked via a GET redirect as a separate step.

**8. Why should the `/signed-out` callback be public?**  
Because the local session was destroyed before the OP redirected back.

**9. Does logging out of RP A automatically log out of RP B?**  
Not guaranteed; requires OP notifications and RP B support.

**10. Does ending the OP session automatically invalidate access tokens?**  
Not by default. Token revocation/expiry/introspection are separate mechanisms.

**11. What does a 302 redirect to the OP prove?**  
The RP instructed the browser to navigate to the OP; it does not prove the OP executed logout.

**12. If a user is immediately logged back in, is local logout definitely broken?**  
No. An SSO session at the OP or an upstream provider may still be active.

**13. Why should OIDC logout `Location` headers not be logged?**  
They can contain `id_token_hint` and sensitive data.

**14. How does back-channel logout differ?**  
The OP sends a Logout Token server-to-server to the RP; it requires its own endpoint, validation, and session mapping.

**15. What if the OP lacks an end-session endpoint?**  
Perform honest local logout and check provider docs for vendor-specific logout; never guess URLs.

**16. What do unit tests without a real OP verify?**  
Redirect URI construction, ID Token hint, callback URI, and fallback; they do not prove OP logout or federated propagation.

### Practice Exercises

1. Register an OIDC test client with separate login callback and post-logout URIs, and explain why they must not be confused.
2. Run the app against a test OP, use the `POST /logout` form, and inspect redirect metadata **without sharing real tokens**.
3. Try `POST /logout` without CSRF and explain the 403 error.
4. Try a mismatched post-logout URI and observe the OP rejecting the redirect, then fix the exact-match URI.
5. Test behind a reverse proxy with a public HTTPS host and verify `{baseUrl}` resolves accurately.
6. Record a test session ID in the lab, log out, and try reusing it from another client to verify the RP server rejects it.
7. Run RP A and RP B with the same OP, log out of A, observe B, and pinpoint where front/back-channel support is missing.
8. Substitute a non-OIDC principal in unit tests to observe the fallback.
9. Design a token revocation policy for a Bearer-token resource server.
10. Write a log-redaction checklist covering `id_token_hint`, `Authorization`, `Cookie`, and `Location`.
11. Propose UX for an unresponsive OP, distinguishing confirmed local logout from unconfirmed OP logout.
12. Describe how “sign out everywhere” requires adding a session registry and multi-device handling.

## 15. References

- [Spring Security — Reactive OIDC Logout](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html): local/RP-initiated/federated logout, reactive handler classes, back-channel limitations.
- [Spring Security — Reactive OAuth2 Login](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html): client registration, OIDC scope, `issuer-uri`, and callbacks.
- [Spring Security — Testing Reactive OAuth2/OIDC](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockOidcLogin()` in `WebTestClient`.
- [Spring Security API 6.2 — OidcClientInitiatedServerLogoutSuccessHandler](https://docs.spring.io/spring-security/site/docs/6.2.8/api/org/springframework/security/oauth2/client/oidc/web/server/logout/OidcClientInitiatedServerLogoutSuccessHandler.html): reactive repository, redirect URI template, fallback.
- [OpenID Connect RP-Initiated Logout 1.0 Final](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): `end_session_endpoint`, `id_token_hint`, `post_logout_redirect_uri`, `state`, and URI matching.
- [OpenID Connect Front-Channel Logout](https://openid.net/specs/openid-connect-frontchannel-1_0.html): OP notifications via browser.
- [OpenID Connect Back-Channel Logout](https://openid.net/specs/openid-connect-backchannel-1_0.html): server-to-server Logout Tokens.
- [OpenID Connect Discovery](https://openid.net/specs/openid-connect-discovery-1_0.html): OP discovery metadata.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): token revocation distinct from OIDC end-session.
- [Spring Security — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): CSRF for POST logout.

**Remember:** **RP-Initiated Logout = local logout at the app → redirect browser to the OP's `end_session_endpoint` with `id_token_hint` and registered callback**. Never equate **“redirected” = “OP logged out” = “all RPs logged out” = “all tokens revoked”**. Test each boundary and communicate the scope accurately.