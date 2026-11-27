# Distinguishing geo_point and geo_shape

Elasticsearch supports geospatial data to find places near coordinates, filter documents within a radius, check whether a location falls inside a service area, and find intersecting geographic regions. The two primary data types for this purpose are `geo_point` and `geo_shape`.

`geo_point` represents a point location using latitude and longitude. It is suitable for stores, users, delivery stations, devices, or any entity described by a single coordinate pair.

`geo_shape` represents more complex geographic geometries such as points, lines, polygons, and geometry collections. It is suitable for district boundaries, delivery zones, restricted areas, routes, or coverage areas.

Both data types can appear in the same document. For example, a store has `location` as a `geo_point` to find stores near a user and `service_area` as a `geo_shape` to describe the area where the store delivers.

## 1. Core differences

| Criterion | `geo_point` | `geo_shape` |
|---|---|---|
| Primary data | A point coordinate; a field can also contain multiple points | Geometries such as point, line, polygon, multipolygon, and geometry collection |
| Common purpose | Proximity search, radius filtering, sorting by distance | Checking intersection, containment, enclosure, or disjointness between shapes |
| Typical queries | `geo_distance`, `geo_bounding_box` | `geo_shape` with relation |
| Sorting by distance | Supports `_geo_distance` | Not used like a simple point; requires a representative point or a different model |
| Representation | lat/lon object, string, coordinate array, or geohash in supported formats | GeoJSON, WKT, or geometry formats supported by Elasticsearch |
| Business example | Coordinates of a restaurant | Boundary polygon of a delivery area |

You can remember:

- Use `geo_point` when the primary question is “where is this place?” or “which points are near this location?”.
- Use `geo_shape` when the primary question is “which area does this geometry intersect, contain, or fall within?”.

`geo_shape` can also store a Point geometry, but if the data is only coordinates for proximity search and distance sorting, `geo_point` is usually simpler and more appropriate.

## 2. Geographic coordinates: latitude and longitude

Before declaring a mapping, you need to standardize the coordinate order. A geographic coordinate has two components:

- **Latitude:** North/South position, typically ranging from -90 to 90.
- **Longitude:** East/West position, typically ranging from -180 to 180.

The representation order depends on the format:

| Format | Order |
|---|---|
| GeoJSON coordinates | [longitude, latitude] |
| Elasticsearch `geo_point` array | [longitude, latitude] |
| `geo_point` object | `{"lat": latitude, "lon": longitude}` |
| `geo_point` string | `"latitude,longitude"` |
| WKT Point | `POINT (longitude latitude)` |

Example of the same location:

~~~json
{
  "lat": 10.78,
  "lon": 106.69
}
~~~

Array representation:

~~~json
[106.69, 10.78]
~~~

GeoJSON/WKT representation:

~~~json
{
  "type": "Point",
  "coordinates": [106.69, 10.78]
}
~~~

~~~text
POINT (106.69 10.78)
~~~

Swapping latitude and longitude is a common mistake. A value may still lie within the valid numeric range while pointing to a completely different geographic location. Standardize the order at the system boundary and write tests for the conversion process.

## 3. Declaring a geo_point field

The `geo_point` mapping indicates that a field holds point coordinates:

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
      "location": {
        "type": "geo_point"
      }
    }
  }
}
~~~

Sample document:

~~~http
PUT /places/_doc/place-001
Content-Type: application/json

{
  "name": "Central Coffee",
  "category": "cafe",
  "location": {
    "lat": 10.78,
    "lon": 106.69
  }
}
~~~

Elasticsearch also accepts several other `geo_point` representations such as `"lat,lon"` strings, `[lon, lat]` arrays, and geohashes. Using an object with `lat` and `lon` is usually easier to read and less error-prone when exchanging data between services.

### 3.1. Multiple points in a single document

A `geo_point` field can contain multiple coordinates. For example, a driver can send multiple positions or an entity can have several measurement points:

~~~json
{
  "driverId": "driver-42",
  "positions": [
    {"lat": 10.78, "lon": 106.69},
    {"lat": 10.79, "lon": 106.70}
  ]
}
~~~

When querying a multi-valued field, you need to understand the query and sort semantics: a document can match if any of the points satisfies the condition; for distance sorting, you should choose an appropriate mode or rely on the default behavior defined in the API. If the application needs a single current location, store an explicit representative field instead of relying on a history array as the sort source.

## 4. Querying geo_point

### 4.1. geo_distance: searching within a radius

`geo_distance` filters documents whose points lie within a maximum distance from an origin:

~~~http
GET /places/_search
Content-Type: application/json

{
  "query": {
    "geo_distance": {
      "distance": "5km",
      "location": {
        "lat": 10.78,
        "lon": 106.69
      }
    }
  }
}
~~~

This example finds places within a 5 km radius of the given coordinates. Distance can use units supported by Elasticsearch such as m, km, mi, or yd.

You can combine it with a bool filter to also filter by place category:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "cafe"
          }
        },
        {
          "geo_distance": {
            "distance": "5km",
            "location": {
              "lat": 10.78,
              "lon": 106.69
            }
          }
        }
      ]
    }
  }
}
~~~

Both the category condition and the distance condition are mandatory filters. There is no need to compute a relevance score if the goal is simply to find all cafes within the radius.

### 4.2. geo_bounding_box: filtering by a coordinate box

`geo_bounding_box` filters points that fall inside a rectangle defined by two corners:

~~~json
{
  "query": {
    "geo_bounding_box": {
      "location": {
        "top_left": {
          "lat": 10.82,
          "lon": 106.64
        },
        "bottom_right": {
          "lat": 10.72,
          "lon": 106.75
        }
      }
    }
  }
}
~~~

A bounding box is well suited for map interactions such as finding points within the current viewport. It filters by a coordinate rectangle, not a circular radius.

### 4.3. Sorting by distance

If you want the nearest places first, use `_geo_distance`:

~~~json
{
  "sort": [
    {
      "_geo_distance": {
        "location": {
          "lat": 10.78,
          "lon": 106.69
        },
        "order": "asc",
        "unit": "km",
        "distance_type": "arc"
      }
    }
  ]
}
~~~

This sort orders results by the distance from the origin to the indexed coordinates. `arc` calculates the distance along the arc on the Earth's surface; choose a calculation method and precision appropriate for your problem.

You can combine relevance with distance using `function_score` or a distance feature if relevant content should still carry weight. Sorting purely by `_geo_distance` prioritizes distance as the primary order, which can place nearby but less relevant results ahead of better-matching ones.

## 5. Declaring a geo_shape field

`geo_shape` is used to store geometries rather than just a single coordinate pair. Common shapes include:

- Point: a single point.
- LineString: a path consisting of multiple coordinates.
- Polygon: an area with a closed boundary.
- MultiPoint, MultiLineString, MultiPolygon: a collection of multiple shapes of the same type.
- GeometryCollection: a collection of geometries of different types.
- Envelope: a rectangle defined by two corners.

Mapping example:

~~~http
PUT /service-areas
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "name": {
        "type": "keyword"
      },
      "service_area": {
        "type": "geo_shape"
      }
    }
  }
}
~~~

Document containing a GeoJSON polygon:

~~~http
PUT /service-areas/_doc/area-001
Content-Type: application/json

{
  "name": "District Service Zone",
  "service_area": {
    "type": "polygon",
    "coordinates": [
      [
        [106.65, 10.75],
        [106.72, 10.75],
        [106.72, 10.81],
        [106.65, 10.81],
        [106.65, 10.75]
      ]
    ]
  }
}
~~~

In GeoJSON, every coordinate always follows longitude then latitude. The outer ring of a polygon must be closed: the last coordinate matches the first coordinate. A polygon with holes includes additional inner coordinate rings.

### 5.1. Polygon with holes

A polygon can contain an outer ring and one or more inner rings representing cut-out areas:

~~~json
{
  "type": "polygon",
  "coordinates": [
    [
      [106.60, 10.70],
      [106.80, 10.70],
      [106.80, 10.90],
      [106.60, 10.90],
      [106.60, 10.70]
    ],
    [
      [106.68, 10.78],
      [106.72, 10.78],
      [106.72, 10.82],
      [106.68, 10.82],
      [106.68, 10.78]
    ]
  ]
}
~~~

The first ring is the outer boundary; subsequent rings represent holes. When creating polygons, ensure coordinates are valid, rings are closed, and ring orientation follows the orientation rules configured in Elasticsearch. For GIS data generated by external tools, verify orientation and geometry before indexing.

### 5.2. LineString and MultiPolygon

A route can be stored using a LineString:

~~~json
{
  "type": "linestring",
  "coordinates": [
    [106.65, 10.75],
    [106.68, 10.77],
    [106.72, 10.80]
  ]
}
~~~

An area composed of multiple separate regions can use a MultiPolygon:

~~~json
{
  "type": "multipolygon",
  "coordinates": [
    [
      [
        [106.60, 10.70],
        [106.65, 10.70],
        [106.65, 10.75],
        [106.60, 10.75],
        [106.60, 10.70]
      ]
    ],
    [
      [
        [106.75, 10.80],
        [106.80, 10.80],
        [106.80, 10.85],
        [106.75, 10.85],
        [106.75, 10.80]
      ]
    ]
  ]
}
~~~

MultiPolygon is useful when a service area consists of multiple non-contiguous geographic regions.

## 6. Querying geo_shape and relations

A `geo_shape` query compares the geometry stored in a document with a query geometry. The `relation` parameter specifies the spatial relationship to satisfy.

Commonly used relations:

| Relation | General meaning |
|---|---|
| `intersects` | The two shapes share an intersecting area |
| `within` | The indexed shape lies inside the query shape |
| `contains` | The indexed shape contains the query shape |
| `disjoint` | The two shapes do not intersect |

Interpreting the direction always requires considering both the shape in the document and the shape in the query. For example, if the `service_area` field stores a delivery zone polygon and the query sends a customer's Point, `contains` asks whether the polygon in the document contains the query point.

### 6.1. Checking if a customer point lies inside a polygon

~~~http
GET /service-areas/_search
Content-Type: application/json

{
  "query": {
    "geo_shape": {
      "service_area": {
        "shape": {
          "type": "point",
          "coordinates": [106.69, 10.78]
        },
        "relation": "contains"
      }
    }
  }
}
~~~

Here:

- The document contains the service_area polygon.
- The query sends a customer point.
- `contains` selects the polygons in documents that contain that point.

If the goal is to find polygons that intersect a requested polygon, use the `intersects` relation:

~~~http
GET /service-areas/_search
Content-Type: application/json

{
  "query": {
    "geo_shape": {
      "service_area": {
        "shape": {
          "type": "polygon",
          "coordinates": [
            [
              [106.68, 10.76],
              [106.73, 10.76],
              [106.73, 10.82],
              [106.68, 10.82],
              [106.68, 10.76]
            ]
          ]
        },
        "relation": "intersects"
      }
    }
  }
}
~~~

The results include service zones that intersect the polygon sent in the query.

### 6.2. Distinguishing within and contains

These two relations are easy to reverse:

- If the polygon in the document lies completely inside the query polygon, use `within`.
- If the polygon in the document encloses the query shape, use `contains`.

With a query point and a polygon in the document:

- `contains` asks whether the document polygon contains the query point.
- `within` asks whether the document polygon lies inside the query shape; when the query is just a point, this condition does not represent the "point inside an area" problem.

Draw both shapes clearly and label them "indexed shape" and "query shape" before choosing a relation. Test with an interior point, an exterior point, and a point near the boundary to confirm the expected semantics.

### 6.3. disjoint

`disjoint` selects shapes that have no intersection with the query shape. For example, finding service areas completely disjoint from a restricted zone. When using this relation, verify whether returning very distant areas matches business requirements; sometimes you should also combine it with a province/city condition or a bounding box to limit scope.

## 7. Comparing geo_point and geo_shape queries

| Business question | Appropriate field | Query or operation |
|---|---|---|
| Which stores are within a 5 km radius? | `geo_point` | `geo_distance` |
| Which points lie inside the map viewport? | `geo_point` | `geo_bounding_box` |
| Which store is nearest? | `geo_point` | `_geo_distance` sort |
| Is the customer inside the delivery zone? | `geo_shape` polygon + point query | `geo_shape` relation `contains` |
| Do two delivery zones overlap? | `geo_shape` | relation `intersects` |
| Does a route intersect a restricted area? | `geo_shape` | relation `intersects` |
| Which areas lie completely within a planning zone? | `geo_shape` | relation `within` |
| Is a region disjoint from the query area? | `geo_shape` | relation `disjoint` |

If a use case requires both nearest distance and area boundary checks, you can store both `geo_point` and `geo_shape` in the same document. Two fields serve two different questions, so there is no need to force one data type to cover every requirement.

## 8. Geospatial data in Spring Data Elasticsearch

Spring Data Elasticsearch supports mapping geospatial fields through annotations and geospatial data types. Exact usage depends on the project's Spring Data release train and Elasticsearch Java Client.

### 8.1. Entity using geo_point

Place entity example:

~~~java
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

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @GeoPointField
    private GeoPoint location;

    // constructors, getters and setters
}
~~~

Spring Data Elasticsearch's `GeoPoint` represents a point with latitude and longitude. Example creating a point:

~~~java
GeoPoint location = new GeoPoint(10.78, 106.69);
~~~

In this constructor, pass latitude first and then longitude. When serialized into GeoJSON coordinates or an Elasticsearch coordinate array, the order on the wire is longitude then latitude. These are two different conventions that converters must handle properly.

You can use `@Field(type = FieldType.GeoPoint)` if the project's version and mapping metadata support that declaration; `@GeoPointField` is the dedicated annotation commonly used for GeoPoint properties.

### 8.2. Entity using geo_shape

For complex geometries, the field must be mapped as `geo_shape`. Example of a model holding GeoJSON as a map:

~~~java
import java.util.Map;

import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

public class ServiceArea {

    @Field(type = FieldType.GeoShape)
    private Map<String, Object> serviceArea;
}
~~~

The map value must serialize into a geometry structure that Elasticsearch understands, for example:

~~~java
Map<String, Object> polygon = Map.of(
        "type", "polygon",
        "coordinates", List.of(
                List.of(
                        List.of(106.65, 10.75),
                        List.of(106.72, 10.75),
                        List.of(106.72, 10.81),
                        List.of(106.65, 10.81),
                        List.of(106.65, 10.75)
                )
        )
);
~~~

This is a structural way to represent GeoJSON data. In real projects, you can use dedicated GeoJSON types supported by the release train or a custom value object with a converter. Check the mapping and the actual JSON sent; declaring `FieldType.GeoShape` only determines the mapping type and does not automatically guarantee every arbitrary Java geometry serializes properly.

### 8.3. Creating mapping through Spring Data

If the index is created from entity metadata, you can obtain `IndexOperations`:

~~~java
IndexOperations indexOperations =
        operations.indexOps(Place.class);

if (!indexOperations.exists()) {
    indexOperations.createWithMapping();
}
~~~

For production indices, geospatial mappings should be managed via index templates or controlled migrations. After creating the index, inspect the actual mapping to confirm the field is `geo_point` or `geo_shape` as expected:

~~~http
GET /places/_mapping
~~~

Changing a field from `geo_point` to `geo_shape` or vice versa is not a simple type change that can be applied directly to an existing mapping. Usually you need to create a new index with the right mapping, convert/reindex the data, and switch the alias.

## 9. Querying geo_distance via Spring Data

When querying by distance, you can use `@Query` with a fixed DSL or `NativeQuery` if the origin and radius vary per request.

Example repository with a structurally fixed query:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface PlaceRepository
        extends ElasticsearchRepository<Place, String> {

    @Query("""
        {
          "geo_distance": {
            "distance": "?0",
            "location": {
              "lat": ?1,
              "lon": ?2
            }
          }
        }
        """)
    List<Place> findWithinDistance(
            String distance,
            double latitude,
            double longitude
    );
}
~~~

This example illustrates positional binding for distance and coordinates; verify how numeric and string binding behave in your version of Spring Data Elasticsearch. For complex dynamic queries or combining multiple conditions, `NativeQuery` and the Elasticsearch Java Client are usually easier to control.

Do not concatenate JSON strings from user coordinate data. Validate latitude/longitude, enforce business limits on distance, and pass values via API binding.

## 10. Querying geo_shape in an application

A query checking whether a customer location belongs to a delivery zone can be expressed using JSON DSL:

~~~java
String queryJson = """
    {
      "geo_shape": {
        "service_area": {
          "shape": {
            "type": "point",
            "coordinates": [106.69, 10.78]
          },
          "relation": "contains"
        }
      }
    }
    """;
~~~

In a Spring Data application, you can place a fixed DSL in `@Query`, or build a GeoShape query using the Elasticsearch Java Client and pass it into `NativeQuery`. If the location varies by request, construct the query object from validated values rather than concatenating JSON strings.

When using geometries generated by GIS libraries, convert the geometry into a format supported by the Elasticsearch client. Check the CRS (coordinate reference system) of the data source: Elasticsearch geo fields work with WGS84 geographic coordinates in longitude/latitude. If the source data uses a planar coordinate system or another CRS, transform it before indexing.

## 11. GeoJSON, WKT, and data normalization

### 11.1. GeoJSON

GeoJSON is a common format for exchanging geometries. Point example:

~~~json
{
  "type": "Point",
  "coordinates": [106.69, 10.78]
}
~~~

LineString example:

~~~json
{
  "type": "LineString",
  "coordinates": [
    [106.65, 10.75],
    [106.68, 10.77],
    [106.72, 10.80]
  ]
}
~~~

Polygon example:

~~~json
{
  "type": "Polygon",
  "coordinates": [
    [
      [106.65, 10.75],
      [106.72, 10.75],
      [106.72, 10.81],
      [106.65, 10.81],
      [106.65, 10.75]
    ]
  ]
}
~~~

GeoJSON uses a geometry type name and a coordinates array. Coordinates in the array are longitude, latitude; do not reverse the order like named `geo_point` objects.

### 11.2. WKT

Well-Known Text (WKT) represents geometries as strings:

~~~text
POINT (106.69 10.78)
LINESTRING (106.65 10.75, 10.68 10.77, 10.72 10.80)
POLYGON ((106.65 10.75, 106.72 10.75, 106.72 10.81, 106.65 10.81, 106.65 10.75))
~~~

WKT uses X/Y order, which in the context of geographic coordinates is longitude/latitude. Check the parser and formats supported by the Elasticsearch API or conversion library.

### 11.3. CRS and source data

Not all data with two numbers represents longitude/latitude. A GIS file may use a planar coordinate system in meters or a local CRS. Before ingesting into Elasticsearch:

1. Identify the source CRS.
2. Transform to WGS84 if needed.
3. Normalize to longitude/latitude order.
4. Validate value ranges.
5. Verify closed polygons and valid geometries.
6. Test indexing a few representative geometries.
7. Run spatial queries to verify positions and relations.

Do not rely solely on Elasticsearch accepting the document; coordinates in the wrong CRS can still be indexed while yielding incorrect geographic results.

## 12. Performance and choosing the right data type

`geo_point` is generally a compact and efficient choice for searching around a point, bounding boxes, distance sorting, and distance aggregations.

`geo_shape` is suitable for complex geometries and spatial relationships between regions. Storing polygons with many vertices or large geometry collections requires more complex geometric processing and indexing than a simple point.

A few guidelines:

- Do not use a polygon just to store a coordinate pair if geometric relations are not needed.
- Do not use `geo_point` to describe area boundaries.
- Reduce unnecessary polygon vertices while preserving business accuracy.
- Avoid sending very large geometries in every request if you can store and reference indexed geometries.
- Use filters when you only need spatial condition checks and do not need scoring.
- Limit search radii or search areas according to business requirements to avoid overly broad queries.
- Test mappings and queries on data at production-like scale.

Do not assume a `geo_shape` query is always slow or a `geo_point` query is always fast across every workload. Performance depends on the number of geometries, geometric complexity, vertex count, shard count, and query structure.

## 13. Common mistakes

### 13.1. Swapping latitude and longitude

A `geo_point` object uses named lat/lon fields, whereas GeoJSON coordinates and arrays use longitude before latitude. WKT also uses X then Y. Verify each format individually.

### 13.2. Using geo_point for areas

A single representative point cannot describe polygon boundaries or routes. If the business logic needs to check whether a customer falls inside a delivery zone, store a `geo_shape`.

### 13.3. Using geo_shape for simple nearest-neighbor queries

If you only need stores near a user sorted by distance, `geo_point` with `geo_distance`/`_geo_distance` is simpler.

### 13.4. Choosing the wrong relation

`contains` and `within` are interpreted according to the relationship between the indexed shape and the query shape. Identify which shape is the polygon stored in the document and which is the query geometry before choosing.

### 13.5. Unclosed polygons or wrong orientation

Polygon rings must be closed and follow orientation rules. Non-standard GIS data may be rejected or interpreted unexpectedly.

### 13.6. Ignoring CRS

Coordinates from a reference system other than WGS84 cannot be treated directly as longitude/latitude. Transform them before indexing.

### 13.7. Inconsistent mappings across indices

A multi-index alias requires compatible geospatial field types. Avoid having an old index use a plain object while a new index uses `geo_shape`.

### 13.8. Changing field types directly

You cannot arbitrarily change `geo_point` to `geo_shape` on an index that already holds data. Create a new index, reindex/convert geometries, and switch the alias following a migration procedure.

## 14. Testing geospatial data

For `geo_point`, write tests for:

- A point inside the radius.
- A point outside the radius.
- A point right near the distance threshold.
- Points inside and outside a bounding box.
- Sorting from nearest to farthest.
- Missing or out-of-range coordinates.
- Multiple points in the same document, if applicable.

For `geo_shape`, write tests for:

- A point inside a polygon.
- A point outside a polygon.
- A point on or near a boundary.
- A polygon partially intersecting the query polygon.
- A polygon completely within the query polygon.
- A polygon containing the query polygon.
- Two disjoint shapes.
- Polygons with holes and MultiPolygons.
- Invalid geometries or reversed coordinate order.

Tests should use data with predetermined coordinates and expected results. For distance queries, do not just check that results exist; verify that distances or ordering match expectations.

In integration tests, use an Elasticsearch version compatible with the project's Spring Data Elasticsearch. Verify the generated mapping, serialized document JSON, and query results against a real cluster.

## 15. Workflow for choosing geo_point or geo_shape

When designing a geospatial field:

1. Determine whether the data represents a location or a geometry.
2. If it is only a location, choose `geo_point`.
3. If it is a line, area, or complex geometry, choose `geo_shape`.
4. Normalize CRS and longitude/latitude order.
5. Design the mapping and corresponding Java types.
6. Inspect the JSON serialized by Spring Data.
7. Choose the query based on the business question: distance, bounding box, or shape relation.
8. Combine bool filters with other business conditions.
9. Test interior/exterior points and intersecting/disjoint shapes.
10. If changing an existing index mapping, create a new index and perform a controlled data migration.

Decision examples:

| Data | Type to consider | Reason |
|---|---|---|
| Store coordinates | `geo_point` | Proximity search and distance sorting |
| Latest GPS position of a vehicle | `geo_point` | A single representative position |
| Ward/district boundaries | `geo_shape` | Polygon |
| Delivery route | `geo_shape` | LineString |
| Multiple separate service areas | `geo_shape` | MultiPolygon |
| Customer point and delivery zone | Both | Point to identify position, polygon to check containment |

## 16. Conclusion

`geo_point` represents point coordinates and suits proximity search, radius filtering, bounding boxes, and distance sorting. `geo_shape` represents geometries such as lines and areas, making it suitable for spatial relation queries such as intersects, within, contains, and disjoint.

Coordinate order must be handled accurately: `geo_point` objects use `lat`/`lon`, whereas GeoJSON coordinates, Elasticsearch arrays, and WKT use longitude before latitude. For polygons, ensure closed rings, proper orientation, and the right CRS.

In Spring Data Elasticsearch, `@GeoPointField` and `GeoPoint` are the common way to map points. For shapes, use a `geo_shape` mapping and a geometry representation supported by your project's version, then verify the actual JSON. Choose the data type based on the spatial question the application needs to answer; when both position and boundaries are needed, you can store both `geo_point` and `geo_shape` in the same document.