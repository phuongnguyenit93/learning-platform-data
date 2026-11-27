# Sorting, Aggregating, and Returning Appropriate Distances

In applications with geospatial data, finding documents within a radius is only the first step. An API that finds stores near a user typically needs to do three additional things:

1. Sort stores from nearest to farthest.
2. Aggregate store counts across distance bands, such as 0–1 km, 1–5 km, and 5–20 km.
3. Return each result's distance to the client in an appropriate unit for display.

Elasticsearch supports these tasks on fields of type geo_point. You can use geo-distance sorting to rank by distance, geo_distance aggregation to group by distance ranges, and sort values or script fields to return distance values in the response.

In Spring Data Elasticsearch, NativeQuery together with the Elasticsearch Java API Client lets you construct these configurations. When reading results, distinguish document content from hit metadata: the distance computed for sorting typically lives in SearchHit's sort values and does not automatically become a property on the entity or inside _source.

## 1. Preparing the geo_point field

Suppose the application manages stores:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Document(indexName = "stores")
public class Store {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    @Field(type = FieldType.GeoPoint)
    private GeoPoint location;

    // constructors, getters and setters
}
~~~

The location field must be mapped as geo_point. Corresponding mapping:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "keyword"
      },
      "category": {
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

You can inspect the mapping:

~~~http
GET /stores/_mapping?pretty
~~~

If location is currently a plain object or text, geo-distance sorting and geo_distance aggregation will not work as intended. Java annotations do not automatically modify the mapping of an existing index; when changing a field type, create a new index and migrate/reindex data through a proper workflow.

### 1.1. Latitude and longitude conventions

With Spring Data GeoPoint, the constructor typically takes latitude first, longitude second:

~~~java
GeoPoint point = new GeoPoint(10.7769, 106.7009);
~~~

In an Elasticsearch JSON object, use the lat and lon properties:

~~~json
{
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
~~~

If using a coordinate array, the order is longitude first, latitude second:

~~~json
{
  "location": [
    106.7009,
    10.7769
  ]
}
~~~

This is a common source of errors. Latitude must lie between -90 and 90; longitude must lie between -180 and 180. Validate input data before saving and standardize the convention at the API boundary.

## 2. Identifying the origin for distance calculation

Every distance calculation requires an origin point. In location-search applications, the origin is typically:

- The current position sent by a device.
- A user-selected address geocoded into coordinates.
- A fixed hub such as an airport, warehouse, or branch.
- A business-specified reference point.

Example:

~~~java
double originLat = 10.7769;
double originLon = 106.7009;
~~~

Never extract these two values from an unvalidated string. Confirm they are finite numbers, latitude/longitude lie within valid bounds, and the values are in the right order.

Distances depend on the origin. If the origin varies per request, the query sort and aggregation must use the exact same origin for consistent results. Do not sort by one coordinate pair while aggregating around another.

### 2.1. Distance units

Elasticsearch supports several distance units; common ones include:

| Unit | Symbol |
|---|---|
| Meter | m |
| Kilometer | km |
| Centimeter | cm |
| Millimeter | mm |
| Mile | mi |
| Yard | yd |
| Feet | ft |
| Nautical mile | nmi |

For mapping or store-locator apps, km is typically suitable for distances above a few hundred meters; m is suitable for displaying short walking distances.

Keep units consistent across requests, aggregations, and DTOs. If the sort returns distances in km while the DTO labels them as meters, the client will display wrong values even though the query ran properly.

## 3. Geo-distance sort: sorting from nearest to farthest

Geo-distance sort orders documents based on the distance from the origin to each document's geo_point.

REST DSL:

~~~http
POST /stores/_search
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
~~~

Meaning:

- _geo_distance requests sorting by geographic distance.
- location is the geo_point field in the document.
- lat/lon is the origin.
- order asc places the nearest point first.
- unit km expresses distance in kilometers.
- distance_type arc calculates distance along an arc on the Earth's surface.

If order is changed to desc, farther documents appear first. For nearest search, asc is normally used.

### 3.1. Combining geo-distance sort with geo_distance query

Geo-distance sort only orders documents matched by the query. It does not restrict the radius on its own.

If the API only wants stores within 10 km, add a geo_distance query:

~~~http
POST /stores/_search
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
          "geo_distance": {
            "distance": "10km",
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
        "unit": "km",
        "distance_type": "arc"
      }
    }
  ]
}
~~~

The geo_distance query bounds the result set by radius. The geo-distance sort ranks the remaining results from nearest to farthest.

This is a common pattern for nearby-places endpoints:

- Filter by status, category, tenant, or access permissions.
- Geo-distance query restricts the radius.
- Geo-distance sort ranks by distance.
- Search size/Pageable caps the number of returned results.

### 3.2. Arc and plane

Elasticsearch supports two common distance calculation modes:

- arc: distance along an arc on a sphere, appropriate for general geographic distances.
- plane: flat-plane approximation, potentially faster, though error increases over large distances or wide geographic regions.

For typical place-search apps, arc is the safe choice for accurate geographic distances. Only choose plane after benchmarking performance and error on your actual data region.

Do not confuse distance_type with unit. distance_type selects the calculation method; unit selects the distance measurement unit.

### 3.3. Sorting on fields with multiple GeoPoints

A document can contain multiple geo_point values. Elasticsearch then needs to determine which distance represents the document.

Geo-distance sort supports modes such as min, max, avg, or sum depending on supported context. Example:

~~~http
POST /branches/_search
{
  "sort": [
    {
      "_geo_distance": {
        "locations": [
          {
            "lat": 10.7769,
            "lon": 106.7009
          }
        ],
        "order": "asc",
        "unit": "km",
        "mode": "min"
      }
    }
  ]
}
~~~

When finding the nearest branch among a document's set of locations, mode min is usually the right choice. If you want the farthest or average distance, pick the corresponding mode and interpret results according to business rules.

With a single location per document, mode is unnecessary in many cases. If a field is multi-valued, specify clearly which point's distance is representative.

### 3.4. Missing geo fields and heterogeneous indices

Some documents may lack location. When searching an alias spanning multiple indices, an index might omit the geo_point field or have a different mapping.

Geo-distance sort provides options for handling unmapped fields across some indices, such as ignore_unmapped. Verify the syntax for your Elasticsearch version and the mappings of all target indices. Ignoring unmapped fields does not turn a coordinate-less document into a valid location.

If location is mandatory for business logic, filter for documents having location with an exists query before sorting.

## 4. Reading distance from sort values

When using _geo_distance in sort, Elasticsearch returns the sort value for each hit inside the response's sort property. That value is the computed distance in the specified unit.

Sample response:

~~~json
{
  "hits": {
    "hits": [
      {
        "_index": "stores",
        "_id": "S-1001",
        "_score": null,
        "_source": {
          "name": "Central Store",
          "location": {
            "lat": 10.7800,
            "lon": 106.7020
          }
        },
        "sort": [
          0.42
        ]
      }
    ]
  }
}
~~~

In this example, sort value 0.42 corresponds to 0.42 km because the sort declared unit km. The response may include additional sort values if the query specifies multiple sort criteria.

Key point: the sort value is hit metadata. It is not automatically written into _source and does not automatically populate properties on the Store entity.

In Spring Data Elasticsearch, keep SearchHit to read both content and metadata:

~~~java
SearchHits<Store> hits =
    operations.search(nativeQuery, Store.class);

for (SearchHit<Store> hit : hits) {
    Store store = hit.getContent();

    List<Object> sortValues = hit.getSortValues();

    System.out.println(store.getName());
    System.out.println(sortValues);
}
~~~

SearchHit.getSortValues() is a metadata API to verify against your version of Spring Data Elasticsearch. The first value in the example is the geo-distance sort value if it was the first sort criterion. If multiple sorts exist, read the exact position matching the declared sort order.

Do not blindly cast the sort value to Double. The exact Java type depends on the serializer/client version. Inspect the runtime value and type in integration tests, then convert safely.

### 4.1. Mapping distance into a DTO

DTO example:

~~~java
public record NearbyStore(
    String id,
    String name,
    double distanceKm
) {
}
~~~

Illustrative mapping when geo-distance is the first sort and the API returns a numeric sort value:

~~~java
List<NearbyStore> results =
    hits.getSearchHits().stream()
        .map(hit -> {
            Store store = hit.getContent();

            Number rawDistance =
                (Number) hit.getSortValues().get(0);

            return new NearbyStore(
                hit.getId(),
                store.getName(),
                rawDistance.doubleValue()
            );
        })
        .toList();
~~~

This example must match the sort value types of your version. If the sort list contains additional criteria, use the index corresponding to the geo-distance sort. Encapsulate reading sort values in a dedicated mapper to avoid scattering magic indices across services.

### 4.2. Sort values with multiple sorts

Example:

~~~json
{
  "sort": [
    { "_geo_distance": { "location": { "lat": 10.7769, "lon": 106.7009 }, "order": "asc", "unit": "km" } },
    { "name.keyword": "asc" },
    { "id.keyword": "asc" }
  ]
}
~~~

Each hit's sort values can contain three elements in exact order:

1. Distance.
2. name.keyword value.
3. id.keyword value.

Do not assume sort values only hold one element. Whenever changing the sort definition, update the mapper and tests accordingly.

## 5. Returning distances without geo-distance sorting

Sometimes an API wants to sort by price or relevance while still returning distance. In that case, sort values are not the only approach.

One option is using a script field to calculate distance from geo_point doc values. In Painless, geo_point offers distance methods such as arcDistance in supported contexts.

REST DSL example:

~~~http
POST /stores/_search
{
  "query": {
    "term": {
      "active": true
    }
  },
  "script_fields": {
    "distance_meters": {
      "script": {
        "lang": "painless",
        "source": "doc['location'].size() == 0 ? null : doc['location'].arcDistance(params.lat, params.lon)",
        "params": {
          "lat": 10.7769,
          "lon": 106.7009
        }
      }
    }
  },
  "sort": [
    {
      "priceInCents": {
        "order": "asc"
      }
    }
  ]
}
~~~

The script field computes the distance for each returned hit without altering the price-based sort order. Script field results appear under the hit's fields section, not in _source.

The arcDistance method typically returns distance in meters. If you need kilometers, divide by 1000 in the script or convert at the application layer. Confirm return types and Painless APIs on your actual Elasticsearch version.

Script fields incur computation cost. If geo-distance sort is already the primary ranking criterion, reading distance from sort values avoids maintaining a redundant script field.

### 5.1. When to use sort values, script fields, or Java calculation?

| Requirement | Appropriate approach |
|---|---|
| Sort nearest-first and return distance | Geo-distance sort, read sort values |
| Sort by price while still returning distance | Script field or compute from returned coordinates |
| Only filter within a radius, no distance needed | geo_distance query |
| Display distance for a small result set with source coordinates | Compute in Java using a chosen geospatial library |
| Compute distances in range-bucket aggregations | geo_distance aggregation |

Computing in Java only makes sense when the application already has document coordinates and accepts full responsibility for formulas, units, and error margins. When relying on Elasticsearch for sorting/filtering, maintain consistent distance semantics so displayed values match the ordering.

## 6. Geo-distance aggregation: bucketing by distance

geo_distance aggregation is a bucket aggregation. It divides documents into bands based on the distance from an origin to a geo_point field.

Example counting stores in these bands:

- Under 1 km.
- From 1 km to under 5 km.
- From 5 km to under 20 km.
- 20 km and more.

REST DSL:

~~~http
POST /stores/_search
{
  "size": 0,
  "aggs": {
    "stores_by_distance": {
      "geo_distance": {
        "field": "location",
        "origin": {
          "lat": 10.7769,
          "lon": 106.7009
        },
        "unit": "km",
        "ranges": [
          {
            "key": "under_1km",
            "to": 1
          },
          {
            "key": "1_to_5km",
            "from": 1,
            "to": 5
          },
          {
            "key": "5_to_20km",
            "from": 5,
            "to": 20
          },
          {
            "key": "20km_and_more",
            "from": 20
          }
        ]
      }
    }
  }
}
~~~

Each bucket contains a key, configured from/to bounds, and doc_count. Results can power distance filter facets or service coverage analytics.

### 6.1. Range boundary rules

For range aggregations, from is inclusive and to is exclusive. The ranges above have the following semantics:

| Key | Range |
|---|---|
| under_1km | distance < 1 km |
| 1_to_5km | 1 km <= distance < 5 km |
| 5_to_20km | 5 km <= distance < 20 km |
| 20km_and_more | distance >= 20 km |

Thus, a document at exactly 1 km belongs to the 1_to_5km bucket, not under_1km. A document at exactly 5 km belongs to 5_to_20km.

Design contiguous ranges to avoid unintended gaps or overlaps. If ranges intentionally overlap, a single document can be counted in multiple buckets and the sum of doc_count values can exceed the unique document count.

### 6.2. Counting and computing metrics per band

You can nest metric sub-aggregations:

~~~http
POST /stores/_search
{
  "size": 0,
  "aggs": {
    "stores_by_distance": {
      "geo_distance": {
        "field": "location",
        "origin": {
          "lat": 10.7769,
          "lon": 106.7009
        },
        "unit": "km",
        "ranges": [
          { "key": "under_1km", "to": 1 },
          { "key": "1_to_5km", "from": 1, "to": 5 },
          { "key": "5_to_20km", "from": 5, "to": 20 }
        ]
      },
      "aggs": {
        "by_category": {
          "terms": {
            "field": "category"
          }
        }
      }
    }
  }
}
~~~

Result structure:

~~~text
stores_by_distance
    |
    +-- under_1km
    |      +-- doc_count
    |      +-- by_category
    |
    +-- 1_to_5km
    |      +-- doc_count
    |      +-- by_category
    |
    +-- 5_to_20km
           +-- doc_count
           +-- by_category
~~~

You can replace the terms aggregation with sum, avg, min, max, or any metric fitting your data. For example, if Store has a numeric rating, you can compute the average rating for each distance band.

### 6.3. Filtering before aggregating

If you only want statistics for active stores, apply a top-level query/filter:

~~~http
POST /stores/_search
{
  "size": 0,
  "query": {
    "term": {
      "active": true
    }
  },
  "aggs": {
    "stores_by_distance": {
      "geo_distance": {
        "field": "location",
        "origin": {
          "lat": 10.7769,
          "lon": 106.7009
        },
        "unit": "km",
        "ranges": [
          { "key": "under_1km", "to": 1 },
          { "key": "1_to_5km", "from": 1, "to": 5 },
          { "key": "5_to_20km", "from": 5, "to": 20 }
        ]
      }
    }
  }
}
~~~

The top-level query restricts the document set fed into the aggregation. If you need multiple differently scoped statistics in the same response, use filter or filters aggregations as separate branches.

### 6.4. Documents with multiple geographic points

If the location field holds multiple geo_points, clarify business semantics. A store may have multiple branches or a document may hold multiple positions. Nearest distance, farthest distance, or whether any point falls inside a range can lead to different interpretations.

With multi-point data, verify the behavior of geo_distance aggregation on your Elasticsearch version and consider modeling each branch as its own document if reports need to count individual locations. Avoid counting one document multiple times unintentionally.

## 7. Differences between geo_distance query, sort, and aggregation

All three features use distance, yet serve different roles:

| Feature | Question answered | Result |
|---|---|---|
| geo_distance query | Is the document within the radius? | Filtered set of documents |
| _geo_distance sort | Which document is closer? | Hit ordering and sort values |
| geo_distance aggregation | How many documents fall in each distance band? | Buckets and doc_count/metrics |

A single request can combine all three:

- geo_distance query limits stores within 20 km.
- _geo_distance sort brings the nearest store to the top.
- geo_distance aggregation counts stores across 0–1, 1–5, and 5–20 km bands.

Example:

~~~http
POST /stores/_search
{
  "size": 20,
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "active": true
          }
        },
        {
          "geo_distance": {
            "distance": "20km",
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
        "unit": "km",
        "distance_type": "arc"
      }
    },
    {
      "id.keyword": "asc"
    }
  ],
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
          { "key": "under_1km", "to": 1 },
          { "key": "1_to_5km", "from": 1, "to": 5 },
          { "key": "5_to_20km", "from": 5, "to": 20 }
        ]
      }
    }
  }
}
~~~

In this example, the aggregation runs over the documents matched by the query—meaning only active stores within 20 km. If you need distance-band statistics over all stores while hits display a differently filtered subset, design an explicit aggregation scope such as a filter aggregation or global aggregation.

## 8. NativeQuery with geo-distance sort in Spring Data Elasticsearch

With Spring Data Elasticsearch 5.x, NativeQuery uses types from the Elasticsearch Java API Client. Geo-distance sort is expressed with SortOptions and GeoLocation.

Illustrative example:

~~~java
import java.util.List;

import co.elastic.clients.elasticsearch._types.DistanceUnit;
import co.elastic.clients.elasticsearch._types.GeoDistance;
import co.elastic.clients.elasticsearch._types.SortOptions;
import co.elastic.clients.elasticsearch._types.SortOrder;
import co.elastic.clients.elasticsearch._types.SortMode;
import co.elastic.clients.elasticsearch._types.GeoLocation;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

double originLat = 10.7769;
double originLon = 106.7009;

GeoLocation origin = GeoLocation.of(g -> g
    .latlon(p -> p
        .lat(originLat)
        .lon(originLon)
    )
);

SortOptions distanceSort = SortOptions.of(s -> s
    .geoDistance(g -> g
        .field("location")
        .location(origin)
        .order(SortOrder.Asc)
        .unit(DistanceUnit.Kilometers)
        .distanceType(GeoDistance.Arc)
        .mode(SortMode.Min)
    )
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(activeAndNearbyQuery)
    .withSort(List.of(distanceSort))
    .build();

SearchHits<Store> hits =
    operations.search(nativeQuery, Store.class);
~~~

This example reflects the Spring Data Elasticsearch 5.x generation with the Elasticsearch Java API Client. Packages, location overloads, and builder methods can differ across minor versions. Use your actual dependency's autocomplete/Javadoc to verify signatures. Do not mix Elasticsearch Java API Client SortOptions with Spring Data Commons Sort in the same builder.

If a stable secondary sort is needed, append a field SortOptions after distanceSort:

~~~java
SortOptions idSort = SortOptions.of(s -> s
    .field(f -> f
        .field("id.keyword")
        .order(SortOrder.Asc)
    )
);

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(activeAndNearbyQuery)
    .withSort(List.of(distanceSort, idSort))
    .build();
~~~

Distance remains the primary criterion; ID only breaks ties when distances are equal.

## 9. NativeQuery with geo_distance aggregation

The Elasticsearch Java API Client provides builder types for geo_distance aggregations. The generated DSL structure should match the REST example:

~~~java
import co.elastic.clients.elasticsearch._types.DistanceUnit;
import co.elastic.clients.elasticsearch._types.GeoLocation;
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import co.elastic.clients.elasticsearch._types.aggregations.GeoDistanceAggregationRange;

GeoLocation origin = GeoLocation.of(g -> g
    .latlon(p -> p
        .lat(originLat)
        .lon(originLon)
    )
);

Aggregation distanceBands = Aggregation.of(a -> a
    .geoDistance(g -> g
        .field("location")
        .origin(origin)
        .unit(DistanceUnit.Kilometers)
        .ranges(
            GeoDistanceAggregationRange.of(r -> r
                .key("under_1km")
                .to(1.0)
            ),
            GeoDistanceAggregationRange.of(r -> r
                .key("1_to_5km")
                .from(1.0)
                .to(5.0)
            ),
            GeoDistanceAggregationRange.of(r -> r
                .key("5_to_20km")
                .from(5.0)
                .to(20.0)
            )
        )
    )
);
~~~

Then attach the aggregation to NativeQuery:

~~~java
NativeQuery aggregationQuery = NativeQuery.builder()
    .withQuery(activeQuery)
    .withAggregation("distance_bands", distanceBands)
    .withMaxResults(0)
    .build();
~~~

The GeoDistanceAggregationRange type name, ranges overloads, and how max results is set must match the Elasticsearch Java API Client and Spring Data Elasticsearch versions in your project. If the IDE rejects an overload, inspect the Javadoc of Aggregation.Builder and GeoDistanceAggregation.Builder. The REST DSL from earlier examples serves as the reference to confirm the final request structure.

## 10. Reading geo-distance sort values from SearchHit

When executing a search via Operations:

~~~java
SearchHits<Store> hits =
    operations.search(nativeQuery, Store.class);
~~~

You can read each hit:

~~~java
for (SearchHit<Store> hit : hits) {
    String id = hit.getId();
    Store store = hit.getContent();
    List<Object> sortValues = hit.getSortValues();

    // The geo-distance sort value lies at that sort's index.
}
~~~

Create a dedicated converter method:

~~~java
private double readDistanceKm(SearchHit<?> hit, int sortIndex) {
    Object raw = hit.getSortValues().get(sortIndex);

    if (!(raw instanceof Number number)) {
        throw new IllegalStateException(
            "Geo-distance sort value is not numeric"
        );
    }

    return number.doubleValue();
}
~~~

If the project targets a Java version below 16, replace pattern matching instanceof with an explicit cast to Number after the type check.

Do not hardcode sortIndex = 0 in multiple places. Define the sort order in one place and let the mapper know which position holds the distance sort value. When adding a preceding secondary sort, the distance value's index can shift.

### 10.1. Converting to meters or kilometers

If the query declares unit km, sort values normally represent kilometers. If the query declares unit m, sort values represent meters.

You can normalize responses:

~~~java
double distanceKm = distanceValueInMeters / 1000.0;
~~~

Never convert twice. Name variables with explicit units such as distanceMeters or distanceKm rather than a generic distance.

### 10.2. Formatting distances for display

The DTO should preserve the numeric value so clients can use it for logic or maps:

~~~java
public record NearbyStoreResponse(
    String id,
    String name,
    double distanceMeters,
    String distanceLabel
) {
}
~~~

The service can produce labels:

- 350 m
- 1.2 km
- 8.4 km

Rounding rules belong in the presentation layer or API mapper. Never round before sorting or bucketing, as doing so can collapse distinct distances into equal values and scramble ordering.

## 11. Geo bounds and related spatial aggregations

In addition to geo_distance aggregation, Elasticsearch provides other bucket/metric aggregations for location analytics:

- geo_bounds: returns the bounding box enclosing the points.
- geohash_grid: groups points into geohash cells.
- geotile_grid: groups points into map tiles.
- geo_centroid: computes the geographic centroid of points.

geo_bounds example:

~~~http
POST /stores/_search
{
  "size": 0,
  "aggs": {
    "store_bounds": {
      "geo_bounds": {
        "field": "location",
        "wrap_longitude": true
      }
    }
  }
}
~~~

geo_bounds is useful for determining the bounding area around a set of stores to fit the map viewport. It does not return each store's distance to an origin.

geotile_grid example:

~~~http
POST /stores/_search
{
  "size": 0,
  "aggs": {
    "stores_per_tile": {
      "geotile_grid": {
        "field": "location",
        "precision": 7
      }
    }
  }
}
~~~

geotile_grid buckets points by tile, useful for heatmaps or dense maps. Higher precision produces smaller tiles and potentially more buckets.

If the business question is "how many stores within 1 km, 5 km, 20 km," use geo_distance aggregation. If the question is "which map regions have the highest store concentration," consider geotile_grid or geohash_grid.

## 12. Pagination when sorting by distance

You can use from/size for the initial page and subsequent pages:

~~~http
POST /stores/_search
{
  "from": 0,
  "size": 20,
  "query": {
    "geo_distance": {
      "distance": "20km",
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
    },
    {
      "id.keyword": "asc"
    }
  ]
}
~~~

For large datasets, deep from/size pagination is expensive. You can use search_after with the sort values from the last hit of the previous page.

Example where the last hit had sort values:

~~~json
[2.75, "S-1020"]
~~~

Next page:

~~~http
POST /stores/_search
{
  "size": 20,
  "search_after": [2.75, "S-1020"],
  "query": {
    "geo_distance": {
      "distance": "20km",
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
    },
    {
      "id.keyword": "asc"
    }
  ]
}
~~~

Rules:

- Keep query, origin, unit, and sort identical across pages.
- Pass the exact sort values from the previous page's last hit.
- Add a unique tie-breaker such as id.keyword.
- Never recalculate sort values from _source.
- If a consistent snapshot is needed while the index changes, consider Point in Time (PIT) with search_after when supported by your Elasticsearch version.

If the origin changes between pages, distance sort values no longer share the same reference point. Therefore, keep the origin fixed throughout the pagination session.

## 13. Combining relevance and distance

An application may search stores by name or description while wanting to favor stores close to the user. Several strategies exist:

- Sort by distance first, breaking ties with relevance.
- Sort by _score first, breaking ties with distance.
- Use function_score or distance_feature to blend proximity into the score.
- Filter radius with geo_distance, then sort by relevance.

Example with distance as the primary priority:

~~~http
POST /stores/_search
{
  "query": {
    "match": {
      "name": "coffee"
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
    {
      "_score": "desc"
    },
    {
      "id.keyword": "asc"
    }
  ]
}
~~~

Example with relevance as the primary priority:

~~~http
POST /stores/_search
{
  "query": {
    "match": {
      "name": "coffee"
    }
  },
  "sort": [
    {
      "_score": "desc"
    },
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
      "id.keyword": "asc"
    }
  ]
}
~~~

The order in the sort array defines priority. You cannot flip a single flag to make Elasticsearch magically balance closeness and relevance according to business rules. If both factors should contribute to a single score, design a function_score/distance_feature configuration and evaluate rankings on real data.

## 14. Distance feature and function score

Elasticsearch provides the distance_feature query to boost the score of documents closer to an origin on a supported date or geo_point field.

Conceptual example:

~~~http
POST /stores/_search
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
      "should": [
        {
          "distance_feature": {
            "field": "location",
            "origin": {
              "lat": 10.7769,
              "lon": 106.7009
            },
            "pivot": "5km"
          }
        }
      ]
    }
  },
  "sort": [
    { "_score": "desc" }
  ]
}
~~~

distance_feature produces a score signal based on distance. pivot controls how quickly the score decays with distance. It fits scenarios where relevance and proximity should jointly affect ranking instead of sorting strictly by one criterion.

Understand that distance_feature is a ranking mechanism, not a way to return actual distances to the client. If the API needs exact kilometer numbers, you still need geo-distance sort values, script fields, or coordinate-based calculation.

function_score is even more flexible, allowing query scores to be combined with decay functions over geo_point or other fields. Score tuning can heavily alter rankings; inspect results with Explain and an evaluation query set rather than picking pivots or weights by guesswork.

## 15. Performance and limits

Geo-distance sorting, aggregations, and script fields all carry computational cost. Contributing factors include:

- Number of candidate documents.
- Number of shards and indices queried.
- Number of hits to sort/return.
- Number of geo_point fields and points per document.
- Distance type and unit.
- Number of buckets in geo_distance aggregations.
- Depth of nested sub-aggregations.
- Whether script fields are evaluated across many hits.
- Deep pagination.

Several guidelines:

- Bound the radius with a geo_distance query whenever business logic has a defined range.
- Use filters for category, active, tenant, and access-control conditions.
- Limit size/page size.
- Only request needed aggregations.
- Keep range bucket counts tailored to the UI.
- Use sort values instead of script fields when already sorting by distance.
- Add a stable tie-breaker when paginating.
- Benchmark queries at production-like data scale.

With multi-dimensional nested aggregations, bucket counts can explode and hit search.max_buckets limits. Do not generate thousands of distance bands when the UI only needs a handful of groups.

## 16. Testing distances and ordering

Integration tests should index points at varying distances around an origin. Do not hardcode distances to many decimal places if tests depend on calculation methods and versions; verify ordering and bucket membership appropriately.

Sample data:

~~~java
GeoPoint origin = new GeoPoint(10.7769, 106.7009);

Store near = new Store(
    "S-NEAR",
    "Nearby Store",
    "grocery",
    true,
    new GeoPoint(10.7770, 106.7010)
);

Store far = new Store(
    "S-FAR",
    "Far Store",
    "grocery",
    true,
    new GeoPoint(10.9000, 106.9000)
);
~~~

Save the documents and refresh the index in tests before searching:

~~~java
operations.save(List.of(near, far));
operations.indexOps(Store.class).refresh();
~~~

Then execute the geo-distance sort and verify:

- S-NEAR appears before S-FAR.
- The sort value is numeric and uses the expected unit.
- Documents missing location are handled according to policy.
- Out-of-radius results are excluded by the geo_distance query.
- Secondary sort preserves stable order when two points have equal or nearly equal distances.

For geo_distance aggregations, create documents on each side of the boundaries, such as 0.5 km, 1 km, 3 km, and 7 km. Confirm doc_count in the proper buckets. Exact boundary tests catch inclusive/exclusive mistakes.

## 17. Reading aggregation and sort metadata in Spring Data

A search response can contain both hits and aggregations. SearchHit holds each document's content along with metadata; SearchHits holds the hit list and the aggregation container.

Pattern for reading sort values:

~~~java
for (SearchHit<Store> hit : searchHits) {
    Store store = hit.getContent();
    List<Object> sortValues = hit.getSortValues();

    // Map content and geo-distance value into response DTO.
}
~~~

Pattern for reading aggregations:

~~~java
SearchHits<Store> searchHits =
    operations.search(aggregationQuery, Store.class);

AggregationsContainer<?> container =
    searchHits.getAggregations();
~~~

In Spring Data Elasticsearch 5.x with the Elasticsearch Java API Client, the container is typically ElasticsearchAggregations. You can look up an aggregate by name and read the corresponding geo-distance variant. Wrapper names, accessors, and bucket types vary across client versions.

For geo_distance aggregations, the response includes a bucket list with key, from, to, and doc_count. If metric aggregations are nested, each bucket contains sub-aggregates. Map results into application DTOs instead of returning Elasticsearch client union types directly from REST APIs.

## 18. Choosing the right way to return distance

| API requirement | Recommended approach |
|---|---|
| Nearest list with distance for each hit | _geo_distance sort + SearchHit sort values |
| List sorted by price while still displaying distance | Script field or compute from source coordinates |
| Only filter within a radius | geo_distance query |
| Count places by distance bands | geo_distance aggregation |
| Analyze density across map regions | geotile_grid or geohash_grid |
| Return bounding box around results | geo_bounds |
| Combine relevance and proximity | distance_feature/function_score or multi-sort |
| Deep pagination sorted by distance | search_after + stable sort, consider PIT |

A place-search endpoint should normally return a distance number with an explicit unit, such as distanceMeters or distanceKm. Never return an unlabelled number and leave the frontend to guess the unit.

## 19. Common mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| Geo-distance sort fails | location is not geo_point | Check mapping |
| Farther stores appear first | Used order desc instead of asc | Use asc for nearest first |
| Sort works but radius is unrestricted | Sort present without geo_distance query | Add geo_distance filter |
| Distances are wildly wrong | Swapped latitude and longitude | Check constructor, JSON object, and array conventions |
| Distances show wrong unit | Query uses km while DTO labels m, or vice versa | Standardize unit and field names |
| Cannot read distance from entity | Distance lives in hit sort metadata | Read SearchHit.getSortValues() |
| Wrong sort value index read | Multiple sort criteria present | Use the exact index matching the sort definition |
| Multi-location document orders unexpectedly | min/max/avg mode not specified | Pick the mode matching business logic |
| Aggregation missing buckets | Ranges do not span full interval or documents lack location | Inspect ranges and data |
| Total doc_count exceeds document count | Overlapping ranges or multi-point documents | Review semantics and mapping |
| NativeQuery fails to compile | Different API client version or imports | Check Javadoc and packages |
| search_after duplicates/skips hits | Missing tie-breaker or origin/sort changed | Keep query and sort identical, add unique field |
| Script field is slow | Evaluating distance across too many hits | Use sort values or cap hit count |
| Aggregation exceeds bucket limit | Too many ranges or nested buckets | Reduce buckets and scope |

## 20. Workflow for designing a nearby endpoint

An endpoint finding stores near a user can be designed in this sequence:

1. Receive latitude and longitude from the client.
2. Validate coordinates and establish the origin.
3. Determine maximum radius and a consistent unit.
4. Build a bool filter for status, category, tenant, and access permissions.
5. Add a geo_distance query to cap the radius.
6. Add _geo_distance sort asc to put the nearest stores first.
7. Add a unique keyword tie-breaker for stable ordering.
8. Cap page size.
9. Read distance from SearchHit sort values and map into a DTO.
10. If the UI needs statistics, add a geo_distance aggregation with non-overlapping ranges.
11. If deep pagination is needed, use search_after with fixed origin/query/sort.
12. Write integration tests for coordinates, units, range boundaries, and sort order.

A response DTO might look like:

~~~java
public record NearbyStoreResponse(
    String id,
    String name,
    String category,
    double distanceMeters
) {
}
~~~

If the API needs a display label, add distanceLabel in the mapper layer. Keep the underlying numeric value so clients can sort or process it accurately.

## 21. Quick reference table

| Goal | Elasticsearch |
|---|---|
| Filter points within a radius | geo_distance query |
| Sort nearest first | _geo_distance sort with order asc |
| Sort farthest first | _geo_distance sort with order desc |
| Choose geographic calculation method | distance_type arc/plane |
| Choose unit | unit m/km/mi/... |
| Pick closest point in multi-valued field | mode min |
| Read each hit's distance | sort values in SearchHit |
| Return distance even when sorting by another field | script_fields or compute from source coordinates |
| Group into distance bands | geo_distance aggregation |
| Aggregate by category inside each band | Sub-aggregation |
| Obtain bounding box | geo_bounds |
| Bucket points into map tiles | geotile_grid |
| Combine relevance and distance | distance_feature/function_score or multi-sort |
| Deep pagination | search_after and unique tie-breaker |

Geo-distance queries, sorts, and aggregations all build on geo_point yet play distinct roles: queries restrict scope, sorts rank by distance, and aggregations summarize across bands. When returning distances for individual hits, geo-distance sorting supplies sort values in your chosen unit; Spring Data preserves those values in SearchHit metadata rather than injecting them into the entity. Keep origin, latitude/longitude, units, and distance semantics consistent across queries, sorts, aggregations, and DTOs; add a stable tie-breaker for pagination, and reserve script fields for cases where distance is needed independently of sorting.