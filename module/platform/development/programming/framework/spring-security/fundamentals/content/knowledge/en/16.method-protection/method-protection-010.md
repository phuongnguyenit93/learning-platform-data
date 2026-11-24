# Never Use Post-Execution Checks as Authorization for Data-Mutating Operations

> **Module:** Spring Security - fundamentals  
> **Parent Topic:** Method protection  
> **Key Message:** A `403 Forbidden` response after `@PostAuthorize` does not prove the method did not mutate data. For actions with side effects, authorization checks must happen **before** the operation; transactions and error-recovery mechanisms must never replace authorization.

## 1. Learning Objectives

After this lesson, you can:

- Explain the difference between `@PreAuthorize` and `@PostAuthorize` in terms of **when** Spring Security evaluates the decision.
- Spot bugs caused by placing `@PostAuthorize` on UPDATE, DELETE, approval, message-sending, or payment methods.
- Read runnable Java 17/Spring Boot code where a method is denied yet a state counter still increments.
- Understand the limits of `@Transactional`, rollbacks, AOP advisor ordering, and side effects outside the database.
- Design pre-action authorization checking owner/tenant/resource and preserving invariants under concurrency.
- Write tests proving both **unauthorized callers are denied** and **data is not mutated without authorization**.

## 2. Does Spring Security Check Before or After the Method?

When method security is enabled with `@EnableMethodSecurity`, Spring Security creates interceptors applied to Spring-managed beans. Two key annotations have different semantics:

| Annotation | When evaluated? | Can access return value? | Recommended use |
| --- | --- | --- | --- |
| `@PreAuthorize` | Before the method body runs | No | Stop writes/deletes/approvals before side effects occur |
| `@PostAuthorize` | After the method body returns | Yes, via `returnObject` | Decide whether the **read result may be returned** |
| `@PreFilter` | Before method execution, filters eligible collection parameters | No | Restrict processed items; does not replace policy |
| `@PostFilter` | After method returns a collection result | Yes | Restrict returned list; does not undo writes |

Minimal configuration example:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Spring Boot Starter Security **does not automatically enable** method security merely because the dependency exists; this config or an equivalent enabler must be loaded into the Spring ApplicationContext. In standard proxy mode, calls must travel through the Spring bean proxy for interceptors to run.

### Check-Timing Diagram

~~~text
@PreAuthorize

Caller -> Spring proxy -> authorization check
                              | DENY -> exception, method never ran
                              | GRANT -> method runs -> writes data -> returns


@PostAuthorize

Caller -> Spring proxy -> method runs -> writes data -> returns
                                                       |
                                                       v
                                                 authorization check
                                                 | DENY -> exception
                                                 | GRANT -> returns result

On the DENY branch, data writes MAY have already occurred.
~~~

`@PreAuthorize` does not by itself guarantee an operation is valid in every scenario: you still need proper policies, proxy-routed calls, and owner/tenant/invariant checks. However, it places the gate **before** side effects—the right spot for write operations.

## 3. Why Is `@PostAuthorize` Dangerous for Data-Mutating Methods?

Suppose an invoice approval method:

~~~java
// WRONG EXAMPLE: illustrative snippet integrated into a service.
@PostAuthorize("hasAuthority('invoice:approve')")
public String approveInvoice(long id) {
    invoiceRepository.updateStatus(id, "APPROVED");
    return "approved";
}
~~~

If the caller is Alice, authenticated yet missing `invoice:approve`:

1. The proxy forwards the call into the method body.
2. The repository executes the invoice UPDATE.
3. The method returns the string `approved`.
4. The after-method interceptor evaluates `hasAuthority('invoice:approve')` and denies access.
5. The caller receives `AccessDeniedException`; proper HTTP integration can turn it into `403 Forbidden`.
6. **Data may already have changed** or committed before the exception was raised.

Point to remember: `@PostAuthorize` is not an undo command. It is designed to decide whether to **return a result after invocation**, not to prevent execution that already took place.

~~~text
Observed from client side: HTTP 403
Possible actual state: invoice #42 = APPROVED
Vulnerability: authorization checked after state mutation
~~~

The same happens when a method emits Kafka events, sends emails, calls a payment gateway, updates an external cache outside a transaction, or launches async tasks.

### Side Effects Are Not Always Reversible

~~~java
// WRONG EXAMPLE: payment gateway already received request before after-check.
@PostAuthorize("hasAuthority('payment:transfer')")
public String transfer(String recipient, long amount) {
    paymentGateway.transfer(recipient, amount);
    return "sent";
}
~~~

Even if `AccessDeniedException` follows, Spring Security does not automatically recall a command the gateway already accepted. Even a database rollback does not automatically unsend emails or retract published messages.

**Rule:** Before any side effect occurs, the system must complete proper authorization; never rely on post-action error responses.

## 4. The Right Pattern for Write Operations

Replace the after-check with a before-check:

~~~java
// Illustrative code inside a Spring-managed service.
@PreAuthorize("hasAuthority('invoice:approve')")
public String approveInvoice(long id) {
    invoiceRepository.updateStatus(id, "APPROVED");
    return "approved";
}
~~~

When the user lacks the authority, the intercepted call is blocked **before** the repository runs.

Yet a coarse action permission may be insufficient. For example, a user may only approve invoices in their own tenant; a resource-level policy is needed:

~~~java
// Requires real invoicePolicy bean and repository from the application.
@PreAuthorize(
    "hasAuthority('invoice:approve') and " +
    "@invoicePolicy.mayApprove(authentication, #invoiceId)"
)
public void approveInvoice(long invoiceId) {
    invoiceRepository.approve(invoiceId);
}
~~~

`invoicePolicy` must use trusted data to verify owner, tenant, state, limits, and business rules. Never trust a client-declared `tenantId`. The expression above is an **illustrative integration snippet**, not a standalone Java example.

Even after `@PreAuthorize`, state can change concurrently; therefore verify/lock/conditionally UPDATE at the transaction boundary where appropriate (section 8).

## 5. Runnable Example: After DENY, the Counter Still Increments

This demo uses **Java 17+, Spring Boot 3.3.5, Spring Security 6.x, and Gradle 8.x**. To clearly expose authorization ordering without depending on database rollbacks, we use an `AtomicInteger` inside a Spring bean. Once a method calls `incrementAndGet()`, a subsequent exception does not decrement it back.

### 5.1. Structure

~~~text
after-authorize-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/afterauth/
    │   ├── Application.java
    │   ├── StateStore.java
    │   └── MutationService.java
    └── test/java/demo/afterauth/
        └── MutationServiceTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'after-authorize-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The demo tests the service directly, requiring no web server. `spring-security-test` provides `@WithMockUser` and `@WithAnonymousUser` to populate test security contexts; they do not perform real logins.

### 5.2. Application Enabling Method Security

File `src/main/java/demo/afterauth/Application.java`:

~~~java
package demo.afterauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

`@EnableMethodSecurity` sits on the loaded Spring Boot configuration class. Removing this annotation prevents default method-security infrastructure from enforcing `@PreAuthorize`/`@PostAuthorize` on the service.

### 5.3. Observable Write State

File `src/main/java/demo/afterauth/StateStore.java`:

~~~java
package demo.afterauth;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class StateStore {

    private final AtomicInteger writes = new AtomicInteger();

    public int writeOnce() {
        return writes.incrementAndGet();
    }

    public int current() {
        return writes.get();
    }

    public void reset() {
        writes.set(0);
    }
}
~~~

### 5.4. Two Methods with the Same Authority, Different Timing

File `src/main/java/demo/afterauth/MutationService.java`:

~~~java
package demo.afterauth;

import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class MutationService {

    private final StateStore store;

    public MutationService(StateStore store) {
        this.store = store;
    }

    // WRONG for writes: executes side effect before checking.
    @PostAuthorize("hasAuthority('record:write')")
    public int writeThenCheck() {
        return store.writeOnce();
    }

    // RIGHT: unauthorized callers never enter the method body.
    @PreAuthorize("hasAuthority('record:write')")
    public int checkThenWrite() {
        return store.writeOnce();
    }
}
~~~

Both methods require `record:write`. For Alice holding only `record:read`:

- `writeThenCheck()` executes `store.writeOnce()`, and is denied afterward.
- `checkThenWrite()` is denied before calling `store.writeOnce()`.

### 5.5. Testing with JUnit 5

File `src/test/java/demo/afterauth/MutationServiceTest.java`:

~~~java
package demo.afterauth;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class MutationServiceTest {

    @Autowired
    MutationService service;

    @Autowired
    StateStore store;

    @BeforeEach
    void resetStore() {
        store.reset();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "record:read")
    void postAuthorizeDeniesAfterTheMutation() {
        assertThrows(AccessDeniedException.class,
            () -> service.writeThenCheck());

        // DENY does not mean no side effect happened.
        assertEquals(1, store.current());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "record:read")
    void preAuthorizeDeniesBeforeTheMutation() {
        assertThrows(AccessDeniedException.class,
            () -> service.checkThenWrite());

        assertEquals(0, store.current());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "record:write")
    void authorizedUserCanWrite() {
        assertEquals(1, service.checkThenWrite());
        assertEquals(1, store.current());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "record:write")
    void authorizedUserAlsoPassesPostCheck() {
        assertEquals(1, service.writeThenCheck());
        assertEquals(1, store.current());
    }

    @Test
    @WithAnonymousUser
    void anonymousCallerCannotWriteWithPreCheck() {
        assertThrows(AccessDeniedException.class,
            () -> service.checkThenWrite());

        assertEquals(0, store.current());
    }
}
~~~

Run from the project root with JDK 17+ and Gradle 8.x:

~~~bash
gradle test
~~~

Or run only the test class:

~~~bash
gradle test --tests demo.afterauth.MutationServiceTest
~~~

**Expected outcome:** all 5 tests pass. The table below describes state after each test when `@BeforeEach` resets the counter; these are **outcomes deduced from the program**, not test logs run inside this article.

| Case | Caller permission | Method outcome | `store.current()` |
| --- | --- | --- | --- |
| Alice calls `writeThenCheck()` | `record:read` | `AccessDeniedException` | **1** |
| Alice calls `checkThenWrite()` | `record:read` | `AccessDeniedException` | **0** |
| Bob calls `checkThenWrite()` | `record:write` | Returns `1` | **1** |
| Bob calls `writeThenCheck()` | `record:write` | Returns `1` | **1** |
| Anonymous calls `checkThenWrite()` | No write permission | `AccessDeniedException` | **0** |

**Pay close attention to the first test.** If you only assert `AccessDeniedException`, a reader easily assumes the system is protected. Yet the state assertion reveals the mutation actually took place.

### Why Is This Example Credible for Explaining Timing?

`AtomicInteger` has no database transaction, so no rollback hides the effect. Tests invoke the Spring-injected service via its AOP proxy (not via `new`). When the after-interceptor denies after the target returns, the counter stays at `1`. This demo proves the ordering issue, **without claiming every JDBC transaction commits in every configuration**.

## 6. Transaction Rollback Is Not a Substitute for Authorization

A common counterargument is: "The method has `@Transactional`, so if `@PostAuthorize` denies, the transaction rolls back—therefore it's safe." That conclusion is **false in general**.

### 6.1. Rollback Has Limited Scope

With Spring Framework declarative transactions, a `RuntimeException` or `Error` crossing the transaction interceptor typically triggers rollback by default. Checked exceptions require explicit rollback rules to roll back. Yet a transaction only coordinates **participating resources** within its actual boundary.

For example, a database rollback does not automatically undo:

- Emails or SMS already sent.
- Transfer requests already accepted by a payment gateway.
- Events published to a broker outside the transaction.
- Files written to the filesystem.
- Non-transactional caches and the `AtomicInteger` in our demo.
- Writes committed in another independent transaction.

Therefore, **even a successful DB rollback does not prove "no unauthorized side effect occurred."**

### 6.2. Advisor Ordering and Transaction Boundaries

Both `@PostAuthorize` and `@Transactional` are applied by Spring via advice. Their nesting order affects whether the exception arises before or after commit.

~~~text
Case A: transaction advice wraps outside after-authorize advice

BEGIN
  target method UPDATE
  @PostAuthorize: DENY
  exception passes through transaction interceptor
ROLLBACK may occur per rollback rules


Case B: after-authorize advice wraps outside transaction advice

BEGIN
  target method UPDATE
COMMIT
@PostAuthorize: DENY
exception appears after COMMIT
~~~

These are **two conceptual possibilities**, not a claim that a specific Spring configuration falls into A or B. You must know the actual advisor order, transaction manager, propagation, exception handling, and proxy topology.

Official Spring Security documentation also warns that `@PostAuthorize` is **not recommended** on classes performing database writes because changes may already happen before security invariants are evaluated.

The more reliable design: **check permissions before write operations**, never relying on an accidental combination of advisor order and rollback to fix an authorization decision made too late.

### 6.3. HTTP 403 Does Not Certify Rollback

A request returning `403 Forbidden` may have been blocked by HTTP authorization, CSRF, `@PreAuthorize`, or `@PostAuthorize`. You cannot infer which layer denied or the database state from HTTP status alone. If a transaction committed before an after-check DENY, a 403 response **does not reverse that commit**.

For high-risk operations, tests must inspect state after the transaction completes and verify no external calls were emitted when unauthorized.

## 7. When Is `@PostAuthorize` Appropriate?

`@PostAuthorize` remains useful for **read methods** when authorization depends on the actual returned value.

~~~java
// Integration example; requires Document and documentRepository in app.
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize(
    "returnObject != null and returnObject.ownerUsername == authentication.name"
)
public Document getDocument(long documentId) {
    return documentRepository.findById(documentId).orElse(null);
}
~~~

The read method returns a `Document` with property `ownerUsername` (e.g., getter `getOwnerUsername()`). The before-check requires read authority; the after-check returns the object only if the owner matches the principal. There is no requirement to update data inside the method body.

Still, the read method **already ran** before the after-check; avoid sensitive side effects inside it. For sensitive data or large document collections, filtering by owner/tenant at the repository/query before loading data is generally better. `@PostFilter` is similar: it filters the **returned** collection without erasing writes executed inside the method body.

## 8. Pre-Write Checks Still Need Invariant Protection Under Concurrent Requests

Holding `invoice:approve` only confirms the principal has the general capability. It does not prove they may approve **invoice #42** belonging to another tenant, or that the invoice is still in `PENDING` state when writing.

A typical defense chain:

1. **Authentication:** system-verified principal exists.
2. **Authority check:** `@PreAuthorize("hasAuthority('invoice:approve')")`.
3. **Object policy:** check owner/tenant/state against server data, not merely client input.
4. **Write-boundary invariant:** re-check conditions inside the transaction or via conditional UPDATE / optimistic versioning / locking to prevent races (*TOCTOU — time of check to time of use*).
5. **External side effects:** proceed only after authorization and according to an explicit consistency design.

Illustrative SQL solely showing atomic check-and-write:

~~~sql
UPDATE invoices
SET status = 'APPROVED'
WHERE id = :invoice_id
  AND tenant_id = :verified_tenant_id
  AND status = 'PENDING';
~~~

`:verified_tenant_id` comes from a trusted identity/tenant source; parameters must be bound safely. Check the affected row count: zero may mean wrong tenant, invalid state, or record no longer eligible. Never return "approved" when the update did not succeed.

A conditional UPDATE **does not replace** authentication or authority checks. It is a data-layer defense enforcing invariants at write time.

### Publishing Events, Outbox, and Idempotency

To publish an "invoice approved" event after database commit, a transactional outbox can be used. Writing the outbox event in the same transaction and dispatching after commit improves consistency. Yet **never create unauthorized events prior to authorization**. With payment gateways, use idempotency keys and retry/compensation policies; those handle business safety, not authorization.

## 9. Protecting the Exact Entry Point Through Spring AOP Proxies

In proxy mode, `@PreAuthorize` on a method does not always block `this.method()` calls from within the same object:

~~~java
// Risky example: self-invocation goes straight to the target method.
@Service
public class InvoiceWorkflow {

    public void run(long id) {
        approve(id); // self-invocation, bypasses standard proxy
    }

    @PreAuthorize("hasAuthority('invoice:approve')")
    public void approve(long id) {
        // writes data
    }
}
~~~

If `run()` is the externally invoked entry point with no policy, the interceptor on `approve()` can be bypassed by self-invocation. Fix by guarding `run()` or extracting `approve()` to another Spring-managed service injected and invoked via its bean proxy.

Similarly, instantiating objects with `new` never receives Spring method-security advice. Private or final methods also carry proxy/overriding limits depending on proxy mode. Adding `@PreAuthorize` is necessary yet insufficient: **verify actual call paths**.

## 10. Testing Permissions and Data: Two Kinds of Assertions Are Needed

| What to verify | Purpose | Assertion |
| --- | --- | --- |
| Authorization | Unauthorized callers are denied | `AccessDeniedException` or HTTP 403 |
| State invariant | No unauthorized mutations occurred | Database row/status identical before and after |
| External side effects | No unauthorized outbound commands | Fake or sandbox payment/event/email records 0 calls |
| Concurrent safety | Concurrent state changes cannot break invariants | Atomic update, version check, concurrency test |
| Proxy boundary | Annotation takes effect on real entry points | Call via Spring bean and test missing-permission path |

Minimum test scenarios:

- Unauthenticated: does not write.
- Authenticated but missing authority: does not write.
- Has authority, wrong owner/tenant: does not write.
- Correct authority and owner/tenant: writes the exact resource once.
- Data changes concurrently: does not bypass business invariants.
- Exceptions, retries, gateway errors: does not duplicate unauthorized side effects.
- Method called from another service or internally: does not bypass policy.

**Do not only write** `assertThrows(AccessDeniedException.class, ...)` and assume safety: the demo in section 5 shows that passes even when state incremented.

Additional note: Integration tests wrapped in test transactions rolled back by the framework at test end can hide real commit behavior. When proving safety across transaction boundaries, test by observing data outside test transactions or properly after commit.

`@WithMockUser` in method tests mocks the security context and does not prove login flows, JWT verification, or production claims-to-`GrantedAuthority` mapping are right. Test those layers separately as needed.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Putting `@PostAuthorize` on DELETE/UPDATE methods | DENY happens, yet target may have already written | Use `@PreAuthorize` and domain authz before mutation |
| Seeing HTTP 403 and concluding data is unchanged | Misses committed writes or external calls | Assert actual state and side effects |
| Assuming `@Transactional` always rolls everything back | Not everything participates in TX; advisor order varies | Never rely on rollback instead of authorization |
| Using only `hasRole('ADMIN')` and skipping owner/tenant checks | Overly broad object-level privileges | Object-level policies and write-boundary invariants |
| Having a before-check without handling TOCTOU | Data changes between check and write | Conditional UPDATE, locking, or versioning |
| `@PostFilter` after already sending messages | Filtering the response does not unsend messages | Check permissions before sending |
| Calling `this.approve()` inside the same bean | Method security may be bypassed | Enforce policy at entry point or separate bean |
| Testing only response codes, never the database | Misses unauthorized mutations | Test both permissions and before/after state |
| Trusting client-supplied permissions/tenants | Privilege escalation or cross-tenant access | Use trusted auth/resource data sources |

## 12. Self-Check Questions

**Question 1.** `@PostAuthorize` denies after the method already updated an invoice, and the client gets 403. Is the invoice guaranteed unchanged?

**Answer:** No. The method ran before the after-check; the UPDATE may have committed. Verify database and transaction boundaries.

**Question 2.** Does `@Transactional` turn an after-check into a before-check?

**Answer:** No. It coordinates commit/rollback of participating resources; the authorization decision still happens afterward when using `@PostAuthorize`. Advisor ordering and external side effects make relying on rollback unsafe.

**Question 3.** If using `@PreAuthorize("hasAuthority('invoice:approve')")`, what else must be checked?

**Answer:** Real invoice tenant/owner/state, business invariants, and potential concurrent updates if required by system policy.

**Question 4.** Why can `@PostAuthorize("returnObject.ownerUsername == authentication.name")` fit a read service?

**Answer:** Permission to receive the object depends on the retrieved object itself, provided the method triggers no sensitive side effects.

**Question 5.** What extra assertions does a test returning 403 need to prove no unauthorized write occurred?

**Answer:** Verify the database/state is unchanged and no unauthorized external action was dispatched.

**Question 6.** Why can `@PreAuthorize` be skipped when calling `this.approve()`?

**Answer:** In Spring AOP proxy mode, self-invocation bypasses the proxy and does not run advice on the called method.

## 13. Conclusion and Official Documentation

**Never use post-execution checks as authorization for data-mutating operations.** For side-effecting actions, authorization must be a precondition **to starting execution**, not a review after the system already acted. `@PostAuthorize` is useful for decisions based on a read method's return data; transactions, compensation, and idempotency serve consistency, not pre-action authorization. Good security tests always verify both DENY and **zero unauthorized mutations**.

References:

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Framework — Transaction Rollback](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — AOP Proxying](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
