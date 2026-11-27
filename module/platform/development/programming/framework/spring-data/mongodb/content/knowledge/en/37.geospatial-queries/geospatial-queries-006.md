# Derived Queries with `Point`, `Distance`, and Supported `GeoResults`

> **Chapter:** Geospatial Queries  
> **Module:** `SPRING_DATA_MONGODB`

A delivery application often needs to find pickup points near a user: "find stores at most 3 km from this location and display the distance to each store". With Spring Data MongoDB, you can declare a repository method such as `findByLocationNear(Point, Distance)` so Spring Data **derives the spatial query** from the method name instead of manually writing MongoDB JSON for every query. When you also need the **calculated distance** for each result, choose the `GeoResult<T>` or `GeoResults<T>` return type matching your imperative or reactive repository.

Easily confused concepts: `Point` only holds coordinates, `Distance` holds a **value and measurement unit/`Metric`**, while `GeoResult<T>` and `GeoResults<T>` are **query results carrying distance metadata**, not the GeoJSON field type stored in MongoDB. Swapping longitude/latitude order, using the wrong `2d`/`2dsphere` index, or misreading `$geoNear` units can cause searches to cover the wrong radius even when the code compiles and runs.

This lesson belongs to module `SPRING_DATA_MONGODB`: using Spring Data MongoDB to connect, map documents, and operate via `MongoTemplate` or repositories; practicing query design, aggregation, indexes, transactions, reactive access, testing, and performance diagnostics. The direct topic is **derived queries with `Point`, `Distance`, and geospatial result types according to framework support**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Identify when repository methods `...Near(...)` and `...Within(...)` generate geospatial queries.
2. Distinguish `org.springframework.data.geo.Point` from `org.springframework.data.mongodb.core.geo.GeoJsonPoint` when constructing data/coordinates.
3. Use `Distance` with `Metrics.KILOMETERS` and `Metrics.MILES`, and understand how metrics affect spherical queries.
4. Declare `List<T>` and `GeoResults<T>` for imperative repositories, and `Flux<T>` and `Flux<GeoResult<T>>` for reactive repositories, **without mistakenly using reactive `GeoResults<T>`**.
5. Understand `GeoResult.getContent()`, `GeoResult.getDistance()`, and `GeoResults.getAverageDistance()`, as well as the limitations of averages when paging or filtering.
6. Create and verify a `2dsphere` index on the right field for BSON GeoJSON or legacy coordinates.
7. Combine coordinates with tenant/status filters, cap results, control query cost, and prevent multi-tenant data leaks.
8. Distinguish derived `Near` from `Within`, `MongoTemplate.geoNear`, and `$geoNear` aggregation when requirements exceed derived-method capabilities.
9. Test result ordering, radius, metrics, and distance metadata against a real test MongoDB instance; recognize common bugs.

## 2. A Running Scenario

Suppose the `pickup_points` collection stores three pickup locations. Each document has `tenantId`, `active`, and a geographic location:

```javascript
// mongosh - illustrative data, not a production system.
db.pickup_points.insertMany([
  {
    _id: "PP-A",
    tenantId: "TENANT-A",
    name: "Warehouse A",
    active: true,
    location: {
      type: "Point",
      coordinates: [106.7009, 10.7769]
    }
  },
  {
    _id: "PP-B",
    tenantId: "TENANT-A",
    name: "Warehouse B",
    active: true,
    location: {
      type: "Point",
      coordinates: [106.7060, 10.7794]
    }
  },
  {
    _id: "PP-C",
    tenantId: "TENANT-B",
    name: "Other tenant warehouse",
    active: true,
    location: {
      type: "Point",
      coordinates: [106.7010, 10.7770]
    }
  }
])
```

Expected API behavior:

```text
GET /pickup-points/nearby?longitude=106.7009&latitude=10.7769&radiusKm=3
    |
    v
Verified tenant: TENANT-A
    |
    v
Find active pickup points near coordinate
    |
    +-- Warehouse A, distance ~0 km
    +-- Warehouse B, a few hundred meters away
    +-- DO NOT return PP-C belonging to TENANT-B
```

**Security requirement:** `tenantId` must come from the authenticated context or be authorized by the service—never trust a query parameter self-declared by the client. The spatial query is an **additional** predicate, never a replacement for tenant filters or authorization.

## 3. Three Distinct Data Roles: Coordinates, Distance, Results

| Type | Typical Package | Represents | Does Not Represent |
| --- | --- | --- | --- |
| `Point` | `org.springframework.data.geo.Point` | `x/y` pair passed as search center | Distance unit or returned entity |
| `GeoJsonPoint` | `org.springframework.data.mongodb.core.geo.GeoJsonPoint` | GeoJSON Point geometry stored/queried by geographic coordinates | A result carrying distance |
| `Distance` | `org.springframework.data.geo.Distance` | Distance with numeric value and `Metric` | A point or coordinate |
| `Metric` / `Metrics` | `org.springframework.data.geo` | Measurement system for converting values | Map geometry |
| `GeoResult<T>` | `org.springframework.data.geo.GeoResult` | One entity `T` and its distance to the center | A MongoDB document inherently storing a distance field |
| `GeoResults<T>` | `org.springframework.data.geo.GeoResults` | Collection of `GeoResult<T>` plus average distance | Reactive Flux/publisher streaming |
| `GeoPage<T>` | `org.springframework.data.geo.GeoPage` | Page of GeoResults with page/distance metadata if supported by API | Valid return type for reactive repositories |

### 3.1. Longitude First, Latitude Second

In the GeoJSON geographic coordinate system (WGS84 lon/lat coordinates), the order is:

```text
[longitude, latitude]
     x         y
```

Example point:

```java
import org.springframework.data.geo.Point;

Point center = new Point(106.7009, 10.7769);
// x = 106.7009: longitude
// y = 10.7769: latitude
```

Never write `new Point(latitude, longitude)` just because a frontend API sends `lat` first. Swapped coordinates can sometimes still fall within valid numeric ranges and silently return wrong results.

### 3.2. `GeoJsonPoint` for GeoJSON Data

```java
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;

GeoJsonPoint location =
    new GeoJsonPoint(106.7009, 10.7769);
```

When Spring Data maps a `GeoJsonPoint`, BSON is stored as:

```javascript
{
  location: {
    type: "Point",
    coordinates: [106.7009, 10.7769]
  }
}
```

This is a **GeoJSON Point**. Meanwhile, a plain `Point` may be represented as a **legacy coordinate pair** `[x, y]` across mapping/query paths. Different representations follow different rules for **native distance units**; choose one consistent contract instead of mixing them arbitrarily.

### 3.3. `Distance` Is a Value with a `Metric`

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;

Distance radius = new Distance(3.0, Metrics.KILOMETERS);
Distance otherRadius = new Distance(2.0, Metrics.MILES);
```

`Metrics.KILOMETERS` and `Metrics.MILES` state the **caller's intended unit**. Spring Data uses `Metric` to convert parameters according to query semantics. Some native MongoDB forms use **radians**, whereas GeoJSON and `2dsphere` typically use **meters**; never treat a bare `3.0` as "3 km" in all contexts.

When extracting the numeric value:

```java
double number = radius.getValue();
// radius.getMetric() describes the corresponding measurement system.
```

Do not multiply blindly by 1000 or 6378 in multiple places. Keep `Distance` unit-aware up to the query boundary, and test actual measurements against known coordinates.

## 4. A Geospatial Index Is a Prerequisite

MongoDB `$near`/`$nearSphere` requires an appropriate **geospatial index**. For GeoJSON Point documents like `location` above, the standard choice is:

```javascript
db.pickup_points.createIndex(
  { location: "2dsphere" },
  { name: "idx_pickup_location_2dsphere" }
)
```

To verify:

```javascript
db.pickup_points.getIndexes()
```

In the Java model:

```java
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexed;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;

@GeoSpatialIndexed(type = GeoSpatialIndexType.GEO_2DSPHERE)
private GeoJsonPoint location;
```

The annotation describes desired index metadata; **do not assume the index has already been created in MongoDB**. Spring Data's auto-index creation can be disabled by default depending on configuration and version; manage indexes via migrations or intentional index-provisioning APIs.

### 4.1. `2d` and `2dsphere` Are Not Interchangeable Names

| Property | `2d` | `2dsphere` |
| --- | --- | --- |
| Primary geometry | Planar/legacy coordinates | Geometry on a sphere |
| Suitable for GeoJSON | Not the standard choice | **Yes** |
| Global lon/lat proximity queries | Limited, operator dependent | **Typically chosen** |
| `$near` with legacy pair | Supported under planar rules | Supported in some cases, requires right format |
| `$nearSphere` and GeoJSON | Do not use `2d` to replace GeoJSON `2dsphere` | Suitable |

If a collection uses `GeoJsonPoint`, prefer `2dsphere` and write tests matching the exact operator/index. Do not store GeoJSON in a collection with only a `2d` index expecting identical query behavior.

### 4.2. Fields Must Be Indexed Under Their Exact BSON Name

If the model declares `@Field("pickupLocation")` yet you create an index on `location`, queries may fail to use the expected index. Cross-check:

- The Java property parsed by the repository, e.g., `location`.
- The BSON field name after `@Field`/converter mapping, e.g., `pickupLocation`.
- The field name in the actual index from `getIndexes()`.

A common pitfall is running `$geoWithin` on small datasets in tests without issue, only to hit "unable to find index" on `$near`, because `$near` strictly requires an appropriate geospatial index.

## 5. Java Model: `PickupPoint` and GeoJSON Mapping

File `PickupPoint.java`:

```java
package com.example.delivery.pickup;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexed;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "pickup_points")
public class PickupPoint {

    @Id
    private String id;
    private String tenantId;
    private String name;
    private boolean active;

    @GeoSpatialIndexed(type = GeoSpatialIndexType.GEO_2DSPHERE)
    private GeoJsonPoint location;

    protected PickupPoint() {
        // For Spring Data's materialization mechanism.
    }

    public PickupPoint(
            String id,
            String tenantId,
            String name,
            boolean active,
            GeoJsonPoint location) {
        this.id = id;
        this.tenantId = tenantId;
        this.name = name;
        this.active = active;
        this.location = location;
    }

    public String getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getName() {
        return name;
    }

    public boolean isActive() {
        return active;
    }

    public GeoJsonPoint getLocation() {
        return location;
    }
}
```

The model keeps `location` as a **GeoJSON Point** mapped to the same field name in MongoDB. Do not mix two different coordinate representations in the same collection without migration/data reconciliation. Documents missing `location` may be omitted from the geospatial index per `2dsphere` semantics, so query completeness depends on valid location data.

### 5.1. Do Not Make `GeoResult` an Entity Property

`GeoResult<PickupPoint>` is created **when running a distance-calculating query**. It does not mean you should add:

```java
private GeoResult<PickupPoint> location;
```

to the model. An entity should hold `GeoJsonPoint location` for its position; "how far from the search center" is **query result metadata** that changes with each search center and is not an intrinsic property of the store.

### 5.2. Entity GeoJSON and `Point` Parameter Are Separate Decisions

A repository can accept `Point` as the **query center** while the entity field is `GeoJsonPoint`. When the framework builds the query, the center representation (`Point`/`GeoJsonPoint`) and `Distance`/`Metric` influence how MongoDB interprets the radius. Distinguish:

1. **Field data type**: GeoJSON stored in the BSON document, indexed with `2dsphere`.
2. **Center parameter type**: `Point` used in derived query APIs; `GeoJsonPoint` used when explicitly specifying GeoJSON.
3. **Distance parameter type**: `Distance` specifying a value with a metric.
4. **Result type**: `List<T>` holds entities only; `GeoResults<T>` adds distance.

Do not pick a return type just because the entity stores GeoJSON. Those are two separate layers.

## 6. Derived `Near` Query Returning an Entity List

Spring Data MongoDB recognizes the `Near` keyword in method names:

```java
package com.example.delivery.pickup;

import java.util.List;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface PickupPointRepository
        extends MongoRepository<PickupPoint, String> {

    List<PickupPoint> findByLocationNear(
        Point center,
        Distance maxDistance);
}
```

Invocation:

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;

Point center = new Point(106.7009, 10.7769);
Distance radius = new Distance(3, Metrics.KILOMETERS);

List<PickupPoint> places =
    repository.findByLocationNear(center, radius);
```

Here `repository` is an injected `PickupPointRepository` bean. The property `Location` in the method name maps to the entity's `location` field and translates into the corresponding MongoDB geospatial query operator.

### 6.1. Meaning of the Two Parameters

- `center` is an x/y coordinate. For geographic data: x = longitude, y = latitude.
- `radius` is the maximum distance in the chosen `Metric`. For example, `3 KILOMETERS`.

Spring Data generates a query finding documents near the center within that radius, typically using `$near` or `$nearSphere` depending on mapping/index/metric. With `2dsphere` and spherical metrics, verify the generated operator in driver logs/real tests instead of guessing from the method name.

### 6.2. `List<PickupPoint>` Has No Distance

Suppose the results are:

```text
PickupPoint("PP-A", "Warehouse A", location=...)
PickupPoint("PP-B", "Warehouse B", location=...)
```

`List<PickupPoint>` only contains entities. There is no `getDistance()` on `PickupPoint` unless you define that property yourself. If the UI needs to show "Warehouse B is 0.6 km away", never assume list index can replace an actual distance measurement.

When you need per-item distances, use **`GeoResults`** or the **`MongoTemplate.geoNear`** API.

### 6.3. `Near` Implicitly Orders by Distance

MongoDB `$near` returns documents **ordered nearest to farthest**. However:

- Do not attach `Sort.by("name")` to the same query expecting distance order to survive.
- When distances are equal or nearly equal, relative order between documents is not guaranteed to be deterministic without an explicit rule.
- Results can shift if locations or documents update between requests.
- Never infer tenant validity from nearest ordering.

### 6.4. Combining Tenant and Active Filters

In multi-tenant applications, spatial constraints must combine with **business filters**. For example, another method:

```java
List<PickupPoint> findByTenantIdAndActiveTrueAndLocationNear(
    String permittedTenantId,
    Point center,
    Distance radius);
```

Add this signature to `PickupPointRepository` above if needed. The method expresses:

```text
tenantId == permittedTenantId
AND active == true
AND location NEAR(center, radius)
```

`permittedTenantId` must come from the authentication/authorization layer. Never invoke this method with an untrusted client-supplied tenant ID assuming the derived query enforces permissions itself.

**Limitation:** when queries combine multiple conditions (tenant, active, geo), inspect the actual emitted JSON, explain plan, and indexes; do not assume every property/keyword combination optimizes or orders identically across all versions.

## 7. `GeoResult<T>` and `GeoResults<T>`: Entity + Distance

A `GeoResult<T>` carries:

```text
GeoResult<PickupPoint>
    |
    +-- content  -> PickupPoint
    |
    +-- distance -> Distance
```

A `GeoResults<T>` wraps **multiple `GeoResult` entries**:

```text
GeoResults<PickupPoint>
    |
    +-- getContent()
    |     +-- GeoResult<PickupPoint> #1
    |     +-- GeoResult<PickupPoint> #2
    |
    +-- getAverageDistance()
          +-- Distance (average of the results)
```

With imperative Spring Data MongoDB, you can declare:

File `PickupPointGeoResultsRepository.java`:

```java
package com.example.delivery.pickup;

import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface PickupPointGeoResultsRepository
        extends MongoRepository<PickupPoint, String> {

    GeoResults<PickupPoint> findByLocationNear(
        Point center,
        Distance maxDistance);
}
```

This is a **separate repository** from `PickupPointRepository` in section 6, even though both target the `pickup_points` collection. We separate the interfaces because Java cannot have **two methods with the same name and parameter types** differing only by **return type**:

```java
// INVALID if in the same interface:
List<PickupPoint> findByLocationNear(Point p, Distance d);
GeoResults<PickupPoint> findByLocationNear(Point p, Distance d);
// Java reports duplicate signature; return type does not distinguish overloads.
```

In production, pick **the one return type you need** or use distinct verified method names/overloads rather than creating extra repositories just for demonstration.

### 7.1. Reading Each `GeoResult` and the Average Distance

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;

Point origin = new Point(106.7009, 10.7769);
Distance maxRadius =
    new Distance(3.0, Metrics.KILOMETERS);

GeoResults<PickupPoint> nearby =
    geoResultsRepository.findByLocationNear(
        origin, maxRadius);

for (GeoResult<PickupPoint> row : nearby.getContent()) {
    PickupPoint point = row.getContent();
    Distance distance = row.getDistance();

    System.out.printf(
        "%s, distance=%s, metric=%s%n",
        point.getName(),
        distance.getValue(),
        distance.getMetric());
}

Distance average = nearby.getAverageDistance();
System.out.println("Average = " + average);
```

`geoResultsRepository` is an injected `PickupPointGeoResultsRepository` bean. Always **check the metric** of the returned distance rather than printing the raw value with an arbitrary "meters" or "km" label.

### 7.2. Do Not Confuse Average Distance with a Collection-Wide Metric

`getAverageDistance()` reflects **the `GeoResult` items inside this `GeoResults` instance**:

- If the query has a 3 km radius, the average covers only **the results returned by the query**.
- If the query is limited or paged, the page's average **is not necessarily the average of all points within 3 km**.
- If few or no results match, handle empty sets per the API contract instead of assuming "nearest distance is 0".
- Do not use average distance to claim all stores meet delivery SLAs without checking real road routes.

`GeoResults` provides convenient metadata, not driving time, street-network distances, or real-world service coverage.

### 7.3. `GeoResults` Does Not Mean MongoDB Documents Have a `distance` Field

A repository returning `GeoResults<T>` may execute a geo-near query/aggregation to compute distances. That does not mean documents in `pickup_points` magically store:

```javascript
{ name: "Warehouse A", distance: 0.0 }
```

`distance` is calculated relative to **each query's center**, changing whenever the user moves. If you ever persist a distance, clearly specify **relative to which reference point**, rather than treating it as an intrinsic spatial field on the entity.

## 8. `GeoPage`, `Pageable`, and Limits of Geospatial Pagination

In supported **imperative** APIs, Spring Data Commons provides `GeoPage<T>`, a `Page<GeoResult<T>>` with `getAverageDistance()`, `getContent()`, and page metadata. Illustrative signature to verify against your project's Spring Data MongoDB version:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoPage;
import org.springframework.data.geo.Point;

GeoPage<PickupPoint> findByLocationNear(
    Point center,
    Distance radius,
    Pageable pageable);
```

Place this signature in an imperative repository on versions supporting this return type; it **is not a reactive method**. Because geo-near and pagination paths change across Spring Data/MongoDB versions, run integration tests before adopting it as a public API contract.

Example usage in a service (with an appropriate injected repository):

```java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.geo.GeoPage;

GeoPage<PickupPoint> page =
    geoPageRepository.findByLocationNear(
        center,
        radius,
        PageRequest.of(0, 20));

page.getContent().forEach(row -> {
    System.out.println(row.getContent().getName());
    System.out.println(row.getDistance());
});
System.out.println(page.getAverageDistance());
```

Here `geoPageRepository` is a separate interface declared with the `GeoPage<PickupPoint>` signature above (to avoid Java overload conflicts with the previous two demo repositories).

### 8.1. Do Not Confuse Total Counts and Cost

With `Page` return types, the framework often needs the total element count—which may incur an extra count query/cost. Geospatial queries have constraints around combining `$near`, counts, filters, and geo-near pipelines, so **do not assume** total page counts are always cheap or exact across every version.

If the UI only needs "the 20 nearest locations", consider:

- Querying with a reasonable radius.
- Capping results via supported `Pageable`/`Limit` APIs or `NearQuery`.
- Skipping total counts when UX does not require them.
- Avoiding re-sorting by name when **distance ranking** is needed.
- Testing load and query plans on real data.

### 8.2. Offset Pagination Over Mutating Result Sets

Suppose a user fetches page 1, and then a new store is added or an existing location updates; nearest-to-farthest order shifts. Fetching page 2 by offset can **miss or duplicate** results.

Do not treat geo-near offset paging as an immutable snapshot. If the product needs consistent multi-page lists, use a snapshot/cursor design, a location-update policy, or an ID list pinned to the search session; `PageRequest.of(page, size)` alone cannot guarantee this.

### 8.3. `GeoPage` Is Neither `GeoResults` Nor a `Flux` `Pageable`

| Type | Metadata | Semantics |
| --- | --- | --- |
| `GeoResults<T>` | List with distances + average | Complete materialized result set |
| `GeoPage<T>` | `Page<GeoResult<T>>` + average, page/total if supported | Single materialized page |
| `Flux<GeoResult<T>>` | Each item has distance; no default average | Reactive stream of results |
| `Flux<T>` | Entities only, no distance metadata | Reactive stream of entities |

**A type having "Geo" in its name does not mean every repository mode supports it.** Check documentation for your exact Spring Data MongoDB version, especially when migrating synchronous code to reactive.

## 9. Reactive Repositories: `Flux<T>` or `Flux<GeoResult<T>>`

In reactive repositories, Spring Data MongoDB supports geospatial queries returning entities directly or each wrapped in `GeoResult<T>`:

File `ReactivePickupPointRepository.java`:

```java
package com.example.delivery.pickup;

import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactivePickupPointRepository
        extends ReactiveMongoRepository<PickupPoint, String> {

    Flux<PickupPoint> findByLocationNear(Point center);

    Flux<GeoResult<PickupPoint>> findByLocationNear(
        Point center,
        Distance maxDistance);
}
```

These two signatures differ in **parameter count**, so Java permits overloading. The `Point` + `Distance` overload returns `GeoResult` carrying distance metadata. If you need both return types for the same two-parameter list, separate interfaces or choose one design.

### 9.1. Why Not Return `Mono<GeoResults<T>>`?

Spring Data MongoDB documentation explicitly states that **reactive repository geospatial queries do not support `GeoResults<T>` and `GeoPage<T>` as return wrappers**, because they typically require collecting the entire result set upfront to compute average distances or page metadata.

**Wrong or unsupported by the reactive repository contract:**

```java
// DO NOT use this signature as a reactive derived-query API.
Mono<GeoResults<PickupPoint>> findByLocationNear(
    Point center, Distance radius);

Mono<GeoPage<PickupPoint>> findByLocationNear(
    Point center, Distance radius, Pageable pageable);
```

The two lines above are **independent anti-examples** and do not belong in the same interface (nor will they compile without imports). `Mono<GeoResults<T>>` is syntactically valid Java, yet **is not supported by Spring Data Reactive MongoDB repositories for derived geo-near queries**.

**Right:**

```java
Flux<GeoResult<PickupPoint>> findByLocationNear(
    Point center, Distance radius);
```

### 9.2. Reactive Service Consuming `GeoResult`

```java
package com.example.delivery.pickup;

import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public final class ReactivePickupSearchService {

    private final ReactivePickupPointRepository repository;

    public ReactivePickupSearchService(
            ReactivePickupPointRepository repository) {
        this.repository = repository;
    }

    public record NearbyPoint(
        String id, String name,
        double distanceValue, String distanceMetric) {}

    public Flux<NearbyPoint> search(
            double longitude, double latitude) {

        Point center = new Point(longitude, latitude);
        Distance max = new Distance(3, Metrics.KILOMETERS);

        return repository.findByLocationNear(center, max)
            .map(row -> {
                PickupPoint entity = row.getContent();
                Distance distance = row.getDistance();
                return new NearbyPoint(
                    entity.getId(),
                    entity.getName(),
                    distance.getValue(),
                    distance.getMetric().toString());
            });
    }
}
```

This service only demonstrates **how to consume `Flux<GeoResult<T>>`**. Before exposing it publicly, add coordinate validation, radius caps, authentication/tenant-scoped filtering, and authorization. Never stream the whole collection just because `Flux` allows streaming.

### 9.3. Computing Average Distance Reactively When Needed

You can intentionally materialize a **bounded result set** and compute the average using a unified metric:

```java
import java.util.List;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.Metrics;
import reactor.core.publisher.Mono;

Mono<Double> averageKm = repository
    .findByLocationNear(
        new Point(106.7009, 10.7769),
        new Distance(3, Metrics.KILOMETERS))
    .take(100)
    .collectList()
    .map(rows -> rows.stream()
        .map(GeoResult::getDistance)
        .mapToDouble(distance ->
            distance.in(Metrics.KILOMETERS).getValue())
        .average()
        .orElse(Double.NaN));
```

Here we average **at most 100 collected entries**, not the entire collection. Returning `NaN` when empty is an illustrative sentinel; production APIs should usually return `OptionalDouble`, a nullable field, or an explicit empty indicator. Never return `0 km` as it implies "average distance is 0".

**Note:** `take(100)` is a **client-side Flux limit**; to bound server and network work, prefer supported `Pageable`/`Limit` APIs or radius/limit-bounded queries. `collectList()` incurs memory overhead, so never collect an unbounded stream just to mimic imperative `GeoResults`.

### 9.4. `Pageable` in Reactive Repositories

Spring Data docs note that reactive geo queries can accept `Pageable` to limit emitted results, while **still returning `Flux<T>` or `Flux<GeoResult<T>>`**, not `Mono<GeoPage<T>>`:

```java
Flux<GeoResult<PickupPoint>> findByLocationNear(
    Point center, Distance radius, Pageable page);
```

This is an optional signature alternative to the two-parameter overload when needed. With `PageRequest`, limits/offsets apply via the repository query engine; test against your exact driver/framework version, preserve primary distance sorting, and keep in mind mutating data can shift ordering.

## 10. Derived `Within` Differs from `Near`

`Near` returns points **close to a center** with distance-sorting semantics. `Within` finds documents **inside a bounding shape**, without requiring per-result distance computation.

Repository example:

```java
import java.util.List;
import org.springframework.data.geo.Box;
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Point;

List<PickupPoint> findByLocationWithin(Circle circle);

List<PickupPoint> findByLocationWithin(Box box);
```

With a `Circle`:

```java
Circle area = new Circle(
    new Point(106.7009, 10.7769), 0.01);

List<PickupPoint> points =
    repository.findByLocationWithin(area);
```

**Important warning:** `0.01` in `Circle` does not mean "0.01 km" or "10 m". Across legacy coordinate and spherical representations, the radius can carry different unit semantics. If the requirement asks for a 3 km radius and distance ranking, `Near` with `Distance(..., Metrics.KILOMETERS)` is usually a clearer starting point.

### 10.1. `Box` Describes Coordinate Regions, Not Travel Ranges

```java
Box box = new Box(
    new Point(106.6980, 10.7730),
    new Point(106.7090, 10.7830));

List<PickupPoint> inside =
    repository.findByLocationWithin(box);
```

Results represent points inside a coordinate rectangle. Do not label every point in the box as "under 3 km from user", because corners lie farther from the center and road travel differs from raw coordinates.

### 10.2. `Polygon` and `GeoJsonPolygon`

When a service area is a GeoJSON polygon, Spring Data provides shape types such as `GeoJsonPolygon` and derived `...Within(GeoJsonPolygon)` methods in supported versions. For complex regions, holes, intersections, or custom conditions, `Criteria` and aggregation are often easier to control than an excessively long derived method name.

Never use `Near` as a substitute for "point inside geographic boundary", because "near a border" and "inside an authorized zone" are two distinct requirements.

## 11. Derived `Near` vs `MongoTemplate.geoNear`

When you need complex filters, `minDistance`, `maxDistance`, distance-field projection, or explicit geospatial index selection, move from repository method names to `NearQuery` and `MongoTemplate`.

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.NearQuery;

Point center = new Point(106.7009, 10.7769);
NearQuery near = NearQuery.near(center)
    .maxDistance(new Distance(3, Metrics.KILOMETERS));

GeoResults<PickupPoint> result =
    mongoTemplate.geoNear(near, PickupPoint.class);
```

`mongoTemplate` is an injected bean. This is an imperative API. When tenant filtering is needed in `NearQuery`, use the `query(Query)` builder with appropriate predicates for your API version rather than filtering in Java after fetching other tenants' data.

### 11.1. Why Spring Data Offers Two Paths

| Aspect | Derived Repository | `MongoTemplate`/`NearQuery` |
| --- | --- | --- |
| Search points within radius | Concise and readable | Explicit |
| Need distance metadata | `GeoResults<T>` (sync) or `Flux<GeoResult<T>>` (reactive) | `geoNear` / fluent geo near |
| Min/max distance, extra options | Depends on supported keywords/signatures | Directly configurable |
| Choosing geospatial index when multiple exist | Hard to control via method name | Configurable via near query/aggregation depending on version |
| Combining many filters, projections | Long, hard-to-read method names | Well-structured `Query`/aggregation |
| Computing distance field in pipeline | Not the main purpose | `$geoNear`/aggregation |

### 11.2. Do Not Use the Legacy `geoNear` Command

MongoDB 4.2 removed the **old `geoNear` command**. Since 2.2, Spring Data MongoDB implements `MongoOperations.geoNear(...)` using the **`$geoNear` aggregation stage**. Never copy `db.runCommand({geoNear: ...})` from outdated guides expecting it to run on modern MongoDB.

In aggregation, `$geoNear` must be the **first stage** and requires a geospatial index; when multiple geospatial indexes exist, specify the field/index via the appropriate API. Furthermore, operations with side effects such as `$out`/`$merge` or transactions carry specific support rules rather than acting as plain read queries.

### 11.3. When Should You Write `Criteria` Instead of `NearQuery`?

A requirement like "find stores **inside a boundary** that are open, with no distance sorting needed" is usually expressed more cleanly with `Criteria.where("location").within(...)` or `geoWithin` with proper indexes/filters, rather than running a geo-near query and re-sorting.

When you need "nearest items and per-result distances", pick `GeoResults` or `$geoNear`. When you need "points inside a shape only", pick `Within`/`$geoWithin`. Two approaches may overlap geographically yet **differ in semantics, cost, and metadata**.

## 12. Designing a Nearest-Pickup Service with Validation

For a public endpoint, required steps include:

```text
Authentication/authorization
     |
     v
Trusted tenant ID
     |
     v
Validate coordinates and radius
     |
     v
Build NearQuery with tenantId and active=true
     |
     v
Limit results AT DATABASE
     |
     v
Map GeoResult<PickupPoint> to API DTO
```

### 12.1. DTO with Explicit Unit Labels

File `NearbyPickupResponse.java`:

```java
package com.example.delivery.pickup;

public record NearbyPickupResponse(
    String id,
    String name,
    double distanceKm
) {}
```

The name `distanceKm` clearly states the unit in the response. Never return a unitless `distance=0.5` leaving the frontend to guess whether it is kilometers, meters, or miles.

### 12.2. Coordinate and Radius Validator

File `GeoSearchInput.java`:

```java
package com.example.delivery.pickup;

public record GeoSearchInput(
    double longitude,
    double latitude,
    double radiusKm,
    int maxResults
) {
    public GeoSearchInput {
        if (!Double.isFinite(longitude)
                || longitude < -180 || longitude > 180) {
            throw new IllegalArgumentException(
                "Longitude must be in [-180, 180]");
        }
        if (!Double.isFinite(latitude)
                || latitude < -90 || latitude > 90) {
            throw new IllegalArgumentException(
                "Latitude must be in [-90, 90]");
        }
        if (!Double.isFinite(radiusKm)
                || radiusKm <= 0 || radiusKm > 25) {
            throw new IllegalArgumentException(
                "radiusKm must be in (0, 25]");
        }
        if (maxResults < 1 || maxResults > 50) {
            throw new IllegalArgumentException(
                "maxResults must be in [1, 50]");
        }
    }
}
```

The `25 km` and `50 results` bounds are **illustrative policies**, not hard MongoDB limits. Projects choose limits based on SLAs, data volume, and real load.

### 12.3. Service Using `MongoTemplate.geoNear` with `query` + `limit`

File `NearbyPickupService.java`:

```java
package com.example.delivery.pickup;

import java.util.List;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.NearQuery;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public final class NearbyPickupService {

    private final MongoTemplate template;

    public NearbyPickupService(MongoTemplate template) {
        this.template = template;
    }

    public List<NearbyPickupResponse> findNearby(
            String authorizedTenantId,
            GeoSearchInput input) {

        if (authorizedTenantId == null
                || authorizedTenantId.isBlank()) {
            throw new IllegalArgumentException(
                "Authenticated tenant is required");
        }
        if (input == null) {
            throw new IllegalArgumentException(
                "Search input is required");
        }

        Point center = new Point(
            input.longitude(), input.latitude());

        Query filters = Query.query(
            Criteria.where("tenantId").is(authorizedTenantId)
                .and("active").is(true));

        NearQuery near = NearQuery.near(center)
            .maxDistance(new Distance(
                input.radiusKm(), Metrics.KILOMETERS))
            .in(Metrics.KILOMETERS)
            .query(filters)
            .limit(input.maxResults());

        GeoResults<PickupPoint> rows =
            template.geoNear(near, PickupPoint.class);

        return rows.getContent().stream()
            .map(row -> new NearbyPickupResponse(
                row.getContent().getId(),
                row.getContent().getName(),
                row.getDistance()
                    .in(Metrics.KILOMETERS)
                    .getValue()))
            .toList();
    }
}
```

`NearQuery.query(filters)` pushes tenant and `active` predicates **into the MongoDB query**, rather than filtering after downloading other tenants' documents. `limit(...)` caps results in the query path instead of calling `rows.getContent().subList(0, 50)` after the server returns an oversized list.

### 12.4. Why Use Both `maxDistance` and `in(Metrics.KILOMETERS)`?

- `maxDistance(new Distance(..., Metrics.KILOMETERS))` sets the **search radius**.
- `in(Metrics.KILOMETERS)` requests the **output distance unit** on the builder.

These two choices are related but distinct. When using `NearQuery` with a legacy-coordinate `Point`, the metric handles converting spherical radian distances to km. With `GeoJsonPoint`, `$geoNear`'s native unit is meters; do not overlook this difference when changing the query center type.

The code above intentionally uses `Point` and explicit metrics for consistency; verify expected output with tests against your project's actual geospatial index and driver.

### 12.5. APIs Should Not Take Tenant IDs from User Query Strings

Anti-example:

```text
GET /pickup-points/nearby?tenantId=TENANT-B
```

If the controller reads `tenantId` from the URL and passes it straight to the repository, callers can probe warehouse locations belonging to other tenants. The right approach is deriving the tenant from the authentication context and role, or validating an authorized tenant path before invoking the service.

Pickup points can be sensitive data (internal warehouses, staff locations). Enforce authorization at the service/query layer and never leak unauthorized coordinates via exceptions, logs, or APIs.

### 12.6. `Distance` Is Geographic Distance, Not Delivery Route Distance

`$geoNear` computes distance under MongoDB's spatial model. A location 500 m away as the crow flies might be several kilometers by road due to rivers, bridges, or one-way streets.

If the product needs **estimated time of arrival (ETA)**, use geo-near to **quickly filter candidates**, then call a routing service (if authorized and appropriate) for those filtered candidates. Never label a MongoDB `Distance` as `estimatedTravelTime`.

## 13. Measurement Units: The Easiest Way to Get Wrong Results

MongoDB supports:

- **Legacy pairs** such as `[106.7009, 10.7769]`.
- **GeoJSON Points** such as `{"type":"Point","coordinates":[106.7009,10.7769]}`.

When running `$geoNear` with spherical geometry:

| Query Center | Common Native Distance Interpretation | How to Handle in Spring Data |
| --- | --- | --- |
| Legacy `Point` / coordinate pair | Distance in **radians** on the sphere in many cases | Use `Metric` to convert to km/miles via the builder |
| `GeoJsonPoint` / `$geometry` | Distance in **meters** | Follow the GeoJSON unit contract; do not treat values as radians |
| `Distance(3, Metrics.KILOMETERS)` | Requests **3 km** at the Spring layer | Let Spring convert; test outputs and actual generated queries |

**Do not write**:

```java
// ANTI-PATTERN: missing Metric, then assuming max=3 means 3 km.
Distance radius = new Distance(3);
```

`new Distance(3)` uses a neutral metric. In some query paths, `3` is interpreted in native units rather **than km**. Always attach a metric when business rules specify km/miles, unless intentionally operating on a coordinate system with another agreed unit.

### 13.1. Longitude/Latitude Are Not Meters

`new Point(106.7009, 10.7769)` holds angles in a geographic coordinate system; simple subtraction does not yield meters:

```java
double dx = other.getX() - center.getX();
double dy = other.getY() - center.getY();
double distanceInMeters = Math.sqrt(dx * dx + dy * dy);
// WRONG: result is in coordinate degrees, not meters.
```

Distances across longitude/latitude cannot be computed accurately with Euclidean distance on degrees in general. Use proper geographic formulas or MongoDB `2dsphere`, and verify against known points.

### 13.2. Comparing GeoJSON and Legacy in `$geoNear`

With a GeoJSON center:

```javascript
db.pickup_points.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      key: "location",
      spherical: true,
      maxDistance: 3000, // Meters with GeoJSON.
      distanceField: "distanceMeters",
      query: {
        tenantId: "TENANT-A",
        active: true
      }
    }
  },
  { $limit: 20 },
  { $project: {
      name: 1,
      location: 1,
      distanceMeters: 1
  }}
])
```

In this example `3000` means **3000 meters** because the query uses a GeoJSON Point, and `distanceMeters` is also in meters. With a legacy center in `$geoNear`, the native value may be **radians**; getting km output requires an appropriate conversion/`distanceMultiplier` for that query shape. Never copy `maxDistance: 3000` verbatim from GeoJSON to legacy thinking they behave identically.

### 13.3. Changing Metrics Can Change the Operator

According to Spring Data MongoDB documentation, passing a `Distance` with a `Metric` can cause a derived query to switch from `$near` to `$nearSphere`. Placing `@GeoSpatialIndexed(type = GEO_2DSPHERE)` on the field also influences operator selection for that query. Therefore:

- Do not assume `Near` always renders the exact same JSON.
- Check driver/server/`MappingMongoConverter` and Spring Data behavior when upgrading.
- Test **results and distances** rather than only asserting operator names, unless the test specifically verifies mapping.

### 13.4. `maxDistance` Measures to the Nearest Part of a Shape

`$near` can return candidates based on shortest distance to the geometry. For polygons or multi-points, distance may be measured from the **nearest point on the geometry** rather than a computed centroid. This lesson uses `GeoJsonPoint` to avoid semantic ambiguity. For polygon/line data, explicitly define which reference point business distances measure from.

## 14. Geospatial Tests Must Verify BSON, Indexes, and Real Distances

A unit test mocking `PickupPointRepository` to return a hardcoded list does not prove:

- Whether Spring Data parses `Near` and `Distance` properly.
- Whether the `2dsphere` index exists and is accepted by MongoDB.
- Whether distances use **km**, **meters**, or **radians**.
- Whether nearest-to-farthest ordering is calculated by the server using real positions.
- Whether `tenantId` and `active` filters execute inside the database.
- Whether `GeoResults<T>` contains sensible distances and average values.

You need integration tests against a **real test MongoDB database** with indexes and controlled fixtures. You do not need a replica set solely for basic geo-near reads; if your application uses transactions, test transactions on a topology that supports them.

### 14.1. Preparing Tenant-Scoped Repositories

To test both distance and tenant isolation, add this signature to `PickupPointGeoResultsRepository`:

```java
GeoResults<PickupPoint> findByTenantIdAndActiveTrueAndLocationNear(
    String authorizedTenantId,
    Point center,
    Distance radius);
```

In `PickupPointRepository`, add another signature returning plain entities:

```java
List<PickupPoint> findByTenantIdAndActiveTrueAndLocationNear(
    String authorizedTenantId,
    Point center,
    Distance radius);
```

Since these methods live in **two separate interfaces**, there is no return-type overload conflict. The geo-near repositories enforce tenant/active filters, while API responses should expose only data the caller is authorized to see.

### 14.2. Testing with `@DataMongoTest` (Imperative)

Example using Spring Boot 3.x, JUnit 5, and AssertJ. Configure `spring.data.mongodb.uri` in the **test profile** pointing to a dedicated test database. Annotation/package imports may differ in Spring Boot 4.x or other major Spring Data versions; verify against your actual dependencies before compiling.

File `PickupPointGeoQueryIntegrationTest.java`:

```java
package com.example.delivery.pickup;

import com.mongodb.client.model.Filters;
import java.util.List;
import java.util.UUID;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
class PickupPointGeoQueryIntegrationTest {

    @Autowired
    MongoTemplate template;

    @Autowired
    PickupPointRepository regularRepository;

    @Autowired
    PickupPointGeoResultsRepository geoRepository;

    @BeforeEach
    void ensureIndexExists() {
        // Run only in an isolated TEST database.
        template.getCollection("pickup_points")
            .createIndex(new Document("location", "2dsphere"));
    }

    @Test
    void nearQueryRespectsTenantRadiusAndDistanceMetadata() {
        String suffix = UUID.randomUUID().toString();
        String tenant = "TENANT-TEST-" + suffix;

        String idHere = "HERE-" + suffix;
        String idNearby = "NEAR-" + suffix;
        String idFar = "FAR-" + suffix;
        String idOther = "OTHER-" + suffix;

        try {
            template.insertAll(List.of(
                new PickupPoint(
                    idHere, tenant, "Right at center",
                    true, new GeoJsonPoint(106.7009, 10.7769)),
                new PickupPoint(
                    idNearby, tenant, "Near center",
                    true, new GeoJsonPoint(106.7060, 10.7794)),
                new PickupPoint(
                    idFar, tenant, "Very far",
                    true, new GeoJsonPoint(106.8500, 10.9900)),
                new PickupPoint(
                    idOther, "OTHER-" + tenant, "Other tenant",
                    true, new GeoJsonPoint(106.7010, 10.7770))
            ));

            Point center = new Point(106.7009, 10.7769);
            Distance radius =
                new Distance(3, Metrics.KILOMETERS);

            GeoResults<PickupPoint> geo =
                geoRepository
                    .findByTenantIdAndActiveTrueAndLocationNear(
                        tenant, center, radius);

            List<GeoResult<PickupPoint>> rows =
                geo.getContent();

            assertThat(rows).hasSize(2);
            assertThat(rows.get(0).getContent().getId())
                .isEqualTo(idHere);
            assertThat(rows.get(1).getContent().getId())
                .isEqualTo(idNearby);

            double nearestKm = rows.get(0).getDistance()
                .in(Metrics.KILOMETERS).getValue();
            double nextKm = rows.get(1).getDistance()
                .in(Metrics.KILOMETERS).getValue();

            assertThat(nearestKm)
                .isGreaterThanOrEqualTo(0.0)
                .isLessThan(0.05);
            assertThat(nextKm)
                .isGreaterThan(0.05)
                .isLessThan(3.0);
            assertThat(geo.getAverageDistance()
                .in(Metrics.KILOMETERS).getValue())
                .isBetween(0.0, 3.0);

            List<PickupPoint> plain =
                regularRepository
                    .findByTenantIdAndActiveTrueAndLocationNear(
                        tenant, center, radius);

            assertThat(plain).hasSize(2);
            assertThat(plain)
                .extracting(PickupPoint::getId)
                .containsExactly(idHere, idNearby);

        } finally {
            template.getCollection("pickup_points")
                .deleteMany(Filters.in(
                    "_id", idHere, idNearby, idFar, idOther));
        }
    }
}
```

Values for warehouses A/B and "near" vs "far" coordinates are spaced well apart so tests do not assert centimeter-exact distances. Instead of `assertThat(nextKm).isEqualTo(0.623197...)`, the test verifies reasonable intervals and expected order.

### 14.3. Key Points to Keep in Mind for the Test Above

1. **The index must exist before the query.** `@GeoSpatialIndexed` alone does not prove the database already has the index.
2. **Isolated database.** `@DataMongoTest` will not create an isolated database if the project points its URI to a dev/shared cluster. Only run when the test profile targets an authorized test environment.
3. **Four random IDs** and ID-scoped cleanup. Never run `dropDatabase()` or `deleteMany({})`.
4. If multiple tests share a database, `createIndex` inside `@BeforeEach` may conflict with migrations/index names/specs from other tests; creating indexes in a pre-test fixture/migration is more stable.
5. `tenant` is generated per test to isolate data from other tests.
6. `@DataMongoTest` only verifies configuration when Spring scans the right repository package; if your project customizes repository scanning, add `@EnableMongoRepositories`/`@Import` as needed.
7. All measurements/geo-near behaviors depend on server version, index, and query mapping; **tests were not executed while authoring this text**, so never claim real-environment results without running them.

### 14.4. Testing Swapped Coordinates

A unit test for the validator:

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import org.junit.jupiter.api.Test;

@Test
void rejectsInvalidLatitudeAfterSwappingCoordinates() {
    assertThatThrownBy(() ->
        new GeoSearchInput(
            10.7769, 106.7009, 3.0, 20))
        .isInstanceOf(IllegalArgumentException.class);
}
```

Here `latitude=106.7009` exceeds `90`, so the validator catches the mistake. However, if swapped coordinates **still fall within valid bounds**, a range validator cannot tell which axis the caller meant. APIs and frontends must agree on the `longitude`/`latitude` contract and test with a reference point at a known location.

### 14.5. Checking Raw BSON After Insert

If tests only assert entities returned by `template.findById`, the converter can mask BSON layout differences. Verify directly:

```java
Document stored = template.getCollection("pickup_points")
    .find(new Document("_id", idHere))
    .first();

assertThat(stored).isNotNull();
Document geoJson = stored.get("location", Document.class);
assertThat(geoJson.getString("type")).isEqualTo("Point");
assertThat(geoJson.getList("coordinates", Double.class))
    .containsExactly(106.7009, 10.7769);
```

This is an **inline fragment inside an integration test** with `template`, `idHere`, and matching imports, not a standalone class. It confirms the persisted field is a GeoJSON `Point` with coordinates in the exact expected order. If custom converters are configured, this test catches mismatches right at the BSON layer.

### 14.6. Reactive Testing with `StepVerifier`

For a reactive repository:

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;
import reactor.test.StepVerifier;

StepVerifier.create(
        reactiveRepository.findByLocationNear(
            new Point(106.7009, 10.7769),
            new Distance(3, Metrics.KILOMETERS)))
    .assertNext(first -> {
        assertThat(first.getContent()).isNotNull();
        assertThat(first.getDistance()).isNotNull();
    })
    .thenConsumeWhile(row -> row.getDistance() != null)
    .verifyComplete();
```

This snippet sits inside a test with `reactiveRepository` and imports configured. It only illustrates **subscribing and receiving `GeoResult` items**; it does not verify tenant filters or expected IDs. To prove correctness, write a dedicated reactive test with fixtures matching the imperative test and check IDs, ordering, metrics, radius, and the real index.

Never declare `Mono<GeoResults<T>>` as a derived reactive repository return type expecting `StepVerifier` to fix unsupported framework behavior. If an average is needed, compute it over a **bounded** stream with explicitly defined semantics.

## 15. Monitoring Indexes and Spatial Query Costs

A geospatial query does not mean "other indexes are unnecessary". In a multi-tenant collection with millions of points, proximity searches can still generate heavy load unless tenant/active predicates are well supported by the query plan.

### 15.1. Single vs Compound Indexes

Basic index:

```javascript
db.pickup_points.createIndex(
  { location: "2dsphere" },
  { name: "idx_geo_location" }
)
```

A compound candidate for tenant-scoped queries:

```javascript
db.pickup_points.createIndex(
  {
    tenantId: 1,
    active: 1,
    location: "2dsphere"
  },
  { name: "idx_tenant_active_geo" }
)
```

This is a **candidate requiring verification**, not guaranteed optimal for every workload. Key order, tenant cardinality, `active` ratio, coordinate distribution, and MongoDB version all affect the planner; measure with `explain()` on representative workloads.

If the application also executes spatial queries without a tenant filter, consider retaining an appropriate standalone index. A compound index requiring equality prefixes does not serve every existing query.

### 15.2. A MongoDB GeoJSON Query for Reference Comparison

```javascript
const center = {
  type: "Point",
  coordinates: [106.7009, 10.7769]
};

db.pickup_points.find({
  tenantId: "TENANT-A",
  active: true,
  location: {
    $near: {
      $geometry: center,
      $maxDistance: 3000 // Meters with GeoJSON.
    }
  }
})
```

This command matches the **business intent** of "read active points for tenant A within 3 km, ordered nearest to farthest". Do not claim the JSON emitted by every derived repository/version matches token-for-token; differences between legacy `Point` and `GeoJsonPoint`/Metrics can alter serialization.

### 15.3. Explain Plans and Examined Document Counts

On a test database:

```javascript
db.pickup_points.find({
  tenantId: "TENANT-A",
  active: true,
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      $maxDistance: 3000
    }
  }
}).explain("executionStats")
```

Things to inspect depending on server version and explain format:

- Which index did the planner select, and is it the expected geospatial index?
- Are `totalKeysExamined` / `totalDocsExamined` disproportionately high compared to results returned?
- Is there an expensive post-geo sort or filter?
- How does latency change when the radius grows from 1 km to 25 km?
- Does a large tenant have a skewed spatial distribution making queries slower than for other tenants?

Do not evaluate performance on a handful of test documents. Near queries with wide radii in dense areas with tens of thousands of locations can return massive payloads, especially if the API lacks a limit.

### 15.4. `$near` Already Sorts by Distance

`$near` orders results nearest to farthest. Adding `sort({name:1})` afterward can force an **extra sort**, destroying nearest-first ordering and increasing cost. If you need grouping or tie-breaking, redesign the sorting goal and verify computed distances:

```text
Near distance ranking:
  1. Warehouse A : 0.00 km
  2. Warehouse B : 0.63 km

Sort by name:
  ...no longer guarantees the first item is closest...
```

### 15.5. `$geoNear` Aggregation Has Specific Constraints

When using `$geoNear` in aggregation:

- `$geoNear` must be the **first stage** of the pipeline.
- It requires a geospatial index, and may need a field `key` specified if the collection has multiple geo indexes.
- Business filter predicates should go into `$geoNear`'s `query` option (`NearQuery.query(...)`) when appropriate.
- Never nest a `$near` predicate inside `$geoNear`'s inner `query`.
- Only place `$limit`, `$project`, `$group`, etc., after the geospatial stage in valid order.

In modern MongoDB, never use the removed `geoNear` database command. Old Java tutorials mentioning `geoNear` are sometimes referring to the **Java API method** `MongoTemplate.geoNear` (still supported in compatible versions) rather than the obsolete server command. Distinguish **Java API names** from **BSON server commands**.

## 16. Failure Modes and Diagnostics

| Symptom | Possible Cause | Inspection / Fix |
| --- | --- | --- |
| `$near` reports no geospatial index found | Missing `2dsphere` or index created on wrong field | `getIndexes()`, verify BSON `location`, run index migration |
| All results appear very far away | Swapped longitude/latitude | Verify `new Point(longitude, latitude)`; test known coordinates |
| Too many results returned beyond 3 km | Passed bare `3` without metric or wrong native unit | Use `Distance(3, Metrics.KILOMETERS)`, test radius |
| Distance values ~1000x larger than expected | Confused meters and kilometers with GeoJSON | Check `getMetric()` and `NearQuery.in(...)` |
| Nearest warehouse has non-zero distance despite "same" coordinates | Precision/coordinate payload or query center mismatch | Inspect raw BSON, compare x/y and rounding |
| `GeoResults` missing distance | Used `List<T>` or query path that does not compute distances | Switch to return type/query path supporting `GeoResult<T>` |
| Reactive repository fails declaring `Mono<GeoResults<T>>` | Unsupported return wrapper in reactive repositories | Use `Flux<GeoResult<T>>` |
| `GeoPage` behaves unexpectedly | Framework/pagination/geoNear version differences | Run version-specific integration tests; consider `NearQuery.limit` |
| `findByLocationWithin(Circle)` yields different results from `Near` | Different shape radius/units, Within does not rank by distance | Verify operator/unit/coordinates and test geometry |
| No results on GeoJSON field | Data stored as legacy array or wrong index type | Inspect raw `location` Document and indexes |
| Documents missing location do not appear | Geospatial index omits missing/invalid fields | Enforce data quality policies, check imports/migrations |
| Active/tenant query is slow | Suboptimal planner/index | Run `explain`, evaluate compound index, cap radius and result count |
| Another tenant's data leaks into API | Repository lacks tenant predicate, or post-filters in Java | Enforce authorization and filter inside the database |
| `@GeoSpatialIndexed` present but index missing | Auto-index creation disabled or metadata not applied | Run migration/`ensureIndex`, check `getIndexes()` |
| Spatial query inside aggregation fails | `$geoNear` is not the first stage | Move `$geoNear` to start of pipeline |
| Query combining `$near` with `$text` fails | Two incompatible special-index operators | Redesign search pipeline instead of combining directly |
| Multiple geo indexes cause ambiguity error | Geo field for `$geoNear` not specified | Specify index field/key via supported API |
| Driver/framework upgrade shifts radius | Mapping/operator/metric changes across versions | Pin versions and run regression tests on real DB |

### 16.1. GeoJSON Stored as a JSON String

This is a common data bug:

```javascript
// WRONG: location is a String containing JSON.
{
  location:
    '{"type":"Point","coordinates":[106.7009,10.7769]}'
}
```

Correctly stored as a BSON document:

```javascript
{
  location: {
    type: "Point",
    coordinates: [106.7009, 10.7769]
  }
}
```

A string that looks like JSON is not automatically understood by MongoDB as GeoJSON. Parse and validate before writing, or migrate badly stored records.

### 16.2. Empty Results Do Not Always Mean "No Stores"

Empty results can happen because:

- No points lie within the radius.
- `tenantId`/`active` filters correctly matched nothing for that tenant.
- Documents lack `location` or have malformed fields.
- The client sent swapped coordinates or an overly tiny radius.
- The query used an unexpected geometric unit.
- Index/mapping issues—which in some cases throw an error rather than returning empty.

The service should distinguish "no matching points found" from "invalid request" and "MongoDB operation failed"; never swallow every exception into an empty list.

### 16.3. Missing-Index Errors Must Not Be Solved by Full Collection Scans

When `$near` lacks an index, the right fix is creating the proper index and cleaning invalid data. **Never** fetch the entire collection via `findAll()` and calculate distances in Java to bypass the index, especially with multi-tenant data or millions of documents.

If an exceptional fallback ever exists, it requires strict dataset bounds, authorization, resource caps, and clear SLAs. An unbounded fallback easily turns an index mishap into a system-wide outage.

### 16.4. When Nearest Distance Should Not Win

Geometrically closest does not always mean best:

```text
Warehouse A: 0.5 km away but closed
Warehouse B: 1.0 km away and in stock
Warehouse C: 0.7 km away but belongs to another tenant
```

Products must filter `active`, inventory, permissions, delivery zones, opening hours, or capacity **per business rules**, rather than blindly sorting by `GeoResult.getDistance()` and returning the first item.

## 17. Choosing an API by Use Case

| Problem | Starting Spring Data API | Recommended Return Type |
| --- | --- | --- |
| Find entities in radius, numeric distance not needed | Derived `findByLocationNear(Point, Distance)` | `List<T>` or `Flux<T>` |
| Find nearest and show distance per item | Derived geo-near returning computed distances | `GeoResults<T>` (sync), `Flux<GeoResult<T>>` (reactive) |
| Need average distance over results | `GeoResults` (sync), or compute on a bounded reactive stream | `Distance` / unit-explicit DTO |
| Require `Page` with distances | `GeoPage` in supported sync APIs | `GeoPage<T>`, verify version/pagination |
| Check containment inside rectangle only | `...Within(Box)` | `List<T>` / `Flux<T>` |
| GeoJSON polygon region | `...Within(GeoJsonPolygon)` if supported, or `Criteria` | `List<T>`/`Flux<T>` |
| Complex tenant filters, minDistance, limit, options | `MongoTemplate.geoNear(NearQuery)` | `GeoResults<T>` (sync) |
| Distance computation and rich aggregation pipeline | `$geoNear` aggregation | Projection DTO with distance field |
| Road route / ETA | Geo-near only filters candidates | Integrate a dedicated routing service |

**Architecture tip:** repository method names work well when queries are short, clear, and stable. Once a method grows long with many filters and distance options, switch to a template/custom repository so reviewers can read the query structure clearly. Never force every query into a hundred-character derived method name.

## 18. Misconceptions to Eliminate

1. **"Point is always GeoJSON."** False: `Point` can serialize as legacy coordinates, whereas `GeoJsonPoint` represents GeoJSON.
2. **"x is latitude, y is longitude."** False for WGS84 GeoJSON: x = longitude, y = latitude.
3. **"Distance(3) means 3 km."** False without an explicit `Metric` or unit policy.
4. **"GeoResults is an entity field."** False: it is a query result wrapper.
5. **"Changing `List<T>` to `GeoResults<T>` creates a valid Java overload with the same parameters."** False: Java does not overload on return type alone.
6. **"Mono<GeoResults<T>> is a valid derived reactive geo-query return type."** Not supported by Spring Data MongoDB reactive repositories per documentation.
7. **"Reactive has `GeoPage` just like imperative."** False; reactive typically uses `Flux<GeoResult<T>>` with optional `Pageable`.
8. **"Adding `@GeoSpatialIndexed` ensures MongoDB creates the index immediately."** Not necessarily; check DB/migrations.
9. **"Near is the same as Within."** Near performs distance ranking; Within checks spatial containment.
10. **"GeoPage average is the mean across all documents."** It is computed over the page/result slice, not automatically the whole collection.
11. **"`$geoNear` can sit anywhere in the pipeline."** False: it must be first.
12. **"Calling `geoNear` in Java always invokes the old MongoDB command."** False: modern Spring Data uses the `$geoNear` stage.
13. **"Combining `$near` and `$text` automatically uses both special indexes."** False; MongoDB restricts combining special-index query operators.
14. **"The closest warehouse always delivers fastest."** False: terrain, road networks, stock, and operating hours also matter.
15. **"Having `tenantId` on the entity automatically enforces security."** False: queries and authorization must explicitly scope the tenant.
16. **"`getDistance().getValue()` is always in meters."** False: check the `Metric` and how the query was constructed.
17. **"Not seeing PP-B in results means PP-B was deleted."** Not necessarily: radius, filters, index, or mapping could exclude it.
18. **"You can replace a geo-index by loading the whole collection into Java."** Never suitable for large datasets.

## 19. Pre-Production Checklist for Geo-Near APIs

### 19.1. Mapping and Data Types

1. **Coordinate contract:** client and server agree on `longitude, latitude` and WGS84.
2. **Range validation:** longitude in `[-180,180]`, latitude in `[-90,90]`, reject `NaN`/`Infinity`.
3. **GeoJSON or legacy?** Does the field hold `GeoJsonPoint` or `Point`? Did you inspect raw BSON?
4. **Never store GeoJSON as a String** and never swap `coordinates` order.
5. **Appropriate index exists:** `2dsphere` for GeoJSON; verify with `getIndexes()`.
6. **Versioned index migrations:** do not rely solely on auto-index creation.
7. **Data quality checks:** handle missing/null/malformed locations or legacy imports.

### 19.2. Queries and Results

8. **Choose the right semantics:** `Near` for distance ranking, `Within` for region checks.
9. **Attach explicit Metrics:** `Distance(3, Metrics.KILOMETERS)` instead of a "mystery number 3".
10. **Read the right return type:** `List<T>` vs `GeoResults<T>` vs `Flux<GeoResult<T>>`.
11. **Do not force `GeoResults`/`GeoPage` onto unsupported reactive repositories.**
12. **Check min/max distance:** are units converted properly for `Point`/`GeoJSON`?
13. **Inspect the planner:** does the query use the geospatial index on the right field?
14. **Enforce hard bounds:** radius and max results match SLAs, never load unbounded data.
15. **Avoid breaking sort order:** preserve nearest-first when business requires proximity ranking.
16. **Understand pagination:** offset paging over mutating data can duplicate or skip items.
17. **Know what average distance represents:** the page, limit slice, or entire result set.

### 19.3. Security, Reliability, and Tests

18. **Filter tenant at the database:** never post-filter in Java after loading unauthorized data.
19. **Validate/authorize requests:** never trust user-supplied tenant IDs.
20. **Protect location privacy:** avoid exposing warehouse/user coordinates in logs.
21. **Error handling:** distinguish bad input, missing index, MongoDB errors, and empty results.
22. **Real MongoDB integration tests:** at center/near/far/other tenant/inactive.
23. **Version-upgrade regression tests:** operators, metrics, mapping, query plans.
24. **Monitoring:** geospatial query latency p95/p99, throughput, examined docs, radius/limit distributions.
25. **Sane degradation mode:** never fall back to full collection scans when an index is missing.

## 20. Practice Exercises

An EV charging-station finder app has a `charging_stations` collection. Each station has `tenantId`, `available`, `connectorType`, and `location`. The UI needs to display up to 10 stations within 5 km of the user, along with distance in km.

### Exercise 1 — Create GeoJSON Data and Index

Insert three stations:

```javascript
db.charging_stations.insertMany([
  {
    _id: "CS-1",
    tenantId: "TENANT-EV",
    available: true,
    connectorType: "CCS2",
    location: {
      type: "Point",
      coordinates: [106.7009, 10.7769]
    }
  },
  {
    _id: "CS-2",
    tenantId: "TENANT-EV",
    available: true,
    connectorType: "CCS2",
    location: {
      type: "Point",
      coordinates: [106.7150, 10.7800]
    }
  },
  {
    _id: "CS-3",
    tenantId: "TENANT-EV",
    available: false,
    connectorType: "CCS2",
    location: {
      type: "Point",
      coordinates: [106.7000, 10.7770]
    }
  }
])

db.charging_stations.createIndex(
  { location: "2dsphere" },
  { name: "idx_charging_location" }
)
```

Explain why `CS-3` must **not** appear when searching only for available stations even though it is closer to the center than `CS-2`.

### Exercise 2 — Derived Repository

Declare entity `ChargingStation` with `GeoJsonPoint location`, `@GeoSpatialIndexed(type = GEO_2DSPHERE)`, and method:

```java
List<ChargingStation>
    findByTenantIdAndAvailableTrueAndLocationNear(
        String tenantId,
        Point center,
        Distance radius);
```

Explain:

1. Which field does `Location` in the method name map to?
2. How does `Point` differ from `GeoJsonPoint`?
3. How should the radius be passed for **5 km**?
4. Does the method return the distance to each station?
5. Where must the tenant ID come from?

### Exercise 3 — `GeoResults`

Switch to a **separate imperative repository** with:

```java
GeoResults<ChargingStation>
    findByTenantIdAndAvailableTrueAndLocationNear(
        String tenantId,
        Point center,
        Distance radius);
```

Iterate `getContent()`, access `GeoResult.getContent()` and `getDistance()`, and return DTOs:

```json
{
  "id": "CS-2",
  "distanceKm": 1.6,
  "connectorType": "CCS2"
}
```

The `1.6` value in the JSON **only illustrates response formatting**, not an exact calculation from the dataset above. In tests, use the real distance returned by MongoDB.

### Exercise 4 — Reactive Repository

With `ReactiveMongoRepository<ChargingStation,String>`, declare a method returning:

```java
Flux<GeoResult<ChargingStation>>
    findByLocationNear(Point center, Distance radius);
```

Explain why:

```java
Mono<GeoResults<ChargingStation>>
    findByLocationNear(Point center, Distance radius);
```

is not a supported derived reactive geo-query return type. If you want the average distance of the **10 nearest stations**, where should you bound and materialize the stream to avoid excessive memory/network usage?

### Exercise 5 — Checking Measurement Units

Using center `new Point(106.7009, 10.7769)`, compare:

```java
new Distance(5);
new Distance(5, Metrics.KILOMETERS);
new Distance(5, Metrics.MILES);
```

Explain why only one of the three accurately expresses **5 km**, and how the query builder handles MongoDB native metrics.

### Exercise 6 — `Near` vs `Within`

1. Use `findByLocationNear(center, radius)` to search stations by distance.
2. Use `findByLocationWithin(Box)` to search stations inside a coordinate region.
3. Predict differences in results and ordering.
4. Explain why a bounding box does not mean "stations under 5 km".
5. If there is a polygonal urban restriction zone, should you use `Within(GeoJsonPolygon)` or `Near`?

### Exercise 7 — `GeoPage` and Performance

An API uses `GeoPage<T>` to return total stations along with pages. Analyze:

- What must the query do to compute the total?
- Could average distance reflect the **current page** or the whole set?
- If a new station is added near the center between page fetches, can items be duplicated or skipped?
- If the UI only needs the first 10 stations, is `NearQuery.limit(10)` preferable to counting totals?
- For reactive repositories, what is the alternative to `GeoPage`?

### Exercise 8 — Production Outage

One day, the API reports no geospatial index found. A developer proposes:

```java
// ANTI-PATTERN: scanning the entire collection in the service.
return repository.findAll().stream()
    .filter(station -> isNearInJava(station, center))
    .toList();
```

Explain why this solution fails for large collections and breaks authorization/unit guarantees. Propose a remediation plan:

1. Stop the unbounded fallback.
2. Inspect `getIndexes()`/field mapping.
3. Audit invalid GeoJSON records.
4. Create the right index via an authorized migration.
5. Re-run integration tests and `explain("executionStats")`.
6. Monitor latency, documents examined, and failed requests.

### Exercise 9 — Testing Single-Point Correctness

Write an integration test against test MongoDB:

- Seed one station **at the exact center coordinates**, one a few hundred meters away, and one very far away.
- Add another tenant's station right next to the center.
- Query the repository near the center with a 2 km radius.
- Assert the nearest same-tenant station comes first with distance near 0.
- Assert the distant station and the other tenant's station do not appear.
- Compare raw BSON against the entity to confirm `location.type="Point"` and `coordinates[0]` is longitude.
- Avoid asserting float distances to excessive decimal places; use reasonable tolerances.

### Exercise 10 — When to Switch to `MongoTemplate`

A new API requires:

```text
Input: authenticated tenantId, center, minKm, maxKm, maxResults
Filter: available=true, connectorType="CCS2"
Output: at most maxResults stations, with distance in km
```

Write `NearQuery` with:

```java
NearQuery near = NearQuery.near(center)
    .minDistance(new Distance(minKm, Metrics.KILOMETERS))
    .maxDistance(new Distance(maxKm, Metrics.KILOMETERS))
    .in(Metrics.KILOMETERS)
    .query(Query.query(
        Criteria.where("tenantId").is(authorizedTenantId)
            .and("available").is(true)
            .and("connectorType").is("CCS2")))
    .limit(maxResults);
```

Assume inputs are validated, `minKm >= 0`, `maxKm > minKm`, and `maxResults` is within system bounds. Explain why this logic is easier to review than a sprawling derived method name and why filters must execute in the server query.

## 21. Quick Review Questions

| Question | Suggested Answer |
| --- | --- |
| GeoJSON `coordinates` order? | `[longitude, latitude]` |
| Find nearest stores by distance? | `Near` + geospatial index |
| Find points inside a polygon? | `Within`/`geoWithin` with matching geometry |
| 3 km radius in Spring? | `new Distance(3, Metrics.KILOMETERS)` |
| Plain entities vs with distance? | `List<T>` vs `GeoResults<T>`/`GeoResult<T>` |
| Can reactive return `GeoResults`? | No; use `Flux<GeoResult<T>>` where supported |
| Mean distance of `GeoResults`? | `getAverageDistance()` over the present result set |
| Is adding `@GeoSpatialIndexed` alone enough? | Must verify the actual index exists |
| Where does `$geoNear` stage go? | First stage of an aggregation pipeline |
| Java `geoNear` name = old MongoDB command? | No; modern Spring Data uses the `$geoNear` stage |
| Does a geospatial index secure tenants alone? | No; authorization + query tenant filter |
| Straight-line proximity = ETA? | No |

## 22. References

- Spring Data MongoDB — [MongoDB-specific Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): derived `Near`, `Within`, `Distance`/`Metric`, `GeoResults`, and reactive limitations.
- Spring Data MongoDB — [Querying Documents — GeoSpatial and GeoNear](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): `Criteria`, `NearQuery`, `MongoTemplate.geoNear`, and GeoJSON/legacy differences.
- Spring Data MongoDB API — [NearQuery](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/NearQuery.html): `near`, `query`, `minDistance`/`maxDistance`, `in`, `limit`, `with(Pageable)`.
- Spring Data Commons — [GeoResults](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/geo/GeoResults.html): `getContent`, `getAverageDistance`.
- Spring Data Commons — [GeoPage](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/geo/GeoPage.html): page metadata and average distance.
- Spring Data MongoDB — [Repository Query Return Types](https://docs.spring.io/spring-data/mongodb/reference/repositories/query-return-types-reference.html): geo result/page wrappers by store support.
- MongoDB Manual — [`$near`](https://www.mongodb.com/docs/manual/reference/operator/query/near/): index requirement, nearest-to-farthest order, coordinate order, and distance units.
- MongoDB Manual — [`$geoNear` aggregation stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/geonear/): first stage rule, distance metadata, and query restrictions.
- MongoDB Manual — [Geospatial Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/): `2d`, `2dsphere`, and index considerations.
- MongoDB Manual — [`$geoWithin`](https://www.mongodb.com/docs/manual/reference/operator/query/geoWithin/): region geometry, distinct from nearest-distance sorting.

## Key Takeaways

**`Point` defines the search center (longitude before latitude), `Distance` defines the radius and metric, and `GeoResult<T>`/`GeoResults<T>` carry results along with distances—three separate roles.** With imperative Spring Data MongoDB, a derived `Near` query can return entities or `GeoResults<T>` depending on the declared return type; with reactive repositories, use `Flux<T>` or `Flux<GeoResult<T>>` and **never** use `Mono<GeoResults<T>>`/`GeoPage<T>` as derived return wrappers. For queries to behave accurately, GeoJSON data must have a `2dsphere` index, coordinates must preserve order, `Distance` must carry an explicit `Metric`, and tenant/active filters must execute in MongoDB. When limits or filters grow complex, switch to `NearQuery`/`MongoTemplate.geoNear` and test on real MongoDB to verify BSON, indexes, radius, ordering, and distances.
