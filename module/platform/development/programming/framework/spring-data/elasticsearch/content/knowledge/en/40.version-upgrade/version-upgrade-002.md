# Distinguishing Elasticsearch from OpenSearch and Compatibility Scope

Elasticsearch and OpenSearch share many similarities because OpenSearch started from a branch of the Elasticsearch codebase. Both are distributed search engines powered by Lucene, store documents as JSON, and expose familiar REST APIs with Query DSL. Consequently, a simple query or HTTP request can look nearly identical across the two systems.

However, **Elasticsearch and OpenSearch are now two independently developed products**. APIs, clients, plugins, security, operational tooling, and release cadences have steadily diverged. An application using Spring Data Elasticsearch may be able to connect to an OpenSearch cluster in certain configurations or versions, but that does not prove full feature support or long-term compatibility.

When evaluating compatibility, clearly identify which layer is being discussed: HTTP protocol, REST endpoints, Query DSL, mappings, Java client, Spring Data abstraction, plugins, snapshots, or operational procedures. Do not use a generic phrase like "Elasticsearch-compatible" as a substitute for a version matrix and real testing.

## 1. What are Elasticsearch and OpenSearch?

**Elasticsearch** is a distributed search and analytics engine developed by Elastic. It is commonly used for indexing, full-text search, filtering, data aggregation, log observability, and building search features in applications.

**OpenSearch** is an open-source project forked from the Elasticsearch 7.10.2 and Kibana 7.10.2 codebase. The project was announced after Elastic changed the licensing model for newer Elasticsearch releases. OpenSearch continues to develop independently alongside OpenSearch Dashboards and its own plugin ecosystem.

Both share historical foundations and many concepts:

- Cluster, node, shard, and replica.
- Index and document.
- Mapping and field types.
- Inverted index and Lucene.
- JSON-based REST API.
- Query DSL with `match`, `term`, `bool`, `range`, and other queries.
- Aggregations for computing statistics.
- Bulk API for writing multiple documents.
- Snapshots and index management mechanisms in their respective forms.

This similarity makes migrating certain basic use cases easier. It does not mean the two products share the same current codebase, release schedule, or API contract.

## 2. Origin and fork point

OpenSearch was created from the Elasticsearch 7.10.2 and Kibana 7.10.2 source code. This is a key historical milestone when reading compatibility documentation.

~~~text
Elasticsearch / Kibana
        |
        | 7.10.2
        |
        +----------------------+
        |                      |
        v                      v
Elasticsearch continues    OpenSearch starts
development by Elastic     from the 7.10.2 branch
        |                      |
        v                      v
Separate API, features,    Separate API, features,
releases, and licensing    releases, and governance
~~~

At the time of the fork, many APIs and concepts were nearly identical. Over subsequent releases, the two development teams added features, fixed bugs, and changed internals along different paths.

Therefore, an old example that ran on Elasticsearch 7.10.2 may require few changes on OpenSearch 1.x, but you cannot extrapolate from that to conclude a modern application using the latest Elasticsearch will run unchanged on the latest OpenSearch.

## 3. Differences in licensing and governance

A major reason behind the creation of OpenSearch was the difference in licensing models.

- Elasticsearch versions prior to 7.11 were released under Apache License 2.0.
- Starting with Elasticsearch 7.11, Elastic changed the license for parts of the distribution and source code, using Elastic License 2.0 and SSPL depending on the component/version licensing model.
- OpenSearch is released under Apache License 2.0.

Do not judge solely by product name and assume every component, plugin, or accompanying service carries the same license. Check the license of the exact version and artifact your organization intends to use.

Regarding governance:

- Elasticsearch is developed and released by Elastic.
- OpenSearch is an open-source project developed by the community and participating organizations under OpenSearch project governance.
- Managed services, support contracts, and commercial distributions have their own terms.

For enterprise projects, licensing, support, security patch policy, and supportability are part of architectural decision-making, not merely legal details after coding is complete.

## 4. Similarities in architecture and data model

Both systems organize data into indexes and JSON documents. Applications typically send HTTP requests to the cluster, and the cluster distributes work across shards.

| Concept | Elasticsearch | OpenSearch |
|---|---|---|
| Cluster | Yes | Yes |
| Node roles | Yes | Yes |
| Index | Yes | Yes |
| Primary/replica shard | Yes | Yes |
| JSON document | Yes | Yes |
| Mapping | Yes | Yes |
| Analyzer/tokenizer | Yes | Yes |
| Query DSL | Yes | Yes |
| Aggregation | Yes | Yes |
| Bulk indexing | Yes | Yes |
| Snapshot/restore | Yes | Yes |
| REST API | Yes | Yes |

The concept names are the same, yet implementation details and options can differ by version. For instance, both having index templates does not mean all template APIs, component templates, lifecycle integrations, or defaults are identical.

## 5. Differences in REST API and Query DSL

Many basic REST endpoints share a similar structure:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "name": "keyboard"
    }
  }
}
~~~

Simple queries like `match`, `term`, `bool`, `range`, `sort`, `from`/`size`, aggregations, and bulk often have high similarity. However, newer features and less common parameters can differ:

- Endpoint names or request parameters.
- Response structure and error bodies.
- New query options added in one product.
- Default scoring or sorting behavior.
- Field types and mapping options.
- Plugin queries or aggregations.
- Search pipelines and ingest processors.
- Vector, semantic, or hybrid search.
- Security APIs and authorization behavior.

Do not test compatibility with a single simple `match` request. Gather the exact set of APIs the application uses and run integration tests on both servers if both must be supported.

## 6. Syntactic compatibility does not mean semantic compatibility

Two servers may accept the exact same JSON request yet return different results due to differences in analyzers, mappings, scoring, default settings, or implementations.

For example:

- Analyzers using synonym or tokenizer plugins may behave differently.
- Keyword normalizer and collation behavior may differ.
- Queries on nested fields depend on matching mappings.
- Terms aggregations may differ in options or limits.
- Highlight fragments may differ due to highlighters and analyzers.
- Vector search or hybrid ranking may use distinct APIs.
- Painless scripts and script contexts must be verified per product.

Therefore, compatibility tests must verify two things:

1. The request is accepted by the server.
2. The results and semantics satisfy the application contract.

Checking only for HTTP 200 is insufficient.

## 7. Java clients of the two ecosystems

This is one of the most important boundaries in Spring integration.

Elasticsearch has its own Java clients, including:

- Elasticsearch Java API Client with packages and artifacts in the Elasticsearch ecosystem.
- Low-level `RestClient` using HTTP.
- `RestHighLevelClient` in older applications; this client has been replaced by the Java API Client in modern Elasticsearch development.

OpenSearch has its own clients, for example:

- OpenSearch Java Client.
- OpenSearch REST Client.
- Compatibility clients/adapters for older applications within supported version ranges.

Example dependencies have different artifact names:

~~~xml
<!-- Elasticsearch Java API Client -->
<dependency>
    <groupId>co.elastic.clients</groupId>
    <artifactId>elasticsearch-java</artifactId>
    <version>...</version>
</dependency>
~~~

~~~xml
<!-- OpenSearch Java Client -->
<dependency>
    <groupId>org.opensearch.client</groupId>
    <artifactId>opensearch-java</artifactId>
    <version>...</version>
</dependency>
~~~

Do not replace one dependency with the other merely by changing `groupId`. Classes, builders, request/response types, transports, serialization, and exceptions can all differ.

If the application only needs basic HTTP REST, you can build an HTTP client or use the corresponding low-level client. However, that approach means the application must manage serialization, retries, timeouts, authentication, TLS, and API evolution itself.

## 8. Elasticsearch Java API Client is not the OpenSearch Java Client

Both clients may offer similar operations such as search, index, update, delete, and bulk. However, packages and model types are not the same.

~~~java
// Elasticsearch Java API Client
co.elastic.clients.elasticsearch.ElasticsearchClient
~~~

~~~java
// OpenSearch Java Client
org.opensearch.client.opensearch.OpenSearchClient
~~~

Request classes such as `SearchRequest`, `BulkRequest`, or response hits are generated from each product's own API specification.

Therefore:

- Code importing Elasticsearch packages will not automatically compile with the OpenSearch client.
- Builder lambdas may differ.
- Enums and data types may differ.
- Exception mapping differs.
- Transport and credential provider configuration differs.
- The client version must be compatible with the target server.

If an application needs to support both backends, place a business interface in between and write a dedicated adapter for each client rather than scattering both client types across services.

## 9. What does Spring Data Elasticsearch support?

Spring Data Elasticsearch provides abstractions following the Spring Data model, for example:

- `ElasticsearchRepository`.
- `ReactiveElasticsearchRepository`.
- `ElasticsearchOperations`.
- `ReactiveElasticsearchOperations`.
- `Query` and `NativeQuery`.
- Mapping/conversion between entities and documents.
- Repository query derivation.
- Auditing and version-specific integrations.

Spring Data Elasticsearch is developed to integrate with Elasticsearch and the clients supported by that Spring Data version. Each release train has its own compatibility matrix across Spring Data Elasticsearch, Spring Framework, Spring Boot, Elasticsearch server, and Java client.

You cannot infer compatibility merely from using Spring Boot or because two servers have similar REST APIs.

When upgrading Spring Data Elasticsearch, consult the official compatibility table of the exact release train rather than picking the latest version of each dependency arbitrarily.

## 10. Can Spring Data Elasticsearch connect to OpenSearch?

The answer depends on versions, client transport, APIs used by the application, and cluster configuration. Some applications using Spring Data Elasticsearch can connect to certain OpenSearch versions over compatible HTTP protocols, especially for closely aligned basic APIs.

However, three levels must be distinguished:

1. **Connectable:** TCP/TLS/authentication and basic HTTP requests work.
2. **Some APIs work:** basic search, index, or bulk are accepted by the server.
3. **Supported and fully compatible:** Spring Data abstractions, client, mappings, queries, repositories, aggregations, exceptions, and application features all fall within a confirmed support matrix.

Level 1 or 2 does not automatically prove Level 3.

If using the Elasticsearch Java API Client against an OpenSearch server, specifically verify client/server version compatibility. Do not assume every request or response of the Java API Client will work on OpenSearch.

If OpenSearch is the primary requirement, evaluate the OpenSearch Java Client and the Spring Data integration for OpenSearch at the appropriate version. The Spring Data OpenSearch project in the OpenSearch ecosystem is a separate integration; check its release matrix, maintenance status, and compatibility with your Spring Boot/Spring Framework versions. Do not treat it as the same artifact or the same release train as Spring Data Elasticsearch.

## 11. REST compatibility mode is not a cross-product guarantee

Some Elasticsearch clients provide a compatibility mode to support communicating with the immediately preceding major version within Elasticsearch's compatibility policy. This mechanism usually involves media types/HTTP headers and how requests/responses are serialized.

That compatibility mode has its own scope:

- It does not turn an Elasticsearch client into an OpenSearch client.
- It does not guarantee endpoints unique to one product will exist in the other.
- It does not align mappings, plugins, or security features.
- It does not guarantee identical query semantics.
- It does not replace testing the server/client matrix.

If documentation mentions a client has a "compatibility mode," read carefully whether it refers to major versions of the same product or compatibility with a forked product. Those are two different concepts.

## 12. Mappings and field types

Basic field types like `keyword`, `text`, `date`, `boolean`, and numeric types share high similarity. However, newer mapping options, specialized field types, and plugin-backed types may be absent from one product or have different semantics.

When migrating, check:

- Text analyzers, tokenizers, and token filters.
- Synonym sets and synonym graphs.
- Normalizers.
- `nested` and `flattened`.
- Runtime fields or dynamic field types.
- Dense vector, sparse vector, and vector search.
- Geo point/shape.
- Rank feature and rank features.
- Percolator or specialized field types.
- Dynamic templates and multi-fields.
- Doc values, fielddata, and `ignore_above`.

Do not simply copy mapping JSON and assume success. Create a new index on the target server and verify the mapping is accepted, then index fixtures and run real queries/aggregations.

A field mapping may be accepted yet exhibit different analyzer or scoring behavior. Tests should verify search results rather than stopping at successful index creation.

## 13. Analyzers, synonyms, and language processing

Analyzers are a critical part of full-text search. Two clusters can use the same analyzer name while having different configurations or plugins.

For example, an index may depend on:

- ICU analysis.
- Vietnamese tokenizer or language plugin.
- Synonym files or synonym APIs.
- Edge n-gram for autocomplete.
- Stemmers and stopwords.
- Custom character filters.

Analysis plugins usually must be installed on the corresponding nodes and match the exact server version. A plugin built for Elasticsearch cannot by default be installed into OpenSearch, or vice versa.

When migrating:

1. List all analyzers and plugins in use.
2. Check whether plugins have equivalent versions on the target server.
3. Compare tokenizer/filter configurations.
4. Run the Analyze API with representative keywords.
5. Compare token streams and search results.
6. Reindex if analyzers/mappings change.

For Vietnamese, check diacritics, compound words, stemming, synonyms, and tokenization using real fixtures. Two different analyzers can alter search results even when the query JSON is unchanged.

## 14. Aggregations, sorting, and pagination

Basic aggregations such as `terms`, `range`, `histogram`, `stats`, and `date_histogram` usually behave similarly. However, advanced features and plugin-specific aggregations may differ.

Check:

- Terms aggregations and bucket ordering.
- Composite aggregations and `after_key`.
- `nested`/`reverse_nested`.
- Pipeline aggregations.
- Cardinality precision.
- Significant terms or specialized statistics.
- `search_after`, PIT, and `scroll`.
- Sort modes, missing values, and nested sorts.
- Total hits and `track_total_hits`.

Do not only compare whether responses have the same bucket names. Use known fixture data to verify `doc_count`, ordering, range boundaries, and semantics.

If the application depends on deep pagination or PIT, verify full support in both the API and client versions on both backends. This is a feature that must be tested explicitly, not inferred from basic search working.

## 15. Vector search and semantic search

Vector search is a fast-evolving area, and the two products have developed separate features since the fork.

Distinguish:

- Vector field mapping.
- How vectors are indexed.
- Similarity metrics.
- Approximate nearest neighbor algorithms.
- KNN query syntax.
- Filters combined with vector search.
- Hybrid search combining lexical and vector.
- Reranking and search pipelines.
- Model integration and inference processors.

Do not assume similar field type names or query DSLs mean identical algorithms and ranking results. They may share the KNN concept while differing in APIs, limits, tuning parameters, or plugin dependencies.

If the application uses semantic search, build dedicated retrieval quality tests: standard query sets, expected relevant documents, `recall@k`, or appropriate metrics. HTTP 200 does not prove equivalent ranking results.

## 16. Ingest pipelines and data lifecycle

Ingest pipelines may use processors such as `set`, `rename`, `remove`, `date`, `grok`, `script`, `attachment`, or enrichment. Some processors are core, while others depend on plugins or product-specific features.

Beyond ingest, the two ecosystems manage index lifecycles differently:

- Elasticsearch has mechanisms such as Index Lifecycle Management (ILM) and related APIs.
- OpenSearch has Index State Management (ISM) and related APIs/plugins.

Goal names like rollover, warm/cold tiers, retention, or deletion may sound alike, but policy schemas, actions, transitions, and APIs are not necessarily the same.

Do not copy an ILM policy and change the endpoint expecting it to become an ISM policy. Convert each state/action individually and verify:

- Rollover alias/data stream.
- Retention and deletion.
- Allocation/tiers.
- Snapshot actions.
- Force merge.
- Policy transitions.
- Retries and error states.
- Required security permissions.

## 17. Security and authentication differ

Both products provide security, TLS, and authorization mechanisms, but APIs and configuration models can differ.

Elasticsearch typically uses Elastic Stack security features with version/license-specific APIs and settings. OpenSearch uses the OpenSearch Security plugin with its own APIs/configurations, including roles, users, backend roles, tenants, and fine-grained access control in its own model.

Points to check:

- Basic authentication or service accounts.
- API keys and credential lifecycles.
- TLS certificates/truststores.
- Role mappings and backend roles.
- Index-level permissions.
- Document-level and field-level security.
- Audit logging.
- Security plugin compatibility.
- Authentication providers such as LDAP/SAML/OIDC per configuration.
- CORS and network boundaries if there are browser clients.

Do not assume Elasticsearch roles can be imported directly as OpenSearch roles. Do not assume security API names are identical or permissions have the same semantics.

If the backend uses a service credential with access across all tenants, the application must still enforce tenant authorization at the service layer for every request. Cluster security and end-user authorization are two separate layers.

## 18. Plugins and extensions are not interchangeable

Plugins are tightly coupled to:

- The product (Elasticsearch or OpenSearch).
- Server version.
- Lucene version.
- Plugin APIs and binary compatibility.
- Node and cluster configuration.

A plugin built for Elasticsearch does not run on OpenSearch by default. Conversely, an OpenSearch plugin is not treated as an Elasticsearch plugin.

Inventory plugins in use:

| Category | Example Need | What to Verify |
|---|---|---|
| Analysis | ICU, language analyzers | Whether a corresponding plugin version exists |
| Security | Auth, audit, DLS/FLS | How features/licenses/APIs differ |
| Ingest | Attachment, enrichment | Whether processors exist with the same semantics |
| Vector | KNN, ANN | Mapping, queries, algorithms, and tuning |
| Observability | Metrics, tracing | Integrations and endpoints |
| Storage | Snapshot repositories | Plugin and repository compatibility |

Do not deploy a new server if a required application plugin lacks a tested replacement.

## 19. Kibana and OpenSearch Dashboards

OpenSearch Dashboards originated from Kibana 7.10.2 but has developed independently. Concepts like dashboards, visualizations, saved objects, and data views may look similar, yet you should not assume saved objects exported from one product will always import directly into the other.

Check:

- Dashboard and visualization types.
- Saved object schema/version.
- Data views/index patterns.
- Security tenants/workspaces.
- Visualization plugins.
- Alerting and reporting.
- Query languages and Dev Tools.
- Role/permission mappings.

If dashboards are part of the migration deliverable, export/import in a test environment and verify each visualization, filter, alert, and access permission.

## 20. Snapshot, restore, and data migration

Snapshots are binary data tied to the metadata and format of a specific product/version. Do not assume snapshots from modern Elasticsearch can be restored directly into OpenSearch or vice versa.

Compatibility depends on:

- Source and target versions.
- Fork milestone.
- Snapshot format.
- Index metadata and mappings.
- Plugin field types.
- Feature state/system indexes.
- Repository type.
- Cluster settings and security configuration.

Some migration paths may support snapshots from older Elasticsearch versions near the fork point, but you must verify the exact migration documentation of the source/target versions. Do not treat "snapshot created successfully" as proof of restore compatibility.

Common strategies:

1. Snapshot/restore if the exact version pair is supported.
2. Reindex from remote or export/import via APIs.
3. Rebuild projections from the database/source of truth.
4. Controlled dual-write/dual-read during the transition period.
5. Create a new index, validate it, then switch the alias.

Reindexing via REST API may require configuring remote allowlists, network access, authentication, and load throttling. Test mappings, analyzers, and pipelines separately on the target before ingesting large datasets.

## 21. You cannot mix nodes of the two products in one cluster

Elasticsearch and OpenSearch are two independently developed distributions. Do not add an Elasticsearch node to an OpenSearch cluster or vice versa as if they were nodes of the same product.

Cluster coordination, transport protocols, metadata, and version compatibility are not designed to mix nodes across the two products. Both using Lucene and having similar REST APIs does not make internal node protocols compatible.

To switch, build a separate target cluster, migrate or rebuild data, validate results, and switch traffic according to plan. Do not perform a cross-product rolling upgrade by swapping node binaries one by one.

## 22. Compatibility matrix to verify

No single version number describes full compatibility. For a Spring application, build a matrix:

| Component | Example Details to Specify |
|---|---|
| Spring Boot | Exact version |
| Spring Framework | Version managed by Boot |
| Spring Data release train | Exact version |
| Spring Data Elasticsearch | Artifact version |
| Java runtime | JDK version |
| Server | Elasticsearch or OpenSearch and version |
| Java client | Elasticsearch Java API Client or OpenSearch Java Client |
| Transport | HTTP/REST client and TLS/auth setup |
| Plugins | Name and version of each plugin |
| Index mapping | Versioned schema |
| Dashboards | Kibana or OpenSearch Dashboards version |

Each row in the matrix needs a status:

- Supported per official documentation.
- Tested by project integration tests.
- Works with limited feature set.
- Unsupported/unknown.
- Blocked by plugin or API.

Do not mark "compatible" if you have only tested the health endpoint or a single `match` query.

## 23. Distinguishing supported, compatible, and tested

These three terms should be used precisely:

**Supported**: the vendor or project confirms the version pair is within the support scope and eligible for bug fixes under policy.

**Compatible**: the components can communicate within a defined scope, though not necessarily covered by an official support matrix.

**Tested**: the project team has run a specific test suite on the version pair and recorded the results.

A server/client pair might "work" in a test environment without being supported. Upon upgrading, a new API could break the integration with no commitment from the vendor.

In architectural documentation, record both versions and feature scope. For example: "Basic search, index, and bulk have been tested on pair A/B; PIT and vector search are unverified" is much clearer than "OpenSearch compatible."

## 24. How to check Spring Data version compatibility

When choosing Spring Data Elasticsearch:

1. Identify the Spring Boot version.
2. Identify the Spring Data release train managed by dependency management.
3. Check the compatibility matrix for that exact Spring Data release.
4. Identify supported Elasticsearch server versions.
5. Identify the Java API Client version used by that release train.
6. Check the minimum JDK.
7. Check deprecated or removed APIs.
8. Run integration tests against the real server version.

Do not override the Java client version independently without understanding dependency alignment. Spring Data Elasticsearch may rely on specific client classes/APIs; forcing an incompatible client version can cause `NoSuchMethodError`, `ClassNotFoundException`, or serialization/runtime errors.

Use Spring Boot/Spring Data dependency management whenever possible. If an override is necessary, document the reason and inspect the dependency tree.

## 25. Verifying client/server with smoke tests

A minimal smoke test needs to do more than a health check:

1. Connect and authenticate.
2. Fetch cluster/server version.
3. Create an index with the required mapping.
4. Index a document.
5. Get a document by ID.
6. Search using `match` and `term`.
7. Sort on keyword/numeric/date fields.
8. Paginate with `from`/`size`.
9. Bulk index and read item-level responses.
10. Run aggregations.
11. Check highlighting if the application uses it.
12. Update and delete.
13. Verify aliases/templates/ingest if applicable.
14. Verify security and tenant isolation.
15. Verify PIT/`search_after` if the application uses them.

Run the smoke test against every server/client pair you plan to support. Store the server version, client version, dependency lock, and test results alongside release artifacts.

## 26. Testing real Query DSL

Create fixtures with known data and run the same query suite on both servers. Compare:

- Hit counts.
- Result IDs and ordering.
- Scores if the application depends on ranking.
- Sort values.
- Highlight fragments within acceptable semantics.
- Aggregation bucket keys and counts.
- Date boundaries/timezones.
- Nested query behavior.
- Null/missing field behavior.
- Error responses for invalid queries.

Do not demand identical absolute scores if implementations/analyzers differ and the products do not guarantee it. Instead, define business criteria: whether key documents appear in the top K, whether filters are exact, and whether bucket counts are correct.

## 27. Testing mappings and data

A migration test should create a new index from the target mapping, not just restore data.

Verify:

- All field types.
- Multi-fields and normalizers.
- Analyzers and token streams.
- Nested paths.
- Date formats and timezones.
- Numeric precision.
- Null/missing values.
- Dynamic templates.
- Aliases and routing.
- Ingest pipelines.
- Source filtering and stored fields.

If the mapping changes, data transformation may be needed. For example, a `text` field in the source may need a new `keyword` multi-field in the target for sorting/aggregations. An analyzer plugin may need to be replaced with another analyzer, leading to different search results.

Do not modify original source data just to fit the target without clearly defining the transformation and rollback plan.

## 28. Risks when using Spring Data Elasticsearch with OpenSearch

An application may build and connect successfully yet run into runtime issues:

- Java API Client sends request options unsupported by OpenSearch.
- Response JSON differs, causing deserialization errors.
- Spring Data uses newer Elasticsearch APIs than the target server supports.
- Repository query derivation generates unexpected DSL.
- `NativeQuery` uses options not yet available on OpenSearch.
- Aggregation containers or hit metadata differ.
- Security plugin rejects requests due to differing credentials/roles.
- Analysis/vector plugins are missing or differ in version.
- Client error mapping fails to recognize status/error types.
- PIT/`search_after` behavior does not match assumptions.

If using Spring Data Elasticsearch with OpenSearch in production, explicitly document the verified feature subset and lock versions. Do not let "connection succeeded" turn into an unsubstantiated compatibility promise.

## 29. Strategy if both backends must be supported

If a product must run on both Elasticsearch and OpenSearch, avoid letting business code depend directly on a specific client.

~~~text
Application service
        |
        v
SearchPort (application interface)
        |
        +----------------------+
        |                      |
        v                      v
Elasticsearch adapter     OpenSearch adapter
        |                      |
        v                      v
Elasticsearch Java        OpenSearch Java
API Client                 Client
        |                      |
        v                      v
Elasticsearch cluster     OpenSearch cluster
~~~

The interface should express use cases, not expose client request types:

~~~java
public interface ProductSearchPort {

    ProductSearchPage search(ProductSearchCriteria criteria);

    void index(ProductDocument document);

    void delete(String productId);
}
~~~

Both adapters can consume a shared internal query model and translate it into their respective DSLs. Do not use Elasticsearch's `SearchRequest` in the interface if an OpenSearch adapter must implement the same interface.

If the application is reactive, define the contract with `Mono`/`Flux` or a consistent async abstraction. Do not have one adapter block while the other is non-blocking without callers knowing the semantics.

## 30. Avoiding over-generalized abstractions

Not every feature can be represented identically. Vector search, search pipelines, security APIs, or plugin-specific queries may exist on only one backend or have different semantics.

An overly generic interface can:

- Hide critical features.
- Create confusing optional parameters.
- Force the weaker backend to simulate unsupported behavior.
- Leave callers unaware of whether a feature is actually supported.

You can split capabilities:

~~~java
public interface ProductSearchPort {
    ProductSearchPage search(ProductSearchCriteria criteria);
}

public interface VectorSearchCapability {
    VectorSearchPage searchSimilar(VectorSearchCriteria criteria);
}

public interface SearchAdministrationCapability {
    void createIndex(ProductIndexDefinition definition);
}
~~~

The application can check capabilities at startup or use explicit configuration. If a backend does not support a required use case, fail fast instead of returning fake results or silently dropping filters.

## 31. Migrating from Elasticsearch to OpenSearch

A migration workflow should include:

1. **Inventory:** list server/client/Spring Data versions, indexes, mappings, templates, aliases, plugins, ingest pipelines, security, and dashboards.
2. **Feature mapping:** map each feature to its corresponding OpenSearch API/feature.
3. **Compatibility spike:** create a proof of concept for critical queries and operations.
4. **Target design:** choose the OpenSearch version, Java client, Spring integration, and plugins.
5. **Data migration:** snapshot if the version pair is supported, or reindex/export-import/rebuild.
6. **Validation:** compare counts, samples, query results, sorting, aggregations, and security.
7. **Performance test:** measure throughput, latency, memory, and recovery.
8. **Cutover:** switch traffic via endpoint/alias/service discovery according to plan.
9. **Observe:** monitor errors, lag, search quality, and resources.
10. **Rollback:** retain the old source/index and rollback conditions for a defined window.

Do not migrate production by simply changing a hostname in config and waiting to see what happens. That ignores differences in clients, plugins, mappings, and security.

## 32. Data migration and reindexing

If snapshots are outside the supported range, other methods can be used:

- Remote reindex if supported and configured on target/source.
- Batch export followed by bulk indexing.
- ETL pipeline.
- Rebuild index from the database/source of truth.
- Dual-write or change streams during the catch-up phase.

For large datasets, create a new target-version index, ingest data in batches, and then replay changes occurring after the snapshot.

Verify:

- Stable IDs.
- Update versions/ordering.
- Delete events.
- Date/number conversions.
- Analyzers and field transformations.
- Partial bulk failures.
- Retries and DLQs.
- Counts and checksums.
- Alias switch and rollback.

Do not only compare total counts. Reconcile by tenant, document type, status, and time ranges to catch localized discrepancies.

## 33. Dual-run and result comparison

During a validation phase, you can send the same query to both the old and new clusters while returning only the selected system's response. Results from the other cluster are used for comparison.

Bound the dual-run so you do not unexpectedly double load. You can sample a fraction of requests or run masked traffic replay.

Compare:

- Success/error rates.
- Latency p50/p95/p99.
- Hit IDs and top-K ordering.
- Aggregation counts.
- Highlight behavior.
- Mapping errors.
- Bulk indexing success.
- Data freshness.
- Security/tenant filtering.

Do not log full queries or responses containing sensitive data. Use request IDs and sanitized/reduced metrics.

## 34. Cutover and rollback

A typical cutover strategy looks like:

~~~text
             Source of truth
                    |
             Sync / CDC stream
                /       \
               v         v
        Old search     New search
           cluster       cluster
               \         /
                \       /
             Compare / validate
                    |
                    v
              Switch traffic
                    |
                    v
                Observe
                    |
          +---------+---------+
          |                   |
          v                   v
        Keep                Rollback
        target              to old
~~~

Before cutover:

- Catch up the backlog.
- Run reconciliation.
- Verify security and roles.
- Run smoke/performance tests.
- Prepare rollback endpoints/configs.
- Identify who is authorized to execute cutover.
- Retain enough source data to rebuild if needed.

After cutover, do not delete the old cluster immediately. Keep it for the defined rollback window, while avoiding indefinite dual-writes if there is no consistency mechanism.

## 35. When should you choose Elasticsearch or OpenSearch?

The decision depends on many factors:

- Required features.
- Licensing and legal requirements.
- Available managed services.
- Plugin ecosystem.
- Spring integration/client support.
- Operational skills of the team.
- Security and compliance.
- Search quality and performance.
- Infrastructure/support costs.
- Upgrade and migration roadmap.

There is no single best choice for every application. If a project relies heavily on Elastic-specific features or Elastic Stack integrations, carefully evaluate switching costs. If a project requires an Apache 2.0 distribution and OpenSearch features meet the use cases, OpenSearch may be a good fit. Base the decision on actual versions and features, not just product names.

## 36. Compatibility verification checklist

**Server and client**

- Identify the exact Elasticsearch/OpenSearch version.
- Identify the Java client artifact and version.
- Avoid mixing packages/clients from the two products arbitrarily.
- Verify JDK and TLS/authentication.
- Check the dependency tree and version alignment.

**Spring**

- Confirm Spring Boot and Spring Data release train.
- Check the official compatibility matrix.
- Verify repositories, Operations, and `NativeQuery`.
- Verify mapping/conversion.
- Verify reactive APIs if using WebFlux.
- Check runtime errors and serialization.

**Features**

- Query DSL and filters.
- Sort, pagination, `search_after`, and PIT.
- Aggregations and composite aggregations.
- Highlighting.
- Bulk, update, and delete.
- Analyzers, synonyms, and plugins.
- Ingest pipelines.
- Vector/hybrid search.
- Security/DLS/FLS.
- Snapshot/restore, aliases, and lifecycle.

**Operations**

- Index templates and settings.
- Plugin binaries/versions.
- Dashboards and saved objects.
- Backup/recovery.
- Monitoring and alerting.
- Performance benchmarks.
- Data reconciliation.
- Rollback plan.

## 37. Common mistakes when assessing compatibility

| Misconception | Why It Is Wrong | How to Verify |
|---|---|---|
| Both use Lucene so they are fully compatible | APIs and features have evolved separately | Test REST, queries, and semantics |
| Both have REST APIs so changing hostname is enough | Client models, endpoints, and responses may differ | Run smoke tests on the version pair |
| Spring Data Elasticsearch supports all OpenSearch | Spring Data has a release matrix for Elasticsearch/clients | Check the specific integration/version |
| Elasticsearch Java client works as-is with OpenSearch | Client models and APIs differ | Use the ecosystem's client or explicitly test scope |
| Compatibility mode guarantees cross-product support | Mode has a specific major-version scope | Read client/server contract |
| Any snapshot can be restored | Snapshots depend on version, product, and plugins | Check migration matrix and test restore |
| Elasticsearch plugins run on OpenSearch | Plugin binaries/APIs are tied to product/version | Find plugins built for the target |
| Query returning 200 means results are identical | Analyzers/scoring/mappings may differ | Compare fixtures and retrieval semantics |
| Same security role names | Security models/APIs differ | Test actual authorization |
| Can rolling-upgrade across products | Cluster protocols/metadata are incompatible | Stand up a separate target cluster and migrate |

## 38. Decision-making process for a Spring project

1. Record the current and target servers with full versions.
2. Record Spring Boot, Spring Data Elasticsearch, and the Java client.
3. List the Spring Data APIs in use.
4. List plugins, analyzers, mappings, and security features.
5. Mark which features are mandatory and which can be substituted.
6. Check the compatibility matrix of Spring Data and the client.
7. If using OpenSearch, check the OpenSearch Java Client or corresponding Spring integration.
8. Set up an integration environment with the exact versions.
9. Run smoke tests and query fixtures.
10. Run load tests, recovery tests, and security tests.
11. Create a migration/rollback plan.
12. Explicitly document supported, unsupported, and unverified feature scope.

If a feature has not been verified, mark it unknown instead of guessing. That is vital information for deciding whether that backend can be taken to production.

Elasticsearch and OpenSearch share a common history, Lucene, and many REST/Query DSL concepts, yet they are now two independent products. Spring Data Elasticsearch is designed around the compatibility matrix of each release with Elasticsearch and its corresponding Java client; connecting to OpenSearch in certain scenarios does not equate to full support. When selecting or switching backends, independently verify server, client, Spring Data, mappings, analyzers, plugins, security, aggregations, pagination, and snapshots. A clear version matrix paired with integration tests on the exact product pair is far more reliable than assuming the two systems are drop-in replacements.
