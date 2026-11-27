# Ingest Pipelines and Application Responsibility Boundaries

An ingest pipeline is a chain of processors executed on Elasticsearch as documents enter an index. Pipelines can normalize strings, convert data types, parse dates, split fields, drop extraneous fields, enrich metadata, or apply transformations before Elasticsearch indexes a document.

Pipelines let multiple write paths share consistent data processing rules. However, they do not replace application logic. Request validation, authorization, business rules, calling external services, transaction management, retry orchestration, and returning user-facing error responses still belong in the application layer.

In Spring Data Elasticsearch, applications can pass documents through a pipeline during indexing or bulk indexing using the version's supported APIs. Defining and managing pipelines sits on the Elasticsearch side. This lesson explains the pipeline lifecycle, common processors, attaching pipelines to write operations, error handling, and responsibility boundaries between the cluster and the application.

## 1. What Is an Ingest Pipeline?

An ingest pipeline is a sequence of processors executed by Elasticsearch before a document is indexed. Each processor receives the current document, can read or modify fields, and passes the result to the next processor.

For example, suppose a system receives products from multiple sources. Incoming data may have unnormalized names, string-encoded prices, and timestamps formatted by source systems. A pipeline can:

- Trim whitespace from names.
- Normalize letter casing.
- Convert prices from strings to numbers.
- Parse dates into a standard date field.
- Drop raw fields used only during ingestion.
- Add an ingestion timestamp.
- Flag processing errors if a processor fails and `on_failure` is configured.

Conceptual processing flow:

~~~text
Application / Bulk Importer
        |
        v
Index API or Bulk API
        |
        v
Select ingest pipeline
        |
        v
Processor 1
        |
        v
Processor 2
        |
        v
Processor N
        |
        v
Mapping and indexing
        |
        v
Document becomes searchable
~~~

Pipelines transform documents at write time. They do not run during search queries, do not automatically alter already-indexed documents, and do not replace query-time transformations.

## 2. Pipelines and Processors

A pipeline has an ID, an optional description, and a list of processors. Each processor performs one transformation step.

| Processor | Purpose |
|---|---|
| `set` | Assigns a value to a field |
| `remove` | Removes a field |
| `rename` | Renames a field |
| `append` | Appends values to a list field |
| `lowercase` / `uppercase` | Normalizes string casing |
| `trim` | Strips leading and trailing whitespace |
| `convert` | Converts data types |
| `date` | Parses date strings into date values |
| `date_index_name` | Derives index names from dates |
| `grok` | Parses strings using patterns |
| `dissect` | Splits strings using delimiters and structure |
| `split` | Splits a string into a list |
| `join` | Joins a list into a string |
| `script` | Transforms using Painless scripts |
| `geoip` | Enriches geographic info from IP addresses |
| `user_agent` | Parses User-Agent strings |
| `enrich` | Looks up reference data from a prepared enrich policy |

Specific processors depend on Elasticsearch version, plugins, and cluster configuration. Before relying on a specialized processor, verify documentation for your exact version and ingest node deployment.

### 2.1. Processor Order Matters

Processors execute in declared order. Later processors see mutations made by earlier ones.

Example:

1. `trim` the `name` field.
2. `lowercase` the `name` field.
3. `rename` `name` to `normalizedName`.

If `rename` ran before `trim`/`lowercase`, later processors would need to reference the new field name. Wrong ordering can cause missing-field errors or incorrect data.

Prefer built-in specialized processors for standard operations. Avoid splitting trivial changes across redundant processors, yet also avoid cramming complex logic into massive scripts that are hard to read and debug.

### 2.2. Ingest Context

Processors operate on the ingest document and ingest context metadata. Useful system values include:

- `_index`: target index.
- `_id`: document ID.
- `_routing`: routing value if set.
- `_ingest.timestamp`: ingestion timestamp.
- `_ingest.pipeline`: current pipeline in supported contexts.
- `_ingest.on_failure_message` and related error metadata during failure handling.

Do not confuse the ingest context with Java objects inside your application. Processors transform the document on the Elasticsearch side after the request is sent; original Java objects are not updated back in memory.

## 3. Creating and Managing Pipelines

Use the Ingest Pipeline API to create or replace a pipeline definition:

~~~http
PUT _ingest/pipeline/product-normalize-v1
{
  "description": "Normalize product documents before indexing",
  "processors": [
    {
      "trim": {
        "field": "name",
        "ignore_missing": true
      }
    },
    {
      "lowercase": {
        "field": "name",
        "ignore_missing": true
      }
    },
    {
      "convert": {
        "field": "price",
        "type": "long",
        "ignore_missing": true
      }
    },
    {
      "date": {
        "field": "createdAtRaw",
        "target_field": "createdAt",
        "formats": [
          "ISO8601",
          "yyyy-MM-dd HH:mm:ss"
        ],
        "timezone": "Asia/Ho_Chi_Minh"
      }
    },
    {
      "set": {
        "field": "ingestedAt",
        "value": "{{_ingest.timestamp}}",
        "override": false
      }
    },
    {
      "remove": {
        "field": "createdAtRaw",
        "ignore_missing": true
      }
    }
  ]
}
~~~

This pipeline assumes incoming documents supply `name`, `price`, and `createdAtRaw` in matching formats. If `createdAtRaw` fails to parse, the `date` processor can fail the index operation unless error handling is configured.

Fetching a pipeline:

~~~http
GET _ingest/pipeline/product-normalize-v1
~~~

Deleting a pipeline:

~~~http
DELETE _ingest/pipeline/product-normalize-v1
~~~

Managing pipelines requires appropriate Elasticsearch privileges. In production, permissions to create/modify pipelines should be restricted to operations teams or deployment identities; arbitrary end-user requests should never modify cluster pipelines.

### 3.1. Naming and Versioning Pipelines

Choose IDs reflecting purpose and version, such as:

- `product-normalize-v1`
- `product-normalize-v2`
- `order-ingest-v1`
- `customer-enrichment-v3`

Pipelines are referenced by index settings or write requests. When changing logic, track which producers use which pipeline.

A safe deployment practice is creating a new pipeline version, simulating and testing it, then switching index settings or applications to the new ID. Keep the old pipeline during the transition if producers still reference it. Never edit a widely shared pipeline in place without assessing impact on active ingestion streams.

## 4. Normalizing Data with Processors

### 4.1. `set`, `remove`, and `rename`

Example assigning a default source, dropping an internal field, and renaming a field:

~~~json
{
  "processors": [
    {
      "set": {
        "field": "sourceSystem",
        "value": "legacy-import",
        "override": false
      }
    },
    {
      "rename": {
        "field": "productTitle",
        "target_field": "name",
        "ignore_missing": true
      }
    },
    {
      "remove": {
        "field": "temporaryImportNote",
        "ignore_missing": true
      }
    }
  ]
}
~~~

- `set` with `override: false` writes the value only when the field is absent per processor semantics.
- `rename` moves a field to a new name; verify behavior if the target already exists.
- `remove` strips the field from the ingest document before indexing.

Use `ignore_missing` when a field may legitimately be absent and that absence is not an error. Do not enable `ignore_missing` habitually on every processor; silently skipping missing required fields can hide corrupt source data.

### 4.2. `convert`

`convert` changes field types:

~~~json
{
  "convert": {
    "field": "price",
    "type": "long",
    "ignore_missing": true
  }
}
~~~

For example, an input `price` string `"259900"` becomes a `long`. The target mapping still needs to match the converted type.

`convert` cannot turn arbitrary strings into valid numbers. Values like `"unknown"` or strings with unexpected characters will fail. If business rules require strict validation, validate in the application before sending or configure explicit pipeline error handling.

### 4.3. `date` Processor

The `date` processor parses strings into date fields:

~~~json
{
  "date": {
    "field": "createdAtRaw",
    "target_field": "createdAt",
    "formats": ["ISO8601", "yyyy-MM-dd HH:mm:ss"],
    "timezone": "Asia/Ho_Chi_Minh"
  }
}
~~~

Align timezones and source formats carefully. If a string already carries an offset, do not shift hours manually in the application and then apply a timezone offset a second time.

Store timestamps as uniform instants and convert to local timezones only for display or business boundary calculations.

### 4.4. `grok` and `dissect`

`grok` parses strings using regex-based patterns:

~~~json
{
  "grok": {
    "field": "message",
    "patterns": [
      "%{IP:clientIp} %{WORD:method} %{URIPATHPARAM:path} %{NUMBER:status:int}"
    ]
  }
}
~~~

`dissect` splits strings using known delimiters and structure, usually lighter on CPU than `grok` when formats are stable:

~~~json
{
  "dissect": {
    "field": "message",
    "pattern": "%{timestamp} %{level} %{service}: %{message}"
  }
}
~~~

Choose `grok` when flexible pattern matching is needed; choose `dissect` when structure and delimiters are fixed. Complex patterns increase CPU usage and error risk when input logs shift.

## 5. `script` Processor

The `script` processor runs Painless scripts for conditional mutations or logic lacking a dedicated processor.

Example creating `displayName` when `name` is present:

~~~json
{
  "script": {
    "lang": "painless",
    "source": "if (ctx.name != null) { ctx.displayName = ctx.name.trim(); }"
  }
}
~~~

Example removing a field only when blank:

~~~json
{
  "script": {
    "lang": "painless",
    "source": "if (ctx.description != null && ctx.description.toString().trim().length() == 0) { ctx.remove('description'); }"
  }
}
~~~

Large scripts make pipelines harder to read and reuse. Prefer dedicated processors for standard operations. When scripting:

- Pass dynamic values via `params` when supported by the processor.
- Never interpolate user input directly into script source.
- Guard against null or missing fields.
- Keep scripts short, deterministic, and tested.
- Measure cost when running across large document volumes.

The script processor is not a place to make arbitrary HTTP calls or coordinate transactions with external systems.

## 6. `enrich` Processor and Enrichment

The `enrich` processor looks up data from a previously created and executed enrich policy—for example, appending partner or region classifications from an indexed internal reference dataset.

General workflow:

1. Create an enrich policy specifying match type and source fields.
2. Execute the policy to build the enrich index.
3. Add an `enrich` processor to the ingest pipeline.
4. During document ingestion, the processor looks up matching values and attaches target fields.

Conceptual processor example:

~~~json
{
  "enrich": {
    "policy_name": "partner-by-code",
    "field": "partnerCode",
    "target_field": "partnerInfo",
    "max_matches": 1
  }
}
~~~

The `enrich` processor is not an HTTP client calling partner systems per document. It looks up pre-built reference data inside Elasticsearch. Whenever reference data changes, re-execute the policy via an update workflow.

Use `enrich` for reference data suited to ingest-time lookup. If you need real-time external API calls, credential handling, fallbacks, or business error handling, perform enrichment in the application before sending the document.

## 7. Handling Errors with `on_failure`

A processor can fail due to missing fields, wrong data types, unparseable dates, or script exceptions. By default, a processor error fails the document's index operation.

You can configure `on_failure` at the processor level or pipeline level to execute actions on failure.

Example pipeline marking failures:

~~~http
PUT _ingest/pipeline/product-normalize-with-error-v1
{
  "processors": [
    {
      "convert": {
        "field": "price",
        "type": "long"
      }
    },
    {
      "date": {
        "field": "createdAtRaw",
        "target_field": "createdAt",
        "formats": ["ISO8601"]
      }
    }
  ],
  "on_failure": [
    {
      "set": {
        "field": "ingestError.message",
        "value": "{{_ingest.on_failure_message}}"
      }
    },
    {
      "set": {
        "field": "ingestError.processor",
        "value": "{{_ingest.on_failure_processor_type}}"
      }
    }
  ]
}
~~~

When pipeline-level `on_failure` is configured, its failure processors run. If the error is handled there, the document can continue and still be indexed. This is useful when storing flagged documents for investigation, yet risky if invalid documents leak into business search indices.

### 7.1. Error Handling Is Not a Dead-Letter Queue

An ingest pipeline does not automatically forward failed documents to Kafka, SQS, or an external queue. `on_failure` only governs processing inside the pipeline.

If invalid data should be rejected, let the failure fail the index item so the application captures the error. If failed data must be saved for later processing, build a dedicated quarantine/dead-letter flow in the application or ingestion infrastructure.

Never just stamp an `ingestError` field and assume every consumer filters out broken documents. Business queries must explicitly account for that field and exclude invalid documents.

### 7.2. Processor-Level `on_failure`

You can attach `on_failure` directly to an individual processor:

~~~json
{
  "convert": {
    "field": "price",
    "type": "long",
    "on_failure": [
      {
        "set": {
          "field": "ingestError.price",
          "value": "{{_ingest.on_failure_message}}"
        }
      },
      {
        "remove": {
          "field": "price",
          "ignore_missing": true
        }
      }
    ]
  }
}
~~~

This illustrates localized error handling on a specific processor. Decide explicitly whether the document should still be indexed after the error or be rejected. Never swallow mandatory field failures without emitting signals for operations and the application.

### 7.3. Error Metadata

Inside `on_failure`, Elasticsearch exposes metadata such as the error message, processor type, tag, and pipeline in the ingest context. You can record those values into fields for diagnostics.

Avoid storing stack traces or unnecessary sensitive data inside business documents. Error messages may expose raw inputs or internal details; restrict access and retention if indexed.

## 8. Tagging Processors and Observing Pipelines

Processors can carry a `tag`:

~~~json
{
  "convert": {
    "tag": "normalize-price",
    "field": "price",
    "type": "long"
  }
}
~~~

Tags identify specific processors during debugging and error analysis. Pipeline descriptions should note purpose, owner, and version.

Ingest observability should cover:

- Document submission counts.
- Per-item success/failure rates.
- Pipeline errors broken down by processor/tag.
- Bulk request latency and ingest throughput.
- Quarantined or error-flagged document counts.
- Mapping changes or missing-field rates.
- CPU and ingest node impact.

A bulk request can succeed at the HTTP level while individual items fail. Always check `errors` and per-item results. Never infer full batch indexing success from HTTP 200 alone.

## 9. Simulating Pipelines Before Use

The Simulate API runs a pipeline against sample documents without writing anything to an index.

~~~http
POST _ingest/pipeline/product-normalize-v1/_simulate
{
  "docs": [
    {
      "_source": {
        "name": "  WIRELESS MOUSE  ",
        "price": "259900",
        "createdAtRaw": "2026-11-13T08:00:00Z"
      }
    }
  ]
}
~~~

The response shows the transformed `_source`. Enable `verbose` to inspect intermediate states after every processor:

~~~http
POST _ingest/pipeline/product-normalize-v1/_simulate?verbose=true
{
  "docs": [
    {
      "_source": {
        "name": "  WIRELESS MOUSE  ",
        "price": "259900",
        "createdAtRaw": "2026-11-13T08:00:00Z"
      }
    }
  ]
}
~~~

Simulate is great for verifying:

- Missing input fields.
- Strings with extra whitespace.
- Invalid data types.
- Varying date formats.
- `rename`/`remove` outcomes.
- `on_failure` behavior.
- Documents with nested objects or arrays.

Simulate does not verify full mapping compatibility, authorization, bulk retries, or application logic. After simulation, run integration tests that index documents into a test index and read them back.

## 10. How Is a Pipeline Selected?

Pipelines can be chosen explicitly per request or configured on the index.

### 10.1. Specifying a Pipeline in the Index API

~~~http
PUT /products/_doc/P-1001?pipeline=product-normalize-v1
{
  "name": "  WIRELESS MOUSE  ",
  "price": "259900",
  "createdAtRaw": "2026-11-13T08:00:00Z"
}
~~~

The specified request pipeline applies to that index operation.

### 10.2. Default Pipeline

An index can configure a default pipeline:

~~~http
PUT /products-v1
{
  "settings": {
    "index.default_pipeline": "product-normalize-v1"
  },
  "mappings": {
    "properties": {
      "name": { "type": "text" },
      "price": { "type": "long" },
      "createdAt": { "type": "date" },
      "ingestedAt": { "type": "date" }
    }
  }
}
~~~

When an index request does not specify a pipeline, Elasticsearch runs the index's default pipeline. Requests can override it with another pipeline or pass the special value `_none` to skip the default pipeline per Elasticsearch semantics.

Default pipelines work well when all producers writing to an index share the same normalization step. However, they introduce an index-level dependency: producers may not realize which pipeline transforms their documents. Document the pipeline contract and test across all producers.

### 10.3. Final Pipeline

An index can configure a final pipeline. The final pipeline runs after the request-selected or default pipeline as the final ingest stage.

~~~http
PUT /products-v1
{
  "settings": {
    "index.default_pipeline": "product-normalize-v1",
    "index.final_pipeline": "product-audit-v1"
  }
}
~~~

Final pipelines typically enforce mandatory index-level transformations that producers cannot bypass. Requests cannot disable a final pipeline by passing `_none` for the default pipeline.

| Setting | Role |
|---|---|
| Request pipeline | Pipeline specified for a single write operation |
| `index.default_pipeline` | Default pipeline when a request specifies none |
| `index.final_pipeline` | Final pipeline enforced per index configuration |

Exact behavior and dynamic setting updates depend on the Elasticsearch version. Before deploying, verify execution order and pipeline replacement semantics on your cluster version.

### 10.4. Specifying a Pipeline in the Bulk API

The Bulk API can specify a pipeline for eligible `index`/`create` operations in a request:

~~~http
POST /_bulk?pipeline=product-normalize-v1
{"index":{"_index":"products","_id":"P-1001"}}
{"name":"  WIRELESS MOUSE  ","price":"259900","createdAtRaw":"2026-11-13T08:00:00Z"}
{"index":{"_index":"products","_id":"P-1002"}}
{"name":"  ERGONOMIC KEYBOARD  ","price":"799900","createdAtRaw":"2026-11-13T09:00:00Z"}
~~~

A request-level pipeline applies to eligible `index`/`create` actions in that bulk request. If different document groups need different pipelines, split them into separate bulk requests or check per-item capabilities supported by your version and verify item semantics.

Do not assume pipelines apply identically to every bulk action type. In particular, `update` actions in bulk have different semantics than `index`/`create`; verify the API before designing update pipelines.

## 11. Bulk Imports and Handling Item Failures

In large ingestion flows, pipelines commonly normalize documents during bulk indexing.

Example bulk response:

~~~json
{
  "errors": true,
  "items": [
    {
      "index": {
        "_index": "products",
        "_id": "P-1001",
        "status": 201,
        "result": "created"
      }
    },
    {
      "index": {
        "_index": "products",
        "_id": "P-1002",
        "status": 400,
        "error": {
          "type": "document_parsing_exception",
          "reason": "failed to parse field"
        }
      }
    }
  ]
}
~~~

Some items succeed while others fail. The ingestion application must:

1. Check `errors`.
2. Iterate every item result.
3. Correlate failed items with source records or business keys.
4. Record the failure reason.
5. Perform controlled retries if the error is recoverable.
6. Route unprocessable records to quarantine/dead-letter per policy.

Never blindly retry the entire batch. Fixed-ID `index` operations are easier to retry safely, whereas incrementing scripts, append operations, or external side effects are unsafe to replay blindly.

### 11.1. Choosing Batch Size

Batches that are too small raise request overhead. Batches that are too large increase memory usage, latency, and pressure on ingest nodes.

No fixed batch number suits every cluster. Measure:

- Average document size.
- Documents per request.
- Processor execution duration.
- Bulk item failure rate.
- Ingest thread pool queues/rejections.
- CPU, heap, and network.
- Response size.

Tune batch size and concurrency based on metrics. When CPU-heavy processors like `grok`, `script`, or `enrich` are active, adding more write workers can overload ingest nodes rather than boosting throughput.

### 11.2. Retries and Idempotency

Ensure retry actions are safe to repeat:

- Writing full snapshots with stable IDs is usually easier to retry.
- Resending partial updates setting fixed values can be idempotent for those fields.
- Incrementing scripts or array-append operations can yield different results if run twice.
- Calling external APIs inside the application can repeat side effects without idempotency keys.

Pipelines should favor deterministic transformations: the same input and pipeline version produce the same output. That makes retries and reindexing predictable.

## 12. Attaching Pipelines with Spring Data Elasticsearch

Spring Data Elasticsearch provides abstractions to index documents. Pipeline support on query/operation types depends on the version. Some APIs allow setting a pipeline on `IndexQuery`; when using the Elasticsearch Java API Client directly, requests can specify pipelines explicitly.

Common `IndexQuery` pattern in Spring Data Elasticsearch 5.x:

~~~java
import org.springframework.data.elasticsearch.core.query.IndexQuery;
import org.springframework.data.elasticsearch.core.query.IndexQueryBuilder;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

IndexQuery indexQuery = new IndexQueryBuilder()
    .withId(product.getId())
    .withObject(product)
    .withPipeline("product-normalize-v1")
    .build();

String id = operations.index(
    indexQuery,
    IndexCoordinates.of("products")
);
~~~

Packages, builder methods, and `withPipeline` support can vary across minor versions. Check `IndexQueryBuilder`/`IndexQuery` in your project's dependency. If your version does not expose pipelines on the abstraction, use the configured Elasticsearch Java API Client or REST client.

### 12.1. Elasticsearch Java API Client: Indexing a Single Document

Direct request example:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;

client.index(request -> request
    .index("products")
    .id(product.getId())
    .pipeline("product-normalize-v1")
    .document(product)
);
~~~

This makes the pipeline attached to the index request explicit. Configure the client with proper endpoints, credentials, TLS, and application lifecycle management.

### 12.2. Elasticsearch Java API Client: Bulk Indexing

~~~java
client.bulk(request -> request
    .index("products")
    .pipeline("product-normalize-v1")
    .operations(operation -> operation
        .index(index -> index
            .id(firstProduct.getId())
            .document(firstProduct)
        )
    )
    .operations(operation -> operation
        .index(index -> index
            .id(secondProduct.getId())
            .document(secondProduct)
        )
    )
);
~~~

This illustrates a request-level pipeline for bulk indexing. Builders can differ across client versions and list construction patterns; check `BulkRequest.Builder` in your actual dependency. Afterward, always check item-level responses rather than assuming success because the call returned normally.

### 12.3. Repository `save` Does Not Automatically Know Which Pipeline to Use

A standard `repository.save(entity)` call does not carry an application-chosen pipeline ID. If the index defines a default/final pipeline, the cluster applies it per settings. If different import flows require specific pipelines, use index/query APIs supporting pipelines or the Java API Client directly.

Do not rely on an implicit default pipeline when multiple producers have differing requirements without an explicit contract.

## 13. Pipelines and Mappings: Two Distinct Layers

A pipeline transforms `_source` before indexing. Mapping defines how fields are stored and indexed.

For instance, a pipeline converting `price` to `long` does not automatically make the mapping of `price` a `long`. If the existing mapping is `keyword`, numeric values can still be indexed as `keyword` or cause unexpected outcomes.

| Component | Responsibility |
|---|---|
| Ingest pipeline | Normalizes/transforms documents before indexing |
| Mapping | Defines field types, analyzers, doc values, and indexing behavior |
| Analyzer | Tokenizes and normalizes text for search |
| Query | Filters and ranks documents at search time |
| Application mapper | Maps API/domain models to Elasticsearch documents |

Pipelines do not replace mapping migrations. Changing an existing field's type generally requires creating a new index with the updated mapping and reindexing data.

### 13.1. Pipelines Can Create New Fields

`set` or `script` processors can add new fields. If dynamic mapping is enabled, Elasticsearch automatically generates mappings for those new fields. While convenient in prototyping, it can cause mapping explosions or unintended field types.

For production schemas, explicitly define mappings for important fields and restrict dynamic mapping appropriately. Version, deploy, and test pipelines and mappings together.

## 14. Reindexing Data Through a Pipeline

Pipelines can transform existing data during a Reindex API run by specifying `pipeline` on the destination.

Example migrating from `products-v1` to `products-v2` while normalizing through a new pipeline:

~~~http
POST _reindex
{
  "source": {
    "index": "products-v1"
  },
  "dest": {
    "index": "products-v2",
    "pipeline": "product-normalize-v2"
  }
}
~~~

This is useful when applying new ingest logic to historical data. Reindex does not modify the source index; it reads `_source` and writes documents into the destination index through the specified pipeline.

Before running on large datasets:

- Create the destination index with proper mappings and settings.
- Simulate the pipeline on representative documents.
- Test reindexing on a small subset or staging index.
- Monitor tasks, failures, and throughput.
- Verify document counts and transformed data.
- Prepare alias/read-write cutover and rollback plans.

Large reindex jobs consume substantial cluster resources. Avoid running multiple heavy tasks simultaneously without evaluating cluster load.

## 15. Responsibility Boundaries Between Ingest Pipelines and the Application

Pipelines belong to the storage/search infrastructure. The application is where requests, users, and business rules are understood. Clear boundaries prevent pushing unsuitable logic into the cluster.

| Task | Typical Right Place | Rationale |
|---|---|---|
| Trim, lowercase, rename fields | Ingest pipeline or application mapper | Mechanical, shared data transformations |
| Parse dates from source formats | Pipeline or application | Pipelines fit simple shared rules across producers |
| Type conversion | Pipeline after schema confirmation | Requires matching target mapping |
| Validate request bodies | Application | Must return errors aligned with the API contract |
| Authentication and authorization | Application/security layer | Pipelines do not replace access controls |
| Tenant isolation | Application and query/index design | Never trust arbitrary client-supplied tenant fields |
| Check business invariants | Application/domain service | Requires understanding domain state and rules |
| Call payment, CRM, or partner APIs | Application/integration service | Requires timeouts, credentials, retries, and side-effect handling |
| Enrich from indexed reference data | Enrich processor or application | Choose based on freshness and semantics |
| Record business audit events | Application/event architecture | Needs actor identity, correlation, and retention policy |
| Shared document normalization across producers | Ingest pipeline | Centralized rule on the Elasticsearch side |
| Query-time ranking and filtering | Queries | Outside ingest pipeline scope |
| Cross-system transactions | Application/service architecture | Pipelines are not distributed transaction coordinators |

### 15.1. Things That Should Not Be Pushed Into a Pipeline

Do not use ingest pipelines to:

- Authenticate users or make authorization decisions.
- Trust client-supplied `tenantId`, `ownerId`, or `role` fields blindly.
- Orchestrate multi-step checkout, order, or state-transition workflows.
- Call external APIs per document as a mandatory transaction step.
- Send emails, webhooks, or trigger non-idempotent side effects.
- Replace transactions or the outbox pattern.
- Format user-friendly business errors for HTTP clients.
- Orchestrate across multiple microservices.

Pipelines can transform a single document inside Elasticsearch, yet they provide no cross-system transactions and lack full business request context.

### 15.2. When Does Logic Belong in a Pipeline?

Pipelines fit transformations that are:

- Mechanical and deterministic.
- Dependent only on data already inside the document or an enrich index.
- Needed consistently across multiple producers.
- Independently testable via `_simulate`.
- Free of user permission checks or external side effects.
- Deployable and versionable as infrastructure configuration.

Examples include name normalization, timestamp parsing, stripping temporary import fields, or adding ingest metadata.

### 15.3. When Should Logic Stay in the Application?

The application should own logic that:

- Needs caller identity and permissions.
- Needs access to databases or other services.
- Varies with business state rules.
- Needs idempotency guarantees or retry orchestration.
- Must return specific 4xx/5xx HTTP errors.
- Requires transactions, outbox patterns, or audit trails.
- Protects sensitive data and tenant boundaries.

Applications can normalize certain fields before sending while the pipeline handles shared normalization. If the same transformation exists in both places, designate one as the single source of truth to prevent divergent outputs.

## 16. Validation Before and After the Pipeline

Applications should validate requests before sending documents:

- Required fields are present.
- Data types are valid.
- Values fall within business bounds.
- Callers are authorized to write the document.
- Tenant and document IDs are derived from trusted context.

Pipelines can enforce extra technical normalization when ingesting from multiple producers, yet must never serve as an authorization boundary.

After the pipeline runs, mappings can still reject documents if output types conflict. Integration tests should therefore verify both post-processor output and successful indexing under the target mapping.

If a pipeline transforms a field already validated by the application, check that the final output still satisfies invariants. For example, if the application ensures `price` is positive and the pipeline converts strings to `long`, verify the final converted value is not corrupted.

## 17. External Enrichment and Freshness

Three common enrichment patterns:

1. The application calls external services before indexing and sends the enriched document.
2. The ingest pipeline uses an `enrich` processor against a prepared enrich index.
3. Another process syncs reference data into Elasticsearch, and pipelines reference it.

Pick based on freshness and reliability needs:

- If data must reflect the real-time state of an external service, the application usually needs to call that service.
- If periodic reference synchronization is acceptable, the `enrich` processor reduces ingest-time coupling.
- Until the enrich index is refreshed via policy re-execution, the pipeline continues using older reference data.

Never assume the `enrich` processor queries an external business database or API live for every document written.

## 18. Security and Pipeline Management Permissions

Pipelines can alter data prior to indexing. Anyone permitted to modify a pipeline can impact every producer using it.

Operational best practices:

- Restrict permissions to create, update, and delete ingest pipelines.
- Separate document-write permissions from pipeline-management permissions where possible.
- Never allow public clients to pass arbitrary pipeline IDs.
- Never let end-user requests pick a pipeline capable of altering tenant/security fields.
- Control access to error fields or sensitive metadata.
- Review pipeline changes like production code/configuration.
- Maintain clear rollback procedures and versioned IDs.

When using a `final_pipeline` for mandatory transformations, verify permissions and deployment flows so producers cannot accidentally or intentionally bypass expected rules—while `default_pipeline` can be skipped, `final_pipeline` still executes.

## 19. Observability and Ingest Operations

Treat pipelines as production infrastructure components:

- Use clear IDs and descriptions.
- Version pipeline definitions.
- Store pipeline JSON in source control or configuration management.
- Simulate before deploying.
- Test with valid, invalid, and edge-case inputs.
- Monitor bulk item failures.
- Monitor ingest node CPU, queues, and rejections.
- Record pipeline IDs and versions in deployment logs.
- Clean up obsolete pipelines once no producers use them.

Elasticsearch provides ingest node statistics and pipeline statistics depending on version. Inspect node stats via:

~~~http
GET _nodes/stats/ingest
~~~

Metrics can include processor counts, failure counts, active counts, and execution times at the node/pipeline level per your version's response format. Combine these with bulk item errors and application logs to pinpoint bottlenecks or failing processors.

## 20. Testing Pipelines and Application Integration

Use multiple testing layers:

### 20.1. Simulate Tests

Use `_simulate` to verify processors on sample documents:

- Complete documents.
- Missing optional fields.
- Invalid data types.
- Malformed date formats.
- Nested objects or arrays.
- Inputs with whitespace, Unicode characters, and empty strings.
- Processor failure cases.

### 20.2. Integration Tests

Create a test index with production-like mappings, install the pipeline, and index documents through it. Then read documents back from Elasticsearch to verify `_source` and indexed behavior.

Verify:

- Fields are normalized properly.
- Raw fields are kept or removed as intended.
- Field types match the mapping.
- Dates parse to the exact instant/timezone.
- Processor errors trigger item failures or error markers per policy.
- Bulk responses are inspected at the item level.
- Request, default, and final pipelines apply in the expected order.

### 20.3. Application Contract Tests

Test the application layer to verify:

- Invalid requests are rejected before calling Elasticsearch.
- Tenant/owner fields are derived from trusted context.
- The right pipeline ID is selected per import flow.
- Retries do not repeat side effects.
- Bulk partial failures are reported per record.
- Pipeline errors translate into responses or dead-letter entries per contract.

Simulate tests alone do not prove the application attached the right pipeline to requests. Integration tests must verify the actual write path.

## 21. Common Pitfalls

| Symptom | Possible Cause | Fix |
|---|---|---|
| Pipeline did not run | Request specified no pipeline and index has no default | Check request pipeline parameter and index settings |
| Request pipeline behaved unexpectedly | Default/final pipelines have specific precedence | Inspect request, default, and final pipeline settings |
| Fields disappeared after ingest | `remove`/`rename` processor or script modified `_source` | Simulate step-by-step with verbose mode |
| `convert`/`date` processor failed bulk items | Input unparseable | Validate upfront and configure `on_failure` intentionally |
| Broken documents still got indexed | `on_failure` caught the error and let the pipeline finish | Flag/quarantine explicitly or let the item fail |
| Bulk HTTP request succeeded yet records missing | Individual items failed in the response | Inspect `errors` and every item |
| Historical data not normalized | Pipelines run only at ingest time | Reindex through the new pipeline |
| `enrich` returned stale data | Enrich policy was not re-executed | Update source index and re-execute the policy |
| Mapping exception after pipeline | Processor output mismatches mapping | Align pipeline output types with mapping |
| Ingest node CPU spiked | Expensive `script`/`grok`/`enrich` or high concurrency | Profile processors, tune batch size and load |
| Producers write inconsistent documents | Uncoordinated pipeline/default settings | Publish a contract and specify pipelines explicitly |
| Retries duplicated data | Non-idempotent append/increment logic | Design retry-safe operations |
| Pipeline edit broke all producers | Mutated a shared pipeline ID in place | Version pipelines and migrate under control |

## 22. Workflow for Designing Ingest Pipelines for Bulk Import

When implementing an ingestion flow:

1. Define input schemas and target index schemas.
2. Decide which fields the application must validate or enrich.
3. Pick mechanical transformations suitable for the pipeline.
4. Define mappings compatible with the final pipeline output.
5. Create a pipeline with an explicit ID and version.
6. Simulate with valid, malformed, and boundary samples.
7. Create a test index and run integration tests.
8. Attach the pipeline in the Index/Bulk API or configure intentional default/final settings.
9. Inspect every item in bulk responses.
10. Build retry/quarantine flows based on idempotency and error types.
11. Monitor ingest metrics and application logs.
12. Version pipelines when logic changes; reindex if historical data needs transforming.

Do not shove entire business workflows into a pipeline merely because pipelines can mutate `_source`. Keep decisions depending on users, permissions, business state, and external services inside the application.

## 23. Quick Reference Table

| Need | Approach |
|---|---|
| Normalize documents before indexing | Ingest pipeline |
| Ordered processor sequence | `processors` executed sequentially |
| Add/remove/rename fields | `set`, `remove`, `rename` |
| Normalize strings | `trim`, `lowercase`, `uppercase` |
| Convert types | `convert` |
| Parse timestamps | `date` processor |
| Split logs/messages | `grok` or `dissect` |
| Custom transformations | Painless `script` processor |
| Look up indexed reference data | `enrich` processor |
| Handle processor errors | `on_failure` and error metadata |
| Test before writing | `_simulate` |
| Apply to a single request | `pipeline` parameter |
| Index default pipeline | `index.default_pipeline` |
| Mandatory final step | `index.final_pipeline` |
| Apply to bulk indexing | Bulk API `pipeline` parameter |
| Normalize historical data | Reindex with `dest.pipeline` |
| Inspect per-record failures | Bulk response `items` and `errors` |
| Monitor ingest nodes | Nodes ingest stats |
| Authentication and authorization | Application/security layer |
| Business rules and external APIs | Application/domain/integration service |

Ingest pipelines fit mechanical, deterministic, shared document transformations at write time. Pipelines do not replace mappings, queries, authorization, or business workflows. In Spring Data Elasticsearch, attach pipelines explicitly to index/bulk operations using your version's supported APIs; inspect bulk responses at the item level, simulate before deploying, and version pipelines cleanly. The application remains responsible for request validation, authorization, business rules, external service calls, idempotency, retries, and error reporting.
