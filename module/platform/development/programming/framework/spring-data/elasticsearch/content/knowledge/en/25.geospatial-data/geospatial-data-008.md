# Querying with CriteriaQuery, NativeQuery, or the Direct Client

Geospatial data is commonly used to answer questions such as: which places lie within a 5 km radius around the user, which stores fall inside a map region, or which delivery point is nearest to a coordinate pair. Elasticsearch provides dedicated data types and Query DSL for coordinates, geographic regions, and distances.

In Spring Data Elasticsearch, you can construct geospatial queries using **CriteriaQuery** for simple conditions supported by the abstraction, use **NativeQuery** when fine-grained control over Query DSL is needed, or call the **Elasticsearch Java API Client** directly when lower-level API access is required. The choice depends on query complexity, how tightly it needs to integrate with Spring Data mapping/conversion, and the level of request control needed.

This lesson uses a store and service-point locator example. It focuses on declaring geo_point, querying by distance and area, sorting by distance, combining business filters, and reading results in Spring Data Elasticsearch.

## 1. Geospatial data types in Elasticsearch

Two commonly encountered mapping types are:

- **geo_point**: a single geographic coordinate pair, typically used for stores, users, delivery stations, or devices.
- **geo_shape**: a geographic shape such as a point, line, polygon, or multi-shape, typically used for service zones, administrative boundaries, or delivery areas.

Choose the type matching your data and business needs. If each document has only one position and needs radius or distance searches, geo_point is usually enough. If you need spatial relationships between regions or complex shapes, consider geo_shape.

### geo_point

A geo_point can be represented in multiple formats. The object form is usually easiest to read:

~~~json
{
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
~~~

Other formats supported by Elasticsearch include:

~~~json
{
  "location": [106.7009, 10.7769]
}
~~~

~~~json
{
  "location": "10.7769,106.7009"
}
~~~

Note the coordinate order:

- In objects, use explicit lat and lon names.
- In geo_point coordinate arrays, the order is [longitude, latitude].
- In geo_point strings, the format is latitude,longitude.
- When using GeoJSON in geo_shape, standard GeoJSON coordinates are [longitude, latitude].

Mixing up latitude and longitude is a common reason queries fail silently without errors by searching the wrong region.

### geo_shape

geo_shape stores geographic shapes. Example GeoJSON polygon:

~~~json
{
  "deliveryArea": {
    "type": "polygon",
    "coordinates": [
      [
        [106.68, 10.77],
        [106.73, 10.77],
        [106.73, 10.81],
        [106.68, 10.81],
        [106.68, 10.77]
      ]
    ]
  }
}
~~~

A polygon's coordinate ring must be closed by repeating the starting point at the end. Every GeoJSON coordinate pair uses longitude then latitude.

## 2. Declaring an entity with a geographic location

Spring Data Elasticsearch provides the GeoPoint type and the @GeoPointField annotation for geo_point fields.

Store entity example:

~~~java
@Document(indexName = "stores")
public class Store {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String name;

    @Field(type = FieldType.Keyword)
    private String city;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    @GeoPointField
    private GeoPoint location;
}
~~~

You can instantiate coordinates in Java:

~~~java
GeoPoint location = new GeoPoint(10.7769, 106.7009);
~~~

Spring Data's GeoPoint constructor takes latitude first and then longitude. When converting to GeoJSON or coordinate arrays, swap the order to match that format.

Equivalent Elasticsearch mapping:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "keyword"
      },
      "city": {
        "type": "keyword"
      },
      "status": {
        "type": "keyword"
      },
      "active": {
        "type": "boolean"
      },
      "location": {
        "type": "geo_point"
      }
    }
  }
}
~~~

If using @Field(type = FieldType.GeoPoint) instead of @GeoPointField, verify that the annotation and converter align with the property type in your version of Spring Data Elasticsearch. In Spring Data, @GeoPointField is the dedicated, easily recognizable declaration.

### Saving coordinates and updating mappings

The field must be mapped with the right type before indexing data. If a field was already created as keyword or object, you cannot alter it directly to geo_point on the existing index. You need to create a new index, declare the proper mapping, reindex or rewrite the data, and switch aliases/traffic.

For API inputs, validate latitude between -90 and 90 and longitude between -180 and 180. Do not accept out-of-range coordinates just because the JSON parses cleanly.

## 3. Commonly used geospatial queries

Elasticsearch provides several query types for geo_point and geo_shape.

| Query | Purpose | Usage example |
|---|---|---|
| geo_distance | Find points within a radius from coordinates | Stores within 5 km |
| geo_bounding_box | Find points inside a geographic rectangle | Places inside the visible map viewport |
| geo_polygon | Find points inside a polygon | Points inside a selected region |
| geo_shape | Evaluate relation between points/shapes and regions | Point inside service area or two overlapping zones |

The right query depends on the mapping type. Queries designed for geo_point and geo_shape are not arbitrarily interchangeable.

## 4. Querying by radius with geo_distance

geo_distance finds documents whose location lies within a maximum distance from a center point.

Example finding stores within a 5 km radius around coordinates:

~~~http
POST /stores/_search
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
~~~

distance takes a value with a unit such as 5km, 500m, or 3mi. Always include an explicit unit so the query is clear and unambiguous.

You can combine geospatial queries with business filters using bool:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "geo_distance": {
            "distance": "5km",
            "location": {
              "lat": 10.7769,
              "lon": 106.7009
            }
          }
        },
        {
          "term": {
            "active": true
          }
        },
        {
          "term": {
            "status": "OPEN"
          }
        }
      ]
    }
  }
}
~~~

In this example, a store must fall within the radius while also being active and having status OPEN. Because the conditions sit in filter context, they narrow down matching documents rather than contributing text relevance scores.

### How is distance calculated?

Elasticsearch supports multiple geographic distance calculation methods. For distance queries, the common choice is arc, which computes arc distance on a spherical surface and fits most use cases. Some APIs also offer plane, which can be faster over small areas but becomes less accurate over long distances or wide regions.

Do not compute distances manually by subtracting latitude/longitude in Java and treating the result like kilometers. The length of a degree of longitude/latitude varies with position, and planar math fails to reflect true distance on the Earth's surface.

## 5. Querying rectangular areas with geo_bounding_box

When a user pans a map and the screen only needs points currently inside the viewport, geo_bounding_box is the right fit.

~~~http
POST /stores/_search
{
  "query": {
    "geo_bounding_box": {
      "location": {
        "top_left": {
          "lat": 10.82,
          "lon": 106.65
        },
        "bottom_right": {
          "lat": 10.72,
          "lon": 106.76
        }
      }
    }
  }
}
~~~

The query returns points inside the rectangle defined by the two corners. The names top_left and bottom_right describe bounding box corners; do not confuse them with the [lon, lat] order of GeoJSON arrays.

A bounding box fits map viewports well, though it cannot accurately represent areas with irregular boundaries. If users draw polygons or you must check membership in irregularly shaped zones, use geo_shape or an appropriate polygon query.

### Bounding boxes crossing the 180-degree meridian

For areas near the international date line, a bounding box can cross the 180-degree meridian. This is a special case requiring careful verification of data, corner specification, and actual results. Do not apply naive longitude comparisons in Java to override Elasticsearch's semantics.

## 6. Querying polygon areas and geo_shape

For polygonal zones, Elasticsearch provides geo_polygon for simple point-in-polygon checks, depending on version and support. For richer shapes, use a geo_shape field and geo_shape query.

Example querying points/shapes intersecting a polygon:

~~~json
{
  "query": {
    "geo_shape": {
      "deliveryArea": {
        "shape": {
          "type": "polygon",
          "coordinates": [
            [
              [106.68, 10.77],
              [106.73, 10.77],
              [106.73, 10.81],
              [106.68, 10.81],
              [106.68, 10.77]
            ]
          ]
        },
        "relation": "intersects"
      }
    }
  }
}
~~~

The geo_shape query compares the supplied shape against the indexed shape. Common relations include:

- intersects: the two shapes share an intersection.
- within: the indexed shape lies inside the query shape per relation semantics.
- contains: the indexed shape contains the query shape.
- disjoint: the two shapes do not intersect.

Confirm the relation direction with respect to the indexed object and the query object; within and contains cannot be swapped while preserving the same meaning.

### geo_shape mapping

The mapping can be declared as:

~~~json
{
  "mappings": {
    "properties": {
      "deliveryArea": {
        "type": "geo_shape"
      }
    }
  }
}
~~~

geo_shape suits polygons, multipolygons, line strings, and other geographic shapes supported by Elasticsearch. Data can be supplied in GeoJSON. Close polygon rings and ensure coordinates follow longitude, latitude order.

If the application only stores a single delivery point, using geo_point is simpler. Do not use geo_shape merely because it sounds more general; shape mappings and queries carry their own costs and semantics.

## 7. Building geospatial queries with CriteriaQuery

CriteriaQuery is convenient when geospatial conditions fall within the operations supported by Spring Data Criteria. For simple queries such as searching inside a circle or bounding box, this abstraction keeps Java code clean without manually constructing full Query DSL.

Example finding stores within a circle:

~~~java
GeoPoint center = new GeoPoint(10.7769, 106.7009);

GeoCircle searchArea = new GeoCircle(
    center,
    new Distance(5, Metrics.KILOMETERS)
);

Criteria criteria = new Criteria("location")
    .within(searchArea);

Query query = new CriteriaQuery(criteria);

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

GeoPoint, GeoCircle, Criteria, CriteriaQuery, Distance, and Metrics belong to their respective Spring Data packages. Exact imports vary by version; GeoPoint takes latitude followed by longitude.

### Bounding box via Criteria

For a rectangular area, you can use GeoBox if your version of the Criteria API provides a within overload for that type:

~~~java
GeoBox box = new GeoBox(
    new GeoPoint(10.82, 106.65),
    new GeoPoint(10.72, 106.76)
);

Criteria criteria = new Criteria("location").within(box);
Query query = new CriteriaQuery(criteria);

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

The two points passed are top-left and bottom-right respectively under the GeoBox model. Check the constructors and geo criteria API of your actual release train if your Spring Data version differs from this example.

### Combining geospatial Criteria with business conditions

You can chain geospatial criteria with other conditions in Criteria:

~~~java
Criteria criteria = new Criteria("location").within(searchArea)
    .and("active").is(true)
    .and("status").is("OPEN");

Query query = new CriteriaQuery(criteria);

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

This works cleanly for simple conditions. When you need fine-grained control over bool branches, multiple geospatial clauses, should, must_not, distance sorting, or geo_shape relations, Criteria may fall short. In those cases, use NativeQuery.

### When is CriteriaQuery not enough?

Choose a different abstraction if:

- The query needs geo_shape with relations or complex shapes.
- You need custom combinations of bool branches and geospatial queries.
- You need distance sorting with detailed options.
- You need nested queries or aggregations combined with geospatial criteria.
- You need Elasticsearch options not wrapped by the Criteria API.
- You need to preserve an exact Query DSL structure produced by another system.

Do not force a complex query into a long, hard-to-read Criteria chain.

## 8. Using NativeQuery when Query DSL control is needed

Spring Data Elasticsearch's NativeQuery lets you use the Elasticsearch Java API Client's query model. It fits well when you want to keep integration with ElasticsearchOperations, entity mapping, and SearchHits while needing detailed Query DSL.

Example building a geo-distance query with the Java API Client query builder:

~~~java
co.elastic.clients.elasticsearch._types.query_dsl.Query geoQuery =
    co.elastic.clients.elasticsearch._types.query_dsl.Query.of(q -> q
        .geoDistance(g -> g
            .field("location")
            .distance("5km")
            .location(location -> location.latlon(point -> point
                .lat(10.7769)
                .lon(106.7009)
            ))
        )
    );

NativeQuery query = NativeQuery.builder()
    .withQuery(geoQuery)
    .withPageable(PageRequest.of(0, 20))
    .build();

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

This builder snippet illustrates the Elasticsearch Java API Client API used in modern Spring Data Elasticsearch versions. Package names, overloads, and builder structure can vary across client versions; check your project's dependencies. The core idea is that NativeQuery takes a typed Query built with the client builder instead of manually assembling JSON via string concatenation.

You can add business filters to a bool query:

~~~java
Query combinedQuery = Query.of(q -> q.bool(b -> b
    .filter(f -> f.geoDistance(g -> g
        .field("location")
        .distance("5km")
        .location(location -> location.latlon(point -> point
            .lat(10.7769)
            .lon(106.7009)
        ))
    ))
    .filter(f -> f.term(t -> t
        .field("active")
        .value(true)
    ))
    .filter(f -> f.term(t -> t
        .field("status")
        .value("OPEN")
    ))
));

NativeQuery query = NativeQuery.builder()
    .withQuery(combinedQuery)
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

This structure places all three conditions in filter context. If the query also needs full-text relevance, put match inside must and keep geospatial conditions in filter.

### Designing with Query DSL JSON first

For multi-layered queries, write and test the JSON in Elasticsearch Dev Tools first:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "coffee"
          }
        }
      ],
      "filter": [
        {
          "geo_distance": {
            "distance": "3km",
            "location": {
              "lat": 10.7769,
              "lon": 106.7009
            }
          }
        },
        {
          "term": {
            "active": true
          }
        }
      ]
    }
  }
}
~~~

Once semantics and mappings are verified, translate the structure to Java API Client builders and wrap it in NativeQuery. This separates Query DSL errors from builder construction errors.

## 9. Calling the Elasticsearch Java API Client directly

You can call ElasticsearchClient directly when low-level control over requests and responses is needed. This is useful for specialized APIs or when the application needs client features not yet exposed through Spring Data abstractions.

Example:

~~~java
SearchResponse<Store> response = elasticsearchClient.search(s -> s
    .index("stores")
    .size(20)
    .query(q -> q.geoDistance(g -> g
        .field("location")
        .distance("5km")
        .location(location -> location.latlon(point -> point
            .lat(10.7769)
            .lon(106.7009)
        ))
    )),
    Store.class
);

List<Store> stores = response.hits().hits().stream()
    .map(hit -> hit.source())
    .filter(Objects::nonNull)
    .toList();
~~~

This example uses the Java API Client; verify generic types, imports, and builder overloads for the Elasticsearch client version managed by Spring Boot.

### Differences between NativeQuery and direct client

| Criterion | NativeQuery + Operations | Direct ElasticsearchClient |
|---|---|---|
| Query DSL | Uses Java API Client query model | Uses Java API Client query model |
| Entity mapping | Integrates Spring Data converters and mapping | Caller handles source/response conversion |
| Results | SearchHits<T>, SearchHit<T> | SearchResponse<T>, client hits |
| Aggregations/metadata | Follows Spring Data abstractions | Direct access to client response |
| Request control | High, within Operations scope | Very high |
| Repository/service integration | Seamless with Spring Data ecosystem | Requires clear adapters and conversion |

If the application already uses Spring Data for most queries, NativeQuery preserves a consistent programming model. The direct client fits situations where low-level APIs or full response control are genuinely required.

### Avoiding inconsistent mixing of access layers

If some services use Operations and others call the client directly, standardize:

- Who is responsible for resolving index/alias names?
- Where are entity mapping and conversion handled?
- Is Elasticsearch error handling uniform?
- Are timeouts, retries, and tracing configured consistently?
- At which layer are raw responses converted into DTOs?

You can encapsulate the direct client behind an adapter so the rest of the application stays decoupled from client response types.

## 10. Sorting by distance with geo-distance sort

A common use case is finding stores within a radius and putting the nearest store first.

Query DSL:

~~~json
{
  "size": 20,
  "query": {
    "geo_distance": {
      "distance": "10km",
      "location": {
        "lat": 10.7769,
        "lon": 106.7009
      }
    }
  },
  "sort": [
    {
      "_geo_distance": {
        "location": {
          "lat": 10.7769,
          "lon": 106.7009
        },
        "order": "asc",
        "unit": "km",
        "distance_type": "arc"
      }
    }
  ]
}
~~~

The query identifies the set of stores within 10 km. The sort calculates each store's distance to the center coordinates and orders ascending, placing the nearest store first.

Distance queries and distance sorts serve different purposes:

- geo_distance in query decides whether a document is included.
- _geo_distance in sort decides document ordering.

If you sort without filtering, results can contain very distant places. If you query without sorting, there is no guarantee the nearest store appears first.

### Multi-geo_point documents

If a field stores multiple locations, sorting needs a rule to select a representative distance. Elasticsearch supports modes such as min, max, avg, or median depending on the sort type. When finding the nearest branch to a user, you normally want the shortest distance to any branch.

Clarify whether each document represents one point or multiple points. If each branch needs independent ranking, modeling one document per branch is usually simpler than storing an array of coordinates in a single document.

### Pagination after geo-distance sort

For deep pagination, sorting must be deterministic. Add a unique field as a tie-breaker after distance:

~~~json
{
  "sort": [
    {
      "_geo_distance": {
        "location": {
          "lat": 10.7769,
          "lon": 106.7009
        },
        "order": "asc",
        "unit": "km"
      }
    },
    {
      "storeId": "asc"
    }
  ]
}
~~~

When using search_after, pass back all sort values from the last hit, including both distance and tie-breaker. Do not recompute sort values from entities, since Elasticsearch's returned values are the exact cursor for that query.

## 11. Combining geospatial search with filters and full-text

A place search page may let users search for a keyword like coffee, cap the radius, restrict to open stores, and filter by category.

The query can be structured as:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "coffee"
          }
        }
      ],
      "filter": [
        {
          "geo_distance": {
            "distance": "5km",
            "location": {
              "lat": 10.7769,
              "lon": 106.7009
            }
          }
        },
        {
          "term": {
            "active": true
          }
        },
        {
          "terms": {
            "category": ["cafe", "restaurant"]
          }
        }
      ]
    }
  },
  "sort": [
    {
      "_geo_distance": {
        "location": {
          "lat": 10.7769,
          "lon": 106.7009
        },
        "order": "asc",
        "unit": "km"
      }
    }
  ]
}
~~~

must finds content matching coffee. filter restricts distance, active status, and category. Sort places the nearest locations first.

If the product values text relevance more than distance, sort by _score first and then distance. If distance is the primary criterion, sort by _geo_distance first. This is a product experience decision, not merely a technical detail.

## 12. Reading results and distances in Spring Data

With ElasticsearchOperations, search results are wrapped in SearchHits<T>:

~~~java
SearchHits<Store> hits =
    operations.search(query, Store.class);

for (SearchHit<Store> hit : hits.getSearchHits()) {
    Store store = hit.getContent();
    float score = hit.getScore();

    // Use store for entity data.
    // Read sort metadata if the query declared a sort.
}
~~~

SearchHit<T> exposes entity content and metadata such as ID, index, score, sort values, highlights, and inner hits depending on the request. When sorting by distance, the distance sort value sits in getSortValues() following the order of sort criteria.

Do not assume distance is always the first element if the query also sorts by _score or other fields. Maintain a single sort definition and map the exact sort-value index.

When calling the direct client, results live in SearchResponse<T> and each hit provides source and sort values according to the client response. An adapter should map that response into application DTOs.

### Returning distance in DTOs

An API might return:

~~~java
public record StoreSearchItem(
    String id,
    String name,
    GeoPoint location,
    Double distanceKm
) {}
~~~

distanceKm should be extracted from distance sort metadata or calculated via a consistent rule. Do not blindly grab sort index 0; verify the query's sort structure.

If the application recalculates distance in Java for display, use an appropriate geospatial library or formula and treat it strictly as a presentation value. Primary ranking should still follow the semantics of the executed Elasticsearch query/sort.

## 13. Building a nearest-store service

A service should accept typed coordinates and radius parameters, validate them first, and then construct the query.

Example structure:

~~~java
public List<Store> findNearby(
        double latitude,
        double longitude,
        double radiusKm) {

    validateCoordinates(latitude, longitude);

    if (radiusKm <= 0 || radiusKm > 100) {
        throw new IllegalArgumentException(
            "radiusKm must be between 0 and 100"
        );
    }

    GeoCircle circle = new GeoCircle(
        new GeoPoint(latitude, longitude),
        new Distance(radiusKm, Metrics.KILOMETERS)
    );

    Criteria criteria = new Criteria("location").within(circle)
        .and("active").is(true);

    Query query = new CriteriaQuery(criteria);

    SearchHits<Store> hits =
        operations.search(query, Store.class);

    return hits.getSearchHits().stream()
        .map(SearchHit::getContent)
        .toList();
}
~~~

This snippet illustrates the case where your version's Criteria API supports GeoCircle and Criteria chaining as shown. If nearest-first ordering is needed, add geo-distance sorting via the appropriate sort API or use NativeQuery to declare _geo_distance explicitly.

Coordinate validation helper:

~~~java
private void validateCoordinates(double latitude, double longitude) {
    if (!Double.isFinite(latitude)
            || latitude < -90
            || latitude > 90) {
        throw new IllegalArgumentException("Invalid latitude");
    }

    if (!Double.isFinite(longitude)
            || longitude < -180
            || longitude > 180) {
        throw new IllegalArgumentException("Invalid longitude");
    }
}
~~~

Do not validate coordinate ranges alone. Applications should also cap maximum radius and page size to avoid overly broad queries or unexpectedly large payloads.

## 14. Testing geospatial queries

Geospatial queries require integration tests against a real Elasticsearch instance or compatible test environment. Unit tests for coordinate validation alone cannot verify mappings and geo query semantics.

Build a small dataset with representative points:

| Store | Illustrative coordinates | Expectation relative to search center |
|---|---|---|
| Store A | Near center | Inside small radius |
| Store B | Farther than A, still within radius | Included in results |
| Store C | Outside radius | Excluded from results |
| Store D | Inside bounding box, outside polygon | Distinguishes the two region types |
| Store E | Duplicate or nearly equal coordinates | Tie-breaker determines order |

Scenarios to test:

1. Center coordinates return expected matches.
2. Points just inside and outside the radius boundary.
3. km and m units are interpreted properly.
4. Bounding box returns exact points within the frame.
5. Polygons have closed coordinate rings and proper longitude/latitude order.
6. Geo_shape relations yield correct results matching relation direction.
7. active/status filters combined with geo queries do not leak disabled documents.
8. Geo-distance sort orders accurately from nearest to farthest.
9. Multi-point documents respect the chosen sort mode.
10. Pagination maintains stable order across pages.
11. Invalid coordinates are rejected at the service layer.
12. Index aliases have uniform mappings when querying across multiple indices.

### Verifying with Dev Tools

Before moving a query into Java, execute the JSON request directly in Elasticsearch Dev Tools. This confirms:

- Field mappings are properly geo_point or geo_shape.
- Coordinates use the right order.
- Query type is appropriate.
- Radius and units are right.
- Sort returns accurate distances.

Once Query DSL behaves properly, translate it to CriteriaQuery or NativeQuery. If results diverge, compare the actual request sent by Spring Data against the verified JSON.

## 15. Common mistakes and fixes

| Symptom | Possible cause | Resolution |
|---|---|---|
| No nearby points found despite seemingly valid coordinates | Swapped latitude and longitude | Check input format and mapping |
| Points appear in a very distant region | Coordinate array has wrong order | Use [lon, lat] for geo_point arrays and GeoJSON |
| Query reports field is not geo_point | Field mapped as keyword/object or stale mapping | Create proper mapping and reindex |
| geo_distance returns more results than expected | Incorrect radius or unit | Specify units explicitly such as 5km |
| Bounding box results differ from drawn region | Bounding box is strictly a rectangle | Use polygon/geo_shape for irregular zones |
| Invalid polygon | Unclosed ring or wrong coordinate order | Check GeoJSON coordinates |
| geo_shape relation has inverted meaning | Mixed up within/contains direction | Identify indexed shape vs. query shape |
| Nearest store is not first | Used geo_distance query without sorting | Add _geo_distance sort |
| Next page contains duplicate results | Equal distances without tie-breaker | Add a unique field and pass all sort values |
| Criteria cannot express the query | Abstraction lacks required options | Switch to NativeQuery |
| Direct client returns null source | Hit lacks _source or uses different response projection | Handle nulls and inspect request/mapping |
| Alias query fails across indices | Inconsistent geo field mappings | Align mappings or split aliases |

## 16. Choosing CriteriaQuery, NativeQuery, or the direct client

Each of the three options has its place:

| Requirement | Appropriate choice |
|---|---|
| Circle or rectangle search with simple conditions | CriteriaQuery |
| Combining geo queries, bool clauses, distance sorting, nested queries, or shape relations | NativeQuery |
| Low-level client APIs, raw responses, or features unwrapped by Spring Data | Direct ElasticsearchClient |
| Keeping Spring Data SearchHits<T>, mapping, and converters | CriteriaQuery or NativeQuery via ElasticsearchOperations |
| Full control over requests/responses | Direct client with a dedicated conversion adapter |

Do not jump to the direct client just because a query includes a geo_distance condition. If NativeQuery expresses the query cleanly, staying on Operations keeps code consistent with Spring Data.

Conversely, do not cram a multi-layered geospatial query into Criteria if the abstraction sacrifices expressiveness or readability. Pick the lowest API tier needed to express the exact semantics cleanly.

## 17. Checklist for implementing geospatial queries

- [ ] Location field is mapped as geo_point or geo_shape matching the data.
- [ ] Coordinates are normalized and validated.
- [ ] Latitude/longitude and longitude/latitude orders are not confused.
- [ ] Distances specify explicit units.
- [ ] Use geo_distance for radii and geo_bounding_box for viewports.
- [ ] Use geo_shape for irregularly shaped regions.
- [ ] Pick the proper relation between indexed shape and query shape.
- [ ] Combine geospatial queries with business filters in bool when needed.
- [ ] Include geo-distance sort when nearest-first results are required.
- [ ] Add a tie-breaker to sort if cursor pagination is used.
- [ ] Restrict CriteriaQuery to operations supported by the abstraction.
- [ ] NativeQuery uses query builders matching the Java API Client version.
- [ ] Direct client is wrapped in an adapter with consistent conversion/error-handling rules.
- [ ] Integration tests verify mappings, boundaries, units, and sorting.
- [ ] Mapping changes roll out via new indices and reindexing as needed.

CriteriaQuery suits simple geospatial queries supported by Spring Data's abstraction. NativeQuery lets you combine Elasticsearch Java API Client geospatial queries with filters, sorts, and complex conditions while still using ElasticsearchOperations. The direct client offers lower-level control over requests and responses. Whichever path you choose, start from an accurate mapping, explicit coordinate conventions, and Query DSL whose semantics are verified with real data.
