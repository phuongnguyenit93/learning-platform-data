# Testing Cross-Scope Create, Update, Delete, Search, and Export

## 1. Objective and Context

In applications with multiple tenants, organizations, workspaces, or projects, a user may hold permission to perform an **operation type** without implicitly having permission to operate on **every record**. This lesson focuses on testing authorization policies at the data scope boundary for five groups of operations: **create, update, delete, search, and export**. This test suite uncovers **Broken Object Level Authorization (BOLA/IDOR)** flaws, cross-tenant data leaks, and missing scope filters across different access paths.

Running example: a system stores documents per tenant. Alice belongs to tenant A, and Bob belongs to tenant B; both have permissions to operate on documents within their own tenant. Document A-101 belongs to A, and document B-202 belongs to B. The policy must guarantee Alice cannot create records in B, modify or delete B-202, see B-202 in search results, or receive B-202 in an export file, even if Alice guesses the exact ID and intentionally alters the URL, query parameters, JSON body, or headers.

**Testing scope:** business permissions, actor–resource relationships, parent tenant, links between records, and outcomes/side effects. This lesson uses Spring Security examples at the servlet layer; the same mindset applies to WebFlux, GraphQL, batch APIs, background jobs, and service-to-service calls, using the corresponding test tools.

### Conventions and Security Invariants

- **Authentication** verifies who is calling. **Functional authorization** determines whether that caller holds `document:create`, `document:edit`, `document:delete`, `document:search`, or `document:export`. **Data-scope authorization** determines which documents/tenants they may operate on. All three must be satisfied.
- **Effective scope** must be derived or verified from the authenticated identity and server-side membership/policy. A client-supplied tenant ID is only a parameter to validate, never a source of authority.
- **Read invariant:** every returned record, every result page, counts, and exported files belong strictly to the set of records viewable under the currently effective policy.
- **Write invariant:** a denied operation never creates, modifies, deletes, moves, or links records outside the allowed scope. Verify **persistence state after the request**, not just HTTP status.
- **Fail closed:** missing scope information, expired membership, invalid scope, or policy service errors must deny access; never silently fall back to an unfiltered query.
- **Existence hiding:** an out-of-scope resource may return `404` to avoid disclosing IDs; `403` is also valid if the API contract uses that policy. Tests assert the published contract consistently rather than arbitrarily accepting any 4xx status.

An actor may belong to multiple tenants. In that case, the server must verify the active tenant and the actor's permission for that *specific tenant*, instead of merely comparing a tenant name against a claim or trusting an `X-Tenant-Id` header.

## 2. Minimal Test Data and Permission Matrix

Prepare fixtures with at least: tenants A and B; Alice in A and Bob in B; an unauthenticated user; an authenticated user lacking the operation permission; documents A-101 and B-202; a document in A linked to an object in A; a linked object in B; and records sharing matching keywords in both A and B to catch broken search filtering. If the application allows an actor to belong to multiple tenants, add a scenario where the actor has read permission in A but write permission only in B. Data must have clearly distinguishable IDs and titles for traceability.

| Operation | Valid Case | Mandatory Cross-Scope Case | What to Verify |
| --- | --- | --- | --- |
| Create | Alice creates in A | Send tenant B in path/body; attach parent/project ID from B | No new record in B; owner is not dictated by the client |
| Update | Alice edits A-101 | Alice edits B-202 or uses path A with an ID from B | Content, version, and relationships of B-202 remain unchanged |
| Delete | Alice deletes an A document | Alice deletes B-202, including soft delete/bulk delete | B-202 still exists, with no tombstone or unauthorized delete job |
| Search | Alice sees only A's set | Filter/query/keyword matching B; pagination, totals, facets, autocomplete | No rows, metadata, or suggestions leak B |
| Export | Alice downloads only A's data | Export all, filter B, select B IDs, run job and download as another actor | File/stream/job contains only authorized data |

For each row, two additional independent checks are needed: **unauthenticated** (`401` for typical bearer APIs) and **authenticated but missing functional permission** (`403` typically); the exact status depends on the authentication entry point and error handling contract. Cross-scope cases must be tested while the actor *holds full functional permissions* to ensure the object-level check is not skipped.

### Designing a High-Signal Test Case

1. **Arrange:** create A-101 and B-202, recording pre-test content/version/row counts; configure Alice's token with the right authorities but only membership in A.
2. **Act:** send a request attempting to access B-202 or scope B via the endpoint under test.
3. **Assert response:** expect the contract-defined rejection status; the response contains no sensitive data such as title, owner, tenant, internal IDs, or stack traces.
4. **Assert persistence:** query directly under test/admin privileges to confirm B-202 is unchanged; also check join tables, attachments, soft-delete flags, events/outbox, and jobs if the operation could trigger them. Auditing a *denied* event is acceptable and distinct from business side effects.
5. **Control:** an equivalent request against A-101 succeeds and mutates only A's data. Without a positive control, a broken endpoint returning 403 unconditionally would still pass negative tests.

Do not treat a route-level `403` as sufficient proof of resource authorization: the request might be blocked for missing CSRF, missing token, or missing functional permission before the scope policy ever runs. Use proper authentication and authorities so execution reaches the path under test.

## 3. Testing CREATE: Never Accept Client Tenant or Owner as Authority

Example endpoint: `POST /api/tenants/{tenantId}/documents`. Test creating in A (succeeds); changing the path to B; keeping path A while sending JSON with `tenantId=B` or `ownerId=Bob`; passing `parentId`/`projectId` belonging to B; and submitting multiple items where one belongs to B.

Critical assertions:

- The server must verify membership and `create` permission for the target tenant; sensitive IDs/owners must be assigned or verified server-side, never mass-assigned from a DTO.
- Parent objects, folders, projects, categories, or referenced resources must also lie within the scope the actor is permitted to link. Checking only the new record's tenant is insufficient.
- A rejected request must not produce records, attachments, relationships, outbox messages, or invalid queue jobs. Check record counts before and after in **both** tenants.
- If the API supports bulk create, explicitly document whether the policy is **atomic all-or-nothing** or **partial success**; test against the contract and ensure item B is never inserted even when item A is valid.

Dangerous counterexample: a service calls `repository.save(dto.toEntity())`, accidentally copying `tenantId`/`ownerId` from the JSON body without verifying membership. An actor holding `document:create` can write across tenants even though middleware authentication succeeded.

## 4. Testing UPDATE/PATCH: Cross-Tenant IDs and Relationship Changes

Example: `PUT /api/tenants/A/documents/B-202` or `PATCH /api/documents/B-202`. Test guessing B's ID, path tenant A + body tenant B, modifying `ownerId`/`tenantId`, switching `projectId` to project B, and batch-updating multiple IDs.

Mandatory checks:

- Load/lock the record with **ID and scope conditions**, or run the policy on the loaded entity before modifying. Never call `findById(id)` and save while ignoring the tenant. With multi-tenant databases, queries may pair with RLS, yet tests must still prove access correctness.
- Check permission **on the old state** before modifying, and check permission on the **target state** if ownership/parent transfer is allowed. Immutable fields must be excluded from DTOs or rejected when modified.
- `PATCH`, JSON Merge Patch, JSON Patch, and PUT must pass through the same policy. Test JSON Patch paths like `/tenantId` and bodies containing disallowed fields, including ignored/aliased field names.
- With optimistic locking, ETag/version must be validated properly; never let a stale-update error mask a scope violation. A rejected request must neither increment the version nor record a success event.

Example database-guarded update query:

~~~sql
UPDATE documents
SET title = :newTitle, version = version + 1
WHERE id = :documentId
  AND tenant_id = :authorizedTenant
  AND version = :expectedVersion;
~~~

Zero affected rows may indicate a missing resource, out-of-scope access, or a version conflict; error-code mapping must follow the API contract without disclosing the existence of out-of-scope documents. `authorizedTenant` must originate from server-side policy, never blindly from the path/body.

## 5. Testing DELETE: Hard Delete, Soft Delete, and Async Consequences

Try `DELETE /api/documents/B-202` using Alice's token with `delete` permission in A. Alongside expecting the rejection response, re-query B-202 to confirm: it still exists; `deleted_at`/`is_deleted` is unchanged; and relations, files, indexes, caches, and outbox rows were not updated by the unauthorized delete attempt.

Separate deletion variants so no policy path is missed: single delete, multi-ID delete, filter-based delete, cascading child deletes, restore/undelete, permanent purge, and admin endpoints. If a request includes both A-101 and B-202, test the published atomic/partial-success policy; B-202 must never be deleted. Depending on the design, returning 404 for out-of-scope IDs prevents enumeration.

For background tasks, confirm the job is **never enqueued** when the request is unauthorized; also test that the worker re-checks scope upon execution if permissions/memberships can be revoked in between. Do not assume an HTTP request check alone authorizes delayed job execution.

## 6. Testing SEARCH: Filtering Both Results and Metadata

Example: `GET /api/documents?tenantId=B&q=invoice&page=0&size=20` as Alice in A. Scope filters must be applied in the base query—before pagination/aggregation—across all join branches, subqueries, search suggestions, and aggregated totals.

A scope-constrained read query pattern (`:authorizedTenant` denotes a server-verified value):

~~~sql
SELECT d.id, d.title
FROM documents AS d
WHERE d.tenant_id = :authorizedTenant
  AND LOWER(d.title) LIKE :escapedSearchPattern
ORDER BY d.id
LIMIT :pageSize OFFSET :offset;
~~~

`COUNT(*)`, facets, grouped statistics, autocomplete, pagination cursors, and search-engine queries must apply the **exact same permission predicates**. Filtering the list only after `LIMIT/OFFSET` yields incomplete pages, inaccurate `totalElements`, or cross-tenant existence leaks via counts. When joining related objects, enforce permissions on the joined data returned in the response, not just the root record.

Minimum tests:

- The same keyword appears in A and B; Alice receives only A's records; Bob receives only B's.
- Filtering by `tenantId=B` must be rejected or forced to the permitted set per the contract; never return B's records. Test empty filters, multiple tenants, nested filters, date ranges, sorting, large page sizes, and the last page.
- Verify `totalElements`, `totalPages`, counts, group-bys, facets, suggestions, and cursors; every value must reflect only visible data.
- Test results after membership revocation, after tenant switching, on cache hits and cache misses, and against eventually consistent search indexes. Cache keys must include the appropriate scope/permission context.
- When policy allows reading only a subset of records within a tenant, test filtering by record ownership/ACL/attributes rather than assuming full-tenant visibility.

## 7. Testing EXPORT: Download Files, Jobs, and Shared Links

Exports may be CSV/XLSX/ZIP/JSON, synchronous streaming endpoints, or asynchronous jobs producing a file later. Policies must be enforced **per row and per sensitive column**, matching search scope while also checking a dedicated `export` permission if specified.

Attack vectors to test: `export all` without filters; selecting B's IDs via `ids[]=...`; declaring tenant B in query parameters; exporting a saved-filter report created by someone else; requesting huge page sizes; swapping job IDs or download URLs; downloading a file generated before permission revocation; and using expired signed URLs or URLs shared with another actor.

End-to-end sequence for asynchronous exports:

1. Alice requests an export for A. The server verifies permission + scope and creates a job carrying the required identity and policy context.
2. Bob, or Alice after losing permissions, attempts to read Alice's job/file. Confirm denial per the contract.
3. Change membership before the worker executes, and verify behavior matches the designed policy: re-checking at execution time, or using a strictly bounded, short-lived permission snapshot. Never silently run exports with full-table server/admin privileges.
4. Open/parse the completed file and check the **actual list of IDs and contents**, total row count, headers, sensitive columns, multiple pages, ordering, and first/last rows; assert no markers from B appear. Checking only the filename, HTTP 200, or file size is insufficient.
5. Simulate mid-stream write failures and job retries; confirm out-of-scope data is neither re-exported nor left behind in a downloadable file.

With CSV, user-controlled values starting with formula characters can cause **CSV formula injection** when opened in spreadsheets. This is an additional output-safety test separate from scope checks: escape properly according to the contract and client applications, rather than assuming CSV quoting alone neutralizes formulas.

## 8. Placing Checkpoints in the Right Spring Security Layer

Request authorization restricts endpoint access and functional permissions. **Object-level authorization** must execute at the service/policy/domain-query layer to protect HTTP requests, async jobs, and internal service calls alike. The following snippet is **illustrative only**, requiring the application's real repository and resolver; it is not a standalone Java program:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}

@Service
class DocumentService {
    private final DocumentRepository repository;
    private final TenantAccess tenantAccess;

    DocumentService(DocumentRepository repository, TenantAccess tenantAccess) {
        this.repository = repository;
        this.tenantAccess = tenantAccess;
    }

    @Transactional
    @PreAuthorize("hasAuthority('document:edit')")
    public void rename(long documentId, String newTitle,
                       Authentication authentication) {
        // requireActiveTenant verifies membership/policy server-side.
        String tenantId = tenantAccess.requireActiveTenant(authentication);

        Document doc = repository.findByIdAndTenantId(documentId, tenantId)
            .orElseThrow(DocumentNotFoundException::new);
        doc.setTitle(newTitle); // Entity is already scope-constrained.
    }
}
~~~

`@EnableMethodSecurity` activates `@PreAuthorize` checks on Spring-managed methods. That serves as the *functional permission* guard; `findByIdAndTenantId` and `TenantAccess` enforce the *scope* guard. The snippet assumes JPA dirty checking within a transaction, valid entity setters, and API-aligned exception mapping. For bulk updates or concurrency, database-level write queries with scope predicates and affected-row checks prevent gaps between check and write. Avoid self-invocation that bypasses the method-security AOP proxy; services must be invoked through the managed bean.

If the system uses JWTs, a `tenant_id` claim alone does not prove active membership. Real authentication must verify issuer, audience, signature/expiry, and the corresponding policy/membership mechanism; testing with `jwt()` from Spring Security Test simulates a security context for authorization tests and **does not** verify full real-world token/signature validation.

## 9. Standalone Java 17 Program to Verify Five-Operation Invariants

The example below uses an in-memory store to demonstrate an automatable *behavioral contract*; it **does not replace Spring Security/JPA/integration tests**. Save `CrossScopeContract.java`, then run `javac CrossScopeContract.java` and `java CrossScopeContract` on Java 17+. Actors A and B both hold all five functional permissions; denied cases fail due to scope mismatch, not missing authorities.

~~~java
import java.util.*;
import java.util.stream.Collectors;

public class CrossScopeContract {
    record Actor(String tenant, Set<String> permissions) {}
    record Doc(long id, String tenant, String title) {}
    static class Forbidden extends RuntimeException {}
    static class NotFound extends RuntimeException {}

    static class Store {
        private final Map<Long, Doc> data = new LinkedHashMap<>();
        private long nextId = 0;

        void allow(Actor actor, String requestedTenant, String operation) {
            if (!actor.tenant().equals(requestedTenant)
                    || !actor.permissions().contains(operation)) {
                throw new Forbidden();
            }
        }

        Doc create(Actor actor, String tenant, String title) {
            allow(actor, tenant, "create");
            Doc doc = new Doc(++nextId, actor.tenant(), title);
            data.put(doc.id(), doc);
            return doc;
        }

        private Doc visible(Actor actor, long id) {
            Doc doc = data.get(id);
            if (doc == null || !doc.tenant().equals(actor.tenant())) {
                throw new NotFound();
            }
            return doc;
        }

        void update(Actor actor, long id, String title) {
            allow(actor, actor.tenant(), "update");
            Doc original = visible(actor, id);
            data.put(id, new Doc(id, original.tenant(), title));
        }

        void delete(Actor actor, long id) {
            allow(actor, actor.tenant(), "delete");
            visible(actor, id);
            data.remove(id);
        }

        List<Doc> search(Actor actor, String requestedTenant, String text) {
            allow(actor, requestedTenant, "search");
            return data.values().stream()
                .filter(d -> d.tenant().equals(actor.tenant()))
                .filter(d -> d.title().contains(text))
                .toList();
        }

        String exportCsv(Actor actor, String requestedTenant) {
            allow(actor, requestedTenant, "export");
            return data.values().stream()
                .filter(d -> d.tenant().equals(actor.tenant()))
                .map(d -> d.id() + "," + d.title())
                .collect(Collectors.joining("\n"));
        }
    }

    static void expectRejected(Runnable action) {
        try {
            action.run();
        } catch (Forbidden | NotFound expected) {
            return;
        }
        throw new AssertionError("Expected cross-scope rejection");
    }

    static void check(boolean condition) {
        if (!condition) throw new AssertionError("Contract failed");
    }

    public static void main(String[] args) {
        Set<String> grants = Set.of("create", "update", "delete",
                                     "search", "export");
        Actor alice = new Actor("A", grants);
        Actor bob = new Actor("B", grants);
        Store store = new Store();
        Doc a = store.create(alice, "A", "ALICE_PRIVATE");
        Doc b = store.create(bob, "B", "BOB_SECRET");

        expectRejected(() -> store.create(alice, "B", "SPOOF"));
        check(store.data.size() == 2);
        System.out.println("PASS create");

        expectRejected(() -> store.update(alice, b.id(), "OVERWRITTEN"));
        check(store.data.get(b.id()).title().equals("BOB_SECRET"));
        store.update(alice, a.id(), "ALICE_EDITED");
        System.out.println("PASS update");

        expectRejected(() -> store.delete(alice, b.id()));
        check(store.data.containsKey(b.id()));
        Doc temporary = store.create(alice, "A", "TEMP");
        store.delete(alice, temporary.id());
        check(!store.data.containsKey(temporary.id()));
        System.out.println("PASS delete");

        expectRejected(() -> store.search(alice, "B", ""));
        List<Doc> visible = store.search(alice, "A", "");
        check(visible.size() == 1 && visible.get(0).id() == a.id());
        System.out.println("PASS search");

        expectRejected(() -> store.exportCsv(alice, "B"));
        String csv = store.exportCsv(alice, "A");
        check(csv.contains("ALICE_EDITED") && !csv.contains("BOB_SECRET"));
        System.out.println("PASS export");
    }
}
~~~

Expected output:

~~~text
PASS create
PASS update
PASS delete
PASS search
PASS export
~~~

The program includes both positive and negative controls for each group. A real store requires transactions, relational data, validation, authentication, isolation, and file-read controls. The `Store` class is only a small model to make invariants clear; never implement production with an in-memory map.

## 10. Spring MVC Tests and Recommended Test Layers

Use `spring-security-test` and Spring MVC Test/MockMvc for servlet applications. For a JWT resource server, you can simulate a principal with `jwt()` and specify authorities to focus on policy testing; the following adapted snippet assumes the application provides the route, fixture data, and tenant extraction from the principal. **This test snippet is an integration skeleton and will not compile standalone without the project's Controller/Repository/fixtures.**

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@Sql("/fixtures/two-tenants.sql")
class CrossTenantDocumentTest {
    @Autowired MockMvc mvc;
    @Autowired DocumentRepository repository;

    @Test
    void aliceCannotEditBobsDocument() throws Exception {
        String originalTitle = repository.findById(202L)
            .orElseThrow().getTitle();

        mvc.perform(patch("/api/documents/{id}", 202L)
                .with(jwt().jwt(j -> j.subject("alice")
                    .claim("tenant_id", "A"))
                    .authorities(new SimpleGrantedAuthority("document:edit")))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"ATTACK\"}"))
            .andExpect(status().isNotFound()); // API contract uses 404.

        assertThat(repository.findById(202L)
            .orElseThrow().getTitle()).isEqualTo(originalTitle);
    }
}
~~~

Required imports/setup depending on context: JUnit 5 `@Test`; Spring Boot Test `@SpringBootTest`, `@AutoConfigureMockMvc`; Spring Test `@Sql`; `MockMvc` and static request/status matchers; `jwt()` from `SecurityMockMvcRequestPostProcessors`; AssertJ `assertThat`; and `spring-security-test` as a test dependency. For APIs using CSRF on state-changing requests, add a valid CSRF token so the test actually exercises the scope policy. If the API publishes `403` instead of `404` for out-of-scope access, update the assertion consistently with the contract.

Three complementary test layers:

1. **Unit/policy tests:** pass actor, resource, tenant, role, membership, and policy version into the decision function; test allow/deny tables, revoked memberships, missing/invalid scopes, and linked ownership. Fast, but does not guarantee every entry point invokes the policy.
2. **Integration/service + database tests:** run real repositories and transactions or a production-like environment; test scope predicates on SELECT/COUNT/UPDATE/DELETE, joins, bulk writes, soft deletes, RLS (if used), outbox, transaction rollbacks, and optimistic locking. Do not mock the logic you want to prove.
3. **HTTP/E2E + async tests:** call every real route as actor A/B (MockMvc plus at least one genuine bearer-token auth flow when needed); assert status, payload, and post-request state. For exports, parse the file/binary/ZIP with an actual parser, wait deterministically for job completion, and check contents by IDs and markers. Test download URLs and job permissions separately.

Create reusable fixture and assertion helpers, but **do not** reuse the same expected ID or expected status across all cases when policies differ. Each test must state its actor, operation, resource scope, and invariant clearly.

## 11. Frequently Overlooked Blind Spots

| Scenario | Risk | Suggested Test |
| --- | --- | --- |
| Checking authorities only in controller | Broad edit permission allows editing any ID | Actor with `edit` in A is still denied on B |
| Client-supplied `tenantId` or `ownerId` | Mass assignment / forged scope selection | Spoof B via path, header, body, and nested objects |
| Fetch by ID then filter afterward | IDOR or metadata leak once entity is loaded | Compare entity, scope, response, and DB before–after |
| Search filtered after paging | Counts, total pages, facets, and cursors leak | Compare all metadata between A and B |
| Shared cache/search index | Cache poisoning or stale data leak | Test cache hit/miss, index lag, policy revocation |
| Soft delete/cascade/batch | Accidental deletion of cross-tenant child records | Verify child records, relations, tombstones, outbox, files |
| Export running as service admin | Bypasses the job creator's scope | Verify rows/files/jobs under the requester's identity |
| Predictable file download URLs | Cross-actor file download | Swap job/file IDs and access after revocation |
| Policy checked only at request time | Permissions change before commit/job runs | Test transaction races, permission revocation, retries |
| Cross-tenant resource references | Allowed to create in A while linking foreign key B | Try parentId, projectId, ownerId, attachment ID belonging to B |

Depending on the system, add tests for hierarchical organizations, document sharing groups, multi-tenant roles, properly scoped super-admins, anonymized data, DB partitioning, and row-level security. Special privileges must have tests for both **legitimate grant** and **privilege bounds**, without adding default bypass paths.

## 12. QA Checklist Before Declaring a Policy Safe

- [ ] At least two independent scopes, records sharing identical keywords, and actors with full authorities in different scopes.
- [ ] Each of create/update/delete/search/export has a positive control, cross-scope negative test, unauthenticated test, and missing-functional-permission test.
- [ ] Scope is covered in path/query/body/headers, referenced relationships, bulk IDs, and batch endpoints.
- [ ] Every denial is verified **post-request**: database, version, soft-delete, links, files, jobs, outbox, side effects.
- [ ] Search verifies rows, total/count, pagination, facets, suggestions, caches, and index layers.
- [ ] Export verifies actual file contents, jobs, download URLs, retries, and permission revocation.
- [ ] Scope predicates live in the service/query or equivalent policy; missing scope fails closed.
- [ ] The same policy applies across HTTP, jobs, internal services, and rarely used routes.
- [ ] Error codes match the contract and do not disclose out-of-scope documents.
- [ ] Test fixtures are isolated, repeatable, assert real data, and do not rely solely on mocks.

**Completion criteria:** every valid request affects only data within its permitted scope; every cross-scope request is rejected or returns only the permitted subset per contract, with zero leaks via payload, metadata, files, or side effects. A test checking only HTTP status does not prove this invariant.

### References

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): enabling and testing `@PreAuthorize`.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): securing HTTP entry points and distinguishing request authorization from data policies.
- [Spring Security — Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `jwt()` request post-processor for MockMvc.
