# Distance, Measurement Units, and Geographic Boundary Handling in MongoDB

A delivery system wants to find pickup points within a 500-meter radius; a fleet management app needs to determine whether a vehicle has entered or left an authorized zone; a disaster monitoring tool must know which routes intersect a flooded area. All three are **geospatial data problems**, yet they ask different questions:

- **Distance:** Which objects are near a location and how many meters away?
- **Containment:** Which points or geometries lie inside a region?
- **Intersection:** Which lines, points, or polygons cross or touch another geometry?

MongoDB supports these questions via **GeoJSON**, **`2dsphere`** indexes, and the operators `$near`, `$nearSphere`, `$geoNear`, `$geoWithin`, and `$geoIntersects`. However, the most dangerous mistake is usually not syntax: it is **confusing longitude/latitude (degrees) with distance (meters), or confusing angular radius (radians) with meters**. A single unit error can cause an application to select locations thousands of kilometers away instead of 500 meters.

Boundaries also involve many tricky scenarios: points hovering near a polygon edge, regions with holes, two overlapping zones, the ±180° antimeridian, near-polar regions, 20 m GPS error, or swapped coordinate order. The database executes geometric operations, while the application must define the **business meaning of inside, outside, and uncertain**.

This lesson belongs to the **Geospatial Data** chapter of the *Database Engine Document MongoDB* module. Examples use **mongosh**, plus **Node.js** and **MongoDB Java Driver** samples. The coordinate set around 106.7° East, 10.78° North is completely **simulated** and does not describe real stores, delivery zones, or legal boundaries. When deploying, check your MongoDB/driver version and the requirements of your official geometry source.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Write properly structured GeoJSON with **[longitude, latitude]** order and the WGS84 reference system.
2. Distinguish meters, kilometers, degrees, and radians, and know when to convert between them.
3. Choose `2dsphere` for GPS coordinates instead of mistakenly using planar `2d`.
4. Find nearest points with `$near` or `$nearSphere`, understanding `$minDistance` and `$maxDistance`.
5. Use `$geoNear` to return a distance field and `distanceMultiplier` to convert display units.
6. Build circular queries using `$geoWithin + $centerSphere` with radius in **radians**.
7. Use `$geoWithin` for containment and `$geoIntersects` for intersection.
8. Construct Polygons, Polygons with holes, MultiPolygons, and handle multiple overlapping zones.
9. Recognize edge, vertex, hole-boundary, floating-point precision, and GPS uncertainty cases.
10. Handle the ±180° dateline, high latitudes, oversized polygons, and invalid geometries.
11. Distinguish straight-line distance from real travel distance along a road network.
12. Measure `2dsphere` index performance and design reliable geofence test suites.

## 2. Proximity, Containment, and Intersection

| Question | Appropriate Operation | Example |
|---|---|---|
| Who is closest to me? | `$near` or `$geoNear` | 10 nearest pickup points to a customer |
| Who is within radius R? | `$near` or `$geoWithin/$centerSphere` | Stations under 500 m away |
| Which points lie inside a region? | `$geoWithin/$geometry` | Devices inside a polygon |
| Which region contains/intersects a point? | `$geoIntersects/$geometry` | Finding zone from GPS |
| Which routes cross a restricted zone? | `$geoIntersects` with LineString | Vehicle routes crossing a flood zone |

~~~mermaid
flowchart TD
    Goal["Geospatial problem"] --> Distance{"Need distance / nearest ranking?"}
    Distance -->|"Yes"| Near["$near / $geoNear"]
    Distance -->|"No"| Inclusion{"Need full containment in region?"}
    Inclusion -->|"Yes"| Within["$geoWithin"]
    Inclusion -->|"No, need intersection"| Intersects["$geoIntersects"]
~~~

A point near the **center** of a polygon is not necessarily inside the polygon. A route **crossing** a polygon is not necessarily **completely inside** the polygon. A bounding rectangle around a region cannot replace the region itself.

## 3. GeoJSON Coordinates: Longitude First, Latitude Second

GeoJSON Point:

~~~javascript
{
  type: "Point",
  coordinates: [106.7000, 10.7800]
}
~~~

This means longitude 106.7° East and latitude 10.78° North. In WGS84 GeoJSON:

| Value | Typical Domain | Unit |
|---|---|---|
| Longitude | -180 to +180 | Degrees |
| Latitude | -90 to +90 | Degrees |

Do not swap the order:

~~~javascript
// WRONG: 106.7 is not a valid latitude.
{
  type: "Point",
  coordinates: [10.7800, 106.7000]
}
~~~

Even more dangerous is when both numbers **still** fall within valid ranges after swapping: MongoDB may accept them, yet the point lands elsewhere on Earth.

### 3.1. GeoJSON Point vs. Legacy Coordinate Pair

These two formats are not completely synonymous:

~~~javascript
// GeoJSON Point: typed geographic representation.
{ location: { type: "Point", coordinates: [106.7, 10.78] } }

// Legacy coordinate pair: legacy number pair format.
{ location: [106.7, 10.78] }
~~~

Depending on the chosen operator and index, **the unit of distance parameters** can differ significantly between GeoJSON/`2dsphere` and legacy/`2d`. Therefore, migrating from legacy data is not merely changing storage structure; you must re-verify every radius-related query.

### 3.2. Degrees Are Not Meters

One degree of latitude is roughly 111 km, while the length of one degree of longitude varies with latitude:

~~~text
Near equator:  1° longitude ~111 km
Latitude 60°:  1° longitude ~55.5 km
Near poles:    1° longitude approaches 0 km
~~~

Thus, `longitude + 0.001` does not equate to adding exactly 100 m everywhere.

### 3.3. Elevation

GeoJSON can hold a third coordinate, but you must not infer that `2dsphere` queries compute 3D distance accounting for altitude. Most use cases in this lesson evaluate geometry **on a spherical surface**; aircraft, drone, or 3D distance problems require an additional specialized model.

## 4. Distinguishing Degrees, Radians, Meters, and Kilometers

A quick reference table:

| Usage | Unit to Store/Pass |
|---|---|
| GeoJSON `coordinates` | Longitude, latitude in **degrees** |
| `$near` with GeoJSON Point and `2dsphere` | `$maxDistance`/`$minDistance` in **meters** |
| `$nearSphere` with GeoJSON Point and `2dsphere` | Distance in **meters** |
| `$geoNear` with GeoJSON Point, spherical | Output distance in **meters** before multiplier |
| `$geoWithin + $centerSphere` | Radius in **radians** |
| `2d` planar distance on flat coordinates | Units of the **planar** coordinate system |
| Legacy spherical coordinate query | Sometimes **radians**, depending on operator/index |

### 4.1. Degrees to Radians

\[
\theta_{\text{rad}}=\theta_{\text{deg}}\frac{\pi}{180}
\qquad
\theta_{\text{deg}}=\theta_{\text{rad}}\frac{180}{\pi}
\]

For example, 180° = π radians, 90° = π/2 radians.

### 4.2. Arc Length and Angular Radius

Using a reference mean Earth radius:

\[
R \approx 6\,371\,008.8\ \text{m}
\]

We have:

\[
\theta=\frac{d}{R}, \quad d=R\theta
\]

where `d` and `R` share the same unit and `θ` is in radians.

Examples:

\[
500\text{ m}\rightarrow \frac{500}{6\,371\,008.8}
\approx 0.00007848\text{ rad}
\]

\[
2\text{ km}\rightarrow \frac{2000}{6\,371\,008.8}
\approx 0.0003139\text{ rad}
\]

This is a spherical-model approximation. Do not use a single mean radius to claim survey-grade cadastral precision.

### 4.3. Unit-Explicit Conversion Functions

~~~javascript
const EARTH_RADIUS_METERS = 6371008.8

function metersToRadians(meters) {
  if (!Number.isFinite(meters) || meters < 0) {
    throw new Error("INVALID_DISTANCE_METERS")
  }
  return meters / EARTH_RADIUS_METERS
}

function kilometersToRadians(kilometers) {
  return metersToRadians(kilometers * 1000)
}

print(metersToRadians(500))
print(kilometersToRadians(2))
~~~

**Do not divide 500 by Earth's radius when using `$near` with a GeoJSON Point:** `$maxDistance` already expects meters in that case. This function is needed for `$centerSphere` or specific angular-distance APIs.

## 5. Spherical Distance vs. Travel Distance

A common incorrect calculation:

~~~javascript
// WRONG if you want the result in meters.
const deltaLon = lon2 - lon1
const deltaLat = lat2 - lat1
const distanceMeters = Math.sqrt(deltaLon ** 2 + deltaLat ** 2)
~~~

That result represents a difference in **degrees** and ignores how longitude length varies by latitude. With GeoJSON and `2dsphere`, MongoDB uses an appropriate spherical geographic geometry model.

### 5.1. Straight-Line Distance Differs from Travel Distance

Two points may be 400 m apart along the shortest spherical arc, yet a vehicle must drive 1.8 km because of a river, bridge, one-way street, or building entrance. MongoDB `$near` knows nothing about roads, travel speeds, vehicle types, or traffic.

If a product needs **ETA** or **fare by driven kilometers**, use a geospatial query to find **nearby candidates**, then combine with a routing engine or road map to compute real route distance and travel time. Never pass `$geoNear`'s `distanceMeters` off as driven kilometers unless the contract allows it.

### 5.2. Sphere vs. Ellipsoid

The Earth is not a perfect sphere. MongoDB's spherical queries suit many applied proximity/GIS problems but do not necessarily provide legal/millimeter survey precision. When determining exact land area, parcel borders, or high-precision safety corridors, use a validated GIS, projection, and ellipsoidal model.

## 6. Common GeoJSON Structures

### 6.1. Point

~~~javascript
{
  type: "Point",
  coordinates: [106.7000, 10.7800]
}
~~~

### 6.2. LineString

~~~javascript
{
  type: "LineString",
  coordinates: [
    [106.6970, 10.7770],
    [106.7000, 10.7800],
    [106.7090, 10.7850]
  ]
}
~~~

### 6.3. Polygon

~~~javascript
{
  type: "Polygon",
  coordinates: [[
    [106.6960, 10.7770],
    [106.7060, 10.7770],
    [106.7060, 10.7840],
    [106.6960, 10.7840],
    [106.6960, 10.7770]
  ]]
}
~~~

A Polygon has **closed rings**: the first and last coordinates match. A ring needs enough vertices to enclose an area without self-intersections. The outer ring describes the region; subsequent rings can represent **holes**.

### 6.4. MultiPolygon

~~~javascript
{
  type: "MultiPolygon",
  coordinates: [
    [[
      [106.690, 10.770],
      [106.695, 10.770],
      [106.695, 10.775],
      [106.690, 10.775],
      [106.690, 10.770]
    ]],
    [[
      [106.710, 10.790],
      [106.715, 10.790],
      [106.715, 10.795],
      [106.710, 10.795],
      [106.710, 10.790]
    ]]
  ]
}
~~~

A MultiPolygon describes two or more disjoint geographic regions. Never try to join two separate regions with a self-intersecting bowtie ring.

## 7. `2dsphere` and `2d` Indexes

| Index | Model | Typical Applications |
|---|---|---|
| `2dsphere` | Spherical/GeoJSON geometry | GPS/WGS84, geographic regions, nearest search |
| `2d` | Planar geometry | Local x/y coordinate systems or legacy data |

Creating a `2dsphere` index:

~~~javascript
db.pickupPoints.createIndex(
  { location: "2dsphere" },
  { name: "idx_location_sphere" }
)
~~~

`$near`, `$nearSphere`, and `$geoNear` require an appropriate geospatial index. `$geoWithin` can run without an index in some cases, though on large datasets an appropriate index is advisable. A `2dsphere` index has rules for valid geometries and documents missing the geo field; validation must verify coordinates before writing.

**Do not use `2d` for global longitude/latitude just because you guess it is faster.** It uses planar math and fails to properly handle latitude convergence, the dateline, and spherical geometry like `2dsphere`.

## 8. Lab Setup: Simulated Points

Operate only on the lab database:

~~~javascript
use geo_distance_lab

db.createCollection("pickupPoints")

db.pickupPoints.createIndex(
  { location: "2dsphere" },
  { name: "idx_location_sphere" }
)

db.pickupPoints.insertMany([
  {
    _id: "P-A", name: "Point A - center",
    active: true, type: "pickup",
    location: { type: "Point", coordinates: [106.7000, 10.7800] }
  },
  {
    _id: "P-B", name: "Point B - east",
    active: true, type: "pickup",
    location: { type: "Point", coordinates: [106.7020, 10.7800] }
  },
  {
    _id: "P-C", name: "Point C - northwest",
    active: true, type: "pickup",
    location: { type: "Point", coordinates: [106.6970, 10.7810] }
  },
  {
    _id: "P-D", name: "Point D - northeast",
    active: true, type: "pickup",
    location: { type: "Point", coordinates: [106.7100, 10.7870] }
  },
  {
    _id: "P-E", name: "Point E - far",
    active: true, type: "pickup",
    location: { type: "Point", coordinates: [106.7200, 10.8000] }
  },
  {
    _id: "P-F", name: "Point F - southwest",
    active: false, type: "pickup",
    location: { type: "Point", coordinates: [106.6800, 10.7700] }
  },
  {
    _id: "P-G", name: "Point G - north",
    active: true, type: "pickup",
    location: { type: "Point", coordinates: [106.7000, 10.7830] }
  },
  {
    _id: "P-H", name: "Point H - south",
    active: true, type: "pickup",
    location: { type: "Point", coordinates: [106.7030, 10.7760] }
  }
])

db.pickupPoints.countDocuments({}) // 8
~~~

These coordinates do not represent real stores or addresses. The dataset is small enough to observe semantics, but **must not be used for performance benchmarking**. If you already ran setup, do not insert the same `_id` values again.

### 8.1. Query Center

~~~javascript
const center = {
  type: "Point",
  coordinates: [106.7000, 10.7800]
}
~~~

`P-A` is right at the center. `P-B` is 0.002° east in longitude (roughly 218 m at this latitude), and `P-G` is 0.003° north (~334 m). Never infer exact distances by multiplying a degree difference by a single global constant across all latitudes.

## 9. `$near`: Finding Nearest Points in Meters

~~~javascript
db.pickupPoints.find({
  active: true,
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      $maxDistance: 500
    }
  }
}, {
  _id: 1,
  name: 1,
  location: 1
}).limit(20)
~~~

With **GeoJSON Point + `2dsphere`**, `$maxDistance:500` means **500 m**, not 500 degrees or 500 km. `$near` returns points ordered nearest first. It does not automatically add a distance field to results.

### 9.1. Annular Search with `$minDistance`

~~~javascript
db.pickupPoints.find({
  active: true,
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      $minDistance: 100,
      $maxDistance: 500
    }
  }
})
~~~

This query selects points within an annular ring from 100 to 500 m. The point at the exact center has distance 0 and is excluded. To exclude a specific business entity, filtering by `_id` is usually clearer than a tiny minimum-distance threshold.

### 9.2. `$nearSphere`

~~~javascript
db.pickupPoints.find({
  location: {
    $nearSphere: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      $maxDistance: 500
    }
  }
})
~~~

With a GeoJSON Point on `2dsphere`, `$maxDistance` is still in meters. `$nearSphere` specifies spherical proximity; `$near` with GeoJSON/`2dsphere` likewise uses appropriate spherical geography. **Do not infer from the operator name that every legacy coordinate pair query also uses meters.**

## 10. Legacy Coordinate Pairs and Unit-Mismatch Risk

A legacy point:

~~~javascript
{ location: [106.7000, 10.7800] }
~~~

can be used with a `2d` index and legacy operators in **planar coordinate units**. Spherical queries on legacy pairs and `2dsphere` have cases where distance is expressed in **radians**. Therefore:

~~~text
Legacy query: maxDistance = 0.005
GeoJSON query: maxDistance = 0.005
~~~

**Must not be assumed to mean the same radius** without verifying index, operator, geometry type, and units in each case. When migrating:

1. Determine whether the data is truly WGS84 longitude/latitude or planar.
2. Determine whether the existing index is `2d` or `2dsphere`.
3. Determine the current unit of `$maxDistance`.
4. Rewrite the API adapter to use **meters** as an explicit business unit.
5. Test with a set of points at known distances.

## 11. `$geoNear`: Returning Distance in Aggregation

When an API needs both ordering and the distance value:

~~~javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      key: "location",
      spherical: true,
      distanceField: "distanceMeters",
      maxDistance: 500,
      query: {
        active: true,
        type: "pickup"
      }
    }
  },
  {
    $project: {
      name: 1,
      distanceMeters: 1,
      location: 1
    }
  },
  { $limit: 20 }
])
~~~

In this spherical GeoJSON case, `distanceMeters` is in **meters**. `key:"location"` specifies the geospatial field/index, which is useful when a collection has multiple geospatial indexes.

### 11.1. `$geoNear` Must Be the First Stage

Do not write:

~~~javascript
// WRONG: $geoNear cannot follow $match.
db.pickupPoints.aggregate([
  { $match: { active: true } },
  { $geoNear: { /* ... */ } }
])
~~~

Place standard filters inside `$geoNear`'s `query` option, then use subsequent stages to project, limit, or rank.

### 11.2. Converting Distance to Kilometers

~~~javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      key: "location",
      spherical: true,
      distanceField: "distanceKm",
      maxDistance: 2000,
      distanceMultiplier: 0.001
    }
  },
  { $project: { name: 1, distanceKm: 1 } }
])
~~~

`distanceMultiplier:0.001` converts **the output from meters to km**. `maxDistance:2000` remains **2,000 m**; the multiplier does not turn it into 2,000 km.

### 11.3. `find + $near` or `aggregate + $geoNear`?

| Requirement | Recommendation |
|---|---|
| Only need nearest points within a radius | `find` + `$near` |
| Need distance field for UI/API | `aggregate` + `$geoNear` |
| Need further aggregation stats or ranking by distance | `$geoNear` then pipeline |
| Only need inside-circle membership, no sorting | `$geoWithin` + `$centerSphere` |

Do not append a different `$sort` and still label the output as nearest-first once the order has changed.

## 12. `$geoWithin + $centerSphere`: Radius Is in Radians

Filter all points within a 500 m radius circle **without** requiring nearest-first ordering:

~~~javascript
const centerLonLat = [106.7000, 10.7800]
const earthRadiusMeters = 6371008.8
const radiusMeters = 500

db.pickupPoints.find({
  active: true,
  location: {
    $geoWithin: {
      $centerSphere: [
        centerLonLat,
        radiusMeters / earthRadiusMeters
      ]
    }
  }
})
~~~

This is where **meters → radians** conversion is required. Do not write:

~~~javascript
// WRONG: $centerSphere does not take a 500-meter radius directly.
$centerSphere: [[106.7000, 10.7800], 500]
~~~

### 12.1. `$near` vs. `$centerSphere`

- `$near` on GeoJSON: radius/`maxDistance` is in **meters**, and results are ordered by distance.
- `$geoWithin + $centerSphere`: radius is in **radians**, with no guaranteed distance ordering.
- `$geoNear`: returns a distance field, which can be converted to km via multiplier.

### 12.2. Do Not Mix Units in the API

An API should accept a validated `radiusMeters` parameter, and only the database adapter should know when conversion is needed. Do not let frontend and backend teams independently guess whether `radius` means meters or kilometers.

## 13. `$geoWithin + $geometry`: Points Inside a Polygon

Simulated zone:

~~~javascript
const deliveryArea = {
  type: "Polygon",
  coordinates: [[
    [106.6960, 10.7770],
    [106.7060, 10.7770],
    [106.7060, 10.7840],
    [106.6960, 10.7840],
    [106.6960, 10.7770]
  ]]
}
~~~

Filter pickup points belonging to the region:

~~~javascript
db.pickupPoints.find({
  active: true,
  location: {
    $geoWithin: {
      $geometry: deliveryArea
    }
  }
})
~~~

The result answers **polygon membership**, not being within a 500 m circle around a center. Two points at the exact same distance from the center may have one inside the polygon and one outside.

### 13.1. Polygon with a Hole

~~~javascript
const deliveryAreaWithHole = {
  type: "Polygon",
  coordinates: [
    [
      [106.6960, 10.7770],
      [106.7060, 10.7770],
      [106.7060, 10.7840],
      [106.6960, 10.7840],
      [106.6960, 10.7770]
    ],
    [
      [106.6990, 10.7790],
      [106.6990, 10.7810],
      [106.7010, 10.7810],
      [106.7010, 10.7790],
      [106.6990, 10.7790]
    ]
  ]
}
~~~

The outer ring goes counterclockwise and the hole ring goes clockwise in this longitude–latitude representation, matching the common right-hand rule convention. In production, validators should check ring orientation, closed rings, self-intersections, and version-specific rules.

Point `P-A` at `[106.7000,10.7800]` lies inside the **hole**, so it does not belong to the coverage of the polygon with a hole. The second ring is **not** an additional region added to the zone.

### 13.2. MultiPolygon

If a region consists of two disconnected parts, use `MultiPolygon`. Never put the second ring into `Polygon.coordinates` thinking it adds another zone: it will be interpreted as a hole.

## 14. `$geoIntersects`: Zones Containing a Point, Routes Crossing a Zone

In `pickupPoints`, `location` is a Point and the query is a Polygon. Another pattern is a collection storing **polygons** and a query passing a Point:

~~~javascript
db.createCollection("zones")
db.zones.createIndex(
  { geometry: "2dsphere" },
  { name: "idx_zone_geometry" }
)

db.zones.insertMany([
  {
    _id: "zone-central",
    name: "Simulated central zone",
    active: true,
    geometry: {
      type: "Polygon",
      coordinates: [[
        [106.6960, 10.7770],
        [106.7060, 10.7770],
        [106.7060, 10.7840],
        [106.6960, 10.7840],
        [106.6960, 10.7770]
      ]]
    }
  },
  {
    _id: "zone-northeast",
    name: "Simulated northeast zone",
    active: true,
    geometry: {
      type: "Polygon",
      coordinates: [[
        [106.7050, 10.7810],
        [106.7150, 10.7810],
        [106.7150, 10.7910],
        [106.7050, 10.7910],
        [106.7050, 10.7810]
      ]]
    }
  }
])
~~~

Find zones intersecting point `P-B`:

~~~javascript
db.zones.find({
  active: true,
  geometry: {
    $geoIntersects: {
      $geometry: {
        type: "Point",
        coordinates: [106.7020, 10.7800]
      }
    }
  }
})
~~~

`P-B` lies inside `zone-central` in the simulated geometry and not in `zone-northeast`. However, a point in the overlap between two zones can return **two records**.

### 14.1. Finding Zones Intersected by a Route

~~~javascript
const courierRoute = {
  type: "LineString",
  coordinates: [
    [106.6930, 10.7780],
    [106.7010, 10.7810],
    [106.7120, 10.7870]
  ]
}

db.zones.find({
  geometry: {
    $geoIntersects: {
      $geometry: courierRoute
    }
  }
})
~~~

`$geoIntersects` answers **whether** they intersect, not "how many meters of the route lie inside the zone." To clip a route by a polygon or measure affected segment lengths, use dedicated geometry clipping and length calculations.

## 15. Geographic Boundaries: Inside, Outside, Edge, Vertex, and Hole

States to distinguish:

~~~text
INSIDE      Point clearly inside region
OUTSIDE     Point clearly outside region
EDGE        Point directly on an edge
VERTEX      Point directly on a vertex
IN_HOLE     Point inside excluded hole
NEAR_EDGE   Point close to edge, affected by error
OVERLAP     Point inside multiple overlapping regions
~~~

Do not assume every operator treats exact boundary points identically. Certain `$geoWithin` containment cases with shared edges or boundaries do not carry the guarantees users intuitively expect. `$geoIntersects` tests geometric intersection, yet you must still test near-boundary data, floating-point precision, and engine versions.

### 15.1. Policy Must Belong to the Business Domain

The application must define:

- **Inclusive boundary:** a point directly on the boundary counts as inside.
- **Exclusive boundary:** a point directly on the boundary is excluded.
- **Priority rule:** when two zones both contain a point, which wins?
- **Uncertain band:** when a point is close enough to the boundary, do not conclude immediately due to GPS error.

MongoDB does not establish a legal contract for whether "on the boundary is permitted or not."

### 15.2. Sources of Error

- GPS reports positions with error ranging from a few meters to tens of meters.
- Coordinates get rounded.
- Polygons were digitized from map imagery of limited resolution.
- GIS sources used a different CRS without converting to WGS84.
- Two adjacent polygons have slight gaps or overlaps in source data.
- Floating-point and spherical geometry operations have numerical limits.

Do not paper over discrepancies by adding an arbitrary tolerance to every query without specifying how it impacts business rules.

## 16. GPS Uncertainty: Why One Boolean Is Not Enough

Suppose a device reports point P:

~~~text
Estimated distance to boundary: 8 m
Reported GPS accuracy:          25 m
Point-in-polygon query result:  INSIDE
~~~

Because uncertainty exceeds the distance to the edge, concluding definitively that the device "has entered the zone" can be wrong.

An API can return:

~~~javascript
{
  zoneId: "zone-central",
  classification: "UNCERTAIN_NEAR_BOUNDARY",
  gpsAccuracyMeters: 25,
  boundaryDistanceMeters: 8,
  observedAt: ISODate("2026-10-01T08:00:00Z")
}
~~~

### 16.1. Suggested Three-Level Classification

1. `CONFIDENT_INSIDE` if the point is inside and farther from the edge than `uncertainty + margin`.
2. `CONFIDENT_OUTSIDE` if outside and sufficiently far from the edge.
3. `UNCERTAIN` if within the buffer band close to the boundary.

**Important:** `$geoWithin` does not compute distance to a Polygon's boundary. To obtain `boundaryDistanceMeters`, use a proper GIS algorithm/engine to measure distance to **the boundary edges**, not distance to the centroid.

### 16.2. A Buffer Is Not a Circle Around the Centroid

To "expand a polygon by 20 m," you cannot replace it with a 20 m `$centerSphere` around the center. A true **polygon buffer** must handle edges, corners, holes, and the right CRS/measurement model. MongoDB does not provide a general `bufferMeters` parameter for `$geoWithin` queries.

### 16.3. Hysteresis to Prevent Geofence Jitter

A vehicle parked near a boundary might have GPS reports like:

~~~text
08:00 INSIDE
08:01 OUTSIDE
08:02 INSIDE
08:03 OUTSIDE
~~~

If you fire ENTER/EXIT on every point, the app floods alerts. A workable model:

~~~mermaid
stateDiagram-v2
    [*] --> UNKNOWN
    UNKNOWN --> OUTSIDE: Enough stable outside points
    UNKNOWN --> INSIDE: Enough stable inside points
    OUTSIDE --> MAYBE_ENTER: Point starts crossing boundary
    MAYBE_ENTER --> INSIDE: N stable samples + margin
    MAYBE_ENTER --> OUTSIDE: Returned outside
    INSIDE --> MAYBE_EXIT: Point starts leaving
    MAYBE_EXIT --> OUTSIDE: N stable samples + margin
    MAYBE_EXIT --> INSIDE: Returned inside
~~~

Sample count and margin should be tuned for travel speed, GPS accuracy, reporting frequency, and business risk. A hazardous zone may prioritize early warning rather than waiting too long.

## 17. Valid Polygons: Rings, Holes, and Self-Intersection

A valid GeoJSON polygon requires:

- **Closed** rings: first and last vertices match.
- Enough positions to enclose a non-zero area.
- No self-intersecting boundaries.
- Holes strictly inside the outer ring without conflicts.
- Proper winding per GeoJSON/MongoDB rules, especially for very large polygons.
- Numeric coordinates in valid lon/lat order.

Example of a polygon missing its closing coordinate:

~~~javascript
// WRONG: unclosed ring.
{
  type: "Polygon",
  coordinates: [[
    [106.69, 10.77],
    [106.71, 10.77],
    [106.71, 10.79],
    [106.69, 10.79]
  ]]
}
~~~

A self-intersecting bowtie ring is not a valid geometry simply because its vertices fall within lon/lat bounds. Validate with GIS tooling before insertion or at ingestion; never "fix" it by randomly deleting a vertex.

### 17.1. Hole Boundaries Are Also Boundaries

A point close to a **hole's edge** must follow the same uncertainty policy as a point close to the outer boundary. Do not measure distance only to the outer ring and ignore inner rings.

### 17.2. One Region Split into Multiple Pieces

When a city has two disjoint delivery zones, use a `MultiPolygon` or separate zone documents with explicit policy. Never stuff two disjoint rings into the same Polygon expecting both to be additive areas, because subsequent rings mean holes structurally.

## 18. Polygons Larger Than a Hemisphere and Strict Winding

For very large polygons, a ring on a sphere separates a **smaller enclosed region** from a **complementary region larger than half the Earth**. MongoDB provides a **strict winding CRS** mechanism for single-ring polygons larger than a hemisphere in supported scenarios:

~~~javascript
{
  type: "Polygon",
  coordinates: [
    // A closed ring with proper winding,
    // containing the actual coordinates of the large polygon.
  ],
  crs: {
    type: "name",
    properties: {
      name: "urn:x-mongodb:crs:strictwinding:EPSG:4326"
    }
  }
}
~~~

This is a **structural template**, not a runnable polygon: `coordinates` must be populated with a valid ring. Do not attach this custom CRS to Points or small regions. When handling large polygons:

1. Check area relative to a hemisphere.
2. Check winding order.
3. Verify which operators and MongoDB versions support the custom CRS.
4. Test with explicit points inside the intended region and on the opposite side of Earth.
5. Do not infer "the white space on a flat map" is outside on a sphere.

## 19. The ±180° Antimeridian (Dateline)

Two locations:

~~~text
Point A: longitude +179.8°
Point B: longitude -179.8°
~~~

are only **0.4° of longitude apart across the dateline**, not 359.6° along the shortest arc.

### 19.1. Mistake with a Linear Bounding Box

~~~javascript
// Does not accurately represent a region crossing the dateline.
{
  longitude: {
    $gte: 179.5,
    $lte: -179.5
  }
}
~~~

This condition has a lower bound greater than its upper bound. If using bounding boxes as a prefilter, split into two intervals `[179.5,180]` and `[-180,-179.5]` or use a GeoJSON/MultiPolygon model handled properly on a sphere.

### 19.2. Geometries Crossing the Dateline

Do not draw a ring "170° → -170°" assuming every engine interprets the **intended side** correctly. Normalize the representation and run tests with points on both sides of ±180°, including the unintended side. Complex regions may need to be split into a **MultiPolygon** via GIS tooling.

### 19.3. ±180 Represents the Same Meridian

At the dateline seam, `+180` and `-180` refer to the same geographic meridian yet are distinct numbers. Establish normalization policies and boundary tests in the application; never let one API assume `+180` while another requires `-180` without rules.

## 20. Near the Poles: Longitude Is No Longer a Stable Length Metric

Near ±90° latitude, meridians converge. Two points with a large difference in longitude can still be physically close. Approximations like:

~~~text
deltaLongDegrees * 111000 = meters
~~~

fail badly as latitude rises. For polar regions and aviation/maritime data, use spherical geometry or validated specialized calculations, and test points near poles and polygon winding.

## 21. Haversine: Reference Distance Calculation in the Application

Given latitudes `φ₁`, `φ₂` and latitude/longitude differences `Δφ`, `Δλ` in radians:

\[
a=\sin^2\left(\frac{\Delta\varphi}{2}\right)
 +\cos(\varphi_1)\cos(\varphi_2)\sin^2\left(\frac{\Delta\lambda}{2}\right)
\]

\[
c=2\operatorname{atan2}(\sqrt{a},\sqrt{1-a}),
\qquad d=Rc
\]

### 21.1. JavaScript

~~~javascript
function degreesToRadians(degrees) {
  return degrees * Math.PI / 180
}

function haversineMeters(pointA, pointB) {
  const [lon1, lat1] = pointA
  const [lon2, lat2] = pointB
  const radius = 6371008.8

  const phi1 = degreesToRadians(lat1)
  const phi2 = degreesToRadians(lat2)
  const deltaPhi = degreesToRadians(lat2 - lat1)

  // Shortest longitude difference within [-180, 180].
  let deltaLon = lon2 - lon1
  deltaLon = ((deltaLon + 540) % 360) - 180
  const deltaLambda = degreesToRadians(deltaLon)

  const a = Math.sin(deltaPhi / 2) ** 2 +
    Math.cos(phi1) * Math.cos(phi2) *
    Math.sin(deltaLambda / 2) ** 2

  const safeA = Math.max(0, Math.min(1, a))
  const c = 2 * Math.atan2(Math.sqrt(safeA), Math.sqrt(1 - safeA))
  return radius * c
}

print(haversineMeters(
  [106.7000, 10.7800],
  [106.7020, 10.7800]
)) // Approximately 218 m.

print(haversineMeters(
  [179.8, 0.0],
  [-179.8, 0.0]
)) // Approximately 44.5 km.
~~~

Haversine is useful for cross-checking or displaying distances, but **does not replace an index**: do not load 10 million points into the application and compute Haversine manually just to pick the top 10. Use `2dsphere + $near/$geoNear` to narrow candidates.

### 21.2. Distance to a Polygon Is a Different Problem

Haversine computes **point-to-point** distance. Distance from a point to a region is 0 when the point is inside the region, or the shortest distance to **the boundary** when outside. It is not the distance to the centroid or to the first polygon vertex.

## 22. A Bounding Box Does Not Replace a Circle

A rectangle in longitude/latitude:

~~~text
lonMin 106.696
lonMax 106.706
latMin 10.777
latMax 10.784
~~~

can help as a coarse prefilter, but the rectangle's corners can lie farther from the center than a 500 m radius. If the requirement is "within radius," use spherical distance or an appropriate circular query.

### 22.1. Prefilter Then Check Precisely

A workable workflow:

~~~text
1. Filter candidates using an index or bounding volume where appropriate.
2. Compute spherical distance or containment.
3. Apply business tolerance and uncertainty policy.
4. Return results with explicit units.
~~~

Never use `longitude ± 0.005` as a fixed global radius. Beyond varying with latitude, this breaks near the dateline and poles.

## 23. Overlapping Zones and Selecting One Zone

The two polygons in the lab overlap around longitude 106.705–106.706 and latitude 10.781–10.784. Query:

~~~javascript
db.zones.find({
  active: true,
  geometry: {
    $geoIntersects: {
      $geometry: {
        type: "Point",
        coordinates: [106.7055, 10.7830]
      }
    }
  }
})
~~~

can return **multiple zones**. This does not mean the database has a bug: the geometries genuinely overlap. To select one business zone:

- Define an explicit `priority`.
- Optionally select the lowest fee or the assigned operational unit's zone.
- Define a tie-breaker policy when priorities are equal.
- Version geometries so you can explain why results changed over time.

Never call `findOne()` and assume the first returned document is the right one. Likewise, two polygons merely **touching along an edge** do not necessarily have meaningful overlapping area. `$geoIntersects` returns whether they intersect, **not the overlap area**.

## 24. Geofencing with Time-Series Location Data

A single GPS sample does not describe a vehicle's trajectory. Distinguish `capturedAt` (measurement time), `receivedAt` (server arrival time), accuracy, and event ID to handle delayed packets.

Example:

~~~javascript
{
  vehicleId: "vehicle-01",
  capturedAt: ISODate("2026-10-01T08:00:00Z"),
  receivedAt: ISODate("2026-10-01T08:00:07Z"),
  accuracyMeters: 18,
  location: {
    type: "Point",
    coordinates: [106.7055, 10.7830]
  }
}
~~~

If the 08:00 point arrives after the 08:01 point, processing sequentially by **`receivedAt`** can emit false ENTER/EXIT events. Implement watermark/out-of-order policies, and avoid retaining precise coordinates longer than needed or permitted.

### 24.1. Geofencing Does Not Prevent GPS Spoofing

A device can report forged coordinates. MongoDB confirming that those coordinates lie inside a polygon **does not prove the device is physically there**. For timekeeping, payments, or security, add anti-spoofing and source verification.

## 25. Java Driver: GeoJSON Point and Distance in Meters

Example using the MongoDB Java Sync Driver:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.geojson.Point;
import com.mongodb.client.model.geojson.Position;
import org.bson.Document;
import org.bson.conversions.Bson;

public class NearbyPickupDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> places = client
                .getDatabase("geo_distance_lab")
                .getCollection("pickupPoints");

            // Position(longitude, latitude), do not swap.
            Point center = new Point(new Position(106.7000, 10.7800));

            // GeoJSON + 2dsphere: 500.0 is 500 meters.
            Bson nearby = Filters.near(
                "location", center, 500.0, 0.0
            );
            Bson filter = Filters.and(
                Filters.eq("active", true),
                nearby
            );

            for (Document place : places.find(filter).limit(20)) {
                System.out.println(place.toJson());
            }
        }
    }
}
~~~

Key takeaways: `Position` takes **lon first, lat second**; `500.0` is in **meters** in this GeoJSON syntax; the collection needs a geospatial index. Across different Java Driver versions or BSON builders, method signatures may vary, but coordinate and unit semantics remain the same.

## 26. Node.js Driver: Retrieving Distance with `$geoNear`

~~~javascript
import { MongoClient } from "mongodb"

const client = new MongoClient(process.env.MONGODB_URI)
await client.connect()

try {
  const col = client
    .db("geo_distance_lab")
    .collection("pickupPoints")

  const results = await col.aggregate([
    {
      $geoNear: {
        near: {
          type: "Point",
          coordinates: [106.7000, 10.7800]
        },
        key: "location",
        spherical: true,
        distanceField: "distanceMeters",
        maxDistance: 500,
        query: { active: true }
      }
    },
    { $project: { name: 1, distanceMeters: 1 } },
    { $limit: 20 }
  ]).toArray()

  console.log(results)
} finally {
  await client.close()
}
~~~

### 26.1. Validating Coordinates and Radius

~~~javascript
function validateGeoInput({ longitude, latitude, radiusMeters }) {
  if (!Number.isFinite(longitude) ||
      longitude < -180 || longitude > 180) {
    throw new Error("INVALID_LONGITUDE")
  }
  if (!Number.isFinite(latitude) ||
      latitude < -90 || latitude > 90) {
    throw new Error("INVALID_LATITUDE")
  }
  if (!Number.isFinite(radiusMeters) ||
      radiusMeters < 0 || radiusMeters > 20000) {
    throw new Error("INVALID_RADIUS_METERS")
  }
}
~~~

The number `20000` here is just an **illustrative API cap**, not a hard MongoDB limit. Never pass `NaN`, `Infinity`, unparsed strings, or unbounded radii from clients.

### 26.2. API Contract

Return:

~~~javascript
{
  placeId: "P-B",
  distanceMeters: 218.4,
  distanceDisplay: "218 m"
}
~~~

Never return `distance:218.4` without a unit. `distanceDisplay` is for UI presentation only; business threshold comparisons should evaluate the **unrounded** numeric value.

## 27. Rounding Errors and Hard Thresholds

Two distances:

~~~text
499,999 m
500,001 m
~~~

may both display as "500 m" while lying on opposite sides of the threshold. Therefore:

- Never compare **formatted strings**.
- Never round before checking `distance <= radius`.
- If a 1–5 m tolerance is needed, document it explicitly as a **business policy**.
- With 20 m GPS accuracy, a computed 499 m distance does not prove the true position is within a 500 m radius.

Adding decimal places to coordinates **does not make the sensor more accurate**. Measurement accuracy must be evaluated from the source and methodology.

## 28. Compound Geospatial Indexes and Business Filters

If nearly every query filters `active:true`:

~~~javascript
db.pickupPoints.createIndex(
  {
    active: 1,
    location: "2dsphere"
  },
  { name: "idx_active_location" }
)
~~~

This is merely a **candidate** to evaluate, not guaranteed to outperform a standalone geo index. Field order, selectivity, queries omitting `active`, and write/index costs all decide. With a compound `2dsphere` index, understand the rules for documents with or without the geometry field and its data type.

### 28.1. Inspecting `explain()`

~~~javascript
db.pickupPoints.explain("executionStats").find({
  active: true,
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      $maxDistance: 1000
    }
  }
}).limit(50)
~~~

Check:

- Which index was used.
- Geospatial stages such as `GEO_NEAR` or related stages depending on engine/version.
- `nReturned`, `totalKeysExamined`, and `totalDocsExamined` where reported.
- p95/p99 latency on representative data.
- Ratio of index entries scanned to returned results.

Never draw production performance conclusions from **8 lab documents**. Stage names can vary by version.

### 28.2. Complex Polygon Boundaries

Polygons with thousands of vertices can incur significant geometry decoding and evaluation costs. Verify:

- Geometry is validated with clear source versioning.
- Whether simplification within an acceptable tolerance **without violating requirements** is possible.
- Whether you can prefilter by tenant, metadata, or time.
- Whether payloads are too large to return in a single API call.

For legal boundaries, never decimate vertices arbitrarily, as doing so can flip points from inside to outside.

## 29. Sharded Clusters and Geospatial Queries

When a collection is sharded, `mongos` may need to route a geospatial query to **multiple shards** if filters do not support shard-key targeting. A `2dsphere` index optimizes geometry lookups **within each shard**, but does not create a shard key or guarantee single-shard execution.

- Geospatial indexes have restrictions when used as shard keys; never assume `{location:"2dsphere"}` is a valid shard key.
- Cluster-wide top-N nearest queries must merge candidates across all relevant shards, not just one shard.
- When the shard key incorporates tenant/region, include appropriate query filters to minimize fan-out whenever possible.
- Measure network and merge overhead as shard count grows.

**Zone sharding** governs data placement by shard key; a **geofence zone** is a business polygon. They are completely different concepts despite sharing the word "zone."

## 30. Security and Access Control

A multi-tenant collection:

~~~javascript
{
  tenantId: "t-01",
  location: {
    type: "Point",
    coordinates: [106.7000, 10.7800]
  }
}
~~~

A geospatial index does not restrict another tenant's read access. An API must bind `tenantId` from the **authenticated context**, never trusting a user-supplied body field.

Precise user coordinates can be sensitive data. Limit storing/logging coordinates when unnecessary, define retention policies, and enforce authorization; `$geoNear` computes accurate geometry, not access control.

## 31. Location Freshness and Event Reliability

A location measured 20 minutes ago may no longer reflect where a vehicle is now. For vehicle tracking:

~~~javascript
{
  vehicleId: "v-001",
  capturedAt: ISODate("2026-10-01T08:00:00Z"),
  receivedAt: ISODate("2026-10-01T08:00:02Z"),
  location: {
    type: "Point",
    coordinates: [106.7000, 10.7800]
  }
}
~~~

The application must verify:

- Is `capturedAt` fresh enough?
- Did events arrive late or out of order?
- What is the GPS accuracy/confidence?
- Did the device overwrite an old position with a new one?
- Does the business decision require multiple consecutive samples?

A `$geoWithin` query returning true on a **stale position** does not prove the current position is still inside the zone.

## 32. Practice A — Nearby Within 500 Meters

~~~javascript
db.pickupPoints.find({
  active: true,
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      $maxDistance: 500
    }
  }
}, { name: 1 }).limit(20)
~~~

Explain the unit of `500`, the rank of `P-A` in nearest-first order, and how to change the radius from 500 m to 2 km.

## 33. Practice B — `$centerSphere`

~~~javascript
const radiusMeters = 500

db.pickupPoints.find({
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.7000, 10.7800],
        radiusMeters / 6371008.8
      ]
    }
  }
})
~~~

Why do you not pass `radiusMeters` directly into `$centerSphere`'s radius slot? Does this query automatically sort nearest first?

## 34. Practice C — Display Distance

~~~javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.7800]
      },
      key: "location",
      distanceField: "distanceMeters",
      spherical: true,
      maxDistance: 1000,
      query: { active: true }
    }
  },
  {
    $project: {
      name: 1,
      distanceMeters: 1,
      distanceKm: { $divide: ["$distanceMeters", 1000] }
    }
  }
])
~~~

Explain why `distanceKm` is computed in `$project` while `maxDistance` stays in meters. Try `distanceMultiplier:0.001` as an alternative way to convert output.

## 35. Practice D — Polygon Containment

~~~javascript
const area = {
  type: "Polygon",
  coordinates: [[
    [106.6960, 10.7770],
    [106.7060, 10.7770],
    [106.7060, 10.7840],
    [106.6960, 10.7840],
    [106.6960, 10.7770]
  ]]
}

db.pickupPoints.find({
  location: {
    $geoWithin: {
      $geometry: area
    }
  }
})
~~~

Check whether the ring is closed; compare with the 500 m circle results. Test the query with `deliveryAreaWithHole` and explain why `P-A` inside the hole is excluded.

## 36. Practice E — Two Overlapping Zones

~~~javascript
db.zones.find({
  geometry: {
    $geoIntersects: {
      $geometry: {
        type: "Point",
        coordinates: [106.7055, 10.7830]
      }
    }
  }
})
~~~

Explain why the result can return **two zones**, and why `findOne()` is not a valid business zone-selection algorithm.

## 37. Practice F — Route Crossing a Polygon

Use `courierRoute` declared in Section 14 with `$geoIntersects`. If you need how many meters of the route pass through the restricted zone, what additional operation is required?

## 38. Practice G — The ±180° Meridian

~~~javascript
print(haversineMeters(
  [179.8, 0.0],
  [-179.8, 0.0]
))
~~~

Explain why the distance is roughly **44.5 km**, not nearly Earth's full circumference. Describe how to normalize MultiPolygons/bounding boxes for regions crossing the dateline and test on both sides of ±180°.

## 39. Practice H — Near-Boundary Geofence

~~~text
Polygon query: INSIDE
Estimated distance to edge: 8 m
GPS reported accuracy: 25 m
~~~

Design an API returning `UNCERTAIN_NEAR_BOUNDARY` and rules for collecting additional samples. Why must you not emit ENTER immediately after a single query returning INSIDE?

## 40. Practice I — Explaining the Plan

Run `explain("executionStats")` on the lab's `$near` query. Record the index, result count, keys/docs examined, and actual returned stages. Never fabricate latency numbers or claim "N times faster" on an 8-point dataset.

## 41. Practice J — Choosing the Right Approach

Choose the query for each requirement:

1. Filter the 20 nearest pickup points within 2 km.
2. Find all vehicle routes crossing a flood zone.
3. Check whether a Point lies inside a delivery zone with a hole.
4. Filter points within a 500 m circle without sorting by distance.
5. Find which Polygon intersects a current GPS Point.
6. Calculate driving time to a delivery point.

Distinguish cases handled by MongoDB geospatial queries from cases requiring external GIS clipping or a routing engine.

## 42. Answer Hints

**A:** With GeoJSON Point and `2dsphere`, `$maxDistance:500` is 500 m. `P-A` is at the center so its distance is 0; for a 2 km radius set `2000`.

**B:** `$centerSphere` radius is in radians, so pass `meters/R`. Distance sorting is not guaranteed.

**C:** `$geoNear` outputs `distanceMeters`; dividing by 1000 or using `distanceMultiplier` produces km without changing `maxDistance`.

**D:** The polygon ring is closed because the last coordinate equals the first; containment differs from circle distance. The hole excludes points inside the polygon's inner ring.

**E:** Two polygons overlap; the query can return multiple rows. Business logic needs priority, pricing, or tie-breaking rules rather than taking an arbitrary first record.

**F:** `$geoIntersects` only returns whether they intersect; to get intersection length, clip the LineString against the polygon and measure length with an appropriate model.

**G:** Two longitudes are 0.4° apart across the dateline. Use spherical distance and properly normalized representations/prefilters.

**H:** Accuracy of 25 m exceeds the 8 m distance-to-edge, so one INSIDE sample is not conclusive. Use an uncertainty/hysteresis policy.

**I:** Rely on actual `explain` output rather than guessing from index names or tiny datasets.

**J:** (1) `$geoNear` or `$near`, (2) `$geoIntersects`, (3) `$geoWithin` on a point collection or `$geoIntersects` on a polygon collection, (4) `$geoWithin+$centerSphere`, (5) `$geoIntersects`, (6) a routing engine after candidate selection.

## 43. Common Mistakes

| Mistake | Why Is It Wrong? | Correct Approach |
|---|---|---|
| Swapping `[lat,lon]` | GeoJSON expects lon first | Validate and normalize inputs |
| Treating degrees as meters | Longitude degrees vary by latitude | Spherical math and explicit units |
| Passing 500 as `$centerSphere` radius | Operator expects **radians** | `500 / R` |
| Converting 500 m to radians for GeoJSON `$near` | `$maxDistance` here expects **meters** | Pass `500` directly |
| Switching legacy queries while keeping old maxDistance numbers | Legacy units may differ | Migrate geometry + index + units together |
| Using `2d` for global GPS | Planar distance is inaccurate | `2dsphere` |
| Treating `$near` as driving route | Ignores road network and restrictions | Routing engine |
| Using centroid to test polygon containment | Regions have corners, holes, concavities | `$geoWithin`/`$geoIntersects` |
| Using `$geoWithin` expecting nearest-first order | No default distance sorting | `$near`/`$geoNear` |
| Placing `$geoNear` after `$match` | Stage must come first | Move filters into `query` |
| Treating a second ring as an additive polygon | Subsequent rings can be holes | MultiPolygon for disjoint regions |
| Ring missing closing coordinate | Invalid polygon | Close ring and validate |
| Self-intersecting polygon | Ambiguous geometry | GIS repair and validation |
| Assuming exact boundary points are always inside | Complex boundary semantics and precision | Policy + boundary tests |
| Concluding from one near-edge GPS sample | GPS uncertainty | Buffer/hysteresis/state machine |
| Using plain longitude boxes across the dateline | ±180° wrap-around | Split/normalize/valid GeoJSON |
| Assuming nearest always hits only one shard | Query can scatter | Measure routing and shards touched |
| Relying solely on geospatial filters for authorization | Index does not enforce tenant auth | Auth + tenant filter |
| Logging raw user coordinates indiscriminately | Privacy risk | Minimization/retention/auth |

## 44. Review Questions

**1. What order does a GeoJSON Point store?** — Longitude first, latitude second; coordinate units are **degrees**.

**2. Which distance unit does `$near` with a GeoJSON Point on `2dsphere` use?** — **Meters**.

**3. What radius unit does `$centerSphere` use?** — **Radians**; convert `meters/R` with `R` in meters.

**4. Roughly how many radians is a 1 km radius?** — `1000/6371008.8 ≈ 0.000157`.

**5. When should you use `$geoNear`?** — When you need nearest querying combined with a distance field and downstream aggregation stages.

**6. Does `distanceMultiplier:0.001` change the meaning of `maxDistance`?** — No, it only scales the output distance per the rule.

**7. How do `$geoWithin` and `$geoIntersects` differ?** — One checks full containment; the other checks geometric intersection.

**8. What is a polygon hole?** — A region inside the outer ring that is **excluded from coverage**.

**9. When should you use a MultiPolygon?** — When a region consists of multiple disconnected parts.

**10. Can boundary points always be assumed inside?** — No. You need explicit business policies, geometry tests, and uncertainty handling.

**11. With 25 m GPS accuracy, is a point 8 m inside the boundary guaranteed to be inside?** — No; the uncertainty interval crosses the boundary.

**12. Why are longitudes +179.8 and -179.8 close together?** — They sit on opposite sides of the antimeridian, 0.4° apart via the short arc.

**13. Near the poles, can you approximate with longitude difference × 111 km?** — No, meridians converge, making that approximation wrong.

**14. How do `2d` and `2dsphere` differ?** — Planar vs. spherical; GeoJSON GPS data usually needs `2dsphere`.

**15. Does Haversine replace a geo index?** — No. It works for computing distance on small sets; an index avoids reading every document.

**16. Does `$geoIntersects` compute overlap area?** — No, it returns intersection match results.

**17. Does 500 m proximity equal a 500 m driving route?** — No; road networks and ETA are a separate routing problem.

**18. Are two zones containing the same point a database bug?** — No, zones can geometrically overlap. Business logic needs priority rules.

**19. Does a matching geospatial query prove a vehicle is physically there?** — No; positions can be stale, inaccurate, or spoofed.

**20. What must be verified before delivering based on legal boundaries?** — Source geometry, CRS/version, boundary policy, location accuracy, and edge-case tests.

## 45. Quick Reference Table

| Requirement | Tool |
|---|---|
| GeoJSON WGS84 | `{type:"Point",coordinates:[lon,lat]}` |
| GPS geographic index | `createIndex({location:"2dsphere"})` |
| Nearest within 500 m | `$near:{$geometry:point,$maxDistance:500}` |
| Spherical nearest | `$nearSphere` with GeoJSON |
| Retrieve distance field | `$geoNear` |
| Convert m to km in `$geoNear` | `distanceMultiplier:0.001` |
| Points inside 500 m circle | `$geoWithin:{$centerSphere:[[lon,lat],500/R]}` |
| Points inside Polygon | `$geoWithin:{$geometry:polygon}` |
| Polygon intersecting Point/Line | `$geoIntersects:{$geometry:...}` |
| Polygon with hole | `coordinates:[outerRing,holeRing]` |
| Disjoint regions | `MultiPolygon` |
| Reference distance | Haversine / GIS system |
| Positions across dateline | Normalize longitude, valid geometry |
| Near-boundary geofence | Accuracy + tolerance + hysteresis |
| Inspect query plan | `explain("executionStats")` |

## 46. Pre-Production Deployment Checklist

- [ ] Are coordinates standardized to WGS84 with **[longitude,latitude]**?
- [ ] Are coordinate bounds, numeric types, and `NaN`/`Infinity` validated?
- [ ] Does the API clearly name `radiusMeters`/`distanceMeters`?
- [ ] Are meters and radians properly distinguished per operator?
- [ ] Does a `2dsphere` index exist on the required GeoJSON field?
- [ ] If migrating legacy data, have all distance units been re-verified?
- [ ] Has the business confirmed whether proximity, containment, or intersection is needed?
- [ ] Is `$geoNear` first in the pipeline and specifying `key` when multiple geo indexes exist?
- [ ] Are max radius, limit, query timeout, and tenant filters enforced?
- [ ] Are polygon rings closed, non-self-intersecting, and with valid holes?
- [ ] Have edge, vertex, hole, MultiPolygon, and overlap cases been tested?
- [ ] Has an inclusive/exclusive/uncertain boundary policy been defined?
- [ ] Are GPS accuracy, `capturedAt`, out-of-order events, and hysteresis handled?
- [ ] Have dateline/near-polar cases been tested if global scope applies?
- [ ] Do legal geometries have clear provenance and versioning?
- [ ] Are you avoiding using spherical distance as route distance or ETA?
- [ ] Have `explain`, p95/p99 latency, and keys/docs examined been measured on representative data?
- [ ] If sharded, have shards touched and global nearest ordering been verified?
- [ ] Are tenant authorization and user location privacy enforced?
- [ ] Is there a golden geospatial fixture suite to run across index/driver/geometry updates?

## 47. Conclusion

In MongoDB geospatial queries, **the units and operations you choose must match business semantics**. GeoJSON uses **longitude/latitude in degrees**; `$near`/`$geoNear` with a GeoJSON Point and `2dsphere` generally use **meters**, whereas `$centerSphere` takes its radius in **radians**. Confusing these units makes queries search the wrong area even when the command executes cleanly.

Distance is only one piece: **`$geoWithin`** solves containment, while **`$geoIntersects`** solves intersection. Polygons with holes, overlapping zones, exact boundary points, the ±180° dateline, and GPS uncertainty all require validation and explicit policies. A geometric query cannot replace route-finding algorithms, legal land surveying, or device trust models.

In production, use a **`2dsphere` index**, bound radii and result counts, read `explain()`, get units right, and normalize GeoJSON. For geofencing, combine geometric results with **accuracy, time windows, state stability, and boundary test suites**. Only then do "nearby," "inside zone," or "left zone" carry consistent meaning for your application.
