# Controlling Returned Fields and Sensitive Data in `_source`

Elasticsearch stores document contents in the `_source` field according to index configuration. When an application executes a search, responses normally include the entire document source. If an entity holds internal information such as personal emails, phone numbers, street addresses, internal notes, tokens, or other sensitive data, returning the raw source through an API can expose information users do not need or are not permitted to see.

Spring Data Elasticsearch lets applications control returned data via source filtering, projections, and mappings. However, three goals must be kept distinct:

- **Reducing payload:** returning only the fields needed for a given query.
- **Data design:** avoiding storing or indexing fields a search use case does not need.
- **Access security:** preventing unauthorized users or services from reading sensitive data.

Source filtering primarily addresses the first goal. It is not an authorization mechanism. If a field remains in the document and mapping, a caller with query privileges can still search, aggregate, or retrieve that field through other APIs. Security must be enforced at the application layer and via Elasticsearch security controls.

## 1. What Is `_source`?

When indexing a document, Elasticsearch typically retains the original JSON in a metadata field named `_source`. Example:

    PUT customers/_doc/c-100
    {
      "name": "Nguyen An",
      "email": "an@example.com",
      "phone": "+84-900-123-456",
      "address": {
        "city": "Ho Chi Minh City",
        "street": "Example Street"
      },
      "internalNote": "Customer requested a private callback"
    }

A default search response returns that source:

    GET customers/_search
    {
      "query": {
        "term": {
          "name.keyword": "Nguyen An"
        }
      }
    }

The `hits.hits[n]._source` section holds the stored document JSON. If the service forwards the raw entity or source into an HTTP response, internal fields can leak unintentionally.

`_source` is useful for:

- Returning the original document after search.
- Mapping JSON into entities with Spring Data.
- Reindexing data into another index.
- Updating documents using source-based workflows.
- Debugging or inspecting data.

Do not treat `_source` as a hidden vault. Access to indices and documents must be controlled separately.

## 2. What Is Source Filtering?

Source filtering lets a search request return only a subset of `_source`. You can select fields to retrieve with `includes` or omit unwanted fields with `excludes`.

Example returning only `name` and `city`:

    GET customers/_search
    {
      "_source": {
        "includes": [
          "name",
          "address.city"
        ]
      },
      "query": {
        "match_all": {}
      }
    }

The response source contains only the selected fields:

    {
      "name": "Nguyen An",
      "address": {
        "city": "Ho Chi Minh City"
      }
    }

Example excluding `internalNote`:

    GET customers/_search
    {
      "_source": {
        "excludes": [
          "internalNote",
          "address.street"
        ]
      },
      "query": {
        "match_all": {}
      }
    }

Source filtering applies to that request's response. It does not remove fields from the document stored in the index.

## 3. `includes` and `excludes`

There are two ways to specify returned fields:

- **`includes`:** specifies fields allowed to appear in the response source.
- **`excludes`:** specifies fields omitted from the response source.

Example:

    "_source": {
      "includes": [
        "id",
        "name",
        "price"
      ],
      "excludes": [
        "internal.*"
      ]
    }

When both `includes` and `excludes` are used together, Elasticsearch selects fields matching `includes` and then removes fields matching `excludes`. For sensitive data, an `includes` allowlist is easier to govern than an `excludes` denylist, because newly added mapping fields will not appear automatically unless explicitly permitted.

`excludes` is convenient when dropping a couple of fields from an internal response, yet poses a risk as documents evolve. If a new sensitive field is added later and `excludes` is not updated, that field can start leaking.

### Wildcards and nested paths

Source filtering supports field name patterns. Example:

    "_source": {
      "includes": [
        "profile.*",
        "preferences.language"
      ],
      "excludes": [
        "profile.private*"
      ]
    }

For nested objects, you can select subfields using dot paths such as `address.city`. Check actual responses to verify the source structure matches your DTO and does not inadvertently pull in an entire object containing sensitive fields.

Avoid broad wildcards like `*` or `profile.*` if that object might receive private fields in the future. Explicit field allowlists are safer and easier to review.

## 4. Source Filtering Is Not Field-Level Security

This is the most important boundary:

| Mechanism | Purpose | Protects Fields from Unauthorized Callers? |
|---|---|---|
| Request-time source filtering | Shrinks fields in a request response | Not by itself |
| Mapping `_source` includes/excludes | Adjusts stored source | Not authorization |
| Application DTO/projection | Shapes business API responses | Can help if all data paths go through this logic |
| Elasticsearch field-level security | Restricts readable fields by role | Yes, when properly configured and enforced |
| Elasticsearch document-level security | Restricts accessible documents | Yes, when properly configured and enforced |
| Index roles/privileges | Restricts which APIs/indices a principal can use | Yes, within granted scope |

A client holding direct search access on an index with permission to read source can simply send another request without the application's source filter. Never treat a source filter on a repository query as a system-wide security barrier.

If users access Elasticsearch directly, configure authentication, authorization, index privileges, and field/document-level security matching your version and deployment tier.

If only the backend accesses Elasticsearch, the backend must verify user permissions before running queries and shape response DTOs. Never hand Elasticsearch credentials or broad index permissions to browser/mobile clients.

## 5. Source Filtering Does Not Prevent Querying Hidden Fields

Suppose a request returns only `name`:

    GET customers/_search
    {
      "_source": {
        "includes": [
          "name"
        ]
      },
      "query": {
        "term": {
          "email.keyword": "an@example.com"
        }
      }
    }

The response may omit `email` from `_source`, yet the query can still match on `email` if the field is indexed and the caller is allowed to run that query.

Similarly, fields omitted from `_source` responses can still be used in:

- `term`, `range`, `match`, or other queries.
- `sort`.
- `aggregations`.
- Scripts if mappings and privileges permit.
- `fields` or `docvalue_fields`.

This creates an inference channel. For example, a caller who cannot see `email` can test whether a document matches a specific email address or run an aggregation to enumerate values.

If a group of users must not access a field, restrict query/aggregation capabilities and field read access at the security layer rather than merely hiding it from `_source`.

## 6. Source Filtering in Spring Data Elasticsearch

Spring Data Elasticsearch supports source filtering via its query abstractions. In modern versions, you can pass `FetchSourceFilter` with `includes` and `excludes` to a query:

    String[] includes = {
        "name",
        "address.city"
    };

    String[] excludes = {
        "internalNote",
        "address.street"
    };

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .matchAll(m -> m)
        )
        .withSourceFilter(
            new FetchSourceFilter(includes, excludes)
        )
        .build();

    SearchHits<Customer> hits =
        operations.search(query, Customer.class);

Packages, constructors, and attachment methods depend on the Spring Data Elasticsearch version. Some versions expose different `SourceFilter` constructors or builders. Check Javadoc/IDE autocompletion for your resolved dependencies instead of copying verbatim from another major version.

With `NativeQuery`, queries are constructed via the Elasticsearch Java API Client. Source filters remain response configuration and do not alter mappings or access rights.

## 7. Source Filters with Query Builders and `Query` Abstractions

When using query abstractions instead of `NativeQuery`, supported versions allow setting a source filter directly on `Query`:

    Query query = NativeQuery.builder()
        .withQuery(q -> q
            .term(t -> t
                .field("status")
                .value("ACTIVE")
            )
        )
        .withSourceFilter(
            new FetchSourceFilter(
                new String[] {"name", "email"},
                new String[] {"internalNote"}
            )
        )
        .build();

    SearchHits<Customer> hits =
        operations.search(query, Customer.class);

This only illustrates where the configuration attaches. Query types, builder methods, and packages may differ in older versions or with other template APIs.

When queries are reused across endpoints, avoid sharing a single query object with an overly broad source filter without checking each caller's permissions. Build queries and DTOs per use case so fields cannot leak through another endpoint.

## 8. Returning a Subset of Source for Search APIs

A public endpoint typically needs only a small set of fields. Define a dedicated DTO:

    public record CustomerSearchItem(
        String id,
        String name,
        String city
    ) {}

The service maps `SearchHit` to the DTO:

    List<CustomerSearchItem> items =
        hits.getSearchHits().stream()
            .map(hit -> new CustomerSearchItem(
                hit.getId(),
                hit.getContent().getName(),
                hit.getContent().getAddress().getCity()
            ))
            .toList();

The DTO establishes an explicit allowlist for the response. Even though `Customer` contains `email`, `phone`, `address.street`, and `internalNote`, the endpoint serializes only the three chosen fields.

This is typically an essential protection layer in the application. Source filtering shrinks the payload from Elasticsearch to the application, while DTOs guarantee the payload from the application to callers includes only designed fields.

Never return persistence entities directly from controllers if the entity holds sensitive or internal fields. Entities evolve over time and can accidentally expose new fields in API responses.

## 9. Why Not Rely Solely on DTOs?

DTOs govern API responses, yet if the application still fetches the entire `_source` into the backend, sensitive fields still traverse backend memory, logs, traces, or exception handlers.

Combine both layers:

1. Source filtering reduces what Elasticsearch returns when queries do not need the full source.
2. DTO allowlists restrict what leaves the service.

If one endpoint is authorized to view `email`, use a separate DTO for that use case with matching source `includes`. Another endpoint without that permission omits `email` from both `includes` and its DTO.

Still, conditionally picking `includes` by role in code does not replace authorization. The backend must authenticate users and verify permissions before building queries.

## 10. Partial Source and Entity Mapping

When a source filter returns only select fields yet Spring Data still maps results into a full entity, omitted properties may become `null`, default values, or become indistinguishable from truly empty fields.

Example entity:

    public class Customer {
        private String name;
        private String email;
        private String phone;
        private Address address;
    }

Query fetching only `name`:

    .withSourceFilter(
        new FetchSourceFilter(
            new String[] {"name"},
            null
        )
    )

When receiving `Customer`, `email` and `phone` are not loaded. If code later calls:

    customer.getEmail()

the value can be `null` even though an email exists in the index.

This creates a data-loss risk if that partial entity is passed back to `save`. An entity loaded with omitted fields must never be treated as the complete document.

### Use projections/DTOs for partial results

When an endpoint needs only a few fields, map to a dedicated DTO or use a supported projection:

    public record CustomerSummary(
        String name,
        String city
    ) {}

Never use a full entity as an update object if a source filter dropped fields. When partial updates are needed, use `UpdateQuery`/partial updates targeting only changed fields rather than calling `save` on a partial entity.

## 11. Source Filtering and Dangerous Updates

A common bug pattern:

1. Search `Customer` with a source filter fetching only `name`.
2. Spring Data hydrates `Customer` without `email`/`phone`.
3. The service modifies `name`.
4. The service calls `save(customer)`.
5. The new source overwrites the document and wipes `email`/`phone` because indexing replaces the entire source.

This is why partial entities must never be used for read-modify-write.

Solutions:

- Use read-only DTOs for partial queries.
- When updating, fetch full required data or use partial updates.
- Use `UpdateQuery`/`UpdateRequest` to mutate only targeted fields.
- Use optimistic concurrency when multiple writers exist.
- Never call `save` on an entity constructed from a source filter unless omitted fields are guaranteed preserved.

## 12. How Source Filtering Differs from `fields` and `docvalue_fields`

Elasticsearch has multiple ways to return field values:

| Mechanism | Data Source | Purpose |
|---|---|---|
| `_source` filtering | Stored `_source` | Return part of the JSON document |
| `fields` | Mapped field values fetched via API | Return typed/normalized values per mapping |
| `docvalue_fields` | Doc values | Fetch fields with doc values, suited for sort/aggregation and value retrieval |
| `stored_fields` | Separately stored fields | Fetch fields explicitly marked `store: true` in mappings |
| `script_fields` | Script output | Compute dynamic values for responses |

The `fields` API does not always return the same structure or types as `_source`. Values are often returned as arrays, and doc values do not support every field type.

Do not switch from source filtering to `fields` expecting it to hide data. If callers can request `fields` on a sensitive field, data can still be returned. Access permissions must be enforced independently.

## 13. Disabling `_source` Entirely

Mappings can disable storing `_source`:

    PUT audit-events
    {
      "mappings": {
        "_source": {
          "enabled": false
        },
        "properties": {
          "eventType": {
            "type": "keyword"
          },
          "createdAt": {
            "type": "date"
          }
        }
      }
    }

This can save storage, at a steep trade-off:

- Original document sources can no longer be retrieved in search responses.
- Standard `_source`-based reindexing becomes unavailable.
- Certain update/recovery workflows relying on source are limited.
- Debugging data becomes harder.
- Applications must rely on `fields`/`stored_fields` or another data store to construct responses.

Disabling `_source` does not secure fields. Indexed fields can still be queried or fetched via other mechanisms if mappings and privileges permit.

Do not disable `_source` merely because you do not want to return a couple of fields in one endpoint. Request-time source filtering or DTOs are far more flexible.

## 14. Mapping-Time `_source` Excludes

Mappings can configure `_source` `excludes` to drop select fields from the stored source:

    PUT customers
    {
      "mappings": {
        "_source": {
          "excludes": [
            "temporaryPayload"
          ]
        },
        "properties": {
          "name": {
            "type": "text"
          },
          "temporaryPayload": {
            "type": "keyword"
          }
        }
      }
    }

Fields excluded from stored `_source` can still be indexed per mapping and used in queries or aggregations. Therefore, this is not field-level access control.

Mapping-time excludes carry long-term impact on source recovery. If a field is dropped from source, reindex or update workflows cannot recover that field from the old source.

Only use mapping-time excludes after evaluating reindexing, updates, debugging, and data recovery requirements. Never use it as a substitute for authorization.

## 15. Synthetic `_source` and Version Differences

Some Elasticsearch versions support synthetic `_source`, where source is reconstructed from indexed data rather than keeping the original JSON verbatim.

Synthetic source can save storage in certain setups, yet has constraints around field types and structural reconstruction. Array ordering, duplicate values, or representation of certain types can differ depending on field types and configuration.

Do not assume synthetic `_source` is a byte-for-byte match of the original payload. If your application requires exact original JSON retention, check the semantics and limitations of your Elasticsearch version.

Source filtering remains a search-request response selection feature; synthetic source is an index-layer storage/reconstruction mechanism. These two concepts solve different problems.

## 16. Should Sensitive Data Be Indexed at All?

If a field is not needed for search, filtering, sorting, or aggregations, consider not indexing it or not sending it to Elasticsearch at all.

Examples:

| Data | Consideration |
|---|---|
| Display name | Likely needs full-text search |
| Email | May need exact lookup; restrict access and consider hashing/tokenization |
| Phone number | Usually needs no full-text search; restrict access and logging |
| Full street address | Index only parts needed for search/filtering |
| Internal notes | Keep out of public search projections |
| Passwords | Never store plaintext; normally has no place in Elasticsearch |
| Access tokens/API secrets | Never put into search indices |
| Payment credentials | Use specialized systems; never store carelessly in `_source` |

Setting a field unindexed limits queryability and reduces exposure surface, yet you must also consider whether it still sits in `_source`. Anyone allowed to read `_source` can still retrieve it.

For secrets such as passwords, tokens, or private keys, the right fix is keeping them out of Elasticsearch entirely. Source filtering is not a way to protect secrets.

## 17. Separating Public Projections from Private Data

A safe architecture avoids mixing all data into a single search document.

Example:

    Customer database:
      id
      name
      email
      phone
      address
      internalNote

    Customer search index:
      id
      displayName
      city
      status

The search index holds only the data needed for search use cases. When an authorized user needs private details, the backend fetches them from the authoritative store after verifying permissions.

Benefits:

- Reduces sensitive data sitting inside search indices.
- Limits damage if a search endpoint is misconfigured.
- Separates search permissions from detailed profile permissions.
- Projections can be rebuilt from the database.

In exchange, some endpoints must query the database or another service for details. That is an intentional trade-off between latency and shrinking sensitive data exposure.

## 18. Masking Data in Responses

Sometimes users may see partial values without needing full details, such as a masked email:

    a***@example.com

Masking should happen in the application layer before constructing response DTOs:

    public record CustomerContactView(
        String name,
        String maskedEmail
    ) {}

    CustomerContactView toContactView(Customer customer) {
        return new CustomerContactView(
            customer.getName(),
            maskEmail(customer.getEmail())
        );
    }

Masking does not erase raw data from Elasticsearch and does not block queries against raw fields. If callers can query the index directly, controller-level masking does not protect the index.

Never log unmasked values. Apply masking consistently across responses, logs, traces, error reports, and DLQs.

## 19. Authorizing Before Constructing Queries

When access depends on roles or tenants, the backend must evaluate permissions before executing searches.

Example:

    public Mono<CustomerSearchResponse> searchCustomers(
            UserPrincipal principal,
            CustomerSearchRequest request) {

        authorization.requireCustomerSearch(principal);

        boolean canReadEmail =
            authorization.canReadCustomerEmail(principal);

        Query query = buildCustomerQuery(
            request,
            canReadEmail
        );

        return operations.search(query, Customer.class)
            .flatMap(this::toResponse);
    }

Inside `buildCustomerQuery`, you can vary source `includes` based on permission:

    String[] includes = canReadEmail
        ? new String[] {"name", "email", "address.city"}
        : new String[] {"name", "address.city"};

Still ensure DTO mapping respects permissions as well. Do not rely solely on omitting `email` in the source filter while handing the full entity to the serializer.

Authorization must rely on verified principals and server-side policy. Never trust a client-sent `canReadEmail` flag.

## 20. Tenant Isolation and Document-Level Filtering

When documents belong to tenants, every query must scope to the right tenant:

    Query query = NativeQuery.builder()
        .withQuery(q -> q
            .bool(b -> b
                .filter(f -> f
                    .term(t -> t
                        .field("tenantId")
                        .value(tenantId)
                    )
                )
                .filter(f -> f
                    .match(m -> m
                        .field("name")
                        .query(searchText)
                    )
                )
            )
        )
        .build();

`tenantId` must come from verified security context, never blindly from request parameters.

Source filtering does not prevent another tenant's documents from appearing if the query omits the tenant filter. Use Elasticsearch document-level security when principals access the cluster directly and require cluster-layer enforcement, while maintaining backend authorization.

When using aliases, routing, or per-tenant indices, verify every query, get, update, aggregation, and bulk path maintains the tenant boundary.

## 21. Field-Level Security in Elasticsearch

Elasticsearch offers security controls to restrict which fields a role may read, depending on version and license/deployment. Field-level security can apply field allowlists or denylists per principal.

How it differs from source filtering:

- Source filtering is chosen per request.
- Field-level security is bound to the principal's permissions.
- When a principal is restricted on fields, queries/fetches targeting forbidden fields are blocked by the security layer per configuration semantics.

Field-level security must be configured in the role/security layer and tested using each role's actual credentials. Never test exclusively as an admin user, since admins can see every field and mask permission bugs.

Check feature availability in your deployed Elasticsearch version and tier. If the backend uses a broadly privileged service account, the backend must enforce application authorization and never give clients direct access to that credential.

## 22. Document-Level Security and Source Filtering

Document-level security limits which documents a role can access—for instance, a Tenant A role can search only documents with `tenantId = A`.

Field-level security limits which fields can be read. Both combine cleanly:

- Document-level security decides which documents are accessible.
- Field-level security decides which fields are accessible inside those documents.
- Source filtering decides which subset of `_source` a request wants within the permitted scope.

Source filtering does not replace the first two. If a query can read out-of-scope fields or documents, fix the security policy and query authorization.

## 23. Field Mappings and `index:false`

If a field never needs to be queried, you can configure `index:false`:

    PUT customers
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "text"
          },
          "internalReference": {
            "type": "keyword",
            "index": false
          }
        }
      }
    }

`index:false` prevents building an inverted index per the field type's semantics, yet the field can still remain in `_source`. For certain data types, doc values or stored behavior should also be considered.

Thus:

- `index:false` does not remove the field from `_source`.
- Source `excludes` does not stop a field from being indexed.
- Neither provides authorization on its own.

If a field has no reason to exist in Elasticsearch, do not send it in the document. That is the clearest way to shrink your data exposure surface.

## 24. Mapping `_source` Excludes and Reindexing

The Reindex API normally reads document sources from a source index and writes them to a destination index. If a field is dropped from stored `_source`, reindexing from that source cannot automatically restore the omitted field.

Example:

    POST _reindex
    {
      "source": {
        "index": "customers-v1"
      },
      "dest": {
        "index": "customers-v2"
      }
    }

If `customers-v1` excluded `internalReference` from `_source`, the new index will lack that value unless pulled from another store or retrieval path.

Before enabling mapping-time excludes or disabling `_source`, verify:

- Will you need to reindex?
- Will you need `update_by_query`?
- Will you need to export original data?
- Will you need to recover the index after an incident?
- Is there another authoritative source to rebuild documents from?

Do not trade away recoverability just to shave response payload size.

## 25. Never Use `@JsonIgnore` as a Security Boundary

Some applications use Jackson annotations:

    @JsonIgnore
    private String internalNote;

This annotation affects serialization/deserialization through Jackson, yet Spring Data Elasticsearch uses its own mapping/conversion infrastructure. Do not assume `@JsonIgnore` reliably prevents a field from being written to or read from `_source` under every configuration.

Similarly, Spring Data's `@Transient` has specific mapping semantics, yet does not purge fields already stored in older indices.

Inspect actual mappings and `_source` via Elasticsearch requests. If a field must not be persisted, omit it from the indexed model/document or use an explicitly configured mapping/converter.

## 26. Using Projections to Avoid Loading Unneeded Data

When only a few fields are needed, you can create a projection interface or DTO depending on Spring Data API support. Still, repository projections and source filtering are not identical.

An explicit read-model DTO:

    public record CustomerListItem(
        String id,
        String name,
        String city
    ) {}

Service:

    Flux<CustomerListItem> listCustomers(Query query) {
        return operations.search(query, Customer.class)
            .flatMapMany(ReactiveSearchHits::getSearchHits)
            .map(hit -> {
                Customer customer = hit.getContent();
                return new CustomerListItem(
                    hit.getId(),
                    customer.getName(),
                    customer.getAddress().getCity()
                );
            });
    }

This reactive snippet is a general pattern. If a source filter omits `address.city`, the getter can throw or return `null`. Align `includes` with the projection.

Projections define required response fields; source filtering reduces fetched data. Combine both when appropriate.

## 27. Search Responses Can Leak Fields Through Multiple Channels

Even when `_source` is filtered, fields can still leak via:

- `fields` or `docvalue_fields`.
- `stored_fields`.
- `highlight`.
- `inner_hits`.
- `script_fields`.
- Sort values or aggregation buckets.
- Error messages and debug logs.
- `explain`/`profile` output.

For instance, if `email` is omitted from `_source` yet a query runs a `terms` aggregation on `email.keyword`, the aggregation response can list email addresses.

Therefore, protecting data requires auditing the entire search response, not just `_source`. Public endpoints should define explicit query capabilities and response DTOs, never letting clients pass arbitrary field names, aggregations, or scripts.

## 28. Never Let Clients Pick Arbitrary Fields

An API like:

    GET /customers/search?fields=name,email,internalNote

creates risk if the backend passes `fields` straight into source `includes` without permission checks.

Instead:

- Define supported response shapes.
- Map each response shape to an explicit field allowlist.
- Check roles/tenants before choosing a shape.
- Block sensitive fields from queries/sorts/aggregations if the caller lacks permission.
- Disallow arbitrary scripts or field names from clients.

Example:

    enum CustomerView {
        SUMMARY,
        CONTACT,
        ADMIN
    }

The backend chooses fields based on `CustomerView` after authenticating the principal and verifying permissions. Clients cannot escalate privileges by passing `ADMIN`.

## 29. Inspecting Actual Data in `_source`

When evaluating a mapping or source filter, inspect real responses:

    GET customers/_doc/c-100

To test source filtering:

    GET customers/_search
    {
      "_source": [
        "name",
        "address.city"
      ],
      "query": {
        "ids": {
          "values": [
            "c-100"
          ]
        }
      }
    }

Inspect mappings:

    GET customers/_mapping

Inspect field capabilities or field mappings to verify how fields are indexed, whether doc values exist, and which analyzers apply.

In test environments, create documents with dummy values standing in for sensitive fields and verify:

- Search responses contain no fields outside the allowlist.
- DTOs serialize no internal fields.
- Disallowed queries cannot target restricted fields.
- Lower-privileged roles cannot retrieve restricted fields via direct requests.
- Get, search, aggregation, and export APIs all enforce permissions.

Avoid using real personal data to test logs or responses unnecessarily.

## 30. Testing Source Filtering in Spring Data

An integration test can save a document and query with a source filter:

    @Test
    void searchReturnsOnlySelectedSourceFields() {
        Customer customer = new Customer();
        customer.setId("c-test-1");
        customer.setName("Test Customer");
        customer.setEmail("test@example.com");
        customer.setInternalNote("private");

        operations.save(customer);
        operations.indexOps(Customer.class).refresh();

        Query query = NativeQuery.builder()
            .withQuery(q -> q
                .ids(ids -> ids.values("c-test-1"))
            )
            .withSourceFilter(
                new FetchSourceFilter(
                    new String[] {"name"},
                    null
                )
            )
            .build();

        SearchHits<Customer> hits =
            operations.search(query, Customer.class);

        assertThat(hits.getSearchHits()).hasSize(1);
        assertThat(hits.getSearchHit(0).getContent().getName())
            .isEqualTo("Test Customer");
    }

This example uses common imperative APIs and builders. Constructors, query builders, and refresh methods depend on your Spring Data Elasticsearch version.

This test confirms the source filter was applied to the query. It does not prove the `email` field is secured across other APIs or principals. Security roles must be tested separately.

## 31. Testing Against Response Leaks

Controller/service tests should inspect the final JSON output:

    mockMvc.perform(get("/customers/search"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$[0].name").exists())
        .andExpect(jsonPath("$[0].email").doesNotExist())
        .andExpect(jsonPath("$[0].internalNote").doesNotExist());

With WebFlux, use `WebTestClient` to assert the corresponding response.

Do not just check that a Java DTO lacks a getter. Jackson may serialize fields through accessors or annotations. Checking the actual JSON verifies the response contract.

If an endpoint supports multiple roles, write tests for every role and every response shape. Testing only with an administrative service account does not prove ordinary users are restricted properly.

## 32. Protecting Logs, Tracing, and Exceptions

Source filtering shrinks search payloads, yet sensitive data can still surface elsewhere:

- Logging whole entities before or after `save`.
- Logging Elasticsearch requests/responses.
- Trace attributes holding queries or sources.
- Exception messages containing field values.
- DLQs storing raw events.
- Debug dumps in tests or local development.

Logging design:

- Log technical IDs or correlation IDs when appropriate.
- Mask or omit sensitive fields.
- Never log access tokens, passwords, or credentials.
- Avoid logging verbatim queries/sources.
- Restrict log access and retention.
- Use synthetic/test data in development environments.

If a DLQ must retain payloads for replay, encrypt them and restrict read access. You can store payloads in separate protected storage and keep only a reference plus error metadata in the DLQ.

## 33. Sensitive Data and Encryption

Encryption at rest protects data against unauthorized infrastructure-level storage access, yet does not stop an authorized search user from reading fields in responses.

TLS protects data in transit between the application and Elasticsearch, yet does not replace authorization.

If a field must be stored without Elasticsearch or operators reading it in plaintext, consider application-layer field encryption before indexing. Understand the trade-offs:

- Encrypted fields usually cannot be full-text searched like plaintext.
- Equality lookups may require a separate deterministic token/hash, though deterministic values can reveal equality relationships.
- Key rotation and reindexing must be planned.
- Never store encryption keys in the same index.
- Key management requires independent access control.

Never roll your own encryption algorithm. Use vetted libraries and key management suited to your system.

## 34. Source Filtering Across Multi-Index and Aliases

A query can target an alias pointing to multiple indices. Mappings and source structures may differ across those indices.

If a source filter specifies:

    "_source": {
      "includes": [
        "name",
        "address.city"
      ]
    }

a field might exist in one index and be absent in another. When Spring Data maps everything into the same entity, properties can be `null` or have mismatched types if mappings drifted.

For version-switching aliases, keep source contracts compatible or use DTOs/converters handling multiple versions. Inspect mappings on every index behind an alias.

Source filtering does not resolve mapping conflicts across multiple indices.

## 35. Nested Objects and Source Filtering

With nested data:

    {
      "name": "Keyboard",
      "offers": [
        {
          "seller": "Store A",
          "price": 120,
          "internalMargin": 20
        },
        {
          "seller": "Store B",
          "price": 95,
          "internalMargin": 15
        }
      ]
    }

You can select:

    "_source": {
      "includes": [
        "name",
        "offers.seller",
        "offers.price"
      ]
    }

Verify the response structure and `List<Offer>` mapping when fields inside `Offer` are omitted. `internalMargin` may become `null` in partial entities.

If the public endpoint only needs seller and price, use an `OfferView` DTO instead of returning full `Offer` entities. When `inner_hits` is used, control inner-hit source filtering separately per supported API; top-level source filters do not necessarily govern every nested hit section.

## 36. Sensitive Data in Aggregations and Sorting

Omitting a field from `_source` does not block aggregations or sorting on that field if mappings and permissions allow it.

Example:

    GET customers/_search
    {
      "size": 0,
      "aggs": {
        "by_email": {
          "terms": {
            "field": "email.keyword"
          }
        }
      }
    }

The aggregation response can still reveal email addresses even though `_source` is not returned.

If emails must not be disclosed, never let endpoints accept arbitrary aggregations on email. Restrict aggregation fields with allowlists and authorization. For direct Elasticsearch access, use field-level security to enforce restrictions on the cluster.

## 37. Choosing the Right Mechanism for Your Goal

| Goal | Approach |
|---|---|
| Reduce response size for a query | Request-time source filtering |
| Return only public fields from a service | DTO/projection allowlist |
| Avoid storing unneeded fields in index | Omit fields from documents before indexing |
| Skip indexing a field while keeping source | Mapping `index:false`, after reviewing needs |
| Omit a field from stored source | Mapping `_source` excludes, after reviewing reindex/recovery |
| Block a role from reading a field | Field-level security or equivalent access control |
| Block a role from reading a document | Document-level security or tenant authorization |
| Protect data at rest/in transit | Encryption at rest/TLS and key management |
| Display only partial values | Application-layer masking |
| Keep secrets out of search | Keep secrets outside Elasticsearch |

No single `_source` option satisfies every goal. Choose mechanisms matching your data boundaries and threat model.

## 38. Common Mistakes

### Thinking source filtering secures fields

Source filters only shape a single request's response. Callers with sufficient privileges can send other queries or call other APIs. Use authorization and field-level security.

### Using `excludes` as a static denylist

New fields can leak if the excludes list is not maintained. For public responses, prefer an `includes` allowlist and DTOs.

### Omitting a field from `_source` while still allowing aggregations

Fields can still leak through aggregations, sorts, `fields`, or scripts. Restrict query capabilities and security policies.

### Returning persistence entities directly

Entities may hold internal fields and grow over time. Map into dedicated DTOs per response shape.

### Saving partial entities back

Fields omitted by a source filter can become `null` and overwrite data during a full document `save`. Use read-only DTOs and partial updates.

### Disabling `_source` just to shrink payloads

Disabling source removes source retrieval and breaks standard reindexing/updates. Use request-time source filtering when you only want smaller payloads.

### Treating mapping `_source` excludes as authorization

Fields can still be indexed and queried. This is not field-level security.

### Assuming `@JsonIgnore` governs Spring Data mapping

Spring Data Elasticsearch uses its own converters. Inspect actual mappings and `_source` rather than relying on Jackson annotations as security boundaries.

### Letting clients pass arbitrary `fields`

Clients could request sensitive fields. Use server-side response shape allowlists and authorization.

### Overlooking `fields`/`inner_hits`/`highlight`

Sensitive fields can leak through response sections outside `_source`. Inspect the full response structure.

### Logging raw sources

Logs, tracing, and DLQs can leak data. Mask, redact, and restrict access/retention.

### Using a broad service account without checking users

The backend must enforce end-user authorization before querying. Never let the service account's privileges become every caller's effective rights.

## 39. Secure Response Design Workflow

When building a search endpoint:

1. Identify which fields are genuinely required for the response.
2. Classify fields as public, internal, confidential, or secret.
3. Keep secrets out of Elasticsearch unless strongly justified.
4. Verify principal and tenant permissions before querying.
5. Build an `includes` allowlist per use case.
6. Map results to dedicated DTOs rather than returning full entities.
7. Check whether queries, sorts, aggregations, highlights, `inner_hits`, or `fields` could expose data.
8. Never let clients choose fields or query capabilities outside allowlists.
9. Use field/document-level security if principals access Elasticsearch directly.
10. Audit logs, traces, exceptions, and DLQs to avoid source leaks.
11. Never use partial entities for full-document `save`/update operations.
12. Test JSON responses and real security roles.
13. Evaluate the impact of mapping `_source` settings on reindexing and recovery.

## Conclusion

Source filtering lets Elasticsearch return only a portion of `_source` using `includes` and `excludes`. In Spring Data Elasticsearch, you can attach source filters to queries and map `SearchHit` results into DTOs. `includes` allowlists fit public responses better because newly added fields are not exposed unless explicitly permitted. However, source filtering only shrinks payloads and is not authorization: fields can still be leveraged in queries, sorts, aggregations, `fields`, or other response channels if mappings and privileges permit.

To protect sensitive data, enforce user authorization in the backend, restrict documents/fields in Elasticsearch when needed, avoid indexing unnecessary secrets, use DTO allowlists, and mask logs/tracing/DLQs. Mapping-time `_source` excludes or disabling `_source` carry long-term consequences for reindexing and recovery, so avoid using them solely to hide fields in one endpoint. Never re-save entities loaded via source filters because omitted fields can be overwritten. Verify full responses and realistic security roles with integration tests so data cannot leak through channels outside `_source`.
