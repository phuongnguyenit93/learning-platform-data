# Testing Boundary Points, Missing Data, and Geospatial Accuracy

Geospatial queries often look simple: find places within a 5 km radius, find points inside a rectangle, or check whether a location falls inside a service zone. Yet results can go wrong if the application reverses latitude/longitude order, ignores missing coordinates, rounds coordinates too early, or assumes a point directly on a boundary behaves identically across every spatial operation.

When using Spring Data Elasticsearch, you must test input validation, mappings, and query results against a real Elasticsearch cluster. Critical cases include:

- Points inside, outside, and directly on the boundary of the search area.
- Missing geospatial fields, null values, empty arrays, or invalid coordinates.
- Coordinates near the international date line, North/South poles, or zone borders.
- Errors caused by coordinate precision, distance formulas, and rounding.
- Differences among `geo_distance`, `geo_bounding_box`, and `geo_shape`.

This lesson uses `geo_point` as the primary example and applies to geospatial testing in Spring Data Elasticsearch.

## 1. Geospatial data in Elasticsearch

Elasticsearch supports several geospatial data types. Two common types are:

| Type | Stores | Common queries |
|---|---|---|
| `geo_point` | A latitude/longitude point | Distance, bounding box, distance sorting |
| `geo_shape` | Geometries such as point, line, polygon, multipolygon | Intersects, within, contains, disjoint |

A store typically only needs a single coordinate point:

~~~json
{
  "storeId": "STORE-001",
  "name": "District 1 Store",
  "location": {
    "lat": 10.762622,
    "lon": 106.660172
  }
}
~~~

A delivery zone may require a polygon:

~~~json
{
  "serviceArea": {
    "type": "polygon",
    "coordinates": [
      [
        [106.65, 10.75],
        [106.68, 10.75],
        [106.68, 10.78],
        [106.65, 10.78],
        [106.65, 10.75]
      ]
    ]
  }
}
~~~

With `geo_point`, latitude and longitude order is a frequent pitfall. In GeoJSON and coordinate arrays, the order is **longitude first, latitude second**. In objects with named properties, Elasticsearch uses `lat` and `lon`. Never infer order from two raw numbers alone.

## 2. Declaring geo_point in Spring Data Elasticsearch

You can use Spring Data Elasticsearch's `GeoPoint` type and annotate the field with `FieldType.GeoPoint`:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Document(indexName = "stores")
public class StoreDocument {

    @Id
    private String id;

    private String name;

    @Field(type = FieldType.GeoPoint)
    private GeoPoint location;

    // Constructors, getters and setters
}
~~~

Construct a point using the constructor taking latitude first, longitude second:

~~~java
GeoPoint location = new GeoPoint(10.762622, 106.660172);
~~~

Verify the GeoPoint constructor signature for the Spring Data Elasticsearch version your project uses. When building custom DTOs or parsers, name parameters explicitly as `latitude` and `longitude`, avoiding generic variables like `x` and `y`.

Corresponding Elasticsearch mapping:

~~~json
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
~~~

Do not let dynamic mapping infer a location field as a regular object. Declare `geo_point` explicitly before indexing data.

## 3. Coordinate formats and latitude/longitude order

Elasticsearch accepts multiple `geo_point` representations. Understand the exact order for each format.

| Format | Example | Order |
|---|---|---|
| Object | `{"lat":10.76,"lon":106.66}` | Explicit property names |
| Array | `[106.66,10.76]` | longitude, latitude |
| String | `"10.76,106.66"` | latitude, longitude |
| WKT | `"POINT (106.66 10.76)"` | longitude, latitude |
| GeoJSON Point | `{"type":"Point","coordinates":[106.66,10.76]}` | longitude, latitude |

Two ways of representing the same point:

~~~json
{
  "location": {
    "lat": 10.762622,
    "lon": 106.660172
  }
}
~~~

~~~json
{
  "location": [
    106.660172,
    10.762622
  ]
}
~~~

If swapped to `[10.762622, 106.660172]`, Elasticsearch may still accept it because both numbers lie within valid bounds, yet the point lands in a completely different geographic location. This bug is dangerous because the request is not guaranteed to be rejected.

Standardize on one format across the application. Objects with explicit `lat` and `lon` keys are usually easiest to read and least prone to mistakes when storing JSON.

## 4. Validating valid coordinate ranges

For standard geographic coordinates:

- Latitude ranges from -90 to 90 degrees.
- Longitude ranges from -180 to 180 degrees.
- Latitude 0 and longitude 0 are both valid values.
- Point `(0, 0)` is a real geographic location, not an indicator of missing data.

Java validation example:

~~~java
public record Coordinates(double latitude, double longitude) {

    public Coordinates {
        if (!Double.isFinite(latitude)
                || latitude < -90.0
                || latitude > 90.0) {
            throw new IllegalArgumentException(
                    "Latitude must be between -90 and 90"
            );
        }

        if (!Double.isFinite(longitude)
                || longitude < -180.0
                || longitude > 180.0) {
            throw new IllegalArgumentException(
                    "Longitude must be between -180 and 180"
            );
        }
    }
}
~~~

Check for `NaN`, `Infinity`, and `-Infinity` as well. They are not valid coordinates. When ingesting from JSON, GPS, or mapping services, validate at the system boundary before instantiating entities.

Never automatically replace invalid coordinates with `(0, 0)`. Doing so turns corrupted data into a valid point and silently skews geospatial search results.

## 5. Missing data and the semantics of exists queries

A geospatial field can be missing in several situations:

- The document omits the `location` property.
- JSON sends `"location": null`.
- The value is represented as an empty array.
- Data was dropped during indexing due to mapping configuration.
- One index in an alias lacks a mapping for that field.

For `geo_point`, an exists query checks whether the field holds an indexed geospatial value.

Find stores with coordinates:

~~~json
{
  "query": {
    "exists": {
      "field": "location"
    }
  }
}
~~~

Find stores missing coordinates:

~~~json
{
  "query": {
    "bool": {
      "must_not": [
        {
          "exists": {
            "field": "location"
          }
        }
      ]
    }
  }
}
~~~

Distinguish these cases:

| Data | exists result on location |
|---|---|
| Field omitted | Does not match |
| `"location": null` | Does not match by default |
| Empty array | No value to index |
| Point `(0, 0)` | Matches; this is a valid coordinate |
| A valid geo_point | Matches |

Exists does not check whether the property appears in the original JSON. It checks whether an indexed value exists in the inverted/spatial structures. If the mapping or indexing skipped the value, the document might still retain data in `_source` without matching exists.

### Combining exists with geospatial queries

If you only want stores that have coordinates and lie within a radius, combine exists with the geospatial query:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "exists": {
            "field": "location"
          }
        },
        {
          "geo_distance": {
            "distance": "5km",
            "location": {
              "lat": 10.762622,
              "lon": 106.660172
            }
          }
        }
      ]
    }
  }
}
~~~

In this example, exists clarifies the business requirement and separates documents with locations from those without. The geo query itself can also only match indexed geospatial values.

## 6. Handling invalid coordinates and ignore_malformed

By default, an invalid `geo_point` value causes indexing the document to fail. The mapping can configure `ignore_malformed` to skip invalid values rather than rejecting the entire document:

~~~json
{
  "mappings": {
    "properties": {
      "location": {
        "type": "geo_point",
        "ignore_malformed": true
      }
    }
  }
}
~~~

When enabling this option, understand that bad location data will not be indexed as expected. The document can still be saved with its other fields while geo queries never find its location.

Do not enable `ignore_malformed` just to silence input errors. For delivery data, store positions, or service zones, a skipped coordinate can produce wrong business results.

Maintain two layers of control:

1. Validate coordinates in the application and return clear errors to the data source.
2. Configure mappings to define whether Elasticsearch rejects or ignores invalid values.

If you need to persist a document while flagging an invalid location, store an explicit status field such as `locationStatus` or `locationValidationError`. Never substitute placeholder coordinates.

## 7. Testing interior, exterior, and boundary points for geo_distance

The geo distance query finds documents whose point falls within a radius from a center.

Example:

~~~json
{
  "query": {
    "geo_distance": {
      "distance": "5km",
      "location": {
        "lat": 10.762622,
        "lon": 106.660172
      }
    }
  }
}
~~~

With a 5 km radius, include at least three test groups:

- A point clearly inside, such as 4.9 km from the center.
- A point right on the 5 km threshold.
- A point clearly outside, such as 5.1 km from the center.

Do not only test one point very close to the center and one point very far away. Boundary bugs commonly surface from unit conversions, coordinate rounding, or distance handling.

### Recommended test dataset

| Case | Position relative to center | Expected result |
|---|---|---|
| At center | 0 m | Matches |
| Inside | Clearly less than radius | Matches |
| Just inside boundary | Radius minus epsilon | Matches |
| On boundary | Equal to radius per test data | Verify version semantics |
| Just outside boundary | Radius plus epsilon | Does not match |
| Outside | Clearly greater than radius | Does not match |
| Missing location | No geo value | Does not match |

Geo distance queries are generally interpreted as distance not exceeding the radius. However, exact-boundary tests require carefully generated data executed against your project's actual Elasticsearch version. Never pick rounded coordinates off a map and treat them as exact to the meter.

### Do not use rounded coordinates to craft boundary tests

One degree of latitude is roughly 111 km, whereas one degree of longitude varies with latitude. Using an approximate constant to place boundary points can leave them slightly inside or outside the radius.

For accurate tests, compute destination points by distance and bearing on a spherical model using the same unit convention as your test. Then add two epsilon-shifted points well outside representation error on either side of the boundary.

A formula to compute a destination point on a sphere with Earth radius \(R\):

\[
\delta = \frac{d}{R}
\]

\[
\varphi_2 =
\arcsin(
\sin \varphi_1 \cos \delta +
\cos \varphi_1 \sin \delta \cos \theta
)
\]

\[
\lambda_2 =
\lambda_1 +
\operatorname{atan2}(
\sin \theta \sin \delta \cos \varphi_1,
\cos \delta - \sin \varphi_1 \sin \varphi_2
)
\]

Where:

- \(\varphi_1, \lambda_1\) are the starting latitude/longitude in radians.
- \(d\) is the desired distance.
- \(R\) is the chosen Earth-model radius.
- \(\theta\) is the bearing.
- \(\varphi_2, \lambda_2\) are the destination coordinates.

This formula produces controlled test data. Elasticsearch results can still differ slightly due to distance models, coordinate encoding, and numerical rules; hence, include dedicated boundary and epsilon tests.

## 8. Distance accuracy: arc and plane

Geo distance queries support multiple distance calculation types. For `geo_distance`, `arc` is Elasticsearch's default and suits most scenarios requiring geographic distance on the Earth's surface.

You can configure:

~~~json
{
  "query": {
    "geo_distance": {
      "distance": "5km",
      "distance_type": "arc",
      "location": {
        "lat": 10.762622,
        "lon": 106.660172
      }
    }
  }
}
~~~

| Type | Characteristics | Notes |
|---|---|---|
| `arc` | Computes arc distance on a sphere | More appropriate for general geographic distances |
| `plane` | Planar approximation | Can be faster, but error increases with distance and position |

Do not choose `plane` just for speed without measuring error across your real data region. At short distances and small areas, error may be acceptable; over long distances, near poles, or across wide regions, results can diverge substantially.

### Distance units

Elasticsearch supports units such as:

- `m`: meter.
- `km`: kilometer.
- `cm`: centimeter.
- `mm`: millimeter.
- `mi`: mile.
- `yd`: yard.
- `ft`: foot.
- `nmi`: nautical mile.

For example, `5000m` and `5km` denote the same radius. Use explicit units in queries and keep units consistent across application APIs.

Do not manually convert distance into latitude/longitude degrees and run range queries when the business goal is a geographic radius. One degree of longitude does not equal the same distance at every latitude.

## 9. Testing geo_bounding_box along edges

Geo bounding box finds points inside a rectangle defined by top-left and bottom-right corners.

~~~json
{
  "query": {
    "geo_bounding_box": {
      "location": {
        "top_left": {
          "lat": 10.80,
          "lon": 106.60
        },
        "bottom_right": {
          "lat": 10.70,
          "lon": 106.72
        }
      }
    }
  }
}
~~~

Test these scenarios:

- Points well inside.
- Points outside the north, south, east, and west edges.
- Points directly on each edge.
- Points directly at all four corners.
- Points missing location.
- Bounding boxes whose longitudes cross the international date line.

For ordinary bounding boxes, edges are determined by min/max coordinates. Build fixtures right on each edge and confirm the behavior of your running Elasticsearch version. Do not deduce results merely from drawing a rectangle on a map, as maps may use projections that differ from geographic coordinates.

### International date line

A bounding box near +180° and -180° longitude requires dedicated testing. Those two longitudes are geographically adjacent despite differing arithmetically by nearly 360 degrees.

If the application serves global data, write tests for:

- A point just east of the date line.
- A point just west of the date line.
- A point far outside the bounding box.
- A rectangle crossing the date line.

Do not normalize a dateline-crossing bounding box by sorting longitudes ascending without accounting for geo query semantics.

## 10. Testing geo_shape and geometric relations

With `geo_shape`, Elasticsearch supports spatial relations such as:

| Relation | General meaning |
|---|---|
| `intersects` | The two geometries share an intersection |
| `within` | The query geometry lies inside the indexed geometry |
| `contains` | The indexed geometry contains the query geometry |
| `disjoint` | The two geometries do not intersect |

Example of a service area stored as a polygon:

~~~json
{
  "mappings": {
    "properties": {
      "serviceArea": {
        "type": "geo_shape"
      }
    }
  }
}
~~~

Document:

~~~json
{
  "serviceArea": {
    "type": "polygon",
    "coordinates": [
      [
        [106.65, 10.75],
        [106.68, 10.75],
        [106.68, 10.78],
        [106.65, 10.78],
        [106.65, 10.75]
      ]
    ]
  }
}
~~~

When testing polygons, include points that are:

- Strictly inside the polygon.
- Outside the polygon.
- Directly on an edge.
- Directly at a vertex.
- Inside a hole if the polygon has holes.
- On or near the border between two service areas.

For `within`, `contains`, and `intersects`, semantics apply in order between the query geometry and the indexed geometry. Read the relation direction carefully. Reversing the direction produces the opposite of the business requirement.

For points lying right on a polygon boundary, do not assume every relation treats them identically. Determine the required relation and write dedicated tests for points on edges, vertices, and epsilon offsets. If business rules must include boundaries, select a relation and geometry rules that reflect that requirement explicitly.

## 11. Testing polar data and special coordinate regions

Geographic coordinates do not behave like a regular Cartesian grid everywhere. Certain regions require dedicated tests:

- Near latitude +90° or -90°.
- Near longitude +180° or -180°.
- Two points on opposite sides of the date line.
- Very close points at high latitudes.
- Polygons crossing a pole or the date line.

Near the poles, small longitude changes do not correspond to the same distances as at the equator. If the application computes distances manually with flat formulas, results will be wrong.

A global geospatial test suite should include at least one case near the equator, one at high latitude, and one across the date line. If a product serves only one region, still test boundary coordinates of that region and verify that out-of-region data is rejected.

## 12. Coordinate error and tolerance strategies

Coordinates from GPS, mobile devices, or mapping services inherently contain measurement error. Beyond measurement noise, results are affected by:

- Input precision and the number of stored decimal places.
- Coordinate encoding inside index structures.
- Distance calculation models.
- Unit conversions.
- Rounding for display.
- Quality and accuracy of the GPS source.

Do not assert distances using exact floating-point equality in code:

~~~java
if (actualDistance == expectedDistance) {
    // Do not rely on exact double equality.
}
~~~

Instead, apply an acceptable tolerance aligned with business needs:

~~~java
double toleranceMeters = 2.0;

assertThat(Math.abs(actualDistanceMeters - expectedDistanceMeters))
        .isLessThanOrEqualTo(toleranceMeters);
~~~

Tolerance has no universal constant for every application. A nearest-store finder might accept several meters of error; an app enforcing safety zones or boundary-based pricing needs stricter rules and may require specialized cadastral data sources.

Distinguish between:

- **Precision**: the granularity that data and systems can represent.
- **Accuracy**: how close a value is to the true physical location.
- **Tolerance**: the margin of error accepted by tests or business logic.

Adding more decimal digits does not automatically make GPS more accurate. Do not store or display false precision just because coordinates carry many digits.

## 13. Where should coordinates be rounded?

Do not round coordinates before saving or before querying if business logic relies on accurate distances. For example, rounding latitude/longitude to two decimal places can shift positions by hundreds of meters to over a kilometer depending on latitude.

Separate concerns:

- Store original coordinates at the precision supported by the source and business rules.
- Use unrounded coordinates in geo queries.
- Only round distance numbers for display.
- If input normalization is needed, define explicit rules and preserve source accuracy (when available).

For example, an API response may display `1.23 km`, while radius filtering should use fuller coordinate precision and unrounded distances.

If input data has low accuracy, you can store `accuracyMeters` from the device as well. The application can then decide how to handle points near boundaries based on measurement uncertainty rather than relying solely on a single point.

## 14. Testing with Spring Data Elasticsearch and NativeQuery

You can build geo queries using the Elasticsearch Java API Client and wrap them in `NativeQuery`.

Example finding stores within a 5 km radius:

~~~java
import co.elastic.clients.elasticsearch._types.GeoLocation;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

GeoLocation center = GeoLocation.of(g -> g
        .latlon(point -> point
                .lat(10.762622)
                .lon(106.660172)
        )
);

Query distanceQuery = Query.of(q -> q
        .geoDistance(g -> g
                .field("location")
                .distance("5km")
                .location(center)
        )
);

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(distanceQuery)
        .build();

SearchHits<StoreDocument> hits =
        operations.search(nativeQuery, StoreDocument.class);
~~~

In this example:

- `GeoLocation` represents the center coordinates.
- `lat(...)` accepts latitude.
- `lon(...)` accepts longitude.
- `geoDistance(...)` creates the geo distance query.
- `field("location")` specifies the `geo_point` field.
- `distance("5km")` specifies the radius.
- `NativeQuery` passes the Java Client's Query DSL into Spring Data.
- `SearchHits` holds results mapped to entities.

Builder methods can vary slightly across Elasticsearch Java API Client versions. Use dependencies compatible with your project's Spring Data Elasticsearch and check the Javadoc if signatures differ.

### Finding documents missing coordinates

~~~java
Query missingLocation = Query.of(q -> q
        .bool(b -> b
                .mustNot(mn -> mn
                        .exists(e -> e.field("location"))
                )
        )
);

NativeQuery missingLocationQuery = NativeQuery.builder()
        .withQuery(missingLocation)
        .build();

SearchHits<StoreDocument> storesWithoutLocation =
        operations.search(
                missingLocationQuery,
                StoreDocument.class
        );
~~~

This query finds documents without an indexed value for `location`. It does not check whether the raw JSON string contains the property.

### Combining exists and geo_distance

~~~java
Query hasLocation = Query.of(q -> q
        .exists(e -> e.field("location"))
);

Query nearby = Query.of(q -> q
        .geoDistance(g -> g
                .field("location")
                .distance("5km")
                .location(center)
        )
);

Query validNearby = Query.of(q -> q
        .bool(b -> b
                .filter(hasLocation)
                .filter(nearby)
        )
);
~~~

Then attach `validNearby` to `NativeQuery` and execute as in the previous example.

## 15. Creating purposeful test datasets

An integration test should index documents representing each scenario instead of relying solely on random data.

Fixture example:

| ID | location | Purpose |
|---|---|---|
| `CENTER` | Center coordinates | Verify zero distance |
| `INSIDE` | Clearly under radius from center | Verify interior point |
| `NEAR_EDGE_IN` | Just inside the boundary | Verify interior epsilon |
| `ON_EDGE` | Computed at exact radius distance | Verify boundary semantics |
| `NEAR_EDGE_OUT` | Just outside the boundary | Verify exterior epsilon |
| `OUTSIDE` | Farther than radius from center | Verify exterior point |
| `NO_LOCATION` | No location field | Verify missing data |
| `NULL_LOCATION` | Null location | Verify null handling |
| `ZERO_POINT` | Latitude 0, longitude 0 | Ensure 0,0 is not treated as missing |
| `INVALID_POINT` | Out-of-range coordinates | Verify validation/mapping |

Do not index `INVALID_POINT` in the same test case using default mapping when the goal is testing queries; the write operation may fail before the query runs. Separate invalid-indexing/validation tests into their own test cases.

After writing fixtures, refresh the index before executing searches in tests. You can use `IndexOperations` refresh API or the Elasticsearch Refresh API. Never rely on fixed `Thread.sleep` waits.

## 16. Integration testing against real Elasticsearch

Mocking `ElasticsearchOperations` only verifies that the service calls the expected method. It cannot test how Elasticsearch interprets geo queries, mappings, coordinate order, precision, or geometric boundaries.

Write integration tests with real Elasticsearch. Testcontainers is a popular option for running an Elasticsearch container during tests.

Gradle dependency example (using project-managed unified versions):

~~~kotlin
dependencies {
    testImplementation("org.testcontainers:elasticsearch")
    testImplementation("org.testcontainers:junit-jupiter")
}
~~~

Container example:

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.elasticsearch.ElasticsearchContainer;

@Testcontainers
class GeoSearchIntegrationTest {

    @Container
    static final ElasticsearchContainer elasticsearch =
            new ElasticsearchContainer(
                    "docker.elastic.co/elasticsearch/elasticsearch:<compatible-version>"
            );

    @Test
    void containerStarts() {
        // Create a Spring client pointing to the container endpoint,
        // create the index, and run the geo queries under test.
    }
}
~~~

This is a skeleton illustrating the container lifecycle. In a Spring Boot project, configure the connection URI and credentials from the container before initializing the Elasticsearch client. Use an image version compatible with the Spring Data Elasticsearch and Java API Client versions managed by your project.

### Steps in an integration test

1. Start the Elasticsearch container.
2. Create an index with an explicit `geo_point` or `geo_shape` mapping.
3. Index fixtures for interior, exterior, boundary, and missing data.
4. Refresh the index.
5. Run geo queries via the service or `ElasticsearchOperations`.
6. Assert the returned ID set.
7. Verify results when varying radius and distance type.
8. Verify documents with null location or missing fields.
9. Verify swapped-order coordinates.
10. Delete the index or let the container terminate with the test lifecycle.

Tests should run against an Elasticsearch version close to production. An embedded mock or fake repository cannot replace real geo engine behavior.

## 17. Recommended test matrix

A test matrix helps prevent missed cases:

| Group | Case | What to verify |
|---|---|---|
| Coordinate | Latitude = -90 or 90 | Accepted within valid range |
| Coordinate | Longitude = -180 or 180 | Accepted within valid range |
| Coordinate | Out-of-range latitude/longitude | Validation or mapping rejects/ignores as configured |
| Coordinate | NaN/Infinity | Rejected by application |
| Coordinate | Swapped lat/lon | Tests catch wrong position |
| Missing | Omitted field | Does not match exists |
| Missing | Null | Does not match exists by default |
| Missing | (0, 0) | Still treated as a valid point |
| Distance | At center | Matches |
| Distance | Inside radius | Matches |
| Distance | On radius boundary | Boundary check |
| Distance | Outside radius | Does not match |
| Bounding box | All four edges and corners | Verify boundary semantics |
| Global | Across date line | Adjacent points not dropped |
| Global | Near poles | No flawed planar calculation |
| Shape | Inside, outside, on edge, at vertex | Verify relation |
| Precision | High-decimal vs. rounded coordinates | Measure error impact |
| Mapping | `ignore_malformed` | Ignore or reject behavior matches configuration |
| Multi-index | One index lacks geo mapping | Verify `ignore_unmapped` or expected failure |

## 18. Testing distance sorting

Nearest-store applications typically do not only filter by radius; they also sort by distance from the user's location.

Verify:

- The closest store appears first when sorting ascending.
- Two stores at nearly equal distances.
- Documents missing location are handled according to missing policy.
- Returned distances use the right unit.
- Order does not shift unpredictably across queries on identical data.
- When multiple documents share the same distance, a stable tie-breaker is used if paginating.

Do not merely assert that the list has the expected element count. Verify IDs in order and distances of the top results.

If the application uses `search_after` on geographically sorted results, preserve the returned sort values and sort definition across pages. Never recompute sort values from entity coordinates.

## 19. Handling multiple indices and ignore_unmapped

An alias may point to multiple indices. During migrations, an older index might lack the `location` field or have a non-`geo_point` mapping.

A geo query running across heterogeneous indices can fail if a field is unmapped in one index. Some queries support `ignore_unmapped` to skip indices lacking that field.

DSL example:

~~~json
{
  "query": {
    "geo_distance": {
      "distance": "5km",
      "ignore_unmapped": true,
      "location": {
        "lat": 10.762622,
        "lon": 106.660172
      }
    }
  }
}
~~~

Use `ignore_unmapped` only when skipping unmapped indices is acceptable business behavior. If that index is supposed to contain location, ignoring it can mask migration errors.

Test both policies:

- Strict: missing mapping fails the request to catch misconfiguration.
- Lenient: unmapped index is skipped intentionally.

## 20. Common mistakes

### Swapping latitude and longitude

Arrays and GeoJSON use longitude before latitude; objects use named `lat` and `lon`. Both numbers can remain valid after swapping, so test with known locations.

### Treating (0, 0) as missing data

(0, 0) is a valid coordinate. Use null or an explicit status field to represent missing locations.

### Testing only very far or very close points

Tests that avoid boundaries miss rounding, unit, or boundary semantics bugs. Include points just inside, right on, and just outside the threshold.

### Rounding before querying

Rounding latitude/longitude can push a point across a radius or service-zone boundary. Keep input precision during queries and only round for display.

### Using plane across wide regions

Planar math can introduce substantial error over long distances, high latitudes, or wide regions. Use arc unless you have measured and accepted plane's error.

### Using exists to validate location quality

Exists only confirms an indexed value is present. It does not verify that a point lies in the business area or matches an address.

### Enabling ignore_malformed without monitoring

Documents can be saved while location goes unindexed. Use logs, metrics, or data-status fields to detect skipped coordinates.

### Only mocking Elasticsearch in unit tests

Mocks cannot verify geo query behavior or mappings. Write integration tests against a compatible Elasticsearch version.

### Testing with rounded distances

If you compute distance and round it before comparing, tests can give false results at thresholds. Compare with an appropriate tolerance and inspect actual responses.

## 21. Implementation and testing workflow

When developing geospatial features:

1. Choose `geo_point` or `geo_shape` based on the business model.
2. Declare explicit mappings in Spring Data or provisioning pipelines.
3. Normalize coordinate order and input formats.
4. Validate latitude/longitude bounds, finite values, and missing data.
5. Define clear rules for nulls, empty arrays, and invalid coordinates.
6. Select the appropriate distance type and distance unit.
7. Define semantics for points directly on radius, bounding box, and polygon boundaries.
8. Create fixtures with interior, exterior, exact-boundary, and two-sided epsilon points.
9. Add tests for (0, 0), poles, and the date line if data scope requires global coverage.
10. Run integration tests against real Elasticsearch.
11. Apply appropriate tolerances for floating-point math and data sources.
12. Test multi-index aliases and heterogeneous mappings.
13. Monitor documents with skipped or malformed locations.
14. Never use fake coordinates to disguise missing data.

## References

- [Elasticsearch — Geo-point field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/geo-point.html)
- [Elasticsearch — Geo-shape field type](https://www.elastic.co/guide/en/elasticsearch/reference/current/geo-shape.html)
- [Elasticsearch — Geo-distance query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-geo-distance-query.html)
- [Elasticsearch — Geo-bounding box query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-geo-bounding-box-query.html)
- [Elasticsearch — Geo-shape query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-geo-shape-query.html)
- [Spring Data Elasticsearch — Reference documentation](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch.html)
- [Testcontainers — Elasticsearch module](https://java.testcontainers.org/modules/elasticsearch/)

## Conclusion

Geospatial testing must cover valid coordinates, missing data, malformed inputs, interior/exterior/boundary points, and distance tolerances. With Spring Data Elasticsearch, declare geospatial mappings explicitly, build queries with `NativeQuery` when geospatial DSL is needed, and verify behavior via integration tests on real Elasticsearch. Distinguish latitude/longitude properly, never treat (0, 0) as missing, preserve coordinate precision during queries, and apply business-driven tolerances instead of exact floating-point comparisons.