# Element Removal Policies vs. Whole-Operation Denial

> **Scope:** Spring Security – authorization, **Method Data Filtering** group. This lesson explains when to allow invoking a method while keeping only elements permitted to be viewed/processed, and when to deny the entire invocation. Examples use Java 17+ and Spring Security method security on a Spring Boot Servlet application.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Distinguish **element-level filtering** (*element filtering / partial result*) from **whole-operation denial** (*all-or-nothing authorization*).
- Choose the right timing and tool: `@PreFilter`, `@PostFilter`, `@PreAuthorize`, `@PostAuthorize`, or permission checks in the service/data layer.
- Accurately predict method execution, input/output data, empty results, exceptions, and HTTP responses.
- Avoid common security and business bugs in large queries, batch updates, pagination, and transactions.

## 2. Two Policies Solve Two Different Problems

Suppose a report store has three records: `R1(owner=alice)`, `R2(owner=bob)`, `R3(owner=alice)`. The logged-in user is `alice`.

**Element filtering**: allows operating on the valid subset; removes elements that fail the condition. For a request "list reports I can view", the list `[R1, R2, R3]` can become `[R1, R3]`. Filtering out an element **does not automatically fail the entire invocation**. If no elements are valid, the result list is usually empty.

**Whole-operation denial**: evaluates a condition that *the entire invocation* must satisfy. For a request "export all reports", someone lacking permission to export all must not receive an export containing only two records that could be mistaken for complete data. The system denies the operation and raises an access-denied error, typically mapped to HTTP 403 when authenticated in a standard web flow.

The decision point is **the business contract and the meaning of the data**: does the user accept a valid subset? Does authorization need to hold for *every* element in an atomic operation?

| Criterion | Element Filtering | Whole-Operation Denial |
| --- | --- | --- |
| Decision unit | Each element in the dataset | The entire invocation/operation |
| Result when only some elements are permitted | Returns/processes valid subset | Fails completely |
| Result when no elements are permitted | May be an empty collection | Denial exception if required condition fails |
| Typical method security tools | `@PreFilter`, `@PostFilter` | `@PreAuthorize`, `@PostAuthorize` |
| Suitable problems | "My" lists, shared lists, selecting eligible items | Full data exports, atomic updates, bulk deletes, actions requiring global permission |
| Risk if misused | Metadata leaks, silent data omission, wasted resources | Over-denial or checking too late after side effects |

> **There is no single default policy right for every API.** "Personal list" may allow filtering; "organization-wide totals" usually require operation-level permission. Two endpoints reading the same table can still have different permission contracts.

## 3. When Annotations Intervene

Enable method security with `@EnableMethodSecurity` on a configuration class. Spring Boot Starter Security **does not automatically enable** method-level authorization simply because the dependency is present. Annotations operate on calls intercepted by a Spring AOP proxy, typically public methods of a Spring-managed bean invoked from another bean.

~~~java
package example.authz;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Conceptual flow:

~~~text
Caller -> Spring AOP proxy
           |
           +-- @PreFilter: screens input collection/array/map/stream
           +-- @PreAuthorize: condition unmet -> denies, does not call method body
           |
           v
        Method executes
           |
           +-- @PostAuthorize: checks result; unmet -> denies returning result
           +-- @PostFilter: screens elements of the result
           |
           v
        Caller receives permitted data
~~~

The diagram illustrates purpose and timing, **not claiming the order among every advisor or every other proxy**. When combining multiple annotations, rules are applied sequentially; whole-invocation blocking conditions must be satisfied. `@PostAuthorize` and `@PostFilter` both run **after the method body has executed**; they do not prevent database queries that have already occurred. Spring Security provides interceptor ordering and allows customization, so do not rely on the illustrated order when designing side effects.

- `@PreFilter("...")`: for collection-like inputs, the `filterObject` variable is each element; non-matching elements are removed before business logic receives the collection.
- `@PostFilter("...")`: for collection-like outputs, `filterObject` is each returned element; non-matching elements are removed from the result.
- `@PreAuthorize("...")`: condition applies to the entire invocation **before** execution. Suitable for blocking write operations when the user lacks permission.
- `@PostAuthorize("...")`: condition applies to the invocation result **after** execution; `returnObject` refers to the result. Useful when authorization decisions require reading object properties, but should not be the sole defense for write operations.

Expression examples use `authentication.name` (principal name), `hasAuthority('report:read')` (exact authority), `filterObject.owner()` (calling a Java record accessor), and `#p0` (the method's first parameter). For a JavaBean with `getOwner()`, you can use `filterObject.owner`. To access parameters by name such as `#id`, appropriate compiler/parameter-name discovery configuration is required; `#p0` avoids that dependency.

## 4. Spring Security Example: Filtering Lists While Blocking Unauthorized Reads/Exports

The following files are in the same package of a Spring Boot application that already has `spring-boot-starter-security`. The repository is mocked in memory to focus on policy. The record class uses the `owner()` accessor; the store returns a filterable `ArrayList`.

**`Report.java`**

~~~java
package example.authz;

public record Report(long id, String owner, String title) {
}
~~~

**`ReportStore.java`**

~~~java
package example.authz;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Component;

@Component
public class ReportStore {
    private final List<Report> reports = List.of(
            new Report(1L, "alice", "Report A"),
            new Report(2L, "bob", "Report B"),
            new Report(3L, "alice", "Report C")
    );

    public List<Report> findAll() {
        return new ArrayList<>(reports);
    }

    public Optional<Report> findById(long id) {
        return reports.stream().filter(r -> r.id() == id).findFirst();
    }
}
~~~

**`ReportAccess.java`** – bean determining permission per record (demo uses simple owner; real applications must also consider tenant, ACL, and resource status):

~~~java
package example.authz;

import org.springframework.stereotype.Component;

@Component("reportAccess")
public class ReportAccess {
    private final ReportStore store;

    public ReportAccess(ReportStore store) {
        this.store = store;
    }

    public boolean isOwner(long reportId, String username) {
        return store.findById(reportId)
                .map(report -> report.owner().equals(username))
                .orElse(false);
    }
}
~~~

**`ReportService.java`** – three different contracts:

~~~java
package example.authz;

import java.util.List;
import java.util.NoSuchElementException;
import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final ReportStore store;

    public ReportService(ReportStore store) {
        this.store = store;
    }

    // Contract: list only includes viewable reports.
    @PreAuthorize("hasAuthority('report:read')")
    @PostFilter("filterObject.owner() == authentication.name")
    public List<Report> listVisibleReports() {
        return store.findAll();
    }

    // Contract: read exactly one record or be denied.
    @PreAuthorize("hasAuthority('report:read') and "
            + "@reportAccess.isOwner(#p0, authentication.name)")
    public Report readOne(long id) {
        return store.findById(id).orElseThrow(NoSuchElementException::new);
    }

    // Contract: complete result, silent omission is not acceptable.
    @PreAuthorize("hasAuthority('report:export:all')")
    public List<Report> exportAll() {
        return store.findAll();
    }
}
~~~

Annotations take effect when `ReportService` is called **through a Spring proxy**. If Alice has the `report:read` authority but lacks `report:export:all`:

| Invocation | Result |
| --- | --- |
| `listVisibleReports()` | Two reports IDs 1 and 3; Bob's report is omitted |
| `readOne(1L)` | Returns report ID 1 |
| `readOne(2L)` | Denied **before** running the `readOne` body |
| `exportAll()` | Denied completely; does not return a subset |
| `listVisibleReports()` with a user who has read permission but owns no records | Empty list; this is not a per-element denial error |
| `listVisibleReports()` with a user lacking `report:read` authority | Blocked completely right at `@PreAuthorize` |

**Why combine `@PreAuthorize` and `@PostFilter`?** The user must have permission to use the list-reading feature, and then each element must also satisfy the ownership condition. Placing only `@PostFilter` while forgetting feature-level permission could inadvertently allow anyone to query (even though results are filtered).

**Why does `readOne` use `@PreAuthorize`?** An API fetching a single resource has "allowed to view or not" semantics; it cannot return "part of a single object". The `reportAccess` bean checks permission before the service returns the resource. Real applications must handle non-existent/unauthorized cases under the same policy to avoid leaking existence (you may choose to map both uniformly to 404 at the HTTP layer, which is not automatically inferred from the annotation).

## 5. `@PreFilter` for Input: Use Only When Partial Processing Is Genuinely Accepted

~~~java
// Method snippet illustrated inside a @Service;
// Report has accessor owner(), and reports is an input parameter.
@PreAuthorize("hasAuthority('report:process')")
@PreFilter(filterTarget = "reports",
           value = "filterObject.owner() == authentication.name")
public List<Report> processAllowedOnly(List<Report> reports) {
    // Receives only the reports remaining after filtering.
    return reports;
}
~~~

If Alice submits `[R1, R2, R3]`, the processing logic receives `[R1, R3]`. This is **only business-correct** when the caller knows and accepts that unauthorized elements are skipped. For "approve all invoices in the request", "batch money transfer", or "delete the entire selected list", silent skipping breaks the contract and leaves partial processing state.

For an operation requiring **all-or-nothing**, pre-check all IDs/resources along with permission conditions, reject when any item is invalid, and only then execute within an appropriate transaction boundary. Sketch example in a service:

~~~java
// Logic sketch; canProcessAll must be implemented per the application's tenant/ACL.
@PreAuthorize("hasAuthority('report:process') "
        + "and @reportAccess.canProcessAll(#p0, authentication)")
public void processAtomically(List<Long> ids) {
    // Execute completely only after required checks have passed.
}
~~~

This is **non-standalone illustrative code**: `canProcessAll` and the business logic must be implemented. Prevent race/TOCTOU between checking and writing (via transactions, locking, DB update conditions, and checking affected row counts); `@PreAuthorize` itself does not create a transaction.

## 6. How Does `@PostAuthorize` Differ from `@PostFilter`?

For a single resource:

~~~java
// Illustrated in @Service that already has ReportStore.
@PostAuthorize("returnObject.owner() == authentication.name")
public Report readOneAfterCheck(long id) {
    return store.findById(id).orElseThrow();
}
~~~

`@PostAuthorize` does not create a filtered version of a report. It **accepts or denies the entire result** after `readOneAfterCheck` runs. For a call returning a list, the `returnObject` expression typically inspects the entire list as a single value; it **does not automatically iterate over each element** like `@PostFilter`.

Placing a post-check after a write method is dangerous:

~~~java
// Anti-pattern: DO NOT use as the sole authorization barrier.
@PostAuthorize("returnObject.owner() == authentication.name")
public Report updateReport(long id, String title) {
    // If DB write/event emission already happened before denial, side effects have occurred.
    throw new UnsupportedOperationException("Illustration example");
}
~~~

A post-invocation denial error does not guarantee that all non-DB side effects (emails, messages, external APIs) are rolled back. For write operations, prefer **pre-checking** before execution, and consider authorization at the data layer and transaction boundaries. Do not treat `@PostAuthorize` as an "automatic rollback".

## 7. Standalone Runnable Java 17 Example to Make Semantics Clear

This example **illustrates policy**, without simulating Spring AOP or HTTP APIs. Save as `PolicyDemo.java`:

~~~java
import java.util.List;

public class PolicyDemo {
    record Item(int id, String owner) {}

    static List<Integer> visibleIds(String username, List<Item> all) {
        return all.stream()
                .filter(item -> item.owner().equals(username))
                .map(Item::id)
                .toList();
    }

    static List<Item> exportComplete(boolean permitted, List<Item> all) {
        if (!permitted) {
            throw new SecurityException("DENIED");
        }
        return all;
    }

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item(1, "alice"),
                new Item(2, "bob"),
                new Item(3, "alice")
        );
        System.out.println(visibleIds("alice", items));

        try {
            exportComplete(false, items);
        } catch (SecurityException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
~~~

Run:

~~~bash
javac --release 17 PolicyDemo.java
java PolicyDemo
~~~

Exact stdout:

~~~text
[1, 3]
DENIED
~~~

Both approaches can protect data, but the user-facing API must clearly state when it returns a subset and when it does not allow proceeding.

## 8. Important Limitations and Consequences When Choosing a Policy

### 8.1. Pagination, Totals, and Search Conditions

`@PostFilter` processes data **after** the method has fetched/returned the output set. If the repository already fetched 20 rows for a page and only 3 rows belong to Alice, post-filtering does not turn the page into "20 rows belonging to Alice"; `totalElements`, page counts, ordering, and precomputed aggregations may be wrong or leak information. Do not promise "secure pagination" by filtering the contents of an arbitrary `Page`.

For large lists, search, pagination, or multi-tenant data, push permission predicates into queries/repositories/row-level security right at query time (e.g., `owner_id = current_user_id` combined with tenant conditions). Evaluate permissions on actual data, avoiding string-concatenating SQL directly from user input. `@PostFilter` is suitable for small sets or as an extra defense layer; it does not replace controlled query design.

### 8.2. Consistency Between List and Detail

An item hidden from `listVisibleReports` must also be denied via `readOne(id)`, export, download, search, guessable-ID URLs, and related APIs. Do not confuse "hiding in UI" or "filtering one endpoint" with overall resource access permission. Centralize ACL/ownership/tenant logic in one testable place; when a "shared" policy exists, update both list filtering and detail checks.

### 8.3. Input Filtering and Batch Writes

`@PreFilter` can mutate the input collection form or produce a filtered data form; supported data types and mutability depend on the implementation. Spring Security supports collections, arrays, maps, and open streams. For maps, `filterObject` represents an entry, e.g. `filterObject.value.owner()`. Do not assume every wrapper like `List.of(...)` or every immutable wrapper allows in-place filtering; use supported structures and write tests for actual input/output types.

Input filtering does not prove the remaining elements are safe for every action: input validation, tenant boundaries, and operation permissions are still required. If the client must be informed which elements were skipped, design a separate result (accepted IDs, rejected IDs, reasons) or choose whole-operation denial, avoiding returning "success" when items were actually dropped.

### 8.4. Check Timing, Proxies, and Side Effects

- `@PreAuthorize` checks before the method body; a denied method does not execute. `@PostFilter` and `@PostAuthorize` evaluate after the method completes, so queries/side effects may have already occurred.
- Internal calls `this.someSecuredMethod()` within the same bean usually bypass the Spring AOP proxy, causing method-level annotations not to be applied. Invoke through a proxy bean or refactor service boundaries; do not treat annotations as the sole defense layer.
- Ensure the proper security context when running async/background tasks; do not assume an HTTP request's `authentication` propagates automatically across every thread.
- Denial operations must follow the **deny by default** principle when permissions cannot be determined. Avoid catching `AccessDeniedException` and silently returning full data or turning security errors into empty lists unintentionally.
- HTTP 401/403/404 depends on authentication, entry points, exception handling, and anti-enumeration policies; method security alone does not determine every response code.

### 8.5. Performance and the Data Layer

Post-filtering all records incurs DB loading, memory, per-element expression evaluation costs, and can trigger N+1 queries when checking ACLs lazily. Using `@PostFilter` does not mean `WHERE owner = ...` was added to the DB query. For large data volumes, enforcing policies at the query layer and adding service-layer protection is usually the more efficient choice.

## 9. Testing Against a Policy Matrix

In an application with `spring-security-test`, use `@WithMockUser` or set an appropriate `SecurityContext` to call **the proxied Spring bean**, rather than instantiating the service directly with `new` and expecting annotations to run.

| Test Scenario | Expected Outcome |
| --- | --- |
| Alice has `report:read`, list has 2 Alice reports + 1 Bob report | `listVisibleReports` returns only IDs 1, 3 |
| Alice has `report:read`, only Bob's report exists | Returns empty list |
| Alice has `report:read`, reads Bob's ID 2 | `AccessDeniedException` (or appropriate subtype) |
| Alice lacks `report:read` | List call denied before processing |
| Alice lacks `report:export:all` | `exportAll` denied completely |
| User has `report:export:all` | `exportAll` returns all three records |
| Atomic batch update containing one unauthorized ID | Entire request denied, no record partially written |
| Paginated query and owner/tenant filter | Content, counts, and total pages consistent with permitted scope |
| Calling protected method through proxy bean vs. internal self-call | Tests verify authorization enforcement on the real call path |

Integration unit test example with Spring context (placed in an application with `@SpringBootApplication` scanning package `example.authz`):

~~~java
package example.authz;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class ReportServiceSecurityTest {
    @Autowired
    ReportService service;

    @Test
    @WithMockUser(username = "alice", authorities = "report:read")
    void filtersListAndDeniesAnotherOwnersReport() {
        List<Long> ids = service.listVisibleReports().stream()
                .map(Report::id).toList();
        assertEquals(List.of(1L, 3L), ids);
        assertThrows(AccessDeniedException.class, () -> service.readOne(2L));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "report:read")
    void deniesWholeExportWhenPermissionMissing() {
        assertThrows(AccessDeniedException.class, service::exportAll);
    }

    @Test
    @WithMockUser(username = "bob", authorities = "report:export:all")
    void privilegedExportKeepsAllItems() {
        assertEquals(3, service.exportAll().size());
    }
}
~~~

These tests require `spring-boot-starter-test` and `spring-security-test` along with a Spring Boot application context. The example does not yet provide a standalone runnable application; it is a set of files to integrate into an existing Spring Boot project. Do not expect "HTTP 403" in service unit tests: here you catch exceptions; HTTP status codes only appear when passing through the web/security filter chain and exception handler.

## 10. Quick Selection Rules in Real-World Scenarios

1. **Need the user to see only the permitted subset?** Return a list scoped by owner/ACL/tenant, usually filtered at the DB; `@PostFilter` can supplement small collections.
2. **A specific resource or feature requires mandatory permission?** Block with `@PreAuthorize` before the service; `@PostAuthorize` is only appropriate for reads needing result inspection after retrieval.
3. **Client sends multiple items, API allows partial success?** `@PreFilter` can be used, but document the contract clearly and return info about skipped items when needed.
4. **Write/export operations require completeness or atomicity?** Check all conditions and deny the entire invocation if one element is invalid; use transactions/DB constraints for atomicity and race prevention.
5. **Results have pagination, statistics, multi-tenancy, or large volume?** Push permission predicates into the query layer before pagination/aggregation; test all cross-cutting access paths.

**Self-check:** If Alice requests deleting both R1 (Alice's) and R2 (Bob's) at the same time, is it right for `@PreFilter` to drop R2 and delete R1? **Only if the API is designed for partial success and clearly communicates it.** If the requirement is "delete both or delete neither", the entire operation must be denied without deleting R1.

## Reference Documentation

- Spring Security Reference – Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html (sections `@PreFilter`, `@PostFilter`, `@PreAuthorize`, `@PostAuthorize`, and AOP methods).
