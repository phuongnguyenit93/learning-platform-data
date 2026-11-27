# Point Indexes and Spatial Data Queries in Neo4j

## 1. Problem Statement: Finding Entities Near a Location

In the **property graph** model, a geographic location can be a property on a node or relationship. For example, a logistics system stores `PickupPoint` nodes, `Supplier` nodes, and `(:Supplier)-[:SUPPLIES]->(:PickupPoint)` relationships. A common requirement is:

> Given a customer's coordinates, find pickup points within a 2 km radius, sort by distance, and return each point's supplier.

If you only store `latitude` and `longitude` as two separate numbers and filter every node, the database may have to scan many records and compute distances repeatedly. A **point index** is an index specifically designed for `POINT` properties, helping Neo4j find points satisfying spatial conditions such as **within a radius** or **within a bounding box**.

Within the **Lookup Indexes** chapter, distinguish these index types:

| Index Type | Data Looked Up | Application Example |
| --- | --- | --- |
| **Token lookup index** | Node labels and relationship types | Finding nodes with the `PickupPoint` label, relationships of type `SUPPLIES` |
| **Range index** | Properties by value or value range; also supports some comparisons with `POINT` | Finding `p.code = 'P001'`, `p.capacity > 10` |
| **Point index** | `POINT` properties, optimized for spatial locations | `point.distance(...)`, `point.withinBBox(...)` |
| **Text index** | `STRING` properties | Finding names containing `'mart'` |

**A point index is not a token lookup index** even though both belong to the broader indexing topic. Token indexes support finding labels/types; point indexes support spatial predicates on **properties**.

## 2. The `POINT` Data Type and Coordinate Systems

Neo4j represents locations using `POINT` values: coordinates paired with a **coordinate reference system** (CRS). Two common groups are:

| CRS | How to Create | SRID | Description |
| --- | --- | --- | --- |
| **WGS 84 2D** | `point({longitude: 106.70, latitude: 10.78})` | `4326` | Longitude/latitude on Earth; suitable for GPS |
| **WGS 84 3D** | `point({longitude: 106.70, latitude: 10.78, height: 15.0})` | `4979` | Adds elevation/height, measured in meters |
| **Cartesian 2D** | `point({x: 30.0, y: 40.0})` | `7203` | Application-defined planar coordinate system |
| **Cartesian 3D** | `point({x: 30.0, y: 40.0, z: 5.0})` | `9157` | Application-defined three-dimensional space |

Test directly in Neo4j Browser:

```cypher
RETURN
  point({longitude: 106.7000, latitude: 10.7800}) AS geographic,
  point({x: 30.0, y: 40.0}) AS cartesian;
```

With WGS 84, **`longitude` is longitude and `latitude` is latitude**. If you use `x`/`y` without specifying a CRS, Neo4j defaults to Cartesian coordinates; you cannot treat `x=106.7, y=10.78` as geographic longitude/latitude without setting the proper CRS.

Neo4j supports `POINT` properties on both nodes and relationships. A point can be stored directly on the `p.location` property:

```cypher
MERGE (p:PickupPoint {code: 'P001'})
SET p.name = 'Pickup Point A',
    p.location = point({longitude: 106.7000, latitude: 10.7800})
RETURN p;
```

Unlike storing coordinates as a string `'106.7,10.78'` or a `LIST<FLOAT>`, storing an **actual `POINT` value** enables spatial functions and point indexes.

### What Units Are Used for Distance?

`point.distance(a, b)` returns a floating-point number if both points share the same CRS:

- For **WGS 84 2D/3D**, the result is in **meters** (a geographic calculation approximating the shape of the Earth).
- For **Cartesian**, the result uses the **units of the input coordinate system**. If `x, y` are pixels, the distance is in pixels—it does not automatically become meters.
- For two points with **different CRSs** or a `null` input, the function can return `null`; do not assume that means zero distance.

```cypher
WITH
  point({x: 0.0, y: 0.0}) AS origin,
  point({x: 3.0, y: 4.0}) AS target
RETURN point.distance(origin, target) AS distanceInCoordinateUnits;
// 5.0 (Cartesian coordinate units)
```

**Geographic distance is not road travel distance.** Two points 500 m apart via `point.distance` might require a much longer road trip due to bridges, rivers, one-way streets, or terrain. To find the shortest route on a road network, model road edges and use an appropriate pathfinding algorithm.

## 3. Creating Sample Data

Suppose simulated pickup points have coordinates around the same area. Run the following query on a test database; `MERGE` by code prevents duplicate nodes on re-runs:

```cypher
UNWIND [
  {code: 'P001', name: 'Pickup Point A', longitude: 106.7000, latitude: 10.7800},
  {code: 'P002', name: 'Pickup Point B', longitude: 106.7050, latitude: 10.7830},
  {code: 'P003', name: 'Pickup Point C', longitude: 106.7200, latitude: 10.7950},
  {code: 'P004', name: 'Pickup Point D', longitude: 106.6900, latitude: 10.7750}
] AS row
MERGE (p:PickupPoint {code: row.code})
SET p.name = row.name,
    p.location = point({
      longitude: row.longitude,
      latitude: row.latitude
    });
```

Two notes when importing data:

1. Data from CSV or JSON often stores coordinates as `STRING`. Validate data and convert to numbers before calling `point(...)`, for example `toFloat(row.longitude)`.
2. Verify that source coordinates truly belong to the chosen CRS. Swapping longitude and latitude or mixing a local metric grid with WGS 84 will produce wrong query results even though the Cypher is valid.

## 4. Creating and Managing Point Indexes

### 4.1. Point Index on a Node Property

```cypher
CREATE POINT INDEX idx_pickup_location IF NOT EXISTS
FOR (p:PickupPoint) ON (p.location);
```

This command creates a point index on the `location` property of nodes carrying the `PickupPoint` label. Only values of type `POINT` are used for spatial lookups in this index. Having the index **does not** turn a string or two numeric properties `latitude`, `longitude` into a point.

`IF NOT EXISTS` allows the index creation command to be re-run when an equivalent index already exists; it does not verify every configuration setting of a preexisting index.

### 4.2. Point Index on a Relationship Property

Relationships can also hold coordinates, such as the intersection location of a road segment:

```cypher
CREATE POINT INDEX idx_road_intersection IF NOT EXISTS
FOR ()-[r:ROAD_SEGMENT]-() ON (r.intersection);
```

An index on a relationship operates on the `POINT` property of relationships with the matching type. However, if `location` describes the physical position of a place, modeling it as a property on a **place node** is usually easier to query and maintain.

### 4.3. Checking That the Index Is Ready

```cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties, state
WHERE name = 'idx_pickup_location'
RETURN name, type, entityType, labelsOrTypes, properties, state;
```

Expected output shows `type = 'POINT'`, `properties = ['location']`, and `state = 'ONLINE'`. After creating an index on a large graph, Neo4j may take time for *population* before the index transitions to `ONLINE`. `SHOW INDEXES` confirms that the index exists and is available to the query planner.

When you need to drop a **test index**, you can use:

```cypher
DROP INDEX idx_pickup_location IF EXISTS;
```

In a database serving live users, audit dependent queries before dropping an index.

### 4.4. Configuring Coordinate Bounds — Only When Needed

Point indexes support `indexConfig` with separate `min`/`max` pairs for Cartesian 2D/3D and WGS 84 2D/3D. Example for **planar coordinates**:

```cypher
CREATE POINT INDEX idx_site_position IF NOT EXISTS
FOR (s:Site) ON (s.position)
OPTIONS {
  indexConfig: {
    `spatial.cartesian.min`: [-10000.0, -10000.0],
    `spatial.cartesian.max`: [10000.0, 10000.0]
  }
};
```

Do not configure `spatial.cartesian.*` for WGS 84 longitude/latitude values: those are **two different coordinate systems**. When there is no measured tuning need, stick with default settings. A point index accepts **one property** in its declaration; you cannot create a composite point index on `(latitude, longitude)`.

## 5. Three Query Patterns That Leverage Point Indexes

### 5.1. Finding Points Within a Radius

Given a center point at longitude `106.7000`, latitude `10.7800`, query nodes within a 2,000 m radius:

```cypher
WITH point({longitude: 106.7000, latitude: 10.7800}) AS center
MATCH (p:PickupPoint)
WHERE point.distance(p.location, center) <= 2000
RETURN
  p.code AS code,
  p.name AS name,
  round(point.distance(p.location, center)) AS distanceMeters
ORDER BY distanceMeters ASC;
```

In this query:

- `MATCH (p:PickupPoint)` narrows the scope to the indexed label.
- `point.distance(p.location, center) <= 2000` is a predicate **capable of being supported by a point index**.
- `ORDER BY distanceMeters` sorts results for display requirements. Using a point index for filtering **does not mean** results are automatically returned in nearest-first order.

Production applications should pass coordinates and radius as parameters:

```cypher
WITH point({
  longitude: $longitude,
  latitude: $latitude
}) AS center
MATCH (p:PickupPoint)
WHERE point.distance(p.location, center) <= $radiusMeters
RETURN
  p.code AS code,
  p.name AS name,
  point.distance(p.location, center) AS distanceMeters
ORDER BY distanceMeters ASC
LIMIT 20;
```

Example parameter set:

```json
{
  "longitude": 106.7,
  "latitude": 10.78,
  "radiusMeters": 2000
}
```

Choose a **positive radius appropriate for the search goal**; if the radius is too large relative to data distribution, many records still have to be processed and sorted.

### 5.2. Finding Points Within a Bounding Box

`point.withinBBox(value, lowerLeft, upperRight)` checks whether a point lies inside the rectangle defined by its **lower-left corner** and **upper-right corner**:

```cypher
MATCH (p:PickupPoint)
WHERE point.withinBBox(
  p.location,
  point({longitude: 106.6900, latitude: 10.7700}),
  point({longitude: 106.7100, latitude: 10.7900})
)
RETURN p.code, p.name, p.location;
```

For WGS 84, the lower-left corner usually has the smaller longitude and smaller latitude, and the upper-right corner has the larger longitude and larger latitude. The function has special handling when the box crosses the 180° meridian; when querying across wide regions or near the International Date Line, test those cases carefully.

Bounding boxes are useful when a map UI asks: **"Load locations inside the currently visible map viewport."** The result is the set of points within the rectangular frame; if you want to filter strictly by a **circular radius**, use `point.distance`.

### 5.3. Equality Comparison Against a Specific `POINT` Value

```cypher
MATCH (p:PickupPoint)
WHERE p.location = point({longitude: 106.7000, latitude: 10.7800})
RETURN p.code, p.name;
```

Point indexes support equality checks on `POINT` properties. Equality comparisons suit data with standardized coordinates, whereas for real-world GPS measurements, slight jitter between two readings often causes exact equality to miss; in such cases, a small radius check is more appropriate.

## 6. Combining Spatial Queries with Graph Relationships

Neo4j's strength lies in using the same query to **filter by location** and **traverse connections**. Suppose we create two simulated suppliers:

```cypher
MERGE (s1:Supplier {id: 'S001'})
SET s1.name = 'Supplier 1'
MERGE (s2:Supplier {id: 'S002'})
SET s2.name = 'Supplier 2'
WITH s1, s2
MATCH (p1:PickupPoint {code: 'P001'})
MATCH (p2:PickupPoint {code: 'P002'})
MATCH (p3:PickupPoint {code: 'P003'})
MERGE (s1)-[:SUPPLIES]->(p1)
MERGE (s1)-[:SUPPLIES]->(p2)
MERGE (s2)-[:SUPPLIES]->(p3);
```

Then query the suppliers of pickup points near the customer:

```cypher
WITH point({longitude: $longitude, latitude: $latitude}) AS center
MATCH (p:PickupPoint)
WHERE point.distance(p.location, center) <= $radiusMeters
MATCH (s:Supplier)-[:SUPPLIES]->(p)
RETURN
  p.code AS pickupCode,
  p.name AS pickupName,
  s.name AS supplierName,
  round(point.distance(p.location, center)) AS distanceMeters
ORDER BY distanceMeters, pickupCode;
```

The query planner can use the point index to locate matching `PickupPoint` nodes, then expand along `SUPPLIES` relationships. **A point index is not a relationship index**: it filters points by location, while traversal uses the graph structure. Actual query optimization still depends on the data, number of matching nodes, and the plan selected by the planner.

## 7. Inspecting the Query Planner and Practical Optimization

### 7.1. `EXPLAIN` and `PROFILE`

Merely creating an index does not guarantee Neo4j will use it for every statement. Use `EXPLAIN` to inspect the plan without executing the query:

```cypher
EXPLAIN
MATCH (p:PickupPoint)
WHERE point.distance(
  p.location,
  point({longitude: 106.7000, latitude: 10.7800})
) <= 2000
RETURN p.code, p.name;
```

When you need **actual metrics**, use `PROFILE` on test data or a representative load test:

```cypher
PROFILE
MATCH (p:PickupPoint)
WHERE point.withinBBox(
  p.location,
  point({longitude: 106.6900, latitude: 10.7700}),
  point({longitude: 106.7100, latitude: 10.7900})
)
RETURN p.code;
```

Inspect index access operators, `Rows`, `DB Hits`, and additional filtering steps. Displayed operator names can vary across Neo4j versions. With an example set of only four nodes, the planner choosing a label scan instead of a point index **is not necessarily an error**; scanning a tiny set can cost less than using an index.

### 7.2. Writing Queries to Enable Point Index Usage

| Query / Design | Point Index Eligibility |
| --- | --- |
| `MATCH (p:PickupPoint) WHERE point.distance(p.location, center) <= radius` | Matches a supported distance predicate |
| `MATCH (p:PickupPoint) WHERE point.withinBBox(p.location, lo, hi)` | Matches a supported bounding box predicate |
| `MATCH (p:PickupPoint) WHERE p.location = point(...)` | Matches a supported `POINT` equality predicate |
| `MATCH (p:PickupPoint) WHERE p.latitude > 10.7` | Does not use the point index on `p.location`, as it filters a different numeric property |
| `MATCH (p) WHERE point.distance(p.location, center) <= radius` | Missing the `PickupPoint` label, giving the planner little basis to pick that label's point index |
| `MATCH (p:PickupPoint) WHERE point.distance(point({longitude: p.lon, latitude: p.lat}), center) <= radius` | Constructs a point at query time from other properties rather than querying the point-indexed property directly |

When multiple indexes or selective conditions coexist, the query planner chooses the access path based on cost estimates. Benchmark on a dataset resembling production with representative input parameters.

### 7.3. What to Measure

- **Selectivity:** a query returning 50 points out of 10 million typically gains far more from an index than a query returning 9 million points.
- **Index status:** confirm `SHOW INDEXES` reports the index as `ONLINE`, on the right label and property.
- **Post-filter costs:** `ORDER BY`, `LIMIT`, multi-hop relationship expansions, and `collect` can still consume substantial resources.
- **CRS consistency:** WGS 84 data and search points must share compatible CRSs; do not mix 2D and 3D points arbitrarily.
- **Write frequency:** indexes incur storage and write-update overhead; create them for properties queried frequently.

**Do not compare a point index against a range/text index based on a single execution time**; cache state, record counts, search parameters, and query plans all influence the outcome.

## 8. Java Driver and Spring Data Neo4j Integration

### 8.1. Java Driver: Passing Parameters into Cypher

With the Java Driver, keep coordinates and radius as parameters for query reuse. The example below assumes the application already has a `Driver driver` instance and database `neo4j`:

```java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

String cypher = """
    WITH point({
      longitude: $longitude,
      latitude: $latitude
    }) AS center
    MATCH (p:PickupPoint)
    WHERE point.distance(p.location, center) <= $radiusMeters
    RETURN p.code AS code,
           p.name AS name,
           point.distance(p.location, center) AS distanceMeters
    ORDER BY distanceMeters ASC
    LIMIT 20
    """;

Map<String, Object> params = Map.of(
    "longitude", 106.7,
    "latitude", 10.78,
    "radiusMeters", 2000.0
);

try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    List<Map<String, Object>> nearest = session.executeRead(tx ->
        tx.run(cypher, params)
          .list(record -> Map.<String, Object>of(
              "code", record.get("code").asString(),
              "name", record.get("name").asString(),
              "distanceMeters", record.get("distanceMeters").asDouble()
          ))
    );
    nearest.forEach(System.out::println);
}
```

`executeRead` is appropriate because the query is read-only; the driver manages the read transaction and invokes the callback. Validate radius, coordinates, and authorization at the API layer; never concatenate raw user input into Cypher strings.

### 8.2. Spring Data Neo4j

When using Spring Data Neo4j, you can write repository queries with `$longitude`, `$latitude`, and `$radiusMeters` parameters similarly. Conceptual example:

```cypher
WITH point({longitude: $longitude, latitude: $latitude}) AS center
MATCH (p:PickupPoint)
WHERE point.distance(p.location, center) <= $radiusMeters
RETURN p
ORDER BY point.distance(p.location, center)
LIMIT 20
```

During entity mapping, the location property must be persisted as the appropriate `POINT` type; Java classes and converters must match your Spring Data Neo4j version. If you also need to return `distanceMeters`, design a DTO/projection or use `Neo4jClient` with explicit result mapping. Do not assume simply naming a field `location` causes the framework to create a point index automatically: indexes must be managed via schema migrations or explicit index creation statements.

## 9. Common Errors and How to Fix Them

**1. Swapping longitude and latitude.** Data may still consist of valid numbers, yet the location falls in the wrong part of the world. Always keep the convention `longitude` first, `latitude` second when parsing sources, constructing points, and designing APIs.

**2. Storing a point as a `STRING` or two numeric fields and expecting a point index to help.** A point index on `p.location` only supports queries on actual `POINT` values. Convert and store the data in the proper property.

**3. Calling `point.distance` across two different CRSs.** The result can be `null`, causing `<= radius` to match no rows. Check `p.location.crs`, SRID, and how the search point is constructed.

**4. Assuming a WGS 84 radius is in degrees.** `point.distance` with WGS 84 returns meters; `2000` means 2 km, not 2,000 degrees. For Cartesian, the unit is whatever coordinate unit the system defines.

**5. Treating a bounding box as if it were a circle.** `point.withinBBox` filters by a rectangle; the box's corners can be farther from the center than the desired radius. You can use a bounding box to pre-filter and then apply `point.distance` for an exact circle when appropriate.

**6. Assuming an index will always be used.** The planner chooses plans by cost; inspect `PROFILE` on sufficiently large data and verify labels, properties, index status, and predicates.

**7. Treating geographic distance as travel time.** Straight-line distance ignores road networks, traffic direction, and speed limits. When routing is needed, you need a road graph or routing service.

## 10. Self-Check Exercises

1. Extend the sample dataset with `P005` using WGS 84 2D coordinates. Find points within a 1,000 m radius around `P001` and sort by distance.
2. Write a bounding box query for a map frame with `longitude` from `106.695` to `106.715` and `latitude` from `10.775` to `10.790`. Compare its result set against a radius query.
3. Run `SHOW INDEXES`, `EXPLAIN`, and `PROFILE` to confirm the index exists, is `ONLINE`, and whether the planner uses it.
4. Design the relationship between `PickupPoint` and `Supplier`. Write a query that filters points within 2 km of a customer location and also returns the supplier name.
5. Explain why `point.distance(point({x: 0, y: 0}), point({x: 3, y: 4}))` does not return a distance in meters by default.

## 11. Key Takeaways

- Use the **`POINT`** type with the proper CRS right when modeling coordinates; avoid storing locations solely as strings.
- Create **`CREATE POINT INDEX`** for nodes or relationships with frequently filtered location properties. This is a **spatial property index**, distinct from token lookup indexes that look up labels/types.
- Use **`point.distance`** for radius searches, **`point.withinBBox`** for map viewports, and equality checks for exact coordinate matches.
- **WGS 84 measures distance in meters**, while Cartesian uses coordinate system units; a point index does not compute shortest driving routes.
- Use **`SHOW INDEXES`**, **`EXPLAIN`**, and **`PROFILE`** to verify schema and performance; combine spatial filtering with graph traversal to leverage the full power of a property graph.

### References

- [Neo4j Cypher Manual — Create indexes (Point indexes)](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/create-indexes/)
- [Neo4j Cypher Manual — Spatial functions](https://neo4j.com/docs/cypher-manual/current/functions/spatial/)
- [Neo4j Cypher Manual — Spatial values](https://neo4j.com/docs/cypher-manual/current/values-and-types/spatial/)
- [Neo4j Cypher Manual — The impact of indexes on query performance](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/using-indexes/)
