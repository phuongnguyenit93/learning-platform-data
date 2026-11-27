# Longitude, Latitude, Distance Units, and Coordinate-Swapping Bugs

When storing and searching locations in Elasticsearch, the two values that must be properly understood are **latitude** and **longitude**. Elasticsearch uses geographic coordinates in WGS 84 and represents positions in decimal degrees. A common bug is swapping the order of latitude and longitude when transferring data between Java, JSON, GeoJSON, databases, or mapping APIs. This error is sometimes rejected immediately because a coordinate exceeds valid bounds, yet it can also silently produce a completely different location without raising an exception.

In Spring Data Elasticsearch, the GeoPoint type takes latitude before longitude. Meanwhile, Elasticsearch arrays, GeoJSON, and WKT generally use longitude before latitude. Distance units must also be declared consistently: geo queries typically accept distance as a string like 5km, whereas geo distance sorts have a separate unit parameter. This lesson explains the coordinate system, coordinate order per format, how to convert and validate data, how to choose distance units, and how to avoid coordinate-swapping bugs.

## 1. What are latitude and longitude?

Geographic coordinates locate a point on the Earth's surface using two components:

- **Latitude:** North or South position relative to the equator.
- **Longitude:** East or West position relative to the Greenwich prime meridian.

Valid ranges:

| Component | Valid range | Sign meaning |
|---|---:|---|
| Latitude | -90 to +90 degrees | North is positive, South is negative |
| Longitude | -180 to +180 degrees | East is positive, West is negative |

Some examples:

| Place | Latitude | Longitude |
|---|---:|---:|
| Ho Chi Minh City, approximate center | 10.7769 | 106.7009 |
| Hanoi, approximate center | 21.0278 | 105.8342 |
| New York, approximate Manhattan | 40.7128 | -74.0060 |
| Sydney, approximate center | -33.8688 | 151.2093 |

The values above are approximate coordinate examples and do not represent a specific street address. For Vietnam, latitude is typically positive because it lies in the Northern Hemisphere, and longitude is typically positive because it lies in the Eastern Hemisphere.

### 1.1. Decimal degrees

Elasticsearch accepts coordinates in degrees. For example:

~~~json
{
  "lat": 10.7769,
  "lon": 106.7009
}
~~~

This is the decimal degrees format. Do not pass radians or projected meter values into a geo_point field.

If a data source provides degrees-minutes-seconds (DMS), convert it to decimal degrees:

~~~text
decimal degrees = degrees + minutes / 60 + seconds / 3600
~~~

Then apply a negative sign if the direction is South (S) or West (W). For example, 10°46'36.8"N equals roughly 10.7769 degrees North. Do not take the absolute value of South/West coordinates, as doing so moves the location to the opposite hemisphere.

### 1.2. Coordinate reference system

Elasticsearch geo_point uses the WGS 84 geographic coordinate system (EPSG:4326). GPS, GeoJSON, and many popular mapping APIs also exchange coordinates in WGS 84.

Some GIS data sources may use a projected coordinate system such as UTM or a local datum such as VN-2000. Those values are typically represented as planar coordinates in meters, not latitude/longitude in degrees. They must be transformed to WGS 84 before writing to geo_point.

You cannot convert a CRS simply by renaming two X/Y columns to latitude/longitude. You must apply a coordinate transformation appropriate to the source data's zone, projection, datum, and parameters. Using the wrong CRS transformation can shift results by hundreds of meters or several kilometers even when both numbers remain within valid numeric ranges.

## 2. Coordinate order depends on format

This is the most important rule when working with geo_point:

| Format | Example | Order |
|---|---|---|
| JSON object | {"lat": 10.7769, "lon": 106.7009} | Explicitly named lat and lon |
| Elasticsearch string | "10.7769,106.7009" | latitude, longitude |
| Elasticsearch array | [106.7009, 10.7769] | longitude, latitude |
| GeoJSON Point | {"type":"Point","coordinates":[106.7009,10.7769]} | longitude, latitude |
| WKT Point | "POINT (106.7009 10.7769)" | longitude, latitude |
| Spring Data GeoPoint | new GeoPoint(10.7769, 106.7009) | latitude, longitude |
| Spring Data GeoJsonPoint | GeoJsonPoint.of(106.7009, 10.7769) | longitude, latitude |
| Geohash | "w3gvk" | Encoded location, no lat/lon pair passed |

There is no single ordering rule that applies to every API. Check the exact format rather than inferring from variable names or element positions.

### 2.1. Object form: clear and easy to inspect

This is the preferred form when constructing JSON manually:

~~~json
{
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
~~~

Property names help prevent confusion. When reading code, you can immediately see which number is latitude and which is longitude.

### 2.2. String form

Elasticsearch accepts a latitude,longitude string:

~~~json
{
  "location": "10.7769,106.7009"
}
~~~

This string uses latitude before longitude, unlike arrays and GeoJSON. Consequently, splitting this string on a comma into an array while keeping the same order is a common bug.

### 2.3. Array form

Arrays use longitude,latitude order:

~~~json
{
  "location": [106.7009, 10.7769]
}
~~~

The first element is longitude (x), and the second element is latitude (y). This follows the GeoJSON coordinate convention and is also common in many mapping libraries.

### 2.4. GeoJSON

A GeoJSON Point has the structure:

~~~json
{
  "type": "Point",
  "coordinates": [106.7009, 10.7769]
}
~~~

GeoJSON defines coordinates in x, y order, corresponding to longitude, latitude for geographic coordinates. Do not switch to [latitude, longitude] just because most Java APIs use constructors taking latitude first.

### 2.5. WKT

Well-Known Text also uses x, y order:

~~~text
POINT (106.7009 10.7769)
~~~

In a geographic WKT Point, the first value is longitude and the second value is latitude. Geometries such as LINESTRING and POLYGON use the same coordinate order for each pair.

## 3. Representing coordinates in Spring Data Elasticsearch

Spring Data Elasticsearch provides GeoPoint in the org.springframework.data.elasticsearch.core.geo package. Its constructor takes latitude first, longitude second:

~~~java
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

GeoPoint location = new GeoPoint(10.7769, 106.7009);
~~~

Read the constructor order as:

~~~text
new GeoPoint(latitude, longitude)
              10.7769, 106.7009
~~~

You can use GeoPoint as an entity property:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.GeoPointField;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;

@Document(indexName = "places")
public class Place {

    @Id
    private String id;

    private String name;

    @GeoPointField
    private GeoPoint location;

    public Place() {
    }

    public Place(String id, String name, double latitude, double longitude) {
        this.id = id;
        this.name = name;
        this.location = new GeoPoint(latitude, longitude);
    }

    public GeoPoint getLocation() {
        return location;
    }
}
~~~

The @GeoPointField annotation indicates that the property maps to an Elasticsearch geo_point. You can inspect the mapping after creating the index:

~~~http
GET places/_mapping
~~~

The output should show the location field having type geo_point. If the index already exists with a different mapping, changing annotations in Java does not automatically fix the index mapping; you must create a new index and migrate data if the field type needs to change.

### 3.1. GeoJsonPoint uses a different order

When working with GeoJSON, Spring Data provides GeoJsonPoint. Its factory method takes x first and y second, corresponding to longitude then latitude:

~~~java
import org.springframework.data.elasticsearch.core.geo.GeoJsonPoint;

GeoJsonPoint point = GeoJsonPoint.of(106.7009, 10.7769);
~~~

Comparing the two:

~~~java
GeoPoint geoPoint = new GeoPoint(10.7769, 106.7009);
GeoJsonPoint geoJsonPoint = GeoJsonPoint.of(106.7009, 10.7769);
~~~

Both objects represent the exact same location. The difference lies in the API parameter order. Do not alter the order just to make two lines of code look alike.

## 4. Writing coordinates to Elasticsearch

With the REST API, the object form expresses the meaning clearly:

~~~http
PUT places/_doc/place-1
{
  "name": "Central Store",
  "location": {
    "lat": 10.7769,
    "lon": 106.7009
  }
}
~~~

With Spring Data Elasticsearch:

~~~java
Place place = new Place(
        "place-1",
        "Central Store",
        10.7769,   // latitude
        106.7009   // longitude
);

placeRepository.save(place);
~~~

Spring Data uses mapping metadata and converters to translate GeoPoint into Elasticsearch data. The application should keep clear variable names, such as latitude and longitude, instead of using lat1, x, y, or coordinate1 without an explicit convention.

## 5. Distance units

Latitude and longitude are stored in degrees. Geographic distances are calculated and returned in units of length such as meters or kilometers. Do not confuse coordinate units with distance units:

- Latitude/longitude: angular degrees.
- Distance: meters, kilometers, miles, or other length units.

Common units in Elasticsearch:

| Unit | Symbol |
|---|---|
| Millimeter | mm |
| Centimeter | cm |
| Meter | m |
| Kilometer | km |
| Inch | in |
| Feet | ft |
| Yard | yd |
| Mile | mi |
| Nautical mile | nmi |

Some conversions:

| Conversion | Value |
|---|---:|
| 1 kilometer | 1,000 meters |
| 1 mile | 1,609.344 meters |
| 1 nautical mile | 1,852 meters |
| 1 meter | 100 centimeters |
| 1 kilometer | approximately 0.621371 miles |

If no unit is specified in a geo distance sort, Elasticsearch defaults to meters. In your application, keep units consistent from queries through DTOs to the display UI.

### 5.1. Distance in a geo_distance query

A geo distance query accepts distance in the distance property. You can pass a number with a unit in a single string:

~~~http
GET places/_search
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

The query above selects documents whose location lies within a 5 km radius of the reference point. You can use 5000m instead of 5km; both representations specify the same length.

A few other examples:

~~~json
{
  "distance": "500m"
}
~~~

~~~json
{
  "distance": "3mi"
}
~~~

~~~json
{
  "distance": "2nmi"
}
~~~

The distance value must include a supported unit or use the API's default unit. In application code, always specify the unit explicitly so readers do not have to guess.

### 5.2. Unit in a geo distance sort

Geo distance sort uses a separate unit property:

~~~http
GET places/_search
{
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

Here unit: km specifies the unit for the sort value. The closest document comes first because order is asc. If unit is omitted, the sort value defaults to meters.

In Spring Data Elasticsearch, GeoDistanceOrder allows specifying the unit:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.core.geo.GeoPoint;
import org.springframework.data.elasticsearch.core.query.GeoDistanceOrder;

GeoDistanceOrder distanceOrder = new GeoDistanceOrder(
        "location",
        new GeoPoint(10.7769, 106.7009))
        .with(Sort.Direction.ASC)
        .withUnit("km");
~~~

GeoDistanceOrder's constructor takes a property and a GeoPoint. GeoPoint still uses latitude, longitude order; withUnit simply selects the distance unit.

## 6. Distinguishing geographic distance from travel distance

Elasticsearch geo_distance computes direct geographic distance between coordinates, commonly understood as straight-line ("as the crow flies") distance on the Earth's surface. This is not road distance, driving time, or walking distance.

For example, two places may be 2 km apart in a straight line but require detouring across a river, one-way streets, or areas without bridges, making the actual route much longer.

Choose the tool according to the requirement:

| Requirement | Approach |
|---|---|
| Find places within a 5 km radius | Elasticsearch geo_distance |
| Rank stores closest to the user in a straight line | Elasticsearch _geo_distance sort |
| Compute driving or walking distance | Routing/directions service |
| Estimate travel time | Routing service with road and transport data |
| Find intersecting geographic regions | geo_shape query |

Do not use geo_distance results to display driving distance if the application has not calculated a route.

## 7. Swapping latitude and longitude

Suppose the correct location is:

~~~text
latitude  = 10.7769
longitude = 106.7009
~~~

In the Spring Data constructor, the right way is:

~~~java
new GeoPoint(10.7769, 106.7009);
~~~

If swapped:

~~~java
new GeoPoint(106.7009, 10.7769);
~~~

then latitude becomes 106.7009, exceeding the -90 to 90 range. The data is typically rejected or throws an error during write/conversion.

### 7.1. Coordinate swaps that remain numerically valid

Not every coordinate swap is caught by range validation.

For example, a location near New York:

~~~text
Correct:   latitude = 40.7128, longitude = -74.0060
Incorrect: latitude = -74.0060, longitude = 40.7128
~~~

Both latitude and longitude values in the incorrect case still fall within allowed ranges. Elasticsearch can accept the wrong coordinates and store them as a valid location elsewhere on Earth.

Therefore, checking latitude within [-90, 90] and longitude within [-180, 180] is not enough to catch all coordinate swaps. You also need checks against the expected geographic region, data sources, and known sample locations.

### 7.2. Why is this bug hard to spot?

A coordinate swap may not raise an exception because:

- Both numbers still lie within valid ranges.
- The JSON remains syntactically valid.
- The mapping is still geo_point.
- Elasticsearch still computes distances to the wrong location.
- Queries still return results, just with incorrect ordering or geographic coverage.

Symptoms often look like the nearest store being in another city/country, searches around the user's location returning empty results, or unusually large distances.

### 7.3. Places where order is easily reversed

- Reading database columns with longitude before latitude and passing them to GeoPoint in the same order.
- Converting a GeoJSON array [lon, lat] into a GeoPoint constructor without swapping.
- Calling GeoJsonPoint.of with lat, lon order instead of lon, lat.
- Splitting a "lat,lon" string and treating it like a [lon,lat] array.
- Reading x/y values from a GIS library while assuming x is latitude.
- Using a DTO with two unnamed number fields.
- Copying coordinates from an API with a different order without reading the documentation.

## 8. Validating coordinates at the application boundary

Validate coordinates before creating entities or calling Elasticsearch. Example of a Java value object:

~~~java
public record GeographicCoordinates(
        double latitude,
        double longitude) {

    public GeographicCoordinates {
        if (!Double.isFinite(latitude) || !Double.isFinite(longitude)) {
            throw new IllegalArgumentException("Coordinates must be finite numbers");
        }

        if (latitude < -90.0 || latitude > 90.0) {
            throw new IllegalArgumentException("Latitude must be between -90 and 90");
        }

        if (longitude < -180.0 || longitude > 180.0) {
            throw new IllegalArgumentException("Longitude must be between -180 and 180");
        }
    }

    public org.springframework.data.elasticsearch.core.geo.GeoPoint toGeoPoint() {
        return new org.springframework.data.elasticsearch.core.geo.GeoPoint(
                latitude,
                longitude);
    }
}
~~~

This value object ensures parameter names and constructor always follow latitude, longitude order. It also rejects NaN and Infinity, which are not valid geographic coordinates.

### 8.1. Checking the business geographic region

For an application serving only a specific region, you can check whether coordinates fall within that region's bounding box. Example illustrating an area covering Southern Vietnam:

~~~java
public static boolean isWithinExpectedRegion(GeographicCoordinates point) {
    return point.latitude() >= 8.0
            && point.latitude() <= 13.0
            && point.longitude() >= 102.0
            && point.longitude() <= 110.0;
}
~~~

This is only a preliminary bounding box check, not an exact administrative boundary. In a real system, use a polygon or geofence matching the business region if exact verification is required.

Do not automatically swap coordinates when encountering an out-of-range value. Return a validation error and ask to fix the data source. Automatic swapping can make corrupted data harder to trace and still fails to detect cases where both values are in valid ranges.

### 8.2. Order cannot be inferred from two numbers alone

If you receive two unnamed numbers such as:

~~~json
{
  "x": 40.7128,
  "y": -74.0060
}
~~~

you cannot know for sure whether x is latitude or longitude without an API contract. Design DTOs with explicit names:

~~~json
{
  "latitude": 40.7128,
  "longitude": -74.0060
}
~~~

For GeoJSON, follow the coordinates [longitude, latitude] rule. Do not reuse a single DTO structure for both conventions without explicit conversion.

## 9. Safe conversion between formats

When converting from a Java object to a JSON object, keep the field names:

~~~java
GeoPoint point = new GeoPoint(latitude, longitude);
~~~

When converting to an array/GeoJSON, swap the order deliberately:

~~~java
double[] coordinates = {
        point.getLon(),
        point.getLat()
};
~~~

This snippet illustrates the intent of the conversion: GeoJSON arrays are longitude first, latitude second. Check the accessor names in the exact Spring Data version you use when implementing directly.

A clearly named conversion function reduces the risk of mistakes:

~~~java
public static double[] toGeoJsonCoordinates(GeographicCoordinates point) {
    return new double[] {
            point.longitude(),
            point.latitude()
    };
}
~~~

And converting back from a GeoJSON array:

~~~java
public static GeographicCoordinates fromGeoJsonCoordinates(double[] coordinates) {
    if (coordinates == null || coordinates.length < 2) {
        throw new IllegalArgumentException("GeoJSON Point needs [longitude, latitude]");
    }

    return new GeographicCoordinates(
            coordinates[1],
            coordinates[0]);
}
~~~

These two functions encode the ordering convention right in their names and implementations, rather than relying on each caller to remember it.

## 10. Using coordinates in a geo_distance query

When searching for places within a radius, pass the reference coordinates in object format to avoid confusion:

~~~http
GET places/_search
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

Spring Data Elasticsearch can build the corresponding query using Criteria:

~~~java
import org.springframework.data.elasticsearch.core.geo.GeoPoint;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

GeoPoint origin = new GeoPoint(10.7769, 106.7009);

Criteria criteria = Criteria.where("location")
        .within(origin, "5km");

CriteriaQuery query = new CriteriaQuery(criteria);
~~~

In the example, GeoPoint takes latitude before longitude; the string "5km" specifies the radius. Criteria expresses the search condition, while Elasticsearch performs the distance calculation.

## 11. Using coordinates in a geo distance sort

If you need results sorted nearest-first, declare the sort separately:

~~~http
GET places/_search
{
  "query": {
    "match_all": {}
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

Both places use the same reference coordinates and the same ordering convention:

- Geo distance query: distance: "5km" to limit the radius.
- Geo distance sort: unit: "km" to return sort values in kilometers.

Query and sort can be combined when you want both radius filtering and nearest-first ordering. Sorting alone does not filter out distant locations.

## 12. Arc, plane, and the meaning of distance

Elasticsearch supports two common distance types for geo distance sorting:

| Distance type | Meaning |
|---|---|
| arc | Computes distance along an arc on the Earth's surface; default and more accurate |
| plane | Uses a planar approximation; can be faster over small areas, but error increases at long distances or near the poles |

Example:

~~~json
{
  "_geo_distance": {
    "location": [106.7009, 10.7769],
    "order": "asc",
    "unit": "km",
    "distance_type": "arc"
  }
}
~~~

For searching stores, hospitals, or services around users, generally keep arc. Only use plane after benchmarking performance and confirming that the deviation is acceptable.

Geo distance is computed as geographic distance, not travel along a street network. If the UI requires driving distance or travel time, use a routing service.

## 13. Unit-related mistakes

### 13.1. Using meters but displaying kilometers

If a sort does not set unit, the sort value defaults to meters. Displaying that raw number directly with a km label in the UI inflates the distance by 1,000 times.

For example, a value of 2,400 meters must be displayed as 2.4 km if you want kilometers. It is better to declare unit: km in the sort and keep the DTO contract consistent.

### 13.2. Confusing coordinate units with distance units

Latitude/longitude are never stored in kilometers or meters. They are angular degrees. Only distance results carry length units.

### 13.3. Sending radians instead of degrees

Elasticsearch geo_point expects coordinates in degrees. If a data source uses radians, convert to degrees before writing:

~~~text
degrees = radians * 180 / pi
~~~

Do not convert coordinates from degrees to radians just because another calculation library uses radians.

### 13.4. Using locale-specific decimal commas

JSON numbers use a decimal point:

~~~json
{
  "lat": 10.7769,
  "lon": 106.7009
}
~~~

Do not write 10,7769 as a decimal number in JSON. The comma is an element/property separator, not a decimal separator. When parsing locale-formatted data, convert to a numeric value before serializing JSON.

### 13.5. Inconsistent units between query and response

If a geo_distance query uses 5km while a geo distance sort returns meters, filtering still works, but DTOs may display wrong values if they assume both share the same unit. Explicitly declare and track the unit for sort values.

## 14. Investigating bad coordinate data

When suspecting swapped or shifted coordinates, check step by step:

1. Inspect the field names and API contract of the coordinate source.
2. Confirm whether the CRS is WGS 84 or another projection.
3. Check that latitude is within [-90, 90] and longitude is within [-180, 180].
4. Compare sample coordinates against known locations or a reliable map.
5. Check the order of JSON objects, arrays, GeoJSON, or WKT.
6. Check whether Java constructors and mappers swap order properly.
7. Check distance query units and sort value units.
8. Run a query around a known reference point and confirm results fall in the right area.
9. Inspect the Elasticsearch mapping and document _source.
10. Fix at the source or conversion step, then reindex corrupted data if needed.

You can inspect a document:

~~~http
GET places/_doc/place-1
~~~

Check the mapping:

~~~http
GET places/_mapping
~~~

If _source contains the right numbers but the map displays the wrong position, inspect coordinate order in the consumer or frontend. If _source itself is wrong, inspect ingest/DTO/converters before data is written.

## 15. Designing clear DTOs and APIs

Avoid APIs accepting two unnamed numbers:

~~~java
public record LocationRequest(double first, double second) {
}
~~~

Prefer:

~~~java
public record LocationRequest(
        double latitude,
        double longitude) {
}
~~~

If the API needs GeoJSON, follow the standard GeoJSON structure:

~~~json
{
  "type": "Point",
  "coordinates": [106.7009, 10.7769]
}
~~~

When converting from LocationRequest to GeoJSON, write an explicit mapper:

~~~java
public static double[] toGeoJson(LocationRequest request) {
    return new double[] {
            request.longitude(),
            request.latitude()
    };
}
~~~

Meaningful field names help API callers and code maintainers recognize order without guessing. For systems with multiple data sources, document the CRS, units, and coordinate order in the API contract.

## 16. Testing coordinates and distances

Test both Java-side validation and actual results on Elasticsearch.

### 16.1. Unit tests for coordinate ranges

~~~java
@Test
void rejectsLatitudeOutsideValidRange() {
    assertThatThrownBy(() ->
            new GeographicCoordinates(106.7009, 10.7769))
            .isInstanceOf(IllegalArgumentException.class);
}

@Test
void acceptsValidLatitudeAndLongitude() {
    GeographicCoordinates point =
            new GeographicCoordinates(10.7769, 106.7009);

    assertThat(point.latitude()).isEqualTo(10.7769);
    assertThat(point.longitude()).isEqualTo(106.7009);
}
~~~

The first test catches a swap that pushes latitude out of bounds. However, also add a test for a swapped pair where both values remain valid, since numeric range validation cannot catch that scenario.

### 16.2. Unit test for GeoJSON order

~~~java
@Test
void convertsLatitudeLongitudeToGeoJsonOrder() {
    GeographicCoordinates point =
            new GeographicCoordinates(10.7769, 106.7009);

    double[] coordinates = toGeoJsonCoordinates(point);

    assertThat(coordinates).containsExactly(106.7009, 10.7769);
}
~~~

This test confirms the first array element is longitude and the second is latitude.

### 16.3. Integration test with Elasticsearch

With a real Elasticsearch cluster or Testcontainers, you should:

- Create an index with a geo_point field.
- Write a few documents at known coordinates.
- Search within a radius that has an explicit unit.
- Sort ascending and verify the nearest place comes first.
- Read the sort value and confirm its unit.
- Test a document missing coordinates.
- Test out-of-range data and confirm ingestion is rejected as configured.

Do not only mock the repository if your goal is to verify that Elasticsearch computes geo distances and sorting accurately. Integration tests catch mapping, converter, and coordinate-order errors in real requests.

## 17. Checklist to prevent coordinate-swapping bugs

Before sending location data into Elasticsearch, verify:

- [ ] Data source uses WGS 84 or has been accurately CRS-transformed.
- [ ] Latitude is the North/South value, within [-90, 90].
- [ ] Longitude is the East/West value, within [-180, 180].
- [ ] Java GeoPoint is constructed with new GeoPoint(latitude, longitude).
- [ ] GeoJSON and arrays use [longitude, latitude].
- [ ] Elasticsearch lat,lon strings are parsed in the right order.
- [ ] Negative signs for South/West coordinates are preserved.
- [ ] Coordinates use decimal degrees, not radians or meters.
- [ ] Distance queries include a unit such as 5km.
- [ ] Geo distance sorts declare unit explicitly.
- [ ] DTOs explicitly name latitude and longitude.
- [ ] Tests cover swapped coordinates where both numbers remain in valid ranges.

## 18. Summary

Elasticsearch geo_point uses WGS 84 geographic coordinates in decimal degrees. Latitude ranges within [-90, 90], and longitude ranges within [-180, 180]. Coordinate order depends on format: JSON objects specify lat/lon explicitly; Elasticsearch strings use latitude,longitude; arrays, GeoJSON, and WKT use longitude,latitude. The Spring Data GeoPoint constructor takes latitude before longitude, while GeoJsonPoint.of takes longitude before latitude.

Distance units are units of length, separate from the angular degrees of coordinates. Geo distance queries use values such as 5km; geo distance sorts use the unit property such as km and default to meters if omitted. Arc is the suitable default calculation for geographic distance; plane is a planar approximation and should be evaluated based on range.

Coordinate-swapping bugs may be caught when latitude exceeds valid bounds, yet in some cases both values remain valid and Elasticsearch silently stores the wrong location. Use clear field names, validated value objects, dedicated mappers for GeoJSON, CRS checks, and tests with known positions. If road distance is needed, use a routing service instead of treating geo distance as travel distance.

## References

- [Spring Data Elasticsearch – GeoPoint API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/geo/GeoPoint.html)
- [Spring Data Elasticsearch – GeoJsonPoint API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/geo/GeoJsonPoint.html)
- [Elasticsearch – Geo point field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/geo-point)
- [Elasticsearch – Geo distance query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-geo-distance-query)
- [Elasticsearch – Sort search results](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/sort-search-results)
- [RFC 7946 – The GeoJSON Format](https://www.rfc-editor.org/rfc/rfc7946)