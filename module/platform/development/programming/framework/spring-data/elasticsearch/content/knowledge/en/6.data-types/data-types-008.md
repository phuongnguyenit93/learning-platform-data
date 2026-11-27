# `flattened` and Limitations When Attribute Structures Change

## 1. The Problem When Objects Have Continuously Changing Structures

In Elasticsearch, a standard JSON object is typically mapped as type `object`. Each sub-property can become a separate field in the mapping.

Event document example:

~~~json
{
  "id": "evt-100",
  "message": "Service started",
  "attributes": {
    "host": "api-01",
    "region": "ap-southeast-1",
    "environment": "production"
  }
}
~~~

If `attributes` uses an `object` mapping with default dynamic mapping, Elasticsearch creates mappings for keys such as `attributes.host`, `attributes.region`, and `attributes.environment` when receiving the document.

This works well when the data structure is known and stable. However, many applications have user-defined, external-service, or event-specific metadata. The next document might carry completely different keys:

~~~json
{
  "id": "evt-101",
  "message": "Payment processed",
  "attributes": {
    "merchant": "shop-42",
    "payment_provider": "gateway-x",
    "retry_count": 2,
    "risk_level": "low",
    "device": {
      "type": "mobile",
      "os": "Android"
    }
  }
}
~~~

Over time, thousands of distinct keys can appear. Elasticsearch must create mappings for every key and its sub-fields. As field counts climb, the cluster has to manage a larger mapping, consumes more memory, and can hit the index's total field limit. This phenomenon is commonly known as **mapping explosion**.

The `flattened` field type is designed for cases where an object has many unpredictable or frequently changing keys. It maps the entire object as a single field and indexes leaf values in a way similar to `keyword`. Consequently, new keys can appear in data without causing the mapping to spawn a separate field for every key.

## 2. What Is `flattened`?

`flattened` is an Elasticsearch mapping type for JSON objects with flexible structures. Rather than mapping each sub-property as an independent field, Elasticsearch treats the entire object as one field and indexes leaf values as keywords.

Mapping:

~~~json
{
  "mappings": {
    "properties": {
      "message": {
        "type": "text"
      },
      "attributes": {
        "type": "flattened"
      }
    }
  }
}
~~~

Document:

~~~json
{
  "message": "Service started",
  "attributes": {
    "host": "api-01",
    "region": "ap-southeast-1",
    "environment": "production",
    "retry_count": 2,
    "device": {
      "type": "mobile",
      "os": "Android"
    }
  }
}
~~~

Here, the mapping only needs one `attributes` field. The keys `host`, `region`, `environment`, `retry_count`, `device.type`, and `device.os` do not generate individual mapping fields via ordinary dynamic mapping.

Elasticsearch still indexes the values so they can be searched by key or across the whole object. Nested keys are accessed using dot notation, such as `attributes.device.type`.

The key point is that `flattened` does not turn the object into one giant JSON string. Elasticsearch extracts leaf values and indexes them under their corresponding keys, treating those values as keywords. The original object structure can still be read from `_source` according to the index's source storage configuration.

## 3. How `flattened` Handles Keys and Values

Suppose a document has an object:

~~~json
{
  "attributes": {
    "priority": "urgent",
    "release": ["v1.2.5", "v1.3.0"],
    "timestamp": {
      "created": 1541458026,
      "closed": 1541457010
    }
  }
}
~~~

You can think of leaf values as indexed along these paths:

~~~text
attributes.priority          -> "urgent"
attributes.release           -> "v1.2.5", "v1.3.0"
attributes.timestamp.created -> "1541458026"
attributes.timestamp.closed  -> "1541457010"
~~~

Both key names and values participate in how Elasticsearch organizes data for search. Values are treated as keyword strings—not automatically analyzed by a text analyzer, and numbers or dates are not automatically converted into numeric or date types.

There are two common search patterns:

- Query the root field to find a value under any key in the object.
- Query a specific key using a dotted path.

Example querying the root field:

~~~json
{
  "query": {
    "term": {
      "attributes": "urgent"
    }
  }
}
~~~

This query finds documents containing the value `urgent` anywhere inside the `attributes` object.

Querying by specific key:

~~~json
{
  "query": {
    "term": {
      "attributes.priority": "urgent"
    }
  }
}
~~~

This query only searches for `urgent` at the `priority` key inside `attributes`.

For nested objects, you can use the full path:

~~~json
{
  "query": {
    "term": {
      "attributes.device.type": "mobile"
    }
  }
}
~~~

Key paths help distinguish identical values stored in different places. For example, `attributes.owner` and `attributes.reviewer` can both hold a person's name while remaining two separate keys.

## 4. Declaring `flattened` in Spring Data Elasticsearch

Spring Data Elasticsearch includes `FieldType.Flattened` on the `@Field` annotation. A Java property of type `Map<String, Object>` fits well for representing objects with flexible key/value pairs.

Entity example:

~~~java
import java.util.Map;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "events")
public class EventDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String message;

    @Field(type = FieldType.Flattened)
    private Map<String, Object> attributes;

    // Constructors, getters and setters
}
~~~

`@Field(type = FieldType.Flattened)` instructs Spring Data to generate a flattened mapping for `attributes` when mappings are created from entity metadata.

The application can populate different keys depending on event type:

~~~java
import java.util.HashMap;

Map<String, Object> attributes = new HashMap<>();
attributes.put("host", "api-01");
attributes.put("region", "ap-southeast-1");
attributes.put("retry_count", 2);

EventDocument event = new EventDocument();
event.setId("evt-100");
event.setMessage("Service started");
event.setAttributes(attributes);
~~~

The document sent to Elasticsearch is formatted as a JSON object:

~~~json
{
  "id": "evt-100",
  "message": "Service started",
  "attributes": {
    "host": "api-01",
    "region": "ap-southeast-1",
    "retry_count": 2
  }
}
~~~

Spring Data handles converting between the Java map and the document. The Elasticsearch mapping determines how keys/values inside the object are indexed.

Note: merely declaring annotations on an entity does not automatically modify the mapping of an existing index. If the index was already created with `attributes` as type `object`, create a new index or run an appropriate migration workflow to change the mapping to `flattened`. Inspect the actual mapping after creating the index.

## 5. Querying `flattened` with Query DSL

Because values are indexed as keywords, `flattened` supports basic queries such as `term`, `terms`, `terms_set`, `prefix`, `wildcard`, `regexp`, `fuzzy`, `range`, `match`, `multi_match`, `query_string`, `simple_query_string`, and `exists`.

### Finding an Exact Value

~~~json
{
  "query": {
    "term": {
      "attributes.environment": "production"
    }
  }
}
~~~

`term` is appropriate when matching an indexed keyword value.

### Finding One of Multiple Values

~~~json
{
  "query": {
    "terms": {
      "attributes.region": [
        "ap-southeast-1",
        "ap-northeast-1"
      ]
    }
  }
}
~~~

The query finds documents whose region matches one of the supplied values.

### Prefix Search

~~~json
{
  "query": {
    "prefix": {
      "attributes.host": "api-"
    }
  }
}
~~~

This query can find hosts starting with `api-`.

### Checking Whether a Key Has an Indexed Value

~~~json
{
  "query": {
    "exists": {
      "field": "attributes.retry_count"
    }
  }
}
~~~

`exists` is useful when a key can appear in some documents and be absent in others.

You can query the root field if you only care whether a value appears somewhere in the object. However, querying by a specific key is usually clearer and reduces unintended matches.

## 6. Critical Limitation: Every Value Is a Keyword

This is the most important limitation to keep in mind when choosing `flattened`. Values inside the object are indexed as keyword strings, even when the original JSON contains numbers, booleans, or timestamps.

Document example:

~~~json
{
  "attributes": {
    "retry_count": 10,
    "enabled": true,
    "created_at": 1735689600000
  }
}
~~~

With default `flattened` behavior:

- `retry_count` is treated as the string `"10"`.
- `enabled` is treated as the string `"true"`.
- `created_at` is treated as a string representation of the timestamp number.

Elasticsearch does not automatically treat `retry_count` as an integer, `enabled` as a boolean, or `created_at` as a date. Consequently, range queries on `flattened` compare values in lexicographical string order rather than numeric or chronological order.

For example, comparing strings `"100"` and `"20"` lexicographically produces a different result from comparing numbers 100 and 20. Therefore, do not use range queries on `flattened` to check numeric thresholds or date intervals without specialized data types.

The following example does not have numeric semantics like an integer field:

~~~json
{
  "query": {
    "range": {
      "attributes.retry_count": {
        "gte": "10",
        "lte": "20"
      }
    }
  }
}
~~~

If you need to filter retry counts from 10 to 20 numerically, map that key as a separate `integer` or `long` field, or use an explicitly mapped numeric property.

Similarly, if you need date, IP, geographic coordinate, or range queries, use specialized field types. `flattened` fits flexible metadata where operations are primarily keyword-style value lookups.

## 7. Sorting and Aggregations on `flattened`

`flattened` supports sorting and keyword-oriented aggregations such as `terms`, but these operations still work on keyword values.

Example aggregation counting documents by environment:

~~~json
{
  "size": 0,
  "aggs": {
    "environments": {
      "terms": {
        "field": "attributes.environment"
      }
    }
  }
}
~~~

Example sorting by a key:

~~~json
{
  "sort": [
    {
      "attributes.region": {
        "order": "asc"
      }
    }
  ]
}
~~~

For numeric or date values stored under default `flattened` settings, the sort order is lexicographical. Do not rely on that output as numeric or chronological order.

If you need to sort by number, date, or IP, define important keys as typed sub-fields or separate fields with appropriate mappings.

Additional limitations:

- Highlighting is not supported on flattened fields.
- Wildcards cannot be used to match key names in field paths; for example, you cannot query `attributes.time*` as a dynamic field pattern.
- Keys must be specified explicitly when querying sub-fields.
- The `store` mapping parameter is not supported for flattened fields.
- Advanced capabilities of specialized field types are not automatically available on `flattened`.

Thus, `flattened` can handle basic search and statistics over metadata, but it does not replace all capabilities of explicitly typed fields.

## 8. Mapped Sub-Fields: Preserving Typed Mappings for Important Keys

Not every key inside an object needs identical handling. Some keys vary flexibly, while others have stable business meaning and require specialized data-type queries.

Elasticsearch supports declaring `properties` inside a `flattened` mapping to map specific keys as typed sub-fields. Example:

~~~json
{
  "mappings": {
    "properties": {
      "attributes": {
        "type": "flattened",
        "properties": {
          "host.name": {
            "type": "keyword"
          },
          "host.ip": {
            "type": "ip"
          },
          "retry_count": {
            "type": "long"
          },
          "created_at": {
            "type": "date"
          }
        }
      }
    }
  }
}
~~~

In this example:

- `host.name` is a keyword field.
- `host.ip` is an IP field supporting IP-aware queries.
- `retry_count` is a long field supporting numeric ranges.
- `created_at` is a date field supporting temporal queries.

Keys declared in `properties` are indexed through their corresponding typed sub-fields and are no longer handled as ordinary flattened values. Other keys continue using flattened's default keyword mechanism.

Document example:

~~~json
{
  "attributes": {
    "host": {
      "name": "web-1",
      "ip": "192.168.1.10"
    },
    "retry_count": 12,
    "created_at": "2026-11-13T09:30:00Z",
    "region": "ap-southeast-1"
  }
}
~~~

Numeric range query on a mapped key:

~~~json
{
  "query": {
    "range": {
      "attributes.retry_count": {
        "gte": 10,
        "lte": 20
      }
    }
  }
}
~~~

IP query:

~~~json
{
  "query": {
    "term": {
      "attributes.host.ip": "192.168.1.10"
    }
  }
}
~~~

Mapped sub-fields combine flexible objects with explicitly typed key handling. However, this is not a way to turn every dynamic key into a typed field. Only pre-known, pre-declared keys receive typed mappings. Typed sub-fields can only be leaf field types; you cannot declare `object`, `nested`, or another `flattened` inside these `properties`.

In Spring Data Elasticsearch, `@Field(type = FieldType.Flattened)` declares the root field. If you need detailed `properties` configuration for keys inside `flattened`, you can manage mappings via a JSON mapping resource or your application's mapping creation mechanism. For example, using `@Mapping` to load a mapping from the classpath:

~~~java
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Mapping;

@Document(indexName = "events")
@Mapping(mappingPath = "/mappings/events-mapping.json")
public class EventDocument {
    // Entity fields
}
~~~

With this approach, the mapping file must contain the complete index mapping, including the flattened `attributes` field and the chosen typed sub-fields. `@Mapping` supplies the mapping resource when creating entity mappings. If the index is provisioned externally and the application sets `createIndex = false`, deploy the mapping file via your external provisioning tooling; annotations do not automatically update existing indices. When using a mapping resource instead of annotation-generated mappings, keep the resource configuration and entity metadata consistent.

## 9. How Do `flattened`, `object`, and `nested` Differ?

These three types serve different goals:

| Criterion | `object` | `nested` | `flattened` |
|---|---|---|---|
| Purpose | JSON object with a relatively clear field structure | Object array needing per-element correlation | Object with a large or unpredictable number of keys |
| Mapping | Sub-fields are mapped individually | Sub-fields are mapped individually in nested scope | Entire object is a single field |
| New keys | Dynamic mapping can create new fields | Dynamic mapping can create new sub-fields | Does not create separate mapping fields per key |
| Value types | Can use text, keyword, numeric, date, IP, etc. | Can use specialized field types | Leaf values default to keyword |
| Relationship among objects in an array | Can be flattened and lose correlation | Preserved inside each nested document | Not a substitute for nested to preserve object correlation |
| Queries | Standard field queries | Requires nested queries | Basic queries on root or key paths |
| Best suited for | Relatively stable schemas | Elements with multiple attributes that must match together | Flexible metadata, labels, attributes |

Selection examples:

- Customer profile with `name`, `birthDate`, `status`: use separate fields with explicit types.
- Product variant list with `color`, `size`, `stock` needing combined filtering on the same variant: consider `nested`.
- Event metadata with hundreds of keys sent by various services: consider `flattened`.
- Selected keys in metadata needing numeric or IP filtering: use typed sub-fields or promote them to separate fields.

Do not use `flattened` for every object just to prevent mapping explosion. If the data structure is stable, an explicitly typed object mapping enables richer Elastic queries and analysis.

## 10. Dynamic Mapping: Controlling Objects Differently

When using `object`, you can tune dynamic mapping to control new keys.

Example:

~~~json
{
  "mappings": {
    "properties": {
      "attributes": {
        "type": "object",
        "dynamic": false
      }
    }
  }
}
~~~

With `dynamic: false`, undeclared keys are not added to the mapping and are not indexed, though they can still be retained in `_source`. This works well if the application only needs to store metadata to read back later without searching by new keys.

If set to `dynamic: strict`, documents containing undeclared fields are rejected at indexing time. This fits scenarios where schemas must be strictly enforced.

Comparison:

- `object` with default dynamic: new keys can create new mapping fields and be queried by inferred types.
- `object` with `dynamic: false`: new keys remain in source but are not indexed.
- `object` with `dynamic: strict`: undeclared keys cause document rejection.
- `flattened`: new keys are still indexed as keywords without creating individual mapping fields per key.

Therefore, choosing between `flattened` and `dynamic: false` depends on whether you need to search on unknown keys.

## 11. Structural and Data-Relationship Limitations

`flattened` handles high key counts, but does not preserve the full semantics of a typed object model.

### Does Not Replace `nested` for Element Correlation

Suppose an object has a list of variants:

~~~json
{
  "variants": [
    {
      "color": "black",
      "stock": 0
    },
    {
      "color": "white",
      "stock": 12
    }
  ]
}
~~~

If the goal is finding a variant that is both black and in stock, the correlation between `color` and `stock` within the same element must be preserved. `flattened` is not a replacement for nested queries in this case.

If data has complex relationships, model it with `nested` or separate documents depending on query patterns.

### Does Not Guarantee Original Data-Type Semantics

A key might contain numbers, dates, or booleans today, yet receive strings tomorrow from another producer. `flattened` accepts these values as keywords, meaning the application must govern value conventions itself.

For instance, `created_at` may sometimes be epoch millis and sometimes an ISO-8601 string. If accurate temporal queries are needed, normalize data before writing and map it to a dedicated `date` field or typed sub-field.

### Object Depth Limit

`flattened` has a `depth_limit` parameter restricting object nesting depth. The current default is 20 levels. If input data is nested too deeply, Elasticsearch can reject the document. Do not treat `flattened` as storage for arbitrarily deep JSON trees.

### Leaf Arrays and Synthetic Source

In ordinary `_source` configurations, Elasticsearch preserves the original JSON source according to the index's source storage mode. With synthetic `_source`, reconstructing leaf arrays of `flattened` may sort and deduplicate values or strip nulls under default settings. The `preserve_leaf_arrays` mapping parameter can adjust this mode, though preserving order, duplicates, and nulls can increase doc values storage cost.

If element order and multiplicity carry business meaning, verify the exact `_source` mode in use and consider storing a separate dedicated representation.

## 12. Designing Entities and Mappings in Spring Applications

A practical design separates stable business fields from flexible metadata.

~~~java
import java.time.Instant;
import java.util.Map;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "events")
public class EventDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String serviceName;

    @Field(type = FieldType.Date)
    private Instant occurredAt;

    @Field(type = FieldType.Text)
    private String message;

    @Field(type = FieldType.Flattened)
    private Map<String, Object> attributes;

    // Constructors, getters and setters
}
~~~

In this design:

- `serviceName` is a dedicated keyword field because exact filtering or aggregations are often needed.
- `occurredAt` is a dedicated date field so temporal ranges and sorting have proper semantics.
- `message` is text for full-text search.
- `attributes` holds flexible metadata such as host, region, deployment, labels, or service-specific details.

When a key inside `attributes` becomes important and requires specialized type queries, you can promote it to an explicit field or declare a typed sub-field in the mapping.

This is a common schema evolution path: initially a key is flexible metadata, and later widely used keys graduate into explicitly typed business properties. Not everything has to stay inside `flattened` forever.

## 13. Workflow for Choosing and Implementing `flattened`

You can follow these steps:

1. **Assess schema stability.** List which fields have fixed structures and which have keys varying by data source.
2. **Keep business fields separate.** Properties requiring full-text search, numeric ranges, date ranges, sorting, or typed aggregations should be mapped separately.
3. **Choose object or flattened.** Use `object` when the schema is known; use `flattened` when dynamic keys must be indexed without creating new mappings per key.
4. **Choose the Java type.** Use `Map<String, Object>` for flexible objects and annotate with `@Field(type = FieldType.Flattened)`.
5. **Declare typed sub-fields if needed.** Pre-identify critical keys such as IP, date, long, or keyword and configure mappings for them.
6. **Create the index with the right mapping.** Do not rely on annotations to modify mappings on an existing index.
7. **Test with realistic data.** Test nested keys, missing keys, null values, arrays, numbers, and strings.
8. **Verify queries.** Confirm term, prefix, range, sort, and aggregation behavior matches data semantics.
9. **Monitor mapping field counts.** Ensure flexible keys no longer cause uncontrolled mapping growth.
10. **Evolve the schema deliberately.** When a key becomes core data, promote it to a typed sub-field or standalone field, then migrate/reindex if the existing mapping must change.

## 14. Common Mistakes

**Using `flattened` for data needing numeric ranges.** Numeric values are treated as keyword strings; ranges and sorting can yield lexicographical results. Use typed sub-fields or dedicated numeric fields.

**Assuming dynamic keys receive automatic typing.** `flattened` does not infer `long`, `date`, `boolean`, or `ip` per key. If typed semantics are required, declare dedicated mappings.

**Using `flattened` to preserve object correlation.** `flattened` solves flexible mappings, not `nested` requirements for queries where conditions must belong to the same child object.

**Querying the root field when a specific key is intended.** Querying the root can match values under any key. Use paths like `attributes.region` when the condition targets a specific key.

**Expecting analyzers or highlighting like `text`.** `flattened` values are not analyzed like ordinary text and do not support highlighting.

**Dumping all data into a single Map.** Important business fields lose the benefits of specialized mappings if stored only in `flattened`. Separate stable fields from dynamic metadata.

**Editing only annotations after the index exists.** Existing mappings do not automatically switch from `object` to `flattened`. Create a new index and reindex when changing mapping types.

**Failing to validate data from multiple sources.** The same key might be sent in multiple formats. Standardize data conventions before indexing.

## Conclusion

`flattened` is a solid choice for JSON objects with many unpredictable or frequently changing keys. It maps the entire object into one field, indexes leaf values as keywords, and helps prevent mapping explosion as metadata grows.

In exchange, default values lose specialized semantics of numbers, dates, booleans, or IPs; range queries and sorting on flattened values follow lexicographical rather than numeric order. `flattened` also cannot replace `nested` for preserving correlation across object arrays and does not provide the full feature set of `text` fields.

In Spring Data Elasticsearch, you can pair `Map<String, Object>` with `@Field(type = FieldType.Flattened)`. Good design keeps stable business fields on specialized mappings while reserving `flattened` for flexible metadata. When a dynamic key becomes important, promote it to a typed sub-field or dedicated field based on query needs.

## References

- [Elasticsearch — Flattened field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/flattened)
- [Elasticsearch — Field data types](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/field-data-types)
- [Spring Data Elasticsearch — Object Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch — Field annotation API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/annotations/Field.html)
