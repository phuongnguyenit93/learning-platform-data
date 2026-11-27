# Geospatial: Recording Coordinates and Calculating Distances in Spring Data Redis

When an application needs to find stores near a customer, check the distance between two delivery points, display branches within a few kilometers, or filter devices by location, merely storing longitude/latitude inside JSON is inconvenient for querying. Redis provides the **Geospatial (GEO)** command group to store locations by identifier, look up coordinates, compute distances, and search points within an area. Spring Data Redis provides **`GeoOperations<K, M>`** to work with these commands via `RedisTemplate`.

This lesson focuses on two core operations: **recording coordinates with `GEOADD` / `GeoOperations.add(...)`** and **calculating distances with `GEODIST` / `GeoOperations.distance(...)`**. To apply them effectively, you also need to understand longitude–latitude ordering, precision, nonexistent members, radius queries, how Redis actually stores GEO data, TTL, location updates, and Redis Cluster limitations.

## 1. Practical Problem: Finding Distances Between Branches

Suppose a retail system has three branches, each with an ID and geographic location. The illustrative data below uses hypothetical coordinates in the Ho Chi Minh City area to explain the API and does not represent real addresses of any actual stores.

| Branch ID | Longitude | Latitude |
|---|---:|---:|
| `branch-01` | 106.7010 | 10.7760 |
| `branch-02` | 106.7080 | 10.7810 |
| `branch-03` | 106.6950 | 10.7740 |

If you only have Redis keys:

```text
shop:dev:branch:branch-01 -> {"longitude":106.7010,"latitude":10.7760}
shop:dev:branch:branch-02 -> {"longitude":106.7080,"latitude":10.7810}
shop:dev:branch:branch-03 -> {"longitude":106.6950,"latitude":10.7740}
```

the application can read the JSON and implement a distance formula itself. However, to find **all branches within a 2 km radius**, it would have to scan many records, decode coordinates, and filter results manually.

Redis GEO lets you maintain one shared key:

```text
shop:dev:branches:geo
    member branch-01 -> (longitude=106.7010, latitude=10.7760)
    member branch-02 -> (longitude=106.7080, latitude=10.7810)
    member branch-03 -> (longitude=106.6950, latitude=10.7740)
```

From there, you can ask Redis to compute the distance between `branch-01` and `branch-02`, or find branches around any coordinate without loading the entire coordinate set into the JVM.

## 2. Which Structure Does Redis Actually Use for GEO?

Redis GEO is **not a standalone Redis data type** like List or Hash. Redis stores GEO points inside a **Sorted Set (ZSET)**:

- **Redis key** is the name of the geospatial dataset, e.g. `shop:dev:branches:geo`.
- **Member** is the location identifier, e.g. `branch-01`.
- **Score** encodes the position using the internal geohash representation Redis uses for lookups.
- Redis provides `GEOADD`, `GEOPOS`, `GEODIST`, `GEOSEARCH`, `GEOHASH`, etc. to operate on this representation.

Example:

```redis
GEOADD shop:dev:branches:geo 106.7010 10.7760 branch-01
TYPE shop:dev:branches:geo
```

The `TYPE` command returns:

```text
zset
```

You can use `ZCARD` to count members in a GEO key and `ZREM` to remove a member. However, do not arbitrarily use `ZADD` with business scores on a GEO key: GEO scores follow coordinate-encoding rules, not ordinary ranking scores.

### One GEO Key Holds Many Locations

```text
                         Redis key
                shop:dev:branches:geo
                           |
                  Redis Sorted Set
                           |
     +---------------------+---------------------+
     |                     |                     |
  branch-01             branch-02             branch-03
  (lon, lat)            (lon, lat)            (lon, lat)
```

This differs from creating a separate key per location. `GEODIST` computes the distance between **two members in the same GEO key**. If two members live in two different keys, you cannot simply pass both member names to `GEODIST` and expect Redis to look up and compute the distance across keys.

## 3. Coordinate System and Argument Order: Longitude First, Latitude Second

Redis GEO uses geographic coordinates in longitude and latitude. A critical rule:

> **Redis `GEOADD` takes `longitude latitude member`, not `latitude longitude member`.**

- **Longitude**: East–West position, in the range `[-180, 180]` degrees.
- **Latitude**: North–South position; Redis GEO uses an approximate range of `[-85.05112878, 85.05112878]` degrees to match its geospatial representation.
- Both are expressed as decimal **degrees**, not radians.
- In Spring Data Redis, `Point(x, y)` maps **`x = longitude`** and **`y = latitude`**.

Correct example:

```redis
GEOADD shop:dev:branches:geo 106.7010 10.7760 branch-01
```

Correct Java example:

```java
Point point = new Point(106.7010, 10.7760);
```

Common mistake:

```java
// Wrong: passing latitude into x and longitude into y.
Point wrong = new Point(10.7760, 106.7010);
```

In this example, Redis will reject it because latitude `106.7010` is out of the supported range. Yet in locations where both numbers happen to fall inside valid bounds, swapping longitude/latitude can go unnoticed at write time and yield completely wrong search results.

### Why Doesn't Redis Support Latitude Up to 90°?

Redis GEO builds its spatial index on a coordinate representation compatible with a latitude-bounded Mercator projection. Consequently, Redis GEO latitudes do not cover the extreme polar regions. For store maps, delivery, or typical user locations, this limit is rarely an issue; specialized polar geography requires a different solution.

## 4. Essential Redis GEO Commands

| Redis command | Function | Key point |
|---|---|---|
| `GEOADD key longitude latitude member` | Store or update member coordinates | Longitude before latitude |
| `GEOPOS key member...` | Retrieve coordinates of one or more members | Nonexistent members return nil |
| `GEODIST key member1 member2 [unit]` | Compute distance between two members in the same key | Defaults to meters; supports `m`, `km`, `mi`, `ft` |
| `GEOHASH key member...` | Retrieve geohash string representing coordinates | Not meant for exact calculation of arbitrary distances |
| `GEOSEARCH key ...` | Search members within a radius or bounding box | Redis 6.2+; supports distance, coordinates, sorting |
| `ZREM key member...` | Remove members from a GEO key | GEO uses a Sorted Set |
| `ZCARD key` | Count total members in a GEO key | Counts locations, not detail records in other keys |

Older commands like `GEORADIUS` and `GEORADIUSBYMEMBER` may still appear in existing systems or library APIs. Redis recommends `GEOSEARCH`/`GEOSEARCHSTORE` for corresponding searches on supported versions. When using Spring Data Redis, distinguish the framework API from the actual server/driver command executed.

## 5. Recording Coordinates with `GEOADD`

Basic syntax:

```redis
GEOADD key longitude latitude member
```

Example adding three branches in one command:

```redis
GEOADD shop:dev:branches:geo \
  106.7010 10.7760 branch-01 \
  106.7080 10.7810 branch-02 \
  106.6950 10.7740 branch-03
```

In interactive Redis CLI or when running directly from a terminal, you can write it on one line:

```bash
redis-cli GEOADD shop:dev:branches:geo 106.7010 10.7760 branch-01 106.7080 10.7810 branch-02 106.6950 10.7740 branch-03
```

`GEOADD` normally returns the **number of newly added members**, not the total number of stored locations. If all three IDs did not exist previously, the return value is `3`.

### 5.1. Updating the Location of an Existing Member

Suppose `branch-01` moves to a new location:

```redis
GEOADD shop:dev:branches:geo 106.7020 10.7770 branch-01
```

Redis updates the coordinates of `branch-01`. With standard `GEOADD` syntax, the return value may be `0` because **no new member was added**, even though the coordinates updated successfully.

This is a very common misinterpretation:

- Returning `1` when adding a new member does not mean the command created a new Redis key.
- Returning `0` when upserting an existing member **does not mean the write failed**.
- `ZCARD` reflects the total member count after updates.
- When you need the count of elements whose coordinates changed, Redis provides the `CH` option on supported command forms; do not assume `GeoOperations.add` returns "number of changed coordinates".

### 5.2. Member IDs Must Be Stable

If the same branch `branch-01` is written as `branch-1` or `Branch-01`, Redis treats them as distinct members. Changing ID formatting without removing old members can cause the same branch to appear twice in results.

Use stable internal IDs, not user phone numbers or street addresses as members. Sensitive identifiers can end up in logs, Redis CLI, metrics, and backups.

## 6. Retrieving Coordinates with `GEOPOS`

Syntax:

```redis
GEOPOS key member [member ...]
```

Example:

```redis
GEOPOS shop:dev:branches:geo branch-01 branch-02 branch-missing
```

Redis returns coordinates in the order of requested members. If `branch-missing` is not in the GEO key, its corresponding slot is nil.

Conceptual result:

```text
branch-01 -> [106.701..., 10.776...]
branch-02 -> [106.708..., 10.781...]
branch-missing -> nil
```

Returned decimal digits may **not match the written numbers verbatim**. Redis stores a quantized geospatial representation at the index's resolution; do not rely on `GEOPOS` as a store for raw coordinates with arbitrary precision.

If the application needs to preserve exact GPS-reported latitude/longitude along with metadata (accuracy, update timestamp, data source), store an authoritative record separately and use GEO as a **spatial query index**.

## 7. Calculating Distance with `GEODIST`

Syntax:

```redis
GEODIST key member1 member2 [m|km|ft|mi]
```

Example:

```redis
GEODIST shop:dev:branches:geo branch-01 branch-02
```

When no unit is provided, Redis returns **meters (m)**. To request kilometers:

```redis
GEODIST shop:dev:branches:geo branch-01 branch-02 km
```

Redis also supports `mi` (miles) and `ft` (feet) as supported by the command. Do not pass arbitrary unit strings like `kilometer` to Redis CLI when the command only accepts defined unit codes.

### 7.1. Both Members Must Reside in the Same Key

Suppose the system creates two GEO keys:

```text
shop:dev:branches:geo         -> branch-01
shop:dev:warehouses:geo       -> warehouse-01
```

You cannot run:

```redis
GEODIST shop:dev:branches:geo branch-01 warehouse-01 km
```

to compute the distance if `warehouse-01` only exists in `shop:dev:warehouses:geo`. Redis will not find the second member in the specified key and thus returns no distance.

You can solve this by placing both members into a shared GEO index if semantics allow, or reading both coordinates and computing distance with a geospatial library in the application. The choice depends on ownership, lifecycle, and query patterns.

### 7.2. When One or Both Members Do Not Exist

`GEODIST` returns nil if the distance cannot be determined because a member is absent from the key. In Spring Data Redis, the returned `Distance` object may be `null`.

Therefore, distinguish clearly:

- Distance `0`: two locations coincide or evaluate to zero at current resolution.
- No result: one or both members do not exist; **never** silently turn this into 0 km.
- Connection/timeout/serializer errors: handle as exceptions or distinct conditions rather than masking them with a fake distance value.

### 7.3. Is Redis Distance the Same as Travel Distance?

**No.** `GEODIST` computes an approximate geographic distance between two points on Earth's surface based on Redis's calculation model. It does **not** account for road networks, bridges, rivers, walking time, driving time, or traffic congestion.

For instance, two spots 1 km apart in a straight line might require a 3 km drive by road. When a product needs "actual driving distance" or "ETA", use a dedicated map routing service after using GEO to pre-filter candidates.

## 8. Integrating with Spring Boot and `GeoOperations`

Example using Spring Boot 3.x, Java 17+, and the Spring Data Redis starter:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Standalone Redis configuration for development:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      database: 0
      connect-timeout: 2s
      timeout: 3s
```

When auto-configuration applies, Spring Boot provides `RedisConnectionFactory` and `StringRedisTemplate`. `StringRedisTemplate` fits well when both **GEO keys and member IDs** are strings.

Obtain `GeoOperations` from the template:

```java
import org.springframework.data.redis.core.GeoOperations;
import org.springframework.data.redis.core.StringRedisTemplate;

GeoOperations<String, String> geo = redis.opsForGeo();
```

Type `K` is the **Redis key** type; type `M` is the **member** type stored in the GEO Set. In this example, both are `String`.

There is no need to open a new connection for every coordinate write. The template bean uses the Spring-managed `RedisConnectionFactory` and handles serialization and Redis connection lifecycles.

## 9. Java: Recording Coordinates with `GeoOperations.add(...)`

`GeoOperations` supports adding a location by member:

```java
Long added = geo.add(
        "shop:dev:branches:geo",
        new Point(106.7010, 10.7760),
        "branch-01"
);
```

Required import:

```java
import org.springframework.data.geo.Point;
```

Notes:

- `new Point(x, y)` takes `x=longitude`, `y=latitude`.
- `added` is typically the number of **new** members added during the write.
- If the member already exists, its coordinates can be updated while `added == 0`.
- Inside a pipeline or transaction, the immediate return value of some Spring Data Redis APIs can be `null` because results are deferred; do not equate `null` with a business error.

Adding multiple points via separate calls:

```java
geo.add(KEY, new Point(106.7010, 10.7760), "branch-01");
geo.add(KEY, new Point(106.7080, 10.7810), "branch-02");
geo.add(KEY, new Point(106.6950, 10.7740), "branch-03");
```

Or using the overload accepting a member → point map:

```java
Map<String, Point> points = Map.of(
        "branch-01", new Point(106.7010, 10.7760),
        "branch-02", new Point(106.7080, 10.7810),
        "branch-03", new Point(106.6950, 10.7740)
);

Long addedCount = geo.add(KEY, points);
```

With a map, map keys are member IDs and values are `Point`s. This is useful for preloading multiple locations when the application has the full dataset ready. Do not build an unbounded map of millions of entries in the JVM; batch appropriately for memory, latency, and system write policies.

## 10. Java: Retrieving Coordinates with `position(...)`

Reading stored locations:

```java
List<Point> points = geo.position(
        "shop:dev:branches:geo",
        "branch-01",
        "branch-02"
);
```

`position` corresponds to `GEOPOS` and returns a list of positions matching the order of input members. For nonexistent members, the corresponding list element may be `null`.

Handling a single member:

```java
public Optional<Point> findPosition(String memberId) {
    List<Point> positions = geo.position(GEO_KEY, memberId);

    if (positions == null || positions.isEmpty()) {
        return Optional.empty();
    }

    return Optional.ofNullable(positions.get(0));
}
```

`Point.getX()` is longitude; `Point.getY()` is latitude. Because Redis quantizes coordinates internally, do not use exact `double == double` comparisons expecting read-back digits to match the initial input identically.

## 11. Java: Calculating Distance with `distance(...)`

Spring Data Redis uses `org.springframework.data.geo.Distance` and `org.springframework.data.geo.Metrics`.

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;

Distance meters = geo.distance(
        GEO_KEY,
        "branch-01",
        "branch-02"
);

Distance kilometers = geo.distance(
        GEO_KEY,
        "branch-01",
        "branch-02",
        Metrics.KILOMETERS
);
```

Available overloads:

- `distance(key, member1, member2)`: measures distance in Redis's default unit (typically meters).
- `distance(key, member1, member2, metric)`: requests a unit such as `Metrics.KILOMETERS`.

Extracting the value:

```java
if (kilometers == null) {
    // One or both members do not exist.
} else {
    double distanceKm = kilometers.getValue();
    System.out.println("Distance: " + distanceKm + " km");
}
```

Do not print the returned number as km if you called the default overload returning meters. Variable names and displayed units must match the `Metric` passed.

### Designing a Distance-Returning API

If a member does not exist, a service can return `OptionalDouble.empty()`:

```java
public OptionalDouble distanceKm(String fromId, String toId) {
    Distance d = geo.distance(
            GEO_KEY, fromId, toId, Metrics.KILOMETERS);

    return d == null
            ? OptionalDouble.empty()
            : OptionalDouble.of(d.getValue());
}
```

This avoids returning `0.0` when Redis has no data. Still, distinguish "coordinates absent" from Redis timeout errors; infrastructure failures must be surfaced via proper exception handling and observability.

## 12. Self-Contained Spring Service Example: Storing Branches and Measuring Distance

A simple location DTO:

```java
package com.example.shop.geo;

public record BranchLocation(
        String id,
        double longitude,
        double latitude
) {}
```

Service:

```java
package com.example.shop.geo;

import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.OptionalDouble;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;
import org.springframework.data.redis.core.GeoOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class BranchGeoStore {

    private static final String GEO_KEY = "shop:dev:branches:geo";
    private static final double MAX_GEO_LATITUDE = 85.05112878;

    private final GeoOperations<String, String> geo;

    public BranchGeoStore(StringRedisTemplate template) {
        this.geo = template.opsForGeo();
    }

    public Long upsert(BranchLocation location) {
        Objects.requireNonNull(location, "location");
        validateId(location.id());
        validateCoordinates(location.longitude(), location.latitude());

        return geo.add(
                GEO_KEY,
                new Point(location.longitude(), location.latitude()),
                location.id()
        );
    }

    public Optional<Point> position(String id) {
        validateId(id);

        List<Point> result = geo.position(GEO_KEY, id);
        if (result == null || result.isEmpty()) {
            return Optional.empty();
        }

        return Optional.ofNullable(result.get(0));
    }

    public OptionalDouble distanceKm(String firstId, String secondId) {
        validateId(firstId);
        validateId(secondId);

        Distance distance = geo.distance(
                GEO_KEY,
                firstId,
                secondId,
                Metrics.KILOMETERS
        );

        return distance == null
                ? OptionalDouble.empty()
                : OptionalDouble.of(distance.getValue());
    }

    public Long remove(String id) {
        validateId(id);
        return geo.remove(GEO_KEY, id);
    }

    private static void validateId(String id) {
        Objects.requireNonNull(id, "branch id");
        if (!id.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid branch id");
        }
    }

    private static void validateCoordinates(double longitude, double latitude) {
        if (!Double.isFinite(longitude) ||
                !Double.isFinite(latitude) ||
                longitude < -180.0 ||
                longitude > 180.0 ||
                latitude < -MAX_GEO_LATITUDE ||
                latitude > MAX_GEO_LATITUDE) {
            throw new IllegalArgumentException(
                    "Coordinates outside Redis GEO range");
        }
    }
}
```

Usage:

```java
store.upsert(new BranchLocation(
        "branch-01", 106.7010, 10.7760));

store.upsert(new BranchLocation(
        "branch-02", 106.7080, 10.7810));

Optional<Point> first = store.position("branch-01");

OptionalDouble km = store.distanceKm(
        "branch-01", "branch-02");
```

This is a synchronous service example where each method issues one basic Redis command. The return value of `upsert` is the count of newly added members, **not a version** of the location and not the total count of stored points.

In production systems, the `shop:dev` namespace should come from deployment configuration so environments never mix. In multi-tenant services, control both tenant ID sourcing and index isolation policy rather than letting clients supply arbitrary GEO keys.

## 13. Searching for Locations Within a Radius

Recording coordinates and computing the distance between two known members is the first step. A more common requirement is:

> "From the user's current coordinates, which branches lie within 3 km?"

Redis supports distance searches centered on either **a coordinate** or **a stored member**.

Redis 6.2+ example:

```redis
GEOSEARCH shop:dev:branches:geo \
  FROMLONLAT 106.7009 10.7769 \
  BYRADIUS 3 km \
  WITHDIST WITHCOORD ASC COUNT 10
```

If running in a shell that does not support multiline line continuations like above, use a single line:

```bash
redis-cli GEOSEARCH shop:dev:branches:geo FROMLONLAT 106.7009 10.7769 BYRADIUS 3 km WITHDIST WITHCOORD ASC COUNT 10
```

Meaning of each clause:

| Clause | Role |
|---|---|
| `FROMLONLAT 106.7009 10.7769` | Center point is a coordinate, not necessarily stored |
| `BYRADIUS 3 km` | Search within a 3 km radius |
| `WITHDIST` | Also return distance from center to each member |
| `WITHCOORD` | Also return coordinates of each member |
| `ASC` | Sort from nearest to farthest |
| `COUNT 10` | Limit number of returned results |

In location-search APIs, request sorting explicitly when displaying "nearest first". Without a sort option, never assume Redis returns results in ascending distance order.

### Searching Around a Stored Member

To find branches near `branch-01`:

```redis
GEOSEARCH shop:dev:branches:geo \
  FROMMEMBER branch-01 \
  BYRADIUS 2 km \
  WITHDIST ASC COUNT 10
```

By search semantics, `branch-01` itself can appear in the results with distance 0 since it lies inside the radius. If the requirement is "**other** branches near `branch-01`", the application must exclude the origin member when constructing the result list.

### Searching Within a Bounding Box

Besides `BYRADIUS`, Redis GEO also supports `BYBOX width height unit`:

```redis
GEOSEARCH shop:dev:branches:geo \
  FROMLONLAT 106.7009 10.7769 \
  BYBOX 4 2 km \
  WITHDIST ASC
```

For a bounding box, parameters represent width and height in the specified unit. Circles and rectangles are two search-area shapes; they are not synonymous with administrative boundaries, road corridors, or arbitrary polygons.

## 14. Radius Search in Spring Data Redis

`GeoOperations` supports `radius(...)` using these types:

- `Point`: center coordinates.
- `Distance`: radius and unit.
- `Circle`: combines center and radius.
- `GeoResults<GeoLocation<M>>`: list of geospatial results.
- `GeoRadiusCommandArgs`: options to return distance, coordinates, sorting, and limit.

Example:

```java
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;
import org.springframework.data.redis.connection.RedisGeoCommands;
import org.springframework.data.redis.connection.RedisGeoCommands.GeoLocation;
import org.springframework.data.redis.core.GeoOperations;

Point center = new Point(106.7009, 10.7769);
Distance radius = new Distance(3.0, Metrics.KILOMETERS);
Circle area = new Circle(center, radius);

RedisGeoCommands.GeoRadiusCommandArgs args =
        RedisGeoCommands.GeoRadiusCommandArgs
            .newGeoRadiusArgs()
            .includeDistance()
            .includeCoordinates()
            .sortAscending()
            .limit(10);

GeoResults<GeoLocation<String>> results =
        geo.radius("shop:dev:branches:geo", area, args);
```

Reading the results:

```java
if (results != null) {
    for (GeoResult<GeoLocation<String>> hit : results) {
        String memberId = hit.getContent().getName();
        Point point = hit.getContent().getPoint();
        Distance distance = hit.getDistance();

        System.out.println(
                "ID=" + memberId +
                ", point=" + point +
                ", distance=" +
                (distance == null ? "n/a" : distance.getValue()));
    }
}
```

When `includeDistance()` is requested, Spring Data Redis can populate distance in `GeoResult.getDistance()`. When omitted, results may not carry distance; check for `null` if application logic reads that field.

The `radius(...)` call above illustrates a stable `GeoOperations` API in Spring Data Redis. Newer versions of Spring Data Redis also provide `search(...)` built on Redis `GEOSEARCH`; choose the exact API/command based on your Redis server, Spring Data Redis, and driver versions. When newer capabilities like bounding-box queries are needed, `GEOSEARCH` is the appropriate direction on Redis 6.2+.

### Differences Between Radius Search and `distance(...)`

- `distance(key, a, b)` computes the distance between **two stored members** in the same GEO key.
- `radius(key, circle, args)` finds **members around an arbitrary point**, without requiring the center to be a stored member.
- `radius(key, member, radius, args)` via the appropriate overload searches around a **stored member**.
- `position(key, members...)` only retrieves coordinates, without computing distances.

When you have a user's current GPS coordinates that are not stored in Redis, do not create a temporary member for the user just to find nearby branches; querying with **center coordinates** is far better.

## 15. Sorting Results by Distance and Limiting Result Count

A service showing "10 nearest branches within 5 km" enforces two separate constraints:

1. **Filter region:** maximum radius of 5 km.
2. **Order and count:** sort nearest to farthest, return at most 10 results.

With Redis CLI:

```redis
GEOSEARCH shop:dev:branches:geo \
  FROMLONLAT 106.7009 10.7769 \
  BYRADIUS 5 km ASC COUNT 10 WITHDIST
```

In Spring Data Redis, `sortAscending()` and `limit(10)` express the corresponding options on `GeoRadiusCommandArgs`.

Some GEOSEARCH variants support `COUNT count ANY`. The `ANY` option lets Redis stop early once enough matches are found in certain situations, reducing cost, yet **should not be used when the contract requires the guaranteed 10 closest points**. If the product requires strict nearest-first ordering, apply `ASC` and avoid early-stop optimizations that do not guarantee nearest-N.

Filters like opening hours, store active status, or stock levels do not automatically live inside the GEO index. Redis GEO returns candidates by **location**; join business data afterward:

```text
GEOSEARCH (5 km radius)
          |
          v
    List of member IDs
          |
          v
  Read branch status / opening hours / stock
          |
          v
   Filter by business rules
          |
          v
   Return locations to user
```

If you fetch `COUNT 10` first and only then filter for "currently open", you may end up with fewer than 10 results even though other valid open branches exist inside the radius. In that case, you need a strategy to expand candidate counts or use an appropriate query planner rather than assuming the first 10 GEO hits satisfy all business filters.

## 16. A Complete API: Finding Branches Near a User Point

Extending the previous service with a result record:

```java
package com.example.shop.geo;

public record NearbyBranch(
        String branchId,
        Double distanceKm
) {}
```

Add the method to `BranchGeoStore`:

```java
import java.util.List;
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;
import org.springframework.data.redis.connection.RedisGeoCommands;
import org.springframework.data.redis.connection.RedisGeoCommands.GeoLocation;

public List<NearbyBranch> findNearby(
        double longitude,
        double latitude,
        double radiusKm,
        int limit) {

    validateCoordinates(longitude, latitude);
    if (!Double.isFinite(radiusKm) || radiusKm <= 0.0) {
        throw new IllegalArgumentException("Invalid radius");
    }
    if (limit <= 0 || limit > 100) {
        throw new IllegalArgumentException("Invalid result limit");
    }

    var args = RedisGeoCommands.GeoRadiusCommandArgs
            .newGeoRadiusArgs()
            .includeDistance()
            .sortAscending()
            .limit(limit);

    var area = new Circle(
            new Point(longitude, latitude),
            new Distance(radiusKm, Metrics.KILOMETERS)
    );

    GeoResults<GeoLocation<String>> hits =
            geo.radius(GEO_KEY, area, args);

    if (hits == null) {
        return List.of();
    }

    return hits.getContent().stream()
            .map(hit -> new NearbyBranch(
                    hit.getContent().getName(),
                    hit.getDistance() == null
                            ? null
                            : hit.getDistance().getValue()
            ))
            .toList();
}
```

Invoke:

```java
List<NearbyBranch> branches =
        store.findNearby(106.7009, 10.7769, 3.0, 10);
```

The record uses `Double` instead of `double` for distance so it can represent "distance absent" if the driver/framework omits it; here `includeDistance()` was requested, so it is normally populated. When exposing an HTTP API, decide whether the distance field is required or optional and how `null` values serialize.

### Why Must Radius and Limit Inputs Be Bounded?

Location query APIs can be abused with requests for "every point in a massive radius" or thousands of requests per second. Bounding `radiusKm`, `limit`, and applying rate limits helps control CPU, network, and response size. The `limit <= 100` check in the example is a demo policy, not a Redis-enforced limit.

If your system holds millions of points, benchmark with realistic data to pick sensible radius/candidate limits. Using GEO does not automatically make every spatial query cheap.

## 17. Removing or Moving Members

### 17.1. Removing a Member from a GEO Key

Because GEO data resides in a Redis Sorted Set, Redis uses `ZREM` to remove entries:

```redis
ZREM shop:dev:branches:geo branch-03
```

In Spring Data Redis:

```java
Long removed = geo.remove(GEO_KEY, "branch-03");
```

The return value reflects how many members were actually removed. If the member does not exist, it is normally `0`. Do not delete the entire GEO key just to drop one point.

### 17.2. Updating Location with the Same ID

When a branch relocates, call `GEOADD` or `geo.add(...)` with the **same member ID** and new coordinates. Do not create `branch-01-new` and forget to remove `branch-01` if it is merely one relocated branch, or queries will show two points for one store.

### 17.3. Detail Data and the GEO Index Can Drift

Systems often store:

```text
shop:dev:branches:geo
  -> GEO index containing branch coordinates

shop:dev:branches:details:branch-01
  -> name, address, status, opening hours, version
```

If updating Redis GEO succeeds but writing details fails, index coordinates and detail records drift. Conversely, deleting details while forgetting `geo.remove` leaves stale IDs in search results.

When tight consistency is needed, design a unified update path managing both—using a Lua script/transaction on the same Redis server, or event processing and reconciliation if the source of truth lives in another system.

## 18. TTL and GEO Data Lifecycle

Redis GEO uses a Sorted Set key, so TTL applies to **the entire GEO key**, not individual members.

For example:

```redis
EXPIRE shop:dev:branches:geo 600
```

After roughly 600 seconds, the entire `shop:dev:branches:geo` dataset expires—not just locations older than 10 minutes.

This is usually **unsuitable** when the key holds a stable catalog of system branches expected to remain long-term. A single branch closing or being deleted should be handled by updating/removing that member and metadata rather than expiring the entire index under a global TTL rule.

### Does Updating a Member Reset the TTL?

`GEOADD` mutates the existing Sorted Set and generally **does not clear the key's TTL**. Once the Redis key expires or is deleted completely, a subsequent `GEOADD` creates a new key that does not inherit the old TTL.

For **continuously moving coordinates**, such as driver locations:

```text
shop:prod:drivers:geo
  driver-101 -> location written 2 seconds ago
  driver-102 -> location written 25 minutes ago
```

You cannot simply set `EXPIRE shop:prod:drivers:geo 60` and expect Redis to evict `driver-102` after 60 seconds while keeping `driver-101`. Key-level TTL deletes **both** upon expiration.

One design pattern is maintaining a separate heartbeat timestamp per driver, then purging stale drivers from the GEO index via a worker or applying a post-query freshness filter. At scale, evaluate data modeling, time filters, backpressure, and bounded stale-entry cleanup.

## 19. GEO Does Not Replace an Authoritative Location Store

Redis stores GEO coordinates in a search-optimized representation with **finite resolution**. When calling `GEOPOS`, returned coordinates can differ slightly from the initial input due to quantization.

Business needs may also require retaining:

- Raw coordinates exactly as reported by the device.
- Update timestamp.
- GPS accuracy radius.
- Altitude or building floor.
- Reporting user/device.
- Verification status and privacy rules.

Redis GEO does not automatically store this metadata. Store it in a Hash/JSON/primary store, and use GEO as a **secondary index** to locate candidate IDs near a coordinate.

Example:

```text
shop:prod:drivers:geo
    driver-101 -> (lon, lat) for search

shop:prod:drivers:state:driver-101
    -> {longitude, latitude, updatedAt, accuracyMeters, status}
```

When a client queries nearby drivers, Redis returns candidate driver IDs; the application can inspect `updatedAt` and `status` to avoid serving stale locations.

If you require extreme precision, surveying/cadastral math, 3D distances, or road-network routing, pick a dedicated geospatial library or GIS engine rather than assuming GEO covers every calculation.

## 20. Redis Cluster and GEO Key Design

### 20.1. One GEO Key Belongs to One Hash Slot

In Redis Cluster, a key maps to one hash slot and one primary node at any moment. Because `GEOADD`, `GEODIST`, `GEOPOS`, and `GEOSEARCH` each operate on **a single GEO key**, Cluster-aware clients can route them directly to the node owning that key.

Example:

```text
shop:prod:geo:branches:hcm
shop:prod:geo:branches:hn
shop:prod:geo:branches:dn
```

These three GEO keys may reside in different slots. Querying one key searches only members **within that key**.

There is no simple native `GEOSEARCH` command that merges all three GEO keys to return "top 10 nearest nationwide" in a single cross-slot query. Applications may need to query relevant regional keys, merge results, and re-sort by distance.

### 20.2. One Nationwide GEO Key vs. Multiple Regional Keys?

**One shared GEO key:**

```text
shop:prod:geo:branches:all
```

Advantage: all members sit in one key, simplifying `GEODIST` between any two branches and single-region queries. Drawback: a single large hot key is still handled by one primary node in the Cluster, potentially limiting throughput and memory for massive workloads.

**Multiple regional GEO keys:**

```text
shop:prod:geo:branches:region-a
shop:prod:geo:branches:region-b
```

Keys can spread across slots, yet querying **near regional borders** becomes complex: a coordinate in region-a can be close to a branch in region-b. Searching only region-a will miss valid stores just across the border.

You must design logic to detect regions intersecting the search radius, query multiple indexes, and deduplicate IDs. No single option fits all systems; balance point count, update frequency, latency, topology, and query requirements.

### 20.3. Hash Tags Do Not Distribute One Key

Redis Cluster uses `{...}` hash tags to pin multiple keys into the same slot, but a single GEO key already keeps all its members in one slot. Putting `{branches}` inside one key does not spread it across nodes.

If a transaction must atomically update both a GEO key and a metadata key in Cluster, all involved keys must obey the same-slot rule. Hash tags allow intentional co-location, though overly broad tags concentrate load onto one slot.

## 21. Consistency When Updating Locations

Suppose a service receives sequential location updates for a driver:

```text
t1: driver-101 -> (106.7000, 10.7700)
t2: driver-101 -> (106.7010, 10.7710)
```

The same member ID is updated twice via `GEOADD`. Redis keeps whichever coordinates were **executed last**, having no awareness of device timestamps. If event t1 arrives late after t2 due to networking/retries, stale coordinates overwrite newer ones.

To prevent this, track a trusted timestamp/version alongside the location and enforce "accept only newer events". If version checking and GEO updating must happen atomically, use an appropriate atomic construct (such as a script on the same slot/server with input and error handling) rather than two uncoordinated Redis commands.

Similarly:

```text
1. GEOADD updates location
2. HSET updates updatedAt
```

If the application crashes between the two steps, the GEO index and timestamp disagree. When strong consistency is required, encapsulate both updates in a unified atomic mechanism; for eventual-consistency tracking, use messaging/outbox patterns and stale-data reconciliation workers.

### Idempotency of `GEOADD`

Calling `GEOADD` repeatedly with the **same member and same coordinates** leaves the final state unchanged. This is convenient when retrying location updates. Yet if two different events arrive out of order, replaying an older event still moves the position backward; idempotency does not replace version/time-ordering checks.

## 22. GEO Query Performance: What to Measure

Redis uses an internal spatial index to avoid scanning every coordinate in application code. Still, you should not assume every `GEOSEARCH` runs in constant time as point counts grow.

Factors affecting performance:

- **Member count in the GEO key:** large indexes consume substantial RAM, especially if metadata lives in separate keys.
- **Point density:** a 2 km radius in a dense city can return huge candidate sets.
- **Search radius:** wider areas typically inspect more candidates.
- **`WITHDIST`/`WITHCOORD`:** adds payload to responses, impacting bandwidth and result parsing.
- **`ASC`/`DESC` and `COUNT`:** sorting, capping, and optimization options change execution cost.
- **`GEOADD` frequency:** continuous GPS pings can generate heavy write load.
- **Redis Cluster:** one hot GEO key is bounded by the primary owning its slot.
- **Post-GEO metadata lookups:** finding 50 nearby stores and then fetching 50 detail records adds round trips.

Measure Redis latency, response size, candidate counts, and Java deserialization/processing time. Batch metadata fetches by ID when the storage model allows, mindful of Cluster multi-key limits. Do not swap an N-coordinate scan for an N+1 Redis metadata request problem without measuring.

### Geographic Distance Alone Is Not Enough for Ranking

"Nearest by `GEODIST`" means nearest by estimated straight-line distance. A point closer as the crow flies can be farther along real delivery roads. Many applications use a two-stage pipeline:

```text
Redis GEO
    |
    | quickly filter 20–50 nearest straight-line candidates
    v
Routing / business rules
    |
    | compute road distance, travel time, status
    v
Final ranked results
```

The candidate pool size depends on load and accuracy goals; there is no universal threshold for every domain.

## 23. Security and Privacy of Location Data

Coordinates can be sensitive data, especially when tied to a user, driver, or device. Even though Redis stores GEO inside a Sorted Set, it is **not an encryption mechanism**. Any client with access to the key and relevant commands can read member positions.

Practical safeguards:

- Use internal member IDs rather than emails, phone numbers, or tokens.
- Restrict `GEOADD` write access and `GEOPOS`/`GEOSEARCH` read access according to business permissions.
- Enable Redis credentials/ACLs and TLS where environments require.
- Never return all drivers/customers within a radius if the caller lacks authorization to view them.
- Limit exposed coordinate precision to what the feature requires; often an approximate zone suffices.
- Define retention windows, deletion mechanisms when data is no longer needed, and compliant logging/backup policies.
- Never dump real user coordinates, movement histories, or exact positions into uncontrolled debug logs.

Namespaces like `shop:prod:drivers:geo` help organize keys, but **do not create a security boundary** if the same credentials hold broad permissions.

## 24. Common Pitfalls and How to Investigate

| Symptom | Possible cause | What to check |
|---|---|---|
| `GEOADD` rejects coordinates | Swapped lon/lat, latitude beyond Redis limits, NaN/Infinity | Check `longitude latitude` order and bounds |
| `geo.add` returns `0` | Member already existed and had coordinates updated | Do not treat 0 as failure; check `GEOPOS` if verifying |
| `geo.distance` returns `null` | One or both members missing from the same GEO key | Check key, IDs, and `GEOPOS` |
| Displayed distance is 1,000x too large | Confused meters with kilometers | Specify `Metrics.KILOMETERS` or convert consistently |
| Position is off by kilometers | Swapped longitude/latitude or wrong coordinate system/input | Compare raw inputs and verify `Point(x,y)` order |
| `GEOPOS` coordinates differ in trailing digits | Redis quantizes GEO coordinates | Do not use GEO as raw coordinate storage when exact precision is needed |
| `TYPE key` returns `zset` instead of `geo` | Expected Redis GEO design | Use GEO commands; avoid arbitrary `ZADD` scores |
| `GEOSEARCH` misses a member despite metadata existing | GEO index was not updated or key/member mismatch | Check `ZCARD`, `GEOPOS`, namespace, TTL |
| Deleted store still appears | Forgot `geo.remove` when deleting metadata | Clean up index and add reconciliation |
| Overly broad query returns huge result set | Large radius, high density, missing result limit | Enforce input bounds and measure query cost |
| `CROSSSLOT` error when updating multiple keys together | GEO key and metadata/index keys sit in different slots | Design co-location or eventual consistency |
| Older GPS overwrites newer GPS | Out-of-order events with no version check | Store timestamp/version and validate before upserting |

Inspection commands in permitted environments:

```bash
redis-cli TYPE shop:dev:branches:geo
redis-cli ZCARD shop:dev:branches:geo
redis-cli GEOPOS shop:dev:branches:geo branch-01
redis-cli GEODIST shop:dev:branches:geo branch-01 branch-02 km
redis-cli TTL shop:dev:branches:geo
```

Avoid running `KEYS *` to inspect a specific GEO key. Never copy real user location data into unauthorized environments or share logs containing sensitive coordinates.

## 25. End-to-End Redis CLI Practice

This section uses the test key `demo:lesson158:geo`. Run only on a Redis instance permitted for practice.

### Step 1 — Record Three Locations

```bash
redis-cli GEOADD demo:lesson158:geo 106.7010 10.7760 branch-01 106.7080 10.7810 branch-02 106.6950 10.7740 branch-03
```

Check data type and member count:

```bash
redis-cli TYPE demo:lesson158:geo
# zset

redis-cli ZCARD demo:lesson158:geo
# 3
```

### Step 2 — Read Coordinates

```bash
redis-cli GEOPOS demo:lesson158:geo branch-01 branch-02
```

Observe that Redis returns **longitude first, latitude second**. Returned coordinates may differ slightly from the input due to GEO index resolution.

### Step 3 — Calculate Distance

```bash
redis-cli GEODIST demo:lesson158:geo branch-01 branch-02 m
redis-cli GEODIST demo:lesson158:geo branch-01 branch-02 km
redis-cli GEODIST demo:lesson158:geo branch-01 branch-02 mi
```

These outputs represent the same physical distance converted to different units. There is no need to implement the Haversine formula yourself just to measure distance between two members in a Redis GEO key.

### Step 4 — Search Within a Radius

```bash
redis-cli GEOSEARCH demo:lesson158:geo FROMLONLAT 106.7009 10.7769 BYRADIUS 3 km ASC COUNT 10 WITHDIST WITHCOORD
```

Inspect the returned IDs, distances, and coordinates. With sample data, results depend on the chosen point and radius; do not infer actual road distance from these numbers.

### Step 5 — Update a Location

```bash
redis-cli GEOADD demo:lesson158:geo 106.7020 10.7770 branch-01
redis-cli GEOPOS demo:lesson158:geo branch-01
redis-cli ZCARD demo:lesson158:geo
```

Even though `GEOADD` returns `0` because `branch-01` already existed, the updated position is saved and the total member count stays unchanged.

### Step 6 — Remove a Member and Check Missing Case

```bash
redis-cli ZREM demo:lesson158:geo branch-03
redis-cli GEOPOS demo:lesson158:geo branch-03
redis-cli GEODIST demo:lesson158:geo branch-01 branch-03 km
```

`GEOPOS`/`GEODIST` for a removed member yields nil; that indicates missing data, not a distance of 0.

### Step 7 — Observe TTL

```bash
redis-cli TTL demo:lesson158:geo
# Usually -1 because the key exists with no expiry set.
```

For static branch catalogs, short key-wide TTLs are normally unnecessary. To experiment with TTL:

```bash
redis-cli EXPIRE demo:lesson158:geo 60
redis-cli TTL demo:lesson158:geo
```

The entire GEO key expires when TTL reaches zero; it does not evict individual members by when they were added.

## 26. Self-Check Questions

**1. Does Redis `GEOADD` require longitude or latitude first?**

Longitude first, latitude second: `GEOADD key longitude latitude member`. In Spring Data Redis, `new Point(longitude, latitude)`.

**2. Does `TYPE` on a Redis GEO key return `geo` or `zset`?**

`zset`. Redis stores geospatial members in a Sorted Set with coordinate-encoded scores.

**3. Why can `GEOADD` return 0 even though the position changed?**

Because by default it counts **new** members. Re-writing an existing member with updated coordinates succeeds without increasing member count.

**4. Can `GEODIST` measure between two members in two different GEO keys?**

Not in a single native `GEODIST` command. Both members must belong to the same key passed to the command, or the application must fetch coordinates and compute distance separately.

**5. When `distance(...)` returns `null`, should you display 0 km?**

No. `null` indicates one or both members are missing; 0 km is a valid distance when two locations coincide.

**6. Is Redis GEO distance the same as driving route distance?**

No. Redis returns geographic distance under its spatial model, ignoring roads, bridges, traffic, or travel speed.

**7. To find places within 3 km of a customer's coordinates without storing the customer as a member, what should you use?**

Use `GEOSEARCH ... FROMLONLAT ... BYRADIUS 3 km`, or `GeoOperations.radius` with `Circle(Point, Distance)`; do not create a temporary member for the customer.

**8. Does TTL apply independently to each GEO member?**

Not via standard Redis TTL. TTL applies to the entire GEO key (Sorted Set); separate logic is required to detect and purge stale members.

**9. When tracking live GPS updates, why do you need a timestamp/version?**

Because out-of-order updates can let stale coordinates overwrite newer ones. `GEOADD` does not inspect device timestamps or automatically reject older events.

**10. Why can a massive GEO key become a hotspot in Redis Cluster?**

One Redis key maps to a single hash slot and one primary node at a time. Splitting data into multiple keys spreads load, though it complicates cross-region and border-area queries.

## 27. Conclusion

Redis Geospatial makes it convenient to store coordinates and query distances by member. In Spring Data Redis, **`GeoOperations.add(...)`** writes/updates locations via `GEOADD`, **`position(...)`** reads coordinates via `GEOPOS`, and **`distance(...)`** measures distance via `GEODIST` in a clearly specified unit. Radius queries can use `GEOSEARCH` on modern Redis or Spring Data Redis's `GeoOperations.radius(...)` API.

When designing, pay close attention to **longitude before latitude**, consistent meter/kilometer units, keeping compared members in the same key for `GEODIST`, and remembering that Redis stores GEO inside a Sorted Set rather than a separate data type. GEO distance is not road travel distance; read-back coordinates have finite precision; and TTL applies to the entire key rather than individual points. Ultimately, a GEO index is reliable only when the application properly manages member updates, detail records, timestamps, access controls, and Redis Cluster partitioning.
