# Region Queries with `$geoWithin` and `$geoIntersects` in MongoDB

## 1. Two Spatial Questions That Look Similar but Differ Fundamentally

A delivery system, real estate map, route manager, or disaster alert service often needs to answer questions such as:

- Which stores lie **inside** a given service zone?
- Which properties lie **completely inside** a map search area?
- Which shipping routes **cross or enter** a restricted zone?
- Which sales territories **overlap** with a selected region?
- When a user stands at a point, which service-area polygons **contain that point**?

MongoDB provides two spatial query operators:

- **`$geoWithin`**: selects documents whose stored geometry lies **completely within** the query region geometry.
- **`$geoIntersects`**: selects documents whose stored geometry **intersects** the query geometry—meaning their intersection is non-empty.

Both operators use MongoDB's geometry support, particularly GeoJSON and `2dsphere` indexes. They can return different results when the stored object is a `Polygon` or `LineString` instead of a `Point`.

> **Quick Rule of Thumb:** "The entire object must lie inside the region" → `$geoWithin`; "any part overlapping/touching the region suffices" → `$geoIntersects`.

Picking the right operator is only the first step. You must understand coordinate order, polygon structure, spherical geometry, boundary behavior, indexing strategies, and actual query costs.

---

## 2. How Does MongoDB Store Geospatial Data?

MongoDB supports **GeoJSON** data and **legacy coordinate pairs**.

### 2.1. GeoJSON Point

A place with `location`:

```javascript
{
  _id: "STORE-01",
  name: "Store A",
  location: {
    type: "Point",
    coordinates: [106.7005, 10.7755]
  }
}
```

Mandatory order when using longitude/latitude:

```text
coordinates: [ longitude, latitude ]
               east-west  north-south
```

Never swap it to `[latitude, longitude]`, even if some map services or APIs deliver data in the reverse order.

Standard limits in the geographic coordinate system used by `2dsphere`:

| Component | Valid Values |
| --- | --- |
| Longitude | From -180 to 180, inclusive |
| Latitude | From -90 to 90, inclusive |
| Default CRS of `$geometry` | WGS84 / EPSG:4326 |

The coordinate pairs in this lesson are for illustration only. Do not infer real roads, administrative boundaries, or true distances from simulated coordinates.

### 2.2. GeoJSON LineString

A simple route:

```javascript
{
  _id: "ROUTE-01",
  route: {
    type: "LineString",
    coordinates: [
      [106.68, 10.77],
      [106.70, 10.78],
      [106.73, 10.80]
    ]
  }
}
```

A `LineString` contains at least two positions. When querying for region intersection, MongoDB evaluates the geometric segments connecting these positions, not just the two endpoints.

### 2.3. GeoJSON Polygon

A simulated rectangular region near small coordinates:

```javascript
{
  type: "Polygon",
  coordinates: [
    [
      [0, 0],
      [4, 0],
      [4, 4],
      [0, 4],
      [0, 0]
    ]
  ]
}
```

An easily confused structure:

```text
Polygon
  coordinates = [
    ring 1 = [
      position 1 = [longitude, latitude],
      position 2 = [longitude, latitude],
      ...
      position N = position 1
    ]
  ]
```

- A `Polygon`'s `coordinates` is an **array of rings**, not a flat list of positions.
- Rings must be **closed**: the first and last positions must match.
- The exterior ring should form a non-self-intersecting region; interior rings can represent **holes**.
- Polygons larger than a hemisphere have special CRS requirements, covered later.

Structural error example:

```javascript
// Wrong: missing a ring array level.
{
  type: "Polygon",
  coordinates: [
    [0, 0],
    [4, 0],
    [4, 4],
    [0, 0]
  ]
}
```

Valid example:

```javascript
{
  type: "Polygon",
  coordinates: [
    [
      [0, 0],
      [4, 0],
      [4, 4],
      [0, 4],
      [0, 0]
    ]
  ]
}
```

### 2.4. GeoJSON MultiPolygon

An object consisting of multiple disjoint regions:

```javascript
{
  type: "MultiPolygon",
  coordinates: [
    [
      [
        [0, 0], [2, 0], [2, 2], [0, 2], [0, 0]
      ]
    ],
    [
      [
        [6, 6], [8, 6], [8, 8], [6, 8], [6, 6]
      ]
    ]
  ]
}
```

`MultiPolygon` adds one more array level compared to `Polygon`: an array of polygons, where each polygon contains an array of rings.

**Do not** set `type: "MultiPolygon"` and provide only the structure of an ordinary `Polygon`.

---

## 3. Both Operators from a Set-Theory Perspective

Let:

- `S` be the point set of the **geometry stored in the document**;
- `Q` be the point set of the **geometry passed into the query**.

Conceptual meaning:

```text
$geoWithin:
  S is contained in Q.

$geoIntersects:
  S intersect Q is non-empty.
```

For a small polygon completely inside the query polygon:

```text
Q:  +-------------------+
    |                   |
    |    +---------+    |
    |    |    S    |    |
    |    +---------+    |
    |                   |
    +-------------------+

$geoWithin:     Yes
$geoIntersects: Yes
```

For a polygon crossing the boundary:

```text
Q:  +-------------------+
    |               +---+-------+
    |               |   S       |
    |               +---+-------+
    +-------------------+

$geoWithin:     No
$geoIntersects: Yes
```

For two disjoint shapes:

```text
Q:  +------------+             S:  +--------+
    |            |                 |        |
    +------------+                 +--------+

$geoWithin:     No
$geoIntersects: No
```

### 3.1. Decision Table

| Stored Geometry | Relationship with Query Region | `$geoWithin` | `$geoIntersects` |
| --- | --- | --- | --- |
| Point | Clearly inside | Matches | Matches |
| Point | Clearly outside | No | No |
| Polygon | Completely inside | Matches | Matches |
| Polygon | Only partially inside | No | Matches |
| Polygon | Encloses the entire query region | No | Matches |
| LineString | Entire route inside region | Matches | Matches |
| LineString | Passes through region | No | Matches |
| Polygon/LineString | Completely disjoint | No | No |
| Shape only **touching an edge/vertex** | Degenerate case | **Not guaranteed like ideal geometry** | **Not guaranteed like ideal geometry** |

**Important regarding boundaries:** MongoDB explicitly notes that *degenerate geometry* cases are not guaranteed to follow an "on-boundary counts as inside" rule. For example, `$geoIntersects` does not guarantee detecting a polygon intersecting its own edge/vertex or another polygon that only shares an edge/vertex without overlapping interiors. `$geoWithin` likewise does not guarantee considering a shape to contain its own boundary components. Test boundary cases against business rules and do not ascribe full general-purpose GIS topological guarantees to the server.

---

## 4. Preparing the Test Dataset

To separate geometric understanding from real-map complexity, we use **simulated coordinates near the origin [0, 0]**. They are valid in WGS84, but do not represent a real business area.

### 4.1. Geographic Points

Create a new test collection without deleting production data:

```javascript
db.geoPoints294.insertMany([
  {
    _id: "P-IN-1",
    category: "store",
    name: "Inside Point 1",
    location: {
      type: "Point",
      coordinates: [1, 1]
    }
  },
  {
    _id: "P-IN-2",
    category: "warehouse",
    name: "Inside Point 2",
    location: {
      type: "Point",
      coordinates: [3, 2]
    }
  },
  {
    _id: "P-OUT",
    category: "store",
    name: "Outside Point",
    location: {
      type: "Point",
      coordinates: [6, 6]
    }
  },
  {
    _id: "P-BOUNDARY",
    category: "store",
    name: "Boundary Point for Testing",
    location: {
      type: "Point",
      coordinates: [4, 2]
    }
  }
]);
```

`P-BOUNDARY` is included deliberately to demonstrate why **you should not write tests relying on an absolute boundary assertion** without verifying specific behavior.

### 4.2. Geographic Polygons

Create another collection to clearly show the difference between **full containment** and **intersection**:

```javascript
db.geoAreas294.insertMany([
  {
    _id: "A-INNER",
    name: "Completely Inside Area",
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [1, 1], [2, 1], [2, 2], [1, 2], [1, 1]
        ]
      ]
    }
  },
  {
    _id: "A-CROSS",
    name: "Right-Edge Crossing Area",
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [3, 1], [5, 1], [5, 3], [3, 3], [3, 1]
        ]
      ]
    }
  },
  {
    _id: "A-OUTER",
    name: "Area Enclosing Query Area",
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [-1, -1], [6, -1], [6, 6], [-1, 6], [-1, -1]
        ]
      ]
    }
  },
  {
    _id: "A-FAR",
    name: "Disjoint Area",
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [7, 7], [8, 7], [8, 8], [7, 8], [7, 7]
        ]
      ]
    }
  }
]);
```

The four polygons are positioned so there is no ambiguity over edge-touching in the main cases.

### 4.3. Shared Query Polygon

```javascript
const queryArea = {
  type: "Polygon",
  coordinates: [
    [
      [0, 0],
      [4, 0],
      [4, 4],
      [0, 4],
      [0, 0]
    ]
  ]
};
```

This is a **query geometry**, not a document inserted into a collection. All examples below use this `queryArea` in the same `mongosh` session unless noted otherwise.

---

## 5. Using `$geoWithin` to Find Points Inside a Region

Standard syntax:

```javascript
db.geoPoints294.find({
  location: {
    $geoWithin: {
      $geometry: queryArea
    }
  }
});
```

Or written out in full:

```javascript
db.geoPoints294.find({
  location: {
    $geoWithin: {
      $geometry: {
        type: "Polygon",
        coordinates: [
          [
            [0, 0],
            [4, 0],
            [4, 4],
            [0, 4],
            [0, 0]
          ]
        ]
      }
    }
  }
});
```

**Guaranteed results given the clear inside/outside placement:**

- `P-IN-1` and `P-IN-2` match.
- `P-OUT` does not match.
- `P-BOUNDARY` must be tested separately; do not use it to infer an absolute boundary rule.

Query returning only ID and name:

```javascript
db.geoPoints294.find(
  {
    location: {
      $geoWithin: {
        $geometry: queryArea
      }
    }
  },
  {
    _id: 1,
    name: 1,
    category: 1
  }
).sort({ _id: 1 });
```

**`$geoWithin` does not automatically sort by distance or name.** If the API needs deterministic ordering, add an appropriate `sort()` or `$sort`.

### 5.1. Combining Regular Conditions

```javascript
db.geoPoints294.find({
  category: "store",
  location: {
    $geoWithin: {
      $geometry: queryArea
    }
  }
});
```

Meaning: only stores inside the region. The `category` condition is a standard filter combined via AND and does not alter how the geometry is defined.

---

## 6. Using `$geoWithin` for Stored Polygons

If the document's field is a Polygon, `$geoWithin` requires **that entire geometry** to lie inside the query region:

```javascript
db.geoAreas294.find(
  {
    geometry: {
      $geoWithin: {
        $geometry: queryArea
      }
    }
  },
  {
    _id: 1,
    name: 1
  }
).sort({ _id: 1 });
```

In the sample dataset, the unambiguous match is:

```text
A-INNER
```

Explanation:

- `A-INNER` lies completely inside `queryArea`.
- `A-CROSS` extends outside the right edge.
- `A-OUTER` is larger and encloses the query region itself, so it is **not completely inside the query**.
- `A-FAR` is far away and does not intersect.

**Crucial distinction:** "does polygon A contain polygon Q?" has the opposite direction from "is polygon A inside polygon Q?". In MongoDB syntax, **the document field sits outside the operator** and **the geometry passed to `$geometry` is the reference region**. To ask "which region contains a point?", switch to `$geoIntersects` on the polygon field with a Point query.

---

## 7. Using `$geoIntersects` to Find Objects Intersecting a Region

Syntax:

```javascript
db.geoAreas294.find({
  geometry: {
    $geoIntersects: {
      $geometry: queryArea
    }
  }
});
```

Or returning only IDs:

```javascript
db.geoAreas294.find(
  {
    geometry: {
      $geoIntersects: {
        $geometry: queryArea
      }
    }
  },
  { _id: 1, name: 1 }
).sort({ _id: 1 });
```

For the four sample polygons, expected results:

```text
A-CROSS
A-INNER
A-OUTER
```

`A-FAR` does not intersect and is excluded.

Comparison:

| Object | `$geoWithin` | `$geoIntersects` | Reason |
| --- | --- | --- | --- |
| `A-INNER` | Yes | Yes | Lies completely inside query. |
| `A-CROSS` | No | Yes | Has overlapping area but extends outside. |
| `A-OUTER` | No | Yes | Encloses the entire query; still intersects. |
| `A-FAR` | No | No | Disjoint. |

### 7.1. Using `$geoIntersects` with Points

For a Point inside a Polygon, the intersection is non-empty:

```javascript
db.geoPoints294.find({
  location: {
    $geoIntersects: {
      $geometry: queryArea
    }
  }
});
```

For Points not lying on the boundary, the result matches `$geoWithin` semantically when finding points inside a region.

However, **do not generalize that the two operators are equivalent**. When documents store LineStrings or Polygons, "completely inside" and "intersects" differ greatly.

### 7.2. Not a Distance Operator

`$geoIntersects` evaluates a **boolean spatial relationship**; it does not return a distance value to the region center. If you need nearest results sorted by proximity, use `$near`, `$nearSphere`, or `$geoNear` as appropriate.

---

## 8. Reverse Query: Finding Regions That Contain a Location

This is an extremely common scenario where beginners often get the direction backwards.

Suppose the `deliveryZones` collection stores **delivery-area Polygons**, and a user has a Point. To find which zones contain that Point, query **the polygon field** using `$geoIntersects` with the Point:

```javascript
const customerPoint = {
  type: "Point",
  coordinates: [1.5, 1.5]
};

db.geoAreas294.find({
  geometry: {
    $geoIntersects: {
      $geometry: customerPoint
    }
  }
});
```

In the sample dataset, the polygons whose interiors clearly contain `[1.5, 1.5]` are `A-INNER` and `A-OUTER`.

### 8.1. Why Not Use `$geoWithin` in This Direction?

Incorrect for **business semantics**:

```javascript
db.geoAreas294.find({
  geometry: {
    $geoWithin: {
      $geometry: customerPoint
    }
  }
});
```

The query above asks for **an entire polygon in the database to fit inside a single point**. It does not ask "is the user's point inside the polygon?".

Mental mnemonic:

```text
Stored STORE is Point, QUERY is Polygon:
  STORE inside QUERY => $geoWithin.

Stored ZONE is Polygon, QUERY is Point:
  ZONE intersects Point => $geoIntersects.
```

### 8.2. Overlapping Regions

If multiple regions contain the customer Point, the query can return **multiple documents**. MongoDB does not automatically pick the cheapest zone or the preferred store's zone. The application must add:

- Tenant or merchant ID.
- Active zone status.
- Zone priority.
- Operating hours and service rules.
- Tie-breaking rules when multiple zones contain the same Point.

Example:

```javascript
db.deliveryZones.find({
  tenantId: "T100",
  status: "ACTIVE",
  geometry: {
    $geoIntersects: {
      $geometry: customerPoint
    }
  }
}).sort({
  priority: -1,
  _id: 1
});
```

With overlapping regions, business ordering is a domain rule, not part of the spatial operator's semantics.

---

## 9. LineString: Completely Inside or Merely Crossing a Region?

Insert two sample routes:

```javascript
db.geoRoutes294.insertMany([
  {
    _id: "R-IN",
    line: {
      type: "LineString",
      coordinates: [
        [1, 1], [2, 2], [3, 3]
      ]
    }
  },
  {
    _id: "R-CROSS",
    line: {
      type: "LineString",
      coordinates: [
        [-1, 2], [2, 2], [5, 2]
      ]
    }
  },
  {
    _id: "R-FAR",
    line: {
      type: "LineString",
      coordinates: [
        [7, 7], [8, 8]
      ]
    }
  }
]);
```

Find routes **completely inside** the region:

```javascript
db.geoRoutes294.find({
  line: {
    $geoWithin: {
      $geometry: queryArea
    }
  }
});
```

Clearly `R-IN` matches. `R-CROSS` has its start and end outside the region; `R-FAR` is disjoint.

Find routes **passing through or intersecting** the region:

```javascript
db.geoRoutes294.find({
  line: {
    $geoIntersects: {
      $geometry: queryArea
    }
  }
});
```

Both `R-IN` and `R-CROSS` match because they have segments inside the polygon.

### 9.1. Do Not Inspect Only Endpoints

A LineString with both endpoints outside can still match `$geoIntersects` if a middle segment passes through the region.

Conversely, a route whose start and end lie inside but detours outside in the middle is not completely inside the query region. `$geoWithin` evaluates the **entire line**, not just `coordinates[0]`.

### 9.2. This Is Geometry, Not a Road Network

MongoDB does not account for one-way streets, intersections, overpasses, traffic rules, or graph connectivity. A geometric line intersecting a region does not prove a vehicle actually entered that region if the LineString is merely straight segments connecting sparse GPS samples.

For high-reliability geofencing, use dense GPS sampling, map matching, or dedicated routing tools.

---

## 10. Polygons with Holes

A delivery-zone polygon may cover a large region while excluding an area in the middle:

```javascript
const zoneWithHole = {
  type: "Polygon",
  coordinates: [
    [
      [0, 0],
      [10, 0],
      [10, 10],
      [0, 10],
      [0, 0]
    ],
    [
      [4, 4],
      [4, 6],
      [6, 6],
      [6, 4],
      [4, 4]
    ]
  ]
};
```

The first ring is the exterior boundary; subsequent rings are **holes**. Definitions must follow GeoJSON rules, ring closure, no self-intersection, and winding orientation appropriate for the geometry and CRS used.

Illustrative Points:

- `[2, 2]` lies clearly inside the covered area.
- `[5, 5]` lies clearly inside the hole, **not part of the covered area**.
- `[12, 12]` is completely outside.

Direct usage example:

```javascript
db.geoPoints294.find({
  location: {
    $geoWithin: {
      $geometry: zoneWithHole
    }
  }
});
```

For delivery systems, holes can represent parks, lakes, restricted zones, or pockets where orders are not accepted.

**Do not drop holes by keeping only the outer ring**: points inside the hole will be mistakenly treated as served. If regions imported from GIS have multiple holes, validate them with a GeoJSON library before writing.

### 10.1. LineString Intersecting a Polygon with a Hole

A route lying purely inside the **hole** may not intersect the polygon's area; a route crossing the valid region and then passing through the hole still intersects the valid region. Use `$geoIntersects` on the full LineString, not `$geoWithin` on the polygon's bounding box.

### 10.2. MultiPolygon

If a service region consists of multiple detached "islands," use a GeoJSON `MultiPolygon` rather than creating a self-intersecting ring to bridge the islands. `$geoWithin` and `$geoIntersects` support GeoJSON geometries for permitted data types, including using a `MultiPolygon` as the query region.

---

## 11. Legacy Shapes: `$box`, `$polygon`, `$center`, and `$centerSphere`

`$geoWithin` does not only have `$geometry` syntax. MongoDB also supports shape specifiers for **legacy coordinate pairs**:

| Shape Specifier | Meaning | Computation Model | Suitable Index |
| --- | --- | --- | --- |
| `$geometry: {type:"Polygon",...}` | GeoJSON Polygon/MultiPolygon | Spherical | `2dsphere` |
| `$box` | Rectangle by two corners | Planar | `2d` |
| `$polygon` | Legacy polygon | Planar | `2d` |
| `$center` | Legacy planar circle | Planar | `2d` |
| `$centerSphere` | Circle on a sphere | Spherical | `2dsphere` and `2d` per conditions |

`$geoIntersects` does **not** use `$box`, `$polygon`, or `$center` as a GeoJSON query geometry. It accepts GeoJSON objects via `$geometry`.

### 11.1. Separate Legacy Data

```javascript
db.geoLegacy294.insertMany([
  { _id: "L-IN", loc: [1, 1] },
  { _id: "L-OUT", loc: [6, 6] }
]);

db.geoLegacy294.createIndex({
  loc: "2d"
});
```

Here `loc` is `[x, y]`, not:

```javascript
{
  type: "Point",
  coordinates: [x, y]
}
```

### 11.2. `$box`

```javascript
db.geoLegacy294.find({
  loc: {
    $geoWithin: {
      $box: [
        [0, 0],
        [4, 4]
      ]
    }
  }
});
```

`$box` uses **planar geometry**, suited for XY coordinate problems on a flat plane. It does not turn a lat/lon rectangle into an accurate geodesic polygon on Earth.

### 11.3. `$polygon`

```javascript
db.geoLegacy294.find({
  loc: {
    $geoWithin: {
      $polygon: [
        [0, 0],
        [4, 0],
        [2, 4]
      ]
    }
  }
});
```

Legacy `$polygon` implicitly closes the final edge back to the first point and uses **planar** geometry. It is not used for GeoJSON Polygons with a `2dsphere` index in the same way as `$geometry`.

### 11.4. `$center`

```javascript
db.geoLegacy294.find({
  loc: {
    $geoWithin: {
      $center: [
        [1, 1],
        2
      ]
    }
  }
});
```

The radius of `$center` is measured in **the planar coordinate units**, not automatically in meters or kilometers.

### 11.5. `$centerSphere`

For a real radius measured on a sphere:

```javascript
db.geoPoints294.find({
  location: {
    $geoWithin: {
      $centerSphere: [
        [1, 1],
        5 / 6378.1
      ]
    }
  }
});
```

This is an example of a circle of radius roughly **5 km** around `[longitude=1, latitude=1]`, using an approximate Earth radius of `6378.1 km`. **The radius parameter of `$centerSphere` is in radians**, not meters or degrees.

Formula:

```text
angularRadiusRadians = distanceKm / earthRadiusKm
                     ≈ distanceKm / 6378.1
```

Do not pass:

```javascript
$centerSphere: [[1, 1], 5000]
```

thinking `5000` means 5,000 meters. That number has the wrong unit and cannot represent a 5 km search.

---

## 12. How Do Radius Queries Differ from `$near`?

The problem "which points are **within** 5 km of the center" has at least two approaches:

1. **Only need to know whether they fall inside the circle** → `$geoWithin` with `$centerSphere`.
2. **Need results sorted nearest first and/or need the distance** → `$near`, `$nearSphere`, or `$geoNear` aggregation.

Circle membership example:

```javascript
const center = [106.70, 10.78];
const radiusKm = 5;

db.places.find({
  location: {
    $geoWithin: {
      $centerSphere: [
        center,
        radiusKm / 6378.1
      ]
    }
  }
});
```

The query above does **not** sort by distance.

Distance query using a GeoJSON Point with a meter radius:

```javascript
db.places.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: center
      },
      $maxDistance: 5000
    }
  }
});
```

`$near` requires an appropriate geospatial index and sorts by distance. With GeoJSON and `2dsphere`, `$maxDistance` is interpreted in **meters**, unlike the radians of `$centerSphere`.

### 12.1. Quick Comparison

| Goal | Use |
| --- | --- |
| Points inside an administrative polygon | `$geoWithin` + Polygon |
| Polygon zone intersecting a search area | `$geoIntersects` |
| Route passing through an area | `$geoIntersects` |
| Points within 5 km radius, no sorting needed | `$geoWithin` + `$centerSphere` |
| 10 nearest points ordered by distance | `$near` or `$geoNear` |
| Compute distance field in aggregation | `$geoNear` and appropriate stages |

**Geometric distance** is not equivalent to road driving distance. MongoDB does not replace a routing engine with these operators.

---

## 13. Creating `2dsphere` Indexes for Region Queries

MongoDB allows `$geoWithin` and `$geoIntersects` to run **without a geospatial index**, though performance typically degrades on large collections. For Earth-based GeoJSON, the recommended index is `2dsphere`.

```javascript
db.geoPoints294.createIndex({
  location: "2dsphere"
});

db.geoAreas294.createIndex({
  geometry: "2dsphere"
});

db.geoRoutes294.createIndex({
  line: "2dsphere"
});
```

### 13.1. What Gets Indexed?

- `Point`: position.
- `LineString`: line geometry.
- `Polygon`: region geometry.
- `MultiPolygon`: multiple regions in the same field.

MongoDB builds an internal spatial representation for spherical indexing. During a query, the index narrows down candidates; the server still evaluates the geometric relationship to return semantically accurate results.

### 13.2. `$geoIntersects` and Indexes

Server documentation notes:

- `$geoIntersects` **does not require** a geospatial index to execute.
- However, **only a `2dsphere` geospatial index** supports optimizing this query type.
- A `2d` index is not a valid substitute for spherical `$geoIntersects` geometry queries.

Similarly, note the distinction for `$geoWithin`: `$geoWithin` can use `2dsphere` for spherical GeoJSON or `2d` for supported legacy planar shapes.

### 13.3. `2dsphere` Indexes Are Sparse

MongoDB `2dsphere` indexes are **inherently sparse**:

- Documents without the geometry field do not get an entry from that field.
- A geospatial field that is `null` or an empty array produces no entry.
- In a compound `2dsphere` index, whether the geospatial field contains valid indexable data determines whether the document is indexed—not merely the regular fields.

This matters for reports like "find all records in the region": documents **without valid coordinates** cannot simply be treated as "outside" or "inside" the region; track missing-location records separately.

### 13.4. Wrong Data Types Can Break Index Builds or Inserts

Schema error example:

```javascript
{
  _id: "BROKEN",
  location: "10.78,106.70"
}
```

A string is neither a valid GeoJSON geometry nor a valid legacy pair. If the field is indexed with `2dsphere`, inserts or index builds can fail. Validate and migrate legacy data before building production indexes.

### 13.5. An Index Cannot Replace the Shard Key Policy

MongoDB **does not allow using a geospatial index as a shard key**. You can create a `2dsphere` index on a sharded collection, but the shard key must be chosen separately per sharding rules. Never write `sh.shardCollection("db.coll",{location:"2dsphere"})` as a region-based sharding strategy.

---

## 14. Compound Indexes Combining Business Filters and Geospatial

A multi-tenant service collection:

```javascript
{
  _id: "STORE-100",
  tenantId: "T100",
  status: "ACTIVE",
  category: "pharmacy",
  location: {
    type: "Point",
    coordinates: [106.70, 10.78]
  }
}
```

Many requests filter by tenant/status/category and a region:

```javascript
db.stores.find({
  tenantId: "T100",
  status: "ACTIVE",
  location: {
    $geoWithin: {
      $geometry: someRegion
    }
  }
});
```

A compound index worth testing:

```javascript
db.stores.createIndex({
  tenantId: 1,
  status: 1,
  location: "2dsphere"
});
```

Choosing field order and deciding whether separate indexes are needed for other queries must be based on **real production statistics**, not a single example.

### 14.1. A Compound Index Is Not Always Chosen

The query planner may pick another plan if:

- A condition is too broad and low-selectivity.
- The geospatial portion generates too many candidates.
- Another index is cheaper.
- Data distributions/statistics change.
- A `$sort` requires an index matching a different order.

Use `explain("executionStats")` and real latency measurements before concluding.

### 14.2. Geospatial Indexes Do Not Cover Queries

MongoDB geospatial indexes do not support **covered queries** the way standard B-tree indexes can completely satisfy a query without reading documents. Do not assume projecting just a few fields avoids fetching documents from storage.

---

## 15. Inspecting Performance with Explain

```javascript
db.geoAreas294.find({
  geometry: {
    $geoIntersects: {
      $geometry: queryArea
    }
  }
}).explain("executionStats");
```

Things to examine:

- Is an appropriate geospatial index used?
- What are `totalKeysExamined` and `totalDocsExamined`?
- Is `nReturned` much smaller than candidate documents?
- Does the plan include geo matching/index stages or a broad scan?
- Does the query include tenant/status filters that narrow data before geometry evaluation?
- How does latency change if the query polygon has many vertices or spans a large portion of the globe?

Stage names in `explain` vary by MongoDB version and execution engine. Do not hardcode a single stage name as sole verification.

### 15.1. `$geoWithin` and `$geoIntersects` Do Not Sort

If the client wants results ordered by name or ID:

```javascript
db.geoAreas294.find({
  geometry: {
    $geoIntersects: {
      $geometry: queryArea
    }
  }
}).sort({
  name: 1,
  _id: 1
});
```

Sorting can be expensive when many documents match. If you need results sorted by distance to a Point, use `$near`/`$geoNear` or compute distances accordingly—do not assume `geoWithin`/`geoIntersects` provide a distance score.

### 15.2. `$match` in Aggregation

```javascript
db.geoAreas294.aggregate([
  {
    $match: {
      geometry: {
        $geoIntersects: {
          $geometry: queryArea
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      name: 1
    }
  },
  {
    $sort: {
      name: 1
    }
  }
]);
```

When possible, place region and tenant filters early in the pipeline to reduce intermediate documents. However, optimizer behavior and index selection depend on the specific stages, so still inspect `explain`.

---

## 16. Using `$geoIntersects` with a GeoJSON Point Query

Not every geospatial query geometry has to be a Polygon.

For a collection storing **polygon regions**, find which regions contain a Point:

```javascript
db.geoAreas294.find({
  geometry: {
    $geoIntersects: {
      $geometry: {
        type: "Point",
        coordinates: [1.5, 1.5]
      }
    }
  }
});
```

For a collection storing **routes**, you can ask which routes pass through a Polygon query region. For a collection storing polygons, you can ask which regions intersect a **LineString** inspection corridor.

```javascript
const inspectionRoute = {
  type: "LineString",
  coordinates: [
    [-1, 1],
    [2, 2],
    [5, 3]
  ]
};

db.geoAreas294.find({
  geometry: {
    $geoIntersects: {
      $geometry: inspectionRoute
    }
  }
});
```

Geometrically, intersection is a **symmetric** relationship between two shapes: the line intersects the polygon and the polygon intersects the line. However, **the document field, index, and collection being queried** determine which MongoDB query answers your business need.

---

## 17. Polygons Larger Than a Hemisphere and Strict Winding CRS

A rare but serious issue occurs with GeoJSON Polygons larger than **half the Earth's surface area**.

With the default CRS, MongoDB may interpret a polygon larger than one hemisphere as its **smaller complementary geometry**. Results can be the exact opposite of what was intended for a huge region query.

For a **single-ring GeoJSON Polygon** covering at least roughly one hemisphere, MongoDB provides a custom CRS:

```javascript
const bigPolygon = {
  type: "Polygon",
  coordinates: [
    [
      [-100, 60],
      [-100, 0],
      [-100, -60],
      [100, -60],
      [100, 60],
      [-100, 60]
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

Usage:

```javascript
db.worldRegions.find({
  geometry: {
    $geoIntersects: {
      $geometry: bigPolygon
    }
  }
});
```

or:

```javascript
db.worldRegions.find({
  geometry: {
    $geoWithin: {
      $geometry: bigPolygon
    }
  }
});
```

### 17.1. Important Conditions

- The custom CRS above is **MongoDB's strict winding** mechanism.
- It uses **counterclockwise winding order** for a single-ring polygon per the rule.
- Do not apply the same mechanism to arbitrary `MultiPolygon`s or multi-ring polygons that are oversized and expect identical single-ring behavior.
- If a large polygon uses the default CRS, queries may target the **smaller complementary region** instead of the intended huge region.

For city or district systems with small polygons, do not attach this custom CRS to every query just because you saw an example online. Use it only when large-geometry cases and requirements warrant it.

### 17.2. Regions Near the Antimeridian and Poles

Longitudes `+179.9` and `-179.9` are close on Earth, even though far apart on a linear number line. `2dsphere` understands spherical geometry. A naive planar bounding box simulating "from 179 to -179" easily creates a wrong or invalid rectangle.

If a query region crosses the **antimeridian** (International Date Line), use proper GeoJSON data and polygon-splitting strategies—do not take `minLongitude=-179`, `maxLongitude=179` and treat it as a 2-degree-wide viewport.

---

## 18. Boundaries: Why Not Assume Inclusive by Default?

In pure mathematical geometry, we often ask whether a point lying **on an edge** counts as inside. In MongoDB geospatial queries, documentation states that boundary/degenerate cases are not guaranteed.

### 18.1. `$geoWithin`

MongoDB does not guarantee that a shape contains its own component geometries or another polygon that only shares component boundaries. Therefore, do not write a rule asserting "every Point on a vertex/edge belongs to the zone" without verifying.

### 18.2. `$geoIntersects`

MongoDB does not guarantee treating a polygon as intersecting:

- Its own edges.
- Its own vertices.
- Another polygon that only shares edges/vertices with no overlapping interior.

### 18.3. Business Implications

- **Delivery fees on zone borders:** need deterministic tie-breaking rules in the business layer.
- **Legal boundary adjudication:** need proper GIS systems and geometry validation, not a single MongoDB predicate.
- **Disaster alerts:** may add a controlled safety buffer and factor in GPS accuracy.
- **Devices hovering near a polygon edge:** GPS jitter can flip inside/outside status repeatedly; use hysteresis or multiple consecutive samples.

For example, "adding 10 meters for safety" cannot be implemented by adding a fixed `0.0001` to all longitudes and latitudes globally. A degree's ground length depends on latitude and projection.

---

## 19. GeoJSON Polygon Validation: Valid Data Before Querying

MongoDB performs some schema/geometry checks, but applications should validate inputs early to avoid storing corrupt data and to return clear errors.

A solid validation workflow:

1. Verify `type` is among the GeoJSON geometry types supported by the feature.
2. Verify `coordinates` has the proper array nesting depth.
3. Verify each Position contains finite numbers and valid lon/lat ranges.
4. For Polygons: every linear ring is closed, first and last positions match, and minimum position count is met.
5. Check for self-intersections, duplicate rings, or holes outside the outer ring when the domain forbids them.
6. Enforce limits on vertex counts, BSON size, geometric complexity, and total polygon count.
7. Normalize CRS/coordinate conventions intentionally rather than guessing swapped lat/lon.
8. Establish policies for handling near-antimeridian and polar regions.
9. Verify data belongs to an authorized tenant/namespace.
10. Test boundary cases with a business-representative dataset.

### 19.1. Do Not "Fix" Invalid Polygons with Naive Tricks

A self-intersecting "bow tie" polygon:

```javascript
{
  type: "Polygon",
  coordinates: [
    [
      [0, 0],
      [4, 4],
      [0, 4],
      [4, 0],
      [0, 0]
    ]
  ]
}
```

is not a valid simple polygon for region semantics. Do not solve this by sorting vertices by longitude, as that alters the shape and meaning. Use a proper GIS library to repair it, or reject the input and ask the client for valid geometry.

### 19.2. JSON Schema Validation

A MongoDB schema can require `location` to exist and be an object, but it **does not replace full geometry validation**:

```javascript
db.runCommand({
  collMod: "geoPoints294",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["location"],
      properties: {
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
              maxItems: 2
            }
          }
        }
      }
    }
  },
  validationAction: "error"
});
```

This example **only illustrates document shape** and intentionally omits per-coordinate numeric/range checks. In production, do not overwrite an existing validator without merging existing rules; implement validation at the API and/or GIS layer.

---

## 20. Java Sync Driver: Storing GeoJSON and Creating Indexes

The MongoDB Java Sync Driver includes convenient GeoJSON classes:

- `com.mongodb.client.model.geojson.Point`
- `com.mongodb.client.model.geojson.Position`
- `com.mongodb.client.model.geojson.LineString`
- `com.mongodb.client.model.geojson.Polygon`

Example storing a Point:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Indexes;
import com.mongodb.client.model.geojson.Point;
import com.mongodb.client.model.geojson.Position;
import org.bson.Document;

public final class StoreLocationRepository {

    public static void prepareIndex(
            MongoCollection<Document> stores
    ) {
        stores.createIndex(Indexes.geo2dsphere("location"));
    }

    public static void insertStore(
            MongoCollection<Document> stores,
            String id,
            double longitude,
            double latitude
    ) {
        if (!Double.isFinite(longitude) ||
            !Double.isFinite(latitude) ||
            longitude < -180.0 || longitude > 180.0 ||
            latitude < -90.0 || latitude > 90.0) {
            throw new IllegalArgumentException(
                "Invalid longitude/latitude"
            );
        }

        Point location = new Point(
            new Position(longitude, latitude)
        );

        stores.insertOne(
            new Document("_id", id)
                .append("location", location)
        );
    }
}
```

This uses modern Java driver syntax; `createIndex` should run during migration/startup, not on every HTTP request.

**Note:** callers pass `longitude` first and `latitude` second. If data from a device or external service uses the reverse order, convert at a controlled boundary layer.

---

## 21. Java Sync Driver: Querying with `Filters.geoWithin`

Assuming `geometry` or `location` is stored as GeoJSON with an appropriate index:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.geojson.Polygon;
import com.mongodb.client.model.geojson.Position;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Arrays;

public final class GeoWithinService {

    public static void findStoresInside(
            MongoCollection<Document> stores
    ) {
        Polygon searchArea = new Polygon(Arrays.asList(
            new Position(0, 0),
            new Position(4, 0),
            new Position(4, 4),
            new Position(0, 4),
            new Position(0, 0)
        ));

        Bson condition = Filters.geoWithin(
            "location",
            searchArea
        );

        stores.find(condition).forEach(
            doc -> System.out.println(doc.toJson())
        );
    }
}
```

`Filters.geoWithin(fieldName, polygon)` builds the predicate corresponding to `$geoWithin + $geometry`. You do not need to construct raw BSON manually when using GeoJSON classes.

### 21.1. Combining Tenant Filters

```java
Bson filter = Filters.and(
    Filters.eq("tenantId", tenantId),
    Filters.eq("status", "ACTIVE"),
    Filters.geoWithin("location", searchArea)
);

stores.find(filter)
    .projection(new Document("_id", 1)
        .append("name", 1))
    .limit(100)
    .forEach(doc -> System.out.println(doc.toJson()));
```

`tenantId` and `searchArea` are supplied by the service and require validation. `limit(100)` only caps returned documents—it **does not guarantee the query is cheap** if filters are broad or indexes are inadequate.

---

## 22. Java Sync Driver: Querying with `Filters.geoIntersects`

Finding polygon areas that intersect a query polygon:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.geojson.Polygon;
import com.mongodb.client.model.geojson.Position;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.Arrays;

public final class GeoIntersectionService {

    public static void findIntersectingAreas(
            MongoCollection<Document> areas
    ) {
        Polygon query = new Polygon(Arrays.asList(
            new Position(0, 0),
            new Position(4, 0),
            new Position(4, 4),
            new Position(0, 4),
            new Position(0, 0)
        ));

        Bson filter = Filters.geoIntersects(
            "geometry",
            query
        );

        areas.find(filter)
            .forEach(doc -> System.out.println(doc.toJson()));
    }
}
```

### 22.1. Java: Finding Zones Containing a Customer Point

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.geojson.Point;
import com.mongodb.client.model.geojson.Position;
import org.bson.Document;
import org.bson.conversions.Bson;

public final class DeliveryZoneLookup {

    public static void lookup(
            MongoCollection<Document> zones,
            String tenantId,
            double longitude,
            double latitude
    ) {
        Point customer = new Point(
            new Position(longitude, latitude)
        );

        Bson filter = Filters.and(
            Filters.eq("tenantId", tenantId),
            Filters.eq("active", true),
            Filters.geoIntersects("geometry", customer)
        );

        zones.find(filter).forEach(
            zone -> System.out.println(zone.toJson())
        );
    }
}
```

Here the document's `geometry` field is a Polygon/MultiPolygon, while the query object is a Point. That is the right direction for "which zone contains the customer point."

With the Java driver, `Filters.geoIntersects` expects an appropriate geometry object such as `Point` or `Polygon`. The driver constructs the BSON; the server evaluates the spatial relationship.

---

## 23. When Not Using Java's GeoJSON Classes

Some applications already hold GeoJSON as a `Document` or receive shapes from JSON APIs. You can build the BSON filter directly:

```java
import org.bson.Document;
import org.bson.conversions.Bson;

Document polygon = new Document("type", "Polygon")
    .append("coordinates", java.util.List.of(
        java.util.List.of(
            java.util.List.of(0.0, 0.0),
            java.util.List.of(4.0, 0.0),
            java.util.List.of(4.0, 4.0),
            java.util.List.of(0.0, 4.0),
            java.util.List.of(0.0, 0.0)
        )
    ));

Bson withinFilter = new Document(
    "location",
    new Document(
        "$geoWithin",
        new Document("$geometry", polygon)
    )
);

Bson intersectsFilter = new Document(
    "geometry",
    new Document(
        "$geoIntersects",
        new Document("$geometry", polygon)
    )
);
```

Never store a string `"{type:'Polygon',...}"` and pass it into `$geometry` as a string. MongoDB requires a **BSON object with valid GeoJSON structure**.

### 23.1. When Receiving a Polygon from an HTTP API

- Limit vertex count, payload size, and nesting depth before sending to MongoDB.
- Do not allow requests to specify arbitrary query fields or operators.
- Use BSON builders/data structures; never concatenate JSON queries as strings.
- Validate tenant permissions and authorized regions.
- Explicitly define the coordinate system and longitude/latitude format.
- Enforce pagination, timeouts, query memory limits, and result caps.

---

## 24. End-to-End Use Case: Finding Delivery Zones Intersecting an Incident Area

Suppose `deliveryZones` stores service-area polygons, and a road-closure incident is issued as a Polygon `incidentArea`.

Goal: **find all affected zones, even if only partially intersected**.

```javascript
const incidentArea = {
  type: "Polygon",
  coordinates: [
    [
      [106.70, 10.77],
      [106.73, 10.77],
      [106.73, 10.80],
      [106.70, 10.80],
      [106.70, 10.77]
    ]
  ]
};

db.deliveryZones.find({
  tenantId: "T100",
  status: "ACTIVE",
  geometry: {
    $geoIntersects: {
      $geometry: incidentArea
    }
  }
});
```

Because the question is "is any part affected?", use `$geoIntersects`. Using `$geoWithin` would **drop** partially affected zones—a serious business bug.

### 24.1. What If You Want Zones Completely Inside the Incident Area?

When the requirement changes to "zones **completely covered** by the incident polygon," use:

```javascript
db.deliveryZones.find({
  geometry: {
    $geoWithin: {
      $geometry: incidentArea
    }
  }
});
```

This is a different question, not an arbitrary optimization.

### 24.2. Do Not Expect Overlap Percentage Automatically

`$geoIntersects` returns a **yes/no** match. It does not return the percentage of overlapping area, affected route length, or clipped polygon geometry.

If you need "zones affected across more than 30% of their area," use a GIS intersection/area engine or an appropriate spatial analytics architecture rather than trying to combine `$geoIntersects` with `$size`.

---

## 25. Map Use Case: Bounding Box Instead of a Business Zone

Frontends frequently send a viewport:

```json
{
  "west": 106.65,
  "south": 10.73,
  "east": 106.75,
  "north": 10.83
}
```

If the dataset stores GeoJSON points, you can construct a Polygon to find points inside the map region:

```javascript
const viewport = {
  type: "Polygon",
  coordinates: [
    [
      [106.65, 10.73],
      [106.75, 10.73],
      [106.75, 10.83],
      [106.65, 10.83],
      [106.65, 10.73]
    ]
  ]
};

db.stores.find({
  location: {
    $geoWithin: {
      $geometry: viewport
    }
  }
}).limit(200);
```

**Differences between a viewport and a service zone:**

- A viewport is the part of the map the user is currently viewing; it changes continuously on pan/zoom.
- A service zone is a business polygon typically stored with versioning and policies.
- If the viewport crosses the antimeridian, do not build a polygon naively from west/east.
- MongoDB spherical polygons do not match rectangular pixel viewports on a Web Mercator map identically. At low zoom levels or huge regions, verify behavior near poles and the antimeridian.

### 25.1. APIs Under Heavy Pan/Zoom Traffic

Do not trigger a full collection scan for every few-pixel pan. Instead:

1. Use a `2dsphere` index.
2. Debounce/throttle requests on the client.
3. Cap result counts and use clustering strategies at low zoom levels.
4. Cache by viewport/grid where appropriate.
5. Apply query predicates/filters by category/status.
6. Measure p95/p99 latency, documents scanned, and response bytes.

`limit(200)` caps the response size; it does not replace indexing or query planning.

---

## 26. Use Case: Checking Whether a Shipping Route Crosses a Restricted Area

Data:

```javascript
{
  _id: "ROUTE-204",
  tenantId: "T100",
  route: {
    type: "LineString",
    coordinates: [
      [106.68, 10.75],
      [106.71, 10.78],
      [106.74, 10.81]
    ]
  }
}
```

Predicate:

```javascript
db.routes.find({
  tenantId: "T100",
  route: {
    $geoIntersects: {
      $geometry: incidentArea
    }
  }
});
```

When you need routes **completely inside** an allowed area:

```javascript
db.routes.find({
  tenantId: "T100",
  route: {
    $geoWithin: {
      $geometry: allowedArea
    }
  }
});
```

These two queries differ in policy:

- **Touches or passes through a restricted zone** → reject/flag route with `$geoIntersects`.
- **Route must remain entirely within the allowed zone** → use `$geoWithin`.

With sparse GPS points, a straight LineString connecting two points may pass through a zone the vehicle never actually entered. For safety-critical applications, use true road-matched geometry and appropriate buffer rules.

---

## 27. Limitations on Sharded Clusters

In a sharded cluster:

- You can create a `2dsphere` index on a sharded collection.
- A geospatial index **cannot be the shard key**.
- `mongos` routes based on the shard key and chunk placement metadata.
- Queries containing only a geospatial predicate **without a shard key filter** may need to fan out to multiple shards.
- The `2dsphere` index speeds up spatial evaluation **within each shard**; it does not guarantee single-shard targeting.

Example using `tenantId` as shard key (design illustration only):

```javascript
db.places.find({
  tenantId: "T100",
  location: {
    $geoWithin: {
      $geometry: viewport
    }
  }
});
```

The `tenantId` predicate helps the router narrow down shards, while the `2dsphere` index evaluates geometry on the targeted shard.

Never query a single shard directly in place of `mongos` when a cluster-wide answer is needed; you may miss data residing on other shards.

---

## 28. Invalid Geospatial Data or Missing Locations

Some documents have:

```javascript
{ _id: "X1", name: "No location" }
{ _id: "X2", location: null }
{ _id: "X3", location: [] }
```

Under `2dsphere` sparse semantics, these documents have no geospatial index entry. Nor can they be considered to contain valid geometry inside a query region.

If a dashboard needs "how many places have coordinates?" and "how many places have locations unknown?", those are **two separate queries**:

```javascript
// Documents that have the location field:
db.places.countDocuments({
  location: {
    $exists: true
  }
});

// Documents whose location actually matches the region:
db.places.countDocuments({
  location: {
    $geoWithin: {
      $geometry: viewport
    }
  }
});
```

`$exists: true` **does not prove** the field holds valid GeoJSON: it could still be `null` or malformed data. Require `location.type: "Point"` and strict schema validation if your domain enforces the standard.

### 28.1. Do Not Mix Coordinate Conventions

Formats:

```javascript
{ loc: [106.70, 10.78] }                 // legacy pair
{ loc: { type: "Point", coordinates: [106.70, 10.78] } } // GeoJSON
{ lat: 10.78, lon: 106.70 }             // two separate scalars
```

do not share the same behavior or index support. In particular, storing two scalar `lat`/`lon` fields and building a compound B-tree index does not make them a `2dsphere` geometry field.

Choose a clean schema and migrate consistently.

---

## 29. Common Errors and Fixes

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| Query misses points clearly nearby | Swapped longitude/latitude | Verify `[lon,lat]` and validation. |
| Polygon throws an error | Missing array level in `coordinates` | GeoJSON Polygon requires an array of rings. |
| Invalid Polygon | Unclosed ring or self-intersection | Close rings, validate with GIS. |
| `$geoWithin` skips partially overlapping zones | Asking for **full** containment | Use `$geoIntersects` if overlap suffices. |
| `$geoIntersects` returns a large zone enclosing the query | That is still an intersection | Use `$geoWithin` if full containment is needed. |
| Using `$geoWithin` to find zones containing a Point returns nothing | Reversed geometry direction | Query polygon field with `$geoIntersects` and Point. |
| Unexpected results on boundaries | Degenerate geometry | Do not rely on absolute boundary guarantees; add tests/policy. |
| Using `$box` on GeoJSON `2dsphere` expecting spherical math | `$box` is legacy planar | Use `$geometry` Polygon for GeoJSON. |
| `$geoIntersects` does not use a `2d` index | Only `2dsphere` supports the operator | Create a spherical index on the proper field. |
| Slow query | Missing geospatial index or overly broad region | Create `2dsphere`, filter early, inspect explain. |
| Query not sorted nearest-first | Operators do not compute/sort distance | Use `$near`/`$geoNear`. |
| Circle radius vastly wrong | Passing km or meters directly to `$centerSphere` | Convert to radians: km / 6378.1. |
| Large polygon returns inverted/opposite region | Default CRS interprets complement | Consider strict winding CRS for single-ring big polygons. |
| Missing results near antimeridian | Treating longitude as continuous planar XY | Design spherical GeoJSON / split regions. |
| Index exists, but inserts fail | Field has strings or invalid geometry type | Clean/migrate data and validate inputs. |
| Geo index exists, but query hits many shards | Missing shard key filter | Combine shard key and `2dsphere` per access patterns. |
| `$geoIntersects` returns too many zones | Any intersection matches | Add business filters; use GIS if overlap area is needed. |
| Unstable ordering | Missing `sort` | Add explicit sort and pagination. |
| Duplicate/ambiguous matches in overlapping zones | Multiple zones match | Add precedence/priority and tie-breaking policy. |
| Polygon has a hole, yet points in the hole match | Wrong ring nesting or hole omitted | Validate GeoJSON Polygon inner rings. |
| Polar region queries differ from flat map | `2dsphere` is spherical | Do not arbitrarily swap to `2d`. |

---

## 30. Hands-On Exercises with Answers

### Exercise 1 — Choosing the Operator

You have a `stores` collection storing Points and want to find stores inside a district Polygon. What do you use?

**Answer:** `$geoWithin` with `$geometry` Polygon on the Point field. `$geoIntersects` can also match intersecting Points, but `$geoWithin` directly expresses the business rule "points inside a region."

### Exercise 2 — Partially Intersecting Regions

A `deliveryZones` collection stores Polygons; an incident area overlaps 20% of a zone polygon. What do you use?

**Answer:** `$geoIntersects`; `$geoWithin` would skip the zone because it is not completely inside the incident area.

### Exercise 3 — Region Enclosing the Query

Polygon A is larger and encloses all of Polygon Q. Does `$geoWithin` match when the document stores A and the query passes Q?

**Answer:** No; A is not inside Q. `$geoIntersects` matches because A and Q intersect.

### Exercise 4 — Reverse Query

A collection stores delivery-area polygons. The query input is a customer location Point. How do you find which zones contain that Point?

**Answer:** Use `$geoIntersects` on the Polygon field with `$geometry` set to the Point.

### Exercise 5 — Coordinates

An API returns `latitude=10.78`, `longitude=106.70`. What is the valid GeoJSON Point?

**Answer:**

```javascript
{
  type: "Point",
  coordinates: [106.70, 10.78]
}
```

### Exercise 6 — Ring Closure

A Polygon has:

```javascript
coordinates: [
  [[0, 0], [4, 0], [4, 4], [0, 4]]
]
```

What is missing?

**Answer:** Repeat `[0,0]` at the end of the ring to close the polygon.

### Exercise 7 — LineString

A line runs from `[-1,2]` to `[5,2]`, crossing a Polygon from `[0,0]` to `[4,4]`. How do `$geoWithin` and `$geoIntersects` differ?

**Answer:** `$geoWithin` does not match because parts of the line lie outside; `$geoIntersects` matches because the line passes through the interior.

### Exercise 8 — Region with a Hole

Point `[5,5]` lies inside outer ring `[0,0]`–`[10,10]` but inside inner hole `[4,4]`–`[6,6]`. Does it belong to the polygon?

**Answer:** No, it does not belong to the area represented by the polygon if the rings are properly defined in GeoJSON.

### Exercise 9 — `$centerSphere`

To search within a 10 km radius using `$centerSphere`, what radius value do you pass?

**Answer:** Approximately `10 / 6378.1` radians, not `10` or `10000`.

### Exercise 10 — Index

To run `$geoIntersects` efficiently against GeoJSON Polygons, which index should you create?

**Answer:** `{ geometry: "2dsphere" }`. The server can execute without an index, but `2d` does not optimize `$geoIntersects`.

### Exercise 11 — Sharding

You have a `2dsphere` index on `location`, and a query filters only by `location` with no shard key predicate. Is it guaranteed to hit only one shard?

**Answer:** No. The router may need to query multiple shards; the geospatial index operates locally on each targeted shard.

### Exercise 12 — Boundary

A LineString touches a single vertex of a Polygon without entering its interior. Does MongoDB guarantee `$geoIntersects` will match?

**Answer:** No; this is a degenerate case not guaranteed by MongoDB documentation. Use explicit policies/tests or specialized GIS tooling when exact boundary semantics are required.

### Exercise 13 — Big Polygon

A single-ring Polygon covers 75% of the Earth's surface, and the default query returns the remaining 25%. Why?

**Answer:** The default CRS uses complementary geometry behavior for polygons larger than a hemisphere. For large single-ring polygons, use MongoDB's custom strict winding CRS as appropriate.

### Exercise 14 — Sorting Nearest First

A `$geoWithin` query returns 100 points. Are they automatically sorted by distance to the region's center?

**Answer:** No. If you need nearest-first ordering, use `$near`/`$geoNear` with the proper index and units.

### Exercise 15 — Legacy vs. GeoJSON

Does `$box` with `2d` completely replace a GeoJSON Polygon with `2dsphere` for Earth regions?

**Answer:** No. `$box` operates on a planar grid; `$geometry` with `2dsphere` uses spherical geometry.

### Exercise 16 — Full Polygon Containment

A business rule requires an asset to lie **completely inside** a registered zone. Documents store the asset's footprint Polygon.

**Answer:** Use `$geoWithin`. If you used `$geoIntersects`, partially overlapping assets would also match.

### Exercise 17 — Result Size

An API filters by a huge Polygon covering nearly the whole area, with `limit(20)`. Does that guarantee the query is cheap?

**Answer:** No. Index selectivity, additional filters, sort/pagination, geometry intersection work, and resource usage still matter.

### Exercise 18 — Map with Missing Coordinates

A record has no `location`. Should it automatically be treated as lying outside every zone?

**Hint:** In queries it will not match any zone, but business logic needs a distinct "location unknown" state rather than conflating it with "confirmed outside."

---

## 31. Pre-Production Checklist for Geospatial Queries

1. Does the field store a Point, LineString, or Polygon?
2. Do you need **full containment** or **intersection only**?
3. Is coordinate order `[longitude,latitude]`?
4. Is the CRS valid WGS84/EPSG:4326?
5. Does the GeoJSON Polygon have the right ring array nesting, closed rings, and no self-intersections?
6. Are there holes or MultiPolygons that must be preserved?
7. Are there regions larger than a hemisphere, near the antimeridian, or near the poles?
8. Are there explicit rules for Points lying directly on boundaries?
9. Is there a `2dsphere` index on the exact field and data type?
10. Are there wrong-type, `null`, or missing records to clean up?
11. Does the query include tenant/status/category filters to narrow the dataset?
12. Is there a compound index aligned with query shapes?
13. On a sharded cluster, is there a shard key predicate to enable targeting?
14. Have you run `explain("executionStats")` to inspect docs/keys examined?
15. Do you need result sorting, pagination, and limits?
16. Are you querying distance or geometric relationship? Did you pick the right operator?
17. Did `$centerSphere` convert its radius to radians?
18. Do you need overlap percentage or intersection length instead of a boolean match?
19. Have you tested overlapping polygons, holes, and boundary cases?
20. Do you validate user-submitted geometries and cap query complexity?
21. Do MongoDB server/FCV/Java driver docs match your deployment environment?
22. Does the API enforce latency, resource, and request rate limits during map pan/zoom?

Decision flowchart:

```text
MongoDB data has geometry
              |
              v
Document stores Point or Polygon/LineString?
              |
              v
What is the query's goal?
       /            |              \
      v             v               v
Completely     Intersects        Nearest /
within          region           distance
      |             |               |
      v             v               v
 $geoWithin   $geoIntersects     $near /
                                    $geoNear
      \             /
       \           /
        v         v
     Valid GeoJSON?
           |
           v
     2dsphere index
           |
           v
  Filter tenant/status, explain
           |
           v
   Check boundaries and
   business constraints
```

---

## 32. Official MongoDB Documentation

- [`$geoWithin` — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/operator/query/geowithin/): full containment definition, GeoJSON, legacy shapes, indexes, degenerate geometry, and big polygons.
- [`$geoIntersects` — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/operator/query/geointersects/): intersection definition, GeoJSON, indexes, degenerate geometry, and strict winding CRS.
- [`$geometry` — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/operator/query/geometry/): EPSG:4326, GeoJSON structure, and longitude/latitude order.
- [Geospatial Queries](https://www.mongodb.com/docs/manual/geospatial-queries/): comparing spatial operators and coordinate systems.
- [2dsphere Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/): spherical index, sparse behavior, and compound indexes.
- [Geospatial Index Restrictions](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/restrictions/): shard key, supported data types, and covered queries.
- [Query for Locations Bound by a Polygon](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/query/geojson-bound-by-polygon/): Polygon examples and ring closure.
- [`$box`](https://www.mongodb.com/docs/manual/reference/operator/query/box/): legacy planar bounding box.
- [`$polygon`](https://www.mongodb.com/docs/manual/reference/operator/query/polygon/): planar legacy polygon.
- [`$center`](https://www.mongodb.com/docs/manual/reference/operator/query/center/): planar circle.
- [`$centerSphere`](https://www.mongodb.com/docs/manual/reference/operator/query/centersphere/): spherical circle with radius in radians.
- [`$near`](https://www.mongodb.com/docs/manual/reference/operator/query/near/): proximity query sorted by distance.
- [`$geoNear`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/geoNear/): aggregation stage for distance.
- [Java Sync Driver — Search Geospatially](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/geo/): `Filters.geoWithin`, GeoJSON classes, and indexing in Java.
- [MongoDB GeoJSON Objects](https://www.mongodb.com/docs/manual/reference/geojson/): geometry types and storage rules.
- [GeoJSON RFC 7946](https://www.rfc-editor.org/rfc/rfc7946): ring structure, polygons, and GeoJSON requirements.

**Version note:** Index/geospatial behaviors and driver details can vary across MongoDB server, FCV, and Java driver versions. Consult documentation for your exact running version, especially when working with legacy coordinates, big polygons, or map data imported from external GIS systems.

## 33. Conclusion

`$geoWithin` and `$geoIntersects` differ in the spatial relationship they evaluate:

- **`$geoWithin`:** the entire geometry in the document must lie inside the query region. Useful for assets fully within a territory, routes entirely inside an allowed corridor, or finding Points inside a Polygon.
- **`$geoIntersects`:** the document geometry and query geometry only need to overlap. Useful for finding overlapping zones, routes crossing a region, or finding service-area polygons containing a customer Point.

For Earth-based data, store **valid GeoJSON**, use **[longitude, latitude]** coordinates, and create a **`2dsphere`** index when query performance matters. For circular queries using `$centerSphere`, convert distances to **radians**. Always distinguish legacy planar shapes from spherical GeoJSON geometries.

Finally, **edge/vertex touching, polygons with holes, oversized polygons, the antimeridian, and documents without coordinates** can all alter business outcomes. Validate geometries, inspect query plans, add selective filters, and write boundary tests aligned with real requirements.

**`$geoWithin` answers "is it completely inside?", whereas `$geoIntersects` answers "do they overlap?". Understanding the exact question before writing the operator prevents wrong data even when queries run fast.**
