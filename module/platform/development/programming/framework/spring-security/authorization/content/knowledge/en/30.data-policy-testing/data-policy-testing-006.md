# Testing Pagination, Total Counts, and Masked Data

## Objective

This lesson shows how to test a paginated list API in Spring Security to guarantee three things simultaneously: (1) each page contains only records the current identity is permitted to view, (2) `totalElements` and `totalPages` do not disclose the count of out-of-scope records, and (3) sensitive fields are masked or omitted from the **actual JSON response**. A request returning HTTP 200 with `size` items does not prove any of those guarantees.

After completing this lesson, you should be able to design fixtures mixing multiple owners/tenants, write tests for first/subsequent/empty pages, reconcile `COUNT` queries with authorization policies, and use a canary value to catch secret fields appearing unexpectedly.

## 1. Define the Policy and Output Contract

Suppose endpoint `GET /api/invoices?page=0&size=2` uses 0-based page indexing and `id ASC` ordering. **Illustrative** policy:

- `ROLE_USER` sees only records where `tenantId` matches the authenticated identity's tenant **and** `ownerUsername` matches the authenticated username.
- `ROLE_ADMIN` sees all invoices within **their own tenant**; ADMIN does not implicitly cross tenant boundaries.
- `customerEmail` is returned verbatim to ADMIN and masked for USER: `alice@example.test` becomes `a***@example.test`.
- `internalMemo` must never appear in the response DTO, even when the caller is ADMIN.

Spring Security does not automatically apply row-level or field-level rules to JPA repositories; the application must implement them. Seed these test values (every `internalMemo` contains canary `SAMPLE_PRIVATE_X9`):

| ID | Tenant | Owner | Email |
| ---: | --- | --- | --- |
| 101 | t-a | alice | alice@example.test |
| 102 | t-a | bob | bob@example.test |
| 103 | t-a | alice | alice@example.test |
| 104 | t-a | alice | alice@example.test |
| 105 | t-a | alice | alice@example.test |
| 201 | t-b | alice | alice@example.test |

For `alice` in `t-a` with `ROLE_USER`, the visible records in order are **[101, 103, 104, 105]**. ID 102 has a different owner; ID 201 belongs to a different tenant even though the owner is still named alice.

| Caller and Request | IDs in `content` | `totalElements` | `totalPages` | `hasNext` |
| --- | --- | ---: | ---: | --- |
| alice/t-a USER, page=0 size=2 | [101,103] | 4 | 2 | true |
| alice/t-a USER, page=1 size=2 | [104,105] | 4 | 2 | false |
| alice/t-a USER, page=2 size=2 | [] | 4 | 2 | false |
| admin/t-a ADMIN, page=0 size=2 | [101,102] | 5 | 3 | true |
| mallory/t-a USER, page=0 size=2 | [] | 0 | 0 | false |

Let `V(u)` be the set of records user `u` is permitted to view. Content must be a slice taken after **filtering V(u) first, then sorting/limiting/offsetting**; `totalElements = |V(u)|` and, for `size > 0`, `totalPages = ceil(totalElements/size)` (when total is 0, page count is 0 per the sample contract). Never use the full table count or full tenant count when the caller only has partial visibility.

### Why Is Paginating Before Filtering Permissions a Bug?

If an owner-unconstrained query fetches the first two IDs of tenant t-a as [101,102] and the controller then drops 102, page=0 only has [101], whereas 103 belongs on the first page. A tenant-wide COUNT query returns 5, leaking the count of unauthorized rows. Setting the total to `content.size()` is also wrong: the true total must be 4, not 1. Filtering after `findAll(pageable)`, filtering in the frontend, or using a post-filter on already-paginated data can never recover accurate pages or totals.

Correct flow: **authentication → API endpoint permission → authorization predicate in query → stable sort → page and COUNT on same scope → DTO → field masking → JSON**.

Conceptual SQL example; variables must be bound as parameters and the tenant obtained from server-verified principal/claims:

```sql
SELECT id, title, customer_email, internal_memo
FROM invoice
WHERE tenant_id = :tenant
  AND (:is_admin = TRUE OR owner_username = :username)
ORDER BY id ASC
LIMIT :size OFFSET :offset;

SELECT COUNT(*)
FROM invoice
WHERE tenant_id = :tenant
  AND (:is_admin = TRUE OR owner_username = :username);
```

The `COUNT` predicates must match the data-filtering predicates. If status, soft-delete, ownership relations, ACLs, search keywords, or tenant policies are added, **both the data query and count query** must evaluate the exact same scope. Never accept a client-declared `tenantId`/`ownerUsername` as authoritative.

## 2. Reference Implementation with Spring Data JPA

The example below is an **integration snippet** inside an existing Spring Boot/Spring Security application, not a standalone compilable Java file. It assumes entity `Invoice` has `id`, `title`, `tenantId`, `ownerUsername`, `customerEmail`, and `internalMemo`; `TenantIdentity` is an application component reading the authenticated tenant; and `@EnableMethodSecurity` is enabled. Add the appropriate Spring/Java imports.

```java
interface InvoiceRepository extends JpaRepository<Invoice, Long>,
        JpaSpecificationExecutor<Invoice> {}

record InvoiceDto(Long id, String title, String customerEmail) {}

@Service
class InvoiceQueryService {
    private final InvoiceRepository repository;
    private final TenantIdentity tenantIdentity;

    InvoiceQueryService(InvoiceRepository repository, TenantIdentity tenantIdentity) {
        this.repository = repository;
        this.tenantIdentity = tenantIdentity;
    }

    @PreAuthorize("hasAnyRole('USER', 'ADMIN')")
    @Transactional(readOnly = true)
    public Page<InvoiceDto> list(Authentication actor, int page, int size) {
        if (page < 0 || size < 1 || size > 100) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid page or size");
        }

        String tenant = tenantIdentity.tenantOf(actor); // from trusted identity
        boolean admin = actor.getAuthorities().stream()
                .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));

        Specification<Invoice> visible = (root, query, cb) -> {
            Predicate sameTenant = cb.equal(root.get("tenantId"), tenant);
            return admin ? sameTenant
                    : cb.and(sameTenant,
                            cb.equal(root.get("ownerUsername"), actor.getName()));
        };

        Pageable pageable = PageRequest.of(
                page, size, Sort.by("id").ascending());

        return repository.findAll(visible, pageable).map(row ->
                new InvoiceDto(
                        row.getId(),
                        row.getTitle(),
                        admin
                                ? row.getCustomerEmail()
                                : maskEmail(row.getCustomerEmail())));
    }

    private static String maskEmail(String email) {
        if (email == null) return null;
        int at = email.indexOf('@');
        if (at <= 0) return "***";
        return email.substring(0, 1) + "***" + email.substring(at);
    }
}
```

`JpaSpecificationExecutor.findAll(spec,pageable)` applies `Specification` to both the page-fetching query and the Page count query. `Page.map` only **transforms items already fetched under the right permissions** while preserving Page metadata; it is not an authorization filtering tool. The entity holds `internalMemo`, while `InvoiceDto` omits that field. Never return JPA entities directly: getters, nested associations, or serializer changes can expose unintended fields.

For a stable JSON contract, define an explicit response DTO instead of relying on how different Spring Data versions serialize `PageImpl` directly:

```java
record PageResponse<T>(
        List<T> content, int number, int size,
        long totalElements, int totalPages, boolean hasNext) {
    static <T> PageResponse<T> from(Page<T> p) {
        return new PageResponse<>(
                p.getContent(), p.getNumber(), p.getSize(),
                p.getTotalElements(), p.getTotalPages(), p.hasNext());
    }
}

@RestController
@RequestMapping("/api/invoices")
class InvoiceController {
    private final InvoiceQueryService service;

    InvoiceController(InvoiceQueryService service) {
        this.service = service;
    }

    @GetMapping
    PageResponse<InvoiceDto> list(
            Authentication actor,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "2") int size) {
        return PageResponse.from(service.list(actor, page, size));
    }
}
```

In production, policies may be richer than USER/ADMIN roles and require appropriate `@PreAuthorize`/permission evaluators/policy services. The email masking rule is illustrative; if policy requires hiding emails from admins too, update the DTO mapping and test expectations accordingly. When sorting by `createdAt`, add `id` as a tie-breaker for deterministic pagination, e.g. `Sort.by("createdAt").ascending().and(Sort.by("id"))`.

## 3. Testing via HTTP and Database

Combine repository/query tests with `MockMvc` integration tests. A unit test mocking the repository to return a pre-built `Page` only tests mapping—it **does not prove SQL WHERE/COUNT clauses enforce permissions correctly**. For database-specific behavior, run integration tests on a production-compatible DB (e.g., Testcontainers); use a deterministic DB fixture with overlapping owners/tenants.

The example below uses the fixture table above and requires a Spring application, entity/repository, SQL fixture `/data/invoices-visibility.sql` (reset between tests), and JUnit/Mockito/Hamcrest/Spring imports. `@WithMockUser` only sets username/roles and **does not create a real tenant claim**. Mocking `TenantIdentity` here isolates the pagination problem; a separate test must verify real principals/JWTs and ensure client-supplied tenants are ignored.

```java
@SpringBootTest
@AutoConfigureMockMvc
@Sql("/data/invoices-visibility.sql")
class InvoiceQueryHttpTest {
    @Autowired MockMvc mvc;
    @MockBean TenantIdentity tenantIdentity;

    @BeforeEach
    void setupTenant() {
        when(tenantIdentity.tenantOf(any(Authentication.class)))
                .thenReturn("t-a");
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void firstPageAndTotalContainOnlyAuthorizedRows() throws Exception {
        mvc.perform(get("/api/invoices").param("page", "0").param("size", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.number").value(0))
                .andExpect(jsonPath("$.size").value(2))
                .andExpect(jsonPath("$.totalElements").value(4))
                .andExpect(jsonPath("$.totalPages").value(2))
                .andExpect(jsonPath("$.hasNext").value(true))
                .andExpect(jsonPath("$.content.length()").value(2))
                .andExpect(jsonPath("$.content[0].id").value(101))
                .andExpect(jsonPath("$.content[1].id").value(103))
                .andExpect(jsonPath("$.content[0].customerEmail")
                        .value("a***@example.test"))
                .andExpect(jsonPath("$.content[*].internalMemo").doesNotExist())
                .andExpect(content().string(
                        not(containsString("SAMPLE_PRIVATE_X9"))));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void subsequentAndOutOfRangePagesPreserveCorrectCount() throws Exception {
        mvc.perform(get("/api/invoices").param("page", "1").param("size", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content[0].id").value(104))
                .andExpect(jsonPath("$.content[1].id").value(105))
                .andExpect(jsonPath("$.totalElements").value(4))
                .andExpect(jsonPath("$.hasNext").value(false));

        mvc.perform(get("/api/invoices").param("page", "2").param("size", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content.length()").value(0))
                .andExpect(jsonPath("$.totalElements").value(4))
                .andExpect(jsonPath("$.totalPages").value(2));
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminIsStillScopedToOwnTenant() throws Exception {
        mvc.perform(get("/api/invoices").param("page", "0").param("size", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content[0].id").value(101))
                .andExpect(jsonPath("$.content[1].id").value(102))
                .andExpect(jsonPath("$.totalElements").value(5))
                .andExpect(jsonPath("$.totalPages").value(3))
                .andExpect(content().string(
                        not(containsString("SAMPLE_PRIVATE_X9"))));
    }

    @Test
    @WithMockUser(username = "mallory", roles = "USER")
    void zeroVisibleRowsMustMeanZeroTotal() throws Exception {
        mvc.perform(get("/api/invoices").param("page", "0").param("size", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content.length()").value(0))
                .andExpect(jsonPath("$.totalElements").value(0))
                .andExpect(jsonPath("$.totalPages").value(0));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void invalidPaginationIsRejected() throws Exception {
        mvc.perform(get("/api/invoices").param("size", "0"))
                .andExpect(status().isBadRequest());
        mvc.perform(get("/api/invoices").param("page", "-1"))
                .andExpect(status().isBadRequest());
        mvc.perform(get("/api/invoices").param("size", "101"))
                .andExpect(status().isBadRequest());
    }
}
```

`jsonPath` and canary matchers inspect the **serialized response**. Testing DTO objects in isolation can still miss fields injected by Jackson; testing only totals can still miss broken page contents. Verify IDs, ordering, empty pages, metadata, and absence of secret strings simultaneously. The illustrative SQL file must align with the project schema and reset for test independence.

## 4. Required Test Case Matrix

| Scenario | Expectations to Verify |
| --- | --- |
| Forbidden record sits between two visible records | Page 0 is complete [101,103], page 1 is complete [104,105]; no post-offset filtering occurs |
| Two users in same tenant, different owners | Each user sees only their own subset; totals are independent |
| Same username in another tenant | alice/t-b sees only [201], total=1; t-a does not leak |
| Same-tenant Admin | Sees row 102 as well, total=5; does not see 201 |
| Zero permitted records | `content=[]`, total=0, totalPages=0, hasNext=false |
| Page beyond the end | `content=[]` while `totalElements` keeps the permitted total |
| Invalid input | Negative page; size 0/negative/over max; non-numeric values return 400 |
| Allowed sorting | Deterministic order with ID tie-breaker; forbid sorting on sensitive fields if policy disallows it |
| Endpoint denial | Anonymous/unauthorized role receives 401 or 403 per security config, returning no data |
| Detail view of unauthorized ID | 403 or 404 per existence-hiding policy; never confirm sensitive IDs via errors |
| Adding/removing permitted fixture rows | Count, totalPages, and hasNext update strictly for the permitted set |
| Field permission changes | Email matches masked format for USER and verbatim for ADMIN if permitted; `internalMemo` always absent |

To verify full pagination against a static fixture, fetch every page and concatenate IDs in order: the result must equal the exact set of visible IDs, **with no duplicates, no gaps, and no unauthorized IDs**. Checking `content.length()==size` alone is insufficient.

## 5. Masking Data: Verify Exact JSON and Exact Policy

Three distinct contract styles exist: **omit field** (property absent), **mask field** (e.g., partial email masking), and **return verbatim** (only with matching permission). When the contract requires omitting a field, JSON containing `"internalMemo": null` differs from the field being completely absent; use an allowlist DTO and assert `doesNotExist()`. When masking is required, assert the exact masked string rather than merely asserting it differs from the raw email; blank values or malformed masks are also bugs.

Place a unique canary in sensitive fields and assert the **entire HTTP body** never contains it. If the API includes nested DTOs, exports, links, metadata, GraphQL resolvers, or error responses, each surface may need its own test. A clean JSON body does not automatically prove application logs, audits, caches, or metrics are safe; review those channels according to system sensitivity.

Even if admins may see emails, that does not imply admins may see `internalMemo`: row-level authorization and field-level authorization are two independent layers. Test every role against the same fixture to catch mapping changes that accidentally widen visibility.

## 6. Page, Slice, and Consistency

`Page<T>` includes `totalElements`/`totalPages` and typically runs a count query over the authorized set. `Slice<T>` mainly indicates whether a next page exists (usually fetching one extra item); **it does not promise an exact total**. Never set `totalElements` to `content.size()` when using `Slice`. If the product needs result counts in the UI, run a proper authorized count.

With continuously changing data, OFFSET pagination can duplicate or skip records between two requests even when authorization queries are right. Test pagination logic against an immutable fixture; if business needs require stable traversal under concurrent writes, consider cursor/keyset pagination or consistent snapshots. Likewise, data and count queries under `READ_COMMITTED` can observe different rows during concurrent writes; `@Transactional(readOnly = true)` does not guarantee snapshot isolation on all databases. Distinguish concurrency drift from missing security predicates.

## 7. Common Mistakes and Acceptance Checklist

| Mistake | Consequence | Detection and Fix |
| --- | --- | --- |
| `findAll(pageable)` then filtering owner/tenant | Underfilled pages, leaked totals | Push permission predicates into query before paging; scope COUNT identically |
| `@PostFilter` on collection after paging | Cannot fix offsets/counts; high cost | Use query-level authorization |
| Count filters only tenant while data filters owner | Total exceeds actual visibility | Test `totalElements` for USER/ADMIN/mallory |
| Frontend hides columns while server returns raw entity | Emails/memos exposed in network payload | Use allowlist DTOs; assert actual HTTP body |
| Fixture contains only valid data | Tests never exercise denial paths | Interleave rows from other owners and tenants |
| Missing page 2, empty page, boundary tests | Broken totalPages/hasNext goes unseen | Test first, subsequent, out-of-range pages, and bad input |
| Taking tenant from query parameter | Cross-tenant access | Derive from server-verified authentication; test tenant spoofing |
| Testing mocked pre-filtered Page | Leaves real WHERE/COUNT untested | Repository + HTTP integration tests on production-compatible DB |

Final checklist: trusted identity and tenant; endpoint permission checked; content has exact IDs and order; count/totalPages/hasNext reflect **the same permitted set**; zero cross-owner/cross-tenant records; pagination input bounded; hidden fields absent from JSON; masked fields have exact expected values; canary never leaks; real tests traverse query, security chain, and serializer. When all these invariants hold, pagination is both functionally accurate and safe against out-of-scope data disclosure.
