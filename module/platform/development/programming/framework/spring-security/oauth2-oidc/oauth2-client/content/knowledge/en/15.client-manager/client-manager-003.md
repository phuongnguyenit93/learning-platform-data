# 15.3. `AuthorizedClientServiceOAuth2AuthorizedClientManager` Outside HTTP Requests

In **Spring Security OAuth 2.0/OIDC Client**, many login and API-calling examples begin from an HTTP request sent by a browser to Spring MVC. However, real-world systems also have tasks **that do not run inside an `HttpServletRequest` lifecycle**: scheduled jobs, message consumers, command-line runners, queue processors, domain event handlers, or service-to-service background tasks.

Those tasks may still need an OAuth 2.0 access token to call an API. Using the wrong manager can cause the application to depend on a nonexistent HTTP request/session or accidentally pick up a logged-in user's token. Spring Security solves this need with **`AuthorizedClientServiceOAuth2AuthorizedClientManager`** — an `OAuth2AuthorizedClientManager` implementation designed for the **service tier and tasks running outside an HTTP request**.

This lesson explains the authorized client model, how to choose a manager, configuring the `client_credentials` grant for background tasks, token reuse/refresh mechanisms, `OAuth2AuthorizedClientService` storage, `principal` identification, error handling, and the limitations when operating under user permissions.

## 1. Real-World Scenario: A Job Calling an API Without a Browser

Suppose a Spring Boot application runs a job every 15 minutes:

```text
@Scheduled
    -> fetch report list from Reporting API
    -> process/aggregate
    -> persist results internally
```

The Reporting API requires:

```http
GET /v1/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
```

The token must be obtained from the Authorization Server via the **Token Endpoint**. However, inside a `@Scheduled` method:

- There is no user sending a request to a controller.
- There is no `HttpServletRequest` or `HttpServletResponse` bound to the current thread.
- There is no browser login session needed to run a system job.
- `SecurityContextHolder` may be empty or contain no user authentication.
- It is impossible to redirect a browser to the Authorization Endpoint for a user to log in.

Therefore, for a task calling an API with the permissions of **the application itself**, the appropriate grant is typically **`client_credentials`**, and the appropriate manager is **`AuthorizedClientServiceOAuth2AuthorizedClientManager`**.

Desired structure:

```mermaid
flowchart TD
    A["@Scheduled / Message Consumer / Service"] --> B["OAuth2AuthorizeRequest"]
    B --> C["AuthorizedClientServiceOAuth2AuthorizedClientManager"]
    C --> D["OAuth2AuthorizedClientService"]
    D --> E{"Valid authorized client already exists?"}
    E -->|Yes| F["Return existing access token"]
    E -->|No or needs reauthorization| G["OAuth2AuthorizedClientProvider"]
    G --> H["Authorization Server / Token Endpoint"]
    H --> I["New access token"]
    I --> D
    F --> J["Call downstream API with Bearer token"]
    I --> J
```

The diagram depicts the general mechanism. The manager/provider decides whether to reissue a token or return the stored client depending on the grant, current token, and reauthorization capability.

## 2. Key Components of Spring OAuth2 Client

Before writing code, it is important to clearly understand the interfaces and classes involved.

| Component | Role | Note |
|---|---|---|
| `ClientRegistration` | Configuration of a registered Client: client ID, secret, grant, scopes, and Token Endpoint | Not a token |
| `ClientRegistrationRepository` | Looks up `ClientRegistration` by `registrationId` | Spring Boot typically creates this from YAML/properties |
| `OAuth2AuthorizedClient` | A Client that has been granted authorization, associated with a principal name and access/refresh tokens | Represents the **authorization result** |
| `OAuth2AuthorizedClientService` | Saves, finds, and removes `OAuth2AuthorizedClient` | Does not need an HTTP request |
| `OAuth2AuthorizedClientManager` | Coordinates authorization/reauthorization to obtain an appropriate authorized client | Common interface |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | Manager using a **service** to store authorized clients, operating outside Servlet requests | Suitable for background/service tiers |
| `DefaultOAuth2AuthorizedClientManager` | Manager using a repository tied to Servlet requests | Used inside HTTP requests |
| `OAuth2AuthorizedClientProvider` | Executes one or more grants such as client credentials or refresh token | Selected via builder |
| `OAuth2AuthorizeRequest` | Request asking the manager to authorize a registration with a specific principal | Can supply principal name as a String |

A crucial point is that **`ClientRegistration` and `OAuth2AuthorizedClient` are different**:

```text
ClientRegistration("reporting-job")
    clientId
    clientSecret
    grantType = client_credentials
    tokenUri
    scopes = reports.read

OAuth2AuthorizedClient
    clientRegistration = "reporting-job"
    principalName = "service:reporting-job"
    accessToken = (token value, type, issuedAt, expiresAt, scopes)
    refreshToken = null (common with client_credentials)
```

A registration can exist before any token is issued. `OAuth2AuthorizedClient` only appears after a successful authorization or after being retrieved from storage.

## 3. Choosing the Right Manager: Inside vs. Outside Servlet HTTP Requests

Spring Security provides two implementations that are often discussed together:

| Criterion | `DefaultOAuth2AuthorizedClientManager` | `AuthorizedClientServiceOAuth2AuthorizedClientManager` |
|---|---|---|
| Primary context | Servlet request with `HttpServletRequest`/`HttpServletResponse` | Scheduler, worker, queue consumer, service tier |
| Storage mechanism | `OAuth2AuthorizedClientRepository` | `OAuth2AuthorizedClientService` |
| Web request/session dependency | May be required | Not needed |
| Example | Controller calling a downstream API as the logged-in user | Job calling an API using client credentials |
| Principal | Usually the current `Authentication` | Can provide an explicit principal name |
| Initialization | `(ClientRegistrationRepository, OAuth2AuthorizedClientRepository)` | `(ClientRegistrationRepository, OAuth2AuthorizedClientService)` |
| Grant execution | Via `OAuth2AuthorizedClientProvider` | Via `OAuth2AuthorizedClientProvider` |

**Do not choose a manager solely based on whether the application uses Spring MVC.** An MVC application can still have scheduled tasks; those background tasks should use the service-based manager.

### 3.1. Why Can Using `DefaultOAuth2AuthorizedClientManager` in `@Scheduled` Fail?

The Servlet request manager has mechanisms to retrieve the HTTP request/response from the request context. In a background thread, thread-bound request attributes normally do not exist.

Some symptoms:

```text
No thread-bound request found
No current ServletRequestAttributes
Cannot find HttpServletRequest / HttpServletResponse
```

Exact messages depend on the version and code path. Trying to mock an `HttpServletRequest` just to make the manager run is usually the wrong direction: a job does not need a browser session, and storing tokens under a fake session can lose tokens across runs.

### 3.2. Why Does `AuthorizedClientServiceOAuth2AuthorizedClientManager` Work?

The service manager:

1. Receives `registrationId` and `principal` from `OAuth2AuthorizeRequest`.
2. Looks up `ClientRegistration` in the configured repository.
3. Looks up any existing authorized client via `OAuth2AuthorizedClientService` when appropriate.
4. Calls `OAuth2AuthorizedClientProvider` to authorize/reauthorize if needed.
5. Saves the authorized client after successful authorization using the default success handler.
6. Returns `OAuth2AuthorizedClient` to the caller, or `null` when authorization is unsupported per the contract.

No fake `HttpServletRequest` is needed. When the background task calls `authorize(...)`, the manager can retrieve and reuse tokens according to the configured grant.

## 4. Distinguishing Two Flows: `client_credentials` vs. User Permissions

A critical design choice: **on whose behalf** is the background task acting?

### 4.1. Service-to-Service Using `client_credentials`

Example report sync job:

```text
Spring job (Client A)
  -> client_id + client_secret / private key
  -> Token Endpoint
  -> access token representing Client A
  -> Reporting API
```

There is no interactive user, no OIDC ID Token representing a logged-in user, and usually no refresh token. When the access token expires, the Client uses its own credentials to **request a new token**.

This is usually the best choice for service accounts or tasks running with application-level permissions.

### 4.2. Background Task Needing User Permissions

Another scenario: a user has logged in via OIDC using authorization code, consented to offline access, and the application wants to continue syncing a resource **under that user's granted permissions**.

In this case:

- The initial token is issued via the interactive **`authorization_code`** flow.
- The authorized client is associated with **that specific user's principal**.
- If the Authorization Server issues a `refresh_token`, the backend can use `refresh_token` to obtain a new access token when permitted.
- The background task must retrieve **the exact saved authorized client** and honor consent, scopes, audience, expiry, and revocation.
- If there is no refresh token or the provider rejects it, the job must handle it via a re-interactive flow; never fall back to someone else's permissions.

**Never change `principal("username")` in `OAuth2AuthorizeRequest` to impersonate a user who has never granted a token.** The principal string is a lookup/storage key for authorized clients, not an “authentication credential” that makes the Authorization Server grant that user's permissions.

### 4.3. Summary of How to Choose

| Need | Grant / Token Source | Principal for Manager |
|---|---|---|
| System job reading shared data API | `client_credentials` | Stable system name such as `service:reporting-job` |
| Worker sending events with application permissions | `client_credentials` | Explicit service or tenant name |
| Job continuing to process user-authorized data | Authorized client from `authorization_code` + `refresh_token` if present | **Exact principal of the user** already saved |
| Browser OIDC Login | `authorization_code` and `oauth2Login` | Logged-in principal in the request |
| Unauthenticated frontend wanting to go through consent page | Authorization code flow via browser | Do not initiate interaction from a background thread |

## 5. Spring Boot Configuration for Client Credentials

Suppose an Authorization Server issues Client `reporting-job` to access `https://api.example.test/v1/reports` with scope `reports.read`.

In `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reporting-job:
            provider: reporting-api
            client-id: ${REPORT_CLIENT_ID}
            client-secret: ${REPORT_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read

        provider:
          reporting-api:
            token-uri: https://id.example.test/oauth2/token
```

Explanation:

- `registration.reporting-job` is the internal **`registrationId`** key.
- `provider: reporting-api` points to the Token Endpoint configuration.
- `authorization-grant-type: client_credentials` makes clear no browser redirect is needed.
- `client-authentication-method: client_secret_basic` illustrates how the Client authenticates to the Token Endpoint; the provider may require another method.
- `scope: reports.read` is the scope the application wishes to request; it must be permitted by the Authorization Server.
- No `redirect-uri` is needed for the client credentials grant itself.
- No `authorization-uri` is needed when only using client credentials; token requests go directly to the Token Endpoint.
- Do not request `openid` by default because this is **not an OIDC user login**.

The `example.test` domain and environment variables are placeholders. In a real system, register the Client at the Authorization Server, use the exact Token Endpoint, and protect credentials with environment variables, a secret manager, or an appropriate key management solution.

### 5.1. How Does the Token Request Happen?

When no suitable access token exists yet, the manager invokes the client credentials provider, producing a request like:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.test
Authorization: Basic EXAMPLE_CLIENT_AUTH_HEADER
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&scope=reports.read
```

The Token Endpoint may return:

```json
{
  "access_token": "EXAMPLE_SERVICE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "reports.read"
}
```

There is no authorization code, browser callback, or ID Token. `refresh_token` is also typically absent in a client credentials response; the Authorization Server normally lets the Client use its own credentials to request a new access token when needed.

### 5.2. Required Dependencies

The Spring Boot application needs the OAuth2 Client starter compatible with the Boot version in use. For example, on a Spring Boot 3.x branch:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
```

Starter/artifact names may differ in newer Spring Boot branches, so use your project's dependencies/BOM and consult the official documentation for your exact version. The Java examples below focus on Spring Security OAuth2 Client APIs.

You do not need to enable `oauth2Login` to obtain tokens via `client_credentials` for a system job. If the application also has OIDC Login for users, that is a separate flow configuration.

## 6. Creating `AuthorizedClientServiceOAuth2AuthorizedClientManager`

A typical configuration bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class OAuth2ServiceClientConfig {

    @Bean
    OAuth2AuthorizedClientManager serviceAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        var manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations,
                authorizedClients
            );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Step-by-step breakdown:

1. `ClientRegistrationRepository` retrieves the `reporting-job` registration declared in YAML.
2. `OAuth2AuthorizedClientService` provides an authorized client store independent of HTTP sessions.
3. `OAuth2AuthorizedClientProviderBuilder.builder().clientCredentials().build()` allows the manager to use the Client Credentials Grant.
4. `AuthorizedClientServiceOAuth2AuthorizedClientManager` ties together registrations, storage, and providers.
5. `OAuth2AuthorizedClientManager` is the interface so business code depends on the abstraction rather than instantiating a manager inside every job.

Spring Boot can auto-configure a default repository/service suited to the Client configuration. If the application has multiple `OAuth2AuthorizedClientManager` beans, use `@Qualifier` or explicit bean names to inject the right service manager for background tasks.

### 6.1. Why Must `setAuthorizedClientProvider` Be Set?

The manager coordinates one or more `OAuth2AuthorizedClientProvider` instances. The provider determines which grants are handled when `authorize(...)` is called.

If you only want the job to use client credentials, configuring:

```java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();
```

is sufficient and explicit. Do not add `authorizationCode()` just because the application has OIDC Login elsewhere.

If the manager has no provider matching the grant in `ClientRegistration`, `authorize(...)` may return `null`. This must be handled instead of assuming an access token is always returned.

### 6.2. Do You Need to Create an `OAuth2AuthorizedClientService` Bean?

If Spring Boot already provides an appropriate bean, you do not need to create one yourself. When you want to explicitly define an in-memory store for development examples, you can use:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Bean
OAuth2AuthorizedClientService authorizedClientService(
        ClientRegistrationRepository registrations) {

    return new InMemoryOAuth2AuthorizedClientService(registrations);
}
```

**Choose only one** bean creation mechanism to avoid duplicates. `InMemoryOAuth2AuthorizedClientService` is easy to use in demos/tests, but tokens are lost on application restart and are not shared across multiple instances. Persistent storage is covered in a later section.

## 7. Calling `authorize(...)` in a `@Scheduled` Job

Key point: **you must provide a stable principal name** even when no user is logged in.

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

public final class ServiceTokenProvider {

    private final OAuth2AuthorizedClientManager manager;

    public ServiceTokenProvider(OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    public String requireAccessToken() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("reporting-job")
                .principal("service:reporting-job")
                .build();

        OAuth2AuthorizedClient authorizedClient =
            manager.authorize(request);

        if (authorizedClient == null) {
            throw new IllegalStateException(
                "OAuth2 authorization is not supported for reporting-job"
            );
        }

        return authorizedClient.getAccessToken().getTokenValue();
    }
}
```

Meaning:

- `withClientRegistrationId("reporting-job")` locates the right `ClientRegistration`.
- `principal("service:reporting-job")` assigns the **logical key** for the manager/service to save and look up the authorized client.
- `authorize(...)` can return an existing client or reissue one when the provider determines it is needed.
- Only after checking the result is non-`null` should you call `getAccessToken()`.
- The access token value is used strictly internally to construct the HTTP `Authorization` header; never log or expose it to the frontend.

**`principal("service:reporting-job")` does not create a real user account.** It scopes the job's token storage space. With `client_credentials`, the token represents the Client per Authorization Server policy, not a user named by that String.

### 7.1. A Complete Job Calling an API with `RestClient`

The example below uses `RestClient`, available in modern Spring Framework (Spring Framework 6.1+). For older projects, use an HTTP client supported by your version while keeping the same manager-based token retrieval.

```java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class ReportingSyncJob {

    private static final String REGISTRATION_ID = "reporting-job";
    private static final String SERVICE_PRINCIPAL = "service:reporting-job";

    private final OAuth2AuthorizedClientManager manager;
    private final RestClient reportingApi;

    public ReportingSyncJob(
            OAuth2AuthorizedClientManager manager,
            RestClient.Builder restClientBuilder) {

        this.manager = manager;
        this.reportingApi = restClientBuilder
            .baseUrl("https://api.example.test")
            .build();
    }

    @Scheduled(cron = "0 */15 * * * *")
    public void synchronize() {
        OAuth2AuthorizeRequest authorizeRequest =
            OAuth2AuthorizeRequest
                .withClientRegistrationId(REGISTRATION_ID)
                .principal(SERVICE_PRINCIPAL)
                .build();

        OAuth2AuthorizedClient authorized =
            manager.authorize(authorizeRequest);

        if (authorized == null) {
            throw new IllegalStateException(
                "No authorized client for " + REGISTRATION_ID
            );
        }

        String accessToken = authorized.getAccessToken().getTokenValue();

        String reportsJson = reportingApi.get()
            .uri("/v1/reports")
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .body(String.class);

        // Replace with your application's persistence/business logic.
        processReports(reportsJson);
    }

    private void processReports(String reportsJson) {
        // Illustrative: parse and persist reports in a dedicated service.
    }
}
```

Enable scheduling in a configuration class:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class SchedulerConfig {
}
```

Ensure the project has Spring Web/RestClient and OAuth2 Client dependencies; the example injects `OAuth2AuthorizedClientManager` and `RestClient.Builder` provided by Spring Boot. If multiple managers of the same type exist, inject with a qualifier.

**Never log the `accessToken` variable or `reportsJson` when it contains sensitive data.** `processReports(...)` is only a placeholder for business logic, not a production implementation.

### 7.2. Obtain the Token Only When Needed to Call an API

A common mistake is fetching a token once in the constructor and holding onto it forever:

```java
// DO NOT DO THIS:
class Job {
    private final String token = fetchAtStartup();
}
```

Access tokens have a lifetime. If the job runs for many hours, the token fetched at startup will expire. Instead, **call the manager each time an operation needing a token executes** so it has the opportunity to look up or reissue the token appropriately.

### 7.3. Why Not Manually Check Expiry Everywhere?

`OAuth2AuthorizedClientProvider` is already responsible for deciding when reauthorization is needed given the grant and current authorized client, including token lifetime and appropriate clock skew policy. If controllers/jobs store `expiresAt` themselves and write ten different refresh mechanisms, race conditions and conflicting logic easily arise.

You can use `getExpiresAt()` for telemetry or redacted diagnostics, but **do not replace the manager with a custom-built Token Endpoint polling schedule** without a clear reason.

## 8. Nature of `principal` in the Service Manager

### 8.1. Principal Name Is the Key of the Authorized Client

`OAuth2AuthorizedClientService` normally looks up tokens by the pair:

```text
(clientRegistrationId, principalName)
```

Examples:

```text
("reporting-job", "service:reporting-job")
    -> access token issued for the job

("billing-job", "service:billing-job")
    -> access token of another Client

("company-login", "user-782")
    -> authorized client for a logged-in user (if stored)
```

If the same registration uses a different principal name on every run:

```java
// DO NOT DO THIS for stably shared Client Credentials tokens:
.principal("service:job:" + UUID.randomUUID())
```

the manager treats them as different authorized clients, increasing unnecessary token requests and stored records.

### 8.2. When to Use a Shared Principal?

If all runs of the same job represent **the Client itself** using `client_credentials`, a stable principal such as `"service:reporting-job"` is usually sensible. It does not depend on thread, session, or a user's username.

In a multi-tenant system, decide which ClientRegistration/credentials/scopes each tenant uses. Never use a single shared principal to share an authorized client across tenants that have different trust boundaries.

### 8.3. Never Use `principal` to Impersonate a User

Dangerous example:

```java
// NOT A MECHANISM TO REQUEST A TOKEN FOR AN ARBITRARY USER:
OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
    .withClientRegistrationId("company-user-login")
    .principal(requestedUserIdFromQueue)
    .build();
```

If a record in the store holds a user's authorized client, letting a caller choose `principalName` could allow the manager to look up that user's token. Therefore, code accessing the token store must be tightly controlled, especially in multi-user tasks.

**A `principal(String)` does not make the Authorization Server authenticate a new user.** It only specifies the identifier used when managing authorized clients; permission to use a token must be guarded by internal authorization and user consent policies.

### 8.4. How Do `Authentication` and a String Principal Name Differ?

`OAuth2AuthorizeRequest.Builder` supports passing either an `Authentication` or a `String` principal name.

- For user-facing web requests, passing a valid `Authentication` allows using the authenticated user's context.
- For background jobs using `client_credentials`, a stable String suffices to partition the authorized client.
- For jobs acting on behalf of a user, you must use the user identifier already linked to the right authorized client and verify who is allowed to trigger that task.

Never manually construct a fake “authenticated” `UsernamePasswordAuthenticationToken` just to pull a user's token. It is not proof that the user recently authenticated at the IdP.

## 9. Authorized Client Lifecycle: Issue, Reuse, Reissue

`authorize(...)` does not mean every call sends an HTTP request to the Token Endpoint.

A high-level lifecycle with `client_credentials`:

```mermaid
sequenceDiagram
    autonumber
    participant J as Scheduled Job
    participant M as Service AuthorizedClientManager
    participant S as OAuth2AuthorizedClientService
    participant P as ClientCredentialsProvider
    participant AS as Authorization Server

    J->>M: authorize(registrationId, service principal)
    M->>S: loadAuthorizedClient(registrationId, principalName)
    alt No token yet or reauthorization needed
        M->>P: authorize(context)
        P->>AS: POST /token grant_type=client_credentials
        AS-->>P: access_token + expires_in
        P-->>M: OAuth2AuthorizedClient
        M->>S: saveAuthorizedClient(...)
        M-->>J: New authorized client
    else Token still valid
        S-->>M: Saved authorized client
        M-->>J: Existing authorized client
    end
```

If the token is still valid according to provider policy, the manager can return the saved authorized client. When expired or requiring reissuance per rules, the Client Credentials Provider uses Client authentication to obtain a new token.

### 9.1. `authorize(...)` Can Return `null`

Per the `OAuth2AuthorizedClientManager` contract, `authorize(...)` can return `null` if authorization is not supported for the requested Client, such as when the grant in `ClientRegistration` is not supported by the configured providers.

Therefore:

```java
OAuth2AuthorizedClient client = manager.authorize(request);

if (client == null) {
    // No valid authorized client could be issued/retrieved by the manager
    // for an unsupported scenario; handle configuration error.
}
```

**Do not** immediately call `manager.authorize(...).getAccessToken()` while ignoring the `null` branch.

When reauthorization is unnecessary or unsupported but an **authorized client already exists**, the manager can return the existing authorized client per the contract. Thus `null` does not mean every token error is represented as `null`; many real failures throw exceptions.

### 9.2. A Non-Null Result Does Not Guarantee API Acceptance

The manager manages tokens based on the OAuth2 information available to the Client. The API can still reject the token because:

- The token was revoked out-of-band.
- The audience does not target the right Resource Server.
- Scopes are insufficient.
- Resource Server policy changed.
- Clock skew or token expiration differs from the Client's calculation.
- The Client accidentally used a token from the wrong registration/tenant.

Therefore, distinguish **errors obtaining a token from the Token Endpoint** from **API errors when using the token**. Do not delete the token and loop infinitely every time you see HTTP 403.

## 10. `OAuth2AuthorizedClientService` and Storage Options

### 10.1. What Does the Interface Do?

`OAuth2AuthorizedClientService` typically provides operations:

```java
<T extends OAuth2AuthorizedClient> T loadAuthorizedClient(
    String clientRegistrationId,
    String principalName
);

void saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal
);

void removeAuthorizedClient(
    String clientRegistrationId,
    String principalName
);
```

These are conceptual signatures of the primary methods; consult the Javadoc of your library version for exact nullable annotations and generics.

Unlike `OAuth2AuthorizedClientRepository` in web apps, this service **does not require an HTTP request/response** to access authorized clients.

### 10.2. `InMemoryOAuth2AuthorizedClientService`

Advantages:

- Simple configuration.
- Suitable for learning, testing, or single-instance services that can request a fresh token on restart.
- Requires no database or migrations.

Limitations:

- Tokens are lost when the process restarts.
- State is not shared across multiple instances.
- Unsuitable if user refresh tokens must survive restarts.
- Certain scenarios lack coordination mechanisms across workers.

With `client_credentials`, losing tokens on restart may be acceptable because the job can re-request using client credentials. However, if the system has strict rate limits or multiple instances, storage and retry strategies must still be considered.

### 10.3. `JdbcOAuth2AuthorizedClientService`

Spring Security provides a JDBC option to persist authorized clients in a database. Example wiring **replacing** in-memory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Bean
OAuth2AuthorizedClientService authorizedClientService(
        JdbcTemplate jdbcTemplate,
        ClientRegistrationRepository registrations) {

    return new JdbcOAuth2AuthorizedClientService(
        jdbcTemplate,
        registrations
    );
}
```

To run, you need the Spring JDBC dependency, a `DataSource`, and the **authorized client table schema** compatible with the Spring Security version in use. Adding the bean alone does not automatically create the table in the database.

Operational points:

- Run schema migrations according to the corresponding Spring Security documentation.
- Restrict database accounts that access the token table.
- Protect stored data, backups, and restore procedures.
- Consider encryption at rest and, for stricter requirements, application-layer token encryption.
- Clean up authorized clients no longer needed per retention policies.
- Design for refresh token rotation and concurrency when multiple instances update simultaneously.

**JDBC does not automatically solve all refresh race conditions.** It shares persistent data, but if two processes both read the old refresh token and send it to the Token Endpoint, contention can still occur.

### 10.4. Service and Repository Can Be Related

In a web application, `OAuth2AuthorizedClientRepository` can be implemented on top of `OAuth2AuthorizedClientService` for authenticated principals. However, do not assume every web configuration saves user authorized clients into the exact same service used by your background manager.

When a job needs to work with a **user-delegated authorized client** issued via browser login, verify the exact storage architecture:

- Where did OAuth2 Login save the authorized client?
- What principal name was used during browser login?
- Will the service manager look up that exact `registrationId` and principal name?
- Was a refresh token issued and persistently saved according to policy?
- Is the token permitted for offline use after the user leaves the application?

Failing to find an authorized client after user login is usually a **mismatched store or mismatched principal key** issue, not the Authorization Server losing the token.

## 11. Difference Between Refreshing with a Refresh Token and Requesting a New Token

Two cases are frequently conflated:

### 11.1. `client_credentials`: Using Client Authentication to Request Another Token

```text
Job needs token
  -> manager / ClientCredentialsProvider
  -> POST /token grant_type=client_credentials
  -> new access token
```

No user login needed, no `refresh_token` needed. Authorization Servers typically do not return a refresh token in the Client Credentials Grant.

### 11.2. `authorization_code` + `refresh_token`: Continuing User-Granted Permissions

```text
User already logged in and consented
  -> authorized client saved with refresh token (if issued by provider)
  -> job uses exact user principal
  -> RefreshTokenProvider
  -> POST /token grant_type=refresh_token
  -> new access token
```

In this flow, the background manager can only **reauthorize based on existing state**. It does not open a browser to start an authorization code flow.

### 11.3. One Manager Can Support Multiple Grants

If the infrastructure needs both client credentials and refresh tokens:

```java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .refreshToken()
        .build();

manager.setAuthorizedClientProvider(provider);
```

Still, each `ClientRegistration` has its own grant type and policy. Do not think adding `.refreshToken()` means the Client Credentials Grant automatically receives refresh tokens.

Mixing user-granted tokens and service tokens within one manager/store requires **very strict tenant, principal, and access controls** to prevent user A's token from being used in user B's job.

## 12. User-Delegated Background Processing Scenario

Suppose a user connects a calendar management app and consents to periodic background calendar synchronization. General workflow:

1. The user actively connects through the browser via the Authorization Code Flow.
2. The Authorization Server issues an access token and, if permitted, a refresh token.
3. The application saves `OAuth2AuthorizedClient` in secure storage, linked to the **internal user identifier** and appropriate registration.
4. The job is scheduled for the exact connection the user approved.
5. The background manager looks up the authorized client for the right user + registration.
6. If the access token is near expiry and a valid refresh token exists, the provider refreshes it.
7. The API is called using the user token with the appropriate audience/scopes.
8. If refresh fails or is revoked, stop syncing and move the connection to a `RECONNECT_REQUIRED` state; never fall back to another user's token.

### 12.1. Illustrative Code Looking Up a Token by Authorized Principal

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

public final class CalendarTokenService {

    private final OAuth2AuthorizedClientManager manager;

    public CalendarTokenService(OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    public OAuth2AuthorizedClient requireUserAuthorizedClient(
            String trustedUserPrincipalName) {

        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("calendar-connection")
                .principal(trustedUserPrincipalName)
                .build();

        OAuth2AuthorizedClient client = manager.authorize(request);

        if (client == null) {
            throw new IllegalStateException(
                "No usable calendar authorization for this user"
            );
        }

        return client;
    }
}
```

This snippet **only illustrates** how the manager accepts a principal; it is not a complete authorization workflow. `trustedUserPrincipalName` must come from a connection record **with verified ownership** for the current account, never an arbitrary query parameter.

If the registration uses the `authorization_code` grant while the background manager only has a `refreshToken()` provider, only an already-existing authorized client with a refresh token has a chance to be refreshed. Without an authorized client or refresh token, it cannot send the user to a consent screen.

### 12.2. Do Not Confuse Refresh Tokens with Login Sessions

An OIDC HTTP session may have expired while the user still allows offline access. The opposite can also happen: the session is active, yet the refresh token has been revoked.

Therefore:

- Offline access permissions require dedicated consent and policy.
- Application logout does not automatically revoke all refresh tokens.
- Users need UI controls to disconnect/revoke access when the product supports it.
- When refresh token rotation is enabled, the new token must be saved in place of the old one per the provider contract.
- Never send refresh tokens to the frontend or store them in job arguments/logs.

### 12.3. Why Not Add `authorizationCode()` to a Background Manager to Auto-Login?

The Authorization Code Grant is a flow requiring interaction with a user agent and callback to receive a code. A job has no browser/session, so it cannot “trigger login” just because the provider builder includes `authorizationCode()`.

`OAuth2AuthorizedClientProviderBuilder` describes **which grants may be processed**, not a way to create a user login channel outside a request. Design a separate interactive connect/reauthorize step and let jobs use only already-granted authorized clients.

## 13. Handling Errors at the Token Endpoint and in the Manager

The manager can encounter errors when issuing/refreshing tokens. Some common OAuth2 errors:

| Error | Common Meaning | How to Handle |
|---|---|---|
| `invalid_client` | Client ID/secret or Client authentication method is wrong | Check registration, secret rotation, and AS configuration |
| `unauthorized_client` | Client is not permitted to use the grant | Check grants registered at the Authorization Server |
| `unsupported_grant_type` | Token Endpoint does not support the requested grant | Check `authorization-grant-type` and endpoint |
| `invalid_scope` | Scope is invalid or not granted | Only request scopes permitted by the API contract |
| `invalid_grant` | Refresh token/code is invalid, expired, already used, or revoked | For refresh: discard invalid state and require reauthorization when needed |
| HTTP 429 | Provider is rate-limiting calls | Backoff appropriately, reduce token request frequency, avoid loops |
| HTTP 5xx / network timeout | Temporary error at the IdP or network | Bounded retries, observability, circuit breaker if appropriate |
| `null` from `authorize(...)` | Provider does not support registration's grant or no authorization result | Check provider builder/registration/context |
| API 401 `invalid_token` | Resource Server rejects the token used to call the API | Check audience, expiry, revocation, and retry policy |
| API 403 `insufficient_scope` | Token lacks permissions required by the API | Request proper permissions per consent/policy, do not refresh infinitely |

### 13.1. Default Success/Failure Handlers of the Service Manager

According to Spring Security Javadoc, `AuthorizedClientServiceOAuth2AuthorizedClientManager` by default:

- On authorization success, saves `OAuth2AuthorizedClient` into `OAuth2AuthorizedClientService`.
- On authorization failure due to **`invalid_grant`**, removes the previously saved authorized client from the service to avoid continuing to use stale error state.

These can be customized using hooks:

```java
manager.setAuthorizationSuccessHandler(customSuccessHandler);
manager.setAuthorizationFailureHandler(customFailureHandler);
```

However, **do not override a handler just to log one line and drop the default save/remove behavior**. If you provide custom handlers, explicitly preserve the required persistence and cleanup behavior. Do not blindly swallow `invalid_grant` and let the manager return an untrustworthy token.

### 13.2. Distinguishing Token Errors from Downstream API Errors

Suppose the manager obtains a token, yet the API returns 401. This is a **Resource Server error**, occurring **after** `manager.authorize` has already completed.

Do not assume the manager's failure handler will be invoked when `RestClient` sees an API 401, since that error does not necessarily pass through the manager. If using an HTTP client integrated with an OAuth2 interceptor, there may be a mechanism to forward authorization failures to the handler as configured. If manually attaching Bearer headers as in the `RestClient` example, define your own 401/403 handling strategy at the HTTP client layer.

Specifically:

- For 401 `invalid_token`, you may need to evict cached tokens/reauthorize or investigate a wrong audience.
- For 403 `insufficient_scope`, re-requesting a token with the same registration and old scopes usually will not solve the problem.
- For 429/5xx, deleting the token is unrelated to the root cause; retrying token requests infinitely can make the system worse.

### 13.3. Handling Exceptions in Jobs

A production job should classify errors so the scheduler does not crash pointlessly:

```java
try {
    OAuth2AuthorizedClient client = manager.authorize(authorizeRequest);

    if (client == null) {
        // Configuration error / unsupported grant.
        return;
    }

    // Call API using granted permissions.
} catch (org.springframework.security.oauth2.core.OAuth2AuthorizationException ex) {
    // Log only redacted error code/registrationId.
    String errorCode = ex.getError().getErrorCode();

    // Never log raw token requests, Authorization headers, or credentials.
    // Classify invalid_client, invalid_scope, invalid_grant, ...
}
```

This is an illustrative snippet, not a complete retry policy. In practice, configure alerts and failure handling aligned with business impact: a failed report sync may be safely retried; a payment action may need an idempotency key and stricter design.

## 14. Token Caching and Expiration

### 14.1. Why Use the Manager Instead of Always POSTing to the Token Endpoint?

If a job runs every 10 seconds while a token lives for 30 minutes, always calling the Token Endpoint would generate hundreds of unnecessary requests.

The manager + authorized client service can:

- Retain issued tokens for the same registration/principal.
- Reuse tokens when the provider determines they are still valid.
- Reissue tokens according to the grant mechanism when needed.
- Update the new token in the service after successful authorization.

This reduces load on the Token Endpoint, avoids rate limits, and centralizes token policy.

### 14.2. Clock Skew and Token Expiration

`OAuth2AccessToken` in Spring Security holds `issuedAt` and `expiresAt`. Depending on the provider/configuration, expiry evaluation may include a clock skew buffer.

A scenario:

```text
expiresAt = 10:00:00 UTC
API request starts = 09:59:59 UTC
Request arrives at Resource Server = 10:00:01 UTC
```

The token may be rejected by the API upon arrival. Therefore, token-managing providers typically refresh/reissue early by a configured tolerance window; do not force sending tokens right at expiry just because `now < expiresAt` on one node.

There is **no single universal clock skew value across all versions/flows**. Check the API/documentation of your provider and synchronize host/VM/container clocks via NTP or an equivalent service. Do not set skew excessively large to mask system clock drift.

### 14.3. Never Store Access Tokens in Static Fields

```java
// Wrong direction: token will fail when expired/revoked.
private static String sharedAccessToken;
```

That approach ignores lifecycle per registration/principal, loses expiry metadata, and is hard to update across multiple processes. Use `OAuth2AuthorizedClientService` + the manager to manage state rather than building a shared String cache yourself.

## 15. Multi-Instance, Multiple Jobs, and Concurrency

A service running across three Kubernetes pods may trigger the same cron scheduler simultaneously. If all three pods use separate `InMemoryOAuth2AuthorizedClientService` instances, each pod holds its own token and may request tokens concurrently upon expiry.

This is not necessarily wrong with the Client Credentials Grant, but evaluate:

- Authorization Server rate limits on the Token Endpoint.
- Number of concurrent tokens permitted.
- Whether the job is allowed to run multiple replicas or must have a single leader.
- API call cost / duplicated work.
- Token revocation/rotation policies.
- Secret rotation environments and whether instances pick up the latest credentials.

### 15.1. When Using a Shared Service Store

A `JdbcOAuth2AuthorizedClientService` can provide a shared authorized client across multiple instances. However, it is not itself a **distributed lock** or transaction coordinating every refresh.

Example race:

```text
Pod A reads expired token
Pod B reads same expired token
Pod A requests new token AT-2
Pod B concurrently requests new token AT-3
Pod A saves AT-2
Pod B saves AT-3
```

With the Client Credentials Grant, both access tokens may be valid or one may be invalidated depending on the provider. With **refresh token rotation**, the situation is more severe because an old refresh token may be single-use.

Design options depending on requirements:

- Accept per-instance tokens when `client_credentials` and rate limits permit.
- Use job leader election / a single scheduler instance to avoid duplicate runs.
- Use locking or distributed coordination when refresh tokens must be rotated safely.
- Persist the latest token with version control / optimistic locking if the store/logic supports it.
- Handle HTTP 401/`invalid_grant` according to policy instead of infinite retries.
- Only retrieve tokens issued for the exact tenant/user/registration.

Do not claim “using JDBC guarantees a token is refreshed only once across the cluster” without a dedicated synchronization layer.

### 15.2. Multi-Tenant

If each tenant has its own Client ID/secret/scopes/issuer, maintain a controlled registration or credential selection mechanism per tenant. The principal key must also be designed so two tenants never accidentally share an authorized client.

Example:

```text
Tenant A -> registration reporting-a -> principal service:reporting-a
Tenant B -> registration reporting-b -> principal service:reporting-b
```

Never take a tenant ID directly from an untrusted message to pick a privileged registration. Workers must verify tenant/resource ownership and only call APIs within a valid trust boundary.

## 16. Securing Secrets, Access Tokens, and Refresh Tokens

### 16.1. Protecting Client Credentials

`client_credentials` is typically used by confidential clients. The `client_secret` or Client private key is a critical credential:

- Store in a secret manager or secure runtime configuration.
- Never hard-code in Git, Docker images, or logs.
- Restrict secret read permissions in pods/service accounts.
- Plan secret rotation and rolling updates across instances.
- Only use Client authentication methods allowed by the Authorization Server.
- Prefer stronger Client authentication mechanisms such as `private_key_jwt` or mTLS when security requirements demand it and the provider supports it.

Never put `client_secret` in an Authorization URL, query string, or downstream API call.

### 16.2. Protecting Access/Refresh Tokens

- Bearer access tokens are typically usable directly as credentials; never print `getTokenValue()`.
- Refresh tokens, when present, must be strictly protected because they can mint new access tokens.
- Only send access tokens to APIs with the matching audience/host.
- Do not return tokens to the frontend if the backend can call the API instead.
- Do not place tokens inside message queue payloads or job arguments unnecessarily.
- Authorized client stores must have access control, encryption, and retention aligned with requirements.
- For per-user tokens, enforce principal ownership: background workers must never look up another user's token arbitrarily.

### 16.3. Do Not Confuse Client Credentials with User Sessions

A client credentials token represents application permissions; it **does not prove** a specific employee logged in. If an API requires user-level audit trails, do not fake a username into the manager principal to manufacture evidence.

For operations modifying sensitive data, the Resource Server may require a separate authorization model based on client identity, service identity, token exchange, or an appropriate delegation mechanism. Never use broad service account permissions to bypass user consent requirements.

## 17. Observability and Safe Logging

Useful metrics:

| Redacted Metric / Log | Purpose |
|---|---|
| `registrationId` | Know which Client is being used |
| Principal category (service/user) | Know credential type without logging sensitive identities |
| Token request success/failure counts | Measure Token Endpoint reliability |
| Token acquisition duration | Observe latency |
| Token reuse count | Check for abnormally repeated token requests |
| `expiresAt` or rounded remaining lifetime | Monitor token lifecycle |
| Resource Server HTTP status | Distinguish 401/403/429/5xx |
| OAuth2 error codes like `invalid_client` | Diagnose registration/credential issues |
| Retry/backoff count | Detect token issuance loops |

Never log:

```text
client_secret
access_token
refresh_token
Authorization: Bearer <token>
Authorization: Basic <client-credentials>
token request body containing secrets
JWT payload containing PII
```

Safe to log:

```text
oauth2_client_registration=reporting-job
authorization_result=success
token_reused=true
api_status=200
```

The log fields above are illustrative only. When tracking user-specific authorized clients, protect usernames, OIDC subjects, and tenant identifiers according to privacy policies.

### 17.1. Why Should Metrics Separate Token Grants from API Calls?

Suppose a job fails because the Reporting API returns `503` even though the token was issued properly. If metrics only report “OAuth2 job failed”, operations teams might needlessly rotate Client secrets.

Layering:

```text
registration lookup
  -> token acquisition/reauthorization
  -> HTTP API call
  -> business processing
```

helps pinpoint whether a failure belongs to Client configuration, the Authorization Server, the Resource Server, or business logic.

## 18. Design Patterns for Maintainable Code

Projects should generally avoid scattering `manager.authorize(...)` calls across controllers and services. You can create a dedicated **Access Token Provider** class built on top of the manager with clear policies:

- Allow only approved `registrationId` values.
- Set a stable, contextually clear principal name.
- Handle `null` and exceptions uniformly.
- Never log token values.
- Separate user-delegated tokens from service tokens.
- Never attempt to broaden permissions or inject extra scopes into tokens.

Example abstraction:

```java
public interface ServiceAccessTokenProvider {
    String requireTokenForReporting();
}
```

Implementation:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Component;

@Component
public class DefaultServiceAccessTokenProvider
        implements ServiceAccessTokenProvider {

    private final OAuth2AuthorizedClientManager manager;

    public DefaultServiceAccessTokenProvider(
            OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    @Override
    public String requireTokenForReporting() {
        var request = OAuth2AuthorizeRequest
            .withClientRegistrationId("reporting-job")
            .principal("service:reporting-job")
            .build();

        OAuth2AuthorizedClient client = manager.authorize(request);

        if (client == null) {
            throw new IllegalStateException(
                "Reporting OAuth2 client could not be authorized"
            );
        }

        return client.getAccessToken().getTokenValue();
    }
}
```

This class is for internal backend use only, not an endpoint returning tokens to a frontend. If multiple managers exist, declare `@Qualifier("serviceAuthorizedClientManager")` to prevent Spring from injecting the web manager by mistake.

### 18.1. When to Use an HTTP Interceptor Instead of Manually Setting the Bearer Header?

Spring Security provides OAuth2 Client integration for modern HTTP clients, such as `OAuth2ClientHttpRequestInterceptor` for `RestClient` in supported versions. The interceptor can obtain the authorized client via the manager and attach the Bearer token automatically.

Advantages:

- Avoids manually setting headers everywhere.
- Provides a unified configuration point for registration/principal resolution.
- Can hook into appropriate authorization failure handlers.

However, pay attention to:

- Your Spring Security/Framework version must support the interceptor used.
- Selecting the right manager (service manager for background tasks).
- Configuring a principal resolver tailored to the job, not depending on an arbitrary HTTP user's `SecurityContextHolder`.
- Never applying the interceptor to an HTTP client calling hosts outside an allowlist, avoiding sending Bearer tokens to the wrong destination.
- If using automatic HTTP client retries/redirects, controlling whether the `Authorization` header is forwarded to other hosts.

For a simple learning example, `headers.setBearerAuth(token)` makes it obvious where the token goes. For larger projects, an interceptor is often easier to maintain when configured properly.

## 19. Failure Cases Caused by Choosing the Wrong Context

### 19.1. Using a Request-Based Manager in a Worker

```text
@Scheduled
  -> DefaultOAuth2AuthorizedClientManager.authorize(...)
  -> no Servlet request
  -> request context error
```

**How to handle:** use `AuthorizedClientServiceOAuth2AuthorizedClientManager` and `OAuth2AuthorizedClientService`. Do not fabricate a fake request if the work does not need a browser session.

### 19.2. Using `@AuthenticationPrincipal` in a Job

`@AuthenticationPrincipal` is typically used in controllers/Servlet requests after Spring Security has authenticated a user. Background jobs have no default browser principal.

**How to handle:** for `client_credentials`, pick a stable service principal. For user-scoped tokens, retrieve the principal name from a trusted persisted authorized connection record after checking permissions.

### 19.3. Using a New UUID Principal on Every Job Run

`OAuth2AuthorizedClientService` looks up authorized clients by principal name. If the name changes every time, the manager creates many authorized clients and requests tokens more often than necessary.

**How to handle:** pick a stable principal aligned with the service/registration/tenant boundary.

### 19.4. Adding `refreshToken()` and Expecting a Refresh Token

The Authorization Server decides whether to issue a refresh token. `client_credentials` normally reuses the client's own credentials to request a new token; adding the refresh token provider does not change the Token Endpoint's response.

**How to handle:** use the grant suited to the goal and understand your provider's access/refresh token lifecycle.

### 19.5. Authorized Client Not Found After OIDC Login

If web login saves to a request/session repository while the background manager looks up in a different service, or the principal name differs, the job will not find the authorized client.

**How to handle:** design an appropriate shared store for the delegated flow, align principal names, and verify offline access issuance. Never copy raw refresh tokens into arbitrary business tables.

### 19.6. Repeatedly Requesting New Access Tokens on API 403

`403 insufficient_scope` is normally due to missing permissions, not an expired token.

**How to handle:** inspect scopes/audience/authorization and update Client permissions or consent per the provider. Unbounded token retries only cause high load.

### 19.7. Multiple Pods Using a Rotating Refresh Token Simultaneously

Two pods load the same refresh token and send refresh requests concurrently. One request can invalidate the old token before the other finishes.

**How to handle:** introduce coordination, persist the latest refresh token, and handle conflicts; do not treat JDBC storage as a distributed lock.

## 20. Quick Diagnostic Table

| Symptom | Where to Check | Resolution |
|---|---|---|
| `No thread-bound request` | Manager implementation | Switch to the service-based manager for workers |
| `authorize(...)` returns `null` | Provider builder, registration grant | Add the appropriate provider or recognize the flow needs interaction |
| `invalid_client` | Client ID/secret/auth method | Check credentials and Token Endpoint |
| `unsupported_grant_type` | `authorization-grant-type`, AS policy | Use a permitted grant |
| `invalid_scope` | Scopes in registration | Request only granted permissions |
| Job fetches a new token on every run | Changing principal key / non-persisting store / token TTL | Check `(registrationId, principalName)` |
| Job loses user refresh token after restart | In-memory service | Use durable storage and proper onboarding/consent |
| Job cannot see logged-in user's token | Web repository differs from service or principal mismatch | Check persistence mechanism and principal mapping |
| Token valid yet API returns 401 | Audience, revocation, clock, host/API | Check Resource Server and token target |
| API returns 403 | Scope/role/permission | Do not refresh infinitely |
| Token Endpoint hammered with requests | Multiple instances, close expiry, unstable principal | Review caching, coordination/backoff |
| Refresh returns `invalid_grant` | Refresh token revoked/expired/rotated | Evict stale state and require reconnection |
| Token response written to logs | Overly broad logging/observability | Redact tokens, lower verbosity, remediate exposure |
| Missing `OAuth2AuthorizedClientService` bean | Missing OAuth2 Client config or incompatible auto-config | Declare service bean explicitly |
| Two `OAuth2AuthorizedClientManager` beans | Ambiguous dependency injection | Use `@Qualifier` |

## 21. Practical Exercises

### Exercise 1: Choosing the Manager

An MVC application has a controller for logged-in users and an hourly `@Scheduled` job calling a system API. Which manager should be used for the scheduled job?

**Suggested answer:** `AuthorizedClientServiceOAuth2AuthorizedClientManager`, because the job has no `HttpServletRequest`. The controller running inside a Servlet request can use `DefaultOAuth2AuthorizedClientManager` when appropriate.

### Exercise 2: Choosing the Grant

A service does not represent a user and only needs a token to read `reports.read` from an API.

**Suggested answer:** `client_credentials` if permitted by the Authorization Server, with an appropriate `ClientRegistration` and a service-based manager configured with `.clientCredentials()`.

### Exercise 3: Principal in the Background

A developer calls:

```java
OAuth2AuthorizeRequest.withClientRegistrationId("reporting-job")
    .principal(UUID.randomUUID().toString())
    .build();
```

Every time the scheduler runs, a different principal is generated. What is the problem?

**Suggested answer:** tokens are stored by registration + principal, so the same authorized client cannot be stably reused; this causes redundant token requests and storage records. For a job representing the same Client, use a stable service principal.

### Exercise 4: User OAuth2 Login and Background Jobs

A user logs in via `company-login` in the browser. A job has a manager supporting only `.clientCredentials()` yet wants to call an API with the user's token.

**Suggested answer:** those are two different flows. To run a job with user-granted permissions, you need the user's authorized client stored safely with refresh/offline access capability when allowed by the provider; the principal must match and the manager's provider must handle refresh tokens. Never use the Client Credentials Grant to impersonate user permissions.

### Exercise 5: Persistence After Restart

An application uses `InMemoryOAuth2AuthorizedClientService`. After a restart, the `client_credentials` job still works after requesting a new token, whereas the user-delegated job loses its authorized client.

**Suggested answer:** this is expected with in-memory storage. Client Credentials can re-request using application credentials; user-delegated access requires durable storage, consent, and token lifecycle design.

### Exercise 6: Resource Server Returns 403

A job has a valid access token, yet the API reports `insufficient_scope`. Should you delete the authorized client and retry indefinitely?

**Suggested answer:** no. Check the scopes, audience, and permissions granted by the Authorization Server/Resource Server. Refreshing with the same permissions usually does not fix missing scopes.

### Exercise 7: Client Credentials and Refresh Token

Token response:

```json
{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "reports.read"
}
```

There is no `refresh_token`. Is the provider misconfigured?

**Suggested answer:** no. For `client_credentials`, Authorization Servers typically do not issue a refresh token. When another token is needed, the Client uses its credentials to request a new one from the Token Endpoint.

### Exercise 8: Two Instances Running the Same Job

Two pods share a JDBC token service. At 10:00 sharp the token expires, and both request a new token at the same time. Does using JDBC already guarantee only one token request occurs?

**Suggested answer:** not yet. A shared store does not automatically replace distributed coordination/locking. Depending on risk, either accept controlled contention or design leader election/locking; with refresh token rotation, extra care is essential.

### Exercise 9: Handling `authorize(...) == null`

A job writes:

```java
String token = manager.authorize(request)
    .getAccessToken()
    .getTokenValue();
```

What needs to change?

**Suggested answer:** separate the step receiving `OAuth2AuthorizedClient`, check for `null`, and classify configuration/grant errors; handle exceptions explicitly. Never assume `authorize` always succeeds or always issues a new token.

## 22. Production Design Checklist

Before operating a background OAuth2 client in production, verify:

- [ ] Tasks running **outside HTTP requests** use the service-based manager?
- [ ] Every registration uses a grant genuinely permitted by the Authorization Server?
- [ ] For service-to-service, does the Client Credentials Grant have minimal scopes/audience?
- [ ] Is the job's `principalName` stable without mixing users/tenants?
- [ ] Is the chosen `OAuth2AuthorizedClientService` aligned with restart/scale-out needs?
- [ ] Are access/refresh tokens and Client secrets protected and excluded from logs?
- [ ] Does `authorize(...)` handle `null` and exceptions?
- [ ] Are Token Endpoint errors distinguished from API 401/403 responses?
- [ ] Do retry/backoff and rate limiting avoid infinite token-request loops?
- [ ] Do multi-instance tasks have a strategy to prevent duplicate work/refresh races?
- [ ] For user-delegated jobs, are consent, user-matched authorized clients, and reauthorization policies in place?
- [ ] Is there a way to disconnect/revoke access and invalidate state when needed?
- [ ] Do metrics separate authorization, downstream API calls, and business logic?
- [ ] Do HTTP clients send Bearer tokens only to trusted hosts/resources?
- [ ] Are policies in place for secret rotation, token revocation, and clock skew?

This checklist guides design decisions; it does not replace verifying the actual configuration of your Authorization Server, Resource Server, and library version.

## 23. Official References

1. [Spring Security Reference — OAuth2 Client Core Interfaces and Classes](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html): `OAuth2AuthorizedClientManager`, service manager, providers, and `client_credentials` examples.
2. [Spring Security API — AuthorizedClientServiceOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html): context outside Servlet requests, persistence, and `invalid_grant` handling.
3. [Spring Security API — DefaultOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizedClientManager.html): manager for `HttpServletRequest` and `OAuth2AuthorizedClientRepository`.
4. [Spring Security API — OAuth2AuthorizeRequest.Builder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizeRequest.Builder.html): `withClientRegistrationId` and `principal(String)` / `principal(Authentication)`.
5. [Spring Security API — OAuth2AuthorizedClientService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientService.html): `loadAuthorizedClient`, `saveAuthorizedClient`, `removeAuthorizedClient`.
6. [Spring Security API — OAuth2AuthorizedClient](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClient.html): `ClientRegistration`, access token, and refresh token.
7. [Spring Security API — OAuth2AuthorizedClientProviderBuilder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientProviderBuilder.html): selecting `clientCredentials`, `refreshToken`, and grant providers.
8. [Spring Security Reference — Authorized Client Features](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): integrating OAuth2 Client with HTTP clients and principal policies.
9. [RFC 6749 — OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749): Client Credentials Grant, Refresh Token Grant, and token response model.
10. [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): security practices for tokens, Clients, and grants.

## 24. Summary

**`AuthorizedClientServiceOAuth2AuthorizedClientManager` is the manager for using OAuth2 Client outside `HttpServletRequest`**, such as scheduled tasks, queue consumers, or service-to-service background jobs. It combines **`ClientRegistrationRepository`**, **`OAuth2AuthorizedClientService`**, and **`OAuth2AuthorizedClientProvider`** to find, issue, store, and reissue authorized clients according to supported grants.

For user-independent jobs, the usual right choice is **`client_credentials`**, a stable service principal name, and an appropriate token storage mechanism. For jobs running with user permissions, only use an authorized client granted by the user, with the matching principal and refresh/offline access policies; a String principal is neither permission to impersonate a user nor a way to start OIDC Login automatically.

When implementing, clearly separate **the web request manager** from **the background manager**, store tokens in the right place, handle `authorize(...) == null`, keep grants/scopes minimal, and prevent leaking Client secrets or refresh tokens. That is the foundation for background tasks that use OAuth2 safely, reuse tokens effectively, and operate reliably as the system scales.
