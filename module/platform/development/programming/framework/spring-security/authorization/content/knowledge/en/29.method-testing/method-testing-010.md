# Testing self-invocation, transactions, and method side effects

> **Context:** Spring Security – authorization, **Method Testing** group. This practice focuses on Spring Method Security based on Spring AOP proxies and declarative transactions (`@Transactional`), with examples in Spring Boot 3.x / Spring Security 6.x, Java 17+, JUnit 5. Notes in this lesson apply to standard JDBC transactions on the same thread; reactive/AspectJ mechanisms have different boundaries.

## 1. Objectives and claims to prove

When a service both checks privileges and writes data, a test that only verifies "an unauthorized user receives an error" is **not enough**. You must simultaneously prove:

1. **Calls genuinely go through the Spring proxy.** `@PreAuthorize` must execute before the method body, including when the method is called from another service. Calling `this.protectedMethod()` in the same bean can bypass advice.
2. **Transactions genuinely activate at the right boundary.** `@Transactional` must take effect when called through the proxy. Observe commit, rollback, and—if `REQUIRES_NEW` is used—the independence of the inner transaction.
3. **When access is denied, no unwanted business side effects occur.** Check record counts, repository invocations, and events/notifications, not just the exception type.
4. **Rollback has a limited scope.** The database can roll back while emails, HTTP requests, messages sent to external systems, or in-memory changes have already occurred.
5. **Tests do not accidentally hide bugs.** A test annotated with `@Transactional` itself can pre-open a transaction, making results differ from real-world service calls.

Crucial distinction: **access denied**, **business failure**, **DB rollback**, and **external side effects already emitted** are four separate observations requiring separate assertions.

## 2. Core mechanism: proxy, method security, and transactions

### 2.1. A call through the proxy vs. a call through `this`

When `@EnableMethodSecurity` is enabled, Spring Security registers Spring AOP interceptors. For example, `@PreAuthorize("hasRole('ADMIN')")` requires the `ROLE_ADMIN` authority. When a caller holds a reference to the Spring-managed bean, the general path is:

```text
Caller
  │
  ▼
Spring proxy  ──► check @PreAuthorize ──► transaction advice (if present)
  │                                            │
  └────────────────────────────────────────────▼
                                      target method body
                                               │
                                               ▼
                                    JDBC / repository / notification
```

The diagram above illustrates only two advice layers and **does not hardcode advice ordering**. Exact order depends on advisors/order and configuration. Pre-method checks with `@PreAuthorize` happen before allowing the method body to run; `@PostAuthorize` evaluates after the method body produces a result.

The self-invocation problem:

```java
@Service
public class WrongService {
    public void start() {
        this.adminOperation(); // call on target, does not go through proxy
    }

    @PreAuthorize("hasRole('ADMIN')")
    @Transactional
    public void adminOperation() {
        // A call from start() can bypass both security and transaction advice.
    }
}
```

- `caller -> wrongService.adminOperation()` through the Spring bean proxy: security and transaction advice have a chance to run.
- `caller -> wrongService.start() -> this.adminOperation()`: an internal call inside the target **does not re-enter the proxy**, so advice attached *specifically* to `adminOperation()` does not run.
- If `start()` was already called through a proxy and opened a transaction, code inside `adminOperation()` can still participate in the **existing** transaction. However, `adminOperation()`'s own transaction settings (such as `REQUIRES_NEW`, isolation, rollback rules) are still not applied due to self-invocation. Do not conclude "self-invocation never has a transaction" when an outer transaction exists.
- Class-based proxies (CGLIB) do not automatically fix self-invocation; private/final methods and calls during bean initialization also have interception limits. AspectJ weaving is a separate mechanism and must be configured explicitly.

**Preferred fix:** extract the protected method into **another Spring bean** and inject that bean into the facade. Self-injection or `AopContext.currentProxy()` can be used in special cases, but they increase coupling to Spring AOP and should not be the default choice.

### 2.2. Combining authorization and transactions

- `@PreAuthorize`: if privileges are insufficient, the method body does not run; suited to blocking write operations **before** side effects.
- `@PostAuthorize`: checks based on the result after the method body has already executed. For write methods, data/events **may already have changed** before denial; advisor ordering and commits can worsen the impact. Do not use `@PostAuthorize` as the sole gate for writes.
- `@Transactional` defaults to `REQUIRED` propagation: join an existing transaction, or create a new one if none exists. By default `RuntimeException`/`Error` triggers rollback; checked exceptions normally **do not** trigger rollback unless `rollbackFor` is set. Exception handling (such as catching and swallowing an exception) also affects the outcome.
- `REQUIRES_NEW` starts an independent physical transaction **when advice is actually triggered via proxy**; this transaction can commit even if the outer transaction rolls back. This is transactional semantics, not an authorization safeguard.

Pattern to avoid in write flows (illustrative snippet, not a standalone program):

```java
@PostAuthorize("returnObject.owner().equals(authentication.name)")
@Transactional
public Receipt createOrder(OrderRequest request) {
    orderRepository.save(/* order */);
    paymentGateway.charge(/* payment */);
    return /* receipt */;
}
```

If the `@PostAuthorize` condition fails, the method has already called the database and payment gateway. Never infer that throwing `AccessDeniedException` means all changes were undone. Check ownership/permissions **before writing** (for example `@PreAuthorize` or a check on a guarding bean) and design separate compensation/reliability mechanisms for external systems.

## 3. Minimum test matrix

| Scenario | Call point | Assertions required |
| --- | --- | --- |
| USER directly calls `@PreAuthorize("hasRole('ADMIN')")` method | Proxy | `AccessDeniedException`; DB and notifications unchanged |
| USER calls that method via `this` in the same bean | Self-invocation | Proves the flaw: method body **still runs**; protecting advice is bypassed |
| USER calls facade delegating to **another protected bean** | Through second bean's proxy | Denied; DB and notifications remain intact |
| ADMIN calls successfully | Through proxy | Transaction active and data committed |
| ADMIN writes DB then throws `RuntimeException` | Through proxy | DB rolls back |
| ADMIN writes DB, sends notification, then throws error | Through proxy | DB rolls back **but** notification is not automatically recalled |
| Code using `@PostAuthorize` to protect write | Through proxy | Verify side effect occurred **before** deny outcome; avoid treating deny as rollback guarantee |

The matrix is a behavioral specification. Unit-style tests calling `new Service()` or using `@InjectMocks` directly do not build AOP proxies, so they are insufficient to prove `@PreAuthorize`/`@Transactional` actually work.

## 4. Runnable Java 17+ integration test suite

The following example uses **real H2 + JdbcTemplate**, a fake notification gateway counting sends (simulating an effect outside the transaction), and `@WithMockUser` from Spring Security Test. Every test calls **an injected Spring bean**, never creating services with `new`.

In a Spring Boot 3.x Gradle module with managed dependency versions, add the required test dependencies (if a dependency is already present, do not declare it twice):

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-jdbc'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Create **one complete file** `src/test/java/example/security/MethodSecurityTransactionTest.java`:

```java
package example.security;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = MethodSecurityTransactionTest.TestApp.class)
class MethodSecurityTransactionTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity
    @EnableTransactionManagement
    @Import({
        VulnerableService.class,
        ProtectedService.class,
        SafeFacade.class,
        NotificationGateway.class
    })
    static class TestApp {
        // DataSource/JdbcTemplate/transaction manager come from Spring Boot
        // auto-configuration with H2 present on the test runtime classpath.
    }

    @Autowired JdbcTemplate jdbc;
    @Autowired VulnerableService vulnerable;
    @Autowired SafeFacade safeFacade;
    @Autowired NotificationGateway notifications;

    @BeforeEach
    void reset() {
        jdbc.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                label VARCHAR(80) NOT NULL
            )
            """);
        jdbc.update("DELETE FROM audit_log");
        notifications.reset();
    }

    private int rowCount() {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM audit_log", Integer.class);
    }

    // Buggy case: same bean calls this.guardedWrite().
    public static class VulnerableService {
        private final JdbcTemplate jdbc;

        public VulnerableService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public boolean invokeInternally() {
            return this.guardedWrite(); // BYPASSES guardedWrite()'s proxy
        }

        @PreAuthorize("hasRole('ADMIN')")
        @Transactional
        public boolean guardedWrite() {
            boolean txActive =
                TransactionSynchronizationManager.isActualTransactionActive();
            jdbc.update(
                "INSERT INTO audit_log(label) VALUES (?)", "vulnerable");
            return txActive;
        }
    }

    // Fake gateway: send count is NOT part of the H2 transaction.
    public static class NotificationGateway {
        private final AtomicInteger sent = new AtomicInteger();

        public void send() {
            sent.incrementAndGet();
        }

        public int count() {
            return sent.get();
        }

        public void reset() {
            sent.set(0);
        }
    }

    // Separate bean: caller must go through ProtectedService's proxy.
    public static class ProtectedService {
        private final JdbcTemplate jdbc;
        private final NotificationGateway notifications;

        public ProtectedService(
            JdbcTemplate jdbc, NotificationGateway notifications) {
            this.jdbc = jdbc;
            this.notifications = notifications;
        }

        @PreAuthorize("hasRole('ADMIN')")
        @Transactional
        public boolean writeAndNotify(boolean failAfterNotify) {
            boolean txActive =
                TransactionSynchronizationManager.isActualTransactionActive();

            jdbc.update(
                "INSERT INTO audit_log(label) VALUES (?)", "protected");
            notifications.send();

            if (failAfterNotify) {
                throw new IllegalStateException("business failure");
            }
            return txActive;
        }
    }

    public static class SafeFacade {
        private final ProtectedService protectedService;

        public SafeFacade(ProtectedService protectedService) {
            this.protectedService = protectedService;
        }

        public boolean execute(boolean fail) {
            return protectedService.writeAndNotify(fail);
        }
    }

    @Test
    @WithMockUser(roles = "USER")
    void selfInvocationBypassesMethodSecurityAndTransactionAdvice() {
        // Direct call on bean proxy: USER is blocked.
        assertThrows(
            AccessDeniedException.class, vulnerable::guardedWrite);
        assertEquals(0, rowCount());

        // Call via this inside the same bean: this proves the design flaw.
        boolean txActive = vulnerable.invokeInternally();
        assertFalse(txActive);        // No enclosing transaction.
        assertEquals(1, rowCount()); // USER still managed to write data!
    }

    @Test
    @WithMockUser(roles = "USER")
    void separateProtectedBeanRejectsUnauthorizedWrite() {
        assertThrows(AccessDeniedException.class,
            () -> safeFacade.execute(false));
        assertEquals(0, rowCount());
        assertEquals(0, notifications.count());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void authorizedWriteCommits() {
        assertTrue(safeFacade.execute(false)); // Transaction active inside service.
        assertEquals(1, rowCount());           // Read after method returns.
        assertEquals(1, notifications.count());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void runtimeFailureRollsBackDbButNotExternalNotification() {
        assertThrows(IllegalStateException.class,
            () -> safeFacade.execute(true));
        assertEquals(0, rowCount());          // INSERT rolled back.
        assertEquals(1, notifications.count()); // "Send" still occurred.
    }
}
```

Run in the module containing the test (for example from the corresponding Gradle project directory):

```bash
./gradlew test --tests "example.security.MethodSecurityTransactionTest"
```

On Windows use `gradlew.bat` with the same arguments; in a multi-project Gradle build you may need to specify `:module-path:test`. Expected result: **4 tests PASS** when configured with Spring Boot 3.x, JDBC/Security starters, H2, and JUnit Platform as shown above. There is no fixed stdout; JUnit/Gradle reports test results, while assertions verify behavior.

### 4.1. Why are these assertions meaningful?

**Self-invocation test:** the same USER is denied when calling `vulnerable.guardedWrite()` yet writes to the DB through `vulnerable.invokeInternally()`. The `false` value of `isActualTransactionActive()` is meaningful only because this test **has no enclosing transaction**. H2 JDBC outside a transaction can auto-commit the INSERT. This test intentionally exposes a flaw; its "PASS" **does not mean the flawed implementation is safe**.

**Separate-bean test:** `SafeFacade` holds a Spring-injected `ProtectedService` reference; calling `protectedService.writeAndNotify()` goes through the proxy, so USER is blocked **before INSERT and send**.

**Commit test:** when called outside an existing transaction, `@Transactional` wraps the operation; after the method returns, reading the DB and seeing the row observes a real commit (not merely buffered persistence-context state).

**Rollback and side-effect test:** `IllegalStateException` is an unchecked exception, causing the JDBC transaction to roll back; the gateway's `AtomicInteger` incremented outside the transactional resource so it does not reset to 0. Replacing the fake gateway with real HTTP/email/message brokers requires matching verification and cleanup strategies.

## 5. Extensions: edge cases easily missed

### 5.1. Self-invocation with `REQUIRES_NEW` and an enclosing transaction

Consider this illustrative snippet (not a standalone Java file):

```java
@Transactional
public void outer() {
    this.writeInNewTransaction(); // bypasses proxy
    throw new IllegalStateException("outer failed");
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeInNewTransaction() {
    repository.save(/* audit */);
}
```

If `outer()` passes through the proxy, the outer transaction is active, yet calling `this.writeInNewTransaction()` does not start a separate `REQUIRES_NEW` transaction; the audit write joins the existing transaction and may roll back together with `outer`. If `writeInNewTransaction` is moved to a separate bean and called through its proxy, the new transaction can commit independently when `outer` rolls back. **A proper test suite** verifies DB state **after `outer` finishes**, with clear expectations per design; do not merely assert `TransactionSynchronizationManager.isActualTransactionActive() == true` because both the old and new transactions return `true`.

Also consider connection-pool exhaustion risks when using `REQUIRES_NEW` while `outer` holds a connection. Do not use `REQUIRES_NEW` just to "rescue" a self-invocation bug or bypass authorization policies.

### 5.2. Caught and swallowed errors and exception types

```java
@Transactional
public void saveWithCatch() {
    repository.save(/* entity */);
    try {
        remoteGateway.call();
    } catch (RuntimeException ex) {
        log.warn("Call failed", ex);
        // Returns normally: transaction advice may commit DB.
    }
}
```

If business rules require the entire DB to roll back when the remote call fails, tests must verify rethrowing the exception, explicitly marking rollback-only, or redesigning the workflow. For checked exceptions, `@Transactional` does not roll back by default unless an appropriate `rollbackFor` is declared. Test explicitly: **what exception type is thrown, does it cross the transaction boundary, and does data remain in the DB?**

### 5.3. `@PostAuthorize` after writing

`@PostAuthorize` works well for **read** results (such as permission to view an object you own). For writes, the post-check can run after side effects and potentially after commit, depending on advisor ordering. Test with a fake write operation having a counter: call with an underprivileged USER, assert the exception **and** re-read the counter/DB. If the counter incremented or a row persisted, the test proved denial did not protect atomicity. Redesign by checking privileges *before* the operation and prefer separating read/authorize/write per domain requirements.

### 5.4. DB rollback does not recall emails, HTTP calls, queues, or files

- **Email/HTTP calls:** once sent, a DB rollback cannot recall them; use fakes/mocks to count invocations, and in integration tests use a test server and inspect received requests.
- **Message brokers:** "send was called" differs from "broker acknowledged" and differs from "consumer processed"; assert at the desired guarantee level.
- **Files, caches, in-memory state:** require separate compensation/synchronization; JDBC `@Transactional` does not manage them by default.
- **`@TransactionalEventListener(phase = AFTER_COMMIT)`:** the listener fires only after a successful commit when a matching transaction exists; tests should verify "rollback means listener does not run" and "commit means it runs". Without a transaction, the listener does not run by default (unless fallback is configured). AFTER_COMMIT avoids sending before rollback, yet **does not guarantee** reliable delivery if the process crashes between commit and sending.
- **Transactional outbox:** write both business data and an outbox row in the **same** DB transaction, then have a separate worker publish events; usually needs retries, idempotency, and deduplication. Tests must prove rollback leaves no outbox row and commit leaves the outbox row, then test publishing separately.

### 5.5. Do not let test-managed transactions create false results

`@Transactional` on a Spring Test method normally opens a **test-managed transaction** and rolls it back after the test. This can hide a bug where "the service forgot to open a transaction", because the service still runs inside the test's transaction. It is also easy to confuse an INSERT visible **inside** the test with committed data.

For tests asserting **service-level** commit/rollback, as in section 4:

1. **Do not** place `@Transactional` on the test method or test class.
2. Clean data in `@BeforeEach`, then invoke the real bean from a normal thread.
3. Assert DB state **after** the service call returns or throws.
4. If forced to use a test-managed transaction, consider `TestTransaction.flagForCommit()/flagForRollback()` and `TestTransaction.end()`, verify data from a separate transaction/connection, and understand propagation carefully.
5. With JPA, `flush()` and possibly `clear()` before verification queries to avoid reading only cached state; flushing **is not synonymous** with committing.

Timeouts running test logic on another thread and asynchronous code can also cross the test's transaction/thread-local or SecurityContext boundaries. Write dedicated integration tests for async code; do not extrapolate from single-threaded synchronous tests.

## 6. Common test errors and diagnostics

| Symptom | Likely cause | How to check/fix |
| --- | --- | --- |
| USER still executes `@PreAuthorize` method | Calling `this.method()`, manually instantiating bean, non-interceptable method, method security disabled | Check `@EnableMethodSecurity`, injected Spring bean, proxy call path; split beans |
| `@Transactional` call does not open a new transaction | Self-invocation; enclosing transaction exists; method/bean not advised | Test without test transaction; assert commit/rollback; check propagation and proxy call |
| Test always rolls back even when service lacks `@Transactional` | `@Transactional` on the test | Remove annotation from transaction-boundary tests; use `TestTransaction` if needed |
| `assertThrows` PASSES yet DB/notification still happened | `@PostAuthorize` checks after side effects; wrong transaction/order/exception handling | Also assert DB state and side effects; move check before write |
| `verify(repository).save()` PASSES yet DB never commits | Mocks do not prove transactions or flush/commit | Test JDBC/JPA against a real database and inspect data after the call |
| DB rolled back yet email/message was sent | External resource outside transaction | AFTER_COMMIT or outbox/idempotency; assert both DB and outbound effects |
| Transaction does not roll back on error | Checked exception; caught and swallowed; nested `REQUIRES_NEW` committed | Test rollback rules, exception propagation, and real boundaries |

An `AccessDeniedException` on a direct service call **does not automatically become HTTP 403**; mapping 403 is the responsibility of web/security filters or exception handling at the HTTP boundary. This lesson tests the method layer; if HTTP contracts are needed, add separate `MockMvc`/request tests. Additionally, `@WithMockUser` supplies mock identity/authorities and does not test real JWT/session/identity providers.

## 7. Practice acceptance checklist

- [ ] Method security and transaction management enabled; use **Spring-injected beans**, never `new` for objects needing AOP.
- [ ] Include a denied **direct call through proxy** case, and a **self-invocation** case proving why the internal call path is problematic.
- [ ] After refactoring into two beans, USER is denied with **no DB/notification writes**.
- [ ] ADMIN succeeds: verify data **after service returns** and active transaction while service runs.
- [ ] Runtime exception: DB rolls back, while explicitly stating whether non-DB effects remain or not.
- [ ] When using `REQUIRES_NEW`, verify independent commit via data after outer ends, not solely via an "active transaction" flag.
- [ ] If using `@PostAuthorize`, never assume denial protects writes; inspect ordering and side effects.
- [ ] Tests verifying transaction boundaries do not carry `@Transactional` themselves; all exceptions, mocks, and lifecycles are controlled.

## Authoritative references

- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize`, and interceptors.
- [Spring Security – Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser`, test context.
- [Spring Framework – AOP Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): why self-invocation bypasses advice and remediation options.
- [Spring Framework – Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy mode, transaction defaults, and rollback rules.
- [Spring Framework – Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`, `NESTED`.
- [Spring Framework – Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollback in tests, `TestTransaction`, and false positives.
- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` and `AFTER_COMMIT`.
