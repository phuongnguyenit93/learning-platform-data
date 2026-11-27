# 16.5. Using `AuthorizedClientServiceOAuth2AuthorizedClientManager` in Jobs and Schedulers

## 1. Problem: Jobs Without a Browser or Logged-In User

A Spring Boot application may both serve users via a web UI and run periodic background tasks:

- Syncing a catalog from an internal API at 02:00 daily.
- Fetching report data on a schedule using a service account.
- Calling an invoicing or inventory API from a worker.
- Sending aggregated data to a partner system.
- Running a scheduled task to reconcile transaction states.

These tasks have no user clicking a login button, no browser to redirect to an Identity Provider, and typically no <code>HttpServletRequest</code> or HTTP session.

If you try to pull an <code>OAuth2AuthorizedClient</code> from an arbitrary user's login session, the job runs into several problems:

1. A user-bound token may expire, be revoked, or lack service permissions.
2. The job does not know which user's session and principal to use.
3. A single user logging out must not cause an infrastructure process depending on that session to fail unexpectedly.
4. Using a user token for a service task can violate audience, scope, and authorization boundaries.

For **service-to-service** needs without an End-User, OAuth 2.0 provides the **Client Credentials Grant**. Spring Security includes a manager designed for environments outside a Servlet request:

**<code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code>**.

This manager coordinates <code>ClientRegistrationRepository</code>, <code>OAuth2AuthorizedClientService</code>, and <code>OAuth2AuthorizedClientProvider</code> to obtain, reuse, and re-issue access tokens in services or background jobs.

> **Principle:** A job/scheduler running with **Client/service** permissions should use a workload-specific `ClientRegistration` and an authorized-client manager independent of HTTP requests. The <code>principal</code> acts as a token management key, **not a simulated End-User**.

## 2. Distinguishing Web Managers from Service Managers

Spring Security has two common implementations:

| Criterion | <code>DefaultOAuth2AuthorizedClientManager</code> | <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> |
|---|---|---|
| Primary context | Servlet web request | Service layer, job, scheduler, background process |
| Depends on <code>HttpServletRequest</code> | Has request/response context via repository | No |
| Authorized client storage component | <code>OAuth2AuthorizedClientRepository</code> | <code>OAuth2AuthorizedClientService</code> |
| Can handle client credentials | Yes, if configured with appropriate context | Yes, especially well-suited |
| Suitable without browser/session | Not the primary choice | Yes |
| Requires <code>ClientRegistrationRepository</code> | Yes | Yes |
| Requires matching grant provider | Yes | Yes |

These are not two different OAuth 2.0 protocols. Both implement the interface:

~~~java
org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager
~~~

The main difference lies in **context and storage mechanism**.

### 2.1. Why Should You Not Read `SecurityContextHolder` in a Scheduler?

In an authenticated web request, <code>SecurityContextHolder</code> typically holds the current user's <code>Authentication</code>. A scheduled task runs on a scheduler thread and does not inherently carry any request's `SecurityContext`.

Error-prone example:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

String principal = authentication.getName();
~~~

In a scheduled task, <code>authentication</code> may be <code>null</code>. Even if a `SecurityContext` is propagated across threads, an infrastructure job should not automatically borrow a human user's permissions to fetch a service token.

For the Client Credentials Grant, choose a **synthetic principal defined by the backend**, such as <code>nightly-sync-worker</code>, so the manager knows under which key to store the authorized client.

### 2.2. Manager Does Not Equal Token Client

Concepts to keep separate:

| Component | Role |
|---|---|
| <code>ClientRegistration</code> | Configures Client ID, client authentication, grant type, token endpoint, and scope |
| <code>OAuth2AuthorizeRequest</code> | An authorize request specifying registration and principal |
| <code>OAuth2AuthorizedClientProvider</code> | Executes the corresponding grant when conditions apply |
| <code>OAuth2AuthorizedClientManager</code> | Coordinates the provider with registration and authorized-client storage |
| <code>OAuth2AuthorizedClient</code> | `ClientRegistration` + `principalName` + access token + optional refresh token |
| <code>OAuth2AuthorizedClientService</code> | Saves, looks up, and removes authorized clients by registration/principal |

Do not confuse <code>OAuth2AuthorizedClientService</code> with <code>ClientRegistrationRepository</code>. The registration repository holds only **Client metadata**, not issued tokens.

## 3. Client Credentials Flow When a Job Runs

For a job using <code>reports-job</code>:

~~~mermaid
sequenceDiagram
    autonumber
    participant S as Spring Scheduler
    participant J as ReportsJob
    participant M as AuthorizedClientServiceOAuth2AuthorizedClientManager
    participant Store as OAuth2AuthorizedClientService
    participant OP as Authorization Server
    participant API as Reports Resource Server

    S->>J: Scheduled trigger
    J->>M: authorize(registrationId=reports-job, principal=reports-worker)
    M->>Store: loadAuthorizedClient(reports-job, reports-worker)
    alt No token yet or access token needs re-issuance
        M->>OP: POST /token, grant_type=client_credentials
        OP-->>M: Access token, expiry, scope
        M->>Store: saveAuthorizedClient
    else Current access token is still usable
        Store-->>M: Saved authorized client
    end
    M-->>J: OAuth2AuthorizedClient
    J->>API: Call API with Bearer access token
    API-->>J: Result per service permissions
    J-->>S: Run complete
~~~

This flow **has no** authorization endpoint, redirect URI, browser callback, or authorization code. The client authenticates directly with the Token Endpoint under the registered Client Credentials Grant.

An illustrative token response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "access_token": "ACCESS_TOKEN_PLACEHOLDER",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "reports.read"
}
~~~

The token value is only a placeholder. By standard design, **the Client Credentials Grant does not need a refresh token**: when the access token expires, the manager can request a new token using the same grant if the Client is still permitted.

## 4. Configuring a Dedicated `ClientRegistration` for the Job

### 4.1. Dependencies

With Spring Boot 3 / Spring Security 6, a server-side application can use:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

<code>spring-boot-starter-web</code> in this example provides convenient HTTP components, including <code>RestClient</code> on Spring Framework 6.1+ (typically Spring Boot 3.2+). A worker does not have to run a web server solely to use OAuth2 Client; you can choose HTTP client dependencies matching your architecture and disable the web application type when needed.

### 4.2. `application.yml`

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-job:
            provider: service-auth
            client-id: reports-worker
            client-secret: ${REPORTS_WORKER_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          service-auth:
            token-uri: https://auth.example.org/oauth2/token

app:
  reports-api:
    base-url: https://api.example.org
  reports-job:
    cron: "0 15 2 * * *"
~~~

Explanation:

| Property | Function |
|---|---|
| <code>registration.reports-job</code> | Internal ID for the manager to select the `ClientRegistration` |
| <code>client-id</code> | Client identifier issued by the Authorization Server |
| <code>client-secret</code> | Confidential Client secret; sourced from env vars / secret manager |
| <code>client-authentication-method</code> | How the Client authenticates at the Token Endpoint; must match OP config |
| <code>authorization-grant-type</code> | <code>client_credentials</code> |
| <code>scope</code> | Minimum API permissions the service actually needs |
| <code>provider.service-auth.token-uri</code> | Exact Token Endpoint of the Authorization Server |
| <code>app.reports-api.base-url</code> | Target Resource Server; not the Token Endpoint |
| <code>app.reports-job.cron</code> | Application schedule, not an OAuth2 Client property |

The domain, Client ID, and cron above are examples only and do not represent a real system. Credentials must be legitimately provisioned and **never committed as secret values** in source code.

The Client Credentials Grant does not need <code>redirect-uri</code>, <code>authorization-uri</code>, or the <code>openid</code> scope for End-User login. Even if the provider supports OAuth2/OIDC, sharing the same Authorization Server does not turn a service job into an OIDC Login Client.

### 4.3. Who Is the Token Issued To?

In the Client Credentials Grant, the Authorization Server issues the access token to the **Client/service identity** according to scopes and policy. The token does not inherently contain a logged-in user's identity.

<code>principal("reports-worker-runtime")</code> in the manager request is not an instruction for the OP to issue a token “on behalf of user reports-worker-runtime.” It is strictly **a principal key used to store/look up the authorized client in Spring Security**, independent of the token subject/audience decided by the OP.

## 5. Creating `AuthorizedClientServiceOAuth2AuthorizedClientManager`

Configuration example:

~~~java
package example.security;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class ReportsOAuth2ClientConfig {

    @Bean("reportsAuthorizedClientManager")
    OAuth2AuthorizedClientManager reportsAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials(configurer -> configurer
                    .clockSkew(Duration.ofSeconds(60)))
                .build();

        var manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Step by step:

1. Spring Boot creates registrations from <code>spring.security.oauth2.client.registration.*</code> when auto-configuration applies.
2. <code>ClientRegistrationRepository</code> tells <code>reports-job</code> which Client ID, grant type, scope, and token endpoint to use.
3. <code>OAuth2AuthorizedClientService</code> holds authorized clients with issued tokens; Spring Boot/Spring Security may supply a default implementation depending on configuration.
4. <code>OAuth2AuthorizedClientProviderBuilder.builder().clientCredentials()</code> enables only the **Client Credentials Grant** for this manager.
5. <code>clockSkew(Duration.ofSeconds(60))</code> treats an access token close to expiring as needing early re-issuance, preventing expiration mid-API call.
6. The manager is named <code>reportsAuthorizedClientManager</code> so the right bean can be injected when the app has multiple managers.

In production, depending on access token lifetime and clock drift, skew can be tuned smaller or larger. Skew does not extend the token's actual lifetime and does not guarantee every API request succeeds.

### 5.1. Why Select Only `clientCredentials()`?

This job needs no browser or user authorization:

~~~java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();
~~~

You do not need to add <code>authorizationCode()</code> and <code>refreshToken()</code>. Adding extra providers does not turn a registration into another grant, but it makes configuration harder to read and can open the door to unintended behavior if registrations or managers change later.

<code>OAuth2AuthorizedClientProviderBuilder</code> determines which grant providers the manager can use; <code>ClientRegistration.authorizationGrantType</code> and Authorization Server policy determine the Client's actual grant.

### 5.2. Default and Alternative Service Storage

<code>OAuth2AuthorizedClientService</code> can be:

- <code>InMemoryOAuth2AuthorizedClientService</code>: stores in process memory; fits demos/single-instance apps.
- <code>JdbcOAuth2AuthorizedClientService</code>: stores in a database using the corresponding schema; fits when persistence is needed.
- Custom implementation with encryption, caching, or distributed storage per project requirements.

An explicit in-memory bean example if the application needs manual configuration:

~~~java
@Bean
OAuth2AuthorizedClientService authorizedClientService(
        ClientRegistrationRepository registrations) {
    return new InMemoryOAuth2AuthorizedClientService(registrations);
}
~~~

Import the corresponding classes when using this snippet. **Do not create a duplicate bean when Spring Boot already auto-configures a service**, unless intentionally replacing auto-configuration with an explicit design.

Running multiple instances does not automatically mean you must share one access token; with Client Credentials, each instance can request its own token if OP policy permits. However, token rate limits, concurrent token requests, security, storage, and performance differ and must be evaluated realistically.

## 6. Creating a Scheduler and Calling the Manager from a Job

This example uses Spring Scheduling and <code>RestClient</code>. The HTTP client portion simply calls a hypothetical API returning report data.

### 6.1. Enabling Scheduling

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class ReportsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReportsApplication.class, args);
    }
}
~~~

<code>@EnableScheduling</code> activates processing of <code>@Scheduled</code>. In the Spring cron expression in this example:

~~~text
0 15 2 * * *
~~~

there are **six fields**: second, minute, hour, day of month, month, day of week. With the specified UTC timezone, the job runs at **02:15 UTC** per the cron schedule. This is not five-field Unix cron.

### 6.2. Creating a `RestClient` for the Resource Server

~~~java
package example.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class ReportsApiConfig {

    @Bean("reportsApiClient")
    RestClient reportsApiClient(
            RestClient.Builder builder,
            @Value("${app.reports-api.base-url}") String baseUrl) {
        return builder.baseUrl(baseUrl).build();
    }
}
~~~

The Token Endpoint and Resource Server are two distinct HTTP targets:

~~~text
Token Endpoint: https://auth.example.org/oauth2/token
Reports API:    https://api.example.org/v1/reports/daily
~~~

In a real system, HTTP client configuration needs timeouts, TLS validation, connection management, and response size limits. The example uses a minimal builder to keep focus on the OAuth2 manager.

### 6.3. Writing the Scheduled Job

~~~java
package example.jobs;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class DailyReportsJob {

    private static final Logger log =
        LoggerFactory.getLogger(DailyReportsJob.class);

    private static final String REGISTRATION_ID = "reports-job";
    private static final String JOB_PRINCIPAL = "reports-worker-runtime";

    private final OAuth2AuthorizedClientManager authorizedClientManager;
    private final RestClient reportsApi;

    public DailyReportsJob(
            @Qualifier("reportsAuthorizedClientManager")
            OAuth2AuthorizedClientManager authorizedClientManager,
            @Qualifier("reportsApiClient") RestClient reportsApi) {
        this.authorizedClientManager = authorizedClientManager;
        this.reportsApi = reportsApi;
    }

    @Scheduled(cron = "${app.reports-job.cron}", zone = "UTC")
    public void run() {
        OAuth2AuthorizeRequest authorizeRequest =
            OAuth2AuthorizeRequest
                .withClientRegistrationId(REGISTRATION_ID)
                .principal(JOB_PRINCIPAL)
                .build();

        OAuth2AuthorizedClient authorizedClient =
            authorizedClientManager.authorize(authorizeRequest);

        if (authorizedClient == null) {
            throw new IllegalStateException(
                "No authorized client for reports-job");
        }

        String accessToken =
            authorizedClient.getAccessToken().getTokenValue();

        String report = reportsApi.get()
            .uri("/v1/reports/daily")
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .body(String.class);

        if (report == null) {
            throw new IllegalStateException("Reports API returned no data");
        }

        // Illustration: call domain service to process report data here.
        // Do not log report contents or accessToken.
        log.info("Reports job completed, response length={}",
            report.length());
    }
}
~~~

When the job runs:

1. <code>OAuth2AuthorizeRequest</code> specifies the <code>reports-job</code> registration and the workload's synthetic principal.
2. The manager checks storage by the registration/principal pair.
3. If a usable access token already exists, the manager can return the current authorized client.
4. If there is no token or re-issuance is needed, the Client Credentials Provider sends a token request.
5. The manager saves the authorized client after successful issuance via the configured success handler.
6. The job retrieves the access token and calls the Resource Server.

The example deliberately **avoids creating an HTTP endpoint that returns the token**. The access token is used solely on the backend to call the right API.

In production, replace `String` response handling with a validated DTO, response size limits, idempotency rules, and an appropriate domain service. Never log PII or raw JSON just to inspect a job run.

### 6.4. Why Use `@Qualifier`?

An application may have:

- A web manager serving OAuth2 Login / authorization code.
- A service manager for <code>reports-job</code>.
- Another service manager for invoicing.

When multiple <code>OAuth2AuthorizedClientManager</code> beans exist, <code>@Qualifier</code> ensures injection of the exact manager with the intended provider and storage. Accidentally injecting the web manager from a scheduler without a Servlet request can fail due to missing request context or fail to authorize as expected.

## 7. `OAuth2AuthorizeRequest`: `registrationId` and `principal` Are Two Different Keys

Minimal snippet:

~~~java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("reports-job")
        .principal("reports-worker-runtime")
        .build();
~~~

Meaning:

| Field | Purpose |
|---|---|
| <code>clientRegistrationId</code> | Selects the `ClientRegistration` and its token endpoint/grant/client authentication |
| <code>principal</code> | Partitions authorized-client storage for the workload context |

An authorized client is essentially looked up in the service by:

~~~text
(registrationId, principalName)
~~~

Examples:

~~~text
(reports-job, reports-worker-runtime)
(billing-job, billing-worker-runtime)
(reports-job, tenant-a-reports-worker)
~~~

The key point is that **a synthetic principal does not become a user subject in the access token**. The Authorization Server determines the service identity, scopes, audience, and token claims.

### 7.1. How to Choose a Synthetic Principal?

Good:

~~~text
reports-worker-runtime
inventory-import-service
tenant-a-report-sync
~~~

Avoid:

~~~java
.principal(request.getParameter("principal"))
~~~

If an HTTP endpoint triggers the job, never let the caller choose the principal to look up privileged tokens. The principal key must be defined by the backend or derived from an authenticated, controlled tenant context.

### 7.2. One Registration with Multiple Synthetic Principals

With Client Credentials, if multiple principals share **one `ClientRegistration` with the same credentials/scopes/audience**, they may cause the manager to store multiple copies of access tokens for the same service identity. This does not create separate independent permissions at the Authorization Server—it only creates additional **storage buckets**.

If the goal is security isolation across tenants, changing `principalName` alone **is not enough**. You may need separate `ClientRegistration`/Client IDs, different scopes, different audiences, or Resource Server authorization policies.

### 7.3. Do Not Change the Principal Arbitrarily Between Runs

Bad for cache efficiency:

~~~java
.principal(UUID.randomUUID().toString())
~~~

Creating a new principal on every run prevents the manager from finding the previous authorized client under the same key, causing more token requests than necessary.

Use a stable key per workload/tenant. If you intentionally need to isolate state per processing run, make that an explicit design decision rather than randomizing on every call.

## 8. Re-issuing Access Tokens and Expiration Time

### 8.1. Does the Manager Request a Token on Every Run?

Not necessarily. If an authorized client already exists and its access token does not yet need re-issuance, the manager can **reuse the token**. This reduces Token Endpoint requests and lowers rate-limit risk.

Example:

~~~text
02:15 Job run 1
  → storage has no authorized client
  → requests new access token, expiresAt = 02:45

02:20 Job triggered again by an event
  → access token still usable
  → can be reused

02:44 Job runs
  → token near expiry; clock skew = 60 seconds
  → requests new access token via client_credentials
~~~

These timestamps illustrate the behavior; actual decisions depend on expiration time and provider configuration.

### 8.2. Is a Refresh Token Needed for `client_credentials`?

Usually no. With Client Credentials, the Client can use its own Client ID/credentials to request a new access token. Many Authorization Servers do not issue refresh tokens for this grant.

Therefore:

~~~java
OAuth2AuthorizedClientProviderBuilder.builder()
    .clientCredentials()
    .build();
~~~

usually meets the use case. Adding <code>.refreshToken()</code> merely because you see access tokens expiring is unnecessary for most client credentials workloads.

### 8.3. Clock Skew Is Not Token Extension

When setting:

~~~java
.clientCredentials(configurer ->
    configurer.clockSkew(Duration.ofSeconds(60)))
~~~

the manager treats a token expiring within 60 seconds as needing renewal. That does not alter the <code>expiresAt</code> issued by the Authorization Server and does not permit using a token after the Resource Server rejects it.

A clock skew that is too large relative to a short token lifetime can cause the job to request tokens continuously. Choose a sensible value and keep system clocks synchronized.

## 9. Where Does `AuthorizedClientService` Store Tokens?

<code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> uses <code>OAuth2AuthorizedClientService</code> to save/look up authorized clients.

Key methods:

~~~java
OAuth2AuthorizedClient loadAuthorizedClient(
    String clientRegistrationId,
    String principalName);

void saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal);

void removeAuthorizedClient(
    String clientRegistrationId,
    String principalName);
~~~

### 9.1. In-Memory

<code>InMemoryOAuth2AuthorizedClientService</code> keeps tokens in memory:

- Simple for demos and single-node apps.
- Tokens are lost on restart, though Client Credentials Manager can re-request them if credentials remain valid.
- Does not share tokens across instances.
- Does not prevent duplicate token requests when multiple nodes run the job simultaneously.

Losing local tokens after a restart **does not mean the Authorization Server revoked previously issued tokens**. Old tokens may remain valid at the Resource Server until they expire or are revoked.

### 9.2. JDBC / Persistent Storage

<code>JdbcOAuth2AuthorizedClientService</code> or custom storage is appropriate when you need:

- Token reuse across restarts.
- State sharing across multiple instances.
- Centralized storage management, monitoring, and lifecycle control.
- Concurrency design when multiple authorization calls occur simultaneously.

However, tokens stored in a database must be protected because access tokens are credentials. Apply least-privilege access, TLS to the database, encryption-at-rest or application-layer encryption where appropriate, auditing, and retention policies.

### 9.3. Must Every Job Use JDBC?

No. With the Client Credentials Grant, requesting a new token is straightforward and protocol-compliant. If the application runs a single instance and the Token Endpoint handles the load, an in-memory service may be appropriate.

As instance count grows or if the Authorization Server enforces tight rate limits, centralized persistent storage/caching can reduce token requests. Yet sharing authorized clients introduces concurrent update and storage access concerns; evaluate holistically rather than picking based solely on performance.

## 10. Scheduled Tasks Running on Multiple Instances

<code>@Scheduled</code> is an **in-process** scheduling mechanism. If three instances deploy with scheduling enabled, all three may execute the same job on the cron schedule:

~~~text
02:15  Instance A → runs job
02:15  Instance B → runs job
02:15  Instance C → runs job
~~~

<code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> **does not lock job execution** and does not turn the scheduler into a distributed job coordinator.

### 10.1. Separating Two Concerns: Execution Schedule and Tokens

| Concern | Mechanism to Consider |
|---|---|
| Only one instance executes the business task | Distributed scheduler, leader election, distributed lock, or worker queue |
| Avoid overlapping two runs of the same job | Locking, concurrency policy, deduplication |
| Tokens reusable across nodes | Shared authorized-client storage if needed |
| Two nodes requesting tokens simultaneously | Throttling/concurrency coordination or accepting independent tokens per policy |
| Job does not cause duplicate side effects | Idempotency keys, transaction boundaries, and domain logic |

Even when only one node executes a business job, other nodes may still need tokens for other workloads. Job locking and token storage **are not the same lock**.

### 10.2. Job Locks Do Not Replace Idempotency

A lock can expire while a job is still running, a node can crash after sending a request but before recording success, or a scheduler may retry. Therefore, for mutating APIs:

- Use an **idempotency key** when supported by the target API.
- Design data updates with versioning or unique constraints.
- Distinguish pre-send failures from ambiguous “unknown whether server processed it” outcomes.
- Never infinitely retry a POST solely due to timeouts.

This is job operational design, not a feature of `OAuth2AuthorizedClientManager`.

### 10.3. Token Reuse Across Nodes

If nodes share client credentials and the same principal key in a JDBC service, one node can persist an authorized client for another node to read.

Keep in mind:

- Two nodes noticing an access token is nearly expired may both request a new token.
- Nodes may overwrite the authorized client in the same row.
- If a provider enforces special token rotation/revocation policies, stale updates can cause errors.
- Storage may need optimistic locking, caching, or key-level coordination if consistency is required.

Client Credentials tokens usually carry no End-User, yet they must still satisfy workload scope, audience, and authorization rules.

## 11. Handling Authorization Errors in Jobs

Distinguish two error groups:

1. **Token acquisition errors:** Client Credentials authorization fails before the job calls the API.
2. **Resource Server errors:** the manager returned a token, yet the target API rejected the token or failed to process the request.

### 11.1. Token Endpoint Rejects the Client

Common OAuth2 Token Endpoint error codes:

| Error Code | Probable Cause | Resolution |
|---|---|---|
| <code>invalid_client</code> | Wrong Client ID/secret or client authentication | Check secret rotation, OP configuration, environment |
| <code>unauthorized_client</code> | Client not permitted to use client credentials | Check permitted grants |
| <code>unsupported_grant_type</code> | Endpoint/Authorization Server does not support the grant | Check token URI and grant type |
| <code>invalid_scope</code> | Scope does not exist or is disallowed | Check scopes at OP and Resource Server |
| <code>invalid_request</code> | Invalid form/token request | Check Client configuration and converter |

For deterministic configuration errors like <code>invalid_client</code> or <code>unauthorized_client</code>, rapid retries rarely help and can trigger rate-limiting or lockout of the service account.

Example catching and classifying errors at the job boundary:

~~~java
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;

try {
    OAuth2AuthorizedClient client = manager.authorize(authorizeRequest);
    if (client == null) {
        throw new IllegalStateException("No client credentials provider result");
    }
    // Proceed to call API with valid client.
} catch (OAuth2AuthorizationException ex) {
    // Log only a controlled error code, never raw token responses or secrets.
    String code = ex.getError().getErrorCode();
    throw new IllegalStateException(
        "Service OAuth2 authorization failed, errorCode=" + code, ex);
}
~~~

This snippet shows how to catch the error. In production, <code>errorCode</code> is also provider-supplied data: apply an allowlist or character/length limits before emitting to telemetry. Never expose raw <code>error_description</code> from the Token Endpoint to UI or logs, and never print stack traces containing HTTP requests if the HTTP client may retain credentials.

### 11.2. Resource Server HTTP 401

Suppose the manager just returned a token, but the API replies:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Possible causes:

- Access token expired before or just as it was used.
- Token was revoked.
- Token has the wrong issuer or audience for the Resource Server.
- Resource Server does not trust the signing key, or the introspection endpoint failed.
- Client's cache/storage holds an unusable token.

**Do not assume every 401 goes away simply by calling <code>authorize()</code> again.** If the token is not near expiration according to the manager, the next call may reuse the exact same stale token. Establish a policy to evict stale authorized clients, verify audience/scope, and perform only bounded retries when genuinely recoverable.

Some Spring Security interceptors/HTTP integrations include mechanisms to handle authorized client failures when a Resource Server rejects a token. If you attach the Bearer header manually as in Section 6, **the application itself must handle HTTP errors and implement proper cleanup/retry policies**; the manager cannot observe HTTP 401s from a `RestClient` call unless you wire that feedback into the appropriate handler.

### 11.3. Resource Server HTTP 403

HTTP 403 usually indicates the token was recognized, yet **lacks sufficient permissions** for the operation. If the target API reports <code>insufficient_scope</code>, adjust the `ClientRegistration` scopes/permissions and authorization policy rather than deleting the token and requesting an identical new one.

### 11.4. Timeouts, 429, and HTTP 5xx

| Error | Recommendation |
|---|---|
| Timeout requesting token | Classify as transport failure; use bounded retry with appropriate backoff/jitter |
| HTTP 429 from Token Endpoint | Respect rate limits and <code>Retry-After</code> when trusted; reduce token requests |
| HTTP 502/503 from Token Endpoint | Monitor outage; use bounded retry if policy permits |
| Timeout calling business API | Assess whether side effects may have occurred before retrying |
| HTTP 503 from API | Circuit breaker/backoff; do not blame every failure on the OAuth2 token |

For Client Credentials, re-requesting a token carries less “one-time code” risk than Authorization Code Flow; still, bound retries and do not assume every token endpoint is strictly idempotent across all extensions.

### 11.5. How Does `@Scheduled` Report Errors?

A <code>@Scheduled</code> method returning <code>void</code> has no interactive user to display errors to. Depending on the scheduler/error handler, exceptions may be logged while subsequent runs continue.

The application should have:

- Metrics for run successes/failures and duration.
- Alerts on consecutive failures or excessive runtime.
- Internal correlation IDs to trace API requests.
- A clearly defined retry/recovery policy rather than relying on an uncaught exception not halting the scheduler permanently.
- Zero access tokens, secrets, or PII-containing raw responses in logs/metrics.

Do not treat “no exception in the console” as proof the work succeeded. Jobs must explicitly verify required business outcomes.

## 12. Success Handlers, Failure Handlers, and Token State

<code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> uses handlers to decide how to save or process the authorized client after authorization.

Typically:

~~~text
manager.authorize(...)
    → Provider executes Client Credentials Grant
    → Valid token response
    → New OAuth2AuthorizedClient
    → AuthorizationSuccessHandler saves via OAuth2AuthorizedClientService
~~~

By default, the manager is configured to persist the authorized client when token issuance succeeds. You do not need to call <code>service.saveAuthorizedClient(...)</code> manually after **every** <code>manager.authorize(...)</code> in typical usage.

If the application **overrides the success handler**, ensure new tokens are still saved as designed. A handler that only logs without saving will force every job run to request a new token.

When a provider returns an error, the manager invokes its failure handler depending on configuration/version. Do not assume **every error** deletes the existing authorized client; nor should you wipe all authorized clients during a temporary Authorization Server outage.

Codes like <code>invalid_grant</code> can indicate an invalid refresh token in flows using refresh grants. Because Client Credentials typically has no refresh token, evaluate errors specific to the active grant rather than applying a blanket cleanup policy across all token types.

## 13. Tuning Frequency and Reducing Unnecessary Token Requests

Each time <code>@Scheduled</code> runs, code typically calls <code>manager.authorize(...)</code>. That **does not mean `POST /token` is sent every time**.

The manager/service can reuse a still-valid authorized client.

However, if:

- The principal key changes on every run.
- The registration ID is wrong or changes.
- In-memory storage is used and instances restart frequently.
- Clock skew is configured too large.
- Tokens are very short-lived.
- A custom success handler fails to persist the result.
- Distributed storage is inconsistent.

then the Token Endpoint may be called far more often than expected.

### 13.1. Anti-Pattern: Random Principal

~~~java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("reports-job")
        .principal(java.util.UUID.randomUUID().toString())
        .build();
~~~

Generating a new principal on every run prevents lookup from finding the previously stored authorized client. Avoid doing this just to have a “unique ID.”

### 13.2. Anti-Pattern: Calling the Token Endpoint Directly on Every Job Run

~~~text
Every job run:
    POST /token with client secret
    call API using newly issued access token
    discard token after request
~~~

While this works at the protocol level, it makes token reuse, error handling, retries, and rate limits harder to manage. Using the manager/service is clearer and more consistent.

### 13.3. Do Not Cache Token Strings in a Static Field

A token is a credential with an expiration and can be revoked. A static `String` in a singleton cannot properly track registration/principal/expiry and risks cross-tenant or cross-workload misuse.

<code>OAuth2AuthorizedClient</code> and the service/manager provide a far better lifecycle model.

## 14. One Job Needing Multiple APIs or Registrations

Suppose a job must call:

~~~text
Reports API: registrationId=reports-job, scope=reports.read
Billing API: registrationId=billing-job, scope=billing.write
~~~

Define two separate `ClientRegistration`s when client credentials, audiences, or authorization policies differ.

Example:

~~~java
OAuth2AuthorizeRequest reportsRequest =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("reports-job")
        .principal("nightly-worker")
        .build();

OAuth2AuthorizeRequest billingRequest =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("billing-job")
        .principal("nightly-worker")
        .build();
~~~

The two authorized clients remain distinct because their registration IDs differ, even with a shared synthetic principal. Still, pick distinct principals per workload when you have clear isolation, operational, or rotation requirements.

Never take the access token from <code>reports-job</code> and send it to the Billing API simply because both accept Bearer tokens. The Resource Server must accept the exact issuer, audience, scope, and authorization policy.

### 14.1. One Manager or Multiple Managers?

If jobs share client credentials, storage, and token-handling policies, **one service manager** can serve multiple registrations.

When one group of jobs needs client credentials while another needs user-delegated authorization/refresh tokens, consider separate managers:

- A manager for web OAuth2 Login, bound to HTTP requests.
- A manager for service jobs, independent of HTTP requests.

Separating managers keeps provider configurations minimal and prevents mixing user tokens with service tokens.

### 14.2. Multi-Tenant Jobs

For tenants A and B, changing `principalName` alone is not always sufficient:

~~~text
Tenant A: client ID A, audience A, scope A
Tenant B: client ID B, audience B, scope B
~~~

If permissions/Client credentials are separated per tenant, use separate registrations or a properly managed dynamic registration mechanism. Principal keys must be namespaced to prevent tokens from overwriting each other across tenants.

Never allow an HTTP request to self-declare a tenant and use it directly to select a privileged service token. Verify tenant context using backend authentication/authorization mechanisms.

## 15. Protecting Credentials in Schedulers

A job without a user must still comply fully with OAuth2 credential protection requirements.

### 15.1. Keep Secrets on the Backend

Do not hardcode:

~~~yaml
client-secret: my-real-secret-value
~~~

Use environment variables or a secret store:

~~~yaml
client-secret: ${REPORTS_WORKER_CLIENT_SECRET}
~~~

When rotating secrets, plan a safe rollout. If the Authorization Server rotates a secret while the job still uses old configuration, the token endpoint may return <code>invalid_client</code>.

### 15.2. Do Not Write Tokens to Logs

Never log:

- <code>authorizedClient.getAccessToken().getTokenValue()</code>.
- Refresh tokens, if any.
- Client secrets or Authorization headers.
- Raw token responses.
- URLs containing credentials in query strings.

Safer telemetry:

~~~text
job=reports-daily
registrationId=reports-job
authorizedClientFound=true
tokenRefreshOrIssueResult=success
apiStatus=200
durationMs=1420
~~~

Even job names, tenant IDs, principal keys, and response metadata should be bounded according to internal data-protection policies.

### 15.3. Do Not Use ID Tokens for Jobs

The Client Credentials Grant is not OIDC End-User authentication. Jobs should not try to obtain an <code>OidcUser</code>, ID Token, or Session to prove service privileges. Credentials must be issued by the Authorization Server specifically for Client Credentials and the target API.

### 15.4. Token Audience and Scope

A valid access token from the Token Endpoint is not guaranteed to be accepted by the Reports API:

- Audience may point to another API.
- Scope may lack <code>reports.read</code>.
- The Resource Server may enforce its own IP, tenant, or entitlement policies.
- The token may be expired or revoked.

Jobs must handle `401`/`403` responses from the API, not merely check whether the manager returned a token.

## 16. Operating Schedulers Reliably

### 16.1. Time Zones and Schedules

Example:

~~~java
@Scheduled(cron = "${app.reports-job.cron}", zone = "UTC")
public void run() { ... }
~~~

Specifying a timezone prevents schedule drift caused by host machine timezones. If a requirement says “02:15 local time,” use the appropriate zone ID and account for DST in regions with daylight saving transitions.

With six-field cron, validate expressions against Spring documentation rather than copying five-field Unix crontabs unmodified.

### 16.2. Scheduling Thread Pool

When running multiple jobs, configure thread pool size, task timeouts, and priorities as needed. More threads are not always better: many concurrent jobs can spike token requests and API traffic.

Do not block all infrastructure jobs because of one slow API. Designing HTTP client timeouts is an essential requirement.

### 16.3. Do Not Place Network Calls Inside Long Transactions

Jobs should separate Token Endpoint/Resource Server calls from long-running database transactions unless strictly necessary. Holding transactions open while waiting on HTTP increases contention and causes deadlocks.

For complex workflows, use outbox patterns, idempotent processing, or explicit job states instead of spanning one transaction across multiple systems.

### 16.4. Shutdown and Restart

If a process restarts mid-job, the scheduled method may be incomplete. Upon startup:

- In-memory authorized clients may be lost; the manager requests a new token when needed.
- Persistent authorized clients may be reused if still valid.
- Business results from the prior run may be partially written.

Therefore, implement **checkpoints/idempotency** for business logic. Token persistence does not prove a job finished.

## 17. Comparing Design Choices

| Need | Suitable Choice | What to Avoid |
|---|---|---|
| Background job without End-User | <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> + <code>clientCredentials()</code> | Using user session/authorization code flow |
| Servlet OIDC web login | <code>oauth2Login()</code> with web security chain | Treating a service token as an ID Token |
| API call on behalf of logged-in user | User's authorized client, valid scope/audience | Using a client credentials token to impersonate a user |
| Persist tokens across restarts | Persistent <code>OAuth2AuthorizedClientService</code> | Assuming in-memory survives restarts |
| Run a job once across a cluster | Distributed scheduler/lock | Thinking <code>@Scheduled</code> coordinates across the cluster |
| Avoid excessive token requests | Stable principal, manager reuse, expiry policy | Random principal or manually requesting tokens every time |
| Separate permissions across tenants | Proper `ClientRegistration` and principal namespacing | Only renaming the principal and assuming permissions are isolated |
| API returns 401 | Classify token/audience/expiry, controlled cleanup | Infinite retries with the same token |

## 18. Common Errors and Diagnostics

| Symptom | Possible Cause | Resolution |
|---|---|---|
| <code>manager.authorize()</code> returns null | Mismatched registration/grant provider/context | Check <code>registrationId</code>, grant type, provider list |
| <code>NoSuchBeanDefinitionException</code> for <code>OAuth2AuthorizedClientService</code> | Missing OAuth2 Client auto-config/bean | Check dependencies, registration, bean wiring |
| Job complains of missing `HttpServletRequest` | Wrongly injected web manager | Use <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> |
| <code>invalid_client</code> | Wrong Client ID/secret or auth method | Check secret rotation, environment, token endpoint |
| <code>unauthorized_client</code> | Service not permitted to use client credentials | Check registration at the Authorization Server |
| <code>invalid_scope</code> | Scope requested by job is not granted | Adjust scope/permissions |
| Job requests a token on every run | Principal keeps changing, store doesn't persist, skew too large, or token too short | Stabilize principal, inspect service/success handler |
| Token lost after restart | In-memory authorized client storage | Use persistence if genuinely required |
| Two nodes run the same job | <code>@Scheduled</code> runs on each instance | Distributed scheduling/locking and idempotency |
| Resource Server returns 401 | Expired/revoked token or wrong audience | Check audience, token validity, error-handling policy |
| Resource Server returns 403 | Insufficient scope/authorization | Check API permissions, not just swapping tokens |
| Token Endpoint rate limits | Too many token requests, instances generating tokens simultaneously | Reduce issuance, cache/store, backoff |
| Wrong manager bean | Multiple managers without <code>@Qualifier</code> | Name and inject explicitly |
| API times out yet job marked success | Business handler swallows exceptions or skips verification | Separate business completion from merely holding a token |
| Permission error after secret rotation | Deployment still using stale secret | Verify rotation timing and rollout |

### 18.1. Isolation Workflow

~~~text
Is the job actually triggered by @Scheduled?
    |
    v
Is the Servlet-independent OAuth2AuthorizedClientManager used?
    |
    v
Does ClientRegistration ID exist with grant = client_credentials?
    |
    v
Does OAuth2AuthorizedClientProvider have clientCredentials()?
    |
    v
Is the synthetic principal stable?
    |
    v
Does OAuth2AuthorizedClientService have a still-usable token?
    |
    +-- Yes --> Use access token matching scope/audience
    |
    +-- No --> Call Token Endpoint
                    |
                    v
              Are client auth + scopes accepted?
                    |
                    v
              Is the authorized client saved?
                    |
                    v
              Does the Resource Server accept the token?
                    |
                    v
              Is job business logic complete / idempotent?
~~~

## 19. Scenarios and Hands-On Exercises

### Exercise 1 — Choosing the Right Manager

A team implements a nightly report-reading job. They use:

~~~java
DefaultOAuth2AuthorizedClientManager manager = ...;
~~~

even though the job has no HTTP request.

**Question:** Why is this pattern unsuitable? Which abstraction should they choose?

**Suggested Answer:** The web manager relies on request context and <code>OAuth2AuthorizedClientRepository</code>. A scheduled service should use <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> with <code>OAuth2AuthorizedClientService</code>.

### Exercise 2 — Principal Is Not a User

Code:

~~~java
OAuth2AuthorizeRequest.withClientRegistrationId("reports-job")
    .principal("reports-worker-runtime")
    .build();
~~~

**Question:** Must the token carry subject <code>reports-worker-runtime</code>?

**Answer:** No. This is a principal key for managing the authorized client in Spring Security. Subject/audience/scope of the access token are determined by the Authorization Server based on the service `ClientRegistration`.

### Exercise 3 — No Refresh Token

The client credentials token response contains only access token, token type, and expiry. Code sees <code>getRefreshToken()==null</code>.

**Question:** Is this an error?

**Answer:** Usually no. The Client Credentials Grant does not require a refresh token to obtain a new token; the <code>clientCredentials()</code> provider can request a new access token when needed.

### Exercise 4 — Running Concurrently Across Three Instances

An application deploys three replicas with <code>@Scheduled(cron="0 15 2 * * *")</code> enabled.

**Question:** What can happen?

**Answer:** All three replicas may execute the job simultaneously; the token manager does not solve this. You need a distributed scheduler/lock, an idempotent workflow, and concurrency policies independent of token storage.

### Exercise 5 — Token Sent to Wrong API

A client is issued a <code>reports.read</code> token meant for Reports API, yet the job sends it to Billing API.

**Question:** Why doesn't the manager guarantee the call succeeds?

**Answer:** The manager only obtains a token within its grant/registration. The Resource Server still validates issuer, audience, scope, and authorization. Use the proper `ClientRegistration`/token intended for the Billing API.

### Exercise 6 — Requesting a Token Every Run

Every time the job runs, it constructs:

~~~java
.principal(java.util.UUID.randomUUID().toString())
~~~

**Question:** What can happen?

**Answer:** Each new principal prevents storage from finding the previously saved authorized client; token requests spike and may hit rate limits. Use a stable principal per workload/tenant.

### Exercise 7 — Handling 401 from the API

The job obtains an authorized client successfully, yet the API returns HTTP 401.

**Question:** Should it call <code>manager.authorize()</code> in a loop until the API accepts the token?

**Answer:** No. The token may have the wrong audience, or the manager may return the same cached token if it is not near expiry. Classify the error, check registration/scope, use controlled failure handling/cleanup, and apply bounded retries only when recoverable.

### Exercise 8 — Designing a Complete Job

Outline:

1. A `ClientRegistration` <code>inventory-sync</code> with <code>authorization-grant-type=client_credentials</code> and a read-only scope.
2. A Servlet-independent manager containing the <code>clientCredentials()</code> provider.
3. An <code>OAuth2AuthorizeRequest</code> using a stable synthetic principal.
4. An HTTP client calling the Inventory API with a Bearer access token.
5. Timeouts and job success/failure tracking.
6. A policy preventing duplicate execution across replicas and ensuring idempotent processing.
7. Logs free of tokens, secrets, or raw API payloads.

## 20. Key Takeaways

- **<code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code>** fits jobs, schedulers, and services without an <code>HttpServletRequest</code>.
- Combine **<code>ClientRegistrationRepository</code>**, **<code>OAuth2AuthorizedClientService</code>**, and **<code>OAuth2AuthorizedClientProviderBuilder.builder().clientCredentials()</code>** to handle the Client Credentials Grant.
- The job calls <code>manager.authorize(OAuth2AuthorizeRequest)</code> with the **right registration ID** and a **stable synthetic principal**. This principal is a token storage key, not an End-User identity inside the token.
- The manager can **reuse valid access tokens** and **request new tokens when needed**; client credentials normally do not need refresh tokens.
- <code>@Scheduled</code> does not coordinate across a cluster. Separate **single-run job execution**, **token storage**, **HTTP retries**, and **business idempotency**.
- Access tokens must only be sent to Resource Servers with matching audience/scopes; 401/403 errors are not automatically fixed by repeatedly requesting tokens.
- Protect client secrets/tokens, use TLS, bound retries, mind clock skew, and never put tokens or credentials into logs.
- When an application has both web login and background jobs, prefer **context-appropriate managers** and separate configurations for user tokens vs. service tokens to prevent privilege mixing.

### References

- **Spring Security Reference — OAuth2 Client:** Authorized Client Manager, Authorized Client Provider, Client Credentials Grant, and Authorized Client Service.
- **Spring Security Java API — AuthorizedClientServiceOAuth2AuthorizedClientManager:** constructors, providers, success/failure handlers, and storage mechanism.
- **Spring Security Java API — OAuth2AuthorizedClientProviderBuilder:** <code>clientCredentials()</code>, clock skew, and grant configuration capabilities.
- **Spring Security Java API — OAuth2AuthorizeRequest, OAuth2AuthorizedClient, and OAuth2AuthorizedClientService:** relationship between registration/principal/token and storage lifecycle.
- **Spring Framework Reference — Task Execution and Scheduling:** <code>@EnableScheduling</code>, <code>@Scheduled</code>, cron expressions, and scheduling thread pools.
- **RFC 6749 — The OAuth 2.0 Authorization Framework, Section 4.4:** Client Credentials Grant and Token Endpoint.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** how Bearer access tokens are used at a Resource Server.
- **RFC 7009 — OAuth 2.0 Token Revocation:** token revocation behavior when supported by the Authorization Server.
