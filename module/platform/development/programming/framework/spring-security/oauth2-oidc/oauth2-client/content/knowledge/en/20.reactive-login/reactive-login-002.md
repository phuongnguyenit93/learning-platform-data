# 20.2. OAuth2 and OIDC Login Flow in WebFlux

## 1. Why Does OAuth2/OIDC Login in WebFlux Need Dedicated Understanding?

Spring Security supports OAuth 2.0 Login and OpenID Connect (OIDC) Login on both **Servlet** and **Reactive WebFlux**. Both models follow the OAuth 2.0/OIDC protocol, but they differ in how Spring handles HTTP requests, session security, asynchronous execution, and HTTP client integration.

In Servlet applications, learners commonly encounter <code>HttpSecurity</code>, <code>SecurityFilterChain</code>, <code>HttpSession</code>, and <code>RestClient</code>. With **WebFlux**, the corresponding components are typically:

- <code>ServerHttpSecurity</code> and <code>SecurityWebFilterChain</code>.
- <code>ServerWebExchange</code> and <code>WebSession</code>.
- <code>ReactiveSecurityContextHolder</code>, Reactor <code>Context</code>, <code>Mono</code>/<code>Flux</code>.
- <code>ReactiveClientRegistrationRepository</code> and reactive authorized-client components.
- <code>WebClient</code> together with <code>ServerOAuth2AuthorizedClientExchangeFilterFunction</code>.

This difference matters when:

1. The user is redirected to the OpenID Provider (OP) to log in.
2. The OP returns an authorization code to the application's callback.
3. Spring Security verifies <code>state</code>, exchanges the code for tokens, and validates the ID Token.
4. The authentication result is placed into the reactive security context.
5. The application continues calling REST APIs with an access token in an environment where the event-loop must not be blocked.

> **Guiding principle of this lesson:** The OAuth2/OIDC protocol does not change just because the application uses WebFlux. What changes is how Spring Security implements the flow via **WebFilters, WebSession, and the Reactor Context**, as well as how the application consumes tokens asynchronously.

## 2. Running Example Scenario

Suppose we are building a reporting management application:

- A browser frontend accesses the WebFlux application at <code>https://portal.example.org</code>.
- The Spring Boot application acts as an **OAuth2/OIDC Client** with registration ID <code>company</code>.
- The OpenID Provider has issuer <code>https://idp.example.org/realms/company</code>.
- Users log in using the **Authorization Code Flow**.
- After login, WebFlux can display <code>OidcUser</code> information and call the Reports API using the issued access token.

The domains, Client IDs, paths, and users in this lesson are **illustrative examples**, not the configuration of a real production system.

A conceptual authorization request:

~~~http
GET /authorize?response_type=code&client_id=portal-web&scope=openid%20profile&redirect_uri=https%3A%2F%2Fportal.example.org%2Flogin%2Foauth2%2Fcode%2Fcompany&state=RANDOM_STATE&nonce=RANDOM_NONCE HTTP/1.1
Host: idp.example.org
~~~

In a real request, Spring Security builds the parameters from <code>ClientRegistration</code> and the authorization request resolver, performing proper encoding. Never assemble URLs by string concatenation in production code.

## 3. Distinguishing OAuth 2.0 Login and OpenID Connect Login

OAuth 2.0 and OIDC are closely related, but they are not synonymous.

| Property | OAuth 2.0 Login | OIDC Login |
|---|---|---|
| Foundation | OAuth 2.0 Authorization Code Flow | OAuth 2.0 Authorization Code Flow extended with OIDC |
| Primary goal | Allows Client authorization and, in Spring Security OAuth2 Login, uses user info from the provider | Authenticates the End-User and conveys identity per the OIDC standard |
| Typical scope | Provider-specific such as <code>read:user</code> | Must request <code>openid</code> to be an OIDC authentication request |
| Token response | Access token, sometimes refresh token | Access token, **ID Token**, optionally refresh token |
| Standard identifier | Varies by API/provider | Pair <code>(iss, sub)</code> in the ID Token |
| User data | Provider-specific UserInfo API | OIDC claims; UserInfo Endpoint if used |
| Typical Spring Security principal | <code>OAuth2User</code> | <code>OidcUser</code> |

**For Spring Security:** the same <code>oauth2Login()</code> configuration can serve both OAuth 2.0 Login and OIDC Login. When `ClientRegistration` uses the <code>openid</code> scope and the provider supports OIDC, Spring Security processes the token response/ID Token according to OIDC.

Do not treat an access token as identity proof equivalent to an ID Token. An access token is meant for accessing a Resource Server and has its own audience, scopes, and lifetime; an ID Token proves End-User authentication to the Client under OIDC.

### 3.1. Roles of the Parties

| Party | Role |
|---|---|
| **Browser/User Agent** | Follows redirects to the OP and returns to the callback |
| **WebFlux application** | OAuth2/OIDC Relying Party / Client; maintains appropriate sessions and tokens |
| **OpenID Provider/Authorization Server** | Authenticates the user, issues authorization codes and tokens |
| **Resource Server** | API protected by access tokens; verifies issuer, audience, scopes, and policies |

One application can simultaneously act as an OIDC Client and a Resource Server, but those flows must be configured separately per endpoint.

## 4. Overall Flow: From Login URL to OIDC Principal

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant W as Spring Security WebFlux Client
    participant OP as OpenID Provider
    participant API as Downstream Resource Server
    U->>B: Open a page requiring login
    B->>W: GET /reports
    W-->>B: 302 to login page or authorization initiation
    B->>W: GET /oauth2/authorization/company
    W->>W: Create OAuth2AuthorizationRequest, state, nonce, PKCE when applicable
    W->>W: Store authorization request in WebSession/repository
    W-->>B: 302 to OP Authorization Endpoint
    B->>OP: Authorization request
    OP->>U: Login, MFA, consent per policy
    OP-->>B: 302 callback with code and state
    B->>W: GET /login/oauth2/code/company?code=...&state=...
    W->>W: Load original request and verify state
    W->>OP: POST Token Endpoint, exchange code for tokens
    OP-->>W: Access Token + ID Token (+ Refresh Token if present)
    W->>W: Verify ID Token, load OidcUser/UserInfo when appropriate
    W->>W: Store authorized client and SecurityContext
    W-->>B: Redirect to post-login page
    B->>W: GET /reports
    W->>API: WebClient + appropriate Bearer access token
    API-->>W: Permitted result
    W-->>B: Page/data payload
~~~

Each phase has a distinct purpose:

1. **Authorization request initiation:** identifies the provider/Client, scopes, redirect URI, and generates correlation data.
2. **Authentication at the OP:** the user submits credentials to the OP; the Client application does not directly handle the OP password.
3. **Callback:** matches the authorization response against the request that was sent out.
4. **Token exchange:** sends the code and appropriate client authentication/PKCE verifier to the Token Endpoint.
5. **OIDC validation:** verifies the ID Token, nonce/issuer/audience, and related constraints.
6. **State persistence:** stores `Authentication` in the WebFlux security context/session and the authorized client in its repository/service.
7. **Using tokens for downstream APIs:** only with a Resource Server matching the proper audience/scopes/permissions.

## 5. Configuring a Minimal WebFlux OIDC Client

### 5.1. Dependencies

Example with Spring Boot 3, Spring Security 6, Java 17:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

If the project is meant to run only **Reactive WebFlux**, do not inadvertently leave <code>spring-boot-starter-web</code> in the same setup. When both Spring MVC and WebFlux are present, Spring Boot normally defaults to the Servlet/MVC application, making expectations that <code>SecurityWebFilterChain</code> acts as the main web configuration incorrect.

If the system genuinely requires both stacks, explicitly decide the application type and design security accordingly; do not use a Servlet configuration assuming it turns reactive automatically.

### 5.2. application.yml for OIDC Discovery

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-web
            client-secret: ${COMPANY_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

Explanation:

| Property | Meaning |
|---|---|
| <code>registration.company</code> | Internal Registration ID, used in the login initiation URL |
| <code>provider: company</code> | Links the registration to provider metadata |
| <code>client-id</code> | Client ID registered at the OP |
| <code>client-secret</code> | Secret for a confidential Client; never commit a real secret |
| <code>authorization-grant-type</code> | <code>authorization_code</code> for browser login |
| <code>redirect-uri</code> | Callback the OP is allowed to redirect back to; must be registered exactly |
| <code>scope: openid</code> | Marks the request as an OIDC authentication request |
| <code>issuer-uri</code> | Trusted issuer, used for OP metadata discovery and validation |

With a valid issuer exposing OIDC Discovery metadata, Spring Security/Boot can infer the authorization endpoint, token endpoint, JWK Set URI, and UserInfo endpoint (if published). For providers that do not support discovery, endpoints and user-info settings must be configured explicitly.

In production:

- Configure OP issuers/endpoints only from trusted sources.
- Store secrets in a secret manager or environment variables.
- Use HTTPS for production callbacks and register exact redirect URIs.
- Verify that the issuer, endpoints, Client ID, scopes, and authentication method align with OP policy.
- Never reuse the same secret across environments just for demo convenience.

### 5.3. SecurityWebFilterChain

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/error", "/assets/**").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

**Differences from Servlet:**

~~~text
Servlet:
    HttpSecurity
    SecurityFilterChain
    authorizeHttpRequests(...)

Reactive WebFlux:
    ServerHttpSecurity
    SecurityWebFilterChain
    authorizeExchange(...)
~~~

<code>oauth2Login()</code> activates the login flow. <code>oauth2Client()</code> adds OAuth2 Client support for using authorized clients when calling APIs; for an application that only needs login, the second part may not be necessary depending on the use case.

Ensure the application has the appropriate reactive registration/repository beans. When Spring Boot auto-configuration is properly triggered by the starters and properties, most of these beans are created automatically.

## 6. Phase 1 — Initiating the Authorization Request

When the user clicks the link:

~~~text
GET /oauth2/authorization/company
~~~

WebFlux OAuth2 Login recognizes <code>company</code> as the registration ID, looks up the <code>ClientRegistration</code>, and builds an <code>OAuth2AuthorizationRequest</code>.

The request contains typical parameters:

~~~text
response_type = code
client_id     = portal-web
redirect_uri  = https://portal.example.org/login/oauth2/code/company
scope         = openid profile email
state         = random value used to correlate callback
nonce         = value binding ID Token to authorization request if sent
code_challenge / code_challenge_method = PKCE when applicable
~~~

<code>state</code>, <code>nonce</code>, and PKCE serve **different** purposes:

| Field | Role |
|---|---|
| <code>state</code> | Links the callback to the original authorization request, preventing CSRF/login injection in the OAuth2 flow |
| <code>nonce</code> | Binds the ID Token to the OIDC authentication request, mitigating replay/token substitution |
| <code>code_verifier</code> | Temporary Client secret used to prove ownership when exchanging the authorization code via PKCE |
| <code>code_challenge</code> | Derived from the verifier and sent to the Authorization Endpoint |
| <code>redirect_uri</code> | Registered callback address to which the OP returns the code |

Never place <code>code_verifier</code> in the front-channel authorization URL; the front channel carries <code>code_challenge</code>, while the verifier is used at the Token Endpoint.

### 6.1. Where Is state Stored in WebFlux?

Spring Security Reactive uses the abstraction <code>ServerAuthorizationRequestRepository&lt;OAuth2AuthorizationRequest&gt;</code> to hold the authorization request pending the callback. A common implementation is <code>WebSessionOAuth2ServerAuthorizationRequestRepository</code>, which stores data in **WebSession**.

~~~text
Browser requests /oauth2/authorization/company
  → Generate random state
  → Store OAuth2AuthorizationRequest in WebSession
  → Redirect browser to OP

Browser returns to callback:
  → Look up matching WebSession
  → Read prior request
  → Verify received state
~~~

If the browser loses its session cookie or multiple nodes do not share sessions as configured, the callback may fail because the authorization request is missing or `state` does not match.

Do not mix <code>WebSessionOAuth2ServerAuthorizationRequestRepository</code> with Servlet's <code>HttpSessionOAuth2AuthorizationRequestRepository</code>; they belong to two different stacks.

### 6.2. Redirect URL to the Authorization Endpoint

Spring Security returns HTTP 302 so the browser navigates to the OP. The OP is where the user enters a password or completes MFA per policy. The WebFlux Client **does not submit the user's credentials** to the OP via a server-to-server request.

For applications behind a reverse proxy, the redirect URI must be computed with the published scheme/host/port. If the backend sees <code>http://localhost:8080</code> while the public endpoint is HTTPS, misconfigured proxies and forwarded headers can cause a redirect URI mismatch.

Trust forwarded headers only from a **controlled proxy**. Never blindly accept <code>X-Forwarded-Host</code> sent by external clients to construct trusted redirect URLs.

## 7. Phase 2 — Browser Login at the OpenID Provider

During this stage, the OP may:

1. Display a login page.
2. Reuse an existing SSO session.
3. Require MFA/step-up authentication.
4. Show a consent screen if needed.
5. Enforce tenant and `ClientRegistration` policies.

Once finished, the OP redirects the browser back to the Client:

~~~http
HTTP/1.1 302 Found
Location: https://portal.example.org/login/oauth2/code/company?code=AUTH_CODE_PLACEHOLDER&state=STATE_PLACEHOLDER
~~~

This is an **authorization code** callback, not yet a token response. The authorization code is typically short-lived, single-use, and must be exchanged at the Token Endpoint.

If the user denies consent, the OP may redirect back to the callback with <code>error</code> and <code>state</code> parameters, such as <code>access_denied</code>. The Client must handle the error per the flow rather than trying to exchange tokens without a code.

### 7.1. State Is Not an Access Token

<code>state</code> is a value that correlates the request and response. It does not authenticate the End-User's identity and does not replace ID Token verification. If a callback arrives with a mismatched state, Spring Security must reject it as an invalid authorization response.

### 7.2. Logging In from Multiple Tabs

Two browser tabs initiating login simultaneously can generate two different authorization requests. Depending on the repository and `WebSession` behavior, the second request may overwrite the first or create a situation where a callback's state no longer matches.

If the product must support parallel login flows, design the repository/correlation mechanism accordingly; never "fix" the issue by disabling state validation.

## 8. Phase 3 — WebFlux Callback Handling and Token Exchange

The default callback is typically:

~~~text
GET /login/oauth2/code/{registrationId}
~~~

For example:

~~~text
GET /login/oauth2/code/company?code=...&state=...
~~~

Spring Security Reactive has dedicated web filters for the OAuth2 Login flow. Common API names are <code>OAuth2AuthorizationRequestRedirectWebFilter</code> for authorization initiation and <code>OAuth2LoginAuthenticationWebFilter</code> for callback/authentication.

Processing overview:

~~~mermaid
flowchart TD
    A["Callback: code + state"] --> B["Look up original authorization request"]
    B --> C{"Valid state and registration?"}
    C -->|No| X["Authentication failure / no session issued"]
    C -->|Yes| D["Token Endpoint: code exchange + client authentication/PKCE"]
    D --> E{"Valid token response?"}
    E -->|No| X
    E -->|Yes, OIDC| F["Verify ID Token, nonce/issuer/audience/expiry"]
    E -->|Yes, non-OIDC OAuth2 Login| G["Fetch OAuth2User per provider config"]
    F --> H["OidcUser / Authentication"]
    G --> H
    H --> I["Store OAuth2AuthorizedClient and SecurityContext"]
    I --> J["Redirect to post-login page"]
~~~

The token exchange occurs **back-channel** from the Client to the OP Token Endpoint:

~~~http
POST /oauth2/token HTTP/1.1
Host: idp.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <CLIENT_AUTH_PLACEHOLDER>

grant_type=authorization_code&code=AUTH_CODE_PLACEHOLDER&redirect_uri=https%3A%2F%2Fportal.example.org%2Flogin%2Foauth2%2Fcode%2Fcompany&code_verifier=PKCE_VERIFIER_PLACEHOLDER
~~~

This example illustrates the structure. In practice, Client Authentication may be <code>client_secret_basic</code>, <code>client_secret_post</code>, private key JWT, or another method per the registration; the PKCE verifier is included only if the flow used PKCE.

Never log the authorization code, code verifier, client secret, or raw token response.

## 9. Phase 4 — ID Token and OIDC Validation

With the <code>openid</code> scope, the OIDC Authorization Code Flow token response must include an ID Token per the protocol:

~~~json
{
  "access_token": "ACCESS_TOKEN_PLACEHOLDER",
  "token_type": "Bearer",
  "expires_in": 3600,
  "id_token": "HEADER.PAYLOAD.SIGNATURE",
  "refresh_token": "REFRESH_TOKEN_PLACEHOLDER"
}
~~~

The refresh token in the JSON above is **optional**; not every provider returns one. Example signed ID Token payload:

~~~json
{
  "iss": "https://idp.example.org/realms/company",
  "sub": "user-2482",
  "aud": "portal-web",
  "iat": 1794810000,
  "exp": 1794813600,
  "nonce": "NONCE_PLACEHOLDER",
  "name": "Alex Example",
  "email": "alex@example.org"
}
~~~

The timestamps, identity data, tokens, and domain names are all illustrative. You may trust these claims **only after the ID Token has been verified using trusted OP configuration**.

### 9.1. Key Validations

Spring Security OIDC Client performs configured validations, including:

| Condition | Why is it needed? |
|---|---|
| Signature/algorithm/trusted keys | Prevents trusting forged or tampered payloads |
| <code>iss</code> | Token must come from the configured issuer |
| <code>aud</code> | Token must be issued for the appropriate Client |
| <code>azp</code> when applicable | Identifies the authorized party per OIDC rules |
| <code>exp</code> / timestamps | Prevents accepting expired ID Tokens |
| <code>nonce</code> when sent in request | Binds the ID Token to the current authorization request |
| Other OIDC constraints | Ensures a valid token response and authentication flow |

The application should never extract the middle segment of a JWT, Base64URL-decode it, and treat those claims as verified. Reading the <code>OidcUser</code> created by Spring Security after authentication is the proper path.

### 9.2. Is UserInfo Mandatory?

No. The OIDC Client can rely on the ID Token to confirm identity, and the **UserInfo Endpoint** is called when the provider, scopes, and configuration allow or require it. UserInfo typically supplies profile claims such as name, email, picture, or locale.

Crucially, the <code>sub</code> claim in the UserInfo response must **match** the ID Token's subject per OIDC. Never merge UserInfo profile data belonging to a different subject into the current principal.

### 9.3. OIDC Identity Is Not API Access Authorization

<code>sub</code>, <code>iss</code>, and <code>email</code> establish identity/profile; they **do not automatically grant administrative roles**. Permissions at a Resource Server also depend on scopes/entitlements, ownership, tenant, and business policies.

A valid ID Token does not give an access token an audience for every API.

## 10. Phase 5 — Reactive Authentication and SecurityContext

After a successful login, Spring Security creates an <code>Authentication</code> representing the user. With OAuth2/OIDC Login, the common type is <code>OAuth2AuthenticationToken</code>; the principal is usually:

- <code>OAuth2User</code> for non-OIDC OAuth2 Login.
- <code>OidcUser</code> for OIDC Login.

### 10.1. Security Context in the Reactor Context

In Servlet apps, developers are used to thread-local-based <code>SecurityContextHolder</code>. In a reactive pipeline, execution can hop across threads; therefore Spring Security uses <code>ReactiveSecurityContextHolder</code> and the **Reactor Context** to propagate the security context.

~~~text
Servlet:
    thread → SecurityContextHolder

Reactive:
    Mono/Flux subscription → Reactor Context → SecurityContext
~~~

Example service reading the principal name:

~~~java
package example.security;

import reactor.core.publisher.Mono;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class CurrentUserService {

    public Mono<String> currentPrincipalName() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .filter(authentication ->
                authentication != null && authentication.isAuthenticated())
            .map(Authentication::getName)
            .switchIfEmpty(
                Mono.error(new IllegalStateException(
                    "No authenticated principal")));
    }
}
~~~

Never call <code>.block()</code> to obtain a synchronous result inside a WebFlux request handler. Blocking the event-loop degrades throughput or causes deadlocks/bottlenecks.

### 10.2. WebSession and Persisting the Security Context

For typical browser logins, the security context must persist across multiple HTTP requests. In WebFlux, the session mechanism is <code>WebSession</code> with the <code>ServerSecurityContextRepository</code> abstraction (commonly <code>WebSessionServerSecurityContextRepository</code>).

~~~text
Request A: OIDC callback succeeds
    → Authentication is stored
    → Browser receives/keeps session cookie

Request B: GET /me
    → WebSession is retrieved
    → SecurityContext/Authentication is restored
~~~

**Authentication/SecurityContext differs from OAuth2AuthorizedClient storage:**

- SecurityContext holds the authenticated user and their authorities.
- Authorized client holds access/refresh tokens tied to a registration/principal.
- The authorization request repository holds <code>state</code>/PKCE **before the callback**.

These three pieces of data have different lifecycles. Do not treat the session cookie as an access token; do not store access/refresh tokens in custom cookies.

### 10.3. A Stateless Configuration Can Break Login

If you configure <code>NoOpServerSecurityContextRepository</code> or clear `WebSession` inappropriately, OAuth2 Login may fail to preserve the login session after the callback.

Stateless Bearer APIs and browser OIDC Login have different requirements. When an application contains both, design security chains by route and ensure login/callback paths belong to a chain that properly supports `WebSession`.

## 11. Accessing OidcUser in a WebFlux Controller

After OIDC Login, a controller can receive the principal:

~~~java
package example.web;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class MeController {

    @GetMapping("/me")
    public Mono<Map<String, Object>> me(
            @AuthenticationPrincipal OidcUser user) {

        return Mono.just(Map.of(
            "subject", user.getSubject(),
            "issuer", user.getIdToken().getIssuer().toString(),
            "hasUserInfo", user.getUserInfo() != null
        ));
    }
}
~~~

In a real application, return only the profile fields the frontend is permitted to see. Never return the raw ID Token, access token, refresh token, or all claims unnecessarily.

The example above assumes the endpoint is exclusively for OIDC Login. If the system also supports non-OIDC OAuth2 Login, <code>@AuthenticationPrincipal OidcUser</code> may not fit every principal; differentiate authentication types or separate routes.

### 11.1. Reading ID Token and UserInfo from the Right Sources

~~~java
OidcIdToken idToken = user.getIdToken();
OidcUserInfo userInfo = user.getUserInfo(); // may be null

String subject = user.getSubject();
String issuer = idToken.getIssuer().toString();
~~~

Imports:

~~~java
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
~~~

If UserInfo was not called or is unavailable, <code>userInfo</code> may be null. Email, full name, or avatar are not guaranteed to be present. <code>(iss, sub)</code> is the authoritative OIDC identifier, whereas email can change.

### 11.2. Do Not Infer Permissions from Name or Email

Dangerous example:

~~~text
if user.getEmail().endsWith("@company.example"):
    grant ADMIN
~~~

An email address is not a business authorization system. Even when the OP provides `email_verified`, you still need explicit role/permission rules from an authorized source enforced on the backend.

## 12. Reactive ClientRegistration and Authorized Client

In WebFlux, Spring Security uses reactive abstractions:

| Purpose | Reactive component |
|---|---|
| Look up registration | <code>ReactiveClientRegistrationRepository</code> |
| Store authorized client by principal | <code>ReactiveOAuth2AuthorizedClientService</code> |
| Store authorized client by web exchange | <code>ServerOAuth2AuthorizedClientRepository</code> |
| Coordinate authorization/refresh | <code>ReactiveOAuth2AuthorizedClientManager</code> |
| Attach access token to WebClient | <code>ServerOAuth2AuthorizedClientExchangeFilterFunction</code> |

<code>OAuth2AuthorizedClient</code> remains the model linking `ClientRegistration` + principal + access token + optional refresh token. The difference lies in how **lookups, persistence, and asynchronous flows** are handled.

Model example:

~~~text
ClientRegistration(company)
    └── principalName = user-2482
        ├── accessToken = token for Reports API when audience/scope match
        └── refreshToken = optional
~~~

Do not mix Servlet/synchronous service-style <code>OAuth2AuthorizedClientService</code> with <code>ReactiveOAuth2AuthorizedClientService</code> without deliberate design. Never call blocking JDBC directly on the event-loop just to fetch a token.

### 12.1. Token and Login Session Can Expire Independently

A user may still be logged into `WebSession` even after the access token has expired. When calling an API, the Client may need to refresh the token or initiate a new authorization flow depending on the provider/policy. Conversely, a valid access token does not prove the current browser session still exists.

A refresh token is not mandatory in every OIDC token response; do not treat the absence of a refresh token as a default error.

### 12.2. Client Credentials Differ from OIDC Login

If a WebFlux application has a background worker calling an API with service credentials, it can use a <code>client_credentials</code> registration and an appropriate reactive manager. That token does **not** represent an End-User and does not create an <code>OidcUser</code>.

For an application with both browser logins and service jobs, separate registrations, scopes, audiences, and principal management for the two use cases so user tokens and service tokens are never mixed up.

## 13. WebClient Using an Authorized Client After OIDC Login

<code>WebClient</code> is Spring's reactive HTTP client. With WebFlux, it is the natural choice for calling APIs without blocking the event-loop.

### 13.1. Creating WebClient with the OAuth2 Client Filter

~~~java
package example.web;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class DownstreamWebClientConfig {

    @Bean("oauth2WebClient")
    WebClient oauth2WebClient(
        ReactiveClientRegistrationRepository registrations,
        ServerOAuth2AuthorizedClientRepository authorizedClients) {

        var oauth2 = new ServerOAuth2AuthorizedClientExchangeFilterFunction(
            registrations, authorizedClients);

        return WebClient.builder()
            .filter(oauth2)
            .build();
    }
}
~~~

This attaches an OAuth2 filter to `WebClient`, which does not mean **every `WebClient` request automatically carries a token**. In the next example, the request explicitly selects the authorized client to avoid accidentally sending a token to an unintended endpoint.

### 13.2. Using @RegisteredOAuth2AuthorizedClient in a Controller

~~~java
package example.web;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@RestController
public class ReportsController {

    private final WebClient webClient;

    public ReportsController(
            @Qualifier("oauth2WebClient") WebClient webClient) {
        this.webClient = webClient;
    }

    @GetMapping("/reports/remote")
    public Mono<String> reports(
            @RegisteredOAuth2AuthorizedClient("company")
            OAuth2AuthorizedClient authorizedClient) {

        return webClient.get()
            .uri("https://api.example.org/v1/reports")
            .attributes(
                ServerOAuth2AuthorizedClientExchangeFilterFunction
                    .oauth2AuthorizedClient(authorizedClient))
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

Key points:

1. The annotation resolves the authorized client by registration ID and current principal/request.
2. <code>oauth2AuthorizedClient(authorizedClient)</code> attaches the **exact authorized client** to the `WebClient` request.
3. The filter attaches the Bearer access token to the HTTP call as configured.
4. <code>bodyToMono(String.class)</code> returns a publisher; WebFlux manages subscription when producing the HTTP response.
5. Never call <code>.block()</code> or manual <code>.subscribe()</code> in the controller to retrieve the result.

This pattern is valid only when the Reports API genuinely accepts tokens issued for registration <code>company</code>. If the access token is intended solely for UserInfo or a different Resource Server, the Reports API should reject it due to audience/scope mismatch.

The example returns a raw `String` to focus on the flow. Production code needs DTOs as well as handling for timeouts, response sizes, HTTP errors, telemetry, business authorization, and avoiding logging sensitive data.

### 13.3. Why You Should Not Enable defaultOAuth2AuthorizedClient Indiscriminately

Some exchange filter configurations allow selecting the authorized client from the current authentication or setting a default registration. Sending a default token on **every request** to every host can inadvertently leak credentials to untrusted URLs if the `WebClient` is reused without strict control.

Safer approach:

- Create dedicated `WebClient` instances for trusted downstream services.
- Select the <code>authorizedClient</code> or registration explicitly at each call site.
- Never allow the browser to pass an arbitrary target URL or registration ID for the backend to attach a token and call.
- If there are multiple issuers/audiences, separate `WebClient`/registrations by resource policy.

### 13.4. Common HTTP Errors

| Resource Server Response | Typical Meaning | How to Handle |
|---|---|---|
| 200 | Request succeeded | Process returned payload per schema |
| 401 <code>invalid_token</code> | Token rejected | Check expiry, issuer, audience, refresh capability |
| 403 <code>insufficient_scope</code> | Token lacks required scope | Check granted permissions, consent, and policy; do not blindly refresh |
| Other 403 | Role/tenant/object authorization or gateway | Identify the source of the response |
| 429 | Rate limited | Bounded backoff |
| 5xx | Downstream/gateway error | Retry only if request is safe, circuit breaker |

Never automatically retry side-effecting POST/PUT calls without idempotency guarantees. When using the OAuth2 `WebClient` filter's failure handler, check its behavior for your exact Spring Security version; do not remove the authorized client on every 403 response.

## 14. Reactive Code Does Not Make Every Library Non-Blocking

A common mistake is using a WebFlux controller while calling a blocking SDK/JDBC client directly inside <code>map</code> or <code>flatMap</code>:

~~~java
// Should not block the event-loop:
return Mono.just(userId)
    .map(id -> blockingJdbcRepository.findById(id));
~~~

If the library blocks, it ties up event-loop threads and degrades concurrency for other requests. Prefer:

- Reactive database drivers/repositories such as R2DBC when appropriate.
- `WebClient` for reactive HTTP I/O.
- Reactive session/token stores or adapters with thread isolation.
- For unavoidable blocking libraries, isolating them on an appropriate scheduler and load-testing.

Example bridging a blocking library (only when replacement is not possible):

~~~java
return Mono.fromCallable(() -> blockingService.loadProfile(userId))
    .subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic());
~~~

This is an **isolation workaround for blocking work**, not a way to turn the library non-blocking or a substitute for bounding connection/thread pools. A slow profile lookup during the OIDC callback can also cause login timeouts; configure timeouts and error policies.

### 14.1. Do Not Read SecurityContext via ThreadLocal Arbitrarily

In reactive code:

~~~java
ReactiveSecurityContextHolder.getContext()
~~~

is appropriate instead of assuming <code>SecurityContextHolder.getContext()</code> on an event-loop thread contains the current user. The Reactor Context is bound to the reactive subscription, not a global thread-local across requests.

### 14.2. Do Not Call subscribe() Manually in a Handler

Incorrect control flow:

~~~java
webClient.get()
    .uri("https://api.example.org/data")
    .retrieve()
    .bodyToMono(String.class)
    .subscribe(value -> System.out.println(value));

return Mono.just("done");
~~~

The handler may return a response before the HTTP call finishes, breaking error propagation, transaction/cancellation handling, and security context propagation. Instead, **return the publisher** or compose with <code>flatMap</code>:

~~~java
return webClient.get()
    .uri("https://api.example.org/data")
    .retrieve()
    .bodyToMono(String.class)
    .map(value -> "Received " + value.length() + " characters");
~~~

Do not log payload contents if they contain PII. The example returns only the character count to illustrate composition.

## 15. SecurityWebFilterChain: Ordering and Callbacks

A WebFlux application can have multiple <code>SecurityWebFilterChain</code> beans, for example:

- An API chain serving Bearer JWTs.
- A web chain serving browser OIDC Login.

In the reactive stack, Spring Security selects the **first matching chain** in order; exchange matchers determine which chain handles a route.

If the API chain is configured too broadly and ends up matching:

~~~text
/oauth2/authorization/company
/login/oauth2/code/company
~~~

then the <code>oauth2Login()</code> filters may never receive the authorization initiation/callback, resulting in 401/404/login loops.

### 15.1. Example Separating API and Web

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class MultipleReactiveChainsConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain webChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/error").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

**This configuration replaces Section 5.3**; do not keep both classes in the same project and end up with three overlapping chains without planned ordering.

An API chain with Resource Server JWT needs the corresponding dependency and proper issuer/audience validation:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
~~~

The example disables CSRF only for the **stateless API chain using Bearer tokens**. Never disable CSRF for the entire web chain just because the API does not use sessions; browser session-based routes remain exposed to CSRF risks.

### 15.2. Chain-Selection Matchers Differ from Authorization Rules

<code>securityMatcher(...)</code> decides **which chain processes** the request.

<code>authorizeExchange(...).pathMatchers(...)</code> decides **access permissions** inside the selected chain.

A <code>permitAll()</code> rule will not route a callback through the login filter if the request already matched a different chain that does not configure <code>oauth2Login()</code>.

## 16. CSRF, Session Cookies, and Callback Security

OAuth2 Login uses state/correlation; browser sessions still require standard web protections.

### 16.1. state and CSRF Are Related but Not Interchangeable

- <code>state</code> in the OAuth2 Authorization Code Flow protects against CSRF/login injection at the **authorization callback**.
- Spring Security's CSRF token protects **state-changing requests** sent by browsers using cookie/session authentication.

You must never conclude that "having state means CSRF can be disabled across the whole application."

### 16.2. Cookies and SameSite

The callback is typically a top-level navigation from the OP back to the Client. If the cookie/session is blocked due to `Domain`, `Path`, `SameSite`, `Secure` flag, or browser policy, Spring Security cannot find the original authorization request.

Symptom:

~~~text
Authorization request created successfully → redirect to OP
OP callback returns to right URL → state not found / mismatch
~~~

Check session cookie settings, HTTPS, reverse proxies, multiple tabs, and the session store. Never resolve this by disabling state validation.

### 16.3. HTTPS and Redirect URIs

Use HTTPS in production and register exact redirect URIs on the OP. Never let arbitrary request parameters or untrusted headers dictate the redirect URI or callback host; that can lead to open redirects, authorization code leakage, and hijacked login flows.

### 16.4. Session Fixation and Logout

After login, the security context/session must be managed with appropriate session security measures. Logging out of the WebFlux application, logging out at the OP, deleting the authorized client, and revoking refresh tokens are **distinct actions**.

Never assume default <code>logout()</code> automatically revokes access/refresh tokens at the Authorization Server. For OIDC RP-Initiated Logout, configure and test the corresponding provider endpoint if SSO logout is required.

## 17. Multi-Instance WebFlux: Sessions and Authorized Client Storage

When deploying multiple replicas:

~~~text
Browser
  └── Load Balancer
       ├── Instance A: Spring WebFlux
       └── Instance B: Spring WebFlux
~~~

There are two independent concerns:

1. **Login callback correlation:** The login initiation request hits A, and the callback returns to B. Without shared `WebSession` or session affinity, B cannot find the authorization request containing `state`.
2. **Authorized client token storage:** After login, the user calls an API handled by B, while the token is only stored in-memory on A, causing lookup failures or stale refresh state.

Spring Session with Redis or another shared session store can help manage `WebSession` across nodes when configured. However, **sharing `WebSession` does not automatically mean every `ReactiveOAuth2AuthorizedClientService` uses that same store**, and a shared authorized-client service does not by itself solve callback session state.

### 17.1. Checklist for Consistency

| Concern | What to Check |
|---|---|
| Cookie/session | Cookie settings, session ID, shared session store or affinity |
| State/correlation | Authorization request repository uses the proper `WebSession` |
| Principal identity | Principal name does not collide across tenants/issuers |
| Authorized client | Storage fits sharing and refresh needs |
| Refresh token rotation | Prevent two instances from concurrently using the same refresh token |
| Logout/revocation | Session/token revocation policy across all nodes |
| Routing | Consistent proxy forwarding, HTTPS, and redirect URI |

### 17.2. Refresh Race Across Multiple Instances

If A and B both read an older refresh token <code>R0</code>:

~~~text
A: refresh R0 → receives A1/R1
B: refresh R0 → invalid_grant / reuse detection
~~~

With an OP enforcing refresh token rotation, concurrent requests can invalidate the newly issued refresh token. Shared storage alone does not prevent races.

The application may need **single-flight refresh keyed by `(registrationId, principal)`**, re-reading state after acquiring the lock, updating access/refresh tokens atomically, and using conditional deletes/versioning so one node does not overwrite newer tokens stored by another.

This is a concurrency problem inherent to the OAuth2 token lifecycle, not specific to Servlet or Reactive.

## 18. Customizing OIDC UserService in a Reactive Flow

Not every application needs only claims from the ID Token/UserInfo. Many systems map users to internal profiles or resolve roles from another service.

In WebFlux, use a **reactive user service** instead of making blocking REST/JDBC calls directly inside the authentication pipeline.

### 18.1. Profile Enrichment Architecture

~~~text
Verified OIDC ID Token
    ↓
Extract (issuer, subject)
    ↓
Reactive profile lookup (WebClient/R2DBC)
    ↓
Check account active, tenant, role
    ↓
Build principal/authorities per policy
    ↓
Authentication succeeds or is rejected
~~~

Never use email as the internal user link key simply because it is human-readable. With OIDC, the <code>(iss, sub)</code> pair is the issuer-scoped identity anchor.

### 18.2. Reactive User Service vs. Servlet User Service

In Servlet, learners commonly see <code>OidcUserService</code>. In the reactive stack, reactive service types exist, such as <code>OidcReactiveOAuth2UserService</code> and the <code>ReactiveOAuth2UserService&lt;OidcUserRequest, OidcUser&gt;</code> interface depending on the Spring Security API/version.

Safe customization pattern:

1. Delegate to the default OIDC user service to preserve proper claim/UserInfo handling.
2. Read subject/issuer from the verified principal.
3. Use `WebClient`/a reactive repository to load the profile.
4. Map roles according to an **allowlist** and application policy.
5. Compose with <code>Mono.flatMap</code> rather than <code>block()</code>.
6. If the user is locked or the profile service is unavailable, apply a fail-closed policy or a designed restricted mode; never grant privileged default roles automatically.

Specific integration points and custom DSL method names depend on the chosen Spring Security version. Do not copy Servlet's synchronous <code>OAuth2UserService</code> into WebFlux and run blocking calls on the event-loop.

### 18.3. Roles Are Not OIDC Authentication

OIDC proves the user was authenticated by the OP, whereas internal roles authorize business functionality. A user with a valid ID Token may still lack permission to access data, or their internal account may be disabled.

For sensitive permissions, never trust a role snapshot cached indefinitely in a session; enforce an appropriate permission refresh/revocation policy.

## 19. Testing: Mocking Principals and Verifying Flows

Spring Security Test for WebFlux integrates with <code>WebTestClient</code>. You can test security rules/controllers by mocking OIDC authentication without running the full flow through a live OP.

### 19.1. Test Dependencies

~~~groovy
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.security:spring-security-test'
~~~

### 19.2. Testing an Endpoint Requiring Login

Illustrative test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOidcLogin;

@SpringBootTest
@AutoConfigureWebTestClient
class MeControllerSecurityTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void authenticatedOidcUserCanReadMe() {
        webTestClient
            .mutateWith(mockOidcLogin())
            .get()
            .uri("/me")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

This is a **test of post-authentication behavior**, not an end-to-end test covering browser redirects, token exchange, ID Token signatures, or live UserInfo. Mock authentication cannot replace verifying OP configuration in an integration test.

### 19.3. Important Test Scenarios

| Scenario | Expected Behavior |
|---|---|
| Unauthenticated browser calls protected route | Response requires authentication/redirect per configuration |
| Valid OIDC principal calls <code>/me</code> | 2xx |
| Authorized client without required scope calls Reports API | API denies with 403 per policy |
| Invalid callback state | No `Authentication`/session issued |
| Token Endpoint rejects code | Login fails; no authorized client stored |
| ID Token has wrong issuer/audience/expiry | OIDC validation rejects |
| Session cookie lost before callback | Correlation error; state check stays enabled |
| Stateless API route with invalid Bearer token | 401 per Resource Server configuration |
| `WebSession` across two replicas | Callback still locates request when session store/affinity works properly |

You do not need to build a fake Authorization Server in every unit test; integration tests can use a test OP or controlled stub endpoints when token exchange needs verification.

## 20. Common Pitfalls When Moving OAuth2 Login to WebFlux

| Symptom | Possible Cause | How to Investigate |
|---|---|---|
| <code>SecurityWebFilterChain</code> has no effect | Project runs MVC/Servlet due to web starter | Check application type, dependencies, security stack |
| <code>/oauth2/authorization/company</code> returns 404 | Missing registration, filter/chain does not match | Check reactive `ClientRegistrationRepository` and chains |
| Redirect URI has wrong host/scheme | Proxy/forwarded headers misconfigured | Check public URL, HTTPS, and trusted proxies |
| OP reports <code>redirect_uri_mismatch</code> | Callback not registered exactly | Compare redirect URI between Client and OP |
| Callback <code>invalid_state</code> | Lost `WebSession`, cookie, multi-tab login, or wrong repository | Check state repository/session |
| Callback repeatedly loops back to login | `SecurityContext` not saved, blocked cookie, wrong chain | Check `WebSession`, `ServerSecurityContextRepository` |
| ID Token rejected | Wrong issuer/audience/nonce, key, or clock | Check OP metadata and OIDC configuration |
| <code>OidcUser</code> null/wrong type | Registration lacks `openid` scope or using plain OAuth2 Login | Distinguish `OAuth2User` and `OidcUser` |
| UserInfo lacks email | Provider does not release claim/scope or UserInfo not called | Never treat email as a mandatory key |
| <code>ReactiveSecurityContextHolder</code> is empty | Pipeline created/subscribed outside request context or context dropped | Check Reactor Context propagation |
| WebFlux request slow/hung | Calling <code>block()</code> or blocking libraries on event-loop | Use `WebClient`/reactive store or isolate blocking work |
| Downstream API returns 401 | Access token has wrong audience/issuer, expired, or missing Bearer | Check authorized client and Resource Server |
| Downstream API returns 403 | Missing scope/role/tenant/ownership | Do not blindly refresh; check authorization |
| Callback hits API chain | Overly broad <code>securityMatcher</code> or wrong `@Order` | Narrow API matcher, keep callback in web chain |
| Login works on node A, fails on node B | `WebSession` or token storage is not shared | Evaluate session store, routing, authorized client service |
| Spring Security reports bean ambiguity | Multiple reactive managers/repositories of same type | Name/qualify and select the right bean |

### 20.1. Systematic Diagnostic Flow

~~~text
Is the application truly running Reactive WebFlux?
    |
    v
Does reactive ClientRegistration "company" exist?
    |
    v
Does GET /oauth2/authorization/company hit the login WebFilter?
    |
    v
Are the authorization request and state saved in WebSession?
    |
    v
Does the OP receive the right redirect URI, client ID, and scopes?
    |
    v
Does the callback return to the right chain with the session cookie?
    |
    v
Does state match and does token exchange succeed?
    |
    v
Are ID Token issuer/audience/signature/expiry/nonce valid?
    |
    v
Are OidcUser/Authentication saved and read back properly?
    |
    v
Does the authorized client hold an access token with right audience/scope?
    |
    v
Does WebClient send the token to an authorized API?
~~~

When debugging, log only safe metadata such as registration ID, error category, route template, correlation ID, session state, and HTTP status. **Never log authorization codes, real state/nonce values, PKCE verifiers, client secrets, access tokens, refresh tokens, or raw ID Tokens.**

## 21. Practice Exercises

### Exercise 1 — Choosing the Right Security Stack

A project adds <code>spring-boot-starter-webflux</code> while keeping <code>spring-boot-starter-web</code> and configures a <code>SecurityWebFilterChain</code>. The application actually starts as MVC.

**Question:** Why might the reactive configuration fail to take effect as expected?

**Answer:** When both MVC and WebFlux are present, Boot usually selects Servlet/MVC by default. You need to confirm the web application type and use <code>HttpSecurity</code>/<code>SecurityFilterChain</code> for Servlet, or build a truly reactive app with <code>ServerHttpSecurity</code>/<code>SecurityWebFilterChain</code>.

### Exercise 2 — Authorization Code Flow

Put the steps in the right order:

~~~text
Create authorization request + state
→ Browser redirects to OP
→ OP authenticates and returns code/state
→ Client verifies state
→ Client exchanges code for tokens
→ Verify ID Token
→ Create OidcUser/Authentication
→ Store SecurityContext/authorized client
~~~

**Question:** Does the browser directly receive the refresh token from the Token Endpoint?

**Answer:** In the confidential server-side OIDC Client model of this lesson, the token exchange happens between the backend and the OP; the browser receives only redirects/cookies and does not need to receive raw refresh tokens.

### Exercise 3 — state, nonce, and PKCE

**Question:** Can <code>state</code>, <code>nonce</code>, and PKCE all be replaced by a single arbitrary <code>requestId</code> variable?

**Answer:** No. Each mechanism has a distinct purpose: `state` correlates the callback, `nonce` binds the ID Token to the OIDC request, and PKCE binds the authorization code to the Client that initiated the request. Use the protocol and framework behavior properly.

### Exercise 4 — SecurityContext in WebFlux

A reactive service calls <code>SecurityContextHolder.getContext()</code> and assumes it always contains the current user.

**Question:** What is the more appropriate way to read it?

**Answer:** Use <code>ReactiveSecurityContextHolder.getContext()</code> within the pipeline, or WebFlux authentication/principal injection. Avoid relying on ThreadLocal in reactive execution.

### Exercise 5 — WebClient and Audience

OIDC login succeeds and the authorized client holds an access token for the UserInfo API. The backend sends that token to the Billing API and gets a 401.

**Question:** Does a valid ID Token prove that the Billing API must accept the access token?

**Answer:** No. An ID Token targets the Client audience; an access token has its own audience/scopes. A token appropriate for the Billing API must be issued and validated by the Resource Server.

### Exercise 6 — Event-Loop Blocking

A user service after callback calls blocking JDBC directly inside <code>map(...)</code>.

**Question:** What is the risk and how do you fix it?

**Answer:** Blocking I/O stalls the reactive event-loop, increasing latency and reducing throughput. Use a reactive database/client or isolate blocking calls onto a bounded/measured scheduler. Never call <code>block()</code> in the authentication pipeline.

### Exercise 7 — Missing State in a Cluster

The authorization request is created on instance A; the callback from the OP is routed by the load balancer to instance B and fails with missing state.

**Question:** Should you disable state validation?

**Answer:** No. Configure a shared `WebSession` or appropriate routing/session affinity, and check cookies, the session repository, and proxies. Disabling state validation weakens the OAuth2 flow.

### Exercise 8 — Multiple SecurityWebFilterChains

An API chain with matcher <code>/**</code> is placed at <code>@Order(1)</code>, while the web OIDC Login chain is at <code>@Order(2)</code>. The callback never runs.

**Question:** Why?

**Answer:** The first chain matches every request and is chosen first, preventing the callback from reaching the chain with the OAuth2 Login `WebFilter`. Match only specific API paths in the first chain and keep login/callback paths in the web chain.

### Exercise 9 — Distinguishing OAuth2User and OidcUser

Provider A does not use the <code>openid</code> scope, while Provider B uses <code>openid profile</code>.

**Question:** Can every principal be cast to <code>OidcUser</code>?

**Answer:** No. Spring Security OAuth2 Login typically produces <code>OAuth2User</code> for non-OIDC providers, while OIDC Login produces <code>OidcUser</code>. Controller and authorization logic must account for the principal type and provider configuration.

### Exercise 10 — Hands-On WebFlux Login

1. Create a Spring Boot WebFlux app without unintentionally mixing in the web MVC starter.
2. Configure an OIDC `ClientRegistration` with issuer, Client ID/secret, <code>openid</code> scope, and a registered callback.
3. Create a <code>SecurityWebFilterChain</code> with <code>oauth2Login()</code>.
4. Open <code>/oauth2/authorization/company</code> and observe the redirect to the OP.
5. After login, use <code>/me</code> to inspect the subject/issuer and presence of UserInfo, **without displaying tokens**.
6. Use <code>WebClient</code> with an authorized client to call a test API **with matching audience/scopes**.
7. Test state mismatch, wrong redirect URI, rejected token, and missing scope cases.
8. Test parallel browser sessions and describe where `WebSession`/authorized clients are stored.
9. Use <code>WebTestClient</code> with mock OIDC login for controller security tests, distinguishing it from real token-exchange integration tests.
10. Record results using HTTP statuses, registration IDs, error codes, and safe correlation IDs.

## 22. Summary

- WebFlux implements OAuth2/OIDC Login using **<code>SecurityWebFilterChain</code>, <code>ServerHttpSecurity</code>, WebFilters, `WebSession`, and the Reactor Context**, replacing the familiar Servlet abstractions.
- The login initiation URL is typically <code>/oauth2/authorization/{registrationId}</code>; the authorization code callback is typically <code>/login/oauth2/code/{registrationId}</code>.
- An authorization request needs <code>state</code> to correlate the callback; with OIDC, <code>nonce</code> binds the ID Token, and PKCE protects the authorization code where applicable.
- The OP authenticates the user and returns an authorization code; the backend exchanges the code at the Token Endpoint and verifies the ID Token. **Never trust claims from an unverified JWT.**
- OIDC Login creates an <code>OidcUser</code> principal; plain OAuth2 Login may use <code>OAuth2User</code>. ID Tokens and UserInfo are distinct from access tokens used for downstream APIs.
- The reactive security context propagates through **<code>ReactiveSecurityContextHolder</code> and the Reactor Context**; avoid ThreadLocal assumptions or arbitrary <code>block()</code>/<code>subscribe()</code> calls.
- <code>WebClient</code> and <code>ServerOAuth2AuthorizedClientExchangeFilterFunction</code> enable using authorized clients; send access tokens only to APIs with the **right audience/scopes**.
- Browser `WebSession`, authorization request repository, and authorized client storage are **three distinct states**. Multi-instance deployments need appropriate session/token sharing and refresh concurrency handling.
- With multiple chains, <code>securityMatcher</code> and <code>@Order</code> must ensure authorization initiation/callback belong to the chain configuring OAuth2 Login.
- Maintain HTTPS, secure session cookies, CSRF protection on browser routes, state/nonce validation, role/tenant enforcement, and avoid logging tokens/credentials.

### References

- **Spring Security Reference — Reactive OAuth2 Login:** configuring <code>oauth2Login()</code>, authorization flow, `ClientRegistration`, and OIDC Login in WebFlux.
- **Spring Security Reference — Reactive OAuth2 Client:** <code>ReactiveOAuth2AuthorizedClientManager</code>, <code>ServerOAuth2AuthorizedClientRepository</code>, and <code>WebClient</code>.
- **Spring Security Reference — Reactive SecurityContext:** <code>ReactiveSecurityContextHolder</code> and the Reactor Context.
- **Spring Security Reference — WebFlux Security:** <code>SecurityWebFilterChain</code>, <code>ServerHttpSecurity</code>, multiple chains, and CSRF.
- **Spring Security Java API:** <code>OAuth2AuthorizationRequestRedirectWebFilter</code>, <code>OAuth2LoginAuthenticationWebFilter</code>, <code>WebSessionOAuth2ServerAuthorizationRequestRepository</code>, <code>ServerOAuth2AuthorizedClientExchangeFilterFunction</code>.
- **Spring Framework Reference — WebFlux / WebClient:** reactive execution, `WebClient` filters, and HTTP response handling.
- **Spring Security Test — WebTestClient:** <code>SecurityMockServerConfigurers.mockOidcLogin()</code> for mocking authentication in reactive tests.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Authorization Code Flow, token exchange, and access/refresh tokens.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** <code>code_challenge</code> and <code>code_verifier</code>.
- **OpenID Connect Core 1.0:** OIDC Authorization Code Flow, ID Token, nonce, and UserInfo.
- **OpenID Connect Discovery 1.0:** issuer and metadata used to configure an OpenID Provider.
