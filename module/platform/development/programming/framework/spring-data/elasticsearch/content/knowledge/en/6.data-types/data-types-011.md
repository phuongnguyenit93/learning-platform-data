# Range, `geo_point`, `geo_shape`, and Spring Data Support Boundaries

Elasticsearch provides specialized data types for storing value intervals and spatial information. **Range fields** represent an interval with a lower bound and an upper bound, such as ages from 18 to 65 or a contract's effective period. **`geo_point`** represents a geographic location via latitude and longitude. **`geo_shape`** represents complex geometries such as routes, service areas, or geographic polygons.

Spring Data Elasticsearch supports mapping these types into Java entities, offering several data types and query abstractions to work with them. However, Spring Data does not turn the entirety of Elasticsearch Query DSL into repository methods or `Criteria` methods. When an advanced option is needed that the abstraction cannot express, the application can use `NativeQuery`/the Elasticsearch Java API Client or the REST API.

This lesson explains how to choose data types, declare mappings, represent data in Java, query ranges and geographic data, and understand the boundary between Elasticsearch features and the API surface Spring Data provides.

## 1. Choosing the Right Data Type

The three field groups serve different goals:

| Field type | Data represented | Business example |
|---|---|---|
| `integer_range`, `long_range`, `float_range`, `double_range`, `date_range`, `ip_range` | An interval with a lower and upper bound | Valid age range, price band, contract duration, IP address range |
| `geo_point` | A geographic point (or multiple points in the same field) | Store location, delivery address, device location |
| `geo_shape` | A geographic geometry that can include points, lines, or regions | Area boundaries, delivery routes, service coverage zones |

Choose the type based on the nature of the data. If you need to find stores within a 5 km radius, `geo_point` is usually appropriate. If you need to find delivery zones intersecting a selected region, use `geo_shape`. If you need to store a policy's effective interval such as date A to date B, `date_range` expresses the data more directly than two separate date fields.

## 2. Range Fields in Elasticsearch

### 2.1. Supported Range Types

Elasticsearch has six main range types:

| Type | Value domain |
|---|---|
| `integer_range` | Signed 32-bit integers |
| `long_range` | Signed 64-bit integers |
| `float_range` | 32-bit floating-point numbers |
| `double_range` | 64-bit floating-point numbers |
| `date_range` | Date-time intervals |
| `ip_range` | IPv4 or IPv6 address intervals |

A range is expressed using bounds. Elasticsearch supports:

- `gt`: lower bound excluding the boundary value.
- `gte`: lower bound including the boundary value.
- `lt`: upper bound excluding the boundary value.
- `lte`: upper bound including the boundary value.

Example of an age range from 18 to under 30:

```json
{
  "validAge": {
    "gte": 18,
    "lt": 30
  }
}
```

The value 18 belongs to the interval, whereas 30 does not. If `lte: 30` is used, the upper bound is included.

A range field stores interval data inside a single field. It differs from running a `range` query on an ordinary scalar field. For example:

- A `price` field of type `long` stores a single price value; a range query checks whether that price falls inside a search interval.
- A `priceBand` field of type `long_range` stores a price interval per document; a range query can compare the document's interval against the query's interval using interval relations.

### 2.2. Declaring Mappings for Range Fields

Example creating an index with an expected attendee range and an event active period:

```http
PUT events
{
  "mappings": {
    "properties": {
      "expectedAttendees": {
        "type": "integer_range"
      },
      "activePeriod": {
        "type": "date_range",
        "format": "strict_date_optional_time||epoch_millis"
      }
    }
  }
}
```

When writing a document:

```http
PUT events/_doc/event-100
{
  "expectedAttendees": {
    "gte": 10,
    "lt": 20
  },
  "activePeriod": {
    "gte": "2026-11-01T00:00:00Z",
    "lte": "2026-11-30T23:59:59Z"
  }
}
```

One bound can be left open to represent an interval unbounded on that side. For example, `{"gte": 18}` represents all values from 18 upward. Check input formats for `date_range` just as you would when working with `date` fields.

Specifically for `ip_range`, CIDR notation is also accepted—such as `192.168.0.0/16`—in addition to `gte`/`lte` bound objects:

```json
{
  "allowedNetwork": "192.168.0.0/16"
}
```

### 2.3. Querying Range Fields

A range query on a range field supports the `relation` parameter:

| Relation | Meaning for the range stored in the document |
|---|---|
| `INTERSECTS` | The document's range intersects the query range; this is the default |
| `CONTAINS` | The document's range contains the entire query range |
| `WITHIN` | The document's range lies completely within the query range |

Example finding events whose effective period falls within November 2026:

```http
GET events/_search
{
  "query": {
    "range": {
      "activePeriod": {
        "gte": "2026-11-01T00:00:00Z",
        "lt": "2026-12-01T00:00:00Z",
        "relation": "within"
      }
    }
  }
}
```

If `intersects` is used, a document whose effective period merely overlaps the query interval is matched. For example, a contract from October 25 to November 5 intersects November, even though it does not lie entirely within that month.

Do not confuse `relation` on range fields with `relation` on `geo_shape`. Both use words like `intersects`, `contains`, and `within`, but they compare two completely different kinds of data.

### 2.4. Range Fields Can Use `term` Queries

In some cases, you can use a `term` query to check whether a single value falls inside a stored range:

```http
GET events/_search
{
  "query": {
    "term": {
      "expectedAttendees": {
        "value": 15
      }
    }
  }
}
```

A document with range `gte: 10, lt: 20` matches because 15 lies within the interval. This differs from running a range query on a scalar integer field.

### 2.5. Limitations of Range Fields

Range fields support interval queries, but aggregation support is limited. Elasticsearch supports aggregations like `histogram` and `cardinality` for range fields; do not assume every aggregation designed for numeric fields works identically.

Elasticsearch does not support sorting directly on range field types. If you need to sort by an endpoint of an interval, also store corresponding scalar fields (e.g., `minimumPrice` or `maximumPrice`) and sort on those fields.

If business logic needs statistics over single values, storing a dedicated numeric scalar field may be better. When storing effective intervals and comparing interval-to-interval relationships, a range field is the direct model.

## 3. Mapping Range Fields in Spring Data Elasticsearch

Spring Data Elasticsearch has `FieldType` enum values corresponding to range mappings:

- `Integer_Range`
- `Long_Range`
- `Float_Range`
- `Double_Range`
- `Date_Range`
- `Ip_Range`

When declaring a field with one of these types, the Java property must convert into the range structure Elasticsearch expects.

### 3.1. Using `org.springframework.data.domain.Range<T>`

In current Spring Data versions, you can use `Range<T>` from Spring Data Commons:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.domain.Range;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "events")
public class EventDocument {

    @Id
    private String id;

    @Field(type = FieldType.Integer_Range)
    private Range<Integer> expectedAttendees;

    // Constructors, getters and setters
}
```

Creating an interval with both bounds inclusive:

```java
Range<Integer> attendees = Range.closed(10, 20);
```

Other factory methods include `Range.open(from, to)`, `Range.leftOpen(from, to)`, `Range.rightOpen(from, to)`, `Range.unbounded()`, and builders for half-bounded intervals. `Range.closed(10, 20)` includes both 10 and 20; `Range.rightOpen(10, 20)` includes 10 and excludes 20.

Version note: Spring Data Elasticsearch previously had `org.springframework.data.elasticsearch.core.Range`. That older class was deprecated starting in Spring Data Elasticsearch 5.0 in favor of `org.springframework.data.domain.Range`. When reading older code or docs, check the package import to avoid using the deprecated class.

### 3.2. Using a Dedicated Class to Represent Bounds

If you want to model range data with a specific domain class, you can declare a class whose properties map to `gte`, `gt`, `lte`, or `lt`:

```java
import org.springframework.data.elasticsearch.annotations.Field;

public class ValidAge {

    @Field(name = "gte")
    private Integer minimum;

    @Field(name = "lt")
    private Integer maximumExclusive;

    public ValidAge() {
    }

    public ValidAge(Integer minimum, Integer maximumExclusive) {
        this.minimum = minimum;
        this.maximumExclusive = maximumExclusive;
    }

    // Getters and setters
}
```

Entity:

```java
@Document(indexName = "people")
public class PersonDocument {

    @Id
    private String id;

    @Field(type = FieldType.Integer_Range)
    private ValidAge validAge;

    // Getters and setters
}
```

During conversion, Spring Data maps `minimum` to the `gte` key and `maximumExclusive` to the `lt` key. This is useful when domain property names should be more descriptive than Elasticsearch's bound keys.

### 3.3. Supported Value Types

Current Spring Data Elasticsearch documentation lists common range value types including `Integer`, `Long`, `Float`, `Double`, `Date`, and types implementing `TemporalAccessor` such as the Java Time API. For `ip_range`, verify converters and representations supported in your Spring Data version; if the abstraction cannot convert the desired IP type, you can use a custom class or custom converter.

Never assume every Java type works with every `FieldType.*_Range`. The entity's data type, Elasticsearch mapping, and converter must be mutually compatible.

## 4. `geo_point`: Storing a Geographic Location

`geo_point` stores a point on Earth using latitude and longitude. Elasticsearch uses the WGS-84 coordinate system.

Example location:

```json
{
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
```

In the example, `lat` is 10.7769 and `lon` is 106.7009. Valid latitudes range from -90 to 90; valid longitudes range from -180 to 180.

### 4.1. Ways to Represent a Geo Point

Elasticsearch accepts multiple point formats:

| Format | Example | Coordinate order |
|---|---|---|
| Object with `lat` and `lon` | `{"lat": 10.77, "lon": 106.70}` | Explicit property names |
| Array | `[106.70, 10.77]` | `[lon, lat]` |
| String | `"10.77,106.70"` | `lat,lon` |
| GeoJSON Point | `{"type":"Point","coordinates":[106.70,10.77]}` | `[lon, lat]` |
| WKT | `"POINT (106.70 10.77)"` | `POINT(lon lat)` |
| Geohash | `"w3gvk"` | Encoded location |

This is a frequent source of bugs: strings use `lat,lon`, whereas arrays, GeoJSON, and WKT use `lon,lat`. Verify coordinate order before sending data.

### 4.2. `geo_point` Mapping

Create the mapping:

```http
PUT places
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
```

Write a document:

```http
PUT places/_doc/place-1
{
  "name": "Central Store",
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
```

A `geo_point` field can hold one point or multiple points. If a document has multiple points, geographic queries generally match the document if any of those points satisfies the condition.

### 4.3. Mapping `geo_point` in Spring Data Elasticsearch

Spring Data Elasticsearch includes the `GeoPoint` class in package `org.springframework.data.elasticsearch.core.geo`. Its constructor accepts latitude first, longitude second:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.GeoPointField;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Document(indexName = "places")
public class Place {

    @Id
    private String id;

    private String name;

    @GeoPointField
    private GeoPoint location;

    public Place() {
    }

    public Place(String id, String name, double latitude, double longitude) {
        this.id = id;
        this.name = name;
        this.location = new GeoPoint(latitude, longitude);
    }

    // Getters and setters
}
```

Spring Data provides converters to serialize `GeoPoint` into a `lat`/`lon` pair on write and back on read. Depending on the Java type used, you can also use `org.springframework.data.geo.Point`; Spring Data Elasticsearch supports converting that `Point` type to `lat`/`lon` representation as well.

If the property already has type `GeoPoint`, Spring Data can recognize the type without an extra annotation in some configurations. `@GeoPointField` states the mapping intent explicitly; `@Field(type = FieldType.Geo_Point)` is another way to declare the field type via `@Field` in versions that support it.

### 4.4. Common Queries with `geo_point`

`geo_point` supports the following needs:

- Finding points within a radius (`geo_distance`).
- Finding points inside a rectangle (`geo_bounding_box`).
- Finding points inside a geometry (`geo_shape` query).
- Sorting documents by distance to a point (`_geo_distance` sort).
- Aggregating by distance or geographic grids such as geohash, geotile, or geohex.

Example finding places within 5 km of a center point:

```http
GET places/_search
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

`geo_distance` restricts results by radius. `_geo_distance` sort orders closer results first. Distance defaults to arc calculation over Earth's surface (`arc`); `plane` can be faster but is less accurate, especially over long distances or near the poles.

Bounding box example:

```http
GET places/_search
{
  "query": {
    "geo_bounding_box": {
      "location": {
        "top_left": {
          "lat": 10.90,
          "lon": 106.55
        },
        "bottom_right": {
          "lat": 10.65,
          "lon": 106.85
        }
      }
    }
  }
}
```

## 5. `geo_shape`: Storing Geographic Geometries

`geo_shape` is used when data is more than a point. For instance, a delivery zone with a polygon boundary, a route shaped as a LineString, or a protected area composed of multiple sub-regions.

Elasticsearch supports GeoJSON and Well-Known Text (WKT) geometries. Common types include:

| GeoJSON | WKT | Purpose |
|---|---|---|
| `Point` | `POINT` | A single point |
| `MultiPoint` | `MULTIPOINT` | Multiple discrete points |
| `LineString` | `LINESTRING` | A path connecting two or more points |
| `MultiLineString` | `MULTILINESTRING` | Multiple separate paths |
| `Polygon` | `POLYGON` | A polygon region, optionally with interior holes |
| `MultiPolygon` | `MULTIPOLYGON` | Multiple polygons |
| `GeometryCollection` | `GEOMETRYCOLLECTION` | Collection of multiple geometry types |
| `envelope` | `BBOX` | Bounding rectangle |

GeoJSON and WKT order coordinates as longitude first, latitude second. This is `x, y` order, opposite to how addresses are commonly spoken as `latitude, longitude`.

### 5.1. `geo_shape` Mapping

Create an index with a `serviceArea` field of type `geo_shape`:

```http
PUT delivery-zones
{
  "mappings": {
    "properties": {
      "zoneName": {
        "type": "keyword"
      },
      "serviceArea": {
        "type": "geo_shape"
      }
    }
  }
}
```

Write a polygon in GeoJSON:

```http
PUT delivery-zones/_doc/zone-1
{
  "zoneName": "District Zone",
  "serviceArea": {
    "type": "Polygon",
    "coordinates": [
      [
        [106.68, 10.78],
        [106.74, 10.78],
        [106.74, 10.82],
        [106.68, 10.82],
        [106.68, 10.78]
      ]
    ]
  }
}
```

Polygons must be closed: the first and last coordinates of each linear ring must be identical. A polygon requires at least four coordinates in its outer ring because the starting point repeats at the end. If a polygon has holes, subsequent rings describe the interior cutouts.

### 5.2. Polygon Orientation

GeoJSON specifies outer rings in counterclockwise order and hole rings in clockwise order. Elasticsearch defaults to `RIGHT`/counterclockwise orientation. For WKT, orientation configuration may be needed because WKT does not enforce vertex order the same way GeoJSON does.

Orientation is especially critical for polygons crossing the international date line. If data is generated by an external GIS system, confirm its vertex-order convention before indexing.

### 5.3. Common Mapping Options

`geo_shape` provides several options:

- `orientation`: specifies how polygon vertex order is interpreted.
- `ignore_malformed`: if enabled, malformed geometries can be ignored instead of rejecting the entire document.
- `ignore_z_value`: defaults to allowing a third coordinate dimension while indexing only longitude/latitude.
- `coerce`: if enabled, Elasticsearch can automatically close unclosed linear rings.
- `index`: toggles fast search indexing on the field.
- `doc_values`: controls columnar data supporting operations such as aggregations/scripts.

Do not enable `ignore_malformed` or `coerce` to hide invalid data if the application must guarantee accurate geographic boundaries. Validate geometries at the source or in the ingest pipeline.

## 6. Mapping GeoJSON in Spring Data Elasticsearch

Spring Data Elasticsearch provides the `GeoJson` interface and classes representing common geometries:

- `GeoJsonPoint`
- `GeoJsonMultiPoint`
- `GeoJsonLineString`
- `GeoJsonMultiLineString`
- `GeoJsonPolygon`
- `GeoJsonMultiPolygon`
- `GeoJsonGeometryCollection`

These types convert into GeoJSON structures in documents. When Spring Data generates entity mappings, the corresponding GeoJSON property is declared as `geo_shape`.

Entity example:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.GeoShapeField;
import org.springframework.data.elasticsearch.core.geo.GeoJsonPolygon;

@Document(indexName = "delivery-zones")
public class DeliveryZone {

    @Id
    private String id;

    private String zoneName;

    @GeoShapeField
    private GeoJsonPolygon serviceArea;

    // Constructors, getters and setters
}
```

`@GeoShapeField` exposes options related to orientation, `ignoreMalformed`, `ignoreZValue`, and `coerce` in versions featuring this annotation. Geometry properties remain represented using appropriate GeoJSON classes.

You can create a GeoJSON point using a factory method:

```java
import org.springframework.data.elasticsearch.core.geo.GeoJsonPoint;

GeoJsonPoint point = GeoJsonPoint.of(106.7009, 10.7769);
```

With `GeoJsonPoint.of(x, y)`, `x` is longitude and `y` is latitude following GeoJSON convention. If you already have a `GeoPoint` whose constructor took latitude before longitude, convert via `GeoJsonPoint.of(geoPoint)` to avoid swapping coordinates manually.

Spring Data provides converters for supported GeoJSON types. If the application requires a specialized geometry without a matching library class, consider representing it as GeoJSON/WKT at the client layer, writing a custom converter, or using the Elasticsearch Java API Client directly.

## 7. Querying `geo_shape` and Spatial Relations

A `geo_shape` query compares the geometry stored in a document against a query shape. Primary relations:

| Relation | Meaning |
|---|---|
| `INTERSECTS` | The two geometries share at least one point; default |
| `DISJOINT` | The two geometries share no points |
| `WITHIN` | The document's geometry lies completely inside the query shape |
| `CONTAINS` | The document's geometry contains the entire query shape |

Example finding delivery zones intersecting a bounding rectangle:

```http
GET delivery-zones/_search
{
  "query": {
    "geo_shape": {
      "serviceArea": {
        "shape": {
          "type": "envelope",
          "coordinates": [
            [106.65, 10.85],
            [106.80, 10.70]
          ]
        },
        "relation": "intersects"
      }
    }
  }
}
```

`envelope` is an Elasticsearch extension representing a rectangle via two opposite corners. It is not one of the GeoJSON classes listed in Spring Data above.

Elasticsearch spatial relations are computed on Lucene's two-dimensional geometric model over longitude/latitude coordinates. Do not assume `within` or `contains` matches every nuance of OGC GIS/DE-9IM predicates identically. If your application demands exact geometric semantics aligned with a specific GIS standard, verify behavior using a representative test suite.

`WITHIN` does not support line geometries in `geo_shape` queries. `geo_shape` operations are also not geodesic distance measurements on Earth's surface. When radius search across the globe is needed, use `geo_distance`.

Due to its complex structure and indexing, Elasticsearch does not support direct sorting by `geo_shape` and does not return geometries via ordinary field retrieval; shape values are read from `_source`. If sorting by distance to a center is needed, consider `geo_point` or a dedicated computed field.

## 8. Geo Queries in Spring Data Elasticsearch

Spring Data provides `Criteria` for certain geographic operations. Example finding places within a 5 km radius:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.stereotype.Service;

@Service
public class PlaceSearchService {

    private final ElasticsearchOperations operations;

    public PlaceSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<Place> findNearby() {
        Criteria criteria = Criteria.where("location")
                .within(new GeoPoint(10.7769, 106.7009), "5km");

        CriteriaQuery query = new CriteriaQuery(criteria);
        return operations.search(query, Place.class);
    }
}
```

The `GeoPoint(latitude, longitude)` constructor accepts latitude before longitude. The `within(GeoPoint, String)` method builds a condition finding locations within the specified distance.

For GeoJSON shapes, `Criteria` provides methods such as `intersects`, `within`, `contains`, and `isDisjoint` on `GeoJson`:

```java
Criteria criteria = Criteria.where("serviceArea")
        .intersects(queryPolygon);

CriteriaQuery query = new CriteriaQuery(criteria);
SearchHits<DeliveryZone> hits = operations.search(query, DeliveryZone.class);
```

Specific methods can vary across release trains. Check the Javadoc of the exact Spring Data Elasticsearch version in use before applying them.

## 9. Range Queries and Geo Queries Are Not Synonymous with Repository Methods

Spring Data Elasticsearch supports repository query methods, `@Query`, `CriteriaQuery`, `NativeQuery`, and `ElasticsearchOperations`. However, not every Query DSL construct has a derived repository method name.

For example, `findByPriceBetween(min, max)` can suit a scalar numeric field, but it does not automatically mean querying an interval relation between two range fields. Similarly, `findByLocationWithin(...)` is not a universally derivable query method for arbitrary property names and geometry types.

When needing exact `relation`, query shapes, `indexed_shape`, distance types, or specialized Elasticsearch options, use `NativeQuery` or the Elasticsearch Java API Client. REST Query DSL examples directly reflect what the server receives and are ideal for testing before translating into the Java API.

### 9.1. Using `NativeQuery` When Full Query DSL Is Needed

`NativeQuery` is Spring Data Elasticsearch's abstraction for queries built with the Elasticsearch Java API Client. Exact query builder syntax depends on the client version bundled by your Spring Data release train. Conceptual example:

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

// Build a native geo query with the Elasticsearch Java API Client query builder.
// Pass the resulting query into NativeQuery.builder().withQuery(...).build().
// Then execute it with operations.search(nativeQuery, Place.class).
```

For complex queries, do not force every option into `Criteria` if the abstraction cannot express it. Using the Java API Client query builder lets you leverage strongly typed request/query types generated for your exact Elasticsearch version.

### 9.2. Using the REST API to Confirm Semantics

Before writing queries in Java, test directly using Dev Tools or an HTTP client:

```http
GET places/_search
{
  "query": {
    "geo_distance": {
      "distance": "5km",
      "location": [106.7009, 10.7769]
    }
  }
}
```

Once results are right, translate the query structure into `NativeQuery` or the client API. This separates Query DSL semantics bugs from Java object conversion issues.

## 10. Spring Data Elasticsearch Support Boundaries

To choose the right abstraction, separate support into layers:

| Layer | Spring Data support | When is a lower-level API needed? |
|---|---|---|
| Range mapping | Provides `FieldType` for six range types and converters for `Range<T>`/bound-representing classes | When needing range types or IP formats without a suitable converter |
| `geo_point` mapping | Provides `GeoPoint`, `Point`, lat/lon converters, and field annotations | When needing newer Elasticsearch mapping options not yet exposed on that version's annotations |
| `geo_shape` mapping | Provides common GeoJSON types and `@GeoShapeField` | When needing special geometries or structures lacking a matching GeoJSON class |
| Geo queries | `Criteria` provides selected distance, bounding box, and GeoJSON relation methods; `GeoDistanceOrder` for distance sorting | When needing full `geo_distance`, `geo_shape`, indexed shape, or newer API options |
| Range queries | Standard query abstractions and `NativeQuery` | When needing specific range relations or newer Query DSL options not exposed by abstractions |
| Mapping management | `@Field`, `@GeoPointField`, `@GeoShapeField`, `IndexOperations` | When needing newer JSON mappings/settings not yet supported in annotations |

Spring Data focuses on object mapping and data-access abstractions. The Elasticsearch server enforces mapping rules, range relations, spatial relations, and field-type constraints. Just because a feature exists in Elasticsearch does not mean every option has a convenience method in Spring Data.

### 10.1. Checking Library Versions

Classes, annotations, and query builders change across release trains. When reading examples online, check:

- Which Spring Data Elasticsearch version your Spring Boot version manages.
- Whether `FieldType` in that version includes enums like `Geo_Point`, `Geo_Shape`, `Integer_Range`.
- Whether `Range` is imported from `org.springframework.data.domain` or the legacy `org.springframework.data.elasticsearch.core` package.
- Whether the needed `GeoJson` classes and `Criteria` methods appear in that version's Javadoc.
- Whether the Elasticsearch server supports the query options or mapping parameters your code sends.

Do not upgrade the Elasticsearch Java API Client independently to a different major version from your Spring Data release without checking compatibility. Spring Data Elasticsearch integrates the client via a dependency train; request types and builders must match the actual client on the classpath.

### 10.2. Automatic Mapping Does Not Replace Inspecting Actual Mappings

Spring Data can create mappings from annotations and entity metadata. However, an index might already exist, or mappings might be managed via index templates. Modifying annotations does not automatically alter existing mappings.

After creating an index, inspect the mapping:

```http
GET places/_mapping
```

```http
GET delivery-zones/_mapping
```

If a field is `object` instead of `geo_point` or `geo_shape`, geographic queries will not work as expected. If a range field was created as a numeric/date scalar, queries with range relations will not behave with range-field semantics either.

## 11. Common Mistakes

### Swapping Latitude and Longitude

`GeoPoint(latitude, longitude)` takes latitude first. GeoJSON and Elasticsearch arrays use `[longitude, latitude]`. Check the format's rule before constructing objects or JSON.

### Using `geo_point` for Area Data

A point cannot fully represent a polygon boundary. If area intersections or containment checks are needed, use `geo_shape`.

### Using `geo_shape` for Every Point Without Needing Geometries

If you only store simple locations and need distance sorting, radius queries, or distance aggregations, `geo_point` is usually simpler and better suited.

### Unclosed Polygons

Outer rings or hole rings of a polygon must have identical first and last coordinates. Unclosed polygons may be rejected by Elasticsearch unless `coerce` allows auto-closing.

### Wrong Polygon Orientation

Vertex order can alter how Elasticsearch interprets a polygon region, especially when geometries cross the international date line. Confirm orientation rules across your data source and mapping.

### Importing the Wrong `Range` Class

In Spring Data Elasticsearch 5.x+, `org.springframework.data.elasticsearch.core.Range` is deprecated in favor of `org.springframework.data.domain.Range`. Check imports if the compiler warns or APIs mismatch.

### Expecting `Criteria` to Support Every Query DSL Option

`Criteria` is a convenience abstraction for a subset of queries. When needing an unexposed relation, option, or complex structure, use `NativeQuery` or the Elasticsearch Java API Client.

### Confusing Range Fields with Range Queries on Scalar Fields

A `long` field stores one number; a `long_range` field stores an interval. Document structures and query semantics differ. Check mappings before designing queries.

### Using `geo_shape` to Measure Exact Earth-Surface Distances

`geo_shape` spatial relations rely on two-dimensional geometry. When needing geographic radius measurements, use `geo_distance` and pick the appropriate distance type.

## 12. Implementation Workflow

When designing an entity with range or geographic data, you can follow this workflow:

1. Determine whether the data is a single value, an interval, a point, or a geometry.
2. Pick the matching field type: scalar, `*_range`, `geo_point`, or `geo_shape`.
3. Pick a Spring Data–supported Java type; for ranges on current versions, consider `org.springframework.data.domain.Range<T>`.
4. Declare mappings via `@Field`, `@GeoPointField`, or `@GeoShapeField` matching your release train.
5. Define open/closed interval rules for ranges and coordinate order for geographic data.
6. Verify converter output and the actual JSON mapping after creating the index.
7. Test queries directly with Elasticsearch Query DSL to confirm semantics.
8. Express queries with `Criteria` if the abstraction covers all needs; otherwise, use `NativeQuery`/Elasticsearch Java API Client.
9. Test edge cases: equal bounds, unbounded intervals, boundary coordinates, polygons with holes, and geometries crossing the date line.
10. Track Spring Data and Elasticsearch server versions during upgrades to confirm field types and query options remain compatible.

## 13. Summary

Range fields store an interval in each document and support comparing intervals using `intersects`, `contains`, or `within`. `geo_point` stores latitude/longitude positions for radius search, bounding boxes, distance sorting, and geo aggregations. `geo_shape` stores geometries such as lines and polygons to query spatial relations.

Spring Data Elasticsearch supports mapping range types, `GeoPoint`/`Point`, and common GeoJSON geometries. `Criteria` covers a subset of geo queries and `ElasticsearchOperations` executes queries; for advanced Query DSL or options not exposed by abstractions, use `NativeQuery` or the Elasticsearch Java API Client. Understanding the distinction between mappings, Java types, and Query DSL helps you choose the right data structures, avoid coordinate-order bugs, and avoid mistaking Spring Data's boundaries for Elasticsearch server limitations.

## References

- [Spring Data Elasticsearch – Object Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch – Criteria API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/Criteria.html)
- [Elasticsearch – Range field types](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/range)
- [Elasticsearch – Geo point field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/geo-point)
- [Elasticsearch – Geo shape field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/geo-shape)
- [Elasticsearch – Geo queries](https://www.elastic.co/docs/reference/query-languages/query-dsl/geo-queries)
