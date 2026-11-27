# OpenSearch Serverless and Choosing the Right Workload

## Lesson Objectives

Within the CLOUD_PROVIDERS_AWS ecosystem, Amazon OpenSearch Service delivers full-text search, log analytics, and semantic search over vector embeddings. When running a provisioned domain, operations teams must choose instance types, storage, shards, replicas, version upgrades, and capacity adjustments. Amazon OpenSearch Serverless removes most cluster management overhead by automatically provisioning and scaling compute for each collection.

Serverless does not mean every workload is automatically cheaper or design-free. Users still need to select collection types, design mappings and queries, set OpenSearch Compute Unit (OCU) limits, govern access permissions, choose ingestion paths, and monitor latency/cost. Picking the wrong collection type or capacity bounds can inflate costs, degrade performance, or leave required APIs unsupported.

After this lesson, learners will be able to:

- Explain collections, indexes, OCUs, and the decoupled indexing/search architecture.
- Distinguish Search, Time series, and Vector search collection types.
- Distinguish NextGen and Classic generations, collection groups, and scale-to-zero.
- Choose between OpenSearch Serverless and provisioned domains based on workload characteristics.
- Design mappings, ingest pipelines, queries, and basic vector search.
- Choose among OpenSearch Ingestion, Data Firehose, Fluent Bit, Lambda, or direct clients for ingestion.
- Configure encryption, network, and data access policies under least privilege.
- Measure capacity, storage, latency, indexing throughput, and costs.
- Identify API/plugin, snapshot, cross-account, and cross-Region limitations.
- Plan migrations, load testing, and production collection operations.

## 1. What Problem Does OpenSearch Serverless Solve?

Amazon OpenSearch Serverless is the on-demand deployment option for Amazon OpenSearch Service. Users create collections and indexes, send documents for indexing, and run queries. The service manages compute, shard placement, index lifecycles, software updates, and scaling instead of operating cluster nodes.

A collection is a group of OpenSearch indexes serving a workload or purpose. Examples:

- The `product-search` collection holds product indexes for website search.
- The `application-logs` collection holds application logs and incident investigation queries.
- The `knowledge-vectors` collection holds document embeddings for semantic search and RAG.

Serverless fits when traffic is uneven, has idle periods, is hard to forecast, or when teams want to focus on data and queries rather than cluster operations. The service still requires capacity to index and query; compute is billed per OCU and storage is billed separately.

## 2. Architecture: Collections, Indexes, and OCUs

In traditional provisioned domains, the same node group typically handles both indexing and search, and index volume ties closely to cluster storage and compute. OpenSearch Serverless separates ingestion compute from query compute and uses Amazon S3 as the primary storage layer for indexes.

~~~mermaid
flowchart LR
    P[Producers and applications] --> I[Indexing compute]
    I --> S3[(Managed storage on Amazon S3)]
    S3 --> Q[Search compute]
    Q --> C[Search clients and dashboards]
    I --> CW[CloudWatch metrics]
    Q --> CW
    S3 --> B[Collection and index metadata]
~~~

When producers write documents, indexing compute processes and writes indexes to managed storage. When applications query, search compute reads needed index data from storage or local caches and executes searches and aggregations. Because the two compute pools scale independently, a bulk ingestion burst does not dictate the same compute tier as peak query hours.

Capacity is measured in OpenSearch Compute Units:

- One OCU provides 6 GiB of memory, corresponding vCPU, and data transfer bandwidth to storage.
- Indexing capacity and search capacity are provisioned and tracked independently.
- The service scales OCUs up with workload demand and scales down as demand drops within configured min/max limits.
- Maximum capacity acts as a budget guardrail; setting it too low throttles workloads during spikes.
- Storage in managed storage is billed separately from OCU-hours.

Serverless manages shards and index lifecycles automatically. Users do not directly select data nodes, shard counts, or replica topologies as in provisioned domains.

## 3. Three Collection Types and How to Choose

Collection type is selected at creation time and cannot be changed afterward. Decide based on data shape, query patterns, and update requirements.

| Collection Type | Data and Queries | Suitable Workloads |
|---|---|---|
| Search | Structured or semi-structured documents; full-text, filters, sorts, aggregations | Product search, content search, profiles, internal documents |
| Time series | Logs, metrics, traces, and machine-generated timestamped data | Log analytics, security analytics, operations monitoring, behavioral analytics |
| Vector search | Embeddings and metadata; k-NN similarity search, metadata filtering | Semantic search, recommendations, image/document retrieval, RAG |

Search and Vector search keep data in hot storage to prioritize query speed. Time series can combine hot and warm storage: recent data stays hot, while older data moves to warm per NextGen time-series settings.

Key differences:

- Search and Time series do not support k-NN vector indexes; vector similarity search requires a Vector search collection.
- Time series collections do not support custom document IDs at index time and do not support upserts; updates by document ID work via supported APIs.
- Search collections fit application-controlled document IDs and frequent updates/upserts.
- Vector search collections use `knn_vector` mappings and carry generation-specific limits and behaviors.
- Never choose collection type solely by data name. For instance, logs might contain embeddings, yet if the primary workload is time-range log querying, Time series fits better; if semantic similarity is needed, build a dedicated Vector search collection.

## 4. Search Collections: Full-Text and Search Applications

Search collections fit scenarios where users search documents by keywords, phrases, structured fields, or business filters. OpenSearch supplies analyzers, inverted indexes, relevance scoring, aggregations, sorting, and query DSL.

Example e-commerce site searching by product name and filtering by category and price range:

~~~json
{
  "mappings": {
    "properties": {
      "product_id": {"type": "keyword"},
      "name": {"type": "text"},
      "category": {"type": "keyword"},
      "price": {"type": "float"},
      "available": {"type": "boolean"},
      "updated_at": {"type": "date"}
    }
  }
}
~~~

Create the index:

~~~http
PUT products
{
  "mappings": {
    "properties": {
      "product_id": {"type": "keyword"},
      "name": {"type": "text"},
      "category": {"type": "keyword"},
      "price": {"type": "float"},
      "available": {"type": "boolean"},
      "updated_at": {"type": "date"}
    }
  }
}
~~~

Query:

~~~http
POST products/_search
{
  "size": 10,
  "query": {
    "bool": {
      "must": [
        {"match": {"name": "wireless headphones"}}
      ],
      "filter": [
        {"term": {"category": "audio"}},
        {"term": {"available": true}},
        {"range": {"price": {"lte": 300}}}
      ]
    }
  },
  "sort": [
    {"updated_at": {"order": "desc"}}
  ]
}
~~~

Assign `keyword`, numeric, `date`, or `boolean` types appropriately for fields used in filters, sorts, and joins. Reserve `text` for full-text analysis; when a field needs both full-text search and exact filtering, use multi-fields. Align mappings with query patterns early because changing the type of an already-indexed field usually requires creating a new index and reindexing.

## 5. Time Series Collections: Logs and Operational Data

Time series collections target continuously generated machine data carrying timestamps and metadata such as service, host, environment, severity, trace ID, or tenant. Queries typically filter by time, group by service/level, and compute statistics.

Example log document:

~~~json
{
  "@timestamp": "2026-11-20T06:30:00Z",
  "service": "checkout",
  "environment": "production",
  "level": "ERROR",
  "trace_id": "trace-8f21",
  "message": "Payment provider timeout",
  "duration_ms": 4200
}
~~~

Time series indexes should define an explicit timestamp field and mappings for fields frequently used in filters/aggregations. Avoid uncontrolled dynamic mapping that spawns excessive fields.

### 5.1. Hot and Warm Storage in NextGen

NextGen Time series collections support `warm-after`. Setting `index.warm.after` specifies how long data in an index remains on hot storage before OpenSearch Serverless transitions older data to warm storage.

~~~http
PUT application-logs-2026.11
{
  "settings": {
    "index": {
      "warm": {
        "after": "7d"
      }
    }
  },
  "mappings": {
    "properties": {
      "@timestamp": {"type": "date"},
      "service": {"type": "keyword"},
      "level": {"type": "keyword"},
      "message": {"type": "text"}
    }
  }
}
~~~

Key points:

- `warm-after` applies only to NextGen Time series collections—not Search, Vector search, or Classic collections.
- If unconfigured, the default is 1 day; the minimum allowed value is 24 hours.
- Values take an integer followed by `d` or `h`, such as `7d` or `36h`.
- If the index has data retention configured, `warm-after` cannot exceed the retention window.
- Data transitions according to ingest order and underlying storage; warm timing is not necessarily calculated from document timestamps.
- Once data enters warm storage, queries still use the same index API, though latency characteristics may differ from hot data.

Pick `warm-after` based on active query windows. If dashboards primarily query the last 7 days, keep that window hot and move older data to warm. Benchmark historical query latencies before setting SLAs.

## 6. Vector Search: Semantic Retrieval and RAG

Vector search stores embeddings as numeric vectors. An embedding model encodes text, images, or other content into high-dimensional vectors; OpenSearch retrieves vectors nearest to a query vector under a chosen similarity metric.

Common similarity metrics:

- Cosine similarity: compares vector direction; typically suits normalized text embeddings.
- Euclidean distance (L2): measures geometric distance between vectors.
- Dot product: inner product, commonly used when the embedding model was trained for this metric.

A vector index can store embeddings alongside metadata such as document ID, title, category, tenant, timestamp, and ACL references. Applications can run semantic search combined with access-control, document-type, or business-attribute filters.

Example creating a vector index:

~~~http
PUT knowledge-vectors
{
  "settings": {
    "index.knn": true
  },
  "mappings": {
    "properties": {
      "embedding": {
        "type": "knn_vector",
        "dimension": 3,
        "space_type": "cosinesimil"
      },
      "document_id": {"type": "keyword"},
      "title": {"type": "text"},
      "tenant_id": {"type": "keyword"},
      "category": {"type": "keyword"}
    }
  }
}
~~~

`dimension` is set to 3 for illustration; production indexes must match the exact vector size emitted by your embedding model. Vectors with mismatched dimensions cannot be indexed.

k-NN query:

~~~http
POST knowledge-vectors/_search
{
  "size": 5,
  "query": {
    "knn": {
      "embedding": {
        "vector": [0.12, 0.34, 0.56],
        "k": 5,
        "filter": {
          "term": {"tenant_id": "tenant-42"}
        }
      }
    }
  },
  "_source": ["document_id", "title", "tenant_id", "category"]
}
~~~

Vector search results commonly power the retrieval stage in RAG:

1. Split documents into appropriately sized chunks.
2. Generate embeddings for each chunk using Amazon Bedrock or another embedding model.
3. Index vectors and metadata into a Vector search collection.
4. Generate an embedding for the user's question.
5. Retrieve top-k nearest chunks, enforcing metadata/authorization filters.
6. Inject retrieved context into the foundation model prompt.
7. Return answers with sources or citations for user verification.

OpenSearch Serverless supports vector dimensions up to 16,000. On NextGen vector collections, 32x compression is enabled by default; supported compression levels include 1x, 2x, 8x, 16x, and 32x. Compression shrinks memory/storage footprints yet can affect recall—benchmark retrieval quality on representative queries before deciding.

NextGen vector collections include default GPU acceleration for large index builds and a read-after-write refresh interval of roughly 5 seconds. Classic vector collections behave differently, including a ~60-second refresh interval and Faiss-specific HNSW algorithm constraints. Always identify the generation before applying documentation limits or migrating legacy collections.

## 7. NextGen vs. Classic: Two Generations to Distinguish

OpenSearch Serverless currently has two generations:

| Characteristic | NextGen | Classic |
|---|---|---|
| Status | Newer generation; default choice in current collection creation flows | Previous generation; existing collections still operate |
| Capacity management | Collection groups sharing OCUs across collections of the same type | Classic account-level / collection-group capacity settings |
| Scale to zero | Collection groups support minimum indexing/search OCU of 0 | Classic collection groups do not support min OCU of 0 |
| Collection creation | Express Create or Standard Create | Multi-step wizard |
| Time series `warm-after` | Supported | Not supported |
| Vector indexing | 32x compression default, GPU index-build acceleration, ~5s refresh | Distinct API and engine/algorithm constraints; Classic lacks Lucene ANN, IVF, or IVFQ per current docs; ~60s refresh |

NextGen Express Create automatically provisions a collection group and default security policies. Standard Create lets you specify the collection group, KMS key, network policy, and data access policy. Express Create defaults may enable public network access and grant broad data access to the creating IAM principal—review and tighten these before production use.

Classic collections do not upgrade generations automatically. To adopt NextGen features, provision a new collection, reindex data, and cut applications over via a migration plan.

## 8. Collection Groups and Capacity Sharing

A collection group organizes one or more collections under shared capacity limits. Collections in the same group share compute OCUs while maintaining independent encryption keys and data access policies.

Collection groups help:

- Pool workloads of the same type to share compute capacity efficiently.
- Set min/max indexing OCUs and search OCUs in one place.
- Cap total resource consumption per group.
- Group collections by environment, application, or security boundary.

A collection group holds only one collection type: Search, Time series, or Vector search—never mix all three workload types in one group. Collections inside the same group can still use distinct KMS keys; compute sharing does not weaken collection-level encryption or access isolation.

With NextGen, you can set min indexing OCU and min search OCU to 0 to scale to zero when idle. This reduces compute charges for intermittent workloads, though the first request after idle incurs cold-start/scale-up latency. For strict steady-latency SLAs, keep minimum capacity above 0 and budget for baseline capacity.

Maximum OCU acts as both a scaling ceiling and a budget guardrail. Setting it too low prevents scaling during ingest/search bursts. Base max values on load tests, SLAs, and budgets, and alert when OCU metrics approach limits.

## 9. Choosing OpenSearch Serverless vs. Provisioned Domain

OpenSearch Serverless and provisioned OpenSearch Service domains share the OpenSearch ecosystem yet differ in infrastructure management and control.

| Criterion | Serverless | Provisioned Domain |
|---|---|---|
| Capacity | Auto-scales in OCUs with min/max bounds | Operators pick instances, nodes, and storage |
| Shard/index lifecycle | Service manages most infrastructure decisions | Finer granular control |
| Ingest/search scaling | Indexing and search compute decoupled | Bound to cluster topology and sizing |
| Plugins/APIs | Supported subset only | Different and often broader feature set depending on version |
| Version/software updates | Service upgrades automatically | Operators plan upgrades |
| Cost model | OCU-hours and managed storage | Instance-hours, storage, and data transfer |
| Suitable workloads | Variable, intermittent, unpredictable loads with minimal cluster ops | Steady loads needing node/shard/plugin/API control and deep tuning |

Prefer Serverless when:

- You want to avoid managing clusters and capacity.
- Ingest and query traffic fluctuates or has idle windows.
- Supported collection types and API subsets cover your requirements.
- You want independent scaling for indexing and search.
- You want managed vector search without managing vector database nodes.

Prefer a provisioned domain when:

- You need plugins, APIs, or features unsupported by Serverless.
- You need direct control over shards, node topology, instance families, JVM, and deep cluster settings.
- Workloads are large, steady, and predictable, benefiting from right-sizing and Reserved Instances or Database Savings Plans.
- Cross-Region, cross-account, or specialized operational requirements demand domain architecture.
- You require strict control over upgrade schedules and version compatibility.

Never decide based on the buzzword "serverless" alone. Map out API/plugin requirements, throughput, latency, data volume, availability, security, retention, and total cost before choosing.

### 9.1. When to Use Another Service?

Not every dataset belongs in an OpenSearch index:

| Need | Service to Evaluate | Why |
|---|---|---|
| Interactive full-text search, filters, and relevance ranking | OpenSearch Serverless or provisioned domain | Built for low-latency search APIs |
| Quick log investigations already stored in Amazon CloudWatch Logs | CloudWatch Logs Insights | Queries log groups directly without maintaining a separate index |
| Ad hoc SQL over data stored in S3/data lakes | Amazon Athena | Queries on demand without ingesting duplicates into a search index |
| Real-time operational log/metric dashboards | OpenSearch Time series or tailored observability services | Needs indexed data for recurring interactive filters/aggregations |

If users only run occasional SQL queries over raw S3 files, Athena is simpler and cheaper than maintaining a search index. If applications need autocomplete, relevance scoring, semantic retrieval, or high-concurrency interactive filtering, OpenSearch fits better.

## 10. Ingesting Data: Choosing the Right Pipeline

OpenSearch Serverless supports multiple ingestion mechanisms:

| Source / Producer | Common Ingestion Path | When Appropriate |
|---|---|---|
| Web/backend applications | Direct OpenSearch client over HTTPS with SigV4 | Search documents or transactional indexing |
| Logs/metrics/traces | OpenSearch Ingestion or Fluent Bit | Streaming observability data |
| Amazon Data Firehose | Firehose delivery destination | Managed buffering, retries, and delivery |
| Kinesis Data Streams | Consumer/Lambda or OpenSearch Ingestion via supported pipelines | Event streaming and near-real-time indexing |
| Amazon S3 | Batch pipelines, Lambda, or OpenSearch Ingestion for supported sources | Backfills, data lake exports |
| DynamoDB | DynamoDB Streams + Lambda or suitable pipelines | Syncing record changes |
| Amazon Bedrock | Private service access or supported retrieval integrations | RAG and knowledge retrieval |

Amazon OpenSearch Ingestion is a serverless collector built on Data Prepper that filters, enriches, transforms, normalizes, and aggregates before writing to collections. Data Firehose also supports OpenSearch Serverless as a destination; Firehose's role requires `WriteDocument` in the data access policy and the target index must exist.

With Fluent Bit, configure the output AWS service name as `aoss` when signing requests. For applications using AWS SDKs/OpenSearch clients, sign SigV4 requests with service name `aoss` (distinct from `es` on provisioned domains), use TLS, and prefer temporary IAM role credentials. For custom request signers, verify `x-amz-content-sha256` requirements and client version compatibility with OpenSearch Serverless.

## 11. Ingest Pipelines and Document Normalization

An OpenSearch ingest pipeline is a sequence of processors executed prior to indexing. It can parse timestamps, rename fields, normalize values, strip sensitive fields, or generate embeddings in supported integrations.

Example simple pipeline normalizing timestamps and dropping unused fields:

~~~http
PUT _ingest/pipeline/normalize-logs
{
  "description": "Normalize application log documents",
  "processors": [
    {
      "set": {
        "field": "ingest_source",
        "value": "application"
      }
    },
    {
      "remove": {
        "field": "debug_payload",
        "ignore_missing": true
      }
    }
  ]
}
~~~

Send a document through the pipeline:

~~~http
POST application-logs/_doc?pipeline=normalize-logs
{
  "@timestamp": "2026-11-20T06:30:00Z",
  "service": "checkout",
  "level": "INFO",
  "message": "Order accepted"
}
~~~

Pipelines ensure every producer applies consistent normalization, though they do not replace upstream data quality checks. Validate schemas, event timestamps, required fields, and sensitive data before indexing.

## 12. Security Model: IAM, Encryption, Network, and Data Access

OpenSearch Serverless uses a different security model than provisioned domains. Each collection is protected by three policy layers:

1. Encryption policy specifies the KMS key encrypting the collection.
2. Network policy determines public vs. private endpoints and allowed network sources.
3. Data access policy specifies which principals can perform OpenSearch operations on collections/indexes.

Additionally, IAM identity policies govern calls to OpenSearch Serverless control-plane/API operations. IAM and data access policies are separate layers; granting permission in one layer does not automatically grant permission in the other.

~~~mermaid
flowchart TD
    U[IAM role or SAML identity] --> IAM[IAM identity policy]
    IAM --> API[OpenSearch Serverless API access]
    U --> DAP[Data access policy]
    NET[Network policy: public or VPC endpoint] --> C[Collection endpoint]
    ENC[Encryption policy: AWS owned or KMS CMK] --> C
    API --> C
    DAP --> C
    C --> IDX[Indexes and documents]
~~~

To reach a collection endpoint, principals normally need `aoss:APIAccessAll` in IAM. Accessing Dashboards additionally requires `aoss:DashboardsAccessAll`. Data access policies then grant granular permissions such as `CreateIndex`, `WriteDocument`, `ReadDocument`, or `UpdateIndex`. Missing either layer yields HTTP 403 even if the other permits access.

### 12.1. Encryption Policy

Encryption at rest is always enabled for collections—you choose an AWS owned key or a customer managed KMS key; encryption cannot be disabled. Encryption policies can target one collection or a multi-collection pattern.

With customer managed keys, key policies/grants must authorize OpenSearch Serverless to use the key. Never disable or schedule deletion for a key while collections depend on it; otherwise the service cannot read data and throws `KMSKeyInaccessibleException`.

Encryption in transit enforces TLS 1.2. Clients must call endpoints via HTTPS and sign requests as required.

### 12.2. Network Policy

Network policies allow public access or private access via OpenSearch Serverless-managed VPC endpoints. Access can be configured separately for the collection endpoint and the OpenSearch Dashboards endpoint.

Private endpoints let applications inside a VPC reach collections without traversing the public internet. Before creating a VPC-endpoint policy, provision the OpenSearch Serverless-managed VPC endpoint and reference its endpoint ID in the policy. AWS service private access such as Amazon Bedrock applies to the collection endpoint only, not the Dashboards endpoint.

Example private network policy:

~~~json
[
  {
    "Description": "Private access for product search",
    "Rules": [
      {
        "ResourceType": "collection",
        "Resource": ["collection/product-search"]
      },
      {
        "ResourceType": "dashboard",
        "Resource": ["collection/product-search"]
      }
    ],
    "AllowFromPublic": false,
    "SourceVPCEs": ["vpce-0123456789abcdef0"]
  }
]
~~~

This is an illustrative policy; replace the VPC endpoint ID with your actual endpoint. Check policy precedence when multiple network policies match the same collection.

### 12.3. Data Access Policy

Data access policies bind principals to collection- or index-level permissions. Example allowing an application role to create indexes and read/write documents in `products*` indexes:

~~~json
[
  {
    "Rules": [
      {
        "ResourceType": "collection",
        "Resource": ["collection/product-search"],
        "Permission": ["aoss:DescribeCollectionItems"]
      },
      {
        "ResourceType": "index",
        "Resource": ["index/product-search/products*"],
        "Permission": [
          "aoss:CreateIndex",
          "aoss:UpdateIndex",
          "aoss:DescribeIndex",
          "aoss:ReadDocument",
          "aoss:WriteDocument"
        ]
      }
    ],
    "Principal": [
      "arn:aws:iam::111122223333:role/ProductSearchAppRole"
    ]
  }
]
~~~

Separate ingest and query roles when workloads have distinct access needs. Producers need only `WriteDocument` and required index permissions; search consumers need only `ReadDocument`. Avoid granting `aoss:*` to every principal in production.

Data access policies are additive: multiple policies matching a principal/resource combine permissions; a narrower policy does not override broader grants from another policy. Data access policies have no explicit deny. When tightening permissions, audit every policy containing wildcards or overlapping collection/index patterns.

## 13. Creating Collections and Environment Rollout

Safe collection creation workflow:

1. Select a Region supported by OpenSearch Serverless that meets data residency rules.
2. Decide whether the workload is Search, Time series, or Vector search.
3. Choose NextGen, or keep Classic if compatibility with existing collections requires it.
4. For NextGen, select an appropriate collection group and configure min/max indexing and search OCUs.
5. Create an encryption policy using an AWS owned key or customer managed key.
6. Create a public/private network policy matching real connectivity paths.
7. Create data access policies for IAM roles or SAML identities.
8. Create the collection and wait for `Active` status.
9. Create index mappings, ingest pipelines, and index templates as needed.
10. Verify request signing, queries, latency, and metrics using the actual application role.

Express Create rapidly provisions a collection with default policies. However, defaults may open public networking and grant broad permissions to the creating principal. Use Express Create for sandboxes once you understand its defaults; for production, use Standard Create or audit every policy before loading real data.

Collection names must be unique per account/Region, 3–64 characters long, using only lowercase `a-z`, digits, hyphens, or underscores. Name collections by domain, workload, and environment—such as `product-search-prod` or `app-logs-staging`. Never embed customer names or sensitive data in resource names.

## 14. Capacity Planning, OCUs, and Scale-to-Zero

OCUs are tracked separately for indexing and search. Forecast both streams independently:

- Indexing: documents/second, bytes/second, bulk sizes, update rates, vector dimensions, and ingest transforms.
- Search: queries/second, concurrency, query complexity, aggregations, vector `k`, and latency targets.

With NextGen collection groups, set min/max for both:

~~~json
{
  "minIndexingCapacityInOCU": 0,
  "maxIndexingCapacityInOCU": 16,
  "minSearchCapacityInOCU": 0,
  "maxSearchCapacityInOCU": 16
}
~~~

These limits illustrate a small workload group, not a universal default or capacity guarantee. Run load tests to determine appropriate settings.

Scale-to-zero helps when collections sit idle for long spans, though cold-start/scale-up latency must be factored in. For 24/7 traffic with strict SLAs, keeping minimum OCUs above 0 yields steadier latency. For heavy bursts, ensure max OCUs are high enough to absorb peaks.

Setting max too low increases throttling or latency during surges. Setting max higher does not immediately consume full capacity, yet relaxes budget guardrails. Set CloudWatch alarms on `SearchOCU` and `IndexingOCU`.

## 15. Optimizing Indexes, Queries, and Vector Retrieval

### Search

- Choose accurate mappings for `text`, `keyword`, numeric, `date`, and geo fields.
- Place non-scoring conditions inside `filter` context.
- Return only required `_source` fields to shrink payloads.
- Avoid wildcard queries on high-cardinality fields when unnecessary.
- Use bulk indexing for large ingests and tune batch sizes.
- Create new indexes and reindex when incompatible mapping changes arise.

### Time Series

- Define an explicit timestamp field.
- Use `keyword` for frequently filtered fields like service, host, environment, and severity.
- Bound field explosion from dynamic mapping.
- Set `warm-after` based on common query windows.
- Configure retention around audit and operational needs.

### Vector Search

- Keep embedding models and dimensions consistent between indexing and querying.
- Match similarity metrics to the embedding model.
- Test recall/latency trade-offs before changing compression levels.
- Store metadata needed for tenant, ACL, category, and version filtering.
- Tune chunk size/overlap around document structure and retrieval evaluations.
- Measure recall@k, precision@k, MRR, or application-relevant metrics.
- Delete/reindex stale embeddings whenever models or chunking pipelines change.

Never rely on vector similarity as an authorization boundary. Always enforce access-control filters or application-side authorization before passing retrieved content into model prompts.

## 16. Observability and Operations

CloudWatch metrics reveal how much compute a collection consumes alongside ingest/search load. Monitor at least:

| Pillar | Metric or Signal | Operational Question |
|---|---|---|
| Capacity | `SearchOCU`, `IndexingOCU` | Approaching max OCU or scaling too frequently? |
| Ingest | Ingestion requests, indexing errors, rejected requests | Are producers writing cleanly? Any mapping errors? |
| Search | Search request rate, latency, rejected requests | Are queries meeting SLAs? |
| Storage | Managed storage usage | Is data growth exceeding budget? |
| Security | 403s, KMS errors, network connection failures | Are principals, keys, or VPC policies misconfigured? |
| Pipeline | OpenSearch Ingestion pipeline health, DLQ/error logs | Is data backing up or dropping? |

Build dashboards per collection/workload and alarm on:

- `SearchOCU` or `IndexingOCU` nearing maximum capacity.
- Rising search/indexing rejections.
- p95/p99 query latency breaching SLAs.
- Storage growing faster than forecast.
- Ingestion pipeline errors or rising backlogs.
- `KMSKeyInaccessibleException` or spikes in HTTP 403 responses.

Request logs should include correlation IDs, index names, query classes, and latency; avoid logging full documents or personal data unnecessarily. For vector search/RAG, monitor retrieval quality and retrieved chunk counts, not just API latency.

## 17. Backups, Migrations, and Limitations to Check

OpenSearch Serverless provides automated snapshots, but does not offer user-triggered manual snapshots like provisioned domains. Never assume you can take a manual snapshot before every change. Design backup/recovery around automated snapshot capabilities, retention, export/reindex options, and upstream sources of truth in S3 or operational systems.

Key limitations:

- Not every OpenSearch API operation or plugin is supported.
- Custom OpenSearch plugins are unsupported.
- Collections do not support direct cross-account resource policies. Users in external accounts can assume an IAM role in the collection-owning account; that role must be declared in the data access policy with corresponding IAM permissions.
- Cross-Region search and replication are not supported as native collection features.
- Shard counts, shard intervals, and refresh intervals are not user-configurable like provisioned domains.
- Refresh intervals are roughly 10 seconds for Search/Time series, ~5 seconds for NextGen vector, and ~60 seconds for Classic vector depending on generation.
- Collections have per-collection index limits and other quotas; check Service Quotas in your target Region.
- Migrating from a managed domain to Serverless requires reindexing data; there is no in-place conversion.
- Collection type cannot change after creation.

Before adopting Serverless, inventory required APIs, plugins, analyzers, ingest processors, snapshot needs, cross-account, and cross-Region requirements. Verify supported operations by collection type and generation. If any mandatory requirement is unsupported, pick a provisioned domain or a complementary architecture.

## 18. Costs and Workload Selection

Main Serverless cost components:

- OCU-hours for indexing compute.
- OCU-hours for search compute.
- Managed storage billed by stored volume.
- Supporting services such as OpenSearch Ingestion, Firehose, customer managed KMS keys, CloudWatch logs/metrics, and data transfer where applicable.

NextGen collection groups let multiple collections of the same type pool OCUs. Min OCU of 0 lowers compute charges during idle periods, though storage and upstream ingestion services still incur costs. Classic uses a different capacity model; never apply Classic minimums or pricing examples to NextGen.

Workload assessment guide:

| Workload | Typical Fit | Reason |
|---|---|---|
| Website product search with variable traffic | Search collection | Full-text, filters, sorting, and auto-scaling |
| Application/CloudTrail logs with multi-stage retention | NextGen Time series | Hot/warm tiers and time-range querying |
| RAG knowledge base or semantic search | Vector search collection | k-NN and metadata filtering |
| Steady search cluster needing shard/plugin control | Provisioned domain | Granular sizing and tuning |
| Search needing custom plugins or unsupported APIs | Provisioned domain | Serverless supports an API/plugin subset |
| Bursty batch ingest and intermittent queries | NextGen Serverless, evaluate scale-to-zero | Cuts compute during idle windows |

To estimate cost, gather at least one full cycle of real workload metrics: daily ingest bytes, document sizes, queries/second, concurrency, p95/p99 latency, vector dimensions, retention, and idle hours. Run a small benchmark to measure peak/average OCUs and storage growth, then model with the AWS Pricing Calculator or Regional pricing pages.

## 19. Architecture Example: Product Search and RAG

An enterprise has two needs: website product search and internal document Q&A.

~~~mermaid
flowchart TD
    subgraph ProductSearch
        A[Product catalog DB] --> B[CDC or application event]
        B --> C[Ingestion pipeline]
        C --> D[Search collection]
        U[Web application] --> D
        D --> R[Product results]
    end
    subgraph KnowledgeRAG
        S3[(S3 documents)] --> E[Chunk and embedding pipeline]
        E --> V[Vector search collection]
        Q[User question] --> M[Query embedding]
        M --> V
        V --> K[Top-k chunks and metadata filters]
        K --> L[Amazon Bedrock model]
        L --> O[Answer with sources]
    end
~~~

Product search uses a Search collection for full-text matching, category filters, price sorting, and document updates by product ID. RAG uses a Vector search collection for embedding similarity and metadata filtering by tenant/document permissions.

The two collections belong in separate collection groups because their collection types differ. If multiple product-search collections exist across environments or tenants, grouping same-type collections pools capacity while retaining per-collection encryption and access policies.

## 20. Workload Selection and Production Deployment Checklist

Before creating a collection, answer:

1. Is the workload document search, time-series logs, or embedding vectors?
2. Does it need full-text, aggregations, k-NN, geospatial, or hybrid retrieval?
3. Does the collection type support all required APIs and operations?
4. Should you choose NextGen, or keep Classic for compatibility?
5. Do ingest and query traffic fluctuate?
6. Can the workload tolerate scale-to-zero, or does it need minimum OCUs for latency?
7. Can multiple same-type collections share capacity via a collection group?
8. Does the data require customer managed KMS keys, private endpoints, or SAML?
9. Are ingest and query roles separated under least privilege?
10. Will producers use OpenSearch Ingestion, Firehose, Fluent Bit, Lambda, or direct clients?
11. Are retries, dead-letter queues, and idempotent indexing designed?
12. Are mappings and index templates under version control?
13. Have you load-tested ingest bursts, query concurrency, and vector recall?
14. Are dashboards/alarms configured for OCUs, latency, rejections, storage, and pipeline health?
15. Do backup, reindexing, and migration runbooks exist?
16. Are Regional support, API/plugin support, and Service Quotas verified?

A production rollout should separate sandbox, staging, and production collections. Manage collections, collection groups, encryption/network/data access policies, and ingestion pipelines via Infrastructure as Code. Test policy changes in staging first—wildcard policies can affect multiple collections simultaneously.

## Conclusion

Amazon OpenSearch Serverless provides managed collections with decoupled indexing and search compute, automatic workload scaling, and managed storage. Three collection types serve distinct needs: Search for full-text, Time series for timestamped logs/metrics, and Vector search for semantic retrieval. Because collection type cannot change after creation, choose carefully around data, query, and API requirements.

NextGen collection groups let multiple same-type collections share OCUs, configure min/max capacity, and scale to zero when suitable. Classic remains with its own capacity model and features. Serverless reduces cluster operations yet still demands deliberate mapping, ingestion, capacity, security, observability, and cost guardrails.

Choose Serverless when minimizing infrastructure operations and workloads match supported collection types and APIs. Choose provisioned domains when deep cluster control, custom plugins/APIs, or operational constraints exceed Serverless support. Ground the final choice in real benchmarks, verified service limits, and end-to-end pipeline costs.

## References

- [Amazon OpenSearch Serverless overview](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless.html)
- [What is Amazon OpenSearch Serverless?](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-overview.html)
- [Choosing a collection type](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-overview.html)
- [Creating collections: NextGen and Classic](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-create.html)
- [Amazon OpenSearch Serverless collection groups](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-collection-groups.html)
- [Managing capacity limits](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-scaling.html)
- [Collection group capacity limits](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/collection-groups-capacity-limits.html)
- [Working with vector search collections](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-vector-search.html)
- [Using warm-after in time series collections](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-warm-after.html)
- [Security overview for OpenSearch Serverless](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-security.html)
- [Encryption in OpenSearch Serverless](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-encryption.html)
- [Network access for OpenSearch Serverless](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-network.html)
- [Data access control for OpenSearch Serverless](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-data-access.html)
- [Ingesting data into OpenSearch Serverless collections](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-clients.html)
- [Overview of Amazon OpenSearch Ingestion](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/ingestion.html)
- [Comparing provisioned and Serverless OpenSearch](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-comparison.html)
- [OpenSearch Serverless quotas and endpoints](https://docs.aws.amazon.com/general/latest/gr/opensearch-service.html)
- [Amazon OpenSearch Service pricing](https://aws.amazon.com/opensearch-service/pricing/)
