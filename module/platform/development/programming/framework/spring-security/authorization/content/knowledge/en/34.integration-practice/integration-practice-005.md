# Comparing Pre-Checks, Post-Checks, and Collection Filtering

> **Scope:** Spring Security Method Security at the service layer (Servlet or synchronous bean calls), Java 17+, Spring Boot 3.x/Spring Security 6.x. This practice compares **checking permissions before execution** (`@PreAuthorize`), **checking permissions after obtaining the result** (`@PostAuthorize`), and **filtering individual elements** before/after invocation (`@PreFilter`, `@PostFilter`). The goal is choosing the right tool for the business case, without confusing “denying the whole call” with “removing some elements.”

## 1. How Do the Four Protection Mechanisms Differ?

When `@EnableMethodSecurity` is enabled, Spring Security creates interceptors on **Spring-managed beans**. These annotations control method invocations or the data passing through them:

| Mechanism | Timing | What Is Checked | When Condition Fails | Typical Purpose |
| --- | --- | --- | --- | --- |
| `@PreAuthorize` | **Before** method body | Principal, authorities, and input parameters | Denies **the entire call**, method body does not run | Block write, archive, delete, approve upfront |
| `@PostAuthorize` | **After** method body returns result | Principal and `returnObject` | Denies **the entire result**; method body **already ran** | Check ownership when the object must be read to know its owner |
| `@PreFilter` | **Before** method body processes parameter | Each `filterObject` of the input collection | Drops non-matching elements; method still runs with remaining subset, possibly empty | Batch processing per permitted resource |
| `@PostFilter` | **After** method body creates result collection | Each `filterObject` of the returned collection | Returns only matching elements to caller; may return an empty collection | Filter result lists for the right principal |

**Two independent axes** determine usage:

1. **When to evaluate?** `Pre` before the method body; `Post` after the method body.
2. **What to evaluate?** `Authorize` decides **the entire call/result**, whereas `Filter` decides **individual elements**.

`@PreAuthorize` and `@PreFilter` are not equivalent: a batch write operation may need to *reject the whole batch* if it contains an unauthorized document, whereas a bulk import designed to allow skipping unauthorized documents can use filtering. *Silently* dropping elements in a business flow that expects all-or-nothing semantics can cause data loss or unexpected partial successes.

`@PostAuthorize` and `@PostFilter` also differ: given data `A1, B1, A2`, `@PostAuthorize` checking a single `returnObject` like `B1` throws an exception and **returns no object**; `@PostFilter` on a list returns `A1, A2` to Alice. Do not treat `@PostFilter` as a way to automatically produce HTTP 403.

### Execution Flow

```text
Caller (alice's SecurityContext)
   |
   v
Spring AOP / method-security proxy
   |
   +--> @PreFilter: drop non-matching elements from input
   +--> @PreAuthorize: decide whether method may run?
   |      No -> AccessDeniedException (method does not run)
   v
Service method body: read DB / process batch / build result
   |
   +--> @PostAuthorize: decide whether entire result may be returned?
   |      No -> AccessDeniedException (method already ran)
   +--> @PostFilter: drop non-matching elements from output
   v
Caller receives protected result
```

This diagram is a way of **categorizing phases**, not an absolute ordering guarantee when combining multiple annotations across versions/configurations. In Spring Security, advisors have their own precedence; when combining annotations on the same method, verify the actual order and write tests matching the final contract. Avoid placing side effects inside authorization expressions.

## 2. Practice Context: One Set of Documents, Multiple Decisions

Suppose the service has three documents, retrieved from **server-managed** data:

| ID | Owner | Alice Can View/Filter? | Bob Can View/Filter? |
| --- | --- | --- | --- |
| `A1` | `alice` | Yes | No |
| `B1` | `bob` | No | Yes |
| `A2` | `alice` | Yes | No |

Four business operations in this lesson:

- `archive(id)` requires authority `document:archive` **and** ID owned by the current principal. Must block before state mutation → `@PreAuthorize`.
- `findOne(id)` must read the document to know its owner. Can use `@PostAuthorize` checking `returnObject.owner`, provided the method body is **read-only without side effects**.
- `acceptedIds(documents)` receives a *server-verified* batch, proactively dropping elements not owned by the caller before the method body receives them → `@PreFilter`.
- `listAll()` returns mixed data and should expose only the caller's own elements → `@PostFilter`.

Expected outcomes:

| User and Invocation | Observed Result | Did Method Body Run? |
| --- | --- | --- |
| Alice with authority, `archive("A1")` | `"archived:A1"` | Yes |
| Alice with authority, `archive("B1")` | `AccessDeniedException` | No |
| Alice lacking authority, `archive("A1")` | `AccessDeniedException` | No |
| Alice, `findOne("A1")` | Document `A1` | Yes |
| Alice, `findOne("B1")` | `AccessDeniedException` | **Yes**: read first, then blocked on return |
| Alice, `acceptedIds([A1,B1,A2])` | `[A1,A2]` | Yes, saw only A1/A2 |
| Alice, `listAll()` | `[A1,A2]` | Yes, built original list including B1 |
| Bob, `listAll()` | `[B1]` | Yes |
| Charlie, `listAll()` | `[]` | Yes, returned empty list |

**Ownership safety:** `@PreAuthorize` should verify owner against **trusted data from repository/ACL/PDP** using the resource ID; never trust an `owner` field sent by the client during updates/deletes. With `@PreFilter`, if the input collection contains client-constructed objects, `filterObject.owner` is likewise insufficient against spoofing; resolve/verify objects from a server source before processing.

## 3. Runnable Spring Test Example with Java 17

The example uses a minimal Spring ApplicationContext test: no web server needs to start. In a Spring Boot 3.x project with Gradle Wrapper and BOM/versions from the plugin, include these dependencies (if not already present):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**The entire test example fits in a single file** `src/test/java/com/example/security/AuthorizationComparisonTest.java`. `@SpringJUnitConfig` initializes the context, `@EnableMethodSecurity` activates interceptors; `@Autowired` injects the service via a real proxy; `@WithMockUser` supplies the SecurityContext per test case.

```java
package com.example.security;

import java.util.ArrayList;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(AuthorizationComparisonTest.Config.class)
class AuthorizationComparisonTest {

    @Autowired DocumentService service;

    @BeforeEach
    void resetCounters() {
        service.reset();
    }

    private static List<Document> mixedInput() {
        // Mutable ArrayList: @PreFilter can remove elements.
        return new ArrayList<>(List.of(
            new Document("A1", "alice"),
            new Document("B1", "bob"),
            new Document("A2", "alice")
        ));
    }

    private static List<String> ids(List<Document> documents) {
        return documents.stream().map(Document::getId).toList();
    }

    // Group A: @PreAuthorize protects the entire write operation.
    @Test
    @WithMockUser(username = "alice", authorities = "document:archive")
    void preAuthorizeAllowsValidAuthorityAndServerOwnership() {
        assertEquals("archived:A1", service.archive("A1"));
        assertEquals(1, service.archiveRuns.get());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "document:archive")
    void preAuthorizeDeniesForeignOwnershipBeforeMethodBody() {
        assertThrows(AccessDeniedException.class,
            () -> service.archive("B1"));
        assertEquals(0, service.archiveRuns.get());
    }

    @Test
    @WithMockUser(username = "alice")
    void preAuthorizeDeniesMissingAuthorityEvenForOwnDocument() {
        assertThrows(AccessDeniedException.class,
            () -> service.archive("A1"));
        assertEquals(0, service.archiveRuns.get());
    }

    // Group B: @PostAuthorize inspects returnObject after reading.
    @Test
    @WithMockUser(username = "alice")
    void postAuthorizeReturnsOwnedDocument() {
        assertEquals("A1", service.findOne("A1").getId());
        assertEquals(1, service.findRuns.get());
    }

    @Test
    @WithMockUser(username = "alice")
    void postAuthorizeRejectsForeignResultButBodyAlreadyRan() {
        assertThrows(AccessDeniedException.class,
            () -> service.findOne("B1"));
        assertEquals(1, service.findRuns.get());
    }

    // Group C: @PreFilter alters the input collection seen by the method.
    @Test
    @WithMockUser(username = "alice")
    void preFilterRemovesForeignElementBeforeBody() {
        assertEquals(List.of("A1", "A2"),
            service.acceptedIds(mixedInput()));
        assertEquals(1, service.acceptRuns.get());
    }

    @Test
    @WithMockUser(username = "alice")
    void preFilterCanPassAnEmptyBatchWithoutDenyingCall() {
        List<Document> onlyBob = new ArrayList<>(List.of(
            new Document("B1", "bob")));
        assertEquals(List.of(), service.acceptedIds(onlyBob));
        assertEquals(1, service.acceptRuns.get());
    }

    @Test
    @WithMockUser(username = "bob")
    void preFilterDependsOnAuthenticatedPrincipal() {
        assertEquals(List.of("B1"),
            service.acceptedIds(mixedInput()));
    }

    // Group D: @PostFilter returns the matching subset to the caller.
    @Test
    @WithMockUser(username = "alice")
    void postFilterKeepsOnlyAliceDocuments() {
        assertEquals(List.of("A1", "A2"),
            ids(service.listAll()));
        assertEquals(1, service.listRuns.get());
    }

    @Test
    @WithMockUser(username = "bob")
    void postFilterKeepsOnlyBobDocuments() {
        assertEquals(List.of("B1"), ids(service.listAll()));
    }

    @Test
    @WithMockUser(username = "charlie")
    void postFilterReturnsEmptyListWhenNoElementMatches() {
        assertEquals(List.of(), ids(service.listAll()));
        assertEquals(1, service.listRuns.get());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    static class Config {
        @Bean
        OwnershipPolicy ownership() {
            return new OwnershipPolicy();
        }

        @Bean
        DocumentService documentService() {
            return new DocumentService();
        }
    }

    public static final class Document {
        private final String id;
        private final String owner;

        public Document(String id, String owner) {
            this.id = id;
            this.owner = owner;
        }

        public String getId() {
            return id;
        }

        public String getOwner() {
            return owner;
        }
    }

    // Simulates server-side lookup, NOT taking owner declared by the request.
    public static class OwnershipPolicy {
        public boolean ownedBy(String id, String username) {
            return DocumentService.STORED.stream().anyMatch(
                d -> d.getId().equals(id)
                  && d.getOwner().equals(username));
        }
    }

    public static class DocumentService {
        static final List<Document> STORED = List.of(
            new Document("A1", "alice"),
            new Document("B1", "bob"),
            new Document("A2", "alice")
        );

        final AtomicInteger archiveRuns = new AtomicInteger();
        final AtomicInteger findRuns = new AtomicInteger();
        final AtomicInteger acceptRuns = new AtomicInteger();
        final AtomicInteger listRuns = new AtomicInteger();

        public void reset() {
            archiveRuns.set(0);
            findRuns.set(0);
            acceptRuns.set(0);
            listRuns.set(0);
        }

        @PreAuthorize(
            "hasAuthority('document:archive') " +
            "and @ownership.ownedBy(#p0, authentication.name)")
        public String archive(String id) {
            archiveRuns.incrementAndGet();
            // Simulates side effect; the example does not write to a database.
            return "archived:" + id;
        }

        @PostAuthorize("returnObject.owner == authentication.name")
        public Document findOne(String id) {
            findRuns.incrementAndGet();
            return STORED.stream()
                .filter(d -> d.getId().equals(id))
                .findFirst()
                .orElseThrow(() -> new NoSuchElementException(id));
        }

        @PreFilter("filterObject.owner == authentication.name")
        public List<String> acceptedIds(List<Document> documents) {
            acceptRuns.incrementAndGet();
            // Method sees only the documents remaining after @PreFilter.
            return documents.stream().map(Document::getId).toList();
        }

        @PostFilter("filterObject.owner == authentication.name")
        public List<Document> listAll() {
            listRuns.incrementAndGet();
            // Intentionally includes both alice and bob documents to test filtering.
            return new ArrayList<>(STORED);
        }
    }
}
```

Use the Gradle Wrapper at the root of a configured Spring Boot project:

```bash
./gradlew test --tests "com.example.security.AuthorizationComparisonTest"
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.security.AuthorizationComparisonTest"
```

**Expected from source code:** **11 JUnit 5 tests PASS**, per the stated assertions and fixtures. Tests do not print fixed stdout; actual Gradle output depends on reporter configuration. This is an **expected outcome**, not a claim that the tests were run in an external environment.

### Why Are These Tests Meaningful?

- `archiveRuns == 0` when `@PreAuthorize` denies proves **the method body did not execute**. At the same time, the test verifies both authority and ownership from server data.
- `findRuns == 1` when `@PostAuthorize` denies proves **the method body already retrieved the object** before the caller received `AccessDeniedException`. Therefore, avoid using `@PostAuthorize` alone for operations with side effects.
- `acceptedIds(mixedInput())` returns IDs **directly inside the method body**, proving the input was filtered beforehand; if the annotation were inactive, `B1` would appear and the test would fail.
- `listAll()` always builds all three documents, yet caller Alice receives only `A1,A2`, Bob receives only `B1`, and Charlie receives `[]`: this checks **output contents**, not just `size()`.
- All calls use an `@Autowired` bean with `@EnableMethodSecurity`; creating `new DocumentService()` manually or calling `this.someSecuredMethod()` within the same bean can bypass the Spring AOP proxy and invalidate conclusions.

**Intentional limitation:** `STORED`, `archiveRuns`, and `findRuns` are internal fixtures; the test suite illustrates semantics and interception. In production, replace the in-memory lookup with a repository enforcing ownership/tenant guards and test database behavior, events, HTTP statuses, and transactional semantics.

## 4. Which Approach Should You Choose for Each Business Case?

### 4.1. Writing Data: Check Permissions Beforehand

If the action mutates state, emits events, or calls external APIs, prefer checking permissions **before** causing effects. With `archive(id)`, `@PreAuthorize` blocks immediately if the caller lacks the authority or does not own the ID.

If you use `@PostAuthorize` on a method that already ran `repository.save(...)`, an authorization failure **after saving** does not automatically guarantee rollback, especially if external systems were called or events emitted outside the transaction. Some transactions may roll back when an exception propagates across the right boundary, but never rely on that instead of a pre-write guard.

In the example, the policy reads owner from `DocumentService.STORED`; in a real system, authorization checks must rely on verified IDs and owner/tenant at the repository or PDP, not client-modifiable attributes. Also guard against **TOCTOU** (owner/status changing in another transaction after the check): use transactions, row locks, or conditional updates depending on business requirements.

### 4.2. Returning a Single Object: Post-Check If Result Attributes Are Needed

A `findOne(id)` call may need to load the object to know its owner. `@PostAuthorize("returnObject.owner == authentication.name")` protects the object **before the caller receives it**, making it especially suitable for read services. For null objects, `returnObject.owner` can fail; establish null-safety/`Optional` conventions or have the service intentionally throw not-found. In the example, missing IDs throw `NoSuchElementException`; the example **does not map** that exception to HTTP 404.

`@PostAuthorize` prevents returning unauthorized objects yet **does not prevent the method from running** and is not optimal for large queries. Whenever you can push `WHERE owner_id = :principal` down into the repository and enforce tenant isolation early, do so at the data layer; keep the annotation as defense-in-depth.

### 4.3. Batch Input: Use `@PreFilter` When Dropping Elements Fits the Contract

`@PreFilter` evaluates each `filterObject` before the method receives the data. Given `[A1, B1, A2]` for Alice, the method only processes `[A1, A2]`. If every element is filtered out, the method can still receive an empty list: **this is not an AccessDeniedException by default**.

When multiple parameters can be filtered, specify `filterTarget` explicitly:

```java
@PreFilter(
    value = "filterObject.owner == authentication.name",
    filterTarget = "documents")
public void submitBatch(String batchId, List<Document> documents) {
    // Illustrative snippet inside a service, not a standalone class.
}
```

To resolve the parameter by the name `documents`, compile Java with `-parameters` (or the corresponding naming mechanism supported by your framework version). Check collection types carefully; for lists in this lesson, use `new ArrayList<>(...)` because filtering may need to remove elements. Passing immutable `List.of(...)` directly can fail depending on how Spring applies the filter. `Map` uses `filterObject.value.owner` because elements are entries. Spring Security also supports arrays and streams; streams must remain open and be consumed only once.

Never use `@PreFilter` as a shortcut for an all-or-nothing batch write: if policy requires rejecting the entire batch when one ID is invalid, validate the whole batch before starting the transaction or return an error. If the business contract allows processing the valid subset, the response should clearly report what was processed, what was skipped, and why, with details matching security policy.

### 4.4. Returning Lists: Use `@PostFilter` When Element-by-Element Filtering Is Required

`@PostFilter("filterObject.owner == authentication.name")` runs on the result collection before the caller receives it. Test different principals against the same fixture to ensure the list leaks no documents. For `Map<String, Document>`, access `filterObject.value.owner`; assert both keys and IDs/owners rather than only `size()`.

**Post-query** filtering carries performance and correctness risks: the service might load thousands of records only to discard most of them; if paginated at the DB level, a 20-record page might shrink to 2 permitted records while `totalElements`/`hasNext` were computed on the unfiltered set. For large datasets, filter by ACL/owner/tenant **directly in the query**, keeping counts and pagination consistent; use method security as an extra guard when needed.

`@PostFilter` does not replace deciding “whether the caller may invoke the list API at all”: you can combine `@PreAuthorize("hasAuthority('document:list')")` to deny the entire call upfront, then `@PostFilter` to restrict individual returned items. Test both invocation authority and individual element contents.

## 5. Comparing Testing Strategies and Error Handling

| Scenario | What to Assert | Assertion That Can Mislead |
| --- | --- | --- |
| `@PreAuthorize` denied | `AccessDeniedException`; side-effect/method-body counter equals 0 | Checking only the exception without proving the method did not run |
| `@PostAuthorize` denied | `AccessDeniedException`; method read exactly once | Assuming the method never ran because the caller got no object |
| `@PreFilter` with mixed input | Exact IDs seen **inside the method body** | Inspecting only the input after the call (depends on collection mutation) |
| `@PostFilter` with mixed output | Caller receives only permitted IDs, right owners, and order if needed | Asserting only count |
| Zero matching elements | Empty collection per contract, not automatically 403 | Treating an empty list as equivalent to access denied |
| Unauthenticated | Test actual authentication/context mechanism | Assuming HTTP 401 in a unit method test |
| Missing resource | Verify not-found per contract | Using an unchecked null expression and treating a SpEL error as 404 |

In non-HTTP **method security tests**, denial normally surfaces as `AccessDeniedException`; HTTP 401/403 codes belong to web filters/entry points/exception translation and require **separate MockMvc/HTTP integration tests** to verify. `@WithMockUser` creates a mock Authentication with username and authorities, without verifying passwords/JWT signatures/claim converters. If the app uses OAuth2, tenant claims, or custom principals, add converter tests and tests with realistic `Authentication` objects.

Essential regression cases: authorized user, missing authority, foreign ownership, nonexistent ID, all-valid batch, mixed batch, completely filtered batch, list results for Alice/Bob/Charlie, and invocations across real entry points (controllers, async/message consumers) that may use different proxies.

## 6. Common Mistakes

1. **Missing `@EnableMethodSecurity`:** adding annotations without activating method security. The Spring Boot Security starter does not automatically enable pre/post annotations.
2. **Using `new Service()` in tests:** bypasses the Spring proxy. `self-invocation` (`this.securedMethod()`) also typically bypasses proxy-based interception.
3. **Trusting `owner` in input JSON:** callers can spoof owner; derive permissions from server-side IDs/tenants.
4. **Using `@PostAuthorize` for operations with side effects:** checking after the method body may be too late.
5. **Using `@PreFilter` instead of rejecting the whole batch:** silently dropping objects can violate atomicity/business semantics.
6. **Testing only happy paths and list counts:** fails to catch leaked IDs belonging to others.
7. **Making `@PostFilter` the default query strategy:** loads excess data and breaks pagination, counts, and caches.
8. **Using immutable inputs** for filters requiring mutation or wrong map expressions (`filterObject.owner` instead of `filterObject.value.owner`).
9. **Confusing `roles` with `authorities`:** `@WithMockUser(roles="ADMIN")` creates `ROLE_ADMIN`; `authorities="document:archive"` is the exact authority string.
10. **Assuming every annotation produces HTTP 403:** method tests and HTTP tests have different boundaries; `@PreFilter/@PostFilter` usually just return the filtered collection.

## 7. Adoption Checklist

- [ ] Clearly decide whether the policy must **deny the entire operation** or **filter individual elements**.
- [ ] For data writes, block unauthorized calls **before** side effects, verifying owner/tenant from the server.
- [ ] When checking results afterward, ensure the method performs no dangerous side effects before authorization.
- [ ] Enable `@EnableMethodSecurity` and invoke through Spring-managed beans/proxies.
- [ ] Test with at least two principals and a dataset containing both owned and foreign items.
- [ ] Use appropriate mutable collections for filtering; verify exact IDs/owners in service inputs and caller outputs.
- [ ] For large datasets/pagination, filter accurately in the query/data layer; check counts and query bounds.
- [ ] When exposing over an API, add HTTP 401/403/404 and business side-effect tests against the real security chain.

## References

- [Spring Security — Method Security, Pre/Post Authorize and Pre/Post Filter](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — `@WithMockUser` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithMockUser.html)
