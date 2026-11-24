# Limitations of `@PostAuthorize` for Write Operations and Irreversible Side Effects

> **Module:** Spring Security – authorization  
> **Category:** Post-method checks  
> **Goal:** Understand that `@PostAuthorize` is evaluated after the method body, not as a rollback guarantee; distinguish denial, transaction rollback, and side effects outside the database; choose `@PreAuthorize`, object-level policy, transactions/locking, outbox, and integration tests to protect write operations.

## 1. Opening scenario: HTTP 403 yet the data changed?

An application allows editing documents:

~~~java
// DANGEROUS DESIGN – do not apply to write operations.
@PostAuthorize("returnObject.ownerId == authentication.name")
public DocumentDto update(long id, UpdateCommand command) {
    Document document = repository.findById(id).orElseThrow();
    document.apply(command);
    repository.save(document);
    mailClient.sendDocumentUpdated(document);
    return mapper.toDto(document);
}
~~~

Suppose Bob edits a document belonging to Alice. The developer's intent: if Bob is not the owner, Spring Security will deny it. The actual sequence of `@PostAuthorize` can be:

~~~text
1. Bob calls update(documentId=7).
2. Spring AOP lets the method body execute.
3. document.apply(command) mutates the object.
4. repository.save(document) is called.
5. mailClient.sendDocumentUpdated(...) is called.
6. The method returns DocumentDto.
7. @PostAuthorize reads returnObject.ownerId.
8. Compared against authentication.name, mismatch -> DENY.
9. Caller receives AccessDeniedException / HTTP 403 depending on entrypoint.
~~~

**At step 8, steps 3–5 have already occurred.** You cannot look at status 403 and conclude the database did not change, the email was not sent, or the business effect was reversed. The database may commit or roll back depending on transaction boundaries; a sent email is not automatically retracted by a Java exception.

**Core point:** `@PostAuthorize` checks **the result after the method executes**, not a pre-mutation permission check, and not a distributed rollback. Official Spring Security documentation does not recommend using `@PostAuthorize` on classes performing database writes, especially when combined with `@Transactional`.

## 2. Comparing `@PreAuthorize` and `@PostAuthorize`

| Criterion | `@PreAuthorize` | `@PostAuthorize` |
|---|---|---|
| Timing | Before the body runs | After the body runs |
| Easily available data | Authentication, authorities, method arguments, policy bean | Authentication, arguments, `returnObject` |
| On denial | Blocks method body if invocation passes through advisor | Body already executed before denial |
| Suitable for | Write/delete/approve/export/send | Reading an object, checking result after querying |
| Key risk | Data race/TOCTOU if checked then written | Mutation already happened, transaction may commit, external effects remain |
| Mechanism | Before-method interceptor | After-method interceptor |

Illustrative flow:

~~~text
Caller
   |
   v
Spring AOP proxy
   |
   +--> @PreAuthorize
   |       - if DENY: method does not run
   |       - if ALLOW: continue
   |
   v
Business method
   |
   +--> SQL update / HTTP call / message / email / return
   |
   v
@PostAuthorize
   |
   +--> Check returnObject / authentication
   +--> if DENY: block return to caller
   |
   v
Caller receives result if allowed
~~~

Different annotation types can be processed sequentially; `@PreAuthorize` and `@PostAuthorize` do not cancel each other out. However, `@PostAuthorize` still only makes its decision after the body has produced its return value.

### 2.1. `@PostAuthorize` is useful when a method is read-only

~~~java
@PostAuthorize("returnObject.owner == authentication.name")
public Account readAccount(long accountId) {
    return repository.findById(accountId).orElseThrow();
}
~~~

The condition only allows returning Account if the owner matches the logged-in user. This is the official example of a post-check on a return object, useful for preventing IDOR/BOLA **at the result-return stage**. The class snippet requires Spring Security, bean/repository, identity contract, and `@EnableMethodSecurity`; it is not a standalone JDK program.

A read method must still genuinely perform no business mutations: a method named `readAccount` could write audit logs, call APIs, trigger lazy loads, or cause indirect side effects. You must inspect the call graph.

### 2.2. `@PostAuthorize` on writes is unsuitable

~~~java
// DO NOT USE as a deletion guard:
@PostAuthorize("returnObject.owner == authentication.name")
public Account deleteAccount(long id) {
    Account account = repository.findById(id).orElseThrow();
    repository.delete(account);
    return account;
}
~~~

If unauthorized, deletion is still invoked before the post-check. Even if some transaction configurations might roll back, the design placed security after the operation; never rely on that as safe by default.

## 3. Method security works via Spring AOP

Enabling method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

With Spring Security Servlet 6.x/7.x, common annotations have dedicated interceptors:

- `@PreAuthorize` via `AuthorizationManagerBeforeMethodInterceptor` and `PreAuthorizeAuthorizationManager`.
- `@PostAuthorize` via `AuthorizationManagerAfterMethodInterceptor` and `PostAuthorizeAuthorizationManager`.
- `@PreFilter` and `@PostFilter` handle filtering arguments/results via related mechanisms.

If `@PostAuthorize` denies, the infrastructure may throw `AccessDeniedException`. In an HTTP request passing through Spring Security filters, exception translation can produce HTTP 403 or trigger appropriate authentication handling. In a non-HTTP batch/job/service call, the caller must handle the exception.

**Denial is not rollback.** `AccessDeniedException` represents the authorization outcome; it does not by itself prove resources modified by the method body were restored to their prior state.

### 3.1. Proxy bypass

Even when annotations are placed properly, an internal call:

~~~java
@Service
class DocumentService {
    void entrypoint() {
        protectedDelete(7);  // self-invocation, may bypass proxy.
    }

    @PreAuthorize("hasAuthority('document:delete')")
    public void protectedDelete(long id) {
        // ...
    }
}
~~~

in standard proxy mode can go straight through `this` without running advice. Likewise, objects created with `new` are not Spring-proxied; private/final methods have limitations depending on proxy strategy.

A secure design for write operations needs **calls routed through a Spring-managed proxy** or a direct, unbypassable business check inside the service. Annotations are not Java statements that execute automatically inside the method body.

## 4. Types of side effects `@PostAuthorize` cannot erase

| Side effect before post-check | Can persist after denial? | Why |
|---|---|---|
| Committed SQL write | Yes | A commit is not automatically reversed by a later exception |
| Uncommitted SQL write | May roll back | Depends on transaction nesting, rollback rules, resource |
| Autocommit SQL | Yes | Statement may persist immediately |
| Email/SMS | Yes | External systems may already have received it |
| Kafka/RabbitMQ publish | Yes | Broker/consumer has separate transactions and timing |
| Webhook | Yes | Receiver may already process it |
| Payment capture/refund | Yes | Provider is a separate system |
| File/object storage delete | Yes | Does not self-recover without versioning/compensation |
| Cache/Redis mutation | Yes | Not part of the DB transaction by default |
| External audit log | Yes | Already written to another system |
| In-memory shared state | Yes | Throwing an exception does not revert shared objects |
| HTTP call to another microservice | Yes | Microservice has its own transaction |
| Granting permissions or issuing JWT | Yes | Token may already be issued/usable |

Some operations have **compensation** (such as refunds, restoring files, sending correction notices), but compensation is a **new action** that can fail; it is not an atomic rollback.

### 4.1. SQL save does not necessarily mean commit

With ORM/JPA, `save`, dirty checking, `flush`, and `commit` are distinct points in time. An entity may be modified in the persistence context before SQL flushes; SQL may also run before method return or commit outside the method. Do not generalize that `repository.save` definitely commits, nor that `@Transactional` definitely rolls back every write. Inspect the advisor chain and test against a real DB.

### 4.2. HTTP status does not tell resource state

`403 Forbidden` on the client only tells you the request was denied by HTTP handling at response time. It **does not confirm** zero database writes, zero outbound calls, or no messages emitted. Tests must assert business state and external interactions.

## 5. Does `@Transactional` always roll back after a `@PostAuthorize` deny?

No. The same method:

~~~java
@Transactional
@PostAuthorize("returnObject.ownerId == authentication.name")
public DocumentDto update(long id, UpdateCommand command) {
    Document doc = repository.findById(id).orElseThrow();
    doc.apply(command);
    return mapper.toDto(doc);
}
~~~

can be wrapped by **multiple AOP advisors**. Outer/inner positioning determines whether the post-check evaluates before or after transaction completion.

### 5.1. Post-check outside transaction

~~~text
PostAuthorize advisor (outer)
   |
   +--> Transaction advisor (inner)
   |      BEGIN
   |      method body: changes
   |      COMMIT
   |
   +--> evaluate returnObject -> DENY
~~~

In this structure, the database may already have committed by the time `@PostAuthorize` throws an exception. The transaction cannot retroactively roll back.

### 5.2. Transaction outside post-check

~~~text
Transaction advisor (outer)
   BEGIN
   |
   +--> PostAuthorize advisor (inner)
   |      method body: changes
   |      evaluate returnObject -> DENY
   |      throw AccessDeniedException
   |
   ROLLBACK if rollback rules apply
~~~

In this structure, a runtime `AccessDeniedException` propagating through the transaction interceptor can trigger a DB rollback by default. However, already-sent emails/webhooks/payments may still exist, a committed `REQUIRES_NEW` may not roll back, and secondary resources not enlisted in the same transaction do not automatically revert.

**Advisor ordering is not determined by the order two annotations are typed in source code.** Spring Security documentation mentions ordering `@EnableTransactionManagement` and `@EnableMethodSecurity` when post-authorization must be coordinated with transactions. That is a configuration to verify, **not a substitute for checking permissions before writing**.

### 5.3. Rollback rules

Spring Framework rolls back by default for `RuntimeException` and `Error`. Checked exceptions normally do not roll back automatically unless `rollbackFor` is configured appropriately.

~~~java
@Transactional(rollbackFor = Exception.class)
public void process() throws Exception {
    // ...
}
~~~

This snippet does not mean you should “fix” misplacing a post-check using `rollbackFor`. When an exception is caught and swallowed inside a transaction, or when the transaction has already committed, rollback still may not occur.

### 5.4. Independent `REQUIRES_NEW`

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeIndependentRecord() {
    // ...
}
~~~

`REQUIRES_NEW` uses an independent physical transaction. The inner transaction can commit even if the outer transaction rolls back. This is sometimes appropriate for auditing, but dangerous if used to alter permissions/resources before an outer method's post-check.

### 5.5. Different transactions across microservices

A database transaction on service A does not automatically undo a call to a payment processor, HTTP service B, or Kafka consumer C. If C has already processed an event, A rolling back does not mean C knows to undo it. Dedicated workflows, idempotency, and compensation are required.

## 6. Default design: `@PreAuthorize` and resource-level policy

Safer modification example:

~~~java
@PreAuthorize(
    "hasAuthority('document:update') and " +
    "@documentPolicy.canUpdate(authentication, #id)"
)
public DocumentDto update(
        @P("id") long id,
        UpdateDocumentCommand command) {
    Document document = repository.findById(id).orElseThrow();
    document.apply(command);
    return mapper.toDto(document);
}
~~~

Here:

1. `hasAuthority('document:update')` checks functional permission.
2. `@documentPolicy.canUpdate(authentication,#id)` checks principal, tenant, owner, and resource state from server sources.
3. If denied, the method body **does not run** through a Spring-proxied invocation.
4. If allowed, mutation proceeds.

This snippet belongs to a **Spring application**; it requires `@EnableMethodSecurity`, a Spring-managed service, `documentPolicy` bean, `@P`, repository, and domain types. It is not standalone JDK Java.

### 6.1. Do not trust `ownerId` from the request body

~~~java
// WRONG POLICY if ownerId is filled in by the client:
@PreAuthorize("#command.ownerId == authentication.name")
public void update(long id, UpdateCommand command) {
    // ...
}
~~~

A user can set `ownerId` in the command to match `authentication.name`. Authorization must be based on the **actual resource matching id** in the database, never on a caller-declared `ownerId` field.

### 6.2. Policy bean reading trusted data

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    private final DocumentRepository repository;
    private final IdentityResolver identityResolver;

    public DocumentPolicy(
            DocumentRepository repository,
            IdentityResolver identityResolver) {
        this.repository = repository;
        this.identityResolver = identityResolver;
    }

    public boolean canUpdate(Authentication auth, long documentId) {
        InternalIdentity actor = identityResolver.resolve(auth);
        if (actor == null) return false;
        return repository.existsEditableByTenantAndOwner(
                documentId, actor.tenantId(), actor.userId());
    }
}
~~~

This is a skeleton depending on the application's `DocumentRepository`, `IdentityResolver`, and `InternalIdentity`. The resolver must reject anonymous/unverified identities, map JWT issuer+subject or session principal to an internal user ID, and never trust tenant/owner from the client. The repository must enforce tenant, owner, and document state.

### 6.3. Permission is insufficient without an object policy

A user with `document:update` still must not edit documents in another tenant. Check:

- Authenticated principal.
- Permission matching the exact action (update differs from read/delete/export).
- Valid tenant membership.
- Resource owner/assignee or scoped override.
- Resource state permits editing.
- Workflow conditions such as approval, MFA, or quotas.
- User is not locked/revoked.

Do not let an ADMIN role automatically bypass every tenant/owner policy if business rules forbid it.

## 7. Race condition after pre-check: TOCTOU

Even `@PreAuthorize` can encounter:

~~~text
T1: Bob has permission to edit document 7 -> precheck ALLOW.
T2: Document 7 transfers owner to Alice.
T1: Bob updates document 7 based on stale authorization result.
~~~

This is **time-of-check/time-of-use**, not a bug specific to Spring Security. Authorization invariants must be tied to the time of write/commit:

- Pessimistic locking when loading the entity.
- Optimistic locking with `@Version` and rechecking permissions on retry.
- Conditional update matching tenant/owner/state/version.
- Appropriate transaction isolation.
- Domain policy checking the resource right before mutation.

A skeleton:

~~~java
@Service
public class DocumentCommandService {
    private final DocumentRepository repository;
    private final DocumentPolicyService policy;

    public DocumentCommandService(
            DocumentRepository repository,
            DocumentPolicyService policy) {
        this.repository = repository;
        this.policy = policy;
    }

    @PreAuthorize("hasAuthority('document:update')")
    @Transactional
    public void update(long id, UpdateCommand command) {
        Document doc = repository.findByIdForUpdate(id).orElseThrow();
        policy.requireCanUpdate(doc);
        doc.apply(command);
    }
}
~~~

`findByIdForUpdate` is an **example API convention** requiring appropriate locking implementation; `policy.requireCanUpdate` must fetch the trusted authenticated identity and throw denial **before `doc.apply`**. The method must be called through a Spring proxy for `@Transactional` and `@PreAuthorize` to work.

### 7.1. Conditional SQL update

~~~sql
UPDATE documents
SET status = :new_status,
    version = version + 1
WHERE id = :id
  AND tenant_id = :tenant_id
  AND owner_user_id = :actor_id
  AND status = 'EDITABLE'
  AND version = :expected_version;
~~~

If 0 rows are updated, permission/state/concurrency was not satisfied; the use case must handle it per policy. This example assumes **only the owner may update** and does not apply verbatim to workflows with sharing/delegation. Function-level permission and tenant context from authentication are still required.

## 8. One way to leverage `@PostAuthorize`: read first, then write

Spring Security guidance notes you can **read a resource and post-check permission on the read data**, and only then perform a mutation in another call.

~~~java
@Service
public class DocumentLookupService {
    @PostAuthorize(
        "hasAuthority('document:update') and " +
        "@documentPolicy.canUpdateReturned(authentication, returnObject)"
    )
    public DocumentSnapshot requireEditable(long id) {
        return repository.findSnapshotById(id).orElseThrow();
    }
}
~~~

Then:

~~~java
@Service
public class DocumentCommandService {
    private final DocumentLookupService lookup;
    private final DocumentRepository repository;

    @Transactional
    public void update(long id, UpdateCommand command) {
        DocumentSnapshot snapshot = lookup.requireEditable(id);
        Document doc = repository.findByIdForUpdate(id).orElseThrow();
        // Recheck state/permission inside the transaction in case of races.
        doc.apply(command);
    }
}
~~~

These snippets need constructors/imports/domain types. The key point is that `lookup.requireEditable` is called through **a different bean proxy**, so `@PostAuthorize` can run before the command method writes. However, a TOCTOU window still exists between read and write; you must recheck/lock before mutating if needed.

**Do not** write `this.requireEditable(id)` in the same service and assume `@PostAuthorize` is enforced: self-invocation can bypass the proxy.

## 9. Outbox and `@TransactionalEventListener`: handling external effects properly

For database writes + event publishing, consider the **transactional outbox**:

~~~text
1. Authenticate and authorize before action.
2. Open DB transaction.
3. Verify resource state/owner/tenant and concurrency.
4. Update business row.
5. Insert outbox row in the same DB transaction.
6. Commit.
7. Dispatcher reads outbox and sends external event.
8. Receiver processes idempotently, dispatcher retries/marks delivered.
~~~

Benefit: if the transaction in steps 2–6 rolls back, both the business row and the outbox row roll back together. If commit succeeds and the process crashes, the event stays in the DB waiting for the dispatcher to send. However, **an outbox cannot rescue an unauthorized commit caused by placing authorization after mutation**.

Outbox alone does not provide end-to-end exactly-once delivery: the dispatcher may send successfully and crash before marking delivered; receivers need idempotency keys and deduplication.

### 9.1. `AFTER_COMMIT` listener

Spring Framework supports:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onDocumentChanged(DocumentChangedEvent event) {
    notificationClient.send(event);
}
~~~

The listener can run after a successful commit. Even so:

- If the transaction commits **before `@PostAuthorize` denies**, the listener can still run.
- In-memory events risk being lost if the process crashes after commit.
- External sends can fail; retries/monitoring are needed if critical.
- Without an active transaction, behavior depends on `fallbackExecution` and configuration.
- `AFTER_COMMIT` **does not** replace authorization before mutation.

### 9.2. Payments and webhooks

For payment capture, SMS, emails containing PII, or webhooks:

~~~text
Authenticated actor
    |
    v
Permission + owner/tenant/amount/workflow approval
    |
    v
Authorized command & idempotent intent
    |
    v
Commit local state/outbox
    |
    v
Send external request with idempotency key
    |
    v
Reconcile response, audit, handle retries/compensation
~~~

A payment provider may already have captured funds when the caller receives 403. Compensation/refund is a new transaction that can fail; it is not a `@PostAuthorize` rollback.

## 10. Standalone Java 17: simulating post-check after mutation

This example uses standard Java, **without Spring Security or a real database**. Two lists recording “database writes” and “external sends” only illustrate operation ordering. It does not simulate Spring rollbacks or AOP advisors.

Create `PostAuthorizationWriteDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class PostAuthorizationWriteDemo {

    record Actor(String userId) {}
    record Resource(String id, String ownerId) {}

    static final class Effects {
        final List<String> databaseWrites = new ArrayList<>();
        final List<String> externalMessages = new ArrayList<>();
    }

    static String unsafePostCheck(Actor actor, Resource target, Effects effects) {
        effects.databaseWrites.add("UPDATED:" + target.id());
        effects.externalMessages.add("SENT:" + target.id());
        return actor.userId().equals(target.ownerId())
                ? "ALLOW_AFTER" : "DENY_AFTER";
    }

    static String preCheckedWrite(Actor actor, Resource target, Effects effects) {
        if (!actor.userId().equals(target.ownerId())) {
            return "DENY_BEFORE";
        }
        effects.databaseWrites.add("UPDATED:" + target.id());
        effects.externalMessages.add("SENT:" + target.id());
        return "ALLOW";
    }

    public static void main(String[] args) {
        Actor bob = new Actor("u-bob");
        Actor alice = new Actor("u-alice");
        Resource document = new Resource("doc-7", "u-alice");

        Effects unsafe = new Effects();
        System.out.println("unsafe decision: "
                + unsafePostCheck(bob, document, unsafe));
        System.out.println("unsafe database writes: "
                + unsafe.databaseWrites.size());
        System.out.println("unsafe external sends: "
                + unsafe.externalMessages.size());

        unsafe.databaseWrites.clear();
        System.out.println("rollback simulated database writes: "
                + unsafe.databaseWrites.size());
        System.out.println("rollback cannot undo sends: "
                + unsafe.externalMessages.size());

        Effects safeDenied = new Effects();
        System.out.println("safe decision: "
                + preCheckedWrite(bob, document, safeDenied));
        System.out.println("safe database writes: "
                + safeDenied.databaseWrites.size());
        System.out.println("safe external sends: "
                + safeDenied.externalMessages.size());

        Effects safeAllowed = new Effects();
        System.out.println("safe owner decision: "
                + preCheckedWrite(alice, document, safeAllowed));
        System.out.println("safe owner database writes: "
                + safeAllowed.databaseWrites.size());
        System.out.println("safe owner external sends: "
                + safeAllowed.externalMessages.size());
    }
}
~~~

Compile/run with JDK 17:

~~~bash
javac --release 17 PostAuthorizationWriteDemo.java
java PostAuthorizationWriteDemo
~~~

Verified expected output:

~~~text
unsafe decision: DENY_AFTER
unsafe database writes: 1
unsafe external sends: 1
rollback simulated database writes: 0
rollback cannot undo sends: 1
safe decision: DENY_BEFORE
safe database writes: 0
safe external sends: 0
safe owner decision: ALLOW
safe owner database writes: 1
safe owner external sends: 1
~~~

**How to read it:** Bob is not the owner. The unsafe function wrote and “sent” before returning `DENY_AFTER`; both lists still contain entries. `unsafe.databaseWrites.clear()` only **simulates** DB writes being rolled back, while `externalMessages` still holds the sent event. The pre-checked function denies upfront so there are zero side effects. Alice is the owner, passes the check, and only then writes.

Do not take this example as proof that a Spring transaction will or will not roll back in a real configuration. That must be tested with a real transaction manager and advisor ordering.

## 11. Integration test: assert denial AND zero side effects

A test having only:

~~~java
assertThrows(
    AccessDeniedException.class,
    () -> service.update(id, command)
);
~~~

**is not enough**. It does not check committed database state, outbox rows, email sends, payment calls, cache writes, or broker publishes.

### 11.1. Minimum test matrix

| Case | Expected security outcome | Side effects to verify |
|---|---|---|
| User is right owner, has `document:update` | Allow | Mutation correct, event emitted once per contract |
| User lacks `document:update` | Deny before body | DB/outbox/external = 0 |
| User has permission but wrong owner | Deny | DB unchanged, external calls = 0 |
| User is right owner but wrong tenant | Deny | No mutation on cross-tenant resource |
| Anonymous user | Deny | No business mutation |
| Locked resource | Deny | Not saved/published |
| Concurrent owner change | Conflict/deny | No unauthorized mutation committed |
| `@PostAuthorize` on read-only method | Deny returned object | No DB writes/no outbound data sent |
| `@PostAuthorize` on write method | Risk of late denial | Tests must detect leaked side effects |
| Different transaction advisor order | Deny | Verify actual commit/rollback |
| Inner `REQUIRES_NEW` | Outer deny | Detect unintended inner commit |
| Outbox transactional rollback | Deny | Neither business row nor outbox row committed |
| Email before denial | Deny | Test detects email invocation; design must prevent it |
| Proxy bypass via `this.` or `new` | Detected | Do not allow call paths bypassing policy |

### 11.2. Real Spring Security test

A test skeleton in a Spring Boot project:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class DocumentCommandSecurityTest {
    @Autowired
    DocumentCommandService commands;

    @Autowired
    DocumentRepository repository;

    @Test
    @WithMockUser(username = "bob", authorities = "document:update")
    void otherOwnerCannotModifyDocument() {
        long id = 7L; // Fixture: document 7 belongs to Alice.
        assertThrows(AccessDeniedException.class,
                () -> commands.update(id, new UpdateCommand()));

        // In a full test:
        // - Re-read the DB in a new transaction and assert the row is unchanged.
        // - Assert outbox has no new event.
        // - Verify notification/payment mocks were not called.
    }
}
~~~

**This is a skeleton, not a copy-paste complete test.** It needs service/repository types, Alice/Bob fixtures, and assertions verifying real state. Never claim production QA passed just because `assertThrows` passed.

### 11.3. Avoid test rollback masking an unauthorized commit

Spring Test can automatically roll back a test transaction if the test is annotated with `@Transactional`. This can hide commits/events that would happen in production.

How to verify:

1. Create committed fixtures.
2. Call the protected service through a Spring-managed proxy.
3. Let the use case's transaction genuinely complete.
4. Read committed state from a fresh persistence context/transaction.
5. Compare fields, version, status, audit/outbox.
6. Verify external mock interactions precisely.
7. For concurrency, use separate transactions/threads and an environment-appropriate DB.

Do not rely solely on a `404`/`403` HTTP response or an in-memory entity cache to prove safety.

## 12. Advisor ordering: measure instead of guessing

A call may pass through:

~~~text
Security before-method advice
Transaction advice
Retry advice
Caching advice
Custom audit advice
Business method
Security after-method advice
~~~

The diagram is illustrative only and **does not promise a specific order**. Beyond `@Order` and advisor order constants, transaction/method-security/version configurations can affect nesting.

To clarify runtime behavior:

- Identify Spring Security/Spring Framework/Boot versions.
- Inspect `@EnableMethodSecurity`, `@EnableTransactionManagement`, `@Order`, custom advisors.
- Enable transaction begin/commit/rollback and method authorization logs in staging.
- Test denial after a method that writes to a real DB: does the DB commit or roll back?
- Test `REQUIRES_NEW`/event listeners and cross-service effects.
- Re-run regression tests when upgrading versions.

Never use the order of two annotations in source code as the basis for determining transaction nesting.

## 13. Design smells that need immediate fixing

| Smell | Risk | Fix |
|---|---|---|
| `@PostAuthorize` as the sole check on update/delete | Checked after mutation | `@PreAuthorize` + object policy |
| 403 treated as proof of “no write” | Commit may already have occurred | Test committed state |
| Email/payment inside a post-checked method | Cannot recall external actions | Pre-check before outbound call |
| `@Transactional` assumed to undo everything | Only transactional resources | Boundary analysis + outbox |
| `REQUIRES_NEW` before deny | Independent inner commit | Avoid business writes before auth |
| Catching and swallowing `AccessDeniedException` | Transaction may continue | Fail closed/propagate |
| Sending events before commit | Consumers see inconsistent events | Outbox/transaction-aware dispatch |
| Using `AFTER_COMMIT` to rescue post-checks | Commit can precede post-check | Fix authorization ordering |
| Pre-check comparing client-sent `ownerId` | Owner spoofing | Query trusted resource |
| Missing tenant/owner check | BOLA/IDOR | Object-level authorization |
| Race between pre-check and write | TOCTOU | Lock, version, conditional update |
| Protected method called via `this.` | Proxy bypass | Separate bean/integration test |
| Tests only asserting exceptions | Missed side effects | DB + broker + email assertions |

## 14. Pre-merge checklist

- [ ] Does the method modify DB, cache, files, messages, emails, payments, or any state?
- [ ] If yes, is authorization checked **before the first side-effect point**?
- [ ] Is `@EnableMethodSecurity` enabled and does bean/method invocation go through a Spring proxy?
- [ ] Are both functional permission and **real resource** permission (owner/tenant/state) checked?
- [ ] Are client-declared `ownerId`/`tenantId` never used as proof?
- [ ] Is there locking/versioning/conditional writing against TOCTOU?
- [ ] Are transaction begin, flush, commit, and post-check clearly distinguished?
- [ ] Are advisor order, rollback rules, and propagation tested for the real deployment?
- [ ] Are you aware `REQUIRES_NEW` or other services can commit independently?
- [ ] Are external effects executed after authorization with idempotency/retries?
- [ ] Is the outbox committed atomically with business rows when needed?
- [ ] Is `@TransactionalEventListener` not mistaken for a delivery guarantee?
- [ ] If `@PostAuthorize` is on a read, is the real method body free of business side effects?
- [ ] Do denial tests assert **DB unchanged, outbox unchanged, external calls = 0**?
- [ ] Are tests free from test-level rollback masking committed state?
- [ ] Are there no bypass paths via self-invocation, `new` instances, or unproxyable methods?
- [ ] Are auditing and monitoring in place for irreversible operations?

**Conclusion:** *Use `@PostAuthorize` to restrict the result returned after an appropriate call. For state-changing operations, check permissions before side effects, recheck the resource inside the transaction, and handle external effects under reliable contracts.*

## 15. Self-check questions

**1. When does `@PostAuthorize` run?**  
After the method body has produced a result for the after-method interceptor.

**2. If `@PostAuthorize` denies, is it certain `repository.save` did not run?**  
No; the body may already have called save/flush before denial.

**3. Does HTTP 403 prove the DB did not change?**  
No. You must read committed state and verify outbound side effects.

**4. Does `@Transactional` always roll back when a post-check denies?**  
No. It depends on advisor order, transaction boundaries, propagation, and rollback rules.

**5. Why is an already-sent email hard to undo?**  
External delivery is outside the local DB transaction; the message may already have reached the recipient.

**6. How does `@PreAuthorize` protect writes better?**  
It can block before the body runs, provided the invocation is proxied and the policy is accurate.

**7. Why must owner/tenant still be checked inside the transaction?**  
To guard against state changing between pre-check and mutation (TOCTOU).

**8. Can an outbox fix an unauthorized write that already committed?**  
No. Outbox ensures coupling DB + event intent; authorization must pass before commit.

**9. Does an `AFTER_COMMIT` listener guarantee not sending when a post-check denies?**  
No, if commit already happened before the post-check.

**10. Why is `REQUIRES_NEW` dangerous here?**  
It has an independent physical transaction and can commit regardless of outer denial/rollback.

**11. Is a test only asserting `AccessDeniedException` sufficient?**  
No; you must verify committed DB state and external calls.

**12. Is compensation the same as rollback?**  
No; compensation is a new action and does not guarantee erasing all consequences that occurred.

## 16. Official references

- Spring Security – **Method Security**, section *Authorizing Method Results with @PostAuthorize* and warning about database writes: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security – **Method Security Testing**: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Framework – **Declarative Transactions: Rolling Back**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework – **Transaction Propagation** and `REQUIRES_NEW`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework – **Transaction-bound Events** and `@TransactionalEventListener`: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework – **Proxying Mechanisms**: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Security – **Authorization Architecture**: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
