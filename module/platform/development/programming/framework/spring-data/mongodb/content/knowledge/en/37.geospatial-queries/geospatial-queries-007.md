# `$geoNear` in Aggregation

When building a **"find stores near the customer's location"** feature, an application does not merely filter documents inside a geographic region—it also wants to **compute distances, sort nearest to farthest, filter by store category and active status, and cap the number of results**. MongoDB provides the **`$geoNear`** aggregation stage to handle these requirements using a geospatial index.

In **Spring Data MongoDB**, you can construct this stage via `Aggregation.geoNear(NearQuery, String)` and execute it with `MongoTemplate.aggregate(...)` or `ReactiveMongoTemplate.aggregate(...)`. What matters is understanding **GeoJSON, longitude/latitude order, `2dsphere` indexes, units of measure, and mandatory stage placement** before chaining `$limit`, `$project`, `$group`, or other aggregation stages.

This lesson belongs to the **Geospatial Queries** chapter of the `SPRING_DATA_MONGODB` module. The module practices connecting, mapping documents, and operating on MongoDB via templates or repositories, covering queries, aggregation, indexes, transactions, reactive access, testing, and data performance diagnostics. The specific topic is **`$geoNear` in aggregation**: from MongoDB Server syntax to expressing, running, and verifying it with Spring Data.

> **Rules to remember:** `$geoNear` returns documents in **ascending distance order**, requires a **geospatial index**, and must sit at the **start of the pipeline**. When `near` is a GeoJSON Point with a `2dsphere` index, `maxDistance`, `minDistance`, and `distanceField` use **meters** unless a `distanceMultiplier` is applied. To restrict by tenant/category, place predicates inside **`$geoNear.query`** instead of putting `$match` before `$geoNear`.

## 1. Learning Objectives

Upon completing this lesson, you will be able to:

1. Distinguish `$geoNear` from `$near`/`$nearSphere`, `$geoWithin`, and `$geoIntersects`.
2. Explain why `$geoNear` is the first stage in the pipeline on the target collection.
3. Normalize locations as GeoJSON `{ type: "Point", coordinates: [longitude, latitude] }`.
4. Validate valid bounds: longitude from −180 to 180 and latitude from −90 to 90.
5. Create and verify a `2dsphere` index before running queries.
6. Understand options `near`, `key`, `distanceField`, `includeLocs`, `query`, `minDistance`, `maxDistance`, `spherical`, and `distanceMultiplier`.
7. Explain the exact units **meters**, **kilometers**, and **radians** for GeoJSON vs legacy coordinates.
8. Build shell pipelines to find stores near a point, filter tenant/category/active, limit, and project DTOs.
9. Use Spring Data MongoDB's `GeoJsonPoint`, `NearQuery`, and `Aggregation.geoNear`.
10. Select a specific geospatial index via `GeoNearOperation.useIndex(...)`.
11. Understand mapping between Java fields and BSON fields when using `@Field` or typed aggregations.
12. Use `MongoTemplate.aggregate(...)` to return documents/DTOs with a distance field.
13. Use `ReactiveMongoTemplate.aggregate(...)` and understand lazy subscription.
14. Recognize the difference between `distanceField` and `distanceMultiplier`, along with unit conversions.
15. Understand nearest-to-farthest order, result limits, ties, sorting, and pagination.
16. Combine distance-based analytics using `$group`, `$bucket`, `$addFields`, and `$project`.
17. Handle collections with multiple location fields, multiple geospatial indexes, and documents with multiple locations.
18. Design safe queries for multi-tenant isolation, validated coordinates, and capped radii.
19. Distinguish spherical proximity from **actual road-network travel time/distance**.
20. Test on real MongoDB, inspect `explain`, observe performance, and diagnose common errors.

## 2. What Problem Does `$geoNear` Solve?

Suppose a `geo_stores` collection contains stores:

```javascript
{
  _id: "STORE-001",
  tenantId: "tenant-a",
  name: "Store Alpha",
  category: "COFFEE",
  active: true,
  location: {
    type: "Point",
    coordinates: [106.7005, 10.7754]
  }
}
```

The client sends search center `[106.7000, 10.7750]` and a 2,000-meter radius. A useful API must return:

| Result Attribute | Why It Is Needed |
| --- | --- |
| `name`, `category` | Display store information |
| `distanceMeters` | Approximate distance using spherical Earth geometry |
| Nearest-to-farthest order | Surface the most relevant choices first |
| `tenantId` + `active` | Prevent reading another tenant's data or inactive stores |
| Limit of 10–20 rows | Protect API and UI |
| Matched location used for calculation | Helpful when a document contains multiple locations |

MongoDB `$geoNear` performs the distance-based search using a geospatial index, appends `distanceMeters` to each result, and sorts in ascending order. Subsequent stages can select fields, cap results, or aggregate.

### 2.1. Do Not Confuse `$geoNear` with Driving Routes

Distances from `$geoNear` are **geometric distances** under geographic semantics—not actual driving/walking distances—and do not reflect traffic jams, bridges, one-way streets, or travel times. If a product needs ETA or turn-by-turn routes, integrate an appropriate routing service after narrowing candidates with `$geoNear`.

## 3. Comparing `$geoNear` with Other Geospatial Operators

| Mechanism | Scope | Distance Included in Output? | Nearest-Farthest Order? |
| --- | --- | --- | --- |
| `$geoNear` | **Aggregation stage** | **Yes**, adds computed field | **Yes**, by default |
| `$near` | Query predicate on location | Typically does not add a separate distance field | Yes, proximity-ordered query semantics |
| `$nearSphere` | Query predicate | Does not add a distance field like aggregation | Yes |
| `$geoWithin` | Selects shapes/points inside a region | Does not add distance | Not required |
| `$geoIntersects` | Selects intersecting geometries | Does not add distance | Not required |

For example, `$geoWithin` is sufficient if you only ask "is it inside the service zone?". However, when you need a **distance field to display, group, transform, or aggregate in a pipeline**, `$geoNear` is the right fit.

`$near` is normally a query predicate in `find`. Never place `$near` inside `$geoNear.query`: MongoDB forbids nested near predicates there.

### 3.1. `MongoTemplate.geoNear` and Modern Aggregation

MongoDB removed the legacy **`geoNear` command** in MongoDB 4.2. Spring Data MongoDB 2.2 and later implement geoNear operations on top of the **`$geoNear` aggregation stage** instead of the old command. Spring Data documentation recommends using `Aggregation.geoNear(NearQuery, String)` directly so you can chain additional stages in a pipeline. Avoid copying old MongoDB examples like `db.runCommand({ geoNear: ... })`.

## 4. Location Data: GeoJSON Point and Coordinate Order

A GeoJSON Point has the form:

```json
{
  "type": "Point",
  "coordinates": [106.7005, 10.7754]
}
```

The order is **always `[longitude, latitude]`** in standard geographic coordinate examples—that is, **longitude first, latitude second**.

| Component | Meaning | Valid Range |
| --- | --- | --- |
| `coordinates[0]` | Longitude | −180 to 180 |
| `coordinates[1]` | Latitude | −90 to 90 |

Do not swap them to `[latitude, longitude]` just because many mapping/UI libraries represent coordinates as `(lat, lng)` pairs. MongoDB GeoJSON expects `[lng, lat]`. Swapped numbers may still lie within valid bounds and return a location very far away without throwing an exception.

### 4.1. Why Use GeoJSON Instead of Legacy Arrays?

MongoDB also supports legacy coordinate pairs:

```javascript
locationLegacy: [106.7005, 10.7754]
```

However, they come with different unit and index rules. For new applications storing locations on Earth, prefer `GeoJSON Point` + `2dsphere`. In this lesson, **all new examples use GeoJSON** unless explicitly marked "legacy".

### 4.2. GeoJSON Point vs Polygon

A document can contain GeoJSON `Point`, `MultiPoint`, `LineString`, or `Polygon` depending on the model. `$geoNear` calculates distance to the nearest part of the geometry per server semantics; for regions/polygons, "distance to centroid" is not automatically what gets returned.

Starting in MongoDB 8.0, the **GeoJSON `near`** parameter is validated to have `type: "Point"`; do not pass a `Polygon` or `MultiPoint` as the search center. A `2dsphere` index still supports other compatible stored geometries per MongoDB rules.

## 5. Preparing an Illustrative Dataset

On a **test database** (never run these commands in production), create the `geo_stores` collection and a few synthetic points:

```javascript
use geo_training

db.geo_stores.insertMany([
  {
    _id: "STORE-001",
    tenantId: "tenant-a",
    name: "Store Alpha",
    category: "COFFEE",
    active: true,
    location: { type: "Point", coordinates: [106.7005, 10.7754] }
  },
  {
    _id: "STORE-002",
    tenantId: "tenant-a",
    name: "Store Beta",
    category: "COFFEE",
    active: true,
    location: { type: "Point", coordinates: [106.7100, 10.7780] }
  },
  {
    _id: "STORE-003",
    tenantId: "tenant-a",
    name: "Store Gamma",
    category: "BOOK",
    active: true,
    location: { type: "Point", coordinates: [106.7050, 10.7800] }
  },
  {
    _id: "STORE-004",
    tenantId: "tenant-a",
    name: "Store Delta",
    category: "COFFEE",
    active: false,
    location: { type: "Point", coordinates: [106.6990, 10.7740] }
  },
  {
    _id: "STORE-005",
    tenantId: "tenant-b",
    name: "Store Other Tenant",
    category: "COFFEE",
    active: true,
    location: { type: "Point", coordinates: [106.7001, 10.7751] }
  }
])
```

These are **hypothetical points for learning syntax**, not verified real-world businesses or names. The IDs use `STORE-...` strings to avoid 24-hex strings being converted to `ObjectId` in certain Spring Data mapping paths.

### 5.1. Selecting the Test Database/Collection Explicitly

`$geoNear` only works on collections with a proper geospatial index. If a collection is shared across applications, provision indexes via controlled migrations/management jobs rather than creating indexes on every HTTP request.

## 6. Creating the Right `2dsphere` Index Before Querying

MongoDB shell:

```javascript
db.geo_stores.createIndex(
  { location: "2dsphere" },
  { name: "location_2dsphere" }
)

db.geo_stores.getIndexes()
```

A `2dsphere` index is used for spherical Earth locations and GeoJSON. Without an index, `$geoNear` fails; MongoDB will not silently fall back to scanning the collection and computing distances in Java.

### 6.1. `2d` vs `2dsphere`

| Index | Primary Data Format | Geometry |
| --- | --- | --- |
| `2dsphere` | GeoJSON and certain legacy locations per rules | Spherical geography |
| `2d` | Legacy coordinate pairs | Planar coordinates / legacy use cases |

When `near` is a GeoJSON Point, you need a compatible **`2dsphere` geospatial index** on the target field. A `2d` index on a legacy field cannot replace the right index for a GeoJSON field.

### 6.2. Spring Data Annotations Are Only Index Descriptions

On an entity you can write:

```java
@GeoSpatialIndexed(type = GeoSpatialIndexType.GEO_2DSPHERE)
private GeoJsonPoint location;
```

However, Spring Data MongoDB **disables automatic index creation by default since version 3.0**. Do not assume adding `@GeoSpatialIndexed` puts the index into MongoDB. Use index migrations or intentional `IndexOperations` provisioning, and verify with `getIndexes()`.

## 7. Complete `$geoNear` Syntax

A MongoDB stage with its key options:

```javascript
{
  $geoNear: {
    near: {
      type: "Point",
      coordinates: [106.7000, 10.7750]
    },
    key: "location",
    distanceField: "distanceMeters",
    maxDistance: 2000,
    minDistance: 0,
    query: {
      tenantId: "tenant-a",
      active: true
    },
    spherical: true,
    includeLocs: "matchedLocation"
  }
}
```

| Option | Purpose | Notes |
| --- | --- | --- |
| `near` | Search center | GeoJSON Point or legacy coordinate pair |
| `key` | Indexed geospatial field path used for calculations | Should be explicit; required if multiple indexes cause ambiguity; also required for time series |
| `distanceField` | Output field storing computed distance | Always declare it; required on many server versions and time series |
| `maxDistance` | Maximum distance | **Meters** for GeoJSON Point |
| `minDistance` | Minimum distance | **Meters** for GeoJSON Point |
| `query` | Filter for candidate documents | Must not contain `$near` |
| `spherical` | Compute using spherical geometry | `true` for geographic examples |
| `includeLocs` | Records the location used to calculate distance | Useful when one document has multiple locations |
| `distanceMultiplier` | Factor multiplying **distance output** | Does not change filter bound units |

**Version note:** starting in MongoDB 8.1, `distanceField` may no longer be mandatory on regular collections, but it remains mandatory on **time series collections**. For compatibility and clean mapping, this lesson always declares `distanceField`.

### 7.1. `key` Is Not the Index Name

In `$geoNear`, `key: "location"` is the **indexed field path**, not the physical index name like `location_2dsphere`. In Spring Data, `GeoNearOperation.useIndex("location")` also accepts the **field path**.

### 7.2. Can You Use `$geoNear` Without `distanceField`?

Only on server versions and collection types that support omitting it. Do not rely on omitting that field if your application must run on MongoDB 7.x/8.0 or time series collections. Always specifying an explicit field keeps tests and DTOs stable.

## 8. The First-Stage Rule in Pipelines

MongoDB requires `$geoNear` **to be the first stage of the pipeline it appears in**:

```javascript
// RIGHT:
db.geo_stores.aggregate([
  { $geoNear: { /* near, key, distanceField... */ } },
  { $limit: 10 },
  { $project: { name: 1, distanceMeters: 1 } }
])
```

Invalid:

```javascript
// WRONG: $match appears before $geoNear.
db.geo_stores.aggregate([
  { $match: { tenantId: "tenant-a" } },
  { $geoNear: { /* ... */ } }
])
```

Even if `$match` filters very selectively, you **cannot** place it before `$geoNear`. Use `$geoNear.query` to push tenant/active/category predicates directly into the first stage.

### 8.1. `$geoNear` Inside a `$lookup` Subpipeline

`$geoNear` can appear **at the start of a permitted subpipeline**, such as inside `$lookup.pipeline` under server-supported conditions. The "first stage" rule applies **to that specific pipeline/subpipeline**, not only the top-level pipeline of the entire command. Verify `$lookup`/`let` constraints and MongoDB version rules when implementing correlated queries.

### 8.2. `$search` Also Has a First-Stage Requirement

If you need to combine full-text search (especially Atlas Search) with geospatial distance, you cannot simply put two stages that both require the first position into the same pipeline. Pick the primary search driver, combine predicates inside the appropriate stage, or design a two-phase flow. Never stack `$search` followed by `$geoNear` expecting the server to accept it.

## 9. Practical Query in MongoDB Shell

Find up to 10 active `COFFEE` stores within a 2 km radius belonging to `tenant-a`:

```javascript
db.geo_stores.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.7750]
      },
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 2000,
      spherical: true,
      query: {
        tenantId: "tenant-a",
        category: "COFFEE",
        active: true
      }
    }
  },
  { $limit: 10 },
  {
    $project: {
      _id: 1,
      name: 1,
      category: 1,
      distanceMeters: 1,
      location: 1
    }
  }
])
```

Results are documents matching `query`, enriched with MongoDB-computed `distanceMeters` and sorted nearest to farthest. Exact numbers depend on coordinates and geometry, so never state a hardcoded "measured" number without running it on real MongoDB.

### 9.1. Why Filter Tenant Inside `$geoNear.query`?

Putting `tenantId` inside `query` ensures **only documents belonging to the authorized tenant are considered** right from the geospatial search. If you filter tenant after `$limit`, the top 10 closest results might come from other tenants, leaving too few valid stores. Returning other tenants' data to the application before filtering also increases information-disclosure risk.

### 9.2. Why Place `$limit` Immediately After `$geoNear`?

`$geoNear` already outputs in ascending distance order. When the API only needs the 10 nearest candidates, placing `$limit:10` right after avoids sending or transforming excessive records. Never place `$limit` **before** the geospatial stage. If extra filtering happens after `$geoNear`, recognize that `$limit` placement can alter the result set.

## 10. `minDistance` and `maxDistance`: Creating an Annulus Region

To find stores between 500 and 2,000 meters from the center:

```javascript
db.geo_stores.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7000, 10.7750]
      },
      key: "location",
      distanceField: "distanceMeters",
      minDistance: 500,
      maxDistance: 2000,
      spherical: true,
      query: { tenantId: "tenant-a", active: true }
    }
  },
  { $limit: 20 }
])
```

This is a **geometric distance band** (a ring around the center), not a road-network service zone. Never pass negative bounds, `NaN`, `Infinity`, or `minDistance > maxDistance`. Validate inputs before building the pipeline so the API returns clear errors.

### 10.1. `maxDistance` Has No Automatic Cap When Omitted

Without `maxDistance` and without `$limit`, geospatial searches can return huge numbers of documents, consuming CPU/index work, network bandwidth, mapping overhead, and HTTP request latency. Enforce radius and result-count caps per product requirements; never let callers request an unbounded radius.

## 11. `distanceField`, `includeLocs`, and `distanceMultiplier`

### 11.1. `distanceField`

`distanceField` is the field name added to each result. Dotted field paths are allowed:

```javascript
{
  $geoNear: {
    near: { type: "Point", coordinates: [106.7000, 10.7750] },
    key: "location",
    distanceField: "geo.distanceMeters",
    spherical: true
  }
}
```

Results will take the shape `geo: { distanceMeters: ... }` if it does not conflict with existing structure. Do not choose a name colliding with an important business field, since `$geoNear` creates or overwrites output at that path.

### 11.2. `includeLocs`

Suppose a document contains multiple locations (e.g., multiple pickup bays). `includeLocs: "geo.nearestPoint"` outputs **which location MongoDB used to compute the distance**, instead of the application guessing from the array. This field is purely additional output; it does not affect index selection.

### 11.3. `distanceMultiplier`

With a GeoJSON Point, base distance output is in **meters**. To display **kilometers**, multiply by `0.001`:

```javascript
db.geo_stores.aggregate([
  {
    $geoNear: {
      near: { type: "Point", coordinates: [106.7000, 10.7750] },
      key: "location",
      distanceField: "distanceKm",
      maxDistance: 2000,
      distanceMultiplier: 0.001,
      spherical: true
    }
  },
  { $limit: 10 }
])
```

**Crucially:** `maxDistance:2000` is still **2,000 meters**; `distanceMultiplier:0.001` only converts the **output field** to km, not the threshold to 2,000 km. If you prefer avoiding multipliers, keep `distanceMeters` and convert for display in a `$set` stage or Java code under an explicit policy.

## 12. GeoJSON vs Legacy: Differences in Units

Spring Data `NearQuery` highlights the difference between `new GeoJsonPoint(lng,lat)` and `new Point(lng,lat)`. Even with identical numeric coordinates, the BSON syntax and native distance units differ.

| `near` Type | Geometry / Index | Default `maxDistance` and `distanceField` |
| --- | --- | --- |
| GeoJSON `Point` | `2dsphere` | **Meters** |
| Legacy pair `[lng,lat]` with spherical | `2dsphere` | **Radians** when no metric/multiplier is applied |
| Legacy pair with `2d` | Planar | 2D coordinate system units |

With legacy spherical queries, approximately `distanceMeters = distanceRadians × 6_371_000`, yet **never convert again if you already used Spring Data's `Metrics.KILOMETERS`/`Distance`**. The factor `distanceMultiplier:6378.137` seen in legacy examples converts **radians to km**, and is wrong for **GeoJSON meters to km** (which uses `0.001`).

**Consistent convention in this lesson:** GeoJSON Point for both storage and `near`; all base radii/inputs/outputs in **meters**; no hidden `distanceMultiplier`. If the API wants km, convert explicitly in projection or DTO and test thresholds.

## 13. Java Entity Mapping with `GeoJsonPoint`

Spring Data MongoDB provides `org.springframework.data.mongodb.core.geo.GeoJsonPoint`. An example record:

```java
package dev.learning.geo;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("geo_stores")
public record Store(
    @Id String id,
    String tenantId,
    String name,
    String category,
    boolean active,
    GeoJsonPoint location
) {
}
```

Creating the Java point:

```java
GeoJsonPoint p = new GeoJsonPoint(106.7005, 10.7754);
Store shop = new Store(
    "STORE-010", "tenant-a",
    "Store Sample", "COFFEE", true, p
);

mongoTemplate.insert(shop);
```

Constructor `GeoJsonPoint(x, y)` takes **longitude before latitude**, matching GeoJSON `[lng,lat]`. The mapped BSON of `location` must contain `type: "Point"` and `coordinates` in that exact order.

### 13.1. Java Property Name Differing from BSON Name

If the entity uses `@Field("tenant_id") String tenantId`, BSON will store `tenant_id`. Raw MongoDB shell needs `tenant_id`; typed Spring Data aggregation/mapping usually uses the mapping context to resolve Java property names. Avoid mixing Java and BSON names when writing custom raw `Document` `AggregationOperation`s; verify actual commands via integration tests and command monitoring.

## 14. Provisioning Geospatial Indexes via `MongoTemplate`

Creating a `2dsphere` index intentionally using `IndexOperations`:

```java
package dev.learning.geo;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;
import org.springframework.data.mongodb.core.index.GeospatialIndex;

public final class StoreIndexProvisioner {

    private StoreIndexProvisioner() {}

    public static String ensureIndex(MongoTemplate mongoTemplate) {
        return mongoTemplate.indexOps(Store.class).ensureIndex(
            new GeospatialIndex("location")
                .typed(GeoSpatialIndexType.GEO_2DSPHERE)
                .named("location_2dsphere")
        );
    }
}
```

Invoke during **migration/startup or test setup**, never per request. Although you can annotate `@GeoSpatialIndexed(type=GEO_2DSPHERE)` on the property, **automatic index creation is disabled by default since Spring Data MongoDB 3.0**, so annotations alone do not guarantee the index exists.

Verify with `db.geo_stores.getIndexes()`. In real environments, execute index migrations/rollouts with proper administrative privileges; if existing geo data is invalid, the index build can fail.

## 15. `NearQuery`: `near`, `query`, `maxDistance`

`NearQuery` lives in package `org.springframework.data.mongodb.core.query`. Building a 2,000-meter radius query:

```java
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.NearQuery;
import org.springframework.data.mongodb.core.query.Query;

GeoJsonPoint center = new GeoJsonPoint(106.7000, 10.7750);

Query filter = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("category").is("COFFEE")
        .and("active").is(true)
);

NearQuery near = NearQuery.near(center)
    .spherical(true)
    .maxDistance(2000.0)
    .query(filter);
```

- `near(center)` passes a **GeoJSON Point**, so `2000` is interpreted in **meters** in this metric-free example.
- `spherical(true)` states spherical geometry intent explicitly.
- `query(filter)` sets `$geoNear`'s inner `query`: filtering tenant, active, and category **before limiting results**.
- Never put `$near` inside `NearQuery.query(...)`; MongoDB rejects nested near predicates.

### 15.1. Using `Metrics` Intentionally

`NearQuery` offers `maxDistance(Distance)`, `minDistance(Distance)`, `inKilometers()`, `inMiles()`, and other `Metric`-related APIs. Some options both convert the radius and configure an output multiplier. To avoid double conversion or accidental radians, stick to **one convention** in your API/tests; this example consistently uses meters with `GeoJsonPoint` and avoids calling `inKilometers()`.

### 15.2. Read Preference Does Not Alter Geometry

`NearQuery` supports `withReadPreference`/`withReadConcern` in corresponding Spring Data versions. These control consistency and MongoDB node selection; they **do not** alter distance calculations or replace geospatial indexes.

## 16. `Aggregation.geoNear(NearQuery, String)`

Spring Data recommends the static factory `Aggregation.geoNear(...)` over constructing `GeoNearOperation` directly. Example:

```java
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.GeoNearOperation;

GeoNearOperation operation = Aggregation
    .geoNear(near, "distanceMeters")
    .useIndex("location");
```

`"distanceMeters"` is the output field. `useIndex("location")` corresponds to `key: "location"` in MongoDB and takes the **field path**, not the physical index name `location_2dsphere`.

### 16.1. `TypedAggregation` with Limit and Projection

```java
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;

TypedAggregation<Store> aggregation =
    Aggregation.newAggregation(
        Store.class,
        Aggregation.geoNear(near, "distanceMeters")
            .useIndex("location"),
        Aggregation.limit(10),
        Aggregation.project(
            "name", "category", "location", "distanceMeters")
    );
```

All other stages must come **after** `geoNear` in this aggregation pipeline. Never place `Aggregation.match(...)` before it:

```java
// INVALID in MongoDB:
Aggregation.newAggregation(
    Aggregation.match(Criteria.where("tenantId").is("tenant-a")),
    Aggregation.geoNear(near, "distanceMeters")
);
```

Filtering tenant inside `NearQuery.query(filter)` from the start is the right approach.

### 16.2. Typed Mapping Still Needs Verification

`TypedAggregation<Store>` helps Spring Data map domain fields. If you use `@Field("tenant_id")` or nested `location.geo`, inspect the BSON stage rendered in your actual Spring Data version. Custom raw `Document` stages may require raw BSON field names rather than relying on automatic mapping.

## 17. `MongoTemplate.aggregate` and Result DTOs

Execute the pipeline and inspect fields:

```java
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;

AggregationResults<Document> results =
    mongoTemplate.aggregate(
        aggregation, "geo_stores", Document.class);

List<Document> rows = results.getMappedResults();

for (Document row : rows) {
    Number distance = row.get("distanceMeters", Number.class);
    System.out.println(row.getString("name")
        + " -> " + distance + " m");
}
```

`mongoTemplate` is an injected Spring Data bean; `aggregation` is the typed pipeline from section 16. Read distance as `Number` because the concrete numeric type can vary across custom pipelines.

Public APIs should return a DTO:

```java
package dev.learning.geo;

public record NearbyStoreDto(
    String id, String name, String category, double distanceMeters
) {
}
```

Map results:

```java
List<NearbyStoreDto> payload = rows.stream()
    .map(doc -> new NearbyStoreDto(
        doc.getString("_id"),
        doc.getString("name"),
        doc.getString("category"),
        doc.get("distanceMeters", Number.class)
            .doubleValue()
    ))
    .toList();
```

In this example, `_id` is a **String** like `STORE-001`. If the collection uses `ObjectId`, map it properly instead of casting with `getString("_id")`. `Aggregation.project(...)` above preserves `_id` by default; if you explicitly exclude `_id`, update DTO mapping accordingly.

### 17.1. Never Return Internal Documents to Clients

A `$geoNear` result can still carry the entire original document if `$project` is omitted. Always restrict returned fields and prevent leaking `tenantId`, internal data, or exact unauthorized coordinates.

## 18. Complete Service: Validating Coordinates and Bounding Resources

Example service accepting only **valid coordinates**, a maximum radius of 20 km, and a maximum limit of 20; `tenantId` comes from the authenticated security boundary.

```java
package dev.learning.geo;

import java.util.List;
import org.bson.Document;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.NearQuery;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class NearbyStoreService {

    private final MongoTemplate template;

    public NearbyStoreService(MongoTemplate template) {
        this.template = template;
    }

    public List<NearbyStoreDto> search(
            String authorizedTenantId,
            double lon,
            double lat,
            double radiusMeters,
            String category,
            int limit) {

        if (!Double.isFinite(lon) || lon < -180 || lon > 180
                || !Double.isFinite(lat) || lat < -90 || lat > 90) {
            throw new IllegalArgumentException("Invalid coordinates");
        }
        if (!Double.isFinite(radiusMeters)
                || radiusMeters <= 0 || radiusMeters > 20_000) {
            throw new IllegalArgumentException(
                "Radius must be in (0, 20000] meters");
        }
        if (limit < 1 || limit > 20) {
            throw new IllegalArgumentException("Limit must be in [1, 20]");
        }
        if (authorizedTenantId == null
                || authorizedTenantId.isBlank()) {
            throw new IllegalArgumentException("Missing authenticated tenant");
        }

        Query filter = Query.query(
            Criteria.where("tenantId").is(authorizedTenantId)
                .and("category").is(category)
                .and("active").is(true));

        NearQuery near = NearQuery
            .near(new GeoJsonPoint(lon, lat))
            .spherical(true)
            .maxDistance(radiusMeters)
            .query(filter);

        TypedAggregation<Store> pipeline =
            Aggregation.newAggregation(
                Store.class,
                Aggregation.geoNear(near, "distanceMeters")
                    .useIndex("location"),
                Aggregation.limit(limit),
                Aggregation.project(
                    "name", "category", "distanceMeters")
            );

        return template
            .aggregate(pipeline, "geo_stores", Document.class)
            .getMappedResults().stream()
            .map(doc -> new NearbyStoreDto(
                doc.getString("_id"),
                doc.getString("name"),
                doc.getString("category"),
                doc.get("distanceMeters", Number.class)
                    .doubleValue()))
            .toList();
    }
}
```

### 18.1. `category` Requires Dedicated Validation

This example focuses on coordinates and radius. In a production API, `category` must be validated against an enum/business whitelist; never let clients supply raw BSON queries, field paths, `$where`, or aggregation stages. Obtain tenant ID from the authenticated principal—**never** trust a client-selected tenant.

### 18.2. Query Fields and Java Mapping

If the Java property is `tenantId` while the BSON field is `tenant_id`, use typed mapping or the exact BSON name in custom raw stages. When unsure, inspect the BSON command via tests/driver monitoring rather than assuming from Java getter names.

## 19. `ReactiveMongoTemplate`: `Flux` Does Not Remove Index Requirements

Spring Data reactive uses the same aggregation semantics and returns `Flux<Document>`:

```java
import org.bson.Document;
import reactor.core.publisher.Flux;

Flux<NearbyStoreDto> nearby =
    reactiveMongoTemplate
        .aggregate(aggregation, "geo_stores", Document.class)
        .map(doc -> new NearbyStoreDto(
            doc.getString("_id"),
            doc.getString("name"),
            doc.getString("category"),
            doc.get("distanceMeters", Number.class)
                .doubleValue()));
```

In WebFlux, return the Publisher for the framework to subscribe; never call `block()` or hide `subscribe()` inside a service. MongoDB reactive Publishers are typically **cold/lazy**: subscribing twice runs the geospatial query twice, adding load and potentially observing changed data.

`Flux` does not automatically reduce MongoDB's work: you still need a `2dsphere` index, maximum radius, `$limit`, and query plan tuning.

## 20. Multiple Geospatial Indexes: Specify `key` Explicitly

If a collection has indexes on both `location` and `deliveryHub`:

```javascript
db.geo_stores.createIndex({ location: "2dsphere" })
db.geo_stores.createIndex({ deliveryHub: "2dsphere" })
```

`$geoNear` can fail with an **ambiguous geospatial index** error unless you specify which field to use. MongoDB syntax:

```javascript
{
  $geoNear: {
    near: { type: "Point", coordinates: [106.7000, 10.7750] },
    key: "location",
    distanceField: "distanceMeters",
    spherical: true
  }
}
```

Spring Data:

```java
Aggregation.geoNear(near, "distanceMeters")
    .useIndex("location");
```

`key` is the **indexed field path**, not the index name. Declaring it explicitly prevents ambiguity when the data team adds new indexes later.

### 20.1. `includeLocs` with Multiple Locations

If a document holds **multiple locations**, `includeLocs` outputs the exact location MongoDB used to compute distance, allowing the API to explain which branch matched instead of guessing from an array. When each document holds only one `location`, `includeLocs` is usually unnecessary.

## 21. Compound `2dsphere` Indexes and Multi-Tenancy

For queries frequently filtering `tenantId`/`active`, evaluate a compound index:

```javascript
db.geo_stores.createIndex(
  { tenantId: 1, active: 1, location: "2dsphere" },
  { name: "tenant_active_location_geo" }
)
```

MongoDB supports compound `2dsphere` indexes, though no combination is guaranteed faster than a single-field index. Performance depends on cardinality, data distribution, geospatial selectivity, key order, sparse geo behavior, and the query planner. **Measure with `explain`**, rather than adding indexes by guesswork.

Records missing `location` or containing `null` will not appear in `$geoNear` due to `2dsphere`'s sparse behavior. If the product needs an "unknown location" workflow, handle it as a separate data path.

### 21.1. Create Only Necessary Indexes

Every index adds storage and write-update cost, especially when stores update coordinates frequently. Never create indexes for every combination of category/active/tenant without analyzing workloads. Use migrations, `getIndexes()`, and `executionStats`.

## 22. Sorting and Pagination: Top-N Is Simpler Than Deep Skip

`$geoNear` returns results sorted by ascending distance. Fetching the 20 closest stores:

```javascript
[
  { $geoNear: { /* near, key, query, distanceField... */ } },
  { $limit: 20 }
]
```

For documents at identical distances, internal relative order should not be treated as strictly deterministic. When an API requires a tie-breaker, add:

```javascript
[
  { $geoNear: { /* ... */ } },
  { $sort: { distanceMeters: 1, _id: 1 } },
  { $limit: 20 }
]
```

However, `$sort` after `$geoNear` can incur extra cost; check with `explain`. If stores/locations mutate between requests, `$skip + $limit` can duplicate or skip items. Keyset pagination on `distanceMeters` also requires handling floating-point values, `_id` tie-breakers, and consistency. For typical map views, prefer an explicit radius + limit over deep pagination.

**Do not rely on the legacy 100-document default limit** of the old `geoNear` command: modern MongoDB no longer caps `$geoNear` at 100 rows automatically. Always specify `$limit` or `NearQuery.limit` intentionally.

## 23. Combining `$geoNear` with `$set`, `$project`, and `$group`

`$geoNear` provides a distance field, so subsequent stages can use that distance to build API outputs or run analytics.

### 23.1. Displaying km from Meter Distances

```javascript
db.geo_stores.aggregate([
  {
    $geoNear: {
      near: { type: "Point", coordinates: [106.7000, 10.7750] },
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 2000,
      spherical: true,
      query: { tenantId: "tenant-a", active: true }
    }
  },
  { $limit: 20 },
  {
    $set: {
      distanceKm: {
        $divide: ["$distanceMeters", 1000]
      }
    }
  },
  {
    $project: {
      name: 1,
      distanceMeters: 1,
      distanceKm: 1
    }
  }
])
```

This keeps both `distanceMeters` and `distanceKm` so clients can display km while business logic stays on meter thresholds. If you already configured `distanceMultiplier:0.001`, never divide by `1000` again.

### 23.2. Aggregating Statistics by Category

```javascript
db.geo_stores.aggregate([
  {
    $geoNear: {
      near: { type: "Point", coordinates: [106.7000, 10.7750] },
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 2000,
      spherical: true,
      query: { tenantId: "tenant-a", active: true }
    }
  },
  {
    $group: {
      _id: "$category",
      storeCount: { $sum: 1 },
      averageDistanceMeters: { $avg: "$distanceMeters" },
      nearestDistanceMeters: { $min: "$distanceMeters" }
    }
  },
  { $sort: { storeCount: -1, _id: 1 } }
])
```

**Output order after `$group` is no longer ascending by distance.** `$group` collapses multiple documents per group, and the trailing `$sort` orders by count/category. When an API expects a nearest-to-farthest store list, never accidentally swap `$group` in place of `$limit`/`$project`.

### 23.3. Grouping into Distance Bands

```javascript
db.geo_stores.aggregate([
  {
    $geoNear: {
      near: { type: "Point", coordinates: [106.7000, 10.7750] },
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 3000,
      spherical: true,
      query: { tenantId: "tenant-a", active: true }
    }
  },
  {
    $bucket: {
      groupBy: "$distanceMeters",
      boundaries: [0, 500, 1000, 2000, 3000],
      default: "outside",
      output: {
        count: { $sum: 1 }
      }
    }
  }
])
```

`$bucket` returns counts per distance band. Do not mistake this histogram for counts within driving distance; MongoDB computes geometry using geospatial semantics.

## 24. Analytics and List Together in `$facet`

When you want both **top nearest** and **category counts** in one aggregation, place `$facet` **after** `$geoNear`:

```javascript
db.geo_stores.aggregate([
  {
    $geoNear: {
      near: { type: "Point", coordinates: [106.7000, 10.7750] },
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 2000,
      spherical: true,
      query: { tenantId: "tenant-a", active: true }
    }
  },
  {
    $facet: {
      closest: [
        { $limit: 10 },
        { $project: { name: 1, category: 1, distanceMeters: 1 } }
      ],
      byCategory: [
        { $group: { _id: "$category", count: { $sum: 1 } } }
      ]
    }
  }
])
```

`$facet` cannot appear **before `$geoNear`** here; the `closest` branch inherits distance-ordered results from the first stage.

### 24.1. Why `$facet` Is Not Always Better Than Two Queries

`$facet` has memory limits and may process many documents across branches. If the summary needs to aggregate 100,000 stores across a huge radius while the UI only needs top 10, running two separate queries or caching summaries can be faster. Measure `explain`, memory, output size, and network overhead before choosing.

### 24.2. Never Put `$limit` Before `$facet` When Counting Everything

Putting `$limit:10` between `$geoNear` and `$facet` restricts both `closest` and `byCategory` to at most 10 documents. Decide **which candidate set** should feed the statistics before optimizing the pipeline.

## 25. Using `$geoNear` with Time Series and Version-Specific Features

MongoDB supports `$geoNear` on **time series collections** in compatible server versions, with important restrictions:

- You must specify `key` for the time series geospatial field.
- You cannot use `$geoNear.query` on a time series collection.
- `distanceField` remains mandatory for time series even though MongoDB 8.1+ may allow omitting it on regular collections.
- Creating `2dsphere` indexes on time series and how fields are stored differ from regular collections; verify server version, schema, and actual indexes.

A time series collection storing sensor coordinates can hold many records per device. `$geoNear` still finds the closest **documents/measurements**, not automatically "the closest device by its latest location". If you need the latest position per device, account for time filtering/rollups/last-state collections and stage limits.

### 25.1. GeoJSON `near` Type Validation

Starting in MongoDB 8.0, `$geoNear` with GeoJSON input enforces a valid `type:"Point"`. Passing `"type":"Polygon"` or a malformed JSON string causes an input error rather than an empty result.

### 25.2. `$geoNear` and `let` Variables

Modern MongoDB can use `let`/bound variables to supply the near point in supported aggregation contexts (such as `$lookup` subpipelines). That is an advanced capability requiring server-version verification and careful stage ordering; the foundational examples in this lesson intentionally pass a direct GeoJSON Point for clarity and testability.

## 26. Query Plans, `explain`, and Performance Metrics

On test MongoDB, inspect `executionStats`:

```javascript
db.geo_stores.explain("executionStats").aggregate([
  {
    $geoNear: {
      near: { type: "Point", coordinates: [106.7000, 10.7750] },
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 2000,
      spherical: true,
      query: {
        tenantId: "tenant-a",
        active: true,
        category: "COFFEE"
      }
    }
  },
  { $limit: 20 }
])
```

Things to examine:

1. Which geospatial index is used (e.g., the name matching `location_2dsphere`).
2. Whether a geospatial stage or index scan is used, without falling back to an unexpected plan.
3. `totalKeysExamined`/`totalDocsExamined` versus results returned.
4. Actual execution time and stability across radius sizes.
5. Impact of `tenantId`, `active`, and `category` inside `query`.
6. Comparison between a standalone index and a compound `2dsphere` index for multi-tenant workloads.
7. Overhead added by `$sort`, `$group`, `$facet`, or `$lookup` after the first stage.
8. Payload size and Spring Data result-mapping time.

Stage names in `explain` can change across MongoDB versions and execution engines; do not lock tests to a single hardcoded stage string unless necessary. Use `getIndexes()` to verify provisioned indexes and query profilers/metrics for safe production observability.

### 26.1. An Index Does Not Solve Infinite Radii

Even when `$geoNear` uses an index, requesting a radius of thousands of km or omitting `maxDistance` can force examining vast numbers of locations. `$limit` caps output, not all server-side calculation cost. Cap inputs before running the aggregation.

### 26.2. Skewed Data Distributions

A dense downtown district may hold tens of thousands of records within 1 km, while sparse areas hold very few. Benchmarks must reflect **density, tenant counts, categories, and null-location ratios**, not just 5 seeded documents.

### 26.3. Diagnosing Empty Query Results

Check in order: are lat/lng swapped on the center? Is the radius in meters or radians? Is `tenantId` right? Are `category`/`active` right? Are locations indexed in the geospatial index? Are you querying the right collection/database? Do not immediately blame a system bug when a query returns 0 rows.

## 27. Integration Testing: Spring Data + Real MongoDB

A meaningful test must **create the real index**, insert GeoJSON points, invoke the service, and verify tenant filtering, distances, and ordering. Use an isolated test database (or Testcontainers)—never run against production data.

```java
package dev.learning.geo;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;

@SpringBootTest
class GeoNearIntegrationTest {

    @Autowired MongoTemplate template;
    @Autowired NearbyStoreService service;

    @BeforeEach
    void ensureIndex() {
        StoreIndexProvisioner.ensureIndex(template);
    }

    @Test
    void returnsOnlyAuthorizedActiveNearbyStores() {
        String suffix = UUID.randomUUID().toString();
        String tenant = "tenant-test-" + suffix;

        Store nearest = new Store(
            "NEAR-" + suffix, tenant, "Near Store",
            "COFFEE", true, new GeoJsonPoint(106.7000, 10.7750));

        Store farther = new Store(
            "FARTHER-" + suffix, tenant, "Farther Store",
            "COFFEE", true, new GeoJsonPoint(106.7060, 10.7750));

        Store inactive = new Store(
            "INACTIVE-" + suffix, tenant, "Inactive",
            "COFFEE", false, new GeoJsonPoint(106.7000, 10.7750));

        Store wrongCategory = new Store(
            "BOOK-" + suffix, tenant, "Book",
            "BOOK", true, new GeoJsonPoint(106.7000, 10.7750));

        Store anotherTenant = new Store(
            "OTHER-" + suffix, "other-" + suffix, "Other Tenant",
            "COFFEE", true, new GeoJsonPoint(106.7000, 10.7750));

        template.insertAll(List.of(
            nearest, farther, inactive, wrongCategory, anotherTenant));

        List<NearbyStoreDto> found = service.search(
            tenant, 106.7000, 10.7750, 2000.0, "COFFEE", 20);

        assertThat(found)
            .extracting(NearbyStoreDto::id)
            .containsExactly(nearest.id(), farther.id());

        assertThat(found.get(0).distanceMeters())
            .isBetween(0.0, 2.0);

        assertThat(found.get(1).distanceMeters())
            .isGreaterThan(found.get(0).distanceMeters())
            .isLessThanOrEqualTo(2000.0);
    }
}
```

### 27.1. Why Do IDs Use UUIDs?

Each run creates isolated tenant and document IDs so parallel/repeated runs do not collide with other tests' records. Indexes are collection-scoped resources, so the test suite must run on an isolated test database. Never call `dropCollection` or `deleteAll` on a shared or production namespace.

### 27.2. Why Avoid Overly Exact Distance Assertions?

`$geoNear` distances depend on spherical geometry, coordinate precision, and floating-point rounding. For a point matching the center, expect near 0; for farther points, verify ordering and reasonable bounds. Never hardcode excessive decimal places unnecessarily.

### 27.3. Testing Swapped Longitude/Latitude

A test should send `longitude=10.7750, latitude=106.7000` and verify the service **rejects** it because latitude exceeds `90`. However, swapped pairs that still lie within valid bounds **cannot be caught by range validation alone**; products may also validate expected operating regions or source coordinate conventions.

### 27.4. Testing Measurement Units

Use two points roughly 1 km apart, verify `distanceMeters` sits within a sensible range, and confirm `maxDistance(500)` excludes the farther point. This catches legacy `Point`/radian mix-ups or wrong multipliers.

### 27.5. Testing Multiple Indexes

In an isolated test database, also provision a `deliveryHub` `2dsphere` index and verify the pipeline with `useIndex("location")` still resolves the right field. Without `key`, MongoDB may throw an ambiguity error; avoid asserting fragile version-specific exception message strings.

## 28. Location Security and Geospatial APIs

Exact coordinates can be sensitive data. A "nearby stores" endpoint must enforce:

- `authorizedTenantId` obtained from the authenticated principal/authorization context.
- Never accept arbitrary MongoDB `query`, `$where`, field paths, or raw pipelines from clients.
- Validate finite longitude/latitude, valid ranges, and coordinate system.
- Enforce product-defined maximum radius and limit caps.
- Never return exact user locations or store data belonging to other tenants.
- Distinguish searching near a user's center from **persisting user locations**; do not store them unless required.
- Apply appropriate rate limits/quotas since wide-radius queries can be resource-heavy.
- Record safe metrics/traces without dumping raw GPS coordinates into application logs.
- If storing user coordinates, follow access-control and retention policies; never treat an unverified geospatial document as proof of personal physical presence.

### 28.1. One Bad Filter Can Leak Data

Never fetch the top 20 stores across all tenants and filter tenants in Java. Doing so can leak the existence/distances of unauthorized locations, or drop valid stores that were cut off by `$limit` beforehand. **The tenant filter must live inside `$geoNear.query`.**

### 28.2. `GeoNear` Does Not Replace Routing/ETA

If the API returns `distanceMeters=500`, that is geometric proximity, not a promise that the customer walks 500 m or arrives in 5 minutes. Name the field `distanceMeters` instead of `travelDistanceMeters` and document it clearly in the API schema.

## 29. Common Pitfalls

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| MongoDB reports missing geo index | Index not created or on wrong field | Provision `2dsphere` on exact `location` |
| Query fails on stage order | Placed `$match`/`$project` before `$geoNear` | Put `$geoNear` first in pipeline |
| Results appear very far away | Swapped longitude/latitude | Normalize to `[lng,lat]` |
| 2 km radius behaves wrongly | Confused m/radians or used legacy `Point` | Use `GeoJsonPoint` and meters |
| Distance output off by thousands | Used legacy multiplier with GeoJSON | Use `0.001` for meters → km |
| Radius becomes 2000 km | Thought multiplier changes `maxDistance` | `maxDistance` always uses `near`'s native unit |
| Nested `$near` query rejected | `$geoNear.query` disallows `$near` | Remove nested near predicate; use stage's `near` |
| Unsure which index is used | Multiple geospatial indexes | Set `key`/`useIndex` to exact field path |
| Returns other tenant's data | Filtered tenant after `$limit` | Use `NearQuery.query`/`$geoNear.query` |
| Documents missing location vanish | Geospatial indexes skip null/missing positions | Separate workflow for unknown locations |
| Added `@GeoSpatialIndexed` yet still errors | Auto-index creation disabled | Migration/`IndexOperations` and verify `getIndexes()` |
| DTO distance is null | Wrong `distanceField` or excluded in projection | Align output field names |
| Results not nearest-first after group | `$group` destroys document ordering | Design appropriate sort/output strategy |
| Page 2 repeats items | Mutating data, unstable skip | Cursor/tie-breaker/consistency policy |
| GeoJSON near Polygon fails | MongoDB 8.0+ requires `type: Point` | Pass a valid GeoJSON Point |
| Time series query invalid | Missing `key` or unsupported `query` option | Follow time series constraints |
| Tests pass yet production is slow | Tiny dataset, wide radius, suboptimal indexes | `explain`/workload benchmarks |
| `geoNear` treated as road distance | Geometry differs from road routing | Use a dedicated routing service |
| Reactive `Flux` emits excessive items | Missing radius/result caps | Bound pipeline and apply backpressure |
| Creating index per request | DDL overhead/permissions | Provision on startup/migration |
| Logging user GPS coordinates | Privacy leak | Redact/truncate/log safe metadata |

### 29.1. Diagnostic Checklist

1. Which collection, MongoDB Server version, and indexes currently exist?
2. Is input valid GeoJSON `type:Point` with `[lon,lat]`?
3. Is `$geoNear` the first stage?
4. Does `key` point to the exact geospatial-indexed field?
5. Are units for `maxDistance`/`distanceField`/`distanceMultiplier` right?
6. Are tenant/active/category filters inside `$geoNear.query`?
7. Are `$limit` and maximum radius enforced?
8. Do subsequent `$sort`/`$group`/`$facet` stages alter semantics?
9. Does typed Spring Data mapping rename any fields?
10. What do `explain` keys/docs examined and latency show?
11. For time series or GeoJSON types, are server-version constraints met?
12. Were tests run against real MongoDB with safe fixtures?

## 30. Exercises, Checklist, and Official References

### 30.1. Practice Exercises

**Exercise 1 — GeoJSON.** Write a `Point` with longitude=106.7000, latitude=10.7750; explain why swapping the order is wrong.

**Exercise 2 — Index.** Create a test collection and a `2dsphere` index on `location`; verify with `getIndexes()` before querying.

**Exercise 3 — Shell `GeoNear`.** Write `$geoNear` with a 2,000-meter radius, `distanceField:"distanceMeters"`, and a tenant filter.

**Exercise 4 — Stage order.** Given pipeline `$match → $geoNear → $limit`, explain the error and move `$match` into `$geoNear.query`.

**Exercise 5 — `MinDistance`.** Find points between 500 and 2,000 meters from the center.

**Exercise 6 — Unit conversion.** Keep `maxDistance:2000`, add `distanceMultiplier:0.001`; determine the output unit and why the search radius stays unchanged.

**Exercise 7 — `NearQuery`.** Use `NearQuery.near(new GeoJsonPoint(...)).maxDistance(2000)` with tenant/active filters.

**Exercise 8 — `Aggregation.geoNear`.** Build a typed aggregation, specify `useIndex("location")`, add limit 10, and project to a DTO.

**Exercise 9 — Multiple indexes.** Add a `deliveryHub` index and explain why `key` must be specified explicitly.

**Exercise 10 — Reactive.** Convert the pipeline to `ReactiveMongoTemplate.aggregate` returning `Flux<NearbyStoreDto>`, without calling `block()`.

**Exercise 11 — Group.** Aggregate store count and average distance by category within a 2 km radius.

**Exercise 12 — Facet.** Return two branches: top 10 and count by category. Why must `$limit` not be placed before `$facet`?

**Exercise 13 — Tenant.** Explain the logic and security flaw of filtering tenants after `$limit`.

**Exercise 14 — Pagination.** When two stores have equal distance and one moves, what can offset pagination cause?

**Exercise 15 — Test.** Using real test MongoDB, UUID tenants, near/far points, and active/inactive records, verify results and distances.

**Exercise 16 — Explain.** Compare `executionStats` between `location_2dsphere` and a compound tenant/location index on representative data.

**Exercise 17 — Time series.** Look up `key`, `distanceField`, and `query` constraints for `$geoNear` on time series collections and explain how they differ from regular collections.

### 30.2. Implementation Checklist

- [ ] Store GeoJSON Points in `[longitude, latitude]` order.
- [ ] Validate lon/lat ranges, `NaN`/`Infinity`, and `Point` schema type.
- [ ] Ensure a geospatial index exists on the right field, preferring `2dsphere` for GeoJSON.
- [ ] Remember `@GeoSpatialIndexed` alone does not guarantee the index is created.
- [ ] `$geoNear` is the first stage in the pipeline/subpipeline.
- [ ] Explicitly specify `near`, `key`, and `distanceField`.
- [ ] Set `spherical` matching intended semantics.
- [ ] Use **meters** for `maxDistance`/`minDistance` when `near` is GeoJSON.
- [ ] Never mix legacy `Point` and `GeoJsonPoint`.
- [ ] Never use radian multipliers for GeoJSON meters.
- [ ] Never put `$near` inside `$geoNear.query`.
- [ ] Put tenant, active, and category filters inside `$geoNear.query`.
- [ ] Enforce server-side `$limit` and API radius caps.
- [ ] Understand `$group`/`$sort`/`$facet` can alter ordering or result sets.
- [ ] DTOs expose only permitted fields and explicit distance units.
- [ ] Use `Aggregation.geoNear(NearQuery,String)` and `GeoNearOperation.useIndex` per Javadoc.
- [ ] Verify typed Spring Data property→BSON mapping.
- [ ] Reactive pipelines are subscribed cleanly at the framework boundary.
- [ ] Never treat geometric distance as road distance/ETA.
- [ ] Check time series / server-version constraints if applicable.
- [ ] Use `getIndexes()` and `explain("executionStats")` on realistic workloads.
- [ ] Maintain integration tests for near/far, tenant isolation, null locations, and unit conversions.
- [ ] Never log sensitive GPS coordinates or run fixtures on production.
- [ ] `WRITTEN` is only a technical drafting status, not yet Content QA'd or published.

### 30.3. Official References

1. [MongoDB Manual — `$geoNear` aggregation stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/geonear/): syntax, first-stage rule, indexes, `key`, distances, and time series.
2. [MongoDB Manual — `$near` query predicate](https://www.mongodb.com/docs/manual/reference/operator/query/near/): GeoJSON and legacy units.
3. [MongoDB Manual — `2dsphere` Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/): spherical geospatial indexing.
4. [MongoDB Manual — GeoJSON Objects](https://www.mongodb.com/docs/manual/reference/geojson/): points, geometry types, and coordinate order.
5. [MongoDB Manual — `$geoWithin`](https://www.mongodb.com/docs/manual/reference/operator/query/geoWithin/): region query options.
6. [MongoDB Manual — `$geoIntersects`](https://www.mongodb.com/docs/manual/reference/operator/query/geoIntersects/): geometric intersection queries.
7. [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/): query plans and performance.
8. [Spring Data MongoDB — Geo-near Queries](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): `NearQuery` and moving from the `geoNear` command to aggregation.
9. [Spring Data MongoDB — `NearQuery` Javadoc](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/NearQuery.html): `GeoJsonPoint`, legacy `Point`, metrics, filters.
10. [Spring Data MongoDB — `GeoNearOperation` Javadoc](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/aggregation/GeoNearOperation.html): `Aggregation.geoNear` and `useIndex`.
11. [Spring Data MongoDB — Index Management](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html): index management and auto-creation defaults.
12. [Spring Data MongoDB — `GeospatialIndex` Javadoc](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/index/GeospatialIndex.html): programmatic `2dsphere` indexes.
13. [Spring Data MongoDB — Aggregation Framework](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html): typed pipelines and projections.
14. [Spring Data MongoDB — Reactive Template](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html): reactive aggregation.
15. [MongoDB Manual — Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/): time series schema/index limits.
16. [MongoDB Manual — `$facet`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/): multiple output branches and resource limits.

**Conclusion:** `$geoNear` is an aggregation stage that uses a geospatial index to find documents by distance, add `distanceField`, and return results **nearest first, farthest last**. Place it **at the start of the pipeline**, put filters such as tenant/active inside `query`, specify `key` to select the location field, and always verify the `2dsphere` index. With a **GeoJSON Point**, use `[longitude, latitude]` and **meters** for native distances—never confuse them with legacy coordinate radians or apply the wrong `distanceMultiplier`. In Spring Data MongoDB, pair `NearQuery` with `Aggregation.geoNear(...)`, run via `MongoTemplate` or `ReactiveMongoTemplate`, test against real MongoDB, and inspect `explain`. Cap radii/results, protect location data, and remember geospatial distance is not road travel distance.
