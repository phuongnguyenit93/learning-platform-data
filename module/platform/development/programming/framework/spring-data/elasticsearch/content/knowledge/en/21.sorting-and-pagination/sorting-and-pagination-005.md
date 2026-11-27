# Geo Distance Sort and Distance-Based Ordering

Elasticsearch can sort search results by the distance between a reference location and each document's geographic field. This feature is commonly used for nearest-location search, stores around a user, delivery stations, hospitals, or devices near a coordinate. In Query DSL, this sort type is named `_geo_distance`.

Spring Data Elasticsearch provides `GeoDistanceOrder`, a specialized `Sort.Order` implementation for passing geo distance sorting into `Sort`, `Pageable`, or repository methods. When advanced Query DSL options are needed, the Elasticsearch Java API Client or REST API still allows direct control of the request.

This lesson explains how to map `geo_point`, how distances are computed and sorted, the `unit`, `distance_type`, `mode`, and `order` options, how to handle documents lacking coordinates, how to use `GeoDistanceOrder` in Spring Data, and how to paginate stably when results share the same distance.

## 1. What Is Geo Distance Sort Used For?

Suppose an index `places` stores locations along with coordinates. An application wants to find places matching business conditions and display the ones closest to a center point first.

For example:

- The user picks their current location on a map.
- The application searches for active stores.
- Results are sorted by distance from the user's location to each store.
- The nearest store appears at the top of the list.

Geo distance sort **orders documents that already match the query** by distance. It does not automatically restrict results within a radius. If you only want places within 5 km, you must combine it with a `geo_distance` query.

```text
Reference location
       |
       v
Compute distance to each document's location
       |
       v
Sort by distance ascending
       |
       v
Nearest place comes first
```

## 2. Mapping `geo_point` for Locations

Geo distance sort typically operates on an Elasticsearch field of type `geo_point`. This type stores a point on Earth's surface using latitude and longitude in the WGS-84 coordinate system.

Example mapping:

```http
PUT places
{
  "mappings": {
    "properties": {
      "name": {
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
```

Documents can be indexed with object-formatted coordinates:

```http
PUT places/_doc/place-1
{
  "name": "Central Store",
  "active": true,
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
```

Latitude ranges from -90 to 90; longitude ranges from -180 to 180.

### 2.1. Coordinate Formats Accepted by Elasticsearch

A `geo_point` can be supplied in several formats:

| Format | Example | Order |
|---|---|---|
| Object | `{"lat": 10.7769, "lon": 106.7009}` | Explicit `lat`, `lon` |
| Array | `[106.7009, 10.7769]` | `[lon, lat]` |
| String | `"10.7769,106.7009"` | `lat,lon` |
| GeoJSON Point | `{"type":"Point","coordinates":[106.7009,10.7769]}` | `[lon, lat]` |
| WKT | `"POINT (106.7009 10.7769)"` | `POINT(lon lat)` |
| Geohash | `"w3gvk"` | Encoded location |

The easiest mistake is coordinate order: Spring Data's `GeoPoint` constructor takes latitude before longitude, whereas arrays, GeoJSON, and WKT use longitude before latitude.

### 2.2. Spring Data Elasticsearch Entity

Spring Data Elasticsearch provides the `GeoPoint` class in package `org.springframework.data.elasticsearch.core.geo` and the `@GeoPointField` annotation:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.GeoPointField;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Document(indexName = "places")
public class Place {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String name;

    @Field(type = FieldType.Boolean)
    private boolean active;

    @GeoPointField
    private GeoPoint location;

    public Place() {
    }

    public Place(String id, String name, boolean active,
                 double latitude, double longitude) {
        this.id = id;
        this.name = name;
        this.active = active;
        this.location = new GeoPoint(latitude, longitude);
    }

    // Getters and setters
}
```

Creating a `GeoPoint`:

```java
GeoPoint origin = new GeoPoint(10.7769, 106.7009);
```

The first parameter is latitude, and the second parameter is longitude. Spring Data converts `GeoPoint` into a structure Elasticsearch understands for a `geo_point` field.

After creating the index, you can inspect the actual mapping:

```http
GET places/_mapping
```

If the `location` field is not mapped as `geo_point`, geo distance sorting will not work as expected. Changing an annotation does not alter the mapping of an existing index; when a field type needs to change, an index migration plan is required.

## 3. Geo Distance Sort in Elasticsearch Query DSL

Geo distance sort is declared in the `sort` array using the `_geo_distance` key.

Example sorting active stores closest to the reference coordinate first:

```http
GET places/_search
{
  "query": {
    "term": {
      "active": true
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

The query filters active stores. Elasticsearch computes the distance from the reference point to each document's `location` and sorts ascending in kilometers.

- `order: "asc"`: nearest first.
- `order: "desc"`: farthest first.
- `unit: "km"`: unit of the computed and returned distance value.
- `distance_type: "arc"`: computes great-circle arc distance across Earth's surface.

If `order` is omitted, sorting normally defaults to ascending; if `unit` is omitted, the default unit is meters. `distance_type` defaults to `arc`.

### 3.1. Representing the Reference Point

`_geo_distance` accepts the same coordinate formats as `geo_point` fields. Example array format:

```json
{
  "sort": [
    {
      "_geo_distance": {
        "location": [106.7009, 10.7769],
        "order": "asc",
        "unit": "km"
      }
    }
  ]
}
```

Arrays always use `[longitude, latitude]` per GeoJSON convention. When reading values directly from `GeoPoint(latitude, longitude)`, be careful not to accidentally swap the order when converting to an array.

WKT can also be used:

```json
{
  "sort": [
    {
      "_geo_distance": {
        "location": "POINT (106.7009 10.7769)",
        "order": "asc",
        "unit": "km"
      }
    }
  ]
}
```

In WKT, coordinates are also ordered as `longitude latitude`.

## 4. Distinguishing `geo_distance` Query and `_geo_distance` Sort

The two constructs have similar names but serve different functions:

| Construct | Location in request | Purpose |
|---|---|---|
| `geo_distance` | Inside `query` | Selects only documents within a maximum distance |
| `_geo_distance` | Inside `sort` | Orders matched documents by distance to a reference point |

Example fetching only stores within 10 km:

```http
GET places/_search
{
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
        "unit": "km"
      }
    }
  ]
}
```

Here `geo_distance` restricts the result set to within 10 km; `_geo_distance` orders those results by ascending distance. If you only declare the sort without a distance-limiting query, Elasticsearch can still return very distant documents as long as they match the main query.

## 5. Choosing `distance_type`: `arc` and `plane`

`distance_type` determines how distance between two coordinates is calculated:

| Value | Characteristics | When to use |
|---|---|---|
| `arc` | Computes arc distance on Earth's surface; default and more accurate | Real-world place search, medium/long distances, near poles |
| `plane` | Uses a planar approximation; can be faster but less accurate over long distances or near poles | Small ranges, benchmarked, where approximation error is acceptable |

For example:

```json
{
  "_geo_distance": {
    "location": [106.7009, 10.7769],
    "order": "asc",
    "unit": "km",
    "distance_type": "arc"
  }
}
```

For searching stores, services, or vehicles by geographic location, usually keep the default `arc`. Only switch to `plane` after benchmarking performance and confirming error bounds are acceptable for your data range.

## 6. Distance Units (`unit`)

Geo distance sort supports common distance units:

| Unit | Value |
|---|---|
| Millimeter | `mm` |
| Centimeter | `cm` |
| Meter | `m` or `meters` |
| Kilometer | `km` or `kilometers` |
| Inch | `in` or `inch` |
| Feet | `ft` or `feet` |
| Yard | `yd` or `yards` |
| Mile | `mi` or `miles` |
| Nautical mile | `nmi`, `NM`, or `nauticalmiles` |

If `unit` is not set, Elasticsearch uses meters. Choose a unit aligned with business requirements and keep it consistent across sort APIs, UI display, and tests.

Example using miles:

```json
{
  "_geo_distance": {
    "location": {
      "lat": 40.7128,
      "lon": -74.0060
    },
    "order": "asc",
    "unit": "mi"
  }
}
```

The unit in the sort determines the unit of the returned sort value. If distance needs to be displayed to users, you can read the sort value and format it per the API contract instead of recomputing distances in the application.

## 7. Fields with Multiple Geo Points and `mode`

A document can contain multiple coordinates in a single `geo_point` field, such as a retail chain with multiple branches or an entity with multiple related locations.

Document:

```json
{
  "name": "Retail Network",
  "locations": [
    { "lat": 10.7769, "lon": 106.7009 },
    { "lat": 10.8000, "lon": 106.6500 },
    { "lat": 10.7500, "lon": 106.7200 }
  ]
}
```

When sorting, Elasticsearch must select a single representative distance for the document. The `mode` parameter controls how it is selected:

| Mode | Meaning |
|---|---|
| `min` | Smallest distance |
| `max` | Largest distance |
| `avg` | Average of distances |
| `median` | Median of distances |

Defaults:

- Ascending sort (`asc`) chooses the smallest distance (`min`), evaluating each document by its nearest point.
- Descending sort (`desc`) chooses the largest distance (`max`).

Example choosing the nearest point of each document:

```json
{
  "sort": [
    {
      "_geo_distance": {
        "locations": [106.7009, 10.7769],
        "order": "asc",
        "unit": "km",
        "mode": "min"
      }
    }
  ]
}
```

If you want to rank a store chain by average distance from the user to its branches, you can use `mode: "avg"`. If you want documents whose points are all far away, consider `mode: "max"` combined with ascending or descending sort depending on the goal.

### 7.1. Multiple Reference Points

Elasticsearch also allows passing multiple reference points in an array:

```json
{
  "sort": [
    {
      "_geo_distance": {
        "locations": [
          [106.7009, 10.7769],
          [106.6500, 10.8000]
        ],
        "order": "asc",
        "unit": "km",
        "mode": "min"
      }
    }
  ]
}
```

Elasticsearch calculates distances between the document's points and the reference points, then applies `mode` to obtain the final sort value. This is useful when a user has multiple starting points or a query needs comparison against multiple hubs.

Spring Data's `GeoDistanceOrder` has a constructor accepting a single `GeoPoint` as the reference point. If you need to pass multiple reference points or more complex geo distance sort structures, use `NativeQuery` / Elasticsearch Java API Client or the REST API directly.

## 8. Handling Documents Missing Coordinates and Unmapped Fields

Not every document has a `location`. Distinguish two situations:

1. The field is mapped as `geo_point`, but a document has no coordinate value.
2. One of the indices being searched lacks a mapping for the sorted field.

### 8.1. Documents Without a Geo Point Value

Geo distance sort does not support `missing` configuration like regular field sorting. A document without coordinates is treated as having distance `Infinity`.

Consequences:

- With `order: "asc"`, documents without coordinates typically appear last because infinite distance is greater than real distances.
- With `order: "desc"`, documents without coordinates may appear first because infinite distance is largest.

If business logic requires excluding documents without locations altogether, add an `exists` condition in the query:

```json
{
  "query": {
    "bool": {
      "filter": [
        { "term": { "active": true } },
        { "exists": { "field": "location" } }
      ]
    }
  }
}
```

### 8.2. Field Unmapped in an Index

When searching across multiple indices, one index may not have a mapping for `location`. By default, Elasticsearch may reject the sort request if the field is unmapped. Use `ignore_unmapped: true` to treat unmapped fields as missing values:

```json
{
  "_geo_distance": {
    "location": [106.7009, 10.7769],
    "order": "asc",
    "unit": "km",
    "ignore_unmapped": true
  }
}
```

`ignore_unmapped` defaults to `false`. Enable it when querying across multiple indices with differing schemas and you accept treating documents from an index missing the field as having no location.

Do not confuse `ignore_unmapped` with tolerating malformed coordinate data. It does not replace latitude/longitude validation or `geo_point` mapping.

## 9. Multi-Criteria Sorting and Combining with `_score`

Elasticsearch processes elements in the `sort` array in order. Subsequent criteria are only used when documents tie on prior criteria.

For example:

```json
{
  "track_scores": true,
  "sort": [
    {
      "_geo_distance": {
        "location": [106.7009, 10.7769],
        "order": "asc",
        "unit": "km"
      }
    },
    { "_score": "desc" },
    { "name.keyword": "asc" }
  ],
  "query": {
    "match": {
      "name": "coffee shop"
    }
  }
}
```

Priority order:

1. Closer locations come first.
2. If distances are equal, documents with higher `_score` come first.
3. If both distance and score are equal, ascending name is used as the next criterion.

When sorting by fields, Elasticsearch does not compute scores by default. `track_scores: true` requests computing and retaining `_score` if needed as a secondary criterion or for display. If sorting solely by distance without using scores, there is no need to enable `track_scores`.

Fields used for regular secondary sorting should have `doc_values`; avoid sorting directly on `text` fields. To sort by name, use a `keyword` multi-field such as `name.keyword`.

## 10. Reading Sort Values in the Search Response

Each hit can contain a `sort` array corresponding to the sort criteria in the request:

```json
{
  "hits": {
    "hits": [
      {
        "_id": "place-1",
        "_source": {
          "name": "Central Store"
        },
        "sort": [0.42]
      },
      {
        "_id": "place-2",
        "_source": {
          "name": "West Store"
        },
        "sort": [1.85]
      }
    ]
  }
}
```

The values `0.42` and `1.85` illustrate distances in the request's `km` unit. If there are multiple sort criteria, the `sort` array contains one value per criterion in the declared order.

In Spring Data Elasticsearch, when using `SearchHits<T>`, each `SearchHit<T>` provides hit metadata. However, do not assume geo distance is populated into the entity; it is a sort value of the search hit. Read sort values from `SearchHit` metadata using the API of your Spring Data version if the application needs to display distance.

## 11. Using `GeoDistanceOrder` in Spring Data Elasticsearch

Spring Data Elasticsearch provides `org.springframework.data.elasticsearch.core.query.GeoDistanceOrder`, a subclass of `Order` designed for `_geo_distance` sorting. This API has been available since Spring Data Elasticsearch 4.0.

The constructor accepts:

- The name of the property holding the `GeoPoint`.
- The reference point of type `GeoPoint`.

Basic example per Spring Data documentation:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;
import org.springframework.data.elasticsearch.core.query.GeoDistanceOrder;

Sort distanceSort = Sort.by(
        new GeoDistanceOrder(
                "location",
                new GeoPoint(10.7769, 106.7009)));
```

A more complete example specifying direction and unit:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;
import org.springframework.data.elasticsearch.core.query.GeoDistanceOrder;
import org.springframework.data.elasticsearch.core.query.Order;

GeoDistanceOrder distanceOrder = new GeoDistanceOrder(
        "location",
        new GeoPoint(10.7769, 106.7009))
        .with(Sort.Direction.ASC)
        .withUnit("km")
        .with(GeoDistanceOrder.DistanceType.arc)
        .with(Order.Mode.min)
        .withIgnoreUnmapped(true);

Sort distanceSort = Sort.by(distanceOrder);
```

Key methods:

| Method | Purpose |
|---|---|
| `with(Sort.Direction.ASC)` | Nearest first |
| `with(Sort.Direction.DESC)` | Farthest first |
| `withUnit("km")` | Choose distance unit |
| `with(GeoDistanceOrder.DistanceType.arc)` | Compute arc distance |
| `with(GeoDistanceOrder.DistanceType.plane)` | Use planar approximation |
| `with(Order.Mode.min)` | Choose smallest distance when multiple points exist |
| `with(Order.Mode.max)` | Choose largest distance |
| `with(Order.Mode.avg)` | Choose average distance |
| `with(Order.Mode.median)` | Choose median distance |
| `withIgnoreUnmapped(true)` | Ignore indices lacking a mapping for the field |

Enum names in Spring Data's Java API are lowercase (`arc`, `plane`, `min`, `max`, `avg`, `median`), corresponding to Query DSL values.

### 11.1. Using `GeoDistanceOrder` in Repository Methods

Repositories can accept `Pageable` or `Sort` as dynamic parameters:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface PlaceRepository
        extends ElasticsearchRepository<Place, String> {

    Page<Place> findByActiveTrue(Pageable pageable);
}
```

Service creating a `Pageable` with geo distance sort:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

import org.springframework.data.elasticsearch.core.geo.GeoPoint;
import org.springframework.data.elasticsearch.core.query.GeoDistanceOrder;

@Service
public class NearbyPlaceService {

    private final PlaceRepository repository;

    public NearbyPlaceService(PlaceRepository repository) {
        this.repository = repository;
    }

    public Page<Place> findNearestPlaces() {
        GeoDistanceOrder order = new GeoDistanceOrder(
                "location",
                new GeoPoint(10.7769, 106.7009))
                .with(Sort.Direction.ASC)
                .withUnit("km");

        Pageable pageable = PageRequest.of(
                0,
                20,
                Sort.by(order));

        return repository.findByActiveTrue(pageable);
    }
}
```

`PageRequest` combines page position, page size, and `Sort`. Spring Data translates `GeoDistanceOrder` into a geo distance sort in the search request.

### 11.2. Needing Only `Sort`, Without `Page`

If total page metadata is not required, a repository method can accept `Sort` and return `List`:

```java
List<Place> findByActiveTrue(Sort sort);
```

Invocation:

```java
List<Place> places = repository.findByActiveTrue(
        Sort.by(new GeoDistanceOrder(
                "location",
                new GeoPoint(10.7769, 106.7009))
                .with(Sort.Direction.ASC)
                .withUnit("km")));
```

Choose `List` when only a reasonably bounded result set is needed. If using `Page`, Spring Data must provide total element/page information and may have to execute an additional count query. If the UI only needs to know whether a next page exists, consider `Slice`.

### 11.3. Using `ElasticsearchOperations`

For queries more complex than repository methods, you can attach `Sort` to a query object and execute it via `ElasticsearchOperations`:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.GeoDistanceOrder;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

GeoDistanceOrder order = new GeoDistanceOrder(
        "location",
        new GeoPoint(10.7769, 106.7009))
        .with(Sort.Direction.ASC)
        .withUnit("km");

CriteriaQuery query = new CriteriaQuery(
        Criteria.where("active").is(true));
query.addSort(Sort.by(order));

SearchHits<Place> hits = operations.search(
        query,
        Place.class,
        IndexCoordinates.of("places"));
```

`CriteriaQuery` expresses the search condition; `addSort` attaches the geo distance order. If Query DSL options not exposed by Spring Data's abstraction in your release train are required, switch to `NativeQuery` or the Elasticsearch Java API Client.

## 12. Nested Geo Points and Advanced Structures

If the geographic field resides inside an object mapped as `nested`, Elasticsearch needs to know the nested path when sorting. Without a nested context, the request may fail because the nested object providing coordinates cannot be determined.

Example mapping:

```http
PUT vendors
{
  "mappings": {
    "properties": {
      "name": {
        "type": "keyword"
      },
      "branches": {
        "type": "nested",
        "properties": {
          "city": {
            "type": "keyword"
          },
          "location": {
            "type": "geo_point"
          }
        }
      }
    }
  }
}
```

Sorting by distance of a nested field:

```http
GET vendors/_search
{
  "sort": [
    {
      "_geo_distance": {
        "branches.location": [106.7009, 10.7769],
        "order": "asc",
        "unit": "km",
        "mode": "min",
        "nested": {
          "path": "branches",
          "filter": {
            "term": {
              "branches.city": "Ho Chi Minh City"
            }
          }
        }
      }
    }
  ],
  "query": {
    "match_all": {}
  }
}
```

`nested.path` identifies the nested object to sort on. `nested.filter` restricts which nested objects are used to obtain distance values; in the example, only branches in Ho Chi Minh City are considered. If nested fields are nested multiple levels deep, each level requires its corresponding nested context.

`GeoDistanceOrder` extends `Order` and supports nested sorting via parent-class APIs in corresponding versions. For complex or multi-level nested filters, verify your Spring Data version's capabilities; use `NativeQuery` / Java API Client when exact JSON control is needed.

## 13. Paginating Distance-Sorted Results

### 13.1. Offset Pagination with `Pageable`

Spring Data repositories can use `Pageable` with `GeoDistanceOrder` as shown above. This fits typical UI lists where users view the first few pages.

Elasticsearch implements offset pagination using `from` and `size`. Each shard must process results prior to the offset to build the requested page. Therefore, overly deep pagination consumes substantial memory and CPU.

By default, `index.max_result_window` typically limits `from + size` to 10,000. Do not raise this limit just to allow scrolling through hundreds of thousands of results with `PageRequest`; for deep pagination, use `search_after` and Point in Time (PIT).

### 13.2. Adding a Tie-Breaker When Multiple Documents Share the Same Distance

Multiple locations can have the exact same sort value—for example, identical coordinates or identical rounded distances. If sorting only by `_geo_distance`, ordering among equal-distance documents may be unstable across requests.

Add a unique keyword field as a secondary criterion:

```json
{
  "sort": [
    {
      "_geo_distance": {
        "location": [106.7009, 10.7769],
        "order": "asc",
        "unit": "km"
      }
    },
    {
      "sortId": "asc"
    }
  ]
}
```

`sortId` must have a unique value per document and `doc_values` for sorting. Do not rely on `_id` as a general sort field; if sorting by ID is needed, copy the ID into a `keyword` field with doc values when indexing documents.

### 13.3. `search_after` for Deep Pagination

`search_after` uses the sort values of the last hit from the previous page to retrieve the next page. Example first request:

```http
GET places/_search
{
  "size": 20,
  "query": {
    "term": {
      "active": true
    }
  },
  "sort": [
    {
      "_geo_distance": {
        "location": [106.7009, 10.7769],
        "order": "asc",
        "unit": "km"
      }
    },
    {
      "sortId": "asc"
    }
  ]
}
```

Suppose the last hit on the page has sort values:

```json
"sort": [1.85, "place-200"]
```

The next request passes that exact array:

```http
GET places/_search
{
  "size": 20,
  "query": {
    "term": {
      "active": true
    }
  },
  "sort": [
    {
      "_geo_distance": {
        "location": [106.7009, 10.7769],
        "order": "asc",
        "unit": "km"
      }
    },
    {
      "sortId": "asc"
    }
  ],
  "search_after": [1.85, "place-200"]
}
```

Requests must keep the same query and sort. `search_after` takes the exact values from `sort` of the last hit of the previous page in the same order. Do not recompute distances or synthesize sort values yourself.

### 13.4. Using Point in Time to Maintain a Stable Snapshot

If an index refreshes while a user moves across pages, new documents or coordinate updates can alter ordering. This can cause documents to be duplicated or skipped when using `search_after` on changing data.

PIT preserves a stable view of the index during pagination:

```http
POST places/_pit?keep_alive=1m
```

Use the PIT ID in subsequent Search API requests. With PIT, Elasticsearch automatically appends `_shard_doc` as a final tie-breaker; you can keep it or specify it explicitly as required. Search requests with PIT do not put the index name in the path; the index and routing are already bound to the PIT.

When finished, close the PIT:

```http
DELETE _pit
{
  "id": "PIT_ID"
}
```

PIT and `search_after` are suitable choices for deep pagination or stable reads across multiple requests. Scroll is primarily meant for batch processing large datasets, not the preferred choice for new interactive pagination.

## 14. Limitations of `GeoDistanceOrder` and When NativeQuery Is Needed

`GeoDistanceOrder` helps bring common geo distance sorting into Spring Data's `Sort` abstraction. The current API provides:

- A geographic property and a reference `GeoPoint` via constructor.
- Sort direction (`ASC`/`DESC`).
- Distance unit.
- `arc` or `plane`.
- Modes `min`, `max`, `avg`, `median`.
- `ignoreUnmapped`.
- Nested options via the parent `Order` class in supported versions.

When advanced structures are needed—such as multiple reference points, complex nested filters, newer Elasticsearch sort options, or combining with multiple search options—`NativeQuery` and the Elasticsearch Java API Client can express them more completely.

Skeleton example using `NativeQuery`:

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

// Build a native search request with the Elasticsearch Java API Client.
// Add the query and geo-distance sort to NativeQuery.builder().
// Execute with operations.search(nativeQuery, Place.class).
```

The specific Java API Client builder depends on the Elasticsearch client version managed by the Spring Data release train. When implementing, use the request builder from the active runtime dependency rather than adding an incompatible major client version.

## 15. Performance and Operational Notes

Geo distance sort must compute distances for candidate documents and retain sort values for ranking. Key notes:

- Use selective query filters to reduce the number of documents that need sorting.
- If only searching within a radius, combine with a `geo_distance` query to limit candidates.
- Choose `arc` by default; only use `plane` for small ranges where approximation error is acceptable.
- Avoid returning too many documents at once; use a reasonable `size`.
- Use `search_after` + PIT for deep pagination; do not raise `from` excessively.
- Verify the field is properly mapped as `geo_point` and coordinate data is valid.
- For multi-valued geo points, choose `mode` based on business semantics rather than relying implicitly on defaults.
- When searching multiple indices, check mapping consistency or set `ignore_unmapped` intentionally.
- Monitor latency and the number of queried shards; geo sorting across many indices/shards can be costly.

Geo distance sort does not replace geographic data quality validation. Coordinates with swapped latitude/longitude may still be numerically valid while pointing to an entirely different place, leading to wrong ranking results without raising a mapping error.

## 16. Common Pitfalls

### Swapping latitude and longitude

`new GeoPoint(latitude, longitude)` takes latitude first and longitude second. Arrays, GeoJSON, and WKT use longitude first and latitude second. Check order when converting between formats.

### Using `geo_distance` query while forgetting `_geo_distance` sort

The query only restricts results to within a radius; it does not automatically ensure the nearest place comes first. Add `_geo_distance` to `sort` if distance-based ranking is needed.

### Using only `_geo_distance` sort and assuming results are radius-limited

Sorting does not exclude distant documents. If you want to limit by radius, add a `geo_distance` query.

### Field mapping is not `geo_point`

The field may have been dynamically mapped as an object or created with the wrong type. Check `GET index/_mapping` and create the right mapping before indexing data.

### Choosing `plane` for long distances

`plane` is an approximation and can be significantly inaccurate over long distances or near the poles. Use `arc` if geographic accuracy matters.

### Omitting `mode` for documents with multiple points

By default, ascending sort picks the nearest point and descending sort picks the farthest point. If business logic requires average or median distance, set `mode` explicitly.

### Documents missing locations appear unexpectedly

Documents lacking coordinates are treated as having infinite distance. Use an `exists` query to exclude them if needed.

### Multi-index search fails on an unmapped field

If an index lacks a `location` mapping, the request can fail. Add consistent mappings or use `ignore_unmapped: true` when you accept treating that index as having no locations.

### Paginated results contain duplicates or missing documents

If multiple hits share the same distance sort value, add a unique tie-breaker. When data can refresh between pages, use PIT with `search_after` to keep a snapshot.

### Using `PageRequest` for overly deep results

Offset pagination is resource-intensive when `from` is large and is bounded by `index.max_result_window` by default. Switch to `search_after` + PIT for large result sets.

### Expecting the sort value to appear in the entity automatically

Distance is search hit metadata, not a field in `_source`. Read sort values from SearchHit/SearchResponse if distance display is needed.

## 17. Workflow for Implementing Geo Distance Sort

When adding nearest-location search, you can follow this sequence:

1. Determine where the reference point comes from and which coordinate system is used.
2. Map the location field as `geo_point`.
3. Validate incoming data, especially latitude/longitude order.
4. Build business filter queries, such as active or category.
5. Add a `geo_distance` query if radius filtering is required.
6. Add `_geo_distance` sort with `order: asc` for nearest first.
7. Choose `unit`, `distance_type`, and `mode` per requirements.
8. Decide how to handle documents missing coordinates and unmapped indices.
9. Use `GeoDistanceOrder` if Spring Data's API suffices; switch to `NativeQuery`/client when advanced options are needed.
10. Add a tie-breaker and choose `Pageable` or `search_after` + PIT depending on pagination depth.
11. Test with nearby points, distant points, identical coordinates, multiple coordinates, missing coordinates, and boundary coordinates.
12. Benchmark performance with production-scale data and monitor queried shard counts.

## 18. Summary

Elasticsearch uses `_geo_distance` in `sort` to rank documents by distance to a reference point. `order: asc` puts the nearest place first; `desc` puts the farthest place first. `unit` selects the distance unit, `distance_type` chooses `arc` or `plane`, `mode` decides how distances are aggregated when a document has multiple geo points, and `ignore_unmapped` handles indices lacking the corresponding mapping. Documents without coordinates are treated as having infinite distance; excluding them requires an `exists` filter.

Spring Data Elasticsearch provides `GeoDistanceOrder` to integrate geo distance sorting with `Sort`, `Pageable`, and repository methods. The constructor takes the property name and `GeoPoint(latitude, longitude)`; methods `with(...)`, `withUnit(...)`, and `withIgnoreUnmapped(...)` configure direction, unit, distance calculation type, mode, and heterogeneous mappings. When multiple reference points or advanced Query DSL options are needed, use `NativeQuery` / Elasticsearch Java API Client.

For pagination, `Pageable` works well for early pages. When results are deep or data changes between requests, use `search_after` with the last hit's sort values and PIT to maintain a stable snapshot. Add a unique tie-breaker to avoid duplicate or skipped hits with equal distances. Accurate mappings, correct coordinate ordering, and appropriate mode selection determine whether geo distance sort results match business requirements.

## References

- [Spring Data Elasticsearch – Miscellaneous operations and sort options](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/misc.html)
- [Spring Data Elasticsearch – `GeoDistanceOrder` API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/GeoDistanceOrder.html)
- [Spring Data Elasticsearch – `GeoPoint` API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/geo/GeoPoint.html)
- [Elasticsearch – Sort search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/sort-search-results)
- [Elasticsearch – Paginate search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/paginate-search-results)
- [Elasticsearch – Geo point field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/geo-point)
- [Elasticsearch – Geo queries](https://www.elastic.co/docs/reference/query-languages/query-dsl/geo-queries)
