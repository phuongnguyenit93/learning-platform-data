# 15.8. Authorization Success Handler and Saving the Authorized Client

## 1. Problem Statement: Once a Token Is Issued Successfully, Who Saves It?

In a **Spring Security OAuth 2.0 OIDC Client** application, after a user logs in or a backend service obtains an Access Token, the application usually needs to **reuse the token** in subsequent API calls. When the token approaches expiration, the client may need to use a Refresh Token or another grant to obtain a new token and update the stored record.

Spring Security addresses this need with three groups of components:

- **`OAuth2AuthorizedClient`**: represents a client registration authorized for a principal, holding an Access Token and optionally a Refresh Token.
- **`OAuth2AuthorizedClientManager`**: orchestrates looking up the existing authorized client, executing the appropriate grant, and handling the authorization result.
- **`OAuth2AuthorizationSuccessHandler`**: callback invoked by the client manager **after a provider completes a successful authorization**, typically to **save/update** the new `OAuth2AuthorizedClient` in a repository or service.

For example, a reporting system uses `client_credentials` to call an internal API. The first time, the manager obtains the token and saves it. Subsequent calls can reuse the stored token; when the token expires, the manager obtains a new token and updates the record. If you replace the default success handler with a handler that only logs, the application can accidentally **stop persisting new tokens** and keep re-requesting tokens continuously.

> **Lesson objective:** distinguish the authorization success handler from the login success handler, trace the path of an authorized client through the manager, configure the default persistence mechanism, and customize properly without breaking persistence or leaking tokens.

## 2. Two “Success Handlers” with Similar Names but Different Responsibilities

This is an easy point of confusion when working with OAuth2 Login and OAuth2 Client:

| Criterion | `OAuth2AuthorizationSuccessHandler` | `AuthenticationSuccessHandler` |
| --- | --- | --- |
| Context | **`OAuth2AuthorizedClientManager`** performing authorization/re-authorization | **Spring Security authentication filter**, such as OAuth2 Login |
| Invoked when | `OAuth2AuthorizedClientProvider` returns a new authorized client from a successful authorization | A user is successfully authenticated during the login flow |
| Key parameters | `OAuth2AuthorizedClient`, `Authentication`, `Map<String,Object> attributes` | `HttpServletRequest`, `HttpServletResponse`, `Authentication` |
| Typical default goal | Save/update the authorized client in storage | Navigate the browser, e.g., redirect back to a saved request |
| Effect on HTTP response | Does not necessarily have a response; service manager can run outside Servlet | Typically determines the redirect/HTTP response for the browser |
| Can it be used in a scheduled job? | Yes, via the appropriate client manager/service | Not an option for background token authorization |
| Configuration point | `manager.setAuthorizationSuccessHandler(...)` | `http.oauth2Login(...).successHandler(...)` |

**`OAuth2AuthorizationSuccessHandler` is not an HTTP login success handler.** Conversely, when a user logs in via OIDC and the browser redirects to the home page, that redirect does not prove that the manager's custom authorization success handler ran.

### 2.1. Interface Names and Packages

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizationSuccessHandler;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
~~~

An application can use **both**:

~~~text
OAuth2/OIDC Login succeeds
  -> Spring Security creates Authentication
  -> OAuth2 Login saves authorized client as part of login flow
  -> AuthenticationSuccessHandler decides where the browser goes next

OAuth2AuthorizedClientManager needs to obtain/refresh Access Token
  -> OAuth2AuthorizedClientProvider executes grant successfully
  -> OAuth2AuthorizationSuccessHandler saves/updates authorized client
  -> manager returns OAuth2AuthorizedClient to API-calling code
~~~

Do not configure `oauth2Login().successHandler(...)` with the sole purpose of “saving Refresh Tokens whenever the manager refreshes”. The HTTP login handler is not invoked on every refresh.

## 3. What Data Does an Authorized Client Contain?

An `OAuth2AuthorizedClient` has these core components:

| Property | Meaning |
| --- | --- |
| `ClientRegistration` | OAuth2/OIDC client and provider configuration, including `registrationId` |
| `principalName` | Logical identity used to associate the authorization record |
| `OAuth2AccessToken` | Current token, token type, scopes, and issued/expiration timestamps |
| `OAuth2RefreshToken` | Refresh Token if issued and the client needs to store it |

Conceptual illustration:

~~~text
OAuth2AuthorizedClient
  clientRegistration.registrationId = "calendar"
  principalName = "employee-123"
  accessToken = <sensitive credential>
  refreshToken = <sensitive credential, optional>
~~~

**An authorized client record is not an OIDC ID Token.** The ID Token proves OIDC identity authentication; Access Tokens/Refresh Tokens are used to call resources and obtain new tokens. Never send an ID Token in place of an Access Token to an API.

### 3.1. Registration ID Is Different from Principal Name

One `calendar` registration can have authorized clients for many people:

~~~text
("calendar", "employee-123") -> token for employee-123
("calendar", "employee-456") -> token for employee-456
~~~

Never use **registration ID as the sole key** for all users. With OIDC, durable identity relies on **issuer + subject**; in multi-issuer/multi-tenant systems, design an appropriate principal namespace to avoid key collisions.

With `client_credentials`, the principal name is typically a fixed service identifier like `system-reports`, with no end-user. Never attach a Client Credentials token to a logged-in user's account.

### 3.2. What Data Is Updated After a Refresh?

When refresh succeeds:

- The Access Token may be replaced with a new value, new expiration, and granted scopes.
- The Refresh Token may be **rotated** (provider returns a new token), or left unreplaced depending on grant/response.
- The new record must be persisted under the **exact registration and principal**.

Never modify raw tokens via string manipulation or write an Access Token received from the browser into storage. A new authorized client must come from a valid OAuth2 flow through a trusted provider/client.

## 4. When Is the Authorization Success Handler Called?

### 4.1. Orchestration Flow Through `OAuth2AuthorizedClientManager`

~~~mermaid
sequenceDiagram
    autonumber
    participant App as API-Calling Code
    participant M as OAuth2AuthorizedClientManager
    participant S as Authorized Client Store
    participant P as OAuth2AuthorizedClientProvider
    participant AS as Authorization Server
    participant H as OAuth2AuthorizationSuccessHandler
    App->>M: authorize(registrationId, principal)
    M->>S: load existing authorized client
    S-->>M: Old client or null
    M->>P: authorize(context, existing client)
    alt Provider needs to issue/refresh and succeeds
        P->>AS: Grant request to Token Endpoint
        AS-->>P: Successful token response
        P-->>M: New OAuth2AuthorizedClient
        M->>H: onAuthorizationSuccess(client, principal, attributes)
        H->>S: save/update authorized client
        S-->>H: Save complete
        M-->>App: New authorized client
    else No re-authorization needed
        P-->>M: Does not create new authorized client
        M-->>App: Existing client, if any
        Note over H: Success handler is normally not called
    end
~~~

This is a **logical model**. Fallback mechanisms, HTTP request context resolution, and behavior when authorization cannot proceed depend on the manager/provider type and actual grant.

One critical point: **the success handler is not guaranteed to run on every `manager.authorize(...)` call**. If an Access Token is being reused and the provider performs no re-authorization, the manager can return the existing authorized client without invoking the handler.

That is why you should not use the success handler to count **every time an API uses a token**. The handler is suited for observing **successful token issuance/update events**.

### 4.2. The `OAuth2AuthorizationSuccessHandler` Interface

The interface has one method:

~~~java
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;

void onAuthorizationSuccess(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal,
    Map<String, Object> attributes
);
~~~

Where:

- `authorizedClient`: the object just successfully authorized by the provider/manager.
- `principal`: the authentication/principal context used to determine record ownership.
- `attributes`: authorization context metadata passed by the manager; may include Servlet data in the corresponding manager.

**The `attributes` map is not a place for arbitrary user-controlled data.** Never take a principal name or redirect target from an unverified query parameter to save a token into another account.

### 4.3. Authorization Success Differs from OAuth2 Login Success

In OAuth2 Login, `OAuth2LoginAuthenticationFilter` and the repository integrate to handle the login callback; saving the authorized client is part of the login flow managed by Spring Security. A successful login may have already saved the Access Token before `AuthenticationSuccessHandler` redirects the browser.

Later, when application code calls `OAuth2AuthorizedClientManager.authorize(...)` to refresh a token, that is **a new token lifecycle step**. When issuance/refresh succeeds, the manager calls its `OAuth2AuthorizationSuccessHandler`.

Avoid blindly calling `saveAuthorizedClient` in the login success handler, controller, manager success handler, and client API all at once without a clear design; it is very easy to overwrite a newer token with an older one or save under a mismatched principal.

## 5. Two Common Managers and Default Success Handlers

Spring Security provides two common managers for different contexts.

| Component | Context | Storage | Default Success Behavior |
| --- | --- | --- | --- |
| `DefaultOAuth2AuthorizedClientManager` | Inside a Servlet HTTP request | `OAuth2AuthorizedClientRepository` | **Saves the authorized client** via the supplied repository |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | Outside a Servlet request, e.g., service/job | `OAuth2AuthorizedClientService` | **Saves the authorized client** via the supplied service |

**Because the default handlers already persist tokens, most applications do not need to write a custom authorization success handler.** Without special auditing or integration requirements, keeping the default is usually the safest and simplest choice.

### 5.1. `DefaultOAuth2AuthorizedClientManager`

The Servlet manager constructor takes:

~~~java
DefaultOAuth2AuthorizedClientManager manager =
    new DefaultOAuth2AuthorizedClientManager(
        clientRegistrationRepository,
        authorizedClientRepository
    );
~~~

These variables are dependencies supplied by the application/Spring Boot. The manager uses the repository to load existing state and by default uses an authorization success handler to **save** the result when the authorization provider creates a new client.

### 5.2. `AuthorizedClientServiceOAuth2AuthorizedClientManager`

~~~java
AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
    new AuthorizedClientServiceOAuth2AuthorizedClientManager(
        clientRegistrationRepository,
        authorizedClientService
    );
~~~

This manager works with a service, requiring neither `HttpServletRequest` nor `HttpServletResponse`. Hence it fits Client Credentials, scheduled tasks, or backend workflows with an appropriate principal context.

### 5.3. How Do Repository and Service Differ?

| API | Conceptual Signature | Fit |
| --- | --- | --- |
| `OAuth2AuthorizedClientRepository.saveAuthorizedClient(...)` | Authorized client + Authentication + Servlet request/response | Web integration, sessions, and browser-context repositories |
| `OAuth2AuthorizedClientService.saveAuthorizedClient(...)` | Authorized client + principal name | Non-Servlet storage, in-memory or JDBC |

A repository can be implemented as an adapter delegating to a service for authenticated principals, such as `AuthenticatedPrincipalOAuth2AuthorizedClientRepository`. Therefore, do not assume “repository only stores in session” or “service always uses a database”.

## 6. Sample Configuration for Servlet OAuth2/OIDC Client

### 6.1. Dependencies

For Spring Boot 3.x with Servlet/MVC:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

In Spring Boot 4.x, starter names are modularized accordingly, such as `spring-boot-starter-webmvc` and `spring-boot-starter-security-oauth2-client`. Pick the exact dependencies from the Spring Boot BOM; do not mix Spring Security versions just because an example uses a different API.

### 6.2. OIDC Registration Configuration

Example `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-provider
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-provider:
            issuer-uri: https://id.example.com/realms/company
~~~

URLs and client IDs are illustrative only. In real applications, issuer and redirect URI must match the registered OP settings; secrets come from a secret manager or environment variables, never committed to the repository.

### 6.3. Enabling OAuth2 Login and OAuth2 Client

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
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

With standard configuration, Spring Security already integrates saving the authorized client after OAuth2 Login. You do not need to write an `AuthenticationSuccessHandler` just to copy the Access Token into the HTTP session.

`oauth2Client()` enables OAuth2 Client integration in Servlet apps. To refresh tokens or request tokens with a specific grant, configure `AuthorizedClientManager` and `AuthorizedClientProvider` properly.

## 7. Example 1: Default Manager Automatically Saving Authorized Clients in Servlet

This is an **explicit configuration** example, useful when you want to control grant types. No custom success handler is installed because the manager's default already handles saving.

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class ServletClientManagerConfig {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        // DO NOT call setAuthorizationSuccessHandler here:
        // by default the manager saves the authorized client via repository.
        return manager;
    }
}
~~~

When the manager refreshes successfully, the new authorized client is saved in the repository matching the call's `Authentication` and Servlet context. If you only want Spring Security's default behavior, you do not even need to define this manager bean unless the application wants to actively configure providers/grants.

**Do not enable `clientCredentials()` in a web manager just because “it gives a new token”.** That grant is for clients/services, not user logins. Enable it only if the app truly has client registrations needing Client Credentials with a separate identity namespace designed.

### 7.1. Calling the Manager from a Service Inside a Servlet Request

Example snippet using the manager:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("company")
        .principal(authentication)
        .build();

OAuth2AuthorizedClient authorizedClient =
    authorizedClientManager.authorize(request);

if (authorizedClient == null) {
    // No suitable authorized client in the current context.
    // Do not call the API without a valid Access Token.
}
~~~

The `authentication` and `authorizedClientManager` variables are assumed to be injected or retrieved from server-side context, not built from arbitrary browser parameters.

With `DefaultOAuth2AuthorizedClientManager`, the call needs an appropriate **Servlet request/response context** (or properly populated attributes) for the repository to operate. This is not the manager for a scheduled job running without an HTTP request.

### 7.2. Reading the Result After the Manager Authorizes

~~~java
if (authorizedClient != null) {
    String registrationId = authorizedClient.getClientRegistration()
        .getRegistrationId();
    boolean hasRefreshToken = authorizedClient.getRefreshToken() != null;
    // Only use the token on the backend to call permitted APIs.
    // Never log or send getTokenValue() to the browser.
}
~~~

Never expose token values, Refresh Tokens, or the entire `OAuth2AuthorizedClient` in HTML, JSON responses, or application logs.

## 8. Example 2: Service-Based Manager for Tasks Without a Servlet Request

Suppose a backend worker needs to call a reporting API using **Client Credentials**. There is no browser, no HTTP login, and no end user.

Configure the OAuth2 client registration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reporting-service:
            provider: reporting-provider
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          reporting-provider:
            token-uri: https://auth.example.net/oauth2/token
~~~

Create `AuthorizedClientServiceOAuth2AuthorizedClientManager`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class ServiceClientManagerConfig {

    @Bean
    AuthorizedClientServiceOAuth2AuthorizedClientManager
            reportingClientManager(
                    ClientRegistrationRepository registrations,
                    OAuth2AuthorizedClientService service) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, service);
        manager.setAuthorizedClientProvider(provider);
        // On success: manager saves via service by default.
        return manager;
    }
}
~~~

For Client Credentials, the manager can obtain an Access Token and save it under the application-supplied principal key. Next time, the manager can load the still-valid token instead of always requesting a new one.

Example invocation:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;

OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("reporting-service")
        .principal("system-reporting-job")
        .build();

OAuth2AuthorizedClient client = reportingClientManager.authorize(request);
if (client == null) {
    throw new IllegalStateException("Could not authorize token for reporting-service");
}

// API client uses client.getAccessToken() on the backend.
~~~

This snippet illustrates the usage pattern, with `reportingClientManager` dependency-injected in the calling class. The `system-reporting-job` identifier is the **principal name in the service's token store**, not an OIDC user account.

**Do not use `AuthenticationSuccessHandler`** for Client Credentials: there is no browser login to redirect.

## 9. When Do You Need to Define a Custom `OAuth2AuthorizationSuccessHandler`?

Keeping the default handler is sufficient for ordinary token save/update needs. A custom success handler is appropriate when the application wants to add one or more tasks **after authorization succeeds**:

1. Record an audit event **containing no tokens**.
2. Update business metadata such as a “connected” status for the exact registration/principal.
3. Measure how many times tokens are reissued, distinct from how many times APIs use tokens.
4. Persist to a custom-designed store or control persistence/transactions.
5. Run a controlled integration hook after the new token has been saved.

**Biggest risk:** `setAuthorizationSuccessHandler(...)` typically **replaces** the default success handler. If a custom handler only logs and omits saving the authorized client, newly issued authorizations will not be persisted.

### 9.1. Example of What Not to Do

~~~java
// ANTI-PATTERN: replacing the default persistence handler with a log-only handler.
manager.setAuthorizationSuccessHandler(
    (authorizedClient, principal, attributes) -> {
        System.out.println("OAuth2 authorization succeeded");
        // Does not save the authorized client!
    });
~~~

Consequences:

- The new Access Token exists only in the return value of the current `authorize()` call.
- The next request may load an old/expired token, or find no record.
- With token rotation, the new Refresh Token is not saved, causing the next refresh to fail.
- The system may keep requesting new Access Tokens continuously, placing unnecessary load on the Token Endpoint.

If you replace the handler, **preserve the persistence responsibility** or explicitly delegate to a handler that performs the save.

### 9.2. Custom Handler Pattern for Service Manager: Save First, Audit Second

With a manager using `OAuth2AuthorizedClientService`, you can write a clear handler without needing Servlet context:

~~~java
package com.example.security;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizationSuccessHandler;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class AuditedServiceClientManagerConfig {

    private static final Logger log =
        LoggerFactory.getLogger(AuditedServiceClientManagerConfig.class);

    @Bean
    AuthorizedClientServiceOAuth2AuthorizedClientManager
            auditedServiceClientManager(
                    ClientRegistrationRepository registrations,
                    OAuth2AuthorizedClientService service) {

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, service);

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .refreshToken()
                .build();
        manager.setAuthorizedClientProvider(provider);

        OAuth2AuthorizationSuccessHandler persistThenAudit =
            (authorizedClient, principal, attributes) -> {
                // Do not skip persistence when replacing the success handler.
                service.saveAuthorizedClient(
                    authorizedClient, principal.getName());

                // Only log non-sensitive metadata.
                log.info(
                    "OAuth2 authorized client saved; registrationId={}",
                    authorizedClient.getClientRegistration().getRegistrationId()
                );
            };

        manager.setAuthorizationSuccessHandler(persistThenAudit);
        return manager;
    }
}
~~~

Here:

- `service.saveAuthorizedClient(...)` writes the new authorized client under the exact principal key.
- `log.info(...)` **never logs** Access Tokens, Refresh Tokens, emails, subjects, HTTP responses, or the full client object.
- The handler is attached to the **service manager**; there is no need to read Servlet request/response from `attributes`.
- Calls that do not issue/refresh a new token may bypass the handler, so this logs **successful token issuances**, not all API calls.

The `@Bean` examples in earlier sections are **alternative configurations**. Do not copy all manager beans of the same type into one application expecting Spring Boot to pick the right bean automatically. If deploying multiple managers, assign distinct names and `@Qualifier` annotations or inject the exact bean per workflow.

### 9.3. Order of Saving and Auditing

A sensible order in the example:

~~~text
Provider issues new token successfully
  -> validate/build OAuth2AuthorizedClient
  -> service.saveAuthorizedClient(...)
  -> audit safe metadata
  -> manager returns authorized client
~~~

If **saving fails**, code should not emit a “persisted successfully” event. If **auditing fails after saving**, define an explicit policy:

- For optional audits: offload to an observability pipeline with retry/buffering so it does not break token issuance.
- For compliance-required audits: design a transactional outbox or appropriate consistency mechanism; never assume saving a token and sending a network audit event are an atomic transaction.
- Never let a logging failure accidentally cause the client manager to retry repeatedly and mint extra unnecessary tokens.

A custom handler does not automatically guarantee atomicity between the database and an external event system.

## 10. Custom Success Handler in Servlet: Preserving the Request Context

For `DefaultOAuth2AuthorizedClientManager`, the default success handler persists through **`OAuth2AuthorizedClientRepository`**. The repository has the signature:

~~~java
void saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal,
    HttpServletRequest request,
    HttpServletResponse response
);
~~~

Because HTTP request/response are required, a custom handler on a Servlet manager is more involved than on a service manager:

~~~text
DefaultOAuth2AuthorizedClientManager
  -> context / attributes holding data for the Servlet request
  -> OAuth2AuthorizationSuccessHandler
  -> authorizedClientRepository.saveAuthorizedClient(
         authorizedClient, principal, request, response
     )
~~~

If you need to add auditing in a Servlet manager, prefer:

- Keeping the default handler and putting auditing inside a **repository decorator** implementing `saveAuthorizedClient(...)`, or
- Creating a custom handler capable of obtaining the exact Servlet request/response from the manager context and delegating full save behavior, per the **exact API of your Spring Security version**.

**Never fabricate fake `HttpServletRequest`/`HttpServletResponse` objects** and never attach a token to a different session. How Spring Security passes request context through authorization attributes may need to be checked against Javadoc/version before implementing custom handlers.

### 10.1. Repository Decorator Pattern to Preserve Persistence

Illustrative code for a wrapper that only adds audit metadata after saving, without managing token lifecycles itself:

~~~java
package com.example.security;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

public final class AuditingAuthorizedClientRepository
        implements OAuth2AuthorizedClientRepository {

    private static final Logger log =
        LoggerFactory.getLogger(AuditingAuthorizedClientRepository.class);

    private final OAuth2AuthorizedClientRepository delegate;

    public AuditingAuthorizedClientRepository(
            OAuth2AuthorizedClientRepository delegate) {
        this.delegate = delegate;
    }

    @Override
    public <T extends OAuth2AuthorizedClient> T loadAuthorizedClient(
            String registrationId,
            Authentication principal,
            HttpServletRequest request) {
        return delegate.loadAuthorizedClient(
            registrationId, principal, request);
    }

    @Override
    public void saveAuthorizedClient(
            OAuth2AuthorizedClient authorizedClient,
            Authentication principal,
            HttpServletRequest request,
            HttpServletResponse response) {

        delegate.saveAuthorizedClient(
            authorizedClient, principal, request, response);

        log.info("Authorized client stored; registration={}",
            authorizedClient.getClientRegistration().getRegistrationId());
    }

    @Override
    public void removeAuthorizedClient(
            String registrationId,
            Authentication principal,
            HttpServletRequest request,
            HttpServletResponse response) {
        delegate.removeAuthorizedClient(
            registrationId, principal, request, response);
    }
}
~~~

This is a **wrapper illustrating separation of responsibilities**. In a real application, configure it as the repository actually used by both the manager and login flow, avoiding circular bean injection/delegation, and ensuring logging failures do not block saves.

Advantage of delegation: the component responsible for persisting tokens **remains intact**, while auditing sits at the save boundary. If the application also needs to audit updates via a service/JDBC outside Servlet requests, attach observability at the corresponding storage layer; a Servlet wrapper will not observe every service-manager save.

### 10.2. Do Not Use a Login Success Handler to Record Refresh Tokens

If the application has:

~~~java
.oauth2Login(login -> login
    .successHandler(myLoginSuccessHandler))
~~~

that handler serves successful HTTP logins. It is not a reliable hook for subsequent Refresh Token grants.

When the goal is **post-login navigation**, use `AuthenticationSuccessHandler`. When the goal is **saving a new authorized client issued/refreshed by the manager**, use the manager's default success handler or a custom `OAuth2AuthorizationSuccessHandler` with explicit persistence delegation.

## 11. How Does `AuthorizedClientManager` Decide When to Refresh?

The manager coordinates with `OAuth2AuthorizedClientProvider` to determine which grants apply:

| Provider / Grant | When Involved? | Authorized Client After Success |
| --- | --- | --- |
| `authorization_code` | User grants consent via browser/redirect | User's Access Token and possibly Refresh Token |
| `refresh_token` | Existing authorized client has a Refresh Token and needs a new Access Token | New token; possibly a rotated Refresh Token |
| `client_credentials` | Backend requests a token as the client/service | Service's Access Token |
| Extension grants | When supported by system and provider, custom configured | Result depends on grant and contract |

Example state progression:

~~~text
Authorized client in store:
  registration=calendar
  principal=employee-123
  accessToken.expiresAt=10:00
  refreshToken=available

At 09:55:
  manager.authorize(...)
  -> Can reuse client, no refresh needed.

At 10:01:
  manager.authorize(...)
  -> Refresh Token provider can request a new Access Token.
  -> On success: authorization success handler saves the new client.
~~~

Actual timing may incorporate **clock skew** and custom policies, rather than always comparing strictly to the second. Do not write your own refresh policy with `token.getExpiresAt().isBefore(now)` and bypass the manager if the framework already covers your needs.

### 11.1. When the Manager Does Not Create a New Authorized Client

If the token is still valid, the provider can return `null` to signal **no re-authorization is needed**, and the manager can return the existing authorized client. In that situation, the success handler is normally **not invoked**.

If the client has never been authorized and no grant can run in the current context, the manager may return `null` or trigger an appropriate authorization initiation path depending on provider/grant. Never conclude that every `null` means the token was revoked.

### 11.2. Refresh Token Rotation

A Token Endpoint might return:

~~~json
{
  "access_token": "NEW_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 300,
  "refresh_token": "NEW_REFRESH_TOKEN",
  "scope": "calendar.read"
}
~~~

If the provider rotates Refresh Tokens, the handler must ensure the new record is saved. Otherwise:

1. The first refresh succeeds, yet the new token is not saved.
2. Next time, the manager reads the old record holding the already-replaced Refresh Token.
3. The Token Endpoint may return `invalid_grant`.
4. The application loses the ability to call the API and must ask the user to authorize again.

This is one of the primary reasons a **log-only custom success handler** causes production failures that are hard to spot immediately.

## 12. Where Is Data Stored: Session, Memory, or JDBC?

The success handler only triggers saving; **where** data is stored depends on the repository/service.

| Implementation | Characteristics | Suitable Cases |
| --- | --- | --- |
| `HttpSessionOAuth2AuthorizedClientRepository` | Organizes storage tied to the HTTP session | Simple web flows where state lives with the session |
| `InMemoryOAuth2AuthorizedClientService` | Stores in process memory | Demos, development, or services that do not need to survive restarts |
| `JdbcOAuth2AuthorizedClientService` | Persists via JDBC into a database | Multiple instances, long-lived persistence requirements |
| `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` | Delegates to service for authenticated principals; falls back for anonymous | Bridge between Servlet repository and service |
| Custom repository/service | Stores in a custom backend with TTL/atomicity rules | Special infrastructure/compliance requirements |

**Saving via a repository does not automatically mean saving in the session**, because the repository may delegate down to a service/JDBC.

### 12.1. Example JDBC `AuthorizedClientService`

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class AuthorizedClientStoreConfig {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            JdbcTemplate jdbcTemplate,
            ClientRegistrationRepository registrations) {

        return new JdbcOAuth2AuthorizedClientService(
            jdbcTemplate, registrations);
    }
}
~~~

You need a `DataSource`, Spring JDBC, and a **database schema compatible with your Spring Security version** before running. This bean illustrates storage; Spring Boot may already auto-configure a service/repository, so avoid duplicate declarations.

When `AuthorizedClientServiceOAuth2AuthorizedClientManager` uses this service, the manager's default handler writes the new token set into JDBC after successful authorization.

### 12.2. Tokens Are Secret Data

A JDBC authorized client record may store:

~~~text
registration_id / principal_name
access_token_value
access_token_issued_at
access_token_expires_at
access_token_scopes
refresh_token_value
refresh_token_issued_at
~~~

This is an illustrative data model, not a replacement for official DDL. Access Tokens and Refresh Tokens must be protected like **credentials**:

- Restrict database read/write/delete permissions per least privilege.
- Encrypt sensitive data as needed and manage encryption keys safely.
- Never allow raw tokens to appear in SQL logs, APM traces, dumps, or unprotected backups.
- Establish retention policies, deletion on disconnect, and proper recovery procedures.
- Control concurrency when multiple instances refresh the same authorized client simultaneously.

**Never log the entire `OAuth2AuthorizedClient` just to observe the success handler.**

## 13. Authorization Failure Handler and Removing Authorized Clients

The manager has a parallel extension point:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizationFailureHandler;
~~~

In certain refresh failure scenarios, the default handler may remove an unusable authorized client, depending on the error code and manager in use. For instance, a revoked Refresh Token can cause the Token Endpoint to return `invalid_grant`.

Distinguish:

| Event | Primary Handling |
| --- | --- |
| Token issuance/refresh succeeds | `OAuth2AuthorizationSuccessHandler` saves the new authorized client |
| Token issuance/refresh fails | `OAuth2AuthorizationFailureHandler` and manager error policy |
| User actively disconnects | Application removes authorized client and may call token revocation |
| User logs out of application | Ends session/`SecurityContext`; does not automatically delete all persistent tokens |

**Do not write a failure handler that deletes the authorized client on every exception.** Transient network drops, timeouts, or 5xx errors from the provider do not necessarily mean the Refresh Token was revoked. Deleting valid tokens on temporary errors can force users to re-consent needlessly.

If replacing the failure handler, carefully review the default behavior and token invalidation policy of your Spring Security version.

### 13.1. Deleting a Local Record Differs from Revocation

~~~java
authorizedClientService.removeAuthorizedClient(
    "calendar", "employee-123"
);
~~~

This call deletes **the record on the client**. It does not automatically send a revocation request to the Authorization Server and does not end the user's SSO session at the IdP.

If the product requires genuine permission termination, OAuth 2.0 Token Revocation (RFC 7009) may be needed when supported by the provider. Handle active tokens, Refresh Tokens, Access Tokens, and responses per the OP contract. Never call `removeAuthorizedClient(...)` and claim the provider revoked the token without verification.

## 14. Multi-User, Multi-Provider, and Safe Storage Keys

For `OAuth2AuthorizedClientService`, the logical key is:

~~~text
(clientRegistrationId, principalName)
~~~

Examples:

| Registration ID | Principal Name | Permission Type |
| --- | --- | --- |
| `company` | `employee-123` | Access Token after OIDC user login |
| `calendar` | `employee-123` | Calendar read access for this user |
| `calendar` | `employee-456` | Calendar read access for another user |
| `reporting-service` | `system-reporting-job` | Backend Client Credentials |

Handlers must never read a principal name from a query parameter and save tokens under an arbitrary user. Principal must come from the **server-managed authorization context**.

### 14.1. Registration ID Does Not Fully Replace Issuer

With OIDC, user identity relies on the **`iss + sub`** pair. If an application uses multiple issuers without strong principal namespacing, collisions can occur. When integrating multiple IdPs and tenants, design registration/principal identities so tokens cannot bind to the wrong account.

### 14.2. Can a Scheduled Job Access an End-User's Token?

A service manager can operate outside HTTP requests, yet using an **end-user's** authorized client in a scheduled job is only appropriate when:

- The user granted permission for that purpose, and product policy permits offline execution without the user present.
- The token store uses a stable, verified principal namespace.
- Refresh Tokens are protected, retention is controlled, and disconnect/revoke capabilities exist.
- The job never borrows another user's token arbitrarily.

Never substitute a Client Credentials token for a delegated user token when a downstream API requires user permissions, or vice versa.

## 15. Two Requests Refreshing Together: Success Handler Race Conditions

A realistic scenario:

~~~mermaid
sequenceDiagram
    autonumber
    participant R1 as Request A
    participant R2 as Request B
    participant S as AuthorizedClientService
    participant AS as Token Endpoint
    R1->>S: load old token for principal X
    R2->>S: load same old token
    R1->>AS: refresh using old Refresh Token
    R2->>AS: refresh using old Refresh Token
    AS-->>R1: New token + rotated Refresh Token
    AS-->>R2: Possibly invalid_grant if token already consumed
    R1->>S: Success handler saves new token
    Note over S: Must prevent stale thread from deleting/overwriting new result
~~~

When multiple requests or instances share an authorized client, **saving a token successfully does not automatically guarantee atomic updates aligned with the latest token version**.

Measures to consider:

1. A **single-flight/lock mechanism per `registrationId + principalName`** for refreshes when genuinely needed.
2. Optimistic locking/versioning or compare-and-swap if using custom JDBC storage.
3. Preventing a failed refresh on request B from deleting the fresh token just saved by request A.
4. Avoiding unbounded retries with an old Refresh Token when the provider uses token rotation.
5. Minimizing concurrent writes to the same token record in sensitive workflows.

Never create a **global lock across all authorized clients**, as that degrades performance across unrelated users; synchronization must be scoped to the specific record.

### 15.1. Custom Success Handler and Transactions

If a success handler must update simultaneously:

~~~text
oauth2_authorized_client:
  new Access Token/Refresh Token

integration_connection:
  connected=true, lastAuthorizedAt=...
~~~

an explicit consistency design is required. With the same database and suitable transaction manager, a transaction can coordinate both; with an event bus or network service, use an outbox or idempotency mechanism rather than assuming two saves are atomic.

**A handler finishing without exception does not mean data has committed across all downstream systems.** Observability/auditing must distinguish “authorization succeeded” from “persistence succeeded”.

## 16. Observing Handlers Without Leaking Tokens

A useful log format:

~~~text
event=oauth2_authorization_persisted
registration_id=reporting-service
principal_type=service
grant_family=client_credentials
outcome=success
correlation_id=internal-5f92
~~~

This is a suggested format, **not a default Spring Security log**. Do not infer grant type solely from the presence or absence of a Refresh Token; if logging grants, read from a verified context source.

Never log:

- `access_token`, `refresh_token`, `id_token`.
- `client_secret` or token endpoint authorization headers.
- The entire `OAuth2AuthorizedClient` or token response JSON.
- Callback query strings containing `authorization_code`, `state`, or PKCE verifiers.
- Overly granular user identities when unnecessary for operations.

When emitting metrics, use aggregated counts by registration/grant/outcome and safe error codes. If recording subject or principal, apply appropriate personal data and access policies.

### 16.1. Success Handler Is Not a Hook for Every HTTP Call

If an application calls a downstream API 500 times while the Access Token remains valid:

~~~text
authorize() call 1 -> needs new token -> success handler saves
authorize() calls 2..500 -> can reuse token -> handler does not run
~~~

Never use success handler execution counts to measure request volume or API success rates. Measure API traffic at the HTTP client / Resource Server layer.

## 17. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Token issued yet next call finds no record | Custom success handler only logs without saving | Delegate/persist the authorized client before returning success |
| Every request calls the Token Endpoint again | Manager does not save token or keeps changing principal/registration | Check handler, store, principal key, and token expiry |
| First refresh succeeds, next one returns `invalid_grant` | Refresh Token rotation enabled yet new token was not saved | Persist the full new authorized client, handle concurrency |
| Service manager bean exists yet web login ignores it | Login flow uses a different repository | Check OAuth2 Login config and repository/service wiring |
| Custom handler never runs while token is valid | Provider did not perform re-authorization | Expected; success handler does not run on every load |
| Using `AuthenticationSuccessHandler` yet refreshes still aren't saved | Login success handler is not the manager hook | Use the right manager/repository authorization success handler |
| JDBC shows no tokens even though login succeeded | Actual store is session/in-memory or bean is unused | Check implementation and wiring, avoid duplicate beans |
| App runs on multiple pods and tokens disappear | Local unshared in-memory store | Use shared JDBC/service or appropriate session store |
| User A's token used for User B | Wrong principal key/namespace | Bind verified registration + principal |
| New token gets deleted after concurrent refresh | Race between success and failure handlers | Per-client synchronization / optimistic concurrency |
| Audit reports “saved” even though DB failed | Logged/audited before save or uncommitted transaction | Order operations properly and design audit consistency |
| Handler log leaks tokens | Logged raw `authorizedClient`/attributes | Log only non-sensitive metadata |
| API returns 403 even though manager has a token | Token lacks scope/role/resource policy | Check Resource Server; client roles do not replace API permissions |
| Authorized client still exists after logout | JDBC service stores independently of HTTP session | Design logout, disconnect, and token revocation separately |

### 17.1. Investigation Steps When Tokens Are Not Saved

~~~text
Was Manager.authorize(...) called?
   |
   +-- Are registrationId and principalName right?
   |
   +-- Did AuthorizedClientProvider execute the grant successfully?
   |
   +-- Did the Provider return a new authorized client or just null?
   |
   +-- Is there a custom AuthorizationSuccessHandler?
   |       |
   |       +-- Does it perform save/delegate?
   |
   +-- Does the store use a repository or service? Is it the right instance/bean?
   |
   +-- After saving, does loading with the same key find the record?
   |
   +-- Is there a race condition, rollback, or premature cleanup?
~~~

When debugging in production, avoid printing real tokens. Use a test environment with dummy tokens and log registration name, event type, and token-presence flags without secret values.

## 18. Scenario Exercises

### Scenario A — Using Defaults Without a Custom Handler

A Spring MVC application logs in via OIDC and occasionally refreshes Access Tokens to call an API. The default manager is already wired with an appropriate repository.

**Solution:** keep the default authorization success handler. Focus on configuring client registrations, grants, storage, and API permissions properly.

### Scenario B — Replacing the Handler Just for Auditing

A developer calls `manager.setAuthorizationSuccessHandler((client,principal,attrs) -> log.info("done"))`.

**Problem:** replaced the default handler's persistence logic. **Solution:** inside the new handler, save via the context-appropriate repository/service, or put auditing in a persistence wrapper/decorator without dropping save behavior.

### Scenario C — Client Credentials Outside Servlet

A scheduled job calls a reporting API with no user/browser session.

**Solution:** use `AuthorizedClientServiceOAuth2AuthorizedClientManager`, provide a fixed service-level principal, enable `clientCredentials()`, and rely on the default success handler saving tokens into the service.

### Scenario D — API Needs a User's Delegated Token

The application already has an authenticated user and needs to call that user's calendar API.

**Solution:** select the right registration, principal, and authorized client saved from the user's authorization flow; use the Servlet manager/repository or a properly authorized non-HTTP workflow. Never borrow a Client Credentials token in place of a user token.

### Scenario E — Token Saved Yet Manager Does Not Refresh

The Access Token expired and a Refresh Token exists, yet the provider/manager was not configured with the `refresh_token` grant.

**Solution:** verify the provider supports Refresh Tokens and how tokens are issued, and enable `refreshToken()` in the corresponding manager's authorized client provider. The success handler only saves once a new token is issued; it does not trigger refreshes itself.

### Scenario F — Token Rotation and Concurrent Writes

Two requests refresh together; request A receives a new Refresh Token and saves it; B gets `invalid_grant` using the old token.

**Solution:** handle concurrency per authorized client so B's failure handler does not delete A's new record; use appropriate transactions/locking at scale.

### Scenario G — User Disconnects an Integration

The authorized client is stored in JDBC. The user requests stopping synchronization.

**Solution:** locate the exact principal and registration, perform token revocation if supported by the provider, and then remove the local record. This is not the responsibility of the authorization success handler.

### Scenario H — Login Success Handler Works Yet Tokens Are Missing from Expected Store

The browser redirects cleanly after login; checking JDBC shows no authorized client.

**Solution:** inspect which repository/service OAuth2 Login uses. `AuthenticationSuccessHandler` may work fine while tokens are being saved in the HTTP session or a different in-memory service.

### Scenario I — Handler Saved the Token Yet Auditing Failed

The DB has the new token, yet the message broker for sending audit events is down.

**Solution:** decide whether auditing is mandatory or optional and handle consistency/idempotency accordingly. Never retry token issuance infinitely because an unrelated tracking system failed.

## 19. Layer-by-Layer Testing Suggestions

These scenarios are **for learners to apply themselves**, not test execution results or QA reports for this lesson file.

| Scenario | Expectation |
| --- | --- |
| First Client Credentials Access Token request | Manager receives new client; success handler saves record |
| Repeated call while token is still valid | Reuses authorized client; handler does not need to run again |
| Token expired and grant applies | Provider issues new token; handler saves new client |
| Refresh Token rotated | Record contains the new Refresh Token, not the old one |
| Audit-only custom success handler | Exposes missing persistence bug if it does not delegate |
| Custom handler with save | After `authorize`, `service.loadAuthorizedClient` returns new client |
| DB save fails | Do not log “persisted success” audit before save completes |
| User A and User B share a registration | Store returns tokens per exact principal without mixing |
| Logout with JDBC store | Token deletion/retention follows policy, not assumptions |
| Token endpoint returns `invalid_grant` | Enters failure handling; success handler is not called |
| Two concurrent refresh requests | New token is not accidentally deleted after stale request errors |
| No browser Servlet request | Use service manager rather than forcing DefaultServlet manager outside its context |

### 19.1. Sample Unit Test for a Custom Service Success Handler

Assuming an `OAuth2AuthorizedClientService` and an `OAuth2AuthorizedClient` built from a **test fixture**, you can test persistence with a standalone handler:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.oauth2.client.OAuth2AuthorizationSuccessHandler;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;

class AuthorizationSuccessHandlerTest {

    @Test
    void savesAuthorizedClientUnderPrincipalName() {
        OAuth2AuthorizedClientService service = /* test in-memory service */;
        OAuth2AuthorizedClient testClient = /* fixture with TEST token */;

        OAuth2AuthorizationSuccessHandler handler =
            (authorizedClient, principal, attributes) ->
                service.saveAuthorizedClient(
                    authorizedClient, principal.getName());

        var principal = new UsernamePasswordAuthenticationToken(
            "test-service-principal", "N/A");

        handler.onAuthorizationSuccess(testClient, principal, Map.of());

        assertNotNull(service.loadAuthorizedClient(
            testClient.getClientRegistration().getRegistrationId(),
            "test-service-principal"));
    }
}
~~~

This is an **illustrative API test skeleton**, intentionally leaving placeholders for the in-memory service and test fixture; running it requires implementing both fixtures. Testing the handler directly only verifies the save operation, **and does not prove OAuth2 token exchange or OIDC ID Token validation**.

## 20. References

- Spring Security — Servlet OAuth2 Client: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- Spring Security — OAuth2 Client Core Interfaces: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html
- Spring Security — OAuth2AuthorizationSuccessHandler Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizationSuccessHandler.html
- Spring Security — OAuth2AuthorizedClientManager Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html
- Spring Security — DefaultOAuth2AuthorizedClientManager Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizedClientManager.html
- Spring Security — AuthorizedClientServiceOAuth2AuthorizedClientManager Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html
- Spring Security — OAuth2AuthorizedClientService Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientService.html
- Spring Security — OAuth2AuthorizedClientRepository Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/OAuth2AuthorizedClientRepository.html
- OAuth 2.0 Authorization Framework (RFC 6749): https://www.rfc-editor.org/rfc/rfc6749
- OAuth 2.0 Token Revocation (RFC 7009): https://www.rfc-editor.org/rfc/rfc7009
- OAuth 2.0 Security Best Current Practice (RFC 9700): https://www.rfc-editor.org/rfc/rfc9700

## 21. Summary: Preserving Persistence When Customizing the Success Handler

~~~text
OAuth2AuthorizedClientManager.authorize(...)
  |
  +-- load existing authorized client from repository/service
  |
  +-- OAuth2AuthorizedClientProvider
  |     |
  |     +-- No re-authorization needed
  |     |      -> may return existing client
  |     |      -> does not necessarily invoke success handler
  |     |
  |     +-- Grant succeeds, new client produced
  |            |
  |            v
  |     OAuth2AuthorizationSuccessHandler
  |            |
  |            +-- DefaultServlet manager: saves via repository
  |            +-- Service manager: saves via service
  |            +-- Custom handler: MUST preserve save/delegate step
  |
  +-- Grant fails
        -> OAuth2AuthorizationFailureHandler / error policy

AuthenticationSuccessHandler (browser login)
  -> a different hook, runs after user login succeeds
  -> does not replace AuthorizedClientManager persistence
~~~

**Three things to remember:**

1. **`OAuth2AuthorizationSuccessHandler` is the client manager's hook after successful token issuance/refresh**, not a post-login browser navigation handler.
2. **Default managers already save authorized clients.** If you only need to save and reuse Access Tokens/Refresh Tokens, no custom handler is needed; if you replace the handler, preserve persistence logic.
3. **Tokens must be saved under the right registration and principal, in storage matching the application lifecycle.** Protect tokens as credentials, handle Refresh Token rotation/concurrency, and distinguish deleting local records from revocation at the provider.

When the right success handler is placed at the right layer, Spring Security can reliably reuse tokens, refresh, and update authorized clients without mixing OIDC login, token persistence, and API authorization responsibilities.
