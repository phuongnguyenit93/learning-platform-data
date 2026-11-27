# Filtering Access Control and Business Conditions in Vector Queries

Vector search finds documents whose embeddings are close to a query vector. However, the closest document semantically is not necessarily one the user is permitted to read or one that meets business criteria. A result is valid only when it simultaneously satisfies access permissions, tenant scope, and conditions such as publish status, category, expiration, or price.

In Elasticsearch, these conditions are expressed using query filters. With kNN search, where you place the filter is critical: a filter placed inside the `knn` clause acts as a pre-filter, applied while searching vectors; a filter placed outside can become a post-filter, discarding results only after kNN has already chosen candidates. Post-filtering can cause a response to return fewer than `k` results even when plenty of eligible documents exist in the index.

This lesson covers how to design fields for ACLs and business filters, how to build vector queries with pre-filters in Spring Data Elasticsearch, how to handle public/user/group access, how to combine filters in hybrid search, how to use Elasticsearch Document-Level Security (DLS) as an additional safeguard, and how to test to prevent cross-user or cross-tenant data leaks.

## 1. Vector Similarity Is Not Access Control

Suppose a knowledge base contains the following documents:

- Document A belongs to tenant alpha, shared with the engineering group.
- Document B belongs to tenant beta, marked public within tenant beta.
- Document C belongs to tenant alpha, readable only by its owner.
- Document D belongs to tenant alpha, expired.

A user in tenant alpha, who is a member of the engineering group, searches for how to configure TLS. Document A's vector may be close to the query. Document C may also be very close semantically, yet the user has no permission to view it. Document D may match the topic, yet is no longer valid.

An eligible result must satisfy all conditions:

~~~text
Eligible document
    = correct tenant
    AND user is allowed to read
    AND business status is valid
    AND document is within effective dates
    AND vector is sufficiently relevant
~~~

Logical precedence matters:

- Authorization determines which documents the user is permitted to access.
- Business filters determine which documents fit the use case criteria.
- Vector similarity ranks the remaining eligible documents.

Never use similarity scores, boosts, or reranking to represent access permissions. An unauthorized document must be excluded from results regardless of how high its vector score is.

## 2. Distinguishing Authorization and Business Filtering

The two filter groups serve different purposes:

| Group | Examples | Data source |
|---|---|---|
| Authorization | `tenantId`, `ownerId`, ACL principal, group membership, visibility | System security context and policy |
| Business filter | `status`, `category`, price range, `language`, `effectiveAt`, stock status | Use case parameters and business data |
| Retrieval constraint | similarity threshold, candidate count, vector field | Search configuration |

Authorization answers "Is this user allowed to see this document?". A business filter answers "Does this document match the current search criteria?".

For example, a user may have permission to read every document in their tenant, while the current request asks only for published documents in the `security` category. `category` and `status` narrow the result set; they never grant additional access.

### 2.1. Authorization Must Be Derived from Server-Side Identity

Never take the following values directly from query parameters or JSON request bodies and trust them:

- Permitted `tenantId`.
- `userId` used to check ownership.
- `groupIds` or `roleIds`.
- Principal IDs in an ACL.
- A list of fields/permissions to bypass.

These values must come from the authenticated principal, a verified token, or a trusted authorization service. Clients can send query text, categories, or price ranges per the API contract; the server supplies tenant and ACL scope itself.

Unsafe example:

~~~http
GET /knowledge/search?q=tls&tenantId=tenant-beta&userId=user-admin
~~~

If the backend plugs those two parameters straight into the query, callers can switch tenants or impersonate another user.

Safer example:

~~~java
SearchContext context = searchContextFactory.from(authentication);
return searchService.search(request.query(), request.filters(), context);
~~~

`SearchContext` is constructed from the verified authentication. Clients must never supply their own principal IDs.

## 3. Designing Document Fields for Access Control

A document must store enough metadata for queries to enforce access scope. Illustrative mapping:

~~~json
{
  "mappings": {
    "properties": {
      "tenantId": { "type": "keyword" },
      "ownerId": { "type": "keyword" },
      "visibility": { "type": "keyword" },
      "acl": {
        "properties": {
          "principalIds": { "type": "keyword" }
        }
      },
      "status": { "type": "keyword" },
      "category": { "type": "keyword" },
      "language": { "type": "keyword" },
      "price": { "type": "scaled_float", "scaling_factor": 100 },
      "effectiveAt": { "type": "date" },
      "expiresAt": { "type": "date" },
      "deleted": { "type": "boolean" },
      "embedding": {
        "type": "dense_vector",
        "dims": 768,
        "index": true,
        "similarity": "cosine"
      }
    }
  }
}
~~~

Meaning:

- `tenantId` defines the tenant's data boundary.
- `ownerId` stores the document owner.
- `visibility` represents scopes such as `PRIVATE` or `PUBLIC`.
- `acl.principalIds` holds authorized user/group/role principals.
- `status` and `category` support business conditions.
- `effectiveAt` and `expiresAt` define validity windows.
- `deleted` excludes soft-deleted documents.
- `embedding` supports vector similarity.

Fields used in `term`/`terms`/`range` filters require suitable mappings. IDs, status, category, tenant, and principals typically use `keyword`; dates use `date`; prices use numeric types; deletion flags use `boolean`. Never use a full-text analyzer on ACL identifiers.

### 3.1. Use Canonical Principal IDs

Avoid storing display names such as "Engineering Team" or mutable email addresses. Use stable, namespaced IDs:

~~~text
user:8f3a
group:engineering
role:knowledge-reader
service:catalog-indexer
~~~

A document can contain:

~~~json
{
  "tenantId": "tenant-alpha",
  "ownerId": "user:42",
  "visibility": "PRIVATE",
  "acl": {
    "principalIds": [
      "user:42",
      "group:engineering",
      "role:knowledge-reader"
    ]
  }
}
~~~

An authenticated user may hold a set of principals:

~~~text
user:42
group:engineering
group:platform
role:knowledge-reader
~~~

A `terms` query on `acl.principalIds` matches if at least one of the user's principals appears in the ACL list. Group membership expansion must come from a trusted identity provider or authorization service.

### 3.2. Simple Keyword Array or Nested ACL Object?

If permission means simply "this principal may read the document", a keyword array is usually sufficient:

~~~json
{
  "acl": {
    "principalIds": ["user:42", "group:engineering"]
  }
}
~~~

If each grant carries multiple attributes that must match together—such as principal, permission, and expiration—consider a `nested` mapping:

~~~json
{
  "acl": {
    "grants": [
      {
        "principalId": "group:engineering",
        "permission": "READ",
        "expiresAt": "2027-01-01T00:00:00Z"
      },
      {
        "principalId": "user:42",
        "permission": "WRITE",
        "expiresAt": null
      }
    ]
  }
}
~~~

Mapping:

~~~json
{
  "acl.grants": {
    "type": "nested",
    "properties": {
      "principalId": { "type": "keyword" },
      "permission": { "type": "keyword" },
      "expiresAt": { "type": "date" }
    }
  }
}
~~~

With a standard object array, Elasticsearch flattens field values and can match the principal from the first grant with the permission from the second grant. A `nested` query keeps conditions bound within the same grant object.

Nested ACL query example:

~~~json
{
  "nested": {
    "path": "acl.grants",
    "query": {
      "bool": {
        "filter": [
          { "terms": { "acl.grants.principalId": ["user:42", "group:engineering"] } },
          { "term": { "acl.grants.permission": "READ" } }
        ]
      }
    }
  }
}
~~~

Nested mappings incur extra storage and query overhead. Use them only when per-grant attribute correlation must be enforced strictly.

## 4. Common ACL Rules

A straightforward policy may grant read access when:

- The document belongs to the right tenant.
- The document is public within that tenant; or
- The user is the owner; or
- At least one of the user's user/group/role principals holds `READ` permission.

Expression:

~~~text
tenant matches
AND (
    visibility = PUBLIC
    OR ownerId = currentUser
    OR acl.principalIds intersects currentPrincipals
)
~~~

The parenthesized conditions form an `OR`. Tenant is a mandatory outer `AND`. Consequently, a public document in another tenant is still excluded.

### 4.1. Public Does Not Necessarily Mean System-Wide Public

In multi-tenant systems, `PUBLIC` usually means "readable by everyone within this tenant". Keep the `tenantId` filter:

~~~text
tenantId = tenant-alpha
AND visibility = PUBLIC
~~~

If truly system-wide public documents exist, model global scope explicitly, such as via a dedicated scope or dedicated index. Never drop the tenant filter merely because a document has `visibility: PUBLIC`.

### 4.2. Owner and ACL Can Be Merged into the Principal List

You can include the owner principal in `acl.principalIds` at index time:

~~~json
{
  "ownerId": "user:42",
  "acl": {
    "principalIds": ["user:42", "group:engineering"]
  }
}
~~~

Then queries only check `visibility: PUBLIC` or `terms` on `principalIds`. If owners carry special rights distinct from `READ`, keep `ownerId` separate so policies stay clear and testable.

### 4.3. `READ` Permission Differs from `WRITE` Permission

Search queries reading documents typically require only `READ`. Never infer that a user who can read may also update or delete. Write APIs need separate authorization tied to the action and source of truth.

## 5. Business Conditions in Vector Search

Business filters commonly include:

- `status = PUBLISHED`.
- `category` within a selected list.
- `language = vi`.
- `price` within min/max bounds.
- `effectiveAt` already started.
- `expiresAt` not yet reached.
- `stockStatus = IN_STOCK`.
- `deleted = false`.
- Appropriate content type or version.

Example:

~~~json
{
  "bool": {
    "filter": [
      { "term": { "status": "PUBLISHED" } },
      { "terms": { "category": ["security", "platform"] } },
      { "term": { "language": "vi" } },
      { "range": { "price": { "gte": 100000, "lte": 500000 } } },
      { "range": { "effectiveAt": { "lte": "2026-11-13T00:00:00Z" } } },
      { "range": { "expiresAt": { "gt": "2026-11-13T00:00:00Z" } } },
      { "term": { "deleted": false } }
    ]
  }
}
~~~

The current date should be computed in the application/service according to the agreed timezone and business calendar, then passed into the query. This lets tests fix a `Clock` and avoids differing semantics between the service and Elasticsearch.

### 5.1. Hard Constraints and Soft Preferences

Not every condition needs a hard filter:

| Condition type | Examples | How to apply |
|---|---|---|
| Mandatory | Tenant, ACL, non-deleted | Filter, must never be bypassed |
| Business eligibility | Published, active dates, within max budget | Pre-filter |
| Soft preference | Preferred category, recently updated, matching language | Boost or reranking |

If a user says "Vietnamese documents only", `language` is a hard filter. If they say "prefer Vietnamese", `language` can be a soft preference. ACLs are always a hard constraint.

Never convert access control into a boost. An unauthorized document cannot become valid simply by scoring high.

## 6. Pre-Filter and Post-Filter in kNN

This is the most important detail when writing conditional vector queries.

### 6.1. Pre-Filter

A pre-filter sits inside the `knn` clause itself. Elasticsearch applies the condition while searching candidate vectors. The goal is to locate nearest neighbors within documents satisfying the filter.

~~~json
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.31, 0.08],
    "k": 10,
    "num_candidates": 100,
    "filter": {
      "bool": {
        "filter": [
          { "term": { "tenantId": "tenant-alpha" } },
          { "term": { "status": "PUBLISHED" } },
          { "term": { "visibility": "PUBLIC" } }
        ]
      }
    }
  }
}
~~~

If enough documents match the filter, vector search returns top `k` from the eligible document set. This is the right pattern for tenant, ACL, and business conditions with kNN.

### 6.2. Post-Filter

A post-filter executes after kNN has already chosen candidates. Example:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "knn": {
            "field": "embedding",
            "query_vector": [0.12, -0.31, 0.08],
            "k": 10,
            "num_candidates": 100
          }
        }
      ],
      "filter": [
        { "term": { "tenantId": "tenant-alpha" } },
        { "term": { "status": "PUBLISHED" } }
      ]
    }
  }
}
~~~

In Query DSL, filters sitting outside the `knn` query act as post-filters. kNN may pick the 10 globally closest documents across the whole index first, and then `bool.filter` drops documents belonging to other tenants or unpublished items. The response might contain only 2 hits even though many matching documents exist in that tenant.

Post-filtering is not a good way to obtain top `k` within an eligible set. For authorization, you should also not rely on a filter outside `knn` when the system needs to ensure the vector retrieval candidate set is restricted from the start.

### 6.3. Comparison

| Characteristic | Pre-filter inside kNN | Post-filter outside kNN |
|---|---|---|
| Timing | During kNN candidate selection | After kNN has selected candidates |
| Semantics | Finds neighbors inside the eligible set | Re-filters top-k found over a broader set |
| Hit count | Can reach `k` if enough eligible documents and similarity threshold allow | Can return fewer than `k` |
| Suitability for ACL/tenant | Appropriate choice for vector queries | Should not be relied on as the sole filter |
| Performance impact | Highly selective filters can force ANN to visit more nodes | Less filtering work during vector traversal, but prone to missing hits |

Elasticsearch can select different execution strategies depending on filter selectivity and shard vector counts. Pre-filter behavior describes result semantics; it does not guarantee every filter makes queries faster.

### 6.4. `k` and `num_candidates`

- `k` is the target neighbor count.
- `num_candidates` is the number of candidates evaluated per shard.
- Increasing `num_candidates` usually improves recall of approximate search while increasing cost.
- Highly selective filters can require HNSW to explore more nodes to gather enough valid candidates.

Benchmark against realistic tenant/ACL distributions. Do not set `num_candidates` too low and blame filters for missing documents, nor raise it without bound to compensate for wrong mappings or queries.

### 6.5. Similarity Thresholds

kNN can return `k` nearest neighbors even when none are truly relevant. If business logic requires a minimum similarity threshold, use the `similarity` parameter when supported by your version and metric, or evaluate scores under calibrated rules.

A similarity threshold never replaces an ACL. It only filters out insufficiently relevant hits.

## 7. Building Query DSL Filters from `SearchContext`

Create a dedicated service that builds security scope from authentication:

~~~java
public record SearchContext(
        String tenantId,
        String userId,
        Set<String> principalIds) {
}
~~~

Factory:

~~~java
public SearchContext from(Authentication authentication) {
    String tenantId = tenantResolver.requireTenant(authentication);
    String userId = userResolver.requireUserId(authentication);
    Set<String> principals = groupResolver.resolvePrincipals(authentication);

    principals = new HashSet<>(principals);
    principals.add("user:" + userId);

    return new SearchContext(tenantId, userId, Set.copyOf(principals));
}
~~~

Resolvers are internal application components. Never pull `Set<String>` principals from a request body.

### 7.1. Fail Closed When Security Context Is Missing

If tenant or identity cannot be resolved, do not run an unfiltered vector query:

~~~java
if (context.tenantId() == null || context.tenantId().isBlank()) {
    throw new AccessDeniedException("A tenant context is required");
}
~~~

If `principalIds` is empty, the policy may allow only `PUBLIC` documents within the tenant or return empty results. Never drop the entire ACL clause simply because the principal list is empty.

### 7.2. Principal Lists Can Include Users and Groups

Example:

~~~text
user:42
group:engineering
group:platform
role:knowledge-reader
~~~

A `terms` query matches any principal in the list. If policy requires multiple simultaneous conditions—such as user belonging to a tenant and holding `READ` permission—express that logic explicitly with a `bool` filter or `nested` query.

## 8. Vector Queries with Spring Data Elasticsearch `NativeQuery`

Spring Data Elasticsearch provides `NativeQuery` to wrap Elasticsearch Java API Client builders. Starting in Spring Data Elasticsearch 5.4, top-level kNN in `NativeQueryBuilder` is configured with `withKnnSearches`. Pre-filters are attached directly to the `KnnSearch` builder.

kNN-only example:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

List<Float> queryVector = embeddingService.embedQuery(text);
List<FieldValue> principalValues = context.principalIds().stream()
        .map(FieldValue::of)
        .toList();

NativeQuery query = NativeQuery.builder()
        .withKnnSearches(knn -> knn
                .field("embedding")
                .queryVector(queryVector)
                .k(20)
                .numCandidates(200)
                .filter(filter -> filter.bool(bool -> {
                    bool.filter(f -> f.term(t -> t
                            .field("tenantId")
                            .value(FieldValue.of(context.tenantId()))));
                    bool.filter(f -> f.term(t -> t
                            .field("status")
                            .value(FieldValue.of("PUBLISHED"))));
                    bool.filter(f -> f.term(t -> t
                            .field("deleted")
                            .value(FieldValue.of(false))));

                    bool.filter(f -> f.bool(access -> {
                        access.should(s -> s.term(t -> t
                                .field("visibility")
                                .value(FieldValue.of("PUBLIC"))));

                        if (!principalValues.isEmpty()) {
                            access.should(s -> s.terms(t -> t
                                    .field("acl.principalIds")
                                    .terms(values -> values.value(principalValues))));
                        }

                        return access.minimumShouldMatch("1");
                    }));

                    return bool;
                })))
        .build();

SearchHits<KnowledgeDocument> hits = operations.search(
        query,
        KnowledgeDocument.class,
        IndexCoordinates.of("knowledge-documents"));
~~~

This example uses the flattened ACL field `acl.principalIds`. The access condition specifies that the document is public in the tenant or shared with at least one of the user's principals. `tenantId`, `status`, and `deleted` remain mandatory filters.

Builder method names reflect the current Spring Data Elasticsearch and Elasticsearch Java API Client APIs. On other releases, verify your dependency's API version; never move a pre-filter to another position just to make code compile.

### 8.1. Using Dynamic Business Filters

You can add `category`, `language`, or date range filters from validated requests. Query DSL example:

~~~json
{
  "bool": {
    "filter": [
      { "term": { "tenantId": "tenant-alpha" } },
      { "term": { "status": "PUBLISHED" } },
      { "terms": { "category": ["security", "platform"] } },
      { "term": { "language": "vi" } },
      { "range": { "effectiveAt": { "lte": "2026-11-13T00:00:00Z" } } },
      { "range": { "expiresAt": { "gt": "2026-11-13T00:00:00Z" } } }
    ]
  }
}
~~~

These filters can be appended to the same `bool` filter inside `KnnSearch.filter`. Never let clients supply raw Query DSL or arbitrary field names.

### 8.2. Do Not Confuse `NativeQueryBuilder.withFilter` with `KnnSearch.filter`

`NativeQueryBuilder` exposes multiple hooks such as `withQuery`, `withFilter`, and `withKnnSearches`. For top-level kNN pre-filtering, the filter must live on the `KnnSearch` built inside `withKnnSearches`. Placing a filter elsewhere in `SearchRequest` does not automatically turn it into a kNN pre-filter.

Verify the actual JSON request via integration tests or safe logging during upgrades. Never infer semantics solely from a method name containing the word `filter`.

## 9. Using `knn` Query Inside Query DSL

Elasticsearch also supports a `knn` query inside the `query` clause. In that case, place the filter directly inside the `knn` query:

~~~json
{
  "query": {
    "knn": {
      "field": "embedding",
      "query_vector": [0.12, -0.31, 0.08],
      "k": 20,
      "num_candidates": 200,
      "filter": {
        "bool": {
          "filter": [
            { "term": { "tenantId": "tenant-alpha" } },
            { "term": { "status": "PUBLISHED" } },
            { "terms": { "acl.principalIds": ["user:42", "group:engineering"] } }
          ]
        }
      }
    }
  }
}
~~~

If you need an `OR` between public visibility and principal ACL, nest `bool.should` with `minimum_should_match = 1` inside the `filter` object. Do not place public/ACL conditions as a sibling filter outside `knn`.

In Spring Data, Query DSL `knn` queries can be constructed via `withQuery` on `NativeQueryBuilder` when your Java API Client version supports the corresponding builder. Top-level `KnnSearch` and query-level `KnnQuery` are different request types; Spring Data switched to `withKnnSearches` for top-level kNN in 5.4.

## 10. Combined Tenant, ACL, and Business Filter Example

Suppose a user searches documents in tenant alpha, requesting only published, unexpired documents in categories `security` or `platform` that they have permission to read.

Illustrative REST query:

~~~http
POST knowledge-documents/_search
{
  "knn": {
    "field": "embedding",
    "query_vector": [0.12, -0.31, 0.08],
    "k": 20,
    "num_candidates": 200,
    "filter": {
      "bool": {
        "filter": [
          { "term": { "tenantId": "tenant-alpha" } },
          { "term": { "status": "PUBLISHED" } },
          { "term": { "deleted": false } },
          { "terms": { "category": ["security", "platform"] } },
          { "range": { "effectiveAt": { "lte": "2026-11-13T00:00:00Z" } } },
          { "range": { "expiresAt": { "gt": "2026-11-13T00:00:00Z" } } },
          {
            "bool": {
              "should": [
                { "term": { "visibility": "PUBLIC" } },
                {
                  "terms": {
                    "acl.principalIds": [
                      "user:42",
                      "group:engineering",
                      "role:knowledge-reader"
                    ]
                  }
                }
              ],
              "minimum_should_match": 1
            }
          }
        ]
      }
    }
  }
}
~~~

Conditions inside `filter` are `AND`-ed. The two branches inside the ACL `should` are `OR`-ed. `minimum_should_match = 1` guarantees the document must either be public or granted to at least one principal.

If you omit `minimum_should_match`, a `bool` containing other `filter`/`must` clauses may not require any `should` clause to match by default; the ACL `OR` would cease to be enforced as intended.

## 11. Nested Grant ACLs

When each grant holds principal, permission, and expiration, the query must ensure all conditions belong to the same grant:

~~~json
{
  "nested": {
    "path": "acl.grants",
    "query": {
      "bool": {
        "filter": [
          {
            "terms": {
              "acl.grants.principalId": [
                "user:42",
                "group:engineering"
              ]
            }
          },
          {
            "term": {
              "acl.grants.permission": "READ"
            }
          },
          {
            "bool": {
              "should": [
                { "bool": { "must_not": { "exists": { "field": "acl.grants.expiresAt" } } } },
                { "range": { "acl.grants.expiresAt": { "gt": "2026-11-13T00:00:00Z" } } }
              ],
              "minimum_should_match": 1
            }
          }
        ]
      }
    }
  }
}
~~~

Place this `nested` query inside `KnnSearch.filter` so it acts as a pre-filter. Elasticsearch supports nested filters inside kNN filters subject to your running version's constraints; consult docs and integration tests when combining nested ACLs with vector search.

With nested ACLs, be careful when a document holds multiple grants for the same principal with differing permissions or expirations. The objective is verifying a single unexpired `READ` grant, not mixing fields across separate grants.

## 12. Which Business Filters Should Run Before Vector Retrieval?

Conditions that exclude ineligible documents should apply before or during vector retrieval:

- Tenant and ACL.
- Required status `PUBLISHED`.
- Non-deleted documents.
- Price within a strict budget.
- Active effective dates.
- Mandatory locale.
- In-stock products when the use case only shows purchasable items.

Conditions affecting only ranking order can be applied afterward:

- Favoring recently updated documents.
- Favoring preferred categories.
- Favoring official sources.
- Favoring preferred language when other languages remain acceptable.

One classification:

~~~text
Hard constraints
  -> filter candidate set
  -> vector retrieval

Soft preferences
  -> score boost / fusion / reranking
  -> final ordering
~~~

Never replace hard filters with boosts. Never use post-filtering for ACLs when trying to retrieve top `k` within authorized documents.

## 13. Hybrid Search Must Filter Every Branch

A hybrid system can execute lexical retrieval and vector retrieval and then fuse results. Both branches must enforce identical tenant, ACL, and business constraints.

Query DSL example:

~~~json
{
  "query": {
    "bool": {
      "should": [
        {
          "bool": {
            "must": [
              {
                "multi_match": {
                  "query": "configure TLS verification",
                  "fields": ["title^3", "content"]
                }
              }
            ],
            "filter": [
              { "term": { "tenantId": "tenant-alpha" } },
              { "term": { "status": "PUBLISHED" } },
              {
                "bool": {
                  "should": [
                    { "term": { "visibility": "PUBLIC" } },
                    {
                      "terms": {
                        "acl.principalIds": ["user:42", "group:engineering"]
                      }
                    }
                  ],
                  "minimum_should_match": 1
                }
              }
            ]
          }
        },
        {
          "knn": {
            "field": "embedding",
            "query_vector": [0.12, -0.31, 0.08],
            "k": 50,
            "num_candidates": 200,
            "filter": {
              "bool": {
                "filter": [
                  { "term": { "tenantId": "tenant-alpha" } },
                  { "term": { "status": "PUBLISHED" } },
                  {
                    "bool": {
                      "should": [
                        { "term": { "visibility": "PUBLIC" } },
                        {
                          "terms": {
                            "acl.principalIds": ["user:42", "group:engineering"]
                          }
                        }
                      ],
                      "minimum_should_match": 1
                    }
                  }
                ]
              }
            }
          }
        }
      ],
      "minimum_should_match": 1
    }
  }
}
~~~

The lexical branch carries its own `bool.filter`. The vector branch carries `filter` inside `knn`. Do not assume a filter on a parent `bool` automatically becomes a kNN pre-filter.

If using the retriever/RRF API, apply the exact same authorization/business policy to every sub-retriever. One un-filtered branch can still inject unauthorized documents into the candidate set.

### 13.1. Result Fusion Is Not an Authorization Step

RRF or rerankers only reorder candidates. They do not replace ACLs. Do not wait until after fusion to drop unauthorized items when policy can be enforced directly inside retrievers.

If a final authorization check runs right before returning the response, treat it as defense-in-depth against stale ACL projections rather than the primary mechanism constraining vector retrieval.

### 13.2. Candidate Counts and Filter Consistency

Each branch can yield a different candidate count. Pick suitable `k`/candidate sizes, but never relax permissions to compensate for sparse results. When a tenant is small or ACLs are very selective, tune `num_candidates` and measure recall over the eligible set.

## 14. Elasticsearch Document-Level Security

Elasticsearch provides Document-Level Security (DLS) to attach queries restricting which documents a role may read. DLS adds a layer of protection when clients authenticate using credentials bound to corresponding identities/roles.

Example role query restricting documents by username/metadata:

~~~json
{
  "indices": [
    {
      "names": ["knowledge-documents"],
      "privileges": ["read"],
      "query": {
        "template": {
          "source": {
            "terms": {
              "acl.principalIds": "{{#toJson}}_user.metadata.principal_ids{{/toJson}}"
            }
          }
        }
      }
    }
  ]
}
~~~

In this example, the Elasticsearch user's metadata holds normalized principal IDs such as `user:42` and `group:engineering`. Role queries can use Mustache templates to read username, roles, or metadata of the authenticated Elasticsearch user. For array/object metadata, templates can use `toJson` per Elasticsearch guidance. Metadata names and group synchronization must match your actual identity model.

### 14.1. Application Filters and DLS Address Two Different Layers

| Approach | Identity used | Responsibility |
|---|---|---|
| Application-level filter | End user from application security context | Backend attaches tenant/ACL filters to every query |
| Elasticsearch DLS | User/API key authenticated by Elasticsearch | Elasticsearch restricts documents by role query |
| Combined | Both | Defense in depth, though semantics across both layers must be tested |

If all backend requests share a single Elasticsearch service account, DLS sees only that service account. It does not automatically know which end user called the API. In that setup, the backend must still build ACL filters from the authenticated principal.

If users or services hold distinct Elasticsearch credentials, DLS can use credential metadata to restrict documents. Ensure roles and API keys are scoped properly.

### 14.2. DLS Does Not Replace All Authorization Logic

DLS is designed primarily for read-only access. Elastic documentation notes that write operations should not be performed by users carrying DLS/FLS on the target index. Writes, updates, and deletes still require separate policies.

DLS also has limitations: global index statistics used for relevance scoring are not restricted by role queries; certain aggregations or queries can leak summary insights about excluded documents. When strict isolation is required, carefully evaluate aggregations, suggestions, and metadata, and consider splitting indexes along security boundaries.

### 14.3. Multiple Roles Combine with `OR`

When an Elasticsearch user holds multiple roles applying DLS on the same index, the document queries across roles are combined using `OR`. Another role lacking DLS can grant read access to every document in the index.

Audit the combined role set of actual users and API keys. Never test only a single role in isolation.

### 14.4. Filtered Aliases Are Not a Security Boundary

Filtered aliases can be convenient for search use cases, yet should not serve as the sole security mechanism preventing access to other documents. Elastic recommends using DLS for document-level access protection. Audit index privileges, alias privileges, and APIs that could reach backing indexes.

## 15. Field-Level Security and Sensitive Data

Document-level ACLs determine which documents can be read. Field-Level Security (FLS) restricts which fields a role can read. These are two distinct concerns.

For instance, a user may view a document yet must not read:

- `internalNotes`.
- `customerEmail`.
- `costPrice`.
- `securityReview`.

Do not rely on application query source filtering as a security mechanism. Source filtering merely asks Elasticsearch to omit certain fields from the response; users permitted to query directly can still request other fields if their security role allows it.

For genuinely sensitive fields, use FLS, separate documents/indexes, or exclude those fields from projections accessible to unauthorized users.

## 16. ACL Updates and Synchronization Lag

ACLs are often managed in a database or authorization service and synced to Elasticsearch. When permissions change, document projections must update:

~~~text
Permission source changes
        |
        v
Outbox / CDC event
        |
        v
ACL projection consumer
        |
        v
Update tenant/ACL fields in Elasticsearch
        |
        v
Refresh makes new ACL searchable
~~~

With eventual consistency, there is a window between revoking permissions at the source and updating the ACL in Elasticsearch. For sensitive content, never assume this lag is acceptable.

Options:

- Update ACL projections synchronously before confirming permission changes.
- Use outbox events and appropriate refresh policies when search visibility is needed.
- Perform a final authorization check against the source of truth before returning sensitive content.
- Use DLS or index separation for an added protective boundary.
- Maintain a short-lived deny/revocation list while projections catch up.

A final check prior to returning responses can leave fewer than `k` results; the backend can fetch further candidates if needed, capping retries and ensuring unauthorized content never leaks into logs or caches.

### 16.1. ACL Version

You can store `aclVersion` or `permissionUpdatedAt` in documents to monitor projection freshness:

~~~json
{
  "tenantId": "tenant-alpha",
  "acl": {
    "principalIds": ["user:42", "group:engineering"]
  },
  "aclVersion": 27
}
~~~

Versions help reconcile sources with projections and detect lagging consumers. They do not block access on their own unless queries check them or source policies are enforced.

### 16.2. Revoking Access Differs from Deleting Documents

When revoking group access, update the ACL list to remove that principal. When a user is deactivated, update identity/group expansion or check principal status. Deleting the document is not necessary.

When deleting a document, update tombstone/`deleted` fields and ensure vector retrieval filters exclude it.

## 17. Caching and Authorization Context

Search results may be cached in the application, API gateway, or query layer. Cache keys must include every factor affecting which documents are permitted:

- `tenantId`.
- `userId` or set of principal IDs.
- Role/group membership version.
- ACL policy version if applicable.
- Business filters.
- Query text or query hash.
- Embedding model version.
- Index/projection version.

Never cache results for user A and serve them to user B just because query text matches. Never use `tenantId` as the sole cache key when ACLs vary among users within the same tenant.

When group memberships or ACLs change, invalidate caches or enforce TTLs/policies matching data sensitivity. When instant revocation is required, stale caches must never continue serving newly revoked results.

## 18. Aggregations, Counts, and Metadata Also Need Scoping

Hits are not the only way data can leak. The following can also reveal sensitive details:

- Total hits.
- Aggregations by category or department.
- Facet counts.
- Highlight fragments.
- Suggestions.
- Inner hits.
- Error messages containing index/document identifiers.

If application filters form the security boundary, ensure aggregations and counts share the exact same query scope. Never run an index-wide count and return the total to a user restricted by ACLs.

When using DLS, note Elastic's documentation that global index statistics and certain aggregation/query patterns can still disclose aggregate information about documents not returned directly. For strict isolation, consider separate indexes or a controlled aggregation service.

## 19. Multi-Tenant: Mandatory Filters and Index Separation

Several tenant isolation strategies exist:

| Strategy | Advantages | Limitations |
|---|---|---|
| Shared index + `tenantId` filter | Fewer indexes, easier operations | Every query path must enforce tenant filters |
| Per-tenant index | Stronger index isolation | More indexes/shards, complex lifecycle management |
| Dedicated cluster/deployment | Strongest operational boundary | High cost and complexity |

With a shared index, `tenantId` must be a mandatory filter inside vector pre-filters and lexical branches. When tenant isolation is strict, consider per-tenant indexes or dedicated deployments combined with Elasticsearch privileges.

Never trust a `tenantId` from the request as the sole source. Derive tenants from verified identity, then verify the user is authorized to select that tenant.

### 19.1. Tenant Filters and Routing

Custom routing by tenant can co-locate a tenant's documents onto the same shard, improving efficiency for tenant-scoped queries. However, routing is not authorization. Users with index access could still probe another routing value if the security layer does not block it.

If using routing, keep routing keys consistent across index/get/update/delete operations while still enforcing tenant/ACL filters.

## 20. Performance When Filtering Vector Search

Filters inside kNN influence how ANN traverses the vector graph. With selective filters, HNSW may need to visit additional nodes to collect enough eligible candidates. Elasticsearch may fall back to brute-force over segments in some cases.

Measure on real data:

- Share of documents per tenant.
- Share of public or shared documents.
- Average number of principals per document.
- Number of groups per user.
- Shards and vectors per shard.
- `k` and `num_candidates`.
- p50/p95/p99 latency.
- Filtered Recall@k.

### 20.1. Oversized ACL Lists

If a document is shared with tens of thousands of individual users, `acl.principalIds` arrays can grow huge and costly to update. Consider:

- Sharing via groups/roles instead of individual users.
- Normalizing group membership in the identity service.
- Using nested grants only when permission tuples are needed.
- Separating public/tenant/group scopes.
- Partitioning indexes along natural boundaries.
- Caching principal expansion server-side with explicit versioning/invalidation.

Never expand full group memberships from an untrusted source on every request.

### 20.2. Controlled `num_candidates` Increases

Raising `num_candidates` can recover recall at higher CPU and latency cost. When filters are highly selective, benchmark filter selectivity alongside candidate budgets. Never drop ACL filters to reduce `num_candidates`.

### 20.3. Filter Exact Fields

Use `term`/`terms` on `keyword`, `range` on numeric/date, and `exists` where needed. Avoid wildcards or script filters for ACLs when explicit fields can model the policy cleanly; complex filter queries raise execution costs.

## 21. Structuring Code So Security Filters Are Never Forgotten

Do not let every controller assemble ACL Query DSL manually. Centralize a shared policy/query factory:

~~~text
Controller
   |
   v
Authentication + SearchRequest
   |
   v
SearchContextFactory
   |
   v
AccessPolicy / FilterFactory
   |
   +---- tenant filter
   +---- owner/public/group ACL
   +---- status/date/tenant business filters
   |
   v
VectorSearchRepository
   |
   v
ElasticsearchOperations
~~~

A contract:

~~~java
public interface SearchFilterFactory {
    Query buildMandatoryKnnFilter(
            SearchContext context,
            KnowledgeSearchFilters filters);
}
~~~

Repositories accept `SearchContext` or a query built by the policy factory. Never allow callers to bypass filters by passing `null` or arbitrary raw queries.

### 21.1. Distinguishing Mandatory and Optional Filters

Use two distinct objects:

- `MandatorySearchScope`: tenant, ACL, status/deleted constraints.
- `OptionalSearchFilters`: category, date range, language, price.

When building queries, mandatory scope is always applied. Optional filters may only narrow the result set further.

If an API exposes an "include archived" or "search all statuses" toggle, enforce it as a distinct verified permission/capability, not merely a client-supplied boolean.

### 21.2. Never Expose Raw Query DSL Through APIs

Do not accept arbitrary JSON Query DSL from frontends and forward it straight to Elasticsearch. Clients could strip ACL filters, probe sensitive fields, or trigger expensive queries.

Accept a request DTO with whitelisted fields, validate values, and construct Query DSL strictly on the backend.

## 22. Testing Access Control in Vector Search

Tests must assert both allowed results and denied results. Checking vector ranking alone is insufficient.

Sample fixture:

| Document | Tenant | ACL | Status | Category |
|---|---|---|---|---|
| A | alpha | `group:engineering` | PUBLISHED | security |
| B | alpha | `user:99` | PUBLISHED | security |
| C | alpha | `PUBLIC` | PUBLISHED | platform |
| D | beta | `PUBLIC` | PUBLISHED | security |
| E | alpha | `group:engineering` | DRAFT | security |
| F | alpha | `group:engineering` | PUBLISHED, expired | security |

Test user:

~~~text
tenant = alpha
principals = [user:42, group:engineering]
~~~

Expected results:

- A is returned.
- C is returned if `PUBLIC` means public within tenant alpha.
- B is not returned.
- D is not returned despite `PUBLIC` because it belongs to a different tenant.
- E is not returned because it is `DRAFT`.
- F is not returned because it is expired.

### 22.1. Testing Tenant Isolation

Create documents in another tenant whose vectors are closer to the query than every document in the current tenant. Search must still return only documents belonging to the authenticated tenant.

This test catches bugs where filters sit outside `knn` and pull candidates from the whole index.

### 22.2. Testing Group Membership

Users in `group:engineering` can read documents bearing principal `group:engineering`. Once group membership is revoked, a fresh query context omits that principal and the document disappears from results.

### 22.3. Testing Public Scope

`PUBLIC` documents in the same tenant are readable; `PUBLIC` documents in another tenant remain excluded. This confirms `PUBLIC` does not accidentally bypass the tenant boundary.

### 22.4. Testing Business Filters

Verify `status`, `deleted`, date ranges, `price`, and `category` apply alongside ACLs. Specifically test `effectiveAt`/`expiresAt` right on boundary timestamps.

### 22.5. Testing Pre-Filter vs. Post-Filter

Insert many nearest vectors where most belong to another tenant. With a pre-filter, the query still recovers top `k` within the tenant when enough eligible data exists. With a post-filter, responses can shrink below `k`. Tests should enforce the semantics guaranteed by the repository.

### 22.6. Testing Fail-Closed Behavior

When tenant, authentication, or principal context is missing, the backend must never execute an unfiltered query. It should fail with `AccessDenied`/`BadRequest` per API contract or return empty results per policy.

### 22.7. Testing Hybrid Branches

Place an unauthorized document at the top of both lexical and vector rankings. Both branches must exclude it prior to merging. Verify RRF/reranking cannot reintroduce unauthorized documents.

### 22.8. Testing ACL Revocation and Caching

Revoke access, update projections/caches, and verify the user can no longer retrieve the content. Where eventual consistency applies, tests must explicitly document bounds and safeguards during the sync window.

## 23. Diagnosing Vector Searches That Return Too Few or Zero Hits

When filters appear too broad or too narrow, isolate the cause:

| Symptom | Possible cause | How to inspect |
|---|---|---|
| Zero hits | Wrong `tenantId` or empty principal list | Inspect `SearchContext` without logging sensitive data |
| Only public docs returned | ACL `terms` fail to match | Check canonical principal IDs and `keyword` mapping |
| Fewer hits despite eligible docs | Filter acts as a post-filter | Check filter placement inside the `knn` clause |
| Users in same group see different hits | Inconsistent group expansion | Check identity provider and membership cache |
| Recently revoked user still sees doc | ACL projection/cache not updated yet | Check event lag, refresh, and cache invalidation |
| Query slow under selective filters | ANN graph visits many candidates | Benchmark `num_candidates`, shards, and selectivity |
| Hybrid returns unauthorized hits | One retriever branch lacks filters | Inspect every lexical/vector/retriever branch |
| Public docs leak across tenants | `PUBLIC` bypasses tenant filter | Keep `tenantId` in mandatory `AND` scope |

Never debug by disabling ACL filters in production. Use test indexes, query fixtures, or staging environments with synthetic data.

## 24. Common Mistakes

### Filtering Only After Vector Search

Results can fall short of `k`, and candidates are gathered over a broader set. Place mandatory conditions inside the kNN `filter`.

### Leaving ACLs in an Optional `should`

When a `bool` has other `filter`/`must` clauses, `should` may not be mandatory by default. Nest a `bool` with `minimum_should_match = 1` for the public-or-principal check.

### Reading `tenantId` from the Request

Users could switch tenants. Derive `tenantId` from verified authentication and check permission to access that tenant.

### Reading `principalIds` from the Client

Clients could spoof groups/roles. Resolve group memberships server-side.

### Using `match` on ACL Keywords

ACL identifiers are structured values. Use `term`/`terms` on `keyword` fields.

### Forgetting Business Filters in the Vector Branch

Lexical and vector branches can return mismatched sets. Replicate the corresponding policy in every retriever.

### Treating Filter Scores as Authorization

Boosts alter ranking only; they never exclude unauthorized documents. ACLs must be hard filters or DLS.

### Relying on Filtered Aliases as a Security Boundary

Alias filters do not replace DLS. Enforce proper index privileges and document-level security.

### Assuming DLS Knows End Users Through a Shared Service Account

Elasticsearch only sees the service credential's identity. The backend must still apply end-user ACLs from application context.

### Treating Source Filtering as FLS

Source filtering is not field-level access control. Use FLS or separate projections for sensitive fields.

### Failing to Update ACL Projections When Permissions Change

Documents can continue appearing under stale ACLs. Monitor lag and build a revocation path.

### Caching Search Results Without User/Tenant Scope

Cache keys lacking security context can leak another user's data. Include tenant and principal/policy version in keys.

### Dropping Filters When the Principal List Is Empty

Doing so can expose the entire index. Fail closed or allow only the tenant's `PUBLIC` branch per policy.

### Dropping Filters to Reduce `num_candidates`

Doing so breaks security boundaries. Tune candidate counts and mappings while keeping filters intact.

### Forgetting Scope on Aggregations and Counts

Hits may be restricted while totals/aggregations still leak information. Enforce scope and assess DLS limitations.

## 25. Implementation Workflow for Access-Controlled Vector Queries

When building vector search in Spring Data Elasticsearch:

1. Identify the source of truth for tenants, users, groups, and ACLs.
2. Define document identity and metadata fields for authorization.
3. Map `tenantId`, `ownerId`, `visibility`, principal IDs, and business fields as `keyword`/numeric/`date`/`boolean` appropriately.
4. Choose flattened keyword ACLs or nested grants according to permission semantics.
5. Build `SearchContext` server-side from the authenticated principal.
6. Fail closed when tenant or identity is missing.
7. Construct mandatory filters covering tenant, ACL, `deleted`/status, and required business constraints.
8. Place filters inside `KnnSearch.filter` or `KnnQuery.filter` for pre-filtering.
9. Never assume `NativeQueryBuilder.withFilter` elsewhere automatically acts as a kNN pre-filter.
10. Enforce identical authorization/business policies across lexical and every hybrid retriever.
11. Use DLS/FLS or index separation when Elasticsearch-layer enforcement is required.
12. Design ACL updates/revocation, refresh handling, and cache invalidation.
13. Measure latency and recall with realistic filter selectivity and principal cardinality.
14. Test tenant boundaries, group ACLs, public scope, business filters, pre/post-filtering, and hybrid branches.
15. Test aggregations, caching, and permission revocation.
16. Monitor ACL projection lag, authorization denials, and reconciliation results.

## 26. Summary

Vector similarity ranks documents solely by embedding proximity; it never decides whether a user is allowed to read a document or whether business criteria are met. A valid query must apply tenant and ACL rules as hard constraints, combine conditions like `status`, `category`, `price`, and validity dates, and only then select matching vectors from that eligible set.

In Elasticsearch kNN, filters placed inside the `knn` clause act as pre-filters. Filters placed outside `knn` can become post-filters and return fewer than `k` hits even when eligible documents exist. With Spring Data Elasticsearch, top-level kNN is configured via `NativeQueryBuilder.withKnnSearches`; attach filters directly to the `KnnSearch` builder. Never assume any method named `withFilter` creates a kNN pre-filter.

Authorization context must originate from verified identity. Client-supplied tenants and principal IDs must never be trusted. Use `keyword` fields for tenants, ACLs, and statuses; use nested grants when principal, permission, and expiration must align within the same object. For hybrid search, every retriever branch must enforce identical policies.

Application-level filtering fits when the backend accesses Elasticsearch through a shared service account for multiple end users. Elasticsearch DLS can add document-level boundaries for authenticated Elasticsearch users, though it carries limitations and cannot identify end users behind a shared backend credential. Filtered aliases and source filtering do not replace security controls. Finally, ACL synchronization, cache invalidation, aggregation scoping, and revocation testing are just as vital as writing the kNN query itself.

## References

- [Spring Data Elasticsearch – Elasticsearch Operations and NativeQuery](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch – NativeQueryBuilder API 6.1.2](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/NativeQueryBuilder.html)
- [Spring Data Elasticsearch – Migration guide 5.3 to 5.4: kNN API](https://docs.spring.io/spring-data/elasticsearch/reference/6.2/migration-guides/migration-guide-5.3-5.4.html)
- [Elasticsearch – kNN query and pre-filters/post-filters](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-knn-query)
- [Elasticsearch – Filter approximate kNN results](https://www.elastic.co/docs/solutions/search/vector/knn/filtered-knn-search)
- [Elasticsearch – kNN search](https://www.elastic.co/docs/solutions/search/vector/knn)
- [Elasticsearch – Document and field level security](https://www.elastic.co/docs/deploy-manage/users-roles/cluster-or-deployment-auth/controlling-access-at-document-field-level)
- [Elasticsearch – Security limitations](https://www.elastic.co/docs/deploy-manage/security/limitations)
- [Elasticsearch – Filtered aliases](https://www.elastic.co/docs/manage-data/data-store/aliases)
