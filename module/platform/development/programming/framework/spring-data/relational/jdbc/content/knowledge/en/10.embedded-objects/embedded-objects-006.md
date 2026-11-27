# Handling All-Null, Partially Null, and Nested Embedded Objects

In **Spring Data Relational JDBC (Spring Data JDBC)**, a value object can be embedded into an entity using `@Embedded`. The value object's properties are flattened into columns of the same table as its containing entity. Consequently, when reading data, the framework must decide when a group of columns represents an **absent embedded object**, when it represents an **object with some null properties**, and when to construct an empty embedded object.

This decision is controlled by `onEmpty` on `@Embedded`:

- `Embedded.OnEmpty.USE_NULL`: if **all columns belonging to the embedded object are SQL NULL**, the property value is materialized as `null`.
- `Embedded.OnEmpty.USE_EMPTY`: if all columns are SQL NULL, the framework still constructs an instance of the embedded type; inner properties receive corresponding null/default values.

With nested embedded objects, each level can have its own prefix and `onEmpty` policy. Clearly understanding each level's column scope helps avoid confusing "address does not exist", "address exists without a city", and "address exists without coordinates".

## 1. How Are Embedded Objects Stored?

Suppose a customer profile has a shipping address. The address consists of street, city, and an optional coordinates object. Coordinates in turn consist of latitude and longitude.

Java model:

~~~text
CustomerProfile
  id
  displayName
  shippingAddress: Address
      street
      city
      geoPoint: GeoPoint
          latitude
          longitude
~~~

With Spring Data JDBC, properties are flattened into the table:

~~~text
customer_profiles
  id
  display_name
  shipping_street
  shipping_city
  shipping_geo_latitude
  shipping_geo_longitude
~~~

~~~mermaid
flowchart TB
    Profile["CustomerProfile<br/>Entity / Aggregate Root"]
    Address["Address<br/>Value Object"]
    Geo["GeoPoint<br/>Nested Value Object"]
    Profile -->|"@Embedded<br/>prefix = shipping_"| Address
    Address -->|"@Embedded<br/>prefix = geo_"| Geo
    Profile --> Table[("customer_profiles")]
    Address --> Table
    Geo --> Table
    Table --- C1["shipping_street"]
    Table --- C2["shipping_city"]
    Table --- C3["shipping_geo_latitude"]
    Table --- C4["shipping_geo_longitude"]
~~~

Two levels of value objects **do not create two separate tables**. They are values belonging to the profile, stored as columns in the `customer_profiles` table. `@Embedded` is not a `@OneToOne` relationship and does not need a foreign key joining to an address table.

## 2. The USE_NULL and USE_EMPTY Rules

`onEmpty` only inspects the state of **all columns within the embedded object's scope**. The two options have different meanings:

| Configuration | All Object Columns Are SQL NULL | Result on Read |
|---|---|---|
| `USE_NULL` | Yes | Embedded property is Java `null` |
| `USE_EMPTY` | Yes | Framework constructs an instance; inner fields map from null/default values |
| Both | At least one column is non-NULL | Framework constructs an instance and maps each property |

Example:

~~~java
@Embedded(
    prefix = "shipping_",
    onEmpty = Embedded.OnEmpty.USE_NULL
)
private Address shippingAddress;
~~~

If `shipping_street`, `shipping_city`, `shipping_geo_latitude`, and `shipping_geo_longitude` are all SQL `NULL`, `shippingAddress` is read as Java `null`.

If `shipping_street = '12 Nguyen Trai'` while the remaining columns are `NULL`, `shippingAddress` is still an `Address` object; only the properties without data hold null values. The framework does not discard the entire object merely because some child columns are null.

If `USE_EMPTY` is used:

~~~java
@Embedded(
    prefix = "billing_",
    onEmpty = Embedded.OnEmpty.USE_EMPTY
)
private Address billingAddress;
~~~

When all `billing_*` columns are SQL `NULL`, `billingAddress` is still constructed as an `Address` instance with corresponding null/default fields.

**Key takeaway:** `USE_NULL` distinguishes "no embedded value" via the all-null state; `USE_EMPTY` actively turns that all-null state into an empty object. Whenever at least one column is non-null, both policies must construct the object to preserve the stored value.

## 3. Java Example with Two Levels of Embedded Objects

We use three types:

- `CustomerProfile` is the entity persisted to the table.
- `Address` is a value object embedded in the profile.
- `GeoPoint` is a value object embedded in Address.

### GeoPoint.java

~~~java
package com.example.profile;

public class GeoPoint {

    private Double latitude;
    private Double longitude;

    protected GeoPoint() {
        // For Spring Data JDBC.
    }

    public GeoPoint(Double latitude, Double longitude) {
        this.latitude = latitude;
        this.longitude = longitude;
    }

    public Double getLatitude() {
        return latitude;
    }

    public Double getLongitude() {
        return longitude;
    }
}
~~~

We use `Double` instead of `double` because coordinates can be missing. If primitive `double` is used, Java cannot represent null and the default value is usually `0.0`; this loses the distinction between "no coordinates yet" and coordinates literally equal to 0.

### Address.java

~~~java
package com.example.profile;

import org.springframework.data.relational.core.mapping.Embedded;

public class Address {

    private String street;
    private String city;

    @Embedded(
        prefix = "geo_",
        onEmpty = Embedded.OnEmpty.USE_NULL
    )
    private GeoPoint geoPoint;

    protected Address() {
        // For Spring Data JDBC.
    }

    public Address(String street, String city, GeoPoint geoPoint) {
        this.street = street;
        this.city = city;
        this.geoPoint = geoPoint;
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }

    public GeoPoint getGeoPoint() {
        return geoPoint;
    }
}
~~~

At the `Address` level, coordinate columns use prefix `geo_`. When `Address` is embedded into `Profile` with prefix `shipping_`, the final column names combine into `shipping_geo_latitude` and `shipping_geo_longitude`.

### CustomerProfile.java

~~~java
package com.example.profile;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer_profiles")
public class CustomerProfile {

    @Id
    private Long id;

    private String displayName;

    @Embedded(
        prefix = "shipping_",
        onEmpty = Embedded.OnEmpty.USE_NULL
    )
    private Address shippingAddress;

    @Embedded(
        prefix = "billing_",
        onEmpty = Embedded.OnEmpty.USE_EMPTY
    )
    private Address billingAddress;

    protected CustomerProfile() {
        // For Spring Data JDBC.
    }

    public CustomerProfile(
            String displayName,
            Address shippingAddress,
            Address billingAddress) {
        this.displayName = displayName;
        this.shippingAddress = shippingAddress;
        this.billingAddress = billingAddress;
    }

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public Address getShippingAddress() {
        return shippingAddress;
    }

    public Address getBillingAddress() {
        return billingAddress;
    }
}
~~~

In this example:

- `shippingAddress` uses `USE_NULL`: if all `shipping_*` columns are null, the object is null.
- `billingAddress` uses `USE_EMPTY`: if all `billing_*` columns are null, an empty `Address` instance still exists.
- Inside `Address`, `geoPoint` uses `USE_NULL`: if `Address` exists yet both coordinate columns are null, `geoPoint` is null.

Policies are configured **per embedded property**, not as a global setting applied to every value object in the application.

## 4. Nested Prefixes and Final Column Names

Outer and inner prefixes are concatenated. With the annotations above:

| Java Property | Outer Prefix | Inner Prefix | SQL Column |
|---|---|---|---|
| `shippingAddress.street` | `shipping_` | — | `shipping_street` |
| `shippingAddress.city` | `shipping_` | — | `shipping_city` |
| `shippingAddress.geoPoint.latitude` | `shipping_` | `geo_` | `shipping_geo_latitude` |
| `shippingAddress.geoPoint.longitude` | `shipping_` | `geo_` | `shipping_geo_longitude` |
| `billingAddress.street` | `billing_` | — | `billing_street` |
| `billingAddress.geoPoint.latitude` | `billing_` | `geo_` | `billing_geo_latitude` |

When embedding the same `Address` type multiple times in an entity, distinct prefixes prevent column name collisions. Without prefixes, fields such as `street` or `city` can collide or fail to produce the intended mapping.

Prefixes also help schema readers tell which column group belongs to which value object. Choose prefix names consistent with the domain, usually ending with an underscore for readable column names.

## 5. SQL Schema for Embedded Objects

Since both shipping and billing addresses may be absent or partially missing, embedded object columns must allow null in the illustrative schema:

~~~sql
CREATE TABLE customer_profiles (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL,

    shipping_street VARCHAR(160),
    shipping_city VARCHAR(100),
    shipping_geo_latitude DOUBLE PRECISION,
    shipping_geo_longitude DOUBLE PRECISION,

    billing_street VARCHAR(160),
    billing_city VARCHAR(100),
    billing_geo_latitude DOUBLE PRECISION,
    billing_geo_longitude DOUBLE PRECISION
);
~~~

This is PostgreSQL syntax. In MySQL, replace the ID column with `BIGINT AUTO_INCREMENT` and use a suitable numeric type such as `DOUBLE` for coordinates. Address columns still need to allow `NULL` to represent an absent object or an object with missing fields.

There is no separate `addresses` table in this model. If addresses must be shared, have an independent lifecycle, or participate in many reference relationships, consider a separate entity/aggregate and store a reference ID instead of an embedded value object.

## 6. Four Common Data States

Assume `shippingAddress` uses `USE_NULL` and `Address.geoPoint` uses `USE_NULL`.

| State | shipping_street | shipping_city | geo_latitude | geo_longitude | Result on Read |
|---|---|---|---|---|---|
| No address | NULL | NULL | NULL | NULL | `shippingAddress == null` |
| Has address, missing city and coordinates | Has value | NULL | NULL | NULL | Address exists; city null; geoPoint null |
| Has address and partial coordinates | Has value | Has value | Has value | NULL | Address exists; GeoPoint exists with longitude null |
| Complete address | Has value | Has value | Has value | Has value | Address and GeoPoint both have all fields |

Sample data rows:

~~~sql
INSERT INTO customer_profiles (
    display_name,
    shipping_street,
    shipping_city,
    shipping_geo_latitude,
    shipping_geo_longitude
) VALUES
    ('An', NULL, NULL, NULL, NULL),
    ('Binh', '12 Nguyen Trai', NULL, NULL, NULL),
    ('Chi', '25 Le Loi', 'Da Nang', 16.0678, NULL),
    ('Dung', '1 Dong Khoi', 'Ho Chi Minh City', 10.7769, 106.7009);
~~~

Mapping outcomes:

- Profile `An`: all shipping columns are null, so `shippingAddress` is null.
- Profile `Binh`: has street, so `shippingAddress` is an object; city is null; both geo columns are null so `geoPoint` is null.
- Profile `Chi`: Address exists; latitude has a value so GeoPoint is constructed; longitude remains null.
- Profile `Dung`: Address and GeoPoint both have complete values.

### All-NULL vs. Partially NULL

Under `USE_NULL`, the framework does not check "whether every property is complete". It only checks **whether at least one column in the embedded object's scope is not SQL NULL**:

~~~text
All columns = NULL
    -> embedded object = null

At least one column != NULL
    -> create embedded object
       -> each property is mapped individually
       -> any SQL NULL property gets its corresponding null/default value
~~~

Therefore, a street value with a null city is a valid Address from a mapping standpoint. Whether that address is valid for the business is the responsibility of validation/domain logic and can be reinforced with a CHECK constraint.

## 7. Handling Empty Objects with USE_EMPTY

Change `shippingAddress`'s policy to:

~~~java
@Embedded(
    prefix = "shipping_",
    onEmpty = Embedded.OnEmpty.USE_EMPTY
)
private Address shippingAddress;
~~~

When all `shipping_*` columns are SQL NULL, Spring Data JDBC still constructs an `Address` instance. The result looks like:

~~~java
Address address = profile.getShippingAddress();

// address is non-null
// address.getStreet() == null
// address.getCity() == null
// address.getGeoPoint() == null (because nested embedded uses USE_NULL)
~~~

This is useful when the domain wants an object always available to call methods on or to represent a group of values not yet provided. However, ensure the embedded type can be instantiated with null/default fields.

### Watch Out for Primitive Types

Suppose coordinates are declared as:

~~~java
private double latitude;
private double longitude;
~~~

Java has no null value for `double`; if the corresponding columns are SQL NULL and the framework creates an empty object, primitive fields may receive a default value of `0.0`. At that point, the application cannot distinguish:

- coordinates not yet provided;
- coordinates actually equal to 0.

For nullable properties, use wrappers such as `Double`, `Integer`, `Boolean`, or corresponding reference types. Use primitives when the domain guarantees the value always exists and the schema has matching constraints.

### USE_EMPTY Does Not Mean Generating Business Default Values

`USE_EMPTY` merely builds an instance from empty data; it does not fill in a default address, call a geocoding service, or synthesize values like `"Unknown"`. If default values are needed, put explicit rules in a constructor/factory or application/domain service, and consider the impact when reading legacy data.

## 8. Nested Embedded Objects Have Independent Policies

In the example, `shippingAddress` can exist while `geoPoint` can be absent. The two properties have two distinct column scopes:

- `shippingAddress` considers all of `shipping_street`, `shipping_city`, `shipping_geo_latitude`, and `shipping_geo_longitude`.
- Once `Address` is constructed, `geoPoint` separately inspects `shipping_geo_latitude` and `shipping_geo_longitude`.

With outer `USE_NULL` and inner `USE_NULL`:

| Shipping Columns | Address | GeoPoint |
|---|---|---|
| All null | null | No parent exists to hold GeoPoint |
| Street has value; geo all null | Object | null |
| Street has value; one coordinate has value | Object | Object with remaining field null |
| Street and both coordinates have values | Object | Object |

If the inner policy changes to `USE_EMPTY`, in the second row `Address` still exists and `GeoPoint` is created as an empty object. If the outer policy changes to `USE_EMPTY` and all outer columns are null, `Address` is still created; then `GeoPoint`'s `onEmpty` policy determines the nested property.

**The parent level can prevent observing the child level:** when `Address` resolves to null, there is no `Address` object through which to access `GeoPoint`. Therefore, when designing nested embedded objects, examine both outer and inner policies—do not read only the annotation on `GeoPoint`.

## 9. Distinguishing NULL from Empty Strings and Default Values

The `onEmpty` rule is based on **SQL NULL**, not "fields that look empty":

| Column Value | Treated as SQL NULL? | Effect with USE_NULL |
|---|---|---|
| `NULL` | Yes | If all columns in embedded are NULL, object is null |
| `''` | No | At least one column is non-NULL, object is created |
| `'   '` | No | Object is created; string contains spaces |
| Number `0` | No | Object is created |
| Boolean `FALSE` | No | Object is created |

For example, if `shipping_street = ''` while other columns are null, `shippingAddress` is still an object because street is not SQL NULL. If the business rejects empty or whitespace-only strings, check separately via validation and/or a CHECK constraint.

Do not use `USE_NULL` as an automatic mechanism to strip empty strings. The two concepts serve different purposes:

- `onEmpty` decides **whether to construct the object** based on nullness across the entire column group.
- Validation decides **whether each field's value is valid**, such as street having non-blank content.

## 10. Validation for Partially Embedded Objects

An `Address` can be mapped into an object even with only a street, yet business rules may require street and city to always appear together. You can place checks in a factory or domain method:

~~~java
public static Address create(
        String street,
        String city,
        GeoPoint geoPoint) {
    if (street == null || street.isBlank()) {
        throw new IllegalArgumentException("Street is required");
    }
    if (city == null || city.isBlank()) {
        throw new IllegalArgumentException("City is required");
    }
    return new Address(street, city, geoPoint);
}
~~~

For data read from the database, the mapping constructor/factory must be compatible with nullable states allowed by the schema. If legacy data can lack a city, do not write a constructor requiring city to be non-null and expect `USE_NULL` to fix the data automatically. Instead:

1. Determine which columns are allowed to be null under the data contract.
2. Construct the object in the corresponding state.
3. Validate completeness in use cases that require the address, or migrate legacy data before tightening constraints.
4. On new writes, validate so that new partial states disallowed by the domain are not created.

If all embedded columns must have values whenever the object exists, an SQL constraint can force fields to appear together. PostgreSQL example:

~~~sql
ALTER TABLE customer_profiles
ADD CONSTRAINT ck_shipping_address_complete
CHECK (
    (shipping_street IS NULL AND shipping_city IS NULL)
    OR
    (shipping_street IS NOT NULL AND shipping_city IS NOT NULL)
);
~~~

The constraint above illustrates just one rule: street and city are either both absent or both present. It does not require coordinates to exist. Design CHECK constraints to match actual policy; avoid accidentally forbidding states permitted by the business.

## 11. When Can States Not Be Distinguished by Embedded Columns Alone?

Suppose you need to distinguish two situations:

1. The user **has not created an address yet**.
2. The user **has created an Address**, though every field is currently blank because an input workflow is awaiting completion.

If both situations store all `shipping_*` columns as SQL NULL, the physical data is identical. No read algorithm can recover meaning that was never stored.

There are three design options:

- **Accept merging the two states:** use `USE_NULL` if an all-null object means no object exists.
- **Use USE_EMPTY:** if reading an all-null object should always yield an empty instance, regardless of whether the user had previously created it.
- **Store a presence flag:** add a column such as `shipping_present BOOLEAN NOT NULL` to distinguish an absent object from an existing object whose properties have no values yet.

Example with a presence flag:

~~~sql
ALTER TABLE customer_profiles
ADD COLUMN shipping_present BOOLEAN NOT NULL DEFAULT FALSE;
~~~

In that case, the domain must explicitly map and handle `shipping_present`. Adding the column without using it in object reconstruction logic will not solve the problem. Another alternative is using a separate table if the address has its own lifecycle, identity, or relationships.

## 12. Repository Reading and Writing Embedded Objects

Because `Address` and `GeoPoint` are embedded value objects, the repository is defined for their containing entity:

~~~java
package com.example.profile;

import org.springframework.data.repository.CrudRepository;

public interface CustomerProfileRepository
        extends CrudRepository<CustomerProfile, Long> {
}
~~~

Saving a profile:

~~~java
Address address = new Address(
    "12 Nguyen Trai",
    "Hanoi",
    new GeoPoint(21.0285, 105.8542)
);

CustomerProfile profile = new CustomerProfile(
    "Nguyen An",
    address,
    null
);

CustomerProfile saved = repository.save(profile);
Long id = saved.getId();
~~~

Reading back:

~~~java
CustomerProfile loaded = repository.findById(id)
    .orElseThrow();

Address shipping = loaded.getShippingAddress();
if (shipping != null) {
    System.out.println(shipping.getStreet());

    GeoPoint point = shipping.getGeoPoint();
    if (point != null) {
        System.out.println(point.getLatitude());
        System.out.println(point.getLongitude());
    }
}
~~~

`findById` loads the entity along with its embedded values according to its column mapping. There is no join to an address table because the columns reside in the same table. The repository needs neither `AddressRepository` nor `GeoPointRepository`.

With the mutable classes in this example, `save` returns the persisted entity; continue using the returned value, especially when the ID is database-generated. `@Embedded` does not change this rule.

## 13. Inspecting SQL Data Directly

Query columns to observe all-null and partially null states:

~~~sql
SELECT
    id,
    display_name,
    shipping_street,
    shipping_city,
    shipping_geo_latitude,
    shipping_geo_longitude,
    CASE
        WHEN shipping_street IS NULL
         AND shipping_city IS NULL
         AND shipping_geo_latitude IS NULL
         AND shipping_geo_longitude IS NULL
        THEN 'ALL_NULL'
        ELSE 'HAS_VALUE'
    END AS shipping_state
FROM customer_profiles
ORDER BY id;
~~~

For nested `GeoPoint`, inspect only the two coordinate columns:

~~~sql
SELECT
    id,
    CASE
        WHEN shipping_geo_latitude IS NULL
         AND shipping_geo_longitude IS NULL
        THEN 'GEO_ALL_NULL'
        ELSE 'GEO_HAS_VALUE'
    END AS geo_state
FROM customer_profiles
ORDER BY id;
~~~

These queries illustrate how the database represents physical state. Whether Java receives `null` or an empty object also depends on `onEmpty` at each level.

## 14. Common Mistakes with Nested Embedded Objects

| Mistake | Consequence | Resolution |
|---|---|---|
| Assuming one null child column makes the entire object null | Losing fields that still have values | Only when all embedded columns are null does `USE_NULL` trigger |
| Assuming an empty string equals SQL NULL | Object may still be created even if string has no content | Distinguish `NULL`, `''`, and whitespace strings |
| Using `USE_EMPTY` when embedded type rejects null fields | Constructor/mapping may fail | Allow empty state or use `USE_NULL` policy |
| Using primitives for nullable fields | Null turns into defaults like 0/false or cannot be represented accurately | Use wrapper/reference types |
| Omitting prefix when embedding the same type twice | Column name collision or ambiguous mapping | Set distinct prefixes per property |
| Forgetting to concatenate prefixes across levels | Querying wrong column names | Outer and inner prefixes form nested column names |
| Assuming embedded creates a separate table | Wrong schema design | Embedded flattens into the containing table |
| Using embedded for an object with independent identity/lifecycle | Blurred domain boundaries | Consider a separate entity/aggregate and store ID |
| Relying on `USE_NULL` to validate an address | Partial objects are still constructed | Validate required fields in domain/service and DB |
| Needing to distinguish absent vs. empty when all columns are null | Original state cannot be recovered | Use a presence flag or another storage model |

## 15. Practice Exercises

1. Create the `customer_profiles` table per the example schema and map `CustomerProfile` with `shippingAddress` using `USE_NULL`.
2. Insert a row with all `shipping_*` columns set to NULL. Read it back and confirm `getShippingAddress() == null`.
3. Insert a row with only `shipping_street`. Read it back and confirm Address is non-null while city and geoPoint are null.
4. Insert a row with street and latitude while longitude is null. Confirm GeoPoint is created with one null field.
5. Change `shippingAddress` to `USE_EMPTY`. Read the first row again and observe that Address is created even when all columns are null.
6. Change nested `geoPoint` to `USE_EMPTY`. For the row with street but both coordinate columns null, observe that GeoPoint is an empty object.
7. Try storing `shipping_street = ''` and `shipping_street = '   '`. Explain why `USE_NULL` does not treat these two values as null.
8. Embed `Address` a second time for the billing address. Set prefix `billing_` and determine the final column names, including GeoPoint's prefix.
9. Add a domain rule requiring street and city to coexist. Decide whether to validate in a factory/service, CHECK constraint, or both.
10. Propose a schema with `shipping_present` if you need to distinguish "no address yet" from "started creating an address without entering any fields".

While doing the exercises, check all three simultaneously: **database values**, **parent-level `onEmpty` configuration**, and **child-level `onEmpty` configuration**. Never inspect only one Java property to infer the entire data state.

## 16. Summary

`@Embedded` represents value objects using columns flattened into the containing entity's table. `USE_NULL` turns an all-SQL-NULL column group into a Java null property; `USE_EMPTY` constructs an instance even when all columns are null. When some columns have values, the object is created and missing properties are mapped to corresponding null/default values.

With nested embedded objects, **each level has its own prefix and `onEmpty` rule**. Prefixes prevent column name collisions; the outer rule determines whether the parent object exists, and then the inner rule determines the child object. Finally, `onEmpty` only governs object construction from SQL NULL states; it does not replace business validation, does not turn empty strings into null, and cannot recover states that the schema never stored.
