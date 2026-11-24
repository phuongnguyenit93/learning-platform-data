# Designing Service Boundaries So Every Entry Point Is Protected

## 1. Objective and Security Invariants

A Spring business operation can be invoked via an HTTP controller, GraphQL resolver, WebSocket handler, message consumer, scheduler, CLI, another service, or an asynchronous workflow. If authorization policies live only in an HTTP filter or only in one controller, other entry paths can go straight to the service/repository and bypass the check.

**Design goal:** Every execution path of a sensitive use case must pass through a **security-controlled business boundary**, which identifies the caller, data scope, operation permissions, and access conditions for each resource **before producing side effects or exposing data**.

Three questions must be answered independently:

1. **Who is calling?** An authenticated user, a verified service identity, or an authorized job? Identity must never be obtained by trusting a raw `userId` or `tenantId` string from a request/event.
2. **What are they allowed to do?** Does the caller hold the authority for `document:write`, `document:read`, `document:archive`, etc.?
3. **Which resources may they act upon?** Does the record belong to the right tenant, project, group, owner, ACL, and permissible business state?

The answer to question 2 does not guarantee question 3. For example, `hasAuthority('document:write')` permits a category of operation, yet **does not** prove the caller may modify every document.

**Verifiable invariants:**

- An operation with side effects executes only with a trusted identity and an authorization decision matching the specific resource.
- Different adapters must not create data-update paths with weaker protection.
- Policies must not depend on whether the call "came from a controller."
- Methods with Spring AOP annotations are considered protected only when the call path genuinely passes **through the Spring proxy**.
- Transactions guarantee atomicity/consistency at their configured level; they **do not replace access control**.
- When identity, scope, or authorization proof is missing, privileged operations do not execute.

## 2. Architecture Diagram: Adapters to Service, Policy, and Data

~~~text
REST / GraphQL / WebSocket    Message consumer     Scheduler / CLI
          |                         |                    |
          v                         v                    v
  Verify human identity     Verify message origin   Verify job/service
  and authentication        + actor/context        identity + purpose
          |                         |                    |
          +-------------+-----------+--------------------+
                        |
              Use-case adapter
                        |
                        v
             PUBLIC SERVICE BOUNDARY
        (Spring-managed bean through proxy)
              @PreAuthorize / guard
                        |
                        v
             @Transactional use case
                |
                +--> resolve TRUSTED scope
                +--> resource/tenant/ACL policy
                +--> validate business invariants
                |
                v
           scoped repository / domain
                |
                v
               database
~~~

This diagram is a design principle; **not every adapter automatically has a Spring SecurityContext**. HTTP typically carries a per-request user context. Message listeners and scheduled tasks need dedicated verification and identity propagation mechanisms. If an adapter lacks appropriate authentication, it must **deny or invoke a separately protected system use case**, never implicitly grant admin rights.

When a system uses Spring Security method security, the service layer is the natural place to check **operation invocation** permissions. The query/domain policy layer checks permissions **per object**. You can add database Row-Level Security (RLS), auditing, validation, and network authorization as complementary layers; each layer has a clear boundary.

## 3. Why Is Protecting Only the Controller Insufficient?

Suppose the following endpoint is protected at the HTTP layer:

~~~java
@PatchMapping("/documents/{id}/title")
public ResponseEntity<Void> rename(
        @PathVariable long id,
        @RequestBody RenameRequest request) {
    documentService.rename(id, request.title());
    return ResponseEntity.noContent().build();
}
~~~

This code is an illustrative Spring MVC component; `RenameRequest` and `documentService` are application-defined.

A request security configuration may allow only users with authority `document:write` to call `PATCH /documents/**`. That protects HTTP requests **passing through that `SecurityFilterChain`**. However, the same `documentService.rename(...)` method can be invoked from:

- `@KafkaListener`, `@RabbitListener`, or a message handler.
- Another service handling batch processing, imports, or cross-domain workflows.
- `@Scheduled`, command-line runners, event listeners, integration tests, or admin code.
- Another API with separate security configuration, such as GraphQL or gRPC.

Those calls do not automatically pass through the HTTP filter chain. If the service does not enforce its own authorization checks, a developer adding a new call path can inadvertently introduce a vulnerability.

**Principle:** Controllers validate request format and delegate to use cases; services own business authorization boundaries; repositories enforce proper data scoping. Never make the controller the sole place that knows the policy.

## 4. How Spring Security Method Security Protects Services

Enable method security explicitly:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Spring Boot starter security does not enable method security merely because the dependency is present. With this configuration, annotations like `@PreAuthorize` on Spring-managed beans can be enforced by interceptors. Example:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentCommandService {

    @PreAuthorize("isAuthenticated() and hasAuthority('document:write')")
    public void rename(long documentId, String newTitle) {
        // Check permissions on the exact document before updating.
    }
}
~~~

Two important observations:

- `@PreAuthorize` is evaluated **before** the method body when the call passes through the interceptor. With the rule above, a user with write authority **does not necessarily** have permission to edit document #17 belonging to another tenant.
- Annotations are metadata for AOP. They do not activate on an object created via `new DocumentCommandService()` outside Spring, nor do they protect Java calls to the method that bypass the proxy.

`@EnableMethodSecurity` does not mean "every public method is locked automatically." Methods without matching rules can still be invoked unless another authorization mechanism is designed to block them. Therefore, you must **inventory sensitive use cases** and attach suitable policies, or establish a testable default-deny mechanism.

## 5. Proxy Boundary: The Dangerous Self-invocation Bug

In standard AOP proxy mode:

~~~text
Other Spring bean --> Proxy --> @PreAuthorize interceptor --> target.method()
                         |
                         +--> @Transactional interceptor (per configuration)
~~~

Yet an **internal call on the same object** does not enter the proxy:

~~~text
Other bean --> Proxy --> target.importBatch()
                              |
                              +--> this.rename(...)    // directly inside target
                                   @PreAuthorize on rename is bypassed
~~~

Faulty design example:

~~~java
@Service
public class UnsafeDocumentService {

    public void importBatch(List<RenameCommand> commands) {
        for (RenameCommand command : commands) {
            this.rename(command.id(), command.title());
        }
    }

    @PreAuthorize("hasAuthority('document:write')")
    @Transactional
    public void rename(long id, String title) {
        // database update
    }
}
~~~

If `importBatch` has no authorization mechanism of its own, calling `importBatch` through the service proxy and then `this.rename(...)` **does not trigger the interceptor attached to `rename`**. Depending on the call path, `rename`'s transaction is not started by that annotation either. This is why the main API can be protected while an import/batch feature runs unchecked.

**Fix by splitting use-case boundaries into separate beans:**

~~~java
@Service
public class DocumentBatchService {
    private final DocumentCommandService commands;

    public DocumentBatchService(DocumentCommandService commands) {
        this.commands = commands;
    }

    @Transactional
    public void renameBatch(List<RenameCommand> items) {
        for (RenameCommand item : items) {
            commands.rename(item.id(), item.title());
        }
    }
}
~~~

Here `commands` is a Spring-injected bean, so `commands.rename(...)` can go through `DocumentCommandService`'s proxy. Every item must cross the same authorization boundary. If the batch is meant to be a single transaction, error handling must be consistent: exceptions denying the batch must not be swallowed leaving partial commits outside the contract.

The integration snippet above assumes `RenameCommand`, constructor dependencies, and transaction configuration are defined. If batch import is a privileged action distinct from manual renaming, `renameBatch` also needs its own **batch execution permission**, such as `@PreAuthorize("hasAuthority('document:bulk-write')")`; per-document permission checks inside are still required.

**Do not treat workarounds like `AopContext.currentProxy()` or self-injecting the proxy as the default choice.** They leak infrastructure details into business code, are error-prone to configure, and complicate testing. Splitting beans/services along clean boundaries is simpler to read and prove. If the application truly uses AspectJ weaving, semantics can differ from proxy mode; verify the actual configuration.

### JDK Proxies, CGLIB, and Method Visibility

Know the actual proxy type in use:

- JDK dynamic proxies normally operate through interfaces implemented by the proxy; callers must go through the corresponding proxied interface.
- Class-based proxies (typically CGLIB-based) require overridable methods; `final` and `private` methods are not normal interception points. `final` classes can cause issues with subclass proxies.
- Whether transactions apply to certain non-public methods varies by Spring version and proxy type. For critical authorization, choose **explicit public service APIs on Spring-managed beans**, invoke from another bean, and test with the real proxy.
- Annotations do not run when code deliberately unwraps the target object and calls it directly, when `new` is used, or when a call is bypassed by another technique.

Avoid placing sensitive access decisions on a `private` method hoping `@PreAuthorize` will guard it.

## 6. Placing Operation Permissions and Resource Permissions in the Same Use Case

An easily testable design uses **two layers of protection**:

1. `@PreAuthorize` blocks callers lacking the required authority before entering the service method.
2. Inside the service, using a trusted scope, load the exact resource and invoke the domain policy to check tenant/owner/ACL **before mutating**.

The example below illustrates Spring Data JPA and method security; domain types `Document`, `Actor`, `ActorResolver`, and `DocumentPolicy` must be defined by the application.

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;
import java.util.UUID;

public interface DocumentRepository extends JpaRepository<Document, Long> {
    Optional<Document> findByIdAndTenantId(Long id, UUID tenantId);
}
~~~

Business service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentCommandService {
    private final DocumentRepository repository;
    private final ActorResolver actorResolver;
    private final DocumentPolicy policy;

    public DocumentCommandService(
            DocumentRepository repository,
            ActorResolver actorResolver,
            DocumentPolicy policy) {
        this.repository = repository;
        this.actorResolver = actorResolver;
        this.policy = policy;
    }

    @PreAuthorize("isAuthenticated() and hasAuthority('document:write')")
    @Transactional
    public void rename(long documentId, String newTitle) {
        Actor actor = actorResolver.requireCurrentAuthenticatedActor();

        if (documentId <= 0 || newTitle == null || newTitle.isBlank()) {
            throw new IllegalArgumentException("Invalid rename request");
        }

        Document document = repository.findByIdAndTenantId(
                documentId, actor.tenantId()
        ).orElseThrow(() -> new ResourceNotFoundException(documentId));

        policy.requireCanRename(actor, document);
        document.rename(newTitle);
    }
}
~~~

Design conditions that must be enforced:

- `ActorResolver` must obtain identity/tenant from a **verified source** (security context, normalized principal, or equivalent identity mechanism), never reading client-supplied `ownerId/tenantId` directly as authority.
- The `findByIdAndTenantId` query pre-scopes by tenant. `DocumentPolicy.requireCanRename` checks all remaining conditions: owner, sharing, document state, membership, account privileges, etc. Never infer owner permission solely from a coarse authority.
- `Document.rename` is illustrative business logic; JPA dirty checking works only when the entity is managed in a persistence context within an active transaction. If using an update query or non-DB API, implement side effects per their own contract.
- `ResourceNotFoundException` is an application exception; only return safe messages adhering to anti-enumeration policies. Cross-tenant IDs can often be handled as "not found" instead of confirming the object's existence.
- `IllegalArgumentException` typically maps to a bad-input response in adapters; it is not synonymous with an authorization error.
- In production implementations, prevent permissions from changing between check and write when business risk warrants it: use transactions, isolation/locking, or scoped `UPDATE` conditions with versioning as appropriate.

**One service, one authorization contract:** User-facing adapters call this same method through the Spring bean, avoiding duplicated owner/ACL logic in every controller. Still, enforce conventions so adapters cannot call `repository.save(...)` directly bypassing the use case; package architecture, tests, and reviews should guard against that.

## 7. Designing for Multiple Entry Points Without Assuming Every Caller Is HTTP

| Entry point | Identity to verify | How it crosses the boundary |
|---|---|---|
| Spring MVC/REST | Authentication from Spring Security filter chain | Controller calls rule-guarded service bean; service checks resource |
| GraphQL resolver | GraphQL request principal/authentication | Resolver calls the same service; never rely solely on URL rules |
| WebSocket handler | Valid connection/message identity, action scope | Handler verifies message authority then calls use case |
| gRPC or internal API | Authenticated service-to-service identity/caller | Gateway interceptor and service/resource policy; never trust self-declared headers |
| Kafka/RabbitMQ/queue consumer | Origin, signature/trust boundary, actor or service identity | Adapter verifies message; calls user-bound use case or dedicated system policy |
| Scheduled job | Job identity, task, and allowed tenant/resource set | Independently controlled admin use case; never grant default admin rights |
| CLI/admin command | Operator/service identity and permission scope | CLI adapter verifies identity then calls the same policy boundary |
| Service-to-service call | Trusted context and proxied public API | Inject service bean; never use `this.method()` to annotated methods |
| Async execution | Identity/scope properly propagated to execution unit | Propagate context safely, or re-evaluate authorization in worker |
| Integration test | Valid fixture-simulated principal or service identity | Test via Spring bean/proxy and observe real data |

The presence of a security context on an HTTP thread does not mean a message worker will have it. Never handle missing authentication by defaulting to `ROLE_ADMIN`.

### Messages from External Systems Do Not Prove Sender Identity

Event payloads may carry `userId`, `tenantId`, or `requestedBy` for tracing, yet those fields are **data**. To use them for authorization, you must prove provenance/identity with a trusted mechanism (mTLS, signature-verifying issuer, broker ACLs with trust contracts, signed commands, expiring authorization tickets, etc.) and bound the source's privileges.

Messages may arrive duplicated, replayed, reordered, or consumed after a user's permissions were revoked. For sensitive actions, consider checking permissions **at execution time**, replay/expiry policies, idempotency keys, and handling stale states.

### Scheduled/System Operations Are Distinct Use Cases

A cleanup job for old data may need cross-tenant privileges that differ from a user editing their own document. Never add a public `updateWithoutSecurity(...)` method for jobs that any bean can invoke.

Alternative design:

- Establish a verified **service identity** with a dedicated authority, e.g. `document:maintenance`, granted only to the right workload.
- Provide a dedicated `archiveEligibleForTenant(...)` use case with its own business scoping rules; verify tenant/job purpose and bound the dataset.
- If the job does not run inside a Spring `SecurityContext`, the policy service accepts a context **constructed and verified by trusted infrastructure**. Never treat an arbitrary caller-constructed DTO as sufficient proof.
- Audit job identity, operation, tenant, record count, and outcome; never log credentials/tokens.
- Test that ordinary endpoints/users cannot invoke maintenance paths merely by knowing the method name.

Some systems need workload identities rather than user contexts. Those cases require two **explicitly protected boundaries**, not an ambiguous "bypass" flag inside user use cases.

## 8. `@Transactional` Does Not Replace `@PreAuthorize`

`@Transactional` orchestrates transactions: starting/joining a transaction and committing/rolling back per rules. It does not verify caller identity, authority, or record scope. Conversely, `@PreAuthorize` allows or denies method entry but does not ensure transactions, isolation, or rollback.

When both annotations sit on a public service method, two interceptors are involved: authorization and transaction. **Advice ordering is configurable**; do not assume every version/proxy setup shares the exact same order. Test your application's actual configuration if ordering matters for side effects, auditing, or performance.

A safe implementation flow for write commands:

1. Block unauthorized execution at the start of the service boundary, before the method body.
2. Inside the transaction, load the object scoped to the verified tenant/scope.
3. Evaluate policy against the object itself, its state, and business constraints.
4. Only after those steps mutate/write; security exceptions must prevent the operation from succeeding.
5. Commit per transaction rules; record logs/audits/outbox per contract and never emit external side effects before authorization is confirmed.

In Spring, runtime exceptions (such as `AccessDeniedException`) trigger rollback by default when escaping through the transaction interceptor; checked exceptions follow different rollback rules unless configured. If code **catches and swallows** an exception from a denied operation, an outer transaction can proceed to commit partial data. Define explicitly whether a batch is atomic, intentionally partial-success, or all-or-nothing; never create a state where "some items slip past checks."

**Warning about `@PostAuthorize` on write commands:** It is evaluated **after the method executes**. If side effects were already committed due to transaction advice ordering or external service calls, post-check denial does not guarantee undoing them. For writes, prefer pre-authorization and resource policies **before mutation**. Use `@PostAuthorize` primarily for intentional read-authorization scenarios with controlled data retrieval beforehand.

## 9. Transaction Boundaries and TOCTOU

*Time of check to time of use* (TOCTOU) occurs when the system checks permissions at T1, yet the document/ACL changes at T2 before writing.

~~~text
T1: check user A can edit document 7
    |
    +--- another transaction revokes A's membership
    |
T2: UPDATE document 7
~~~

A `@PreAuthorize` checking only a general authority will not detect permission changes on the document. Placing domain policy checks close to the write inside an appropriate transaction narrows the window, yet **does not eliminate all races**.

Depending on safety/consistency requirements, you can use:

- Update queries constrained by tenant and permission, e.g. `UPDATE ... WHERE id = :id AND tenant_id = :tenant AND ...`, checking the affected row count.
- Optimistic locking with `@Version` on entities, or pessimistic locks on related resources when business policy demands it.
- Appropriate transaction isolation and ACL synchronization strategies; never assume reading inside a transaction means the ACL cannot change concurrently.
- With external authorization services, explicitly define decision freshness, expiry/revocation, timeouts, retries, and fail-closed denial when no valid decision exists.

You do not need the highest isolation level for every operation. Choose based on race impact, throughput, and required consistency.

## 10. "Shortcuts" That Commonly Break Boundaries

### 10.1. `@PreAuthorize` on `private`/Helper Methods

~~~java
private void assertUserAllowed() { /* ... */ }
~~~

If a security annotation is placed only on a private helper, standard Spring AOP proxies do not intercept internal calls to that helper. **Fix:** place the rule on the proxied public use-case method, or call a Java policy directly inside the method before mutation.

### 10.2. Instantiating Services with `new`

~~~java
DocumentCommandService service = new DocumentCommandService(...);
service.rename(7L, "New title");
~~~

The object is not managed by Spring as a proxied bean, so method security and transaction annotations may have no effect. **Fix:** inject the Spring-managed service and test through the application context.

### 10.3. Callers Going Directly to Repositories

~~~java
documentRepository.deleteById(id);
~~~

Repositories may not enforce tenant/ACL checks if methods take raw IDs. **Fix:** restrict which modules can access repositories, force adapters through application services, design scoped queries, and add architectural tests to prevent bypasses.

### 10.4. Locking URLs While Leaving Message/CLI Paths Open

`SecurityFilterChain` applies to HTTP requests; a message handler does not inherit those rules automatically. **Fix:** each adapter authenticates its source and invokes a use case / domain authorization layer with an explicit contract.

### 10.5. Using Broad Roles Instead of Resource Permissions

`hasRole('ADMIN')` or `hasAuthority('document:write')` may authorize a use case, yet does not verify eligibility for every tenant/owner. **Fix:** check actual scope on each resource.

### 10.6. Assigning a Default Principal in Workers

If a scheduled task lacks authentication, inventing a "superuser" token without issuance/revocation/audit processes destroys the trust boundary. **Fix:** use workload identity or a dedicated system-operation guard accepting credentials only from trusted sources.

### 10.7. `@Async` Not Carrying `SecurityContext`

With thread-bound security contexts in imperative processing, switching threads loses the context unless propagated properly. **Fix:** use managed propagation like `DelegatingSecurityContextExecutor`/`DelegatingSecurityContextRunnable` when genuinely needed, or re-evaluate identity in the worker. Propagate context only from trusted sources, and clear it after execution so users never bleed across tasks.

With WebFlux/reactive, the security context uses Reactor context; never mechanically apply `ThreadLocal` and imperative transaction managers to reactive pipelines. Test context propagation and subscription timing on your actual stack.

### 10.8. Exposing "Internal" APIs Without Authorization

An `internal` label on a class/package or running inside the same JVM does not confer permission. Any caller holding a bean reference can attempt to invoke the method. **Fix:** define capabilities explicitly and check at boundaries; internal helpers should have narrow visibility without leaving public bypass alternatives.

## 11. An Interface Pattern: All Adapters Converge on One User Use Case

For HTTP, the adapter can be very thin:

~~~java
@RestController
@RequestMapping("/documents")
public class DocumentController {
    private final DocumentCommandService commands;

    public DocumentController(DocumentCommandService commands) {
        this.commands = commands;
    }

    @PatchMapping("/{id}/title")
    public ResponseEntity<Void> rename(
            @PathVariable long id,
            @RequestBody RenameRequest request) {
        commands.rename(id, request.title());
        return ResponseEntity.noContent().build();
    }
}
~~~

Another service also calls the injected bean:

~~~java
@Service
public class DocumentWorkflowService {
    private final DocumentCommandService commands;

    public DocumentWorkflowService(DocumentCommandService commands) {
        this.commands = commands;
    }

    public void renameFromWorkflow(long id, String title) {
        commands.rename(id, title);
    }
}
~~~

Prerequisite: the workflow truly represents an authenticated actor in the current security context. If no actor is present, `@PreAuthorize` must deny. The code in both examples is a **Spring application snippet**: it requires DTOs, beans, dependencies, and security configuration; it is not a standalone Java program.

This pattern also separates business boundaries cleanly instead of creating a "God service" serving users, jobs, imports, and maintenance via flags like `skipAuthorization=true`. Each public use case should have a permission contract that can be read and tested independently.

## 12. Standalone Java 17: One Policy Enforced Across Multiple Entry Points

The following Java code has no Spring in order to demonstrate the principle: **entry points may vary, yet the service guard runs on every call path**. It does not simulate Spring proxies, transactions, or identity propagation.

Create `ServiceBoundaryDemo.java`:

~~~java
import java.util.Set;

public class ServiceBoundaryDemo {
    record Actor(String name, String tenant, Set<String> authorities) { }

    static final class Document {
        private final int id;
        private final String tenant;
        private final String owner;
        private String title;

        Document(int id, String tenant, String owner, String title) {
            this.id = id;
            this.tenant = tenant;
            this.owner = owner;
            this.title = title;
        }
    }

    static final class DocumentService {
        private final Document document =
                new Document(7, "north", "an", "Draft");

        void rename(Actor actor, int documentId, String title) {
            if (actor == null
                    || actor.authorities() == null
                    || !actor.authorities().contains("document:write")
                    || !actor.tenant().equals(document.tenant)
                    || !actor.name().equals(document.owner)
                    || documentId != document.id) {
                throw new SecurityException("Denied");
            }
            if (title == null || title.isBlank()) {
                throw new IllegalArgumentException("Invalid title");
            }
            document.title = title;
        }

        String title() {
            return document.title;
        }
    }

    static void call(String channel, Runnable operation) {
        try {
            operation.run();
            System.out.println(channel + ": allowed");
        } catch (SecurityException exception) {
            System.out.println(channel + ": denied");
        }
    }

    public static void main(String[] args) {
        DocumentService service = new DocumentService();
        Actor owner = new Actor(
                "an", "north", Set.of("document:write"));
        Actor outsider = new Actor(
                "binh", "north", Set.of("document:write"));

        call("http", () -> service.rename(owner, 7, "Reviewed"));
        call("message", () -> service.rename(
                outsider, 7, "Overwritten"));
        call("internal", () -> service.rename(
                null, 7, "Bypassed"));
        System.out.println("title: " + service.title());
    }
}
~~~

Run on JDK 17 or later:

~~~bash
javac ServiceBoundaryDemo.java
java ServiceBoundaryDemo
~~~

Exact output:

~~~text
http: allowed
message: denied
internal: denied
title: Reviewed
~~~

Lesson from the demo: a new adapter cannot skip checks when **all entry points share one guarded operation**. In real applications, `Actor` must not be trusted if any adapter can fabricate it with fake name/tenant/authorities; it must be **verified or built from a trusted source**. With Spring AOP, you must still ensure callers go through the bean proxy; direct Java guards like the demo do not carry annotation self-invocation risks.

## 13. Designing Tests to Prove "Every Entry Point Is Protected"

### 13.1. Entry Point × Permission Matrix

Build a matrix for each sensitive use case:

| Call path | Valid identity/authority, right resource | Missing authority | Right authority, wrong tenant/ACL | No identity |
|---|---|---|---|---|
| HTTP controller | Succeeds | Denied | Denied | Denied / login required |
| Service-to-service | Succeeds via proxy | Denied | Denied | Denied |
| Message from trusted source | Succeeds when actor/purpose valid | Denied | Denied | Denied or verification error |
| Scheduled system operation | Succeeds with scoped workload identity | Denied | Denied | Denied |
| Batch import | Succeeds when all items valid or per partial contract | Unauthorized items not written | No cross-tenant writes | Denied |

Every cell must verify **the final state in the database**, not just the HTTP status or exception type. A request returning 403 whose data already committed before a post-check is still a critical vulnerability.

### 13.2. Testing Through Real Spring Beans

Write integration tests using `@SpringBootTest` or appropriate test slices, injecting services from the application context. For HTTP use `MockMvc` or an equivalent test client; for method security use `@WithMockUser` or a custom security context when authorization depends on a custom principal or tenant claim.

Essential test cases:

1. Caller without `document:write` calls `DocumentCommandService.rename(...)` directly on the bean: denied and document is unchanged.
2. Caller with authority but wrong tenant/owner: denied, even if guessing a valid ID.
3. Batch service calls child bean via dependency injection: every element is still checked.
4. A variant using `this.rename(...)` on the same bean illustrates proxy bypass; confirm production has no similar call paths at sensitive points.
5. Message event declaring fake `userId/tenantId`: does not modify out-of-scope documents.
6. Job missing workload identity or with wrong job purpose: does not execute.
7. If a batch contains a denied item, verify full rollback or partial-success **strictly matches the documented contract**, with no accidental commits.
8. For async and retries, confirm security context / actor scope does not leak between tasks and is not reused after revocation.
9. If `@PostAuthorize` exists on a write command, check side effects/commits on denial to prove no exposure; typically move checks before mutation.
10. For overloaded method names, JDK/class-based proxies, or `final` methods, confirm annotations actually fire on the invoked method.

### 13.3. Architectural Tests and Operational Observability

Some bugs cannot be caught by unit-testing individual services:

- Use ArchUnit or module rules to forbid adapters/controllers/listeners from calling write repositories directly, except explicitly approved modules.
- Audit all public methods mutating data with side effects: which are entry points, which are helpers, and where policies live.
- Ensure audit logs record real actor, trust source, action, resource ID, tenant, result, and correlation ID; never log tokens or sensitive data.
- Monitor `AccessDeniedException` counts, policy service errors, missing-scope requests, transaction rollbacks, cross-tenant attempts, and abnormal message retries.
- Run tests with production-like proxy/transaction configs; avoid unit-testing only `new`-ed objects and concluding annotations work.

The goal of testing is to prove **non-bypassability** across supported call paths and paths the codebase can construct, not merely that a controller carries an annotation.

## 14. Design Checklist When Adding a New Entry Point

Before adding a controller, message listener, cron job, or service method:

1. Identify the use case and resource; document required authorities and owner/tenant/ACL conditions.
2. Verify caller identity per transport; missing identity must never implicitly grant permissions.
3. Select a public application-service boundary or a dedicated, protected system use case.
4. Ensure method security is enabled and calls pass through a **Spring-managed proxy**.
5. Do not rely on annotations on `private`/`final` methods or internal `this.method()` calls in proxy mode.
6. Separate operation permissions at the service from resource permissions in queries/domain policies.
7. Place authorization checks before side effects and inside transactions fitting consistency requirements.
8. Verify rollback, checked/runtime exceptions, `@PostAuthorize`, retries, and nested transactions where applicable.
9. For async/messages/jobs, verify identity propagation, replay/idempotency, and zero default admin privileges.
10. Forbid adapters from bypassing the use case to call write repositories directly.
11. Test at least one HTTP path, one non-HTTP path, one internal service call path, plus wrong-authority / wrong-tenant / unauthenticated cases.
12. Observe/audit outcomes without logging tokens or sensitive payloads.

**Operational mindset:** Every new "entry path" should increase the number of tested adapters, **not** increase copies of authorization logic. Permissions should be expressed at service boundaries and shared resource policies, with system exceptions defined and protected explicitly.

## References

- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, and how Spring AOP proxies invoke authorization interceptors.
- [Spring Framework – Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): proxies, self-invocation, JDK proxy/CGLIB, and interception limits.
- [Spring Framework – Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): transaction advice, proxy mode, self-invocation, ordering, and rollback defaults.
- [Spring Security – Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html): `SecurityContext` across threads and managed context-propagation wrappers.
