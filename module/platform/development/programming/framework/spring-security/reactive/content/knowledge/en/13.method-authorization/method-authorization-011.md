# Side Effects Already Occurred and the Limits of Post-Execution Checks

## 1. Learning objectives

In **Spring Security Reactive**, method authorization can occur before or after a service method produces a result. `@PreAuthorize` generally checks permissions before allowing the method to run; `@PostAuthorize` inspects the returned result, while `@PostFilter` drops non-matching elements from the result. However, **refusing to return a result does not mean side effects were prevented**.

Dangerous example: a method saves an order to the database and returns `Mono<Order>`. `@PostAuthorize` discovers the order belongs to someone else and denies it. The client receives HTTP 403, yet the `UPDATE` statement may have already committed beforehand. If the method sent an email or published a Kafka event, there is no built-in mechanism to recall those actions solely via post-authorization.

This lesson belongs to **Method Authorization** in **Spring Security - reactive**. After this lesson, you will know how to:

1. Distinguish authentication, pre-execution vs. post-execution authorization, HTTP responses, and actual resource state.
2. Understand the sequence of cold publishers, subscription, executing side effects, emitting values, `@PostAuthorize` evaluation, and subscribers receiving signals.
3. Explain when `@PostAuthorize` is useful, and why it should not be the primary authorization gate for writes, deletes, or payments.
4. Recognize the consequences of `@PostFilter` on `Flux`, pagination, expensive queries, streaming data, and upstream side effects.
5. Analyze `Mono<Void>`, empty publishers, errors, cancellation, emitted events, DB commits, and already-committed HTTP responses.
6. Structure upfront checks with `@PreAuthorize`, permission services, conditional SQL, transactions, and the transactional outbox pattern.
7. Run a WebFlux Java 17+ demo and use `WebTestClient` to verify that an HTTP 403 **can still leave side effects**, contrasted with pre-authorization denying before state changes.
8. Avoid self-invocation bypassing Spring AOP, manual `subscribe()`, blocking I/O, and confusing CSRF 403 with authorization 403.

Code examples target Spring Boot 3.x, Spring Security 6.x, and Java 17+. In the example, `AtomicInteger` acts as a non-transactional side effect for clear observation; it is **not** a production business storage model. Annotated methods must reside on Spring-managed beans invoked through the proper proxy.

## 2. What is a side effect, and when does it happen?

A **side effect** is any observable impact outside the return value. Examples:

| Operation | Side effect | Automatically undone just because post-check denies? |
|---|---|---|
| Adding two numbers in local variables | No external state | Not needed |
| `AtomicInteger.incrementAndGet()` | Counter mutates | **No** |
| Committed `UPDATE ...` | Database mutates | **No** |
| Sending email/SMS | Recipient may already see notification | **No** |
| Successful payment API call | External system already processed it | **No** |
| Sending a message to a broker | Consumers may already receive it | **No** |
| Writing to a global cache | Cache state mutates | **No** |
| Writing logs containing sensitive data | Data may already be exposed | **No** |
| R2DBC write in an uncommitted transaction | State may roll back if transaction catches error in the right scope | **Depends on transaction boundary** |

Do not treat a `403 Forbidden` response as a rollback command. 403 indicates the client lacked permission in the active security flow; it **does not prove** that databases, filesystems, caches, or external systems remained untouched.

### 2.1. Distinguishing four layers of outcomes

When debugging a denied request, inspect independently:

- **Authorization decision:** did policy grant or deny?
- **Reactor signal:** did the publisher emit a value, `onError`, `onComplete`, or get cancelled?
- **HTTP response:** 401, 403, 302, 500, or response already committed?
- **Actual state:** was the row updated, event published, email sent, or cache written?

A `WebTestClient` test checking only `expectStatus().isForbidden()` is insufficient for a mutating endpoint. Tests must also assert that data did **not** change on unauthorized requests.

## 3. Execution order: @PreAuthorize vs. @PostAuthorize

Logical model for a method returning `Mono<Receipt>`:

```text
REQUEST -> Security Authentication
             |
             v
        Spring AOP proxy
             |
        @PreAuthorize
             | deny -> blocks before protected method/work
             v allow
        method returns Mono<Receipt>
             |
           subscribe
             |
     upstream executes (DB write / event / email)
             |
       emit Receipt(owner=...)
             |
        @PostAuthorize
         |          |
       allow       deny
         |          |
     return value   AccessDeniedException / denial signal
                    |
                  HTTP layer may return 403
                    |
              SIDE EFFECT does not disappear automatically
```

This is a **functional model**, not a fixed internal ordering of every advisor. In reactive code, distinguish **when the Java method is called** from **when the publisher is subscribed and executed**.

### 3.1. Reactor is lazy, yet not every Java statement is lazy

```java
AtomicInteger writes = new AtomicInteger();

Mono<Integer> lazy = Mono.fromSupplier(
    () -> writes.incrementAndGet());

// Only creates the Mono: writes.get() is still 0.
// Only upon subscribe does the supplier run.
```

This snippet requires importing `java.util.concurrent.atomic.AtomicInteger` and `reactor.core.publisher.Mono`. Running `lazy.block()` is appropriate only in illustrative main/test code, **never** in WebFlux handlers.

Watch out for:

```java
Mono<Integer> eager =
    Mono.just(writes.incrementAndGet());
```

Here `incrementAndGet()` is executed by Java **immediately before** `Mono.just(...)` is invoked. The side effect happened during publisher assembly without waiting for subscription. If a method performs eager side effects, post-authorization is even less capable of acting as "upfront protection".

Publishers from R2DBC/WebClient normally execute I/O upon subscription, yet custom Java statements can run eagerly. Do not assume lifecycle behavior merely because a method declares `Mono<T>`.

### 3.2. What does a pre-check need to know?

`@PreAuthorize` can use the principal, roles, authorities, and method arguments:

```java
@PreAuthorize("#p0 == authentication.name")
public Mono<Receipt> saveFor(String owner) {
    return repository.saveFor(owner);
}
```

This is a snippet; `repository` and `Receipt` are project-defined. `#p0` is the first method argument, avoiding reliance on parameter-name retention config. Checking beforehand blocks method invocation if the `owner` argument does not match the authenticated user.

**However, a client-sent owner does not prove true resource ownership.** For `orderId` or `projectId`, look up owner/tenant/ACL from an authoritative source, and embed permission predicates inside the update query. A pre-check with the right timing can still enforce the wrong policy if its input data is untrusted.

### 3.3. Post-checks require the result before deciding

```java
@PostAuthorize("returnObject.owner == authentication.name")
public Mono<Report> read(String reportId) {
    return repository.findById(reportId);
}
```

This snippet assumes `Report` has JavaBean property `owner` and the repository returns `Mono<Report>`. Post-authorization can be helpful as defense-in-depth for **read-only results**: objects belonging to others are not forwarded to callers. Nevertheless:

- The database **may already have read** the data.
- The query may have triggered audit/cache/observability side effects.
- Tenant-unscoped queries can waste resources or leak side-channel signals.
- If the method mutated data before returning `Report`, side effects may already have occurred.

Prefer queries that fetch only data the principal is allowed to access and keep post-checks as an extra layer, never the sole safeguard.

### 3.4. @PostFilter is not equivalent to WHERE owner = ...

```java
@PostFilter("filterObject.owner == authentication.name")
public Flux<Report> listReports() {
    return repository.findAll();
}
```

This snippet uses `Flux`, `@PostFilter`, and a project-supplied reactive repository. `filterObject` is each element to inspect. Downstream filtering **does not automatically rewrite the query** into `WHERE owner_id = :principal`. All data may have been fetched, mapped, decrypted, logged, or subjected to upstream side effects before being dropped. It can also break pagination: the DB returns a large page of unauthorized records, leaving only a few after post-filtering.

For large or multi-tenant datasets, prefer repository queries scoped by **tenant, user, membership, role, and ACL**. Do not assume `@PostFilter` protects every streaming/hot publisher case; test behavior for your exact Spring Security version, publisher type, and serialization.

### 3.5. Mono.empty, Mono<Void>, and errors

With `Mono.empty()` or `Mono<Void>`, there is no business object emitted to inspect `returnObject.owner`. For instance, a delete operation returning `Mono<Void>` cannot be safely guarded solely by an expression on the *result's* owner. Authorize before deleting and enforce owner/tenant directly inside the `DELETE`.

When a publisher emits `Mono.error(e)`, there is no valid `returnObject` to apply success-path rules. Cancellation cannot undo already-committed effects either. On streams that already started flushing bytes, a late authorization error may arise after the HTTP response committed; the server cannot claw back data the client already received.

## 4. @EnableReactiveMethodSecurity and differences from Servlet

Spring Security WebFlux uses Reactor Context to hold `Authentication` per subscription. To apply `@PreAuthorize`, `@PostAuthorize`, and `@PostFilter` to reactive methods, enable reactive method security, e.g.:

```java
@Configuration
@EnableReactiveMethodSecurity
public class ReactiveAuthorizationConfig {
}
```

This is a Spring configuration class requiring `Configuration` and `EnableReactiveMethodSecurity` imports. The hands-on project below enables it in the full security config.

- Reactive method security integrates via **Spring AOP**; a method on a Spring-managed bean must be called through its proxy for advisors to execute.
- Standard reactive methods return `Mono<T>`/`Flux<T>`; Spring Security reads authentication from Reactor Context.
- `@EnableMethodSecurity`, `HttpSecurity`, and `SecurityFilterChain` belong to Servlet method/HTTP configuration; do not substitute them literally for `@EnableReactiveMethodSecurity` + `ServerHttpSecurity` in WebFlux.
- SpEL `authentication.name` is the username verified by security filters, never read from client input.
- Expressions referencing `returnObject` must rely on real JavaBean getters/properties or result types supported by your Spring Security version.

If a custom update method returns `Mono<Void>`, design **pre-authorization** instead of trying to inspect an empty return value.

## 5. Typical side effects that post-checks cannot undo

### 5.1. Committed database UPDATE/DELETE

```text
POST /orders/42/approve (Alice)
  -> repository.update(42, "APPROVED")
  -> DB changes / may commit
  -> Mono emits Order(id=42, owner="bob")
  -> @PostAuthorize("returnObject.owner == authentication.name")
  -> Alice is not Bob -> deny
  -> HTTP 403

Possible outcome:
  HTTP client does not receive the order
  HOWEVER order 42 is already in APPROVED state
```

The keyword is **may**: if the same reactive transaction actually wraps the post-check and rolls back when the denial signal reaches the transaction boundary, uncommitted DB writes may roll back. Yet never assume that happens merely because `@Transactional` appears in source code. Verify commit timing, advisor order, and transaction propagation with tests.

### 5.2. Emails, webhooks, push notifications

If a method calls `emailSender.send(...)`, returns a receipt, and the post-check then denies, the email may already have been sent. There is no "email rollback". Authorize **before enqueueing/sending**, and to send only upon successful DB commit, use an outbox/worker with explicit policies and idempotency.

### 5.3. Kafka and message brokers

An event acknowledged by a broker can already be consumed by other services even if the HTTP handler ends up receiving `AccessDeniedException`. Never publish before verifying permissions and transaction decisions. For post-commit events, design idempotency/retry/outbox rather than publishing eagerly and hoping denial recalls the event.

### 5.4. Payments and external systems

A `WebClient` call causing a payment gateway to create a charge is not undone because Spring Security refuses to return the receipt. Money transfers, privilege grants, shipments, and reservations need pre-checks, business rules, idempotency keys, auditing, and dedicated compensating workflows where appropriate. `Mono.error(AccessDeniedException)` is not a refund command.

### 5.5. Caches, logs, and observability

An operator upstream of post-authorization might call `doOnNext(item -> cache.put(...))` or log sensitive objects. Even if post-authorization later denies, data may remain in the cache/logs. Cache keys must include user/tenant/ACL where needed, and never log passwords, bearer tokens, session IDs, or sensitive payloads. Do not assume that because no HTTP body was sent, no data was processed.

## 6. Safer design: check beforehand and at the mutation site

Proper mindset for mutating methods:

```text
Verified Authentication
    |
    v
Pre-authorization by action + principal + args
    |
    v
Repository fetches ownership/tenant/ACL from trusted source
    |
    v
Conditional UPDATE/DELETE or atomic transaction
    |
    +-- affectedRows == 0 -> do not proceed with effects
    |
    v
Write outbox event in transaction if needed
    |
    v
COMMIT
    |
    v
Worker safely/idempotently publishes external effect
```

### 6.1. SQL protecting the resource at update time

```sql
UPDATE orders
SET status = :new_status
WHERE id = :order_id
  AND tenant_id = :trusted_tenant
  AND owner_id = :authenticated_user_id
  AND status = :expected_status;
```

This is **sample SQL with bound parameters**, not a standalone runnable repository implementation. `trusted_tenant` and `authenticated_user_id` must be derived from trusted identity and server-side policy, **never** read straight from an `X-User` header or client-controlled query parameter. If affected row count is 0, publish no events and never assume success; choose 403/404/conflict per security policy while avoiding resource enumeration.

### 6.2. TOCTOU: even pre-checks are not enough

*Time of check / time of use*: a user holds permission at t0 yet loses it before the update at t1. Even when `@PreAuthorize` ran properly, if the service relies solely on the stale check it can perform an unauthorized write. To mitigate races:

1. Check ACLs from authoritative data.
2. During mutations, include tenant/owner/version predicates in SQL or use proper transactions/locking.
3. Check affected rows/optimistic version rather than blindly assuming success.
4. For ultra-sensitive permissions, re-evaluate policy close to commit.
5. Support idempotency for retries and maintain audit trails.

### 6.3. Can a reactive transaction roll back a post-check failure?

The answer is **configuration-dependent**. Spring R2DBC and `TransactionalOperator` manage transactions via Reactor Context. Rollback depends on whether `@PostAuthorize`'s denial signal reaches the transaction operator **before commit** and whether operations share that transaction.

Wrong assumptions:
- "`@PostAuthorize` always runs after DB commit, so it definitely never rolls back."
- "`@Transactional` guarantees 100% rollback whenever `@PostAuthorize` denies."

Tests must use real database transactions, assert before/after state, and observe commit timing and advisor ordering on your deployed version. Emails or external events outside the transaction still cannot be rolled back even if the DB reverts. Transactions guarantee atomicity within their boundary — **they are not an authorization tool replacing pre-checks**.

### 6.4. Transactional outbox for DB + events

```text
BEGIN DB TRANSACTION
  verify resource ACL / authorization
  UPDATE resource with tenant/owner/version condition
  INSERT outbox_event (if update is valid)
COMMIT

Outbox dispatcher:
  read committed event -> publish -> retry/idempotency
```

If the transaction rolls back, the outbox event is never committed for emission. The dispatcher publishes after commit with retries, while consumers enforce idempotency. This is a far more consistent real-world pattern than publishing directly to Kafka and relying on `@PostAuthorize` at the end.

## 7. Spring WebFlux Java 17+ project demonstrating side effects after 403

Let's build two service methods with the **exact same side effect** but different check ordering:

- `risky(owner)`: increments a counter inside `Mono.fromSupplier`, creates a receipt, and uses `@PostAuthorize` to compare `result.owner` with principal.
- `safe(owner)`: uses `@PreAuthorize` to compare the argument with principal, incrementing the counter only when allowed.

Each HTTP POST requires authentication and valid CSRF. The demo uses `AtomicInteger` to make effects immediately observable in tests; **never use such counters to store real transactions**.

### 7.1. Creating the project and dependencies

Use Spring Initializr with Java 17+, Spring Boot 3.x, Gradle (Groovy DSL), and dependencies **Spring Reactive Web**, **Spring Security**, **Spring Boot Starter Test**, and **Spring Security Test**.

Keep the Spring Boot plugins, repositories, dependency management, and Java toolchain generated by Initializr. Corresponding `dependencies` block in `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

This is the **`dependencies` block**, not the entire `build.gradle`. Do not add `spring-boot-starter-web`: when both MVC and WebFlux starters exist, Spring Boot 3.x usually picks Servlet MVC for the inbound stack.

Layout:

```text
src/main/java/demo/sideeffects/
  SideEffectsApplication.java
  SecurityConfig.java
  OperationService.java
  OperationController.java
src/test/java/demo/sideeffects/
  SideEffectSecurityTests.java
```

### 7.2. Application entry point

File `src/main/java/demo/sideeffects/SideEffectsApplication.java`:

```java
package demo.sideeffects;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SideEffectsApplication {
    public static void main(String[] args) {
        SpringApplication.run(SideEffectsApplication.class, args);
    }
}
```

### 7.3. WebFlux security and reactive method security

File `src/main/java/demo/sideeffects/SecurityConfig.java`:

```java
package demo.sideeffects;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class SecurityConfig {

    @Bean
    public SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health").permitAll()
                .pathMatchers(HttpMethod.POST, "/ops/**").authenticated()
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    public MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("bob-pass"))
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(alice, bob);
    }
}
```

Explanation:
- `@EnableReactiveMethodSecurity` enables method advisors on Spring-managed beans.
- HTTP security on `/ops/**` requires only a logged-in user. The owner rule is **method-level security** to illustrate ordering.
- `httpBasic` supplies demo credentials. Real applications must use HTTPS; HTTP Basic only Base64-encodes credentials in headers without protecting transport.
- `formLogin` is disabled so API tests receive 401 instead of an HTML redirect when unauthenticated.
- **CSRF is not disabled**; POST requires a valid token in the default config. In section 8, `WebTestClient.mutateWith(csrf())` provides the token via Spring Security test infrastructure.
- The in-memory user store and sample passwords are for learning only; passwords are stored as encoded hashes, never use this data in production.

### 7.4. Service containing a controlled side effect

File `src/main/java/demo/sideeffects/OperationService.java`:

```java
package demo.sideeffects;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OperationService {

    private final AtomicInteger effects = new AtomicInteger();

    public static final class Receipt {
        private final String owner;
        private final int sequence;

        public Receipt(String owner, int sequence) {
            this.owner = owner;
            this.sequence = sequence;
        }

        public String getOwner() {
            return owner;
        }

        public int getSequence() {
            return sequence;
        }
    }

    @PostAuthorize("returnObject.owner == authentication.name")
    public Mono<Receipt> risky(String owner) {
        return Mono.fromSupplier(() -> {
            int sequence = effects.incrementAndGet();
            return new Receipt(owner, sequence);
        });
    }

    @PreAuthorize("#p0 == authentication.name")
    public Mono<Receipt> safe(String owner) {
        return Mono.fromSupplier(() -> {
            int sequence = effects.incrementAndGet();
            return new Receipt(owner, sequence);
        });
    }

    public int effectCount() {
        return effects.get();
    }

    // For JUnit tests, do not expose as an HTTP endpoint.
    public void resetForTests() {
        effects.set(0);
    }
}
```

This is a complete Java class. `Receipt` has `getOwner()`, so SpEL can read JavaBean property `returnObject.owner`. `@PostAuthorize` checks after `risky` builds the result; `safe`'s `@PreAuthorize` checks the argument before allowing the method to execute.

With principal Alice:
- `risky("bob")`: the supplier increments the counter **and** returns Bob's Receipt; post-authorization denies it. The side effect remains.
- `safe("bob")`: pre-check sees owner does not match principal and prevents the method from running; counter stays unchanged.
- `safe("alice")`: permitted, counter increments, and response contains Receipt.
- `risky("alice")`: post-check permits; counter increments and Receipt returns to caller.

This **illustrates the design flaw using a non-transactional side effect**, not proof that all DB transactions fail to roll back. In production never let clients specify an owner and trust it: check real resource ACLs.

### 7.5. Controller returns the publisher without manual subscription

File `src/main/java/demo/sideeffects/OperationController.java`:

```java
package demo.sideeffects;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class OperationController {

    private final OperationService service;

    public OperationController(OperationService service) {
        this.service = service;
    }

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("ok");
    }

    @PostMapping("/ops/risky/{owner}")
    public Mono<OperationService.Receipt> risky(
            @PathVariable String owner) {
        return service.risky(owner);
    }

    @PostMapping("/ops/safe/{owner}")
    public Mono<OperationService.Receipt> safe(
            @PathVariable String owner) {
        return service.safe(owner);
    }
}
```

The controller invokes the injected `OperationService` bean so calls traverse the Spring AOP proxy. Never call `subscribe()` manually in controllers or services; WebFlux subscribes to the returned publisher. Direct calls from one method to another in the **same instance**, such as `this.safe(...)`, can bypass the proxy and skip annotations in proxy-based Spring AOP.

### 7.6. Expected HTTP results with valid CSRF

| Request | Authorization | Expected HTTP | Side effect |
|---|---|---:|---|
| Alice POST `/ops/risky/alice` | Post-check passes | 200 | Counter +1 |
| Alice POST `/ops/risky/bob` | Post-check denies | 403 | **Counter +1** |
| Alice POST `/ops/safe/alice` | Pre-check passes | 200 | Counter +1 |
| Alice POST `/ops/safe/bob` | Pre-check denies | 403 | **Counter unchanged** |
| Anonymous POST `/ops/safe/alice` | Unauthenticated | 401 via HTTP Basic | None |
| Alice POST missing CSRF | Blocked by CSRF filter | 403 | None |

**The same 403 status can originate from two distinct places**: missing CSRF or method denial. To test post-authorization, you must send a valid CSRF token so the request reaches the service.

### 7.7. Running the demo

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Check the public route:

```bash
curl -i http://localhost:8080/health
```

Expected HTTP 200, body:

```text
ok
```

A `curl` POST missing a CSRF token can receive 403 before method-level checks run. Do not disable CSRF just to build a "side-effect demo"; Spring Security tests in section 8 attach the token properly.

## 8. WebTestClient tests: 403 does not mean side effects = 0

File `src/test/java/demo/sideeffects/SideEffectSecurityTests.java`:

```java
package demo.sideeffects;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class SideEffectSecurityTests {

    @Autowired
    ApplicationContext context;

    @Autowired
    OperationService service;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        service.resetForTests();
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicHealthWorks() {
        client.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");

        assertEquals(0, service.effectCount());
    }

    @Test
    void postDenyDoesNotUndoSideEffect() {
        client.mutateWith(csrf())
            .post().uri("/ops/risky/bob")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isForbidden();

        assertEquals(1, service.effectCount());
    }

    @Test
    void preDenyPreventsSideEffect() {
        client.mutateWith(csrf())
            .post().uri("/ops/safe/bob")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isForbidden();

        assertEquals(0, service.effectCount());
    }

    @Test
    void allowedPreCheckRunsOnce() {
        client.mutateWith(csrf())
            .post().uri("/ops/safe/alice")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.owner").isEqualTo("alice")
            .jsonPath("$.sequence").isEqualTo(1);

        assertEquals(1, service.effectCount());
    }

    @Test
    void allowedPostCheckRunsOnce() {
        client.mutateWith(csrf())
            .post().uri("/ops/risky/alice")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.owner").isEqualTo("alice");

        assertEquals(1, service.effectCount());
    }

    @Test
    void anonymousCannotCallMutation() {
        client.mutateWith(csrf())
            .post().uri("/ops/safe/alice")
            .exchange()
            .expectStatus().isUnauthorized();

        assertEquals(0, service.effectCount());
    }

    @Test
    void missingCsrfPreventsPost() {
        client.post().uri("/ops/safe/alice")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isForbidden();

        assertEquals(0, service.effectCount());
    }
}
```

This is a JUnit 5 class using the WebFlux test context. `WebTestClient.bindToApplicationContext(context).apply(springSecurity())` attaches security filters to the mock server. `mutateWith(csrf())` supplies a CSRF token via Spring Security **test support**; real clients must obtain tokens/sessions per protocol rather than forging arbitrary tokens.

**Two core assertions**:

- `postDenyDoesNotUndoSideEffect`: HTTP 403 **and** counter = 1, proving post-authorization does not undo a non-transactional side effect.
- `preDenyPreventsSideEffect`: HTTP 403 **and** counter = 0, proving pre-authorization blocks work in this case.

In tests, `@BeforeEach` resets the counter each run. If tests run in parallel or share an `ApplicationContext` across classes, avoid races between measurements; real production tests should use isolated fixtures, test containers, or controlled test doubles.

Run:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Expect **7 tests** on the presented configuration. This is the **expected result from code**, not a claim that Gradle was executed. If discrepancies arise due to versions or test setup, inspect the filter chain, CSRF, AOP proxy, actual HTTP response, user store data, and whether the `Mono` was actually subscribed. Never change expected 403 to 200 just to turn tests green.

### 8.1. Production mutation tests must assert real state

Beyond HTTP statuses, tests must verify the following per endpoint:

- Database row and version remain unchanged when permissions are lacking.
- No new outbox event is inserted when conditional SQL update rejects.
- No unintended Kafka events, emails, webhooks, or payment calls occur.
- Caches do not store unauthorized data or leak other tenants' data.
- Retries/idempotency do not duplicate side effects.
- Concurrent permission revocation leaves no unauthorized write window.
- Streams do not emit sensitive elements before authorization.
- Logout, session expiry, and role updates alter permissions as expected.

## 9. Limits of rollback and cancellation

### 9.1. @Transactional does not automatically solve security ordering

With reactive transactions, managers like `R2dbcTransactionManager`/`TransactionalOperator` use Reactor Context; operations participate when composed properly inside the transaction publisher/boundary. If `@PostAuthorize`'s denial signal reaches the transaction operator before commit, DB writes can roll back. If the transaction committed prior to the post-check, rollback cannot be assumed. `@Transactional`, advisors, ordering, and resource boundaries dictate behavior.

**Never jump to an absolute conclusion**. Test DB state, transaction commit/rollback, and advisor ordering in your exact application version. Even if the DB rolls back, emails, webhooks, Kafka messages, or background tasks outside the transaction may still have happened.

### 9.2. Cancellation is not an undo button

A browser closing a tab or a subscriber cancelling does not mean in-flight HTTP calls, DB commits, emails, or messages automatically roll back. A `Mono.fromCallable` or detached task can run to completion; reactive I/O supporting cancellation may stop, yet outcomes depend on when external systems processed the request. Mutations require idempotency/compensation and independent state verification.

### 9.3. Streaming responses may already be committed

If a `Flux` flushes a couple of elements before emitting an error, the client may already have received data bytes. HTTP status/headers may already be committed, preventing the server from changing the whole response to 403. Guard at the source and authorize **before the first emission**, never relying on late post-checks to retract bytes the client already read.

## 10. Common pitfalls

### 10.1. Self-invocation bypasses AOP proxies

```java
// Buggy snippet: two methods in the same class, direct call via this.
public Mono<Receipt> entry(String owner) {
    return this.secured(owner);
}

@PreAuthorize("#p0 == authentication.name")
public Mono<Receipt> secured(String owner) {
    return repository.update(owner);
}
```

If calls bypass the Spring AOP proxy, the annotation on `secured` may not run. Invoke an injected bean, split services, or design appropriate proxies and test. Never assume an annotation runs merely because it exists in source code.

### 10.2. Manual `subscribe()` for fire-and-forget

```java
// Buggy snippet: email is detached from the returned publisher.
emailSender.send(user).subscribe();
return repository.save(item);
```

The side effect runs on a detached subscription outside the same error, cancellation, context, and authorization lifecycle. Even if a post-check denies, the email can still be sent. Compose publishers, authorize before enqueuing, and for true background work use queues/outboxes with proper permissions, retries, TTLs, and idempotency.

### 10.3. Using blocking repositories in reactive services

Calling `jdbcRepository.save(...)` synchronously on the Netty event loop stalls threads. If you cannot migrate to R2DBC yet, wrap blocking parts in `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` **with concurrency bounds** — that does not make blocking non-blocking. And never assume switching schedulers reverses post-check side effects.

### 10.4. Relying on @PostFilter for overly broad queries

Results get filtered afterward while the DB still scans every tenant; pagination, counts, latency, and side-channels break. Query tenant-scoped directly in the DB, check ACLs in the service, and add post-filtering only as defense-in-depth for small sets.

### 10.5. Confusing CSRF 403 with authorization 403

A POST missing a CSRF token can be blocked **before** the controller, so `counter = 0` does not prove `@PreAuthorize` ran. In tests, pass `csrf()` properly to send requests through the filter, then test the method-deny branch independently.

### 10.6. Trusting client-supplied returnObject values

If a method simply returns an object built from a client-supplied owner, `@PostAuthorize("returnObject.owner == authentication.name")` checks the wrong data source. Owners in results must tie to an **authoritative resource**; even read-only post-checks must rely on trustworthy data.

## 11. Mechanism selection table

| Operation type | Primary check | Role of post-check |
|---|---|---|
| Read single object | Principal/tenant first, ACL-scoped query | Defense-in-depth on returned object |
| List multiple objects | Repository `WHERE` owner/tenant, proper pagination | Optional PostFilter, never replaces query |
| Create object | PreAuthorize action/quota/tenant, transaction | Never use as initial permission gate |
| Update/delete | PreAuthorize + conditional SQL owner/version | Does not block already-committed writes |
| Send email/SMS | Authorize before send/enqueue | Does not recall emails |
| Payment/transfer | Authentication, authorization, limits, idempotency | Does not auto-refund |
| Publish Kafka event | Authorize, transaction + outbox | Does not delete emitted events |
| Streaming response | Authz before emit, query/record-level ACL | Does not recall sent bytes |
| Cache personal data | Pre-check + cache key by principal/tenant | Does not automatically purge upstream caches |

## 12. Exercises and answers

**Exercise 1.** Alice calls a method with `@PostAuthorize("returnObject.owner == authentication.name")`. The method updated Bob's record and returned `Receipt(owner=Bob)`. The client receives 403. Is the database guaranteed unchanged?

**Answer:** No. Side effects may have committed before the post-check. 403 only indicates access denied at the return boundary; assert state and design pre-authorization/conditional DB writes.

**Exercise 2.** Why is `@PreAuthorize("#p0 == authentication.name")` still insufficient if `#p0` is a client-supplied owner?

**Answer:** Real ownership/tenant/ACLs must be verified from a trusted source. Clients can declare their own username for someone else's resource. Use lookups + conditional SQL or row-level security.

**Exercise 3.** `@PostFilter` returns 25 records while the query scanned 10,000 records. Did the server avoid reading the 9,975 unauthorized records?

**Answer:** No. Filtering results after querying does not alter DB predicates and can cause high load, broken pagination, and upstream side effects.

**Exercise 4.** In the demo, Alice calls `risky("bob")`, receives HTTP 403, and counter = 1. Is this a Spring Security bug?

**Answer:** No, it is the expected consequence of a post-check-only design: Spring Security prevents returning the result yet does not automatically undo already-executed side effects.

**Exercise 5.** Should you use `@PostAuthorize` based on `returnObject.owner` to protect a `Mono<Void>` DELETE method?

**Answer:** No. `Mono<Void>` has no owner object to inspect; check permissions before DELETE and include owner/tenant predicates in the statement.

**Exercise 6.** A reactive transaction rolls back the DB when post-authorization denies, yet an email was sent. Is the email rolled back?

**Answer:** No. Email is an external system outside the DB transaction. Authorize before sending and use an outbox/compensation where appropriate.

**Exercise 7.** Why can `this.securedMethod()` bypass `@PreAuthorize`?

**Answer:** Internal calls normally do not pass through the Spring AOP proxy. You need a Spring-managed bean boundary and integration tests proving annotations are enforced.

**Exercise 8.** What is missing from a test that asserts only `expectStatus().isForbidden()` on a mutating POST?

**Answer:** It must also verify DB state is unchanged, no events/emails fired, caches were not written, and counters/side effects stayed untouched. Protecting a system means protecting state, not just HTTP responses.

**Exercise 9.** A `Flux` response flushed 2 records and then the third triggered an authorization denial. Can the first 2 records be retracted?

**Answer:** No. HTTP bytes already sent cannot be recalled. Authorize before streaming and scope queries at the source.

**Exercise 10.** When should a transactional outbox event be created?

**Answer:** Only after permissions and resource update conditions succeed, **inside the same DB transaction** as the update. A dispatcher publishes after commit with retries and idempotency.

## 13. Pre-production review checklist

- [ ] Side-effecting methods never rely solely on `@PostAuthorize`.
- [ ] `@PreAuthorize`/policy services genuinely execute through Spring AOP proxies.
- [ ] Principals, tenants, owners, and ACLs come from trusted identities and databases, never unverified client inputs.
- [ ] SQL `UPDATE`/`DELETE` includes owner/tenant/version predicates and checks affected row counts.
- [ ] Reactive transaction boundaries and rollback behavior are **tested**, not guessed.
- [ ] External emails, Kafka events, payments, and API calls never fire before authorization; outbox/idempotency/compensation used as required.
- [ ] No manual `subscribe()` or `block()` in reactive handlers/methods.
- [ ] `@PostFilter` never substitutes for ACL queries or breaks pagination.
- [ ] Never rely on `returnObject` for mutations returning `Mono<Void>` or empty publishers.
- [ ] Streaming HTTP responses are authorized before the first emission.
- [ ] Tests verify HTTP status **and** state in DB/caches/events/side effects, including denial cases.
- [ ] Tests cover CSRF, anonymous 401, authenticated 403, and authorized 200.
- [ ] Tested race conditions, retries, idempotency, permission revocation, errors, and cancellation.
- [ ] Logs contain no tokens, passwords, session IDs, or unauthorized data.
- [ ] Authorization exceptions are never turned into HTTP 200 by overly broad fallbacks.

## 14. Technical summary

```text
@PreAuthorize
   Authentication + arguments -> allow / deny
   deny -> prevents protected method/work from running

@PostAuthorize
   Publisher is subscribed
   -> upstream may already have run side effects
   -> emits returnObject
   -> post-check allow / deny
   deny -> does not return result, DOES NOT automatically roll back external effects

@PostFilter
   -> filters elements already fetched/emitted upstream
   -> DOES NOT replace query scoping / resource-level ACL

Safe for mutations
   -> pre-check
   -> authoritative ACL/tenant in repository
   -> conditional UPDATE/DELETE + transaction
   -> outbox/idempotency for events and external APIs
   -> test real state alongside HTTP status
```

**Key sentence to remember:** *"Not receiving the result" is completely different from "not executing the action."* `@PostAuthorize` guards the right to **receive a result**, not the right to **perform a mutation**. Sensitive actions must be authorized before causing side effects and enforced where data is mutated.

## Official documentation

- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security — Reactive Method Security Tests](https://docs.spring.io/spring-security/reference/reactive/test/method.html)
- [Spring Security — PostAuthorize](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/prepost/PostAuthorize.html)
- [Spring Security — PreAuthorize](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/prepost/PreAuthorize.html)
- [Spring Security — PostFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/prepost/PostFilter.html)
- [Spring Framework — Reactive Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
