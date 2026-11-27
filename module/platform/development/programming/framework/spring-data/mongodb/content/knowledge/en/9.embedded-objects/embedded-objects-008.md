# Queries, Updates, and Mapping Limitations on Unwrapped Properties

In MongoDB, a Java object is normally stored as a **nested document**. However, Spring Data MongoDB supports `@Unwrapped` to *flatten* the fields of a value object into the **parent document**. This directly affects query paths, update operators, field names used in indexes and aggregations, and how documents with missing fields are read back.

For example, Java has `customer.billingAddress.city`, yet BSON can store `billing_city` at the root level, with **no** `billingAddress` document existing at all. As a result, `mongosh` commands and entity-aware `MongoTemplate` operations can use **two different path syntaxes** while accessing the same stored value.

This lesson in the **Objects and Embedding** chapter focuses on querying and updating `@Unwrapped` data, key mapping limitations, and verification in MongoDB. This knowledge applies directly when building Spring Data MongoDB applications with `MongoRepository`, `MongoTemplate`, aggregations, and indexes.

After this lesson, you can:

- Explain `@Unwrapped`, `prefix`, and `onEmpty`, and contrast them with standard embedded documents.
- Write queries using **Java property paths** in repositories/`MongoTemplate` and **flattened BSON names** in `mongosh`.
- Update one or more flattened fields, handle field deletion, and prevent write conflicts.
- Identify when you should not query or update an unwrapped object **as a whole**.
- Design prefixes, indexes, projections, migrations, and tests to avoid field name collisions or incorrect mapping results.

## 1. How Do Standard Embedding and Unwrapped Mapping Differ?

Suppose a customer profile includes a billing address:

```java
class Address {
    private String street;
    private String city;
    private String postalCode;
}

class CustomerProfile {
    private Address billingAddress;
}
```

If `billingAddress` uses **standard embedded mapping**, BSON looks like:

```javascript
{
  customerNo: "CUS-001",
  billingAddress: {
    street: "12 Sample St",
    city: "Ha Noi",
    postalCode: "100000"
  }
}
```

A raw MongoDB query uses dot notation:

```javascript
db.customer_profiles.find({ "billingAddress.city": "Ha Noi" });
```

If `@Unwrapped(prefix = "billing_")` is placed on `billingAddress`, BSON is flattened:

```javascript
{
  customerNo: "CUS-001",
  billing_street: "12 Sample St",
  billing_city: "Ha Noi",
  billing_postal_code: "100000"
}
```

With flattened data, a raw MongoDB query must use:

```javascript
db.customer_profiles.find({ billing_city: "Ha Noi" });
```

**Core implication:** `billingAddress.city` is the **Java property path**; `billing_city` is the **actual BSON field name**. MongoDB Server has no awareness of Spring Data's `@Unwrapped` annotation. Only operations flowing through the Spring Data MongoDB mapper with entity type information can translate paths.

| Perspective | Standard Embedding | `@Unwrapped(prefix = "billing_")` |
| --- | --- | --- |
| Java | `billingAddress.city` | `billingAddress.city` |
| BSON | `billingAddress: { city: ... }` | `billing_city: ...` |
| `mongosh` filter | `"billingAddress.city"` | `"billing_city"` |
| `MongoTemplate` with domain class | `"billingAddress.city"` | Usually still written as `"billingAddress.city"` so the mapper converts it to `billing_city` |
| Replace whole object via one BSON field | Has a `billingAddress` field | No `billingAddress` field exists to replace directly |

## 2. Declaring `@Unwrapped` in Spring Data MongoDB

### 2.1. A Complete Example with Prefix and `@Field`

```java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.Unwrapped;

@Document(collection = "customer_profiles")
public class CustomerProfile {
    @Id
    private ObjectId id;
    private String customerNo;
    private String displayName;

    @Unwrapped(
        prefix = "billing_",
        onEmpty = Unwrapped.OnEmpty.USE_NULL
    )
    private Address billingAddress;

    @Version
    private Long version;

    protected CustomerProfile() { }

    public CustomerProfile(
            String customerNo,
            String displayName,
            Address billingAddress) {
        this.customerNo = customerNo;
        this.displayName = displayName;
        this.billingAddress = billingAddress;
    }

    public ObjectId getId() { return id; }
    public String getCustomerNo() { return customerNo; }
    public String getDisplayName() { return displayName; }
    public Address getBillingAddress() { return billingAddress; }

    public static class Address {
        private String street;
        private String city;

        @Field("postal_code")
        private String postalCode;

        protected Address() { }

        public Address(String street, String city, String postalCode) {
            this.street = street;
            this.city = city;
            this.postalCode = postalCode;
        }

        public String getStreet() { return street; }
        public String getCity() { return city; }
        public String getPostalCode() { return postalCode; }
    }
}
```

Spring Data MongoDB maps the three properties `street`, `city`, and `postalCode` of `Address` onto the parent document. The `billing_` prefix is applied to the **stored field names**; because `postalCode` has `@Field("postal_code")`, the resulting field is `billing_postal_code`.

Example stored document, omitting `_class` for readability:

```javascript
{
  _id: ObjectId("665f1f2a4b6c7d8e9f001234"),
  customerNo: "CUS-001",
  displayName: "Example customer",
  billing_street: "12 Sample St",
  billing_city: "Ha Noi",
  billing_postal_code: "100000",
  version: NumberLong(0)
}
```

`_id` is generated by the application or driver, and the exact BSON type of `version` or presence of `_class` depends on configuration. The BSON above is an illustrative sample, **not a fixed output** across every Spring Data MongoDB version.

### 2.2. `@Unwrapped` Is Not an Independent Entity

`Address` is a **value object** owned by `CustomerProfile`. It has no `@Id` of its own, no separate repository, and is not written as an independent document in an `addresses` collection. Address changes must be managed through the `CustomerProfile` aggregate root.

Do not use `@Unwrapped` to model a link between two aggregates with independent lifecycles. If `Address` needs its own identity, independent change history, or sharing as a live object across multiple customers, consider references or a separate collection.

### 2.3. When No Prefix Is Specified

```java
@Unwrapped
private Address billingAddress;
```

With the default empty prefix, fields appear directly as `street`, `city`, and `postal_code` on the parent document. This is concise, but risks collisions if the root also defines `city` or holds multiple addresses.

Choosing meaningful prefixes such as `billing_`, `shipping_`, or `contact_` from the start keeps schemas readable and prevents collisions. Changing a prefix after data exists is a **BSON schema change** requiring a migration plan.

## 3. Querying via `MongoRepository` and Derived Queries

Declare a repository with the matching Java ID type:

```java
import java.util.List;
import java.util.Optional;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerProfileRepository
        extends MongoRepository<CustomerProfile, ObjectId> {

    Optional<CustomerProfile> findByCustomerNo(String customerNo);

    List<CustomerProfile> findByBillingAddressCity(String city);

    List<CustomerProfile>
        findByBillingAddressCityAndBillingAddressPostalCode(
            String city, String postalCode);
}
```

Spring Data parses the method name along Java class property paths, then applies `@Unwrapped` metadata when building the MongoDB query. `findByBillingAddressCity("Ha Noi")` targets BSON field `billing_city`, while the second method combines `billing_city` and `billing_postal_code`.

**Do not name repository methods after BSON fields** such as `findByBilling_city(...)` when the Java class has no such property. Derived queries are constructed from Java property names; prefixes are a MongoDB mapping detail. When property chains become long or ambiguous to the method-name parser, consider an explicit `@Query`.

### 3.1. `@Query` and Stored Field Names

```java
import org.springframework.data.mongodb.repository.Query;

@Query("{ 'billing_city': ?0 }")
List<CustomerProfile> findByBillingCityRaw(String city);
```

This illustrates an **additional method inside the repository interface** above. The JSON query references the BSON field `billing_city` directly, expressing the exact storage schema. Query string syntax and mapping behavior still depend on Spring Data, so write integration tests verifying the actual executed query whenever using property paths in JSON queries or changing prefixes.

### 3.2. Do Not Match the Whole Unwrapped Object as a Nested Document

This query **does not match the actual BSON**:

```javascript
// Wrong for a schema using @Unwrapped(prefix = "billing_").
db.customer_profiles.find({
  billingAddress: {
    city: "Ha Noi",
    postal_code: "100000"
  }
});
```

Because no `billingAddress` field exists in the stored document, this query fails to find documents as intended. Instead, filter by the flattened fields:

```javascript
db.customer_profiles.find({
  billing_city: "Ha Noi",
  billing_postal_code: "100000"
});
```

Similarly, with Spring Data query APIs, prefer **matching individual properties of the value object** rather than `Criteria.where("billingAddress").is(address)`. Serializing an entire value object as a single query operand is not equivalent to a nested BSON match and should not be relied upon as a design basis.

## 4. Querying via `MongoTemplate`: Property Paths vs. Raw BSON

With `MongoTemplate`, supply the **entity class** so Spring Data knows the `@Unwrapped` metadata:

```java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<CustomerProfile> findInCity(
        MongoTemplate template, String city) {

    Query query = Query.query(
        Criteria.where("billingAddress.city").is(city)
    );
    return template.find(query, CustomerProfile.class);
}
```

`billingAddress.city` is a **Java domain** path; the query mapper applies `@Unwrapped(prefix = "billing_")` to query `billing_city`. With the nested `@Field("postal_code")` annotation, you can query:

```java
Query query = Query.query(
    Criteria.where("billingAddress.postalCode").is("100000")
);
List<CustomerProfile> matches =
    template.find(query, CustomerProfile.class);
```

When there is no domain mapping—such as with the raw MongoDB Java Driver or `mongosh`—use the BSON field name:

```javascript
db.customer_profiles.find({
  billing_postal_code: "100000"
});
```

If you access a collection as `org.bson.Document`/raw BSON via the driver, annotations on `CustomerProfile` are not applied to handwritten query strings. Never assume a raw query automatically translates `billingAddress.postalCode` into `billing_postal_code`.

### 4.1. Multi-Criteria Filtering and Projections

Example finding profiles by customer number and city:

```java
Query query = Query.query(
    Criteria.where("customerNo").is("CUS-001")
        .and("billingAddress.city").is("Ha Noi")
);
query.fields().include("customerNo");
query.fields().include("displayName");
query.fields().include("billingAddress.city");

List<CustomerProfile> result =
    template.find(query, CustomerProfile.class);
```

**Watch out for partial projections:** projecting only `billing_city` without `billing_street` and `billing_postal_code` reconstructs an **incomplete** `Address` object. Combined with `onEmpty`, completely missing fields also affect whether `Address` is constructed or set to `null`. Never take a partially projected entity and pass it back to `save` as if it were the full aggregate; full-document replacement can wipe out unloaded fields.

If you only need fields for display, use a dedicated read DTO/projection, or update only target fields with conditional updates rather than overwriting the entire document.

### 4.2. Verifying Queries with `mongosh`

```javascript
db.customer_profiles.find(
  {
    customerNo: "CUS-001",
    billing_city: "Ha Noi"
  },
  {
    _id: 0,
    customerNo: 1,
    displayName: 1,
    billing_city: 1
  }
);
```

When debugging unexpected query results, inspect **actual field names** in BSON via `findOne` and compare them against entity metadata: prefixes, `@Field`, and whether writes came from Spring Data or the raw driver.

## 5. Updating Individual Unwrapped Fields with `MongoTemplate`

A MongoDB update modifies **BSON fields**, not an imaginary nested Java object path. The safe pattern with `@Unwrapped` is updating **individual properties**.

### 5.1. Updating City and Postal Code in One Command

```java
import org.bson.types.ObjectId;
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public UpdateResult changeBillingLocation(
        MongoTemplate template, ObjectId profileId,
        String city, String postalCode) {

    Query query = Query.query(
        Criteria.where("id").is(profileId)
    );
    Update update = new Update()
        .set("billingAddress.city", city)
        .set("billingAddress.postalCode", postalCode);

    return template.updateFirst(
        query, update, CustomerProfile.class
    );
}
```

With `CustomerProfile.class`, the mapper resolves:

| Path in `Update` | BSON Field to Update |
| --- | --- |
| `billingAddress.city` | `billing_city` |
| `billingAddress.postalCode` | `billing_postal_code` |
| `billingAddress.street` | `billing_street` |

A single `updateFirst` modifies all specified fields on **one document** atomically. Check `getMatchedCount()` and `getModifiedCount()` on `UpdateResult`: zero matched means the filter matched no document; zero modified can mean setting the same value already stored (or other update-specific details).

In most applications, before updating you also need authorization checks and validation on `city`/`postalCode`. `@Unwrapped` is purely mapping metadata; it enforces no business rules.

### 5.2. Equivalent `mongosh` Command

```javascript
db.customer_profiles.updateOne(
  { customerNo: "CUS-001" },
  {
    $set: {
      billing_city: "Da Nang",
      billing_postal_code: "550000"
    }
  }
);
```

Running `$set: { "billingAddress.city": "Da Nang" }` directly on a flattened collection creates a **separate nested document** in BSON instead of modifying the existing `billing_city`. That kind of schema drift is especially dangerous when operational scripts run outside Spring Data.

### 5.3. Do Not `$set` the Whole Unwrapped Object as a Single Field

The following cannot be interpreted as "update all flattened fields" under MongoDB rules:

```javascript
// Do not use with an unwrapped schema: creates/replaces a billingAddress field.
db.customer_profiles.updateOne(
  { customerNo: "CUS-001" },
  {
    $set: {
      billingAddress: {
        city: "Da Nang",
        postalCode: "550000"
      }
    }
  }
);
```

This writes to a new `billingAddress` field, while real data lives in `billing_city` and `billing_postal_code`. At the Spring Data layer, do not rely on `new Update().set("billingAddress", address)` as a monolithic replacement API for an unwrapped object: depending on mapping support and version, it may be unsupported or behave differently from per-field updates.

If business logic needs to replace the entire address, **include every constituent field in the same update**. When clearing an old value, add `unset` for the corresponding field so stale values do not linger.

## 6. Removing Fields, `null`, and `onEmpty`

### 6.1. `USE_NULL` and `USE_EMPTY` When Reading

`@Unwrapped` has an `onEmpty` option that decides how Spring Data handles a value object when **there are no populated fields to construct it**:

| Configuration | Expected Behavior When All Unwrapped Fields Are Empty/Missing |
| --- | --- |
| `Unwrapped.OnEmpty.USE_NULL` | Java property `billingAddress` is read as `null` |
| `Unwrapped.OnEmpty.USE_EMPTY` | Spring Data attempts to instantiate an empty `Address` via its instantiation mechanism |

When at least one useful field exists, `Address` can be constructed with missing fields holding `null` or Java defaults. Exact behavior is also affected by constructors, conversions, and Spring Data versions; test with real data, especially when distinguishing BSON Null from missing fields matters.

Example changing the setting:

```java
@Unwrapped(
    prefix = "billing_",
    onEmpty = Unwrapped.OnEmpty.USE_EMPTY
)
private Address billingAddress;
```

**Important:** `onEmpty` is a **read-time object instantiation** rule; it does not make MongoDB store a `billingAddress: {}` document, nor is it a validation rule ensuring an address is always valid.

### 6.2. `$unset` Each Flattened Field

To remove the entire address from our example profile:

```javascript
db.customer_profiles.updateOne(
  { customerNo: "CUS-001" },
  {
    $unset: {
      billing_street: "",
      billing_city: "",
      billing_postal_code: ""
    }
  }
);
```

After this update, the three BSON fields **no longer exist**. With `USE_NULL`, reading back via Spring Data usually yields `billingAddress == null`. With `USE_EMPTY`, you can get an empty `Address`. Direct `mongosh` output carries none of this mapping behavior.

In `MongoTemplate`:

```java
Update clearAddress = new Update()
    .unset("billingAddress.street")
    .unset("billingAddress.city")
    .unset("billingAddress.postalCode");

template.updateFirst(
    Query.query(Criteria.where("id").is(profileId)),
    clearAddress,
    CustomerProfile.class
);
```

Do not treat `$set: { billing_city: null }` as equivalent to `$unset: { billing_city: "" }`. MongoDB distinguishes **BSON Null** from a **non-existent field**; `{ billing_city: null }` matches both, whereas `{ billing_city: { $exists: false } }` matches only missing fields.

### 6.3. Inspecting Empty Data

```javascript
// Address missing city field:
db.customer_profiles.find({
  billing_city: { $exists: false }
});

// City field exists with BSON Null:
db.customer_profiles.find({
  billing_city: { $type: "null" }
});

// No address fields at all:
db.customer_profiles.find({
  billing_street: { $exists: false },
  billing_city: { $exists: false },
  billing_postal_code: { $exists: false }
});
```

These queries help find incomplete documents before changing `onEmpty` or running a migration.

## 7. Preventing Lost Updates with `@Version` and Compare-and-Set

With `@Version` on the root, `repository.save(profile)` checks the version when writing. If two requests read the same old state and update the address, the second request cannot silently overwrite the first when optimistic locking is active and writes are acknowledged.

However, `MongoTemplate.updateFirst` **does not automatically know which version the client read** if the query filters only by `id`. Some Spring Data update APIs may increment `version` automatically, yet **incrementing version** is not the same as **matching expected version**.

To enforce the version check explicitly, include it in the query:

```java
public boolean changeCityIfVersionMatches(
        MongoTemplate template,
        ObjectId profileId,
        long expectedVersion,
        String newCity) {

    Query query = Query.query(
        Criteria.where("id").is(profileId)
            .and("version").is(expectedVersion)
    );
    Update update = new Update()
        .set("billingAddress.city", newCity)
        .inc("version", 1);

    return template.updateFirst(
        query, update, CustomerProfile.class
    ).getModifiedCount() == 1;
}
```

This example assumes `version` already holds a `Long` value. If nothing matches, return an appropriate business error—such as HTTP 409 Conflict after inspecting the cause—rather than retrying endlessly. Because the update targets one document, changing the city and incrementing version happen atomically.

**Do not blindly mix** manual version updates with `save` or callbacks that also alter version. Every write path must share the same optimistic locking contract and check `matchedCount`/`modifiedCount` after writing.

## 8. Indexes, Aggregations, and Projections on Flattened BSON Names

### 8.1. Indexes on Physical Fields

If queries often look up customers by city and postal code, create a compound index:

```javascript
db.customer_profiles.createIndex(
  { billing_city: 1, billing_postal_code: 1 },
  { name: "idx_billing_city_postal" }
);

db.customer_profiles.getIndexes();
```

In raw index definitions, use **BSON field names**. Defining an index on `"billingAddress.city"` indexes a **different nested path** and will not speed up queries on `billing_city`.

Index metadata can be declared in Spring Data or created explicitly via `IndexOperations`/migrations. **Automatic index creation** from annotations is typically disabled by default in modern Spring Data MongoDB versions; verify indexes exist in MongoDB rather than relying solely on annotations.

Inspect the query plan:

```javascript
db.customer_profiles.find({
  billing_city: "Ha Noi",
  billing_postal_code: "100000"
}).explain("executionStats");
```

Review `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, and `nReturned`; metrics also depend on data volume and MongoDB version. A tiny dataset is not enough to prove an index lowers latency in production.

### 8.2. Raw Aggregations Use BSON Field Names

Count profiles by billing city:

```javascript
db.customer_profiles.aggregate([
  { $match: { billing_city: { $exists: true } } },
  {
    $group: {
      _id: "$billing_city",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

`$group` uses `"$billing_city"` rather than `"$billingAddress.city"`, because this raw pipeline runs directly on BSON inside MongoDB Server.

When building typed aggregations in Spring Data, the mapper can use domain class metadata to translate property paths. Still, custom JSON/`Document` stages, computed fields, projection aliases, and multi-collection pipelines can have different mapping contexts. Inspect the generated pipeline or run integration tests rather than assuming every string in a pipeline is mapped just like `Query`.

### 8.3. Distinguishing Indexes from Schema Validation

`@Unwrapped` **does not guarantee** flattened fields have the right types or are always present. To enforce checks at the database level, define a MongoDB JSON Schema validator against BSON fields `billing_city` and `billing_postal_code`, not an imaginary `billingAddress` object.

Illustrative schema fragment for the address fields:

```javascript
{
  bsonType: "object",
  properties: {
    billing_city: { bsonType: "string" },
    billing_postal_code: { bsonType: "string" }
  }
}
```

This is an **illustrative schema snippet** to place inside `$jsonSchema` when configuring a validator. Indexes serve queries and uniqueness constraints; validators enforce document structure and types. They are separate mechanisms.

## 9. Limitations and Unsuitable Cases for `@Unwrapped`

| Situation | Problem | Design Guidance |
| --- | --- | --- |
| Root and unwrapped object both have a `city` field | Without a prefix, both compete for the same BSON key | Use distinct prefixes; review field ownership |
| Both `billingAddress` and `shippingAddress` | Unwrapping both without prefixes collides on `street`/`city` | Use `billing_` and `shipping_` |
| Querying the whole `Address` | No `billingAddress` BSON field exists to match as an object | Query individual flattened fields |
| `$set` of an entire object | Raw BSON writes to a new `billingAddress` field | `$set` each `billing_*` key in one command |
| Dynamic collections or maps as value objects | Unbounded/dynamic child keys risk unpredictable collisions | Use nested documents or properly structured maps |
| Value object has its own ID or lifecycle | Not a dependent component of one aggregate root | Split into its own aggregate/collection with references |
| Need to query an array of addresses element by element | Flattening does not preserve an array of multiple addresses | Use a nested array and `$elemMatch` when appropriate |
| Refactoring `prefix` or `@Field` names | Old documents keep old BSON keys | Plan a migration with pre/post checks |
| Reading partial fields and calling `save` | May overwrite the document with an incomplete object | Use dedicated read DTO/projections or targeted updates |
| Data written by scripts and Spring Data | Raw scripts lack the mapper and may create nested fields accidentally | Standardize the BSON naming contract and write integration tests |

### 9.1. Field Name Collisions Are Schema Bugs

Suppose the root class has `private String city` alongside:

```java
@Unwrapped
private Address billingAddress;
```

Both root `city` and `billingAddress.city` target the BSON key `city`. These are not independent storage slots in the document. Fix the structure or configure a prefix:

```java
@Unwrapped(prefix = "billing_")
private Address billingAddress;
```

Never rely on mapping order to guess which field overwrites the other. Even if names do not collide today, adding a property to the value object later can introduce a collision if there is no prefix.

### 9.2. Do Not Blindly Use `@Unwrapped` for Polymorphic or Dynamic Types

`@Unwrapped` works best with **value objects that have a bounded, stable structure** owned by one aggregate. If a value object has multiple subtypes, constantly changing child fields, or a collection requiring separate pagination, flattening blurs structural boundaries and complicates deserialization.

Before combining `@Unwrapped` with polymorphism, nested unwrapping, maps, or collections, verify support in your exact Spring Data MongoDB version and write integration tests. When a child structure must remain a cohesive BSON unit, standard embedding is clearer.

### 9.3. Do Not Expect Automatic Cascades or Transactions

`@Unwrapped` is mapping metadata, **not** a foreign-key constraint, cascade rule, or transaction boundary. Updating one or more flattened fields inside a single document is atomic at the document level in MongoDB. If updating another document simultaneously is required (for example, customer profile plus an address statistics table in another collection), design a multi-document transaction or an asynchronous consistency workflow.

## 10. Hands-on with `mongosh`: Inspecting Flattened Data

Create test data in an isolated collection, tagging each run with a unique marker to avoid altering other data:

```javascript
use spring_data_training

const lab = db.getCollection("unwrapped_lab");
const runId = "embedded-objects-008-" + new ObjectId().toHexString();

const insertion = lab.insertOne({
  runId: runId,
  customerNo: "CUS-LAB-001",
  displayName: "Test customer",
  billing_street: "10 Sample St",
  billing_city: "Ha Noi",
  billing_postal_code: "100000"
});

printjson(insertion.insertedId);
printjson(lab.findOne({ _id: insertion.insertedId, runId: runId }));
```

`unwrapped_lab` is a **different** collection from `customer_profiles` in the Java example above; it is solely for inspecting raw BSON syntax. To read these documents with `CustomerProfile`, map the entity to the corresponding collection or specify the collection in the read operation.

### 10.1. Querying the Right Field

```javascript
lab.find({
  _id: insertion.insertedId,
  runId: runId,
  billing_city: "Ha Noi"
}).toArray();

// Does not match because raw BSON has no billingAddress.city:
lab.find({
  _id: insertion.insertedId,
  runId: runId,
  "billingAddress.city": "Ha Noi"
}).toArray();
```

### 10.2. Atomic Update of Two Fields

```javascript
const updateResult = lab.updateOne(
  { _id: insertion.insertedId, runId: runId },
  {
    $set: {
      billing_city: "Da Nang",
      billing_postal_code: "550000"
    }
  }
);

printjson({
  matchedCount: updateResult.matchedCount,
  modifiedCount: updateResult.modifiedCount
});
```

Read back:

```javascript
lab.findOne(
  { _id: insertion.insertedId, runId: runId },
  {
    _id: 0,
    billing_street: 1,
    billing_city: 1,
    billing_postal_code: 1,
    billingAddress: 1
  }
);
```

The result shows the three `billing_*` fields and no `billingAddress` field.

### 10.3. Removing Individual Fields

```javascript
lab.updateOne(
  { _id: insertion.insertedId, runId: runId },
  { $unset: { billing_street: "", billing_postal_code: "" } }
);

lab.findOne({
  _id: insertion.insertedId,
  runId: runId
});
```

`billing_city` still exists, so a Java `Address` read back has `city`, while `street` and `postalCode` are `null`. Only when every field belonging to the unwrapped object is empty or absent does `onEmpty` govern constructing an empty object per configuration.

### 10.4. Cleaning Up Test Data

```javascript
lab.deleteOne({
  _id: insertion.insertedId,
  runId: runId
});
```

Never run `deleteMany({})` or `drop()` on a real collection. Delete only the document created in the current run. If you want to inspect it in MongoDB Compass, clean up **after** inspecting.

## 11. Integration Testing Mapping and Write Paths

Because `@Unwrapped` alters field names **in BSON**, unit tests checking Java objects alone are insufficient. Integration tests with a real MongoDB or Testcontainers MongoDB should verify both sides:

1. Persist `CustomerProfile` via the repository.
2. Read raw BSON from `customer_profiles`, verifying `billing_city` **is present** and `billingAddress` **is absent**.
3. Query via `findByBillingAddressCity` and `MongoTemplate` using property paths.
4. Update via `Update.set("billingAddress.city", ...)`, verifying the raw field actually changes.
5. Test partial fields, absent fields, and `USE_NULL` / `USE_EMPTY` settings.
6. Test version conflicts or concurrent updates when required by business rules.

Skeleton integration test for the first two steps, using Spring Boot Test / JUnit 5 with repository and template pointed at a test MongoDB:

```java
import static org.junit.jupiter.api.Assertions.*;
import static com.mongodb.client.model.Filters.eq;

import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@SpringBootTest
class UnwrappedMappingTest {
    @Autowired CustomerProfileRepository repository;
    @Autowired MongoTemplate template;

    @Test
    void storesFlatFieldsInsteadOfNestedAddress() {
        var address = new CustomerProfile.Address(
            "10 Sample St", "Ha Noi", "100000"
        );
        var profile = repository.insert(
            new CustomerProfile("CUS-TEST-001", "Test customer", address)
        );

        try {
            Document raw = template.getCollection("customer_profiles")
                .find(eq("_id", profile.getId()))
                .first();

            assertNotNull(raw);
            assertEquals("Ha Noi", raw.getString("billing_city"));
            assertEquals("100000",
                         raw.getString("billing_postal_code"));
            assertFalse(raw.containsKey("billingAddress"));

            assertFalse(
                repository.findByBillingAddressCity("Ha Noi").isEmpty()
            );
        } finally {
            repository.deleteById(profile.getId());
        }
    }
}
```

Customer codes in this example are illustrative; in test environments, isolate databases/collections and avoid relying on hardcoded names that could collide across runs. This test requires a running MongoDB and suitable Spring Boot test configuration. As a lesson sample, the code is provided for practice and was not executed in the workspace while authoring this material.

### Checks When Modifying Metadata

If `@Field("postal_code")` is renamed to `@Field("zip")` or the prefix changes from `billing_` to `invoice_`, existing documents **do not rename their fields automatically**. Before releasing:

- Inventory existing collections and BSON fields.
- Define old/new schemas and how reads behave during the transition.
- Run a controlled migration, considering `$rename` on **actual** field names when appropriate.
- Update indexes, raw queries, aggregations, validators, and Java code.
- Run integration tests and verify data before and after migration.

Illustrative BSON rename command, **run only on test data after evaluating risks**:

```javascript
// Example renaming an old flattened field to a new flattened field.
db.customer_profiles.updateMany(
  { billing_postal_code: { $exists: true } },
  { $rename: { billing_postal_code: "invoice_postal_code" } }
);
```

This modifies many documents at once and is not an automatic transactional migration. Before applying in practice, handle documents that already have the target field, rollback plans, index updates, and all active read/write paths.

## 12. Practice Exercises

**Exercise 1 — Determine BSON layout.** An `Employee` class has `@Unwrapped(prefix = "contact_") ContactInfo contact`, where `ContactInfo` has `email`, `phone`, and `@Field("emergency_phone") emergencyPhone`. Write the expected BSON document, then write a `mongosh` filter searching by email.

**Exercise 2 — Repository and template.** Write `findByContactEmail(...)` on a repository, `Criteria.where("contact.email").is(...)` for `MongoTemplate`, and the equivalent raw query. Explain when the mapper applies the prefix.

**Exercise 3 — Updating the right fields.** Write an `Update` changing both email and phone of `ContactInfo` in a single write. Write the equivalent `mongosh` command and explain the danger of `$set: { contact: {...} }`.

**Exercise 4 — Missing fields and nulls.** Test three documents: no `contact_*` fields, only `contact_email`, and `contact_email: null`. Compare reads under `onEmpty = USE_NULL` and `onEmpty = USE_EMPTY`. Verify with an integration test.

**Exercise 5 — Name collisions.** A class has `@Unwrapped Address homeAddress` and `@Unwrapped Address officeAddress`, both containing `city`. Propose two prefixes, write the BSON shape, and design an index for querying by office city.

**Exercise 6 — Projections and optimistic locking.** A service reads only `contact_email` and then saves the entire `Employee`. Point out the field-loss risk and propose a conditional update by `id` and `version`. Define what status the application should return when the version no longer matches.

**Exercise 7 — Schema refactoring.** When renaming prefix `contact_` to `primary_contact_`, list everything that must be updated: legacy data, repository queries, raw Mongo queries, pipelines, indexes, validators, tests, and write paths from other services.

### Key Takeaways

**`@Unwrapped` flattens a value object into its parent document.** Java still uses property paths like `billingAddress.city`, whereas BSON stores fields like `billing_city`. Repositories and `MongoTemplate` use entity metadata to translate queries and updates; `mongosh`, Compass, raw drivers, indexes, and raw aggregations must use **actual BSON field names**. Prefer querying and updating individual flattened fields, use prefixes to prevent collisions, check `onEmpty` for missing fields, and never replace whole unwrapped objects or save partially projected entities. Testing against a real MongoDB instance is the surest way to confirm every mapping path works properly.
