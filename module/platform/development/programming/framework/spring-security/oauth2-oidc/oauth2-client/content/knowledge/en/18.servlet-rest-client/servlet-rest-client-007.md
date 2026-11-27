# 18.7. Handling Authorization Failures and Removing Invalid Authorized Clients

## 1. Problem: Portal Remains Logged In, Yet the API Rejects the Bearer Token

Suppose an **Employee Portal** application runs **Spring Boot 3, Spring Security 6, Servlet/Spring MVC**. An employee logs in via **OpenID Connect (OIDC)**, after which the Portal backend uses **RestClient** to call the **Orders API** on the user's behalf.

At first, everything works:

~~~text
Browser ──GET /bff/orders──> Employee Portal
                              |
                              | RestClient sends access token AT-1
                              v
                           Orders API
                              |
                              └── 200 OK
~~~

Later, the Orders API returns:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token",
                  error_description="The access token is invalid"
Content-Type: application/json

{"error":"unauthorized"}
~~~

This can happen because the access token was revoked, expired per the Resource Server's clock, affected by a policy change, or became invalid for another reason. Meanwhile, **the Portal's HTTP session still holds a valid `Authentication`**.

If the Portal keeps fetching the same `OAuth2AuthorizedClient` from storage and sending AT-1 on every request, the user sees endless loading or repeated 401s, even though the API already declared the token unusable.

**Practical need:** upon receiving **sufficient evidence** that an authorized client is no longer valid, the application must **invalidate/remove the faulty authorized client record** from the exact repository or service so the next usage can go through a valid authorization mechanism. At the same time, it must avoid **mistakenly deleting tokens** merely because an API returned 403 insufficient permissions or a 500 network error.

On the Servlet stack, Spring Security provides:

- `OAuth2ClientHttpRequestInterceptor`: integrates OAuth2 Client into **RestClient** (Spring Security 6.4+).
- `OAuth2AuthorizedClientManager`: resolves tokens by registration, principal, and grant lifecycle.
- `OAuth2AuthorizationFailureHandler`: receives authorization failure events.
- `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler`: removes authorized clients for qualifying errors.
- `OAuth2AuthorizedClientRepository` and `OAuth2AuthorizedClientService`: where authorized clients are stored or retrieved.

> Scope: Java 17+, Spring Boot 3, Spring Security 6 on **Servlet**, using OAuth2/OIDC Client to call Resource Servers. The RestClient OAuth2 interceptor code requires **Spring Security 6.4+**; on older versions, use the integrations available in that version. Hostnames, credentials, and tokens are illustrative data.

## 2. First: What Is an Authorized Client?

An `OAuth2AuthorizedClient` represents the outcome of an OAuth2 Client authorized for a principal:

~~~text
OAuth2AuthorizedClient
├── ClientRegistration
│   ├── registrationId = company
│   ├── clientId = employee-portal
│   └── authorizationGrantType = authorization_code
├── principalName = employee-0042
├── accessToken
│   ├── tokenValue = <sensitive>
│   ├── issuedAt
│   ├── expiresAt
│   └── scopes
└── refreshToken (may be null)
    ├── tokenValue = <sensitive>
    └── issuedAt
~~~

This object is **not** `Authentication` or `SecurityContext`. A user can stay logged into the Portal while the token for the Orders API is no longer usable. Conversely, a token record may remain in a persistent store after the web session ends; that record **does not by itself authenticate** new browser requests.

When an application "removes an authorized client," it is normally an operation that **deletes the token record on the OAuth2 Client side**. It **does not automatically**:

1. Log the user out of the Portal.
2. Revoke the token at the Authorization Server.
3. Invalidate access tokens copied to other systems.
4. Terminate the Single Sign-On session at the OpenID Provider.
5. Delete all other authorized clients for the same principal.

This is the single most important point for scoping failure handling properly.

## 3. Big Picture of RestClient, Manager, and Failure Handler

~~~mermaid
sequenceDiagram
    actor U as User
    participant P as Employee Portal
    participant R as RestClient OAuth2 Interceptor
    participant M as OAuth2AuthorizedClientManager
    participant S as Authorized Client Repository
    participant AS as Authorization Server
    participant API as Orders API

    U->>P: GET /bff/orders (valid session)
    P->>R: GET Orders API, registration=company
    R->>M: authorize(company, principal)
    M->>S: Load authorized client
    S-->>M: AT-1 / RT-1
    opt Access token needs refresh and refresh token exists
        M->>AS: POST token endpoint - refresh_token grant
        AS-->>M: AT-2 / RT-2
        M->>S: Save new authorized client
    end
    M-->>R: Appropriate authorized client
    R->>API: GET /api/orders, Bearer access token
    API-->>R: 401, WWW-Authenticate: Bearer error="invalid_token"
    R->>R: Interpret authorization failure
    R->>S: Failure handler removes authorized client if error qualifies
    R-->>P: Downstream error handled per policy
    P-->>U: Error message or prompt for re-authorization
~~~

This flow has **two distinct failure points**:

- **Before calling the Resource Server:** the manager tries to refresh/issue a token and the Authorization Server returns an error (e.g., `invalid_grant`).
- **After calling the Resource Server:** Orders API rejects the Bearer token (e.g., `invalid_token`).

Both can result in removing the authorized client, yet **error source, interpretation, and where the failure handler attaches differ**.

## 4. Distinguishing Token Endpoint Errors from Resource Server Errors

| Stage | Error Source | Example | Meaning |
|---|---|---|---|
| Initial access token acquisition | Authorization Server token endpoint | `invalid_grant` due to used/expired code | Token exchange did not complete |
| Access token refresh | Token endpoint | `invalid_grant` due to revoked refresh token | Existing authorized client may no longer be refreshable |
| OAuth client authentication | Token endpoint | `invalid_client` | Invalid client secret, mTLS, or client authentication method |
| Calling Orders API | Resource Server | HTTP 401 / Bearer `invalid_token` | Bearer token rejected |
| Calling Orders API | Resource Server | HTTP 403 / Bearer `insufficient_scope` | Token may be valid yet lacks required permissions |
| Calling Orders API | Resource Server or gateway | HTTP 429 | Rate limit; does not prove the token is bad |
| Calling Orders API | Resource Server or gateway | HTTP 500/503, timeout | Infrastructure error; insufficient evidence of invalid token |

**Never use a blanket rule like "delete the authorized client on every HTTP 4xx or 5xx."** That triggers token-issuance loops, overloads the IdP, and can disrupt users who actually hold valid permissions.

### 4.1. HTTP 401 Alone Is Not Enough to Identify Every Cause

A 401 may be caused by:

- Missing Bearer header.
- Malformed/expired/revoked Bearer token.
- Gateway failing to forward the token to the backend.
- Resource Server rejecting the issuer/audience.
- A non-OAuth2 Bearer security filter/endpoint producing 401.

To decide on removing the authorized client, inspect the RFC 6750 **Bearer challenge**, especially the header:

~~~http
WWW-Authenticate: Bearer error="invalid_token"
~~~

An HTTP 401 response **without** corresponding Bearer error details may not give a standard handler enough signal to infer the token should be removed.

### 4.2. HTTP 403 Usually Means Missing Permissions, Not a Broken Token

Example:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope",
                  scope="orders.write"
~~~

The current token may still be valid for `orders.read`, yet lack the `orders.write` scope. **Deleting the token and requesting a new one with the same scopes usually will not solve it**.

The right response is checking consent policies, scopes, tenant rights, and Orders API authorization. Never assume every 403 requires a refresh or logout.

## 5. What Is `OAuth2AuthorizationFailureHandler`'s Role?

On Spring Security Servlet, `OAuth2AuthorizationFailureHandler` is the abstraction for handling OAuth2 Client **authorization failures**.

In short, the handler receives the error details and context needed for post-processing, such as:

- Recording metrics or audits **with sensitive data masked**.
- Removing invalid authorized clients from the repository/service.
- Delegating to retry/re-authorization mechanisms per application policy.

A commonly used implementation:

~~~java
import org.springframework.security.oauth2.client
    .RemoveAuthorizedClientOAuth2AuthorizationFailureHandler;
~~~

`RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` is designed to **remove authorized clients for a qualifying set of OAuth2 errors**. Do not interpret the class name as "delete every token whenever any HTTP request fails."

### 5.1. Two Triggers for Authorization Failure

**Source A — Manager/provider:** the token endpoint rejects authorization or refresh. The manager can invoke a failure handler to remove the stored authorized client upon qualifying errors.

**Source B — RestClient calling a Resource Server:** the downstream API returns a Bearer error indicating the active token is invalid. The interceptor can invoke a failure handler to **remove the authorized client record**, avoiding reusing that token next time.

The difference is that **the manager sees token acquisition**, while **the interceptor sees the Resource Server's response**. The two events must not be conflated into "user login failed."

## 6. Preparing Spring Boot OAuth2 Client on Servlet

### 6.1. Dependencies

Gradle example using Spring Boot dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

`RestClient` is in Spring Framework 6.1+; **`OAuth2ClientHttpRequestInterceptor`** is a Spring Security 6.4+ integration. Check the actual dependencies managed by your Spring Boot BOM. If the application uses an older Spring Security version, such as WebClient Servlet integration, configure the failure handler using that version's API; never copy a class that does not exist yet.

### 6.2. OIDC Client Registration

~~~yaml
# src/main/resources/application.yml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

Environment variables are **placeholders**; never put real secrets into Git or documentation. The provider must be configured with a trusted token endpoint and issuer.

### 6.3. `SecurityFilterChain`

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
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

`oauth2Login()` handles OIDC login. `oauth2Client()` provides OAuth2 Client support in the Servlet security chain. Neither **automatically attaches an authorized-client failure handler to every RestClient** your application builds; HTTP integration must be configured explicitly.

## 7. Creating a Manager for RestClient Token Resolution

When calling Orders API via RestClient, `DefaultOAuth2AuthorizedClientManager` can be used within a Servlet request/response context:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class AuthorizedClientConfig {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientRepository authorizedClients
    ) {
        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations,
                authorizedClients
            );
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

The manager uses:

1. `ClientRegistrationRepository` to resolve registration `company`.
2. `OAuth2AuthorizedClientRepository` to load/save the principal's tokens.
3. The provider chain to pick the corresponding grant.
4. The manager's configured authorization success/failure handling.

**The manager can only refresh when an authorized client and valid refresh token already exist.** It cannot open a browser on its own to re-run the entire Authorization Code Flow from a background request.

In Spring Boot, default beans/integrations may already exist. The code above is an explicit configuration example; projects do not have to declare a custom manager unless customization is needed.

## 8. RestClient Sending Tokens and Handling `invalid_token`

### 8.1. `OAuth2ClientHttpRequestInterceptor`

On Spring Security 6.4+, configure a RestClient integrated with OAuth2 Client:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.web.client.RestClient;

@Configuration
public class OrdersRestClientConfig {

    @Bean
    RestClient ordersRestClient(
        OAuth2AuthorizedClientManager authorizedClientManager
    ) {
        OAuth2ClientHttpRequestInterceptor oauth2 =
            new OAuth2ClientHttpRequestInterceptor(
                authorizedClientManager
            );

        return RestClient.builder()
            .baseUrl("https://orders.example.test")
            .requestInterceptor(oauth2)
            .build();
    }
}
~~~

The interceptor resolves the authorized client via the manager and attaches the access token to the Bearer header per registration and principal when calling the API. Controllers do not need to extract token strings manually and call `headers.setBearerAuth(...)` in every method.

**However**, this only covers **attaching the token**; to handle Bearer errors and remove broken authorized clients, an authorization failure handler must also be configured.

### 8.2. Adding `authorizationFailureHandler`

Using `OAuth2ClientHttpRequestInterceptor`'s own convenience API in Spring Security 6.4+:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.web.client.RestClient;

@Configuration
public class OrdersRestClientFailureConfig {

    @Bean
    RestClient ordersRestClient(
        OAuth2AuthorizedClientManager authorizedClientManager,
        OAuth2AuthorizedClientRepository authorizedClientRepository
    ) {
        OAuth2ClientHttpRequestInterceptor oauth2 =
            new OAuth2ClientHttpRequestInterceptor(
                authorizedClientManager
            );

        oauth2.setAuthorizationFailureHandler(
            OAuth2ClientHttpRequestInterceptor
                .authorizationFailureHandler(
                    authorizedClientRepository
                )
        );

        return RestClient.builder()
            .baseUrl("https://orders.example.test")
            .requestInterceptor(oauth2)
            .build();
    }
}
~~~

**This replaces the RestClient bean in Section 8.1**—do not keep two `@Bean RestClient ordersRestClient` definitions in the same application.

The key piece:

~~~java
oauth2.setAuthorizationFailureHandler(
    OAuth2ClientHttpRequestInterceptor
        .authorizationFailureHandler(authorizedClientRepository)
);
~~~

The handler uses the repository to **remove authorized clients determined to be no longer valid** per Bearer/OAuth2 errors interpreted by Spring Security and default handler policies. Use a repository **matching the manager**, avoiding setups where the manager saves to store A while the failure handler tries deleting from store B.

**Do not infer:** "configuring this handler deletes the token on every HTTP 401/403." The mechanism must identify a **qualifying authorization failure**, such as a Bearer challenge containing `invalid_token`; verify your running Spring Security version's behavior and actual Resource Server responses.

### 8.3. Calling RestClient with an Explicit Registration ID

~~~java
package com.example.portal.web;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

import static org.springframework.security.oauth2.client.web.client
    .RequestAttributeClientRegistrationIdResolver.clientRegistrationId;

@RestController
public class OrdersController {

    private final RestClient ordersRestClient;

    public OrdersController(
        @Qualifier("ordersRestClient") RestClient ordersRestClient
    ) {
        this.ordersRestClient = ordersRestClient;
    }

    @GetMapping("/bff/orders")
    public String listOrders() {
        return ordersRestClient.get()
            .uri("/api/orders")
            .attributes(clientRegistrationId("company"))
            .retrieve()
            .body(String.class);
    }
}
~~~

`clientRegistrationId("company")` helps the interceptor pick the right authorized client. In a logged-in request, Spring Security supplies the `Authentication`; the manager/repository uses that context to find the token.

This is a **server-to-server** HTTP call. The browser never needs to know the Portal's access token. In production, configure the Orders API URL, timeouts, trusted hosts, transport, and error handling properly; never send tokens to user-supplied arbitrary URLs.

## 9. When to Use `OAuth2AuthorizedClientService` Instead of Repository?

On Servlet, two storage mechanisms are common:

| Mechanism | Typical API | Context |
|---|---|---|
| `OAuth2AuthorizedClientRepository` | `loadAuthorizedClient(registrationId, principal, request)`, `removeAuthorizedClient(registrationId, principal, request, response)` | HTTP Servlet request/response |
| `OAuth2AuthorizedClientService` | `loadAuthorizedClient(registrationId, principalName)`, `removeAuthorizedClient(registrationId, principalName)` | Services, tasks without an HTTP request |

A repository may delegate to an underlying service—for example, `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` branching by authenticated principal. Still, do not assume every repository persists to a database.

If the manager uses an **HTTP request repository**, configure the failure handler to delete via the matching repository. If the manager uses **`AuthorizedClientServiceOAuth2AuthorizedClientManager`** for service/background workflows, choose removal via the corresponding authorized-client service.

### 9.1. Example Removal via Service

In business code that has definitively determined an authorized client must be removed:

~~~java
import org.springframework.security.oauth2.client
    .OAuth2AuthorizedClientService;

public final class AuthorizedClientCleanup {

    private final OAuth2AuthorizedClientService authorizedClients;

    public AuthorizedClientCleanup(
        OAuth2AuthorizedClientService authorizedClients
    ) {
        this.authorizedClients = authorizedClients;
    }

    public void removeKnownInvalidClient(
        String registrationId,
        String trustedPrincipalName
    ) {
        authorizedClients.removeAuthorizedClient(
            registrationId,
            trustedPrincipalName
        );
    }
}
~~~

**This is a direct deletion once the server has confirmed an error under a trusted policy**, not an endpoint allowing browsers to delete arbitrary tokens. Never take `trustedPrincipalName` from a client-sent query parameter if that operation could affect someone else's token.

### 9.2. Example Removal via Servlet Repository

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.web
    .OAuth2AuthorizedClientRepository;

void removeForCurrentRequest(
    OAuth2AuthorizedClientRepository repository,
    Authentication authenticatedPrincipal,
    HttpServletRequest servletRequest,
    HttpServletResponse servletResponse
) {
    repository.removeAuthorizedClient(
        "company",
        authenticatedPrincipal,
        servletRequest,
        servletResponse
    );
}
~~~

Here `authenticatedPrincipal` must come from a verified security context. Storage backed by `HttpSession`, a database, or custom stores each has its own contract and side effects. Never call remove for all registrations when only `company`'s token is invalid.

## 10. `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler`

The class name reflects its purpose: remove an authorized client **when the authorization failure belongs to the removal policy**.

A diagram:

~~~text
OAuth2AuthorizationException
    |
    +-- errorCode indicating token/grant is no longer valid
    |      |
    |      +--> RemoveAuthorizedClientOAuth2AuthorizationFailureHandler
    |               |
    |               +--> OAuth2AuthorizedClientRemover
    |                        |
    |                        +--> removeAuthorizedClient(...)
    |
    +-- error without sufficient grounds to remove token
           |
           +--> Not deleted by default or governed by app policy
~~~

Spring Security provides a remover mechanism that can point to the right repository/service. Configuring it via the `OAuth2ClientHttpRequestInterceptor` helper in Section 8 is usually more convenient because the interceptor must also pass the request/response context to the handler.

### 10.1. Which Errors Typically Warrant Removing the Authorized Client?

Errors like `invalid_grant` when a refresh token is rejected, or `invalid_token` when the Resource Server explicitly reports an invalid Bearer token, are typical candidates for removing the unusable record.

However:

- `invalid_client` may be an application credential misconfiguration, which cannot be "fixed" by deleting everyone's tokens.
- `insufficient_scope` means the current grant lacks sufficient permissions; the token may still be valid for other APIs.
- HTTP 429/500/503 or timeouts do not prove the token is bad.
- An HTTP 403 from business authorization does not mean the Bearer token is invalid.

**The exact set of error codes handled by default must be checked for your version**, rather than assuming it expands to all OAuth2 errors. If you need a custom policy, design an explicit error allowlist and tests.

### 10.2. Removing an Authorized Client Does Not Immediately Issue a New Token

After removing `company`'s record:

~~~text
Request A:
  AT-1 rejected by Resource Server
  -> failure handler removes authorized client company/employee-0042
  -> Request A still fails or is handled per error policy

Request B:
  manager finds no existing authorized client
  -> needs a matching grant to obtain a valid token
  -> may require a new browser authorization code flow
~~~

At this point, the **Authorization Code Grant** may require redirecting the user to the IdP/consent; a backend RestClient call cannot complete interactive user steps on its own. Do not "auto-retry Request A with a new token" if the token manager lacks a valid grant and it has not been verified that the HTTP request is safe to retry.

## 11. Manager Handling Authorization Failure When Refresh Token Is Invalid

Another important flow occurs **before RestClient sends the request**:

~~~mermaid
sequenceDiagram
    participant App as Orders Controller
    participant I as RestClient Interceptor
    participant M as Authorized Client Manager
    participant S as Authorized Client Store
    participant AS as Authorization Server

    App->>I: GET Orders API
    I->>M: authorize(company, principal)
    M->>S: Load AT-1 + RT-1
    S-->>M: AT-1 expired, RT-1
    M->>AS: POST /token with RT-1
    AS-->>M: 400 invalid_grant
    M->>M: Authorization failure handling
    M->>S: Remove authorized client if policy matches
    M-->>I: OAuth2 authorization failure
    I-->>App: Failed to obtain valid Bearer token
~~~

In this flow, **Orders API was never called**. If you only configure a failure handler for Resource Server responses without handling refresh/token endpoint failures, the application may keep a record containing a broken RT-1.

`DefaultOAuth2AuthorizedClientManager` has default success/failure handling behaviors for certain cases, such as removing the authorized client upon a qualifying `invalid_grant` OAuth2 error. However, exact behavior depends on the manager type, storage, and version; do not assume every implementation behaves identically or that failure handlers apply automatically to custom managers.

### 11.1. Do Not Equate `invalid_grant` with `invalid_token`

~~~text
invalid_grant:
  Common source -> Authorization Server / token endpoint
  Usually relates to authorization code or refresh token grant

invalid_token:
  Common source -> Resource Server / WWW-Authenticate Bearer
  Usually relates to the Bearer access token currently in use
~~~

Because they arise at two different steps, **where the handler attaches** and **when a new token can be obtained** can differ. An `invalid_grant` error while exchanging the code at initial login does not mean an `OAuth2AuthorizedClient` already exists in the store to delete.

## 12. Not Every 401 Permits Automatic Retries

An anti-pattern:

~~~text
RestClient call
  -> 401
  -> remove authorized client
  -> refresh/re-authorize
  -> retry same request
  -> 401
  -> remove...
  -> infinite loop
~~~

Risks:

- If the API rejects the token due to audience/issuer, issuing a token with the same config will keep failing.
- If the OP does not issue refresh tokens and requires browser consent, the backend cannot complete it alone.
- If the Resource Server returned 401 due to a broken gateway/middleware, deleting the token accomplishes nothing.
- For HTTP POST/PUT/PATCH/DELETE, automatic retries can **duplicate business operations**, especially if the first request partially succeeded on the server before returning an error.
- Simultaneous retries from many requests can overload the Authorization Server.

### 12.1. Controlled Retry Policy

A reasonable policy might:

1. Recognize only explicit Bearer errors, such as `invalid_token`.
2. Remove the authorized client for the exact registration/principal.
3. Distinguish whether the request is safe to retry.
4. Bound reauthorization/retry attempts, typically at most one controlled cycle if permitted by the product.
5. Never retry non-idempotent operations without an **idempotency key** or outcome-verification mechanism.
6. If the browser must be sent to the IdP, return an appropriate interactive prompt instead of silently looping requests.
7. If the API lacks permissions, report 403 or request additional scopes per policy—never treat it as token expiry.

**A failure handler is not a retry engine.** Removing an authorized client only alters state for a future authorization; business HTTP requests and error responses must still be handled separately.

## 13. Login State and Token State Can Diverge

Example timeline:

~~~text
09:00  Browser login succeeds.
       SecurityContext/Session is valid.
       Authorized client = AT-1 + RT-1.

09:05  AT-1 expires per metadata.
       Manager can use RT-1 to obtain AT-2.

09:10  Orders API returns Bearer invalid_token for AT-2.
       Failure handler removes the corresponding authorized client.

09:11  Browser still has a Portal session.
       User is still authenticated at the Portal.
       Yet there is no valid authorized client to call Orders API.

09:12  Application may need re-authorization/consent.
~~~

**Removing an authorized client does not log the user out of the Portal.** The user may still be able to view internal pages that do not call Orders API.

Conversely, when a user logs out of the Portal, the session terminates, yet issued access tokens are **not necessarily** revoked immediately at the Authorization Server. **Local token cleanup** and **remote token revocation** are two different operations.

## 14. When Must the User Be Prompted to Re-Authorize?

Once a token is removed from the local store, the manager has no current authorized client for that registration. Depending on the grant:

| Grant | How Can a New Token Be Obtained? | Requires Browser Interaction? |
|---|---|---|
| `authorization_code` | Start a new authorization flow (with proper state/PKCE/redirect URI) | Usually requires a top-level redirect; may SSO automatically if IdP session remains |
| `refresh_token` | Only if a valid RT remains on the authorized client | No browser needed if AS permits |
| `client_credentials` | Client requests a new token using its own service credentials | No |

If `company`'s token belongs to a user `authorization_code` flow and no refresh token remains, a call to Orders API may need to return an error so the frontend starts a new **authorization flow**. Never turn the application's `client_credentials` into a user-impersonation token just to avoid consent.

If the application stores user permissions/info in a database, it must still check account/tenant status. A successful IdP login does not automatically ensure the user holds the right roles for Orders API.

## 15. Resource Server Returns `insufficient_scope`

Suppose the Portal sends an access token:

~~~text
token scopes = orders.read
~~~

Yet the endpoint requires:

~~~http
DELETE /api/orders/123 HTTP/1.1
Authorization: Bearer <token-with-orders.read>
~~~

Orders API replies:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope",
                  scope="orders.write"
~~~

This is a **Resource Server authorization failure**, not grounds to conclude the token is unusable for everything. The token may still be valid for:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <same-token>
~~~

**Deleting the token purely because of `insufficient_scope`** can force read-only screens to re-authenticate/re-consent, even though the user never had write permissions in the first place.

The application should handle permissions properly:

- Inspect client registration and requested scopes.
- Confirm whether the Authorization Server grants that scope to the user.
- Check business/tenant/resource-ownership policies in Orders API.
- If incremental authorization is supported, trigger the consent flow per policy.
- If the user lacks permission, return 403 and appropriate UI.

Never modify a JWT access token yourself, inject `orders.write` into a header, or switch to another grant to "bypass" API authorization.

## 16. Errors Not Originating from Bearer Authentication

Other responses can also carry HTTP 401 or 403 without being directly related to the OAuth2 access token:

- A proxy enforcing its own Basic Auth layer.
- An endpoint requiring an API key or mTLS that the Portal has not supplied.
- A WAF blocking requests by rule.
- Application business logic returning 403 due to tenant or ownership rules.
- CSRF protection on another Servlet endpoint.
- A gateway returning 401 for an undeclared route.

If you delete authorized clients based solely on **raw status codes**, the application could destroy good tokens over an unrelated failure.

Inspect `WWW-Authenticate` header structure, endpoint type, request path, security filters, and accessible logs.

## 17. Managing Principal and Registration During Removal

An authorized client store may contain:

~~~text
registrationId = company, principalName = employee-0042
registrationId = company, principalName = employee-0099
registrationId = reports-service, principalName = reports-worker
~~~

When `employee-0042`'s AT is rejected by Orders API, cleanup must **target only the affected record**. Never do:

~~~java
// Wrong: deletes company registration records for all users.
deleteAllByRegistrationId("company");
~~~

because the event only proves **one authorized client** has an issue.

### 17.1. Never Trust a Browser-Supplied `principalName`

Dangerous example:

~~~http
DELETE /internal/oauth2/token?principalName=admin HTTP/1.1
~~~

If a controller reads `principalName=admin` and deletes admin's token without authorization checks, someone else can disrupt or manipulate another user's tokens.

For user-authorized tokens, obtain the principal from the `Authentication` verified by Spring Security. For service tokens, use a backend-configured and protected service principal. Token administration APIs must enforce separate authorization and proper auditing.

### 17.2. Email Changes Can Affect Token Storage Keys

Some implementations key storage by `(registrationId, principalName)`. If `principalName` is configured as `email` and the email changes, old records can no longer be found under the new name.

For OIDC, treat identity as **issuer + subject** and avoid using email as a durable technical identifier. When changing `user-name-attribute`, evaluate the impact on the authorized client store and migrations.

## 18. Multiple RestClients or Multiple Registrations

Employee Portal might call:

~~~text
Orders API:  registrationId = company
Reports API: registrationId = reports-service
Partner API: registrationId = partner
~~~

When Orders API returns `invalid_token`, you must not:

- Delete the Reports API token.
- Invalidate all users' sessions.
- Switch to `reports-service`'s token.
- Use the partner token to call Orders API.

**Principle of least privilege:** each RestClient should know its base URL, appropriate registration, and token-sharing rules. Never configure an HTTP interceptor that sends Bearer tokens to any hostname the application might call unless all such hosts sit inside the same trust boundary.

One option is dedicated RestClients per Resource Server:

~~~text
ordersRestClient  -> https://orders.example.test, company
reportsRestClient -> https://reports.example.test, reports-service
partnerRestClient -> https://partner.example.test, partner
~~~

Registration selection must be pinned in backend code/configuration, never taken freely from untrusted input.

## 19. Handling Errors in Controllers and the HTTP Layer

If a RestClient call to a downstream API fails, the application must decide **what response to return to the browser**. Removing the authorized client does not automatically resolve BFF UX or status codes.

Some principles:

1. If the browser has no `Authentication`, the Portal can return 401 JSON or redirect to login depending on the endpoint.
2. If the user is logged in yet lacks downstream scope, the Portal can return an appropriate 403 or prompt for additional authorization.
3. If the token was invalid and cleaned up, the Portal can return a status asking the user to reconnect/re-authorize.
4. If the downstream returned 5xx or timed out, that is an external dependency failure; do not turn it into "login session expired."
5. Never return raw token endpoint error bodies or `WWW-Authenticate` headers containing unnecessary sensitive details to the browser.

### 19.1. Example Controlled REST API Error Mapping

~~~java
package com.example.portal.web;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;

@RestControllerAdvice
public class DownstreamErrorAdvice {

    @ExceptionHandler(HttpClientErrorException.Unauthorized.class)
    ResponseEntity<ApiError> downstreamUnauthorized() {
        return ResponseEntity
            .status(HttpStatus.BAD_GATEWAY)
            .body(new ApiError("ORDERS_AUTHORIZATION_REQUIRED"));
    }

    @ExceptionHandler(HttpClientErrorException.Forbidden.class)
    ResponseEntity<ApiError> downstreamForbidden() {
        return ResponseEntity
            .status(HttpStatus.FORBIDDEN)
            .body(new ApiError("ORDERS_ACCESS_DENIED"));
    }

    @ExceptionHandler(HttpServerErrorException.class)
    ResponseEntity<ApiError> downstreamUnavailable() {
        return ResponseEntity
            .status(HttpStatus.BAD_GATEWAY)
            .body(new ApiError("DOWNSTREAM_UNAVAILABLE"));
    }

    record ApiError(String code) {}
}
~~~

This is a **simple BFF error-mapping example**, not a universal standard policy for every product. If a downstream 401 requires user reauthorization, the application can choose another status/code per the frontend contract; distinguish a **Portal session** 401 from a **downstream API** 401.

**Do not rely on this `ControllerAdvice` to clean up tokens**: cleanup must be configured on the corresponding OAuth2 interceptor/manager. Advice only formats how the application returns errors. Depending on the RestClient version, actual exceptions and response interception may vary; use handlers matching your HTTP client stack.

## 20. Removing an Authorized Client Is Not Remote Token Revocation

Two operations:

~~~text
Local cleanup:
  authorizedClientRepository.removeAuthorizedClient(...)

Remote revocation:
  POST to the Authorization Server's revocation endpoint (if supported)
~~~

**Local cleanup** deletes the token from the store managed by the Portal so future requests stop reusing it. It **does not send a revocation request** to the Authorization Server.

**Remote revocation** asks the Authorization Server to revoke the access token or refresh token via OAuth2 Token Revocation (if supported by the provider). Depending on token type, Resource Servers enforce revocation differently; do not assume all issued JWTs are immediately invalidated by a local operation.

When a user logs out, you may need to:

- Clear `SecurityContext` and HTTP session.
- Delete the authorized client from the local store.
- Call the revocation endpoint to revoke tokens if required by policy and supported by the provider.
- Perform OIDC RP-Initiated Logout or a dedicated SSO logout flow.

These are **four separate responsibilities**. A RestClient failure handler does not replace the full logout/revocation flow.

## 21. Storing Tokens in Multi-Replica Environments

Suppose Portal runs on two nodes:

~~~text
                   +--> Portal A
Browser -> Gateway |
                   +--> Portal B
                          |
                          v
                 Authorized Client Store
~~~

Request A on Node A receives `invalid_token` and deletes the authorized client. Request B on Node B had already loaded the old token prior to deletion and may still send it to the Resource Server.

This raises **concurrency** and **eventual consistency** concerns:

- Is storage shared across nodes?
- Does the repository/service maintain per-node caches?
- If B refreshed the token right before A processed the error, could A accidentally delete the **newer record**?
- Is there a version/generation mechanism or compare-and-delete to protect newer updates?
- Does refresh token rotation cause two concurrent requests to use the same RT-1?

### 21.1. Race Condition Between Concurrent Refresh and Cleanup

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant Store as Token Store
    participant AS as Authorization Server
    participant API as Orders API

    A->>Store: Load old AT-1 / RT-1
    B->>Store: Load old AT-1 / RT-1
    B->>AS: Refresh RT-1
    AS-->>B: New AT-2 / RT-2
    B->>Store: Save AT-2 / RT-2
    A->>API: Send old AT-1
    API-->>A: 401 invalid_token
    A->>Store: Remove authorized client by registration/principal
    Note over Store: Without version checks on delete, newly saved AT-2/RT-2 may be lost
~~~

With default repositories, remove operations typically target the registration/principal key; **they do not necessarily perform compare-and-delete by token generation**. If a product experiences high concurrency and must not lose fresh refresh tokens, design a storage layer/custom handler enforcing version/token-generation consistency.

This is **advanced operational engineering**, not an excuse to ignore `invalid_token` or keep rejected tokens indefinitely.

### 21.2. Shared Storage Must Be Protected

Access tokens and refresh tokens are sensitive credentials. If using JDBC/Redis/shared stores, ensure:

1. Restricted access for services and operators.
2. TLS to storage where applicable.
3. Encryption-at-rest and key management per policy.
4. Never put tokens into audit logs/tracing.
5. Proper TTL/retention/backup and data-deletion workflows.
6. Prevent other applications from reading a principal's tokens without separate authorization.

## 22. Impact of Refresh Token Rotation

In a system supporting refresh token rotation:

~~~text
AT-1 + RT-1
   |
   | POST refresh_token=RT-1
   v
AT-2 + RT-2
   |
   +--> RT-1 may become invalid
~~~

If another request still uses RT-1, the Authorization Server may return `invalid_grant`. Some servers enforce **reuse detection** and may revoke the entire token family.

When encountering `invalid_grant`:

- Do not retry infinitely with the same refresh token.
- Inspect concurrent requests, storage, and persistence of RT-2.
- If the RT is truly invalid, require fresh authorization per the appropriate grant.
- Never substitute client credentials or use another principal's token.

A failure handler deleting broken tokens is only **part of the solution**; under concurrent load, control who refreshes and updates the record.

## 23. Handling Cases Without a Refresh Token

An `OAuth2AuthorizedClient` may hold only an access token:

~~~text
registration = company
principal    = employee-0042
accessToken  = AT-1 (expired/revoked)
refreshToken = null
~~~

Here, the manager **cannot use the `refresh_token` grant** to recover state. After cleanup, the application normally must initiate a new **Authorization Code Flow** if the registration uses interactive login/consent.

Lacking a refresh token can be normal Authorization Server behavior. Requesting the `openid` scope or performing OIDC login does not guarantee a refresh token will be issued.

Never fabricate a refresh token from an ID Token or session cookie. Those credentials serve different purposes and are not interchangeable.

## 24. Background Jobs and `client_credentials`

Suppose the Portal has a scheduled job calling Reports API with the `client_credentials` grant.

It has no browser request/HTTP session. In that case, the appropriate manager is usually:

~~~java
import org.springframework.security.oauth2.client
    .AuthorizedClientServiceOAuth2AuthorizedClientManager;
~~~

paired with `OAuth2AuthorizedClientService` and the `clientCredentials()` provider.

With client credentials, expired access tokens are usually **re-issued via the `client_credentials` grant**, without needing a user refresh token.

If Reports API returns `invalid_token`, cleanup targets the record:

~~~text
registrationId = reports-service
principalName  = reports-worker
~~~

not `company/employee-0042`. A service token failure must never log out employees' browser sessions.

In background jobs, use an appropriate service-based remover/service storage; an HTTP Servlet request/response is not required to delete an authorized client.

## 25. Do Not Compromise Trust Boundaries When Writing Custom Failure Handling

A custom authorization failure handler introduces risks if:

- It trusts a response body from an untrusted server and deletes arbitrary tokens.
- It allows users to choose `clientRegistrationId` and `principalName` freely.
- It receives exceptions from **an HTTP client with no OAuth2 token** and deletes tokens for another registration.
- It writes `WWW-Authenticate`, token values, or client secrets to logs.
- It turns every 403 into "user logged out."
- It automatically retries side-effecting POST requests.

Maintain the invariant:

~~~text
Token rejected by the right Resource Server
        |
        v
Identify the authorized client the interceptor actually used
        |
        v
Handle only error codes within the token-removal policy
        |
        v
Delete the exact registration/principal/context and log a safe event
        |
        v
Never erroneously issue a new token or grant privileges
~~~

**Never use responses from a user-chosen server** to decide on deleting tokens across client registrations. Base URLs and allowed destinations for OAuth2-enabled RestClients must be configured/constrained in the backend.

## 26. Testing: Verifying Tokens Are Removed at the Right Time

You do not need to hit production IdPs or Orders APIs to test behavior. You can use:

- **`MockRestServiceServer`** or a mock HTTP server returning 401/403 responses and Bearer challenges.
- **Mock `OAuth2AuthorizedClientManager`** returning a test authorized client.
- **In-memory `OAuth2AuthorizedClientService`** or fake repository recording remove calls.
- **Spring Security Test** to supply user `Authentication` when testing Servlet request contexts.
- Tests for manager refresh failures using a mock token endpoint.

### 26.1. Core Test Matrix

| Case | HTTP/Token Result | Behavior to Verify |
|---|---|---|
| 200 OK | Valid Bearer token | Authorized client is not removed |
| 401 + Bearer `invalid_token` | Token rejected by Resource Server | Failure handler triggers and removes matching record |
| 401 without clear Bearer error | Error may not be token-related | Do not delete by default if policy lacks evidence |
| 403 + `insufficient_scope` | Missing permissions | Do not treat as revoked token |
| 403 business permission | User lacks resource access | Do not remove token solely for 403 status |
| 429 | Rate limit | Do not delete token on rate limiting |
| 500/503 | API outage | Do not delete token |
| Timeout | Connection failure | Do not delete token purely on timeout |
| Refresh `invalid_grant` | RT broken/invalid | Manager failure handling removes token per policy |
| Refresh timeout | Unknown whether RT was consumed | Never retry blindly or wipe all accounts |
| Two users | One user's token invalid | Never delete another user's token |
| Two registrations | `company` token invalid | Never delete `reports-service`/`partner` |
| Concurrent refresh+remove | New AT just saved | Verify versioning/policy if required |

### 26.2. Test Fixture

Create an authorized client with a dummy token:

~~~java
import java.time.Instant;
import java.util.Set;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AccessToken;

ClientRegistration registration =
    ClientRegistration.withRegistrationId("company")
        .clientId("test-portal")
        .clientSecret("test-secret")
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
            AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationUri("https://login.example.test/authorize")
        .tokenUri("https://login.example.test/token")
        .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
        .build();

Instant now = Instant.now();
OAuth2AccessToken accessToken = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    "TEST_TOKEN_NOT_REAL",
    now.minusSeconds(30),
    now.plusSeconds(300),
    Set.of("orders.read")
);

OAuth2AuthorizedClient authorizedClient =
    new OAuth2AuthorizedClient(
        registration,
        "employee-0042",
        accessToken
    );
~~~

This fixture uses a **dummy** token for mocking the manager/repository. It does not need to be signed by an Authorization Server. A RestClient interceptor test should stub the manager to return this authorized client, simulate an Orders API 401 with:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

and verify the remover targeted `company/employee-0042`. Then test 403 `insufficient_scope` and 500 to ensure tokens are not removed improperly.

### 26.3. Test the Wiring, Not Just Individual Classes

A test that only instantiates `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` and calls it directly verifies the remover logic, yet **does not prove RestClient actually uses that handler**.

Verify the exact `RestClient` injected into services/controllers:

~~~text
RestClient builder
  -> OAuth2ClientHttpRequestInterceptor(manager)
  -> setAuthorizationFailureHandler(repository-backed handler)
  -> /api/orders request with clientRegistrationId(company)
  -> Mock response 401 invalid_token
  -> Repository.removeAuthorizedClient called for exact registration/principal
~~~

If the interceptor is not attached to the right `RestClient` instance, the handler will never run even if a handler bean exists in the Spring context.

### 26.4. Never Use Production Tokens in Tests

Never place real client secrets, refresh tokens, ID Tokens, or cookies into fixtures. When evaluating token endpoint integration, use a mock/isolated Authorization Server, dedicated test credentials, and masked logging.

## 27. Observability and Metrics for Authorized Client Errors

Useful metrics:

| Metric/Event | Meaning |
|---|---|
| `oauth_authorized_client_resolved` | Manager found an authorized client |
| `oauth_refresh_attempted` | Token refresh was attempted |
| `oauth_refresh_failed` | Token endpoint error |
| `oauth_resource_invalid_token` | Resource Server rejected Bearer token |
| `oauth_authorized_client_removed` | Record cleaned up per policy |
| `oauth_reauthorization_required` | New authorization required |
| `oauth_insufficient_scope` | Insufficient scope/permissions |
| `oauth_downstream_unavailable` | 5xx/network failure, not necessarily token-related |

These metrics are **naming suggestions**, not emitted out of the box by Spring Security. When instrumenting, log non-sensitive fields such as allowlisted registration ID, error code, status, duration, trace ID, and outcome.

Avoid logging:

~~~text
access_token=<actual-token>
refresh_token=<actual-token>
client_secret=<actual-secret>
Authorization: Bearer <actual-token>
JSESSIONID=<actual-session>
~~~

Specifically, **token expiry** may not explain every `invalid_token`; inspect Resource Server responses and token lifecycles rather than logging full JWTs for convenience.

## 28. Symptom-Based Troubleshooting

| Symptom | Possible Cause | How to Narrow It Down |
|---|---|---|
| Orders API keeps returning 401 with the same AT-1 | Interceptor lacks failure handler or deletes from wrong store | Check RestClient bean, failure handler, and repository |
| Handler bean exists yet is never called | Not attached to the RestClient used for the API call | Check `setAuthorizationFailureHandler(...)` on the active interceptor |
| Token deleted when API returns 500 | Custom handler deletes on every error | Restrict to qualifying OAuth2/Bearer errors |
| Token deleted yet next request still uses AT-1 | Different store, stale cache, or manager/HTTP client using another instance | Check repo/service, caches, registration/principal |
| Deleting token does not yield a new token | Authorization Code Grant needs browser/consent | Design a reauthorization flow |
| 403 `insufficient_scope` treated as expired token | Relying on HTTP status instead of error code | Separate scope/permissions from invalid tokens |
| Refresh fails with `invalid_grant` | RT expired, revoked, rotation race | Check manager failure handling and token store |
| Fails only when scaled to multiple nodes | Unshared storage or refresh/remove race | Check shared store and versioning |
| Login succeeds yet Orders API returns 401 | Wrong audience/issuer, expired/revoked token | Check token used for that API and `WWW-Authenticate` |
| 401 occurs only behind a proxy | Proxy strips `Authorization` header or enforces another security layer | Inspect gateway HTTP flow; do not blindly delete tokens |
| One user's error drops another user's token | Cleanup keyed by wrong principal | Check trusted `Authentication` and registration/principal binding |
| Reports job fails and logs users out | Mixing service token with user session | Separate managers and failure policies |
| RT remains after logout | Local logout is not remote revocation | Design cleanup/revocation endpoints |
| Token invalid yet UI reports wrong password | Conflating downstream error with login failure | Separate entry point, token manager, and Resource Server |

**Effective investigation approach:** identify whether the failure originated in **authorization request/callback**, **token endpoint**, **RestClient interceptor/manager**, or **Resource Server**. Each layer has different remediation.

## 29. Anti-Patterns to Avoid

**1. Deleting tokens on any 401/403.** HTTP status alone is not sufficient proof that a token is invalid.

**2. Retrying every request infinitely after cleanup.** Especially dangerous for non-idempotent operations.

**3. Logging out users when a downstream API returns `invalid_token`.** One registration's token can break while the Portal session remains valid.

**4. Keeping a rejected token and sending it forever.** Leads to repeated errors and hides the need for reauthorization.

**5. Using a service access token as a substitute for a user.** `client_credentials` does not replace the user's Authorization Code Flow.

**6. Treating local cleanup as remote revocation.** Deleting a database row does not invalidate the Access Token at every API.

**7. Deleting an authorized client using `principalName` from a query parameter.** Can affect other users' data/tokens.

**8. Parsing a JWT and editing its expiration yourself.** You cannot turn an old token into a valid one by altering claims on the client.

**9. Ignoring races between refresh and remove.** Key-based deletion can wipe out a newer token record.

**10. Attaching a handler only on the manager while ignoring Resource Server Bearer errors.** Both failure sources need proper integration points.

**11. Enabling wire logging containing tokens to debug.** Access/refresh tokens and client secrets must be protected.

## 30. Scenario Exercises

### Exercise 1 — `401 invalid_token`

Orders API returns:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

**Question:** What should happen to the authorized client used to call the API?

**Hint:** Use the corresponding failure handler to remove the `company` authorized client for the right principal if policy confirms the token is invalid. Then return an error or trigger appropriate reauthorization—do not log out the entire Portal.

### Exercise 2 — `403 insufficient_scope`

The token has `orders.read`, while Orders API requires `orders.write` and returns:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

**Question:** Will deleting the token and refreshing with the same scope solve this?

**Hint:** Usually no. The token may be valid yet lack permissions; check scopes/consent and API authorization.

### Exercise 3 — Manager Saves a New Token, Handler Still Deletes the Old Record

Two concurrent requests: B just saved AT-2 after a refresh, while A receives a 401 for AT-1 and deletes by registration/principal.

**Question:** What is the risk?

**Hint:** A can delete the newly saved AT-2 if storage does not check versions. Consider token-generation/versioned removal in high-concurrency environments.

### Exercise 4 — HTTP 500

Orders API returns 503 during backend maintenance.

**Question:** Should you automatically delete the authorized client?

**Hint:** No; 503 does not prove the token is invalid. Handle infrastructure errors with controlled backoff/retries and appropriate messages.

### Exercise 5 — Portal Logout

The user logs out and the Portal session is destroyed, yet RT-1 remains in the persistent authorized-client service.

**Question:** Can you conclude RT-1 was revoked at the IdP?

**Hint:** No. Local sessions, local token cleanup, and remote revocation are separate mechanisms.

### Exercise 6 — Handler Not Attached

The application declares a `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` bean, yet the RestClient interceptor only receives the manager.

**Question:** Why does the API keep receiving the invalid token repeatedly?

**Hint:** Having a bean in the context does not mean the interceptor uses it. Attach the handler with `setAuthorizationFailureHandler(...)` on the exact OAuth2 interceptor inside the RestClient bean.

### Exercise 7 — Token Endpoint `invalid_grant`

The manager tries to refresh RT-1, yet the Authorization Server returns `invalid_grant`. Orders API was never called.

**Question:** Does the Resource Server's failure handler handle this case?

**Hint:** Not directly. The failure occurred inside the manager/token provider; handle authorization failures at the manager and clean up the authorized client per policy.

## 31. Implementation Checklist

| Question | What to Verify |
|---|---|
| Using Spring Security 6.4+? | If using the RestClient OAuth2 interceptor, the class/API must exist |
| Servlet or WebFlux? | This lesson uses `HttpSecurity`, Servlet repositories, and RestClient |
| Did RestClient receive the right manager? | Has `OAuth2ClientHttpRequestInterceptor(manager)` |
| Is the failure handler attached to the interceptor? | Has appropriate `setAuthorizationFailureHandler(...)` |
| Where does the handler delete from? | The same repository/service where the manager saves authorized clients |
| Are registration and principal accurate? | Obtained from trusted request/service context |
| What Bearer error did the Resource Server return? | Distinguish `invalid_token`, `insufficient_scope`, and statuses without a challenge |
| How does the manager handle refresh `invalid_grant`? | Failure handler/cleanup on the token endpoint path |
| After cleanup, what is the reauthorization path? | User interaction, consent, or valid `client_credentials`? |
| Are retries bounded? | No infinite retries; watch non-idempotent methods |
| Multi-replica deployment? | Shared store, caching, refresh/remove races, and versioning |
| Does logout require remote revocation? | Clear policy, not confused with local cleanup |
| Using the right access token for the Resource Server? | Matching audience, scope, issuer, and registration |
| Tested 401/403/500/refresh failures? | Verify exact record removed without false deletions |
| Login state separated from token state? | Never unconditionally log users out on API errors |
| Does logging avoid credentials? | Never log AT/RT, client secrets, codes, or cookies |

## 32. Summary

In **Spring Security OAuth 2.0/OIDC Client on Servlet**, handling authorization failures is not just catching HTTP 401 and retrying. A request via **RestClient** can fail in two places: at the **Authorization Server/token endpoint** when issuing or refreshing tokens, and at the **Resource Server** when validating the Bearer token. Distinguish errors like `invalid_grant`, `invalid_token`, and `insufficient_scope`, alongside HTTP 5xx, timeouts, and business errors.

With **Spring Security 6.4+**, `OAuth2ClientHttpRequestInterceptor` connects `RestClient` to `OAuth2AuthorizedClientManager`. Adding an `OAuth2AuthorizationFailureHandler`—commonly via `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` and a matching repository/service—helps **remove authorized clients determined to be no longer valid**, preventing continued reuse of stale tokens. Still, this operation **does not automatically log users out, revoke tokens at the IdP, or automatically issue a new token for every grant**.

A reliable design **deletes only the exact registration/principal**, acts only on errors with clear evidence, keeps **retries bounded**, avoids stripping valid permissions on `insufficient_scope` or 5xx, and controls concurrency during simultaneous refreshes or rotations. Combining **manager + RestClient interceptor + failure handler + authorized-client store + reauthorization policy** with proper boundaries lets the Portal recover cleanly from token errors while protecting user sessions and data.
