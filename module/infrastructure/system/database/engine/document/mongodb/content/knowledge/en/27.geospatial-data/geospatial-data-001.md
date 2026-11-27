# GeoJSON, Longitude/Latitude Order, and Coordinate Models in MongoDB

Mapping, delivery, travel, logistics, and location-search applications often need to store a position, route, or geographic region in a database. MongoDB supports this data through **GeoJSON**, **2dsphere indexes**, and operators such as **$near**, **$geoWithin**, **$geoIntersects**, and **$geoNear**.

A very common mistake is **swapping longitude and latitude**. Many geolocation APIs return latitude before longitude, but a **GeoJSON position is always [longitude, latitude]**. If the axes are swapped, a point can appear in a completely different location or be rejected due to invalid coordinates. Another mistake is taking x/y values from a projected system in meters and storing them as if they were WGS84 degrees.

This lesson clarifies:

1. The GeoJSON structure of Point, LineString, Polygon, MultiPoint, MultiLineString, and MultiPolygon.
2. The **[longitude, latitude]** rule, valid ranges, WGS84, and differences between GeoJSON and other formats/coordinate systems.
3. Line and region semantics on the Earth's surface, polygon rings, holes, the antimeridian, and elevation.
4. How to store GeoJSON in MongoDB, create a 2dsphere index, and execute geospatial queries.
5. How to write Java Sync Driver code, ingest CSV/API/GIS data, validate, and migrate legacy data.
6. Common pitfalls, hands-on exercises, and a checklist for projects.

## 1. Coordinates Are Not Just Two Numbers

The pair [106.70098, 10.77689] only has meaning when you know which coordinate system the two values belong to and in what order they appear.

| Model | Example | Unit/Semantics |
| --- | --- | --- |
| GeoJSON WGS84 | [106.70098, 10.77689] | Longitude/latitude, unit in degrees |
| Location API | {lat:10.77689,lng:106.70098} | Named latitude and longitude fields |
| Web Mercator | [11880000,1200000] | Projected x/y in meters |
| Canvas | [300,180] | Pixels or UI coordinates |
| Local grid | [12,7] | Grid cell or internal coordinates |
| Address | "Ho Chi Minh City" | Text requiring geocoding |

You cannot take a pair of numbers from a canvas, EPSG:3857, or a warehouse grid and assume it works as GeoJSON WGS84. MongoDB does not infer the reference system from variable names.

### 1.1. Required Source Metadata

- **CRS/datum:** Which coordinate reference system is the location referenced in?
- **Axis order:** Longitude first or latitude first?
- **Units:** Degrees, radians, meters, feet, or custom units?
- **Accuracy:** GPS data, user-placed pin, or geocoding system?
- **Timestamp:** When was the point recorded?
- **Geometry semantics:** A position, a line, or a closed region?

### 1.2. Starting Point for Every Pipeline

A geospatial data ingestion pipeline should do the following:

~~~text
Source
  |
  v
Identify CRS + axis order + units
  |
  v
Transform to WGS84 longitude/latitude
  |
  v
Build GeoJSON geometry
  |
  v
Validate + store + geospatial index
  |
  v
Query / render / analyze
~~~

Do not skip the first step and then try to fix errors by swapping the two numbers when an issue shows up.

## 2. What Is GeoJSON?

GeoJSON is a standard JSON format for describing geometries and geographically located objects. The two main structural groups are **geometry objects** and **Feature objects**.

A Point geometry:

~~~json
{
  "type": "Point",
  "coordinates": [106.70098, 10.77689]
}
~~~

A Feature:

~~~json
{
  "type": "Feature",
  "geometry": {
    "type": "Point",
    "coordinates": [106.70098, 10.77689]
  },
  "properties": {
    "name": "Sample Place",
    "category": "cafe"
  }
}
~~~

### 2.1. Differences Between Geometry and Feature

- **Geometry**: The actual geometry, consisting of `type` and `coordinates` or `geometries`.
- **Feature**: An object with `geometry` and `properties`.
- **FeatureCollection**: A list of Features.

In MongoDB, applications typically store the geometry in a field such as **location**, while business attributes are stored at the top level for easier indexing and querying:

~~~javascript
{
  _id: "P-001",
  name: "Sample Shop",
  category: "cafe",
  active: true,
  location: {
    type: "Point",
    coordinates: [106.70098, 10.77689]
  }
}
~~~

This structure differs from stuffing an entire FeatureCollection into a single document. If each Feature represents an independent place, you should generally create a separate MongoDB document for each Feature.

### 2.2. Common GeoJSON Geometries

| Type | Meaning |
| --- | --- |
| Point | A single position |
| MultiPoint | A set of points |
| LineString | A line connecting positions in order |
| MultiLineString | Multiple lines |
| Polygon | A closed region that may contain holes |
| MultiPolygon | Multiple polygon regions |
| GeometryCollection | A set of geometries of mixed types |

Not every MongoDB geospatial operator accepts every geometry type with the same semantics. For example, proximity queries typically take a **Point** as the query center.

## 3. GeoJSON Coordinate Order: [longitude, latitude]

A two-dimensional position in GeoJSON has the order:

~~~text
[longitude, latitude]
[east-west, north-south]
~~~

Example:

~~~javascript
const longitude = 106.70098;
const latitude = 10.77689;

const point = {
  type: "Point",
  coordinates: [longitude, latitude]
};
~~~

### 3.1. Longitude

Longitude represents the East–West direction relative to the prime meridian.

- Typical range: **-180° to +180°**.
- **Positive** values: East.
- **Negative** values: West.
- 0°: Prime meridian.

~~~text
106.70  -> approximately 106.70° East
-122.40 -> approximately 122.40° West
0       -> prime meridian
~~~

### 3.2. Latitude

Latitude represents the North–South direction relative to the equator.

- Valid range: **-90° to +90°**.
- **Positive** values: North.
- **Negative** values: South.
- 0°: Equator.

~~~text
10.77  -> approximately 10.77° North
-33.86 -> approximately 33.86° South
0      -> equator
~~~

### 3.3. Reference Table

| Component | Other Names | Position in GeoJSON | Valid Range |
| --- | --- | --- | --- |
| longitude | lon, lng | coordinates[0] | [-180, 180] |
| latitude | lat | coordinates[1] | [-90, 90] |

Name variables **longitude** and **latitude** or **lon** and **lat**, rather than just **x** and **y** if doing so makes the team prone to confusion.

## 4. Why Do APIs and UIs Often Reverse the Order?

Many applications and services return:

~~~json
{
  "lat": 10.77689,
  "lng": 106.70098
}
~~~

However, GeoJSON must be:

~~~javascript
{
  type: "Point",
  coordinates: [106.70098, 10.77689]
}
~~~

Correct conversion code:

~~~javascript
const source = {
  lat: 10.77689,
  lng: 106.70098
};

const location = {
  type: "Point",
  coordinates: [
    source.lng,
    source.lat
  ]
};
~~~

### 4.1. Axis-Swap Errors Can Be Obvious

Incorrect:

~~~javascript
{
  type: "Point",
  coordinates: [10.77689, 106.70098]
}
~~~

The second element is interpreted as **latitude = 106.70098°**, exceeding the +90° limit, so MongoDB may reject it during geospatial indexing or querying.

### 4.2. Axis-Swap Errors Can Also Be Silent

Consider a point with longitude 2.35° and latitude 48.86°:

~~~javascript
[2.35, 48.86]  // lon = 2.35; lat = 48.86
[48.86, 2.35]  // lon = 48.86; lat = 2.35
~~~

Both fall within valid numeric ranges, yet they represent **two different locations**. Therefore, range checking alone is not enough to prove the axis order is correct.

### 4.3. Do Not Blindly Swap When Data "Looks Wrong"

If a source sends lat = 106.7 and lng = 10.77, it could be a swapped-field bug, or it could be the wrong CRS or a mapping error. Before fixing it, verify the source contract and inspect samples—do not automatically swap every record.

## 5. WGS84 and Coordinate Systems

**WGS84** is the geographic reference system widely used in GPS and location data. Modern GeoJSON per RFC 7946 uses geographic coordinates based on WGS84, with positions ordered **longitude first, latitude second**.

### 5.1. What Is a CRS?

A **Coordinate Reference System (CRS)** defines how coordinate numbers map to locations. It involves the datum, axes, units, and potentially a map projection.

Two locations with the same x/y numbers under different CRSs can point to completely different places.

### 5.2. EPSG:4326 and Axis Order

EPSG:4326 is commonly used to denote the WGS84 geographic CRS. However, in some GIS definitions or applications, the formal axis order may be presented as latitude, longitude.

**GeoJSON RFC 7946 still specifies positions as longitude, latitude**, close to the axis order of CRS84. Therefore, do not just read the EPSG:4326 label and assume every library outputs [lon,lat].

An ingestion pipeline from GIS must confirm:

~~~text
Source states WGS84 / EPSG:4326
  -> does the library output lat/lon or lon/lat?
  -> normalize to GeoJSON [lon,lat]
~~~

### 5.3. EPSG:3857 Web Mercator

A mapping source may return planar x/y coordinates in meters:

~~~javascript
{
  x: 11880000,
  y: 1200000,
  crs: "EPSG:3857"
}
~~~

Do not treat:

~~~javascript
[11880000, 1200000]
~~~

as longitude and latitude in degrees. You must apply a proper CRS transformation using a GIS library or a trusted conversion service.

### 5.4. Swapping Axes Is Not CRS Transformation

Converting:

~~~text
[x, y] -> [y, x]
~~~

only changes the order. It does not turn Web Mercator meter values into WGS84 degrees.

## 6. Degrees Are Not Meters

GeoJSON coordinates such as:

~~~javascript
[106.70098, 10.77689]
~~~

are **longitude/latitude in degrees**. However, the radius parameter of several MongoDB operators uses **meters**.

Do not compute distance using:

~~~text
sqrt((lon2-lon1)^2 + (lat2-lat1)^2)
~~~

and treat the result as meters. That calculation produces degrees and ignores the curvature of the Earth.

### 6.1. One Degree of Longitude Does Not Equal the Same Number of Meters Everywhere

Meridians converge at the poles. Therefore, a difference of 0.01° in longitude near the equator versus near the poles corresponds to different ground distances.

### 6.2. Geographic Distance Differs from Road Distance

When using 2dsphere, $near or $geoNear returns results based on a geographic distance model; it does not automatically calculate driving routes, bridges, one-way streets, or traffic delays.

If ETA is required, you must use an appropriate routing engine and road network.

## 7. GeoJSON Point

A Point consists of exactly one position:

~~~json
{
  "type": "Point",
  "coordinates": [106.70098, 10.77689]
}
~~~

Use cases:

- Store location.
- Pickup point.
- A GPS station.
- Delivery point.
- Sensor or monitoring station.

MongoDB document:

~~~javascript
db.places.insertOne({
  _id: "P-001",
  name: "Sample Place",
  location: {
    type: "Point",
    coordinates: [106.70098, 10.77689]
  }
});
~~~

### 7.1. GeoJSON Point vs. Legacy Coordinate Pair

Legacy pair:

~~~javascript
{
  location: [106.70098, 10.77689]
}
~~~

GeoJSON geometry:

~~~javascript
{
  location: {
    type: "Point",
    coordinates: [106.70098, 10.77689]
  }
}
~~~

MongoDB supports some geospatial operations on legacy coordinate pairs, but you should not conflate the two schemas or apply geometry-type rules to a raw numeric array.

## 8. GeoJSON LineString

A LineString represents a sequence of connected points:

~~~json
{
  "type": "LineString",
  "coordinates": [
    [106.7000, 10.7700],
    [106.7050, 10.7750],
    [106.7100, 10.7800]
  ]
}
~~~

Each position in the list **is still [lon,lat]**.

### 8.1. At Least Two Positions

A LineString requires at least two positions to represent a segment:

~~~javascript
{
  type: "LineString",
  coordinates: [
    [106.70, 10.77],
    [106.71, 10.78]
  ]
}
~~~

### 8.2. Not Equivalent to an Actual Travel Route

Putting two GPS points into a LineString does not make MongoDB find the road route between them. It only describes geometry built from the given positions.

If you need to analyze where a vehicle traveled, you must consider GPS sampling frequency, measurement noise, and road network data.

## 9. GeoJSON Polygon

A Polygon is a region described by **one or more closed linear rings**.

~~~json
{
  "type": "Polygon",
  "coordinates": [
    [
      [106.69, 10.76],
      [106.71, 10.76],
      [106.71, 10.78],
      [106.69, 10.78],
      [106.69, 10.76]
    ]
  ]
}
~~~

Structure:

~~~text
Polygon
  coordinates
    -> list of rings
      -> one ring
        -> list of positions
          -> [longitude, latitude]
~~~

### 9.1. Why Is There an Extra Array Level?

A Polygon can contain an outer ring and multiple inner rings. Therefore, **coordinates** contains an array of rings, even when the polygon has no holes.

### 9.2. Rings Must Be Closed

The first and last positions of a ring must be equal:

~~~javascript
[
  [106.69, 10.76],
  [106.71, 10.76],
  [106.71, 10.78],
  [106.69, 10.78],
  [106.69, 10.76]
]
~~~

If you omit the final position, the ring is not explicitly closed according to the standard.

### 9.3. Minimum Four Positions

Three distinct vertices plus the repeated starting point at the end form the minimum triangular ring:

~~~javascript
[
  [106.70, 10.77],
  [106.72, 10.77],
  [106.71, 10.79],
  [106.70, 10.77]
]
~~~

Do not duplicate vertices just to meet the count without forming a valid area.

## 10. Polygon with Holes

A Polygon can contain an outer ring and an inner ring:

~~~javascript
{
  type: "Polygon",
  coordinates: [
    [
      [106.68, 10.75],
      [106.73, 10.75],
      [106.73, 10.80],
      [106.68, 10.80],
      [106.68, 10.75]
    ],
    [
      [106.695, 10.765],
      [106.695, 10.780],
      [106.710, 10.780],
      [106.710, 10.765],
      [106.695, 10.765]
    ]
  ]
}
~~~

The inner ring typically represents an area excluded from the outer polygon.

### 10.1. Ring Winding Order

GeoJSON RFC 7946 specifies a ring orientation rule commonly called the **right-hand rule**: outer rings are counterclockwise and inner rings are clockwise when viewed on the corresponding planar map projection.

When MongoDB interprets polygons on a sphere—especially very large regions—additional winding rules and region representations can matter.

### 10.2. Holes Must Fit Within the Outer Ring

Do not place a hole completely outside the outer ring or allow rings to self-intersect arbitrarily. Invalid polygon data can be rejected by indexes/queries or produce unintended results.

### 10.3. Self-Intersection

If a ring forms a "bowtie" shape with crossing edges, it is not a reliable simple polygon. You need to normalize the topology using an appropriate GIS tool, not merely check that arrays have enough elements.

## 11. MultiPoint

A MultiPoint is a collection of points:

~~~json
{
  "type": "MultiPoint",
  "coordinates": [
    [106.700, 10.770],
    [106.710, 10.780],
    [106.720, 10.790]
  ]
}
~~~

It does not connect the points into a line like a LineString.

If each point is a branch with its own ID, opening hours, and status, **one MongoDB Point document per branch** is usually easier to manage than a very large MultiPoint.

## 12. MultiLineString

A MultiLineString contains multiple independent line segments:

~~~json
{
  "type": "MultiLineString",
  "coordinates": [
    [
      [106.700, 10.770],
      [106.705, 10.775]
    ],
    [
      [106.710, 10.780],
      [106.715, 10.785],
      [106.720, 10.790]
    ]
  ]
}
~~~

It can represent disconnected route segments without adding imaginary connecting lines between them.

## 13. MultiPolygon

A MultiPolygon contains multiple Polygons:

~~~json
{
  "type": "MultiPolygon",
  "coordinates": [
    [
      [
        [106.68, 10.75],
        [106.70, 10.75],
        [106.70, 10.77],
        [106.68, 10.77],
        [106.68, 10.75]
      ]
    ],
    [
      [
        [106.72, 10.78],
        [106.74, 10.78],
        [106.74, 10.80],
        [106.72, 10.80],
        [106.72, 10.78]
      ]
    ]
  ]
}
~~~

Structure:

~~~text
MultiPolygon
  -> list of polygons
     -> list of rings of each polygon
        -> list of positions
           -> [longitude, latitude]
~~~

A delivery zone with two non-contiguous areas can use a MultiPolygon. You should not connect two disjoint areas with fake bridge segments to force them into a single Polygon.

## 14. GeometryCollection and FeatureCollection

A GeometryCollection contains multiple geometries, potentially of different types:

~~~json
{
  "type": "GeometryCollection",
  "geometries": [
    {
      "type": "Point",
      "coordinates": [106.70, 10.77]
    },
    {
      "type": "LineString",
      "coordinates": [
        [106.70, 10.77],
        [106.72, 10.79]
      ]
    }
  ]
}
~~~

The field inside a GeometryCollection is **geometries**, not root-level coordinates.

A FeatureCollection contains multiple Features:

~~~json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [106.70, 10.77]
      },
      "properties": {
        "name": "Place A"
      }
    }
  ]
}
~~~

In MongoDB, if you need to search individual Features by location, you should generally import each Feature as a separate document with a consistent geometry field.

## 15. Elevation: The Third Element

GeoJSON can represent a position with a third element, usually interpreted as elevation/altitude depending on context:

~~~json
{
  "type": "Point",
  "coordinates": [106.70098, 10.77689, 15]
}
~~~

However, standard MongoDB geospatial indexes and operators focus on geometry on the Earth's surface, **not 3D distance accounting for altitude**.

### 15.1. A Clearer Model

~~~javascript
{
  location: {
    type: "Point",
    coordinates: [106.70098, 10.77689]
  },
  elevationMeters: 15,
  elevationReference: "SOURCE_SPECIFIC"
}
~~~

This prevents mistakenly assuming a 2dsphere query factors in elevation differences.

### 15.2. Vertical Datum

Height above an ellipsoid, height above sea level, and floor number in a building are different things. A bare number `15` is not enough to infer true height without a vertical datum and unit.

## 16. Range and Data Type Validation

For a two-dimensional WGS84 position:

\[
-180 \leq \text{longitude} \leq 180
\]

\[
-90 \leq \text{latitude} \leq 90
\]

Invalid examples:

~~~javascript
[106.70, 110]              // latitude exceeds 90
[250, 10.77]               // longitude exceeds 180
["106.70", "10.77"]         // string, not number
[106.70]                   // missing latitude
[106.70, null]             // missing/null
[Infinity, 10.77]          // not finite
~~~

### 16.1. JavaScript Validation Function

~~~javascript
function makeGeoPoint(longitude, latitude) {
  if (
    !Number.isFinite(longitude) ||
    !Number.isFinite(latitude)
  ) {
    throw new Error("Coordinates must be finite numbers");
  }

  if (longitude < -180 || longitude > 180) {
    throw new Error("Longitude out of [-180,180]");
  }

  if (latitude < -90 || latitude > 90) {
    throw new Error("Latitude out of [-90,90]");
  }

  return {
    type: "Point",
    coordinates: [longitude, latitude]
  };
}
~~~

### 16.2. Validation Does Not Automatically Catch All Axis Swaps

Both [2.35,48.86] and [48.86,2.35] are valid by range. You must check **the source contract, expected region, and reference data samples**.

### 16.3. Avoid Using parseFloat Blindly

JavaScript's `parseFloat` can extract a leading numeric prefix from a string containing other characters. For location data, parse strictly and reject invalid records.

## 17. The 180° Meridian (Antimeridian)

Two points with longitudes:

~~~text
179.8°
-179.8°
~~~

can be very close on Earth, even though their arithmetic difference is 359.6°.

### 17.1. Pitfall with a Flat X-Axis

If code draws a segment from 179.8 to -179.8 like ordinary x/y coordinates, the line may stretch across the entire map instead of crossing the ±180° meridian.

### 17.2. GeoJSON Crossing the Antimeridian

RFC 7946 recommends handling/splitting geometries that cross the antimeridian to avoid unintended interpretations. For a polygon crossing this line, you may need to represent it as a **MultiPolygon** with parts on both sides.

Do not try to fix it simply by wrapping longitude and assuming the polygon/topology is guaranteed to be valid.

### 17.3. Regions Near the Poles

Near ±90° latitude, meridians converge sharply. Euclidean distance in degrees and naive bounding boxes become even less reliable.

Use appropriate geospatial operators and test boundary cases.

## 18. Very Large Polygons and Strict-Winding

On a sphere, a closed ring divides the surface into two regions. For very large polygons, the interpretation of the "interior" can depend on ring winding order and MongoDB rules.

MongoDB has a special CRS mechanism for certain large polygons, commonly referred to as **strict-winding CRS**:

~~~javascript
{
  type: "Polygon",
  coordinates: [
    [
      [-170, -10],
      [-170, 10],
      [170, 10],
      [170, -10],
      [-170, -10]
    ]
  ],
  crs: {
    type: "name",
    properties: {
      name: "urn:x-mongodb:crs:strictwinding:EPSG:4326"
    }
  }
}
~~~

**This is a MongoDB-specific convention, not a license to attach arbitrary CRSs to standard RFC 7946 GeoJSON.** Before using it, check the exact operator, version, and winding requirements.

For small polygons representing a store or a district, valid WGS84 GeoJSON is usually sufficient—do not use strict-winding without a reason.

## 19. 2dsphere Index in MongoDB

For spherical geospatial queries, you typically use a **2dsphere index**:

~~~javascript
db.places.createIndex({
  location: "2dsphere"
});
~~~

Sample data:

~~~javascript
use geo_lab

db.places.insertMany([
  {
    _id: "P-001",
    name: "Store A",
    category: "shop",
    location: {
      type: "Point",
      coordinates: [106.70098, 10.77689]
    }
  },
  {
    _id: "P-002",
    name: "Store B",
    category: "shop",
    location: {
      type: "Point",
      coordinates: [106.70900, 10.78400]
    }
  },
  {
    _id: "P-003",
    name: "Warehouse C",
    category: "warehouse",
    location: {
      type: "Point",
      coordinates: [106.72500, 10.79500]
    }
  }
]);

db.places.createIndex({
  location: "2dsphere"
});
~~~

### 19.1. Differences Between 2dsphere and 2d

| Index | Primary Model | Typical Data |
| --- | --- | --- |
| **2dsphere** | Spherical/WGS84 | GeoJSON and supported forms |
| **2d** | Planar/legacy model | Legacy coordinate pairs |

Do not use `2d` just because the geometry has two numbers. To query locations on Earth using GeoJSON, `2dsphere` is generally more appropriate.

### 19.2. 2dsphere Does Not Fix Bad Data

If a document contains latitude = 105°, creating a geospatial index can fail with an error. Validate data before indexing large collections.

### 19.3. The Indexed Field Must Be Exact

If the geometry is stored in **location**, creating an index on **area** will not help queries on `location`. Likewise, a Feature object containing geometry under a `geometry` field needs the exact index and query path.

### 19.4. Missing Location

MongoDB 2dsphere indexes have their own sparse behavior. A document without a location may not have a corresponding index entry. If business rules require coordinates, enforce them with schema validation rather than relying solely on the index.

## 20. $near: Nearest Points

Example querying places near a Point, up to 5,000 meters:

~~~javascript
db.places.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      $maxDistance: 5000
    }
  }
});
~~~

With a GeoJSON Point and a 2dsphere index, **$maxDistance** in this context is in **meters**.

### 20.1. Do Not Confuse Degrees and Meters

~~~text
Point coordinates = [106.70098°, 10.77689°]
$maxDistance      = 5000 meters
~~~

If a user enters a 5 km radius, the application must convert it to 5,000 meters. Do not pass `5` thinking it means 5 km.

### 20.2. Using $minDistance

~~~javascript
db.places.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      $minDistance: 500,
      $maxDistance: 5000
    }
  }
});
~~~

This example finds places at least 500 m and at most 5,000 m from the center according to the operator's semantics.

### 20.3. $near Returns Results Ordered by Distance

`$near` executes a query ordered from nearest to farthest. If you only need the set of points inside a region and do not need distance ordering, `$geoWithin` may be appropriate.

## 21. $geoNear: Returning Distance as Well

The `$geoNear` aggregation stage is suitable when you want the results to include a distance field:

~~~javascript
db.places.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      distanceField: "distanceMeters",
      maxDistance: 5000,
      spherical: true,
      key: "location"
    }
  },
  {
    $project: {
      name: 1,
      category: 1,
      location: 1,
      distanceMeters: 1
    }
  }
]);
~~~

### 21.1. $geoNear Must Be First in the Pipeline

In aggregation, `$geoNear` is required to be the first stage in the pipeline per MongoDB's supported semantics. Do not arbitrarily put `$match` before it and expect it to behave like a regular `find`.

You can use `$geoNear`'s built-in filter options and subsequent stages to apply business conditions as supported.

### 21.2. Using key When Multiple Geo Indexes Exist

The **key: "location"** option specifies the geospatial field in situations where multiple matching indexes exist.

### 21.3. Distance Is Not Yet a Route

`distanceMeters` represents geographic distance under the model used; it does not automatically find road routes or ETA.

## 22. $geoWithin: Inside a Polygon

Example delivery-area Polygon:

~~~javascript
const deliveryArea = {
  type: "Polygon",
  coordinates: [
    [
      [106.68, 10.76],
      [106.72, 10.76],
      [106.72, 10.80],
      [106.68, 10.80],
      [106.68, 10.76]
    ]
  ]
};

db.places.find({
  location: {
    $geoWithin: {
      $geometry: deliveryArea
    }
  }
});
~~~

### 22.1. $geoWithin Does Not Sort by Distance

This operator checks containment within a region and does not guarantee returning the nearest point first.

### 22.2. Regions with Holes

If a Polygon has a hole, points inside the hole can be excluded from the region according to geometry semantics. Ensure the outer and inner rings are valid.

### 22.3. Points on the Boundary

For points lying directly on the boundary, verify the semantics on your actual MongoDB version and dataset. If business logic requires determining whether "on the boundary counts as inside or outside," establish a clear rule and numerical tests.

## 23. $geoIntersects: Intersecting Geometries

If a collection stores service-area Polygons:

~~~javascript
db.serviceAreas.createIndex({
  area: "2dsphere"
});
~~~

Find areas intersecting a Polygon:

~~~javascript
db.serviceAreas.find({
  area: {
    $geoIntersects: {
      $geometry: {
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
      }
    }
  }
});
~~~

### 23.1. Intersection Differs from Full Containment

Two Polygons that only partially overlap can still satisfy the intersection condition, even if neither polygon completely contains the other.

### 23.2. Querying Regions Containing a Point

You can query which service areas intersect with a customer Point:

~~~javascript
db.serviceAreas.find({
  area: {
    $geoIntersects: {
      $geometry: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      }
    }
  }
});
~~~

If multiple overlapping regions match, the application needs a rule to pick a store rather than relying solely on the returned list of matching areas.

## 24. $centerSphere Uses Radians

Another style of circular region query:

~~~javascript
db.places.find({
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.70098, 10.77689],
        0.001
      ]
    }
  }
});
~~~

The radius in **$centerSphere** is in **radians**, not meters.

| Query | Distance/Radius Unit |
| --- | --- |
| $near with GeoJSON + 2dsphere | Meters |
| $geoNear with GeoJSON + spherical | Meters per corresponding semantics |
| $geoWithin + $centerSphere | Radians |

If you need a radius of R meters, the angular radius is approximately **R / Earth radius** when using an appropriate spherical model. Do not pass raw meters as the radian parameter.

## 25. Designing a POI Collection

A point of interest (POI) usually uses a Point:

~~~javascript
{
  _id: "STORE-001",
  tenantId: "T-A",
  name: "Store A",
  category: "grocery",
  active: true,
  location: {
    type: "Point",
    coordinates: [106.70098, 10.77689]
  },
  updatedAt: new Date(),
  locationSource: "gps",
  accuracyMeters: 25
}
~~~

### 25.1. Useful Metadata

- **locationSource**: GPS, geocoded address, user-placed pin.
- **accuracyMeters**: Estimated error margin, when available.
- **updatedAt**: When the location was updated.
- **active**: Whether it is still in service.
- **tenantId**: Owning tenant.
- **category**: Place category.

### 25.2. Compound Indexes

A query that frequently filters `active` + proximity to `location` may warrant considering an index:

~~~javascript
db.places.createIndex({
  active: 1,
  location: "2dsphere"
});
~~~

Effectiveness depends on workload, field order, MongoDB version, and the query plan. Do not assume a compound geo index is always better than every alternative.

### 25.3. Multiple Branches

A store chain with 500 branches should consider **500 Point documents** if each branch has independent operating hours, inventory, and status, instead of one giant MultiPoint.

## 26. GPS Tracking and LineString

A sample route:

~~~javascript
{
  _id: "ROUTE-001",
  path: {
    type: "LineString",
    coordinates: [
      [106.7000, 10.7700],
      [106.7050, 10.7750],
      [106.7100, 10.7800]
    ]
  }
}
~~~

If you need timestamps for each GPS sample, you can store separate records:

~~~javascript
{
  vehicleId: "V-01",
  recordedAt: ISODate("2026-11-14T03:00:00Z"),
  location: {
    type: "Point",
    coordinates: [106.7000, 10.7700]
  },
  speedKmh: 28
}
~~~

### 26.1. Do Not Accumulate Unboundedly in One Document

MongoDB documents have a size limit. GPS sample sets should not grow unboundedly inside a single array or MultiPoint if the application needs long-term history.

### 26.2. Filtering by Time and Location

Consider indexes for `vehicleId`, `recordedAt`, and a separate geospatial index when location queries are needed. Do not rely on a single geo index while ignoring other query patterns.

## 27. Schema Validation

You can use JSON Schema to enforce a Point consisting of two numeric values:

~~~javascript
db.createCollection("validatedPlaces", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["name", "location"],
      properties: {
        name: { bsonType: "string" },
        location: {
          bsonType: "object",
          required: ["type", "coordinates"],
          properties: {
            type: { enum: ["Point"] },
            coordinates: {
              bsonType: "array",
              minItems: 2,
              maxItems: 2,
              items: {
                bsonType: [
                  "double",
                  "int",
                  "long",
                  "decimal"
                ]
              }
            }
          }
        }
      }
    }
  }
});
~~~

This validator checks basic shape, but does not prove that:

- Longitude/latitude fall within specific ranges.
- The axis order from the source is correct.
- The place lies within the expected business region.
- Polygons do not self-intersect.
- Longitude/latitude were properly transformed from the source CRS.

Additional validation is needed in the application, ingestion pipeline, or GIS tooling.

## 28. Ingesting Data from APIs and CSV

An API often returns:

~~~json
{
  "latitude": 10.77689,
  "longitude": 106.70098,
  "accuracy": 12
}
~~~

Convert it:

~~~javascript
const location = makeGeoPoint(
  apiResponse.longitude,
  apiResponse.latitude
);
~~~

CSV with `lat,lng` columns:

~~~csv
id,lat,lng
P-001,10.77689,106.70098
P-002,10.78400,106.70900
~~~

Build GeoJSON:

~~~javascript
const location = {
  type: "Point",
  coordinates: [
    Number(row.lng),
    Number(row.lat)
  ]
};
~~~

### 28.1. Do Not Use CSV Column Order as GeoJSON Order

A CSV having `lat` before `lng` does not change the GeoJSON standard. Mapping must be explicit.

### 28.2. Ingesting from GIS

Shapefiles, GeoPackages, WKT, or other geospatial services may use different CRSs.

Workflow:

~~~text
Read source geometry
  -> inspect source CRS and axis order
  -> transform to WGS84 longitude/latitude
  -> create GeoJSON geometry
  -> validate coordinate ranges and topology
  -> import MongoDB
  -> build index
  -> verify sample positions and queries
~~~

### 28.3. Some Points Are Still Wrong Despite Being Numerically Valid

Checking on a map or cross-referencing against an operational-area polygon can reveal swapped lat/lon points that range validation misses.

## 29. Migrating Legacy Schemas to GeoJSON

Legacy data:

~~~javascript
{
  _id: "P-OLD-001",
  lat: 10.77689,
  lng: 106.70098
}
~~~

New schema:

~~~javascript
{
  _id: "P-OLD-001",
  location: {
    type: "Point",
    coordinates: [106.70098, 10.77689]
  }
}
~~~

For legacy sources confirmed to be WGS84 with valid numeric fields, you can test an update pipeline in a staging environment:

~~~javascript
db.places.updateMany(
  {
    lat: { $type: "number" },
    lng: { $type: "number" }
  },
  [
    {
      $set: {
        location: {
          type: "Point",
          coordinates: ["$lng", "$lat"]
        }
      }
    }
  ]
);
~~~

**This is for illustration only**; it does not replace range checks, backups, data classification, and result verification. Do not run this batch directly on a production collection without testing.

### 29.1. Migration Steps

1. Inventory sources and schemas.
2. Identify the exact CRS and axis order of each source.
3. Classify nulls, strings, out-of-range values, and duplicates.
4. Transform to WGS84 lon/lat.
5. Populate the new GeoJSON field.
6. Cross-check sample coordinates and operational regions.
7. Build the 2dsphere index.
8. Test `$near`/`$geoWithin`.
9. Switch applications to the new schema.
10. Remove legacy fields after all consumers have switched.

### 29.2. Mixed Correct/Incorrect Data

If some records already store `[lon,lat]` while others store `[lat,lon]`, **do not swap everything**. Identify the source/version and only fix the subset with evidence of being swapped.

## 30. Java Sync Driver: Creating a Point

The Java Sync Driver provides GeoJSON classes such as **Point** and **Position**:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.geojson.Point;
import com.mongodb.client.model.geojson.Position;
import org.bson.Document;

public class InsertPointExample {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing MONGODB_URI"
            );
        }

        double longitude = 106.70098;
        double latitude = 10.77689;

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database =
                    client.getDatabase("geo_lab");

            MongoCollection<Document> places =
                    database.getCollection("places");

            Point point = new Point(
                    new Position(longitude, latitude)
            );

            Document place = new Document("_id", "JAVA-P-001")
                    .append("name", "Java Point")
                    .append("location", point);

            places.insertOne(place);
        }
    }
}
~~~

The order matters:

~~~java
new Position(longitude, latitude)
~~~

Do not create `Position(latitude, longitude)` out of API display habit.

### 30.1. Creating an Explicit BSON Document

If you do not need dedicated GeoJSON classes:

~~~java
Document location = new Document("type", "Point")
        .append(
                "coordinates",
                java.util.Arrays.asList(
                        longitude,
                        latitude
                )
        );
~~~

Use a codec/driver version appropriate for how BSON is encoded.

## 31. Java Sync Driver: 2dsphere Index

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

// places is MongoCollection<Document>.

String indexName = places.createIndex(
        Indexes.geo2dsphere("location")
);

System.out.println(indexName);
~~~

Only build the index after normalizing records that have a `location`. If the collection contains invalid geometries, the index build may fail.

## 32. Java Sync Driver: $near Query

You can build an explicit BSON filter:

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import java.util.Arrays;

// places is MongoCollection<Document>.

double longitude = 106.70098;
double latitude = 10.77689;

Document point = new Document("type", "Point")
        .append(
                "coordinates",
                Arrays.asList(
                        longitude,
                        latitude
                )
        );

Document near = new Document("$geometry", point)
        .append("$maxDistance", 5000);

Document filter = new Document(
        "location",
        new Document("$near", near)
);

places.find(filter).forEach(
        row -> System.out.println(row.toJson())
);
~~~

In this example, `5000` corresponds to **5,000 meters** under GeoJSON 2dsphere near query semantics.

### 32.1. Why Use Document?

It shows the MongoDB query structure directly, reducing dependency on `Filters` overloads across driver versions. Applications can also use the Java Driver's geospatial helpers where appropriate.

## 33. Java Sync Driver: $geoWithin Query

~~~java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.Arrays;
import java.util.List;

// places is MongoCollection<Document>.

List<List<Double>> ring = Arrays.asList(
        Arrays.asList(106.68, 10.76),
        Arrays.asList(106.72, 10.76),
        Arrays.asList(106.72, 10.80),
        Arrays.asList(106.68, 10.80),
        Arrays.asList(106.68, 10.76)
);

Document polygon = new Document("type", "Polygon")
        .append(
                "coordinates",
                Arrays.asList(ring)
        );

Document filter = new Document(
        "location",
        new Document(
                "$geoWithin",
                new Document("$geometry", polygon)
        )
);

places.find(filter).forEach(
        row -> System.out.println(row.toJson())
);
~~~

Nesting:

~~~text
Polygon.coordinates
  = List<Ring>

Ring
  = List<Position>

Position
  = List<Double> [longitude, latitude]
~~~

Missing one array level will result in a structure that is not a valid Polygon.

## 34. Java Helper to Validate a Point

~~~java
import java.util.Arrays;
import org.bson.Document;

public final class GeoJsonFactory {

    private GeoJsonFactory() {}

    public static Document point(
            double longitude,
            double latitude
    ) {
        if (!Double.isFinite(longitude) ||
                !Double.isFinite(latitude)) {
            throw new IllegalArgumentException(
                    "Coordinates must be finite"
            );
        }

        if (longitude < -180 || longitude > 180) {
            throw new IllegalArgumentException(
                    "Longitude out of [-180,180]"
            );
        }

        if (latitude < -90 || latitude > 90) {
            throw new IllegalArgumentException(
                    "Latitude out of [-90,90]"
            );
        }

        return new Document("type", "Point")
                .append(
                        "coordinates",
                        Arrays.asList(
                                longitude,
                                latitude
                        )
                );
    }
}
~~~

This function validates numeric type and range; it cannot detect on its own when a source swaps axes and both numbers remain in valid range.

### 34.1. Parameter Naming Prevents Bugs

~~~java
GeoJsonFactory.point(
        request.longitude(),
        request.latitude()
);
~~~

is much easier to review than meaningless parameter names like `a` and `b`.

## 35. REST API Contract

APIs receiving data should use clear field names:

~~~json
{
  "name": "Store A",
  "location": {
    "longitude": 106.70098,
    "latitude": 10.77689
  }
}
~~~

The service converts this into:

~~~javascript
{
  type: "Point",
  coordinates: [
    body.location.longitude,
    body.location.latitude
  ]
}
~~~

If a frontend map library requires `[lat,lon]`, convert **at that library's boundary**, without altering the GeoJSON rules in the database.

### 35.1. APIs Returning GeoJSON Directly

If an API exposes a field documented as GeoJSON, always preserve `[lon,lat]`. Never return `[lat,lon]` inside an object labeled `type: "Point"`.

### 35.2. Breaking Changes

If an older API version used coordinates in `[lat,lon]` order, switching to standard GeoJSON is a contract change. Use versioning/migration instead of silently changing behavior and producing inconsistent records.

## 36. Precision and Accuracy

A coordinate with 10 decimal places does not mean the positioning source is accurate to that level.

- **Precision:** How finely the number is represented.
- **Accuracy:** How close it is to the true physical location.
- **Uncertainty:** The uncertainty/variation of the measurement.

For example, GPS under a roof or between tall buildings can drift by many meters even when longitude/latitude values have many decimal digits.

### 36.1. Store accuracyMeters When Available

~~~javascript
{
  location: {
    type: "Point",
    coordinates: [106.70098, 10.77689]
  },
  accuracyMeters: 40,
  locationSource: "gps"
}
~~~

If the application decides whether someone has "entered a 20 m zone," it must account for positioning error potentially exceeding the check boundary.

### 36.2. Rounding Changes Position

Aggressive coordinate rounding can push a point across the boundary of a small Polygon. Choose precision based on requirements rather than rounding arbitrarily.

## 37. Explain and Performance

You can inspect the query plan:

~~~javascript
db.places.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      $maxDistance: 5000
    }
  }
}).explain("executionStats");
~~~

Observe:

- Which index is used.
- Documents/keys examined.
- Number of results.
- Geo processing cost and other filters.
- Stage and plan according to MongoDB version.

Do not time a single query run and conclude that all geo indexes are always fast; caching, data volume, polygon complexity, query cardinality, and network all have an impact.

### 37.1. Queries on a Sharded Cluster

A sharded collection may be distributed across multiple shards. A 2dsphere index does not automatically target a single shard if the shard-key predicate does not narrow the range.

Read `explain` output to see which shards participate and what local plan each shard runs.

### 37.2. Overly Complex Geometries

Polygons with hundreds of thousands of vertices or queries returning millions of points can consume significant CPU, memory, and network bandwidth. Geospatial indexes do not eliminate geometry computation and data transfer costs.

## 38. Common Pitfalls

| Mistake | Consequence |
| --- | --- |
| Storing [latitude, longitude] in GeoJSON | Wrong location or latitude out-of-range error |
| Seeing EPSG:4326 and ignoring axis order | Mixing lat/lon and lon/lat |
| Using EPSG:3857 x/y as degrees | Out-of-range / wrong CRS |
| Using strings for coordinates | Not a valid numeric GeoJSON position |
| Allowing longitude > 180 or latitude > 90 | Invalid geometry |
| Trusting range validation to catch all axis swaps | Both numbers may still be in valid range |
| Point with only one number | Missing coordinate in position |
| Polygon missing an array level | Invalid ring nesting |
| Unclosed ring | Malformed Polygon structure |
| Self-intersecting ring | Invalid topology |
| Hole outside the outer ring | Invalid region |
| Using Point for multiple positions | Wrong geometry type |
| Confusing FeatureCollection with a geometry field | Wrong index/query path |
| Using LineString as road routing | No actual road path |
| Using a giant MultiPoint for GPS history | Hard to update and hits document size limit |
| Computing Euclidean distance on degrees | Does not produce valid meters |
| Using $maxDistance=5 to search 5 km | Only 5 meters in GeoJSON near context |
| Using $centerSphere radius=5000 | Radians, not meters |
| Assuming $geoWithin sorts near-to-far | Does not guarantee distance ordering |
| Assuming $geoNear returns ETA | No road path or traffic data |
| Confusing 2d and 2dsphere | Using the wrong distance model |
| Placing 2dsphere index on the wrong field | Query cannot use the right index |
| Assuming many decimal digits mean high accuracy | Precision differs from accuracy |
| Arbitrarily wrapping longitude | Can mask CRS bugs |
| Swapping all records without classification | Corrupts records that were already right |
| Not testing the antimeridian | Regions/lines may be misinterpreted |
| Ignoring winding on large polygons | Unintentionally selects the complementary region |
| Assuming GeoJSON automatically geocodes addresses | Geometry is not generated from text |

## 39. Hands-On Exercises

### Exercise 1 – Standard Coordinates

An API returns:

~~~json
{"lat":10.77689,"lng":106.70098}
~~~

Write the GeoJSON Point. Which value must come first?

### Exercise 2 – Obvious Axis Swap

Find the error in:

~~~javascript
{
  type: "Point",
  coordinates: [10.77689, 106.70098]
}
~~~

Why does latitude exceed 90°?

### Exercise 3 – Hard-to-Detect Axis Swap

Compare `[2.35,48.86]` and `[48.86,2.35]`. Why can both be stored even though one pair points to the wrong location?

### Exercise 4 – CRS

A source returns EPSG:3857 x/y in meters. List the steps required before creating WGS84 GeoJSON.

### Exercise 5 – Polygon

Write a valid rectangular Polygon consisting of a ring with five positions where the first and last positions match. Explain the nesting of `coordinates`.

### Exercise 6 – Hole

Create a Polygon with an outer ring and a hole. State the requirements for ring orientation and ensuring the hole lies inside the outer ring.

### Exercise 7 – MultiPolygon

A service area has two non-adjacent zones. Why should you not connect their vertices into a single Polygon?

### Exercise 8 – LineString

Write a LineString with four GPS positions. Why does it not inherently store timestamps or vehicle ETA?

### Exercise 9 – 2dsphere Index

Create `places` with a Point `location`, then create a `2dsphere` index. Test a Point with `latitude = 100` in the lab and record how the server handles it.

### Exercise 10 – $near

Write a query to find Points within a 3,000-meter radius, sorted by distance. Why should you not use `$maxDistance=3` to represent 3 km?

### Exercise 11 – $geoWithin

Write a delivery-area Polygon and query Points inside it. If you need the nearest ones first, does this operator sort automatically?

### Exercise 12 – $geoIntersects

Find `serviceAreas` that intersect a test Polygon. Distinguish between intersecting and being completely contained inside.

### Exercise 13 – $geoNear

Use the `$geoNear` aggregation stage to return `distanceMeters` for places around a Point. Where must the `$geoNear` stage be placed in the pipeline?

### Exercise 14 – $centerSphere

What unit does the radius use? Why should you not pass meters directly as the second parameter?

### Exercise 15 – Java

Write a Java helper `GeoJsonFactory.point(longitude,latitude)` that checks finite/range and returns a GeoJSON BSON Document.

### Exercise 16 – CSV Import

A CSV has columns `lat,lng` in that order. Write a mapping to GeoJSON `[lon,lat]` and raise an error for invalid records.

### Exercise 17 – Mixed Legacy Data

Some records have the right `[lon,lat]` while others have the wrong `[lat,lon]`. Design a migration by source/version, and explain why you must not swap all records.

### Exercise 18 – Antimeridian

How can two points at `179.8°` and `-179.8°` longitude be close to each other? Why can a simple x/y bounding box fail?

### Exercise 19 – Accuracy

A GPS point has 10 decimal places, but `accuracyMeters = 40`. Is it accurate to the centimeter?

### Exercise 20 – Sharding and Geospatial

A sharded collection uses `tenantId` as its shard key. A query only has `$near` on `location`. Is only one shard guaranteed to participate? What should you inspect in `explain`?

### Exercise 21 – FeatureCollection

A GeoJSON file contains 1,000 Features. Design an import into MongoDB documents so that each Feature can be queried with a 2dsphere index.

### Exercise 22 – Service-Area Overlap

A customer Point falls inside two service-area Polygons. What additional business rules are needed to select a store?

## 40. Pre-Production Checklist

1. Identify the true CRS of every data source.
2. Identify the source axis order and normalize to `[lon,lat]`.
3. Validate finite numbers and longitude/latitude ranges.
4. Have tests that catch axis swaps even when both numbers are in valid range.
5. Use Point/LineString/Polygon/Multi* according to their true semantics.
6. Close polygon rings, verify winding, holes, and self-intersections.
7. Handle antimeridian/polar/large polygons where relevant.
8. Transform projected CRSs to WGS84 rather than just renaming fields.
9. Do not assume 2dsphere computes 3D elevation.
10. Store `accuracy`/`source`/`updatedAt` as needed.
11. Use a geometry field with a well-defined schema only.
12. Create the 2dsphere index on the exact field after the data is clean enough.
13. Distinguish between `$near`, `$geoWithin`, `$geoIntersects`, and `$geoNear`.
14. Verify meters for near/geoNear and radians for centerSphere.
15. Do not substitute geographic distance for road distance.
16. Check query plans and index performance.
17. If sharded, check shard-key targeting.
18. Design APIs with explicit `longitude`/`latitude` field names.
19. Have migrations and tests for legacy `lat`/`lng` data.
20. Cross-check sample coordinates on a map.
21. Monitor invalid geospatial record rates and query latency.
22. Have a plan for falsely over-precise or stale GPS data.

## 41. Conclusion

GeoJSON provides a JSON model for geographic data, from **Point** and **LineString** to **Polygon** and composite geometries. MongoDB can store these geometries, build **2dsphere indexes**, and query by distance, containment, or intersection.

The most important rule:

> **A two-dimensional GeoJSON position is always ordered [longitude, latitude].**

Both values are in **degrees**, typically in WGS84. Longitude falls in `[-180,180]` and latitude in `[-90,90]`. Do not confuse this with `lat/lng` from some APIs, the axis order of certain EPSG:4326 libraries, or x/y in meters from Web Mercator.

When working with MongoDB:

- Store Point for a position, LineString for a path, and Polygon/MultiPolygon for regions.
- Maintain proper `coordinates` nesting, close rings, and validate topology.
- Create a **2dsphere index** on the geometry field.
- Use **$near/$geoNear** for distance, **$geoWithin** for containment, and **$geoIntersects** for intersection.
- Distinguish between degrees, meters, and radians in different parts of a query.
- Validate source data, check for axis-swap errors, and test edge cases.

**Syntactically valid GeoJSON does not guarantee a correct position on Earth.** The geometric model, axis order, and source coordinate system must all be determined together.

## References

- [MongoDB Manual — Geospatial Queries](https://www.mongodb.com/docs/manual/geospatial-queries/)
- [MongoDB Manual — GeoJSON Objects](https://www.mongodb.com/docs/manual/reference/geojson/)
- [MongoDB Manual — Geospatial Indexes](https://www.mongodb.com/docs/manual/core/geospatial-indexes/)
- [MongoDB Manual — 2dsphere Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/)
- [MongoDB Manual — $near](https://www.mongodb.com/docs/manual/reference/operator/query/near/)
- [MongoDB Manual — $geoWithin](https://www.mongodb.com/docs/manual/reference/operator/query/geoWithin/)
- [MongoDB Manual — $geoIntersects](https://www.mongodb.com/docs/manual/reference/operator/query/geoIntersects/)
- [MongoDB Manual — $geoNear](https://www.mongodb.com/docs/manual/reference/operator/aggregation/geoNear/)
- [MongoDB Manual — Geospatial Query Operators](https://www.mongodb.com/docs/manual/reference/operator/query-geospatial/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [GeoJSON RFC 7946](https://www.rfc-editor.org/rfc/rfc7946)
