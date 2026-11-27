# 21.3. AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager for Background Tasks

## 1. Scenario: Background Task Needs to Call an API Without a Logged-In User

Suppose the **Employee Portal** application uses **Spring Boot, Spring Security OAuth 2.0 Client, and WebFlux**. Beyond the OIDC login UI for employees, the system has a **Reports Job** that runs periodically to aggregate reports. On each execution, the job must call a **Reports API** protected by an OAuth 2.0 Bearer token.

~~~text
01:00:00  Reports Job is triggered.
01:00:01  The job needs to call GET https://reports.example.test/api/daily-summary.
01:00:01  Reports API requires an access token with scope reports.read.
01:00:02  There is no browser, no logged-in user, and no ServerWebExchange.
~~~

In a normal WebFlux HTTP request, Spring Security can obtain `Authentication` and `ServerWebExchange` to look up the authorized client. However, a **scheduled task, message consumer, queue worker, or batch job** does not inherently have those objects.

If you try to use the web-request manager, the job easily runs into missing exchange/context errors, fails to find an authorized client, or confuses a user's token with the application's own authority.

**The right solution** is to use:

~~~java
org.springframework.security.oauth2.client
    .AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
~~~

This is an implementation of **`ReactiveOAuth2AuthorizedClientManager`** that uses **`ReactiveOAuth2AuthorizedClientService`** to manage authorized clients **without depending on a WebFlux ServerWebExchange**.

In this lesson, the primary grant is **`client_credentials`**: the Reports Job calls the API using the **OAuth client/service** identity, without simulating a logged-in OIDC user.

> Context: Java 17+, Spring Boot 3, Spring Security 6, and Project Reactor. All hostnames, registration names, and tokens in this lesson are illustrative only. Any case of calling an API "on behalf of a user" requires its own delegation policy; never use client credentials and treat them as an employee's token.

## 2. Same ReactiveOAuth2AuthorizedClientManager Interface, Different Contexts

Spring Security Reactive provides two common implementations:

| Feature | `DefaultReactiveOAuth2AuthorizedClientManager` | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
|---|---|---|
| Intended context | WebFlux request | Tasks outside a WebFlux request |
| Storage | `ServerOAuth2AuthorizedClientRepository` | `ReactiveOAuth2AuthorizedClientService` |
| Client registrations | `ReactiveClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| Needs ServerWebExchange? | Usually requires exchange/context to use the repository | **No** |
| Suitable examples | WebClient calling an API inside a user request | Scheduler, queue consumer, background worker |
| Principal | User Authentication from request or trusted context | Application-defined principal name/identity |
| Common grants | Authorization code, refresh token | Client credentials; or refresh token under business rules |
| Authorization API | `Mono<OAuth2AuthorizedClient>` | `Mono<OAuth2AuthorizedClient>` |

**Both managers implement the same interface but cannot be swapped arbitrarily.** The web-request manager coordinates with security/session context; the service manager works directly with the authorized-client service.

### 2.1. Which Mechanism Manages HTTP Sessions?

**Not** `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`. It does not create a `SecurityWebFilterChain`, perform OIDC login, or store a WebSession for browsers.

An application can run both simultaneously:

~~~text
Employee HTTP request
  -> OIDC login / SecurityContext / WebSession
  -> DefaultReactiveOAuth2AuthorizedClientManager

01:00 background job
  -> service registration: reports-service
  -> AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
  -> client_credentials access token
~~~

Each flow has its own **principal, storage, and security boundary**.

## 3. Overall Architecture of the Background Manager

~~~mermaid
flowchart TD
    J["@Scheduled / Queue Consumer / Background Worker"] --> G["ReportsGateway"]
    G --> A["OAuth2AuthorizeRequest"]
    A --> M["AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager"]
    M --> R["ReactiveClientRegistrationRepository"]
    M --> S["ReactiveOAuth2AuthorizedClientService"]
    M --> P["ReactiveOAuth2AuthorizedClientProvider"]
    P --> CC["client_credentials grant"]
    CC --> T["Reactive token response client"]
    T --> AS["Authorization Server token endpoint"]
    AS --> T
    T --> P
    P --> M
    M -->|save/update| S
    M -->|Mono<OAuth2AuthorizedClient>| G
    G --> W["WebClient"]
    W -->|Authorization: Bearer access token| API["Reports API"]
~~~

In this architecture:

1. **The Job** determines it needs to call the Reports API.
2. **The Gateway** creates an `OAuth2AuthorizeRequest` for the `reports-service` registration and a stable service principal.
3. **The Manager** checks for a stored authorized client in `ReactiveOAuth2AuthorizedClientService`.
4. If a new token is needed, **the provider** executes the supported grant.
5. **The Authorization Server** returns an access token.
6. **The Manager** saves the new authorized client via the service.
7. **WebClient** sends the Bearer token to the Reports API.

No step requires a browser redirect or a user's OIDC session.

## 4. Components to Understand

| Component | Responsibility |
|---|---|
| `ReactiveClientRegistrationRepository` | Reads OAuth client config, token URI, grant type, client authentication method, and scopes |
| `ReactiveOAuth2AuthorizedClientService` | Saves/loads/removes authorized clients by registration ID and principal name |
| `ReactiveOAuth2AuthorizedClientProvider` | Decides which grant applies and acquires tokens/authorized clients |
| `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` | Coordinates registration, provider, storage, and success/failure lifecycle |
| `OAuth2AuthorizeRequest` | Carries registration ID or authorized client along with principal/context for an authorization attempt |
| `OAuth2AuthorizedClient` | Authorized result holding the access token and optionally a refresh token |
| `WebClient` | Sends HTTP requests to the Resource Server |
| **Reports API / Resource Server** | Validates Bearer tokens, scopes/audience, and resource permissions |

### 4.1. Do Not Confuse Registration with Authorized Client

`ClientRegistration` is **static configuration/metadata**:

~~~text
registrationId = reports-service
clientId = reporting-worker
authorizationGrantType = client_credentials
tokenUri = https://login.example.test/oauth2/token
scope = reports.read
~~~

`OAuth2AuthorizedClient` is the **result holding tokens**:

~~~text
registrationId = reports-service
principalName = reports-scheduler
accessToken = AT-1, expiresAt = 01:05
refreshToken = null (common for client_credentials)
~~~

Having a registration in YAML **does not mean** a token has been issued. A token is only obtained when a component actually invokes the manager/provider for the matching grant.

### 4.2. The Manager Does Not Run Automatically on a Clock

Having `Manager` in the class name does not make it a scheduler. It does not wake up every minute on its own to refresh access tokens. The **Job** or consumer must call:

~~~java
manager.authorize(authorizeRequest);
~~~

to trigger retrieving or refreshing the authorized client.

## 5. client_credentials: The Grant for Service-to-Service Calls

In the **Client Credentials Grant**, the OAuth client uses the **application's own credentials** to request an access token.

~~~mermaid
sequenceDiagram
    participant Job as Reports Job
    participant Manager as Reactive Authorized Client Manager
    participant AS as Authorization Server
    participant API as Reports API

    Job->>Manager: authorize(reports-service, reports-scheduler)
    Manager->>AS: POST /token grant_type=client_credentials
    AS-->>Manager: access_token, token_type, expires_in
    Manager-->>Job: OAuth2AuthorizedClient
    Job->>API: GET /api/daily-summary + Bearer token
    API-->>Job: 200 DailySummary
~~~

Illustrative HTTP token request when the client uses `client_secret_basic`:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <redacted-client-credentials>

grant_type=client_credentials&scope=reports.read
~~~

Illustrative response:

~~~json
{
  "access_token": "EXAMPLE_SERVICE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "reports.read"
}
~~~

With `client_credentials`, a **refresh token is usually not issued** under standard OAuth2 semantics. When the access token is expired or about to expire, the manager can execute a **new client_credentials grant** to obtain another access token.

There is no need to create an OIDC `OidcUser`, call `/oauth2/authorization/...`, or simulate a user session for the job.

### 5.1. A Client Token Is Not a User Token

A token issued via `client_credentials` represents the authority of the **client/service**. If the Reports API needs to know "which employee is requesting data", do not blindly attach an employee name to the request and treat the service token as proof that the user was authenticated.

In background tasks, determine **who is allowed to schedule/submit jobs**, **which tenant the job may access**, and **which scopes/audience the service token has**. These are application/Resource Server policies, not automatically enforced just because the manager successfully issued a token.

## 6. Configuring Spring Boot for a Reports Job

### 6.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

An application **running only as a background worker**, exposing no HTTP endpoints, may use a different dependency set and application type. A **service-style** OAuth2 Client manager does not require a WebFlux HTTP server. However, if the Portal is a WebFlux application, the dependencies above are the appropriate context.

### 6.2. application.yml

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-service:
            provider: company
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}

reports:
  api:
    base-url: https://reports.example.test
  job:
    fixed-delay-ms: 60000
~~~

The variables `REPORTS_CLIENT_ID`, `REPORTS_CLIENT_SECRET`, and `OIDC_ISSUER_URI` must come from a secure deployment environment. In particular, **never commit client secrets to Git, logs, JavaScript, or shared documents**.

**Note on issuer-uri:** Spring Security can use provider metadata discovery when the issuer supports it. If the Authorization Server does not support discovery, explicitly configure `token-uri` and other required endpoints per the provider contract. With `client_credentials`, there is no browser authorization endpoint in the job runtime, but the client still needs a valid token endpoint.

### 6.3. Scope Does Not Determine Every Permission

`scope: reports.read` is the scope the application **requests**. The Authorization Server decides which scopes are granted, while the Reports API checks the actual token, audience, and resource permissions.

Do not treat a token containing `reports.read` as proof the job can read every tenant if the Reports API also enforces per-tenant authorization.

## 7. ReactiveOAuth2AuthorizedClientService: Where Authorized Clients Are Stored

The background-task manager works with:

~~~java
org.springframework.security.oauth2.client
    .ReactiveOAuth2AuthorizedClientService
~~~

This interface provides operations similar to:

~~~java
Mono<OAuth2AuthorizedClient> loadAuthorizedClient(
    String clientRegistrationId,
    String principalName
);

Mono<Void> saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal
);

Mono<Void> removeAuthorizedClient(
    String clientRegistrationId,
    String principalName
);
~~~

In Spring Security Reactive, these operations return **Mono**, fitting non-blocking pipelines.

### 7.1. In-Memory Service for Development

One implementation:

~~~java
import org.springframework.security.oauth2.client
    .InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client
    .ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration
    .ReactiveClientRegistrationRepository;

ReactiveOAuth2AuthorizedClientService service =
    new InMemoryReactiveOAuth2AuthorizedClientService(registrations);
~~~

`registrations` is the `ReactiveClientRegistrationRepository` that Spring Boot can create from OAuth2 Client configuration.

In-memory storage:

- Suits demos and single-instance environments where data does not need durability.
- Loses authorized clients on restart.
- Does not share state across replicas.
- Does not solve concurrency on its own if multiple tasks acquire tokens simultaneously.

If Spring Boot already auto-configures a suitable `ReactiveOAuth2AuthorizedClientService` bean, do not create a second bean just to have the service. Multiple beans of the same type can make injection ambiguous.

### 7.2. Storage for Production

When jobs run across multiple replicas or need durable state recovery, a `ReactiveOAuth2AuthorizedClientService` backed by a centralized database/cache may be needed. Depending on the Spring Security version and infrastructure, you can use a provided implementation or build a reactive adapter over your existing store.

Requirements to evaluate:

- Protecting token values, refresh tokens, and client secrets.
- Encryption-at-rest, TLS, access control, and backup policy.
- Keying by registration ID and principal name.
- TTL/retention/cleanup aligned with the token lifecycle.
- Race conditions when multiple jobs authorize concurrently.
- Avoiding blocking JDBC calls directly on the Reactor event loop if the storage wrapper is not genuinely reactive.

**Never implement a custom `saveAuthorizedClient()` that drops principal/registration mapping or logs unencrypted tokens.**

## 8. Creating AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager

This is the core configuration:

~~~java
package com.example.portal.reports;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Configuration
public class ReportsOAuth2ManagerConfig {

    @Bean("reportsAuthorizedClientManager")
    ReactiveOAuth2AuthorizedClientManager reportsAuthorizedClientManager(
        ReactiveClientRegistrationRepository registrations,
        ReactiveOAuth2AuthorizedClientService authorizedClientService
    ) {
        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations,
                authorizedClientService
            );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

**Line-by-line breakdown:**

1. `ReactiveClientRegistrationRepository` holds the `reports-service` registration.
2. `ReactiveOAuth2AuthorizedClientService` saves and loads tokens.
3. `ReactiveOAuth2AuthorizedClientProviderBuilder.builder().clientCredentials()` enables the provider to issue tokens via the service grant.
4. `new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(...)` creates a manager **that does not need ServerWebExchange**.
5. `setAuthorizedClientProvider(provider)` attaches the grant provider to the manager.
6. The bean name keeps injection unambiguous if the application also has a web-request manager.

`oauth2Login()` is not required for the job to run. If the Portal also has user login, the OIDC web login configuration **is a separate flow**.

### 8.1. Why Not Call the Token Endpoint Manually with WebClient?

A manual approach:

~~~text
POST /token -> parse JSON -> compute expiresAt manually
-> cache accessToken manually -> retry manually -> rotate refreshToken manually
~~~

can miss client authentication details, error mapping, token response parsing, and concurrency handling. Using the standard provider/manager centralizes the OAuth2 token lifecycle in one place, separate from the Reports API gateway.

## 9. Mono<OAuth2AuthorizedClient>: The Manager's Reactive Contract

Interface:

~~~java
import org.springframework.security.oauth2.client
    .ReactiveOAuth2AuthorizedClientManager;

Mono<OAuth2AuthorizedClient> authorize(
    OAuth2AuthorizeRequest authorizeRequest
);
~~~

Possible outcomes on subscription:

| Outcome | Meaning |
|---|---|
| Emits `OAuth2AuthorizedClient` | A valid authorized client is available with an access token usable per policy |
| `Mono.empty()` | Could not issue/return an authorized client in the current context; provider/grant may not apply |
| `Mono.error(...)` | OAuth2 authorization or the transport/storage layer encountered an error |

**Do not treat `Mono.empty()` as a valid blank token**, and never build an empty Bearer header to call a Resource Server.

### 9.1. Reactive Publishers Are Usually Lazy

Writing:

~~~java
Mono<OAuth2AuthorizedClient> publisher = manager.authorize(request);
~~~

does not mean the token endpoint has already been called. The publisher must be subscribed to by the Reactor pipeline/framework.

Avoid:

~~~java
// Do not invoke inside a service and discard the result:
manager.authorize(request).subscribe();

// Do not block inside the Reactor Netty event loop:
OAuth2AuthorizedClient client = manager.authorize(request).block();
~~~

Instead, **return the Mono or compose with flatMap** so cancellation, errors, and lifecycle remain managed.

## 10. Building OAuth2AuthorizeRequest for a Service Principal

The manager needs the **registration** and **principal**:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;

OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("reports-service")
        .principal("reports-scheduler")
        .build();
~~~

Here:

- `reports-service` is the **ClientRegistration ID** in YAML.
- `reports-scheduler` is a stable principal name used for the job's authorized-client storage.
- That principal string **does not** prove a human user named reports-scheduler logged in.
- When using `client_credentials`, the token represents the **client/service**, not that principal string as an IdP user account.

### 10.1. Why Must a Principal Still Be Passed?

Authorized clients are typically stored under a key like:

~~~text
(clientRegistrationId, principalName)

("reports-service", "reports-scheduler")
~~~

The principal name partitions token state across consumers/contexts in the store. For a job sharing the same policy and permissions, choose a **stable, backend-managed name**.

Do not generate a new random UUID as the principal on every run if your goal is to **reuse the authorized client** while the token is still valid: each call would create a new storage key.

### 10.2. Do Not Accept Principal Names from Untrusted Input

Do not design:

~~~http
POST /internal/run-report?principalName=admin HTTP/1.1
~~~

and then pass `.principal("admin")` to retrieve another account's stored token. For service tokens, the principal must come from controlled backend configuration; for user-authorized tokens, it must come from a verified Authentication.

## 11. ReportsGateway: Acquiring a Token via Manager and Calling WebClient

A clear, low-context-coupling design is to **explicitly fetch the authorized client in the service**, then attach the access token to the request to the Reports API:

~~~java
package com.example.portal.reports;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ReportsGateway {

    private final ReactiveOAuth2AuthorizedClientManager manager;
    private final WebClient reportsWebClient;

    public ReportsGateway(
        @Qualifier("reportsAuthorizedClientManager")
        ReactiveOAuth2AuthorizedClientManager manager,
        @Qualifier("reportsWebClient") WebClient reportsWebClient
    ) {
        this.manager = manager;
        this.reportsWebClient = reportsWebClient;
    }

    public Mono<DailySummary> fetchDailySummary() {
        OAuth2AuthorizeRequest authorization =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("reports-service")
                .principal("reports-scheduler")
                .build();

        return manager.authorize(authorization)
            .switchIfEmpty(Mono.error(
                new IllegalStateException(
                    "No authorized client for reports-service"
                )
            ))
            .flatMap(client -> reportsWebClient.get()
                .uri("/api/daily-summary")
                .headers(headers -> headers.setBearerAuth(
                    client.getAccessToken().getTokenValue()
                ))
                .retrieve()
                .bodyToMono(DailySummary.class)
            );
    }
}
~~~

In the example above, `DailySummary` is an application-defined business DTO. `reportsWebClient` must have its base URL, timeout, and transport security configured separately.

**Step-by-step explanation:**

1. Build `OAuth2AuthorizeRequest` for the registration + service principal.
2. `manager.authorize(...)` loads or acquires a token per the grant.
3. `switchIfEmpty(...)` prevents continuing if the manager returns no authorized client.
4. `flatMap(...)` uses the retrieved access token to call the Reports API.
5. `bodyToMono(DailySummary.class)` decodes the response.

This is a **server-to-server** design. The Bearer token **must never be returned to the browser**.

### 11.1. Dedicated WebClient Bean

~~~java
package com.example.portal.reports;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class ReportsWebClientConfig {

    @Bean("reportsWebClient")
    WebClient reportsWebClient(
        WebClient.Builder builder,
        @Value("${reports.api.base-url}") String baseUrl
    ) {
        return builder
            .baseUrl(baseUrl)
            .build();
    }
}
~~~

The `WebClient.Builder` provided by Spring Boot may already incorporate the app's HTTP transport/codec configuration. For production, add timeouts, TLS, proxy, and observability settings; never use a dynamic base URL supplied by untrusted input.

### 11.2. Scoping Where the Bearer Token Is Sent

The `headers.setBearerAuth(...)` pattern attaches the token to the targeted request. If the WebClient can invoke **arbitrary absolute URLs** from external input, a request to a malicious host could leak the token.

Restrict requests to the Reports API via a fixed **base URL/allowlisted destinations**, and never automatically forward Bearer headers across redirects to untrusted hosts.

## 12. Can ServerOAuth2AuthorizedClientExchangeFilterFunction Be Used?

Spring Security Reactive's WebClient integration includes:

~~~java
org.springframework.security.oauth2.client.web.reactive.function.client
    .ServerOAuth2AuthorizedClientExchangeFilterFunction
~~~

The filter has a constructor accepting `ReactiveOAuth2AuthorizedClientManager`. It can resolve the authorized client when WebClient calls an API, depending on request attributes/principal context.

However, **a background job has no WebFlux request and usually no user ReactiveSecurityContextHolder**. If using the OAuth2 filter instead of explicit `manager.authorize(...)`, you must supply a **trusted clientRegistrationId and principal context** per your Spring Security version's API, and verify the filter works with a service-based manager without a ServerWebExchange.

Basic configuration example:

~~~java
ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
    new ServerOAuth2AuthorizedClientExchangeFilterFunction(
        reportsAuthorizedClientManager
    );

WebClient client = WebClient.builder()
    .baseUrl("https://reports.example.test")
    .filter(oauth2)
    .build();
~~~

This snippet only **registers the filter**. When making API calls, you still must select the registration and supply the proper principal context. For a straightforward scheduled job, the **explicit manager.authorize + setBearerAuth** pattern in section 11 is often easier to control and test.

**Never use `ServletOAuth2AuthorizedClientExchangeFilterFunction` or `HttpServletRequest` in a background WebFlux service to resolve tokens.**

## 13. @Scheduled with Reactive Return Types: Avoid Careless Manual Subscriptions

Starting in **Spring Framework 6.1+**, Spring scheduling supports methods returning a `Publisher`, such as `Mono<Void>`. The framework takes the Publisher and subscribes according to the configured schedule.

Example:

~~~java
package com.example.portal.reports;

import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableScheduling
public class SchedulingConfig {
}
~~~

Job:

~~~java
package com.example.portal.reports;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class ReportsScheduler {

    private final ReportsGateway gateway;
    private final ReportsPersistence persistence;

    public ReportsScheduler(
        ReportsGateway gateway,
        ReportsPersistence persistence
    ) {
        this.gateway = gateway;
        this.persistence = persistence;
    }

    @Scheduled(
        fixedDelayString = "${reports.job.fixed-delay-ms:60000}"
    )
    public Mono<Void> run() {
        return Mono.defer(() ->
            gateway.fetchDailySummary()
                .flatMap(persistence::saveSummary)
        );
    }
}
~~~

`ReportsPersistence` is an application-defined abstraction; assume `saveSummary(DailySummary)` returns `Mono<Void>`. If persistence uses blocking JDBC, do not invoke it directly on the Reactor event loop; use an appropriate scheduling mechanism or a non-blocking storage client.

### 13.1. Why Use Mono.defer()?

Reactive scheduling works by constructing the Publisher once when the framework registers the scheduled task, then **re-subscribing** on each cycle.

`Mono.defer(...)` ensures each subscription rebuilds the unit of work:

~~~text
Cycle 01 -> defer -> manager.authorize -> call Reports API
Cycle 02 -> defer -> manager.authorize -> call Reports API
Cycle 03 -> defer -> manager.authorize -> call Reports API
~~~

If code constructs token requests, timestamps, job inputs, or side effects **eagerly** when creating the Publisher, work may not be recomputed as intended. `Mono.defer` keeps the boundary of **each execution** clear.

### 13.2. Error Signals in Reactive Scheduled Tasks

Errors from the token endpoint or Reports API flow through Reactor error signals. Spring's reactive scheduled processing records errors via its scheduling mechanism, but **do not rely solely on default logs** when a job has an SLA or requires alerting.

Example:

~~~java
return Mono.defer(() -> gateway.fetchDailySummary()
    .flatMap(persistence::saveSummary))
    .doOnError(error ->
        metrics.recordFailure("reports-scheduler", error))
    .onErrorResume(error ->
        notificationService.alertJobFailure(error)
            .then(Mono.empty()));
~~~

`metrics` and `notificationService` are application-defined services, not Spring Security APIs. Only return `Mono.empty()` after recording the failure if that genuinely matches business policy; never turn a system failure into a silent "job succeeded" without auditing.

### 13.3. What About Older Spring Framework Versions?

If running a Spring Framework version without reactive return-type support in `@Scheduled`, you need a **scheduler adapter** or a runtime that explicitly manages subscriptions. Do not simply write `@Scheduled public Mono<Void> run()` assuming the framework will subscribe if the version does not support it.

If you must call `subscribe()` manually, manage the `Disposable`, error callbacks, cancellation/shutdown, and concurrency; avoid fire-and-forget where the application cannot track progress.

## 14. Fixed-Delay, Cron, and Overlapping Executions

Two configurations:

~~~java
@Scheduled(fixedDelayString = "${reports.job.fixed-delay-ms}")
~~~

and:

~~~java
@Scheduled(
    cron = "0 0 1 * * *",
    zone = "Asia/Ho_Chi_Minh"
)
~~~

have different semantics:

- **Fixed delay:** interval after the previous execution finishes per scheduler rules.
- **Cron:** trigger time according to the specified expression and time zone.

With reactive tasks, understand how your framework version's scheduler subscribes and waits for publisher completion. If a job runs longer than its period or runs across multiple replicas, **overlap** can occur.

### 14.1. @Scheduled Is Not a Distributed Lock

Two instances running simultaneously:

~~~text
Node A 01:00 -> Reports Job
Node B 01:00 -> Reports Job
~~~

Each node can acquire an access token and call the Reports API. If report aggregation must run only once, you need a **distributed lock/leader election/queue consumer group/idempotency** at the business layer.

The OAuth2 manager **does not guarantee exactly-once execution**. It only manages authorized clients.

### 14.2. Do Not Use the Token Cache as an Execution Lock

Both jobs sharing `(reports-service, reports-scheduler)` does not prove only one job is running. The authorized-client service only stores tokens and is not a mutual-exclusion mechanism for scheduled tasks.

## 15. Token Lifecycle in client_credentials

Suppose the Authorization Server issues:

~~~text
01:00:00  AT-1 issued, expiresAt = 01:05:00.
01:01:00  Job runs, manager can reuse AT-1.
01:04:30  Job runs, manager sees AT-1 nearing expiration per clock skew.
01:04:31  client_credentials provider requests AT-2.
01:05:00  AT-1 expires.
~~~

This is an example; exact timing depends on `expiresAt`, clock skew, manager/provider configuration, and when something **calls the manager**.

### 15.1. New Tokens Can Still Be Acquired Without a Refresh Token

With `client_credentials`, when AT-1 expires, the provider requests a **new access token via the client_credentials grant**. No `refresh_token` is needed.

~~~text
Authorization Code + Refresh Token:
  access token expires
  -> use refresh token if still valid

Client Credentials:
  access token expires
  -> client authenticates at token endpoint to obtain a new access token
~~~

Do not add the `offline_access` scope just to "force a refresh token" for every client credentials registration. Token issuance and lifecycle must follow the Authorization Server's contract.

### 15.2. Holding a Token Until the Exact Moment of Expiry Is Not Ideal

A token takes time to travel to the Resource Server. If you only request a new token when `Instant.now() > expiresAt`, requests could arrive at the API right after expiration.

Providers normally apply **clock skew** to treat tokens as nearing expiration and renew them slightly early.

## 16. Customizing the client_credentials Provider and Clock Skew

When you need finer control over when a new token is requested:

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.client
    .ClientCredentialsReactiveOAuth2AuthorizedClientProvider;

ClientCredentialsReactiveOAuth2AuthorizedClientProvider provider =
    new ClientCredentialsReactiveOAuth2AuthorizedClientProvider();

provider.setClockSkew(Duration.ofSeconds(60));
~~~

Then attach the provider to the service manager:

~~~java
AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager =
    new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
        registrations,
        authorizedClientService
    );

manager.setAuthorizedClientProvider(provider);
~~~

Here `registrations` and `authorizedClientService` are the same dependencies as in section 8. This snippet illustrates an **alternative to constructing the provider via the builder**, not configuring a second manager with the same name in the application.

**Clock skew** makes the provider treat the access token as expiring earlier; it **does not** change:

- The access token lifetime issued by the Authorization Server.
- Web user session timeouts.
- Refresh token TTL (if present).
- Permission policies at the Resource Server.

If an access token lives only 90 seconds and clock skew is 60 seconds, the job will re-request tokens frequently. Choose values based on token lifetime, network latency, and token endpoint limits.

## 17. Customizing the Reactive HTTP Token Response Client

The `client_credentials` provider needs an HTTP client dedicated to calling the Authorization Server token endpoint. Spring Security provides:

~~~java
org.springframework.security.oauth2.client.endpoint
    .WebClientReactiveClientCredentialsTokenResponseClient
~~~

Example configuring the token WebClient with Reactor Netty:

~~~java
import java.time.Duration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.security.oauth2.client.endpoint
    .WebClientReactiveClientCredentialsTokenResponseClient;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

HttpClient httpClient = HttpClient.create()
    .responseTimeout(Duration.ofSeconds(5));

WebClient tokenWebClient = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(httpClient))
    .build();

WebClientReactiveClientCredentialsTokenResponseClient tokenClient =
    new WebClientReactiveClientCredentialsTokenResponseClient();

tokenClient.setWebClient(tokenWebClient);
~~~

Then:

~~~java
ClientCredentialsReactiveOAuth2AuthorizedClientProvider provider =
    new ClientCredentialsReactiveOAuth2AuthorizedClientProvider();

provider.setAccessTokenResponseClient(tokenClient);
provider.setClockSkew(Duration.ofSeconds(30));
~~~

**This configures the token endpoint transport**, not the HTTP client that calls the Reports API.

~~~text
WebClient A: Authorization Server token endpoint
  -> POST /token, client_credentials

WebClient B: Reports Resource Server
  -> GET /api/daily-summary, Bearer access token
~~~

Adjusting timeouts on WebClient B **does not automatically change** timeouts on WebClient A. Both require independent timeout/TLS/proxy settings as needed.

### 17.1. Never Disable TLS Verification

Never fix token endpoint errors by trusting all certificates. Client secrets and token responses are sensitive data; use HTTPS, valid truststores/CAs, and mTLS when required by the provider.

Never enable wire logging containing `Authorization: Basic ...`, client secrets, or access token responses in production.

## 18. When the Manager Returns Mono.empty()

Code should not assume `authorize()` always emits a token:

~~~java
return manager.authorize(request)
    .switchIfEmpty(Mono.error(
        new IllegalStateException(
            "No authorized client for reports-service"
        )
    ));
~~~

Common causes:

- No matching `ClientRegistration`.
- The registration uses a grant not supported by the provider chain.
- The context does not supply data required by the grant.
- The manager/provider could not produce an authorized client per contract without throwing an error.

**Never fall back to another registration's access token.** A job needing `reports.read` must never borrow the token of a user logged in with `openid profile`.

### 18.1. If Configuration Fail-Fast Is Desired

The application can verify at startup that the `reports-service` registration exists and uses the `client_credentials` grant. Checking metadata early catches misconfigurations before the job runs.

However, **do not require fetching a production token at startup** unless policy demands it; startup token requests can prevent the application from booting during a transient IdP outage. Consider readiness probes and dependency policies instead of uncontrolled hard-fails.

## 19. Token Endpoint Errors Must Be Classified

A request:

~~~http
POST /oauth2/token HTTP/1.1
Authorization: Basic <redacted>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
~~~

can fail in several ways:

| Error | Common cause | Appropriate handling |
|---|---|---|
| `invalid_client` | Wrong client secret/ID/mTLS/client authentication | Check config/rotate secret, alert operations |
| `unauthorized_client` | Client not permitted to use this grant | Check registration and Authorization Server policy |
| `invalid_scope` | Requested scope not permitted | Fix scope configuration/policy |
| HTTP 429 | Token endpoint rate limiting | Backoff/rate limit; do not retry aggressively |
| HTTP 500/503 | Authorization Server outage | Bounded retry within deadline |
| TLS handshake failure | Wrong CA/certificate/proxy/mTLS | Fix transport; never disable TLS verification |
| Timeout | Slow server/network | Bound timeouts; retry only under safe conditions |
| Reactive storage failure | Unable to read/write authorized client | Inspect store; never mask errors with a fake fallback token |

For **client_credentials**, `invalid_grant` is not as common as in the refresh-token grant, because this flow does not submit an authorization code or refresh token. When errors occur, inspect the actual error code and provider contract rather than guessing.

### 19.1. Never Swallow Errors and Return a Stale Token

Avoid:

~~~java
return manager.authorize(request)
    .onErrorResume(error -> Mono.just(oldAuthorizedClient));
~~~

The old token may have been revoked or no longer have the right scope/audience. If policy permits using an unexpired token during a brief token endpoint outage, enforce strict conditions and check Resource Server acceptance; never fall back blindly.

### 19.2. Grant Errors Are Distinct from Reports API Errors

~~~text
Token endpoint:
  fails to issue an access token to the Reports Job

Reports API:
  receives an access token but returns 401/403/500
~~~

These two error sources need separate metrics, retries, and error handling. Never retry `GET /api/daily-summary` when the job has not even acquired a valid token.

## 20. Handling HTTP 401/403 from the Reports API

The Reports API may return:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Or:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope",
                  scope="reports.admin"
~~~

Distinction:

- **401 invalid_token:** the sent token was rejected by the Resource Server; check whether the authorized client is still valid, revoked, wrong audience, or expired.
- **403 insufficient_scope:** the token may be valid yet lack the required permission; requesting a new token with the same registration/scope will not necessarily fix it.

A job may **remove an invalid authorized client** per policy and request a fresh token via `client_credentials`. Never retry infinitely: if the issuer/audience/client policy is wrong, the new token will still be rejected.

**Deleting a local authorized client** does not send a revocation request to the Authorization Server. For machine clients, credential revocation/rotation requires dedicated security and operational procedures.

## 21. Retries and Timeouts in Background Workflows

Even though a background job has no browser waiting for a response, it still needs **deadlines** so it does not hold resources indefinitely.

Example bounded GET handling:

~~~java
import java.time.Duration;
import org.springframework.web.reactive.function.client
    .WebClientResponseException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public Mono<DailySummary> fetchWithRetry() {
    Retry retry = Retry.backoff(2, Duration.ofMillis(250))
        .maxBackoff(Duration.ofSeconds(1))
        .jitter(0.3)
        .filter(error ->
            error instanceof WebClientResponseException response
                && (
                    response.getStatusCode().value() == 502
                    || response.getStatusCode().value() == 503
                    || response.getStatusCode().value() == 504
                )
        );

    return fetchDailySummary()
        .timeout(Duration.ofSeconds(3))
        .retryWhen(retry)
        .timeout(Duration.ofSeconds(8));
}
~~~

**Note:** this illustrates the concept of bounded retries for **GET**. In the `ReportsGateway` class from section 11, `fetchDailySummary()` also includes `manager.authorize()`, so retrying the whole pipeline may call the manager again. If you want to retry **only the downstream HTTP call**, place the retry on the WebClient call after the token is resolved and errors are classified.

Never retry client credentials errors like `invalid_client`, `unauthorized_client`, or `invalid_scope` under the same 502/503 policy.

### 21.1. Retrying POST or Report Writes

If a job sends:

~~~http
POST /api/reports/generate HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{"period":"2026-11"}
~~~

and times out after the server already created the report, retrying can produce **duplicate reports/side effects**.

For write operations, require an idempotency key/business operation ID and deduplication contract on the Reports API. A timeout does not prove the downstream service did not process the request.

## 22. Multiple Jobs Sharing One Client Registration

Suppose:

~~~text
ReportsJobA: revenue aggregation job
ReportsJobB: operations aggregation job
ReportsJobC: analytics fetch job
~~~

All three invoke the manager with:

~~~text
registrationId = reports-service
principalName = reports-scheduler
~~~

They can share the same authorized client/tokens **if they genuinely share the same service identity, scopes, and security policy**.

Advantages:

- Reduces unnecessary token requests.
- Reuses tokens while still valid.
- Shares the service principal's lifecycle/persistence.

Risks:

- A job might hold broader permissions than needed if all share one client.
- Concurrent requests might simultaneously request new tokens.
- Cleanup errors in one job could wipe a usable token needed by another.
- If jobs belong to different tenants, sharing tokens can break isolation.

**Principle of least privilege:** just because sharing is easy does not mean you should share. If two jobs have different privileges/tenants, separate their registrations or enforce clear scope/security policies.

## 23. Multi-Tenancy and Service Principals

Suppose a system serves multiple tenants:

~~~text
Tenant A -> Reports API for A
Tenant B -> Reports API for B
~~~

Do not assume:

~~~text
principalName = tenant-A
~~~

automatically makes a token "Tenant A's token". The principal string is just a **storage key** in OAuth2 Client; neither the Authorization Server nor the Reports API implicitly trusts it.

If each tenant has its own OAuth client credentials/issuer, separate registrations and authorized-client storage per security policy. If sharing one service credential, the API must verify tenant/resource authorization independently; never trust a tenant ID asserted by the job without validation.

**Never let an untrusted queue message freely choose a registration ID** to pick a higher-privileged token. Job inputs must be authenticated/authorized and mapped to backend-controlled registrations.

## 24. Tasks Running on Behalf of Users: Different from client_credentials

Some workers do not run under a machine identity, but need to call APIs **on behalf of an employee who granted consent**. For instance, an employee explicitly schedules a personal data export.

In that case:

~~~text
User previously completed Authorization Code Flow
  -> Application stored the user's authorized client with proper consent
  -> Background worker needs to use the refresh token (if issued)
  -> Worker calls API under the authorized user's identity
~~~

Technically, a service-based reactive manager can be configured with the `refreshToken()` provider to handle an **existing authorized client** that has a refresh token and matching principal.

However, strict security conditions must be met:

1. **The user explicitly granted permission** for background execution per policy.
2. Tokens/refresh tokens are stored securely with bounded retention.
3. The job identifies the exact user and granted scopes, never choosing an arbitrary principal name.
4. Mechanisms exist to stop processing when the user cancels the schedule, revokes consent, disables their account, or authorization expires.
5. Never treat a refresh token as proof the user still has an active WebFlux session.
6. Never mint or fake tokens from `sub` or email.

### 24.1. Provider Chain for an Existing User Authorized Client

~~~java
ReactiveOAuth2AuthorizedClientProvider provider =
    ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .refreshToken()
        .build();
~~~

This is **an option for a different use case**; do not replace the Reports Job's `clientCredentials()` provider if the Reports Job needs machine identity.

Note: the refresh provider only works when the **authorized client has a refresh token**. You cannot start an interactive Authorization Code Flow from a browserless scheduled job merely by adding `.authorizationCode()`.

### 24.2. When Should User Tokens Not Be Used in a Job?

If a job only gathers system-wide metrics with minimal service permissions, using `client_credentials` with clear scopes is simpler and avoids depending on individual user refresh tokens.

Conversely, if data requires per-user authorization/consent, **a machine token must never replace a user token** to bypass authorization checks.

## 25. Authenticated Users in WebFlux vs Jobs Without SecurityContext

In a WebFlux request, the principal can be obtained from Reactor SecurityContext:

~~~java
ReactiveSecurityContextHolder.getContext()
    .map(context -> context.getAuthentication());
~~~

Yet in a job triggered by a scheduler:

~~~text
No user request
No browser cookie
No WebSession/ServerWebExchange
No default user SecurityContext
~~~

Therefore, avoid:

~~~java
// Wrong expectation in a scheduled job:
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
~~~

ThreadLocal-based `SecurityContextHolder` is not the mechanism for locating a user in a reactive background pipeline. If a job requires user consent, it must receive an **application-authorized user identifier** from a verified job payload and map it to the authorized client per policy.

### 25.1. Never Spoof an Authentication for Another User

Constructing an `Authentication` with username "admin" does not prove the job is permitted to use the admin token. `OAuth2AuthorizedClientService` keys tokens by principal name; that is a **lookup index**, not an identity verification mechanism.

If the app exposes an API that triggers jobs, enforce authorization on that API before enqueuing; queue messages and workers also require proper integrity/identity context.

## 26. The Manager Does Not Replace the Token Response Client

`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` **coordinates** authorized clients. It is not itself an HTTP client posting to the token endpoint.

Layering:

~~~text
AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
    |
    +--> ReactiveOAuth2AuthorizedClientProvider
            |
            +--> ReactiveOAuth2AccessTokenResponseClient<...>
                    |
                    +--> WebClient HTTP POST /token
~~~

For `client_credentials`, the corresponding token-response client is:

~~~java
ReactiveOAuth2AccessTokenResponseClient<
    OAuth2ClientCredentialsGrantRequest
>
~~~

For the refresh-token grant, the corresponding request type is `OAuth2RefreshTokenGrantRequest`. Do not use the Authorization Code Flow's token response client merely because it also returns an access token.

## 27. Failure Handlers and Authorized Client Cleanup

The manager can apply **authorization success/failure handlers** to save or remove authorized clients based on outcomes and policy. When relying on default implementations, understand your running version's behavior before replacing handlers.

Several scenarios:

| Error | Should tokens be deleted? |
|---|---|
| `invalid_client` at token endpoint | Do not delete all tokens for every user/service; this may be a config/secret error |
| Old access token expired, new token acquired | Save the new authorized client |
| `invalid_grant` when refreshing a user token | May remove the failing authorized client per policy |
| Reports API returns `401 invalid_token` | May clean up the corresponding service token once the error is verified |
| Reports API returns `403 insufficient_scope` | Token may be valid; do not clean up just because scope is insufficient |
| Reports API returns `503` | Insufficient evidence that the token is bad |
| Token store timeout | Do not substitute a fake token or delete everything |

**Removing a local authorized client** is not the same as **revoking a token** at the Authorization Server. If a service credential is compromised, execute an actual revocation/rotation plan; deleting a row from the store is not enough to remediate an incident.

### 27.1. Background Job Failures Must Not Log Out Users

If the Reports Job is denied a token, employees can continue using the Employee Portal. Those are two distinct security contexts and client registrations.

Never invalidate all WebSessions just because `reports-service` hit `invalid_client` or a 503 from the Authorization Server.

## 28. Multi-Instance Environments and Token Acquisition Races

Two replicas:

~~~mermaid
sequenceDiagram
    participant A as Job Node A
    participant B as Job Node B
    participant S as Authorized Client Store
    participant AS as Authorization Server

    A->>S: load(reports-service, reports-scheduler)
    B->>S: load(reports-service, reports-scheduler)
    S-->>A: Old/expiring token
    S-->>B: Old/expiring token
    A->>AS: client_credentials
    B->>AS: client_credentials
    AS-->>A: AT-2
    AS-->>B: AT-3
    A->>S: save(AT-2)
    B->>S: save(AT-3)
~~~

With client credentials, both token requests may succeed, yet they add load to the Authorization Server and cause back-to-back overwrites in storage.

Mitigation approaches:

- Use shared storage when authorized clients genuinely need to be shared across nodes.
- Limit concurrency with a lock/single-flight keyed by registration/principal if cost and load warrant it.
- Apply client-side rate limiting and backoff toward the token endpoint.
- Never expect local `synchronized` blocks to lock across multiple replicas.
- Separate **exactly-once job orchestration** from **token coordination**.

### 28.1. If the Flow Uses Refresh Token Rotation

For a background job genuinely acting on a user's behalf with a refresh token, two requests submitting the same RT-1 can cause `invalid_grant` or trigger reuse detection at the OP.

That case demands consistency/locking and saving the new RT. **Client credentials normally have no refresh token**, so rotation risk is not the default case for the Reports Job in this lesson.

## 29. Storage, Security, and Secret Rotation

A service may run for months, so **client credentials** must be managed carefully:

1. Store `client-secret` in a secret manager/store with strict permissions.
2. Never put secrets in source code or CI logs.
3. Have a rotation procedure for secrets/certificates without unnecessary full-system downtime.
4. Monitor for `invalid_client` after rotations.
5. Protect the token store with access control, TLS, and encryption if policy requires.
6. Avoid putting tokens in metric labels, exception messages, or HTTP access logs.
7. Never return access/refresh tokens through a "debug" API to the frontend.
8. Restrict egress to allowlisted token endpoints and Resource Servers.

**Never fix TLS errors by disabling certificate verification.** That exposes client secrets and access tokens to man-in-the-middle attacks.

### 29.1. Client Assertion / mTLS

Some Authorization Servers require client authentication via mTLS or `private_key_jwt` instead of `client_secret_basic`. In that case, registration and token-response transport settings must match the contract. The token manager can still be `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`, while the **token response client** and client authentication method must be configured appropriately.

## 30. Monitoring Background Tasks with Metrics and Audits

A job can fail when nobody is looking at the UI. Therefore, logs/metrics and alerts matter more than a UI popup.

Recommended signals to monitor:

| Metric/event | Meaning |
|---|---|
| Job triggered | Scheduler actually fired |
| Authorization attempted | Manager was invoked |
| Token acquisition success | Access token issued or reused |
| Token endpoint latency | IdP responsiveness |
| Authorized-client load/save failure | Persistence failure |
| HTTP 401/403 from Reports API | Invalid token or insufficient permissions |
| HTTP 429/503 from Reports API | Rate limiting/outage |
| Job success/failure | Final business outcome |
| Job duration | Latency vs schedule and SLO |
| Overlapping executions | Concurrent runs overlapping |
| Stale report age | How outdated the report has become |

Never log:

~~~text
client_secret=<real-secret>
access_token=<real-token>
refresh_token=<real-token>
Authorization: Bearer <real-token>
~~~

Log controlled registration IDs, error codes, durations, correlation IDs, and job IDs. Never use tokens or user emails as metric labels due to data leakage and high cardinality.

## 31. Testing the Manager Without an HTTP Request

To test with the right focus, tests should prove:

1. The manager acquires tokens **without a ServerWebExchange**.
2. `OAuth2AuthorizeRequest` uses the right registration and service principal.
3. The manager uses service-based storage.
4. While the access token is still valid, the provider does not unnecessarily request a new one.
5. When a token needs reissuing, the `clientCredentials()` provider works.
6. Token endpoint errors propagate through the Reactor error signal.
7. The job actually uses the manager's token when calling the Reports API.
8. There is no dependency on user login or HTTP sessions.

### 31.1. Testing with StepVerifier and a Fake Manager

Example creating a fake authorized client to test `ReportsGateway`:

~~~java
import java.time.Instant;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReportsGatewayTest {

    @Test
    void managerCanProvideServiceAuthorizedClientWithoutWebExchange() {
        ClientRegistration registration =
            ClientRegistration.withRegistrationId("reports-service")
                .clientId("test-service")
                .clientSecret("test-secret")
                .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                    AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri("https://login.example.test/token")
                .scope("reports.read")
                .build();

        Instant now = Instant.now();
        OAuth2AccessToken accessToken = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "FAKE_SERVICE_TOKEN",
            now.minusSeconds(10),
            now.plusSeconds(300),
            Set.of("reports.read")
        );

        OAuth2AuthorizedClient client = new OAuth2AuthorizedClient(
            registration,
            "reports-scheduler",
            accessToken
        );

        ReactiveOAuth2AuthorizedClientManager fakeManager =
            request -> Mono.just(client);

        StepVerifier.create(fakeManager.authorize(
                org.springframework.security.oauth2.client
                    .OAuth2AuthorizeRequest
                    .withClientRegistrationId("reports-service")
                    .principal("reports-scheduler")
                    .build()
            ))
            .assertNext(actual ->
                org.junit.jupiter.api.Assertions.assertEquals(
                    "reports-scheduler", actual.getPrincipalName()
                ))
            .verifyComplete();
    }
}
~~~

This test verifies the **contract/service principal** of a fake manager. It **does not prove** a real manager sends HTTP requests to the Authorization Server. In integration tests, use the real manager with a mocked token-response client or mock HTTP server to verify grant logic.

### 31.2. Testing the HTTP Authorization Header

Using a mock WebClient `ExchangeFunction` to inspect requests without network calls:

~~~java
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReportsHttpTest {

    @Test
    void sendsBearerTokenToExpectedReportsEndpoint() {
        AtomicReference<String> authorization = new AtomicReference<>();

        ExchangeFunction fakeHttp = request -> {
            authorization.set(
                request.headers().getFirst(HttpHeaders.AUTHORIZATION)
            );
            return Mono.just(ClientResponse.create(HttpStatus.OK)
                .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                .body("{\"total\":7}")
                .build());
        };

        WebClient reportsWebClient = WebClient.builder()
            .baseUrl("https://reports.example.test")
            .exchangeFunction(fakeHttp)
            .build();

        StepVerifier.create(reportsWebClient.get()
            .uri("/api/daily-summary")
            .headers(headers -> headers.setBearerAuth("FAKE_SERVICE_TOKEN"))
            .retrieve()
            .bodyToMono(String.class))
            .expectNext("{\"total\":7}")
            .verifyComplete();

        assertEquals("Bearer FAKE_SERVICE_TOKEN", authorization.get());
    }
}
~~~

This tests **HTTP header behavior**, not the full manager. A more valuable integration test wires both the fake manager and mock WebClient into `ReportsGateway`, asserting the registration ID/principal and verifying the token is never sent to another host.

### 31.3. Testing Errors and Empty Publishers

~~~java
ReactiveOAuth2AuthorizedClientManager emptyManager =
    request -> Mono.empty();

ReactiveOAuth2AuthorizedClientManager failingManager =
    request -> Mono.error(
        new IllegalStateException("Simulated token failure")
    );
~~~

Check `ReportsGateway`:

- When manager emits `Mono.empty()`: the Reports API must not be called.
- When manager emits `Mono.error(...)`: the error propagates and the job records a failure.
- When manager emits a client: the request carries the expected fake Bearer token.
- Never use another user's token as a "fallback".

### 31.4. Testing Reactive @Scheduled

For Spring Framework 6.1+ `@Scheduled`, tests should verify **each subscription re-executes the logic** inside `Mono.defer(...)`, rather than reusing a stale result from an eagerly built publisher.

If integration-testing schedules, use appropriate scheduler/test-clock configuration and avoid long sleeps that make CI flaky. Do not simply assert the method returns `Mono<Void>` and assume the job actually ran.

## 32. Symptom-Based Troubleshooting

| Symptom | Possible cause | Investigation steps |
|---|---|---|
| Job fails due to missing `ServerWebExchange` | Using `DefaultReactiveOAuth2AuthorizedClientManager` for background work | Switch to the service-based reactive manager |
| Manager bean exists but job does not use it | Wrong bean injected or `authorize` not called | Check constructor injection/qualifiers |
| Job never acquires a token | `Mono` never subscribed or older `@Scheduled` lacks Publisher support | Check Reactor lifecycle / Spring Framework version |
| Re-requests token every run despite valid AT | Unstable principal name, non-persistent store, or provider/clock skew | Inspect key, `expiresAt`, store |
| `Mono.empty()` from manager | Incompatible grant or missing registration/context | Check provider chain and request |
| `invalid_client` | Wrong client secret/ID/mTLS | Check secrets and token endpoint config |
| `unauthorized_client` | Client not permitted to use `client_credentials` | Check AS policy |
| `invalid_scope` | `reports.read` scope not granted | Check ClientRegistration/AS permissions |
| Reports API returns 401 | Wrong audience/revoked/expired token | Check Bearer error and manager lifecycle |
| Reports API returns 403 | Insufficient scope or resource permission | Do not retry blindly; check authorization |
| Token endpoint timeout | Network/IdP latency | Check HTTP token response client, not just API WebClient |
| Fails only across multiple nodes | Separate in-memory stores or concurrency | Use shared store, locking, idempotency |
| One job wipes another job's token | Shared registration/principal with overly broad cleanup | Separate policy and storage keys |
| Job runs twice | Two replicas both running `@Scheduled` or overlap | Use distributed lock/queue/idempotency |
| Job requests a new token after restart | In-memory authorized client service lost state | Expected behavior for in-memory stores |
| Token exposed in logs | HTTP wire logging/debug exposing credentials | Disable raw body/header logging; rotate exposed credentials |
| WebClient OAuth2 filter fails with missing principal | Background job has no user SecurityContext | Supply service principal context properly or call manager explicitly |
| Job exists yet no reports appear | Mono failed and was swallowed into empty | Add explicit metrics/audit/error signals |

**Investigation order:** check **schedule trigger → subscription → OAuth2AuthorizeRequest → manager/provider → authorized-client service → token endpoint → WebClient → Reports API → persistence**.

## 33. Common Anti-Patterns

**1. Using the WebFlux request manager in a job without a ServerWebExchange.** Use the service manager.

**2. Reading `SecurityContextHolder` inside a Reactor scheduled job and assuming it holds the current user.** Background tasks have no default user web context.

**3. Treating `client_credentials` as if a user had granted consent.** Machine identity and user identity are separate security boundaries.

**4. Manually POSTing `/token`, caching tokens, and computing expiry in ad-hoc logic across every job.** Centralize this in the OAuth2 Client manager/provider.

**5. Calling `.block()` on the event loop.** Use `Mono`/`flatMap` to remain non-blocking.

**6. Calling `.subscribe()` fire-and-forget without managing errors or disposal.** Jobs can fail silently or fail to shut down cleanly.

**7. Generating a random principal name on every run.** Causes the manager to repeatedly acquire new tokens because the storage key changes.

**8. Letting user input choose the registration ID and principal name.** Risks unauthorized token access.

**9. Passing arbitrary URLs to a WebClient that auto-attaches Bearer tokens.** Risks credential exfiltration.

**10. Assuming the manager ensures only one job runs across replicas.** OAuth2 token management is not a distributed scheduler.

**11. Retrying infinitely when the token endpoint returns `invalid_client`.** Config/credential errors cannot be fixed by retrying.

**12. Logging raw access tokens/client secrets for debugging.** Credentials must be protected and rotated if leaked.

**13. Treating an unexpired AT as a guarantee the API will accept it.** Audience, scopes, revocation, and business permissions are still checked by the Resource Server.

**14. Treating a refresh token as mandatory in `client_credentials`.** This grant normally requests a fresh access token directly.

## 34. Practice Exercises

### Exercise 1 — Choosing the Scheduler Manager

An hourly job uses `client_credentials` and has no HTTP request:

~~~text
ReactiveClientRegistrationRepository
ReactiveOAuth2AuthorizedClientService
Reports Job
~~~

**Question:** Which manager should be used?

**Solution:** `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` with the `clientCredentials()` provider. It does not require a `ServerWebExchange`.

### Exercise 2 — Changing Principal Name

A job builds:

~~~java
.principal(UUID.randomUUID().toString())
~~~

on every execution.

**Question:** Why is the token never reused?

**Solution:** The authorized-client service keys entries by registration/principal; each new UUID is treated as a distinct identity in storage. For a service job sharing the same authority, use a stable backend-managed principal name.

### Exercise 3 — No Refresh Token

~~~text
ClientRegistration.grant = client_credentials
OAuth2AuthorizedClient.accessToken = AT-1
OAuth2AuthorizedClient.refreshToken = null
~~~

**Question:** Can the job obtain a new access token when AT-1 expires?

**Solution:** Yes, provided the client credentials remain valid and the provider/manager are properly configured. The manager uses the `client_credentials` grant to request a new token without needing a refresh token.

### Exercise 4 — Job Not Executing

~~~java
@Scheduled(fixedDelay = 60000)
public Mono<Void> run() {
    return reportsGateway.fetchDailySummary().then();
}
~~~

The application uses an older Spring Framework version without reactive scheduling support.

**Question:** Can you assume the publisher will be subscribed to?

**Solution:** No. Verify that the Spring Framework version supports reactive `@Scheduled`. Otherwise, build a scheduler adapter that manages subscription/errors/cancellation; on Spring Framework 6.1+, use `Mono.defer` so each subscription executes fresh work.

### Exercise 5 — API Returns 403

The Reports API requires `reports.admin` while the token only has `reports.read`.

**Question:** Will retrying `client_credentials` 10 times elevate permissions?

**Solution:** No. Fix the scope/permissions per Authorization Server/Resource Server policy; never rely on retries to escalate privileges.

### Exercise 6 — Two Nodes Running the Same Cron

Node A and Node B both run the Reports Job at 01:00 and write the same report.

**Question:** Does the authorized-client manager prevent creating two reports?

**Solution:** No. The manager manages access tokens, not exactly-once job execution. Use a distributed scheduling lock, queue semantics, or idempotency/business deduplication.

### Exercise 7 — Token Endpoint Timeout

The team increased the timeout on the WebClient calling the Reports API, yet the token endpoint still times out.

**Question:** What needs to be inspected?

**Solution:** The WebClient/token-response client used by the `clientCredentials()` provider. It is a separate HTTP transport from the WebClient calling the Resource Server.

### Exercise 8 — Running on Behalf of a User

An employee grants consent for a job to export personal data on a schedule; the job needs user authority.

**Question:** Can you switch to `client_credentials` to avoid handling refresh tokens?

**Solution:** Not by default. If the API requires user delegation, you must store and use the user's authorized client/refresh token according to consent and revocation policy. A machine token does not automatically carry user permissions.

## 35. Implementation Checklist

| Question | What to ensure |
|---|---|
| Does the task have a ServerWebExchange? | If not, use the service-based manager |
| Which grant does the OAuth client use? | Typically `client_credentials` for machine-to-machine |
| Is the Registration ID explicit? | `reports-service` configured by the backend |
| Is the principal name stable? | E.g., `reports-scheduler`, never user-supplied from a browser |
| Is `ReactiveClientRegistrationRepository` present? | Configured with issuer/token URI/client ID and grant |
| Is `ReactiveOAuth2AuthorizedClientService` present? | Yes, with environment-appropriate storage |
| Does the provider chain include `clientCredentials()`? | Yes, for machine grants |
| Which manager class is used? | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
| Is the Mono subscribed under proper lifecycle? | Yes, no unmanaged fire-and-forget |
| Which version runs reactive `@Scheduled`? | Spring Framework 6.1+ or an appropriate adapter |
| Does each scheduled subscription run fresh work? | Use `Mono.defer` when needed |
| Does WebClient attach tokens only to the right API? | Restricted to Reports API / allowlisted hosts |
| Does the token have the right scope/audience? | Verify AS and Resource Server policies |
| Is clock skew appropriate? | Tuned to token lifetime and network latency |
| Does the token HTTP transport have timeouts/TLS? | Yes, separate from the Reports API transport |
| Are retries bounded? | Yes, with error classification and idempotency |
| Do multiple replicas duplicate job runs? | Use distributed lock/queue/idempotency if needed |
| Is the authorized-client store shared/secured? | Yes, if required by architecture |
| Is there a client secret rotation process? | Yes, paired with `invalid_client` alerting |
| Are job failures monitored? | Metrics, safe logs, and alerts |
| Tested without web context? | Unit/integration tests for authorize without ServerWebExchange |
| Tested `Mono.empty`/error/success? | `StepVerifier` and a fake token endpoint |

## 36. Summary

`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` is the **appropriate manager for background tasks in Spring Security OAuth2 Client Reactive**, where there is no browser, WebFlux `ServerWebExchange`, or user session. It coordinates **`ReactiveClientRegistrationRepository`**, **`ReactiveOAuth2AuthorizedClientService`**, and **`ReactiveOAuth2AuthorizedClientProvider`** to load, issue, and store `OAuth2AuthorizedClient` instances via a `Mono` pipeline.

For schedulers or queue workers calling APIs under service authority, you typically configure the `clientCredentials()` provider, build `OAuth2AuthorizeRequest.withClientRegistrationId("reports-service").principal("reports-scheduler")`, and use the returned access token to call the Reports API with `WebClient`. Having no refresh token is normal for this grant; when a token needs replacement, the manager can request a new access token using client credentials again.

For stable production operation, separate the **web-request manager** from the **background-worker manager**, keep principals and registrations within strict trust boundaries, manage `Mono` and reactive scheduling properly, design timeouts/retries, prevent duplicate executions across replicas, protect tokens and secrets, and monitor Authorization Server errors. **Token management is neither user login nor job orchestration**: each responsibility belongs in its proper layer.
