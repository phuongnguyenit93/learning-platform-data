# Limitations in Expressing Nested, Geo-Shape, and Complex Conditions

Spring Data Elasticsearch supports several ways to declare queries. For simple conditions, derived queries from method names are readable and sufficient. When search requirements involve multiple `bool` levels, conditions that must match on the same `nested` element, `geo_shape` geometric queries, aggregations, or dynamic conditional branches, method names and query annotations can become difficult to express.

The limitation here does not mean Elasticsearch lacks support for those queries. Elasticsearch Query DSL can represent very rich structures. The point is choosing the Spring Data abstraction that matches query complexity:

- **Derived queries**: suited for simple conditions derivable from method names.
- **`@Query`**: suited for explicit JSON Query DSL that is relatively static and parameterizable.
- **`NativeQuery` / `ElasticsearchOperations`**: suited for dynamic queries, nested queries, geo-shape queries, and complex DSL structures built in code.
- **Elasticsearch Java Client directly**: suited when fine-grained request/response control is needed or features are not conveniently exposed by current Spring Data abstractions.

The goal is keeping query semantics clear, especially the scope of nested conditions and geometric semantics of geo-shape queries.

## 1. Three levels of query expression in Spring Data Elasticsearch

### 1.1 Derived queries from method names

Spring Data can parse repository method names to generate queries. Example:

```java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);

    List<Product> findByActiveTrue();

    List<Product> findByPriceBetween(Double min, Double max);

    List<Product> findByCategoryAndActiveTrue(String category);
}
```

These methods are easy to understand because each describes a simple condition. However, derived queries only support the keywords and name-parsing rules defined by Spring Data. They are not a general-purpose language for expressing arbitrary Query DSL structures.

When a query requires a nested query wrapping multiple same-element conditions, a geo-shape relation, multiple `should` branches, `minimum_should_match`, `inner_hits`, or deeply nested queries, cramming everything into a method name makes it long, hard to read, and unable to guarantee correct semantics.

For example, a method name such as:

```java
findByVariantsColorAndVariantsSizeAndVariantsAvailableTrue(...)
```

does not automatically guarantee that color, size, and available are evaluated against the same element inside the `variants` array. If the field is `nested`, a nested query with an explicit scope is required. Method names cannot replace proper nested Query DSL design.

### 1.2 `@Query` with Elasticsearch Query DSL JSON

`@Query` lets you declare JSON queries directly on repository methods. This helps when queries are static, readable as JSON, and only substitute a few parameters.

Nested query example:

```java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
        {
          "nested": {
            "path": "variants",
            "query": {
              "bool": {
                "filter": [
                  { "term": { "variants.color": "?0" } },
                  { "term": { "variants.size": "?1" } },
                  { "term": { "variants.available": true } }
                ]
              }
            }
          }
        }
        """)
    List<Product> findProductsWithAvailableVariant(String color, String size);
}
```

Placeholders `?0` and `?1` refer to the first and second parameters. All three conditions sit inside the same nested query, so they must match on the same nested document under `variants`.

`@Query` avoids overly long method names and shows the DSL directly. However, queries are written as strings. When there are optional branches, varying shapes, or input-dependent logic, assembling JSON strings becomes hard to maintain. Never concatenate user input directly into JSON; rely on Spring Data's supported parameter binding and inspect generated queries.

### 1.3 `NativeQuery` and `ElasticsearchOperations`

When queries must be built dynamically, `NativeQuery` paired with `ElasticsearchOperations` is usually more suitable. You can add or omit conditions based on input, assemble `bool` clauses, declare nested queries, sorting, aggregations, and search options without creating long method names or manually concatenating JSON.

Service structure example:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<Product> search(Query query) {
        return operations.search(query, Product.class);
    }
}
```

`Query` can be a `NativeQuery` built with the Elasticsearch Java Client builders. Specific builder APIs depend on the Spring Data Elasticsearch and Elasticsearch Java Client versions used by your project. Repositories remain convenient for simple queries; for dynamic queries or preserving exact DSL structure, building `NativeQuery` in a dedicated layer keeps logic clear.

## 2. Nested queries: condition scope matters more than method names

Suppose a product has multiple variants:

```json
{
  "name": "Jacket",
  "variants": [
    { "color": "red", "size": "XL", "available": true },
    { "color": "blue", "size": "M", "available": true }
  ]
}
```

The `variants` field must be mapped as `nested` if queries need to preserve relationships among properties of individual elements:

```json
PUT /products
{
  "mappings": {
    "properties": {
      "name": { "type": "text" },
      "variants": {
        "type": "nested",
        "properties": {
          "color": { "type": "keyword" },
          "size": { "type": "keyword" },
          "available": { "type": "boolean" }
        }
      }
    }
  }
}
```

### 2.1 One nested query containing multiple conditions

Requirement: find products with a variant that is simultaneously red, size M, and available.

```json
GET /products/_search
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "bool": {
          "filter": [
            { "term": { "variants.color": "red" } },
            { "term": { "variants.size": "M" } },
            { "term": { "variants.available": true } }
          ]
        }
      },
      "inner_hits": {}
    }
  }
}
```

All conditions live inside one nested scope, so they must match together on a single variant. With the sample document above, no single element is both red and size M, so the product is not returned.

### 2.2 Multiple independent nested queries have a different meaning

If you write two separate nested queries at the parent level—one for red and one for size M—they can match two different variants:

```json
GET /products/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "nested": {
            "path": "variants",
            "query": { "term": { "variants.color": "red" } }
          }
        },
        {
          "nested": {
            "path": "variants",
            "query": { "term": { "variants.size": "M" } }
          }
        }
      ]
    }
  }
}
```

This query means: the product has at least one red variant and at least one size M variant; the two variants need not be the same.

| Structure | Conditions must match |
|---|---|
| One `nested` containing multiple filters | The same nested element |
| Multiple independent `nested` clauses at parent | Potentially different nested elements |

This is a semantic distinction that name-based derived queries usually cannot express clearly enough. When multiple child conditions exist, write explicit nested DSL and test with documents whose elements intentionally split conditions across items.

### 2.3 Multi-level nested queries

Mappings can contain nested fields inside nested fields. For example, an order has a list of `items`, and each item has a list of `discounts`. To find an item containing a discount matching a condition, the query must traverse the exact nested paths matching the mapping structure.

```json
{
  "nested": {
    "path": "items",
    "query": {
      "bool": {
        "filter": [
          { "term": { "items.sku": "SKU-1001" } },
          {
            "nested": {
              "path": "items.discounts",
              "query": {
                "range": {
                  "items.discounts.percent": { "gte": 10 }
                }
              }
            }
          }
        ]
      }
    }
  }
}
```

This illustrates nested scopes inside nested scopes. `items.discounts` must be declared as nested in the mapping. The query must specify the right path and parent-child scope; merely using dotted field paths without a nested query does not produce nested semantics.

## 3. Geo-shape: geometric queries beyond method-name conditions

Basic geo queries can find points near coordinates or within a geographic bounding region. Geo-shape extends the model to work with complex shapes such as polygons, multipolygons, linestrings, and envelopes. Applications can represent service areas, administrative boundaries, delivery zones, routes, or restricted zones.

Requirements such as "find stores whose service area intersects the user-selected region" or "find land parcels completely inside project boundaries" require a `geo_shape` query with a specific relation. Name-based derived queries are not the right abstraction for expressing this geometry.

### 3.1 Mapping a geo_shape field

Example store index with a `serviceArea` field:

```json
PUT /stores
{
  "mappings": {
    "properties": {
      "name": { "type": "text" },
      "serviceArea": { "type": "geo_shape" }
    }
  }
}
```

A document can store a polygon in GeoJSON format:

```json
PUT /stores/_doc/store-01
{
  "name": "Central Store",
  "serviceArea": {
    "type": "polygon",
    "coordinates": [
      [
        [106.68, 10.76],
        [106.72, 10.76],
        [106.72, 10.79],
        [106.68, 10.79],
        [106.68, 10.76]
      ]
    ]
  }
}
```

In GeoJSON, coordinate order is `[longitude, latitude]`, i.e., longitude first and latitude second. This is a common bug when ingesting data from systems using latitude/longitude order. Polygons must close by repeating the first point at the end of the ring; the first ring is the outer boundary, and subsequent rings (if present) represent holes.

Common shape types include `point`, `multipoint`, `linestring`, `multilinestring`, `polygon`, `multipolygon`, `geometrycollection`, and `envelope`. Choose types fitting your geographic data and validate coordinates/geometries before indexing.

### 3.2 `geo_shape` queries and relations

Example finding stores whose service area intersects a query polygon:

```json
GET /stores/_search
{
  "query": {
    "geo_shape": {
      "serviceArea": {
        "shape": {
          "type": "polygon",
          "coordinates": [
            [
              [106.70, 10.77],
              [106.74, 10.77],
              [106.74, 10.80],
              [106.70, 10.80],
              [106.70, 10.77]
            ]
          ]
        },
        "relation": "intersects"
      }
    }
  }
}
```

`relation` specifies the spatial relationship between the indexed shape in the document and the query shape:

| Relation | General meaning |
|---|---|
| `intersects` | Both shapes share some area; this is the common default |
| `within` | Indexed shape lies inside the query shape |
| `contains` | Indexed shape contains the query shape |
| `disjoint` | Both shapes do not intersect |

Read the relation in the direction **document shape relative to query shape**. Reversing the subject alters results. With `within`, the document shape must be inside the query shape; with `contains`, the document shape must enclose the query shape.

### 3.3 Geo-shape vs. geo-distance and geo-bounding-box

Not all geographic queries need `geo_shape`:

| Field/query type | Data | Best-fit use case |
|---|---|---|
| `geo_point` + `geo_distance` | Single coordinate point | Finding points within a radius of a location |
| `geo_point` + `geo_bounding_box` | Single coordinate point | Finding points inside a coordinate rectangle |
| `geo_shape` | Polygons, lines, envelopes, and other shapes | Spatial relationships between regions or geometries |

If you only need stores within 5 km of a user, `geo_point` and `geo_distance` are usually simpler. If you need to check whether a service area intersects a customer's polygon, `geo_shape` is more appropriate.

## 4. Why are derived queries ill-suited for geo-shape?

Repository method names express conditions using Spring Data keywords such as `Between`, `LessThan`, `Containing`, or `Near` (depending on module and data type). However, geometric relationships between two shapes cannot be boiled down to a property name plus one simple operator.

A geo-shape query may require:

- Field mapping set to `geo_shape`.
- Query geometry with type and coordinates.
- Relation such as `intersects`, `within`, `contains`, or `disjoint`.
- Polygon orientation rules where applicable.
- Multiple shapes or multiple bool branches.
- Additional business filters such as store status or service type.

Those components belong to Query DSL structure. Trying to pack them into a method name does not make the query clearer. Use `@Query` if the shape is static; use `NativeQuery`/Java Client if shapes are constructed per request or require optional filters.

### 4.1 Static geo-shape queries with `@Query`

Example repository method with a fixed polygon:

```java
@Query("""
    {
      "geo_shape": {
        "serviceArea": {
          "shape": {
            "type": "envelope",
            "coordinates": [
              [106.70, 10.80],
              [106.74, 10.76]
            ]
          },
          "relation": "intersects"
        }
      }
    }
    """)
List<Store> findStoresIntersectingConfiguredArea();
```

This is a static query taking no shape from callers. For dynamic coordinate data, do not manually concatenate JSON strings. Use typed query builders or client APIs to build shapes safely.

## 5. Combining nested, geo-shape, and bool queries

A real requirement might search for stores that:

- Are active.
- Have a service area intersecting a user-selected polygon.
- Offer a matching service inside a nested `services` array.
- That service is enabled and of type `delivery`.

Example mapping:

```json
PUT /stores
{
  "mappings": {
    "properties": {
      "name": { "type": "text" },
      "active": { "type": "boolean" },
      "serviceArea": { "type": "geo_shape" },
      "services": {
        "type": "nested",
        "properties": {
          "type": { "type": "keyword" },
          "enabled": { "type": "boolean" }
        }
      }
    }
  }
}
```

Query DSL:

```json
GET /stores/_search
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } },
        {
          "geo_shape": {
            "serviceArea": {
              "shape": {
                "type": "polygon",
                "coordinates": [
                  [
                    [106.70, 10.77],
                    [106.74, 10.77],
                    [106.74, 10.80],
                    [106.70, 10.80],
                    [106.70, 10.77]
                  ]
                ]
              },
              "relation": "intersects"
            }
          }
        },
        {
          "nested": {
            "path": "services",
            "query": {
              "bool": {
                "filter": [
                  { "term": { "services.type": "delivery" } },
                  { "term": { "services.enabled": true } }
                ]
              }
            }
          }
        }
      ]
    }
  }
}
```

This query shows why derived queries no longer fit: conditions apply at three different scopes. `active` is a parent document field; `serviceArea` is a geometric relation; `services.type` and `services.enabled` must match together inside a nested document. An outer `bool.filter` combines all three requirements.

## 6. Choosing between @Query, NativeQuery, and Elasticsearch Java Client

No single option fits every query. You can use these criteria:

| Scenario | Recommended expression | Reason |
|---|---|---|
| Simple equality/range | Derived query | Short method name, clear intent |
| Static Query DSL, few parameters | `@Query` | JSON shows query structure directly |
| Many optional conditions | `NativeQuery` + `ElasticsearchOperations` | Build queries from input without JSON concatenation |
| Complex nested scopes | `NativeQuery` or Java Client | Explicit control over scopes and bool branches |
| Dynamic geo-shape | `NativeQuery` or Java Client | Construct shapes, coordinates, and relations per request |
| Aggregations, highlights, inner hits, complex sorting | `NativeQuery`/`ElasticsearchOperations` | Search API controls multiple parts of the request |
| Features not conveniently exposed by abstraction | Elasticsearch Java Client directly | Direct access to Elasticsearch API requests/responses |

### 6.1 When to use `@Query`

Advantages:

- Query DSL is immediately visible and directly comparable with REST requests.
- No multi-level builder boilerplate for stable queries.
- Easy to keep sample queries and test them in Elasticsearch Dev Tools.

Limitations:

- Queries live inside Java strings, which can get long and hard to read with deep nesting.
- Optional conditional logic feels unnatural; often forces extra methods or switching to builders.
- JSON structural mistakes may be hard to catch at compile time.
- Placeholders and escaping depend on Spring Data binding; never concatenate user data into JSON strings.

### 6.2 When to use NativeQuery

Advantages:

- Queries can be assembled dynamically from input data.
- Supports rich Elasticsearch Query DSL components via Java Client builders.
- Combines query, sort, aggregations, highlighting, and search options.
- Works with `ElasticsearchOperations` to map results back to entities.

Limitations:

- Builders can become verbose for deeply nested queries.
- Builder APIs evolve across Elasticsearch Java Client and Spring Data generations.
- Authors still need to understand Query DSL; builders do not fix wrong semantics automatically.
- Newer Elasticsearch features may not yet exist in the client version managed by your project.

### 6.3 When to use the Java Client directly

If you need APIs or response fields not exposed by `ElasticsearchOperations`, you can inject `ElasticsearchClient` and call the API directly. This gives fuller control, though the application assumes responsibility for result mapping, error handling, pagination, and data conversion.

Avoid mixing multiple client layers for a single complex query. Pick one suitable abstraction per use case and isolate query-building logic in a dedicated service or repository adapter.

## 7. Building dynamic queries without JSON string concatenation

Suppose users can filter by category, geographic region, and several service filters, any of which may be omitted. A clean approach is collecting a list of filters from inputs and combining them inside one `bool`.

Pseudo-code describing the structure:

```java
List<Query> filters = new ArrayList<>();

if (category != null) {
    filters.add(termQuery("category", category));
}

if (serviceArea != null) {
    filters.add(geoShapeIntersectsQuery("serviceArea", serviceArea));
}

if (serviceType != null || enabledOnly) {
    filters.add(nestedServiceFilter(serviceType, enabledOnly));
}

Query query = boolFilter(filters);
```

Here `termQuery`, `geoShapeIntersectsQuery`, `nestedServiceFilter`, and `boolFilter` are conceptual helper functions, not built-in Spring Data APIs. In an implementation, they can return `co.elastic.clients.elasticsearch._types.query_dsl.Query` instances from the Elasticsearch Java Client and pass them into `NativeQuery.builder().withQuery(...)`.

Separating builders by scope keeps code easy to inspect:

- A parent filter builder handles only parent document fields.
- A nested query builder groups conditions that must match on the same child element.
- A geo-shape builder handles geometry type, coordinates, and relation.
- The final assembly combines branches into `bool.filter`, `must`, `should`, or `must_not`.

Do not dump all conditions into a flat list if they belong to different nested scopes. Query object structure should mirror the semantic scope of the requirement.

## 8. Expression limitations and how to handle them

### 8.1 Overly long method names

When a method name accumulates many `And`, `Or`, `Between`, `Containing`, `Not`, and property paths, it becomes hard to read and verify logically. Move to `@Query` or a builder so query structure is explicit.

### 8.2 Derived queries cannot guarantee nested scope alone

A method name listing multiple child properties does not imply conditions must match on the same nested object. Use a single nested query wrapping all same-scope conditions.

### 8.3 `@Query` is awkward for many optional branches

If a request supports a dozen optional filters, static JSON strings scale poorly. Use `NativeQuery` and builders to add only supplied conditions.

### 8.4 Geo-shape is more than two coordinates

Geo-shape requires geometry type, coordinate structure, and relation. Do not substitute `geo_distance` or bounding boxes when the requirement is intersection/containment between two geometries.

### 8.5 Queries with multiple `must_not` or `should` clauses

Nested `bool` branches and `minimum_should_match` directly impact results. Write explicit JSON or structured builders and build representative test data for every branch.

### 8.6 Query DSL depends on version support

The Elasticsearch Java Client, Spring Data Elasticsearch, and Elasticsearch server must be compatible. Newer server features might be absent from the client managed by Spring Boot. Check your dependency version matrix and API reference; do not upgrade a single client artifact independently if the framework manages a different version.

## 9. Testing complex queries

For nested and geo-shape queries, testing only matching documents is insufficient. Include near-miss documents that must not match to verify semantics.

### 9.1 Testing nested same-element matching

Create at least two documents:

```json
{
  "_id": "p1",
  "variants": [
    { "color": "red", "size": "XL" },
    { "color": "blue", "size": "M" }
  ]
}
```

```json
{
  "_id": "p2",
  "variants": [
    { "color": "red", "size": "M" }
  ]
}
```

A single-scope nested query requiring red and M must return only `p2`. If it also returns `p1`, inspect your mapping and how the nested query is structured.

### 9.2 Testing geo-shape relations

Create shapes that are:

- Completely inside the query polygon.
- Crossing the boundary of the query polygon.
- Enclosing the query polygon.
- Completely outside the query polygon.

Run each relation (`intersects`, `within`, `contains`, `disjoint`) and verify results in the direction of document shape versus query shape. Also test boundary coordinates and polygons with multiple rings if business data uses holes.

### 9.3 Testing dynamic queries

For each optional filter, test:

- Passing no filters.
- Passing a single filter.
- Passing multiple filters together.
- Passing empty or invalid values.
- Combining parent filters with nested filters and geo-shape.

Inspect actual outgoing queries when needed. Enable controlled logging in development or execute the same JSON DSL directly against an Elasticsearch test instance.

### 9.4 Using real Elasticsearch in integration tests

Behaviors depending on mappings, nested fields, analyzers, and geo-shape should be tested against a compatible Elasticsearch instance rather than only mocking repositories. Mocks confirm a service calls the right collaborator, but cannot prove the server understands the Query DSL as intended.

## 10. Design principles

- Use derived queries for simple, stable conditions where method names stay readable.
- Use `@Query` for static Query DSL with clear structure and few variations.
- Use `NativeQuery` when queries are built dynamically or have multi-level nested/geo-shape/bool clauses.
- Use the Elasticsearch Java Client directly when APIs/responses exceed what current abstractions offer.
- Place conditions that must match on the same child inside a single nested query.
- Place independent nested queries at the parent level when conditions may match different children.
- Use `geo_shape` for geometric relationships between regions/shapes; use `geo_point` for simple point and distance problems.
- Always confirm GeoJSON coordinate order is longitude then latitude.
- Never concatenate user input into JSON queries via string concatenation.
- Organize query builders by business scope and test edge cases.
- Verify compatibility across Spring Data, Elasticsearch Java Client, and Elasticsearch server.

## 11. Summary

Name-based derived queries are great for simple conditions, but they are not a complete language for Query DSL. Nested queries require explicit scoping so conditions evaluate on the same element or across different elements as required by business rules. Geo-shape requires geometry types, coordinates, and relations; complex bool logic likewise needs clear nested structure.

For static queries, `@Query` makes JSON DSL explicit. For dynamic queries, multi-level nesting, geo-shape, or multi-part search requests, `NativeQuery` paired with `ElasticsearchOperations` is usually more flexible. When full API control is needed, use the Elasticsearch Java Client directly. Whichever approach you pick, make query structure mirror data scope, real mappings, and user-expected semantics.
