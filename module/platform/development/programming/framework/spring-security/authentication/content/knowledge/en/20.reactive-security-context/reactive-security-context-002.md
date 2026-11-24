# Publisher Subscription Time and Identity Lifecycle in a Sequence

In Spring Security WebFlux, the identity of a processing flow is not fixed at the moment a Mono/Flux object is created. Identity is provided and looked up via **each subscription's Reactor Context**. Understanding this timing helps avoid reading the wrong user, losing SecurityContext, or leaking data across requests.

## 1. Distinguishing Assembly from Subscription

A Publisher describes *how to process*; creating it usually does not execute asynchronous work yet.

| Phase | What happens | Meaning for identity |
| --- | --- | --- |
| Assembly | Controller/service returns a Mono or Flux, declaring operators such as map, flatMap, contextWrite. | You cannot assume which Authentication will accompany future subscriptions. |
| Subscription | A Subscriber subscribes; the subscribe signal travels from the end of the sequence back to the source, then data/error/completion flows forward along the processing path. | Reactor Context propagates with the subscriber; lazily evaluated SecurityContext reads only then see that subscription's identity. |
| OnNext / OnError / OnComplete | The Publisher emits signals and terminates, or is canceled via cancel. | The Context is scoped to the subscription; it is not a global variable or an identity that persists indefinitely after the request. |

In WebFlux, **the framework normally performs the subscribe** on the Publisher returned by a handler. Calling a controller method to obtain a Mono does not mean all logic inside the Mono has already run. If a callback, computation, or call outside the Publisher executes eagerly during assembly, it can still run early; laziness depends on how the Publisher is constructed.

Java example with Reactor:

~~~java
Mono<String> eager = Mono.just(expensiveCall()); // expensiveCall() runs immediately
Mono<String> lazy = Mono.fromCallable(() -> expensiveCall()); // runs upon subscribe
Mono<String> deferred = Mono.defer(() -> buildPublisher()); // creates the inner Publisher upon subscribe
~~~

This is an **illustrative snippet**, not a standalone program. If work has side effects or needs the request identity, place it in a reactive branch executed at subscription time. Do not use Mono.just to defer a call that has already executed beforehand.

## 2. Where Does Identity Live in WebFlux?

In synchronous Spring MVC, code is commonly accustomed to ThreadLocal-based SecurityContextHolder. In reactive processing, parts of a single request can run on multiple threads and one thread can serve multiple requests. Therefore ThreadLocal is not a reliable source for inferring the current user at every stage of a pipeline.

Spring Security reactive uses:

- **Authentication**: the principal, authorities, and authentication state of a user/application.
- **SecurityContext**: holds Authentication.
- **ReactiveSecurityContextHolder**: API for reading/writing Mono<SecurityContext> in the Reactor Context.
- **Reactor Context**: data attached to the *subscriber*, immutable in usage (contextWrite creates a new context for the affected portion of the sequence).

Core API:

~~~java
Mono<SecurityContext> context = ReactiveSecurityContextHolder.getContext();

Mono<String> username = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);

Mono<String> forOneSubscription = username.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(authentication)
);
~~~

This is an **illustrative snippet**; the authentication variable must hold an appropriate value in scope. getContext() returns a Publisher, not a synchronous SecurityContext. If no context is present, the Mono may complete empty. Depending on anonymous authentication configuration, an unauthenticated request may see an anonymous principal instead of an empty Mono; do not equate the two cases.

Note: withAuthentication(...) adds Authentication to the **Reactor Context of the affected subscription**. It **does not automatically persist login state across other requests** and does not replace the application's authentication policy, repository, or tokens.

## 3. Timeline of a WebFlux Request

A typical path (details depend on filter configuration):

1. An HTTP request enters the WebFilter/Spring Security chain.
2. Spring Security obtains authentication information from the appropriate mechanism. ReactorContextWebFilter may use ServerSecurityContextRepository to initialize ReactiveSecurityContextHolder; AuthenticationWebFilter may establish the context upon successful authentication.
3. The handler creates and returns a Mono/Flux. When WebFlux subscribes to the Publisher, the subscriber's Reactor Context is delivered to operators in scope.
4. When an operator reads ReactiveSecurityContextHolder.getContext() in the sequence, it receives the context effective for the **current subscription**.
5. When the response completes, errors, or is canceled, the subscription ends. A subscription's context is not a long-term data store. If you want authentication to persist across requests, there must be an appropriate storage/restoration strategy (e.g., session) or re-authentication from a token on each new request.

Timeline diagram:

~~~text
HTTP request
  -> Spring Security WebFilter / authentication
  -> build Mono/Flux sequence (assembly)
  -> WebFlux subscribes
       -> subscriber carries Reactor Context
       -> contextWrite enriches context for upstream
       -> getContext() reads that subscription's Authentication
       -> process data -> complete / error / cancel
  -> end of subscription scope
~~~

Context is not bound to "the moment the Mono variable is declared." Two requests can share the exact same pipeline definition yet subscribe with two different contexts. Isolation holds only if the application does not share mutable state or cache identity-dependent data with the wrong scope.

## 4. Java 17+ Example: One Publisher, Three Subscriptions

The example below runs in a project with **reactor-core** and **spring-security-core** (typically already present in a Spring Boot WebFlux app using Spring Security). File: **IdentityContextDemo.java**.

~~~java
import java.util.List;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

import reactor.core.publisher.Mono;

public class IdentityContextDemo {

    public static void main(String[] args) {
        Mono<String> identity = Mono.defer(() -> {
            System.out.println("read during subscribe");
            return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .defaultIfEmpty("anonymous");
        });

        System.out.println("ASSEMBLED");

        System.out.println("S1=" + identity
            .contextWrite(ReactiveSecurityContextHolder.withAuthentication(user("alice")))
            .block());

        System.out.println("S2=" + identity
            .contextWrite(ReactiveSecurityContextHolder.withAuthentication(user("bob")))
            .block());

        System.out.println("S3=" + identity.block());
    }

    private static Authentication user(String name) {
        return new UsernamePasswordAuthenticationToken(
            name,
            "demo",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
    }
}
~~~

Exact stdout result:

~~~text
ASSEMBLED
read during subscribe
S1=alice
read during subscribe
S2=bob
read during subscribe
S3=anonymous
~~~

Explanation:

- Merely creating the Mono at the identity declaration line does not print "read during subscribe".
- Each block() in the demo program creates **a separate subscription**, so Mono.defer runs three times.
- S1 and S2 apply different contextWrite calls to the same previously built Publisher, reading alice and bob respectively.
- S3 attaches no SecurityContext, so defaultIfEmpty emits "anonymous".
- The Authentication values in the example are test data only; a real application must verify credentials/tokens via a trusted mechanism before granting access.

**Do not copy this use of block() into a WebFlux controller or event-loop processing.** block() here only makes the synchronous main program easy to observe and explicitly triggers subscriptions. In an application, return Mono/Flux to the framework so the framework manages subscription.

## 5. Which Part of the Sequence Does contextWrite Apply To?

Reactor Context travels **from subscriber (downstream) toward source (upstream) during the subscribe phase**. Therefore a contextWrite operator below a processing segment can enrich the context seen by segments above it. Do not treat contextWrite as mutating a global variable for the entire sequence.

Standalone Reactor Context example (snippet; assumes Mono is imported):

~~~java
Mono<String> message = Mono.deferContextual(ctx ->
    Mono.just("user=" + ctx.getOrDefault("user", "guest"))
);

String a = message.contextWrite(ctx -> ctx.put("user", "alice")).block();
String b = message.block();

// a = "user=alice"
// b = "user=guest"
~~~

The comments for a/b show the expected results when run in a synchronous demo environment. contextWrite affects only subscription a; it does not mutate the message Publisher so that b automatically becomes alice.

**Placement of contextWrite matters.** Consider the snippet:

~~~java
Mono<String> identity = ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .defaultIfEmpty("anonymous");

Mono<String> correct = Mono.just("go")
    .flatMap(value -> identity)
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(user("alice")));

Mono<String> wrongScope = Mono.just("go")
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(user("alice")))
    .flatMap(value -> identity);
~~~

When subscribed independently in an environment with no external context, correct emits "alice", whereas wrongScope emits "anonymous": wrongScope's contextWrite is upstream of flatMap, while the identity Publisher is subscribed to by flatMap downstream. Practical rule: place the context scope where it wraps **every part of the processing that needs to read it**, and verify the position of context-reading operators when splitting sequences.

If you need arbitrary data from Reactor Context, use Mono.deferContextual(...) (or the corresponding contextual API). For Spring Security identity, prefer ReactiveSecurityContextHolder.getContext(), avoiding guessing internal Reactor Context keys.

## 6. Preserving Identity Across flatMap and Asynchronous Operations

In pure Reactor sequences, flatMap, concatMap, publishOn, and subscribeOn work with Reactor's subscription/context. Switching schedulers via publishOn/subscribeOn **does not automatically lose Reactor Context**. However, arbitrary ThreadLocals, MDC, tasks manually submitted to an executor, or callbacks from non-Reactor libraries do not inherently share the same semantics.

User-scoped business pattern:

~~~java
public Mono<Order> currentUserOrder(String orderId) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .switchIfEmpty(Mono.error(new IllegalStateException("Missing authentication")))
        .flatMap(auth -> orderService.findForOwner(orderId, auth.getName()));
}
~~~

This is a **service snippet**, depending on your application's Order type and orderService. The repository must enforce ownership/permissions at the appropriate query boundary; merely passing auth.getName() does not guarantee authorization. For systems using immutable identifiers, extract a stable id from the principal/token rather than assuming username is always the data key.

Common mistake:

~~~java
public Mono<Void> triggerAudit() {
    auditPublisher.subscribe(); // creates a standalone subscription detached from the request
    return Mono.empty();
}
~~~

This subscribe() call creates an independent branch that is not automatically governed by the request's cancellation/error/context lifecycle. The right pattern is to **chain the audit into the returned pipeline**:

~~~java
public Mono<Void> triggerAudit() {
    return auditPublisher.then();
}
~~~

Both snippets above assume auditPublisher is a Mono<Void> or compatible Publisher. If auditPublisher already generated data at assembly or genuinely needs to run in the background, design a dedicated lifecycle and pass minimal, explicit identity; do not rely on a new subscriber automatically inheriting the Reactor Context.

## 7. Lifecycle Breakpoints and Identity Leakage Risks

| Situation | What to understand | How to handle |
| --- | --- | --- |
| Reading SecurityContextHolder.getContext() in a reactive handler | ThreadLocal depends on the thread; multiple requests can interleave on the same pool. | Use ReactiveSecurityContextHolder.getContext() inside Mono/Flux, or the principal supplied by WebFlux. |
| Calling block() to obtain Authentication in a controller/service | Creates a separate subscription, can lose request context and block the event loop. | Keep processing in map/flatMap, returning a Publisher. |
| Calling subscribe() inside doOnNext/subscribe(...) | The child branch has its own subscription/lifecycle; errors and cancellation are hard to manage and context may be missing. | Compose the child branch with flatMap/then/when and return the Publisher to WebFlux. |
| Mono.cache(), share(), or hot Publishers holding per-user results | Results may be reused across subscribers; a different context will not recompute the cached value. | Do not cache identity-sensitive results in a shared scope; if caching is needed, partition by user key and permissions, with expiration/invalidation policies. |
| Storing Authentication in a static field or singleton mutable field | One request's identity can overwrite another's. | Keep data scoped to the subscription or pass the specific principal as an argument. |
| Crossing to CompletionStage, executor, or non-Reactor callback APIs | Reactor Context propagation does not necessarily cross integration boundaries. | Pass minimal information explicitly or use a configured context propagation mechanism, verified by tests. |
| retry()/repeat() | Can re-subscribe to the source and re-run side effects. | Design idempotent operations, read context within the subscription, and verify which permissions and state apply on each attempt. |
| cancel/error | The pipeline terminates early; doOnComplete does not run for all termination types. | Use doFinally when cleanup is needed for complete, error, or cancel; do not retain principals past their lifecycle. |

A dangerous caching illustration (snippet; identity and user(...) as in section 4):

~~~java
Mono<String> shared = identity.cache();

String first = shared
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(user("alice")))
    .block();

String second = shared
    .contextWrite(ReactiveSecurityContextHolder.withAuthentication(user("bob")))
    .block();
~~~

After the first completion succeeds, first and second can both be "alice", because Mono.cache() replays the stored signal without re-executing the source for subsequent subscribers. **This is a design flaw of caching user-specific information**, not evidence that Reactor Context mixed things up. Never use an application-wide shared cache for results that depend on SecurityContext.

## 8. Subscription SecurityContext vs. Login Session

Three questions must be separated:

1. **Who authenticates this request?** Authentication filters, tokens, session/repository, or security configuration establish a valid Authentication.
2. **Who does the current reactive segment see?** The SecurityContext in the current subscription's Reactor Context, provided the reading operator is in the proper scope.
3. **Who does the next request see?** Depends on the mechanism for maintaining/restoring authentication across requests; a Publisher's contextWrite does not serve that role.

For example, a stateless application can verify a bearer token on each request; a session-based application can save/restore SecurityContext via ServerSecurityContextRepository. Both can use Reactor Context **within** a single request. Never use the demo's withAuthentication to simulate a successful login in production.

Reactive method security also relies on Reactor Context. To enforce authorization along a reactive path, keep the returned Mono/Flux sequence under Spring Security's management; avoid detaching subscribe calls that drop policy scope.

## 9. Testing with StepVerifier

Targeted testing example (JUnit 5 snippet; the project needs reactor-test and spring-security-core, plus the user(...) method from the main example):

~~~java
@Test
void eachSubscriptionReadsItsOwnIdentity() {
    Mono<String> identity = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .defaultIfEmpty("anonymous");

    StepVerifier.create(identity.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(user("alice"))))
        .expectNext("alice")
        .verifyComplete();

    StepVerifier.create(identity.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(user("bob"))))
        .expectNext("bob")
        .verifyComplete();

    StepVerifier.create(identity)
        .expectNext("anonymous")
        .verifyComplete();
}
~~~

Import org.junit.jupiter.api.Test and reactor.test.StepVerifier, along with the IdentityContextDemo imports from section 4. Tests do not need to call block(); StepVerifier actively subscribes and verifies signals. To test scope mistakes, place contextWrite before/after flatMap as in section 5 and compare outcomes. To test data leakage, run two different principals against the same cache/share Publisher and verify the design does not return the first principal's data to the second.

## 10. How to Apply This When Designing and Debugging

When a request reports "user not found," "occasionally wrong identity," or "lost Authentication after async," check in order:

1. **Publisher creation point:** does it run side effects or read ThreadLocal eagerly at assembly time?
2. **Subscription point:** is WebFlux the subscriber, or is there a manual subscribe()/block() creating a new path?
3. **Authentication source:** did the authentication filter create/restore SecurityContext, and was the request actually authenticated?
4. **contextWrite boundary:** is the operator reading ReactiveSecurityContextHolder upstream in the right scope?
5. **Library boundary:** pure Reactor schedulers or non-Reactor callbacks/executors?
6. **Result sharing:** are caches, singleton state, hot Publishers, or retries corrupting data scope?
7. **Termination:** do complete/error/cancel paths clean up properly without holding identity references past the request lifecycle?

Core mindset: **a Publisher is a description; a subscription is an execution with its own Reactor Context.** Read identity at the appropriate reactive point at subscription time; keep SecurityContext scoped to the pipeline rather than turning it into global state.

### Technical References

- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security — ReactiveSecurityContextHolder API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security — ReactorContextWebFilter API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ReactorContextWebFilter.html
- Project Reactor — Context reference: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
