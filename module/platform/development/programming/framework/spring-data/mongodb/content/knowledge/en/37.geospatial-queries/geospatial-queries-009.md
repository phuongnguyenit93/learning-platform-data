# Counting Limitations, Transactions, and Reactive Variants

## 1. Why Do Geospatial Queries Need a Different Way to Count?

A booking application uses **SPRING_DATA_MONGODB** to find stores around a coordinate: returning the 20 nearest locations while also displaying "137 stores within a 2 km radius". A developer uses Spring Data MongoDB via **MongoTemplate** or a repository and writes:

~~~java
Query nearby = Query.query(
    Criteria.where("location")
        .near(new GeoJsonPoint(106.7009, 10.7769))
        .maxDistance(2_000)
);

List<StoreDocument> results =
    mongoTemplate.find(nearby, StoreDocument.class);

long total = mongoTemplate.count(
    nearby, StoreDocument.class);
~~~

The **find** and **count** parts may not execute the same query shape on MongoDB Server. **`$near`/`$nearSphere`** operators are built for finding and sorting results by distance, whereas **`countDocuments`** uses aggregation-based counting and disallows placing those two operators directly inside the count filter.

Spring Data MongoDB includes logic to rewrite certain geospatial queries for counting, yet that mechanism must be understood properly:

- **Counting matches is not the same as sorting by distance.**
- **`$near`/`$nearSphere` cannot be turned into `$geoWithin` without considering semantics.**
- **`$minDistance`** usually requires an extra exclusion condition for the inner circle.
- **Total count and returned list may not come from the same snapshot** if executed as two independent commands.
- **Transactions** must be evaluated separately for sessions, supported operators, and overhead.
- **Reactive** supports geospatial queries, yet returns Publishers and does not provide every aggregate wrapper available in the blocking API.

This lesson, **Counting Limitations, Transactions, and Reactive Variants**, belongs to the **Geospatial Queries** chapter of the **SPRING_DATA_MONGODB** module. The module focuses on connecting and mapping documents, operating on MongoDB via MongoTemplate/repositories, query design, aggregation, indexes, transactions, reactive access, testing, and performance diagnostics.

After this lesson, you will be able to build a radius-based store search API with explainable total counts, resource-bounded reactive queries, and tests targeting MongoDB's real boundaries.

## 2. Three Distinct Questions: Nearest, Within Region, and How Many?

Suppose five stores A, B, C, D, and E sit at different locations:

~~~text
                     B
                .----------.
             .-'            '-.
            /      A           \
           |         X      C   |     E
            \         D         /
             '-.            .-'
                '----------'

X: customer location
Circle: search radius
~~~

Three non-equivalent requirements:

| Question | Appropriate Operator / Pipeline | Output |
| --- | --- | --- |
| Which points are closest to X, with distances? | **`$near`/`$nearSphere`** or **`$geoNear`** | Distance-ordered list |
| Which points lie inside a shape/radius? | **`$geoWithin`** | Matching documents geometrically inside, no automatic distance sort |
| How many points fall within a radius? | **`countDocuments`** with **`$geoWithin`** or suitable aggregation count | A single count |

**Avoid using `$near` solely to count** when the API does not need distance sorting.

### 2.1. Counting the Whole Set vs Counting a Page

An API may return:

~~~json
{
  "items": ["store-A", "store-C"],
  "pageSize": 2,
  "totalInRadius": 5
}
~~~

**`items.length = 2`** is the number of rows on the current page, whereas **`totalInRadius = 5`** is the total number of documents matching the region and filters before skip/limit. Never use the returned page item count as the total across the entire set.

### 2.2. Counting Documents, Not Counting Coordinates

If a single `Store` document holds multiple points inside an array (multiple branches), `countDocuments` counts **matching documents**, not necessarily matching coordinates. If the business wants to count **individual branches**, model one document per branch or use an aggregation with appropriate unwind/filter stages.

### 2.3. GeoJSON Coordinate Order

A GeoJSON Point uses:

~~~json
{
  "type": "Point",
  "coordinates": [106.7009, 10.7769]
}
~~~

The mandatory order is **`[longitude, latitude]`**, not `[latitude, longitude]`. Longitude lies in `[-180,180]`, latitude in `[-90,90]`. An inverted coordinate pair may be rejected by MongoDB or interpreted as a completely different place on Earth.

## 3. `StoreDocument` Model and `2dsphere` Index

Sample data used throughout:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "shop-a",
  name: "Store A",
  active: true,
  location: {
    type: "Point",
    coordinates: [106.7009, 10.7769]
  }
}
~~~

Java entity:

~~~java
package com.example.geosearch;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexed;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "stores")
public record StoreDocument(
    @Id ObjectId id,
    String tenantId,
    String name,
    boolean active,
    @GeoSpatialIndexed(type = GeoSpatialIndexType.GEO_2DSPHERE)
    GeoJsonPoint location
) {}
~~~

**`@GeoSpatialIndexed`** declares index metadata. The actual index must exist in MongoDB; automatic index creation is not enabled by default in every project.

~~~javascript
db.stores.createIndex(
  { location: "2dsphere" },
  { name: "idx_stores_location_2dsphere" }
);
~~~

### 3.1. Compound Indexes and Tenants

If the system always filters tenant/active, evaluate a compound index:

~~~javascript
db.stores.createIndex(
  { tenantId: 1, active: 1, location: "2dsphere" },
  { name: "idx_stores_tenant_active_geo" }
);
~~~

This is a **benchmark candidate**, not guaranteed faster in all scenarios. How MongoDB utilizes a compound geospatial index depends on query shape, data distribution, cardinality, and MongoDB Server version; run **`explain("executionStats")`** before deploying to production.

### 3.2. Invalid Data

A GeoJSON Point needs a valid type and valid coordinates. A **`2dsphere` index** imposes requirements on indexed geometries. Validate user input, guard against null/missing fields, and manage schema migrations carefully.

### 3.3. Never Confuse `2d` and `2dsphere`

| Index | Typical Data | Model |
| --- | --- | --- |
| `2d` | Legacy coordinate pairs | Planar; requires attention to coordinate units |
| `2dsphere` | GeoJSON and certain legacy coordinate formats | Spherical geometry |

For real store locations on Earth, **GeoJSON Point + `2dsphere`** is usually much clearer to model. Never treat planar map arithmetic with a radius in "degrees" as accurate meter distances.

## 4. Geospatial Operators to Distinguish

| Operator | Purpose | Auto-Sorts by Distance? | Counting Caveat? |
| --- | --- | --- | --- |
| `$near` | Proximity search near a point | Yes | Cannot be used directly in `countDocuments` |
| `$nearSphere` | Proximity search using spherical geometry | Yes | Cannot be used directly in `countDocuments` |
| `$geoWithin` | Filter geometries inside a region | No | Suitable for `countDocuments` |
| `$geoIntersects` | Filter geometries intersecting another geometry | No | Suitable when requirement is "intersection" |
| `$geoNear` | Aggregation stage computing distance and sorting nearest–farthest | Yes | Not a `$match`; stage must lead the pipeline |

### 4.1. `$near` and GeoJSON

~~~javascript
db.stores.find({
  tenantId: "shop-a",
  active: true,
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      $maxDistance: 2000
    }
  }
});
~~~

With a **GeoJSON Point** in the proximity predicate, max distance is expressed in **meters**. `$near` returns matching documents ordered nearest first; adding another sort can override distance ordering and increase cost.

### 4.2. `$geoWithin` with `$centerSphere`

~~~javascript
const EARTH_RADIUS_METERS = 6371008.8;
const radiusRadians = 2000 / EARTH_RADIUS_METERS;

db.stores.find({
  tenantId: "shop-a",
  active: true,
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.7009, 10.7769],
        radiusRadians
      ]
    }
  }
});
~~~

**`$centerSphere` takes its radius in radians**, so 2,000 meters must be divided by Earth's radius in meters. Passing `2000` directly as the `$centerSphere` radius is a unit error.

### 4.3. `$geoWithin` Does Not Return Distance

A document within the 2 km radius will match, yet **no distance field is automatically attached**. If you need to show "430 m away" or sort nearest-first, use `$geoNear` or compute distance with explicit units per requirements.

### 4.4. Why Not Replace `$near` with `$geoWithin` Everywhere?

Both queries can select a similar set of points when configured equivalently, but they differ in default sorting, distance metadata, inner/outer ring semantics, index/operator constraints, and boundary cases. Therefore, **switching when counting** is a deliberate design choice.

## 5. `countDocuments` Does Not Directly Support `$near`/`$nearSphere`

Per MongoDB and Spring Data MongoDB documentation on **Counting Documents**, `countDocuments` and the corresponding `$match` aggregation step do not accept `$near` or `$nearSphere` as counting predicates.

The following `mongosh` call is not supported for counting:

~~~javascript
// Do not use $near directly inside countDocuments:
db.stores.countDocuments({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      $maxDistance: 2000
    }
  }
});
~~~

Replace it with a containment query:

~~~javascript
const radiusRadians = 2000 / 6371008.8;

const total = db.stores.countDocuments({
  tenantId: "shop-a",
  active: true,
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.7009, 10.7769],
        radiusRadians
      ]
    }
  }
});
~~~

**Core point:** `countDocuments` needs a filtering predicate over the document set, not distance-based ordering.

### 5.1. `countDocuments` vs the Count of a Paginated Result

~~~javascript
const page = db.stores.find(withinQuery)
  .sort({ name: 1, _id: 1 })
  .skip(20)
  .limit(10)
  .toArray();

const total = db.stores.countDocuments(withinQuery);
~~~

`page.length` may be 10, while `total` may be 1,000. Never infer the total from a single page; when counting via `mongosh` or a specific API, confirm `skip`/`limit`/options are handled properly.

### 5.2. Never Substitute `estimatedDocumentCount`

`estimatedDocumentCount()` uses collection metadata/statistics for a fast collection-wide estimate and **cannot apply geospatial, tenant, active, or radius filters**. It never answers "total stores within 2 km".

### 5.3. What If Total Count Is Not Needed?

When an API only needs to render one page and a `hasNext` flag, fetch `pageSize + 1` results to determine whether a next page exists. **Running a count query is not mandatory** for every endpoint if UX does not need a total count.

## 6. How Spring Data MongoDB Rewrites `near` Queries for Counting

Since Spring Data MongoDB 3.x, **`count`** calls through `MongoTemplate`/`ReactiveMongoTemplate` use `countDocuments`-based execution rather than collection statistics for regular count queries.

Because `countDocuments` rejects `$near`/`$nearSphere`, Spring Data includes logic converting geospatial predicates to **`$geoWithin`** with a corresponding **`$center`/`$centerSphere`** region during counting.

For example, Spring Data documentation illustrates:

~~~javascript
// Original intent: select points near a location, with maxDistance.
{
  location: {
    $near: [-73.99171, 40.738868],
    $maxDistance: 1.1
  }
}
~~~

represented during counting as an equivalent containment shape like:

~~~javascript
{
  location: {
    $geoWithin: {
      $center: [
        [-73.99171, 40.738868],
        1.1
      ]
    }
  }
}
~~~

**Note:** the snippet above uses legacy coordinate pairs and `$center` in coordinate-space units. It is **not** a 1.1-meter radius example. For GeoJSON/`2dsphere`, use proper spherical geometry and unit conversions.

### 6.1. Can You Call `MongoTemplate.count` Directly?

~~~java
GeoJsonPoint origin =
    new GeoJsonPoint(106.7009, 10.7769);

Query nearQuery = Query.query(
    Criteria.where("location")
        .near(origin)
        .maxDistance(2_000)
);

long total = mongoTemplate.count(
    nearQuery, StoreDocument.class);
~~~

On Spring Data versions that support rewriting, the API adapts the count query accordingly. Even so:

- Do not treat automatic rewriting as proof that all min/max bounds and geometries behave identically to your intent.
- Do not rely on internal rewrite mechanics as a public contract across unrelated code.
- When you need tightly controlled count semantics, **define a separate `$geoWithin` query** and cover it with integration tests.
- Whenever upgrading Spring Data versions, re-test rewrite behavior.

### 6.2. Why Inspect the Actual Executed Command?

For subtle cases, enable driver command monitoring or write integration tests to inspect the **actual filter sent to MongoDB**. Never just print `Query.toString()` and assume it equals the exact command sent after Spring Data's conversion.

### 6.3. Rewriting a Count Query Does Not Turn It into Nearest-Neighbor Search

A successful count returns neither a sorted list, nor per-document distances, nor an average distance. It solely counts documents matching the rewritten filter.

## 7. `minDistance` + `maxDistance`: Counting an Annulus

A search may require **500 m to 2,000 m**, excluding points too close to the origin:

~~~javascript
db.stores.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      $minDistance: 500,
      $maxDistance: 2000
    }
  }
});
~~~

**`$geoWithin`** has no direct `$minDistance` option. To count an annulus, model it as:

~~~text
Counted set = Documents inside 2,000 m circle
              minus documents inside 500 m circle
~~~

A MongoDB expression:

~~~javascript
const earthRadius = 6371008.8;
const outerRadius = 2000 / earthRadius;
const innerRadius = 500 / earthRadius;

db.stores.countDocuments({
  $and: [
    { tenantId: "shop-a", active: true },
    {
      location: {
        $geoWithin: {
          $centerSphere: [
            [106.7009, 10.7769],
            outerRadius
          ]
        }
      }
    },
    {
      $nor: [
        {
          location: {
            $geoWithin: {
              $centerSphere: [
                [106.7009, 10.7769],
                innerRadius
              ]
            }
          }
        }
      ]
    }
  ]
});
~~~

### 7.1. Inner Circle Boundary

If the inner circle is evaluated as **inclusive** at exactly 500 m, `$nor` excludes those exact-boundary points too. Meanwhile, `$minDistance` on proximity queries has its own boundary semantics.

Exact-boundary positions, floating-point precision, and edge geometries require **integration tests** when counting must be exact down to boundary points.

### 7.2. Automatic Rewriting in Spring Data

Spring Data documentation describes handling **`minDistance`** by combining `$geoWithin` and `$nor`. Do not equate rewriting in one specific version with preserving every nuance of the original query; verify against your API/version and generated BSON.

### 7.3. Do Not Run Two Separate Counts and Subtract If You Need One Snapshot

~~~javascript
const outer = db.stores.countDocuments(outerFilter);
const inner = db.stores.countDocuments(innerFilter);
const annulus = outer - inner;
~~~

If concurrent writers insert, delete, or relocate stores between the two count calls, the difference can be inconsistent. A single **`countDocuments` with the annulus condition** or a single aggregation is better when all predicates must evaluate together.

## 8. Near vs Within: Decision Table for Real APIs

| API Requirement | Preferred Query | Separate Count Needed? |
| --- | --- | --- |
| "20 nearest stores" | `$near`/`$geoNear` + limit | No, unless displaying total |
| "All stores within 2 km" | `$geoWithin` + `$centerSphere` | Can count if total is needed |
| "Within 2 km, sorted by name" | `geoWithin` + sort name/id | Yes, if UI wants total |
| "From 500 m to 2 km" | `$geoNear` min/max or `geoWithin` outer + exclude inner | Yes, if total is needed |
| "How many open stores are in radius?" | `countDocuments` `geoWithin` + status filter | No need for nearest query |
| "List real distance to each store" | `$geoNear` | Count is a separate operation |
| "Polygons intersecting a route" | `$geoIntersects` by geometry | Count with matching geometry/filters |

**Use counting only for an independent business question**, rather than reflexively pairing `countDocuments` with every `$near` query.

## 9. Building a Radius-Counting Service with `MongoTemplate`

To eliminate ambiguity, the service should expose a dedicated counting method taking **meters** and using `$geoWithin`/`$centerSphere`.

~~~java
package com.example.geosearch;

import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class StoreRadiusCountService {

    private static final double EARTH_RADIUS_METERS = 6_371_008.8;
    private final MongoTemplate mongoTemplate;

    public StoreRadiusCountService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public long countWithin(
            String authenticatedTenantId,
            double longitude, double latitude,
            double radiusMeters) {

        validate(authenticatedTenantId,
            longitude, latitude, radiusMeters);

        Circle sphere = new Circle(
            new Point(longitude, latitude),
            radiusMeters / EARTH_RADIUS_METERS
        );

        Query query = Query.query(
            Criteria.where("tenantId")
                .is(authenticatedTenantId)
                .and("active").is(true)
                .and("location").withinSphere(sphere)
        );

        return mongoTemplate.count(query, StoreDocument.class);
    }

    private static void validate(
            String tenant,
            double longitude, double latitude,
            double radiusMeters) {

        if (tenant == null || tenant.isBlank()
                || !Double.isFinite(longitude)
                || !Double.isFinite(latitude)
                || longitude < -180 || longitude > 180
                || latitude < -90 || latitude > 90
                || !Double.isFinite(radiusMeters)
                || radiusMeters <= 0
                || radiusMeters > 50_000) {
            throw new IllegalArgumentException(
                "Invalid location or radius");
        }
    }
}
~~~

**Why this works:** `tenant` comes from a trusted authentication context; latitude/longitude/radius are validated; the radius converts to **radians** for `withinSphere`; all tenant + active + location filters apply during the count.

### 9.1. Why Cap at 50 km?

That is an **illustrative policy**, not a hard MongoDB limit. Depending on requirements, choose 5 km, 100 km, or a custom region; measure query plans, data, and SLAs.

### 9.2. Single Source of Filters

List and count APIs must use the exact same center, radius, tenant, active, category, and other predicates. Maintain a shared **`StoreSearchCriteria` object** or filter-builder helper so one endpoint never drifts out of sync with the other.

### 9.3. Counting Immediately After an Update

Results can depend on read preference, read concern, replication lag, and commit state. Even a syntactically right query does not guarantee every replica reflects the newest write at the exact same instant.

## 10. Counting with Aggregation `$match` + `$count`

MongoDB supports an aggregation pipeline:

~~~javascript
const r = 2000 / 6371008.8;

db.stores.aggregate([
  {
    $match: {
      tenantId: "shop-a",
      active: true,
      location: {
        $geoWithin: {
          $centerSphere: [
            [106.7009, 10.7769],
            r
          ]
        }
      }
    }
  },
  { $count: "total" }
]);
~~~

This counts within a region **without placing `$near` in `$match`**.

### 10.1. Spring Data Aggregation

~~~java
import org.bson.Document;
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;

Circle radius = new Circle(
    new Point(106.7009, 10.7769),
    2000.0 / 6371008.8
);

Aggregation pipeline = Aggregation.newAggregation(
    Aggregation.match(
        Criteria.where("tenantId").is("shop-a")
            .and("active").is(true)
            .and("location").withinSphere(radius)
    ),
    Aggregation.count().as("total")
);

AggregationResults<Document> results =
    mongoTemplate.aggregate(
        pipeline, StoreDocument.class, Document.class);

Document row = results.getUniqueMappedResult();
long total = row == null
    ? 0L
    : ((Number) row.get("total")).longValue();
~~~

This snippet illustrates `Aggregation.match`, `Aggregation.count`, and empty-result handling. A complete service must validate inputs, never hardcode the tenant, and enforce authorization.

### 10.2. What If Zero Documents Match?

When `$count` receives no input documents, the pipeline emits **no result document** instead of `total=0`. DTO mapping must treat an empty aggregation output as `0`.

### 10.3. Should You Write an Aggregation for Every Count?

No. **`mongoTemplate.count(query, type)`** with `$geoWithin` is usually shorter and easier to maintain. Dedicated aggregations help when multiple pipeline stages are needed, but are not automatically faster than `countDocuments`.

## 11. Counting with Paging: Avoid Returning Just the Page Size

An API returning `page=2, size=10, total=97`:

~~~text
List query:  tenant + active + region + sort + skip 20 + limit 10
Count query: tenant + active + region (no page limit applied)
~~~

Example:

~~~java
Query countFilter = Query.query(
    Criteria.where("tenantId").is(tenant)
        .and("active").is(true)
        .and("location").withinSphere(circle)
);

long total = mongoTemplate.count(
    countFilter, StoreDocument.class);

Query pageQuery = Query.query(
    Criteria.where("tenantId").is(tenant)
        .and("active").is(true)
        .and("location").withinSphere(circle)
);

pageQuery.with(
    org.springframework.data.domain.PageRequest.of(
        2, 10,
        org.springframework.data.domain.Sort.by("name")
            .ascending()
            .and(org.springframework.data.domain.Sort.by("_id"))
    )
);

List<StoreDocument> page =
    mongoTemplate.find(pageQuery, StoreDocument.class);
~~~

**Using a separate `Query` for counting** avoids guessing how a count API handles `skip`/`limit` across different framework versions.

### 11.1. Deterministic Sorting

If multiple stores share the same `name`, sorting only by `name` is non-deterministic; append a unique tie-breaker such as **`_id`**. Even then, concurrent mutations between requests can cause offset paging to repeat or skip rows.

### 11.2. How Does Nearest Paging Differ?

With `$near`/`$geoNear`, distance defines the natural order. Locations at equal distances may need a tie-breaker, though extra sorting can add cost. Inspect query plans when using large offsets/skips.

### 11.3. When Total Is Unnecessary

Fetch at most **`pageSize + 1`** results to decide `hasNext`, and return the first `pageSize` elements. You do not need a count query on every screen just because the framework provides a `Page` type.

## 12. Transactions: Not Simply Adding `@Transactional`

MongoDB transactions bind to a **`ClientSession`** and require a supporting deployment—typically a replica set or compatible sharded cluster. Spring Data provides `MongoTransactionManager`:

~~~java
package com.example.geosearch;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class MongoTxConfiguration {

    @Bean("mongoTransactionManager")
    MongoTransactionManager transactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

`MongoTemplate` sharing the same `MongoDatabaseFactory` can participate in the transaction session managed by this manager.

### 12.1. Why Does Counting Inside Transactions Have Historical Differences?

The legacy `count` command relied on collection statistics and failed to reflect uncommitted changes inside a transaction. Spring Data used to switch to aggregation-based counting only when a transaction was active. Since **Spring Data MongoDB 3.x**, regular `count` calls use **`countDocuments`/aggregation-based counting** even outside transactions.

**Never rely on estimated collection statistics for business logic requiring transactional snapshot consistency.**

### 12.2. Near Operators and Transactions

Spring Data documentation on **Special behavior inside transactions** notes that count filters using `$near`/`$nearSphere` must use `$geoWithin` with `$center`/`$centerSphere` on the aggregation count path.

This **does not mean all geospatial queries are forbidden inside all transactions**. Distinguish commands, operators, stages, server versions, and transaction topologies.

### 12.3. Never Create Geospatial Indexes Inside a Business Transaction

Provision collections/indexes via migrations before serving traffic. DDL support inside transactions depends on MongoDB version and topology; never execute index creation inside read/write business transactions.

### 12.4. Read-Only Transactions Still Have Overhead

`MongoTransactionManager` can still start a transaction on methods annotated with **`@Transactional(readOnly=true)`**. It does not magically make queries cheaper or bypass read concern/read preference constraints.

## 13. Count and List Can Differ Across Two Separate Commands

~~~text
T0: count within radius -> total=10
T1: one store inside radius moves outside
T2: find within radius -> 9 stores
~~~

This can be normal behavior when two independent commands do not share a snapshot. **`total=10`** alongside **9 items** does not by itself prove the geospatial filter is buggy.

| Requirement | Approach |
| --- | --- |
| Nearby search UI where data may change | Two independent queries may be acceptable |
| API requires count and items consistent in one read | Single aggregation or appropriate snapshot |
| Multi-document writes must commit together | Short transaction, guards, and retry logic |

### 13.1. Transactions and Read Concern

**`@Transactional`** does not unconditionally guarantee every read shares an identical snapshot across every topology. When snapshots matter, configure transaction read concern and test against your real deployment.

### 13.2. `$facet`

When the spatial filter uses `$geoWithin` in `$match`, a **`$facet`** pipeline can compute both the `items` branch (sort/skip/limit) and the `totals` branch (`$count`) from the same input. However, `$facet` has memory and BSON output size limits; do not default to it for very large collections.

### 13.3. Never Forget Authorization

Inside a transaction or `$facet`, tenant filters remain mandatory. If `items` filters tenant while `totals` forgets to filter, the total count leaks other tenants' existence.

## 14. `$geoNear` Is a Special Aggregation Stage

MongoDB **`$geoNear`** computes distance to each document and emits results ordered nearest to farthest:

~~~javascript
db.stores.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 2000,
      spherical: true,
      query: {
        tenantId: "shop-a",
        active: true
      }
    }
  },
  { $limit: 20 },
  {
    $project: {
      name: 1,
      distanceMeters: 1
    }
  }
]);
~~~

Three key points:

1. **`$geoNear` must be the first stage** in a regular pipeline.
2. **`key`** selects the geospatial-indexed field (critical when multiple geospatial indexes exist).
3. Tenant/active filters go inside **`query`** of `$geoNear`; never place `$match` before `$geoNear`.

### 14.1. Why Not Put `$match` First?

~~~javascript
// Invalid structure: never place $match before $geoNear.
[
  { $match: { tenantId: "shop-a" } },
  { $geoNear: { /* ... */ } }
]
~~~

MongoDB requires `$geoNear` to come first. Put normal conditions such as tenant/active into `$geoNear`'s `query` field to narrow candidates whenever supported.

### 14.2. `$geoNear` Inside Transactions?

Aggregation in general is supported inside MongoDB transactions, subject to a **list of disallowed stages** and server-version rules. Never make absolute claims that `$geoNear` is always forbidden or always allowed in every workload.

Verify on your real deployment:

- Valid geospatial index and `$geoNear` is the first stage.
- Pipeline contains no transaction-disallowed stages.
- Transaction read concern, read preference, and cursor lifecycle fit.
- MongoDB Server/driver/Spring Data versions support the pattern.
- Integration tests run against a replica set or sharded test cluster.

### 14.3. `$near` Is Not `$geoNear`

`$near`/`$nearSphere` are **query match execution operators** that cannot be stuffed directly inside an aggregation pipeline's `$match`. For nearest aggregation, use the **`$geoNear`** stage.

## 15. `$geoNear` + `$count`: Another Option

When you need **`$geoNear`'s exact semantics** for min/max distance filtering, `$geoNear` can feed directly into a count stage:

~~~javascript
db.stores.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      key: "location",
      distanceField: "distanceMeters",
      minDistance: 500,
      maxDistance: 2000,
      spherical: true,
      query: {
        tenantId: "shop-a",
        active: true
      }
    }
  },
  { $count: "total" }
]);
~~~

This is an **aggregation** starting with `$geoNear`, not `countDocuments` taking a `$near` predicate. It may compute distances across many candidates before counting, so benchmark it against `$geoWithin` counting.

### 15.1. When Does It Make Sense?

- You need min/max distance counts strictly consistent with `geoNear` semantics.
- Near-boundary behavior matters and geometry has been tested.
- Appropriate indexes exist and pipeline cost is acceptable.

### 15.2. Never Limit Before Counting Total

~~~javascript
[
  { $geoNear: { /* ... */ } },
  { $limit: 20 },
  { $count: "total" }
]
~~~

This pipeline only counts **at most 20** items because `$limit` precedes `$count`, not the total in the whole region.

### 15.3. Do Not Rely on Legacy Default Limits

Current MongoDB no longer defaults `$geoNear` to a 100-document cap as old documentation stated. For list APIs, **set `$limit` explicitly**; for full-region counts, understand the execution cost.

## 16. Single `$facet` Pipeline: `items` and `total`

With a `$geoWithin` filter, `$facet` can return a page and total count in a single aggregation:

~~~javascript
const radius = 2000 / 6371008.8;

db.stores.aggregate([
  {
    $match: {
      tenantId: "shop-a",
      active: true,
      location: {
        $geoWithin: {
          $centerSphere: [
            [106.7009, 10.7769],
            radius
          ]
        }
      }
    }
  },
  {
    $facet: {
      items: [
        { $sort: { name: 1, _id: 1 } },
        { $skip: 20 },
        { $limit: 10 },
        { $project: { name: 1, location: 1 } }
      ],
      totals: [
        { $count: "total" }
      ]
    }
  }
]);
~~~

### 16.1. Filter Before `$facet`

Filtering geography/tenant before `$facet` lets both branches share the narrowed candidate set; `items` adds sorting/pagination while `totals` counts the whole filtered set.

### 16.2. Empty Results

The `totals` branch can be an **empty array** rather than containing `total=0`. DTO mapping must handle an empty `totals` array gracefully.

### 16.3. Cost of `$facet`

`$facet` is subject to memory and BSON output limits, can evaluate many candidates for the total, and sometimes increases latency. Never assume it beats two separate queries; measure on real data.

## 17. When Should a Geo Query Be Inside a Transaction?

A read-only request for the **ten nearest stores** rarely **needs a multi-document transaction**. Transactions belong around well-defined consistency boundaries.

Example order-fulfillment flow:

~~~text
1. Find nearest stores.
2. Attempt to reserve stock at a store.
3. Create reservation document.
4. Write stock movement and outbox event.
~~~

**Steps 2–4** may need a transaction to commit/roll back together. Yet a store appearing closest does not guarantee stock remains available or reservable when the write runs.

### 17.1. Candidate Queries Do Not Replace Conditional Updates

~~~javascript
db.stores.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.7009, 10.7769]
      },
      distanceField: "distanceMeters",
      maxDistance: 5000,
      key: "location",
      query: { tenantId: "shop-a", active: true }
    }
  },
  { $limit: 5 }
]);
~~~

Then in the inventory service, you still need a **conditional update `stock>=quantity`** inside the reservation transaction/state transition. Never decrement stock using a stale snapshot without a guard condition.

### 17.2. Transaction Context

`MongoTransactionManager` binds to thread context in the imperative stack; `ReactiveMongoTransactionManager` binds to the Reactor Context. Raw drivers or separate sessions do not automatically join a Spring transaction.

### 17.3. Avoid Long-Running Transactions

A slow geo search inside a transaction holds snapshots, sessions, and cursors open. Never keep a transaction open across HTTP response streaming or while waiting on clients unless strictly required for consistency.

### 17.4. A Count Does Not Replace a Business Guard

Checking "count of stores within radius >= 1" does not ensure a Store still has stock or stays open when reservation executes; writes must re-verify state/version at update time.

## 18. `ReactiveMongoTemplate`: `count` Returns `Mono`, `find` Returns `Flux`

Reactive MongoDB access avoids loading all results into a `List`. Instead:

| Imperative API | Reactive API |
| --- | --- |
| `MongoTemplate.count(query, class)` → `long` | `ReactiveMongoTemplate.count(query, class)` → `Mono<Long>` |
| `MongoTemplate.find(query, class)` → `List<T>` | `ReactiveMongoTemplate.find(query, class)` → `Flux<T>` |
| `MongoTemplate.geoNear(nearQuery, class)` → `GeoResults<T>` | `ReactiveMongoTemplate.geoNear(nearQuery, class)` → `Flux<GeoResult<T>>` |
| `MongoTemplate.aggregate(...)` → `AggregationResults<T>` | `ReactiveMongoTemplate.aggregate(...)` → `Flux<T>` |

This difference is in API contract and lifecycle, not MongoDB Server changing its geospatial operators.

### 18.1. Reactive Service Counting Within a Radius

~~~java
package com.example.geosearch;

import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveStoreCountService {

    private static final double EARTH_RADIUS_METERS = 6_371_008.8;
    private final ReactiveMongoTemplate template;

    public ReactiveStoreCountService(
            ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Mono<Long> countWithin(
            String authenticatedTenantId,
            double longitude, double latitude,
            double radiusMeters) {

        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || !Double.isFinite(longitude)
                || longitude < -180 || longitude > 180
                || !Double.isFinite(latitude)
                || latitude < -90 || latitude > 90
                || !Double.isFinite(radiusMeters)
                || radiusMeters <= 0 || radiusMeters > 50_000) {
            return Mono.error(
                new IllegalArgumentException("Invalid search"));
        }

        Circle circle = new Circle(
            new Point(longitude, latitude),
            radiusMeters / EARTH_RADIUS_METERS
        );

        Query query = Query.query(
            Criteria.where("tenantId")
                .is(authenticatedTenantId)
                .and("active").is(true)
                .and("location").withinSphere(circle)
        );

        return template.count(query, StoreDocument.class);
    }
}
~~~

**`Mono<Long>`** emits the count only once the Publisher is subscribed to and the query completes. If the query fails, it emits an **error signal** rather than silently turning into `Mono.just(0)`.

### 18.2. Never Block on the WebFlux Event Loop

~~~java
// Avoid:
long total = reactiveStoreCountService
    .countWithin(tenant, lon, lat, meters)
    .block();
~~~

Blocking stalls the event loop or throws on non-blocking threads. Return the `Mono` to the controller or compose with `map`/`flatMap`/`zip`.

### 18.3. Never Self-Subscribe Inside a Service

~~~java
// Avoid:
Mono<Long> total = template.count(query, StoreDocument.class);
total.subscribe(value -> log.info("Total: {}", value));
return total;
~~~

The snippet above triggers **two subscriptions and two count commands**: one from manual `subscribe`, and one when WebFlux subscribes to the returned `Mono`. To log within the pipeline, use **`doOnNext`** without a separate subscription.

### 18.4. Preserve Error Semantics

Do not write:

~~~java
return template.count(query, StoreDocument.class)
    .onErrorReturn(0L);
~~~

hiding all database failures as "zero stores". Timeouts, authorization errors, and missing-index errors are completely different from an empty result set. Any fallback needs an explicit policy, metrics/logs, and an unambiguous response.

## 19. Reactive `geoNear`: `Flux<GeoResult<T>>`

With Spring Data MongoDB `ReactiveMongoTemplate`:

~~~java
Flux<GeoResult<StoreDocument>> nearby =
    reactiveMongoTemplate.geoNear(
        nearQuery, StoreDocument.class);
~~~

Each **`GeoResult<T>`** holds `content` as the mapped entity and `Distance` matching `NearQuery`'s metric.

### 19.1. Using `NearQuery` with Explicit Units

~~~java
package com.example.geosearch;

import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.Metrics;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.NearQuery;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class ReactiveNearestStoreService {

    private final ReactiveMongoTemplate template;

    public ReactiveNearestStoreService(
            ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Flux<GeoResult<StoreDocument>> findNearby(
            double longitude, double latitude,
            double radiusKilometers) {

        if (!Double.isFinite(longitude)
                || !Double.isFinite(latitude)
                || longitude < -180 || longitude > 180
                || latitude < -90 || latitude > 90
                || !Double.isFinite(radiusKilometers)
                || radiusKilometers <= 0
                || radiusKilometers > 50) {
            return Flux.error(
                new IllegalArgumentException("Invalid search"));
        }

        GeoJsonPoint center =
            new GeoJsonPoint(longitude, latitude);

        NearQuery near = NearQuery.near(
                center, Metrics.KILOMETERS)
            .maxDistance(
                new Distance(radiusKilometers, Metrics.KILOMETERS))
            .limit(20);

        return template.geoNear(near, StoreDocument.class);
    }
}
~~~

**The example above focuses on units and API shape** and omits tenant/active filters. In multi-tenant systems, you must add the tenant filter to `NearQuery` or use server-side `$geoNear.query`. Never expose unscoped results to real users.

### 19.2. Distance Depends on the `Point` Type

`NearQuery` Javadoc highlights:

- Legacy **`Point`** can imply distance semantics in **radians** under neutral configuration.
- **`GeoJsonPoint`** uses **meters** in MongoDB GeoJSON representation.
- Setting a **`Metric`** (e.g., `Metrics.KILOMETERS`) tells `NearQuery` to compute/display distances in an explicit unit.

Never copy literal `maxDistance` values between `Point` and `GeoJsonPoint` without checking coordinate type and metric.

### 19.3. Reading Distance

~~~java
return reactiveTemplate.geoNear(
        near, StoreDocument.class)
    .map(geo -> new StoreDistanceView(
        geo.getContent().id(),
        geo.getContent().name(),
        geo.getDistance().getValue()
    ));
~~~

`StoreDistanceView` is an application DTO to define. If `NearQuery` returns distance in kilometers, name the DTO property **`distanceKilometers`** rather than letting clients guess the unit.

### 19.4. Adding a Tenant Filter to `NearQuery`

`NearQuery` exposes `query(Query)` for regular conditions:

~~~java
Query scopedFilter = Query.query(
    Criteria.where("tenantId").is(tenant)
        .and("active").is(true)
);

NearQuery scopedNear = NearQuery
    .near(new GeoJsonPoint(lon, lat), Metrics.KILOMETERS)
    .maxDistance(new Distance(2, Metrics.KILOMETERS))
    .query(scopedFilter)
    .limit(20);
~~~

`tenant` must be resolved by authentication/authorization, never trusted directly from client input.

## 20. Reactive Repository Methods for Geospatial Queries

Spring Data MongoDB reactive repositories support derived geospatial queries, including return types:

~~~java
package com.example.geosearch;

import org.bson.types.ObjectId;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactiveStoreRepository
        extends ReactiveMongoRepository<StoreDocument, ObjectId> {

    Flux<StoreDocument> findByLocationNear(
        Point point, Distance distance);

    Flux<GeoResult<StoreDocument>> findByLocationNear(
        Point point, Distance distance,
        org.springframework.data.domain.Pageable pageable);
}
~~~

These two overloads illustrate an entity `Flux` and a `GeoResult` `Flux`; verify method resolution, parameter order, and field names against your exact Spring Data version. In multi-tenant systems, use derived methods including **`TenantId`/`Active`** or use Template with full filters.

### 20.1. Reactive Does Not Return `GeoPage`/`GeoResults`

In the blocking stack, **`GeoResults<T>`** wraps a list of `GeoResult` items and computes aggregate data such as average distance. **`GeoPage<T>`** is an eager pageable result wrapper.

Spring Data MongoDB documentation states that reactive geospatial queries **do not support `GeoResults`/`GeoPage` return types** because they conflict with deferred streaming semantics. The reactive API still supports **`Flux<GeoResult<T>>`** and entity `Flux`.

### 20.2. `Pageable` Is Still Supported

Not supporting `GeoPage` **does not mean no pagination**. Reactive derived queries can accept **`Pageable`** to push sort/skip/limit down to the database, while the return type remains `Flux`.

### 20.3. No `Mono<Page>` for Reactive Repositories

If an API needs `totalPages`, the service must fetch content and count separately, or run an aggregation returning both. `Mono<Page<T>>` is not automatically supported by Spring Data reactive repositories the way `Page` is in blocking repositories.

### 20.4. Do Not Confuse `GeoResult` with `GeoPage`

`GeoResult` represents **one item + distance**. If you need the average distance on a single page, compute it over a **bounded set** with a capped item count; if you need region-wide aggregates, design an explicit aggregation pipeline.

## 21. Reactive Paging and Total: Composing with `Mono.zip`

With `geoWithin`, you can run a `Flux` find and a `Mono` count:

~~~java
import java.util.List;
import org.springframework.data.geo.Circle;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import reactor.core.publisher.Mono;

public record StorePageResponse(
    List<StoreDocument> items,
    long total,
    int page,
    int size
) {}

public Mono<StorePageResponse> searchPage(
        String tenant, Circle circle,
        int page, int size) {

    if (tenant == null || tenant.isBlank()
            || circle == null
            || page < 0 || size <= 0 || size > 100) {
        return Mono.error(
            new IllegalArgumentException("Invalid page"));
    }

    Query pageQuery = Query.query(
        Criteria.where("tenantId").is(tenant)
            .and("active").is(true)
            .and("location").withinSphere(circle)
    );

    pageQuery.with(PageRequest.of(
        page, size,
        Sort.by("name").ascending()
            .and(Sort.by("_id"))
    ));

    Query countQuery = Query.query(
        Criteria.where("tenantId").is(tenant)
            .and("active").is(true)
            .and("location").withinSphere(circle)
    );

    Mono<List<StoreDocument>> items =
        reactiveTemplate.find(
            pageQuery, StoreDocument.class)
            .collectList();

    Mono<Long> count = reactiveTemplate.count(
        countQuery, StoreDocument.class);

    return Mono.zip(items, count)
        .map(tuple -> new StorePageResponse(
            tuple.getT1(), tuple.getT2(),
            page, size
        ));
}
~~~

This snippet belongs in a service with an injected **`ReactiveMongoTemplate reactiveTemplate`** field; `StorePageResponse` is a public record and should live in its own source file.

### 21.1. Is `collectList` Bounded?

Yes, because the `find` is capped at **`size<=100`**. Never call `collectList` on a `Flux` returning every store in a country or an unbounded change stream.

### 21.2. `Mono.zip` and Consistency

`Mono.zip` composes two Publishers, yet **does not automatically open a transaction or snapshot**. Count and find can run as two separate MongoDB commands; data can mutate between them.

### 21.3. If You Only Need `hasNext`

Fetch `size + 1` results with a safe upper bound, return up to `size` items, and set `hasNext`. That skips the count query, though you must still account for offset-paging drift under concurrent edits.

### 21.4. Empty Counts

`ReactiveMongoTemplate.count` typically emits **`Mono<Long>`** with `0` when no document matches—unlike a custom `$count` aggregation, which can emit **`Flux.empty()`** on empty input. Never assume one uniform empty-handling behavior across every API.

## 22. Reactive Transactions: Using Reactor Context

When reactive transactions are required, configure **`ReactiveMongoTransactionManager`**:

~~~java
package com.example.geosearch;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

@Configuration
public class ReactiveMongoTxConfiguration {

    @Bean("reactiveMongoTransactionManager")
    ReactiveMongoTransactionManager reactiveTxManager(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }
}
~~~

Reactive transaction context flows through the Publisher/Subscriber context, unlike `MongoTransactionManager`'s thread-bound imperative sessions.

### 22.1. `TransactionalOperator`

~~~java
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

TransactionalOperator operator =
    TransactionalOperator.create(
        reactiveMongoTransactionManager);

Mono<StorePageResponse> result =
    searchPage(tenant, circle, 0, 20)
        .as(operator::transactional);
~~~

This demonstrates wrapping a pipeline in a transaction. Only use transactions when consistency/transaction options require them; never enable transactions just because a query is geospatial.

### 22.2. Do Not Block or Fork Subscriptions

~~~java
// Wrong reactive transaction management.
Mono<Long> count = reactiveTemplate.count(
    countQuery, StoreDocument.class);

count.subscribe();  // Separate subscription, outside the returned chain.

return reactiveTemplate.find(pageQuery, StoreDocument.class);
~~~

Independent subscriptions do not share the reactive transaction context and can execute outside the request lifecycle.

### 22.3. Do Not Mix Blocking `MongoTemplate` into a Reactive Transaction

A `MongoTemplate` call running on `boundedElastic` or another thread will not automatically join a session managed by `ReactiveMongoTransactionManager`. When atomicity is required, keep all reactive operations inside **one reactive chain** under the right manager.

### 22.4. What Does `readOnly` Mean?

Spring Data may still open a transaction even with `@Transactional(readOnly=true)` in the reactive stack. Never assume `readOnly` disables sessions or routes all queries to secondaries.

## 23. Speed Depends on More Than `Flux`

Reactive I/O avoids tying up a blocking thread while waiting on the network, yet **does not make an expensive geospatial search cheap**.

### 23.1. Sources of Cost

- Large numbers of documents matching a wide region.
- Effectiveness of the geospatial index/compound filter.
- Number of round trips (`items` + `total`).
- Distance calculations, sorting, and `skip`.
- Number of items mapped/projected by the converter.
- Page size and concurrency limits.
- Transaction/session/snapshot overhead.
- MongoDB Server saturation and network latency.

### 23.2. Backpressure Is Not an Index

`Flux` supports backpressure in reactive streams, yet MongoDB still has to locate/retrieve candidates via a query plan. Backpressure does not fix an unindexed filter, nor does it guarantee the database only scans the exact number of rows requested by the subscriber in every query.

### 23.3. Bounded Resources

For nearest APIs:

~~~java
NearQuery near = NearQuery
    .near(new GeoJsonPoint(lon, lat), Metrics.KILOMETERS)
    .maxDistance(new Distance(3, Metrics.KILOMETERS))
    .limit(30);
~~~

Capping both radius **and** limit controls data exposure and cost. For full-region `geoWithin` APIs, enforce pagination and similar caps.

### 23.4. Cancellation Is Not Data Rollback

Client subscription cancellation stops downstream pipeline processing, yet does not roll back prior server work—especially if the request had write side effects. Read-only geo searches carry less risk, though timeouts/cancellations still need monitoring.

## 24. Indexes, Query Plans, and Geospatial Count Cost

Having the right count formula is not enough; performance depends on indexes, examined documents, and how the server evaluates filters.

### 24.1. A `2dsphere` Index Must Actually Exist

~~~javascript
db.stores.getIndexes();
~~~

Without a compatible geospatial index, queries like `$near`/`$geoNear` can fail due to a missing geospatial index. **`@GeoSpatialIndexed`** is only Java metadata and does not ensure the collection has the index if auto-creation is off.

### 24.2. Reading `executionStats`

~~~javascript
const withinQuery = {
  tenantId: "shop-a",
  active: true,
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.7009, 10.7769],
        2000 / 6371008.8
      ]
    }
  }
};

db.stores.find(withinQuery)
  .explain("executionStats");
~~~

Inspect the chosen index, keys/documents examined, returned document count, latency, and query plan. If a query scans huge numbers of documents only to discard them in memory, fix the index/filter/geometry instead of simply adding more threads.

### 24.3. Never Substitute `estimatedDocumentCount` for Filtered Counts

`estimatedDocumentCount` is cheap, yet ignores tenant, active, and radius filters. A fast number with **the wrong semantics** is not a valid optimization.

### 24.4. Geospatial Indexes Are Not Typical Covered Queries

Geospatial indexes have restrictions on covered queries. Do not assume projecting only `_id`/`name` will always be served purely from the index; verify via `explain` and server documentation.

### 24.5. Sort and Skip

`$near` queries inherently order by distance. Adding another sort can increase sorting overhead; offset paging with large `skip` values gets expensive. Evaluate page caps and cursor/snapshot policies.

### 24.6. Compound Indexes Do Not Cure Every Query

A compound index with `tenantId`, `active`, and `location` `2dsphere` can fit a specific workload. However, field order, geospatial components, and cardinality are not universally optimal; benchmark on real data before keeping extra indexes that slow down every write.

### 24.7. Partial Indexes

If you only index `active` Stores, queries hoping to use the partial index must include predicates compatible with the index's partial filter expression. A count covering all Stores will take a different plan or miss the partial index.

### 24.8. Sharding

MongoDB cannot use a geospatial index as a shard key, though sharded collections can carry geospatial indexes alongside a separate shard key. Design the shard key for your workload and measure cross-shard geo query cost.

## 25. Geometry and Distance Units

| Data / Operation | Unit / Meaning |
| --- | --- |
| GeoJSON `Point.coordinates` | `[longitude, latitude]` in degrees |
| `$near` with GeoJSON + `maxDistance` | Meters |
| `$geoNear` with GeoJSON + `min`/`maxDistance` | Meters |
| `$centerSphere` radius | Radians |
| `Distance(2, Metrics.KILOMETERS)` | Two km at the Spring Data layer |
| Legacy `Point` with neutral `NearQuery` | May use radians |
| `2dsphere` index | Spherical geometry, valid geographic data |

### 25.1. Radius Conversion Formula

Using an approximate Earth radius:

\[
\theta_{\mathrm{rad}}=\frac{d_{\mathrm{m}}}{R_{\mathrm{m}}}
\]

Where **R ≈ 6,371,008.8 meters** is the mean Earth radius used in examples. For `d=2,000 m`, angle `theta` is roughly `0.0003139 radians`.

This is a spherical geometric approximation. If the business requires high-precision geodetic surveying, choose an appropriate coordinate system/method and respect its geometric limits.

### 25.2. Near-Boundary Points

For stores at 1,999.999 m and 2,000.001 m, inclusion can vary due to floating-point math, radius conversion, and geometry models. Test fixtures should keep points **well clear of boundaries**, adding separate boundary tests driven by business policy.

### 25.3. Poles and the 180° Meridian

Polygons/circles near the poles or crossing the ±180° meridian require proper spherical geometry. Never convert them into flat bounding boxes with `longitude >= min AND <= max` ignoring wrap-around.

### 25.4. Coordinate Data Types

~~~json
{"coordinates":["106.7009","10.7769"]}
~~~

These are **strings**, not the numeric values GeoJSON Points require. Validate inputs and prevent client formatting from turning numbers into strings.

### 25.5. Comparing Distances from Two Paths

`NearQuery` may return `Distance` in kilometers, whereas raw BSON `$geoNear` with GeoJSON computes `distanceMeters`. If merging results from two query paths, normalize units before sorting or displaying.

## 26. Privacy and Multi-Tenancy in Geo Queries

User coordinates or sensitive site coordinates can constitute personal data. Even in a store-finder example, the service must:

- Collect coordinates only with valid purpose and permission.
- Validate bounds, radius, request rates, and response sizes.
- Avoid persisting full user location histories in logs unnecessarily.
- Expose store coordinates per business disclosure policy.
- Enforce **tenant/authorization filters** on both count and items.
- Never serve cached responses containing tenant A's data to tenant B.
- Rate-limit/guard against abuse from overly granular coordinate probing.

### 26.1. Returning Only a Count Can Still Leak Information

An API that returns zero coordinates—only the count of sensitive locations within 10 m across many query centers—can still allow triangulation across repeated queries. Consider minimum radii, coordinate precision, suppression thresholds, and rate limits per use case.

### 26.2. Tenant Must Be Verified Server-Side

~~~java
Criteria.where("tenantId").is(authenticatedTenantId)
    .and("active").is(true)
    .and("location").withinSphere(circle);
~~~

Never treat a client-supplied `tenantId` query parameter as authorization to read data. Authorization and data scoping belong to the security boundary.

### 26.3. Query Telemetry Does Not Need Exact Location History

You can safely log `requestId`, query type, radius bucket, duration, error code, result count, and protected tenant metadata. Avoid retaining raw user coordinates indefinitely by default.

## 27. Integration Testing Strategy

At a minimum, verify:

| Test Case | Expectation |
| --- | --- |
| Store right at center | Included in positive radius |
| Store ~100 m from center | Included in 2 km |
| Store > 5 km from center | Excluded from 2 km count |
| Other tenant's store right beside center | Excluded from count |
| Inactive store right beside center | Excluded from count |
| No matching documents | Count = 0 |
| Out-of-range longitude/latitude | Rejected before hitting DB |
| Negative, `NaN`, or infinite radius | Rejected |
| `$geoWithin` count vs proximity search | Agree on fixtures well away from boundaries |
| `minDistance` + `maxDistance` | Exact annulus set matched |
| `$geoNear` | `GeoResult` has distance and nearest–farthest order |
| Reactive count | `Mono<Long>` emits right count |
| Reactive `geoNear` | `Flux<GeoResult<T>>` emits right items |
| Transaction count on replica set | No near-in-count error and accurate per policy |
| Count and find under concurrent writes | Behavior matches documented consistency contract |
| Missing index | Tests/migrations catch and resolve it |

### 27.1. Why Mocking Is Insufficient

Unit tests mocking `MongoTemplate` only verify that the service constructs a `Criteria` or calls `count`. They **do not verify** that MongoDB executes `2dsphere`, radian radii, query rewrites, cursors, or transactions properly.

### 27.2. Seed Points Well Away from Boundaries

~~~text
Center: (106.7009, 10.7769)
Near:   (106.7019, 10.7769)  — roughly one hundred meters away
Far:    (106.7609, 10.7769)  — several km away
~~~

These numbers are illustrative fixtures, not meter-exact geodetic measurements. Tests assert `near` lies inside 2 km and `far` lies outside, avoiding floating-point boundary sensitivity.

### 27.3. MongoDB for Testing

Count/near integration tests need a test MongoDB instance and geospatial index. Multi-document transaction tests need a replica set or compatible deployment. Never run fixture seed/delete scripts from this lesson against production.

### 27.4. Layering Tests

1. **Unit tests:** radius/coordinate validation, meters→radians conversion.
2. **Integration:** indexes, find/count, raw MongoDB geometry.
3. **Transaction integration:** read/count inside a MongoDB transaction session.
4. **Reactive integration:** `Mono`/`Flux`/`StepVerifier`, error/cancellation behavior.
5. **Performance tests:** `explain`/stats on production-like data and workloads.

## 28. Synchronous Integration Test: Same Filters for Count and Near

Testing directly against MongoDB catches wrong radii, missing tenant scopes, and missing indexes.

~~~java
package com.example.geosearch;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.UUID;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
@Import(StoreRadiusCountService.class)
class StoreRadiusCountIntegrationTest {

    @Autowired MongoTemplate template;
    @Autowired StoreRadiusCountService countService;

    @BeforeEach
    void ensureGeoIndex() {
        template.getCollection("stores")
            .createIndex(new Document("location", "2dsphere"));
    }

    @Test
    void countsOnlyActiveStoresOfAuthenticatedTenant() {
        String tenant = "TEST-" + UUID.randomUUID();
        String otherTenant = "TEST-" + UUID.randomUUID();

        StoreDocument center = new StoreDocument(
            new ObjectId(), tenant, "CENTER", true,
            new GeoJsonPoint(106.7009, 10.7769));
        StoreDocument near = new StoreDocument(
            new ObjectId(), tenant, "NEAR", true,
            new GeoJsonPoint(106.7019, 10.7769));
        StoreDocument far = new StoreDocument(
            new ObjectId(), tenant, "FAR", true,
            new GeoJsonPoint(106.7609, 10.7769));
        StoreDocument wrongTenant = new StoreDocument(
            new ObjectId(), otherTenant, "OTHER", true,
            new GeoJsonPoint(106.7009, 10.7769));
        StoreDocument inactive = new StoreDocument(
            new ObjectId(), tenant, "INACTIVE", false,
            new GeoJsonPoint(106.7009, 10.7769));

        List<StoreDocument> fixtures = List.of(
            center, near, far, wrongTenant, inactive);
        List<ObjectId> ids = fixtures.stream()
            .map(StoreDocument::id)
            .toList();

        template.insertAll(fixtures);

        try {
            long total = countService.countWithin(
                tenant, 106.7009, 10.7769, 2_000);
            assertThat(total).isEqualTo(2L);

            Query nearQuery = Query.query(
                Criteria.where("tenantId").is(tenant)
                    .and("active").is(true)
                    .and("location")
                    .near(new GeoJsonPoint(106.7009, 10.7769))
                    .maxDistance(2_000)
            );

            List<StoreDocument> found = template.find(
                nearQuery, StoreDocument.class);

            assertThat(found)
                .extracting(StoreDocument::name)
                .containsExactlyInAnyOrder("CENTER", "NEAR");

            assertThat(countService.countWithin(
                tenant, 107.5, 11.5, 100))
                .isZero();

        } finally {
            template.remove(
                Query.query(Criteria.where("_id").in(ids)),
                StoreDocument.class);
        }
    }

    @Test
    void rejectsBadLocationWithoutSendingCount() {
        assertThatThrownBy(() ->
            countService.countWithin(
                "shop-a", 999, 10, 2_000))
            .isInstanceOf(IllegalArgumentException.class);

        assertThatThrownBy(() ->
            countService.countWithin(
                "shop-a", 106, 10, Double.NaN))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

### 28.1. Why Does the Test Need an Index?

Geospatial queries—especially nearest searches—require matching indexes. If tests only mock repositories or omit the `2dsphere` index, they fail to reflect production. Ensure the test fixture/database has the index before running queries.

### 28.2. Why Compare Count and Near?

The fixtures sit well away from boundaries, so both selection methods:

- `$near` within at most 2 km.
- `$geoWithin` spherical 2 km circle.

must pick **`CENTER + NEAR`** and exclude `FAR`. If the count fails due to a missing tenant filter, wrong units, or passing 2,000 radians, the test catches it right away.

### 28.3. Do Not Demand Fixed Order When Distances Are Equal

The test above compares name sets since the focus is filtering/counting. To test distance sorting, use points at clearly distinct distances, check returned ordering, and define a tie-breaker for equal distances.

### 28.4. Test Configuration

Tests require a test MongoDB database, the Spring Boot Data MongoDB test slice, JUnit 5, and AssertJ. The example omits container setup to focus on domain logic; projects can connect via MongoDB Testcontainers or another test server.

**Never run tests against production**, never reuse real user IDs/tenants, and always scope fixture cleanup tightly.

## 29. Transaction Integration Test with a Replica Set

To prove **geospatial counting works inside a MongoDB transaction**, write a dedicated test against a real replica set, such as Testcontainers MongoDB.

### 29.1. Transactional Service

~~~java
package com.example.geosearch;

import org.springframework.data.geo.Circle;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransactionalGeoCountService {

    private final MongoTemplate template;

    public TransactionalGeoCountService(MongoTemplate template) {
        this.template = template;
    }

    @Transactional(
        transactionManager = "mongoTransactionManager")
    public long insertAndCount(
            StoreDocument newStore, Circle searchArea) {

        template.insert(newStore);

        Query query = Query.query(
            Criteria.where("tenantId").is(newStore.tenantId())
                .and("active").is(true)
                .and("location").withinSphere(searchArea)
        );

        return template.count(query, StoreDocument.class);
    }
}
~~~

Because the service uses the **`MongoTemplate` sharing the transaction manager's `MongoDatabaseFactory`**, insert and count execute in the same transaction when invoked through the Spring proxy.

### 29.2. Testcontainers Replica Set

~~~java
package com.example.geosearch;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
@Import(MongoTxConfiguration.class)
class TransactionalGeoCountTest {

    @Container
    static MongoDBContainer mongo = new MongoDBContainer(
        DockerImageName.parse("mongo:7.0"));

    @DynamicPropertySource
    static void mongoProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.mongodb.uri",
            mongo::getReplicaSetUrl);
    }

    @Autowired MongoTemplate template;
    @Autowired TransactionalGeoCountService service;

    @Test
    void countInsideTransactionCanSeeOwnInsertedStore() {
        template.getCollection("stores")
            .createIndex(new Document("location", "2dsphere"));

        String tenant = "TEST-" + UUID.randomUUID();
        StoreDocument store = new StoreDocument(
            new ObjectId(),
            tenant,
            "TX-STORE",
            true,
            new GeoJsonPoint(106.7009, 10.7769)
        );

        Circle circle = new Circle(
            new Point(106.7009, 10.7769),
            2000.0 / 6371008.8
        );

        try {
            long inTransaction =
                service.insertAndCount(store, circle);

            assertThat(inTransaction).isEqualTo(1L);

            long afterCommit = template.count(
                Query.query(
                    Criteria.where("_id").is(store.id())
                ),
                StoreDocument.class
            );
            assertThat(afterCommit).isEqualTo(1L);
        } finally {
            template.remove(
                Query.query(
                    Criteria.where("_id").is(store.id())
                ),
                StoreDocument.class
            );
        }
    }
}
~~~

This sample assumes a Spring Boot application whose component scan covers the service package, Testcontainers MongoDB dependencies, and Docker in the test environment. Verify Testcontainers packages/APIs against your project's version.

### 29.3. Why Create the Index Outside the Transaction?

Never place `createIndex` inside `insertAndCount`. Indexes/schemas should be provisioned before transactions begin—both avoiding DDL restrictions and keeping index errors distinct from count errors.

### 29.4. What Does This Test Prove?

Inside the transaction, the service:

1. Inserts a `Store`.
2. Counts using `geoWithin` inside the same MongoDB transaction.
3. Returns `1` on the isolated fixture.
4. Commits.
5. The outer test observes the persisted document.

**It does not prove all read-concern/snapshot choices**, nor does it cover transaction aborts/retries or nearest filters inside transactions. Add dedicated tests as required by your system.

### 29.5. How to Test Rollback

Add a service method that throws a `RuntimeException` **after** insert+count, then assert the document does not appear outside once the transaction aborts. Ensure the call goes through the Spring proxy rather than self-invocation on `@Transactional`.

### 29.6. Do Not Blindly Put `@Transactional` on the Test Method

A transaction opened externally by the test framework can cause the service to merely join the test's transaction, hiding the service's real commit boundaries. Transactional service tests should clearly control which transaction owns the commit.

## 30. Reactive Integration Test with `StepVerifier`

To prove reactive count and `geoNear` emit properly through their publishers, seed fixtures with **`ReactiveMongoTemplate`** and test with `StepVerifier`.

~~~java
package com.example.geosearch;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.UUID;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.NearQuery;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@DataMongoTest
@Import(ReactiveStoreCountService.class)
class ReactiveGeospatialIntegrationTest {

    @Autowired ReactiveMongoTemplate template;
    @Autowired ReactiveStoreCountService countService;

    @Test
    void reactiveCountAndGeoNearUseSameTestPoints() {
        String tenant = "TEST-" + UUID.randomUUID();

        StoreDocument near = new StoreDocument(
            new ObjectId(), tenant, "NEAR", true,
            new GeoJsonPoint(106.7009, 10.7769));
        StoreDocument far = new StoreDocument(
            new ObjectId(), tenant, "FAR", true,
            new GeoJsonPoint(106.7609, 10.7769));

        Query cleanup = Query.query(
            Criteria.where("_id").in(
                List.of(near.id(), far.id()))
        );

        Mono<Long> scenario = Mono.from(
                template.getCollection("stores")
                    .createIndex(
                        new Document("location", "2dsphere")))
            .then(template.insert(near))
            .then(template.insert(far))
            .then(countService.countWithin(
                tenant, 106.7009, 10.7769, 2_000));

        try {
            StepVerifier.create(scenario)
                .expectNext(1L)
                .verifyComplete();

            NearQuery nearQuery = NearQuery.near(
                    new GeoJsonPoint(106.7009, 10.7769),
                    Metrics.KILOMETERS)
                .maxDistance(
                    new Distance(2, Metrics.KILOMETERS))
                .query(Query.query(
                    Criteria.where("tenantId").is(tenant)
                        .and("active").is(true)))
                .limit(10);

            StepVerifier.create(
                template.geoNear(
                    nearQuery, StoreDocument.class))
                .assertNext(result -> {
                    assertThat(result.getContent().name())
                        .isEqualTo("NEAR");
                    assertThat(result.getDistance().getValue())
                        .isGreaterThanOrEqualTo(0d);
                })
                .verifyComplete();
        } finally {
            StepVerifier.create(
                template.remove(cleanup, StoreDocument.class))
                .expectNextCount(1)
                .verifyComplete();
        }
    }
}
~~~

### 30.1. Why Use `Mono.from(createIndex)`?

Calling `createIndex` on a **reactive `MongoCollection`** returns a Publisher. Wrapping it with `Mono.from(...).then(...)` ensures the index operation is subscribed to and finishes before inserts/queries run, instead of creating a Publisher and discarding it.

### 30.2. Testing `Mono` Count vs `Flux` `geoNear`

- **`Mono<Long>`**: `expectNext(1L)`, `verifyComplete`.
- **`Flux<GeoResult<T>>`**: assert each `GeoResult`, `verifyComplete`, or use `expectNextCount` with appropriate fixtures.

If the `Flux` completes empty, `assertNext` fails; this catches wrong filters, wrong units, or missing indexes.

### 30.3. Never Block or Subscribe Twice

The test never calls `block()` and never calls `subscribe()` outside `StepVerifier`. Each `StepVerifier` creates a single subscription driving its query.

### 30.4. Cleanup After Errors

The `finally` block cleans up the test database using a Publisher and `StepVerifier`. Even if the test fails while indexing before inserts run, `remove` can safely execute over nonexistent IDs. Never run this cleanup on production data.

### 30.5. Versions and Test Slices

A reactive-only project needs reactive starters/drivers and matching Spring Boot test auto-configuration. Verify `@DataMongoTest` and `ReactiveMongoTemplate.getCollection` APIs against your exact version; Testcontainers can provide an isolated MongoDB test instance.

## 31. Diagnostics Table When Counts, Transactions, or Reactive Queries Fail

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| `countDocuments` fails with `$near` | `$near`/`$nearSphere` disallowed directly in `countDocuments` | Use `geoWithin` count or verified Spring Data rewrite |
| Count is huge despite asking for 2 km | Passed 2000 into `$centerSphere` as radians | Convert meters to radians |
| Finds stores in the wrong region | Swapped `[lat,lon]` vs `[lon,lat]` | Validate and inspect raw GeoJSON |
| `$near`/`$geoNear` reports missing index | `2dsphere` index not created | Run migration/`ensureIndex` in tests |
| Count = 0 yet `find` returns rows | Mismatched filters, units, or field mapping | Compare tenant/active/radius/BSON query |
| Count differs from page length | Count covers whole region; page has limit | Distinguish total vs page size |
| `total=20` despite 500 items in region | `$limit` placed before `$count` | Count before limiting or split branches |
| `total` and `items` differ under concurrent writes | Two independent reads without shared snapshot | Accept eventual view or use snapshot/aggregation |
| `estimatedCount` ignores geospatial filter | Collection stats ignore query filters | Never use `estimatedCount` for radius totals |
| Min/max annulus count is wrong | Forgot inner circle exclusion, boundary/unit mismatch | `geoWithin` outer + `$nor` inner, test boundaries |
| Spring Data count changes after upgrade | Geo near rewrite behavior evolved | Check version docs and integration tests |
| `$geoNear` fails on stage position | Placed `$match` before `$geoNear` | Put `$geoNear` first, filter inside `query` |
| `$geoNear` picks wrong geospatial field | Multiple geospatial indexes without `key` | Specify exact `key` |
| `$geoNear` returns no distance | Used `geoWithin` only or projection dropped distance | Use `$geoNear` and `distanceField` |
| Geo query is slow | Wide radius, missing/wrong index, large sort/skip | `explain`, radius caps, index tuning |
| Transaction count fails locally | Standalone `mongod` | Test against a replica set |
| Transaction count hits near restriction | `$near` inside aggregation-count helper | Use `geoWithin` with matching sphere/circle |
| Long-running transaction times out | Held open across slow geo search / HTTP streaming | Shorten transaction scope |
| Transaction reads appear inconsistent | Read concern/session mismatch with assumptions | Verify transaction options and test |
| `GeoPage` rejected in reactive stack | Reactive lacks `GeoPage`/`GeoResults` wrappers | Use `Flux<GeoResult<T>>` and DTOs |
| `Mono<Page>` on reactive repository fails | No automatic reactive `Page` return | Use `Flux` + separate count `Mono` |
| Reactive query never executes | Publisher never subscribed | Return `Mono`/`Flux`, test with `StepVerifier` |
| Reactive count runs twice | Manual `subscribe()` plus caller subscription | Maintain a single subscription lifecycle |
| WebFlux event loop stalls | Called `.block()` or blocking repositories | Compose reactive operators |
| Reactor returns 0 despite DB timeout | `onErrorReturn(0L)` swallowed errors | Keep errors distinct from empty results |
| `collectList` spikes RAM | Unbounded query | Cap page size, never collect infinite `Flux` |
| Reactive transaction misses commands | Forked subscriptions or mixed sync manager | `ReactiveMongoTransactionManager` + single chain |
| User sees another tenant's count | Count filter missing authorization | Enforce tenant filter on both count and items |
| Tests pass only with mocks | Never exercised real geospatial engine | MongoDB integration tests with `2dsphere` index |

### 31.1. Layered Investigation Checklist

1. **Input:** are longitude, latitude, radius, and units right?
2. **BSON data:** is `location` a proper GeoJSON Point with numeric coordinates?
3. **Index:** does the `2dsphere` index exist, and does the query use it?
4. **Filters:** do count and items share identical tenant/active/category predicates?
5. **Command:** using `$near`, `$geoWithin`, or `$geoNear`; is `$near` accidentally entering `countDocuments`?
6. **Count rewrite:** how does your Spring Data version rewrite near/count queries?
7. **Region:** with `minDistance`, did you exclude the inner circle and test boundary semantics?
8. **Paging:** does the count run without `skip`/`limit`?
9. **Consistency:** do count and items execute independently, or with transactions/read concern?
10. **Reactive:** are Publishers composed and subscribed within one clean lifecycle?
11. **Transactions:** right manager/session/topology, and kept short?
12. **Performance:** `explain`, command latency, and connection-pool wait on realistic loads.

## 32. Practice Exercises

### Exercise 1: Choosing a Counting Operator

An API only needs the count of active stores within a 2 km radius, with no distances or sorting. Should you start with `$near` or `$geoWithin`?

**Answer:** **`$geoWithin` + `$centerSphere`** in `countDocuments`, including tenant/active filters.

### Exercise 2: GeoJSON in the Right Order

Coordinates `longitude=106.7009`, `latitude=10.7769`. What is the right GeoJSON Point?

~~~json
{
  "type": "Point",
  "coordinates": [106.7009, 10.7769]
}
~~~

**Answer:** longitude comes before latitude.

### Exercise 3: Distance in Radians

With `$centerSphere`, how must a 2,000-meter radius be converted?

~~~java
double radians = 2_000.0 / 6_371_008.8;
~~~

**Answer:** About `0.0003139 radians`. Never pass `2_000` directly as radians.

### Exercise 4: `countDocuments` with Near

A developer passes `$near` into `db.stores.countDocuments`. Should you assume that is valid?

**Answer:** No. `countDocuments` does not accept `$near`/`$nearSphere` directly; use `geoWithin` or another supported mechanism.

### Exercise 5: Spring Data Rewriting

Why might `MongoTemplate.count` with `Criteria.near` return a number even though `countDocuments` rejects `$near`?

**Answer:** Spring Data includes logic **rewriting near predicates** into `geoWithin` for counting. Still verify units/`minDistance`/boundaries on your exact version and actual queries.

### Exercise 6: Min/Max Distance

Need to count between 500 m and 2 km. Does `$geoWithin` directly have a `minDistance` option?

**Answer:** No. Combine an outer 2 km `$centerSphere` **and** `$nor` excluding the inner 500 m circle, testing boundaries. Or use `$geoNear` + `$count` when semantics and performance fit.

### Exercise 7: Page Count vs Total Count

A query returns 10 rows out of 125 matching rows. The API needs `totalPages` with `size=10`. Can you use 10 as the total?

**Answer:** No. You need `total=125` from the un-limited filter; `totalPages` is `ceil(125/10)=13`.

### Exercise 8: `estimatedCount`

Does `estimatedDocumentCount` return the total within a 2 km radius scoped to `tenantId`?

**Answer:** No. It applies neither geospatial nor tenant filters.

### Exercise 9: Transactions

Spring Data MongoDB calls `count` inside a `MongoTransactionManager` transaction. Should it rely on collection statistics to see newly inserted uncommitted documents?

**Answer:** No. Transactional counting needs a method reflecting transactional state; modern Spring Data uses `countDocuments`/aggregation-based counting.

### Exercise 10: `$geoNear` Stage

A MongoDB aggregation pipeline puts `$match` before `$geoNear`. What is wrong?

**Answer:** `$geoNear` must come first in the pipeline; put tenant/active predicates in `$geoNear.query`.

### Exercise 11: Counting with `$geoNear`

~~~javascript
[
  { $geoNear: { /* filter near */ } },
  { $limit: 20 },
  { $count: "total" }
]
~~~

**Question:** Is `total` the total across the whole region or the capped count?

**Answer:** The total **after `$limit`**, at most 20—not the whole region.

### Exercise 12: Two Independent Queries

Count=10 at T0; one Store moves at T1; `find` returns 9 at T2. Is this necessarily a bug?

**Answer:** No. Without a shared snapshot, data can mutate between two commands. Define the API consistency contract explicitly.

### Exercise 13: `$facet`

To return both `items` and `total` from the same `$geoWithin` input, which stage can you use?

**Answer:** **`$facet`** with `items` and `totals` branches after `$match`. Monitor memory/output limits and do not assume it always beats two queries.

### Exercise 14: Reactive Count

What return type does `ReactiveMongoTemplate.count` produce?

**Answer:** **`Mono<Long>`**, not `long` and not `Flux<Long>` for a standard count.

### Exercise 15: Reactive `geoNear`

What return type does `ReactiveMongoTemplate.geoNear` produce?

**Answer:** **`Flux<GeoResult<T>>`**. Each `GeoResult` carries the entity and a `Distance`.

### Exercise 16: `GeoPage`

Why does a reactive repository not automatically return `GeoPage` like the blocking API?

**Answer:** `GeoPage`/`GeoResults` are eager/aggregated wrappers incompatible with deferred reactive streaming contracts. Return `Flux` and build DTOs/counts as needed.

### Exercise 17: Reactive `Pageable`

Does lacking `GeoPage` mean reactive repositories cannot accept `Pageable`?

**Answer:** No. `Pageable` can still pass limit/skip/sort down into derived queries, while the return type stays `Flux`.

### Exercise 18: `Mono.zip`

Does `Mono.zip(itemsMono, countMono)` automatically open a MongoDB transaction?

**Answer:** No. It composes Publishers; use `ReactiveMongoTransactionManager`/`TransactionalOperator` when a true transactional snapshot is needed.

### Exercise 19: Blocking and Subscribing

A reactive service calls `.block()` to get the total and `.subscribe()` on the nearest query. What is wrong?

**Answer:** Blocking stalls the event loop; manual subscriptions detach lifecycle and transaction context. Return and compose `Mono`/`Flux` cleanly.

### Exercise 20: Tenant Security

The count API filters by tenant, yet the list API forgets the tenant filter. Is that safe?

**Answer:** No. Both count and items must enforce authorization/tenant filters, while controlling which location details may be exposed.

### Exercise 21: Multi-Point Documents

A `Store` document holds five locations in an array, two inside the region. How many `Store` documents does `countDocuments` count for that record?

**Answer:** **One document** if it matches, not two coordinates. Counting individual branches requires a separate document model or pipeline.

### Exercise 22: Proper Testing

A unit test mocks `MongoTemplate` returning `2` for count. Does that prove meters→radians conversion and `2dsphere` work?

**Answer:** No. You need MongoDB integration tests with center/near/far fixtures, a real index, and verified results.

## 33. Pre-Production Checklist

- **Schema:** Does `Store` `location` store a GeoJSON Point in `[longitude,latitude]` order?
- **Input bounds:** Are longitude/latitude valid, and radius positive and finite?
- **Units:** Does GeoJSON near use meters, `centerSphere` take radians, and `NearQuery` have explicit metrics?
- **`2dsphere`:** Has the index actually been created/migrated on the collection?
- **Compound index:** Has the query plan been measured with tenant/active/location predicates?
- **Tenant:** Does `authenticatedTenantId` come from a trusted server-side source?
- **Privacy:** Are overly granular coordinates or count triangulation mitigated?
- **Count:** Have you avoided putting `$near`/`$nearSphere` directly inside `countDocuments`?
- **Rewrite:** Has your Spring Data version's count-rewrite behavior been tested?
- **Manual count:** Do `geoWithin`/`$centerSphere` use the exact same region and filters as the list query?
- **`MinDistance`:** Is the inner circle/annulus handled per required semantics?
- **Boundary:** Are near-boundary tests present if high accuracy is needed?
- **Estimated count:** Have you avoided using `estimatedDocumentCount` for geospatial totals?
- **Paging:** Is the count query free of page `skip`/`limit`?
- **Stable ordering:** Is there a tie-breaker so sorted pagination stays deterministic?
- **Nearby:** Do `$near` or `$geoNear` cap radius and max results?
- **Distance:** Do responses state explicit units without mixing meters and kilometers?
- **Aggregation:** Is `$geoNear` first, with `key` if needed and proper `query` filters?
- **Pipeline count:** Have you avoided putting `$limit` before `$count` when counting the whole region?
- **`$facet`:** Have you measured memory/latency and handled empty `totals`?
- **Transaction topology:** Are replica set/sharded deployment and indexes ready?
- **Transaction scope:** Opened only when consistency requires it, and kept short?
- **Read concern:** Are snapshot/read-preference expectations understood for count + items?
- **Write guard:** If picking a Store then reserving stock, is there still a conditional stock update?
- **Reactive count:** Returns `Mono<Long>` and preserves error signals?
- **Reactive nearest:** Returns `Flux<GeoResult<T>>` instead of `GeoPage`/`GeoResults`?
- **Reactive paging:** Uses `Flux` + count `Mono`, or explicit aggregation/`hasNext`?
- **Reactive lifecycle:** No blocking or multiple manual subscriptions?
- **Reactive transaction:** Uses `ReactiveMongoTransactionManager`/Reactor Context when needed?
- **Backpressure:** Not mistaking streaming for automatic index optimization?
- **Limits:** Are `pageSize`, radius, and timeouts bounded?
- **Tests:** Do MongoDB integration tests cover center/near/far/tenant/units?
- **Transaction tests:** Are replica-set tests present for read/count where needed?
- **Reactive tests:** Does `StepVerifier` cover count, `GeoResult`, and error/cancel cases?
- **Operations:** Are `executionStats`, command latencies, pool metrics, and alerts configured?

## 34. Summary

1. **`$near`/`$nearSphere`** serve proximity searches with distance-sorting semantics; they **cannot be used directly inside `countDocuments`**.
2. **`$geoWithin`** with `$centerSphere` is the natural way to count GeoJSON points inside a spherical radius, requiring converting the radius from **meters to radians**.
3. **Spring Data MongoDB** rewrites near queries for counting in current versions; understand its behavior, especially around `minDistance`.
4. **An annulus** between `minDistance`/`maxDistance` can be modeled as an outer circle excluding an inner circle via `$nor`, or with `$geoNear` + `$count` when appropriate.
5. **`estimatedDocumentCount`** cannot replace filtered counts because it ignores tenant and radius predicates.
6. **Region-wide total** differs from page item count; never place `$limit` before `$count` when counting the full set.
7. **`$geoNear`** is an aggregation stage that must lead the pipeline and requires a geospatial index; place scalar filters in `query`.
8. **`$facet`** can return items and total in one pipeline, subject to memory/latency overhead and output size limits.
9. **`MongoTransactionManager`** enables imperative transactions; transactional counts need transactional-safe counting rather than collection statistics.
10. **Transactions are not needed by default for read-only geo searches**, do not speed up queries, and do not replace conditional write guards afterward.
11. **Count and items across two independent commands** can observe different data under concurrent writes; define the consistency contract before choosing snapshots/transactions.
12. **`ReactiveMongoTemplate.count`** returns `Mono<Long>`, while **`ReactiveMongoTemplate.geoNear`** returns `Flux<GeoResult<T>>`.
13. **Reactive repositories** support geospatial queries and `Pageable`, yet do not automatically return `GeoPage`/`GeoResults` or `Mono<Page>`.
14. **`Mono.zip`** composes two Publishers without opening a transaction; `ReactiveMongoTransactionManager` coordinates transactions via Reactor Context.
15. **Reactive streaming does not replace index/query-plan tuning**; bound radii, result counts, concurrency, and resources.
16. **Tenant security applies to both counts and items**; overly granular geographic counts can also leak information.
17. **MongoDB integration tests** must verify `2dsphere` indexes, coordinates, units, regions, and real execution; transaction tests require a supporting topology.

Mastering **counting limitations, transactions, and reactive variants** lets a **`SPRING_DATA_MONGODB`** service return accurate business-defined location counts, run unit-explicit proximity searches, maintain proper consistency boundaries, and implement reactive geospatial APIs without violating MongoDB Server constraints.

### References

- [Spring Data MongoDB — Counting Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-document-count.html) — `countDocuments`, `estimatedCount`, `$near`/`$nearSphere` rewrites, and `minDistance`.
- [Spring Data MongoDB — Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html) — `Criteria.near`/`withinSphere`, `$geoNear`, and `NearQuery`.
- [Spring Data MongoDB — Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — counting in transactions, sessions, transaction managers, and geospatial restrictions.
- [Spring Data MongoDB — Repository Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html) — reactive `GeoResult`, `Pageable`, and `GeoPage`/`GeoResults` limitations.
- [Spring Data MongoDB — NearQuery API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/NearQuery.html) — metrics, `GeoJsonPoint`, max/min distance, limits, and query filters.
- [Spring Data MongoDB — ReactiveMongoTemplate API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveMongoTemplate.html) — `count` `Mono`, `geoNear` `Flux`, and `aggregate`.
- [MongoDB Manual — `countDocuments`](https://www.mongodb.com/docs/manual/reference/method/db.collection.countDocuments/) — query predicate restrictions in `countDocuments`.
- [MongoDB Manual — `$geoNear` Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/geoNear/) — first-stage rule, geospatial indexes, distances, and query filters.
- [MongoDB Manual — `$near`](https://www.mongodb.com/docs/manual/reference/operator/query/near/) — nearest-neighbor filters and distance units.
- [MongoDB Manual — `$geoWithin`](https://www.mongodb.com/docs/manual/reference/operator/query/geoWithin/) — geometry containment and `centerSphere`.
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — sessions, topology, and transaction limits.
