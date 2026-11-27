# Geo-shape Queries and Geometric Relations

## 1. What problem does a geo-shape query solve?

In applications with geospatial data, searches sometimes cannot rely on a single coordinate pair. A document may represent a delivery zone, district boundary, route, coverage area, or land parcel. When a user selects a region on a map, the application needs to find documents whose geometries relate to that region.

For example:

- Find delivery zones that intersect the region a user drew on the map.
- Find districts lying completely inside a selected region.
- Find land parcels that enclose an entire planning zone.
- Exclude regions having no overlap with a restricted area.
- Find routes or geographic areas having a geometric relationship with a polygon.

Elasticsearch provides the **geo_shape query** to perform these comparisons. The query takes a query geometry and a spatial relation, then compares it against the geometry indexed in each document.

Geo-shape queries support these relations:

- `INTERSECTS`: the two shapes share at least one point.
- `WITHIN`: the geometry in the document lies completely inside the query geometry.
- `CONTAINS`: the geometry in the document completely encloses the query geometry.
- `DISJOINT`: the two shapes share no points.

A geo-shape query can search documents indexed with a `geo_shape` or `geo_point` field. If the data consists solely of point coordinates, `geo_point` is usually the more suitable mapping. When storing lines, polygons, or complex shapes is required, use `geo_shape`.

## 2. Distinguishing geo_point, geo_shape, and shape

Elasticsearch has geospatial and geometric data types for different purposes:

| Field type | Data | Coordinate system | Use cases |
|---|---|---|---|
| `geo_point` | A single geographic point | WGS-84 longitude/latitude | Store, device, or user locations |
| `geo_shape` | Points, lines, polygons, multipolygons, and geographic shapes | WGS-84 longitude/latitude | Region boundaries, coverage zones, routes |
| `shape` | Two-dimensional X/Y geometries | Planar Cartesian coordinate system | Indoor maps, floor plans, non-geographic spatial coordinates |

`geo_shape` operates in geographic coordinate space. `shape` processes planar X/Y coordinates and carries no longitude/latitude meaning. Do not use `shape` for geographic boundaries just because both accept GeoJSON or WKT.

If an application only stores a store's location, consider `geo_point`. If it stores the boundary of the store's service area, use `geo_shape`. A geo-shape query can query both field types, but geometric semantics still depend on the indexed data type.

## 3. Declaring a geo_shape mapping

Elasticsearch requires explicitly declaring a field of type `geo_shape` in the mapping.

Example creating the `delivery-zones` index:

~~~http
PUT /delivery-zones
{
  "mappings": {
    "properties": {
      "name": {
        "type": "keyword"
      },
      "boundary": {
        "type": "geo_shape"
      }
    }
  }
}
~~~

The `boundary` field stores the geometry of the delivery zone. The `name` field stores the zone name.

You can declare additional options for geo_shape:

~~~json
{
  "boundary": {
    "type": "geo_shape",
    "orientation": "right",
    "ignore_malformed": false,
    "ignore_z_value": true,
    "coerce": false
  }
}
~~~

Several important options:

| Option | Purpose | Default |
|---|---|---|
| `orientation` | Specifies polygon ring orientation, mainly relevant for WKT and polygons crossing the 180° meridian | `RIGHT` |
| `ignore_malformed` | Ignores malformed geometries instead of rejecting the document | `false` |
| `ignore_z_value` | Accepts 3D coordinates while indexing only longitude/latitude | `true` |
| `coerce` | Automatically closes unclosed polygon rings | `false` |
| `index` | Enables or disables structures used for fast search | `true` |
| `doc_values` | Stores columnar data for certain operations | `true` |

Do not enable `ignore_malformed` or `coerce` to hide bad geospatial data. If a polygon has invalid coordinates, wrong vertex order, or invalid self-intersections, fix it at the data source so boundaries are indexed accurately.

## 4. GeoJSON and WKT

Elasticsearch supports two popular geometry representations:

- **GeoJSON:** JSON structure with `type` and `coordinates`.
- **WKT (Well-Known Text):** text-string geometry representation.

Example of a point:

~~~json
{
  "type": "Point",
  "coordinates": [106.7009, 10.7769]
}
~~~

Corresponding WKT form:

~~~text
POINT (106.7009 10.7769)
~~~

Example of a line:

~~~json
{
  "type": "LineString",
  "coordinates": [
    [106.7009, 10.7769],
    [106.7050, 10.7800],
    [106.7100, 10.7850]
  ]
}
~~~

Corresponding WKT:

~~~text
LINESTRING (106.7009 10.7769, 106.7050 10.7800, 106.7100 10.7850)
~~~

Commonly supported geometry types:

| GeoJSON type | WKT type | Meaning |
|---|---|---|
| `Point` | `POINT` | A single point |
| `LineString` | `LINESTRING` | A line with at least two points |
| `Polygon` | `POLYGON` | An area with a closed boundary |
| `MultiPoint` | `MULTIPOINT` | Multiple disjoint points |
| `MultiLineString` | `MULTILINESTRING` | Multiple lines |
| `MultiPolygon` | `MULTIPOLYGON` | Multiple polygons |
| `GeometryCollection` | `GEOMETRYCOLLECTION` | Collection of multiple geometry types |
| `Envelope` | `BBOX` | Bounding rectangle |

In GeoJSON, `type` and `coordinates` are the two core properties defining a geometry. `GeometryCollection` uses `geometries` to hold its member geometries.

### Coordinate order

This is the most common mistake when working with GeoJSON:

**Elasticsearch uses longitude, latitude (X, Y) order, not latitude, longitude.**

Example:

~~~json
{
  "type": "Point",
  "coordinates": [106.7009, 10.7769]
}
~~~

- `106.7009` is longitude.
- `10.7769` is latitude.

Many map APIs or user interfaces display coordinates in latitude, longitude order. When transferring data from such APIs into GeoJSON, swap the order appropriately. Otherwise, the point can end up in a completely different location.

Elasticsearch uses the WGS-84 coordinate system for geo_shape. Do not put pixel coordinates, drawing coordinates, or arbitrary Cartesian coordinates into this field.

## 5. Polygons, outer rings, and inner holes

A Polygon represents a closed area. In GeoJSON, polygon coordinates are an array of rings:

- The first ring is the outer boundary.
- Subsequent rings are holes inside the polygon.

Simple polygon example:

~~~json
{
  "type": "Polygon",
  "coordinates": [
    [
      [106.68, 10.75],
      [106.72, 10.75],
      [106.72, 10.79],
      [106.68, 10.79],
      [106.68, 10.75]
    ]
  ]
}
~~~

The first and last points of the outer ring must match. A polygon has at least three sides, so the outer ring needs at least four coordinates, counting the closing point.

Polygon with an inner hole:

~~~json
{
  "type": "Polygon",
  "coordinates": [
    [
      [106.68, 10.75],
      [106.74, 10.75],
      [106.74, 10.81],
      [106.68, 10.81],
      [106.68, 10.75]
    ],
    [
      [106.70, 10.77],
      [106.72, 10.77],
      [106.72, 10.79],
      [106.70, 10.79],
      [106.70, 10.77]
    ]
  ]
}
~~~

The second ring is an empty cutout. Points inside the hole are not considered part of the polygon's area.

If a region consists of multiple disjoint areas, use `MultiPolygon`. If a single geometry must hold multiple object types, you can use `GeometryCollection`.

## 6. Storing geometries in documents

Once the mapping is created, you can index a document containing a polygon:

~~~http
PUT /delivery-zones/_doc/zone-01
{
  "name": "Central Zone",
  "boundary": {
    "type": "Polygon",
    "coordinates": [
      [
        [106.68, 10.75],
        [106.72, 10.75],
        [106.72, 10.79],
        [106.68, 10.79],
        [106.68, 10.75]
      ]
    ]
  }
}
~~~

Another document can store a line:

~~~http
PUT /delivery-zones/_doc/zone-02
{
  "name": "North Route",
  "boundary": {
    "type": "LineString",
    "coordinates": [
      [106.70, 10.78],
      [106.73, 10.80],
      [106.76, 10.82]
    ]
  }
}
~~~

Elasticsearch decomposes geometries into spatial structures for search. For polygons and multipolygons, processing cost depends heavily on vertex count. A boundary with hundreds of thousands of points consumes far more processing and resources than a simple polygon.

If the data source contains too many vertices, consider simplifying the geometry before indexing. Simplification must preserve the accuracy required for business boundaries.

## 7. Structure of a geo_shape query

A basic geo_shape query looks like:

~~~json
{
  "query": {
    "geo_shape": {
      "boundary": {
        "shape": {
          "type": "Polygon",
          "coordinates": [
            [
              [106.69, 10.76],
              [106.71, 10.76],
              [106.71, 10.78],
              [106.69, 10.78],
              [106.69, 10.76]
            ]
          ]
        },
        "relation": "intersects"
      }
    }
  }
}
~~~

Components:

- `geo_shape`: the spatial query type.
- `boundary`: geometry field stored in the document.
- `shape`: query geometry supplied inline.
- `relation`: spatial relationship to evaluate.

If `relation` is omitted, Elasticsearch uses `INTERSECTS` by default.

You can place a geo_shape query inside `bool.filter` when you only want to filter documents by geometry:

~~~json
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
          "geo_shape": {
            "boundary": {
              "shape": {
                "type": "Polygon",
                "coordinates": [
                  [
                    [106.69, 10.76],
                    [106.71, 10.76],
                    [106.71, 10.78],
                    [106.69, 10.78],
                    [106.69, 10.76]
                  ]
                ]
              },
              "relation": "intersects"
            }
          }
        }
      ]
    }
  }
}
~~~

Here, the document must both have `active = true` and satisfy the geometric relation. Using filter context is appropriate when the geospatial condition only decides whether a document is returned without computing relevance scores.

## 8. The four geometric relations

The most important part of geo_shape queries is understanding the comparison direction properly. Elasticsearch compares:

- **Indexed geometry:** the geometry stored in the document's field.
- **Query geometry:** the geometry sent in the search request.

Relations are defined for the document's geometry relative to the query geometry.

Suppose the query shape is a large area polygon:

| Relation | Condition on document geometry | Example |
|---|---|---|
| `INTERSECTS` | Shares at least one point with the query shape | Delivery zone touches or crosses the selected area |
| `WITHIN` | Lies completely inside the query shape | District fits entirely inside the search region |
| `CONTAINS` | Completely encloses the query shape | Service area covers the entire region drawn by the user |
| `DISJOINT` | Shares no points with the query shape | Region lies completely outside the selected area |

### INTERSECTS

`INTERSECTS` is the default relation. Two shapes intersect when they share at least one point, including points on the boundary.

Example finding delivery zones that have any overlap with the user-selected area:

~~~json
{
  "geo_shape": {
    "boundary": {
      "shape": {
        "type": "Polygon",
        "coordinates": [
          [
            [106.69, 10.76],
            [106.71, 10.76],
            [106.71, 10.78],
            [106.69, 10.78],
            [106.69, 10.76]
          ]
        ]
      },
      "relation": "intersects"
    }
  }
}
~~~

A delivery zone only needs to touch the boundary or lie partially inside the query polygon to be returned.

Use `INTERSECTS` when the business requirement is to find every entity overlapping or touching the selected region.

### WITHIN

`WITHIN` requires the shape in the document to lie completely inside the query shape. Under current semantics, boundary overlap also counts as being inside.

Example finding delivery zones that lie completely inside the user-selected region:

~~~json
{
  "geo_shape": {
    "boundary": {
      "shape": {
        "type": "Polygon",
        "coordinates": [
          [
            [106.69, 10.76],
            [106.75, 10.76],
            [106.75, 10.82],
            [106.69, 10.82],
            [106.69, 10.76]
          ]
        ]
      },
      "relation": "within"
    }
  }
}
~~~

If the document's region extends outside the query polygon even slightly, it does not satisfy `WITHIN`.

The `WITHIN` relation does not support line geometries according to Elasticsearch documentation. When working with lines, verify the geometry type and pick another suitable relation.

### CONTAINS

`CONTAINS` reverses `WITHIN`: the shape in the document must completely enclose the query shape.

Example finding service zones that cover the entire region drawn by the user:

~~~json
{
  "geo_shape": {
    "boundary": {
      "shape": {
        "type": "Polygon",
        "coordinates": [
          [
            [106.70, 10.77],
            [106.71, 10.77],
            [106.71, 10.78],
            [106.70, 10.78],
            [106.70, 10.77]
          ]
        ]
      },
      "relation": "contains"
    }
  }
}
~~~

Here, the polygon stored in the document must enclose the entire query polygon. If they only overlap partially, the document is not returned for `CONTAINS`.

### DISJOINT

`DISJOINT` requires the two shapes to have no points in common. It is the negation of `INTERSECTS`.

Example finding regions that do not intersect a restricted zone at all:

~~~json
{
  "geo_shape": {
    "boundary": {
      "shape": {
        "type": "Polygon",
        "coordinates": [
          [
            [106.69, 10.76],
            [106.71, 10.76],
            [106.71, 10.78],
            [106.69, 10.78],
            [106.69, 10.76]
          ]
        ]
      },
      "relation": "disjoint"
    }
  }
}
~~~

`DISJOINT` can return a huge number of documents because most geometries lie outside the query area. Combine it with additional business filters or restrict the dataset before running it in a broad query.

## 9. Avoiding WITHIN vs. CONTAINS direction confusion

These two relations are easily mixed up because natural language can express the same requirement from either side.

For example:

- Query shape is the city region.
- Document shape is a district.

If you want to find districts inside the city, use `WITHIN` because the shape in the document lies inside the query shape.

If you want to find a city that encloses a submitted district region, use `CONTAINS` because the shape in the document contains the query shape.

Diagram:

~~~text
WITHIN
Query shape:       +-------------------------+
Document shape:          +-------------+
                         |             |
                         +-------------+

Document lies within Query.


CONTAINS
Document shape:    +-------------------------+
Query shape:              +-------------+
                           |           |
                           +-------------+

Document encloses Query.
~~~

Explicitly identify which shape is stored in the index and which shape is sent in the query before choosing the relation. Do not infer the relation solely from natural-language phrasing like “find areas contained in” without identifying the subject of each shape.

## 10. Inline shape and indexed_shape

Geo-shape queries support two ways of supplying the query geometry:

1. `shape`: pass GeoJSON or WKT inline in the query.
2. `indexed_shape`: reference a shape already stored in a document in another index.

### Inline shape

Inline shapes fit cases where the query geometry is drawn by the user or generated dynamically:

~~~json
{
  "geo_shape": {
    "boundary": {
      "shape": {
        "type": "Envelope",
        "coordinates": [
          [106.68, 10.80],
          [106.75, 10.74]
        ]
      },
      "relation": "intersects"
    }
  }
}
~~~

An `Envelope` is a bounding rectangle defined by its top-left and bottom-right corners. For a GeoJSON envelope, the order is:

`[[minLon, maxLat], [maxLon, minLat]]`.

### Indexed shape

If the application frequently reuses the same geographic region, you can store that shape in a dedicated index:

~~~http
PUT /search-shapes
{
  "mappings": {
    "properties": {
      "geometry": {
        "type": "geo_shape"
      }
    }
  }
}
~~~

Store a shape with a fixed ID:

~~~http
PUT /search-shapes/_doc/central-region
{
  "geometry": {
    "type": "Polygon",
    "coordinates": [
      [
        [106.68, 10.75],
        [106.74, 10.75],
        [106.74, 10.81],
        [106.68, 10.81],
        [106.68, 10.75]
      ]
    ]
  }
}
~~~

Then reference the stored shape:

~~~json
{
  "query": {
    "geo_shape": {
      "boundary": {
        "indexed_shape": {
          "index": "search-shapes",
          "id": "central-region",
          "path": "geometry"
        },
        "relation": "intersects"
      }
    }
  }
}
~~~

Key properties of `indexed_shape`:

| Property | Meaning |
|---|---|
| `index` | Index holding the geometry document; defaults to `shapes` |
| `id` | ID of the document holding the geometry |
| `path` | Field containing the geometry; defaults to `shape` |
| `routing` | Routing of the geometry document if the index requires it |

Indexed shapes are useful when many queries share a common boundary, such as administrative zones, restricted zones, or service coverage areas. When the boundary changes, the application updates the shape document in the source index and subsequent queries continue referencing that ID.

## 11. ignore_unmapped when searching across multiple indices

When searching across multiple indices with differing mappings, an index might not declare the geometry field. By default, a geo_shape query on an unmapped field throws an error.

You can use `ignore_unmapped`:

~~~json
{
  "query": {
    "geo_shape": {
      "boundary": {
        "shape": {
          "type": "Point",
          "coordinates": [106.70, 10.77]
        },
        "relation": "intersects"
      },
      "ignore_unmapped": true
    }
  }
}
~~~

When `ignore_unmapped: true`, Elasticsearch skips indices lacking that field and matches no documents from unmapped indices. This is useful when querying an alias or multiple indices with heterogeneous schemas.

This option does not fix mappings and does not turn a missing field into a geo_shape. If the field is supposed to exist in every index, standardize mappings instead of relying on `ignore_unmapped`.

## 12. Geo-shape query on geo_point

A geo-shape query can also search documents with a `geo_point` field by comparing points against the query geometry.

Mapping example:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "keyword"
      },
      "location": {
        "type": "geo_point"
      }
    }
  }
}
~~~

Document:

~~~json
{
  "name": "Store A",
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
~~~

Find store points intersecting a polygon:

~~~json
{
  "query": {
    "geo_shape": {
      "location": {
        "shape": {
          "type": "Polygon",
          "coordinates": [
            [
              [106.68, 10.75],
              [106.72, 10.75],
              [106.72, 10.79],
              [106.68, 10.79],
              [106.68, 10.75]
            ]
          ]
        },
        "relation": "intersects"
      }
    }
  }
}
~~~

For points, `INTERSECTS` means the point lies inside or on the boundary of the query geometry. `WITHIN` can also be used to require the point to lie within the query shape. Do not use `CONTAINS` for a point to express that the query polygon contains the point; relation direction is always evaluated from the document's indexed geometry relative to the query geometry.

## 13. How does Spring Data Elasticsearch support GeoJSON?

Spring Data Elasticsearch includes GeoJSON types in the package:

`org.springframework.data.elasticsearch.core.geo`

Supported classes include:

- `GeoJsonPoint`.
- `GeoJsonMultiPoint`.
- `GeoJsonLineString`.
- `GeoJsonMultiLineString`.
- `GeoJsonPolygon`.
- `GeoJsonMultiPolygon`.
- `GeoJsonGeometryCollection`.

These GeoJSON types map to document structures conforming to the GeoJSON specification. When Spring Data writes the mapping for an entity with a GeoJSON property, that property is declared as a `geo_shape` field.

Entity example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.core.geo.GeoJsonPolygon;

@Document(indexName = "delivery-zones")
public class DeliveryZone {

    @Id
    private String id;

    private String name;

    private GeoJsonPolygon boundary;

    // Constructors, getters and setters
}
~~~

`GeoJsonPolygon` represents the delivery zone boundary. If a property is `GeoJsonPoint`, `GeoJsonLineString`, or other GeoJSON types, Spring Data also supports their corresponding mappings.

Spring Data can use `ElasticsearchOperations` to index and search entities. When complex geo_shape queries are needed, `NativeQuery` is a suitable choice because it lets you use the Elasticsearch Java API Client query builders.

## 14. Building a geo_shape query with NativeQuery

`NativeQuery` uses the query types from the Elasticsearch Java API Client. For geo_shape, you can use the `geoShape` builder and the `GeoShapeRelation` enum.

Example query finding delivery zones intersecting a polygon:

~~~java
import co.elastic.clients.elasticsearch._types.GeoShapeRelation;
import co.elastic.clients.json.JsonData;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Query;

String polygonJson = """
{
  "type": "Polygon",
  "coordinates": [
    [
      [106.69, 10.76],
      [106.71, 10.76],
      [106.71, 10.78],
      [106.69, 10.78],
      [106.69, 10.76]
    ]
  ]
}
""";

Query query = NativeQuery.builder()
    .withQuery(q -> q
        .geoShape(gs -> gs
            .field("boundary")
            .shape(s -> s
                .shape(JsonData.fromJson(polygonJson))
                .relation(GeoShapeRelation.Intersects)
            )
        )
    )
    .build();

SearchHits<DeliveryZone> hits = operations.search(
    query,
    DeliveryZone.class
);
~~~

Components:

- `NativeQuery.builder()` creates Spring Data's query builder.
- `withQuery` accepts an Elasticsearch Java API Client query.
- `geoShape` builds a geo_shape query.
- `field("boundary")` specifies the geometry field in the document.
- `JsonData.fromJson` parses the GeoJSON string into JSON data for the Java API Client.
- `GeoShapeRelation.Intersects` specifies the intersection relation.
- `operations.search` executes the query and maps results to entities.

You can swap the relation enum:

~~~java
GeoShapeRelation.Intersects
GeoShapeRelation.Within
GeoShapeRelation.Contains
GeoShapeRelation.Disjoint
~~~

Enum names in the Java API Client use PascalCase. In JSON Query DSL, relation values serialize to the corresponding lowercase strings.

Exact builder APIs depend on the Elasticsearch Java API Client version bundled with Spring Data Elasticsearch. Use dependencies compatible with your project's Spring Data version.

## 15. Combining geo_shape with business conditions

In practice, geospatial queries often accompany other conditions such as active status, service type, or access permissions.

Example finding active delivery zones intersecting a user-selected polygon:

~~~java
Query query = NativeQuery.builder()
    .withQuery(q -> q
        .bool(b -> b
            .filter(f -> f
                .term(t -> t
                    .field("active")
                    .value(true)
                )
            )
            .filter(f -> f
                .geoShape(gs -> gs
                    .field("boundary")
                    .shape(s -> s
                        .shape(JsonData.fromJson(polygonJson))
                        .relation(GeoShapeRelation.Intersects)
                    )
                )
            )
        )
    )
    .build();

SearchHits<DeliveryZone> hits = operations.search(
    query,
    DeliveryZone.class
);
~~~

In this example:

- The term query restricts to documents with `active = true`.
- The geo-shape query restricts to documents whose boundary intersects the polygon.
- The bool filter requires both conditions to hold.

If the query is constructed dynamically from user input, validate the incoming GeoJSON before sending it to Elasticsearch. Never accept an arbitrary JSON string and assume it is a valid polygon.

## 16. Constructing polygons with GeoJsonPolygon in Spring Data

If the application prefers building geometries with Java objects rather than keeping JSON strings, Spring Data provides `GeoJsonPolygon`.

Example:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.geo.GeoPoint;
import org.springframework.data.elasticsearch.core.geo.GeoJsonPolygon;

GeoJsonPolygon polygon = GeoJsonPolygon.ofGeoPoints(
    List.of(
        new GeoPoint(10.76, 106.69),
        new GeoPoint(10.76, 106.71),
        new GeoPoint(10.78, 106.71),
        new GeoPoint(10.78, 106.69),
        new GeoPoint(10.76, 106.69)
    )
);
~~~

Spring Data's `GeoPoint` accepts latitude and longitude in its constructor's parameter order. When converted to GeoJSON, coordinates serialize in longitude, latitude order.

The first and last points must match to close the polygon. The example above uses identical start/end coordinates.

`GeoJsonPolygon` is helpful when the application wants explicit Java types in entities or geometry construction logic. When converting the object into a query shape for the Java API Client, you still need to pass the data into `JsonData` or use an appropriate serialization mechanism.

## 17. Geometric relations are not the same as distance

A geo-shape query answers topological questions: whether two shapes intersect, contain each other, lie within each other, or are disjoint. It does not directly compute meter distances between two points or regions.

Choose queries based on requirements:

| Requirement | Appropriate query |
|---|---|
| Find documents with shapes intersecting a polygon | `geo_shape` with `INTERSECTS` |
| Find shapes lying completely inside a polygon | `geo_shape` with `WITHIN` |
| Find shapes enclosing the query polygon | `geo_shape` with `CONTAINS` |
| Find shapes disjoint from a polygon | `geo_shape` with `DISJOINT` |
| Find points within a radius around a center | `geo_distance` |
| Find points/shapes intersecting a rectangle | `geo_bounding_box` or `geo_shape` with envelope |
| Find shapes intersecting a geohash or tile | `geo_grid` |

The `WITHIN` and `CONTAINS` relations are evaluated in two-dimensional longitude/latitude space per Lucene's implementation. They are not great-circle spherical distance checks or geodesic calculations on an ellipsoid.

If business logic needs true surface distance on the Earth, such as stores within a 5 km radius, use the `geo_distance` query. Do not replace a distance query with an approximate large polygon when accurate meter results are needed.

## 18. Orientation and the international date line

Polygon coordinate rings have an orientation:

- `RIGHT`: counter-clockwise.
- `LEFT`: clockwise.

Elasticsearch uses orientation to determine whether a polygon crosses the international date line at longitude ±180°.

For GeoJSON, by default outer rings are counter-clockwise and inner rings are clockwise. This is the GeoJSON convention. For WKT, the mapping can configure a default orientation because WKT does not enforce a particular vertex ordering.

When a polygon spans less than 180° in longitude, orientation does not affect dateline resolution. When longitude span reaches 180° or more, orientation can dictate how Elasticsearch interprets and splits the polygon across the dateline.

If your application handles global data, check polygon orientation and how regions crossing ±180° longitude are represented. Do not arbitrarily reverse vertex order to fix a polygon that looks inverted.

## 19. Geometric meaning and semantic limits

Spatial relations in Elasticsearch are evaluated using two-dimensional geometry. With `geo_shape`, coordinates are WGS-84 longitude/latitude, yet predicates are not geodesic checks on an ellipsoid surface.

This has several implications:

- For small areas at low latitudes, results usually match the expectations of typical mapping apps.
- For very large regions or areas near the poles, two-dimensional planar evaluation may differ from spherical calculations.
- Query shapes are quantized to match the precision of indexed data.
- Indexed shapes are tessellated into triangular components; comparisons are not literal GeoJSON string comparisons.
- Although WITHIN/CONTAINS share names with common GIS predicates, they do not guarantee every detail of OGC Simple Features or DE-9IM.

If legal, cadastral, or urban-planning workflows must strictly conform to a specific GIS standard, verify semantics with representative test datasets and a dedicated GIS library before relying on query results as final authority.

## 20. Validating geometry data before indexing

Bad geometry data can cause indexing to fail or yield unexpected search results. Checks to perform at the ingestion layer include:

**Verify coordinate order.** GeoJSON must use longitude then latitude.

**Verify ranges.** Longitude generally lies between -180 and 180; latitude lies between -90 and 90.

**Verify closed polygons.** The start and end points of every ring must match.

**Verify point counts.** A polygon must have at least four coordinates for a closed ring.

**Verify holes.** Inner rings must lie inside the outer ring and must not be misinterpreted as solid area.

**Verify orientation.** Especially for WKT and polygons crossing the dateline.

**Verify self-intersections.** Self-intersecting polygons may be invalid or fail to capture the intended business semantics.

**Verify complexity.** Polygons with excessive vertices increase tessellation and search cost.

You can use `ignore_malformed` or `coerce` for certain ingestion scenarios, but never treat them as substitutes for validation. A skipped geometry cannot participate in queries as the application expects.

## 21. Performance and query selection

Geo-shape query cost depends on document count, vertex count, polygon complexity, and shard count.

Practical guidelines:

- Use `geo_point` when data only consists of points.
- Use `geo_shape` when storing lines, polygons, or complex shapes is required.
- Reduce unnecessary vertices while preserving business accuracy.
- Reuse `indexed_shape` for fixed query shapes used repeatedly.
- Combine geo_shape with other filters to narrow the document scope.
- Use `geo_distance` if you only need a radius around a point.
- Use `geo_bounding_box` if you only need a simple bounding rectangle.
- Avoid `DISJOINT` queries over overly broad document sets unless necessary.
- Monitor latency and query geometry size on real data.

When querying with a very complex polygon, passing an inline shape on every request inflates payloads. If that shape is reused often, storing it in a separate index and using an indexed shape can keep requests compact.

## 22. Common mistakes

**Swapping latitude and longitude.** Elasticsearch expects GeoJSON in longitude, latitude order. Reversing the order places the shape in the wrong location.

**Using geo_point for polygons.** geo_point only represents points. Boundaries and regions require a geo_shape field.

**Using shape instead of geo_shape.** shape uses Cartesian X/Y coordinates; geo_shape uses WGS-84 geographic coordinates.

**Forgetting to close polygons.** Ring start and end points must match. Otherwise, the document may be rejected on index.

**Confusing WITHIN and CONTAINS direction.** Relations always compare the document's indexed geometry against the query geometry. Identify which shape is stored and which is sent.

**Assuming INTERSECTS means containment.** Two shapes sharing even a single point, including touching edges, intersect.

**Using geo_shape for radius calculations.** Relations do not measure distances in meters. Use geo_distance when business rules require distance.

**Confusing GeoJSON and WKT orientation.** GeoJSON has its own default orientation rules; WKT requires attention to mapping orientation.

**Indexing polygons with too many vertices.** Tessellation can be resource-intensive. Simplify geometries carefully before indexing.

**Using indexed_shape with the wrong path or ID.** Verify index, document ID, routing, and field path containing the geometry.

**Ignoring inconsistent mappings.** When searching across multiple indices, an unmapped field can break the query. Use ignore_unmapped when semantically appropriate or standardize mappings.

**Treating results as strict GIS standards.** Elasticsearch runs 2D spatial operations over longitude/latitude. For workflows requiring strict GIS compliance, verify semantics.

## 23. Workflow for implementing geo_shape queries

You can implement geo_shape queries using these steps:

1. Determine whether the data consists only of points or includes lines, polygons, and regions.
2. Choose `geo_point` or `geo_shape` matching the data type.
3. Declare an explicit mapping before indexing documents.
4. Normalize coordinate sources to longitude, latitude.
5. Validate GeoJSON/WKT, ring closure, orientation, and coordinate ranges.
6. Index geometries into documents.
7. Decide whether query shapes will be passed inline or stored as indexed shapes.
8. Choose the relation according to the direction between indexed geometry and query geometry.
9. Combine the query with bool filters if other business conditions apply.
10. Execute via REST API, StringQuery, or NativeQuery.
11. Test results across boundary-touching, containment, enclosure, and disjoint scenarios.
12. Benchmark performance with polygons whose complexity mirrors production data.
13. Monitor mapping errors, malformed geometries, and execution latency.

## Conclusion

Geo-shape queries allow searching documents by geometric relationships between stored geometries and query geometries. The four main relations are `INTERSECTS`, `WITHIN`, `CONTAINS`, and `DISJOINT`. Always understand the comparison direction: Elasticsearch evaluates the shape in the document relative to the shape sent in the query.

To use it correctly, declare a `geo_shape` field, represent geometries in GeoJSON or WKT, maintain longitude/latitude order, and ensure polygons are closed. Query shapes can be supplied inline via `shape` or reused from another index via `indexed_shape`.

In Spring Data Elasticsearch, `GeoJsonPoint`, `GeoJsonLineString`, `GeoJsonPolygon`, and other GeoJSON implementations support geometry mapping. For complex queries, `NativeQuery` lets you build geo_shape queries with the Elasticsearch Java API Client. When meter-based distances are needed, use `geo_distance`; when strict GIS-compliant spatial operations are required, verify semantics with dedicated test datasets.

## References

- [Elasticsearch — Geo-shape field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/geo-shape)
- [Elasticsearch — Geo-shape query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-geo-shape-query)
- [Elasticsearch — Geo queries](https://www.elastic.co/docs/reference/query-languages/query-dsl/geo-queries)
- [Elasticsearch — Shape field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/shape)
- [Spring Data Elasticsearch — Object Mapping and GeoJSON Types](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch — Elasticsearch Operations and NativeQuery](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — GeoJsonPolygon API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/geo/GeoJsonPolygon.html)
- [Elasticsearch Java API Client — GeoShapeFieldQuery.Builder](https://artifacts.elastic.co/javadoc/co/elastic/clients/elasticsearch-java/8.18.8/co/elastic/clients/elasticsearch/_types/query_dsl/GeoShapeFieldQuery.Builder.html)
- [Elasticsearch Java API Client — GeoShapeRelation](https://artifacts.elastic.co/javadoc/co/elastic/clients/elasticsearch-java/8.17.3/co/elastic/clients/elasticsearch/_types/GeoShapeRelation.html)