# Data Streams, Append-Only Data, and Compatibility Requirements

An Elasticsearch data stream is an abstraction for storing and searching data that is frequently appended, especially logs, metrics, events, and time-based data. The application sends documents to a stable data stream name; Elasticsearch automatically routes write operations to the current backing index. When the backing index meets rollover conditions, a new backing index is created and becomes the target for subsequent writes.

Data streams fit the **append-only** model: the system primarily adds new events, then searches or analyzes stored events. This model differs from a typical business index where the application frequently updates or deletes documents by ID.

To use data streams properly, you must understand three key requirements:

- Documents must include a `@timestamp` time field mapped as `date` or `date_nanos`.
- Documents written to a data stream must follow a creation model; write operations use create semantics rather than overwriting existing documents.
- Backing indices must have compatible mappings, typically prepared via an index template and managed throughout their lifecycle with rollover/retention policies.

## 1. What is a data stream?

A data stream is a logical name representing a sequence of backing indices. Applications read and write through the data stream name, while Elasticsearch manages the underlying physical indices.

For example, an application writes logs to the data stream logs-app-default. The data stream might consist of:

    logs-app-default
       |
       +-- .ds-logs-app-default-2026.10.01-000001
       |
       +-- .ds-logs-app-default-2026.11.01-000002
       |
       +-- .ds-logs-app-default-2026.12.01-000003
                  ^
                  |
             Current write index

Backing index names illustrate Elasticsearch's standard format. Backing indices are typically hidden indices managed by the data stream. Applications do not need to pick a backing index manually when writing.

A data stream provides a stable business name:

- Searching the data stream name queries data across the stream's backing indices.
- Indexing a document into the data stream name routes to the current write index.
- Upon rollover, the old write index becomes a read-only backing index under normal lifecycle rules; a new backing index is added to the stream.
- Backing index management is performed via data stream APIs, index templates, and lifecycle policies.

A data stream is not a single physical index. Nor is it simply a regular alias: it has its own document creation rules, backing indices, and rollover semantics.

## 2. Why are data streams suited for append-only data?

Many types of data are generated continuously over time:

- Application logs: each request or error creates a new event.
- Audit events: each user action creates a record.
- Metrics: the system records CPU, memory, and latency periodically.
- Device events: devices emit status or signals over time.
- Telemetry: services send observability data about the system.

Such data typically shares these characteristics:

1. Each record represents an event at a point in time.
2. New data is added continuously.
3. Queries commonly filter by time range.
4. Older data is rarely modified.
5. Data can be retained for a defined duration and then deleted per retention policy.

Data streams are designed to serve that model. When the application writes a new event, it only needs to know the data stream name. Elasticsearch decides the current write index and handles transitioning to the next backing index.

### What does append-only mean?

Append-only means data is augmented with new events rather than frequently modifying old records. For example, when an order's status changes, an event system can write a new OrderStatusChanged event instead of updating an earlier OrderCreated event.

This event model offers several benefits:

- Preserves change history.
- Supports time-based analysis.
- Reduces reliance on updating old documents.
- Easily partitions data into backing indices by lifecycle.
- Allows retention policies to be applied to older data.

If the business domain requires a current record that is updated continuously, such as a customer profile or current inventory level, a standard index or alias is usually more suitable than a data stream.

## 3. Requirements for the @timestamp field

Every document in a data stream must contain a @timestamp field. This field must be mapped as date or date_nanos.

Example log document:

    {
      "@timestamp": "2026-11-13T10:15:30Z",
      "service": "catalog-api",
      "level": "ERROR",
      "message": "Product lookup failed",
      "duration_ms": 125
    }

The @timestamp field represents when the event occurred. It is essential for:

- Sorting events chronologically.
- Filtering by time ranges.
- Analyzing trends and frequencies.
- Supporting routing, rollover, and lifecycle operations in applicable configurations.

The mapping must explicitly declare the date type:

    {
      "properties": {
        "@timestamp": {
          "type": "date"
        },
        "service": {
          "type": "keyword"
        },
        "level": {
          "type": "keyword"
        },
        "message": {
          "type": "text"
        },
        "duration_ms": {
          "type": "long"
        }
      }
    }

Do not rely on dynamic mapping to infer @timestamp from an arbitrary document in production. Declare explicit mappings to ensure all backing indices share the same data types.

### Event time vs. ingestion time

Applications should distinguish:

- Event time: when the event actually occurred.
- Ingestion time: when Elasticsearch receives or indexes the document.

If events arrive late, the two timestamps can differ. @timestamp usually represents event time for querying by business occurrence time. If you need to analyze ingest latency, you can store a separate field such as event.ingested.

Timestamp values should include an explicit timezone, typically ISO-8601 in UTC or with an offset. Avoid sending timestamps without timezone info if the system spans multiple deployment regions.

## 4. Creating a data stream using an index template

A data stream requires an index template with a data_stream section. The template defines the data stream name pattern, settings, mappings, and can compose component templates.

Example of creating a template for logs-app-*:

    PUT _index_template/logs_app_template
    {
      "index_patterns": [ "logs-app-*" ],
      "data_stream": {},
      "priority": 200,
      "template": {
        "settings": {
          "number_of_shards": 1
        },
        "mappings": {
          "properties": {
            "@timestamp": {
              "type": "date"
            },
            "service": {
              "type": "keyword"
            },
            "level": {
              "type": "keyword"
            },
            "message": {
              "type": "text"
            },
            "duration_ms": {
              "type": "long"
            }
          }
        }
      }
    }

A template containing data_stream indicates this pattern is used to create data streams. The @timestamp mapping is mandatory. Other fields are declared according to how the application writes and queries them.

Once the template is created, you can create the data stream:

    PUT _data_stream/logs-app-default

Elasticsearch creates the initial backing index from the template and registers the data stream under the name logs-app-default.

You can inspect its status:

    GET _data_stream/logs-app-default

The response provides data stream details and backing indices. When inspecting the actual mapping configuration, you can read the mapping of a backing index or use the appropriate data stream APIs.

### Role of the template

Index templates ensure every new backing index receives the same set of settings and mappings. Without controlled templates, backing indices created at different times could end up with inconsistent schemas, especially when applications introduce new fields.

For large systems, templates can be split into component templates:

- Component template for shared mappings.
- Component template for settings.
- Index template combining component templates and declaring data_stream.

This allows reusing configuration across multiple data streams while keeping schema versions controlled.

## 5. Writing documents to a data stream

The application sends documents to the data stream name without needing to know the current backing index name.

REST API example:

    POST logs-app-default/_doc?op_type=create
    {
      "@timestamp": "2026-11-13T10:15:30Z",
      "service": "catalog-api",
      "level": "INFO",
      "message": "Product search completed"
    }

Elasticsearch routes the document to the current write index. For data streams, write operations must have create semantics. In the Bulk API, the appropriate action is create:

    POST _bulk
    { "create": { "_index": "logs-app-default" } }
    { "@timestamp": "2026-11-13T10:15:30Z", "service": "catalog-api", "level": "INFO" }

The crucial point is that a data stream must not be used like a regular index to overwrite existing documents by the same ID. A document sent to a data stream represents a new event. If state corrections are needed, consider writing a corrective event or a new event describing the subsequent state.

### Rules regarding IDs

If the application generates IDs itself, ensure each event has an appropriate identifier. Resending an event with the same ID using create semantics may be rejected because the document already exists. This can help detect duplicates, though the application needs a strategy for handling retries and idempotency.

If no ID is supplied, Elasticsearch generates one automatically. This is convenient for append-only events, though retrying the same payload can create duplicate documents if the prior request succeeded without the client receiving the response.

Therefore, producer design must decide:

- Are deterministic IDs needed for deduplication?
- Should an event ID from the source system be stored?
- On timeout, how do we determine whether the request was already written?
- Are duplicate events acceptable and handled at the analytics layer?

## 6. Reading and searching data in a data stream

Data streams support searching across all backing indices via the stream name:

    GET logs-app-default/_search
    {
      "query": {
        "bool": {
          "filter": [
            {
              "range": {
                "@timestamp": {
                  "gte": "2026-11-13T00:00:00Z",
                  "lt": "2026-11-14T00:00:00Z"
                }
              }
            },
            {
              "term": {
                "service": "catalog-api"
              }
            }
          ]
        }
      },
      "sort": [
        {
          "@timestamp": "desc"
        }
      ]
    }

The query uses a range on @timestamp and filters by service. Elasticsearch searches across the backing indices belonging to the data stream without requiring the application to stitch individual indices together.

If you need to read across multiple data streams, you can use wildcards or data stream aliases as designed. Restrict patterns to avoid unintentionally querying excessive data.

### Field mappings must remain consistent

When searching across multiple backing indices, the same field should have compatible types. For example:

- service should be keyword across all backing indices.
- @timestamp should consistently be date or date_nanos per design.
- duration_ms should have a consistent numeric type.

If one backing index has service as text and another has it as keyword, queries, sorting, or aggregations across the whole stream can fail or return inconsistent results.

This is why index templates and component templates are vital: every new backing index must receive the same controlled schema.

## 7. Rollover and backing indices

Rollover is the process of switching a data stream's write index to a new backing index. The data stream keeps the same logical name, while new data is written into the new index.

Example:

    Before rollover:
      logs-app-default
        -> .ds-logs-app-default-...-000001 (write index)

    After rollover:
      logs-app-default
        -> .ds-logs-app-default-...-000001
        -> .ds-logs-app-default-...-000002 (write index)

Rollover can be triggered manually or by lifecycle policy conditions. Common conditions include:

- Backing index age.
- Data size.
- Document count.

Manual rollover example:

    POST logs-app-default/_rollover

Conditions can be added:

    POST logs-app-default/_rollover
    {
      "conditions": {
        "max_age": "1d",
        "max_primary_shard_size": "30gb"
      }
    }

The example illustrates age and shard size conditions. Actual values should be based on ingest rate, document size, shard count, and operational requirements.

After rollover:

- The data stream name remains unchanged.
- Old backing indices continue serving searches.
- The new backing index becomes the write index.
- The application keeps sending documents to the data stream name as before.

Applications should not write directly to backing index names. Doing so bypasses the routing and lifecycle guarantees provided by the data stream.

## 8. Lifecycle management and retention

Data streams are commonly paired with lifecycle policies to automate rollover and manage older data.

Elasticsearch provides lifecycle mechanisms such as Index Lifecycle Management (ILM) and Data Stream Lifecycle (DSL), depending on version and cluster type. They can manage:

- Rolling over when an index reaches age or size thresholds.
- Moving data across storage tiers if supported by the architecture.
- Retaining data for a defined period.
- Deleting expired backing indices.

A simple ILM policy example:

    PUT _ilm/policy/logs_app_policy
    {
      "policy": {
        "phases": {
          "hot": {
            "actions": {
              "rollover": {
                "max_age": "1d",
                "max_primary_shard_size": "30gb"
              }
            }
          },
          "delete": {
            "min_age": "30d",
            "actions": {
              "delete": {}
            }
          }
        }
      }
    }

For an ILM policy to apply to backing indices, the template must attach the appropriate lifecycle policy, for instance via the index.lifecycle.name setting. For data streams, do not configure rollover_alias as done for traditional write aliases; use the data stream rollover mechanism appropriate for your Elasticsearch version. If choosing Data Stream Lifecycle, configure the lifecycle according to the APIs and limits of that version.

Do not assume every cluster supports the exact same lifecycle API or that every feature is included under the same license. Check the version and deployment policy before choosing between ILM and Data Stream Lifecycle.

Retention policies directly affect data availability. Once a backing index expires and is deleted, documents inside it are no longer available. Retention duration must align with business, audit, and organizational data policies.

## 9. How do data streams and index aliases differ?

Both data streams and aliases provide a logical name so applications avoid tight coupling to a physical index. However, their semantics differ.

| Criterion | Data stream | Index alias |
|---|---|---|
| Primary goal | Append-only data, usually time-based | Logical name for one or more indices |
| Structure | Sequence of backing indices managed as a data stream | Alias pointing to one or more indices |
| Writing documents | Create semantics to the current write index | Depends on index/alias and submitted operation |
| Updating/deleting by ID | Not suited for standard update/delete workflows | Can be executed on target index if privileges and routing match |
| Rollover | Has dedicated data stream rollover semantics | Can use rollover API with configured alias |
| @timestamp | Mandatory | Optional |
| Use cases | Logs, metrics, events, telemetry | Versioned indices, read/write aliases, blue-green migrations |

If data consists of append-only events with a clear timestamp, a data stream is usually a natural fit. If data consists of business entities subject to updates/deletes by ID, an index alias is usually more flexible.

Do not choose a data stream merely to get a stable index name. Choose based on the data model and operations your application must perform.

## 10. Compatibility with Spring Data Elasticsearch

Spring Data Elasticsearch can map a Java entity to a data stream name in the same way it maps to an index, but Elasticsearch-side data stream rules must be respected.

Example log entity:

    @Document(
        indexName = "logs-app-default",
        createIndex = false
    )
    public class AppLog {

        @Id
        private String id;

        @Field(name = "@timestamp", type = FieldType.Date)
        private Instant timestamp;

        @Field(type = FieldType.Keyword)
        private String service;

        @Field(type = FieldType.Keyword)
        private String level;

        @Field(type = FieldType.Text)
        private String message;
    }

The entity references the data stream name. createIndex = false indicates the application does not auto-create an index via repository lifecycle; the data stream and mapping are provisioned by templates or deployment processes.

The @timestamp mapping must match the mapping created in the index template. The Java property name can be timestamp, while the field name stored in Elasticsearch must be @timestamp as annotated.

### Pay attention that write operations must be create

Data streams require write operations to use create semantics. Standard index write APIs may default to index semantics, allowing documents with the same ID to be overwritten. Therefore, do not assume every Spring Data save method works with data streams across all versions.

When using Spring Data, inspect the API of your deployed version to specify document creation (CREATE) semantics for each write. With APIs allowing IndexQuery configuration, you can specify the corresponding operation type if supported by that version. If repository abstractions cannot express the required semantics, use the Elasticsearch Java Client and send a create operation directly.

Example at the Elasticsearch Java Client level:

    client.index(request -> request
        .index("logs-app-default")
        .id(log.getId())
        .opType(OpType.Create)
        .document(log)
    );

Enum names and builder types must match the Java API Client version. The mandatory requirement is that requests use op_type=create when writing to a data stream.

For bulk indexing, use the create action for each event:

    client.bulk(request -> request
        .operations(operation -> operation
            .create(create -> create
                .index("logs-app-default")
                .id(log.getId())
                .document(log)
            )
        )
    );

Do not use a bulk index action intending to overwrite old documents in a data stream.

### Searching with Spring Data

Spring Data search APIs can use the data stream name as IndexCoordinates or entity indexName:

    SearchHits<AppLog> hits =
        operations.search(query, AppLog.class);

Spring Data sends the query to the data stream name; Elasticsearch executes the search across backing indices. Ensure the entity's mapping and backing indices are compatible.

If using a repository, confirm that the repository does not trigger unintended index creation and that write methods adhere to create semantics. Setting createIndex = false is generally appropriate when data streams are managed by dedicated templates and lifecycles.

## 11. Rules on updates and deletes

Data streams are designed for append-only data. Directly updating or deleting documents by ID conflicts with the create-only semantics of a data stream.

If previously written information needs adjustment, there are several approaches:

- Write a new event describing the correction or new state.
- Use event sourcing or projections to compute current state at the read layer.
- For special administrative needs, consider update_by_query or delete_by_query APIs supported by your Elasticsearch version, while understanding the impact on append-only guarantees and lifecycles.
- If the business domain routinely updates/deletes documents by ID, move that data to a regular index or an index accessed via an alias.

Do not design a data stream like a CRUD table. Attempting updates by ID can be rejected by the server or create complex processing flows inconsistent with the original purpose.

## 12. Compatibility requirements across backing indices

A data stream can contain multiple backing indices created at different points in time. When querying the entire stream, field mappings must be compatible so Elasticsearch can perform searches, sorts, and aggregations consistently.

Example of a schema error:

- The first backing index has duration_ms as long.
- A new backing index accidentally infers duration_ms as keyword.
- Range queries or aggregations across the whole data stream may fail or behave unexpectedly.

Common causes:

- Relying entirely on dynamic mapping.
- Changing Java entities without updating the template.
- A new template having an unexpected priority.
- Multiple templates matching the pattern and overriding settings.
- Producers sending different JSON types across versions.

To preserve compatibility:

1. Declare explicit mappings for key fields.
2. Use index templates with controlled patterns and priorities.
3. Use component templates to reuse shared mappings.
4. Test templates before new backing indices are created.
5. Inspect mappings of all backing indices when investigating query errors.
6. Apply schema changes deliberately rather than only editing entities.

You can validate templates with the simulate index template API before applying them. This shows which templates will match and the final configuration a new index receives.

## 13. Standard data streams vs. time series data streams

Standard data streams fit logs, events, and timestamped append-only data. Elasticsearch also offers time series data streams (TSDS) for time-based metrics data with stricter requirements.

TSDS may require:

- index.mode set to time_series.
- @timestamp with an appropriate date mapping.
- Dimension fields explicitly declared and identified.
- Metric fields configured with corresponding types and metrics settings.
- routing_path configured according to dimensions.
- Compliance with time bounds and data structure limits per Elasticsearch version.

Conceptual example of a metric mapping:

    {
      "settings": {
        "index.mode": "time_series",
        "index.routing_path": [ "host", "service" ]
      },
      "mappings": {
        "properties": {
          "@timestamp": {
            "type": "date"
          },
          "host": {
            "type": "keyword",
            "time_series_dimension": true
          },
          "service": {
            "type": "keyword",
            "time_series_dimension": true
          },
          "cpu_usage": {
            "type": "double",
            "time_series_metric": "gauge"
          }
        }
      }
    }

This example only illustrates the main components; TSDS imposes additional validation rules and version-specific compatibility requirements. Do not pick TSDS solely because documents have timestamps. Select it only when data genuinely represents metrics/time-series and can satisfy Elasticsearch's dimensions, metrics, and routing model.

## 14. Inspecting and operating data streams

Commonly used observability APIs:

    GET _data_stream/logs-app-default

Inspect mappings:

    GET .ds-logs-app-default-*/_mapping

Inspect backing indices:

    GET _cat/indices/.ds-logs-app-default-*?v

Check analyzers or field mappings using appropriate APIs when the data stream contains text content.

During operations, monitor:

- Number of backing indices.
- Age and size of the write index.
- Ingest rate and document count.
- Rollover status.
- Mapping errors or create operation failures.
- Storage usage and retention.
- Search load across backing indices.

If rollover fails to occur, the write index can keep growing. If retention fails to run, old data can consume disk longer than planned. If the mapping template is flawed, errors may only surface when a new backing index is created or when a producer emits a new field.

## 15. Common mistakes

### Missing @timestamp

Data streams require documents to have @timestamp mapped as date or date_nanos. Documents lacking this field or having an incompatible type will be rejected.

### Using a data stream for entities needing frequent updates

Data streams are optimized for append-only events. If the business domain needs to update or delete documents by ID like standard CRUD, consider a regular index or alias.

### Writing with index semantics

Data streams require create semantics. If a client sends requests overwriting documents by ID, the server may reject them. Inspect op_type and the API used by Spring Data or the client.

### Writing directly to a backing index

Applications should write through the data stream name. Writing to a specific backing index bypasses write-index routing and breaks lifecycle assumptions.

### Relying on dynamic mapping

Backing indices can receive different mappings if initial data or templates differ. Declare explicit mappings and test templates before creating indices.

### Confusing data streams with aliases

Both provide a logical name, yet they have different write rules and lifecycles. Data streams are tailored for append-only/time-series data; aliases fit diverse index models, including CRUD and versioned index cutovers.

### Not planning for duplicates on retry

If a write request succeeds but the response is lost, retrying can create duplicate events when IDs are auto-generated. Design deterministic event IDs or accept and deduplicate downstream at the consumption layer.

### Not checking mappings after rollover

A new backing index's mapping depends on the template at creation time. After modifying a template, verify the new index receives the right schema and older backing indices remain compatible with stream-wide queries.

## Conclusion

A data stream is a logical name managing a sequence of backing indices, suited for append-only data such as logs, events, metrics, and telemetry. Every document requires @timestamp mapped as date/date_nanos; write operations must follow create semantics; backing indices are created and managed via templates along with rollover/lifecycle policies.

In Spring Data Elasticsearch, entities can reference a data stream name and use converters to map documents, but the application must ensure the stream is provisioned properly and write operations use create semantics. If data needs CRUD by ID, a regular index or alias is typically more suitable. Understanding these compatibility requirements helps avoid write failures, mapping drift across backing indices, and operational friction with time-based data.
