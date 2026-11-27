# Multi-Tenant Isolation Using Separate Indices or Tenant Filters

In SaaS applications, multiple customers (tenants) often share a single Elasticsearch cluster. Each tenant must see only its own data, even when two tenants have identical document IDs or search the same kind of data.

Spring Data Elasticsearch provides APIs for storing, searching, and mapping documents; it does not automatically establish security boundaries between tenants. Your architecture must decide where to place that boundary and ensure every access path obeys the same rules.

Two common models are:

- **Dedicated index per tenant:** each customer's data lives in its own index. Elasticsearch permissions can be scoped by index.
- **Shared index with tenant filters:** multiple customers share an index, each document carries a `tenantId` field, and every operation is constrained to that tenant.

Both models can be combined in systems with many small tenants and a few large tenants. Whichever approach you pick, tenant identity must come from an authenticated identity—never trust a `tenantId` sent by the client.

## 1. Goals of Tenant Isolation

A multi-tenant design must guarantee:

1. Tenant A cannot read Tenant B's documents.
2. Tenant A cannot update or delete Tenant B's documents.
3. Search, aggregations, count, bulk, and auxiliary endpoints all obey the same boundary.
4. A tenant cannot select another tenant's index or alias by tampering with a request.
5. Identical document IDs across two tenants never cause overwrites or wrong-tenant reads.
6. Access rights are enforced server-side and are testable.
7. Onboarding a new tenant does not require code changes or uncontrolled manual configuration.

Tenant isolation covers both reads and writes. A proper search filter alone is not enough if get-by-ID, update, delete, bulk, or export endpoints access documents without checking the tenant.

It also helps to distinguish three layers:

- **Data partitioning:** which index, shard, and fields hold the data.
- **Application authorization:** the service determines which tenant is allowed to perform an operation.
- **Elasticsearch security:** cluster/index privileges, document-level security (DLS), and field-level security (FLS) limit what a credential can read or modify.

These layers reinforce one another. Routing or aliases can direct requests and simplify queries, but never replace authorization on their own.

## 2. Choosing a Storage Model

### 2.1. One index per tenant

Each tenant gets its own index, for example:

~~~text
products-tenant-001
products-tenant-002
products-tenant-003
~~~

Advantages:

- Index privileges can be granted per tenant.
- The same document ID can appear across different indices.
- Index templates, mappings, and lifecycle policies are easy to apply per tenant group.
- Snapshots, restores, reindexing, or deleting a single tenant's data are more independent.
- Access can be bounded using credentials holding privileges only on the matching index.

Drawbacks:

- Index and shard counts grow with tenant count.
- Creating too many small indices increases cluster state, heap usage, and management overhead.
- Index creation, mappings, aliases, lifecycles, and migrations must be automated.
- Cross-tenant reporting must query across many indices or an aggregated index.
- Mapping changes must be rolled out consistently across many indices.

This model works well when tenants require strong index-level boundaries, have significant data volume, or need independent data lifecycles.

### 2.2. One shared index, filtered by `tenantId`

All tenants store documents in the same index:

~~~text
products
  ├── tenantId = tenant-001, document P-100
  ├── tenantId = tenant-002, document P-100
  └── tenantId = tenant-003, document P-200
~~~

The mapping needs a `tenantId` field of type `keyword`:

~~~json
{
  "mappings": {
    "properties": {
      "tenantId": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      },
      "category": {
        "type": "keyword"
      },
      "price": {
        "type": "scaled_float",
        "scaling_factor": 100
      }
    }
  }
}
~~~

Advantages:

- Fewer indices and shards when hosting many small tenants.
- Easy to manage one mapping and one deployment pipeline.
- Easier to run authorized administrative or reporting tasks across all tenants.
- Adding a new tenant typically requires no new index creation.
- Good cluster resource utilization when tenant data is evenly distributed.

Drawbacks:

- Every tenant-facing query must carry a tenant filter.
- One code path forgetting a filter can leak cross-tenant data without an extra protection layer.
- A single index does not allow index privileges to distinguish documents per tenant.
- A single tenant with huge data or traffic can affect other tenants.
- Document IDs must be designed to avoid collisions within the shared index.

This model fits well when there are many small tenants, uniform data structures, and a tightly controlled data access layer.

### 2.3. Hybrid model

A system can use a shared index for small tenants and dedicated indices for large or strictly regulated tenants:

~~~text
small tenants
     |
     v
shared-products
  tenantId filter

large tenant A
     |
     v
products-tenant-A

regulated tenant B
     |
     v
products-tenant-B
~~~

This requires a tenant-to-storage resolver to determine where each tenant's data resides. The resolver must take the tenant from the verified security context and look up a trusted storage configuration.

Never let clients pass an index name directly. If a tenant can supply an arbitrary string as an index name, they could attempt to reach an out-of-scope index.

### 2.4. Quick comparison

| Criterion | Dedicated Index | Shared Index + Tenant Filter |
| --- | --- | --- |
| Boundary in Elasticsearch | Can be constrained via index privileges. | Requires DLS or application layer to restrict documents. |
| Index count | Grows with tenants. | Fewer indices. |
| Operational overhead | Provisioning and migrations are more complex. | Simpler mappings and lifecycles. |
| Same ID across tenants | Allowed in separate indices. | Requires globally unique or composite IDs. |
| Cross-tenant analytics | Must query multiple indices or an aggregated index. | Easier in the same index when authorized. |
| Deleting tenant data | Can delete the dedicated index via controlled workflow. | Must delete by tenant filter and verify scope. |
| Unusually large tenant | Can isolate into its own shards/index. | Risk of noisy neighbor impact. |
| Security setup | Per-index roles. | DLS can restrict reads; writes still require app control or other partitioning. |

There is no single right choice for every system. The decision depends on tenant count, data size, compliance rules, query load, shard costs, and operational automation maturity.

## 3. Tenant Identity Must Come from a Trusted Source

Tenant ID is part of the authorization context. Never use a tenant value supplied by a request body or query parameter as the basis for data access.

An appropriate flow:

~~~text
HTTP request
     |
     v
Authentication
     |
     v
JWT / session / API credential
     |
     v
Resolve tenant membership
     |
     v
Trusted TenantContext
     |
     v
Service / Repository
     |
     v
Tenant-scoped Elasticsearch request
~~~

For example, a request might contain `tenantId` in a URL to select a resource, but the server must verify that tenant is in the list of tenants the principal is authorized to access. If an application supports only one tenant per request, extract the tenant ID from verified claims or membership.

Key principles:

- Never trust `tenantId` in JSON payloads.
- Never let callers pick index names themselves.
- Never let callers send arbitrary DLS queries or raw Elasticsearch Query DSL.
- Never use an unverified tenant ID to construct an alias or routing value.
- Include the tenant ID in audit logs alongside principal and request ID.
- For background tasks, store the tenant ID in a verified job payload and re-check it at execution time.

If a user can belong to multiple tenants, authorization must identify the active tenant they are operating under. Never assume knowing a tenant ID implies permission to access that tenant.

## 4. Designing Documents and `tenantId`

With a shared index, every document must carry `tenantId`:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String tenantId;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    // Constructor, getters, and setters
}
~~~

`tenantId` should be `keyword` because applications use exact matches, filters, and aggregations on tenant. Never apply a text analyzer to a tenant identity.

You can configure stricter mappings to reject documents missing fields or having wrong types, though dynamic mappings and dynamic templates must be designed alongside the application schema. Most importantly, the service must assign `tenantId` from the verified context when creating documents.

### 4.1. Tenant ID should be immutable

Once a document is created in Tenant A, ordinary updates must not allow changing `tenantId` to Tenant B. Moving data across tenants is an intentional migration requiring a dedicated workflow:

1. Verify permissions on both source and destination tenants.
2. Read the source document.
3. Check for ID and business key collisions.
4. Write the document to the destination tenant's storage.
5. Verify data and related references.
6. Delete the source document after confirmation.
7. Record an audit event.

Never allow generic update DTOs to carry `tenantId` and overwrite the entity. Exclude `tenantId` from update requests or verify it matches the current tenant context.

### 4.2. Document IDs in a shared index

In a shared index, Elasticsearch enforces `_id` uniqueness across the index. If two tenants both have product ID `P-100`, indexing one can overwrite the other if they share the same `_id`.

Two common approaches:

- Use a globally unique internal ID generated by the system.
- Use a composite ID built from tenant and business ID, e.g., `tenant-001:P-100`.

Example ID builder:

~~~java
public String documentId(String tenantId, String businessId) {
    return tenantId + ":" + businessId;
}
~~~

Only use verified `tenantId` values and validated `businessId` values. If IDs can contain the delimiter, use encoding or an unambiguous composite format.

With dedicated per-tenant indices, the same `_id` can exist in separate indices. Still, tenant-aware index resolution is required to prevent accessing the wrong index.

## 5. Isolation with Dedicated Indices in Spring Data

The `@Document` annotation typically declares an entity's default index:

~~~java
@Document(indexName = "products")
public class ProductDocument {
    // fields
}
~~~

For dynamic per-tenant indices, pass `IndexCoordinates` to `ElasticsearchOperations` methods. `IndexCoordinates` specifies the actual target index for the current operation.

Example resolver:

~~~java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Component;

@Component
public class TenantIndexResolver {

    public IndexCoordinates productsIndex(TenantId tenantId) {
        String indexName = "products-" + tenantId.value();
        return IndexCoordinates.of(indexName);
    }
}
~~~

`TenantId` in the example is a domain type constructed from a verified tenant identity, not an arbitrary client-supplied string. In real systems, index names must conform to Elasticsearch index naming rules or be retrieved from a tenant configuration registry.

Saving a document:

~~~java
@Service
public class TenantProductService {

    private final ElasticsearchOperations operations;
    private final TenantIndexResolver indexResolver;

    public TenantProductService(
            ElasticsearchOperations operations,
            TenantIndexResolver indexResolver) {
        this.operations = operations;
        this.indexResolver = indexResolver;
    }

    public ProductDocument save(TenantId tenantId, ProductDocument product) {
        product.setTenantId(tenantId.value());

        IndexCoordinates index = indexResolver.productsIndex(tenantId);
        return operations.save(product, index);
    }
}
~~~

Reading a document:

~~~java
public ProductDocument findById(TenantId tenantId, String id) {
    IndexCoordinates index = indexResolver.productsIndex(tenantId);
    return operations.get(id, ProductDocument.class, index);
}
~~~

Here the index is resolved from the verified tenant. The same document ID can exist in another tenant's index, yet the request targets only the corresponding index.

### 5.1. Why default repositories may not suffice

Repositories usually read their default index from `@Document`. A shared repository cannot automatically know the current tenant to pick a concrete index.

With index-per-tenant, you can:

- Use `ElasticsearchOperations` and pass `IndexCoordinates` per request.
- Create a dedicated adapter/service to hide index selection from controllers.
- Define separate repositories for fixed index groups if the number of groups is small.
- Use a custom repository fragment with a tenant-aware index resolver.

Do not create a new repository or `ElasticsearchClient` for each request. Passing `IndexCoordinates` is sufficient to switch target indices in `Operations` calls.

### 5.2. Creating and managing per-tenant indices

Tenant indices need consistent base mappings and settings. You can use an index template to apply configuration when new indices are created:

~~~http
PUT /_index_template/products-template
Content-Type: application/json

{
  "index_patterns": ["products-*"],
  "template": {
    "mappings": {
      "properties": {
        "tenantId": { "type": "keyword" },
        "sku": { "type": "keyword" },
        "name": { "type": "text" },
        "category": { "type": "keyword" }
      }
    }
  }
}
~~~

A provisioning service can create the concrete index when a tenant is activated. Separate index creation privileges from runtime credentials if business services do not need index administration rights.

Things to manage:

- Mapping versions.
- Number of primary shards and replica policy.
- Index templates and component templates.
- Lifecycle/retention policies.
- Read/write aliases.
- Snapshots and restores.
- Migrations when mappings change.
- Offboarding and tenant data deletion workflows.

Do not create one primary shard by default for every tenant without evaluating total tenant count and data sizes. Thousands of tiny indices produce thousands of shards and put heavy pressure on the cluster.

## 6. Isolation with Tenant Filters in a Shared Index

With a shared index, every tenant-facing request must attach a `tenantId` filter taken from a trusted context.

Example searching products by name:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.SearchHit;
import java.util.List;

public List<ProductDocument> search(
        String tenantId,
        String searchText) {

    NativeQuery query = NativeQuery.builder()
            .withQuery(q -> q.bool(b -> b
                    .filter(f -> f.term(t -> t
                            .field("tenantId")
                            .value(FieldValue.of(tenantId))
                    ))
                    .must(m -> m.match(mm -> mm
                            .field("name")
                            .query(searchText)
                    ))
            ))
            .build();

        return operations.search(
                    query,
                    ProductDocument.class,
                    IndexCoordinates.of("products"))
            .stream()
            .map(SearchHit::getContent)
            .toList();
}
~~~

This example uses synchronous `ElasticsearchOperations`, so results are mapped from `SearchHits` to `List`. For reactive applications, use `ReactiveElasticsearchOperations` and return `Flux` as shown in the reactive section below. The key requirement is that the tenant filter sits in the `bool` filter of every search request.

JSON Query DSL example:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "tenantId": "tenant-001"
          }
        }
      ],
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ]
    }
  }
}
~~~

Use filter context for `tenantId` because it is a data partitioning condition, not a relevance signal. Filters can be cached depending on conditions and configuration, and do not affect scores.

Never concatenate `tenantId` into a query string. Pass it as a typed `term` value.

### 6.1. Tenant filters must apply to every query type

All of the following endpoints require a tenant boundary:

| Operation | Required Condition |
| --- | --- |
| Search/list | `tenantId` filter. |
| Count | `tenantId` filter. |
| Aggregations/facets | `tenantId` filter in query scope before aggregations. |
| Search after/PIT | Each subsequent request keeps the same tenant scope and matching PIT. |
| Update by query | `tenantId` filter alongside update criteria. |
| Delete by query | `tenantId` filter alongside deletion criteria. |
| Bulk index/update/delete | Check tenant for every item; never trust `tenantId` in untrusted payloads. |
| Multi-search | Every sub-request must carry tenant scope. |
| Suggest/script queries | Must never drop tenant scope or read another tenant's data. |
| Export/reports | Tenant filter must apply before streaming or aggregating data. |

Adding a filter in a search controller does not protect other methods. Centralize tenant scoping inside a service/repository adapter so all access paths pass through the same rules.

### 6.2. Aggregations must also be filtered

Never run aggregations over the entire shared index and filter buckets on the frontend. Doing so can leak counts, category names, values, or trends from other tenants.

Place the tenant filter on the top-level query:

~~~json
{
  "size": 0,
  "query": {
    "term": {
      "tenantId": "tenant-001"
    }
  },
  "aggs": {
    "categories": {
      "terms": {
        "field": "category",
        "size": 20
      }
    }
  }
}
~~~

All metrics and sub-buckets are then computed strictly over the filtered document set.

## 7. Avoiding Access Paths That Bypass Tenant Filters

A common hazard in shared indices is a convenience method that is not tenant-aware.

Examples of calls to watch out for:

~~~java
repository.findAll();
repository.findById(id);
operations.get(id, ProductDocument.class);
operations.count(Query.findAll(), ProductDocument.class);
~~~

These methods do not know the current tenant. If called directly in a tenant-facing service, they can return data outside the tenant.

Helpful design rules:

- Never inject raw repositories into controllers.
- Create `TenantProductService` as the data access gateway.
- Service methods always accept a verified `TenantId` or resolve it from a secure context.
- Never expose unscoped `findAll`/`getById` to tenant-facing business code.
- Use custom repository fragments for complex queries needing tenant scope.
- Inspect background jobs, admin endpoints, and export paths as well.

### 7.1. Derived queries with tenant conditions

You can define methods with `tenantId` in the method name:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByTenantIdAndCategory(
            String tenantId,
            String category);

    Optional<ProductDocument> findByTenantIdAndId(
            String tenantId,
            String id);
}
~~~

Derived query methods with `tenantId` make the access scope explicit in the contract. However, the repository still inherits `findAll()`, `findById()`, and other unscoped methods.

Therefore, do not let tenant-facing services call the repository directly. Hide the repository behind a service or custom facade and expose only scoped methods. If using a custom base repository, ensure inherited methods such as `findById`, `existsById`, `deleteById`, and `findAll` are also overridden per tenant policy; missing a single method still leaves a gap.

### 7.2. Get-by-ID needs a tenant guard

A search filter does not protect a get-by-ID call if the get request has no tenant condition. With a shared index, you can:

- Use a composite `_id` containing the tenant ID and construct IDs only after verifying the tenant.
- Use a query combining both `tenantId` and the ID/business ID.
- After reading, check `tenantId` before returning data, while avoiding responses or timing that leak cross-tenant existence.

Composite IDs reduce ID collision risk but do not replace authorization. If an attacker knows another tenant's composite ID, the endpoint must still verify the current tenant.

## 8. Aliases and the Limitations of Filtered Aliases

You can create a filtered alias for each tenant:

~~~http
POST /_aliases
Content-Type: application/json

{
  "actions": [
    {
      "add": {
        "index": "products",
        "alias": "products-tenant-001",
        "filter": {
          "term": {
            "tenantId": "tenant-001"
          }
        }
      }
    }
  ]
}
~~~

Aliases provide friendly names for requests and can centralize tenant filters for supported search APIs.

However, filtered aliases should not be treated as a complete security boundary:

- Alias filters primarily apply to search/count operations and select query-based APIs.
- Do not assume filters automatically apply to the Get API reading by `_id`.
- Alias filters do not automatically validate `tenantId` when indexing new documents through the alias.
- Callers with access to the concrete index can bypass the alias.
- Different APIs have different semantics; check the specific endpoint documentation.

If using aliases for partitioning, pair them with index privileges/DLS and never grant broader concrete index access than necessary. For a shared index, aliases can be a convenient query routing layer, but the service must still guard gets/writes and any API not covered by alias filters.

## 9. Document-Level Security and Field-Level Security

Elasticsearch security can restrict readable data with document-level security (DLS) and restrict returned fields with field-level security (FLS), depending on licensing and deployment setup.

### 9.1. DLS for shared indices

DLS attaches a query filter to a role's index privileges. For example, a role that reads only documents with `tenantId` equal to `tenant-001`:

~~~json
{
  "indices": [
    {
      "names": ["products"],
      "privileges": ["read"],
      "query": {
        "term": {
          "tenantId": "tenant-001"
        }
      }
    }
  ]
}
~~~

When a principal using this role performs supported read operations, Elasticsearch applies the role's document query. Even if the application sends a match-all query, DLS restricts the documents the role can read.

DLS helps enforce boundaries inside Elasticsearch instead of relying solely on every code path remembering to add a tenant filter. Keep in mind:

- DLS attaches to read privileges; do not treat it as a mechanism limiting which documents can be written or updated.
- A shared credential may carry broader roles, defeating isolation.
- When a principal has multiple roles, the way roles combine can widen readable scope unexpectedly; design role composition carefully.
- DLS has limitations and specific interactions with certain APIs/features; check specific endpoints.
- Administrative or cross-tenant tasks need a separate identity with controlled permissions.

For shared indices, DLS protects reads at the Elasticsearch layer, while the service must still assign `tenantId` correctly and verify permissions on every write.

### 9.2. FLS to hide sensitive fields

FLS limits which fields a role can read. For instance, allowing a role to read all fields except `internalCost` or `margin`:

~~~json
{
  "field_security": {
    "grant": ["*"],
    "except": ["internalCost", "supplierNotes"]
  }
}
~~~

FLS is useful when user groups in the same tenant have different permissions, or a service should read only a subset of data. It does not replace tenant isolation: FLS restricts fields, while DLS restricts documents.

### 9.3. Per-tenant API keys

You can issue dedicated API keys per tenant or service with role descriptors constraining indices and/or DLS. When doing so:

- Create keys using an identity authorized to grant those exact privileges.
- Scope keys to the required indices.
- For shared indices, use DLS for reads if appropriate.
- Never grant unnecessary cluster privileges.
- Manage expiration, rotation, and revocation.
- Never store keys in source code or logs.
- Verify effective privileges of the key, including the intersection with the creating identity's privileges per Elasticsearch rules.

An API key is only effective if its role descriptor genuinely restricts access. An API key with `read` on the entire shared index can still read every tenant's data if DLS is absent.

## 10. Per-Index Authorization with Index-Per-Tenant

With dedicated indices, roles can allow access solely to a single tenant's index:

~~~json
{
  "indices": [
    {
      "names": ["products-tenant-001"],
      "privileges": ["read", "write"]
    }
  ]
}
~~~

This identity needs no permissions on `products-tenant-002`. A service can use a per-tenant API key or credentials fetched from a controlled credential broker.

Never grant wildcard permissions like `products-*` to a single-tenant service if index isolation is the goal. Index create/manage privileges should belong to a separate provisioning service or operator.

If one backend service serves multiple tenants, it can select the right credential after authenticating the tenant. Credential selection must come from a trusted registry, never from a client-supplied header.

## 11. Tenant Routing to Improve Locality

With a shared index, you can use `tenantId` as the routing value so documents for the same tenant typically land on the same shard.

Index example:

~~~http
PUT /products/_doc/P-100?routing=tenant-001
Content-Type: application/json

{
  "tenantId": "tenant-001",
  "name": "Keyboard"
}
~~~

Mappings can require routing:

~~~json
{
  "mappings": {
    "_routing": {
      "required": true
    },
    "properties": {
      "tenantId": {
        "type": "keyword"
      },
      "name": {
        "type": "text"
      }
    }
  }
}
~~~

When searching by tenant, pass the matching routing value so Elasticsearch searches only the target shard:

~~~http
GET /products/_search?routing=tenant-001
Content-Type: application/json

{
  "query": {
    "term": {
      "tenantId": "tenant-001"
    }
  }
}
~~~

Keep the distinction clear:

- `routing` selects which shard processes the request.
- The `tenantId` filter selects which documents may appear in results.
- `routing` does not check tenant permissions.
- Multiple tenants can hash onto the same shard.
- A high-traffic tenant can make its shard hot.

Therefore, always keep the tenant filter even when `routing` is supplied. Routing is a performance and locality optimization, not a security boundary.

If mappings set `_routing.required=true`, every index request must include routing. Get/update/delete by ID also need the same routing. Check Spring Data's routing resolver or pass routing via the corresponding API so you do not inadvertently send unrouted requests.

### 11.1. Routing and large tenants

A tenant with disproportionate document counts or write throughput can concentrate load onto one shard when `tenantId` is used as routing. This is a trade-off between locality and load distribution.

Options:

- Skip custom routing if the cluster needs more even data distribution.
- Move large tenants to dedicated indices.
- Use routing partitioning if compatible with your version and query model.
- Split a tenant's data across a controlled secondary key while ensuring queries include all target routing partitions.

Never use routing partitions as a security mechanism. The tenant filter remains mandatory.

## 12. Implementing a Tenant-Aware Service in Spring Data

A service should receive the tenant identity from the authorization layer and apply it to every operation.

Shared-index service example:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.stereotype.Service;
import java.util.List;

@Service
public class TenantProductService {

    private static final IndexCoordinates PRODUCTS =
            IndexCoordinates.of("products");

    private final ElasticsearchOperations operations;

    public TenantProductService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public List<ProductDocument> search(
            TenantId tenantId,
            String text) {

        NativeQuery query = NativeQuery.builder()
                .withQuery(q -> q.bool(b -> b
                        .filter(f -> f.term(t -> t
                                .field("tenantId")
                                .value(FieldValue.of(tenantId.value()))
                        ))
                        .must(m -> m.match(mm -> mm
                                .field("name")
                                .query(text)
                        ))
                ))
                .build();

        return operations.search(
                        query,
                        ProductDocument.class,
                        PRODUCTS)
                .stream()
                .map(SearchHit::getContent)
                .toList();
    }

    public ProductDocument save(
            TenantId tenantId,
            ProductDocument product) {

        product.setTenantId(tenantId.value());
        return operations.save(product, PRODUCTS);
    }
}
~~~

This example assumes `TenantId` was constructed from an authenticated principal and cannot be forged by callers from request payloads. The service sets `tenantId` on write and enforces the filter on search.

For shared indices, also add tenant scoping to get/update/delete. Never reuse an unfiltered get-by-ID method in a tenant-facing endpoint.

### 12.1. Updating documents with a tenant condition

When using query-based updates, criteria must include both document identity and tenant:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-001" } },
        { "term": { "sku": "SKU-100" } }
      ]
    }
  },
  "script": {
    "lang": "painless",
    "source": "ctx._source.price = params.price",
    "params": {
      "price": 49.99
    }
  }
}
~~~

Updating by `_id` does not automatically apply a tenant filter. You can read the document using a query with both `tenantId` and ID before updating with a concurrency token, or use a query-based update carrying the tenant filter. The exact choice depends on race conditions, routing, and atomicity needs.

### 12.2. Deleting documents

Deleting by ID without checking the tenant can delete the wrong document if the endpoint takes a caller-supplied ID.

With a shared index, use delete-by-query with a tenant condition or verify document ownership before deleting. Example query scope:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-001" } },
        { "term": { "sku": "SKU-100" } }
      ]
    }
  }
}
~~~

With dedicated indices, the index resolver narrows the index scope; still verify the tenant before resolving `IndexCoordinates`.

## 13. Reactive Applications and Tenant Context

In WebFlux, never rely on `ThreadLocal` as the sole store for tenant context. Reactive pipelines can hop across threads between operators; `ThreadLocal` does not automatically follow subscriptions.

Safe approaches:

- Pass `TenantId` explicitly as a parameter through service methods.
- If context is needed across the pipeline, place tenant identity into Reactor `Context` after authentication.
- Extract verified tenant context only from the security layer.
- Never allow `tenantId` in request bodies to override the context.
- Ensure background publishers/jobs carry verified tenant IDs.

Reactive service example accepting an explicit tenant ID:

~~~java
public Flux<ProductDocument> search(
        TenantId tenantId,
        String text) {

    NativeQuery query = NativeQuery.builder()
            .withQuery(q -> q.bool(b -> b
                    .filter(f -> f.term(t -> t
                            .field("tenantId")
                            .value(FieldValue.of(tenantId.value()))
                    ))
                    .must(m -> m.match(mm -> mm
                            .field("name")
                            .query(text)
                    ))
            ))
            .build();

    return reactiveOperations.search(
                    query,
                    ProductDocument.class,
                    IndexCoordinates.of("products"))
            .map(SearchHit::getContent);
}
~~~

This example uses `ReactiveElasticsearchOperations`. Do not inject synchronous `ElasticsearchOperations` and wrap results in `Mono` to simulate non-blocking behavior.

## 14. Background Jobs, Events, and Message Queues

Tenant isolation is often overlooked in flows that do not enter through HTTP controllers:

- Scheduled jobs.
- Kafka/RabbitMQ consumers.
- Batch imports/exports.
- Reindexing or data migrations.
- Webhook handlers.
- Async event listeners.
- Admin tooling.

Every job must know its valid tenant scope and maintain it throughout execution.

Example event:

~~~json
{
  "eventId": "evt-100",
  "tenantId": "tenant-001",
  "type": "ProductPriceChanged",
  "productId": "P-100"
}
~~~

Consumers should not trust `tenantId` merely because it appears in a message. Message producers must be authenticated, topic/queue permissions must be constrained, and consumers should verify tenant ownership before acting.

For batches spanning multiple tenants, split batches by tenant or track an isolated tenant scope per item. Never use a single mutable shared tenant context across parallel tasks.

## 15. Migrating Between the Two Models

You may need to move a tenant from a shared index to a dedicated index as scale grows or isolation requirements change.

A controlled migration process:

1. Identify the tenant, document count, mappings, and related dependencies.
2. Create the target index from the right template version.
3. Start syncing new changes via dual-write or ordered change capture.
4. Copy tenant data using a `tenantId` query filter.
5. Verify counts, checksums, or business keys across the dataset.
6. Switch the tenant resolver to the new index.
7. Pause or handle in-flight writes to avoid lost updates.
8. Verify reads/writes on the target index.
9. Stop writing the tenant to the shared index.
10. Delete source data after an approved rollback window.

Never simply copy data and flip an alias without addressing concurrent writes. A document updated during reindexing can be lost or overwritten without synchronization.

When moving from index-per-tenant back to a shared index, ensure global IDs do not collide, `tenantId` is populated everywhere, and all services have switched to tenant-scoped queries before opening access to the shared index.

## 16. Offboarding and Deleting Tenant Data

When a tenant leaves the service, deletion depends on the storage model:

- Dedicated index: verify the exact tenant index, take snapshots/follow retention policy, then delete the index.
- Shared index: run delete-by-query with the exact `tenantId` and check deleted document counts.
- Hybrid: handle all related indices, aliases, snapshots, and replicas.

Deleting data in Elasticsearch does not necessarily remove copies in snapshots, backups, data lakes, logs, or downstream systems. Offboarding workflows must define data scope and retention timelines per organizational policy.

Never let tenant-facing endpoints accept arbitrary index names or delete queries. Tenant deletion should be an approved administrative workflow with auditing and tenant identity verification.

## 17. Testing Tenant Isolation

Tests must prove both valid access succeeds and cross-tenant access is blocked.

Create fixtures:

| Tenant | Document ID | SKU | Name |
| --- | --- | --- | --- |
| `tenant-A` | `A:P-100` | `P-100` | Keyboard A |
| `tenant-B` | `B:P-100` | `P-100` | Keyboard B |

Minimum tests:

1. Tenant A search returns only Keyboard A.
2. Tenant B search returns only Keyboard B.
3. Tenant A cannot fetch Tenant B's document by business ID.
4. Tenant A cannot update Tenant B's document.
5. Tenant A cannot delete Tenant B's document.
6. Tenant A's counts and aggregations exclude Tenant B's documents.
7. Bulk requests cannot write Tenant B's `tenantId` while running under Tenant A.
8. Requests without a tenant context are rejected.
9. Requests attempting to pass another `tenantId` in the body do not alter tenant scope.
10. Aliases, routing, and DLS create no bypass paths.
11. Background jobs verify each message's tenant.
12. Admin/cross-tenant workflows use dedicated credentials and produce audit logs.

With index-per-tenant, verify Tenant A's credential has no index privileges on Tenant B's index.

With a shared index, test both service filters and DLS roles if DLS is used. A single test calling service search is not enough to prove get/update/delete APIs or direct credentials are safe.

### 17.1. Testing ID collisions

Create two documents with the same business ID in two tenants:

~~~text
tenant-A + P-100
tenant-B + P-100
~~~

With a shared index, confirm the system uses distinct `_id` values or globally unique internal IDs. With dedicated indices, confirm the resolver always selects the right index before reading or writing.

### 17.2. Testing Elasticsearch privileges

If using DLS or index privileges, run integration tests using real tenant credentials:

- Send a search without a tenant filter and confirm DLS still constrains results.
- Attempt to access another tenant's index and confirm denial.
- Test get-by-ID and APIs not covered by alias filters.
- Check that combined roles do not accidentally broaden access.
- Attempt to write a document with a different `tenantId` and confirm the service layer blocks it.

DLS does not restrict writes by tenant. Tests must verify the application assigns `tenantId` from the principal and prevents callers from changing the tenant field.

## 18. Performance and Noisy Neighbors

Multi-tenancy is not solely an authorization concern. A high-load tenant can degrade latency for other tenants.

Monitor per tenant:

- Document counts and index size.
- Ingest/update/delete rates.
- Search request rate and latency.
- Query timeouts and rejected requests.
- Aggregation bucket counts.
- Shard skew when using routing.
- Cache usage and refresh pressure.
- Bulk batch sizes.
- Error and retry rates.

Controls:

- Cap page sizes and bulk sizes.
- Rate-limit per tenant at the API gateway/service.
- Cap query complexity and aggregation sizes.
- Set sensible timeouts.
- Move high-volume tenants above thresholds into dedicated indices.
- Separate ingest and search workloads if needed.
- Never allow tenants to submit arbitrary Query DSL or scripts.
- Include tenant IDs in cache keys.

If caches key solely by `productId` or query text, Tenant A's data can be returned to Tenant B even when Elasticsearch filters work properly. Cache keys must include the tenant identity and relevant authorization parameters.

## 19. Anti-Patterns to Avoid

| Anti-Pattern | Risk | Fix |
| --- | --- | --- |
| Trusting `tenantId` from request body | Callers can impersonate another tenant. | Derive from authenticated principal and verify membership. |
| Filtering only in search controllers | Get/update/delete or jobs can bypass. | Centralize tenant scoping in service/repository boundaries. |
| Using alias filters as sole security | Get-by-ID or writes may not be filtered as expected. | Use index privileges/DLS and service-layer authorization. |
| Using routing instead of tenant filters | Routing only picks shards, never verifies ownership. | Keep both routing and tenant filters. |
| Calling unscoped `findAll`/`findById` | Can access another tenant's documents. | Expose a tenant-aware facade and restrict raw repositories. |
| Shared index using business ID as `_id` | Two tenants can overwrite each other. | Use global IDs or composite IDs. |
| Allowing `tenantId` changes via update DTO | Documents can accidentally switch tenants. | Keep tenant ID immutable in normal update flows. |
| Treating DLS as write protection | DLS applies to reads; writes need separate control. | Assign `tenantId` and validate rights in service, or use dedicated indices. |
| API key with index-wide read access | Key can read all tenants if DLS is absent. | Scope role descriptors by index/document and verify effective privileges. |
| Cache keys missing tenant | Can return cross-tenant data. | Include tenant ID in cache keys. |
| `ThreadLocal` in reactive flows | Tenant context can be lost across thread hops. | Pass explicit arguments or use Reactor `Context`. |
| Creating an index for every tiny tenant unchecked | Cluster accumulates too many shards/indices. | Use shared index or hybrid model above thresholds. |
| Deleting tenant data with missing filter | Could wipe multiple customers' data. | Scoped offboarding workflow, auditing, and count checks. |

## 20. Tenant Isolation Design Workflow

When building a multi-tenant Spring Data Elasticsearch module:

1. Define isolation requirements, compliance rules, tenant counts, and data scale.
2. Choose index-per-tenant, shared index, or hybrid.
3. Derive tenant identity from authentication and membership.
4. Design an immutable, verified `TenantContext`/`TenantId`.
5. If using a shared index, map `tenantId` as `keyword` and assign it server-side.
6. Design `_id` to prevent cross-tenant collisions.
7. Centralize queries inside a tenant-aware service or custom repository fragment.
8. Audit search, count, aggregations, get, update, delete, bulk, and background jobs.
9. If using dedicated indices, resolve `IndexCoordinates` from a trusted registry.
10. If using DLS/FLS or API keys, design roles and verify effective privileges.
11. Use aliases and routing solely as routing/optimization tools, never as authorization.
12. Plan provisioning, mapping migrations, rollovers, and offboarding.
13. Write negative cross-tenant tests.
14. Measure noisy-neighbor impact and set quotas/rate limits.
15. Audit all direct access paths to Elasticsearch.

## 21. References

- [Spring Data Elasticsearch — Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch — Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/repositories.html)
- [Elasticsearch — Index privileges and security](https://www.elastic.co/guide/en/elasticsearch/reference/current/security-privileges.html)
- [Elasticsearch — Document-level security](https://www.elastic.co/guide/en/elasticsearch/reference/current/document-level-security.html)
- [Elasticsearch — Field-level security](https://www.elastic.co/guide/en/elasticsearch/reference/current/field-level-security.html)
- [Elasticsearch — Index aliases](https://www.elastic.co/guide/en/elasticsearch/reference/current/aliases.html)
- [Elasticsearch — Routing](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping-routing-field.html)
- [Elasticsearch — Index templates](https://www.elastic.co/guide/en/elasticsearch/reference/current/index-templates.html)
- [Elasticsearch — Reindex API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-reindex.html)

Dedicated indices per tenant enable index-level privilege boundaries and independent data lifecycles, at the cost of higher index/shard counts and provisioning overhead. Shared indices save resources, but require tenant filters on every operation and a reliable authorization layer; DLS can reinforce read enforcement, while writes still require dedicated controls. Spring Data Elasticsearch provides `IndexCoordinates`, `Operations`, and repository fragments to implement both models. Tenant identity must come from an authenticated principal, while aliases and routing serve strictly as routing aids rather than security boundaries.
