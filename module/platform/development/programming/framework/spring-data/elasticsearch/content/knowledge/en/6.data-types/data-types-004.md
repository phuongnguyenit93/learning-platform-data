# Boolean, Binary, IP, and Specialized Types

Elasticsearch provides many field types beyond basic text and numeric types. Types such as `boolean`, `binary`, `ip`, `geo_point`, `geo_shape`, `completion`, `flattened`, or vector types help model data in the exact way the system needs to store and query it.

In Spring Data Elasticsearch, a field's mapping is typically declared using `@Field` on a Java property. This annotation describes the Elasticsearch type and several indexing attributes; Spring Data uses that metadata when creating mappings and converting documents. However, Java types and Elasticsearch types do not always map one-to-one. Choose the type based on how data is searched, filtered, sorted, or used in the application.

```text
Java model                         Elasticsearch mapping
----------                         ----------------------
Boolean / boolean       ------->   boolean
String with Base64      ------->   binary
String with IP address  ------->   ip
GeoPoint                ------->   geo_point
Shape                   ------->   geo_shape
String / object         ------->   completion / flattened / ...
```

Specialized types and mapping attributes can vary by Elasticsearch and Spring Data Elasticsearch version. When adopting a new type, check the server, Java client, and Spring Data versions managed by your application.

## 1. Boolean: True or False Data

The `boolean` type stores a state with two logical values: `true` or `false`. This is the right type for attributes like active accounts, enabled products, confirmed orders, or connected devices.

Entity example:

```java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(name = "is_active", type = FieldType.Boolean)
    private Boolean active;
}
```

Corresponding mapping in Elasticsearch:

```json
PUT /products
{
  "mappings": {
    "properties": {
      "is_active": {
        "type": "boolean"
      }
    }
  }
}
```

Document:

```json
{
  "is_active": true
}
```

### Querying Booleans

You can use a `term` query to find documents with the exact value `true`:

```json
GET /products/_search
{
  "query": {
    "term": {
      "is_active": true
    }
  }
}
```

In Spring Data, repositories can declare query methods based on the Java property:

```java
List<ProductDocument> findByActiveTrue();

List<ProductDocument> findByActiveFalse();
```

The method name references the `active` property; mapping metadata resolves that property to the `is_active` field when Spring Data constructs the query.

### Boolean Differs from Null

In Java, `boolean` is a primitive type that can only be `true` or `false`; `Boolean` is a wrapper type and can also be `null`. This distinction matters when data may omit a field or be undetermined.

| Value in document | Possible business meaning |
|---|---|
| `true` | Enabled / true / confirmed. |
| `false` | Disabled / false / rejected. |
| Field missing | Unknown, not yet recorded, or older data without the attribute. |

Elasticsearch does not automatically turn a missing field into `false`. If business rules treat a missing field as `false`, the application must normalize data or use a query that explicitly handles missing values. Do not blur `false` and `null` if they carry different meanings.

## 2. Binary: Storing Binary Data as Base64

The `binary` type is used for binary data represented as a Base64 string in JSON. Some use cases include small binary payloads, signatures, or embedded payloads inside a document.

Mapping:

```json
PUT /attachments
{
  "mappings": {
    "properties": {
      "file_name": {
        "type": "keyword"
      },
      "content_base64": {
        "type": "binary"
      }
    }
  }
}
```

A document can contain a Base64 string:

```json
{
  "file_name": "sample.bin",
  "content_base64": "SGVsbG8gRWxhc3RpY3NlYXJjaA=="
}
```

The value above is Base64-encoded data. When sending JSON, the client passes the Base64 string; Elasticsearch decodes that representation to store binary content according to the mapping.

### Is Binary Searchable?

A `binary` field is not designed for full-text search or filtering by byte content. It is not indexed like `text`/`keyword`, and does not provide doc values for standard sorting/aggregations. If you need to search file metadata, store metadata as separate fields:

```json
{
  "file_name": "report.pdf",
  "content_type": "application/pdf",
  "size_bytes": 125000,
  "content_base64": "..."
}
```

The application can filter by `file_name`, `content_type`, or `size_bytes`; `content_base64` only holds the binary payload.

In Spring Data, you can declare the field with `FieldType.Binary`:

```java
@Field(name = "content_base64", type = FieldType.Binary)
private String contentBase64;
```

In this example, the Java property holds the Base64 string. If you want to use `byte[]`, ensure the application's converter/serializer converts the byte array to a Base64 representation compatible with Elasticsearch's binary mapping. Inspect the actual document in `_source` and test reading it back in an integration test; do not assume every serializer handles byte arrays identically.

`binary` in Elasticsearch does not replace object storage or a file management system. For large files, usually store the content in object storage or a file service, while Elasticsearch stores only the URL/key, file name, MIME type, size, checksum, and searchable metadata. Embedding binary data enlarges documents and increases network, storage, snapshot, and reindexing costs.

## 3. IP: IPv4 and IPv6 Addresses

The `ip` type stores IPv4 or IPv6 addresses. It is suitable for client addresses, server addresses, network devices, or request source information.

Entity:

```java
@Document(indexName = "access-logs")
public class AccessLogDocument {

    @Id
    private String id;

    @Field(name = "client_ip", type = FieldType.Ip)
    private String clientIp;

    @Field(name = "request_path", type = FieldType.Keyword)
    private String requestPath;
}
```

Mapping:

```json
PUT /access-logs
{
  "mappings": {
    "properties": {
      "client_ip": {
        "type": "ip"
      },
      "request_path": {
        "type": "keyword"
      }
    }
  }
}
```

Documents can use IPv4 or IPv6:

```json
POST /access-logs/_doc
{
  "client_ip": "192.0.2.10",
  "request_path": "/api/products"
}
```

```json
POST /access-logs/_doc
{
  "client_ip": "2001:db8::1",
  "request_path": "/api/orders"
}
```

### Querying IP Addresses

You can filter for a specific address using `term`:

```json
GET /access-logs/_search
{
  "query": {
    "term": {
      "client_ip": "192.0.2.10"
    }
  }
}
```

You can find addresses within a CIDR block using a range query:

```json
GET /access-logs/_search
{
  "query": {
    "range": {
      "client_ip": {
        "gte": "192.0.2.0",
        "lte": "192.0.2.255"
      }
    }
  }
}
```

Depending on requirements, you can use supported CIDR syntax in IP queries to filter a subnet, such as `192.0.2.0/24`. Verify the exact syntax for the query in use and your Elasticsearch version.

### `ip` Differs from `ip_range`

`ip` stores a single IP address. `ip_range` stores a range of addresses, such as a network block or CIDR. These two types serve different data models:

| Type | Data | Example |
|---|---|---|
| `ip` | A single address | `192.0.2.10` |
| `ip_range` | An address range | `192.0.2.0` to `192.0.2.255` |

If a document represents a device or a request, `ip` is typically used. If a document represents a subnet or an allocated block, `ip_range` can be considered.

Do not use `keyword` for IPs simply because the input data is a string. The `ip` type provides storage and query handling suited to network address semantics, including range checks.

## 4. Geo-point: Point-Based Geographic Location

`geo_point` represents a location using longitude and latitude. This type is commonly used for stores, delivery addresses, GPS devices, or event origin locations.

Mapping:

```json
PUT /stores
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
      "location": {
        "type": "geo_point"
      }
    }
  }
}
```

A document can pass coordinates as an object:

```json
POST /stores/_doc/store-1
{
  "name": "Central Store",
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
```

Elasticsearch also supports other representations such as `"lat,lon"` strings or `[lon, lat]` arrays. Pay close attention to coordinate order: GeoJSON array format uses longitude first, latitude second.

In Spring Data Elasticsearch, you can use Spring Data's `GeoPoint` type and the corresponding geo point mapping:

```java
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Field(name = "location", type = FieldType.Geo_Point)
private GeoPoint location;
```

When converting between Java and Elasticsearch, keep the latitude/longitude convention consistent. Swapping the order can produce an incorrect location even though the values remain numerically valid.

### Distance Search

The `geo_distance` query finds documents with points within a radius around a location:

```json
GET /stores/_search
{
  "query": {
    "geo_distance": {
      "distance": "5km",
      "location": {
        "lat": 10.7769,
        "lon": 106.7009
      }
    }
  }
}
```

This can be combined with distance `sort` to bring the nearest locations first. `geo_point` fits when each document only needs a single representative point. If boundaries or regions must be modeled, look at `geo_shape`.

## 5. Geo-shape: Geographic Regions and Geometries

`geo_shape` stores geometries such as points, lines, polygons, or geometry collections. It is suitable when representing delivery zone boundaries, coverage areas, administrative regions, or restricted zones.

Mapping example:

```json
PUT /delivery-zones
{
  "mappings": {
    "properties": {
      "zone_name": {
        "type": "keyword"
      },
      "boundary": {
        "type": "geo_shape"
      }
    }
  }
}
```

Polygon document in GeoJSON:

```json
POST /delivery-zones/_doc/zone-1
{
  "zone_name": "Zone A",
  "boundary": {
    "type": "polygon",
    "coordinates": [
      [
        [106.69, 10.77],
        [106.72, 10.77],
        [106.72, 10.79],
        [106.69, 10.79],
        [106.69, 10.77]
      ]
    ]
  }
}
```

For polygons, the coordinate ring must close by repeating the first point at the end. GeoJSON coordinate order is `[longitude, latitude]`.

You can use a `geo_shape` query with relations such as `intersects`, `within`, `contains`, or `disjoint` depending on query type and version. For example, finding zones intersecting an input geometry:

```json
GET /delivery-zones/_search
{
  "query": {
    "geo_shape": {
      "boundary": {
        "shape": {
          "type": "point",
          "coordinates": [106.7009, 10.7769]
        },
        "relation": "intersects"
      }
    }
  }
}
```

`geo_shape` is more powerful than `geo_point` in modeling capability, but it also makes mappings and queries more complex. If you only need to find stores within a radius around a user, `geo_point` is usually the simpler choice.

## 6. Completion: Typeahead Suggestions

The `completion` type is optimized for autocomplete/suggest features. For example, when a user types `spr`, the system can suggest `Spring Data Elasticsearch`, `Spring Boot`, or `Spring Framework`.

Mapping:

```json
PUT /suggestions
{
  "mappings": {
    "properties": {
      "title": {
        "type": "completion"
      }
    }
  }
}
```

Document:

```json
POST /suggestions/_doc/1
{
  "title": {
    "input": [
      "Spring Data Elasticsearch",
      "Spring Elasticsearch"
    ],
    "weight": 10
  }
}
```

Sending a suggest request:

```json
GET /suggestions/_search
{
  "suggest": {
    "title-suggest": {
      "prefix": "spr",
      "completion": {
        "field": "title"
      }
    }
  }
}
```

The completion suggester uses specialized data structures to return suggestions quickly. It is well suited for pre-prepared suggestion lists, such as product names, place names, or keywords. If you need full-text search with token analysis, complex filter conditions, or searching across long content, `text` paired with appropriate queries may be more suitable.

Spring Data Elasticsearch supports mapping completion fields in corresponding versions. When using specialized annotations or Java types representing completion inputs, check the API for your exact version instead of assuming any `String` property is automatically converted to an `input`/`weight` structure.

## 7. Flattened: Objects with Many Dynamic Keys

Normally, Elasticsearch creates separate mappings for the sub-fields of an object. If each document contains many dynamic keys, the mapping can grow rapidly and hit the field count limit.

The `flattened` type stores an object's keys and values as a single composite field, helping curb mapping explosion. It is suitable for metadata with flexible key-value structures, such as extensible attributes sent from many sources.

Mapping:

```json
PUT /events
{
  "mappings": {
    "properties": {
      "event_id": {
        "type": "keyword"
      },
      "metadata": {
        "type": "flattened"
      }
    }
  }
}
```

Document:

```json
POST /events/_doc/1
{
  "event_id": "EVT-001",
  "metadata": {
    "source": "mobile",
    "region": "south",
    "campaign": "summer-2026"
  }
}
```

You can query a sub-key using the field path:

```json
GET /events/_search
{
  "query": {
    "term": {
      "metadata.region": "south"
    }
  }
}
```

Flattened helps manage objects with non-fixed keys, but it does not replace standard object mapping in every scenario. Values are handled with simple keyword semantics; numeric, range, full-text, and aggregation capabilities are not equivalent to each sub-field having its own typed mapping. If content analysis, numeric calculation, or specialized type queries are needed, declare fields explicitly.

## 8. Range Fields: Storing a Value Range

Elasticsearch has range types to store an interval instead of a single value, such as `integer_range`, `long_range`, `float_range`, `double_range`, `date_range`, and `ip_range`.

Example of a promotion valid during a date range:

```json
PUT /promotions
{
  "mappings": {
    "properties": {
      "name": {
        "type": "keyword"
      },
      "valid_period": {
        "type": "date_range"
      }
    }
  }
}
```

Document:

```json
POST /promotions/_doc/promo-1
{
  "name": "Summer sale",
  "valid_period": {
    "gte": "2026-06-01",
    "lt": "2026-09-01"
  }
}
```

A range query can check whether the stored range intersects a search range:

```json
GET /promotions/_search
{
  "query": {
    "range": {
      "valid_period": {
        "gte": "2026-07-01",
        "lt": "2026-08-01",
        "relation": "INTERSECTS"
      }
    }
  }
}
```

Range relations typically include `INTERSECTS`, `CONTAINS`, and `WITHIN`. Choose the right relation according to the business question: is the promotion active during any part of the month, spanning the entire month, or contained completely within the month.

A range field is not the same as two independent `start_date` and `end_date` fields. It represents the interval as a structured value and enables queries based on relationships between intervals.

## 9. Vector and Other Specialized Types

Elasticsearch has types serving semantic search and ranking, such as `dense_vector`, `sparse_vector`, `rank_feature`, and `rank_features`. Specific capabilities depend on the Elasticsearch version, license/deployment features, and index configuration.

### Dense Vector

`dense_vector` stores a numeric vector with a fixed number of dimensions. Vectors are typically generated by external embedding models or AI services, then used to find documents semantically close to a query.

Illustrative mapping:

```json
PUT /knowledge
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text"
      },
      "embedding": {
        "type": "dense_vector",
        "dims": 3,
        "index": true,
        "similarity": "cosine"
      }
    }
  }
}
```

Illustrative document:

```json
POST /knowledge/_doc/1
{
  "title": "Spring Data Elasticsearch",
  "embedding": [0.12, -0.08, 0.91]
}
```

The three-dimensional vector in the example is purely to illustrate structure. In real applications, the number of dimensions must match the chosen embedding model exactly. When switching to a model with a different dimension count or vector space, redesign the mapping and regenerate compatible embeddings.

### Rank Feature

`rank_feature` and `rank_features` store numeric signals used in ranking results, such as popularity, authority, or relevance indicators. They support specialized queries to fold these signals into the relevance score. Do not use them in place of standard numeric fields if the application needs calculations, range queries, or general numeric aggregations.

Vector and ranking types must be chosen according to specific query features. Before designing, check the documentation for your exact server version because parameter names, indexing options, and vector search algorithms can change across releases.

## 10. Choosing a Field Type by Need

| Data need | Elasticsearch type to consider | Notes |
|---|---|---|
| On/off flag, true/false state | `boolean` | Distinguish `false` from a missing field. |
| Small Base64 binary payload | `binary` | Not for searching byte content; consider object storage for large files. |
| Single IPv4/IPv6 address | `ip` | Supports querying by address and IP range. |
| A GPS location | `geo_point` | Used for distance and location-based searches. |
| Line, polygon, or geographic area | `geo_shape` | Used for geometric relations such as intersects/within. |
| Prefix autocomplete suggestions | `completion` | Optimized for pre-prepared autocomplete lists. |
| Object with many dynamic keys | `flattened` | Curb mapping explosion in exchange for less specialized sub-field types. |
| Numeric, date, or IP intervals | `*_range` types | Query relationships between intervals. |
| Embeddings or vector search | `dense_vector` / `sparse_vector` | Dimensions and features must be compatible with model/server. |
| Ranking signals | `rank_feature` / `rank_features` | Used in specialized scoring queries. |

Do not choose a specialized type simply because Elasticsearch supports it. Start from the questions the application needs to answer, then pick a mapping with matching semantics. For example, if you only need to store latitude/longitude and find stores within a radius, `geo_point` is simpler than `geo_shape`; if you need to search user names by content, `text` fits better than `completion`.

## 11. Applying in Spring Data Elasticsearch

Spring Data provides annotations to declare mappings on entities. For common types, you can describe them directly with `@Field`:

```java
@Document(indexName = "network-devices")
public class NetworkDeviceDocument {

    @Id
    private String id;

    @Field(name = "enabled", type = FieldType.Boolean)
    private Boolean enabled;

    @Field(name = "management_ip", type = FieldType.Ip)
    private String managementIp;

    @Field(name = "configuration_base64", type = FieldType.Binary)
    private String configurationBase64;
}
```

Types requiring more complex representations can use `@Field` with the corresponding type, specialized Spring Data annotations (if provided by the version), or JSON mapping declarations when creating the index. For example, `geo_point` can map to `GeoPoint`; completion and vectors need Java structures matching the client/converter contract.

For application-managed mappings, `IndexOperations` can be used to inspect or create an index with a prepared mapping. Ensure the actual index is created with the desired mapping before writing data. Merely adding annotations to an entity does not guarantee an existing index automatically changes its field types.

Example reading the mapping from Elasticsearch:

```http
GET /network-devices/_mapping
```

When a field has already been created with an unsuitable type, it is usually necessary to create a new index and reindex data instead of trying to alter the field type in place. Verify mapping compatibility with your Spring Data and server versions before deployment.

## 12. Data Validation and Common Mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| Boolean write throws parse error | Sending a string that is not a valid boolean representation or mismatched Java type. | Check actual JSON and `boolean` mapping. |
| Binary is not matched by queries | Binary fields are not indexed for content search. | Search by separate metadata such as name, MIME type, or checksum. |
| IP is rejected | Value is not a valid IPv4/IPv6 address or field has another mapping. | Check input data and `ip` mapping. |
| Geo query returns no results | Swapped latitude/longitude, invalid GeoJSON structure, or wrong field type. | Check `[lon, lat]` order and geo mapping. |
| Completion returns no suggestions | Field not mapped as `completion`, request uses wrong field, or data lacks matching inputs. | Check mapping, document, and suggest request. |
| Dynamic objects create too many fields | Each key is mapped as a separate field. | Consider `flattened` if per-key typed mappings are not needed. |
| Vector query reports wrong dimension | Written vector has a different element count from `dims` in mapping. | Align embedding model and mapping; regenerate vectors if changing models. |
| Mapping conflict after changing annotations | Existing index already has the field with the old type. | Create a new index, reindex, and switch aliases according to plan. |

When investigating, inspect all three parts: the Java entity, the current mapping, and the document in `_source`. If queries do not work, also check query type, analyzer, or specialized field features.

## 13. Key Takeaways

- `boolean` stores `true`/`false`; a missing field still differs from `false`.
- `binary` accepts binary data in Base64 form and is not suitable for searching byte content.
- `ip` is for IPv4/IPv6 addresses; `ip_range` is for address intervals.
- `geo_point` represents a point; `geo_shape` represents geometries such as lines or polygons.
- `completion` serves autocomplete; `flattened` fits objects with many dynamic keys.
- `*_range`, vector, and rank feature types solve specialized querying needs.
- Spring Data can declare mappings via `@Field` and supporting annotations; for complex types, check converters and capabilities of your version.
- Existing index mappings do not change automatically just because an entity is edited; changing field types usually requires migration/reindexing.

Choosing the right field type lets Elasticsearch store and query data with accurate semantics. With Spring Data Elasticsearch, combine explicit annotations, inspectable actual mappings, and integration tests to ensure the Java model, JSON documents, and queries remain consistent.
