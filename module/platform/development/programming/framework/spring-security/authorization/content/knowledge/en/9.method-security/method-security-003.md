# `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` in Spring Security

Spring Security can enforce authorization at URLs and at **methods of Spring-managed services**. The four annotations `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` all belong to **method security**, but **do not perform the same function**. The two `Authorize` annotations decide whether a call is allowed or denied, while the two `Filter` annotations remove individual elements from inputs/outputs. Misusing them is especially dangerous when processing batches of resources or when a method already causes side effects before post-checking.

This article explains the mechanisms on **Spring Security 6.x, Spring Boot 3.x, Java 17+, and the Servlet stack**: how to enable method security, the interceptor lifecycle, SpEL syntax, input/output and tenant handling, proxy pitfalls, filtering cost, transactions, and testing. Framework snippets must be placed in a Spring project with real dependencies/beans. The standalone plain Java section at the end runs independently to observe the exact differences in order and behavior.

## 1. How Do the Four Annotations Differ?

| Annotation | When? | Target | When Unsatisfied |
| --- | --- | --- | --- |
| `@PreAuthorize` | **Before the method body** | Checks whether the whole call is allowed to run. | By default throws `AccessDeniedException`; body has not run. |
| `@PostAuthorize` | **After the method body** | Checks whether the caller is allowed to receive the returned object. | By default throws `AccessDeniedException`; body has already run. |
| `@PreFilter` | **Before the body** | Filters individual elements in a supported parameter. | Drops non-matching elements; does not automatically reject the whole batch. |
| `@PostFilter` | **After the body** | Filters individual elements in the returned collection. | Drops non-matching elements; method has already run. |

Mental model:

~~~text
Caller -> Spring AOP proxy
  | @PreFilter:    [docA, docB, docC] -> [docA, docC]
  | @PreAuthorize: allowed ? YES : throw AccessDeniedException
  v
METHOD BODY (may query/write/call external APIs)
  | @PostAuthorize: can the result be handed to the caller?
  | @PostFilter:    [docA, docB, docC] -> [docA, docC]
  v
Caller receives result or exception
~~~

The diagram only illustrates **before/after** and intent. Spring AOP has separate interceptors for each annotation; actual fixed ordering depends on advisor ordering. If combining multiple annotations on the same method, test every checkpoint. Do not repeat two `@PreAuthorize` annotations on the same method because Spring Security does not support repeated annotations of the same type that way; use a single logical expression or a clear policy bean.

**To remember:** `Authorize` = **ALLOW/DENY** decision, `Filter` = transforms **element set**. `Post` = body **has already run**; it does not automatically undo side effects.

## 2. Enabling Method Security and Understanding the Spring AOP Proxy

In Spring Boot 3, `spring-boot-starter-security` **does not automatically enable method-level authorization**. You need to configure:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

With Spring Security 6.5, `@EnableMethodSecurity` enables all four pre/post annotations by default. If you configure `@EnableMethodSecurity(prePostEnabled = false)`, they will not run automatically. `@Secured` and `@RolesAllowed` belong to different interceptors and are not the same annotations.

Common Spring Boot dependencies in Gradle Groovy:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This is only the **dependencies block**, not a full `build.gradle`. Use versions managed by Spring Boot. Legacy `@EnableGlobalMethodSecurity` should be replaced with `@EnableMethodSecurity` in new Spring Security 6 projects.

For annotations to take effect, **callers must invoke through the Spring-managed bean proxy**:

~~~text
HTTP -> controller bean -> service proxy -> method security interceptor
message consumer bean ----^                      |
scheduled job bean ------^                       v
                                           service method body
~~~

Common cases that bypass the proxy: instantiating the service with `new`, calling `this.securedMethod()` inside the same instance (self-invocation), private/final methods that cannot be intercepted under the active proxy type, or beans not picked up by component scanning. An integration test using a Spring-injected bean is mandatory to avoid assuming an annotation works just because it is present in source code.

## 3. Which Interceptors Are Used and What Data Does SpEL Receive?

Spring Security uses typical components:

| Annotation | Interceptor/Manager |
| --- | --- |
| `@PreAuthorize` | `AuthorizationManagerBeforeMethodInterceptor` paired with `PreAuthorizeAuthorizationManager`. |
| `@PostAuthorize` | `AuthorizationManagerAfterMethodInterceptor` paired with `PostAuthorizeAuthorizationManager`. |
| `@PreFilter` | `PreFilterAuthorizationMethodInterceptor`. |
| `@PostFilter` | `PostFilterAuthorizationMethodInterceptor`. |

SpEL is evaluated via `MethodSecurityExpressionHandler` (by default usually `DefaultMethodSecurityExpressionHandler`) with `Authentication`/principal and the method invocation. Special variables:

| Symbol | Meaning |
| --- | --- |
| `authentication` | Caller `Authentication` from the security context. |
| `principal` | Principal of the Authentication, with type depending on the auth mechanism. |
| `hasAuthority('DOC_READ')` | Evaluates the exact authority string literally. |
| `hasRole('ADMIN')` | Under the default prefix, requires `ROLE_ADMIN`. |
| `#id`, `#documentId` | Method parameters when the resolver can obtain their names. |
| `@policy.mayRead(...)` | Calls a Spring bean containing business authorization logic. |
| `returnObject` | Value returned by the method, used in `@PostAuthorize`. |
| `filterObject` | Each element of input/output during filtering. |
| `filterObject.value` | Value of a Map entry when filtering a Map. |
| `filterTarget="items"` | Selects the parameter name for `@PreFilter` to filter. |

`#id` requires parameter names at runtime: you can use the Java compiler flag **`-parameters`** or Spring Security's `@P("id")`. `principal.tenantId` is not a built-in property on every user/JWT; you must verify the actual authenticated `Authentication`/claims. Complex logic should live in a **Java policy bean** rather than long, hard-to-test SpEL expressions.

## 4. `@PreAuthorize`: Preventing Execution When Unauthorized

A sensitive method requiring an authority:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ExportService {

    @PreAuthorize("hasAuthority('REPORT_EXPORT')")
    public String requestExport() {
        return "created";
    }
}
~~~

Someone without `REPORT_EXPORT` is denied before the body runs. This is the right choice for protecting **write actions or operations with side effects**, though specific resource permissions must also be checked.

Standalone SpEL forms:

~~~java
@PreAuthorize("isAuthenticated()")
@PreAuthorize("hasRole('ADMIN')")
@PreAuthorize("hasAuthority('DOC_READ')")
@PreAuthorize("hasAnyAuthority('DOC_READ', 'DOC_ADMIN')")
@PreAuthorize("hasAuthority('DOC_WRITE') and #id > 0")
~~~

These are **separate annotation examples**; do not put all five on one method. With `hasRole('ADMIN')`, `ROLE_ADMIN` is required by default; `hasAuthority('DOC_READ')` requires the exact authority. A JWT resource server typically converts scopes to `SCOPE_...`, and does not automatically grant `ROLE_ADMIN` to someone with `SCOPE_admin`.

When owner/tenant checks are needed, call a policy bean backed by **server** data:

~~~java
@PreAuthorize(
    "hasAuthority('DOC_APPROVE') and @documentPolicy.canApprove(authentication, #documentId)")
public void approve(long documentId) {
    documentWriter.approveWithCurrentStateChecks(documentId);
}
~~~

This is **pseudocode inside a Spring service**, requiring `documentPolicy`, `documentWriter`, repository/transactions; it will not run with only the JDK. `#documentId` must be resolvable. Using an explicit alias:

~~~java
import org.springframework.security.access.method.P;

@PreAuthorize("@documentPolicy.canRead(authentication, #id)")
public DocumentView read(@P("id") long documentId) {
    return documentReader.find(documentId);
}
~~~

If the client sends a DTO with field `owner="alice"`, that is **not** proof the document belongs to Alice. The policy must load trustworthy owner/tenant/status from the DB by ID. For data writes, TOCTOU can occur (checking and then the record changes before the write); enforce invariants close to the transaction/update and use optimistic locking, row locks, or conditional updates when needed.

## 5. `@PostAuthorize`: Checking `returnObject` After the Body Has Executed

A query returning an account:

~~~java
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.stereotype.Service;

@Service
public class AccountLookupService {

    @PostAuthorize(
        "returnObject != null and returnObject.owner == authentication.name")
    public AccountView find(long accountId) {
        return accountRepository.loadView(accountId);
    }
}
~~~

This is an **illustrative class requiring a real `AccountView`/repository**, and does not compile standalone. `returnObject` is the returned object; SpEL compares owner with the current caller. When Alice requests Bob's account, the repository **already ran**, and the result is blocked from being **handed to Alice**. This mechanism is useful to prevent IDOR on the *data return path* for side-effect-free read methods.

~~~text
Caller -> body runs -> returns AccountView
                         |
                         v
                   @PostAuthorize
                     /         \
                    /           \
                TRUE             FALSE
                 |                 |
          caller gets result   AccessDeniedException
~~~

**Do not use `@PostAuthorize` as the final gate for `transferMoney`, `deleteOrder`, `approvePayment`, `sendEmail`, or `updateDatabase`.** For methods with side effects, when the post-check fails, the side effects may **already have happened**, even if the HTTP response is 403. Combining with `@Transactional` is not guaranteed to undo everything: interceptor ordering and non-DB effects (emails/webhooks) are separate concerns. Spring Security 6.5 also warns against `@PostAuthorize` on database writes.

For null results, accessing `returnObject.owner` without a guard can fail during evaluation. Choose an explicit null/not-found policy (for example, 404 at the service or fail-closed). If the method returns a list, `@PostAuthorize` makes a **decision on the whole result**, not filtering individual elements — use `@PostFilter` when the intent is filtering a list.

## 6. `@PreFilter`: Keeping Only Valid Input Elements

`@PreFilter` filters each element of a **supported collection/array/map/stream parameter** before the body receives the data:

~~~java
import java.util.List;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.stereotype.Service;

@Service
public class DraftService {

    @PreFilter("filterObject.owner == authentication.name")
    public int countOwned(List<DraftView> drafts) {
        return drafts.size();
    }
}
~~~

This is **Spring code requiring `DraftView` with an owner and a Spring bean**. With input `[Alice's draft, Bob's draft]`, Alice can send only Alice's part into the body. Bob's part is **filtered out** without causing the entire method to throw `AccessDeniedException` by default. Therefore, do not treat a prefilter as proof that "a batch containing an invalid item will be rejected".

With multiple parameters, use `filterTarget`:

~~~java
@PreFilter(
    value = "filterObject.tenantId == @tenantContext.currentTenantId()",
    filterTarget = "items")
public void inspect(String batchId, List<WorkItem> items) {
    // items contains elements that passed prefilter
}
~~~

This snippet depends on a `tenantContext` bean, DTOs, and a discoverable parameter name `items`. In SpEL, `filterObject` is each element. If the input is a **Map**, Spring Security 6.5 documentation gives an example using `filterObject.value` (each map entry):

~~~java
@PreFilter("filterObject.value.owner == authentication.name")
public void inspectMap(Map<String, AccountView> items) {
    // Each entry needs to be evaluated by value.
}
~~~

Per the 6.5 docs, prefilter can handle arrays, collections, maps, and open streams; **the concrete types and version behavior must be tested**. Some implementations remove elements via `remove`, so immutable `List.of(...)` can fail. Use a mutable `ArrayList` in tests for collection filtering; for streams avoid already-consumed streams. Do not assume `@PreFilter` is an atomic batch validation algorithm.

### What If the Batch Must Be All-or-Nothing?

Suppose a caller requests approving three invoices 10, 11, 12 but only owns 10. `@PreFilter` can drop 11/12 and still approve 10. That is **partial success**, which can violate API contracts, corrupt audits, or leak the count of allowed items.

If you need to abort the entire batch when one item is out of scope:

1. Guard invocation permission with `@PreAuthorize("hasAuthority('DOC_APPROVE')")`.
2. Load **all real documents** by ID/tenant from the DB.
3. Verify all belong to scope, are in an approvable state, with no duplicate/missing IDs.
4. If **any** condition fails, throw a safe exception before updating.
5. Execute updates with state checks inside a transaction, handling races.

Java/Spring pseudocode:

~~~java
@Transactional
@PreAuthorize("hasAuthority('DOC_APPROVE')")
public void approveAll(List<Long> ids) {
    List<Document> docs = repository.findAllById(ids);
    if (docs.size() != ids.size()) {
        throw new EntityNotFoundException();
    }
    if (!docs.stream().allMatch(d -> policy.mayApprove(actor.get(), d))) {
        throw new AccessDeniedException("Access denied");
    }
    repository.approveWithInvariantChecks(docs);
}
~~~

The code above omits project-defined beans/types and needs handling for duplicate IDs, concurrent data, and real transactions. **Not a standalone file.** If the API intentionally allows subset processing, `@PreFilter` has value, but responses and audits must explicitly report partial processing rather than silently claiming "full success".

## 7. `@PostFilter`: Filtering What the Caller Can See After Querying

`@PostFilter` applies `filterObject` to the **returned collection of values**:

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.stereotype.Service;

@Service
public class AccountSearchService {

    @PostFilter("filterObject.owner == authentication.name")
    public List<AccountView> findCandidates(String keyword) {
        return new ArrayList<>(repository.search(keyword));
    }
}
~~~

The repository **already read the data** before filtering. Alice may receive only elements owned by Alice, yet Bob's data was already loaded into memory. Spring Security 6.5 documents support for arrays, collections, maps, and streams (if still open); for a Map you can use:

~~~java
@PostFilter("filterObject.value.owner == authentication.name")
public Map<String, AccountView> findMap() {
    return repository.loadMap();
}
~~~

These snippets only illustrate syntax and require a repository, types, and a Spring context. `@PostFilter` **does not replace** SQL filtering predicates by tenant/owner.

Why not use postfiltering for pagination?

- The DB returns the first 20 items, postfilter removes 18 belonging to others, and the caller sees a page of only 2 items.
- Metadata such as `totalElements`/`totalPages` is still computed from the unfiltered query.
- Out-of-scope loaded data can trigger N+1 queries when reading lazy owners.
- If the body already wrote logs/events/caches containing items before filtering, post-filtering cannot retract them.
- `Page<T>`/cursor responses are not automatically restructured properly by postfilter.

**Recommendation:** in multi-tenant systems, push authorization predicates into the repository/query, e.g., `WHERE tenant_id = ? AND owner_id = ?` or an appropriate sharing permission model; `@PostFilter` is only supplemental protection when datasets are small and filter semantics are clear. For Maps and immutable collections, test concrete types.

### Comparing `@PostAuthorize` with `@PostFilter`

`@PostAuthorize("returnObject.owner == authentication.name")` on a single object → if not the owner, DENY **the entire result**. `@PostFilter("filterObject.owner == authentication.name")` on multiple objects → removes individual elements, possibly returning an empty list **with status 200**. Do not treat status 200 as proof that items passed the policy if the method had a self-invocation proxy bypass.

## 8. Combined Service Example (Illustrative Spring Code)

Assume the application has `DocumentRepository`, `DocumentView`, `DocumentDraft` with an `owner` getter, and authentication setup:

~~~java
import java.util.ArrayList;
import java.util.List;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('DOC_READ')")
    public DocumentView read(long id) {
        return repository.findById(id);
    }

    @PostAuthorize(
        "returnObject != null and returnObject.owner == authentication.name")
    public DocumentView readOwned(long id) {
        return repository.findById(id);
    }

    @PreFilter(
        value = "filterObject.owner == authentication.name",
        filterTarget = "drafts")
    public int processDrafts(List<DocumentDraft> drafts, String batch) {
        return repository.processDrafts(drafts, batch);
    }

    @PostFilter("filterObject.owner == authentication.name")
    public List<DocumentView> listVisible() {
        return new ArrayList<>(repository.loadCandidates());
    }
}
~~~

**This is an API example requiring the framework and application-defined interfaces; it does not run with plain JDK.** It intentionally omits certain domain policies to illustrate the exact scope of each annotation: `read` only has a coarse authority (not yet safe from IDOR); `readOwned` only checks owner (not tenant); `processDrafts` may process a partial batch; `listVisible` loads before filtering. Production code needs owner/tenant/status/permissions from trustworthy data, all-or-nothing when required, and repository-scoped optimization.

Do not stack all four annotations on one method just to "make security stronger". Choose each mechanism according to the functional contract, write execution tests, and verify input/output types.

## 9. Relationship with HTTP Authorization and `SecurityContext`

The HTTP layer may be configured as:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/documents/**")
        .hasAuthority("DOC_READ")
    .anyRequest().denyAll()
);
~~~

The method layer can add further annotations. Result flow:

~~~text
HTTP AuthorizationFilter
  DENY -> does not reach controller
  ALLOW -> Controller -> Spring service proxy
             @PreAuthorize DENY -> body does not run
             @PreAuthorize ALLOW -> body runs
                @PostAuthorize DENY -> body ran, object not returned
                @PostFilter -> may return shortened list
~~~

HTTP 403 can come from CSRF/filters, request authorization, method authorization, or service policies; you must verify **the source of the denial**, not just look at status 403. If the service is invoked from a scheduler, message listener, or job, there is no HTTP request going through `SecurityFilterChain`: method security and domain policies are the required layers. With `@Async`/thread pools, `SecurityContextHolder` defaults to `ThreadLocal`, so workers may lack authentication unless context is propagated properly.

## 10. Standalone Java 17 Example Proving the Four Stages

The following example **does not use Spring** and deliberately uses plain Java to simulate the decisions. The demo's `preFilter`/`postFilter` return new lists rather than copying how the Spring interceptor mutates collections in place.

Save with the exact name **`FourMethodSecurityStagesDemo.java`**:

~~~java
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

public class FourMethodSecurityStagesDemo {
    record Actor(String user, String tenant, Set<String> authorities) {}
    record Document(int id, String owner, String tenant) {}

    static boolean hasAuthority(Actor actor, String authority) {
        return actor != null && actor.authorities().contains(authority);
    }

    static boolean visible(Actor actor, Document doc) {
        return actor != null && doc != null
                && actor.user().equals(doc.owner())
                && actor.tenant().equals(doc.tenant());
    }

    static List<Integer> ids(List<Document> docs) {
        return docs.stream().map(Document::id).toList();
    }

    static List<Document> preFilter(Actor actor, List<Document> incoming) {
        return incoming.stream().filter(doc -> visible(actor, doc)).toList();
    }

    static List<Document> postFilter(Actor actor, List<Document> returned) {
        return returned.stream().filter(doc -> visible(actor, doc)).toList();
    }

    static void require(boolean allowed) {
        if (!allowed) throw new SecurityException("Access denied");
    }

    static String readOne(Actor actor, Document doc, AtomicInteger bodyRuns) {
        require(hasAuthority(actor, "DOC_READ"));         // @PreAuthorize
        bodyRuns.incrementAndGet();                      // actual method body
        require(visible(actor, doc));                    // @PostAuthorize
        return "record-" + doc.id();
    }

    static int exportAllowed(Actor actor, List<Document> docs) {
        require(hasAuthority(actor, "DOC_EXPORT"));
        return preFilter(actor, docs).size();             // @PreFilter model
    }

    public static void main(String[] args) {
        Actor alice = new Actor("alice", "shop-a",
                Set.of("DOC_READ", "DOC_EXPORT"));
        Actor bob = new Actor("bob", "shop-a", Set.of("DOC_READ"));
        Actor guest = new Actor("guest", "shop-a", Set.of());
        Document first = new Document(10, "alice", "shop-a");
        Document second = new Document(11, "bob", "shop-a");
        Document crossTenant = new Document(12, "alice", "shop-b");
        List<Document> docs = List.of(first, second, crossTenant);
        AtomicInteger bodyRuns = new AtomicInteger();

        System.out.println("PreAuthorize Alice DOC_READ: "
                + hasAuthority(alice, "DOC_READ"));
        System.out.println("PreAuthorize guest DOC_READ: "
                + hasAuthority(guest, "DOC_READ"));
        System.out.println("PreFilter Alice IDs: " + ids(preFilter(alice, docs)));
        System.out.println("PostFilter Alice IDs: " + ids(postFilter(alice, docs)));
        System.out.println("PostFilter Bob IDs: " + ids(postFilter(bob, docs)));

        boolean deniedBefore = false;
        try {
            readOne(guest, first, bodyRuns);
        } catch (SecurityException ex) {
            deniedBefore = true;
        }
        System.out.println("PreAuthorize guest denied before body: " + deniedBefore);
        System.out.println("Body executions after pre-denial: " + bodyRuns.get());

        boolean deniedAfter = false;
        try {
            readOne(bob, first, bodyRuns);
        } catch (SecurityException ex) {
            deniedAfter = true;
        }
        System.out.println("PostAuthorize Bob denied after body: " + deniedAfter);
        System.out.println("Body executions after post-denial: " + bodyRuns.get());

        System.out.println("PostAuthorize Alice result: "
                + readOne(alice, first, bodyRuns));
        System.out.println("Body executions final: " + bodyRuns.get());
        System.out.println("Batch export accepted count: "
                + exportAllowed(alice, docs));
    }
}
~~~

Run on JDK 17+:

~~~bash
javac --release 17 FourMethodSecurityStagesDemo.java
java FourMethodSecurityStagesDemo
~~~

Standard stdout (verified with the command above):

~~~text
PreAuthorize Alice DOC_READ: true
PreAuthorize guest DOC_READ: false
PreFilter Alice IDs: [10]
PostFilter Alice IDs: [10]
PostFilter Bob IDs: [11]
PreAuthorize guest denied before body: true
Body executions after pre-denial: 0
PostAuthorize Bob denied after body: true
Body executions after post-denial: 1
PostAuthorize Alice result: record-10
Body executions final: 2
Batch export accepted count: 1
~~~

The body count of **0** after pre-denial proves blocking before the body. The count of **1** after post-denial proves post-checking does not prevent the body from running. Alice only sees document 10; document 12 has owner Alice but a different tenant so it is filtered out. The batch count of 1 proves filtering keeps only a subset without automatically throwing an error for the entire batch.

## 11. Testing Real Method Security in Spring Boot

Spring Security Test provides `@WithMockUser` to simulate `Authentication` and test the service directly through the Spring proxy:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class DocumentMethodSecurityIT {
    @Autowired DocumentService documents;

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void allowedRead() {
        assertNotNull(documents.read(10L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "OTHER_PERMISSION")
    void deniedRead() {
        assertThrows(AccessDeniedException.class,
                () -> documents.read(10L));
    }
}
~~~

This is a **test skeleton** requiring real repository fixtures and a Spring Test context; it does not run standalone with the JDK. For `@PreAuthorize`, add a spy/counter proving the method body **did not run** on DENY. For `@PostAuthorize`, test valid/invalid owners and prove the repository lookup **did run** when post-checking DENIES. For `@PreFilter`, use a mutable `ArrayList` with multiple owners, verify the input **seen by the body**, and test `filterTarget`. For `@PostFilter`, verify the result only contains valid items, map entries work properly, and pagination policies are honored.

Test matrix:

| Test Case | Expected |
| --- | --- |
| User lacks authority, `@PreAuthorize` | Exception, body did not run. |
| Has authority but different tenant | Domain policy still DENIES. |
| `@PostAuthorize` returns someone else's object | Body ran, caller does not receive result. |
| `@PreFilter` receives Alice/Bob batch | Body sees only subset, if business logic permits. |
| Batch must be all-or-nothing | One invalid item → reject whole batch, no partial commit. |
| `@PostFilter` returns multi-owner list | Only valid owner, no leaked items. |
| Map input/output | Expression uses `filterObject.value` properly. |
| Multi-tenant pagination | Filter in query, valid total count. |
| Called from non-HTTP bean/job | Proxy and security context must still be right. |
| Self-invocation/private/final | Test detects proxy bypass. |

A `MockMvc` test returning 403 is **not sufficient** to prove method annotations are working, because `AuthorizationFilter` or CSRF can block before the controller. Test the service independently, then test HTTP→controller→service.

## 12. Common Mistakes

1. **Forgetting `@EnableMethodSecurity`.** → Enable configuration and write negative tests.
2. **Using `@PostAuthorize` to protect write methods.** → Enforce permissions before side effects and protect transactions.
3. **Assuming `@PreFilter` rejects the whole batch.** → It filters elements; implement an all-or-nothing policy if business rules require it.
4. **Assuming `@PostFilter` optimizes queries.** → Filter in the DB by owner/tenant instead of loading everything.
5. **Passing an immutable collection into an interceptor that needs `remove`.** → Test concrete types, use mutable collections when needed.
6. **Forgetting `filterTarget` or unresolvable parameter names.** → Check `-parameters`/`@P`.
7. **Filtering a Map like a List.** → Remember `filterObject.value`.
8. **Dereferencing `returnObject.owner` without handling null.** → Fail-closed or explicit not-found handling.
9. **Reading owner only from a client-sent DTO.** → Query trustworthy server records.
10. **Service calling its own annotated method in the same instance.** → Call through proxy/another bean.
11. **Confusing `ROLE_ADMIN` with `SCOPE_admin`.** → Map authorities properly.
12. **Ignoring actor/tenant on background threads.** → Propagate context or use an intentional service identity.
13. **Testing only 200/403 responses.** → Test stage-specific behavior, body counters, input/output, and domain policies.

## 13. Implementation Checklist

- [ ] Method security is enabled and calls go through the Spring proxy.
- [ ] Use `@PreAuthorize` for execution permissions before side effects.
- [ ] Use `@PostAuthorize` when evaluating **a single read result**, never as the final gate for writes.
- [ ] Use `@PreFilter` only when the API **permits subset processing**; otherwise reject the whole batch.
- [ ] Use `@PostFilter` for suitable small collections; put large data-scoping in DB/queries.
- [ ] General permissions and real owner/tenant/state are checked against server data, never trusting DTOs.
- [ ] Verify `filterObject`, Map entries, `filterTarget`, nullable returns, and immutable collections.
- [ ] Have tests for pre-denial before the body and post-denial after the body.
- [ ] Have tests for wrong authority, different tenant, multi-owner inputs/outputs, and concurrent writes.
- [ ] Have tests calling the service over HTTP and outside HTTP; do not assume security context propagates automatically to every async thread.
- [ ] Do not treat an HTTP 403 as proof that service annotations are working properly.

**Conclusion:** `@PreAuthorize`/`@PostAuthorize` make **allow or deny** decisions before/after the call; `@PreFilter`/`@PostFilter` **filter elements** before/after the method. Distinguish these two behaviors to protect data at the right boundary: **block before side effects, avoid silent partial updates when atomic batches are needed, and push data-scoping down into queries at scale**.

### Official References

- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security 6.5 — @PreAuthorize API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/prepost/PreAuthorize.html)
- [Spring Security 6.5 — @PostAuthorize API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/prepost/PostAuthorize.html)
- [Spring Security 6.5 — @PreFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/prepost/PreFilter.html)
- [Spring Security 6.5 — @PostFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/prepost/PostFilter.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
