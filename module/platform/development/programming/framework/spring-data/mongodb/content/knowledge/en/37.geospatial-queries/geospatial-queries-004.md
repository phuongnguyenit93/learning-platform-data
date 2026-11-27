# Near, Within, and Geospatial Query Operators

## 1. Problem Statement and Goals

An application using **Spring Data MongoDB** wants to look up active pickup points based on a customer's location. Questions that look similar have very different semantics:

1. **Which points are closest to me?** Requires distance-ordered results: `$near` or `$nearSphere`.
2. **Which points lie within a 2 km radius?** Only needs region filtering: `$geoWithin` with `$centerSphere`.
3. **Which points lie within a district described by a Polygon?** `$geoWithin` with `$geometry`.
4. **Which delivery routes cross a warning zone?** `$geoIntersects`.
5. **Want to return the calculated distance for each location as well?** Use `$geoNear` aggregation or Spring Data `NearQuery`/`GeoResult`.

Mixing up these operations can cause the application to return the wrong order, wrong distances, scan too much data, or fail due to missing geospatial indexes.

In this lesson, we practice **MongoDB query operators**, **`MongoTemplate`/`Criteria`**, **repository derived queries**, **reactive access** considerations, indexes, transactions, testing, and performance analysis. This lesson is part of the **Geospatial Queries** chapter of Spring Data MongoDB.

### Learning Objectives

After this lesson, you will be able to:

- Distinguish GeoJSON from legacy coordinate pairs, `2dsphere` from `2d`, and **longitude–latitude** order.
- Choose `$near`/`$nearSphere` when you need **proximity + ordering**, and `$geoWithin` when you need **region filtering**.
- Use `$box`, `$center`, `$centerSphere`, GeoJSON Polygon, and `$geoIntersects` with accurate semantics.
- Write `Criteria.near(...)`, `nearSphere(...)`, `within(...)`, `withinSphere(...)`, `intersects(...)`, and corresponding repository methods.
- Understand **meters, degrees, and radians**, boundary issues, indexes/`explain`, `countDocuments`, and `$geoNear`.
- Test against a real MongoDB instance instead of guessing results from coordinates by eye.

## 2. Data Standards: GeoJSON, Longitude/Latitude, and Legacy Pairs

### 2.1. GeoJSON Point

In MongoDB, a geographic point is typically represented as:

```javascript
{
  location: {
    type: "Point",
    coordinates: [106.7000, 10.8000]
  }
}
```

**Mandatory order: `[longitude, latitude]` — longitude first, latitude second.** This is the order GeoJSON/MongoDB uses; many UIs and mapping libraries represent `(latitude, longitude)`, making this a very common source of bugs.

In the examples, coordinates are **synthetic data for illustration** and do not represent a real business or pickup point. Valid ranges for standard WGS84 geographic coordinates:

| Property | Meaning | Value Range |
| --- | --- | --- |
| Longitude / x | Longitude, West negative, East positive | From -180 to +180 degrees |
| Latitude / y | Latitude, South negative, North positive | From -90 to +90 degrees |
| `coordinates` | In a GeoJSON Point | `[longitude, latitude]` |
| Stored dimension | Angular degrees on the globe | **Not meters** |

For instance, a frontend API often sends `lat = 10.8` and `lng = 106.7`. When building a `GeoJsonPoint`, call `new GeoJsonPoint(lng, lat)`; never swap them because a variable is named `x`/`y`.

### 2.2. Legacy Coordinates

MongoDB also supports legacy arrays:

```javascript
{ location: [106.7000, 10.8000] }
```

This is **not GeoJSON**. A Spring Data `Point` is a basic coordinate geometry type; `GeoJsonPoint` represents a GeoJSON structure with `type: "Point"` and `coordinates`. These two types can cause MongoDB to generate different query expressions and interpret distances **in different units**.

| Criterion | GeoJSON Point | Legacy Pair |
| --- | --- | --- |
| Sample BSON | `{type:"Point", coordinates:[x,y]}` | `[x,y]` |
| Common Java type | `GeoJsonPoint` | `Point` |
| Typical index | `2dsphere` | `2d` for planar; `2dsphere` also supports some legacy forms |
| Geometry | Spherical / Earth | Planar or spherical depending on operator/index |
| Distance with `$near` | Typically **meters** | Depends on operator/index; not meters by default |

**Do not arbitrarily mix** legacy points and GeoJSON objects in the same field when the API requires consistent unit conversion. When migrating old data, inspect each BSON type, index, and actual operator.

### 2.3. GeoJSON Polygon and Other Geometry Types

A Polygon is constructed from one or more **linear rings**. The first and last coordinates of each ring must match:

```javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.69, 10.79],
      [106.72, 10.79],
      [106.72, 10.82],
      [106.69, 10.82],
      [106.69, 10.79]
    ]
  ]
}
```

The first ring represents the exterior boundary; subsequent rings can be holes per the GeoJSON standard. You must validate polygon validity, ring orientation/winding, self-intersection, polygons crossing the ±180° meridian, and large-area cases. A visual "rectangle" may not follow geodesic boundaries on a sphere.

Types such as `MultiPoint`, `LineString`, `MultiLineString`, `MultiPolygon`, and `GeometryCollection` can also be involved in queries, though operator/index support and edge cases should be checked against your MongoDB release.

## 3. Choosing an Index: `2dsphere` and `2d` Are Not Equivalent

### 3.1. Creating Isolated Demo Data

Create an illustrative database **containing no important data**:

```javascript
use geospatial_training

db.pickup_points.insertMany([
  {
    _id: "P-001",
    tenant_id: "TENANT-A",
    name: "Point A",
    active: true,
    location: {
      type: "Point",
      coordinates: [106.7000, 10.8000]
    }
  },
  {
    _id: "P-002",
    tenant_id: "TENANT-A",
    name: "Point B",
    active: true,
    location: {
      type: "Point",
      coordinates: [106.7050, 10.8050]
    }
  },
  {
    _id: "P-003",
    tenant_id: "TENANT-A",
    name: "Point C",
    active: false,
    location: {
      type: "Point",
      coordinates: [106.7300, 10.8300]
    }
  },
  {
    _id: "P-004",
    tenant_id: "TENANT-B",
    name: "Point D",
    active: true,
    location: {
      type: "Point",
      coordinates: [106.7010, 10.8010]
    }
  }
])
```

`insertMany` is a one-time seed; re-running it with the same `_id` triggers a duplicate key error. Test suites must clean up data in an **isolated** database—never run full-wipe commands against production.

### 3.2. GeoJSON Index

```javascript
db.pickup_points.createIndex(
  { location: "2dsphere" },
  { name: "pickup_location_2dsphere" }
)

db.pickup_points.getIndexes()
```

`2dsphere` is designed for data on Earth and is the natural choice for GeoJSON Point/Polygon. An appropriate geospatial index is required for `$near`/`$nearSphere` and `$geoNear`. `$geoWithin` can in some cases **run without an index** but is usually much slower on large datasets; `$geoIntersects` requires checking `2dsphere` requirements for the geometry/index used.

`2d` is a separate index type for coordinates on a **flat plane**. Do not add `2d` to a GeoJSON field just because a query is slow; verify the data model and geometry type first.

### 3.3. Compound Indexes and Tenant Filtering

Real-world queries typically include:

```javascript
{
  tenant_id: "TENANT-A",
  active: true,
  location: { /* geospatial clause */ }
}
```

You may consider an index combining scalar and geographic fields, such as:

```javascript
db.pickup_points.createIndex(
  { tenant_id: 1, active: 1, location: "2dsphere" },
  { name: "pickup_tenant_active_geo" }
)
```

However, **do not** assume a compound index is always faster than `{location:"2dsphere"}`. Effectiveness depends on tenant cardinality, point density, query radius, selectivity, and execution plan; measure `explain("executionStats")` on representative data. On a sharded cluster, you must also evaluate the shard key, data partitioning, and routing. Never use geospatial queries to read across tenants or expect an index to enforce authorization.

### 3.4. Spring Data Annotations Are Only Definitions

`@GeoSpatialIndexed` can declare an index on an entity, but **does not guarantee the index is automatically created in production MongoDB**. Spring Data MongoDB provides configurable index creation and the `IndexOperations` API; run migrations and verify actual indexes before serving traffic:

```javascript
db.pickup_points.getIndexes()
```

Without an index, `$near` will throw an error instead of returning results and optimizing later. Do not handle this error by catching the exception and **dropping the location filter**.

## 4. Operator Selection Table by Intent

| MongoDB Operator | Meaning | Sorted Nearest → Farthest? | Index / Scenario |
| --- | --- | --- | --- |
| `$near` | Geometries near a point; shortest distance first | **Yes** | Requires geospatial index; for GeoJSON use `2dsphere` |
| `$nearSphere` | Geometries near a point using spherical geometry | **Yes** | Requires geospatial index; explicit spherical distance |
| `$geoWithin` + `$centerSphere` | Inside a circle on a sphere | **No** | Radius in **radians**; `2dsphere` helpful |
| `$geoWithin` + `$geometry` | Inside a GeoJSON geometry (e.g., Polygon) | **No** | Typically uses `2dsphere` |
| `$geoWithin` + `$box` | Inside a planar coordinate box | **No** | For legacy planar/`2d` problems |
| `$geoWithin` + `$center` | Inside a planar circle | **No** | Radius in **coordinate units** |
| `$geoWithin` + `$polygon` | Inside a legacy planar polygon | **No** | Not a GeoJSON Polygon |
| `$geoIntersects` + `$geometry` | Geometries intersecting/touching a region geometry | **No** | Use when intersection rather than full containment is needed |
| `$geoNear` aggregation | Nearest items with a **distance** field in a pipeline | **Yes** | Geospatial index, stage ordering restrictions |

**Decision examples:**

- "Ten closest points, ordered" → `$near` or `$geoNear` followed by `limit`.
- "Count points within a 2 km radius" → `$geoWithin: {$centerSphere: ...}`; do not use `$near` inside `countDocuments`.
- "Filter points inside a delivery zone, sorted by name" → `$geoWithin` + `sort({name:1})`.
- "Check if a route (LineString) crosses a restricted zone" → `$geoIntersects`.

## 5. `$near`: Filtering by Distance **and** Returning Ranked Results

### 5.1. Direct GeoJSON Query

Find points within 2,000 meters around `[106.7,10.8]`, scoped to tenant A and active:

```javascript
db.pickup_points.find({
  tenant_id: "TENANT-A",
  active: true,
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.8000]
      },
      $maxDistance: 2000
    }
  }
}).limit(10)
```

With a GeoJSON Point and `2dsphere` index, `$maxDistance: 2000` means **2,000 meters**, not 2,000 degrees. Results are sorted from nearest to farthest. `limit(10)` takes at most ten matching points.

To search an annulus from 500 to 2,000 meters:

```javascript
db.pickup_points.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.8000]
      },
      $minDistance: 500,
      $maxDistance: 2000
    }
  }
})
```

This is an illustrative query **based solely on distance**; in a multi-tenant API you must add tenant/authorization filters before returning data.

### 5.2. `$near` Already Sorts; Adding `sort` Can Change Meaning

```javascript
// NO LONGER guarantees nearest-first once re-sorted by name:
db.pickup_points.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7, 10.8]
      },
      $maxDistance: 2000
    }
  }
}).sort({ name: 1 })
```

MongoDB performs an extra sort by name. That consumes extra resources and breaks nearest-first ordering. If you need deterministic tie-breaking by ID or multiple criteria, define an explicit ranking contract and consider `$geoNear` + an appropriate pipeline `$sort` after distance is computed.

### 5.3. `$near` Does Not Fit Every Query

A `$near` geospatial query is a predicate with specific semantics:

- Requires a geospatial index. Missing indexes normally cause an error.
- Cannot be combined with queries requiring another special index such as `$text`.
- An `$or` containing `$near`/`$nearSphere` cannot include other branches (cannot be used for "near OR featured").
- In aggregation, do not place `$near` inside `$match`; use the `$geoNear` stage.
- When you only need region filtering **without caring about distance order**, `$geoWithin` usually matches the requirement better and avoids distance-sorting overhead.

Starting in MongoDB 8.0, `$near`, `$nearSphere`, and `$geoNear` enforce that the query GeoJSON geometry must be a **Point**. Do not send a Polygon as the `$near` center, even if older client code accepted that payload.

## 6. `$nearSphere`: Explicitly Choosing Spherical Distance

`$nearSphere` requests spherical distance and also returns results **nearest to farthest**. When storing and querying **GeoJSON Point + `2dsphere`**, `$near` and `$nearSphere` behave equivalently for proximity search, but `$nearSphere` states spherical intent explicitly:

```javascript
db.pickup_points.find({
  tenant_id: "TENANT-A",
  active: true,
  location: {
    $nearSphere: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.8000]
      },
      $minDistance: 300,
      $maxDistance: 2000
    }
  }
}).limit(10)
```

With GeoJSON `$geometry`, `$minDistance`/`$maxDistance` are measured in **meters**. With **legacy coordinate pairs**, the same operator name can interpret limit values in **radians**. Determine the actual query argument type generated by Spring Data rather than relying solely on the Java method name.

### 6.1. Do Not Infer Distance from Result Order Without a Distance Field

`find(...)` using `$nearSphere` returns documents nearest-first, but does not automatically include a computed `distanceMeters` field in the response. If the API needs to display "450 m", use **`$geoNear` aggregation**, Spring Data `NearQuery`/`GeoResult`, or an explicitly defined distance calculation step.

Never use the document's `index` in the result list to guess a distance; ordering only reflects relative closeness per the operator.

### 6.2. Spherical Distance Is Not Real Travel Route Distance

Spherical geographic distance is **not** road travel distance, driving time, or detours around rivers/bridges. An API recommending pickup points should make clear that `distanceMeters` is **geodesic/geospatial distance**, not ETA. If real ETA/routes are needed, use a dedicated routing system.

## 7. `$geoWithin`: Selecting Points in a Region, **Without** Proximity Sorting

`$geoWithin` is a predicate selecting geometries inside a shape. It does not output distances or rank by proximity to an origin; it can combine `tenant_id`/`active` filters and `sort` by **business attributes**.

### 7.1. Spherical Circle: `$centerSphere`

To find points within 2 km of `[106.7,10.8]`:

```javascript
const earthRadiusKm = 6378.137; // approximate WGS84 equatorial radius
const radiusKm = 2;
const radiusRadians = radiusKm / earthRadiusKm;

db.pickup_points.find({
  tenant_id: "TENANT-A",
  active: true,
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.7000, 10.8000],
        radiusRadians
      ]
    }
  }
}).sort({ name: 1 })
```

**The unit of `radiusRadians` here is radians**. If you write `$centerSphere: [[lng, lat], 2000]`, MongoDB **will not treat it as 2,000 meters**. Converting from meters to radians:

\[
r_{\mathrm{rad}} = \frac{d_{\mathrm{m}}}{R_{\mathrm{m}}}
\]

With `R ≈ 6,378,137 m`, 2,000 m corresponds to roughly `0.00031357 rad`. A "spherical Earth" reference is an approximation; do not use this precision for legal boundaries or centimeter-level surveying.

### 7.2. Planar Box: `$box`

`$box` specifies two corners of a box:

```javascript
db.legacy_locations.find({
  location: {
    $geoWithin: {
      $box: [
        [106.68, 10.78],
        [106.72, 10.83]
      ]
    }
  }
})
```

This example assumes collection `legacy_locations` holds **legacy coordinate pairs** with suitable `2d`/planar setup. `$box` does not take a radius in meters; it describes **planar geometry in the data's coordinate system**, so using it to draw a "2 km square" in lon/lat without accounting for distortion can introduce errors.

### 7.3. Planar Circle: `$center`

```javascript
db.legacy_locations.find({
  location: {
    $geoWithin: {
      $center: [
        [106.7000, 10.8000],
        0.01
      ]
    }
  }
})
```

Here the radius `0.01` is in **planar coordinate units** (if the inputs are longitude/latitude, that means angular degrees), not 0.01 km or 10 m. For area problems on Earth, `$centerSphere` and `2dsphere` are usually clearer.

### 7.4. Legacy Planar Polygon: `$polygon`

```javascript
db.legacy_locations.find({
  location: {
    $geoWithin: {
      $polygon: [
        [106.69, 10.79],
        [106.72, 10.79],
        [106.72, 10.82],
        [106.69, 10.82]
      ]
    }
  }
})
```

This is a legacy planar region operator, **not** identical to a GeoJSON Polygon using `$geometry`. For real geographic regions using GeoJSON and `2dsphere`, prefer `$geometry`.

### 7.5. GeoJSON Polygon with `$geometry`

```javascript
const deliveryZone = {
  type: "Polygon",
  coordinates: [[
    [106.69, 10.79],
    [106.72, 10.79],
    [106.72, 10.82],
    [106.69, 10.82],
    [106.69, 10.79]
  ]]
};

db.pickup_points.find({
  tenant_id: "TENANT-A",
  active: true,
  location: {
    $geoWithin: {
      $geometry: deliveryZone
    }
  }
})
```

MongoDB evaluates the region geometry and returns points inside the polygon. **There is no distance ordering**; if the UI needs ordering, `sort` by a field (such as name/priority) or run a separate distance-calculating pipeline.

### 7.6. Testing Region Boundaries and Tricky Polygons

Cases requiring dedicated tests:

- Points **lying right on the boundary** or near it within floating-point tolerance.
- Polygons with holes, multiple rings, or `MultiPolygon`.
- Self-intersecting polygons, unclosed rings, winding direction, and regions covering large portions of the globe.
- Regions crossing the 180° meridian (antimeridian), near the poles, or across the Prime Meridian.
- Coordinate systems other than WGS84 longitude/latitude (e.g., internal projected systems in meters).

Do not assume "on-boundary is handled just like Euclidean geometry" for all `2dsphere` queries: MongoDB has its own geometric rules and limitations, including **not guaranteeing consistent results right on geometric boundaries** in certain cases. If boundaries affect money, legal compliance, or delivery zoning, establish fallback business rules (buffers, tolerances, tie-breakers) and test with real data.

## 8. `$geoIntersects`: Intersection Differs from Full Containment

For a point, checking membership inside a polygon can be expressed with `$geoWithin`. However, for routes, regions, or extended geometries, **intersecting** and **lying completely inside** are two different conditions:

- `$geoWithin`: the document's geometry **lies completely inside** the query region.
- `$geoIntersects`: the geometry **intersects or touches** the query region under MongoDB's supported spatial math.

Example storing a route:

```javascript
db.delivery_routes.insertOne({
  _id: "ROUTE-001",
  tenant_id: "TENANT-A",
  path: {
    type: "LineString",
    coordinates: [
      [106.68, 10.80],
      [106.70, 10.80],
      [106.73, 10.80]
    ]
  }
})

db.delivery_routes.createIndex(
  { path: "2dsphere" },
  { name: "route_path_geo" }
)
```

Finding routes **crossing through** a warning zone:

```javascript
db.delivery_routes.find({
  tenant_id: "TENANT-A",
  path: {
    $geoIntersects: {
      $geometry: {
        type: "Polygon",
        coordinates: [[
          [106.69, 10.79],
          [106.72, 10.79],
          [106.72, 10.82],
          [106.69, 10.82],
          [106.69, 10.79]
        ]]
      }
    }
  }
})
```

The route above starts outside the region, passes through it, and exits. It **does not lie completely inside** the polygon, yet it intersects it. This is a job for `$geoIntersects`, not `$geoWithin`.

## 9. Spring Data MongoDB: Java Mapping and `Criteria`

### 9.1. GeoJSON Point Entity

```java
package com.example.geo;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexed;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "pickup_points")
public class PickupPoint {

    @Id
    private String id;

    @Field("tenant_id")
    private String tenantId;

    private String name;
    private boolean active;

    @GeoSpatialIndexed(type = GeoSpatialIndexType.GEO_2DSPHERE)
    private GeoJsonPoint location;

    protected PickupPoint() {}

    public PickupPoint(
            String id, String tenantId, String name,
            boolean active, GeoJsonPoint location) {
        this.id = id;
        this.tenantId = tenantId;
        this.name = name;
        this.active = active;
        this.location = location;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getName() { return name; }
    public boolean isActive() { return active; }
    public GeoJsonPoint getLocation() { return location; }
}
```

`new GeoJsonPoint(106.70, 10.80)` produces a GeoJSON Point where `x = longitude`, `y = latitude`. The `@GeoSpatialIndexed` annotation describes the required index but **does not replace migrations**; verify the database has the index before running the application.

### 9.2. Template with `Criteria.nearSphere`

```java
package com.example.geo;

import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class PickupSearchService {

    private final MongoTemplate template;

    public PickupSearchService(MongoTemplate template) {
        this.template = template;
    }

    public List<PickupPoint> nearest(
            String authorizedTenantId,
            double longitude, double latitude,
            double maxDistanceMeters, int limit) {

        validate(authorizedTenantId, longitude, latitude,
            maxDistanceMeters, limit);

        Query query = Query.query(
            Criteria.where("tenantId").is(authorizedTenantId)
                .and("active").is(true)
                .and("location")
                    .nearSphere(new GeoJsonPoint(longitude, latitude))
                    .maxDistance(maxDistanceMeters)
        );

        query.limit(limit);
        return template.find(query, PickupPoint.class);
    }

    private static void validate(
            String tenantId, double lng, double lat,
            double meters, int limit) {
        if (tenantId == null || tenantId.isBlank()
                || !Double.isFinite(lng)
                || !Double.isFinite(lat)
                || lng < -180 || lng > 180
                || lat < -90 || lat > 90
                || !Double.isFinite(meters)
                || meters < 0 || meters > 50000
                || limit < 1 || limit > 100) {
            throw new IllegalArgumentException(
                "Invalid geospatial parameter");
        }
    }
}
```

`Criteria.nearSphere(...)` builds a `$nearSphere` condition. With `GeoJsonPoint` and `2dsphere`, the distance limit uses **meters** in the GeoJSON query. `MongoTemplate` uses `PickupPoint` mapping metadata to translate property `tenantId` to BSON `tenant_id`.

**Authorization must still be enforced by the service/authorization layer.** Do not accept `authorizedTenantId` from an arbitrary query parameter; obtain it from the authenticated identity. If an index is missing, fix the migration/index rather than silently falling back to a query without a location filter.

### 9.3. Template with `Criteria.withinSphere`

Spring Data's `Circle` takes a center `Point` and a `double` radius. When using `withinSphere` to generate `$centerSphere`, **the radius must be in radians**:

```java
import java.util.List;
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

double radiusMeters = 2000.0;
double radiusRadians = radiusMeters / 6_378_137.0;

Circle area = new Circle(
    new Point(106.7000, 10.8000), radiusRadians);

Query withinQuery = Query.query(
    Criteria.where("tenantId").is(authorizedTenantId)
        .and("active").is(true)
        .and("location").withinSphere(area)
);

List<PickupPoint> points =
    mongoTemplate.find(withinQuery, PickupPoint.class);
```

`mongoTemplate`/`authorizedTenantId` are variables available in the service. `withinSphere` **does not sort by distance**. If you need ordering by name, add `withinQuery.with(Sort.by("name"))`; if you need proximity ranking, choose `nearSphere`/`$geoNear`.

### 9.4. Template with `within(Box)` and `within(GeoJsonPolygon)`

`Criteria.within(...)` accepts a `Shape`:

```java
import org.springframework.data.geo.Box;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.geo.GeoJsonPolygon;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Box box = new Box(
    new Point(106.68, 10.78),
    new Point(106.72, 10.83)
);
Query legacyPlanar = Query.query(
    Criteria.where("location").within(box)
);

GeoJsonPolygon zone = new GeoJsonPolygon(
    new Point(106.69, 10.79),
    new Point(106.72, 10.79),
    new Point(106.72, 10.82),
    new Point(106.69, 10.82),
    new Point(106.69, 10.79)
);

Query withinGeoJson = Query.query(
    Criteria.where("location").within(zone)
);
```

**Do not equate the two queries**: `Box` represents a legacy planar region; `GeoJsonPolygon` maps to GeoJSON `$geoWithin/$geometry`. In a multi-tenant service, add `tenantId`/`active` and validation; these snippets only illustrate the API.

### 9.5. Template with `Criteria.intersects`

When storing route or region geometries, you can use:

```java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query crossing = Query.query(
    Criteria.where("path").intersects(zone)
);
```

`zone` is the `GeoJsonPolygon` from the example above; this query uses `$geoIntersects`. The `delivery_routes` collection must have an appropriate `path` field and a geospatial index. `PickupPoint` does not have a `path` field, so do not run this query with `PickupPoint.class` expecting to find routes.

## 10. Repository Derived Queries: `Near` and `Within`

Spring Data MongoDB supports `Near`/`Within` keywords in repository method names:

```java
package com.example.geo;

import java.util.List;
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.geo.GeoJsonPolygon;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface PickupPointRepository
        extends MongoRepository<PickupPoint, String> {

    List<PickupPoint> findByLocationNear(
        Point center, Distance maxDistance);

    List<PickupPoint> findByLocationWithin(
        Circle circle);

    List<PickupPoint> findByLocationWithin(
        GeoJsonPolygon polygon);
}
```

Spring Data builds queries from the names `findByLocationNear`/`findByLocationWithin`. For methods taking a `Distance` with `Metrics.KILOMETERS` or `Metrics.MILES`, Spring Data can use `$nearSphere` and convert units per the metric; for GeoJSON shape types, it constructs the appropriate `$geometry` structure.

### 10.1. Calling the `Near` Method

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;

List<PickupPoint> nearby = repository.findByLocationNear(
    new GeoJsonPoint(106.7000, 10.8000),
    new Distance(2, Metrics.KILOMETERS)
);
```

`repository` is injected into a service. The query can use spherical semantics because `Distance` carries a `Metric`. **Do not override the unit contract** by assuming `new Distance(2)` always means 2 km; if no metric is passed, the meaning of distance depends on query representation/index.

### 10.2. Calling the `Within` Method

```java
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Point;

// Circle via Within(Circle) is typically planar,
// radius is in coordinate units, NOT meters.
Circle planarCircle = new Circle(
    new Point(106.70, 10.80),
    0.01
);

List<PickupPoint> results =
    repository.findByLocationWithin(planarCircle);
```

**Important note:** `findByLocationWithin(Circle)` typically maps to `$geoWithin/$center` (planar). For a **2 km radius on Earth**, use `Criteria.withinSphere`/`$centerSphere`, or a repository method explicitly designed for spherical semantics in your Spring Data version. Never pass `new Circle(..., 2000)` thinking it means 2,000 m.

### 10.3. Methods Returning `GeoResults` and Distance

A geospatial repository finder can return `GeoResults<T>` or `GeoResult<T>` depending on API/version support:

```java
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface PickupDistancesRepository
        extends MongoRepository<PickupPoint, String> {

    GeoResults<PickupPoint> findByLocationNear(Point center);
}
```

In Spring Data MongoDB, the geonear path returns `GeoResult` containing `getContent()` and `getDistance()`; distances inside `GeoResult` must be checked against their metric. For large APIs, **enforce `maxDistance` and `limit` bounds** rather than querying all locations just to compute an average.

### 10.4. Do Not Rely on Derived Methods When Business Filters Are Complex

Repository derived methods fit simple queries. When you need tenant authorization, active status, dynamic polygons, distances, projections, or version-specific options, `MongoTemplate`/`NearQuery` is usually clearer. A `findByLocationNear(...)` method filtering only by location **does not automatically filter by tenant**; using it directly in a multi-tenant API can leak data.

## 11. `NearQuery` and `$geoNear`: When You Need a Distance Field

### 11.1. `$geoNear` Aggregation in MongoDB

`$geoNear` returns documents nearest → farthest and can add a numeric field such as `distanceMeters`:

```javascript
db.pickup_points.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.8000]
      },
      key: "location",
      distanceField: "distanceMeters",
      spherical: true,
      maxDistance: 2000,
      query: {
        tenant_id: "TENANT-A",
        active: true
      }
    }
  },
  { $limit: 10 },
  {
    $project: {
      name: 1,
      tenant_id: 1,
      distanceMeters: 1
    }
  }
])
```

With a GeoJSON Point query, distances in this stage typically have unit **meters**, unless another `distanceMultiplier` is chosen. `distanceField` is an explicit way for clients to receive the distance; some newer MongoDB versions changed whether this field is mandatory, so **keep specifying it explicitly** for compatibility.

**Stage ordering:** `$geoNear` must appear **at the beginning of the pipeline** (aside from specific version exceptions such as `$search`, which should be checked separately). Do not insert `$match` before `$geoNear` and assume the error is an index problem; use `$geoNear`'s `query` field to apply tenant/active filters. Never place `$near` inside an aggregation `$match`: it is a query match execution operator restricted in pipelines.

### 11.2. Java `NearQuery` and `MongoTemplate.geoNear`

```java
package com.example.geo;

import java.util.List;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.NearQuery;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class PickupDistanceService {

    private final MongoTemplate template;

    public PickupDistanceService(MongoTemplate template) {
        this.template = template;
    }

    public List<GeoResult<PickupPoint>> withDistance(
            String authorizedTenantId,
            double longitude, double latitude) {

        Query businessFilter = Query.query(
            Criteria.where("tenantId").is(authorizedTenantId)
                .and("active").is(true)
        );

        NearQuery near = NearQuery.near(
                new GeoJsonPoint(longitude, latitude),
                Metrics.KILOMETERS)
            .maxDistance(2)
            .query(businessFilter)
            .limit(10);

        GeoResults<PickupPoint> result =
            template.geoNear(near, PickupPoint.class);

        return result.getContent();
    }
}
```

Here `maxDistance(2)` is interpreted in `Metrics.KILOMETERS` chosen by `NearQuery`, and `getDistance().getValue()` in `GeoResult` expresses distance in the result's metric—always check the response/metric if converting to meters for display. This illustrative API omits validation to focus on `NearQuery`; a production service must validate authenticated tenant, finite/valid longitude/latitude, max radius, and result limit as in section 9.

Note: Starting in MongoDB 4.2, the legacy `geoNear` command was removed; since Spring Data MongoDB 2.2, `MongoOperations.geoNear(...)` runs via the **`$geoNear` aggregation stage** rather than sending the old `geoNear` server command. Therefore, when upgrading versions, check driver/Spring Data release notes instead of using `runCommand({geoNear: ...})` from very old docs.

### 11.3. How `$near`, `NearQuery`, and `$geoNear` Differ

| Usage | Returns | Distance Field Included? | Constraints |
| --- | --- | --- | --- |
| `find({location: {$near: ...}})` | Documents nearest → farthest | Not added automatically | Needs geo index; cannot use `$near` inside aggregation `$match` |
| `MongoTemplate.find(queryNear)` | `List<PickupPoint>` | Not added automatically | Corresponds to `$near`/`$nearSphere` |
| `MongoTemplate.geoNear(NearQuery)` | `GeoResults<PickupPoint>` | `GeoResult.getDistance()` | Backed by `$geoNear` aggregation |
| `aggregate([{$geoNear: ...}])` | Documents + distance field if configured | Yes | Stage position/index/geometry restrictions |

Only pay the cost and complexity of `$geoNear` when you truly need **proximity and returned distance values**. A list of "locations in a zone sorted by name" usually only needs `$geoWithin`.

## 12. Distance Units: Summary to Avoid Being Off by Thousands

A handy unit table:

| Form/Operator | Input Field | Unit |
| --- | --- | --- |
| GeoJSON Point `coordinates` | `[lng,lat]` | Degrees |
| GeoJSON `$near/$nearSphere` `$maxDistance` | `2000` | **Meters** |
| GeoJSON `$geoNear` `maxDistance` | `2000` | **Meters** |
| `$geoWithin/$centerSphere` | `radius` | **Radians** |
| `$geoWithin/$center` | `radius` | Planar coordinate units |
| `$geoWithin/$box` | Two corners | Planar coordinate units |
| Legacy `$nearSphere` | `maxDistance` | Typically **radians** |
| `NearQuery` with `Metrics.KILOMETERS` | `maxDistance(2)` | **Km** in Java API; Spring converts when building query |

### 12.1. Safe Unit Conversion Example

```java
public final class GeoDistanceUnits {

    private static final double EARTH_RADIUS_METERS = 6_378_137.0;

    private GeoDistanceUnits() {}

    public static double metersToRadians(double meters) {
        if (!Double.isFinite(meters) || meters < 0) {
            throw new IllegalArgumentException("Invalid meters");
        }
        return meters / EARTH_RADIUS_METERS;
    }
}
```

The radius value here is a spherical approximation, **not an exact radius** for all ellipsoid measurements. A system needing cadastral/legal accuracy or accounting for specific GPS error should use measurements/coordinate systems verified by GIS specialists.

### 12.2. The Same Number Can Have Two Very Different Meanings

```text
GeoJSON $nearSphere:
    maxDistance = 2000  => about 2 km

$geoWithin + $centerSphere:
    radius = 2000       => NOT 2 km
    radius = 2000 / 6378137.0 => about 2 km

Java NearQuery:
    near(geoPoint, Metrics.KILOMETERS).maxDistance(2)
    => intends 2 km at the Spring API, converted by the framework.
```

Never pass a `radiusKm` variable directly into `Criteria.withinSphere(new Circle(..., radiusKm))`. In that example, the radius **must be converted to radians first**.

## 13. Combining Business Conditions and Query Limitations

### 13.1. Tenant, Status, and Location

In a multi-tenant application, geospatial predicates do not replace authorization:

```javascript
db.pickup_points.find({
  tenant_id: "TENANT-A",
  active: true,
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.7, 10.8],
        2000 / 6378137.0
      ]
    }
  }
})
```

The tenant filter is determined by the **authenticated identity**; never blindly take the tenant from client JSON. To optimize multi-tenant queries, consider compound geospatial indexes and check `explain`, while still keeping the tenant filter in the query regardless of which index the optimizer picks.

### 13.2. `$or` with `$near` Has Restrictions

Do not use:

```javascript
// WRONG: $or containing a near clause alongside a regular branch.
db.pickup_points.find({
  $or: [
    {
      location: {
        $near: {
          $geometry: {
            type: "Point",
            coordinates: [106.7, 10.8]
          },
          $maxDistance: 2000
        }
      }
    },
    { featured: true }
  ]
})
```

MongoDB does not allow an `$or` to contain `$near`/`$nearSphere` alongside other clauses. If the business requirement is "nearby **or** featured points", design **two separate queries** and merge them in a controlled manner, or use `$geoWithin` to express the region condition without ranking. When merging, handle deduplication, ordering, and result limits.

`$geoWithin`/`$geoIntersects` can be combined with `$or` in appropriate cases, though every branch still needs authorization and index verification.

### 13.3. `$text` and `$near` Cannot Be Used Together

`$text` requires a text index while `$near` requires a geospatial special index. MongoDB does not allow combining these two special-index operators in the same standard query.

Instead of:

```javascript
// INVALID due to special-index restrictions:
{
  $text: { $search: "coffee" },
  location: { $near: { /* GeoJSON query */ } }
}
```

You can choose:

- Filter the region with `$geoWithin` and filter normalized keyword attributes, when expressive enough.
- Use a search engine with dedicated geospatial capabilities (such as Atlas Search with appropriate configuration/indexes) and verify semantics.
- Split into two bounded steps—"find candidates" and "sort by distance"—avoiding loading the whole collection into the application.

**Never** run multiple queries and merge them without keeping the tenant filter, thinking it is a safe "optimization".

### 13.4. Geospatial Search and Pagination

`$near`/`$geoNear` sorts by distance, but when multiple points share **equal distances** or data changes between requests, offset paging with `skip` can be unstable. For large result sets:

1. Set `maxDistance`/bounded regions to narrow candidates.
2. Apply a reasonable `limit`.
3. If deterministic ordering is needed, define a tie-breaker such as `_id` after distance.
4. When an API requires strict cursor pagination, design a comparable ordering key and filter subsequent pages on computed fields rather than relying on unbounded `skip`.
5. If results require exactly "ten nearest" and ties occur, publish the rule for handling nearly equal distances.

### 13.5. `$geoWithin` Does Not Impose an Ordering

`$geoWithin` can return documents in different index/plan orders across runs. Never assume it is nearest-first, insertion order, or ID order. Add a `sort` on indexed fields when the API needs ordering. If you want **true distance sorting**, use `$geoNear` or compute distances and sort explicitly.

## 14. `countDocuments`, `MongoTemplate.count`, and Transactions

### 14.1. Do Not Count Using `$near` in `countDocuments`

MongoDB implements `countDocuments` via aggregation, so it **disallows** `$near`/`$nearSphere` predicates inside the count filter.

Invalid example:

```javascript
// Do not use $near inside countDocuments:
db.pickup_points.countDocuments({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7, 10.8]
      },
      $maxDistance: 2000
    }
  }
})
```

If you only need "how many locations are within 2 km?", use `$geoWithin/$centerSphere`:

```javascript
db.pickup_points.countDocuments({
  tenant_id: "TENANT-A",
  active: true,
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.7, 10.8],
        2000 / 6378137.0
      ]
    }
  }
})
```

**Changing the operator changes semantics:** `$near` sorts nearest-first; `$geoWithin` does not sort. When counting within a region, sorting is unnecessary so `$geoWithin` fits the intent. If the requirement is "count the 10 nearest places", redefine the problem because "nearest" normally yields 10 whenever the entire collection has at least 10 items.

### 14.2. Spring Data `count(...)` Inside Transactions

Inside a MongoDB transaction, the legacy `count` command is disallowed because it relies on collection metadata. Spring Data MongoDB translates `MongoTemplate.count(...)` to an aggregation `$match` + `$count` when an active transaction is detected.

Therefore, **count queries containing `Criteria.near(...)`/`nearSphere(...)` must be switched** to `Criteria.within(...)` or `withinSphere(...)` accordingly:

```java
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

double radiusMeters = 2000;
Circle circle = new Circle(
    new Point(106.7, 10.8),
    radiusMeters / 6_378_137.0);

Query filter = Query.query(
    Criteria.where("tenantId").is(authorizedTenantId)
        .and("active").is(true)
        .and("location").withinSphere(circle)
);

long count = mongoTemplate.count(filter, PickupPoint.class);
```

This is a sample query suited to counting within a region. To run inside a transaction, the environment needs a replica set/sharded cluster, a transaction manager, and collections/indexes provisioned beforehand. Do not open a long multi-document transaction just to return a dashboard total when that level of consistency is unnecessary.

### 14.3. `$near` Cannot Be Used in Aggregation `$match`

`$near` is a match execution operator **disallowed inside aggregation pipelines**. Invalid:

```javascript
db.pickup_points.aggregate([
  {
    $match: {
      location: {
        $near: {
          $geometry: {
            type: "Point",
            coordinates: [106.7, 10.8]
          }
        }
      }
    }
  }
])
```

Replace it with a **`$geoNear` stage** if you need nearest-first and distances, or use `$match` with `$geoWithin` if you only need region filtering. With MongoDB transactions, verify the specific stage/operation and server version before opening a transaction for geospatial search; do not assume every aggregation is allowed on every topology.

## 15. Reactive MongoDB: `ReactiveMongoTemplate` and Reactive Repositories

Spring Data MongoDB offers the same set of geospatial predicates for `ReactiveMongoTemplate`; `find` returns `Flux<PickupPoint>` instead of `List<PickupPoint>`.

### 15.1. Reactive Service Filtering a Region

```java
package com.example.geo;

import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class ReactivePickupSearchService {

    private final ReactiveMongoTemplate template;

    public ReactivePickupSearchService(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Flux<PickupPoint> withinMeters(
            String authorizedTenantId,
            double longitude, double latitude,
            double radiusMeters) {

        if (authorizedTenantId == null
                || authorizedTenantId.isBlank()
                || !Double.isFinite(longitude)
                || !Double.isFinite(latitude)
                || longitude < -180 || longitude > 180
                || latitude < -90 || latitude > 90
                || !Double.isFinite(radiusMeters)
                || radiusMeters < 0 || radiusMeters > 50000) {
            return Flux.error(
                new IllegalArgumentException("Invalid search region"));
        }

        Circle circle = new Circle(
            new Point(longitude, latitude),
            radiusMeters / 6_378_137.0);

        Query query = Query.query(
            Criteria.where("tenantId").is(authorizedTenantId)
                .and("active").is(true)
                .and("location").withinSphere(circle)
        );

        query.limit(100);
        return template.find(query, PickupPoint.class);
    }
}
```

`Flux` is a publisher; the MongoDB query typically executes only upon subscription. Never call `.block()`/`.collectList().block()` in a WebFlux handler just to "return to the controller". If a DTO list is needed, use `collectList()` and return `Mono<List<...>>` at the API boundary, remaining non-blocking.

### 15.2. Reactive Repository `Within`

```java
package com.example.geo;

import org.springframework.data.geo.Circle;
import org.springframework.data.mongodb.core.geo.GeoJsonPolygon;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactivePickupRepository
        extends ReactiveMongoRepository<PickupPoint, String> {

    Flux<PickupPoint> findByLocationWithin(Circle area);

    Flux<PickupPoint> findByLocationWithin(
        GeoJsonPolygon polygon);
}
```

For reactive geospatial repositories, result wrappers `GeoPage`/`GeoResults` are generally unsupported because precomputing average distance and total count conflicts with deferred results. `Flux<PickupPoint>` or `Flux<GeoResult<PickupPoint>>` can work depending on the method/API version. When explicit distances are needed, use `ReactiveMongoTemplate` with `NearQuery`/`geoNear` for a clear contract rather than forcing `Mono<GeoResults<T>>` onto a reactive repository.

### 15.3. Reactive Transactions Do Not Change Geospatial Query Semantics

`ReactiveMongoTransactionManager` binds the session to the Reactor Context for operations in the same transaction, but **does not make `$near` legal inside aggregation `$match`** and does not alter `countDocuments` restrictions. For pure location lookups, multi-document transactions are rarely needed; when a flow must read locations and update a business resource, verify the update condition via a **conditional query/CAS** instead of trusting that the nearest result from a previous request is still valid.

## 16. Performance Tuning: Indexes, `explain`, and Bounding Radius

### 16.1. Why Can Proximity Search Be Slow?

A `$near` query may have to traverse multiple index regions to gather enough points and guarantee distance order. Without a `maxDistance` cap, scanning nearest → farthest across an entire dataset can consume massive time and resources.

Principles:

1. Set a **reasonable business radius**, e.g., 2–10 km for urban pickup points, rather than scanning the entire cluster.
2. Set a `limit` when the UI only renders top N.
3. Ensure a **`2dsphere` index** exists on the exact BSON path.
4. Combine proper tenant/active filters and evaluate compound indexes based on measurements.
5. Only request distance calculations when the API truly needs them.
6. Avoid attaching another `sort` to `$near` if you want to keep nearest-first ranking.
7. Never fetch all results and filter tenant/active in Java; filter in MongoDB.

### 16.2. Inspecting `explain("executionStats")` Outside Transactions

```javascript
db.pickup_points.find({
  tenant_id: "TENANT-A",
  active: true,
  location: {
    $nearSphere: {
      $geometry: {
        type: "Point",
        coordinates: [106.7, 10.8]
      },
      $maxDistance: 2000
    }
  }
}).limit(10).explain("executionStats")
```

Fields/stages to inspect depend on server/version/engine:

| Component | How to Read |
| --- | --- |
| `winningPlan` | Which execution path the planner chose |
| `GEO_NEAR_2DSPHERE` or equivalent geo stage | Indicator that a geo index/near plan was used |
| `IXSCAN`, `FETCH`, `COLLSCAN` | Index lookup, document fetch, or collection scan |
| `totalKeysExamined` | Number of index entries examined |
| `totalDocsExamined` | Number of documents read |
| `nReturned` | Number of documents returned |
| `executionTimeMillis` | Server-observed execution time in explain; does not replace full API latency |

In newer MongoDB releases, stage names/plan trees may vary; do not assert the exact string `GEO_NEAR_2DSPHERE` in tests across all versions. Inspect the actual plan and compare on representative workloads.

### 16.3. `$geoWithin` Can Skip Sorting

If the API only asks "which points are in the region?", the query:

```javascript
db.pickup_points.find({
  tenant_id: "TENANT-A",
  location: {
    $geoWithin: {
      $centerSphere: [[106.7, 10.8], 2000 / 6378137.0]
    }
  }
})
```

does not need to compute and sort distances; it can be cheaper than a proximity search of the same radius, especially for membership checks or counts. However, that **does not guarantee `$geoWithin` is always faster**. Examine point density, indexes, filters, and the query planner.

### 16.4. What If There Are Multiple Geospatial Indexes?

A collection may have `2dsphere` indexes on both `location` and `serviceArea`. For `$geoNear`, explicitly specify `key: "location"` to avoid picking the wrong index or failing when the server cannot disambiguate which geospatial index to use.

```javascript
{
  $geoNear: {
    near: {
      type: "Point",
      coordinates: [106.7, 10.8]
    },
    key: "location",
    distanceField: "distanceMeters",
    spherical: true
  }
}
```

Rate limits and result caps should be enforced in the API; prevent clients from passing huge radii or unlimited result counts.

## 17. Bad Data, Safety, and Boundary Cases

### 17.1. Validating at the API and Database

All client-submitted coordinates should be checked:

```java
public static void checkLngLat(double longitude, double latitude) {
    if (!Double.isFinite(longitude)
            || !Double.isFinite(latitude)
            || longitude < -180 || longitude > 180
            || latitude < -90 || latitude > 90) {
        throw new IllegalArgumentException(
            "Invalid longitude/latitude");
    }
}
```

Reject `NaN`, `Infinity`, swapped lat/lng, or "geocoded addresses" lacking clear provenance/accuracy. Validate GeoJSON `type`, `coordinates` structure, ring closure, and Polygon topology before persisting.

MongoDB geospatial indexes are typically **sparse-like** for null/missing geo fields, so documents lacking a location may be omitted from the index and absent from proximity searches. Do not assume "not found" means the document does not exist; its `location` may be missing, malformed, or unindexed.

### 17.2. A Point Standing Right on the Boundary

If a user is near a delivery zone border, GPS drift (several meters or more) can make `within` flip between two readings. A geospatial query result is an observation over stored coordinates, **not a guarantee of exact physical position**.

For critical delivery rules:

- Choose an explicit policy for boundaries, tolerance/buffers, and GPS source accuracy.
- Consider storing a verified location or normalized address when needed.
- Never base irreversible financial or legal consequences on a single `$geoWithin` check.
- If regions have holes or overlaps, define zone priority order and overlap handling.

### 17.3. Antimeridian and Regions Larger Than a Hemisphere

Polygons crossing the ±180° meridian can produce unexpected results if points are connected naively in 2D Euclidean map space. For GeoJSON geospatial queries, MongoDB has specific CRS/ring rules; areas larger than a hemisphere may require strict winding CRS configuration or splitting into multiple suitable polygons. Check the `$geoWithin`/`2dsphere` docs for your version and test directly on boundary-crossing data.

### 17.4. Avoid Computing Distances via Euclidean Formula on Lon/Lat Degrees

Do not use:

```java
double distance = Math.sqrt(
    Math.pow(lng1 - lng2, 2) +
    Math.pow(lat1 - lat2, 2)
);
// Value is in coordinate "degrees", NOT meters.
```

At different latitudes, one degree of longitude represents very different ground distances; even degrees of latitude are not strictly flat across reference systems. For proximity search, use MongoDB's spatial engine/index or a verified GIS library matching your requirements.

### 17.5. Privacy of Location Data

Exact coordinates can be sensitive information. For location APIs:

- Do not log exact user GPS coordinates or identities unnecessarily.
- Enforce tenant isolation and role-based query limits.
- Set TTL/retention on location history where appropriate instead of storing indefinitely by default.
- Cap query radii and apply rate limiting to mitigate user location probing.
- Distinguish **public store locations** from **real-time personal locations** in access control.

## 18. Integration Testing: Near Has Order, Within Only Filters

Unit-testing `Criteria`/`Query` alone does not prove a real geospatial index works. You must run real MongoDB in an **isolated test database**, create indexes before querying, and verify both BSON and results.

### 18.1. `@DataMongoTest` and Seeding Synthetic Points

```java
package com.example.geo;

import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.index.GeospatialIndex;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
class PickupGeoQueryIntegrationTest {

    @Autowired
    MongoTemplate template;

    @BeforeEach
    void prepareIsolatedTestCollection() {
        // WARNING: run only on an isolated test database!
        template.getCollection("pickup_points")
            .deleteMany(new Document());

        template.indexOps(PickupPoint.class)
            .ensureIndex(new GeospatialIndex("location")
                .typed(GeoSpatialIndexType.GEO_2DSPHERE)
                .named("pickup_location_2dsphere"));

        template.insertAll(List.of(
            new PickupPoint(
                "P-001", "TENANT-A", "Point A", true,
                new GeoJsonPoint(106.7000, 10.8000)),
            new PickupPoint(
                "P-002", "TENANT-A", "Point B", true,
                new GeoJsonPoint(106.7050, 10.8050)),
            new PickupPoint(
                "P-003", "TENANT-A", "Point C", false,
                new GeoJsonPoint(106.7300, 10.8300)),
            new PickupPoint(
                "P-004", "TENANT-B", "Point D", true,
                new GeoJsonPoint(106.7010, 10.8010))
        ));
    }

    @Test
    void nearSphereOrdersByDistanceAndFiltersTenant() {
        Query query = Query.query(
            Criteria.where("tenantId").is("TENANT-A")
                .and("active").is(true)
                .and("location")
                    .nearSphere(
                        new GeoJsonPoint(106.7000, 10.8000))
                    .maxDistance(2000)
        );

        List<PickupPoint> actual =
            template.find(query, PickupPoint.class);

        assertThat(actual).extracting(PickupPoint::getId)
            .containsExactly("P-001", "P-002");
    }

    @Test
    void withinSphereSelectsSameAreaWithoutDistanceRanking() {
        double radians = 2000.0 / 6_378_137.0;

        Query query = Query.query(
            Criteria.where("tenantId").is("TENANT-A")
                .and("active").is(true)
                .and("location")
                    .withinSphere(new org.springframework.data.geo.Circle(
                        new org.springframework.data.geo.Point(
                            106.7000, 10.8000),
                        radians))
        );

        List<PickupPoint> actual =
            template.find(query, PickupPoint.class);

        // Do not assert order: $geoWithin does not sort automatically.
        assertThat(actual).extracting(PickupPoint::getId)
            .containsExactlyInAnyOrder("P-001", "P-002");
    }

    @Test
    void geoJsonMappingStoresLongitudeBeforeLatitude() {
        Document raw = template.getCollection("pickup_points")
            .find(new Document("_id", "P-001"))
            .first();

        assertThat(raw).isNotNull();
        Document loc = (Document) raw.get("location");
        assertThat(loc.getString("type")).isEqualTo("Point");
        assertThat(loc.getList("coordinates", Double.class))
            .containsExactly(106.7000, 10.8000);
    }
}
```

`template.getCollection(...).deleteMany(new Document())` deletes **every document** in the connected test collection. Only use this on a dedicated test MongoDB instance; never run it on production, shared staging databases, or parallel test suites sharing the same collection. If your project uses a different `GeoSpatialIndexType.GEO_2DSPHERE`/`GeospatialIndex` API in its version, adjust per Javadoc; never skip verifying the index.

### 18.2. Testing Different Units and Boundary Points

Beyond the two main tests, cover these cases:

| Scenario | Expectation |
| --- | --- |
| Point identical to center | Near distance approximately 0, appears first if no other tied point |
| Point ~700 m from center | Included within 2 km radius |
| Point ~4 km from center | Excluded from 2 km radius |
| Closer point from another tenant | Never appears in authenticated tenant's results |
| `active=false` point near center | Excluded when filtering `active=true` |
| Just outside radius | Excluded per MongoDB semantics; use reasonable test tolerance |
| Swapped lat/lng | Rejected by input validation when out of range, or caught by reference location tests |
| `NaN`/`Infinity` | Rejected by validation before querying |
| Missing index | Near query fails; caught by migration readiness checks |
| Unclosed polygon ring | Rejected by validation or server error depending on type/version |
| `$geoWithin` returns different order across runs | Never assert ordering without `sort` |
| Legacy pair vs GeoJSON query | Test units/serialization for the actual type |

### 18.3. Testing `GeoResults` with Metrics

```java
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.NearQuery;

NearQuery near = NearQuery.near(
        new GeoJsonPoint(106.7, 10.8),
        Metrics.KILOMETERS)
    .maxDistance(2)
    .limit(10);

GeoResults<PickupPoint> results =
    template.geoNear(near, PickupPoint.class);

assertThat(results.getContent())
    .isNotEmpty();

GeoResult<PickupPoint> first = results.getContent().get(0);
assertThat(first.getContent().getId()).isEqualTo("P-001");
assertThat(first.getDistance().getValue())
    .isCloseTo(0.0, org.assertj.core.data.Offset.offset(0.001));
```

This snippet illustrates a test block using the injected `template` and fixtures above; if additional points share exact coordinates, tie order is not guaranteed. `getDistance().getValue()` reflects the query's metric; **do not multiply by 1000** if your code already selected meter units.

## 19. Common Errors and Diagnostics Table

| Symptom | Possible Cause | How to Fix |
| --- | --- | --- |
| `$near` reports no geo index | Missing `2dsphere` on the exact BSON field | Check `getIndexes()`, migrations, and field path |
| Proximity search returns very distant points | Swapped lat/lng or confused degrees/meters/radians | Check `GeoJsonPoint(x,y)` and `$maxDistance` expression |
| `withinSphere` returns far too many points | Passed `radiusMeters` directly into `Circle` | Divide by Earth radius to convert to radians |
| `within(Circle)` behaves differently from `withinSphere` | Planar `$center` vs spherical `$centerSphere` | Pick the right geometric model and unit |
| `$near` order breaks after adding `sort` | Additional sort overrides distance ranking | Remove extra sort or build a `$geoNear` pipeline then sort |
| `$geoWithin` results not ordered by proximity | Within does not rank by distance | Use `$near`/`$geoNear` if ranking is required |
| `$geoIntersects` returns routes crossing zone missed by Within | Intersects matches partial overlap | Pick operator for "intersects" vs "fully inside" |
| Polygon fails to match despite looking right on map | Unclosed ring, bad geometry, or wrong CRS | Validate GeoJSON, winding, holes, and test |
| Wrong results near ±180° | Region crosses antimeridian | Design Polygon/CRS properly and add boundary tests |
| `$geoNear` fails due to multiple geospatial indexes | Ambiguous location index | Specify `key: "location"` |
| `$geoNear` stage ordering error | Placed `$match`/another stage before `$geoNear` | Put `$geoNear` first, filter inside `query` |
| `$near` inside aggregation `$match` fails | `$near` is disallowed in aggregation | Use `$geoNear` or `$geoWithin` |
| `countDocuments` with `$nearSphere` fails | Count helper uses aggregation | Switch to `$geoWithin/$centerSphere` |
| Repository `Near` returns confusing distances | Legacy `Point`/`GeoJsonPoint` and `Metric` differences | Choose type/metric explicitly, test actual numbers |
| `NearQuery.maxDistance(2)` too large or too small | Missing metric or wrong unit | Pass `Metrics.KILOMETERS` when intending km |
| `$or` query with near + other branch fails | `$or`/near restriction | Redesign query or merge results safely |
| `$text` combined with near fails | Two conflicting special-index requirements | Split steps or use a dedicated search engine |
| `2dsphere` index omits documents | `location` missing, null, invalid geometry, or sparse semantics | Check schema, migrations, and bad data |
| Multi-tenant repository leaks locations | Derived query only filters location, lacks tenant filter | Add tenant predicate from auth/service |
| `explain` shows high scan cost | Radius too large, missing index, or unselective filters | Cap radius/limit and evaluate compound indexes |
| `GeoJsonPolygon` constructor throws | Unclosed ring or too few points | Ensure first == last point, validate topology |
| Frontend sends `lat,lng` while server expects `lng,lat` | Unclear naming convention | Use explicit DTOs and serialization unit tests |
| Geosearch pagination misses/duplicates items | Distance ties/mutating data and deep skip | Tie-breaker, cap radius, cursor policy |
| "Nearest" store is not the fastest to reach | Spherical distance differs from road network | Use a routing/ETA service for travel routes |

### Short Investigation Workflow

1. **Confirm real data:** is raw BSON `location` a GeoJSON Point or legacy `[x,y]`? Are longitude/latitude swapped?
2. **Confirm indexes:** inspect `getIndexes()`, geospatial type, BSON field name, and migration state.
3. **Print the actual query:** inspect `$geometry`, `$centerSphere`, distance limits, and tenant filters; avoid logging sensitive user coordinates.
4. **Check the operator:** is nearest-first required? If only counting or filtering a region, use Within.
5. **Check units:** meters for GeoJSON near, radians for centerSphere, degrees for coordinates.
6. **Check explain outside transactions:** which index was picked, how many keys/docs were examined, actual latency.
7. **Check edge tests:** center point, outside radius, ring closure, other tenant, ±180°, and concurrent data updates.

## 20. Practice Exercises and Answers

### Exercise 1. Near or Within?

**Question:** An API only needs to return all pickup points within a 3 km radius to plot on a map, with no nearest-first ordering needed. Which operator should you pick?

**Answer:** `$geoWithin` with `$centerSphere` (radius in radians). `$near` is unnecessary because it sorts by distance. Still maintain a geospatial index and cap the result count.

### Exercise 2. Coordinate Order

**Question:** Frontend sends `latitude=10.8`, `longitude=106.7`. Which code creates the right GeoJSON Point?

**Answer:**

```java
GeoJsonPoint point = new GeoJsonPoint(106.7, 10.8);
```

Because GeoJSON requires `[longitude, latitude]`.

### Exercise 3. 2 km in `$nearSphere`

**Question:** With a GeoJSON Point and `2dsphere` index, how many km is `$maxDistance: 2000`?

**Answer:** **2 km**, because `$maxDistance` is in **meters** when the query uses a GeoJSON Point.

### Exercise 4. 2 km in `$centerSphere`

**Question:** Can you write `$centerSphere: [[lng,lat], 2000]` to search within 2 km?

**Answer:** No. Convert:

```javascript
const radians = 2000 / 6378137.0;
const filter = {
  location: {
    $geoWithin: {
      $centerSphere: [[106.7, 10.8], radians]
    }
  }
};
```

### Exercise 5. Repository `Within(Circle)`

**Question:** Does `findByLocationWithin(new Circle(new Point(...), 2))` always mean a 2 km radius?

**Answer:** No. `Within(Circle)` typically generates planar `$center`, with radius in coordinate units. For 2 km on Earth, use `withinSphere` with radians or a geospatial API explicitly configured with a metric.

### Exercise 6. Lost Ordering

**Question:** Why does `$near` followed by `sort({name:1})` stop returning nearest-first?

**Answer:** `$near` produces distance order; the extra `sort` re-orders by name. If you need nearest-first, keep the geographic ordering or use a `$geoNear` pipeline to define an explicit tie-breaker.

### Exercise 7. Points Inside a Polygon

**Question:** Check which stores lie inside a declared GeoJSON Polygon without sorting by distance—what do you use?

**Answer:** `$geoWithin: {$geometry: polygon}`, or `Criteria.where("location").within(geoJsonPolygon)`.

### Exercise 8. Route Crossing a Region

**Question:** A `LineString` starts outside a zone, enters it, and exits, so it may not satisfy `$geoWithin`. Which operator detects that it crosses the zone?

**Answer:** `$geoIntersects` with the GeoJSON Polygon, plus a `2dsphere` index on the route field.

### Exercise 9. `countDocuments` and Near

**Question:** Why is `countDocuments({location: {$near: ...}})` rejected?

**Answer:** The count helper is backed by aggregation and does not accept `$near`/`$nearSphere`. For "count points within a radius", switch to `$geoWithin` and `$centerSphere` with the right units.

### Exercise 10. `GeoNear` Aggregation

**Question:** When a `distanceMeters` field is needed for each location, is `find` with `$near` enough?

**Answer:** No, it does not automatically provide a distance field. Use `$geoNear` with `distanceField`, or Spring Data `NearQuery`/`GeoResult.getDistance()`.

### Exercise 11. Required Index

**Question:** For a GeoJSON Point and `$near`, what index should you create?

**Answer:** `{location: "2dsphere"}`. Do not just add the annotation and assume production already has the index.

### Exercise 12. Legacy Pair vs GeoJSON

**Question:** Why might `NearQuery.near(new Point(lng,lat))` produce different distances than `NearQuery.near(new GeoJsonPoint(lng,lat))` when no `Metric` is specified?

**Answer:** Legacy pairs and GeoJSON have different representations and unit interpretations (radians vs meters in spherical near). Use the proper type and `Metrics.KILOMETERS`/`MILES` when needed.

### Exercise 13. Another Tenant Very Close By

**Question:** A TENANT-B location is 100 m from the customer, and a TENANT-A location is 500 m away. May TENANT-A's API return TENANT-B's location?

**Answer:** No. Geospatial queries must include an authenticated tenant filter. Never let small proximity bypass authorization.

### Exercise 14. Retries and GPS Drift

**Question:** A user sends the same request twice, but GPS coordinates shifted by a few meters; must nearest-first results always be identical?

**Answer:** No. Results depend on query coordinates, source data, and index state; if a business decision must replay identically, store the version/input/decision under an explicit idempotency contract rather than assuming searches are immutable.

### Exercise 15. `$text` Together with `$near`

**Question:** Can you combine `$text` and `$near` in one regular MongoDB query?

**Answer:** No, due to restrictions on combining two special indexes. Redesign the query, use a search engine that supports text + geo, or split into bounded steps and test.

## 21. Geospatial Queries Implementation Checklist

1. **Clear data model:** GeoJSON or legacy? Need Point/Polygon/LineString?
2. **Longitude before latitude:** validate bounds and reject non-finite numbers.
3. **Choose the right geospatial index:** `2dsphere` for GeoJSON/spherical, `2d` for planar legacy.
4. **Migrate indexes before serving traffic:** do not rely solely on `@GeoSpatialIndexed`.
5. **Pick operator by intent:** nearest-first → Near; membership → Within; intersection → GeoIntersects.
6. **Right units:** GeoJSON Near in meters; CenterSphere in radians; verify legacy/Metric.
7. **Distinguish `Circle` and `GeoJsonPolygon`:** planar `Within(Circle)` is not `WithinSphere(Circle)`.
8. **Do not re-sort Near by name** if distance ordering is needed.
9. **Never use `$near` inside a multi-branch `$or` or alongside `$text`.**
10. **Never use Near in `countDocuments`/aggregation `$match`:** use Within or `$geoNear` depending on the goal.
11. **Filter tenant and permissions in the query**, never in Java after loading data.
12. **Cap radius, limit, and query time:** avoid scanning entire collections or sorting excessive distances.
13. **Set `key` in `$geoNear`** if the collection has multiple geospatial indexes.
14. **When distances are needed in responses, use `NearQuery`/`$geoNear`** with explicit units.
15. **Reactive only changes the return wrapper**, not query operators, indexes, or semantics.
16. **Verify raw BSON and explain:** mapped field names, keys/docs examined, geospatial plan.
17. **Validate Polygons:** ring closure, holes, winding, antimeridian, boundaries, and error tolerance.
18. **Never treat geodesic distance as driving time/route distance.**
19. **Test on real MongoDB:** near/far, other tenant, active false, polygons, boundaries, and units.
20. **Protect location data:** privacy, retention, access control, and rate limits.
21. **Verify against your MongoDB/Spring Data version**, especially geospatial stages, transactions, and repository APIs.

## 22. References

Official sources to cross-check against your MongoDB/Spring Data version:

1. **MongoDB Manual — Geospatial Queries:** https://www.mongodb.com/docs/manual/geospatial-queries/
2. **MongoDB Manual — Geospatial Indexes:** https://www.mongodb.com/docs/manual/core/indexes/index-types/index-geospatial/
3. **MongoDB Manual — `$near`:** https://www.mongodb.com/docs/manual/reference/operator/query/near/
4. **MongoDB Manual — `$nearSphere`:** https://www.mongodb.com/docs/manual/reference/operator/query/nearSphere/
5. **MongoDB Manual — `$geoWithin`:** https://www.mongodb.com/docs/manual/reference/operator/query/geoWithin/
6. **MongoDB Manual — `$geoIntersects`:** https://www.mongodb.com/docs/manual/reference/operator/query/geoIntersects/
7. **MongoDB Manual — `$centerSphere`:** https://www.mongodb.com/docs/manual/reference/operator/query/centerSphere/
8. **MongoDB Manual — `$geoNear` aggregation:** https://www.mongodb.com/docs/manual/reference/operator/aggregation/geoNear/
9. **Spring Data MongoDB — Querying Documents:** https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html
10. **Spring Data MongoDB — Repository Query Methods:** https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html
11. **Spring Data MongoDB — Sessions & Transactions:** https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html
12. **Spring Data MongoDB — Criteria Javadoc:** https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/Criteria.html
13. **Spring Data MongoDB — NearQuery Javadoc:** https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/NearQuery.html
14. **Spring Data MongoDB — GeoJsonPolygon Javadoc:** https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/geo/GeoJsonPolygon.html

`current` docs may describe APIs newer than your project's version. When copying code, verify Javadoc for your exact Spring Data MongoDB and MongoDB Server release (especially geospatial geometry parsing, `$geoNear` stage, indexing, transactions, and unit conversion). All coordinates in this lesson are **synthetic examples**, not real-world location recommendations.

## 23. Conclusion

**`Near` and `Within` answer two different questions:** `$near`/`$nearSphere` select geometries near a center and **sort from nearest to farthest**, whereas `$geoWithin` filters geometries lying **inside a region** without sorting. For lines/routes, `$geoIntersects` answers "does it cross/intersect the region?". When you need a **computed distance field**, pick `$geoNear` or `NearQuery`/`GeoResult`. Spring Data MongoDB lets you express these operations through `Criteria`, `MongoTemplate`, repository query methods, and reactive templates.

To keep geographic data accurate and queries fast, store GeoJSON in **`[longitude, latitude]`** order, create a real **`2dsphere` index**, use the right units (**meters for GeoJSON Near, radians for `$centerSphere`**), enforce tenant/radius/limit controls, and verify via `explain` and real MongoDB integration tests. Never use `$near` inside `countDocuments`/aggregation `$match` or mix it with incompatible special-index operators. Finally, test Polygons/antimeridian cases, account for GPS drift, and never equate spherical distance with real road travel.
