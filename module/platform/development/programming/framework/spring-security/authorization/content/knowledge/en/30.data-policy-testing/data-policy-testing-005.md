# Testing Bulk Operations Containing Both Allowed and Denied Items

## 1. Problem Statement and Testing Goals

A bulk operation API accepts multiple IDs in a single request—such as archiving documents, deleting records, changing order statuses, or granting permissions across multiple objects. When the caller is only authorized to act on **a subset** of the list, checking permissions at the endpoint level or checking only the first item is insufficient. This is a common source of *Broken Object Level Authorization (BOLA/IDOR)* vulnerabilities: an out-of-scope item still gets modified because it travels alongside valid items.

Running example: `POST /api/documents/bulk-archive` accepts `{"ids":[101,102,103]}`. User `alice` holds the general `DOC_ARCHIVE` authority; documents `101` and `103` belong to `alice`, while document `102` belongs to `bob`. All initially have `archived=false`.

| ID | Owner | Is Alice allowed to archive? | Initial State |
| --- | --- | --- | --- |
| 101 | alice | Yes | `archived=false` |
| 102 | bob | No | `archived=false` |
| 103 | alice | Yes | `archived=false` |

**Primary goal:** prove that item `102` remains unmodified under any published processing mode, and that outcomes for `101`/`103` adhere strictly to the chosen bulk policy. A passing or failing HTTP status code **does not by itself prove** the data is protected; tests must re-read persistence state and check side effects.

After this lesson, learners should know how to define a partial-success or all-or-nothing contract, construct mixed test data, execute requests with Spring Security Test, assert per-ID results, detect information leaks, and test transactions/concurrency.

## 2. Finalize the Security Contract Before Writing Tests

Both policies can be valid from a business standpoint, but **they must never be mixed**. Pick one policy and state explicit expectations in the API contract.

| Policy | Request containing 101, 102, 103 | Suggested HTTP/response | Post-request State |
| --- | --- | --- | --- |
| **All-or-nothing (atomic)** | At least one denied item ⇒ reject the entire batch | `403 Forbidden` or agreed error code; generic response | 101, 102, and 103 are all unchanged |
| **Partial success** | Process only authorized items; each ID has its own result | E.g. `200 OK` with per-ID `results`; `207 Multi-Status` only if intentionally defined | 101 and 103 change; 102 stays unchanged |

In the Spring example below, we **intentionally choose partial success**, returning `200 OK` and two statuses: `ARCHIVED` and `NOT_PROCESSED`. The `NOT_PROCESSED` status intentionally merges unauthorized, non-existent, and already-archived cases so it does not reveal whether an ID exists or who owns it. That is a design choice of this example API, **not a Spring Security default**.

Let `allowed(u,id)` denote the authorization decision for user `u` on object `id`, and `changed(id)` denote whether the object was updated:

- For **partial success**: `changed(id) ⇒ allowed(u,id)` for every ID; every denied ID must retain its original data.
- For **all-or-nothing**: `∃ id : !allowed(u,id) ⇒ ∀ id : !changed(id)`.
- For both: a caller lacking method-level authority for the bulk operation must be blocked **before any write**; authentication never substitutes for per-object authorization.

Also define edge cases prone to test bugs: result ordering, duplicate IDs, non-existent IDs, batch size limits, what counts as "processed" when an item is already in the target state, and rollback behavior on database errors. This example deduplicates IDs while preserving first-seen order; empty lists or invalid IDs return `400 Bad Request`.

## 3. Authorization Layers to Traverse

Typical request flow:

`HTTP request → authentication → DOC_ARCHIVE operation authority → per-ID scope check → conditional database mutation → response`.

1. **Authentication:** derive identity from the Spring Security-verified `Authentication`/principal. Never use client-supplied `username`, tenant, or role fields in JSON for authorization decisions.
2. **Functional authority:** `@PreAuthorize("hasAuthority('DOC_ARCHIVE')")` on a Spring-managed bean blocks callers lacking functional permission. Enable `@EnableMethodSecurity`; Spring Boot's security starter does not turn on method authorization automatically.
3. **Per-object authorization:** before or atomically with updating each row, verify actual owner/tenant/permission. Holding functional authority **does not mean** every ID in the batch is permitted.
4. **Safe writes:** conditional update statements like `WHERE id = ? AND owner_username = ?` ensure out-of-scope records are untouched, even when slipped between valid IDs. For richer policies, include tenant, ACL, status, and version predicates accordingly.
5. **Response:** never return owner, tenant, metadata, content, or detailed reasons for denied IDs if the caller is not permitted to see them. Use generic messages aligned with the API contract.
6. **Deep checkpoints:** do not guard only the controller. Calls to the service from jobs, listeners, or internal code must still enforce authorization rules; remember that direct calls within the same instance (*self-invocation*) bypass the `@PreAuthorize` Spring AOP proxy.

`@PreFilter`/`@PostFilter` can help in certain filtering scenarios, but they do not by themselves prove bulk write safety. In particular, **never** update records first and then strip denied items from the response: the data has already been altered, so the vulnerability still exists.

## 4. Standalone Java 17 Example: Testing Core Behavior

This snippet models an in-memory store to highlight the invariant "denied IDs are never written." It is a pure Java model and **does not replace** Spring Security, HTTP, or database tests underneath.

File `BulkArchiveDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;

public class BulkArchiveDemo {
    record Document(long id, String owner, boolean archived) {}
    enum Status { ARCHIVED, NOT_PROCESSED }
    record ItemResult(long id, Status status) {}

    static List<ItemResult> archivePartial(
            Map<Long, Document> database, String actor, List<Long> ids) {
        if (ids == null || ids.isEmpty()
                || ids.size() > 100 || ids.contains(null)) {
            throw new IllegalArgumentException("Invalid batch");
        }

        List<ItemResult> results = new ArrayList<>();
        for (Long id : new LinkedHashSet<>(ids)) {
            Document document = database.get(id);
            if (document == null
                    || !document.owner().equals(actor)
                    || document.archived()) {
                results.add(new ItemResult(id, Status.NOT_PROCESSED));
                continue;
            }

            database.put(id, new Document(id, document.owner(), true));
            results.add(new ItemResult(id, Status.ARCHIVED));
        }
        return List.copyOf(results);
    }

    public static void main(String[] args) {
        Map<Long, Document> database = new LinkedHashMap<>();
        database.put(101L, new Document(101, "alice", false));
        database.put(102L, new Document(102, "bob", false));
        database.put(103L, new Document(103, "alice", false));

        List<ItemResult> results = archivePartial(
                database, "alice", List.of(101L, 102L, 103L));

        System.out.println(results.stream()
                .map(x -> x.id() + ":" + x.status()).toList());
        System.out.println("archived=" + database.values().stream()
                .filter(Document::archived).map(Document::id).toList());
    }
}
```

Run with JDK 17 or newer:

```bash
javac BulkArchiveDemo.java
java BulkArchiveDemo
```

Exact stdout:

```text
[101:ARCHIVED, 102:NOT_PROCESSED, 103:ARCHIVED]
archived=[101, 103]
```

Try changing the owner of `102` to `alice`: all three IDs will be archived. Try `List.of(101L,101L,102L)`: each ID yields only one result because `LinkedHashSet` deduplicates while preserving order. This demo only verifies the in-memory algorithm; real tests must also prove the filter chain, method security, transactions, and database write conditions.

## 5. Applying in Spring Security: Partial Success

The example below uses Spring MVC, Spring Security method security, Spring JDBC, and transactions. It assumes the application already provides Spring Boot, Spring Security, JDBC, a DataSource configuration, and a `documents(id, owner_username, archived)` table, with classes placed in component-scanned packages. This snippet illustrates **one specific design**: only the owner may archive. If the system uses tenants/ACLs/shared permissions, replace the `owner_username` predicate with the real effective policy. Relying solely on owner in SQL is **insufficient** for other authorization models.

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {}

record BatchArchiveRequest(List<Long> ids) {}
record BatchItemResult(long id, String status) {}
record BatchArchiveResponse(List<BatchItemResult> results) {}

interface DocumentArchiveRepository {
    int archiveIfOwned(long id, String owner);
}

@Repository
class JdbcDocumentArchiveRepository implements DocumentArchiveRepository {
    private final JdbcTemplate jdbc;

    JdbcDocumentArchiveRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public int archiveIfOwned(long id, String owner) {
        return jdbc.update("""
                UPDATE documents
                   SET archived = TRUE
                 WHERE id = ?
                   AND owner_username = ?
                   AND archived = FALSE
                """, id, owner);
    }
}

@Service
class BulkArchiveService {
    private final DocumentArchiveRepository repository;

    BulkArchiveService(DocumentArchiveRepository repository) {
        this.repository = repository;
    }

    @Transactional
    @PreAuthorize("hasAuthority('DOC_ARCHIVE')")
    public BatchArchiveResponse archivePartial(
            List<Long> rawIds, Authentication actor) {
        if (rawIds == null || rawIds.isEmpty() || rawIds.size() > 100
                || rawIds.stream().anyMatch(
                        id -> id == null || id <= 0)) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid batch");
        }

        List<BatchItemResult> results = new ArrayList<>();
        for (Long id : new LinkedHashSet<>(rawIds)) {
            int updated = repository.archiveIfOwned(id, actor.getName());
            results.add(new BatchItemResult(
                    id, updated == 1 ? "ARCHIVED" : "NOT_PROCESSED"));
        }
        return new BatchArchiveResponse(List.copyOf(results));
    }
}

@RestController
@RequestMapping("/api/documents")
class BulkArchiveController {
    private final BulkArchiveService service;

    BulkArchiveController(BulkArchiveService service) {
        this.service = service;
    }

    @PostMapping("/bulk-archive")
    BatchArchiveResponse archive(
            @RequestBody BatchArchiveRequest request,
            Authentication authentication) {
        return service.archivePartial(request.ids(), authentication);
    }
}
```

**Why is this write pattern safer than `findById() → check → updateById()`?** The `UPDATE` statement modifies a row only when ID, owner, and state all match simultaneously. The update returns `0` if conditions are unmet, so the service cannot accidentally overwrite document `102`. With tenants, add `AND tenant_id = ?` using a trusted principal tenant; when sharing is allowed, substitute predicates/permission evaluators reflecting the real ACL. Relying solely on owner in SQL is **not enough** for other authorization models.

`@Transactional` causes runtime errors during updates to roll back the entire transaction by default; however, *partial success* here refers to **items denied due to authorization**, not automatic per-ID recovery from database errors. If "best effort" is needed even when one ID hits an I/O or constraint failure, separate per-ID transactions must be designed and explicitly tested.

Note: `@PreAuthorize` requires calls to pass through the Spring-managed proxy; annotations on methods called directly within the same bean may be bypassed. `hasAuthority` matches the exact string `DOC_ARCHIVE`; `hasRole("ADMIN")` involves the `ROLE_` prefix convention and cannot be swapped arbitrarily.

## 6. Spring Security Integration Tests + Post-Request Data

Requires the `spring-security-test` dependency alongside the Spring Boot Test ecosystem. The example below uses `MockMvc`, `@WithMockUser`, `csrf()`, and an isolated test database containing the `documents` table above. `@BeforeEach` resets data per test; tests have **no execution-order dependency**.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class BulkArchiveAuthorizationIT {
    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void seed() {
        jdbc.update("DELETE FROM documents WHERE id IN (101,102,103)");
        jdbc.update("INSERT INTO documents (id,owner_username,archived) "
                + "VALUES (?,?,FALSE)", 101L, "alice");
        jdbc.update("INSERT INTO documents (id,owner_username,archived) "
                + "VALUES (?,?,FALSE)", 102L, "bob");
        jdbc.update("INSERT INTO documents (id,owner_username,archived) "
                + "VALUES (?,?,FALSE)", 103L, "alice");
    }

    private boolean archived(long id) {
        return Boolean.TRUE.equals(jdbc.queryForObject(
                "SELECT archived FROM documents WHERE id = ?",
                Boolean.class, id));
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_ARCHIVE")
    void mixedBatch_updatesOnlyOwnedDocuments() throws Exception {
        mvc.perform(post("/api/documents/bulk-archive")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"ids\":[101,102,103]}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.results[0].id").value(101))
            .andExpect(jsonPath("$.results[0].status").value("ARCHIVED"))
            .andExpect(jsonPath("$.results[1].id").value(102))
            .andExpect(jsonPath("$.results[1].status").value("NOT_PROCESSED"))
            .andExpect(jsonPath("$.results[2].id").value(103))
            .andExpect(jsonPath("$.results[2].status").value("ARCHIVED"));

        assertThat(archived(101L)).isTrue();
        assertThat(archived(102L)).isFalse();
        assertThat(archived(103L)).isTrue();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_READ")
    void missingFunctionalAuthority_rejectsAllWrites() throws Exception {
        mvc.perform(post("/api/documents/bulk-archive")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"ids\":[101,103]}"))
            .andExpect(status().isForbidden());

        assertThat(archived(101L)).isFalse();
        assertThat(archived(102L)).isFalse();
        assertThat(archived(103L)).isFalse();
    }

    @Test
    @WithMockUser(username = "alice", authorities = "DOC_ARCHIVE")
    void deniedOnly_doesNotModifyDocument() throws Exception {
        mvc.perform(post("/api/documents/bulk-archive")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"ids\":[102]}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.results[0].status").value("NOT_PROCESSED"));

        assertThat(archived(102L)).isFalse();
    }
}
```

This test runs **within an application configured with the matching schema, dependencies, and security configuration**, not as a standalone Java file compiled with `javac`. For session/cookie APIs with CSRF enabled, POST test requests need `.with(csrf())`; if the API uses bearer tokens without CSRF, tests must reflect the real filter chain. `@WithMockUser` suits MockMvc tests with the Spring Test context; end-to-end HTTP tests hitting a real server and separate threads must send real credentials in the request.

What the test must uphold: `alice` authentication, `DOC_ARCHIVE` functional authority, **per-ID** results, and **post-request database state**. Do not use a mock repository returning canned JSON when the goal is proving data protection: such a mock could report `NOT_PROCESSED` for `102` even if real code wrote to the wrong row.

## 7. When Business Requirements Demand All-or-Nothing

Under an atomic policy, you must never silently "skip" `102` while committing `101` and `103`. Safe sequence:

1. Authenticate, verify functional authority, validate the entire input, and deduplicate IDs.
2. Inside the transaction, verify **every** item is authorized and in an actionable state. If any item fails, throw `AccessDeniedException` or the designated business error.
3. Once all pass, execute conditional `UPDATE` statements scoped by actor/tenant; if any update returns `0` because state or permission changed mid-flight, **throw an exception to trigger rollback** rather than returning success.
4. After a mixed request `[101,102,103]`, tests expect the contract error and verify all three rows remain `archived=false`. Also test placing the denied ID at the **end of the batch** to confirm earlier writes roll back.

`@Transactional` requires a real transaction manager and invocation through the Spring proxy. By default, Spring rolls back on unchecked exceptions such as `AccessDeniedException`; catching the exception and returning a normal response inside the transaction may allow earlier updates to commit. Never assume "running a preflight check" eliminates TOCTOU risk: use conditional updates, locks, or versioning/optimistic locking based on data criticality.

All-or-nothing expected example:

```text
Input:  user=alice; ids=[101,102,103]
Policy: 101=ALLOW, 102=DENY, 103=ALLOW
HTTP:   403 (per sample API contract)
DB:     archived(101)=false
        archived(102)=false
        archived(103)=false
```

Two severe red flags: the API returns `403` yet `101` changed (missing rollback), or the API returns `200` reporting full batch completion despite `102` being denied.

## 8. Required Test Matrix

The following checks use a clean fixture; the default expected column reflects **partial success** from Section 5. For all-or-nothing, adjust expectations for every mixed batch to **zero changes**.

| Scenario | Request / Identity | What to Assert |
| --- | --- | --- |
| All allowed | alice: `[101,103]` | Both updated, results in expected order |
| **Mixed, deny in middle** | alice: `[101,102,103]` | 101/103 updated; 102 unchanged; generic result for 102 |
| Mixed, deny at start/end | alice: `[102,101]` and `[101,102]` | Order-independent, no missed check at end of loop |
| All denied | alice: `[102]` | Zero updates and zero side effects |
| Missing functional permission | alice without `DOC_ARCHIVE` | Blocked at method/endpoint; zero writes |
| Unauthenticated | anonymous | Zero writes; `401`/redirect/`403` per configured entry point |
| Duplicate IDs | alice: `[101,101,102]` | Per sample contract: single update/result for 101 |
| Non-existent ID | alice: `[101,999]` | Do not mark 999 as updated; do not reveal existence vs denial |
| Invalid input | `[]`, null ID, negative ID, >100 IDs | `400`, zero items modified |
| Already archived record | alice: `[101]` when 101 is archived | Per sample contract: `NOT_PROCESSED`, not updated again |
| Cross-tenant/ACL | actor in tenant A, ID from tenant B | DB predicate/permission evaluator blocks even when ID is known |
| Mid-batch error | database error after one update | Rollback/partial commit matches published transaction policy |
| Concurrency | owner/permission/state changes mid-batch | No unauthorized update occurs; transaction/versioning handles properly |
| Side effects | event, audit, queue, email tied to ID 102 | No "archived" side effect emitted for denied IDs |

You do not need 14 massive tests from day one; prioritize mixed batches, all-denied, missing functional authority, and database verification, then expand variants according to module risk.

## 9. Verifying Side Effects and Preventing Information Leaks

**Do not stop at `status().isOk()` or `isForbidden()`.** After the request, re-query all three rows or compare before–after snapshots. In mock-based unit tests, `verify(repository, never()).archiveIfOwned(102L, ...)` is only supplemental; database integration tests prove actual persistence state. If events/audits/queues exist, verify no success event is emitted for ID 102 and none occurs after rollback. Auditing the denied attempt separately is acceptable if policy requires it, but it must never masquerade as a succeeded business action.

Verify the response does not contain `bob`, another tenant, document content, or messages like "ID 102 exists but does not belong to you." If a product intentionally returns `403` vs `404` by context, evaluate object-existence enumeration risk and test against that exact security contract. Do not treat `403`/`404` as a one-size-fits-all default across every API.

Additionally, bound the ID count, normalize, and validate the entire request **before** the first write. Never load each ID while skipping tenant filters in the query. Never trust a client-supplied list of "allowed" IDs. If the system processes bulk operations asynchronously, test the queue/job worker as well, since permissions can change between enqueue and execution; define a clear re-check policy and trusted actor context.

## 10. Common Mistakes and Symptoms

- **Checking only `hasAuthority`:** caller holds operation permission yet alters another user's objects; fix with per-ID decisions and conditional updates.
- **Checking one representative ID:** a valid first item masks invalid middle/last items; test shifting the denied item's position.
- **Checking only the response:** status is `403` yet the transaction partially committed; re-query the DB and secondary events.
- **Filtering the response after writing:** output looks clean while denied objects were already modified; verify persistence rather than relying on JSON.
- **Catching exceptions and committing:** under all-or-nothing, handling an error mid-transaction skips rollback; throw an unchecked exception or mark rollback per contract.
- **Allowing TOCTOU:** checking ownership first and updating unconditionally afterward; use conditional updates and handle affected row counts.
- **Skipping the real security chain:** disabling filters or mocking the entire service in integration tests leaves `@PreAuthorize`/CSRF/credentials untested.
- **Leaking via per-item errors:** messages expose owner/tenant or distinguish existing IDs the caller may not view.

## 11. Acceptance Checklist for a Bulk Authorization Test

A valuable test suite answers: *Who is calling? Which functional permission? Which IDs are allowed? Does the contract choose atomic or partial? Exactly which IDs did the database modify? Did rollback happen when required? Does the response leak data?* At minimum, a mixed-batch test must have **at least one ALLOW ID, one DENY ID, and individual post-request assertions for each ID**.

Mark the task complete only when the same isolated fixture reproduces results reliably, duplicate-ID and invalid-input behavior is explicit, both functional and object-level permissions are verified, and zero unauthorized side effects occur. Adding race-condition, tenant/ACL, or async tests depends on system architecture, but never implicitly assume `@PreAuthorize` already covers them.

## References

- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Testing Method Security: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Security — Spring MVC Test Integration: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
- Spring Security — Testing with CSRF Protection: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
