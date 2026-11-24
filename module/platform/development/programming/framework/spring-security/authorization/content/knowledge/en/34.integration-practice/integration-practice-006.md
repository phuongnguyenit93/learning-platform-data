# Implementing PermissionEvaluator for Read, Edit, and Share Permissions

> **Context:** Spring Security – authorization, **Integration Practice** group. This lesson applies Spring Security 6.x / Spring Boot 3.x and Java 17+. Examples run with JUnit 5, testing real method security through a Spring proxy and using an in-memory repository to observe permissions and side effects. For a production database, add transactions, concurrency checks, and tenant constraints at the DB layer.

## 1. Problem Statement and Authorization Rules

A document management application has `id`, `tenant`, `owner`, `title`, plus `readers` and `editors` lists. The service exposes three actions:

- **`read`:** read the document title/content. Owner, editors, and readers in the same tenant are allowed.
- **`edit`:** modify the title/content. Owner and editors in the same tenant are allowed; readers have read-only access.
- **`share`:** grant read permission to another user. In this lesson **only the owner** may share; editors cannot self-escalate privileges.
- **Tenant isolation:** even if the caller matches the owner or appears in an ACL, documents belonging to another tenant must still be denied. The caller's tenant comes from a trusted authentication context.
- **Fail closed:** nonexistent IDs, unknown resource types, unknown permissions, anonymous principals, or insufficient context all receive `false`.

Permission matrix:

| Actor–Document Relationship | Read | Edit | Share |
| --- | :---: | :---: | :---: |
| Owner in same tenant | ✅ | ✅ | ✅ |
| Editor in same tenant | ✅ | ✅ | ❌ |
| Reader in same tenant | ✅ | ❌ | ❌ |
| No permission, same tenant | ❌ | ❌ | ❌ |
| Different tenant even with matching owner | ❌ | ❌ | ❌ |
| Anonymous or nonexistent document | ❌ | ❌ | ❌ |

A real application may have administrators, delegates, or share expirations; those are **explicit additional policies**, never implicitly letting `ROLE_ADMIN` bypass tenant boundaries.

**Learning goal:** Write a `PermissionEvaluator` implementing the entire matrix above, wire it into `DefaultMethodSecurityExpressionHandler`, use `@PreAuthorize` to block before the method body, and prove via integration tests that every DENY case **does not modify the document, write to the ACL, or send notifications**.

## 2. How Does Spring Security Invoke PermissionEvaluator?

Spring method security is enabled with `@EnableMethodSecurity`. `@PreAuthorize` runs through a Spring AOP interceptor before the service call. The SpEL expression `hasPermission(...)` uses the evaluator configured on `MethodSecurityExpressionHandler`:

```text
Authenticated caller
   │
   ▼
DocumentService Spring proxy
   │
   ▼
@PreAuthorize("hasPermission(#p0, 'DOCUMENT', 'edit')")
   │
   ▼
MethodSecurityExpressionHandler → PermissionEvaluator
   │
   ├─ extract actor from Authentication
   ├─ load canonical resource by ID
   ├─ match tenant
   └─ evaluate read/edit/share action
         │
         ├─ false → AccessDeniedException → DO NOT run body
         └─ true  → invoke DocumentService.edit(...) → mutation
```

**Authentication** answers who the caller is; `GrantedAuthority` may hold roles/scopes/tenants from the authentication source; **object permission** answers what that user may do on a *specific document*. `hasAuthority('document:write')` does not by itself know the owner/ACL of `documentId=10`. If both functional permission and object permission are required, use AND logic:

```java
// Illustrative snippet inside a service, not a standalone class.
@PreAuthorize("hasAuthority('document:write') "
    + "and hasPermission(#p0, 'DOCUMENT', 'edit')")
public void edit(long documentId, String newTitle) { /* ... */ }
```

Never use OR when both scope and object permission are mandatory. In the complete runnable example below, the policy focuses on `hasPermission` so the evaluator's behavior stands out clearly.

### 2.1. The Two Required Interface Overloads

```java
// Signatures excerpted from org.springframework.security.access.PermissionEvaluator.
boolean hasPermission(
    Authentication authentication,
    Object targetDomainObject,
    Object permission
);

boolean hasPermission(
    Authentication authentication,
    Serializable targetId,
    String targetType,
    Object permission
);
```

The **object overload** serves `hasPermission(#document, 'read')` when a document instance is already available. The **ID/type overload** serves `hasPermission(#documentId, 'DOCUMENT', 'edit')` when the service only receives an ID. `targetType` is an application-defined domain identifier; the example uses the exact string constant `DOCUMENT`. Since `permission` is an `Object`, validate its type and allowed actions rather than trusting arbitrary strings.

If a controller receives a JSON object with `owner`, `tenant`, or `readers` fields, an actor could claim to be the owner. Therefore, in this practice, the object overload **takes only the ID** and delegates to the ID overload to **load the canonical record from the store**. This incurs a lookup cost yet makes it straightforward to prove forged objects are never trusted.

### 2.2. Placing Guards Before Side Effects

`@PreAuthorize` checks before the body. `@PostAuthorize` evaluates after the body has produced a result; if used as the sole guard on `share`, the ACL or email might already have changed before denial. `@PostFilter` only filters result elements and does not undo mutations. Use pre-authorization for `edit/share` and assert **data state after DENY**, not just exceptions.

Method security intercepts only calls passing through a **Spring-managed proxy**. Unit tests using `new DocumentService(...)` or methods in the same bean calling `this.edit(...)` can bypass the advice. In section 4's tests, the service instance is injected via `@Autowired` from Spring to test the real execution path.

## 3. Implementing the Policy: Rules Before Code

Policy inputs are `(Authentication, documentId, action)`, not filtered response results.

```text
If authentication is missing/anonymous → DENY
If targetType is not DOCUMENT, or id has wrong type → DENY
If action is not one of read/edit/share → DENY
If document does not exist → DENY
If actor has no trusted tenant matching document.tenant → DENY

read  = owner OR editor OR reader
edit  = owner OR editor
share = owner
```

In tests, authority `TENANT_acme` represents a tenant granted by a trusted authentication mechanism. Real applications must **verify the tenant** from a validated principal/token or an explicit policy context, never blindly copying an `X-Tenant` header or request body field. Avoid using username as a global identity in systems allowing duplicate usernames across tenants; use user ID/subject + tenant/issuer instead.

Sharing is an **ACL-mutating** operation, distinct from editing content. The example grants **read permission** only to the recipient; it never grants edit or further sharing rights.

## 4. Runnable Example: Spring Boot 3.x, Java 17, JUnit 5

The test suite creates a lightweight Spring context without starting a web server. `DocumentStore` is an in-memory store immutable per record; `NotificationGateway` counts sends. `@WithMockUser` simulates actors belonging to different tenants.

### 4.1. Dependencies

In a Gradle module already using the Spring Boot plugin/BOM:

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

If these dependencies are already present, do not duplicate them. Create **one file** `src/test/java/example/security/PermissionEvaluatorIntegrationTest.java`:

```java
package example.security;

import java.io.Serializable;
import java.util.HashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.PermissionEvaluator;
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    classes = PermissionEvaluatorIntegrationTest.App.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class PermissionEvaluatorIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableMethodSecurity
    @Import({
        DocumentStore.class,
        DocumentPermissionEvaluator.class,
        DocumentService.class,
        NotificationGateway.class
    })
    static class App {

        // static @Bean ensures the handler is published early,
        // before Spring initializes method-security configuration.
        @Bean
        static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            DocumentPermissionEvaluator permissionEvaluator
        ) {
            DefaultMethodSecurityExpressionHandler handler =
                new DefaultMethodSecurityExpressionHandler();
            handler.setPermissionEvaluator(permissionEvaluator);
            return handler;
        }
    }

    public record Document(
        long id, String tenant, String owner, String title,
        Set<String> readers, Set<String> editors
    ) {
        // Do not share mutable Sets across callers.
        public Document {
            readers = Set.copyOf(readers);
            editors = Set.copyOf(editors);
        }
    }

    public static class DocumentStore {
        private final Map<Long, Document> documents =
            new ConcurrentHashMap<>();

        public void reset() {
            documents.clear();
        }

        public void seed(Document document) {
            documents.put(document.id(), document);
        }

        public Optional<Document> find(long id) {
            return Optional.ofNullable(documents.get(id));
        }

        public Document require(long id) {
            return find(id).orElseThrow();
        }

        public void rename(long id, String title) {
            documents.computeIfPresent(id, (key, doc) ->
                new Document(
                    doc.id(), doc.tenant(), doc.owner(), title,
                    doc.readers(), doc.editors()
                )
            );
        }

        public void grantRead(long id, String recipient) {
            documents.computeIfPresent(id, (key, doc) -> {
                Set<String> readers = new HashSet<>(doc.readers());
                readers.add(recipient);
                return new Document(
                    doc.id(), doc.tenant(), doc.owner(), doc.title(),
                    readers, doc.editors()
                );
            });
        }
    }

    // Simulates side effects outside the database transaction.
    public static class NotificationGateway {
        private final AtomicInteger sends = new AtomicInteger();

        public void send() {
            sends.incrementAndGet();
        }

        public int count() {
            return sends.get();
        }

        public void reset() {
            sends.set(0);
        }
    }

    public static class DocumentPermissionEvaluator
        implements PermissionEvaluator {

        private final DocumentStore store;

        public DocumentPermissionEvaluator(DocumentStore store) {
            this.store = store;
        }

        @Override
        public boolean hasPermission(
            Authentication authentication,
            Object targetDomainObject,
            Object permission
        ) {
            // Do not trust owner/tenant on a client-constructed object:
            // keep only the ID and reload the canonical document from the store.
            if (!(targetDomainObject instanceof Document doc)) {
                return false;
            }
            return hasPermission(
                authentication, Long.valueOf(doc.id()),
                "DOCUMENT", permission
            );
        }

        @Override
        public boolean hasPermission(
            Authentication authentication,
            Serializable targetId,
            String targetType,
            Object permission
        ) {
            if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
                return false;
            }

            if (!"DOCUMENT".equals(targetType)
                || !(targetId instanceof Long id)
                || !(permission instanceof String operation)) {
                return false;
            }

            String action = operation.toLowerCase(Locale.ROOT);
            if (!Set.of("read", "edit", "share").contains(action)) {
                return false;
            }

            Optional<Document> found = store.find(id);
            if (found.isEmpty()) {
                return false;
            }
            Document doc = found.get();

            // TENANT_* is an authority from trusted authentication.
            boolean sameTenant = authentication.getAuthorities().stream()
                .anyMatch(granted -> (
                    "TENANT_" + doc.tenant()
                ).equals(granted.getAuthority()));
            if (!sameTenant) {
                return false;
            }

            String actor = authentication.getName();
            boolean owner = doc.owner().equals(actor);

            return switch (action) {
                case "read" -> owner
                    || doc.readers().contains(actor)
                    || doc.editors().contains(actor);
                case "edit" -> owner || doc.editors().contains(actor);
                case "share" -> owner;
                default -> false;
            };
        }
    }

    public static class DocumentService {
        private final DocumentStore store;
        private final NotificationGateway notifications;

        public DocumentService(
            DocumentStore store, NotificationGateway notifications
        ) {
            this.store = store;
            this.notifications = notifications;
        }

        @PreAuthorize("hasPermission(#p0, 'DOCUMENT', 'read')")
        public String read(long documentId) {
            return store.require(documentId).title();
        }

        @PreAuthorize("hasPermission(#p0, 'DOCUMENT', 'edit')")
        public void edit(long documentId, String title) {
            store.rename(documentId, title);
            notifications.send();
        }

        @PreAuthorize("hasPermission(#p0, 'DOCUMENT', 'share')")
        public void shareRead(long documentId, String recipient) {
            if (recipient == null || recipient.isBlank()) {
                throw new IllegalArgumentException("Invalid recipient");
            }
            // Example assumes recipient is valid in the same tenant.
            // Production must check the recipient's tenant/membership.
            store.grantRead(documentId, recipient);
            notifications.send();
        }
    }

    @Autowired DocumentStore store;
    @Autowired DocumentService service;
    @Autowired DocumentPermissionEvaluator evaluator;
    @Autowired NotificationGateway notifications;

    @BeforeEach
    void seed() {
        store.reset();
        notifications.reset();

        // ID 10: owner alice, editor bob, reader carol.
        store.seed(new Document(
            10L, "acme", "alice", "Original",
            Set.of("carol"), Set.of("bob")
        ));

        // ID 20: username alice is also owner,
        // yet the document belongs to tenant globex, different from acme.
        store.seed(new Document(
            20L, "globex", "alice", "Other tenant",
            Set.of("alice"), Set.of("alice")
        ));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "TENANT_acme")
    void ownerCanReadEditAndShare() {
        assertEquals("Original", service.read(10L));
        service.edit(10L, "Revised");
        service.shareRead(10L, "dave");

        assertEquals("Revised", store.require(10L).title());
        assertTrue(store.require(10L).readers().contains("dave"));
        assertEquals(2, notifications.count());
    }

    @Test
    @WithMockUser(username = "bob", authorities = "TENANT_acme")
    void editorCanReadAndEditButCannotShare() {
        assertEquals("Original", service.read(10L));
        service.edit(10L, "Edited by Bob");
        assertThrows(AccessDeniedException.class,
            () -> service.shareRead(10L, "dave"));

        assertEquals("Edited by Bob", store.require(10L).title());
        assertFalse(store.require(10L).readers().contains("dave"));
        assertEquals(1, notifications.count());
    }

    @Test
    @WithMockUser(username = "carol", authorities = "TENANT_acme")
    void readerCannotEditOrShareAndHasNoSideEffects() {
        assertEquals("Original", service.read(10L));
        assertThrows(AccessDeniedException.class,
            () -> service.edit(10L, "Tampered"));
        assertThrows(AccessDeniedException.class,
            () -> service.shareRead(10L, "dave"));

        assertEquals("Original", store.require(10L).title());
        assertFalse(store.require(10L).readers().contains("dave"));
        assertEquals(0, notifications.count());
    }

    @Test
    @WithMockUser(username = "dave", authorities = "TENANT_acme")
    void unrelatedUserCannotReadEditOrShare() {
        assertThrows(AccessDeniedException.class,
            () -> service.read(10L));
        assertThrows(AccessDeniedException.class,
            () -> service.edit(10L, "Tampered"));
        assertThrows(AccessDeniedException.class,
            () -> service.shareRead(10L, "eve"));

        assertEquals("Original", store.require(10L).title());
        assertEquals(0, notifications.count());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "TENANT_acme")
    void tenantBoundaryOverridesEvenOwnerAndAcl() {
        assertThrows(AccessDeniedException.class,
            () -> service.read(20L));
        assertThrows(AccessDeniedException.class,
            () -> service.edit(20L, "Tampered"));
        assertThrows(AccessDeniedException.class,
            () -> service.shareRead(20L, "dave"));

        assertEquals("Other tenant", store.require(20L).title());
        assertEquals(0, notifications.count());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "TENANT_acme")
    void unknownResourcesAndUnsupportedPermissionsDeny() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        assertFalse(evaluator.hasPermission(
            authentication, 999L, "DOCUMENT", "read"));
        assertFalse(evaluator.hasPermission(
            authentication, 10L, "DOCUMENT", "delete"));
        assertFalse(evaluator.hasPermission(
            authentication, 10L, "ORDER", "read"));
        assertFalse(evaluator.hasPermission(
            authentication, (Object) null, "read"));

        assertThrows(AccessDeniedException.class,
            () -> service.read(999L));
        assertEquals(0, notifications.count());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "TENANT_acme")
    void objectOverloadUsesCanonicalStoreNotForgedFields() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        assertTrue(evaluator.hasPermission(
            authentication, store.require(10L), "share"));

        // Caller forges tenant/owner on object id=20.
        // Canonical store still keeps id=20 in tenant globex.
        Document forged = new Document(
            20L, "acme", "alice", "Forged",
            Set.of("alice"), Set.of("alice")
        );

        assertFalse(evaluator.hasPermission(
            authentication, forged, "share"));
        assertEquals("Other tenant", store.require(20L).title());
    }
}
```

The test uses `#p0`, i.e., the first method parameter, so it does not depend on the compiler retaining parameter names via `-parameters`. In real projects, if using `#documentId`, ensure Spring can discover parameter names or use `@P`.

Run command:

```bash
./gradlew test --tests "example.security.PermissionEvaluatorIntegrationTest"
```

On Windows use `gradlew.bat`; multi-project Gradle builds may need `:module-path:test`. With Spring Boot 3.x and the dependencies above, **expected result: 7 tests PASS**. These are JUnit assertions, not a `main` program with fixed stdout. Because the example uses an in-memory store, this result cannot be used as evidence of JDBC/JPA commit/rollback behavior.

### 4.2. What Do the Tests Prove?

| Test | Policy | Key Assertion |
| --- | --- | --- |
| `ownerCanReadEditAndShare` | Owner has all three permissions | Title changes, recipient granted read, exactly 2 events |
| `editorCanReadAndEditButCannotShare` | Editor cannot share | Edit succeeds, share denied; ACL unchanged; exactly 1 event |
| `readerCannotEditOrShareAndHasNoSideEffects` | Reader has read only | Edit/share denied; title, ACL, and notification unchanged |
| `unrelatedUserCannotReadEditOrShare` | Stranger in same tenant | Cannot read/edit/share, creates no side effects |
| `tenantBoundaryOverridesEvenOwnerAndAcl` | Tenant gate overrides | Same username/ACL in wrong tenant still denied |
| `unknownResourcesAndUnsupportedPermissionsDeny` | Fail closed | Unknown ID/type/action, null target object all false |
| `objectOverloadUsesCanonicalStoreNotForgedFields` | Defends against forged objects | Self-declared owner/tenant fails canonical store lookup |

For denied cases, tests must verify **after the call** that data, ACLs, and outbound effects remain unchanged. Checking only the exception is insufficient if authorization was placed after the mutation.

## 5. Turning the Sample into a Production Design

### 5.1. Separating Layers by Responsibility

```text
HTTP Controller
     │
     ▼
DocumentService  ← @PreAuthorize(hasPermission(...))
     │                          │
     │                          ▼
     │               DocumentPermissionEvaluator
     │                          │
     ▼                          ▼
DocumentRepository        ACL/PolicyRepository
     │                          │
     └──────── Database ────────┘
     │
     └── outbox/notification after valid operation
```

The evaluator **only checks permissions**; avoid sending emails, modifying ACLs, or calling side-effecting network APIs just to evaluate policy. If permission logic grows complex, have the evaluator call a separate unit-tested `DocumentPolicy`. If the policy reads repositories repeatedly, consider optimized queries, caches with invalidation, and failing closed when information is missing.

### 5.2. Granting Share Must Verify the Recipient

`shareRead(documentId, recipient)` in the demo assumes the recipient is a valid user in the same tenant. Real code should:

1. Check that the actor has `share` on the document.
2. Check that the recipient exists, belongs to the right tenant, is not locked, and is allowed to receive the document.
3. Determine the exact grant: `READ` or `EDIT`, expiration, and whether resharing is allowed.
4. Persist the ACL in an appropriate transaction; handle duplicate shares idempotently.
5. Send notifications through a post-commit guarantee mechanism (e.g., outbox).
6. Test revocation and when permissions take effect, including stale caches.

Never assume `edit` permission implies `share` permission. If the business wants editors to share as well, deliberately update the policy matrix and add tests.

### 5.3. Preventing TOCTOU When Permissions Change Concurrently

The evaluator checks data at time A; the `edit` body executes at time B. In between, the document could change owner/tenant/status or the user could have permissions revoked. That is a time-of-check to time-of-use risk.

With a database, one way to reduce races is **embedding tenant and ACL conditions directly into the UPDATE statement**; the example below is illustrative SQL and must be adapted to your schema/dialect:

```sql
UPDATE document
   SET title = :new_title
 WHERE id = :id
   AND tenant_id = :trusted_tenant
   AND (
       owner_id = :actor_id
       OR EXISTS (
           SELECT 1
             FROM document_acl a
            WHERE a.document_id = document.id
              AND a.principal_id = :actor_id
              AND a.permission = 'EDIT'
       )
   );
```

Check **affected rows**: 1 row is valid; 0 rows means no row satisfied the policy at mutation time. For complex flows, use locking/isolation/optimistic versioning and transactions. Never just run a `SELECT` to check ownership and then fire `UPDATE document SET ... WHERE id = ?` with no tenant/policy predicate.

For lists/pagination over many documents, prefer scoping tenant/ACL **directly in the query** rather than loading the entire table and applying `@PostFilter`: performance is better, pages/counts are accurate, and there is less risk of loading another tenant's data into memory/logs.

### 5.4. Transactions and Notifications

A `@PreAuthorize` denial before the body avoids side effects from that service. Yet once allowed, if the write fails partway, `@Transactional` manages only its transactional resources. Emails, HTTP calls, queue messages, or in-memory changes may already have happened even if the DB rolls back. When business rules require post-commit notifications, use `@TransactionalEventListener(phase = AFTER_COMMIT)` or a transactional outbox + retry/idempotency.

When testing service commit/rollback, use a real DB or appropriate Testcontainers/H2 and assert **after the service returns/throws**; avoid annotating the test method itself with `@Transactional`, because a test-managed transaction can mask boundary bugs and auto-roll back at test end.

### 5.5. Caching, Revocation, and Auditing

- **Permission caching:** keys need actor ID, tenant, document ID, action, and ACL/policy version; share/owner/revoke changes must invalidate. Never cache allow decisions indefinitely.
- **Revocation:** an editor removed from `editors` might still have read access if also listed in `readers`. Policies must define how grants and denies combine.
- **Auditing:** log actor, tenant, resource, action, and decision per log retention policy; avoid placing sensitive documents or tokens into DENY logs.
- **DB row-level security:** can add defense-in-depth, not replace action-level authorization (`read`/`edit`/`share`).
- **Exception policy:** storage errors must never turn into “permit.” Applications may return an appropriate system error, yet must never proceed with mutation without a trusted authorization decision.

## 6. Common Mistakes

| Symptom | Cause | How to Verify |
| --- | --- | --- |
| `hasPermission(...)` always false | Evaluator not wired into `MethodSecurityExpressionHandler`; wrong `targetType`/permission | Register handler as `@Bean static`, test a valid owner |
| Method runs despite deny | Missing `@EnableMethodSecurity` or proxy bypassed via `this`/`new` | Invoke injected bean from another bean; measure side effects |
| Reader can edit | Used `read` condition instead of `edit`, or overly broad OR | Separate matrix for read/edit/share |
| Editor can grant share | Treated edit as implying share | Test `share` rule for owner-only |
| Cross-tenant user can read | Matched owner/ACL only, untrusted tenant from request | Tenant gate from authenticated principal, DB scope |
| Client forges a document to get grant | Trusted owner/tenant fields on object overload | Look up canonical document by ID |
| Null/unknown ID throws unhandled error | Missing deny branch before calling store | `Optional` and fail closed |
| Denied yet notification sent | Checked after body, `@PostAuthorize`, or side effects in evaluator | `@PreAuthorize`, side-effect assertions |
| Still readable after revoke | Stale cache/token/permissions | ACL version and invalidation/revoke tests |
| Permitted at check time, unauthorized at update | Race/TOCTOU | Conditional mutation, transactions/locking |

**How does PermissionEvaluator differ from the ACL module?** `PermissionEvaluator` is just the extension interface for `hasPermission`. It does not create ACL tables or compute inheritance automatically. Spring Security ACL provides `AclPermissionEvaluator`, `AclService`, and SID/ACE/ACL tables, useful when persistent multi-level ACLs are needed. For smaller owner/editor/reader models, a custom domain evaluator is often easier to read and test. In Spring Security 6+, method authorization underneath is built on `AuthorizationManager`; `PermissionEvaluator` remains a valid SpEL hook. If policies grow complex, consider a bean authorizer or a custom `AuthorizationManager<MethodInvocation>`.

## 7. Acceptance Checklist

- [ ] `@EnableMethodSecurity` is enabled; `MethodSecurityExpressionHandler` bean configures `setPermissionEvaluator`.
- [ ] Both `PermissionEvaluator` overloads work; object overload does not trust self-declared owner/tenant.
- [ ] Read, edit, and share are separated per the agreed matrix, with no implicit permissions.
- [ ] Tenant comes from a trusted context and is checked before any ACL condition.
- [ ] Unknown permission/type/id, anonymous callers, and missing documents all fail closed.
- [ ] Methods are invoked through a Spring proxy, with denials occurring before mutations.
- [ ] Every DENY leaves data, ACLs, and notifications untouched.
- [ ] Share verifies recipient/tenant and grant type; revocation plan exists.
- [ ] With a real database, check row scoping, concurrency, and transactions/outbox.
- [ ] Tests cover owner/editor/reader/stranger/cross-tenant and HTTP paths as needed.

## Official References

- [Spring Security 6.5 – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html) – configuring `@EnableMethodSecurity`, `@PreAuthorize`, SpEL `hasPermission`, and expression handlers.
- [Spring Security – PermissionEvaluator Java API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/PermissionEvaluator.html) – the two `hasPermission` overloads.
- [Spring Security – Method Security Testing](https://docs.spring.io/spring-security/reference/servlet/test/method.html) – `@WithMockUser` and integration tests.
- [Spring Framework – AOP Proxying](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html) – self-invocation limitations.
- [Spring Security – ACL Support](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html) – persisted ACL alternative.
