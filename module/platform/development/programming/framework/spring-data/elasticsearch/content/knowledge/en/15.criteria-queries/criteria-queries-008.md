# Geographic Queries Within Criteria Capabilities

Spring Data Elasticsearch provides CriteriaQuery to build queries using a fluent API. Besides standard conditions like keyword matching, ranges, and booleans, Criteria also supports several geographic conditions on `geo_point` fields.

Common geographic queries include:

- Finding documents within a radius around a coordinate.
- Finding documents inside a geographic rectangle (bounding box).
- Finding documents inside a polygon.
- Combining geographic conditions with other business conditions such as status, venue type, or tenant.

CriteriaQuery lets you express these conditions as Java objects instead of manually assembling JSON queries. However, Criteria does not cover the entire Elasticsearch Query DSL. Advanced requirements such as `geo_shape`, distance sorting, geographic aggregations, or specialized options may require NativeQuery or the Elasticsearch Java API Client directly.

## 1. Preparing a Geographic Field in the Entity

Elasticsearch supports the `geo_point` field type to store a location consisting of latitude and longitude. In Spring Data Elasticsearch, you can declare the field as follows:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Document(indexName = "stores")
public class Store {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String name;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.GeoPoint)
    private GeoPoint location;

    // constructors, getters and setters
}
~~~

The `location` field is declared with `FieldType.GeoPoint`. Spring Data Elasticsearch's `GeoPoint` type represents a geographic point.

You can instantiate a point with latitude and longitude:

~~~java
GeoPoint location = new GeoPoint(10.7769, 106.7009);
~~~

In this example:

- 10.7769 is the latitude.
- 106.7009 is the longitude.

The parameter order in the `GeoPoint` constructor is latitude first, longitude second. This is easy to mix up because some geographic JSON formats use longitude, latitude order.

### 1.1. Actual Mapping in Elasticsearch

The corresponding mapping looks like:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "keyword"
      },
      "active": {
        "type": "boolean"
      },
      "category": {
        "type": "keyword"
      },
      "location": {
        "type": "geo_point"
      }
    }
  }
}
~~~

You can inspect the mapping with:

~~~http
GET /stores/_mapping?pretty
~~~

If `location` is created as an ordinary object instead of `geo_point`, geographic queries will not work as expected. Dynamic mapping can infer certain point formats, but for important business data you should declare the mapping explicitly.

### 1.2. Representations of geo_point

Elasticsearch supports several point formats, such as an object with lat/lon, a string `"lat,lon"`, or a coordinate array in longitude, latitude order. Object example:

~~~json
{
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
~~~

For Elasticsearch/GeoJSON coordinate arrays, the order is typically `[longitude, latitude]`:

~~~json
{
  "location": [
    106.7009,
    10.7769
  ]
}
~~~

Do not confuse this order with the `GeoPoint(latitude, longitude)` constructor. Standardize the convention at boundaries where data enters from APIs, databases, or maps.

Valid latitudes fall between -90 and 90; longitudes fall between -180 and 180. Validate input data to prevent swapped coordinates or out-of-range values from being stored.

## 2. CriteriaQuery and Criteria for Geographic Queries

CriteriaQuery is Spring Data Elasticsearch's `Query` implementation, built from one or more `Criteria`.

Common imports:

~~~java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
~~~

A simple query:

~~~java
Criteria criteria = new Criteria("active").is(true);
Query query = new CriteriaQuery(criteria);

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

For geographic queries, Criteria is created on the `geo_point` field name:

~~~java
Criteria criteria = new Criteria("location");
~~~

Then add a spatial condition such as `within` with `GeoCircle`, `GeoBox`, or `GeoPolygon`, depending on the target region type and the APIs available in your Spring Data Elasticsearch version.

Commonly used geographic classes live in the package:

~~~java
import org.springframework.data.elasticsearch.core.geo.GeoPoint;
import org.springframework.data.elasticsearch.core.geo.GeoBox;
import org.springframework.data.elasticsearch.core.geo.GeoCircle;
import org.springframework.data.elasticsearch.core.geo.GeoPolygon;
~~~

Class names, constructors, and overloads can change across Spring Data Elasticsearch versions. Check your actual dependency before applying examples to your project.

## 3. Finding Locations Within a Radius

A common requirement is finding stores within a given radius around a user's location. For example, finding stores within 5 km around central Ho Chi Minh City.

With Criteria supporting `GeoCircle`, you can express a circular area around a point:

~~~java
GeoPoint center = new GeoPoint(10.7769, 106.7009);

Criteria criteria = new Criteria("location")
    .within(new GeoCircle(center, 5000));

Query query = new CriteriaQuery(criteria);

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

The example uses a radius of 5,000 meters. In `GeoCircle` APIs with a constructor taking a numeric radius, that value is expressed in meters. If your project's version uses a `Distance` type or another constructor, convert units according to that API.

A circle condition typically translates into Elasticsearch's `geo_distance` query. The equivalent REST query looks like:

~~~http
POST /stores/_search
{
  "query": {
    "geo_distance": {
      "distance": "5km",
      "location": {
        "lat": 10.7769,
        "lon": 106.7009
      }
    }
  }
}
~~~

Where:

- `distance` is the search radius.
- `location` is the center coordinate.
- Elasticsearch returns documents whose point lies within the specified distance.

### 3.1. Distance Units

Elasticsearch supports many distance units, for example:

| Unit | Common symbol |
|---|---|
| Meters | m |
| Kilometers | km |
| Centimeters | cm |
| Millimeters | mm |
| Miles | mi |
| Yards | yd |
| Feet | ft |
| Inches | in |
| Nautical miles | nmi |

When using REST DSL, you can pass a string with units such as `5km` or `5000m`. When using `GeoCircle`, check the constructor in your version to know whether the radius is in meters or a `Distance` object with its own unit.

Do not pass the number 5 assuming it means 5 km if the API interprets it as 5 meters. Unit mismatches can make results far too narrow or far too broad.

### 3.2. Searching Within a Radius with Other Conditions

You can combine geographic conditions with store status:

~~~java
GeoPoint center = new GeoPoint(10.7769, 106.7009);
GeoCircle radius = new GeoCircle(center, 5000);

Criteria criteria = new Criteria("active").is(true)
    .and("location").within(radius);

Query query = new CriteriaQuery(criteria);

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

This condition requires documents to both have `active = true` and have `location` inside the circle. Criteria joins conditions with AND in the example above.

You can also add category:

~~~java
Criteria criteria = new Criteria("active").is(true)
    .and("category").is("grocery")
    .and("location").within(radius);
~~~

Confirm that `category` has a mapping suited for exact matching, typically `keyword`.

## 4. Finding Locations Inside a Geographic Rectangle (Bounding Box)

A bounding box is a rectangular region defined by two corners:

- Top-left: upper-left corner.
- Bottom-right: lower-right corner.

With `GeoBox`, for example:

~~~java
GeoBox box = new GeoBox(
    new GeoPoint(10.85, 106.65),
    new GeoPoint(10.70, 106.80)
);

Criteria criteria = new Criteria("location").within(box);
Query query = new CriteriaQuery(criteria);

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

The two points are passed in top-left then bottom-right order. `GeoPoint` still uses latitude, longitude order.

The equivalent REST query uses `geo_bounding_box`:

~~~http
POST /stores/_search
{
  "query": {
    "geo_bounding_box": {
      "location": {
        "top_left": {
          "lat": 10.85,
          "lon": 106.65
        },
        "bottom_right": {
          "lat": 10.70,
          "lon": 106.80
        }
      }
    }
  }
}
~~~

Bounding boxes suit scenarios such as:

- Finding points inside the currently displayed map area.
- Finding locations within an approximate rectangular region.
- Limiting data to a map application's viewport.
- Preliminary filtering before running more complex geographic processing.

A bounding box does not accurately model administrative borders or arbitrary shapes. If the target region is non-rectangular, polygon or `geo_shape` is more appropriate.

### 4.1. Limitations When Crossing the 180th Meridian

Regions near the International Date Line may cross the 180th meridian. Longitude can then wrap from values near 180 to -180. A simple bounding box may fail to represent the small region you intended to describe.

For global applications, test Elasticsearch's behavior for bounding boxes crossing the 180th meridian and consider polygons or splitting regions appropriately. Do not assume every rectangle on a flat map corresponds to a simple geographic bounding box.

## 5. Finding Locations Inside a Polygon (Geo Polygon)

Some regions have boundaries that are neither rectangles nor circles. Examples include delivery zones, campuses, coverage areas, or business district boundaries.

`GeoPolygon` describes an area using a list of points forming the boundary:

~~~java
List<GeoPoint> points = List.of(
    new GeoPoint(10.80, 106.65),
    new GeoPoint(10.80, 106.75),
    new GeoPoint(10.72, 106.75),
    new GeoPoint(10.72, 106.65),
    new GeoPoint(10.80, 106.65)
);

GeoPolygon polygon = new GeoPolygon(points);

Criteria criteria = new Criteria("location").within(polygon);
Query query = new CriteriaQuery(criteria);

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

This example describes a roughly rectangular area using a polygon. The last point repeats the first point to close the boundary. Check constructor requirements and polygon rules for the library version you are using.

The equivalent REST query uses `geo_polygon`:

~~~http
POST /stores/_search
{
  "query": {
    "geo_polygon": {
      "location": {
        "points": [
          { "lat": 10.80, "lon": 106.65 },
          { "lat": 10.80, "lon": 106.75 },
          { "lat": 10.72, "lon": 106.75 },
          { "lat": 10.72, "lon": 106.65 },
          { "lat": 10.80, "lon": 106.65 }
        ]
      }
    }
  }
}
~~~

Notes on polygons:

- Points must form a valid boundary.
- Avoid self-intersecting polygons or unintended overlapping edges.
- Point order must trace the region's perimeter in the intended shape.
- Verify polygons around special meridians or parallels.
- For complex geographic data, verify results with sample points inside and outside the region.

`GeoPolygon` in Criteria expresses a `geo_polygon` query on `geo_point`. It is not equivalent to the full `geo_shape` feature set in Elasticsearch.

## 6. Combining Geographic Queries with Business Conditions

Criteria can combine geographic conditions with regular conditions. For example, finding open stores within a 3 km radius in the `pharmacy` category:

~~~java
GeoPoint center = new GeoPoint(10.7769, 106.7009);
GeoCircle radius = new GeoCircle(center, 3000);

Criteria criteria = new Criteria("active").is(true)
    .and("category").is("pharmacy")
    .and("location").within(radius);

Query query = new CriteriaQuery(criteria);

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

Conditions in the example are ANDed: documents must satisfy all three conditions.

When OR logic or multiple condition branches are needed, Criteria supports chaining according to its API. However, when a query has a complex bool structure, use an explicit Query DSL to avoid misinterpreting how the parser groups branches.

For example, requirement: store must lie within the geographic region and have one of two categories. Desired logical structure:

~~~text
location within region
        AND
   +----+----+
   |         |
category A  category B
    (OR)
~~~

If a Criteria chain does not clearly express the required OR/AND grouping, switch to NativeQuery or the Elasticsearch Java API Client for exact control over the bool query.

## 7. Paginating Geographic Results

A geographic area can contain many documents. Do not load all results into the application if the UI only displays one page.

You can attach `Pageable` to `CriteriaQuery`:

~~~java
GeoPoint center = new GeoPoint(10.7769, 106.7009);
GeoCircle radius = new GeoCircle(center, 5000);

Criteria criteria = new Criteria("location").within(radius);

Query query = new CriteriaQuery(criteria)
    .setPageable(PageRequest.of(0, 20));

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

The example retrieves up to 20 results on the first page. `Pageable` limits returned documents and can carry sort information.

Notes:

- Page/total counts may require Elasticsearch to track total hits.
- Large offsets can be resource-intensive.
- If data is large and many pages must be traversed, consider `search_after` or an appropriate pagination mechanism.
- If the goal is showing the nearest places, limiting size alone is not enough; you also need distance sorting.

## 8. Filtering by Region Does Not Mean Sorting by Distance

An important point: a `geo_distance` or `GeoCircle` query determines which documents lie within a radius. It does not automatically guarantee results are sorted from nearest to farthest.

Criteria example:

~~~java
Criteria criteria = new Criteria("location")
    .within(new GeoCircle(center, 5000));

Query query = new CriteriaQuery(criteria);
~~~

This query limits the result set within the radius. If the UI needs to show the closest store first, you must add a geo distance sort.

Elasticsearch REST DSL looks like:

~~~http
POST /stores/_search
{
  "query": {
    "geo_distance": {
      "distance": "5km",
      "location": {
        "lat": 10.7769,
        "lon": 106.7009
      }
    }
  },
  "sort": [
    {
      "_geo_distance": {
        "location": {
          "lat": 10.7769,
          "lon": 106.7009
        },
        "order": "asc",
        "unit": "km",
        "distance_type": "arc"
      }
    }
  ]
}
~~~

Results are sorted by ascending distance. Distance sort is a separate part of the Search DSL; whether it can be expressed directly via Criteria varies by version. When CriteriaQuery lacks the required option, use NativeQuery or the Elasticsearch Java API Client.

When multiple documents have identical distances, add a stable secondary sort criterion such as ID for consistent pagination. Secondary sort syntax depends on the query API in use.

## 9. What Does CriteriaQuery Support and Where Are Its Limits?

Criteria is a convenient API for conditions clearly mapped by Spring Data. For geography, common forms are:

| Data/region type | Purpose | Common Criteria |
|---|---|---|
| `geo_point` within radius | Search around a center by distance | `within(GeoCircle)` |
| `geo_point` inside rectangle | Search within a bounding box | `within(GeoBox)` |
| `geo_point` inside polygon | Search within a polygon region | `within(GeoPolygon)` |
| Combine geo with regular fields | Filter by location and business rules | `Criteria.and(...)` / `Criteria.or(...)` |

Criteria is not a replacement for the entire Elasticsearch DSL. The following requirements usually need careful verification or another query API:

- `geo_shape` with complex geometries such as multipolygons, line strings, or geometry collections.
- Spatial relations such as `intersects`, `within`, `contains`, or `disjoint` on `geo_shape`.
- Sorting by distance with `_geo_distance`.
- Geographic aggregations such as `geohash_grid`, `geo_tile_grid`, or `geo_bounds`.
- Script-based calculations using location.
- Specialized `geo_distance` options like `distance_type` or `validation_method` if the Criteria version does not expose them.
- Combining complex bool branches alongside nested queries or specialized filters.

When these capabilities are needed, use NativeQuery (in supported Spring Data Elasticsearch versions) to build queries via the Elasticsearch Java API Client, or invoke the client directly. Pick an abstraction suited to your dependency version and do not force complex DSL into Criteria.

## 10. Distinguishing geo_point and geo_shape

`geo_point` represents a single location. It fits:

- Stores.
- Restaurants.
- Users.
- GPS devices.
- Sensor stations.
- A pickup/delivery point.

`geo_shape` represents complex geometries such as lines, areas, or geometry collections. It fits:

- Regional boundaries.
- Routes.
- Coverage zones.
- Arbitrary-shaped delivery areas.
- Multi-sided or multi-part shapes.

| Characteristic | geo_point | geo_shape |
|---|---|---|
| Data | A single point | Geometry |
| Radius query around a point | `geo_distance` | Can use shape relations depending on requirements |
| Bounding box | Yes | Yes |
| Polygon query over points | `geo_polygon` | Geometric query with relations |
| Complex lines or regions | Not suitable | Suitable |
| Common geographic Criteria | Supports several predicates | Typically requires Query DSL/native API |

Do not use Criteria's `GeoPolygon` on a `geo_shape` field assuming the same semantics as a `geo_polygon` query on `geo_point`. The two mapping types and query families serve different purposes.

## 11. Checking Mapping and Data Before Running Queries

If a geographic query returns no results, confirm the field is actually `geo_point`:

~~~http
GET /stores/_mapping?pretty
~~~

Inspect a document:

~~~http
GET /stores/_doc/store-1001
~~~

The document might contain:

~~~json
{
  "_source": {
    "name": "Central Store",
    "location": {
      "lat": 10.7769,
      "lon": 106.7009
    }
  }
}
~~~

Verify these factors:

- Is the field name actually `location`?
- Does the mapping have type `geo_point`?
- Are latitude and longitude in the right order in the data?
- Are coordinates within valid ranges?
- Is the query targeting the right index or alias?
- Is the radius in the right unit?
- Does the sample point actually fall inside the chosen region?

If the index was created before the entity mapping changed, new Java annotations do not automatically modify the old mapping. You may need to create a new index, migrate data, and switch aliases following a migration workflow.

## 12. Testing Geographic Queries

Create test data with locations inside and outside the target region. Example:

~~~java
Store nearby = new Store(
    "S-NEAR",
    "Nearby Store",
    true,
    "grocery",
    new GeoPoint(10.7770, 106.7010)
);

Store farAway = new Store(
    "S-FAR",
    "Far Store",
    true,
    "grocery",
    new GeoPoint(10.9000, 106.9000)
);
~~~

Write documents to the test index, then refresh the index before calling the Search API:

~~~java
operations.save(List.of(nearby, farAway));

IndexOperations indexOperations =
    operations.indexOps(Store.class);

indexOperations.refresh();
~~~

Create radius Criteria:

~~~java
GeoPoint center = new GeoPoint(10.7769, 106.7009);

Criteria criteria = new Criteria("location")
    .within(new GeoCircle(center, 1000));

Query query = new CriteriaQuery(criteria);

SearchHits<Store> hits =
    operations.search(query, Store.class);
~~~

Assertions should verify:

- `S-NEAR` is in the results.
- `S-FAR` is not in the results.
- No document missing `location` is returned as a valid point.
- Coordinates right near the radius boundary are handled according to expected rules.

Geographic search results depend on spherical distance and how Elasticsearch processes coordinates. Avoid picking test points right on the boundary unless tolerances and distance calculations are clearly verified. Use points clearly inside and outside first, then add separate boundary tests.

### 12.1. Refresh in Tests

Elasticsearch is a near-real-time system for Search. Newly indexed documents may not appear in queries until the next refresh.

In integration tests, you can call `indexOperations.refresh()` before searching. Do not force a refresh after every write in production; frequent refreshes degrade indexing performance.

## 13. Common Pitfalls

| Symptom | Possible cause | How to check |
|---|---|---|
| Criteria geo query fails on mapping | Field not declared as `geo_point` | Read the index mapping |
| No results even though coordinates look right | Swapped latitude/longitude or wrong index | Check `_source` and coordinate conventions |
| Too few results | Radius misinterpreted in wrong unit | Confirm meters vs. km |
| Too many results | Swapped longitude/latitude or overly large radius | Check center point and unit |
| `GeoCircle` constructor mismatch | Different Spring Data version | Check `GeoCircle` API of your dependency |
| Bounding box covers wrong area | Swapped top-left/bottom-right | Verify both corners and lat/lon order |
| Invalid polygon | Points out of order, self-intersecting, or unclosed boundary | Check point list |
| Nearest results do not appear first | Query only filters, no geo distance sort | Add `_geo_distance` sort via NativeQuery/client |
| Cannot use `geo_shape` | `geo_point` Criteria does not cover shape DSL | Use native query or Java API Client |
| Newly written test doc not found | Index not refreshed | Refresh index in test |
| Query runs slowly | Searching across too many indices/shards or overly wide region | Limit indices, bounding box, and result size |

## 14. API Selection Workflow

You can select how to build queries based on requirements:

1. If only finding points within a radius, use Criteria with `GeoCircle` if supported by your version.
2. If finding points inside a rectangle, use Criteria with `GeoBox`.
3. If finding points inside a polygon, use Criteria with `GeoPolygon`.
4. If combining geographic predicates with regular fields, join Criteria with AND/OR when logic is straightforward.
5. If needing `geo_shape`, distance sort, geographic aggregations, or DSL options not exposed by Criteria, use NativeQuery or the Elasticsearch Java API Client.
6. If dynamic index control is needed, pass `IndexCoordinates` to the appropriate `ElasticsearchOperations` overload.

API selection examples:

| Need | Implementation approach |
|---|---|
| Stores within 5 km | Criteria + `GeoCircle` |
| Points inside map viewport | Criteria + `GeoBox` |
| Points inside delivery zone | Criteria + `GeoPolygon` |
| Nearest points first | Geo query + `_geo_distance` sort |
| Complex area boundaries | `geo_shape` + native DSL |
| Count points within radius | `CriteriaQuery` + `operations.count` if query is supported |
| Search by location and status | Combine geographic Criteria with regular field conditions |

## 15. Performance and Geographic Data Notes

Geographic queries are still affected by shard count, index count, document count, and cluster load. Useful guidelines:

- Limit index scope whenever possible.
- Use bounding boxes to restrict viewports when appropriate.
- Cap the number of returned results.
- Fetch only needed fields if documents are large.
- Do not run geo queries on unnecessary indices.
- Use `geo_point` mapping for single-point location fields.
- Validate input data and reject invalid coordinates.
- Measure latency on production-scale data.

If a query finds stores near a point while requiring distance-sorted results, distinguish filtering cost from sorting cost. Do not fetch a large result set into Java to compute distances manually if Elasticsearch can handle the geo query/sort directly.

For requirements such as complex delivery zone shapes, evaluate `geo_shape` and geometry storage during mapping design. Converting discrete `geo_point` coordinates into a polygon at the application layer does not automatically provide geometric intersection semantics.

## 16. Quick Reference Table

| Purpose | Criteria / API |
|---|---|
| Declare geographic point | `@Field(type = FieldType.GeoPoint)` |
| Create a point | `new GeoPoint(latitude, longitude)` |
| Create CriteriaQuery | `new CriteriaQuery(criteria)` |
| Search within radius | `within(new GeoCircle(center, radius))` |
| Search within rectangle | `within(new GeoBox(topLeft, bottomRight))` |
| Search within polygon | `within(new GeoPolygon(points))` |
| Combine regular conditions | `Criteria.and(...)` / `Criteria.or(...)` |
| Execute query | `ElasticsearchOperations.search(query, Entity.class)` |
| Count results | `ElasticsearchOperations.count(query, Entity.class)` |
| Sort by distance | `_geo_distance` sort via native query/client |
| Complex geometry queries | `geo_shape` via native query/client |

CriteriaQuery supports common `geo_point` geographic queries such as radius, bounding box, and polygon, while allowing you to combine them with business conditions. Declare accurate mappings, standardize latitude/longitude order and distance units, verify regions with sample data, and switch to NativeQuery or the Elasticsearch Java API Client when `geo_shape`, distance sorting, aggregations, or advanced DSL options beyond Criteria are needed.
