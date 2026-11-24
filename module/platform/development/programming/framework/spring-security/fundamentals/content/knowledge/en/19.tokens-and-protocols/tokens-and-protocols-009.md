# Distinguishing OAuth2 Login, OAuth2 Client, and Resource Server in Spring Security

Spring Security provides several features named OAuth2, so when starting an application it is easy to mix up three questions: **how do users log in through an Identity Provider (IdP)?**, **how does the application obtain an access token to call another API?**, and **how does my API verify access tokens sent by clients?** These three needs correspond to **OAuth2 Login**, **OAuth2 Client**, and **OAuth2 Resource Server**.

The most important point is that **OAuth2 Login is a feature built on top of OAuth2 Client**; these two concepts are related, not synonymous. **Resource Server** sits on the side that *receives and verifies* Bearer access tokens. None of the three automatically turns your application into an **Authorization Server** issuing tokens.

This article focuses on **Spring Security Servlet / Spring MVC**, using modern `SecurityFilterChain` configuration on Java 17+ and Spring Boot 3 / Spring Security 6. OAuth 2.0 concepts still apply in other environments, yet the API names for WebFlux are Reactive counterparts and should not be mixed up.

## 1. Choosing the Right Feature with Three Questions

| Scenario | Spring Security Component | Application Role | Key Artifacts |
|---|---|---|---|
| User clicks "Sign in with Google/IdP" on a website | **OAuth2 Login** — `http.oauth2Login(...)` | **Client**, and also the web app managing the login session | Authorization code, user info; possibly an OIDC ID token |
| App has logged the user in and needs to call a partner API using an issued token | **OAuth2 Client** — `http.oauth2Client(...)`, `OAuth2AuthorizedClientManager` | **Client** sending outbound requests | Access token, refresh token if issued |
| A backend job needs to obtain a token via `client_credentials` to call an API | **OAuth2 Client** | **Client** acting under the application's identity | Client registration, access token for the application |
| API `/api/orders` needs to accept `Authorization: Bearer ...` | **OAuth2 Resource Server** — `http.oauth2ResourceServer(...)` | **Resource Server** receiving inbound requests | JWT access token or opaque access token |
| System needs to **issue** access tokens, refresh tokens, and manage OAuth grants | **Authorization Server**, implemented via a dedicated product/component | **Authorization Server** | Authorization endpoint, token endpoint, keys, grants |

**Mental map:** **Login = log users into the application**, **Client = obtain/manage tokens so the application can call other services**, **Resource Server = protect an API receiving Bearer tokens**. One system can simultaneously play multiple roles across different endpoints; this classification is by **request flow direction and security responsibility**, not three project types that must be separated.

### Relationships Between the Features

```text
                   Spring Security OAuth2 (Servlet)
                              |
          +-------------------+------------------+
          |                                      |
     OAuth2 Client                        OAuth2 Resource Server
          |                                      |
          +-- OAuth2 Login                      +-- JWT validation
          |   (browser login)                   |
          +-- Authorization Code                +-- Opaque token introspection
          +-- Client Credentials
          +-- Refresh Token
          +-- Authorized Client / Token Manager
```

The diagram groups by application processing responsibility. **OAuth2 Login uses OAuth2 Client infrastructure**, while Resource Server has its own mechanism to receive and validate Bearer tokens. Authorization Server is a separate role and is not created by enabling these three DSLs.

## 2. One System, Three Perspectives

Consider an architecture with web app `portal.example.test`, API `api.example.test`, and identity provider `idp.example.test`:

```text
    [Browser - User]
              |
              | (1) Opens portal, clicks Sign In
              v
    [Portal / Spring MVC]
       OAuth2 Login + OAuth2 Client
              |           ^
              | Redirect  | Authorization code / tokens
              v           |
       [Identity Provider / Authorization Server]
              ^
              | (3) When a new token is needed, portal exchanges with IdP
              |
    [Portal / Spring MVC]
              |
              | (2) Calls API with Authorization: Bearer ACCESS_TOKEN
              v
       [Orders API / Spring MVC]
          OAuth2 Resource Server
              |
              | Validates token, checks scope/audience,
              | checks permissions on orders
              v
         [Business Data]
```

In step (1), **the portal is a client performing user login**. In step (2), the portal **is a client calling an API**, while Orders API **is a resource server**. When tokens are issued or refreshed, the **IdP/authorization server** is responsible. Software named "server" is not automatically an OAuth2 Resource Server; determine whether it **accepts Bearer access tokens to protect resources**.

## 3. OAuth2 Login: User Sign-In via IdP

### When to Use It?

Use OAuth2 Login if your application has a web UI and wants users to sign in with accounts managed by an external provider, such as "Sign in with Google" or "Login with Company".

Spring Security supports OAuth2 Login via the **Authorization Code Grant**. If the provider supports **OpenID Connect (OIDC)** and the client requests the `openid` scope, the OIDC flow includes an **ID token** for verifying user identity. OAuth 2.0 by itself is an authorization framework, so for standardized federated login, OIDC is usually the right choice; some providers supply user info over OAuth 2.0 without OIDC.

### Sequence of the Login Flow

1. Browser visits a login-protected page on the portal.
2. Spring Security redirects the user to `/oauth2/authorization/{registrationId}`; for example `/oauth2/authorization/company`. Depending on configuration, the client sends the browser to the IdP's authorization endpoint carrying `state` and required parameters; PKCE may be used depending on client type and configuration.
3. User authenticates at the IdP and grants consent if prompted by the IdP.
4. IdP redirects the browser back to the application's callback URI, by default `{baseUrl}/login/oauth2/code/{registrationId}`, carrying the authorization code and matching `state`.
5. The application **exchanges the authorization code with the IdP's token endpoint** over a server-to-server connection; the client receives tokens, verifies them, and processes identity details per provider mechanism.
6. Spring Security builds an `Authentication` representing the logged-in user and stores it in `SecurityContext`; in typical session-based Servlet apps, login state is managed via HTTP session.
7. Browser continues navigating the portal using the corresponding session cookie. The browser **does not have to send an access token itself** for every internal portal page.

Illustrative URLs:

```http
GET /oauth2/authorization/company HTTP/1.1
Host: portal.example.test
```

```http
GET /login/oauth2/code/company?code=EXAMPLE_CODE&state=EXAMPLE_STATE HTTP/1.1
Host: portal.example.test
```

`EXAMPLE_CODE` and `EXAMPLE_STATE` are descriptive placeholders only. An authorization code is short-lived, single-use, and must be bound and verified properly. Never put real codes, tokens, or session cookies in logs or screenshots.

### What Does Spring Security Store After Login?

When OAuth2 Login succeeds, the user is typically represented by an `OAuth2AuthenticationToken` in `SecurityContext`; the principal can be an `OAuth2User`, or an `OidcUser` with OIDC. Typical applications use a session cookie to maintain login across browser requests. This mechanism can coexist with an `OAuth2AuthorizedClient` holding the access token issued for calling APIs.

**Do not confuse these three artifacts:**

- `SecurityContext`: authentication state within the current application, serving logged-in user checks and authorization within the portal.
- `OAuth2AuthorizedClient`: association between a client registration, user/principal, and issued tokens; serves outbound OAuth2 requests from the app to other resources.
- OIDC `IdToken`: OIDC identity attestation intended for the logging-in client; **never use an ID token instead of an access token** to call a resource server.

**OAuth2 Login does not automatically turn the portal into a Bearer API Resource Server.** If the portal also exposes REST APIs accepting `Authorization: Bearer`, configure Resource Server appropriately for those endpoints.

### Minimal Configuration for Web Login

In a Spring Boot Servlet application with the OAuth2 Client starter and valid client registration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebLoginSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
```

This is **Spring Boot/Spring Security configuration code**; it cannot run standalone with just `javac` because it requires framework dependencies, a provider, client registration, and a Servlet runtime. When multiple filter chains exist, assign appropriate `securityMatcher` and ordering.

In `application.yml`, an OIDC provider client registration typically looks like:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid, profile
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          company-idp:
            issuer-uri: https://idp.example.test/issuer
```

This configuration **illustrates structure**; `idp.example.test` is not a real IdP. Configure the exact issuer per your real IdP, register the exact redirect URI at the IdP, and supply `OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET` safely via environment variables or a secret manager. For public clients/PKCE, client authentication methods and secret storage must be designed accordingly; never embed confidential client secrets in frontend JavaScript.

### Login and Logout

In a session-based web application, once authenticated, users can navigate portal pages via their session. **Local logout** clears authentication/session state in the portal, yet **does not by default log out the SSO session at the IdP**, revoke all access tokens, or log out other applications. OIDC offers dedicated federated logout mechanisms when supported by the IdP; configure them explicitly if single logout is required.

## 4. OAuth2 Client: Obtaining and Using Tokens to Call External APIs

### When to Use It?

OAuth2 Client is used when your application **actively calls an API protected by OAuth2**. This occurs when:

- A user has logged in and the application calls an API on the user's behalf (**delegated access**).
- A backend task or microservice calls an API under the service's own identity (**client credentials**), with no interactive user.
- The application must manage access tokens, refresh tokens, and re-authorization matching the grant used.

In Spring Security Servlet, key infrastructure includes:

| Component | Role |
|---|---|
| `ClientRegistration` | Configuration describing an OAuth2 client: registrationId, provider, grant type, client ID, scopes, endpoints |
| `ClientRegistrationRepository` | Looks up configured client registrations |
| `OAuth2AuthorizedClient` | Binds a client registration, associated principal, and access token (plus refresh token if present) |
| `OAuth2AuthorizedClientService` | Saves/retrieves authorized clients by client registration and principal; suited for state outside web requests |
| `OAuth2AuthorizedClientRepository` | Saves/retrieves authorized clients tied to web request/response and principal |
| `OAuth2AuthorizedClientManager` | Manages authorizing/re-authorizing with the provider per grant, including refresh when supported and configured |
| `oauth2Client(...)` DSL | Enables/configures OAuth2 Client support in `HttpSecurity`, especially authorization code and related components |

**The name `OAuth2AuthorizedClient` does not mean "a user logged into the website".** It means **a client has obtained authorization and a token** to access resources. A backend job using `client_credentials` still has an authorized client even though no user has a browser open.

### Two Important Usage Patterns

**A. Using User-Delegated Permissions**

A portal application can use `oauth2Login()` for browser login and `oauth2Client()` / authorized client infrastructure to call an external API. Tokens must be retrieved from `OAuth2AuthorizedClient` or managed client mechanisms, never using an ID token as an access token. The authorization code flow may issue a refresh token depending on provider, scopes, and policy.

**B. Service-to-Service API Calls with `client_credentials`**

For example, a `reporting-service` job needs to read an inventory API with no browser involved:

```text
reporting-service             IdP / Authorization Server
      |  POST token endpoint (client_credentials)
      |------------------------------------>|
      |<-------------- access token -------|
      |
      | Authorization: Bearer access_token
      |------------------------------------> inventory-api
      |                         inventory-api validates token
      |<---------------- authorized data ---|
```

In client credentials, the token usually represents the **application's** permissions; never assume it represents an end user. The server may authenticate clients via secret, private-key JWT, mTLS, or another suitable method. On the backend, **client secrets must be stored securely**, never placed in source code or browsers.

Configuration registering a machine-to-machine client, separate from the web login example above:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory:
            provider: service-idp
            authorization-grant-type: client_credentials
            client-id: ${INVENTORY_CLIENT_ID}
            client-secret: ${INVENTORY_CLIENT_SECRET}
            scope: inventory.read
        provider:
          service-idp:
            token-uri: https://idp.example.test/oauth2/token
```

Assuming `inventory` is properly registered at the authorization server and secrets are loaded from the environment, the application can configure an `OAuth2AuthorizedClientManager` for backend tasks:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;

@Configuration
public class ServiceOAuth2ClientConfig {

    @Bean
    OAuth2AuthorizedClientManager serviceAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService service) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build();

        var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, service);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

In a service needing to use the token, acquiring the authorized client can look like this (code belonging to the app configured above, not framework-independent):

```java
OAuth2AuthorizeRequest request =
        OAuth2AuthorizeRequest.withClientRegistrationId("inventory")
                .principal("reporting-service")
                .build();

OAuth2AuthorizedClient authorizedClient =
        authorizedClientManager.authorize(request);

if (authorizedClient == null) {
    throw new IllegalStateException("Failed to obtain authorized client");
}

String accessToken = authorizedClient.getAccessToken().getTokenValue();
// Use accessToken in Authorization: Bearer when calling the matching inventory API.
// Do not write real tokens to logs or print to the console.
```

Additional imports for `OAuth2AuthorizeRequest` and `OAuth2AuthorizedClient` plus an injected `authorizedClientManager` are required. The snippet illustrates **how to use Spring Security's API in a service**, not a standalone Java class. The name `reporting-service` binds the authorized client to a service-identifying principal inside the manager; it does not mean a user is logged in.

Note that `AuthorizedClientServiceOAuth2AuthorizedClientManager` suits services independent of `HttpServletRequest`. In user-facing web flows, use `DefaultOAuth2AuthorizedClientManager` or request-aware `RestClient`/`WebClient` integrations. Choose the manager based on context and grant; **never arbitrarily borrow a user's access token** for a background job.

### Does OAuth2 Client Automatically Refresh Tokens?

Spring Security provides refresh token infrastructure and corresponding `OAuth2AuthorizedClientProvider` implementations, yet behavior **depends on provider/grant, how the manager is built, and how `authorize` is called**. Never just enable `oauth2Client()` and assume every client automatically receives refresh tokens, rotates them, or re-authenticates in every context. The authorization server decides whether to issue refresh tokens and what usage policy applies.

## 5. Resource Server: Verifying Bearer Tokens at the API

### When to Use It?

Use **OAuth2 Resource Server** when your application exposes an API and each request must be protected by an OAuth2 access token. Callers may be browser-based apps, backends, mobile apps, or other services; the API does not care whether the client signed in via Google or which grant was used, provided the token was validly issued by the authorization server for this API and meets rules.

Request arriving at the API:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
```

`Bearer` indicates how the token is presented. **Presence of the header is not enough**: Spring Security must validate the token via JWT or introspection, then enforce access permissions.

### Two Ways to Validate Access Tokens

**JWT access token**: the resource server uses `JwtDecoder` to verify the signature and relevant claims. When `issuer-uri` is configured, Spring Security can discover issuer metadata/keys and validate `iss`, `exp`, and `nbf` per corresponding defaults. **Audience (`aud`) must be explicitly configured/verified for your API** if not automatically enforced for your specific requirements. Scopes are typically mapped to `SCOPE_<scope>` authorities.

**Opaque access token**: the resource server typically uses `OpaqueTokenIntrospector` to ask the authorization server/introspection endpoint whether the token is active and what permissions it carries. Even JWT-formatted tokens can be verified via introspection when dynamic state checks are desired; "opaque" here refers to the **verification method** via introspection rather than solely the token string's appearance.

Both require TLS, scope checks, and appropriate revocation policies. **A Resource Server does not issue access tokens, issue refresh tokens, or set up login redirect pages itself.**

### JWT API Configuration Sample

Add the appropriate dependencies in Spring Boot:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Configure the authorization server's issuer (illustrative URL; requires a real IdP):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
```

Configuration code in Spring Boot Servlet:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiResourceServerConfig {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
```

This is a configuration example inside a **Spring Boot application with proper dependencies**; the app must point to a real issuer/JWKS and have matching API controllers. Scope `orders.read` is just an illustrative permission name; actual permissions are issued by the authorization server and enforced by the API. Do not treat `hasAuthority("SCOPE_orders.read")` as sufficient for all per-order checks; resource ownership and business rules must still be verified.

### 401, 403, and Login Redirects

A typical resource server returns **401 Unauthorized** for missing/invalid tokens, potentially with `WWW-Authenticate: Bearer`. For a valid token lacking permissions, it typically returns **403 Forbidden**. It **does not** redirect browsers to a provider's login page: that belongs to OAuth2 Login.

When configuring Resource Server alongside OAuth2 Login in one application, if you want the API to always respond with 401/403 instead of HTML login/302, create a **separate filter chain** for `/api/**` and configure an appropriate entry point. Avoid accidentally letting the API inherit browser session/redirect policies.

## 6. Are the Three DSLs the Same Just Because All Are Named OAuth2?

```java
http.oauth2Login(Customizer.withDefaults());          // Browser login via IdP
http.oauth2Client(Customizer.withDefaults());         // App acts as OAuth2 Client
http.oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));       // API receives & validates Bearer JWT
```

**Do not copy all three into every `SecurityFilterChain`.** These lines configure three distinct needs; they do not belong together in the same chain by default. Instead determine:

| Architectural Question | Leads To |
|---|---|
| Does the app let interactive users log in via an IdP? | OAuth2 Login |
| Does the app call another API using OAuth2 tokens? | OAuth2 Client |
| Does the app validate inbound access tokens on its own endpoints? | OAuth2 Resource Server |
| Does the app itself issue access tokens to other clients? | Standalone Authorization Server |
| Does the app both log users in and call APIs on their behalf? | OAuth2 Login **and** OAuth2 Client |
| Does the app have both a browser UI and Bearer REST APIs? | Combination of Login/Client and Resource Server, with separate filter chains |

Using `oauth2Login()` for a web UI already brings in the OAuth2 Client infrastructure needed for login. Enabling `oauth2Client()` additionally is useful when the app needs custom outbound/client behavior. **You do not necessarily need both just to have a login button.**

Similarly, adding the OAuth2 Client dependency provides client infrastructure, not inbound JWT acceptance. API protection requires Resource Server configuration and corresponding validators.

## 7. A Hybrid Application: Browser Login and Bearer API

This is the easiest scenario to confuse. Suppose one Spring Boot service has:

- Pages `/dashboard`, `/account` for browser users logged in via OIDC.
- Endpoints `/api/orders/**` for other applications sending Bearer access tokens.
- After login, the portal may use OAuth2 Client to call downstream APIs.

We can split into two `SecurityFilterChain` beans, prioritizing the API chain before the browser chain:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MixedSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error", "/assets/**").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
```

This Java code is **one implementation option inside a Spring Boot 3 / Spring Security 6 project** having both OAuth2 Client and Resource Server starters, client registrations, issuer, controllers, and required resources. It cannot run via `javac` outside Spring Boot. In a real application, **keep only one configuration matching your architecture**; never leave earlier sample `SecurityFilterChain` beans active alongside this one without checking order and matchers.

Why split them this way?

1. `apiChain` applies only to `/api/**`. It accepts Bearer tokens, verifies JWTs, and does not use HTTP sessions to store `SecurityContext`. CSRF is disabled **only in this chain assuming a purely Bearer-only API**, because browser cookies are not used as authentication credentials here.
2. `browserChain` handles all remaining requests. It uses OAuth2 Login and can use OAuth2 Client to call other APIs. For session/cookie-based web login, keep CSRF protection enabled for state-changing operations; the example does not disable CSRF globally.
3. `@Order(1)` and `@Order(2)` determine which chain is evaluated first, while `securityMatcher` determines which requests belong to the chain. Spring Security typically uses only the **first matching filter chain** for a request.
4. `/oauth2/authorization/{registrationId}` and `/login/oauth2/code/{registrationId}` are handled by the browser chain; avoid matching login callbacks under `securityMatcher("/api/**")`.

**Important condition:** The configuration above is suitable only if `/api/**` truly uses Bearer headers and never relies on cookies/sessions for authentication. If the API is called using browser session cookies, CSRF can still be a threat and requires a different protection strategy. Disabling CSRF is based on request and credential transport models, not merely because a path contains `api`.

### Looking at a Request Tells You Which Chain Runs

| Request | Chain | Expected Result |
|---|---|---|
| Browser visits `GET /dashboard` unauthenticated | Browser | Redirects to OAuth2 Login flow as needed |
| Browser callback `GET /login/oauth2/code/company` | Browser | Processes code/state and completes login if valid |
| Mobile sends `GET /api/orders` with valid Bearer JWT having `orders.read` | API | Validates token, checks authority, proceeds to controller |
| Mobile sends `GET /api/orders` with no token | API | Typically returns 401, does not redirect to HTML login page |
| Valid token lacking `orders.read` | API | Typically returns 403 |
| Browser calls `POST /account/change-email` using session | Browser | Must satisfy CSRF protection and matching authorization |

## 8. Tokens, Sessions, and Authentication: Do Not Put Them All in One Basket

Every example mentions "token", yet there are different objects:

| Object | Where Typically Seen? | Purpose |
|---|---|---|
| **Authorization code** | Redirect callback after IdP consent, short-lived | Client exchanges at token endpoint to obtain tokens |
| **OIDC ID token** | OAuth2/OIDC Login client | Proves user identity information to the client |
| **Access token** | Sent by OAuth2 Client to Resource Server | Grants API access within valid scope/audience |
| **Refresh token** | Sent by Client to Authorization Server | Requests a new access token per policy |
| **Session cookie / `JSESSIONID`** | Exchanged between browser and web app | Identifies login session/state on the web app |

A browser that logs in successfully via OIDC can hold a portal **session cookie**, while IdP-issued access tokens are managed server-side by the portal. The browser does not have to see the access token in `localStorage`. That is a viable BFF/server-rendered design.

**An access token is not an ID token.** Even when both tokens are JWTs, a resource server must validate an **access token** intended for its API—checking issuer, audience, expiration, scope, and applicable constraints. An ID token intended for an OAuth2 Client must never be treated as an API access token.

**`SecurityContext` is not `OAuth2AuthorizedClient`.** After login, `Authentication` indicates who is authenticated inside the portal; `OAuth2AuthorizedClient` manages tokens/grants issued for the client to call other services. The two are related yet serve two different decisions.

**JWT does not automatically create a login session.** A Resource Server can verify JWTs on every request and run statelessly. OAuth2 Login typically creates a browser session; those are two separate state models that may share a codebase while keeping clear boundaries.

## 9. Differences in Endpoints and Common Errors

| Component | Common Endpoints / Channels | On Error |
|---|---|---|
| OAuth2 Login | `/oauth2/authorization/company`, callback `/login/oauth2/code/company` | Login failure, redirect issues, `state`/`redirect_uri`/ID token/provider errors |
| OAuth2 Client | IdP token endpoint; outbound calls from app to external APIs | `invalid_client`, `invalid_grant`, timeouts, insufficient scope, refresh failures |
| Resource Server | Inbound `/api/**` requests with `Authorization: Bearer` | 401 on missing/invalid token; 403 on insufficient permissions |
| Authorization Server | Authorization endpoint, token endpoint, JWKS, introspection/revocation per server | Grant denial, token issuance, token revocation |

`spring.security.oauth2.client.registration.company` is for client login/outbound API calls, whereas `spring.security.oauth2.resourceserver.jwt.issuer-uri` is for the API validating inbound tokens. Both configurations may point to the same IdP, yet **they do not replace each other**.

Never assume Resource Server automatically exposes `/oauth2/token`: Spring Security Resource Server only **validates incoming tokens** and does not turn your app into a token issuer.

## 10. Configuration Mistakes and How to Diagnose Them

### Mistake 1 — Enabling `oauth2ResourceServer().jwt()` and Expecting a Google Login Button

Resource Server does not generate authorization redirects or login sessions. Browser sign-in requires **OAuth2 Login** and corresponding client registration.

### Mistake 2 — Enabling `oauth2Login()` and Assuming All `/api/**` Accept Bearer Tokens

OAuth2 Login handles browser login and `SecurityContext`; validating Bearer tokens from other clients requires **Resource Server**. If an app has both, split chains and verify redirect vs. 401 behavior as designed.

### Mistake 3 — Thinking `oauth2Client()` Issues Tokens Itself

OAuth2 Client **requests tokens from an Authorization Server** via valid grants; Spring Security Client does not sign/issue tokens for other parties. To issue tokens, an appropriate Authorization Server is needed.

### Mistake 4 — Using `client_credentials` to Represent a Logged-In User

`client_credentials` typically represents the **client application**, carrying no direct end-user delegated authorization. If an API requires user-identity access, use a user authorization flow, matching scope/resource policies, and an appropriate token.

### Mistake 5 — API Accepts ID Tokens as Access Tokens

An OIDC ID token is issued for the client to verify login, not as a pass to access every API. The Resource Server must validate access tokens intended for it—never merely read `sub` and grant access.

### Mistake 6 — Treating a Valid JWT Signature as Enough

The Resource Server must still verify `iss`, `aud`, `exp`, `nbf`, scopes/permissions, algorithms/keys, and business rules. In particular, **an audience validator may require explicit configuration**. A valid token for API A is not automatically permitted at API B.

### Mistake 7 — Disabling Sessions and CSRF Across the Whole App "Because of OAuth2"

If browsers use sessions/cookies to log in, disabling CSRF globally opens vulnerabilities. Bearer-only APIs and web logins need separate policies; `SessionCreationPolicy.STATELESS` on an API chain must not bleed into the browser chain.

### Mistake 8 — Logging Access/Refresh Tokens or Putting Them in URLs

Tokens are credentials. Use HTTPS, secure secret/token stores, narrow scopes, and short lifetimes; never write tokens into logs, analytics, shell history, URLs, exception messages, or telemetry systems.

### Mistake 9 — Confusing 401 and 403 Errors

401 means the request lacks valid required authentication; 403 typically means authenticated yet lacking permissions. If an API redirects to an HTML login page, check the **filter chain / entry point** rather than assuming an access token error.

### Mistake 10 — Overlooking Proxies, Issuers, and Redirect URIs

Login can fail because `redirect_uri` mismatches the registered URI, wrong `{baseUrl}` behind a reverse proxy, or wrong hostname/scheme. Resource Server can reject tokens due to mismatched `iss`, unreachable JWKS, or invalid `aud`. Handle forwarded headers strictly from trusted proxies; never blindly trust arbitrary headers from the Internet.

## 11. Standalone Java 17 Example to Practice Role Recognition

Before writing Spring configuration, a quick exercise is classifying scenarios by direction of action. The following Java example is **only a learning model** to remember the three roles; it does not execute OAuth2 or issue/verify real tokens.

Create file `OAuth2RoleChooserDemo.java`:

```java
public class OAuth2RoleChooserDemo {
    enum UseCase {
        LOGIN_BROWSER,
        CALL_EXTERNAL_API,
        VALIDATE_INCOMING_BEARER
    }

    static String springFeature(UseCase useCase) {
        return switch (useCase) {
            case LOGIN_BROWSER -> "OAuth2 Login (uses OAuth2 Client)";
            case CALL_EXTERNAL_API -> "OAuth2 Client";
            case VALIDATE_INCOMING_BEARER -> "OAuth2 Resource Server";
        };
    }

    public static void main(String[] args) {
        System.out.println("Browser login: " +
                springFeature(UseCase.LOGIN_BROWSER));
        System.out.println("Outbound API: " +
                springFeature(UseCase.CALL_EXTERNAL_API));
        System.out.println("Inbound Bearer: " +
                springFeature(UseCase.VALIDATE_INCOMING_BEARER));
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac OAuth2RoleChooserDemo.java
java OAuth2RoleChooserDemo
```

Exact output:

```text
Browser login: OAuth2 Login (uses OAuth2 Client)
Outbound API: OAuth2 Client
Inbound Bearer: OAuth2 Resource Server
```

The standalone example uses Java 17 `switch` expressions. The `SecurityFilterChain` and `OAuth2AuthorizedClientManager` examples earlier are **code dependent on Spring Boot/Spring Security**, requiring a project with dependencies and a real IdP; do not expect them to compile with bare `javac`.

## 12. Practical Checklist for a Specific Application

1. **Draw the request diagram:** who calls whom, which requests are browser redirects, which carry inbound Bearer tokens, and which are outbound client calls.
2. **Identify the role** of each service: OAuth2 Client, Resource Server, Authorization Server, or multiple roles.
3. **Choose dependencies:** in Spring Boot, use `spring-boot-starter-oauth2-client` for Login/Client, and `spring-boot-starter-oauth2-resource-server` for Bearer APIs.
4. **Register clients** with the IdP: right client ID, client authentication, grant type, redirect URI, and scopes; never embed secrets in frontends.
5. **Configure the login chain** if browser login is needed: authorization code/OIDC, state/PKCE, sessions, and appropriate CSRF.
6. **Configure outbound client** if calling APIs: authorized-client manager, secure token storage/refresh, and resource-matching scopes/audiences.
7. **Configure the API chain** if accepting inbound Bearer tokens: issuer, JWT or introspection, audience, authority mapping, and business authorization.
8. **Test error branches:** anonymous browser redirect, API missing token 401, token missing scope 403, wrong issuer/audience, expired refresh, logout, and revocation.
9. **Check for secret leaks:** never log authorization codes, client secrets, access tokens, refresh tokens, or session cookies; verify HTTPS and proxy configs.

### Four Self-Check Questions

**Question 1:** A website has a "Login with IdP" button and after login needs to call an external API on the user's behalf. Which components are needed?

**Answer:** OAuth2 Login for browser authentication, and OAuth2 Client / authorized-client infrastructure to manage access tokens when calling the external API. If the external API is managed by another application, that API application is the Resource Server.

**Question 2:** A headless application with no UI only receives `Authorization: Bearer` from a mobile app. Does it need `oauth2Login()`?

**Answer:** No. What it needs is Resource Server, choosing JWT validation or introspection. Browser login is needed only if the product actually has an interactive login flow.

**Question 3:** A backend job needs to acquire a token via `client_credentials` to call an API. Does enabling Resource Server on the job help obtain that token?

**Answer:** No. The job acts as an **OAuth2 Client**, using a client registration and appropriate authorized-client manager/provider to request an access token from the Authorization Server.

**Question 4:** If a service has `oauth2Login()`, `oauth2Client()`, and `oauth2ResourceServer()`, can it issue refresh tokens to other clients yet?

**Answer:** No. Those features do not replace an Authorization Server and token endpoint. A service can issue OAuth tokens only if it runs a separately designed, configured, and operated Authorization Server component.

**Remember:** **OAuth2 Login handles users signing in via an IdP; OAuth2 Client requests and uses tokens to call APIs; OAuth2 Resource Server is an API validating incoming tokens.** The right setup is determined by request direction, state management, and the security responsibility of each component.

## Official References

- [Spring Security — OAuth2 overview, Servlet](https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html): distinguishes Resource Server, Client, Authorization Server, and Login's place within Client.
- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/): login flows based on authorization code.
- [Spring Security — OAuth2 Login Core Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): client registration, redirect URI, and `oauth2Login` setup.
- [Spring Security — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): `oauth2Client`, `OAuth2AuthorizedClientManager`, and grants.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): validating JWT Bearer tokens.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): validating tokens via introspection.
