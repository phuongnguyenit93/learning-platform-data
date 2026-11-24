# Distinguishing Unexecuted Business Logic from Executed Logic Whose Result Was Blocked

An API returning **403 Forbidden** is not enough to tell whether the business logic executed or not. In Spring Security method security, an error denied **before** the target method runs is completely different from **the method having run, produced a return value, and then the result being denied by a post-check**. Both cases can throw `AccessDeniedException` and both can be translated by the HTTP layer into 403, yet the DB state, emitted events, and effects on other systems can be very different.

This lesson dives into **Post-Method Checks** via `@PostAuthorize` and compares it with `@PreAuthorize`, applicable to Spring Security 6.x / Spring Boot 3.x on the Servlet stack and Java 17+. The content clarifies the Spring AOP proxy, when `returnObject` exists, conditions under which the body has not run, what happens when a post-check DENYs, transaction ordering/rollback, side effects such as emails and events, how to move authorization before mutation, and tests proving execution timing. It includes a standalone Java 17 program that compiles/runs with verified stdout.

## 1. Two types of denial, one similar status

~~~text
A. BEFORE-METHOD DENY                    B. AFTER-METHOD DENY

caller -> service proxy                  caller -> service proxy
             |                                         |
       @PreAuthorize                                method body
             |                                         |
             +-- DENY                                 +-- execute business logic
             |                                        +-- return returnObject
             v                                         |
     AccessDeniedException                       @PostAuthorize
     target body NOT YET run                           |
                                                      +-- DENY
                                                      |
                                                      v
                                               AccessDeniedException
                                               target body ALREADY ran
~~~

| Question | `@PreAuthorize` denies | `@PostAuthorize` denies |
| --- | --- | --- |
| Was the method body called? | **No**, when passing through the before-interceptor. | **Yes**, because a result must exist to evaluate afterward. |
| Was the DB queried? | A pre-check policy may read the DB, but the blocked body has not run. | The body may have read or written depending on implementation. |
| Are there side effects? | No side effects from the blocked body; earlier layers may still have done work. | **Possible**, not automatically undone. |
| Does the caller receive the result? | No, under default DENY. | No, under default DENY. |
| What might HTTP return? | 403, 401, or redirect depending on authentication/exception handler. | Can be the same HTTP 403; status does not reveal timing. |
| Suitable for protecting mutations? | Often useful to block early; still needs invariants inside the transaction. | **Should not** be the sole authorization gate for writes. |

**Accurate wording:** “Business logic not yet executed” should be understood as **the guarded target method body has not run**, not that no Java code, SQL SELECT, security filter, or policy bean has been called at all.

## 2. Conditions for the annotation to actually take effect

Spring Boot Starter Security **does not enable method security automatically**. You must declare:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Spring Security 6.x registers pre/post method annotations by default when `@EnableMethodSecurity` is active. Key components:

- `AuthorizationManagerBeforeMethodInterceptor` + `PreAuthorizeAuthorizationManager` enforce `@PreAuthorize` **before** the target invocation.
- `AuthorizationManagerAfterMethodInterceptor` + `PostAuthorizeAuthorizationManager` enforce `@PostAuthorize` **after** the target invocation returns normally.
- `MethodSecurityExpressionHandler` builds the SpEL context to evaluate Authentication, arguments, and `returnObject`.

An essential condition is that the caller invokes **the Spring-managed service bean through an AOP proxy**. Calling `this.securedMethod()` on the same instance (self-invocation) or manually creating `new Service()` can bypass the proxy in default AOP configuration. In that case the annotation appears in source code but blocks nothing. You must test an object **injected from the ApplicationContext**, not just a directly instantiated Java object.

If a request is blocked by `AuthorizationFilter` or the CSRF filter before the controller, the method body also has not run, yet **that is not proof that `@PreAuthorize` ran**. HTTP authorization and method authorization are two distinct gates.

## 3. `@PreAuthorize`: blocking before the target method

Spring service example:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportReadService {
    private final ReportRepository reports;

    public ReportReadService(ReportRepository reports) {
        this.reports = reports;
    }

    @PreAuthorize("hasAuthority('REPORT_READ')")
    public ReportView read(long id) {
        return reports.loadView(id);
    }
}
~~~

This snippet **depends on Spring and application-written `ReportRepository`/`ReportView` types**, and does not compile with JDK alone. Anyone lacking `REPORT_READ` is denied before `reports.loadView(id)` is called in the body.

You can check permission by ID using a policy bean:

~~~java
@PreAuthorize(
    "hasAuthority('REPORT_READ') and @reportPolicy.mayRead(authentication, #id)")
public ReportView read(long id) {
    return reports.loadView(id);
}
~~~

The `reportPolicy` bean must be defined and `mayRead(Authentication,long)` must rely on **server-verified** data (owner/tenant/status), not merely a client-declared ID or owner. The policy may issue a SELECT to decide; therefore even a pre-denial does not prove “zero SQL was executed”. What is guaranteed is that **the blocked method body does not run**, provided interception occurred properly.

For write operations, a pre-check on permissions is an important step but **does not replace** invariant checks at UPDATE time: data can change after the policy check (TOCTOU). Appropriate versioning/locking or conditional updates are needed.

## 4. `@PostAuthorize`: checking a result already produced

A method reading a single object:

~~~java
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportLookupService {
    private final ReportRepository reports;

    public ReportLookupService(ReportRepository reports) {
        this.reports = reports;
    }

    @PostAuthorize(
        "returnObject != null and returnObject.owner == authentication.name")
    public ReportView find(long id) {
        return reports.loadView(id);
    }
}
~~~

This is also a Spring snippet requiring a real `ReportView`, repository, Authentication, and bean, **not a standalone Java program**. Suppose Alice requests a report owned by Bob: the body called the repository, received Bob's `ReportView`, and returned. `@PostAuthorize` sees `returnObject.owner` differs from `authentication.name`, so the caller does not receive the object and instead receives a DENY via the default mechanism.

Limitations to understand:

- `returnObject` only exists after the method returns normally, not as a variable to block queries at the start of the body.
- `returnObject != null` is a null guard; if you want 404 when not found, handle not-found consistently in domain/exception handling.
- Owner matching username may not be enough: you must check **tenant membership, sharing scope, and actual permissions**, not rely solely on owner name.
- `Authentication.getName()` may be a JWT subject or an identity different from DB username; the policy needs proper mapping.
- The method may already have logged/cached/emitted events before returning; the post-check only blocks **returning the result via the proxy**, not recalling data from other channels.
- If the method throws an exception before returning, there is no normal `returnObject` for the expression above; that is a body exception, **not a boolean post-denial**.

Spring Security 6.5 views `@PostAuthorize` as a useful tool against **Insecure Direct Object Reference (IDOR)** when the returned object itself carries the ownership attribute to inspect. However, when feasible, constrain the query directly at the DB to avoid loading out-of-scope data before checking.

## 5. Same method having both pre- and post-checks

~~~java
@PreAuthorize("hasAuthority('REPORT_READ')")
@PostAuthorize(
    "returnObject != null and @reportPolicy.maySee(authentication, returnObject)")
public ReportView read(long id) {
    return reports.loadView(id);
}
~~~

In this example, `reportPolicy` is a Spring bean and `maySee` receives Authentication and ReportView; the logic must be implemented by the application and is not built in. Three scenarios:

~~~text
1) Missing REPORT_READ:
   @PreAuthorize DENY -> body NOT YET run -> no returnObject.

2) Has REPORT_READ but report belongs to another tenant:
   @PreAuthorize ALLOW -> body runs and returns ReportView
   -> @PostAuthorize DENY -> caller does not receive ReportView.

3) Has REPORT_READ and view permission on report:
   @PreAuthorize ALLOW -> body runs -> @PostAuthorize ALLOW
   -> caller receives ReportView.
~~~

When both annotations apply, their respective authorization decisions must pass for the call to complete. Spring AOP advisor ordering is determined by framework/configuration; do not infer the order of **transaction, cache, audit, or custom advisors** from the order printed in source code.

Note: `@PostFilter` differs from `@PostAuthorize`. `@PostFilter` can remove individual elements from a collection and return a reduced list; `@PostAuthorize` by default decides **whether to hand over the entire result or not**. A 200 response with an empty list does not by itself prove post-check authorization denied.

## 6. Anti-pattern: mutating first, post-checking afterward

This is an example **intentionally wrong in security design**:

~~~java
@PostAuthorize("returnObject.approver == authentication.name")
public ApprovalReceipt approve(long reportId) {
    reportRepository.markApproved(reportId);
    eventPublisher.sendApproved(reportId);
    return receipts.load(reportId);
}
~~~

The beans/types above are application placeholders. Execution flow:

~~~text
1. User calls approve(reportId)
2. Method body UPDATEs data
3. Method body publishes event or sends email
4. Method body creates receipt and RETURNs
5. @PostAuthorize checks returnObject.approver
6. Predicate false -> AccessDeniedException
7. HTTP caller may see 403
~~~

**At step 7, you cannot conclude steps 2 and 3 did not run.** If the update committed, data changed; if the broker received the event, consumers may have processed it; a sent email cannot automatically be retracted by a Java exception. If the client retries thinking the command failed, there is a risk of **repeating the operation** when idempotency is missing.

Nor may you claim “post-denial always means the DB COMMITted”. The method body ran and returned, while commit/rollback depends on transaction advice ordering, transaction propagation, rollback rules, and implementation. **Actual impact must be verified via DB state and side-effect logs/test fixtures.**

Spring Security 6.5 **does not recommend `@PostAuthorize` for DB-writing methods**, because changes can occur before the security check. For mutations, move the authorization decision before the update and check domain invariants at update time.

## 7. Transactions and advisor ordering: don't guess rollback

A method having both `@Transactional` and `@PostAuthorize` is affected by **at least two advisors**. If transaction advice sits **inside** the after-method interceptor, one path can be:

~~~text
outer @PostAuthorize advice
  inner @Transactional advice
    BEGIN
    target method body UPDATE
    COMMIT
  @PostAuthorize checks -> DENY
caller sees 403 / AccessDeniedException
~~~

If the transaction advisor **wraps outside** the post-check, the `@PostAuthorize` exception can cross the transaction boundary before the commit decision, and rollback can happen for DB writes within the transaction according to rules. Both descriptions are **nesting models**, not a fixed guarantee for every Spring Boot version/setup.

Spring Framework documentation defines advice precedence and default transaction advisor order; Spring Security 6.5 documentation also shows how to adjust the order of enabling transactions/method security when a post-check must be used on a write. Even so, **adjusting advisor order does not make this strategy safe by default**:

- Emails already sent do not automatically roll back.
- Money transfer APIs or out-of-process webhooks do not roll back with the DB.
- Message brokers may already have received messages.
- A `REQUIRES_NEW` transaction or another service can commit independently.
- Files/caches/telemetry can be modified independently.
- Auto-rolling-back transactional tests can hide a production bug.

Therefore, observe **DB state after the transaction**, outbox/broker, external calls, and retry behavior—not just the exception. `@Transactional(readOnly = true)` also does not guarantee the whole body is side-effect-free: code can still call APIs, caches, or the file system even in a read-only transaction.

## 8. Safer design for write operations

For invoice approval, guard permissions upfront and check business invariants inside the transaction:

~~~java
@Service
public class InvoiceApprovalService {
    private final InvoiceRepository invoices;
    private final ApprovalPolicy policy;
    private final OutboxRepository outbox;

    public InvoiceApprovalService(InvoiceRepository invoices,
                                  ApprovalPolicy policy,
                                  OutboxRepository outbox) {
        this.invoices = invoices;
        this.policy = policy;
        this.outbox = outbox;
    }

    @PreAuthorize("hasAuthority('INVOICE_APPROVE')")
    @Transactional
    public ApprovalReceipt approve(long id) {
        Invoice invoice = invoices.findForUpdate(id)
            .orElseThrow(InvoiceNotFoundException::new);

        Authentication actor =
            SecurityContextHolder.getContext().getAuthentication();
        if (!policy.mayApprove(actor, invoice)) {
            throw new AccessDeniedException("Access denied");
        }

        invoice.approveIfPending();
        outbox.recordApproved(invoice);
        return new ApprovalReceipt(invoice.getId());
    }
}
~~~

This is a **Spring structural pattern requiring real imports/beans/DTOs/repositories/transactions**, not standalone JDK-compilable code. In production you must use locking/versioning or conditional updates to prevent state changing between check and write. `policy.mayApprove` must check tenant, owner, separation of duties, still-PENDING status, and current permissions on **server data**. Events written to the transactional outbox should be dispatched post-commit via an idempotent worker.

Thus, a request denied **before the update** does not execute the mutation. Do not rely on `@PostAuthorize` on `ApprovalReceipt` to block an already-completed update. For read results containing sensitive data, you can still use post-checks on **read-only** methods, but that is a separate concern from approval authorization.

## 9. “Body has not run” does not mean the system did nothing at all

An example:

~~~java
@PreAuthorize("@invoicePolicy.mayRead(authentication, #id)")
public InvoiceView read(long id) {
    return repository.loadView(id);
}
~~~

If the policy returns false:

- `repository.loadView(id)` in the body **has not run**.
- The `invoicePolicy` bean may **already have run a SELECT** to look up owner/tenant.
- The HTTP authentication filter may have queried the user store.
- The controller may have called logging/audit before the service.
- Another AOP advisor may have created a trace.

So an accurate log is:

~~~text
stage=BEFORE_METHOD
decision=DENY
target_body_invoked=false
policy_database_reads=possible
other_filters_or_advice=may_have_run
~~~

To stay safe, policy beans should **not produce business side effects**. Evaluating permissions is the policy's only job; if it sends emails or updates state while evaluating SpEL, that is a design flaw. Avoid concluding zero SQL or logs occurred solely from a pre-denial.

Conversely, a post-denial means **the body returned normally**, yet a pure read/compute body may have caused no mutations. State specifically which queries, changes, or events occurred rather than guessing from annotations.

## 10. Standalone Java 17: proving timing with counters and events

This example simulates pre-checks and post-checks in **plain Java**; no Spring Security is required and it does not simulate transactions/SpEL. It uses `bodyRuns` to count body executions, and `emittedEvents` to represent produced side effects.

Save with exact filename **`AfterMethodDecisionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

public class AfterMethodDecisionDemo {
    record Actor(String name, Set<String> permissions) {}
    record Invoice(long id, String owner, String status) {}

    static final class InvoiceService {
        final AtomicInteger bodyRuns = new AtomicInteger();
        final List<String> emittedEvents = new ArrayList<>();

        Invoice preGuardedRead(Actor actor, Invoice invoice) {
            if (actor == null || !actor.permissions().contains("INVOICE_READ")
                    || !actor.name().equals(invoice.owner())) {
                throw new SecurityException("Denied before invocation");
            }
            bodyRuns.incrementAndGet();
            return invoice;
        }

        Invoice postGuardedRead(Actor actor, Invoice invoice) {
            Invoice result = loadInvoice(invoice);
            if (actor == null || !actor.permissions().contains("INVOICE_READ")
                    || !actor.name().equals(result.owner())) {
                throw new SecurityException("Denied after invocation");
            }
            return result;
        }

        String unsafePostGuardedApproval(Actor actor, Invoice invoice) {
            String result = approveAndEmit(invoice);
            if (actor == null || !actor.permissions().contains("INVOICE_APPROVE")
                    || actor.name().equals(invoice.owner())) {
                throw new SecurityException("Denied after mutation");
            }
            return result;
        }

        String safePreGuardedApproval(Actor actor, Invoice invoice) {
            if (actor == null || !actor.permissions().contains("INVOICE_APPROVE")
                    || actor.name().equals(invoice.owner())) {
                throw new SecurityException("Denied before mutation");
            }
            return approveAndEmit(invoice);
        }

        private Invoice loadInvoice(Invoice invoice) {
            bodyRuns.incrementAndGet();
            return invoice;
        }

        private String approveAndEmit(Invoice invoice) {
            bodyRuns.incrementAndGet();
            emittedEvents.add("invoice-" + invoice.id() + "-approved");
            return "approved-" + invoice.id();
        }
    }

    public static void main(String[] args) {
        InvoiceService service = new InvoiceService();
        Actor alice = new Actor("alice", Set.of("INVOICE_READ"));
        Actor reviewer = new Actor("reviewer", Set.of("INVOICE_APPROVE"));
        Invoice bobInvoice = new Invoice(41L, "bob", "PENDING");
        Invoice aliceInvoice = new Invoice(42L, "alice", "PENDING");

        try {
            service.preGuardedRead(alice, bobInvoice);
        } catch (SecurityException ex) {
            System.out.println("Pre denied: " + ex.getMessage());
        }
        System.out.println("Body after pre deny: " + service.bodyRuns.get());

        try {
            service.postGuardedRead(alice, bobInvoice);
        } catch (SecurityException ex) {
            System.out.println("Post denied: " + ex.getMessage());
        }
        System.out.println("Body after post deny: " + service.bodyRuns.get());
        System.out.println("Allowed post read id: "
                + service.postGuardedRead(alice, aliceInvoice).id());
        System.out.println("Body after allowed read: " + service.bodyRuns.get());

        try {
            service.unsafePostGuardedApproval(alice, aliceInvoice);
        } catch (SecurityException ex) {
            System.out.println("Unsafe approval denied: " + ex.getMessage());
        }
        System.out.println("Events after unsafe denial: "
                + service.emittedEvents);
        try {
            service.safePreGuardedApproval(alice, aliceInvoice);
        } catch (SecurityException ex) {
            System.out.println("Safe approval denied: " + ex.getMessage());
        }
        System.out.println("Events after safe denial: "
                + service.emittedEvents);
        System.out.println("Reviewer approval: "
                + service.safePreGuardedApproval(reviewer, aliceInvoice));
        System.out.println("Events final: " + service.emittedEvents);
        System.out.println("Body final: " + service.bodyRuns.get());
    }
}
~~~

Compile and run on **JDK 17 or higher**:

~~~bash
javac --release 17 AfterMethodDecisionDemo.java
java AfterMethodDecisionDemo
~~~

Verified stdout:

~~~text
Pre denied: Denied before invocation
Body after pre deny: 0
Post denied: Denied after invocation
Body after post deny: 1
Allowed post read id: 42
Body after allowed read: 2
Unsafe approval denied: Denied after mutation
Events after unsafe denial: [invoice-42-approved]
Safe approval denied: Denied before mutation
Events after safe denial: [invoice-42-approved]
Reviewer approval: approved-42
Events final: [invoice-42-approved, invoice-42-approved]
Body final: 4
~~~

The two numbers **0** and **1** prove the difference: pre-denial does not enter the body; post-denial already entered the body. The **non-empty** event list after unsafe post-denial shows that blocking the result does not erase side effects. Safe pre-denial adds no events. The demo aims to illustrate timing, **not to prove Spring DB commits/rollbacks behave in one fixed way**.

## 11. Testing real method security with counters and Spring proxies

If a test only does `assertThrows(AccessDeniedException.class)`, you still cannot tell whether the exception came before or after the body. Use a Spring-managed fixture with counters:

~~~java
@Service
class TimingFixtureService {
    final AtomicInteger preBodyRuns = new AtomicInteger();
    final AtomicInteger postBodyRuns = new AtomicInteger();

    @PreAuthorize("hasAuthority('REPORT_ACCESS')")
    public String beforeGuard() {
        preBodyRuns.incrementAndGet();
        return "executed";
    }

    @PostAuthorize("returnObject == authentication.name")
    public String afterGuard() {
        postBodyRuns.incrementAndGet();
        return "someone-else";
    }
}
~~~

This is a fixture class **requiring imports and Spring Test setup**, not a complete file. Test skeleton:

~~~java
@SpringBootTest
class TimingMethodSecurityIT {
    @Autowired TimingFixtureService fixture;

    @Test
    @WithMockUser(username = "alice", authorities = "OTHER")
    void beforeDeniedNoBody() {
        fixture.preBodyRuns.set(0);
        assertThrows(AccessDeniedException.class, fixture::beforeGuard);
        assertEquals(0, fixture.preBodyRuns.get());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "OTHER")
    void afterDeniedBodyAlreadyRan() {
        fixture.postBodyRuns.set(0);
        assertThrows(AccessDeniedException.class, fixture::afterGuard);
        assertEquals(1, fixture.postBodyRuns.get());
    }
}
~~~

The project needs `spring-boot-starter-test`, `spring-security-test`, JUnit imports, and test context. Singleton counters are only for fixtures with proper reset/isolated execution. Never use global body counters containing user identities in production.

Thorough testing requires:

| Scenario | Evidence needed |
| --- | --- |
| `@PreAuthorize` false | Body counter = 0, exception thrown before method. |
| `@PostAuthorize` false | Body counter = 1, caller receives no normal result. |
| `@PostAuthorize` true | Body counter = 1, caller receives result. |
| Body throws exception before return | Exception from body, not misattributed to post-denial. |
| Self-invocation | Detect annotation not running due to proxy bypass. |
| HTTP 403 from security filter | Service body = 0, yet not proof that method annotation denied. |
| Post-denial after DB write | Check DB **after transaction** and outbox/messages, not just exception. |
| Post-denial after external call | Fake broker/HTTP server/spies show the effect occurred. |
| Data of another owner/tenant | No out-of-scope result delivered; no unauthorized side effects. |

**Test transaction warning:** A test annotated with `@Transactional` can auto-roll back at the end, hiding SQL executed by the service before the post-check. When testing commit/rollback, set production-like boundaries and observe state **outside the test transaction**; also check outbox, emails, and retry/idempotency. `MockMvc` 403 is not enough to prove order without counters/spies.

## 12. When to use post-checks and when to move authorization earlier

| Business operation | Primary approach | Explanation |
| --- | --- | --- |
| Reading a single object needing owner inspection in result | `@PostAuthorize`, optionally combined with pre-authority and scoped query | Blocks result if out of scope; body must cause no side effects. |
| Returning large/paginated lists | Pre-authority + repository WHERE tenant/owner | Avoids loading out-of-scope objects; accurate pagination. |
| Approving invoices, changing status, payments | Pre-check + domain invariant inside transaction | Do not wait until post-check to decide write permission. |
| Sending emails/webhooks | Check before sending, outbox and idempotency when appropriate | External effects do not roll back with DB. |
| Exporting private files | Check permissions before generating/streaming file | Do not generate or leak large data and then DENY. |
| Scheduler/message consumer calling service | Method/domain policy with valid security identity | No HTTP filter runs automatically for such calls. |
| Method reading object but doing audit/caching | Post-check only if audit/cache does not leak out-of-scope data | Read-only does not necessarily mean side-effect-free. |

Safe rule of thumb: if a method **can produce an irreversible effect**, authorization to perform that effect must happen **before the effect**. If the permission condition is only known after loading the object, **load + check permission** in the read step and enforce policy before any state-mutating operation. Never treat throwing a late exception as an undo mechanism.

## 13. Diagnostic workflow for “returns 403 yet business logic still ran”

1. Identify user/tenant, request ID, and which HTTP rules are applied.
2. Check whether an HTTP filter blocked before the controller.
3. Confirm the service is called **through a Spring AOP proxy**.
4. Separate exception origin: before-interceptor, body/domain policy, or after-interceptor.
5. Observe body counters/method spies: do not infer from response status.
6. Inspect SQL SELECT and UPDATE **by call site**, distinguishing queries inside pre-policy from queries inside the body.
7. On post-check false, verify DB state, commit/rollback, broker/outbox, email/webhook, files/cache.
8. Check transaction advisor ordering on the actual dependency versions; do not guess from annotation order.
9. Check whether client retries or message redeliveries create duplicate side effects.
10. Move authorization earlier to pre-check and keep invariant checks inside the transaction.
11. Add tests for DENY/ALLOW, different owner, different tenant, body exception, and concurrent update.
12. Do not log JWTs, PII, or full report/returnObject payloads for diagnostics.

A good log might include `authorization_stage=BEFORE_METHOD` or `AFTER_METHOD`, `decision=DENY`, `target_body_invoked=true/false` (actually instrumented), and correlation ID. Never assert committed or rolled-back status without evidence from persistence/outbox.

## 14. Pre-deployment checklist

- [ ] `@EnableMethodSecurity` is active and service is called through a Spring proxy.
- [ ] Method is classified: read-only vs. having DB writes/external side effects.
- [ ] `@PostAuthorize` is not used as the sole protection layer for mutations.
- [ ] Body that only reads and returns a post-checked object does not log/cache/send out-of-scope data before DENY.
- [ ] Owner/tenant data is verified from the server, never trusting client DTOs/headers.
- [ ] Null `returnObject` and not-found have clear contracts.
- [ ] General permissions and domain invariants are checked before writes, guarding against TOCTOU.
- [ ] Transaction advisor ordering/rollback is genuinely tested, not inferred from 403.
- [ ] External effects use outbox/idempotency/compensation where appropriate.
- [ ] Pre-denial test proves body has not run; post-denial test proves body already ran.
- [ ] Exceptions thrown inside the body are tested separately from post-denials.
- [ ] HTTP filter-denials are tested separately from method-denials.
- [ ] DB/outbox state is tested on DENY and on client retries.
- [ ] Logging/auditing names the exact denial stage without leaking sensitive data.

**Conclusion:** In Spring method security, `@PreAuthorize` can deny **before the target method body runs**, whereas `@PostAuthorize` inspects **`returnObject` after the body has run**. Both can cause the caller to see 403, yet a post-denial does not erase mutations or side effects that already occurred. Use post-checks for **read** data when appropriate, and use **authorization before side effects + invariant checks at write time** for business actions that can change state.

### Official references

- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — @PreAuthorize API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/prepost/PreAuthorize.html)
- [Spring Security 6.5 — @PostAuthorize API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/prepost/PostAuthorize.html)
- [Spring Security 6.5 — After-Method Interceptor API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/method/AuthorizationManagerAfterMethodInterceptor.html)
- [Spring Framework — @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — AOP Advice Ordering](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html)
