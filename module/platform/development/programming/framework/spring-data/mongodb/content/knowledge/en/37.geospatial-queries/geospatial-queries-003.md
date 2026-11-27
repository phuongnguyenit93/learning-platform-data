# `2d` and `2dsphere` Indexes in Spring Data MongoDB

When building features like "find stores near me", checking whether a point lies inside a delivery zone, or finding routes that intersect a region, an application needs to query data by location. **Spring Data MongoDB** provides repositories and `MongoTemplate` to work with these queries; **MongoDB** uses spatial indexes to narrow down candidate documents and perform appropriate geometric calculations. The two index types to distinguish are **`2d`** and **`2dsphere`**.

After this lesson, you will be able to choose the right index type, normalize coordinate structures, declare indexes using MongoDB or Spring Data MongoDB, write queries, and read execution plans to verify performance.

## 1. `2d` and `2dsphere` Solve Two Different Geometric Models

| Criterion | `2d` | `2dsphere` |
| --- | --- | --- |
| Model | Cartesian plane, Euclidean distance | Earth's surface, spherical calculations |
| Typical data | Legacy coordinate pairs `[x, y]` or objects with two coordinate fields | GeoJSON (`Point`, `LineString`, `Polygon`, …) and valid legacy coordinate pairs |
| Use cases | Internal coordinates in warehouse floor plans, games, or layouts | Real-world locations with longitude/latitude, radius searches, geographic regions |
| Typical queries | `$near` on planar coordinates; `$geoWithin` with `$box`, `$polygon` | `$near`, `$nearSphere`, `$geoWithin`, `$geoIntersects`, `$geoNear` with appropriate geographic semantics |
| Distance unit | Unit of the source coordinate system | With GeoJSON and `$near`/`$geoNear`: typically **meters**; with some spherical legacy syntaxes: **radians** |
| Optional config | Coordinate domain configurable via `min`, `max` | Designed for longitude/latitude per GeoJSON/WGS84 |

**Quick rule of thumb:** If coordinates represent locations on a world map, prefer **GeoJSON + `2dsphere`**. Only choose `2d` when the problem genuinely operates on a flat plane and distance units are defined by the application. Do not apply the Euclidean distance formula directly to longitude/latitude degrees for a requirement like "2 km apart": one degree of longitude corresponds to different distances depending on latitude.

> Indexes help MongoDB find candidates efficiently; they do not replace defining the right coordinate system, measurement units, and business conditions. A "fast" result can still be wrong if data has longitude and latitude swapped.

## 2. Normalizing Data Before Creating Indexes

### 2.1. GeoJSON for Geographic Locations

A GeoJSON `Point` has the structure `{"type": "Point", "coordinates": [longitude, latitude]}`. **The order is `[longitude, latitude]`**, not `[latitude, longitude]`. Longitude lies in `[-180, 180]`, latitude in `[-90, 90]`; geographic GeoJSON coordinates use the WGS84 reference system.

Example of three *simulated* locations in the Ho Chi Minh City area:

```javascript
db.places.insertMany([
  {
    _id: "p1",
    name: "Cafe A",
    category: "cafe",
    location: { type: "Point", coordinates: [106.7000, 10.7800] }
  },
  {
    _id: "p2",
    name: "Cafe B",
    category: "cafe",
    location: { type: "Point", coordinates: [106.7070, 10.7830] }
  },
  {
    _id: "p3",
    name: "Shop C",
    category: "shop",
    location: { type: "Point", coordinates: [106.7600, 10.8300] }
  }
]);
```

To describe an area instead of a point, GeoJSON uses `Polygon`. A polygon's exterior ring must be **closed**: the first and last coordinates of the ring must match. `LineString` represents a line and can be used with geometric intersection queries. These types suit `2dsphere` when the application needs to evaluate real geographic shapes.

### 2.2. Legacy Coordinates for a Flat Plane

For a floor plan using application-defined meter units, you can store:

```javascript
db.flat_points.insertMany([
  { _id: "a1", name: "Rack A", position: [10, 20] },
  { _id: "b1", name: "Rack B", position: [13, 24] }
]);
```

Here `[10, 20]` is `[x, y]` on the floor plan, **not** a location on Earth. Although legacy coordinate pairs can also represent longitude/latitude, a `2d` index still performs calculations on a flat plane. Avoid mixing GeoJSON and internal coordinate systems in the same field.

## 3. Creating and Managing Indexes in MongoDB

### 3.1. Creating a `2dsphere` Index

```javascript
db.places.createIndex(
  { location: "2dsphere" },
  { name: "location_2dsphere" }
);
```

MongoDB uses the geometry data in `location` to support proximity, containment, and intersection queries. For queries that frequently filter by `category` while searching by location, you can **test** a compound index:

```javascript
db.places.createIndex(
  { category: 1, location: "2dsphere" },
  { name: "category_location_2dsphere" }
);
```

The effectiveness of a compound index depends on query patterns, `category` selectivity, and real data; verify with `explain()` rather than assuming a compound index is always better. Missing, `null`, or empty-array `location` fields will not have an entry in a `2dsphere` index; this index behaves *sparsely* by design. For compound indexes containing `2dsphere`, whether a document is indexed depends on the spatial field.

### 3.2. Creating a `2d` Index

```javascript
db.flat_points.createIndex(
  { position: "2d" },
  { name: "position_2d", min: -1000, max: 1000 }
);
```

`min` and `max` here define the coordinate bounds of the planar index; choose them based on the actual `[x, y]` range of your data. Do not copy those two values for longitude/latitude systems or blindly for every floor plan: a point outside the index's accepted bounds can cause write/index operations to fail.

### 3.3. Inspecting Existing Indexes

```javascript
db.places.getIndexes();
db.flat_points.getIndexes();
```

When migrating a field from planar data to GeoJSON, you must **convert the data, add the appropriate index, and verify queries** before dropping the old index. Do not assume changing a Java annotation alone will automatically convert data types or remove an existing `2d` index in the database.

## 4. Declaring Indexes with Spring Data MongoDB

Spring Data provides `GeoJsonPoint` to represent a GeoJSON point and `@GeoSpatialIndexed` to describe the index on an entity property.

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexed;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "places")
public class Place {
    @Id
    private String id;

    private String name;
    private String category;

    @GeoSpatialIndexed(type = GeoSpatialIndexType.GEO_2DSPHERE)
    private GeoJsonPoint location;

    protected Place() {}

    public Place(String name, String category, GeoJsonPoint location) {
        this.name = name;
        this.category = category;
        this.location = location;
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public String getCategory() { return category; }
    public GeoJsonPoint getLocation() { return location; }
}
```

Example instantiating the entity:

```java
Place place = new Place(
    "Cafe A", "cafe", new GeoJsonPoint(106.7000, 10.7800)
);
// placeRepository.save(place);
```

`GeoJsonPoint` preserves the `(longitude, latitude)` parameter order and, when mapped to MongoDB, produces `type: "Point"` with a `coordinates` array. If using planar coordinates, you can declare `@GeoSpatialIndexed(type = GeoSpatialIndexType.GEO_2D)` on the corresponding property while ensuring the stored MongoDB data type is compatible with `2d`.

**Note on index creation:** The annotation describes the index, but the index must actually exist in MongoDB. In modern Spring Data MongoDB versions, automatic index creation is not enabled by default. In development, you can configure Spring Boot:

```yaml
spring:
  data:
    mongodb:
      auto-index-creation: true
```

For production systems, manage index creation via migrations or controlled deployment workflows. If you want to create it explicitly with `MongoTemplate`:

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.GeospatialIndex;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;

// mongoTemplate is an injected MongoTemplate bean.
mongoTemplate.indexOps(Place.class).ensureIndex(
    new GeospatialIndex("location")
        .typed(GeoSpatialIndexType.GEO_2DSPHERE)
);
```

Choose an index management mechanism that fits your application and confirm the result with `db.places.getIndexes()`. If the schema already has an index on the same field with a different type or different options, resolve the conflict in your migration.

## 5. Queries Using `2dsphere`

### 5.1. Finding Points Near a Location

With GeoJSON and `2dsphere`, `$near` accepts a `Point` as `$geometry`; `$maxDistance` and `$minDistance` are expressed in **meters**:

```javascript
db.places.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      $minDistance: 0,
      $maxDistance: 2000
    }
  }
}).limit(10);
```

The query above retrieves up to 10 points within roughly 2 km of the center and returns results ordered by ascending distance. The `$near` operator requires a suitable geospatial index; without one, the query will error. When you want to compute and return the measured distance as well, you can use `$geoNear` aggregation (see the performance section).

Spring Data MongoDB repositories support queries derived from the `Near` method keyword:

```java
import java.util.List;
import org.springframework.data.geo.Distance;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface PlaceRepository extends MongoRepository<Place, String> {
    List<Place> findByLocationNear(GeoJsonPoint center, Distance maxDistance);
}
```

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;

GeoJsonPoint center = new GeoJsonPoint(106.7000, 10.7800);
List<Place> nearby = placeRepository.findByLocationNear(
    center, new Distance(2, Metrics.KILOMETERS)
);
```

`Distance` with `Metrics.KILOMETERS` makes the unit explicit at the call site; Spring Data converts it according to the generated geospatial query semantics. Use consistent coordinate types across entity properties, query parameters, and indexes, and verify generated queries when upgrading framework versions.

### 5.2. Filtering Points Inside a Polygon

`$geoWithin` returns points or geometries contained within the specified region. The polygon below is just a sample rectangular area; the first and last elements repeat to close the ring:

```javascript
db.places.find({
  location: {
    $geoWithin: {
      $geometry: {
        type: "Polygon",
        coordinates: [[
          [106.6800, 10.7600],
          [106.7300, 10.7600],
          [106.7300, 10.8100],
          [106.6800, 10.8100],
          [106.6800, 10.7600]
        ]]
      }
    }
  }
});
```

Unlike `$near`, `$geoWithin` does not sort results by distance. Containment queries can execute without an index, but usually need an index to perform well on large datasets. For lines, regions, or polygons, `$geoIntersects` is the choice for "do two shapes intersect?". Area and intersection operations on Earth should use `2dsphere` with GeoJSON.

### 5.3. Computing Distances with `MongoTemplate`

When the application needs both the entity and the distance to the center, `MongoTemplate.geoNear` returns `GeoResults<Place>`:

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.NearQuery;

NearQuery query = NearQuery
    .near(new GeoJsonPoint(106.7000, 10.7800))
    .maxDistance(new Distance(2, Metrics.KILOMETERS))
    .spherical(true);

GeoResults<Place> results = mongoTemplate.geoNear(query, Place.class);
for (GeoResult<Place> result : results) {
    System.out.println(result.getContent().getName()
        + ": " + result.getDistance());
}
```

This is an example using an injected `MongoTemplate`. `GeoResults` provides `getDistance()` according to Spring Data's query unit rules; before displaying the number to users, check the unit in the `Distance` object and convert/format explicitly.

## 6. Queries Using `2d` on a Flat Plane

With `flat_points` having a `position: "2d"` index, MongoDB can find racks near `[10, 20]` within a radius of 5 **floor-plan units**:

```javascript
db.flat_points.find({
  position: {
    $near: [10, 20],
    $maxDistance: 5
  }
});
```

The distance in this example is calculated from `[x, y]` pairs using Euclidean geometry. If the floor plan defines one unit as one meter, the radius is 5 meters; if it is in pixels, the result radius is 5 pixels. Never interpret it as "5 km on a map" when the data lacks a corresponding projection conversion.

To find points inside a planar rectangle:

```javascript
db.flat_points.find({
  position: {
    $geoWithin: {
      $box: [[0, 0], [20, 30]]
    }
  }
});
```

`$box` suits planar filtering with legacy coordinates. When business requirements move to distances on Earth, migrate the model and index to GeoJSON/`2dsphere` instead of just swapping the query operator.

## 7. Checking Performance with `explain()`

Suppose the application searches for up to 10 cafes within 2 km. The `$geoNear` aggregation stage must appear at the **start of the pipeline** and can combine attribute filters:

```javascript
db.places.explain("executionStats").aggregate([
  {
    $geoNear: {
      near: { type: "Point", coordinates: [106.7000, 10.7800] },
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 2000,
      spherical: true,
      query: { category: "cafe" }
    }
  },
  { $limit: 10 }
]);
```

With GeoJSON, `distanceMeters` expresses distance in meters unless `distanceMultiplier` is set to convert units. In the execution plan, focus on the chosen index, the number of keys and documents examined (`totalKeysExamined`, `totalDocsExamined`), the number of documents returned (`nReturned`), and execution time. Stage names may differ across MongoDB versions; inspect the actual index used rather than relying on one fixed stage name.

Several optimization practices are generally helpful:

- Apply selective business filters (`category`, active status, tenant) and test corresponding compound indexes; measure again against realistic data distributions.
- Limit the number of results when a screen only needs the closest locations; project only needed fields, especially when documents carry large payloads.
- Avoid sorting by another field after `$near` unless required by business logic: `$near` already orders by distance; an extra sort adds cost.
- Validate geometry on write, and update data and indexes when the model evolves; avoid fetching all spatial data into the application to compute distances manually.

## 8. Common Errors and Diagnostics

| Symptom | Common Cause | How to Check and Fix |
| --- | --- | --- |
| Expected nearby locations not found | Swapped latitude/longitude, out-of-range data, wrong coordinate system | Verify `[longitude, latitude]`, inspect raw document, and run a sample query with known points |
| `$near` reports missing geospatial index | Index not created or created on a different field | Run `db.places.getIndexes()`; verify exact field path and index type |
| 2 km query returns a wildly different range | Mixed meters, km, radians, or planar units | Distinguish GeoJSON/legacy; in Java use `Distance` and `Metrics` consistently |
| Index creation fails | Malformed GeoJSON, invalid lon/lat, wrong value type, coordinates outside `2d` bounds | Inspect failing documents and validate schema before rebuilding the index |
| Document exists in collection but not in `2dsphere` index | Location field missing, `null`, or empty; geospatial indexes are sparse | Inspect `location`, fix data, or define a clear policy for unlocated places |
| Query slow when filtering additional attributes | Index does not match actual conditions, result set too broad | Read `executionStats`, test compound indexes, and benchmark on representative workloads |

Additionally, test points near polygon boundaries, the International Date Line, and very large regions separately: spherical geometry follows inclusion rules that differ from planar intuition. For real-world polygons, normalize vertex order, closed rings, and representation rules before persisting.

## 9. Self-Check Practice Exercises

1. Create the `places` collection with the three GeoJSON documents in section 2 and the `location_2dsphere` index in section 3.
2. Run `$near` centered at `[106.7000, 10.7800]` with a `2000`-meter radius. Expect `p1` and `p2` to be nearby while `p3` is out of range; verify distance ordering.
3. Run `$geoWithin` for the polygon in section 5 and compare its results with `$near`: a geographic polygon and a circular radius are two different conditions.
4. Create `flat_points` and `position_2d`; test `$near` at `[10, 20]` with radius `5` units. Explain why you cannot arbitrarily call that "5 km".
5. Use `db.places.getIndexes()` and `explain("executionStats")` to inspect the index used by a `$geoNear` query; change the `category` filter and compare execution plans.

**Remember:** `2d` serves planar coordinates, while `2dsphere` serves spherical geographic calculations. In Spring Data MongoDB, the data model (`GeoJsonPoint`), actual MongoDB annotations/indexes, query operators, and measurement units must all align for both results and performance to be trustworthy.
