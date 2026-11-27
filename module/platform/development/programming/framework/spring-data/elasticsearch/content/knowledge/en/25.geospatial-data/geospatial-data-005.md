# Bounding Boxes and Map Viewport Filtering

When users pan or zoom a map, an application often needs to fetch places inside the currently visible portion of the map. That visible area can be described by a geographic rectangle called a **bounding box**. Elasticsearch supports the **geo_bounding_box** query to find documents whose coordinates fall inside this rectangle.

In Spring Data Elasticsearch, location data is typically mapped to a **geo_point** field. The application can construct a bounding box condition using Query DSL and execute it via **ElasticsearchOperations**. When combining with business conditions such as status, place category, or access permissions, place those conditions inside **bool.filter** to filter results without computing a relevance score for each condition.

This lesson uses the **places** index, where each document contains a place name, category, status, and coordinates. It focuses on coordinate representation, configuring geo_point, building a bounding box from a map viewport, reading results, and handling edge cases such as invalid coordinates or map regions crossing the 180-degree meridian.

## 1. What is a bounding box?

A **bounding box** is a rectangle defined by two opposite corners:

- **Top-left**: northwest corner, with the larger latitude and typically the smaller longitude.
- **Bottom-right**: southeast corner, with the smaller latitude and typically the larger longitude.

For example, a map area covering a city center can be described by:

- Top-left: latitude 10.82, longitude 106.65.
- Bottom-right: latitude 10.75, longitude 106.72.

Conceptual diagram:

~~~text
                West                       East
                 |                          |
North         +--------------------------+  Top-left
              |                          |
              |        Target map        |
              |           area           |
              |                          |
South         +--------------------------+  Bottom-right
~~~

Any point whose coordinates fall inside this rectangle can be returned. The bounding box is usually obtained from the map's viewport—the geographic area currently visible on screen.

A bounding box is a rectangle in latitude and longitude. It is neither a fixed-radius circle nor an administrative boundary. Therefore:

- Use a bounding box when you want points within the currently displayed map region.
- Use geo_distance when you want points within a radius from a center point.
- Use geo_shape when you need relationships with polygons, lines, or complex geographic geometries.

## 2. geo_point and coordinate order

Elasticsearch uses the **geo_point** type to store a location consisting of latitude and longitude.

- **Latitude (lat)**: north-south position, ranging from -90 to 90.
- **Longitude (lon)**: east-west position, ranging from -180 to 180.

Example coordinates of a place:

~~~json
{
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
~~~

The object representation with explicit lat and lon properties helps readers tell the order apart clearly. Elasticsearch also accepts several other geo_point representations, though coordinate order depends on the format.

| Format | Example | Order |
|---|---|---|
| Object | {"lat": 10.7769, "lon": 106.7009} | Explicit lat and lon |
| String | "10.7769,106.7009" | Latitude, longitude |
| Array | [106.7009, 10.7769] | Longitude, latitude |
| GeoJSON point | {"type":"Point","coordinates":[106.7009,10.7769]} | Longitude, latitude |

This is a frequent source of bugs when pulling data from map libraries. Many JavaScript libraries represent coordinates in **[longitude, latitude]** order, while some Java APIs accept two parameters in **latitude, longitude** order.

When passing data between frontend, backend, and Elasticsearch, explicitly establish the convention at each boundary. Never guess coordinate order.

## 3. Declaring a geo_point field in Spring Data Elasticsearch

A place entity can use the **@GeoPointField** annotation to map a location property to geo_point.

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.GeoPointField;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Document(indexName = "places")
public class Place {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Keyword)
    private String status;

    @GeoPointField
    private GeoPoint location;

    public Place() {
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getCategory() {
        return category;
    }

    public void setCategory(String category) {
        this.category = category;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public GeoPoint getLocation() {
        return location;
    }

    public void setLocation(GeoPoint location) {
        this.location = location;
    }
}
~~~

In this example:

- **@Document(indexName = "places")** binds the entity to the places index.
- **@Id** marks the document ID.
- **@GeoPointField** designates the location field as geo_point.
- **GeoPoint** represents coordinates in Java.
- category and status are keyword because they are typically used for exact filtering.

Spring Data Elasticsearch's GeoPoint class holds latitude and longitude values. When instantiating it, pass parameters in the order required by your library version's constructor; the common API accepts latitude first, longitude second.

Example:

~~~java
GeoPoint location = new GeoPoint(10.7769, 106.7009);
~~~

Before deploying, verify the actual index mapping. Java annotations do not alter the mapping of an existing index automatically. If an old index declared location as text or keyword, create the right mapping through an index management workflow and reindex data as needed.

You can check the mapping via API:

~~~http
GET /places/_mapping
~~~

The expected mapping section looks like:

~~~json
{
  "properties": {
    "location": {
      "type": "geo_point"
    },
    "category": {
      "type": "keyword"
    },
    "status": {
      "type": "keyword"
    }
  }
}
~~~

If location is not geo_point, the geo_bounding_box query will not work as expected.

## 4. Building a bounding box from a map viewport

Mapping libraries typically provide viewport bounds when a user drags or zooms the map. These bounds usually consist of four values:

- North: northernmost latitude.
- South: southernmost latitude.
- East: easternmost longitude.
- West: westernmost longitude.

The backend might receive a request like:

~~~json
{
  "north": 10.82,
  "south": 10.75,
  "east": 106.72,
  "west": 106.65
}
~~~

From these values, construct the two corners:

~~~text
top_left     = (north, west)
bottom_right = (south, east)
~~~

An API payload can use clear field names:

~~~java
public record MapBounds(
        double north,
        double south,
        double east,
        double west
) {
}
~~~

Avoid sending an unnamed coordinate array if backend and frontend have not agreed on the ordering. An object with north/south/east/west prevents confusion during processing.

Some mapping libraries return getNorthEast() and getSouthWest(). When translating to the request:

- North comes from northeast's latitude.
- East comes from northeast's longitude.
- South comes from southwest's latitude.
- West comes from southwest's longitude.

Verify the data types used by your mapping library. Some use {lat, lng} objects, some use {lat, lon}, and some use [lng, lat] arrays.

## 5. geo_bounding_box query in Elasticsearch

The **geo_bounding_box** Query DSL finds documents whose geo_point falls inside the specified rectangle.

Example:

~~~http
POST /places/_search
{
  "query": {
    "geo_bounding_box": {
      "location": {
        "top_left": {
          "lat": 10.82,
          "lon": 106.65
        },
        "bottom_right": {
          "lat": 10.75,
          "lon": 106.72
        }
      }
    }
  }
}
~~~

Reading the query:

- **geo_bounding_box** is the geospatial query type.
- **location** is the geo_point field in the mapping.
- **top_left** is the northwest corner.
- **bottom_right** is the southeast corner.
- Documents with location inside this region are treated as matches.

Shorthand array or alternative object forms exist in Elasticsearch syntax, but objects with explicit lat/lon names are usually easier to inspect.

### A bounding box is a geometric condition

Elasticsearch evaluates point membership strictly by coordinates. It does not check whether a place belongs to a neighborhood, district, or administrative boundary in business terms.

For example, if a bounding box encloses an irregularly shaped region, points lying in the corners of the rectangle are still returned even though they may sit outside the desired zone boundary. When exact polygon boundary filtering is required, use a geo_shape query instead of a bounding box.

## 6. Combining bounding box with business conditions

A map screen rarely filters by location alone. Users may select place categories, statuses, or other filters. You can combine all of them inside **bool.filter**.

Example fetching only active restaurants inside the viewport:

~~~http
POST /places/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "geo_bounding_box": {
            "location": {
              "top_left": {
                "lat": 10.82,
                "lon": 106.65
              },
              "bottom_right": {
                "lat": 10.75,
                "lon": 106.72
              }
            }
          }
        },
        {
          "term": {
            "category": "restaurant"
          }
        },
        {
          "term": {
            "status": "ACTIVE"
          }
        }
      ]
    }
  }
}
~~~

The filters are combined with AND logic:

- Location must lie within the bounding box.
- category must equal restaurant.
- status must equal ACTIVE.

Filter context is appropriate because these are data-filtering criteria that do not require relevance scoring. You can add other criteria such as tenant, access permissions, operating hours, or service type into the same bool.filter.

Do not rely solely on frontend filtering. The backend must enforce business conditions and access permissions so clients cannot craft requests that bypass data restrictions.

## 7. Creating queries with StringQuery in Spring Data Elasticsearch

When using geo_bounding_box, you can pass Query DSL JSON via **StringQuery** and execute it with **ElasticsearchOperations**.

Example:

~~~java
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.StringQuery;

String dsl = """
{
  "bool": {
    "filter": [
      {
        "geo_bounding_box": {
          "location": {
            "top_left": {
              "lat": 10.82,
              "lon": 106.65
            },
            "bottom_right": {
              "lat": 10.75,
              "lon": 106.72
            }
          }
        }
      },
      {
        "term": {
          "status": "ACTIVE"
        }
      }
    ]
  }
}
""";

Query query = new StringQuery(dsl);

SearchHits<Place> hits = operations.search(
        query,
        Place.class,
        IndexCoordinates.of("places")
);
~~~

In this example:

- The JSON string contains the bool query clause.
- geo_bounding_box filters by position.
- term filters status.
- StringQuery wraps the DSL for Spring Data.
- operations.search executes against the places index.
- SearchHits holds the matched hits along with search metadata.

The string passed to StringQuery is a query clause. Do not pass a full search request body containing **query**, **from**, **size**, or **sort** keys when the constructor expects only the query JSON.

To add pagination, configure Pageable on the Query object if supported by your version's API:

~~~java
query.setPageable(PageRequest.of(0, 100));
~~~

Import PageRequest:

~~~java
import org.springframework.data.domain.PageRequest;
~~~

When returning map markers, you usually need to cap the number of points per request to avoid oversized responses. If a viewport holds tens of thousands of places, consider clustering or zoom-level aggregations instead of returning every marker at once.

## 8. Building dynamic queries from MapBounds

In real services, coordinates should not be hardcoded. The backend receives MapBounds, validates the values, and constructs the appropriate JSON query or query builder.

Input validation example:

~~~java
public void validateBounds(MapBounds bounds) {
    if (bounds == null) {
        throw new IllegalArgumentException("Bounds must not be null");
    }

    if (bounds.north() < -90 || bounds.north() > 90
            || bounds.south() < -90 || bounds.south() > 90) {
        throw new IllegalArgumentException("Latitude must be within [-90, 90]");
    }

    if (bounds.east() < -180 || bounds.east() > 180
            || bounds.west() < -180 || bounds.west() > 180) {
        throw new IllegalArgumentException("Longitude must be within [-180, 180]");
    }

    if (bounds.north() < bounds.south()) {
        throw new IllegalArgumentException("North must be greater than or equal to South");
    }
}
~~~

This is basic validation for an ordinary bounding box that does not cross the 180-degree meridian. Dateline crossings must be handled separately because west can be greater than east under normalized longitude representation.

After validation, you can construct JSON objects using a serializer instead of string concatenation:

~~~java
Map<String, Object> topLeft = Map.of(
        "lat", bounds.north(),
        "lon", bounds.west()
);

Map<String, Object> bottomRight = Map.of(
        "lat", bounds.south(),
        "lon", bounds.east()
);
~~~

Then assemble these two objects into the query structure and serialize using your application's JSON library. This avoids bracket, comma, and escaping errors when generating dynamic JSON.

If using the Java API Client, you can construct the query with typed builders. Exact builder syntax varies across Elasticsearch Java API Client versions; use the version managed by Spring Boot and check the project's API signatures. Whether using StringQuery or NativeQuery, the key is preserving top_left/bottom_right and lat/lon conventions.

## 9. Example service finding places within a viewport

A service can encapsulate bounds validation and query execution. The example below uses StringQuery to keep the DSL structure clear:

~~~java
import java.util.Locale;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.StringQuery;
import org.springframework.stereotype.Service;

@Service
public class PlaceSearchService {

    private static final IndexCoordinates PLACES =
            IndexCoordinates.of("places");

    private final ElasticsearchOperations operations;

    public PlaceSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<Place> findInViewport(MapBounds bounds) {
        validateBounds(bounds);

        String dsl = String.format(Locale.ROOT, """
        {
          "bool": {
            "filter": [
              {
                "geo_bounding_box": {
                  "location": {
                    "top_left": {
                      "lat": %f,
                      "lon": %f
                    },
                    "bottom_right": {
                      "lat": %f,
                      "lon": %f
                    }
                  }
                }
              }
            ]
          }
        }
        """,
                bounds.north(),
                bounds.west(),
                bounds.south(),
                bounds.east()
        );

        Query query = new StringQuery(dsl);

        return operations.search(query, Place.class, PLACES);
    }

    private void validateBounds(MapBounds bounds) {
        if (bounds == null
                || bounds.north() < -90
                || bounds.north() > 90
                || bounds.south() < -90
                || bounds.south() > 90
                || bounds.east() < -180
                || bounds.east() > 180
                || bounds.west() < -180
                || bounds.west() > 180
                || bounds.north() < bounds.south()) {
            throw new IllegalArgumentException("Invalid bounding box");
        }
    }
}
~~~

This example uses String.formatted to demonstrate substituting coordinate numbers into the query. In production code, use a JSON serializer or Java API Client builder for safer, more maintainable request construction. If you still format strings, pass only validated numeric values; never interpolate raw user-supplied text into JSON.

For regions crossing the 180-degree meridian, do not enforce west less than east as in an ordinary bounding box. Handle them separately following the dateline rules covered later.

## 10. Limiting marker count and paginating results

A viewport can contain a huge number of places. Returning every marker in a single response can cause:

- Large JSON payloads.
- Increased query and network transfer latency.
- Excessive marker rendering work on the frontend.
- Unusable maps with overlapping markers.
- High memory usage in both backend and browser.

You can cap the result count:

~~~java
Query query = new StringQuery(dsl);
query.setPageable(PageRequest.of(0, 500));
~~~

However, capping size means some places in the region will not be returned when total hits exceed the limit. The UI needs a clear policy:

- Indicate when results are truncated if possible.
- Use pagination or "load more" when users need the full list.
- Use clustering to group markers at low zoom levels.
- Return detailed markers only when zoomed in sufficiently.
- Use aggregations or grid-based clustering for large datasets.

If deep pagination is required, do not increase from indefinitely. For multi-page queries or large datasets, consider search_after with a stable sort or Point in Time as appropriate. Scroll is suited for batch exports, not continuous marker loading while users pan a map.

## 11. Combining bounding box with distance sorting

A bounding box returns all points within the rectangle. If you want to prioritize places near the center of the map, combine the geo filter with **geo_distance sort**.

Example:

~~~http
POST /places/_search
{
  "query": {
    "geo_bounding_box": {
      "location": {
        "top_left": {
          "lat": 10.82,
          "lon": 106.65
        },
        "bottom_right": {
          "lat": 10.75,
          "lon": 106.72
        }
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
        "unit": "km"
      }
    }
  ]
}
~~~

Here:

- geo_bounding_box restricts the target region.
- _geo_distance sorts points within that region by distance to the center.
- order asc places closer locations first.
- unit km requests distance units in kilometers.

This does not turn the bounding box into a circular radius. A point in the far corner of the rectangle is still returned if it lies inside the box; sorting only changes order.

If the requirement is to find every point within a 3 km radius, use a **geo_distance query**:

~~~json
{
  "query": {
    "geo_distance": {
      "distance": "3km",
      "location": {
        "lat": 10.7769,
        "lon": 106.7009
      }
    }
  }
}
~~~

Do not substitute a bounding box for geo_distance simply because both restrict location. Circles and rectangles cover different regions.

## 12. Bounding boxes and geo_shape

**geo_bounding_box** fits geo_point fields, where each document has a single point location. If a document represents a region with a polygon or line, the appropriate data type may be **geo_shape**.

Example of an area stored as a GeoJSON polygon:

~~~json
{
  "type": "Polygon",
  "coordinates": [
    [
      [106.65, 10.82],
      [106.72, 10.82],
      [106.72, 10.75],
      [106.65, 10.75],
      [106.65, 10.82]
    ]
  ]
}
~~~

GeoJSON uses **[longitude, latitude]** coordinate order. The polygon ring must be closed by repeating the first coordinate at the end.

If you need geometries intersecting the viewport, use a **geo_shape query** with an envelope shape:

~~~http
POST /areas/_search
{
  "query": {
    "geo_shape": {
      "boundary": {
        "shape": {
          "type": "envelope",
          "coordinates": [
            [106.65, 10.82],
            [106.72, 10.75]
          ]
        },
        "relation": "intersects"
      }
    }
  }
}
~~~

In a GeoJSON envelope:

- The first coordinate is the northwest corner [west, north].
- The second coordinate is the southeast corner [east, south].
- **intersects** finds geometries intersecting the envelope.

geo_shape relations can include intersects, within, contains, or disjoint depending on query type and mapping. Choose the relation based on business meaning. Do not use geo_bounding_box on polygons just because the query name says bounding box; use geo_shape when geometric relationships between shapes are needed.

## 13. Handling bounding boxes crossing the 180-degree meridian

Longitude is normally normalized between -180 and 180. When a user views an area near the international date line, the viewport may cross the 180-degree meridian.

For example, a region spanning part of the Pacific Ocean:

- West = 170.
- East = -170.

In this representation, west is numerically greater than east because the area crosses the dateline. This is not automatically an input error; it can be a valid bounding box on the globe.

Distinguish between:

- Normal box: west is less than or equal to east.
- Dateline-crossing box: west is greater than east.
- Box with north less than south: normally invalid data unless a special convention applies.

Elasticsearch supports longitude-handling rules when bounding boxes cross the dateline, though exact behavior should be verified for your version and query format. If the application wants explicit control, you can split the region into two boxes:

1. A box from west to 180 degrees.
2. A box from -180 degrees to east.

Then combine the two boxes with bool.should:

~~~json
{
  "query": {
    "bool": {
      "should": [
        {
          "geo_bounding_box": {
            "location": {
              "top_left": {
                "lat": 20,
                "lon": 170
              },
              "bottom_right": {
                "lat": -20,
                "lon": 180
              }
            }
          }
        },
        {
          "geo_bounding_box": {
            "location": {
              "top_left": {
                "lat": 20,
                "lon": -180
              },
              "bottom_right": {
                "lat": -20,
                "lon": -170
              }
            }
          }
        }
      ],
      "minimum_should_match": 1
    }
  }
}
~~~

This split represents the regions on both sides of the date line. If there are additional filters such as status or category, place them in an outer bool.filter so they apply to both branches.

Do not blindly sort west/east using min and max when crossing the dateline. Doing so can turn a small area around the 180-degree meridian into an area covering nearly the entire globe.

## 14. Validating coordinates and bounds on the backend

The frontend may send bounds from a map library, but the backend must still validate them. Basic checks:

- North and south must be within [-90, 90].
- East and west must be within [-180, 180].
- North must be greater than or equal to south.
- Reject NaN and Infinity.
- Reject null values if the endpoint requires all four edges.
- Cap region size if business rules disallow global searches.
- Handle dateline crossings explicitly rather than silently reordering longitudes.

Area size restrictions can use business rules such as a minimum zoom level or blocking overly wide viewports. Do not merely restrict decimal precision; validate geographic span and potential hit counts.

If the API accepts inputs from multiple clients, normalize inputs into an internal MapBounds type. Do not force services to know how each map library formats latitude/longitude.

## 15. Performance of geo_bounding_box

geo_bounding_box is generally well suited for filtering points within a viewport, though cost still depends on data scale and request patterns.

Factors to consider:

- Number of documents in the index.
- Number of shards and data distribution.
- Point density inside the selected region.
- Number of fields returned in _source.
- Response payload size.
- Additional filters.
- Distance-based sorting.
- Request frequency from the frontend as users pan/zoom.

A bounding box covering an entire country or the whole globe can match a huge number of documents. If the UI only needs markers for a small viewport, send accurate map bounds and cap results.

### Debouncing requests during pan and zoom

Do not send a search request for every single pixel moved. The frontend should wait briefly after panning/zooming stops before sending new bounds.

Typical flow:

~~~text
User pans or zooms map
             |
             v
      Update viewport
             |
             v
       Wait debounce
             |
             v
      Send new bounds
             |
             v
     Backend validates
             |
             v
  geo_bounding_box query
             |
             v
 Return markers in area
             |
             v
        Update map
~~~

If an older request is still running when the user changes the viewport, the frontend can abort the old request or ignore stale responses so markers from a previous viewport do not overwrite the new one. The backend can also rate-limit requests per user.

### Returning only required fields

If markers only need ID, name, and coordinates, use source filtering to shrink payloads:

~~~http
POST /places/_search
{
  "_source": [
    "name",
    "location",
    "category"
  ],
  "size": 500,
  "query": {
    "geo_bounding_box": {
      "location": {
        "top_left": {
          "lat": 10.82,
          "lon": 106.65
        },
        "bottom_right": {
          "lat": 10.75,
          "lon": 106.72
        }
      }
    }
  }
}
~~~

If the Place entity has large fields such as long descriptions or metadata, you do not need to return all of them for markers. You can map results to a dedicated map DTO or projection.

## 16. Clustering and aggregation when there are too many points

At low zoom levels, thousands of markers can overlap. Returning every point does not help the user understand the map. Instead, you can group points into grid clusters or use geo aggregations.

One option is **geotile_grid aggregation**, which groups geo_point locations into map tiles at a given zoom level:

~~~http
POST /places/_search
{
  "size": 0,
  "query": {
    "geo_bounding_box": {
      "location": {
        "top_left": {
          "lat": 10.82,
          "lon": 106.65
        },
        "bottom_right": {
          "lat": 10.75,
          "lon": 106.72
        }
      }
    }
  },
  "aggs": {
    "clusters": {
      "geotile_grid": {
        "field": "location",
        "precision": 7
      },
      "aggs": {
        "center": {
          "geo_centroid": {
            "field": "location"
          }
        }
      }
    }
  }
}
~~~

In this example:

- The query filters points inside the viewport.
- **geotile_grid** divides the area into cells according to the tile system.
- **precision** determines cell granularity.
- **geo_centroid** calculates the average center of points in each bucket.
- **size: 0** skips the hit list and returns only aggregations.

Higher precision creates more smaller cells; lower precision creates fewer larger cells. You can select precision based on the map's zoom level. However, aggregations have bucket limits and their own costs, so control result size and bucket count.

A mapping system can use two modes:

- Low zoom: return clusters/buckets.
- High zoom: return detailed markers within the bounding box.

This is a presentation and performance decision, not a change in the semantics of geo_bounding_box.

## 17. Reading SearchHits and converting to markers

When using ElasticsearchOperations, **SearchHits<Place>** holds the mapped results. Each **SearchHit<Place>** provides the entity and hit metadata.

Example:

~~~java
SearchHits<Place> hits = operations.search(
        query,
        Place.class,
        IndexCoordinates.of("places")
);

List<PlaceMarker> markers = hits.getSearchHits().stream()
        .map(SearchHit::getContent)
        .map(place -> new PlaceMarker(
                place.getId(),
                place.getName(),
                place.getLocation().getLat(),
                place.getLocation().getLon()
        ))
        .toList();
~~~

Marker DTO:

~~~java
public record PlaceMarker(
        String id,
        String name,
        double latitude,
        double longitude
) {
}
~~~

If SearchHits has no results, the marker list will be empty. That is normal when the viewport contains no matching places.

When constructing DTOs, ensure location is not null. Data may lack coordinates if older documents were written before location became mandatory. Filter or handle documents missing location according to business rules; do not call getLat/getLon on null values.

If the frontend expects GeoJSON, convert to the proper [longitude, latitude] order:

~~~json
{
  "type": "Feature",
  "geometry": {
    "type": "Point",
    "coordinates": [106.7009, 10.7769]
  },
  "properties": {
    "id": "place-1001",
    "name": "Central Place"
  }
}
~~~

Do not return [latitude, longitude] in GeoJSON because that order violates the GeoJSON coordinate standard.

## 18. Does a bounding box include its boundaries?

A bounding box defines a rectangular region by its edges. Points lying directly on an edge may need consistent handling across mapping libraries, Elasticsearch, and business logic.

When testing, create points that are:

- Strictly inside the box.
- Outside to the north.
- Outside to the south.
- Outside to the east.
- Outside to the west.
- Directly on each edge.
- Directly at the four corners.

This confirms how Elasticsearch handles boundary coordinates under your mapping and version. If business logic demands a specific boundary rule, document it explicitly in the API and tests; do not rely on frontend coordinate rounding.

Do not arbitrarily add or subtract an epsilon to bounds to "compensate for error." That can unintentionally enlarge or shrink the query region. If coordinate rounding is needed, use consistent precision on both client and server.

## 19. Testing bounding boxes

You can test bounds logic with unit tests and query behavior with integration tests.

### Unit test for creating bounds

Example checking conversion from four edges to two corners:

~~~java
@Test
void createsTopLeftAndBottomRightFromViewport() {
    MapBounds bounds = new MapBounds(
            10.82,
            10.75,
            106.72,
            106.65
    );

    assertEquals(10.82, bounds.north());
    assertEquals(10.75, bounds.south());
    assertEquals(106.72, bounds.east());
    assertEquals(106.65, bounds.west());
}
~~~

### Bounds validation test

~~~java
@Test
void rejectsLatitudeOutsideValidRange() {
    MapBounds bounds = new MapBounds(
            95,
            10.75,
            106.72,
            106.65
    );

    assertThrows(
            IllegalArgumentException.class,
            () -> validator.validate(bounds)
    );
}
~~~

### Integration test with Elasticsearch

Create an index with location mapped as geo_point and insert documents at coordinates:

- A point inside the box.
- A point outside the box.
- A point on the boundary.
- A document without location if the mapping permits it.

Then execute the geo_bounding_box query and assert the returned IDs. Integration tests must run against an Elasticsearch version compatible with the project's Spring Data Elasticsearch; mocking repositories cannot verify actual cluster geospatial behavior.

## 20. Common mistakes when filtering by map viewport

| Symptom | Possible cause | Resolution |
|---|---|---|
| Query fails saying field is not geo_point | location is mapped as text or keyword | Inspect mapping and create an index with the right type |
| Point at right location is not found | Swapped lat/lon when saving or querying | Check coordinate conventions in frontend, Java, and JSON |
| Results appear outside visible area | Wrong bounds sent or north/south/east/west mixed up | Inspect viewport values and the two corners |
| Query returns too many markers | Bounding box too wide or low zoom | Cap size, cluster, or use geotile aggregation |
| Query returns too few markers | Bounds shrunk, edges swapped, or bad rounding | Log validated bounds and test boundary coordinates |
| New place does not appear yet | Index not refreshed after write | Review refresh policy and near-real-time behavior |
| Place missing coordinates causes DTO error | Null location in some documents | Check for null and handle missing data |
| Dateline-crossing region behaves wrongly | Treated west/east like a normal box | Support longitude wrap or split into two boxes |
| Used bounding box when wanting polygon filter | Rectangles do not match real boundaries | Use geo_shape with a polygon |
| Used bounding box to search within radius | Rectangles differ from circles | Use geo_distance query |
| Frontend renders markers in wrong spots | GeoJSON received wrong coordinate order | Output coordinates as [longitude, latitude] |
| Request spikes while dragging map | Query sent on every small viewport change | Debounce, cancel stale requests, and rate-limit |

## 21. Workflow for implementing viewport filtering

When building a feature to find places within a map region, follow this sequence:

1. **Choose the data model.** Use geo_point for point locations; use geo_shape for polygons or complex geometries.
2. **Declare the mapping.** Ensure the location field is indexed with the right type.
3. **Standardize coordinate conventions.** Define the order used by frontend, backend, and Elasticsearch.
4. **Read viewport bounds.** Obtain north, south, east, and west from the mapping library.
5. **Validate inputs.** Check lat/lon ranges, edge ordering, and dateline crossings.
6. **Build geo_bounding_box.** Place top_left and bottom_right into Query DSL.
7. **Combine business filters.** Add category, status, tenant, or access permissions into bool.filter.
8. **Bound the response.** Use sensible size limits, source filtering, or clustering.
9. **Convert results to markers.** Ensure GeoJSON coordinates follow [longitude, latitude].
10. **Optimize interaction.** Debounce requests, handle stale responses, and monitor latency.
11. **Test boundaries.** Verify points inside, outside, on edges, and across the dateline.
12. **Monitor production.** Measure hit counts, payloads, query times, and viewport request rates.

geo_bounding_box is a straightforward way to retrieve documents whose geo_point falls inside a viewport's rectangular area. In Spring Data Elasticsearch, map the location field properly, translate bounds into top_left/bottom_right with accurate latitude and longitude order, and combine additional conditions inside bool.filter. Bounding boxes suit map-viewport marker loading; when radius search is needed, use geo_distance, and when polygon boundary filtering is needed, use geo_shape. With large datasets, cap hit counts or use clustering so the map UI stays fast and usable.