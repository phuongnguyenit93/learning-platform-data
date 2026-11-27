# Coordinate Validation, Invalid Geometries, and Index Limitations in MongoDB

## 1. Why Is Valid Geospatial Data More Important Than Just Creating an Index?

An apartment-rental application may store apartment locations, transaction offices, train stations, and neighborhood boundaries as **GeoJSON**. Common queries include:

- Finding apartments within a **3 km** radius of a location.
- Showing only listings within a selected **area boundary**.
- Finding the nearest places belonging to the same **tenant** or service group.
- Checking whether a delivery point falls inside a service zone.
- Syncing the map when locations are updated or deleted.

Suppose the API receives coordinates:

~~~javascript
{
  type: "Point",
  coordinates: [10.776, 106.700]
}
~~~

The user might think this means **latitude = 10.776, longitude = 106.700**. However, GeoJSON uses **[longitude, latitude]** order, so MongoDB interprets the second element as latitude **106.700**, which lies outside valid geographic bounds. A **`2dsphere` index** can reject this geometry.

Even more dangerously, a pair like **[40, 10]** has both numbers within valid ranges, even if swapped from **[latitude=40, longitude=10]**. Range checking **is not enough** to detect every axis-swap error.

Therefore, a reliable system needs multiple layers:

~~~text
Client request / ingestion system
                 |
                 v
        Parse and check types
                 |
                 v
     Validate CRS, coordinate order
                 |
                 v
   Check range and geometry/topology
                 |
                 v
    Business rules, tenant, region
                 |
                 v
   MongoDB schema validation (if any)
                 |
                 v
     Write document + geospatial index
                 |
                 v
     Query, monitor, and reconcile data
~~~

**Bottom line:** indexes accelerate searches and can reject certain malformed geometries; they **do not** detect a point placed in the wrong city that is still a valid GeoJSON Point, do not enforce access control, and do not replace GIS validation workflows.

### Learning Objectives

After this lesson, you will be able to:

1. Read and validate **longitude, latitude** coordinates in **WGS84**.
2. Distinguish **GeoJSON Point, LineString, Polygon, MultiPolygon**, and common structural mistakes.
3. Understand **closed Polygon rings, self-intersection, holes, the antimeridian**, and the limits of application-level checks.
4. Use a **`2dsphere` index** for geographic data on Earth, and recognize when a **`2d` index** is inappropriate.
5. Explain how indexes handle **missing/null/empty locations**, bad data, and compound indexes.
6. Write **`$near`, `$geoWithin`, `$geoIntersects`, and `$geoNear`** queries with proper geometry and units.
7. Validate data prior to import, quarantine bad records, and troubleshoot failed index builds.
8. Understand index limitations: **a geospatial index is not a unique constraint, not a shard key, does not cover arbitrary queries, and carries cost for complex geometries**.
9. Run a `mongosh` lab with fixed data and explain query results.

> This lesson belongs to **Database Engine Document MongoDB → Geospatial Data**. Examples use the **`mongo_geo_validation_lab_298`** database and IDs prefixed with **`geo298-`**. City coordinates in the lab are approximate points for learning queries, **not to be used for navigation or legal boundary determination**.

## 2. GeoJSON and Coordinate Conventions Must Be Consistent

### 2.1. A Valid GeoJSON Point

~~~javascript
{
  type: "Point",
  coordinates: [106.700, 10.776]
}
~~~

Two values in the Array:

- **coordinates[0] = 106.700**: longitude, unit in **degrees**.
- **coordinates[1] = 10.776**: latitude, unit in **degrees**.

**Not** `[latitude, longitude]`, and **not** `[x in meters, y in meters]`.

### 2.2. Longitude and Latitude Bounds

In standard WGS84 longitude/latitude representation:

| Quantity | Valid Value Range | Interpretation |
| --- | --- | --- |
| **Longitude** | From **-180** to **180** degrees | West negative, East positive |
| **Latitude** | From **-90** to **90** degrees | South negative, North positive |

Examples:

~~~javascript
// Valid in type and range:
[106.700, 10.776]
[-73.985, 40.758]
[0, 0]

// Invalid if representing WGS84 lon/lat:
[106.700, 95.000]     // latitude exceeds 90
[210.000, 10.776]     // longitude exceeds 180
["106.700", "10.776"] // String instead of Number
[106.700]             // missing latitude
~~~

**Valid by range does not mean the right location.** `[10.776, 40.758]` may be a valid point on the map yet completely wrong if the application swapped axes from another source.

### 2.3. `[0,0]` Is Not Null

The point **[0,0]** near the Gulf of Guinea is a valid coordinate, informally nicknamed "Null Island." If a system defaults missing locations to `[0,0]`, MongoDB stores and indexes it as a real location.

Distinguish clearly:

- **missing `location`**: no location received yet.
- **`location: null`**: location unknown.
- **`location: {type:"Point", coordinates:[0,0]}`**: an explicit numeric coordinate.

Never silently convert missing data to `[0,0]`. For a business accepting locations only within Vietnam, add a geographic range check **specific to that data source**, rather than applying Vietnam bounds to a global collection.

### 2.4. WGS84 Differs from Planar Coordinate Systems

GeoJSON in **`2dsphere`** queries uses longitude/latitude on Earth's surface, typically tied to **WGS84**.

Do not confuse:

- **EPSG:4326**: longitude/latitude in degrees.
- **EPSG:3857**: Web Mercator coordinates in flat units near meters, not longitude/latitude.
- **UTM**: planar zone-based coordinates; require proper transformation before writing GeoJSON Points for `2dsphere`.

For example, a GIS source sends Web Mercator coordinates:

~~~javascript
{ x: 11877670, y: 1206650 }
~~~

You cannot directly rewrite that as:

~~~javascript
{ type: "Point", coordinates: [11877670, 1206650] }
~~~

expecting MongoDB to treat it as a position on Earth. Determine the **source CRS** and transform properly to longitude/latitude.

### 2.5. Elevation Is Not Used as 3D Spatial Distance

Some GeoJSON data includes a third elevation element:

~~~javascript
{
  type: "Point",
  coordinates: [106.700, 10.776, 18]
}
~~~

In standard `2dsphere` queries, MongoDB evaluates geographic relationships using **longitude/latitude**, not 3D spatial search by altitude like a 3D GIS. If the application needs elevation:

- Store **`altitudeMeters`** with an explicit unit and vertical reference.
- Handle elevation logic separately, such as building floor or height range.
- Do not assume `$near` computes 3D distance simply because `coordinates` contains a third element.

To keep the lab and validators focused, examples use **two coordinates** per Point.

## 3. Common GeoJSON Geometry Types

### 3.1. Point

A single point:

~~~javascript
{
  type: "Point",
  coordinates: [106.700, 10.776]
}
~~~

Suitable for an apartment, sensor, branch, or delivery spot.

### 3.2. LineString

A polyline with **at least two positions**:

~~~javascript
{
  type: "LineString",
  coordinates: [
    [106.700, 10.776],
    [106.706, 10.783],
    [106.715, 10.792]
  ]
}
~~~

Suitable for a path or high-level transport route. This geometry does not solve road-network rules, one-way streets, or travel times.

### 3.3. Polygon

A region with an outer ring:

~~~javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.695, 10.770],
      [106.730, 10.770],
      [106.730, 10.820],
      [106.695, 10.820],
      [106.695, 10.770]
    ]
  ]
}
~~~

**`coordinates`** is an Array of rings (**linear rings**), not a flat Array of points. The first ring is the outer boundary. Subsequent rings, when present, represent **holes** per GeoJSON and MongoDB rules.

### 3.4. Polygon with a Hole

~~~javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.690, 10.760],
      [106.750, 10.760],
      [106.750, 10.830],
      [106.690, 10.830],
      [106.690, 10.760]
    ],
    [
      [106.710, 10.785],
      [106.710, 10.800],
      [106.725, 10.800],
      [106.725, 10.785],
      [106.710, 10.785]
    ]
  ]
}
~~~

This example describes a large region with an excluded interior area. Using holes properly requires valid, non-self-intersecting rings with holes contained inside the outer ring and obeying ring-orientation/area rules of GeoJSON and the geospatial engine.

### 3.5. MultiPoint, MultiLineString, and MultiPolygon

These types hold multiple geometry parts of the same kind:

~~~javascript
// Multiple points:
{
  type: "MultiPoint",
  coordinates: [
    [106.700, 10.776],
    [106.750, 10.850]
  ]
}

// Multiple lines:
{
  type: "MultiLineString",
  coordinates: [
    [
      [106.700, 10.776],
      [106.706, 10.783]
    ],
    [
      [106.715, 10.792],
      [106.724, 10.807]
    ]
  ]
}

// Multiple Polygons:
{
  type: "MultiPolygon",
  coordinates: [
    [
      [
        [106.690, 10.760],
        [106.710, 10.760],
        [106.710, 10.790],
        [106.690, 10.790],
        [106.690, 10.760]
      ]
    ],
    [
      [
        [106.725, 10.795],
        [106.750, 10.795],
        [106.750, 10.830],
        [106.725, 10.830],
        [106.725, 10.795]
      ]
    ]
  ]
}
~~~

With `MultiPolygon`, array nesting deepens: **MultiPolygon → Polygon → ring → position → Number**. Missing a single pair of brackets turns the data into a different structure, preventing MongoDB from indexing or querying it properly.

### 3.6. GeometryCollection

A `GeometryCollection` contains multiple geometry objects:

~~~javascript
{
  type: "GeometryCollection",
  geometries: [
    {
      type: "Point",
      coordinates: [106.700, 10.776]
    },
    {
      type: "LineString",
      coordinates: [
        [106.700, 10.776],
        [106.706, 10.783]
      ]
    }
  ]
}
~~~

**`GeometryCollection` uses a `geometries` field**, not a single `coordinates` Array like Point or Polygon. When an application only needs an apartment's position, restrict the schema to `Point` instead of accepting arbitrary GeoJSON types and having to handle rare edge cases.

## 4. Error Taxonomy: Syntax, Numeric, Structural, and Topological

| Error Level | Example | Why Is It Dangerous? |
| --- | --- | --- |
| **Wrong type** | coordinates: ["106.7", "10.77"] | Strings are not numeric lon/lat |
| **Missing element** | coordinates: [106.7] | Missing latitude |
| **Extra Array level** | coordinates: [[106.7, 10.77]] for Point | MultiPoint-like shape, not a Point |
| **NaN/Infinity** | coordinates: [Infinity, 10.77] | Not a finite position |
| **Out of range** | latitude 110 | Exceeds latitude bounds |
| **Swapped axes** | [10.776, 106.700] | Latitude 106.700 out of range; or silently wrong if both stay in range |
| **Wrong CRS** | [11877670, 1206650] | Planar coordinates treated as lon/lat |
| **Line too short** | Only one position | Cannot form a valid LineString |
| **Unclosed Polygon** | Last point differs from first | Ring is not closed |
| **Polygon missing vertices** | Two repeated points forming a loop | Zero real area |
| **Self-intersection** | Bow-tie ring | Ambiguous inside/outside or rejected |
| **Invalid hole** | Hole outside outer ring | Invalid topology |
| **Region crossing antimeridian** | 179°E to -179°W | Naive bounding box selects the wrong side of Earth |
| **Wrong place, valid numbers** | Point in another city | Index succeeds and returns wrong business results |
| **Unit mismatch** | $maxDistance: 3 intending 3 km | GeoJSON queries use meters; searches only 3 m |

**Do not lump all of these together as "MongoDB geospatial errors."** Some must be blocked at the input API, some in GIS libraries, and some in schema validation or `2dsphere` index creation.

## 5. Validating Points at the Application Layer

### 5.1. Do Not Use `parseFloat` Carelessly

Example:

~~~javascript
parseFloat("106.700abc"); // Returns 106.7
~~~

Such input is actually invalid if the API specifies numeric coordinates. Permissive coercion masks upstream bugs.

The input contract should be explicit:

- Client sends JSON Numbers, not strings with trailing characters.
- Source uses **[longitude, latitude]**.
- Values must be **finite** and within range.
- Conventions exist for precision, geocoding quality, and allowed regions.

### 5.2. Point Validation Function

JavaScript example runnable in `mongosh` or Node.js for standard JSON Numbers:

~~~javascript
function validateGeoPoint(geometry) {
  const errors = [];

  if (!geometry || typeof geometry !== "object" ||
      Array.isArray(geometry)) {
    return ["Geometry must be an object."];
  }

  if (geometry.type !== "Point") {
    errors.push("type must be Point.");
  }

  const coordinates = geometry.coordinates;
  if (!Array.isArray(coordinates) || coordinates.length !== 2) {
    errors.push("coordinates must be [longitude, latitude].");
    return errors;
  }

  const longitude = coordinates[0];
  const latitude = coordinates[1];

  if (typeof longitude !== "number" ||
      !Number.isFinite(longitude)) {
    errors.push("longitude must be a finite Number.");
  } else if (longitude < -180 || longitude > 180) {
    errors.push("longitude must be in [-180, 180].");
  }

  if (typeof latitude !== "number" ||
      !Number.isFinite(latitude)) {
    errors.push("latitude must be a finite Number.");
  } else if (latitude < -90 || latitude > 90) {
    errors.push("latitude must be in [-90, 90].");
  }

  return errors;
}

const candidates = [
  { type: "Point", coordinates: [106.700, 10.776] },
  { type: "Point", coordinates: [10.776, 106.700] },
  { type: "Point", coordinates: ["106.700", 10.776] },
  { type: "Point", coordinates: [106.700] },
  { type: "Point", coordinates: [0, 0] }
];

for (const geometry of candidates) {
  printjson({
    geometry,
    errors: validateGeoPoint(geometry)
  });
}
~~~

Results:

- Point `[106.700, 10.776]` passes structure/range validation.
- Point `[10.776, 106.700]` fails latitude validation.
- Point with String coordinates is rejected.
- Point with only one element is rejected.
- `[0,0]` passes numeric/range validation because it is a real coordinate.

**Function scope:** this is a validator for **JSON Numbers and 2D GeoJSON Points** under a specific app contract, not a full GeoJSON parser. If using BSON Decimal128, Long, or altitude support, extend types/semantics deliberately—never silently ignore out-of-range values.

### 5.3. Domain Validation Can Catch Silent Axis Swaps

Suppose an app only accepts points inside a small legally/technically defined region. You can add a coarse bounding-box check:

~~~javascript
function inApproxHcmLabBox(longitude, latitude) {
  return longitude >= 106.55 &&
         longitude <= 106.90 &&
         latitude >= 10.65 &&
         latitude <= 10.95;
}
~~~

This is an **approximate bounding box solely for the lab**, not an administrative boundary of HCMC, and must never be used for legal decisions.

If an application serves multiple provinces or countries, you cannot apply this box to all data. Use a **catalog of valid regions per tenant/country**, verified geofence data, or trusted GIS datasets.

### 5.4. Detecting Abnormal Distance Jumps

Suppose a stationary sensor reports a new location thousands of kilometers away one minute later. Mathematically both coordinates may be valid, yet this signals a **data quality anomaly**:

~~~text
T0: coordinates near HCMC
T1: one minute later in Europe

=> Does not necessarily violate GeoJSON,
   but violates business expectations for a stationary device.
~~~

You can check:

- Maximum travel speed for the device type.
- GPS accuracy / reference system.
- Whether the position lies inside an authorized region.
- Whether the data source swapped axes, dropped a minus sign, or changed CRS.

**Never let a `2dsphere` index substitute for these rules.**

## 6. Validating LineString, Polygon, and MultiPolygon

### 6.1. Minimum Structural Rules

| Geometry | Basic Structural Requirements |
| --- | --- |
| **Point** | One position with valid lon/lat |
| **MultiPoint** | One Array of positions |
| **LineString** | At least 2 positions |
| **MultiLineString** | Array of LineStrings |
| **Polygon** | Array of rings; each ring has at least 4 positions, first = last |
| **MultiPolygon** | Array of Polygons, each Polygon contains rings |
| **GeometryCollection** | Array of geometries with valid types |

These conditions only check **structure**. A Polygon can pass vertex count and ring closure checks while still **self-intersecting** or having misplaced holes.

### 6.2. Example of an Unclosed Polygon

Incorrect:

~~~javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.690, 10.760],
      [106.720, 10.760],
      [106.720, 10.800],
      [106.690, 10.800]
      // Missing repeated closing element [106.690, 10.760].
    ]
  ]
}
~~~

Valid for ring closure:

~~~javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.690, 10.760],
      [106.720, 10.760],
      [106.720, 10.800],
      [106.690, 10.800],
      [106.690, 10.760]
    ]
  ]
}
~~~

A ring requires **at least four positions** because three distinct vertices need a fourth position repeating the first to close the loop. A ring made from one or two repeated positions is not a polygon with valid area.

### 6.3. Self-Intersection: Bow-Tie Shape

Conceptual example of a ring with crossing edges:

~~~javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.690, 10.760],
      [106.730, 10.800],
      [106.690, 10.800],
      [106.730, 10.760],
      [106.690, 10.760]
    ]
  ]
}
~~~

This ring follows two crossing diagonals. Interpreting the "interior" of a self-intersecting shape does not yield a valid simple Polygon as expected. MongoDB/`2dsphere` may reject invalid geometries during index builds or writes depending on the exact geometry and version.

**Never check only `first === last` and conclude a Polygon is valid.** Topology also includes self-intersection, degenerate edges, holes, relationships between rings, and spherical surface behavior.

### 6.4. Holes Must Lie Inside the Outer Region

A hole must not:

- Lie completely outside the outer ring.
- Cross through the outer ring.
- Intersect other holes in violation of validity rules.
- Have a self-intersecting ring or too few vertices.

Reliable hole validation requires topological algorithms built for **spherical/WGS84 coordinates** and MongoDB's rules. Do not rely on a simple planar polygon checker for large shapes or shapes crossing the antimeridian.

### 6.5. Ring Structure Validation Function

The following snippet catches simple structural errors early, **not a full GIS topology validator**:

~~~javascript
function validLonLatPosition(position) {
  return Array.isArray(position) &&
    position.length === 2 &&
    typeof position[0] === "number" &&
    typeof position[1] === "number" &&
    Number.isFinite(position[0]) &&
    Number.isFinite(position[1]) &&
    position[0] >= -180 &&
    position[0] <= 180 &&
    position[1] >= -90 &&
    position[1] <= 90;
}

function samePosition(a, b) {
  return a[0] === b[0] && a[1] === b[1];
}

function validateRingStructure(ring) {
  const errors = [];
  if (!Array.isArray(ring) || ring.length < 4) {
    return ["Ring must have at least 4 positions."];
  }

  if (!ring.every(validLonLatPosition)) {
    errors.push("Contains position that is not valid lon/lat.");
    return errors;
  }

  if (!samePosition(ring[0], ring[ring.length - 1])) {
    errors.push("Unclosed ring: start and end differ.");
  }

  const distinctVertices = new Set(
    ring.slice(0, -1).map(p => p[0] + "," + p[1])
  );
  if (distinctVertices.size < 3) {
    errors.push("Ring has fewer than 3 distinct vertices.");
  }

  return errors;
}

function validatePolygonStructure(geometry) {
  if (!geometry || geometry.type !== "Polygon") {
    return ["Geometry must be a Polygon."];
  }

  if (!Array.isArray(geometry.coordinates) ||
      geometry.coordinates.length === 0) {
    return ["Polygon requires at least one ring."];
  }

  const errors = [];
  geometry.coordinates.forEach((ring, i) => {
    for (const error of validateRingStructure(ring)) {
      errors.push("Ring " + i + ": " + error);
    }
  });
  return errors;
}

printjson(
  validatePolygonStructure({
    type: "Polygon",
    coordinates: [
      [
        [106.69, 10.76],
        [106.72, 10.76],
        [106.72, 10.80],
        [106.69, 10.80]
      ]
    ]
  })
);
~~~

The output reports **unclosed ring**. Yet a closed ring **can still fail topology**, such as self-intersection. For Polygons coming from GIS files or user map drawings, use a **dedicated GIS library** to validate geometry, remove degenerate edges, normalize rings, and handle coordinate systems.

### 6.6. Do Not Repair Invalid Polygons by Guessing

If you receive a self-intersecting Polygon:

- Do not sort all points by longitude and treat it as "repaired."
- Do not merely append the first point at the end and ignore other defects.
- Do not arbitrarily reverse ring winding without understanding area/hole rules.
- Do not round coordinates to 1 decimal place and distort the geometric boundary.

A better approach:

1. Record **source, CRS, geometry ID, and failure reason**.
2. Block/quarantine data whose validity cannot be verified.
3. If reliable GIS tooling is available, repair and re-validate topology.
4. Compare area and position before and after repair; large shifts need business sign-off.
5. Insert into the indexed collection only once geometry meets the data contract.

## 7. Antimeridian, Large Regions, and Winding

### 7.1. Why Does the 180° Meridian Cause Confusion?

A Polygon spanning **179°E to -179°W** may represent a small region crossing the **antimeridian**, rather than a band wrapping almost all the way around Earth.

A flat bounding box:

~~~text
minLongitude = -179
maxLongitude =  179
~~~

can represent a region **nearly covering the entire world**, rather than a narrow strip around the dateline. Consequently, GeoJSON crossing the antimeridian requires proper spherical geography algorithms; simple min/max longitude comparisons do not work universally.

### 7.2. Polygons Larger Than a Hemisphere

MongoDB has special rules for **single-ringed GeoJSON Polygons** larger than a hemisphere; on corresponding versions and query paths, you may need MongoDB's **strict-winding coordinate reference system** to specify which side of the sphere is meant.

If a product draws a Polygon covering most of the globe, simply reversing vertex order can flip which region is selected. Consult **Big Polygons** documentation for your server version before working with oversized geometries.

### 7.3. Administrative Boundaries Require Authoritative Data

Legal boundaries must never be approximated by four hand-picked coordinates. For delivery maps or administrative borders:

- Use datasets with clear provenance, effective date, resolution, and licensing.
- Track boundary versions (e.g., after municipal redistricting).
- Validate polygons, holes, and antimeridian handling before import.
- Do not over-round or over-simplify if decisions hinge on points near edges.
- Define explicit rules for **points lying directly on the boundary** rather than guessing from map visuals.

**A geospatial index evaluates the stored geometry**; it cannot tell whether a boundary dataset matches current law.

## 8. `2dsphere` and `2d` Indexes: Two Different Geometric Models

### 8.1. `2dsphere` for Data on Earth

~~~javascript
db.places.createIndex({ location: "2dsphere" });
~~~

A **`2dsphere`** index supports geospatial queries on a spherical surface, covering GeoJSON Point, LineString, Polygon, and other supported types. It is normally the right choice for WGS84 locations, proximity searches, and geometric relationships on real maps.

**Distance unit:** when using a **GeoJSON Point** with `$near`/`$geoNear` on `2dsphere`, thresholds and distances are generally expressed in **meters** per the corresponding operator semantics.

### 8.2. `2d` for Planar Space / Legacy Coordinate Pairs

~~~javascript
db.canvasPoints.createIndex({ position: "2d" });
~~~

**`2d`** is an index for planar calculations on legacy coordinate pairs. It suits certain planar coordinate datasets and queries that do not require spherical math, but should not be used by default for Earth distances when data is GeoJSON lon/lat.

Intuitive difference example:

~~~text
One degree of longitude near the equator
differs in ground distance from one degree of longitude at high latitudes.

If you use Euclidean distance directly on degrees
as a substitute for distance on Earth's surface,
results can be significantly wrong.
~~~

### 8.3. Comparison Table

| Criterion | **`2dsphere`** | **`2d`** |
| --- | --- | --- |
| Model | Geometry on a spherical surface | Planar / legacy coordinates |
| Typical data | GeoJSON, WGS84 lon/lat | Legacy coordinate pairs |
| Real-world applications | Homes, delivery points, geofencing, map lines/regions | Canvases, flat coordinates per use case |
| Near queries on GeoJSON | Geographic distance in meters | Should not substitute for spherical model |
| Complex geometry support | Supported GeoJSON types | More limited with different semantics |
| Automatically verifies real-world correctness? | No | No |

**Do not merely switch index type from `2d` to `2dsphere` to fix wrong-CRS data.** Proper remediation starts with how coordinates and geometries are encoded.

## 9. Geospatial Index Behavior with Missing and Invalid Data

### 9.1. `2dsphere` Is Sparse by Default

**`2dsphere` indexes are inherently sparse.** A document missing the geo field, or having `null` or an empty array for the geo field, may **not be indexed** under these index rules.

Examples:

~~~javascript
// Missing location:
{ _id: "p01", name: "No location yet" }

// location null:
{ _id: "p02", location: null }

// empty location:
{ _id: "p03", location: [] }
~~~

Such documents can still exist in the collection depending on schema validation, yet they will not appear in **`$near`** queries simply because the collection has an index.

**Do not confuse sparse behavior with "MongoDB silently skips all invalid GeoJSON."**

### 9.2. Invalid Geometry Differs from Missing Location

~~~javascript
// Has geo field, but wrong type/range:
{
  _id: "p04",
  location: {
    type: "Point",
    coordinates: [106.700, 106.700]
  }
}
~~~

When a `2dsphere` index attempts to extract keys for this document, MongoDB can reject the write or the index build due to invalid geometry. This is not a "missing location" document skipped by sparse indexing.

Therefore, handle these two groups separately:

| Group | Meaning | Recommended Policy |
| --- | --- | --- |
| Missing/null location | Coordinates not yet available | Define as optional or required; may exclude from geo results |
| Location present, geometry invalid | Uninterpretable/invalid data | Reject or quarantine; never wait for index to "fix" it |

### 9.3. Building an Index After Importing Legacy Data

An existing collection with 1 million documents and no geospatial index may harbor invalid locations. Running:

~~~javascript
db.places.createIndex({ location: "2dsphere" });
~~~

forces the server to scan existing data to build the index. If even one document has an unindexable geometry, **the index build can fail**. Failure does not mean the 999,999 valid documents automatically end up fully indexed.

Therefore, before indexing legacy data:

1. Measure the missing/null rate.
2. Scan GeoJSON structure and coordinate types.
3. Detect out-of-range, unclosed-ring, or self-intersecting geometries with appropriate tools.
4. Establish a repair/quarantine policy for bad records.
5. Run the index build in a properly planned maintenance window and environment.
6. Verify the index exists via `getIndexes`/`explain`.

### 9.4. Writes After the Index Exists

When inserting or updating a document with an invalid `location`, the `2dsphere` index can cause the write operation to fail. **The application must catch write errors**, return useful diagnostics, and preserve input for operator remediation rather than swallowing errors and reporting success.

With `bulkWrite`, earlier operations may succeed before an invalid geometry fails a later operation. **`bulkWrite` is not an automatic transaction.** Check partial results, track request IDs, and design idempotent retry logic.

## 10. `mongosh` Lab: Valid Points and Verifiable Query Results

### 10.1. Lab Data

We create eight approximate locations for practicing queries:

| ID | Tenant | Region | Longitude | Latitude |
| --- | --- | --- | ---: | ---: |
| geo298-p01 | t001 | HCMC | 106.700 | 10.776 |
| geo298-p02 | t001 | HCMC | 106.705 | 10.782 |
| geo298-p03 | t001 | HCMC | 106.713 | 10.792 |
| geo298-p04 | t001 | HCMC | 106.724 | 10.807 |
| geo298-p05 | t001 | HCMC | 106.751 | 10.850 |
| geo298-p06 | t002 | HCMC | 106.660 | 10.760 |
| geo298-p07 | t001 | Hanoi | 105.834 | 21.028 |
| geo298-p08 | t002 | Da Nang | 108.202 | 16.054 |

These values are meaningful only for the sample coordinates, not postal coordinates of real places.

### 10.2. Idempotent Seed Script

Run in `mongosh`:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_geo_validation_lab_298");
  const places = lab.getCollection("lab_places");
  const tag = "geo-validation-v1";

  const rows = [
    ["geo298-p01", "t001", "hcm", "Central A", 106.700, 10.776],
    ["geo298-p02", "t001", "hcm", "Central B", 106.705, 10.782],
    ["geo298-p03", "t001", "hcm", "Central C", 106.713, 10.792],
    ["geo298-p04", "t001", "hcm", "North D",   106.724, 10.807],
    ["geo298-p05", "t001", "hcm", "East E",    106.751, 10.850],
    ["geo298-p06", "t002", "hcm", "West F",    106.660, 10.760],
    ["geo298-p07", "t001", "hanoi", "HN G",    105.834, 21.028],
    ["geo298-p08", "t002", "danang", "DN H",   108.202, 16.054]
  ];

  for (const row of rows) {
    const doc = {
      _id: row[0],
      labTag: tag,
      tenantId: row[1],
      city: row[2],
      name: row[3],
      location: {
        type: "Point",
        coordinates: [row[4], row[5]]
      }
    };

    places.replaceOne(
      { _id: doc._id, labTag: tag },
      doc,
      { upsert: true }
    );
  }

  places.createIndex(
    { location: "2dsphere" },
    { name: "ix_geo298_location" }
  );

  printjson({
    documents: places.countDocuments({ labTag: tag }),
    indexes: places.getIndexes().map(index => ({
      name: index.name,
      key: index.key
    }))
  });
})();
~~~

**Expected output:** 8 documents carrying the lesson's `labTag`; geospatial index **`ix_geo298_location`** present. Re-running the script uses `replaceOne`/`upsert` by fixed `_id` to reset the sample dataset cleanly.

**Data ownership note:** use a dedicated lab database and do not drop the collection. If a collection with the same name already holds unrelated data or an index with the same name has a different key pattern, stop and inspect instead of modifying or deleting those items.

### 10.3. Variable Declarations for Subsequent Examples

~~~javascript
const lab = db.getSiblingDB("mongo_geo_validation_lab_298");
const places = lab.getCollection("lab_places");
const tag = "geo-validation-v1";
~~~

If you open a new `mongosh` session, re-run those three declaration lines.

### 10.4. Inspecting All Existing Coordinates

~~~javascript
printjson(
  places.find(
    { labTag: tag },
    {
      _id: 1,
      tenantId: 1,
      city: 1,
      "location.coordinates": 1
    }
  )
  .sort({ _id: 1 })
  .toArray()
);
~~~

Results should match the eight-place table above.

## 11. `$near`: Finding Points Near a Location

### 11.1. Finding Locations Within a 3,000-Meter Radius

~~~javascript
const nearCenter = {
  type: "Point",
  coordinates: [106.700, 10.776]
};

const nearby = places.find(
  {
    labTag: tag,
    tenantId: "t001",
    location: {
      $near: {
        $geometry: nearCenter,
        $maxDistance: 3000
      }
    }
  },
  {
    _id: 1,
    name: 1,
    location: 1
  }
).toArray();

printjson(nearby);
~~~

In the lab, **p01, p02, and p03** are within 3 km of the center, while p04/p05 are farther away; p06 belongs to another tenant. Expected count is **3 documents** (per spherical distance math on the seeded dataset).

**The unit of `$maxDistance` is meters** when using a GeoJSON Point with `$near` and `2dsphere`. Passing **3** intending "3 km" searches only 3 meters.

### 11.2. `$near` Orders Results by Distance

A `$near` query normally returns results **in ascending distance order**. With the center right at `p01`, `p01` has distance ~0 and appears first.

Do not add another sort and still assume nearest-first ordering. If you want to sort by rental price while constraining to a region, design a separate query/ordering strategy.

### 11.3. `$near` Does Not Replace Access Control

The filter **`tenantId: "t001"`** in the example is an illustrative condition. In a real API, obtain `tenantId` from server-side authentication rather than trusting an arbitrary request parameter.

Never leak another tenant's results simply because they are geographically closer.

### 11.4. Only a Valid Point Is Suitable as a `$near` Center

~~~javascript
// Wrong when used as a GeoJSON Point $near center:
{
  type: "Polygon",
  coordinates: []
}
~~~

For standard `$near`/`$geoNear` queries, the query center is a **Point**. To find geometries intersecting or contained within a Polygon, use **`$geoWithin`** or **`$geoIntersects`**.

## 12. `$geoWithin`: Finding Points Inside a Region

### 12.1. Rectangular Polygon for the Lab

~~~javascript
const sampleArea = {
  type: "Polygon",
  coordinates: [
    [
      [106.695, 10.770],
      [106.730, 10.770],
      [106.730, 10.820],
      [106.695, 10.820],
      [106.695, 10.770]
    ]
  ]
};
~~~

This Polygon is an illustrative box covering part of central HCMC, **not an administrative border**.

### 12.2. Query

~~~javascript
const withinArea = places.find(
  {
    labTag: tag,
    tenantId: "t001",
    location: {
      $geoWithin: {
        $geometry: sampleArea
      }
    }
  },
  { _id: 1, name: 1 }
)
.sort({ _id: 1 })
.toArray();

printjson(withinArea);
~~~

**Expected result:** **p01, p02, p03, p04**. `p05` lies farther northeast, `p06` is outside and belongs to another tenant, and `p07` is in Hanoi.

**`$geoWithin` does not automatically sort results by distance.** Sorting by `_id` in the example is purely for deterministic output.

### 12.3. Validate Polygon Input Before Querying

Never pass a user-drawn Polygon directly into `$geoWithin` without validating:

1. Does it have **`type: "Polygon"`** or another supported type?
2. Do rings have enough points and proper closure?
3. Are there self-intersections or topologically invalid holes?
4. Does it cross the antimeridian or exceed a hemisphere?
5. Is the user authorized to query this region?
6. Is the geometry simple enough to stay within API time/resource limits?

A malformed input region can cause empty results or unexpectedly huge scans, impacting both performance and correctness.

### 12.4. `$geoWithin` Does Not Always Require an Index

MongoDB can evaluate some `$geoWithin` queries **without a geospatial index**, though it must read and inspect more documents. On large collections, a `2dsphere` index is very helpful for narrowing candidates.

Do not equate "the query returned the right answer on 8 samples" with "the query is guaranteed to use an index on 8 million samples."

## 13. `$geoIntersects` and Intersecting Regions

### 13.1. Difference Between Within and Intersects

**`$geoWithin`** asks whether a geometry lies inside the query region under the corresponding semantics.

**`$geoIntersects`** asks whether the indexed geometry **intersects** the query geometry.

For example, a route **crossing** a region without lying completely inside it intersects the Polygon even though the entire route is not inside the Polygon.

~~~text
Region polygon:   +----------------+
                  |                |
Route line:  -----+----------------+-----
                  |                |
                  +----------------+

The route intersects the Polygon but does not lie completely inside the region.
~~~

### 13.2. Dedicated Geofence Example

Suppose a **`lab_geofences`** collection stores region geometries:

~~~javascript
{
  _id: "geo298-fence-01",
  labTag: "geo-validation-v1",
  tenantId: "t001",
  name: "Area A",
  boundary: {
    type: "Polygon",
    coordinates: [
      [
        [106.695, 10.770],
        [106.730, 10.770],
        [106.730, 10.820],
        [106.695, 10.820],
        [106.695, 10.770]
      ]
    ]
  }
}
~~~

On a separate geofence collection populated with valid geometry and indexed:

~~~javascript
db.getSiblingDB("mongo_geo_validation_lab_298")
  .getCollection("lab_geofences")
  .createIndex({ boundary: "2dsphere" });
~~~

Query geofences containing/intersecting a Point:

~~~javascript
const geofences = db.getSiblingDB("mongo_geo_validation_lab_298")
  .getCollection("lab_geofences");

geofences.find({
  tenantId: "t001",
  boundary: {
    $geoIntersects: {
      $geometry: {
        type: "Point",
        coordinates: [106.705, 10.782]
      }
    }
  }
});
~~~

**This example only defines the schema and query**; Section 10 did not seed geofences. To run it and observe results, insert a valid geofence document into your lab collection. Do not mistake an empty result for an operator bug if the collection is empty.

### 13.3. Objects Touching a Boundary

A point lying right on a boundary line can be sensitive to coordinate representation, numerical precision, and operator rules. If outcomes affect **delivery zoning or legal obligations**:

- Use high-quality source geometry.
- Design appropriate business tolerances/buffers.
- Test points directly on and immediately on either side of the boundary.
- Never rely on map pixel rendering to verify exact geometric relationships.

## 14. `$geoNear`: Including Distance in Aggregation

### 14.1. Returning Distance for Display

~~~javascript
const results = places.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.700, 10.776]
      },
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 3000,
      spherical: true,
      query: {
        labTag: tag,
        tenantId: "t001"
      }
    }
  },
  {
    $project: {
      _id: 1,
      name: 1,
      distanceMeters: 1
    }
  },
  { $limit: 10 }
]).toArray();

printjson(results);
~~~

Purpose:

- **near**: center Point `[lon,lat]`.
- **distanceField**: output field holding the distance to each point.
- **maxDistance**: 3,000 m limit in this GeoJSON example.
- **query**: additional tenant/lab predicates.
- **key**: specifies the geo field, especially helpful when a collection has multiple geospatial indexes/fields.

### 14.2. Position of `$geoNear` in the Pipeline

**`$geoNear` must be the first stage** in an aggregation pipeline per MongoDB rules; never place a `$match` before it as in ordinary aggregation pipelines.

Incorrect:

~~~javascript
db.places.aggregate([
  { $match: { tenantId: "t001" } },
  { $geoNear: { /* ... */ } }
]);
~~~

Correct: place the tenant condition inside **`$geoNear.query`**, then follow with `$project`, `$limit`, and other stages.

### 14.3. Required Index

**`$geoNear`** and **`$near`** require a matching geospatial index; without one, the command can fail. In the lab, **`{location:"2dsphere"}`** is created beforehand.

If a collection has multiple geo fields/indexes, specify **`key`** explicitly and check the planner; never let adding a second index make an aggregation ambiguous.

### 14.4. Distance Is a Geographic-Model Approximation

Point-to-point distance on a spherical Earth model is not equivalent to:

- Driving distance.
- Actual walking distance.
- Road travel time.
- 3D distance accounting for elevation and building floors.

To find apartments "within a 10-minute walk of a train station," `2dsphere` `$geoNear` is only an initial spatial filter; real distance/duration requires road-network routing data.

## 15. Compound `2dsphere` Indexes and Multi-Condition Queries

### 15.1. Why Add `tenantId` to the Index?

APIs frequently query:

~~~javascript
{
  tenantId: "t001",
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.700, 10.776]
      },
      $maxDistance: 3000
    }
  }
}
~~~

In a large multi-tenant collection, an index solely on `location` may scan many nearby places belonging to other tenants before filtering them out. A compound **`tenantId + location`** index is a candidate:

~~~javascript
places.createIndex(
  {
    tenantId: 1,
    location: "2dsphere"
  },
  {
    name: "ix_geo298_tenant_location"
  }
);
~~~

This is a **candidate index**, not a promise that the planner will always choose it or that it beats a location-only index for every query. Verify with `explain` on representative data.

### 15.2. Compound `2dsphere` Remains Sparse on the Geo Field

In a compound index combining **`2dsphere`** and regular fields, **the presence of the geo field** determines whether a document is indexed per `2dsphere` sparse semantics.

For example, the document:

~~~javascript
{
  tenantId: "t001",
  name: "Location unknown",
  location: null
}
~~~

is not included in the compound `2dsphere` index just because `tenantId` has a value.

**Never treat `{tenantId:1, location:"2dsphere"}` as an ordinary B-tree index that can replace all `tenantId` indexes for documents missing a location.**

### 15.3. Combining Status / Category

A workload:

~~~javascript
{
  tenantId: "t001",
  status: "active",
  category: "apartment",
  location: {
    $geoWithin: { $geometry: sampleArea }
  }
}
~~~

Candidate indexes can combine equality fields and the geo field per server-supported rules. However, adding more fields means:

- Larger index storage footprint.
- Higher write and update costs.
- Risk that the query planner chooses another index.
- Prefix/sort semantics that differ from pure numeric/string compound B-trees.

For rapidly changing status/category filters, evaluate whether they belong in the index, as post-geo filters, or in a separate read model.

### 15.4. Do Not Let One Rare Query Dictate Every Index

Suppose:

~~~text
Q1: find apartments within 3 km by tenant, 80% of traffic
Q2: check if a Point belongs to a geofence, 15%
Q3: report all Points nationwide, 5%
~~~

Prioritize indexing for **Q1** first. Q3 may warrant a separate batch job or aggregation. Creating dozens of indexes for every field combination slows down writes without proportional benefit.

## 16. Important Limitations of Geospatial Indexes

### 16.1. An Index Does Not Catch Every Data Error

A Point in the wrong city whose lon/lat stay within bounds will still be indexed cleanly. A structurally valid Polygon with outdated boundaries will also be indexed cleanly.

Numeric/geometric validity **is not business correctness**.

### 16.2. A Geospatial Index Is Not a Unique Constraint

Two different stores can share the exact same coordinates. A `2dsphere` index cannot act like a unique index to enforce that only one document exists at a location.

If business logic requires each **`tenantId + locationId`** to be unique:

~~~javascript
db.places.createIndex(
  { tenantId: 1, locationId: 1 },
  { unique: true }
);
~~~

This is a **separate unique index on a business key**, not a unique constraint on geometry. In sharded collections, unique index rules also depend on the shard key and server version.

### 16.3. Geospatial Indexes Cannot Serve as Shard Keys

You cannot use a **`2dsphere` index directly as a shard key index** the way standard shard keys work. A **sharded collection can have a geospatial index**, but its shard key must follow sharding rules.

Consequence: a geo-only query may scatter-gather across multiple shards if the shard key does not let `mongos` narrow target shards. A good `2dsphere` index **on each shard** does not guarantee hitting only one shard.

### 16.4. Geospatial Indexes Do Not Support Arbitrary Covered Queries

Geospatial indexes have limitations compared to standard B-tree indexes—in particular, **you cannot rely on them to fully cover a query** the way a B-tree index holds every filtered and projected field.

A `$near` operation may need to compute distance and fetch documents; seeing `IXSCAN` in `explain` **does not** mean zero documents were read.

### 16.5. Complex Geometries Create Heavy Index and Query Work

A Polygon with tens of thousands of vertices or an ultra-complex MultiPolygon can:

- Incur heavy geometric processing costs.
- Generate excessive internal spatial index keys/cells.
- Increase storage size and index build duration.
- Make intersection/containment queries CPU-intensive and slow.
- Hit the **16 MiB BSON** document size limit or other operational limits.

**There is no single universal vertex cap across all geometries, server versions, and index settings** that substitutes for real measurement. Enforce **business limits** on vertices, holes, and complexity, apply controlled simplification, and test on representative data.

### 16.6. Geospatial Indexes and Array Data

A `location` field can hold a MultiPoint/MultiPolygon or Array types supported by MongoDB semantics. When storing multiple geometries in one document, distinguish between:

- A valid GeoJSON **`MultiPoint`**.
- An **Array of GeoJSON Point documents**.
- An **Array of legacy coordinate pairs**.

These forms are not indexed or queried identically and can multiply index entries. Design a clear schema per use case rather than using an untyped nested Array to "hold everything."

### 16.7. Distance Units and Index Types Are Not Freely Interchangeable

With GeoJSON Point + `2dsphere`:

~~~javascript
$maxDistance: 3000 // meters
~~~

In some legacy syntaxes or operators like **`$centerSphere`**, the radius uses **radians**, not meters. Example:

~~~javascript
const radiusKm = 3;
const earthRadiusKmApprox = 6378.1;

places.find({
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.700, 10.776],
        radiusKm / earthRadiusKmApprox
      ]
    }
  }
});
~~~

This example converts **approximately 3 km into radians** for `$centerSphere`; do not confuse it with GeoJSON `$near`, which uses `$maxDistance` in meters.

### 16.8. Do Not Arbitrarily Mix Geospatial Operators with Text/Ranking

Certain query operators and aggregation stages have restrictions when combined with **`$near`**, **`$geoNear`**, **`$text`**, or custom sort/ranking logic. If a product needs "search apartments by keyword, then rank by both text relevance and distance," design an appropriate pipeline or search engine and verify version support—do not assume two separate indexes merge two ranking models automatically.

### 16.9. An Index Does Not Guarantee Constant-Time Queries

Even with a proper index, a query like:

~~~javascript
{
  location: {
    $geoWithin: {
      $geometry: hugePolygon
    }
  }
}
~~~

can return millions of documents. When result counts are huge, document reads, network transfer, and serialization remain expensive. Indexes narrow candidates—they do not eliminate output volume costs.

## 17. JSON Schema Validation: Catching Structural Errors in the Database

### 17.1. Second Line of Defense

MongoDB supports collection-level **schema validation** via **`$jsonSchema`**. It blocks missing fields or malformed structures even if an application forgets to run client/API validation.

Example creating a dedicated **Point-only** collection:

~~~javascript
db.getSiblingDB("mongo_geo_validation_lab_298")
  .createCollection("lab_point_only", {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["tenantId", "location"],
        properties: {
          tenantId: {
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
                  bsonType: [
                    "double", "int", "long", "decimal"
                  ]
                }
              }
            }
          }
        }
      }
    },
    validationLevel: "strict",
    validationAction: "error"
  });
~~~

**Run this snippet only once on a new lab database**; if the collection already exists, `createCollection` errors instead of silently replacing the validator. This is a DDL example, not part of Section 10's required seed.

### 17.2. What Does JSON Schema Validate?

The example above checks:

- Documents require `tenantId` and `location`.
- `location` must be an object.
- `type` must be `"Point"`.
- `coordinates` must have exactly two elements.
- Both elements must be one of the listed BSON numeric types.

However, it **does not fully validate**:

- `longitude` in `[-180,180]` and `latitude` in `[-90,90]` by exact array position.
- Absence of `NaN`/`Infinity` across all sources/types.
- Whether the Point falls in the right city.
- Ingestion system CRS.
- Complex Polygon geometries (since this schema only allows Points).

When per-element Array ranges are needed, add positional validation rules or application checks depending on your server version's expressiveness. **Do not assume a simple JSON Schema using homogeneous `items` checks the distinct bounds of longitude and latitude.**

### 17.3. Do Not Use a Point-Only Schema on a Mixed Collection

If the same collection stores Points, Lines, and Polygons, a Point-only validator will reject valid documents of other types.

Depending on requirements:

- Split **`places`** (Point) and **`geofences`** (Polygon) into two collections.
- Use a type-branched schema with supported rules.
- Accept only the GeoJSON types handled by your consumers.

Accepting every `GeometryCollection` variant is not "flexibility"—a narrow, consistent schema aligned with the application makes data quality far easier to enforce.

### 17.4. `validationAction` and Legacy Data

When adding or tightening a validator on a collection with existing legacy documents, evaluate **`validationLevel`** and **`validationAction`**:

- Choose **`error`** to reject invalid writes.
- Transitional strategies may use `warn` or targeted conditions while cleaning legacy records.
- Enabling strict validation immediately can block updates to existing legacy documents.

Plan cleanup/migration before tightening validation in production. **Schema validation does not automatically repair existing bad data.**

## 18. Quarantining Bad Geometry Data Before Indexing

### 18.1. Do Not Write Bad Data Hoping the Index Handles It

For external CSV/JSON imports, design a pipeline:

~~~text
Source file / ingestion API
          |
          v
     Parse raw input
          |
          v
  Validate schema/range/CRS
          |
          v
 Check geometry topology
          |
          +---------------------+
          |                     |
        VALID                INVALID
          |                     |
          v                     v
  Indexed collection     Quarantine records
          |              + reason + raw input
          v                     |
      Query API          Manual fix / reconcile
~~~

### 18.2. Quarantine Record Sample

~~~javascript
{
  _id: "geo298-invalid-001",
  sourceId: "import-file-12-row-90",
  receivedAt: ISODate("2026-01-15T12:00:00Z"),
  rawLocation: {
    type: "Point",
    coordinates: [10.776, 106.700]
  },
  status: "quarantined",
  errors: [
    "latitude outside [-90,90]",
    "suspected axis swap"
  ]
}
~~~

If `rawLocation` can hold huge payloads, sensitive data, or malicious input, enforce retention limits, access control, and size caps. Never dump unbounded raw input into production logs.

### 18.3. Example Pre-Insert Input Filtering

~~~javascript
const candidateLocations = [
  {
    id: "candidate-good",
    location: {
      type: "Point",
      coordinates: [106.700, 10.776]
    }
  },
  {
    id: "candidate-swapped",
    location: {
      type: "Point",
      coordinates: [10.776, 106.700]
    }
  },
  {
    id: "candidate-text",
    location: {
      type: "Point",
      coordinates: ["106.700", "10.776"]
    }
  }
];

for (const row of candidateLocations) {
  const errors = validateGeoPoint(row.location);
  if (errors.length) {
    print("QUARANTINE " + row.id);
    printjson(errors);
    continue;
  }

  print("READY FOR INSERT " + row.id);
  // Only after other business/topology checks,
  // write into the collection that has the 2dsphere index.
}
~~~

This snippet assumes **`validateGeoPoint`** was declared in Section 5. It performs no writes; it illustrates rejecting bad records before the index has to handle them.

### 18.4. Do Not "Auto-Swap" Every Coordinate Pair

While `[10.776,106.700]` fails latitude bounds, suggesting an axis swap, `[40,10]` falls within valid ranges in both orders. Range-based auto-swapping can:

- Fix some corrupted records.
- Silently corrupt records that were already correct.
- Destroy evidence of upstream bugs.

The right workflow knows **each source's schema/CRS**, logs applied transformations, and verifies positions after conversion.

## 19. When a `2dsphere` Index Build Fails

### 19.1. Typical Symptoms

For example, an index build fails with an error such as:

~~~text
Unable to extract geo keys
... invalid GeoJSON geometry ...
~~~

Exact wording varies across MongoDB versions; do not hardcode string parsing on this message to classify business errors.

### 19.2. Remediation Workflow

1. **Preserve the error log and server/index version.**
2. Check whether the collection contains GeoJSON Points, Polygons, legacy pairs, or a mix.
3. Measure missing/null separately from fields **having a malformed value**.
4. Scan for structural and range errors using an application capable of inspecting the corresponding BSON types.
5. For Polygons, run GIS tooling to verify topology.
6. Fix or quarantine confirmed bad documents per data policy.
7. Re-run the index build in staging/proper maintenance flow.
8. Use **`getIndexes()`**, **`explain()`**, and sample queries to confirm the index works.

**Do not** impulsively drop the collection or strip the `location` field just to make the index build turn green if the application still needs geospatial data. Deleting data recklessly destroys vital information.

### 19.3. Legacy Schema Migration Strategy

Suppose an old source has:

~~~javascript
{
  _id: "old-001",
  lat: 10.776,
  lng: 106.700
}
~~~

And we want to migrate to:

~~~javascript
{
  _id: "old-001",
  lat: 10.776,
  lng: 106.700,
  location: {
    type: "Point",
    coordinates: [106.700, 10.776]
  }
}
~~~

Workflow:

- Verify `lat`/`lng` types, ranges, and source contract.
- Build `location` from **`[lng,lat]`**, not `[lat,lng]`.
- Tag records with a migration version or converted status.
- Backfill in resumable batches; log valid/error counts.
- Verify samples against maps and business geography.
- Only create/enforce the `2dsphere` index after unindexable records are resolved.

If the collection serves live production traffic, design a **dual-read/dual-write or migration window** strategy based on compatibility, never updating millions of records without checkpoints.

## 20. `explain` and Measuring Geospatial Query Performance

### 20.1. Inspecting Indexes

~~~javascript
printjson(
  places.getIndexes().map(index => ({
    name: index.name,
    key: index.key
  }))
);
~~~

Goal: verify **`location:"2dsphere"`** exists and see any compound indexes present.

### 20.2. Explaining a `$near` Query

~~~javascript
const nearPlan = places.find({
  labTag: tag,
  tenantId: "t001",
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.700, 10.776]
      },
      $maxDistance: 3000
    }
  }
}).explain("executionStats");

printjson(nearPlan);
~~~

Depending on server version and query engine, you may see stages/details related to **`GEO_NEAR_2DSPHERE`**, index scans, and documents examined. Never write brittle code relying on a single stage name; `explain` output evolves across versions.

### 20.3. Explaining `$geoWithin`

~~~javascript
const withinPlan = places.find({
  labTag: tag,
  tenantId: "t001",
  location: {
    $geoWithin: {
      $geometry: sampleArea
    }
  }
}).explain("executionStats");

printjson(withinPlan);
~~~

In this session, **`sampleArea`** must be declared as in Section 12. If switching to a new terminal, re-declare it.

### 20.4. Questions to Answer

| Metric / Observation | Question |
| --- | --- |
| **`winningPlan`** | Did the server use the intended geospatial index? |
| **`totalKeysExamined`** | How many index entries/cells were examined? |
| **`totalDocsExamined`** | How many documents were actually read/examined? |
| **`nReturned`** | How many documents were returned? |
| **`executionTimeMillis`** | How long did the `explain` execution take? |
| **FETCH / additional filters** | Did it have to filter status, tenant, or category after the geo index? |
| **Sort/limit** | Was an expensive sort needed, or were too many results returned? |

A query returning 5 documents after examining millions of candidates likely needs optimization. Conversely, a query returning millions of documents can be slow due to **output volume**, even if the index filtered out other candidates.

### 20.5. Never Benchmark with 8 Points

The lab has only eight Points, so:

- Latency is tiny and easily skewed by caches and the optimizer.
- The query planner may choose a plan unrepresentative of production.
- All geometries are simple, failing to reflect complex Polygon costs.

To benchmark properly, use realistic geographic distributions, tenant cardinality, search radii, polygon sizes, point density, write rates, and resource limits.

## 21. Blocking Overly Broad or Overly Complex Geospatial Queries

### 21.1. Radius Limits

Suppose an application accepts **`radiusMeters`**:

~~~javascript
function validateRadiusMeters(value) {
  if (!Number.isFinite(value) ||
      value <= 0 ||
      value > 50000) {
    throw new Error(
      "Radius must be > 0 and <= 50,000 meters."
    );
  }
  return value;
}
~~~

The **50,000 m** threshold is merely a hypothetical API policy, not a general MongoDB limit.

If clients can send a radius of thousands of kilometers against a collection of tens of millions of places, an index cannot prevent one request from generating massive output.

### 21.2. Input Geometry Limits

For user-drawn Polygons, enforce limits on:

- Maximum **vertices**.
- Maximum **rings/holes**.
- Maximum Polygons in a MultiPolygon.
- Request JSON/BSON payload size.
- Area/extent caps per access permissions.
- Query deadline / `maxTimeMS`.

Set these limits based on benchmarks and required precision, not merely BSON's maximum document size.

### 21.3. Pagination and Ordering

~~~javascript
places.find({
  tenantId: "t001",
  location: {
    $geoWithin: {
      $geometry: sampleArea
    }
  }
})
.sort({ _id: 1 })
.limit(50);
~~~

Sorting by `_id` here ensures stable ordering, not distance ordering. If you want **nearest-first**, use `$near`/`$geoNear` with an appropriate pagination strategy. On large datasets, large `skip` values are costly; multi-key cursor pagination `(distance, id)` also requires care when positions or geometries change.

### 21.4. `maxTimeMS` and Cost Control

Example:

~~~javascript
places.find({
  tenantId: "t001",
  location: {
    $geoWithin: {
      $geometry: sampleArea
    }
  }
})
.maxTimeMS(3000)
.limit(100)
.toArray();
~~~

**`maxTimeMS`** enforces a processing deadline where supported; it does not replace rate limiting, result caps, and input geometry validation.

## 22. Common Mistakes

| Symptom | Cause | Remediation |
| --- | --- | --- |
| Point rejected with latitude > 90 | Sent `[lat,lon]` instead of `[lon,lat]` | Normalize source and validate |
| Point indexed, but in another country | Silent axis swap or bad geocoding | Check CRS and business region |
| All "unlocated" listings appear in the ocean | Used `[0,0]` as default | Use missing/null with clear policy |
| `2dsphere` index build fails | Some documents have invalid GeoJSON | Scan, quarantine, fix, then build |
| Polygon created, but query errors | Unclosed ring or wrong Array depth | Validate structure and topology |
| Bow-tie Polygon gives weird results | Self-intersection | Use GIS validator / controlled repair |
| Polygon hole covers outer area | Invalid hole topology or winding | Normalize rings per rules |
| Polygon across 180° covers huge area | Wrong antimeridian handling | Use proper spherical algorithms |
| Region larger than hemisphere inverted | Missing strict winding / special CRS | Check version Big Polygons docs |
| Query finds only places with coordinates | `2dsphere` is sparse; null/missing excluded | Understand missing-location semantics |
| Near query returns nothing with `maxDistance=3` | Thought 3 meant km, actually meters | Pass `3000` for 3 km with GeoJSON |
| `$geoWithin` points not nearest-first | Operator does not sort by distance | Use `$near`/`$geoNear` when needed |
| `$geoNear` fails to run | Missing geo index, wrong stage position, or ambiguous `key` | Create index, place first, specify `key` |
| `$near` returns another tenant's data | Wrong tenant filter | Derive tenant from auth context |
| Compound geo index misses docs without location | Sparse behavior on geo field | Create separate non-geo index if needed |
| Unique requirement at one coordinate not enforced | Geospatial index is not a unique business key | Create unique index on business ID |
| Treating geospatial index as shard key | `2dsphere` cannot act as shard key | Design shard key per sharding rules |
| Region-wide query still slow | Huge geometry or huge result set | Cap area, paginate, cache |
| Large geometry consumes heavy resources | Too many vertices, rings, or index cells | Cap complexity, simplify validly |
| Query accurate, but wrong driving route | Geographic distance differs from road distance | Use routing engine when needed |
| Floor-level checks fail | `2dsphere` is not a 3D index | Store and check altitude/floor separately |
| Outdated boundary data | Valid Polygon from stale source | Track source versions and effective dates |
| Point-only `$jsonSchema` rejects Polygons | Validator hardcodes `type: Point` | Separate collections or branch schema |
| Auto-swap corrupts valid points | Guessing CRS from range checks | Use source metadata and explicit transforms |
| Using `$near` to find Polygons containing a Point | Wrong operator / center geometry | Use `$geoIntersects`/`$geoWithin` properly |
| Seeing fast `explain` on 8 points and assuming production is fast | Lab dataset is too small | Benchmark on representative dataset |

## 23. Geospatial Ingestion and Design Checklist

### 23.1. Before Accepting a Point

1. Know the exact **CRS** of the source.
2. Normalize to **`[longitude,latitude]`** in degrees.
3. Reject arbitrary Strings, `NaN`, `Infinity`, wrong element counts, and out-of-range values.
4. Distinguish missing/null from `[0,0]`.
5. Check region and accuracy per business contract.
6. Record provenance and geocoding source when traceability is needed.
7. Never trust `tenantId` from an unauthenticated request.

### 23.2. Before Accepting a Polygon / MultiPolygon

1. Check `type` and exact Array nesting depth.
2. Check all positions are valid lon/lat.
3. Check rings have at least four positions and are closed.
4. Check topology: self-intersection, holes, degenerate edges, polygon relationships.
5. Handle antimeridian / large regions / strict winding where applicable.
6. Cross-check boundaries against source data and precision.
7. Enforce vertex/hole/area limits and keep raw source for reconciliation.

### 23.3. Before Creating a `2dsphere` Index

1. Count documents with valid geo fields, missing/null, and invalid values.
2. Check whether the schema is Point-only or mixed geometry.
3. Quarantine unindexable records.
4. Choose indexes by query shape (geo-only vs. tenant + geo).
5. Budget storage, index build time, and write impact.
6. Never rely on geospatial indexes for unique or shard-key semantics.
7. Verify with `getIndexes`/`explain` after completion.

### 23.4. Before Launching a Geospatial API to Production

1. Validate radius and geometry inputs.
2. Bind tenant, status, and category from security context.
3. Cap result counts and pagination.
4. Set query deadlines and rate limits.
5. Measure p95/p99 latency across radius, density, and complexity.
6. Log GeoJSON errors safely with IDs for investigation.
7. Monitor missing-location rates, import failures, and outliers.
8. Establish processes for updating geofences/boundaries and testing near edges.

## 24. Hands-On Exercises

### Exercise 1 — Distinguishing Longitude and Latitude

Given source pair **`latitude=10.776, longitude=106.700`**, write the valid GeoJSON Point. Explain why `[10.776,106.700]` is wrong and why another swapped pair could still pass range validation.

### Exercise 2 — Validating Coordinate Types

Write a function that rejects invalid inputs from:

~~~javascript
[106.700, 10.776]
["106.700", "10.776"]
[Infinity, 10.776]
[106.700]
[106.700, 120]
~~~

Which pair in the list is structurally and range-valid? When are additional business bounds needed?

### Exercise 3 — Null vs. `0,0`

Compare missing `location`, `location:null`, and GeoJSON Point `[0,0]`. How should an API represent "no location yet" without distorting maps?

### Exercise 4 — CRS

A system sends Web Mercator coordinates, while the MongoDB collection uses `2dsphere`. Why can you not store x/y directly as GeoJSON lon/lat? What must you do before creating the index?

### Exercise 5 — Polygon Ring

Write a rectangular Polygon with four distinct vertices and a valid closed ring. Explain why a ring requires at least four positions.

### Exercise 6 — Self-Intersecting Polygon

Given the bow-tie ring in Section 6.3, does a ring-closure check detect the error? Why is topological validation needed alongside structural checks?

### Exercise 7 — Hole

A Polygon has a hole lying completely outside the outer ring. State why it is invalid and how to handle it in an ingestion pipeline.

### Exercise 8 — Antimeridian

A small region lies between `179°E` and `-179°W`. Why does a simple longitude filter from `-179` to `179` fail the intent? Describe what spherical geography handling is needed.

### Exercise 9 — Index Types

Compare **`2d`** and **`2dsphere`** for an apartment-search app spanning multiple cities. Explain the role of spherical geometry and distance units.

### Exercise 10 — Creating the Lab

Run the seed script in Section 10. Verify 8 Points, `getIndexes`, and a query reading back all coordinates.

### Exercise 11 — `$near`

Find places for tenant `t001` within 3,000 meters of `[106.700,10.776]`. Predict the three closest Points in the lab and explain why `p06` does not appear.

### Exercise 12 — `$geoWithin`

Use `sampleArea` from Section 12. Fetch places belonging to tenant `t001` inside the region. Predict the four `_id` values and explain why `$geoWithin` does not automatically sort by distance.

### Exercise 13 — `$geoIntersects`

Create a geofence Polygon in a separate lab collection and create a `2dsphere` index on `boundary`. Write a query finding zones intersecting a Point. Compare this question with "Points lying inside a Polygon."

### Exercise 14 — `$geoNear`

Write an aggregation returning `name` and `distanceMeters`, filtering tenant `t001` with `maxDistance: 3000`. Why must `$geoNear` be first in the pipeline, and what role does `key` play when multiple geospatial fields exist?

### Exercise 15 — Sparse Index

A collection has 100 documents: 20 lack `location`, 10 have `location:null`, and the rest have valid Points. Why does the geospatial index not automatically reference all 100 documents? What differs if 5 Points have out-of-range latitudes?

### Exercise 16 — Failed Index Build

A legacy collection contains one unclosed Polygon and one valid Point. When creating a `2dsphere` index fails, what should you do? Propose a scan, quarantine, repair, and rebuild workflow without dropping the whole collection.

### Exercise 17 — Compound Geospatial Index

An API accepts `tenantId` and a center point, always searching within a 5 km radius. Compare **`{location:"2dsphere"}`** and **`{tenantId:1,location:"2dsphere"}`**. How do you measure effectiveness on a real dataset?

### Exercise 18 — Unique Business Key

Two apartments in the same building share the exact same coordinates. If business rules only require `listingId` to be unique per tenant, which index should you use? Why not use `2dsphere` as a unique index?

### Exercise 19 — Sharding

A sharded collection has a `2dsphere` index on `location` and a shard key on `tenantId`. How can a `$near`-only query without `tenantId` end up contacting multiple shards? Why can you not use a `2dsphere` index in place of a shard key index?

### Exercise 20 — Reading Query Explain

Run `explain("executionStats")` for `$near` and `$geoWithin` in the lab. Record fields/stages showing the geospatial index, keys/documents examined, and `nReturned`. Why can a single run on eight documents never prove production latency?

### Exercise 21 — Capping Vertex Count

An API receives a MultiPolygon with 50,000 vertices. What must you check before executing the query? Analyze BSON limits, index cost, topology, and simplification within business tolerance.

### Exercise 22 — Data Quality

A stationary device in HCMC suddenly reports a valid Point in Europe. Will the index catch the bad data? Propose checks for source/CRS, geofencing, travel speed, and error retention.

### Exercise 23 — Measurement Units

Compare **`$near` with GeoJSON `$maxDistance: 3000`** and **`$centerSphere` with radius in radians**. Why can you not pass `3` directly to both to represent 3 km?

### Exercise 24 — Multi-Layer Validation

Design an API contract accepting a GeoJSON Point for listings: Number types, lon/lat bounds, tenant, required/optional location, schema validator, `2dsphere` index, and quarantine. Distinguish errors returned to clients from errors requiring operational investigation.

### Exercise 25 — Migrating Legacy `lat`/`lng`

An old collection stores `lat`/`lng` in two separate fields, sometimes as Strings. Describe a migration pipeline to GeoJSON `location` with checkpoints, proper CRS/type conversion, error detection, and safe index creation.

### Exercise 26 — Listing Places With and Without Coordinates

A UI needs to display both un-geocoded listings and listings within a 3 km radius. Why should you not try to use a single `$near` query to fetch both groups? Design a two-step query or explicit read model.

### Exercise 27 — Legal Boundaries

A point sits right next to a delivery boundary. The Polygon was drawn roughly on a map and GPS has error. What rules are needed before deciding fees or delivery eligibility? Why does valid geometry not equal legally sufficient accuracy?

### Exercise 28 — Post-Migration Reconciliation

After backfilling one million GeoJSON Points and building a geospatial index, propose a reconciliation report: total documents, missing/null, valid/invalid, outlier rate, index build errors, city breakdown, sample queries, and p95 performance.

## 25. Official Reference Documentation

- MongoDB Manual — [Geospatial Queries](https://www.mongodb.com/docs/manual/geospatial-queries/).
- MongoDB Manual — [2dsphere Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/).
- MongoDB Manual — [2d Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2d/).
- MongoDB Manual — [GeoJSON Objects](https://www.mongodb.com/docs/manual/reference/geojson/).
- MongoDB Manual — [$near](https://www.mongodb.com/docs/manual/reference/operator/query/near/).
- MongoDB Manual — [$geoWithin](https://www.mongodb.com/docs/manual/reference/operator/query/geoWithin/).
- MongoDB Manual — [$geoIntersects](https://www.mongodb.com/docs/manual/reference/operator/query/geoIntersects/).
- MongoDB Manual — [$geoNear](https://www.mongodb.com/docs/manual/reference/operator/aggregation/geoNear/).
- MongoDB Manual — [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/).
- MongoDB Manual — [$jsonSchema](https://www.mongodb.com/docs/manual/reference/operator/query/jsonSchema/).
- MongoDB Manual — [Geospatial Index Restrictions](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/restrictions/).
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).
- GeoJSON — [RFC 7946](https://www.rfc-editor.org/rfc/rfc7946).

**Key takeaways:** **A GeoJSON Point uses `[longitude,latitude]` in WGS84**, with finite numeric values and valid geographic bounds. **Polygons must also have valid rings and topology**, not merely the right `type` and vertex count. A **`2dsphere` index** accelerates spherical searches but **does not fix wrong CRSs, does not catch every business-wrong point, does not replace unique indexes or shard keys**, and can reject index builds when existing GeoJSON data is invalid. To build a reliable system, **validate inputs across multiple layers, quarantine bad geometries, use `$near`/`$geoWithin`/`$geoIntersects` with the right semantics, inspect `explain`, and bound query complexity**. A fast geospatial query is only meaningful when **coordinates are right, geometry is right, and the user is authorized to see the results**.
