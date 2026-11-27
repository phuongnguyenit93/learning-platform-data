# Routing Does Not Replace Access Control

Elasticsearch uses routing to decide which shard stores a document and which shards a search request should target. In multi-tenant applications, routing is often used to colocate a tenant's data, reduce the number of shards searched, and improve performance.

However, **routing is not an authorization mechanism**. Routing only directs requests to shards. It does not verify whether the caller has permission to read, update, or delete a document; nor does it automatically filter documents on a shard by tenant. If an application treats routing as proof that a user is allowed to access data, a request carrying a user-chosen routing value can cross tenant boundaries.

This lesson distinguishes routing from authorization, explains how Elasticsearch routes documents, how to pass routing in Spring Data Elasticsearch, how to combine routing with tenant filters and access control, and what test cases are needed for multi-tenant systems.

## 1. What Problem Does Routing Solve?

Elasticsearch divides an index into primary shards. Every document is stored on one shard. When custom routing is not specified, Elasticsearch uses the document ID as the default routing value to determine the shard.

With custom routing, the application provides a value such as tenant ID, customer ID, or account ID. Elasticsearch uses that value to select a shard for the document.

For example, an order management system:

- Tenant A has thousands of orders.
- Tenant B has thousands of different orders.
- Users frequently search orders within their own tenant.
- The application wants documents from the same tenant routed consistently so tenant queries can narrow shard scope.

Routing helps reduce the number of searched shards when queries supply the matching routing value. It also helps get, update, or delete operations locate the document on the shard where it was stored.

Routing is useful for data distribution and retrieval. It does not decide who is permitted to perform an operation.

## 2. How Elasticsearch Chooses a Shard

When indexing a document, Elasticsearch computes the shard from the routing value and the index's primary shard count. Conceptually:

~~~text
routing value
      |
      v
    hash
      |
      v
primary shard count
      |
      v
 target shard
~~~

If no routing is passed, the document ID is used as the default value. If custom routing is passed, the custom value determines the shard.

For example, two documents with the same routing value `tenant-42` are routed consistently to the same shard within the same index:

~~~http
POST /orders/_doc/O-100?routing=tenant-42
{
  "orderId": "O-100",
  "tenantId": "tenant-42",
  "status": "OPEN"
}
~~~

~~~http
POST /orders/_doc/O-101?routing=tenant-42
{
  "orderId": "O-101",
  "tenantId": "tenant-42",
  "status": "PAID"
}
~~~

If a document is indexed with custom routing, subsequent reads or updates by ID normally must pass the exact same routing value to find the right shard.

### Routing does not create a separate shard per tenant

Two different routing values can hash to the same shard. A tenant can also share a shard with many other tenants.

For example:

~~~text
Primary shard 0: tenant-A, tenant-B, tenant-C
Primary shard 1: tenant-D, tenant-E
Primary shard 2: tenant-F, tenant-G, tenant-H
~~~

This diagram only illustrates how multiple routing values can select the same shard. It does not represent a security boundary.

If a search request specifies routing for `tenant-A` and shard 0 is selected, Elasticsearch can still match documents belonging to `tenant-B` or `tenant-C` on shard 0 unless the query filters by tenant. Routing narrows which shards participate; it does not automatically insert a tenant condition into the Query DSL.

## 3. Routing and Authorization Are Two Separate Responsibilities

Authorization answers the question: is the current user or service allowed to perform this action on this resource?

Routing answers the question: which shard holds the document and which shard should the search request visit?

| Aspect | Routing | Authorization |
|---|---|---|
| Goal | Route to shard | Allow or deny action |
| Input | Routing value | Identity, role, permission, resource |
| Identity verification | No | Based on verified authentication |
| Tenant membership check | No | Must be enforced by authorization layer |
| Filtering documents by tenant | Not automatic | Requires matching policy/filter |
| Prevents unauthorized access | No | Yes |
| Primary impact | Shard scope and performance | Data and operation security |

A request with a valid routing value can still come from an unauthorized user. Elasticsearch does not infer permissions from the presence of a routing value.

Never make the following assumptions:

- A user knowing a tenant ID means they belong to that tenant.
- A request reaching only one shard means all documents on that shard belong to the user.
- A routing value matching a document ID means the caller has permission.
- An index with custom routing automatically isolates data.
- A repository method taking a `routing` parameter is enough to protect a tenant.

## 4. Why Search Routing Is Not a Tenant Filter

Suppose `tenant-A` and `tenant-B` both have documents on shard 0. The application sends:

~~~http
GET /orders/_search?routing=tenant-A
{
  "query": {
    "match_all": {}
  }
}
~~~

The request narrows the search to the shard chosen by `tenant-A`. Yet that shard still holds `tenant-B` documents if `tenant-B`'s routing value also hashes to shard 0.

Therefore, the search needs an explicit tenant condition:

~~~http
GET /orders/_search?routing=tenant-A
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "tenantId": "tenant-A"
          }
        }
      ]
    }
  }
}
~~~

Both parts have distinct roles:

- `routing` narrows the shards to search.
- The `tenantId` filter narrows which documents may appear in the results for that tenant.

The routing value and `tenantId` should be consistent, yet they remain separate concepts. Routing is Elasticsearch routing metadata; `tenantId` in `_source` is business data that can be queried and verified.

### Never omit the tenant filter just because routing is passed

Even if current test data happens to place `tenant-A` and `tenant-B` on two different shards, that is no long-term guarantee. Primary shard counts, routing strategies, new data, and index settings can place tenants on the same shard.

A change in shard count or routing scheme can invalidate old assumptions. The tenant condition must always be present in queries per application policy, regardless of whether routing is passed.

## 5. Multi-Tenant Data Design

A multi-tenant document should contain an explicit tenant identifier in its source:

~~~json
{
  "orderId": "O-100",
  "tenantId": "tenant-A",
  "customerId": "C-200",
  "status": "OPEN",
  "total": 125.50
}
~~~

When indexing a document:

- The application determines the tenant from the authenticated identity.
- The application sets `tenantId` on the document.
- The application uses the same tenant identifier as the routing value if the routing strategy selects by tenant.
- Never accept `tenantId` or routing values from the request body as trusted values.

`tenantId` in the source supports filtering, auditing, and reconciliation. It also helps detect mismatches when routing metadata and source data disagree.

### Determining document IDs

With custom routing, the same document ID can be stored on different shards if separate index requests use different routing values. Elasticsearch enforces ID uniqueness per shard, not as a business-level unique constraint across arbitrary routing values.

Hence, multi-tenant systems need a clear ID rule:

- Use an index-wide globally unique ID; or
- Combine tenant ID and business ID to create a tenant-unique document ID.

Either way, the routing value must stay stable for the document's lifecycle. If the same record is indexed with two different routing values, two copies can end up on different shards instead of overwriting the old one.

## 6. Authenticating Users and Resolving Tenant from a Trusted Source

The application should resolve the tenant after authentication succeeds. Tenant context can come from:

- Verified claims in an access token.
- Membership loaded from an identity management system.
- Context built after checking user permissions.
- Verified and scoped service-to-service identity.

Never blindly trust values from:

- A `tenantId` query parameter.
- An `X-Tenant-ID` HTTP header.
- The request body.
- Caller-chosen path variables.
- Frontend-sent routing values.

These values can be used as requested target hints, but the server must verify the caller holds membership or permission for them before acting.

The processing flow should look like:

~~~text
HTTP request
     |
     v
Authenticate identity
     |
     v
Resolve trusted principal / tenant membership
     |
     v
Authorize requested action
     |
     v
Derive tenantId on server
     |
     +-----------------------+
     |                       |
     v                       v
Add tenant query filter   Set routing value
     |                       |
     +-----------+-----------+
                 |
                 v
       Elasticsearch request
                 |
                 v
       Return authorized result
~~~

The routing value is derived from the verified tenant context, never used as proof to construct the tenant context.

## 7. Integrating with Spring Security

In a Spring application, services can receive the tenant ID from a context component backed by the authenticated principal.

Example small abstraction:

~~~java
public interface CurrentTenant {

    String requireTenantId();
}
~~~

An implementation can read claims or the principal verified by Spring Security. Extraction details depend on the application's authentication model.

Services never accept an arbitrary tenant ID from callers:

~~~java
@Service
public class OrderService {

    private final CurrentTenant currentTenant;
    private final OrderRepository repository;

    public OrderService(
            CurrentTenant currentTenant,
            OrderRepository repository) {
        this.currentTenant = currentTenant;
        this.repository = repository;
    }

    public List<Order> findMyOrders() {
        String tenantId = currentTenant.requireTenantId();
        return repository.findByTenantId(tenantId);
    }
}
~~~

In this example, the tenant ID comes from server-side context. The repository must still apply the tenant filter. When verifying access to a specific order, the service must confirm the order belongs to the principal's tenant before acting.

### Method security

Method security can restrict who may call a service method:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

~~~java
@Service
public class OrderAdministrationService {

    @PreAuthorize("hasAuthority('orders:read')")
    public List<Order> listOrdersForCurrentTenant() {
        // Resolve tenant from authenticated context
        // and query only that tenant's documents.
        return List.of();
    }
}
~~~

Authorities like `orders:read` are just examples. Actual permissions must reflect application policy. Checking a functional authority alone is not enough to identify which tenant owns a resource; enforce tenant scope in the same flow.

Never use a coarse permission annotation as an excuse to drop tenant filters from queries.

## 8. Enforcing Tenant Filters in Repositories

Repository methods should make tenant scope explicit. With derived queries, you can write:

~~~java
public interface OrderRepository
        extends ElasticsearchRepository<Order, String> {

    List<Order> findByTenantIdAndStatus(
        String tenantId,
        String status
    );

    Optional<Order> findByIdAndTenantId(
        String id,
        String tenantId
    );
}
~~~

The service passes the tenant ID from trusted context:

~~~java
public List<Order> findOpenOrders() {
    String tenantId = currentTenant.requireTenantId();

    return repository.findByTenantIdAndStatus(
        tenantId,
        "OPEN"
    );
}
~~~

Do not expose an endpoint calling `repository.findAll()` for tenant users without a clear policy. Generic CRUD repositories do not automatically know the current tenant.

For lookups by ID, use a query combining both ID and tenant. Never assume hard-to-guess IDs act as authorization.

### `@Query` must also include the tenant condition

Example static JSON query:

~~~java
@Query("""
{
  "bool": {
    "filter": [
      { "term": { "tenantId": "?0" } },
      { "term": { "status": "?1" } }
    ]
  }
}
""")
List<Order> findByTenantAndStatus(
    String tenantId,
    String status
);
~~~

Callers must still pass a tenant ID from verified context. Never let clients pass an arbitrary tenant ID straight into this method without authorization.

If many queries need a tenant filter, consider a custom repository fragment or shared query builder to reduce the risk of omitting the condition. Still, helpers cannot protect separate paths like raw CRUD, direct clients, or admin endpoints if they bypass the helper.

## 9. Combining Routing with `NativeQuery`

When using `NativeQuery`, construct a `bool` query with the tenant filter. At the same time, if your API version supports routing metadata on search requests, pass the routing value to narrow shards.

Example Query DSL structure:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "tenantId": "tenant-A"
          }
        },
        {
          "term": {
            "status": "OPEN"
          }
        }
      ]
    }
  }
}
~~~

In Spring Data code, the query part can be built using the Java API Client builder:

~~~java
Query tenantQuery = Query.of(q -> q.bool(b -> b
    .filter(f -> f.term(t -> t
        .field("tenantId")
        .value(tenantId)
    ))
    .filter(f -> f.term(t -> t
        .field("status")
        .value("OPEN")
    ))
));
~~~

The `Query` object above expresses the filter criteria. Routing is passed separately via request metadata or query options supported by your Spring Data Elasticsearch version. Builder method names and overloads vary across release trains; inspect the actual API rather than assuming a tenant filter produces routing automatically.

If using the Elasticsearch Java API Client directly, search requests can take `routing` explicitly:

~~~java
SearchResponse<Order> response =
    elasticsearchClient.search(s -> s
        .index("orders")
        .routing(tenantId)
        .query(q -> q.bool(b -> b
            .filter(f -> f.term(t -> t
                .field("tenantId")
                .value(tenantId)
            ))
            .filter(f -> f.term(t -> t
                .field("status")
                .value("OPEN")
            ))
        )),
        Order.class
    );
~~~

Here `tenantId` must be derived server-side from verified context. Never forward a caller-controlled routing value directly.

## 10. Routing During Index, Get, Update, and Delete

Routing must stay consistent throughout the document lifecycle.

### Index

When writing a document, pass the server-determined routing value:

~~~java
IndexResponse response = elasticsearchClient.index(i -> i
    .index("orders")
    .id(order.getId())
    .routing(tenantId)
    .document(order)
);
~~~

The entity source should hold the matching `tenantId`. Before indexing, ensure the entity does not carry a caller-forged `tenantId`.

### Get

When fetching by ID, routing must match the value used at index time:

~~~java
GetResponse<Order> response = elasticsearchClient.get(g -> g
    .index("orders")
    .id(orderId)
    .routing(tenantId),
    Order.class
);
~~~

After fetching the document, the service must still verify tenant ownership per policy. Never treat routing as a permission check.

### Update

Updating by ID needs the right routing:

~~~java
UpdateResponse<Order> response =
    elasticsearchClient.update(u -> u
        .index("orders")
        .id(orderId)
        .routing(tenantId)
        .doc(Map.of("status", "PAID")),
        Order.class
    );
~~~

If business rules require a tenant condition, verify ownership before updating or use a query-based update flow with an explicit tenant condition. Never let callers specify routing and update documents directly.

### Delete

Delete also requires the right routing:

~~~java
DeleteResponse response = elasticsearchClient.delete(d -> d
    .index("orders")
    .id(orderId)
    .routing(tenantId)
);
~~~

Before deleting, the service must verify the caller has permission to delete orders in that tenant. If routing is wrong, Elasticsearch may return not found even though the document exists on another shard. Never interpret not found as proof the user lacks permission; handle errors per API contract and avoid revealing whether another tenant's document exists.

## 11. Routing in Spring Data Elasticsearch

Spring Data Elasticsearch supports declaring routing metadata on an entity using the routing annotation on a property. Example:

~~~java
@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    @Routing
    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Keyword)
    private String status;
}
~~~

In practice, use a single tenant identifier property and verify your version's mapping/conversion behavior. The example highlights that routing metadata and source fields serve two distinct purposes; you do not necessarily need two separate tenant fields.

One model can typically use the same `tenantId` property both as the routing value and as a `keyword` field for queries. Verify the annotation and generated mappings in your project's release train.

### Setting routing before saving

When creating a new entity, the server must assign the tenant ID from trusted context:

~~~java
public Order createOrder(CreateOrderRequest request) {
    String tenantId = currentTenant.requireTenantId();

    Order order = new Order();
    order.setTenantId(tenantId);
    order.setStatus("OPEN");
    order.setCustomerId(request.customerId());

    return repository.save(order);
}
~~~

Do not copy a tenant ID from the request body without verifying permissions. If a DTO contains a `tenantId` field, ignore it or reject mismatches against the tenant context.

### Routing for custom operations

When using `ElasticsearchOperations`, `NativeQuery`, or bulk operations, routing can be passed through operation/query metadata or per bulk item. Exact APIs vary across Spring Data Elasticsearch versions.

For bulk requests, routing must be set per item operation. Never assume a single batch-level routing value fits every document if a batch can span multiple tenants.

When tenant isolation is required, every item must carry a verified tenant ID and corresponding query/filter. If a batch contains multiple tenants, never apply a single shared routing value to the whole batch.

## 12. What Does `_routing.required` Do?

Elasticsearch allows mappings to require routing when indexing documents. Example:

~~~http
PUT /orders
{
  "mappings": {
    "_routing": {
      "required": true
    },
    "properties": {
      "tenantId": {
        "type": "keyword"
      },
      "status": {
        "type": "keyword"
      }
    }
  }
}
~~~

When `required` is enabled, index operations missing routing are rejected. This setting helps catch callers that forget to pass a routing value.

However, it does not verify that the routing value matches the right tenant:

- Routing `tenant-A` can still be sent while the document source contains `tenant-B`.
- An unauthorized user can still supply routing if the API permits it.
- Search routing still does not automatically insert a tenant filter.
- Any arbitrary routing value still resolves to a valid shard.

Therefore, `required` is a completeness check on routing metadata, not authorization.

## 13. Elasticsearch Roles, Document-Level Security, and Field-Level Security

Elasticsearch provides cluster/index-layer security mechanisms, and in eligible setups/versions can offer document-level security (DLS) and field-level security (FLS).

- **Index privileges** restrict which indices a user/API key can read, write, create, or delete.
- **Document-level security** restricts which documents a user can access via query policies.
- **Field-level security** restricts which fields can be read or written depending on privilege type and supported setup.
- **API key/service identity** establishes identity and permissions for applications or clients calling Elasticsearch.

Features and licensing conditions vary by version and subscription. Confirm DLS/FLS availability in your actual deployment environment.

DLS can serve as an additional defense layer when different users or API keys connect directly to Elasticsearch with distinct roles. FLS can reduce exposure of sensitive fields for principals that do not need to read them.

### DLS/FLS do not automatically recognize end users when the backend shares one credential

A common architecture has the Spring backend use a shared service account or API key when calling Elasticsearch on behalf of all end users. In that setup, Elasticsearch sees only the backend's identity and does not know whether the current request came from `tenant-A` or `tenant-B`.

If the backend shares one credential permitted to read the entire index, any DLS policy attached to that credential applies to the backend identity. It does not dynamically shift per HTTP request's user principal.

In this architecture, the backend must still:

- Authenticate users.
- Resolve tenant membership.
- Authorize actions.
- Build mandatory tenant filters.
- Derive routing values server-side from trusted context.
- Prevent clients from submitting arbitrary queries that bypass service policy.

If individual tenants or users have separate Elasticsearch identities, roles/DLS/FLS can reinforce cluster enforcement. Even then, identity lifecycles, credential rotation, and least privilege must be designed carefully.

## 14. Dedicated Indices, Aliases, and Routing

Some systems isolate data with a dedicated index per tenant. This creates clearer operational boundaries, yet is only secure if Elasticsearch privileges restrict each principal to its own index.

Aliases can point to one or multiple indices and can be configured with search/index routing. Alias routing directs requests through the alias using the configured routing value.

Still, alias routing only directs shards. It does not prove the caller belongs to a tenant allowed to access that alias.

If the backend service account holds privileges across all tenant indices, application endpoints must still check tenant context before choosing an alias/index. Never let users supply arbitrary index or alias names.

| Model | Benefit | What Must Still Be Protected |
|---|---|---|
| Shared index, tenant routing | Easy data consolidation, can reduce shard fan-out | Mandatory tenant filter and server-derived route |
| Shared index, no custom routing | Simpler model | Tenant filter remains mandatory |
| Dedicated index per tenant | Separate mappings/lifecycles and index privilege boundaries | Index selection and Elasticsearch roles |
| Per-tenant alias | Stable access API, can attach routing | Alias does not replace authorization |
| Per-principal DLS/FLS | Cluster enforcement for that principal | Identity, role policy, and license/version |

Never choose a model under the assumption that separate shards or separate aliases automatically provide security.

## 15. Avoiding Unscoped Queries

A common bug occurs when a repository exposes both safe and generic methods:

~~~java
List<Order> findByTenantId(String tenantId);

Iterable<Order> findAll();
~~~

If any controller or service can call `findAll`, multi-tenant data can be returned unexpectedly.

Design guidelines:

- Place repositories behind a service layer.
- Never expose CRUD repositories directly to controllers.
- Favor methods with explicit tenant scope.
- For system-wide admin operations, use separate services and authorities.
- Restrict access to raw `ElasticsearchOperations`/clients.
- Code-review every new query to verify tenant filters.
- Maintain tests verifying endpoints cannot query cross-tenant.

Do not rely on convention or comments to protect data. Tenant conditions must exist in queries or be enforced by an actual security layer.

## 16. Checking Tenant Ownership on ID Operations

A request like `GET /orders/O-100` carries only an order ID. The service must verify whether the order belongs to the current tenant.

One approach is querying by both ID and tenant ID:

~~~java
public Optional<Order> findOrder(String orderId) {
    String tenantId = currentTenant.requireTenantId();

    return repository.findByIdAndTenantId(
        orderId,
        tenantId
    );
}
~~~

If the result is empty, the API can return not found per policy so other tenants' documents are not disclosed. If policy distinguishes forbidden from not found, do so only after safely verifying permissions.

Never treat hard-to-guess IDs as authorization. IDs leak into logs, URLs, messages, and shared data.

With custom routing, get/update/delete require the matching routing value. Correct routing only locates the document; the service must still verify ownership and permissions.

## 17. Bulk Operations and Tenant Isolation

A bulk request can hold many operations, each with its own routing value. Tenant scope bugs hide easily here if only the overall request is checked.

Before constructing a bulk request:

1. Resolve the tenant for each record from a trusted source.
2. Verify the caller or job identity is authorized for that tenant.
3. Ensure `tenantId` in the source does not conflict with the tenant context.
4. Assign the routing value per item.
5. Keep source ID, tenant ID, and operation type metadata for reconciliation.
6. Inspect per-item results and record errors.

Never let a tenant client send a list of documents with arbitrary `tenantId` values and bulk-index all of them. A technically successful bulk operation can still violate application data boundaries.

For system-wide import jobs, define a clear service identity and job scope. A job's permissions must never be inferred from per-item routing values.

## 18. Changing Routing Values and Migrations

Routing values should stay stable across a document's lifecycle. If a routing strategy changes, documents may need to move to different shards.

Do not merely edit the `tenantId` field in `_source` and assume routing metadata updates too. Routing metadata determined which shard stored the document; updating a source field does not migrate the document to a new shard.

A migration workflow may involve:

1. Read the document from the old location using the old routing.
2. Verify the document's tenant and version.
3. Index the document at the destination with the new routing.
4. Confirm the new document was written properly.
5. Delete the old document using its ID and old routing.
6. Reconcile to ensure no unintended duplicates remain.
7. Update read/write code to use the new routing strategy.

If using reindex, configure destination routing derivation and manage concurrent write conflicts. Migration plans must account for documents updated mid-transition.

## 19. Common Pitfalls

| Symptom or Assumption | Problem | Resolution |
|---|---|---|
| Search uses routing yet returns another tenant's document | Multiple tenants share a shard and query omits tenant filter | Add mandatory `tenantId` filter |
| Client supplies routing value | Caller can pick another tenant's route | Derive route from authenticated tenant context |
| Source has different `tenantId` than route | Data and routing out of sync | Assign/validate tenant server-side before indexing |
| Get by ID fails to find document | Missing or wrong routing in request | Pass the routing value used when indexing |
| Update/delete touches wrong tenant | Relied solely on ID or route without ownership check | Authorize tenant and verify resource scope |
| Same ID appears twice | Indexed same ID with different routing values | Use globally unique IDs or tenant-qualified IDs |
| `_routing.required` treated as security | `required` only checks routing presence | Add authorization and tenant filters |
| Alias treated as a security boundary | Alias routing only directs requests | Use index privileges and service authorization |
| DLS does not isolate end users | Backend shares one credential | Enforce tenant in backend or use separate identities |
| Repository `findAll` called from controller | Query lacks tenant scope | Encapsulate repository behind service and limit methods |
| Bulk request mixes tenants with one route | Shared batch routing across tenants | Apply routing and tenant validation per item |
| Changed tenant ID but kept doc on old shard | Source update does not move routing metadata | Reindex/migrate with the new route |

## 20. Testing Routing Security and Tenant Isolation

Tests must prove Tenant A cannot read, update, or delete Tenant B's documents—even when the caller knows the ID or attempts to alter the routing value.

An integration test suite should involve at least two tenants. To prove routing is not a filter, create a test index with a single primary shard so all routing values land on that shard. Then a search with routing but without a tenant filter demonstrates that multiple tenants' documents are visible on the same shard.

Sample data:

~~~json
[
  {
    "orderId": "A-100",
    "tenantId": "tenant-A",
    "status": "OPEN"
  },
  {
    "orderId": "B-200",
    "tenantId": "tenant-B",
    "status": "OPEN"
  }
]
~~~

Required test scenarios:

| Scenario | Expected Outcome |
|---|---|
| Tenant A searches its orders | Only `tenant-A` documents returned |
| Tenant A tries changing routing to `tenant-B` | Authorization rejects or service still enforces `tenant-A` route |
| Tenant A calls get with `tenant-B` ID | `tenant-B` content not returned |
| Tenant A updates `tenant-B` ID | `tenant-B` document unchanged |
| Tenant A deletes `tenant-B` ID | `tenant-B` document not deleted |
| Search routed to `tenant-A` missing tenant filter | Test demonstrates other tenant docs on the same shard can appear |
| Query with both routing and tenant filter | Only `tenant-A` documents returned |
| Index request passes `tenantId` mismatching principal | Rejected or server overwrites `tenantId` per policy |
| Bulk includes an unauthorized tenant item | That item is rejected and recorded |
| Request without authenticated tenant | No tenant data accessed |
| Same ID with different routing | System prevents duplicates per chosen ID rule |
| DLS/FLS enabled | Principal sees only docs/fields allowed by role policy |

### Tests should not merely mock routing

Mocks can verify a service passes parameters, yet cannot prove shard routing and actual Query DSL behave as intended.

Use compatible Elasticsearch integration tests to confirm:

- Documents are indexed with routing.
- Get/update/delete require matching routes.
- Search routing only narrows shards.
- Tenant filters actually exclude other tenants' documents.
- Mappings and `_routing.required` behave properly.
- Roles/DLS/FLS are enforced if the environment uses those features.

Alongside integration tests, test service authorization under different principals to ensure clients cannot swap tenant contexts.

## 21. Secure Implementation Checklist

- [ ] Understand routing is shard selection, not access control.
- [ ] Store explicit `tenantId` in source for filtering and auditing.
- [ ] Resolve tenant from an authenticated principal or verified membership.
- [ ] Never trust client-supplied tenant IDs/routing values without authorization.
- [ ] Assign routing values on the server.
- [ ] Use the exact same routing value consistently for index and ID operations.
- [ ] Add tenant filters to every tenant-scoped search.
- [ ] Check ownership on get/update/delete by ID.
- [ ] Never expose `findAll` or raw clients to tenant callers.
- [ ] Prevent unintended duplicate IDs under different routing values.
- [ ] Use `_routing.required` to catch missing routing, never as authorization.
- [ ] Configure least-privilege index permissions.
- [ ] Evaluate DLS/FLS based on version, subscription, and identity model.
- [ ] Understand a shared backend credential does not distinguish end users automatically.
- [ ] Handle routing per item in bulk requests.
- [ ] Maintain a migration plan when changing routing strategies.
- [ ] Include integration tests with multiple tenants on the same shard.
- [ ] Test read, update, delete, and index authorization.
- [ ] Log enough for auditing without exposing sensitive payloads.

Routing helps Elasticsearch distribute documents and narrow searched shards. It does not verify identity, check tenant membership, or filter documents within a shard. A secure Spring Data Elasticsearch system must derive tenants from authenticated identities, check permissions in the service/security layer, attach mandatory tenant filters to queries, and use server-side routing strictly as a routing optimization. Roles, index privileges, and DLS/FLS can add protection inside Elasticsearch when the identity architecture aligns, but a routing value by itself is never proof of access rights.
