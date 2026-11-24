# OAuth2AuthorizedClientManager and Calling Protected APIs from a Spring Security Servlet App

## 1. The problem: a Servlet app must call an API requiring an OAuth 2.0 access token

A Spring Boot application using **Spring Security Servlet** can both serve browsers and act as an **OAuth 2.0 Client** when calling APIs on other systems. Suppose:

- A user logs into the web app and wants to view their own profile from `https://resource.example.test/users/me`. This request uses **user-delegated authorization**, typically via `authorization_code` (and `refresh_token` when issued).
- The application synchronizes reports on its own with `https://resource.example.test/reports`, without needing per-request user authorization. This request can use **`client_credentials`** to obtain a token for the application's identity.
- The target API (resource server) validates `Authorization: Bearer <access-token>` and checks scopes/audience/permissions. The application calling the API is the *client*; it must not assume it is a resource server merely because it handles access tokens for outbound calls.

To manage selecting an OAuth client registration, obtaining tokens, reusing valid tokens, refreshing or re-issuing tokens when permitted, and persisting authorized client state, Spring Security provides **`OAuth2AuthorizedClientManager`**.

### Components and roles

| Component | Responsibility |
| --- | --- |
| `ClientRegistration` | Describes an OAuth client: `registrationId`, client ID/secret, grant type, authorization/token URI, scopes... |
| `ClientRegistrationRepository` | Looks up `ClientRegistration` entries by `registrationId`, e.g., `user-api` or `report-api` |
| `OAuth2AuthorizedClient` | Combines `ClientRegistration`, principal name, and issued access token (possibly with refresh token) |
| `OAuth2AuthorizedClientRepository` | Saves/loads authorized clients per Servlet request/response and principal, typically tied to web session/state |
| `OAuth2AuthorizedClientService` | Saves/loads authorized clients by client registration ID and principal name, independent of Servlet requests |
| `OAuth2AuthorizedClientProvider` | Executes enabled mechanisms like `authorization_code`, `refresh_token`, `client_credentials`... |
| `OAuth2AuthorizedClientManager` | Coordinates providers, storage, and the token issue/exchange cycle via `authorize(...)` |
| `RestClient`/`WebClient`/`RestTemplate` | Sends HTTP calls to target APIs; access tokens must be attached to requests properly |

**`OAuth2AuthorizedClient` is not synonymous with `Authentication`**: `Authentication` represents the user/service authenticated **at the application**, whereas an authorized client represents an OAuth 2.0 token granted to a client and principal to call **external resources**. Having a valid principal does not guarantee authorization for every target API.

## 2. How OAuth2AuthorizedClientManager works

The central API of the interface is:

~~~java
OAuth2AuthorizedClient authorizedClient =
    authorizedClientManager.authorize(authorizeRequest);
~~~

This is a **snippet inside an application with suitable beans/config**, not a standalone Java file. `OAuth2AuthorizeRequest` specifies at least `clientRegistrationId` and `principal`; additional attributes can supply request context or grant parameters when needed.

Overall flow:

~~~text
Controller / Service / HTTP client interceptor
               │
               │ OAuth2AuthorizeRequest(registrationId, principal)
               ▼
       OAuth2AuthorizedClientManager
               │
               ├─ Find matching ClientRegistration
               ├─ Read existing OAuth2AuthorizedClient by principal + registration
               ├─ Ask OAuth2AuthorizedClientProvider if token needs/can be issued?
               │     ├─ access token still valid → can reuse
               │     ├─ token near/past expiration + refresh token → try refresh_token
               │     ├─ client_credentials → fetch new access token when needed
               │     └─ grant prerequisites missing → cannot authorize yet
               ├─ Save authorized client after successful token issue/exchange
               └─ Return OAuth2AuthorizedClient (may be null)
               │
               ▼
  HTTP request: Authorization: Bearer <access-token>
               │
               ▼
   Resource Server validates token and permissions
~~~

Points that must be understood accurately:

1. **`authorize(...)` does not mean always sending a network request to the authorization server.** The manager/provider can reuse a still-valid authorized client and access token, or determine nothing needs to be done.
2. **The result can be `null`** if no matching authorized client exists and the configured providers cannot issue a new one in that situation. Never access `getAccessToken()` without checking the result.
3. **Grant types require matching providers.** A manager that only enables `clientCredentials()` will not refresh a user's token with `refresh_token`, and vice versa.
4. **Interactive browser `authorization_code`** happens via redirect to the authorization server and callback, driven by security filters and application config. Do not assume calling `manager.authorize(...)` alone will automatically prompt consent/redirect for an unauthorized user.
5. **Network, configuration, and OAuth2 errors** can cause `authorize(...)` to throw exceptions; the client must have proper error handling, timeouts, and retry policies. Never retry infinitely when a client secret is wrong or consent was revoked.

## 3. Choosing the right manager for the context

There are two common implementations sharing the `OAuth2AuthorizedClientManager` interface, with different operational boundaries.

| Criterion | `DefaultOAuth2AuthorizedClientManager` | `AuthorizedClientServiceOAuth2AuthorizedClientManager` |
| --- | --- | --- |
| Target environment | Has `HttpServletRequest`/`HttpServletResponse` inside a Servlet request flow | Outside HTTP requests: jobs, background workers, message consumers; also usable in Servlets |
| Storage | `OAuth2AuthorizedClientRepository` | `OAuth2AuthorizedClientService` |
| Principal context | Typically the logged-in user and web session | Application-supplied principal/service name |
| Typical grants | `authorization_code` + `refresh_token` for users | `client_credentials` for the application or suitable grants in background work |
| Common mistake | Using in a `@Scheduled` thread without a Servlet request | Sharing one fixed principal name for tokens of many different users |

**Rule:** for authorized browser requests, use the manager backed by the Servlet repository. For service-to-service tokens needed in scheduled jobs, choose the service manager instead of relying on browser sessions.

The principal name helps key the stored authorized client. Using a name like `reporting-service` for `client_credentials` makes sense because the token represents the application; **never share that same name to store access tokens issued per individual user**.

### How does Repository differ from Service?

- `OAuth2AuthorizedClientRepository` has load/save/remove APIs taking request, response, and `Authentication`. A configuration may store in the session or delegate to a service depending on principal state.
- `OAuth2AuthorizedClientService` accesses by `clientRegistrationId` and `principalName` without requiring a Servlet request. Spring Boot may provide an in-memory implementation by default; for multi-node environments, restarts, and durability requirements, evaluate shared persistence, encryption mechanisms, and revocation workflows.
- Storing a token does not guarantee it remains valid: the resource server still enforces signature/introspection, expiration, audience, scopes, and policy at call time.

## 4. Preparing the Spring Boot project and OAuth client config

The following example targets **Java 17+, Spring Boot 3.2+ / Spring Security 6.x**, using Spring Framework 6.1+'s `RestClient`. All URLs/domains/credentials are **example values** that must be replaced with real authorization and resource servers before running.

Corresponding Gradle dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

If the application **also accepts Bearer tokens** from external clients, you may need `spring-boot-starter-oauth2-resource-server`; that is a separate role. To **call outbound APIs as an OAuth2 Client**, the OAuth2 Client starter alone provides the needed components.

Example `application.yml` with two client registrations:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          user-api:
            provider: user-idp
            client-id: ${USER_API_CLIENT_ID}
            client-secret: ${USER_API_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - api.read
          report-api:
            provider: service-idp
            client-id: ${REPORT_API_CLIENT_ID}
            client-secret: ${REPORT_API_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          user-idp:
            issuer-uri: https://login.example.test/realms/demo
          service-idp:
            token-uri: https://login.example.test/oauth2/token
~~~

Meaning:

- `registration.user-api` uses **authorization code**. `issuer-uri` requires the provider to have compatible metadata discovery; depending on the provider, you may need to explicitly configure authorization URI, token URI, JWK set URI, and user-info URI.
- `redirect-uri` must be accurately registered with the authorization server, using HTTPS in production and the right host/path behind a reverse proxy. `scope` only requests permissions; the authorization server decides what is granted.
- `registration.report-api` uses **client credentials**, so it needs `token-uri` and client credentials. This grant typically **has no refresh token**; when the access token expires, the provider requests a new access token using client credentials.
- `${...}` is a Spring placeholder reading environment variables or externalized config. **Never commit client secrets**, authorization codes, access tokens, or refresh tokens to Git/logs.
- Use the exact registration ID in `OAuth2AuthorizeRequest`; the ID is an internal config name, not a URL and not automatically equal to scope or client ID.

If the provider issues an access token of a type/format that the resource server does not accept, changing the registration alone will not fix it; check audience/resource indicators, scopes, and the contract on both sides.

## 5. Configuring two OAuth2AuthorizedClientManagers

File `OAuth2ClientManagersConfig.java` in package `com.example.demo`:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class OAuth2ClientManagersConfig {

    @Bean("servletAuthorizedClientManager")
    OAuth2AuthorizedClientManager servletAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository repository) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations, repository);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Bean("serviceAuthorizedClientManager")
    OAuth2AuthorizedClientManager serviceAuthorizedClientManager(
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
        return manager;
    }
}
~~~

Here both beans implement the same interface, so when injecting into controllers/services you must use **`@Qualifier`** (or explicit bean selection) to avoid ambiguous dependency errors.

**Why two different providers?**

- For `user-api`, the first step must be the browser completing the OAuth2 authorization redirect/callback; the manager processes the existing authorized client and can use the `refreshToken()` provider if a refresh token was granted.
- For `report-api`, the `clientCredentials()` provider automatically requests a machine access token from the token endpoint when missing or needing renewal. Never use a browser session or try running OAuth2 Login for a backend job.
- One manager can be configured with multiple providers, but the choice here **clarifies the boundary between user tokens and service tokens**, reducing the risk of sending the wrong token type to an API.

These managers have success/failure handler mechanisms to save or remove authorized clients as appropriate. On errors such as a revoked refresh token, handle the OAuth2 failure properly; do not assume the framework automatically triggers user consent or retries all errors. Never pull tokens manually from storage while bypassing the manager on every call, or you risk using expired tokens.

## 6. Connecting OAuth2 Login to the Servlet SecurityFilterChain

File `SecurityConfig.java`, minimal example for the browser flow:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/user/**", "/api/machine/**")
                .authenticated()
                .anyRequest().permitAll())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
~~~

`oauth2Login(...)` supports the interactive login flow; `oauth2Client(...)` enables OAuth2 Client integrations for the Servlet application. The `authenticated()` rule in the example protects the front-facing proxy endpoints; production apps must add proper authorization, endpoint restrictions, and CSRF/CORS policies.

**Never disable CSRF globally** just because the application calls downstream Bearer APIs. When browsers authenticate to the app itself using session cookies, state-changing requests from browsers must still be evaluated for CSRF independently of the backend using Bearer tokens to call other APIs.

When the user is not logged in, Spring Security can send the browser to the login page and then to the provider. For registration `user-api`, the initiation path is typically `/oauth2/authorization/user-api`, and the default callback has the form `/login/oauth2/code/user-api`. Verify the registered redirect URI and proxy configuration; the authorization code is exchanged for tokens by OAuth2 Login components, not by a controller parsing the callback manually.

## 7. Calling protected APIs with RestClient

Below is `DownstreamApiController.java` in the same `com.example.demo` package. The project already has the beans from Sections 5 and 6 and the registration config from Section 4. The resource server URI is an example and must be replaced with a real URL. Only GET is handled to focus on OAuth2 Client; other operations need proper HTTP methods, error mapping, and validation.

~~~java
package com.example.demo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.client.RestClient;

@RestController
public class DownstreamApiController {

    private final OAuth2AuthorizedClientManager servletManager;
    private final OAuth2AuthorizedClientManager serviceManager;
    private final RestClient api;

    public DownstreamApiController(
            @Qualifier("servletAuthorizedClientManager")
            OAuth2AuthorizedClientManager servletManager,
            @Qualifier("serviceAuthorizedClientManager")
            OAuth2AuthorizedClientManager serviceManager,
            RestClient.Builder restClientBuilder) {
        this.servletManager = servletManager;
        this.serviceManager = serviceManager;
        this.api = restClientBuilder
            .baseUrl("https://resource.example.test")
            .build();
    }

    @GetMapping("/api/user/profile")
    public String userProfile(Authentication authentication) {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("user-api")
                .principal(authentication)
                .build();

        // Must be called within a Servlet request with an authenticated principal.
        OAuth2AuthorizedClient authorized =
            servletManager.authorize(request);

        if (authorized == null) {
            throw new ResponseStatusException(
                HttpStatus.FORBIDDEN,
                "User has not authorized this OAuth2 client");
        }

        return api.get()
            .uri("/users/me")
            .headers(headers -> headers.setBearerAuth(
                authorized.getAccessToken().getTokenValue()))
            .retrieve()
            .body(String.class);
    }

    @GetMapping("/api/machine/reports")
    public String reports() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("report-api")
                .principal("reporting-service")
                .build();

        OAuth2AuthorizedClient authorized =
            serviceManager.authorize(request);

        if (authorized == null) {
            throw new ResponseStatusException(
                HttpStatus.BAD_GATEWAY,
                "Unable to obtain access token for report-api");
        }

        return api.get()
            .uri("/reports")
            .headers(headers -> headers.setBearerAuth(
                authorized.getAccessToken().getTokenValue()))
            .retrieve()
            .body(String.class);
    }
}
~~~

**Detailed analysis:**

1. For `/api/user/profile`, the `Authentication` parameter is supplied by Spring Security from the user's context. This principal must correspond to the user's login/authorization event; never replace it with a fixed name. `DefaultOAuth2AuthorizedClientManager` and `OAuth2AuthorizedClientRepository` operate inside a **Servlet request flow** where Spring MVC has the active request/response.
2. If no authorized client has been granted via an authorization redirect, `authorize(...)` may return `null`. The 403 response here is only an **illustrative controller decision**. An app can direct the user to a consent/login flow appropriately, but **never automatically retry the authorization endpoint in an infinite loop**.
3. For `/api/machine/reports`, `"reporting-service"` is a stable principal name used to manage the machine authorized client; it is **not a user's credentials**. The service manager can reuse the token or request a new one from the provider depending on state.
4. `headers.setBearerAuth(...)` adds the access token only to the **outbound HTTP request** at call time. The controller never includes the access token in JSON returned to the browser.
5. The target resource server is responsible for validating the token and scopes. Receiving HTTP 403 from downstream **does not necessarily** mean the token expired; it could also be missing scopes/permissions or wrong audience.
6. The example uses `RestClient`, which is a synchronous HTTP client. In reactive `WebFlux` applications, context management and `WebClient` usage differ; this article covers only **Spring Security Servlet**.
7. `RestClient.retrieve()` can throw exceptions for 4xx/5xx responses. In production, configure timeouts, bound retries, map downstream errors, and observe safely instead of exposing raw error bodies with sensitive details.

**Note on tokens:** use `authorized.getAccessToken().getTokenValue()`. With OIDC login, the **ID token** describes the user's login to the client; never substitute an ID token for an access token when calling a resource server unless the API has a clearly defined contract for doing so.

## 8. How do the two flows execute?

### 8.1. User delegated access: authorization_code + refresh_token

~~~text
Browser ── GET /oauth2/authorization/user-api ──▶ Spring Security
Browser ◀──────── redirect to Authorization Server ───┘
Browser ───────── login/consent ──────────────────▶ Authorization Server
Browser ◀──────── redirect to /login/oauth2/code/user-api (code + state)
Spring Security ───── exchange code for token ────▶ Authorization Server
Spring Security ───── save authorized client ─────▶ Repository/session/service
Browser ───────── GET /api/user/profile ─────────▶ Controller
Controller ───── servletManager.authorize(...) ──▶ Authorized client
Controller ───── Bearer access token ─────────────▶ Resource Server /users/me
Browser ◀──────── business result ────────────────── Controller
~~~

Spring Security must verify `state` in the callback and apply appropriate protocol mechanisms (PKCE when applicable). Do not hand-roll callback/token exchange logic when standard filters handle it. A refresh token is only present when the provider actually issues it and the grant/provider supports it.

If the user logs out or the grant is revoked, review the policy for removing the authorized client from storage and handling the session. Clearing the web session, revoking the access token at the authorization server, and deleting the authorized-client record are **distinct actions**; never assume all of them happened merely because a cookie was cleared.

### 8.2. Machine-to-machine: client_credentials

~~~text
Backend job / Servlet controller
    │
    └─ serviceManager.authorize("report-api", "reporting-service")
                    │
                    ├─ Valid access token already exists → reuse
                    └─ Missing/expired → POST token endpoint
                             grant_type=client_credentials
                             client authentication + scope
                                    │
                                    ▼
                        Authorization Server issues token
                                    │
                                    ▼
                    Save OAuth2AuthorizedClient by principal
                                    │
                                    ▼
              GET /reports + Authorization: Bearer <token>
                                    │
                                    ▼
                          Resource Server checks permissions
~~~

No browser, authorization code, or redirect is needed in this flow. The token belongs to the client/service, so do not treat it as "the token of the user calling the controller"; if the front-facing endpoint requires user permissions, still check separately **who is allowed to trigger the work**.

Machine tokens can be shared across invocations with the same registration and principal, within the bounds of caching/storage policies. If the client secret changes or authorization is revoked, new token requests may fail even while an old record remains in storage.

## 9. Expired access tokens, refresh tokens, and authorization errors

Common cases:

| State | Expected behavior with a matching provider |
| --- | --- |
| Access token still valid | Can return the authorized client without calling the token endpoint |
| Access token near/past expiration, refresh token available and accepted | `refreshToken()` requests a new access token; authorized client is updated |
| Access token expired, no refresh token, client_credentials | `clientCredentials()` requests another access token using client credentials |
| Access token expired, user authorization_code without refresh token | User may need to run through the interactive authorization flow again |
| Refresh token revoked or returns `invalid_grant` | Authorize may fail; clear stale token / reauthorize per policy |
| Token still valid, but API returns 403 | May lack scope, role, audience, or tenant; refreshing will not fix every error |
| Token endpoint temporarily returns 5xx/timeout | Backoff, bounded retries, metrics; avoid infinite loops or token storms |

Some providers apply **clock skew** to proactively renew tokens shortly before expiration; verify the actual version and configuration. Do not write your own expiration comparison lacking clock skew and cache tokens manually in controllers, as you may send expired tokens or break refresh behavior.

**The OAuth2 protocol does not mean tokens are always JWTs.** An access token can be an opaque string. The client only needs to attach the right Bearer token to requests; the resource server can use JWT validation or token introspection depending on its design.

If a downstream call returns `401 invalid_token`, distinguish an expired token from a wrong-audience token or a network/proxy error. Automatically refreshing tokens infinitely after every 401 is dangerous: sometimes the token is still valid but sent to the wrong resource, or the API denies permission. Handle with a maximum retry count and inspect actual error codes.

### Why not call the token endpoint directly in every controller?

Hand-writing `POST /token` per request easily leads to redundant token exchanges, broken cache/expiry handling, lost refresh tokens, secret leaks in logs, and maintenance pain. `OAuth2AuthorizedClientManager` standardizes management, though it **does not eliminate** the need for proper provider setup, secure storage, timeouts, and HTTP error handling.

## 10. Servlet requests and background jobs: a critical boundary

**`DefaultOAuth2AuthorizedClientManager`** is designed for HTTP requests with a Servlet context. Calling its `authorize(...)` inside `@Scheduled`, asynchronous tasks, or manually spawned threads may lack an `HttpServletRequest`/`Response`, causing errors or failing to persist tokens. Never "copy" a user's context into a job just to bypass the error without an explicit security and lifecycle policy.

For background application tasks, reuse **`AuthorizedClientServiceOAuth2AuthorizedClientManager`**:

~~~java
package com.example.demo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Component;

@Component
public class ReportTokenJob {
    private final OAuth2AuthorizedClientManager manager;

    public ReportTokenJob(
            @Qualifier("serviceAuthorizedClientManager")
            OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    @Scheduled(fixedDelayString = "PT30M")
    public void checkAuthorization() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("report-api")
                .principal("reporting-service")
                .build();

        OAuth2AuthorizedClient client = manager.authorize(request);
        if (client == null) {
            throw new IllegalStateException(
                "Cannot authorize report-api");
        }

        // From here you can call the API using client.getAccessToken().
        // Do not log the token or return it to users.
    }
}
~~~

This is a **sample class with Spring dependencies** that requires scheduling enabled (e.g., `@EnableScheduling` on an application configuration) for the periodic task to run. If you only want to call the API every 30 minutes, place the HTTP call in a service using this token, configure timeouts, and prevent duplicate job execution across multiple instances.

**Never use a service manager with a shared principal to fetch individual users' tokens in the background** without a proper model for storage, consent, refresh token protection, and per-user access control. A job using user-delegated tokens is a more complex design than machine client credentials.

## 11. Separating errors and responsibilities across layers

| Error/symptom | Where to look first | How to diagnose |
| --- | --- | --- |
| Client registration not found | `registrationId` config, property binding | Compare exact names, active profiles, and repository bean |
| Cannot obtain `client_credentials` access token | Authorization server/token URI, client auth, secret, scope | Check OAuth2 error and config; do not log secrets/tokens |
| `authorize(...)` returns `null` for user | User has not completed consent/code flow, missing authorized client, or incompatible provider | Check login, callback, principal, repository, registration |
| Browser redirects continuously | Session/cookie, redirect URI, state, hostname/proxy, client registration | Check HTTPS, cookies, proxy forwarding, and provider URI |
| Has token, yet target API returns 401 | Missing/wrong/expired token, audience/issuer mismatch, header format | Inspect `WWW-Authenticate` and safe resource server logs |
| Target API returns 403 | Token is valid, but insufficient scopes/permissions or policy denial | Check granted scopes, authority mapping, and resource checks |
| Token refreshed on every request | Different principal/registration each call, non-persistent storage, clock skew, or short token lifetime | Check storage key, expiry, persistence, and token endpoint call counts |
| Scheduled job fails with missing Servlet context | Wrongly used `DefaultOAuth2AuthorizedClientManager` | Switch to `AuthorizedClientServiceOAuth2AuthorizedClientManager` |
| Non-unique `OAuth2AuthorizedClientManager` bean error | Two managers declared, injection lacks qualifier | Use `@Qualifier`/bean names per Section 5 |
| Works locally in tests, loses session in production | Using in-memory or unshared sessions across nodes | Design proper storage/persistence, load balancing, and sessions |
| Downstream HTTP errors unhandled | `RestClient.retrieve()` throws exception | Map response statuses, set timeouts, bounded retries, and circuit breakers if needed |

Do not draw conclusions from a single status code. Distinguish three domains: (1) browser authenticating to the app; (2) app requesting an OAuth2 token from the authorization server; (3) resource server receiving/checking the token when the API is called. Each domain has its own failure causes and logs.

## 12. Meaningful testing

### 12.1. Testing authorized client management

Use test doubles or a test OAuth2 authorization server to verify:

1. On the first `client_credentials` call with no authorized client, the manager calls the token endpoint and stores the token.
2. On subsequent calls while the token is valid, the manager can return the stored token without requesting a new one.
3. When the token expires, the manager can request a new token via client credentials; with delegated access and a valid refresh token, the provider attempts a refresh.
4. When the token endpoint returns an error, the application does not loop infinitely or leak the client secret.
5. Two different principals/registration IDs do not accidentally read each other's tokens.
6. The manager serving Servlet requests receives the right principal and does not fail due to missing request context.

To test the HTTP client, use **MockWebServer/WireMock** (or an equivalent stub server) and verify that the request to the resource server carries **exactly one** `Authorization: Bearer <token-test>` header; never log real tokens in test reports. Also simulate 401/403/5xx responses and timeouts from the resource server to verify error mapping.

### 12.2. Testing the browser flow

With authorization code, tests must cover redirects, `state` parameters and callbacks, sessions, consent, and token storage. `MockMvc` can verify filters/controllers under mocked conditions, but **does not replace** integration tests with a real authorization server and browser over HTTPS/proxies. For OIDC logins, verify required claims, issuer, and user mapping; avoid treating the access token as an ID token.

### 12.3. Smoke testing in a development environment

Start the app configured with a test IdP/resource server (the `example.test` domains in this guide are placeholders only), then:

~~~bash
# Run from a browser to perform interactive login/callback:
# http://localhost:8080/oauth2/authorization/user-api

# After valid login in the same browser session:
# http://localhost:8080/api/user/profile

# The service-token route is still subject to the app's front-door auth:
curl -i http://localhost:8080/api/machine/reports
~~~

The final `curl` command **does not carry a browser session**, so with the example `SecurityFilterChain` it may receive a login redirect or authentication error before the controller ever fetches a machine token. This is expected when the route requires `authenticated()`. To run a machine job without a browser, call the service manager directly inside the job and protect the job trigger appropriately.

Do not assume a fixed stdout/HTTP 200: responses depend on the real authorization server, API data, proxy, session, scopes, and configuration.

## 13. Safe deployment principles

- **Use access tokens, not ID tokens**, to call resource servers unless the API specifies a clearly defined protocol otherwise.
- **Protect secrets and tokens:** TLS, secret manager/env, never write to URLs, query strings, logs, exceptions, frontend HTML, or browser `localStorage` when the backend holds tokens.
- **Do not blindly forward the inbound client's Authorization header downstream.** Use the proper authorized client for the user/service and the target API's scope/audience.
- **Do not let clients arbitrarily control downstream URLs.** Maintain a target host/path allowlist to mitigate SSRF and avoid sending Bearer tokens to user-chosen endpoints.
- **Enforce least-privilege scopes.** Machine clients should not hold broader permissions than required; delegated tokens must remain tied to the right user and resource.
- **Authorize internal endpoints independently:** a token authorized to call a resource server does not replace checking who is allowed to click the button/call the front-facing controller.
- **Maintain CSRF defenses** if the Servlet app accepts session cookies from browsers and has state-changing operations.
- **Distinguish token expiration from downstream HTTP errors:** refreshing a token does not fix missing permissions or wrong audiences.
- **Choose appropriate storage:** in-memory services lose tokens on restart; evaluate session/repositories in multi-node deployments. For refresh tokens, encrypt and restrict storage access.
- **Safe observability:** metrics for token issuance, refresh failures, downstream 401/403s, and latency; log only registration ID, error codes, and correlation IDs—never log access/refresh tokens or client secrets.

### Self-assessment checklist

- [ ] `ClientRegistrationRepository` has the right registration IDs, grant types, token/authorization endpoints, and scopes.
- [ ] User flow has real OAuth2 Login/authorization callbacks, valid redirect URIs, and properly linked principals.
- [ ] Service flow uses `client_credentials` and a manager backed by `OAuth2AuthorizedClientService`.
- [ ] Managers have matching providers: `authorizationCode()`, `refreshToken()`, `clientCredentials()` per client.
- [ ] Every `authorize(...)` call checks for null and has an OAuth2 error-handling strategy.
- [ ] Outbound HTTP sends only the right `Authorization: Bearer <access-token>` to controlled hosts.
- [ ] Tested fresh tokens, valid cached tokens, expired tokens, refresh/grant failures, missing scopes, and lost storage.
- [ ] Verified Servlet endpoint authorization, session/CSRF, proxy/HTTPS, and safe error observability.

**Remember:** `OAuth2AuthorizedClientManager` is the coordinator of **authorized clients and the access token lifecycle** for an OAuth2 Client in Spring Security. For per-user Servlet requests, pick `DefaultOAuth2AuthorizedClientManager` with a repository; for background tasks or `client_credentials`, pick `AuthorizedClientServiceOAuth2AuthorizedClientManager` with a service. Even when the manager obtains and refreshes tokens cleanly, the application must still send the right Bearer header, protect tokens, handle HTTP errors, and respect resource server authorization.
