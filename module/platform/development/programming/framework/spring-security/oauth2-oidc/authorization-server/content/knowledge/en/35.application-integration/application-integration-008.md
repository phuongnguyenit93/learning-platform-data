# Implementing SSO Across Multiple Clients Sharing an Authorization Server

> **Chapter: Application Integration.** This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, guiding how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in Spring Boot. The focus is implementing Single Sign-On (SSO) across multiple OAuth2/OIDC client applications trusting a single Authorization Server, managing browser sessions, handling consent, and scoping logout properly.

## 1. SSO in a Multi-Client Architecture

Suppose an organization has multiple applications:

| Application | Client ID | Target Users |
|---|---|---|
| Employee Portal | employee-portal | Employees |
| Orders System | orders-web | Sales staff |
| Billing Management | billing-web | Accountants |
| Admin Dashboard | admin-console | Administrators |

All applications are registered with the same Authorization Server:

~~~text
https://login.example.vn
~~~

When a user signs in to the Employee Portal, the Authorization Server creates a login session on its domain. Next, the user opens the Orders System. That application still sends an authorization request to the Authorization Server, but the browser attaches the login.example.vn session cookie. The Authorization Server recognizes the existing login session and can proceed with the flow without prompting the user to re-enter their password.

This is SSO based on the **login session at the Authorization Server**:

- Each client has its own client_id, redirect URI, scopes, client authentication method, and policy.
- The user authenticates at the Authorization Server once per browser session.
- Subsequent authorization requests from other clients can reuse that login session.
- Each client still receives its own authorization code and its own tokens.
- Consent and access permissions are still evaluated per client, principal, scope, and policy.

SSO is not sharing access tokens across applications. It enables reusing the user's authentication state at the Authorization Server.

SSO in this lesson refers to browser-based user SSO. The client_credentials flow is for workload/service-to-service communication without an interactive user and does not rely on a browser session; two services sharing an Authorization Server does not by itself create user SSO.

## 2. Distinguishing Session and Credential Types

This architecture involves multiple independent states:

| Component | Managed By | Scope |
|---|---|---|
| Authorization Server browser session | Spring Security at the Authorization Server | Recognizes the user logged in at the OP |
| Client A application session | Client A | Holds local login state in application A |
| Client B application session | Client B | Holds local login state in application B |
| Authorization code | Authorization Server | Single authorization transaction, single-use |
| Access token | Authorization Server | API access permissions by scope/audience/lifetime |
| ID Token | OpenID Provider | Proof of authentication for the OIDC client |
| Refresh token (if policy allows) | Authorization Server | Obtains new access tokens per client policy |

One browser session at the Authorization Server can serve multiple clients. However, a local session at Client A does not automatically create a local session at Client B. Client B must still complete its callback and establish its own session upon receiving the authorization result.

Nor does Client A's access token become Client B's token. Each client must use tokens issued for its own flow, and Resource Servers must validate the corresponding issuer, audience, scope, expiry, and policies.

## 3. SSO Flow When a User Moves from Client A to Client B

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User Browser
    participant A as Client A
    participant B as Client B
    participant AS as Shared Authorization Server
    participant API as Resource Server

    U->>A: Open Employee Portal
    A->>U: Redirect to AS /authorize (client A)
    U->>AS: Authorization Request A
    AS->>AS: No authenticated session yet
    AS-->>U: Display login page
    U->>AS: Sign in successfully
    AS->>AS: Persist SecurityContext in HTTP session
    AS-->>U: Redirect callback A with authorization code
    U->>A: Callback A
    A->>AS: Token Request A
    AS-->>A: Tokens for client A
    A->>U: Create local session A

    U->>B: Open Orders System
    B->>U: Redirect to AS /authorize (client B)
    U->>AS: Authorization Request B + AS session cookie
    AS->>AS: Restore existing SecurityContext
    AS->>AS: Validate client B, redirect, scope and consent
    AS-->>U: Redirect callback B with authorization code
    U->>B: Callback B
    B->>AS: Token Request B
    AS-->>B: Tokens for client B
    B->>U: Create local session B
    B->>API: Call API with access token B
    API-->>B: Resource response
~~~

What creates SSO happens on the second authorization request: the browser still holds the Authorization Server's session cookie. The Authorization Server does not need to re-verify the password if the session remains valid and the request does not require re-authentication.

### 3.1. Conditions for SSO to Work

- Clients must use the same issuer/Authorization Server sharing a browser session.
- The browser must send the session cookie to the Authorization Server's domain.
- Requests must hit the same session system or a session store shared across instances.
- SecurityContext must be persisted and restored across HTTP requests.
- The session must not be expired or revoked, and the user must not be disabled.
- The authorization request's authentication policy must not force re-login.

If each client uses an Authorization Server on a different domain, one domain's session cookie will not be sent to the other domain. In that case, a shared IdP or federation layer is needed so the Authorization Servers can rely on a common SSO system.

If a single host serves multiple issuers by tenant path, a host-only cookie may be sent by the browser to every path on that host. That does not mean Tenant A's user session or authorization is allowed in Tenant B. Tenant/issuer context and account membership must be verified in every authorization transaction; the session cookie only proves the browser holds a session with the host.

## 4. Registering Each Client Separately

SSO does not eliminate the requirement to register each application individually. For example, two server-side web clients can use confidential client authentication:

~~~java
import java.time.Duration;
import java.util.UUID;

import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

RegisteredClient employeePortal = RegisteredClient
        .withId(UUID.randomUUID().toString())
        .clientId("employee-portal")
        .clientName("Employee Portal")
        .clientSecret(passwordEncoder.encode(employeePortalSecret))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://portal.example.vn/login/oauth2/code/internal")
        .postLogoutRedirectUri("https://portal.example.vn/logout/callback")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .scope("employee.read")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
        .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(10))
                .build())
        .build();

RegisteredClient ordersWeb = RegisteredClient
        .withId(UUID.randomUUID().toString())
        .clientId("orders-web")
        .clientName("Orders Web")
        .clientSecret(passwordEncoder.encode(ordersWebSecret))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://orders.example.vn/login/oauth2/code/internal")
        .postLogoutRedirectUri("https://orders.example.vn/logout/callback")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
        .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(10))
                .build())
        .build();
~~~

This example shows two server-side applications capable of keeping secrets. If a client is an SPA or native app, register it as a public client with the appropriate authentication method and mandatory PKCE; never embed a client secret in frontend/mobile binaries.

Attributes that must differ per application:

- client_id and client authentication credentials.
- Redirect URIs and post-logout redirect URIs.
- Allowed grant types, scopes, and token settings.
- Consent policies and allowed claims/audiences.

Do not share one client_id across multiple applications just to achieve SSO. Separating registrations allows per-application revocation, auditing, scope restriction, and incident response.

### 4.1. Persisting Registrations Durably

RegisteredClientRepository must persist registrations reliably across restarts. Development can use InMemoryRegisteredClientRepository; production should use JDBC or an appropriate persistence implementation.

Every redirect URI must be registered accurately. postLogoutRedirectUri must also belong to the client's registration so the Authorization Server can verify it before redirecting after logout.

## 5. Configuring OAuth2/OIDC Login in Each Client

Each Spring Security OAuth2 Client application registers with the same issuer while maintaining its own client-id, secret, and redirect URI.

Example configuration at Client A:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          internal:
            provider: company-as
            client-id: employee-portal
            client-secret: ${EMPLOYEE_PORTAL_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - employee.read
        provider:
          company-as:
            issuer-uri: https://login.example.vn
~~~

Client B has a similar registration using the client-id, secret, redirect URI, and scopes of orders-web.

When a user does not yet have a local session at Client B, Spring Security initiates OAuth2 Login. The browser is redirected to the Authorization Server. If the AS session is still valid, the user can return to Client B without re-entering credentials.

### 5.1. Do Not Share ClientRegistration or AuthorizedClient Across Applications

ClientRegistration is OAuth client configuration. OAuth2AuthorizedClient is bound to a registration ID, principal, and the tokens issued for that client. Never copy Client A's authorized client to Client B.

If two applications share the same database to store authorized clients, keys and access policies must still separate by application/registration/principal. Never allow application A to read application B's refresh tokens.

## 6. Configuring Sessions and SecurityContext on the Authorization Server

By default, Spring Security persists SecurityContext into the HTTP session to restore Authentication on subsequent requests. This is the foundational mechanism for browser-based SSO.

The Authorization Server protocol endpoints and application login may reside in separate SecurityFilterChain beans. These chains must use an appropriate session-based security context; do not configure the Authorization Server browser flow as stateless if you intend to preserve SSO.

Condensed configuration example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;
import org.springframework.security.config.http.SessionCreationPolicy;

@Bean
@Order(1)
SecurityFilterChain authorizationServerChain(HttpSecurity http) throws Exception {
    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                    server.oidc(Customizer.withDefaults()))
            .authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated())
            .exceptionHandling(exceptions ->
                    exceptions.defaultAuthenticationEntryPointFor(
                            new LoginUrlAuthenticationEntryPoint("/login"),
                            new MediaTypeRequestMatcher(MediaType.TEXT_HTML)))
            .sessionManagement(session ->
                    session.sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED));

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain loginAndApplicationChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(authorize ->
                    authorize
                            .requestMatchers("/login", "/assets/**").permitAll()
                            .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .sessionManagement(session ->
                    session.sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
                            .sessionFixation(fixation -> fixation.changeSessionId()));

    return http.build();
}
~~~

This example illustrates filter chain structure. The application must also supply the other required Authorization Server beans and policies such as RegisteredClientRepository, authorization service, consent service, JWKSource, and user authentication.

Key takeaways:

- IF_REQUIRED allows creating a session when the browser login/authorization flow requires one.
- Do not set SessionCreationPolicy.STATELESS on the browser authorization flow if SSO via HTTP sessions is expected.
- Spring Security protects against session fixation by changing the session ID upon successful authentication.
- If a controller/filter constructs an Authentication manually, persist SecurityContext via SecurityContextRepository; never simply set SecurityContextHolder and assume the next request will automatically receive the session.

## 7. Session Cookies and the Authorization Server Domain

Clients do not need to read the Authorization Server's session cookie. When the browser redirects to login.example.vn, the browser automatically sends cookies belonging to that domain. The cookie should remain scoped to the Authorization Server.

Spring Boot example:

~~~yaml
server:
  servlet:
    session:
      cookie:
        name: __Host-ASSESSION
        path: /
        http-only: true
        secure: true
        same-site: lax
~~~

With the __Host- cookie prefix, HTTPS, Path=/, and no Domain attribute are required. This is an ideal choice so the host-only cookie is sent strictly to login.example.vn.

There is no need to set Domain=.example.vn just because portal and orders live on different subdomains. The browser does not need to send the AS cookie to clients; clients simply redirect the browser to the AS so the cookie is sent to the right host.

### 7.1. SameSite and Redirects

SameSite=Lax generally suits authorization code flows using top-level browser navigation and GET callbacks. If implementing response_mode=form_post, iframes, or another cross-site POST flow, test actual cookie behavior; you may need to adjust SameSite as required while maintaining CSRF/state validation and Secure.

Do not switch to SameSite=None by default. None cookies require Secure and broaden cookie transmission in cross-site contexts.

### 7.2. SSO Across Multiple Browser Profiles

SSO reuses sessions only within the browser context holding the corresponding cookie:

- Tabs within the same browser profile normally share a cookie jar.
- Incognito/private windows normally have a separate cookie jar.
- Different browsers have separate cookie jars.
- Clearing cookies or expiring the session requires re-authentication.
- Native apps can use the system browser and share SSO depending on the platform; embedded WebViews typically isolate cookies/sessions and should not be used as an OAuth login user-agent.

## 8. Session Store in Multi-Instance Deployments

In production, the Authorization Server typically runs multiple application instances. If the first request creates a session on node A and the next request lands on node B, node B must be able to restore the exact same session and SecurityContext.

| Model | How It Works | What Must Be Guaranteed |
|---|---|---|
| Sticky session | Load balancer prefers the same node | Node stays healthy and sessions survive failover |
| Shared session store | Multiple nodes use the same session repository | Session ID, SecurityContext, and expiry are shared |
| Distributed cache/session | Uses Redis or equivalent store | Serialization, TTL, eviction, and availability are configured properly |

With Spring Session, HTTP sessions can be stored in Redis or a database. Every node needs identical namespace/cookie configuration, compatible session serializers, and aligned clock policies.

If OIDC logout or concurrent session control uses SessionRegistry, verify how the registry is synchronized across nodes. An in-memory SessionRegistry local to each node is insufficient for node A to see sessions created on node B. Use event publishers and shared/distributed session tracking matching your deployment.

Never write session IDs into logs or metric labels. Never use a session ID as a user ID or public correlation ID.

## 9. Consent Is Still Evaluated per Client

SSO only enables the Authorization Server to recognize that the user is already signed in. It does not mean the user has approved every permission for every application.

Example:

- Client A requests openid profile employee.read.
- Client B requests openid profile orders.read orders.write.

The user may have consented to employee.read for Client A without ever consenting to orders.write for Client B. The Authorization Server must still enforce the consent policy for Client B.

Spring Authorization Server stores consent via OAuth2AuthorizationConsentService, tied to RegisteredClient and principal. Consent for one client does not automatically become consent for another client. In multi-tenant or multi-issuer setups, the consent store must also be isolated by tenant/issuer.

### 9.1. Consent and Silent Authorization

If a client already has matching consent, the AS can proceed with authorization without showing the consent page, depending on policy. If new or sensitive scopes appear, prompt for additional consent or re-consent.

Never disable consent globally simply to make SSO look seamless. SSO eliminates repetitive logins; consent remains an explicit decision about access permissions.

## 10. Controlling Re-Authentication with OIDC Parameters

OIDC Authorization Requests support parameters affecting user interaction:

| Parameter | Meaning |
|---|---|
| prompt=none | Requests no UI be displayed; return an appropriate error if interaction is required |
| prompt=login | Forces re-authentication rather than relying solely on the current session |
| prompt=consent | Forces displaying consent |
| prompt=select_account | Prompts the user to select an account |
| max_age | Limits maximum age of the last authentication; re-authenticate if exceeded |

Example client requesting silent authentication:

~~~text
GET /oauth2/authorize
    ?response_type=code
    &client_id=employee-portal
    &redirect_uri=https%3A%2F%2Fportal.example.vn%2Flogin%2Foauth2%2Fcode%2Finternal
    &scope=openid%20profile
    &prompt=none
    &state=STATE_VALUE
    &nonce=NONCE_VALUE
~~~

If no suitable login session exists, or policy requires consent/MFA/re-authentication, the Authorization Server must never silently show a login page when prompt=none; it must return an appropriate OIDC error such as login_required, consent_required, or interaction_required.

prompt=login requires re-authentication. If the Authorization Server merely sees an existing session and proceeds without re-authenticating, the server fails to honor the request semantics. With max_age, the OP must check the authentication timestamp and emit auth_time when required by OIDC.

The prompt values are part of the OIDC contract. Verify the behavior of your Spring Authorization Server version; if the provider does not enforce all semantics out of the box, add authorization request validation/interaction policies and integration tests. Never assume merely sending a parameter makes the framework enforce all semantics automatically.

## 11. Logout: Local Logout vs. SSO Logout

Logout has multiple distinct scopes:

| Action | What Is Terminated | What Is Not Automatically Terminated |
|---|---|---|
| Logout at Client A | A's local session | AS session, Client B session, and issued tokens |
| Logout at Authorization Server | Browser SSO session at AS | Local sessions across all clients and all access tokens |
| RP-Initiated Logout | Client asks OP to end the user's session at AS | Does not automatically guarantee all other RPs cleared their sessions |
| Back-channel/front-channel logout | Notifies clients/RPs per implemented protocol | Does not automatically revoke all tokens without corresponding policy |
| Token revocation | Tokens are revoked per token store/introspection policy | Does not automatically clear browser sessions |

If a user only logs out at Client A, the next time they open Client B the browser may still hold the AS session and sign them in without asking for a password. That is normal SSO behavior.

To log out of SSO, Client A must initiate OIDC RP-Initiated Logout to the Authorization Server's end-session endpoint. The AS verifies the request, id_token_hint, client, and post_logout_redirect_uri and then terminates the corresponding session per configuration.

### 11.1. Enabling OIDC Logout on the Authorization Server

Spring Authorization Server configures OIDC via:

~~~java
OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

http.securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server ->
                server.oidc(Customizer.withDefaults()));
~~~

The OIDC configurer enables OIDC endpoints, including the RP-Initiated Logout endpoint. OidcLogoutAuthenticationProvider uses SessionRegistry to locate the End-User's session. Verify discovery metadata so clients obtain the exact end_session_endpoint.

Client registrations must declare allowed post-logout redirect URIs:

~~~java
RegisteredClient employeePortal = RegisteredClient
        .withId("registered-client-employee-portal")
        .clientId("employee-portal")
        // Other client settings and grant types
        .postLogoutRedirectUri("https://portal.example.vn/logout/callback")
        .build();
~~~

Allow only registered URIs. Never redirect to an arbitrary URL supplied by the client.

### 11.2. Client Initiating RP-Initiated Logout with Spring Security

With Spring Security OAuth2 Client, you can use OidcClientInitiatedLogoutSuccessHandler:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.authentication.logout.LogoutSuccessHandler;

@Bean
LogoutSuccessHandler oidcLogoutSuccessHandler(
        ClientRegistrationRepository registrations) {

    OidcClientInitiatedLogoutSuccessHandler handler =
            new OidcClientInitiatedLogoutSuccessHandler(registrations);

    handler.setPostLogoutRedirectUri("{baseUrl}/logout/callback");
    return handler;
}
~~~

Attach the handler to the client's filter chain:

~~~java
http.logout(logout ->
        logout.logoutSuccessHandler(oidcLogoutSuccessHandler));
~~~

The client needs issuer discovery to obtain end_session_endpoint, sends the ID Token hint as supported by the handler/provider, and uses a post-logout redirect URI registered at the OP.

### 11.3. Logging Out of All Applications and Tokens

Ending the AS session only prevents subsequent authorization requests from reusing the browser SSO session. Applications may still hold local sessions until they log out locally or receive a logout notification.

If global sign-out is required, also design:

- RP-Initiated Logout from the initiating application to the OP.
- OIDC Back-Channel Logout or Front-Channel Logout if supported by OP/RPs.
- Tracking sid/sub and session mappings per the OIDC logout contract.
- Revoking refresh tokens/authorizations when policy demands.
- Resource Servers using introspection, denylists, or short access token TTLs if revocation must take effect quickly.
- Signing out all devices/browser sessions under a controlled workflow.

Never assume already-issued access tokens become invalid solely because the browser session at the Authorization Server was cleared. For offline-verified JWT access tokens, Resource Servers may keep accepting tokens until expiration unless an additional revocation mechanism is in place.

## 12. SSO Security and Operations

### 12.1. Protecting Sessions

- Use HTTPS across the entire login and callback flow.
- Session cookies must use Secure, HttpOnly, appropriate SameSite, and host-only where possible.
- Keep session fixation protection enabled.
- Set idle timeouts and absolute session lifetimes aligned with risk.
- Maintain a re-authentication policy for sensitive operations.
- Do not set a broad cookie Domain solely to achieve SSO across subdomains.
- Never place session IDs in URLs, logs, analytics, or client-side storage.

### 12.2. Protecting Authorization Requests

- Each client has exact-match redirect URIs and its own registration.
- Use Authorization Code Flow; require PKCE for public clients and consider PKCE for confidential clients.
- Validate state, nonce, issuer, audience, and callback transactions.
- Never skip consent or MFA just because the user already holds an AS session.
- Never accept unregistered post_logout_redirect_uri values.
- Enforce prompt, max_age, and re-authentication policies per OIDC.

### 12.3. Session and Account Lifecycle

- When a user is disabled, block new authorizations and handle active sessions per SLA.
- When passwords/MFA credentials are reset due to suspected compromise, consider terminating existing sessions.
- Monitor concurrent sessions and signed-in devices.
- Maintain a workflow to revoke refresh tokens/authorizations when an account is locked or a user leaves the organization.
- Synchronize the session registry across nodes in clustered deployments.
- Audit login, re-authentication, consent, logout, and session termination; never log credentials or tokens.

## 13. Multi-Client SSO Test Matrix

| # | Scenario | Expected Result |
|---|---|---|
| 1 | Client A logs in for the first time | AS renders login, authenticates user, and creates AS session |
| 2 | Client A exchanges authorization code | A receives tokens for registration A |
| 3 | Client B opens in the same browser profile | AS receives session cookie and skips password prompt if policy allows |
| 4 | Client B uses its own client ID | Authorization request is processed under registration B |
| 5 | Client B uses Client A's redirect URI | AS rejects the redirect URI |
| 6 | Client B requests its own scopes | Scopes are validated against registration B |
| 7 | Client A has consented, Client B has not | Client B's consent is still evaluated separately |
| 8 | Client B requests a new scope | Prompts for additional consent or enforces corresponding policy |
| 9 | User opens a different browser profile | Does not reuse the first profile's session cookie |
| 10 | User uses incognito | Does not inherit the regular browser's AS session |
| 11 | AS session idle timeout expires | Next authorization request forces re-login |
| 12 | AS session absolute lifetime expires | Forces re-authentication per policy |
| 13 | Client A local logout | Session A ends; AS session may persist |
| 14 | Open Client B after local logout at A | B can SSO if AS session persists |
| 15 | Client A RP-Initiated Logout | OP processes end-session request and terminates AS session properly |
| 16 | Unregistered post_logout_redirect_uri | OP rejects redirect |
| 17 | Client B after global OP logout | B cannot reuse the terminated AS session |
| 18 | Client B local session remains after OP logout | Behavior follows configured front/back-channel logout policy |
| 19 | Old JWT access token after AS logout | Remains valid until expiry unless a revocation mechanism exists |
| 20 | Revoked refresh token | Token endpoint rejects refresh per policy |
| 21 | prompt=none with valid AS session | Displays no UI when no interaction is needed |
| 22 | prompt=none when not logged in | Returns login_required without showing login UI |
| 23 | prompt=none when consent is required | Returns appropriate error without showing consent UI |
| 24 | prompt=login while session is active | Forces re-authentication per policy |
| 25 | prompt=consent | Prompts for consent per OIDC behavior |
| 26 | max_age exceeded | Re-authenticates and supplies auth_time when needed |
| 27 | Two clients log in concurrently | Authorization transactions do not overwrite each other's state |
| 28 | Two AS instances handle the same browser session | Both restore SecurityContext from the shared session |
| 29 | Node holding session shuts down | Another node continues serving if session store supports failover |
| 30 | SessionRegistry kept only in per-node RAM | Test catches unsynchronized logout/session tracking |
| 31 | Cookie Domain/path modified | Browser behavior verified; cookie never leaks to unintended hosts |
| 32 | SameSite=Lax with top-level GET redirect | Cookie is sent per expected browser behavior |
| 33 | response_mode=form_post | Cookie/SameSite and CSRF behavior tested separately |
| 34 | User disabled while AS session remains | New authorizations rejected per account policy |
| 35 | Client A attempts to use Client B's token | Resource Server/client policy rejects wrong audience/scope |
| 36 | Logout redirect URL contains arbitrary host | No redirect outside allowlist |
| 37 | Debug logging enabled during authorization flow | No session IDs, authorization codes, or tokens logged |
| 38 | Multiple apps share issuer with different client IDs | Each app receives tokens/consent matching its registration |

### 13.1. End-to-End Integration Test

An SSO test should execute within the same browser context:

1. Open Client A and complete login at the Authorization Server.
2. Verify the browser receives the AS session cookie with proper Secure/HttpOnly/SameSite attributes.
3. Exchange the code and establish a local session at Client A.
4. Open Client B in the same browser profile.
5. Confirm the browser sends the cookie to the same AS host and the AS does not prompt for a password again.
6. Verify Client B is still validated against its own client registration, redirect URI, scopes, and consent.
7. Exchange the code at the token endpoint using Client B's credentials.
8. Verify Token A and Token B are not swapped.
9. Perform local logout at A, then open B to verify SSO behavior.
10. Execute RP-Initiated Logout and verify the AS session terminates.
11. Verify Client B's local session and old access tokens behave according to published logout/revocation policies.
12. Repeat the test when requests are routed across different AS nodes.

## 14. Troubleshooting and Production Checklist

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Client B always prompts for login even after Client A logged in | AS session not persisted or browser not sending cookie | Check SecurityContextRepository and cookie host/path/SameSite |
| Login A succeeds but request B hitting another node prompts for login | Session stored only locally on one node | Use a shared session store or sticky sessions with failover |
| Client B receives another client's token | Shared client registration or improperly shared tokens/authorized clients | Separate RegisteredClients and validate audience |
| Client B lacks a local session despite AS SSO success | Callback or local authentication persistence failed | Check OAuth2 Login callback and B's session |
| Client A logs out yet B stays signed in | Only Client A local logout occurred | Use RP-Initiated Logout to terminate the AS session |
| AS logs out yet access tokens still call APIs | JWT access token still valid and API validates offline | Use short TTLs or revocation/introspection policies |
| prompt=none renders a login page | Provider not handling silent requests per contract | Return OIDC error instead of interactive UI |
| prompt=login still reuses the old session | Re-authentication not enforced | Add interaction policy and test it |
| Post-logout redirect is rejected | URI not present in RegisteredClient | Register the exact postLogoutRedirectUri |
| Logout cannot find session on another node | SessionRegistry not shared | Configure distributed session tracking |
| Cookie not sent on form_post | SameSite policy incompatible with cross-site POST | Review response mode, cookie settings, and CSRF |
| Incognito prompts for login again | Independent cookie jar | Expected browser behavior |

### 14.1. Production Checklist

- [ ] All clients use the shared issuer/Authorization Server.
- [ ] Each application has its own RegisteredClient, client ID, redirect URI, and credentials.
- [ ] Confidential web clients keep secrets server-side; public clients use PKCE without embedded secrets.
- [ ] Authorization Server uses session-based SecurityContext for browser logins.
- [ ] Browser authorization flow is never configured as STATELESS.
- [ ] Session fixation protection is enabled.
- [ ] Session cookies use Secure, HttpOnly, appropriate SameSite, and host-only scoping.
- [ ] Cookie Domain is not broadened to share SSO across clients.
- [ ] Session store is shared across AS nodes or has reliable failover.
- [ ] SessionRegistry/concurrent session tracking is synchronized if needed.
- [ ] Consent is evaluated per client and principal.
- [ ] Clear policies govern prompt, max_age, MFA, and re-authentication.
- [ ] RP-Initiated Logout is enabled when SSO logout is needed.
- [ ] Post-logout redirect URIs are registered and validated.
- [ ] Back-channel/front-channel logout is designed if other RPs' local sessions must terminate.
- [ ] Token revocation/expiry is decoupled from browser session logout.
- [ ] Account disablement/compromise workflows terminate sessions and revoke authorizations.
- [ ] Integration tests cover multiple clients, browser profiles, AS nodes, and logout paths.
- [ ] Audit logs omit session IDs, authorization codes, access tokens, refresh tokens, and ID Tokens.

**Self-Assessment Questions**

1. On what state does SSO across multiple clients sharing an Authorization Server rely?
2. Why does each client still need its own RegisteredClient even when sharing an issuer?
3. What is the difference between the AS browser session and each client's application session?
4. Why must Client A's access token not be used in place of Client B's token?
5. Where does Spring Security persist SecurityContext by default?
6. Why is SessionCreationPolicy.STATELESS unsuitable for browser-based SSO?
7. Does the Authorization Server's cookie need to be shared across client subdomains?
8. Why can a host-only cookie still support SSO across multiple clients?
9. When running multiple AS nodes, what is required to restore the same session?
10. Does consent for Client A automatically apply to Client B?
11. How must prompt=none be handled when the user has no active session?
12. How do prompt=login and max_age affect an existing session?
13. Does local logout at Client A automatically terminate the AS session?
14. How does RP-Initiated Logout differ from local logout?
15. Why does terminating the AS session not automatically revoke already-issued JWT access tokens?
16. When are Back-Channel Logout or Front-Channel Logout needed?
17. How do you test SSO across two clients and multiple AS instances?

## References

- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): OIDC endpoints, RP-Initiated Logout endpoint, and SessionRegistry.
- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClient, authorization, consent, and token model.
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): SecurityContextRepository, HTTP sessions, session fixation, session policies, and logout.
- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html): how SecurityContext is stored and restored across requests.
- [Spring Security — OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html): local logout, RP-Initiated Logout, and Back-Channel Logout on OAuth2/OIDC clients.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): Authorization Request, prompt, max_age, auth_time, and authentication semantics.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): end_session_endpoint, id_token_hint, post_logout_redirect_uri, and state.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): session, redirect, token, and client security considerations.
