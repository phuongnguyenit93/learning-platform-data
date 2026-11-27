# Finding Places by Radius and Distance Order

Elasticsearch can store geographic coordinates in a `geo_point` field to find documents within a radius around a user's location and sort results from nearest to farthest. In Spring Data Elasticsearch, you can declare a coordinate field on an entity, build a `geo_distance` condition with `NativeQuery`, and add a geographic distance sort.

A place search request typically has three independent parts:

1. **Origin:** the user's location or search center.
2. **Radius:** the maximum distance limit, such as 5 km.
3. **Distance order:** ascending sort so the nearest place appears first.

It is important to use the correct latitude/longitude order, place the radius condition inside the query filter, and use `_geo_distance` sort for result ordering. Filtering by radius and sorting by distance are two separate operations; adding a sort alone does not restrict results to the radius.

## 1. Geographic Data Model

Elasticsearch supports two main geographic data types:

- `geo_point`: represents a single location with latitude and longitude.
- `geo_shape`: represents complex geometries such as polygons, multipolygons, lines, or geographic regions.

Finding stores, restaurants, hospitals, or transit stations around a point typically uses `geo_point`. Each document has a coordinate representing the place.

Example document:

~~~json
{
  "name": "Central Coffee",
  "category": "CAFE",
  "status": "OPEN",
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
~~~

Where:

- `lat`: latitude, ranging from -90 to +90.
- `lon`: longitude, ranging from -180 to +180.
- `location`: field mapped as `geo_point`.

Do not use regular `double` or `keyword` fields for coordinates if you need geo queries and geo-distance sorting. The mapping must be `geo_point` so Elasticsearch interprets the data in geographic coordinate space.

### 1.1. How Do Latitude and Longitude Differ?

Latitude measures North–South position:

- The Equator is 0°.
- The Northern Hemisphere has positive latitude.
- The Southern Hemisphere has negative latitude.
- The North Pole is +90° and the South Pole is -90°.

Longitude measures East–West position:

- The Prime Meridian (Greenwich) is 0°.
- East has positive longitude.
- West has negative longitude.
- Values range from -180° to +180°.

For example, coordinates for downtown Ho Chi Minh City are approximately:

~~~text
latitude  = 10.7769
longitude = 106.7009
~~~

These are illustrative coordinates; applications should use accurate coordinates from a place dataset or positioning device.

### 1.2. Watch Coordinate Order Carefully

APIs and formats do not always share the same coordinate order.

| Representation | Order |
| --- | --- |
| `geo_point` object | `lat`, then `lon` |
| Elasticsearch string | `"lat,lon"` |
| Elasticsearch array | `[lon, lat]` |
| GeoJSON | `[longitude, latitude]` |
| Spring Data `GeoPoint` | Typically `(latitude, longitude)` |

For example, the same location:

~~~json
{
  "lat": 10.7769,
  "lon": 106.7009
}
~~~

Corresponding array:

~~~json
[106.7009, 10.7769]
~~~

This is the most common bug when integrating map data: swapping latitude and longitude can produce a completely different location that still falls within valid ranges. Therefore, checking only that latitude is in [-90, 90] and longitude is in [-180, 180] is not enough to catch swapped axes.

### 1.3. Choose a Consistent Storage Format

Elasticsearch accepts several `geo_point` representations, but you should standardize application payloads as an object with explicit fields:

~~~json
{
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
~~~

Explicitly named objects reduce mistakes during serialization, log inspection, and data verification. For external APIs using GeoJSON, convert from `[lon, lat]` to `{lat, lon}` at the application boundary.

## 2. Declaring a `geo_point` Mapping

You can create the index with an explicit mapping:

~~~http
PUT /places
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "name": {
        "type": "text"
      },
      "category": {
        "type": "keyword"
      },
      "status": {
        "type": "keyword"
      },
      "location": {
        "type": "geo_point"
      }
    }
  }
}
~~~

After creating the index, verify the mapping:

~~~http
GET /places/_mapping
~~~

The output should show:

~~~json
{
  "properties": {
    "location": {
      "type": "geo_point"
    }
  }
}
~~~

The mapping should be created before indexing the first document. If dynamic mapping has already inferred `location` as a regular object or another type, changing Java annotations alone cannot turn that field into `geo_point` in the existing index. When a type change is needed, create a new index with the right mapping and reindex the data.

### 2.1. Mapping Fields in Spring Data Elasticsearch

Spring Data Elasticsearch provides the `@GeoPointField` annotation for coordinate properties.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.GeoPointField;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Document(indexName = "places")
public class PlaceDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Keyword)
    private String status;

    @GeoPointField
    private GeoPoint location;

    // Constructor, getters and setters
}
~~~

Spring Data Elasticsearch's `GeoPoint` represents latitude and longitude. When constructing it, pass latitude first, then longitude:

~~~java
GeoPoint location = new GeoPoint(10.7769, 106.7009);
~~~

In some versions, factory APIs or packages may differ slightly. Use `org.springframework.data.elasticsearch.core.geo.GeoPoint` from your installed dependency and verify the actual mapping after creating the index.

Another option is annotating the field with `@Field(type = FieldType.GeoPoint)` if your Spring Data version provides that enum constant. `@GeoPointField` makes the mapping intent clear and is usually easier to read.

### 2.2. Saving a Place

Example service saving a place:

~~~java
@Service
public class PlaceService {

    private final ElasticsearchOperations operations;

    public PlaceService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public PlaceDocument save(
            String id,
            String name,
            String category,
            double latitude,
            double longitude) {

        PlaceDocument place = new PlaceDocument();
        place.setId(id);
        place.setName(name);
        place.setCategory(category);
        place.setStatus("OPEN");
        place.setLocation(new GeoPoint(latitude, longitude));

        return operations.save(place);
    }
}
~~~

Latitude and longitude values must be validated before creating `GeoPoint`. If coordinates arrive from a client, the API should validate value ranges, numeric types, and axis conventions. If places come from a geocoding provider, store the source and coordinate update timestamp to aid investigating bad data.

## 3. Finding Documents Within a Radius Using `geo_distance`

A geo-distance query filters documents based on the distance between an origin point and a `geo_point` field.

Example finding places within a 5 km radius around the user's location:

~~~http
GET /places/_search
Content-Type: application/json

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

Meaning:

- `distance`: maximum radius.
- `location`: `geo_point` field in the document.
- `lat`, `lon`: search center coordinates.

Elasticsearch returns only documents whose distance to the origin lies within the declared radius.

### 3.1. Distance Units

Distances can be expressed in several units:

| Unit | Example |
| --- | --- |
| Kilometer | `5km` |
| Meter | `5000m` |
| Mile | `3mi` |
| Yard | `5000yd` |
| Foot | `16000ft` |
| Nautical mile | `2.7nmi` |
| Centimeter | `500000cm` |
| Millimeter | `5000000mm` |

Choose a single consistent unit in the API. For example, the API accepts `radiusKm`, and the service builds `"5km"` when constructing the query. Never mix kilometers and meters in the same contract without field names indicating the unit.

### 3.2. Adding Business Conditions

Finding nearby places often requires filtering by category or status as well. Put those conditions inside `bool.filter` so they narrow the result set without affecting relevance scores.

~~~http
GET /places/_search
Content-Type: application/json

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
            "category": "CAFE"
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

This query returns open cafes within 5 km. If you add a `must` match query for name or description, Elasticsearch computes relevance scores for the text part; radius and status conditions should still stay inside filter.

### 3.3. Should `geo_distance` Use `arc` or `plane`?

Elasticsearch supports two distance calculation modes in certain geo operations:

- `arc`: calculates distance along the curved surface of the Earth. This is the default and fits most geographic applications.
- `plane`: uses a flat-plane approximation, which can be faster but loses accuracy as distance and latitude increase.

Example:

~~~json
{
  "geo_distance": {
    "distance": "5km",
    "distance_type": "arc",
    "location": {
      "lat": 10.7769,
      "lon": 106.7009
    }
  }
}
~~~

For searching places around a user, normally keep `arc`. Choose `plane` only after benchmarking and confirming the error margin is acceptable for your use case. Do not use flat calculations over large distances or near the poles when geographic accuracy matters.

## 4. Sorting by Distance with `_geo_distance`

A geo-distance filter only restricts documents within the radius. It does not automatically put the closest document first. To sort, add `_geo_distance` to the `sort` array.

Complete example:

~~~http
GET /places/_search
Content-Type: application/json

{
  "size": 20,
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
~~~

Properties:

- `location`: geographic field to compute distance from.
- `order: asc`: nearest first.
- `order: desc`: farthest first.
- `unit`: distance unit returned in the sort value.
- `distance_type`: distance calculation method.

**You must include both the `geo_distance` query and the `_geo_distance` sort** when the requirement is "find within radius and order from nearest to farthest."

With only `_geo_distance` sort, Elasticsearch will sort all documents matching other query clauses, including places outside the radius. With only the `geo_distance` query, results stay inside the radius, but the default order is not nearest-first.

### 4.1. Sort Value Is Distance, Not Coordinates

Each hit can contain sort values computed by Elasticsearch. When sorting by `_geo_distance`, the sort value is the distance from the origin to the document in the chosen unit.

Abbreviated response example:

~~~json
{
  "hits": {
    "hits": [
      {
        "_id": "place-01",
        "_source": {
          "name": "Cafe A",
          "location": {
            "lat": 10.7771,
            "lon": 106.7010
          }
        },
        "sort": [0.024]
      },
      {
        "_id": "place-02",
        "_source": {
          "name": "Cafe B",
          "location": {
            "lat": 10.7800,
            "lon": 106.7040
          }
        },
        "sort": [0.45]
      }
    ]
  }
}
~~~

The numbers in the example are illustrative distances in kilometers. You can use the sort value to display approximate distance in the API response without recalculating from coordinates. If the application needs formatting like "450 m" or "1.2 km", convert and round in the presentation layer.

### 4.2. Multiple Points in One Document

A `geo_point` field can hold multiple coordinates. When sorting, Elasticsearch needs a mode to aggregate distances across those points, such as `min`, `max`, `avg`, or `median` depending on operation support.

For documents representing a single venue with one location, store a single `geo_point` to avoid ambiguous semantics. For businesses with multiple branches, consider indexing each branch as its own document so every result has an unambiguous location and distance.

## 5. Implementing Queries with Spring Data Elasticsearch

Spring Data Elasticsearch provides `NativeQuery` to use Elasticsearch Java API Client Query DSL. This suits `geo_distance` well because all Elasticsearch query attributes are available.

Example creating a geo-distance query:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

public class PlaceSearchService {

    private final ElasticsearchOperations operations;

    public PlaceSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<PlaceDocument> findWithinRadius(
            double latitude,
            double longitude,
            String radius) {

        Query geoDistanceQuery = Query.of(q -> q.geoDistance(g -> g
                .field("location")
                .distance(radius)
                .location(location -> location.latlon(point -> point
                        .lat(latitude)
                        .lon(longitude)
                ))
        ));

        NativeQuery query = NativeQuery.builder()
                .withQuery(geoDistanceQuery)
                .build();

        return operations.search(query, PlaceDocument.class);
    }
}
~~~

Here:

- `Query.of(...)` constructs an Elasticsearch query.
- `geoDistance(...)` creates the `geo_distance` query.
- `field("location")` targets the `geo_point` field.
- `distance(radius)` accepts a unit string like `5km`.
- `latlon(...)` takes latitude and longitude separately.
- `NativeQuery` passes the query into Spring Data Elasticsearch.

Generated method names in the Java API Client can differ by the client version managed by Spring Data. When upgrading Spring Data, use the compatible client API managed by the dependency and verify compilation.

### 5.1. Combining Filters with Geo-Distance

You can add category and status into a bool filter:

~~~java
Query queryDsl = Query.of(q -> q.bool(b -> b
        .filter(f -> f.geoDistance(g -> g
                .field("location")
                .distance("5km")
                .location(location -> location.latlon(point -> point
                        .lat(latitude)
                        .lon(longitude)
                ))
        ))
        .filter(f -> f.term(t -> t
                .field("category")
                .value("CAFE")
        ))
        .filter(f -> f.term(t -> t
                .field("status")
                .value("OPEN")
        ))
));

NativeQuery query = NativeQuery.builder()
        .withQuery(queryDsl)
        .build();
~~~

Independent filters are combined by Elasticsearch using AND. Only documents that are simultaneously within the radius, in the right category, and open are returned.

### 5.2. Sorting by Distance in Spring Data

Spring Data Elasticsearch provides `GeoDistanceOrder` to express distance sorting inside Spring `Sort`.

Example:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;
import org.springframework.data.elasticsearch.core.query.GeoDistanceOrder;

GeoPoint origin = new GeoPoint(latitude, longitude);

Sort distanceSort = Sort.by(
        new GeoDistanceOrder("location", origin)
);

NativeQuery query = NativeQuery.builder()
        .withQuery(geoDistanceQuery)
        .withSort(distanceSort)
        .withPageable(PageRequest.of(0, 20))
        .build();

SearchHits<PlaceDocument> hits =
        operations.search(query, PlaceDocument.class);
~~~

`GeoDistanceOrder` defaults to ascending distance order in the corresponding Spring Data API. Some versions expose extra options for unit, distance type, or sort mode. If you need exact control over `unit: km`, `distance_type: arc`, or other options, check the `GeoDistanceOrder` API in your dependency; you can use `SortOptions` from the Elasticsearch Java API Client if the abstraction does not expose the needed property.

Never pass a plain `Sort.by("location")` as a substitute for geo-distance sort. Sorting on a `geo_point` field requires an origin and distance semantics, not lexical or numeric field sorting.

### 5.3. Reading Distance from Results

`SearchHit<T>` holds document content, ID, score, and hit metadata. With geo-distance sort, sort values are returned in hit metadata according to your API version.

Example:

~~~java
for (SearchHit<PlaceDocument> hit : hits) {
    PlaceDocument place = hit.getContent();

    List<Object> sortValues = hit.getSortValues();

    System.out.println(place.getName());
    System.out.println(sortValues);
}
~~~

A sort value may be a numeric type or representation depending on client/version. If the product API needs a `distanceKm` field, parse the sort value according to your defined contract and return a DTO—do not leak Elasticsearch metadata into domain entities.

## 6. Creating a Nearby Places Search API

A realistic endpoint may accept:

~~~http
GET /api/places/nearby?lat=10.7769&lon=106.7009&radiusKm=5&category=CAFE&page=0&size=20
~~~

The API must validate:

- `lat` lies within [-90, 90].
- `lon` lies within [-180, 180].
- `radiusKm` is greater than 0 and does not exceed business limits.
- `size` has an upper cap.
- `category` belongs to supported categories.
- When category is absent, omit the category filter instead of creating a term filter with null.

Example DTO:

~~~java
public record NearbyPlaceRequest(
        double latitude,
        double longitude,
        double radiusKm,
        String category,
        int page,
        int size
) {
}
~~~

Validate inputs before querying Elasticsearch:

~~~java
public void validate(NearbyPlaceRequest request) {
    if (request.latitude() < -90 || request.latitude() > 90) {
        throw new IllegalArgumentException("Latitude is out of range");
    }

    if (request.longitude() < -180 || request.longitude() > 180) {
        throw new IllegalArgumentException("Longitude is out of range");
    }

    if (request.radiusKm() <= 0 || request.radiusKm() > 100) {
        throw new IllegalArgumentException("Radius is out of range");
    }

    if (request.size() <= 0 || request.size() > 100) {
        throw new IllegalArgumentException("Page size is out of range");
    }

    if (request.page() < 0) {
        throw new IllegalArgumentException("Page must not be negative");
    }
}
~~~

The 100 km radius cap and page size 100 are examples only. Products should choose limits based on use case, query cost, and user experience.

### 6.1. Formatting Radius with an Explicit Unit

If the API accepts kilometers:

~~~java
String distance = request.radiusKm() + "km";
~~~

For decimal inputs, format with `Locale.ROOT` to prevent locale-dependent decimal commas:

~~~java
String distance = String.format(
        Locale.ROOT,
        "%.3fkm",
        request.radiusKm()
);
~~~

Never concatenate unvalidated input strings into Query DSL. Use numeric types in DTOs, validate ranges, and generate unit strings inside the service.

### 6.2. Response DTO with Distance

Example response:

~~~json
{
  "items": [
    {
      "id": "place-01",
      "name": "Cafe A",
      "latitude": 10.7771,
      "longitude": 106.7010,
      "distanceKm": 0.024
    }
  ],
  "page": 0,
  "size": 20
}
~~~

Distance can come from the geo sort value. If computed in the application, use a proper geographic formula such as Haversine and keep units consistent. Never compute planar distance by subtracting latitude and longitude and treat the result as kilometers.

## 7. Searching by Radius and Text Simultaneously

A common use case is finding places near the user whose name or description matches keywords.

Example searching for "pho" within a 3 km radius:

~~~http
GET /places/_search
Content-Type: application/json

{
  "size": 20,
  "query": {
    "bool": {
      "must": [
        {
          "multi_match": {
            "query": "pho",
            "fields": ["name^2", "description"]
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
            "status": "OPEN"
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

In this example, the text query sits inside `must` and may compute `_score`, while primary ordering prioritizes distance. If you prefer text relevance first, sort by `_score` descending and then distance; if nearest must always appear first, keep geo-distance sort as the first criterion.

Choose ordering based on product goals:

| Goal | Sort |
| --- | --- |
| Nearest place always first | Geo distance ascending. |
| Best text match first | `_score` descending, then distance ascending. |
| Relevance first, closer when scores tie | `_score` desc then `_geo_distance` asc. |
| Only filter by radius, nearest order not needed | `geo_distance` query, sorted by another criterion or default. |

Do not assume query score and distance automatically combine into a sensible ranking. If combined ranking is needed, define an explicit scoring/ranking policy and benchmark with relevance data.

## 8. Pagination and Stable Ordering

You can use `from`/`size` or `PageRequest` for simple pagination. However, if multiple places have the same rounded distance, ordering among them may become unstable.

For deterministic ordering, add a unique tie-breaker, usually `_id` or a keyword ID field.

Example:

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
      "_id": "asc"
    }
  ]
}
~~~

For deep pages, `from`/`size` forces Elasticsearch to buffer many results on each shard. Use `search_after` for deep pagination when queries and sorts allow it.

### 8.1. Search After with Geo-Distance Sort

`search_after` requires sending back the sort values of the last hit from the previous page. With geo-distance sort, the sort value contains the distance; the tie-breaker establishes a unique total order.

Flow:

1. Request the first page with geo-distance sort and `_id`.
2. Capture the sort values of the last hit.
3. Send the next request with `search_after` containing those sort values.
4. Keep origin, radius, filters, and sort identical across subsequent requests.

If the origin changes between pages, sort order shifts and `search_after` no longer represents the same ordering. For continuously changing data, consider Point in Time (PIT) together with `search_after` to keep a consistent view while paging.

Never use `search_after` with sort values from a different request or a different query.

## 9. Multiple Indices and Aliases

If a query targets an alias spanning multiple indices, every index must map `location` consistently as `geo_point`. If one index maps `location` as a regular object or lacks the mapping, the query or sort may fail depending on `ignore_unmapped` and the API.

Check mappings:

~~~http
GET /places-*/_mapping/field/location
~~~

When an alias covers multiple index versions:

- Keep the same field name and type.
- Keep coordinate semantics consistent.
- Verify older indices before adding them to the alias.
- Never allow an index without a geo_point field to participate in geo searches unintentionally.
- If missing fields must be skipped during sorting, evaluate `ignore_unmapped` and its impact on result semantics.

Do not use `ignore_unmapped` to mask broken mappings in indices that are supposed to contain coordinates. It is helpful for queries spanning heterogeneous indices, provided you understand which indices are skipped.

## 10. Error-Prone Geographic Scenarios

### 10.1. Swapped Latitude and Longitude

Symptom: valid query returns no places near the expected area, or results appear in another region of the world.

Checks:

- Is the input `[lon, lat]` from GeoJSON?
- Does the Spring Data constructor take `(lat, lon)`?
- Does the Query DSL use `{lat, lon}` correctly?
- Does the client map library expect a different coordinate order?

Write unit tests for conversions from GeoJSON to `GeoPoint`.

### 10.2. Out-of-Range Coordinates

Latitude outside [-90, 90] or longitude outside [-180, 180] usually indicates corrupted data or swapped axes. Validate at the API boundary before indexing.

### 10.3. Points on Either Side of the International Date Line

Longitudes near +180° and -180° are geographically adjacent even though their numeric values differ wildly. Never compute distance with naive longitude subtraction. Elasticsearch geo-distance operates on the Earth's surface.

### 10.4. Regions Near the Poles

A degree of longitude does not represent the same physical distance at every latitude. Near the poles, meridians converge. Use `geo_distance` instead of custom flat-coordinate math whenever geographic distance matters.

### 10.5. Documents Without Coordinates

Documents missing `location` will not match geo-distance queries. Never invent a default coordinate like `(0,0)` to fill missing data; fake coordinates put those documents into searches around the Gulf of Guinea.

Distinguish clearly between:

- Documents with valid coordinates.
- Documents not yet geocoded.
- Documents whose geocoding failed.
- Documents flagged with unreliable coordinates.

You can store `locationStatus` or a similar state field to handle missing data explicitly.

### 10.6. Stale or Inaccurate Coordinates

Place locations can change. Store `locationUpdatedAt`, coordinate source, and accuracy if provided by the geocoding provider. For delivery or service-station apps, coordinates off by a few hundred meters can break user expectations.

## 11. Testing Radius Search

Seed data with known distances to verify both filtering and sorting.

Example fixtures:

| ID | Position | Expectation with 5 km radius |
| --- | --- | --- |
| A | ~0.5 km from origin | Included, appears before B. |
| B | ~2 km from origin | Included. |
| C | ~4.9 km from origin | Included. |
| D | ~5.1 km from origin | Excluded. |
| E | No location | Excluded from geo-distance query. |

Distances should be calculated from verified coordinates or precomputed fixtures rather than eyeballed on a map.

### 11.1. Testing Radius Filters

Verify:

- Documents just inside the radius are returned.
- Documents outside the radius are excluded.
- Documents matching category/status are returned.
- Documents with wrong category/status are excluded.
- Documents missing location do not appear.
- Very small and large radii behave per contract.
- Boundary latitude/longitude values are handled properly.

### 11.2. Testing Sort Order

With a fixed origin, assert non-decreasing distances:

~~~java
List<Double> distances = hits.getSearchHits().stream()
        .map(hit -> (Number) hit.getSortValues().get(0))
        .map(Number::doubleValue)
        .toList();

for (int i = 1; i < distances.size(); i++) {
    assertThat(distances.get(i))
            .isGreaterThanOrEqualTo(distances.get(i - 1));
}
~~~

Sort value types and units must be verified for your request and client version. If the query adds another sort field before geo distance, the corresponding sort value index shifts accordingly.

### 11.3. Testing Coordinate Order

Write a test using a location whose latitude and longitude are unmistakably distinct, for example a coordinate in Vietnam. Inspect the serialized values in `_source` and the query origin. Do not check only the Java object before saving.

You can read the document back directly:

~~~http
GET /places/_doc/place-01
~~~

Confirm `_source.location.lat` and `_source.location.lon` match expected values.

## 12. Performance and Query Limits

Geo-distance queries must evaluate distances for candidate documents. These practices keep queries bounded:

- Set a maximum allowed radius per product requirements.
- Apply category, status, or tenant filters when appropriate.
- Cap page size.
- Avoid huge radius queries if the UI only renders nearby venues.
- Return only needed fields via source filtering.
- Monitor p95/p99 latency and hit counts.
- Ensure `location` is mapped as `geo_point`.
- Use pagination suited to traversal depth.

Example fetching only needed fields:

~~~http
GET /places/_search
Content-Type: application/json

{
  "_source": ["name", "category", "location"],
  "size": 20,
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
        "unit": "km"
      }
    }
  ]
}
~~~

Never cache results keyed solely by category and radius. The origin must be part of the cache key; otherwise users elsewhere receive another user's nearby places. Round coordinates in cache keys only if grouping nearby requests is desired and you have an explicit accuracy policy.

### 12.1. Choosing Reasonable Radii

Larger radii match more documents and increase query work. Enforce business limits:

- Finding stores around a user: a few kilometers to a few tens of kilometers.
- Finding hospitals in a metro area: a wider radius may apply.
- Finding charging stations along a route: radius may depend on vehicle type and context.
- Nationwide geographic analytics: may require geo aggregations or a dedicated analytics pipeline.

These figures illustrate use cases, not hard technical limits.

### 12.2. Filter Before Sorting

Query filters narrow down the document set. Distance sorting then ranks the matching hits. Place business predicates inside `bool.filter` so Elasticsearch skips unnecessary relevance scoring for exact-match filters.

Geo-distance sort still computes distances for matching hits being sorted. When radii are wide and hit counts are high, factor in page size, shard distribution, and UI requirements.

## 13. Other Options: Geohash, Grids, and Geo Aggregations

If you need to group places by region or build heatmaps, `geo_point` also supports geographic aggregations such as geotile grid, geohash grid, or geo bounds depending on the use case.

That is a different problem from "top nearest places":

- Geo-distance query filters documents within a radius.
- Geo-distance sort orders documents by distance to an origin.
- Geo-distance aggregation buckets documents by distance rings where supported.
- Geotile/geohash grids cluster documents into map cells for map rendering or heatmaps.

Do not use aggregations instead of geo-distance sort when the requirement is returning individual places ordered nearest-first.

## 14. Implementation Checklist in Spring Data Elasticsearch

1. Is the coordinate field mapped as `geo_point`?
2. Does the entity declare `@GeoPointField` or an equivalent mapping?
3. Are Java `GeoPoint` instances constructed as `(latitude, longitude)`?
4. Is GeoJSON `[longitude, latitude]` converted properly?
5. Are latitude/longitude inputs validated?
6. Does the query include `geo_distance` with radius and origin?
7. Are business conditions placed in `bool.filter`?
8. Does sort include `_geo_distance` with `order: asc`?
9. Are units consistent across query, sort, and API response?
10. Is there a stable tie-breaker for pagination?
11. Are mappings verified across all indices behind any alias?
12. Are documents missing coordinates handled cleanly?
13. Are there tests for points inside and outside the radius?
14. Are there tests verifying distance sort order?
15. Does any cache key include the origin?
16. Are radius, page size, and query latency bounded?

## 15. References

- [Spring Data Elasticsearch — GeoPoint and mapping annotations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch — NativeQuery](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Elasticsearch — Geo-point field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/geo-point.html)
- [Elasticsearch — Geo-distance query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-geo-distance-query.html)
- [Elasticsearch — Geo-distance sort](https://www.elastic.co/guide/en/elasticsearch/reference/current/sort-search-results.html#geo-sorting)
- [Elasticsearch — Search results sorting](https://www.elastic.co/guide/en/elasticsearch/reference/current/sort-search-results.html)
- [Elasticsearch — Geo-shape field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/geo-shape.html)
- [Elasticsearch — Geotile grid aggregation](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-aggregations-bucket-geotilegrid-aggregation.html)

To find places within a radius and sort from nearest to farthest, map `location` as `geo_point`, use `geo_distance` in the query to bound the radius, and use `_geo_distance` in sort to control ordering. Spring Data Elasticsearch lets you declare coordinates with `@GeoPointField`, construct queries with `NativeQuery`, and sort with `GeoDistanceOrder`. Pay special attention to latitude/longitude ordering, distance units, business filters, and pagination so results match the user's real location.
