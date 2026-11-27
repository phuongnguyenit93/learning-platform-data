# Combining Business Conditions with Geospatial Queries in MongoDB

## Lesson Objectives

Applications with location data usually need to answer much more specific questions than "find places near me." For example:

- Find apartments **within 3 km of the guest**, belonging to the **current tenant**, currently **published**, priced **under 1,200,000 VND/night**, fitting **two guests**, and having **Wi-Fi**.
- List pickup points **within the map viewport**, keeping only those currently open and in stock.
- Find stores **whose delivery zone covers the customer's address**, while meeting minimum order amounts and delivery policies.
- Find accommodations near a desired location with **no conflicting bookings**, and ensure two guests cannot simultaneously confirm the same single room.
- Rank results that are both geographically valid and satisfy price, rating, and service availability conditions.

MongoDB supports geospatial data through **GeoJSON**, **`2dsphere`** indexes, the **`$near`**, **`$geoWithin`**, and **`$geoIntersects`** operators, and the **`$geoNear`** aggregation stage. Real value comes when you combine them with **ordinary business predicates**, rather than treating geospatial and business logic as two unrelated queries.

This lesson belongs to **Database Engine Document MongoDB → Geospatial Data → Combining Business Conditions with Geospatial Queries**. After completing it, you will be able to:

1. Design documents containing GeoJSON Points or Polygons with proper coordinate standards.
2. Distinguish between **proximity**, **region containment**, and **geometry intersection**.
3. Write queries combining geospatial conditions with `tenantId`, status, price, capacity, amenities, time windows, and access control.
4. Choose `find()` vs. `$geoNear` aggregation depending on whether distance fields, ranking, or multi-collection joins are needed.
5. Create compound `2dsphere` indexes and understand missing-location behavior, selectivity, and partial indexes.
6. Explain distances in meters, radii in radians, and longitude/latitude ordering.
7. Combine geospatial queries with delivery-area Polygons using `$geoIntersects`.
8. Distinguish **search-time availability** from **booking success under concurrency**.
9. Optimize distance caps, business filters, pagination, sorting, and query plans.
10. Handle edge cases: complex polygons, boundary points, bad coordinates, time zones, accuracy, and privacy.
11. Implement queries in `mongosh` and the MongoDB Java Sync Driver.
12. Test business filters combined with geospatial queries and read performance metrics.

> **Principle:** Geospatial conditions answer "is the location suitable?", whereas business conditions answer "is the entity **permitted and eligible** to appear or be booked?". Both sets of conditions must be applied consistently; the closest result is not necessarily the most eligible.

---

## 1. Scenario: Finding an Apartment Near a Pickup Point

Suppose an application manages accommodation listings. A guest enters:

~~~text
Desired coordinates: 106.70098, 10.77689
Radius:              3,000 m
Guests:              2
Max price:           1,200,000 VND/night
Amenities:           Wi-Fi
Show only:           published and verified listings
Tenant:              tenant-a (taken from authenticated context)
~~~

A listing should appear when it satisfies **all of the following simultaneously**:

\[
\text{Eligible} =
\text{Near} \land
\text{SameTenant} \land
\text{Published} \land
\text{Verified} \land
\text{PriceOK} \land
\text{CapacityOK} \land
\text{AmenityOK}
\]

This expression describes how results are filtered, **without** yet checking time-based bookings. If the user picks check-in/check-out dates, you must also check availability over that date range.

### 1.1. The Mistake of Filtering Only by Distance

~~~javascript
db.listings.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      $maxDistance: 3000
    }
  }
});
~~~

This query can return hidden listings, prices over budget, listings belonging to another tenant, or insufficient capacity.

### 1.2. The Right Mindset

~~~text
Geospatial conditions
    +
Visibility/tenant conditions
    +
Business conditions
    +
Sorting/pagination
    +
Final availability check before booking
~~~

Never treat a geospatial index or `$near` as an authorization mechanism. Access control must be enforced **alongside** geospatial conditions.

---

## 2. MongoDB-Compatible Geospatial Data

### 2.1. GeoJSON Point

A listing with a location:

~~~javascript
{
  _id: "L-101",
  title: "Central Apartment",
  location: {
    type: "Point",
    coordinates: [106.704, 10.776]
  }
}
~~~

GeoJSON uses the order:

~~~text
coordinates: [longitude, latitude]
               east-west  north-south
~~~

**Do not** swap to `[latitude, longitude]` just because many map APIs display lat/lng pairs. With the standard WGS84 coordinate system:

- Longitude is typically in **-180 to 180**.
- Latitude is in **-90 to 90**.

### 2.2. Why Must Coordinates Be Validated?

Example:

~~~javascript
coordinates: [10.776, 106.704]
~~~

Latitude `106.704` falls outside the valid range. Such data may be rejected or cause index/query errors.

Another swapped pair that still falls within valid numeric bounds is even more dangerous: MongoDB may store a point somewhere else on Earth without raising an obvious error.

### 2.3. GeoJSON Polygon

Use a Polygon for regions, service boundaries, delivery zones, or geofences.

~~~javascript
{
  type: "Polygon",
  coordinates: [[
    [106.69, 10.77],
    [106.71, 10.77],
    [106.71, 10.79],
    [106.69, 10.79],
    [106.69, 10.77]
  ]]
}
~~~

The outer ring coordinates are closed: the first and last positions match. These coordinates are illustrative only, **not real administrative boundaries or real business zones**.

### 2.4. Point, Polygon, MultiPolygon

| Data Type | Use Case |
|---|---|
| `Point` | House / store / pickup station / dropoff point |
| `Polygon` | One service area, one search region |
| `MultiPolygon` | Multiple disjoint regions managed together |
| `LineString` | Geometric route / delivery path |
| Array of Points | Multiple locations belonging to the same entity, if the model genuinely needs it |

Do not store a position as a string like `"10.776,106.704"` when you want indexed GeoJSON operators. Convert it into the proper data structure.

### 2.5. Geometry Does Not Replace Actual Travel Routes

Distance in `$near` is based on spherical geometry, **not road routes, driving time, traffic flow, or shipping fares**. An apartment 500 m away as the crow flies might require a much longer trip due to a river, bridge, or one-way street.

If the business requires true travel time, use the MongoDB query as a candidate-selection step and then call a routing service with appropriate call limits and external-data policies.

---

## 3. Designing Sample Collections for This Lesson

We use the `geo_business_lab` database. The data is illustrative, not real properties or real listed prices.

### 3.1. Listings

~~~javascript
use geo_business_lab

db.listings.insertMany([
  {
    _id: "L-101",
    tenantId: "tenant-a",
    title: "Near-Center Apartment",
    status: "PUBLISHED",
    verified: true,
    location: {
      type: "Point",
      coordinates: [106.704, 10.776]
    },
    category: "APARTMENT",
    pricePerNight: NumberLong("850000"),
    capacity: 2,
    amenities: ["wifi", "parking"],
    rating: 4.7,
    instantBook: true
  },
  {
    _id: "L-102",
    tenantId: "tenant-a",
    title: "Family Apartment",
    status: "PUBLISHED",
    verified: true,
    location: {
      type: "Point",
      coordinates: [106.716, 10.785]
    },
    category: "APARTMENT",
    pricePerNight: NumberLong("1100000"),
    capacity: 4,
    amenities: ["wifi", "kitchen"],
    rating: 4.5,
    instantBook: false
  },
  {
    _id: "L-103",
    tenantId: "tenant-b",
    title: "Listing belonging to another tenant",
    status: "PUBLISHED",
    verified: true,
    location: {
      type: "Point",
      coordinates: [106.702, 10.777]
    },
    category: "APARTMENT",
    pricePerNight: NumberLong("700000"),
    capacity: 2,
    amenities: ["wifi"],
    rating: 4.8,
    instantBook: true
  },
  {
    _id: "L-104",
    tenantId: "tenant-a",
    title: "Unpublished listing",
    status: "DRAFT",
    verified: false,
    location: {
      type: "Point",
      coordinates: [106.699, 10.778]
    },
    category: "APARTMENT",
    pricePerNight: NumberLong("650000"),
    capacity: 2,
    amenities: ["wifi"],
    rating: 0,
    instantBook: false
  },
  {
    _id: "L-105",
    tenantId: "tenant-a",
    title: "Over-budget villa",
    status: "PUBLISHED",
    verified: true,
    location: {
      type: "Point",
      coordinates: [106.705, 10.779]
    },
    category: "VILLA",
    pricePerNight: NumberLong("3800000"),
    capacity: 8,
    amenities: ["wifi", "pool"],
    rating: 4.9,
    instantBook: true
  }
]);
~~~

If re-run on the same database, duplicate `_id` values will raise duplicate key errors. Use a fresh lab database or clean up deliberately; never run broad delete commands in production.

### 3.2. Basic Geospatial Index

~~~javascript
db.listings.createIndex(
  {
    location: "2dsphere"
  },
  {
    name: "idx_listings_location_2dsphere"
  }
);
~~~

MongoDB uses a `2dsphere` index for spherical geometry queries on GeoJSON.

### 3.3. Compound Index Combining Business Fields

~~~javascript
db.listings.createIndex(
  {
    tenantId: 1,
    status: 1,
    location: "2dsphere"
  },
  {
    name: "idx_listings_tenant_status_geo"
  }
);
~~~

This is **one candidate index option**. Effectiveness depends on filter selectivity, tenant distribution, listing count, search radius, and query shape. Never assume this index always beats every alternative without inspecting `explain`.

### 3.4. Index for Bookings

~~~javascript
db.bookings.createIndex(
  {
    listingId: 1,
    status: 1,
    checkIn: 1,
    checkOut: 1
  },
  {
    name: "idx_bookings_listing_status_interval"
  }
);
~~~

This index assists part of the conflicting-booking lookup. Having two inequality conditions over a time range means the index cannot always resolve every condition optimally; measure your workload and consider precomputed calendar/availability models.

---

## 4. `$near`: Selecting Eligible and Nearest Locations

### 4.1. Query Combining Multiple Conditions

~~~javascript
const origin = {
  type: "Point",
  coordinates: [106.70098, 10.77689]
};

db.listings.find(
  {
    tenantId: "tenant-a",
    status: "PUBLISHED",
    verified: true,
    capacity: { $gte: 2 },
    pricePerNight: {
      $lte: NumberLong("1200000")
    },
    amenities: "wifi",
    location: {
      $near: {
        $geometry: origin,
        $maxDistance: 3000
      }
    }
  },
  {
    title: 1,
    pricePerNight: 1,
    capacity: 1,
    amenities: 1,
    location: 1
  }
).limit(20);
~~~

The expected results are documents satisfying **all** predicates above, sorted by proximity to `origin` per `$near` semantics.

### 4.2. What Does `$near` Handle?

- Finds locations near a point.
- Uses an appropriate geospatial index.
- Sorts results nearest to farthest.
- Caps maximum radius via `$maxDistance`.
- Optionally excludes overly close regions via `$minDistance` when needed.

### 4.3. What Unit Is `$maxDistance`?

When using a **GeoJSON Point with `2dsphere`** as above, `$maxDistance` is in **meters**.

~~~javascript
$maxDistance: 3000
~~~

means 3,000 meters in geographic distance—**not** 3,000 km and **not** radians.

### 4.4. Implicit AND Conditions

The filter document:

~~~javascript
{
  tenantId: "tenant-a",
  status: "PUBLISHED",
  verified: true,
  location: { $near: { ... } }
}
~~~

expresses **AND**: all field-level predicates must hold. There is no need to wrap them in `$and` unless specifically required.

### 4.5. Nearest Is Not Necessarily Cheapest

`$near` sorts by distance. If you want "cheapest within 3 km," that is a **different ranking**. Adding `.sort({pricePerNight:1})` requires checking the query plan and may incur sorting overhead; if you want a computed distance field and multi-criteria ranking, `$geoNear` aggregation is usually clearer.

### 4.6. When Not to Use `$near`

If you only need to check "is this point inside a region?" and **do not need distance values or nearest sorting**, `$geoWithin` or `$geoIntersects` may be a better fit.

Never use `$near` as an authorization or booking check. Visibility and access-control predicates are still mandatory.

---

## 5. `$nearSphere` and Distance Measurements

### 5.1. `$near` vs. `$nearSphere`

`$nearSphere` expresses spherical proximity. With GeoJSON and `2dsphere`, MongoDB provides near-query options with appropriate spherical semantics. Never pick an operator purely by the word "Sphere" in its name while ignoring geometry type, index type, and units.

Example:

~~~javascript
db.listings.find({
  location: {
    $nearSphere: {
      $geometry: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      $maxDistance: 3000
    }
  },
  tenantId: "tenant-a",
  status: "PUBLISHED"
});
~~~

### 5.2. Straight-Line Distance Is Not Travel Distance

Proximity returned by a geospatial query can serve as a prefilter for:

- Assigning stores to customers.
- Choosing apartments near a destination.
- Selecting pickup stations.
- Suggesting places within a radius.

However, actual routes depend on roads and terrain, so never translate 3 km proximity directly into a 5-minute delivery time.

### 5.3. At Equal Distances, Is Result Order Stable?

Multiple items can have virtually identical distances. A query sorted solely by distance may lack a **stable tie-break** by ID as data changes.

If the API supports pagination or requires deterministic output, define a secondary sort key (such as `_id`) in aggregation or business ranking and test it. Do not assume ties always appear in the same order.

---

## 6. `$geoWithin`: Filtering Points in a Region Without Nearest Sorting

### 6.1. Polygon Search Area

A user draws a box on the map. We want listings **inside** the region that meet business policies:

~~~javascript
const area = {
  type: "Polygon",
  coordinates: [[
    [106.69, 10.77],
    [106.71, 10.77],
    [106.71, 10.79],
    [106.69, 10.79],
    [106.69, 10.77]
  ]]
};

db.listings.find({
  tenantId: "tenant-a",
  status: "PUBLISHED",
  verified: true,
  pricePerNight: {
    $lte: NumberLong("1200000")
  },
  location: {
    $geoWithin: {
      $geometry: area
    }
  }
});
~~~

### 6.2. Differences from `$near`

| Property | `$near` | `$geoWithin` |
|---|---|---|
| Query input | Origin point | Region geometry |
| Primary goal | Near a point | Inside a region |
| Automatic nearest sort | Yes | **No** |
| Returned distance field | No automatic distance field | None |
| Sort by price/rating | Requires ranking logic | Easy to add standard sort, check plan |
| Typical use case | "Near me" | "Within map area" |

### 6.3. Polygon Must Be Valid

- GeoJSON uses closed coordinate rings.
- Order is longitude, latitude.
- Do not create self-intersecting rings or invalid geometries.
- For complex Polygons/MultiPolygons, account for holes, winding order, crossing the 180° meridian, regions larger than a hemisphere, and MongoDB's spherical semantics.
- For external map data, validate and normalize before writing.

### 6.4. Region Boundaries

A point close to a boundary can be tricky due to coordinate precision, operator semantics, or inconsistent polygon sources. Especially for fee or compliance decisions, define an explicit **boundary policy** and test points on edges and vertices rather than relying on visual map intuition.

### 6.5. Circular Queries Using `$centerSphere`

If you only need a list within 3 km and **do not need nearest sorting**, you can use:

~~~javascript
const earthRadiusMeters = 6378137;
const radiusMeters = 3000;

db.listings.find({
  tenantId: "tenant-a",
  status: "PUBLISHED",
  location: {
    $geoWithin: {
      $centerSphere: [
        [106.70098, 10.77689],
        radiusMeters / earthRadiusMeters
      ]
    }
  }
});
~~~

`$centerSphere` takes a **radius in radians** — dividing meter distance by Earth's radius (reference value). This is very easy to confuse with `$near.$maxDistance`, which takes meters for a GeoJSON Point.

---

## 7. `$geoIntersects`: Service Zones Containing a Customer Point

### 7.1. Delivery Coverage Problem

A merchant may have a Polygon representing a **delivery zone**. A customer enters their delivery location. We need to find service zones that:

- Are active.
- Belong to the right tenant.
- Intersect the customer's location.
- Support the `STANDARD` service.
- Satisfy `minOrderAmount` for the cart.

### 7.2. Data Model for Delivery Zones

~~~javascript
db.deliveryZones.insertMany([
  {
    _id: "ZONE-A",
    tenantId: "tenant-a",
    name: "Inner-City Delivery Zone A",
    active: true,
    supportedServices: ["STANDARD", "EXPRESS"],
    minOrderAmount: NumberLong("150000"),
    area: {
      type: "Polygon",
      coordinates: [[
        [106.69, 10.77],
        [106.72, 10.77],
        [106.72, 10.80],
        [106.69, 10.80],
        [106.69, 10.77]
      ]]
    }
  },
  {
    _id: "ZONE-B",
    tenantId: "tenant-a",
    name: "Inactive Zone",
    active: false,
    supportedServices: ["STANDARD"],
    minOrderAmount: NumberLong("100000"),
    area: {
      type: "Polygon",
      coordinates: [[
        [106.68, 10.76],
        [106.73, 10.76],
        [106.73, 10.81],
        [106.68, 10.81],
        [106.68, 10.76]
      ]]
    }
  }
]);
~~~

### 7.3. Zone Index

~~~javascript
db.deliveryZones.createIndex(
  { area: "2dsphere" },
  { name: "idx_delivery_zone_area" }
);
~~~

### 7.4. Querying Matching Zones

~~~javascript
const customerPoint = {
  type: "Point",
  coordinates: [106.70098, 10.77689]
};

const cartTotal = NumberLong("300000");

db.deliveryZones.find({
  tenantId: "tenant-a",
  active: true,
  supportedServices: "STANDARD",
  minOrderAmount: { $lte: cartTotal },
  area: {
    $geoIntersects: {
      $geometry: customerPoint
    }
  }
});
~~~

This query asks: **does the stored Polygon `area` intersect the customer's point geometry?** With a Polygon enclosing the point and matching predicates, the result is the candidate zones meeting all business conditions.

### 7.5. Do Not Reverse the Problem's Direction

- Listing location is a **Point**; user draws a **Polygon**: usually `location:{$geoWithin:{$geometry:polygon}}`.
- Service stores a **Polygon**; customer is a **Point**: use `area:{$geoIntersects:{$geometry:customerPoint}}`.

Do not confuse "Point inside Polygon" with "stored Polygon completely inside a Point." `$geoWithin` is not a drop-in replacement for every coverage query.

### 7.6. Coverage Does Not Guarantee Immediate Delivery

Beyond geometry, check:

- Branch/store is open.
- Driver capacity is available.
- Inventory is in stock.
- Address is not restricted.
- Day/time delivery policies.
- Route distance if delivery pricing depends on driven distance.
- Fees and minimum order requirements.
- Tenant/region access permissions.

Geometric containment is only **one component of the business decision**.

---

## 8. `$geoNear`: Retrieving Distance and Composing Aggregations

### 8.1. When to Use Aggregation?

`$near` works well when you only need a nearest list. Use `$geoNear` when you need to:

- Return `distanceMeters`.
- Compute a ranking score.
- Join bookings/calendars or metadata tables.
- Build price facets or groupings.
- Limit, project fields, and process further in a pipeline.

### 8.2. `$geoNear` Must Be at the Start of the Pipeline

Example:

~~~javascript
const searchPoint = {
  type: "Point",
  coordinates: [106.70098, 10.77689]
};

db.listings.aggregate([
  {
    $geoNear: {
      near: searchPoint,
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 5000,
      spherical: true,
      query: {
        tenantId: "tenant-a",
        status: "PUBLISHED",
        verified: true,
        capacity: { $gte: 2 },
        pricePerNight: {
          $lte: NumberLong("1200000")
        },
        amenities: "wifi"
      }
    }
  },
  {
    $project: {
      _id: 1,
      title: 1,
      pricePerNight: 1,
      capacity: 1,
      rating: 1,
      distanceMeters: 1
    }
  },
  {
    $limit: 20
  }
]);
~~~

`$geoNear` returns results already ordered by distance, computes the `distanceMeters` field, and supports business predicates in `query`.

### 8.3. Why Use `query`?

Because `$geoNear` must be the first stage, do not write:

~~~javascript
[
  { $match: { status: "PUBLISHED" } },
  { $geoNear: { ... } }
]
~~~

to "filter first then geoNear." That violates standard stage placement rules. Place field-level business filters inside `$geoNear.query`.

### 8.4. What Does `key` Do?

If a collection has multiple geospatial indexes, `key:"location"` specifies which field `$geoNear` should use. Even with a single field, declaring it explicitly improves readability and removes ambiguity.

### 8.5. `distanceField` and Units

With a GeoJSON Point, `2dsphere`, and `spherical:true` in this example, distances are in **meters**. You can display kilometers by dividing by 1000:

~~~javascript
db.listings.aggregate([
  {
    $geoNear: {
      near: searchPoint,
      key: "location",
      spherical: true,
      distanceField: "distanceMeters",
      maxDistance: 5000,
      query: {
        tenantId: "tenant-a",
        status: "PUBLISHED"
      }
    }
  },
  {
    $addFields: {
      distanceKm: {
        $divide: ["$distanceMeters", 1000]
      }
    }
  },
  {
    $project: {
      title: 1,
      distanceKm: 1,
      distanceMeters: 1
    }
  },
  {
    $limit: 20
  }
]);
~~~

Never treat straight-line distance as estimated driving distance or ETA.

### 8.6. `$geoNear.query` Is Not for Nesting a Second `$near`

Specify the source geometry via `$geoNear`'s `near` option, and put **non-geospatial/business** predicates in `query`. Never nest another `$near` inside it to create "double proximity."

---

## 9. Combining Conditions with Boolean Logic

### 9.1. AND

A guest needs max price, Wi-Fi, and sufficient capacity:

~~~javascript
{
  capacity: { $gte: 2 },
  pricePerNight: {
    $lte: NumberLong("1200000")
  },
  amenities: "wifi"
}
~~~

Co-occurring field-level predicates carry implicit AND logic.

### 9.2. `$in`: Multiple Accepted Categories

~~~javascript
{
  category: {
    $in: ["APARTMENT", "STUDIO"]
  }
}
~~~

Combine this condition with `location.$near` or `$geoNear.query` as appropriate.

### 9.3. `$all`: All Required Amenities

~~~javascript
{
  amenities: {
    $all: ["wifi", "parking"]
  }
}
~~~

Unlike:

~~~javascript
{
  amenities: {
    $in: ["wifi", "parking"]
  }
}
~~~

`$all` requires both amenities; `$in` requires at least one value from the set.

### 9.4. `$or` for Business Alternatives

For example, accepting listings with **instantBook** or **supported manual approval**:

~~~javascript
{
  $or: [
    { instantBook: true },
    { manualApprovalAllowed: true }
  ]
}
~~~

You can combine `$or` business filters in a pipeline or `$geoNear.query` within operator and query-planner limits. However, `$near` itself has restrictions when combined directly with `$or`; do not duplicate `$near` inside every `$or` branch expecting a single-near-query plan.

### 9.5. User-Dependent Business Rules

For example:

- VIP users can view `PREMIUM` listings.
- Domestic customers can book domestic-only products.
- Verified accounts can view listings requiring verification.

**Authenticate and evaluate policies in the service layer**, then pass predicates constructed from the trusted context. Never allow clients to send:

~~~json
{
  "tenantId": "tenant-admin",
  "includeUnpublished": true
}
~~~

to bypass access controls.

### 9.6. Do Not Encode Flawed Business Rules in Naive Predicates

For instance, `rating:{$gte:4.5}` excludes new listings with no reviews yet. If the business rule is "rating >= 4.5 **or unrated**," model that rule explicitly rather than assuming a single comparison suffices.

---

## 10. Nearest Results and Conditions from Another Collection

Sometimes a listing matches on location and price, yet is **already booked for the requested dates**. Bookings live in a separate collection:

~~~javascript
{
  _id: "B-1001",
  listingId: "L-101",
  status: "CONFIRMED",
  checkIn: ISODate("2026-12-10T00:00:00Z"),
  checkOut: ISODate("2026-12-13T00:00:00Z")
}
~~~

### 10.1. Overlap Rule for Two Time Intervals

Using half-open intervals `[start, end)`, two bookings conflict when:

\[
\text{existing.checkIn} < \text{requested.checkOut}
\]

and

\[
\text{existing.checkOut} > \text{requested.checkIn}
\]

For example, one guest checking out on the 13th and the next guest checking in on the 13th **do not conflict** if checkout/checkin rules align and no mandatory cleaning buffer applies.

### 10.2. Checking for One Listing

~~~javascript
const requestedCheckIn =
  ISODate("2026-12-10T00:00:00Z");

const requestedCheckOut =
  ISODate("2026-12-13T00:00:00Z");

db.bookings.find({
  listingId: "L-101",
  status: {
    $in: ["CONFIRMED", "HELD"]
  },
  checkIn: { $lt: requestedCheckOut },
  checkOut: { $gt: requestedCheckIn }
});
~~~

If the query returns conflicting documents, the listing is unavailable.

**Note:** In production, `HELD` bookings can expire; check `holdExpiresAt` or clean them up properly so expired holds do not block inventory forever.

### 10.3. Time Zones Matter Greatly

Check-in dates chosen by users follow the **property's time zone or product policy**, not necessarily UTC midnight. Normalize local dates to the right stored timestamps; never blindly convert a local date to `00:00Z` if the business operates in another time zone.

### 10.4. Availability Search Differs from Confirming a Booking

A geospatial query joined with bookings might show a listing as available at 10:00:00. Two guests could both see it and click "Book" moments later.

Search results are **point-in-time information**. To prevent overbooking, enforce **conditional writes, transactions, unique slot/hold records, or equivalent synchronization** upon booking confirmation.

---

## 11. Aggregation: `$geoNear` Combined with `$lookup` on Bookings

### 11.1. Problem

Find listings within 5 km, published, belonging to the current tenant, matching price and capacity, and **having no overlapping bookings**.

### 11.2. Illustrative Pipeline

~~~javascript
const point = {
  type: "Point",
  coordinates: [106.70098, 10.77689]
};

const checkIn = ISODate("2026-12-10T00:00:00Z");
const checkOut = ISODate("2026-12-13T00:00:00Z");

db.listings.aggregate([
  {
    $geoNear: {
      near: point,
      key: "location",
      distanceField: "distanceMeters",
      maxDistance: 5000,
      spherical: true,
      query: {
        tenantId: "tenant-a",
        status: "PUBLISHED",
        verified: true,
        capacity: { $gte: 2 },
        pricePerNight: {
          $lte: NumberLong("1200000")
        }
      }
    }
  },
  {
    $lookup: {
      from: "bookings",
      let: {
        currentListingId: "$_id"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                {
                  $eq: [
                    "$listingId",
                    "$$currentListingId"
                  ]
                },
                {
                  $in: [
                    "$status",
                    ["CONFIRMED", "HELD"]
                  ]
                },
                {
                  $lt: ["$checkIn", checkOut]
                },
                {
                  $gt: ["$checkOut", checkIn]
                }
              ]
            }
          }
        },
        {
          $limit: 1
        }
      ],
      as: "conflictingBookings"
    }
  },
  {
    $match: {
      conflictingBookings: {
        $size: 0
      }
    }
  },
  {
    $project: {
      title: 1,
      pricePerNight: 1,
      capacity: 1,
      distanceMeters: 1
    }
  },
  {
    $limit: 20
  }
]);
~~~

### 11.3. Explanation

- `$geoNear`: nearby candidates + same-collection business predicates.
- `$lookup`: queries bookings per candidate listing.
- `$match`: keeps only listings with zero conflicting bookings.
- `$project`: returns required fields.
- `$limit`: caps result count after checking availability.

### 11.4. Why Not Place `$limit:20` Immediately After `$geoNear`?

Suppose the 20 closest apartments are all booked, while apartments 21–30 are available. Limiting before the lookup inspects only those first 20 and returns 0 results, **missing valid available apartments slightly farther away**.

This is the difference between:

> "Take the 20 closest apartments, then drop unavailable ones."

and:

> "Take the 20 closest **eligible** apartments."

The two requirements can yield drastically different results.

### 11.5. Performance Cost

Conversely, running `$lookup` across every listing within a large radius before limiting can be very expensive. Approaches to consider:

- Set a reasonable radius.
- Increase predicate selectivity in `$geoNear.query`.
- Index `bookings` properly.
- Maintain a precomputed availability calendar or summary.
- Two-phase search: fetch a sufficiently large candidate batch, check availability in bulk, and fetch more if needed.
- Precomputed search views for common availability patterns.
- Benchmark on production-like data.

**Trade-off:** Two-phase fetching of N initial candidates cannot guarantee the full top K unless you iteratively expand the candidate window until K are found or the search area is exhausted.

### 11.6. What If Bookings Change Mid-Query?

Even a pipeline accurate at read time does not guarantee the unit remains free when the user confirms. Checkout must enforce the invariant with an atomic write or transaction.

---

## 12. Preventing Overbooking at Confirmation Time

### 12.1. Never Treat a Search Result as a Lock

Two requests:

~~~text
Guest A: query sees L-101 is available
Guest B: query sees L-101 is available
Guest A: confirms
Guest B: confirms
~~~

If the code merely calls `insertOne` into `bookings` without enforcing time-slot uniqueness, both requests can create overlapping bookings.

### 12.2. Example: Night Locks for a Single-Unit Listing

For a listing allowing **one booking per night**, you can use a `listingNightLocks` collection whose unique `_id` combines `listingId` and the date.

~~~javascript
{
  _id: "L-101:2026-12-10",
  listingId: "L-101",
  night: "2026-12-10",
  bookingId: "B-2001"
}
~~~

If a booking spans nights 10, 11, and 12, a transaction attempts to insert all three night-lock documents alongside the booking.

### 12.3. Conceptual Java / Mongosh Logic

~~~text
startTransaction
    |
    +-- insert lock "L-101:2026-12-10"
    +-- insert lock "L-101:2026-12-11"
    +-- insert lock "L-101:2026-12-12"
    +-- insert booking B-2001
    |
commitTransaction
~~~

If any night-lock `_id` already exists, the unique constraint fails the transaction, which must abort per policy. Thus, two confirmations for the same listing-night cannot both succeed as unique locks.

### 12.4. Limitations of the Night-Lock Pattern

- Nights must be defined in the listing's time zone.
- Locks must be released upon cancellation or expiry.
- Temporary holds need TTL/expiration and safe contention handling.
- Multi-room listings with capacity > 1 need a different model.
- Hourly bookings need appropriate time slots.
- Unknown commit results and idempotency must be handled.
- Unique IDs alone do not enforce all other business constraints.

This is **one double-booking prevention example for single-unit capacity**, not a universal model for every reservation system.

---

## 13. Compound `2dsphere` Indexes and Business Predicates

### 13.1. Single Geospatial Index

~~~javascript
db.listings.createIndex({
  location: "2dsphere"
});
~~~

Suitable for basic geospatial queries.

### 13.2. Compound Index

~~~javascript
db.listings.createIndex(
  {
    tenantId: 1,
    status: 1,
    location: "2dsphere"
  },
  {
    name: "idx_tenant_status_location"
  }
);
~~~

A compound geospatial index helps the planner evaluate both business predicates and location when the query shape aligns.

### 13.3. Adding More Fields Is Not Always Better

Example:

~~~javascript
db.listings.createIndex({
  tenantId: 1,
  status: 1,
  location: "2dsphere",
  pricePerNight: 1,
  capacity: 1,
  rating: -1
});
~~~

This index **does not automatically guarantee** optimal filtering and sorting across price, capacity, and rating simultaneously. Geospatial access, inequality predicates, multikey fields, and sorting all impose constraints, while larger indexes increase storage and write overhead.

Propose a small set of candidate indexes based on your workload and compare them with `explain("executionStats")`.

### 13.4. Indexes for Tenant Isolation

A multi-tenant product frequently queries:

~~~javascript
{
  tenantId: trustedTenantId,
  status: "PUBLISHED",
  location: { $near: { ... } }
}
~~~

`tenantId` has strong selectivity in many workloads; placing it in a compound index can help. Base the decision on real tenant distributions. Never turn an index into a security boundary: queries must still enforce tenant authentication.

### 13.5. Partial Index for Published Listings

For example, indexing only published listings:

~~~javascript
db.listings.createIndex(
  {
    tenantId: 1,
    location: "2dsphere"
  },
  {
    name: "idx_public_tenant_location",
    partialFilterExpression: {
      status: "PUBLISHED"
    }
  }
);
~~~

Queries using this partial index safely must include a matching predicate such as `status:"PUBLISHED"`. If a query requests `DRAFT` listings, this index does not cover them, and the planner will need another path.

### 13.6. `2dsphere` Indexes Are Sparse

`2dsphere` indexes exhibit sparse behavior: documents missing the geospatial field or lacking valid indexable Point values are omitted from the normal geospatial index. Even in a **compound `2dsphere` index**, a document missing `location` will not be covered by the geospatial index regardless of its other business fields.

Do not rely on `tenantId` in a compound geo index to find **all** listings including ones without a location.

### 13.7. Location Updates Carry Cost

Whenever a listing updates `location`, MongoDB must update the geospatial index. For continuously moving entities (couriers, taxis), write rates and index updates can be high; evaluate update frequency, "last known location" tables, TTL/retention, and real-time architecture.

---

## 14. `explain()`: Checking How Queries Actually Use Indexes

### 14.1. Example with `find`

~~~javascript
db.listings.find({
  tenantId: "tenant-a",
  status: "PUBLISHED",
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      $maxDistance: 3000
    }
  }
}).explain("executionStats");
~~~

### 14.2. Example with Aggregation

~~~javascript
db.listings.explain("executionStats").aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      key: "location",
      spherical: true,
      maxDistance: 3000,
      distanceField: "distanceMeters",
      query: {
        tenantId: "tenant-a",
        status: "PUBLISHED"
      }
    }
  },
  { $limit: 20 }
]);
~~~

### 14.3. Metrics to Inspect

| Metric / Info | Meaning |
|---|---|
| `winningPlan` | Selected query plan |
| Geospatial index access | Whether an appropriate geospatial index was used |
| `totalKeysExamined` | Number of index keys examined |
| `totalDocsExamined` | Number of documents examined |
| `nReturned` | Number of documents returned |
| Execution time | Duration in the measured environment |
| Sort stage | Whether an expensive memory/CPU sort ran |
| Rejected plans | Alternative plans considered by the planner |

Stage names and `explain` output structures can change across MongoDB versions and engines. Never write production assertions coupled to a single stage name.

### 14.4. Predicate Selectivity

If a 50 km radius covers 1 million listings yet only 0.1% are active for the current tenant, the query may examine many candidates before finding enough matches. Compound indexes, partial indexes, and filter strategy matter greatly.

Conversely, if a 200 m radius contains only 10 listings, a geo-only index may already suffice. No single index is optimal for every radius.

### 14.5. Benchmark on Realistic Data

A handful of lab documents proves nothing about production speed. Measure with:

- Large location counts.
- Realistic spatial distributions.
- Tenant skew.
- Sparse vs. dense clusters.
- Peak traffic loads.
- Radii of 100 m, 3 km, and 50 km.
- Queries returning very few vs. very many results.
- Proportion of listings missing geolocation.
- Price and rating distributions.

---

## 15. Sorting: Nearest, Cheapest, or Best Match?

### 15.1. Define Ranking Before Writing Queries

Three distinct requirements:

1. **Nearest:** sort by distance.
2. **Cheapest in area:** filter region + price, then sort by price.
3. **Best match:** distance, price, rating, verification, booking availability, and business weights.

Never return a nearest list and label it "Best Match" without defining business ranking.

### 15.2. `$geoNear` Returning Distance

Illustrative ranking score example:

~~~javascript
db.listings.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      distanceField: "distanceMeters",
      key: "location",
      spherical: true,
      maxDistance: 3000,
      query: {
        tenantId: "tenant-a",
        status: "PUBLISHED",
        verified: true
      }
    }
  },
  {
    $addFields: {
      rankingScore: {
        $subtract: [
          { $multiply: ["$rating", 1000] },
          "$distanceMeters"
        ]
      }
    }
  },
  {
    $sort: {
      rankingScore: -1,
      _id: 1
    }
  },
  { $limit: 20 },
  {
    $project: {
      title: 1,
      distanceMeters: 1,
      rating: 1,
      rankingScore: 1
    }
  }
]);
~~~

This formula is **purely a technical illustration**, not a good production recommendation algorithm. The multiplier `1000` is arbitrary; normalize scales, fairness, and business requirements properly.

### 15.3. Why Must Sort Precede Limit for Global Ranking?

If you take the 20 nearest listings and then sort by price or rating, the 21st-nearest listing with a far better price or rating will be excluded. If the requirement is "top 20 by `rankingScore` within 3 km," compute and sort over the **eligible candidate set** before limiting, or use a top-k algorithm with equivalent guarantees.

### 15.4. Capping the Candidate Set

Because scoring and sorting every point inside a huge radius can be resource-intensive:

- Set reasonable `maxDistance` caps.
- Filter by tenant, status, verified, and price before ranking.
- Keep payloads small.
- Precompute stable signals.
- Provide fallbacks when scope is too broad.
- Monitor sort memory, disk spills, and query latency.

---

## 16. Pagination with Geospatial Results

### 16.1. Simple Approach: `skip` and `limit`

~~~javascript
db.listings.aggregate([
  {
    $geoNear: {
      near: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      key: "location",
      distanceField: "distanceMeters",
      spherical: true,
      maxDistance: 5000,
      query: {
        tenantId: "tenant-a",
        status: "PUBLISHED"
      }
    }
  },
  { $skip: 40 },
  { $limit: 20 }
]);
~~~

Good for illustrating page 3 with page size 20. However, deep pagination with large `skip` values is expensive.

### 16.2. Defining Stable Ordering

When multiple results have nearly identical distances, add a tie-breaker such as:

~~~javascript
{
  $sort: {
    distanceMeters: 1,
    _id: 1
  }
}
~~~

A `$sort` stage adds resource cost, yet deterministic ordering is vital for pagination.

### 16.3. Cursor / Keyset Pagination

An advanced approach uses a token containing:

- Fixed origin and radius.
- Business filter signature.
- Last returned distance/score.
- Tie-breaker `_id`.
- Optional snapshot/ranking version.

Then fetch results after that marker. However:

- Floating-point distances pose exact-comparison issues.
- Changing the user's origin alters every distance.
- Adding, deleting, or updating listings shifts order between pages.
- `$geoNear` must still be the first stage.
- When booking availability changes over time, pagination does not guarantee an immutable snapshot across requests.

Do not build a naive "distance+id" token and claim zero duplicates/skips on dynamic data. Define an explicit paging contract and test it.

### 16.4. Changing Map Viewports

When a user pans or zooms the map:

- The origin or Polygon changes.
- Radius and filters change.
- Old pagination tokens become invalid.

Reset to page 1 for each new query context. Cache keys should incorporate tenant, normalized coordinates, radius, filters, and appropriate versioning.

---

## 17. Viewport Search: `geoWithin` or `near`?

### 17.1. "Show Everything Inside the Map Rectangle"

Use a polygon/geometry representing the viewport:

~~~javascript
db.listings.find({
  tenantId: "tenant-a",
  status: "PUBLISHED",
  location: {
    $geoWithin: {
      $geometry: {
        type: "Polygon",
        coordinates: [[
          [106.69, 10.77],
          [106.72, 10.77],
          [106.72, 10.80],
          [106.69, 10.80],
          [106.69, 10.77]
        ]]
      }
    }
  }
});
~~~

### 17.2. "Show 10 Places Closest to the Center"

Use `$near` or `$geoNear` with origin and radius.

### 17.3. Large Viewports Require Marker Limits

If a map would render tens of thousands of points, the bottleneck is not only query speed but also client rendering and memory. You can:

- Project only fields needed for map markers.
- Cluster points by zoom/grid (in the application or an appropriate pipeline).
- Cap or sample results per business rules.
- Partition viewports into cacheable tiles.
- Return total counts/facets separately if needed.

Never fetch the 100 nearest points and display them as if "these are all listings in the viewport."

### 17.4. Viewports Crossing the 180° Meridian

In a global application, bounding boxes can cross the antimeridian. A naive rectangle connecting longitude `179` to `-179` can be misinterpreted without proper spherical geometry. Use Polygon/MultiPolygon geometries structured per MongoDB semantics and test boundary regions.

---

## 18. Accuracy and Business Invariants

### 18.1. User-Supplied Coordinates Are Untrusted Input

Validate:

- `longitude` and `latitude` are finite numbers.
- Values fall within valid bounds.
- Not `null`, `NaN`, or `Infinity`.
- Correct axis order.
- Radius does not exceed the maximum allowed.
- User-supplied data does not form self-intersecting or oversized Polygons.
- Vertex count is capped to prevent heavy queries.

### 18.2. User Radii Need a Server-Side Cap

Suppose a user submits a 500,000 km radius. Even if the API accepts a radius parameter, the server must enforce a clear maximum and default:

~~~text
UI radius: 3 km
Backend validated radius: 3000 meters
Server maximum: defined by business, e.g. 50 km
~~~

This maximum is illustrative, not a MongoDB limit.

### 18.3. Never Use Geospatial Results as Authorization

A listing close to a customer yet belonging to another tenant must be excluded. Likewise, a `PRIVATE` listing must not leak just because it falls inside the search region.

Trusted predicates must be constructed from authenticated context:

~~~javascript
{
  tenantId: requestAuth.tenantId,
  status: "PUBLISHED",
  verified: true,
  location: { $near: { ... } }
}
~~~

This snippet illustrates trusted service-side sourcing; never read `tenantId` from arbitrary client input when tenant isolation is a security requirement.

### 18.4. Fields Prone to Staleness

- `openNow`.
- `availableRooms`.
- `inventoryCount`.
- `estimatedDeliveryTime`.
- `rating` or review counts when ingestion lags.

If using denormalized fields for search, establish update mechanisms and consistency policies. Never treat cached search values as final booking confirmation.

### 18.5. A Delivery Zone Does Not Guarantee Capacity

`$geoIntersects` tells you the customer point falls inside a declared zone, yet drivers may be unavailable, or the store may be closed or overloaded. Final decisions must check live business rules.

### 18.6. Date and Time Rules

Stores open in local time, bookings run by local nights, and order cutoffs depend on time zones. When combining time with location, store each entity's time zone explicitly, convert timestamps properly, and test Daylight Saving Time transitions where applicable.

---

## 19. Privacy and Location Data

### 19.1. Location Is Sensitive Data in Many Contexts

Precise coordinates can reveal home addresses, workplaces, or daily movements. Store only the precision required, restrict read access, and enforce retention policies.

### 19.2. Never Return Full Documents Indiscriminately

Queries can use projections:

~~~javascript
db.listings.find(
  { tenantId: "tenant-a", status: "PUBLISHED" },
  {
    title: 1,
    pricePerNight: 1,
    location: 1
  }
);
~~~

However, for listings whose exact address is private before booking, the API must obfuscate coordinates or return an approximate circle/area per policy. Never let clients request `ownerPhone` or `privateNotes`.

### 19.3. Limit Logging of Request Coordinates

Avoid storing full user coordinates in logs long-term without valid purpose and policy. Consider rounding, grid hashing, or redaction in monitoring depending on compliance requirements.

### 19.4. Do Not Use a Polygon as the Sole Security Geofence

If a security rule relies on a user physically being inside an area, client-reported coordinates can be spoofed. GeoJSON queries evaluate provided data—they do not prove location authenticity.

---

## 20. Java Sync Driver: Combining Near with Business Conditions

### 20.1. Working with the `Filters` API

The MongoDB Java Sync Driver provides builders like `Filters.near`, `Filters.geoWithin`, and `Aggregates.geoNear` depending on API/version. Using `Document` directly illustrates the exact BSON query shape clearly.

### 20.2. Example Using `Document`

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.List;

public class GeoBusinessFindExample {

    public static void search(MongoClient client) {
        MongoDatabase database =
            client.getDatabase("geo_business_lab");

        MongoCollection<Document> listings =
            database.getCollection("listings");

        Document point = new Document(
            "type", "Point"
        ).append(
            "coordinates",
            List.of(106.70098, 10.77689)
        );

        Document near = new Document(
            "$near",
            new Document("$geometry", point)
                .append("$maxDistance", 3000)
        );

        Document filter = new Document(
            "tenantId", "tenant-a"
        )
            .append("status", "PUBLISHED")
            .append("verified", true)
            .append(
                "capacity",
                new Document("$gte", 2)
            )
            .append(
                "pricePerNight",
                new Document("$lte", 1200000L)
            )
            .append("amenities", "wifi")
            .append(
                "location",
                near
            );

        listings.find(filter)
            .projection(
                new Document("title", 1)
                    .append("pricePerNight", 1)
                    .append("capacity", 1)
                    .append("location", 1)
            )
            .limit(20)
            .forEach(System.out::println);
    }
}
~~~

### 20.3. Key Points

- `coordinates` is `[longitude,latitude]`.
- `$maxDistance` for GeoJSON near is in meters.
- Tenant/status/verified/price/capacity/wifi filters sit in the **same query** as location.
- `tenantId` is a literal in the example; obtain it from the authenticated context in production.
- Projection reduces payload size.
- Requires a `2dsphere` index.
- Java `long` `1200000L` maps to a 64-bit integer under standard codecs.

### 20.4. Do Not Create a `MongoClient` per Query

In production, `MongoClient` is managed as a long-lived singleton by the application or dependency injection with connection pooling. Never open and close a client for each map request.

---

## 21. Java Sync Driver: Aggregation with a Distance Field

### 21.1. Using `Document` to Represent the Pipeline

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.List;

public class GeoBusinessAggregationExample {

    public static void run(MongoClient client) {
        MongoDatabase db =
            client.getDatabase("geo_business_lab");

        MongoCollection<Document> listings =
            db.getCollection("listings");

        Document point = new Document(
            "type", "Point"
        ).append(
            "coordinates",
            List.of(106.70098, 10.77689)
        );

        Document businessFilters = new Document(
            "tenantId", "tenant-a"
        )
            .append("status", "PUBLISHED")
            .append("verified", true)
            .append(
                "capacity",
                new Document("$gte", 2)
            )
            .append(
                "pricePerNight",
                new Document("$lte", 1200000L)
            );

        Document geoNear = new Document(
            "$geoNear",
            new Document("near", point)
                .append("key", "location")
                .append(
                    "distanceField",
                    "distanceMeters"
                )
                .append("maxDistance", 5000)
                .append("spherical", true)
                .append("query", businessFilters)
        );

        Document project = new Document(
            "$project",
            new Document("title", 1)
                .append("pricePerNight", 1)
                .append("capacity", 1)
                .append("distanceMeters", 1)
        );

        listings.aggregate(
            List.of(
                geoNear,
                project,
                new Document("$limit", 20)
            )
        ).forEach(System.out::println);
    }
}
~~~

### 21.2. Why Must the Pipeline Start with `$geoNear`?

MongoDB normally requires `$geoNear` to be the first stage in the pipeline. Put filters inside `query` rather than placing `$match` before `$geoNear`.

### 21.3. What If There Are Many Complex Conditions?

Use builder classes to avoid assembling raw BSON manually where filters multiply, or separate:

- Trusted filters.
- Validated geospatial input.
- Aggregation stages.
- Post-geospatial joins/ranking.
- Response projection.

Crucially, **never merge unvalidated user input directly into an arbitrary BSON query**.

### 21.4. Do Not Call an External Routing API for Thousands of Candidates

If you need ETAs per listing, select the top N geospatial and business candidates first, then compute routes/travel times for a controlled count. Keep in mind that picking top N by straight-line distance may drop a listing with faster road access—this is a search quality vs. performance trade-off to test.

---

## 22. Exposing Multi-Criteria Search in an API

### 22.1. Illustrative API Input

~~~json
{
  "center": {
    "longitude": 106.70098,
    "latitude": 10.77689
  },
  "radiusMeters": 3000,
  "maxPrice": 1200000,
  "guests": 2,
  "requiredAmenities": ["wifi"],
  "sort": "DISTANCE_ASC",
  "pageSize": 20
}
~~~

### 22.2. What the Server Must Decide

- `tenantId` from identity/authorization, never trusting self-reported input.
- Listing visibility per user role.
- Capping `radius`/`pageSize` within product limits.
- Validating price, guest count, and allowed amenity values.
- Ensuring proper coordinate order.
- Location precision policies and allowed response fields.
- Time zones and date ranges for bookings.
- Default sorting/ranking.

### 22.3. A Query Builder Must Not Become a JSON Passthrough

Never allow clients to submit raw MongoDB queries:

~~~json
{
  "$or": [
    {"status": "PUBLISHED"},
    {"tenantId": {"$ne": "tenant-a"}}
  ]
}
~~~

and pass them straight into `find()`. Instead, parse a whitelisted DTO, validate values, and construct the BSON query strictly from permitted fields.

### 22.4. Responses Should Use Consistent Units

Example:

~~~json
{
  "id": "L-101",
  "title": "Near-Center Apartment",
  "distanceMeters": 420,
  "pricePerNight": 850000,
  "currency": "VND",
  "capacity": 2
}
~~~

The distance value is purely illustrative of the response shape, not the result of an actual query run. Never fabricate travel time without calling a routing service.

---

## 23. Another Business Case: Nearest In-Stock Stores Within a Radius

### 23.1. Store Document

~~~javascript
{
  _id: "STORE-101",
  tenantId: "tenant-a",
  active: true,
  storeType: "PICKUP_POINT",
  location: {
    type: "Point",
    coordinates: [106.701, 10.778]
  },
  stockBySku: {
    SKU101: 12,
    SKU102: 0
  }
}
~~~

### 23.2. Combined Query

~~~javascript
db.stores.find({
  tenantId: "tenant-a",
  active: true,
  storeType: "PICKUP_POINT",
  "stockBySku.SKU101": { $gte: 2 },
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      $maxDistance: 2000
    }
  }
});
~~~

### 23.3. Do Not Stuff Unbounded SKU Fields into Store Documents

If a store carries hundreds of thousands of SKUs, dynamic fields like `stockBySku.SKU101` bloat documents and complicate indexing. Consider a separate `storeInventory` collection or a search/materialized view optimized for SKU + geospatial filtering.

### 23.4. Indexing Strategy

When the common query is "specific SKU, in stock, near user," you can build an **inventory availability search collection** with one document per store-SKU, embedding or referencing the store location, and index on SKU/stock + location.

Trade-off: duplicated locations must be updated if a store moves. This is a standard denormalization vs. consistency trade-off.

### 23.5. Final Confirmation

Seeing stock = 2 at search time does not guarantee stock is still 2 when the customer checks out. Order/reservation placement must execute a conditional update such as `available:{$gte:quantity}` inside a transaction or equivalent mechanism.

---

## 24. Another Business Case: Finding Drivers or Service Agents

### 24.1. Adding Status Predicates

A driver near a customer whose `status` is `"OFFLINE"` or who is already on a trip is ineligible.

~~~javascript
db.drivers.find({
  tenantId: "tenant-a",
  status: "AVAILABLE",
  vehicleType: "BIKE",
  capacityKg: { $gte: 5 },
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.70098, 10.77689]
      },
      $maxDistance: 3000
    }
  }
}).limit(20);
~~~

### 24.2. Location Freshness

If a position was reported 30 minutes ago, the driver may no longer be there. You can require:

~~~javascript
{
  lastLocationAt: {
    $gte: ISODate("2026-11-14T04:00:00Z")
  }
}
~~~

Compute the threshold relative to current time and actual SLAs; the timestamp above is illustrative. Never hardcode sample dates in production code.

### 24.3. Status at Assignment Time

Two orders may concurrently see the same `AVAILABLE` driver. Use an atomic conditional update or transaction to transition the driver from `AVAILABLE` to `ASSIGNED` for at most one request.

### 24.4. High-Frequency Location Updates

If drivers report locations every second, geospatial indexes undergo constant updates. Depending on scale, separate:

- Real-time locations with TTL.
- Long-lived profile data.
- Work assignment / availability state.
- Geospatial candidate search.
- Final assignment transaction.

Do not assume a single collection containing every field is mandatory.

---

## 25. Evaluating Performance with a Two-Stage Model

A practical mental model:

~~~text
Stage 1:
  Find candidates matching geospatial predicates and business filters
  that can be pushed down into the query/index.

Stage 2:
  Evaluate expensive conditions (booking calendars, rating ranking,
  routing ETA, dynamic inventory) on the narrowed candidate set.
~~~

### 25.1. Benefits

- Fewer documents to join.
- Fewer calls to external services.
- Smaller payloads.
- Easier to isolate bottlenecks.

### 25.2. Correctness Risk

Cutting candidates too aggressively can drop eligible results slightly farther away. For instance, taking the 20 closest listings and finding only 2 available after checking bookings does not mean only 2 exist within the radius.

### 25.3. How to Balance

- Choose radii matched to actual need.
- Apply selective business filters as early as possible.
- Over-fetch candidates adequately, and fetch another batch if needed.
- Enforce latency/cost budgets and clear paging metadata.
- When exact top-K is required, scan enough candidates or use a dedicated index/data model.
- When using approximate candidate selection, document that results are best-effort suggestions rather than exhaustive.

---

## 26. Common Mistakes

**"GeoJSON uses [lat,lng]."** Wrong. It uses `[longitude,latitude]`.

**"`$maxDistance` is in km."** Wrong for GeoJSON Point/`2dsphere` here; it is in meters.

**"`$centerSphere` takes meters."** Wrong. `$centerSphere`'s radius is passed in radians.

**"`$near` alone is enough for search."** Wrong. You also need tenant, visibility, price, capacity, amenities, and other business rules.

**"`$geoWithin` automatically sorts nearest first."** Wrong. It tests containment and does not sort by distance.

**"To check if a stored Polygon contains a customer Point, use `$geoWithin` with the query Point."** Wrong direction; with a stored Polygon area and query Point, use `$geoIntersects`.

**"`$geoNear` can go after an initial `$match` in a pipeline."** Violates standard stage placement rules.

**"`$geoNear.query` can contain a second `$near`."** Incorrect; the stage's `near` option already defines proximity.

**"Having a geo index automatically optimizes all business filters."** Wrong. Evaluate compound indexes, selectivity, and `explain`.

**"Putting every field in a compound geo index is fastest."** Wrong. Index bloat and sort/inequality/geospatial trade-offs must be measured.

**"A partial index on PUBLISHED still serves DRAFT queries."** No; a partial index only indexes documents matching its filter expression.

**"A `2dsphere` compound index always includes documents missing `location`."** Wrong; geospatial sparse behavior applies.

**"20 nearest then filtering bookings equals the 20 nearest available listings."** Wrong. Filtering after limiting can drop valid matches.

**"A listing returned by search has a room lock held."** Wrong. Availability must be confirmed atomically at booking time.

**"Use UTC midnight for check-in/check-out across all listings."** Wrong. Respect property time zones and local date rules.

**"1 km straight-line = 1 km driving."** Wrong. Routing distance/ETA differs from geospatial distance.

**"A point inside a delivery zone guarantees delivery."** Wrong. Operating hours, capacity, and business conditions still apply.

**"Client-supplied `tenantId` is secure enough."** Wrong. Take tenant from authenticated context and enforce field-level visibility.

**"Exact location precision can be returned to every user."** No; enforce privacy policies.

**"Deep pagination with `skip` is free."** Wrong. Large skips force the planner to process excessive work.

**"A location query at 10:00 stays valid when confirming at 10:05."** Wrong. Locations, stock, bookings, and availability can change.

---

## 27. Workflow for Designing Combined Geospatial + Business Queries

### Step 1 — Write Requirements as Explicit Predicates

Example:

~~~text
Within 3 km around customer location
AND belongs to current tenant
AND status PUBLISHED
AND verified = true
AND price <= 1,200,000
AND capacity >= 2
AND amenities contains Wi-Fi
AND no overlapping bookings
~~~

### Step 2 — Classify the Data

- Location Point/Polygon.
- Same-collection business fields.
- Dynamic fields / related collections.
- Permissions and policies.
- Time and time zones.
- Eventual vs. strong consistency requirements.

### Step 3 — Choose the Geospatial Operator

| Question | Operator |
|---|---|
| Near a Point, sorted by distance | `$near` |
| Near a Point, needing distance field / pipeline | `$geoNear` |
| Stored Point inside Polygon or circle | `$geoWithin` |
| Stored Polygon intersecting customer Point/geometry | `$geoIntersects` |

### Step 4 — Place Business Filters in the Same Query

Tenant, status, price, category, capacity, amenities, verification. Ensure authorization filters come from a trusted context.

### Step 5 — Select Candidate Indexes

Create a `2dsphere` index plus targeted compound/partial indexes matched to your workload, avoiding index bloat.

### Step 6 — Define Ranking and Pagination

Nearest vs. price vs. blended score; tie-breakers, radius, page size, and dynamic updates.

### Step 7 — Optimize Related-Data Checks

Availability lookups, stock joins, delivery-zone matching, routing ETA — run on reasonable candidate pools without silently sacrificing required completeness.

### Step 8 — Protect the Final Mutation

Booking, inventory, and driver assignment require conditional writes, unique constraints, or transactions. Search is discovery, not a lock.

### Step 9 — Measure on Production-Like Data

Inspect `explain`, query latency, documents examined, index selection, disk/memory usage, varied radii, and tenant skew.

### Step 10 — Test Edge Cases

Swapped coordinates, missing locations, malformed Polygons, boundaries, time zones, stale availability, concurrent bookings, privacy rules, and unauthorized requests.

---

## 28. Test Matrix

| Test | Data / Input | Expected Outcome to Verify |
|---|---|---|
| T1 | Nearby listing in `DRAFT` | Excluded from public search |
| T2 | Nearby listing belonging to another tenant | Excluded |
| T3 | Listing exceeding max price | Excluded |
| T4 | Capacity smaller than guests | Excluded |
| T5 | Missing Wi-Fi | Excluded when Wi-Fi is required |
| T6 | Point inside search Polygon | Included if other rules pass |
| T7 | Point outside Polygon | Excluded |
| T8 | Stored service area intersects customer Point | Zone returned as candidate |
| T9 | Inactive delivery zone | Excluded despite matching geometry |
| T10 | GeoJSON with swapped lat/lng | Validation rejects or test catches wrong location |
| T11 | 3 km vs. 30 km radius | Query selects corresponding scope |
| T12 | Bounding Polygon with unclosed ring | Validation fails or handled explicitly |
| T13 | Listings at nearly equal distances | Stable tie-break/pagination per policy |
| T14 | Exact overlapping booking | Listing excluded from available results |
| T15 | Checkout = next booking's check-in | No overlap under `[start,end)` |
| T16 | Two guests confirm the same night | Only one booking acquires the lock |
| T17 | One tenant has millions of listings | Explain/index and latency still meet SLO |
| T18 | Booking lookup after limit | Verify no valid listings dropped prematurely |
| T19 | Missing location field | Handled per geo index / data quality policy |
| T20 | User pans map | Old paging token properly reset |
| T21 | Client attempts sending another `tenantId` | Backend rejects privilege bypass |
| T22 | Listing has private coordinates | API does not leak precision beyond policy |

---

## 29. Hands-On Exercises

### Exercise 1 — Designing GeoJSON

Create three GeoJSON Points for three listings, verifying longitude/latitude order. Create a rectangular Polygon with a closed outer ring.

### Exercise 2 — `2dsphere` Index

Create an index on `listings.location`. Observe behavior when a document lacks `location`.

### Exercise 3 — Finding Nearby Listings

Use `$near` to search within 2,000 m around a Point, limiting to 10 results. Explain result ordering and the unit of `$maxDistance`.

### Exercise 4 — Combining Status and Tenant

Return only listings belonging to `tenant-a`, `PUBLISHED`, `verified`, and within a 3 km radius. Add a `DRAFT` listing right next to the origin and verify it is excluded.

### Exercise 5 — Budget and Capacity

Add `pricePerNight <= 1000000` and `capacity >= 2` filters. Explain why these filters should be applied before making business decisions.

### Exercise 6 — Amenities

Write two queries: requiring both `wifi` and `parking` with `$all`, and accepting either `wifi` or `parking` with `$in`.

### Exercise 7 — Geographic Region

Use `$geoWithin` with a user-drawn Polygon. Compare it with a `$near` query around the region's center.

### Exercise 8 — Radius in Radians

Use `$geoWithin + $centerSphere` with a 5 km radius. Convert to radians using a chosen Earth radius and explain why you must not pass `5000` directly.

### Exercise 9 — Delivery Zones

Store `deliveryZones` as Polygons and query with `$geoIntersects` against a customer Point. Add `active`, `tenant`, and `minOrderAmount` filters.

### Exercise 10 — Aggregation Distance

Write a `$geoNear` pipeline returning `distanceMeters`, price, and rating. Convert distance to km and limit results.

### Exercise 11 — Pipeline Order

Explain why placing `$match` before `$geoNear` is invalid. Move the filter into `$geoNear.query`.

### Exercise 12 — Booking Intervals

Write a `bookings.find` query checking interval overlap using the formula:

~~~text
existing.checkIn < requested.checkOut
AND
existing.checkOut > requested.checkIn
~~~

### Exercise 13 — `GeoNear` + Booking Lookup

Write a `$geoNear → $lookup → $match → $limit` pipeline to find nearby listings without overlapping bookings. Discuss performance and the false-negative bug caused by limiting before lookup.

### Exercise 14 — Preventing Overbooking

Design unique night locks for a single-room listing. Simulate two concurrent bookings and explain the role of transactions and unique constraints.

### Exercise 15 — Compound Geospatial Index

Propose two candidate indexes for multi-tenant, status, and near queries. Compare them using `explain`, rather than guessing by field count.

### Exercise 16 — Partial Index

Index only `PUBLISHED` listings. Write a query that can use the index and a `DRAFT` query that is not covered by it.

### Exercise 17 — Ranking

Build an aggregation that computes `distanceMeters` and sorts by an illustrative score combining distance and rating. Explain why `$sort` must precede `$limit` for top-K by score.

### Exercise 18 — Pagination

Compare `skip`/`limit` with cursor pagination when a user pans a map. Discuss floating-point distances, tie-breaking, and dynamic data.

### Exercise 19 — Java Sync Driver

Write a Java `find` combining tenant/status/price/capacity with `$near`. Convert it to an aggregation using `$geoNear` and a distance field.

### Exercise 20 — Security and Data Quality

Create a checklist covering coordinate validation, radius caps, Polygons, tenant authorization, private locations, and time zones. Write a test where a client tries to query another tenant's listing.

### Exercise 21 — Nearest In-Stock Store

Propose a schema for store inventory in a chain with 10,000 stores and 100,000 SKUs. Compare embedding `stockBySku` vs. a separate `storeInventory`/materialized search view.

### Exercise 22 — Closest Results Unavailable

Create 25 listings where the 20 closest are already booked. Demonstrate how limiting before the availability lookup returns too few results, and propose a strategy that does not miss eligible top-K matches.

---

## 30. Review Questions

1. Why do geospatial queries usually need to combine business filters?
2. In what order does a GeoJSON Point store coordinates?
3. How must a GeoJSON Polygon close its coordinate ring?
4. What kind of queries does a `2dsphere` index support?
5. By what criterion does `$near` sort results automatically?
6. Which unit does `$maxDistance` use with a GeoJSON Point and `2dsphere`?
7. Does `$near` automatically return a distance field?
8. When should you use `$geoNear`?
9. Where in a pipeline must `$geoNear` be placed?
10. What is `$geoNear.query` used for?
11. Why should you not nest another `$near` inside `$geoNear.query`?
12. How does `$geoWithin` differ from `$near`?
13. What unit does `$centerSphere` expect for its radius?
14. When stored Polygons represent delivery zones and the query is a customer Point, which operator is typically used?
15. Does `$geoIntersects` automatically confirm that a store can currently deliver?
16. How do `$all` and `$in` differ for amenities?
17. Why is a client-supplied `tenantId` insecure?
18. What benefit can a compound `2dsphere` index with business fields provide?
19. Why should you not add every business field into one huge geo index?
20. Does a partial index on `status:"PUBLISHED"` cover `DRAFT` documents?
21. How does a `2dsphere` index handle documents missing `location`?
22. Does `$geoWithin` sort by distance automatically?
23. Why might a listing be nearby yet ineligible?
24. Why must you not limit to 20 before checking bookings when looking for the 20 closest available listings?
25. What is the overlap formula for two booking intervals?
26. Why use half-open `[start,end)` intervals for bookings?
27. Why must local dates be converted with the proper time zone?
28. Is a search result showing availability a booking lock?
29. How do unique night locks help prevent overbooking?
30. If a listing has multiple rooms, how must a single-slot night lock change?
31. Why does road distance differ from geospatial distance?
32. When is a routing service required?
33. Why can deep `skip` pagination be expensive?
34. Why is a tie-breaker needed when sorting by distance?
35. When a user changes their origin, can the old pagination token still be reused?
36. Which `explain` metrics should you inspect?
37. Why must benchmarks use realistic data distributions?
38. How do continuous location updates affect indexes?
39. If a delivery zone covers the customer's point but the store is closed, how should it be handled?
40. How do you prevent leaking exact coordinates of private listings?

---

## 31. Summary

Geospatial querying in MongoDB is not just a distance calculation. In production applications, a result is only valuable when **both geometry and business conditions align**.

Key tools:

- **GeoJSON + `2dsphere`:** represent and index positions/geometries on Earth's surface.
- **`$near` / `$nearSphere`:** find places near a Point, usually prioritized nearest first.
- **`$geoWithin`:** test whether a Point/geometry lies inside a region, without automatic distance sorting.
- **`$geoIntersects`:** test geometric intersection, such as stored delivery Polygons covering a customer Point.
- **`$geoNear`:** first-stage aggregation operator returning a distance field for downstream joins, ranking, and business filtering.
- **Business predicates:** tenant, visibility, verification, price, capacity, amenities, inventory, time/availability, and policies.

Operational principles:

1. **Always verify longitude/latitude order and distance units.**
2. **Never omit security or tenant predicates when applying geo filters.**
3. **Push simple predicates into the query / `$geoNear.query` early to narrow candidates.**
4. **Pick compound/partial geo indexes based on real workloads, measuring with `explain` instead of guessing.**
5. **Do not limit before expensive business checks if doing so drops eligible results.**
6. **Search results do not guarantee inventory or booking availability:** confirmation requires transactions, conditional writes, or unique constraints.
7. **Geographic distance is not ETA or road distance.**
8. **Design ranking and pagination with explicit tie-breakers, especially on dynamic data.**
9. **Define clear policies for Polygon boundaries, time zones, and privacy.**
10. **Test both business correctness and performance across varied radii and data skew.**

The most useful question when designing a "near me" feature is not just **"how do I run `$near`?"**, but **"who is authorized to see the entity, does the entity meet current requirements, and how do we ensure the final decision stays valid when data changes?"**

## References

- [MongoDB Manual — Geospatial Queries](https://www.mongodb.com/docs/manual/geospatial-queries/)
- [MongoDB Manual — GeoJSON Objects](https://www.mongodb.com/docs/manual/reference/geojson/)
- [MongoDB Manual — 2dsphere Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/)
- [MongoDB Manual — Geospatial Index Restrictions](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/restrictions/)
- [MongoDB Manual — Compound Geospatial Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/geospatial/2dsphere/create/)
- [MongoDB Manual — $near](https://www.mongodb.com/docs/manual/reference/operator/query/near/)
- [MongoDB Manual — $nearSphere](https://www.mongodb.com/docs/manual/reference/operator/query/nearSphere/)
- [MongoDB Manual — $geoWithin](https://www.mongodb.com/docs/manual/reference/operator/query/geoWithin/)
- [MongoDB Manual — $geoIntersects](https://www.mongodb.com/docs/manual/reference/operator/query/geoIntersects/)
- [MongoDB Manual — $centerSphere](https://www.mongodb.com/docs/manual/reference/operator/query/centerSphere/)
- [MongoDB Manual — $geoNear](https://www.mongodb.com/docs/manual/reference/operator/aggregation/geoNear/)
- [MongoDB Manual — Query Plans and Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Java Sync Driver — Geospatial Search](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/geo/)
- [MongoDB Java Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/)
