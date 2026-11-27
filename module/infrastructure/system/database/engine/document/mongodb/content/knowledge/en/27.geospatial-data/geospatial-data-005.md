# Proximity Queries with `$near`, `$nearSphere`, and the `$geoNear` Stage in MongoDB

## 1. Problem: Finding Places Near a Location

Suppose an application stores pickup point locations on a map. A user sends their current coordinates and wants to find the **10 nearest active points within a 3 km radius**, while displaying the distance to each point.

A document might be stored as:

```javascript
{
  _id: ObjectId("66a000000000000000000295"),
  name: "Pickup Point A",
  category: "pickup",
  status: "OPEN",
  location: {
    type: "Point",
    coordinates: [106.7009, 10.7769]
  }
}
```

In MongoDB, this problem should not be solved by reading every document into the application, computing distances manually for each point, and sorting. MongoDB has **geospatial indexes** and proximity query mechanisms:

- **`$near`**: a query predicate operator in `find()` that selects locations near a given point and sorts them automatically from nearest to farthest.
- **`$nearSphere`**: a query predicate operator in `find()` that explicitly emphasizes spherical geometry distance calculation.
- **`$geoNear`**: an **aggregation pipeline stage** that finds nearest documents and can output the computed distance field for downstream processing with `$project`, `$group`, `$limit`, and other stages.

These three mechanisms serve different API design patterns. With **GeoJSON Point + `2dsphere` index**, both `$near` and `$nearSphere` use spherical geometry; do not assume `$near` always computes planar distance.

After completing this lesson in MongoDB's **Geospatial Data** chapter, you will be able to:

1. Store GeoJSON Points with the proper structure and coordinate order.
2. Select geospatial indexes appropriate for GeoJSON and legacy coordinate pairs.
3. Write `$near` and `$nearSphere` queries with `$geometry`, `$minDistance`, and `$maxDistance`.
4. Use `$geoNear` with `near`, `distanceField`, `spherical`, `key`, `query`, and `distanceMultiplier`.
5. Distinguish **meters**, **radians**, **coordinate degrees**, and **kilometers**.
6. Combine filter predicates, result limits, and subsequent aggregation stages.
7. Avoid missing-index errors, invalid stage ordering, or confusing straight-line distance with actual travel distance.
8. Evaluate performance, security, and result handling in a Node.js API.

## 2. Representing Coordinates with GeoJSON

### 2.1. A GeoJSON Point Is a Structured Object

MongoDB can store a geographic position in GeoJSON:

```javascript
{
  location: {
    type: "Point",
    coordinates: [106.7009, 10.7769]
  }
}
```

Inside the `coordinates` array:

```text
coordinates: [ longitude, latitude ]
               east-west  north-south
```

This is a common source of confusion: many map APIs or user interfaces accept parameters in **latitude, longitude** order, but GeoJSON must store **longitude first, latitude second**.

Example:

```javascript
// CORRECT: [longitude, latitude]
{ type: "Point", coordinates: [106.7009, 10.7769] }

// WRONG in this example: swapped to [latitude, longitude]
{ type: "Point", coordinates: [10.7769, 106.7009] }
```

In geographic GeoJSON, longitude ranges from **-180 to 180**, and latitude ranges from **-90 to 90**. Swapped coordinates may be rejected for out-of-range latitude, or worse: remain two valid numbers that point to **a completely different place**.

The coordinates in this lesson are **simulated data around an urban area** for query practice; point names do not represent real businesses.

### 2.2. Why Use GeoJSON Instead of Two Separate Fields?

A less favorable design for geospatial queries:

```javascript
{
  latitude: 10.7769,
  longitude: 106.7009
}
```

An application can store those two numbers for UI display or integration, but to use a `2dsphere` index and the operators in this lesson, maintain a clear GeoJSON field:

```javascript
{
  location: {
    type: "Point",
    coordinates: [106.7009, 10.7769]
  }
}
```

GeoJSON also includes other geometry types such as `LineString`, `Polygon`, and `MultiPoint`. However, the **reference point** parameter for `$near`, `$nearSphere`, and `$geoNear` queries in recent MongoDB versions must be a **GeoJSON `Point`**, not an arbitrary Polygon passed as the center.

### 2.3. WGS84, Degrees, and Distance

Geographic GeoJSON coordinates are typically expressed in WGS84 with longitude and latitude in **degrees**. Yet in proximity queries where `$geometry` is a GeoJSON Point, `$minDistance` and `$maxDistance` are measured in **meters**.

Therefore:

```text
coordinates: [106.7009, 10.7769]  -> lon/lat degrees
maxDistance: 3000                 -> 3,000 meters
distanceField: "distanceMeters"    -> distance in meters
```

Do not use `0.03` degrees to approximate a `3 km` radius. One degree of longitude does not correspond to a fixed number of meters across all latitudes.

### 2.4. Coordinates Are Neither Street Addresses Nor Travel Routes

Geospatial distance computed from coordinates is **geometric geographic distance** on a sphere or plane depending on the index type, not:

- walking distance along streets;
- driving time during rush hour;
- distance avoiding rivers, bridges, or one-way streets;
- drivable routes along a road network;
- elevation or depth in an arbitrary 3D model.

If an application wants "the 10 stores fastest to walk to," the MongoDB query can fetch a **geographically nearby candidate set**, and then a **routing service** computes real travel times and paths before final ranking.

## 3. Geospatial Indexes: `2dsphere` and `2d`

### 3.1. `2dsphere` Index for Geographic Coordinates

Create index:

```javascript
db.pickupPoints.createIndex({
  location: "2dsphere"
});
```

`2dsphere` supports geographic queries on a spherical model and works with GeoJSON objects or legacy coordinate pairs under appropriate conditions.

It is the standard choice for:

- pickup/dropoff points near a user;
- retail stores near GPS coordinates;
- points of interest (POIs);
- vehicles, devices, and service points;
- geographic regions and spatial queries on Earth's surface.

Do not create a regular `{location:1}` index and expect `$near` to use it as a geospatial index. You need the **right index type**.

### 3.2. `2d` Index for Planar Space and Legacy Coordinates

A legacy coordinate pair has the form:

```javascript
{
  pos: [10, 20]
}
```

If the data represents points on a **Cartesian plane** or a legacy project uses legacy coordinates, you can create:

```javascript
db.legacyPoints.createIndex({
  pos: "2d"
});
```

With legacy data, distance calculations and **distance-limit units** must follow the exact syntax, operator, and index rules of your MongoDB version. Do not copy meter parameters from a GeoJSON query directly onto legacy pairs assuming equivalent results.

If the actual data is latitude/longitude on Earth, `2dsphere` and GeoJSON provide a clearer design that avoids planar distortion over large distances or near the poles and antimeridian.

### 3.3. Quick Comparison

| Criterion | `2dsphere` | `2d` |
| --- | --- | --- |
| Primary model | Spherical geometry | Planar geometry |
| Data | GeoJSON; also supports legacy coordinates | Typically legacy coordinate pairs |
| Used with GeoJSON `Point` in `$near` | Yes | No; GeoJSON `$near` requires `2dsphere` |
| Querying GPS locations on Earth | Usually suitable | Not the default choice |
| Querying x-y coordinates on a flat drawing | Not the primary target | Better suited |
| Output distance unit | Depends on operator and input format; meters for GeoJSON geographic examples | Depends on legacy/planar semantics |

**Do not conflate indexes and operators**: `$nearSphere` does not mean MongoDB has a separate index type named `nearSphere`. It is an **operator**, and still requires a compatible geospatial index.

### 3.4. Invalid Data Can Cause Index Creation to Fail

Errors to catch before creating a `2dsphere` index:

- The `coordinates` field is not a properly structured array.
- Longitude/latitude values are out of valid bounds.
- Strings are stored instead of numbers.
- Invalid or incompatible GeoJSON `type`.
- GeoJSON with empty coordinates or wrong array nesting.
- Uncontrolled mixing of multiple representations in the same field.

Examples that should be rejected at the API layer:

```javascript
{ type: "Point", coordinates: ["106.7", "10.77"] }
{ type: "Point", coordinates: [106.7, 102.0] }
{ type: "Point", coordinates: [null, 10.77] }
{ type: "LineString", coordinates: [106.7, 10.77] }
```

A document missing `location` behaves differently during indexing from a field that **has a malformed value**. `2dsphere` indexes are sparse, but that does not mean MongoDB automatically repairs invalid GeoJSON.

### 3.5. Compound Geospatial Indexes

If most queries filter by status as well as proximity:

```javascript
db.pickupPoints.createIndex({
  status: 1,
  location: "2dsphere"
});
```

Or with multi-tenant data:

```javascript
db.pickupPoints.createIndex({
  tenantId: 1,
  location: "2dsphere"
});
```

A compound index can help certain filter-plus-proximity patterns. However, effectiveness depends on **the query, data distribution, field order, index planner, and MongoDB version**. There is no rule saying "adding every field to a compound index always makes it faster."

When a geospatial index includes regular fields, understand MongoDB's sparse rules and index bounds. For multi-tenant data, ensure queries always include the authenticated tenant filter, even if the index does not cover every predicate.

## 4. The `$near` Operator: Finding and Sorting by Distance

### 4.1. GeoJSON Syntax

Suppose a collection stores `location` as a GeoJSON Point and has an index:

```javascript
db.pickupPoints.createIndex({
  location: "2dsphere"
});
```

Query:

```javascript
const center = {
  type: "Point",
  coordinates: [106.7009, 10.7769]
};

db.pickupPoints.find({
  location: {
    $near: {
      $geometry: center,
      $maxDistance: 3000
    }
  }
});
```

Meaning:

1. Take the reference point `center`.
2. Evaluate document positions via the `2dsphere` index.
3. Include only points within at most **3,000 meters**.
4. Return documents ordered **nearest to farthest**.

For GeoJSON, `$near` uses **spherical distance calculation**, not flat subtraction of longitude and latitude.

### 4.2. Adding a Minimum Distance

```javascript
db.pickupPoints.find({
  location: {
    $near: {
      $geometry: center,
      $minDistance: 500,
      $maxDistance: 3000
    }
  }
});
```

Results fall within an **annulus (ring)** at least 500 m and at most 3 km away.

Use cases:

- excluding overly close points already served by another workflow;
- finding nearby resources not right next to the user's coordinates;
- building min/max radius filters.

With GPS data, positioning error can reach several meters or more; do not treat tiny distance boundaries as an exact physical line.

### 4.3. Adding Business Filters

```javascript
db.pickupPoints.find({
  status: "OPEN",
  category: "pickup",
  location: {
    $near: {
      $geometry: center,
      $maxDistance: 3000
    }
  }
}).limit(10);
```

The `status` and `category` conditions do not change distance semantics. MongoDB returns matching documents sorted nearest → farthest.

In a multi-tenant system:

```javascript
db.pickupPoints.find({
  tenantId: authenticatedTenantId,
  status: "OPEN",
  location: {
    $near: {
      $geometry: center,
      $maxDistance: 3000
    }
  }
}).limit(10);
```

**Never take `tenantId` from an unauthenticated client parameter** to partition sensitive data. Geospatial indexes speed up lookup, but authorization must be enforced in filters and the service layer.

### 4.4. Does `$near` Return a Numeric Distance Field?

`$near` in `find()` guarantees **distance ordering** but does not automatically attach a `distanceMeters` field to each returned document for display.

If you need to display:

```text
Point A    420 m
Point B    815 m
Point C  1,350 m
```

use the **`$geoNear` stage** with `distanceField`, or another explicit distance calculation controlled by the application. Do not infer distances solely from array position.

### 4.5. No Second `sort()` Needed for Distance Ordering

`$near` **already sorts nearest to farthest**. Example:

```javascript
// Usually unnecessary when the goal is simply "nearest".
db.pickupPoints.find({
  location: {
    $near: {
      $geometry: center,
      $maxDistance: 3000
    }
  }
}).sort({ name: 1 });
```

Adding `sort({name:1})` **re-sorts results by name**, discarding the "nearest first" order. It can also add extra sorting cost.

If you need multi-criteria prioritization such as "open, nearby, high rating," design a transparent scoring/pipeline balancing geospatial sorting, filters, and candidate limits.

### 4.6. Do Not Use `$near` as an Arbitrary Predicate in Aggregation

`$near` is a **query predicate operator** for match commands like `find()`. MongoDB does not allow using it inside `$match` in an aggregation pipeline:

```javascript
// Not the right pattern for proximity queries in aggregation:
db.pickupPoints.aggregate([
  {
    $match: {
      location: {
        $near: {
          $geometry: center,
          $maxDistance: 3000
        }
      }
    }
  }
]);
```

When you need a pipeline, start with `$geoNear`.

## 5. The `$nearSphere` Operator: Spherical Distance

### 5.1. Syntax with GeoJSON

```javascript
db.pickupPoints.find({
  location: {
    $nearSphere: {
      $geometry: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      $maxDistance: 3000
    }
  }
});
```

With a GeoJSON Point and a `2dsphere` index:

- `$nearSphere` sorts results by **spherical distance**.
- `$maxDistance` and `$minDistance` are expressed in **meters**.
- Other field filters can be combined.
- Results are sorted nearest to farthest.

### 5.2. Comparing `$near` and `$nearSphere` on GeoJSON

If two queries use the **same reference point**, the **same `2dsphere` index**, the **same filters**, and the **same distance bounds**, they produce virtually identical behavior because on GeoJSON, `$near` also uses spherical geometry.

```javascript
// Query A
{
  location: {
    $near: {
      $geometry: center,
      $maxDistance: 3000
    }
  }
}

// Query B
{
  location: {
    $nearSphere: {
      $geometry: center,
      $maxDistance: 3000
    }
  }
}
```

Do not teach the false rule "`$near` always measures straight lines on a plane while `$nearSphere` measures on a sphere." That rule ignores **input type** and **index type**.

### 5.3. Main Difference Appears with Legacy Coordinates

When the data and reference point are **legacy coordinate pairs**:

- `$near` with `2d` has planar geometry semantics.
- `$nearSphere` requests spherical distance and uses legacy syntax/units.
- `$nearSphere` can use a `2d` index for legacy coordinate pairs under MongoDB-supported conditions.
- With legacy `$nearSphere`, distance bounds are typically specified in **radians**.

Example in a separate collection with a `2d` index:

```javascript
// Legacy data, syntax illustration only.
db.legacyPlaces.createIndex({ pos: "2d" });

db.legacyPlaces.find({
  pos: {
    $nearSphere: [106.7009, 10.7769],
    $maxDistance: 0.0005
  }
});
```

`0.0005` in the legacy example is **not 0.0005 meters**; it follows the query's radian semantics. For new GPS problems, use GeoJSON Point with `2dsphere` to avoid unnecessary unit mixing.

### 5.4. Radians and Unit Conversion

To illustrate approximate surface distance on a sphere:

\[
d_{\text{meters}} \approx \theta_{\text{radians}} \times R_{\text{Earth}}
\]

Using an approximate Earth radius:

\[
R \approx 6\,371\,000\ \text{m}
\]

For example, `0.0005` radians corresponds to roughly **3.2 km** under that radius assumption. This is an approximation for understanding units, **not** a guaranteed exact conversion for every geodesic model or road map.

For a `$nearSphere` query **using GeoJSON `$geometry`**, pass `$maxDistance: 3200` for a 3.2 km radius; **do not divide 3,200 by 6,371,000** and pass that into a GeoJSON parameter.

## 6. Decision Matrix: `$near`, `$nearSphere`, and `$geoNear`

| Requirement | `$near` | `$nearSphere` | `$geoNear` |
| --- | --- | --- | --- |
| Find nearest in `find()` | Suitable | Suitable | Not a `find()` predicate |
| GeoJSON Point, `2dsphere` index | Yes | Yes | Yes |
| Return results nearest to farthest | Yes | Yes | Yes |
| Filter by min/max distance | Yes | Yes | Yes |
| Automatically add distance field to output | No | No | **Yes**, via `distanceField` |
| Combine with `$project` / `$group` / `$lookup` | Not directly a pipeline stage | Not directly a pipeline stage | Yes, after `$geoNear` stage |
| Reference point is a GeoJSON Point | Yes | Yes | Yes |
| Legacy coordinate pairs model | Yes, depending on index | Yes, spherical semantics | Yes, depending on index/options |
| Requires `$geoNear` first in pipeline | Not applicable | Not applicable | **Mandatory** |
| Convert output to km via multiplier | Compute in application | Compute in application | Has `distanceMultiplier` |
| Filter a region **without distance sorting** | Incurs unnecessary sort cost | Incurs unnecessary sort cost | Incurs nearest sort cost |

If you only want "which points fall within this radius" **without nearest → farthest ordering**, consider `$geoWithin` with an appropriate shape, because `$near` and `$nearSphere` carry **distance sorting** semantics and may incur unnecessary overhead.

## 7. The `$geoNear` Stage: Proximity Queries in Aggregation Pipelines

### 7.1. When Should You Use `$geoNear`?

An API needs results like:

```javascript
{
  name: "Pickup Point A",
  distanceMeters: 420.7,
  distanceKm: 0.421,
  category: "pickup"
}
```

If you use `$near` in `find()`, you get documents sorted by distance without an automatic `distanceMeters` field. `$geoNear` solves this by:

1. Finding documents near the point.
2. Computing the distance.
3. Writing the distance to a field.
4. Returning results ordered nearest to farthest.
5. Passing documents to subsequent stages for further processing.

### 7.2. Basic Syntax

```javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      distanceField: "distanceMeters",
      maxDistance: 3000,
      spherical: true,
      key: "location"
    }
  },
  { $limit: 10 },
  {
    $project: {
      _id: 1,
      name: 1,
      category: 1,
      status: 1,
      distanceMeters: 1,
      location: 1
    }
  }
]);
```

Meaning:

- `near`: the reference point.
- `distanceField`: name of the output field containing the distance.
- `maxDistance`: maximum limit, in **meters** when `near` is a GeoJSON Point.
- `spherical: true`: explicitly selects spherical geometry calculation.
- `key: "location"`: identifies the geospatial indexed field.
- `$limit`: caps the number of nearest results.
- `$project`: returns only fields needed by the API.

### 7.3. `$geoNear` Must Be the First Stage

Correct:

```javascript
db.pickupPoints.aggregate([
  { $geoNear: { near: center, key: "location",
                distanceField: "distanceMeters", spherical: true } },
  { $match: { status: "OPEN" } },
  { $limit: 10 }
]);
```

Incorrect:

```javascript
db.pickupPoints.aggregate([
  { $match: { status: "OPEN" } },
  { $geoNear: { near: center, key: "location",
                distanceField: "distanceMeters", spherical: true } }
]);
```

MongoDB requires `$geoNear` to be **the first stage of the pipeline containing it**. If you need to filter documents semantically upfront, use the `query` field **inside `$geoNear`** instead of placing `$match` before it.

Note: `$geoNear` can also appear as the first stage of a **nested pipeline** in certain supported contexts, such as inside `$lookup`. The rule is first stage in **its respective pipeline**, not necessarily the top of the outermost command.

### 7.4. Filtering in the Right Place with `query`

```javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceMeters",
      spherical: true,
      maxDistance: 3000,
      query: {
        status: "OPEN",
        category: "pickup"
      }
    }
  },
  { $limit: 10 }
]);
```

`query` can contain standard MongoDB filter conditions, but **must not contain another `$near` predicate inside `query`**. When queries enforce tenant or access-control conditions, keep them right at the data source:

```javascript
query: {
  tenantId: authenticatedTenantId,
  status: "OPEN"
}
```

A `$match` placed late in the pipeline after outputting all candidates does not have the same performance or correctness properties as placing the filter inside `$geoNear.query`. In particular, putting `$limit` before `$match` can drop valid results and return too few items.

### 7.5. `distanceField` Across MongoDB Versions

`distanceField` outputs the numeric distance for display. In **MongoDB prior to 8.1**, it is a required field in standard `$geoNear` syntax. **Starting in MongoDB 8.1**, this field may be **optional on non-time-series collections**, though `$geoNear` queries on time-series collections still require `distanceField` per current documentation.

In this lesson and most real-world applications, **explicitly specify `distanceField`** so that:

- the API receives the computed distance;
- cross-version compatibility is preserved;
- there is no confusion when results omit a distance field.

Do not assume that because `distanceField` can be optional in a newer release, older versions accept omitting it as well.

### 7.6. `key` When a Collection Has Multiple Geospatial Indexes

Suppose each place stores both a store location and a parking location:

```javascript
db.pickupPoints.createIndex({
  location: "2dsphere"
});

db.pickupPoints.createIndex({
  parkingLocation: "2dsphere"
});
```

Now `$geoNear` needs to know **which field to measure distance against**:

```javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceToPickupMeters",
      spherical: true
    }
  }
]);
```

If a collection has multiple matching geospatial indexes and `key` is omitted, MongoDB may throw an error due to ambiguity. Specifying `key` explicitly is clearer and avoids coupling to how many indexes happen to exist on the collection.

### 7.7. `includeLocs`: Which Position Was Used for Calculation?

If a document contains multiple positions in the same geospatial field, MongoDB can compute distance using the closest one. The `includeLocs` option reveals which location participated in the distance calculation:

```javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "geo.distanceMeters",
      includeLocs: "geo.matchedLocation",
      spherical: true
    }
  },
  {
    $project: {
      name: 1,
      location: 1,
      geo: 1
    }
  }
]);
```

Do not overwrite critical business fields or create conflicting paths in output documents. Standardize `distanceField` and `includeLocs` names in API responses.

### 7.8. `distanceMultiplier`: Converting Meters to Kilometers

With a GeoJSON Point + `2dsphere` index, distance is expressed in **meters**. To return kilometers:

```javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceKm",
      distanceMultiplier: 0.001,
      maxDistance: 3000,
      spherical: true
    }
  },
  { $limit: 10 }
]);
```

Example:

```text
Initial computed distance:  1500 m
distanceMultiplier:         0.001
distanceKm value:           1.5
```

**Note:** `distanceMultiplier` scales the **output distance value**; it **does not change the unit of `maxDistance` to kilometers**. In the example, you still pass `maxDistance: 3000` for a 3 km radius.

With **legacy coordinates**, distances may be returned/computed in **radians** under spherical semantics, where the conversion factor is not `0.001`. Always verify input format and units before applying a multiplier.

### 7.9. `minDistance`, `maxDistance`, and Annular Regions

```javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceMeters",
      minDistance: 1000,
      maxDistance: 5000,
      spherical: true
    }
  }
]);
```

This query selects points between roughly **1 km and 5 km**, sorted nearest to farthest within the matching set. This is useful when tiering service levels or bucketing by distance rings.

When administrative boundaries apply, geometric distance does not replace rules like "in district X," "inside service area," or "across a restricted bridge/road." Additional filters or a spatial intersection check may be required.

## 8. Complete `mongosh` Lab: Simulated Service Points

### 8.1. Preparing an Isolated Database

The examples use **simulated data** only; they contain no real user home coordinates or real business addresses. Run only on a test MongoDB instance you are permitted to modify.

Connect:

```bash
mongosh "mongodb://127.0.0.1:27017/"
```

In the shell:

```javascript
const lab = db.getSiblingDB("mongo_geo_row295_lab");
const places = lab.getCollection("places_demo");
const runId = "row295-" + new ObjectId().toHexString();

const center = {
  type: "Point",
  coordinates: [106.7009, 10.7769]
};

print("database=" + lab.getName());
print("collection=" + places.getName());
print("runId=" + runId);
```

`runId` scopes queries and cleanup strictly to the documents from **this lab run**, avoiding interference with other data.

### 8.2. Inserting Sample Points

```javascript
const samples = [
  {
    _id: new ObjectId(),
    runId,
    code: "LAB-295-A",
    name: "Simulated Point A",
    category: "pickup",
    status: "OPEN",
    rating: 4.8,
    location: {
      type: "Point",
      coordinates: [106.7009, 10.7769]
    }
  },
  {
    _id: new ObjectId(),
    runId,
    code: "LAB-295-B",
    name: "Simulated Point B",
    category: "pickup",
    status: "OPEN",
    rating: 4.5,
    location: {
      type: "Point",
      coordinates: [106.7045, 10.7778]
    }
  },
  {
    _id: new ObjectId(),
    runId,
    code: "LAB-295-C",
    name: "Simulated Point C",
    category: "pickup",
    status: "CLOSED",
    rating: 4.9,
    location: {
      type: "Point",
      coordinates: [106.7080, 10.7750]
    }
  },
  {
    _id: new ObjectId(),
    runId,
    code: "LAB-295-D",
    name: "Simulated Point D",
    category: "locker",
    status: "OPEN",
    rating: 4.2,
    location: {
      type: "Point",
      coordinates: [106.6950, 10.7800]
    }
  },
  {
    _id: new ObjectId(),
    runId,
    code: "LAB-295-E",
    name: "Simulated Point E",
    category: "pickup",
    status: "OPEN",
    rating: 4.7,
    location: {
      type: "Point",
      coordinates: [106.7290, 10.7900]
    }
  }
];

const insertResult = places.insertMany(samples);
printjson(insertResult);
printjson(
  places.find(
    { runId },
    { code: 1, name: 1, status: 1, location: 1 }
  ).toArray()
);
```

Coordinates are demo values for comparing near-query logic; do not interpret them as exact locations of any real business.

### 8.3. Creating the `2dsphere` Index

```javascript
places.createIndex(
  { location: "2dsphere" },
  { name: "location_2dsphere" }
);

printjson(places.getIndexes());
```

Creating the index after inserting in the lab highlights the two distinct parts: **GeoJSON data** and the **geospatial index**. In production, index build order, migrations, and system load must be planned; building an index on a large collection can consume significant I/O and time.

### 8.4. Finding Nearest Points with `$near`

```javascript
const nearest = places.find(
  {
    runId,
    location: {
      $near: {
        $geometry: center,
        $maxDistance: 3000
      }
    }
  },
  {
    code: 1,
    name: 1,
    status: 1,
    location: 1
  }
).limit(10).toArray();

printjson(nearest);
```

Results include only documents for `runId` within the requested radius, ordered nearest to farthest, though without a quantitative distance field.

### 8.5. Similar Query Using `$nearSphere`

```javascript
printjson(
  places.find({
    runId,
    status: "OPEN",
    location: {
      $nearSphere: {
        $geometry: center,
        $maxDistance: 3000
      }
    }
  }).limit(10).toArray()
);
```

With GeoJSON and a `2dsphere` index, results generally match `$near` when filters are identical. Here `status:"OPEN"` was added, so do not compare two outputs with different filters and attribute the difference to the operators.

### 8.6. Using `$geoNear` to Retrieve Distance Too

```javascript
const nearbyOpen = places.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 3000,
      spherical: true,
      query: {
        runId,
        status: "OPEN"
      }
    }
  },
  { $limit: 10 },
  {
    $project: {
      _id: 0,
      code: 1,
      name: 1,
      category: 1,
      status: 1,
      distanceMeters: { $round: ["$distanceMeters", 1] },
      distanceKm: {
        $round: [{ $divide: ["$distanceMeters", 1000] }, 3]
      }
    }
  }
]).toArray();

printjson(nearbyOpen);
```

Here:

- `query` filters by `runId` and status.
- `distanceField` generates the distance in meters.
- `$limit` caps the number of nearest points.
- `$project` formats both meters and km after computation.
- `$round` is for display formatting only and does not alter how MongoDB picks the nearest points.

If `$project` strips `distanceMeters` too early, subsequent stages will lack the field to convert to km or apply further filtering.

### 8.7. Filtering by Both Category and Distance

```javascript
printjson(
  places.aggregate([
    {
      $geoNear: {
        near: center,
        key: "location",
        distanceField: "distanceMeters",
        maxDistance: 5000,
        spherical: true,
        query: {
          runId,
          status: "OPEN",
          category: "pickup"
        }
      }
    },
    { $limit: 3 },
    {
      $project: {
        _id: 0,
        code: 1,
        name: 1,
        distanceMeters: 1
      }
    }
  ]).toArray()
);
```

Semantically: returns at most the **3 nearest OPEN pickup points** within a 5 km radius. Reordering `$limit:3` **before filtering category** could pick three general points and then filter some out, returning fewer results than requested.

### 8.8. Counting Points Within a Radius

`$geoNear` no longer imposes the 100-document default cap found in some older versions/mechanisms. To count within range:

```javascript
const counts = places.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 3000,
      spherical: true,
      query: { runId }
    }
  },
  { $count: "totalWithin3Km" }
]).toArray();

printjson(counts);
```

This counts using `$geoNear` while still carrying search-and-distance-calculation semantics. If you only need region membership, consider `$geoWithin` to avoid unnecessary sorting overhead.

### 8.9. Safe Cleanup of Test Data

Before cleaning up:

```javascript
print("database=" + lab.getName());
print("collection=" + places.getName());
print("runId=" + runId);

const ownDocs = places.find(
  { runId },
  { _id: 1, runId: 1, code: 1 }
).toArray();

printjson(ownDocs);
```

Only after confirming `ownDocs` contains the documents you created:

```javascript
for (const doc of ownDocs) {
  const removed = places.deleteOne({
    _id: doc._id,
    runId
  });
  print(doc.code + ": deleted=" + removed.deletedCount);
}

print("remaining=" + places.countDocuments({ runId }));
```

Do not run `deleteMany({})`, `dropDatabase()`, or `drop()` in a shared environment. The `location_2dsphere` index can remain on the demo collection after deleting documents; do not drop someone else's index.

## 9. Advanced Practice: Ranking by Distance and Status

### 9.1. Goal: Prioritize OPEN, Nearby, Then Rating

Suppose an API wants **only OPEN points** within a 5 km radius, ordered by distance first, and by rating on ties.

You can write:

```javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceMeters",
      spherical: true,
      maxDistance: 5000,
      query: { status: "OPEN" }
    }
  },
  {
    $sort: {
      distanceMeters: 1,
      rating: -1,
      _id: 1
    }
  },
  { $limit: 20 }
]);
```

**Trade-off:** `$geoNear` already produces nearest-to-farthest order, while a second `$sort` can consume extra resources; use it when you need a **deterministic tie-breaker**. On very large datasets, bound the search region, inspect the execution plan, and verify cursor stability.

Do not expect MongoDB to treat two distances as "equal" just because they look close on a map; two floating-point values can differ by a tiny fraction.

### 9.2. Selecting N Nearby Candidates Then Computing Complex Ranking

A recommendation algorithm might:

1. Use `$geoNear` to fetch **N valid points within radius**.
2. Compute a business score based on inventory, opening hours, and rating.
3. Select at most K results.

```javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 5000,
      spherical: true,
      query: { status: "OPEN" }
    }
  },
  { $limit: 100 },
  {
    $addFields: {
      score: {
        $subtract: [
          { $multiply: ["$rating", 10] },
          { $divide: ["$distanceMeters", 100] }
        ]
      }
    }
  },
  { $sort: { score: -1, _id: 1 } },
  { $limit: 10 }
]);
```

This is an **illustrative formula**, not a recommended production ranking function. Notice the key point: `$limit:100` before scoring builds a candidate pool of the **100 nearest points**, so the 101st-nearest point with an extremely high rating will **never have a chance** to be selected.

To balance distance and quality fairly, define the candidate set trade-off explicitly with business stakeholders—do not let `$limit` silently change the definition of "top K."

### 9.3. Finding Nearest Within Each Place Category

Suppose you want up to three nearest points **per category**:

```javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 10000,
      spherical: true,
      query: { status: "OPEN" }
    }
  },
  {
    $setWindowFields: {
      partitionBy: "$category",
      sortBy: { distanceMeters: 1, _id: 1 },
      output: {
        rankInCategory: { $documentNumber: {} }
      }
    }
  },
  { $match: { rankInCategory: { $lte: 3 } } },
  {
    $project: {
      name: 1,
      category: 1,
      distanceMeters: 1,
      rankInCategory: 1
    }
  }
]);
```

`$setWindowFields` must only be used on MongoDB versions supporting it; it may require extra sorting and memory. If you do not need top-N per group, do not add a complex window stage just to find a single overall nearest point.

## 10. `$geoNear` and `$lookup`: Dynamic Reference Locations

Some applications need to find nearby locations for **many different origin points**. On supported MongoDB versions, `$geoNear` can be used inside a **`$lookup` pipeline**, passing the reference location via `let`:

```javascript
db.deliveryRequests.aggregate([
  {
    $lookup: {
      from: "pickupPoints",
      let: {
        requestPoint: "$pickupLocation"
      },
      pipeline: [
        {
          $geoNear: {
            near: "$$requestPoint",
            key: "location",
            distanceField: "distanceMeters",
            maxDistance: 3000,
            spherical: true,
            query: {
              status: "OPEN"
            }
          }
        },
        { $limit: 3 },
        {
          $project: {
            _id: 1,
            name: 1,
            distanceMeters: 1
          }
        }
      ],
      as: "nearbyPickupPoints"
    }
  }
]);
```

Key points:

- `$geoNear` must still be the **first stage in the nested lookup pipeline**.
- `near` can reference a variable bound via `let` in supported versions.
- Every input document can trigger a geospatial lookup; on large input sets, total cost can be high.
- If tenant isolation is required, the inner `query`/pipeline must also enforce safe tenant conditions rather than filtering only the parent collection.
- Both collections must use the right geospatial indexed fields and namespaces.

Do not use this `$lookup` pattern to replace a complex dispatch/routing optimization system across millions of requests and points; benchmark realistic workloads to decide on batching, caching, or precomputed candidates.

## 11. Performance and Execution Plans

### 11.1. What Happens Without a Geospatial Index?

`$near`, `$nearSphere`, and `$geoNear` all require an **appropriate geospatial index**. Without one, the server returns an error indicating no supporting index was found.

Example:

```javascript
// Prerequisite for the GeoJSON examples.
db.pickupPoints.createIndex({ location: "2dsphere" });
```

Do not think `$geoNear` can bypass an index by calculating distances across all documents; it will not work as expected without a proper geospatial index.

### 11.2. Larger Radii Mean Larger Candidate Sets

A query like:

```javascript
{
  location: {
    $near: {
      $geometry: center,
      $maxDistance: 5000000
    }
  }
}
```

opens up a search spanning thousands of kilometers. On large collections, candidate count, sorting cost, and resource consumption can surge dramatically.

In a "near me" API:

- Cap `maxDistance` by product requirements (e.g., a few km or tens of km); never trust arbitrary client-supplied values.
- Cap result counts and page sizes.
- Query only necessary fields and categories.
- Throttle repeated ultra-wide queries from a single client.
- Monitor index usage, p95/p99 latency, and documents/index keys examined.

Recent MongoDB versions also enforce memory limits on nearest-query processing in certain cases; check your server version rather than assuming a near query can buffer unlimited results for sorting.

### 11.3. `explain()` for `find()`

```javascript
db.pickupPoints.find({
  status: "OPEN",
  location: {
    $near: {
      $geometry: center,
      $maxDistance: 3000
    }
  }
}).explain("executionStats");
```

When reading the output, check:

- Which geospatial index was used?
- Is there evidence of a geospatial index scan?
- Total documents examined and keys examined?
- Query execution time?
- Is there an extra sort stage?
- Where is the `status` filter applied?

Internal stage names in `explain` change across MongoDB versions and query engines; avoid writing monitoring parsers tied rigidly to a single stage name string.

### 11.4. `explain()` for Aggregation

```javascript
db.pickupPoints.explain("executionStats").aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 3000,
      spherical: true,
      query: {
        status: "OPEN"
      }
    }
  },
  { $limit: 10 }
]);
```

In production, running heavy `explain` queries still incurs cost. Run them in staging or on controlled valid queries—never run a worldwide scan repeatedly just to gather stats.

### 11.5. Index Overhead and Write Throughput

A `2dsphere` index accelerates near queries but consumes storage and incurs index update overhead whenever documents move.

If a collection tracks vehicle locations updating several times per second across millions of devices:

- every location update modifies index entries;
- write throughput can become a bottleneck;
- TTL and data lifecycle policies should be considered;
- separating current location from historical locations may be necessary;
- frequent top-nearest reads need caching or rate limiting.

Do not create geospatial indexes on every location field unless there are actual spatial queries against it.

### 11.6. Choosing Multi-Tenant Indexes

For a large multi-tenant collection:

```javascript
db.pickupPoints.createIndex({
  tenantId: 1,
  location: "2dsphere"
});
```

may be worth evaluating if queries always include `tenantId`. Measure the interplay between tenant selectivity, bounding distance, and spatial point distribution.

In particular:

- Indexes do not replace access control.
- Creating multiple compound indexes increases storage and write amplification.
- Queries without a geospatial predicate may still need a separate regular index.
- On sharded collections, query targeting also depends on the **shard key**, not just the `2dsphere` index.

### 11.7. Sharding and Geospatial Queries

A sharded collection can still have a geospatial index and support proximity queries, but:

- A geo index is not a valid shard key by itself.
- `mongos` may need to query multiple shards and merge/sort results.
- Filters containing the shard key can help routing if version rules are satisfied.
- Shard count and point distribution affect latency.
- Zone and tenant isolation policies must still be enforced.

Choosing a shard key for location lookups is a separate problem from choosing a geospatial index. Never assume `location:"2dsphere"` works as a collection shard key.

## 12. Pagination and Stable Ordering

### 12.1. `limit` Is the Starting Point

```javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceMeters",
      spherical: true,
      maxDistance: 10000
    }
  },
  { $limit: 20 }
]);
```

This is the classic query for "top 20 nearest."

### 12.2. `skip` Is Expensive at Large Offsets

```javascript
db.pickupPoints.aggregate([
  {
    $geoNear: {
      near: center,
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 10000,
      spherical: true
    }
  },
  { $skip: 10000 },
  { $limit: 20 }
]);
```

To skip 10,000 results, the server may still have to process all preceding candidates. Therefore, deep offset pagination is usually unsuitable for applications with millions of points.

### 12.3. Moving Data Shifts Page Boundaries

If a user is moving or resources update locations continuously:

```text
Page 1 at T0: A, B, C
Page 2 at T1: D, E, F
```

Between T0 and T1, point G moves closer or B is deleted; result order shifts, causing duplicates or skipped items across pages.

Solutions depending on requirements:

- Pin the `center` coordinate and filters across the pagination session.
- Maintain an appropriate snapshot/cursor if supported by the API.
- Use a stable tie-breaker such as `distanceMeters` plus `_id`, evaluating sort cost.
- For highly volatile datasets, consider returning top-N "near me" rather than supporting deep offset pagination.
- If results must remain immutable across pages, materialize a candidate ID list at a point in time with a managed TTL.

Never use `_id` alone as a continuation token for **distance** ordering, because `_id` order does not correspond to geographic order.

## 13. Node.js API: Input Validation and Proximity Queries

### 13.1. Suggested Contract

Example:

```text
GET /pickup-points/nearby?longitude=106.7009&latitude=10.7769&radiusMeters=3000&limit=10
```

Parameters to validate:

- `longitude`: finite number in `[-180, 180]`.
- `latitude`: finite number in `[-90, 90]`.
- `radiusMeters`: non-negative finite number not exceeding the product cap.
- `limit`: positive integer within allowed bounds.
- `tenantId`/`userId`: taken from authentication context, never from arbitrary query strings.

Never accept a raw MongoDB filter object from the client and pass it straight into `$geoNear.query`, as that opens injection and unauthorized data access risks.

### 13.2. Example Service Function

Assume `collection` is a MongoDB Node.js driver collection with a `2dsphere` index on `location`:

```javascript
function assertFiniteNumber(value, name) {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    throw new Error("INVALID_" + name);
  }

  return number;
}

function parseNearbyInput(input) {
  const longitude = assertFiniteNumber(input.longitude, "LONGITUDE");
  const latitude = assertFiniteNumber(input.latitude, "LATITUDE");
  const radiusMeters = assertFiniteNumber(input.radiusMeters, "RADIUS");
  const limit = Number(input.limit ?? 10);

  if (longitude < -180 || longitude > 180) {
    throw new Error("LONGITUDE_OUT_OF_RANGE");
  }
  if (latitude < -90 || latitude > 90) {
    throw new Error("LATITUDE_OUT_OF_RANGE");
  }
  if (radiusMeters < 0 || radiusMeters > 20000) {
    throw new Error("RADIUS_OUT_OF_RANGE");
  }
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > 50) {
    throw new Error("LIMIT_OUT_OF_RANGE");
  }

  return { longitude, latitude, radiusMeters, limit };
}

async function findNearbyPickupPoints(
  collection,
  input,
  authenticatedTenantId
) {
  const { longitude, latitude, radiusMeters, limit } =
    parseNearbyInput(input);

  const center = {
    type: "Point",
    coordinates: [longitude, latitude]
  };

  const pipeline = [
    {
      $geoNear: {
        near: center,
        key: "location",
        distanceField: "distanceMeters",
        spherical: true,
        maxDistance: radiusMeters,
        query: {
          tenantId: authenticatedTenantId,
          status: "OPEN",
          category: "pickup"
        }
      }
    },
    { $limit: limit },
    {
      $project: {
        _id: 1,
        name: 1,
        category: 1,
        distanceMeters: {
          $round: ["$distanceMeters", 1]
        },
        longitude: {
          $arrayElemAt: ["$location.coordinates", 0]
        },
        latitude: {
          $arrayElemAt: ["$location.coordinates", 1]
        }
      }
    }
  ];

  return collection.aggregate(pipeline).toArray();
}
```

This is a **service illustration**, not complete production code. In real requests:

- Authenticate and authorize the tenant before calling the function.
- Guard against `Number(undefined)` or `Number(null)` silently becoming `0`: check that **required parameters are present** before parsing if the API does not allow defaults.
- Catch validation errors and return clear HTTP status codes.
- Configure timeouts, rate limits, and monitoring.
- When handling sensitive data, limit the GPS precision written to logs.

### 13.3. Example Service Invocation

```javascript
const results = await findNearbyPickupPoints(
  db.collection("pickupPoints"),
  {
    longitude: "106.7009",
    latitude: "10.7769",
    radiusMeters: "3000",
    limit: "10"
  },
  authenticatedTenantId
);

console.log(results);
```

A result might include a document such as:

```javascript
{
  _id: ObjectId("66a000000000000000000295"),
  name: "Pickup Point A",
  category: "pickup",
  distanceMeters: 421.6,
  longitude: 106.7045,
  latitude: 10.7778
}
```

The distance in the sample response only illustrates shape; actual numbers are computed by MongoDB from coordinates and data.

### 13.4. Distinguishing Invalid Input, Index Errors, and Timeouts

An API should classify failures properly:

| Error | Meaning | Handling |
| --- | --- | --- |
| Longitude/latitude out of range | Invalid request | Return validation error; do not query DB |
| `radiusMeters` exceeds cap | Unacceptable request | Return radius limit error |
| Missing `2dsphere` index | Schema/configuration error | Fix migration/index; do not report "no places found" |
| Malformed GeoJSON in stored data | Corrupt source data | Clean/migrate data and add schema validation |
| Query timeout | Heavy load, wide area, or incident | Reduce scope, inspect index/latency, retry carefully |
| No matching points | Valid empty result | Return empty array with clear contract |
| Unauthorized tenant | Authorization error | Never leak points outside authorized scope |

Never return "no places near you" when the server actually failed due to a missing index or invalid pipeline.

## 14. Comparing `$geoNear` with `$geoWithin` and `$geoIntersects`

### 14.1. Different Operators Serve Different Purposes

| Requirement | Appropriate Tool |
| --- | --- |
| Find the 10 nearest points | `$near` / `$nearSphere` |
| Find nearest and return distance in a pipeline | `$geoNear` |
| Check which points **lie inside a region** | `$geoWithin` |
| Find geometries intersecting another shape | `$geoIntersects` |
| Count points in a circle without distance sorting | `$geoWithin` with an appropriate circular shape |
| Compute driving time to a point | Not a standalone MongoDB geo query; needs a routing/graph service |

### 14.2. `$geoWithin` for Circles When Sorting Is Not Needed

MongoDB supports `$centerSphere` using `[longitude, latitude]` as center and **radius in radians**:

```javascript
const earthRadiusMeters = 6371000;
const radiusMeters = 3000;

db.pickupPoints.find({
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.7009, 10.7769],
        radiusMeters / earthRadiusMeters
      ]
    }
  }
});
```

This differs from `$near`:

- It tests membership inside a circle.
- It **does not sort nearest to farthest**.
- The radius of `$centerSphere` is in **radians**, not meters.

Therefore, never pass `3000` directly into `$centerSphere`'s radius parameter thinking it means 3 km.

### 14.3. `$geoIntersects` for Coverage Areas

If a system stores delivery zones as GeoJSON Polygons:

```javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.68, 10.76],
      [106.72, 10.76],
      [106.72, 10.79],
      [106.68, 10.79],
      [106.68, 10.76]
    ]
  ]
}
```

you may need to query whether a coverage zone contains or intersects a point or line. `$geoIntersects` answers a different question from "which point is nearest?". Polygons must obey structure, ring closure, and coordinate order; queries searching for covering service zones need an appropriate data model.

### 14.4. Combining Proximity and Service Regions

A pickup point near a user is not necessarily **eligible to serve** that user due to administrative or operational constraints.

A common architecture:

1. Find nearby candidates with `$geoNear` and status filters.
2. Check service-area / geofencing logic.
3. Check inventory and operating hours.
4. If needed, call a routing system to compute real ETA.
5. Return compliant results per contract.

Never take the geographically closest point and automatically assume it is optimal or valid for every transaction.

## 15. Accuracy, GPS Data, and Location Privacy

### 15.1. GPS Has Measurement Error

A device may report:

```javascript
{
  latitude: 10.7769,
  longitude: 106.7009,
  accuracyMeters: 40
}
```

This means the measured location carries uncertainty; do not interpret a "2 m distance" result as a crisp boundary between "inside zone" and "outside zone."

For delivery apps, you can:

- use a search radius wider than positioning error;
- require address confirmation;
- store `accuracyMeters` to explain GPS quality;
- avoid using a single raw GPS distance alone as proof of physical presence.

### 15.2. Longitude/Latitude Are Not Pixel Coordinates

Map coordinates may pass through coordinate reference systems and projections (such as converting to web map pixels). Never take tile or pixel coordinates, store them as GeoJSON longitude/latitude, and expect `2dsphere` to understand them.

If the data source uses a specialized planar coordinate system, **transform the coordinates** according to proper rules before storing geographic GeoJSON.

### 15.3. Not Every Circle on a Map Is Drivable

A 3 km circle can cross rivers, lakes, highways, or administrative borders. Spherical proximity does not reflect:

- actual drivable roads;
- travel duration;
- tolls;
- vehicle restrictions;
- operating conditions at a specific time.

MongoDB excels at finding **geographic candidates**, whereas routes and ETAs require a dedicated routing system.

### 15.4. Privacy and Sensitive Location Data

Precise coordinates can be sensitive personal or commercial data. Design considerations:

- Collect location only with proper purpose and consent.
- Do not log exact GPS coordinates in default access logs.
- Restrict read permissions and retention periods.
- Round or bucket coordinates when the UI does not require meter-level precision.
- Never allow an API to query another user's location simply by changing `tenantId`/`userId`.
- Enforce rate limits to deter location scraping or trilateration.
- Protect data when forwarding to third parties (routing, analytics).

Correctness of a geospatial index does not replace security and privacy policy.

## 16. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Storing `[latitude, longitude]` instead of `[longitude, latitude]` | Wrong location or coordinate error | Normalize GeoJSON and validate |
| Passing `$maxDistance: 3` intending 3 km | Searches only 3 meters for GeoJSON | Pass `3000` meters |
| Using `$near` without a geospatial index | Query error | Create an appropriate `2dsphere` index |
| Creating a regular `{location:1}` index and calling `$near` | Index lacks geo semantics | Use `{location:"2dsphere"}` |
| Thinking `$near` is always planar and `$nearSphere` is always spherical | False for GeoJSON and `2dsphere` | Check input format and index type |
| Using legacy pairs and interpreting radius as GeoJSON meters | Wrong search radius | Understand legacy/radian units |
| Using `$near` inside an aggregation `$match` | Not supported | Use `$geoNear` as the first stage |
| Placing `$match` before `$geoNear` | Invalid pipeline | Move filters into `$geoNear.query` |
| Omitting `key` when multiple geo indexes exist | Query may fail or be ambiguous | Specify the indexed field explicitly |
| Omitting `distanceField` on older servers | Invalid pipeline | Explicitly specify the distance field |
| Using `distanceMultiplier:0.001` and switching `maxDistance` to km | Wrong radius filter | GeoJSON filter still uses meters |
| Using `sort({name:1})` after `$near` expecting nearest-first | Breaks distance ordering | Do not re-sort unless intentional |
| Applying `$limit` before status/category filters | May return fewer valid items | Filter inside query before limit |
| Treating spherical distance as driving distance | Inaccurate ETA | Use a routing service |
| Assuming GPS is exact | Unstable boundary decisions | Account for accuracy and buffers |
| Returning all points within thousands of km | High CPU, memory, and network cost | Cap radius and result count |
| Deep pagination via `$skip` on huge nearest sets | High latency | Prefer top-N caps or snapshot/cursor |
| Treating `location:"2dsphere"` as a valid shard key directly | Confuses geo index with shard key | Design a separate shard key |
| Relying solely on a geospatial index for tenant isolation | Cross-tenant data leak | Enforce authorization filters |
| Treating `updateLookup` or stale records as current position | Moving targets go stale | Define TTL and freshness rules |
| Dropping the entire collection after a lab | May wipe other users' data | Clean up strictly by `_id` + `runId` |

## 17. Self-Study Exercises

### Exercise A. Choosing the Right Coordinate Order

A point has:

```text
latitude  = 10.7769
longitude = 106.7009
```

Write the correct GeoJSON Point and explain why `[10.7769, 106.7009]` is wrong.

### Exercise B. `$near` Within a 2 km Radius

A `shops` collection has a GeoJSON Point `location` field and a `2dsphere` index. Write a `find()` query:

- Center `[106.7009,10.7769]`.
- Radius 2 km.
- Only `status:"OPEN"`.
- Return at most 15 nearest documents.

### Exercise C. Comparing `$near` and `$nearSphere`

On the same `2dsphere` index and the same GeoJSON input:

1. Is it true that `$near` always computes planar distance?
2. Why is `$nearSphere` helpful for code readability regarding spherical geometry?
3. When switching to legacy pairs + a `2d` index, what must be revisited?

### Exercise D. `$geoNear` and Distance in Kilometers

Write a pipeline that:

- Has `$geoNear` as the first stage.
- Filters `category:"locker"`.
- Caps radius at 5 km.
- Returns `name`, `distanceMeters`, and `distanceKm`.
- Limits to the 5 nearest points.

Explain why `maxDistance` must still be `5000` even when `distanceMultiplier:0.001` is set.

### Exercise E. Wrong Pipeline Order

Snippet:

```javascript
db.shops.aggregate([
  { $match: { status: "OPEN" } },
  {
    $geoNear: {
      near: center,
      distanceField: "d",
      spherical: true
    }
  }
]);
```

Rewrite it so the pipeline is syntactically valid while preserving the filter for OPEN shops.

### Exercise F. Multiple Geospatial Indexes

A collection has:

```javascript
db.shops.createIndex({ storeLocation: "2dsphere" });
db.shops.createIndex({ parkingLocation: "2dsphere" });
```

To measure distance to the store rather than the parking lot, which option must `$geoNear` include and why?

### Exercise G. Legacy Units

A developer copies `$nearSphere` syntax for legacy coordinate pairs and sets `$maxDistance:3000` to search within 3 km. Find the flaw in that reasoning and show a GeoJSON + `2dsphere` design that avoids unit confusion.

### Exercise H. Region Search Without Distance Sorting

A statistics job only needs to count shops within a 10 km circle; ordering does not matter. Evaluate `$near`, `$geoNear`, and `$geoWithin`, and explain the sorting trade-off.

### Exercise I. Optimizing Multi-Tenant Queries

A collection has 20 million points, with hundreds of thousands per tenant. The API always provides an authenticated `tenantId`, `status:"OPEN"`, and a location.

Propose:

- How to place filters in `$geoNear`.
- Two candidate indexes to benchmark.
- Caps for `radiusMeters` and `limit`.
- Metrics from `explain("executionStats")` to inspect.
- Why indexes alone cannot serve as the entire tenant-isolation mechanism.

### Exercise J. Geographic Distance vs. ETA

Two points:

```text
Point A: 700 m as the crow flies, must detour across a river.
Point B: 900 m as the crow flies, direct road.
```

The application wants the fastest delivery. At which step do you use `$geoNear`, and what additional data sources or calculations are needed to make the final decision?

## 18. Official Reference Documentation

Geospatial feature details vary by **MongoDB server version** and data format; always check documentation for your running version:

- [MongoDB Geospatial Queries](https://www.mongodb.com/docs/manual/geospatial-queries/) — overview of GeoJSON, indexes, and operators.
- [`$near` query operator](https://www.mongodb.com/docs/manual/reference/operator/query/near/) — syntax, index requirements, and units for GeoJSON/legacy.
- [`$nearSphere` query operator](https://www.mongodb.com/docs/manual/reference/operator/query/nearSphere/) — spherical distance and legacy syntax.
- [`$geoNear` aggregation stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/geoNear/) — `distanceField`, `distanceMultiplier`, `includeLocs`, `key`, and stage order.
- [`2dsphere` Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/) — storing GeoJSON and creating geographic indexes.
- [`2d` Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2d/) — legacy/planar data.
- [Query Locations Near a Point on a Sphere](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/query/proximity-to-geojson/) — GeoJSON proximity query examples.
- [`$geoWithin`](https://www.mongodb.com/docs/manual/reference/operator/query/geoWithin/) — region containment queries.
- [`$geoIntersects`](https://www.mongodb.com/docs/manual/reference/operator/query/geoIntersects/) — region intersection queries.
- [`$centerSphere`](https://www.mongodb.com/docs/manual/reference/operator/query/centerSphere/) — spherical circle with radius in radians.

Depending on version, MongoDB has changed certain limits—for example, requiring a GeoJSON `Point` as input to proximity queries starting in MongoDB 8.0 and making `distanceField` optional for non-time-series `$geoNear` starting in 8.1. Always verify version and FCV behavior before promoting sample code to production.

## 19. Conclusion

To find nearby locations in MongoDB, start with a **GeoJSON Point** using `[longitude, latitude]` coordinates and a matching **`2dsphere` geospatial index**. Use **`$near`** or **`$nearSphere`** when `find()` needs documents ordered nearest to farthest; with GeoJSON, both use spherical geometry and distance bounds in **meters**. When you need a computed distance field and further pipeline processing, use **`$geoNear` as the first pipeline stage**, combining `query`, `distanceField`, `maxDistance`, `key`, and subsequent stages.

Getting **units** right is mandatory: GeoJSON points store lon/lat in degrees while near-query radii are in meters; legacy coordinates follow separate semantics, often requiring radians for spherical queries. `distanceMultiplier` scales the **output** distance, not the unit of the `maxDistance` filter.

Finally, a sound geospatial query accounts for **input data quality, indexes, business filter scope, performance, GPS accuracy, and privacy**. MongoDB excels at selecting **geographically nearby** candidates, but **it does not compute travel time, road rules, or service eligibility on its own**. Picking the right operator is only the first step; reliable outcomes depend on designing the full application flow properly.
