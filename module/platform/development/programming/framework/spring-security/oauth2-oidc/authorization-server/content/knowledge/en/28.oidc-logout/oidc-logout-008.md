# Distinguishing SSO Session Logout, Token Revocation, and Per-Application Sign-Out

## 1. Context: "Logout" Has Multiple Scopes

In an OAuth 2.0/OpenID Connect (OIDC) system using **Spring Security**, **Spring Authorization Server**, and Spring Boot, a user can sign in once at the OpenID Provider (OP) and then access multiple Relying Party (RP) applications. When they click "Sign out," the system needs to determine precisely which state must be terminated.

There are at least three independent kinds of state:

1. **Application local session (RP local session):** the cookie/session and `SecurityContext` managed by the application itself.
2. **SSO session at the OP:** the user's login session on the Authorization Server/OpenID Provider domain.
3. **OAuth authorization/token state:** access tokens, refresh tokens, and authorization grants issued to a client.

In addition, to log a user out across multiple applications, the OP and RPs can coordinate via OIDC Session Management, Front-Channel Logout, or Back-Channel Logout.

These mechanisms are related, yet they do not automatically replace one another. Deleting one RP's cookie does not delete the SSO cookie at the OP. Ending the SSO session at the OP also does not automatically invalidate all access tokens. Revoking a refresh token does not delete active login sessions at RPs.

This lesson belongs to the **OIDC Logout** chapter and focuses on distinguishing SSO session logout, token revocation, and per-application sign-out, while guiding configuration on both OP and RP sides in Spring.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish local logout, RP-Initiated Logout, logout notifications, and OAuth token revocation.
2. Explain why a user may remain logged into Application B after logging out of Application A.
3. Select the appropriate mechanism for "sign out of this app," "sign out of SSO," and "sign out of all apps."
4. Understand the roles of `end_session_endpoint`, `id_token_hint`, `post_logout_redirect_uri`, and `state`.
5. Distinguish Front-Channel Logout from Back-Channel Logout.
6. Understand `sid`, `sub`, and the Logout Token in Back-Channel Logout.
7. Configure local logout and RP-Initiated Logout with Spring Security.
8. Enable the OIDC Logout Endpoint and manage `SessionRegistry` in Spring Authorization Server.
9. Distinguish logout from RFC 7009 Token Revocation.
10. Design testing, operations, and troubleshooting in a multi-application environment.

## 2. Multi-Application Model Sharing SSO

Suppose an enterprise has three applications:

- `portal.example.com`: employee portal.
- `orders.example.com`: order management application.
- `reports.example.com`: reporting application.
- `auth.example.com`: OpenID Provider/Authorization Server.

A user logs into the OP via `portal`. Next, they open `orders` and `reports`; both applications redirect the browser to the OP. Because the OP still holds an SSO session, the user can be authenticated without re-entering a password.

Each application still maintains its own local session. The cookie for `portal.example.com` is not the cookie for `orders.example.com`; the SSO cookie for `auth.example.com` is also an independent cookie.

~~~mermaid
flowchart TB
    U[Browser / End-User]
    OP[OpenID Provider<br/>auth.example.com<br/>SSO Session]
    A[portal.example.com<br/>RP Session A]
    B[orders.example.com<br/>RP Session B]
    C[reports.example.com<br/>RP Session C]
    T[OAuth Token Store<br/>Access / Refresh Tokens]

    U --> A
    U --> B
    U --> C
    A <--> OP
    B <--> OP
    C <--> OP
    A --> T
    B --> T
    C --> T
~~~

A logout action may affect one or more components in the diagram. Before implementing, define the logout scope and how each component gets notified.

## 3. Three Kinds of State to Distinguish

| State | Managed By | Example Data | How It Ends |
|---|---|---|---|
| RP local session | Each application | `HttpSession`, session cookie, `SecurityContext` | Local logout at the RP |
| OP SSO session | Authorization Server/OP | OP `HttpSession`, SSO cookie, session registry | RP-Initiated Logout or logout at the OP |
| OAuth authorization/token | Authorization Server and Resource Server | Access token, refresh token, authorization grant, token state | Token Revocation, expiry, or revocation policy |

### 3.1. RP Local Session

An RP usually creates its own session after completing OIDC login. This session can hold `SecurityContext`, user details, and references to the server-side stored Authorized Client/tokens.

Local logout at the RP can:

- Clear `SecurityContext`.
- Invalidate `HttpSession`.
- Delete the session cookie for the RP's own domain.
- Remove or mark the user's cached tokens as no longer usable.
- Redirect the user to a logged-out page.

This action has no authority to delete cookies on the OP domain or on another RP's domain.

### 3.2. OP SSO Session

The OP manages the shared login session across OIDC clients. When the browser returns to the OP to start a new authorization request, the SSO cookie lets the OP recognize the already logged-in user.

If the RP only clears its local session, the OP SSO session remains active. When the user clicks Login again, the OP can issue a new code without showing a login screen.

### 3.3. OAuth Tokens and Authorization Grants

Access tokens and refresh tokens are credentials representing access rights. They have their own lifecycles, can be stored in an authorization store, and can be revoked according to policy.

Deleting a session cookie does not automatically revoke tokens. Conversely, revoking a token does not necessarily delete the OP browser session or RP local sessions.

## 4. Four User Actions Commonly Lumped Under "Logout"

| Product Need | Desired Scope | Appropriate Mechanism |
|---|---|---|
| Sign out of the current application | Only the currently open RP | Local logout |
| Sign out of SSO | End the session at the OP | RP-Initiated Logout |
| Sign out of all logged-in applications | OP ends SSO and RPs receive notifications and clear local sessions | RP-Initiated Logout combined with Front/Back-Channel or equivalent mechanism |
| Sign out and invalidate credentials | End required sessions and revoke tokens/grants | Logout flow combined with RFC 7009 per policy |

Not every product needs "logout all." Banking, admin, or sensitive-data applications may require revoking refresh tokens and access tokens when a user logs out. Internal apps might only need local logout when a user switches accounts on the same machine.

## 5. Local Logout: Signing Out of One Application Only

Local logout is an operation at the RP. Spring Security provides default logout support configurable via the `logout()` DSL.

Example:

~~~java
@Configuration
@EnableWebSecurity
class ApplicationSecurityConfig {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        return http.build();
    }
}
~~~

With default servlet configuration, Spring Security exposes the `POST /logout` endpoint. The request requires a CSRF token when CSRF protection is enabled, which is the right default for cookie/session-based web applications.

### 5.1. What Does Spring Security Do During Local Logout?

The default logout handlers typically perform the steps needed to:

- Remove `Authentication` from `SecurityContext`.
- Clear `SecurityContext` from the repository.
- Invalidate `HttpSession` if present.
- Delete configured session cookies.
- Invoke `LogoutSuccessHandler` after logout handlers complete.

Applications can add handlers to delete custom session data or clean up server-side authorized-client/token caches.

### 5.2. Local Logout Does Not End the OP SSO Session

For example, a user logs out at `orders.example.com`:

1. Spring Security deletes `orders`'s session.
2. `orders`'s session cookie becomes invalid.
3. The SSO cookie at `auth.example.com` still remains.
4. Sessions at `portal` and `reports` still remain.
5. If the user visits `orders` again, the OP can log them back in immediately via the SSO session.

This is the right behavior when the product wants "Sign out from this application."

### 5.3. Do Not Use GET to Change Logout State

For cookie-based local logout, keep CSRF protection enabled and use POST. Do not expose a GET endpoint like `/logout?user=...` to delete sessions, because browsers, crawlers, or third-party pages can trigger unintended requests.

Do not place access tokens or refresh tokens in URLs for logout.

## 6. RP-Initiated Logout: Requesting the OP to End the SSO Session

**OpenID Connect RP-Initiated Logout 1.0** defines how an RP requests the OP to log out an End-User. The RP directs the User Agent to the OP's Logout Endpoint, usually obtained from Provider Discovery Metadata via the `end_session_endpoint` attribute.

RP-Initiated Logout is an operation initiated by one application, yet targets the user's session at the OP. It can be combined with Session Management, Front-Channel Logout, and/or Back-Channel Logout to notify other RPs.

### 6.1. Common Parameters

| Parameter | Meaning |
|---|---|
| `id_token_hint` | ID Token issued by the OP to the RP; RECOMMENDED for the OP to identify the session/user to log out |
| `post_logout_redirect_uri` | URI to which the OP returns the browser after logout; must be pre-registered with the OP |
| `state` | Opaque value for the RP to link the logout callback to the initiated transaction |
| `client_id` | Client ID at the OP; may be used when `id_token_hint` is not sent or where permitted by spec |
| `logout_hint` | User identification hint with OP-defined semantics |
| `ui_locales` | Logout UI language hint |

`id_token_hint` is an ID Token previously issued by the OP to the RP, not an access token. The OP uses it as a hint about the user/session; it is not an access token for calling Resource Servers.

### 6.2. RP-Initiated Logout Flow

~~~mermaid
sequenceDiagram
    actor U as End-User / Browser
    participant RP as RP / orders.example.com
    participant OP as OP / auth.example.com
    participant R2 as Other RP / portal.example.com

    U->>RP: POST /logout
    RP->>RP: Delete local session
    RP-->>U: Redirect to end_session_endpoint
    U->>OP: GET/POST Logout Endpoint + id_token_hint + state
    OP->>OP: Verify hint and locate OP session
    OP->>OP: Terminate OP SSO session
    opt Supported logout notification enabled
        OP-->>R2: Front-channel or Back-channel logout
        R2->>R2: Delete corresponding session
    end
    OP-->>U: Redirect to post_logout_redirect_uri
    U->>RP: Callback + state
    RP->>RP: Verify state and display logout page
~~~

The OP must support both GET and POST at the Logout Endpoint per the RP-Initiated Logout specification. The RP can use either method depending on implementation and policy.

### 6.3. RP-Initiated Logout Does Not Mean Logging Out All RPs

When the OP ends the SSO session, the browser no longer has that SSO session for subsequent authorization requests. However, other RPs may still hold previously created local sessions.

To end local sessions at other RPs, you need a logout notification mechanism supported by both the OP and the RPs. Never assume that merely redirecting the browser through the OP suffices to delete server-side sessions across all applications.

## 7. Discovery and end_session_endpoint

The RP should retrieve the Logout Endpoint from verified Provider Configuration Discovery rather than concatenating a URL from a guessed path.

Abbreviated metadata example:

~~~json
{
  "issuer": "https://auth.example.com",
  "authorization_endpoint": "https://auth.example.com/oauth2/authorize",
  "token_endpoint": "https://auth.example.com/oauth2/token",
  "jwks_uri": "https://auth.example.com/oauth2/jwks",
  "end_session_endpoint": "https://auth.example.com/connect/logout"
}
~~~

This is an illustrative example. The actual URI depends on OP configuration. When supporting RP-Initiated Logout and Discovery, the metadata needs to advertise `end_session_endpoint`; this URL must use HTTPS.

The RP should:

- Trust a configured issuer or discovery from a trusted source.
- Verify the OP's TLS.
- Send logout requests only to the endpoint confirmed by discovery/configuration.
- Never accept an arbitrary logout URL from a browser query parameter.
- Verify callback `state` before completing the logout UI.

## 8. post_logout_redirect_uri and state

`post_logout_redirect_uri` lets the OP return the browser to the RP after logout. This URI must be pre-registered in client metadata, such as `post_logout_redirect_uris` or an equivalent registration mechanism.

Do not accept arbitrary redirect URLs from user input. If the OP allows an open redirect, attackers can abuse the trusted logout page to send users to spoofed websites.

`state` helps the RP correlate the logout response with the initial request. The RP should generate an unpredictable value, save it in the logout transaction, and verify it when receiving the callback. Do not use a static state or trust a browser-supplied state without matching it.

Logical request example:

~~~http
GET /connect/logout?
    id_token_hint=SIGNED_ID_TOKEN&
    post_logout_redirect_uri=https%3A%2F%2Forders.example.com%2Flogged-out&
    state=RANDOM_LOGOUT_STATE
Host: auth.example.com
~~~

On the wire, query parameters must be URL-encoded. Never write ID Tokens or sensitive `state` values into access logs.

## 9. Logging Out from the RP with Spring Security

Spring Security OAuth2 Client provides `OidcClientInitiatedLogoutSuccessHandler` to implement RP-Initiated Logout.

Example:

~~~java
@Configuration
@EnableWebSecurity
class OidcClientSecurityConfig {

    @Bean
    SecurityFilterChain applicationSecurity(
            HttpSecurity http,
            ClientRegistrationRepository registrations)
            throws Exception {

        OidcClientInitiatedLogoutSuccessHandler logoutSuccessHandler =
            new OidcClientInitiatedLogoutSuccessHandler(registrations);

        logoutSuccessHandler.setPostLogoutRedirectUri("{baseUrl}");

        http
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutSuccessHandler(logoutSuccessHandler));

        return http.build();
    }
}
~~~

`OidcClientInitiatedLogoutSuccessHandler` uses `ClientRegistration` to retrieve OP information, including the logout endpoint from discovery when the registration has an issuer URI. The handler constructs the redirect request after local logout handlers finish running.

### 9.1. Configuring ClientRegistration

Spring Boot example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          order-oidc:
            provider: local-op
            client-id: order-web
            client-secret: SECRET_FROM_SECRET_MANAGER
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile
        provider:
          local-op:
            issuer-uri: https://auth.example.com
~~~

The secret in the example is a placeholder. Never commit real credentials into a repository. The client registration must match the client registered at the OP.

### 9.2. Configuring the Post-Logout Redirect URI

The `{baseUrl}` value is supported by the handler and is replaced with the application's base URL. The OP must still have the corresponding URI in the post-logout redirect URI list registered for that client.

Do not let the browser pass an arbitrary URI into `setPostLogoutRedirectUri` or the logout request.

### 9.3. GET or POST to the OP?

Spring Security redirects to the Logout Endpoint via HTTP GET by default. You can configure a Form Post redirect strategy if the OP requires or policy prefers POST:

~~~java
logoutSuccessHandler.setRedirectStrategy(new FormPostRedirectStrategy());
~~~

Test compatibility with the OP and browsers before switching methods. Using POST to the OP does not replace CSRF protection on the RP's local logout endpoint.

## 10. Enabling the OIDC Logout Endpoint in Spring Authorization Server

In Spring Authorization Server 1.x, OIDC must be enabled on the Authorization Server `SecurityFilterChain`. The OIDC configurer registers the RP-Initiated Logout Endpoint and related protocol endpoints.

Configuration skeleton example:

~~~java
@Configuration
@EnableWebSecurity
class AuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http) throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
            .with(authorizationServerConfigurer, authorizationServer ->
                authorizationServer.oidc(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

In a complete configuration, the application also needs `RegisteredClientRepository`, `OAuth2AuthorizationService`, token generator, signing key/JWK source, issuer, and an End-User authentication chain.

`oidc(Customizer.withDefaults())` enables the OIDC Logout Endpoint with default configuration. When logout request customization is needed, use the `logoutEndpoint` extension point on `OidcLogoutEndpointConfigurer`.

### 10.1. Extension Points of OidcLogoutEndpointConfigurer

Spring Authorization Server 1.5.8 provides extension points such as:

- `logoutRequestConverter` / `logoutRequestConverters`: reads and converts HTTP requests into logout authentication tokens.
- `authenticationProvider` / `authenticationProviders`: processes authentication and logout request validation.
- `logoutResponseHandler`: handles success and executes logout.
- `errorResponseHandler`: returns OAuth/OIDC error responses.

Do not replace the entire provider or success handler without fully understanding default validation. A custom handler must preserve ID Token hint verification, client registration checks, and post-logout redirect URI validation per contract.

### 10.2. SessionRegistry in the Authorization Server

Spring Authorization Server uses `SessionRegistry` to track authenticated sessions when OIDC is enabled. The OIDC Logout Endpoint queries `SessionRegistry` to find `SessionInformation` corresponding to the End-User requesting logout.

If no separate bean is registered, the framework uses the default `SessionRegistryImpl`. When registering `SessionRegistryImpl`, also register `HttpSessionEventPublisher` so the registry updates when sessions are destroyed.

~~~java
@Bean
SessionRegistry sessionRegistry() {
    return new SessionRegistryImpl();
}

@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}
~~~

### 10.3. SessionRegistry in Multi-Instance Environments

`SessionRegistryImpl` stores information in the process's memory by default. If the OP runs multiple instances, design consistent session tracking across nodes or use an appropriate shared session/registry mechanism.

If login is handled on node A yet the logout request reaches node B and node B cannot find the session, results may fall short of expectations. Test load balancers, sticky sessions, session stores, and event propagation in a real deployment environment.

## 11. RegisteredClient and Post-Logout Redirect URIs

Clients must register the URIs to which the OP is permitted to redirect after logout. Registration example:

~~~java
RegisteredClient orderWeb = RegisteredClient
    .withId("order-web-registration")
    .clientId("order-web")
    .clientSecret(passwordEncoder.encode(secretFromSecretManager))
    .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .redirectUri("https://orders.example.com/login/oauth2/code/order-oidc")
    .postLogoutRedirectUri("https://orders.example.com/logged-out")
    .scope(OidcScopes.OPENID)
    .build();
~~~

This is an illustrative configuration snippet. Grants, scopes, redirect URIs, and token settings must fit the actual client.

The OP must verify that `post_logout_redirect_uri` belongs to the registered list for the right client. If the request contains both `id_token_hint` and `client_id`, the OP must ensure the client ID matches the issued ID Token.

Do not use overly broad wildcards like `https://*.example.com/**` for post-logout redirect URIs without a secure registration design.

## 12. Logging Out One RP or Multiple RPs?

Suppose a user is logged into `portal`, `orders`, and `reports`:

| Action | Portal Local Session | Orders Local Session | Reports Local Session | OP SSO Session |
|---|---|---|---|---|
| Local logout at `orders` | Remains | Deleted | Remains | Remains |
| RP-Initiated Logout from `orders`, no RP notification | Remains | Deleted per local handler | May remain | Terminated |
| OP logout with Back-Channel notification to all three RPs | Deleted if notification received/validated | Deleted | Deleted | Terminated |
| Only revoke `orders`'s refresh token | Remains | May still remain | Remains | Remains |
| Revoke token and local logout `orders` | Remains | Deleted | Remains | Remains, unless RP-Initiated Logout runs |

This table assumes each RP has its own session and the OP supports the corresponding operations. Exact outcomes depend on the notification mechanism, session correlation, and token validation strategy.

## 13. Session Management, Front-Channel, and Back-Channel Logout

RP-Initiated Logout is the mechanism by which an RP asks the OP to log out. Session Management, Front-Channel, and Back-Channel address communicating logout status from the OP to RPs.

| Mechanism | Transport | Advantages | Limitations |
|---|---|---|---|
| Session Management | Browser iframe/postMessage | Tracks OP session status | Depends on browser, iframes, and cookie policies |
| Front-Channel Logout | OP uses User Agent to call RP logout URIs | Easy integration with clearing cookies/local browser state | Can be blocked by browser third-party context rules, closed tabs, or network failures |
| Back-Channel Logout | OP calls RP directly server-to-server | Independent of open browsers; fits server-side sessions | RP must expose a public endpoint with proper session store/correlation |

RP-Initiated Logout can be used alone or combined with one or more of these notification mechanisms. Choose based on OP/RP capabilities and product requirements.

## 14. Front-Channel Logout

Front-Channel Logout uses the User Agent to transmit logout requests from the OP to RPs. The OP can render each RP's logout URI inside an iframe; the RP receives the request and clears the corresponding session state.

The client registers `frontchannel_logout_uri`. If session-specific logout is required, the OP and RP can also exchange `iss` and `sid`.

### 14.1. How It Works

~~~mermaid
sequenceDiagram
    actor U as Browser
    participant OP as OpenID Provider
    participant RP1 as portal RP
    participant RP2 as orders RP

    U->>OP: Logout at OP
    OP->>U: Logout page containing logout URI iframes
    U->>RP1: GET /frontchannel-logout?iss=...&sid=...
    RP1->>RP1: Delete matching session
    U->>RP2: GET /frontchannel-logout?iss=...&sid=...
    RP2->>RP2: Delete matching session
    OP-->>U: Complete logout page
~~~

### 14.2. Limitations to Consider

Front-channel relies on the browser loading iframes and sending matching cookies. Cookie `SameSite`, third-party cookie restrictions, Content Security Policy, browser privacy settings, or closed tabs can interfere with receiving notifications.

Therefore, Front-Channel Logout can be helpful, yet must not be treated as a guarantee that all RP sessions are cleared under every condition.

### 14.3. Verifying Logout Information

If the RP receives `iss` and `sid`, it can match them against the stored session/ID Token for that session. Delete only the session belonging to the verified OP and user. Never build a logout endpoint relying solely on an unauthenticated user ID parameter.

## 15. Back-Channel Logout

Back-Channel Logout uses direct server-to-server communication. The OP sends an HTTP POST to the RP's registered `backchannel_logout_uri` attaching a Logout Token.

The Logout Token is a JWT with claims describing the logout action. The RP must verify the signature, issuer, audience, timestamps, and required claims per OIDC Back-Channel Logout 1.0 before terminating the session.

### 15.1. Logout Token and Claims

A Logout Token typically contains:

| Claim | Meaning |
|---|---|
| `iss` | Issuer of the OP |
| `aud` | Client ID/RP receiving the logout |
| `iat` | Issued-at timestamp |
| `jti` | Unique ID for replay detection |
| `events` | Must contain member `http://schemas.openid.net/event/backchannel-logout` with an empty object value |
| `sid` | Session ID at the OP, if logging out a single session |
| `sub` | End-User subject, if logging out all RP sessions of the subject |

The Logout Token must contain at least one of `sid` or `sub`, and must not contain a `nonce` claim. The RP must verify the signature using the trusted issuer's keys, `iss`, `aud`, `iat`, `jti`, the `events` claim, and timing/replay rules per OIDC Back-Channel Logout 1.0.

A Logout Token is not an ID Token. It must be processed under its own validation rules; never pass it into a user-authentication code path as an ID Token.

### 15.2. How Do `sid` and `sub` Differ?

- `sid` present: the RP terminates sessions associated with that OP session ID.
- `sub` present without `sid`: the RP terminates sessions of the corresponding End-User within the client context.
- The RP must check `aud` to ensure the Logout Token is intended for the right client.
- `jti` should be tracked to prevent duplicate/replay processing over an appropriate window.

Do not treat `sid` as a global user identifier. It is an opaque session identifier within the issuer's context.

### 15.3. Back-Channel Logout Flow

~~~mermaid
sequenceDiagram
    participant OP as OpenID Provider
    participant RP as orders RP
    participant SR as OIDC Session Registry
    participant DB as Session Store

    OP->>RP: POST backchannel_logout_uri + Logout Token
    RP->>RP: Verify JWT signature, iss, aud, events, iat, jti
    RP->>SR: Look up sessions by sid or sub
    SR->>DB: Invalidate matching RP sessions
    DB-->>SR: Session invalidated
    RP-->>OP: HTTP success response
~~~

The Back-Channel Logout request uses a POST form with the `logout_token` parameter:

~~~http
POST /logout/connect/back-channel/order-oidc HTTP/1.1
Host: orders.example.com
Content-Type: application/x-www-form-urlencoded

logout_token=SIGNED_LOGOUT_TOKEN
~~~

The RP executes logout only after verifying the token and locating sessions matching `sid` or `sub`. Never accept a plain user ID value in place of a Logout Token.

Back-channel is more reliable than front-channel in server-side environments because it does not depend on the browser. Even so, the RP endpoint must be reachable from the OP, use TLS, enforce strict token validation, and handle requests idempotently.

## 16. Back-Channel Logout in Spring Security

Spring Security supports RPs receiving Back-Channel Logout. On the servlet stack, configure OIDC login and back-channel logout support.

Example using Spring Security's DSL:

~~~java
@Bean
OidcBackChannelLogoutHandler oidcBackChannelLogoutHandler() {
    return new OidcBackChannelLogoutHandler();
}

@Bean
SecurityFilterChain relyingPartySecurity(HttpSecurity http)
        throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .oidcLogout(oidc ->
            oidc.backChannel(Customizer.withDefaults())
        );

    return http.build();
}
~~~

When enabled, Spring Security registers an endpoint of the form:

~~~text
/logout/connect/back-channel/{registrationId}
~~~

`registrationId` is the RP's `ClientRegistration` identifier. The OP must register the corresponding URI as the back-channel logout URI.

### 16.1. HttpSessionEventPublisher

Spring Security recommends registering `HttpSessionEventPublisher` so invalidated sessions are removed from the registry:

~~~java
@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}
~~~

Without cleaning up the session registry, session mapping data can linger after sessions have been invalidated.

### 16.2. Cookie Name and Spring Session

The default mechanism uses the `JSESSIONID` cookie to link the session cookie with `OidcSessionInformation`. If the application uses Spring Session with the default `SESSION` cookie, configure the appropriate session cookie name for the handler.

Do not change the cookie name arbitrarily after deployment without testing session correlation.

### 16.3. Clusters and OidcSessionRegistry

By default, Spring Security may store OP-session-to-RP-session mappings in memory. In a multi-instance cluster, consider a custom `OidcSessionRegistry` storing mappings in a database or distributed store.

If the OP sends Back-Channel Logout to node A while the session mapping exists only on node B, logout may fail to find the session. The session registry must stay consistent with the session store and lifecycle events.

### 16.4. Spring Versions

The `oidcLogout` API and handlers depend on the Spring Security release line in use. Consult the docs for your exact version (6.x/7.x) before copying configurations; do not mix reactive APIs with servlet APIs.

## 17. Spring Authorization Server and Support Boundaries to Understand

In Spring Authorization Server 1.5.8, the OIDC Logout Endpoint is an implementation of **RP-Initiated Logout**. `OidcLogoutEndpointConfigurer` provides extension points for the request converter, authentication provider, response handler, and error handler. `OidcLogoutAuthenticationProvider` uses `SessionRegistry` to look up the End-User's session.

This provides the mechanism for the OP to process logout requests and terminate tracked sessions. It does not by itself prove that all other RPs have cleared their local sessions. To achieve multi-application logout, the OP must implement or integrate a notification mechanism supported and registered by the RPs.

### 17.1. Default Logout Endpoint Configuration

~~~java
OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
    OAuth2AuthorizationServerConfigurer.authorizationServer();

http
    .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
    .with(authorizationServerConfigurer, server ->
        server.oidc(oidc ->
            oidc.logoutEndpoint(Customizer.withDefaults())
        )
    );
~~~

This is the endpoint configuration portion; the application still needs the full Authorization Server beans and filter chains. When only default OIDC is enabled, the logout endpoint is configured with the framework defaults.

### 17.2. Customizing Validation

Spring Authorization Server has a default validator that checks `post_logout_redirect_uri`. If modifying the validator, preserve allowlist/registration validation and throw `OAuth2AuthenticationException` when requests are invalid.

Never allow arbitrary browser-supplied redirect URIs. Never skip client ID/ID Token hint checks just to "make logout always succeed."

### 17.3. Distinguishing the OP Session from the RP Session Registry

Spring Authorization Server's `SessionRegistry` tracks authenticated sessions at the OP. Spring Security OAuth2 Client's `OidcSessionRegistry` tracks the link between OP sessions and local sessions at the RP. These are two registries in two different roles; one cannot substitute for the other without explicit integration.

## 18. Token Revocation per RFC 7009

Token Revocation is a separate OAuth protocol enabling a client to inform the Authorization Server that an access token or refresh token is no longer needed.

RFC 7009 defines an HTTP POST request to the Revocation Endpoint using `application/x-www-form-urlencoded` and authenticating the client according to its registered OAuth mechanism.

Example:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: auth.example.com
Authorization: Basic BASE64_OF_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

token=REFRESH_TOKEN_VALUE&token_type_hint=refresh_token
~~~

`token_type_hint` can be `access_token` or `refresh_token`. This is only a lookup hint; if the token is not found under the hint, the AS must broaden its search across supported token types.

### 18.1. Revocation Response

Per RFC 7009, the AS returns HTTP 200 both when the token was revoked successfully and when the submitted token is invalid. This response avoids disclosing which tokens exist, reducing token enumeration.

The client must authenticate with the AS and may revoke only tokens belonging to that client per server validation.

### 18.2. Revocation Does Not Automatically Log Out the Browser

Revocation invalidates token/authorization state per AS policy. It does not automatically remove the OP's SSO cookie or RP session cookies.

For example, revoking `orders-web`'s refresh token:

- The OP can no longer issue new access tokens from that refresh token.
- `orders`'s local session may still remain.
- The browser may still hold an SSO session at the OP.
- `portal` and `reports` are not logged out automatically.
- The user may need to log in or authorize again when the app needs new tokens.

If the product requires both logout and revocation, execute both actions in the appropriate order and policy.

## 19. Revocation of JWT Access Tokens and Opaque Tokens

Revocation effectiveness depends on how Resource Servers validate access tokens.

| Access Token Type | How the RS Verifies | Effect of Revocation |
|---|---|---|
| Self-contained JWT | Verifies signature/claims locally | Offline RSs may continue accepting the JWT until expiration unless a denylist/event/status check exists |
| Opaque/reference | Calls introspection or checks central state | Sees inactive status once revocation is persisted and propagated |
| JWT + revocation list/event | Local validation combined with central state | Shortens window from revocation to denial, depending on propagation |

RFC 7009 specifies that the server invalidates the token and related tokens per policy. Yet for an already-issued JWT access token verified offline by an RS, the RS does not know the token was revoked without a state-update mechanism.

Therefore, if near-instant revocation is needed, consider opaque tokens + introspection, a denylist/shared status store, event propagation, or short access token TTLs. Each option trades off latency, availability, and consistency differently.

### 19.1. Revoking a Refresh Token Can Affect Related Access Tokens

RFC 7009 specifies that if the AS supports revoking access tokens, when revoking a refresh token the AS SHOULD revoke access tokens issued under the same grant. If the AS does not support revoking access tokens, already-issued JWTs can stay valid until expiration.

Do not promise users that "revoking a refresh token" immediately cuts off all API requests if Resource Servers validate JWTs offline.

## 20. Combining Local Logout, RP-Initiated Logout, and Revocation

A comprehensive logout flow may include:

1. RP receives a CSRF-protected POST logout.
2. RP preserves the ID Token hint and required token references before clearing Authentication.
3. RP clears its local session and cookies.
4. RP backend calls the Revocation Endpoint for refresh/access tokens per policy with valid credentials.
5. RP redirects the browser to the OP Logout Endpoint with the ID Token hint.
6. OP terminates the SSO session.
7. OP sends Front-Channel/Back-Channel notifications to registered RPs.
8. Receiving RPs validate notifications and delete matching sessions.
9. The initiating RP handles the post-logout callback and verifies `state`.

Ordering may differ by architecture. If a local logout handler clears Authentication first, save the necessary ID Token/authorized client in a secure transaction so the logout handler still has the data needed to build the OP request.

### 20.1. Do Not Let Revocation Failures Block Local Logout Indefinitely

Local logout must end the session at the RP even if the AS is temporarily unavailable. You can record pending revocations and retry in the backend per policy, but never keep the user authenticated solely because the revocation endpoint timed out.

If revocation fails, record the operational state clearly and rely on TTL/incident policies. Never log raw tokens in retry queues or audits.

### 20.2. Do Not Revoke Another Application's Tokens

A client should revoke only tokens issued to that client itself. Do not take tokens from `portal`, `orders`, or `reports` and attempt to revoke them from another client. Token ownership and client authentication must be enforced by the AS.

## 21. Cookies, Session Stores, and Secure Logout

Logout is effective when both server-side state and browser-side cookies are handled properly.

### 21.1. Clearing Server-Side Sessions

Invalidate `HttpSession` or delete the session record from the distributed session store. Deleting only the browser cookie while leaving the server session alive can create orphaned sessions and complicate auditing/cleanup.

### 21.2. Deleting Cookies with the Right Domain/Path

An RP can delete only cookies belonging to domains/paths it controls. `orders.example.com` cannot directly delete a host-only cookie of `auth.example.com` or cookies of `portal.example.com`.

Cookies must be cleared using Domain/Path attributes matching the original cookie. Session cookies should use `Secure`, `HttpOnly`, and a `SameSite` policy suited to the flow.

### 21.3. Session Fixation and Switching Accounts

After authenticating a new user, the RP needs session fixation protection per Spring Security. When logging out and logging in with another account, never reuse old state/sessions containing the previous user's identity or token cache.

### 21.4. CSRF and Logout Endpoints

Browser-cookie local logout should use POST with CSRF protection. The back-channel endpoint is a machine-to-machine protocol endpoint; exempt only that exact endpoint from CSRF per framework configuration and strictly validate the Logout Token per the standard.

Never disable CSRF application-wide just to make Back-Channel Logout work.

## 22. Testing Logout in a Multi-Application System

### 22.1. Local Logout and SSO Matrix

| Scenario | Expected Result |
|---|---|
| Local logout at RP A | Only session A is deleted |
| RP A logs out then logs in again while OP session remains | Can log back in without re-entering credentials |
| RP-Initiated Logout at RP A | OP processes the logout request and ends SSO session per policy |
| OP logout without RP notifications | Local sessions B/C may remain |
| OP logout with Back-Channel notifications | RPs receive and delete the exact specified sessions |
| User logs in again after OP logout | OP requires fresh authentication when no valid session remains |

### 22.2. Token Revocation Matrix

| Scenario | Expected Result |
|---|---|
| Revoke valid refresh token | AS marks token inactive |
| Revoke non-existent token | HTTP 200 per RFC 7009 |
| Revoke with invalid client credentials | AS rejects client authentication |
| Revoke token belonging to another client | AS rejects per ownership validation |
| Revoke refresh token with related access token | Cascade outcome per policy and RFC |
| JWT access token validated offline | May stay valid until `exp` without a status check |
| Opaque token introspected | RS receives inactive once revocation state propagates |
| AS returns 503 | Client assumes token may still exist and retries per `Retry-After`/policy |

### 22.3. Front-Channel and Back-Channel Matrix

- Browser blocks third-party cookies or iframes.
- Browser closes tab before receiving the Front-Channel request.
- RP is unreachable from the OP.
- Logout Token has an invalid signature.
- Logout Token has wrong issuer or audience.
- Logout Token lacks the `events` claim.
- Logout Token replayed with the same `jti`.
- Logout Token contains a non-existent `sid`.
- Logout Token contains `sub` with multiple RP sessions.
- RP runs multiple instances with a distributed session registry.
- Session cookie name differs from `JSESSIONID`.
- Notification for the same session delivered multiple times.

Expected outcome: the RP terminates only sessions matching verified issuer, client, and subject/session; repeated delivery must be idempotent.

## 23. Integration Testing with Spring Security and Spring Authorization Server

### 23.1. Testing Local Logout

Using MockMvc:

~~~java
mockMvc.perform(post("/logout")
        .with(csrf())
        .with(user("user-42")))
    .andExpect(status().is3xxRedirection());
~~~

Tests must verify that the session is no longer authenticated and cookie/session state is handled properly. The redirect target depends on `LogoutSuccessHandler`.

### 23.2. Testing RP-Initiated Logout

- Log in with an OIDC test provider.
- Send POST to the local logout endpoint with a CSRF token.
- Verify the local session was deleted.
- Verify redirect to `end_session_endpoint` retrieved from `ClientRegistration`/discovery.
- Verify `id_token_hint` and `post_logout_redirect_uri` are constructed accurately.
- Verify callback `state` is matched against the transaction.
- Verify unregistered redirect URIs are rejected at the OP.

### 23.3. Testing the OP's OIDC Logout Endpoint

With Spring Authorization Server:

- Enable the OIDC configurer.
- Log in an End-User and register the session in `SessionRegistry`.
- Send a logout request with a valid ID Token hint.
- Verify the provider finds the right session and executes logout.
- Test ID Token hints with wrong issuer/client.
- Test unregistered `post_logout_redirect_uri`.
- Test `client_id` mismatching the ID Token hint.
- Verify `SessionRegistry` is cleaned up when `HttpSession` is invalidated.

### 23.4. Testing RP Back-Channel Logout

- Log into the RP and persist the mapping between OP session ID and RP session ID.
- Send a Logout Token signed by a trusted test key.
- Verify right audience/issuer/`events`/`iat`/`jti`.
- Send a token with `sid` and verify only the matching session is deleted.
- Send a token with `sub` and verify sessions of that subject in the client context are deleted.
- Send a token with an invalid signature or replay and verify rejection.
- Run tests across multiple nodes to check registry consistency.

## 24. Common Implementation Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Thinking local logout deletes the SSO session | User returns to app and gets logged back in automatically | Use RP-Initiated Logout to end the OP session |
| Thinking OP logout deletes every RP's session automatically | Other apps keep active sessions | Enable Front/Back-Channel or a notification mechanism |
| Thinking token revocation deletes browser sessions | User still appears logged into RP/OP | Combine with session logout |
| Thinking revoking a refresh token cuts off JWT access tokens immediately | APIs still accept unexpired JWTs | Use introspection/denylist/events or short TTLs |
| Sending an access token as `id_token_hint` | OP cannot properly identify the session | Send the ID Token issued by the OP to the RP |
| Not registering `post_logout_redirect_uri` | OP rejects callback or skips redirect | Register exact URI |
| Accepting redirect URIs from the browser | Open redirect/phishing | Per-client allowlist |
| Using static `state` | Logout callback injection/CSRF | Generate random per-transaction `state` |
| Missing proper `SessionRegistry` | OP cannot locate the session | Verify session registration and event publisher |
| Using in-memory `SessionRegistry` in a cluster | Logout becomes node-dependent | Use a shared registry/session store |
| Back-channel endpoint not validating Logout Token | Attackers can force-log-out users | Verify signature, `iss`, `aud`, `events`, `iat`, `jti` |
| Not handling `sid`/`sub` properly | Logs out too many or too few sessions | Apply exact spec semantics |
| Relying solely on Front-channel | Logout notifications can be blocked by browsers | Consider Back-Channel |
| Deleting cookie without invalidating server session | Orphaned sessions or lingering server validity | Clear the session store as well |
| Disabling CSRF application-wide for logout | Expands CSRF attack surface | Keep POST local logout and configure protocol endpoints precisely |
| Logging ID Tokens/refresh tokens/Logout Tokens | Leaks credentials or PII | Redact tokens, restrict audits |
| Not testing callbacks and multiple apps | Logout behavior diverges from product expectations | Test multi-RP end-to-end |

## 25. Observability and Runbook

### 25.1. Metrics to Track

- Local logout successes/failures per RP.
- RP-Initiated Logout requests and OP responses.
- OIDC logout errors by client/error code.
- `SessionRegistry` active sessions and cleanup failures.
- Front-Channel/Back-Channel notification successes, latency, and retries.
- Logout Token validation failures: signature, issuer, audience, event, replay.
- Token revocation successes/failures, 503s, and `Retry-After`.
- Time elapsed from OP logout until RP session invalidation.
- Access tokens still accepted by Resource Servers after revocation.
- Post-logout session counts and token counts per policy.

Never put raw tokens, ID Tokens, Logout Tokens, refresh tokens, or PII into metric labels.

### 25.2. Audit Events

Events you can record:

~~~text
RP_LOCAL_LOGOUT_COMPLETED
RP_INITIATED_LOGOUT_REQUESTED
OP_SSO_SESSION_TERMINATED
OIDC_FRONTCHANNEL_LOGOUT_SENT
OIDC_BACKCHANNEL_LOGOUT_SENT
RP_BACKCHANNEL_LOGOUT_RECEIVED
RP_SESSION_INVALIDATED
OAUTH_TOKEN_REVOCATION_REQUESTED
OAUTH_TOKEN_REVOCATION_COMPLETED
OAUTH_TOKEN_REVOCATION_FAILED
~~~

Audits should include correlation ID, client ID, issuer, pseudonymized session identifier, token fingerprint when needed, outcome, and timestamp. Never log raw credentials.

### 25.3. Runbook When a User Remains Logged In After Logout

1. Determine whether the user triggered local logout or RP-Initiated Logout.
2. Check whether the RP's local `HttpSession` and session cookie were deleted.
3. Check whether the OP SSO cookie/session still exists.
4. Check whether the browser was redirected to `end_session_endpoint`.
5. Check whether the OP received `id_token_hint` and found the session in `SessionRegistry`.
6. Check whether the OP sent notifications to other RPs.
7. Check the Back-Channel Logout Token and RP session registry.
8. Check whether access/refresh tokens remain active and whether Resource Servers validate via JWT or introspection.
9. Check session stores, caches, clocks, proxies, and cookie `SameSite`/Domain/Path settings.
10. Cross-check against product requirements: sign out one app, SSO, or all apps.

Never remediate by wiping all tokens of all clients without verifying scope and ownership first.

## 26. Production Checklist

- [ ] Local RP sessions, OP SSO sessions, and OAuth token state are clearly delineated.
- [ ] Local logout uses POST and keeps CSRF protection.
- [ ] RP local logout invalidates server sessions and deletes cookies with the right domain/path.
- [ ] RP-Initiated Logout uses `end_session_endpoint` from trusted OP Discovery.
- [ ] `id_token_hint` is the ID Token issued by the OP for the right RP.
- [ ] `post_logout_redirect_uri` is pre-registered and validated per client.
- [ ] `state` is generated per transaction and verified on callback.
- [ ] Spring Authorization Server enables the OIDC Logout Endpoint for your version.
- [ ] `SessionRegistry` tracks OP sessions and cleans up via session lifecycle events.
- [ ] Session registry behaves consistently when the OP runs multiple instances.
- [ ] Decision is documented on whether Front-Channel/Back-Channel notifications are required.
- [ ] RP Back-Channel Logout endpoint verifies signature, `iss`, `aud`, `events`, `iat`, and `jti`.
- [ ] `sid`/`sub` are handled with the right session scope.
- [ ] RP session registry is shared if the RP runs multiple instances.
- [ ] Token revocation uses RFC 7009 with client authentication.
- [ ] No assumption is made that offline JWTs become invalid immediately after revocation.
- [ ] Refresh tokens, access tokens, and session cookies each have explicit policies.
- [ ] Revocation failures do not keep local user sessions alive indefinitely.
- [ ] Raw ID Tokens, refresh tokens, access tokens, or Logout Tokens are never logged.
- [ ] Integration tests cover local logout, RP-Initiated logout, notifications, and token revocation.
- [ ] Metrics, audits, and a runbook exist for logout propagation.

### Core Knowledge

**Local logout** ends the session of a single application. **RP-Initiated Logout** asks the OpenID Provider to terminate the End-User's SSO session. For other applications to delete their local sessions as well, the OP and RPs must coordinate via Session Management, Front-Channel Logout, or Back-Channel Logout.

**Token Revocation per RFC 7009** is a separate operation to invalidate access/refresh tokens according to Authorization Server policy. It does not automatically delete browser sessions. For JWT access tokens verified offline by Resource Servers, tokens can continue to be accepted until expiration unless additional status checks exist.

In Spring Security, use `logout()` for local logout and `OidcClientInitiatedLogoutSuccessHandler` to initiate RP-Initiated Logout. In Spring Authorization Server, enable the OIDC Logout Endpoint and manage `SessionRegistry`. When multi-application logout is required, implement notifications and session correlation explicitly; test both scenarios where browsers block Front-Channel and where Back-Channel runs across multiple instances.

## References

- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html)
- [OpenID Connect Session Management 1.0](https://openid.net/specs/openid-connect-session-1_0.html)
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html)
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [Spring Security — OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html)
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Security — Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
