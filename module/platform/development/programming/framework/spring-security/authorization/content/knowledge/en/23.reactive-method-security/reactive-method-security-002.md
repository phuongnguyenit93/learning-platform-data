# `Mono`, `Flux`, and Subscription-Time Authorization Checks in Reactive Method Security

## 1. Real-World Problem: Publisher Created While Authorized, Subscribed After Revocation

In a Spring WebFlux service, `alice` holds the `report:read` authority. An orchestration layer calls the service to build a data-reading pipeline:

```java
Mono<String> pending = reportService.readOne();
```

After `pending` is created, Alice's read permission is revoked. At a later point, the application subscribes to execute it:

```java
pending.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(alice)
).block();
```

**Key question:** Is permission checked when calling `readOne()` to obtain the `Mono`, when `subscribe()`/`block()` runs, or for every element emitted by a `Flux`?

In Reactive Method Security, method calls are intercepted by an AOP proxy, yet **authorization evaluation must coordinate with the subscriber's Reactor `Context`**. With `@EnableReactiveMethodSecurity` and `@PreAuthorize` on a method returning `Mono`/`Flux`, the authorization decision is part of the protected publisher and executes when that stream is subscribed to. Therefore:

- **Merely constructing a publisher does not prove access was granted.**
- For a cold protected publisher, each subscription can re-evaluate permissions against that subscription's `Authentication`.
- `@PreAuthorize` guards the **method execution**, and does not by default re-check **every item** of a long-lived `Flux`.
- Permission changes after the check **do not automatically cancel** all running subscriptions.
- `cache()`, `share()`, hot publishers, or storing/passing an already-authorized publisher can break the authorization boundary for subsequent receivers.
- To guarantee no side effects run before the subscriber is authorized, code inside the method must be **lazy** (`Mono.defer`, `Mono.fromSupplier`, reactive repository) rather than eagerly initiating writes or blocking work.

This chapter belongs to the **Reactive Method Security** topic of the **Spring Security – Authorization** module. It focuses on `Mono`, `Flux`, and **when authorization is checked at subscription time**, covering pipeline *assembly*, subscription, data emission, context, and verification testing.

After this chapter, you will be able to:

1. Distinguish **method call**, **assembly**, **subscription**, **onNext**, **onComplete/onError**, and **cancellation**.
2. Correctly enable `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` for Spring Security 6.5.
3. Understand `@PreAuthorize`/`@PostAuthorize` in a reactive environment and how they differ from synchronous method security.
4. Read `Authentication` using `ReactiveSecurityContextHolder` instead of assuming a ThreadLocal.
5. Verify that authorization decisions can differ between two subscriptions to the **same publisher**.
6. Understand why a `Flux` permitted at startup **does not imply every future item remains permitted**.
7. Avoid privilege leaks via `Mono.cache()`, `Flux.cache()`, hot/multicast streams, and detached subscriptions.
8. Build a Java 17+ / Spring Boot 3.5.8 example with `StepVerifier`, dynamic policies, and side-effect checks.
9. Distinguish pre-execution checks from per-item filtering, owner/tenant ACLs, and write-time rechecks.
10. Avoid `block()` on the WebFlux event loop, fire-and-forget `subscribe()`, and self-invocation that bypasses AOP.

**Core message:** In reactive code, you cannot infer "authorization has been checked" merely from holding a `Mono<T>` or `Flux<T>` variable. You must know who subscribes, which `Reactor Context` is active, whether the subscription actually traverses the protected publisher, and how data or permissions may change after the initial decision.

---

## 2. `Mono` and `Flux`: A Publisher Is Not an Executed Result

A **Reactive Streams `Publisher`** describes a source that emits signals when a subscriber attaches. Reactor provides:

| Type | Max `onNext` elements | Examples |
| --- | --- | --- |
| `Mono<T>` | 0 or 1 | Reading one report, async permission check, writing one document |
| `Flux<T>` | 0 to many | List of documents, event feed, multiple database rows |

A publisher is typically assembled before the underlying data source executes:

```java
Mono<String> source =
    Mono.fromSupplier(() -> {
        System.out.println("READ_DB");
        return "record-42";
    });

System.out.println("ASSEMBLED");
// READ_DB has not occurred yet.
source.block();
// At subscription time: READ_DB is printed.
```

In a simple synchronous run, stdout is:

```text
ASSEMBLED
READ_DB
```

`Mono.fromSupplier` invokes the supplier only upon subscription. `block()` itself creates **a subscription**, waits for the result, and returns the value; using it in CLI tools or tests is fine, but **never** call `block()` on the WebFlux/Netty event loop to fetch data inside a reactive controller or service.

### 2.1. Assembly Does Not Guarantee Laziness

Not every Java call that builds a publisher is lazy:

```java
// WRONG if expensiveOrMutatingCall() has immediate side effects.
Mono<String> eager = Mono.just(expensiveOrMutatingCall());
```

Java evaluates `expensiveOrMutatingCall()` **before** `Mono.just(...)` is created. If that method writes to a DB, sends an email, or calls a remote service, the side effect has already happened at **method invocation/assembly**, without waiting for subscription.

Better:

```java
Mono<String> lazy =
    Mono.fromSupplier(() -> expensiveOrMutatingCall());
```

For logic returning a Publisher:

```java
Mono<String> lazyPublisher =
    Mono.defer(() -> reactiveRepositoryOperation());
```

The two snippets above are **illustrative fragments**: `expensiveOrMutatingCall` and `reactiveRepositoryOperation` must be defined separately if used in an application.

`Mono.defer` defers **creating the inner publisher** until subscription; `Mono.fromSupplier` defers **computing a value**. For `Flux`, consider `Flux.defer(...)` and `Flux.fromIterable(...)` along with when the iterable is constructed.

### 2.2. Each Subscription Can Re-Run the Source

```java
AtomicInteger calls = new AtomicInteger();

Mono<Integer> mono = Mono.fromSupplier(
    calls::incrementAndGet
);

System.out.println(mono.block());
System.out.println(mono.block());
```

Output:

```text
1
2
```

This is a **cold** publisher, re-evaluating on every subscription. That helps when each request needs its own `Authentication` and policy evaluation, but for write operations be careful: **re-subscribing can write again**. Use idempotency keys, transactions, unique constraints, or domain guards whenever a side-effecting publisher may be retried or re-subscribed.

**Do not confuse** `Mono.just(value)` with `Mono.fromSupplier(...)`: `just` replays the precomputed value, whereas `fromSupplier` executes the supplier for each subscription.

---

## 3. Reactive Method Security Operates via Reactor Context

### 3.1. Enabling the Right Annotation

With Spring Boot 3.5.x/Spring Security 6.5.x, example configuration:

```java
@Configuration
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class SecurityConfiguration {
}
```

Methods must be called through a **Spring-managed proxy**:

```java
@Service
public class ReportService {

    @PreAuthorize("hasAuthority('report:read')")
    public Mono<String> read(Long id) {
        return Mono.defer(() -> loadReportReactively(id));
    }
}
```

`loadReportReactively` is an undefined illustrative method. In a real application, it may return a `Mono` from R2DBC, reactive MongoDB, a reactive HTTP client, or another domain service.

**Why is `@EnableReactiveMethodSecurity` required?** The Security starter and `@EnableWebFluxSecurity` for web routes do not replace **method-level** authorization configuration. Servlet/imperative `@EnableMethodSecurity` should also not be substituted for reactive method security when expecting `Mono`/`Flux` and Reactor Context.

### 3.2. Where Does Reactive Authorization Read Authentication?

Reactive Spring Security uses `ReactiveSecurityContextHolder` to access `SecurityContext` in the **subscriber's Reactor Context**. This is not the same model as ThreadLocal-backed `SecurityContextHolder` in traditional Servlets.

```java
Mono<String> currentUser =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
```

In WebFlux HTTP requests processed by Spring Security, web filters populate the security context for the request pipeline. In unit/integration tests outside HTTP, provide the context explicitly:

```java
Authentication alice = new UsernamePasswordAuthenticationToken(
    "alice", "unused",
    List.of(new SimpleGrantedAuthority("report:read"))
);

Mono<String> named =
    currentUser.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(alice)
    );
```

`contextWrite` affects only the relevant upstream portion of that chain according to Reactor Context rules. It does not make `Authentication` a global variable and does not automatically grant permissions to every thread or task in the JVM.

### 3.3. Authentication Must Not Be Self-Asserted by the HTTP Request

`new UsernamePasswordAuthenticationToken(...)` in examples and tests is **strictly for simulating an actor in a trusted environment**. Production must verify sessions/tokens via a Spring Security provider, JWT signature/issuer/audience checks, or an appropriate authentication mechanism.

Do not construct authorities from JSON like:

```json
{
  "username": "admin",
  "authorities": ["report:read", "ROLE_ADMIN"]
}
```

and treat that as valid authentication.

### 3.4. Thread Hops and `publishOn`/`subscribeOn`

The Reactor Context travels with the subscription, so a pipeline can switch schedulers via `publishOn`/`subscribeOn` while still accessing `ReactiveSecurityContextHolder.getContext()` under Reactor's model.

```java
Mono<String> result =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .publishOn(Schedulers.parallel());
```

This is a **code snippet** requiring Reactor scheduler imports. Do not conclude that ThreadLocal `SecurityContextHolder.getContext()` inside callbacks on the new scheduler will always hold authentication. If work leaves the Reactor pipeline for `CompletableFuture`, `new Thread`, `@Async`, or a background queue, context may not propagate automatically; design explicit propagation/identity for that task.

---

## 4. Four Timestamps to Distinguish

```text
T0  method invocation through Spring proxy
    service.readOne()
       |
       +--> returns a protected Publisher
             (reactive authorization is part of the pipeline)

T1  assembly/composition
    securedMono.map(...).filter(...).contextWrite(...)

T2  subscription
    subscribe(), block(), StepVerifier.create(...).verify()
       |
       +--> Reactor Context holds the subscriber's Authentication
       +--> reactive @PreAuthorize evaluates permissions
       +--> If DENY: emits authorization error
       +--> If ALLOW: continues executing the business source

T3  publisher emits signals
    onNext(...) -> onComplete() or onError(...)

T4  completion / cancel / retry / subsequent subscription
```

Even though AOP code always involves a **Java call to the proxy** at T0, with the reactive method-security interceptor in this setup, authorization evaluation is attached to the publisher and **runs at subscription**. Never inspect a constructor or T0 method-call log and conclude that authorization has already run.

### 4.1. Assembling a Publisher Before a Security Context Exists

A caller can assemble the pipeline first:

```java
Mono<String> pipeline = service.readOne();
```

Then a subscriber attaches context later:

```java
Mono<String> aliceView = pipeline.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(alice)
);
```

Crucially: **the decision must not be "frozen" to whoever created `pipeline`**, but instead evaluated against the execution's subscriber context. The runnable example in section 6 and tests in section 7 verify this behavior.

### 4.2. Same Publisher, Two Subscribers, Two Identities

```text
securedMono (not yet subscribed)
      |
      +-- subscribe Alice / report:read --> ALLOW --> business source
      |
      +-- subscribe Bob / no read --------> DENY ---> source not executed
```

This holds for **cold** protected publishers when both subscriptions **traverse the authorization boundary**. If a caller wraps the publisher with `.cache()` and replays cached results, the second receiver **may never re-subscribe to the underlying publisher carrying the security interceptor**. Section 9 explains this risk.

### 4.3. A `Flux` Permitted at Subscribe Is Not Per-Item Authorization

```text
Subscribe Flux -> @PreAuthorize ALLOW
       |
       v
  onNext(item1)
       |
  permission revoked externally
       |
  onNext(item2)
       |
  onNext(item3)
```

`@PreAuthorize` is generally a **decision prior to the protected execution**. It does not automatically re-query a permission service on every `onNext` of a long-lived `Flux`. A hot stream can continue emitting after a user's permission is revoked unless the system implements a recheck/cancellation protocol.

If business rules require per-item checks or checks before each mutation, add policies at the **point of use**. Never treat an initial ALLOW as permanent access.

---

## 5. `@PreAuthorize`, `@PostAuthorize`, and Filtering in Reactive Flows

### 5.1. `@PreAuthorize`: Blocking Before Business Execution

```java
@PreAuthorize("hasAuthority('report:read')")
public Flux<ReportView> list() {
    return reactiveRepository.findVisibleReports();
}
```

This is a **code snippet** depending on `ReportView`/repository. When denied, the business publisher is not executed under standard reactive security flow; this must be confirmed by testing data-source/side-effect counters, not only HTTP status codes.

### 5.2. `@PostAuthorize`: Inspecting Result Data, Never the Sole Guard for Writes

```java
// CODE SNIPPET, conceptual example for a Mono result.
@PostAuthorize("returnObject.ownerId == authentication.name")
public Mono<ReportView> get(Long id) {
    return reactiveRepository.findById(id);
}
```

`@PostAuthorize` inspects the result according to the method-security contract, unlike `@PreAuthorize`. With `Flux`, post-authorization/filtering mechanisms have specific semantics depending on version and Publisher type; **never assume** post-method checks safely block all side effects or every signal in a long stream. Test actual emitted items and policy invocation counts on your exact Spring Security version.

In particular, avoid:

```java
// INTENTIONALLY FLAWED DESIGN: checking after transferring money.
@PostAuthorize("hasAuthority('money:transfer')")
public Mono<String> transfer(...) {
    return sendMoney(); // side effect may already have occurred before post-check
}
```

This snippet does not compile standalone (`sendMoney` and arguments are omitted) and highlights that **authorization must precede mutation**, backed by atomic DB/business checks.

### 5.3. Filtering Each Element with a Reactive Policy

Suppose the repository already runs a **tenant-scoped** query returning `Flux<Report>`, and you want to emit only reports the actor is individually allowed to read:

```java
// CODE SNIPPET: requires defining repository, policy, Report,
// actor, and tenant from verified Authentication.
Flux<Report> visible =
    repository.findByTenant(trustedTenant)
        .concatMap(report ->
            reactivePolicy.canRead(trustedActor, report)
                .flatMap(allowed ->
                    allowed ? Mono.just(report) : Mono.empty()
                )
        );
```

Here a decision can be fetched **for each report** as `concatMap` subscribes to the policy. `concatMap` preserves ordering, whereas `flatMap` provides higher concurrency without preserving emission order when inner streams have differing latencies.

However:

- **Filter at the repository first:** avoid querying an entire tenant and filtering only in Java whenever avoidable, and never query all tenants to filter afterward.
- If the policy returns an error or no decision, never default to ALLOW.
- With pagination, filtering after `LIMIT` corrupts page sizes and counts while still loading forbidden records. Design queries and policies accordingly.
- For infinite continuous `Flux` streams, choose a recheck/cancel cadence matching your revocation SLA; `@PreAuthorize` alone is insufficient.

### 5.4. Reactive SpEL Beans Can Return `Mono<Boolean>`

Spring Security 6.5 supports calling an authorization bean from SpEL expressions, for example:

```java
@PreAuthorize("@gate.mayRead(authentication)")
public Mono<String> readOne() {
    return source.read();
}
```

In the runnable example, `gate.mayRead(Authentication)` returns a **lazy** `Mono<Boolean>`, allowing tests to flip the flag after assembly and before subscription. If a policy returns `Mono.empty()` (abstain), define the default behavior and combination rules clearly; never turn "no decision" into ALLOW. When business logic requires a definitive decision, a policy should explicitly emit `true` or `false`.

---

## 6. Preparing the Java 17+ / Spring Boot 3.5.8 Example

The demo separates three components:

- `ReadGate`: dynamic policy returning `Mono<Boolean>` and counting **actual evaluations**.
- `SecureNotes`: two protected methods returning `Mono` and `Flux`, each using `defer` and counting business-source subscriptions.
- `ReactiveMethodDemo`: builds a publisher **first**, revokes access, subscribes and checks the outcome; then re-grants access and subscribes as another actor.

**Scope:** The example runs in CLI/tests using **real Spring Security reactive method security**. You do not need an HTTP endpoint to observe Reactor Context; in real WebFlux requests, Spring Security WebFilters populate the subscriber context. CLI/tests use `contextWrite(...)` to supply verified authentication.

**No database:** counters simply reveal whether the source ran. With a real DB, you also need tenant predicates, authorization versions, and transactions; CLI tests do not prove every DB or hot stream is safe.

### 6.1. Directory Structure

```text
reactive-method-subscription/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/demo/
    │       ├── ReactiveMethodDemo.java
    │       ├── ReadGate.java
    │       └── SecureNotes.java
    └── test/
        └── java/demo/
            └── SubscriptionSecurityTest.java
```

### 6.2. Gradle

**`settings.gradle`:**

```groovy
rootProject.name = 'reactive-method-subscription'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'io.projectreactor:reactor-core'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The Spring Boot BOM selects compatible Spring Security and Reactor versions. Spring Security 6.5 applies to Boot 3.5.x; if moving to Spring Security 7/Boot 4, re-check method-security APIs and dependency migrations.

### 6.3. Dynamic Read Policy: `ReadGate.java`

**`src/main/java/demo/ReadGate.java`:**

```java
package demo;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component("gate")
public class ReadGate {

    private final AtomicBoolean open = new AtomicBoolean(true);
    private final AtomicInteger evaluations = new AtomicInteger();

    public void setOpen(boolean value) {
        open.set(value);
    }

    public int evaluations() {
        return evaluations.get();
    }

    public Mono<Boolean> mayRead(Authentication authentication) {
        return Mono.fromSupplier(() -> {
            // This runs when the policy publisher is SUBSCRIBED to,
            // not when mayRead returns the Mono.
            evaluations.incrementAndGet();

            if (!open.get() || authentication == null
                    || !authentication.isAuthenticated()) {
                return false;
            }

            return authentication.getAuthorities().stream()
                .anyMatch(authority ->
                    "notes:read".equals(authority.getAuthority()));
        });
    }
}
```

`AtomicBoolean` simulates **revoking/re-granting** decisions at runtime; it is not a production policy store. `AtomicInteger` measures how many times the decision publisher is subscribed to.

`Mono.fromSupplier` ensures reading the `open` flag happens **when the gate's publisher is subscribed to**, not eagerly when `@PreAuthorize` constructs the pipeline.

In production, `mayRead` might call a reactive permission service, tenant directory, or ACL; it must handle anonymous callers, account status, malformed responses, timeouts, and `DENY` on missing data. Never accept a boolean from an untrusted client endpoint as an authorization decision.

### 6.4. Business Service with Both `Mono` and `Flux`: `SecureNotes.java`

**`src/main/java/demo/SecureNotes.java`:**

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class SecureNotes {

    private final AtomicInteger monoSourceSubscriptions =
        new AtomicInteger();

    private final AtomicInteger fluxSourceSubscriptions =
        new AtomicInteger();

    private final AtomicInteger writes = new AtomicInteger();

    @PreAuthorize("@gate.mayRead(authentication)")
    public Mono<String> readOne() {
        return Mono.defer(() -> {
            monoSourceSubscriptions.incrementAndGet();

            return ReactiveSecurityContextHolder.getContext()
                .map(ctx ->
                    "NOTE:" + ctx.getAuthentication().getName()
                );
        });
    }

    @PreAuthorize("@gate.mayRead(authentication)")
    public Flux<String> readMany() {
        return Flux.defer(() -> {
            fluxSourceSubscriptions.incrementAndGet();
            return Flux.just("N1", "N2");
        });
    }

    @PreAuthorize("hasAuthority('notes:write')")
    public Mono<String> writeOne() {
        return Mono.fromSupplier(() -> {
            writes.incrementAndGet();
            return "WRITTEN";
        });
    }

    public int monoSubscriptions() {
        return monoSourceSubscriptions.get();
    }

    public int fluxSubscriptions() {
        return fluxSourceSubscriptions.get();
    }

    public int writes() {
        return writes.get();
    }
}
```

**Three lazy layers demonstrated:**

1. `@PreAuthorize` operates under reactive method authorization.
2. `ReadGate.mayRead` computes the policy decision only when the gate publisher is subscribed to.
3. `Mono.defer`, `Flux.defer`, and `Mono.fromSupplier` run the business source only once the subscription is permitted to proceed.

With `readOne()`, `"NOTE:alice"` is produced using the **subscriber's Reactor Context**, not a ThreadLocal belonging to whoever assembled the publisher.

With `readMany()`, one allowed subscription emits **two items**. That does not mean the gate is evaluated twice. If you need per-item checks, add them in the pipeline as shown in section 5.3.

`writeOne()` simulates a side effect with a counter; in production, writes need transactions/conditional updates and object/tenant/state guards.

### 6.5. Application + CLI Proving Assembly Differs from Subscription

**`src/main/java/demo/ReactiveMethodDemo.java`:**

```java
package demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class ReactiveMethodDemo {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveMethodDemo.class, args);
    }

    @Bean
    @Profile("!test")
    CommandLineRunner demonstrate(
            SecureNotes notes,
            ReadGate gate) {

        return args -> {
            Authentication alice =
                actor("alice", "notes:read");
            Authentication bob =
                actor("bob", "notes:view");

            // T0: build publisher; NOT YET subscribed.
            Mono<String> sharedCold = notes.readOne();
            System.out.println("CHECKS_BEFORE_SUBSCRIBE: "
                + gate.evaluations());

            // T1: revoke after assembly but before subscribe.
            gate.setOpen(false);
            denied("ALICE_AFTER_REVOKE", () ->
                sharedCold.contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(alice)
                ).block()
            );

            // T2: grant again and subscribe to the SAME publisher.
            gate.setOpen(true);
            System.out.println("ALICE_AFTER_GRANT: "
                + sharedCold.contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(alice)
                ).block()
            );

            // T3: Bob lacks the authority, still the SAME publisher.
            denied("BOB_NO_AUTHORITY", () ->
                sharedCold.contextWrite(
                    ReactiveSecurityContextHolder
                        .withAuthentication(bob)
                ).block()
            );

            // T4: Flux has 2 items, yet the gate is evaluated
            // per subscription, not automatically twice.
            Flux<String> many = notes.readMany();
            List<String> values = many.contextWrite(
                ReactiveSecurityContextHolder
                    .withAuthentication(alice)
            ).collectList().block();

            System.out.println("ALICE_FLUX: " + values);
            System.out.println("POLICY_EVALUATIONS: "
                + gate.evaluations());
            System.out.println("MONO_SOURCE_SUBSCRIPTIONS: "
                + notes.monoSubscriptions());
            System.out.println("FLUX_SOURCE_SUBSCRIPTIONS: "
                + notes.fluxSubscriptions());
        };
    }

    static Authentication actor(
            String name, String authority) {
        return new UsernamePasswordAuthenticationToken(
            name,
            "demo-only",
            List.of(new SimpleGrantedAuthority(authority))
        );
    }

    private static void denied(
            String label, Runnable task) {
        try {
            task.run();
            System.out.println(label + ": UNEXPECTED_ALLOW");
        } catch (AccessDeniedException expected) {
            System.out.println(label + ": DENIED");
        }
    }
}
```

Why is this program useful?

- `notes.readOne()` is called **once** to create `sharedCold`.
- The `.contextWrite(...).block()` calls subscribe to the **same publisher** under Alice or Bob.
- The gate closes after assembly; the first subscription does not use a "frozen" prior allow decision.
- After reopening the gate, Alice reads successfully.
- Bob lacks `notes:read`; the publisher does not grant Bob access just because Alice used it earlier.
- `readMany()` shows two items emitted within one Flux subscription without the gate automatically rechecking each item.

**The program runs on the Spring-managed service bean** injected into `CommandLineRunner`, so the method-security proxy applies. Never instantiate `new SecureNotes()` and expect `@PreAuthorize` interception.

### 6.6. Expected Console Lines

Run with the Gradle Wrapper in the project directory:

```bash
./gradlew bootRun
```

PowerShell:

```powershell
.\gradlew.bat bootRun
```

If no wrapper exists yet, generate one with a compatible Gradle version or run `gradle bootRun` if Gradle is installed.

The lines printed by `System.out.println` in `CommandLineRunner` are expected to be:

```text
CHECKS_BEFORE_SUBSCRIBE: 0
ALICE_AFTER_REVOKE: DENIED
ALICE_AFTER_GRANT: NOTE:alice
BOB_NO_AUTHORITY: DENIED
ALICE_FLUX: [N1, N2]
POLICY_EVALUATIONS: 4
MONO_SOURCE_SUBSCRIPTIONS: 1
FLUX_SOURCE_SUBSCRIPTIONS: 1
```

**Analysis:**

1. Before subscribing: the gate has not evaluated -> 0.
2. Alice while gate closed: denied; mono source is not subscribed.
3. Alice after reopening gate: allowed; mono source is subscribed once.
4. Bob while gate open but missing authority: denied; source does not run again.
5. Alice subscribes to Flux: allowed; Flux source is subscribed once and emits two values.
6. Total of four subscriptions through the gate (`deny`, `allow`, `deny`, `allow`) -> four evaluations; mono source = 1, flux source = 1.

**Verification note:** This is the **expected output from the design and source code**, not a compile/run result confirmed in the authoring environment. Run the tests in the next section on your actual Spring Boot/Spring Security version. If a project customizes reactive interceptors, re-verify this behavior.

---

## 7. Integration Tests with `StepVerifier` and Reactor Context

### 7.1. Full Test File

**`src/test/java/demo/SubscriptionSecurityTest.java`:**

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("test")
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD
)
class SubscriptionSecurityTest {

    @Autowired
    SecureNotes notes;

    @Autowired
    ReadGate gate;

    private static Authentication alice() {
        return ReactiveMethodDemo.actor(
            "alice", "notes:read");
    }

    private static Authentication bob() {
        return ReactiveMethodDemo.actor(
            "bob", "notes:view");
    }

    private static <T> Mono<T> as(
            Mono<T> publisher, Authentication auth) {
        return publisher.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auth));
    }

    private static <T> Flux<T> as(
            Flux<T> publisher, Authentication auth) {
        return publisher.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auth));
    }

    @Test
    void assemblingMonoDoesNotEvaluatePolicy() {
        Mono<String> publisher = notes.readOne();

        assertEquals(0, gate.evaluations());
        assertEquals(0, notes.monoSubscriptions());

        StepVerifier.create(as(publisher, alice()))
            .expectNext("NOTE:alice")
            .verifyComplete();

        assertEquals(1, gate.evaluations());
        assertEquals(1, notes.monoSubscriptions());
    }

    @Test
    void revocationBeforeSubscriptionIsEffective() {
        Mono<String> publisher = notes.readOne();

        gate.setOpen(false);

        StepVerifier.create(as(publisher, alice()))
            .expectError(AccessDeniedException.class)
            .verify();

        assertEquals(1, gate.evaluations());
        assertEquals(0, notes.monoSubscriptions());

        // Same publisher, but policy was re-enabled.
        gate.setOpen(true);
        StepVerifier.create(as(publisher, alice()))
            .expectNext("NOTE:alice")
            .verifyComplete();

        assertEquals(2, gate.evaluations());
        assertEquals(1, notes.monoSubscriptions());
    }

    @Test
    void sameColdPublisherUsesEachSubscribersIdentity() {
        Mono<String> publisher = notes.readOne();

        StepVerifier.create(as(publisher, alice()))
            .expectNext("NOTE:alice")
            .verifyComplete();

        StepVerifier.create(as(publisher, bob()))
            .expectError(AccessDeniedException.class)
            .verify();

        assertEquals(2, gate.evaluations());
        assertEquals(1, notes.monoSubscriptions());
    }

    @Test
    void fluxAuthorizationIsPerSubscriptionNotPerItem() {
        Flux<String> publisher = notes.readMany();

        StepVerifier.create(as(publisher, alice()))
            .expectNext("N1", "N2")
            .verifyComplete();

        assertEquals(1, gate.evaluations());
        assertEquals(1, notes.fluxSubscriptions());

        gate.setOpen(false);

        StepVerifier.create(as(publisher, alice()))
            .expectError(AccessDeniedException.class)
            .verify();

        assertEquals(2, gate.evaluations());
        assertEquals(1, notes.fluxSubscriptions());
    }

    @Test
    void writeCannotExecuteWithOnlyReadAuthority() {
        StepVerifier.create(as(notes.writeOne(), alice()))
            .expectError(AccessDeniedException.class)
            .verify();

        assertEquals(0, notes.writes());

        Authentication writer = ReactiveMethodDemo.actor(
            "writer", "notes:write");

        StepVerifier.create(as(notes.writeOne(), writer))
            .expectNext("WRITTEN")
            .verifyComplete();

        assertEquals(1, notes.writes());
    }

    @Test
    void missingSubscriberSecurityContextCannotRead() {
        // In tests without a WebFlux request/security context.
        // No trusted Authentication for the subscription.
        StepVerifier.create(notes.readOne())
            .expectError()
            .verify();

        assertEquals(0, notes.monoSubscriptions());
    }
}
```

Run:

```bash
./gradlew test
```

**Why are these integration tests rather than mere unit tests?**

- `@SpringBootTest` builds a real ApplicationContext, creating the `SecureNotes` and `ReadGate` beans plus the Spring AOP Method Security interceptor.
- `@ActiveProfiles("test")` prevents the CLI runner from executing before tests.
- `@DirtiesContext` isolates counter and gate state across tests.
- `StepVerifier` **actually subscribes**; simply calling the method and asserting no exception was thrown does not test reactive authorization.
- `as(publisher, auth)` attaches the right `ReactiveSecurityContextHolder` to each subscription.
- Tests reuse **one publisher** across two subscriptions to catch premature permission caching/pinning.
- Assertions on source subscription counts prove that denial **did not merely turn a response into an error after the business source already ran**.

### 7.2. Why Is Testing "Assembly Does Not Check" Important?

If a test only writes:

```java
notes.readOne();
```

without subscribing, the test can still pass even if the implementation checks no permissions at all. You must use `StepVerifier` or a real subscriber to verify behavior:

```java
StepVerifier.create(
    notes.readOne().contextWrite(
        ReactiveSecurityContextHolder
            .withAuthentication(alice())
    )
).expectNext("NOTE:alice").verifyComplete();
```

This **subscriber context** boundary is what distinguishes reactive method authorization from traditional synchronous calls.

### 7.3. Why Not Use `@WithMockUser` in All These Tests?

`@WithMockUser` is a helpful Spring Security testing tool. However, this lesson intentionally attaches two subscribers **to the same publisher** with differing identities and gate states, so `contextWrite(withAuthentication(...))` makes authentication timing and scope **more explicit**.

For WebFlux HTTP integration tests, you can use `WebTestClient` with `SecurityMockServerConfigurers.mockUser(...)` and `springSecurity()`. Just ensure tests actually subscribe and go through the WebFilter/proxy rather than calling controller methods directly.

---

## 8. When Is `@PreAuthorize` Re-Evaluated on a `Flux`?

Distinguish **per subscription** from **per element**:

```text
Subscription #1 (Alice):
  check policy -> ALLOW
  Flux source -> onNext(A), onNext(B), onComplete()

Subscription #2 (Bob):
  check policy -> DENY
  Flux source -> NOT subscribed

Subscription #3 (Alice, grant revoked):
  check policy -> DENY
  Flux source -> NOT subscribed
```

This is the behavior of a cold protected publisher as shown; using `Flux` alone does not add per-element ACL evaluation.

### 8.1. Permissions Can Change Between `onNext` Signals

If a stream runs for several hours, the following can occur:

```text
t1: @PreAuthorize ALLOW, subscribe
t2: emit report A
t3: admin revokes grant
t4: emit report B
t5: emit report C
```

Never assume Spring Security automatically listens to all ACL changes and cancels subscriptions after t3. If your product requires **immediate revocation on active streams**, design for it explicitly:

- Recheck before **each sensitive item** or per batch according to a freshness SLA.
- Track policy versions/tenant membership and actively cancel subscriptions upon revocation.
- Use tenant-scoped data sources at the database/query level instead of loading every tenant's rows and filtering later.
- For WebSocket/SSE or hot streams, bind principal/tenant to each session/subscriber and enforce policy at emission time.
- Once access is revoked, avoid pushing already-prefetched or buffered content beyond your product guarantees.

### 8.2. Warning About Prefetching and Buffering

Operators like `publishOn`, `flatMap`, `buffer`, `window`, and `limitRate` can alter prefetch/request patterns. Even when policy is rechecked per item at one pipeline stage, **data may already have been read upstream** before the downstream check runs.

If the requirement is "the DB must never read another tenant's object", filter inside the query/repository. If the requirement is "the item must never be emitted to an unauthorized client", enforce the check **before emission to the subscriber**. The two requirements are not identical.

### 8.3. `@PostFilter` Is Not Magic

Reactive Method Security supports filtering annotations appropriate to the version, yet `@PostFilter` should not be assumed to automatically secure arbitrary hot infinite `Flux` streams: test per-item behavior, context, authorization caching, mid-stream errors, and resource limits.

For complex policies, explicit `filterWhen`, `concatMap`, or a policy-aware repository can be easier to observe and test. `filterWhen` with a policy returning `Mono<Boolean>` can work well, provided you define behavior on policy error/empty, concurrency, and backpressure; never collapse PDP errors into `true`.

---

## 9. `cache()` and Hot Publishers: An Easily Overlooked Security Boundary

### 9.1. Replaying Data to Subscribers Who No Longer Have Permission

A dangerous pattern:

```java
// INTENTIONALLY DANGEROUS SNIPPET:
Flux<String> secured = notes.readMany();

// cache wraps OUTSIDE the publisher protected by the method interceptor
Flux<String> cached = secured.cache();
```

Suppose Alice subscribes to `cached` while authorized. The cache subscribes once to `secured`, retrieves the items, and stores them. Later, Bob subscribes to **the same `cached`**. If the cache replays stored values without **creating a new subscription to `secured`**, the original publisher's method-security check does not run for Bob.

```text
Alice -> cached
          -> subscribe secured -> authz ALLOW -> Flux source
          -> cache [N1, N2]

Bob   -> cached
          -> replay [N1, N2]
          -> does not re-subscribe secured -> does not recheck authz
```

This is a vulnerability whenever `cached` is shared **across identities or tenants**. The same applies to `Mono.cache()`, `share()`, multicast `ConnectableFlux`, Sinks, and hot stream designs if policy is placed only on the shared source subscription.

That does not mean "every cache in Reactor is unsafe"; the issue is **where the cache sits relative to the authorization boundary** and **the cache's sharing scope**.

### 9.2. Principles for Safe Cache Design

- Never cache **a publisher encapsulating user A's authorization decision** and reuse it as safe output for user B.
- When caching raw domain data, keys must include appropriate tenant/resource/version attributes; still authorize **every request/subscriber** before emission.
- If responses vary by principal or field-level policy, cache keys may need subject, action, and `policyVersion`.
- ACL/membership changes and revocations must trigger invalidation or carry strict freshness semantics.
- For multi-subscriber hot streams, enforce permissions **per subscriber** prior to exposing sensitive data, not only when connecting the upstream source.

One approach is assembling the protected publisher inside `defer`:

```java
Flux<String> perSubscription =
    Flux.defer(() -> notes.readMany());
```

Each subscriber triggers **a call through the Spring bean proxy** and subscribes to a fresh publisher. This does not replace all policies (hot sources can still share data), but avoids pinning a cached, pre-authorized publisher outside the check boundary.

### 9.3. `retry` and `repeat` Also Create New Subscriptions

```java
Mono<String> read = notes.readOne();

// Use when a proper retry policy exists; illustrative only.
Mono<String> retried = read.retry(1);
```

Retry **re-subscribes** on matching errors and can trigger another policy check. If `read` performs a write, retrying can repeat the side effect. Never automatically retry `AccessDeniedException`, because **denial is not a transient network glitch** and unauthorized retries can flood the PDP.

### 9.4. Fire-and-Forget `subscribe()`

A code path must not do:

```java
// INTENTIONALLY DISCOURAGED:
notes.writeOne().subscribe();
```

and return "write succeeded" before authorization, transaction, or mutation actually completes. The subscription may emit an error after the caller already returned a response, and Security Context might not be wired as intended if detached.

Always **return the publisher** so WebFlux/the framework manages its lifecycle, or orchestrate subscriptions with explicit state, identity, error, and cancellation handling. On HTTP paths, prefer:

```java
return notes.writeOne();
```

and let WebFlux subscribe within the request pipeline holding the proper Reactor Security Context.

---

## 10. Subscription-Time Authorization Still Has TOCTOU

Even though permissions are evaluated at subscription time, they can still change before the data transaction commits:

```text
t1: subscribe -> @PreAuthorize ALLOW
t2: Admin revokes ACL or transfers owner/tenant
t3: DB UPDATE based on stale state
t4: Commit
```

Especially with `Mono.delay`, remote calls, slow processing, or a `Flux` writing multiple items, the window between t1 and t3 can be significant.

**An ALLOW at subscription is not a guarantee that permission remains valid until commit.**

### 10.1. Updating Data with Conditional SQL

```sql
UPDATE documents
SET content = :newContent,
    version = version + 1
WHERE id = :documentId
  AND tenant_id = :trustedTenantId
  AND owner_id = :trustedActorId
  AND state = 'DRAFT'
  AND version = :expectedVersion;
```

This is **illustrative SQL**, not a schema from the demo. Check the updated row count; `0` can mean authorization, state, or version no longer matches, and must never be silently treated as success.

If permissions depend on another grants/ACL table, establish a versioning/locking/transaction protocol between **writer** and **revoker**. Wrapping a publisher in `@Transactional` alone does not guarantee permission data is freshly checked if the authorization manager ran before the transaction started.

### 10.2. Reactive Transaction Scope

With R2DBC, you can use a reactive transaction manager and:

```java
// CODE SNIPPET: requires TransactionalOperator/secured repository.
return transactionalOperator.transactional(
    repository.findByIdAndTenantId(id, tenant)
        .flatMap(doc -> recheckAndUpdate(doc, actor))
);
```

`TransactionalOperator` binds the transaction to the publisher's Reactor Context; this **differs** from thread-bound imperative JDBC transaction management. `recheckAndUpdate` must genuinely re-verify policy rather than reading a stale ALLOW from a global cache.

**Never call blocking JDBC** on the WebFlux event loop; if integrating a legacy blocking API is unavoidable, isolate it on a dedicated scheduler boundary with timeouts and proper transaction handling. Offloading blocking calls does not turn them into an R2DBC transaction.

---

## 11. Spring AOP: Paths That Can Bypass Authorization Checks

### 11.1. Self-invocation

```java
@Service
class ReportService {

    public Mono<String> outer() {
        // WARNING: called directly on this, bypassing the proxy.
        return inner();
    }

    @PreAuthorize("hasAuthority('report:read')")
    public Mono<String> inner() {
        return Mono.just("SECRET");
    }
}
```

This snippet is illustrative. If `outer` is called through a proxy yet invokes `this.inner()` internally, Spring AOP may **not apply** `@PreAuthorize` to `inner`. Move the protected method to another Spring bean and call it via an injected proxy, or place the guard at the domain boundary so it cannot be bypassed.

### 11.2. Do Not Call `new` and Expect Method Security to Work

```java
SecureNotes notes = new SecureNotes();
// new object is not managed by a Spring proxy.
```

In the demo, `SecureNotes` must be injected from the `ApplicationContext`; tests must use `@SpringBootTest` or a test context with reactive method security enabled. Do not manually instantiate the class and assume annotations take effect.

### 11.3. Return Types and Non-Reactive APIs

Per the Spring Security 6.5 documentation, reactive method security relies on **Reactor Context** and supports publisher types such as `Mono`/`Flux` (or reactive types supported by the respective version). Do not mix reactive `@PreAuthorize` on a synchronous method returning `String` and assume Servlet-identical context, pointcut, and deny behavior. For non-reactive functions, pick the matching security model and verify it.

### 11.4. Subscribing Internally

A service calling a protected method and doing `.subscribe()` on a detached publisher can lose the request's error/identity lifecycle. In WebFlux, return and combine Publishers:

```java
return auditService.saveEvent()
    .then(notes.writeOne());
```

This is a code snippet (requiring `auditService`/beans and its own contract); it lets the framework track completion and errors. When side effects must run independently of the request, create a **background job with its own dedicated identity, authorities, and policy**, rather than blindly copying a user's `SecurityContext` into a multi-hour task.

---

## 12. HTTP Errors vs. Reactive Stream Errors

A rejected subscription may receive `AccessDeniedException`/`AuthorizationDeniedException` as an **error signal**, rather than a Java exception thrown synchronously when assembling the publisher.

```java
Mono<String> pending = notes.readOne();

// Only assembling pipeline, not yet confirmed permitted.
StepVerifier.create(asAlice(pending))
    .expectError(AccessDeniedException.class)
    .verify();
```

This is a test snippet; `asAlice` must be defined. In WebFlux HTTP flows, Spring Security handles authorization errors through web security to return statuses such as 401/403 depending on state and entry point. In non-HTTP CLI or scheduler flows, the caller must handle publisher errors, for example asserting `StepVerifier.expectError(...)`.

**Do not use**:

```java
// INTENTIONALLY DANGEROUS:
.onErrorResume(AccessDeniedException.class,
    e -> Mono.just("SECRET"))
```

to turn a DENY into emitting sensitive data. If an API needs a custom error response, the fallback must **never leak data** and must perform no side effects. When the PDP yields no decision, fail closed.

If an error occurs **after the HTTP response has started streaming**, you cannot reliably convert the whole response into a clean 403; the stream/session may have to terminate with an error. Sensitive data must therefore be authorized at the right point **before emitting items**.

---

## 13. Avoiding Confusion Between `Reactor Context`, ThreadLocal, and Misrouted Identity

### 13.1. Security Context Follows the Subscription, Not the Publisher Variable

```java
Mono<String> pipeline = notes.readOne();
```

`pipeline` does not hold a single fixed "global username" in all scenarios. `ReactiveSecurityContextHolder` resolves context per subscription and `contextWrite`/composition chain. Two subscribers with different contexts are evaluated independently if both traverse the authorization boundary.

### 13.2. Never Broadcast `Authentication` Across Streams

If you cache `Authentication` in a singleton field and reuse it:

```java
// DANGEROUS: singleton retains identity from previous request.
private Authentication lastActor;
```

a subsequent request can inadvertently run as the previous user. Never store the current principal in singleton fields or custom ThreadLocals inside reactive pipelines. Use `ReactiveSecurityContextHolder.getContext()` when identity is needed inside a subscriber chain.

### 13.3. Misplaced `contextWrite`

Reactor Context obeys **upstream lookup rules**; attaching context after an unrelated branch or creating a detached subscription can prevent context consumers from seeing the expected value. Test with `StepVerifier` on the **final publisher** handled by WebFlux, not only an isolated sub-pipeline.

### 13.4. Async and Schedulers

Reactor's `publishOn`/`subscribeOn` are built with Context propagation, but futures or manually spawned threads outside Reactor do not automatically preserve `ReactiveSecurityContextHolder`. When calling remote services or pushing to queues, propagate a contract-verified identity/policy scope with correlation/auditing, and never log raw tokens.

---

## 14. Testing Timing, Replay, and Changing Permissions

An important test matrix:

| Scenario | Expected |
| --- | --- |
| Create publisher, do not subscribe | DB/source does not run; not yet considered authorized |
| Subscribe as Alice with READ | ALLOW, receives data |
| Subscribe as Bob without READ on same cold publisher | DENY, source does not run |
| Create publisher with gate open, close before subscribe | DENY |
| Create publisher with gate closed, open before subscribe | Evaluates state at subscribe; can ALLOW |
| Flux single subscription emits two items | Does not automatically recheck per item |
| Subscribe Flux second time after revocation | DENY if traversing new/re-checked protected publisher |
| Close gate after first item in long stream | Requires per-item/cancel protocol to block later items |
| `.cache()` outside secured publisher, shared with another actor | Risk of replay bypassing authorization |
| `Mono.fromSupplier` vs `Mono.just(doWrite())` | Supplier is lazy; method inside `just` ran eagerly |
| `retry`/`repeat` | Can trigger additional subscriptions and side effects |
| Method hit via self-invocation | Can bypass AOP |
| Mono authorization error | `StepVerifier.expectError(...)`; do not expect synchronous throw at assembly |
| Missing Reactor Security Context | Fail closed, never fall back to default admin/tenant |
| Grant revoked before commit yet after precheck | Requires DB/policy recheck at mutation |
| Hot SSE/WebSocket stream | Initial connection authorization insufficient for instant revocation |

### 14.1. Common Mistakes

| Mistake | Cause | Fix |
| --- | --- | --- |
| Test calls method without subscribing | Reactive auth never triggered | Use `StepVerifier`/`block` in CLI tests |
| Assuming authority locks in when creating `Mono` | Confusing assembly and subscription | Build publisher then change permission before subscribe to verify |
| Assuming `Flux` checks every `onNext` | `@PreAuthorize` guards the execution | Per-item policy / cancellation / versioning |
| Reader Bob sees Alice's cached data | Cache wrapped outside secured publisher and shared | Scope cache + authorize every subscriber |
| Write side effect occurs without subscribing | Eager `Mono.just(doWrite())` | `defer`/`fromSupplier` and transactions |
| Same command written twice | Cold publisher subscribed/retried twice | Idempotency, unique constraints, retry policies |
| Code uses `SecurityContextHolder` inside Reactor | ThreadLocal is not subscriber Context | `ReactiveSecurityContextHolder` |
| Switching to `CompletableFuture` loses identity | Leaves Reactor Context | Explicit trusted context/adapter |
| `@PreAuthorize` skipped on `this.inner()` | Self-invocation bypasses proxy | Extract bean + integration tests |
| User with same role in different tenant reads data | Checked static authority only | Tenant-scoped repository + ACL |
| PDP error handled with `.onErrorReturn(true)` | Fail-open | DENY/error without executing mutation |
| `@PostAuthorize` on write with side effects | Permission checked too late | Pre-authorize and DB guards |
| Method returns publisher yet blocks in body | Breaks reactiveness, blocks event loop | Reactive I/O, `Mono.defer`, scheduler boundary |
| Test runs outside Spring context | No AOP advisor | Inject proxy via `@SpringBootTest` |
| Flux emits partially before erroring | HTTP response already streaming | Enforce permissions before data emission |
| Assuming revoke auto-cancels active subscriptions | No notify/cancel mechanism | Policy epoch, stream cancel/recheck |

---

## 15. Self-Assessment Questions

**1.** Does `Mono<String> p = securedService.readOne();` prove Alice is authorized?

**Answer:** No. In reactive method security, you must observe an actual subscription passing through the protected publisher with a valid Reactor Security Context.

**2.** Does calling `block()` create a subscription?

**Answer:** Yes; `block()` subscribes and waits for a value or terminal signal. It is appropriate only in CLI/tests or boundaries that explicitly permit blocking.

**3.** If the gate is open at assembly but closes before subscribe, what does the demo program produce?

**Answer:** DENY, because the gate is evaluated when the subscription executes.

**4.** Two subscribers share the same cold publisher—one has READ and the other does not. Will they receive the same data?

**Answer:** No, provided both pass through the Method Security publisher; each subscription uses its own context and permissions.

**5.** If a `Flux` emits 100 items, does `@PreAuthorize` check permissions 100 times?

**Answer:** Not by default. It guards the method invocation/subscription, not automatic per-item ACL checks.

**6.** If permission is revoked mid-stream, does Spring Security automatically stop emitting all subsequent items?

**Answer:** There is no general guarantee of that. Implement a recheck/cancel policy matching your product contract.

**7.** Why is `Mono.just(repository.save(entity))` different from `Mono.defer(...)`?

**Answer:** `save` runs immediately while evaluating the argument to `Mono.just`; `defer` invokes its supplier only upon subscription.

**8.** A secured publisher is wrapped in `.cache()` after Alice reads it. Is it dangerous if Bob receives the replayed values?

**Answer:** Yes, if the cache is shared and Bob's subscription never re-enters the authorization boundary.

**9.** Does `@EnableWebFluxSecurity` enable Reactive Method Security?

**Answer:** Not by default. Enable `@EnableReactiveMethodSecurity` and verify the AOP proxy in tests.

**10.** Why must tests assert source subscription counts after a DENY?

**Answer:** To prove no unauthorized side effect or source execution occurred even though the final signal was an authorization error.

**11.** Why should `@PostAuthorize` not be the sole guard on a write operation?

**Answer:** Mutations can happen before post-authorization runs; combine pre-checks with DB/transaction constraints.

**12.** When calling `this.secured()` inside the same bean, is Method Security guaranteed to run?

**Answer:** No. Self-invocation can bypass the Spring AOP proxy.

**13.** Are `ReactiveSecurityContextHolder` and traditional `SecurityContextHolder` the same?

**Answer:** No. The reactive holder uses the subscriber's Reactor Context rather than a per-request ThreadLocal by default.

**14.** If a `Flux` has already emitted part of an HTTP response and then emits `AccessDeniedException`, can the entire response always be turned into a 403?

**Answer:** Not reliably. Once the response has started, you must handle stream termination; authorize data before emission.

**15.** What is needed when ACL/policy data in the database changes after subscription but before commit?

**Answer:** Enforce tenant/owner/authorization constraints inside the transaction or conditional update with appropriate locking/rechecking; an ALLOW at subscribe does not protect the commit by itself.

---

## 16. Official References and Further Reading

- [Spring Security 6.5 – Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html): `@EnableReactiveMethodSecurity`, `@PreAuthorize`, `@PostAuthorize`, reactive authorization interceptor, Reactor Context.
- [Spring Security 6.5 – Reactive Method Security with AuthorizationManager](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html#_enablereactivemethodsecurity_with_authorizationmanager): registering method-security advisors and expressions returning `Mono<Boolean>`.
- [Spring Security – Reactive Authentication](https://docs.spring.io/spring-security/reference/reactive/authentication/index.html): authentication in WebFlux.
- [Spring Security – Testing WebFlux Method Security](https://docs.spring.io/spring-security/reference/reactive/test/method.html): Spring Security test support for reactive methods.
- [Spring Security – Testing WebFlux Applications](https://docs.spring.io/spring-security/reference/reactive/test/web/index.html): `WebTestClient`, `mockUser`, reactive security integration.
- [Reactor Core – Reference Guide](https://projectreactor.io/docs/core/release/reference/): cold/hot publishers, assembly/subscription, backpressure, and operator semantics.
- [Reactor – Context Propagation](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): subscriber context and `contextWrite`.
- [Reactor Test – StepVerifier](https://projectreactor.io/docs/test/release/reference/): testing `Mono`/`Flux` subscriptions and terminal signals.
- [Spring Framework – Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): reactive `TransactionalOperator` and transaction boundaries.
- [Spring Framework – AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): self-invocation and proxy limitations.

**Conclusion:** In Reactive Method Security, think in terms of **publisher + subscription + Reactor Security Context**. Calling `service.method()` to obtain a `Mono`/`Flux` is neither performing the work nor "being authorized". For cold publishers guarded by Spring Method Security, subscription is the decisive point for evaluating policy and running the source; each subscription can carry a different identity and permission set. Yet `@PreAuthorize` does not automatically check every item, block hot replays, cancel active streams upon later revocation, or replace DB write-time authorization. Use lazy publishers, proper context, `StepVerifier`, scoped caches, per-item policies when needed, and transactional/conditional mutations to truly protect data.