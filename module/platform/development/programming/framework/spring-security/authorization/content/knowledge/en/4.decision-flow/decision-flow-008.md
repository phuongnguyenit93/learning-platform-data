# Pre- and Post-Method Interceptors and Policy Enforcement Points

> **Module:** Spring Security - authorization  
> **Group:** Decision Flow  
> **Objective:** Understand precisely when a method call is blocked **before execution**, when the result is checked **after the method runs**, where interceptors/`AuthorizationManager` sit, how to combine business-data policies, and how to test so side effects never happen before denial.

## 1. Why does a method need multiple permission-check moments?

Suppose a system has methods `readReport(42)` and `approvePayment(42)`. User Alice has the `report:read` authority, yet must not read reports belonging to another tenant. User Bob has the `payment:approve` permission, yet must not approve a payment he created himself.

There are at least three places an application can check:

1. **Before the method (pre-invocation):** Does Alice have `report:read`? Does Bob have `payment:approve`? From the ID argument, tenant, and trusted data, can we determine whether the caller may enter the method?
2. **After the method (post-invocation):** Does the `Report` returned by the read method have an `owner` matching the caller? Sometimes this information is only available **after loading the record**.
3. **Inside the use case/domain (policy enforcement):** After loading the record inside a transaction, verify tenant, owner, creator, state, limits, business locks, and necessary rules **before mutating data**.

An ALLOW outcome at the HTTP layer or in a pre-interceptor only allows proceeding to the next stage. It **does not automatically grant all permissions on the object**. For state-changing operations, the essential principle is:

> A rule must be checked **before the side effect it is responsible for guarding**, within an appropriately consistent data scope. A check after the method completes cannot guarantee that all side effects are undone.

## 2. What is an interceptor in Spring Security?

In Spring Security Servlet applications, two groups of interceptors are easily confused:

| Layer | Checkpoint | Unit being protected |
| --- | --- | --- |
| **Servlet filter / `AuthorizationFilter`** | Before an HTTP request is handled by an application endpoint | `HttpServletRequest`, path, method, authority |
| **Method-security interceptor** | Wraps a method call on a Spring-managed bean | Method, arguments, `Authentication`, return value |
| **Domain/application policy** | At application-designed use cases/state-change points | Actor, resource, tenant, state, transaction |

`AuthorizationFilter` is not a "pre-method interceptor": it participates in the **HTTP filter chain**. Method-security interceptors operate via **Spring AOP advisors/proxies** per configuration; the same method can be invoked from a controller, a message consumer, or another bean.

A method interceptor is a form of *advice* wrapping an invocation:

```text
Caller
  |
  v
Spring AOP proxy
  |
  +-- BEFORE advice: check permission beforehand
  |       | DENY -> stop, do not invoke target
  |       v ALLOW
  |
  +-- TARGET METHOD: execute method body
  |       | throws error -> exception flow
  |       v return value
  |
  +-- AFTER advice: check based on return value
          | DENY -> do not return value to caller normally
          v ALLOW
Caller receives result
```

This is a conceptual model of a method carrying both `@PreAuthorize` and `@PostAuthorize`, not a promise that all other advisors (`@Transactional`, caching, retry, logging, etc.) run in the exact positions illustrated. Actual advisor order can be configured, so never infer transaction behavior from annotation order in source code.

## 3. Enabling method security: a dependency does not mean automatic interception

In Spring Security 6.x, `@EnableMethodSecurity` enables method authorization infrastructure and by default registers advisors for `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter`. Adding the Spring Security starter alone **does not automatically enable** method-level authorization.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

This is a Spring configuration snippet, not standalone Java `main` runnable with `javac` alone.

Older codebases may show `@EnableGlobalMethodSecurity(prePostEnabled = true)`; modern configuration prefers `@EnableMethodSecurity` and `AuthorizationManager`. If `@Secured` or JSR-250 annotations like `@RolesAllowed` are needed, they have separate opt-in flags, e.g.:

```java
@EnableMethodSecurity(
    securedEnabled = true,
    jsr250Enabled = true
)
```

Do not mix every annotation type just because the framework supports them; pick one auditable style, usually preferring `@PreAuthorize` for expression conditions and custom policies.

**Critical condition:** the advisor must actually be applied to the method through the corresponding proxy/AspectJ weaving. An object instantiated manually with `new` instead of obtained as a Spring bean, an internal `this` call, or a method that cannot be intercepted under the config may not be protected as expected.

## 4. Pre-method checkpoint: @PreAuthorize

Example:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @PreAuthorize("hasAuthority('report:read')")
    public String readSummary(long reportId) {
        return "Summary " + reportId;
    }
}
```

When a Spring client calls `reportService.readSummary(42)` **through the proxy**:

1. The proxy receives `MethodInvocation` (method, target, arguments).
2. `AuthorizationManagerBeforeMethodInterceptor` has a pointcut matching `@PreAuthorize`.
3. `PreAuthorizeAuthorizationManager` evaluates the expression.
4. `MethodSecurityExpressionHandler` builds an evaluation context with `Authentication` and invocation details.
5. `hasAuthority('report:read')` checks the caller's `GrantedAuthority` set.
6. **ALLOW:** the real method executes.
7. **DENY:** the interceptor throws an access-denial exception (typically in the `AccessDeniedException` hierarchy); the method body does not run.

In pre-authorization expressions, parameters are already available:

```java
@PreAuthorize(
    "hasAuthority('report:read') and @reportPolicy.canRead(authentication, #reportId)"
)
public ReportDto readReport(long reportId) {
    return reportRepository.loadDto(reportId);
}
```

`@reportPolicy` is an application-defined Spring bean, while `#reportId` requires Spring Security to resolve parameter names (via appropriate compiler/metadata/annotation configuration). If parameter-name binding is unreliable, configure the build or specify explicit parameter names rather than assuming the expression always extracts the ID.

**Before the method runs, there is no return value.** You can decide from `Authentication`, method, arguments, and policy services, but you cannot reference `returnObject`, which the method has not produced yet. If the policy needs to load a resource from the database, a helper can query it here; however, watch out for duplicate loads, transaction timing, and races between pre-check and update.

## 5. Post-method: @PostAuthorize

`@PostAuthorize` evaluates **after the method returns successfully**. It suits certain read scenarios where the permission rule depends on the returned value:

```java
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentQueryService {
    private final DocumentRepository repository;

    public DocumentQueryService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PostAuthorize("returnObject.ownerId == authentication.name")
    public DocumentView read(long id) {
        return repository.getView(id);
    }
}
```

The snippet above is an **integration snippet**, not a standalone program: `DocumentRepository`, `DocumentView`, and `getView` are defined by the application. Ensure SpEL can access an `ownerId` property on `DocumentView` and that the principal name is normalized to the same type as owner ID. With records, getters, or custom objects, property syntax can vary; always test against the real type.

Flow:

1. The proxy receives the `read(id)` call.
2. The target method **runs first**, possibly querying the DB and constructing `DocumentView`.
3. `AuthorizationManagerAfterMethodInterceptor` applies the `@PostAuthorize` pointcut.
4. `PostAuthorizeAuthorizationManager` evaluates the expression with the `returnObject` variable.
5. If the owner does not match, an exception is thrown; the caller does not receive the return value as a successful call.
6. If it matches, the proxy forwards the result to the caller.

Crucial point: "not returning the result to the caller" **does not mean** "the method did not run". The query was already sent. Logs, metrics, or side effects inside the method body may have already occurred.

If the method throws an exception before returning, do not expect a `returnObject`-based expression to run to validate the result. For write operations, mandatory rules must be enforced **before mutation**; never use post-checks as the primary permission barrier.

## 6. Comparing pre/post timing in a table

| Property | `@PreAuthorize` | `@PostAuthorize` |
| --- | --- | --- |
| Timing | Before the method body runs | After the method returns a result |
| Available data | Authentication, method, arguments, beans/policies | Authentication, method, and `returnObject` |
| On DENY | Target has not run for this invocation | Target **has already run** |
| Used for | Blocking missing permissions before operations; checking argument conditions | Checking permission on the result of a read method |
| Suitable for writes? | Yes, if the policy has sufficient consistent facts | Should not be the primary guard |
| Usable for owner permissions? | Yes, if loading/passing the resource or ID properly to policy | Yes, when owner is only known after reading |
| Main risks | TOCTOU, duplicate resource loading, SpEL/parameter binding | Side effects already happened, data loaded, transaction order |
| What caller sees on deny | Exception/handler depending on context | Exception/handler depending on context |

**Design rule:** for pure read queries whose return value needs ownership checking, `@PostAuthorize` can be useful. For commands like `approvePayment`, `changeOwner`, `deleteDocument`, or `sendEmail`, use pre-authorization or a use-case guard before side effects.

## 7. Classes involved during Spring AOP decisions

When `@EnableMethodSecurity` is enabled, Spring Security registers specialized interceptors/advisors, commonly:

| Annotation | Typical interceptor / manager | Timing |
| --- | --- | --- |
| `@PreAuthorize` | `AuthorizationManagerBeforeMethodInterceptor` → `PreAuthorizeAuthorizationManager` | Pre-method |
| `@PostAuthorize` | `AuthorizationManagerAfterMethodInterceptor` → `PostAuthorizeAuthorizationManager` | Post-method |
| `@PreFilter` | `PreFilterAuthorizationMethodInterceptor` | Filters input before method |
| `@PostFilter` | `PostFilterAuthorizationMethodInterceptor` | Filters returned collection after method |
| `@Secured` (if enabled) | Before-method interceptor → `SecuredAuthorizationManager` | Pre-method |
| JSR-250 (if enabled) | Before-method interceptor → `Jsr250AuthorizationManager` | Pre-method |

Each annotation type has its **own pointcut** and its own interceptor. From an AOP standpoint, an invocation matching multiple advisors passes through them in their respective order. Never assume an annotation on a controller protects every method of the same name elsewhere; pointcuts match by actual bean and type.

`AuthorizationManager` types can accept `Supplier<Authentication>` to defer identity lookup until needed. For pre-method checks, the protected object type is typically `MethodInvocation`; for post-method checks, Spring Security uses an invocation-with-result context (such as `MethodInvocationResult` in the corresponding API). Exact signatures of `authorize`/`check` can vary across versions; when writing custom managers, check the API for your exact dependency version rather than blindly copying old snippets.

### Why separate the interceptor and the manager?

The **interceptor** is the enforcement component: it wraps the invocation, invokes the manager, and proceeds or denies. The **`AuthorizationManager`** decides: it evaluates `Authentication` and the protected object. The **policy service** is where the business can centralize rules like `canApprove(actor, payment)`.

Separating these responsibilities lets you swap policies without writing custom AOP advice, or change checkpoints without scattering permissions across every controller.

## 8. Multiple annotations on one method: how are they combined?

Example of a document-reading method:

```java
@PreAuthorize("hasAuthority('document:read')")
@PostAuthorize("returnObject.ownerId == authentication.name")
public DocumentView readDocument(long id) {
    return repository.getView(id);
}
```

**Both** conditions must hold:
- Missing `document:read` → blocked before loading.
- Has `document:read`, but document belongs to another user → method loads it, then post-check denies.
- Has authority and valid owner → result is returned normally.

Different method-security annotations are evaluated sequentially; logically, all relevant checks must pass. **Never repeat the same `@PreAuthorize` twice on the same method.** For complex conditions, use SpEL `and`/`or` operators or delegate to a policy bean with clearly named methods and dedicated tests.

Example accepting only users with role AUDITOR **and** read permission:

```java
@PreAuthorize(
    "hasRole('AUDITOR') and hasAuthority('report:read')"
)
public ReportView exportReport(long id) {
    return repository.getReport(id);
}
```

`hasRole('AUDITOR')` checks the `ROLE_AUDITOR` authority by default. `hasAuthority('report:read')` matches that exact string and is not inferred from the AUDITOR role. If you changed the default prefix, verify your actual configuration.

### Be careful with `or` expressions

```java
// Could accidentally bypass tenant checks if ADMIN is assumed to go anywhere:
@PreAuthorize(
    "hasRole('ADMIN') or (@tenantPolicy.inTenant(authentication, #id) and hasAuthority('report:read'))"
)
```

If admins must also obey tenant isolation, group the conditions differently. Every bypass branch is a critical policy decision, not merely a SpEL syntax detail.

## 9. Collection filtering: @PreFilter and @PostFilter

These two annotations **differ** from allowing/denying the entire invocation:

- `@PreFilter`: evaluates each element of a supported collection parameter, keeping valid elements before calling the method.
- `@PostFilter`: evaluates each element of a supported returned collection/result after the method runs, returning only accepted elements.
- Inside filter expressions, `filterObject` is the element under evaluation; with multiple filterable arguments, you may need to specify the target parameter.
- Supported collection/stream/map types and mutation behavior depend on API/version; test against actual types. Never assume every `Iterable`, database stream, or immutable collection can be modified/filtered safely.

Illustrative example on a query method:

```java
@PostFilter("filterObject.ownerId == authentication.name")
public List<DocumentView> findRecentDocuments() {
    return repository.findRecentDocuments();
}
```

This snippet only illustrates syntax; `DocumentView` and `repository` are application types. It carries three risks:
1. The repository may have already loaded **unauthorized documents** into application memory before filtering.
2. Pagination performed before filtering skews page sizes and total record counts.
3. Another path (export, download API) might forget the filter, leaking data.

Therefore, for large lists or multi-tenant data, **push scoping into the database query** (`WHERE tenant_id = ?`, ACL/visibility joins) before fetching; use `@PostFilter` only as a supplement where genuinely appropriate, never as a replacement for primary data boundaries.

For commands accepting multiple IDs to delete, do not use `@PreFilter` and silently treat filtered-out elements as "partial deletion succeeded" if the API requires all-or-nothing. Transaction and UX rules must explicitly state whether partial success is allowed or the whole batch must be rejected.

## 10. Policy enforcement point: pre-method, inside method, or post-method?

A real system typically involves three kinds of information:

| Information | Available before the call? | Reasonable checkpoint |
| --- | --- | --- |
| Actor's `invoice:approve` authority | Yes, if `Authentication` is trusted | `@PreAuthorize` or HTTP guard |
| Invoice ID in arguments | Yes | Pre-check can use ID, but must authenticate and query in right scope |
| Actual owner/tenant of invoice | May require DB query | Domain policy after loading resource; or dedicated pre-policy query |
| Current `PENDING`/`PAID` state | Must read consistent data | Inside use case/transaction before update |
| Just-read DTO result | Only available after method | `@PostAuthorize` if method has no side effects |
| Permission to modify ACL or share object | Requires resource/actor check | Dedicated policy in the permission-changing use case |

Place policies based on **data scope and when data is available**. There is no need to cram entire business policies into hard-to-audit SpEL strings. A component with a clear interface like `InvoiceAuthorizationPolicy.canApprove(actor, invoice)` centralizes and makes logic unit-testable.

Likewise, never assume `@PreAuthorize` always runs before opening a transaction, or `@PostAuthorize` always runs inside a transaction. `@Transactional` is another AOP advisor; `@Order` configuration and proxy mechanics govern nesting order. When a policy depends on data that can change concurrently, put mandatory checks inside the use case with appropriate transactions/locks.

## 11. Application example: method with general permission and business rules

Suppose only users with the `payment:approve` authority may participate in approvals, yet approving a payment also requires:
- The payment belongs to the actor's active tenant.
- The payment is in `PENDING` state.
- The actor is not the payment creator (*separation of duties*).
- The amount is within the actor's limit.
- No duplicate approval exists and the version matches.

A service design might look like:

```java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentApprovalService {
    private final ActorResolver actorResolver;
    private final PaymentRepository payments;
    private final PaymentPolicy policy;

    public PaymentApprovalService(
            ActorResolver actorResolver,
            PaymentRepository payments,
            PaymentPolicy policy) {
        this.actorResolver = actorResolver;
        this.payments = payments;
        this.policy = policy;
    }

    @PreAuthorize("hasAuthority('payment:approve')")
    @Transactional
    public void approve(long paymentId) {
        Actor actor = actorResolver.requireActor();
        Payment payment = payments
            .findPendingForUpdate(paymentId, actor.tenantId())
            .orElseThrow(PaymentNotFoundException::new);

        if (!policy.mayApprove(actor, payment)) {
            throw new AccessDeniedException("Payment approval denied");
        }

        payment.approveBy(actor.id());
    }
}
```

**Note:** this is an *integration* snippet, not a standalone file. `Actor`, `ActorResolver`, `PaymentRepository`, `PaymentPolicy`, `Payment`, `findPendingForUpdate`, and exceptions are **application-defined types/contracts**. The name `findPendingForUpdate` suggests a locking or versioned query, but it must be properly implemented with real JPA/database semantics—no locking arises automatically from a method name.

Explanation:
1. Pre-interceptor blocks callers lacking the general authority; the method body does not run.
2. Inside the transaction, the actor is resolved from trusted `Authentication`; never accept client-declared `actorId` and `tenantId` as proof of permission.
3. The repository loads the payment scoped to the right tenant and state within the transaction using a consistency strategy.
4. `PaymentPolicy` denies self-approval, limit violations, or lack of object permission.
5. Only afterward is `payment.approveBy` called to make the mutation.

**Do not replace the above with**:

```java
@PostAuthorize("returnObject.approvedBy == authentication.name")
public Payment approve(long paymentId) {
    // Performs payment update and/or calls external gateway.
    // Denying after return is too late to guard the mutation.
}
```

If the domain has already written to the DB, sent an email, or called a payment gateway, denying afterward does not guarantee rollback. A transaction rollback may occur in some configurations, yet it cannot undo messages, network calls, file writes, or out-of-transaction side effects; advisor/commit order must also be verified. Therefore, **write authorization belongs before side effects**, not in a post-return check.

## 12. Standalone Java 17+ example: clearly seeing before and after

The following plain Java example simulates interceptor order. There is no Spring, AOP, token, or database; the `Actor` object is mocked as **already authenticated by the system**. The goal is to observe the difference between "target did not run" and "target ran yet its result was withheld".

Save as `MethodBoundaryDemo.java`:

```java
import java.util.Set;

public class MethodBoundaryDemo {
    record Actor(String id, Set<String> authorities) {}
    record Document(String ownerId, String content) {}

    private static int readCalls = 0;
    private static int writeCalls = 0;

    static boolean has(Actor actor, String authority) {
        return actor != null && actor.authorities().contains(authority);
    }

    static String read(Actor actor, Document document) {
        // Simulates @PreAuthorize("hasAuthority('document:read')")
        if (!has(actor, "document:read")) {
            return "DENY @BEFORE";
        }

        // Target method HAS EXECUTED here.
        readCalls++;
        String loaded = document.content();

        // Simulates @PostAuthorize: check return object.
        if (!document.ownerId().equals(actor.id())) {
            return "DENY @AFTER";
        }
        return "ALLOW " + loaded;
    }

    static String write(Actor actor, Document document) {
        // General permission and resource policy must be evaluated BEFORE writing.
        if (!has(actor, "document:write")) {
            return "DENY @BEFORE";
        }
        if (!document.ownerId().equals(actor.id())) {
            return "DENY @POLICY";
        }

        writeCalls++;
        return "ALLOW updated";
    }

    public static void main(String[] args) {
        Actor alice = new Actor("alice",
            Set.of("document:read", "document:write"));
        Actor bob = new Actor("bob",
            Set.of("document:read", "document:write"));
        Actor guest = new Actor("guest", Set.of());
        Document doc = new Document("alice", "draft-42");

        System.out.println("Guest read: " + read(guest, doc));
        System.out.println("Bob read: " + read(bob, doc));
        System.out.println("Alice read: " + read(alice, doc));
        System.out.println("Bob write: " + write(bob, doc));
        System.out.println("Alice write: " + write(alice, doc));
        System.out.println("Target reads: " + readCalls);
        System.out.println("Target writes: " + writeCalls);
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac MethodBoundaryDemo.java
java MethodBoundaryDemo
```

**Exact** output:

```text
Guest read: DENY @BEFORE
Bob read: DENY @AFTER
Alice read: ALLOW draft-42
Bob write: DENY @POLICY
Alice write: ALLOW updated
Target reads: 2
Target writes: 1
```

Interpretation:
- Guest lacks read authority: pre-check denies **before** incrementing `readCalls`.
- Bob has read authority but is not the owner: the target ran and incremented `readCalls`, then the post-check denied.
- Alice has both permission and ownership: returns the result successfully.
- Bob has write authority but is not the owner: domain policy denies **before** incrementing `writeCalls`.
- Alice has both permission and ownership: write proceeds, `writeCalls` increments.

This is a **verifiable simulation**, not the actual implementation of `PreAuthorizeAuthorizationManager` or `PostAuthorizeAuthorizationManager`. Spring Security uses AOP interceptors, SpEL, authentication, and exceptions; in the demo, results are represented as strings to highlight blocking timing.

## 13. Checkpoints also depend on who is calling

Method security is not just for HTTP controllers. Call paths can include:

```text
REST controller --------------+
GraphQL resolver -------------+--> Spring proxy --> Method interceptor --> use case
Message consumer -------------+
Scheduled job ----------------+
Other Spring service bean ----+
```

The benefit is reusing method protection across multiple entry points. However:

- An HTTP controller guarded by `authorizeHttpRequests` does not mean a message consumer is protected.
- A method interceptor only works for invocations **matching the proxy/advisor mechanism**.
- Background tasks may lack an interactive user `SecurityContext`; you must design a service identity or trusted delegated actor.
- If the caller is a system job, decide how to grant scoped permissions and audit them, never defaulting to full admin privileges.
- When business policy requires a specific actor, keep context explicit; avoid fallbacks like "no user → skip authorization".

In Servlet apps, `SecurityContextHolder` defaults to binding to the current thread. `@Async` or other executors do not automatically preserve the right context; `DelegatingSecurityContext...` wrappers can help propagate context where appropriate while avoiding holding identities too long. In WebFlux, use Reactor's `ReactiveSecurityContextHolder` instead of assuming Servlet `ThreadLocal`.

## 14. The self-invocation trap: annotation present, interceptor skipped

Look at this example:

```java
@Service
class TransferService {
    public void runBatch() {
        // Calling on 'this' within the same object can bypass the proxy.
        transferOne();
    }

    @PreAuthorize("hasAuthority('transfer:execute')")
    public void transferOne() {
        // Perform money transfer.
    }
}
```

When Spring AOP uses proxies, a call from `runBatch()` to `this.transferOne()` **does not pass through the proxy** in standard configurations. Consequently, `@PreAuthorize` on `transferOne` must not be assumed to run on this path.

Design solutions depending on requirements:

1. Place the annotation on the **entry point** `runBatch` if the entire batch shares the same permission requirement.
2. Extract `transferOne` into a dedicated Spring bean and inject that bean into `runBatch` so the call crosses the proxy.
3. Place mandatory policy checks inside the use case/domain service and call them explicitly before any side effect.
4. Consider AspectJ weaving if your organization genuinely requires interception on internal calls, weighing the configuration and testing cost.

**Do not fix it by** calling `AopContext.currentProxy()` casually or stacking nested proxies without evaluating complexity; use that only when genuinely required and the team understands its limits.

Other cases to verify: private/final methods, final classes, interface-based JDK dynamic proxies, CGLIB proxies, manually `new`-ed services, annotations on interfaces vs. implementations, and Kotlin variants (classes are final by default unless opened). Testing under the real build configuration is far stronger evidence than guessing from annotations.

## 15. What happens on DENY?

Method-security interceptors typically throw `AccessDeniedException` or a related subclass when denying. This differs from a method returning `Optional.empty()`, `null`, or a business error status. When called over HTTP:

1. The exception unwinds up the call stack from service/controller.
2. MVC exception handling or filters may participate depending on application configuration.
3. `ExceptionTranslationFilter` can translate `AccessDeniedException` (or related security exceptions) according to authentication status.
4. Logged-in users lacking permission typically receive `403 Forbidden` via `AccessDeniedHandler`.
5. For anonymous/insufficient authentication, `AuthenticationEntryPoint` may return `401 Unauthorized` for APIs or redirect to a login form.

If the method is invoked by a scheduler, batch job, or message consumer **without an HTTP request**, there is no outer servlet `ExceptionTranslationFilter`. The caller itself must handle the exception explicitly—for instance, marking the task failed, writing an audit entry, and not retrying indefinitely on deterministic denials.

Some Spring Security versions support `@HandleAuthorizationDenied`/`MethodAuthorizationDeniedHandler` to supply fallback values or mask results when denied in method security. That is a **specialized policy** and should not be used to hide denials of sensitive commands. Verify the version-specific API and check whether a fallback leaks resource existence.

**Do not equate every 403 error with method security.** The CSRF filter, URL authorization, authentication, domain policies, or custom exception handlers can produce similar responses. Always find the **first denying checkpoint**.

## 16. Interaction with @Transactional and commit timing

`@Transactional` and method-security interceptors can both use Spring AOP advisors. Advice ordering and transaction boundaries can affect what happens when a post-check throws an exception.

Two conceptual illustrations:

```text
Case A: Transaction advice wraps outside post advice
Transaction BEGIN
  -> Target method writes DB
  -> Post-authorize DENY
Transaction ROLLBACK (when exception propagates and rollback rule applies)
```

```text
Case B: Post advice wraps outside transaction advice
Transaction BEGIN
  -> Target method writes DB
Transaction COMMIT
  -> Post-authorize DENY
# DB already committed, later denial does not auto-undo
```

Both only illustrate **why ordering must be verified**; never assume your system follows Case A or Case B without confirming advisor order and transaction semantics. Moreover, even when the DB rolls back, actions like sending emails, calling payment gateways, publishing messages, or writing files **do not automatically roll back**.

For transaction-sensitive authorization, stronger options are:

- Pre-authorize general permissions before the method.
- Inside the transaction, load the tenant-scoped entity from the DB.
- Check resource policy/business conditions immediately before the update statement.
- Use optimistic versioning, pessimistic locking, or conditional updates under contention.
- Manage outbox/side effects so "success" signals are never emitted before the valid transaction completes.
- Test concurrent revocation/owner change/status change when rules must take effect immediately.

**Never place `@PostAuthorize` on a money-transfer method** and treat a post-return exception as a reliable state-change safeguard.

## 17. Data changes between check and execution: TOCTOU

**Time-of-check / time-of-use (TOCTOU)** is the gap between checking permissions and using the resource.

Example:

```text
T1: PreAuthorize reads Document 42 and sees status=DRAFT
T2: Another request changes Document 42 to LOCKED
T3: T1 method body performs update without re-checking
=> Rule "LOCKED cannot be edited" can be violated
```

A pre-check executed outside the write transaction can observe stale data. Similarly, ownership or membership can be revoked between the pre-check and the operation. Mitigations depend on policy:
- Use `UPDATE documents SET ... WHERE id=? AND tenant_id=? AND version=? AND status='DRAFT'`, then check the affected row count.
- Use optimistic locking with `@Version` in JPA.
- Acquire appropriate row locks and check within the same transaction when strong consistency is required.
- Agree on the contract for permission revocation timing and caches/tokens: not every system demands instant invalidation of old permissions, yet the requirement must be explicit.

**A transaction is not a magic switch that eliminates all race conditions.** Isolation levels, locks, side-effect operations, and query structure affect correctness. Policies must rely on real server records, not client-asserted IDs or states.

## 18. When to use a policy bean inside @PreAuthorize?

For simple rules, expressions like `hasAuthority('document:read')` are very readable. For complex rules, you can delegate:

```java
@PreAuthorize(
    "hasAuthority('invoice:approve') and @invoiceAccess.canApprove(authentication, #invoiceId)"
)
public void approve(long invoiceId) {
    // ...
}
```

A policy bean such as `invoiceAccess` can receive `Authentication`, resolve the real actor, query data, and return a boolean. Caveats:

1. **Never accept permissions from the client:** use only verified authentication and trusted DB sources.
2. **Avoid circular calls:** if a policy bean calls back into a `@PreAuthorize`-annotated method on the same use case, it can cause loops or hard-to-reason-about structures.
3. **Control loaded data:** query by tenant/ownership to prevent cross-reads; never load secrets and accidentally log them.
4. **Do not depend on mutable global state:** policies must decide from the specific actor/resource/context.
5. **Measure cost:** an authorize check can trigger SQL, sometimes repeatedly if multiple advisors run; consider scoped caching and invalidation mechanisms.
6. **Run rules at the right time:** pre-checks block early, yet if a policy depends on rapidly changing state, you still need protection inside the transaction right before writing.

Another option for large systems is implementing a custom `AuthorizationManager<MethodInvocation>` or declaring advisors/pointcuts for groups of methods. This suits separating policies from SpEL, though it increases configuration effort and requires testing both checkpoints and decision logic.

## 19. Customizing pre- and post-method AuthorizationManagers

Spring Security lets you write custom `AuthorizationManager`s and attach them through method interceptors. Benefits:
- Use structured Java instead of long SpEL strings.
- Separate rules from logging/auditing.
- Reuse across a group of methods or a meta-annotation.
- Unit-test policies with structured inputs.

In Spring Security 6.5, advanced configurations can disable default pre/post via `@EnableMethodSecurity(prePostEnabled = false)` and publish required advisors using factories like `AuthorizationManagerBeforeMethodInterceptor.preAuthorize(manager)` and `AuthorizationManagerAfterMethodInterceptor.postAuthorize(manager)`. When configuring manually, ensure you **do not accidentally strip protection** from methods relying on existing annotations.

Conceptual class/contract illustration without stuffing full imports into a standalone program:

```java
// Java pseudocode close to Spring Security 6.5;
// must choose the right AuthorizationManager<T> and version-specific API.
AuthorizationManager<MethodInvocation> beforeManager = (auth, invocation) -> {
    // Inspect method/arguments, call policy, and return AuthorizationResult.
    // Never take permissions from client-supplied data.
    // MethodInvocation provides method name, arguments, target.
    return new AuthorizationDecision(/* allowed */ true);
};

// Create appropriate pre-authorize advisor from manager.
// Requires real bean and pointcut configuration in Spring context.
```

**This is not runnable Java**: `/* allowed */` marks the constructor argument placeholder, and wiring must be implemented per your exact dependencies. For standard practical guidance, `@PreAuthorize` with policy beans is safer and easier to read; choose custom managers only when you have specific interception/logic requirements.

Besides annotation-based authorization, you can configure advisors with AOP pointcuts protecting groups of service methods. In that case, carefully check match scope to avoid blocking helpers or missing sensitive public methods.

## 20. Interceptor ordering, @Order, and other annotations

Each annotation has its own pointcut/interceptor. In Spring Security 6.5, method-security interceptors have distinct order values (for instance, `@PreFilter` runs before `@PreAuthorize` by default; docs cite orders such as 100 and 200). Ordering also interacts with `@Transactional` and other framework/application advisors.

Situations to distinguish:

- **Pre-filter then pre-authorize:** input data may already be filtered before the pre-expression checks.
- **Pre-authorize then method body:** body does not execute on pre-deny.
- **Post-authorize after method body:** can be denied after a read/write operation.
- **Post-filter after building collection:** list can be filtered before returning.
- **Transaction/caching/retry:** inner/outer advisor nesting can alter check timing and side effects.

When ordering genuinely needs adjustment, Spring Security provides order configuration hooks (such as `AuthorizationInterceptorsOrder`, or the `offset` attribute of `@EnableMethodSecurity` in supported versions). Consult version-exact docs, run real tests, and evaluate every advisor's impact. **Never tweak order just to make one current test pass** without understanding the security consequences.

## 21. Pre/post interceptors and object control: ownership scenario

Suppose Alice and Bob both hold the `file:read` authority, yet only Alice owns file 42.

### Approach A: general @PreAuthorize only

```java
@PreAuthorize("hasAuthority('file:read')")
public FileContent readFile(long id) {
    return store.load(id);
}
```

**Insufficient.** Bob has `file:read` so he also passes; if the service does not check owner/tenant, Bob can read Alice's file (IDOR/BOLA).

### Approach B: @PreAuthorize + @PostAuthorize on read

```java
@PreAuthorize("hasAuthority('file:read')")
@PostAuthorize("returnObject.ownerId == authentication.name")
public FileDto readFile(long id) {
    return store.loadDto(id);
}
```

This can block **returning an unauthorized object**. However, `loadDto` already ran. If returning huge files, querying multiple resources, or triggering side effects, reconsider.

### Approach C: use case proactively queries with scope + policy

```java
@PreAuthorize("hasAuthority('file:read')")
public FileDto readFile(long id) {
    Actor actor = actorResolver.requireActor();
    FileEntity file = store
        .findByIdAndTenantId(id, actor.tenantId())
        .orElseThrow(FileNotFoundException::new);
    policy.assertCanRead(actor, file);
    return mapper.toDto(file);
}
```

Approach C is preferable when you want to **avoid loading/constructing sensitive content before checking permission** and extend cleanly to list/download/export. You can combine pre-authorize with use-case policy; post-authorize can still serve as defense-in-depth for pure reads, but should not mask query-scoping flaws.

In multi-tenant systems, `authentication.name` might be an email or OIDC subject and **not** the DB owner ID. Always use an adapter mapping the principal to a stable actor ID before comparing ownership.

## 22. Multiple entry points and overlooked bypass paths

Using service-layer interceptors is valuable when the same use case is called from multiple places. Yet beyond self-invocation, watch for:

| Call path | Risk | Mitigation |
| --- | --- | --- |
| REST controller | Overly broad HTTP matcher | Method guard and domain policy |
| GraphQL resolver | Does not use REST matchers | Policy in application service |
| Message listener | Lacks request `SecurityContext` | Valid service actor, domain guard |
| Scheduler | Runs with unbounded system privileges | Scoped service account and audit |
| Same bean calling `this.securedMethod()` | Bypasses proxy | Refactor bean boundary or internal guard |
| Test instantiating service via `new` | No AOP proxy | Integration test with real Spring bean |
| Cache returns value before protective advisor | AOP/cache order can surprise | Verify order and identity-aware cache keys |
| Retry wrapping command | Can repeat side effects/exceptions | Idempotency and proper transactions |
| Calling external API before checking permissions | Side effects already happened | Policy pre-check before external call |
| Batch job ignoring tenant boundaries | Cross-organization data leak | Scoped queries and per-resource policy |

All entry points should funnel into a policy or a use case with reliable checkpoints. If a path genuinely requires a bypass (e.g., internal migration), design the bypass explicitly with dedicated authorization/auditing, never bypassing implicitly due to missing `Authentication`.

## 23. Testing interceptors: proving actual timing

**Never just assert a 403 status.** A test can pass due to CSRF, URL matchers, or another exception even if `@PreAuthorize` never ran. Verify **whether the method body was called**, **whether state changed**, and **which checkpoint denied**.

### Test 1 — PreAuthorize must block before target

In a Spring Security Test integration test, create a principal lacking the authority and invoke the Spring-managed service proxy:

```java
// JUnit 5 + Spring Test snippet; requires real beans and appropriate fixtures.
@Test
@WithMockUser(authorities = {"report:read"})
void paymentApprovalWithoutAuthorityNeverRunsTarget() {
    assertThatThrownBy(() -> paymentService.approve(42L))
        .isInstanceOf(AccessDeniedException.class);

    verify(paymentRepository, never()).findPendingForUpdate(anyLong(), anyString());
}
```

If the method is genuinely invoked through the proxy, pre-authorization denies before the body queries the repository. AssertJ/Mockito/JUnit/Test imports and bean fixtures depend on the project; this snippet **is not standalone**. If the service is a mock instead of a real AOP-proxied bean, the test fails to exercise the real mechanism.

### Test 2 — PostAuthorize denies after body executes

Use a read method returning an object not owned by the caller, with a mock principal holding valid read authority:

```java
@Test
@WithMockUser(username = "alice", authorities = {"document:read"})
void postAuthorizeDeniesForeignDocumentAfterRead() {
    when(repository.getView(42L))
        .thenReturn(new DocumentView("bob", "sample"));

    assertThatThrownBy(() -> queryService.read(42L))
        .isInstanceOf(AccessDeniedException.class);

    verify(repository).getView(42L);
}
```

This test confirms the read target **did execute**, yet the caller was denied. DTO/constructor are application-defined fixtures.

### Test 3 — Domain policy denies before write

Fix the `payment:approve` authority on the actor and vary creator/tenant/status/limit. Prove:
- Callers lacking object permission are denied.
- Payment state does not change on denial.
- Gateway/email/outbox are not invoked.
- With valid permission, the mutation executes once.
- When the actor's permission is revoked, new requests reflect revocation timing per contract.

### Test 4 — AOP bypass risks

Obtain the bean via Spring and test both direct calls from another bean and `this.secured()` inside the same bean. Never assume behavior from annotations; verify via behavior/tests. If a test reveals a bypass, fix the architecture before release.

### Test 5 — HTTP, CSRF, and transaction interactions

With `MockMvc`, supply valid authentication and a CSRF token for write requests protected by CSRF, then verify differences across authorities/policies. Confirm anonymous users, missing authorities, different tenants, nonexistent resources, and domain conflicts adhere to the contract. If post-checking reads, also test that responses do not leak DTOs after denial.

## 24. Debugging practice: finding the first denying interceptor

When facing "should be allowed yet got 403" or "annotated yet still entered", check in order:

1. **HTTP or non-HTTP call?** If HTTP, check whether `SecurityFilterChain` and request authorization blocked earlier.
2. **Called via Spring-managed bean/proxy?** Check self-invocation, method visibility, and interface/proxy type.
3. **Is `@EnableMethodSecurity` enabled?** Verify application context scope and pre/post settings.
4. **What authorities are actually in `Authentication`?** `ROLE_*`, `SCOPE_*`, and raw permission strings must match exactly; never log credentials/tokens.
5. **What data does the SpEL expression use?** Does `#id` resolve properly, does `returnObject` expose the right property, and which actor reaches the policy bean?
6. **Did denial occur before or after the target?** Enable safe logging/metrics or verify mocks to confirm whether the body ran.
7. **Other AOP interactions?** Check `@Transactional`, cache, retry, and actual advisor order.
8. **Data policy?** Do owner, tenant, state, delegation, and query scope match the database?
9. **Where are exceptions turned into responses?** Inside requests, check handlers/controller advice/filters; outside requests, check how the caller handles them.
10. **Did tests eliminate noise?** Failures from CSRF, validation, expired tokens, or route mismatches do not prove method guards.

You can enable appropriate Spring Security log levels in development and observe denial events, while never logging raw access tokens, passwords, sensitive principal details, or full document contents. Audit logs should record normalized actor ID, action, resource ID, denial point, safe reason code, and correlation ID per system policy.

## 25. Common misconceptions and fixes

| Misconception | Consequence | Correct approach |
| --- | --- | --- |
| "`@PreAuthorize` is a Java guard inside the method body" | Proxy-bypassing calls skip checks | Understand interception and test via Spring-managed proxy |
| "`@PostAuthorize` checks before DB writes" | May write/commit before denying | Guard writes before side effects, inside an appropriate transaction |
| "With `@EnableMethodSecurity`, every method is protected" | Unmatched methods still run | Declare policies explicitly at entry points/use cases |
| "Multiple annotations on a class/method mean pick one" | Missed checks | Distinct annotations may all need to pass |
| "You can repeat `@PreAuthorize` multiple times" | Unsupported configuration | Combine expressions or call a policy bean |
| "`@PostFilter` solves all list security" | Data already loaded, broken pagination | Scope DB queries, supplement with filter if reasonable |
| "`@PreFilter` checks every element and rejects the whole batch" | Can silently filter, partial processing | Design explicit all-or-nothing or partial-success semantics |
| "Having role ADMIN always bypasses tenant checks" | Cross-tenant data leak | Bypass policies must be explicitly defined and tested |
| "Using `#id` always grabs the right argument" | SpEL may fail to resolve parameter names | Configure compiler/metadata and test real methods |
| "Private/final methods get AOP interception like public methods" | Annotations may not run | Verify proxy/AspectJ capabilities and guard at boundaries |
| "HTTP 403 means `@PreAuthorize` worked" | Could be CSRF or URL guard | Verify target did not run, cross-check with valid authority |
| "Transaction rollback recalls sent emails" | External side effects persist | Check permissions before external calls; use outbox |
| "Just throwing 403 is enough" | Non-HTTP jobs mishandle retries | Design handlers per entry point |
| "Missing Authentication means run as system" | Easy permission bypass via jobs | Use limited-privilege service actors with auditing |

## 26. Checklist for placing policy enforcement points

Before shipping a method to production, confirm:

1. **Purpose:** does the method read data or mutate state? Are there non-DB side effects?
2. **Entrypoints:** which guards cover REST, GraphQL, jobs, events, and other services?
3. **Proxy:** is the method called through an appropriate Spring-managed proxy/AspectJ?
4. **Authentication:** is the actor authenticated from a trusted source, with the right `SecurityContext` on threads/tasks?
5. **Pre-rule:** which roles/authorities block before the target? Do SpEL and parameter names actually work?
6. **Resource-rule:** where are owner, tenant, ACL, groups, state, and limits checked?
7. **Policy timing:** are all rules affecting write permissions checked **before** mutations?
8. **Concurrency:** are transactions, locks, versions, or conditional updates needed so state does not change between check and use?
9. **Post-rule:** if using `@PostAuthorize`, is the method body pure-read? Does the return object have the expected type/properties?
10. **List filtering:** are permissions applied directly in DB queries or only after loading data?
11. **Advisor order:** have transaction, cache, retry, and method-security ordering interactions been verified?
12. **Exceptions:** do HTTP entry point/denied handler and non-HTTP callers handle denials consistently?
13. **Tests:** did you verify body skipped on pre-deny, body ran on post-deny, and state unchanged on domain deny?
14. **Observability:** do audit logs capture actor/action/resource/decision without exposing secrets?
15. **Fallback:** how are anonymous users, revoked users, stale tokens/sessions, and ACL/database errors handled fail-closed?

### Self-check

**1.** A `@PostAuthorize("returnObject.ownerId == authentication.name")` method returns Bob's object when Alice calls it. Was the database queried?  
→ **Yes, the target already ran** to produce the return value. The post-interceptor only decides whether to forward the successful result to the caller.

**2.** Method `approvePayment` has `@PostAuthorize` but no permission check before sending a confirmation email. If a request is denied, is the email guaranteed not to have been sent?  
→ **No**. The email may have been sent before the post-check; permissions must be checked before side effects.

**3.** A bean calls `this.secured()`, where `secured` carries `@PreAuthorize`. Does a standard proxy guarantee interception?  
→ **No**. Self-invocation can bypass the proxy; refactor the call site or enforce an internal guard.

**4.** Controller has `hasRole('EDITOR')` and service has `@PreAuthorize("hasAuthority('document:edit')")`. Is having only `ROLE_EDITOR` enough?  
→ **No**, unless it is also mapped to `document:edit`. The two conditions are independent in the authority chain.

**5.** Bob has `document:edit`, but the file belongs to another tenant. Where should he be blocked?  
→ Use pre-rules to block missing general permissions, and check tenant/object inside the use case/policy using trusted data before the operation.

**6.** A batch job bypasses `AuthorizationFilter` yet calls a service through its proxy. Can method security still run?  
→ **Yes**, if the method is intercepted and has an appropriate security context/actor. The HTTP filter does not participate in the job path.

**7.** A list query returns 50,000 documents and `@PostFilter` keeps only 15. Is this a safe/efficient default query strategy?  
→ **No**. Excessive data is loaded, wasting resources and breaking pagination; use scoped queries and test them.

**8.** Does `@Transactional` alongside `@PostAuthorize` on a write method guarantee rollback on post-deny?  
→ **Do not assume so**. Advisor order, commit timing, rollback rules, and external side effects affect the outcome. Write guards must be placed before side effects.

**Conclusion:** A *before-method interceptor* checks permissions **before the target runs**; an *after-method interceptor* can check **the return value after the target has run**. `AuthorizationManager` makes the decision, the interceptor enforces it at the call boundary, and business policies must live where trusted actor, object, and state are available. For commands with side effects, check permissions before mutating data; reserve post-authorization primarily for read scenarios where only the loaded result supplies the needed information.

## References

- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html)
- [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — Spring Security Test: Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html)
