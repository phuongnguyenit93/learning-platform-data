# Never Call `block()` or Manual `subscribe()` in a Reactive Security Flow

> **Topic:** Reactive architecture — Spring Security fundamentals (WebFlux, Reactor). This rule applies to code executing during HTTP request handling, especially authentication, authorization, and security `WebFilter`s. Examples use Java 17+ and Spring Security WebFlux / Spring Reactor APIs.

## 1. The Core Rule and Why

In a Spring WebFlux request-processing flow, **return a `Mono`/`Flux` describing the entire security work** so WebFlux/Spring Security manages subscription. Never call `block()` to obtain a result synchronously, and never call `subscribe()` just to kick off an async operation inside a filter, authentication manager, authorization manager, or the services they invoke.

The right mental flow:

```text
HTTP request
  → SecurityWebFilterChain / WebFilters
  → authentication (Publisher) → authorization check (Publisher)
  → forward to downstream processing only if permitted
  → return Mono<Void> / Mono<Response> to WebFlux
  → runtime subscribes at the request-handling boundary
```

A `Mono<T>` is typically **lazy**: calling a method that creates a `Mono` does not mean authentication has finished. Results, errors, request cancellation, and Reactor `Context` must all flow through **the same Publisher chain** returned to the framework. Therefore, “grabbing the result right now” with `block()` and “running in the background for speed” with `subscribe()` both break the security pipeline's required execution model in different ways.

## 2. Why Is `block()` Wrong in a Security Flow?

`block()` registers a subscription and **waits synchronously** until the Publisher finishes. Inside a reactive request, the consequences can include:

- **Blocking the event loop:** if the event loop has to wait on I/O, concurrency capacity drops sharply; a slow authorization decision can hold the thread for far too long.
- **Immediate errors on non-blocking threads:** Reactor can throw an `IllegalStateException` with a message like `block()/blockFirst()/blockLast() are blocking, which is not supported in thread ...` when called on a thread marked non-blocking. Do not rely on that error always appearing; even if undetected, blocking the thread remains a bug.
- **Detaching lifecycle from the original pipeline:** `block()` creates its own subscription separate from the one WebFlux manages; it may re-execute a *cold* Publisher, trigger extra queries/permission checks, or complicate context coordination.
- **Loss of control over timeouts, errors, and cancellation:** the HTTP response flow is no longer fully expressed as a reactive operator chain.

**Wrong — checking permissions and waiting synchronously inside a `WebFilter`:**

```java
// Illustrative snippet: tokenVerifier.isValid(exchange) returns Mono<Boolean>.
Boolean valid = tokenVerifier.isValid(exchange).block(); // DO NOT do this in a WebFlux filter
if (Boolean.TRUE.equals(valid)) {
    return chain.filter(exchange);
}
exchange.getResponse().setStatusCode(HttpStatus.UNAUTHORIZED);
return exchange.getResponse().setComplete();
```

That code “works on a dev machine” or occasionally does not throw an exception **proves nothing about safety** under real load.

## 3. Why Is Manual `subscribe()` Also Wrong?

`subscribe()` immediately returns a `Disposable`, creating a **separate subscription**. It is not a way to express “finish authenticating first, then let it pass.” If a filter returns `chain.filter(exchange)` right after calling `subscribe()`, the check may still be unfinished when the request moves downstream.

**Wrong — authentication runs outside the returned chain:**

```java
// Illustrative snippet inside WebFilter.filter(...).
tokenVerifier.isValid(exchange).subscribe(valid -> {
    if (!valid) {
        exchange.getResponse().setStatusCode(HttpStatus.UNAUTHORIZED);
    }
});
return chain.filter(exchange); // May run before the verification result arrives.
```

Main risks:

1. **Race conditions and potential security bypass:** the request can proceed or the response may already be sent before the authentication callback runs.
2. **Errors live on a different subscription:** exceptions do not automatically enter the chain returned by `filter`; WebFlux/Spring Security error-handling logic cannot observe or handle them as intended.
3. **Loss of cancellation and lifetime linkage:** when a client disconnects or the request times out, the manually created subscription is not wired to the returned Publisher's cancellation; work can keep running.
4. **Loss of security/trace context:** `ReactiveSecurityContextHolder` uses Reactor `Context` bound to the subscriber. A separate `subscribe()` does not automatically inherit the request subscriber's context.
5. **Hard to test:** tests checking the returned `Mono<Void>` can report completion while the detached security work is still unfinished.

`subscribe()` **is not synonymous with `block()`**: it does not necessarily block a thread. The core mistake is creating an execution flow detached from the chain the framework needs to control. Even `subscribe(errorHandler)` does not fix the loss of ordering, context, and lifecycle.

## 4. The Right Way: Compose Security Operations with Reactor Operators

Common operators:

| Need | Appropriate expression |
|---|---|
| Transform a value synchronously with no I/O | `map` |
| Call a function returning `Mono`/`Flux` and wait in the same pipeline | `flatMap` |
| Proceed only after a `Mono<Void>` completes | `then` / `thenReturn` |
| Deny when no authentication result is emitted | `switchIfEmpty` or type-appropriate `defaultIfEmpty` |
| Log/record metrics synchronously without altering data | `doOnNext`, `doOnError`, `doFinally` |
| Handle errors intentionally inside the chain | `onErrorResume` or map to an appropriate security exception |

**Complete example of `WebFilter` *composition*** (file `TokenGateFilter.java`; requires Spring WebFlux and Reactor dependencies, and the application must provide an implementation of `TokenVerifier`):

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

public final class TokenGateFilter implements WebFilter {
    private final TokenVerifier tokenVerifier;

    public TokenGateFilter(TokenVerifier tokenVerifier) {
        this.tokenVerifier = tokenVerifier;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        return tokenVerifier.isValid(exchange)
                .defaultIfEmpty(false)
                .flatMap(valid -> {
                    if (valid) {
                        return chain.filter(exchange);
                    }
                    exchange.getResponse().setStatusCode(HttpStatus.UNAUTHORIZED);
                    return exchange.getResponse().setComplete();
                });
    }

    public interface TokenVerifier {
        Mono<Boolean> isValid(ServerWebExchange exchange);
    }
}
```

**Exact explanation:**

- `isValid(exchange)` returns `Mono<Boolean>`; no verification happens immediately when constructing the `Mono`.
- `defaultIfEmpty(false)` prevents an empty Publisher from leaving the filter without a decision.
- `flatMap` picks **one** branch once the result arrives. If `true`, it returns `chain.filter(exchange)`; if `false`, it sets HTTP 401 and completes the response. No downstream request processing starts before the result is known.
- Errors from `isValid` are not swallowed inside a detached callback; they travel through the pipeline so the error-handling layer can decide the proper response.
- WebFlux itself subscribes to the returned `Mono<Void>`; the filter **does not** call `subscribe()` or `block()`.

This example teaches Publisher composition, **not a complete token-authentication implementation**: a real application needs consistent authentication policies, error handling, filter placement, and authorization inside `SecurityWebFilterChain`. In practice, prefer built-in mechanisms such as `AuthenticationWebFilter`, `ReactiveAuthenticationManager`, and `ServerHttpSecurity` configuration rather than building a competing custom security mechanism alongside Spring Security.

## 5. Preserving `SecurityContext` Properly in a Reactive Pipeline

In the Servlet stack, many security APIs rely on `ThreadLocal`. With WebFlux, a request can hop threads; **never assume Servlet `SecurityContextHolder.getContext()` holds the reactive request's identity**. Reactive Spring Security propagates context via **Reactor `Context`**. The proper read API is `ReactiveSecurityContextHolder.getContext()`, and that Publisher must be chained into the request flow.

**Example — endpoint reading the username from reactive security context** (file `WhoAmIController.java` in a configured WebFlux + Spring Security application):

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class WhoAmIController {
    @GetMapping("/whoami")
    public Mono<String> whoAmI() {
        return ReactiveSecurityContextHolder.getContext()
                .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
                .map(Authentication::getName)
                .defaultIfEmpty("anonymous");
    }
}
```

The controller returns the Publisher to WebFlux; Spring Security has already had the chance to bind the security context to the subscription as the request traversed the chain. The fallback above applies only when no `Authentication` can be read; actual name and authorities also depend on the application's anonymous-authentication configuration.

Never write code like this in a security service:

```java
ReactiveSecurityContextHolder.getContext()
        .subscribe(ctx -> audit(ctx.getAuthentication()));
return Mono.empty();
```

The `audit` callback becomes a detached task with no guarantee of finishing before the response, is not awaited by the request, and easily loses context. If `audit` is an async operation returning `Mono<Void>`, chain it with `flatMap`/`then` into the main Publisher; if it is lightweight synchronous logging, use `doOnNext`/`doOnEach` at an appropriate point.

## 6. Ordering Authentication, Authorization, and Forwarding

A valid path must express explicit dependencies:

```text
Extract credentials / token
  └─> Verify credentials (Mono)
        ├─ error or invalid → deny / handle error
        └─ valid → create / load Authentication
                     └─> check resource permission (Mono)
                           ├─ insufficient permission → 403 / AccessDenied
                           └─ sufficient permission → chain.filter(exchange)
```

Real security code can delegate authentication and authorization to built-in filters; the diagram expresses the **logically required ordering**, not a requirement to cram every step into a single custom filter. `401 Unauthorized` typically applies to unauthenticated requests or invalid credentials; `403 Forbidden` typically applies to an authenticated identity lacking access permission. Spring Security's entry points and access-denied handlers determine the final response per configuration.

**Do not use `doOnNext` to launch an asynchronous check:**

```java
// WRONG: checkPermission(...) returns Mono<Boolean> but is not chained.
return loadAccount(id)
        .doOnNext(account -> checkPermission(account).subscribe())
        .flatMap(this::showAccount);
```

**Chain the permission check so downstream cannot “run ahead”:**

```java
// Snippet inside a service returning Mono<AccountView>.
// loadAccount, checkPermission, and showAccount are application APIs.
return loadAccount(id)
        .flatMap(account -> checkPermission(account)
                .flatMap(allowed -> allowed
                        ? showAccount(account)
                        : Mono.error(new AccessDeniedException("Forbidden"))));
```

The final example requires importing `org.springframework.security.access.AccessDeniedException` and your application types; it is a snippet, not a standalone Java class. If the permission result can be `Mono.empty()`, define an explicit default-deny policy (such as `defaultIfEmpty(false)`) so the branch is never silently skipped.

## 7. What If You Encounter a Synchronous Library?

“Do not use `block()` in reactive requests” **does not mean every synchronous API magically becomes non-blocking**. If code calls JDBC, a synchronous HTTP client, blocking file I/O, or a thread-blocking SDK, merely wrapping it in `Mono.just(...)` still runs the blocking work immediately when constructing the value.

The first priority is using genuine reactive APIs: Spring WebClient, a suitable reactive driver, or a source returning `Mono`/`Flux`. If you must integrate a legacy library, isolate the blocking portion via `Mono.fromCallable(...)` combined with `subscribeOn(Schedulers.boundedElastic())`; then **still return the Publisher** to the chain without manually subscribing or blocking.

```java
// Illustrative snippet inside a method returning Mono<Boolean>.
// legacyAcl.isAllowed(...) is a synchronous call that may block a thread.
return Mono.fromCallable(() -> legacyAcl.isAllowed(userId, resourceId))
        .subscribeOn(Schedulers.boundedElastic());
```

This is a **bounded transitional workaround**, not something that makes a synchronous API non-blocking I/O. You must bound load, account for timeouts, thread resources, and thread-safety of the legacy library. Never use `publishOn`/`subscribeOn` as an excuse to legitimize `block()` inside a filter, and do not move all authentication processing onto a scheduler just for the sake of being “reactive.” CPU-heavy password hashing also needs its own resource planning, which should not be confused with waiting on I/O via `block()`.

## 8. Cases Where `block()` / `subscribe()` Can Legitimately Appear

- **Control-program boundaries:** a CLI `main` or purely synchronous migration tool sometimes uses `block()` to wait for a result before exiting. That context is completely different from the WebFlux event loop.
- **Tests:** `StepVerifier` or a test harness subscribes to a Publisher to verify signals, errors, completion, and context. Testing is not a license to bring `block()` into production filters.
- **Top-level consumers owning lifecycle:** the WebFlux runtime, message consumers with managed start/stop lifecycles, or intentionally independent background workers can subscribe at clear boundaries. Typical filter/request security authors **do not own that boundary**.

Rule of thumb: **if your method returns `Mono`/`Flux` to Spring WebFlux/Security, compose the work into the return value; let the framework own the subscription.**

## 9. How to Test and Spot Mistakes

Use `StepVerifier` (`reactor-test` dependency) or `WebTestClient` integration tests to verify the **returned Publisher**, not just external callbacks. Meaningful test cases:

| Scenario | Expected outcome |
|---|---|
| Token verification completes late | Request does not reach the handler before the verification result arrives |
| Invalid token or permission check is `false` | Proper denial; protected processing step is never invoked |
| Verification source completes empty | Default deny or explicit policy, never silently skipping the check |
| Verification source emits an error | Error travels through the Publisher and is handled by the security handler |
| Client cancels / times out | No detached `subscribe()` task keeps running outside managed lifecycle |
| Request with identity | `ReactiveSecurityContextHolder` reads the right context inside the pipeline |
| Concurrent load | No event-loop blocking, no reliance on accidental execution ordering |

Signals to look for during code review: `.block()`, `.blockOptional()`, `.blockFirst()`, `.blockLast()`, `.toFuture().get()`/`join()`, or `.subscribe()` inside a `WebFilter`, `ReactiveAuthenticationManager`, `ReactiveAuthorizationManager`, reactive controller, or the services they call. They are not automatically bugs everywhere; check **who owns the subscription and which method returns a Publisher**. Be especially alert to `subscribe()` inside `doOnNext`, `map`, listeners, or authentication callbacks.

## 10. Checklist Before Finalizing a Reactive Security Flow

1. Every authentication step, user lookup, permission check, and awaited audit lives inside the **returned Publisher**.
2. No `block()` or equivalent synchronous wait runs on the request's event loop.
3. No manual `subscribe()` creates security work detached from the request.
4. Denial decisions are emitted **before** `chain.filter(exchange)` / resource handling; 401/403 status codes are decided by the proper configuration.
5. Empty values, errors, cancellation, and timeouts have explicit behavior; never allow by default when results are missing.
6. Security context is retrieved through the reactive chain, without assuming `ThreadLocal` follows the request across threads.
7. Thread-blocking library integrations are replaced with reactive clients or isolated under strict bounds; tests include realistic latency/load scenarios.

**Takeaway:** with Spring Security WebFlux, security must be **part of the Publisher the request is awaiting**. `flatMap`, `then`, and reactive operators express ordering, errors, and context; `block()` and manual `subscribe()` inside the pipeline strip away those guarantees.