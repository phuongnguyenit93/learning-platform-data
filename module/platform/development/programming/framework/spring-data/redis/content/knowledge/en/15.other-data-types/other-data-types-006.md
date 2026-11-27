# Finding Nearby Points by API and Redis Server Capabilities

A store, delivery, or location-aware service often needs a **"find points near my current coordinates"** feature: the user submits longitude/latitude, and the application finds stores within a few kilometers, optionally sorted nearest-first and capped to a result limit.

**Spring Data Redis** provides `GeoOperations` to work with Redis geospatial data. However, the presence of a method in the Java library does not guarantee every **Redis Server** understands the underlying command. Redis 3.2 introduced `GEOADD` and legacy radius queries; only in Redis **6.2** did `GEOSEARCH` and `GEOSEARCHSTORE` arrive with unified syntax for circles and bounding boxes.

This lesson focuses on three areas: using the Spring Data Redis API, Redis Server version constraints, and accurately answering "nearest points" without confusing straight-line distance, arbitrary ordering, or extra business filters.

> **Technical scope:** Java examples target Spring Boot 3.3.x / Spring Data Redis 3.3.x using Lettuce via `spring-boot-starter-data-redis`. `GEOSEARCH` examples assume Redis Server **6.2+**. Coordinates for `store:1`, `store:2` in this lesson are test fixtures, not real stores.

## 1. How Does Redis Store GEO Data?

Redis does not report a data type named `geo` from `TYPE`. Geographic data is encoded into a **Sorted Set (ZSET)**. Each ZSET member is an ID, while its score holds a Redis-encoded geographic position.

~~~text
demo:shops (Redis type = zset)
  member store:1 → position 106.7000, 10.7760
  member store:2 → position 106.7050, 10.7780
  member store:3 → position 106.7250, 10.7950
~~~

To store coordinates in the right format, use `GEOADD` rather than assigning arbitrary scores via `ZADD`.

~~~redis
GEOADD demo:shops 106.7000 10.7760 store:1
GEOADD demo:shops 106.7050 10.7780 store:2
GEOADD demo:shops 106.7250 10.7950 store:3
TYPE demo:shops
ZCARD demo:shops
~~~

`TYPE` returns `zset` and `ZCARD` returns the number of members in the index. Redis can ingest multiple members in a single `GEOADD`:

~~~redis
GEOADD demo:shops 106.7000 10.7760 store:1 106.7050 10.7780 store:2
~~~

Writing coordinates for an existing member updates that member's position instead of creating a duplicate. **The return value of `GEOADD` is normally the count of newly added members**, so `0` does not mean a location update failed.

### 1.1. What Does a GEO Index Store?

~~~mermaid
flowchart LR
    A["GEOADD key longitude latitude member"] --> B["Redis ZSET"]
    B --> C["member ID"]
    B --> D["coordinate-encoded score"]
    C --> E["GEOSEARCH"]
    D --> E
    E --> F["IDs near query center"]
~~~

Redis GEO is well-suited for:

- Filtering points within a **radius** around coordinates.
- Filtering points inside a **bounding box** around coordinates on supported Redis Servers.
- Measuring distances between stored members.
- Reading coordinates of a member.
- Fetching nearest members sorted by distance with a result limit.

It does **not** automatically solve route planning, driving times, live traffic, complex polygon containment, "currently open stores", or SQL-style multi-criteria queries.

## 2. Coordinate Order: Longitude First, Latitude Second

A very common source of bugs is reversing coordinate order.

Redis uses:

~~~text
longitude latitude
east-west north-south
~~~

Example:

~~~redis
GEOADD demo:shops 106.7000 10.7760 store:1
~~~

In Spring Data Redis:

~~~java
import org.springframework.data.geo.Point;

Point location = new Point(106.7000, 10.7760);
~~~

`Point.getX()` corresponds to **longitude**, and `Point.getY()` is **latitude**. Some map SDKs represent coordinates as `[latitude, longitude]`; never pass that order verbatim into `new Point(x, y)`.

### 2.1. Valid Ranges

| Component | Redis GEO range | Notes |
|---|---|---|
| Longitude | `-180` to `180` | East–West |
| Latitude | Roughly `-85.05112878` to `85.05112878` | Not the full `-90` to `90` |
| Radius | Positive number and valid unit | Maximum cap should be enforced by the application |
| Units | `m`, `km`, `ft`, `mi` | Must stay consistent when displaying |

Redis GEO supports a narrower latitude range than theoretical latitude. When accepting coordinates from an API, validate finiteness, range bounds, and axis order **before writing to Redis or querying**.

### 2.2. What Distance Does Redis Calculate?

Redis GEO returns an approximate geographic distance, commonly understood as **as-the-crow-flies** distance between two locations on Earth's surface. It does not measure actual travel distance across bridges, one-way streets, traffic, or terrain.

Therefore:

- `1.5 km` from Redis does not guarantee driving only takes 1.5 km.
- Redis has no awareness of travel speed or congestion.
- If ETA, delivery time, or turn-by-turn routes are required, use a separate routing service.

Coordinates are also encoded with finite precision, so `GEOPOS` may return numbers slightly different from the input coordinates.

## 3. Redis Server Capabilities by Version

Consult this table before picking Spring Data Redis methods:

| Redis command | Available since Redis OSS | Purpose |
|---|---|---|
| `GEOADD` | 3.2 | Add/update member and coordinates |
| `GEOPOS` | 3.2 | Retrieve member coordinates |
| `GEODIST` | 3.2 | Distance between two members |
| `GEOHASH` | 3.2 | Retrieve geohash string of member |
| `GEORADIUS` | 3.2 | Radius search from coordinates, legacy |
| `GEORADIUSBYMEMBER` | 3.2 | Radius search from member, legacy |
| `GEOSEARCH` | **6.2** | Search by circle or box, from coordinates or member |
| `GEOSEARCHSTORE` | **6.2** | Search and store results into a destination |

Since Redis 6.2, `GEORADIUS` and `GEORADIUSBYMEMBER` have been marked **deprecated**. They do not immediately vanish from newer Redis releases, yet `GEOSEARCH` and `GEOSEARCHSTORE` are the recommended commands for new code.

### 3.1. Checking Actual Version and Commands

Example against a local Redis instance you are permitted to inspect:

~~~bash
redis-cli -h localhost -p 6379 INFO server
redis-cli -h localhost -p 6379 COMMAND INFO GEOSEARCH
redis-cli -h localhost -p 6379 COMMAND INFO GEOSEARCHSTORE
~~~

The `redis_version` line reports the server version. `COMMAND INFO` verifies whether the command is recognized by the server; on servers lacking the command, the reply may be nil or empty depending on version.

An application using **Spring Data Redis 3.3** can still connect to **Redis 5.x**. Calling `GEOSEARCH` directly there triggers an error like `ERR unknown command 'GEOSEARCH'`.

### 3.2. All Three Layers Must Align

~~~mermaid
flowchart TD
    A["App calls GeoOperations.search"] --> B{"Spring Data Redis library has search()?"}
    B -->|No| C["Use compatible API or upgrade library"]
    B -->|Yes| D{"Driver/connection supports command mapping?"}
    D -->|No| E["Switch to compatible implementation"]
    D -->|Yes| F{"Redis Server supports GEOSEARCH >= 6.2?"}
    F -->|No| G["Use legacy radius() path when sufficient"]
    F -->|Yes| H["Execute GEOSEARCH"]
~~~

**Java API availability ≠ command support on the server.** Do not assume Spring Data Redis automatically falls back from `GEOSEARCH` to `GEORADIUS` when the server rejects the command. Supporting older servers requires an explicit compatibility strategy.

## 4. Using Spring Data Redis to Store and Manage Locations

Common starter in Spring Boot projects:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

With `StringRedisTemplate`:

~~~java
import org.springframework.data.geo.Point;
import org.springframework.data.redis.core.GeoOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ShopLocationStore {

    private static final String KEY = "demo:shops";

    private final GeoOperations<String, String> geo;

    public ShopLocationStore(StringRedisTemplate template) {
        this.geo = template.opsForGeo();
    }

    public void save(String shopId, double lon, double lat) {
        validate(lon, lat);
        geo.add(KEY, new Point(lon, lat), shopId);
    }

    public void delete(String shopId) {
        geo.remove(KEY, shopId);
    }

    private void validate(double lon, double lat) {
        if (!Double.isFinite(lon) || !Double.isFinite(lat)
                || lon < -180 || lon > 180
                || lat < -85.05112878 || lat > 85.05112878) {
            throw new IllegalArgumentException("Invalid GEO coordinate");
        }
    }
}
~~~

Saving entries:

~~~java
store.save("store:1", 106.7000, 10.7760);
store.save("store:2", 106.7050, 10.7780);
store.save("store:3", 106.7250, 10.7950);
~~~

`GeoOperations<String, String>` has two generic parameters:

- `K = String`: outer Redis key, e.g. `demo:shops`.
- `M = String`: member ID in the GEO index, e.g. `store:1`.

Do not serialize the entire store object as the member when only the ID is needed. Store store profiles in a Hash/JSON or primary database, while keeping only IDs and positions in the GEO index.

### 4.1. Writing Multiple Coordinates in One Call

~~~java
import java.util.Map;
import org.springframework.data.geo.Point;

Map<String, Point> coordinates = Map.of(
        "store:1", new Point(106.7000, 10.7760),
        "store:2", new Point(106.7050, 10.7780),
        "store:3", new Point(106.7250, 10.7950)
);

Long added = geo.add("demo:shops", coordinates);
~~~

The `added` value reflects newly added members according to command semantics, not necessarily the total number of updated members. Inside pipelines/transactions, some Spring Data Redis methods return `null` before responses are collected.

### 4.2. Reading Coordinates and Distance

~~~java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;

Distance distanceKm = geo.distance(
        "demo:shops",
        "store:1",
        "store:2",
        Metrics.KILOMETERS
);

java.util.List<Point> positions = geo.position(
        "demo:shops",
        "store:1",
        "store:2"
);
~~~

`GEODIST` requires **two members already stored in the same GEO index**. If either member does not exist, distance may be `null`. `position()` can return `null` elements for missing members; preserve response ordering when mapping back to IDs.

## 5. Radius Search with Redis `GEOSEARCH`

From Redis 6.2+, querying from coordinates:

~~~redis
GEOSEARCH demo:shops FROMLONLAT 106.7000 10.7760 BYRADIUS 2 km
~~~

This requests all indexed members located inside a circle centered at `(106.7000, 10.7760)` with a 2 km radius.

A command with sorting and details:

~~~redis
GEOSEARCH demo:shops FROMLONLAT 106.7000 10.7760 BYRADIUS 2 km ASC COUNT 10 WITHDIST WITHCOORD
~~~

Clause meanings:

| Clause | Meaning |
|---|---|
| `FROMLONLAT lon lat` | Use coordinates as search center |
| `FROMMEMBER id` | Use an existing member as search center |
| `BYRADIUS 2 km` | Search area of 2 km radius |
| `BYBOX 4 3 km` | Rectangular area 4 km wide by 3 km tall |
| `ASC` | Sort nearest to farthest |
| `DESC` | Sort farthest to nearest |
| `COUNT 10` | At most 10 results |
| `WITHDIST` | Include distance from center in query unit |
| `WITHCOORD` | Include longitude/latitude of each member |
| `WITHHASH` | Include geohash score of each member |

If no sort option is specified, **never assume results are ordered nearest-first**. If `WITHDIST` is omitted, never assume responses include distances.

### 5.1. Difference Between `COUNT` and `COUNT ... ANY`

~~~redis
GEOSEARCH demo:shops FROMLONLAT 106.7000 10.7760 BYRADIUS 2 km ASC COUNT 10
~~~

This is the appropriate command when the goal is the **10 nearest points in the area** using Redis's search/sort capabilities.

The option:

~~~redis
GEOSEARCH demo:shops FROMLONLAT 106.7000 10.7760 BYRADIUS 2 km COUNT 10 ANY
~~~

lets Redis stop searching as soon as enough candidates are found. This can reduce search work across huge areas, yet **does not guarantee the absolute 10 closest points across the entire region**. Even if combining `ASC` with `ANY`, understand that the candidate set may stop early.

| Need | Option |
|---|---|
| "10 nearest points" | `ASC COUNT 10`, without `ANY` |
| "Up to 10 arbitrary points in the area" | Can use `COUNT 10 ANY` |
| "All points in the area" | Omit COUNT, though load must be bounded/measured |
| "10 farthest points in the area" | `DESC COUNT 10` |

`COUNT 10` is a **maximum cap**, not a guarantee that the area contains 10 members.

## 6. Searching Around a Stored Member

When the center is an indexed member, use `FROMMEMBER`:

~~~redis
GEOSEARCH demo:shops FROMMEMBER store:1 BYRADIUS 1 km ASC WITHDIST
~~~

Redis looks up `store:1`'s stored coordinates. This is helpful for "other points near store X" queries when the caller does not have the store's coordinates locally.

Points to keep in mind:

- `store:1` must exist in the index.
- The center member itself can appear in results with a distance near 0.
- If you want only **other** stores, filter out the center member per business rules.
- If 10 other stores are requested, requesting `COUNT 10` may leave only 9 after dropping the center; fetch an extra candidate and cap in Java.

Example:

~~~redis
GEOSEARCH demo:shops FROMMEMBER store:1 BYRADIUS 2 km ASC COUNT 11 WITHDIST
~~~

Then filter out `store:1` and keep at most 10 other members. Do not assume Redis has a built-in "exclude center" default option.

## 7. Spring Data Redis `GeoOperations.search()`

Spring Data Redis 3.3 offers `GeoOperations.search()` overloads for `GEOSEARCH`:

- `search(key, GeoReference, Distance)`: searches within a circle around the specified center.
- `search(key, GeoReference, Distance, GeoSearchCommandArgs)`: adds sort, limit, distance, and coordinates.
- `search(key, GeoReference, BoundingBox)`: searches within a bounding box.
- `search(key, GeoReference, BoundingBox, GeoSearchCommandArgs)`: searches within a bounding box with options.

Commonly used classes:

| Class | Package | Role |
|---|---|---|
| `GeoOperations` | `org.springframework.data.redis.core` | Redis GEO API |
| `GeoReference` | `org.springframework.data.redis.domain.geo` | Specify center from member or coordinates |
| `Point` | `org.springframework.data.geo` | Longitude/latitude |
| `Distance` | `org.springframework.data.geo` | Distance value and unit |
| `Metrics` | `org.springframework.data.geo` | Meters/kilometers... |
| `BoundingBox` | `org.springframework.data.geo` | Width/height of rectangular region |
| `GeoResults` / `GeoResult` | `org.springframework.data.geo` | Result collection and individual hit |
| `GeoLocation` | `RedisGeoCommands.GeoLocation` | Member name and position |
| `GeoSearchCommandArgs` | `RedisGeoCommands.GeoSearchCommandArgs` | Sort, limit, WITHDIST/WITHCOORD |

### 7.1. Example: Finding Nearest by Coordinates

~~~java
import java.util.List;
import java.util.Objects;

import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;
import org.springframework.data.redis.connection.RedisGeoCommands.GeoLocation;
import org.springframework.data.redis.connection.RedisGeoCommands.GeoSearchCommandArgs;
import org.springframework.data.redis.core.GeoOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.domain.geo.GeoReference;
import org.springframework.stereotype.Service;

@Service
public class NearbyShopService {

    private static final String KEY = "demo:shops";
    private final GeoOperations<String, String> geo;

    public NearbyShopService(StringRedisTemplate redis) {
        this.geo = redis.opsForGeo();
    }

    public record NearbyShop(
            String id,
            double distanceKm,
            Point position
    ) {}

    public List<NearbyShop> findNearest(
            double longitude,
            double latitude,
            double radiusKm,
            int maxResults
    ) {
        if (!Double.isFinite(longitude)
                || !Double.isFinite(latitude)
                || longitude < -180 || longitude > 180
                || latitude < -85.05112878
                || latitude > 85.05112878) {
            throw new IllegalArgumentException("Invalid coordinate");
        }

        // Illustrative application bounds, not Redis limits.
        if (!Double.isFinite(radiusKm)
                || radiusKm <= 0 || radiusKm > 20
                || maxResults < 1 || maxResults > 50) {
            throw new IllegalArgumentException(
                    "Invalid radius/limit"
            );
        }

        GeoSearchCommandArgs args =
                GeoSearchCommandArgs.newGeoSearchArgs()
                        .includeDistance()
                        .includeCoordinates()
                        .sortAscending()
                        .limit(maxResults);

        GeoResults<GeoLocation<String>> result = geo.search(
                KEY,
                GeoReference.fromCoordinate(
                        longitude,
                        latitude
                ),
                new Distance(
                        radiusKm,
                        Metrics.KILOMETERS
                ),
                args
        );

        if (result == null) {
            // May lack response if queued in pipeline/transaction;
            // this example assumes direct synchronous calls.
            throw new IllegalStateException(
                    "Expected direct GEO result"
            );
        }

        return result.getContent().stream()
                .map(item -> new NearbyShop(
                        item.getContent().getName(),
                        Objects.requireNonNull(
                                item.getDistance()
                        ).getValue(),
                        item.getContent().getPoint()
                ))
                .toList();
    }
}
~~~

Step-by-step explanation:

1. `GeoReference.fromCoordinate(longitude, latitude)` sets the center from coordinates.
2. `Distance(radiusKm, Metrics.KILOMETERS)` prevents unit mix-ups.
3. `sortAscending()` requests nearest results first.
4. `limit(maxResults)` caps the response, without enabling `ANY`.
5. `includeDistance()` requests distance in each `GeoResult`.
6. `includeCoordinates()` requests member coordinates in `GeoLocation`.
7. The `NearbyShop` DTO holds application data instead of leaking framework objects throughout business code.

The 20 km and 50-result bounds in the example are **application rules to control resource usage**, not hard Redis limits. Choose thresholds based on data density and product needs.

### 7.2. Simple Query Without Extra Arguments

~~~java
GeoResults<GeoLocation<String>> results = geo.search(
        "demo:shops",
        GeoReference.fromCoordinate(106.7000, 10.7760),
        new Distance(2, Metrics.KILOMETERS)
);
~~~

This is concise when you only need members in the region. If you need top-N nearest or explicit distances, do not guess default sorting/response fields; pass `GeoSearchCommandArgs`.

### 7.3. Querying from a Member in Spring Data Redis

~~~java
GeoResults<GeoLocation<String>> aroundStore = geo.search(
        "demo:shops",
        GeoReference.fromMember("store:1"),
        new Distance(1, Metrics.KILOMETERS),
        GeoSearchCommandArgs.newGeoSearchArgs()
                .includeDistance()
                .sortAscending()
                .limit(10)
);
~~~

This mirrors `FROMMEMBER store:1 BYRADIUS 1 km`. If `store:1` is missing, handle it as a nonexistent center rather than falling back to an assumed default coordinate.

## 8. Searching Within a Rectangle: `BYBOX`

Redis 6.2+ supports:

~~~redis
GEOSEARCH demo:shops FROMLONLAT 106.7000 10.7760 BYBOX 4 3 km ASC WITHCOORD
~~~

`BYBOX 4 3 km` specifies a **rectangle 4 km wide and 3 km tall**, not a circle of radius 4 km.

In Java:

~~~java
import org.springframework.data.geo.BoundingBox;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.redis.connection.RedisGeoCommands.GeoLocation;
import org.springframework.data.redis.domain.geo.GeoReference;

BoundingBox viewport = new BoundingBox(
        new Distance(4, Metrics.KILOMETERS),
        new Distance(3, Metrics.KILOMETERS)
);

GeoResults<GeoLocation<String>> points = geo.search(
        "demo:shops",
        GeoReference.fromCoordinate(106.7000, 10.7760),
        viewport
);
~~~

Use `BYBOX` when you need a rectangular area around a center, such as an approximate map viewport. Use `BYRADIUS` when the requirement is actually "points no more than N km away".

Core Redis GEO **does not support point-in-arbitrary-polygon queries** or regions with holes/concavities common in GIS. For complex polygons, use GEO to retrieve bounding candidates and apply exact geometric filtering in the application, or use a dedicated geospatial search engine.

## 9. Legacy `radius()` API for Servers Before Redis 6.2

When compatibility with Redis 3.2 through 6.0 is needed, circular queries can use `GeoOperations.radius()`:

~~~java
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;
import org.springframework.data.redis.connection.RedisGeoCommands.GeoLocation;

Circle area = new Circle(
        new Point(106.7000, 10.7760),
        new Distance(2, Metrics.KILOMETERS)
);

GeoResults<GeoLocation<String>> legacy = geo.radius(
        "demo:shops",
        area
);
~~~

At the Redis level, legacy commands include:

~~~redis
GEORADIUS demo:shops 106.7000 10.7760 2 km ASC WITHDIST
GEORADIUSBYMEMBER demo:shops store:1 2 km ASC WITHDIST
~~~

Redis 6.2 marked these commands deprecated in favor of `GEOSEARCH`/`GEOSEARCHSTORE`. Still, code supporting older servers can use the legacy path when the server and driver support it.

| Requirement | Redis Server 3.2–6.0 | Redis Server 6.2+ |
|---|---|---|
| Add location | `GEOADD` | `GEOADD` |
| Read location | `GEOPOS` | `GEOPOS` |
| Distance between 2 members | `GEODIST` | `GEODIST` |
| Coordinate radius search | `GEORADIUS` / `geo.radius()` | Prefer `GEOSEARCH` / `geo.search()` |
| Member radius search | `GEORADIUSBYMEMBER` | `GEOSEARCH FROMMEMBER` |
| Bounding box | No `GEOSEARCH BYBOX` | `GEOSEARCH BYBOX` |
| Search and store (modern) | No `GEOSEARCHSTORE` | `GEOSEARCHSTORE` |

Specifically, **do not assume `geo.search()` automatically falls back to `geo.radius()` on Redis 5**. If supporting multiple server versions, detect capabilities at startup and select the implementation rather than issuing failing commands on every request.

## 10. `GEOSEARCHSTORE`: Searching and Storing Results

`GEOSEARCH` returns members to the client, whereas `GEOSEARCHSTORE` writes matching results into a destination Sorted Set key.

~~~redis
GEOSEARCHSTORE demo:shops:nearby demo:shops FROMLONLAT 106.7000 10.7760 BYRADIUS 2 km ASC COUNT 10
~~~

Where:

- `demo:shops` is the source GEO index.
- `demo:shops:nearby` is the destination holding matching results.

By default, scores in the destination preserve geospatial coordinate encoding, so it can itself be used as a GEO index. If `STOREDIST` is added:

~~~redis
GEOSEARCHSTORE demo:shops:distances demo:shops FROMLONLAT 106.7000 10.7760 BYRADIUS 2 km ASC COUNT 10 STOREDIST
ZRANGE demo:shops:distances 0 -1 WITHSCORES
~~~

the destination stores the **distance from center as the score**. That makes it a distance-scored ZSET, no longer holding coordinate scores expected by GEO commands.

### 10.1. `GeoOperations.searchAndStore()`

~~~java
Long count = geo.searchAndStore(
        "demo:shops",
        "demo:shops:nearby",
        GeoReference.fromCoordinate(106.7000, 10.7760),
        new Distance(2, Metrics.KILOMETERS)
);
~~~

`count` is the number of stored members upon direct successful execution. Inside pipelines/transactions, operations may temporarily return `null` until responses arrive.

**Do not write all users' results to the same destination key** when requests vary by location. Sharing `demo:shops:nearby` allows one request to overwrite another's results. Temporary result caches require properly scoped key names, TTLs, and access control.

### 10.2. Limitations in Redis Cluster

`GEOSEARCH` reads a single GEO index key, so cluster-aware drivers can route it to that key's slot. However, `GEOSEARCHSTORE` touches both **source and destination**, triggering Redis Cluster multi-key rules.

Use hash tags when both keys must map to the same slot:

~~~redis
GEOADD shops:{hcm} 106.7000 10.7760 store:1
GEOSEARCHSTORE shops:{hcm}:nearby shops:{hcm} FROMLONLAT 106.7000 10.7760 BYRADIUS 2 km
~~~

Keys sharing the `{hcm}` tag map to the same hash slot. Never put every large geo index under one global tag; that creates a hot slot and defeats sharding.

## 11. Interpreting `GeoResults` Semantically

`GeoOperations.search()` typically returns:

~~~java
GeoResults<GeoLocation<String>>
~~~

Each element is a `GeoResult<GeoLocation<String>>`, with:

- `item.getContent().getName()`: member ID.
- `item.getContent().getPoint()`: member coordinates when requested/returned.
- `item.getDistance()`: distance from center when provided in the response.

When `WITHDIST` or `WITHCOORD` is omitted, those fields may be absent. Do not blindly unbox or dereference fields the command was not instructed to return.

### 11.1. Empty Results Do Not Imply an Error

If a search region contains no points, a successful query returns an **empty list**. Contrast that with:

- Redis Server does not recognize `GEOSEARCH`.
- Key holds the wrong data type.
- Coordinates or distance are invalid.
- Redis connection loss, timeout, or ACL rejection.
- Wrong member/key serializer.
- Calling inside a pipeline/transaction where the method returns `null` before responses arrive.

Never catch all exceptions and return an empty list; doing so hides deployment or data errors.

### 11.2. The Center Member May Appear in Results

A `FROMMEMBER store:1` query can return `store:1` itself. If the product wants "5 **other** stores near `store:1`", filter out that member and manage your limit carefully.

### 11.3. Distance Is Not Travel Time

GEO distance ignores traffic and real road networks. If the UI asks for travel duration, use an independent routing/ETA service. Never divide `distanceKm` by an arbitrary speed and present it as an accurate ETA.

## 12. GEO Alone Is Not Enough for Business Filters

A common requirement:

> "Find the 10 nearest stores within 3 km that are **currently open** and have stock."

GEOSEARCH searches by location. It does not automatically know `isOpen` or stock levels for each member. A simple flow:

~~~mermaid
flowchart TD
    A["User coordinates"] --> B["GEOSEARCH returns candidate IDs"]
    B --> C["Read profile/status/inventory"]
    C --> D["Filter by business rules"]
    D --> E["Return up to 10 results"]
~~~

However, notice:

~~~text
GEOSEARCH ASC COUNT 10 → 10 nearest points
Filter by "isOpen"     → 3 points remain
~~~

There may be more open stores within the radius that fell outside the first 10 candidates. Thus, capping to 10 points **before filtering** does not guarantee returning the "10 nearest points matching business rules".

Approaches depend on required accuracy:

1. **Over-fetch candidates**, filter, and keep up to 10 — fast in some cases, though still capable of missing matches.
2. **Maintain specialized GEO indexes** split by low-churn status/category, accepting index update costs.
3. **Use a search/geospatial query engine** capable of combining attribute filters and distance together.
4. **Materialized read models** updated from an authoritative source, if eventual consistency is acceptable.

No single plain GEO command evaluates arbitrary SQL or business predicates.

## 13. Performance, Limits, and Precision

`GEOSEARCH` uses a spatial index so Java doesn't have to scan every Redis key and compute distances itself. Still, cost scales with the search area and point count.

Redis documentation describes command complexity in terms of elements in the bounding area and matching results, not `O(1)` for arbitrary radii. Broad queries over extremely dense areas can burn CPU and return huge payloads.

| Issue | Consequence | Mitigation |
|---|---|---|
| Unbounded radius | Heavy query, huge response | Enforce business-level cap |
| Missing COUNT | Returns too many members | Enforce pagination/limit |
| Sorting `ASC` over huge area | Selection/sorting cost | Measure latency, bound search area |
| `COUNT n ANY` | Potentially faster, no nearest-N guarantee | Use only when acceptable |
| Very large single GEO key | Memory/CPU hotspot | Evaluate sharding/partitioning |
| Filtering after capping | Top-N after filter misses matches | Design proper filtering/indexing |
| Rapidly changing positions | Stale data, heavy writes | Tune update frequency |
| Logging exact coordinates | Privacy risk | Minimize logging and enforce retention |

Redis GEO uses finite-precision geohash encoding, so retrieved coordinates may not match input digits identically. It is not an arbitrary-precision GIS database or surveying tool.

### 13.1. Geographic Region Partitioning Has Trade-offs

You can use:

~~~text
shops:geo:region-a
shops:geo:region-b
~~~

instead of one global GEO index. This shrinks individual indexes and spreads load in some systems, yet points near region borders may live in the neighboring region's index.

When searching near a border, the application may need to query multiple regions, merge, and re-sort results. Otherwise, searches can miss the closest store right across the boundary.

Therefore, never treat administrative or partition boundaries as hard boundaries for radius searches.

## 14. Diagnostic Checklist When Points Are Missing

A quick cause-differentiation table:

| Symptom | Likely cause | What to check |
|---|---|---|
| `unknown command GEOSEARCH` | Redis Server older than 6.2 | `INFO server`, `COMMAND INFO` |
| GEOADD rejected | Wrong coordinate order/range | Longitude first, latitude second |
| Empty results despite existing data | Wrong key/DB/radius/coordinates | `TYPE`, `ZCARD`, `GEOPOS` |
| Not ordered nearest-first | Forgot `ASC` | `sortAscending()` or `ASC` |
| Distances missing | Did not request `WITHDIST` | `includeDistance()` |
| Fewer than `COUNT n` results | Fewer members in area, or extra filtering | COUNT is an upper bound only |
| Unexpected results with `ANY` | Early termination | Drop `ANY` when top-N nearest is required |
| GEOSEARCHSTORE fails with `CROSSSLOT` | Source and destination in different slots | Add hash tags / check slots |
| `WRONGTYPE` | Key is not a GEO-compatible ZSET | `TYPE key` |
| Stale results | Member not updated/removed | Audit location sync flow |
| Java `null` inside pipeline | Responses not yet collected | Read results after pipeline/transaction |

Run these commands in a test environment:

~~~bash
redis-cli -h localhost -p 6379 INFO server
redis-cli -h localhost -p 6379 TYPE demo:shops
redis-cli -h localhost -p 6379 ZCARD demo:shops
redis-cli -h localhost -p 6379 GEOPOS demo:shops store:1
redis-cli -h localhost -p 6379 GEOSEARCH demo:shops FROMLONLAT 106.7000 10.7760 BYRADIUS 2 km ASC WITHDIST
~~~

If the last command reports `unknown command`, widening the radius will not help: ensure a compatible server and command first.

In Redis Cluster, use a topology-aware client to route commands to the owning node. For commands storing results, ensure source and destination share a slot.

## 15. End-to-End Implementation Flow for "Places Near Me"

Requirement:

> Accept coordinates from a user and return up to 10 stores within a 3 km radius, sorted nearest-first. Store locations may change.

A practical workflow:

**Step 1 — Choose key/index.** Name the key `shops:active:geo` or a deliberately planned partitioned key. Members are stable store IDs.

**Step 2 — Sync data.** Call `GEOADD` when creating or moving locations, and `GeoOperations.remove()` when a store ceases to be searchable. Do not leave orphaned members indefinitely if the business requires only active places.

**Step 3 — Lock in capability config.** On Redis 6.2+, call `GeoOperations.search()`; if forced to support older servers, use the `radius()` path for circular queries with documented feature limits. Do not retry unsupported `GEOSEARCH` commands per request.

**Step 4 — Validate input.** Enforce valid longitude/latitude bounds, 3 km radius, max 10 results, and server-determined IDs/keys instead of trusting client-supplied keys.

**Step 5 — Query.** Use `GeoReference.fromCoordinate(lon, lat)`, `new Distance(3, Metrics.KILOMETERS)`, and `GeoSearchCommandArgs.sortAscending().limit(10)`. Include `includeDistance()` when the UI displays distance.

**Step 6 — Hydrate details.** Fetch profiles and status for returned IDs. If "currently open" is mandatory, adapt candidate limits so post-filter top-10 isn't truncated prematurely.

**Step 7 — Return stable DTOs.** Expose e.g. `id`, `name`, `distanceKm`, `location`; avoid leaking driver structures directly to the frontend.

**Step 8 — Monitor operations.** Track p95/p99 latency by radius, member counts, cache miss rates, location update rates, command errors, and out-of-bounds requests.

~~~mermaid
flowchart TD
    A["Request longitude/latitude"] --> B["Validate radius and limit"]
    B --> C{"Redis supports GEOSEARCH >= 6.2?"}
    C -->|Yes| D["GeoOperations.search()"]
    C -->|No, legacy available| E["GeoOperations.radius()"]
    C -->|No compatible path| F["Report unsupported capability"]
    D --> G["ID, distance, location"]
    E --> G
    G --> H["Fetch profiles, apply business filters"]
    H --> I["Return application DTO"]
~~~

## 16. Misconceptions to Avoid

**"Having `GeoOperations.search()` means Redis 5 can run it."** No. `GEOSEARCH` requires Redis Server 6.2+.

**"Deprecated `GEORADIUS` means it never works."** No; it may remain for backward compatibility, though Redis 6.2+ recommends `GEOSEARCH`.

**"Redis GEO is a separate Redis type."** No. Data is stored as a ZSET with geospatial scores.

**"`Point(x, y)` is latitude, longitude."** Here `x` is longitude and `y` is latitude.

**"`ASC COUNT 10 ANY` always returns the 10 nearest points."** `ANY` permits early termination, so it does not guarantee global top-N across the region like a query without ANY.

**"`BYBOX 4 3 km` is a circle."** It is a rectangle 4 km wide by 3 km tall.

**"GEO distance is driving kilometers."** No; it is approximate straight-line geographic distance.

**"`GEOSEARCHSTORE` isn't affected by Cluster multi-key rules."** It uses both source and destination, requiring proper slot alignment.

**"Fetching 10 points via GEO then filtering always gives the 10 closest matching points."** Not necessarily; capping candidates before filtering can drop valid matches.

**"A GEO index expires individual members automatically."** Standard TTL applies to the whole Redis key; individual members need explicit update/removal lifecycles.

## 17. Key Takeaways

- **Redis 3.2+**: `GEOADD`, `GEODIST`, `GEOPOS`, and legacy radius queries.
- **Redis 6.2+**: `GEOSEARCH` by **BYRADIUS** or **BYBOX**, centered on coordinates or a member; `GEOSEARCHSTORE` stores results.
- **Spring Data Redis 3.3**: `GeoOperations.search()`, `GeoReference`, `Distance`, `BoundingBox`, and `GeoSearchCommandArgs`.
- **Java API and Redis Server capabilities differ**: verify which commands exist on the actual endpoint.
- **Longitude before latitude**, explicit radius units, and validated inputs are mandatory.
- **`ASC COUNT n`** is the clear choice for top-N nearest; `ANY` trades completeness for speed.
- **GEO is a spatial candidate index**, not a routing engine, arbitrary polygon matcher, or SQL attribute filter.
- **Redis Cluster**: single-key GEO queries route directly; storing results with `GEOSEARCHSTORE` requires source and destination in the same slot.
- **Operations require bounds and lifecycle management**: radius, limits, partitioning, updates, removals, and sensitive location data controls.

Finding nearby points effectively takes more than calling `geo.search()`. You must verify **server command support**, design how coordinates are stored and updated, interpret distances accurately, and ensure query results satisfy downstream business rules.

## References

- [Spring Data Redis 3.3.7 API — GeoOperations](https://docs.spring.io/spring-data/redis/docs/3.3.7/api/org/springframework/data/redis/core/GeoOperations.html)
- [Spring Data Redis 3.3.7 API — GeoSearchCommandArgs](https://docs.spring.io/spring-data/redis/docs/3.3.7/api/org/springframework/data/redis/connection/RedisGeoCommands.GeoSearchCommandArgs.html)
- [Spring Data Redis 3.3.7 API — GeoReference](https://docs.spring.io/spring-data/redis/docs/3.3.7/api/org/springframework/data/redis/domain/geo/GeoReference.html)
- [Spring Data Redis — GEO](https://docs.spring.io/spring-data/redis/reference/redis/geo.html)
- [Redis — GEOADD](https://redis.io/docs/latest/commands/geoadd/)
- [Redis — GEOSEARCH](https://redis.io/docs/latest/commands/geosearch/)
- [Redis — GEOSEARCHSTORE](https://redis.io/docs/latest/commands/geosearchstore/)
- [Redis — GEORADIUS](https://redis.io/docs/latest/commands/georadius/)
- [Redis — GEOPOS](https://redis.io/docs/latest/commands/geopos/)
- [Redis — GEODIST](https://redis.io/docs/latest/commands/geodist/)
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
