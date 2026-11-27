# 1.7. Division of Responsibilities Between the Client Application and Identity Provider

In a Spring Boot application using **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, users are typically redirected to a centralized login system such as Keycloak, Microsoft Entra ID, Okta, or another OpenID Provider. After logging in, the user returns to the application and uses business features as normal.

"Logging in via an IdP" does not mean the identity provider is responsible for the application's entire security. **The identity provider authenticates users and issues protocol information/tokens; the client application must protect the login flow, establish its own session, determine what the user is allowed to do, and protect business data.** If the application calls a separate API, that API is also responsible for checking access permissions on the resource server side.

This lesson focuses on that boundary of responsibility: what can be delegated to the IdP, what Spring Security handles, and what the application development team still must design.

## 1. Roles in the System

Example: an order management system with a web UI written in Spring Boot, using a corporate IdP for login and calling an order management API.

| Component | Role | Example |
|---|---|---|
| **End User** | The end user wanting to use the application. | Employee logging in to view orders. |
| **User Agent** | Browser performing redirects between the application and the IdP. | Chrome, Firefox. |
| **OAuth 2.0 Client / OIDC Relying Party (RP)** | Application requesting login, receiving OIDC results, and managing business sessions. | Spring Boot application configured with `oauth2Login`. |
| **Identity Provider (IdP) / OpenID Provider (OP)** | Identity system authenticating users, managing login policies, and issuing ID Tokens. In OIDC, the OP also acts as the OAuth 2.0 Authorization Server. | Company SSO system. |
| **Resource Server** | API accepting Access Tokens, validating tokens, and controlling access to API resources. | Orders API accepting `Authorization: Bearer ...`. |
| **Spring Security** | Library implementing configured protocol flows and security mechanisms on the client and/or resource server side. | Filter chain, OIDC login, storing `SecurityContext`. |

Distinguish two terms that frequently appear together:

- **Authentication:** "Who is logging in?" The IdP is usually where password checks, MFA, passkeys, or other login methods are decided.
- **Authorization:** "What is that person allowed to do on a specific resource?" The IdP can provide groups and attributes to support authorization, but the application and API must decide permissions over their own features and data.

One application can play multiple roles simultaneously. For example, Spring Boot may both log users in with `oauth2Login` and expose REST endpoints accepting bearer tokens via `oauth2ResourceServer`. In that case, **two distinct security flows** must be designed; being an OIDC Client does not automatically turn every API inside the application into a secure Resource Server.

## 2. Responsibility Boundary: Who Owns Which Decision?

The following table uses the common scenario: a web application with a Spring Boot backend, logging in via the **Authorization Code Flow**, and calling APIs using an Access Token.

| Item | IdP / Authorization Server | Client Application and Related Components |
|---|---|---|
| **Identity and accounts** | Stores/syncs accounts, status, and identity attributes per organizational policy. | Decides whether to create user profiles in the application, links profiles with IdP identities, and handles users blocked at the business layer. |
| **Credential verification** | Verifies passwords, passkeys, federated identities, MFA, login policies. | Directs users through the right IdP login channel; does not need to collect IdP passwords. |
| **OAuth/OIDC client registration** | Stores `client_id`, client authentication method, allowed redirect URIs, scopes/policies. | Configures the right `client_id`, secret if any, issuer, scopes, and callback URI; manages secrets on the server side. |
| **Login request** | Provides the authorization endpoint and enforces IdP policies. | Initiates requests, selects scopes and redirect URI; binds requests to browser/session using `state`, `nonce`, and PKCE when applicable. |
| **Authorization Code** | Issues a short-lived code bound to client/redirect URI and code challenge if PKCE is used. | Receives callback, validates `state`, and exchanges the code at the token endpoint. |
| **ID Token** | Issues token carrying OIDC authentication info and publishes verification keys. | Validates token against issuer/client/login request before trusting identity. Spring Security assists with this when OIDC login is configured properly. |
| **Access Token** | Issues token for calling resources per scope/audience/policy. | Keeps token safe and sends it to the intended API. **Resource Server** is responsible for verifying the token and deciding API access. |
| **Refresh Token** | May issue, rotate, expire, or revoke according to policy. | Stores securely and uses it to request a new Access Token if issued and configured in the application. |
| **Profile/group information** | Provides claims, UserInfo, or user directory APIs depending on configuration. | Decides which claims to trust and maps them into the application's user/permission model. |
| **Business permissions** | Can manage centralized groups/roles or supporting policies. | Decides who can approve orders, view which department's data, or edit which records; checks at the point of action execution. |
| **Login session** | Manages the SSO session at the IdP. | Manages application sessions, cookies, expiration, CSRF, session fixation, and local logout. |
| **Logout** | Provides mechanisms to end the IdP session and/or revoke tokens if supported by the product. | Invalidates application session, clears login state; coordinates OIDC logout when needed and supported by the IdP. |
| **Logging and auditing** | Records authentication events, account changes, MFA within IdP scope. | Records business actions and authorization decisions; protects data, never writes raw tokens/secrets to logs. |

**Design principle:** Only delegate responsibility to the IdP for what the IdP actually knows and controls. The IdP may know an employee belongs to the `finance` group, but it usually cannot know which department order #123 belongs to or whether that employee is currently allowed to approve that order.

## 3. Where Does an OIDC Login Flow Take Place?

The diagram illustrates a Spring Boot application operating as a **server-side OIDC Client** with a backend API:

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant C as Spring Boot OIDC Client
    participant I as IdP / OpenID Provider
    participant A as Resource Server / API

    B->>C: Initiate /oauth2/authorization/company
    C-->>B: Redirect to authorization endpoint (state, nonce, scope, PKCE if used)
    B->>I: Authentication request /authorize
    I->>B: Login / MFA / consent (per policy)
    I-->>B: Redirect to callback with code and state
    B->>C: GET /login/oauth2/code/company?code=...&state=...
    C->>C: Validate state and saved request
    C->>I: Exchange authorization code at token endpoint
    I-->>C: ID Token + Access Token (+ Refresh Token if issued)
    C->>C: Validate ID Token; create Authentication and application session
    C-->>B: Session cookie; access permitted features
    C->>A: Call API with appropriate Bearer Access Token
    A->>A: Verify Access Token and resource access permissions
    A-->>C: Authorized API data returned
```

Key responsibility handoff points:

1. **Request initiation:** Spring Security builds the authorization request and records the state needed to verify the callback. The application must use registered issuer/endpoints, scopes, and redirect URIs, over HTTPS in production environments.
2. **User authenticates at IdP:** The IdP chooses how to verify identity, may require MFA, display consent, reject locked accounts, or leverage an existing SSO session. The application never sees the IdP password.
3. **IdP redirects back with code:** The code is neither an ID Token nor an Access Token. In the Authorization Code Flow, the backend client exchanges the code at the token endpoint over a server-side channel.
4. **Client validates results:** `state` detects callbacks that do not match an earlier login request. With OIDC, the client checks the ID Token and `nonce` if nonce was sent. With PKCE, the token endpoint confirms `code_verifier` matches the earlier request's `code_challenge`.
5. **Client creates its own session:** Spring Security creates an `Authentication` object, places it into `SecurityContext`, and uses the configured session storage mechanism. Being logged in at the IdP does not mean every feature in the application is authorized.
6. **API checks its own permissions:** When the client calls an API, the Resource Server must independently verify the Access Token intended for it and apply the API's authorization rules.

`state`, `nonce`, and **PKCE** protect different parts of the flow: `state` binds the callback to the original request; `nonce` binds the ID Token to the OIDC request session if used; PKCE helps prevent an intercepted authorization code from being exchanged for tokens by a party lacking `code_verifier`. They do not replace each other. For public clients, Authorization Code + PKCE is essential; for backend confidential clients, PKCE remains useful when supported and configured.

## 4. Distinguishing ID Token, Access Token, Refresh Token, and Session Cookies

This is where confusion most often occurs when dividing responsibilities.

| Type | Issued / Created By | Primary Consumer | Meaning and Trust Scope |
|---|---|---|---|
| **ID Token** | OpenID Provider | OIDC Client | Confirms the authentication event and user identity for **the client receiving the token**. Contains claims such as `iss`, `sub`, `aud`, `exp`, `iat`, and others when applicable. |
| **Access Token** | Authorization Server | Resource Server / API; forwarded by client when calling API | Grants access to APIs per granted scopes and conditions. May be a JWT or opaque token; the API verifies it with the appropriate mechanism. |
| **Refresh Token** | Authorization Server, if permitted | Eligible client issued the token | Requests a new Access Token without repeating the full interactive login step; subject to expiration, rotation, and revocation policies. |
| **Application session cookie** | Spring Boot application or session infrastructure | Browser and application backend | Maintains the link to the local login session, e.g., `JSESSIONID`; not an OIDC token issued by the IdP. |
| **SSO session cookie** | IdP | Browser and IdP | Allows the IdP to recognize the user on subsequent redirects; does not grant access to application data by itself. |

### 4.1. Under What Conditions Should the Client Trust an ID Token?

An ID Token does not become trustworthy merely because it is a JWT or contains a valid name/email. During OIDC login, the client must verify appropriate constraints, including:

- **Signature and keys:** valid signature against keys published by the trusted issuer, such as via JWKS; accepting algorithms conforming to policy.
- **Issuer (`iss`):** matches the configured and trusted OpenID Provider.
- **Audience (`aud`):** token issued for the application's `client_id`; handles `azp` when required by OIDC rules.
- **Time validity:** `exp` is still valid, `iat` and other timing conditions pass validation rules.
- **Session binding:** validates `nonce` when the OIDC request sent a nonce; inspects `auth_time` and authentication level if the flow requires it.

Spring Security OIDC Client provides protocol handling and ID Token validation for the `oauth2Login` flow when properly configured. The development team must still choose the right trusted issuer, manage configuration, and never skip verification steps when writing custom integrations.

To store a key linking a user to internal data, typically use the **`(issuer, subject)`** pair, i.e., `iss` and `sub`. Do not use email as an immutable identifier: email addresses can change, be recycled, or be unverified. The `email_verified` claim also does not automatically mean the user holds every permission in the application.

### 4.2. Access Token Does Not Replace ID Token

An Access Token may contain `sub` and other claims, but **never use it as OIDC login proof in place of an ID Token**. The token may be issued for a specific API, have an audience different from the OIDC Client, or have an opaque format unreadable by the client.

When an API receives `Authorization: Bearer <access_token>`, the API itself must enforce appropriate checks:

- JWT: verify signature, issuer, audience intended for the API, lifetime, scopes, and required claims.
- Opaque token: typically use introspection or a mechanism provided by the Authorization Server to determine whether the token is active and which permissions are attached to it.
- After token validation: still verify business permissions such as order ownership, organizational scope, record state, and roles enforced at the API.

**Successful OIDC login on the frontend is not grounds for another API to skip bearer token verification.** Conversely, an API verifying a valid Access Token does not replace session and CSRF management on the frontend if the frontend uses cookies.

### 4.3. Application Session Differs from SSO Session

Suppose a user logs into portal A, then opens portal B using the same IdP:

- A and B can leverage the shared SSO session at the IdP so the user does not have to re-enter a password.
- A still has its own session cookie, timeout, internal user data, and authorization; B has its own separate set.
- Expiring the session at A does not necessarily expire the SSO session at the IdP. A can redirect to log in again and be authenticated by the IdP almost immediately.
- Locking an account at the IdP, changing a password, or logging out of SSO does not guarantee all application sessions and issued JWTs become invalid immediately unless the parties have appropriate synchronization or revocation mechanisms.

For backend web applications, prefer keeping tokens on the server side and using session cookies with proper security configuration (HTTPS, `Secure`, `HttpOnly`, `SameSite` per real flow). Client secrets must never be placed in JavaScript, URLs, logs, or frontend bundles. If building a public SPA or mobile app, token storage and PKCE requirements must be designed for that client type; do not copy a confidential server-side client configuration directly onto an app that cannot protect a secret.

## 5. In Spring Security, What Does the Library Do and What Must Developers Do?

Spring Security provides protocol implementation mechanisms; it does not know each system's business rules in advance.

### 5.1. Two Configurations Easily Confused

- **`oauth2Login()`:** logs users into the application via OAuth 2.0/OIDC. When the registration includes the `openid` scope and the IdP supports OIDC, Spring Security handles OIDC login and creates an OIDC principal.
- **`oauth2Client()`:** supports the application acting as an OAuth 2.0 Client when obtaining/managing tokens to call other services. Authorized client and refresh behavior depend on registration, grant type, authorized client management config, and tokens issued by the IdP.
- **`oauth2ResourceServer()`:** used for API endpoints receiving bearer access tokens. This is a separate resource server responsibility, not implicitly enabled just because `oauth2Login()` is present.

Depending on architecture, an application can use only `oauth2Login`, or combine these configurations with appropriate security filter chains and access rules.

### 5.2. Example Configuration of a Server-Side Spring Boot OIDC Client

Suppose the company's IdP publishes OIDC metadata at issuer `https://id.example.org/realms/company`. The configurations below are illustrative; issuer values, client registrations, and access scopes must match the real IdP.

In a Spring Boot project using Gradle:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
}
```

In `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company:
            issuer-uri: https://id.example.org/realms/company
```

Meaning of the main sections:

- `registration.company` is the client registration name in Spring Security; linked to the default login initiation path `/oauth2/authorization/company`.
- `client-id` and `client-secret` are the application's credentials **on the IdP side**. For confidential clients, secrets must come from environment variables/a secret manager and exist only on the backend. Public clients use authentication mechanisms suitable for their client type rather than relying on a secret embedded in the app.
- `redirect-uri` is the default callback `/login/oauth2/code/company` after Spring substitutes `{registrationId}`. The actual URI must be permitted by the IdP.
- `scope` contains `openid` to request OIDC. `profile` and `email` are supplementary scopes and do not guarantee all claims appear in the ID Token.
- `issuer-uri` helps Spring discover endpoints and key information from the issuer's metadata. Issuers must be explicitly chosen and trusted via configuration, never accepted arbitrarily from user parameters.

Example HTTP security configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

With this configuration, Spring Security handles standard OIDC login steps and only allows authenticated users to access protected paths. **However, `hasRole("ADMIN")` does not automatically understand IdP groups.** The application still needs a trustworthy rule assigning `ROLE_ADMIN` if users are actually meant to access `/admin/**`.

The default login path to initiate the flow is `/oauth2/authorization/company`. After a successful callback, the OIDC principal can be read in a controller:

```java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    @GetMapping("/me")
    public Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "issuer", user.getIdToken().getIssuer().toString(),
            "subject", user.getSubject()
        );
    }
}
```

`/me` illustrates how the application receives identity **already processed by the OIDC login layer**. In practice, the application typically uses `(issuer, subject)` to look up an internal profile and then checks status and business permissions before returning data.

### 5.3. Mapping IdP Claims to Application Authorities

Suppose the IdP sends a `groups` claim in the ID Token and the `portal-admins` group is governed by organizational policy. The application can choose to map that group to `ROLE_ADMIN`:

```java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;

@Bean
GrantedAuthoritiesMapper userAuthoritiesMapper() {
    return authorities -> {
        Set<GrantedAuthority> mapped = new HashSet<>(authorities);

        for (GrantedAuthority authority : authorities) {
            if (authority instanceof OidcUserAuthority oidcAuthority) {
                List<String> groups =
                    oidcAuthority.getIdToken().getClaimAsStringList("groups");

                if (groups != null && groups.contains("portal-admins")) {
                    mapped.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
                }
            }
        }

        return mapped;
    };
}
```

Place this `@Bean` method inside a `@Configuration` class such as `SecurityConfig`. The sample uses Java 17+ syntax and assumes the `groups` claim is configured at the IdP to appear in the **ID Token**. Many IdPs do not send this claim by default, or place groups in UserInfo, the Access Token, or a separate API. In those cases, integrate with the IdP's exact source and policy instead of assuming the claim is always present.

Mapping external groups into roles is only **one way** to determine permissions. For sensitive applications, the app may need to query internal role tables, organization/project permissions, multi-level approval policies, or record-level checks. Never treat `email` alone or some self-declared attribute as sufficient for administrative privileges.

For example, `hasRole("ADMIN")` protecting a route is only a first step; an "approve order" operation also needs to check whether the order belongs to an assigned branch and whether the user holds approval rights at the time of the action.

### 5.4. When the Client Calls Another API

The client application can retrieve the Access Token belonging to the OAuth 2.0 authorized client to call a permitted API:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class OrderApiProxyController {

    private final RestClient restClient;

    public OrderApiProxyController(RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    @GetMapping("/external-orders")
    public String orders(
        @RegisteredOAuth2AuthorizedClient("company")
        OAuth2AuthorizedClient authorizedClient
    ) {
        String accessToken = authorizedClient.getAccessToken().getTokenValue();

        return restClient.get()
            .uri("https://api.example.org/orders")
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .body(String.class);
    }
}
```

This example shows **a backend client using an Access Token to call an API**, not substituting an ID Token. Before applying it, the IdP must issue a token with audience, scopes, and permissions suited to the target API; the `openid profile email` scopes from the login example above do not automatically grant permission to call the orders API. In a real system, organize an HTTP client/authorized-client manager layer to handle expired tokens, access errors, controlled retries, and avoid logging tokens.

At the same time, the `https://api.example.org/orders` API must have corresponding resource server security. A client sending a bearer token does not allow the API to blindly trust everything in the request.

## 6. Responsibilities That Cannot Be "Fully Delegated" to the IdP

### 6.1. Business-Context Authorization

An IdP is usually good at answering "which account is this?" and may answer "which groups does this account belong to?". Only the application knows:

- Which tenant, department, or project the user belongs to in the application's data model.
- Whether the user has permission to view/edit **a specific record**.
- Whether the data is in a state that permits the operation.
- Whether an admin role in system A corresponds to any role in system B.

Do not use `sub`, `email`, or just a broad IdP group to skip ownership checks on specific resources. APIs and business layers must enforce permissions on every sensitive operation.

### 6.2. Local User Lifecycle Management

On first login, the application can automatically create a profile from `iss` and `sub` (just-in-time provisioning), or require prior administrator approval. That is an **application decision**. The application needs to define how to:

- Link an IdP identity to an existing business account without accidentally hijacking an account.
- Handle a user disabled in the application even if the IdP still allows them to log in.
- Update changed profile fields from the IdP without losing business data.
- Handle IdP migrations, multiple issuers, multiple tenants, or merged accounts.

If supporting multi-organization setups, never take a user-submitted `iss` and immediately trust it for token validation. Every accepted issuer/tenant must belong to the application's trusted policy and registrations.

### 6.3. Protecting the Application After Login

The IdP completing MFA does not automatically secure an endpoint that allows a user to edit someone else's email address. The application remains responsible for:

- Access control at the URL, method, and business layers; IDOR/ownership checks.
- CSRF when using session cookies, preventing session fixation, XSS, and cookie/HTTPS configuration.
- Limiting sensitive data exposed to the frontend, logs, metrics, and traces.
- Handling tokens, secrets, sessions, and user data in memory/storage.
- Session lifetime policies or re-authentication requirements for sensitive actions, if applicable.

OAuth/OIDC `state` protects the login callback; it **does not replace** CSRF tokens for state-changing business requests. Similarly, a token with the `orders.read` scope does not mean the user may read every order.

### 6.4. Logout and Revocation

Logout has multiple layers:

1. **Local logout:** the application invalidates the session, clears `SecurityContext`, and clears associated session cookies. This is the part the client controls directly.
2. **RP-Initiated Logout:** the application can redirect the user to the OpenID Provider's end-session endpoint, if supported by the IdP and configured with matching metadata. Spring Security provides `OidcClientInitiatedLogoutSuccessHandler` for this case.
3. **Revoking tokens or other sessions:** the Authorization Server and related applications/resource servers need corresponding mechanisms, such as revocation, introspection, short token lifetimes, or supported logout protocols.

**Local logout is not equivalent to IdP SSO logout.** Therefore, a user can click log out in application A, then click log in and be recognized again by the IdP without entering a password. This is not necessarily a bug in Spring Security.

Similarly, logging out at the IdP does not automatically delete session cookies across all applications unless they integrate an appropriate logout notification mechanism. With self-contained JWT access tokens, immediate permission revocation may require mechanisms beyond standard signature and `exp` checks.

## 7. Illustrative Scenarios for Identifying the Right Responsibility

### Scenario A: Login Succeeds but Admin Page Cannot Be Opened

An employee logs in via the IdP, receives a valid OIDC principal, yet gets HTTP `403 Forbidden` when visiting `/admin`.

This may be the **correct authorization decision** by the application. Check which role the application requires, which permission/claim sources were granted, whether a `ROLE_ADMIN` mapping rule exists, and whether the employee falls within the permitted scope. Successful login alone is not enough to grant admin privileges.

### Scenario B: Web Page Shows User Name but API Call Returns HTTP 401

OIDC login succeeded, yet the token sent to the API may be expired, have the wrong issuer, not target the API's audience, or the endpoint may be missing a bearer token. The place to check is the OAuth client configuration when acquiring the token **and** the verification configuration at the resource server.

Do not solve it by sending the ID Token to the API "just in case". Issue and use an **Access Token appropriate for the API**, and let the resource server verify it.

### Scenario C: Two Systems Share SSO but Have Different Permissions

An employee can be an administrator in the HR system yet read-only in the procurement system. Both log in via the same IdP and may receive the same identity, but **each system owns its own business authorization**. Centralized groups only become permissions when a system has a valid mapping rule.

### Scenario D: User Logs Out but Logs Back In Immediately Without Password Prompt

The application destroyed its local session, while the SSO session at the IdP remains active. To terminate SSO as well, integrate logout with the IdP using a supported method and assess the impact on other applications sharing SSO.

### Scenario E: User Is Locked at the IdP While Already Inside the Application

The IdP typically blocks **the next authentication attempt**, while the application may still have an active local login session. If near-real-time access blocking is required, developers must design session validity policies, user status sync, or corresponding revocation mechanisms; never assume locking an account at the IdP immediately clears every session and Access Token elsewhere.

## 8. Diagnosing Where to Investigate Based on the Error

| Symptom | Where to Look First | Reason |
|---|---|---|
| Login fails due to password, MFA, or locked account. | IdP, authentication policies, and login logs. | The IdP directly handles identity and authentication methods. |
| IdP reports invalid redirect URI. | Client registration config at the IdP and Spring's actual `redirect-uri`. | Both sides must match allowed URIs; proxies/hosts/schemes can affect the effective URL. |
| Callback rejected due to `state` mismatch. | Client-side OAuth session/state, cookies, browser, and reverse proxy. | The client must correlate the callback with an earlier initiated request. |
| ID Token has wrong issuer or audience. | Client-side issuer/registration config and IdP issuance config. | Tokens must be issued for the right client by a trusted issuer. |
| Login succeeds but feature returns `403`. | Authorization rules, authority mapping, and application data permissions. | Completing authentication does not mean being permitted to perform the action. |
| API returns `401` even though web UI is logged in. | Access Token, API audience/scope, resource server config, and API call path. | The API validates bearer tokens independently of the web session. |
| Logged out on web app yet SSO remains active. | Distinguish local logout from IdP-side OIDC logout. | The two sessions are managed by two different systems. |

The IdP, API, and claim names in these examples are illustrative. During actual integration, consult the issuer's metadata, client registration settings, and claim/scope contracts supported by that system's identity provider.

The final trust boundary is enforced at **the right decision point**: the IdP authenticates and issues tokens; the OIDC Client validates login results, maintains sessions, and enforces application policies; the Resource Server validates tokens calling APIs and checks permissions on the resources it manages.
