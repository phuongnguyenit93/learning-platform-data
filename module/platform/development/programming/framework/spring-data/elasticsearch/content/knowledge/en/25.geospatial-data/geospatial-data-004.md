# Geo Distance Query and Searching Around a Location

Searching around a location is a common requirement in delivery apps, store locators, service booking, real estate, and asset management. Users provide coordinates or a geocoded address; the system needs to find documents whose locations fall within a given radius and typically sort the nearest places first.

Elasticsearch supports the `geo_point` data type to store a geographic point and the `geo_distance` query to filter documents within a distance from an origin point. When distance-based ranking is needed, you can combine it with geo distance sorting. In Spring Data Elasticsearch, the location property can be declared with `@GeoPointField`, and queries can be built using the Elasticsearch Java API Client DSL and attached to `NativeQuery`.

A typical nearby search has two logical steps:

1. **Filter by radius:** keep only stores within range, for example 10 km from the user's location.
2. **Sort by distance:** nearest places appear first.

```text
Origin location (latitude, longitude)
              |
              v
       geo_distance query
       distance = 10 km
              |
              v
     Keep only places within radius
              |
              v
       geo distance sort
         nearest first
              |
              v
       Pageable / page size
              |
              v
       SearchHits<Store>
```

## 1. What is `geo_point`?

`geo_point` is an Elasticsearch field type used to store a coordinate pair consisting of latitude and longitude. It supports geospatial operations such as searching documents within a radius, sorting by distance, and certain geospatial aggregations.

Example of a store in Ho Chi Minh City:

```json
{
  "store_id": "SG-001",
  "name": "Central Store",
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
```

Where:

- `lat` is latitude, ranging from -90 to 90 degrees.
- `lon` is longitude, ranging from -180 to 180 degrees.
- `location` must be mapped as `geo_point` to use geo distance query/sort.

If the field is mapped as a regular `object`, Elasticsearch does not automatically treat the number pair as a geographic point. The `geo_distance` query requires a field with an appropriate geospatial type.

### 1.1. Coordinate formats accepted by Elasticsearch

Elasticsearch can accept a geo point in several common forms:

**Object with lat/lon:**

```json
{ "lat": 10.7769, "lon": 106.7009 }
```

**`latitude,longitude` string:**

```json
"10.7769,106.7009"
```

**Coordinate array:**

```json
[106.7009, 10.7769]
```

Arrays follow longitude-first, latitude-second order, matching the GeoJSON coordinate convention. This is a frequent source of bugs because many Java APIs take two parameters `lat, lon`, whereas Elasticsearch/GeoJSON arrays are `[lon, lat]`.

**GeoJSON Point:**

```json
{
  "type": "Point",
  "coordinates": [106.7009, 10.7769]
}
```

When exchanging data between Spring, Elasticsearch, GeoJSON, and mapping services, explicitly define the format and coordinate order at each boundary.

## 2. Declaring `geo_point` in the mapping

You can declare the mapping directly in Elasticsearch:

```json
PUT /stores
{
  "mappings": {
    "properties": {
      "store_id": {
        "type": "keyword"
      },
      "name": {
        "type": "text",
        "fields": {
          "keyword": { "type": "keyword" }
        }
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
```

In Spring Data Elasticsearch, you can use `@GeoPointField`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.GeoPointField;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Document(indexName = "stores")
public class StoreDocument {

    @Id
    private String id;

    @Field(name = "store_id", type = FieldType.Keyword)
    private String storeId;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Boolean)
    private boolean active;

    @GeoPointField
    private GeoPoint location;

    // constructors, getters, setters
}
```

`@GeoPointField` tells Spring Data that the property should map to `geo_point`. Spring Data Elasticsearch's `GeoPoint` type represents latitude and longitude coordinates.

Example creating an entity:

```java
StoreDocument store = new StoreDocument();
store.setId("SG-001");
store.setStoreId("SG-001");
store.setName("Central Store");
store.setActive(true);
store.setLocation(new GeoPoint(10.7769, 106.7009));
```

The constructor parameters in this example are latitude first, longitude second. When calling other APIs or building GeoJSON arrays, convert to the exact order required by that API.

### 2.1. Inspecting the mapping after index creation

You can read the mapping:

```http
GET /stores/_mapping
```

The result should show:

```json
{
  "properties": {
    "location": {
      "type": "geo_point"
    }
  }
}
```

If the index already exists with `location` as `object` or an incompatible type, merely adding the annotation to the entity does not change the existing index mapping. You must create a new index with the right mapping and reindex the data. You cannot change an existing field's type directly from `object` to `geo_point` in an active mapping.

## 3. `geo_distance` query

The `geo_distance` query finds documents that have at least one geo point value within a specified distance from an origin point.

Example finding stores within a 5 km radius around coordinates:

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

Key parts:

- `distance`: search radius, e.g. `500m`, `5km`, `3mi`.
- `location`: `geo_point` field in the mapping.
- `lat` and `lon`: origin coordinates serving as the center of the search area.

The query matches documents whose location lies within the radius. Documents without a valid `location` value generally do not match this condition.

### 3.1. Distance units

Elasticsearch supports multiple distance units; commonly used ones include:

| Unit | Symbol |
|---|---|
| Kilometre | `km` |
| Metre | `m` |
| Centimetre | `cm` |
| Millimetre | `mm` |
| Mile | `mi` |
| Yard | `yd` |
| Foot | `ft` |
| Nautical mile | `nmi` |

Use explicit units in requests for readability and to avoid ambiguity. For instance, `distance: "5000m"` and `distance: "5km"` specify the same radius.

### 3.2. Combining searches with business conditions

Nearby search often needs additional filtering on status or place type:

```json
GET /stores/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "active": true
          }
        },
        {
          "term": {
            "category": "GROCERY"
          }
        },
        {
          "geo_distance": {
            "distance": "5km",
            "location": {
              "lat": 10.7769,
              "lon": 106.7009
            }
          }
        }
      ]
    }
  }
}
```

Here all three conditions are filter criteria: the store must be active, belong to the grocery category, and lie within a 5 km radius. Placing `geo_distance` in a filter context is appropriate when distance only decides whether a document appears in results.

If you want to use distance as a relevance signal, you can design custom scoring such as `distance_feature` or `function_score`. Do not expect a `geo_distance` filter to automatically rank closer stores first.

## 4. `geo_distance` query does not automatically sort nearest-first

A common mistake is assuming `geo_distance` query results are automatically returned in ascending distance order. The query only determines which documents fall within the radius; the default search order still follows relevance score or the request's sort specification.

To put the nearest stores first, add a geo distance sort:

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
```

`order: "asc"` puts smaller distances first. `unit: "km"` specifies the unit of sort distance in the response. `distance_type: "arc"` uses arc distance on a spherical surface; this is a suitable default for most nearby searches.

If you only use geo sort without a geo distance query, the request can sort documents by distance while still returning very distant places. Therefore, when the UI requires "within 5 km and nearest first," you need both a radius filter and a sort.

### 4.1. Adding a tie-breaker for stable ordering

Two stores may be nearly equidistant from the origin. If you sort solely by distance, the order among documents with equal sort values may be unstable across requests.

You can add a unique field with doc values and a `keyword` mapping as a tie-breaker:

```json
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
    "store_id": "asc"
  }
]
```

The `store_id` field must have stable, unique values across the relevant result set. Do not assume `_id` can be used as an ordinary sort field.

## 5. Geo distance sort with multi-location documents

A `geo_point` field can hold multiple coordinates. For instance, a delivery provider might have multiple service points or an asset might have multiple recorded locations.

```json
{
  "service_id": "S-100",
  "locations": [
    { "lat": 10.77, "lon": 106.70 },
    { "lat": 10.80, "lon": 106.68 }
  ]
}
```

A geo distance query matches the document if a qualifying geo point value lies within the radius. With geo distance sort, you can choose how distances across multiple points are combined using `mode`, for example:

- `min`: shortest distance among the document's points.
- `max`: longest distance.
- `avg`: average distance.
- `median`: median distance.

For finding the nearest provider, `min` is usually the sensible choice because the document is ranked by its closest service point. Configure the mode explicitly whenever a document holds multiple coordinates and business logic depends on that calculation.

## 6. `distance_type`: arc and plane

Geo distance queries/sorts can use different distance calculation methods:

- `arc`: calculates distance along an arc on a spherical surface. Suitable for most geographic applications and real-world distances.
- `plane`: uses a flat-plane approximation. Can be faster in certain small-scale cases, but error grows at large distances or high latitudes.

Unless you have benchmarked reasons to choose plane, stick with the default arc. Do not switch to plane solely for performance optimization without comparing results across your application's actual region and distances.

Distances returned by Elasticsearch are geographic distances under Elasticsearch's computation model, not driving distance, walking path, or travel time. If your product requires "nearest by road," use an external routing/directions service; geo distance only measures straight-line ("as the crow flies") distance.

## 7. `geo_distance` query with Spring Data Elasticsearch

With modern Spring Data Elasticsearch, you can build a `geo_distance` query using the Elasticsearch Java API Client DSL and attach it to `NativeQuery`.

Example finding stores within 5 km:

```java
import co.elastic.clients.elasticsearch._types.GeoLocation;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

public SearchHits<StoreDocument> findNearby(
        double latitude,
        double longitude,
        String radius) {

    Query geoQuery = Query.of(q -> q
            .geoDistance(g -> g
                    .field("location")
                    .distance(radius)
                    .location(GeoLocation.of(l -> l
                            .latlon(point -> point
                                    .lat(latitude)
                                    .lon(longitude)
                            )
                    ))
            )
    );

    NativeQuery query = NativeQuery.builder()
            .withQuery(geoQuery)
            .build();

    return operations.search(query, StoreDocument.class);
}
```

In this code:

- `field("location")` is the name of the `geo_point` field in the Elasticsearch mapping.
- `distance(radius)` accepts a string with a unit such as `"5km"` or `"500m"`.
- `GeoLocation.latlon(...)` constructs the origin point with latitude and longitude.
- `NativeQuery` wraps the Elasticsearch Java API Client Query DSL.
- `ElasticsearchOperations.search(...)` executes the query and maps results into `StoreDocument`.

This is the Elasticsearch Java API Client API used by Spring Data Elasticsearch 5.x. Exact packages and overloads must match your project's Spring Data/Java API Client versions.

### 7.1. Combining business filters

Example fetching only active stores within the radius:

```java
Query nearbyActiveStores = Query.of(q -> q
        .bool(b -> b
                .filter(f -> f.term(t -> t
                        .field("active")
                        .value(true)
                ))
                .filter(f -> f.geoDistance(g -> g
                        .field("location")
                        .distance("5km")
                        .location(GeoLocation.of(l -> l
                                .latlon(ll -> ll
                                        .lat(10.7769)
                                        .lon(106.7009)
                                )
                        ))
                ))
        )
);

NativeQuery query = NativeQuery.builder()
        .withQuery(nearbyActiveStores)
        .build();
```

Placing the geo query inside `filter` indicates that distance is a boolean yes/no condition. If you also need store name search with relevance scoring, place `match` in `must` and keep the active/geo conditions in `filter`.

## 8. Combining text search and nearby search

An application may let users search for "pharmacy" around their current location. In that case:

- `match` on place name/category determines keyword relevance.
- `term` on status ensures only active places are returned.
- `geo_distance` restricts the radius.
- Geo distance sort prioritizes the nearest places.

Query DSL example:

```json
GET /places/_search
{
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "pharmacy",
            "fields": ["name^2", "category"]
          }
        }
      ],
      "filter": [
        { "term": { "active": true } },
        {
          "geo_distance": {
            "distance": "3km",
            "location": {
              "lat": 10.7769,
              "lon": 106.7009
            }
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
    },
    { "place_id": "asc" }
  ]
}
```

In this example, geo sort comes first, so distance dictates the primary order. If you want relevance to decide first and distance only as a tie-breaker, place `_score` before the geo sort:

```json
"sort": [
  { "_score": "desc" },
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
  { "place_id": "asc" }
]
```

Sort order must reflect UX: "nearest" and "most relevant" are two different goals. If you sort by distance first, a weak keyword match that is close can rank ahead of an excellent match further away.

## 9. Geo distance sort in Spring Data `NativeQuery`

The Elasticsearch Java API Client provides `SortOptions` for geo distance sorting. You can build a sort by origin coordinates, unit, and ascending direction:

```java
import co.elastic.clients.elasticsearch._types.DistanceUnit;
import co.elastic.clients.elasticsearch._types.GeoDistanceType;
import co.elastic.clients.elasticsearch._types.GeoLocation;
import co.elastic.clients.elasticsearch._types.SortMode;
import co.elastic.clients.elasticsearch._types.SortOptions;
import co.elastic.clients.elasticsearch._types.SortOrder;

SortOptions nearestFirst = SortOptions.of(s -> s
        .geoDistance(g -> g
                .field("location")
                .location(GeoLocation.of(l -> l
                        .latlon(point -> point
                                .lat(10.7769)
                                .lon(106.7009)
                        )
                ))
                .order(SortOrder.Asc)
                .unit(DistanceUnit.Kilometers)
                .distanceType(GeoDistanceType.Arc)
                .mode(SortMode.Min)
        )
);

NativeQuery query = NativeQuery.builder()
        .withQuery(nearbyActiveStores)
        .withSort(nearestFirst)
        .withPageable(PageRequest.of(0, 20))
        .build();
```

`SortMode.Min` picks the smallest distance when a document has multiple geo points. For single-valued fields, this mode does not change results. If the builder API in your version uses a different overload for a list of `SortOptions`, use the corresponding overload; the principle is that sorts are added to `NativeQuery` before calling `operations.search`.

When a tie-breaker is needed, add a deterministic field sort after the geo sort, such as `store_id` of type `keyword`. This is especially useful when paginating with `search_after`.

## 10. Reading distance from search results

Geo distance sort normally returns the distance value inside each hit's `sort` array. If the request sorts by `_geo_distance`, the response might look like:

```json
{
  "_id": "SG-001",
  "_source": {
    "name": "Central Store",
    "location": {
      "lat": 10.7769,
      "lon": 106.7009
    }
  },
  "sort": [
    0.42,
    "SG-001"
  ]
}
```

The first value is the distance in the unit chosen for the geo sort, e.g. kilometers; the second value is the `store_id` tie-breaker.

In Spring Data Elasticsearch, `SearchHit<T>` exposes hit sort values according to your version's API. You can read `SearchHit.getSortValues()` to construct a DTO containing the distance:

```java
SearchHits<StoreDocument> hits = operations.search(query, StoreDocument.class);

List<NearbyStore> results = hits.getSearchHits().stream()
        .map(hit -> {
            Object distance = hit.getSortValues().get(0);
            return new NearbyStore(
                    hit.getContent(),
                    ((Number) distance).doubleValue()
            );
        })
        .toList();
```

This example assumes geo distance is the first sort value and the unit is kilometers. If you change the sort order or add another sort field before geo distance, the list index changes. Encapsulate this rule in a mapper/service rather than letting controllers hardcode positional indices.

If the application needs distances without sorting by geo distance, you can use `script_fields` or an appropriate distance calculation mechanism, though geo distance sort is usually convenient because it both ranks and returns the sort value.

## 11. Paginating nearby searches

Nearby search typically returns a list of the closest places, so you can use `Pageable` with geo distance sort:

```java
Pageable pageable = PageRequest.of(
        0,
        20
);

NativeQuery query = NativeQuery.builder()
        .withQuery(nearbyActiveStores)
        .withSort(nearestFirst)
        .withPageable(pageable)
        .build();
```

`PageRequest` uses 0-based page indexing. For page 0 with size 20, Elasticsearch fetches the 20 nearest places according to the geo sort.

### 11.1. Stable sorting when distances tie

If multiple places have identical distances after rounding or equal sort values, add a unique tie-breaker field. Otherwise, moving between pages can produce unstable ordering among tied documents.

### 11.2. Deep pagination

`from/size` is unsuitable for paging deeply through hundreds of thousands of places. For large lists, use `search_after` with a stable sort. If data can change while the user pages through results, combine it with Point in Time (PIT) to preserve a consistent search view.

With PIT, the sort must produce deterministic values. You can use geo distance first, a unique business ID as a tie-breaker, and `_shard_doc` when using PIT as recommended by Elasticsearch. Take the `sort` array from the last hit of the previous page and pass it unchanged into `search_after` on the next request.

## 12. Validating coordinate and radius inputs

Do not pass raw client values directly into geo queries. The service should validate:

- Latitude lies within `[-90, 90]`.
- Longitude lies within `[-180, 180]`.
- Radius is positive.
- Distance unit belongs to the set supported by the API.
- Radius does not exceed allowed business limits.
- Values are not `NaN`, infinite, or unparseable strings.

Validation example:

```java
public record Coordinates(double latitude, double longitude) {

    public Coordinates {
        if (!Double.isFinite(latitude)
                || latitude < -90 || latitude > 90) {
            throw new IllegalArgumentException("Invalid latitude");
        }

        if (!Double.isFinite(longitude)
                || longitude < -180 || longitude > 180) {
            throw new IllegalArgumentException("Invalid longitude");
        }
    }
}
```

For radius, parse into an internal data type or use a unit enum rather than concatenating arbitrary strings from the client. For example, if the API only permits `500m`, `1km`, `3km`, `5km`, and `10km`, the service should whitelist those options.

Do not assume the current location sent by a browser/mobile client is always accurate. If location permission is denied or data is unavailable, prompt the user to enter an address or pick a point on the map.

## 13. Searching around an address: geocoding and geo distance are two separate steps

Users often enter an address such as "District 1, Ho Chi Minh City" rather than coordinates. Elasticsearch geo distance queries require coordinates, so applications typically have two steps:

1. Use a geocoding service to convert the address into latitude/longitude.
2. Use a `geo_distance` query to find documents around those coordinates.

Geocoding is not a feature of the `geo_distance` query. It is a separate step that can use a mapping service or internal address data. Store geocoded coordinates for fixed places to avoid repeatedly calling the geocoder on every search.

If the geocoder returns multiple candidates, choose the right match or ask the user to confirm. Coordinates off by a few kilometers can significantly skew nearby search results.

## 14. Missing fields, multiple locations, and nested locations

### Missing location field

Documents without a valid location cannot participate in ordinary geo distance queries. If location data is required, validate before indexing. If location is optional, you can add an `exists` filter to exclude documents missing locations or let the geo query exclude them naturally.

### Multiple geo points on a single document

If a property holds multiple geo points, the query can match when any point falls within the radius. Geo sort needs `mode` to decide how distances across points are combined. For "nearest place," `min` is typically used.

### Geo point inside a nested object

If coordinates reside inside a nested object, you need a nested mapping and a nested query with the corresponding path. For instance, a document representing a business with multiple branches, each having its own location and status. With an ordinary object mapping, conditions across array elements can cross-match. With a nested mapping, the query traverses the exact path and sorting may need a nested sort filter/path matching the data structure.

Do not use nested just because a document has a `geo_point`. Only use nested when each object element in an array needs to preserve independent relationships between its location and its other fields.

## 15. Accuracy notes and the meaning of distance

Geo distance measures geographic distance between coordinates, commonly called straight-line ("as the crow flies") distance. It does not account for:

- Walking paths or driving roads.
- Rivers, bridges, one-way streets, or barriers.
- Traffic-adjusted travel times.
- User accessibility.
- Actual walking distance inside multi-story buildings.

If users need the nearest store by travel path, use a routing engine or directions API to calculate route distance/time. Elasticsearch can pre-filter candidates within a straight-line radius, and then the application calls the routing service for that small candidate set.

For areas near the international date line or near the poles, Elasticsearch handles geographic coordinates according to its geo model; applications should not compute distances manually using Euclidean formulas on latitude/longitude. If calculating in the service, use an appropriate geographic formula and handle longitude wrap-around.

## 16. Geo distance aggregation by distance bands

Beyond queries, Elasticsearch also offers `geo_distance` aggregations to bucket documents by distance from an origin point. This is useful when a dashboard needs to show how many places lie within 1 km, 1–5 km, or beyond 5 km.

Example:

```json
GET /stores/_search
{
  "size": 0,
  "aggs": {
    "distance_bands": {
      "geo_distance": {
        "field": "location",
        "origin": {
          "lat": 10.7769,
          "lon": 106.7009
        },
        "unit": "km",
        "ranges": [
          { "to": 1 },
          { "from": 1, "to": 5 },
          { "from": 5 }
        ]
      },
      "aggs": {
        "average_rating": {
          "avg": {
            "field": "rating"
          }
        }
      }
    }
  }
}
```

Each distance bucket has a `doc_count` and the sub-metric `average_rating`. This is an aggregation for distribution analysis, not a replacement for the `geo_distance` query when you need to restrict returned hits.

## 17. Complete Spring Data service example

The following example combines coordinate validation, active-store filtering, radius filtering, and nearest-first sorting. To keep the focus on geo search, radius is passed as a string validated at the service layer.

```java
import co.elastic.clients.elasticsearch._types.DistanceUnit;
import co.elastic.clients.elasticsearch._types.GeoDistanceType;
import co.elastic.clients.elasticsearch._types.GeoLocation;
import co.elastic.clients.elasticsearch._types.SortMode;
import co.elastic.clients.elasticsearch._types.SortOptions;
import co.elastic.clients.elasticsearch._types.SortOrder;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.stereotype.Service;

@Service
public class NearbyStoreService {

    private final ElasticsearchOperations operations;

    public NearbyStoreService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<StoreDocument> findNearby(
            double latitude,
            double longitude,
            String radius,
            int page,
            int size) {

        Coordinates origin = new Coordinates(latitude, longitude);
        validateRadius(radius);

        GeoLocation point = GeoLocation.of(l -> l.latlon(ll -> ll
                .lat(origin.latitude())
                .lon(origin.longitude())
        ));

        Query queryDsl = Query.of(q -> q
                .bool(b -> b
                        .filter(f -> f.term(t -> t
                                .field("active")
                                .value(true)
                        ))
                        .filter(f -> f.geoDistance(g -> g
                                .field("location")
                                .distance(radius)
                                .location(point)
                        ))
                )
        );

        SortOptions distanceSort = SortOptions.of(s -> s
                .geoDistance(g -> g
                        .field("location")
                        .location(point)
                        .order(SortOrder.Asc)
                        .unit(DistanceUnit.Kilometers)
                        .distanceType(GeoDistanceType.Arc)
                        .mode(SortMode.Min)
                )
        );

        NativeQuery query = NativeQuery.builder()
                .withQuery(queryDsl)
                .withSort(distanceSort)
                .withPageable(PageRequest.of(page, size))
                .build();

        return operations.search(query, StoreDocument.class);
    }

    private void validateRadius(String radius) {
        // Parse and whitelist supported values, for example 500m, 1km, 3km, 5km.
        if (radius == null || radius.isBlank()) {
            throw new IllegalArgumentException("Radius is required");
        }
    }
}
```

This is a service structure template; `Coordinates` is the validation record presented earlier. In production code, use a structured radius type instead of only checking for blank strings. If a tie-breaker is needed, add a stable sort field after the geo sort using your `NativeQuery` version's API.

## 18. Testing nearby search

Use integration tests with a real Elasticsearch cluster or Testcontainers to verify the `geo_point` mapping, distances, and sorting. Mocking `ElasticsearchOperations` only confirms that the service issues the call, not Elasticsearch's geospatial behavior.

A simple fixture set:

| ID | Latitude | Longitude | Meaning |
|---|---:|---:|---|
| S1 | 10.7769 | 106.7009 | Origin point. |
| S2 | 10.7800 | 106.7009 | Close to origin. |
| S3 | 10.8200 | 106.7009 | Farther away. |
| S4 | 10.7769 | 106.7600 | To the east. |
| S5 | 10.7769 | 106.7009 | Same coordinates as origin, but inactive. |

Tests should verify:

1. The origin point is included within a small radius.
2. Closer points are returned before farther points under ascending geo sort.
3. Points outside the radius are excluded.
4. Inactive stores are excluded by business filters.
5. Swapped latitude/longitude coordinates produce different results or are rejected by validation if out of range.
6. Documents missing location do not appear.
7. Sort tie-breaker preserves stable ordering when two documents have the same distance.
8. Page 0 and page 1 do not duplicate documents when data and snapshot are stable.
9. Multi-valued geo points use the selected `mode` properly.

Exact fixture distances depend on Elasticsearch's geospatial calculation. Tests should verify ordering and inside/outside inclusion using well-separated points, avoiding razor-thin boundary thresholds affected by floating-point error.

## 19. Common mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| `geo_distance` reports field is not geo_point | Wrong field mapping or old index created before annotation | Check mapping and create/reindex with `geo_point`. |
| Nearby results are in the wrong area | Swapped latitude and longitude | Use `lat, lon` for objects/APIs; remember GeoJSON arrays are `[lon, lat]`. |
| Query returns farthest places first | Only used `geo_distance` query without adding geo distance sort | Add `_geo_distance` sort with `order: asc`. |
| Sorted nearest-first but still returns out-of-radius places | Has geo sort without geo distance filter | Use both radius filter query and sort. |
| Distances display wrong unit | Omitted `unit` or mapper misread sort value | Set unit explicitly and document the unit in the DTO. |
| Straight-line search when users expect road distance | Geo distance does not compute routing or traffic | Use a routing/directions service for route distance/time. |
| Duplicate items or shifting order across pages | Sort lacks tie-breaker or data changed between requests | Add a unique sort field; use PIT + `search_after` when snapshots are needed. |
| Multi-location document ranked by unexpected point | Unsuitable geo sort mode | Choose `min`, `max`, `avg`, or the mode matching business semantics. |
| Places missing coordinates are not found | Geo distance query does not match documents missing geo point | Populate location data or handle locationless documents separately. |
| Query is slow when radius is too large | Candidate set too broad or combined with costly conditions | Cap radius, add selective filters, and benchmark. |

## 20. Design principles

- Map location fields as `geo_point`; in Spring Data use `@GeoPointField`.
- Standardize coordinate order: Java APIs typically take latitude before longitude; GeoJSON arrays take longitude before latitude.
- Validate latitude, longitude, and radius before constructing queries.
- Use `geo_distance` query to bound the radius.
- Use geo distance sort with `asc` to bring the nearest places first.
- Do not confuse radius filter queries with distance sorting; the two operations serve separate roles.
- Place geo filters in the filter context when distance is purely a yes/no condition.
- Choose `arc` in most cases; use `plane` only after measuring and accepting the error.
- With multiple geo points, choose the appropriate `mode`, usually `min` for the nearest point.
- Add a unique tie-breaker for stable pagination.
- Use `NativeQuery` and the Elasticsearch Java API Client DSL when building geo queries/sorts in modern Spring Data Elasticsearch.
- Use geocoding to convert addresses into coordinates; geo distance queries do not geocode automatically.
- Use a routing service when road distance or travel time is needed.

## 21. Key takeaways

- `geo_point` stores latitude/longitude and is the required mapping type for geo distance queries and sorts.
- `@GeoPointField` maps the location property in a Spring Data Elasticsearch entity.
- `geo_distance` query filters documents within a radius from an origin point.
- Queries do not sort by distance automatically; you must add a `_geo_distance` sort.
- `order: asc` puts the nearest places first; set `unit` explicitly to interpret sort values.
- `arc` is the suitable default for most geospatial searches; `plane` is an approximation.
- `mode: min` is usually right when a document has multiple locations and the shortest distance is needed.
- GeoJSON coordinates use `[longitude, latitude]` order; `lat/lon` objects name fields explicitly, reducing ambiguity.
- Spring Data Elasticsearch can build geo queries via the Java API Client DSL, attach them to `NativeQuery`, and execute via `ElasticsearchOperations`.
- Geo distance is straight-line distance, not route distance or travel time.
- Use a tie-breaker and PIT + `search_after` when stable deep pagination is required.

The geo distance query is the foundation for nearby search in Spring Data Elasticsearch. Store locations as `geo_point`, filter by an appropriate radius, sort separately by distance, and validate coordinates at the API boundary. Combining query, sort, and pagination properly enables applications to return nearest places consistently and reliably.

## References

- [Elasticsearch — Geo-point field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/geo-point.html)
- [Elasticsearch — Geo-distance query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-geo-distance-query.html)
- [Elasticsearch — Sort search results by geographic distance](https://www.elastic.co/guide/en/elasticsearch/reference/current/sort-search-results.html#geo-sorting)
- [Elasticsearch Java API Client — Query DSL](https://www.elastic.co/guide/en/elasticsearch/client/java-api-client/current/query.html)
- [Spring Data Elasticsearch — Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)