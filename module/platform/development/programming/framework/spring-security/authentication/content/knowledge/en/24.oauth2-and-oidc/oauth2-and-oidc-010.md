# Local Logout, OIDC Logout, and Boundaries with Token Lifecycles

## 1. Objectives and Context

In a Spring Security application using OpenID Connect (OIDC) login, the **Sign out** button sounds like a single action. In reality, the application may hold its own session, the identity provider (OpenID Provider, **OP**) maintains a separate SSO session, and the OAuth 2.0 system issues tokens with independent lifetimes and revocation policies. Consequently, closing a session in one place does not automatically guarantee that access is gone everywhere else.

After this lesson, you should be able to:

1. Distinguish **local logout at the Relying Party (RP)**, **RP-Initiated Logout at the OP**, **OP-Initiated Back-Channel/Front-Channel Logout**, and **OAuth 2.0 token revocation**.
2. Accurately explain the impact of each operation on the RP session, browser cookies, OP SSO session, ID token, access token, and refresh token.
3. Configure local logout and OIDC RP-Initiated Logout with Spring Security Servlet; identify the corresponding APIs for Spring WebFlux.
4. Understand how an OP-signed logout token triggers RP back-channel logout, why `iss`, `aud`, `events`, and `sid`/`sub` must be verified, and why callbacks cannot be trusted merely for “coming from a familiar URL”.
5. Define explicit policies for access/refresh tokens upon logout, instead of assuming tokens expire immediately once cookies are deleted.
6. Test scenarios involving SSO, multiple devices, already-issued JWTs, refresh tokens, CSRF, gateways/reverse proxies, and multi-node session stores.

**Scope:** Spring Security + OAuth 2.0/OIDC. The Servlet demo uses Spring Boot 3.x and Java 17+. The WebFlux section shows separate reactive configuration; never mix `HttpSecurity` and `ServerHttpSecurity`. Practicing OIDC logout requires a real OP supporting OIDC Discovery and a logout endpoint; sample URLs in this lesson must be replaced with your test OP's configuration.

## 2. Five State Types That Must Be Distinguished

Consider someone logged into a task management app `https://tasks.example.org` via OP `https://id.example.org`. The browser currently holds session cookies for both parties. The RP may hold an OAuth 2.0 authorized client to call APIs; APIs may validate access tokens in multiple ways.

| Component | Who Owns / Controls It? | Purpose | Does RP Logout Auto-Delete It? |
| --- | --- | --- | --- |
| **RP local session** (e.g., `JSESSIONID` in Servlet, `WebSession` in WebFlux) | RP application and RP session store | Remembers `SecurityContext`, HTTP session data, and app login state | **Yes**, if logout handlers/session invalidation are properly configured |
| **OP SSO session** (often an OP-domain cookie) | OP | Enables SSO across multiple RPs without re-entering credentials | **No**; requires a logout protocol supported by the OP |
| **ID token** (OIDC) | Signed/issued by OP; consumed by RP | Proves authentication event and claims to the RP; usable as `id_token_hint` | Cannot “delete an already issued token” simply by destroying the local session; token is not an API access token |
| **Access token** (OAuth 2.0) | Issued by Authorization Server (AS); validated by Resource Server (RS) | Authorizes API access within `aud`/`scope`/permissions | **Not by default**; issued tokens may remain valid until expiry or invalidation via RS/AS mechanisms |
| **Refresh token** (OAuth 2.0) | Managed by AS and stored by RP/native app per architecture | Obtains new access tokens without re-prompting the user | **Not by default**; deleting a token from storage and revoking it at the AS are two distinct actions |

Some applications hold no server-side session, such as APIs validating only Bearer JWTs or SPAs storing tokens client-side. There, “local logout” may simply clear state/tokens from the client with **no HTTP session to invalidate**. Clearly document the architecture before promising what a logout button achieves.

### Differences Between RP, OP, AS, and RS

- **RP (Relying Party):** the application using OIDC to authenticate users; Spring Security `oauth2Login()` runs here.
- **OP (OpenID Provider):** authenticates users and issues ID tokens; the OP often also serves as the OAuth 2.0 Authorization Server.
- **AS (Authorization Server):** issues access/refresh tokens and may expose revocation/introspection endpoints.
- **RS (Resource Server):** the API receiving Bearer access tokens, validating them, and deciding access permissions.
- **Client registration:** the RP details registered at the OP, including `client_id`, redirect URIs, and optionally `post_logout_redirect_uri`.

A single system may combine multiple roles, yet **that never merges token and session lifecycle contracts into one**.

## 3. Four Operations Named “Logout” with Different Consequences

| Operation | Who Initiates? | Communication Path | Primary Outcome | What Is NOT Guaranteed |
| --- | --- | --- | --- | --- |
| **Local logout** | User at RP | Browser → RP `POST /logout` | RP clears security context and invalidates session per config | OP SSO session ends; issued tokens are revoked |
| **RP-Initiated OIDC Logout** | RP after user request | Browser → OP `end_session_endpoint`, optionally back to RP | OP is asked to end the SSO session; RP should have already run local logout | OP always accepts/completes; all clients and tokens immediately become invalid |
| **OP-Initiated Front-Channel Logout** | OP | OP → browser → each RP | RP receives logout signal via the user agent | Every RP receives the signal (browsers may block third-party cookies/iframes) |
| **OP-Initiated Back-Channel Logout** | OP | Server-to-server `POST` delivering logout token | RP validates the message and invalidates matching sessions | Access JWTs at RS become invalid immediately |
| **OAuth Token Revocation (RFC 7009)** | OAuth client / authorized party | Client → AS revocation endpoint | AS revokes tokens/grants per its own rules | Offline-verifying RS sees the revocation immediately |

A business logout flow can **combine** multiple rows above: for instance, the RP clears the local session, redirects the user to the OP to end SSO, and the backend proactively requests revocation for any remaining refresh tokens. However, no single Spring Security `logout()` call automatically performs all of those steps across every architecture.

### Concrete Illustration of Consequences

Suppose before logout:

```text
Browser:
  [Active RP session] [Active OP SSO session]

RP/backend:
  [access token A, 5 minutes left] [refresh token R]

Resource server:
  [accepts access token A if signature/iss/aud/exp are valid]
```

If the user logs out only from the RP:

```text
RP session:           DELETED
OP SSO session:       MAY STILL REMAIN
Access token A:       MAY STILL BE USABLE until exp
Refresh token R:      DEPENDS on storage/revocation policy; not automatically revoked
```

If the user immediately clicks “Sign in with OIDC” again, the OP may still hold an SSO session and issue a new authorization code without asking for a password. **This does not mean local logout failed**; it reflects that the OP session remains active.

Conversely, if OP logout completed yet an access JWT is verified offline by an RS and remains unexpired, the RS may still accept that JWT until expiry unless revocation state is implemented. **This does not mean OIDC logout failed to happen**; session logout and token validation are two separate contracts.

## 4. Local Logout in Spring Security: What Exactly Gets Cleared?

### 4.1. Servlet / Spring MVC

Spring Security provides a default `/logout` endpoint when a Security filter chain is enabled. With default CSRF protection:

- `GET /logout` is typically a logout confirmation page; it is **not** the recommended way to mutate session state.
- `POST /logout` with a valid CSRF token runs configured `LogoutHandler` instances. Defaults usually include invalidating `HttpSession`, clearing `SecurityContext`, handling remember-me/CSRF tokens, and publishing logout events per enabled features.
- After local logout succeeds, `LogoutSuccessHandler` determines the redirect or response. Redirecting to the OP is an **additional** step when implementing OIDC RP-Initiated Logout.

```text
Browser POST /logout (+ CSRF token)
        |
        v
Spring Security LogoutFilter
        |
        +--> local LogoutHandler(s)
        |      - invalidate HttpSession
        |      - clear SecurityContext
        |      - related cleanup per configuration
        |
        +--> LogoutSuccessHandler
               - local redirect, OR
               - redirect to OIDC OP end_session_endpoint
```

**Never delete a cookie manually and conclude you have logged out.** Deleting a browser cookie removes the client-side session identifier, yet the server-side session and associated records persist until invalidated or expired. Conversely, server-side session invalidation is the real security boundary even if a browser keeps an obsolete cookie.

The browser must send the logout request following CSRF policy; avoid turning `POST /logout` into GET just to attach it to an anchor link. Attackers can abuse logout CSRF to force unwanted logouts. In Thymeleaf/Spring MVC apps with Spring Security form integration, a logout button template looks like:

```html
<form th:action="@{/logout}" method="post">
  <button type="submit">Sign out</button>
</form>
```

This is a **Thymeleaf template snippet**, not static HTML: form processing must emit the matching CSRF token. If the frontend builds forms or requests manually, send the token in the field/header expected by the configured `CsrfTokenRepository`. Never disable CSRF app-wide just to make a logout button work.

### 4.2. WebFlux / Spring Security Reactive

In WebFlux, Spring Security uses `LogoutWebFilter`, `ServerLogoutHandler`, `ServerLogoutSuccessHandler`, and `ServerSecurityContextRepository`. Do not use Servlet's `SecurityContextLogoutHandler` in reactive apps.

Across Spring Security versions, reactive local logout clears security data via default handlers, yet if **invalidating the entire WebSession** is required, explicitly verify and configure `WebSessionServerLogoutHandler` for your version. The example in section 7 combines `SecurityContextServerLogoutHandler` and `WebSessionServerLogoutHandler`. Never assume calling an API with a similar name to Servlet has the exact same effect on the session store.

### 4.3. Does Local Logout Delete the OAuth2 Authorized Client?

An RP using `oauth2Login` may store authorized clients (access/refresh tokens) via `OAuth2AuthorizedClientService` or `OAuth2AuthorizedClientRepository`, depending on config (session, JDBC, custom repository, etc.). When the session is invalidated, tokens stored **only inside that session** become inaccessible from the RP. If tokens reside in a database/Redis or shared storage, evaluate whether authorized-client records must also be deleted upon logout.

Two concepts must be separated:

1. **Local removal**: the app deletes its local token copy or authorized-client record from storage; tokens already issued at the AS are not necessarily revoked.
2. **Revocation at the AS**: the app calls the AS's proper endpoint/protocol requesting the token be invalidated; the RS may need an appropriate verification mechanism to observe it.

A custom `LogoutHandler` can perform app-owned cleanup, yet deleting a local record must never be mistaken for a revocation call. Ordering cleanup before or after OP logout requires considering **data needed to call revocation or supply `id_token_hint`**; do not delete needed information only to discover it is missing mid-flow.

## 5. OIDC RP-Initiated Logout: Asking the OP to End the SSO Session

OIDC [RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html) defines how an RP requests that the OP log out a user. It is a **session coordination protocol**, not OAuth token revocation.

### 5.1. Primary Flow

```text
User              Browser                  RP (Spring Security)            OP
 | Click Logout      |                                |                       |
 |------------------>|  POST /logout + CSRF          |                       |
 |                   |------------------------------->|                       |
 |                   |     Local session invalidated  |                       |
 |                   |<------- 302 redirect ----------|                       |
 |                   |       to end_session_endpoint                          |
 |                   |------------------------------------------------------->|
 |                   |                                  OP validates request  |
 |                   |                                  and ends OP session   |
 |                   |<--------------- redirect to registered URI ------------|
 |                   |------------------------------->| /signed-out           |
 |                   |<------------- response ---------|                       |
```

In practice, the OP may ask the user for confirmation, may not support protocol logout, or network/browser interruptions may occur before returning to the RP. Therefore, the RP should design around **local logout having already occurred** even if OP logout does not finish.

### 5.2. Discovery and Standard Parameters

The RP typically finds the OP logout URL at `end_session_endpoint` in OIDC Discovery metadata, if supported by the OP. Key parameters:

| Parameter | Role | Notes |
| --- | --- | --- |
| `id_token_hint` | ID token issued by OP to the RP, **recommended** to help OP identify session and client | Not an access token or refresh token; avoid logging the full value |
| `post_logout_redirect_uri` | Where OP sends the browser after handling logout | Must match a URI registered with the OP; never take arbitrary redirects from client query params |
| `state` | Opaque value used by RP to correlate response/redirect and preserve flow consistency | Generated/checked per app design; never used as a credential |
| `client_id` | Can identify the client in cases permitted by spec | OP must verify client matches `id_token_hint` if both are present |
| `logout_hint` | Hint about identity or session for the OP, provider-dependent | Not accepted by every OP by default |

**Illustrative URL** example (actual token values omitted):

```text
GET https://id.example.org/connect/endsession
    ?id_token_hint=(issued ID token)
    &post_logout_redirect_uri=https%3A%2F%2Ftasks.example.org%2Fsigned-out
    &state=(opaque value)
```

Never build URLs through unchecked string concatenation or send tokens through arbitrary URLs. Spring Security's standard handler uses `ClientRegistration` and configured metadata to construct the redirect. Redirect endpoints and schemes should use HTTPS in production; external reverse-proxy hostnames must match registered URIs.

**OP logout does not equal global logout across all RPs.** An OP may notify other RPs via front-channel/back-channel/session management, or it may only terminate the OP session. Coverage depends on OP features, registration, browsers, and each RP's implementation.

### 5.3. Ordering Local Logout and OIDC Logout

The OIDC spec allows the RP to choose whether to clear the local session before redirecting to the OP or wait for an OP logout notification. In Spring Security, `OidcClientInitiatedLogoutSuccessHandler` (Servlet) and `OidcClientInitiatedServerLogoutSuccessHandler` (WebFlux) are **local logout success handlers**, meaning they run after local logout handlers. That is why the proper configuration is `logout(...logoutSuccessHandler(...))`, rather than putting redirect logic in a controller and bypassing the logout filter.

If the OP lacks an `end_session_endpoint` or does not support RP-Initiated Logout, design an appropriate **local logout fallback**. Never promise OP redirects succeed in every environment.

### 5.4. Frontend Must Perform a Top-Level Browser Navigation

If the frontend calls `fetch("/logout", {method: "POST", ...})`, JavaScript's HTTP client usually follows redirects in the background; **the browser does not navigate the top-level page** to the OP. For redirect-based RP-Initiated Logout, the logout button should use a top-level form POST/navigation, or a controlled frontend mechanism so the browser actually visits OP logout.

Never construct a logout URL containing tokens and return it as JSON for the client to log/debug/copy. Avoid exposing `id_token_hint` in analytics, referrers, server logs, or error pages.

## 6. Complete Spring Boot Servlet Example: Local + OIDC RP-Initiated Logout

This example uses **Spring Boot 3.x + Spring Security 6.x + Java 17+**, following a browser/web app model with server-side sessions. A real OP and properly registered client registration are required; `id.example.org` is illustrative and not a live endpoint. The Java classes below compile in a project with the appropriate starters.

### 6.1. Dependencies for a Generated Spring Boot Gradle Project

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

Do not mix `spring-boot-starter-web` and `spring-boot-starter-webflux` just to share snippets; choose either the servlet or reactive stack per your application architecture.

### 6.2. Provider Configuration (Replace with Real Values)

Place in `src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: web-application
            client-secret: "${OIDC_CLIENT_SECRET}"
            scope: openid,profile,email
        provider:
          corp:
            issuer-uri: "${OIDC_ISSUER_URI}"
```

Provide real `OIDC_CLIENT_SECRET` and `OIDC_ISSUER_URI` environment variables; never commit client secrets. The OP must expose Discovery metadata for the issuer and, for RP-Initiated Logout, an appropriate `end_session_endpoint`. At the OP, register at least:

- Login redirect URI: `https://tasks.example.org/login/oauth2/code/corp`.
- Post-logout redirect URI: `https://tasks.example.org/signed-out`.

`corp` is the registration ID, kept consistent across config and URLs. Locally, `http://localhost:8080` and exact redirect URIs may be used if permitted by the OP. Login and post-logout redirect URIs serve **two distinct functions** and must not be mixed.

### 6.3. Java 17: Security Chain and Controller

Save as `src/main/java/demo/logout/OidcLogoutDemoApplication.java`:

```java
package demo.logout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class OidcLogoutDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(OidcLogoutDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        OidcClientInitiatedLogoutSuccessHandler oidcLogout =
                new OidcClientInitiatedLogoutSuccessHandler(registrations);

        // Must match the post-logout redirect URI registered at the OP.
        oidcLogout.setPostLogoutRedirectUri("{baseUrl}/signed-out");

        http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/signed-out", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .logout(logout -> logout
                        .logoutSuccessHandler(oidcLogout));

        // Keep default CSRF protection.
        return http.build();
    }

    @RestController
    static class Pages {

        @GetMapping("/")
        String home() {
            return "Home. Open /me to log in, then GET /logout to see "
                    + "the logout confirmation form.";
        }

        @GetMapping("/me")
        String me(@AuthenticationPrincipal OidcUser user) {
            return "OIDC subject: " + user.getSubject();
        }

        @GetMapping("/signed-out")
        String signedOut() {
            return "Returned from logout flow.";
        }
    }
}
```

The code **does not define `/logout` itself** because Spring Security already provides the logout endpoint/filter. Trying to add a `@PostMapping("/logout")` controller without understanding the filter chain easily skips local cleanup or CSRF. This code does not revoke access/refresh tokens automatically.

### 6.4. Running and Observing the Expected Results

From a project with the Spring Boot Gradle plugin and Java 17+, run:

```bash
./gradlew bootRun
```

On Windows use `gradlew.bat bootRun`. Visit `http://localhost:8080/me` (or your configured URL) in a browser and complete OIDC login. Once signed in:

1. Open `GET /logout` to view Spring Security's generated confirmation page, or submit a valid POST form with a CSRF token.
2. Observe the `POST /logout` HTTP request to the RP. Spring Security invalidates the local session per config.
3. Observe the redirect to the OP's `end_session_endpoint`. If the OP supports it and accepts the ID token/redirect URI, the OP performs SSO logout.
4. The OP may redirect back to `/signed-out`. That endpoint only shows a navigation message; **it does not prove** that all tokens and all other RPs have been invalidated.
5. Revisit `/me`: a new OIDC login at the RP must be required. Whether the OP prompts for a password again depends on the OP's session/SSO policy.

There is no fixed stdout from the live OIDC example because `sub`, hosts, and user/OP steps depend on the environment. Inspect status codes, `Location` headers, and cookies in browser DevTools, while never logging raw ID tokens or client secrets.

### 6.5. Local-Only Logout in the Same Application

If business requirements call only for **closing the RP session**, omit `.logoutSuccessHandler(oidcLogout)`, letting the default handler redirect to the RP's login/logout success page. Then the RP session is closed while the OP may keep its SSO session. This is an intentional choice in many systems supporting “switch account” or “sign out from this app”; the UI should clearly communicate the scope.

## 7. Equivalent Configuration in WebFlux Reactive

Spring WebFlux uses `SecurityWebFilterChain` and `ServerHttpSecurity` instead of Servlet's `SecurityFilterChain`/`HttpSecurity`. The example below is a **standalone configuration class** for a Boot 3.x project using `spring-boot-starter-webflux`, `spring-boot-starter-security`, and `spring-boot-starter-oauth2-client` with a valid OIDC client registration.

Save as `src/main/java/demo/logout/ReactiveOidcLogoutConfig.java` in a reactive app that already has a main application class:

```java
package demo.logout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.oidc.web.server.logout.OidcClientInitiatedServerLogoutSuccessHandler;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;

@Configuration
@EnableWebFluxSecurity
public class ReactiveOidcLogoutConfig {

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            ReactiveClientRegistrationRepository registrations) {

        OidcClientInitiatedServerLogoutSuccessHandler oidc =
                new OidcClientInitiatedServerLogoutSuccessHandler(
                        registrations);
        oidc.setPostLogoutRedirectUri("{baseUrl}/signed-out");

        // Clear security context and invalidate WebSession as specifically required.
        DelegatingServerLogoutHandler local =
                new DelegatingServerLogoutHandler(
                        new SecurityContextServerLogoutHandler(),
                        new WebSessionServerLogoutHandler());

        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/", "/signed-out").permitAll()
                        .anyExchange().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .logout(logout -> logout
                        .logoutHandler(local)
                        .logoutSuccessHandler(oidc))
                .build();
    }
}
```

Here `DelegatingServerLogoutHandler` combines two local handlers into a single logout handler; afterward, the OIDC logout success handler builds the redirect to the OP. This does not replace cleanup policies for database-stored tokens and does not automatically call a revocation endpoint. Do not apply both the Servlet config from section 6 and the WebFlux config here in the same application expecting the two chains to interact.

**CSRF with WebFlux:** by default `LogoutWebFilter` protects logout with HTTP POST and CSRF; the frontend must submit a valid token. Since the OIDC logout handler returns a redirect, the browser must perform a corresponding navigation (such as a top-level HTML form POST). Avoid GET logout merely for “link convenience”.

**Version note:** OIDC back-channel APIs and handler/session-registry details vary across Spring Security releases; verify the exact APIs below for your version. The local + RP-initiated code above relies on APIs supported in Spring Security 6.x.

## 8. OP-Initiated Logout: When the OP Logs Out the User First

A user may sign out directly at the OP, or an administrator may revoke their login session. If the RP receives no signal, it can retain its local session and let the user keep using the RP until the local session ends or RP policies detect the change.

### 8.1. Front-Channel Logout

The OP uses the **user agent** to send logout notifications/URLs to one or more RPs, e.g., via navigation or iframes per the registered profile. This approach can be blocked by SameSite/third-party cookie restrictions, iframe policies, early browser closure, or network drops. Thus, front-channel should not be relied upon as an absolute guarantee for mandatory logout across all sessions.

### 8.2. Back-Channel Logout

Per [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html), the OP sends an HTTP POST **directly from server to RP**, carrying a `logout_token` parameter that is a signed JWT. The user's browser **does not need an RP tab open**.

```text
User/Admin                  OP                       RP
    | Logout at OP            |                        |
    |------------------------>|                        |
    |                     End OP session               |
    |                         |                        |
    |                         | POST back_channel URI  |
    |                         | logout_token=<JWT>     |
    |                         |----------------------->|
    |                         |              Verify token:
    |                         |              signature, iss, aud,
    |                         |              iat/exp/jti, events,
    |                         |              sid/sub, no nonce
    |                         |              -> find/invalidate RP session
    |                         |<-------------- HTTP 200/400 ... |
```

**A logout token is not an ID token, access token, or refresh token.** It is a signed event message with its own format; you cannot just decode the JWT and trust `sub`. Mandatory/key checks include:

- `iss` matches the registered OP, `aud` contains the RP's client ID, and signature/algorithm are valid; reject `alg=none`.
- `iat`, `exp`, and `jti` to evaluate freshness and prevent replay per design; reject expired messages.
- `events` must contain the standard `http://schemas.openid.net/event/backchannel-logout` key with an object value.
- **At least one** of `sub` or `sid` must be present; `nonce` **must not appear** in a logout token.
- `sid` identifies a specific OP session if present; `sub` alone may affect the user's sessions at the RP for that client/issuer per spec policy.
- The session registry must distinguish **issuer + audience/client + subject/session id**. Never wipe every user sharing an email across all tenants upon receiving a logout token.

If no matching session is found because the user already logged out earlier, logout handling may be treated as successful; ensure idempotency on retries. Invalid tokens must be rejected; never invalidate sessions just because a client hit the right endpoint.

### 8.3. Spring Security Back-Channel Logout Integration

Depending on the Spring Security version, WebFlux can register:

```java
// Excerpt inside reactive SecurityWebFilterChain configuration.
// Import the APIs corresponding to your Spring Security version.
http.oauth2Login(Customizer.withDefaults());
http.oidcLogout(oidc -> oidc
        .backChannel(Customizer.withDefaults()));
```

Spring Security documentation describes a default endpoint like:

```text
POST /logout/connect/back-channel/{registrationId}
Content-Type: application/x-www-form-urlencoded

logout_token=<OP's JWT>
```

Depending on the version's back-channel configuration, you may need to publish an `OidcBackChannelServerLogoutHandler` bean as documented by Spring Security. For example, in the reactive API shown in Spring Security docs:

```java
// Bean excerpt inside a @Configuration with the proper class imported.
@Bean
OidcBackChannelServerLogoutHandler oidcLogoutHandler() {
    return new OidcBackChannelServerLogoutHandler();
}
```

**This is an illustrative configuration snippet, not a runnable full project**: to use it, verify dependencies, Spring Security version, endpoint registered at the OP, session storage mechanism, and actual session cookie name. `oidcLogout` requires `oauth2Login`. Spring Security documentation notes that back-channel logout correlation commonly assumes `JSESSIONID`, whereas Spring Session may use `SESSION`; a name mismatch will prevent invalidation from working as expected. In multi-node deployments, use an appropriate shared session registry/store rather than assuming an in-memory registry suffices.

For Servlet, the corresponding configuration sits on `HttpSecurity.oidcLogout(...backChannel(...))`, not WebFlux classes. Per Spring Security Servlet docs, multi-node setups also require attention to `HttpSessionEventPublisher` and session registry synchronization.

**Never disable CSRF app-wide to “allow OP callbacks”.** Use the proper back-channel integration that validates the logout token and configure endpoint rules specifically if required by your framework/version. Never write a `POST /logout-by-email` endpoint that takes an email and invalidates sessions without verifying an OP-signed message.

## 9. Token Lifecycles: Why Clearing a Session Does Not Invalidate Access Tokens

OAuth 2.0 separates the lifecycles of **user sessions**, **authorization grants**, and **tokens**. Tokens can be used across independent systems and are not directly affected by the RP's session cookie.

### 9.1. Access Tokens

- **Opaque access token:** the RS can query the AS via Token Introspection (RFC 7662) to check whether the token is still active; RS latency and caching affect when revocations take effect.
- **Self-contained JWT access token:** the RS can verify signature, `iss`, `aud`, `exp`, and `nbf`/scopes completely offline. In that case, **AS token revocation sends no automatic signal to the RS**, and the RS may keep accepting the JWT until `exp` without a denylist, introspection, or other coordination.
- **Short-lived tokens:** shrink the exposure window, yet do not replace session/refresh-token revocation when compromised. Balance lifetime against UX and security needs.
- **Once a token is copied:** deleting the token from the browser or authorized-client store **does not revoke copies** held by third parties.

An API running only `oauth2ResourceServer().jwt()` to verify Bearer tokens **has no default user login session to log out in the OIDC browser sense**. Calling `POST /logout` on a browser session (if one exists) does not invalidate already-issued JWTs. A “sign out all devices” requirement calls for AS revocation, token policies, and session/grant management aligned with the system model.

### 9.2. Refresh Tokens

A refresh token lets a client obtain new access tokens. If a user logs out while the refresh token remains unrevoked, any client holding it can keep exchanging it for tokens until the AS rejects it due to expiry, rotation, inactivity, revocation, or grant policy.

- **Revoking refresh tokens:** typically the priority when a client ends delegation normally or detects compromise, subject to AS endpoint support and policy.
- **Refresh token rotation:** the AS issues a new refresh token upon exchange; the old token becomes unusable, though family revocation/reuse detection semantics vary by AS. Never assume rotation happens automatically on every provider.
- **Offline access:** refresh tokens issued with `offline_access` may have a lifecycle independent of the SSO session; the OIDC Back-Channel Logout spec even distinguishes policies for offline vs. non-offline refresh tokens. Therefore, **never claim OP logout always revokes every refresh token**.
- **Local removal vs. revocation:** deleting only the local copy stops the app from using the token; if stolen earlier, it may still be valid at the AS.

### 9.3. ID Tokens

An ID token is proof of an **OIDC authentication event** intended for the RP, not an “all-access pass” to every API. Local logout cannot erase the signature on an already-issued ID token. ID tokens also carry their own `exp`; an OP may accept an old ID token as `id_token_hint` per OIDC logout rules even after expiration, though that is the OP's decision and never makes ID tokens usable as access tokens.

### 9.4. Logout Tokens

A back-channel logout token is an **event message** signed by the OP instructing the RP to terminate related sessions. It is not an API access credential and must never be stored or placed in `Authorization: Bearer` as an access token. Accepting an invalid `logout_token` lets attackers force logouts on other users or tenants.

## 10. OAuth 2.0 Token Revocation (RFC 7009)

[RFC 7009](https://www.rfc-editor.org/rfc/rfc7009) defines a revocation endpoint at the AS. An authorized client submits the token to revoke, optionally with `token_type_hint`, and authenticates the client using the method required by the AS.

### 10.1. Sample HTTP Request

```http
POST /oauth2/revoke HTTP/1.1
Host: id.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-credentials>

token=<refresh-token-value>&token_type_hint=refresh_token
```

This is a **protocol template**; the exact endpoint path and client authentication method are dictated by the AS/Discovery/provider spec. Never copy `Basic <client-credentials>` into a browser or public SPA: client secrets must remain protected in a confidential backend client. Never print real tokens into logs, URL queries, analytics, or shell history.

`token_type_hint` is only a hint, not proof of the token's type. The AS may invalidate related tokens/grants per its own policy. RFC 7009 states that **200** may be returned both when a token is revoked and when it was invalid, so **HTTP 200 does not prove a token ever existed**. Client authentication failures, unsupported token types, or network errors must be handled per contract.

### 10.2. What Does Revocation Change?

Suppose the AS revokes refresh token `R`; previously issued access tokens `A` may still be accepted by the RS. In that situation:

```text
Refresh R:  cannot be used to obtain new access tokens (if AS revoked it)
Access A:   may still be accepted by RS until exp/cache invalidation
RP cookie:  may have been cleared independently
OP cookie:  may still remain independently
```

Achieving “stop all access immediately” requires an end-to-end definition: the AS must track revocation state, the RS must check/receive that state with bounded caching, and all related sessions/clients must be accurately identified. A single browser redirect can never deliver that guarantee.

### 10.3. Safe Workflow in a BFF / Confidential Web Client

A **Backend For Frontend (BFF)** holding refresh tokens server-side can implement an ordered logout flow:

1. Receive a logout request that passed the RP's CSRF/authentication checks.
2. Identify the session and associated authorized client using the authenticated identity (never accept arbitrary tokens/client IDs from browser payloads).
3. When policy requires, send a backend revocation request to the AS per provider specs, handling errors/timeouts cleanly.
4. Delete backend-owned token/authorized-client records, invalidate the RP session, and clear cookies per policy.
5. If ending SSO is desired, redirect the browser to the OP logout endpoint with valid parameters and a registered return URL.

Exact ordering depends on policy: some systems keep the ID token long enough to build the redirect; some ensure **local logout succeeds even if AS revocation temporarily fails**. Define outcomes, retries, and telemetry per step so users are never trapped in an active session because an external endpoint failed.

## 11. “Log Out Everywhere” Is a Product Requirement That Needs a Contract

“Sign out”, “Sign out of this app”, “Sign out of all devices”, and “Revoke this app's access” are not equivalent.

| User Request | Minimum Actions Required | Resources Potentially Outside Direct Control |
| --- | --- | --- |
| Sign out of this app in current tab/browser | Invalidate RP local session, clean scoped client state | OP still holds SSO session; tokens issued elsewhere |
| Also sign out of OP / SSO | Local logout + RP-Initiated OP logout; verify provider support | Whether other RPs receive notification; offline tokens |
| Sign out all sessions of the same RP | Enumerate and invalidate user's sessions in the right session store/registry | OP and other applications remain active |
| Terminate token-issuing delegation | Revoke grant/refresh token at AS per AS capabilities | Already-issued, unexpired access JWTs |
| Lock account after an incident | Disable account/credentials, revoke sessions/grants/tokens per policy, update RS | Cache/propagation delays and systems outside trust domain |

An OP may offer multi-device session management or global logout APIs, yet **the RP-Initiated Logout standard alone does not guarantee that**. Logging out of RP A does not mean RP B cleared its session unless the OP notifies RP B and RP B processes it successfully.

### Two Devices and One User

If Alice is signed in on a laptop and a phone, logging out on the laptop typically invalidates only the laptop's RP session. A back-channel logout token containing `sid` can target a specific session; a message containing only `sub` may instruct the RP to invalidate all sessions for that subject under that client/issuer per supported mechanisms. Never group sessions by email because emails can change or collide across issuers.

## 12. Browser / SPA / Mobile / Service-to-Service Architectures

### 12.1. Web App with Server-Side Sessions

Servlet/Spring MVC `oauth2Login` typically uses server-side sessions to store authentication and OAuth2 authorized clients depending on repository. Local logout closes the RP session; RP-Initiated OIDC logout follows a browser redirect; token revocation is an additional policy.

### 12.2. SPA Using OIDC Authorization Code + PKCE

SPAs usually hold login state in the browser and manage tokens per library/architecture design. On logout:

- Clear state/tokens from the exact storage owned by the app so the UI stops displaying stale user info.
- Use the OIDC client library's logout mechanism to navigate to the OP and handle `state`/callbacks safely when supported by the provider.
- Never embed a client secret in JS or call revocation endpoints requiring confidential client credentials from the browser.
- Be cautious with refresh tokens in the browser, XSS, concurrent tabs, and lingering SSO state at the OP.
- Never claim API Bearer access tokens became invalid simply because `localStorage`/`sessionStorage` was cleared.

To reduce token exposure in the browser, consider the BFF pattern keeping tokens on the backend and giving the browser a same-site session; BFF logout will need cleanup on both the server and provider per policy.

### 12.3. Mobile / Native App

Logout typically includes clearing credentials from secure storage, requesting OP logout via the provider-supported system browser/session mechanism, and revoking tokens when needed. Session cookies inside the system browser may persist, automatically signing the account back in next time. Do not mechanically apply Spring MVC `JSESSIONID` patterns to native mobile apps.

### 12.4. Machine-to-Machine / Client Credentials

A service using the client credentials grant normally **has no end-user OP SSO session** to log out from. Stop the client, clear local tokens, revoke tokens if supported by the AS, rotate/revoke client credentials, and block new token issuance per policy. Calling OIDC `end_session_endpoint` for a client credentials token is not an appropriate mechanism.

### 12.5. Purely Stateless Resource Server

If a service only processes `Authorization: Bearer <access_token>` and validates JWTs, it cannot destroy a cookie/session that does not exist. Stopping an access token before `exp` requires AS coordination, denylists/session versions, introspection, or equivalent techniques. Avoid exposing a fake `/logout` endpoint that merely clears `SecurityContextHolder` for the current request and claims “token revoked”.

## 13. Reverse Proxies, Redirect URIs, and Cookies: Common Pitfalls

### 13.1. `{baseUrl}` Behind a Gateway

Spring Security's logout success handler can use `{baseUrl}` for `post_logout_redirect_uri`. If the app runs internally on `http://app:8080` while users reach `https://tasks.example.org`, the generated URI can be wrong if proxy and app misconfigure forwarded headers. Ensure you:

- Register the exact public URI at the OP and compare against the actual HTTP `Location`.
- Trust `Forwarded` / `X-Forwarded-*` only from controlled reverse proxies; strip untrusted headers at ingress.
- Never let clients pick arbitrary logout targets via an un-allowlisted `returnUrl`.

### 13.2. Cookie Domain, SameSite, Secure, and Path

The RP cookie (`JSESSIONID`/`SESSION`) and OP SSO cookie typically belong to **different domains**. The RP cannot arbitrarily delete OP-domain cookies; browsers only honor cookie deletions from the matching domain/scope. Verify `Secure` and `SameSite` so callback/logout flows comply with HTTPS and browser policies, without weakening security attributes just to paper over an un-isolated bug.

### 13.3. Cookie Deletion Does Not Replace Server Invalidation

The logout handler must terminate the session inside the session store, not merely return `Set-Cookie: JSESSIONID=; Max-Age=0`. In Redis/clustered sessions, delete the exact session key and associated session indices; if caching is used, verify replication and TTLs.

### 13.4. Back-Channel Across Multi-Node Infrastructure

Back-channel requests generally do not pass through the browser and **do not carry the user's RP cookie**. The RP needs a session registry to locate matching local sessions by OP `sid`/`sub`/`iss`/`aud`. If the registry lives in each node's local memory and logout hits a different node, sessions will remain active. Use a shared registry/store, eviction, session invalidation events, and concurrency/replay tests.

## 14. Common Mistakes and Fixes

| Symptom | Possible Cause | How to Diagnose / Fix |
| --- | --- | --- |
| Clicking logout then visiting `/me` skips password prompt | Local logout succeeded yet OP SSO session remains | Check redirect to `end_session_endpoint`, registered post-logout URL, and OP policy; do not assume RP session stayed alive |
| After logout, API still accepts old Bearer JWT | JWT is unexpired, RS validates offline, no revocation/denylist | Evaluate AS/RS policy, token exp, caching; design end-to-end revocation semantics |
| `GET /logout` only shows a confirmation page | Default CSRF requires POST to log out | Use a form POST with a CSRF token; never disable CSRF to skip confirmation |
| SPA calls fetch logout, OP never appears | Redirect happened inside fetch instead of top-level navigation | Use a form or navigation flow compatible with your OIDC client library |
| OP reports invalid redirect URI | `post_logout_redirect_uri` differs from registered URI, wrong scheme/host/path | Check exact public URI, proxy headers, and provider registration |
| After OP logout, session remains at another RP | Other RP did not receive/handle front/back-channel notification | Check OP/RP support, back-channel endpoint, and session registry |
| Back-channel receives request yet fails to clear session | Token rejected, wrong client/issuer, cookie name or registry mismatch | Inspect validation outcome, `sid` correlation, `JSESSIONID`/`SESSION`, multi-node setup |
| Logging out on one device clears too many sessions | Mapping by username/email instead of issuer + client + `sid` | Separate single-session vs. all-session policies; use standard identity registry |
| Refresh token still exchanges after logout | Only RP cookie deleted; AS did not revoke refresh token | Check revocation support, offline access, and refresh token policy |
| Token revocation returns 200 yet JWT still works | RFC 7009 allows 200 even for invalid tokens; RS unaware of revocation | Test directly against RS, exp/introspection/cache instead of relying on HTTP 200 |
| Logout fails when OP is temporarily down | App synchronously depends on OP | Ensure local session is terminated, with fallback and scoped warning logs |
| User loses session yet tokens remain in DB | Authorized client stored outside session | Implement repository cleanup and call AS revocation per policy |
| Front-channel logout works intermittently | Browser blocks iframes/third-party cookies/closed tabs | Prefer back-channel when supported by OP/RP; test SameSite and browsers |

## 15. Repeatable Tests and PASS Criteria

Do not test only that an HTTP redirect occurs; observe **each state layer**. The test suite can run in an integration environment with a real OP or a test provider supporting matching logout/revocation features.

| # | Scenario | Signal to Assert |
| --- | --- | --- |
| 1 | User signs in with OIDC, calls protected endpoint | RP creates valid session; only authenticated users gain access |
| 2 | Valid `POST /logout` in local-only mode | RP session invalidated; protected endpoint requires login; OP SSO may persist |
| 3 | `GET /logout` or POST missing CSRF | Does not mutate session beyond CSRF policy |
| 4 | RP-Initiated logout with OP supporting end-session | RP local logout succeeds; browser visits OP logout; returns to registered URI |
| 5 | OP does not support or rejects end-session | RP does not keep logged-out session; clear fallback/reporting, never claims global SSO closed |
| 6 | JWT access token issued before logout | Call RS before/after logout; verify acceptance matches `exp`/revocation policy |
| 7 | Revoke refresh token at AS | Refresh request with old token rejected per AS policy, even after local session loss |
| 8 | OP-initiated logout via back-channel | Valid logout token leads to exact local session invalidation |
| 9 | Back-channel logout token with bad signature/issuer/audience/exp/events or containing nonce | RP rejects, **does not destroy valid sessions** |
| 10 | Two sessions for same user with different `sid` | `sid`-targeted logout affects only matching session, not other devices |
| 11 | Multiple tenants/issuers sharing `sub` or email | Does not mistakenly invalidate sessions of another issuer/client |
| 12 | Multi-node and Spring Session | Back-channel hitting any node invalidates the matching session |
| 13 | Re-login after RP local logout | If OP session remains, SSO may issue new login; if OP logout succeeded, OP enforces its policy |
| 14 | Frontend logout via fetch vs. top-level form | Form/navigation takes browser to OP as expected; plain fetch does not change page |
| 15 | Pure JWT API holding no session | Never claim “JWT invalidated upon logout” unless RS implements an actual mechanism |

For Servlet apps, `MockMvc` and `spring-security-test` can verify POST/CSRF behavior, yet mock logout tests do not prove a real OP ended SSO or a real RS stopped accepting JWTs. For WebFlux, use `WebTestClient` and matching integration tests. Test both browser redirects and server-to-server back-channel paths on realistic deployment infrastructure.

### Self-Check Exercise: Demonstrating State Independence in Plain Java 17

The small example below is a **simulated state model**; it does not interact with Spring Security or an OP. It shows that separate state updates require separate actions and cannot be inferred from a single flag. Save as `LogoutBoundaryDemo.java`:

```java
public class LogoutBoundaryDemo {
    record State(boolean rp, boolean op, boolean access, boolean refresh) {
        @Override
        public String toString() {
            return "rp=" + rp + ", op=" + op
                    + ", access=" + access + ", refresh=" + refresh;
        }
    }

    public static void main(String[] args) {
        State before = new State(true, true, true, true);

        // Simulate local logout: only RP session loss is guaranteed.
        State local = new State(false, before.op(), before.access(),
                before.refresh());

        // Simulate successful OP logout: additionally ends OP session.
        State afterOp = new State(local.rp(), false, local.access(),
                local.refresh());

        // Simulate AS confirming refresh token revocation.
        State afterRevoke = new State(afterOp.rp(), afterOp.op(),
                afterOp.access(), false);

        System.out.println("before:      " + before);
        System.out.println("local:       " + local);
        System.out.println("op logout:   " + afterOp);
        System.out.println("revoke R:    " + afterRevoke);
    }
}
```

Run with JDK 17+:

```bash
javac LogoutBoundaryDemo.java
java LogoutBoundaryDemo
```

Exact stdout:

```text
before:      rp=true, op=true, access=true, refresh=true
local:       rp=false, op=true, access=true, refresh=true
op logout:   rp=false, op=false, access=true, refresh=true
revoke R:    rp=false, op=false, access=true, refresh=false
```

Important truth: this program **only simulates specified consequences**; it does not assert every provider keeps access tokens alive after logout or every AS revokes refresh tokens identically. In real systems, test your specific AS/RS/RP policies.

## 16. Pre-Production Design Checklist

1. **Define the logout button's scope:** current RP logout, OP SSO logout, all-device logout, or access/grant revocation? UI and API must make promises matching the actual mechanism.
2. **Identify where sessions/tokens live:** Servlet `HttpSession`, reactive `WebSession`, Spring Session, OAuth2 authorized client service, browser storage; who owns cleanup?
3. **Keep CSRF on browser logout:** POST with valid CSRF token; never add GET logout that accidentally enables forced logout.
4. **Use standard OIDC handlers:** `OidcClientInitiatedLogoutSuccessHandler` or `OidcClientInitiatedServerLogoutSuccessHandler` for RP-Initiated logout; never concatenate URLs from untrusted input.
5. **Register URIs accurately:** OIDC Discovery exposes `end_session_endpoint`, `post_logout_redirect_uri` matches registered public URL; confirm whether OP prompts for logout confirmation.
6. **Handle OP outages:** still invalidate the local RP session per policy; provide fallback and telemetry, never claiming “logged out of all devices” when OP fails.
7. **Enable back-channel when global SSO is required:** check Spring Security version, OP registration, logout token signature/claims, multi-node session registry, cookie name, and replay policy.
8. **Decide token revocation:** AS endpoint, client authentication, refresh vs. access, JWT/opaque, RS cache/denylist, offline access, and authorization grant lifecycle.
9. **Limit tokens in the browser:** store appropriately, defend against XSS/CSRF, avoid logging `id_token_hint`/`logout_token`/access/refresh tokens.
10. **Test end-to-end:** multiple RPs, multiple browsers, multiple sessions, two users/tenants, lingering OP session, unexpired access JWT, delayed back-channel, revoked refresh token, and proxies.
11. **Observe data safely:** log per-step outcomes and correlation IDs; never log raw tokens, cookies, client secrets, or full ID token contents.
12. **Verify version constraints:** check docs/contracts for your exact Spring Security version and OP, especially back-channel and session registry, avoiding copying Servlet configs into Reactive.

Overarching principle: **local logout closes the application session; OIDC logout coordinates the identity provider and RP sessions; OAuth token revocation is a separate contract with the Authorization Server.** Final security depends on how the Resource Server enforces token lifetimes and status.

## 17. Authoritative Reference Documents

- [Spring Security — Servlet OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html): local logout, RP-Initiated logout, and back-channel logout.
- [Spring Security — Reactive OIDC Logout](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html): `OidcClientInitiatedServerLogoutSuccessHandler`, `oidcLogout`, back-channel session registry.
- [Spring Security — Servlet Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): `POST /logout`, CSRF, `SecurityContextLogoutHandler`, and default cleanup.
- [Spring Security — Reactive Logout](https://docs.spring.io/spring-security/reference/reactive/authentication/logout.html): `LogoutWebFilter`, local security context, and `WebSessionServerLogoutHandler`.
- [Spring Security — Reactive CSRF/Logout](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): why POST with CSRF should be used.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): `end_session_endpoint`, `id_token_hint`, and `post_logout_redirect_uri`.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): `logout_token` structure/validation, `sid`, and `sub`.
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html): browser-based notifications and front-channel limits.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revocation endpoint and HTTP 200 semantics.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): token active status and how RS queries AS.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): JWT claims such as `iss`, `aud`, and `exp`.
