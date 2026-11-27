# 1.3. Federated Login and Calling APIs on Behalf of the User Use Case

## 1. Real-World Scenario

Suppose a company has an **Employee Portal** for employees to view their profiles, leave requests, and authorized orders. The company already has a centralized identity management system (Identity Provider, abbreviated **IdP**). Users want to:

1. Open the Employee Portal and choose **Sign in with company account** without creating a separate password for the Portal.
2. After logging in, view their name and account details on the Portal.
3. Select **My Orders**. The Portal calls the **Orders API** to fetch data belonging to the current employee, according to the permissions they have been granted.

In Spring Security, this is a scenario combining two related capabilities that serve two different purposes:

- **OpenID Connect (OIDC) login** authenticates the user and tells the Portal who is logged in.
- **OAuth 2.0 Client** enables the Portal to obtain and use an **access token** to call the Orders API **on behalf of the logged-in user**.

For example, employee An is allowed to read her own orders. When An opens the orders screen, the Portal does not use a shared administrative application privilege to access all data; the Portal sends an access token representing An's authorization session. The Orders API validates the token, read permission, and user identity before returning results.

### Expected Learning Outcomes

After this lesson, readers should be able to explain who logs in where, which token serves which purpose, how Spring Security stores login state and access tokens, and how a web application calls APIs on behalf of a user without exposing the OAuth Client's secret to the browser.

## 2. Roles in the Architecture

| Component | Role | Example |
|---|---|---|
| **End User / Resource Owner** | User logging in and owner of the data and access rights | Employee An |
| **Browser** | Renders UI, follows login redirects, holds the Portal's session cookie | An's browser |
| **OAuth 2.0 Client / Relying Party** | Application directing the user to the IdP, handling callbacks, storing authorized clients, and calling APIs | Spring Boot Employee Portal |
| **OpenID Provider / Authorization Server** | Authenticates users, issues authorization codes and tokens according to policy | Company IdP |
| **Resource Server** | API receiving access tokens, verifying tokens, and enforcing access permissions | Spring Security Orders API |

An IdP can simultaneously be an **OpenID Provider** (supporting OIDC) and an **Authorization Server** (supporting OAuth 2.0). In this situation, the Portal plays **two roles at the same time**: the party relying on OIDC identity to log users in and the OAuth Client using granted permissions to access resources.

The concept of **federated login** means the application relies on a trusted identity provider instead of collecting passwords itself. When the same IdP serves multiple applications, users can experience SSO: once logged into the IdP, logging into the next application often does not require re-entering a password, depending on session policies and additional authentication requirements.

## 3. Distinguishing Authentication, Authorization, and Tokens

| Concept | Answers the Question | Primary Consumer |
|---|---|---|
| **OIDC ID Token** | Who was authenticated, when, and by which IdP? | **Portal (OIDC Client)** |
| **OAuth 2.0 Access Token** | Which resources can the client call, with what permissions, and for how long? | **Orders API (Resource Server)** |
| **Refresh Token** (if issued) | Can the client obtain a new access token without sending the user to log in again? | **Portal**, used with the token endpoint |
| **Portal session cookie** | Which Portal login session is the browser bound to? | **Portal**, when receiving requests from the browser |
| **Authorization Code** | Short-lived, single-use code exchanged for tokens at the token endpoint | **Portal**, at the callback step |

**An ID Token is not an access token.** An ID Token contains OIDC claims such as **iss** (issuer), **sub** (stable identifier within the issuer scope), **aud** (audience of the ID Token, usually the client ID), **exp**, and may include profile information. The Portal validates the ID Token at login; do not send the ID Token to the Orders API in place of an access token.

**An access token is proof of authorization for an API.** The token may be a JWT or an opaque token, depending on the IdP. The API needs to verify its validity and usage scope: appropriate signature or introspection, issuer, timestamps, **audience** intended for the API, along with scopes/authorities and business rules.

**Scope and audience are not synonymous:**

- Scope, such as **orders.read**, describes the type of operation granted.
- Audience, such as **orders-api**, identifies the API intended to receive the access token. A token carrying **orders.read** but intended for another API must still not be accepted by the Orders API.
- Business permissions, such as "An can only view An's orders", must still be enforced at the API using trusted identity and data; having the **orders.read** scope alone is not enough.

OAuth 2.0 supports authorization; OIDC adds the identity authentication layer. You can use OAuth 2.0 without OIDC login, but a web application wanting to **log users in** should rely on an explicit authentication mechanism such as OIDC rather than inferring identity merely from receiving an access token.

## 4. Overall Flow: Authorization Code + OIDC + Calling API

The appropriate flow for a server-side Spring Boot web application maintaining a session is the **Authorization Code Flow**. **PKCE** can be added to bind the authorization code to the initiating request, even when the client has a secret.

~~~mermaid
sequenceDiagram
    actor User as Employee
    participant Browser as Browser
    participant Portal as Spring Boot Portal (OAuth2 Client)
    participant IdP as OIDC Provider / Authorization Server
    participant API as Orders API (Resource Server)

    User->>Browser: Choose Company Login
    Browser->>Portal: GET /oauth2/authorization/company
    Portal-->>Browser: 302 to authorization endpoint (state, nonce, PKCE)
    Browser->>IdP: Authorization request
    IdP->>User: Authenticate and request consent if needed
    IdP-->>Browser: 302 to callback ?code=...&state=...
    Browser->>Portal: GET /login/oauth2/code/company
    Portal->>IdP: POST /token (code, client auth, PKCE verifier)
    IdP-->>Portal: ID Token + Access Token (+ Refresh Token)
    Portal->>Portal: Validate ID Token; create SecurityContext and store authorized client
    Portal-->>Browser: Session cookie, redirect to post-login page
    Browser->>Portal: GET /bff/orders + session cookie
    Portal->>Portal: Retrieve authorized client of logged-in user
    Portal->>API: GET /api/orders + Authorization: Bearer access_token
    API->>API: Validate token, audience, scope, and data permissions
    API-->>Portal: User's orders
    Portal-->>Browser: JSON / orders UI
~~~

Notable steps:

1. **Initiate login:** Spring Security by default provides the URL **/oauth2/authorization/{registrationId}**; in this example **registrationId** is **company**.
2. **Redirect to IdP:** The request uses **response_type=code**, **client_id**, **redirect_uri**, scopes such as **openid profile email orders.read**, **state**, along with OIDC/PKCE parameters when configured. **state** binds the callback to the initiating request, preventing CSRF attacks against the authorization flow. **nonce** binds the ID Token to the OIDC authentication attempt; **PKCE** binds the authorization code to the client that initiated the transaction.
3. **Centralized authentication:** The user enters credentials at the IdP; the Portal never sees the password. The IdP can apply MFA, SSO, access conditions, and consent depending on the organization.
4. **Callback:** The IdP redirects the browser back to the registered URL with a short-lived **authorization code** and **state**. Spring Security validates request state before exchanging the code.
5. **Exchange code for tokens:** The Portal sends a **server-to-server** request to the token endpoint, using the registered client authentication method and **code_verifier** when PKCE applies. The ID Token is verified per OIDC requirements, including signature, issuer, audience, expiration, and nonce when present.
6. **Create login session:** Spring Security creates an **Authentication**, typically with an **OidcUser** principal, and stores it in **SecurityContext** bound to the HTTP session. At the same time, **OAuth2AuthorizedClient** associates the client registration, user, and received tokens.
7. **User accesses data:** The browser calls the Portal using the session cookie. The Portal identifies the user from `SecurityContext`, finds the corresponding access token, and calls the Orders API over HTTPS with **Authorization: Bearer ...**.
8. **API enforces access control:** The API validates the token, then enforces the **orders.read** permission and checks whether the orders belong to the user. The browser only receives the data the application needs to display.

There is no OAuth 2.0 requirement forcing the access token to be exposed to browser JavaScript. With the **Backend for Frontend (BFF)** pattern or a session-based MVC application, the Portal keeps tokens on the server side and the browser only sends a session cookie.

## 5. Implementation Illustration with Spring Boot and Spring Security

The examples below use **Java 17+** and modern Spring Security configuration syntax on Spring Boot 3 / Spring Security 6. They illustrate each application's responsibilities; URLs, client IDs, scopes, and audiences are placeholder values that must be configured correspondingly in a real IdP.

### 5.1. Configuring the IdP Before Running the Application

Create an OAuth/OIDC client **portal-web** at the IdP, with:

- Client type: **confidential web client** because the Portal handles tokens on the server side and can safely hold a client secret.
- Authorization grant: **authorization_code**; enabling/supporting **PKCE S256** is recommended.
- Registered redirect URI: **http://localhost:8080/login/oauth2/code/company** for development. In production, use HTTPS and the exact domain name.
- OIDC scope **openid** and only the scopes actually needed, such as **profile**, **email**, **orders.read**.
- Access token intended for **Orders API**, with an appropriate audience (e.g., **orders-api**). How audience is configured depends on the IdP.

The client secret must not be embedded in source code, HTML, or JavaScript. Options like **offline_access**, refresh tokens, consent, logout endpoints, or how audiences are added vary across providers; do not assume every provider supports them identically.

### 5.2. Portal Application: OIDC Login and OAuth2 Client

Core Gradle dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.springframework.boot:spring-boot-starter-webflux' // use WebClient
}
~~~

The Portal's **application.yml** file:

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
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
              - orders.read
        provider:
          company:
            issuer-uri: https://sso.example.test/realms/acme

orders:
  api-base-url: http://localhost:8081
~~~

The **issuer-uri** property allows Spring Security to load OIDC/OAuth metadata from the discovery endpoint when supported by the IdP. Replace the example address with your IdP's actual issuer. If the application sits behind a reverse proxy, ensure forwarded headers are configured and **{baseUrl}** produces an HTTPS redirect URI matching the registration.

**SecurityFilterChain** protecting pages that require login:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class PortalSecurityConfig {

    @Bean
    SecurityFilterChain portalSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

**oauth2Login()** handles redirects, callbacks, and creating the OIDC authentication session. **oauth2Client()** adds authorized client management so the application can call protected resources. This configuration preserves default CSRF protection for state-changing requests.

Example controller that both reads identity from the OIDC principal and retrieves the currently logged-in user's access token to call an API:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

@RestController
class PortalController {

    private final WebClient ordersApi;

    PortalController(WebClient.Builder webClientBuilder,
                     @Value("${orders.api-base-url}") String baseUrl) {
        this.ordersApi = webClientBuilder.baseUrl(baseUrl).build();
    }

    @GetMapping("/me")
    Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        // sub is taken from the identity authenticated by the IdP.
        return Map.of("sub", user.getSubject());
    }

    @GetMapping("/bff/orders")
    List<OrderView> myOrders(
        @RegisteredOAuth2AuthorizedClient("company")
        OAuth2AuthorizedClient authorizedClient
    ) {
        String accessToken = authorizedClient.getAccessToken().getTokenValue();

        return ordersApi.get()
            .uri("/api/orders")
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .bodyToFlux(OrderView.class)
            .collectList()
            .block();
    }

    record OrderView(String id, String title) {}
}
~~~

The core piece lies in **@RegisteredOAuth2AuthorizedClient("company")**: Spring Security finds the authorized client bound to the **company** registration and the current principal, rather than using a single system-wide token. When a provider configuration supports refresh and the IdP issues a refresh token, the authorized client manager can request a new access token when needed; never assume a refresh token always exists.

The example explicitly attaches the **Bearer** header to make the path of the access token clear. In an application with many API calls, you can also configure **ServletOAuth2AuthorizedClientExchangeFilterFunction** on `WebClient` to automatically select the authorized client and attach the token, though you must clearly specify the registration/principal per request to avoid accidentally sending a token to an unrelated API.

### 5.3. Orders API Application: Resource Server

The Orders API is a standalone application and **does not need to perform OIDC login** to handle requests carrying bearer tokens. It requires dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Example API configuration using **JWT** access tokens:

~~~yaml
server:
  port: 8081

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://sso.example.test/realms/acme

security:
  expected-audience: orders-api
~~~

A SecurityFilterChain for a pure bearer-token API, without cookies or forms:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersApiSecurityConfig {

    @Bean
    SecurityFilterChain ordersApiSecurity(HttpSecurity http) throws Exception {
        return http
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**CSRF is disabled only in this API example** because it is a stateless Resource Server that only accepts bearer tokens via headers and does not use cookies for authentication. Do not copy disabling CSRF into the Portal that uses session cookies. Spring Security usually converts a JWT's scope into an authority prefixed with **SCOPE_**, so the **orders.read** scope corresponds to **SCOPE_orders.read** in endpoint checks.

Beyond verifying signature, issuer, and token expiration, the API must verify the appropriate **audience**. Configuring **issuer-uri** by itself does not replace audience checking according to the contract between the API and the Authorization Server. Example validator for JWT:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoders;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class JwtAudienceConfig {

    @Bean
    JwtDecoder jwtDecoder(
        @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
        String issuer,
        @Value("${security.expected-audience}")
        String expectedAudience
    ) {
        NimbusJwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(expectedAudience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token", "Unexpected audience", null));

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(issuer),
            audienceValidator));
        return decoder;
    }
}
~~~

The API determines the subject from the **verified** token, never trusting a parameter like **?userId=an** passed by the browser:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrdersController {

    @GetMapping("/api/orders")
    List<Map<String, String>> myOrders(@AuthenticationPrincipal Jwt jwt) {
        String ownerSubject = jwt.getSubject();

        // Illustration: in real deployment, query DB by ownerSubject
        // and check additional record-level authorization policies.
        return List.of(Map.of(
            "id", "ORD-101",
            "title", "Sample order of " + ownerSubject
        ));
    }
}
~~~

In production, the API usually maps the **(issuer, subject)** pair to an internal account and queries the records that user is authorized to read. Do not use an unstandardized name or email claim as an authorization key unless the system has an explicit policy. If the IdP issues **opaque access tokens**, the Resource Server must use **introspection** instead of a JWT decoder.

## 6. A Request Viewed from Browser, Portal, and API

### 6.1. Browser Initiates Login

~~~http
GET /oauth2/authorization/company HTTP/1.1
Host: localhost:8080
~~~

Spring Security returns **302** pointing to the IdP's authorization endpoint; after login the IdP calls the registered callback. The browser receives the Portal's session cookie (for example **JSESSIONID**, additionally configured with **Secure**, **HttpOnly**, **SameSite** appropriate for HTTPS and redirect flows).

### 6.2. Browser Accesses Application Data

~~~http
GET /bff/orders HTTP/1.1
Host: localhost:8080
Cookie: JSESSIONID=<session-value>
~~~

The browser **does not need to receive the access token**. The Portal uses the session to identify the user, looks up the authorized client, and calls the API:

~~~http
GET /api/orders HTTP/1.1
Host: localhost:8081
Authorization: Bearer <valid-access-token-for-orders-api>
~~~

A successful API call can return:

~~~json
[
  { "id": "ORD-101", "title": "Sample order" }
]
~~~

These are **two separate trust relationships**: the browser proves its session to the Portal using a cookie; the Portal proves API access rights using an access token. A session cookie is not used as a bearer token for the Orders API, and an access token must never be placed in URLs, logs, or HTML responses.

## 7. When to Use This Pattern?

| Situation | Why It Fits |
|---|---|
| **Employee portal using company accounts** | Leverages centralized IdP, SSO, MFA, and account lifecycle management |
| **Portal calling orders, schedule, or personal document APIs** | Each request carries permissions granted to the user rather than broad system-wide privileges |
| **BFF for a web frontend** | Keeps client secrets and access/refresh tokens on the server; frontend only needs a session cookie |
| **One Portal calling multiple APIs** | Can manage separate scopes/audiences/tokens per API; avoids misusing tokens across resources |

This pattern differs from **client_credentials**: `client_credentials` represents the application itself, not An. If a background job needs application permissions, `client_credentials` can make sense; if you need to know the data and permissions of a logged-in user, you must choose an authorization model suitable for that user.

Additionally, OAuth 2.0 **Token Exchange / On-Behalf-Of** is a separate approach when an intermediate API must receive an inbound token and exchange it for a new token for another API. Do not assume every system supports token exchange; in the example where the Portal holds the authorized client, the Portal calls the Orders API directly with the access token issued for that API.

## 8. Session, Token, and Logout Lifecycle

**The Portal's login session** and **the access token's lifetime** can differ. A valid cookie session does not guarantee the access token is still valid. When the access token expires:

- If the IdP issued a refresh token and the client is configured to support refresh, Spring Security can use the refresh token to obtain a new access token; the new token must be saved back to the authorized client repository/service.
- If permission is missing or refresh is impossible, the user may need to go through the authorization flow again. The application should handle this error by redirecting to login or showing a clear message, without infinite request retries.
- If permissions are revoked, the token may be rejected depending on token policy, introspection, lifetime, and the IdP's revocation mechanism. Do not assume every JWT becomes invalid immediately when the user logs out.

**Logout** can involve several separate actions: invalidating the Portal session, clearing the Portal's tokens/authorized client, and depending on the IdP performing **OIDC RP-Initiated Logout** to end the centralized login session. Deleting only the Portal cookie does not necessarily log out of the IdP; logging out only at the IdP also does not automatically revoke every issued access token. Logout design must follow product policy and the IdP's supported capabilities.

The default authorized client storage mechanism may suit development environments, but it does not automatically guarantee persistence across multiple instances. When deploying across multiple nodes or when session/token revocation management is needed, choose an appropriate storage repository/service, protect stored tokens, and control access permissions and lifetimes.

## 9. Trust Boundaries and Key Security Points

1. **Always use HTTPS** for endpoints in production; register exact redirect URIs. Do not use arbitrary wildcard redirect URIs.
2. **Protect the authorization flow:** validate **state**, use **nonce** properly with OIDC, and prefer **PKCE S256**. Spring Security handles much of the flow; if customizing resolvers/filters, preserve these checks.
3. **Keep secrets on the server:** client secrets, access tokens, and refresh tokens must not appear in frontend source, URLs, analytics, or application logs. Secrets should be loaded via a secret manager or secure environment.
4. **Protect cookies and prevent CSRF:** a Portal using session cookies needs **Secure**, **HttpOnly**, **SameSite** per deployment flow; preserve CSRF protection for state-changing operations. CORS and CSRF solve different problems.
5. **Do not confuse tokens:** use ID Token for authentication at the Client; access token for the Resource Server; do not use refresh tokens to call APIs; do not send access tokens to hosts outside the intended audience.
6. **The API is responsible for its own authorization:** validate token, audience, scope, and resource-level permissions. Never trust user IDs, roles, or scopes sent directly by the browser outside a verified token.
7. **Limit permissions:** only request needed scopes; if another API is needed, define the corresponding audience/scope and token-acquisition mechanism. A user-granted token does not implicitly grant permission to read all data.
8. **Safe error handling:** the API returns **401 Unauthorized** for missing/invalid tokens and **403 Forbidden** when the token is valid but lacks permissions; the Portal must not expose tokens or sensitive details in error messages.

A note on **SSO**: the ability to log in without re-entering a password depends on the IdP session, MFA policy, `prompt`/`login_hint`/`max_age`, and account status. Integrating OIDC does not mean every login attempt will automatically skip authentication.

## 10. How to Self-Verify the Flow

Once the IdP is configured and both applications run with a valid issuer/tokens, you can verify with these scenarios:

| Action | Expected Result |
|---|---|
| Open **/bff/orders** while unauthenticated | Portal sends the browser into the OIDC login flow |
| Log in at IdP and return to Portal | Portal has a valid session; **/me** returns the user's **sub** |
| Call **/bff/orders** after logging in | Portal calls Orders API with the current authorized client's access token and displays data |
| Call **/api/orders** directly without a bearer token | Resource Server returns **401** |
| Call API with a valid token missing **orders.read** | Resource Server returns **403** |
| Call API with a token lacking the **orders-api** audience | Resource Server rejects the token, typically **401** |
| Log in as another user | API retrieves data for that user's identity; ignores any user ID self-assigned by Portal/browser |
| Access token expires | Refreshes or requests re-authorization depending on IdP capabilities and client config |

These tests depend on how the IdP issues tokens, so inspect **issuer**, **scope**, **audience**, and expiration using secure admin tools or debug mechanisms with sensitive data masked; never copy real bearer tokens into logs or public docs.

## 11. Common Misconceptions

**"Successful login means any API can be called."** Incorrect. OIDC authentication only confirms the login session at the Portal. API access still depends on the access token, audience, scope, user policies, and business checks at the Resource Server.

**"Once you have an ID Token, send the ID Token to the API."** Incorrect. The ID Token is issued for the OIDC Client; the API needs an access token tailored to that API itself.

**"Passing userId in a query parameter is enough to call on behalf of the user."** Incorrect. A client-chosen user ID can be forged. The API must extract the verified identifier from the access token or introspection result, then check permissions against the data.

**"Using client_credentials calls the API on behalf of the user."** Incorrect in this context. That grant issues a token representing the client/application and carries no logged-in user semantics.

**"Spring Security automatically enforces per-order authorization."** Incorrect. Spring Security provides the foundation for authentication and authority checks; the API must still check ownership, tenant, data status, and business rules.

**"One bearer token works for every microservice."** Should not be assumed. Tokens must only be sent to resources permitted by the authorization server's granted permissions and audience. If you need to call another API, design appropriate scopes, audiences, and authorization mechanisms.

## 12. Architecture Summary

In this use case, **OIDC** lets the Portal perform federated login and build the employee's **SecurityContext**. **OAuth 2.0 Client** manages the authorization code flow and **OAuth2AuthorizedClient** holding the access token so the Portal can call the **Orders API**. **Spring Security Resource Server** protects the API by validating the access token, scope, audience, and data access permissions.

The boundary of responsibility is: **the IdP authenticates and issues tokens; the Portal maintains the user session and makes authorized calls; the API decides which resources are returned.** Keeping this separation prevents confusing ID Tokens with access tokens, avoids using application privileges in place of user permissions, and builds both federated login and user-delegated API calls on a clear model.
