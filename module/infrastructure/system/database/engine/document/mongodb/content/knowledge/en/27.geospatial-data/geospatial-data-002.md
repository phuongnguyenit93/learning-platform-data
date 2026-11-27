# Point, LineString, Polygon, and Supported Geometries in MongoDB

## 1. Introduction: How Do a Position, a Route, and a Region Differ?

Imagine a delivery application that needs to store:

- A driver's current location.
- A route traveled across multiple coordinates.
- A warehouse's delivery coverage area.
- Multiple pickup locations belonging to the same partner.
- Two disconnected route segments.
- A service area consisting of multiple separate zones.
- A composite geographic entity that has a station, a route, and a zone.

If you only store two numbers, `latitude` and `longitude`, for everything, you cannot adequately represent these geometries. MongoDB supports **GeoJSON**, a way to represent geographic geometries using JSON/BSON documents. The key types include **Point**, **LineString**, **Polygon**, and their variants **MultiPoint**, **MultiLineString**, **MultiPolygon**, and **GeometryCollection**.

This lesson focuses on **geometry and data structures**, and then connects them to MongoDB's geospatial queries so you understand why choosing the right shape matters.

### 1.1. Questions to Answer

1. How does a `Point` differ structurally from a `LineString` and a `Polygon`?
2. Why is `coordinates: [106.7, 10.8]` **not** `[latitude, longitude]`?
3. Why must a polygon have a **closed ring**, whereas an ordinary LineString does not need to be closed?
4. How is a polygon with **holes** represented using nested arrays?
5. When should you use a `MultiPolygon` instead of a single `Polygon`?
6. How does a `GeometryCollection` differ from having multiple geospatial documents?
7. Which types can MongoDB index and query with **`2dsphere`**?
8. How do you avoid self-intersecting polygons, swapped coordinate orders, wrong CRSs, or misunderstandings of spherical terrain?

### 1.2. Mind Map

```text
                           GEOJSON GEOMETRY
                                  |
          +-----------------------+----------------------+
          |                       |                      |
     Single Point            Line/Boundary              Area
          |                       |                      |
        Point                 LineString               Polygon
          |                       |                      |
      MultiPoint             MultiLineString          MultiPolygon
          \                       |                      /
           \______________________|_____________________/
                                  |
                         GeometryCollection
                       (mix multiple geometries)
```

GeoJSON geometries are not only for rendering on a map. When represented properly, MongoDB can use them to **find the nearest places**, **check whether a location falls inside a region**, and **determine whether objects intersect**.

## 2. General Structure of a GeoJSON Geometry

### 2.1. Two Core Fields

For the six common geometry types, the basic form is:

```javascript
{
  type: "Point",
  coordinates: [106.70, 10.80]
}
```

Where:

- `type` is the **geometry type name string**, case-sensitive and type-specific, such as `"Point"` or `"LineString"`.
- `coordinates` is the **coordinate array with nesting depth varying by type**.

Specifically, `GeometryCollection` uses **`geometries`** to hold a list of sub-geometries rather than a single `coordinates` array.

### 2.2. Geometries Usually Live Inside Business Documents

Location example:

```javascript
{
  _id: "hub-001",
  name: "Test Delivery Hub",
  category: "warehouse",
  location: {
    type: "Point",
    coordinates: [106.70, 10.80]
  }
}
```

`location` is **a geometry field**. Fields like `name`, `category`, and `capacity` remain ordinary business document fields.

MongoDB does not require the entire document to follow GeoJSON structure at the top level. You can store multiple geospatial fields in one document—for example, `pickupLocation` as a Point and `deliveryArea` as a Polygon—and then create indexes on the field paths you need to query.

### 2.3. GeoJSON Geometry vs. GeoJSON Feature

In the broader GeoJSON ecosystem, there are `Feature` and `FeatureCollection` objects:

```json
{
  "type": "Feature",
  "properties": {
    "name": "Warehouse A"
  },
  "geometry": {
    "type": "Point",
    "coordinates": [106.70, 10.80]
  }
}
```

This is how GeoJSON wraps **geometry + properties**. However, when using a MongoDB **geospatial index**, index the **geometry field**—for example, `geometry`—and **do not** index a whole Feature field expecting `2dsphere` to unwrap arbitrary wrapper layers.

Example:

```javascript
db.geoFeatures292.createIndex({
  "feature.geometry": "2dsphere"
});
```

If you store a Feature under `feature`, the path `feature.geometry` is what contains the geometry with `type: "Point"` or another type.

## 3. Coordinate Order Rule: Longitude First, Latitude Second

### 3.1. The `[longitude, latitude]` Structure

For GeoJSON in MongoDB, a position has the form:

```text
[ longitude, latitude ]
  longitude  latitude
      x         y
```

Example:

```javascript
{
  type: "Point",
  coordinates: [106.70, 10.80]
}
```

In this example:

- `106.70` is **longitude**, the east/west position.
- `10.80` is **latitude**, the north/south position.

Do not swap it to:

```javascript
{
  type: "Point",
  coordinates: [10.80, 106.70] // WRONG: latitude = 106.70, out of range.
}
```

### 3.2. Value Ranges

| Component | Typical Valid Range | Meaning |
|---|---:|---|
| Longitude | -180 to 180 degrees | West ↔ East |
| Latitude | -90 to 90 degrees | South ↔ North |

The values must be **numbers**, not arbitrary strings:

```javascript
// Valid.
coordinates: [106.70, 10.80]

// Wrong data type for standard geometry.
coordinates: ["106.70", "10.80"]
```

### 3.3. Why Is It Easily Swapped?

Some map APIs or user interfaces display coordinates in **latitude first, longitude second** order, for example:

```text
lat = 10.80
lng = 106.70
```

When converting to GeoJSON, map them explicitly:

```javascript
const lat = 10.80;
const lng = 106.70;

const geometry = {
  type: "Point",
  coordinates: [lng, lat]
};
```

If the data lies in a region where swapping both numbers still keeps them within valid ranges, MongoDB **may not raise an error**, yet the point ends up somewhere else on Earth. Thus, **range checking is not enough**; check the source's axis order and visualize on a map whenever possible.

### 3.4. The WGS84 Reference System

MongoDB uses a spherical model with the **WGS84 / EPSG:4326** geographic reference system for standard GeoJSON queries.

Number pairs `[x, y]` in a planar coordinate system measured in meters (such as GIS data using a local projection) **must not be renamed to GeoJSON longitude/latitude and fed directly into `2dsphere`**.

If the GIS source uses a different reference system:

1. Identify the **input CRS**.
2. Transform the coordinates using an appropriate GIS library to WGS84 longitude/latitude.
3. Verify axis order.
4. Write the transformed geometry to MongoDB.

### 3.5. The Third Elevation Element

In the GeoJSON standard, a position can include a third element representing elevation:

```javascript
{
  type: "Point",
  coordinates: [106.70, 10.80, 15.5]
}
```

However, `2dsphere` geospatial queries primarily evaluate **two dimensions on a spherical surface**; do not expect MongoDB to automatically compute **3D distance with elevation** or distinguish two objects on different building floors.

If the application needs accurate height, store it separately:

```javascript
{
  location: {
    type: "Point",
    coordinates: [106.70, 10.80]
  },
  altitudeMeters: 15.5
}
```

and implement 3D logic in the application or a specialized GIS tool. Clearly define the unit and vertical datum—do not use `15.5` without semantics.

## 4. Seven GeoJSON Geometry Types Supported by MongoDB

| Type | Core Structure | Meaning | Example Use Case |
|---|---|---|---|
| `Point` | One position | A single location | Warehouse, store, vehicle |
| `LineString` | Array of positions | A continuous path of segments | Route, river, boundary line |
| `Polygon` | Array of coordinate rings | A region, optionally with holes | Delivery zone, park |
| `MultiPoint` | Array of positions | Multiple points in one geometry | Group of monitoring stations |
| `MultiLineString` | Array of LineStrings | Multiple disconnected lines | Multiple route segments |
| `MultiPolygon` | Array of Polygons | Multiple separate regions | Multi-part service area |
| `GeometryCollection` | Array `geometries` | Mix of multiple geometry types | Facility with point, route, and zone |

The `Multi*` types and `GeometryCollection` are GeoJSON geometries supported by MongoDB in the context of **`2dsphere`**. That **does not mean every geospatial query accepts every geometry type as an argument**. For example, a `$near` distance query requires a **point as its center**, whereas `$geoWithin` with `$geometry` accepts regions such as Polygon/MultiPolygon.

An easy rule to remember:

```text
Point       -> [position]
LineString  -> [position, position, ...]
Polygon     -> [ring, ring, ...]
MultiPoint  -> [position, position, ...]
MultiLine   -> [line, line, ...]
MultiPoly   -> [polygon, polygon, ...]
Collection  -> geometries: [geometry, geometry, ...]
```

Note that the first line is just a **conceptual model**. The `coordinates` value of a `Point` is directly one position `[lon, lat]`, not `[[lon, lat]]`.

## 5. Point: A Specific Location

### 5.1. Syntax

```javascript
{
  type: "Point",
  coordinates: [106.70, 10.80]
}
```

A `Point` has only **one coordinate pair**, not multiple pairs:

```javascript
// Invalid Point structure.
{
  type: "Point",
  coordinates: [
    [106.70, 10.80],
    [106.72, 10.82]
  ]
}
```

To store multiple points in one geometry, use **MultiPoint**; to store an ordered path passing through points, use **LineString**.

### 5.2. When to Use Point?

- A store location.
- A pickup/dropoff spot.
- A device's current location.
- Coordinates of a measurement station.
- The origin for nearest-location searches.

### 5.3. MongoDB Document

```javascript
db.getSiblingDB("geo_training_292").sites292.insertOne({
  _id: "site-001",
  name: "Staging Point A",
  active: true,
  location: {
    type: "Point",
    coordinates: [106.70, 10.80]
  }
});
```

### 5.4. A Point Does Not Describe Area

If a warehouse occupies a large plot, storing a `Point` only provides a **representative point** for the warehouse. It does not describe the warehouse's actual boundary.

Two different questions:

```text
"Where is the warehouse?"              -> Point
"What is the warehouse land boundary?" -> Polygon
```

Do not use a Point at the center of a region and assume MongoDB knows the radius or boundary of that region. If business logic requires "within a 5 km radius," use a distance query or a dedicated region model.

## 6. LineString: A Path Connecting Multiple Points

### 6.1. Syntax

```javascript
{
  type: "LineString",
  coordinates: [
    [106.68, 10.78],
    [106.72, 10.80],
    [106.77, 10.83],
    [106.82, 10.86]
  ]
}
```

`coordinates` is an **array of positions**, requiring at least **two positions** to form a valid line.

```text
 A ------- B ------ C ------ D
 106.68    106.72   106.77   106.82  (illustration)
```

### 6.2. What Does It Represent?

- A list of path vertices.
- The connection order A → B → C → D.
- Geographic segments connecting consecutive pairs of vertices as interpreted by MongoDB on a sphere.

A LineString **does not inherently imply** vehicle speed, road direction, arrival time, drivable roads, or traffic-optimal ordering.

### 6.3. LineString vs. an Array of Points

Two geometries:

```javascript
// Sequential connection between points.
{
  type: "LineString",
  coordinates: [
    [106.68, 10.78],
    [106.72, 10.80],
    [106.77, 10.83]
  ]
}

// Just multiple positions, no connecting segments defined.
{
  type: "MultiPoint",
  coordinates: [
    [106.68, 10.78],
    [106.72, 10.80],
    [106.77, 10.83]
  ]
}
```

**LineString connects positions in order**; MultiPoint represents a set of points. Mistakenly using MultiPoint for a route can cause intersection queries or map rendering to behave unexpectedly.

### 6.4. A Line Does Not Need to Be Closed

```javascript
{
  type: "LineString",
  coordinates: [
    [106.68, 10.78],
    [106.75, 10.80]
  ]
}
```

The LineString above is valid in terms of minimum vertex count. Unlike a Polygon ring, the last point **does not need to match** the first point.

### 6.5. Can a LineString Serve as a Boundary?

A LineString can represent a **boundary line**, but it **does not automatically become a region with area**.

If the application needs to query "which points lie inside the delivery zone," store a **Polygon** or **MultiPolygon** (along with its corresponding constraints). Do not pass an open line to `$geoWithin` expecting it to form a closed region automatically.

### 6.6. Note on Lines on a Sphere

Segments in GeoJSON are evaluated by MongoDB in a spherical geographic context; they are **not** Euclidean line segments on an arbitrary flat map. For long paths—especially across the antimeridian or near the poles—screen rendering and intersection results can differ from straight lines drawn in a particular map projection.

## 7. Polygon: A Region Bounded by Rings

### 7.1. A Polygon Is Not Just an Array of Points

A GeoJSON Polygon has:

```javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.65, 10.75],
      [106.85, 10.75],
      [106.85, 10.90],
      [106.65, 10.90],
      [106.65, 10.75]
    ]
  ]
}
```

The array nesting here is:

```text
Polygon.coordinates
  |
  +-- outer ring
        |
        +-- position [lon, lat]
        +-- position [lon, lat]
        +-- position [lon, lat]
        +-- position [lon, lat]
        +-- position [lon, lat] = first position
```

Why are there **two `[` brackets** after `coordinates`? The outer `[` holds the list of rings, and the next `[` holds the positions of the first ring.

### 7.2. LinearRing: Closed Ring

A **LinearRing** is a closed LineString used as a region boundary:

- Contains at least **four positions**, including the repeated element that closes it.
- First and last positions are **identical**.
- Needs enough distinct vertices to form a meaningful area.
- Must not have self-intersections that violate validity rules.

Triangle example:

```javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.68, 10.78],
      [106.78, 10.78],
      [106.74, 10.86],
      [106.68, 10.78]
    ]
  ]
}
```

**Three distinct vertices + repeating the first vertex = four positions.**

### 7.3. Simple Diagram

```text
             D ----------------- C
             |                   |
             |      REGION       |
             |                   |
             A ----------------- B

Ring: [A, B, C, D, A]
```

The diagram only illustrates how vertices connect; over large distances on the globe, geodesic arcs along the spherical surface must be considered.

### 7.4. Common Structural Mistakes

**Mistake 1 — forgetting to repeat the first vertex:**

```javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.65, 10.75],
      [106.85, 10.75],
      [106.85, 10.90],
      [106.65, 10.90]
      // Missing closing [106.65, 10.75] at the end.
    ]
  ]
}
```

**Mistake 2 — missing the ring array level:**

```javascript
{
  type: "Polygon",
  coordinates: [
    [106.65, 10.75],
    [106.85, 10.75],
    [106.85, 10.90],
    [106.65, 10.75]
  ]
}
```

The pattern above looks like the `coordinates` of a closed LineString, which is **incorrect** for a Polygon structure that requires a list of rings.

### 7.5. A Polygon Does Not Compute Internal Routes

Knowing a location lies inside a delivery polygon **does not** mean there is a drivable road to get there. Polygons evaluate **spatial relationships**, while shortest paths, road networks, and travel times require other data and algorithms.

## 8. Polygon with Holes: Outer Ring and Inner Ring

### 8.1. Why Do Regions Have Holes?

A delivery area may exclude:

- A restricted zone.
- An unserved area.
- A lake or special terrain feature.
- An area outside operational authority despite lying inside the outer boundary.

You can use a **Polygon with multiple rings**.

### 8.2. Structure

```javascript
const deliveryArea292 = {
  type: "Polygon",
  coordinates: [
    // Ring 0: outer boundary.
    [
      [106.65, 10.75],
      [106.85, 10.75],
      [106.85, 10.90],
      [106.65, 10.90],
      [106.65, 10.75]
    ],

    // Ring 1: hole completely inside.
    [
      [106.70, 10.78],
      [106.70, 10.82],
      [106.75, 10.82],
      [106.75, 10.78],
      [106.70, 10.78]
    ]
  ]
};
```

The **first** ring is the **outer ring**. Subsequent rings represent **holes** inside it.

### 8.3. Visual Diagram

```text
        +-----------------------------------+
        |                                   |
        |     Served region                 |
        |                                   |
        |        +------------+             |
        |        |    HOLE    |             |
        |        |  excluded  |             |
        |        +------------+             |
        |                                   |
        +-----------------------------------+
```

Example:

- `[106.68, 10.78]` is inside the outer boundary and outside the hole.
- `[106.72, 10.80]` is inside the hole.
- `[106.90, 10.80]` is outside the outer boundary.

These positions were chosen clearly away from the boundaries; cases **lying directly on the boundary** require checking operator definitions and tolerance handling.

### 8.4. Topology Rules for Holes

A valid hole:

- Must lie **inside** the outer ring.
- Must not intersect or overlap another hole.
- Must not share an edge with another hole.
- Must not cause the outer ring to self-intersect.
- Must be closed like every Polygon ring.

If an inner ring is placed outside the outer ring, the geometry may be rejected or fail to reflect the intended business region. Do not treat "the array has the right nesting depth" as sufficient proof that a polygon is valid.

### 8.5. Ring Winding Direction

Modern GeoJSON specifies the **right-hand rule**: outer rings are typically oriented counterclockwise when represented on a longitude/latitude plane, while holes are clockwise.

MongoDB has its own spherical geometry rules and interpretations, especially for **very large polygons**. Do not arbitrarily reverse ring order to "fix errors" without knowing which region on Earth the polygon represents; verify against the data standard and specific MongoDB rules.

### 8.6. A Hole Does Not Create an Independent Polygon

Here is the difference:

```text
Polygon with two rings:
  outer region - inner hole

MultiPolygon with two polygons:
  region A + region B
```

If you want **two regions to both be served**, use a **MultiPolygon**—do not place the second region in the inner ring slot and accidentally create an **excluded zone**.

## 9. MultiPoint: Multiple Positions in One Geometry

### 9.1. Structure

```javascript
{
  type: "MultiPoint",
  coordinates: [
    [106.67, 10.77],
    [106.71, 10.79],
    [106.78, 10.84]
  ]
}
```

This is a geometry containing **multiple Points**, without implying they are connected into a line.

### 9.2. When to Use?

- A group of measurement points within the same GIS object.
- Observation locations belonging to the same campaign.
- Reference points of a multi-location entity.

### 9.3. When Not to Use?

If three stations have independent names, opening hours, statuses, and location updates, it usually makes more sense to create **three separate Point documents**:

```javascript
{ _id: "station-A", name: "A", location: { type: "Point", coordinates: [106.67, 10.77] } }
{ _id: "station-B", name: "B", location: { type: "Point", coordinates: [106.71, 10.79] } }
{ _id: "station-C", name: "C", location: { type: "Point", coordinates: [106.78, 10.84] } }
```

**MultiPoint** fits when the locations are parts of **one geometric entity**. Separate Point documents fit when each point is **a business entity** requiring independent CRUD and indexing.

## 10. MultiLineString: Multiple Disconnected Lines

### 10.1. Syntax

```javascript
{
  type: "MultiLineString",
  coordinates: [
    [
      [106.65, 10.76],
      [106.69, 10.79],
      [106.73, 10.82]
    ],
    [
      [106.80, 10.84],
      [106.83, 10.88]
    ]
  ]
}
```

Nesting levels:

```text
MultiLineString.coordinates
  |
  +-- LineString 1
  |     +-- position A
  |     +-- position B
  |     +-- position C
  |
  +-- LineString 2
        +-- position D
        +-- position E
```

### 10.2. When to Use?

- Multiple road segments of the same route that are separated.
- A river represented by multiple branches.
- A cable network with multiple segments.

### 10.3. MultiLineString vs. LineString

Single LineString:

```text
A --- B --- C --- D --- E
```

MultiLineString with two parts:

```text
A --- B --- C            D --- E
```

Do not draw an extra **C → D** segment when the geometry is a two-part MultiLineString. Connecting both parts into a single LineString **alters the spatial meaning**.

## 11. MultiPolygon: Multiple Separate Regions

### 11.1. Syntax and Array Nesting

```javascript
{
  type: "MultiPolygon",
  coordinates: [
    // Polygon A -> ring list of A.
    [
      [
        [106.60, 10.70],
        [106.65, 10.70],
        [106.65, 10.74],
        [106.60, 10.74],
        [106.60, 10.70]
      ]
    ],

    // Polygon B -> ring list of B.
    [
      [
        [106.80, 10.85],
        [106.85, 10.85],
        [106.85, 10.89],
        [106.80, 10.89],
        [106.80, 10.85]
      ]
    ]
  ]
}
```

Nesting to distinguish:

```text
MultiPolygon
  |
  +-- Polygon A
  |     +-- outer ring
  |           +-- position
  |           +-- position
  |
  +-- Polygon B
        +-- outer ring
              +-- position
              +-- position
```

Each sub-Polygon **has its own list of rings**, and can have its own holes.

### 11.2. Use Cases

- A company with two non-contiguous delivery zones.
- An administrative area with detached territories (exclaves).
- A conservation area consisting of multiple zones.

### 11.3. Do Not Confuse MultiPolygon with a Multi-Ring Polygon

```text
Polygon:
  coordinates: [outerRing, holeRing]
  => one region with one hole.

MultiPolygon:
  coordinates: [
    [outerRingA],
    [outerRingB]
  ]
  => two separate regions.
```

This is one of the most serious mistakes causing wrong geospatial query results when ingesting GIS data.

### 11.4. Validating Sub-Polygons

A MultiPolygon must still satisfy the corresponding geometry constraints. Simply placing any two polygons in an array does not guarantee a valid geometry:

- Every sub-ring must be closed.
- Parts must not have invalid topology such as self-intersection or improper overlap.
- Holes must lie inside their respective polygons.
- You must understand how MongoDB interprets boundaries on a sphere.

If two polygons are adjacent and actually represent a single region, you might model them as one Polygon with a combined boundary, depending on data requirements and boundary validity.

## 12. GeometryCollection: Mixing Geometries

### 12.1. This Is a Structural Special Case

It does not use `coordinates` at the top level:

```javascript
{
  type: "GeometryCollection",
  geometries: [
    {
      type: "Point",
      coordinates: [106.70, 10.80]
    },
    {
      type: "LineString",
      coordinates: [
        [106.68, 10.78],
        [106.75, 10.83]
      ]
    },
    {
      type: "Polygon",
      coordinates: [
        [
          [106.66, 10.76],
          [106.80, 10.76],
          [106.80, 10.88],
          [106.66, 10.88],
          [106.66, 10.76]
        ]
      ]
    }
  ]
}
```

### 12.2. Meaning

A GeometryCollection contains **multiple geometries that may have different types**. It is useful when a geographic entity is described by:

- A central point.
- A connecting line.
- An occupied region.

The child geometries reside in the `geometries` array rather than three ad-hoc business fields named `point`/`route`/`area`.

### 12.3. When Should It Not Be Used?

If the application needs to:

- Find the nearest warehouse with `$near`.
- Find routes intersecting a region.
- Find regions containing a point.

and each geometry has independent query semantics, storing **separate geometry fields** usually makes indexing and querying clearer:

```javascript
{
  _id: "facility-A",
  center: {
    type: "Point",
    coordinates: [106.70, 10.80]
  },
  route: {
    type: "LineString",
    coordinates: [
      [106.68, 10.78],
      [106.75, 10.83]
    ]
  },
  serviceArea: {
    type: "Polygon",
    coordinates: [
      [
        [106.66, 10.76],
        [106.80, 10.76],
        [106.80, 10.88],
        [106.66, 10.88],
        [106.66, 10.76]
      ]
    ]
  }
}
```

Then you can create exact indexes on `center`, `route`, or `serviceArea` according to your workload.

**GeometryCollection is not the optimal solution for all multi-geometry data.** It is a specific geometry type, not a substitute for business schema design.

## 13. Why Does Array Structure Matter So Much?

The same set of coordinate pairs can carry **three different meanings**:

```javascript
const a = [106.70, 10.80];

const point = {
  type: "Point",
  coordinates: a
};

const line = {
  type: "LineString",
  coordinates: [
    [106.70, 10.80],
    [106.75, 10.85]
  ]
};

const polygon = {
  type: "Polygon",
  coordinates: [
    [
      [106.70, 10.80],
      [106.80, 10.80],
      [106.80, 10.88],
      [106.70, 10.80]
    ]
  ]
};
```

Those `[` brackets are not merely JSON syntax. They describe:

- The **position** level.
- The **line** level.
- The **ring** level.
- The **polygon** level.
- The **geometry collection** level.

### 13.1. Exact Comparison Table

| Type | Mnemonic Nesting of `coordinates` | Short Pattern |
|---|---|---|
| Point | Position | `[x, y]` |
| MultiPoint | Positions | `[[x,y],[x,y]]` |
| LineString | Positions | `[[x,y],[x,y]]` |
| MultiLineString | LineStrings | `[[[x,y],[x,y]],[[x,y],[x,y]]]` |
| Polygon | Rings | `[[[x,y],[x,y],[x,y],[x,y]]]` |
| MultiPolygon | Polygons | `[[[[x,y],...]],[[[x,y],...]]]` |
| GeometryCollection | No top-level `coordinates` | `geometries: [{type,...}, ...]` |

**MultiPoint and LineString share the same array nesting depth but differ in `type` and connection semantics.** Polygon and MultiLineString can also look nearly identical by nesting depth alone; **`type` determines how it is interpreted**.

### 13.2. Array Levels Do Not Self-Describe Meaning

If an API only returns:

```javascript
[
  [106.70, 10.80],
  [106.75, 10.85]
]
```

you do not yet know whether it represents two independent points, a route, or map data in another format. You need a **clear type and API contract** before storing it in MongoDB.

## 14. Polygons on a Sphere: Geodesics, the Antimeridian, and Large Regions

### 14.1. A Flat Map Is Not the Earth

In a 2D drawing, two points are connected by a straight line segment. On Earth, a geographic connection can be interpreted as a **geodesic** path on a spherical surface.

For short segments within a city, the difference may be tiny. For very long segments, how they appear on a map projection and how MongoDB computes spatial relationships can differ significantly.

### 14.2. The Antimeridian

Two longitudes:

```text
179.9° E
-179.9° W
```

are right next to each other across the antimeridian, not nearly 360° apart on Earth.

Do not try to measure them by taking the absolute difference:

```javascript
Math.abs(179.9 - (-179.9)) // 359.8: not a valid geographic distance.
```

For geometries crossing the antimeridian, inspect the data in a WGS84-aware GIS tool and verify that MongoDB interprets the intended region correctly.

### 14.3. Regions Larger Than a Hemisphere

MongoDB has special rules for GeoJSON polygons **larger than a single hemisphere**. With the default CRS, a query may interpret the **smaller complementary region** instead of the large region the user intended.

For a **single-ring Polygon** in supported operators such as `$geoWithin` or `$geoIntersects`, MongoDB provides an extended **strict-winding** CRS to disambiguate large regions:

```javascript
const largePolygonQuery = {
  type: "Polygon",
  coordinates: [
    [
      [-100,  60],
      [-100,   0],
      [-100, -60],
      [ 100, -60],
      [ 100,  60],
      [-100,  60]
    ]
  ],
  crs: {
    type: "name",
    properties: {
      name: "urn:x-mongodb:crs:strictwinding:EPSG:4326"
    }
  }
};
```

**Important:** this is not a way to attach arbitrary CRSs to all GeoJSON. MongoDB's strict-winding CRS has a **specific scope of support**, tied particularly to single-ring polygons and corresponding operators. Do not apply it to MultiPolygons or polygons with holes and assume identical semantics.

### 14.4. Small Polygons Still Need Validation

Even when a region is only a few square kilometers:

- A ring may self-intersect.
- A hole may lie outside.
- A boundary may pass through invalid coordinates.
- Positions on the boundary may be affected by precision/tolerance.

Do not treat a successful `insertOne()` on an unindexed document as proof of topologically valid geometry.

## 15. The `2dsphere` Index: Foundation for GeoJSON Queries

### 15.1. Creating the Index

Given a collection:

```javascript
{
  _id: "shop-A",
  location: {
    type: "Point",
    coordinates: [106.70, 10.80]
  }
}
```

Create the index:

```javascript
db.shops.createIndex({
  location: "2dsphere"
});
```

`2dsphere` serves geometry queries on an Earth-like spherical surface, suitable for GeoJSON/WGS84 data.

### 15.2. Why Not Use a Regular Index?

An index:

```javascript
db.shops.createIndex({ "location.coordinates": 1 });
```

does not have the capabilities of `2dsphere` to answer:

- Which locations lie inside a Polygon?
- Which geometries intersect a route?
- Which points are closest to the current location?

Regular indexes simply sort BSON values in standard order; they do not replace spatial indexing structures.

### 15.3. GeoJSON Types and `2dsphere`

`2dsphere` is the choice for **Point, LineString, Polygon**, as well as **MultiPoint, MultiLineString, MultiPolygon, and GeometryCollection** under supported conditions.

When indexing complex geometries, MongoDB must build internal spatial representations; a document with a polygon having very many vertices or many sub-geometries can sharply increase index and update costs.

### 15.4. An Index Is Not a Data Cleaner

A geospatial index can **refuse** to build if any document in the indexed field contains invalid geometry types or out-of-range coordinates.

Example:

```javascript
{
  location: {
    type: "Point",
    coordinates: ["abc", "def"]
  }
}
```

Do not rely on MongoDB to coerce strings into coordinates or guess the CRS. Validate inputs before writing.

### 15.5. `2dsphere` Is Not a Shard Key

In a sharded cluster, **a geospatial index cannot be used directly as a shard key**. A sharded collection can have a geospatial index for queries, but the **shard key** must be designed with fields and indexes that follow sharding rules.

Do not pick `{ location: "2dsphere" }` as a shard key just because all queries are geographic.

## 16. `2d` and Legacy Coordinate Pairs vs. GeoJSON `2dsphere`

MongoDB supports **legacy coordinate pairs**:

```javascript
{
  loc: [106.70, 10.80]
}
```

and indexes such as:

```javascript
db.legacyPlaces.createIndex({
  loc: "2d"
});
```

However, distinguish between them:

| Aspect | `2d` | `2dsphere` |
|---|---|---|
| Geometry model | Planar, suitable for flat coordinates as needed | Spherical, built for Earth geographic data |
| Typical data | Legacy coordinate pairs | GeoJSON geometries or legacy coordinate pairs |
| Polygons / sphere | Cannot substitute for GeoJSON spherical semantics | Supports appropriate GeoJSON geometries |
| Proximity distance | Requires careful unit and operator understanding | With GeoJSON Point, distance is typically in meters |
| Use for GPS locations | Not the default choice | Usually choose `2dsphere` |

**Do not convert a legacy coordinate pair into a GeoJSON Point simply by adding `type` if you do not know whether the values are truly WGS84 longitude/latitude.**

### 16.1. Do Not Mix Two Representations in the Same Path Without Control

Do not store:

```javascript
{
  location: {
    lat: 10.80,
    lng: 106.70,
    coordinates: [106.70, 10.80],
    type: "Point"
  }
}
```

and let different systems pick whichever source they prefer. If you need to support a legacy API, maintain **one canonical geometry field** and explicit conversion rules.

### 16.2. GeoJSON Does Not Store Every Map Attribute Automatically

GeoJSON describes **geometry**; it does not inherently carry:

- Proof that another EPSG code was transformed accurately.
- Road network graphs.
- Speeds and travel times.
- Elevation for 3D distance computation.
- Historical boundary changes.
- Geopolitical border dispute resolution.

Those require separate fields/schemas or dedicated GIS systems.

## 17. Hands-On Dataset: Points and Regions

The examples use the **`geo_training_292`** database. Coordinates in this lesson are **simulated data for learning structures**, not claims about real administrative boundaries or delivery zones in any city.

### 17.1. Creating Points

In `mongosh`:

```javascript
const demo = db.getSiblingDB("geo_training_292");
const points = demo.points292;

// Use only a new/empty lab collection.
if (points.countDocuments({}) !== 0) {
  throw new Error("points292 already has data; use an empty lab collection");
}

points.insertMany([
  {
    _id: "P-A",
    name: "Point A: inside region",
    location: {
      type: "Point",
      coordinates: [106.68, 10.78]
    }
  },
  {
    _id: "P-B",
    name: "Point B: inside excluded hole",
    location: {
      type: "Point",
      coordinates: [106.72, 10.80]
    }
  },
  {
    _id: "P-C",
    name: "Point C: outside region",
    location: {
      type: "Point",
      coordinates: [106.90, 10.80]
    }
  },
  {
    _id: "P-D",
    name: "Point D: inside region",
    location: {
      type: "Point",
      coordinates: [106.81, 10.85]
    }
  }
]);

points.createIndex({ location: "2dsphere" });
```

### 17.2. Creating a Region Geometry with a Hole

```javascript
const deliveryArea292 = {
  type: "Polygon",
  coordinates: [
    [
      [106.65, 10.75],
      [106.85, 10.75],
      [106.85, 10.90],
      [106.65, 10.90],
      [106.65, 10.75]
    ],
    [
      [106.70, 10.78],
      [106.70, 10.82],
      [106.75, 10.82],
      [106.75, 10.78],
      [106.70, 10.78]
    ]
  ]
};
```

### 17.3. Storing the Region as a Separate Document

```javascript
demo.areas292.insertOne({
  _id: "ZONE-A",
  name: "Simulated service area",
  geometry: deliveryArea292
});

demo.areas292.createIndex({ geometry: "2dsphere" });
```

**Note:** The `demo.areas292.insertOne()` example is intended for an empty collection. If you already ran it, do not insert the same `_id` a second time and mistake a duplicate key error for a geospatial error.

## 18. `$geoWithin` Query: Completely Inside a Region

### 18.1. Problem

Find points whose `location` falls within the delivery area, **excluding the hole**.

```javascript
points.find({
  location: {
    $geoWithin: {
      $geometry: deliveryArea292
    }
  }
}, {
  _id: 1,
  name: 1
});
```

With points chosen clearly away from the boundaries, expect `P-A` and `P-D` to be returned as inside the region. `P-B` lies inside the hole, and `P-C` lies outside the outer ring.

### 18.2. Why Use `$geometry`?

`$geometry` tells MongoDB that the right-hand shape is a **GeoJSON query geometry**:

```javascript
{
  $geoWithin: {
    $geometry: {
      type: "Polygon",
      coordinates: [
        [
          [106.65, 10.75],
          [106.85, 10.75],
          [106.85, 10.90],
          [106.65, 10.90],
          [106.65, 10.75]
        ]
      ]
    }
  }
}
```

Do not confuse a query geometry parameter with a full business document containing `_id`, `name`, and `createdAt`.

### 18.3. `$geoWithin` Is Not the Same as `$geoIntersects`

`$geoWithin` asks: is the geometry in the document's field **completely inside** the specified shape?

`$geoIntersects` asks: does the geometry in the document's field **intersect** with the specified shape?

A route passing through a zone while having segments outside it can **intersect** without being **within**.

### 18.4. Indexes and Results

`$geoWithin` does not automatically sort points by distance or name. If you need stable ordering, add an explicit `sort()`.

`$geoWithin` does not always require a geospatial index to execute, but creating a `2dsphere` index on the proper field optimizes spherical queries for appropriate workloads.

## 19. `$geoIntersects` Query: Intersecting Geometries

### 19.1. Storing a Route

```javascript
const shapes = demo.shapes292;

shapes.insertOne({
  _id: "ROUTE-A",
  kind: "route",
  geometry: {
    type: "LineString",
    coordinates: [
      [106.60, 10.78],
      [106.72, 10.81],
      [106.90, 10.86]
    ]
  }
});

shapes.createIndex({ geometry: "2dsphere" });
```

This is a LineString passing through the test region with endpoints outside it, ideal for demonstrating **intersection**.

### 19.2. Finding Routes Intersecting a Region

```javascript
shapes.find({
  kind: "route",
  geometry: {
    $geoIntersects: {
      $geometry: deliveryArea292
    }
  }
});
```

The query finds route geometries that **intersect** the specified polygon.

### 19.3. Finding Regions Intersecting a Route

If the database stores multiple `geometry: Polygon` regions and you want to find which regions a route passes through, you can swap the stored side and the query side:

```javascript
const routeGeometry292 = {
  type: "LineString",
  coordinates: [
    [106.60, 10.78],
    [106.72, 10.81],
    [106.90, 10.86]
  ]
};

demo.areas292.find({
  geometry: {
    $geoIntersects: {
      $geometry: routeGeometry292
    }
  }
});
```

### 19.4. Intersection Does Not Mean Public Road Access

A route may geometrically cross a Polygon boundary, yet in reality the path might:

- Cross a restricted zone.
- Go over a bridge.
- Pass through a tunnel.
- Be at a different elevation.

MongoDB evaluates spatial relationships in **2D on a spherical surface**; it does not infer travel permissions or 3D traffic rules.

### 19.5. Boundary Cases

Intersection at an exact vertex or boundary line can have mathematical/tolerance subtleties compared to a line clearly passing through the interior. If business logic distinguishes **touches**, **crosses**, and **overlaps** per advanced GIS standards, verify operator capabilities and use supplemental GIS tooling if needed.

## 20. `$near` Query: Distance to a Point

### 20.1. Finding Locations Near an Origin Point

```javascript
const pickupPoint292 = {
  type: "Point",
  coordinates: [106.70, 10.80]
};

points.find({
  location: {
    $near: {
      $geometry: pickupPoint292,
      $maxDistance: 15000
    }
  }
}, {
  _id: 1,
  name: 1
});
```

With GeoJSON + `2dsphere`, `$maxDistance`/`$minDistance` are interpreted in **meters** per operator semantics. `$near` results are normally ordered by distance to the specified point.

### 20.2. Why Must the Center Be a Point?

`$near` answers "which geometries are closest to **this location**?". The query parameter must be a **point**—do not pass an entire Polygon into `$geometry` expecting the system to automatically pick a "polygon center."

If you need a representative point for a polygon, the application must determine a **centroid or an interior point** according to appropriate rules; a geometric centroid can fall outside a concave polygon or inside a hole, so it is not always a good business location.

### 20.3. Required Index

Proximity queries such as `$near`/`$nearSphere` require an appropriate **geospatial index**. For geographic GeoJSON data, create:

```javascript
points.createIndex({ location: "2dsphere" });
```

If a collection has multiple geospatial indexes, some APIs such as `$geoNear` require specifying the field/index via `key` to avoid ambiguity.

## 21. `$geoNear` in Aggregation

### 21.1. When You Need Distance Included in Results

`$geoNear` can compute a distance field and continue through the aggregation pipeline:

```javascript
points.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.70, 10.80]
      },
      key: "location",
      distanceField: "distanceMeters",
      spherical: true,
      maxDistance: 15000
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
]);
```

### 21.2. Important Notes

- `$geoNear` must generally be placed as the **first stage** of the pipeline per MongoDB rules.
- Requires an appropriate geospatial index.
- `distanceField` is an output field path you choose; it does not need to exist in source documents.
- `near` is a Point (or supported compatible representation), not an arbitrary Polygon.
- For spherical geometry, set `spherical: true` according to your use case and version syntax.

### 21.3. `$near` vs. `$geoNear`

| Need | Common Tool |
|---|---|
| Only filter nearby points and return results ordered by distance | `$near` in `find()` |
| Want a distance field for further aggregation calculations | `$geoNear` |
| Find points inside a Polygon region | `$geoWithin` |
| Find geometries intersecting a region/route | `$geoIntersects` |

Do not use `$geoNear` as a replacement for network routing or travel time; geographic distance is not driving time.

## 22. Choosing the Right Operator for Each Geometry

### 22.1. A Decision Table

| Business Question | Stored Data | Query Geometry | Suggested Operator |
|---|---|---|---|
| Which stores are inside the delivery area? | `Point` | `Polygon` | `$geoWithin` |
| Which routes cross a restricted zone? | `LineString` | `Polygon` | `$geoIntersects` |
| Which zone contains the customer's location? | `Polygon` | `Point` | `$geoIntersects` |
| Find the ten nearest stations | `Point` | `Point` | `$near` or `$geoNear` |
| Which land parcels intersect the zoning boundary? | `Polygon`/`MultiPolygon` | `Polygon` | `$geoIntersects` |
| Is a route completely inside a zone? | `LineString` | `Polygon` | `$geoWithin`, when topology is appropriate |
| Do multiple observation points intersect a zone? | `MultiPoint` | `Polygon` | Choose operator based on "any point intersects" vs. "all points inside" |

### 22.2. "Partially" vs. "Completely"

Given a MultiPoint with two points, one inside and one outside the polygon:

```javascript
{
  type: "MultiPoint",
  coordinates: [
    [106.68, 10.78], // inside
    [106.90, 10.80]  // outside
  ]
}
```

- If asking **whether it intersects the region**, the point set intersects because at least one point is in the region.
- If asking **whether the entire geometry lies inside the region**, the whole MultiPoint cannot be considered completely within the region.

This is why choosing `$geoIntersects` vs. `$geoWithin` depends on **business semantics**, not merely because both accept a Polygon parameter.

## 23. Validating GeoJSON Data Before Writing

### 23.1. Validating a Position

A simple JavaScript function:

```javascript
function isPosition(value) {
  return Array.isArray(value) &&
    (value.length === 2 || value.length === 3) &&
    value.every(v => typeof v === "number" && Number.isFinite(v)) &&
    value[0] >= -180 && value[0] <= 180 &&
    value[1] >= -90 && value[1] <= 90;
}

print(isPosition([106.70, 10.80]));       // true
print(isPosition(["106.70", "10.80"]));   // false
print(isPosition([10.80, 106.70]));       // false
print(isPosition([181, 10]));            // false
```

This is only a **basic type and range check**; it does not confirm the coordinate is where the user intended, nor does it handle CRS or elevation accurately.

### 23.2. Validating a LineString

```javascript
function isBasicLineStringCoordinates(coords) {
  return Array.isArray(coords) &&
    coords.length >= 2 &&
    coords.every(isPosition);
}

print(isBasicLineStringCoordinates([
  [106.70, 10.80],
  [106.75, 10.85]
])); // true
```

This function checks **count and structure**, not whether two points are identical or whether the line makes geographic sense.

### 23.3. Validating a Closed Ring

```javascript
function samePosition(a, b) {
  return Array.isArray(a) &&
    Array.isArray(b) &&
    a.length === b.length &&
    a.every((value, i) => value === b[i]);
}

function isBasicLinearRing(ring) {
  if (!Array.isArray(ring) || ring.length < 4) {
    return false;
  }

  if (!ring.every(isPosition)) {
    return false;
  }

  return samePosition(ring[0], ring[ring.length - 1]);
}

print(isBasicLinearRing([
  [106.65, 10.75],
  [106.85, 10.75],
  [106.85, 10.90],
  [106.65, 10.75]
])); // true for basic structure
```

### 23.4. Basic Polygon Validation

```javascript
function isBasicPolygonCoordinates(coords) {
  return Array.isArray(coords) &&
    coords.length >= 1 &&
    coords.every(isBasicLinearRing);
}

print(isBasicPolygonCoordinates(deliveryArea292.coordinates));
// true if the variable was declared in the previous example.
```

**Do not interpret `true` as a fully valid polygon!** The function above does not check for:

- Self-intersection.
- Holes outside the outer ring.
- Overlapping holes.
- Distinct vertex count.
- Ring orientation and spherical interpretation.
- Boundaries crossing the antimeridian.
- Wrong CRS or wrong business geometry.

To validate production geospatial data, use proper GIS/geometry validation tools along with MongoDB index checks, rather than writing a five-line function and treating it as sufficient.

### 23.5. Why Validate Upfront?

If a batch contains 100,000 geometries, a single bad document can:

- Cause index creation or insert operations to fail.
- Produce distorted coverage areas, leading to missing or extra search results.
- Cause unexpected area or intersection computations.
- Break map rendering or draw malformed paths in the application.

Geometry validation is an **input data quality requirement**, not something you can replace by scaling up MongoDB resources.

## 24. Common Mistakes When Converting Data from GIS/APIs

### 24.1. Planar Coordinate Systems Mistaken for Lon/Lat

A GIS file with coordinates:

```text
x = 689000
y = 1192000
```

may be using meters in some projected coordinate system. These values are not valid longitude/latitude and must be transformed to WGS84 first.

### 24.2. A String Containing JSON Is Not a BSON Geometry

Incorrect:

```javascript
{
  location: '{"type":"Point","coordinates":[106.70,10.80]}'
}
```

`location` is a **String**, not an embedded GeoJSON document. A `2dsphere` index on that field will not process it as a Point geometry.

Correct:

```javascript
{
  location: {
    type: "Point",
    coordinates: [106.70, 10.80]
  }
}
```

### 24.3. A GeoJSON FeatureCollection Is Not a GeometryCollection

FeatureCollection example:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": { "name": "A" },
      "geometry": {
        "type": "Point",
        "coordinates": [106.70, 10.80]
      }
    }
  ]
}
```

It is **different** from:

```javascript
{
  type: "GeometryCollection",
  geometries: [
    {
      type: "Point",
      coordinates: [106.70, 10.80]
    }
  ]
}
```

If importing GeoJSON from a file containing a `FeatureCollection`, extract each geometry into an indexed MongoDB field, or store the Feature structure in a clearly designed path.

### 24.4. Polygon with a Hole Imported as a MultiPolygon

A file with an outer ring and an inner hole must not be converted into two independent polygons just because "there are two coordinate arrays." Doing so flips the meaning from **excluding** a region to **adding** another region.

### 24.5. Route Imported as a MultiPoint

If a route has four waypoints, storing it as a MultiPoint loses the **connecting segments** semantics. Intersection queries against a polygon may only evaluate the points rather than detecting where the route passes between two waypoints.

### 24.6. Overly Simplified Boundaries

A region drawn with four vertices may omit important curves. If the application serves legal or safety purposes, use a boundary source with appropriate precision and versioning.

Conversely, polygons with hundreds of thousands of vertices can make queries and indexes expensive. Evaluate the required level of detail based on acceptable tolerance and the use case.

## 25. Java Sync Driver: Creating a Point and Querying a Polygon

### 25.1. Using the Driver's GeoJSON Classes

The MongoDB Java Sync Driver includes classes such as `Position`, `Point`, `LineString`, and `Polygon` in the `com.mongodb.client.model.geojson` package.

Example reading/writing a Point:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Indexes;
import com.mongodb.client.model.geojson.Point;
import com.mongodb.client.model.geojson.Position;
import org.bson.Document;

public class GeoPointExample {
    public static void main(String[] args) {
        try (MongoClient client =
                 MongoClients.create("mongodb://localhost:27017")) {

            MongoDatabase database =
                client.getDatabase("geo_training_292");
            MongoCollection<Document> collection =
                database.getCollection("javaPoints292");

            collection.createIndex(
                Indexes.geo2dsphere("location"));

            // Position takes longitude first, latitude second.
            Point point = new Point(new Position(106.70, 10.80));

            Document doc = new Document("_id", "JAVA-P-01")
                .append("name", "Java Station")
                .append("location", point);

            collection.replaceOne(
                new Document("_id", "JAVA-P-01"),
                doc,
                new com.mongodb.client.model.ReplaceOptions()
                    .upsert(true));
        }
    }
}
```

### 25.2. Creating a Polygon and `geoWithin()`

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.geojson.Polygon;
import com.mongodb.client.model.geojson.Position;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Arrays;

public class PolygonQueryExample {
    public static void main(String[] args) {
        try (MongoClient client =
                 MongoClients.create("mongodb://localhost:27017")) {

            MongoCollection<Document> points =
                client.getDatabase("geo_training_292")
                      .getCollection("points292");

            Polygon area = new Polygon(Arrays.asList(
                new Position(106.65, 10.75),
                new Position(106.85, 10.75),
                new Position(106.85, 10.90),
                new Position(106.65, 10.90),
                new Position(106.65, 10.75)
            ));

            Bson filter = Filters.geoWithin("location", area);

            for (Document doc : points.find(filter)) {
                System.out.println(doc.toJson());
            }
        }
    }
}
```

**Note:** This second Java Polygon example uses an **outer region without holes**, unlike `deliveryArea292` earlier. Therefore, point `P-B` lies inside the outer region and can be returned by this query; do not take that result as evidence that holes do not work.

### 25.3. The Java Driver Does Not Auto-Swap Coordinate Order

```java
new Position(106.70, 10.80);  // longitude, latitude
```

If input arrives as:

```java
double latitude = 10.80;
double longitude = 106.70;
```

explicitly construct:

```java
Point point = new Point(new Position(longitude, latitude));
```

The driver cannot guess that the developer swapped the arguments.

### 25.4. When You Need a Polygon with Holes in Java

The driver provides polygon/hole construction APIs depending on its version. When a use case requires more than a single outer ring:

1. Construct the positions for the outer ring and inner rings.
2. Ensure closure and topological validity.
3. Use the driver version's constructor/API supporting holes, or construct a properly formatted GeoJSON `BsonDocument`/`Document`.
4. Run the query and verify results on sample data containing a point inside the hole.

Do not take a Java `List<Position>` for a single ring and substitute it for an entire multi-level `MultiPolygon`.

## 26. Performance and Schema Decisions

### 26.1. More Complex Shapes Mean More Expensive Indexes

A polygon with 5 vertices is very different from a polygon with 50,000 vertices. With `2dsphere`, MongoDB generates spatial keys/representations for the geometry; overly detailed shapes can bloat index size and make writes/updates expensive.

Do not jump to the conclusion that "adding more vertices always makes queries faster and more accurate." Balance:

- Boundary precision.
- Storage footprint.
- Index build cost.
- Geometry update cost.
- Document and network payload size.
- Query results at boundary cases.

### 26.2. Rarely Changing Regions vs. Continuously Updated Locations

For example:

- `deliveryArea: Polygon` updated monthly.
- `driverLocation: Point` updated every few seconds.

If placed together in one large document and the Point is updated continuously, the application can incur unnecessary document write and index overhead depending on the actual architecture.

You can separate them:

```text
deliveryZones292
  zoneId, name, geometry: Polygon

driverLocations292
  driverId, location: Point, updatedAt
```

so each collection has its own indexes and lifecycle.

### 26.3. Mixing Multiple Geometry Types in One Collection?

MongoDB can store different GeoJSON geometries in the same `geometry` field if the data is valid:

```javascript
{ _id: "A", geometry: { type: "Point", coordinates: [106.70,10.80] } }
{ _id: "B", geometry: { type: "LineString", coordinates: [[106.70,10.80],[106.80,10.85]] } }
```

However, ask yourself:

- Do all documents share the same query contract?
- Do you need to filter by `kind` before running an operator?
- Are there appropriate indexes for the frequent queries?
- When returning geometries to clients, does the client support every type?

In many systems, separating Points, Routes, and Areas into dedicated collections keeps code and indexes cleaner.

### 26.4. Combining Business Filters with Geospatial Queries

For example, finding active warehouses within a region:

```javascript
db.warehouses.find({
  active: true,
  location: {
    $geoWithin: {
      $geometry: deliveryArea292
    }
  }
});
```

You can consider a compound index combining the filter field and the geospatial field according to the query pattern:

```javascript
db.warehouses.createIndex({
  active: 1,
  location: "2dsphere"
});
```

This is a **candidate index**, not a guarantee that the optimizer will always choose it as the fastest plan for all datasets. Use `explain("executionStats")` on a representative workload to verify.

### 26.5. Do Not Index Every Geometry Field Just Because You Can

Every added index:

- Consumes storage space.
- Increases write/update overhead.
- Requires maintenance as data grows.

Design indexes around **actual queries executed**, not simply the number of geometry fields in the schema.

## 27. Detailed Application Scenarios

### 27.1. Stores Near a Customer's Location

**Data:** `location: Point`.

**Query:** `$near` from the customer's coordinates.

**Not needed:** Polygon if you only need distance to a representative point of each store.

**Note:** Direct distance is not road travel distance.

### 27.2. Warehouses with Special Delivery Zones

**Data:** `serviceArea: Polygon` or `MultiPolygon`.

**Query:** Whether a customer's point intersects/falls within the zone.

**Note:** If there is an excluded area, use a **hole**, not a second polygon that adds area.

### 27.3. Delivery Vehicle Route

**Data:** `route: LineString`.

**Query:** Does the path intersect a restricted zone?

**Note:** A LineString represents a geometric path and does not guarantee drivable roads exist between waypoints.

### 27.4. Vehicle Route with Disconnected Segments

**Data:** `route: MultiLineString`.

**Query:** Do the segments intersect a zone?

**Note:** Do not automatically connect disconnected segments into one continuous path.

### 27.5. Service Covering Separate Zones

**Data:** `serviceArea: MultiPolygon`.

**Query:** Is the customer inside one of the valid zones?

**Note:** Do not represent the second part as an inner ring of a Polygon.

### 27.6. Survey Measurement Points

**Data:** `samples: MultiPoint` if all points belong to one geometry.

**Note:** If individual points need independent updates or identifiers, consider separate Point documents.

### 27.7. Multi-Component Infrastructure Facility

**Data:** `GeometryCollection`, or multiple geometry fields if each component needs separate indexing/querying.

**Note:** GeometryCollection does not organize your domain model automatically; you still need clear IDs, relationships, permissions, and lifecycles.

## 28. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using `[lat, lon]` | Wrong location or invalid coordinates | Normalize to `[lon, lat]` |
| Passing String coordinates | Geometry index/query error | Use BSON numbers |
| Storing a Point as `[[x,y]]` | Wrong nesting depth | Point uses `[x,y]` |
| Storing a Polygon like a LineString | Missing ring list | Wrap in an extra ring array |
| Unclosed ring | Invalid Polygon | Repeat first position at the end |
| Ring with fewer than 4 positions | Insufficient area geometry | Require at least 3 distinct vertices + closure |
| Hole outside the outer ring | Invalid topology | Verify containment |
| Self-intersecting Polygon | Invalid/ambiguous region | Fix boundaries with GIS tooling |
| Multiple zones placed as multiple rings | Second zone treated as a hole | Use MultiPolygon |
| Using MultiPoint for a route | Loses connecting segment semantics | Use LineString |
| Joining disconnected segments into LineString | Introduces fake connecting segment | Use MultiLineString |
| GeometryCollection using top-level `coordinates` | Invalid structure | Use `geometries` |
| Indexing an entire Feature instead of its geometry | Wrong geometry path | Index `feature.geometry` |
| Choosing `2d` index for GeoJSON GPS data | Wrong spherical geometry | Use `2dsphere` |
| Passing a Polygon as center to `$near` | Wrong query geometry type | Use a Point as center |
| Assuming `$geoWithin` matches partial overlap | May miss routes that merely cross a zone | Choose `$geoIntersects` |
| Treating `updateLookup`/app data as a GIS engine | Relies on out-of-scope functionality | Use GIS tooling when needed |
| Using document `_id` instead of spatial conditions | Does not answer geographic relationships | Use geospatial operators |
| Thinking `$maxDistance` is km when passing 5000 | Wrong unit | With spherical GeoJSON, usually meters |
| Using an oversized polygon without considering complement | Query targets unintended region | Check hemisphere / `strictwinding` CRS |
| Assuming geometry with altitude enables 3D queries | Results ignore elevation as expected | Handle elevation separately |
| Assuming boundary results match flat checks | Different tolerances/boundary definitions | Define boundary rules and test |
| Using a Polygon to describe optimal driving path | Lacks road network | Use a routing engine when needed |
| Using geospatial index as shard key | Violates sharding constraints | Choose a separate shard key |
| Failing to check input CRS | Regions are completely wrong | Transform to WGS84 first |

## 29. Hands-On Exercises

### Exercise 1 — Identifying Geometry Types

Given:

```javascript
const A = { type: "Point", coordinates: [106.70, 10.80] };
const B = {
  type: "LineString",
  coordinates: [[106.70,10.80],[106.75,10.82]]
};
const C = {
  type: "MultiPoint",
  coordinates: [[106.70,10.80],[106.75,10.82]]
};
```

Answer: How do B and C have identical `coordinates` structures yet differ semantically? How does A differ from them in array nesting depth?

### Exercise 2 — Fixing Coordinate Order

An API returns:

```javascript
{
  latitude: 10.81,
  longitude: 106.71
}
```

Write a valid GeoJSON Point. Why must you not pass `[latitude, longitude]`? What happens if both values happen to fall within valid longitude/latitude ranges?

### Exercise 3 — Creating a LineString

Given three waypoints:

```text
A = [106.65, 10.76]
B = [106.70, 10.80]
C = [106.75, 10.85]
```

Write a LineString from A → B → C. If you reverse the order to C → B → A, does the geometric line change its drawn position? Can the application's directional travel meaning change?

### Exercise 4 — Closing a Polygon Ring

A polygon sent from the frontend:

```javascript
[
  [106.65, 10.75],
  [106.85, 10.75],
  [106.85, 10.90],
  [106.65, 10.90]
]
```

Convert it into a valid `{ type: "Polygon", coordinates: ... }`. Why must the first vertex be repeated? How many **distinct vertices** and how many **positions in the ring** are there?

### Exercise 5 — Polygon with a Hole

Create a Polygon consisting of:

- A rectangular outer ring from longitude 106.60 to 106.90 and latitude 10.70 to 10.90.
- An inner hole from longitude 106.70 to 106.75 and latitude 10.78 to 10.82.

Write the exact array nesting and keep rings closed. Does `[106.72, 10.80]` belong to the served area?

### Exercise 6 — MultiPolygon or Multi-Ring Polygon?

A company serves two zones:

```text
Zone A: [106.60..106.65] × [10.70..10.74]
Zone B: [106.80..106.85] × [10.85..10.89]
```

Choose Polygon, MultiPolygon, or GeometryCollection and explain why. Write the JSON/BSON geometry for your choice.

### Exercise 7 — MultiLineString

A transport route has two parts:

```text
Segment 1: A -> B -> C
Segment 2: D -> E
```

Write the MultiLineString. If changed to a LineString A → B → C → D → E, what artificial segment has the system added?

### Exercise 8 — GeometryCollection

Create a GeometryCollection containing:

1. A central station Point.
2. A route LineString.
3. A coverage Polygon.

Why does `GeometryCollection` use `geometries` instead of top-level `coordinates`? When can you use three separate geometry fields instead?

### Exercise 9 — Importing a GeoJSON Feature

Given:

```json
{
  "type": "Feature",
  "properties": { "name": "Warehouse A" },
  "geometry": {
    "type": "Point",
    "coordinates": [106.70, 10.80]
  }
}
```

Design a MongoDB document with `name` and `location`. Create a `2dsphere` index on the appropriate path. Why should you not index a String field containing serialized JSON?

### Exercise 10 — Finding Points Inside a Region

Using `points292` and `deliveryArea292`:

1. Write a `$geoWithin` query.
2. Predict which Points are inside the region, outside the region, and inside the hole.
3. Explain why a point inside the hole must not be considered valid.
4. Are `$geoWithin` results automatically sorted by distance?

### Exercise 11 — Route Crossing a Region

Given the route:

```javascript
{
  type: "LineString",
  coordinates: [
    [106.60, 10.78],
    [106.72, 10.81],
    [106.90, 10.86]
  ]
}
```

Write a `$geoIntersects` query against `deliveryArea292`. Why might `$geoWithin` be inappropriate when part of the route lies outside the region?

### Exercise 12 — Finding Nearest Locations

Create a `2dsphere` index on `location` and find Points within a 5,000-meter radius of `[106.70, 10.80]`. Use `$near` with `$geometry`. Distinguish between geographic distance and driving time.

### Exercise 13 — `$geoNear` in Aggregation

Write a pipeline that:

1. Computes distance from a Point.
2. Names the field `distanceMeters`.
3. Returns only `_id`, `name`, and `distanceMeters`.
4. Limits output to 10 results.

Explain the role of `key` if the collection has multiple geospatial indexes.

### Exercise 14 — Validating Geometries

Write validation functions verifying:

- A Position is an array of 2 finite numbers within lon/lat ranges.
- A LineString has at least 2 positions.
- A Polygon has at least one ring.
- A Ring has at least 4 positions and matching start/end positions.

Then list **at least four topology/CRS errors** that these functions cannot detect.

### Exercise 15 — Wrong CRS

A GIS data source uses meter coordinates:

```text
x = 689000
y = 1192000
```

The development team plans to write:

```javascript
{
  type: "Point",
  coordinates: [689000, 1192000]
}
```

Explain the problem and the steps to transform to GeoJSON/WGS84. Why can you not simply divide the numbers by an arbitrary constant?

### Exercise 16 — Crossing the Antimeridian

A LineString runs from `[179.9, 10]` to `[-179.9, 10]`. The longitude difference by ordinary subtraction is nearly 360 degrees. Does that mean the line must wrap almost all the way around the Earth? Explain how spherical geometry and map projections affect interpretation.

### Exercise 17 — Regions Larger Than a Hemisphere

Why can a very large Polygon using the default CRS be interpreted as the complementary region? Which queries does MongoDB's `strictwinding` relate to, and can it be arbitrarily applied to a MultiPolygon?

### Exercise 18 — Logistics Schema Design

An application has:

- 20,000 drivers updating their locations every 3 seconds.
- 200 warehouses with delivery boundaries changing quarterly.
- 10,000 routes recalculated daily.

Propose collections and GeoJSON types for each group. Choose geospatial indexes based on expected queries, factoring in update costs, storage, and geometries with too many vertices.

### Exercise 19 — Map Looks Right but Query Fails

A polygon appears to render properly on a map, yet `$geoWithin` misses points. List possible causes:

- Swapped lon/lat.
- Polygon has a hole or self-intersecting ring.
- Data uses a different CRS.
- Large-region / hemisphere definition.
- Wrong geometry type value.
- Wrong query field/index path.
- Differences right on the boundary.

For each cause, suggest how to verify it with data or appropriate tools.

### Exercise 20 — Choosing Among the 7 Geometry Types

Classify:

1. A train station.
2. A single train line.
3. A park with a lake in the middle not belonging to the park.
4. Multiple sensor points in a single measurement unit.
5. Three disconnected cable segments.
6. A nature reserve made up of two separate zones.
7. A facility consisting of a central point, connecting line, and auxiliary zone.

Choose among `Point`, `LineString`, `Polygon`, `MultiPoint`, `MultiLineString`, `MultiPolygon`, and `GeometryCollection`. Explain when storing multiple independent documents is better than one `Multi*` geometry.

## 30. Workflow for Designing Reliable Geospatial Data

When receiving a requirement to store geometry in MongoDB, proceed from **business semantics** to **geometry structure**, and only then decide on indexes and queries.

1. **Identify the unit of data:** point, line, region, multiple components of the same type, or a mixed set of shapes?
2. **Identify the CRS:** is the source data truly WGS84 longitude/latitude?
3. **Normalize positions:** `[longitude, latitude]`, finite numeric types, and valid ranges.
4. **Pick the right type:** do not turn a LineString into a MultiPoint or a Polygon with a hole into a MultiPolygon.
5. **Check topology:** ring closure, ring order, hole containment, self-intersection, overlapping shapes, and oversized regions.
6. **Design fields:** `location`, `route`, `serviceArea`, or `geometry` matching query patterns; avoid String fields containing JSON.
7. **Build proper indexes:** `2dsphere` on the **actual geometry field** when spatial queries are required.
8. **Pick operators by question:** within, intersects, or near; understand the difference between "completely inside" and "intersects."
9. **Test edge cases:** points inside holes, lines crossing boundaries, crossing the antimeridian, near-polar coordinates, and large Polygons.
10. **Measure on real data:** inspect `explain()`, index size, and latency; polygons with many vertices can be resource-intensive.
11. **Monitor source quality:** malformed geometries or wrong CRSs must be caught before corrupting business results.
12. **Document the contract:** field names, allowed geometry types, precision, data versioning, and distance units.

## 31. Summary

**GeoJSON describes geometry using `type` and a corresponding coordinate structure.** A `Point` is a single `[lon, lat]` position; a `LineString` is a sequence of vertices meant to connect into a path; a `Polygon` is a region bounded by **closed LinearRings**, optionally with **holes**. These three types solve three distinct geometric problems and should not be interchanged.

**Extended types have distinct meanings:** `MultiPoint` for multiple points, `MultiLineString` for multiple lines, `MultiPolygon` for multiple separate regions, and `GeometryCollection` holding mixed geometry types via the `geometries` field. A Polygon with multiple rings is not the same as a MultiPolygon: inner rings usually represent **excluded holes**, not additional regions.

**MongoDB processes GeoJSON with WGS84 spherical geographic semantics.** Proper **longitude-first, latitude-second** ordering, proper CRS, valid topology, and understanding how oversized polygons are interpreted are foundational requirements. `2dsphere` enables appropriate geometry queries; `$geoWithin`, `$geoIntersects`, and `$near` answer **different spatial questions**.

**Indexes cannot fix bad geometry, and valid geometry does not replace business logic.** A Point does not define a boundary on its own, a LineString is not a road network with shortest paths, and a Polygon does not encode warehouse operational rules. By choosing the right geometry, validating structure, and keeping data contracts explicit, MongoDB can effectively support location, route, and region queries in production applications.

## References

- [MongoDB Database Manual — GeoJSON Objects](https://www.mongodb.com/docs/manual/reference/geojson/): the seven geometry types, coordinate nesting, Polygons, and holes.
- [MongoDB Database Manual — Geospatial Queries](https://www.mongodb.com/docs/manual/geospatial-queries/): data models and spatial queries.
- [MongoDB Database Manual — 2dsphere Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/): creating and using spherical geometry indexes.
- [MongoDB Database Manual — $geoWithin](https://www.mongodb.com/docs/manual/reference/operator/query/geoWithin/): containment, large regions, and constraints.
- [MongoDB Database Manual — $geoIntersects](https://www.mongodb.com/docs/manual/reference/operator/query/geoIntersects/): intersection queries.
- [MongoDB Java Sync Driver — Geospatial Queries](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/geo/): GeoJSON types and builders for Java.
