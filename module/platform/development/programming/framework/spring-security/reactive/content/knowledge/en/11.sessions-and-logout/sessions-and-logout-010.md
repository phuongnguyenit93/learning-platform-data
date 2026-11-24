# Distinguishing Local Logout, Token Expiration, and Token Revocation at the Identity Provider

**Module:** Spring Security – reactive (Spring WebFlux)  
**Section:** Sessions and logout  
**Scope:** Application `WebSession`, OAuth 2.0 access/refresh tokens, OpenID Connect (OIDC), Identity Providers (IdP), and how they coordinate.

When a user clicks **Log out**, at least three kinds of state can exist independently:

1. **Local application session:** session cookie and `SecurityContext` for the Spring WebFlux website.
2. **Token validity period:** `exp`/`nbf` on a JWT, or expiration state managed by the Authorization Server for opaque access/refresh tokens.
3. **State at the Identity Provider (IdP):** SSO login session, authorization grants, revoked refresh or access tokens, and OIDC logout signals to related applications.

**These three events are not equivalent.** An application can clear its session while an issued access token still works at an API until it expires or is rejected by API policy; token expiration does not automatically "log out" a user from a site with a still-valid `WebSession`; and revoking a refresh token at the IdP does not necessarily make an already-issued JWT access token immediately rejected at every resource server verifying signatures offline.

This lesson provides diagrams, comparison tables, runnable Java 17+ code, WebFlux configuration, and a verification matrix so learners do not conflate the logout layers.

## 1. Classify Correctly Before Configuring

| Mechanism / event | Who manages the state? | Direct effect | What does **NOT** happen automatically |
| --- | --- | --- | --- |
| **Local logout** | Spring WebFlux app; `ServerSecurityContextRepository`, `WebSession` | Clears the app's security context, optionally invalidates corresponding `WebSession`/cookie | Does not automatically revoke access/refresh tokens at IdP; does not close IdP SSO session; does not log out all apps |
| **Access token expiration** | Issued lifetime + resource server token validation | API should reject the token past validity, accounting for clock skew | Does not clear `WebSession`, refresh tokens, SSO sessions, or other access tokens |
| **Refresh token expired/unusable** | Authorization Server/IdP + client holding token | Cannot obtain new access tokens using that refresh token | Already-issued access tokens may stay valid until `exp` or until rejected by another policy |
| **Token revocation** (*OAuth2 revocation*) | Authorization Server/IdP via revocation endpoint (RFC 7009) | Invalidates token/grant within what the provider supports | Does not guarantee offline JWTs at resource servers immediately receive notice; does not mean app browser session was cleared |
| **OIDC RP-Initiated Logout** | Application (*Relying Party*, RP) and OpenID Provider (OP) | RP sends user-agent to OP's `end_session_endpoint` to end the OP session per supported flow | Does not by default call RFC 7009 to revoke all tokens; not guaranteed every other RP is logged out |
| **OIDC Back-Channel Logout** | OP sends Logout Token over server-to-server channel to RP | RP receives and verifies signal to terminate corresponding sessions | Not bearer access token revocation; requires IdP and RP support and proper config |
| **Log out all devices** | Architecture coordinating IdP, multiple apps, session stores, resource servers | Can cover multiple sessions and grants per designed policy | No single default Spring Security button/API synchronizes every party absolutely |

**First question to ask when receiving a "logout" requirement:** Where must the system block access and within what timeframe? Only the current browser window, all sessions of one user, all OAuth clients, refresh tokens, or every unexpired access token across all APIs? The answer determines the architecture and test suite.

## 2. Multi-Party Architecture: Browser, Application, API, and IdP

```text
   Browser / Mobile App                    Identity Provider (OP/AS)
  +---------------------+                  +--------------------------+
  |  Cookie SESSION     |<-- OIDC login -->| SSO browser session      |
  |  Access Token?      |                  | Authorization grants     |
  |  Refresh Token?     |                  | Revocation / introspect  |
  +----------+----------+                  +-------------+------------+
             |                                           |
             | HTTPS                                     | JWT keys / introspection
             v                                           v
  +---------------------+                  +--------------------------+
  | Spring WebFlux App  |--- API request ->| Resource Server / API    |
  | WebSession          |                  | JWT offline validation   |
  | SecurityContext     |                  | or introspection         |
  | OAuth2 Client       |                  | scope/role checks        |
  +---------------------+                  +--------------------------+
```

A deployment may combine several roles into one process, yet you should **separate them conceptually**:

- **Website/RP app** keeps a local session so users do not run OAuth2/OIDC login on every UI request.
- **Authorization Server/OP/IdP** issues, refreshes, and revokes tokens and may maintain its own SSO browser session.
- **Resource Server** validates access tokens to authorize APIs, via JWT checks (`iss`/`aud`/`exp`/signature) or introspection. It may **not know** the user just logged out of another website.
- **OAuth2 Client** holds or uses access/refresh tokens per granted permissions; where the client stores tokens is a separate architectural decision.

In Spring Security Reactive, `oauth2Login()` supports **RPs logging in via an OP**, while `oauth2ResourceServer()` supports **APIs accepting Bearer access tokens**. The two concepts must not be collapsed into a naive "logout = remove JWT from session" diagram.

### Example of a misleading scenario

- 10:00: Alice opens the website, completes OIDC login; the web app creates `WebSession A`. The IdP issues an access JWT expiring at 10:15 and a refresh token R.
- 10:05: Alice clicks Log out **at the web app only**. `WebSession A` is invalidated.
- 10:06: Another program still holding the previously issued access JWT can still call the API if the API verifies JWTs **offline** without a separate revocation/denylist check.
- 10:07: Alice reopens the website; if the SSO session at the OP is still alive, OIDC can log her back in quickly, potentially without re-entering a password.
- 10:08: If the IdP revokes refresh token R, the client cannot obtain new access tokens with R; however, the current JWT may still be accepted until expiry or until the resource server receives a revocation signal.
- 10:15: The JWT reaches `exp` in the example; the resource server must reject it past configured clock skew.

Timestamps here are illustrative, not guaranteed latencies. **Independently test** website state, IdP state, refresh endpoint, and API behavior.

## 3. Local Logout in Spring Security WebFlux

### 3.1. What does the default do?

In the form-login/`WebSession` model, Spring Security Reactive provides logout endpoints:

- `GET /logout` normally renders a logout confirmation page and **does not** execute logout by default when CSRF is enabled.
- `POST /logout` with a matching **CSRF token** triggers `LogoutWebFilter`. Spring Security cleans up `SecurityContext` and CSRF state per configuration, then usually redirects to the login page.
- To ensure **the active `WebSession` itself is also invalidated**, configure `WebSessionServerLogoutHandler` alongside `SecurityContextServerLogoutHandler` via `DelegatingServerLogoutHandler`.

WebFlux docs emphasize that final point: clearing the security context and invalidating the **entire session** are two actions to consider separately; do not assume default logout always performs every custom cleanup an app expects.

### 3.2. Local logout processing chain

```text
Logged-in browser: Cookie SESSION=abc
        |
        | POST /logout + valid _csrf
        v
Spring Security LogoutWebFilter
        |
        +-- SecurityContextServerLogoutHandler
        |     clears SecurityContext in ServerSecurityContextRepository
        |
        +-- WebSessionServerLogoutHandler
        |     invalidates current WebSession
        |
        +-- ServerLogoutSuccessHandler
              redirects /login?logout (or custom target)
        |
        v
Browser GET /private/me with old cookie
        |
        v
No Authentication left in session -> redirect login / require auth
```

This is **local logout**. It sends zero HTTP requests to the IdP's `/revoke` unless you explicitly add an OAuth2 flow, and it cannot "erase" an access token sitting on another device.

### 3.3. Cookies and CSRF

Logging out is a state-changing operation. If `GET /logout` were allowed to perform logout without protection, an external site could use an image/link to force the browser to log out; Spring Security WebFlux handles real logout via POST by default when CSRF is enabled. Never disable CSRF just to run a simple curl command.

The `SESSION` cookie is a credential: require HTTPS, `Secure`, `HttpOnly`, appropriate `SameSite`, and proper domain/path policies; handle session fixation, timeouts, session stores, and multi-instance logout. Deleting the cookie client-side does not necessarily erase backend session data if the session store remains intact; server-side session invalidation is the more trustworthy control. Conversely, invalidating `WebSession` does not delete copies of data intentionally stored by a frontend in `localStorage`/`IndexedDB`.

**Single-session logout differs from all-session logout:** If Alice logs in from Chrome and her phone, `POST /logout` in Chrome normally invalidates only Chrome's session. To "log out of all devices", the app must store/index sessions per user with a dedicated invalidation/reauth mechanism, or coordinate with the IdP and participating clients.

## 4. Access Token Expiration: API Access Ends, Not "Browser Logged Out"

### 4.1. JWT timestamps

JWT access tokens typically carry:

- `iat`: issued-at time, useful for policy yet **insufficient** by itself to validate a token;
- `nbf`: token is not valid before this timestamp;
- `exp`: token expires after this timestamp;
- `iss`: trusted issuer;
- `aud`: intended resource/audience for the token;
- `sub`: subject; `scope`/`scp` or permission claims per policy.

Resource servers must verify **signature, algorithm, issuer, audience, timestamps**, and permission policies. Never merely Base64-decode the payload and inspect `exp` as security validation. Spring Security WebFlux provides `oauth2ResourceServer(oauth -> oauth.jwt(...))` and `ReactiveJwtDecoder` for this.

**Scenario:** If an API verifies signed JWTs *offline* using JWKS/public keys, the IdP flipping a revoked flag in its database does not automatically alter the signature or claims of an already-issued JWT. The API may continue accepting that token until `exp` (plus configured clock skew), unless it checks revocation status via introspection, a denylist, token versions, or another method.

### 4.2. Clock skew is not a user-controlled "session extension"

Server clocks can drift. Spring Security supports `JwtTimestampValidator` and a `clockSkew` tolerance to reduce false 401s around `exp`/`nbf` boundaries. However, tolerance widens the acceptance window around expiration: set it per requirements with NTP synchronization, and never assume tokens are blocked **to the exact millisecond** past `exp` across all systems.

If a client receives `401 invalid_token` when an access token expires, an OAuth2 client can use a **still-valid refresh token** to request a new access token and retry per policy. That **does not mean logout failed** if the user's session was designed to stay active; that is the token lifecycle. However, if the product requires "logout = cannot obtain new access tokens", refresh privileges must be revoked too.

### 4.3. Refresh tokens and access tokens differ

| Property | Access token | Refresh token |
| --- | --- | --- |
| Purpose | Presented to resource servers to call APIs | Presented to Authorization Server to obtain new access tokens |
| Where used | HTTP `Authorization: Bearer ...` at APIs | `token_endpoint` per appropriate flow |
| Validity duration | Usually relatively short per policy | Usually longer, yet subject to expiry, rotation, revocation, inactivity policies |
| Consequence on expiration | API rejects old access token; may refresh | Cannot use that refresh token to obtain new tokens |
| Consequence on revocation | Depends on API's ability to check revocation | Normally blocks issuing new tokens with the revoked refresh token |
| Storage | Strict protection, minimize exposure | Stricter protection; never log or store in JS if architecture can avoid it |

**Refresh-token rotation** issues a new refresh token upon use and can invalidate the old one; token reuse detection is an IdP policy. Never send refresh tokens to resource servers; never use an OIDC ID token in place of an access token to call APIs. `id_token` attests an OIDC login session to the client in the proper context with its own expiry; `id_token` expiration does not mean all applications just logged out.

## 5. Revocation at the IdP: RFC 7009 and Blast Radius

OAuth 2.0 Token Revocation (RFC 7009) specifies an Authorization Server endpoint for **clients to request invalidation of a token**. Example request structure (URL, token, and client credentials are synthetic):

```http
POST /oauth2/revoke HTTP/1.1
Host: idp.example.invalid
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-credentials>

token=<refresh-token>&token_type_hint=refresh_token
```

HTTPS must be used outside local environments. Invoke it using a client authorized by the IdP and authenticated per its required method. Never put production `curl -u client:secret` in shell history or embed real tokens in tutorials.

According to RFC 7009:

- Authorization Servers **MUST** support refresh token revocation and **SHOULD** support access token revocation.
- A successful revocation request can invalidate the specified token and related tokens/grants per IdP policy; revoking an access token vs. revoking a refresh token can behave differently.
- The endpoint normally returns **HTTP 200 even if the token does not exist or was already revoked**, to avoid leaking token existence. Thus, a 200 response **does not prove** every resource server has rejected the token.
- Revocation state propagation across servers can incur latency. Test at real resource servers against the required consistency SLA.

### 5.1. Revoking a refresh token vs. revoking an access token

Suppose a client holds a valid refresh token R and access JWT A:

- When **revoking R**: the client cannot use R to obtain new access tokens. Per provider policy, access tokens tied to the same grant **may** also be invalidated at the IdP.
- When **revoking A**: the IdP marks A revoked if supported; policy may also revoke associated refresh tokens.
- If the API validates JWT A **offline** without querying revocation state, the API may still accept A within its signed lifetime. That is a **resource-server enforcement boundary**, not "RFC 7009 is broken".
- If the API checks **introspection per request** and the IdP returns `active=false`, the API will reject A per the introspection result (accounting for caches, networking, and SLAs).

Therefore, state the security requirement clearly: "Do not issue new tokens" or "immediately stop accepting already-issued tokens". The two requirements carry different costs, latencies, and mechanisms.

### 5.2. Introspection per RFC 7662 and revocation

A Resource Server can call the introspection endpoint (RFC 7662) to ask whether a token is still `active`. Spring Security WebFlux supports opaque tokens via `ReactiveOpaqueTokenIntrospector`; the name "opaque" describes **validating via introspection**, not a requirement that the token string lack JWT structure. A Resource Server can even pass a JWT to the IdP for introspection if the provider supports it and policy demands revocation freshness.

Trade-offs:

| Token checking approach | Strength | Risk / cost |
| --- | --- | --- |
| Offline JWT signature verification | Low latency, low IdP dependency when serving requests | Unaware of immediate revocation without an extra channel |
| Per-request introspection | Sees `active=false` in near real time | Adds latency, load on IdP, network dependency; caching results creates a delay window |
| JWT + `jti` denylist or session/token version | Can block specific tokens per policy | Requires shared state store, proper TTLs, and consistent checks |
| Very short-lived access token + refresh rotation/revocation | Bounds token exposure window | More refresh round trips; no instant hard cutoff |
| Push revocation events/notifications to resource servers | Can reduce revocation latency if well integrated | Must handle dropped events, races, retries, cache invalidation, and fallbacks |

**Never cache introspection `active=true` indefinitely.** A long cache TTL turns "immediate revocation" into "valid until cache expires". Equally, never automatically `permitAll` when the introspection server fails: choose *fail-closed* behavior based on your risk model, return appropriate error responses, and monitor rather than skipping token checks.

## 6. OIDC Logout at the IdP vs. OAuth Token Revocation

### 6.1. RP-Initiated Logout: browser is redirected to the OP

In OpenID Connect, an RP (web app) can ask the OP to end the login session via the **end-session endpoint** if supported by the OP. When configuring `oauth2Login()` and an appropriate logout handler, the app redirects the browser to the OP; the OP processes logout per its policy and can then return the browser to an allowed `post_logout_redirect_uri`.

**Common misconception:** An OIDC logout redirect to the OP **is not** an RFC 7009 token revocation request, nor does it guarantee all issued JWT access tokens become immediately invalid across every API. It targets the **OP-side login session** and the SSO experience.

In Spring Security Reactive, the corresponding class is:

```java
OidcClientInitiatedServerLogoutSuccessHandler
```

Note the **`Server`** infix for WebFlux. `OidcClientInitiatedLogoutSuccessHandler` without `Server` belongs to **Servlet**. In WebFlux, the handler typically reads `end_session_endpoint` from the OIDC discovery metadata of `issuer-uri`, using `ReactiveClientRegistrationRepository` and a matching client registration.

**WebFlux configuration fragment (requires real OAuth2 Client beans/properties; not standalone runnable):**

```java
@Bean
SecurityWebFilterChain oidcChain(
        ServerHttpSecurity http,
        ReactiveClientRegistrationRepository registrations) {

    var oidcLogout =
        new OidcClientInitiatedServerLogoutSuccessHandler(registrations);
    oidcLogout.setPostLogoutRedirectUri("{baseUrl}/signed-out");

    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/signed-out").permitAll()
            .anyExchange().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .logout(logout -> logout.logoutSuccessHandler(oidcLogout))
        .build();
}
```

Import `OidcClientInitiatedServerLogoutSuccessHandler` from `org.springframework.security.oauth2.client.oidc.web.server.logout`, along with `ReactiveClientRegistrationRepository`, `ServerHttpSecurity`, `SecurityWebFilterChain`, `Customizer`, and `@Bean`. This snippet assumes the IdP exposes discovery with an end-session endpoint, and `post_logout_redirect_uri` is allowlisted at the OP. Behind a proxy, resolve `{baseUrl}` with accurate scheme/host/path and trust forwarded headers only from trusted proxies; otherwise you risk broken redirects or open-redirect vulnerabilities.

To run a real OAuth2 Client, you need `spring-boot-starter-oauth2-client`, a client ID/secret or PKCE per client type, and a **real** issuer URI; that is a multi-party system and cannot run from the config fragment above without an IdP. The standalone lab in section 8 uses local form login so it requires no external accounts/secrets.

### 6.2. Back-Channel Logout: OP proactively notifies RP

If the OP needs to notify RPs that a user logged out at the OP or another application, OIDC **Back-Channel Logout** lets the OP send a Logout Token to an RP endpoint over a server-to-server channel. The RP must:

1. Verify the signature and required claims of the **Logout Token** (do not confuse with an access token); validate issuer, audience, timestamps, `events`, and token replay per spec.
2. Locate local sessions matching `sid` or `sub`/client.
3. Invalidate the matching sessions per policy, distinguishing a single OP session from all sessions of a user.
4. Ensure cookie/session registries and multi-instance synchronization work.

Spring Security Reactive supports OIDC back-channel logout depending on version via `oidcLogout(...).backChannel(...)` and `ReactiveOidcSessionRegistry`. However, **check your exact Spring Security version and cookie name**: Spring docs note constraints in some back-channel configurations around `JSESSIONID` while Spring Session may use `SESSION`, requiring matching handler/config adjustments. **Do not assume** merely enabling `oauth2Login()` logs out all RPs automatically from the IdP.

Back-channel logout and front-channel/browser redirects differ in transport channel, reliability, behavior when browsers are closed, and RP/OP coordination. Both differ completely from RFC 7009 access/refresh token revocation.

## 7. Standalone Java 17 Illustration: Three Separate Timelines

To understand outcomes *deterministically*, we simulate a local session, an offline access JWT, and an IdP refresh token with separate variables. This is **not** real token validation library code: the simulation skips signature/issuer/audience checks and must never be used for security decisions.

Save `LogoutAxesDemo.java`:

```java
import java.time.Instant;

public class LogoutAxesDemo {
    public static void main(String[] args) {
        Instant issuedAt = Instant.parse("2026-01-01T10:00:00Z");
        Instant expiresAt = issuedAt.plusSeconds(900);

        boolean localSessionActive = true;
        boolean refreshTokenActiveAtIdp = true;

        Instant t1 = issuedAt.plusSeconds(300);
        localSessionActive = false; // User logs out at website

        System.out.println("local-session-active=" + localSessionActive);
        System.out.println("jwt-time-valid-after-local-logout="
            + t1.isBefore(expiresAt));

        refreshTokenActiveAtIdp = false; // IdP revokes refresh token
        System.out.println("can-refresh=" + refreshTokenActiveAtIdp);
        System.out.println("jwt-time-valid-after-refresh-revocation="
            + t1.isBefore(expiresAt));

        Instant t2 = expiresAt.plusSeconds(1);
        System.out.println("jwt-time-valid-after-exp="
            + t2.isBefore(expiresAt));
    }
}
```

Run:

```bash
javac LogoutAxesDemo.java
java LogoutAxesDemo
```

**Exact** stdout:

```text
local-session-active=false
jwt-time-valid-after-local-logout=true
can-refresh=false
jwt-time-valid-after-refresh-revocation=true
jwt-time-valid-after-exp=false
```

Explanation: after clearing `WebSession`, the JWT's time condition **has not changed**; after revoking the refresh token, the issued JWT's time condition **still has not changed**; past `exp`, the time condition is no longer valid. In a real resource server, the JWT must still pass signature, issuer/audience, `nbf`, authorization, denylist/introspection, and clock skew checks. Never use the demo's `Instant.isBefore(exp)` to "validate JWTs"; it only illustrates the independence of the three axes.

## 8. Runnable Spring Boot WebFlux Application: Proper Local Logout

The sample application focuses on the **local layer**; the IdP and JWT pieces in section 11 are separate configs/architectures because they require a real Authorization Server. That way, learners can exercise the complete session lifecycle without faking external token revocation.

### 8.1. Project structure

```text
reactive-local-logout/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/logout/
    │   │   ├── LocalLogoutApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── PageController.java
    │   └── resources/application.properties
    └── test/java/demo/logout/
        └── LocalLogoutTests.java
```

Use **Java 17+**, Maven 3.9+, Spring Boot `3.5.7` in the example. The version is an anchor for the lab, not a production requirement to pin that exact version; in practice choose a supported patched release.

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-local-logout</artifactId>
    <version>1.0.0</version>
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
```

Do not add `spring-boot-starter-web` (Servlet MVC) when the lesson requires WebFlux; having both starters in the same project can make Boot choose the Servlet stack. Local logout in the example uses **`SecurityWebFilterChain`**, not Servlet `HttpSecurity`.

`src/main/resources/application.properties`:

```properties
spring.application.name=reactive-local-logout
server.port=8080
```

### 8.2. Main class

`src/main/java/demo/logout/LocalLogoutApplication.java`:

```java
package demo.logout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LocalLogoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(LocalLogoutApplication.class, args);
    }
}
```

### 8.3. SecurityConfig: clearing SecurityContext and invalidating WebSession

`src/main/java/demo/logout/SecurityConfig.java`:

```java
package demo.logout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice123"))
            .roles("USER").build();
        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob123"))
            .roles("USER").build();

        return new MapReactiveUserDetailsService(alice, bob);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        var logoutHandlers = new DelegatingServerLogoutHandler(
            new SecurityContextServerLogoutHandler(),
            new WebSessionServerLogoutHandler()
        );

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/", "/goodbye").permitAll()
                .pathMatchers("/login").permitAll()
                .pathMatchers(HttpMethod.GET, "/private/me").authenticated()
                .anyExchange().denyAll())
            .formLogin(Customizer.withDefaults())
            .httpBasic(basic -> basic.disable())
            .logout(logout -> logout.logoutHandler(logoutHandlers))
            .build();
    }
}
```

Key takeaways:

- `formLogin(...)` creates the default `GET /login` page and processes `POST /login`; this is a **local session** based on `WebSession`, not OIDC logout.
- `SecurityContextServerLogoutHandler` clears the saved context via the security context repository.
- `WebSessionServerLogoutHandler` invalidates the current `WebSession`; paired with the handler above, they clean up both security data and the session.
- `httpBasic(...disable())` makes browsers receive a form-login redirect rather than an HTTP Basic challenge, keeping the session demo clear.
- `PasswordEncoderFactories` hashes demo passwords before storing them in memory; never use `{noop}` for real users. Never hardcode production accounts.
- **Do not** disable CSRF. WebFlux requires a valid token by default when submitting `POST /login` and `POST /logout` in cookie/session apps.
- `anyExchange().denyAll()` prevents undeclared routes from being left open accidentally. If there are Bearer APIs, separate chains/matchers and matching session rules instead of copying form-login config across all APIs.

### 8.4. Controller

`src/main/java/demo/logout/PageController.java`:

```java
package demo.logout;

import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class PageController {

    @GetMapping(value = "/", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> home() {
        return Mono.just("home");
    }

    @GetMapping(value = "/goodbye", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> goodbye() {
        return Mono.just("goodbye");
    }

    @GetMapping(value = "/private/me", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> privateMe() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .map(name -> "signed-in:" + name);
    }
}
```

Every `/private/me` request uses the current subscription's `Authentication`. Never use a `static currentUser` variable because multiple users may call concurrently. There are no JWT checks or IdP calls in the demo: this is **intentional**, proving that local logout does not touch external tokens.

## 9. Running and Verifying Local Logout from a Browser

From the project directory:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Wait for Netty to start on 8080. In a fresh incognito browser window:

1. Open `http://localhost:8080/private/me`; since you are not logged in, the browser redirects to `/login`.
2. Enter `alice / alice123` in the default form. After successful login, the protected page returns `signed-in:alice`; open DevTools/Network to inspect the redirect chain and `SESSION` cookie.
3. Open `http://localhost:8080/logout` via GET: this is a logout confirmation page, not an immediate logout action when CSRF is enabled. While still on the confirmation page, try opening another tab to `/private/me`; the session is still authenticated.
4. Confirm logout via the POST form containing the hidden CSRF token provided by Spring Security. The app cleans up the context and invalidates `WebSession`.
5. Reopen `/private/me` with the old cookie/tab; it must require logging in again rather than returning `signed-in:alice`.
6. In a separate browser/profile, log in as Bob; Alice's logout **must not** end Bob's session, because local logout affects only the current session.

If step 5 still shows Alice's name, check whether an IdP SSO or login automation is **re-logging in automatically**, or whether you are truly still using an active old session. For this local form-login demo app, there is no IdP, so compare cookies and `SecurityContext` rather than looking only at URLs.

In production, use HTTPS, a suitable session store if multi-instance, and clean up cookies/CSRF state per policy. Never "fix" logout by turning `GET /logout` into a CSRF-free side effect.

## 10. WebTestClient Verifying Local Logout and Two Independent Sessions

A test that only checks for a redirect after `POST /logout` is not enough: you must **call the protected resource again with the old cookie** and see access denied. Also ensure logging out one session **does not** drop another user's session.

The test below uses `@SpringBootTest(webEnvironment = RANDOM_PORT)`: Spring starts a real HTTP server on a random port, and `WebTestClient` sends credentials/cookies like a real browser. Because the login/logout pages are generated by Spring Security, the test extracts the hidden `_csrf` from the HTML form. That is how to test real CSRF mechanics rather than bypassing them.

`src/test/java/demo/logout/LocalLogoutTests.java`:

```java
package demo.logout;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LocalLogoutTests {

    @Autowired
    WebTestClient client;

    private static String updatedSessionCookie(
            EntityExchangeResult<?> response, String earlier) {
        ResponseCookie cookie = response.getResponseCookies()
            .getFirst("SESSION");
        return cookie != null ? cookie.getValue() : earlier;
    }

    private static String csrfToken(String html) {
        assertNotNull(html, "Missing HTML form");
        Matcher tag = Pattern.compile(
            "(?is)<input\\b(?=[^>]*\\bname\\s*=\\s*['\\\"]_csrf['\\\"])[^>]*>")
            .matcher(html);
        assertTrue(tag.find(), "No hidden _csrf field");

        Matcher value = Pattern.compile(
            "(?i)\\bvalue\\s*=\\s*['\\\"]([^'\\\"]+)['\\\"]")
            .matcher(tag.group());
        assertTrue(value.find(), "No CSRF token value");
        return value.group(1);
    }

    private String signIn(String username, String password) {
        EntityExchangeResult<String> loginPage =
            client.get().uri("/login")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).returnResult();

        String cookie = updatedSessionCookie(loginPage, null);
        assertNotNull(cookie, "No login WebSession cookie");
        String csrf = csrfToken(loginPage.getResponseBody());

        EntityExchangeResult<byte[]> loggedIn =
            client.post().uri("/login")
                .cookie("SESSION", cookie)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("username", username)
                    .with("password", password)
                    .with("_csrf", csrf))
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectBody().returnResult();

        String location = loggedIn.getResponseHeaders()
            .getFirst(HttpHeaders.LOCATION);
        assertNotNull(location);
        // Login succeeded -> home page or saved protected URL.
        assertTrue(!location.contains("error"), "Login failed");
        return updatedSessionCookie(loggedIn, cookie);
    }

    @Test
    void anonymousVisitorIsRedirectedToLogin() {
        client.get().uri("/private/me")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().value(HttpHeaders.LOCATION,
                location -> assertTrue(location.contains("/login")));
    }

    @Test
    void formLoginCreatesUsableLocalSession() {
        String alice = signIn("alice", "alice123");
        client.get().uri("/private/me")
            .cookie("SESSION", alice)
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("signed-in:alice");
    }

    @Test
    void getLogoutIsOnlyAConfirmationPage() {
        String alice = signIn("alice", "alice123");

        client.get().uri("/logout")
            .cookie("SESSION", alice)
            .exchange()
            .expectStatus().isOk();

        client.get().uri("/private/me")
            .cookie("SESSION", alice)
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("signed-in:alice");
    }

    @Test
    void postLogoutWithoutCsrfIsRejected() {
        String alice = signIn("alice", "alice123");

        client.post().uri("/logout")
            .cookie("SESSION", alice)
            .exchange()
            .expectStatus().isForbidden();

        client.get().uri("/private/me")
            .cookie("SESSION", alice)
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("signed-in:alice");
    }

    @Test
    void logoutInvalidatesOnlyCurrentSession() {
        String alice = signIn("alice", "alice123");
        String bob = signIn("bob", "bob123");

        client.get().uri("/private/me")
            .cookie("SESSION", alice)
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("signed-in:alice");

        client.get().uri("/private/me")
            .cookie("SESSION", bob)
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("signed-in:bob");

        // Fetch logout confirmation form using Alice's exact WebSession.
        EntityExchangeResult<String> confirmation =
            client.get().uri("/logout")
                .cookie("SESSION", alice)
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).returnResult();

        alice = updatedSessionCookie(confirmation, alice);
        String token = csrfToken(confirmation.getResponseBody());

        client.post().uri("/logout")
            .cookie("SESSION", alice)
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("_csrf", token))
            .exchange()
            .expectStatus().is3xxRedirection();

        // Alice's old cookie/session must no longer grant access.
        client.get().uri("/private/me")
            .cookie("SESSION", alice)
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().value(HttpHeaders.LOCATION,
                location -> assertTrue(location.contains("/login")));

        // Bob's independent session remains valid.
        client.get().uri("/private/me")
            .cookie("SESSION", bob)
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("signed-in:bob");
    }
}
```

Run:

```bash
mvn test
```

With the class above, **5 tests** are expected to pass if the environment, versions, and cookie name match the example. This is sample code for readers to run themselves, **not confirmation that it was run in a real project**. Maven timings, logs, and session IDs are non-fixed data.

**HTML test limitation:** regex is merely a convenience for reading the hidden token on the demo's generated pages, not a production HTML parser; if using custom login pages, adjust token extraction accordingly. If the session cookie naming policy is not `SESSION`, update tests and app accordingly. The tests do not prove IdP JWT/refresh token revocation because the demo **has no IdP**.

### 10.1. Criteria for genuinely achieving local logout

- Before logout, protected endpoints return bodies tied to the right user.
- GET logout only renders confirmation, without losing access.
- POST logout **without CSRF** is rejected and the session remains usable.
- POST logout **with CSRF** succeeds.
- Subsequent protected requests reusing the old cookie are no longer authenticated.
- An independent browser/session is unaffected.

Merely deleting the browser cookie and watching the UI disappear **does not** prove the security context was invalidated on the server.

## 11. Illustrative Configurations for Token-Validating Resource Servers

These are **two alternative options** for a resource server, not two snippets to enable simultaneously inside the local form-login app in section 8.

### 11.1. Offline-verified JWT

If the resource server accepts JWTs:

```java
@Bean
SecurityWebFilterChain jwtApi(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

Example issuer configuration:

```properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://idp.example.invalid/issuer
```

This fragment depends on `spring-boot-starter-oauth2-resource-server`, a real issuer, and valid keys/discovery. Spring Security uses `ReactiveJwtDecoder` to verify signature/`iss`/`exp`/`nbf`; verify `aud` and scopes/roles per specific API. When the IdP revokes a refresh token, do not assume an offline JWT decoder knows about it.

### 11.2. Opaque token / introspection

If the API needs to query the IdP about each token's status:

```java
@Bean
SecurityWebFilterChain introspectingApi(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.opaqueToken(Customizer.withDefaults()))
        .build();
}
```

Example properties configured on a **separate** resource server:

```properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=https://idp.example.invalid/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id=resource-server-client
spring.security.oauth2.resourceserver.opaquetoken.client-secret=REPLACE_WITH_SECRET_FROM_VAULT
```

The hosts/secrets above are **non-working illustrations**; do not copy them expecting a runnable app without an IdP. Production uses a secret manager/environment variables and HTTPS; never commit client secrets to git. Resource Servers typically rely on `ReactiveOpaqueTokenIntrospector` to call introspection and map scopes to authorities. If the IdP returns `active=false`, the corresponding Bearer request must be rejected. Real systems also need latency benchmarks, timeout/retry policies, cache TTLs, and IdP load limits.

**Do not infer:** "Because `opaqueToken()` is enabled, local logout revokes tokens." Introspection is a **resource-server token check**, whereas revocation is an **authorization-server state-mutating operation**; they must be connected architecturally.

## 12. Cross-System Verification Matrix

To prove the three kinds of "logout" truly differ, tests should track **four observables**: app session, API access token, IdP refresh grant, and IdP SSO login session.

| Scenario | Web app session | API access token | IdP refresh token | OP/SSO session |
| --- | --- | --- | --- | --- |
| Normal user login | Present | May be valid | Usable | Present, if logged in via OIDC |
| **Local logout only** | Gone (for target session) | May still work | May still work | May still exist |
| Access JWT reaches `exp` | Unchanged | Rejected past expiry per validator/skew | May still work | Unchanged |
| Refresh token revoked | Unchanged | Already-issued offline JWT may work until expiry | Cannot refresh with revoked token | Unchanged |
| RP-Initiated OIDC logout | RP local logout per flow | Not guaranteed to invalidate all access tokens | Depends on provider/policy | OP handles logout |
| OIDC Back-Channel Logout to RP | RP destroys targeted sessions | Does not alter JWTs at all APIs | Does not automatically mean revocation | OP initiated event |
| Revocation + introspection `active=false` | Unchanged | API rejects introspected token per policy | Depends on grant/token | Unchanged |
| Custom-designed "log out everywhere" | Must destroy managed sessions | Must block all tokens per policy | Must revoke grants/refresh | Must log out OP/SSO and coordinate RPs |

The table intentionally uses **"may" / "depends"**: protocols do not automatically guarantee strict synchronization across independent systems.

### 12.1. Minimum test suite with a real IdP

1. **Local:** Log in via OIDC, capture session cookie; POST logout with valid CSRF; accessing a protected page with the old cookie must be rejected.
2. **SSO:** After local logout, attempt to start OIDC login again and observe whether the IdP prompts for credentials or reuses a live SSO session. This tests **OP state**, not token expiry.
3. **Access token:** Save a token before logout, call a real API before/after local logout; document whether continued acceptance matches design.
4. **Expiration:** Issue a short-TTL test token, call the API after `exp` and past allowed clock skew; verify 401/`invalid_token` rather than only reading payload timestamps.
5. **Refresh:** Use an old refresh token before and after revocation; after revocation it must not mint new access tokens. If using rotation, test reuse detection.
6. **RFC 7009:** Call the provider's revocation endpoint with an appropriately authenticated client; do not treat HTTP 200 as sufficient; verify introspection/refresh/API behavior afterward.
7. **OIDC RP-initiated:** Test `end_session_endpoint`, `post_logout_redirect_uri` allowlisting, and cases where the OP does not support logout.
8. **OIDC back-channel:** Send a **valid OP-signed** Logout Token via a test provider and verify corresponding sessions are destroyed; forged/wrong `aud`/`sid`/replayed tokens must be rejected.
9. **Two devices/three apps:** Verify sessions in other apps terminate **only if policy promises it**; never assume local logout logs out the entire network.
10. **IdP outage:** Test revocation/introspection timeouts, errors, and caches: fail-closed/availability per risk model, never opening APIs when the IdP fails.

For distributed systems, record propagation latency (P50/P95/P99 if SLAs exist) and maximum exposure windows. **"Immediate"** is a target to measure and engineer explicitly, not a free property of a Log out button.

## 13. Common Mistakes

### 13.1. Only deleting cookies without invalidating the server-side session

If the frontend deletes cookies while the backend keeps the session ID valid, a stolen copy of the cookie can still be used during the session's lifetime. Invalidate server-side `WebSession`/`SecurityContext` and handle cookies/CSRF per policy; never treat redirecting to `/login` as proof of logout.

### 13.2. Calling Servlet-style `SecurityContextHolder.clearContext()`

WebFlux uses `ReactiveSecurityContextHolder` and `ServerSecurityContextRepository` across reactive pipelines, not local `ThreadLocal`. Use appropriate `LogoutWebFilter`/`ServerLogoutHandler` and test over HTTP; do not call clear inside a controller while forgetting to persist/propagate changes for the next request.

### 13.3. Thinking a token with `exp` has been revoked

Expiration is checked against time. Revocation is an IdP state decision/index. The two events differ: a token can be revoked **before** `exp`; an expired token may never have been revoked. Define how resource servers learn revocation status.

### 13.4. Revoking a refresh token and assuming old access JWTs fail everywhere

Not automatically. Offline JWTs can be accepted until `exp` without a denylist, introspection, or extra signals. Near-real-time revocation requires designing resource servers and accepting latency/state costs.

### 13.5. Assuming IdP logout also clears every RP's session

Not guaranteed. Browser-based OP logout cannot guarantee delivering signals to every app; RPs can retain independent sessions. Back-channel/front-channel and session registries must be supported, synchronized, replay-protected, and tested per RP.

### 13.6. Using GET to mutate logout state

A GET link is easily triggered cross-site and weakens CSRF protection. For cookie/session apps, keep `POST /logout` + CSRF; if you want a UI button/link, submit a POST form with a valid token.

### 13.7. Casually storing refresh/access tokens in logs, query strings, or localStorage

Bearer tokens are credentials: anyone possessing the token can use it within its scope. Avoid logging full tokens; use secret vaults, protected storage, encryption at rest where appropriate, and least privilege. For web apps, consider BFF/secure session cookies instead of keeping long-lived refresh tokens in JavaScript when security requirements are high.

### 13.8. Confusing ID tokens with access tokens

`id_token` helps the RP verify OIDC authentication and must not be sent by default as an access token to APIs. ID token expiration does not mean access tokens were revoked, and revoking OAuth tokens does not necessarily clear the OP session.

### 13.9. Caching introspection infinitely or skipping checks when the IdP is offline

Caching `active=true` creates a window where revoked tokens are accepted. If the IdP goes offline, never silently bypass authentication to preserve UX; define clear downtime policies, monitoring, and appropriate fail-closed tests.

### 13.10. Failing to distinguish "this device" logout from "everywhere" logout

Each logout type needs a feasible contract: current session ID, all sessions of the user, grants/tokens of this client, or the entire OP session. Never display "Log out of all devices" if the server only deletes one cookie.

## 14. Process for Designing Logout in Real Applications

1. **Map roles:** Is the WebFlux web app an OAuth2 Client/RP or Resource Server, which IdP issues tokens, where is the session store, and do other apps share the same OP?
2. **Define the promise scope:** "Log out this session", "end SSO", or "revoke all access/refresh tokens"; align UI wording and security policy.
3. **Manage local sessions:** Use `LogoutWebFilter` and handlers to clear `SecurityContext` and invalidate `WebSession`; POST + CSRF, secure cookies, session timeouts.
4. **Manage OAuth2 tokens:** Track client token ownership, storage, TTL, rotation, and revocation on logout if policy demands; do not attempt to revoke tokens outside your client/user/authorization grant.
5. **Coordinate with the OP:** For OIDC RPs, consider RP-Initiated Logout; if the OP must proactively log out RPs, configure back-channel logout and registries, verifying token/session correlation.
6. **API token rejection mechanism:** Offline JWTs accept the TTL window or add introspection/denylists/versions; opaque/introspection needs clear timeout and cache policies. Never pass JWTs to `NoOpServerSecurityContextRepository` and imagine that revoked them at the IdP.
7. **Test along time boundaries:** Before/after local logout, before/after `exp`, before/after revocation, at OP logout time, across multiple apps/devices, and when the IdP is unreachable.
8. **Measure and observe:** Collect safe event metadata (no token secrets), request IDs, outcomes, 401/403 reasons; track revocation propagation latency.
9. **Document limits:** Explicitly document cases where access JWTs remain valid until `exp`, sessions in other apps may persist, and how fast access is guaranteed to stop.
10. **Periodic security reviews:** Upgrade Spring Security/Boot, audit cookies/sessions/CSRF, OIDC endpoints, JWKS rotation, refresh policies, and secret handling.

## 15. Self-Assessment Questions

**Question 1.** Alice logs out of the WebFlux website, yet a JWT access token with 5 minutes left still calls the API. Is that necessarily a Spring Security bug?  
**No.** The website may have invalidated only the local `WebSession`, while the API verifies JWTs offline. That is a consequence of **policy/architecture**; if immediate blocking is required, design introspection/denylists or another mechanism.

**Question 2.** Does access token `exp` expiration automatically delete the website's `SESSION` cookie?  
**No.** The application session is separate state with its own timeouts, revocation, and security.

**Question 3.** What is the most certain meaning of revoking a refresh token at the IdP?  
The client can no longer use the **revoked refresh token** to obtain new access tokens. Its effect on already-issued access tokens depends on the IdP/resource server and verification mechanism.

**Question 4.** Why does HTTP 200 from the revocation endpoint not guarantee an API has stopped accepting a JWT?  
RFC 7009 returns 200 even when tokens are already invalid, and resource servers validating JWTs offline may not yet know the revocation status.

**Question 5.** Is RP-Initiated Logout equivalent to RFC 7009 revocation?  
**No.** One coordinates ending the **SSO session at the OP** via browser redirects; the other asks the AS to **invalidate tokens/grants**.

**Question 6.** What problem does OIDC Back-Channel Logout solve?  
The OP proactively sends a verified Logout Token so the RP finds and destroys **matching sessions**, even when the browser did not call logout directly at the RP. It does not automatically invalidate all JWTs.

**Question 7.** Why should `GET /logout` not destroy the session directly?  
Because cross-site GETs are easily triggered unintentionally; POST with proper CSRF mitigates logout CSRF risk.

**Question 8.** How do you prove local logout actually works?  
Log in, read a protected resource, POST logout with CSRF, then call the protected resource again with the **old cookie** and receive a login redirect/401 instead of the old content.

**Question 9.** If `WebSessionServerLogoutHandler` is already configured, are all of Alice's other tabs/browsers logged out?  
**Not automatically.** It invalidates the **current `WebSession`**; global logout requires a session index/coordinator by design.

**Question 10.** How do introspection `active=false` and JWT `exp` differ?  
`active=false` is the result of a live status check at the AS for the token/grant; `exp` is a time limit inside the token's claims that an RS can check offline. Policies, latencies, and data sources differ.

### Official documentation

- Spring Security Reactive, *Logout*: https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/logout.html
- Spring Security Reactive, *CSRF and Logout*: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security Reactive, *OIDC Logout (Local, RP-Initiated, Back-Channel)*: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html
- Spring Security Reactive, *OAuth2 Resource Server JWT*: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security Reactive, *Opaque Token Introspection*: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html
- Spring Security API, `WebSessionServerLogoutHandler`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/logout/WebSessionServerLogoutHandler.html
- IETF RFC 7009, *OAuth 2.0 Token Revocation*: https://www.rfc-editor.org/rfc/rfc7009
- IETF RFC 7662, *OAuth 2.0 Token Introspection*: https://www.rfc-editor.org/rfc/rfc7662
- OpenID Connect, *RP-Initiated Logout*: https://openid.net/specs/openid-connect-rpinitiated-1_0.html
- OpenID Connect, *Back-Channel Logout*: https://openid.net/specs/openid-connect-backchannel-1_0.html

**Summary:** Local logout clears the **application's context and session**; access/refresh token expiry bounds **credential lifetime**; IdP revocation and OIDC logout act on **token issuance state or SSO sessions** per protocol and provider policy. Achieving "system-wide effective logout" requires coordinating all parties, designing how Resource Servers receive revocation signals, and testing actual behavior at each boundary.