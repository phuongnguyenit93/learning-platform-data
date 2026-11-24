# Risk of Partial Updates When Filtering Batch Request Data

## 1. The Problem to Understand

In Spring Security, method-level authorization (method security) can check permissions for **each element** of a list passed into a service using `@PreFilter`. This mechanism is useful when business rules intentionally allow "process only the elements the user is authorized for". However, if an API receives **a batch update request** and promises **all-or-nothing** processing, silent filtering can cause **partial updates**.

For example, a user submits three document update commands `[101, 102, 103]`, but only has permission to edit `101` and `103`. With input filtering:

- Original data: `[101, 102, 103]`.
- List entering the method body after filtering: `[101, 103]`.
- The service updates these two documents and returns success.
- Document `102` is not updated; the caller may not realize the request was trimmed.

This is the difference between **"transaction succeeded on the filtered list"** and **"the entire original request was executed"**. A database transaction can commit the two changes `101` and `103` intact while still violating the business commitment of a three-element request.

**Goal:** accurately identify the risk when filtering data at the method security layer; choose between a whole-operation denial policy or intentional partial success; control transactions, consistency, and API responses accordingly.

## 2. How Does `@PreFilter` Work?

To use annotations like `@PreAuthorize`, `@PreFilter`, and `@PostFilter`, the application needs to enable method security, for example:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

The two annotations in the snippet above belong to Spring Framework (`org.springframework.context.annotation.Configuration`) and Spring Security (`org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity`).

When an invocation passes **through a Spring proxy** to a Spring-managed method:

1. `@PreFilter` advice evaluates each element of the filtered parameter; in the SpEL expression, `filterObject` represents the current element.
2. Elements failing the condition are removed from the data passed into the method. For `Collection`, note removal support; passing an immutable collection like `List.of(...)` may cause operation errors, depending on the processing path.
3. The method body receives and processes the remaining elements. `@PreFilter` itself **does not require denying the entire invocation** just because one element was removed.

Integration illustration in an application that already has `ChangeRequest`, a repository, and a `documentPolicy` bean:

```java
@Service
class UnsafeBatchService {
    private final DocumentRepository repository;

    UnsafeBatchService(DocumentRepository repository) {
        this.repository = repository;
    }

    @PreFilter("@documentPolicy.canEdit(authentication, filterObject.id())")
    @Transactional
    public void updateAll(List<ChangeRequest> commands) {
        for (ChangeRequest command : commands) {
            repository.updateTitle(command.id(), command.title());
        }
    }
}
```

*This is an illustrative integration snippet, not a standalone runnable Java file:* `ChangeRequest`, `DocumentRepository`, and `documentPolicy` are application-provided types/beans. `documentPolicy.canEdit` must check permissions on **trusted data from the server/database**, not trust a client-supplied "owner" field. If 1 of 3 elements is filtered out, the loop only updates 2 of 3 elements; `@Transactional` does not automatically restore removed elements.

If there are multiple collection-typed parameters, explicitly identify the parameter to filter with `filterTarget` and ensure Spring resolves parameter names properly (e.g., compiling with `-parameters` or an appropriate naming mechanism). With a single collection parameter, `filterTarget` can usually be omitted.

**Distinguish three mechanisms:**

| Mechanism | Timing | When Check Fails | Implications for Bulk Write |
| --- | --- | --- | --- |
| `@PreFilter` | Before method body runs | Removes unauthorized elements from parameter | Easily causes partial updates if the service writes remaining elements |
| `@PreAuthorize` | Before method body runs | Denies the **entire invocation**, usually throwing `AccessDeniedException` | Suitable for "every item must be permitted" if checked on **the original request** |
| `@PostFilter` | After method body returns | Filters elements from **the return value** | Only changes returned data; does not undo writes that already occurred |

`@PostAuthorize` also checks after the method runs; post-write checks should not be used as the primary authorization barrier for a bulk write. In particular, **filtering results is not equivalent to rolling back data**.

Advanced note: when combining `@PreFilter` and `@PreAuthorize` on the same method, do not assume `@PreAuthorize` still sees the original list. In the default method security advisor configuration, pre-filter has an earlier order than pre-authorize; count or permission checks on the parameter may be applying to **the already-filtered list**. For all-or-nothing business logic, avoid placing `@PreFilter` on the same write path.

## 3. Why Are Partial Updates Dangerous?

### 3.1. API Contract Mismatch

Suppose endpoint `PATCH /documents/bulk` receives:

```json
{
  "changes": [
    {"id": 101, "title": "A1"},
    {"id": 102, "title": "B1"},
    {"id": 103, "title": "C1"}
  ]
}
```

If the API returns `200 OK` with the message "Updated 3 documents" while only editing `101` and `103`, the response contradicts reality. Even if returning "Updated 2 documents", the API still needs to make clear which items were rejected and whether partial success is part of the contract.

### 3.2. Breaking Business Invariants

A batch may represent a single logical operation: transitioning all invoices to a new state, allocating quotas for a group, closing a processing period, or updating interdependent items. Dropping one item can break balance or leave an undesirable intermediate state.

### 3.3. Hindering Auditing and Retries

The input list in logs may differ from the list actually written. A client retrying the entire request may re-write elements that succeeded; if the operation is not idempotent, consequences are worse. A filter running before the method body can also erase traces of which items were rejected if the application does not keep the original list.

### 3.4. Confusing Access Control with Atomicity

Authorization answers "who can do what on which resource"; transactions answer "do changes within a resource scope commit/roll back together". The two mechanisms address different questions:

- `@PreFilter` selects the set of elements to process.
- `@Transactional` wraps the actual write operations when running through a transactional proxy and transaction-capable resources.
- The transaction **does not know** three items were sent by the client if it only receives two items after filtering.

Therefore, placing `@Transactional` on a method with `@PreFilter` **does not guarantee** "update nothing if one element in the original request is forbidden".

## 4. Explicitly Choosing Between Two Business Contracts

### A. All-or-Nothing: Recommended for an Atomic Bulk Command

Rule: **write only if all elements are valid and permitted; if even one element is invalid/unauthorized, write none**.

Workflow:

1. Receive the full original request; check for null, empty list, malformed data, and duplicate IDs.
2. Check method/role-level permission, then **check object-level permission for every ID** based on authoritative records on the server.
3. When concurrency protection is needed, read and lock or check versions within the same transaction scope as the write operation.
4. If any item is missing, forbidden, or in an invalid state, throw an appropriate exception **before the first write operation**.
5. Write only after all items pass validation; a mid-way failure must roll back the transaction according to the defined policy.
6. Return a success response only when the entire batch is applied.

You can use `@PreAuthorize("@bulkPolicy.canEditAll(authentication, #p0)")` at the service boundary to **deny the entire invocation** when the full original list does not satisfy the policy. `#p0` is the first parameter, avoiding parameter name dependency. If permissions depend on concurrently mutable data, re-check data/versions inside the transaction before writing: a precheck before the transaction is insufficient to eliminate time-of-check/time-of-use race conditions.

### B. Partial Success: Only When the Product Explicitly Permits It

Rule: each element is an independent operation; the result must clearly state successes, rejections, and business errors **per ID**. Design transaction boundaries per item or permitted group; define retry/idempotency strategies. Business response example:

```json
{
  "requested": 3,
  "updated": [101, 103],
  "rejected": [
    {"id": 102, "reason": "NOT_AUTHORIZED"}
  ]
}
```

HTTP status and response content must follow the published contract; do not automatically assume every partial success case is `200` or `207`. Avoid disclosing sensitive information about resource existence/ownership in error messages. If distinguishing "not found" from "unauthorized" is needed, weigh the API's security requirements.

## 5. Safe Service Design for All-or-Nothing

The following example uses Java 17 and Spring Security method authorization. This is a **compilable class when placed in a Spring project with the corresponding dependencies**; the `DocumentStore` implementation is provided by the project. The decisive point is that `lockAndFindByIds` must read/lock authoritative rows inside the same transaction performing the write.

File `BatchDocumentService.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BatchDocumentService {

    public record ChangeRequest(long id, String title) {}

    public record DocumentSnapshot(long id, String ownerUsername) {}

    public interface DocumentStore {
        // Implementation: load authoritative rows with appropriate locking.
        List<DocumentSnapshot> lockAndFindByIds(List<Long> ids);

        // Implementation: perform a database update within the caller's transaction.
        void updateTitle(long id, String title);
    }

    private final DocumentStore store;

    public BatchDocumentService(DocumentStore store) {
        this.store = store;
    }

    @PreAuthorize("hasAuthority('DOCUMENT_WRITE')")
    @Transactional
    public void updateAll(List<ChangeRequest> commands) {
        if (commands == null || commands.isEmpty()
                || commands.stream().anyMatch(c ->
                    c == null || c.id() <= 0
                    || c.title() == null || c.title().isBlank())) {
            throw new IllegalArgumentException("Invalid batch");
        }

        List<Long> ids = commands.stream()
                .map(ChangeRequest::id)
                .toList();

        if (new HashSet<>(ids).size() != ids.size()) {
            throw new IllegalArgumentException("Duplicate ID");
        }

        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
        if (auth == null) {
            throw new AccessDeniedException("Authentication required");
        }

        Map<Long, DocumentSnapshot> byId = new HashMap<>();
        for (DocumentSnapshot document : store.lockAndFindByIds(ids)) {
            byId.put(document.id(), document);
        }

        boolean denied = ids.stream().anyMatch(id -> {
            DocumentSnapshot document = byId.get(id);
            return document == null
                    || !auth.getName().equals(document.ownerUsername());
        });
        if (denied) {
            throw new AccessDeniedException("Batch access denied");
        }

        // Only reached when ALL original items pass authorization.
        for (ChangeRequest command : commands) {
            store.updateTitle(command.id(), command.title());
        }
    }
}
```

How to read the example:

- `@PreAuthorize("hasAuthority('DOCUMENT_WRITE')")` blocks lack of general permission **before** entering the method. Per-object ownership is confirmed after loading authoritative records inside the transaction.
- `@PreFilter` is not used, so `commands` preserves the exact number of elements sent by the client; there is no silent item removal.
- Validating the list and detecting duplicate IDs prevents writing the same resource twice due to malformed input.
- `lockAndFindByIds` is a data-access layer contract: the real adapter must perform locking/version checks appropriate to the database and chosen isolation level; the method name **does not automatically create a lock**.
- The `document == null` condition rejects the whole batch if any ID cannot be retrieved. `ownerUsername` comes from the server record, preventing the client from spoofing ownership in the body.
- `AccessDeniedException` is an unchecked (runtime) exception. With default transaction behavior, this exception triggers rollback. If an error occurs after several `updateTitle` calls, rollback reverts changes participating in the same transaction.
- The code requires a real `DocumentStore` bean, transaction infrastructure, `@EnableMethodSecurity` configuration, and calls through a proxy. This is not a plain JDK example runnable with `javac` without a classpath.

**Do not misread the example:** the locking mechanism must match the database; some business flows require optimistic locking (`@Version`/`If-Match`), status verification, tenant, quota, or state transition checks inside the transaction before writing. If an update can fail due to DB constraints, let the exception propagate or configure explicit rollback, rather than catching errors and returning success.

### Transaction Limitations to Account For

- `@Transactional` typically operates through a Spring proxy; self-calling an annotated method from another method in **the same instance** may bypass advice.
- By default Spring rolls back on `RuntimeException` and `Error`; checked exceptions do not roll back by default (configurable via `rollbackFor`).
- DB transactions do not automatically roll back emails, HTTP requests to external systems, written files, sent messages, or side effects outside the transactional resource. Use outbox/post-commit events, idempotency, and compensation mechanisms where appropriate.
- Checking permissions at entry does not replace checking the state read and used at write time. Handle cases where permissions, owner, or resource version change during execution.
- For large batches, consider locking costs and timeouts; if splitting into multiple transactions is required, the API is no longer a single atomic DB transaction, which must be communicated clearly to clients.

## 6. Standalone Runnable Java 17 Program: Seeing the Difference

The following snippet **simulates element filtering results** without needing Spring; it does not itself trigger `@PreFilter`. It lets us clearly observe the two business contracts, while the Spring code above shows how to apply it in a real service.

Save as `BatchFilterRiskDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

public class BatchFilterRiskDemo {
    record Change(long id, String newTitle) {}

    static final Set<Long> ALLOWED_IDS = Set.of(101L, 103L);
    static final List<Long> WRITTEN_IDS = new ArrayList<>();

    static void write(List<Change> commands) {
        for (Change command : commands) {
            WRITTEN_IDS.add(command.id());
        }
    }

    static void silentlyFilterThenWrite(List<Change> original) {
        List<Change> filtered = original.stream()
                .filter(c -> ALLOWED_IDS.contains(c.id()))
                .toList();
        write(filtered);
    }

    static void validateAllThenWrite(List<Change> original) {
        boolean denied = original.stream()
                .anyMatch(c -> !ALLOWED_IDS.contains(c.id()));
        if (denied) {
            throw new SecurityException("Denied: cancel entire batch");
        }
        write(original);
    }

    public static void main(String[] args) {
        List<Change> batch = List.of(
                new Change(101, "A1"),
                new Change(102, "B1"),
                new Change(103, "C1")
        );

        silentlyFilterThenWrite(batch);
        System.out.println("Filtered write: " + WRITTEN_IDS);

        WRITTEN_IDS.clear();
        try {
            validateAllThenWrite(batch);
        } catch (SecurityException ex) {
            System.out.println(ex.getMessage());
        }
        System.out.println("All-or-nothing write: " + WRITTEN_IDS);
    }
}
```

Compile and run from the directory containing the file:

```bash
javac BatchFilterRiskDemo.java
java BatchFilterRiskDemo
```

Exact stdout:

```text
Filtered write: [101, 103]
Denied: cancel entire batch
All-or-nothing write: []
```

In the simulation, `WRITTEN_IDS` is an in-memory ID log, **not a database transaction**. It demonstrates the difference in the input set processed; proving actual rollback requires integration tests with the application's transaction and database.

## 7. Security Testing According to the Contract

With the **all-or-nothing** choice, you should have integration tests calling the service through a Spring bean/proxy, verifying DB data before and after. Core scenarios:

| Scenario | Expected Result | Signal to Verify |
| --- | --- | --- |
| All IDs exist, all permitted | Complete success | Number of written records equals original item count |
| One ID is unauthorized | Complete denial | **0** DB changes, not just "fewer" |
| No ID is permitted | Complete denial | **0** changes |
| One ID does not exist | Per policy, usually complete denial | Do not write remaining IDs |
| Duplicate IDs or invalid payload | Input error reported | No writes or duplicate writes |
| General role valid but object permission missing | Complete denial | Verify object-level permission check actually runs |
| DB error on second item after first item written | Roll back entire transaction | First item returns to previous state |
| Owner/version changed concurrently | Detect conflict/lock per policy | Do not commit based on stale permission state |
| API configured for partial success | Explicit response per ID | `requested = updated + rejected + failed` per contract definition |

Also test when the caller passes a mutable `ArrayList` and an immutable collection, especially if choosing `@PreFilter`. Tests must go through the proxy; calling `new Service(...)` directly will not test method security advice. For HTTP APIs, verify status, response, and the actual number of records modified; do not only assert exceptions.

## 8. Frequently Asked Questions and Common Pitfalls

**Q: Is `@Transactional` enough to prevent partial updates?** No. A transaction only covers operations executed inside the transaction. If `@PreFilter` removes part of the input before the service runs, those elements were never passed to the write phase.

**Q: Can `@PreFilter` be combined with `@PreAuthorize` to keep all-or-nothing?** You should not rely on that combination without proving the order and which list is checked. The clearest approach for an atomic command is to keep the input intact and reject when **any** original item lacks permission.

**Q: Does `@PostFilter` protect against unauthorized data writes?** No. It filters the return value after the method runs; for methods with side effects, hiding an item from the result does not erase the side effect.

**Q: Is checking an `ownerId` field from the request enough?** No. Permissions must be checked against trusted server-side resources/tenants/state. A client can alter an owner field or arbitrary IDs in the body.

**Q: When is `@PreFilter` appropriate?** When the published goal is genuinely **processing the permitted subset** (e.g., building a display list or independent per-resource tasks), and the client/business rules accept that outcome. For bulk updates, a partial success contract, complete reporting, and retry strategy are needed.

**Q: Which HTTP status code does an authorization error return?** In Spring Security web flows, `AccessDeniedException` is typically mapped to `403 Forbidden`; exact outcomes also depend on authentication, exception handling configuration, and resource-existence hiding policies. Validation errors or state conflicts must be handled separately per the API contract.

## 9. Checklist Before Putting Bulk Updates Into Production

- [ ] API clearly defines **all-or-nothing** or **partial success**, including status codes and response data.
- [ ] Permissions are evaluated for **every element in the original request**, not just elements remaining after filtering.
- [ ] `@PreFilter`/`@PostFilter` is not attached as the sole protection mechanism for atomic write operations.
- [ ] Checks exist for duplicate IDs, missing items, invalid data, and cross-item constraints.
- [ ] Per-object authorization relies on trusted data; accounts for tenants and concurrent changes.
- [ ] Transaction boundaries, rollback, locking/versioning, and external side effects are defined.
- [ ] Tests verify **0 changes** for rejected batches, even when the first item was permitted.
- [ ] Logs/audits record requests, decisions, and outcomes in a manner compliant with sensitive-data restrictions.
- [ ] Retry/idempotency is decided for network failures or unclear outcome states.

**Principle to remember:** `@PreFilter` expresses **"only pass qualifying items into the method"**; `@PreAuthorize` expresses **"is this invocation allowed to proceed?"**. For atomic bulk updates, validate **the entire original request** and control **all write operations** within an appropriate transaction.

### References

- [Spring Security — Method Security, `@PreFilter`, `@PostFilter`, `@PreAuthorize`](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Framework — Declarative transaction rollback rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — `@Transactional` annotation settings](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
