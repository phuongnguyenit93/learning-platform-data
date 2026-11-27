# Geographic Region Matching and Boundary Coordinate Testing

## 1. Problem Statement: Is a Point Inside a Service Area?

In the **Geospatial Queries** chapter of **Spring Data MongoDB**, applications often need to determine whether a location belongs to a **delivery zone**, **management area**, **promotion region**, or **geofence**. The question sounds simple—"is point P inside region A?"—yet the answer depends on coordinate format, region geometry, boundaries, and MongoDB operator semantics.

For example, a business stores outlets with GeoJSON locations:

~~~json
{
  "_id": "store-101",
  "tenantId": "tenant-a",
  "status": "ACTIVE",
  "name": "Pickup Point A",
  "location": {
    "type": "Point",
    "coordinates": [106.7000, 10.7800]
  }
}
~~~

A test rectangular region spans longitude `106.66` to `106.74` and latitude `10.74` to `10.82`. We want to find stores inside the region, while also answering:

- Is a point **clearly inside** or **clearly outside**?
- Is a point **very close** to an edge without touching the boundary?
- Should a point **lying exactly on an edge or vertex** be considered inside or outside?
- What if the region has a **hole** in the middle, multiple disjoint parts, or crosses the ±180° meridian?
- Can one region **touch** another without intersecting interiors?
- Does the query use a **`2dsphere` index**, restrict by tenant, and target the right BSON field?

Lesson objectives:

1. Model GeoJSON Points, Polygons, MultiPolygons, and rings with valid structure.
2. Distinguish `$geoWithin`, `$geoIntersects`, and the different purpose of `$near`.
3. Build region-matching queries using MongoDB BSON and `MongoTemplate`.
4. Treat **boundaries as cases requiring an explicit contract**, rather than guessing from a drawing.
5. Design a test suite covering **inside / outside / just-inside / just-outside / on-edge / on-vertex / hole**.
6. Verify on real MongoDB, confirming GeoJSON/`2dsphere` indexes and performance with `explain`.
7. Avoid errors from swapped longitude–latitude, precision drift, anti-meridian wrap, projections, or missing tenant filters.

> Examples use Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x, and MongoDB supporting GeoJSON/`2dsphere` operators. Tests for **points lying right on a boundary** must be verified empirically on your exact server/version/geometry: boundary results of geospatial queries should not be treated as a universal "closed/open" contract unless MongoDB guarantees it for the case under test.

## 2. Distinguishing Coordinates from Distance Units

A GeoJSON Point represents:

~~~json
{
  "type": "Point",
  "coordinates": [106.70, 10.78]
}
~~~

The `coordinates` array follows **`[longitude, latitude]`** order—that is, **[longitude, latitude]**. For the sample points in Vietnam, longitude is around 106.x and latitude around 10.x. Swapping the two numbers is a common bug when input data uses "latitude, longitude" order.

| Component | Meaning | Typical Range |
|---|---|---|
`longitude` | Longitude, east/west direction | From −180° to +180° |
`latitude` | Latitude, north/south direction | From −90° to +90° |
`coordinates[0]` | Longitude | Decimal degrees |
`coordinates[1]` | Latitude | Decimal degrees |

Never treat an arbitrary coordinate pair as GeoJSON without confirming the coordinate reference system. MongoDB uses a spherical coordinate system per the GeoJSON standard for supported queries. `GeoJsonPoint(106.70, 10.78)` means **x=longitude**, **y=latitude**.

### 2.1. Degrees Are Angles, Not Meters

A `0.001°` longitude span does not have the same physical length at the equator as near the poles. Therefore:

- Do not convert a "within 20 m of the boundary" threshold into `±0.0002°` as a global constant.
- Do not use direct Euclidean distance on longitude/latitude pairs for legal or safety criteria.
- If you need "how many meters from the boundary", pick an appropriate geographic/geodesic distance algorithm, define tolerances, and verify separately.

In this lesson, *just-inside* and *just-outside* points use decimal coordinates offset from the edge by a finite margin to test classification, **without implicitly claiming that offset equals a standard number of meters**.

### 2.2. Coordinates Do Not Prove GPS Accuracy

Devices can supply locations with several meters of error or more. Many decimal places do not imply commensurate measurement precision. When applying geofences for billing, safety, or access control, enforce an explicit policy:

~~~text
reported location + accuracy/uncertainty
          |
          v
candidate region matching
          |
          v
near-boundary confidence policy
          |
          v
accept / reject / request better evidence
~~~

MongoDB returns geometric query results over stored coordinates; it does not evaluate GPS source quality.

## 3. Creating Valid GeoJSON Polygons

Rectangular test region:

~~~json
{
  "type": "Polygon",
  "coordinates": [
    [
      [106.66, 10.74],
      [106.74, 10.74],
      [106.74, 10.82],
      [106.66, 10.82],
      [106.66, 10.74]
    ]
  ]
}
~~~

GeoJSON Polygon `coordinates` is an **array of rings**. The first ring describes the exterior boundary. Each ring has at least four positions (counting the repeated final point closing the ring).

Here:

- Southwest corner: `[106.66, 10.74]`.
- Southeast corner: `[106.74, 10.74]`.
- Northeast corner: `[106.74, 10.82]`.
- Northwest corner: `[106.66, 10.82]`.
- The last point **matches the first point** to close the ring.

Diagram on a small coordinate plane (illustrative only, not a scaled map):

~~~text
              latitude
                  ^
  10.82     NW +---------------+ NE
              |               |
              |     INSIDE    |
  10.78       |       •       |
              |               |
  10.74     SW +---------------+ SE
                  106.66      106.74  --> longitude
~~~

### 3.1. Do Not Drop an Array Nesting Level

Wrong:

~~~json
{
  "type": "Polygon",
  "coordinates": [
    [106.66, 10.74],
    [106.74, 10.74],
    [106.74, 10.82]
  ]
}
~~~

This structure resembles a `LineString`, **not** a valid `Polygon.coordinates`. The right structure is:

~~~text
Polygon.coordinates = [
  outerRing[ [lon,lat], [lon,lat], ... ],
  optionalHoleRing[ ... ],
  ...
]
~~~

### 3.2. Ring Orientation and the Right-Hand Rule

Per GeoJSON RFC 7946, the exterior ring is recommended to wind **counter-clockwise (CCW)** and hole rings **clockwise (CW)** when viewed in a standard longitude–latitude plane.

Do not arbitrarily reverse point order to "fix" geometries when a region crosses the antimeridian, covers more than a hemisphere, or uses MongoDB `$geometry` with a special CRS. MongoDB has specific winding/spherical polygon interpretation rules; verify with tests and documentation for your version on large/complex regions.

### 3.3. Valid Geometry Means More Than Closing the Ring

A Polygon can be closed yet still invalid:

- Edges self-intersect into a "bowtie" shape.
- Zero-length edges or duplicate vertices create ambiguous topology.
- A hole lies outside the outer ring or illegally touches/crosses the outer boundary.
- Rings violate the winding rules of the target system.
- The polygon was constructed from swapped lat/lon coordinates.

A validator checking only lon/lat bounds and first/last equality **is not a full topology verifier**. For polygons imported from users or GIS tools, run dedicated geometry/topology validation or use verified GIS sources before persisting.

## 4. Region-Matching and Geometric Operators

Three commonly confused operator groups:

| Operator | Main Meaning | When to Use |
|---|---|---|
`$geoWithin` | Selects geometries lying inside the given region | Find store points **inside** a Polygon |
`$geoIntersects` | Selects geometries intersecting the query geometry | Find warehouse zones **intersecting** a restricted area; check geometry intersection |
`$near`/`$nearSphere` | Sorts by distance near a point, with optional max distance | Find stores near a customer; **does not** replace region inclusion |

MongoDB `$geoWithin` example:

~~~javascript
db.geo_outlets.find({
  tenantId: "tenant-a",
  status: "ACTIVE",
  location: {
    $geoWithin: {
      $geometry: {
        type: "Polygon",
        coordinates: [[
          [106.66, 10.74],
          [106.74, 10.74],
          [106.74, 10.82],
          [106.66, 10.82],
          [106.66, 10.74]
        ]]
      }
    }
  }
});
~~~

This query **fetches documents whose `location` lies inside the Polygon** per MongoDB operator and geometry semantics. It is not measuring distance to a center; a point close to the center can still sit outside a concave polygon or inside a hole.

### 4.1. Matching a `Point` Against a `Polygon`

For stores storing `location: Point`, `$geoWithin` with a Polygon directly expresses point-in-region checks. When the stored field is a Polygon or MultiPolygon rather than a Point, "geometry inside region" differs from "do two regions intersect?"; in that case consider `$geoIntersects`.

### 4.2. Region-to-Region Matching with `$geoIntersects`

If a document stores a Polygon representing a partner's service area:

~~~javascript
db.partner_areas.find({
  tenantId: "tenant-a",
  coverage: {
    $geoIntersects: {
      $geometry: {
        type: "Polygon",
        coordinates: [[
          [106.66, 10.74],
          [106.74, 10.74],
          [106.74, 10.82],
          [106.66, 10.82],
          [106.66, 10.74]
        ]]
      }
    }
  }
});
~~~

Intersection differs from `$geoWithin`: two regions may overlap partially without either containing the other completely. Also, **shared boundaries** warrant separate testing; if the business requires positive overlapping area rather than merely touching at a point/edge, do not treat an intersects query as an area calculation.

### 4.3. `$near` Does Not Answer "Inside the Region?"

A point 100 m from a zone's center can fall outside a narrow polygon; conversely, a point far from the center can lie inside a long arm of a concave polygon. Finding `nearest N` with `maxDistance` only works when the region itself is a disk of that radius, never for arbitrary shapes.

### 4.4. Bounding Boxes Are a Different Filter

Minimum and maximum longitude/latitude predicates can pre-filter candidates inside **a bounding box**. However, for concave Polygons, regions with holes, or antimeridian-crossing regions, a bounding box contains points that are **outside the real region**.

Thus:

~~~text
bbox match != polygon match
~~~

If using a bbox to speed up pre-filtering, still evaluate the real geometry and measure whether MongoDB's index planner even needs that pre-filter.

## 5. Creating the Appropriate Geospatial Index

For GeoJSON `Point` on field `location`, the standard index is:

~~~javascript
db.geo_outlets.createIndex(
  { location: "2dsphere" },
  { name: "idx_outlet_location_2dsphere" }
);
~~~

`2dsphere` supports spherical spatial queries on valid geometries. Never arbitrarily use `2d` for global GeoJSON or assume a `2d` index shares `2dsphere` semantics.

### 5.1. Is an Index Mandatory for `$geoWithin` to Run?

Some geospatial predicates can execute without a geospatial index, though on large datasets you should evaluate a `2dsphere` index to reduce scanned documents. Index requirements vary by operator and server version, so do not assume "without an index every geo operator fails" or "with an index every query is fast".

To know whether a query actually uses an index, run `explain("executionStats")` on a representative dataset and inspect index names and stages.

### 5.2. Compound `2dsphere` Index for Tenant/Status

When the workload always filters by tenant and status:

~~~javascript
db.geo_outlets.createIndex(
  { tenantId: 1, status: 1, location: "2dsphere" },
  { name: "idx_outlet_tenant_status_geo" }
);
~~~

This is a **design candidate**, not guaranteed optimal for every dataset. Evaluate selectivity, index size, write load, and query plans. Geospatial compound indexes have specific rules regarding the geo field and documents lacking geometry; avoid creating duplicate indexes without benchmarking.

### 5.3. Indexes Do Not Protect Tenants

Having `tenantId` in a compound index can accelerate queries when used. It **does not inject `tenantId` into filters**. The service layer must take the tenant from a verified auth context and put that predicate into **the same query** alongside the geospatial predicate.

### 5.4. Index Provisioning Must Be Controlled

Do not assume `@GeoSpatialIndexed` creates indexes in production under all configurations. Modern Spring Data MongoDB bases auto-index creation on configuration; use migration/provisioning workflows, verify existing indexes, and account for index build impact on the cluster.

## 6. Polygons with Holes: Inside the Outer Ring Is Not Enough

A service area with an excluded interior zone, such as a campus where delivery is prohibited:

~~~json
{
  "type": "Polygon",
  "coordinates": [
    [
      [106.66, 10.74],
      [106.74, 10.74],
      [106.74, 10.82],
      [106.66, 10.82],
      [106.66, 10.74]
    ],
    [
      [106.69, 10.77],
      [106.69, 10.79],
      [106.71, 10.79],
      [106.71, 10.77],
      [106.69, 10.77]
    ]
  ]
}
~~~

The outer ring encloses the region. The second ring is a **hole**. In this example, the hole's vertices wind opposite to the outer ring. Intended geometric classification:

| Point | Coordinate `[lon, lat]` | Intended Classification |
|---|---|---|
West, inside outer | `[106.675, 10.78]` | Inside effective region |
Center of hole | `[106.700, 10.780]` | Outside effective region |
East, inside outer | `[106.725, 10.78]` | Inside effective region |
Outside outer | `[106.750, 10.78]` | Outside region |
On hole boundary | `[106.690, 10.78]` | Boundary case needing dedicated policy/test |

### 6.1. Do Not Turn a Hole into a Separate Polygon in the Same Query

If you place both the outer ring and the hole into a `MultiPolygon` as two standalone polygons, the "hole" would be treated as an **included** region. A hole must live as the **second ring** inside the same `Polygon.coordinates`, not as a separate Polygon unioned into the area.

### 6.2. A Hole's Border Is a Special Boundary

A point right on a hole's edge behaves differently from a point clearly inside the hole. If business rules must reject every point "in the hole or touching the hole edge", define a **buffer inclusion/exclusion rule** instead of expecting a single operator to behave identically on every edge and vertex.

### 6.3. Never Accept Self-Intersecting Polygons

A polygon whose hole touches or crosses the exterior boundary can be invalid or interpreted differently across GIS libraries/servers. Validate topology at ingestion time before indexing and querying.

## 7. `MultiPolygon`: Regions with Multiple Disjoint Parts

A service with two separate operating clusters:

~~~json
{
  "type": "MultiPolygon",
  "coordinates": [
    [
      [
        [106.66, 10.74],
        [106.74, 10.74],
        [106.74, 10.82],
        [106.66, 10.82],
        [106.66, 10.74]
      ]
    ],
    [
      [
        [106.80, 10.74],
        [106.84, 10.74],
        [106.84, 10.78],
        [106.80, 10.78],
        [106.80, 10.74]
      ]
    ]
  ]
}
~~~

`MultiPolygon.coordinates` has **one extra array nesting level** compared to Polygon:

~~~text
Polygon      = [ ring, optionalHoleRing, ... ]
MultiPolygon = [ polygonRings, polygonRings, ... ]
~~~

Do not join two disjoint regions into a single ring, as connecting lines can create unwanted area or self-intersecting polygons.

### 7.1. Multiple Regions and Multiple Tenants

When each tenant has multiple regions, you can:

- Store each region in its own `service_areas` document with `tenantId` and `geometry`.
- Find regions containing a location using `$geoIntersects` or `$geoWithin` depending on geometry/object direction.
- Or store one normalized `MultiPolygon` if the business wants a unified region.

When modeling **store Points** and **region Polygons**, keep query direction clear:

~~~text
store.location Point $geoWithin input Polygon
    => find stores belonging to the query region

service_area.geometry Polygon $geoIntersects input Point
    => find regions intersecting the query point
~~~

Do not swap `$geoWithin` and `$geoIntersects` just because both start with "geo".

## 8. Boundaries: Something to Test Rather Than Guess

A polygon has an **interior**, **exterior**, and **boundary**. Mathematically, one can define a "closed" set (including boundary) or "open" set (excluding boundary). Yet a real geospatial system also involves:

- Spherical surface geometry rules—edges are not always straight Euclidean lines on a screen.
- Floating-point numbers and coordinate precision.
- Outer ring, hole, and shared-edge topology.
- Operator/index behavior documented by MongoDB.
- Sensor error and business policies when points lie near borders.

**Never write a rigid test assuming "`$geoWithin` always includes every point right on a Polygon edge/vertex" or "always excludes" across all geometries and MongoDB versions.** MongoDB documents caveats regarding boundary determinism/interpretation; test real queries and your system's contract.

### 8.1. Minimal Test Case Matrix

For the rectangular sample region:

| Case | Coordinate | Test Intent |
|---|---|---|
Clearly inside | `[106.70, 10.78]` | Expect match |
Clearly outside | `[106.76, 10.78]` | Expect no match |
Just-inside west edge | `[106.662, 10.78]` | Expect match |
Just-outside west edge | `[106.658, 10.78]` | Expect no match |
Just-inside southwest corner | `[106.662, 10.742]` | Expect match |
Just-outside southwest corner | `[106.658, 10.738]` | Expect no match |
Exactly-on-edge | `[106.66, 10.78]` | Observe actual result, compare with policy |
Exactly-on-vertex | `[106.66, 10.74]` | Observe actual result, compare with policy |
Just outside edge by tiny epsilon | `[106.65999999, 10.78]` | Precision stress test, not a brittle acceptance gate |

The "just-inside/outside" points in the example sit **a finite distance** from the edge to avoid round-off noise during testing. Points separated by tiny fractions of a degree are precision tests, not mandatory stability tests across every environment.

### 8.2. Separating Geometry Decisions from Business Decisions

For example, a business rule might specify:

~~~text
P clearly inside region  -> ACCEPT
P clearly outside region -> REJECT
P on or within 15 meters of boundary -> REVIEW / REQUEST_PRECISE_LOCATION
~~~

MongoDB `$geoWithin` helps find geometric candidates; it does not know what "within 15 meters of the boundary" is, does not read GPS accuracy, and does not issue business certifications. Near-boundary classification must use proper metric distance math and uncertainty metadata.

### 8.3. Shared Borders Between Two Regions

Two adjacent polygons can touch along an edge. If business rules require **a point belongs to at most one region**, independent geospatial matches cannot choose the winner. You need deterministic tie-breaking:

- Prefer the region with higher priority.
- Prefer the region registered earlier by an immutable business key.
- Or classify near-boundary points as ambiguous and request extra verification.

Never rely on unsorted MongoDB cursor return order as a tie-breaking policy.

## 9. Validating Input Coordinate Data

An endpoint receiving locations from a mobile app should distinguish:

1. **Syntactically valid data:** two numbers, valid GeoJSON structure.
2. **Valid coordinate bounds:** finite longitude/latitude within valid ranges.
3. **Valid polygon geometry:** closed rings, non-self-intersecting, valid holes, valid winding/CRS.
4. **Business-valid data:** region belongs to the right tenant, is active, and is approved.
5. **Trustworthy location:** location source and accuracy satisfy policy.

Checks covering only (1) and (2) do not guarantee (3)–(5).

### 9.1. Avoiding Latitude/Longitude Swaps

Do not use constructors with ambiguous naming:

~~~java
// Use clear names before building GeoJSON:
double longitude = 106.70;
double latitude = 10.78;

GeoJsonPoint point = new GeoJsonPoint(longitude, latitude);
~~~

`GeoJsonPoint` is imported from `org.springframework.data.mongodb.core.geo.GeoJsonPoint`. An input API naming fields `lat`/`lng` must explicitly convert before constructing GeoJSON rather than guessing another library's parameter order.

### 9.2. Rejecting `NaN`, `Infinity`, and Out-of-Range Values

~~~java
public static void validateCoordinates(
        double longitude, double latitude) {
    if (!Double.isFinite(longitude)
            || !Double.isFinite(latitude)
            || longitude < -180 || longitude > 180
            || latitude < -90 || latitude > 90) {
        throw new IllegalArgumentException("Invalid coordinates");
    }
}
~~~

This validates one coordinate pair; when ingesting a Polygon, run it on **every position in every ring**. While certain formats or extended CRSs carry other semantics, examples in this lesson use GeoJSON longitude–latitude within these ranges.

### 9.3. Do Not Auto-Fix Errors by Swapping Two Numbers

A pair `[10.78, 106.70]` violates latitude bounds if read as `[lon,lat]`. Never silently swap the two numbers and continue as if the source were valid: many places worldwide have both numbers inside valid bounds, so an automatic swap heuristic can **corrupt valid data**.

Instead, define explicit input API contracts and validation; if an upstream sends `(latitude, longitude)`, convert inside the dedicated adapter for that upstream.

## 10. Antimeridian, Poles, and Large Polygons

The ±180° meridian (antimeridian) is where longitude flips from near +180° to near −180° even though two places sit right next to each other on the globe.

Two example positions:

~~~text
P1 = [ 179.9, 10.0]
P2 = [-179.9, 10.0]
~~~

Geographically they lie on adjacent sides of the antimeridian, yet on a naive number line the arithmetic gap is 359.8°. A Polygon or bounding box built from `minLongitude=-179.9` to `maxLongitude=179.9` can span **almost the entire Earth** instead of the intended narrow strip.

### 10.1. Workflow When a Region Crosses ±180°

1. Confirm the source data actually crosses the antimeridian.
2. Use a GIS-standardized GeoJSON/MultiPolygon representation for this case, or split the region cleanly across both sides.
3. Never take naive `min/max longitude` and treat it as the region.
4. Test points on both sides (`179.9` and `-179.9`), a point at `0°`, and points near edges.
5. Check MongoDB's winding/spherical area interpretation on that exact geometry.
6. Verify the `2dsphere` index and queries against the production server/version.

Do not adopt a rule of thumb like "connecting +179 to −179 always takes the short edge" for every geometry. On spherical polygons and large loops, results depend on interpretation rules and ring winding.

### 10.2. Polygons Larger Than a Hemisphere and Winding

MongoDB has specific rules for large-area GeoJSON polygons, winding, and in certain cases supports the custom `strictwinding` CRS. Do not slap non-standard CRSs onto every Polygon: it is a specialized mechanism requiring exact syntax, server support, and tests.

If data spans multiple continents or nears the poles, read MongoDB docs for your exact version and use geometries prepared by a specialized GIS tool. **This lesson does not use a hemisphere-spanning region as a generic acceptance test** because multiple interpretations apply.

### 10.3. Near the Poles

Near ±90° latitude, meridians converge. A polygon drawn as a rectangle on a 2D map can form a spherical shape quite different from what appears on screen. Tests must use real spherical geometry, not screenshots from a Web Mercator map.

## 11. Spring Data MongoDB Entity for Locations

We store pickup points in collection `geo_outlets` as GeoJSON Points.

**GeoOutlet.java**

~~~java
package com.example.geo;

import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexed;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "geo_outlets")
public record GeoOutlet(
        @MongoId(FieldType.STRING) String id,
        String tenantId,
        String status,
        String name,
        @GeoSpatialIndexed(type = GeoSpatialIndexType.GEO_2DSPHERE)
        GeoJsonPoint location) {
}
~~~

An instance:

~~~java
GeoOutlet outlet = new GeoOutlet(
        "store-101",
        "tenant-a",
        "ACTIVE",
        "Pickup Point A",
        new GeoJsonPoint(106.7000, 10.7800));
~~~

Spring Data's MongoDB mapping converter persists `GeoJsonPoint` as a GeoJSON `Point` with a `coordinates` array through standard persistence operations.

### 11.1. `@GeoSpatialIndexed` Is Not a Schema Constraint

This annotation expresses an intended index to Spring Data; whether **the index actually exists in MongoDB** depends on your index provisioning mechanism. Never assume "annotated in Java" means "indexed in production".

### 11.2. `@MongoId` Keeps `_id` as `String`

With ID `"store-101"`, the example uses `@MongoId(FieldType.STRING)` to avoid ambiguity with `ObjectId` conversion. When writing raw BSON queries, use String `_id` per this schema; when using typed Spring Data `Criteria.where("id")`, mapping resolves it to `_id` automatically.

### 11.3. Designing a Separate Region Entity

When regions are persisted:

~~~json
{
  "_id": "area-a1",
  "tenantId": "tenant-a",
  "status": "ACTIVE",
  "geometry": {
    "type": "Polygon",
    "coordinates": [
      [
        [106.66, 10.74],
        [106.74, 10.74],
        [106.74, 10.82],
        [106.66, 10.82],
        [106.66, 10.74]
      ]
    ]
  }
}
~~~

Do not overload a Point store's `location` field with a region's `geometry` field without clear typing. The two collections can use different index/query strategies, and each geometry needs topology validation suited to its role.

## 12. `MongoTemplate` Queries Using Explicit BSON

For complex Polygon queries (especially with holes or MultiPolygons), you can express `$geoWithin` via `BasicQuery` with explicit BSON. This avoids assuming every geometry variant has an identical convenience method across every Spring Data line.

**GeoAreaService.java**

~~~java
package com.example.geo;

import java.util.List;
import java.util.Objects;
import org.bson.Document;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.BasicQuery;
import org.springframework.stereotype.Service;

@Service
public class GeoAreaService {

    private final MongoTemplate mongo;

    public GeoAreaService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public List<GeoOutlet> findInside(
            String authenticatedTenantId, Document inputPolygon) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()) {
            throw new IllegalArgumentException("Invalid tenant");
        }

        Document polygon = validatedPolygon(inputPolygon);

        Document geometryFilter = new Document(
                "$geoWithin",
                new Document("$geometry", polygon));

        Document bsonQuery = new Document(
                "tenantId", authenticatedTenantId)
                .append("status", "ACTIVE")
                .append("location", geometryFilter);

        BasicQuery query = new BasicQuery(bsonQuery);
        query.with(Sort.by(Sort.Direction.ASC, "id"));
        query.limit(100);

        return mongo.find(query, GeoOutlet.class);
    }

    public static Document rectangle() {
        return Document.parse("""
            {
              "type": "Polygon",
              "coordinates": [[
                [106.66, 10.74],
                [106.74, 10.74],
                [106.74, 10.82],
                [106.66, 10.82],
                [106.66, 10.74]
              ]]
            }
            """);
    }

    /**
     * Only verifies structure/ranges/ring closure.
     * DOES NOT replace full GIS topology validation.
     */
    public static Document validatedPolygon(Document candidate) {
        if (candidate == null
                || !"Polygon".equals(candidate.getString("type"))
                || !(candidate.get("coordinates") instanceof List<?> rings)
                || rings.isEmpty() || rings.size() > 8) {
            throw new IllegalArgumentException(
                    "Geometry must be a Polygon with 1..8 rings");
        }

        for (Object ringObject : rings) {
            if (!(ringObject instanceof List<?> positions)
                    || positions.size() < 4
                    || positions.size() > 512) {
                throw new IllegalArgumentException("Invalid ring");
            }
            for (Object positionObject : positions) {
                if (!(positionObject instanceof List<?> position)
                        || position.size() != 2
                        || !(position.get(0) instanceof Number lonNumber)
                        || !(position.get(1) instanceof Number latNumber)) {
                    throw new IllegalArgumentException(
                            "Coordinates must be [longitude, latitude]");
                }
                double lon = lonNumber.doubleValue();
                double lat = latNumber.doubleValue();
                if (!Double.isFinite(lon) || !Double.isFinite(lat)
                        || lon < -180 || lon > 180
                        || lat < -90 || lat > 90) {
                    throw new IllegalArgumentException(
                            "Coordinates out of range");
                }
            }
            if (!Objects.equals(
                    positions.get(0),
                    positions.get(positions.size() - 1))) {
                throw new IllegalArgumentException(
                        "Ring is not closed");
            }
        }

        // Do not keep arbitrary client-supplied keys (e.g. $-operators).
        // Copy only the two validated geometry properties.
        return new Document("type", "Polygon")
                .append("coordinates", rings);
    }
}
~~~

### 12.1. What Is Already Protected?

- `tenantId` comes from an **authenticated/authorized** parameter at the application boundary.
- `status = ACTIVE` avoids returning closed outlets.
- `location` is queried via `$geoWithin/$geometry` in the same BSON filter.
- Input geometry only allows Polygon, capped at 8 rings and 512 positions/ring in this example.
- Each position has two finite numbers with longitude/latitude within valid ranges.
- Rings must have matching start/end positions.
- The query caps results at 100 and sorts deterministically by ID.

**What is not yet protected:** full geometric topology, valid holes, winding, antimeridian, real tenant authorization enforcement, and GPS accuracy. Those belong to other validation/security layers.

### 12.2. Never Pass Client `$-Operators` Directly into Queries

An API accepting raw JSON and inserting that entire `Document` into a query can accidentally permit unwanted operators. The example above only accepts `type` and `coordinates`, then builds `$geoWithin` itself. Still, for large/complex inputs, also cap HTTP payload size, JSON depth, total vertex count, and parsing/validation CPU time.

### 12.3. Do Not Use a `Document` Parser as "Topology Validation"

`Document.parse(...)` only parses valid JSON/BSON. A self-intersecting yet syntactically valid Polygon will parse cleanly. Checks such as "holes inside outer ring", "non-self-intersecting rings", and antimeridian rules must be handled by proper geometry validation before accepting new regions.

### 12.4. The Result Type Does Not Tell How Far a Point Is from the Boundary

`findInside` returns `List<GeoOutlet>` matching the Polygon. It does not return:

- Shortest distance to the boundary.
- GPS coordinate accuracy.
- Percentage of overlapping area.
- Whether a point on an edge counts as inside or outside.

When those values are needed, add dedicated geodesic/topological measurements rather than inferring them from matched document counts.

## 13. Spring Data `Criteria` and `GeoJsonPolygon`

For simple polygons, Spring Data provides geometric classes to write typed queries.

~~~java
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.core.geo.GeoJsonPolygon;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

GeoJsonPolygon polygon = new GeoJsonPolygon(
        new Point(106.66, 10.74),
        new Point(106.74, 10.74),
        new Point(106.74, 10.82),
        new Point(106.66, 10.82),
        new Point(106.66, 10.74));

Query query = Query.query(
        Criteria.where("tenantId").is("tenant-a")
                .and("status").is("ACTIVE")
                .and("location").within(polygon));

List<GeoOutlet> inside = mongo.find(
        query, GeoOutlet.class);
~~~

This demonstrates usage with `GeoJsonPolygon`, `Criteria.within(...)`, and `MongoTemplate` on supported APIs. `mongo` is the service's `MongoTemplate` field. Points begin with longitude then latitude—**not** `Point(latitude, longitude)`.

### 13.1. When to Use Typed Geometry vs BSON

| Situation | Choice |
|---|---|
Simple polygon, explicit Java types | `GeoJsonPolygon` + `Criteria.within` |
Dynamic geometry with holes, MultiPolygon, or exchanged between GIS systems | Validated BSON `$geometry` or version-verified API shapes |
Want exact correspondence to MongoDB operators | Raw query/BSON makes comparing with `mongosh` straightforward |
Queries with multiple business predicates | `Criteria`/`Query` or validated `BasicQuery` |
Adding support for new geometry types | Add type whitelist, validation, and per-geometry tests |

Do not treat typed APIs and raw BSON as having different semantics if they emit **the exact same BSON query**. The differences lie mainly in expressiveness, mapping, and input validation at the Spring layer.

### 13.2. Field Names in `Criteria` vs BSON

In `Criteria.where("location")`, `"location"` is the Java property on `GeoOutlet` and also the BSON field in the example schema. If the entity declares `@Field("geo_location")`, typed Spring Data mapping translates property `location` to BSON `geo_location`. With raw driver `Document`s, you must use the **actual BSON name**.

Tests inspecting raw BSON catch mapping mismatches before you waste time debugging geospatial math.

## 14. Reversed Query Direction: Finding Regions Containing a Point

Suppose MongoDB stores `service_areas`, each document having `geometry: Polygon`. An input Point needs to be matched against stored regions.

~~~javascript
db.service_areas.find({
  tenantId: "tenant-a",
  status: "ACTIVE",
  geometry: {
    $geoIntersects: {
      $geometry: {
        type: "Point",
        coordinates: [106.70, 10.78]
      }
    }
  }
});
~~~

Idea: does the region's geometry intersect the input Point? Queries of this type can leverage a `2dsphere` index on `service_areas.geometry` when properly provisioned:

~~~javascript
db.service_areas.createIndex(
  { tenantId: 1, geometry: "2dsphere" },
  { name: "idx_area_tenant_geometry" }
);
~~~

### 14.1. Do Not Confuse Operators When Flipping Data Direction

Two distinct questions:

1. "List `GeoOutlet.location` Points inside an input `Polygon`."
2. "List `ServiceArea.geometry` Polygons containing/intersecting an input `Point`."

They differ in query field direction and do not necessarily use the same operator. When regions have holes, boundaries, or MultiPolygons, test according to the real goal: **selecting points** vs **selecting regions**.

### 14.2. Multiple Regions Matching One Point

A point can intersect multiple regions belonging to the same tenant. If the API needs a single region, enforce:

~~~text
match zones
  -> apply business priority
  -> tie-breaker stable zone ID
  -> return selected zone + reason
~~~

Never rely on default MongoDB cursor order as priority. If policy forbids overlapping regions, detect overlaps when creating/updating polygons rather than only at query time.

## 15. Security and Region Validity

A geofence is normally used to **evaluate business rules**, not as an authentication mechanism. Essential invariants:

- `tenantId` comes from identity/access policy, never trusting arbitrary client-supplied tenants.
- Regions have `ACTIVE`/`DRAFT`/`RETIRED` status and effective timestamps if required.
- When a region changes after an order is placed, store `regionVersion`/snapshot or a business decision ID for auditing.
- User-submitted coordinates can be spoofed; a geospatial match does not prove physical presence.
- When region matching governs fees, taxes, or permissions, log input geometry version, timestamp, policy, and decision reason while avoiding logging unnecessary sensitive location data.

### 15.1. Geometrically Correct Queries Can Still Be Business-Wrong

Suppose a `tenant-b` store lies inside `tenant-a`'s Polygon. If the query contains `location: {$geoWithin: ...}` without `tenantId`, the geometry is right yet **leaks another tenant's data**.

Similarly, an `INACTIVE` store can still sit inside the Polygon; omitting the `status` filter lets the API suggest a closed outlet.

### 15.2. Never Trust Unbounded Input Polygons

A request with millions of vertices can spike CPU, memory, and server load. Enforce limits:

~~~text
request size
  + geometry type whitelist
  + max rings/polygons
  + max points
  + topological validity check
  + tenant ownership
  + query timeout/limit
~~~

The checks in `validatedPolygon` are only **minimal structural validation**; in production, normalize geometries upfront, cap complexity, and optionally cache validated regions.

## 16. Designing a Coordinate Matrix and Test Expectations

To avoid writing tests with a few convenient points, define **location groups** and expectations before writing Java. For the test region:

| Group | Case ID | Coordinate `[lon,lat]` | Expectation |
|---|---|---|---|
Clearly inside | `inside` | `[106.700,10.780]` | Match |
Clearly outside | `outside` | `[106.760,10.780]` | No match |
Just inside west edge | `west-in` | `[106.662,10.780]` | Match |
Just outside west edge | `west-out` | `[106.658,10.780]` | No match |
Just inside southwest corner | `corner-in` | `[106.662,10.742]` | Match |
Just outside southwest corner | `corner-out` | `[106.658,10.738]` | No match |
On west edge | `edge` | `[106.660,10.780]` | Observe, do not hard-assert |
At southwest vertex | `vertex` | `[106.660,10.740]` | Observe, do not hard-assert |
Belongs to another tenant | `foreign-tenant` | `[106.700,10.780]` | Excluded when filtering tenant-a |
INACTIVE inside region | `inactive` | `[106.700,10.780]` | Excluded when filtering ACTIVE |
Inside hole | `hole-in` | `[106.699,10.780]` | No match for Polygon with hole |
Outside hole, inside outer | `hole-out` | `[106.675,10.780]` | Match for Polygon with hole |

`inside` lies inside the simple Polygon, yet also falls **inside the hole** once the hole from section 6 is added. Never expect the same point to match two differently structured regions.

### 16.1. Test Clearly Inside/Outside Before Testing Exact Boundaries

For a small, topologically valid polygon:

~~~text
Clearly inside             -> true
Clearly outside            -> false
Just inside                -> true
Just outside               -> false
Inside hole                -> false
Outside hole, inside outer -> true
Wrong tenant               -> absent
INACTIVE                   -> absent
~~~

These assertions are far more stable than forcing points **exactly on an edge** to produce a behavior undefined by the system contract.

### 16.2. Near-Boundary Tests Require a Business Policy

When a product needs an uncertain zone, define:

~~~text
raw MongoDB geometry match
    + geodesic distance to boundary
    + GPS error radius
    + region/policy version
    -> INSIDE / OUTSIDE / UNCERTAIN
~~~

MongoDB `$geoWithin` does not compute shortest distance to the boundary or GPS error. A "within 15 meters of boundary" policy needs dedicated metric distance math and rules; never infer it from a boolean match.

### 16.3. Do Not Hardcode Inclusion on Exact Boundaries Unverified

The following test makes an unsafe assumption unless guaranteed by contract:

~~~java
// Avoid making this a universal default across every GeoJSON/driver:
assertThat(ids).contains("edge");
~~~

Log edge/vertex outcomes separately in test reports for your exact MongoDB version; keep hard assertions on points **clearly separated from the boundary**. If the product requires exact boundary handling, implement a dedicated boundary classifier with its own tests.

## 17. Integration Testing on Real MongoDB

Mocking `MongoTemplate` cannot verify how the server interprets GeoJSON Polygons, holes, and spherical indexes. You need real test MongoDB (e.g., Testcontainers or an isolated test server).

Spring Boot `@DataMongoTest` configures a test slice, **without starting a MongoDB server itself**. Provide a URI pointing to an isolated test MongoDB beforehand. The `remove`/`insert` calls below must never run against production.

### 17.1. Seeding Points with Clear Expectations

**GeoAreaServiceIntegrationTest.java**

~~~java
package com.example.geo;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
@Import(GeoAreaService.class)
class GeoAreaServiceIntegrationTest {

    @Autowired MongoTemplate mongo;
    @Autowired GeoAreaService service;

    private GeoOutlet outlet(
            String id, String tenant,
            String status, double lon, double lat) {
        return new GeoOutlet(
                id, tenant, status, "Point " + id,
                new GeoJsonPoint(lon, lat));
    }

    @BeforeEach
    void seed() {
        // Operate only on an isolated test database.
        mongo.remove(new Query(), GeoOutlet.class);

        // Create the index explicitly instead of relying on auto-index.
        mongo.getCollection("geo_outlets")
                .createIndex(new Document("location", "2dsphere"));

        List<GeoOutlet> fixtures = List.of(
                outlet("inside", "tenant-a", "ACTIVE",
                        106.700, 10.780),
                outlet("outside", "tenant-a", "ACTIVE",
                        106.760, 10.780),
                outlet("west-in", "tenant-a", "ACTIVE",
                        106.662, 10.780),
                outlet("west-out", "tenant-a", "ACTIVE",
                        106.658, 10.780),
                outlet("corner-in", "tenant-a", "ACTIVE",
                        106.662, 10.742),
                outlet("corner-out", "tenant-a", "ACTIVE",
                        106.658, 10.738),
                outlet("edge", "tenant-a", "ACTIVE",
                        106.660, 10.780),
                outlet("vertex", "tenant-a", "ACTIVE",
                        106.660, 10.740),
                outlet("foreign-tenant", "tenant-b", "ACTIVE",
                        106.700, 10.780),
                outlet("inactive", "tenant-a", "INACTIVE",
                        106.700, 10.780),
                outlet("hole-out", "tenant-a", "ACTIVE",
                        106.675, 10.780),
                outlet("hole-in", "tenant-a", "ACTIVE",
                        106.699, 10.780)
        );

        for (GeoOutlet point : fixtures) {
            mongo.insert(point);
        }
    }

    private Set<String> insideIds(Document polygon) {
        return service.findInside("tenant-a", polygon)
                .stream()
                .map(GeoOutlet::id)
                .collect(Collectors.toSet());
    }

    @Test
    void clearlyInsideOutsideAndNearEdgeAreClassified() {
        Set<String> ids = insideIds(GeoAreaService.rectangle());

        assertThat(ids)
                .contains("inside", "west-in", "corner-in")
                .doesNotContain("outside", "west-out", "corner-out");
    }

    @Test
    void tenantAndStatusAreFilteredWithGeometry() {
        Set<String> ids = insideIds(GeoAreaService.rectangle());
        assertThat(ids)
                .contains("inside")
                .doesNotContain("foreign-tenant", "inactive");
    }

    @Test
    void exactEdgeAndVertexAreObservedNotAssumed() {
        Set<String> ids = insideIds(GeoAreaService.rectangle());

        assertThat(ids).contains("inside");
        assertThat(ids).doesNotContain("outside");

        // Diagnostic for the test environment's MongoDB version.
        System.out.printf(
                "GeoJSON boundary outcome: edge=%s, vertex=%s%n",
                ids.contains("edge"),
                ids.contains("vertex"));
    }

    @Test
    void aHoleExcludesItsInterior() {
        Document polygonWithHole = Document.parse("""
            {
              "type": "Polygon",
              "coordinates": [
                [
                  [106.66, 10.74],
                  [106.74, 10.74],
                  [106.74, 10.82],
                  [106.66, 10.82],
                  [106.66, 10.74]
                ],
                [
                  [106.69, 10.77],
                  [106.69, 10.79],
                  [106.71, 10.79],
                  [106.71, 10.77],
                  [106.69, 10.77]
                ]
              ]
            }
            """);

        Set<String> ids = insideIds(polygonWithHole);
        assertThat(ids)
                .contains("hole-out", "west-in")
                .doesNotContain("inside", "hole-in", "outside");
    }

    @Test
    void invalidLatitudeAndOpenRingAreRejected() {
        Document badLatitude = Document.parse("""
            {
              "type": "Polygon",
              "coordinates": [[
                [106.66, 10.74],
                [106.74, 10.74],
                [106.74, 106.82],
                [106.66, 10.74]
              ]]
            }
            """);

        assertThatThrownBy(() ->
                GeoAreaService.validatedPolygon(badLatitude))
                .isInstanceOf(IllegalArgumentException.class);

        Document openRing = Document.parse("""
            {
              "type": "Polygon",
              "coordinates": [[
                [106.66, 10.74],
                [106.74, 10.74],
                [106.74, 10.82],
                [106.66, 10.82]
              ]]
            }
            """);

        assertThatThrownBy(() ->
                GeoAreaService.validatedPolygon(openRing))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

### 17.2. Reading the Test Meaning Correctly

`exactEdgeAndVertexAreObservedNotAssumed` **does not claim** the server always includes or excludes exact boundary points; it is a diagnostic showing your version's behavior. If the product needs decisions based on boundary tolerance, test the policy in a separate layer with acceptance tests.

### 17.3. Separating Topology/Geometry Tests from Business Tests

Geospatial tests prove MongoDB executes queries properly over fixtures. Policy tests prove near-boundary cases are classified per business rules. Never let one test carry ambiguous assumptions for both.

### 17.4. The Database Must Be Isolated

`mongo.remove(new Query(), GeoOutlet.class)` wipes the entire target collection. Never run against production or shared databases. If tests run in parallel, use separate collections/databases so tests do not wipe each other's fixtures.

## 18. Verifying Raw BSON and Indexes on Test MongoDB

When `$geoWithin` unexpectedly returns empty, verify MongoDB actually stored a **GeoJSON Point** instead of guessing the geometry is wrong.

### 18.1. Checking Longitude/Latitude Order in the Raw Document

Add this method to `GeoAreaServiceIntegrationTest`:

~~~java
@Test
void mappedLocationIsGeoJsonWithLongitudeFirst() {
    Document raw = mongo.getCollection("geo_outlets")
            .find(new Document("_id", "inside"))
            .first();

    assertThat(raw).isNotNull();
    Document location = raw.get("location", Document.class);
    assertThat(location).isNotNull();
    assertThat(location.getString("type")).isEqualTo("Point");

    List<?> coordinates =
            location.getList("coordinates", Object.class);
    assertThat(coordinates).hasSize(2);

    assertThat(((Number) coordinates.get(0)).doubleValue())
            .isEqualTo(106.7);
    assertThat(((Number) coordinates.get(1)).doubleValue())
            .isEqualTo(10.78);
}
~~~

If `coordinates[0] = 10.78` and `coordinates[1] = 106.7`, the data is swapped and latitude is invalid; fix input data/mapping before debugging spatial operators.

### 18.2. Verifying the Actual Index

~~~java
@Test
void twoDSphereIndexExists() {
    List<Document> indexes = mongo
            .getCollection("geo_outlets")
            .listIndexes()
            .into(new java.util.ArrayList<>());

    assertThat(indexes).anySatisfy(index -> {
        Document key = index.get("key", Document.class);
        assertThat(key).isNotNull();
        assertThat(key.getString("location"))
                .isEqualTo("2dsphere");
    });
}
~~~

This test only verifies **index metadata** has key `location: "2dsphere"`. It does not prove the query planner picks the index for every query. Use `explain("executionStats")` on representative data volumes.

### 18.3. Cross-Checking BSON Queries in `mongosh`

~~~javascript
db.geo_outlets.find({
  tenantId: "tenant-a",
  status: "ACTIVE",
  location: {
    $geoWithin: {
      $geometry: {
        type: "Polygon",
        coordinates: [[
          [106.66, 10.74],
          [106.74, 10.74],
          [106.74, 10.82],
          [106.66, 10.82],
          [106.66, 10.74]
        ]]
      }
    }
  }
});
~~~

If the raw query returns points while the Spring Data query does not, check:

- Whether `MongoTemplate` is connected to the right database/collection.
- Whether `@Document(collection = "geo_outlets")` on the entity matches.
- Whether `@Field`/`@MongoId` and converters map fields properly.
- Whether tenant/status values match.
- Whether code is passing a Polygon versus another geometry.
- JSON number precision and ring closure.

## 19. Testing `MultiPolygon` and Reversed Query Direction

`GeoAreaService.validatedPolygon` in section 12 accepts only `Polygon` to constrain the endpoint input. To test `MultiPolygon`, run an internal BSON query on isolated fixtures without **blindly exposing** it on the public API.

### 19.1. `MultiPolygon` with Two Disjoint Parts

~~~java
import org.springframework.data.mongodb.core.query.BasicQuery;

Document multiPolygon = Document.parse("""
    {
      "type": "MultiPolygon",
      "coordinates": [
        [[
          [106.66, 10.74],
          [106.74, 10.74],
          [106.74, 10.82],
          [106.66, 10.82],
          [106.66, 10.74]
        ]],
        [[
          [106.80, 10.74],
          [106.84, 10.74],
          [106.84, 10.78],
          [106.80, 10.78],
          [106.80, 10.74]
        ]]
      ]
    }
    """);

// Seed an extra point in the second cluster and in the gap between clusters
// BEFORE querying.
mongo.insert(outlet("second-zone", "tenant-a",
        "ACTIVE", 106.82, 10.76));
mongo.insert(outlet("between-zones", "tenant-a",
        "ACTIVE", 106.77, 10.76));

Document filter = new Document("tenantId", "tenant-a")
        .append("status", "ACTIVE")
        .append("location", new Document(
                "$geoWithin",
                new Document("$geometry", multiPolygon)));

List<GeoOutlet> matches = mongo.find(
        new BasicQuery(filter), GeoOutlet.class);

Set<String> ids = matches.stream()
        .map(GeoOutlet::id)
        .collect(Collectors.toSet());

assertThat(ids).contains("second-zone");
assertThat(ids).doesNotContain("between-zones");
~~~

This snippet is a fragment inside `GeoAreaServiceIntegrationTest`, using `mongo`, the `outlet` helper, and matching imports. **Seed before querying** so `matches` covers both clusters. If extracting into a separate test method, import `BasicQuery` and ensure the test collection/database is isolated.

### 19.2. Testing Regions Containing a Point

When a collection stores Polygons and receives a Point query, the typical matching direction is:

~~~javascript
db.service_areas.find({
  tenantId: "tenant-a",
  status: "ACTIVE",
  geometry: {
    $geoIntersects: {
      $geometry: {
        type: "Point",
        coordinates: [106.70, 10.78]
      }
    }
  }
});
~~~

You must have a suitable geometry/`2dsphere` index on `service_areas.geometry` and test cases where points fall inside holes, overlapping regions, or right on boundaries.

### 19.3. One Point Can Belong to Two Regions

If two zones overlap, the query can return **two zone documents**. Business policy must determine:

~~~text
matched zones: [zone-a, zone-b]
select by: active + priority DESC + stable zoneId ASC
~~~

Never pick the cursor's first element by default. If regions are required not to overlap, validate topology before publishing new regions.

### 19.4. Do Not Treat a Missing Location as Verified Outside

A document lacking `location` is skipped by geospatial predicates/indexes. Yet it is not "verified coordinates lying outside the region".

An API should distinguish:

- `INSIDE_REGION`: valid coordinates matched.
- `OUTSIDE_REGION`: valid coordinates did not match.
- `MISSING_LOCATION`: no coordinates available yet.
- `INVALID_LOCATION`: invalid or rejected coordinates.
- `UNCERTAIN`: accuracy/tolerance leaves the decision inconclusive.

A `$geoWithin` query only returns matched documents; it does not directly tell why every remaining document was excluded.

## 20. Distance to Boundary and Testing with GPS Error

If the product needs to know "location is within 15 m of the boundary", never use this formula:

~~~java
// Anti-pattern: wrong across latitudes and for slanted edges/holes.
boolean isNearBoundary =
        Math.abs(longitude - westEdgeLongitude) < 0.00015;
~~~

This measures longitude difference in **degrees**, not shortest distance to the entire boundary in **meters**. It ignores slanted edges, hole rings, polar regions, and coordinate reference systems.

### 20.1. Three-State Policy

| Verified Condition | Decision |
|---|---|
Clearly inside region and farther than tolerance from all borders | `INSIDE` |
Clearly outside region and farther than tolerance from all borders | `OUTSIDE` |
Point near border or location error radius too large | `UNCERTAIN` |

MongoDB `$geoWithin` selects geometric candidates. Shortest distance to the boundary is not returned by `$geoWithin`. To classify `UNCERTAIN`, you need:

1. Geodesic/geometric distance math matching the CRS and Polygon.
2. Location accuracy radius, timestamp, and source.
3. Metric tolerance policy and hole-handling rules.
4. Region version and policy version.
5. Response strategy when evidence is insufficient: reject, re-verify, or escalate to manual review.

### 20.2. Separating Policy Unit Tests from MongoDB Integration Tests

Sample test data for the business classifier:

~~~text
Given:
  distanceToBoundaryMeters = 7
  accuracyMeters = 10
  toleranceMeters = 15

When:
  apply policy version v3

Then:
  UNCERTAIN
~~~

In policy unit tests, pass precomputed distance inputs from the geometry service. Dedicated GIS integration tests verify the distance algorithm. Never assume `$geoWithin` directly provides `distanceToBoundaryMeters`.

### 20.3. Precision Across Serialization/Deserialization

A point right on a boundary can flip results when formatting/rounding differs across mobile JSON, Spring APIs, storage, and GIS renderers. Check:

- JSON coordinate round-tripping.
- Parsing into `double` or the agreed numeric type.
- How `GeoJsonPoint` stores BSON.
- Exporting points to UI and receiving them back.
- Real device accuracy; never fabricate precision using extra decimal digits.

Never treat a point displayed on a map image as golden truth if the image uses a different projection and rounding than GeoJSON.

### 20.4. Error Does Not Imply Fraud

GPS drift or a near-boundary point is an **uncertain state**, not proof that the client spoofed coordinates. If a security system needs anti-spoofing, implement independent verification and proper location-data/privacy policies.

## 21. Performance: `explain`, Indexes, and Result Caps

A geometrically accurate query can still be slow when outlet counts are large or polygons are complex.

### 21.1. Interpreting `executionStats` on Representative Queries

~~~javascript
db.geo_outlets.find({
  tenantId: "tenant-a",
  status: "ACTIVE",
  location: {
    $geoWithin: {
      $geometry: {
        type: "Polygon",
        coordinates: [[
          [106.66, 10.74],
          [106.74, 10.74],
          [106.74, 10.82],
          [106.66, 10.82],
          [106.66, 10.74]
        ]]
      }
    }
  }
}).limit(100).explain("executionStats");
~~~

Inspect:

- `queryPlanner.winningPlan` and the geospatial index/stages used.
- `totalKeysExamined` and `totalDocsExamined`.
- `nReturned`.
- `executionTimeMillis` (on representative systems/load tests).
- Index build/write overhead, region count, and vertex counts.

Do not invent numbers like "10x faster" without benchmarking. A region covering nearly all data will still return many documents even with an index. A complex Polygon with thousands of vertices incurs higher computation cost than a simple shape.

### 21.2. `limit` and `sort` Have Distinct Roles

`query.limit(100)` in `GeoAreaService` caps returned documents; it does not guarantee the "best" 100 locations unless a sort criterion is defined. The lesson uses `id ASC` for deterministic ordering on relatively static sets. If you need "closest to customer", compute distances and sort separately; `$geoWithin` does not auto-sort by distance.

### 21.3. Keyset Paging and Concurrent Updates

If tens of thousands of stores lie inside a region, do not load all of them into a `List`. You can use keyset cursors on `_id` or another stable sort key, yet when documents move, appear, or disappear concurrently, pages do not automatically form an immutable snapshot.

For reports requiring snapshot consistency, configure read concern/sessions/transactions or batch versioning as required. Never expect `sort(id)` alone to give snapshot consistency.

### 21.4. Compound Indexes Must Be Benchmarked

The index:

~~~javascript
{ tenantId: 1, status: 1, location: "2dsphere" }
~~~

can fit queries filtering tenant, status, and geometry, but is not guaranteed to beat `{location:"2dsphere"}` on every distribution. Test across large/small tenants, varying `ACTIVE`/`INACTIVE` ratios, and small/large Polygons before deciding the production strategy.

## 22. Common Errors in Region Matching and Boundary Testing

| Symptom or Mistake | Possible Cause | Inspection / Fix |
|---|---|---|
Point inside region on map but query misses | Swapped lat/lon | Check BSON `coordinates[0]=longitude` |
MongoDB rejects coordinates | Latitude outside ±90° or invalid number | Validate every position |
Polygon matches nothing | Missing ring nesting level or unclosed ring | Check `Polygon.coordinates` |
Region flips to cover the rest of the globe | Winding or oversized polygon | Normalize geometry, test spherical semantics |
Bowtie-shaped region | Self-intersecting ring | Run GIS topology validation before ingest |
Point inside hole still matches | Hole stored as separate polygon | Place hole as next ring of the same Polygon |
MultiPolygon misses second part | Wrong array nesting level | Check `MultiPolygon.coordinates` |
Antimeridian region covers almost the whole world | Wrong min/max longitude | Normalize/split regions, test ±180° |
Shape on Web Mercator differs from GeoJSON | Confused projection with geometry | Transform CRS and inspect raw data |
Point on edge returns unexpected result | Boundary semantics and precision | Avoid hardcoding without policy/tests |
Two regions both match a boundary point | Shared border/overlap | Stable priority or `UNCERTAIN` |
Near-edge coordinates flip pass/fail | Precision/rounding, GPS accuracy | Metric distance to edge and tolerance |
`$near` returns store close by yet outside zone | Nearest is not within | Use `$geoWithin` with Polygon |
Bounding box matches but polygon does not | Concave shape / hole | Run real point-in-polygon check |
Query returns another tenant's stores | Missing tenant filter | Tenant from auth context in BSON query |
Query returns `INACTIVE` points | Missing status predicate | Filter status in the database |
`@GeoSpatialIndexed` present yet index missing | Auto-index disabled / unprovisioned | List indexes and run explicit migrations |
Index exists yet query stays slow | Huge region, unindexed filter, complex polygon | `explain("executionStats")`/benchmark |
`BasicQuery` differs from typed `Criteria` | Different BSON query / field mapping | Safely log command / compare raw BSON |
Parsed valid JSON yet polygon is invalid | Parsing skips topology checks | GIS geometry validator |
API accepts Polygons with millions of vertices | Missing limits / DoS guard | Cap payload, rings, vertices, timeout |
Mockito test passes, real MongoDB differs | Mock lacks spherical engine | Integration tests with `2dsphere` |
Boundary test fails after server upgrade | Assumption at exact boundary | Define policy, separate diagnostics |
`$geoWithin` misses records with no location | Missing field differs from outside | Separate data-quality state |
Reading raw BSON shows wrong Point type | Incorrect mapper field type | Check `GeoJsonPoint`, `@Document`, raw BSON |
Sort unstable across calls | Missing tie-breaker | Sort with unique key |
Count right yet some returned stores invalid | Tenant/status or non-geometry rules | Test the full filter |
Transaction/geofence state shifts between two queries | Missing region version/snapshot | Record snapshot/version on decision record |
Running delete/seed tests against production data | Wrong database connection | Isolated test database and URI guards |

### 22.1. Workflow to Diagnose a Misclassified Point

1. **Fetch raw coordinates** and data source; confirm lon/lat order, units, and CRS.
2. **Check GPS accuracy** and rounding/serialization steps.
3. **Read raw BSON `location`** of the document and confirm GeoJSON Point.
4. **Read actual region geometry** and version; check Polygon/MultiPolygon/hole/ring closure.
5. **Run the same BSON query in `mongosh`** with the same tenant/status as the real request.
6. **Note boundary cases** separately if the point sits near an edge or vertex.
7. **Check `2dsphere` index** and `executionStats` if results are right but slow.
8. **Cross-check policy**: is the region still ACTIVE, user authorized, geofence tolerance applied?
9. **Check external systems**: mobile map projection, GIS import, geocoding.
10. **Create a regression fixture** with the offending coordinates and geometry version.

Never stare at a map screenshot alone and blame MongoDB; displayed points may use different rounding or projections than the queried data.

## 23. Designing a Sustainable Region Management System

When managing thousands of delivery zones, Polygon data needs its own lifecycle:

~~~mermaid
flowchart TD
    A["GIS / admin creates region"] --> B["Check GeoJSON structure"]
    B --> C["Check topology, winding, CRS"]
    C --> D["Check tenant ownership + business rules"]
    D --> E["Save region version"]
    E --> F["Provision/index 2dsphere"]
    F --> G["Publish ACTIVE"]
    G --> H["Query points / match regions"]
    H --> I["Boundary tolerance + accuracy policy"]
    I --> J["Decision + version + audit metadata"]
~~~

### 23.1. Storing Region Versions for Auditing

Example region document:

~~~json
{
  "_id": "delivery-area-101",
  "tenantId": "tenant-a",
  "status": "ACTIVE",
  "revision": 12,
  "policyVersion": "2026-11",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[
      [106.66, 10.74],
      [106.74, 10.74],
      [106.74, 10.82],
      [106.66, 10.82],
      [106.66, 10.74]
    ]]
  }
}
~~~

When processing an order, persist `areaId`, `revision`, `decision`, timestamp, and request ID so you can explain why the order was accepted under the zone **at that moment**, even if an admin edits the polygon a day later.

### 23.2. Do Not Treat Live Queries as Audit History

Running `$geoWithin` today does not necessarily reproduce **yesterday's** result if region geometry, store points, or policies changed. Auditing requires durable snapshots/versions or event logs with proper read access controls.

### 23.3. Do Not Store Locations Longer Than Needed

Location can be sensitive data. A system that only needs to confirm "inside delivery zone" may not need to retain exact customer GPS history long-term. Distinguish **public store locations** from **personal user locations** to set appropriate retention, access control, and audit logging.

### 23.4. Handling Concurrent Region Changes

If an admin updates a region while a customer places an order, this race can occur:

~~~text
T0: order checked against region revision=11
T1: admin publishes revision=12
T2: order created without recording the revision used
~~~

The system cannot consistently explain why the order was valid or invalid. Pin the decision to an explicit revision, or use appropriate transactions/state machines when multiple documents must change together. A geospatial query **does not create a workflow-wide snapshot**.

### 23.5. Separating Geometry Validation from Business Validation

| Category | Examples |
|---|---|
Geometry | Closed rings, non-self-intersecting, valid holes, winding, CRS |
Data ingestion | Right lon/lat source order, no NaN, JSON normalization |
Access control | Tenant owns region, roles allowed to edit/publish |
Business policy | ACTIVE, effective dates, priority, tolerance |
Persistence | Document mapping, unique ID, `2dsphere` index |
Operations | Monitoring, versioning, rollback/migration, backups |

Never cram everything into one Spring Data callback or one `containsPoint` method. Independent responsibilities need independent tests plus an end-to-end integration test.

## 24. Testing Strategy from Unit to Production-Like

A solid test suite spans multiple layers:

| Layer | Coverage | Tools |
|---|---|---|
Unit validation | Lon/lat ranges, ring closure, vertex limits | JUnit/AssertJ |
Unit policy | `INSIDE`/`OUTSIDE`/`UNCERTAIN` decision from computed distance/accuracy | JUnit |
Geometry/topology | Holes, self-intersection, antimeridian, winding, geodesic distance | GIS library supporting target CRS |
MongoDB integration | `$geoWithin`/`$geoIntersects` with GeoJSON, `2dsphere` | Real MongoDB, `@DataMongoTest` |
Security integration | Tenant/status filters, region permissions | Spring Security + database tests |
Contract/API | Lon/lat order, JSON DTOs, error semantics | HTTP integration tests |
Load/performance | Large/small regions, vertex counts, indexes, p95/CPU | Benchmarks + `explain` |
Regression | Sanitized fixtures from real production bugs | Versioned test fixtures |

### 24.1. Boundary Coordinate Groups Worth Expanding

Beyond the west edge and southwest corner in the example, test:

- North, south, and east edges plus every vertex.
- Inside/outside points **at finite offsets** around each edge.
- Points near a hole, inside a hole, and on a hole's edge.
- Two overlapping polygons or polygons sharing an edge.
- A `MultiPolygon` with two disjoint components and a point between them.
- Very narrow regions and concave regions.
- Coordinates near ±180° and near ±90°.
- Missing locations, wrong location types, and legacy data.
- Identical points across `tenant-a`/`tenant-b`.
- `DRAFT`/`EXPIRED` regions excluded from `ACTIVE` decisions.

You do not need every unit test to run all permutations; organize them into geometry regression suites and server integration tests.

### 24.2. Metamorphic Tests with Clear Invariants

A good way to strengthen tests is applying **semantics-preserving geometric transformations**:

- Add an **interior** point far from edges and verify it still matches when the test grid expands.
- Add a store outside the region and verify existing matched sets stay unchanged.
- Add a `tenant-b` store at the same coordinates and verify `tenant-a` queries never leak it.
- Flip a store's `status` from `ACTIVE` to `INACTIVE` and verify it is excluded.
- Pass the same Polygon to both typed queries and raw BSON queries and compare matched IDs (on MongoDB versions supporting both paths).

Never assume **reversing all vertices** or **shifting a polygon across ±180°** preserves semantics in every spherical system. Those can alter winding or region definition and must be evaluated explicitly.

### 24.3. Fail Fast on Geometry Ingestion

Self-intersecting, oversized, unclosed, or NaN-containing Polygon inputs should be rejected at ingestion with meaningful errors instead of failing later during checkout. Yet never conflate:

~~~text
malformed geometry -> HTTP 400 / validation error
no matching region -> business OUTSIDE_REGION
point near boundary -> business UNCERTAIN
MongoDB timeout -> infrastructure error / retry policy
wrong tenant -> authorization failure
~~~

These five states have distinct causes and handling. Never use `onErrorResume` or a catch-all to turn every error into "outside region".

## 25. Applied Exercises

**Exercise 1 — Coordinate order.** Take `[106.70,10.78]` and `[10.78,106.70]`. Write a validator checking lon/lat; explain why you should not auto-swap when both numbers lie within valid bounds.

**Exercise 2 — GeoJSON Polygon.** Build a rectangle with four corners and the final point repeating the first. Contrast `Polygon.coordinates` structure with `LineString.coordinates`.

**Exercise 3 — `$geoWithin`.** Seed 6 stores covering inside/outside/near-edge points. Write a MongoDB query and `MongoTemplate` service to retrieve points inside the region filtered by `tenant-a` and `ACTIVE` status.

**Exercise 4 — Typed `GeoJsonPolygon`.** Convert the BSON query to `GeoJsonPolygon` and `Criteria.within`. Compare matched IDs and raw BSON queries on test MongoDB.

**Exercise 5 — Edges and vertices.** Create fixtures on every edge and vertex and record MongoDB's output by version. Explain why these tests do not replace a business boundary policy.

**Exercise 6 — Inside/outside offsets.** Create two points offset to either side of the west edge by a finite margin, asserting one matches and one does not. Keep separate from exact-edge tests.

**Exercise 7 — Polygon with hole.** Add a rectangular hole, seed one point in the center of the hole and one inside the outer ring only; assert they classify differently.

**Exercise 8 — `MultiPolygon`.** Create two disjoint areas and seed 3 points: in area one, in area two, and between them. Use `$geoWithin` to verify.

**Exercise 9 — `$geoIntersects`.** Store service areas as Polygons and query which regions intersect a Point, verifying when multiple regions match.

**Exercise 10 — Zone priority.** Design a rule when one point belongs to two regions: priority descending, zone ID ascending. Test tie-breaking independent of cursor order.

**Exercise 11 — Antimeridian.** Construct a GIS-verified region crossing ±180°, test points at `+179.x` and `−179.x`, plus a point at `0°`. Explain why naive min/max longitude fails.

**Exercise 12 — Polar latitudes.** Test the validator with latitude `+90`, `−90`, and out-of-bounds values. Evaluate why a 2D box does not match a spherical polygon near the poles.

**Exercise 13 — Topology.** Construct a self-intersecting Polygon or a hole outside the outer ring. Show why `Document.parse` and ring-closure checks are insufficient; integrate an appropriate GIS validator.

**Exercise 14 — Index.** Create a `2dsphere` index on `location` and verify with `listIndexes`. Compare `executionStats` when the index exists versus without an appropriate index.

**Exercise 15 — Compound index.** Benchmark `{location:"2dsphere"}` vs `{tenantId:1,status:1,location:"2dsphere"}` on a multi-tenant dataset; do not draw conclusions from a 12-document sample.

**Exercise 16 — Tenant security.** Seed identical coordinates for `tenant-a`/`tenant-b` and an `INACTIVE` record; assert `tenant-a` queries return only `ACTIVE` `tenant-a` items. Test that actors cannot pass arbitrary tenant IDs via query strings without authorization.

**Exercise 17 — Missing vs outside.** Create one document missing `location` and one with a valid Point outside the Polygon. Design the API to return distinct data-quality reasons instead of labeling both `OUTSIDE_REGION`.

**Exercise 18 — Location accuracy.** Simulate a point 7 m from the edge, accuracy radius 10 m, tolerance 15 m. Unit-test the business classifier returning `UNCERTAIN` without comparing raw longitude deltas.

**Exercise 19 — Concurrency and versioning.** An admin updates region revision from 11 to 12 while an order is being validated. Design a record persisting the revision used and test post-hoc decision auditing.

**Exercise 20 — Regression tests.** Build a versioned JSON fixture covering inside, outside, boundary, holes, multipolygon, antimeridian, and tenant cases. Separate which tests use hard assertions vs which only observe server geometry behavior.

## 26. Key Takeaways

**Geospatial region matching in MongoDB is more than checking whether two numbers lie between min and max.** GeoJSON uses **`[longitude, latitude]`** order, Polygons consist of **closed rings**, MultiPolygons contain multiple polygons, and holes must sit at the right ring nesting level. Verify topology, winding, CRS, antimeridian behavior, and geometry size limits before running critical queries.

**`$geoWithin`** fits finding `Point`s inside a `Polygon`; **`$geoIntersects`** fits checking whether geometries intersect, such as stored `Polygon` region documents against an input point. `$near` solves proximity ranking, not point-in-region inclusion. A `2dsphere` index enables spatial queries to run efficiently, yet requires actual provisioning and verification with `explain("executionStats")`—never assume from annotations.

**Boundaries must be part of your contract and test suite.** Assert confidently for points clearly inside, clearly outside, and finitely offset on either side; record exact edge/vertex or hole-border outcomes separately. When business rules require metric distance thresholds to boundaries, use proper **meter**-based measurements, factor in GPS error, and return `UNCERTAIN` when evidence is insufficient rather than forcing a geometric boolean into a safety decision.

Finally, **accurate geometry alone does not guarantee security or business consistency**. Queries must enforce tenant/status filters, regions need explicit revisions and policies, input geometries need size and topology bounds, and coordinates, mapped BSON, indexes, and server outputs must all be verified via integration tests on real MongoDB. Save near-boundary tests and region/version fixtures as regression tests before deploying to production.
