# Controlling Execution Order Between Security, Transactions, and Reactive Chains

> **Topic:** Spring Security - reactive · **Group:** Method Authorization

## 1. Objectives

This lesson explains how to coordinate `@PreAuthorize`, `@PostAuthorize`, Spring AOP, `ReactiveSecurityContextHolder`, `@Transactional`, `TransactionalOperator`, and Reactor publishers to avoid mutating data before checking permissions, avoid committing when a business step fails, and avoid losing security context when switching threads.

After studying this lesson, you must be able to explain **three distinct moments in time**: when the Java method is called through a proxy; when the publisher is subscribed to; and when the R2DBC transaction commits or rolls back. You must also be able to write tests verifying that denied requests do not modify the database, valid requests commit both the UPDATE and audit, and an error between two SQL operations triggers a rollback.

## 2. Illustrative order approval rules

The order approval workflow requires:
- Actor is authenticated, holding both `ROLE_APPROVER` and `SCOPE_orders.approve`.
- Order belongs to a tenant the actor is allowed to operate on.
- Order is currently `PENDING`.
- Approver differs from the order creator (four-eyes rule).
- When valid, UPDATE the order status and INSERT an audit record **in the same transaction**.

Test data: `o-100` belongs to tenant `acme`, creator `alice`; `o-200` belongs to `beta`; `o-300` belongs to `acme`, creator `reviewer`. Actor `reviewer` holds `TENANT_acme` plus the required role and scope. `reviewer` can approve `o-100`, yet cannot cross tenants to `o-200` or self-approve `o-300`.

~~~mermaid
flowchart TD
  A["Subscriber / HTTP request"] --> B["Method security proxy"]
  B --> C{"@PreAuthorize role + scope?"}
  C -->|"No"| D["AccessDenied; no write"]
  C -->|"Yes"| E["Transactional reactive publisher"]
  E --> F["SELECT order + check tenant/status/creator"]
  F -->|"Insufficient permissions"| G["onError → rollback"]
  F -->|"Valid"| H["Conditional UPDATE order"]
  H --> I["INSERT approval_audit"]
  I -->|"Success"| J["onComplete → commit"]
  I -->|"Error"| G
~~~

## 3. Distinguishing three layers of ordering

| Layer | Tools | Key things to remember |
| --- | --- | --- |
| Spring AOP | `@PreAuthorize`, `@PostAuthorize`, `@Transactional` | Advisors run before/after the method; the method normally only returns a publisher |
| Reactor | `Mono.defer`, `flatMap`, `then`, `contextWrite` | Cold publishers execute upon subscription, not when constructed |
| R2DBC transaction | `ReactiveTransactionManager`, `TransactionalOperator` | Wraps SQL subscribed within the same context; commits on success, rolls back on error |

For example, `Mono<String> task = service.approve("o-100")` does not mean SQL has already executed. However, synchronous Java code placed **outside** the `Mono` (e.g., `sendEmailImmediately()` before `return Mono.just(...)`) still runs when the method is called. Thus **returning a `Mono` does not automatically make every side effect lazy**.

## 4. Method security before and after operations

Enable `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` on a Spring configuration class. `@PreAuthorize` checks before allowing the method to execute; `@PostAuthorize` checks based on the produced result, suited for read-only data authorization. Once a method has run an `UPDATE` or called an external API, an `AccessDeniedException` from post-authorization **does not prove side effects were rolled back**.

The right policy for writes is: check roles/scopes **before the use case**, check tenant/creator/status **before UPDATE and close to the data**, and wrap the UPDATE/audit inside the same transaction. Never place two annotations on the same method and infer an implicit commit order.

Spring reactive method security relies on AOP and Reactor Context. Calling `this.securedMethod()` or manually instantiating `new Service()` can bypass the proxy. Methods must be invoked through Spring bean proxies and tested via `@Autowired`.

## 5. Reactive context and transactions

`ReactiveSecurityContextHolder.getContext()` retrieves `Authentication` from the subscription's Reactor Context. Reactive transactions use Reactor Context to attach the connection and transaction synchronization. Both use the same propagation mechanism, yet **the two context entries do not replace each other**.

~~~java
public Mono<String> currentName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
}
~~~

In tests you can use `publisher.contextWrite(ReactiveSecurityContextHolder.withAuthentication(auth))`. Never rely on Servlet's ThreadLocal `SecurityContextHolder.getContext()` in WebFlux; never call `subscribe()` inside services or spawn detached threads/callbacks expecting the same SecurityContext/transaction.

Imperative transactions use `PlatformTransactionManager` and blocking JDBC/JPA; reactive transactions use `ReactiveTransactionManager` with R2DBC. With reactive `@Transactional`, the method must return a Publisher, the transaction executes upon subscription, and calls must go through the proxy. With `TransactionalOperator`, the publisher segment is wrapped explicitly via `work.as(tx::transactional)`.

## 6. Advisor order is not commit order

In Spring AOP, higher-precedence advisors run **earlier on method entry** and **later on exit**. Spring Security has `AuthorizationManagerBeforeReactiveMethodInterceptor`, `AuthorizationManagerAfterReactiveMethodInterceptor`, and `AuthorizationInterceptorsOrder`. Transaction advice can configure `@EnableTransactionManagement(order=...)`; default proxy mode is typically `Ordered.LOWEST_PRECEDENCE`.

~~~text
Advisor A: enter
  Advisor B: enter
    target method → returns Mono
  Advisor B: exit
Advisor A: exit

Subsequent subscription:
  Reactor Context → R2DBC → transaction terminal signal
~~~

**Never deduce COMMIT timing from annotation ordering in source code.** A method combining `@PreAuthorize`, `@Transactional`, and `@PostAuthorize` must be tested on your exact Spring version and advisor/publisher composition. A clean, easy-to-verify pattern is separating the security facade from the transactional writer, as in the project below.

## 7. Runnable Java 17+ Maven project

This lesson uses Spring Boot `3.3.13` (Spring Security 6.x) for the lab; the 3.3 branch is past OSS support, so new products should select a supported version. Tests invoke Spring beans and R2DBC H2 directly without needing an HTTP endpoint.

~~~text
reactive-secure-tx/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/securetx/
    │   │   ├── SecureTxApplication.java
    │   │   ├── TxConfig.java
    │   │   ├── ApprovalFacade.java
    │   │   └── ApprovalWriter.java
    │   └── resources/
    │       ├── application.yml
    │       ├── schema.sql
    │       └── data.sql
    └── test/java/demo/securetx/
        └── ApprovalFlowTest.java
~~~

### pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>reactive-secure-tx</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <properties><java.version>17</java.version></properties>
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
      <artifactId>spring-boot-starter-data-r2dbc</artifactId>
    </dependency>
    <dependency>
      <groupId>io.r2dbc</groupId>
      <artifactId>r2dbc-h2</artifactId>
      <scope>runtime</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
~~~

### SecureTxApplication.java

~~~java
package demo.securetx;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@SpringBootApplication
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class SecureTxApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecureTxApplication.class, args);
    }
}
~~~

### application.yml

~~~yaml
spring:
  r2dbc:
    url: "r2dbc:h2:mem:///securetx163?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
  sql:
    init:
      mode: always
~~~

### schema.sql

~~~sql
CREATE TABLE purchase_orders (
  id VARCHAR(32) PRIMARY KEY,
  tenant_id VARCHAR(32) NOT NULL,
  created_by VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL
);

CREATE TABLE approval_audit (
  id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  order_id VARCHAR(32) NOT NULL,
  actor VARCHAR(64) NOT NULL
);
~~~

### data.sql

~~~sql
INSERT INTO purchase_orders (id, tenant_id, created_by, status) VALUES
  ('o-100', 'acme', 'alice', 'PENDING'),
  ('o-200', 'beta', 'bob', 'PENDING'),
  ('o-300', 'acme', 'reviewer', 'PENDING');
~~~

The YAML/SQL files reside in `src/main/resources`. `DB_CLOSE_DELAY=-1` keeps the H2 in-memory database alive after connections close. Spring Boot's SQL initializer loads schema/data for the lab. Never use these SQL scripts in place of production migrations.

## 8. TxConfig: ReactiveTransactionManager → TransactionalOperator

File `src/main/java/demo/securetx/TxConfig.java`:

~~~java
package demo.securetx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Configuration
public class TxConfig {
    @Bean
    TransactionalOperator tx(ReactiveTransactionManager manager) {
        return TransactionalOperator.create(manager);
    }
}
~~~

Spring Boot configures `R2dbcTransactionManager` when a matching `ConnectionFactory` exists. `TransactionalOperator` does not create data or authorize on its own; it wraps a chosen publisher in a transaction using Reactor Context resources.

## 9. ApprovalFacade: blocking invalid roles and scopes early

File `src/main/java/demo/securetx/ApprovalFacade.java`:

~~~java
package demo.securetx;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ApprovalFacade {
    private final ApprovalWriter writer;

    public ApprovalFacade(ApprovalWriter writer) {
        this.writer = writer;
    }

    @PreAuthorize(
        "hasRole('APPROVER') and hasAuthority('SCOPE_orders.approve')")
    public Mono<String> approve(String id) {
        return writer.approveInsideTransaction(id, false);
    }
}
~~~

The facade only blocks coarse-grained permissions, unaware of record owner, tenant, or status. The writer still checks permissions again to guard against another adapter accidentally calling it directly, and runs all data-level checks inside the transactional publisher.

## 10. ApprovalWriter: check domain rules then UPDATE + audit atomically

File `src/main/java/demo/securetx/ApprovalWriter.java`:

~~~java
package demo.securetx;

import org.springframework.http.HttpStatus;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

record OrderRow(String id, String tenant, String creator, String status) {}

@Service
public class ApprovalWriter {
    private final DatabaseClient db;
    private final TransactionalOperator tx;

    public ApprovalWriter(DatabaseClient db, TransactionalOperator tx) {
        this.db = db;
        this.tx = tx;
    }

    public Mono<String> approveInsideTransaction(
            String id, boolean failAfterUpdate) {
        Mono<String> work = Mono.defer(() ->
            ReactiveSecurityContextHolder.getContext()
                .switchIfEmpty(Mono.error(
                    new AccessDeniedException("No security context")))
                .map(ctx -> ctx.getAuthentication())
                .flatMap(auth -> approveForActor(id, failAfterUpdate, auth))
        );
        return work.as(tx::transactional);
    }

    private Mono<String> approveForActor(
            String id, boolean failAfterUpdate, Authentication auth) {
        if (!auth.isAuthenticated()
                || !has(auth, "ROLE_APPROVER")
                || !has(auth, "SCOPE_orders.approve")) {
            return Mono.error(new AccessDeniedException("Denied"));
        }

        return db.sql(
            "SELECT id, tenant_id, created_by, status " +
            "FROM purchase_orders WHERE id = :id")
            .bind("id", id)
            .map((r, m) -> new OrderRow(
                r.get(0, String.class), r.get(1, String.class),
                r.get(2, String.class), r.get(3, String.class)))
            .one()
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(HttpStatus.NOT_FOUND)))
            .flatMap(order -> {
                boolean tenantOk = has(auth, "TENANT_" + order.tenant());
                boolean notCreator =
                    !order.creator().equals(auth.getName());
                boolean pending = "PENDING".equals(order.status());

                if (!tenantOk || !notCreator || !pending) {
                    return Mono.error(new AccessDeniedException("Denied"));
                }

                return db.sql(
                    "UPDATE purchase_orders SET status = 'APPROVED' " +
                    "WHERE id = :id AND status = 'PENDING'")
                    .bind("id", id).fetch().rowsUpdated()
                    .flatMap(updated -> {
                        if (updated != 1L) {
                            return Mono.error(new IllegalStateException(
                                "Concurrent modification"));
                        }
                        if (failAfterUpdate) {
                            return Mono.error(new IllegalStateException(
                                "Simulated audit failure"));
                        }
                        return db.sql(
                            "INSERT INTO approval_audit " +
                            "(order_id, actor) VALUES (:id, :actor)")
                            .bind("id", id)
                            .bind("actor", auth.getName())
                            .fetch().rowsUpdated()
                            .flatMap(inserted -> inserted == 1L
                                ? Mono.just("APPROVED")
                                : Mono.error(new IllegalStateException(
                                    "Audit failure")));
                    });
            });
    }

    private static boolean has(Authentication auth, String authority) {
        return auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .anyMatch(authority::equals);
    }
}
~~~

Upon subscription, the transaction wraps the entire `work`: obtaining `Authentication`, `SELECT`, domain checks, `UPDATE`, and `INSERT` audit. If an error occurs between `UPDATE` and audit, `onError` reaches the operator and rolls back. Only upon success does `onComplete` commit.

Subtle detail: the `UPDATE` includes `WHERE status='PENDING'` and checks `rowsUpdated()==1` to catch concurrent state changes. Real systems need appropriate transaction isolation, optimistic locking/versioning, and business-level idempotency handling.

## 11. Integration tests with StepVerifier and database

File `src/test/java/demo/securetx/ApprovalFlowTest.java`:

~~~java
package demo.securetx;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest
class ApprovalFlowTest {
    @Autowired ApprovalFacade facade;
    @Autowired ApprovalWriter writer;
    @Autowired DatabaseClient db;

    private Authentication actor(String name, String... permissions) {
        return UsernamePasswordAuthenticationToken.authenticated(
            name, null, AuthorityUtils.createAuthorityList(permissions));
    }

    private Authentication reviewer() {
        return actor("reviewer",
            "ROLE_APPROVER", "SCOPE_orders.approve", "TENANT_acme");
    }

    private Mono<String> as(Mono<String> mono, Authentication auth) {
        return mono.contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auth));
    }

    private String status() {
        return db.sql(
            "SELECT status FROM purchase_orders WHERE id = 'o-100'")
            .map((r, m) -> r.get(0, String.class))
            .one().block();
    }

    private long auditCount() {
        return db.sql(
            "SELECT COUNT(*) FROM approval_audit WHERE order_id = 'o-100'")
            .map((r, m) -> ((Number) r.get(0)).longValue())
            .one().block();
    }

    @BeforeEach
    void reset() {
        db.sql(
            "UPDATE purchase_orders SET status = 'PENDING' " +
            "WHERE id = 'o-100'")
            .fetch().rowsUpdated().block();
        db.sql("DELETE FROM approval_audit")
            .fetch().rowsUpdated().block();
    }

    @Test
    void missingScopeDoesNotWrite() {
        Authentication noScope =
            actor("reviewer", "ROLE_APPROVER", "TENANT_acme");
        StepVerifier.create(as(facade.approve("o-100"), noScope))
            .expectError(AccessDeniedException.class).verify();
        assertEquals("PENDING", status());
        assertEquals(0L, auditCount());
    }

    @Test
    void permittedActorCommitsBothWrites() {
        StepVerifier.create(as(facade.approve("o-100"), reviewer()))
            .expectNext("APPROVED").verifyComplete();
        assertEquals("APPROVED", status());
        assertEquals(1L, auditCount());
    }

    @Test
    void wrongTenantCannotWrite() {
        Authentication beta = actor("reviewer",
            "ROLE_APPROVER", "SCOPE_orders.approve", "TENANT_beta");
        StepVerifier.create(as(facade.approve("o-100"), beta))
            .expectError(AccessDeniedException.class).verify();
        assertEquals("PENDING", status());
        assertEquals(0L, auditCount());
    }

    @Test
    void creatorCannotApproveOwnOrder() {
        Authentication alice = actor("alice",
            "ROLE_APPROVER", "SCOPE_orders.approve", "TENANT_acme");
        StepVerifier.create(as(facade.approve("o-100"), alice))
            .expectError(AccessDeniedException.class).verify();
        assertEquals("PENDING", status());
    }

    @Test
    void auditFailureRollsBackUpdate() {
        StepVerifier.create(as(
            writer.approveInsideTransaction("o-100", true), reviewer()))
            .expectError(IllegalStateException.class).verify();
        assertEquals("PENDING", status());
        assertEquals(0L, auditCount());
    }

    @Test
    void missingContextIsDenied() {
        StepVerifier.create(facade.approve("o-100"))
            .expectError().verify();
        assertEquals("PENDING", status());
    }

    @Test
    void coldMonoDoesNotWriteBeforeSubscribe() {
        Mono<String> operation =
            as(facade.approve("o-100"), reviewer());
        assertEquals("PENDING", status());
        StepVerifier.create(operation)
            .expectNext("APPROVED").verifyComplete();
        assertEquals("APPROVED", status());
    }

    @Test
    void secondApprovalIsRejected() {
        StepVerifier.create(as(facade.approve("o-100"), reviewer()))
            .expectNext("APPROVED").verifyComplete();
        StepVerifier.create(as(facade.approve("o-100"), reviewer()))
            .expectError(AccessDeniedException.class).verify();
        assertEquals(1L, auditCount());
    }
}
~~~

Tests execute through `@Autowired` Spring beans, not manually `new`-constructed objects. `contextWrite` supplies the subscriber's `SecurityContext`. `block()` is used solely on the JUnit test thread to inspect DB state, never inside WebFlux services.

| Test | Publisher | Final DB state |
| --- | --- | --- |
| Missing scope | AccessDeniedException | PENDING, 0 audits |
| Valid role/scope/tenant | APPROVED then complete | APPROVED, 1 audit |
| Wrong tenant | AccessDeniedException | PENDING, 0 audits |
| Creator self-approval | AccessDeniedException | PENDING |
| Error between UPDATE and audit | IllegalStateException | PENDING, 0 audits |
| Missing Authentication | onError | PENDING |
| Unsubscribed Mono | No write yet | PENDING |
| Double approval | 2nd call denied | Only 1 audit |

Run `mvn clean test`. Expect **8 JUnit tests PASS**. These test method security/transactions; they do not yet verify HTTP statuses, JWT signatures, or CSRF on an actual endpoint.

## 12. How do @Transactional and TransactionalOperator differ?

Reactive `@Transactional` can wrap a publisher returned by a bean method when a `ReactiveTransactionManager` is configured. Standalone syntax example (without authorization, not exposed as an API):

~~~java
package demo.securetx;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
class TransactionalExample {
    private final DatabaseClient db;
    TransactionalExample(DatabaseClient db) { this.db = db; }

    @Transactional
    public Mono<Long> markApproved(String id) {
        return db.sql(
            "UPDATE purchase_orders SET status='APPROVED' " +
            "WHERE id=:id AND status='PENDING'")
            .bind("id", id).fetch().rowsUpdated();
    }
}
~~~

The annotation relies on Spring AOP proxies and is vulnerable to self-invocation; the operator does not require a proxy to create a transaction, yet can be scoped incorrectly. **Do not mix both mechanisms in the same workflow** without explicitly verifying propagation. For real transactional methods, keep all SQL and domain checks inside the returned publisher without manual `subscribe()` or blocking JDBC managers.

## 13. Mistakes with AOP, publishers, and rollback

### Self-invocation

~~~java
@Service
class WrongService {
    public Mono<String> process(String id) {
        return this.protectedMethod(id);
    }

    @PreAuthorize("hasRole('APPROVER')")
    @Transactional
    public Mono<String> protectedMethod(String id) {
        return Mono.just("ok");
    }
}
~~~

Buggy illustration: calls via `this` usually bypass method security/transaction proxies. Separate facade and writer as in the runnable project, and test through Spring beans.

### Nested subscribe

~~~java
public Mono<String> wrong(String id) {
    repository.update(id).subscribe();
    return Mono.just("APPROVED");
}
~~~

This is pseudocode with a hypothetical repository. `UPDATE` runs in a separate subscription, risking lost `SecurityContext`, transactions, error propagation, and ordering. Instead, return the composed publisher chained with `flatMap`/`then` and let the lifecycle-owning layer subscribe.

### Wrapping only UPDATE, omitting audit

~~~java
Mono<Long> update = repository.update(id).as(tx::transactional);
return update.then(repository.insertAudit(id));
~~~

Wrong because the audit runs outside the already-committed transaction. Proper scope placement:

~~~java
Mono<String> work = repository.update(id)
    .then(repository.insertAudit(id))
    .thenReturn("APPROVED");
return work.as(tx::transactional);
~~~

The snippets above are **operator models**, not runnable classes. The real project in section 10 wraps domain checks and both SQL statements.

### Swallowing errors inside a transaction

~~~java
Mono<String> risky = repository.update(id)
    .then(repository.insertAudit(id))
    .onErrorResume(ex -> Mono.just("ignored"))
    .as(tx::transactional);
~~~

If an audit error is converted to completion **before the transaction boundary**, the transaction can commit the `UPDATE`. Let errors reach the transaction operator to roll back, then map errors to responses outside `tx`. Never use `Mono.empty()` for denial if a downstream `then(otherWrite)` would treat completion as success.

## 14. Retries, cancellation, and non-DB side effects

- `onError` reaching the transaction: rolls back. `onComplete`: commits when conditions hold.
- `cancel` (e.g., `take(1)` on a Flux) can cause reactive transactions to roll back in modern Spring Framework; never assume partial consumption implies commit.
- `retryWhen` re-subscribes to the publisher, potentially repeating SQL and side effects. Design idempotency, optimistic locking, or unique event IDs.
- `timeout` and upstream cancellation can abort workflows; test against real DBs and drivers.
- `flatMap` can execute concurrently; when sequential ordering is needed, consider `concatMap` and proper transaction scoping.
- `publishOn` within the same Reactor pipeline does not lose context on its own; detached threads or manual `subscribe()` calls are the culprits.

A database transaction cannot recall an email or HTTP call sent prior to rollback. Use a **transactional outbox**: `UPDATE` order, `INSERT` audit, and `INSERT` outbox event inside the same DB transaction; post-commit, a worker publishes and consumers process event IDs idempotently. Never treat `send().subscribe()` as an after-commit event.

## 15. HTTP and data authorization in production

A real HTTP request adds a `SecurityWebFilterChain` to authenticate and populate Reactor `SecurityContext`. The controller calls the facade via Spring bean, the facade enforces `@PreAuthorize`, and the writer verifies tenant/status/owner and mutates atomically. Missing credentials usually return 401; authenticated lacking permissions returns 403; missing records may return 404; concurrency conflicts may return 409 per API contract. Direct Spring bean tests observe exceptions only, with no HTTP status.

With JWTs, verify signature, issuer, expiry, audience, and claim-to-authority mapping. Never trust client-sent tenants in headers or query params. With browser sessions/Basic, consider CSRF because browsers attach credentials automatically; never disable CSRF just to make POSTs work.

Users holding valid roles/scopes can still be denied if tenant or record state changed. Domain authorization must check close to the data rather than trusting stale session/token claims alone. For critical writes, add optimistic locking/isolation, bounded retries, and idempotency.

## 16. Diagnostic error matrix

| Symptom | Possibility | Fix |
| --- | --- | --- |
| Denied yet DB changed | Eager side effect / `@PostAuthorize` after commit | Pre-check, transactional domain policy, DB tests |
| Annotations not running | Method security not enabled, self-invocation | Test via `@Autowired` proxy |
| Empty context | ThreadLocal, nested subscribe, missing `contextWrite` | Reactor SecurityContext on right subscription |
| DB does not roll back | Transaction wraps wrong publisher, error swallowed | `TransactionalOperator` scope, propagate `onError` |
| Missing audit yet order APPROVED | `UPDATE` committed before audit | Wrap both in the same transaction |
| Duplicate approval | Missing status/version predicate | Conditional update, check `rowsUpdated` |
| Email sent despite DB rollback | External side effect not atomic with DB | Outbox/idempotency |
| Tests leak state | Fixtures not reset | `@BeforeEach` reset and DB readback |
| Timeout/policy store failure grants access | Fail-open | Fail closed, monitor |

**Investigation order:** called through proxy? → Authentication in Reactor Context? → pre-check blocked? → which publisher subscribed? → tx wraps the right operations? → error/cancel propagated to operator? → what did DB actually persist?

## 17. Exercises and checklist

**Exercise A:** create a `Mono` without subscribing; prove DB stays `PENDING`. After `StepVerifier` succeeds, DB becomes `APPROVED`.

**Exercise B:** move audit outside `work.as(tx)` in the lab, simulate an error, observe the rollback mismatch, then restore it.

**Exercise C:** add `onErrorResume` before the operator to swallow the error; test and explain when an invalid commit occurs.

**Exercise D:** call the protected method via `this`, demonstrate proxy bypass, then restore two beans.

**Exercise E:** test an actor with valid role/scope but wrong tenant, and an actor self-approving their own order. Neither may write.

**Exercise F:** test two concurrent approvals, add a version column or conditional update, and test idempotency.

**Exercise G:** create a transactional Flux cancelled with `take(1)`; inspect rollback/commit via DB tests.

**Exercise H:** add an outbox table for `OrderApproved` events and a post-commit publishing worker.

**Checklist:**
- [ ] Distinguish method invocation, subscription, and transaction terminal signals.
- [ ] Never use `@PostAuthorize` as a rollback guarantee.
- [ ] Invoke through Spring bean proxies, avoiding self-invocation.
- [ ] Never call `subscribe()` manually or run synchronous side effects before authorization.
- [ ] Use the proper `ReactiveTransactionManager` and cold publishers.
- [ ] Domain checks, `UPDATE`, and audit sit inside one transaction.
- [ ] Write negative tests and assert DB rollback when audit fails.
- [ ] Understand `onErrorResume`, retry, cancel, timeout, and outbox.
- [ ] Never confuse HTTP permissions with actual tenant/object permissions.

## 18. References

- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html): method-security advisors, Reactor Context.
- [Spring Security — AuthorizationInterceptorsOrder](https://docs.spring.io/spring-security/site/docs/6.3.9/api/org/springframework/security/authorization/method/AuthorizationInterceptorsOrder.html): interceptor ordering.
- [Spring Framework — Transaction Management Explained](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): reactive vs. imperative transactions.
- [Spring Framework — @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy mode, advisor order.
- [Spring Framework — TransactionalOperator](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): transaction scope and cancel semantics.
- [Spring Framework — R2DBC](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html): R2DBC connections.
- [Spring Boot — SQL Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): `schema.sql`/`data.sql`.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Reactor Context.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default, least privilege, object permissions.

**Conclusion:** The safe rule is blocking coarse permissions with `@PreAuthorize` before the use case; fetching and verifying business state right inside the transaction; chaining all atomic SQL into one publisher without nested subscriptions; letting errors reach `TransactionalOperator` to roll back; and asserting with DB readbacks rather than trusting HTTP statuses alone.