# Multiple Indices, Multiple Clusters, and Cross-Source Query Limits

A Spring Data Elasticsearch application may need to search across multiple indices, multiple datasets, or multiple Elasticsearch clusters. For example, a product catalog partitioned by year, tenant, or region; a system with one cluster for transactional data and another for analytics; or a screen aggregating results from multiple independent systems.

These scenarios look similar on the surface yet differ architecturally:

- **Multiple indices in the same cluster:** a single search request can target multiple indices, aliases, or index patterns. Elasticsearch coordinates shards and merges results within the same cluster.
- **Multiple clusters:** each cluster has its own client, connections, access permissions, state, and resource limits. Searching across clusters requires Cross-Cluster Search (CCS), or the application must fan out requests to multiple clients and merge results.
- **Multiple heterogeneous data sources:** Elasticsearch does not automatically join with databases, message brokers, or other search engines. The application must build a read model or coordinate results at the service layer.

Spring Data Elasticsearch provides `ElasticsearchOperations`, `IndexCoordinates`, repositories, and query abstractions for working with indices. However, an `ElasticsearchOperations` instance is bound to a configured client/cluster. Passing multiple index coordinates does not cause a query to automatically run across multiple independent clusters.

## 1. Distinguishing indices, aliases, clusters, and data sources

Before designing cross-source queries, identify which resources are being combined.

| Concept | Meaning | Example |
| --- | --- | --- |
| Index | Space storing documents and shards within a cluster | products-2025 |
| Alias | Logical name pointing to one or more indices | products-read |
| Index pattern | Expression selecting multiple indices | products-* |
| Cluster | An Elasticsearch deployment with its own cluster state and resources | catalog-cluster |
| Remote cluster | Another cluster configured for access by a coordinating cluster | archive |
| Data stream | Logical name managing time-based backing indices | product-events |
| Data source | System producing or storing data | PostgreSQL, Kafka, Elasticsearch |

### 1.1. Multiple indices are not multiple clusters

The following indices may all reside within one cluster:

~~~text
catalog-cluster
  |
  +-- products-2024
  +-- products-2025
  +-- products-2026
  +-- products-current
~~~

A single search request can target multiple indices in that cluster:

~~~http
GET /products-2024,products-2025,products-2026/_search
~~~

Or use an index pattern:

~~~http
GET /products-*/_search
~~~

Elasticsearch routes the query to the relevant shards within that cluster and reduces the results.

### 1.2. Multiple clusters have distinct boundaries

~~~text
Application
   |
   +---- client A ----> catalog-cluster
   |
   +---- client B ----> archive-cluster
   |
   +---- client C ----> analytics-cluster
~~~

Each cluster may have its own endpoints, TLS, and credentials; its own cluster state, indices, shards, and nodes; different mappings/analyzers; different Elasticsearch versions within supported compatibility ranges; distinct resource limits, latency, and availability; and separate access permissions and retention policies.

A request to `catalog-cluster` does not automatically know `archive-cluster` exists. Searching another cluster requires configuring CCS or sending requests using that cluster's client.

### 1.3. Multiple data sources do not mean Elasticsearch can join them

Elasticsearch can query documents in the indices supplied to a search request. It does not automatically perform distributed SQL joins against PostgreSQL, a Kafka topic, or a business API.

If you need to search across data from multiple systems, there are typically three approaches:

1. Sync searchable data into a single Elasticsearch read model.
2. Fan out queries to each source and merge at the application layer.
3. Use a federation/search platform suited to the source types and business requirements.

Which approach to choose depends on what needs to be joined, freshness, latency, and consistency requirements.

## 2. Searching across multiple indices in the same cluster

This is the simplest case. A query can target multiple indices via an explicit index list, an alias pointing to multiple indices, an index pattern/wildcard, or a data stream.

Example:

~~~http
GET /products-2025,products-2026/_search
{
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

Or:

~~~http
GET /products-*/_search
{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

Elasticsearch returns a merged set of hits from the queried shards. Each hit still carries metadata indicating its source index via the `_index` field.

### 2.1. Using an explicit list of indices

An explicit list fits when the application knows exactly which indices to read, the index count is small and stable, accidental querying of unrelated indices must be avoided, or index lifecycles are managed in code/config.

~~~java
IndexCoordinates coordinates = IndexCoordinates.of(
    "products-2025",
    "products-2026"
);

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class, coordinates);
~~~

`IndexCoordinates` represents the target indices of a Spring Data operation. When passing multiple index names, the search operation can target multiple indices in the same cluster, depending on the API and version used.

Do not pass index names from another cluster here expecting Spring Data to pick another client automatically. `IndexCoordinates` only specifies target index names for requests sent through the current `operations` instance.

### 2.2. Using wildcards/index patterns

Index patterns query a set of indices created by convention:

~~~java
IndexCoordinates coordinates =
    IndexCoordinates.of("products-202*");
~~~

Patterns are useful when indices are partitioned by year or bucket. However, broad wildcards can match more indices than intended, increasing the number of queried shards and reduce overhead.

Avoid generic patterns like `*` in everyday application queries. They can touch internal indices, other modules' indices, or data with incompatible schemas.

### 2.3. Using aliases as an abstraction

Aliases provide a stable logical name:

~~~text
products-read
    |
    +--> products-2025
    +--> products-2026
~~~

The application queries `products-read` without knowing which physical indices hold the data. When adding a new index, operations updates the alias; code keeps using the same logical name.

Aliases fit when the application needs to read multiple indices sharing a schema, physical indices roll over or get replaced periodically, indices must switch without code changes, or physical storage layout should be hidden from repositories/services.

### 2.4. Read aliases and write aliases

A read alias can point to multiple indices. A write alias typically needs one designated write index so write operations have a single target.

~~~http
POST /_aliases
{
  "actions": [
    {
      "add": {
        "index": "products-2025",
        "alias": "products-read"
      }
    },
    {
      "add": {
        "index": "products-2026",
        "alias": "products-read"
      }
    },
    {
      "add": {
        "index": "products-2026",
        "alias": "products-write",
        "is_write_index": true
      }
    }
  ]
}
~~~

The application reads through `products-read` and writes through `products-write`. Never point a write alias at multiple indices without an explicit write index.

## 3. Important limitations when searching multiple indices

A search request across multiple indices is a distributed query within one cluster, which does not mean all indices can be assumed to share an identical schema.

Key limitations:

- Mappings for the same field may have different types.
- Analyzers or normalizers may differ.
- A field may exist in one index and not in another.
- Sorting and aggregations require compatible data types.
- Queries hit more shards, so cost scales with shard count.
- Relevance scores can be skewed by different corpus statistics.
- Pagination and snapshot consistency must be designed carefully.

### 3.1. Mappings must be compatible

Suppose:

~~~text
products-2025:
  price -> double
  brandId -> keyword
  name -> text

products-2026:
  price -> keyword
  brandId -> keyword
  name -> text
~~~

A range query on `price` may work on one index yet fail or behave incompatibly on the other. Sorting/aggregating on fields with differing types can also fail.

Before grouping indices under an alias or query, establish a schema contract covering field names/types, analyzers/normalizers, date formats and timezone semantics, nested/object structures, multi-fields, null/missing behavior, and document schema versions.

### 3.2. Fields missing in some indices

A field may not have been added to older indices yet. Multi-index queries may need `unmapped_type` for sorting or mapping governance to avoid errors when fields are absent.

~~~json
{
  "sort": [
    {
      "rating": {
        "order": "desc",
        "unmapped_type": "double"
      }
    }
  ]
}
~~~

`unmapped_type` lets Elasticsearch handle indices lacking that field in certain sort contexts. It does not turn missing fields into valid data and cannot resolve mapping conflicts between incompatible types.

### 3.3. Mapping conflicts cannot be fixed by wildcards alone

If one index stores `price` as `keyword` and another stores `price` as `double`, an index pattern does not convert between mappings automatically. Options include:

- Creating new indices under a unified schema and reindexing older data.
- Introducing a new field with a unified name/schema.
- Splitting queries across compatible mapping groups.
- Normalizing data at the ingest or application layer.

Avoid relying on ad-hoc runtime conversions for production queries because cost and semantics are hard to control.

## 4. Repositories and ElasticsearchOperations with multiple indices

Spring Data Elasticsearch has two common usage styles: repositories driven by entity metadata such as `@Document(indexName = "products")`, and `ElasticsearchOperations` accepting explicit `IndexCoordinates` per operation.

### 4.1. Repositories usually bind to entity metadata

~~~java
@Document(indexName = "products-read")
public class ProductDocument {
    @Id
    private String id;
    private String name;
}
~~~

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
~~~

Repositories use the index/alias from entity metadata. This is convenient when a repository always operates against the same logical index.

Ordinary repository methods do not accept a different `IndexCoordinates` per call. If you must select indices dynamically by tenant, time, or shard group, use `ElasticsearchOperations` with explicit coordinates or design dedicated repositories/operations.

### 4.2. Using ElasticsearchOperations with multiple indices

~~~java
IndexCoordinates coordinates = IndexCoordinates.of(
    "products-2025",
    "products-2026"
);

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class, coordinates);
~~~

An `ElasticsearchOperations` instance uses its configured client/template. Multiple index coordinates in a request still target the cluster that client connects to.

### 4.3. IndexCoordinates is not a cluster selector

Do not write the following expecting two indices on two separate clusters:

~~~java
IndexCoordinates coordinates = IndexCoordinates.of(
    "cluster-a:products",
    "cluster-b:products"
);
~~~

The string `cluster-a:products` only acts as a remote index expression in a CCS request if the coordinating cluster already configured remote cluster alias `cluster-a`. It does not cause Spring Data to create or pick two different clients.

If the remote cluster is not configured, the request fails because the remote alias is unrecognized or unreachable.

## 5. Multiple Elasticsearch clusters in one Spring application

When an application must talk to two independent clusters without CCS, configure two clients and two corresponding operations/templates.

~~~text
Spring ApplicationContext
       |
       +-- catalogClient
       |       |
       |       +-- catalogOperations
       |       +-- catalogRepositories
       |
       +-- archiveClient
               |
               +-- archiveOperations
               +-- archiveRepositories
~~~

Each operations instance must be wired to its proper client. When injecting into repositories or services, dependency injection must explicitly identify which cluster is used.

### 5.1. Separating client configurations

Conceptual configuration:

~~~java
@Configuration
class CatalogElasticsearchConfiguration {

    @Bean
    ElasticsearchClient catalogClient() {
        // Create client connecting to catalog cluster.
        return createCatalogClient();
    }

    @Bean
    ElasticsearchOperations catalogOperations(
            ElasticsearchClient catalogClient) {
        // Create Spring Data operations from catalog client.
        return createOperations(catalogClient);
    }
}
~~~

~~~java
@Configuration
class ArchiveElasticsearchConfiguration {

    @Bean
    ElasticsearchClient archiveClient() {
        // Create client connecting to archive cluster.
        return createArchiveClient();
    }

    @Bean
    ElasticsearchOperations archiveOperations(
            ElasticsearchClient archiveClient) {
        // Create Spring Data operations from archive client.
        return createOperations(archiveClient);
    }
}
~~~

`createCatalogClient`, `createArchiveClient`, and `createOperations` are placeholders showing structure. Actual client, transport, converter, and template setup depend on your project's Spring Data Elasticsearch, Java API Client, and TLS/authentication versions.

In real applications, avoid ambiguous bean names or indistinguishable candidates. Use explicit bean names and qualifiers.

### 5.2. Injecting the right operations

~~~java
@Service
class ProductSearchService {

    private final ElasticsearchOperations catalogOperations;
    private final ElasticsearchOperations archiveOperations;

    ProductSearchService(
            @Qualifier("catalogOperations")
            ElasticsearchOperations catalogOperations,
            @Qualifier("archiveOperations")
            ElasticsearchOperations archiveOperations) {
        this.catalogOperations = catalogOperations;
        this.archiveOperations = archiveOperations;
    }
}
~~~

Every search call must use the operations instance for the right source. A query targeting the catalog cluster cannot use `archiveOperations` merely by changing the index name.

### 5.3. Separating repository scanning by operations

If using repositories for both clusters, bind each repository package to its matching operations bean via repository scanning config supported by your Spring Data version, such as `elasticsearchOperationsRef` on `@EnableElasticsearchRepositories`.

Structural example:

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.catalog.repository",
    elasticsearchOperationsRef = "catalogOperations"
)
class CatalogRepositoriesConfiguration {
}
~~~

~~~java
@Configuration
@EnableElasticsearchRepositories(
    basePackages = "com.example.archive.repository",
    elasticsearchOperationsRef = "archiveOperations"
)
class ArchiveRepositoriesConfiguration {
}
~~~

Verify attribute names and multi-config support against your Spring Data Elasticsearch version. The two package trees must not overlap on the same repository interfaces.

### 5.4. Reactive cluster clients

When using reactive operations, each cluster needs its own `ReactiveElasticsearchClient`/`ReactiveElasticsearchOperations`. Never mix a reactive repository with operations from another cluster.

A service can fan out reactive requests to multiple clusters, provided it composes `Publisher`s and handles errors/timeouts per source. If one cluster is slow, the merged result may be delayed depending on policy.

## 6. Cross-Cluster Search (CCS)

Cross-Cluster Search lets a coordinating Elasticsearch cluster route queries to configured remote clusters. The client sends one search request to the coordinating cluster, which fans out query execution to remote clusters and reduces the results.

~~~text
Application
    |
    v
Coordinating cluster
    |
    +---- local index
    |
    +---- remote alias A ----> archive cluster
    |
    +---- remote alias B ----> analytics cluster
    |
    v
Merged search response
~~~

CCS fits when you need a unified search API across indices living on multiple Elasticsearch clusters.

### 6.1. Configuring remote clusters

The coordinating cluster must know remote clusters via remote cluster connection settings. Configuration includes aliases, seed addresses or appropriate connection modes, TLS, authentication, and connection limits.

A remote alias is a logical name used in index expressions. For example, alias `archive` can represent the archive cluster.

Remote clusters must be configured before querying. Prepending `archive:` to an index name does not establish a connection on its own.

### 6.2. Remote index expression syntax

A CCS request can specify both local and remote indices:

~~~http
GET /products-current,archive:products-2024,archive:products-2025/_search
{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

Or use wildcards on remote indices:

~~~http
GET /archive:products-*/_search
{
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

The remote alias must match the configuration on the coordinating cluster. Index expressions can reference multiple remote aliases, though exact capabilities and syntax depend on Elasticsearch version.

### 6.3. Sending CCS via Spring Data Elasticsearch

Spring Data Elasticsearch uses its underlying configured client. If that client sends search requests to a CCS-enabled coordinating cluster, queries can pass remote index expressions inside `IndexCoordinates` if the API version passes those index expression strings intact.

Conceptual example:

~~~java
IndexCoordinates coordinates = IndexCoordinates.of(
    "products-current",
    "archive:products-2024",
    "archive:products-2025"
);

SearchHits<ProductDocument> hits =
    coordinatingOperations.search(
        query,
        ProductDocument.class,
        coordinates
    );
~~~

`coordinatingOperations` still connects only to the coordinating cluster. The Elasticsearch cluster itself performs CCS. If you need CCS-specific parameters not exposed by Spring Data abstractions, use the Elasticsearch Java API Client directly.

Do not configure a separate `ElasticsearchOperations` per remote alias when using CCS. Remote aliases are managed on the coordinating cluster, not as Spring client beans.

### 6.4. CCS is not a distributed transaction

CCS only merges search results. It does not provide atomic writes across clusters, arbitrary distributed joins across documents by business relationships, a shared transactional snapshot across all clusters, automatic data replication between remote clusters, or guarantees that all remote clusters are simultaneously available.

If multiple clusters must be updated, the application needs dedicated write workflows, retries, reconciliation, and partial-failure policies.

## 7. Consistency limits when querying multiple indices/clusters

Searching across multiple indices or clusters should not be treated as a snapshot read transaction across all sources.

### 7.1. No shared cross-cluster snapshot

A request may be dispatched to shards across multiple indices/clusters at slightly different instants. If data mutates mid-query, different sources may reflect slightly different points in time.

PIT can preserve a stable view within the scope Elasticsearch supports for that request, but do not assume a global transactional snapshot across all remote clusters. Verify combined PIT/CCS capabilities and remote limitations for your version.

If business logic demands a unified snapshot, you usually need a consolidated read model or data-layer watermarks/versions.

### 7.2. Eventual consistency across clusters

If data is replicated or projected asynchronously to multiple clusters, one cluster can be newer than another.

~~~text
catalog cluster: Product P-100 version 42
archive cluster: Product P-100 version 40
~~~

CCS can return both documents if both match the index pattern. Elasticsearch does not automatically know they are two versions of the same business aggregate.

The application must choose an authoritative source per document, store `sourceVersion`/`updatedAt` with clear semantics, deduplicate by business ID when needed, or ensure each aggregate exists in only one queried source.

### 7.3. Duplicate documents across indices

If the same document lives in both an old index and a new index, querying an alias pointing to both can return two hits with the same business ID.

Elasticsearch treats `_index` + `_id` as the identity within index scope; the same `_id` in two indices still represents two distinct documents.

Never assume Elasticsearch merges two hits sharing an ID. If using an alias to read both old and new indices during a migration, define a deduplication strategy or prevent overlap.

### 7.4. No automatic business joins

If products live in the catalog cluster and inventory lives in the stock cluster, CCS does not automatically join `product.id` with `inventory.productId` like a relational database.

Options:

- Sync inventory fields into the product search document.
- Fan out queries and join results in the service layer.
- Use a data platform/read model suited to the query.

Application-layer joins require well-defined pagination, sorting, and counting. Merely fetching the top 20 from each source and combining them does not guarantee an accurate global top 20 without an appropriate merge strategy.

## 8. Relevance scores across multiple indices and clusters

`_score` depends on the query and term statistics within each dataset/shard. When searching across multiple indices or clusters with different corpora, do not assume scores are directly comparable across all sources.

Factors involved:

- Term frequencies in each shard/index.
- Document counts and field distributions.
- Differing analyzers and mappings.
- Search type and how term statistics are gathered.
- Cluster versions and configurations.

### 8.1. Sort by field when business ordering is required

If global ordering by price, timestamp, or a shared-semantics ranking field is needed, sort by a field with uniform mappings.

~~~json
{
  "sort": [
    {
      "updatedAt": {
        "order": "desc",
        "unmapped_type": "date"
      }
    },
    {
      "productId": {
        "order": "asc",
        "unmapped_type": "keyword"
      }
    }
  ]
}
~~~

A tie-breaker field stabilizes ordering when multiple documents share `updatedAt`. Data types must be compatible across indices.

### 8.2. dfs_query_then_fetch

Elasticsearch offers the `dfs_query_then_fetch` search type, which gathers term statistics across shards before querying to improve scoring consistency in certain distributed queries.

It adds an extra round trip and overhead. Do not enable it merely because a query hits multiple indices. With CCS, search type support and semantics vary by version; do not assume it produces perfectly normalized relevance scores across clusters with very different data or mappings.

### 8.3. Normalizing ranking at the application layer

When merging results from sources with incompatible scoring, you can sort by a shared-semantics field, apply a common ranking model over normalized data, combine scores with source priority or freshness, use Reciprocal Rank Fusion (RRF) or an appropriate rank-fusion method if supported, and deduplicate by business ID before returning results.

Never compare raw `_score` values across different queries or different-corpus clusters unless comparability has been verified.

## 9. Pagination and sorting across multiple indices

Pagination easily becomes unstable if indices have differing mappings or data mutates while users page through results.

### 9.1. from/size

`from/size` suits shallow pagination. Elasticsearch enforces `index.max_result_window` on deep pagination, commonly defaulting to 10,000 hits in many setups.

Raising the limit increases memory and heap pressure because shards must buffer larger result sets. Do not increase `max_result_window` as a universal pagination fix.

### 9.2. search_after

For deep results, use deterministic sorting and `search_after` to fetch the next page from the sort values of the previous page's last hit.

Example sort:

~~~json
{
  "sort": [
    { "updatedAt": "desc" },
    { "productId": "asc" }
  ]
}
~~~

The next page passes `search_after` matching the sort values of the last hit from the prior page. Sort fields must have doc values and compatible mappings across indices.

### 9.3. PIT

Point in Time maintains a stable view during deep pagination over a supported index/cluster scope. Combining PIT with `search_after` avoids items shifting due to refreshes/indexing between pages.

With CCS, PIT and remote cluster support carry version- and topology-specific constraints. Never assume PIT IDs or lifecycles behave identically to local queries; verify against documentation for your running version.

### 9.4. Pagination with multi-client fan-out

If the application dispatches separate requests to each cluster and merges them:

1. Each source returns a local page.
2. The application merges results by a common sort key.
3. Separate cursors/continuation tokens must be kept per source.
4. The next page must resume from each source's cursor.

Simply requesting the same `from/size` from every cluster and concatenating does not guarantee accurate global pagination. A k-way merge algorithm with sufficient per-source lookahead is required.

If one source returns insufficient results or times out, the merged page may miss items that belong earlier in the global order.

## 10. Aggregations across multiple indices and clusters

Within a single cluster, aggregations can span multiple indices in one search request if mappings are compatible.

~~~http
GET /products-2025,products-2026/_search
{
  "size": 0,
  "aggs": {
    "by_brand": {
      "terms": {
        "field": "brandId"
      }
    },
    "average_price": {
      "avg": {
        "field": "price"
      }
    }
  }
}
~~~

Results are reduced across shards. However, field types must be compatible; distributed `terms` aggregations can incur approximation error depending on `shard_size`; `cardinality` aggregations are approximate by algorithm; pipeline aggregations depend on collected buckets; and multi-index aggregations can consume substantial memory and CPU.

### 10.1. Aggregations and missing fields

If an index lacks `brandId`, aggregations skip documents missing that value. Distinguish missing fields from actual business values.

If field mappings differ, the request can fail. Standardize schemas or split queries by compatible mapping groups.

### 10.2. Aggregations over CCS

CCS can execute searches and reduce aggregations from remote clusters within supported feature/version boundaries. However, not every aggregation, plugin, or cluster topology behaves identically to a single index.

Verify remote cluster version compatibility, field mappings and types, shard failures/partial results, bucket limits and memory, aggregation accuracy, and security privileges on remote indices.

### 10.3. Aggregations with application fan-out

If querying separate clusters independently, the application must merge aggregation results. Never sum or average values blindly:

- `sum` can generally be added if units and filter semantics match.
- `count` requires knowing whether documents duplicate across sources.
- `avg` must be merged using `sum` and `count`, not by averaging averages.
- `cardinality` estimates cannot simply be summed to produce exact global cardinality.
- `percentiles` and `histograms` need proper merge algorithms or centralized queries.

For analytics requiring exact, consistent numbers, a unified pipeline/materialized dataset is usually better than ad-hoc response merging.

## 11. Failure semantics when querying multiple sources

When searching across multiple indices/shards/clusters, some sources may fail while others return results.

### 11.1. Shard failures within one cluster

A search response can report shard failures. If partial results are allowed, the response still contains hits from healthy shards without representing the full dataset.

The application must check `timed_out`, failed shard counts, shard failure lists, `terminated_early` if present, and CCS remote cluster status when using CCS.

Never assume HTTP 200 guarantees all shards succeeded.

### 11.2. Remote cluster unavailable

In CCS, a remote cluster may be unreachable or time out. Depending on request configuration, Elasticsearch can return a partial response or fail the whole request.

Choose a policy per business needs:

- **Strict:** if a mandatory source fails, return an error to the caller.
- **Best effort:** return results from healthy sources along with failed-source status.
- **Fallback:** fall back to a read model/cache if permitted.

Never silently drop remote failures if the UI requires complete results.

### 11.3. Timeouts and deadlines

A multi-cluster query's latency is bounded by the slowest source if the application waits for all of them. Set an overall deadline, per-source timeouts, and a cancellation policy.

When fanning out with reactive APIs, handle timeouts and errors on each `Publisher`. A single failing branch can fail `zip`/`combine` completely unless mapped into a per-source result wrapper.

### 11.4. Circuit breakers

If a cluster fails repeatedly, a circuit breaker prevents the application from flooding the degraded source with requests.

Define trip thresholds, open duration, half-open probes, fallback or partial response behavior, metrics, and alerts.

Never let a circuit breaker turn data errors into empty results without notifying the caller.

## 12. Security when querying multiple indices/clusters

Each index/cluster can have its own access permissions.

### 12.1. Least privilege

Clients should only hold read permissions for required indices. Never use cluster-admin credentials solely to run searches.

### 12.2. CCS remote privileges

CCS requires proper privileges on both the coordinating cluster and remote clusters. Depending on Elasticsearch security/version, the remote user or API key must hold read permissions on the target indices/cluster.

Do not assume permission to read local indices automatically grants permission to read remote indices.

### 12.3. Tenant filters must apply to every source

If the application fans out to multiple clusters, tenant/authorization conditions must be applied to every request. Forgetting the filter on one source can leak data.

With CCS, ensure remote index mappings and security policies enforce identical tenant semantics. Application query filters do not replace Elasticsearch access controls.

### 12.4. Never let clients pick arbitrary indices

Never take a raw index expression from users and pass it straight to `IndexCoordinates` or a CCS request. Resolve tenants/sources/indices from controlled configuration or authorization context.

Overly broad index expressions can query out-of-scope data or cause heavy load.

## 13. Choosing between aliases, CCS, and application fan-out

| Need | Usually suitable solution | Reason |
| --- | --- | --- |
| Multiple indices in one cluster, same schema | Alias | Stable logical name, easy operations |
| Multiple indices in one cluster, pattern-based set | Index pattern | Query index families by convention |
| Multiple Elasticsearch clusters needing one search response | CCS | Elasticsearch coordinates and reduces |
| Multiple clusters with independent auth/clients/policies | Multiple operations + application fan-out | Independent per-source control and failure handling |
| Joining Elasticsearch data with a database | Read model or application join | CCS is not a relational join |
| Complex global ranking and pagination | Unified read model/search service | Easy control over schema, score, and cursor |
| Sources with differing freshness | Source version/freshness policy | Must decide which record is authoritative |

### 13.1. Prefer aliases when only physical indices differ

If all indices sit in one cluster with the same schema, an alias is usually the cleanest abstraction. Services do not need to track physical index lists.

### 13.2. Use CCS when remote sources are Elasticsearch

If all sources are Elasticsearch clusters and a single merged search response is needed, CCS reduces fan-out and merge code in the application.

However, CCS does not eliminate requirements for mapping compatibility, security, latency budgets, remote failure handling, and pagination.

### 13.3. Use fan-out when per-source control is needed

Application fan-out fits when each cluster needs different queries, each source has distinct authentication or timeouts, business-specific fallback/partial results are required, results need transformation before merging, or CCS is unsuitable/unavailable.

In return, the application must implement merge algorithms, pagination, aggregation reconciliation, and duplicate handling itself.

### 13.4. Build a unified read model for frequent queries

If every request has to call five clusters and then join/deduplicate/sort, cost and complexity escalate fast. Build a consolidated Elasticsearch index/read model updated from sources via CDC/outbox.

A unified read model needs clear document IDs and source ownership, versioning and idempotency, a unified schema, reconciliation and rebuildability, freshness SLAs, and delete/tombstone handling.

This is usually the better choice for high-frequency cross-source queries with stable semantics.

## 14. Spring Data example: searching via a multi-index alias

Entity:

~~~java
@Document(indexName = "products-read")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String brandId;

    @Field(type = FieldType.Double)
    private Double price;
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {
}
~~~

Alias `products-read` points to `products-2025` and `products-2026`. The repository queries using the same logical name:

~~~java
Page<ProductDocument> products =
    productRepository.findByBrandId(
        "BRAND-10",
        PageRequest.of(0, 20)
    );
~~~

Which indices the alias targets is managed by Elasticsearch. No repository code changes are needed when adding a new index if mappings stay compatible.

## 15. Spring Data example: explicitly selecting multiple indices

When querying a specific set of indices:

~~~java
public SearchHits<ProductDocument> searchArchive(
        Query query,
        ElasticsearchOperations operations) {

    IndexCoordinates indices = IndexCoordinates.of(
        "products-2024",
        "products-2025"
    );

    return operations.search(
        query,
        ProductDocument.class,
        indices
    );
}
~~~

This runs a single request on the cluster used by `operations`. If the index list varies per request, validate index names and never accept arbitrary raw patterns from clients.

## 16. CCS example with the Elasticsearch REST API

Suppose the coordinating cluster already configured remote alias `archive`:

~~~http
GET /products-current,archive:products-2024/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "ACTIVE"
          }
        }
      ]
    }
  },
  "sort": [
    {
      "updatedAt": {
        "order": "desc",
        "unmapped_type": "date"
      }
    }
  ]
}
~~~

This request goes to the coordinating cluster. Remote alias `archive` must be configured and credentials must have read permissions on the target index.

If `updatedAt` mappings differ between local and remote indices, sorting can error or behave inconsistently. `unmapped_type` handles only unmapped fields; it does not resolve general mapping conflicts.

## 17. Application fan-out example across two clusters

When using two separate `ElasticsearchOperations` beans, a service can call each source:

~~~java
public record SearchSourceResult<T>(
    String source,
    List<T> items,
    boolean complete,
    String error
) {}
~~~

~~~java
public SearchResponse<ProductDocument> searchAcrossSources(
        Query query) {

    SearchSourceResult<ProductDocument> catalog =
        searchCatalog(query);

    SearchSourceResult<ProductDocument> archive =
        searchArchive(query);

    return mergeResults(catalog, archive);
}
~~~

This is an illustrative structure. `mergeResults` must define a common sort key, deduplication key, authoritative source on business ID collisions, failure policy when one source errors, per-source pagination cursors, aggregation merging, and freshness/version policies.

Never concatenate two lists in response-arrival order if result ordering is a business requirement.

### 17.1. Merging by sort key

If two sources return lists already sorted by the same key, a k-way merge can be used:

~~~text
Catalog: A(10), C(30), E(50)
Archive: B(20), D(40), F(60)

Merged:  A(10), B(20), C(30), D(40), E(50), F(60)
~~~

However, to guarantee the first page contains the global top N, each source must return enough items and continuation cursors must be maintained. If one source times out, the merged result is no longer guaranteed to reflect the global top N.

### 17.2. Deduplicating by business ID

If the same `Product P-100` exists in both catalog and archive, choose one copy: prefer the live source, compare `sourceVersion`, compare authoritative timestamps with clear semantics, or drop the archive record if the product was migrated.

Never use `_score` to decide which record is newer.

## 18. Observability for multi-source queries

A cross-source search service must measure latency and health per source, not just overall endpoint duration.

| Metric | Meaning |
| --- | --- |
| `search_requests_total` | Total search requests |
| `search_source_latency` | Latency by cluster/source |
| `search_source_failures_total` | Failures by source |
| `search_partial_results_total` | Count of incomplete responses |
| `search_remote_timeout_total` | Remote cluster timeouts |
| `search_shard_failures_total` | Shard failures |
| `search_hits_per_source` | Hits returned per source |
| `search_merge_duration` | Application-side merge time |
| `search_duplicate_hits_total` | Hits sharing a business ID |
| `search_mapping_errors_total` | Mapping/type errors |
| `search_freshness_lag` | Data lag by source |

Logs should capture correlation ID, source name, index expression, latency, timeouts, shard/remote failures, and partial status. Avoid logging query payloads containing sensitive data.

### 18.1. Distinguishing query errors from source errors

A query can fail due to invalid syntax/DSL, field mapping conflicts, missing indices, insufficient permissions, shard failures, remote cluster timeouts, or circuit breaker/resource exhaustion.

Classifying errors informs whether to retry or fix the query. Never infinitely retry mapping or authorization errors.

## 19. Testing multi-index/cluster designs

Integration tests should exercise real boundaries.

### 19.1. Multiple indices in one cluster

- Create two indices with compatible mappings.
- Write documents with distinct IDs into each index.
- Query using an index list or alias.
- Verify hits arrive from both indices.
- Verify `_index` identifies the source.
- Verify sorting/aggregations behave accurately across the union.

### 19.2. Mapping incompatibility

- Create one index with a numeric field.
- Create another index with the same field as `keyword`.
- Run sort/range/aggregation queries.
- Verify the system detects the error or applies the split-query strategy.

### 19.3. CCS

- Configure a test remote cluster.
- Query local and remote indices in one request.
- Simulate remote unavailability.
- Verify partial-result policy.
- Verify remote access permissions.

### 19.4. Application fan-out

- Mock or spin up two separate test clusters.
- Make one source slow or failing.
- Verify timeouts/deadlines.
- Verify deduplication.
- Verify merge sorting and pagination.
- Verify aggregation merging if supported by the app.

### 19.5. Never run failure tests against production clusters

Tests need to create indices, swap aliases, or disconnect remote clusters. Use Testcontainers/test clusters and least-privilege credentials.

## 20. Common mistakes

**Assuming multiple IndexCoordinates select multiple clusters.** Coordinates only specify index expressions for the current client. Use CCS or multiple clients/operations.

**Using broad wildcards.** They can query unintended indices and increase shard count. Use aliases or narrow patterns.

**Grouping indices with differing mappings under one alias.** Queries, sorts, and aggregations can fail or return inconsistent results. Standardize schemas before grouping.

**Assuming aliases automatically deduplicate documents.** The same business ID across two indices still produces two hits. Deduplicate or design non-overlapping data.

**Using a write alias pointing to multiple indices without a write index.** Write operations can fail or target ambiguously. Configure `is_write_index` explicitly.

**Assuming repositories can switch indices per method via service-level IndexCoordinates.** Repositories normally rely on entity metadata. Use `operations` or configure repositories per index.

**Configuring multiple ElasticsearchOperations beans without qualifiers on injection.** Spring may complain about multiple candidates or inject an unintended bean. Use explicit bean names and qualifiers.

**Assuming CCS automatically sets up remote clusters.** Remote aliases must be configured on the coordinating cluster with proper credentials and networking.

**Treating CCS as a distributed transaction.** CCS only merges search responses. Multi-cluster writes need dedicated workflows.

**Treating `_score` from different clusters as directly comparable.** Corpus statistics, analyzers, and mappings may differ. Normalize ranking or sort by business fields.

**Paginating fan-out using identical from/size per source.** That does not guarantee global ordering or top N. Use k-way merges with per-source cursors or a unified read model.

**Merging averages by averaging averages.** Use sum and count to compute an accurate global average.

**Treating partial responses as complete results.** Check `timed_out`, shard failures, and remote cluster status.

**Omitting the tenant filter on one source.** That can leak data. Enforce authorization on every source.

**Using application fan-out without deadlines.** One slow source can hang requests indefinitely. Set timeouts and partial/fallback policies.

**Combining approximate aggregations as if they were exact.** `cardinality`, `percentile`, and `terms` buckets carry approximate/distributed semantics. Use proper merge algorithms or a unified analytics store.

## 21. Cross-source query design process

When tasked with searching across multiple indices or clusters:

1. Inventory data sources and classify which are Elasticsearch indices, clusters, or external systems.
2. Determine whether indices share a cluster or live on separate clusters.
3. If in one cluster with matching schemas, prefer aliases or explicit index lists.
4. If remote Elasticsearch clusters must be queried, evaluate CCS and remote cluster setup.
5. If sources require separate auth/failures/queries, consider multiple operations and application fan-out.
6. If frequent joins or complex global ranking/pagination are needed, consider a unified read model.
7. Standardize mappings, analyzers, field types, IDs, and `sourceVersion`.
8. Define duplicate handling and authoritative sources.
9. Choose a shared scoring/sorting strategy.
10. Design pagination and snapshot consistency.
11. Define aggregation semantics and partial-failure policies.
12. Configure timeouts, circuit breakers, security, and observability.
13. Test mapping conflicts, remote failures, duplicates, timeouts, and pagination.

## 22. References

- [Spring Data Elasticsearch - Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html): `ElasticsearchOperations`, `IndexCoordinates`, and query execution.
- [Spring Data Elasticsearch - Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories.html): repository abstractions and repository scanning configuration.
- [Elasticsearch - Search multiple indices](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-multiple-indices.html): index expressions, wildcards, and multi-index search.
- [Elasticsearch - Aliases](https://www.elastic.co/guide/en/elasticsearch/reference/current/aliases.html): read/write aliases and alias actions.
- [Elasticsearch - Cross-cluster search](https://www.elastic.co/guide/en/elasticsearch/reference/current/modules-cross-cluster-search.html): remote clusters and CCS.
- [Elasticsearch - Search API](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-search.html): search parameters, sorting, pagination, and partial results.
- [Elasticsearch - Pagination](https://www.elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html): `from/size`, `search_after`, and PIT.
- [Elasticsearch - Search aggregations](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations.html): distributed aggregations and reduce results.
- [Elasticsearch - Distributed search](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-shard-routing.html): shard routing and distributed search behavior.

CCS, PIT, remote cluster, and repository configuration APIs and limits may vary by Elasticsearch and Spring Data Elasticsearch version. Consult documentation/Javadoc matching your deployed dependencies. The essential principle is that multiple indices in one cluster can be queried in a single request when schemas are compatible; multiple clusters require CCS or multiple clients; and joins, transactions, global pagination, and cross-source consistency must be explicitly designed at the data or application layer.
