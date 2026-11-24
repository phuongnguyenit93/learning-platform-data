# Configuring oauth2Login with an External Identity Provider in Spring Security Reactive

> **Module:** Spring Security - reactive  
> **Group:** OAuth2/OIDC Login  
> **Outcome:** Understand the OpenID Connect (OIDC) login flow via an external Identity Provider (IdP), configure `oauth2Login` in WebFlux, protect callbacks and WebSession, verify behavior with WebTestClient, and know when OAuth2 Resource Server is needed instead of OAuth2 Login.

## 1. The Problem and Expected Outcome

A WebFlux application running at `http://localhost:8080` needs to let users “Sign in with Google” or another IdP such as Keycloak, Okta, or Microsoft Entra ID. Users enter their password at the **IdP**, never giving their IdP password to the application. After the IdP authenticates them, the application holds an internal login session and allows access to private endpoints.

A login cycle requires:

1. The browser opens `GET /api/me` while unauthenticated → redirected to the login flow.
2. The user chooses an IdP on `/login` or visits `/oauth2/authorization/google`.
3. Spring Security builds an OAuth2 Authorization Request with `client_id`, `scope`, `redirect_uri`, `state`, and required protection parameters.
4. The browser is redirected to the Authorization Server; the IdP performs login/consent.
5. The browser returns to the `/login/oauth2/code/google` callback with an authorization code and state.
6. The server validates request correlation, exchanges the authorization code for tokens, verifies the OIDC ID Token, and obtains the principal.
7. Spring Security records the login state in the application's session.
8. Subsequent requests carry the session cookie and receive the user subject without re-sending the IdP password.

**OAuth2 and OIDC are not the same.** OAuth 2.0 is an authorization framework; OpenID Connect adds **end-user authentication**, ID Tokens, and verification rules. If you want to “log in” with an external provider, choose OIDC support and request the `openid` scope. A random OAuth2 access token does not by itself “prove the user logged in”.

## 2. Roles Involved

| Role | Entity in This Lesson | Responsibility |
| --- | --- | --- |
| End-user / Resource owner | Browser user | Selects provider and authenticates |
| OAuth2 Client / OIDC Relying Party | Spring WebFlux application | Builds authorization request, handles callback, exchanges code, saves session |
| Authorization Server / OpenID Provider | Google or enterprise IdP | Verifies identity, issues code/ID Token/access token |
| Resource Server | API receiving Bearer tokens | Validates issuer/audience/signature/scope of access tokens |
| Browser | User agent | Follows redirects, carries local cookies |

`oauth2Login()` belongs to **OAuth2 Client**, used for browser login into the application. `oauth2ResourceServer().jwt()` belongs to **Resource Server**, used when each API request sends a Bearer JWT. Both mechanisms can coexist in a multi-security-chain system, though their configurations and threat models differ.

In this lab model, the browser logs in via the IdP and then sends the **application's cookie** to `/api/me`. It does not send an ID Token or Bearer access token on every request. Do not turn a local session into a stateless setup by slapping on `oauth2Login()`.

## 3. Configuration Terms You Must Know

| Name | Example | Meaning |
| --- | --- | --- |
| `registrationId` | `google` | ID of a `ClientRegistration` |
| `client-id` | ID from IdP console | Identifier of the client application |
| `client-secret` | Secret from IdP console | Confidential client secret; kept strictly server-side |
| `authorization-uri` | URL at IdP | Where the browser goes to log in and consent |
| `token-uri` | URL at IdP | Where the backend exchanges the authorization code |
| `issuer-uri` | Exact issuer of IdP | Discovery/trust boundary and validation |
| `jwk-set-uri` | IdP endpoint | Public keys to verify token signatures |
| `redirect-uri` | `{baseUrl}/login/oauth2/code/{registrationId}` | Callback registered at the IdP |
| `scope` | `openid,profile,email` | Requested permissions/claims |
| `state` | Random value per login | Binds callback to the original authorization request |
| `nonce` | Random OIDC value | Binds ID Token to the authentication request |
| `PKCE` | Code verifier/challenge | Mitigates authorization code theft/replay |
| `ID Token` | Signed JWT per OIDC | Authenticates end-user **to the client** |
| `Access Token` | Opaque/JWT per provider | Calls protected APIs, does not replace ID Token |
| `Refresh Token` | Optional | Requests new access tokens per IdP policy |

Never store or return client secrets, authorization codes, ID Tokens, access tokens, or refresh tokens to public endpoints or logs. Never use an ID Token as a Bearer token for an API expecting an access token.

## 4. Authorization Code + OIDC: The Full Flow

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant A as Spring WebFlux Client
    participant P as External OIDC Provider
    B->>A: GET /api/me
    A-->>B: 302 /login
    B->>A: GET /oauth2/authorization/google
    A->>A: Generate request, state, nonce/PKCE if configured
    A-->>B: 302 to IdP authorization endpoint
    B->>P: GET /authorize?client_id&redirect_uri&scope&state...
    P->>B: Login + consent
    B->>P: Authenticate at provider
    P-->>B: 302 callback?code=...&state=...
    B->>A: GET /login/oauth2/code/google
    A->>A: Verify state + registration
    A->>P: Backend token request (code + client auth + PKCE if used)
    P-->>A: Tokens, including id_token for OIDC
    A->>A: Verify ID Token, load OIDC principal
    A->>A: Save SecurityContext / WebSession
    A-->>B: Post-login redirect + session cookie
    B->>A: GET /api/me + session cookie
    A-->>B: 200 JSON subject
~~~

Key distinctions:

- The authorization code is a **short-lived, single-use** credential bound to the client, redirect URI, and required protections.
- `state` prevents mixing callbacks across login attempts (login CSRF/mix-up); `nonce` binds the ID Token to the OIDC authentication request; PKCE uses `code_challenge` and `code_verifier` to prevent code theft. They are not interchangeable.
- The backend—not frontend JavaScript—holds the confidential web client's secret and performs the token exchange.
- When `openid` is present, the ID Token must have its signature, issuer, audience, expiry, and appropriate OIDC checks verified. Never accept a callback `code` and trust query parameters as proof of a logged-in user.
- After login, the server-side OAuth2 client can store Authentication in WebSession. The browser only needs a local cookie for subsequent requests; the local cookie is not a JWT.

## 5. Preparing the Client at the Provider

In the Google/IdP console:

1. Create an OAuth2/OIDC client of type **Web application/confidential client** if the backend can keep a secret.
2. Obtain `client-id` and `client-secret`. The secret must live in server environment variables/a secret manager, never committed to Git or sent to the frontend.
3. Register the exact authorized redirect URI. For registration `google` locally: `http://localhost:8080/login/oauth2/code/google`.
4. Configure Authorization Code grant, scope `openid`, and add `profile`/`email` only if needed.
5. If the provider requires a consent screen, test users, tenant restrictions, or logout allowlists, complete them per provider documentation.
6. Obtain the exact issuer/metadata/JWKS; for Google, Spring Boot has provider defaults so the lab does not need manual endpoint entries.
7. Prepare an **HTTPS public URL** and redirect for production; local HTTP is only for localhost.
8. Distinguish the backend's redirect URI from an SPA's CORS allowed origin. Those two settings do not replace each other.

If the app runs behind a reverse proxy, the IdP must know the **public URL seen by the browser**, not the pod/internal service URL. Never use wildcard callbacks or open redirects as a “quick fix” for mismatches.

## 6. Java 17+ / Maven Project

Use Spring Boot `3.3.13` for the Spring Security 6.x lab. The 3.3 branch has reached end of OSS support; new production projects must choose a supported version and verify exact APIs. Structure:

~~~text
reactive-external-oidc-login/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/oidc/
    │   │   ├── OidcApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ProfileController.java
    │   └── resources/application.yml
    └── test/java/example/oidc/
        └── OidcLoginTest.java
~~~

### 6.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactive-external-oidc-login</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <properties><java.version>17</java.version></properties>
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
            <artifactId>spring-boot-starter-oauth2-client</artifactId>
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
    <build><plugins><plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
    </plugin></plugins></build>
</project>
~~~

`spring-boot-starter-oauth2-client` is the dependency for `oauth2Login`, not `spring-boot-starter-oauth2-resource-server`. Do not add `spring-boot-starter-web` (Servlet) because the lab runs on WebFlux.

### 6.2. OidcApplication.java

~~~java
package example.oidc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OidcApplication {
    public static void main(String[] args) {
        SpringApplication.run(OidcApplication.class, args);
    }
}
~~~

### 6.3. application.yml

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          google:
            client-id: ${OIDC_CLIENT_ID:replace-me}
            client-secret: ${OIDC_CLIENT_SECRET:replace-me}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
~~~

When a registration is named `google`, Spring Boot applies provider defaults for Google. The two `replace-me` values are **placeholders only for testing/startup**: real `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` must be set to actually log in with Google.

**Never put real secrets in committed YAML, READMEs, CI logs, or JavaScript.** To authenticate users at another provider, use the appropriate ClientRegistration/provider settings rather than copying Google settings to an incompatible IdP.

## 7. WebFlux SecurityWebFilterChain and oauth2Login

File `src/main/java/example/oidc/SecurityConfig.java`:

~~~java
package example.oidc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/", "/login").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/me").authenticated()
                .pathMatchers(HttpMethod.POST, "/api/notes").authenticated()
                .anyExchange().denyAll()
            )
            .oauth2Login(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .build();
    }
}
~~~

Explanation:

- `@EnableWebFluxSecurity` activates reactive HTTP security.
- `authorizeExchange` allows the homepage/login; `/api/me` and POST `/api/notes` require an authenticated user.
- `oauth2Login(Customizer.withDefaults())` configures OAuth2 Client Authorization Code login, relying on `ReactiveClientRegistrationRepository` from Boot properties.
- `logout(Customizer.withDefaults())` uses the local logout filter.
- Spring Security WebFlux **enables CSRF by default**. Because the browser uses a session cookie, never disable CSRF for POSTs just because the IdP is external.
- `anyExchange().denyAll()` denies routes outside the contract. The OAuth2 login endpoints are handled by Spring Security filters, not custom controllers.
- Do not enable HTTP Basic or form password login as a fallback if the architecture requires logging in exclusively via the IdP.

**Do not confuse with Servlet APIs:** `HttpSecurity`/`SecurityFilterChain`/`HttpSession` belong to Servlet; here we use `ServerHttpSecurity`/`SecurityWebFilterChain`/`WebSession`.

## 8. Controller Returns OIDC Subject Without Leaking Tokens

File `src/main/java/example/oidc/ProfileController.java`:

~~~java
package example.oidc;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

record NoteInput(String text) {}

@RestController
public class ProfileController {

    @GetMapping("/")
    public Mono<Map<String, String>> publicPage() {
        return Mono.just(Map.of(
            "message", "Visit /login or /oauth2/authorization/google"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            @AuthenticationPrincipal OidcUser user) {
        return Mono.just(Map.of("subject", user.getSubject()));
    }

    @PostMapping("/api/notes")
    public Mono<Map<String, String>> save(
            @RequestBody Mono<NoteInput> input) {
        return input.map(note -> Map.of(
            "accepted", note.text()));
    }
}
~~~

`@AuthenticationPrincipal OidcUser` fits when the registration uses OIDC scope `openid`; if a provider only supplies OAuth2 UserInfo, the principal may be `OAuth2User` with no ID Token. This lab **intentionally chooses OIDC**.

With a real user, the returned JSON looks like:

~~~json
{"subject":"provider-assigned-subject"}
~~~

This value is issued by the IdP; there is no fixed universal subject. Never return ID Tokens, access tokens, refresh tokens, or secrets to the client just to render a profile. When storing internal users, use the `(issuer, sub)` key or map to an immutable user ID rather than using email as a primary key.

POST notes only echoes the data **to test login/CSRF**, without writing to a DB. When building a real app, the service must still enforce owner/tenant checks, validation, auditing, and transactions.

## 9. Default URLs and Running with Google

| Component | URL/Address | Role |
| --- | --- | --- |
| Login page | `/login` | Login page generated by Spring Security when appropriate |
| Start OAuth2 | `/oauth2/authorization/google` | Builds request, state; redirects to IdP |
| Authorization endpoint | At Google | User login/consent |
| Callback | `/login/oauth2/code/google` | Processes code and state |
| Token endpoint | At Google | Backend exchanges code for tokens |
| JWKS/UserInfo | At IdP | Validates tokens, fetches claims when needed |
| Local profile | `/api/me` | Uses local Authentication from session |
| Local logout | `POST /logout` with CSRF | Terminates local session per config |

In Google OAuth client configuration, register exactly:

~~~text
http://localhost:8080/login/oauth2/code/google
~~~

Example environment variable setup with **Bash**:

~~~bash
export OIDC_CLIENT_ID="id-issued-by-provider"
export OIDC_CLIENT_SECRET="secret-issued-by-provider"
mvn spring-boot:run
~~~

With **PowerShell**:

~~~powershell
$env:OIDC_CLIENT_ID = "id-issued-by-provider"
$env:OIDC_CLIENT_SECRET = "secret-issued-by-provider"
mvn spring-boot:run
~~~

These values are placeholders and must be replaced with real credentials managed securely. Open `http://localhost:8080/login` to choose Google, or open `http://localhost:8080/oauth2/authorization/google` directly.

After login/consent, the browser returns to the callback and enters the app. Access `/api/me` in the **same browser session** to see the JSON subject. Using a private window/empty cookies treats you as unauthenticated and triggers the login flow.

**Do not use curl as proof of completing full OAuth2 login.** `curl -i http://localhost:8080/oauth2/authorization/google` only observes the first redirect; it does not perform browser login/consent, session handling, callback processing, or JWKS validation.

## 10. Reality at the IdP: Default Providers and Custom Issuers

Spring Boot includes provider defaults for common providers such as Google. For an enterprise OIDC IdP, use a **different registration**, e.g., `enterprise`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          enterprise:
            provider: enterprise
            client-id: ${ENTERPRISE_CLIENT_ID}
            client-secret: ${ENTERPRISE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,email
        provider:
          enterprise:
            issuer-uri: ${ENTERPRISE_ISSUER_URI}
~~~

This is an **alternative YAML**, not to be pasted on top of the Google project unless you intend to support multiple IdPs. `issuer-uri` must match the issuer published by the IdP. Spring Boot can use OIDC discovery to locate authorization/token/JWKS/UserInfo endpoints.

**Note:** With a custom issuer, metadata discovery may require network connectivity at ClientRegistration creation/startup time. If the IdP is unreachable or the issuer URI is wrong, the app may fail to boot or login will fail. Never use a dummy URI and disable signature validation to bypass errors.

If the IdP does not support discovery, Spring Boot provides `provider.enterprise.authorization-uri`, `token-uri`, `jwk-set-uri`, `user-info-uri`, and `user-name-attribute`. When filling these in manually, ensure TLS, issuer, endpoint URLs, and token validation align with the provider's configuration.

### 10.1. Scopes Matched to Actual Needs

- `openid`: requests OpenID Connect login and an ID Token.
- `profile`: name/picture/profile claims if permitted by the IdP.
- `email`: email claims if provided; check `email_verified`.
- `offline_access`: request only if refresh/offline access is genuinely needed, per IdP policy.
- IdP API scopes: request the minimum needed; a sign-in button should not ask for Drive/mail read permissions by default.

**Do not equate scopes with roles.** A user who authenticates successfully with `openid` is not automatically granted `ROLE_ADMIN` in the application.

## 11. User Identification and Internal Account Linking

An OIDC ID Token contains claims such as `iss`, `sub`, `aud`, `iat`, `exp`, and `nonce` if used. Spring Security OIDC handles ID Token validation and builds `OidcUser`.

Durable identification should look like:

~~~text
Application user ID (UUID)
    ↔ verified identity: issuer + subject
    ↔ app-specific roles/tenant/permissions
~~~

Two ID Tokens with the same `sub` but different `iss` **do not prove the same person**. Emails can change, be recycled, be unverified, or exist across multiple providers; never auto-merge accounts solely on matching email.

Example database schema:

~~~sql
CREATE TABLE user_identities (
    id UUID PRIMARY KEY,
    application_user_id UUID NOT NULL,
    issuer VARCHAR(255) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    CONSTRAINT uq_identity UNIQUE (issuer, subject)
);
~~~

Before linking an additional external identity to an existing account, verify that the user owns both the current identity **and** the new identity. Otherwise, an unverified email from another provider could lead to account takeover.

**Authority mapping:** Spring can create `OIDC_USER` and authorities from scopes. Business permissions must be explicitly granted by internal policy or trusted provider groups. If groups/tenants change, old sessions/tokens can carry stale permissions; enforce appropriate session lifetimes, refresh/revalidation, or revocation.

## 12. Optional Example: Mapping Groups to Application Roles

An IdP may sign a `groups` claim in the ID Token. If this claim is trustworthy and the `app-readers` group is enterprise-managed, you can add a `GrantedAuthoritiesMapper` bean to map it to `ROLE_APP_READER`:

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;

@Bean
GrantedAuthoritiesMapper appRoles() {
    return authorities -> {
        Set<GrantedAuthority> mapped = new HashSet<>(authorities);
        for (GrantedAuthority auth : authorities) {
            if (auth instanceof OidcUserAuthority oidc) {
                List<String> groups =
                    oidc.getIdToken().getClaimAsStringList("groups");
                if (groups != null && groups.contains("app-readers")) {
                    mapped.add(new SimpleGrantedAuthority(
                        "ROLE_APP_READER"));
                }
            }
        }
        return mapped;
    };
}
~~~

This is an **optional snippet** to place inside a Spring `@Configuration`. It is not part of the lab's three runnable classes. Never grant roles carelessly if `groups` is absent from a trusted ID Token; some IdPs provide groups via UserInfo or a separate API and require a `ReactiveOAuth2UserService` to look them up.

If roles/tenants come from a DB, check current permissions in a reactive service/domain layer; a synchronous mapper is not the place for blocking JDBC calls on the event loop. `hasRole("APP_READER")` looks for `ROLE_APP_READER`, whereas `hasAuthority(...)` matches the exact string.

## 13. WebSession After Login and Token Lifecycles

In WebFlux, Spring Security can store `SecurityContext` in `WebSession` via `WebSessionServerSecurityContextRepository`. The browser typically keeps a session cookie named `SESSION`; the cookie value is a **session ID**, not an ID Token or access token.

Distinguish three storage types:

| Storage | Contents | Lifecycle |
| --- | --- | --- |
| Authorization request repository | State and request awaiting callback | Temporary between start and callback |
| SecurityContext + WebSession | Logged-in user for the application | Until logout/timeout/invalidation |
| Authorized client repository/service | Access/refresh tokens for downstream APIs | Per token expiry/refresh/revocation policy |

`ReactiveSecurityContextHolder` lets you read Authentication from the **currently executing request's** Reactor Context. Never use Servlet's `ThreadLocal` `SecurityContextHolder` and assume reactive code always stays on one thread.

In multi-node deployments, the authorization request + session store must be available to the callback even if the redirect hits a different node. Use Spring Session/Redis or proper routing affinity. Do not assume “external login” makes the application stateless.

Production cookies require HTTPS, `Secure`, `HttpOnly`, `SameSite`, timeouts, rotation/session fixation protection, and logout invalidation. Tokens in the authorized client store must be protected; never send raw tokens to the frontend just to fetch a profile.

## 14. CSRF for Sessions, Login, and Logout

OAuth2 `state` and a Spring Web CSRF token are **different**. `state` protects correlation of the OAuth2 authorization callback, whereas the CSRF token protects the app's POST/PUT/PATCH/DELETE mutations when the browser automatically attaches the session cookie. OIDC `nonce` binds the ID Token to the authentication request.

Spring Security WebFlux enables CSRF protection by default. In the lab, POST `/api/notes` as an authenticated user **without a CSRF token** must be rejected with 403; only with a valid CSRF token does the request reach the controller. That is why you should not add `csrf().disable()` merely because the app uses OIDC.

Local logout usually uses `POST /logout` with CSRF—do not turn it into an arbitrary GET link to bypass the token. For SPAs, supply the CSRF token via a server-rendered form/meta tag or a safe endpoint; the token must match the current session and may need to be re-fetched after login/logout. A CORS allowlist does not replace CSRF because browsers can still trigger cross-site requests with side effects even when the attacker cannot read the response.

## 15. Redirect URI and Reverse Proxy

Default value:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

Local example:

~~~text
http://localhost:8080/login/oauth2/code/google
~~~

Behind an ingress, the browser may hit `https://app.example.com` while the backend sees `http://service:8080`. If `{baseUrl}` is computed from the internal URL, the IdP can return `redirect_uri_mismatch`.

Configure forwarded headers/trusted proxy boundaries properly so Spring sees the public scheme/host/port; never unconditionally trust spoofed `X-Forwarded-Host` headers from the Internet. In the provider console, register the **exact** callback without using wildcards to work around mismatches.

If customizing the callback to `/login/oauth2/callback/{registrationId}`, update all three together:
1. `oauth2Login().authenticationMatcher(...)` in `ServerHttpSecurity`.
2. `ClientRegistration.redirectUri`.
3. Allowed redirect URI in the IdP console.

After login, any success redirect driven by a parameter like `next` must be validated against an internal allowlist; never allow open redirects to arbitrary external websites.

## 16. Local Logout and OIDC Logout

| Logout Type | What It Accomplishes | What It Does Not Guarantee |
| --- | --- | --- |
| Delete client cookie | Browser stops sending session ID | Old server session may not be invalidated yet |
| Local POST logout | Clears local SecurityContext/session per config | Does not automatically log out of IdP SSO |
| RP-Initiated OIDC Logout | Redirects to provider end-session endpoint if supported | Does not necessarily revoke all access tokens |
| Back-channel logout | Provider notifies app to terminate session via supported protocol | Requires matching session registry/mapping |
| Refresh token revocation | Prevents obtaining new access tokens | Already-issued access tokens may stay valid until expiry |

**Local logout does not equal global SSO logout.** After local logout, if the browser still has an active session at the IdP, starting OAuth2 login again may silently re-authenticate the user. This is normal SSO behavior, not necessarily a bug in local logout.

If the IdP publishes end-session metadata and supports client-initiated logout, Spring Reactive provides `OidcClientInitiatedServerLogoutSuccessHandler`. Example **as an alternative chain only**; do not copy as a parallel bean into the lab project without separating matchers:

~~~java
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.server.logout.OidcClientInitiatedServerLogoutSuccessHandler;

@Bean
SecurityWebFilterChain oidcLogoutChain(
        ServerHttpSecurity http,
        ReactiveClientRegistrationRepository clients) {
    var handler = new OidcClientInitiatedServerLogoutSuccessHandler(clients);
    handler.setPostLogoutRedirectUri("{baseUrl}");

    return http
        .authorizeExchange(ex -> ex.anyExchange().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .logout(logout -> logout.logoutSuccessHandler(handler))
        .build();
}
~~~

The provider must support the logout endpoint and allowlisted post-logout redirect URL. Back-channel logout may require exact session registry/session cookie name alignment; never assume every IdP supports it or every WebFlux version shares identical defaults.

## 17. WebTestClient: Testing Without a Real IdP

`spring-security-test` provides `mockOidcLogin()` to inject an OIDC principal into test requests; it **does not** verify real signatures, issuers, audiences, token endpoints, or callbacks. The tests below verify login-initiation redirects, HTTP authorization, and CSRF—not the full cryptographic OIDC handshake.

File `src/test/java/example/oidc/OidcLoginTest.java`:

~~~java
package example.oidc;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOidcLogin;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class OidcLoginTest {
    @Autowired WebTestClient client;

    @Test
    void publicEndpointIsAvailable() {
        client.get().uri("/").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").exists();
    }

    @Test
    void anonymousBrowserMustLogin() {
        client.get().uri("/api/me").exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void authorizationStartHasStateAndProviderRedirect() {
        EntityExchangeResult<byte[]> result =
            client.get().uri("/oauth2/authorization/google")
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectBody()
                .returnResult();

        String location = result.getResponseHeaders()
            .getFirst(HttpHeaders.LOCATION);
        assertNotNull(location);
        assertTrue(location.startsWith("https://accounts.google.com/"));
        assertTrue(location.contains("state="));
        assertTrue(location.contains("openid"));
    }

    @Test
    void mockOidcUserCanReadSubjectButNotTokens() {
        client.mutateWith(mockOidcLogin().idToken(token ->
                token.claim("sub", "external-sub-123")))
            .get().uri("/api/me").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("external-sub-123")
            .jsonPath("$.access_token").doesNotExist()
            .jsonPath("$.id_token").doesNotExist();
    }

    @Test
    void authenticatedPostWithoutCsrfIsForbidden() {
        client.mutateWith(mockOidcLogin())
            .post().uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("text", "hello"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void authenticatedPostWithCsrfSucceeds() {
        client.mutateWith(mockOidcLogin())
            .mutateWith(csrf())
            .post().uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("text", "hello"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.accepted").isEqualTo("hello");
    }

    @Test
    void unexpectedRouteDenied() {
        client.mutateWith(mockOidcLogin())
            .get().uri("/api/admin/debug")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

**Note on test statuses:** `oauth2Login` browser flows typically redirect anonymous requests to `/login`; pure Bearer APIs usually return 401. A 403 on POST can mean CSRF or authorization. Never turn every response into 200/401 just to get “green tests”.

A mock OIDC user only proves the application layer receives an already-created Authentication; it cannot replace testing against a real provider. To test full code exchange/ID Token validation offline, use a mock IdP that supports metadata, authorize, token, JWKS, and userInfo per protocol; never disable signature verification.

## 18. Commands, Expectations, and Step-by-Step Verification

In the `pom.xml` directory:

~~~bash
mvn clean test
~~~

Expected: **7 JUnit methods** in `OidcLoginTest` PASS with the test config and Google provider defaults, without needing a real Google secret for the mock security tests. Maven stdout depends on version and environment, with no fixed subject value.

For real login:

~~~bash
mvn spring-boot:run
~~~

Verify in the browser:
1. `GET /login` has the sign-in link.
2. The link leads to `/oauth2/authorization/google`.
3. `Location` redirect points to Google with `client_id`, `state`, `redirect_uri`, and `scope`.
4. After IdP login, the callback does not return `redirect_uri_mismatch`/`invalid_client`.
5. The browser stores the application cookie; `/api/me` returns the subject.
6. Requests without cookies in a private browser window are prompted to log in.
7. POST `/api/notes` without CSRF is rejected, and only processed with a valid token.

Observing the initial redirect with `curl` is only a smoke test:

~~~bash
curl -i "http://localhost:8080/oauth2/authorization/google"
~~~

Never paste a callback `Location` containing an authorization code into issue trackers/logs. Browser DevTools/IdP audit logs can assist diagnostics, but redact secrets/tokens/cookies.

## 19. Common Errors and How to Handle Them

| Error | Common Cause | How to Fix |
| --- | --- | --- |
| Missing login link | ClientRegistration not loaded, wrong custom page | Check registration ID, `/login`, and repository |
| `/oauth2/authorization/google` does not redirect | Wrong registrationId, resolver/security chain | Check exact path |
| `redirect_uri_mismatch` | IdP callback differs from app baseUrl | Compare scheme/host/port/path and proxy settings |
| `invalid_client` | Wrong client ID/secret/authentication method | Check IdP console/secret rotation |
| Callback state mismatch | Session/state lost, changed browser/node/cookie | Cookie policy, shared session, state correlation |
| Token response lacks ID Token | Missing `openid` or OAuth2-only provider | Use an OIDC provider and appropriate scope |
| Invalid ID Token | Wrong issuer/aud/exp/nonce/signature/JWKS | Check metadata, clock, trust roots |
| Still anonymous after callback | SecurityContext/session cookie not saved/loaded | WebSession, auth success, and Set-Cookie |
| POST returns 403 | CSRF or missing permission | Check CSRF token, role/scope separately |
| User assigned wrong account | Linked by email instead of `(iss,sub)` | Audit identity linking |
| Still logged into IdP after logout | Local logout does not clear SSO session | Review RP-Initiated/Back-channel logout |
| Roles changed at IdP not reflected in app | Stale session/claims | Session invalidation/refresh/revalidation |
| Downstream token rejected by API | Wrong audience/scope, expired | Authorized client token policy |
| Secret leaked in logs | Logging requests/tokens or config | Redaction, secret manager, restrict access |

**Debugging order:** ClientRegistration config → authorization redirect → state/session → callback/redirect URI → token exchange → ID Token verification → SecurityContext/WebSession → cookie → role/CSRF/business authorization. Never “fix” issues by opening all redirect URIs, disabling OIDC validation, or disabling CSRF.

## 20. PKCE, state, nonce, and Trust Boundaries

- **State:** random per login attempt; callback must match the pending authorization request. Never hardcode it or accept arbitrary user input.
- **Nonce:** used by OIDC to bind the ID Token to the request when applicable; never use username/email as a nonce.
- **PKCE:** client generates a random `code_verifier`, sends `code_challenge`, and presents the verifier when exchanging the code; reduces the risk of stolen-code reuse.
- **PKCE default:** Spring supports PKCE for public clients configured with `client-authentication-method: none` and an empty secret, or when client settings require a proof key. **Do not assume confidential clients in the lab always have PKCE enabled by default**; if policy requires it, configure and test `code_challenge`.
- **Issuer:** trust only allowlisted IdPs; never accept an arbitrary issuer URI from an HTTP parameter and run discovery (SSRF/trust confusion risk).
- **ID Token:** verify signature, issuer, audience, timestamps, and nonce per OIDC; never accept `alg=none`.
- **Redirect:** allowed redirect URLs must be exact; post-login `next` parameters must be restricted to prevent open redirects.
- **Credentials:** never log access/refresh tokens, client secrets, codes, or session IDs; production requires HTTPS, proper cookie flags, and secret rotation.

## 21. Connections to APIs, SPAs, and BFFs

| Model | What Browser/Client Sends to Backend | Configuration |
| --- | --- | --- |
| Server-side WebFlux OIDC Login | Application session cookie | `oauth2Login`, CSRF, WebSession |
| SPA calling API directly with JWT | Authorization Bearer token | OAuth2 Code + PKCE in client; backend `oauth2ResourceServer().jwt()` |
| Backend-for-Frontend (BFF) | Browser → BFF cookie, BFF → Bearer downstream | `oauth2Login` at BFF, authorized client manager/store |
| Service-to-service | Machine/delegated access token | OAuth2 Client Credentials + Resource Server, no user login session |

Never copy a raw ID Token into localStorage just to “use it as an access token”. Being authenticated does not imply object-level permissions; business APIs must still verify owner/tenant. When a BFF calls downstream services on behalf of the user, it needs `ServerOAuth2AuthorizedClientRepository` and secure token management, forwarding an **access token with the right audience/scope**, never blindly forwarding an ID Token.

## 22. Exercises and Checklist

**A — provider setup:** Create a Web application client at an IdP, configure the exact callback, and test real browser login. Never include tokens/secrets in reports.

**B — fixing redirect errors:** Simulate a callback with the wrong scheme/port; compare `redirect_uri` in the authorization redirect with the IdP allowlist; configure trusted proxy settings.

**C — testing state:** Start login in browser A, and try hitting the callback in browser B with no session. Explain why it must be rejected.

**D — distinguishing OIDC/Resource Server:** Build a table of requests from browser local sessions vs. API Bearer calls; decide whether each service uses `oauth2Login` or `oauth2ResourceServer`.

**E — mockOidcLogin:** Test anonymous redirect; mock subject; test missing/present CSRF; explain why the mock does not verify a real ID Token.

**F — identity linking:** Design a unique `(issuer,sub)` constraint storing application user IDs; verify two providers with the same email do not auto-link.

**G — role mapping:** Add a trusted `app-readers` group in a test IdP; verify that omitting the claim does not grant the role.

**H — OIDC logout:** Compare local POST logout, RP-Initiated Logout, and back-channel logout; check whether the IdP supports end-session metadata.

**I — PKCE:** Enable a policy requiring PKCE with a supporting IdP, observe `code_challenge`, and review `code_verifier` storage rules.

**Checklist:**
- [ ] Understand OAuth2 Login vs. OIDC vs. Resource Server.
- [ ] Properly configure ClientRegistration/registrationId/client ID/secret/scopes.
- [ ] Callback URI matches identically in the app and at the IdP.
- [ ] Use `ServerHttpSecurity.oauth2Login` in WebFlux.
- [ ] Never handle code/state manually with an ad-hoc controller.
- [ ] Validate ID Tokens and never use tokens with the wrong audience.
- [ ] Use `issuer + sub` to link users; never trust email as a primary key.
- [ ] Keep CSRF enabled for browser sessions, POSTs, and logout.
- [ ] Understand how state/nonce/PKCE differ.
- [ ] Have tests for anonymous access, provider redirect, mock OIDC, and CSRF.
- [ ] Understand how mock tests differ from real end-to-end login.
- [ ] Have production policies for cookies/security/sessions/secret rotation/logout.

## 23. Self-Check Questions

1. Does an application using `oauth2Login()` act as an OAuth2 Client or a Resource Server?
2. Which URL initiates login and what is the default callback URL when `registrationId` is `google`?
3. How can the backend log users in via an IdP without ever seeing their IdP password?
4. What is the ID Token for, and why must it not be used arbitrarily as an access token?
5. Why do `state` and the application's CSRF token have different responsibilities?
6. How does `nonce` relate to the ID Token? What threat does PKCE mitigate?
7. Why must the client secret stay server-side and never be placed in frontend code?
8. Why should account identity use `issuer + sub` instead of email?
9. Are application roles automatically generated when a user signs in with Google successfully?
10. Does `mockOidcLogin()` validate real signatures and audiences?
11. Does local logout automatically clear the IdP SSO session?
12. When a proxy changes the host/port, how does an incorrect `{baseUrl}` affect the callback?
13. In an app using WebSession, why does a POST still need CSRF?
14. When should you use BFF/session vs. API bearer and Resource Server?
15. If provider metadata is unreachable, what errors can custom issuer discovery cause?

## 24. References

- [Spring Security — OAuth2 Login WebFlux (Core)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html): client/redirect/Google and `oauth2Login` configuration.
- [Spring Security — OAuth2 Login WebFlux (Advanced)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/advanced.html): authorization resolver, custom callback, user authorities, ID Token verification.
- [Spring Security — OIDC Logout](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html): local/RP-Initiated/back-channel logout.
- [Spring Security — OAuth2 Grant Support](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorization-grants.html): Code Grant and PKCE.
- [Spring Security — Testing OAuth2 in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockOidcLogin()`.
- [Spring Security — CSRF in WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): CSRF for sessions/login/logout.
- [Spring Boot — OAuth2 Client](https://docs.spring.io/spring-boot/reference/security/oauth2.html): registration/provider configuration.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, claims, and validation.
- [RFC 6749](https://www.rfc-editor.org/rfc/rfc6749): OAuth 2.0 Authorization Framework.
- [RFC 7636](https://www.rfc-editor.org/rfc/rfc7636): PKCE.
- [OWASP — OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): OAuth2/OIDC risks and best practices.

**Conclusion:** In Spring Security Reactive, `oauth2Login` is an **OAuth2 Client** mechanism connecting to an external IdP. You must configure `ClientRegistration` accurately, protect authorization code/state/nonce/PKCE, verify the ID Token, and store the application session securely. ID Tokens, access tokens, and session cookies serve distinct purposes. Finally, separate tests for OAuth2 redirects/HTTP security from full integration with an IdP so you do not mistake a mock principal for genuinely verified login.