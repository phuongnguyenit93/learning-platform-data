# Mapping @Document, @Id, @Field, and Nested Document Structures in Spring Data MongoDB

## 1. Problem Statement: From Java Objects to MongoDB Documents

A rental listing management service written in **Java and Spring Boot** needs to store the following information:

~~~text
Listing
  id
  tenantId
  title
  monthlyRent
  address
    cityCode
    district
    coordinates
      longitude
      latitude
  rooms[]
    type
    areaSqm
    amenities[]
  tags[]
  createdAt
~~~

In Java, developers want to follow **camelCase** property naming conventions: `monthlyRent`, `cityCode`, `createdAt`. In MongoDB, the storage team has standardized fields in **snake_case** such as `monthly_rent`, `city_code`, and `created_at`. The primary identifier field must be stored at **_id**, while `address` and `rooms` should be kept as **embedded documents** rather than creating separate collections for every small object.

Spring Data MongoDB provides an **object-document mapping** mechanism to convert between the two representations:

~~~text
                 Java application
                       |
                       v
            ListingDocument (POJO)
              id: ObjectId
              tenantId: String
              address: Address
              rooms: List<Room>
                       |
                       v
        Spring Data MongoDB mapping layer
            MappingMongoConverter
                       |
                       v
                BSON document
              _id: ObjectId
              tenant_id: String
              address: { ... }
              rooms: [ { ... }, ... ]
                       |
                       v
                   MongoDB
              rental_listings_398
~~~

Three core annotations:

- **@Document:** declares a Java type used as a MongoDB root document and configures its collection.
- **@Id:** declares the identifier property, mapping to the BSON **_id** field.
- **@Field:** configures the BSON field name or representation options for a property, such as target type.

Child objects, lists, and maps are generally mapped recursively into **embedded documents/arrays** even when the child class has no `@Document` annotation.

### Learning Objectives

After this lesson, you will be able to:

1. Explain the **Java object → MappingMongoConverter → BSON** pipeline and its reverse direction.
2. Use **@Document(collection = "...")** to specify the root document's collection.
3. Use **@Id** properly with **_id**, and distinguish between `ObjectId`, String IDs, and `@MongoId`.
4. Use **@Field** to set custom storage field names, such as `monthlyRent` → `monthly_rent`.
5. Map **embedded objects, multi-level nested objects, Lists, and Maps**.
6. Read actual BSON and recognize **_class**, BSON Date, Decimal128, arrays, null, and missing fields.
7. Query nested properties using **MongoRepository** and **MongoTemplate**.
8. Design indexes based on **BSON field names** and nested paths.
9. Distinguish **embedding**, **DBRef**, and **DocumentReference** in terms of how data is stored.
10. Handle schema evolution, field renaming, and data-loss risks when saving legacy documents.
11. Test mapping and avoid confusing it with business validation or authorization.
12. Implement a complete lab with packages, model classes, repository, service, and `mongosh` verification.

> **Version Scope:** Examples use Java 17+ syntax and corresponding Spring Boot 3.x/Spring Data MongoDB APIs as a learning baseline. Minor APIs, auto-index creation behavior, or driver configuration may vary by version; consult the official documentation for your target version. Examples only use the lab database **mongo_mapping_lab_398**, collection **rental_listings_398**, and synthetic data. Never connect to or modify production for practice.

## 2. What Role Does Spring Data MongoDB Mapping Play?

### 2.1. BSON Is Not a Java Object

MongoDB stores **BSON documents**. A document can contain:

~~~javascript
{
  _id: ObjectId("660000000000000000000398"),
  tenant_id: "tenant-001",
  title: "Studio near the park",
  monthly_rent: NumberDecimal("12500000.00"),
  address: {
    city_code: "HCM",
    district: "Binh Thanh",
    coordinates: {
      longitude: 106.71,
      latitude: 10.80
    }
  },
  rooms: [
    {
      type: "bedroom",
      area_sqm: 22,
      amenities: ["desk", "wifi"]
    }
  ],
  tags: ["near-park", "furnished"],
  created_at: ISODate("2026-01-15T09:30:00Z")
}
~~~

Java has classes, private fields, constructors, records, generics, and enums. BSON has storage types such as **ObjectId, Date, Decimal128, string, number, boolean, document, array, and null**.

The mapping layer must decide:

- Which Java property corresponds to which BSON field name?
- Which Java type corresponds to which BSON type?
- Should a nested object be embedded inside the parent document?
- Which property is the ID?
- Which constructor should be used when reading BSON?
- When a field is missing, does Java receive null, a primitive default, or a constructor-supplied value?
- Is a custom converter needed?

### 2.2. MappingMongoConverter

In Spring Data MongoDB, the core mapping component is **MappingMongoConverter**, which uses mapping metadata and conversions to translate between Java objects and BSON `Document` instances.

Diagram:

~~~text
MongoRepository / MongoTemplate
              |
              v
       MappingMongoConverter
              |
       +------+------+
       |             |
  Mapping context   Custom conversions
       |             |
 @Document/@Id/    Converter Java <-> BSON
 @Field/metadata    when registered
       |             |
       +------+------+
              |
              v
         MongoDB Driver
              |
              v
             BSON
~~~

This differs from using the raw Java driver to manually build `Document` instances:

~~~java
Document raw = new Document()
    .append("tenant_id", "tenant-001")
    .append("title", "Studio");
~~~

With Spring Data, we can persist a **ListingDocument** while the mapping layer handles field name translation, nested types, and ID mapping.

### 2.3. Annotations Assist Mapping, Not Validation

**@Document** and **@Field** do not automatically enforce a fixed schema on every document in MongoDB. A `mongosh` client or another service can still write documents missing fields if the server lacks proper validation.

To validate input data, you must add:

- Java Bean Validation and checks at the API/service layer.
- Business invariants.
- MongoDB **$jsonSchema validation** if enforcement at the database level is required.
- Tests and migrations when schemas change.

Never treat mapping annotations as an automatic database constraint mechanism.

## 3. Preparing the Spring Boot and MongoDB Lab

### 3.1. Dependency

A Spring Boot application uses the starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
~~~

Spring Boot manages dependency versions through its dependency management BOM. Do not arbitrarily mix a newer Spring Data MongoDB release with an incompatible Spring Boot version.

If using Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
}
~~~

Both **Spring Data MongoRepository** and **MongoTemplate** used in the examples are included in the standard starter.

### 3.2. Local Lab application.yml

~~~yaml
spring:
  data:
    mongodb:
      uri: "mongodb://127.0.0.1:27017/mongo_mapping_lab_398"
~~~

This is strictly a URI for a **local lab** MongoDB instance. Production requires TLS, credentials from a secret manager, a least-privilege database user, and proper network configuration. Never commit real passwords into `application.yml`.

Spring Boot also supports configuration via environment variables or runtime secret injection. Do not hardcode credentials in source code.

### 3.3. Illustrative Package Structure

~~~text
src/main/java/com/example/mongo398/
  Mongo398Application.java
  domain/
    ListingDocument.java
    Address.java
    Coordinates.java
    Room.java
  repository/
    ListingRepository.java
  service/
    ListingService.java
~~~

The filenames in this lesson are **illustrative learning descriptions**, not external files created by the worker.

### 3.4. Connections and Permissions

A CRUD service needs sufficient permissions for its read/write operations. If a deployment is read-only, it must not use `root`. If an application creates indexes on startup, index management privileges should be separated into a migration job where appropriate.

To focus on mapping behavior, we use an isolated lab instead of enabling auto-index creation on a production cluster.

## 4. @Document: Java Type Representing a Collection

### 4.1. Basic Syntax

~~~java
package com.example.mongo398.domain;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "rental_listings_398")
public class ListingDocument {

    @Id
    private ObjectId id;

    private String title;

    protected ListingDocument() {
        // Constructor for the mapping framework.
    }

    public ListingDocument(String title) {
        this.title = title;
    }

    public ObjectId getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
~~~

**@Document(collection = "rental_listings_398")** specifies that this root object is stored in the **rental_listings_398** collection when using default mapping APIs for that type.

If no collection is specified, Spring Data uses a naming convention to derive the collection name from the type; however, that convention may not match an existing schema. Specifying the name explicitly prevents accidental collection changes during class refactoring.

### 4.2. @Document Is Not Equivalent to SQL CREATE TABLE

MongoDB creates collections on first write according to server behavior; merely declaring `@Document` **does not guarantee the collection already exists**.

~~~text
@Document read by mapping context
                 |
                 v
           Mapping metadata
                 |
            insert/save
                 |
                 v
          MongoDB collection
~~~

If you need collection validators, collation, indexes, or controlled collection creation, use an appropriate migration or administrative workflow.

### 4.3. An Entity Binds to One Default Collection

~~~java
@Document(collection = "tenant_listings")
public class TenantListing {
    @Id
    private String id;
}
~~~

This maps the entity type to a default collection. It does not mean a class can only ever be used with a single collection across every API: `MongoTemplate` provides overloads that accept an explicit collection name at operation time.

However, dynamic collection overrides require managing consistency, indexes, tenant authorization, and migrations. Never accept arbitrary collection names directly from user requests.

### 4.4. Is @Document Needed on Nested Classes?

No. An **Address** class can simply be an embedded value object:

~~~java
public class Address {
    private String cityCode;
    private String district;
}
~~~

When `Address` is a property of `ListingDocument`, Spring Data writes it as a subdocument. There is no need to add `@Document` to `Address` just to embed it.

**@Document does not automatically turn properties referencing that class into cross-collection relationships.** References are a separate design choice, such as `@DBRef` or `@DocumentReference`.

## 5. @Id: Which Property Becomes BSON _id?

### 5.1. The MongoDB _id Field

In a MongoDB collection, every document has an **_id** field serving as its unique identifier within that collection. Spring Data uses **@Id** to identify the Java property mapped to that field:

~~~java
@Id
private ObjectId id;
~~~

BSON:

~~~javascript
{
  _id: ObjectId("660000000000000000000398"),
  title: "Studio"
}
~~~

There is no separate BSON field named **id** in the document above.

### 5.2. The Java Property Name Does Not Have to Be id

~~~java
@Id
private ObjectId listingId;
~~~

The Java property named **listingId** still maps to **_id** when written to BSON.

Therefore, in Java:

~~~java
listing.getListingId()
~~~

and in `mongosh`:

~~~javascript
db.rental_listings_398.findOne({
  _id: ObjectId("660000000000000000000398")
});
~~~

refer to the exact same identifier.

### 5.3. When Is ObjectId Generated?

When inserting a new object with an **ObjectId** field whose value is unset, Spring Data or the driver can auto-generate an ID depending on the mapping/insertion path. If you want complete explicitness in the lab, you can **assign the ObjectId explicitly**:

~~~java
ObjectId id = new ObjectId();
~~~

Never generate a brand-new `ObjectId` every time you **save** an existing entity, as doing so can cause the write to create a separate document.

### 5.4. @Id String Has Important Conversion Rules

~~~java
@Id
private String id;
~~~

Spring Data MongoDB applies ID conversion rules. A valid 24-character hex string ID may be converted into a **BSON ObjectId**, whereas other strings may be stored as **BSON String** depending on the mapping path.

Illustrative behavior:

~~~text
Java id: "660000000000000000000398"
  -> may be stored as BSON ObjectId

Java id: "listing-398"
  -> stored as String
~~~

Do not assume every `@Id String` is stored as a BSON string. Type mismatches can cause raw driver or `mongosh` queries to miss matching documents.

### 5.5. @MongoId to Control the ID's BSON Type

If you want an ID stored **strictly as a String** even when it resembles an ObjectId, Spring Data provides **@MongoId**.

~~~java
import org.springframework.data.mongodb.core.mapping.MongoId;
import org.springframework.data.mongodb.core.mapping.FieldType;

public class ExternalListing {

    @MongoId(FieldType.STRING)
    private String id;

    public String getId() {
        return id;
    }
}
~~~

**@MongoId(FieldType.STRING)** explicitly expresses the intent to store the ID as a BSON string; **@MongoId(FieldType.OBJECT_ID)** expresses the intent for an ObjectId. Syntax and conversion behavior should always be tested against your actual Spring Data version.

**Do not declare both @Id and @MongoId on the same property** as two competing sources of truth. Choose one strategy.

### 5.6. ObjectId vs. UUID vs. Domain Key

| ID strategy | Advantages | Considerations |
| --- | --- | --- |
| **ObjectId** | Common, BSON native, convenient generation | DTOs/REST often convert to hex string |
| **Business-meaningful String** | Easy integration with external systems | BSON type and key length/index size need control |
| **UUID** | Distributed generation, low server coupling | Driver/UUID representation must be consistent |
| **Compound business identity** | Represents business key directly | `_id` is a single field; can use embedded ID or unique index depending on design |

An `_id` alone does not enforce **tenant authorization**. When reading a listing by ID, the application must still verify the tenant/owner:

~~~java
// Concept: must have an authenticated tenantId.
// Querying by _id alone does not prevent cross-tenant access.
~~~

### 5.7. Do Not Arbitrarily Change _id Type During Migration

If a collection already contains:

~~~javascript
{ _id: ObjectId("660000000000000000000398") }
~~~

then a query for:

~~~javascript
{ _id: "660000000000000000000398" }
~~~

is not equivalent in BSON because String and ObjectId are distinct types. Old and new records will fail to match if you switch from ObjectId to String without a proper migration.

## 6. @Field: Mapping Property Names to BSON Field Names

### 6.1. Basic Example

~~~java
@Field("tenant_id")
private String tenantId;

@Field("monthly_rent")
private BigDecimal monthlyRent;

@Field("created_at")
private Instant createdAt;
~~~

Java:

~~~text
tenantId
monthlyRent
createdAt
~~~

MongoDB:

~~~text
tenant_id
monthly_rent
created_at
~~~

**@Field does not rename the Java variable.** It describes the name used during persistence mapping.

### 6.2. Omit @Field When Names Match

If both the Java property and BSON field are named **title**, you can simply declare:

~~~java
private String title;
~~~

Spring Data maps it by convention. You may add `@Field("title")` to state the contract explicitly, though it is not required.

### 6.3. @Field and @Id Have Different Responsibilities

| Annotation | Purpose | Resulting BSON |
| --- | --- | --- |
| `@Document(collection = "rental_listings_398")` | Specifies root collection | Collection name |
| `@Id ObjectId id` | Document identifier | `_id` |
| `@Field("tenant_id") String tenantId` | Data field name | `tenant_id` |
| `@Field("monthly_rent") BigDecimal monthlyRent` | Field name and optional type config | `monthly_rent` |

**_id is a special field.** Do not try to use `@Field("listingId")` to replace `@Id` semantics. If a domain ID is stored under another field name, understand that it is **a regular field** or an explicit custom identity design—it does not rename `_id`.

### 6.4. @Field targetType

For monetary data, **BigDecimal** is a Java type that represents decimal values more accurately than floating-point numbers. MongoDB provides the **Decimal128** type:

~~~java
import java.math.BigDecimal;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Field(
    value = "monthly_rent",
    targetType = FieldType.DECIMAL128
)
private BigDecimal monthlyRent;
~~~

MongoDB document:

~~~javascript
{
  monthly_rent: NumberDecimal("12500000.00")
}
~~~

**Do not assume BigDecimal is stored as Decimal128 under every configuration or converter.** Depending on annotations and registered conversions, storage representation can differ. For monetary values, standardize domain policies for currency, scale, and rounding, backed by tests and schema validation.

### 6.5. Changing @Field Does Not Automatically Update Existing Data

If an older class had:

~~~java
private String postalCode;
~~~

storing BSON field **postalCode**, and you change it to:

~~~java
@Field("postal_code")
private String postalCode;
~~~

Spring Data begins reading and writing **postal_code** under the new mapping. Existing documents that only have **postalCode** are not automatically renamed in MongoDB.

Consequences:

- Reading older records may yield null for the property.
- Queries targeting the new property may miss older documents.
- Saving an entire document can inadvertently drop or overwrite the old field with the new shape.

Plan a proper migration rather than treating annotations like a live `ALTER COLUMN`.

## 7. Complete Java Model: Root and Embedded Value Objects

### 7.1. Root Document

Illustrative file **ListingDocument.java**:

~~~java
package com.example.mongo398.domain;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document(collection = "rental_listings_398")
public class ListingDocument {

    @Id
    private ObjectId id;

    @Field("tenant_id")
    private String tenantId;

    @Field("title")
    private String title;

    @Field(
        value = "monthly_rent",
        targetType = FieldType.DECIMAL128
    )
    private BigDecimal monthlyRent;

    @Field("address")
    private Address address;

    @Field("rooms")
    private List<Room> rooms = new ArrayList<>();

    @Field("tags")
    private List<String> tags = new ArrayList<>();

    @Field("available")
    private boolean available;

    @Field("created_at")
    private Instant createdAt;

    @Transient
    private String displayLabel;

    protected ListingDocument() {
        // Used by Spring Data when materializing the object.
    }

    public ListingDocument(
            String tenantId,
            String title,
            BigDecimal monthlyRent,
            Address address,
            List<Room> rooms,
            List<String> tags,
            boolean available,
            Instant createdAt) {
        this.tenantId = tenantId;
        this.title = title;
        this.monthlyRent = monthlyRent;
        this.address = address;
        this.rooms = rooms == null
                ? new ArrayList<>() : new ArrayList<>(rooms);
        this.tags = tags == null
                ? new ArrayList<>() : new ArrayList<>(tags);
        this.available = available;
        this.createdAt = createdAt;
    }

    public ObjectId getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getTitle() {
        return title;
    }

    public BigDecimal getMonthlyRent() {
        return monthlyRent;
    }

    public Address getAddress() {
        return address;
    }

    public List<Room> getRooms() {
        return rooms;
    }

    public List<String> getTags() {
        return tags;
    }

    public boolean isAvailable() {
        return available;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public String getDisplayLabel() {
        return displayLabel;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public void setMonthlyRent(BigDecimal monthlyRent) {
        this.monthlyRent = monthlyRent;
    }

    public void setAvailable(boolean available) {
        this.available = available;
    }
}
~~~

**Mapping explanation:**

1. **@Document** selects the collection.
2. **@Id** places the `ObjectId` into BSON **_id**.
3. **@Field("tenant_id")** renames the field.
4. **@Field(... targetType = DECIMAL128)** specifies the monetary representation.
5. **address** is an embedded document.
6. **rooms** is a BSON array of embedded documents.
7. **tags** is a BSON array of strings.
8. **createdAt** is a timestamp, converted to the appropriate date type via conversions.
9. **@Transient** prevents **displayLabel** from being persisted as a regular BSON field.

This is a mutable POJO with a no-arg constructor to make mapping mechanics easy to follow; production code may use immutable classes/records, builders, or Lombok, provided constructor binding and access rules are understood.

### 7.2. Address — Embedded Object

Illustrative file **Address.java**:

~~~java
package com.example.mongo398.domain;

import org.springframework.data.mongodb.core.mapping.Field;

public class Address {

    @Field("city_code")
    private String cityCode;

    @Field("district")
    private String district;

    @Field("coordinates")
    private Coordinates coordinates;

    protected Address() {
    }

    public Address(
            String cityCode,
            String district,
            Coordinates coordinates) {
        this.cityCode = cityCode;
        this.district = district;
        this.coordinates = coordinates;
    }

    public String getCityCode() {
        return cityCode;
    }

    public String getDistrict() {
        return district;
    }

    public Coordinates getCoordinates() {
        return coordinates;
    }
}
~~~

Result nested inside parent:

~~~javascript
{
  address: {
    city_code: "HCM",
    district: "Binh Thanh",
    coordinates: { /* nested document */ }
  }
}
~~~

Declaring `Address` does not create an **address** collection. Spring Data maps it along the parent property hierarchy unless an explicit reference directive is present.

### 7.3. Coordinates — Third-Level Nested Document

File **Coordinates.java**:

~~~java
package com.example.mongo398.domain;

public class Coordinates {

    private double longitude;
    private double latitude;

    protected Coordinates() {
    }

    public Coordinates(double longitude, double latitude) {
        this.longitude = longitude;
        this.latitude = latitude;
    }

    public double getLongitude() {
        return longitude;
    }

    public double getLatitude() {
        return latitude;
    }
}
~~~

BSON:

~~~javascript
{
  address: {
    coordinates: {
      longitude: 106.71,
      latitude: 10.80
    }
  }
}
~~~

This is simply a plain coordinate pair. If you need a **2dsphere geospatial index**, MongoDB generally expects **GeoJSON** or a supported coordinate format; do not assume any arbitrary object with `longitude` and `latitude` fields automatically supports `$near`.

### 7.4. Room — Array Element

File **Room.java**:

~~~java
package com.example.mongo398.domain;

import java.util.ArrayList;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Field;

public class Room {

    @Field("type")
    private String type;

    @Field("area_sqm")
    private int areaSqm;

    @Field("amenities")
    private List<String> amenities = new ArrayList<>();

    protected Room() {
    }

    public Room(
            String type,
            int areaSqm,
            List<String> amenities) {
        this.type = type;
        this.areaSqm = areaSqm;
        this.amenities = amenities == null
                ? new ArrayList<>() : new ArrayList<>(amenities);
    }

    public String getType() {
        return type;
    }

    public int getAreaSqm() {
        return areaSqm;
    }

    public List<String> getAmenities() {
        return amenities;
    }
}
~~~

`Room` has no `@Id` because it is not a root document stored in its own collection. If the application needs to identify individual rooms to update a specific array element, you can add a business field such as **roomId** inside the subdocument; it does not automatically become a MongoDB root `_id`.

### 7.5. Summary Mapping Tree

~~~text
ListingDocument                       BSON
----------------------------------------------------------------
id: ObjectId                      -> _id: ObjectId(...)
tenantId: String                  -> tenant_id: "tenant-001"
title: String                     -> title: "Studio"
monthlyRent: BigDecimal           -> monthly_rent: Decimal128(...)
address: Address                  -> address: { ... }
  cityCode: String                ->   city_code: "HCM"
  district: String                ->   district: "Binh Thanh"
  coordinates: Coordinates        ->   coordinates: { ... }
    longitude: double             ->     longitude: 106.71
    latitude: double              ->     latitude: 10.80
rooms: List<Room>                 -> rooms: [ { ... }, ... ]
  areaSqm: int                    ->   area_sqm: 22
  amenities: List<String>         ->   amenities: ["desk","wifi"]
tags: List<String>                -> tags: ["near-park"]
createdAt: Instant                -> created_at: Date(...)
displayLabel: @Transient          -> field not written
~~~

## 8. What Does the Generated MongoDB Document Look Like?

### 8.1. An Illustrative BSON Document

When inserting `ListingDocument` using the default converter, the logical BSON structure looks like:

~~~javascript
{
  _id: ObjectId("660000000000000000000398"),
  tenant_id: "tenant-001",
  title: "Studio near the park",
  monthly_rent: NumberDecimal("12500000.00"),
  address: {
    city_code: "HCM",
    district: "Binh Thanh",
    coordinates: {
      longitude: 106.71,
      latitude: 10.80
    }
  },
  rooms: [
    {
      type: "bedroom",
      area_sqm: 22,
      amenities: ["desk", "wifi"]
    },
    {
      type: "kitchen",
      area_sqm: 8,
      amenities: ["stove"]
    }
  ],
  tags: ["near-park", "furnished"],
  available: true,
  created_at: ISODate("2026-01-15T09:30:00Z"),
  _class: "com.example.mongo398.domain.ListingDocument"
}
~~~

**_class** is commonly written by the default `MappingMongoConverter` as type metadata, especially for root documents and polymorphic scenarios. Embedded values may or may not include additional type metadata depending on mapping and concrete types. This is an illustrative sample, not a byte-for-byte guarantee across all Spring Data configurations.

### 8.2. Why Does _class Exist?

A document can be read back into the corresponding type:

~~~text
_class:
  com.example.mongo398.domain.ListingDocument
~~~

This helps the converter determine the target type when metadata is needed, particularly when a Java property is declared as an interface or base class while stored data holds a subclass.

Systems that do not want to store the FQCN can use **@TypeAlias** or customize the type mapper in Spring Data. However, altering type metadata is a **schema and compatibility decision**—never delete `_class` directly in production simply because it "looks redundant."

### 8.3. In Practice, _class Can Vary

If converter configuration changes type mapping, `_class` may:

- Store a short alias.
- Be omitted in certain configurations.
- Use custom metadata via a custom type mapper.

Do not write integration tests that assert exact raw document equality including `_class` without explicitly fixing the converter configuration.

### 8.4. Extended JSON and BSON Representation

The MongoDB shell displays `ObjectId`, `ISODate`, and `NumberDecimal` for human readability. When exported as **Extended JSON**, values may appear as:

~~~json
{
  "_id": { "$oid": "660000000000000000000398" },
  "monthly_rent": { "$numberDecimal": "12500000.00" },
  "created_at": { "$date": "2026-01-15T09:30:00Z" }
}
~~~

This is JSON notation representing BSON types—it does not mean MongoDB stores a nested `$oid` subdocument inside `_id`. Always distinguish **BSON native types** from **Extended JSON notation**.

## 9. Creating a ListingDocument and Persisting with MongoTemplate

### 9.1. Constructing the Object

~~~java
Address address = new Address(
    "HCM",
    "Binh Thanh",
    new Coordinates(106.71, 10.80)
);

List<Room> rooms = List.of(
    new Room("bedroom", 22, List.of("desk", "wifi")),
    new Room("kitchen", 8, List.of("stove"))
);

ListingDocument listing = new ListingDocument(
    "tenant-001",
    "Studio near the park",
    new BigDecimal("12500000.00"),
    address,
    rooms,
    List.of("near-park", "furnished"),
    true,
    Instant.parse("2026-01-15T09:30:00Z")
);
~~~

Before insertion, **listing.getId()** can be null. When saved via Spring Data, the ID is typically populated according to the mapping strategy.

### 9.2. Insert

~~~java
ListingDocument saved = mongoTemplate.insert(listing);

System.out.println(saved.getId());
~~~

For a new document, `insert` writes into the collection specified by `@Document`. **insert** is intended for creating new documents and throws a duplicate-key error if `_id` already exists.

### 9.3. Save

~~~java
listing.setTitle("Studio near the park - updated");
mongoTemplate.save(listing);
~~~

**save** generally performs insert-or-replace/upsert semantics based on the mapped ID, unlike updating a single field. Be cautious with:

- Properties that are null or defaulted.
- Nested objects that were not loaded completely.
- Concurrent updates overwriting another writer's changes.
- Legacy documents containing fields no longer present in the mapped class.

When only modifying a single field, a targeted **Update** is usually safer than saving the entire document.

### 9.4. Find by ID

~~~java
ObjectId id = saved.getId();

ListingDocument loaded =
    mongoTemplate.findById(id, ListingDocument.class);

System.out.println(loaded.getTitle());
~~~

This reads the document back through the converter: BSON **_id** maps back to Java **id**.

### 9.5. Repository

When using a Spring Data repository:

~~~java
package com.example.mongo398.repository;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;
import com.example.mongo398.domain.ListingDocument;

public interface ListingRepository
        extends MongoRepository<ListingDocument, ObjectId> {
}
~~~

Methods such as **save**, **findById**, **findAll**, and **deleteById** are provided by the interface. Never treat the repository abstraction as a way to bypass MongoDB authorization or transaction rules.

## 10. Querying by Java Property Name or BSON Field Name?

### 10.1. MongoTemplate Understands Mapping Metadata

When you declare:

~~~java
@Field("tenant_id")
private String tenantId;
~~~

you can use the Java property name in a **typed query**:

~~~java
Query query = new Query(
    Criteria.where("tenantId").is("tenant-001")
);

List<ListingDocument> result =
    mongoTemplate.find(query, ListingDocument.class);
~~~

The Spring Data mapping layer translates **tenantId** into BSON field **tenant_id** when the query runs with entity mapping context.

### 10.2. Do Not Confuse Criteria.where with Raw mongosh Queries

In `mongosh`, you must use the stored field name:

~~~javascript
db.rental_listings_398.find({
  tenant_id: "tenant-001"
});
~~~

The MongoDB server **does not know about the Java property `tenantId`** if the database only contains `tenant_id`.

### 10.3. Nested Property Paths

Given the model:

~~~text
ListingDocument.address
Address.cityCode -> @Field("city_code")
~~~

Typed `MongoTemplate` query:

~~~java
Query query = new Query(
    Criteria.where("tenantId").is("tenant-001")
        .and("address.cityCode").is("HCM")
        .and("available").is(true)
);
~~~

Logically equivalent BSON query:

~~~javascript
{
  tenant_id: "tenant-001",
  "address.city_code": "HCM",
  available: true
}
~~~

Here, **address.cityCode** is the Java property path, while **address.city_code** is the dotted path in the stored document.

### 10.4. Dotted Paths vs. Literal Field Names

MongoDB uses dot notation to query nested fields:

~~~javascript
{
  "address.coordinates.longitude": {
    $gte: 106.5
  }
}
~~~

This is not a root-level field literally named **address.coordinates.longitude** in our model; it is a **path to a nested value**.

Spring Data MongoDB has modes/options for handling literal field names containing dots depending on version, but that is a special case. Never design schemas with dots inside field names just to mimic dotted paths.

## 11. MongoRepository: Derived Queries on Nested Properties

### 11.1. Repository with Query Methods

~~~java
package com.example.mongo398.repository;

import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;
import com.example.mongo398.domain.ListingDocument;

public interface ListingRepository
        extends MongoRepository<ListingDocument, ObjectId> {

    List<ListingDocument> findByTenantIdAndAvailableTrue(
        String tenantId
    );

    List<ListingDocument> findByTenantIdAndAddress_CityCode(
        String tenantId,
        String cityCode
    );

    Page<ListingDocument> findByTenantIdAndAvailableTrue(
        String tenantId,
        Pageable pageable
    );
}
~~~

The method name segment **Address_CityCode** uses an underscore to explicitly separate property traversal in Spring Data's derived query syntax (not an underscore from the BSON field name). It represents the Java path **address.cityCode**.

**Note on overloads:** The two `findByTenantIdAndAvailableTrue` methods above have different parameter lists, making them valid Java overloads. In production codebases, prefer clear, unambiguous names to avoid confusing teammates.

### 11.2. Query Methods Do Not Use BSON Field Names

If the Java property is `monthlyRent` and the BSON field is `monthly_rent`, the method:

~~~java
List<ListingDocument> findByTenantIdAndMonthlyRentLessThanEqual(
    String tenantId,
    BigDecimal maxRent
);
~~~

uses **Java property names**. Spring Data repository mapping translates them to the corresponding BSON names.

### 11.3. @Query with Stored Field Names

You can also write a JSON query:

~~~java
import org.springframework.data.mongodb.repository.Query;

@Query("{ 'tenant_id': ?0, 'address.city_code': ?1 }")
List<ListingDocument> findByStoredFields(
    String tenantId,
    String cityCode
);
~~~

When using **@Query**, keep in mind you are writing a MongoDB JSON query string whose field-name resolution depends on mapping rules and version. To avoid ambiguity, standardize project conventions on **explicit stored names** for raw JSON queries, and **Java property paths** for derived queries and typed `Criteria`.

### 11.4. Pageable and Sort

~~~java
Pageable pageable = PageRequest.of(
    0, 20, Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);

Page<ListingDocument> page =
    repository.findByTenantIdAndAvailableTrue(
        "tenant-001", pageable
    );
~~~

When using a Spring Data repository, sorting by **createdAt** maps to **created_at**, and **id** maps to **_id**. Remember the imports:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
~~~

For large datasets, offset pagination becomes inefficient at deep pages; consider keyset pagination over `created_at` + `_id` backed by an appropriate index and verified by tests.

## 12. Embedded Documents: When to Use Them and Why

### 12.1. An Address Belongs to a Listing

An address is almost always read together with its listing. Embedding retrieves everything in one document:

~~~javascript
{
  title: "Studio",
  address: {
    city_code: "HCM",
    district: "Binh Thanh"
  }
}
~~~

Instead of:

~~~text
listings:
  listingId -> addressId

addresses:
  addressId -> cityCode, district
~~~

The MongoDB embedded model fits well when `address` shares the listing's lifecycle and is routinely fetched alongside it.

### 12.2. Advantages

- A single document read returns all related data.
- Updating multiple fields within the **same document** is atomic under MongoDB's single-document atomicity semantics.
- Reduces the need for joins or `$lookup`.
- Clear query structure using nested paths.

### 12.3. Limitations

- MongoDB documents have a **BSON size limit** (typically 16 MiB per document).
- Unbounded array growth inflates documents and causes write contention.
- Data with an independent lifecycle or shared across many parent documents may not be suitable for embedding.
- Updating nested arrays requires careful element-matching conditions.
- Replication and network transfer costs rise when documents grow large.

Never embed an unbounded event history inside **ListingDocument.rooms** or a similar array without a bounding strategy.

### 12.4. One-to-Few, One-to-Many, Unbounded

| Relationship | Common Design Consideration |
| --- | --- |
| One listing has one address | Embedded `Address` |
| An apartment has 2–10 rooms | Embedded `List<Room>` |
| A listing has a few dozen tags | Embedded `List<String>` |
| A listing has millions of page views | Separate collection for events |
| An owner has many independent listings | Reference or `ownerId` field; evaluate read patterns |

Choose based on **query patterns, update frequency, growth, and ownership/lifecycle**—not purely from UML diagrams.

## 13. Nested Arrays and Matching the Right Element

### 13.1. Array of Embedded Documents

Java:

~~~java
@Field("rooms")
private List<Room> rooms;
~~~

BSON:

~~~javascript
{
  rooms: [
    {
      type: "bedroom",
      area_sqm: 22,
      amenities: ["desk", "wifi"]
    },
    {
      type: "kitchen",
      area_sqm: 8,
      amenities: ["stove"]
    }
  ]
}
~~~

### 13.2. Querying an Array Where Any Element Matches

`mongosh`:

~~~javascript
db.rental_listings_398.find({
  "rooms.amenities": "wifi"
});
~~~

This query matches documents where **at least one `rooms` element** has `amenities` containing `"wifi"`, following MongoDB array query semantics.

Typed `MongoTemplate`:

~~~java
Query q = new Query(
    Criteria.where("rooms.amenities").is("wifi")
);

List<ListingDocument> matches =
    mongoTemplate.find(q, ListingDocument.class);
~~~

### 13.3. Two Conditions Must Apply to the Same Room

It is a mistake to assume two predicates always apply to the same array element:

~~~javascript
{
  "rooms.type": "bedroom",
  "rooms.area_sqm": { $gte: 20 }
}
~~~

A document might have **room A as a bedroom** and **room B with 20 m²**; two separate dotted predicates on an array can match across different elements.

Use **$elemMatch**:

~~~javascript
db.rental_listings_398.find({
  rooms: {
    $elemMatch: {
      type: "bedroom",
      area_sqm: { $gte: 20 }
    }
  }
});
~~~

Typed `MongoTemplate`:

~~~java
Query q = new Query(
    Criteria.where("rooms").elemMatch(
        Criteria.where("type").is("bedroom")
            .and("areaSqm").gte(20)
    )
);
~~~

The **areaSqm** path inside `Room` maps to BSON field **area_sqm** when the query runs under the `ListingDocument` mapping context. When using raw BSON updates or aggregations, carefully verify the mapping semantics of the API you call.

### 13.4. Updating Nested Arrays

MongoDB supports positional operators and `arrayFilters` in updates. These operations require determining:

- Which element(s) are matched.
- Whether one or multiple elements should be updated.
- Whether your client version maps field aliases inside `arrayFilters` as expected.
- Concurrency and business conditions.

Do not run:

~~~javascript
{ $set: { rooms: [] } }
~~~

just to update one room's area: that replaces the entire array with an empty array.

A targeted, conditional update tested in the lab is far safer than loading the object and calling **save** on the whole document when multiple users might edit different rooms concurrently.

## 14. Maps and Dynamic Attributes

### 14.1. Map in Java

~~~java
@Field("attributes")
private Map<String, String> attributes;
~~~

Corresponding BSON:

~~~javascript
{
  attributes: {
    floor: "12",
    orientation: "east",
    furnishing: "full"
  }
}
~~~

A `Map` works well when keys are controlled yet extensible.

### 14.2. Important Considerations

- Map keys become field names in the nested BSON object.
- Never accept arbitrary keys directly from untrusted clients.
- Dots and **`$`** characters in field names carry special restrictions/behaviors across MongoDB versions and APIs; many query/update operators rely on dot notation.
- Do not let a map grow unbounded inside a single document.
- If an attribute needs stable indexing and querying, a typed Java property is clearer than a dynamic `Map`.

### 14.3. Typed Class vs. Map

~~~java
public class Address {
    private String cityCode;
}
~~~

benefits:

- Compiler-checked property access.
- Easy `@Field` aliasing and validation.
- Safer refactoring for derived repository queries.

Map:

~~~java
Map<String, Object> address;
~~~

provides high schema flexibility at the cost of weaker type safety, validation, and query pattern predictability.

## 15. Nested Objects vs. References

### 15.1. Default Embedded Object

~~~java
private Address address;
~~~

Stored as:

~~~javascript
{ address: { city_code: "HCM" } }
~~~

### 15.2. @DBRef Reference

Spring Data offers the **@DBRef** annotation:

~~~java
@DBRef
private OwnerDocument owner;
~~~

This represents a reference to another document, **without embedding the full `OwnerDocument` under default `DBRef` semantics**. Reading references can trigger extra database queries and requires attention to eager/lazy loading, performance, and serialization.

### 15.3. @DocumentReference

Spring Data MongoDB also provides **@DocumentReference** for flexible references based on configured mapping/lookups. It differs from `@DBRef` in how references are stored and resolved.

Do not use `@DBRef` or `@DocumentReference` for **Address** if `address` has no independent lifecycle. Use references only when access patterns and lifecycles justify them.

### 15.4. Independent One-to-Many

An owner may have many listings that change independently. Often it makes sense to store:

~~~javascript
{
  _id: ObjectId(...),
  owner_id: ObjectId("...")
}
~~~

and query/list by `owner_id`, rather than embedding thousands of listings inside a single owner document. References can be modeled as a plain ID field or via reference annotations depending on requirements.

## 16. Common Java Types and Their BSON Counterparts

| Java property | Typical BSON | Notes |
| --- | --- | --- |
| `String` | `String` | Not every String ID is stored as String if `@Id` triggers conversion |
| `ObjectId` | `ObjectId` | Used for `_id` or BSON ObjectId fields |
| `int`/`Integer` | `Int32` | Primitive receives default `0` when field is missing |
| `long`/`Long` | `Int64` | Distinct from `Int32`; check types during schema evolution |
| `double`/`Double` | `Double` | Subject to binary floating-point precision loss |
| `BigDecimal` | Possibly `Decimal128` with `@Field` `targetType` | Standardize scale and rounding |
| `boolean`/`Boolean` | `Boolean` | `boolean` defaults to `false`; `Boolean` can be `null` |
| `Instant`, `Date` | `BSON Date` | Control timezone and precision |
| `List<T>` | `Array` | Nested elements converted according to `T` |
| `Map<String,T>` | `Embedded object/document` | Key names require policy |
| `Enum` | Usually `String` via default converter | Renaming enum constants can break old records |
| `POJO value object` | `Embedded document` | May include type metadata depending on case |

Exact conversion behavior depends on registered converters, custom conversions, and the driver; this table is a general guide rather than a substitute for actual testing.

### 16.1. Instant and Timezones

~~~java
@Field("created_at")
private Instant createdAt;
~~~

BSON Date stores an instant in time, typically represented as UTC epoch milliseconds. **Instant** has clear point-in-time semantics; for local calendar appointments, you may also need a **ZoneId** and a business timezone.

Do not use **LocalDateTime** assuming it carries timezone information. When converting between `LocalDateTime` and `Instant` or `Date`, define the zone and conversion policy explicitly.

### 16.2. Primitives and Null

~~~java
private boolean available;
private int roomCount;
~~~

If an older BSON document lacks these fields, the Java object receives Java defaults: `false` and `0`.

~~~java
private Boolean available;
private Integer roomCount;
~~~

allows representing `null` in Java. However, **missing fields** and **explicit BSON `null`** may need to be distinguished at the migration or validation layer; Java `null` alone does not always preserve that distinction.

### 16.3. Enums

~~~java
enum ListingStatus {
    DRAFT,
    ACTIVE,
    ARCHIVED
}
~~~

Typically stored as strings matching the enum constant name by default:

~~~javascript
{ status: "ACTIVE" }
~~~

Renaming **ACTIVE** to **PUBLISHED** without handling legacy documents can cause read errors or inconsistent data. Consider explicit stable codes and custom converters for long-lived schemas.

### 16.4. BigDecimal and Monetary Values

For monetary amounts:

- Use `BigDecimal` or represent **amountInMinorUnits** as a `long` per policy.
- Avoid `double` for monetary arithmetic when exactness is required.
- Verify the actual `Decimal128` mapping stored in MongoDB.
- Include `currencyCode`, scale, and rounding policies.
- Never assume the string `"12500000.00"` and `Decimal128` behave identically in queries.

## 17. Reading Objects with Missing Fields or Newly Added Fields

### 17.1. Schema-Less Does Not Mean Schema-Free

MongoDB does not require every document in a collection to share the exact same fields unless validation is enforced. A collection may contain:

~~~javascript
// Legacy version
{
  _id: ObjectId(...),
  title: "Studio",
  tenant_id: "tenant-001"
}

// New version
{
  _id: ObjectId(...),
  title: "Studio",
  tenant_id: "tenant-001",
  address: { city_code: "HCM" },
  available: true
}
~~~

The new Java class must handle legacy documents missing `address`:

~~~java
if (listing.getAddress() != null) {
    String city = listing.getAddress().getCityCode();
}
~~~

Calling `listing.getAddress().getCityCode()` unconditionally will easily throw a `NullPointerException`.

### 17.2. Constructor Defaults Are Not Always a Migration Policy

Writing:

~~~java
private List<Room> rooms = new ArrayList<>();
~~~

initializes an empty list in some object instantiation paths. However, with immutable mapping, constructor binding and converter behavior can produce different results when BSON fields are missing or null.

Do not rely solely on field initializers as a substitute for backfilling legacy production data.

### 17.3. Renaming Fields

From:

~~~javascript
{ monthlyRent: NumberDecimal("12000000") }
~~~

to:

~~~javascript
{ monthly_rent: NumberDecimal("12000000") }
~~~

Simply changing `@Field` in code does not rewrite existing documents.

In an **isolated lab**, a migration might use:

~~~javascript
db.rental_listings_398.updateMany(
  {
    labTag: "mongo398-v1",
    monthlyRent: { $exists: true },
    monthly_rent: { $exists: false }
  },
  {
    $rename: {
      monthlyRent: "monthly_rent"
    }
  }
);
~~~

This command **modifies data** and is not a mandatory step of the lesson. In production, you must evaluate field conflicts, backups, index/query rollouts, active writers, and dual-read/dual-write strategies; never run a bulk `$rename` while older application instances are still writing the old field name without a plan.

### 17.4. Expand–Migrate–Contract

A safe field-renaming plan:

~~~text
Expand:
  New app can read both old and new data
         |
         v
Migrate:
  Backfill legacy documents in bounded batches
         |
         v
Verify:
  Count missing/new fields, check business values
         |
         v
Contract:
  Drop old field support once writers/readers migrated
~~~

**Never deploy a new mapping and immediately save the entire collection** if legacy data has not been accounted for.

### 17.5. Unknown Fields

A document may contain fields not defined in the Java class. When read through the converter, those fields do not automatically become Java properties.

If you subsequently **save** that object, weigh the risk of losing unknown fields due to replacement semantics. When updating only a single field, a targeted `Update` reduces that risk.

## 18. @Transient, Static Fields, and Computed Properties

### 18.1. @Transient

~~~java
import org.springframework.data.annotation.Transient;

@Transient
private String displayLabel;
~~~

This property is excluded from persistence mapping as a BSON field. It is suitable for:

- Computed display values.
- Temporary in-memory caches on the object.
- State that should not be persisted.

Do not use `@Transient` to "hide" sensitive data from API JSON; **persistence mapping** is separate from **Jackson serialization**. A property marked transient for MongoDB can still be serialized to JSON if it has a getter and no API DTO or JSON exclusion is configured.

### 18.2. @Transient Can Affect Constructor Binding

If an immutable class includes a constructor parameter corresponding to a `@Transient` field, the mapper may lack data to bind it as expected. Design persistence constructors and derived fields cleanly.

### 18.3. Computed Values

Example:

~~~java
public String getDisplayTitle() {
    return title + " (" + tenantId + ")";
}
~~~

Without a corresponding mapped field, this method is pure Java logic. Do not assume Spring Data persists every getter as a new field; mapping relies on persistent properties, field access, and metadata.

## 19. Constructor Mapping, Immutable Classes, and Records

### 19.1. Mutable POJO

The model in section 7 has:

- A no-arg constructor.
- Fields accessed by the mapping layer.
- Getters for the application.
- Selected setters for business updates.

This style is easy to learn and works reliably with Spring Data.

### 19.2. Immutable Class

An immutable model has `final` fields and a constructor:

~~~java
public final class Money {

    private final BigDecimal amount;
    private final String currency;

    public Money(BigDecimal amount, String currency) {
        this.amount = amount;
        this.currency = currency;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getCurrency() {
        return currency;
    }
}
~~~

Spring Data supports constructor-based materialization; when multiple constructors or factory methods exist, annotations such as **@PersistenceCreator** may be needed depending on version and model.

### 19.3. Java Record

Java 17:

~~~java
import org.springframework.data.mongodb.core.mapping.Field;

public record AddressView(
    @Field("city_code") String cityCode,
    String district
) {}
~~~

Records model immutable value objects cleanly, and Spring Data supports record mapping in modern versions. However, for root entities with auto-generated IDs, records have no setters; understand how the mapping layer handles immutable properties, constructor binding, and ID population.

To keep the baseline lab focused, the primary examples use a **mutable root POJO** and simple embedded classes.

### 19.4. @PersistenceCreator

When a class has multiple constructors and Spring Data needs to know which one to use for reading persistence data, **@PersistenceCreator** from Spring Data Commons can be applied.

~~~java
import org.springframework.data.annotation.PersistenceCreator;

public final class Label {
    private final String value;

    @PersistenceCreator
    public Label(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
~~~

Do not annotate a constructor that omits required properties of an immutable object. Test actual BSON readback and follow parameter-naming and type-conversion rules.

## 20. Indexes on Nested Fields and @Field Aliases

### 20.1. MongoDB Indexes Use BSON Names

In `mongosh`:

~~~javascript
db.rental_listings_398.createIndex(
  {
    tenant_id: 1,
    "address.city_code": 1,
    available: 1
  },
  { name: "ix_398_tenant_city_available" }
);
~~~

This index supports queries filtering on tenant, city, and availability, depending on selectivity, sort order, and query plan.

Do not use:

~~~javascript
{ tenantId: 1, "address.cityCode": 1 }
~~~

in **raw `mongosh`** when actual data is stored under `tenant_id` and `city_code`.

### 20.2. @CompoundIndex

Spring Data MongoDB provides annotations to declare compound indexes:

~~~java
import org.springframework.data.mongodb.core.index.CompoundIndex;

@Document(collection = "rental_listings_398")
@CompoundIndex(
    name = "ix_398_tenant_city_available",
    def = "{ 'tenant_id': 1, 'address.city_code': 1, 'available': 1 }"
)
public class ListingDocument {
    // fields omitted
}
~~~

This is an **annotation pattern added to the model**, not a second `ListingDocument` class in the same codebase.

### 20.3. Annotations Do Not Guarantee the Index Exists

Spring Data MongoDB has auto-index creation options, but in many versions and projects, automatic index creation is **disabled by default**. Moreover, the runtime DB user may lack `createIndex` privileges.

Therefore:

1. Define indexes in your migration strategy.
2. Create indexes using an identity with appropriate permissions.
3. Confirm index builds finish cleanly.
4. Verify with `getIndexes` and `explain`.
5. Measure impact on both reads and writes.

Never rely on `@Field` or `@CompoundIndex` alone as proof that an index exists on the server.

### 20.4. Indexes on Arrays

~~~javascript
db.rental_listings_398.createIndex(
  { "rooms.amenities": 1 },
  { name: "ix_398_room_amenities" }
);
~~~

Because `rooms` and `amenities` are arrays, this creates a **multikey index**. Understand multikey and compound index rules when arrays are involved; never combine multiple array fields in a compound index without checking MongoDB's parallel-array restrictions and costs.

### 20.5. Explain

~~~javascript
db.rental_listings_398.find({
  tenant_id: "tenant-001",
  "address.city_code": "HCM",
  available: true
}).explain("executionStats");
~~~

Inspect:

- `winningPlan`.
- `nReturned`.
- `totalKeysExamined`.
- `totalDocsExamined`.
- `executionTimeMillis`.

Adding a new index does not guarantee the optimizer picks it or that request latency improves. Dataset distribution, selectivity, sort order, and concurrent workload all matter.

## 21. MongoTemplate: Updating Nested Fields Without Replacing the Whole Document

### 21.1. Updating a Single Nested Property

~~~java
Query query = new Query(
    Criteria.where("id").is(listingId)
        .and("tenantId").is(authorizedTenantId)
);

Update update = new Update()
    .set("address.cityCode", "HN");

mongoTemplate.updateFirst(
    query,
    update,
    ListingDocument.class
);
~~~

With entity mapping context, the Java property path **address.cityCode** is translated to BSON **address.city_code**. This targets a single field rather than saving the whole object.

### 21.2. Tenant Predicate Is a Security Requirement

Never query only by:

~~~java
Criteria.where("id").is(listingId);
~~~

when data spans multiple tenants and application users must not read or modify other tenants' data. MongoDB RBAC typically operates at the database/collection level and **does not automatically inject per-document `tenantId` filters**.

Always obtain `tenantId` from a **verified security context** and enforce it on both read and write queries.

### 21.3. Replacing an Entire Nested Document

~~~java
Update update = new Update()
    .set("address", new Address(
        "HN",
        "Ba Dinh",
        new Coordinates(105.83, 21.03)
    ));
~~~

Setting `address` directly **replaces the entire embedded address**. If the old `address` held fields not present on the new `Address` class, you can lose them. Use full subdocument replacement only when the business intent is to replace the entire address.

### 21.4. Optimistic Locking

Spring Data supports **@Version** for optimistic locking:

~~~java
import org.springframework.data.annotation.Version;

@Version
private Long version;
~~~

This helps detect certain concurrent updates when saving entities via version-aware mapping APIs. However:

- It requires a version field in documents and a migration policy for legacy records.
- It does not automatically apply uniformly to every raw driver update.
- Conflicts and retries must be handled in the service layer.
- Write concern and driver behavior can influence error reporting.

Do not treat `@Version` as a replacement for all concurrency controls or business invariants.

## 22. Separating DTOs from the Persistence Model

### 22.1. Never Return ListingDocument Directly from an API

The persistence model may contain:

- `_id` as an `ObjectId`.
- Internal `tenantId`.
- `_class` or metadata fields.
- Detailed `address` or sensitive fields.
- Newly added fields not yet approved for the public API.

If a REST controller returns the entity directly, JSON serialization can leak internal fields or create fragile API contracts when classes evolve.

### 22.2. Response DTO

~~~java
public record ListingResponse(
    String id,
    String title,
    String cityCode,
    String district,
    String monthlyRent
) {}
~~~

Mapper:

~~~java
public static ListingResponse toResponse(
        ListingDocument listing) {
    Address address = listing.getAddress();

    return new ListingResponse(
        listing.getId() == null
            ? null : listing.getId().toHexString(),
        listing.getTitle(),
        address == null ? null : address.getCityCode(),
        address == null ? null : address.getDistrict(),
        listing.getMonthlyRent() == null
            ? null : listing.getMonthlyRent().toPlainString()
    );
}
~~~

Converting `BigDecimal` to a string in the DTO preserves exact decimal representation; real APIs should define a consistent JSON monetary schema rather than mixing strings and numbers arbitrarily across endpoints.

### 22.3. Creation Request DTO

~~~java
public record CreateListingRequest(
    String title,
    String cityCode,
    String district,
    String monthlyRent
) {}
~~~

When creating `ListingDocument`, **`tenantId` must come from the server-verified session/token**, never trusting a client-supplied field unless the user is explicitly authorized to select tenants.

## 23. Testing Mapping with MongoConverter

### 23.1. Why Test the Converter?

When changing `@Field` or ID types, visually inspecting the Java class alone can miss:

- BSON fields written under the wrong name.
- `BigDecimal` not stored in the expected BSON type.
- Nested `Address` resolving to null.
- Array elements failing to materialize.
- `_class`/type aliases causing read failures.
- Legacy documents missing fields.

A test can verify both **write conversion** and **read conversion**.

### 23.2. Mapping Smoke Check with the Converter

In a test with a configured `MongoTemplate`:

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.convert.MongoConverter;

MongoConverter converter = mongoTemplate.getConverter();

ListingDocument source = new ListingDocument(
    "tenant-001",
    "Studio mapping smoke test",
    new BigDecimal("12500000.00"),
    new Address(
        "HCM",
        "Binh Thanh",
        new Coordinates(106.71, 10.80)
    ),
    List.of(new Room(
        "bedroom", 22, List.of("wifi")
    )),
    List.of("demo"),
    true,
    Instant.parse("2026-01-15T09:30:00Z")
);

Document raw = new Document();
converter.write(source, raw);

System.out.println(raw.toJson());

ListingDocument roundTrip =
    converter.read(ListingDocument.class, raw);

System.out.println(
    roundTrip.getAddress().getCityCode()
);
~~~

**Note:** `converter.write` on an object with a null `ObjectId` may produce a raw `Document` without `_id`, because ID generation typically happens during `MongoTemplate`'s `insert`/`save` flow. To test `_id` generation, run an actual **insert** against the lab database. Do not confuse a converter round-trip with the full persistence lifecycle.

### 23.3. Recommended Assertions

In an integration test:

~~~text
assert raw.containsKey("tenant_id")
assert !raw.containsKey("tenantId")
assert raw.get("address") is Document
assert nested.get("city_code") == "HCM"
assert raw.get("rooms") is List
assert rooms[0].get("area_sqm") == 22
assert Decimal128 representation matches expectations
assert roundTrip.getAddress().getCityCode() == "HCM"
~~~

These are **assertion guidelines**, not complete JUnit code. For `Decimal128`, compare using actual BSON/driver types rather than `mongosh` `NumberDecimal` text output.

### 23.4. Testing Schema Evolution

Construct a legacy document:

~~~javascript
{
  _id: ObjectId(...),
  tenant_id: "tenant-001",
  title: "Old listing",
  monthlyRent: NumberDecimal("8000000")
}
~~~

Then read it with the new mapping, inspect what value `monthlyRent` receives, test your migration, and ensure you do not re-save without a data-preservation strategy.

### 23.5. Testing Against Real MongoDB

Converter-only tests do not exercise:

- MongoDB indexes and unique constraints.
- Server-side JSON Schema validation.
- BSON size limits.
- Query planner and index selection.
- Repository method query parsing and real database queries.
- Transactions and write concerns.

Therefore, serious projects need **integration tests running against a MongoDB instance/container matching the deployed version** in a test environment. Never use production as an integration test database.

## 24. mongosh Lab: Comparing Java Mapping with Stored BSON

### 24.1. Purpose

Even without spinning up a Spring Boot project, you can create the equivalent BSON document in `mongosh` and verify it against the mapping table. Use a dedicated database:

~~~text
mongo_mapping_lab_398
  rental_listings_398
~~~

Insert only a single document with a fixed `_id` reserved for this lesson:

~~~text
ObjectId("660000000000000000000398")
~~~

### 24.2. Idempotent Seed

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_mapping_lab_398");
  const listings = lab.getCollection("rental_listings_398");
  const id = ObjectId("660000000000000000000398");

  const sample = {
    _id: id,
    labTag: "mongo398-v1",
    tenant_id: "tenant-001",
    title: "Studio near the park",
    monthly_rent: NumberDecimal("12500000.00"),
    address: {
      city_code: "HCM",
      district: "Binh Thanh",
      coordinates: {
        longitude: 106.71,
        latitude: 10.80
      }
    },
    rooms: [
      {
        type: "bedroom",
        area_sqm: 22,
        amenities: ["desk", "wifi"]
      },
      {
        type: "kitchen",
        area_sqm: 8,
        amenities: ["stove"]
      }
    ],
    tags: ["near-park", "furnished"],
    available: true,
    created_at: ISODate("2026-01-15T09:30:00Z")
  };

  listings.replaceOne(
    {
      _id: id,
      labTag: "mongo398-v1"
    },
    sample,
    { upsert: true }
  );

  printjson(listings.findOne({ _id: id }));
})();
~~~

**Safety bounds:** The script targets only the fixed `_id` and `labTag`. If a document with that `_id` already exists without belonging to this lesson, `upsert` fails with a duplicate-key error instead of overwriting it. Never drop the collection to clear errors. Run only against a writable lab database.

**Difference from the converter:** This `mongosh` document has no `_class`; Java mapping can still read it when the root type is explicitly specified via **find(..., ListingDocument.class)**, but do not assume polymorphic behavior works without type metadata.

### 24.3. Inspecting Field Names

~~~javascript
const lab = db.getSiblingDB("mongo_mapping_lab_398");
const listings = lab.getCollection("rental_listings_398");

printjson(
  listings.findOne(
    {
      _id: ObjectId("660000000000000000000398")
    },
    {
      _id: 1,
      tenant_id: 1,
      monthly_rent: 1,
      "address.city_code": 1,
      rooms: 1
    }
  )
);
~~~

This projection uses **stored BSON field names**, not Java property names.

### 24.4. Querying Nested City

~~~javascript
printjson(
  listings.find({
    labTag: "mongo398-v1",
    tenant_id: "tenant-001",
    "address.city_code": "HCM"
  }).toArray()
);
~~~

Expected result: the sample document.

### 24.5. Querying Arrays with $elemMatch

~~~javascript
printjson(
  listings.find({
    labTag: "mongo398-v1",
    rooms: {
      $elemMatch: {
        type: "bedroom",
        area_sqm: { $gte: 20 }
      }
    }
  }, {
    _id: 1,
    title: 1,
    rooms: 1
  }).toArray()
);
~~~

Expected result: includes the sample because the same `bedroom` element has `area_sqm` 22.

### 24.6. Absent vs. Null Fields

~~~javascript
printjson({
  hasCity: listings.countDocuments({
    labTag: "mongo398-v1",
    "address.city_code": { $exists: true }
  }),
  explicitlyOrMissingNull: listings.countDocuments({
    labTag: "mongo398-v1",
    "address.city_code": null
  }),
  missingCity: listings.countDocuments({
    labTag: "mongo398-v1",
    "address.city_code": { $exists: false }
  })
});
~~~

In MongoDB, equality against `null` matches both explicitly `null` fields and missing fields; use **$exists** and **$type** when you need to distinguish exact field states.

### 24.7. Inspecting BSON Types

~~~javascript
printjson(
  listings.aggregate([
    {
      $match: {
        _id: ObjectId("660000000000000000000398")
      }
    },
    {
      $project: {
        idType: { $type: "$_id" },
        rentType: { $type: "$monthly_rent" },
        addressType: { $type: "$address" },
        roomsType: { $type: "$rooms" },
        createdType: { $type: "$created_at" }
      }
    }
  ]).toArray()
);
~~~

Expected type output:

~~~text
idType      objectId
rentType    decimal
addressType object
roomsType   array
createdType date
~~~

### 24.8. Verifying Aliases Without Old Field Names

~~~javascript
printjson(
  listings.findOne(
    {
      _id: ObjectId("660000000000000000000398")
    },
    {
      _id: 0,
      tenantId: 1,
      tenant_id: 1,
      monthlyRent: 1,
      monthly_rent: 1
    }
  )
);
~~~

In the lab sample, the stored fields are **tenant_id** and **monthly_rent**, not `tenantId` or `monthlyRent`.

### 24.9. Controlled Nested Field Update

To demonstrate an update in the isolated lab:

~~~javascript
printjson(
  listings.updateOne(
    {
      _id: ObjectId("660000000000000000000398"),
      labTag: "mongo398-v1",
      tenant_id: "tenant-001"
    },
    {
      $set: {
        "address.district": "District 1"
      }
    }
  )
);
~~~

The `_id + labTag + tenant_id` filter bounds the scope. This update **has side effects**—run it only when actively practicing. You can re-run the seed script to restore the sample document to its initial state.

### 24.10. Adding an Index for Lab Queries

~~~javascript
listings.createIndex(
  {
    tenant_id: 1,
    "address.city_code": 1,
    available: 1
  },
  { name: "ix_398_tenant_city_available" }
);
~~~

Never create this index in production without evaluating storage cost, write overhead, and index build impact.

### 24.11. Explain Query

~~~javascript
printjson(
  listings.find({
    tenant_id: "tenant-001",
    "address.city_code": "HCM",
    available: true
  }).explain("executionStats")
);
~~~

With a single lab document, `explain` carries little capacity significance—it simply illustrates field names and index/query plan concepts.

## 25. Common Mapping Pitfalls

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Entity loads but `id` is null | Incorrect `_id` mapping/conversion or unusual data | Check `@Id`, BSON `_id`, and type |
| `findBy...` returns nothing | Confusing Java property and BSON alias, or ID type mismatch | Check `@Field`, mapped query, actual BSON |
| `Address` is null | Legacy document lacks `address` or constructor binding issue | Handle null / run migration |
| Room `areaSqm` is 0 | BSON lacks field or stored under `area_sqm` | Check `@Field` and primitive defaults |
| Money amount reads incorrectly | Mismatch among String/Double/Decimal128 | Standardize `Decimal128`/conversion |
| Query on `@Id String` fails to match | 24-hex string stored as `ObjectId` | Verify BSON type; consider `@MongoId` |
| Document has `_class` | Default type metadata | Understand converter; do not delete arbitrarily |
| Legacy document loses fields on `save` | Full-document replacement across schema versions | Use targeted updates / migration |
| Assuming `@Document` creates indexes | Collection annotation != index creation | Manage indexes in separate migration |
| Assuming `@Field` performs validation | Mapping metadata does not enforce schema | Use Bean Validation / `$jsonSchema` |
| Missing suitable constructor | Mapper cannot instantiate immutable/POJO | Provide no-arg or persistence constructor |
| Saving embedded object overwrites sibling fields | Full subdocument replacement | Use dotted-path targeted update |
| Rooms query matches wrong room | Array predicates matched across different elements | Use `$elemMatch` |
| Tenant query filters only by `id` | RBAC does not filter per tenant | Enforce server-side tenant filter |
| Internal fields leaked via REST | Returning persistence entity directly | Use explicit DTOs |
| `@Transient` still returned by API | Mongo mapping != Jackson serialization | Configure DTOs / JSON policy |
| Nested object unexpectedly gets own collection | Separate repository or misplaced reference | Distinguish embedding vs. references |
| Updated `@Field` does not update old records | Annotations do not migrate BSON | Expand–migrate–contract |
| Many indexes created on startup | Uncontrolled auto-index/job config | Separate migrations and least privilege |
| Null and missing treated identically | MongoDB `null` query semantics | Use `$exists`/`$type`/schema validation |
| User-supplied map key creates tricky dot paths | Field naming and update semantics | Validate/whitelist keys |
| Using `double` for money | Floating-point precision errors | Use `BigDecimal`/`Decimal128` or minor units |
| Immutable record fails to populate `id` | Constructor/ID population differs from POJO | Test version and choose strategy |
| Converter test passes but DB insert fails | Server indexes/constraints not tested | Run integration tests with real MongoDB |

## 26. Mapping Design Workflow for a New Collection

### 26.1. Step 1 — Start from Access Patterns

Ask:

- Which fields does a typical request read?
- Is `Address` always fetched alongside the listing?
- Is the room count bounded?
- Must changes be atomic within a single document?
- Does the document grow unboundedly?
- Is data shared across many listings?
- How must the API search by tenant, city, availability, and price?

These questions matter far more than picking annotations first.

### 26.2. Step 2 — Design the BSON Contract

Example:

~~~text
Collection: rental_listings_398
_id: ObjectId
tenant_id: String
title: String
monthly_rent: Decimal128
address.city_code: String
address.district: String
rooms[].type: String
rooms[].area_sqm: Int32
created_at: Date
~~~

Document data types and missing/null rules. Annotations will then reflect an explicit contract.

### 26.3. Step 3 — Write the Java Model

1. `@Document` on the root.
2. `@Id` with an explicit ID strategy.
3. `@Field` where BSON names differ from Java names.
4. Embedded classes for groups of fields sharing a dependent lifecycle.
5. Arrays/Maps where appropriate.
6. Suitable constructors and accessors.
7. `@Transient` for non-persistent properties.

### 26.4. Step 4 — Test the Converter

- Java → BSON field names and types.
- BSON → Java nested structures.
- Missing fields.
- ID conversion.
- `Decimal128`/Date handling.
- `_class`/type aliases.

### 26.5. Step 5 — Test Queries and Indexes

- Derived repository queries.
- Typed `Criteria` with nested paths.
- Raw BSON queries.
- `$elemMatch` for arrays.
- Indexes using stored BSON names.
- `explain` against representative datasets.

### 26.6. Step 6 — Control Compatibility

- Legacy data may still carry old field names.
- Define migration/dual-read policies.
- Account for field renames and type changes.
- Run integration tests against both old and new fixtures.
- Never bulk-save legacy documents if unknown fields could be lost.

### 26.7. Step 7 — Separate DTOs and Authorization

- Validate API inputs.
- Derive `tenantId` from a trusted security context.
- Return only permitted output fields.
- Never allow clients to supply arbitrary collection names or raw queries.
- Grant the MongoDB account only required collection/action privileges.

## 27. Practice Exercises

### Exercise 1 — Three Core Annotations

Explain the distinct purposes of `@Document`, `@Id`, and `@Field`. For each annotation, describe one change that occurs in the collection/document during persistence mapping.

### Exercise 2 — @Document

Write a `ProductDocument` class stored in the `catalog_products` collection. If you only declare the annotation without inserting data, is the collection guaranteed to exist?

### Exercise 3 — @Id ObjectId

A class has `@Id ObjectId listingId`. What field name does MongoDB store? In `mongosh`, should you query by `listingId` or `_id`?

### Exercise 4 — String IDs

Compare `@Id String id` when the value is `"abc"` versus `"660000000000000000000398"`. What BSON type risk exists? When should you use `@MongoId(FieldType.STRING)`?

### Exercise 5 — @Field Aliases

Map Java fields `tenantId`, `monthlyRent`, and `createdAt` to BSON `tenant_id`, `monthly_rent`, and `created_at`. Write the corresponding annotations.

### Exercise 6 — Decimal128

Why is `double` generally unsuitable for monetary values? Which annotation expresses the intent to store `BigDecimal` as BSON `Decimal128`?

### Exercise 7 — Embedded Address

Create an `Address` containing `cityCode` and `district`, and place it inside `ListingDocument`. Does `Address` need `@Document` when it is only embedded?

### Exercise 8 — Multi-Level Nesting

Map `Address.coordinates.longitude` and `Address.coordinates.latitude`. Write the corresponding nested BSON document.

### Exercise 9 — List<Room>

Map a listing with two rooms. Where do `Room` `type`, `areaSqm`, and `amenities` appear in BSON?

### Exercise 10 — ObjectId vs. Extended JSON

Compare a native BSON `ObjectId` with the `{"$oid":"..."}` notation in Extended JSON. Which one is the actual stored data type?

### Exercise 11 — @Transient

A `displayLabel` property is used solely for UI display. Which annotation prevents it from being stored in MongoDB? Does that automatically exclude it from JSON API responses?

### Exercise 12 — _class

Why might documents saved by Spring Data contain `_class`? Under what circumstances should type aliases or a custom type mapper be explicitly designed?

### Exercise 13 — Insert/Save

Compare inserting an entity without `_id` against saving an entity that already has `_id`. Why does saving an entire document require caution in systems with concurrent updates?

### Exercise 14 — Repository

Declare a `MongoRepository` for `ListingDocument` with `ObjectId` as the ID type. Write `findByTenantIdAndAvailableTrue`.

### Exercise 15 — Nested Derived Query

Write a repository method to find listings by `tenantId` and `address.cityCode`. Explain the underscore in `Address_CityCode` in the method name.

### Exercise 16 — MongoTemplate

Write a `Criteria` query using Java properties `tenantId` + `address.cityCode` + `available`. Predict the actual stored BSON query paths.

### Exercise 17 — mongosh

Write a `mongosh` `find` query using `tenant_id` and `address.city_code`. What happens on the lab collection if you type `tenantId` and `address.cityCode` instead?

### Exercise 18 — Array Query

Write a query finding listings that have at least one room whose `amenities` includes `"wifi"`.

### Exercise 19 — $elemMatch

Explain why querying `"rooms.type": "bedroom"` and `"rooms.area_sqm": {$gte: 20}` does not force both conditions to apply to the same room. Fix it using `$elemMatch`.

### Exercise 20 — Maps

Map `Map<String, String> attributes` into an embedded object. Describe the risks if clients are allowed to submit arbitrary keys containing dots.

### Exercise 21 — Embedded vs. DBRef

An owner has thousands of independently changing listings, while each listing has a single address. Choose embedding or referencing for each relationship and justify based on access patterns.

### Exercise 22 — 16 MiB Document Limit

Why shouldn't you embed one million `pageViewEvents` inside a `ListingDocument`? Design an alternative data model.

### Exercise 23 — Missing Fields

A legacy document lacks `address` and `available`. When reading it into a Java POJO with an `Address` reference and primitive `boolean available`, what cases must the application handle?

### Exercise 24 — Schema Rename

Does changing `@Field` from `postalCode` to `postal_code` automatically update existing documents? Outline an expand–migrate–contract plan.

### Exercise 25 — Unknown Fields

An old document contains `legacy_notes` not declared in the Java class. Why can reading and then saving the full document cause data loss?

### Exercise 26 — Constructors

An immutable class has two constructors. Which constructor should Spring Data use when reading BSON? When should you consider `@PersistenceCreator`?

### Exercise 27 — Records

Write a record `AddressView` with `@Field("city_code") String cityCode`. Compare pros and cons against a mutable POJO in persistence mapping.

### Exercise 28 — Nested Field Index

Write a `mongosh` index for `tenant_id` + `address.city_code` + `available`. Why is using Java property names directly in raw `mongosh` usually wrong?

### Exercise 29 — Compound Index

Add the matching `@CompoundIndex` annotation. Is MongoDB guaranteed to create the index automatically at app startup? Who should own production index migrations?

### Exercise 30 — Targeted Update

Write a `MongoTemplate` `Update` to change `address.cityCode` without replacing the entire `address`. Why is `tenantId` required in the `Query` filter?

### Exercise 31 — DTO

Design a `ListingResponse` returning `id` as a hex string, `title`, `cityCode`, and `monthlyRent`. Why shouldn't you return `ListingDocument` directly?

### Exercise 32 — Converter Round-Trip

Obtain `MongoTemplate.getConverter()`, write `ListingDocument` to a `Document`, and read it back. Which assertions prove field aliases and nested objects mapped accurately?

### Exercise 33 — mongosh Lab

Run the seed script from section 24 on the lab database. Verify `_id` (`ObjectId`), `monthly_rent` (`Decimal128`), `address` (`object`), `rooms` (`array`), and `created_at` (`date`) using `$type`.

### Exercise 34 — Integration Tests

Why can't converter-only tests replace integration tests with real MongoDB? Mention indexes, validation, BSON size limits, and authorization.

### Exercise 35 — Tenant Authorization

User `t001` guesses the `_id` of a listing belonging to `t002`. Why do correct `@Id` and `@Document` mappings still fail to prevent cross-tenant access? Write the mandatory service predicate.

### Exercise 36 — Capstone Design

A system must store listings with an `ObjectId`, tenant ID, rent price, address, up to 10 rooms, tags, and posting timestamp. Write the model annotations, a sample JSON/BSON document, repository queries by tenant/city, a compound index, DTOs, legacy schema tests, and a safe migration plan.

## 28. References

- Spring Data MongoDB Reference — [Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html).
- Spring Data MongoDB Reference — [Mapping Configuration](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-config.html).
- Spring Data MongoDB Reference — [Mapping Usage](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html).
- Spring Data MongoDB Reference — [Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html).
- Spring Data MongoDB Reference — [MongoTemplate](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-api.html).
- Spring Data MongoDB Reference — [MongoDB Repositories](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/repositories.html).
- Spring Data MongoDB Reference — [Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html).
- Spring Data MongoDB Reference — [Index Creation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html).
- Spring Data MongoDB Reference — [DBRef / Document References](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/document-references.html).
- Spring Data MongoDB API — [@Document](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/Document.html).
- Spring Data MongoDB API — [@Field](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/Field.html).
- Spring Data MongoDB API — [@MongoId](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/MongoId.html).
- Spring Data Commons API — [@Id](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/annotation/Id.html).
- MongoDB Manual — [Documents](https://www.mongodb.com/docs/manual/core/document/).
- MongoDB Manual — [BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/).
- MongoDB Manual — [Query Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-embedded-documents/).
- MongoDB Manual — [Query Arrays of Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-array-of-documents/).
- MongoDB Manual — [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/).

**Conclusion:** In Spring Data MongoDB, **@Document** selects the root collection, **@Id** maps the Java identifier to BSON **_id**, and **@Field** defines the stored field name and optional BSON type settings. **MappingMongoConverter** converts between Java objects and BSON—including multi-level embedded objects, arrays, and maps—allowing ordinary **Address** or **Room** types to be embedded without separate collections. When querying, **Spring Data typed mapping uses Java property paths**, whereas **raw `mongosh` queries use BSON stored field names**; mixing up these two layers is a frequent cause of empty query results. Equally critical are **ObjectId/String ID conversion, Decimal128, `_class`, null vs. missing fields, index paths, constructor mapping, and schema evolution**. Annotations do not migrate legacy data, create all indexes automatically, enforce tenant authorization, or replace integration tests. A resilient design relies on **an explicit BSON contract, embedded models aligned with access patterns, dedicated API DTOs, targeted updates, and bidirectional Java ↔ BSON testing**.
