# Business Policy Beans and Extracting Long Expressions from Annotations

> **Context:** Spring Security – authorization → Expressions and policies. This lesson focuses on encapsulating **business authorization rules** inside a dedicated Spring bean and invoking that bean from `@PreAuthorize`/`@PostAuthorize`. The main examples target synchronous methods using Spring AOP, Java 17+, and modern Spring Security.

## 1. Why shouldn't you cram the entire policy into the annotation?

Consider a document-reading feature. Users may view a document when **they own the document themselves**; or when the document is published and the user has the `DOC_PUBLIC_READ` authority. Non-existent documents must be denied. Later, the system will also add tenants, lock state, grant expiration, and delegated access.

Trying to stuff every condition into a `@PreAuthorize` string produces hard-to-audit code like:

~~~java
// Illustrates an expression gradually growing too long; not a standalone runnable example.
@PreAuthorize(
    "isAuthenticated() and " +
    "(@documentLookup.isOwner(#docId, authentication.name) or " +
    " (@documentLookup.isPublished(#docId) and hasAuthority('DOC_PUBLIC_READ'))) and " +
    "!@documentLookup.isLocked(#docId)"
)
public Document readDocument(long docId) {
    // ...
}
~~~

The issue is not SpEL's expressive power, but **where the policy lives**. Long expressions make the full rule hard for readers to grasp, invite missing parentheses or wrong `and`/`or` precedence, duplicate conditions across multiple services, hinder testing individual branches, obscure repeated queries for the same data, and complicate updates when business rules evolve.

A clearer structure:

~~~java
@PreAuthorize("@documentPolicy.canRead(authentication, #docId)")
public Document readDocument(@P("docId") long docId) {
    // ...
}
~~~

The annotation states only **the authorization intent**: whether the caller may read this document. The `documentPolicy` bean is responsible for determining **why** access is granted or denied. Enforcement must still go through Spring Method Security; moving code into a plain bean **does not automatically** protect a method if the annotation or proxy is missing.

### Four components and responsibility boundaries

| Component | Responsibility | Should not take on |
| --- | --- | --- |
| `@PreAuthorize` on the service | Places a gate before the action and passes context needed by the policy | Long business condition trees, repeated queries in SpEL |
| `DocumentPolicy` (`@Component`) | Evaluates caller, authorities, ownership, resource state, and returns a `boolean` decision | Mutating document state as a side effect of checking |
| `DocumentStore` / repository | Fetches data or minimal attributes required for the decision | Making permission decisions without knowing caller identity |
| `DocumentService` | Executes business logic once allowed; manages transactions and domain errors | Assuming only controllers call it and skipping service-level checks |

Diagram of a policy-guarded read call:

~~~mermaid
flowchart TD
    A[Controller or another service calls bean] --> B[Method Security Proxy]
    B --> C["@PreAuthorize calls documentPolicy.canRead"]
    C --> D[Policy reads Authentication and document metadata]
    D --> E{Rule allows?}
    E -- No --> F[AccessDeniedException]
    E -- Yes --> G[DocumentService.read]
    G --> H[Return Document]
~~~

`@PreAuthorize` evaluates **before the method body executes**. If the policy returns `false`, the method body will not run. If the policy throws an unexpected error (e.g., query failure), that error does not mean access is granted; never catch exceptions and return `true`.

## 2. How Spring Security finds and invokes a policy bean

Suppose you declare:

~~~java
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    public boolean canRead(/* ... */) {
        // ... 
        return false;
    }
}
~~~

When Method Security is active, SpEL inside `@PreAuthorize` understands the following syntax:

| Expression element | Meaning |
| --- | --- |
| `@documentPolicy` | Looks up a Spring bean named exactly `documentPolicy` in the application context |
| `.canRead(...)` | Calls the bean's public method; its return value determines allow/deny |
| `authentication` | The `Authentication` object in the call's security context |
| `#docId` | Method parameter resolved by Spring Security with name `docId` |
| `hasAuthority('DOC_PUBLIC_READ')` | Checks for a `GrantedAuthority` with that exact name |
| `hasRole('ADMIN')` | Under default config, checks authority `ROLE_ADMIN`; not identical to `hasAuthority('ADMIN')` |

The `@` prefix before the bean name is SpEL's bean-reference syntax; the `#` prefix before `docId` is variable-reference syntax. The two symbols are not interchangeable. Bean names are case-sensitive; `@DocumentPolicy` does not automatically point to a bean named `documentPolicy`.

If no name is passed to `@Component`, Spring derives a default name from the class, yet specifying an **explicit name** keeps annotations stable and easy to search in code. Another option is defining `@Bean(name = "documentPolicy")` in configuration if the object is factory-created.

`@EnableMethodSecurity` activates interceptors handling `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` (pre/post enabled by default). Merely adding the Spring Security dependency or configuring URL protection **does not automatically enable Method Security**.

## 3. Policy design: explicit decisions, deny by default

This lesson's simple example has three documents:

| ID | Owner | Published? | Read rule |
| --- | --- | --- | --- |
| 1 | `alice` | No | Only `alice` |
| 2 | `bob` | No | Only `bob` |
| 3 | `alice` | Yes | `alice` or an authenticated user with authority `DOC_PUBLIC_READ` |

This is an **illustrative rule**: "published" does not mean anonymous access is allowed. The system assumes non-owners still need the `DOC_PUBLIC_READ` authority to read a published document.

The policy must return `false` when:

- There is no valid authenticated user, or only an anonymous token is present.
- The document does not exist.
- The caller is not the owner and does not satisfy the published-document exception.
- A request crosses organization/tenant boundaries or targets a locked resource, if the system later adds those rules.

In practice, never trust `owner`, `tenantId`, or `role` self-declared by the client in a request as proof of authorization. Use verified identity/claims from `Authentication` and resource state from a trusted source. Never infer a caller's permissions solely from an ID they submitted.

A good policy has an action-oriented name (e.g., `canRead`, `canEdit`, `canApprove`) and a clear return contract. Avoid creating a generic `check(Object... args)` method for every domain rule if it erases type safety and makes rules hard to test.

## 4. Complete Spring Boot example: a policy bean called from a service

The files below assemble into a runnable example in a **Spring Boot Gradle project configured with the Spring Boot plugin, Java 17+, and JUnit 5**. Spring Boot manages compatible Spring Security versions through dependency management. Data lives in memory to illustrate the mechanism; a real repository can use JPA/JDBC with the same semantic interface.

### 4.1. Dependencies and configuration

In an existing Spring Boot project's `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

If the application needs HTTP REST, add the web starter too, though **testing Method Security at the service layer** requires neither controllers nor sample endpoints.

**`src/main/java/demo/authorization/DemoApplication.java`**

~~~java
package demo.authorization;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`@EnableMethodSecurity` is placed on the main class in this example so it is not forgotten. In larger multi-config projects, it can sit on a dedicated `@Configuration` class.

### 4.2. Model and document store

**`src/main/java/demo/authorization/Document.java`**

~~~java
package demo.authorization;

// Records are available since Java 16; this example targets Java 17+ as baseline.
public record Document(
        long id,
        String owner,
        String title,
        boolean published) {
}
~~~

**`src/main/java/demo/authorization/DocumentStore.java`**

~~~java
package demo.authorization;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentStore {
    private final Map<Long, Document> documents = Map.of(
        1L, new Document(1L, "alice", "Private draft", false),
        2L, new Document(2L, "bob", "Private memo", false),
        3L, new Document(3L, "alice", "Public guide", true)
    );

    public Optional<Document> findById(long id) {
        return Optional.ofNullable(documents.get(id));
    }
}
~~~

`Map.of` is immutable and used solely for **reads** in this example. In a real system, `DocumentStore` is typically an adapter to a repository/JPA; it must fetch data by ID from the database, never accepting an owner claimed by the caller.

### 4.3. Business policy bean

**`src/main/java/demo/authorization/DocumentPolicy.java`**

~~~java
package demo.authorization;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {
    private final DocumentStore store;

    public DocumentPolicy(DocumentStore store) {
        this.store = store;
    }

    public boolean canRead(Authentication authentication, long documentId) {
        if (!isRealUser(authentication)) {
            return false;
        }

        return store.findById(documentId)
                .map(document ->
                        document.owner().equals(authentication.getName())
                        || (document.published()
                            && hasAuthority(authentication, "DOC_PUBLIC_READ")))
                .orElse(false);
    }

    private boolean isRealUser(Authentication authentication) {
        return authentication != null
                && authentication.isAuthenticated()
                && !(authentication instanceof AnonymousAuthenticationToken);
    }

    private boolean hasAuthority(Authentication authentication, String required) {
        return authentication.getAuthorities().stream()
                .anyMatch(authority -> required.equals(authority.getAuthority()));
    }
}
~~~

**Decision breakdown:**

1. `isRealUser` rejects unauthenticated callers and anonymous tokens. Calling `isAuthenticated()` alone does not distinguish anonymous tokens in some setups; explicitly checking the token type makes behavior predictable.
2. `store.findById(documentId)` fetches the real document by ID; if absent, `orElse(false)` enforces deny-by-default.
3. `document.owner().equals(authentication.getName())` permits the owner. Real systems may compare an immutable user ID rather than a mutable username.
4. `document.published() && hasAuthority(...)` permits non-owners to read published documents, only when they hold the matching authority.
5. The method only **reads** and returns a `boolean`; it never deletes, sends notifications, grants roles, or alters the document while checking.

Java uses short-circuit evaluation: when the ownership branch is true, the authority branch does not execute. That does not make the expression unsafe; the two branches form an intentional `OR` rule inside valid input guards.

### 4.4. Service exposing the protected action

**`src/main/java/demo/authorization/DocumentService.java`**

~~~java
package demo.authorization;

import java.util.NoSuchElementException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentStore store;

    public DocumentService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize("@documentPolicy.canRead(authentication, #docId)")
    public Document read(@P("docId") long docId) {
        return store.findById(docId)
                .orElseThrow(() -> new NoSuchElementException("Document not found"));
    }
}
~~~

When invoking `documentService.read(1L)` through the Spring bean proxy, the sequence is:

1. The `@PreAuthorize` advisor retrieves `Authentication` and the `#docId` value from the invocation.
2. SpEL resolves the `documentPolicy` bean and calls `canRead(authentication, docId)`.
3. `true` → executes `read`'s body; `false` → blocks the call and throws `AccessDeniedException`.
4. The service still handles missing data in case state changes **after** the check (for instance, concurrent deletion).

Why use `@P("docId")`? Spring Security needs the argument name when evaluating `#docId`. Java parameter names can be discovered via the `-parameters` compiler flag, the `@P` annotation, or other name discoverers; placing `@P` here makes name binding explicit and avoids relying on project compiler flags.

Never call `new DocumentService(...)` when testing annotations: objects constructed via `new` are not wrapped by Spring's Method Security proxy. Nor should you call `this.read(...)` internally from another method in the same service expecting annotations to run; internal calls typically bypass the proxy.

### 4.5. Integration testing: right decisions and real enforcement

**`src/test/java/demo/authorization/DocumentServiceTest.java`**

~~~java
package demo.authorization;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(classes = DemoApplication.class)
class DocumentServiceTest {
    @Autowired
    private DocumentService service;

    @Test
    @WithMockUser(username = "alice")
    void ownerCanReadPrivateDocument() {
        assertEquals(1L, service.read(1L).id());
    }

    @Test
    @WithMockUser(username = "bob")
    void differentOwnerCannotReadPrivateDocument() {
        assertThrows(AccessDeniedException.class, () -> service.read(1L));
    }

    @Test
    @WithMockUser(username = "bob", authorities = "DOC_PUBLIC_READ")
    void authorityAllowsReadingPublishedDocument() {
        assertEquals(3L, service.read(3L).id());
    }

    @Test
    @WithMockUser(username = "bob")
    void publishedDocumentStillRequiresTheAuthorityForNonOwner() {
        assertThrows(AccessDeniedException.class, () -> service.read(3L));
    }

    @Test
    @WithMockUser(username = "alice")
    void unknownIdIsDeniedBeforeEnteringServiceBody() {
        assertThrows(AccessDeniedException.class, () -> service.read(999L));
    }

    @Test
    @WithAnonymousUser
    void anonymousUserCannotReadPublishedDocument() {
        assertThrows(AccessDeniedException.class, () -> service.read(3L));
    }
}
~~~

Each test covers a distinct path: the `alice` test verifies the **allow** path, the `bob` tests verify **private documents do not leak**, the published-document tests distinguish authority from ownership, the missing-ID test verifies **deny-by-default**, and the anonymous test checks authentication enforcement. Every test retrieves `DocumentService` from the Spring Context, testing both **proxy and policy**.

From the Gradle project directory, run:

~~~text
./gradlew test --tests demo.authorization.DocumentServiceTest
~~~

On Windows:

~~~text
gradlew.bat test --tests demo.authorization.DocumentServiceTest
~~~

No custom stdout is printed by the sample methods. When configured properly and all assertions pass, the test task completes successfully (Gradle typically prints `BUILD SUCCESSFUL`); never claim tests were run merely from reading the example.

### 4.6. Unit testing: exercising policy branches without Spring AOP

Although the policy is a bean, it is fundamentally a Java class with injected dependencies. You can therefore test **its logic directly** and catch branching mistakes faster.

**`src/test/java/demo/authorization/DocumentPolicyTest.java`**

~~~java
package demo.authorization;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DocumentPolicyTest {
    private final DocumentPolicy policy =
            new DocumentPolicy(new DocumentStore());

    @Test
    void ownerAndMissingDocument() {
        Authentication alice =
                new UsernamePasswordAuthenticationToken("alice", "unused", List.of());

        assertTrue(policy.canRead(alice, 1L));
        assertFalse(policy.canRead(alice, 2L));
        assertFalse(policy.canRead(alice, 999L));
    }

    @Test
    void publishedDocumentNeedsExplicitAuthorityForOtherUser() {
        Authentication bob = new UsernamePasswordAuthenticationToken(
                "bob", "unused", List.of());
        Authentication bobWithRead = new UsernamePasswordAuthenticationToken(
                "bob", "unused",
                List.of(new SimpleGrantedAuthority("DOC_PUBLIC_READ")));

        assertFalse(policy.canRead(bob, 3L));
        assertTrue(policy.canRead(bobWithRead, 3L));
        assertFalse(policy.canRead(bobWithRead, 1L));
    }

    @Test
    void nullAuthenticationIsDenied() {
        assertFalse(policy.canRead(null, 3L));
    }
}
~~~

Using the three-argument constructor of `UsernamePasswordAuthenticationToken` in unit tests creates an authenticated token suitable for exercising permission logic. Unit tests **do not replace** Spring proxy tests; if `@EnableMethodSecurity` is missing, `DocumentPolicy` unit tests still pass while annotations are silently ignored. Both layers of verification are mandatory.

Run both test classes together:

~~~text
./gradlew test --tests demo.authorization.DocumentPolicyTest --tests demo.authorization.DocumentServiceTest
~~~

## 5. Why pass `Authentication` and the ID into the policy?

There are several parameter design choices for a policy:

| Signature | Best suited when | Watch out for |
| --- | --- | --- |
| `canRead(Authentication auth, long id)` | Decision depends on identity and a document identified by ID | Policy may need a query; potential double read in precheck and service |
| `canRead(Authentication auth, Document doc)` | Service already holds a trusted-source object, or checking post-call | Never trust `Document` data supplied by a client |
| `canRead(Authentication auth, long id, String operation)` | Shared rule across multiple structured actions | Constrain allowed operations; avoid ad-hoc string comparisons everywhere |
| `decide(MethodSecurityExpressionOperations root)` | Need rich SpEL context or deep expression API integration | Couples tightly to Spring Security; avoid if explicit parameters suffice |

This lesson uses `canRead(Authentication, long)` because callers pass only the ID, while the policy reads truth from the store. It also keeps unit tests simple, requiring only an `Authentication` and `DocumentStore`.

**Do not write** `@PreAuthorize("@documentPolicy.canRead(#owner, #docId)")` if `#owner` is a caller-supplied argument purporting to confirm ownership. Callers can send any `owner`. Checks must bind to the identity in the Spring Security–verified `Authentication`.

With JWT/OIDC, `authentication.name` often comes from whichever claim is configured as the name, and is not always a stable owner identifier. If the policy needs a user ID or tenant ID, use a verified claim/account through a trusted token converter or resolver. Never rely on a mutable email or a URL `tenantId` as sole proof.

## 6. Multiple actions: splitting policies by business operation

When expanding to editing and approval, keep **specific action names** instead of duplicating complex SpEL strings across services:

~~~java
// Illustrates extended design, not part of the full runnable example in Section 4.
@Component("documentPolicy")
public class DocumentPolicy {
    public boolean canRead(Authentication auth, long docId) { /* ... */ return false; }
    public boolean canEdit(Authentication auth, long docId) { /* ... */ return false; }
    public boolean canApprove(Authentication auth, long docId) { /* ... */ return false; }
}
~~~

~~~java
// Illustrates signatures in another service.
@PreAuthorize("@documentPolicy.canEdit(authentication, #docId)")
public void edit(@P("docId") long docId, UpdateDocumentCommand command) {
    // Executes update only after authorization.
}

@PreAuthorize("@documentPolicy.canApprove(authentication, #docId)")
public void approve(@P("docId") long docId) {
    // Validates additional business conditions during the update.
}
~~~

These two snippets illustrate naming only. `UpdateDocumentCommand` and update logic are not implemented in Section 4's example; do not paste them in directly expecting a complete compiling program.

A clean split is:

- `canRead`: checks owner, published status, and read authority.
- `canEdit`: checks edit authority, owner, lock status, and organization scope.
- `canApprove`: checks approver role, prevents self-approval, and verifies workflow state.

When one policy spans multiple services, use a central bean with clear naming and dependencies. When a single short SpEL check like `hasAuthority('DOC_READ')` suffices, do not wrap it in an unnecessary bean. Move rules to a bean when **business logic** needs reuse, lookups, multiple combined conditions, or independent testing.

You can combine a coarse-grained authority gate with a fine-grained policy:

~~~java
// Illustrative only, differs from the policy in the runnable example in Section 4.
@PreAuthorize(
    "hasAuthority('DOC_READ') and @documentPolicy.canRead(authentication, #docId)")
public Document read(@P("docId") long docId) {
    // ...
}
~~~

In this example, `hasAuthority('DOC_READ')` is an **additional mandatory requirement**; it does not replace ownership checks. Do not copy this expression into Section 4's tests without granting `DOC_READ` to allowed users, as the new requirement would fail those tests.

## 7. Differences between pre-authorization and post-authorization

Two common annotation styles:

~~~java
@PreAuthorize("@documentPolicy.canRead(authentication, #docId)")
public Document read(@P("docId") long docId) {
    // Only runs after check permits.
    // ...
}
~~~

~~~java
// Illustrates a post-check variant; requires defining canReadObject and lookup.
@PostAuthorize("@documentPolicy.canReadObject(authentication, returnObject)")
public Document readThenCheck(long docId) {
    // Method body runs before policy inspects returnObject.
    // ...
}
~~~

**`@PreAuthorize`** fits when you must stop actions with side effects beforehand, such as deleting, editing, approving, transferring funds, or sending notifications. **`@PostAuthorize`** is used when you must inspect the actual return object (`returnObject`), such as when ownership can only be checked after loading data. However, because the method body has already run before the post-check, never use `@PostAuthorize` as the sole protection for write operations.

When a service already has to load data, post-checks can save one lookup compared to pre-checks. Evaluate that trade-off deliberately: never pick a post-check merely to save one query if it lets side effects happen before authorization runs.

`@PostFilter` and `@PreFilter` filter individual **elements** in collections. They do not fully replace a `canRead(...)` bean deciding single-resource access. For large or paginated lists, filter directly in the data query instead of loading everything and pruning in memory.

## 8. Critical rules in multi-tenant and mutable-data systems

### 8.1. Tenant boundaries must be checked before other permission exceptions

Suppose documents carry a `tenantId`. A dangerous expression is:

~~~java
// DO NOT use if ADMINs may only administer within their own tenant:
boolean allowed = hasAdminAuthority || (sameTenant && isOwner);
~~~

Here an admin can bypass `sameTenant`. The right structure when admins are tenant-scoped is:

~~~java
// Plain Java boolean illustration, not a complete file.
boolean allowed = sameTenant && (hasAdminAuthority || isOwner);
~~~

`sameTenant` must be computed from the document's tenant and the user's verified/authorized tenant; never let an arbitrary client-supplied tenant create a false match.

If the application supports cross-tenant administration, model that privilege in an explicit separate branch with its own conditions and tests; never implicitly give every `ROLE_ADMIN` access across all tenants.

### 8.2. Policy lookup followed by service lookup can hit TOCTOU

In Section 4's example, `DocumentPolicy` reads the document to check permissions and `DocumentService` reads it again to return the result. In-memory data is immutable here so no issue arises, yet with a real database you can hit:

~~~text
T1: Policy sees document 1 belongs to alice -> allow
T2: Another transaction changes owner/tenant of document 1
T3: Service re-reads modified document 1 -> result is no longer valid
~~~

This is the gap between **time-of-check** and **time-of-use** (TOCTOU). Depending on business needs, embed permission predicates directly in the query/update statement, use appropriate transactions, version checks, or locking. Never treat `@PreAuthorize` as a guarantee that database state stays frozen between two statements.

For writes requiring strong consistency—e.g., updating only if owner/tenant still match—use conditional updates:

~~~sql
-- Illustrates SQL idea; exact syntax depends on database and schema.
UPDATE documents
SET title = :new_title
WHERE id = :id
  AND owner_id = :authenticated_user_id
  AND tenant_id = :trusted_tenant_id
  AND locked = false;
~~~

Checking the affected row count and handling 0 rows is part of the business contract. The annotation guards **the invocation**, whereas the conditional database statement guards **the real state at write time**.

### 8.3. Performance and transactions

If `canRead` queries the database on every read, calling it in a loop over hundreds of documents triggers N+1 queries. When returning lists, let the repository filter by user/tenant directly in the query, or perform batched checks with minimal data. Avoid hitting the repository repeatedly just because multiple conditions sit in SpEL.

On `@Transactional` methods, advisor ordering can cause pre-authorization to execute before the business transaction opens. Do not rely on lazy JPA relationships inside a policy assuming the method body's transaction is already active. If a policy needs queries, design dedicated queries or an appropriate read transaction and verify against your real configuration. Slapping `@Transactional` indiscriminately on every policy can introduce unexpected overhead and transaction semantics.

### 8.4. Do not leak information through error responses

If both non-existent documents and unauthorized documents yield a denial, outsiders learn less about resource IDs. However, `AccessDeniedException` is typically translated to HTTP 403 at the web layer, whereas `NoSuchElementException` usually needs explicit mapping to 404. Whether the app returns 403 or 404 for unauthorized resources must align with anti-enumeration policy, API contracts, and error design; a policy bean alone does not guarantee HTTP status codes.

Avoid logging tokens, private details, or full document objects on the authorization path. For auditing, record resource ID, actor ID, action, outcome, and safe reason codes; compute decisions solely from trusted state.

## 9. What stays in the annotation vs. what moves into a bean?

| Case | Appropriate choice |
| --- | --- |
| Method needs only one fixed authority | `@PreAuthorize("hasAuthority('DOC_READ')")` |
| Rules depend on owner, status, tenant, delegated access | `@PreAuthorize("@documentPolicy.canRead(authentication, #id)")` |
| Same rules across many methods with specific action names | A reusable policy bean with `canRead`, `canEdit`, ... |
| Want domain-readable annotation names across the codebase | Meta-annotation, e.g., `@CanReadDocument`, backed by `@PreAuthorize`; consider if reused widely |
| Want unified authorization across requests, methods, schedulers, or messages | Design a shared `AuthorizationManager` or core policy; avoid duplicating logic |
| Very large or paginated result sets | Enforce permission predicates in repository/query; do not post-filter everything |
| Single short check with no business rules | Keep short inline SpEL directly; avoid over-abstraction |

A **business policy bean** is usually the sweet spot: it leverages existing Method Security, moves logic into typed Java, uses dependency injection, and enables direct unit tests. `AuthorizationManager` fits when deeper integration with Spring Security's authorization infrastructure is needed. You do not need a custom expression handler just to call a Java method.

## 10. Common implementation pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| `@PreAuthorize` blocks nothing | Missing `@EnableMethodSecurity` or called bypassing proxy | Enable Method Security, invoke Spring-managed bean, add non-owner test |
| SpEL reports bean not found | Wrong `@documentPolicy` name, missing `@Component`, or outside component scan | Match bean name and component scanning config |
| SpEL cannot read `#docId` | Missing parameter name metadata, typo, interface method lacking names | Use `@P("docId")`, enable `-parameters`, test with context |
| Policy unit tests pass yet service allows unauthorized access | Tested Java method directly without running annotation/proxy | Add `@SpringBootTest` + `@WithMockUser` integration tests |
| User gets access by passing `owner` or `tenantId` | Trusting unverified arguments | Read identity from `Authentication`, resource from trusted repository |
| Non-existent document causes 500 or leaks info | Unhandled `Optional.empty()` or unintended state differentiation | Deny by default; keep 403/404 API semantics consistent |
| Data mutated even though ultimately denied | Post-check used after method body already ran | Gate with `@PreAuthorize`; enforce DB invariants on write |
| Slow due to repeated queries | Expression, policy, and service each re-read the same data | Fetch minimal projections, conditional queries, consolidate checks, profile |
| Policy throws exception and unexpectedly allows | Catching all exceptions and returning `true` as "fallback" | Fail closed; log technically without turning errors into grants |
| Lazy JPA check fails outside transaction | Advisor runs before business transaction; data unloaded | Run dedicated policy query, configure transactions explicitly, integration test |

### Parameter names, permissions, and boolean logic

`hasRole('ADMIN')` is easily confused with `hasAuthority('ADMIN')`. Under default prefixes, `hasRole('ADMIN')` looks for `ROLE_ADMIN`, while `hasAuthority('ADMIN')` looks only for `ADMIN`. Never write overly broad `OR` clauses if admins must still respect tenant or document state.

SpEL supports `and`/`or`, yet forms like `isAuthenticated() and hasRole('ADMIN') or ...` can open unintended access when parentheses are missing. Moving complex expressions into Java `if` statements and clearly named methods helps reviewers verify evaluation order. Test edge cases too: authenticated admin in wrong tenant, locked document, deactivated owner, or missing authority.

## 11. Testing strategy and review checklist

| Scenario group | Expected outcome | Test type |
| --- | --- | --- |
| Owner, private document | Allow | Policy unit + Method Security integration |
| Non-owner, private document | Deny | Policy unit + Method Security integration |
| Non-owner, published document, with authority | Allow | Unit + integration |
| Non-owner, published document, missing authority | Deny | Unit + integration |
| Anonymous, missing principal, non-existent ID | Deny | Appropriate unit + integration |
| Different tenant, former-tenant admin | Deny unless cross-tenant explicitly allowed | Unit + DB tenant integration |
| Concurrent owner/state change during write | No unauthorized write persisted | Database/transaction integration |
| Call via Spring proxy vs. internal same-bean call | Verify gate executes at right boundary | Integration; refactor design if self-invoking |
| Spring Security upgrade | Authorization behavior unchanged | Re-run regression tests on new dependency |

**Testing approach:** test policy logic by instantiating the Java class with test doubles/simple stores, then test **actual enforcement** through the Spring bean. Unit tests will not catch a missing `@EnableMethodSecurity`; integration tests do. Authorization tests must cover both allowed and denied paths; testing only the happy path never proves unauthorized access is blocked.

When reviewing a new policy, ask yourself:

1. Which resource is protected, and which actions are permitted?
2. Which trusted source identifies the caller? Could IDs or tenants be spoofed?
3. What happens if the resource is missing, permission is absent, or data lookup fails?
4. Is the annotation on a bean/method actually intercepted by a proxy?
5. Do policy data reads cause repeated queries, lazy-loading failures, or race conditions?
6. Are other users, anonymous callers, non-existent records, other tenants, and elevated roles tested?
7. Which logic can move from SpEL into a clearly named Java method for maintainability?

## 12. Hands-on exercises

**Exercise 1 – Add edit permission.** Add `canEdit(Authentication auth, long docId)` requiring the caller to be the owner **and** hold `DOC_EDIT`, with the document unlocked. Add `@PreAuthorize("@documentPolicy.canEdit(authentication, #docId)")` to an update method. Write tests verifying that an owner lacking `DOC_EDIT` is denied, and a non-owner holding `DOC_EDIT` is also denied.

**Exercise 2 – Tenant-safe policy.** Extend `Document` with `tenantId` and add a trusted tenant resolver for `Authentication`. An admin of tenant A must not read documents of tenant B. Write a test where the same username exists in both tenants.

**Exercise 3 – Extract a long expression.** Find an annotation with multiple repository-backed conditions. Build its truth table, move the policy into a bean with clear action methods, keep the annotation short, test every branch, and compare query counts before and after.

**Exercise 4 – Self-invocation.** Create two methods in the same `@Service`, with the first calling `this.read(...)` annotated with `@PreAuthorize`. Prove via an integration test that internal calls bypass the proxy, and redesign so the call goes through an appropriate service bean. Do not use self-injection as a default fix for an architectural issue.

**Completion criteria:** learners distinguish simple annotation checks from business rules in a policy bean; use `@bean`, `authentication`, and `#param` properly; enforce real blocking through the Spring proxy; write tests for both allow and deny cases; and recognize tenant, TOCTOU, and repeated-query risks.

## References

- Spring Security, **Method Security** – `@EnableMethodSecurity`, `@PreAuthorize`, Spring AOP proxies, parameter names, and calling custom beans from SpEL: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security, **Testing Method Security** – `@WithMockUser`, `@WithAnonymousUser`, testing through Spring Context: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security, **Authorization Architecture** – distinguishing authorities from authorization decisions: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Framework, **SpEL Bean References** – `@beanName` syntax: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/bean-references.html
