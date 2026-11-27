# Distances, Measurement Units, and Conversion Factors

## 1. Why Does a Syntactically Valid Query Return the Wrong Radius?

A pickup-point lookup API receives a request: **"Find points within 2 km of the current location, returning distance in km."** The developer writes a `$geoNear` command with `maxDistance: 2` because the request sent `radiusKm=2`. The command succeeds, yet with a **GeoJSON Point**, MongoDB interprets `maxDistance: 2` as **2 meters**, not 2 km. Only points nearly identical to the coordinates appear.

A legacy system stores coordinates as a `[longitude, latitude]` pair and invokes a spherical search; the value `0.002` in another query might represent **0.002 radians**, corresponding to roughly 12.76 km assuming an Earth radius of 6,378.137 km. If a developer sees "0.002" and interprets it as 2 m, the results can span thousands of times farther than intended.

The issue lies in the **unit contract**, not necessarily the index or MongoDB driver:

- API inputs may use **kilometers** or **meters**.
- WGS84 coordinates are **longitude/latitude in angular degrees**, not meters.
- Some GeoJSON query operators use **meters**, while some legacy operators use **radians**.
- Returned distances may be in **meters**, **radians**, or already multiplied by **`distanceMultiplier`**.
- Spring Data `Distance` and `Metrics` carry their own unit semantics and **must never be guessed from a bare number**.

This lesson belongs to the **Geospatial Queries** chapter in the **SPRING_DATA_MONGODB** module. The module scope covers using Spring Data MongoDB to connect, map documents, and operate via `MongoTemplate` or repositories, practicing query design, aggregation, indexes, transactions, reactive access, testing, and data performance diagnostics.

After this lesson, you will be able to:

1. Distinguish **degrees (°)**, **radians (rad)**, **meters (m)**, **kilometers (km)**, and **miles (mi)**.
2. Choose the right units for `$near`, `$nearSphere`, `$geoNear`, and `$centerSphere`.
3. Understand why a **GeoJSON Point** differs from a **legacy coordinate pair** in both data format and distance calculation.
4. Apply `distanceMultiplier` to convert **returned values**, without confusing it with the `maxDistance` filter.
5. Use `Point`, `GeoJsonPoint`, `Distance`, `Metrics`, and `NearQuery` in Spring Data MongoDB.
6. Design DTOs with explicit units, validate inputs, and protect APIs against unit-conversion bugs.
7. Optimize with `2dsphere`/`2d` indexes, cap results, and test points near radius boundaries.

> **Guidance:** Java examples assume Java 17+, a Spring Data MongoDB version compatible with your project's Spring Boot version, a MongoDB server supporting the geospatial operators used, and isolated test data. Detailed syntax/behavior may depend on server/driver/Spring Data versions. For real deployments, inspect the generated BSON/pipeline and the unit of returned values.

## 2. Unit Model: One Table to Read All Examples

| Quantity | Symbol | Example | Meaning |
| --- | --- | --- | --- |
| Longitude | ° longitude | `106.70` | East–West angle |
| Latitude | ° latitude | `10.78` | North–South angle |
| Central angle | radian | `0.00031357` | Angle between two radii of a sphere |
| Straight-line distance | meter | `2_000 m` | Arc length on a spherical model |
| Straight-line distance | kilometer | `2 km` | `2_000 m` |
| Straight-line distance | mile | `1 mi` | `1_609.344 m` |
| Route distance | real minutes/km | Not inferred from `$geoNear` | Requires separate road-network/traffic data |
| Output factor | Dimensionless (ratio) | `0.001` | Multiply meters to get km |

Calculations below use a **reference radius R = 6,378,137 meters** (6,378.137 km, close to the WGS84 equatorial radius), consistent with Spring Data examples converting radians to kilometers. This is a **reference constant for examples**, not a guarantee that every geospatial system uses the exact same Earth model.

### 2.1. Three Categories of Quantities That Cannot Be Added or Compared Directly

```text
GeoJSON coordinates = [longitudeDegrees, latitudeDegrees]
maxDistance        = distance in meters (for GeoJSON queries)
legacy spherical   = central angle in radians

Example:
  [106.70, 10.78] = a position in angular degrees
  2_000           = 2,000 meters
  0.00031357      = about 2 km in radians on chosen R
```

Do not subtract `Point.x` and `Point.y` to compute meters. Differences in longitude/latitude degrees do not have a constant conversion factor to meters across all latitudes.

### 2.2. GeoJSON Point and Coordinate Order

```javascript
{
  type: "Point",
  coordinates: [106.70, 10.78]
}
```

Per GeoJSON/MongoDB rules, geographic coordinates are written **[longitude, latitude]**, not `[latitude, longitude]` as some map/mobile APIs return.

- Longitude lies in `[-180, 180]`.
- Latitude lies in `[-90, 90]`.
- Input values here are **degrees**, not radians.
- A GeoJSON Point on Earth uses WGS84 longitude/latitude; do not put meters or UTM coordinates into `coordinates` without proper coordinate transformation.

### 2.3. Avoiding Examples Dependent on Real Place Names

The points in this lesson named **"Warehouse A", "Point B", and "Point C"** are synthetic fixtures with numeric coordinates near a tropical region; they do not represent real business locations and must not be used to infer road distances or delivery times.

## 3. Formulas Converting Meters, Kilometers, Miles, and Radians

For a spherical model of radius `R`:

\[
d_{\mathrm{m}} = \theta_{\mathrm{rad}}\times R_{\mathrm{m}}
\]

\[
\theta_{\mathrm{rad}} = \frac{d_{\mathrm{m}}}{R_{\mathrm{m}}}
\]

\[
d_{\mathrm{km}} = \frac{d_{\mathrm{m}}}{1000},\qquad
d_{\mathrm{mi}} = \frac{d_{\mathrm{m}}}{1609.344}
\]

Constants used in this lesson:

```text
R_METERS      = 6_378_137.0
R_KILOMETERS  = 6_378.137
METERS_PER_KM = 1_000.0
METERS_PER_MI = 1_609.344
```

### 3.1. Example: Converting 2 km to Radians

```text
2 km = 2_000 m
2_000 / 6_378_137 ≈ 0.000313571 rad
```

This value is useful for a legacy spherical or `$centerSphere` query, and **must not** be passed as `maxDistance` for GeoJSON `$near`.

### 3.2. Example: Converting 0.001 Radians to Kilometers

```text
0.001 rad × 6_378.137 km/rad = 6.378137 km
```

Conversely, "1 radian" does not mean "1 km". A radian is an angle; multiplying by the radius in a distance unit gives arc length.

### 3.3. Example: Converting 5 Miles to Meters

```text
5 miles × 1_609.344 m/mile = 8_046.72 m
```

With GeoJSON `$nearSphere`, if the API accepts 5 miles, send `$maxDistance: 8046.72`.

### 3.4. Converting Degrees to Radians

\[
\theta_{\mathrm{rad}} = \theta_{\mathrm{deg}}\times\frac{\pi}{180}
\]

**Do not apply this formula directly to longitude/latitude before storing them in GeoJSON.** GeoJSON still expects degrees. The degree-to-radian formula is useful for geometric calculations (e.g., Haversine) or operators requiring a **radial angle**, not for changing GeoJSON's format.

## 4. Unit Table by MongoDB Operator

| Operator / Query Path | Query Point | Radius / Limit Unit | Returned Distance Unit | Primary Index |
| --- | --- | --- | --- | --- |
| `$near` | GeoJSON `Point` | **Meters** | Finds/sorts only, does not add a distance field | `2dsphere` |
| `$nearSphere` | GeoJSON `Point` | **Meters** | Does not add a distance field | `2dsphere` |
| `$geoNear` | GeoJSON `Point` | **Meters** | Usually **meters** before multiplier | `2dsphere` |
| `$nearSphere` | Legacy `[lon,lat]` on sphere | **Radians** | Does not add a distance field | Suitable `2d` or `2dsphere` |
| `$geoNear` | Legacy `[lon,lat]` with spherical | **Radians** | **Radians** before multiplier | Suitable geospatial index |
| `$near` | Legacy `[x,y]` with `2d` | Depends on legacy operator/semantics (planar) | Does not add a distance field | `2d` |
| `$geoWithin: {$centerSphere: ...}` | Legacy center `[lon,lat]` | **Radians** in radius element | Does not compute distance output | `2dsphere` or suitable geospatial index |
| `$geoWithin: {$center: ...}` | Legacy planar center | Planar coordinate units | Does not compute distance output | `2d` |

**An important pitfall:** Storing GeoJSON in the collection does not automatically make every **query point** format use meters. In `$geoNear`, the shape of `near` (GeoJSON object vs legacy pair) and spherical semantics determine the unit of limits and outputs. Never inspect only the document's `location` field and assume the unit.

### 4.1. Keep the Internal Standard as Simple as Possible

For business applications using longitude/latitude, a safe choice is usually:

1. Store **GeoJSON Point** in `[longitude, latitude]` order.
2. Create a **`2dsphere`** index.
3. Normalize input distances to **meters** before sending raw MongoDB queries.
4. Read `$geoNear` outputs in **meters** when no multiplier is used.
5. Convert to km/miles **once at the API boundary** or use a controlled multiplier.

External APIs do not all have to send meters; just use an explicit conversion adapter and test it properly.

## 5. Preparing a GeoJSON Collection and `2dsphere` Index

Run the following fixtures only on an **isolated test database**:

```javascript
use geo_training;

db.pickup_points.insertMany([
  {
    _id: "p-a",
    tenantId: "tenant-a",
    name: "Warehouse A",
    active: true,
    location: {
      type: "Point",
      coordinates: [106.7000, 10.7800]
    }
  },
  {
    _id: "p-b",
    tenantId: "tenant-a",
    name: "Point B",
    active: true,
    location: {
      type: "Point",
      coordinates: [106.7100, 10.7800]
    }
  },
  {
    _id: "p-c",
    tenantId: "tenant-a",
    name: "Point C",
    active: false,
    location: {
      type: "Point",
      coordinates: [106.7400, 10.8000]
    }
  },
  {
    _id: "p-foreign",
    tenantId: "tenant-b",
    name: "Foreign tenant point",
    active: true,
    location: {
      type: "Point",
      coordinates: [106.7001, 10.7801]
    }
  }
]);

db.pickup_points.createIndex(
  { location: "2dsphere" },
  { name: "ix_pickup_location_2dsphere" }
);
```

These longitudes/latitudes are synthetic data. Before creating an index on a collection with legacy data, check for malformed geometry fields, `null`s, missing fields, coordinate order, and index version.

### 5.1. Why Not Use a `2d` Index for GeoJSON?

`2dsphere` supports spherical geometry queries and GeoJSON. `2d` targets legacy coordinate pairs and planar geometry. If the goal is "points within a 2 km radius on Earth's surface", do not pick `2d` and implicitly treat each x/y unit as one meter.

### 5.2. Avoid Indexing the Wrong Field Path

```javascript
// Right for GeoJSON Point:
db.pickup_points.createIndex({ location: "2dsphere" });

// Do not replace arbitrarily with:
// db.pickup_points.createIndex({ "location.coordinates": "2d" });
```

Indexing `location.coordinates` as `2d` changes semantics and is not equivalent to indexing the GeoJSON geometry object. With multiple geospatial fields/indexes, `$geoNear` queries should specify `key` explicitly.

### 5.3. Do Not Create Indexes Inside Request Handlers

Create/manage indexes through migrations, provisioning, or operational workflows; verify index existence before running geo queries. Spring Data `@GeoSpatialIndexed` can help define index metadata, but auto-index creation depends on config/framework version and does not replace production management procedures.

## 6. `$near` Query with GeoJSON: Radius in Meters

Find points within **2 km** around `[106.7000, 10.7800]`:

```javascript
db.pickup_points.find({
  tenantId: "tenant-a",
  active: true,
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
});
```

Here `2000` is **meters**. `$near` executes a geospatial proximity query returning nearest to farthest per the operator's semantics; a standard `find` **does not add a distance field** for the client to read. If the API needs to display exact km, use `$geoNear` or an external distance calculation with a consistent definition.

### 6.1. If You Only Want Within 500 Meters

```javascript
$maxDistance: 500
```

### 6.2. If the Request Receives `radiusKm = 2`

```javascript
const radiusKm = 2;
const radiusMeters = radiusKm * 1000;
// Use radiusMeters as $maxDistance in the GeoJSON query.
```

### 6.3. If the Radius Comes in Miles

```javascript
const radiusMiles = 3;
const radiusMeters = radiusMiles * 1609.344;
// 4828.032 meters.
```

### 6.4. Do Not Turn `$near` into Road Distance Measurement

Spherical geospatial distance knows nothing about closed roads, rivers, bridges, overpasses, traffic jams, or routing restrictions. Use it to **filter candidates** and approximate straight-line distance; if the contract requires ETA or driving kilometers, integrate a proper routing data source.

## 7. `$nearSphere` with GeoJSON: Also Meters

```javascript
db.pickup_points.find({
  location: {
    $nearSphere: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      $maxDistance: 2000
    }
  }
});
```

With a **GeoJSON Point**, `$nearSphere`'s `$maxDistance` is also in meters. Do not infer from the word `Sphere` that radians must be passed in every case.

### 7.1. Choosing `$near` vs `$nearSphere` by Context

In MongoDB geospatial queries:

- `$near` with GeoJSON uses spherical semantics suitable for `2dsphere`.
- `$nearSphere` emphasizes spherical geometry and also supports legacy coordinate pairs under different rules.
- Choose based on **geometry representation and index**, not only the operator name.

### 7.2. `minDistance` Must Use the Same Unit

To query an **annulus from 500 m to 2,000 m**, use:

```javascript
db.pickup_points.find({
  location: {
    $nearSphere: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      $minDistance: 500,
      $maxDistance: 2000
    }
  }
});
```

Never mix `$minDistance` in kilometers and `$maxDistance` in meters within the same query.

## 8. `$geoNear`: Computing Distance and Controlling Returned Units

When an API needs **both the nearest points and the meters/km** for each result, `$geoNear` in an aggregation pipeline fits better than a plain `$near` query.

### 8.1. Returning Distance in Meters (Default for GeoJSON)

```javascript
db.pickup_points.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      key: "location",
      spherical: true,
      minDistance: 0,
      maxDistance: 2000,
      distanceField: "distanceMeters",
      query: {
        tenantId: "tenant-a",
        active: true
      }
    }
  },
  { $limit: 20 },
  {
    $project: {
      _id: 1,
      name: 1,
      location: 1,
      distanceMeters: 1
    }
  }
]);
```

Here:

- `near` is a **GeoJSON Point**.
- `maxDistance: 2000` is **2,000 meters**.
- No `distanceMultiplier` → `distanceMeters` is the distance **in meters** in this case.
- `query` adds tenant/active conditions right inside `$geoNear`.
- `key` specifies the field carrying the `2dsphere` index.
- `$limit: 20` caps returned records; `$geoNear` does not default to a 100-result limit in current MongoDB versions.

### 8.2. `$geoNear` Must Be at the Start of the Pipeline

```javascript
// Invalid under general $geoNear rules:
db.pickup_points.aggregate([
  { $match: { tenantId: "tenant-a" } },
  { $geoNear: { /* ... */ } }
]);
```

`$geoNear` must be the **first stage** in the pipeline, with specific nuances for time-series and versions. Place tenant/active predicates in the stage's `query` option when supported by the API. Do not move `$match` in front just hoping to filter earlier.

### 8.3. Multiple Geospatial Indexes Require `key`

If a collection has `2dsphere` indexes on both `location` and `backupLocation`, the server may not know which index to pick for `$geoNear`. Set:

```javascript
key: "location"
```

to specify the field. Do not assume an index will be chosen reliably by alphabetical order.

### 8.4. `distanceField` Does Not Enforce Its Own Unit

The field name `"distanceMeters"` is just our naming choice. MongoDB does not validate that the name matches the unit. If you add `distanceMultiplier: 0.001` while still naming the field `distanceMeters`, the API will silently mislead consumers.

## 9. `distanceMultiplier`: Multiplies Output, Does Not Change Filter Radius

`$geoNear`'s `distanceMultiplier` **multiplies returned distances** after calculation. It **does not convert `maxDistance` from km to meters**.

### 9.1. GeoJSON: Returning Kilometers

```javascript
db.pickup_points.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      key: "location",
      spherical: true,
      maxDistance: 2000,           // still METERS
      distanceMultiplier: 0.001,   // m -> km for OUTPUT
      distanceField: "distanceKm",
      query: {
        tenantId: "tenant-a",
        active: true
      }
    }
  },
  { $limit: 20 }
]);
```

For example, for a point at raw distance 1,250 m:

```text
distanceKm = 1_250 × 0.001 = 1.25 km

The filter condition remains:
  raw distance <= 2_000 meters
```

### 9.2. GeoJSON: Returning Miles

```javascript
distanceMultiplier: 1 / 1609.344
```

A point 1,609.344 m away is shown as roughly 1 mile. The unit of `maxDistance` remains **meters**, e.g., `maxDistance: 4828.032` for 3 miles.

### 9.3. Multiplier Table for GeoJSON Output

| Raw Result Unit | Desired Output | `distanceMultiplier` Factor | Example |
| --- | --- | --- | --- |
| meters | meters | `1` (or omit property) | 500 m → 500 |
| meters | kilometers | `0.001` | 500 m → 0.5 km |
| meters | miles | `1 / 1609.344` | 1609.344 m → 1 mi |

### 9.4. Do Not Use 6378.137 for GeoJSON Output If You Want Kilometers

```javascript
// WRONG with GeoJSON raw distance in meters:
distanceMultiplier: 6378.137
```

The factor 6378.137 (km/rad) is for **raw results in radians** in a spherical query using a legacy coordinate pair. Using it with GeoJSON raw distances in meters inflates the output by roughly 6,378,137 times compared to the true km value.

### 9.5. Do Not Convert Twice

If the pipeline returns `distanceKm` via `distanceMultiplier: 0.001`, the service **must not divide by 1000 again**. An API contract should pick one:

- Return raw `distanceMeters` from MongoDB and convert to km in Java, **or**
- Use `distanceMultiplier` in MongoDB and return `distanceKm` directly.

Never perform both conversions on the same value.

## 10. Legacy Coordinate Pairs and Radian Distances

A legacy point has the syntax:

```javascript
[106.7000, 10.7800]
```

These are still **longitude/latitude coordinates in degrees**, **not** a pair of radians. However, in a legacy spherical query, **distance parameters** and computed distances can be in radians.

### 10.1. Illustrative Legacy Data

```javascript
db.legacy_pickup_points.insertMany([
  { _id: "l-a", tenantId: "tenant-a", loc: [106.7000, 10.7800] },
  { _id: "l-b", tenantId: "tenant-a", loc: [106.7100, 10.7800] }
]);

db.legacy_pickup_points.createIndex(
  { loc: "2dsphere" },
  { name: "ix_legacy_loc_2dsphere" }
);
```

A `2dsphere` index can work with legacy coordinate pairs in appropriate cases. When using a specific operator, still check its own format/index requirements.

### 10.2. Legacy `$nearSphere`: 2 km Must Be Converted to Radians

```javascript
const earthRadiusMeters = 6378137.0;
const twoKmRadians = 2000.0 / earthRadiusMeters;

db.legacy_pickup_points.find({
  loc: {
    $nearSphere: [106.7000, 10.7800],
    $maxDistance: twoKmRadians
  }
});
```

This is the major difference compared to `$nearSphere` using GeoJSON `$geometry`:

```text
GeoJSON nearSphere:
  $maxDistance = 2000 METERS

Legacy spherical nearSphere:
  $maxDistance = 2000 / R_METERS RADIANS
```

### 10.3. Legacy `$geoNear` Returning Distance in Kilometers

```javascript
db.legacy_pickup_points.aggregate([
  {
    $geoNear: {
      near: [106.7000, 10.7800],
      key: "loc",
      spherical: true,
      maxDistance: 2000.0 / 6378137.0,
      distanceMultiplier: 6378.137,
      distanceField: "distanceKm",
      query: { tenantId: "tenant-a" }
    }
  },
  { $limit: 20 }
]);
```

In this example:

- The raw distance of the legacy spherical query is **radians**.
- `maxDistance` is passed in **radians**.
- Multiply by `distanceMultiplier: 6378.137` to output **km**.

If you want output in meters instead of km, use `distanceMultiplier: 6378137.0`. The numerical conversion relies on a reference radius; do not assume geometric calculations across systems or versions always yield bitwise identical results.

### 10.4. Stored Data and Near Query Shape Are Two Separate Things

A MongoDB field can store GeoJSON while `$geoNear` still accepts a legacy coordinate pair as its near query input if an appropriate index is used. In that case, **the shape of the near query** determines the unit of limits and results. That is why inspecting the **BSON pipeline** matters more than only looking at the Java entity field type.

## 11. `$centerSphere`: Always Requires Radius in Radians

A `$geoWithin` query with `$centerSphere` looks like finding points in a circle:

```javascript
db.pickup_points.find({
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.7000, 10.7800],
        2000.0 / 6378137.0
      ]
    }
  }
});
```

With `$centerSphere`, the radius element of the expression **is in radians**, even when the collection stores GeoJSON Points and uses a `2dsphere` index.

### 11.1. `$centerSphere` Does Not Return Precomputed Distances

`$geoWithin` tests region membership; it **does not sort nearest-to-farthest** and **does not add a distance field**. If the API wants to display km per point, calculate it afterward in the application or use `$geoNear`.

### 11.2. Comparison with `$near`

| Goal | Operator |
| --- | --- |
| Get points within radius and auto-sort nearest first | `$near`/`$nearSphere` |
| Get points + distance field for display | `$geoNear` |
| Only filter points belonging to a circular region | `$geoWithin + $centerSphere` |
| Complex polygon/geometry regions | `$geoWithin + $geometry` with suitable semantics |

### 11.3. Different Optimizations

`$near` and `$geoNear` generally require a matching geospatial index. `$centerSphere` can also be evaluated without an index on some paths, though indexes improve performance on large collections. Use `explain` to verify instead of assuming every geospatial query uses the same plan.

## 12. Conversion Factors Are Not Coordinate Systems

A `distanceMultiplier` only scales **computed length/angle outputs**; it does not turn GPS coordinates into planar coordinates. It does not:

- Convert longitude/latitude into UTM X/Y.
- Fix swapped `[latitude, longitude]` order.
- Modify already indexed data.
- Turn straight-line distance into driving distance.
- Compensate for GPS errors from devices, roofs, or urban canyons.
- Add elevation or terrain into MongoDB's geospatial algorithms.

### 12.1. Example Confusing Degrees and Meters

```javascript
// WRONG: passing coordinates multiplied by 1000 intending to "convert to meters".
{
  type: "Point",
  coordinates: [106700, 10780]
}
```

GeoJSON Points require lon/lat within valid bounds, so the numbers above are meaningless for Earth coordinates. Convert only **radius/distance** where required—never scale longitude/latitude.

### 12.2. Degrees of Latitude and Longitude Do Not Have Equal Length

One degree of longitude near the equator represents a longer ground distance than one degree of longitude at high latitudes. Therefore:

```text
deltaLon = 0.01 degrees
```

does not correspond to a fixed number of meters worldwide. Use appropriate geo operators or distance formulas with a defined Earth model.

### 12.3. Earth Radius Is a Model Parameter

MongoDB/Spring documentation includes examples using an equatorial radius near `6378.1 km`. Some GIS systems use a mean radius near `6371 km`. The two choices yield small differences visible in boundary tests. Therefore:

- Use **one named constant** across all `meters ↔ radians` conversions in your application.
- Never promise bitwise identical results compared to another algorithm using a different ellipsoid/CRS.
- Use reasonable tolerances for distance assertions.

## 13. Spring Data MongoDB: Where Do `Point` and `GeoJsonPoint` Differ?

### 13.1. Legacy `Point`

```java
import org.springframework.data.geo.Point;

Point legacyNear = new Point(106.7000, 10.7800);
```

In Spring Data MongoDB, `Point` in a geo query context may be serialized as a **legacy coordinate pair**:

```javascript
[106.7000, 10.7800]
```

In a spherical legacy query, limit units may be converted to radians. Do not assume a `Point` always has GeoJSON semantics just because x/y are longitude/latitude.

### 13.2. `GeoJsonPoint`

```java
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;

GeoJsonPoint geoNear = new GeoJsonPoint(
    106.7000, 10.7800
);
```

It renders as:

```javascript
{
  type: "Point",
  coordinates: [106.7000, 10.7800]
}
```

`GeoJsonPoint.getX()` corresponds to **longitude**, and `getY()` corresponds to **latitude**. The serialization difference of the origin governs how MongoDB interprets raw distances in geospatial queries.

### 13.3. Do Not Import the Wrong `Point`

```java
// Legacy:
org.springframework.data.geo.Point

// GeoJSON:
org.springframework.data.mongodb.core.geo.GeoJsonPoint
```

A refactor that merely swaps imports/constructors from `Point` to `GeoJsonPoint` can alter **units** in the pipeline even though the numeric coordinates stay identical. Always inspect rendered BSON queries before and after migration.

## 14. Spring Data `Distance`, `Metric`, and `Metrics`

Spring Data Commons provides `Distance` and `Metric` to carry unit semantics into queries. Common types:

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metric;
import org.springframework.data.geo.Metrics;

Distance twoKilometers = new Distance(
    2, Metrics.KILOMETERS
);

Distance threeMiles = new Distance(
    3, Metrics.MILES
);

Distance rawNumber = new Distance(
    2000, Metrics.NEUTRAL
);
```

| Type | Role |
| --- | --- |
| `Distance` | Wraps a value and unit/metric |
| `Metric` | Conversion abstraction for measurement units |
| `Metrics.KILOMETERS` | Kilometers |
| `Metrics.MILES` | Miles |
| `Metrics.NEUTRAL` | Neutral metric, does not attach km/mi |
| `NearQuery` | Builder for geospatial near queries and criteria |
| `GeoResult<T>` | Result containing entity and distance |
| `GeoResults<T>` | Wrapper holding multiple results + aggregate info for imperative APIs |

### 14.1. The Issue Is Not Just the Enum Name

`Metrics.KILOMETERS` does not mean MongoDB Server receives a literal `maxDistance=2` and magically understands km. Spring Data uses the metric to build **queries converted appropriately for the representation**. For legacy spherical queries, Javadoc examples show `Distance(2, Metrics.KILOMETERS)` being converted into a radian bound and matching distance multiplier.

### 14.2. `getValue()` Must Accompany `getMetric()`

```java
Distance distance = new Distance(
    2, Metrics.KILOMETERS
);

double numeric = distance.getValue();
Metric unit = distance.getMetric();
```

`numeric == 2` only means **2 in the Distance's metric**. If you discard `Metric` and serialize the bare number into a unitless JSON `distance` field, clients may assume meters.

### 14.3. Two Safe Strategies

**Strategy A — normalize to meters at the application layer:**

```text
radiusKm from HTTP → convert to radiusMeters
GeoJsonPoint → $geoNear(maxDistance=radiusMeters)
MongoDB raw distanceMeters → response distanceKm = /1000
```

**Strategy B — let Spring Data manage `Metric`:**

```text
Point + Distance(2, Metrics.KILOMETERS)
       ↓
NearQuery / Repository query construction
       ↓
Inspect generated BSON:
  legacy spherical → maxDistance radians,
  corresponding distanceMultiplier for km output
```

Do not mix A and B and end up converting multiple times. With `GeoJsonPoint` and `NearQuery`, prefer explicit **meter** pipelines/bounds in this tutorial and verify outputs rather than assuming Spring Data always generates one fixed BSON shape across all versions.

## 15. A GeoJSON Entity in Spring Data MongoDB

### 15.1. Class Storing Pickup Points

```java
package com.example.geo.persistence;

import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexed;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document("pickup_points")
public record PickupPoint(
    @MongoId(FieldType.STRING) String id,
    String tenantId,
    String name,
    boolean active,
    @GeoSpatialIndexed(type = GeoSpatialIndexType.GEO_2DSPHERE)
    GeoJsonPoint location
) {}
```

`GeoJsonPoint` persists as BSON:

```javascript
{
  type: "Point",
  coordinates: [106.7000, 10.7800]
}
```

Not every MongoDB collection gets an index automatically just from adding an annotation. Spring Data's automatic index creation depends on configuration and version and should generally **not be enabled blindly in production**. When mongosh fixtures create the index, the application should verify actual schema/indexes.

### 15.2. The Field Should Represent One Point

If a document stores multiple locations via `MultiPoint`/array, `$geoNear` may compute distance to the nearest point/boundary per MongoDB semantics, **not necessarily to the geometric center the UI displays**. For a pickup-point search API, one `GeoJsonPoint` per document is usually simpler.

### 15.3. Do Not Patch Raw x/y Numbers While Ignoring Mapping

When updating a location, write a complete valid GeoJSON geometry object. If a migration modifies only part of `location.coordinates`, verify indexes and stored data afterward so you do not accidentally swap lon/lat or store the wrong coordinate system.

## 16. `NearQuery`: Expressing a Query with an Explicit Meter Radius

### 16.1. GeoJSON Origin with a 2,000-Meter Limit

```java
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.NearQuery;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

GeoJsonPoint origin = new GeoJsonPoint(
    106.7000, 10.7800
);

NearQuery near = NearQuery
    .near(origin)
    .maxDistance(2000.0)
    .spherical(true)
    .query(Query.query(
        Criteria.where("tenantId").is("tenant-a")
            .and("active").is(true)
    ));
```

With `GeoJsonPoint` and a numeric maxDistance in this explicit query, the intent is to pass **2,000 meters** to `$geoNear`. Calling `spherical(true)` avoids relying on implicit defaults when reading the code. Before going to production, verify the generated BSON stage in your exact Spring Data version.

### 16.2. Why Not Use `Distance(2, Metrics.KILOMETERS)` Everywhere by Default?

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;

Distance twoKm = new Distance(
    2, Metrics.KILOMETERS
);
```

A `Distance` with a metric is useful if you let Spring Data build the query end-to-end. However, once code has already converted `radiusKm -> radiusMeters` with a GeoJSON origin, you must not **both pass pre-converted meters and attach `Metrics.KILOMETERS`**. Inspect `getMetric` and the serialized pipeline to prevent multiplying or dividing by 1,000 twice.

### 16.3. Specifying Both Min and Max Distance

```java
NearQuery annulus = NearQuery
    .near(new GeoJsonPoint(106.7000, 10.7800))
    .minDistance(500.0)
    .maxDistance(2000.0)
    .spherical(true);
```

Numeric limits are passed in GeoJSON's native unit: **meters** in this example. The name `annulus` refers to a geometric range from 500 m to 2,000 m, not a ring along road networks.

### 16.4. Watch Out for `key` and Multiple Indexes

`NearQuery` is a Spring Data abstraction. If a collection has **multiple geospatial index fields**, check your API version for specifying the key and, if necessary, use an explicit BSON aggregation stage to force `key: "location"`. Never assume the server will always pick the right geospatial index.

## 17. `MongoOperations.geoNear`: Understanding the Legacy API and Returned Distances

Spring Data has:

```java
import org.springframework.data.geo.GeoResults;
import org.springframework.data.mongodb.core.MongoOperations;

GeoResults<PickupPoint> rows =
    mongoOperations.geoNear(near, PickupPoint.class);
```

In current versions, `MongoOperations.geoNear(...)` is marked **deprecated since Spring Data MongoDB 2.2** because MongoDB 4.2 removed the legacy `geoNear` command; Spring Data uses `$geoNear` aggregation underneath for compatibility. **Prefer `Aggregation.geoNear(...)` for new code.**

### 17.1. `GeoResult` and `GeoResults`

```java
rows.getContent().forEach(row -> {
    PickupPoint pickup = row.getContent();
    double value = row.getDistance().getValue();
    // Do not name value as km without verifying metric.
});
```

`GeoResult.getDistance()` returns a `Distance`. A bare `Distance.getValue()` does not attach a unit in JSON if serialized as a `double`. Verify the query/result metric, especially when migrating code from legacy `Point` to `GeoJsonPoint`.

### 17.2. Example of `Point` with `Metrics.KILOMETERS`

```java
import org.springframework.data.geo.Point;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;

Point legacyOrigin = new Point(106.7000, 10.7800);
NearQuery legacyNear = NearQuery
    .near(legacyOrigin)
    .maxDistance(new Distance(2, Metrics.KILOMETERS));

GeoResults<PickupPoint> legacyResults =
    mongoOperations.geoNear(legacyNear, PickupPoint.class);
```

This is the API path **for letting Spring Data manage the metric**, not an example of passing literal `2` to MongoDB as radians. Javadoc explains that Spring Data can generate **`maxDistance` in radians** for legacy spherical queries, along with a multiplier returning results in km. Storing GeoJSON in the document field does not eliminate differences caused by the **near argument**.

### 17.3. Never Directly Compare Results with Different Metrics

```text
GeoJSON raw distance:
  1_250      → meters

Legacy + Metrics.KILOMETERS:
  1.25       → kilometers

Both numbers represent the same distance in different units.
```

Normalize to a single internal unit before comparing, sorting, aggregating, or serializing.

## 18. Spring Data `Aggregation.geoNear`: Preferred for New Code

### 18.1. Aggregation with `$geoNear` at the Start of the Pipeline

```java
package com.example.geo.persistence;

import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.NearQuery;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;

@Component
public class PickupGeoGateway {
    private final MongoOperations mongo;

    public PickupGeoGateway(MongoOperations mongo) {
        this.mongo = mongo;
    }

    public List<Document> nearbyMeters(
        String tenantId,
        double longitude,
        double latitude,
        double radiusMeters
    ) {
        GeoInput.validate(tenantId, longitude, latitude, radiusMeters);

        NearQuery near = NearQuery
            .near(new GeoJsonPoint(longitude, latitude))
            .maxDistance(radiusMeters)
            .spherical(true)
            .query(Query.query(
                Criteria.where("tenantId").is(tenantId)
                    .and("active").is(true)
            ));

        TypedAggregation<PickupPoint> agg =
            Aggregation.newAggregation(
                PickupPoint.class,
                Aggregation.geoNear(near, "distanceMeters"),
                Aggregation.limit(20)
            );

        return mongo
            .aggregate(agg, Document.class)
            .getMappedResults();
    }
}
```

In this example, `GeoInput` is the validation helper from section 22. Resulting `Document` entries carry `distanceMeters` in raw GeoJSON units **when no other multiplier/metric is configured**. Using `TypedAggregation<PickupPoint>` gives Spring Data mapping metadata, though you should still test the pipeline and collection fields.

### 18.2. Return Data Should Use a DTO

```java
public record NearbyPickupResponse(
    String pickupId,
    String name,
    double distanceMeters,
    double distanceKm
) {}
```

Never return a raw `Document` directly from a public API; it could expose internal fields like tenant ID, location metadata, or confidential details. Map/whitelist into a DTO and convert units once.

### 18.3. Converting from BSON to DTO

```java
private NearbyPickupResponse toResponse(Document row) {
    Object raw = row.get("distanceMeters");
    if (!(raw instanceof Number number)) {
        throw new IllegalStateException(
            "Missing numeric distanceMeters"
        );
    }
    double meters = number.doubleValue();
    if (!Double.isFinite(meters) || meters < 0) {
        throw new IllegalStateException(
            "Invalid distance from MongoDB"
        );
    }
    return new NearbyPickupResponse(
        row.getString("_id"),
        row.getString("name"),
        meters,
        meters / 1000.0
    );
}
```

Place this method in a gateway/mapper class with appropriate imports. If the ID is not a String (e.g., BSON ObjectId), convert the type properly. Never cast directly to `Double` when the driver can return other `Number` subtypes.

### 18.4. `distanceField` and Server Versions

MongoDB 8.1 and later may allow omitting `distanceField` in some `$geoNear` queries on regular collections, but **pass `distanceField` explicitly in this lesson** to maintain the output contract and cross-version compatibility. Never treat an optional property as a reason to drop unit naming.

### 18.5. Limiting Result Count

`Aggregation.limit(20)` after `$geoNear` caps the returned documents. The server still performs geo index traversal and query filtering; a limit does not fix a missing index or unbounded radius. Choose radius caps and page/limit sizes according to the workload.

## 19. Distance-Based Repository Derived Queries

### 19.1. Interface

```java
package com.example.geo.persistence;

import java.util.List;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface PickupRepository
        extends MongoRepository<PickupPoint, String> {

    List<PickupPoint> findByLocationNear(
        Point origin,
        Distance maxDistance
    );

    List<PickupPoint> findByTenantIdAndActiveTrue(
        String tenantId
    );
}
```

`findByLocationNear(Point, Distance)` is a derived geospatial method. Spring Data picks the operator and converts the metric based on argument/index metadata. If the repository API must enforce tenant/active filtering **in the same geo query**, write a fully tested derived query or use explicit `MongoOperations`/aggregation as in section 18—never fetch all geospatial results and filter tenant in Java.

### 19.2. Calling with Legacy `Point` and `Distance` Metric

```java
List<PickupPoint> nearby = repository.findByLocationNear(
    new Point(106.7000, 10.7800),
    new Distance(2, Metrics.KILOMETERS)
);
```

This method can render a spherical operator with bounds converted from km by Spring Data. Do not multiply by 1000 inside `Distance(2, Metrics.KILOMETERS)`.

### 19.3. Calling with `GeoJsonPoint` and Neutral Metric

```java
List<PickupPoint> nearbyGeoJson =
    repository.findByLocationNear(
        new GeoJsonPoint(106.7000, 10.7800),
        new Distance(2000, Metrics.NEUTRAL)
    );
```

Here the goal is to pass **2,000 numeric native units** for GeoJSON = meters. Verify the actual rendered BSON in your Spring Data version. If a derived query generates unexpected output/limits, switch to explicit aggregation for critical contracts.

### 19.4. Repository Returning Entities vs Returning Distances

`List<PickupPoint>` gives the points, but does not automatically provide a computed `distanceMeters` field. Spring Data supports `GeoResult<T>`/`GeoResults<T>` return types on supported derived geospatial queries, though behavior and reactive support differ. For APIs that must return both distances and units, `$geoNear` with an explicit `distanceField` is easier to control.

### 19.5. Do Not Filter Tenant After the Geo Query

```java
// Avoid: fetch all tenants then filter in Java.
// repository.findByLocationNear(...).stream()
//     .filter(p -> p.tenantId().equals(authenticatedTenant))
//     .toList();
```

The tenant predicate from the authentication context must be included in the query sent to MongoDB.

## 20. `ReactiveMongoOperations` and Distances

### 20.1. Reactive Aggregation Returning `Flux`

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.ReactiveMongoOperations;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.NearQuery;
import reactor.core.publisher.Flux;

TypedAggregation<PickupPoint> aggregate =
    Aggregation.newAggregation(
        PickupPoint.class,
        Aggregation.geoNear(
            NearQuery.near(
                new GeoJsonPoint(106.7000, 10.7800)
            )
            .maxDistance(2000.0)
            .spherical(true),
            "distanceMeters"
        ),
        Aggregation.limit(20)
    );

Flux<Document> nearby =
    reactiveMongoOperations.aggregate(
        aggregate, Document.class
    );
```

Production code needs tenant/active filters in `NearQuery.query(...)` as in section 18; this snippet only demonstrates the **reactive API shape**. `Flux` executes when subscribed to, not when the variable is constructed.

### 20.2. Legacy Reactive `geoNear` API

```java
// Available in many versions but deprecated:
// Flux<GeoResult<PickupPoint>> rows =
//     reactiveMongoOperations.geoNear(nearQuery, PickupPoint.class);
```

Current Spring Data recommends `Aggregation.geoNear` over the deprecated convenience API. If a legacy project uses the old API, verify `GeoResult.getDistance()` units when upgrading.

### 20.3. Backpressure Does Not Fix Heavy Queries

A `Flux<Document>` does not mean MongoDB does less work. `$geoNear` still needs an index, distance computations, and sorting/filtering. Cap radius, result counts, and concurrent queries, and use `explain` to optimize server-side execution.

### 20.4. Never Call `block()` Inside a WebFlux Handler

```java
// Do not use in a reactive controller:
// List<Document> rows = nearby.collectList().block();
```

Return `Flux` or `Mono<List<DTO>>` when lists are small and bounded; never block the event loop. If using `collectList()`, apply `$limit` in MongoDB aggregation first—never buffer millions of locations in RAM.

## 21. Separating Unit Contracts into a Type-Safe API

Instead of passing a unitless `double radius`, use a wrapper:

```java
package com.example.geo.domain;

public record Meters(double value) {
    public Meters {
        if (!Double.isFinite(value) || value < 0) {
            throw new IllegalArgumentException(
                "Meters must be finite and nonnegative"
            );
        }
    }

    public static Meters fromKilometers(double kilometers) {
        if (!Double.isFinite(kilometers) || kilometers < 0) {
            throw new IllegalArgumentException(
                "Kilometers must be finite and nonnegative"
            );
        }
        return new Meters(kilometers * 1000.0);
    }

    public static Meters fromMiles(double miles) {
        if (!Double.isFinite(miles) || miles < 0) {
            throw new IllegalArgumentException(
                "Miles must be finite and nonnegative"
            );
        }
        return new Meters(miles * 1609.344);
    }

    public double kilometers() {
        return value / 1000.0;
    }

    public double radians(double earthRadiusMeters) {
        if (!Double.isFinite(earthRadiusMeters)
                || earthRadiusMeters <= 0) {
            throw new IllegalArgumentException(
                "Invalid earth radius"
            );
        }
        return value / earthRadiusMeters;
    }
}
```

### 21.1. Example Using the Wrapper

```java
Meters radius = Meters.fromKilometers(2.0);

double forGeoJsonQuery = radius.value(); // 2000 meters
double forCenterSphere = radius.radians(6_378_137.0);

double inKm = new Meters(1250).kilometers(); // 1.25 km
```

For GeoJSON `maxDistance`, use `radius.value()`; for legacy spherical/`$centerSphere`, use `radius.radians(R)`.

### 21.2. A Unit Object Alone Does Not Enforce Business Caps

The wrapper above allows 10 million km as long as it is finite. APIs should enforce a **maximum limit** matching SLOs—for instance, disallowing radii above 100,000 m in pickup-point search. Aviation or geographic research systems need not pick the same limit.

## 22. Validating Longitude, Latitude, and Radius

### 22.1. An Input Validation Helper

```java
package com.example.geo.persistence;

public final class GeoInput {
    private static final double MAX_BUSINESS_RADIUS_METERS =
        100_000.0;

    private GeoInput() {}

    public static void validate(
        String tenantId,
        double longitude,
        double latitude,
        double radiusMeters
    ) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Missing tenant");
        }
        if (!Double.isFinite(longitude)
                || longitude < -180 || longitude > 180) {
            throw new IllegalArgumentException("Invalid longitude");
        }
        if (!Double.isFinite(latitude)
                || latitude < -90 || latitude > 90) {
            throw new IllegalArgumentException("Invalid latitude");
        }
        if (!Double.isFinite(radiusMeters)
                || radiusMeters < 0
                || radiusMeters > MAX_BUSINESS_RADIUS_METERS) {
            throw new IllegalArgumentException("Invalid radius");
        }
    }
}
```

`MAX_BUSINESS_RADIUS_METERS` is an **illustrative application limit**, not a limit on all MongoDB geo queries. Never trust an unauthenticated client-supplied `tenantId`; it must come from the security context.

### 22.2. Blocking `NaN` and `Infinity`

```java
Double.NaN
Double.POSITIVE_INFINITY
Double.NEGATIVE_INFINITY
```

These are not valid radii. Checking only `radius >= 0` may fail to reject NaN if formulated asymmetrically because comparisons with NaN return false; use `Double.isFinite`.

### 22.3. Preventing Overflow After Conversion

```java
Meters.fromKilometers(Double.MAX_VALUE)
```

Multiplication can overflow to Infinity, which the `Meters` constructor rejects. In production, validate business limits on the raw input before multiplying so you return clearer errors and avoid massive search ranges.

### 22.4. Distinguishing Coordinate Values and Radius Values

`longitude = 106.7` is a valid longitude. Yet `radiusMeters = 106.7` means **106.7 meters** when internal APIs use meters. A number only has meaning when paired with its unit and field name.

## 23. Designing an API from Kilometers to Meters and Back

Suppose a REST endpoint receives:

```http
GET /api/pickup-points/nearby?longitude=106.70&latitude=10.78&radiusKm=2
```

This is only an example endpoint, not a live request. A good contract explicitly states:

| Field | Unit | Validation |
| --- | --- | --- |
| `longitude` | Degrees (°) | Finite, from -180 to 180 |
| `latitude` | Degrees (°) | Finite, from -90 to 90 |
| `radiusKm` | Kilometers | Finite, non-negative, below business cap |
| Returned `distanceMeters` | Meters | Non-negative, finite number |
| Returned `distanceKm` | Kilometers | `distanceMeters / 1000` |
| Internal `tenantId` | Not a unit of measurement | Obtained from authentication, never client-controlled |

### 23.1. Placing Conversion at a Single Boundary

```java
public record NearbyRequest(
    double longitude,
    double latitude,
    double radiusKm
) {
    public Meters toRadiusMeters() {
        Meters result = Meters.fromKilometers(radiusKm);
        if (result.value() > 100_000.0) {
            throw new IllegalArgumentException(
                "Radius too large"
            );
        }
        return result;
    }
}
```

In real code, `Meters` resides in the domain package and must be imported. The controller converts `radiusKm` to `Meters` **once** before calling the persistence adapter.

### 23.2. Avoid Ambiguous Field Names

```json
{
  "pickupId": "p-b",
  "distanceMeters": 1093.4,
  "distanceKm": 1.0934
}
```

The numbers in this example illustrate the JSON contract, **not real measured route distances**. A user-facing UI can display `1.09 km` while keeping the raw numeric distance internally for sorting/filtering.

### 23.3. Round Only at the Final Step

```java
double displayKm =
    Math.round(distanceMeters / 1000.0 * 100.0) / 100.0;
```

Round only for display; **never use a rounded `displayKm`** to decide whether a point lies inside or outside the radius. For example, 2.004 km rounds to 2.00 km, yet still lies **outside a 2,000 m radius**.

### 23.4. Do Not Trust Client-Supplied Distances

If a client also sends `distanceKm: 0.1` to self-rank, never treat it as proof of actual distance. The server must compute/verify from coordinates and source data per query policy; for decisions with financial impact, consider anti-spoofing and GPS accuracy.

## 24. Haversine for Sanity-Checking, Not Replacing MongoDB

To verify order-of-magnitude distances outside the database, you can use the Haversine formula between two longitude/latitude points on a sphere of radius R:

\[
\begin{aligned}
\Delta\varphi &= \varphi_2-\varphi_1,\\
\Delta\lambda &= \lambda_2-\lambda_1,\\
a &= \sin^2\left(\frac{\Delta\varphi}{2}\right)
 + \cos\varphi_1\cos\varphi_2
\sin^2\left(\frac{\Delta\lambda}{2}\right),\\
d &= 2R\arcsin\left(\sqrt{a}\right).
\end{aligned}
\]

Where `φ` is latitude and `λ` is longitude **converted to radians for trigonometric functions**, while GeoJSON points sent to MongoDB remain in degrees.

### 24.1. Java Reference Implementation

```java
package com.example.geo.domain;

public final class SphericalDistance {
    public static final double EARTH_RADIUS_METERS =
        6_378_137.0;

    private SphericalDistance() {}

    public static double haversineMeters(
        double lon1, double lat1,
        double lon2, double lat2
    ) {
        requireCoordinate(lon1, lat1);
        requireCoordinate(lon2, lat2);

        double phi1 = Math.toRadians(lat1);
        double phi2 = Math.toRadians(lat2);
        double deltaPhi = Math.toRadians(lat2 - lat1);
        double deltaLambda = Math.toRadians(lon2 - lon1);

        double sinPhi = Math.sin(deltaPhi / 2);
        double sinLambda = Math.sin(deltaLambda / 2);
        double a = sinPhi * sinPhi
            + Math.cos(phi1) * Math.cos(phi2)
            * sinLambda * sinLambda;

        // Clamp against floating-point error near 0 or 1.
        double clamped = Math.min(1.0, Math.max(0.0, a));
        return 2 * EARTH_RADIUS_METERS
            * Math.asin(Math.sqrt(clamped));
    }

    private static void requireCoordinate(
        double longitude, double latitude
    ) {
        if (!Double.isFinite(longitude)
                || !Double.isFinite(latitude)
                || longitude < -180 || longitude > 180
                || latitude < -90 || latitude > 90) {
            throw new IllegalArgumentException(
                "Invalid geographic coordinate"
            );
        }
    }
}
```

### 24.2. What Haversine Does Not Prove

- It does not tell you whether a MongoDB index was used.
- It does not verify `$geoNear` maxDistance/multiplier rendering.
- It does not give driving distance.
- It does not model altitude/terrain or ellipsoid geodesic effects.
- It does not verify tenant, active, authorization, or result-limit query filters.

It is only a **reference sanity check** in tests. For points right near the 2,000 m boundary, small differences can arise from radius models, floating-point math, or MongoDB's geometry handling. Avoid overly strict equality assertions.

### 24.3. Checking Two Simple Cases

```java
double same = SphericalDistance.haversineMeters(
    106.7, 10.78,
    106.7, 10.78
);

double nearby = SphericalDistance.haversineMeters(
    106.7, 10.78,
    106.71, 10.78
);

// same ≈ 0 meters; nearby is roughly over 1 km.
```

Do not hardcode "two longitudes differing by 0.01° are always exactly 1.1 km apart" across all latitudes.

## 25. Precision, Radius Boundaries, and Real-World Measurements

### 25.1. A 2 km Filter Differs from Display Distance

Suppose two candidates have distances:

```text
Candidate A: 1_999.96 m
Candidate B: 2_000.04 m
```

With `$maxDistance: 2000`, MongoDB filters by server-computed distance, not the UI's rounded `2.00 km` label. In tests, pick points **clearly inside and clearly outside** the boundary so tests are not overly sensitive to numerical tolerances.

### 25.2. GPS Has Finite Accuracy

A device may report an accuracy radius of tens of meters or more. MongoDB does not know how trustworthy each coordinate is unless the document stores metadata. For location-dependent systems, consider:

- Timestamp when the coordinate was measured.
- Device accuracy/uncertainty.
- Time since last update.
- Whether the user granted location permission.
- Business rules when a point lies near a threshold.

### 25.3. Coordinates Near the ±180° Meridian

At the anti-meridian, the ground distance between `+180°` and `-180°` longitude can be tiny even though arithmetic subtraction is nearly 360°. Never compute distance with `abs(lon1-lon2)`. Use proper geospatial operators and spherical math.

### 25.4. Latitudes Near ±90°

Near the poles, the ground length of one degree of longitude differs dramatically from the equator. Fixed-degree bounding boxes fail here; test edge cases if your data spans the globe.

### 25.5. Altitude

MongoDB `2dsphere` generally evaluates surface geography on a sphere rather than 3D distance using altitude. If a drone or multi-floor indoor app needs elevation, design an explicit model rather than assuming a third GeoJSON coordinate triggers 3D distance queries.

## 26. Indexes, `explain`, and Performance Limits

### 26.1. Viewing Existing Indexes

```javascript
db.pickup_points.getIndexes();
```

Confirm the exact field/type `location: "2dsphere"`, not just that documents contain GeoJSON.

### 26.2. Explaining a `$geoNear` Aggregation

```javascript
db.pickup_points.explain("executionStats").aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      key: "location",
      spherical: true,
      maxDistance: 2000,
      distanceField: "distanceMeters",
      query: {
        tenantId: "tenant-a",
        active: true
      }
    }
  },
  { $limit: 20 }
]);
```

Look for plan/index indicators such as geospatial index access, keys/documents examined, time spent, and filters not leveraging an index. Stage names and explain structure vary across MongoDB versions/execution engines; never write tests tied to a single fixed stage name.

### 26.3. Compound Geospatial Index

A candidate for a multi-tenant system:

```javascript
db.pickup_points.createIndex(
  { location: "2dsphere", tenantId: 1, active: 1 },
  { name: "ix_geo_tenant_active" }
);
```

Key order and effectiveness depend on query shape, cardinality, active/tenant ratios, and server optimizer version. **Do not** create this index in production just because it looks plausible: measure index size, write cost, and `explain` on representative data.

If the same collection also has a standalone `location: "2dsphere"` index, `$geoNear.key: "location"` specifies the **field**, not necessarily forcing one specific compound index name. The query planner may choose among indexes on that field; inspect the actual plan.

### 26.4. Larger Radius Means More Candidates

```text
radius = 500 m    → usually few candidates
radius = 2 km     → more candidates
radius = 100 km   → potentially very many candidates
```

This is a general geometric trend, not a fixed count. Over roughly uniform distributions on a small plane, area grows approximately with `r²`; doubling the radius can roughly quadruple the search area. Real-world density may be uneven.

### 26.5. Limiting and Projection

After `$geoNear`, add a reasonable `$limit` and `$project` only the fields actually needed:

```javascript
{ $limit: 20 },
{
  $project: {
    _id: 1,
    name: 1,
    distanceMeters: 1
  }
}
```

Never expose full address details, owners, internal notes, or sensitive coordinates belonging to other tenants.

### 26.6. Re-Sorting Can Break Nearest-First Ordering

`$geoNear` returns points from nearest to farthest. Adding `$sort: { name: 1 }` afterward changes the ordering to alphabetical by name, no longer "nearest". If you need a deterministic tie-breaker or multi-factor ranking, document those criteria in the API contract.

## 27. Geospatial Search, Authorization, and Data Consistency

### 27.1. Place Tenant Filters in Server-Side Queries

```javascript
query: {
  tenantId: "tenant-a",
  active: true
}
```

Never compute distances for all points and filter tenants on the client; returning distances or even existence of forbidden locations is a data leak.

### 27.2. Point Locations Can Change

A pickup point can relocate between two queries. Therefore, a "1.2 km" result is a snapshot at query time, not a permanent guarantee. For order scheduling workflows, verify the point is still active, has a valid address, and has capacity at **confirmation time**, rather than trusting a potentially stale geospatial search result.

### 27.3. Read Preference and Replica Lag

When reading from secondaries, locations or active status may lag behind the primary. That affects result freshness even when units are correct. Distinguish **unit bugs** (logic errors) from **stale reads** (consistency policy) and **bad geocodes** (data quality).

### 27.4. Location and Privacy

User coordinates can be sensitive data. Avoid logging raw lon/lat alongside personal identifiers when unnecessary; constrain retention, authorization, precision, and usage per applicable policy. Never allow debugging endpoints to leak another tenant's locations.

## 28. Unit Tests for Conversions

Unit tests prove multiplication/division logic works without needing MongoDB. They **do not** prove queries use indexes or follow server semantics.

### 28.1. JUnit 5 for km, Miles, and Radians

```java
package com.example.geo.domain;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class MetersTest {
    private static final double EARTH_R =
        6_378_137.0;

    @Test
    void kilometersConvertToMeters() {
        Meters d = Meters.fromKilometers(2.0);
        assertEquals(2000.0, d.value(), 1e-9);
        assertEquals(2.0, d.kilometers(), 1e-12);
    }

    @Test
    void milesConvertToMeters() {
        Meters d = Meters.fromMiles(5.0);
        assertEquals(8046.72, d.value(), 1e-8);
    }

    @Test
    void radiansRoundTripWithChosenEarthRadius() {
        Meters d = new Meters(2000.0);
        double radians = d.radians(EARTH_R);
        assertEquals(
            2000.0,
            radians * EARTH_R,
            1e-9
        );
    }

    @Test
    void rejectsNaNAndInfiniteDistance() {
        assertThrows(
            IllegalArgumentException.class,
            () -> new Meters(Double.NaN)
        );
        assertThrows(
            IllegalArgumentException.class,
            () -> Meters.fromKilometers(Double.POSITIVE_INFINITY)
        );
    }

    @Test
    void rejectsNegativeDistance() {
        assertThrows(
            IllegalArgumentException.class,
            () -> Meters.fromKilometers(-1)
        );
    }
}
```

### 28.2. `GeoInput` Unit Tests

```java
@Test
void invalidLatitudeIsRejected() {
    assertThrows(
        IllegalArgumentException.class,
        () -> GeoInput.validate(
            "tenant-a", 106.7, 106.7, 2000
        )
    );
}

@Test
void validCoordinatesAndTwoKmPass() {
    assertDoesNotThrow(
        () -> GeoInput.validate(
            "tenant-a", 106.7, 10.78, 2000
        )
    );
}
```

Put both methods inside a test class with appropriate JUnit/`GeoInput` imports. Note that bounds checks do not catch **every** swapped lon/lat: if both numbers lie in valid ranges, wrong order passes validation. Use contracts, clear naming, and semantic test fixtures.

### 28.3. Haversine Sanity Check

```java
@Test
void nearbyPointIsRoughlyOneKilometerAway() {
    double meters = SphericalDistance.haversineMeters(
        106.7000, 10.7800,
        106.7100, 10.7800
    );

    assertTrue(meters > 1000.0);
    assertTrue(meters < 1200.0);
}
```

The test uses a wide tolerance to check **order of magnitude**, avoiding brittle exact-digit matching against MongoDB algorithms using different radii/ellipsoids.

### 28.4. Never Scale Coordinates Like Distances

```java
// WRONG:
// new GeoJsonPoint(longitude * 1000, latitude * 1000)

// RIGHT:
new GeoJsonPoint(longitude, latitude);
```

Coordinates remain in degrees; only radius/distance values undergo unit conversion.

## 29. MongoDB Integration Tests: Catching Unit Bugs in the Database

To prove query units, you must run against real MongoDB in a test environment rather than only mocking `MongoOperations`. The example below uses MongoDB Testcontainers and Spring Boot 3.x; on Spring Boot 4.x, select the matching test starter and URI property.

### 29.1. Test Dependencies

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>mongodb</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
```

Testcontainers 2.x may use different artifact/module names than this example. Use verified Spring Boot BOM/parent and test dependency versions. Run Docker/Testcontainers only in authorized environments; never run suites containing `drop()` against production.

### 29.2. Test Fixture with Three Distances and Another Tenant

```java
package com.example.geo;

import static org.junit.jupiter.api.Assertions.*;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class GeoDistanceMongoIntegrationTest {

    @Container
    static MongoDBContainer mongo =
        new MongoDBContainer("mongo:7.0");

    @DynamicPropertySource
    static void mongoConfig(DynamicPropertyRegistry registry) {
        // Spring Boot 3.x:
        registry.add(
            "spring.data.mongodb.uri",
            mongo::getReplicaSetUrl
        );
        // Spring Boot 4.x: spring.mongodb.uri
    }

    @Autowired MongoOperations template;

    @BeforeEach
    void seed() {
        var col = template.getCollection("pickup_points");
        col.drop(); // ONLY in an isolated test database
        col.createIndex(new Document("location", "2dsphere"));

        col.insertMany(List.of(
            place("inside", "tenant-a", 106.7000, 10.7800),
            place("nearby", "tenant-a", 106.7100, 10.7800),
            place("outside", "tenant-a", 106.7500, 10.8000),
            place("foreign", "tenant-b", 106.7001, 10.7801)
        ));
    }

    private Document place(
        String id, String tenant,
        double longitude, double latitude
    ) {
        return new Document("_id", id)
            .append("tenantId", tenant)
            .append("active", true)
            .append("location", new Document("type", "Point")
                .append(
                    "coordinates", List.of(longitude, latitude)
                ));
    }

    private List<Document> query(Double multiplier) {
        Document geo = new Document(
            "near",
            new Document("type", "Point")
                .append(
                    "coordinates", List.of(106.7000, 10.7800)
                )
        )
        .append("key", "location")
        .append("spherical", true)
        .append("maxDistance", 2000.0)
        .append("distanceField",
            multiplier == null ? "distanceMeters" : "distanceKm")
        .append("query",
            new Document("tenantId", "tenant-a"));

        if (multiplier != null) {
            geo.append("distanceMultiplier", multiplier);
        }

        return template.getCollection("pickup_points")
            .aggregate(List.of(
                new Document("$geoNear", geo),
                new Document("$limit", 20)
            ))
            .into(new ArrayList<>());
    }

    @Test
    void twoKmIncludesInsideAndNearbyOnly() {
        List<Document> results = query(null);
        Set<String> ids = results.stream()
            .map(row -> row.getString("_id"))
            .collect(Collectors.toSet());

        assertEquals(Set.of("inside", "nearby"), ids);
    }

    @Test
    void multiplierChangesOutputButNotMatchingIds() {
        List<Document> meters = query(null);
        List<Document> kilometers = query(0.001);

        Set<String> meterIds = meters.stream()
            .map(d -> d.getString("_id"))
            .collect(Collectors.toSet());
        Set<String> kmIds = kilometers.stream()
            .map(d -> d.getString("_id"))
            .collect(Collectors.toSet());
        assertEquals(meterIds, kmIds);

        Document raw = meters.stream()
            .filter(d -> d.getString("_id").equals("nearby"))
            .findFirst().orElseThrow();
        Document converted = kilometers.stream()
            .filter(d -> d.getString("_id").equals("nearby"))
            .findFirst().orElseThrow();

        double rawMeters =
            ((Number) raw.get("distanceMeters")).doubleValue();
        double km =
            ((Number) converted.get("distanceKm")).doubleValue();

        assertEquals(rawMeters / 1000.0, km, 1e-6);
    }
}
```

This is an **integration test skeleton compatible with Spring Boot 3/Testcontainers APIs**, needing build config/component scanning tailored to your real project. In the example, JUnit, Spring Boot MongoDB starter, and the MongoDB container are configured in test scope; never use production fixtures. Points outside the radius, same tenant, and foreign tenant catch both unit errors and tenant leaks.

### 29.3. Why Test with Raw `Document`?

The test above intentionally uses raw BSON for `$geoNear` to verify **MongoDB's semantics** without `NearQuery` transforming metrics. Afterward, add a **Spring Data aggregation** test with the same fixtures to verify generated stages and DTO mapping.

### 29.4. Regression Test Comparing GeoJSON and Legacy

A good regression test:

1. Query GeoJSON `near: {type:"Point",coordinates:[...]}` with `maxDistance=2000`, raw meters result.
2. Query legacy `near: [lon,lat]`, `spherical:true` with `maxDistance=2000/R` and `distanceMultiplier=R/1000`, kilometers result.
3. Compare ID sets and compare distances after converting both to meters.
4. Use reasonable tolerance since distance models may differ slightly.

If testing against the same `2dsphere` field storing GeoJSON, confirm your server version supports legacy input queries as documented. Never assume two representations produce **bitwise identical ordered outputs** when metrics change.

### 29.5. Testing Missing/Invalid Indexes

Before index migration/provisioning, a `$geoNear` requiring a geospatial index can error. Test using a temporary collection in a test database without dropping production indexes. Assert the failure surfaces clearly in monitoring/health checks rather than silently turning into an empty "no points found" result.

### 29.6. Reactive Integration Test

```java
Flux<Document> stream = reactiveMongoOperations.aggregate(
    geoAggregation, Document.class
);

StepVerifier.create(stream)
    .expectNextCount(2)
    .verifyComplete();
```

`geoAggregation` here is a `TypedAggregation<PickupPoint>` like section 20, **with a tenant filter and test fixtures** ensuring exactly two results; add Reactor/`StepVerifier` imports and a reactive test context. Creating a `Flux` without subscribing does not prove the query ran.

### 29.7. One Test Suite Should Prove Both Units and Tenant Isolation

If a geospatial test also returns `foreign`, that is an access-control failure even when distances are right. If it returns `outside` because radius 2 was treated as 2 radians, that is a unit bug. Separate assertions so you can pinpoint the exact root cause.

## 30. Common Mistakes When Converting Units

| Symptom | Typical Cause | How to Fix |
| --- | --- | --- |
| 2 km radius returns almost no points | Passed `maxDistance: 2` for GeoJSON | Convert to 2000 m |
| 2 km radius returns very distant points | Passed 2 for legacy spherical (radians) | Use `2000 / R_METERS` |
| GeoJSON result is 1200 but UI shows 1200 km | Mistook raw meters for km | Raw GeoJSON output is in meters |
| Legacy result is `0.0002` but UI shows 0.0002 km | Mistook raw radians for km | Multiply by Earth radius in km |
| `distanceMultiplier: 6378.137` produces huge outputs | Used legacy multiplier with GeoJSON meters | GeoJSON m → km uses `0.001` |
| `distanceMultiplier: 0.001` still filters wrong | Believed multiplier converts `maxDistance` | Convert query radius separately |
| UI shows distances 1000x too small | Divided by 1000 in both MongoDB and Java | Convert units only once |
| Points appear in strange locations | Swapped longitude and latitude | GeoJSON is `[longitude, latitude]` |
| GeoJSON cannot find index | Used `2d` index on an incompatible field | Use `2dsphere` on the GeoJSON field |
| Legacy query misinterpreted after changing import | Replaced `Point` with `GeoJsonPoint` | Regression-test generated BSON/units |
| `$centerSphere` filters way too broadly | Passed radius in meters instead of radians | Divide by Earth radius |
| `$geoNear` aggregation errors on stage position | Put `$match` before `$geoNear` | Put `$geoNear` first, use `query` |
| `$geoNear` picks wrong geospatial field | Multiple indexes without `key` | Specify `key` explicitly |
| Results carry unexpected units | Metric in `NearQuery` differs from assumption | Check query metric/BSON/result |
| `maxDistance` evaluated in miles | Client sent miles, adapter assumed km | Unit-explicit API contract and validation |
| Boundary test flakes pass/fail | Point right on threshold, model rounding | Pick points away from threshold and use tolerance |
| Both show 2.00 km yet one is excluded | Rounded before filtering | Filter on raw numeric distance |
| Huge radius slows query down | Missing business cap | Limit radius, results, and concurrency |
| Query returns another tenant's locations | Filtered tenant after query | Move tenant predicate into server query |
| GeoJSON gives tiny distances at high latitudes | Took degree differences directly | Use geo operators or proper Haversine |
| Expected driving time from `$geoNear` | Confused spherical distance with road route | Use a routing/travel-time service |
| Reactive endpoint returns empty despite valid query | Never subscribed to `Flux`/`Mono` | Compose and let framework subscribe |
| Backend lacks metric validation | Allowed `NaN`/`Infinity` | Use `Double.isFinite` and bounds |
| Nearest order changed after migration | Changed near geometry or sort stage | Verify semantics + regression suite |
| Output uses wrong unit relative to field name | Named `distanceKm` while raw stays meters | Rename/convert and add contract tests |
| Location cache is stale | Lagging Redis/read model | Freshness policy and invalidation |
| Huge index / slow writes after adding geo index | Added index without benchmarking | Explain, size, write p95/p99, rollout |
| Wrong results near poles/anti-meridian | Used Euclidean approximation on degrees | Use appropriate geometry/coordinate system |

### 30.1. Step-by-Step Diagnostic Workflow

```text
1. Which unit does the API accept for radius (m/km/mi)?
                  ↓
2. Is the origin a GeoJSON Point [lon,lat] or legacy pair?
                  ↓
3. Using $near, $nearSphere, $geoNear, or $centerSphere?
                  ↓
4. Does the MongoDB command have maxDistance/minDistance in the right unit?
                  ↓
5. If $geoNear: what is distanceMultiplier?
                  ↓
6. Is the result field named/converted to the right unit?
                  ↓
7. Does a 2dsphere/2d index exist on the exact field for the query?
                  ↓
8. Are tenant/active filter, limit, and projection right?
                  ↓
9. Inspect actual BSON and explain on test MongoDB.
                  ↓
10. Regression test points inside/outside radius and legacy/GeoJSON.
```

### 30.2. Diagnosing Using a Point at a Known Distance

If a fixture is expected to be ~1 km away yet MongoDB returns `0.001`, first ask **what the unit is**. It could represent 0.001 rad (≈6.4 km) or 0.001 km (1 m)—totally different values. Never try to "fix" it with a random multiplier until you confirm both the near point representation and output unit.

## 31. Worked Practice Exercises

### Exercise 1 — Converting a 2 km Radius for GeoJSON

**Prompt:** Client sends `radiusKm = 2`, MongoDB uses `$near` with a GeoJSON Point. What value goes into `$maxDistance`?

**Solution:** `2 * 1000 = 2000` meters.

```javascript
{
  $near: {
    $geometry: {
      type: "Point",
      coordinates: [106.7000, 10.7800]
    },
    $maxDistance: 2000
  }
}
```

### Exercise 2 — Legacy Spherical Requires Radians

**Prompt:** For the same 2 km, build `$maxDistance` for legacy `$nearSphere`.

**Solution:** Using reference radius `R = 6_378_137 m`:

```javascript
const radiusRadians = 2000 / 6378137;
```

The value is approximately `0.000313571 rad`, **not** 2 or 2000.

### Exercise 3 — `$centerSphere` with GeoJSON Stored in the Collection

**Prompt:** Collection stores GeoJSON and has a `2dsphere` index. Using `$geoWithin/$centerSphere` to search within 2 km, is radius in meters or radians?

**Solution:** Radius in `$centerSphere` is always **radians** in this example:

```javascript
db.pickup_points.find({
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.7000, 10.7800],
        2000 / 6378137
      ]
    }
  }
});
```

Never write `$centerSphere: [[lon,lat], 2000]`.

### Exercise 4 — GeoJSON `$geoNear` Returning km

**Prompt:** Filter within 3 km and output distance in km.

**Solution:**

```javascript
{
  $geoNear: {
    near: {
      type: "Point",
      coordinates: [106.7, 10.78]
    },
    key: "location",
    spherical: true,
    maxDistance: 3000,
    distanceMultiplier: 0.001,
    distanceField: "distanceKm"
  }
}
```

`maxDistance` remains 3000 m, while output is divided by 1000.

### Exercise 5 — GeoJSON `$geoNear` Returning Miles

**Prompt:** Given a 5-mile radius, output `distanceMiles`.

**Solution:**

```javascript
{
  maxDistance: 5 * 1609.344,
  distanceMultiplier: 1 / 1609.344,
  distanceField: "distanceMiles"
}
```

These are the additional fields for GeoJSON `$geoNear` from Exercise 4. Input radius equals `8046.72 m`; output converts meters to miles.

### Exercise 6 — Legacy `$geoNear` in km

**Prompt:** Legacy `near: [lon,lat]` running spherical, `maxDistance` needs 10 km, output needs km. Choose both factors.

**Solution:**

```javascript
maxDistance: 10000 / 6378137,
distanceMultiplier: 6378.137
```

The filter bound is radians and the output factor is km/radian. Do not swap the two factors.

### Exercise 7 — Does `distanceMultiplier` Change Membership?

**Prompt:** A GeoJSON `$geoNear` query has `maxDistance=2000`. If you add `distanceMultiplier=0.001`, will a point 2,500 m away be included?

**Solution:** No. The multiplier only transforms the **returned `distanceField`**; it does not change `maxDistance` from 2000 m to 2000 km. A point at 2500 m remains outside the 2000 m radius.

### Exercise 8 — `Point` vs `GeoJsonPoint`

**Prompt:** Two Java objects:

```java
new Point(106.7, 10.78);
new GeoJsonPoint(106.7, 10.78);
```

They represent the same origin, but do they produce the same BSON near query shape?

**Solution:** No. `Point` is typically a legacy pair; `GeoJsonPoint` serializes into a GeoJSON object. In spherical geoNear, that can change native distance units (radians vs meters). Inspect generated BSON and adapter conversions when refactoring.

### Exercise 9 — Spring `Distance` and `Metrics`

**Prompt:** What does `new Distance(10, Metrics.MILES)` mean? Should you call `getValue()` and assume 10 means meters?

**Solution:** The value is **10 miles**, not 10 meters. When passed to `NearQuery`/repositories, Spring Data can convert the metric into the appropriate native bound and output unit. If you extract `getValue()` to serialize, preserve the unit alongside it.

### Exercise 10 — Fixing a Misordered Pipeline

**Prompt:** Code:

```javascript
db.pickup_points.aggregate([
  { $match: { tenantId: "tenant-a" } },
  { $geoNear: { /* geo options */ } }
]);
```

**Solution:** Place `$geoNear` as the first stage, move the tenant predicate into `query` inside `$geoNear` (when supported by collection/operator), then add `$limit` and `$project`. Never place `$match` before `$geoNear`.

### Exercise 11 — Catching Another Tenant Inside the Radius

**Prompt:** The collection contains a `tenant-b` point only a few meters from the origin. Should `tenant-a`'s API return it when the radius is 2 km?

**Solution:** No. Geo queries must include a server-side tenant predicate, e.g., `query: {tenantId:"tenant-a", active:true}`. In tests, assert the exact **ID set**, not just the count. Never filter tenants after retrieving raw results.

### Exercise 12 — Designing a Unit-Conversion Test Suite

**Prompt:** Design tests for migrating from legacy `Point` to `GeoJsonPoint`.

**Solution:** Include (1) fixtures inside/outside the radius; (2) longitude/latitude ordering checks; (3) generated BSON `near` is GeoJSON; (4) `maxDistance` is meters; (5) `distanceMultiplier` produces the right output; (6) comparison between raw MongoDB query and Spring Data aggregation; (7) ID membership matching within tolerance; (8) tenant isolation; (9) index/`explain`; (10) performance under realistic radius/limit; (11) reactive subscription tests if used; (12) regressions for `NaN`/`Infinity`/negative/oversized radii. Never just change an import and rely on one happy-path test.

## 32. Pre-Deployment Technical Checklist

| Review Question | Evidence / How to Verify |
| --- | --- |
| Do API inputs state units explicitly? | `radiusKm`/`radiusMeters`, schema and docs |
| Do API outputs state units explicitly? | `distanceMeters`/`distanceKm`, contract tests |
| Are longitude and latitude in the right order? | Fixtures and `[lon, lat]` validation |
| Can inputs be `NaN`/`Infinity`? | `Double.isFinite` |
| Are longitude/latitude within bounds? | -180..180 / -90..90 |
| Is there a business max radius? | Validation and load tests |
| Is result count capped? | `$limit` / query limit |
| Does the DB store GeoJSON or legacy? | Inspect persisted BSON |
| Is the existing index `2dsphere` or `2d`? | `getIndexes()` and migrations |
| Does the query use `$near`, `$nearSphere`, or `$geoNear`? | Inspect generated BSON |
| Is `$geoNear` the first stage? | Pipeline inspection/tests |
| Are there multiple geospatial indexes? | `key` and `explain` |
| Does GeoJSON `maxDistance` use meters? | Test 2000 m bound |
| Does legacy spherical `maxDistance` use radians? | Conversion test |
| Does `$centerSphere` radius use radians? | Query + boundary tests |
| Do `minDistance` and `maxDistance` share units? | DTO validation, query assertions |
| Is `distanceMultiplier` applied correctly to outputs? | Tests with/without multiplier |
| Are values converted twice anywhere? | Integration + response contract |
| Spring Data `Point` or `GeoJsonPoint`? | Imports, serialized `near` |
| Do `Distance` and `Metrics` keep their units? | `getMetric`/output tests |
| Does code use deprecated `geoNear`? | Prefer `Aggregation.geoNear` |
| Are real repository queries/aggregations tested? | Testcontainers |
| Do read results get post-converted with wrong units? | Raw BSON + DTO readback |
| Is Earth radius constant `R` unified? | Named constant + tolerance |
| Is straight-line distance treated as ETA? | API copy / routing boundary |
| Are anti-meridian/poles tested if global? | Edge fixtures |
| Is overly granular location data retained? | Privacy/security review |
| Is tenant authorization inside the Mongo query? | Cross-tenant test |
| Do caches/read preferences serve stale locations? | Freshness SLO |
| Are index plans and p95/p99 measured under load? | Explain and load tests |
| Is there a migration plan for `Point` → `GeoJsonPoint`? | Pre/post BSON diff |
| Is academic QA performed after writing? | STEP 6 NEW per workflow |

### 32.1. Quick Decision Table

| Input | Goal | Choice |
| --- | --- | --- |
| GeoJSON Point + `2dsphere` | Find nearby points within 2 km | `$near` with `$maxDistance: 2000` |
| GeoJSON Point + `2dsphere` | Also return distance in meters | `$geoNear`, `distanceField`, no multiplier |
| GeoJSON Point + `2dsphere` | Return distance in km | `$geoNear`, `maxDistance` meters, multiplier `0.001` |
| Legacy near spherical | Search within 2 km | `maxDistance = 2000/R_METERS` rad |
| Legacy geoNear spherical | Output km | `distanceMultiplier = R_KILOMETERS` |
| Regardless of GeoJSON/legacy storage | `$centerSphere` circular region | Radius in radians |
| Spring Data with `GeoJsonPoint` | Explicit meter bound | `NearQuery.near(GeoJsonPoint).maxDistance(meters)` |
| Spring Data with legacy `Point` | Km bound via metric | `Distance(km, Metrics.KILOMETERS)` |
| Service needs driving distance | ETA/road km | Geospatial filters candidates, routing handles the rest |

### 32.2. Change Only One Variable at a Time When Debugging

If a query returns wrong results, do not simultaneously switch `Point -> GeoJsonPoint`, switch index `2d -> 2dsphere`, and add a multiplier, leaving you unsure which change fixed it. Keep fixtures and queries explicit, checking one step at a time:

1. Data/coordinate order.
2. Index and geometry representation.
3. `maxDistance` and raw result unit.
4. `distanceMultiplier`.
5. Spring Data serialization.
6. DTO/HTTP response unit.

### 32.3. Do Not Use a Map Screenshot to Prove Precision

Maps may display rounded coordinates or projection effects. Test using raw numeric values and fixtures inside/outside the radius, then use the map UI to verify user experience. Never treat a circle drawn on a map as proof that every query uses the same units.

## 33. Official References

Documents to cross-check against the exact MongoDB Server and Spring Data MongoDB versions you run:

- MongoDB — [`$near` operator](https://www.mongodb.com/docs/manual/reference/operator/query/near/): GeoJSON longitude/latitude rules, geospatial indexes, and `$minDistance`/`$maxDistance` units.
- MongoDB — [`$nearSphere` operator](https://www.mongodb.com/docs/manual/reference/operator/query/nearsphere/): difference between GeoJSON meters and legacy radians.
- MongoDB — [`$geoNear` aggregation stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/geonear/): `distanceField`, `distanceMultiplier`, `maxDistance`, `key`, stage ordering, and version behavior.
- MongoDB — [`$centerSphere`](https://www.mongodb.com/docs/manual/reference/operator/query/centersphere/): radius in radians.
- MongoDB — [Convert Distance to Radians](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2d/calculate-distances/): distance / Earth radius formula.
- MongoDB — [2dsphere Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/): spherical geospatial index characteristics.
- Spring Data MongoDB — [Querying Documents / Metrics and Distance Calculation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): comparing `Point`, `GeoJsonPoint`, and `NearQuery`.
- Spring Data MongoDB — [NearQuery API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/query/NearQuery.html): builder, metric conversion, and result units.
- Spring Data MongoDB — [Repository Geo-spatial Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): derived Near methods and return types.
- Spring Data MongoDB — [MongoOperations API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/MongoOperations.html): deprecation note on `geoNear(...)`.
- Spring Data MongoDB — [ReactiveMongoOperations API](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/ReactiveMongoOperations.html): aggregation options for reactive access.
- Testcontainers — [MongoDB module](https://java.testcontainers.org/modules/databases/mongodb/): setting up compatible test databases.

### 33.1. Version Notes

- MongoDB 4.2 removed the legacy `geoNear` command; Spring Data's `geoNear(...)` compatibility API uses aggregation, is deprecated, and recommends `Aggregation.geoNear`.
- MongoDB 7.2 allows certain constant expressions in `$geoNear.maxDistance`/`minDistance`; examples in this lesson always use numeric literals for broad cross-version compatibility.
- MongoDB 8.0 more strictly validates `type: "Point"` for GeoJSON near inputs; always pass a valid GeoJSON Point.
- MongoDB 8.1 may allow omitting `distanceField` on some regular collections, but this lesson keeps declaring it to preserve the output contract.
- Spring Data `NearQuery.maxDistance(double)` interprets the number in any metric previously attached; **never mix pre-normalized meter values with an unintended `KILOMETERS` metric**.

Do not assume newer database/driver changes without checking release notes. Whenever upgrading Spring Boot/Spring Data or MongoDB Server, re-run integration tests covering units and query plans.

## 34. Summary: Every Distance Must Carry Its Unit

1. **GeoJSON Points hold longitude/latitude in degrees**, not meters or radians. The order is `[longitude, latitude]`.
2. **GeoJSON `$near`, `$nearSphere`, and `$geoNear`** take radii/limits in **meters** in the geographic examples covered.
3. **Legacy spherical queries** can take bounds and return raw distances in **radians**, requiring `distance / Earth radius`.
4. **`$centerSphere` always uses radian radii** inside `$geoWithin`, even when stored data is GeoJSON.
5. **`distanceMultiplier` only multiplies `$geoNear` output distances**; it does not convert `maxDistance`. For raw GeoJSON meters wanting km output, use multiplier `0.001`.
6. **Spring Data `Point` and `GeoJsonPoint` differ in serialization/units** in geospatial queries; use and test `Distance`/`Metrics` consistently.
7. **Prefer `Aggregation.geoNear` for new code**, keep `distanceField` named with its unit, and cap result counts explicitly.
8. **Type-safe `Meters` wrappers, unit-named DTOs, and input validation** prevent 1000x scaling errors, miles-to-meters bugs, or double conversions.
9. **`2dsphere` indexes, tenant filters, limits, and `explain`** protect performance and access control; right units alone do not fix bad query plans.
10. **Test on real MongoDB** with fixtures inside/outside the radius, comparing membership and distance outputs before/after multipliers; pure unit tests do not replace integration tests.
11. Geospatial query distance is **straight-line geometric distance**, not ETA, driving route distance, or absolute GPS accuracy.

**Conclusion:** To build a reliable "find within 2 km" API, do not simply pass a bare number `2`. Explicitly define the coordinate representation, GeoJSON vs legacy form, radius unit before calling MongoDB, output distance multiplier, and response unit—and verify everything with integration tests and `explain`. That is the foundation for accurate, verifiable, and maintainable geospatial search in Spring Data MongoDB.






