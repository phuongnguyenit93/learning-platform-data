# Handling Rejected Tokens, Removing OAuth2AuthorizedClient, and Avoiding Retry Loops in Spring Security Reactive

## 1. Objectives

A **Spring WebFlux** application uses **OAuth2 Client** to call a resource server with `WebClient`. An access token once worked, but later the downstream API returns **HTTP 401** with Bearer error `invalid_token`, or the token endpoint rejects a refresh token with OAuth2 error `invalid_grant`. If the app keeps that `OAuth2AuthorizedClient` cached and reuses the same token, every subsequent request fails with 401. If someone adds `retryWhen(Retry.indefinitely())` or builds a refresh -> call API -> 401 -> refresh loop, the system can trigger a request storm against the Authorization Server and Resource Server.

This lesson examines three **distinct yet related** decisions:

1. **Error classification:** 401/403 from a resource server differs from `invalid_grant` from the token endpoint and differs from transient 5xx/timeout outages.
2. **Managing `OAuth2AuthorizedClient` state:** using the right `ReactiveOAuth2AuthorizedClientManager`, `ReactiveOAuth2AuthorizedClientService`, or `ServerOAuth2AuthorizedClientRepository`, and removing unusable token entries when appropriate.
3. **Bounding retries:** knowing when **not to retry**, when to reacquire a token on the **next request**, when at most one backoff retry makes sense for an idempotent GET, and when re-login or operator intervention is required.

You will study **Spring Security 7.1** reactive APIs, distinguish the two constructors of `ServerOAuth2AuthorizedClientExchangeFilterFunction`, use built-in failure handlers, walk through a Spring Boot 4.1.x / Java 17+ application illustrating evicted client tokens, and test retry-loop prevention.

> **Principle:** deleting `OAuth2AuthorizedClient` is **deleting client-side cached authorization/token state**, which does not mean the auth server has revoked the token everywhere; nor does it **grant new permissions to a user**. A 403 from missing scopes/roles requires fixing policy, not infinite refreshes.

## 2. Four Entities Never to Confuse

| Component | Function | What Not to Infer |
| --- | --- | --- |
| `ClientRegistration` | Configuration of client-id, grant type, token-uri, scopes, provider | Not an issued access token |
| `OAuth2AuthorizedClient` | Binds `ClientRegistration` with principal, access token, and optional refresh token | Not the user's authenticated `SecurityContext` |
| `ReactiveOAuth2AuthorizedClientManager` | Authorizes/re-authorizes and coordinates providers, persistence, success/failure handlers | Does not infinitely retry resource requests |
| `ReactiveOAuth2AuthorizedClientService` | Saves/loads/removes authorized clients at application/service layer | Calling remove does not revoke refresh tokens at the IdP |
| `ServerOAuth2AuthorizedClientRepository` | Saves/loads/removes authorized clients in `ServerWebExchange`/web request scope | Not interchangeable with the service without principal/exchange |
| `ReactiveOAuth2AuthorizedClientProvider` | Executes grants like `authorization_code`, `refresh_token`, `client_credentials` | Does not handle downstream HTTP statuses for `WebClient` |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Attaches Bearer tokens to `WebClient` requests and forwards certain failures to a handler | The two constructors do not share identical default behavior |
| `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` | Deletes authorized clients for configured **OAuth2 error codes** | Does not delete on every 403 merely because status is 403 |

**Distinguish the two directions:** tokens are issued by the **Authorization Server / token endpoint**, and tokens are presented to the **Resource Server / downstream API**. A failure during token refresh and a failure when presenting an access token to an API take different handling paths.

## 3. OAuth2 Client Error Flow in WebFlux

~~~text
         Reactor request / background job
                      |
                      v
          ReactiveOAuth2AuthorizedClientManager
                      |
           load OAuth2AuthorizedClient?
                      |
        +-------------+--------------+
        |                            |
        v                            v
     absent                    token present
        |                            |
 token endpoint                access token near
 gets access token             expiry? refresh token?
        |                            |
        |                 +----------+----------+
        |                 |                     |
        |            refresh succeeds     invalid_grant
        |                 |                     |
        |                 |             failure handler deletes
        |                 |             stale authorized client
        v                 v                     |
      WebClient attaches Bearer token          STOP
                      |
              Resource Server
                      |
          +-----------+-----------+
          |                       |
         2xx                 401 / 403
          |                       |
          v                       v
        result             classify response
                                  |
              +-------------------+-------------------+
              |                   |                   |
       invalid_token        insufficient_scope    other error
              |                   |                   |
       remove old token     no refresh loop       handle separately
       when handler is      report denied         bounded retry for
       properly configured  permissions           5xx if allowed
              |
           STOP current request
              |
   Next valid request may acquire a
   new token / reauthorize per grant
~~~

This diagram illustrates the **recommended decision flow**; not every version or constructor implements every branch automatically. Exact behavior depends on your manager/filter, OAuth2 error codes, and repository/service.

### 3.1. When an Unexpired Token Still Gets 401

An access token may have a future `expiresAt` in `OAuth2AuthorizedClient`, yet the resource server rejects it early because:

- The token was revoked or account/app permissions changed.
- The resource server uses a different issuer/audience or has not picked up a JWK rotation.
- The resource server rejects the issued token type or scopes.
- The token is validly signed yet not accepted by that specific API.
- Clocks, caches, clusters, or gateways are misconfigured.
- The token was altered or corrupted in transit.

**Do not look solely at `expiresAt` to conclude a token is valid.** The resource server validates the token at use time; a `401 Bearer invalid_token` indicates the stored token should not keep being sent.

### 3.2. HTTP Status Alone Is Only a Clue, Not the Full Error

Standard error example from a resource server:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Insufficient scope case:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.read"
~~~

These are **illustrative HTTP responses per RFC 6750**. A 401 can also come from an auth gateway missing headers; a 403 can come from business authorization policy despite a valid token. **Never delete every authorized client on any 401 or 403** hoping a new token will fix a role/scope mismatch.

### 3.3. Where Does invalid_grant Appear?

When a refresh token is expired, revoked, out of rotation, or replayed, the **token endpoint** can return:

~~~json
{
  "error": "invalid_grant"
}
~~~

`invalid_grant` is an **OAuth2 token endpoint error**, distinct from `invalid_token` in a Resource Server's `WWW-Authenticate` header. With default managers, a refresh `invalid_grant` error typically causes `ReactiveOAuth2AuthorizationFailureHandler` to remove the stored client. Yet removing the token does not guarantee automatic re-login: `authorization_code` requires user interaction/consent, while `client_credentials` can obtain a fresh token on the next request if credentials/config remain valid.

## 4. Choosing the Right Manager for the Context

Spring Security reactive provides two common managers:

| Context | Manager | Primary Storage |
| --- | --- | --- |
| WebFlux request with `ServerWebExchange` and logged-in user | `DefaultReactiveOAuth2AuthorizedClientManager` | `ServerOAuth2AuthorizedClientRepository` |
| Background job/scheduled task/service-to-service without web request | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientService` |

**Never** use `DefaultOAuth2AuthorizedClientManager` (Servlet/non-reactive) or `OAuth2AuthorizedClientService` (blocking) in a reactive WebFlux design. Distinguish packages and interfaces with `Reactive`.

### 4.1. DefaultReactiveOAuth2AuthorizedClientManager

Example configuring a web-request manager in Spring configuration:

~~~java
@Bean
ReactiveOAuth2AuthorizedClientManager webAuthorizedClientManager(
        ReactiveClientRegistrationRepository registrations,
        ServerOAuth2AuthorizedClientRepository repository) {

    ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                    .authorizationCode()
                    .refreshToken()
                    .clientCredentials()
                    .build();

    DefaultReactiveOAuth2AuthorizedClientManager manager =
            new DefaultReactiveOAuth2AuthorizedClientManager(
                    registrations, repository);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

This is a **bean method snippet**, requiring Spring Security imports and a real `ServerWebExchange` at runtime. Its Javadoc states that it saves the client by default on successful authorization and can delete the authorized client via its failure handler if refresh fails with `invalid_grant`.

### 4.2. AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager

For jobs/services:

~~~java
@Bean
ReactiveOAuth2AuthorizedClientManager serviceAuthorizedClientManager(
        ReactiveClientRegistrationRepository registrations,
        ReactiveOAuth2AuthorizedClientService clientService) {

    var provider = ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build();

    var manager = new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
            registrations, clientService);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

With `client_credentials`, the principal is a stable **service identity**, not a browser user. The hands-on section uses principal `"reports-backend"`, so client removal must use **that exact `registrationId` + `principalName`**.

**Important:** configuring only `.clientCredentials()` suits this demo; it does not enable the refresh token grant. A browser `authorization_code` app needs the right provider chain and account lifecycle; never copy a `client_credentials`-only provider and expect user logins to refresh automatically.

## 5. Default Manager Behavior When Refresh Fails

Per the Spring Security reactive OAuth2 Client reference:

- On successful authorize/re-authorize, the manager calls `ReactiveOAuth2AuthorizationSuccessHandler`, usually **saving the new authorized client**.
- On failed authorize/re-authorize, the manager calls `ReactiveOAuth2AuthorizationFailureHandler`.
- On `invalid_grant`, `DefaultReactiveOAuth2AuthorizedClientManager` and `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` can **remove the saved authorized client** by default via `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler`.

However:

1. This handles **errors from the authorization/token endpoint**, not automatically every HTTP 401 from downstream APIs.
2. The failure handler only deletes the **matching client registration/principal key**, not the global user session or every token at the IdP.
3. Which default error codes trigger deletion depends on the handler/version. `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` removes only when `OAuth2Error.getErrorCode()` belongs to its configured set.
4. Deleting the client does not automatically retry the failing request right away.
5. With rotated single-use refresh tokens, concurrent refreshes can hit races; see the concurrency section.

### 5.1. When No Refresh Token Exists

`RefreshTokenReactiveOAuth2AuthorizedClientProvider` returns an empty publisher when it cannot refresh under the grant/context (e.g., no refresh token or token not yet within the expiry window). The manager can return the existing authorized client if no refresh is needed. **Never** force refreshes in a loop when a token is missing or unusable.

### 5.2. When client_credentials Fails with invalid_client

`invalid_client` from the Authorization Server can mean a wrong/expired secret, disabled client, or policy change. Deleting the cached `OAuth2AuthorizedClient` and repeatedly re-requesting with the **same bad secret** only creates a request storm. Report the config/credential failure to observability, stop unbounded retries, and take operational action such as rotating the secret.

## 6. WebClient OAuth2 Filter: Two Constructors, Two Behaviors

`ServerOAuth2AuthorizedClientExchangeFilterFunction` is a key `WebClient` integration. It finds `OAuth2AuthorizedClient`, authorizes/refreshes if needed, and attaches the Bearer token to downstream HTTP requests.

### 6.1. Repository Constructor: Includes a Default Failure Handler

~~~java
ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
        new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                clientRegistrations, authorizedClientRepository);

WebClient webClient = WebClient.builder()
        .filter(oauth2)
        .build();
~~~

This snippet applies when you have `ReactiveClientRegistrationRepository` and `ServerOAuth2AuthorizedClientRepository`. Per Spring Security **7.1** Javadoc, the `(registrations, repository)` constructor **automatically configures** `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` to handle auth/authz errors propagated from the resource server that **carry an OAuth2 error code in its removal list**.

In a service call:

~~~java
webClient.get()
        .uri("https://resource.example.com/api/me")
        .attributes(
                ServerOAuth2AuthorizedClientExchangeFilterFunction
                        .clientRegistrationId("corp"))
        .retrieve()
        .bodyToMono(String.class);
~~~

In this snippet, `corp` is a configured client registration and the resource must be a **trusted URL/host**—never accept arbitrary user-supplied hosts that could leak Bearer tokens.

### 6.2. Manager Constructor: **Does Not Automatically Register a Resource-Server Failure Handler**

~~~java
ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
        new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);
~~~

Spring Security 7.1 Javadoc states clearly that with this constructor, HTTP **401/403 errors from the resource server** are not automatically forwarded to `ReactiveOAuth2AuthorizationFailureHandler`. Even though the manager itself has a handler for `invalid_grant` during refresh, that does **not** mean downstream HTTP 401s automatically evict the authorized client.

Attach an appropriate handler if you want the OAuth filter to evict rejected client tokens:

~~~java
RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler
        remover = new RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler(
                (registrationId, principal, attributes) ->
                        authorizedClientService.removeAuthorizedClient(
                                registrationId, principal.getName()));

oauth2.setAuthorizationFailureHandler(remover);
~~~

This snippet uses a **service-backed store**; `authorizedClientService` must be the exact `ReactiveOAuth2AuthorizedClientService` used by the manager, not a different store. The lambda signature matches Javadoc:

~~~java
Mono<Void> removeAuthorizedClient(
        String clientRegistrationId,
        Authentication principal,
        Map<String, Object> attributes);
~~~

`onAuthorizationFailure(...)` receives the `OAuth2AuthorizationException`, principal, and attributes. The handler inspects the **OAuth2 error code** and invokes the remover only if the code is in its configured set; not every 403 triggers removal.

**Boundary:** the handler on the filter reacts to **resource server 401/403 responses**, whereas the manager's failure handler reacts to **errors during authorize/re-authorize**. Both may be needed to keep stale tokens out of cache. If you replace the manager's success/failure handlers with custom implementations, preserve the required persistence/removal semantics so refresh does not silently break.

### 6.3. Warning on setDefaultOAuth2AuthorizedClient(true)

The filter offers `setDefaultOAuth2AuthorizedClient(true)`: it can resolve a default client from the current `Authentication` and attach the access token to requests. Javadoc advises caution because **many HTTP requests** may carry the token once a client is resolved. Never enable it on a shared `WebClient` accepting user-controlled URIs, as Bearer tokens could leak to unlisted hosts.

Prefer:

- Explicit `clientRegistrationId("known-registration")`.
- Fixed, allowlisted resource server base URLs.
- Separate authorization checks when proxying user OAuth2 tokens, never defaulting user tokens onto external APIs.
- Never logging `Authorization` headers, access/refresh tokens, or full error response bodies containing sensitive data.

## 7. Exact APIs for Removing OAuth2AuthorizedClient

### 7.1. In a Service/Background Context

`ReactiveOAuth2AuthorizedClientService` provides:

~~~java
Mono<Void> removeAuthorizedClient(
        String clientRegistrationId,
        String principalName);
~~~

Example:

~~~java
return authorizedClientService.removeAuthorizedClient(
        "downstream", "reports-backend");
~~~

This snippet sits **inside a method returning `Mono<Void>`**. **You must return or compose the publisher** so the removal actually executes; never invoke it and discard the `Mono`, and never call `.block()`.

The `registrationId + principalName` key must match the key used by the manager during save/load. Removing under the wrong principal may complete cleanly while leaving the stale client intact under another key.

### 7.2. In a ServerWebExchange/Repository Context

`ServerOAuth2AuthorizedClientRepository` uses:

~~~java
Mono<Void> removeAuthorizedClient(
        String clientRegistrationId,
        Authentication principal,
        ServerWebExchange exchange);
~~~

Invocation snippet:

~~~java
return authorizedClientRepository.removeAuthorizedClient(
        "corp", authentication, exchange);
~~~

Choose service vs. repository according to where clients are stored. Never wire two independent stores where the manager reads from A while the failure handler deletes from B: deletion will "succeed" yet the next request will still load the stale token.

### 7.3. Removing a Client Is Not Revoking Tokens at the IdP

Deleting the local record:

- Does not call the OAuth2 revocation endpoint by default.
- Does not guarantee the access token is invalidated at the resource server.
- Does not clear all `WebSession`/browser cookies.
- Does not delete the `ClientRegistration` or secret.
- Does not change scopes, user roles, or client policies at the IdP.

If **true revocation** is required, call the RFC 7009 revocation endpoint where supported and permitted by the provider, or apply dedicated token governance policies. **Never treat local removal as global logout.**

## 8. Classifying Errors and Deciding Whether to Retry

| Error Source | Example | Cleanup | Retry? |
| --- | --- | --- | --- |
| Token endpoint | `invalid_grant` on refresh token | Default manager can remove authorized client | **No** repeated refreshes with the stale token; need re-login or new grant |
| Token endpoint | `invalid_client` | Investigate client-id/secret | Do not retry infinitely with broken config |
| Resource server | 401 + Bearer `invalid_token` | Remove cached client via configured failure handler | **No** automatic replay of the failing request by default |
| Resource server | 401 without challenge or from gateway | Inspect auth scheme, proxy/headers | Do not delete or retry blindly |
| Resource server | 403 `insufficient_scope` | Keep token unless policy dictates otherwise | No refresh loop; fix scopes/consent/permissions |
| Resource server | 403 business authorization | Do not treat token as corrupt | Do not retry to "change roles" |
| Network timeout / 502/503/504 | Transient outage | Do not delete token just for gateway errors | At most **once** with backoff for idempotent GETs if budget permits |
| 429 | Rate limit | Do not delete token | Retry only per `Retry-After`, bounded with backpressure |
| 400 invalid payload | Input error | Do not delete token | Never retry automatically |
| Payment/write POST | Timeout where server may have committed | Do not delete token due to timeout | Never replay without idempotency key / transaction contract |

**Decision point:** `retryWhen` on a `WebClient` typically **resubscribes the entire pipeline**, which can re-invoke the manager, token endpoint, and API. If the failure is persistent, unbounded retries become a **token-issuance and request-flood loop**.

### 8.1. Why Is 403 Not "Token Expired"?

A valid access token carrying only `reports.read` will be denied on an API requiring `reports.admin`. Refreshing a token typically re-issues **already-permitted scopes**, never adding new roles. A refresh -> 403 loop repeats pointlessly, burns quota, and clutters logs.

### 8.2. Safe Retry Principles

1. By default, **do not retry 401/403**.
2. On `invalid_token`, remove the cached authorized client by error code; **let the next request** perform acquisition/reauthorization.
3. On `invalid_grant`, stop the current flow; prompt for re-login or issue a new grant when the contract allows.
4. Retry only **bounded** transient/network errors, using exponential backoff + jitter, deadlines, and a total retry budget.
5. Replay only idempotent operations or requests backed by idempotency keys / replay-safe contracts; GETs must have no side effects.
6. Never call `retryWhen(Retry.indefinitely())` on token-bearing requests.
7. Avoid stacked retries across WebClient + API gateway + circuit breaker without accounting for multiplicative attempts.
8. Add circuit breakers and rate limiting, especially when the IdP/token endpoint is degraded.
9. If retrying after cleanup, re-acquire on a fresh pipeline rather than reusing a stale client captured in a variable.
10. Emit metrics by error code, `registrationId`, and allowlisted upstream host—**never** log tokens.

### 8.3. "Retry At Most Once" Does Not Mean "Always Retry"

Suppose a downstream GET returns HTTP 503. After a short backoff, one retry may be safe if the timeout budget permits. Yet if a GET returns `401 invalid_token` or `403 insufficient_scope`, stop and address the root cause. If a POST without an idempotency key times out, it may have happened **after downstream already committed side effects**; retrying could create duplicate transactions.

## 9. Pure Java 17 Demo: Standalone Runnable Retry Policy

Before wiring real OAuth2, run a simple Java class proving the decision table **never retries authentication/authorization failures**.

Create `RetryPolicyDemo.java`:

~~~java
public final class RetryPolicyDemo {

    enum Decision {
        REMOVE_AND_STOP,
        STOP_PERMISSION_DENIED,
        RETRY_ONCE_WITH_BACKOFF,
        STOP
    }

    private RetryPolicyDemo() {
    }

    static Decision decide(int status, String oauthError,
            boolean idempotent, int previousRetries) {

        if (status == 401 && "invalid_token".equals(oauthError)) {
            return Decision.REMOVE_AND_STOP;
        }
        if (status == 403 &&
                "insufficient_scope".equals(oauthError)) {
            return Decision.STOP_PERMISSION_DENIED;
        }
        if ((status == 502 || status == 503 || status == 504)
                && idempotent && previousRetries == 0) {
            return Decision.RETRY_ONCE_WITH_BACKOFF;
        }
        return Decision.STOP;
    }

    public static void main(String[] args) {
        System.out.println("invalid_token=" +
                decide(401, "invalid_token", true, 0));
        System.out.println("scope=" +
                decide(403, "insufficient_scope", true, 0));
        System.out.println("transient_get=" +
                decide(503, null, true, 0));
        System.out.println("second_attempt=" +
                decide(503, null, true, 1));
        System.out.println("post_timeout=" +
                decide(503, null, false, 0));
        System.out.println("unknown_401=" +
                decide(401, null, true, 0));
    }
}
~~~

Run standalone with JDK 17+:

~~~bash
javac RetryPolicyDemo.java
java RetryPolicyDemo
~~~

**Deterministic stdout:**

~~~text
invalid_token=REMOVE_AND_STOP
scope=STOP_PERMISSION_DENIED
transient_get=RETRY_ONCE_WITH_BACKOFF
second_attempt=STOP
post_timeout=STOP
unknown_401=STOP
~~~

This is a **pure Java policy example**; it makes no IdP calls and touches no repository. It encodes a testable invariant: **retry counts do not repeat on persistent token failures**, and 401/403 are never treated as transient errors. Real applications also need deadlines, jitter, budgets, circuit breakers, and idempotency verification; this enum does not execute sleep or retry logic itself.

## 10. Spring Boot WebFlux App: Evicting Rejected Access Tokens Without Replay

To highlight the exact flow, the demo uses the **`client_credentials` grant** of a backend service named `reports-backend`. It **does not depend on browser login**, so it uses `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` with `ReactiveOAuth2AuthorizedClientService`.

When calling the downstream API:

1. The manager loads a cached `OAuth2AuthorizedClient` or fetches a new access token from the token endpoint.
2. `WebClient` sends the token to a **fixed HTTPS resource server**.
3. Downstream 2xx -> returns the body.
4. Downstream 401 with Bearer challenge `error="invalid_token"` -> **removes the exact stored authorized client**, emits an application error, and **does not retry immediately**.
5. Downstream 403 -> reports an authorization/upstream error **without automatically deleting the token**.
6. A **subsequent** HTTP request lets the manager acquire a new token; if the IdP or resource still rejects it, no in-request loop occurs.

**Demo scope:** requires a real Authorization Server issuing `client_credentials` and a resource server trusting that issuer/token; no hardcoded fake IdP secrets are assumed. `RetryPolicyDemo` runs offline; the WebFlux app runs end-to-end only when those two external services are configured.

### 10.1. pom.xml

Create Maven project `reactive-client-recovery`, group `com.example`, Java 17+. Spring Boot **4.1.2** provides the OAuth2 Client starter named `spring-boot-starter-security-oauth2-client` (in Boot 4 this name replaces the older OAuth2 Client starter).

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reactive-client-recovery</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <artifactId>spring-boot-starter-security-oauth2-client</artifactId>
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
~~~

Use the Boot BOM rather than overriding Spring Security core/client/web to mismatched versions. Never add Servlet `spring-boot-starter-web` to WebFlux just to write a REST controller.

### 10.2. application.properties

Create `src/main/resources/application.properties`:

~~~properties
server.port=8080

spring.security.oauth2.client.registration.downstream.provider=downstream
spring.security.oauth2.client.registration.downstream.client-id=${DEMO_CLIENT_ID}
spring.security.oauth2.client.registration.downstream.client-secret=${DEMO_CLIENT_SECRET}
spring.security.oauth2.client.registration.downstream.authorization-grant-type=client_credentials
spring.security.oauth2.client.registration.downstream.scope=reports.read
spring.security.oauth2.client.provider.downstream.token-uri=${DEMO_TOKEN_URI}

demo.resource-base-url=${DEMO_RESOURCE_BASE_URL}
~~~

When saved in the project, `${...}` expressions resolve via standard Spring environment-variable placeholders at runtime.

- `DEMO_TOKEN_URI`: HTTPS endpoint of the Authorization Server issuing `client_credentials`, such as a corporate IdP.
- `DEMO_RESOURCE_BASE_URL`: **HTTPS base URL of a resource server you control and trust**.
- `DEMO_CLIENT_ID` / `DEMO_CLIENT_SECRET`: credentials issued by the IdP for this service, kept out of Git.
- The resource server must serve `GET /reports/summary`, or update the URI in Java to match the real API.
- Client registration `downstream` and principal `reports-backend` form the fixed key used to load and remove the authorized client.

**No public or simulated token endpoint is supplied in this lesson.** Without a configured IdP and valid client credentials, the app boots, yet requests to `/demo/report` fail during authorization; that is expected rather than a bug in the retry policy.

### 10.3. Complete Java Source

Create `src/main/java/com/example/clientrecovery/ReactiveClientRecoveryApplication.java`:

~~~java
package com.example.clientrecovery;

import java.util.Locale;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveClientRecoveryApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ReactiveClientRecoveryApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        // Demo uses GET only; never use permitAll for private production APIs.
        return http.authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/demo/report").permitAll()
                    .anyExchange().denyAll())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService service) {

        var provider =
                ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build();

        var manager =
                new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                        registrations, service);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Bean
    WebClient resourceWebClient(
            WebClient.Builder builder,
            @Value("${demo.resource-base-url}") String baseUrl) {
        // baseUrl must be a fixed HTTPS endpoint whose trust has been verified.
        return builder.baseUrl(baseUrl).build();
    }

    @Service
    static class ResourceGateway {
        private static final String REGISTRATION_ID = "downstream";
        private static final String SERVICE_PRINCIPAL = "reports-backend";

        private final ReactiveOAuth2AuthorizedClientManager manager;
        private final ReactiveOAuth2AuthorizedClientService service;
        private final WebClient webClient;

        ResourceGateway(
                ReactiveOAuth2AuthorizedClientManager manager,
                ReactiveOAuth2AuthorizedClientService service,
                WebClient resourceWebClient) {
            this.manager = manager;
            this.service = service;
            this.webClient = resourceWebClient;
        }

        Mono<String> fetchOnce() {
            OAuth2AuthorizeRequest authorizeRequest =
                    OAuth2AuthorizeRequest
                            .withClientRegistrationId(REGISTRATION_ID)
                            .principal(SERVICE_PRINCIPAL)
                            .build();

            return manager.authorize(authorizeRequest)
                    .switchIfEmpty(Mono.error(
                            new IllegalStateException(
                                    "Client authorization unavailable")))
                    .flatMap(authorizedClient ->
                            webClient.get()
                                    .uri("/reports/summary")
                                    .headers(headers ->
                                            headers.setBearerAuth(
                                                    authorizedClient
                                                            .getAccessToken()
                                                            .getTokenValue()))
                                    .exchangeToMono(response -> {

                if (response.statusCode().is2xxSuccessful()) {
                    return response.bodyToMono(String.class);
                }

                if (response.statusCode().value() == 401) {
                    String challenge = response.headers()
                            .asHttpHeaders().getFirst(
                                    HttpHeaders.WWW_AUTHENTICATE);

                    Mono<Void> cleanup =
                            hasInvalidTokenChallenge(challenge)
                                    ? service.removeAuthorizedClient(
                                            REGISTRATION_ID,
                                            SERVICE_PRINCIPAL)
                                    : Mono.empty();

                    return response.releaseBody()
                            .then(cleanup)
                            .then(Mono.error(new ResponseStatusException(
                                    HttpStatus.BAD_GATEWAY,
                                    "upstream_authentication_rejected")));
                }

                if (response.statusCode().value() == 403) {
                    // Missing scopes/roles cannot be fixed by a refresh loop.
                    return response.releaseBody()
                            .then(Mono.error(new ResponseStatusException(
                                    HttpStatus.BAD_GATEWAY,
                                    "upstream_authorization_denied")));
                }

                return response.releaseBody()
                        .then(Mono.error(new ResponseStatusException(
                                HttpStatus.BAD_GATEWAY,
                                "upstream_unavailable")));
            }));
        }

        // Minimal parser for demonstrating common RFC 6750 challenges only.
        // Production should use Spring Security's filter/handler for error parsing.
        private static boolean hasInvalidTokenChallenge(
                String challenge) {
            if (challenge == null) {
                return false;
            }
            String value = challenge.trim().toLowerCase(Locale.ROOT);
            return value.startsWith("bearer ")
                    && value.contains("error=\"invalid_token\"");
        }
    }

    @RestController
    static class DemoController {
        private final ResourceGateway gateway;

        DemoController(ResourceGateway gateway) {
            this.gateway = gateway;
        }

        @GetMapping(value = "/demo/report",
                produces = MediaType.TEXT_PLAIN_VALUE)
        Mono<String> report() {
            return gateway.fetchOnce();
        }
    }
}
~~~

**Behavior analysis:**

- `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` supports `client_credentials` without requiring a current browser user.
- Principal `reports-backend` is a stable constant. The manager saves the client under key `downstream/reports-backend`.
- `manager.authorize(...)` retrieves the stored client or requests a new token when needed; `switchIfEmpty` fails when no provider supports or authorizes it.
- The resource URL is fixed under `demo.resource-base-url`, never assembled from untrusted queries/headers.
- On downstream 2xx, returns the text body.
- On 401, the demo **evicts the client only** when `WWW-Authenticate` contains Bearer `error="invalid_token"` in a common syntax. A 401 without that specific error still fails, **without deleting blindly**.
- `response.releaseBody()` frees the response body before completing the error branch.
- `service.removeAuthorizedClient(...)` is a `Mono<Void>` composed via `then(...)`; thus removal is subscribed **before** emitting the current error.
- Downstream HTTP 403 does not delete the token, since it may indicate missing permissions/scopes.
- The demo maps upstream 401/403 to **502 Bad Gateway** on the facade because the `client_credentials` token belongs to the backend service, **not the HTTP caller's credentials**. Other products may choose different status mappings per contract.
- There is no `retryWhen`, recursion, or `repeat()`; a single `GET /demo/report` makes **exactly one downstream resource call** after acquire/re-authorize.
- Never log raw tokens or full `WWW-Authenticate` headers; the challenge is inspected solely in-process to classify the error.
- `hasInvalidTokenChallenge` is a **minimal parser for learning**, not handling every RFC 6750 syntax variant (unquoted values, multiple challenges, escaping, casing). Production systems should prefer `ServerOAuth2AuthorizedClientExchangeFilterFunction` paired with `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` per framework contracts, or use a thoroughly tested parser.

### 10.4. Why Should a Parser Not Delete Clients on Every HTTP 401?

A reverse proxy may return 401 because the proxy itself expects another auth scheme, or an API route changed. Deleting clients unconditionally turns every request into a token-endpoint call followed by another 401, causing a rate-limit storm. The demo parser cleans up only on a Bearer `invalid_token` signal. Even when cleanup runs, **it is not a license to automatically replay**.

### 10.5. Why Does the Demo Code Not Use the WebClient OAuth2 Filter?

To make the sequence explicit: authorize -> request -> classify -> remove -> stop. In real applications, `ServerOAuth2AuthorizedClientExchangeFilterFunction` is usually more convenient. When using the manager constructor, **you must configure a failure handler** to process resource 401/403 responses, as shown in section 6. The demo invokes the manager directly and inspects statuses explicitly so it does not rely on filter forwarding behavior.

### 10.6. Storage in Demo vs. Production

Spring Boot OAuth2 client auto-configuration normally provides `ReactiveOAuth2AuthorizedClientService`, defaulting to in-memory when no custom store exists. In-memory state **is not shared across replicas** and is lost on restart. For multi-node deployments or durable token management, consider `R2dbcReactiveOAuth2AuthorizedClientService` or a secured distributed store with encryption at rest and concurrency control. Never let multiple pods run uncoordinated refresh token rotations simultaneously.

## 11. Running and Testing the Application

### 11.1. Startup

With a provisioned IdP and resource server, set environment variables:

~~~bash
export DEMO_CLIENT_ID='reports-service'
export DEMO_CLIENT_SECRET='secret-from-your-idp'
export DEMO_TOKEN_URI='https://idp.example.com/oauth2/token'
export DEMO_RESOURCE_BASE_URL='https://resource.example.com'

./mvnw clean package
./mvnw spring-boot:run
~~~

Those hosts/secrets are **illustrative placeholders**; replace them with real URLs and credentials from your IdP. On Windows PowerShell, set `$env:DEMO_CLIENT_ID="..."` and likewise for the other variables, then run `.\mvnw.cmd spring-boot:run`.

`client_credentials` needs no browser login, yet requires an Authorization Server accepting the grant, a matching `reports.read` scope, and a live `GET /reports/summary` resource server. Without those services, only `RetryPolicyDemo` runs offline; never claim OAuth integration tests are complete without running them against live or properly mocked services.

### 11.2. Calling the Facade

~~~bash
curl -i http://localhost:8080/demo/report
~~~

When the token is valid and downstream returns 200, the facade returns **200** with the resource body. If downstream returns 401 with Bearer `invalid_token`, the facade returns **502** via `ResponseStatusException` after deleting the matching authorized client. The current request **stops**, without replaying to the resource server.

A **new** request:

~~~bash
curl -i http://localhost:8080/demo/report
~~~

can trigger fetching a fresh token from the IdP because the stale record was removed. If the IdP still denies or the resource still returns 401, the facade fails cleanly per policy **without looping infinitely inside one request**.

### 11.3. Assertions Needed in Integration Tests

| Case | Mock Token Endpoint / Downstream | Expected |
| --- | --- | --- |
| No authorized client yet | Token endpoint 200, API 200 | 1 acquire, 1 resource call |
| Valid cached client exists | API 200 | Reuses stored client without unnecessary token calls |
| API returns 401 `invalid_token` | Valid Bearer challenge | Removes `downstream/reports-backend` once; facade 502; **no replay** |
| API returns 401 without Bearer error | Generic 401 | Not deleted per demo, facade 502 |
| API returns 403 `insufficient_scope` | Bearer 403 | Not removed; facade 502; no refresh loop |
| Token endpoint returns `invalid_client` | Invalid client credentials | No retry storm; operational error reported |
| Another refresh-token flow returns `invalid_grant` | Refresh failed | Manager failure handler deletes stale client |
| API returns 503 | Downstream outage | Does not delete token; demo returns 502, no retry |
| 10 concurrent 401 requests | Same cached token | Each request bounded; concurrency handled in production |
| Service A `client_credentials` | Principal differs from Service B | Never deletes another service's key |
| Side-effecting POST API | Timeout | Never replays without an idempotency contract |
| Bearer token sent toward untrusted host | SSRF/redirect test | Bearer header never leaks |

### 11.4. Testing the API with WebTestClient

In WebFlux, `WebTestClient` can test the facade using a fake `ReactiveOAuth2AuthorizedClientManager`, fake `ReactiveOAuth2AuthorizedClientService`, and mocked `ExchangeFunction`/resource server:

~~~java
// Test snippet, not a standalone JUnit class:
webTestClient.get()
        .uri("/demo/report")
        .exchange()
        .expectStatus().isBadGateway();
~~~

To verify **side-effect behavior**, asserting 502 alone is not enough. The fake service/repository must record `removeAuthorizedClient("downstream","reports-backend")`; the mock downstream must record **exactly one request**. With 10 concurrent calls, assertions must distinguish "once per call" from "once system-wide".

Use `StepVerifier` to confirm the removal publisher completes, and use a mock resource server emitting standard `WWW-Authenticate` headers. Tests need no real tokens or secrets; test data must never be logged in production.

## 12. Configuring Bounded Retries for Transient Errors

If an idempotent GET request should retry **at most once** on `503 Service Unavailable`, place the Reactor policy at the **adapter layer that knows idempotency**:

~~~java
// Illustrative snippet on Mono<String> calling an idempotent GET only.
// UpstreamTemporarilyUnavailableException is emitted by your adapter for 503.
return fetchIdempotentGet()
        .retryWhen(Retry.backoff(1, Duration.ofMillis(200))
                .filter(ex -> ex instanceof UpstreamTemporarilyUnavailableException));
~~~

This is a **snippet**, not a standalone runnable file; `fetchIdempotentGet()` and the exception must be defined per your API. Critical rules:

- `Retry.backoff(1, ...)` permits **at most one retry**, meaning at most two total attempts (if the first fails).
- `UpstreamTemporarilyUnavailableException` must only be emitted for classified transient errors; **never** emit it for HTTP 401/403.
- Per Reactor semantics, resubscribing may re-run the entire pipeline, including authorization and downstream calls. Ensure the GET is idempotent and respects timeouts and retry budgets.
- Avoid placing `retryWhen` at the adapter, controller, and gateway simultaneously without calculating multiplicative retries.
- For POST/PUT/DELETE, require server-accepted idempotency keys or transaction/deduplication before allowing retries.

### 12.1. Loops to Avoid

~~~java
// Anti-pattern: can flood the token endpoint and resource server.
return callResourceWithOAuth()
        .retryWhen(Retry.indefinitely());
~~~

If the resource keeps returning 401, the exception repeats forever. Even `Retry.fixedDelay(100, ...)` with 100 attempts is far too many for authentication errors that will not self-heal. Retries help only when the **cause is transient and the operation is safe to replay**.

### 12.2. Retry-After on 429

When downstream returns `429 Too Many Requests`, consider `Retry-After`, global rate limiters, queues/backpressure, and circuit breakers. Parse `Retry-After` with strict upper bounds, never trusting absurd or malformed values, and avoid thousands of clients retrying in lockstep. **429 is never a reason to delete `OAuth2AuthorizedClient`**.

## 13. Concurrency: Refresh Token Rotation and Stale Invalidation

### 13.1. Two Requests Refreshing the Same Token

~~~text
Request A                      Request B                   Authorization Server
   |                              |                                |
load client X                  load client X                       |
   |                              |                                |
refresh R0 ---------------------> |                                |
   |                          refresh R0 ------------------------->|
   |                              |                                |
receive access A1, R1          invalid_grant (R0 reused)           |
   |                              |                                |
save new client X               remove client X                    |
   |                              |                                |
result: last-write / deletion race -> new client may be lost
~~~

This depicts a **possible race scenario**, without claiming every IdP rotates tokens or lets one request win first. In practice, many IdPs rotate refresh tokens; one request redeems R0 and gets R1, while the other reuses R0 and gets `invalid_grant`. If the failure handler deletes the record after the first request already persisted R1, the newly refreshed client can be wiped out.

### 13.2. Reducing Races

- Keyed by `clientRegistrationId + principalName`, use **single-flight refresh** / appropriate locking.
- Across multiple nodes, locks must be distributed or the store must support conditional updates; local JVM locks do not protect a cluster.
- Use compare-and-swap / version checks so a stale failure from an older request cannot delete a newer token.
- When needed, track a **one-way** access token ID/hash (logging only a non-sensitive fingerprint) to identify which token was rejected.
- Coordinate saving new tokens and removing old ones so concurrent refreshes do not interleave destructively.
- Never retry `invalid_grant` repeatedly—once R0 is rotated or revoked, retrying R0 is futile.
- Monitor duplicate refresh attempts, oauth2 refresh failures, token rotations, and cleanup errors.

**Demo code note:** `ReactiveOAuth2AuthorizedClientService.removeAuthorizedClient(registrationId, principalName)` is typically a key-based deletion, **not a conditional compare-and-delete**. In a production cluster, preventing accidental deletion of a newer token requires an appropriately versioned repository design; do not assume the default remove API solves races.

### 13.3. Retrying Requests After Cleanup and Idempotency

Even when cleanup lets the next request acquire a new token, that does not mean the prior operation **never executed** downstream. On network timeouts or gateway retries, downstream may have committed changes while the response was lost. Never replay a payment/order POST just because the client saw 401 or a timeout; rely on idempotency contracts and downstream request IDs.

## 14. Observability, Security, and Alerting

### 14.1. Useful Metrics

Tag using **bounded-cardinality labels**:

| Metric | Example Reason |
| --- | --- |
| `oauth2.client.authorize.success` | Authorized client / access token acquired successfully |
| `oauth2.client.authorize.failure` | `invalid_grant`, `invalid_client`, timeout |
| `oauth2.client.removal` | Cleanup on `invalid_token`/`invalid_grant` |
| `oauth2.resource.401` | Downstream rejected authentication |
| `oauth2.resource.403` | Insufficient scope or permission denied |
| `oauth2.refresh.concurrent` | Concurrent refreshes for the same client/principal |
| `oauth2.retry.attempts` | Total attempts per request |
| `oauth2.credential.rotation` | Token/client-secret lifecycle failures |

These are **suggested metric names**, not Micrometer meters automatically provided by Spring Security under those exact names. Never put raw access tokens, refresh tokens, emails/subject IDs, or arbitrary request URLs into metric tags, avoiding cardinality explosions and PII exposure.

### 14.2. What Never to Log

- `Authorization: Bearer ...` headers.
- Access tokens, refresh tokens, or client secrets.
- Raw `WWW-Authenticate` headers if they may contain unvalidated sensitive data.
- Full IdP OAuth2 error responses without inspecting content first.
- JWT claims holding PII or internal secrets.

Log allowlisted `registrationId`, configured upstream ID, error category, HTTP status, correlation ID, and outcome (**removed / not removed / retry suppressed**). If you must identify which token failed, use a keyed one-way/truncated fingerprint instead of logging raw tokens.

### 14.3. Early Warnings

- Spike in `invalid_client` -> client secret expired or misconfigured.
- Spike in `invalid_grant` -> refresh token rotation race, revoked tokens, or changed IdP policy.
- Repeated `invalid_token` right after acquisition -> issuer/audience/JWK/scope mismatch; never let a request loop mask misconfiguration.
- Rising 403s while tokens remain valid -> permissions/resource scopes; stop refreshing.
- Token endpoint 429/503 -> enforce backpressure and circuit breaking.
- Surge in acquisitions per principal -> authorized-client store not persisting or overly broad cleanup.

## 15. Common Implementation Pitfalls

### 15.1. "The manager has a failure handler, so WebClient 401s auto-delete"

Not necessarily. With `ServerOAuth2AuthorizedClientExchangeFilterFunction(manager)`, Javadoc specifies resource 401/403 errors are not forwarded automatically. Configure `setAuthorizationFailureHandler(...)` on the filter or perform explicit classification/cleanup as in the demo.

### 15.2. "On any 403, delete the client and fetch a new token"

Wrong. A 403 can be `insufficient_scope` or business authorization. Refreshing tokens does not mint new permissions and only creates a loop.

### 15.3. "Calling removeAuthorizedClient(...) alone means the response works"

Methods returning `Mono<Void>` are lazy publishers. Without `return`/`then`/`flatMap`, the removal **may never execute**.

### 15.4. "Removing by user without the right registration"

Keys are `registrationId + principalName`; with WebFlux repositories, `Authentication` and `ServerWebExchange` must also match. Deleting under the wrong key leaves the stale token untouched.

### 15.5. "Local deletion means system-wide token revocation"

No. Local removal only clears client state; the access token may remain valid at the resource server until expiration or separate revocation.

### 15.6. "retryWhen handles security errors automatically"

No. `Retry.indefinitely()` does not distinguish 401/403/503 and resubscribes the entire reactive chain. Write explicit policies with exception filters and retry budgets.

### 15.7. "When client_credentials fails, force user browser login"

The `client_credentials` grant belongs to a service identity. Downstream 401s indicate a service config/token issue; never translate it into a frontend user 401. Classify upstream failures and monitor operations.

### 15.8. "On refresh invalid_grant, retry R0 multiple times"

No. R0 may already be revoked or rotated; retrying the same token only increases errors. Discard the stale client and require re-login or a valid new grant.

### 15.9. "Every 401 means invalid_token"

No. Reverse proxies, Basic auth, missing tokens, wrong issuers, wrong audiences, or missing challenges can also produce 401. Inspect `WWW-Authenticate`, client registrations, policies, and the 401 origin.

### 15.10. "Using non-reactive OAuth2AuthorizedClientService on Netty event loop"

Never use blocking services or arbitrary `.block()` calls; Spring WebFlux requires reactive managers, services, and repositories to avoid blocking event loops.

### 15.11. "In-memory token stores across multiple instances are fine"

In-memory stores are isolated per node; refresh rotation and token invalidation become inconsistent, requiring shared state coordination or a shared store under load.

### 15.12. "Attaching a filter that adds tokens to every URL including user-supplied ones"

A global `WebClient` with `setDefaultOAuth2AuthorizedClient(true)` and user-supplied URIs can leak Bearer tokens. Enforce fixed trusted base URLs and explicit client registrations.

### 15.13. "Seeing facade 502 means downstream did nothing"

Facade HTTP status mapping never proves absence of side effects; on timeouts or network errors, downstream may have committed. Retrying state-changing requests requires idempotency.

### 15.14. "No errors in logs means cleanup worked"

Assert the authorized-client store is cleared and the next request stops using the stale token. Track removal-outcome metrics, test connectors, and verify exact principal/registration keys.

## 16. Production Checklist

1. Distinguish token-endpoint `invalid_grant` from resource `invalid_token` and `insufficient_scope`.
2. Know whether the client uses `DefaultReactiveOAuth2AuthorizedClientManager` or `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`.
3. Know whether authorized clients live in a repository or service, and the exact keys used by the manager.
4. For the WebClient OAuth filter, inspect its **constructor** and `ReactiveOAuth2AuthorizationFailureHandler` configuration.
5. Evict only when OAuth2 error codes/policies indicate a stale token; never delete on every 403.
6. Never replay the current request by default when a token is rejected.
7. Have an appropriate re-login or new-grant strategy for `authorization_code` vs. `client_credentials`.
8. Bound transient retries with limits, backoff, jitter, deadlines, and circuit breakers; never retry auth errors.
9. Require idempotency keys and downstream contracts before allowing POST/PUT/DELETE replays.
10. Never send Bearer tokens to user-supplied URLs or unallowlisted hosts.
11. Never log tokens/secrets/raw claims; emit metrics by registration and error code.
12. Test stale tokens, missing challenges, `invalid_grant`, `invalid_client`, `insufficient_scope`, timeouts, 429/503, and 2xx.
13. Test concurrency during refresh token rotation, stale cleanup, multi-node deployments, and shared stores.
14. When removing clients, compose `Mono<Void>`—never discard the publisher or block.
15. Never confuse local removal with OAuth2 token revocation or global logout.
16. Verify Spring Security versions; never copy Servlet failure handlers into WebFlux.
17. Maintain runbooks for rotating client secrets, updating permissions, and resolving issuer/audience/JWK mismatches.
18. Cap requests/token acquisitions per principal to prevent retry storms during IdP outages.

## 17. Self-Assessment

**Q1.** Why must `invalid_grant` and `invalid_token` be handled separately?

**Answer:** `invalid_grant` typically comes from the token endpoint when a refresh token fails; `invalid_token` typically comes from a resource server Bearer challenge rejecting an access token. They happen at different stages and involve different failure handlers.

**Q2.** Using only `ServerOAuth2AuthorizedClientExchangeFilterFunction(manager)`, do downstream 401s automatically evict the client?

**Answer:** Not by default. Per 7.1 Javadoc, you must set an authorization failure handler or handle cleanup manually; the repository constructor auto-configures the remover.

**Q3.** Does `removeAuthorizedClient("downstream","reports-backend")` revoke the access token at the IdP?

**Answer:** No. It deletes the cached client by key. Server-side revocation is a separate mechanism.

**Q4.** On `403 insufficient_scope`, should you keep refreshing until you get 200?

**Answer:** No. The issue is missing scopes/permissions; refreshing generally grants no new permissions and creates a loop.

**Q5.** Why must you return/compose the `Mono<Void>` from remove?

**Answer:** Reactive operations are lazy; calling without subscribing through the pipeline means cleanup may never run.

**Q6.** When should you retry at most once?

**Answer:** On transient errors (e.g., 503) for idempotent/replay-safe operations, with backoff and a retry budget. Never for 401/403.

**Q7.** Why does multi-node refresh token rotation suffer from races?

**Answer:** Two workers can use the same old refresh token; one receives a new token while the other receives `invalid_grant` and deletes the newly saved record. Single-flight or conditional updates are required.

**Q8.** Why might a new request still get 401 right after cleanup?

**Answer:** Acquiring a fresh token does not fix issuer, audience, scope, JWK, or provider/resource misconfiguration. Diagnose the root cause instead of retrying endlessly.

**Q9.** With `client_credentials`, should you delete the client under the browser user's principal?

**Answer:** No. Use the stable service identity that the manager used to authorize and save, such as `reports-backend`.

**Q10.** If a POST times out after downstream committed, should it be auto-replayed?

**Answer:** Not without an idempotency contract. A timeout does not prove the operation was not executed.

## 18. Official Documentation

- [Spring Security — Reactive OAuth2 Client: Core Interfaces / Classes](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html)
- [Spring Security — OAuth2 Client in WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html)
- [Javadoc — ServerOAuth2AuthorizedClientExchangeFilterFunction](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html)
- [Javadoc — DefaultReactiveOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultReactiveOAuth2AuthorizedClientManager.html)
- [Javadoc — AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager.html)
- [Javadoc — RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler.html)
- [Javadoc — OAuth2AuthorizedClientRemover](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler.OAuth2AuthorizedClientRemover.html)
- [Javadoc — ReactiveOAuth2AuthorizedClientService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/ReactiveOAuth2AuthorizedClientService.html)
- [Javadoc — ServerOAuth2AuthorizedClientRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/server/ServerOAuth2AuthorizedClientRepository.html)
- [Javadoc — RefreshTokenReactiveOAuth2AuthorizedClientProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/RefreshTokenReactiveOAuth2AuthorizedClientProvider.html)
- [Spring Boot — OAuth2 Client configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html)
- [RFC 6750 — OAuth2 Bearer Token Usage, invalid_token / insufficient_scope](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 6749 — OAuth2 Authorization Framework, invalid_grant](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7009 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [Project Reactor — RetrySpec and RetryBackoffSpec](https://projectreactor.io/docs/core/release/api/reactor/util/retry/Retry.html)
