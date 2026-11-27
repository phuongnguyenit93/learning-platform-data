# Testing Unauthorized Access and Cross-Tenant Data Leaks

An application built with Spring Data Elasticsearch can return accurate search results and still harbor security flaws if users can view another tenant's data, access documents via guessable IDs, or infer information from aggregations and metadata. These bugs commonly occur when the backend verifies login authentication yet forgets to constrain data scope by user, organization, or business permissions.

**Unauthorized access testing** verifies that unprivileged users cannot read, modify, delete, or infer data outside their granted scope. **Cross-tenant data leak testing** verifies that every access path respects tenant boundaries—including less obvious paths like get-by-ID, count, aggregations, autocomplete, exports, bulk updates, and caches.

This lesson is framed around Spring Data Elasticsearch, Spring Security, and multi-tenant systems. Examples use a `products` index with a `tenantId` field. The goal is building a test suite capable of catching authorization bugs across HTTP, service, query, and Elasticsearch layers while proving both permitted and denied scenarios behave properly.

## 1. Define Security Boundaries Before Writing Tests

Before writing tests, clearly state who can perform which actions on which data. Multi-tenant systems typically involve these concepts:

- **Authentication:** identifying who the caller is.
- **Authorization:** deciding which actions that caller may perform.
- **Tenant isolation:** restricting which tenant's data a caller may see or modify.
- **Object-level authorization:** checking permissions on a specific document.
- **Field-level authorization:** restricting which fields can be read or edited.
- **Function-level authorization:** restricting operations such as search, export, delete, or index administration.

An already logged-in user may still be denied access to a specific product. A user authorized to read products in Tenant A must still not read products belonging to Tenant B.

Example permission matrix:

| Principal | Tenant | Search Products | View Details | Edit | Delete |
|---|---|---:|---:|---:|---:|
| Alice | `tenant-a` | Yes | Within Tenant A | Per role | Per role |
| Bob | `tenant-b` | Yes | Within Tenant B | Per role | Per role |
| Guest | None | No | No | No | No |
| Support | Per support policy | Per policy | Per policy | May be restricted | Not by default |

This matrix serves as the contract for your tests. Never infer authorization guarantees solely from a role name or because a happy-path endpoint test returns HTTP 200.

## 2. Distinguishing 401, 403, and 404

HTTP status codes typically mean:

- **401 Unauthorized:** the request is unauthenticated or credentials are invalid.
- **403 Forbidden:** the caller is authenticated, but lacks permission for the action.
- **404 Not Found:** the resource does not exist, or the application intentionally avoids disclosing whether an out-of-scope resource exists.

For ID-based endpoints, an application may return 404 for both nonexistent IDs and IDs belonging to another tenant. This curbs ID enumeration across tenants. Another application may return 403 to explicitly signal access denial. Both policies can be valid when applied consistently without leaking data.

Tests must assert the chosen policy. Do not write tests loosely accepting either 403 or 404 when product requirements specify exact behavior.

| Scenario | Typically Expected Result |
|---|---|
| No token sent | 401 |
| Expired or invalid-signature token | 401 |
| Authenticated, but missing authority | 403 |
| Nonexistent ID | 404 |
| ID belonging to another tenant | 404 or 403 per policy |
| Valid tenant with required permission | 200 |

## 3. Creating Test Data That Can Detect Cross-Tenant Leaks

A test suite with only one tenant cannot catch cross-tenant bugs. Set up at least two tenants with clearly distinguishable data.

| ID | `tenantId` | `name` | `category` | `status` |
|---|---|---|---|---|
| `p-a-001` | `tenant-a` | Alpha Keyboard | `keyboard` | `ACTIVE` |
| `p-a-002` | `tenant-a` | Alpha Mouse | `mouse` | `ACTIVE` |
| `p-b-001` | `tenant-b` | Beta Keyboard | `keyboard` | `ACTIVE` |
| `p-b-002` | `tenant-b` | Beta Monitor | `monitor` | `ACTIVE` |

Fixtures should include distinct IDs across tenants, recognizable names and SKUs, sensitive fields restricted to specific roles, both `ACTIVE` and `INACTIVE` statuses, overlapping categories across tenants to catch cross-tenant aggregation sums, and overlapping keywords to catch suggestion or autocomplete leaks.

Using distinctive canary values like `BETA-SECRET-9281` makes it easy to spot leaked strings in responses, test logs, or error messages.

## 4. Never Trust Client-Supplied `tenantId`

A classic flaw occurs when an API reads `tenantId` from a query parameter:

~~~http
GET /products?tenantId=tenant-a
~~~

If the backend uses that value directly as a filter, a Tenant A user can change it to `tenant-b` to read out-of-scope data.

Tenant context must be derived from an authenticated principal or trusted authorization mechanism, such as a signature-verified JWT carrying a `tenant_id` claim:

~~~java
String tenantId = jwt.getClaimAsString("tenant_id");
~~~

The controller extracts the JWT principal and passes tenant context to the service:

~~~java
@GetMapping
public Flux<ProductView> search(
        @AuthenticationPrincipal Jwt jwt,
        @RequestParam String q) {

    String tenantId = jwt.getClaimAsString("tenant_id");
    return productService.searchForTenant(tenantId, q);
}
~~~

Never let a client-sent `tenantId` replace the claim. If an admin API accepts a tenant parameter to switch tenants, verify the authority permitting tenant switching and verify the target tenant falls within granted scope.

Tests should send forged `tenantId` values in query parameters, bodies, and headers and prove the backend still uses only the principal's tenant.

## 5. Protecting Queries with Mandatory Filters

For Elasticsearch searches, a tenant filter must be attached to every query capable of returning multi-tenant data.

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "tenantId": "tenant-a"
          }
        },
        {
          "term": {
            "status": "ACTIVE"
          }
        }
      ],
      "must": [
        {
          "match": {
            "name": "keyboard"
          }
        }
      ]
    }
  }
}
~~~

`tenantId` bounds data scope, `status` applies business filtering, `match` searches text within the filtered set, and filter context does not distort relevance scores.

Tenant filters must be applied on the backend—never rely on the frontend appending a filter clause. Never accept arbitrary Query DSL from clients and combine it with a tenant filter using fragile logic; a client-controlled query could introduce `bool.should` or branches altering intended semantics.

Best practice is constructing queries from validated business parameters and always adding the tenant clause inside a shared service/helper.

## 6. Creating a Tenant-Scoped Query Builder Component

You can centralize tenant filter construction so services do not forget to add it. Example using `NativeQuery` and Spring Data Elasticsearch's Java API Client builder:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

public final class TenantQueries {

    private TenantQueries() {
    }

    public static Query activeProducts(String tenantId, String text) {
        return NativeQuery.builder()
                .withQuery(q -> q.bool(b -> b
                        .filter(f -> f.term(t -> t
                                .field("tenantId")
                                .value(tenantId)
                        ))
                        .filter(f -> f.term(t -> t
                                .field("status")
                                .value("ACTIVE")
                        ))
                        .must(m -> m.match(match -> match
                                .field("name")
                                .query(text)
                        ))
                ))
                .build();
    }
}
~~~

The service passes the authenticated `tenantId`:

~~~java
public Flux<Product> searchForTenant(
        String tenantId,
        String text) {

    Query query = TenantQueries.activeProducts(tenantId, text);

    return operations.search(query, Product.class)
            .map(SearchHit::getContent);
}
~~~

Builder syntax may vary across Spring Data Elasticsearch and Java API Client versions. The key point is that the tenant filter is built server-side from the principal and cannot be overridden by clients.

If the system spans multiple indices or document types, provide corresponding query helpers. A shared helper does not mean every query is identical; it guarantees the mandatory tenant condition is placed in the right query tree.

## 7. Never Use `findById` Blindly in Multi-Tenant Systems

The repository method:

~~~java
repository.findById(id)
~~~

typically fetches strictly by document ID across the index. It does not know the current tenant and does not add a `tenantId` filter unless the application explicitly enforces one.

This is a classic source of IDOR (Insecure Direct Object Reference): a user changes the ID in the URL to read another tenant's document.

Vulnerable endpoint example:

~~~java
@GetMapping("/{id}")
public Mono<Product> findById(@PathVariable String id) {
    return repository.findById(id);
}
~~~

A safer approach queries by both tenant and ID, or applies vetted object-level authorization.

Example querying by tenant and `productId`:

~~~java
public Mono<Product> findForTenant(String tenantId, String productId) {
    Query query = NativeQuery.builder()
            .withQuery(q -> q.bool(b -> b
                    .filter(f -> f.term(t -> t
                            .field("tenantId")
                            .value(tenantId)
                    ))
                    .filter(f -> f.term(t -> t
                            .field("productId")
                            .value(productId)
                    ))
            ))
            .withMaxResults(1)
            .build();

    return operations.search(query, Product.class)
            .next()
            .map(SearchHit::getContent);
}
~~~

If `productId` is Elasticsearch's `_id`, use an `ids` query combined with the tenant filter instead of storing a duplicate `productId` field. Check your version's query builder API.

Another option is encoding the tenant inside structured IDs, though never treat unguessable IDs as authorization. Random IDs slow down enumeration, yet the backend must still verify permissions.

## 8. Testing IDOR by Swapping IDs

An IDOR test needs two principals from two different tenants attempting cross-tenant access.

Scenario:

1. Create `p-a-001` owned by `tenant-a`.
2. Create `p-b-001` owned by `tenant-b`.
3. Call the detail endpoint with `tenant-a` JWT and ID `p-a-001`: must succeed.
4. Call the detail endpoint with `tenant-a` JWT and ID `p-b-001`: must be denied per policy.
5. Call the endpoint with a nonexistent ID: must match the 404 policy.
6. Assert the response contains no fields from `p-b-001`.

Tests must assert more than just a 403/404 status. Verify the body contains no name, SKU, `tenantId`, price, address, or metadata from the out-of-scope document.

Example test using `WebTestClient`:

~~~java
webTestClient
        .mutateWith(mockJwt().jwt(jwt -> jwt
                .subject("alice")
                .claim("tenant_id", "tenant-a")
                .claim("scope", "products.read")
        ))
        .get()
        .uri("/products/p-b-001")
        .exchange()
        .expectStatus().isNotFound()
        .expectBody()
        .jsonPath("$").doesNotExist();
~~~

This snippet illustrates test JWT setup; exact authority mappings and response bodies depend on your application. If endpoints return `ProblemDetail`, assert the body carries only a generic error code and no source or internal info.

## 9. Testing That Searches Return No Other Tenant's Data

Search tests should verify both returned IDs and aggregate metadata.

~~~java
@Test
void searchReturnsOnlyProductsFromAuthenticatedTenant() {
    StepVerifier.create(
            service.searchForTenant("tenant-a", "keyboard")
    )
    .expectNextMatches(product ->
            "p-a-001".equals(product.getId())
    )
    .verifyComplete();
}
~~~

Run this test against indexed and refreshed test fixtures. When searches can return multiple items, collect the small test result set and assert the exact set of IDs rather than asserting only that at least one hit exists.

Additional assertions:

- Tenant A receives no Tenant B products despite matching keywords.
- Tenant A receives no Tenant B products despite matching categories.
- Tenant A receives no `INACTIVE` products if the role or API restricts to `ACTIVE`.
- Results contain no other `tenantId`.
- `totalHits` counts only documents belonging to the current tenant.
- Sorting and pagination never drop the tenant filter.

## 10. Prevent Counts and Aggregations from Leaking Cross-Tenant Data

An endpoint might omit documents yet still leak document counts from other tenants.

For instance, search hits are filtered by tenant, while an aggregation runs in an unfiltered branch. Tenant A users could then see system-wide product counts or category distributions.

Outputs to verify:

- `totalHits` and total relation.
- Count APIs.
- `terms` aggregations by category/status/brand.
- Min/max/avg prices.
- Cardinality by customer or SKU.
- Date histograms by day.
- Geo aggregations and centroids.
- Suggestions or facet counts.
- Dashboard summary statistics.

Example proper aggregation inside the same tenant-filtered query:

~~~http
POST /products/_search
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "tenantId": "tenant-a"
          }
        }
      ]
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

Tests should create a category existing only in Tenant B and verify that bucket does not appear in Tenant A's response. Also assert bucket counts and `doc_count`, because hiding only bucket names can still leak totals.

## 11. Testing Autocomplete, Suggestions, and Highlights

Auxiliary search features are frequently overlooked in authorization tests. A suggest request can draw recommendations from the index-wide term dictionary, rather than automatically inheriting the main query's tenant filter as expected.

Cases to test:

- Autocomplete returning product names from another tenant.
- Term/phrase suggesters recommending secret SKUs or names from another tenant.
- Highlights returning text snippets containing out-of-scope data.
- Search-as-you-type leaking suggestion counts or scores that imply cross-tenant data.
- Completion suggesters using an index-wide field without tenant partitioning.

If a suggester does not support tenant filtering as required or shares a dictionary, redesign the index/field or validation layer accordingly. Never assume adding a filter to the main search query automatically scopes every suggestion feature.

Tests should seed a secret string existing solely in Tenant B, call autocomplete as Tenant A, and verify that string appears in no option, highlight, or metadata.

## 12. Testing Get, Multi-Get, Exists, and Count

Beyond search, test every ID-lookup and counting API:

- Repository `findById`.
- `ElasticsearchOperations` `get`.
- Java API Client `get`.
- `MultiGet`.
- `Exists`.
- `Count`.
- Delete-by-query or update-by-query if endpoints expose them.
- `ids` search queries.
- Scroll, `search_after`, and Point in Time.

An endpoint might guard search while forgetting `multi-get` or `exists`. For example, returning `true` for `exists` on another tenant's ID leaks document existence.

With `multi-get`, verify permissions or query with tenant scoping for every ID. Never accept a client-supplied ID list and fire `mget` directly against a shared index without scoping.

Tests should pass a mixed ID list: one ID from the current tenant, one from another tenant, and one nonexistent ID. Verify responses disclose no content and do not distinguish between the two unauthorized IDs against policy.

## 13. Testing Authorization on Create, Update, and Delete

Cross-tenant leaks are not limited to reads. Users can alter another tenant's documents if the backend uses IDs without tenant constraints.

Operations to test:

- Creating a document with a forged `tenantId`.
- Updating an out-of-tenant document.
- Deleting an out-of-tenant document.
- Scripted updates.
- Upserts with an ID belonging to another tenant.
- Bulk index/create/update/delete.
- Update-by-query and delete-by-query.
- Reindexing or exports if endpoints expose them.
- Modifying the owner/`tenantId` of a document.

On create, `tenantId` must be set server-side from the principal or verified admin privileges. Never allow clients to create documents in another tenant simply by supplying `tenantId` in JSON.

On update, queries must require both ID and tenant. Never perform plain ID updates after relying only on frontend checks.

On delete, follow the exact same rule: deletions apply strictly within the permitted tenant scope.

## 14. Preventing Clients from Moving Documents to Another Tenant

A dangerous payload:

~~~json
{
  "name": "Updated Product",
  "tenantId": "tenant-b"
}
~~~

If an entity is bound straight from the request and saved, a client can swap `tenantId`. That creates a cross-tenant or unauthorized ownership-transfer vulnerability.

Use a request DTO omitting `tenantId`:

~~~java
public record UpdateProductRequest(
        String name,
        BigDecimal price,
        String status
) {
}
~~~

The service loads the document within the current tenant, updates only allowed fields, and preserves `tenantId`:

~~~java
public Mono<Product> update(
        String tenantId,
        String productId,
        UpdateProductRequest request) {

    return findForTenant(tenantId, productId)
            .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(productId)
            ))
            .map(product -> {
                product.setName(request.name());
                product.setPrice(request.price());
                product.setStatus(request.status());
                return product;
            })
            .flatMap(repository::save);
}
~~~

This snippet illustrates the flow. Production code needs validation, per-field update authorization, and protection of system attributes. If using partial updates, also exclude `tenantId` from writable client fields.

Write a test sending a different `tenantId` in the body and assert the tenant value in Elasticsearch remains unchanged.

## 15. Bulk APIs Must Enforce Tenant Control Per Item

A bulk request can contain multiple actions. If the backend checks permissions once at the endpoint without validating every item, a single request can write across tenants.

~~~text
Bulk request:
  item 1 -> tenant-a / product A
  item 2 -> tenant-b / product B
  item 3 -> tenant-a / product C
~~~

If the principal belongs to `tenant-a`, item 2 must be rejected or excluded per API contract. Never write item 2 just because the other two items are valid.

One approach sets the tenant from the principal on each document before building bulk actions and rejects payloads with conflicting `tenantId` values. For updates/deletes, queries/actions must carry tenant scope. For multi-tenant admin bulk imports, verify permissions on every target tenant.

Bulk tests should verify partial handling: items in the current tenant succeed, out-of-tenant items are rejected, and responses reveal no source data from unauthorized documents.

## 16. Field-Level Security and Sensitive Data

A user may be allowed to read a `Product` yet forbidden from seeing cost prices, supplier details, or customer notes.

~~~json
{
  "tenantId": "tenant-a",
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "sellingPrice": 120,
  "costPrice": 72,
  "supplierContract": "SUPPLIER-SECRET",
  "customerNotes": "Confidential"
}
~~~

Public APIs might return only `sku`, `name`, and `sellingPrice`. Internal endpoints for finance roles may view `costPrice`. Never return the entire entity hoping the frontend hides sensitive fields.

Protection layers:

- Response DTOs containing only permitted fields.
- Source filtering in queries to reduce sensitive data fetched from Elasticsearch.
- Service-layer permission checks before constructing responses.
- Elasticsearch field-level security (if supported by edition and configuration) as defense-in-depth.
- Keeping sensitive fields out of logs and error responses.

Source filtering does not replace authorization. If another endpoint or code path returns the full entity, data still leaks.

Tests should verify lower-privileged roles never see sensitive fields in JSON, even when those fields exist in `_source` and mappings. Also test export, detail, search, aggregation, and cache endpoints.

## 17. Document-Level Security in Elasticsearch

Elasticsearch supports **document-level security (DLS)** and **field-level security (FLS)** in eligible editions/configurations. DLS restricts which documents a user or API key can access; FLS restricts which fields can be read.

This provides cluster-side protection, useful when multiple applications or users connect directly to Elasticsearch using separate credentials. Keep in mind:

- Confirm feature availability in your deployed license/edition.
- Test with real roles and API keys.
- Test DLS queries across multiple tenants.
- Test FLS across search, get, and related APIs.
- Never assume a shared backend credential automatically applies DLS per end user.

If the backend uses one service credential permitted to read all tenants, Elasticsearch sees the service identity. The application must enforce per-tenant authorization in the backend for every request. DLS only enforces boundaries for the principal/role Elasticsearch actually receives.

## 18. Prevent Aliases or Index Routing from Breaking Tenant Isolation

Some systems isolate tenants using dedicated indices; others share an index with a `tenantId` field. Both models need tests.

For dedicated indices:

- Verify Tenant A cannot select Tenant B's alias/index.
- Verify aliases point to the intended backing indices.
- Verify rollovers and migrations never place data into the wrong tenant.
- Never accept arbitrary index names from clients.
- Verify credential index privileges.

For shared indices:

- Every query includes the tenant filter.
- Every get/update/delete scopes by tenant.
- Aggregations, suggestions, and exports also scope by tenant.
- Mappings and templates stay consistent.
- Bulk operations validate every item.

Tenant routing can improve data locality and performance, yet **routing is not an authorization mechanism**. Clients might try sending another routing value if permitted; the server must still validate tenant and permissions.

## 19. Testing Caches to Avoid Serving Wrong-Tenant Data

A query with a proper tenant filter can still leak data if the cache key omits the tenant or permission scope.

~~~text
product-search:keyboard
~~~

Tenant A searches `keyboard` and caches the response. Tenant B searches `keyboard` and receives A's response if the key depends only on query text.

Cache keys must include the tenant and permission-affecting attributes:

~~~text
product-search:tenant-a:keyboard:role-catalog-reader
~~~

Check more than search response caches. Audit ID caches, count and aggregation caches, autocomplete/suggest caches, export caches, in-memory application caches, CDN/reverse proxy caches, and role/permission versions in cache keys when permissions change.

Tests should call the same URL and query with two different tenant JWTs. Assert Tenant B's response contains no cached data from Tenant A, verifying both cache hit and cache miss paths.

## 20. Pagination, Cursors, and Point in Time

Pagination can leak data if cursors or search tokens can be reused across tenants.

When using `search_after` or Point in Time:

- Cursors must bind to the tenant and query context.
- Reject client-tampered cursors if they encode internal state.
- Verify tenant filters are applied on every page.
- Verify Tenant A's cursor cannot be used with Tenant B's JWT.
- Bound PIT lifetimes.
- Close or clear PITs when finished.
- Never embed sensitive data in plaintext tokens passed via URLs.

You can cryptographically sign cursors or store cursor state server-side. Either way, the backend must verify the current request's tenant matches the tenant that created the cursor.

Critical test: obtain a cursor as Tenant A, then submit that cursor using Tenant B's principal. The request must be rejected or restarted within Tenant B's scope per policy—never continue paging Tenant A's data.

## 21. Exports, Scroll, and Background Jobs

Export endpoints often return large datasets and may rely on `scroll` or `search_after`. If only the search endpoint is protected, exports become a leak path.

Verify:

- Dedicated export permissions.
- Tenant filters on every batch.
- Record count and runtime limits.
- Generated files carry explicit tenant scope.
- Download links cannot be used by other tenants.
- Object storage keys and file read permissions.
- Background jobs preserve verified tenant context.
- Job retries never switch to the wrong credential or tenant.
- Temporary files and old exports are deleted per retention.

Background jobs lack an HTTP principal. Persist the verified tenant ID alongside the job request and verify permissions when creating the job. Never pull tenants from an unvalidated message field if producers are untrusted.

Test downloading files as another tenant's principal, guessing job IDs, and accessing export URLs across tenants.

## 22. Verify Errors and Logs Leak No Data

Even when an API returns 403, error payloads can disclose source or index details:

~~~json
{
  "error": "Access denied for product Beta Monitor, supplier SUPPLIER-SECRET, tenant tenant-b"
}
~~~

This message reveals the name and supplier of an unauthorized document.

Public responses should use generic messages:

~~~json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Resource not found"
}
~~~

Internal logs also need controls. Avoid logging full request bodies, source documents, tokens, sensitive queries, or error reasons containing source fragments unless strictly needed.

Tests should check:

- Responses contain no names or fields from other tenants.
- Error bodies return no Elasticsearch stack traces.
- Logs contain no access tokens.
- Logs contain no sensitive source documents.
- Metric labels omit high-cardinality tenant IDs or user IDs unless necessary.
- Traces do not record sensitive query parameters in plaintext.

## 23. Testing Permissions in Spring Security

Endpoint authorization can use authorities or method security. Example:

~~~java
@PreAuthorize("hasAuthority('products:read')")
public Flux<Product> searchForTenant(String tenantId, String text) {
    // Tenant filter must still be applied in the query.
}
~~~

Method security checks functional permissions. It does not automatically restrict documents by tenant. Both layers must be present:

1. Authority check: is the principal allowed to search products?
2. Tenant filter/object authorization: which tenant may the principal search?

Having `products:read` does not imply permission to read all tenants.

Tests should cover:

- Anonymous callers cannot access endpoints.
- Authenticated callers missing the authority are denied.
- Callers with the authority and `tenant-a` receive only `tenant-a` data.
- Callers with the authority passing `tenant-b` in a query still cannot read `tenant-b`.
- Admins with cross-tenant access operate only through dedicated administrative endpoints/functions.

## 24. WebFlux Test Examples with JWT

With WebFlux and Spring Security Test, mock JWTs let you test controllers cleanly:

~~~java
@Test
void tenantASeesOnlyItsOwnProducts() {
    webTestClient
            .mutateWith(mockJwt().jwt(jwt -> jwt
                    .subject("alice")
                    .claim("tenant_id", "tenant-a")
            ))
            .get()
            .uri("/products?q=keyboard")
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(ProductView.class)
            .value(products -> {
                assertThat(products)
                        .extracting(ProductView::getId)
                        .containsExactly("p-a-001");
            });
}
~~~

This test assumes fixtures contain one keyboard product for Tenant A and a similar one for Tenant B. Import the mock JWT configuration matching your Spring Security Test version.

Testing tenant spoofing:

~~~java
@Test
void queryParameterCannotSwitchTenant() {
    webTestClient
            .mutateWith(mockJwt().jwt(jwt -> jwt
                    .subject("alice")
                    .claim("tenant_id", "tenant-a")
            ))
            .get()
            .uri("/products?tenantId=tenant-b")
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(ProductView.class)
            .value(products -> assertThat(products)
                    .allSatisfy(product ->
                            assertThat(product.getTenantId())
                                    .isEqualTo("tenant-a")
                    ));
}
~~~

If the response DTO omits `tenantId`, assert the ID list or an identifying field. Tests must prove the token's tenant is the authoritative source.

## 25. Example Test Preventing Modification of Another Tenant's Document

An update test must check both the response and the persisted state afterward:

~~~java
@Test
void tenantACannotUpdateTenantBProduct() {
    webTestClient
            .mutateWith(mockJwt().jwt(jwt -> jwt
                    .subject("alice")
                    .claim("tenant_id", "tenant-a")
                    .claim("scope", "products.write")
            ))
            .put()
            .uri("/products/p-b-001")
            .bodyValue(new UpdateProductRequest(
                    "Compromised Name",
                    new BigDecimal("1.00"),
                    "ACTIVE"
            ))
            .exchange()
            .expectStatus().isNotFound();

    StepVerifier.create(
            productService.findForTenant("tenant-b", "p-b-001")
    )
    .expectNextMatches(product ->
            "Beta Keyboard".equals(product.getName())
    )
    .verifyComplete();
}
~~~

This test confirms a Tenant A user cannot modify Tenant B's document and the original source stays intact. If policy returns 403, adjust the status expectation to match your API contract.

Never check status alone. A bug might update the document first and only return an error afterward because the permission check ran after the write.

## 26. Integration Testing with Real Elasticsearch

Mocked repositories verify service composition, yet cannot confirm the final Query DSL carries the right tenant filter. To verify data boundaries, write integration tests against an Elasticsearch instance matching your project's version.

An integration suite should:

1. Create the index and mappings.
2. Index Tenant A and Tenant B fixtures.
3. Refresh the index or wait for the appropriate refresh cycle.
4. Invoke the service through read and write APIs.
5. Check search results and `totalHits`.
6. Check aggregations and suggestions.
7. Check get-by-ID and multi-get.
8. Attempt cross-tenant updates/deletes.
9. Inspect source after denied operations.
10. Clean up test indices or fixtures afterward.

Testcontainers can spin up Elasticsearch for integration tests if the image and version match cleanly. Never use mocks to assume mapping, alias, aggregation, or cluster security plugin behavior.

## 27. Testing Matrix by Access Surface

A helpful checklist maps every endpoint/API against required tenant boundary tests:

| Surface | Cross-Tenant Read Test | Cross-Tenant Write Test |
|---|---:|---:|
| Search/list | Yes | — |
| Get-by-ID | Yes | — |
| Multi-get | Yes | — |
| Exists/count | Yes | — |
| Aggregations/facets | Yes | — |
| Suggest/autocomplete | Yes | — |
| Highlight/inner hits | Yes | — |
| Scroll/`search_after`/PIT | Yes | — |
| Export/download | Yes | — |
| Cache | Yes | — |
| Create | — | Yes |
| Update/partial update | — | Yes |
| Upsert | — | Yes |
| Delete | — | Yes |
| Bulk operations | Possible | Yes |
| Update-by-query/delete-by-query | Possible | Yes |
| Reindex/admin jobs | Possible | Yes |

Not every application exposes all of these APIs. Check off every surface that exists, and do not skip an API simply because it is absent from the main UI.

## 28. Verifying Queries and Testing Across Layers

A security test suite should span multiple layers:

- **Unit tests for tenant resolvers:** verify tenants come from authenticated principals, never arbitrary request fields.
- **Unit tests for query builders:** verify every business query includes the mandatory tenant filter.
- **Service tests:** verify ID, tenant, role, and field permissions are enforced properly.
- **Controller/security tests:** verify 401/403/404 and leak-free responses.
- **Elasticsearch integration tests:** verify real Query DSL, mappings, aggregations, and bulk semantics.
- **End-to-end tests:** verify the complete chain from token to response, cache, and export.

Never verify only the query builder's JSON string. One query builder might be right while another service calls `repository.findById` bypassing the helper. Audit actual call paths and consider code reviews/static analysis to flag direct Elasticsearch API usage outside controlled layers.

## 29. Common Security Testing Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Tests only check user login | Confused authentication with authorization | Test authorities and tenant scope separately |
| Search is safe, yet detail view leaks | `findById` omits tenant scope | Query by both tenant and ID |
| Hits are right, yet `totalHits` is wrong | Count/aggregations lack the same filter | Apply tenant filter across the entire request |
| Response has no docs, yet suggest leaks names | Suggest uses index-wide dictionary | Design tenant-scoped suggestions and test separately |
| User edits `tenantId` in body | Request bound directly to entity | Use DTOs and assign tenant server-side |
| Bulk writes across tenants | Individual items not validated | Assign tenant server-side and check every action |
| Update denied, yet data changed | Permission check ran after write | Authorize first and scope the query |
| Cache returns another tenant's data | Cache key lacked tenant/role | Include tenant and permissions in cache keys |
| Cursor works across tenants | Cursor unbound from query context | Sign or store cursors and verify tenant |
| Exports contain cross-tenant data | Export path skipped filters | Enforce authorization per batch |
| Error responses leak source | Returned raw Elasticsearch exceptions | Standardize error responses |
| Mocks pass while prod leaks data | Mocks did not test real Query DSL | Add Elasticsearch integration tests |

## 30. Investigation Workflow When a Leak Is Found

When tests catch cross-tenant data appearing, follow these steps:

1. Capture the request, test principal, tenant claim, and masked response.
2. Identify the endpoint or operation producing the response.
3. Inspect the actual Query DSL sent to Elasticsearch.
4. Confirm whether the tenant filter came from the principal or client input.
5. Check whether repositories, `Operations`, Java API Client, or bulk paths bypassed the service.
6. Check aggregations, suggestions, highlights, caches, exports, and pagination.
7. Verify via integration tests whether data was misread or miswritten.
8. Fix the shared control point so no code path bypasses tenant scope.
9. Add a regression test reproducing the exact flaw.
10. Check logs, caches, export files, and copies that might have retained cross-tenant data.
11. Assess impact scope and follow organizational incident response procedures.

During debugging, use test fixtures and synthetic data. Never copy sensitive production data into logs or test artifacts without appropriate handling.

## 31. Design Principles to Prevent Cross-Tenant Data Leaks

- Derive tenant from an authenticated principal or authorized context.
- Never trust `tenantId` in query parameters, paths, or bodies without permission checks.
- Enforce tenant filters on the backend for every shared-index query.
- Never use `findById`/`get`/`mget`/`exists` without object-level authorization.
- Protect counts, aggregations, suggestions, highlights, exports, and pagination.
- Assign `tenantId` server-side when creating documents.
- Never let clients change `tenantId` on updates.
- Scope updates/deletes/upserts/bulk operations by tenant.
- Separate function-level and tenant-level permissions.
- Use DTOs and field-level authorization for sensitive data.
- Treat DLS/FLS as defense-in-depth when supported and properly configured.
- Never treat unguessable IDs or routing as authorization.
- Include tenant and permissions in cache keys.
- Bind cursors/PITs to tenant and query context.
- Never return raw Elasticsearch errors or sources in responses.
- Test with at least two tenants and distinguishable canary data.
- Combine unit, service, security, integration, and end-to-end tests.
- Test both permitted and denied scenarios.
- Verify persisted state remains unchanged after unauthorized writes.

Security testing for Spring Data Elasticsearch must prove users access only the data and operations within their granted scope. Endpoint authentication and role checks are not enough: tenant scope must hold across search, get-by-ID, counts, aggregations, suggestions, caches, exports, and all write paths. Multi-tenant suites should exercise IDOR, spoofed tenants, cross-tenant bulk items, sensitive fields, and metadata side channels while verifying data stays untouched after unauthorized writes. Combining tests across Spring Security, service/query builders, and Elasticsearch integration catches cross-tenant leaks before they reach production.
