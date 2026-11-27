# `2dsphere` Index, `2d` Index, and Selection Criteria

MongoDB supports **geospatial indexes** for storing and querying location-based data: finding stores near a user, filtering places within a delivery zone, finding intersecting geographic regions, or looking up positions on a warehouse floor plan. The two commonly referenced index types are **`2dsphere`** and **`2d`**.

Although both serve "coordinate" problems, the two indexes have **different geometric models**:

- **`2dsphere`** is used for geographic calculations on an **Earth-like spherical surface**. It is the standard choice for longitude/latitude locations, GeoJSON, and real-world mapping applications.
- **`2d`** is used for **planar coordinates** and distance under a Euclidean geometry model. It suits floor plans, game grids, or legacy data representing points as coordinate pairs when the business logic genuinely requires planar measurements.

The choice is not merely about `createIndex()` syntax. You must evaluate **measurement units, coordinate systems, geometry types, query operators, region sizes, accuracy requirements, workload patterns, compound indexes, and input data validity**.

> **First Principle:** Real-world locations on Earth are stored in GeoJSON as `[longitude, latitude]` pairs and typically use **`2dsphere`**. Locations on a flat map using an application's own X/Y units that require Euclidean distance can consider **`2d`**. Never interchange the two indexes simply because both contain "2d" in their name.

## 1. Before Choosing an Index: Which Space Does the Data Represent?

Suppose we have two collections.

The `geoPlaces` collection stores locations on Earth:

```javascript
{
  _id: "PLACE-01",
  name: "Service Point A",
  category: "service",
  location: {
    type: "Point",
    coordinates: [106.7000, 10.7760]
  }
}
```

The two numbers in `coordinates` are:

```text
[longitude, latitude]
[east-west, north-south]
```

This is a **GeoJSON Point**. The sample coordinate pair falls within valid longitude/latitude bounds for illustration; it does not refer to a specific street address.

The `floorPoints` collection stores positions on a warehouse floor plan:

```javascript
{
  _id: "SHELF-A01",
  floorId: "F1",
  name: "Shelf A01",
  xy: [125.5, 64.0]
}
```

Here:

```text
x = 125.5 floor-plan units
y = 64.0 floor-plan units
```

If each unit corresponds to one meter, the planar distance from `[100,50]` to `[125.5,64]` can be calculated with Euclidean geometry. If the unit is pixels or centimeters, the result is in **that unit**—MongoDB does not automatically convert it to meters.

Both documents appear to hold two numbers, yet their physical meanings are completely different.

## 2. The Nature of `2dsphere`

`2dsphere` is a geospatial index designed for an **Earth-like sphere** geometric model. It supports GeoJSON data and permitted legacy coordinate pair representations.

Example index creation:

```javascript
db.geoPlaces.createIndex({
  location: "2dsphere"
});
```

Once indexed, queries can use geospatial operators such as:

- `$near` / `$nearSphere` on supported geometries;
- `$geoWithin` to check whether positions lie inside a region;
- `$geoIntersects` to check whether geometries intersect;
- Aggregation `$geoNear` to find neighbors along with distance.

Depending on the operation, MongoDB can use the index to narrow down candidate regions and then perform geometric checks to ensure accurate results.

### 2.1. Why Not Use Euclidean Distance Directly on Longitude/Latitude?

One degree of longitude **does not have the same ground length at every latitude**. Near the equator versus near the poles, a one-degree difference in longitude corresponds to vastly different distances. The Earth's surface is also curved.

If you apply naive planar math on two longitude/latitude numbers and treat the result as meters, the application can:

- Miscalculate distances;
- Misorder nearby places;
- Produce distorted radius searches, especially at high latitudes;
- Fail on data crossing the ±180° meridian;
- Struggle to extend logic to polygons or paths.

`2dsphere` handles geographic semantics on a spherical model better suited for mapping problems.

### 2.2. `2dsphere` Is Not a Turn-by-Turn Routing Engine

A proximity search with `2dsphere` typically relies on **shortest spherical geographic distance**. It does not know about:

- One-way streets;
- Bridges, ferries, or restricted zones;
- Traffic congestion;
- Elevation, stairs, or elevators;
- Travel times by motorbike, car, or on foot.

Therefore, "geographically closest" is not necessarily "fastest delivery time." If real road routing is needed, use a geospatial query to build a **candidate set**, then hand off to a routing engine or mapping service.

## 3. The Nature of `2d`

`2d` is an index used for **planar coordinate** data stored as legacy coordinate pairs.

Example:

```javascript
db.floorPoints.createIndex({
  xy: "2d"
});
```

Coordinates can be stored as:

```javascript
{
  _id: "ROBOT-01",
  xy: [20.0, 45.0]
}
```

Common planar queries include:

- `$near` on X/Y pairs to find the closest points;
- `$geoWithin` combined with `$box`, `$center`, or `$polygon` using supported legacy shapes;
- Other geospatial variants with specific support conditions.

A system tracking warehouse floor layouts, robot coordinates, 2D game arenas, or engineering schematics may need **planar** distance calculations. When data is pure X/Y, do not force it into fake GeoJSON longitude/latitude values.

### 3.1. `2d` Is Not an Older Equivalent of `2dsphere`

The same numbers `[106.7,10.776]` can appear in legacy format in both systems, yet:

- In `2d`, planar calculations treat them as two X/Y coordinates in the chosen planar system.
- In `2dsphere`, when used with valid geographic data, you are working with locations on Earth.

Thus, if the actual data is longitude/latitude, choosing `2d` merely because an old schema used `[x,y]` arrays leads to **wrong distance semantics**.

### 3.2. Coordinate Bounds of a `2d` Index

`2d` supports indexing options such as `min`, `max`, and `bits` to control the coordinate domain and spatial resolution. By default, the bounds target legacy geographic pairs; for planar coordinates outside the default range, you must declare an appropriate range.

Example for a floor plan with coordinates from 0 up to under 500 units:

```javascript
db.floorPoints.createIndex(
  { xy: "2d" },
  {
    min: 0,
    max: 500
  }
);
```

When choosing `min`/`max`:

1. Understand the application's **true coordinate domain**;
2. Leave room for layout expansion or coordinate shifts;
3. Data outside index bounds can cause index build or write errors;
4. Some configuration options affect resolution and index overhead;
5. Do not treat tuning `bits` as a way to fix invalid coordinates.

Do not stuff lon/lat coordinates into `2d` with arbitrary `min/max` bounds expecting meter-based queries like GeoJSON `2dsphere`.

## 4. Comparing `2dsphere` and `2d`

| Criterion | `2dsphere` | `2d` |
|---|---|---|
| Model | Geometry on an Earth-like sphere | Planar geometry |
| Typical use case | Earth maps, longitude/latitude | Floor plans, X/Y coordinates |
| Recommended data | GeoJSON Point/LineString/Polygon and supported types | Legacy coordinate pairs, supported legacy shapes |
| GeoJSON geometry | **Supported** | Not an index for GeoJSON geometries |
| `$near` | Supports geographic proximity queries | Supports planar proximity queries |
| `$geoWithin` | Supports appropriate spherical/GeoJSON regions | Supports legacy planar regions |
| `$geoIntersects` | **Index supports geometry intersection** | Not intended for GeoJSON intersection |
| `$geoNear` | Supported with an appropriate index | Supported with compatible near syntax and index |
| Distance unit | With GeoJSON Point and matching syntax, typically **meters** | In planar coordinate units |
| Proximity with lon/lat | Suitable | Should not replace spherical distance |
| Map polygon data | Suitable | More limited, planar/legacy model |
| Compound index | Has rules for compound `2dsphere` | Has restrictions on geo field position |
| Cost | Depends on geometry type / index keys / query | Depends on X/Y domain and query |
| Recommended for real delivery apps | Usually `2dsphere` | Only when intentionally using internal planar coordinates |

**Neither index is "faster in every case."** Compare **identical operations**, datasets, and documents processed—do not benchmark a single `find()` across incompatible schemas.

## 5. GeoJSON: Conventions That Must Be Exact

GeoJSON uses objects with `type` and `coordinates` (or corresponding fields depending on the geometry type).

### 5.1. Point

```javascript
{
  type: "Point",
  coordinates: [106.7000, 10.7760]
}
```

**The mandatory GeoJSON order is longitude first, latitude second.**

| Element | Meaning | Typical Geographic Domain |
|---|---|---|
| `coordinates[0]` | Longitude | −180 to +180 degrees |
| `coordinates[1]` | Latitude | −90 to +90 degrees |

Common mistake:

```javascript
{
  type: "Point",
  coordinates: [10.7760, 106.7000]
}
```

Here latitude is set to 106.7°, exceeding the valid latitude domain. MongoDB may reject the invalid geometry during indexing or querying.

**Do not validate coordinates simply by checking that an array has two numbers.** Validate both axis order and range bounds.

### 5.2. LineString

A path made up of multiple points:

```javascript
{
  type: "LineString",
  coordinates: [
    [106.6900, 10.7700],
    [106.7000, 10.7760],
    [106.7100, 10.7850]
  ]
}
```

A LineString represents a **line geometry**, not an arbitrary collection of unrelated points. When asking whether a route crosses a region, `$geoIntersects` with `2dsphere` is useful.

### 5.3. Polygon

A GeoJSON Polygon has an array of **linear rings**. Each ring is closed: the first and last coordinates match.

```javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.6800, 10.7600],
      [106.7200, 10.7600],
      [106.7200, 10.8000],
      [106.6800, 10.8000],
      [106.6800, 10.7600]
    ]
  ]
}
```

Array nesting:

```text
coordinates
  └── list of rings
        └── list of [longitude, latitude]
```

The outer ring defines the boundary; additional rings can represent **holes** when valid.

### 5.4. Validating Geometry

Before loading Polygons or MultiPolygons into a large collection, verify:

- Rings are properly closed;
- Enough distinct vertices exist;
- No unintended self-intersections occur;
- Longitude/latitude are not swapped;
- Consistent rules for winding and holes are followed;
- Degrees are not accidentally treated as meters;
- Overly complex geometries are avoided unless necessary;
- Regions crossing the ±180° meridian and polygons larger than a hemisphere follow MongoDB rules.

A syntactically valid JSON GeoJSON object is not guaranteed to be **geometrically** valid or business-accurate.

## 6. Sample Dataset for Real-World Location Queries

The following commands target the **test collection** `geoPlacesLab`. Only run `drop()` when you accept deleting all data in this lab collection.

```javascript
use geoIndexLab;

db.geoPlacesLab.drop();

db.geoPlacesLab.insertMany([
  {
    _id: "P01",
    name: "Point A",
    category: "service",
    tenantId: "T-01",
    location: {
      type: "Point",
      coordinates: [106.6950, 10.7760]
    }
  },
  {
    _id: "P02",
    name: "Point B",
    category: "service",
    tenantId: "T-01",
    location: {
      type: "Point",
      coordinates: [106.7050, 10.7790]
    }
  },
  {
    _id: "P03",
    name: "Point C",
    category: "shop",
    tenantId: "T-02",
    location: {
      type: "Point",
      coordinates: [106.7100, 10.7850]
    }
  },
  {
    _id: "P04",
    name: "Point D",
    category: "shop",
    tenantId: "T-02",
    location: {
      type: "Point",
      coordinates: [106.6800, 10.7650]
    }
  },
  {
    _id: "P05",
    name: "No coordinates yet",
    category: "service",
    tenantId: "T-03"
  }
]);

db.geoPlacesLab.createIndex({
  location: "2dsphere"
});
```

These coordinates are **illustrative query samples**, not a list of real commercial locations.

Document `P05` lacks `location`. This case is useful when discussing the sparse behavior of `2dsphere`.

### 6.1. Inspecting Created Indexes

```javascript
db.geoPlacesLab.getIndexes();
```

The output may show a default index name such as:

```text
location_2dsphere
```

Index names depend on creation syntax and options. Use `getIndexes()` to verify **actual state**, rather than assuming the previous command succeeded.

## 7. Finding Nearest Locations with `$near`

With a `2dsphere` index, use a GeoJSON Point as the center:

```javascript
db.geoPlacesLab.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7760]
      },
      $maxDistance: 3000
    }
  }
}).limit(10);
```

Meaning:

- The query center is the GeoJSON Point `[106.7000, 10.7760]`.
- `$maxDistance: 3000` means **3,000 meters** under `$near` semantics with GeoJSON.
- `$near` results are **sorted nearest first**.
- `.limit(10)` returns at most 10 matching points.
- MongoDB requires an appropriate geospatial index for this type of near query.

### 7.1. `$minDistance`

You can find points between 1,000 and 5,000 meters from the center:

```javascript
db.geoPlacesLab.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7760]
      },
      $minDistance: 1000,
      $maxDistance: 5000
    }
  }
});
```

This forms an annular/ring region in **geographic distance** around the center, not a rectangle on a map.

### 7.2. `$near` Does Not Return a Distance Field

A `$near` query sorts results by distance, but returned documents do not automatically receive a `distanceMeters` field just because `$near` was used.

If the application needs **the distance for each document**, use the `$geoNear` aggregation stage or compute it at the appropriate layer.

### 7.3. When Not to Use `$near`?

If the requirement is simply "all points inside a district/polygon region" **without needing distance sorting**, `$geoWithin` is usually more semantically accurate.

Do not use `$near` in a report fetching hundreds of thousands of points only to `.sort()` again by name; near-distance sorting adds unnecessary overhead.

## 8. Finding Points Inside a Polygon with `$geoWithin`

Suppose you want locations inside a rectangular region represented as a GeoJSON Polygon:

```javascript
const serviceArea = {
  type: "Polygon",
  coordinates: [
    [
      [106.6800, 10.7600],
      [106.7200, 10.7600],
      [106.7200, 10.8000],
      [106.6800, 10.8000],
      [106.6800, 10.7600]
    ]
  ]
};

db.geoPlacesLab.find({
  location: {
    $geoWithin: {
      $geometry: serviceArea
    }
  }
});
```

Meaning: find locations situated **inside the geometry region**.

### 8.1. `$geoWithin` vs. `$near`

| Question | Operator |
|---|---|
| "What are the 10 nearest points to the center within 3 km?" | `$near` |
| "Which points lie inside the delivery polygon?" | `$geoWithin` |
| "Which lines or regions intersect the search area?" | `$geoIntersects` |
| "Find nearby and return the computed distance?" | `$geoNear` |

`$geoWithin` **does not sort by distance**. If you need deterministic ordering for pagination, add an explicit sort and consider index and execution costs.

### 8.2. Is an Index Always Required?

Some `$geoWithin` queries can run without a geospatial index, but on large datasets scanning and checking many geometries can be very expensive. `2dsphere` generally improves efficiency when the data is Earth-based GeoJSON.

Do not infer from "the query ran" that "the planner used an index." Always check `explain()` on a realistic workload.

## 9. `$geoIntersects`: When Geometries Intersect

Another requirement:

> "Which shipping routes have at least a portion intersecting a maintenance zone?"

A `routesLab` collection with LineStrings:

```javascript
db.routesLab.insertMany([
  {
    _id: "R1",
    name: "Route A",
    path: {
      type: "LineString",
      coordinates: [
        [106.6900, 10.7700],
        [106.7100, 10.7900]
      ]
    }
  },
  {
    _id: "R2",
    name: "Route B",
    path: {
      type: "LineString",
      coordinates: [
        [106.7300, 10.8100],
        [106.7400, 10.8200]
      ]
    }
  }
]);

db.routesLab.createIndex({
  path: "2dsphere"
});
```

Query:

```javascript
const affectedArea = {
  type: "Polygon",
  coordinates: [
    [
      [106.6800, 10.7600],
      [106.7200, 10.7600],
      [106.7200, 10.8000],
      [106.6800, 10.8000],
      [106.6800, 10.7600]
    ]
  ]
};

db.routesLab.find({
  path: {
    $geoIntersects: {
      $geometry: affectedArea
    }
  }
});
```

Difference:

- `$geoWithin`: the stored geometry lies **inside** the query geometry.
- `$geoIntersects`: the stored geometry **intersects** the query geometry, even if not fully contained in it.

For example, a road crossing a polygon typically **intersects** without being **completely within** the polygon.

`2dsphere` is the right index for GeoJSON intersection queries. Do not port this query to a planar `2d` index expecting all spherical polygon/line semantics to stay the same.

## 10. `$geoNear` Aggregation: Returning Distance Too

When an API needs a "nearest" list along with the distance in meters, `$geoNear` is a natural fit.

```javascript
db.geoPlacesLab.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.7760]
      },
      key: "location",
      distanceField: "distanceMeters",
      spherical: true,
      maxDistance: 5000,
      query: {
        category: "service"
      }
    }
  },
  {
    $project: {
      _id: 1,
      name: 1,
      category: 1,
      distanceMeters: 1
    }
  },
  { $limit: 10 }
]);
```

Meaning:

- `near`: the search center.
- `key`: the geospatial indexed field used to compute distance.
- `distanceField`: output field containing distance per index/syntax semantics.
- `spherical: true`: uses spherical calculations per configuration.
- `maxDistance`: radius limit.
- `query`: additional attribute filter.
- `$project`: returns only needed fields.
- `$limit`: caps the number of results.

With GeoJSON Point and `2dsphere`, distance is generally expressed in **meters**.

### 10.1. `$geoNear` Must Be First in the Pipeline

In a standard aggregation pipeline, **`$geoNear` must be the first stage**. Do not write:

```javascript
db.geoPlacesLab.aggregate([
  { $match: { category: "service" } },
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.7760]
      },
      distanceField: "distanceMeters",
      spherical: true
    }
  }
]);
```

instead, place the filter inside `$geoNear`'s `query` option, as shown in the valid example above.

### 10.2. Why Specify `key`?

If a collection has multiple geospatial indexes, the router/planner needs to know which field represents the location for `$geoNear`. Specifying `key` removes ambiguity. It also clarifies query intent when a schema has:

```javascript
pickupLocation
deliveryLocation
warehouseLocation
```

Computing distance to a pickup point versus a delivery point are two distinct queries.

### 10.3. `$geoNear` Does Not Generate Routes

`distanceMeters` is not driving distance. If an API displays **estimated arrival time**, calculate it using a routing/travel-time system. MongoDB returns geographic distance, not traffic-aware road paths.

## 11. Planar Queries with a `2d` Index

Now let us build a collection for floor-plan X/Y coordinates.

```javascript
db.floorPointsLab.drop();

db.floorPointsLab.insertMany([
  {
    _id: "S1",
    floorId: "F1",
    xy: [10, 10],
    kind: "shelf"
  },
  {
    _id: "S2",
    floorId: "F1",
    xy: [30, 15],
    kind: "shelf"
  },
  {
    _id: "C1",
    floorId: "F1",
    xy: [80, 70],
    kind: "charger"
  },
  {
    _id: "S3",
    floorId: "F2",
    xy: [25, 25],
    kind: "shelf"
  }
]);

db.floorPointsLab.createIndex(
  { xy: "2d" },
  { min: 0, max: 500 }
);
```

Assume the X/Y unit is **meters** per the application's floor-plan design. Then a radius of 30 carries the meter unit of this coordinate system. If pixels are stored instead, a radius of 30 means pixels—it does not automatically become 30 meters.

### 11.1. `$near` in Planar Space

```javascript
db.floorPointsLab.find({
  xy: {
    $near: [20, 20],
    $maxDistance: 30
  }
}).limit(10);
```

This query finds points near `[20,20]` using **planar** distance based on the stored coordinates.

### 11.2. `$geoWithin` with `$box`

```javascript
db.floorPointsLab.find({
  xy: {
    $geoWithin: {
      $box: [
        [0, 0],
        [50, 50]
      ]
    }
  }
});
```

`$box` is a legacy rectangular region defined by two corners in planar coordinates. It is useful for finding robots or shelves inside a rectangular section of a floor plan.

### 11.3. `$geoWithin` with `$center`

```javascript
db.floorPointsLab.find({
  xy: {
    $geoWithin: {
      $center: [
        [20, 20],
        25
      ]
    }
  }
});
```

`$center` uses a **planar radius** in the same coordinate units, unlike `$centerSphere` which uses an angular radius on a spherical surface.

### 11.4. Do Not Mix Multiple Floor Plans into One X/Y System Unchecked

If Floor F1 and Floor F2 both have a point at `[25,25]`, a query filtering only by position can return data from both floors. Depending on business logic, add a filter:

```javascript
db.floorPointsLab.find({
  floorId: "F1",
  xy: {
    $near: [20, 20],
    $maxDistance: 25
  }
});
```

For optimization, consider a compound index suitable for the geo index type rather than relying purely on `floorId` under heavy workloads. A `2d` index has rules about the geo field's position in a compound index, covered in the next section.

## 12. Measurement Units: An Easy Silent Bug

A dangerous mistake is using the right operator with the wrong unit.

| Syntax / Case | Expected Unit |
|---|---|
| GeoJSON Point + `$near`/`$maxDistance` with `2dsphere` | Meters |
| GeoJSON Point + `$geoNear` on `2dsphere` | Meters for returned distance under GeoJSON semantics |
| `$centerSphere` | **Radians** for radius |
| `$center` on planar pairs | Planar coordinate units |
| `$near` on planar pairs with `2d` index | Planar coordinate units |
| Longitude/latitude in GeoJSON | **Degrees** for position, not meters |

### 12.1. `$centerSphere`: Radius Is in Radians

Suppose you want to find points within a 2 km radius around an Earth coordinate using `$centerSphere`.

Formula:

\[
\text{angularRadius (radian)} = \frac{\text{distanceMeters}}{\text{EarthRadiusMeters}}
\]

Sample code:

```javascript
const earthRadiusMeters = 6378100;
const targetRadiusMeters = 2000;
const angularRadius = targetRadiusMeters / earthRadiusMeters;

db.geoPlacesLab.find({
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.7000, 10.7760],
        angularRadius
      ]
    }
  }
});
```

**Do not pass `2000` directly as the `$centerSphere` radius** thinking MongoDB interprets it as 2,000 meters. Here the radius is in radians; with `$near` using a GeoJSON Point, `maxDistance` is in meters.

### 12.2. Same Number 100, Completely Different Meaning

```javascript
// 2dsphere / GeoJSON: approximately 100 meters.
$maxDistance: 100

// 2d / X-Y: approximately 100 floor-plan units.
$maxDistance: 100
```

`2d` data might use pixels, centimeters, meters, or game coordinates; MongoDB does not automatically know which unit it represents.

### 12.3. Swapped Lon/Lat Order

A real location `[106.7000,10.7760]` swapped to `[10.7760,106.7000]` produces a latitude exceeding 90°. However, some swapped coordinate pairs still **fall inside valid bounds**, making the bug hard to spot because the index builds and queries return results at the wrong place.

Schema validation and tests with known reference coordinates are essential rather than relying solely on server errors.

## 13. Which Geometry Should Be Stored?

### 13.1. Single Point

Stores, delivery hubs, pickup points, sensor locations:

```javascript
{
  type: "Point",
  coordinates: [longitude, latitude]
}
```

This is the most common model for near-search APIs. Use `2dsphere`.

### 13.2. Line

Vehicle routes, road segments, operating corridors:

```javascript
{
  type: "LineString",
  coordinates: [
    [106.69, 10.77],
    [106.70, 10.78]
  ]
}
```

For questions like "does the line intersect any zone?", use GeoJSON + `2dsphere` and the appropriate operator.

### 13.3. Region

Delivery areas, service zones, territories:

```javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.68, 10.76],
      [106.72, 10.76],
      [106.72, 10.80],
      [106.68, 10.80],
      [106.68, 10.76]
    ]
  ]
}
```

Clarify the query relationship:

- **A Point is inside a service area**;
- **A service area intersects another polygon**;
- **A service area contains a point**.

Which geometry is **stored in the field** and which is **passed in the query** can affect whether you choose `$geoWithin` or `$geoIntersects`. Do not swap the two geometries assuming the results will be identical.

### 13.4. X/Y Floor Plan

Robots, pallets, shelf coordinates on a flat map:

```javascript
{ xy: [125.5, 64.0] }
```

If business logic only requires Euclidean distance on a plane and does not need GeoJSON, `2d` is a candidate. If you need to represent complex planar lines or polygons under a custom model, verify legacy operator limitations or consider a dedicated planar geometry engine.

## 14. Compound Geospatial Indexes

Location is rarely the only filter. For example, an application may search for service points **belonging to the same tenant** near a user.

### 14.1. Compound `2dsphere`

You can create a compound index combining a regular field with a geospatial field:

```javascript
db.geoPlacesLab.createIndex({
  tenantId: 1,
  location: "2dsphere"
});
```

A query with both tenant and location:

```javascript
db.geoPlacesLab.find({
  tenantId: "T-01",
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7760]
      },
      $maxDistance: 5000
    }
  }
});
```

A compound index can help workloads that know `tenantId` before searching nearby locations, though planner choice still depends on selectivity, query shape, and statistics/other indexes.

**There is no rule saying "adding tenantId before geo makes every near query faster."** If most queries omit `tenantId`, a compound index optimized only for tenant-specific queries may not be the only index needed.

### 14.2. Compound `2dsphere` with Multiple Location Fields

Where supported by MongoDB, a compound `2dsphere` index can include multiple geospatial fields:

```javascript
db.shipments.createIndex({
  pickupLocation: "2dsphere",
  deliveryLocation: "2dsphere"
});
```

However, such designs complicate indexing and field selection for geospatial queries. If using `$geoNear` on a collection with multiple geospatial indexes/fields, declare `key` explicitly.

Do not assume a single index with two location fields automatically finds "nearest by both pickup and delivery" for every query.

### 14.3. Compound `2d` Has Restrictions on the Geo Field

A compound `2d` index has stricter rules: the `2d` geospatial field must appear **first** in the index key pattern under supported conditions.

Example:

```javascript
db.floorPointsLab.createIndex({
  xy: "2d",
  floorId: 1
});
```

Do not arbitrarily reverse the order:

```javascript
// Not a valid compound 2d configuration.
db.floorPointsLab.createIndex({
  floorId: 1,
  xy: "2d"
});
```

This difference is an important selection criterion when an application has many regular filters that need indexing.

### 14.4. Compound Indexes Do Not Replace All Other Indexes

Example:

```javascript
db.geoPlacesLab.find({
  tenantId: "T-01",
  category: "service"
});
```

has no geo predicate. This query may be better served by a standard index:

```javascript
db.geoPlacesLab.createIndex({
  tenantId: 1,
  category: 1
});
```

Geospatial indexes are designed to accelerate spatial queries, not to replace all B-tree indexes used for business listings, filters, and sorting.

## 15. Sparse Behavior of `2dsphere`

An easily overlooked detail: **`2dsphere` indexes have inherent sparse behavior**. Documents without a valid location according to index rules—for example, when the geo field is missing or null—may **not have an entry** in the geospatial index.

Example:

```javascript
{
  _id: "P05",
  name: "No coordinates yet",
  tenantId: "T-03"
}
```

With:

```javascript
db.geoPlacesLab.createIndex({
  location: "2dsphere"
});
```

document `P05` is not a point on the map, so it does not participate in proximity queries on `location`.

### 15.1. Compound `2dsphere` and Missing Location

Example:

```javascript
db.geoPlacesLab.createIndex({
  tenantId: 1,
  location: "2dsphere"
});
```

In a compound `2dsphere` index, the presence and indexability of the geospatial field determine whether a document gets a geospatial index entry—**not merely the existence of `tenantId`**.

Therefore, do not treat this compound index as a complete index over all documents of a tenant if some records lack a location.

### 15.2. Why Does This Matter?

Suppose a business has 1 million places, of which 100,000 do not yet have verified coordinates. A report asking "how many active places does the tenant have?" must not rely solely on scanning the `2dsphere` index assuming it contains every document.

The distinction between **all records** and **records with indexed locations** must be explicit in logic and metrics.

### 15.3. Distinguish Missing from Invalid Coordinates

A document missing `location` simply produces no geospatial index entry. A document that has `location` with malformed GeoJSON, out-of-range longitude/latitude, or an invalid polygon can cause **index creation or data writes to fail**.

Do not treat sparse behavior as a guarantee that MongoDB will "silently skip all bad geospatial data."

## 16. Invalid Data and Schema Validation

Geospatial data quality directly affects query results.

Invalid examples:

```javascript
// Wrong lat/lon order.
{
  location: {
    type: "Point",
    coordinates: [10.776, 106.700]
  }
}

// Missing one coordinate.
{
  location: {
    type: "Point",
    coordinates: [106.700]
  }
}

// Strings instead of numbers.
{
  location: {
    type: "Point",
    coordinates: ["106.700", "10.776"]
  }
}

// Unclosed Polygon ring.
{
  area: {
    type: "Polygon",
    coordinates: [
      [
        [106.68, 10.76],
        [106.72, 10.76],
        [106.72, 10.80]
      ]
    ]
  }
}
```

A schema validator can enforce:

- Required vs. optional fields;
- `type: "Point"` for point-only collections;
- `coordinates` is an array;
- Exactly two elements;
- Numeric element types;
- Longitude/latitude within allowed ranges.

For polygons, validating **topological geometry** goes beyond basic JSON Schema validation; consider a dedicated GeoJSON/geometry library during ingestion.

### 16.1. Point-Only Validator Example

```javascript
db.createCollection(
  "validatedPlacesLab",
  {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["name", "location"],
        properties: {
          name: {
            bsonType: "string"
          },
          location: {
            bsonType: "object",
            required: ["type", "coordinates"],
            properties: {
              type: {
                enum: ["Point"]
              },
              coordinates: {
                bsonType: "array",
                minItems: 2,
                maxItems: 2,
                items: {
                  bsonType: ["double", "int", "long", "decimal"]
                }
              }
            }
          }
        }
      }
    }
  }
);
```

This validator is **one structural validation layer**. It does not prove longitude is in `[−180,180]` and latitude is in `[−90,90]`, because positional constraints on array elements require additional expressions or API-level validation.

Do not present a basic validator as though it solves every geometric error.

## 17. Geometry Edge Cases

### 17.1. The ±180° Meridian (Antimeridian)

A region straddling the 180° meridian may contain points with longitudes near `+179°` and `−179°`. If a polygon is represented as a sequence of pairs without accounting for wrap-around, the resulting region can be completely different from what was intended.

For data near the antimeridian:

- Design polygons using spherical paths;
- Confirm exact GeoJSON interpretation;
- Test results using test points on both sides of ±180°;
- Avoid arbitrary flat bounding boxes on raw longitudes;
- Review MongoDB's winding and large-geometry requirements.

### 17.2. Regions Larger Than a Hemisphere

For certain large polygons, ring winding direction and spherical interior/complement rules affect which side is treated as "inside." MongoDB provides GeoJSON CRS/winding mechanisms for special cases per version documentation.

Do not use a Polygon spanning more than half the Earth without verifying semantics; for very large regions, modeling with multiple smaller Polygons or a MultiPolygon is often clearer.

### 17.3. Poles and High Latitudes

The ground distance between two longitudes does not correspond to the same number of meters at every latitude. That is why you should not approximate with `deltaLongitude * constant` globally and treat the result as accurate.

### 17.4. Elevation

A GeoJSON Position can contain a third element in certain contexts, but do not assume `2dsphere` queries automatically solve 3D distance problems accounting for altitude as in 3D Euclidean space.

If the system needs building floors, drone altitude, or ocean depth, design a **3D/vertical model** and dedicated algorithms or filters; `2dsphere` primarily serves 2D geographic geometry operations on a spherical surface.

## 18. Optimizing Queries and Reading Explain

A collection with a geospatial index can still be slow if:

- The search area is too large;
- Nearly every document falls inside the polygon;
- The query requires complex sorting or pagination;
- Geometries are overly complex;
- Many points/lines live in a single document;
- Too many results are returned;
- The query lacks selective tenant/category filters;
- The query does not use the intended index;
- Indexes are local while data is scattered across multiple shards.

### 18.1. Inspecting executionStats

```javascript
db.geoPlacesLab.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7760]
      },
      $maxDistance: 5000
    }
  }
}).limit(10).explain("executionStats");
```

Things to inspect:

| Metric | Meaning |
|---|---|
| `winningPlan` | Which access plan the query planner selected |
| Geospatial index stage | Whether an appropriate index was used |
| `totalKeysExamined` | Number of index entries scanned |
| `totalDocsExamined` | Number of documents examined |
| `nReturned` | Number of documents returned |
| `executionTimeMillis` | Execution time in the explain context |
| Filter/FETCH | Cost of inspecting documents outside the index |
| Sort/merge | Cost of sorting/merging results, if any |

Stage names and formats vary by MongoDB version and query engine; you may see stages related to geo near or index scans. Do not write monitoring code tightly coupled to a single stage name.

### 18.2. Testing with Realistic Data Distributions

A benchmark of 100 clustered documents does not represent a collection of 30 million points distributed nationwide.

Test:

1. Query centers in dense areas;
2. Query centers in sparse areas;
3. Small and large radii;
4. Simple and complex polygons;
5. Queries filtered by tenant/category;
6. Cases with many documents missing `location`;
7. Queries returning a handful of records vs. hundreds of thousands;
8. Concurrent requests under peak load.

### 18.3. `$near` Already Orders by Distance

If an API needs the 10 nearest points, let `$near`/`$geoNear` perform nearest selection and limit accordingly. Do not add an unnecessary sort on another attribute that disrupts nearest ordering.

If you need "the 10 nearest places with rating above 4, then prioritized by highest rating," clearly define precedence: **filtering rating before finding nearest** differs from **taking the 10 nearest and then sorting by rating**. The two queries return different result sets.

### 18.4. Radius and Result Counts Must Be Bounded

A "find places near me" endpoint should not accept an unbounded client-supplied `$maxDistance` and return millions of records. Enforce:

- Radius limits appropriate to the use case;
- Result count limits;
- Coordinate validation;
- Proper indexes;
- Intentional pagination/continuation strategies;
- Timeouts, rate limits, and monitoring.

## 19. Index Selection Rules by Use Case

### 19.1. Stores Around a User

Data:

```javascript
{
  location: {
    type: "Point",
    coordinates: [106.7000, 10.7760]
  }
}
```

Requirement:

```text
Find 20 stores near the user within a 5 km radius.
```

Choice: **`2dsphere`** with GeoJSON, using `$near` or `$geoNear`.

### 19.2. Delivery Coverage Polygon

Data:

```javascript
{
  serviceArea: {
    type: "Polygon",
    coordinates: [
      [
        [106.68, 10.76],
        [106.72, 10.76],
        [106.72, 10.80],
        [106.68, 10.80],
        [106.68, 10.76]
      ]
    ]
  }
}
```

Requirement:

```text
Find delivery zones intersecting a target area.
```

Choice: **`2dsphere`**, using `$geoIntersects`.

### 19.3. Robots on a Warehouse Floor Plan

Data:

```javascript
{
  floorId: "F1",
  xy: [34.5, 72.0]
}
```

Requirement:

```text
Find robots within 20 meters on the same floor,
using the floor plan's planar coordinate system.
```

Choice: **`2d`** if X/Y is truly planar and units are consistent, combined with a `floorId` filter.

### 19.4. Legacy GPS Data as `[lon,lat]`

Legacy data:

```javascript
{
  loc: [106.7000, 10.7760]
}
```

If the requirement involves Earth locations and distances in meters, consider **migrating to GeoJSON + `2dsphere`**.

MongoDB `2dsphere` also supports legacy coordinate pairs in certain cases, but modernizing the schema improves clarity and enables extended geometries. Do not switch indexes based solely on field names without testing query behavior.

### 19.5. Planar Map Needing Complex Polygons

If business logic requires complex polygon intersections in a **non-Earth** coordinate system, do not assume `2dsphere` will behave properly just because it supports GeoJSON. You may need a dedicated planar geometry engine, or to normalize the coordinate system and operation rules before choosing a MongoDB index.

`2d` supports limited legacy planar searches, not a full planar GIS engine for every operation.

## 20. Lon/Lat Order, Coordinate Systems, and Transformations

An application may receive coordinates from multiple systems:

- GPS: WGS84 longitude/latitude;
- Web maps rendering data through a projection;
- CAD drawings: X/Y coordinates with an arbitrary origin;
- Robots: local room coordinates;
- Sensor systems: centimeters or millimeters.

Never mix these values into a single `location` field and index it, because identical two-number arrays carry completely different meanings.

### 20.1. Web Map Coordinates Are Not Always Raw Longitude/Latitude

A web map may use a projection to render on screen. If an API provides X/Y in a projected coordinate system, transform it to GeoJSON longitude/latitude before using `2dsphere` with WGS84.

Never take viewport pixel coordinates and store them as `[longitude, latitude]`.

### 20.2. Coordinate System Metadata

For planar data:

```javascript
{
  floorId: "F1",
  xy: [34.5, 72.0],
  unit: "meter",
  coordinateSystem: "WAREHOUSE-F1-V2"
}
```

Metadata helps when floor plans change or different floors have different origins. However, a `2d` index only inspects the position field per schema; it does not automatically transform between coordinate systems.

If multiple floors use incompatible coordinate systems, queries must filter by the exact floor/map version.

## 21. `2dsphere` and Arrays / Multikey

A document can contain multiple locations or a complex GeoJSON geometry, depending on structures supported by MongoDB:

```javascript
{
  _id: "DELIVERY-01",
  stops: [
    {
      type: "Point",
      coordinates: [106.6900, 10.7700]
    },
    {
      type: "Point",
      coordinates: [106.7100, 10.7900]
    }
  ]
}
```

Create index:

```javascript
db.deliveries.createIndex({
  stops: "2dsphere"
});
```

How the index generates keys and supports arrays depends on the geometry and index type. A document with many points can generate many index entries and incur higher storage and write costs than a single Point.

### 21.1. Do Not Stuff 100,000 GPS Points into One Document Arbitrarily

If a vehicle trip has 100,000 positions, putting all points into one document can:

- Approach the BSON document size limit;
- Cause heavy document and index rewrites;
- Create numerous index entries;
- Cause write amplification;
- Make querying time windows per point difficult.

Consider **one document per point/event** (or an appropriate time-series design), simplified LineStrings for geometric paths, or storing raw tracks outside the proximity-queried collection.

### 21.2. `2dsphere` GeoJSON Is Not an Arbitrary X/Y Array

A field:

```javascript
[
  [106.6900, 10.7700],
  [106.7100, 10.7900]
]
```

should not be assumed automatically equivalent to a GeoJSON `LineString`. When representing a path, use an object with `type: "LineString"` and properly structured `coordinates`.

## 22. Geospatial in Sharded Collections

When a collection is sharded, distinguish between:

1. **Shard key**: routes documents and queries across shards.
2. **Geospatial index**: executes geo queries within the relevant shards.

A geospatial index is not automatically a valid shard key. MongoDB has explicit restrictions on **using a geospatial index as a shard key**: you cannot simply pick `{location:"2dsphere"}` as a shard key the way you pick a standard B-tree index.

### 22.1. Queries with Only a Geo Predicate Can Fan Out

Suppose a collection is sharded on:

```javascript
{ tenantId: 1 }
```

and has an index:

```javascript
{ location: "2dsphere" }
```

Query:

```javascript
db.geoPlaces.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7760]
      },
      $maxDistance: 3000
    }
  }
});
```

does not provide `tenantId`, so the router may need to contact multiple shards to find nearby points across the cluster. Having a good geo index on each shard **does not prevent fan-out**.

### 22.2. A Tenant Filter Changes Routing

```javascript
db.geoPlaces.find({
  tenantId: "T-01",
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7000, 10.7760]
      },
      $maxDistance: 3000
    }
  }
});
```

When `tenantId` is the shard key and the query supplies the required predicate, `mongos` can target the appropriate shard subset. `2dsphere` then handles **spatial filtering within the shard**.

Inspect the query planner and check geo/sharding constraints specific to the MongoDB version in use.

## 23. Java MongoDB Driver: Creating `2dsphere` and Near Queries

Java Sync Driver example using collections of `org.bson.Document`:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

import java.util.Arrays;

MongoDatabase database = mongoClient.getDatabase("geoIndexLab");

MongoCollection<Document> places =
    database.getCollection("geoPlacesLab");

// Create geospatial index for GeoJSON.
places.createIndex(Indexes.geo2dsphere("location"));

Document center = new Document("type", "Point")
    .append("coordinates", Arrays.asList(106.7000, 10.7760));

Document nearSpec = new Document("$geometry", center)
    .append("$maxDistance", 3000);

Document filter = new Document(
    "location",
    new Document("$near", nearSpec)
);

for (Document place : places.find(filter).limit(10)) {
    System.out.println(place.toJson());
}
```

The code above illustrates constructing the BSON query directly to observe MongoDB's structure. In production, you must:

- Manage the `MongoClient` lifecycle;
- Read coordinates from validated inputs;
- Use consistent field names;
- Handle exceptions and timeouts;
- Cap result counts;
- Avoid logging personal coordinates indiscriminately.

### 23.1. Java: `$geoNear` Aggregation

```java
import org.bson.Document;

import java.util.Arrays;

Document center = new Document("type", "Point")
    .append("coordinates", Arrays.asList(106.7000, 10.7760));

Document geoNear = new Document(
    "$geoNear",
    new Document("near", center)
        .append("key", "location")
        .append("distanceField", "distanceMeters")
        .append("spherical", true)
        .append("maxDistance", 3000)
        .append("query", new Document("category", "service"))
);

Document limit = new Document("$limit", 10);

for (Document result : places.aggregate(Arrays.asList(
        geoNear,
        limit))) {
    System.out.println(result.toJson());
}
```

If the collection has multiple geospatial fields/indexes, `key` selects the field to use. Results with GeoJSON + `2dsphere` return distance in meters.

### 23.2. Java: Compound Geospatial Index

```java
places.createIndex(
    Indexes.compoundIndex(
        Indexes.ascending("tenantId"),
        Indexes.geo2dsphere("location")
    )
);
```

Do not add redundant overlapping indexes in production without measuring write overhead and query plans.

### 23.3. Java: Representing `2d` Planar

For planar layouts, you can use a BSON Document:

```java
import com.mongodb.client.model.IndexOptions;
import org.bson.Document;

MongoCollection<Document> floorPoints =
    database.getCollection("floorPointsLab");

// MongoDB field type "2d" expressed explicitly.
floorPoints.createIndex(
    new Document("xy", "2d"),
    new IndexOptions()
);

Document xyFilter = new Document(
    "xy",
    new Document("$near", Arrays.asList(20.0, 20.0))
        .append("$maxDistance", 30.0)
);

for (Document point : floorPoints.find(xyFilter).limit(10)) {
    System.out.println(point.toJson());
}
```

To declare `min` and `max` for a `2d` index, use the options/API/BSON command supported by your driver version. Avoid mixing GeoJSON data with a `2d` index simply because both use Java `Document`.

## 24. Migrating from `2d` to `2dsphere`

Suppose a legacy system stores:

```javascript
{
  _id: 1,
  loc: [106.7000, 10.7760]
}
```

and has an index:

```javascript
db.places.createIndex({
  loc: "2d"
});
```

Business requirements now demand distances in meters on Earth, delivery polygons, and routes.

A safe migration should:

1. **Verify the domain and coordinate order** of legacy data is truly `[lon,lat]`, not `[lat,lon]`.
2. Count records with null, missing, or invalid coordinates.
3. Introduce a new field `location` as a GeoJSON Point.
4. Backfill data in batches with safety predicates.
5. Update write paths to populate `location` properly.
6. Build the `2dsphere` index on the new field.
7. Run shadow queries in staging and verify distances and targeting.
8. Switch read paths via feature flag or monitored rollout.
9. Once stable, consider dropping the legacy index/field when no consumers depend on it.

### 24.1. Do Not Simply Drop `2d` and Create `2dsphere` on the Same Field

If legacy data contains X/Y pairs that are not truly longitude/latitude, changing the index **alters the mathematical semantics** and can cause data errors.

If the data genuinely consists of legacy lon/lat pairs, MongoDB can build a `2dsphere` index on supported legacy representations, but applications should consider migrating to **standard GeoJSON** to avoid ambiguity and cleanly support Points, Lines, and Polygons.

### 24.2. Batch Backfilling Data

Idea using an aggregation update pipeline on a test collection:

```javascript
db.places.updateMany(
  {
    loc: { $type: "array" },
    location: { $exists: false }
  },
  [
    {
      $set: {
        location: {
          type: "Point",
          coordinates: "$loc"
        }
      }
    }
  ]
);
```

**Warning:** this snippet is only safe when `loc` is guaranteed to be an **array of two valid `[lon,lat]` numbers**. If legacy data has bad entries, clean them first; never run `updateMany` across all of production merely because a field has type `array`.

Monitor index size growth, oplog volume, replication lag, and write traffic during backfills.

## 25. Selection Criteria: Decision Workflow

Walk through these questions in order.

### Question 1 — What Is the Geometric Model?

- Real locations on Earth, lon/lat, spherical distance → prefer **`2dsphere`**.
- X/Y coordinates on an internal flat plane, Euclidean distance → consider **`2d`**.
- 3D space or projected CRSs with custom rules → define the model first; another engine may be needed.

### Question 2 — What Form Does the Data Take?

- GeoJSON Point/LineString/Polygon or supported GeoJSON types → **`2dsphere`**.
- Planar legacy coordinate pairs → **`2d`**.
- Legacy `[lon,lat]` representing Earth coordinates → consider **`2dsphere`** or migrating to GeoJSON.

### Question 3 — Which Operators Do the Queries Use?

- Nearest on Earth → `2dsphere` + `$near`/`$geoNear`.
- Inside an Earth polygon → `2dsphere` + `$geoWithin`.
- Intersecting lines/regions → `2dsphere` + `$geoIntersects`.
- Nearest on a floor plan → `2d` + planar `$near`.
- Planar rectangle/circle → `2d` + legacy `$geoWithin`.

### Question 4 — What Unit Must Be Returned?

- Meters in geographic queries → GeoJSON + `2dsphere`.
- CAD/pixel/internal meter units on a plane → `2d` with explicit schema units.
- Travel time / road distance → neither index solves this alone; a routing layer is needed.

### Question 5 — What Are the Filter and Data Characteristics?

- Are there `tenantId`/`category`/`status` filters?
- Do many documents lack `location`?
- Are multiple geometry types mixed in one field?
- Are there very many points in a single document?
- Is a compound index needed?
- Is the collection sharded?

### Question 6 — Has Performance Been Measured?

- Run `explain("executionStats")`;
- Test queries in dense and sparse areas;
- Measure p95/p99 latency and CPU/IOPS;
- Inspect index size;
- Test small and large `maxDistance` values;
- Check how many shards participate if sharded.

### Question 7 — Are There Edge Cases?

- Antimeridian;
- High latitudes;
- Polygons with holes;
- Oversized polygons;
- Swapped lat/lon data;
- Multiple floors or floor plans;
- Invalid geometries;
- Missing or null coordinates.

Only after answering these questions should you finalize the production index.

## 26. Common Misconceptions

| Misconception | Consequence | Correct Understanding |
|---|---|---|
| "2d and 2dsphere both index two numbers, so they are equivalent." | Wrong distance/geometry | Choose based on planar vs. spherical |
| "GeoJSON Point stores `[lat,lon]`." | Wrong point or index error | GeoJSON is `[lon,lat]` |
| "Degree coordinates are meters." | Wrong radius and distances | Distinguish units by operator |
| "`$centerSphere` takes a radius in meters." | Severely distorted query region | Radius is in radians |
| "2d works for all GeoJSON polygons." | Lacks required semantics | Use `2dsphere` for geographic GeoJSON |
| "`$near` needs an extra sort by distance." | Redundant sort or disrupted order | `$near` already returns nearest order |
| "`$geoWithin` automatically sorts nearest first." | Results lack expected ordering | Use `$near`/`$geoNear` |
| "`$geoNear` can be placed at any stage." | Pipeline error | Place `$geoNear` first in the pipeline |
| "`$near` always returns a distance field." | API missing distance | Use `$geoNear` if a distance field is needed |
| "Without a geo index, `$near` still works like a normal query." | Query error | Create the appropriate geo index |
| "A 2dsphere index includes every document even without a location." | Inaccurate record counts | `2dsphere` has sparse behavior |
| "Missing location and invalid GeoJSON behave the same." | Index build/write failures | Validate properly against schema |
| "Being close on a sphere means close by road." | Wrong ETA | Use a separate routing engine |
| "A compound index can freely place `2d` after tenant." | Invalid configuration | `2d` geo field must come first in compound |
| "Having 2dsphere makes tenant-only queries fast." | Suboptimal query plan | Add appropriate regular indexes |
| "A single geometry holding all points is cheaper than individual Points." | Huge index keys/payloads | Measure multi-point arrays and document size |
| "Just replacing `2d` with `2dsphere` completes a migration." | Wrong units and schema | Verify CRS, data, and queries |
| "A geo index routes queries on a sharded cluster." | Unexpected scatter-gather | Shard key is distinct from geospatial index |
| "`explain` only requires checking nReturned." | Misses scans and CPU cost | Check keys/docs examined and plan |
| "Web map pixel coordinates are longitude/latitude." | Wrong locations | Apply proper projection transform |

## 27. Hands-On Exercises

### Exercise 1 — Choose the Right Index

Given four problems:

1. Find stores within a 2 km radius around a customer.
2. Find robots within 15 units of `[100,200]` on a warehouse floor plan.
3. Find train lines intersecting a geographic Polygon.
4. Find shelf locations inside an X/Y rectangle on a floor plan.

For each case, select `2dsphere` or `2d`, the geometry type, operator, and unit.

### Exercise 2 — GeoJSON Coordinate Order

Given:

```javascript
{ type: "Point", coordinates: [10.776, 106.700] }
```

1. Which value is being interpreted as longitude?
2. Which value is latitude?
3. What is the specific error?
4. Fix it into valid GeoJSON.
5. Explain what happens when lon/lat are swapped yet both values remain within valid ranges.

### Exercise 3 — `$near` with `2dsphere`

Using `geoPlacesLab`:

1. Create a `2dsphere` index on `location`.
2. Find up to 10 points within a 3,000-meter radius.
3. Add `$minDistance: 500`.
4. Observe the order of results.
5. Use `explain` to verify index usage.

### Exercise 4 — `$geoWithin` and Polygon

1. Create a closed Polygon surrounding four points.
2. Query points lying inside the Polygon.
3. Reverse or reorder a few vertices and inspect the resulting shape.
4. Test a Polygon missing its closing vertex.
5. Explain why valid JSON GeoJSON is not guaranteed to be geometrically valid.

### Exercise 5 — `$geoIntersects`

Create two LineStrings and one Polygon.

1. Find lines intersecting the Polygon.
2. Compare with the question "line completely inside the Polygon."
3. Why can `$geoWithin` and `$geoIntersects` return different result sets?
4. Which index is most appropriate?

### Exercise 6 — `$geoNear` and Distance

Write an aggregation returning:

- Place name;
- Category;
- Distance in meters;
- 5,000-meter limit;
- At most 10 results.

Explain why `$geoNear` must normally be first in the pipeline and when `key` is needed.

### Exercise 7 — `2d` X/Y

Create `floorPointsLab` and a `2d` index with bounds 0–500.

1. Find points near `[20,20]`.
2. Find points inside `$box` `[[0,0],[50,50]]`.
3. Find points inside `$center` with radius 25.
4. Suppose the coordinate unit is pixels—what does the radius result mean?
5. Add a `floorId` filter so floors are not mixed.

### Exercise 8 — `$centerSphere`

An application needs to find points within 2,000 meters of a GeoJSON position.

1. Write the formula converting meters to radians.
2. Write the `$geoWithin` + `$centerSphere` query.
3. Explain how it differs from `$near` + `$maxDistance: 2000`.
4. What goes wrong if `2000` is passed directly as the `$centerSphere` radius?

### Exercise 9 — Sparse Behavior

A collection contains:

```javascript
[
  { _id: 1, location: { type: "Point", coordinates: [106.7,10.77] } },
  { _id: 2, location: null },
  { _id: 3 }
]
```

1. Which record has a valid geospatial position for indexing?
2. Why can you not use a geospatial index to count all records?
3. Does a compound `{tenantId:1,location:"2dsphere"}` index change the rule for indexing docs missing `location`?
4. Distinguish a missing field from a field containing invalid GeoJSON.

### Exercise 10 — Legacy Migration

From:

```javascript
{ loc: [106.7, 10.77] }
```

to:

```javascript
{
  location: {
    type: "Point",
    coordinates: [106.7, 10.77]
  }
}
```

Design a plan to verify lon/lat, backfill, build the index, test queries, roll out, and roll back. Why should you not `drop()` the legacy index before all consumers have migrated?

### Exercise 11 — Compound Indexes and Workloads

An application runs:

```javascript
db.places.find({
  tenantId: "T-01",
  location: {
    $near: {
      $geometry: { type: "Point", coordinates: [106.7,10.77] },
      $maxDistance: 2000
    }
  }
});
```

1. Compare `{location:"2dsphere"}` with `{tenantId:1,location:"2dsphere"}`.
2. If most queries do not include `tenantId`, what should you measure?
3. Why does a compound `2d` index not share the same key-order flexibility as a compound `2dsphere` index?
4. Is a plain `tenantId` index still needed?

### Exercise 12 — Antimeridian

A service area contains points near both `+179.8°` and `−179.8°`.

1. Why can a flat bounding box on longitude fail?
2. Which geometric model should be used to validate the polygon?
3. Which test points are needed?
4. Why should you not blindly add `360°` to all longitudes without understanding the CRS?

### Exercise 13 — Sharded Cluster

A collection is sharded on `tenantId` but has `location` indexed with `2dsphere`.

1. How many shards can a geo-only query on `location` hit?
2. How does adding `tenantId` to the filter change routing?
3. Why does a `2dsphere` index not replace a shard key?
4. What information should you inspect in `explain` on each shard?

### Exercise 14 — Protecting a Nearby API

Design an endpoint:

```text
GET /places/nearby?lon=...&lat=...&radiusMeters=...
```

Specify:

- Longitude/latitude validation;
- Maximum radius cap;
- Index type;
- `$near` or `$geoNear` query;
- Result limit;
- Caching strategy;
- Rate limiting;
- When to call a routing engine for ETA;
- Key p95/p99 metrics to monitor.

## 28. MongoDB Reference Documentation

- [Geospatial Queries](https://www.mongodb.com/docs/manual/geospatial-queries/)
- [2dsphere Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/)
- [2d Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2d/)
- [GeoJSON Objects](https://www.mongodb.com/docs/manual/reference/geojson/)
- [Geospatial Query Operators](https://www.mongodb.com/docs/manual/reference/operator/query-geospatial/)
- [$near](https://www.mongodb.com/docs/manual/reference/operator/query/near/)
- [$nearSphere](https://www.mongodb.com/docs/manual/reference/operator/query/nearSphere/)
- [$geoWithin](https://www.mongodb.com/docs/manual/reference/operator/query/geoWithin/)
- [$geoIntersects](https://www.mongodb.com/docs/manual/reference/operator/query/geoIntersects/)
- [$geoNear Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/geoNear/)
- [$centerSphere](https://www.mongodb.com/docs/manual/reference/operator/query/centerSphere/)
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)

## Conclusion

**`2dsphere`** is the sensible default for most applications working with **geographic coordinates on Earth**, GeoJSON Point/LineString/Polygon geometries, and queries such as finding nearby locations, containment within a region, or intersection with a region. For GeoJSON Points, store coordinates in **`[longitude, latitude]`** order, validate ranges, and understand distance units (typically meters for nearest operators using GeoJSON).

**`2d`** fits when data consists of **planar X/Y coordinates** and the application needs Euclidean measurements in a flat system with well-defined units. It is not an interchangeable substitute for all geographic geometries and spherical distances.

Beyond the geometric model, inspect **query patterns, compound indexes, sparse behavior, GeoJSON validity, geometry size, antimeridian handling, sharding, latency, and API limits**. Never choose an index purely by its name or because a query worked on a handful of test documents.

**Choosing correctly starts with answering: "Do these two numbers live on an internal flat plane or describe a position on Earth, and what question does the application truly need to ask about them?"**
