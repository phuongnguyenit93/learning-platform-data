# 7.5. OAuth2LoginAuthenticationFilter and Authentication Creation

In a **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client application running on Servlet**, a user clicks "Sign in", the browser redirects to the OpenID Provider (OP), and then returns to the application via a callback carrying `code` and `state`. At that callback, **`OAuth2LoginAuthenticationFilter`** intercepts the HTTP message, coordinates with `AuthenticationManager` and `AuthenticationProvider` implementations to authenticate the OAuth2/OIDC result, and produces an **`Authentication`** object representing the logged-in user.

Understanding this filter answers very practical questions:

- Why doesn't the `/login/oauth2/code/{registrationId}` callback need a controller?
- How does the filter take `code` and create `OAuth2AuthenticationToken`?
- When does Spring Security exchange the authorization code for tokens, verify the ID Token, and fetch user information?
- How do `Authentication`, `SecurityContext`, HTTP session, and `OAuth2AuthorizedClient` differ?
- Why can login succeed at the OP while the application still treats the user as unauthenticated?

This lesson uses **Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet**, and the Authorization Code Flow. Class names are public Spring Security concepts; some internal details or defaults may vary across versions. We focus on responsibilities and data flow within the framework.

## 1. Role of the Filter in the Login Diagram

A typical OIDC login flow has two sides:

1. **Front-channel via browser:** redirect from the application to the OP's Authorization Endpoint, then callback with the authorization code.
2. **Back-channel from backend:** Spring exchanges the code at the Token Endpoint, receives tokens, and verifies OIDC details.

`OAuth2LoginAuthenticationFilter` sits at the **callback step**. It is not the filter that sends the browser to the OP initially; that initiation step is normally handled by `OAuth2AuthorizationRequestRedirectFilter`.

```mermaid
sequenceDiagram
    autonumber
    actor B as Browser
    participant R as OAuth2AuthorizationRequestRedirectFilter
    participant O as OpenID Provider
    participant F as OAuth2LoginAuthenticationFilter
    participant M as AuthenticationManager
    participant P as OAuth2/OIDC AuthenticationProvider
    B->>R: GET /oauth2/authorization/academy
    R->>R: Build authorization request; save state/context
    R-->>B: 302 to OP
    B->>O: GET /authorize?client_id=...&state=...
    O-->>B: 302 callback with code & state
    B->>F: GET /login/oauth2/code/academy?code=...&state=...
    F->>F: Retrieve saved authorization request
    F->>M: authenticate(OAuth2LoginAuthenticationToken)
    M->>P: Delegate to matching AuthenticationProvider
    P->>O: POST token endpoint (authorization code)
    O-->>P: Access Token + ID Token (OIDC)
    P->>P: Verify tokens; load and map user
    P-->>M: Authenticated Authentication
    M-->>F: Successful OAuth2LoginAuthenticationToken
    F->>F: Convert to OAuth2AuthenticationToken
    F->>F: Save OAuth2AuthorizedClient
    F->>F: Complete success handling, SecurityContext/session
    F-->>B: 302 to destination page
    B->>F: Next request with session cookie
    Note over B,F: New request passes through SecurityFilterChain; no re-login needed
```

The diagram intentionally separates the filter, manager, and provider. **The filter coordinates HTTP communication**, while the provider handles the core OAuth2/OIDC authentication work. It also shows that "having a token issued by the OP" does not equate to "having an `Authentication` in the application".

## 2. Concepts to Distinguish

| Concept | Meaning in Spring Security | Example in OAuth2/OIDC login |
| --- | --- | --- |
| `Authentication` | Interface representing principal, authorities, credentials/details, and authentication status | `OAuth2AuthenticationToken` after successful login |
| `Principal` | User identity currently recognized by the application | `OAuth2User` or `OidcUser` |
| `AuthenticationManager` | Entry point for processing an authentication request | `ProviderManager` delegating the authentication request to a supporting provider |
| `AuthenticationProvider` | Component implementing a specific authentication mechanism | `OAuth2LoginAuthenticationProvider` or `OidcAuthorizationCodeAuthenticationProvider` |
| `SecurityContext` | Container holding the current `Authentication` | Bound to request processing and can be persisted across requests |
| `SecurityContextHolder` | Access point to the context during request handling | Controllers/services reading the authenticated user |
| `OAuth2AuthorizedClient` | Data binding a client registration and principal to issued tokens | Stores access token/refresh token (if present) for calling APIs |
| `HTTP session` | Mechanism for maintaining state across browser requests | Can store `SecurityContext` and temporary authorization request data |

An **`Authentication` object is not simply an access token**. It holds the principal, permissions, and authentication status for Spring Security to make access decisions. In a web application, the browser typically carries a **session cookie** back to the application after login; access tokens are managed separately on the backend via the authorized client.

### 2.1. Authentication types appearing in the same flow

Note the transformation:

```text
Authorization response (code + state)
             |
             v
OAuth2LoginAuthenticationToken
  - authentication request passed to AuthenticationManager
  - contains ClientRegistration and OAuth2AuthorizationExchange
             |
             v
AuthenticationProvider succeeds
  - tokens, principal, and authorities are created/attached
             |
             v
OAuth2AuthenticationToken
  - final Authentication used by the web application
  - contains OAuth2User/OidcUser, authorities, authorizedClientRegistrationId
             |
             v
SecurityContext
  - Authentication attached to the request and saved per session policy
```

`OAuth2LoginAuthenticationToken` is the type used **during the OAuth2 login authentication process**. Upon success, `OAuth2LoginAuthenticationFilter` converts the result into `OAuth2AuthenticationToken` for the application. Do not assume controllers will see `OAuth2LoginAuthenticationToken` inside `SecurityContextHolder`.

## 3. Where Does the Filter Sit and Which URLs Does It Listen On?

In the Servlet model, Spring Security has `FilterChainProxy` and one or more `SecurityFilterChain` beans. When registering:

```java
http.oauth2Login(Customizer.withDefaults());
```

Spring Security adds the filters and components serving OAuth2 Login, including `OAuth2LoginAuthenticationFilter`.

### 3.1. Two easily confused URLs

| Default URL | Primary component | Meaning |
| --- | --- | --- |
| `/oauth2/authorization/{registrationId}` | `OAuth2AuthorizationRequestRedirectFilter` | Initiates login by building an authorization request and redirecting to the OP. |
| `/login/oauth2/code/{registrationId}` | `OAuth2LoginAuthenticationFilter` | Receives the callback from the OP and authenticates using the authorization code. |

Example when registration ID is `academy`:

```text
GET /oauth2/authorization/academy

GET /login/oauth2/code/academy?code=CODE&state=STATE
```

`OAuth2LoginAuthenticationFilter` has a default callback matching pattern tied to `/login/oauth2/code/*`. The `*` here matches the callback path corresponding to the registration; **it does not mean the filter authenticates every request on the website**.

If a request does not match the URL handled by the filter, the filter does not start OAuth2 login authentication from that request. In applications with multiple `SecurityFilterChain` beans, the callback must land in a chain configured with `oauth2Login()`; a higher-priority chain that captures the callback without containing the filter can cause login to fail.

### 3.2. The filter extends `AbstractAuthenticationProcessingFilter`

`OAuth2LoginAuthenticationFilter` extends **`AbstractAuthenticationProcessingFilter`**. Its general processing pattern is:

1. Check whether the request is an authentication request intended for this filter.
2. Call `attemptAuthentication(...)` to build the request and ask `AuthenticationManager` to authenticate it.
3. On success, apply the session strategy, populate `SecurityContext`, and invoke the configured success handler.
4. On failure, clear any invalid authentication context and invoke the failure handler.

Success or failure applies to **the application login step**, not merely the OP's HTTP message.

## 4. Step 1: Creating and Saving the Authorization Request Before the Callback

Although this lesson focuses on the callback filter, it cannot be understood without the data saved **before the browser goes to the OP**.

When the browser navigates to:

```http
GET /oauth2/authorization/academy HTTP/1.1
Host: app.example.com
```

`OAuth2AuthorizationRequestRedirectFilter` together with the authorization request resolver typically:

1. Looks up `ClientRegistration` by registration ID `academy`.
2. Creates an authorization request containing `client_id`, `response_type=code`, `redirect_uri`, and `scope`.
3. Generates/adds `state`, along with required OIDC/PKCE data such as `nonce` and `code_challenge` depending on configuration.
4. Saves `OAuth2AuthorizationRequest` into an `AuthorizationRequestRepository`.
5. Returns `302 Location` so the browser redirects to the OP's Authorization Endpoint.

A common storage mechanism is **`HttpSessionOAuth2AuthorizationRequestRepository`**, which saves the pending callback request in the server-side HTTP session. The browser brings the session cookie back after redirecting so the server can locate the original request.

Illustrative response example:

```http
HTTP/1.1 302 Found
Location: https://idp.example.com/authorize?response_type=code&client_id=academy-web&state=RANDOM_STATE&scope=openid%20profile&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Facademy
Set-Cookie: JSESSIONID=SESSION_REFERENCE; Path=/; Secure; HttpOnly
```

**`state` is request–response correlation data**, not an access token. The client-side saved authorization request tells the callback filter which request was initiated and which provider/client registration must be used.

If the application cannot recover this record, the fact that the OP logged the user in successfully is **not enough** for the application to complete login safely.

## 5. Step 2: Browser Returns to `OAuth2LoginAuthenticationFilter`

After the user authenticates and consents (if required by the OP), the OP redirects the browser back to the registered callback:

```http
GET /login/oauth2/code/academy?code=ONE_TIME_CODE&state=RANDOM_STATE HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_REFERENCE
```

This is a new HTTP request sent by the browser to the **Spring application**. The filter receives the callback, reads parameters, and correlates it with the saved authorization request.

Conceptually, `attemptAuthentication` performs these steps:

1. Identifies this as an **OAuth2 authorization response**, containing `code` and `state` on success, or `error` when denied by the OP.
2. Calls `AuthorizationRequestRepository` to load and remove the corresponding pending authorization request per repository behavior.
3. Extracts the **registration ID** belonging to the saved request and looks up the matching `ClientRegistration`.
4. Constructs an `OAuth2AuthorizationResponse` object.
5. Combines the request and response into an **`OAuth2AuthorizationExchange`**.
6. Creates an **`OAuth2LoginAuthenticationToken`** as the input authentication token and passes it to `AuthenticationManager.authenticate(...)`.

These steps are responsible for **preserving protocol context**. The client must not arbitrarily trust an externally supplied `registrationId`, `redirect_uri`, or endpoint without binding it to the initiated request.

### 5.1. Why must the authorization request be restored?

A bare callback such as:

```text
/login/oauth2/code/academy?code=abc&state=xyz
```

is insufficient on its own to prove:

- Whether the browser previously initiated login;
- Whether `state` belongs to a request the application is expecting;
- Which client registration and OP participated;
- What the original request's redirect URI, scopes, and PKCE verifier were.

This information must come from **client-side trusted context**. If no authorization request exists or the callback is invalid, Spring Security must terminate the flow with an error rather than creating an `Authentication` from an arbitrary code.

### 5.2. The `authorization_request_not_found` error

A typical callback failure is being unable to locate the saved authorization request. Common causes include:

- The browser did not send back the session cookie due to `Secure`, `SameSite`, `Domain`, `Path`, or hostname mismatch;
- The HTTP session expired while the user logged in at the OP;
- The initiation request and callback hit two instances that do not share sessions;
- The user opened multiple concurrent login flows against a storage mechanism that does not support concurrent requests;
- The callback was invoked directly without going through initiation;
- Inconsistent callback URI or security chain configuration.

Never fix this by skipping request storage or disabling `state` checks. Find where the session and authorization request were lost.

## 6. Step 3: Creating `OAuth2LoginAuthenticationToken`

Input data from the callback and saved request are packaged into a dedicated `Authentication` for the login process.

Relationship diagram:

```text
ClientRegistration
  - registrationId = academy
  - clientId, client authentication method, scopes
  - authorizationUri, tokenUri, jwkSetUri, issuer metadata
            |
            v
OAuth2AuthorizationRequest  +  OAuth2AuthorizationResponse
            |                            |
            +---- OAuth2AuthorizationExchange ----+
                                                  |
                                                  v
                              OAuth2LoginAuthenticationToken
                                                  |
                                                  v
                              AuthenticationManager.authenticate(...)
```

This is where Spring turns **HTTP protocol information** into an **authentication request** understood by Spring Security's authentication system.

Key points to remember:

- `OAuth2LoginAuthenticationToken` at the start of the flow **does not yet prove the user is logged in**.
- An authorization code is **not a user identity**.
- `AuthenticationManager` is invoked to route this request through a supporting provider.
- `OAuth2AuthenticationToken` for `SecurityContext` is created **after the provider authenticates successfully**.

In normal application code, you do not manually `new OAuth2LoginAuthenticationToken(...)`. Spring Security performs that step when the callback reaches the right filter.

## 7. Step 4: `AuthenticationManager` Selects a Provider and Authenticates

`AuthenticationManager` is an interface with a primary method:

```java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
```

In standard configurations, `ProviderManager` delegates authentication to an `AuthenticationProvider` supporting the received `Authentication` type. For OAuth2 Login, the key providers are:

| Provider | Primary context | Result |
| --- | --- | --- |
| `OAuth2LoginAuthenticationProvider` | Non-OIDC OAuth2 Login, e.g., provider returning user info via a custom UserInfo API | Exchanges code for tokens, uses `OAuth2UserService` to obtain an OAuth2 principal and map authorities. |
| `OidcAuthorizationCodeAuthenticationProvider` | **OIDC Authorization Code Flow**, when login includes `openid` | Exchanges code for tokens, verifies ID Token, and creates `OidcUser` per OIDC configuration. |

Providers may use lower-level components such as **`OAuth2AccessTokenResponseClient`** to call the Token Endpoint and **`OAuth2UserService` / `OidcUserService`** to construct the principal from user data. Exact classes for the HTTP client, token decoder, and repository may vary by version or customization.

### 7.1. Exchanging the authorization code for tokens

Using the created authorization exchange, the provider executes a server-to-server HTTP request to the OP's Token Endpoint:

```http
POST /oauth2/token HTTP/1.1
Host: idp.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-credentials-when-applicable>

grant_type=authorization_code&code=ONE_TIME_CODE&redirect_uri=https%3A%2F%2Fapp.example.com%2Flogin%2Foauth2%2Fcode%2Facademy
```

The request is shown abbreviated. For clients using PKCE, the request also includes **`code_verifier`**. For confidential clients, the client authentication method can be `client_secret_basic`, `client_secret_post`, or another mechanism supported by the OP.

Key point: **Spring's backend performs the token request**; the browser never needs to know the client secret or PKCE verifier. The OP verifies that the code is valid, matches the client/redirect URI, is unused, and satisfies PKCE conditions before issuing tokens.

An OIDC response may look like:

```json
{
  "access_token": "<access-token>",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "openid profile email",
  "id_token": "<signed-oidc-id-token>"
}
```

Some OPs also issue a `refresh_token` if the client, grant, scopes, and OP policy allow it; never assume a refresh token is always present.

### 7.2. `state`, PKCE, and filter boundaries

Three checks occur at different places across the flow:

| Mechanism | Where is it handled in terms of responsibility? | Goal |
| --- | --- | --- |
| `state` | Client matches the authorization response against the saved authorization request during callback/authorization code handling | Binds response to request; defends against login CSRF and forged callbacks. |
| PKCE | OP verifies `code_verifier` at the Token Endpoint against the previously received challenge | Binds the code to the party that initiated the authorization request. |
| OIDC `nonce` | OIDC Client verifies `nonce` inside the ID Token after token verification | Binds the ID Token to the initiated authentication attempt. |

Do not assume `OAuth2LoginAuthenticationFilter` performs all cryptographic checks by itself. The filter coordinates the callback and passes the authentication request to providers; providers, the token response client, and OIDC decoders/validators handle the corresponding protocol steps and validations.

When replacing default components yourself, preserve all of these constraints. Simply "being able to log in" after customization does not prove the flow remains adequately protected.

## 8. Step 5: From OP Tokens to `OAuth2User` or `OidcUser`

An access token and ID Token are data issued by the OP, while Spring needs a **principal** and **authorities** so the application knows who the user is and what they can do.

### 8.1. Standard OAuth2 Login

For non-OIDC OAuth2 providers, Spring typically uses `OAuth2UserService` (e.g., `DefaultOAuth2UserService`) to retrieve data from the configured UserInfo endpoint or user API and construct an `OAuth2User`.

The principal may provide:

- `getName()`: identifier mapped via `user-name-attribute`;
- `getAttributes()`: attributes returned by the provider;
- `getAuthorities()`: set of permissions Spring Security uses during authorization.

If a provider returns JSON like:

```json
{
  "id": "u-928",
  "display_name": "Learner A",
  "email": "learner@example.com"
}
```

then `user-name-attribute: id` can be used in the OAuth2 user mapping configuration. Avoid assuming email is an immutable or verified identifier.

### 8.2. OIDC Login

When the request includes scope `openid` and the OP returns a valid ID Token, Spring runs the **OIDC** flow. `OidcAuthorizationCodeAuthenticationProvider` validates the ID Token per OIDC, including applicable conditions such as:

- Allowed signature and algorithm, signing key from a trusted provider;
- `iss` matching the configured issuer;
- `aud` containing the corresponding client ID;
- `exp` / timestamp constraints;
- `nonce` matching the authorization request if a nonce was sent;
- Other OIDC constraints such as `azp` when applicable.

Then `OidcUserService` can combine the ID Token and UserInfo data depending on deployment conditions to create an **`OidcUser`**. `OidcUser` is a specialized `OAuth2User` providing access to the ID Token and OIDC claims.

Example of claims an OIDC principal can provide:

```java
OidcUser principal = ...;

String subject = principal.getSubject();
String issuer = principal.getIssuer().toString();
String displayName = principal.getFullName();
String email = principal.getEmail();
```

This snippet illustrates the claim-reading API, not code that creates the principal. `getFullName()` or `getEmail()` may return `null` because providers do not necessarily supply all claims.

**The ID Token is for authenticating the user to the OIDC Client**, not for replacing access tokens when calling APIs. UserInfo data must also match the ID Token's subject per OIDC rules.

### 8.3. How are authorities created and mapped?

`Authentication` holds **`GrantedAuthority`** instances, such as default authorities representing an OAuth2/OIDC user and authorities mapped from claims/scopes by the framework. However, an OP sending a `groups` or `roles` claim **does not mean** Spring automatically grants `ROLE_ADMIN`.

For example, with the rule:

```java
.requestMatchers("/admin/**").hasRole("ADMIN")
```

Spring Security looks for the matching authority, typically `ROLE_ADMIN`. If the principal only has default OIDC authorities, the user lacks admin access. The application must explicitly define how to trust and map OP claims to internal authorities, or read permissions from its own database.

Common extension points are:

- `GrantedAuthoritiesMapper` to translate provider authorities into application authorities;
- A custom `OidcUserService` to read and translate additional claims;
- A custom `OAuth2UserService` for non-OIDC OAuth2 providers.

When adding authorities, verify the claim source, issuer, audience, authorization contract, and how values may change per provider. Never build authorization decisions by blindly trusting arbitrary claims sent from the browser.

## 9. Step 6: Converting to `OAuth2AuthenticationToken`

Once the provider authenticates successfully and returns a result containing the principal, authorities, and related tokens, `OAuth2LoginAuthenticationFilter` converts it into an **`OAuth2AuthenticationToken`** via the corresponding converter mechanism.

You can picture it as:

```text
OAuth2LoginAuthenticationToken (result from provider)
  - ClientRegistration = academy
  - OAuth2User or OidcUser
  - GrantedAuthority collection
  - AccessToken (and RefreshToken if present)
           |
           | convert authentication result
           v
OAuth2AuthenticationToken
  - principal = OAuth2User / OidcUser
  - authorities = application permissions read from principal
  - authorizedClientRegistrationId = academy
  - authenticated = true
```

`OAuth2AuthenticationToken` is the object that components such as **`SecurityContextHolder`**, authorization rules, controllers, and method security normally see after a successful login.

At the API level, you can read:

```java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

String name = authentication.getName();
boolean authenticated = authentication.isAuthenticated();
Collection<? extends GrantedAuthority> authorities =
        authentication.getAuthorities();
```

**Do not conclude a user is valid merely because `isAuthenticated()` returns `true` on an arbitrary object created by your own code.** In the standard flow, Spring Security only stores the result after `AuthenticationManager`/provider authentication succeeds. Avoid injecting untrusted `Authentication` objects into the context to "skip login".

### 9.1. Where is the access token stored?

`OAuth2AuthenticationToken` primarily represents the **logged-in user**. Tokens for calling APIs are managed through **`OAuth2AuthorizedClient`**, which associates:

- `ClientRegistration`;
- The authorized principal's name/identifier;
- The access token and expiration metadata;
- The refresh token if available.

Therefore, reading `Authentication.getCredentials()` or casting `OAuth2AuthenticationToken` to a Bearer token type to obtain an access token is the wrong model. Use `OAuth2AuthorizedClientRepository`, `OAuth2AuthorizedClientService`, or appropriate OAuth2 Client integration when obtaining tokens to call downstream APIs.

## 10. Step 7: Saving `OAuth2AuthorizedClient`

In the typical Servlet login flow, after receiving the authentication result, `OAuth2LoginAuthenticationFilter` creates/registers an `OAuth2AuthorizedClient` corresponding to the registration and principal. The data is saved through the configured **`OAuth2AuthorizedClientRepository`**.

```text
Login from OP
   |
   +--> OAuth2AuthenticationToken
   |      Placed in SecurityContext
   |      => application knows the user is logged in
   |
   +--> OAuth2AuthorizedClient
          Stores access token / refresh token when available
          => application can call APIs on behalf of the user
```

These two branches serve different needs. In simple applications, the HTTP session may hold both `SecurityContext` and the authorized client, though the repository/service can certainly be backed by persistent or distributed storage.

Example Spring MVC controller receiving the authorized client when integration is enabled:

```java
import java.util.Map;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class TokenStateController {

    @GetMapping("/token-state")
    Map<String, Object> tokenState(
            @RegisteredOAuth2AuthorizedClient("academy")
            OAuth2AuthorizedClient client) {

        return Map.of(
                "registrationId", client.getClientRegistration().getRegistrationId(),
                "expiresAt", client.getAccessToken().getExpiresAt().toString());
    }
}
```

The example only returns technical state, **never the access token value**. It assumes the authorized client already exists and the resolver is integrated into Spring MVC/Security; in other scenarios, handle the case where the authorized client is not yet present. For production applications, avoid exposing internal endpoints describing token state without clear justification and access control.

If an application only needs web login, you can use `oauth2Login()` without writing any code to read access tokens. When calling APIs is needed, integrate `OAuth2AuthorizedClientManager` or an OAuth2-capable HTTP client.

## 11. Step 8: `SecurityContext`, Session, and Success Handler

After `attemptAuthentication` returns a successful result, `AbstractAuthenticationProcessingFilter` continues finalizing login. In a session-based Servlet app, the key actions are:

1. Apply the appropriate **`SessionAuthenticationStrategy`**, such as session fixation protection by rotating the session ID on login.
2. Create or update **`SecurityContext`** with the authenticated `OAuth2AuthenticationToken`.
3. Use **`SecurityContextRepository`** to save `SecurityContext` per configured policy; in Spring Security 6, persist it explicitly via the right mechanism rather than assuming every setup saves automatically.
4. Publish events / execute remember-me callbacks per filter/framework config when applicable.
5. Invoke **`AuthenticationSuccessHandler`**, typically redirecting the browser back to the saved request or a target page.

From here, subsequent requests carry the session cookie, Spring Security restores `SecurityContext`, and the application knows the user is logged in without calling the OP on every request.

```http
HTTP/1.1 302 Found
Location: /account
Set-Cookie: JSESSIONID=UPDATED_SESSION_REFERENCE; Path=/; Secure; HttpOnly
```

The browser continues:

```http
GET /account HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=UPDATED_SESSION_REFERENCE
```

This is an illustrative header example: not every login emits a new cookie with the same name/attributes. Session behavior depends on session strategy, container, proxy, and application config.

### 11.1. Three state stores not to conflate

| Data | Purpose | Lifecycle |
| --- | --- | --- |
| Temporary authorization request | Stores `state` and data to verify callback / exchange code | From flow initiation until completion / cancellation / expiration |
| `SecurityContext` holding Authentication | Indicates which principal authenticated the request and its authorities | Follows request/session policy and logout |
| `OAuth2AuthorizedClient` | Stores client tokens for subsequent resource calls | Follows storage, token lifetime, and refresh/revoke policy |

The OP's session (SSO login) is yet another independent session. Expiring the Spring app's session does not necessarily log out of the OP; expiring an access token does not necessarily expire the Spring app's login session.

### 11.2. Why not redirect manually before success handling completes?

If you write a custom filter/controller receiving the callback and call `response.sendRedirect(...)` while bypassing authentication and context persistence, the browser may see a landing page while subsequent requests are still treated as anonymous.

To customize post-login behavior, use **`AuthenticationSuccessHandler`** or Spring Security's supported extension points, keeping authentication and context persistence intact. If replacing the default success handler, decide explicitly whether to preserve returning to the **saved request**.

## 12. Minimal Configuration for the Filter to Work

Assume the OP supports issuer discovery and client `academy` has the appropriate callback registered.

### 12.1. Dependencies

For a Spring Boot MVC application using Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
```

### 12.2. `application.yml`

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          academy:
            provider: academy-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
              - email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          academy-oidc:
            issuer-uri: ${OIDC_ISSUER_URI}
```

Where:

- `academy` is the **registration ID**: also the trailing segment of `/oauth2/authorization/academy` and the callback.
- `academy-oidc` is an alias for the OP with a specific issuer.
- `openid` indicates OIDC login, enabling ID Token verification and `OidcUser` creation.
- `{baseUrl}` is inferred by Spring Security from the request/deployment environment; behind a reverse proxy, configure forwarded headers securely.
- `${OIDC_CLIENT_SECRET}` is supplied via environment/secret store; never commit secrets to Git.

### 12.3. `SecurityFilterChain`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain webSecurityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/assets/**", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

If no `SecurityFilterChain` is declared, Spring Boot with the right starters can provide default auto-configuration. Once you **declare your own chain**, make sure that chain enables `oauth2Login()` and its matcher does not exclude the callback. You do not need to declare a bean directly for `OAuth2LoginAuthenticationFilter` in basic setups.

The application can start the flow directly at:

```text
GET http://localhost:8080/oauth2/authorization/academy
```

The path the OP redirects back to is typically:

```text
http://localhost:8080/login/oauth2/code/academy
```

This callback URI must be registered at the OP. In production, HTTPS is normally required.

## 13. Inspecting Authentication from a Controller

After a successful login, a controller can use `Authentication` or `@AuthenticationPrincipal`.

### 13.1. Reading generic Authentication

```java
import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SessionUserController {

    @GetMapping("/whoami")
    Map<String, Object> whoami(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities()
                .stream()
                .map(a -> a.getAuthority())
                .toList();

        return Map.of(
                "name", authentication.getName(),
                "type", authentication.getClass().getSimpleName(),
                "authenticated", authentication.isAuthenticated(),
                "authorities", authorities);
    }
}
```

If the endpoint is protected and logged in via OAuth2/OIDC, the `Authentication` type is typically `OAuth2AuthenticationToken`. In real code, never treat display class names or client-supplied authority lists as trusted input; the server retrieves them from `SecurityContext`.

### 13.2. Reading the OIDC principal

```java
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OidcProfileController {

    @GetMapping("/profile")
    Map<String, String> profile(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
                "subject", user.getSubject(),
                "name", user.getFullName() != null
                        ? user.getFullName() : "(not provided)");
    }
}
```

This example applies to endpoints expecting **OIDC** users only. If the application supports multiple authentication types, the controller must handle cases where the principal is not an `OidcUser`.

Getters for OIDC claims do not replace ID Token verification: Spring Security already validated the token before the principal became the login result. For persistent user identification, consider the **(issuer, subject)** pair; never automatically link accounts solely by email.

### 13.3. Why might the principal lack expected names/claims?

In OIDC, display name, email, and username might be absent from the ID Token or UserInfo. `OidcUser` mapping depends on scopes, provider, and `OidcUserService`. Do not treat a missing `email` as proof that the filter failed to run, and do not assume every provider returns the same claim set.

## 14. Customizing Login While Preserving Authentication Mechanics

### 14.1. Customizing the callback path

If an OP requires a callback following a specific convention, you can change Spring Security's **redirection endpoint** along with the client registration's redirect URI template.

Example using callback `/auth/callback/{registrationId}`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          academy:
            redirect-uri: "{baseUrl}/auth/callback/{registrationId}"
```

```java
@Bean
SecurityFilterChain webSecurityFilterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/assets/**", "/error").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2Login(oauth2 -> oauth2
            .redirectionEndpoint(redirection -> redirection
                .baseUri("/auth/callback/*")));

    return http.build();
}
```

**Both paths must match**: the URI sent to the OP and the filter's callback matcher. You must also update the allowlist at the OP. Changing only one side causes the browser to return to a URL the filter does not handle.

The bean snippet is an **alternative** to the security chain in section 12.3, not a second chain to copy alongside it.

### 14.2. Customizing success/failure

You can configure:

```java
.oauth2Login(oauth2 -> oauth2
    .defaultSuccessUrl("/dashboard", false)
    .failureUrl("/login?error"))
```

This is a DSL snippet inside an active `HttpSecurity` configuration. The `false` argument allows the redirect mechanism to check the saved request per default success handler behavior. Setting `true` always routes login to `/dashboard` in that configuration instead of prioritizing saved requests.

Some systems need custom login auditing or user database mapping. You can use a success handler or appropriate authentication events, while avoiding:

- Printing access tokens, refresh tokens, authorization codes, session IDs, or client secrets to logs;
- Injecting an `Authentication` that has not been verified by a provider;
- Redirecting to client-supplied URLs without validation, avoiding open redirects;
- Executing non-repeatable business logic in a success handler without error handling and idempotency.

### 14.3. Customizing user information

A custom OIDC user service can be wired via:

```java
.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(userInfo -> userInfo
        .oidcUserService(customOidcUserService)))
```

`customOidcUserService` is an application-defined `OAuth2UserService<OidcUserRequest, OidcUser>` bean/object. Customizations should **delegate to the standard `OidcUserService`** to load the user properly, then map additional needed data. If replacing the entire user-loading mechanism, preserve issuer validation, token validation, and subject matching constraints.

Changing the principal does not alter the token endpoint or browser callback; it occurs after the provider has returned valid tokens.

## 15. What Happens When Authentication Fails?

`OAuth2LoginAuthenticationFilter` follows the `AbstractAuthenticationProcessingFilter` pattern: when authentication throws `AuthenticationException`, Spring Security takes the failure branch, clears invalid context per filter mechanics, and delegates to the failure handler.

Error sources can arise at multiple points:

```text
Callback received
    |
    +-- Authorization response missing/invalid?
    |
    +-- Authorization request missing from repository?
    |
    +-- ClientRegistration not found?
    |
    +-- Invalid state, code, PKCE, or redirect_uri?
    |
    +-- Token endpoint returns invalid_client / invalid_grant?
    |
    +-- ID Token has invalid signature, issuer, audience, expiration, or nonce?
    |
    +-- UserInfo request / principal mapping failed?
    |
    v
AuthenticationException -> failure handler
    |
    v
No authenticated login session established
```

In many default web configs, the user is sent to the login page with an error parameter, e.g., `/login?error`. With a custom failure handler, the application can choose another display approach. Never render raw error descriptions from the OP or stack traces containing tokens on a public page.

### 15.1. Diagnostic table by processing stage

| Symptom | Where to investigate | Hint |
| --- | --- | --- |
| Callback `404`, does not enter login flow | Security chain/callback matcher | Compare `redirect-uri` with `redirectionEndpoint().baseUri(...)`; does the chain have `oauth2Login()`? |
| `authorization_request_not_found` | `AuthorizationRequestRepository`, session | Did the browser send the right session cookie? Was the pre-callback request lost/expired? |
| State mismatch | Correlation between request and response | Callback hit a different session, request already consumed, or parallel URL/cookie/flow mixed up. |
| Token endpoint returns `invalid_client` | Client registration and OP authentication method | Wrong client ID/secret, `client-authentication-method`, tenant, or endpoint. |
| Token endpoint returns `invalid_grant` | Authorization code exchange | Expired/reused code, mismatched redirect URI, wrong/missing PKCE verifier. |
| ID Token rejected | OIDC provider/decoder/validator | Signature, JWKS, `iss`, `aud`, `exp`, `nonce`, clock skew. |
| UserInfo returns `401` | `OAuth2UserService`/`OidcUserService` | Access token, scope, UserInfo URI, and how credentials are sent. |
| Callback succeeds, yet user is sent back to login | `SecurityContextRepository`, cookies, session | Context not saved/restored; wrong cookie domain/path/`SameSite`/`Secure`; multi-instance session issue. |
| Login finishes, `403` on `/admin` | Authorization/authorities | Principal lacks the required application authority; does not mean login failed. |
| Browser login works, but Bearer API returns `401` | OAuth2 Resource Server | Access token audience/issuer/scope or API config; web session does not protect Bearer APIs. |

**`invalid_grant` is not solely a PKCE error**; this code can reflect many token endpoint causes. Compare parameters and sanitized logs.

### 15.2. Safe logging

In a learning environment, you can enable Spring Security logging at an appropriate level:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

Logs reveal filter chains, authentication steps, and errors; however, **avoid enabling sensitive logging in production**. Specifically, never collect verbatim callback URLs containing `code`, `Authorization` headers, tokens, session cookies, PKCE verifiers, client secrets, or ID Tokens in widely shared logging systems.

When troubleshooting, log non-sensitive values such as request ID, registration ID, normalized exception type, endpoint (without query string), timestamp, and outcome.

## 16. Common Misconceptions

### 16.1. "A callback with a code means the user is logged in"

False. The code is a temporary credential to **exchange for tokens**, time-limited, bound to the client/redirect URI, and single-use. Spring still has to look up the authorization request, authenticate the exchange, and build the principal.

### 16.2. "OAuth2LoginAuthenticationFilter validates all tokens by itself"

Incorrect regarding division of responsibilities. The filter receives the callback and coordinates handling; `AuthenticationManager`, providers, the OAuth2 token client, and OIDC decoders/user services perform the protocol steps and required content verification.

### 16.3. "The ID Token is the Authentication"

The ID Token is an OP-issued token proving an authentication event to the OIDC Client. `Authentication` is the Spring Security object holding the application's principal and authorities. They are related, but **neither the same type nor for the same purpose**.

### 16.4. "Having Authentication automatically gives you an access token for APIs"

`OAuth2AuthenticationToken` represents the logged-in user; tokens to call APIs live in the authorized client and must match the proper client registration/scopes/audience. An app can have a valid session while the access token has expired or lacks the required scope.

### 16.5. "Successful OP login guarantees the app has a session"

OP login and Spring app login are **two separate sessions**. If the callback fails, `state` is invalid, or context is not persisted, the application is still not logged in. Spring's session timeout is also independent of the OP's SSO lifetime.

### 16.6. "After login, AuthenticationManager must run on every request"

In a standard stateful Servlet app, Spring Security **restores `SecurityContext` from the session** on subsequent requests. There is no need to exchange an authorization code or re-verify an ID Token with the OP on every page load. Session policies and token freshness may require separate refresh or re-authentication flows when business rules demand it.

### 16.7. "Disable CSRF so the callback works"

Authorization Code Flow `state` binds the authorization response to the saved request, whereas **web app CSRF protection** guards state-changing requests when browsers automatically send cookies. Never disable CSRF globally just to make a callback error disappear without investigating chains, methods, cookies, and configuration.

## 17. Tracing a Complete Scenario

Suppose an unauthenticated user opens `/orders`.

**Step A — Request requires authentication**

```text
Browser -> GET /orders
Spring Security -> saves request to return to
Spring Security -> redirects to login
```

**Step B — Initiate OAuth2 Login**

```text
Browser -> GET /oauth2/authorization/academy
Spring -> builds authorization request, saves state and context
Spring -> 302 to OP's Authorization Endpoint
```

**Step C — Callback enters the right filter**

```text
Browser -> GET /login/oauth2/code/academy?code=CODE&state=STATE
OAuth2LoginAuthenticationFilter -> reads response
OAuth2LoginAuthenticationFilter -> retrieves saved authorization request
OAuth2LoginAuthenticationFilter -> creates OAuth2LoginAuthenticationToken
```

**Step D — AuthenticationManager executes authentication**

```text
AuthenticationManager -> matching provider (OIDC)
Provider -> exchanges CODE for tokens at OP
Provider -> verifies ID Token and OIDC claims
Provider -> builds OidcUser and authorities
```

**Step E — Filter completes login**

```text
OAuth2LoginAuthenticationFilter -> converts result to OAuth2AuthenticationToken
OAuth2LoginAuthenticationFilter -> saves OAuth2AuthorizedClient
AbstractAuthenticationProcessingFilter -> handles session, SecurityContext, success handler
Browser <- 302 to /orders
```

**Step F — Subsequent request uses the saved Authentication**

```text
Browser -> GET /orders + session cookie
SecurityContextRepository -> restores Authentication
Authorization -> permits or denies based on authorities/policy
Controller -> reads OidcUser/Authentication
```

At Step F, the controller **never receives the authorization code directly** and never calls the Token Endpoint to construct the user. Those belong to the login flow already handled by Spring Security.

## 18. Self-Check Exercises

**Question 1.** An application registers `redirect-uri: "{baseUrl}/login/oauth2/code/academy"`, while the filter is configured to handle `/auth/callback/*`. What happens?

**Hint:** The OP will redirect to the URL registered by the client, yet the returning request does not match the login filter's matcher. Align the redirect URI, redirection endpoint, and OP allowlist.

**Question 2.** The user logs in successfully at the OP, but the callback reports `authorization_request_not_found`. Should you manually construct an `OAuth2LoginAuthenticationToken` from the received code to continue?

**Hint:** No. The application failed to restore the authorization request and its bindings. Investigate session/cookie/repository issues; never bypass context verification.

**Question 3.** After a successful callback, `Authentication` in the controller is `OAuth2AuthenticationToken`, while the principal is `OidcUser`. Is this abnormal?

**Hint:** No. This is the proper distinction between the `Authentication` object used in `SecurityContext` and the OIDC principal representing the user.

**Question 4.** A user has `Authentication.isAuthenticated() == true` yet gets `403` on `/admin`.

**Hint:** Authentication answers "who is logged in"; authorization checks authorities/endpoint policy. Check authority mapping rather than starting at the token endpoint.

**Question 5.** After login, the application wants to call a downstream API. Should it obtain the access token from `Authentication.getCredentials()` or from the authorized client?

**Hint:** Use `OAuth2AuthorizedClient` and an appropriate token management/refresh mechanism. `Authentication` serves web request principal/authorities; tokens authorizing API calls are managed separately.

## 19. Key Takeaways to Remember

- **`OAuth2LoginAuthenticationFilter` handles callbacks** for OAuth2/OIDC Login in Servlet applications, typically at `/login/oauth2/code/{registrationId}`.
- It **restores the authorization request**, builds `OAuth2AuthorizationExchange`, and passes `OAuth2LoginAuthenticationToken` to `AuthenticationManager`.
- **`AuthenticationProvider`** performs token exchange, OAuth2/OIDC verification, and creation of the `OAuth2User` or `OidcUser` principal.
- On success, the filter converts the result into **`OAuth2AuthenticationToken`**, saves **`OAuth2AuthorizedClient`**, and lets authentication success processing establish/save **`SecurityContext`** per the session mechanism.
- **Principal, Authentication, SecurityContext, authorized client, and session cookie** are distinct objects/concepts serving different purposes.
- Callback errors even after successful OP authentication can still arise from `state`, sessions, redirect URIs, token endpoints, ID Tokens, or security chain configuration.
- For standard flows, **let Spring Security manage the filters and providers**, customizing only via extension points when specifically needed while preserving all security checks.

### References

- [Spring Security Reference — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html).
- [Spring Security Reference — OAuth 2.0 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html).
- [Spring Security Reference — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html).
- [Spring Security API — OAuth2LoginAuthenticationFilter](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/web/OAuth2LoginAuthenticationFilter.html).
- [Spring Security API — OAuth2LoginAuthenticationToken](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/authentication/OAuth2LoginAuthenticationToken.html).
- [Spring Security API — OAuth2AuthenticationToken](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/authentication/OAuth2AuthenticationToken.html).
- [Spring Security API — AbstractAuthenticationProcessingFilter](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html).
- [OpenID Connect Core 1.0 — Authorization Code Flow](https://openid.net/specs/openid-connect-core-1_0.html).
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749).
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700).
