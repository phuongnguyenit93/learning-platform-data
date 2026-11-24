# Choosing the Right Manager in Web Requests vs. Out-of-Request Tasks

> **Topic:** Spring Security – reactive  
> **Group:** OAuth2 Client  
> **Lesson:** Choose the right `ReactiveOAuth2AuthorizedClientManager` when the application has a `ServerWebExchange` (a WebFlux request) and when tasks run **outside a request** (schedulers, queue consumers, batch jobs, service-to-service).  
> **Example version scope:** Java 17+, Spring Boot 3.5.x, and Spring Security 6.5.x; core APIs are verified against the official Spring Security documentation.

## 1. The Problem: One WebClient Pattern, Two Different Contexts

Suppose a Spring WebFlux application has two requirements:

1. User `alice` logs into the website, clicks "View Report", and the backend calls a downstream API using an **access token issued for the user/client**. The call executes inside an HTTP request that has a `ServerWebExchange`, `Authentication`, `WebSession`, and web attributes.
2. A `@Scheduled` task runs nightly to synchronize reports. There is no browser, incoming HTTP request, `ServerWebExchange`, or user login. The job requests an access token using `client_credentials` to call the downstream API under **the service's own identity**.

Both need an **OAuth2 Client** capable of issuing or renewing an access token before calling the API, yet **you must not blindly use the same manager for both**.

**Selection rule:**

| Context | Reactive Spring Security Manager to Use | Authorized Client Storage |
| --- | --- | --- |
| Inside a WebFlux HTTP request with `ServerWebExchange` | `DefaultReactiveOAuth2AuthorizedClientManager` | `ServerOAuth2AuthorizedClientRepository` |
| Outside an HTTP request, in a scheduler/queue/service tier | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientService` |

Both implement **`ReactiveOAuth2AuthorizedClientManager`**; they differ in **available context, how tokens are loaded/saved, and which grant and principal are used**. There is no rule saying "if you use `WebClient`, pick the web manager"; the name `WebClient` only indicates a **reactive** HTTP client, not that your code runs inside a server web request.

### After This Lesson You Will Be Able To

- Correctly explain `OAuth2AuthorizedClient`, `ReactiveOAuth2AuthorizedClientManager`, `ReactiveOAuth2AuthorizedClientProvider`, registrations, and the two store types.
- Choose the right manager based on the presence of `ServerWebExchange`, not based on the class calling it.
- Call `authorize(OAuth2AuthorizeRequest)` properly and understand when the result is `Mono.empty()`.
- Distinguish `authorization_code` + `refresh_token` for user contexts from `client_credentials` for system tasks.
- Set `clientRegistrationId`, `Authentication`/principal, and web exchange accurately.
- Configure two `WebClient` beans with separate `@Qualifier`s so Bearer tokens are never sent to arbitrary hosts.
- Use `StepVerifier` to test tokens **pre-seeded in the store** without depending on a real IdP, while knowing the limits of those tests.
- Avoid blocking calls, cross-user token leaks, wrong cache keys, reusing user-request tokens in background tasks, and configuration failures.

## 2. What Does OAuth2 Authorized Client Mean?

A `ClientRegistration` merely describes **an application registered with the Authorization Server**:

```text
registrationId, clientId, clientSecret,
authorizationGrantType, scopes,
authorizationUri/tokenUri/redirectUri ...
```

It is **not** an access token. Once the OAuth2 Client is authorized and obtains a token, Spring Security represents that state via `OAuth2AuthorizedClient`:

```text
OAuth2AuthorizedClient
  ├── ClientRegistration  (which client?)
  ├── principalName       (which user or system identity?)
  ├── OAuth2AccessToken   (Bearer token and expiration)
  └── OAuth2RefreshToken? (if issued)
```

Crucially: an authorized client binds **`registrationId` + principal name**. When web user `alice` has a token for `reports-user`, that token **is not automatically reused** for `bob`. For a batch job, a principal like `reports-scheduler` is just a **stable name to identify/cache the service's token**; it **does not turn a `client_credentials` token into a user token**.

### 2.1. What Responsibilities Does the Manager Have?

`ReactiveOAuth2AuthorizedClientManager` has one primary API:

```java
Mono<OAuth2AuthorizedClient> authorize(
    OAuth2AuthorizeRequest authorizeRequest);
```

This is the **API signature** (not a method you implement yourself). The manager is responsible for:

1. Looking up the client registration by `clientRegistrationId`.
2. Loading any saved `OAuth2AuthorizedClient` for the corresponding principal.
3. Invoking the appropriate `ReactiveOAuth2AuthorizedClientProvider` to **authorize/re-authorize**, such as code grant, refresh token, or client credentials.
4. On success, saving/updating the authorized client via the appropriate repository or service.
5. On failure, handling it via a failure handler/policy; some errors such as `invalid_grant` may delete the stale token/authorized client.

Not every `authorize` call makes a network request to the Authorization Server. A **still-valid** token in the store can be reused; a token needing refresh or not yet obtained can trigger the token endpoint.

### 2.2. Providers Decide Grants, Managers Decide Coordination

`ReactiveOAuth2AuthorizedClientProvider` is the strategy for authorization grants. Use the builder:

```java
ReactiveOAuth2AuthorizedClientProvider webProvider =
    ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build();

ReactiveOAuth2AuthorizedClientProvider jobProvider =
    ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();
```

This selection **does not alter the registration itself**. If a registration declares `client_credentials`, a provider supporting only `authorization_code` cannot authorize it. Conversely, if a job uses an `authorization_code` registration without a user or browser, an out-of-request manager **cannot fabricate the redirect/consent step**.

Do not enable all grant types just to "prevent errors"; each flow has its own threat model. The `password` grant has been dropped from OAuth 2.1 and should not be chosen for new designs. `client_credentials` is meant for service-to-service calls, while `authorization_code` is for user-interactive flows.

## 3. Manager One: DefaultReactiveOAuth2AuthorizedClientManager

### 3.1. Use When a ServerWebExchange Is Present

Full class name:

```java
org.springframework.security.oauth2.client.web
    .DefaultReactiveOAuth2AuthorizedClientManager
```

Constructor:

```java
new DefaultReactiveOAuth2AuthorizedClientManager(
    ReactiveClientRegistrationRepository clientRegistrations,
    ServerOAuth2AuthorizedClientRepository authorizedClients);
```

Spring Security's Javadoc specifies this as the manager to use **within the context of a `ServerWebExchange`**, because it loads and saves authorized clients per user/request/session using `ServerOAuth2AuthorizedClientRepository`.

Suitable scenarios:

- A user is interacting with the WebFlux application via a browser.
- A user's OAuth2 Login/OIDC flow has established an `Authentication`.
- A controller or service handling a request needs a downstream access token bound to the user.
- Authorization Code/OIDC and refresh tokens are properly configured.
- The authorization repository stores tokens tied to the user or `WebSession` per policy.

### 3.2. Where Are Tokens Read and Stored?

`ServerOAuth2AuthorizedClientRepository` is the request-bound abstraction:

```java
Mono<T> loadAuthorizedClient(
    String registrationId,
    Authentication principal,
    ServerWebExchange exchange);
```

There are also `saveAuthorizedClient(...)` and `removeAuthorizedClient(...)`. The interface has the generic type bound `T extends OAuth2AuthorizedClient`, so the snippet above depicts the shape rather than a complete self-contained interface declaration.

Common implementations:

- `WebSessionServerOAuth2AuthorizedClientRepository`: authorized clients tied to `WebSession`, useful for unauthenticated web flows or session-scoped storage.
- `AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository`: for authenticated principals, delegates storage to `ReactiveOAuth2AuthorizedClientService`; for anonymous users, it can fall back to the WebSession repository. **Never assume every web token is stored exclusively in the session.**

`DefaultReactiveOAuth2AuthorizedClientManager` uses default authorization success/failure handlers to save or remove authorized clients in the repository. You can replace the handlers for custom storage/audit/TTL needs, provided consistency is preserved on refresh and token invalidation.

### 3.3. Is Passing the Exchange Mandatory?

When calling the manager **directly**, supply `ServerWebExchange` in the attributes:

```java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("reports-user")
        .principal(authentication)
        .attribute(ServerWebExchange.class.getName(), exchange)
        .build();

Mono<OAuth2AuthorizedClient> authorized =
    webAuthorizedClientManager.authorize(request);
```

This snippet **belongs inside a method that has real `authentication` and `exchange` variables**. The attribute name is `ServerWebExchange.class.getName()`, an API documented by Spring Security. Never construct a fake exchange in production just to "satisfy" the manager; **if there truly is no inbound web request, choose the service manager**.

When using WebClient's `ServerOAuth2AuthorizedClientExchangeFilterFunction`, helpers are available:

```java
.attributes(clientRegistrationId("reports-user"))
.attributes(serverWebExchange(exchange))
```

Both helpers reside in `org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction`. Depending on the call path, the framework may resolve the exchange from the context; passing it explicitly aids auditing when a service receives the exchange from a controller.

### 3.4. User Tokens Must Stay Bound to the Right User

A severe security bug:

```java
// Wrong: storing one authorized client for Alice in a shared static variable.
static OAuth2AuthorizedClient lastAuthorizedClient;
```

If Bob calls the service after Alice, reading `lastAuthorizedClient` can send Alice's access token to the API or return Alice's data to Bob. Always use a repository/service **keyed by registrationId + principal**, or pass the current request's authorized client explicitly—never cache globally under a single shared key.

## 4. Manager Two: AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager

### 4.1. Use Outside a ServerWebExchange

Full class name:

```java
org.springframework.security.oauth2.client
    .AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
```

Constructor:

```java
new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
    ReactiveClientRegistrationRepository clientRegistrations,
    ReactiveOAuth2AuthorizedClientService authorizedClientService);
```

Javadoc states this class **can operate outside a `ServerWebExchange` context**, for example:

- `@Scheduled` tasks / timed jobs.
- Queue consumers (Kafka, RabbitMQ, cloud tasks).
- Batch import/export or command-line/worker jobs.
- Service-tier calls to an API when **there is no inbound HTTP request**.
- Background publishers triggered after an HTTP request has completed.
- B2B machine-to-machine `client_credentials` requiring no user login.

There is no reason to force a `ServerWebExchange` into a job; nor should you grab an old web request from static/global/ThreadLocal storage and reuse it.

### 4.2. Using ReactiveOAuth2AuthorizedClientService

`ReactiveOAuth2AuthorizedClientService` provides:

```java
Mono<T> loadAuthorizedClient(
    String registrationId, String principalName);
Mono<Void> saveAuthorizedClient(OAuth2AuthorizedClient authorizedClient);
Mono<Void> removeAuthorizedClient(
    String registrationId, String principalName);
```

`loadAuthorizedClient` uses the generic bound `T extends OAuth2AuthorizedClient`; the snippet illustrates the familiar signatures.

A default implementation is `InMemoryReactiveOAuth2AuthorizedClientService`, which is not durable across restarts and **does not synchronize across multiple replicas**. If tasks run across multiple instances or refresh tokens must survive restarts, consider a database-backed implementation (such as R2DBC) along with policies for encrypting secrets, synchronizing renewals, handling token failures, and isolating tenants.

**Do not confuse them:**

```text
ReactiveClientRegistrationRepository:
    stores CONFIGURATION: client_id, grant_type, endpoints, scopes.

ReactiveOAuth2AuthorizedClientService:
    stores authorization RESULTS: access/refresh tokens + principal + registration.

ServerOAuth2AuthorizedClientRepository:
    operates on authorized clients within a request/web session/user context.
```

### 4.3. Choosing a Stable Principal for Batch Jobs

Even though `client_credentials` has no end-user, `OAuth2AuthorizeRequest` **still requires a principal** so the manager can key the authorized client. Example:

```java
Authentication system =
    new UsernamePasswordAuthenticationToken(
        "reports-scheduler",
        "not-a-password",
        List.of(new SimpleGrantedAuthority("ROLE_SYSTEM")));

OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("reports-batch")
        .principal(system)
        .build();

return jobAuthorizedClientManager.authorize(request);
```

`principal` here is the **cache/storage key for the `client_credentials` authorization**, not a real user, and must not be used to bypass Resource Server permissions. The Resource Server still validates the access token (issuer, signature/introspection, audience, and scopes).

If each job run uses a random principal, the service stores many `OAuth2AuthorizedClient` entries for the same client registration, hurting cache hit rates and causing token churn. Conversely, sharing one principal across **multiple tenants or registrations with differing permissions** blurs boundaries; pick consistent principal names per service/tenant and scope registrations accordingly.

## 5. Manager Selection Decision Tree

```text
Start: code needs a token to call a downstream API
  |
  +-- Is an active inbound WebFlux ServerWebExchange present?
  |      |
  |      +-- YES: is the token tied to the website user?
  |      |         |
  |      |         +-- YES:
  |      |         |   DefaultReactiveOAuth2AuthorizedClientManager
  |      |         |   + ServerOAuth2AuthorizedClientRepository
  |      |         |   + user principal / exchange
  |      |         |
  |      |         +-- NO, token belongs to the backend itself / client_credentials:
  |      |             Can isolate a separate service manager
  |      |             to avoid coupling to request/user session.
  |      |
  |      +-- NO (scheduler/queue/background):
  |                AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
  |                + ReactiveOAuth2AuthorizedClientService
  |                + stable service principal
  |
  +-- Does ClientRegistration grant type match the provider?
  +-- Is the access token issued for the right API/scopes/tenant?
  +-- Does the store enforce isolation and clear refresh/failure policies?
```

**Nuance:** When an HTTP request is present but the downstream call intentionally uses the backend's **`client_credentials`** token, a service manager can still be the cleaner choice to avoid coupling with the user or `WebSession`. The crux is not "HTTP present = must use web manager", but **what the token and authorized-client lifecycle belong to**. Conversely, never pick the web manager in a job merely because the code uses `WebClient`.

### 5.1. Practical Scenario Table

| Scenario | Preferred Manager | Principal | Grant and Reason |
| --- | --- | --- | --- |
| Controller handling Alice's dashboard, calling API on Alice's behalf | Web manager | Alice | Authorization Code/OIDC, refreshes user token |
| Logged-in user, controller uses `@RegisteredOAuth2AuthorizedClient` | Framework web repository/client manager | Current user | Uses the request's authorized client |
| Web endpoint triggers system report unrelated to user permissions | Service manager | Service/tenant | Client credentials, prevents user token leaks |
| `@Scheduled` nightly data sync | Service manager | `reports-scheduler` | Client credentials, no exchange |
| Kafka consumer syncing inventory | Service manager | `inventory-worker` | Client credentials / service identity |
| CLI/`CommandLineRunner` calling an API | Service manager | `cli-service` | No HTTP request |
| Reactive service called by controller to get user's token | Web manager or explicitly passed authorized client | User | Request context available; avoid global token lookup |
| Async publisher executing after request ends, exchange gone | Service manager if using service identity; if user authorization needed, design separate delegation/token storage | Depends on use case | Never assume web Reactor Context still exists |
| API Resource Server only validating inbound Bearer tokens | No OAuth2 Client manager needed | Inbound JWT principal | Use `oauth2ResourceServer`, does not fetch tokens itself |
| Authorization Server issuing access tokens to clients | Not the purpose of either manager | AS identity | Use dedicated Authorization Server product/config |

## 6. Most Common Mistakes

### 6.1. Relying Solely on a Default ReactiveOAuth2AuthorizedClientManager Bean

Spring Boot/Spring Security can auto-create a default `ReactiveOAuth2AuthorizedClientManager` if none is defined. However, **never assume the default bean is optimal for every context**. When a project has both WebFlux requests and background jobs, explicitly define the manager type, principal, and storage for each use case. If two beans implement the same interface, every injection point needs `@Qualifier` or a distinct bean name to avoid ambiguous dependencies.

### 6.2. WebClient Does Not Imply Web Manager

```java
WebClient client = WebClient.builder().build();
```

That object is purely a reactive HTTP client. It **does not contain a `ServerWebExchange`**. In a scheduler, `WebClient` runs fine, whereas using `DefaultReactiveOAuth2AuthorizedClientManager` can fail due to a missing request exchange/repository context. Inside a controller, `WebClient` can use the web manager to fetch a user token. **Execution context** and **authorized principal** determine the manager.

### 6.3. No Authentication in a Scheduler

`ReactiveSecurityContextHolder.getContext()` can return `Mono.empty()` in a scheduler because there is no HTTP login. Never fabricate a "fake Alice authentication" and attach it to a job to reuse a user token. For service-to-service work, use `client_credentials` and an explicit system principal. If business rules require acting *on behalf of Alice*, use an AS-approved delegation/on-behalf-of mechanism with proper data protection—never "grab Alice's latest token" from cache.

### 6.4. Writing Imperative Code That Blocks the Reactive Pipeline

```java
// Wrong in the WebFlux event loop:
OAuth2AuthorizedClient c = manager.authorize(request).block();

// Wrong if the subscription is unmanaged:
manager.authorize(request).subscribe(client -> callSomething(client));
```

In reactive methods, **return** a `Mono` or compose with `flatMap`:

```java
return manager.authorize(request)
    .switchIfEmpty(Mono.error(
        new IllegalStateException("No authorized client")))
    .flatMap(client -> downstreamCall(client));
```

Never log tokens. For scheduled jobs, starting a subscription at the task-runner boundary requires lifecycle management, retries, timeouts, cancellation, and monitoring; do not fire stray `.subscribe()` calls inside business services and silently lose error signals. If a scheduler API is imperative, use a cleanly designed adapter on an appropriate scheduler and **never block the Netty event loop**; never apply `.block()` indiscriminately.

## 7. Where Do Web Flows and Job Flows Differ?

### 7.1. Web User Flow

```text
Browser Alice
   |
   v
GET /web/report
   |
   v
Spring Security WebFlux: Authentication(Alice) + ServerWebExchange
   |
   v
DefaultReactiveOAuth2AuthorizedClientManager
   |   + registrationId = reports-user
   |   + principal = Alice
   |   + exchange = current request
   |
   v
ServerOAuth2AuthorizedClientRepository
   |   + find Alice's existing token
   |   + refresh when needed and permitted
   |
   v
OAuth2AuthorizedClient(Alice)
   |
   v
WebClient -> Authorization: Bearer ALICE_ACCESS_TOKEN -> API
```

Use providers supporting authorization code and refresh token once prior authorization exists. Without prior login/consent/authorization, the web request must initiate an **Authorization Code redirect** (normally handled by `oauth2Login`/the framework); you cannot mint an "Alice" access token from a username alone.

### 7.2. Scheduler/Service Flow

```text
@Scheduled / queue consumer / batch job
   |
   v
No ServerWebExchange
   |
   v
AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
   |   + registrationId = reports-batch
   |   + principal = reports-scheduler
   |
   v
ReactiveOAuth2AuthorizedClientService
   |   + find valid service access token
   |   + client_credentials when token missing/expired
   |
   v
OAuth2AuthorizedClient(reports-scheduler)
   |
   v
WebClient -> Authorization: Bearer SERVICE_ACCESS_TOKEN -> API
```

Normally **`client_credentials` does not issue a refresh token**; when the access token expires, the client uses that same grant to **request a new access token** from the Token Endpoint. Do not configure `refreshToken()` merely wanting the job token to renew itself; the `clientCredentials()` provider handles re-authorization per framework policy.

### 7.3. Avoid Redundant Re-Authorization at Every Step

The manager handles token caching and refresh via the store. Do not manually call the token endpoint per HTTP request by hand-POSTing `grant_type=client_credentials`. Use the injected manager and service to keep the token lifecycle consistent while preventing multiple workers from flooding the token endpoint simultaneously. For high-throughput or multi-node workloads, control concurrency, rate limits, retries, and shared storage appropriately.

## 8. Two WebClients and Choosing clientRegistrationId

A `WebClient` can integrate `ServerOAuth2AuthorizedClientExchangeFilterFunction`:

```java
@Bean("userWebClient")
WebClient userWebClient(
        @Qualifier("webManager")
        ReactiveOAuth2AuthorizedClientManager webManager) {
    var oauth2 = new ServerOAuth2AuthorizedClientExchangeFilterFunction(
        webManager);
    return WebClient.builder().filter(oauth2).build();
}

@Bean("batchWebClient")
WebClient batchWebClient(
        @Qualifier("jobManager")
        ReactiveOAuth2AuthorizedClientManager jobManager) {
    var oauth2 = new ServerOAuth2AuthorizedClientExchangeFilterFunction(
        jobManager);
    return WebClient.builder().filter(oauth2).build();
}
```

These are snippets from a `@Configuration`; the complete version with imports is in section 11.

In a web request:

```java
return userWebClient.get()
    .uri("https://api.example.invalid/user/report")
    .attributes(clientRegistrationId("reports-user"))
    .attributes(serverWebExchange(exchange))
    .retrieve()
    .bodyToMono(String.class);
```

In a job with a service principal **requiring no exchange**:

```java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("reports-batch")
        .principal(systemAuthentication)
        .build();

return jobManager.authorize(request)
    .switchIfEmpty(Mono.error(
        new IllegalStateException("No service authorized client")))
    .flatMap(authorized ->
        batchWebClient.get()
            .uri("https://api.example.invalid/system/report")
            .attributes(oauth2AuthorizedClient(authorized))
            .retrieve()
            .bodyToMono(String.class));
```

In the second snippet, `oauth2AuthorizedClient(authorized)` is passed explicitly so `WebClient` does not inadvertently pick up a user from the Reactor Context or fail from a missing principal. Check the exact version's Javadoc for whether the filter re-checks or re-authorizes when an explicit client's token expires.

**Security critical:** `setDefaultOAuth2AuthorizedClient(true)` or `setDefaultClientRegistrationId(...)` can attach a Bearer token to **every request** sent through that `WebClient`. Never enable defaults on a shared WebClient that could call arbitrary hosts, follow uncontrolled redirects, or accept URLs from client input. Use separate `WebClient` beans per trusted downstream origin, pass `clientRegistrationId`/authorized client **explicitly**, enforce a host allowlist, and prevent access-token exfiltration.

### 8.1. Two WebClient Filter Constructors Are Not Identical

`ServerOAuth2AuthorizedClientExchangeFilterFunction` has two common constructors:

```java
new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    ReactiveOAuth2AuthorizedClientManager manager);
```

and:

```java
new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    ReactiveClientRegistrationRepository registrations,
    ServerOAuth2AuthorizedClientRepository repository);
```

According to Spring Security 6.5 Javadoc, the constructor taking `registrations + repository` automatically configures `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` to handle certain downstream 401/403 responses by OAuth2 error code; the constructor taking a **manager** does not automatically attach this failure handler to the filter. When using a custom manager, consider configuring `setAuthorizationFailureHandler(...)` with the matching backing repository/service. Do not treat **every 403** as an invalid token—a 403 may simply indicate a missing scope or permission, in which case the token should not be unconditionally evicted.

Distinguish two error classes:

- **Authorization failures when requesting/refreshing a token** from the AS (e.g., `invalid_grant`) are handled by the manager/provider and its handler.
- **401/403 from a downstream Resource Server** occur during the `WebClient` request; the filter's failure handler inspects the Bearer challenge/error to remove a cached authorized client when appropriate.

Never retry infinitely on refresh failures or 403 permission denials, avoiding request storms and error leaks.

## 9. Storage, Scopes, and Principals: Comparison Model

| Aspect | Web Manager | Service Manager |
| --- | --- | --- |
| Class name | `DefaultReactiveOAuth2AuthorizedClientManager` | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
| Interface | `ReactiveOAuth2AuthorizedClientManager` | Same interface |
| Context | `ServerWebExchange`, principal from request | No request needed, system principal |
| Store | `ServerOAuth2AuthorizedClientRepository` | `ReactiveOAuth2AuthorizedClientService` |
| Principal examples | `alice`, `bob` | `reports-scheduler`, `inventory-worker` |
| Grant examples | `authorization_code`, `refresh_token` | `client_credentials` |
| Session | Can use WebSession or per-user storage | Requires no WebSession |
| Typical use | BFF/website calling APIs on behalf of users | M2M, schedulers, batch jobs |
| Permissions | Depends on user and client/token scopes | Service client permissions granted by AS |
| Common pitfalls | Omitting exchange, leaking tokens across users | Expecting `ReactiveSecurityContextHolder` to hold a user |
| Scaling | Token persistence per request/principal/session | Service storage suited to multi-node setups |

**Subtle truth:** `AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository` can delegate to the **exact same `ReactiveOAuth2AuthorizedClientService`**. Thus "web manager = always stored in session" is **oversimplified and often false**. The distinction lies in the repository API and request context, not necessarily separate physical storage.

### 9.1. Principal Name Is Part of the Token Key

The same `registrationId` with two different principals represents two separate authorized clients:

```text
(reports-user, alice)  -> Alice's authorized client
(reports-user, bob)    -> Bob's authorized client
(reports-batch, reports-scheduler) -> service authorized client
```

Never use `"system"` to represent all tenants if downstream authorization depends on tenant identity; design client registrations, scopes, and principal naming with isolation. For auditing, log the registration ID, an opaque principal identifier, and status, **never access tokens or refresh tokens**.

### 9.2. Unexpired Does Not Guarantee Downstream Authorization

An `OAuth2AuthorizedClient` can hold an unexpired access token while the Resource Server still returns 401 (revoked, wrong audience/issuer) or 403 (missing scope). The manager only handles the **client authorization/token** lifecycle; downstream servers still validate tokens independently. Never use `OAuth2AuthorizedClient.getAccessToken().getExpiresAt()` as proof that a user is allowed to read a resource.

## 10. A Java 17+ Project with Two Independent Managers

The following project **runs locally with Java 17+/Maven** to examine wiring, token persistence, and differences between managers. It **does not pretend to include a real Authorization Server**: `ClientRegistration` uses `.invalid` endpoints per reserved domain standards. The tests seed **valid `OAuth2AuthorizedClient` fixtures** into the store to verify manager selection **without calling a network token endpoint**. To test new grants, refresh, PKCE, and real downstream calls, replace the endpoints/credentials with a sandbox IdP and add corresponding integration tests.

### 10.1. Directory Layout

```text
reactive-oauth2-manager-choice/
├── pom.xml
└── src/
    ├── main/java/demo/manager/
    │   ├── Application.java
    │   ├── ManagerConfiguration.java
    │   ├── BrowserReportController.java
    │   └── BatchReportService.java
    └── test/java/demo/manager/
        └── ManagerSelectionTests.java
```

### 10.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-oauth2-manager-choice</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-client</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

The example uses Spring Boot **3.5.16** as a released baseline with Spring Security **6.5.x**. Older branches may reach end of OSS support in 2026, so new production systems must choose a supported branch and verify APIs against migration guides. Never pin `spring-security-oauth2-client` separately when Boot dependency management already manages it.

### 10.3. src/main/java/demo/manager/Application.java

```java
package demo.manager;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 10.4. src/main/java/demo/manager/ManagerConfiguration.java

```java
package demo.manager;

import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.InMemoryReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server.AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.reactive.function.client.WebClient;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class ManagerConfiguration {

    @Bean
    ReactiveClientRegistrationRepository registrations() {
        // Public placeholder values for the example only, not a real IdP.
        ClientRegistration browser = ClientRegistration
            .withRegistrationId("reports-user")
            .clientId("local-browser-client")
            .clientSecret("local-demo-secret")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .authorizationUri(
                "https://identity.example.invalid/oauth2/authorize")
            .tokenUri("https://identity.example.invalid/oauth2/token")
            .userInfoUri("https://identity.example.invalid/userinfo")
            .userNameAttributeName("sub")
            .scope("profile", "reports.read")
            .build();

        ClientRegistration batch = ClientRegistration
            .withRegistrationId("reports-batch")
            .clientId("local-service-client")
            .clientSecret("local-demo-secret")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.CLIENT_CREDENTIALS)
            .tokenUri("https://identity.example.invalid/oauth2/token")
            .scope("reports.read")
            .build();

        return new InMemoryReactiveClientRegistrationRepository(
            browser, batch);
    }

    @Bean
    ReactiveOAuth2AuthorizedClientService authorizedClientService(
            ReactiveClientRegistrationRepository registrations) {
        return new InMemoryReactiveOAuth2AuthorizedClientService(
            registrations);
    }

    @Bean
    ServerOAuth2AuthorizedClientRepository webAuthorizedClientRepository(
            ReactiveOAuth2AuthorizedClientService service) {
        return new AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository(
            service);
    }

    @Bean("webManager")
    ReactiveOAuth2AuthorizedClientManager webManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository repository) {

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        var manager = new DefaultReactiveOAuth2AuthorizedClientManager(
            registrations, repository);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Bean("jobManager")
    ReactiveOAuth2AuthorizedClientManager jobManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService service) {

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        var manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, service);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Bean("userWebClient")
    WebClient userWebClient(
            @Qualifier("webManager")
            ReactiveOAuth2AuthorizedClientManager manager) {
        var oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);
        // Do not enable default token for every host.
        return WebClient.builder().filter(oauth2).build();
    }

    @Bean("batchWebClient")
    WebClient batchWebClient(
            @Qualifier("jobManager")
            ReactiveOAuth2AuthorizedClientManager manager) {
        var oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);
        return WebClient.builder().filter(oauth2).build();
    }

    @Bean
    SecurityWebFilterChain webSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/public").permitAll()
                .pathMatchers("/web/**").authenticated()
                .anyExchange().denyAll())
            .oauth2Login(withDefaults())
            .oauth2Client(withDefaults())
            .build();
    }
}
```

**Configuration explanation:**

- `registrations()` creates **two client registrations with different grant types**, without creating any tokens yet.
- `authorizedClientService()` is an in-memory store for the demo; replace with a secure persistent service in production when HA/restart durability is required.
- `webAuthorizedClientRepository()` connects to the service for authenticated principals and falls back to session for anonymous users per the default implementation.
- `webManager` configures `authorizationCode().refreshToken()`, persists via the **Server repository**, and is used when a request has an exchange.
- `jobManager` configures `clientCredentials()`, persists via the **Reactive authorized client service**, and requires no exchange.
- Both `WebClient` beans are separated by name/qualifier. This keeps token sources distinct and eases auditing.
- Web security enables `oauth2Login` and `oauth2Client` to illustrate the user flow; endpoints outside `/public` require login. **Never** disable default CSRF casually to silence errors.
- The `example.invalid` domain is intentionally nonexistent, so **real OAuth2 authorization/token exchanges cannot execute**. The tests in section 11 use pre-seeded authorized clients with unexpired tokens so this host is never called.

**Security:** `local-demo-secret` is an example-only literal. Real applications read client secrets from a secrets manager or environment and enforce HTTPS. Never print secrets or tokens in HTTP responses or logs. If the IdP supports PKCE, state, nonce, or issuer metadata, use a complete login configuration matching the provider; never assume a registration without `openid` performs OIDC Login.

### 10.5. src/main/java/demo/manager/BrowserReportController.java

```java
package demo.manager;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.web.server.context.ServerSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.serverWebExchange;

@RestController
public class BrowserReportController {

    private final ReactiveOAuth2AuthorizedClientManager manager;
    private final WebClient webClient;

    public BrowserReportController(
            @Qualifier("webManager")
            ReactiveOAuth2AuthorizedClientManager manager,
            @Qualifier("userWebClient") WebClient webClient) {
        this.manager = manager;
        this.webClient = webClient;
    }

    @GetMapping("/public")
    public Mono<String> publicInfo() {
        return Mono.just("manager choice OK");
    }

    @GetMapping("/web/report")
    public Mono<String> report(ServerWebExchange exchange) {
        return exchange.getPrincipal()
            .cast(Authentication.class)
            .flatMap(principal -> {
                OAuth2AuthorizeRequest request =
                    OAuth2AuthorizeRequest
                        .withClientRegistrationId("reports-user")
                        .principal(principal)
                        .attribute(
                            ServerWebExchange.class.getName(), exchange)
                        .build();

                return manager.authorize(request)
                    .switchIfEmpty(Mono.error(
                        new IllegalStateException(
                            "User has not authorized this client")))
                    .flatMap(client -> webClient.get()
                        .uri("https://api.example.invalid/user/report")
                        .attributes(oauth2AuthorizedClient(client))
                        .attributes(serverWebExchange(exchange))
                        .retrieve()
                        .bodyToMono(String.class));
            });
    }
}
```

`/web/report` shows the **exact place where `ServerWebExchange` is needed**, rather than picking a random principal. If the browser user has not completed OAuth2 Login/authorization, the manager cannot obtain a valid token for the client. Because both IdP and downstream endpoints are nonexistent examples, **`GET /web/report` cannot succeed end-to-end with the sample config as-is**; the integration tests below exercise the manager directly against stored fixtures.

In a real system, the service must only access **trusted downstream URLs** and ensure access tokens are issued for the right API audience and scopes. The controller does not return tokens in its body; it returns only API data. Protecting a route with `.authenticated()` does not guarantee the user holds `reports.read`; the downstream Resource Server still validates permissions on the access token.

### 10.6. src/main/java/demo/manager/BatchReportService.java

```java
package demo.manager;

import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

@Service
public class BatchReportService {

    private final ReactiveOAuth2AuthorizedClientManager manager;
    private final WebClient webClient;

    public BatchReportService(
            @Qualifier("jobManager")
            ReactiveOAuth2AuthorizedClientManager manager,
            @Qualifier("batchWebClient") WebClient webClient) {
        this.manager = manager;
        this.webClient = webClient;
    }

    private Authentication systemPrincipal() {
        // Stable cache key for the authorized-client store only;
        // not a logged-in end user.
        return new UsernamePasswordAuthenticationToken(
            "reports-scheduler",
            "not-a-password",
            List.of(new SimpleGrantedAuthority("ROLE_SYSTEM")));
    }

    private OAuth2AuthorizeRequest request() {
        return OAuth2AuthorizeRequest
            .withClientRegistrationId("reports-batch")
            .principal(systemPrincipal())
            .build();
    }

    // Useful for wiring tests; never return the access token externally.
    public Mono<String> describeAuthorizedClient() {
        return manager.authorize(request())
            .switchIfEmpty(Mono.error(
                new IllegalStateException("No system authorized client")))
            .map(client -> "registration="
                + client.getClientRegistration().getRegistrationId()
                + ";principal=" + client.getPrincipalName());
    }

    // Let the scheduler/queue runner decide when to subscribe.
    public Mono<String> fetchReport() {
        return manager.authorize(request())
            .switchIfEmpty(Mono.error(
                new IllegalStateException("No system authorized client")))
            .flatMap(client -> webClient.get()
                .uri("https://api.example.invalid/system/report")
                .attributes(oauth2AuthorizedClient(client))
                .retrieve()
                .bodyToMono(String.class));
    }
}
```

**Read very carefully:** `systemPrincipal()` is a synthetic `Authentication` used solely so the manager has a consistent `principalName` for the service token. It **must never be placed in a user's `ReactiveSecurityContextHolder`** and **grants no authority at the Resource Server**. The Batch API's permissions depend strictly on the access token issued by the Authorization Server for `client_credentials`.

`fetchReport()` returns `Mono<String>` without calling `block()` or `subscribe()` in the business layer. A real scheduler must orchestrate subscription, metrics, timeouts, retries, and concurrency limits. Never use `@Scheduled` to fire hundreds of unmanaged subscriptions, as asynchronous token/HTTP calls can overload systems or cause duplicate runs.

**Note the distinction:** `java.util.List` here only constructs authorities for `Authentication`. If `client_credentials` requires per-tenant tokens, define separate principals/registrations per tenant and never allow HTTP users to override the service principal to obtain another tenant's token.

## 11. Practical Unit/Integration Tests for Manager Selection Without a Real IdP

The tests aim to **verify manager classes, storage keys, and re-authorization from valid tokens**. An access token fixture is **seeded** into the repository/service. Because the token is unexpired, the manager loads it **without making network calls to an IdP**. These tests do not cover grant exchange, refresh, JWT signatures, OIDC login, or downstream resource servers.

### 11.1. src/test/java/demo/manager/ManagerSelectionTests.java

```java
package demo.manager;

import java.time.Instant;
import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
class ManagerSelectionTests {

    @Autowired @Qualifier("webManager")
    ReactiveOAuth2AuthorizedClientManager webManager;

    @Autowired @Qualifier("jobManager")
    ReactiveOAuth2AuthorizedClientManager jobManager;

    @Autowired
    ReactiveClientRegistrationRepository registrations;

    @Autowired
    ReactiveOAuth2AuthorizedClientService service;

    @Autowired
    ServerOAuth2AuthorizedClientRepository webRepository;

    @Autowired
    BatchReportService batchReportService;

    @Autowired @Qualifier("userWebClient")
    WebClient userWebClient;

    @Autowired @Qualifier("batchWebClient")
    WebClient batchWebClient;

    private static Authentication user(String name) {
        return new TestingAuthenticationToken(
            name, "unused", "ROLE_USER");
    }

    private static OAuth2AuthorizedClient issued(
            ClientRegistration registration, String principalName) {
        Instant now = Instant.now();
        OAuth2AccessToken token = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "test-access-token-for-" + principalName,
            now.minusSeconds(60),
            now.plusSeconds(3600),
            Set.of("reports.read"));
        return new OAuth2AuthorizedClient(
            registration, principalName, token);
    }

    private static ServerWebExchange exchange() {
        return MockServerWebExchange.from(
            MockServerHttpRequest.get("/web/report").build());
    }

    @Test
    void requestManagerHasWebExchangeImplementation() {
        assertInstanceOf(
            DefaultReactiveOAuth2AuthorizedClientManager.class,
            webManager);
    }

    @Test
    void taskManagerHasServiceImplementation() {
        assertInstanceOf(
            AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager.class,
            jobManager);
    }

    @Test
    void registrationsHaveDifferentGrants() {
        Mono<String> names = Mono.zip(
                registrations.findByRegistrationId("reports-user"),
                registrations.findByRegistrationId("reports-batch"))
            .map(tuple -> tuple.getT1().getAuthorizationGrantType()
                .getValue() + "|" + tuple.getT2()
                    .getAuthorizationGrantType().getValue());

        StepVerifier.create(names)
            .expectNext("authorization_code|client_credentials")
            .verifyComplete();
    }

    @Test
    void webRepositoryStoresAnAuthorizedClientForAlice() {
        Authentication alice = user("alice");
        ServerWebExchange requestExchange = exchange();

        Mono<String> loaded =
            registrations.findByRegistrationId("reports-user")
                .flatMap(reg -> {
                    OAuth2AuthorizedClient seeded = issued(reg, "alice");
                    return webRepository.saveAuthorizedClient(
                            seeded, alice, requestExchange)
                        .then(webRepository.loadAuthorizedClient(
                            "reports-user", alice, requestExchange))
                        .map(client -> client.getPrincipalName());
                });

        StepVerifier.create(loaded)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void webManagerLoadsExistingUserClientWithExchange() {
        Authentication alice = user("alice");
        ServerWebExchange requestExchange = exchange();

        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("reports-user")
                .principal(alice)
                .attribute(
                    ServerWebExchange.class.getName(), requestExchange)
                .build();

        Mono<String> authorized =
            registrations.findByRegistrationId("reports-user")
                .flatMap(reg -> {
                    OAuth2AuthorizedClient seeded = issued(reg, "alice");
                    return webRepository.saveAuthorizedClient(
                            seeded, alice, requestExchange)
                        .then(webManager.authorize(request))
                        .map(client -> client.getPrincipalName());
                });

        StepVerifier.create(authorized)
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void jobManagerLoadsExistingClientWithoutExchange() {
        Authentication system = user("reports-scheduler");

        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("reports-batch")
                .principal(system)
                .build(); // NO ServerWebExchange.

        Mono<String> authorized =
            registrations.findByRegistrationId("reports-batch")
                .flatMap(reg -> {
                    OAuth2AuthorizedClient seeded =
                        issued(reg, "reports-scheduler");
                    return service.saveAuthorizedClient(seeded)
                        .then(jobManager.authorize(request))
                        .map(client -> client.getPrincipalName());
                });

        StepVerifier.create(authorized)
            .expectNext("reports-scheduler")
            .verifyComplete();
    }

    @Test
    void serviceStoreDoesNotLeakTokenToAnotherPrincipal() {
        Mono<String> result =
            registrations.findByRegistrationId("reports-batch")
                .flatMap(reg -> {
                    OAuth2AuthorizedClient seeded =
                        issued(reg, "tenant-a-worker");
                    return service.saveAuthorizedClient(seeded)
                        .then(service.loadAuthorizedClient(
                            "reports-batch", "tenant-b-worker"))
                        .map(client -> client.getPrincipalName());
                });

        StepVerifier.create(result)
            .verifyComplete(); // Mono.empty(): different principal.
    }

    @Test
    void batchServiceUsesStableServicePrincipalForCacheKey() {
        Mono<String> description =
            registrations.findByRegistrationId("reports-batch")
                .flatMap(reg ->
                    service.saveAuthorizedClient(
                        issued(reg, "reports-scheduler"))
                    .then(batchReportService.describeAuthorizedClient()));

        StepVerifier.create(description)
            .expectNext(
                "registration=reports-batch;principal=reports-scheduler")
            .verifyComplete();
    }

    @Test
    void bothWebClientsAreWiredExplicitly() {
        assertNotNull(userWebClient);
        assertNotNull(batchWebClient);
    }
}
```

The test suite contains **9 `@Test` methods**. It verifies:

1. The request manager is `DefaultReactiveOAuth2AuthorizedClientManager`.
2. The task manager is `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`.
3. The two registrations have different grant types.
4. The web repository saves and loads an authorized client for Alice.
5. The web manager loads Alice's client when a `ServerWebExchange` is present.
6. The service manager loads the scheduler's client **without needing an exchange**.
7. The principal-keyed store does not give tenant A worker's token to tenant B worker.
8. `BatchReportService` uses the expected stable principal name.
9. Both `WebClient` beans are injected explicitly by bean name.

**Testing limitations:** `test-access-token-for-...` is only an in-RAM fixture and **is never sent over the network**. `manager.authorize` in these tests receives an unexpired token, so it **does not prove** token endpoint, PKCE, or refresh configuration actually works. To test acquiring new tokens, test against an Authorization Server (mock HTTP/token endpoint) or sandbox IdP; never claim these tests verified JWT signatures.

### 11.2. A Test You Should Not Write

```java
// Anti-pattern: no exchange, yet forcing the web manager.
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("reports-user")
        .principal(user("reports-scheduler"))
        .build();
return webManager.authorize(request);
```

That call carries no `ServerWebExchange`, violating the usage contract of the web-context manager. Depending on the version/code path, it may fail to resolve the repository or throw a context error; do not rely on a specific exception without testing that exact version. **The fix is to switch managers, not to fabricate a fake web request for a scheduler token**.

## 12. Running Maven and Observing the Output

In the directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn clean test
```

With the configuration and fixtures above, **expect** 9 tests and Maven Surefire reporting `Tests run: 9, Failures: 0, Errors: 0`, `BUILD SUCCESS` when the dependency/test environment is compatible. This is an **expectation from the code**, not a claim that Maven was executed in the authoring environment.

Start the server:

```bash
mvn spring-boot:run
```

Try the public endpoint:

```bash
curl -i http://localhost:8080/public
```

Expected:

```http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

manager choice OK
```

`/web/report` is protected by OAuth2 login; you will not receive an actual report unless `identity.example.invalid` and `api.example.invalid` are replaced with a properly configured IdP and API sandbox. This is **intentional in the example**: compiling and wiring tests require no real secrets; running OAuth2 redirects, token exchanges, and downstream calls end-to-end is a separate integration step.

Never call `batchReportService.fetchReport().block()` in a controller or event loop; a real job runner needs dedicated orchestration to subscribe with timeouts, retries, backoff, error reporting, and cancellation. For a real cron job, configure scheduling per operational policy rather than using `@Scheduled` with unmanaged `.subscribe()`.

### 12.1. When Testing New Token Acquisition with a Sandbox IdP

Add a test server or mock Authorization Server simulating token endpoint responses (without going out to the real internet), covering:

- No authorized client yet => service manager calls `client_credentials`.
- AS returns `access_token`, `token_type=Bearer`, `expires_in` => saves client in the service.
- Second call while token valid => reuses it without calling the token endpoint again.
- Old token expired => re-authorizes, receives a different token, and updates the store.
- AS returns `invalid_client` or 5xx => propagates failure; bounded retries.
- Two different principals => separate storage keys, never cross-using tokens.
- Web manager with exchange + authorized user => refreshes per token/registration.
- Web manager missing exchange => fails cleanly and triggers redesign toward service manager.
- Downstream 401 `invalid_token` => applies appropriate failure handler without infinite loops.
- Downstream 403 `insufficient_scope` => fixes scopes/AS policy rather than deleting tokens indiscriminately.

This is a **recommended test suite**; no mock AS code is included in the project yet. Use WireMock or an embedded Reactor Netty server with a mock token endpoint, while ensuring proper TLS/issuer/config/trust policies before going to production.

## 13. Debugging Manager and Authorized Client Errors

| Symptom | Possible Cause | Troubleshooting |
| --- | --- | --- |
| `ServerWebExchange` null in scheduler | Using web manager outside request | Switch to service manager |
| Controller has exchange but manager loads no token | Wrong principal, registration ID, or store; not yet authorized | Log safe metadata, check OAuth2 Login/callback |
| Background job sees empty `ReactiveSecurityContextHolder` | No browser/user security context | Use stable service principal, `client_credentials` |
| `authorize()` returns `Mono.empty()` | Provider does not support grant or authorization cannot run | Check registration and provider builder |
| `invalid_client` | Wrong client ID/secret/auth method | Check client registration at AS; secrets manager |
| `invalid_grant` | Code/refresh token invalid, already used, or expired | Check state/PKCE/callback/refresh policy, remove stale client when appropriate |
| `401` from downstream | Token missing/expired/revoked/wrong audience/issuer | Inspect Bearer challenge and token validation, never log tokens |
| `403` from downstream | Valid token but missing scope/permission/tenant | Inspect authorities/claims, update policy/consent if needed |
| Job keeps requesting new tokens | Principal cache key changes, token deleted, or unshared store | Use stable principal, durable store, concurrency control |
| Another user's token is sent | Global/static cache or improper WebClient default token | Isolate principals, select authorized client explicitly |
| Scheduler hangs on `block()` | Blocking on wrong scheduler/event loop | Use reactive composition and proper orchestrator |
| Ambiguous manager bean injection | Missing `@Qualifier` | Use clear `webManager` and `jobManager` names |
| 403 causes filter to keep deleting token | Failure handler treats all 403s as invalid token | Inspect error code, check scopes |
| Token exists yet API still returns 401 | Token not intended for API audience | Verify `aud`, issuer, signature, token type |
| Job re-requests token after restart | In-memory store reset | Use persistent/shared store when needed |
| Multi-tenant tokens cross over | Principal/store keys not partitioned | Isolate by tenant/registration, add negative tests |
| Scheduled job with `client_credentials` has no `refresh_token` | Expected behavior for this grant | Reauthorize using client credentials |
| Web manager triggers redirect in background | Auth code requires a browser | Use an M2M grant or standard delegation protocol |

### 13.1. Ordered Investigation Checklist

1. Determine whether the code executes inside a **server web request** or an **out-of-request job**.
2. Inspect the injected manager class; if two beans exist, verify `@Qualifier`.
3. Confirm `ClientRegistration.authorizationGrantType` and the provider chain.
4. Identify the actual principal, registration ID, and where authorized clients are stored.
5. For the web manager, confirm the current exchange and user authentication belong to the right request.
6. For the service manager, confirm the system principal key is stable and tenant-partitioned.
7. Check whether the token is valid and whether a refresh token exists; never print tokens to logs.
8. Distinguish AS errors during `authorize` from downstream Resource Server 401/403 errors.
9. Across multiple nodes, check persistence/refresh concurrency, clock skew, retries, and throttling.
10. Add real/sandbox token endpoint integration tests once seeded tests pass.

## 14. Production Security Practices

**Never pass a user access token into a background job** after the user logs out or the request ends, unless the architecture uses an AS- and policy-approved delegation mechanism. Retaining a user's `OAuth2AuthorizedClient` longer requires clear authorization, consent, refresh, storage encryption, logout/revocation, and auditing.

**Never share a single `WebClient` with a default token across arbitrary URLs**. When the framework attaches Bearer tokens automatically, an attacker-controlled endpoint or uncontrolled redirect can receive the token. Separate `WebClient` beans per trusted downstream host, configure allowlists, and never log `Authorization` headers.

**Never take scopes from user input and trust them**. In client credentials, scopes are requested according to the registration/AS grant; the Resource Server still decides whether to permit access to the API resource. A high-privilege service account is dangerous if its token leaks, so grant least privilege, bound TTLs, rotate secrets, and use mTLS/`private_key_jwt` where appropriate.

**Never assume a refresh token for client credentials.** Most M2M flows use short-lived access tokens and request new ones as needed. In user code flows, refresh tokens (if issued) must be protected, stored centrally under strict controls, and `invalid_grant` must be handled properly.

**Never use an in-memory store in HA production** when authorizations/refresh tokens must survive restarts. `InMemoryReactiveOAuth2AuthorizedClientService` only fits demos, tests, or cases genuinely needing no persistence. For shared stores, design encryption at rest, access control, key separation, and TTLs.

**Never confuse a synthetic `Authentication` used as a cache key with a real user.** `new UsernamePasswordAuthenticationToken("reports-scheduler", ...)` in this lesson exists solely to supply a principal to the service manager. It authenticates no user and must never enter the web security context. The Resource Server validates the service token issued by the AS.

### 14.1. CSRF and Sessions Are a Separate Layer

OAuth2 Client web logins using cookies/sessions may still need CSRF protection and appropriate `SameSite`/`Secure`/`HttpOnly` flags. The manager only handles the OAuth2 token lifecycle; it does not replace CSRF, login session validation, CORS, or data-level authorization.

For pure Bearer-header APIs, the CSRF threat model differs; do not copy `.csrf(disable)` from an M2M service and disable CSRF across a website using form login. CORS also does not make a service manager work in the background—CORS is a browser policy and creates neither a `ServerWebExchange` nor a user principal.

## 15. Reasoning Exercises and Answers

**Q1.** If a scheduler uses `WebClient`, must it use `DefaultReactiveOAuth2AuthorizedClientManager`?  
**Answer:** No. Using `WebClient` does not imply a `ServerWebExchange` is present; prefer `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` for jobs.

**Q2.** If a `ClientRegistration` declares `client_credentials`, does it already have an access token?  
**Answer:** Not yet. A registration is only configuration; the manager/provider must authorize with the AS and save an `OAuth2AuthorizedClient`.

**Q3.** Inside a controller handling a logged-in user that needs a user-scoped access token, which manager do you choose?  
**Answer:** Typically `DefaultReactiveOAuth2AuthorizedClientManager`, a web repository, and the current principal/exchange.

**Q4.** Inside an HTTP request where the backend needs its own token to call an internal API, are you forced to use the web manager?  
**Answer:** No. You can intentionally use the service manager + `client_credentials` to keep it decoupled from the user session.

**Q5.** Why does a job still need a principal even though the grant has no user?  
**Answer:** The manager/store needs a `(registrationId, principalName)` key for the issued token. In a job, the principal is a stable system identity name.

**Q6.** What happens if a scheduler passes `UUID.randomUUID()` as the principal every run?  
**Answer:** Cache misses and token churn, creating many authorized client records; use a stable key matching the service/tenant.

**Q7.** How does `ReactiveOAuth2AuthorizedClientService` differ from `ReactiveClientRegistrationRepository`?  
**Answer:** The registration repository stores OAuth client configuration; the service stores authorized clients and issued tokens.

**Q8.** Does the web repository always store inside `WebSession`?  
**Answer:** No. `AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository` can delegate to the service for authenticated users and use the session for anonymous users.

**Q9.** Does `client_credentials` usually renew tokens via `refreshToken()`?  
**Answer:** Typically there is no refresh token; the `clientCredentials()` provider requests a new access token when needed.

**Q10.** When `authorize` returns `Mono.empty()`, should you call `block()` and return null?  
**Answer:** No. Use `switchIfEmpty` and handle unsupported/unavailable authorization cleanly inside the reactive chain.

**Q11.** If two beans implement `ReactiveOAuth2AuthorizedClientManager`, what is the risk of injecting without `@Qualifier`?  
**Answer:** Ambiguous bean resolution or injecting the wrong manager. Give clear bean names and inject explicitly.

**Q12.** Is calling `setDefaultOAuth2AuthorizedClient(true)` on a WebClient calling multiple hosts safe?  
**Answer:** Not recommended. Tokens could be attached to every HTTP request made by that `WebClient` and leaked to untrusted hosts.

**Q13.** If a token is unexpired yet downstream returns 403, does that mean the token endpoint is broken?  
**Answer:** No. 403 can mean missing scopes or object/tenant permissions; inspect downstream authorization separately.

**Q14.** Do tests seeding `OAuth2AuthorizedClient` with an unexpired token test the real client secret, PKCE, or AS?  
**Answer:** No. Those tests verify manager selection/storage and token reuse; validating the protocol requires testing grant exchanges against a mock/sandbox IdP.

**Q15.** A `@Scheduled` job needs to act on behalf of a logged-out user; should it grab the user's latest token from a static cache?  
**Answer:** No. That requires an AS-approved delegation/offline-access protocol along with proper consent, revocation, and storage policies.

## 16. Project Adoption Checklist

- [ ] Identify contexts with vs. without `ServerWebExchange`, separating user tokens from service tokens.
- [ ] Choose `DefaultReactiveOAuth2AuthorizedClientManager` + web repository for applicable web requests.
- [ ] Choose `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` + reactive service for background tasks.
- [ ] Configure `ClientRegistration` with exact grant type, scopes, AS endpoints, and client authentication.
- [ ] Configure provider builder with only the grants genuinely permitted.
- [ ] Use stable principals, partition by registration/tenant, and never cache tokens globally.
- [ ] Use `@Qualifier` whenever multiple manager or `WebClient` beans exist.
- [ ] Build `OAuth2AuthorizeRequest` with the proper principal, and include the exchange in web contexts when needed.
- [ ] Attach authorized client or `clientRegistrationId` to `WebClient` requests explicitly.
- [ ] Restrict downstream origins; never enable default tokens on a shared multi-host `WebClient`.
- [ ] Handle `Mono.empty()`, errors, and retries in a controlled manner.
- [ ] Never call `block()` or stray `subscribe()` in WebFlux services.
- [ ] Do not assume `client_credentials` services receive refresh tokens.
- [ ] Prevent access/refresh token secrets from leaking into JSON, logs, or metrics.
- [ ] Across multiple nodes, enforce an appropriate policy for token stores and refresh concurrency.
- [ ] Maintain tests for web exchange context, no-exchange service context, and principal isolation.
- [ ] Add integration tests for token endpoints, 401/403, and a sandbox AS before going to production.
- [ ] Design CSRF, sessions, CORS, and downstream resource authorization separately.

## 17. Conclusion and Official References

Remember this single sentence:

> **When a WebFlux request exists and the token belongs to the user/request -> use `DefaultReactiveOAuth2AuthorizedClientManager`. When there is no request (scheduler, job, queue) and the token belongs to the service -> use `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`.**

Both use `ReactiveOAuth2AuthorizedClientManager` and `WebClient`, yet differ in **context, repository/service storage, principal, and authorization grant**. Picking the wrong manager commonly manifests as missing `ServerWebExchange`, lost authorized clients, repeated re-authorizations, or misusing user tokens in system tasks. Designing this boundary properly keeps token management in Spring Security reactive controlled and testable.

**Verified official sources:**

- Spring Security 6.5 – OAuth2 Client core interfaces and managers: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html
- Spring Security 6.5 – Authorized Client/WebClient integration: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorized-clients.html
- Spring Security 6.5 – Reactive OAuth2 Client overview: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
- Spring Security 6.5 – `DefaultReactiveOAuth2AuthorizedClientManager` Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/DefaultReactiveOAuth2AuthorizedClientManager.html
- Spring Security 6.5 – `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager.html
- Spring Security 6.5 – `ServerOAuth2AuthorizedClientExchangeFilterFunction` Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html
- Spring Security – `AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/server/AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository.html
- IETF RFC 6749 – OAuth 2.0 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
- IETF RFC 6750 – OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- OWASP – OAuth 2.0 Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html
