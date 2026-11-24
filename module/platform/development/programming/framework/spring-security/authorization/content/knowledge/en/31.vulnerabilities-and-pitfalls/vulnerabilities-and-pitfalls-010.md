# Confusing Result Filtering with Blocking Action Execution

> **Context:** Spring Security – authorization, **Mistakes and Vulnerabilities** group. This lesson targets Spring Security 6 / Spring Boot 3.x, Java 17+, and Spring AOP proxy-based method security. The focus is distinguishing **which data is shown** from **which action is allowed to run**.

## 1. The Problem: A Safe Response Does Not Mean a Safe Action

**Result filtering** only decides which records or data fields are returned to the caller. For example: filtering a list so Alice only sees Alice's documents, or stripping `internalNote` from JSON.

**Action authorization** must decide **before effects occur** whether the actor is permitted to perform the specific operation on the specific resource: creating, editing, deleting, approving, refunding, sending notifications, or calling external system APIs.

An endpoint can return `[]` or HTTP 403 **after** already modifying the database, sending emails, or publishing messages. That is a severe defect: the filtered response creates the illusion that the action was denied, while side effects already executed.

Four things must be verified **separately**:

1. **Action permission:** does the actor have permission to perform this kind of operation (e.g., `document:update`, `refund:approve`)?
2. **Object/tenant scope:** on which document/order/tenant/owner is the operation permitted?
3. **Side effects:** did the database, queue, email, HTTP, file, cache, or audit change **before denial**?
4. **Response visibility:** was returned data filtered to the right rows/fields?

Getting item 4 right does not prove items 1–3 are right. **Reading a list** and **executing a mutation** are two different kinds of workflows requiring different policies and tests.

## 2. Method Security: Where to Block, Where to Filter?

### 2.1. Timeline of a Vulnerability

```text
WRONG – filtering results after mutation:
Alice's request (owner="bob")
    │
    ▼
Service.action(...)
    ├─ UPDATE Bob's document         ← already modified
    ├─ send notification             ← external effect already emitted
    └─ return list of documents
          │
          ▼
    @PostFilter removes Bob's record
          │
          ▼
    Response = []                    ← only hides the result


RIGHT – protecting before the action:
Alice's request
    │
    ▼
Determine trusted actor, action, resource, tenant/state
    │
    ▼
@PreAuthorize / policy / conditional update
    ├─ DENY → stop before DB/gateway
    └─ ALLOW → execute on the exact permitted resource
                     │
                     ▼
                filter response if needed
```

### 2.2. Which Tool Does Which Job?

| Mechanism | When It Runs | Blocks Body Before Side Effects? | Appropriate Role |
| --- | --- | --- | --- |
| `@PreAuthorize` | Before method invocation | **Yes**, when intercepted by the advice | Action permission, role/scope, and resource policy |
| `@PostAuthorize` | After body returns result | **No** | Result-based authorization, mainly reads; use cautiously for writes |
| `@PostFilter` | After body produces supported collection/map/stream | **No** | Restricting visible elements in the result |
| `@PreFilter` | Filters collection argument before body runs | **Does not by itself prove** the whole action is allowed | Selecting input items; requires separate action/policy checks |
| DTO/JSON field masking | During response mapping/serialization | **No** | Hiding sensitive fields from JSON |
| Frontend filtering | After client receives data | **No** | UI presentation, not server protection |
| Query-scope `WHERE tenant_id = ?` | When reading/writing database | Only when applied to the right operation and context | Limiting accessed/mutated rows, enforcing tenant isolation |

With Spring Security 6, `@EnableMethodSecurity` registers method-security interceptors. Annotations take effect only when called through a Spring proxy: unit tests instantiating the service with `new` or `this.securedMethod()` calls inside the same bean can bypass advice. Always test through a Spring-injected bean.

**Do not treat `@PostFilter` as a firewall for the method:** it processes the *return value*; it does not prevent SQL statements, network calls, or in-memory mutations that already executed inside the method body. Even when the filtered collection is empty, the body may still have processed every record.

### 2.3. `@PostAuthorize` Also Runs After the Body

With a method like:

```java
@PostAuthorize("returnObject.owner() == authentication.name")
public Receipt process(String owner) {
    database.write(/* ... */);
    paymentGateway.charge(/* ... */);
    return /* Receipt belonging to owner */;
}
```

the condition referencing `returnObject` is evaluated only **after** the body runs. If the caller lacks permission, Spring may throw `AccessDeniedException`, yet the payment request has already been sent. For DB work inside `@Transactional`, commit/rollback depends on transaction boundaries, advice ordering, and rollback rules; **do not assume** “denied = full rollback” or “denied always commits”. Measure real DB state and out-of-transaction side effects after the call.

## 3. Common Real-World Vulnerabilities

### 3.1. IDOR/BOLA: Hiding Owner Yet Allowing Edits by ID

Alice may only edit Alice's documents. The API receives `PATCH /documents/57`, where ID 57 belongs to Bob. A faulty implementation (pseudocode, not a complete file):

```java
public List<DocumentDto> renameThenList(long id, String title) {
    repository.rename(id, title);             // WRONG: ignores owner
    notificationGateway.sendRenamed(id);      // Notification already sent
    return repository.findAll().stream()
        .filter(doc -> doc.owner().equals(currentUsername()))
        .map(mapper::toDto)
        .toList();
}
```

Alice may receive an empty list and still have modified Bob's document. Replacing `.filter` with `@PostFilter` fixes nothing; the user simply **does not see** Bob's document after editing it. Hiding `ownerId` in the DTO only addresses field exposure, not **Broken Object Level Authorization (BOLA/IDOR)**.

### 3.2. Function Scope Does Not Equal Object Permission

`@PreAuthorize("hasAuthority('SCOPE_documents.write')")` checks write permission **in general**, yet does not prove the caller may edit *document id 57*. Actor–action–resource–context must check role/scope, owner, tenant, status (e.g., editable only when `DRAFT`), and business relationships. Never trust client-supplied `ownerId` or `tenantId` by default; derive them from the authenticated principal/verified tenant context.

### 3.3. `@PreFilter` Can Still Execute the Wrong Kind of Action

When a method takes a list of documents to “approve”, `@PreFilter` can drop items not owned by Alice. Yet the method still runs on the remaining items and may trigger shared effects. Alice **owning** a document does not automatically prove Alice may **approve** it. For batches, define the contract clearly: reject the whole batch if any item is unauthorized (all-or-nothing) or process partially; test DB/notifications against that exact contract.

### 3.4. Only Hiding Buttons or Filtering Data on the Client

Hiding a `Delete` button in React does not block manual cURL/Postman requests. Client-side list filtering after fetching also leaks unfiltered data in the browser Network tab. All mutations must be authorized on the backend at the execution boundary.

## 4. Java 17+ Integration Test Demonstrating by Observation

The test suite below uses Spring Boot 3.x, Spring Security 6.x, JUnit 5. `DocumentStore` stores records in memory; `SendingGateway` counts “sent” notifications. They are **not part of a database transaction**: tests directly prove output filtering does not undo state or external effects. The test invokes a **Spring-injected bean** so the method-security interceptor actually runs.

In a module with Spring Boot dependency management configured:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Create file **`src/test/java/example/security/FilteringIsNotAuthorizationTest.java`**:

```java
package example.security;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = FilteringIsNotAuthorizationTest.App.class)
class FilteringIsNotAuthorizationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity
    @Import({DocumentStore.class, SendingGateway.class, DocumentService.class})
    static class App {}

    public record Document(long id, String owner, String title) {}

    public static class DocumentStore {
        private final AtomicLong ids = new AtomicLong();
        private final List<Document> documents = new CopyOnWriteArrayList<>();

        public Document add(String owner, String title) {
            Document doc = new Document(ids.incrementAndGet(), owner, title);
            documents.add(doc);
            return doc;
        }

        // Return a mutable List so @PostFilter can remove elements.
        public List<Document> all() {
            return new ArrayList<>(documents);
        }

        public void reset() {
            documents.clear();
            ids.set(0);
        }
    }

    // Simulates an external effect: cannot be rolled back by a DB transaction.
    public static class SendingGateway {
        private final AtomicInteger count = new AtomicInteger();

        public void send() {
            count.incrementAndGet();
        }

        public int sent() {
            return count.get();
        }

        public void reset() {
            count.set(0);
        }
    }

    public static class DocumentService {
        private final DocumentStore store;
        private final SendingGateway sending;

        public DocumentService(DocumentStore store, SendingGateway sending) {
            this.store = store;
            this.sending = sending;
        }

        // Valid for READ: returns only the current viewer's documents.
        @PostFilter("filterObject.owner() == authentication.name")
        public List<Document> visibleDocuments() {
            return store.all();
        }

        // VULNERABILITY: write/send already happened BEFORE @PostFilter ran.
        @PostFilter("filterObject.owner() == authentication.name")
        public List<Document> unsafeCreateThenFilter(
            String owner, String title) {

            store.add(owner, title);
            sending.send();
            return store.all();
        }

        // VULNERABILITY: checking permission via returnObject is too late.
        @PostAuthorize("returnObject.owner() == authentication.name")
        public Document unsafeCreateThenCheck(String owner, String title) {
            Document doc = store.add(owner, title);
            sending.send();
            return doc;
        }

        // Blocks BEFORE the method body creates side effects.
        // #p0 is the first parameter (owner), independent of -parameters.
        @PreAuthorize("isAuthenticated() and #p0 == authentication.name")
        public Document createIfAllowed(String owner, String title) {
            Document doc = store.add(owner, title);
            sending.send();
            return doc;
        }
    }

    @Autowired DocumentStore store;
    @Autowired SendingGateway sending;
    @Autowired DocumentService service;

    @BeforeEach
    void reset() {
        store.reset();
        sending.reset();
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void readFilterChangesOnlyResponse() {
        store.add("alice", "Mine");
        store.add("bob", "His");

        List<Document> visible = service.visibleDocuments();

        assertEquals(
            List.of("alice"),
            visible.stream().map(Document::owner).toList());
        assertEquals(2, store.all().size()); // Bob stays in store.
        assertEquals(0, sending.sent());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void postFilterDoesNotBlockUnauthorizedAction() {
        List<Document> visible =
            service.unsafeCreateThenFilter("bob", "Changed");

        assertTrue(visible.isEmpty());       // Response was filtered.
        assertEquals(1, store.all().size()); // Mutation already occurred.
        assertEquals("bob", store.all().get(0).owner());
        assertEquals(1, sending.sent());     // Event was already sent.
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void postAuthorizeDenyHappensAfterSideEffects() {
        assertThrows(AccessDeniedException.class,
            () -> service.unsafeCreateThenCheck("bob", "Changed"));

        assertEquals(1, store.all().size());
        assertEquals(1, sending.sent());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void preAuthorizeDeniesBeforeSideEffects() {
        assertThrows(AccessDeniedException.class,
            () -> service.createIfAllowed("bob", "Changed"));

        assertEquals(0, store.all().size());
        assertEquals(0, sending.sent());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void validActionStillRuns() {
        Document result = service.createIfAllowed("alice", "Allowed");

        assertEquals("alice", result.owner());
        assertEquals(1, store.all().size());
        assertEquals(1, sending.sent());
    }
}
```

Run tests from the corresponding Gradle project/module:

```bash
./gradlew test --tests "example.security.FilteringIsNotAuthorizationTest"
```

On Windows, use `gradlew.bat`; multi-project Gradle builds may require `:module-path:test`. **Expected result: 5 tests PASS**, based on JUnit assertions; there is no fixed stdout.

**Explanation:**

- `readFilterChangesOnlyResponse`: Alice sees only her own document while Bob remains in the store. That is valid output-filtering behavior for reads.
- `postFilterDoesNotBlockUnauthorizedAction`: Alice receives an empty list yet the store already contains Bob's document and the gateway already ran. This is the core proof of the vulnerability.
- `postAuthorizeDenyHappensAfterSideEffects`: `AccessDeniedException` occurs **after** write/send; the model intentionally uses non-transactional resources to prove denial does not revoke effects.
- `preAuthorizeDeniesBeforeSideEffects`: the call is denied before the method body, leaving both store and gateway unchanged.
- `validActionStillRuns`: authorized operations still succeed.

In real applications, do not accept `owner` from the client and trust it as the principal. The demo uses `#p0 == authentication.name` to illustrate an object-specific rule; real services should derive identity from the authenticated principal and enforce business policies, including delegation/admin privileges when needed.

## 5. Preventing IDOR/BOLA Directly in DB Mutations

### 5.1. `hasRole` or `hasAuthority` Alone Is Insufficient

A method with `@PreAuthorize("hasAuthority('SCOPE_documents.write')")` can still be exploited if the SQL updates by ID without checking owner/tenant:

```java
@PreAuthorize("hasAuthority('SCOPE_documents.write')")
public void rename(long documentId, String title) {
    repository.renameById(documentId, title);
}
```

Policy must check the actor's permission on the **specific resource**, not just permission to call the function. If a race exists between “check owner” and “update”, the object's state/owner may change between steps. A useful pattern is a conditional SQL mutation within **the same statement**.

```sql
UPDATE document
   SET title = :new_title
 WHERE id = :document_id
   AND tenant_id = :trusted_tenant_id
   AND owner_id = :authenticated_user_id
   AND status = 'DRAFT';
```

Check the row count: `1` means one resource matched the exact conditions; `0` means no valid resource was available to update. The snippet below is an **illustration inside a service with JDBC and trusted context**, not a standalone Java class:

```java
int updated = jdbc.update("""
    UPDATE document
       SET title = ?
     WHERE id = ?
       AND tenant_id = ?
       AND owner_id = ?
       AND status = 'DRAFT'
    """, newTitle, documentId, trustedTenantId, authenticatedUserId);

if (updated != 1) {
    throw new AccessDeniedException("Document unavailable");
}
// Only after permission/mutation succeeds, schedule notification/outbox.
```

The `trustedTenantId` value must come from the authenticated/authorized context, never taken verbatim from body/query params. The API should consistently return 403/404 for non-existent/out-of-scope resources to avoid leaking ID existence. For complex workflows, verify transitions and version/concurrency; database row-level security is an additional defense layer, not a replacement for action permissions.

### 5.2. Filter Directly in Queries When Reading Multiple Records

`@PostFilter` is useful for small lists, yet the method may still load every row before filtering. In multi-tenant systems, query scoping is usually more suitable:

```sql
SELECT id, owner_id, title
FROM document
WHERE tenant_id = :trusted_tenant_id
  AND owner_id = :authenticated_user_id
ORDER BY id
LIMIT :page_size OFFSET :offset;
```

Filtering **before** pagination ensures total counts/pages align with the set of viewable records, avoiding pages suddenly becoming empty or short after `@PostFilter`. Query scoping reduces load and leak risks through logs/caches; it **does not** excuse running an unguarded `UPDATE`/`DELETE` lacking equivalent predicates.

## 6. Transactions and Side Effects: Measure After the Action Finishes

`@Transactional` covers only resources coordinated by the transaction manager. A runtime exception escaping the boundary usually triggers a DB rollback under default rules, yet does not undo already-sent emails/HTTP calls/messages, altered files/caches, or separate `REQUIRES_NEW` transactions that already committed.

**With `@PostAuthorize`:** because the post-check runs after the body, DB changes may roll back or commit depending on advisor ordering and transaction boundaries. Therefore tests should observe simultaneously:

- DB state **after** the service returns/throws;
- Gateway invocation counts and confirmations from external systems;
- Outbox rows/events if present;
- Exception/HTTP status and returned data.

If events must only be emitted after commit, `@TransactionalEventListener(phase = AFTER_COMMIT)` helps defer listeners; a transactional outbox supports reliable event publishing with retries/idempotency. Neither **replaces** pre-action permission checks. Avoid annotating tests that inspect service transaction boundaries with `@Transactional`, because test-managed transactions can mask bugs and auto-rollback afterward.

A test that only checks `verify(repository).save(...)` or HTTP 403 **does not** prove the DB committed/rolled back or that external side effects did not occur. Use JDBC/JPA + H2 or Testcontainers when real transaction evidence is needed.

## 7. Mandatory Test Matrix for Authorization

| Case | Response Expectation | What Must Be Verified Outside the Response |
| --- | --- | --- |
| Alice lists documents | Only Alice's data | Zero rows created/edited/deleted, no notifications emitted |
| Alice GETs Bob's document by ID | 403/404 per policy | No content leaked, no state changed |
| Alice PATCHes Bob's document | DENY | DB/queue/email/cache **unchanged** |
| Alice has write scope but wrong tenant | DENY | Other tenant's rows unaffected |
| Alice sends batch mixing allowed and disallowed resources | Per batch contract | Verify every row and side effect matches atomic/partial contract |
| Alice calls WRITE method having only `@PostFilter` | Response may be `[]` | Must detect that the unauthorized action still ran |
| Alice calls WRITE with `@PostAuthorize` | Denied after method | DB and gateway must be inspected, not inferred from exception |
| Alice edits her own resource in valid status | Succeeds | Right row modified, valid event, no other rows altered |

Add HTTP tests (`MockMvc`) to ensure 403/404 mapping; `@WithMockUser` method tests only fabricate principal/authorities and do not test token/session authentication mechanisms. For method security, always verify the actual call path traverses the Spring proxy and is not bypassed by self-invocation.

## 8. Myths and Remedies

**“Hiding the button in the UI locks the action.”** Incorrect: callers can send manual requests. The server must enforce policy before mutation.

**“An empty response means no data was affected.”** Incorrect: `@PostFilter` only sanitizes what is visible. Directly assert row counts, versions, owners, and event/counters.

**“`@PostAuthorize` throws `AccessDeniedException`, so everything rolls back automatically.”** No general guarantee exists. The method already ran; effects outside the transaction do not reverse themselves. For DB, inspect actual transactions and advisor order.

**“`@PreFilter` removes foreign-owned items, so batch approve is safe.”** Insufficient: check role/action, status, scope, and the contract for handling invalid batch items.

**“`@PreAuthorize('isAuthenticated()')` prevents IDOR.”** Authentication only proves who the caller is; authorization must bind resource/tenant/operation. Owner/tenant must not rely on untrusted input.

**“`@Transactional` handles permissions and events automatically.”** Transactions do not decide policy; DB rollback does not undo API calls/emails. Place guards before the action and design outbox/after-commit as needed.

**“Client or DTO filtering replaces object-level authorization.”** DTO masking protects returned fields; BOLA/IDOR concerns per-object access permissions. These are two independent protection layers.

## 9. Secure Design Checklist

1. Identify actor, operation, resource, tenant/state, and all side effects for each endpoint.
2. Block actions **before the body**: `@PreAuthorize`, policy services, and DB row predicates where needed. Ensure the Spring proxy actually intercepts.
3. Never rely on result filtering, DTOs, frontend code, or HTTP status to prove execution permissions.
4. For ID-based mutations, enforce real resource/tenant scope; consider conditional SQL to reduce races.
5. For reads, scope data in queries before pagination and use output filtering where appropriate.
6. Test deny-paths via **zero mutation + zero outbound side effects**, not just `assertThrows`/403/`[]`.
7. Test allow-paths to avoid false denials, verifying DB state and proper responses.
8. Separately test rollback, after-commit, and outbox/retry when transactional workflows and external systems exist.

**Key takeaway:** *Result filtering* answers “what does the user **see**?”; *action authorization* answers “what is the user **allowed to do on which object**?”. Place the guard **before mutation** and prove it via system state **after the call finishes**.

## Official References

- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html) – `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter`, interceptors.
- [Spring Security – Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html) – `@WithMockUser`, Spring Test integration.
- [Spring Framework – AOP Proxying](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html) – self-invocation/proxy boundaries.
- [Spring Framework – Declarative Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html) – transactions/rollback and advice.
- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html) – `@TransactionalEventListener`.
- [OWASP API Security Top 10 – Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/) – per-resource permission checks.
