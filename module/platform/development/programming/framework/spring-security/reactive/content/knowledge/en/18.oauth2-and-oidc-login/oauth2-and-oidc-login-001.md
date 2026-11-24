# The Role of a WebFlux Application When Using OAuth2 Login and OpenID Connect

**Module:** Spring Security – reactive (Spring WebFlux)  
**Section:** OAuth2/OIDC Login  
**Objective:** Accurately identify that a WebFlux application plays the **role of an OAuth 2.0 Client / OpenID Connect Relying Party**, understand what it does in the Authorization Code flow, distinguish the application from the Authorization Server/Identity Provider and Resource Server, configure `oauth2Login()`, manage principal/session/tokens, and test the proper boundaries.

A Spring WebFlux application with a **“Sign in with Google”** button does not itself become the token issuer or verify Google passwords. It acts as a **Client** of an Authorization Server and, when using OpenID Connect, acts as a **Relying Party (RP)** that trusts authentication information verified by an **OpenID Provider (OP)**. WebFlux redirects the browser to the OP, handles the callback containing the authorization code, exchanges the code for tokens **on the server side**, verifies identity according to the protocol, and creates an `Authentication` for the application's local session.

**Remember:** `oauth2Login()` handles **login for a web application**. `oauth2Client()` supports **calling external APIs with an access token**. `oauth2ResourceServer()` is used when **your own API receives a Bearer token from a client**. These features can coexist in the same system, but they are **not equivalent**. Issuing tokens, managing SSO sessions, and managing users' primary credentials belong to the **Authorization Server/OP/IdP** (or a separate product such as Spring Authorization Server).

## 1. Role Map: Who Does What?

In OAuth 2.0, the roles are Resource Owner, Client, Authorization Server, and Resource Server. OpenID Connect (OIDC) adds the identity login layer: OpenID Provider (OP), Relying Party (RP), ID Token, and identity verification mechanisms.

| Role | Primary Responsibility | Example in a WebFlux Login Scenario |
| --- | --- | --- |
| Resource Owner / End User | The person who owns the account, performs login, and grants consent in the flow | A user opening your website |
| **OAuth2 Client** | Requests authorization, receives the callback, exchanges the authorization code, manages issued access tokens | **Your Spring WebFlux application** |
| **OIDC Relying Party (RP)** | Relies on authentication from the OP, verifies the ID Token, creates the user principal for the website | **Also the WebFlux application when scope includes `openid`** |
| Authorization Server (AS) | Manages authorization requests, issues authorization codes and OAuth2 access/refresh tokens | Google Identity service / enterprise IdP |
| OpenID Provider (OP) | An AS supporting OIDC that authenticates users and issues `id_token`, and may provide UserInfo | Google or an OP configured and trusted by the organization |
| Resource Server | Protects APIs/resources by validating incoming Bearer access tokens | CRM API, reporting API, private data |
| Browser (user agent) | Follows redirects between RP and OP, stores each site's cookies per policy | The user's Chrome/Firefox |
| API Gateway/BFF | If present, fronts or protects the browser/backend boundary | Gateway in front of WebFlux, not itself an OP |

**Direct answer to this lesson's question:** When you write `http.oauth2Login(...)` in **Spring WebFlux**, the application is normally an **OAuth2 Client and OIDC RP**, not an OP, Authorization Server, or necessarily a Resource Server. Having it simultaneously play another role must be configured/implemented intentionally.

### 1.1. Comparing Three Commonly Confused Configurations

| Spring Security WebFlux DSL | Role It Serves | Primary Input Data | Result |
| --- | --- | --- | --- |
| `oauth2Login(Customizer.withDefaults())` | Web app login / RP | Callback `code` + `state`, exchanged with the OP | `OAuth2AuthenticationToken`, typically with `OidcUser`; website session |
| `oauth2Client(Customizer.withDefaults())` | OAuth2 Client to obtain/use access tokens | Client registration, authorized client/grants | Access token for outbound `WebClient` |
| `oauth2ResourceServer(oauth -> oauth.jwt(...))` | Resource Server | Inbound `Authorization: Bearer ...` | Verifies JWT token, creates Authentication for the API |
| Spring Authorization Server (separate project) | Authorization Server/OP if configured for OIDC | Login/consent/token requests | Issues tokens, metadata/JWK endpoints, protocol endpoints |

`oauth2Login` **is a feature of OAuth2 Client**, not a capability completely separate from OAuth2 Client. However, enabling `oauth2Client` **alone** does not automatically provide a user login screen.

### 1.2. Example of Two Systems in the Same Product

A website `https://portal.example.test` uses WebFlux, and users sign in via an OP. Afterward, the portal server needs to call `https://reports.example.test` to fetch the user's reports:

```text
        Browser (portal's SESSION cookie)
                  |
                  v
      +-------------------------+
      | Spring WebFlux Portal   |
      | OAuth2 Client / OIDC RP |
      | OAuth2 Login            |
      | WebSession + Principal  |
      +-------+-----------+-----+
              |           |
  Code flow   |           | Access token in outbound request
              v           v
       +-----------+   +----------------+
       | OIDC OP / |   | Reports API    |
       | IdP / AS  |   | Resource Server|
       +-----------+   +----------------+
```

The browser does not necessarily hold the access token. In a server-side web application (BFF) architecture, access/refresh tokens are typically managed by the backend client, and WebFlux uses a **session cookie** to identify the browser. When WebFlux calls the Reports API, it can attach the Bearer token **on the server-side outbound call**. The two paths “browser → portal” and “portal → Reports API” use different credential mechanisms.

## 2. Distinguishing OAuth 2.0 and OpenID Connect

**OAuth 2.0** is a resource access authorization framework. An `access_token` is intended for a **Resource Server** to accept within the granted scope; it **does not by itself provide a complete standardized identity login** merely by existing.

**OpenID Connect 1.0** builds on OAuth 2.0 and uses the `openid` scope to request standardized login. In the appropriate flow, the OP issues an **ID Token** containing claims about the authentication event and the end user. The RP application validates the ID Token according to OIDC rules before relying on its `sub`/claims as an identity.

| Value | What Is It Used For? | Who Should Use It? | What Not to Do |
| --- | --- | --- | --- |
| `authorization_code` | Short-lived grant for the Client to exchange for tokens at the token endpoint | WebFlux backend in the code flow | Do not use the code as a session or to call APIs |
| `state` | Binds the authorization response to the initiating request, preventing login CSRF/mix-up in the flow | OAuth2 Client/RP | Do not treat it as an access token |
| `code_verifier`/`code_challenge` (PKCE) | Binds the code exchanger to the holder of the verifier; mitigates code interception | Client + Authorization Server | Do not use PKCE to replace `state`, `nonce`, or client registration checks |
| `nonce` (OIDC) | Binds the ID Token to the authentication request session, reducing replay/substitution | RP and OP per profile | Do not generate it and then skip validation |
| **`id_token`** | Proof of identity authentication for the **RP**, usually a signed JWT | RP/Client | **Do not send it as an access token** to APIs |
| **`access_token`** | Credential for APIs/resource servers per `scope`/`aud` | OAuth2 Client sending to a Resource Server | Do not misuse it as proof of login |
| `refresh_token` (if issued) | Requests a new access token from the AS per policy | Client permitted to hold it | Do not send it to Resource Servers/browsers unnecessarily |
| Browser session cookie | Maintains authentication **locally at the WebFlux website** | Browser and RP | Do not assume cookie = access token |

### 2.1. What Changes Just by Adding the openid Scope?

Spring Security OAuth2 Login inspects the registration/scopes. When a registration uses `openid`, the flow is handled as OIDC: the RP gets an `OidcUser`/`OidcIdToken` and uses a service such as `OidcReactiveOAuth2UserService`. If the provider does not support OIDC and there is no `openid` scope, OAuth2 Login can fall back to an OAuth2 UserInfo service and `OAuth2User`; in that case **there is no standard OIDC ID Token**. Both cases can produce an `OAuth2AuthenticationToken` for the website, but the trustworthiness of claims and how attributes are retrieved differ.

Merely receiving `email` or `name` from an OAuth2 endpoint does not prove the user was authenticated via OIDC. Email addresses can change; `sub` (combined with a trusted `iss`) is more stable as an internal identifier. Do not use a bare email as the sole unique key across all providers/tenants.

## 3. OIDC Authorization Code Login Lifecycle

Assume the `registrationId` is `google`:

```text
(1) Browser -> WebFlux:
    GET /oidc/me  [no logged-in SESSION yet]
        |
        v
(2) WebFlux Security:
    not authenticated yet -> redirect to /login page
    or direct link /oauth2/authorization/google
        |
        v
(3) WebFlux OAuth2 Client:
    create authorization request:
      response_type=code
      client_id=...
      redirect_uri=https://portal.../login/oauth2/code/google
      scope=openid profile email
      state=...
      nonce=... (OIDC)
      PKCE params if configured/required
    save request correlation context in WebSession/repository
        |
        v
(4) Browser follows redirect to Google/OP authorization endpoint:
    user login/consent at OP (do not send Google password to WebFlux)
        |
        v
(5) OP -> Browser -> WebFlux callback:
    GET /login/oauth2/code/google?code=...&state=...
        |
        v
(6) WebFlux OAuth2 Login filter:
    verify state/session + code flow
    backend POSTs code to OP token endpoint over HTTPS
    receive access_token + id_token (+ optional refresh_token)
    verify OIDC ID Token per provider/config
    (claims/nonce/JWS/issuer/audience/time per flow)
    may call UserInfo if needed and supported
        |
        v
(7) Spring Security:
    create OidcUser / OAuth2AuthenticationToken
    save/restore SecurityContext per WebSession config
    manage related OAuth2AuthorizedClient tokens
    redirect user back to saved request or success URL
        |
        v
(8) Browser GET /oidc/me with portal session cookie:
    Spring Security loads Authentication for portal session
    endpoint returns safe info, does not expose tokens
```

**Default paths to remember:**

- Start flow: `/oauth2/authorization/{registrationId}`, for example `/oauth2/authorization/google`.
- Callback receiving code: `/login/oauth2/code/{registrationId}`, for example `/login/oauth2/code/google`.
- Provider selection page: usually `/login`, generated by Spring Security when matching registrations exist.
- The redirect URI on the OP side **must match exactly** the registered RP callback; scheme/host/port/path mismatches are a common reason Google/OP rejects the request.

These endpoints are handled by security WebFilters; you do not need to write a `@GetMapping("/login/oauth2/code/google")` controller to exchange the code for tokens. **Never put the client secret in the browser/JavaScript.**

### 3.1. Browser Role vs. WebFlux Role

The browser sends the user to the OP and back to the RP; the **WebFlux backend** performs the token exchange using `authorization_code` (in the confidential web client model). The browser may briefly see `code`/`state` in the callback URL, but should not receive the client secret or refresh token. Spring Security manages correlation and authentication processing; sample code does not need to manually parse the callback in a controller or log the code.

### 3.2. state, nonce, and PKCE Are Not the Same Variable

- **`state`:** Binds the initiated flow to the callback, detecting unsolicited callbacks. If a user opens two login tabs, session/correlation must be handled properly; never disable the `state` check to “fix” a callback error.
- **`nonce`:** The OIDC RP sends a nonce per policy and compares it with the claim in the ID Token, reducing replay/token substitution risks. Never disable nonce validation.
- **PKCE:** When the client/OP uses PKCE, the authorization request carries `code_challenge` and the token request carries `code_verifier`. For public clients, PKCE is especially important; confidential clients should also use it where supported/required by policy. Do not assume every Spring configuration/version generates PKCE identically; inspect the actual requests and provider registration.
- **HTTPS + exact redirect URI:** Protects codes/tokens from leakage and reduces open redirects; do not use arbitrary wildcard redirect URIs.

**If `state` is missing or invalid:** the callback must not be recognized as a completed login. If the ID Token fails `iss`/`aud`/signature/time/`nonce` checks: a valid authenticated session must not be created. Never “skip signature verification” just to get a failing flow to run.

## 4. What Components Does Spring Security WebFlux Provide?

| Component | Responsibility | What Not to Misunderstand |
| --- | --- | --- |
| `ServerHttpSecurity.oauth2Login(...)` | Configures the reactive OAuth2/OIDC browser-login flow | Does not turn the RP into an AS/OP |
| `ReactiveClientRegistrationRepository` | Stores/looks up `ClientRegistration` by registrationId, client id, provider endpoints, scopes | Not a user account database |
| `ClientRegistration` | Describes an app registered with an OP/AS | Does not hold individual users' login sessions |
| `ServerOAuth2AuthorizationRequestResolver` and authorization-request repository | Creates/stores authorization requests, helping correlate `state`/flow | Does not store business transactions |
| `OAuth2AuthenticationToken` | Authentication after OAuth2/OIDC login | Not identical to `JwtAuthenticationToken` of a Resource Server |
| `OidcUser` / `OidcIdToken` | Processed principal and ID Token in an OIDC flow | Not a Bearer token for every API |
| `DefaultReactiveOAuth2UserService` | Fetches user attributes for non-OIDC OAuth2 | Does not itself perform login using an OIDC ID Token |
| `OidcReactiveOAuth2UserService` | Processes OIDC user, may call UserInfo | Does not issue access tokens |
| `ServerSecurityContextRepository` / WebSession | Persists local Authentication across browser HTTP requests | Not where the OP manages its SSO session |
| `OAuth2AuthorizedClient` | Combines client registration + principal name + access token/optional refresh token | Not a public user profile |
| `ServerOAuth2AuthorizedClientRepository` / `ReactiveOAuth2AuthorizedClientService` | Stores/reads authorized clients by design | Does not automatically revoke all tokens on local logout |
| `ReactiveOAuth2AuthorizedClientManager` | Coordinates issuing/refreshing authorized client tokens when configured | Does not replace domain-level permission checks in the app |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Intentionally attaches a Bearer token to **outbound WebClient** calls | Should not automatically attach tokens to every URL |
| `OAuth2ResourceServerSpec` | Protects **inbound** APIs with Bearer tokens | Not a mechanism to automatically create website login |

### 4.1. Three Types of Data Commonly Misplaced

**ClientRegistration** is the application's configuration with a provider (client ID, secret, endpoints, scopes, redirect URI). An app can have multiple registrations, such as Google and an internal IdP.

**SecurityContext** answers “who does the application currently consider this browser request to be?”. In a session-based website, the context is usually kept in WebSession and can be read from `ReactiveSecurityContextHolder`.

**OAuth2AuthorizedClient** answers “which authorization/tokens is the application holding for this registration and principal to call APIs?”. Access/refresh tokens live in this layer per provider policy and storage. Never expose it in the profile JSON returned to the browser. An application might have a logged-in session without yet having a new token for another API, or have a token while the session has been invalidated; their lifecycles must be managed separately.

### 4.2. Reactor Context Remains the Source of Authentication in the Pipeline

WebFlux processes requests on a non-blocking pipeline. When reading the principal in a service, use `ReactiveSecurityContextHolder` or a Spring-supported method parameter; **never** read the user from a static variable or Servlet's `ThreadLocal SecurityContextHolder`:

```java
Mono<String> currentName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
}
```

This is a fragment that requires imports. A single WebFlux thread can serve multiple users interleaved; Reactor Context is bound to the subscription/request. Avoid calling a detached `subscribe()` or `block()` inside a handler.

## 5. After Login, Is Authentication an Access Token?

**No.** After OAuth2/OIDC login, Spring Security typically has an `OAuth2AuthenticationToken` with an `OAuth2User` or `OidcUser` principal. The website can use a `SESSION` cookie to maintain Authentication across HTTP requests. The access token is kept in the authorized client store so WebFlux can **call APIs** when business logic requires it.

Comparison:

| Scenario | Inbound Cookie/Authorization to WebFlux | Typical Authentication | Credential Verifier |
| --- | --- | --- | --- |
| User using an OIDC-logged-in RP website | `Cookie: SESSION=...` | `OAuth2AuthenticationToken` with `OidcUser` | WebFlux reads established WebSession/SecurityContext |
| Resource Server API receiving a JWT | `Authorization: Bearer ...` | `JwtAuthenticationToken` | JWT decoder verifies token |
| Resource Server API receiving an opaque token | `Authorization: Bearer ...` | `BearerTokenAuthentication` | Introspection/opaque token validator |
| Browser using HTTP Basic | `Authorization: Basic ...` | `UsernamePasswordAuthenticationToken` or per manager | Basic authentication manager |
| OP/IdP handling user login | OP-specific credentials/state | Per OP implementation | OP, **not the WebFlux RP** |

The same user can have an **SSO session at the OP** and a **local session at the RP**. Local logout typically ends an RP session without automatically terminating the OP's SSO session or revoking access/refresh tokens. Separate OIDC RP-Initiated Logout/Back-Channel Logout and revocation mechanisms are needed when product requirements call for them.

## 6. Standalone Java 17 Model: Identifying Roles in Clear Terms

Before configuring the framework, try the small program below. It does not perform real OAuth2/OIDC or verify JWTs; it only illustrates the roles of the components.

Save `OAuth2RoleDemo.java`:

```java
import java.util.List;

public class OAuth2RoleDemo {
    record Component(String name, String role) {}

    public static void main(String[] args) {
        List<Component> architecture = List.of(
            new Component("Browser", "User Agent"),
            new Component("WebFlux Portal", "OAuth2 Client / OIDC RP"),
            new Component("Identity Provider", "Authorization Server / OP"),
            new Component("Reports API", "Resource Server")
        );

        architecture.forEach(component ->
            System.out.println(component.name() + " -> " + component.role())
        );
    }
}
```

Run with JDK 17+:

```bash
javac OAuth2RoleDemo.java
java OAuth2RoleDemo
```

**Exact stdout:**

```text
Browser -> User Agent
WebFlux Portal -> OAuth2 Client / OIDC RP
Identity Provider -> Authorization Server / OP
Reports API -> Resource Server
```

This is a classification exercise, not an OAuth2 implementation. **Do not** hand-roll code to exchange authorization codes or verify ID Tokens by merely Base64-decoding them; the next sections use real Spring Security.

## 7. Spring Boot WebFlux Java 17+ App Configured for OAuth2/OIDC Login

We will build a WebFlux website with these routes:

- `GET /` is public, returning `public-home`.
- `GET /oidc/me` requires a user logged in **via OIDC**, returning JSON with `sub`, registration ID, and principal type, **without returning raw ID Tokens/access tokens**.
- `GET /oidc/admin` is allowed only for `ROLE_ADMIN`, illustrating that successful login **is not enough** to obtain business roles.
- `POST /oidc/preferences` simulates a mutation using WebSession, so it **still requires a CSRF token**.
- The `/login` page and authorization-start `/oauth2/authorization/google` are generated/handled by Spring Security.
- Callback `/login/oauth2/code/google` is handled by a Spring Security WebFilter.
- Local logout keeps the default mechanism; OP logout is only added if supported by the provider (section 11).

**Prerequisites to run:** You can start the app with dummy client id/secret, view the login page and initiate the redirect, and run `mockOidcLogin()` tests **without calling a real OP**. To **complete a real Google login**, you must have a valid OAuth client ID/secret issued by Google, a matching redirect URI configuration, and connectivity to the provider. Do not claim real login works with dummy credentials.

### 7.1. Project Structure

```text
webflux-oidc-rp/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/oidc/
    │   │   ├── OidcRpApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ProfileController.java
    │   └── resources/application.properties
    └── test/java/demo/oidc/
        └── OidcRpTests.java
```

The example uses **Java 17+, Maven, and Spring Boot 3.5.7**. That is a dependency baseline for the curriculum; in real deployments, choose a still-supported version with security patches. Do not add `spring-boot-starter-web` because this lesson uses WebFlux, not Servlet MVC.

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
    <artifactId>webflux-oidc-rp</artifactId>
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

### 7.2. Properties: ClientRegistration Named google

`src/main/resources/application.properties`:

```properties
spring.application.name=webflux-oidc-rp
server.port=8080

# CommonOAuth2Provider.GOOGLE provides common endpoints by default.
# Replace with real client ID/secret via environment before real login.
spring.security.oauth2.client.registration.google.client-id=${GOOGLE_CLIENT_ID:training-client-not-valid}
spring.security.oauth2.client.registration.google.client-secret=${GOOGLE_CLIENT_SECRET:training-secret-not-valid}
spring.security.oauth2.client.registration.google.authorization-grant-type=authorization_code
spring.security.oauth2.client.registration.google.scope=openid,profile,email
spring.security.oauth2.client.registration.google.redirect-uri={baseUrl}/login/oauth2/code/{registrationId}
```

`${...}` in the Markdown source is replaced with Spring property placeholder syntax `${...}` in the saved content. The default values `training-...-not-valid` only keep the configuration well-formed; they are **not real credentials**. When switching to an enterprise provider, set `spring.security.oauth2.client.registration.<id>.provider=<providerId>` and `spring.security.oauth2.client.provider.<providerId>.issuer-uri=https://trusted-idp.example/...` per OIDC Discovery. Only trust the issuer/metadata/JWK of an approved provider.

**With Google:** Register the **exact** redirect URI `http://localhost:8080/login/oauth2/code/google` for local testing in Google Cloud Console (provider policies may restrict URI/client types). When running behind HTTPS/Ingress, `{baseUrl}` must reflect the right host/scheme; only accept forwarded headers from trusted proxies, never blindly trust `X-Forwarded-Host` from the Internet.

### 7.3. Application Entry Point

`src/main/java/demo/oidc/OidcRpApplication.java`:

```java
package demo.oidc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OidcRpApplication {
    public static void main(String[] args) {
        SpringApplication.run(OidcRpApplication.class, args);
    }
}
```

### 7.4. SecurityConfig: Website as an OIDC RP

`src/main/java/demo/oidc/SecurityConfig.java`:

```java
package demo.oidc;

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
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/", "/signed-out").permitAll()
                .pathMatchers("/login",
                    "/oauth2/authorization/**",
                    "/login/oauth2/code/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/oidc/admin")
                    .hasRole("ADMIN")
                .pathMatchers("/oidc/**").authenticated()
                .anyExchange().denyAll())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            // Default CSRF remains enabled for browser session POSTs.
            .build();
    }
}
```

**Reading the config:**

1. `@EnableWebFluxSecurity` enables reactive security WebFilters. `ServerHttpSecurity` is the WebFlux DSL; avoid confusing it with Servlet `HttpSecurity`/`SecurityFilterChain`.
2. `oauth2Login` provides authorization code + OIDC login for the website; `oauth2Client` enables authorized-client integration, e.g., `WebClient` calling upstream APIs.
3. The login start and callback paths are permitted so the dedicated filters can handle the flow; `/oidc/**` is not granted to unauthenticated users.
4. `/oidc/admin` requires `ROLE_ADMIN`. OIDC login **does not automatically grant the ADMIN role to every account**; you must design trusted role mapping per enterprise policy if needed.
5. `anyExchange().denyAll()` blocks undefined routes. Default CSRF for session POSTs is kept enabled; do not call `csrf.disable()` just because the website uses OAuth2.
6. The app is an OAuth2 Client/RP. There is **no** JWT issuance configuration, AS token endpoint, or `oauth2ResourceServer(jwt)` for inbound bearer tokens.

### 7.5. Controller: Returning Only Necessary Information from OidcUser

`src/main/java/demo/oidc/ProfileController.java`:

```java
package demo.oidc;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
public class ProfileController {

    public record IdentityView(
        String subject,
        String registrationId,
        String principalType
    ) {}

    @GetMapping(value = "/", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> publicHome() {
        return Mono.just("public-home");
    }

    @GetMapping(value = "/signed-out",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> signedOut() {
        return Mono.just("signed-out");
    }

    @GetMapping(value = "/oidc/me",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<IdentityView> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .flatMap(authentication -> {
                if (!(authentication instanceof OAuth2AuthenticationToken oauth)
                        || !(oauth.getPrincipal() instanceof OidcUser oidc)) {
                    return Mono.error(new ResponseStatusException(
                        HttpStatus.FORBIDDEN, "OIDC login required"));
                }

                // Do not return raw id_token, access_token, refresh_token
                // or all OIDC claims to the browser.
                return Mono.just(new IdentityView(
                    oidc.getSubject(),
                    oauth.getAuthorizedClientRegistrationId(),
                    "OIDC_USER"
                ));
            });
    }

    @GetMapping(value = "/oidc/admin",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> admin() {
        return Mono.just("admin-only");
    }

    @PostMapping(value = "/oidc/preferences",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> preferences() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .map(name -> "saved:" + name);
    }
}
```

`OidcUser.getSubject()` is the identifier from the ID Token scoped to the OP; if the application supports multiple OPs/tenants, store the identity keyed by **(issuer, subject)** rather than relying on email alone. The demo API returns `subject` for learning purposes; production systems must classify PII and restrict responses by authorization.

**Never** return `OidcUser.getIdToken().getTokenValue()` or `OAuth2AuthorizedClient.getAccessToken().getTokenValue()` in a profile response merely for debugging convenience. Tokens are credentials or contain sensitive claims. If observability is needed, log safe metadata (issuer, registrationId, status), never tokens.

## 8. Testing Without a Real OP Using mockOidcLogin and WebTestClient

There are **two test layers** to distinguish:

- **In-memory WebFlux security test**: `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` and `mutateWith(mockOidcLogin())` simulate the Authentication/authorized client, proving that the controller and authorization policy work. It does **not** go out to the Internet, does not exchange a real authorization code, and does not verify tokens from an OP.
- **End-to-end with a real OP or protocol-compliant mock OP**: the browser goes through `/oauth2/authorization/google`, `state`/`nonce`/PKCE are managed properly, the OP calls the callback, and the backend exchanges the code, verifies the ID Token/JWK/claims, and establishes a session. This requires a suitable OP environment; you cannot just mock an OidcUser and consider all of OAuth2 verified.

Add the `spring-security-test` dependency as shown in `pom.xml` above. Because `mockOidcLogin()` works on a **WebTestClient bound to the application context**, do not use an HTTP client calling a real server and expect the mutator to fake a session on the server side.

`src/test/java/demo/oidc/OidcRpTests.java`:

```java
package demo.oidc;

import java.net.URI;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOAuth2Login;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOidcLogin;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class OidcRpTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicHomeIsAccessibleWithoutLogin() {
        client.get().uri("/")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public-home");
    }

    @Test
    void anonymousProtectedResourceNeedsLogin() {
        client.get().uri("/oidc/me")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().value(HttpHeaders.LOCATION,
                location -> assertTrue(location.contains("/login")));
    }

    @Test
    void generatedLoginPageContainsGoogleAuthorizationLink() {
        client.get().uri("/login")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .value(html -> assertTrue(
                html.contains("/oauth2/authorization/google")));
    }

    @Test
    void authorizationStartRedirectsToProviderWithState() {
        client.get().uri("/oauth2/authorization/google")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().value(HttpHeaders.LOCATION, location -> {
                URI destination = URI.create(location);
                assertEquals("https", destination.getScheme());
                assertEquals("accounts.google.com", destination.getHost());
                assertNotNull(destination.getRawQuery());
                assertTrue(destination.getRawQuery()
                    .contains("response_type=code"));
                assertTrue(destination.getRawQuery()
                    .contains("state="));
                assertTrue(destination.getRawQuery()
                    .contains("client_id="));
            });
    }

    @Test
    void mockOidcPrincipalIsVisibleToReactiveController() {
        client.mutateWith(mockOidcLogin())
            .get().uri("/oidc/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("user")
            .jsonPath("$.principalType").isEqualTo("OIDC_USER")
            .jsonPath("$.registrationId").exists();
    }

    @Test
    void plainOAuth2UserIsNotAccidentallyTreatedAsOidcUser() {
        client.mutateWith(mockOAuth2Login())
            .get().uri("/oidc/me")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void oidcLoginDoesNotAutomaticallyGrantAdminRole() {
        client.mutateWith(mockOidcLogin())
            .get().uri("/oidc/admin")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void explicitlyMappedAdminAuthorityCanEnterAdminRoute() {
        client.mutateWith(mockOidcLogin().authorities(
                new SimpleGrantedAuthority("ROLE_ADMIN")))
            .get().uri("/oidc/admin")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin-only");
    }

    @Test
    void oidcBrowserPostWithoutCsrfIsRejected() {
        client.mutateWith(mockOidcLogin())
            .post().uri("/oidc/preferences")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void oidcBrowserPostWithCsrfIsAccepted() {
        client.mutateWith(mockOidcLogin())
            .mutateWith(csrf())
            .post().uri("/oidc/preferences")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("saved:user");
    }
}
```

Run:

```bash
mvn test
```

**Target: 10 tests** for the project above in an appropriate environment. This is an example for learners to run; **do not claim Maven has already been run or Google login has been tested on your system**. When encountering version-specific differences, read the response/debug output and cross-check the corresponding Spring Security version API. If the generated login page or Google endpoint changes due to the provider/framework, adjust the expected condition according to the verified configuration rather than altering permission rules just to make the test pass.

### 8.1. What the Test Suite Proves, and What It Does Not Prove

| Test | Proves | Does Not Prove |
| --- | --- | --- |
| Public 200 / anonymous redirect | Routing and login requirement in the WebFlux chain | That the user is logged in at the OP |
| Generated login page / authorization start | Registration ID `google` is linked to the authorization endpoint; URL has `state` | That the OP actually issues a valid code |
| `mockOidcLogin()` returns subject | The controller handles `OidcUser` properly in the Reactor/Authentication context | That the provider's ID Token was actually verified |
| `mockOAuth2Login()` is rejected on OIDC-only endpoint | Distinction between `OAuth2User` and `OidcUser` | That all providers support OIDC |
| Default role gets 403 / test ADMIN role gets 200 | Authorization rules work | That provider claims are mapped to ADMIN in production |
| POST without/with CSRF | Cookie-style web mutations retain CSRF protection | That cross-site browser/proxy production setups are always correct |

In particular, `mockOidcLogin()` intentionally **skips token exchange/cryptographic verification**. Do not use that test in place of an e2e suite covering `state`/`nonce`/PKCE, issuer/audience, callback URI, token expiry, logout, and OP failure cases. Real testing must use a trusted test OP or a registered sandbox/provider environment.

## 9. Trying Real OIDC Login with Google

### 9.1. Preparation

- Create an OAuth2 **Web application client** on the provider; obtain `client-id` and `client-secret`, and manage the secret in an environment/secret store.
- Register the **exact** authorized redirect URI `http://localhost:8080/login/oauth2/code/google` when testing locally. For production, use HTTPS and a controlled base URL.
- If the provider requires an OAuth consent screen/test users, configure it per environment; review provider policies and approved scopes.
- Start the app with real environment variables:

```bash
# Bash/Linux/macOS:
export GOOGLE_CLIENT_ID='your-issued-client-id'
export GOOGLE_CLIENT_SECRET='your-issued-client-secret'
mvn spring-boot:run
```

On PowerShell:

```powershell
$env:GOOGLE_CLIENT_ID = "your-issued-client-id"
$env:GOOGLE_CLIENT_SECRET = "your-issued-client-secret"
mvn spring-boot:run
```

The two strings `your-issued-...` are **placeholders that must be replaced** with values from the provider; do not copy them verbatim. In an organizational environment, use a secret manager instead of typing real credentials into shell history. Never commit `client-secret` to Git or send it to the browser.

### 9.2. Browser Journey

1. In an incognito window, open `http://localhost:8080/oidc/me`. Without local authentication → the browser goes to `/login`.
2. Choose the Google provider (or open `http://localhost:8080/oauth2/authorization/google`). In DevTools/Network, observe the `302` to Google's authorization endpoint; the URI has `client_id`, `redirect_uri`, `response_type=code`, `scope=openid...`, `state`, and potentially `nonce`/PKCE parameters.
3. Log in at **OP/Google** and complete consent per policy. The browser is redirected back to callback `/login/oauth2/code/google?code=...&state=...`.
4. WebFlux Security validates the flow, calls the OP's token endpoint **server-to-server**, processes the ID Token/UserInfo, and creates a local session. The browser returns to `/oidc/me`.
5. The `/oidc/me` body displays JSON with `subject` and `registrationId`; it **does not** display raw tokens. Verify the session cookie is set with the appropriate policy.
6. Call `/oidc/admin` with a regular OIDC account; receive **403** if no `ROLE_ADMIN` authority mapping exists. This is correct: an authenticated identity does not automatically grant admin privileges.
7. Try `POST /oidc/preferences` without a CSRF token: receive **403**. Only a properly constructed request from a same-origin UI with a valid CSRF token is allowed, with an authenticated session.
8. Perform local logout and then access `/oidc/me` with the old session: it must require logging in again. If the OP SSO session is still active, re-initiating login may complete quickly without prompting for a password; that **does not** mean local logout failed.

**Do not** try opening the callback by manually crafting `?code=fake&state=fake` and expecting login to succeed. An authorization code is a one-time credential issued by the OP to the client, bound to the flow, redirect URI, and correlation state.

### 9.3. curl Is Only for Observing the Initial Phase

```bash
curl -i http://localhost:8080/
curl -i http://localhost:8080/oidc/me
curl -i http://localhost:8080/login
curl -i http://localhost:8080/oauth2/authorization/google
```

Expected: public 200, protected redirect, login page 200 HTML, authorization-start redirect to Google (when configured validly). `curl` does not persist cookies across commands by default or perform user login/consent at the provider. **Do not treat an HTTP 302 as proof of successful OIDC authentication.** Use a browser/cookie jar and a real test IdP to verify the full flow.

## 10. OAuth2AuthorizedClient: WebFlux Calling a Resource Server with an Access Token

After logging in, the RP application sometimes needs to call other APIs. `OAuth2AuthorizedClient` holds the registration, principal name, and OAuth access token (and optionally a refresh token) for the OAuth2 Client to use. Spring Security provides `ReactiveOAuth2AuthorizedClientManager` and `ServerOAuth2AuthorizedClientExchangeFilterFunction` for outbound `WebClient`.

**WebClient integration fragment** (not a required file for the demo project since a real resource server is needed):

```java
@Bean
WebClient protectedApiClient(
        ReactiveOAuth2AuthorizedClientManager manager) {

    ServerOAuth2AuthorizedClientExchangeFilterFunction filter =
        new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

    return WebClient.builder()
        .filter(filter)
        .build();
}
```

To select the **right authorized client** for a request, a controller parameter can be used:

```java
@GetMapping("/oidc/external-profile")
Mono<String> external(
        @RegisteredOAuth2AuthorizedClient("google")
        OAuth2AuthorizedClient authorizedClient) {

    return protectedApiClient.get()
        .uri("https://openidconnect.googleapis.com/v1/userinfo")
        .attributes(
            ServerOAuth2AuthorizedClientExchangeFilterFunction
                .oauth2AuthorizedClient(authorizedClient))
        .retrieve()
        .bodyToMono(String.class);
}
```

This is a **standalone fragment**, requiring a `WebClient` bean, imports/approved API URLs, consent/scopes, and error handling. Not every provider/scope permits calling the URL in the example. Some providers return UserInfo automatically during login; the app does not always need to call it again manually. If an `openid profile email` token lacks the scope for another business API, that resource server may reject it.

**Warning:** Avoid `filter.setDefaultOAuth2AuthorizedClient(true)` on a shared `WebClient` used to call arbitrary hosts: that default can send the user's token on every outbound request through that client. Specify the authorized client and trusted endpoints explicitly; use separate `WebClient` instances per integration, validate host/scheme, and never forward an access token to a service without the granted audience/scope.

### 10.1. Token Storage and Session Management Rules

- `ServerSecurityContextRepository`/WebSession: holds Authentication for the website; the browser holds the session cookie per policy, not the raw refresh token in a cookie unless explicitly designed and reviewed.
- `ServerOAuth2AuthorizedClientRepository`/`ReactiveOAuth2AuthorizedClientService`: manages authorized clients by principal/registration, keeping access/refresh tokens on the backend per policy. An in-memory repository is suitable only for demos/small scopes; multi-node systems need secure storage, lifecycle management, and proper encryption.
- `ReactiveOAuth2AuthorizedClientManager`: when configured with supporting providers, can refresh expired access tokens; **do not assume** every OP issues refresh tokens or that refresh always succeeds.
- Local logout: clears SecurityContext/session per config, and evaluate whether authorized clients/refresh tokens need to be removed/revoked at the provider; this is not automatic.
- Never log `access_token`, `refresh_token`, `id_token`, `code`, raw `state`/`nonce`, or client secret. Restrict read access to token stores, backups, and tracing baggage.

## 11. Logout: RP Session vs. OP SSO Session

When the browser POSTs `/logout` with CSRF, Spring Security can perform **local logout** to clear the RP's authentication. However, the **OP session** and access/refresh tokens have different lifecycles:

- WebFlux local logout does not automatically sign the OP out across all devices.
- An already-issued JWT access token may still be accepted by a Resource Server until `exp` if validated offline without revocation checks.
- A refresh token may remain valid until expiration/rotation/revocation per OP policy.
- **OIDC RP-Initiated Logout**, if the OP supports discovery `end_session_endpoint`, allows the RP to direct the browser to the OP to end the OP session.
- **OIDC Back-Channel Logout**, if configured by both parties, enables the OP to send a Logout Token so the RP can clear the corresponding session, though it is not bearer-token revocation.

**Variant fragment** to add RP-Initiated Logout to the `SecurityWebFilterChain` bean (do not run in parallel as a second chain bean with the same matcher):

```java
OidcClientInitiatedServerLogoutSuccessHandler oidcLogout =
    new OidcClientInitiatedServerLogoutSuccessHandler(
        reactiveClientRegistrationRepository);

oidcLogout.setPostLogoutRedirectUri("{baseUrl}/signed-out");

return http
    .authorizeExchange(ex -> ex
        .pathMatchers("/", "/signed-out").permitAll()
        .anyExchange().authenticated())
    .oauth2Login(Customizer.withDefaults())
    .logout(logout -> logout.logoutSuccessHandler(oidcLogout))
    .build();
```

You need to import `OidcClientInitiatedServerLogoutSuccessHandler` from package `org.springframework.security.oauth2.client.oidc.web.server.logout` and `ReactiveClientRegistrationRepository`. **Only enable this when the provider actually supports** `end_session_endpoint` and allows `post_logout_redirect_uri`. For Google, for example, do not assume a standard OIDC logout endpoint is always available for the same registration; check discovery/provider documentation first.

**CSRF protection for logout:** For browsers using session cookies, real logout via POST requires a valid CSRF token per Spring Security config. Do not change it to a GET with side effects just to make writing links easier.

## 12. Essential Security Considerations for a Relying Party

### 12.1. Redirect URI and Forwarded Headers

The `redirect_uri` in the authorization request must match the URI the RP registered at the OP. When running behind a reverse proxy, the URL constructed by the framework from scheme/host/port/path can be wrong if trusted forwarded headers are not configured. Never allow external Internet clients to inject `Forwarded`/`X-Forwarded-Host` headers that the app trusts unconditionally; that creates open redirect risks and callbacks to rogue hosts.

### 12.2. Authorization After Login

OIDC proves the user was authenticated by the OP; it **does not by itself determine business permissions in the app**. `OidcUser` has `sub`, `email`, claims, and authorities granted by the configured mapper. When ADMIN roles or tenant document permissions are needed, map them from trusted sources, verify the issuer, claim mapping, and domain policy; never trust an `X-Role` header or an unverified email domain.

In the code example, `/oidc/admin` requires `ROLE_ADMIN` to emphasize: getting a 200 on `/oidc/me` **does not** mean access to admin routes is granted.

### 12.3. Do Not Use ID Token as an Access Token

`id_token` is meant for the **client/RP** to verify authentication. Resource Server APIs normally require an **access token** with the proper audience, scopes, and validation. Sending an ID Token to an API as a bearer token just because it is a signed JWT is a misuse. Nor should an ID Token's email be used as the sole permission check to access any tenant's data.

### 12.4. XSS and CSRF Are Different

The RP session cookie is automatically sent by the browser per cookie rules, so state-changing POSTs still need CSRF protection even when logged in via OAuth2/OIDC. XSS can perform valid actions within the session or leak JavaScript-accessible data/tokens; CSP, output encoding, Secure/HttpOnly/SameSite cookies, and script restrictions are complementary defenses, not replacements for `state`/`nonce`/CSRF.

### 12.5. Multiple Providers, Account Linking, and Multi-Tenant

A user with the same email at two providers **is not automatically the same identity**. Use the **`issuer + subject`** tuple as the correlation key and an account-linking workflow with explicit confirmation. Avoid letting an attacker link accounts via an unverified email; multi-tenant role mapping must enforce an issuer/tenant allowlist and claim integrity.

### 12.6. Authorization Codes and Tokens Must Not Be Logged or Placed in URLs Unintentionally

`code` is a short-lived one-time grant and may appear in the callback query string, so access logs/analytics/proxies must redact it. Never send access/refresh/ID tokens in query strings, referrers, HTTP errors, or browser localStorage if policy forbids it. Configure session cookies properly, rotate session IDs on authentication, enforce timeouts/logout, and use central session storage across multiple app instances.

### 12.7. PKCE, nonce, state, and Issuer Validation

Never disable `state`, `nonce`, JWS ID Token validation, or issuer/audience/time checks just to “debug and make login work”. PKCE strengthens protection against code interception when used in the right flow, but does not replace `state`/redirect URI checks. Changing provider/client types affects PKCE/client authentication requirements: cross-check metadata and actual configuration.

### 12.8. Client Credentials Are Different from User Credentials

`client-id` identifies the application (not a secret). `client-secret` or private-key client authentication proves the **client** to the AS via the registered method, not the user's password. User password/login happens at the OP, while WebFlux holds its own client configuration. Never place the client secret in HTML or JavaScript of a public SPA.

## 13. Common Implementation Pitfalls

| Symptom | Possible Cause | How to Analyze/Fix |
| --- | --- | --- |
| Clicking login does not reach the provider | Wrong `registrationId`, missing `ReactiveClientRegistrationRepository`, wrong initiate URL | Check `/oauth2/authorization/google`, registration, and chain matchers |
| Provider reports `redirect_uri_mismatch` | Base URL/URI differs from registered value | Compare scheme, host, port, path **exactly**; check trusted proxy settings |
| Callback has code but login fails | Lost state/session, expired/used code, wrong client credentials, token endpoint/ID Token validation error | Preserve cookies, check correlation and safe metadata logs |
| Browser loops on login continuously | WebSession cookie not persisted, unsuitable SameSite/Secure/domain/path | Check Set-Cookie/request Cookie in DevTools, proxy, and session store |
| Login succeeds but Bearer API endpoint returns 401 | Website's `OAuth2AuthenticationToken` is not an inbound Bearer access token | Separate RP and Resource Server roles; outbound client uses authorized client |
| User logs in via OIDC and admin still returns 403 | Missing `ROLE_ADMIN` authority/mapper | This may be expected; check policy and trusted role source |
| `OidcUser` is null after another OAuth2 provider | Provider does not support OIDC, missing `openid` scope | Use `OAuth2User` for OAuth-only providers or an OIDC provider with proper scope |
| `@AuthenticationPrincipal` gets unexpected name | Different UserInfo/ID Token `sub`/username mappings | Use stable issuer+sub; verify claim mapping |
| Token refresh does not work | OP does not issue refresh tokens, token store lacks refresh token, misconfigured authorized client manager | Check scopes/grants/policy; do not log refresh tokens |
| Login succeeds but POST request returns 403 | Missing/invalid CSRF token, not necessarily missing role | Check WebFlux CSRF token/session and request method |
| RP logout succeeds but logging in again does not ask for password | OP SSO session is still active | Evaluate RP-Initiated/Back-Channel Logout; do not conclude local logout is broken |
| `WebClient` sends token to unintended host | Using default authorized client on a shared `WebClient` | Specify `oauth2AuthorizedClient` per request and host allowlist |
| Callbacks through gateway have wrong HTTP/hostname | Incorrect forwarded headers/ingress config | Trust only the proxy, configure base URL and public TLS |
| Multiple providers sharing email mix up users | Using email instead of issuer+sub key | Check account linking, issuer/subject, and email_verified per policy |

### 13.1. Do Not Use Servlet APIs When the Lesson Is WebFlux

| Servlet MVC | WebFlux reactive |
| --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `ClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| `OAuth2AuthorizedClientRepository` | `ServerOAuth2AuthorizedClientRepository` |
| `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| `OidcClientInitiatedLogoutSuccessHandler` | `OidcClientInitiatedServerLogoutSuccessHandler` |
| `SecurityContextHolder` thread-based | `ReactiveSecurityContextHolder` Reactor Context |

Similar names do not mean code can be copied 1:1. Set the `spring-boot-starter-webflux` dependency and import packages for the right stack, avoiding mixing Servlet login filters into a reactive app.

## 14. Pre-Production OIDC RP Architecture Checklist

1. Identify the app as an OAuth2 Client/OIDC RP; explicitly document the providers/AS and Resource Servers the client needs to call.
2. Trust only approved provider issuers; use `ClientRegistration` and standard OIDC Discovery/JWKS/HTTPS.
3. Register exact redirect URIs; verify proxy and forwarded headers with clear trust boundaries.
4. Use Authorization Code flow; enable/verify state, nonce, and PKCE per client type/provider policy.
5. Protect client secrets/private keys on the backend; never place them in frontend code/repositories/logs.
6. Verify ID Token signature, issuer, audience, expiry, and nonce per OIDC; never Base64-decode and trust claims blindly.
7. Distinguish `id_token` (RP login), `access_token` (Resource Server), `refresh_token` (refresh at AS), and `SESSION` (RP local auth).
8. Store WebSession/SecurityContext and authorized clients in a design safe for multi-instance deployments, with timeout/rotation/revocation policies.
9. Never send tokens to browsers or APIs with the wrong audience; use `ServerOAuth2AuthorizedClientExchangeFilterFunction` with explicit authorized client selection.
10. Enforce authorization/role/tenant/ownership checks in services; successful OIDC login does not equal admin.
11. Keep CSRF enabled on cookie-authenticated browser mutations; add CSP, cookie hardening, session fixation protection, and XSS defenses.
12. Distinguish local logout from OP logout and token revocation, choosing RP-initiated/back-channel/token revoke based on requirements.
13. Test in-memory with `mockOidcLogin` **and** run real integration tests with a sandbox OP: state, PKCE, code exchange, ID Token claims, session, logout.
14. Monitor redirect errors, state mismatches, token exchange failures, and timeouts using correlation IDs, **without logging credentials**.
15. When upgrading Spring Security/Boot, cross-check endpoint defaults, callbacks, user services, cookies, and authorized-client persistence, then run regression tests.

## 15. Self-Assessment Questions

**1.** When Spring WebFlux uses `oauth2Login()` for “Login with Google”, is it the Authorization Server?  
**No.** It is the **OAuth2 Client and OIDC RP**; Google/OP performs user authentication and issues tokens.

**2.** Why must `scope=openid` be declared?  
This scope puts the flow into **OpenID Connect**, enabling ID Tokens and `OidcUser` per OIDC; if a provider does not support OIDC, you cannot fabricate OIDC behavior simply by renaming the scope.

**3.** Where is the authorization code processed?  
The browser brings the code back to the `/login/oauth2/code/{registrationId}` callback; Spring Security on the **backend** checks `state` and exchanges the code at the token endpoint. Application controllers do not need to call that endpoint manually.

**4.** Are `id_token` and `access_token` different?  
**Yes.** The ID Token is for the RP to verify login; the access token is for the Resource Server protecting an API. Never use an ID Token in place of an access token.

**5.** A user completes OIDC login successfully and `GET /oidc/admin` returns 403. Is this an OAuth2 Login bug?  
**Not necessarily.** Authentication succeeded, but the `ADMIN` role has not been granted/mapped; this is business authorization.

**6.** Is `OAuth2AuthenticationToken` the same as `JwtAuthenticationToken`?  
**No.** One represents a web app's OAuth2/OIDC login; the other is typically used when a Resource Server validates an inbound JWT Bearer token.

**7.** When WebFlux calls an upstream API on behalf of the user, where should the token be attached?  
In the **outbound WebClient `Authorization: Bearer`** header via a selected authorized client with the proper resource/audience/scope; never expose the token in the browser profile response.

**8.** Does local logout automatically close SSO at the OP and revoke all access tokens?  
**No.** You must also configure OIDC RP-Initiated/Back-Channel Logout and/or a revocation policy when required.

**9.** Why does a post-login website still need a CSRF token on POST?  
The browser authenticates to the website via an automatically sent session cookie. OIDC login does not eliminate CSRF risks for browser mutations.

**10.** Does `mockOidcLogin()` prove that the ID Token from the OP is genuinely verified?  
**Not yet.** It creates a mock principal in the test harness to verify controllers/security rules. Integration with a real OP or protocol-compliant mock OP is required to test code exchange and validation.

### Official Documentation

- Spring Security 6.5, *OAuth2 WebFlux Overview*: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
- Spring Security 6.5, *OAuth2 Login Core Configuration*: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/core.html
- Spring Security 6.5, *OAuth2 Login Advanced Configuration*: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/advanced.html
- Spring Security, *Reactive OAuth2 Client / Authorized Client Features*: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorized-clients.html
- Spring Security, *Testing OAuth 2.0 in WebFlux*: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Security, *OIDC Logout for Reactive*: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- OAuth 2.0 Authorization Code Grant, RFC 6749: https://www.rfc-editor.org/rfc/rfc6749
- Proof Key for Code Exchange, RFC 7636: https://www.rfc-editor.org/rfc/rfc7636
- OAuth 2.0 Security Best Current Practice, RFC 9700: https://www.rfc-editor.org/rfc/rfc9700

**Summary:** WebFlux with `oauth2Login()` is an **OAuth2 Client and OIDC RP**: it redirects the browser to the OP, receives the callback code, exchanges it for tokens and verifies identity, then holds `Authentication` for the website session. It **does not issue tokens itself or verify OP passwords**. Separate ID Token, access token, refresh token, and session; use `oauth2Client` when calling Resource Servers, `oauth2ResourceServer` when an API receives Bearer tokens directly; and always enforce roles, CSRF, session/logout handling, and provider trust boundaries.