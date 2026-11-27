# Authentication Context When Switching to Another Task or Asynchronous Chain

In a Spring Security Resource Server application, HTTP requests are typically authenticated in the security filter chain. Once an access token is valid, Spring Security creates an **`Authentication`** and places it in **`SecurityContext`** for controllers, services, and authorization rules to use. However, when execution moves to another thread, executor, asynchronous callback, Reactor pipeline, or background job, this context may no longer be available.

This is a key point in the **Token Relay** chapter: **propagating `SecurityContext`**, **relaying an access token**, and **delegating to call another service** are three related but distinct concerns. Copying the authentication context to another thread does not automatically make an access token suitable for a downstream API. Conversely, putting raw tokens into a task or message queue is not a safe way to preserve identity.

This lesson explains how Spring Security stores and propagates context in Servlet and WebFlux, how to configure executors for `@Async`/`CompletableFuture`, how to use `WebClient` to relay Bearer tokens, the limits of Reactor Context, and how to handle background work that outlives the request. The focus is on preserving the right identity and permissions across each execution boundary while avoiding credential leakage or misusing tokens.

> **Illustrative context:** The Orders API runs Spring Boot 3.x / Spring Security 6.x. The API receives access tokens from callers, checks scopes, and may call the Inventory API or Billing API. Some operations run via `@Async`, `CompletableFuture`, WebFlux `Mono`/`Flux`, or a message queue. Code examples are architectural patterns; select the right Servlet/WebFlux stack and verify APIs against your project version.

## 1. Four Concepts to Distinguish

### 1.1. Authentication

`Authentication` represents the result of authentication or a pending authentication request. In a Resource Server, common examples include:

- `JwtAuthenticationToken` when the access token is a JWT.
- `BearerTokenAuthentication` when an opaque access token is verified via introspection.

An authenticated `Authentication` may contain the principal, authorities, and related token information. It is not a harmless object: depending on the `Authentication` type, credentials or token objects may hold sensitive bearer credentials.

### 1.2. SecurityContext

`SecurityContext` holds the current `Authentication`. Application code typically reads the context via:

- Servlet: `SecurityContextHolder`.
- WebFlux: `ReactiveSecurityContextHolder`.

`SecurityContext` answers the question: **under which identity is the current execution running?**

### 1.3. Access Token

An access token is a credential sent to a Resource Server or an appropriate downstream resource. It has an audience, scope, expiration, and issuer. Having an `Authentication` in memory does not automatically prove the token is still valid or suitable for another API.

### 1.4. Delegation and Token Relay

When the Orders API calls the Inventory API, it can:

- **Relay:** forward the current inbound access token if that token was issued for the downstream resource and policy permits it.
- **OAuth2 Client:** use the Orders service's own authorized client to obtain an outbound token.
- **Token exchange / on-behalf-of:** request a new token intended for downstream, representing the user or actor per AS policy.
- **Workload identity:** call using the service's own identity, without impersonating the user.

Do not pick an approach merely because `SecurityContext` happens to be available.

| Concept | Question Solved | Example |
|---|---|---|
| Authentication | Who has been authenticated? | `JwtAuthenticationToken` |
| SecurityContext | Which `Authentication` belongs to the current execution? | Context in request/thread/Reactor |
| Access token | Which credential is sent to the resource? | `Authorization: Bearer ...` |
| Token relay | Can the current token be forwarded downstream? | WebClient bearer relay filter |
| Token exchange | Does the AS issue another token for downstream? | Token intended for `inventory-api` |
| Workload identity | How does the service authenticate itself to the AS? | `client_credentials`, mTLS |

## 2. Why Can Authentication Context Be Lost When Running Asynchronously?

A Servlet request typically traverses the filter chain on a single thread:

```text
HTTP request
    |
    v
Security filter chain
    |
    v
Authenticate Bearer token
    |
    v
SecurityContextHolder
    |
    v
Controller
    |
    v
Service
    |
    v
Response
```

In the default Servlet stack, Spring Security stores `SecurityContext` using `ThreadLocal` via the default `SecurityContextHolderStrategy`. The request-handling thread has the context, whereas a thread pool running background tasks consists of different threads.

Example:

```text
Request thread: http-nio-8080-exec-4
    SecurityContext = user-42
          |
          | submit task
          v
Worker thread: task-7
    SecurityContext = empty
```

If code invokes `@Async`, `CompletableFuture.supplyAsync(...)`, `Executor.execute(...)`, or a library that spawns its own threads without context propagation, the worker thread does not automatically inherit the request's `SecurityContext`.

### 2.1. Thread Pools Make the Problem Harder

Thread pools reuse threads across many requests:

```text
Worker thread task-7
    |
    +-- processes user A's task
    |
    +-- returned to pool
    |
    +-- processes user B's task
```

If code calls `setContext(...)` manually without `clearContext()` in a `finally` block, user A's context can linger when the worker runs user B's task. This creates a risk of **cross-user context leakage**.

### 2.2. InheritableThreadLocal Is Not a General Solution for Thread Pools

Spring Security can be configured with `MODE_INHERITABLETHREADLOCAL`, but that mechanism is better suited for newly created child threads inheriting context at creation time. With thread pools, threads are usually already created before a request's task runs; request context does not automatically update per task.

Therefore, do not use `MODE_INHERITABLETHREADLOCAL` as a global propagation toggle for all executors. Use wrapper executors with an explicit set/restore/clear context lifecycle.

## 3. How Servlet SecurityContextHolder Works

In a Servlet application, after a Bearer token is verified, Spring Security creates an `Authentication` and places it in `SecurityContext`. Code can read it:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
```

This is how you read it on the Servlet execution thread. Do not store `Authentication` in a field on a singleton service:

```java
// DO NOT USE: singleton field shared across all requests.
@Service
public class OrderService {
    private Authentication currentAuthentication;
}
```

Many requests can execute concurrently. A shared field can be overwritten, causing user A to be processed under user B's identity.

### 3.1. Context Belongs to the Current Execution, Not a Singleton Bean

Spring services are normally singletons. Context must be read while the method is executing, or passed explicitly into a task. Never store request context in fields, static variables, or shared caches.

### 3.2. Spring Security Clears Context at the End of the Request

The security filter chain manages setting and clearing `SecurityContext` over the request lifecycle. Whenever code modifies `SecurityContextHolder` manually, it must restore the previous context or clear it in `finally`.

Never retain `Authentication` beyond the request by copying it into a global variable.

## 4. Propagating SecurityContext to an Executor in Servlet

Spring Security provides wrappers to execute tasks with the `SecurityContext` captured at submission time. Two common options:

- `DelegatingSecurityContextExecutor` for `Executor`.
- `DelegatingSecurityContextAsyncTaskExecutor` for `AsyncTaskExecutor` and Spring `@Async`.

The wrapper sets the appropriate context before running the task and clears/restores it after the task finishes.

### 4.1. Configuring ThreadPoolTaskExecutor and DelegatingSecurityContextAsyncTaskExecutor

```java
package com.example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;

@Configuration
@EnableAsync
public class AsyncSecurityConfiguration {

    @Bean
    ThreadPoolTaskExecutor applicationDelegateExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("orders-async-");

        return executor;
    }

    @Bean(name = "taskExecutor")
    AsyncTaskExecutor taskExecutor(
            ThreadPoolTaskExecutor applicationDelegateExecutor) {

        return new DelegatingSecurityContextAsyncTaskExecutor(
            applicationDelegateExecutor
        );
    }
}
```

In this configuration:

1. `applicationDelegateExecutor` manages the thread pool.
2. The bean named `taskExecutor` is the executor wrapped by Spring Security.
3. `@Async("taskExecutor")` explicitly targets the wrapped executor.
4. The wrapper propagates the submitting thread's context into the task.
5. When the task completes, the wrapper clears the context per Spring Security's mechanism.

Spring manages the lifecycle of the `ThreadPoolTaskExecutor` bean; do not create a new pool per request.

### 4.2. Using with @Async

```java
package com.example.orders.application;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class OrderReportService {

    @Async("taskExecutor")
    public CompletableFuture<ReportResult> buildReport(
            String orderId) {

        // Can read SecurityContext in this task
        // because taskExecutor propagated the context.
        ReportResult result = buildReportForCurrentActor(orderId);

        return CompletableFuture.completedFuture(result);
    }

    private ReportResult buildReportForCurrentActor(String orderId) {
        // Illustrative business processing.
        return new ReportResult(orderId, "READY");
    }
}
```

`ReportResult` is an application DTO. The `@Async` method must be invoked through a Spring proxy from another bean for async interception to work.

### 4.3. Self-Invocation Within the Same Bean Does Not Trigger @Async as Expected

Example:

```java
@Service
public class ReportService {

    public void start() {
        this.buildAsync(); // Self-invocation: typically bypasses the proxy.
    }

    @Async("taskExecutor")
    public void buildAsync() {
        // ...
    }
}
```

In proxy-based Spring AOP, calling `this.buildAsync()` does not go through the proxy, so `@Async` is not applied. Move the async method to another bean or invoke it through an injected proxy according to an appropriate architecture.

## 5. DelegatingSecurityContextExecutor for CompletableFuture

`CompletableFuture.supplyAsync(...)` defaults to using the common `ForkJoinPool` if no executor is passed. The common pool does not automatically carry the request's Servlet `SecurityContext`.

Avoid:

```java
CompletableFuture.supplyAsync(() -> {
    Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

    return createReport(authentication);
});
```

The task may run on a thread without context.

### 5.1. Passing a Wrapped Executor

```java
package com.example.orders.config;

import java.util.concurrent.Executor;
import java.util.concurrent.Executors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;

@Configuration
public class ReportExecutorConfiguration {

    @Bean(destroyMethod = "shutdown")
    Executor reportDelegateExecutor() {
        return Executors.newFixedThreadPool(8);
    }

    @Bean(name = "securityContextExecutor")
    Executor securityContextExecutor(Executor reportDelegateExecutor) {
        return new DelegatingSecurityContextExecutor(
            reportDelegateExecutor
        );
    }
}
```

In real projects, avoid injecting a generic `Executor` when multiple beans share that type; use `@Qualifier` or explicit bean names to avoid picking the wrong executor. The example above illustrates the wrapper; production setups should configure thread naming, bounded queues, shutdown, and rejection policies.

### 5.2. Using the Explicit Executor in CompletableFuture

```java
@Service
public class AsyncOrderFacade {

    private final Executor securityContextExecutor;

    public AsyncOrderFacade(
            @Qualifier("securityContextExecutor")
            Executor securityContextExecutor) {
        this.securityContextExecutor = securityContextExecutor;
    }

    public CompletableFuture<ReportResult> createReport(String orderId) {
        return CompletableFuture.supplyAsync(
            () -> createReportForCurrentActor(orderId),
            securityContextExecutor
        );
    }

    private ReportResult createReportForCurrentActor(String orderId) {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        return new ReportResult(
            orderId,
            authentication.getName()
        );
    }
}
```

This snippet requires imports for `Authentication`, `SecurityContextHolder`, `Qualifier`, and the DTO. It only illustrates propagation in a task submitted from a request thread that has context.

### 5.3. With thenApplyAsync and Subsequent Stages

Each async stage needs an explicitly chosen executor:

```java
CompletableFuture.supplyAsync(
        () -> loadOrder(orderId),
        securityContextExecutor
    )
    .thenApplyAsync(
        this::buildReport,
        securityContextExecutor
    );
```

Do not assume `thenApplyAsync(...)` will use the right executor or context if you omit the executor argument. Non-`Async` stages may execute on whatever thread completed the preceding stage; do not rely on ambient thread context in callbacks to perform security-sensitive work.

In multi-stage pipelines, passing an immutable actor context as an explicit parameter is often easier to reason about and control than relying on implicit ambient context in every callback.

### 5.4. A Delegating Executor Does Not Turn Context into an Outbound Token

The executor wrapper only makes `SecurityContext` visible to the task. It does not:

- Extend the access token's lifetime.
- Refresh the access token.
- Change the audience or scope.
- Grant permission to call a downstream API.
- Turn a JWT into a token exchange.
- Make a long-running task safe to hold credentials indefinitely.

The task must still use tokens for their intended purpose and enforce authorization per policy.

## 6. Never Use ThreadLocal Manually and Forget Cleanup

If you must write a highly specialized wrapper, the minimum rule is to save the old context, set the task context, and restore/clear in `finally`. However, prefer Spring Security's built-in wrappers over writing your own.

An example illustrating why `finally` is necessary:

```java
SecurityContext previous =
    SecurityContextHolder.getContext();

try {
    SecurityContextHolder.setContext(taskContext);
    task.run();
} finally {
    SecurityContextHolder.setContext(previous);
}
```

This only illustrates cleanup; real code must handle the case where the previous context was empty and should avoid sharing a mutable `SecurityContext` across tasks. Official wrappers handle lifecycle and strategy details much more reliably.

Avoid:

```java
SecurityContextHolder.setContext(context);
executor.execute(task);
// No cleanup when the task completes.
```

If the context remains on a pooled thread, the next task can inherit the wrong identity.

## 7. Mutable SecurityContext and the Principle of Minimal Data Passing

`SecurityContext` and `Authentication` can be mutable objects. Never mutate authorities/principal inside a context shared across tasks. Never attach additional tenant information to a shared `Authentication` after publishing it to an executor.

If a task only needs to know which actor initiated the work, create an immutable object with minimal information:

```java
public record ActorContext(
    String issuer,
    String subject,
    String tenantId,
    String correlationId
) {}
```

You can extract this object during the authenticated request and pass it explicitly:

```java
ActorContext actor = actorContextFactory.fromCurrentAuthentication();

CompletableFuture<ReportResult> future =
    CompletableFuture.supplyAsync(
        () -> reportService.buildFor(actor, orderId),
        reportExecutor
    );
```

`ActorContext` is data for auditing/business logic. It is **not a credential** and does not replace authorization at the time the task runs. If the task must access sensitive data, check current permissions or use service identity/delegated tokens per policy.

### 7.1. Do Not Store Raw Access Tokens in Actor DTOs

Do not add fields such as:

```java
public record UnsafeActorContext(
    String userId,
    String accessToken,
    String refreshToken
) {}
```

Placing tokens inside objects passed across multiple layers increases the number of places where tokens can be logged, serialized, dumped, or held too long. Only keep tokens in components responsible for sending tokens with an explicit lifecycle.

### 7.2. Do Not Store Authentication in Singleton Fields

Avoid:

```java
@Component
public class CurrentUserHolder {
    private Authentication authentication;
}
```

Singletons are shared by many requests. `Authentication` must be tied to the execution context or passed via task parameters, never stored in shared bean state.

## 8. WebFlux Stores SecurityContext in Reactor Context

WebFlux does not use `ThreadLocal` as the default mechanism to pass security context through a reactive pipeline. Spring Security integrates `SecurityContext` with **Reactor Context**.

Reading `Authentication`:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

import reactor.core.publisher.Mono;

public Mono<Authentication> currentAuthentication() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication);
}
```

In a reactive chain, context travels with the subscription. Operators such as `map`, `flatMap`, `publishOn`, and `subscribeOn` do not lose Reactor Context simply because execution switches threads.

### 8.1. Threads Change While Reactor Context Follows the Subscription

```text
HTTP request
    |
    v
WebFlux security filters
    |
    v
SecurityContext is written to Reactor Context
    |
    v
Mono / Flux pipeline
    |
    +-- publishOn(Schedulers.parallel())
    |
    +-- flatMap(...)
    |
    +-- WebClient outbound call
    |
    v
The same subscription context is used
```

Reactor Context is not `ThreadLocal`. Therefore, code should not call `SecurityContextHolder.getContext()` inside a WebFlux operator expecting to find the request's authentication.

### 8.2. Do Not Use SecurityContextHolder in WebFlux Reactive Code

Wrong:

```java
return orderRepository.findById(orderId)
    .map(order -> {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        return authorize(order, authentication);
    });
```

The thread running the operator may not be the original request thread, and `SecurityContextHolder` may be empty or not represent the current request.

Right:

```java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .zipWith(orderRepository.findById(orderId))
    .map(tuple -> authorize(
        tuple.getT2(),
        tuple.getT1()
    ));
```

Or pass `Authentication`/`ActorContext` explicitly from a step that already read the context.

### 8.3. contextWrite Is Not a Way to Grant Arbitrary Identity

Reactor lets you write context per subscription. Spring Security provides the helper `ReactiveSecurityContextHolder.withAuthentication(...)`. This API is useful for tests or intentional integrations, but must never be used to fabricate an `Authentication` from unverified request headers.

Avoid:

```java
return service.call()
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(
            new UsernamePasswordAuthenticationToken(
                request.getUser(),
                "N/A",
                List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
            )
        )
    );
```

This turns caller-supplied data into an identity/authority. `Authentication` must be created by a trusted authentication mechanism before being placed into `SecurityContext`.

## 9. Reactive Chains Preserve Context Automatically; Detached Subscriptions Do Not

In WebFlux, keep work inside the same publisher:

```java
public Mono<OrderSummary> summarize(String orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order ->
            inventoryClient.getAvailability(order)
                .map(availability ->
                    toSummary(order, availability)
                )
        );
}
```

If `inventoryClient` uses `WebClient` and an appropriate DPoP/Bearer relay filter, it can read the security context from the same subscription's Reactor Context.

### 9.1. Do Not Call Detached subscribe() Inside a Service

Wrong:

```java
public Mono<Void> processOrder(String orderId) {
    inventoryClient.update(orderId)
        .subscribe();

    return Mono.empty();
}
```

Calling `subscribe()` creates an independent subscription. It detaches the work from the caller's pipeline, makes error/cancellation/lifecycle management difficult, and may not carry the expected context. The controller or framework should normally subscribe to the returned publisher.

Right:

```java
public Mono<Void> processOrder(String orderId) {
    return inventoryClient.update(orderId);
}
```

If a side effect must run, express it in the pipeline and let the caller/framework manage the subscription.

### 9.2. Do Not Block to Retrieve Authentication

Wrong:

```java
Authentication authentication =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .block();
```

`block()` can stall the event loop and break reactive structure. Use `flatMap`, `zipWhen`, `deferContextual`, or pass data explicitly.

### 9.3. Mono/Flux Created Before the Request Context

A cold publisher can be created in one place and subscribed to in another. `SecurityContext` belongs to the **current subscription**, not a fixed field attached to a `Mono` object. Therefore, never cache a publisher containing user-specific data and share it across requests.

Use `Mono.defer(...)`/`Flux.defer(...)` when context must be read at subscription time, and avoid storing `Authentication` in fields.

## 10. Boundary from Reactor to Executor or CompletableFuture

Reactor Context is preserved across operators within the same reactive subscription. When crossing into an imperative API or independent executor, decide which data should be carried over.

Poor example:

```java
return orderRepository.findById(orderId)
    .doOnNext(order -> {
        CompletableFuture.runAsync(
            () -> auditService.record(order)
        );
    })
    .then();
```

`CompletableFuture.runAsync` does not automatically participate in Reactor Context. It typically uses the common pool and may run with no security context.

### 10.1. Prefer Keeping Work Reactive

If downstream has a reactive client, compose the publisher into the same pipeline:

```java
return orderRepository.findById(orderId)
    .flatMap(order ->
        auditClient.record(order)
    );
```

This is the simplest way to preserve context and error propagation in WebFlux.

### 10.2. If an Imperative Task Must Be Called, Pass ActorContext Explicitly

Read the actor from Reactor Context and pass it into the task:

```java
public Mono<ReportResult> createReport(String orderId) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(actorContextFactory::from)
        .flatMap(actor ->
            Mono.fromFuture(
                reportExecutor.submit(actor, orderId)
            )
        );
}
```

`reportExecutor.submit(...)` and `ActorContextFactory` are illustrative application APIs. `ActorContext` must be immutable and contain no raw bearer/refresh tokens.

If the task needs to call APIs on behalf of the user, a proper delegation mechanism is required; merely passing a subject or tenant ID does not make the task an authorized OAuth client.

### 10.3. Context Propagation Libraries Do Not Replace Security Design

Ecosystems may use Micrometer Context Propagation or context snapshot integrations to bridge `ThreadLocal`/Reactor Context. These tools help transmit context data across boundaries, but they do not determine which context is permitted to cross, whether raw tokens should be carried, whether the task still belongs to the original request, whether user authorization is still valid at task execution time, or whether downstream audience/scope match.

Only enable automatic context propagation once context keys, lifecycle, and sensitive data are clearly defined.

## 11. Relaying Bearer Tokens with WebClient in Servlet

When a downstream API accepts the exact inbound access token and the token has a matching audience/scope, Spring Security provides `ServletBearerExchangeFilterFunction`.

Example:

```java
package com.example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServletBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class DownstreamClientConfiguration {

    @Bean
    WebClient inventoryWebClient() {
        return WebClient.builder()
            .baseUrl("https://inventory.internal.example")
            .filter(new ServletBearerExchangeFilterFunction())
            .build();
    }
}
```

The filter function reads the current `Authentication` in the Servlet `SecurityContext`. When `Authentication` represents a suitable OAuth2 access token, it adds the Bearer token to the outbound request.

### 11.1. Conditions for Relay to Work in an Async Task

On the request thread, `SecurityContextHolder` holds `Authentication`, so the filter function can retrieve the token.

If `WebClient` is invoked inside `@Async` or `CompletableFuture` on another thread, context must be propagated via a wrapped executor. Otherwise, the filter cannot see the caller's `Authentication` and cannot relay the token as expected.

### 11.2. The Relay Filter Does Not Refresh Tokens

`ServletBearerExchangeFilterFunction` only forwards the existing access token. It does not call the token endpoint, use refresh tokens, alter the audience, expand scopes, convert the token to DPoP/mTLS, or guarantee downstream acceptance.

If the token expires, downstream may return 401. Obtaining a new token belongs to the OAuth2 Client/Authorization Server flow.

### 11.3. Only Relay When Downstream Is Truly Permitted to Receive the Token

Do not forward the inbound access token to every `WebClient`. The token may be intended for `orders-api`, not `inventory-api`. If downstream has a different audience, the token may be rejected or introduce token substitution risks.

Only relay if the AS issued the token for that resource or the trust contract allows multiple resources. Otherwise, use token exchange or service identity.

## 12. Relaying Bearer Tokens in WebFlux

In WebFlux, the corresponding component is `ServerBearerExchangeFilterFunction`.

```java
package com.example.orders.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServerBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReactiveDownstreamClientConfiguration {

    @Bean
    WebClient inventoryWebClient() {
        return WebClient.builder()
            .baseUrl("https://inventory.internal.example")
            .filter(new ServerBearerExchangeFilterFunction())
            .build();
    }
}
```

This filter uses the `Authentication` in the subscription's reactive security context to relay the Bearer access token when appropriate.

### 12.1. The WebClient Call Must Stay in the Same Reactive Chain

```java
public Mono<Availability> check(String sku) {
    return inventoryWebClient.get()
        .uri("/api/availability/{sku}", sku)
        .retrieve()
        .bodyToMono(Availability.class);
}
```

When this method is called within the same reactive chain as the authenticated request, Reactor Context propagates with the subscription and the filter can retrieve the token.

### 12.2. Do Not Create a New Subscription Inside a WebClient Wrapper

Avoid calling `subscribe()` yourself inside a filter or service. Let `WebClient` return the publisher to the caller. That way, 401/403 errors, cancellation, timeouts, and context are managed in a single flow.

### 12.3. Servlet and WebFlux Use Different Filters

| Application | Filter |
|---|---|
| Servlet MVC | `ServletBearerExchangeFilterFunction` |
| Spring WebFlux | `ServerBearerExchangeFilterFunction` |

Do not use the Servlet filter function in a reactive application, and do not use the WebFlux filter function in a Servlet request context. The two implementations retrieve `SecurityContext` from two different models.

## 13. Token Relay Is Not Token Exchange

Suppose a client sends a token intended for the Orders API:

```json
{
  "iss": "https://login.example.com",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

The Orders API calls the Inventory API. If the Inventory API requires `aud=inventory-api`, the inbound token does not automatically qualify.

There are three options:

1. **Relay token:** use the same access token when downstream is permitted to receive that token.
2. **Client credentials:** the Orders service calls Inventory using the service's own identity.
3. **Token exchange/on-behalf-of:** the AS issues a new token for Inventory, with appropriate subject/actor delegation.

### 13.1. Relay Token

```text
Caller --access token A--> Orders API
Orders API --same token A--> Inventory API
```

Only use when audience, scope, issuer, trust boundaries, and delegation policies allow it. Token relay does not modify the token.

### 13.2. Client Credentials

```text
Orders service --client authentication--> Authorization Server
Authorization Server --service access token--> Orders service
Orders service --service token--> Inventory API
```

Downstream sees the Orders service's workload identity. If per-user authorization is needed, a dedicated policy or delegation mechanism is required.

### 13.3. Token Exchange

RFC 8693 defines OAuth 2.0 Token Exchange. The Orders service can use a subject token/actor token per contract to request a new token for the downstream resource. The AS checks delegation permissions and issues an appropriate token.

Token exchange is not the Resource Server editing `aud` or `scope` inside a JWT itself. Only the AS has the authority to issue new tokens per policy.

## 14. When Should You Not Relay an Inbound Access Token?

Do not automatically relay tokens when:

- Downstream has a different audience.
- The token lacks required scopes.
- Downstream is outside the trust boundary permitted to receive the token.
- Downstream is a third party or a user-controlled host.
- The token has sender constraints such as DPoP/mTLS that downstream cannot satisfy.
- The task runs long and the token may expire.
- The caller has logged out or been revoked while the job is still pending.
- The service needs its own workload identity.
- Relaying exposes tokens via logs/proxies or observability systems.

### 14.1. Do Not Send Tokens to Arbitrary URLs

Do not write code that reads a downstream URL from the request and attaches an `Authorization` header:

```java
// INTENTIONALLY WRONG: could send bearer token to caller-chosen host.
webClient.get()
    .uri(request.getParameter("callbackUrl"))
    .headers(headers -> headers.setBearerAuth(accessToken))
    .retrieve();
```

This is a credential exfiltration/SSRF risk. Downstream endpoints must be configured or allowlisted, never taken from untrusted input.

### 14.2. Token Relay Can Expose Broader Permissions Than Needed

If an inbound access token contains `orders.read`, that does not mean every downstream service is permitted to receive that token. Consider the principle of least privilege, resource indicators/audience, scopes, and service boundaries.

## 15. Short In-Request Async Tasks vs. Long-Lived Background Jobs

Two kinds of work must be distinguished.

### 15.1. Short Async Work Belonging to the Same Request

For example, building a report in a few seconds and returning the result to the open request. You can propagate `SecurityContext` via an executor if the task genuinely needs to execute under the caller's identity.

Ensure:

- The executor is wrapped.
- The task has timeouts and a bounded queue.
- The task does not retain context longer than necessary.
- The token remains valid during outbound calls.
- Cancellations/errors are returned to the right request.
- Tokens are not written to task results or logs.

### 15.2. Background Jobs Living Independently of the Request

For example, a caller submits an export request, the API returns `202 Accepted`, and the job runs minutes or hours later. Do not keep the request's `SecurityContext` and bearer token in a queue to run indefinitely.

Reasons:

- The access token may expire before the job runs.
- The user may be disabled or their permissions/tenant membership may change.
- Refresh tokens belong to the OAuth client, not the worker.
- Queue payloads are often persisted/replicated/inspected.
- The job may run on another host or worker.
- The old context may no longer match the current state.

### 15.3. Suitable Pattern for Background Jobs

```text
HTTP request
   |
   v
Authenticate caller
   |
   v
Authorize creation of job
   |
   v
Create immutable job command:
  jobId, actorId, tenantId, requestedOperation,
  resourceIds, correlationId, createdAt
   |
   v
Persist + enqueue command (no raw tokens)
   |
   v
Worker receives job
   |
   v
Authenticate as workload/service
   |
   v
Re-check current policy and resource state
   |
   v
Execute job
   |
   v
Audit initiatedBy=actorId
```

Actor metadata in the job helps audit "who initiated it," while the worker still authenticates with workload identity and enforces current policies at execution time.

### 15.4. When Delegated User Permissions Must Be Preserved

If the job truly must act on behalf of the user, an explicit delegation design is needed:

- OAuth Token Exchange to issue a downstream token with restricted audience/scope.
- A grant/job authorization record bound to expiry, scope, and tenant.
- Delegated credentials stored in a vault/secure store with an explicit lifecycle if supported by the provider.
- Re-checking user/grant/job state prior to execution.

Do not serialize `SecurityContext` or raw refresh tokens into a message queue as a substitute for a delegation protocol.

## 16. Queues and Message Listeners Do Not Automatically Have Request SecurityContext

When a message is published, the current execution may have a `SecurityContext`. However, the message consumer typically runs in a different process/thread with no original HTTP request.

Do not assume:

```java
@KafkaListener(topics = "order-export")
public void consume(ExportCommand command) {
    Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
}
```

will receive the HTTP caller's `Authentication`. Consumers need a workload identity or a dedicated message security mechanism.

### 16.1. Event Payloads Should Contain Minimal Actor Metadata

Example:

```json
{
  "eventId": "evt-1024",
  "jobId": "job-77",
  "initiatedBy": {
    "issuerId": "company-idp",
    "subject": "customer-42",
    "tenantId": "tenant-a"
  },
  "operation": "ORDER_EXPORT",
  "resourceIds": ["order-42", "order-43"],
  "correlationId": "corr-abc"
}
```

This is event metadata, not a credential. Consumers must authenticate the message broker/source and not treat `initiatedBy` sent by any arbitrary publisher as verified identity.

### 16.2. Broker Trust and Event Integrity

- Authenticate producers/consumers with the broker.
- Authorize topics and consumer groups.
- Use explicit message schemas/versions.
- Protect event integrity across trust boundaries.
- Never put access/refresh tokens in payloads.
- Prevent duplicate delivery using idempotency/event IDs.
- Audit actor metadata as provenance data, not as a replacement for the worker's identity.

### 16.3. Re-Authorization at Processing Time

If a user's permissions are revoked after a job is enqueued but before it runs, policy must decide:

- Should a job authorized and accepted at creation time still proceed?
- Or must current permissions be re-checked?
- Does the job have an expiry/cancel state?
- Do the tenant/resources still exist and belong to the right actor?

Do not use an old `Authentication` snapshot to bypass new policies if the business domain requires permissions to remain valid at execution time.

## 17. WebClient Inside @Async: Coordinating Context and Token Relay

A Servlet application can call `WebClient` from `@Async`. To relay the inbound Bearer token, both conditions must hold:

1. The executor propagates Servlet `SecurityContext` to the worker thread.
2. `WebClient` has `ServletBearerExchangeFilterFunction`.

Example:

```java
@Service
public class AsyncInventoryService {

    private final WebClient inventoryWebClient;

    public AsyncInventoryService(
            @Qualifier("inventoryWebClient")
            WebClient inventoryWebClient) {
        this.inventoryWebClient = inventoryWebClient;
    }

    @Async("taskExecutor")
    public CompletableFuture<Availability> check(String sku) {
        Availability result = inventoryWebClient.get()
            .uri("/api/availability/{sku}", sku)
            .retrieve()
            .bodyToMono(Availability.class)
            .block();

        return CompletableFuture.completedFuture(result);
    }
}
```

This is a Servlet async example, not a WebFlux service. `block()` here may be appropriate if the method runs on a dedicated worker thread and the `WebClient` call is bounded with timeouts; do not copy this pattern onto a Netty event loop or reactive handler. For pure reactive code, return `Mono` and do not block.

In production, configure connect/response timeouts, a bounded executor, cancellation policies, and downstream error handling. If an imperative boundary is not needed, keeping the publisher reactive is simpler.

### 17.1. What Happens Without DelegatingSecurityContextAsyncTaskExecutor?

The task still runs, but `ServletBearerExchangeFilterFunction` may fail to find `Authentication` in `SecurityContextHolder`. Outbound requests go out without a Bearer token or fail per configuration. Do not work around this by putting raw tokens into singleton fields.

### 17.2. What Happens If the Token Expires Between Request and Task?

Context propagation does not extend the token. Downstream may reject the token. The client/BFF needs an OAuth2 Client manager or an appropriate token exchange; the Resource Server does not auto-refresh inbound tokens.

## 18. Token Relay in a WebFlux Chain

In WebFlux, use `ServerBearerExchangeFilterFunction` and keep outbound calls inside the same subscription:

```java
@Service
public class ReactiveInventoryService {

    private final WebClient inventoryWebClient;

    public ReactiveInventoryService(
            @Qualifier("inventoryWebClient")
            WebClient inventoryWebClient) {
        this.inventoryWebClient = inventoryWebClient;
    }

    public Mono<Availability> check(String sku) {
        return inventoryWebClient.get()
            .uri("/api/availability/{sku}", sku)
            .retrieve()
            .bodyToMono(Availability.class);
    }
}
```

When `check(...)` is invoked from a reactive request pipeline, Reactor Context is preserved and the filter can relay the appropriate Bearer token.

Do not create a `CompletableFuture` or `new Thread(...)` inside this method if you want to keep reactive context naturally.

### 18.1. publishOn and subscribeOn

`publishOn`/`subscribeOn` change the execution scheduler/thread, yet Reactor Context belongs to the subscription and is still passed across Reactor operators. This differs from Servlet `ThreadLocal`.

Even so, if an imperative API reading `SecurityContextHolder` is called inside an operator, the context does not automatically become a `ThreadLocal`. Use reactive APIs or a configured context-propagation bridge.

## 19. OAuth2 Client Manager for Separate Outbound Tokens

When the inbound access token is unsuitable for downstream, the backend can act as an OAuth2 Client and use `OAuth2AuthorizedClientManager` (Servlet) or `ReactiveOAuth2AuthorizedClientManager` (WebFlux).

The manager can select a client registration, execute client credentials or authorization code flows, refresh outbound authorized clients when a valid refresh token exists, and store authorized clients per principal/service context.

This is the **outbound authorized client's token**, not the inbound caller's token automatically turning into a downstream token.

### 19.1. When Using Service Identity

The Orders service can use `client_credentials` to call the Inventory API. Downstream then receives the service principal. If checking the initiating user is needed, pass separate actor metadata for auditing or use delegation/token exchange per policy.

### 19.2. When Using On-Behalf-Of/Token Exchange

If downstream needs delegated user permissions, the AS can issue a new token with an appropriate audience/scope. Token exchange must be performed by a permitted client with explicit policies covering subject token, actor, audience, scope, and tenant.

Never decode a JWT yourself and change the `aud` claim to the downstream audience. Only the AS issues new tokens.

## 20. DPoP and Sender-Constrained Tokens During Relay

If the inbound access token is bound to a DPoP key, merely forwarding the raw token as `Bearer` is wrong. The downstream request needs a proof matching the key bound to the token, the downstream HTTP method, target URI, exact access token, `iat`, `jti`, nonce, and replay rules.

The inbound request's proof cannot be reused downstream because `htm`/`htu` differ and `ath` may relate to a different token. A DPoP-aware client must generate a new proof for downstream per the protocol.

For mTLS-bound tokens, the downstream connection needs a certificate/private key matching the `cnf` binding. Never relay the token over a connection lacking the corresponding sender identity.

If the sender constraint cannot be satisfied, use an appropriate token exchange/workload identity instead of downgrading the token to Bearer.

## 21. Context Propagation and Cancellation/Timeouts

Async tasks need a clear lifecycle:

- If the client disconnects from the request, should the task continue?
- Can the task be canceled?
- What is the maximum execution time of the task?
- If downstream times out, should it retry?
- Does the task retain context/tokens longer than necessary?
- When a user logs out or is revoked, do running tasks stop?
- Are async exceptions returned in the HTTP response or recorded in job status?

With `CompletableFuture`, attach timeouts/cancellation per use case and avoid filling the thread pool with indefinitely waiting tasks.

With Reactor, keep publishers inside the pipeline so cancellation propagates. Use appropriate `timeout` operators and handle upstream/downstream errors.

For background jobs returning `202 Accepted`, the HTTP request has ended; do not attempt to write a response afterward. Persist job status and let clients poll/subscribe via protected endpoints.

## 22. Error Handling and Auditing When Running Under Caller Identity

An async task can fail after the initial request has already returned a response. The system should clearly record:

- `jobId`/correlation ID.
- Initiating actor.
- Relevant tenant and resource scope.
- Worker execution identity.
- Policy decisions at submission and execution time.
- Error category, never raw tokens or sensitive claims.
- Timestamp and retry count.

Distinguish:

- **Initiator:** the user/service that requested the work.
- **Executor:** the workload identity actually executing the work.
- **Delegated subject:** the identity that token exchange/delegation permits representing.

Do not log everything as if the worker were the user if the worker is using service identity. Audits should reflect both initiator and executor.

## 23. Testing Servlet Context Propagation

### 23.1. Testing That the Task Sees Authentication

A test can install a mock `SecurityContext` and submit a task through `DelegatingSecurityContextExecutor`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SecurityContextExecutorTest {

    @Test
    void propagatesContextToWorkerTask() throws Exception {
        ExecutorService delegate =
            Executors.newSingleThreadExecutor();

        try {
            var executor =
                new DelegatingSecurityContextExecutor(delegate);

            SecurityContext context =
                SecurityContextHolder.createEmptyContext();

            context.setAuthentication(
                UsernamePasswordAuthenticationToken.authenticated(
                    "user-42",
                    "N/A",
                    java.util.List.of()
                )
            );

            SecurityContextHolder.setContext(context);

            Future<String> future = submit(executor);

            assertEquals("user-42", future.get());
        } finally {
            SecurityContextHolder.clearContext();
            delegate.shutdown();
        }
    }

    private Future<String> submit(java.util.concurrent.Executor executor)
            throws Exception {
        var result = new java.util.concurrent.CompletableFuture<String>();

        executor.execute(() ->
            result.complete(
                SecurityContextHolder.getContext()
                    .getAuthentication()
                    .getName()
            )
        );

        return result;
    }
}
```

This is an illustrative test fragment. In real tests, await executor shutdown properly, avoid leaking context across tests, and use appropriate test authentications.

### 23.2. Testing That Context Does Not Leak to the Next Task

Using a single-thread executor:

1. Submit a task under user A.
2. Wait for the task to finish.
3. Submit a second task with no context.
4. Verify the second task does not see user A's `Authentication`.

This test verifies wrapper cleanup, not just successful propagation.

### 23.3. Testing @Async via the Spring Proxy

Integration tests must call the async method from another bean and await the `Future`. Calling `this.asyncMethod()` within the same bean may bypass the proxy and fail to verify `@Async` configuration.

## 24. Testing WebFlux Reactor Context

You can use `StepVerifier` and `ReactiveSecurityContextHolder.withAuthentication(...)` to set up test context:

```java
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveSecurityContextTest {

    @Test
    void readsAuthenticationFromReactorContext() {
        var authentication =
            UsernamePasswordAuthenticationToken.authenticated(
                "user-42",
                "N/A",
                java.util.List.of()
            );

        Mono<String> currentUser =
            ReactiveSecurityContextHolder.getContext()
                .map(context ->
                    context.getAuthentication().getName()
                )
                .publishOn(reactor.core.scheduler.Schedulers.parallel());

        StepVerifier.create(
                currentUser.contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(authentication)
                )
            )
            .expectNext("user-42")
            .verifyComplete();
    }
}
```

This test proves Reactor Context is read across a scheduler switch. It does not prove JWT signatures or DPoP proofs are verified; those layers require separate tests.

### 24.1. Testing Detached Subscriptions Is Not Context Propagation

Creating a detached `subscribe()` and asserting behavior can be flaky due to threads/schedulers. Instead, test the architecture by ensuring services return publishers without subscribing themselves, and verify the `WebClient` outbound filter runs in the same chain and receives the right authentication.

## 25. Testing Token Relay and Token Boundaries

| Test | What to Prove |
|---|---|
| Servlet request with Bearer token | WebClient relay filter forwards the token per configuration |
| Servlet `@Async` with wrapped executor | Filter sees `SecurityContext` on the worker |
| Servlet `@Async` with raw executor | Do not assume context is present |
| WebFlux in same Reactor chain | Server bearer relay filter reads context |
| WebFlux detached subscription | Does not rely on the old request context |
| Token audience wrong for downstream | Downstream rejects or does not relay per policy |
| Token expires during task | Relay filter does not auto-refresh |
| DPoP-bound token | Not downgraded to Bearer and inbound proof is not reused |
| Background queue job | No raw tokens in payloads |
| Token exchange | New token has appropriate audience/scope |
| Worker identity | Audit distinguishes initiator and executor |

Do not just assert that the outbound request has an `Authorization` header. Assert the **exact token**, right host, right resource, that it is never sent to endpoints outside the allowlist, and that it never appears in logs.

## 26. Common Anti-Patterns

1. **Assuming `@Async` propagates `SecurityContext` automatically:** false for unwrapped executors. Use `DelegatingSecurityContextAsyncTaskExecutor` or pass an explicit actor context.
2. **Using the default `commonPool` for `CompletableFuture`:** wrong if the task needs Servlet `SecurityContext`. Pass a wrapped executor or avoid relying on implicit context.
3. **Enabling `MODE_INHERITABLETHREADLOCAL` to fix all thread pools:** wrong because thread pools reuse threads; inheritance is not per-task and can cause stale context.
4. **Reading `SecurityContextHolder` in WebFlux:** wrong because WebFlux uses Reactor Context. Use `ReactiveSecurityContextHolder`.
5. **Detached `subscribe()` in reactive services:** wrong because it detaches the subscription, errors/cancellation/context, and lifecycle from the request pipeline.
6. **`block()` on the Netty event loop:** wrong because it blocks the event loop. Keep the reactive chain.
7. **Storing `Authentication` in a singleton field:** wrong because concurrent requests can overwrite and mix identities.
8. **Putting raw access/refresh tokens into queues:** wrong because queues, DLQs, backups, and consumer logs expand credential exposure.
9. **Treating `SecurityContext` propagation as token exchange:** wrong because propagation only carries context; it does not change audience, scope, or issue new tokens.
10. **Relaying tokens to every downstream service:** wrong because tokens may have the wrong audience, trust boundary, or sender constraints.
11. **Assuming token relay auto-refreshes:** wrong. Bearer exchange filters only forward the existing token.
12. **Using an inbound DPoP proof downstream:** wrong because proofs are bound to the inbound request's method/URI/token.
13. **Retaining `SecurityContext` after the request has ended:** wrong because long-running tasks may run with stale rights, expired tokens, and revoked users.
14. **Logging `Authentication`/`toString()`:** wrong because the object may contain claims/credentials.

## 27. Workflow for Choosing How to Propagate Context

**Step 1 — Identify the execution model.**

- Servlet thread?
- `@Async`/Executor?
- `CompletableFuture`?
- WebFlux Reactor chain?
- Queue/background worker?

**Step 2 — Determine what data the task needs.**

- Only an actor ID for auditing?
- Authorization under the caller's identity?
- An outbound access token?
- A token intended for a different resource?
- Workload identity?

**Step 3 — Choose the appropriate propagation approach.**

| Requirement | Approach |
|---|---|
| Short Servlet async needing current context | `DelegatingSecurityContextAsyncTaskExecutor` |
| Servlet Executor/CompletableFuture | `DelegatingSecurityContextExecutor` |
| WebFlux reactive chain | Keep the same Reactor pipeline/Context |
| WebFlux to imperative task | Pass `ActorContext` explicitly or use a controlled bridge |
| Outbound same token/suitable audience | Servlet/Server Bearer Exchange filter |
| Outbound token for another resource | OAuth2 Client or token exchange |
| Independent background job | Message command + workload identity + re-authorization |
| DPoP/mTLS-bound token | Use a protocol-compliant sender-constrained client; do not relay raw as Bearer |

**Step 4 — Check trust boundaries.**

- Is the destination allowlisted?
- Does the token have the right audience?
- Are scopes sufficient?
- Are there sender constraints?
- Could tokens leak into logs/proxies/queues?
- Could the task outlive the request or token?

**Step 5 — Test the lifecycle.**

- Is context set before the task?
- Is it cleared/restored after the task?
- Is there any cross-user leakage?
- Do errors/cancellations clean up properly?
- Does the async boundary still hold the right security context?
- Does token relay send the right token to the right downstream?

## 28. Operational Checklist

| Item | What to Ensure |
|---|---|
| Servlet async executor | Wrapped with a Delegating Security Context executor when context is needed |
| `@Async` | Invoked via proxy and specifies the right executor |
| CompletableFuture | Does not use default `commonPool` when context is needed |
| Thread pool | Bounded, with lifecycle/rejection policies |
| Context cleanup | Context never leaks to subsequent tasks |
| Mutable context | Never mutate shared `SecurityContext`/`Authentication` |
| WebFlux | Uses Reactor Context APIs |
| Reactive pipeline | No detached `subscribe`/`block` |
| WebClient Servlet | Uses Servlet bearer relay only when permitted |
| WebClient WebFlux | Uses Server bearer relay only when permitted |
| Token audience | Matches downstream |
| Scope/tenant | Checked independently |
| Refresh | Not performed by Resource Server bearer relay filters |
| Token exchange | Performed via a trusted AS |
| Queue payload | Contains no raw access/refresh tokens |
| Background worker | Workload identity and re-authorization |
| DPoP/mTLS | Preserves sender constraints per protocol |
| Logging | Never logs tokens, proofs, or full `Authentication` |
| Auditing | Distinguishes initiator, executor, and delegated subject |
| Tests | Cover context propagation, cleanup, token relay, and cross-user isolation |

## 29. References

- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html): `DelegatingSecurityContextRunnable`, executor wrappers, and context propagation in Servlet.
- [Spring Security — Servlet OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): Bearer authentication and `ServletBearerExchangeFilterFunction`.
- [Spring Security — Reactive OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html): Bearer authentication in WebFlux and `ServerBearerExchangeFilterFunction`.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): authorized clients and token lifecycle for outbound calls.
- [Spring Security — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html): `ReactiveOAuth2AuthorizedClientManager` and `WebClient` integration.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): context bound to subscriptions rather than threads.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer access token usage and security considerations.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): token exchange and delegation between resource servers.
- [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained access tokens and proof-of-possession.
- [OWASP API Security Top 10](https://owasp.org/API-Security/): authorization, credential exposure, and API trust boundaries.

**Conclusion:** `SecurityContext` must be propagated according to the execution model: Servlet uses executor wrappers such as `DelegatingSecurityContextAsyncTaskExecutor`, while WebFlux preserves the same Reactor Context within a reactive subscription. Token relay only forwards the existing access token; it does not refresh, change audience, or grant downstream permissions. For independent background jobs, pass minimal actor metadata, run with workload identity, and re-check permissions at execution time; if acting on behalf of a user is required, use delegation/token exchange supported by the Authorization Server. Keeping **context propagation**, **token relay**, and **delegation** distinct ensures async work never mixes identities, leaks credentials, or carries stale permissions beyond the request lifecycle.
