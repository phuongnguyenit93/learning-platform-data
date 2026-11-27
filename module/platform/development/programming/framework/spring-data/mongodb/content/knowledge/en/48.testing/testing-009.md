# Testing Null, Missing Fields, Embedded Documents, and References

> **Chapter:** Testing  
> **Scope:** Spring Data MongoDB — testing document mapping, queries with `MongoTemplate`/repositories, null and missing values, embedded documents, and cross-collection references.

## 1. Why Does This Topic Matter?

MongoDB does not force documents in a collection to share the same structure. A field can be absent altogether, hold BSON `null`, or contain an empty string, empty array, or empty object. Child documents can also be embedded directly or referenced from another collection.

Example:

```javascript
// A: nickname is completely missing
{ _id: "a", tenantId: "t1" }

// B: nickname key exists with value BSON Null
{ _id: "b", tenantId: "t1", nickname: null }

// C: nickname has content
{ _id: "c", tenantId: "t1", nickname: "Lan" }
```

When Spring Data maps these documents to a POJO with property `String nickname`, both A and B normally yield Java `null`. If a test only checks `profile.nickname == null`, it cannot tell whether the field actually exists in BSON.

This distinction affects `$exists`, `$type`, queries, unique indexes, `$unset` updates, legacy data migrations, and business rules. For references, a Java object may appear to contain child data while the database actually stores only an ID or a DBRef.

**Goal:** verify **real BSON**, **Java mapping results**, and **query/update behavior** separately, instead of inspecting only Java objects after reading.

## 2. Distinguishing BSON Null, Missing, and Empty Values

| Predicate for scalar field `nickname` | Missing field | `nickname: null` | `nickname: "Lan"` |
| --- | :---: | :---: | :---: |
| `{ nickname: null }` | Yes | Yes | No |
| `{ nickname: { $type: 10 } }` | No | Yes | No |
| `{ nickname: { $exists: false } }` | Yes | No | No |
| `{ nickname: { $exists: true } }` | No | Yes | Yes |
| `{ nickname: { $ne: null } }` | No | No | Yes |

These are the rules for scalar fields. When the field is an array, matching operators can inspect array elements; arrays containing null elements must be tested separately.

In Spring Data MongoDB, use:

```java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query nullOrMissing = Query.query(
    Criteria.where("nickname").isNull()
);
Query explicitNullOnly = Query.query(
    Criteria.where("nickname").isNullValue()
);
Query missingOnly = Query.query(
    Criteria.where("nickname").exists(false)
);
Query present = Query.query(
    Criteria.where("nickname").exists(true)
);
```

- `isNull()` uses null equality, matching **both null and missing**.
- `isNullValue()` checks BSON Null type, matching **only explicit null**.
- `exists(false)` requires the key to be absent; `exists(true)` still matches a key whose value is null.

The helpers `isNull()` and `isNullValue()` exist since Spring Data MongoDB 3.3. A repository method like `findByNicknameIsNull()` can generate null equality, so **do not assume** it matches only explicit BSON Null fields. Whenever business rules distinguish the two, inspect the generated BSON query.

Empty string `""`, number `0`, boolean `false`, object `{}`, and array `[]` are real, present BSON values. Never conflate them with null or missing in fixture design.

## 3. Java Mapping Can Hide Field Presence

`MappingMongoConverter` converts BSON into Java objects. In particular, for a reference property like `String`, both a missing field and an explicit null map to the same Java `null`. Furthermore, constructors, default field initializers, and custom converters can affect what happens when a property is missing.

On the write side, Spring Data MongoDB offers two strategies:

| Mapping | Java value | BSON written by converter |
| --- | --- | --- |
| Default, `Field.Write.NON_NULL` | `null` | Normally **omits the key** |
| `@Field(write = Field.Write.ALWAYS)` | `null` | Writes **key: null** |
| Any standard mapping | Non-null value | Writes the corresponding BSON value |

Illustrative entity:

```java
package example.mongodb;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document("profiles")
public class Profile {
    @Id
    public String id;

    public String nickname; // null may be omitted from BSON by default

    @Field(value = "note", write = Field.Write.ALWAYS)
    public String note;     // null still writes BSON key "note"

    public Contact contact; // embedded document

    public Profile() {}
    public Profile(String id) { this.id = id; }
}

class Contact {
    public String phone;

    @Field("postal_code")
    public String postalCode;

    public Contact() {}
}
```

Public fields are used here for brevity in a learning example. Real projects typically use private fields with getters/setters or constructors compatible with Spring Data. Depending on version, `@Field(write = Field.Write.ALWAYS)` has been available since Spring Data MongoDB 3.3.

To verify raw field presence, read the **raw BSON document** via `MongoTemplate.getCollection(...)` and check `org.bson.Document.containsKey(...)`. Relying on entity getters alone is not enough.

## 4. Integration Test Suite Using `@DataMongoTest`

To verify real MongoDB semantics, use an actual MongoDB test instance, such as Testcontainers. The snippet below uses **Spring Boot 3.x, the corresponding Spring Data MongoDB, JUnit Jupiter, AssertJ, and Testcontainers 1.x**. You need the MongoDB starter, test starter, `spring-boot-testcontainers`, and Testcontainers MongoDB/JUnit Jupiter dependencies; Docker must be running.

```java
package example.mongodb;

import static org.assertj.core.api.Assertions.assertThat;
import static com.mongodb.client.model.Filters.eq;

import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@DataMongoTest
@Testcontainers
class ProfileTest {
    @Container
    @ServiceConnection
    static final MongoDBContainer mongo =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"));

    @Autowired
    MongoTemplate template;

    @BeforeEach
    void clean() {
        // Use only a dedicated test container/database.
        template.dropCollection(Profile.class);
    }

    @Test
    void distinguishesMissingAndNullInQueries() {
        // Raw BSON fixtures preserve the distinction between null and missing.
        template.getCollection("profiles").insertMany(List.of(
            new Document("_id", "missing"),
            new Document("_id", "null").append("nickname", null),
            new Document("_id", "value").append("nickname", "Lan")
        ));

        assertThat(template.count(
            Query.query(Criteria.where("nickname").isNull()), Profile.class
        )).isEqualTo(2);

        assertThat(template.count(
            Query.query(Criteria.where("nickname").isNullValue()), Profile.class
        )).isEqualTo(1);

        assertThat(template.count(
            Query.query(Criteria.where("nickname").exists(false)), Profile.class
        )).isEqualTo(1);

        assertThat(template.count(
            Query.query(Criteria.where("nickname").exists(true)), Profile.class
        )).isEqualTo(2);

        Document absent = template.getCollection("profiles")
            .find(eq("_id", "missing")).first();
        Document hasNull = template.getCollection("profiles")
            .find(eq("_id", "null")).first();

        assertThat(absent).isNotNull();
        assertThat(absent.containsKey("nickname")).isFalse();
        assertThat(hasNull).isNotNull();
        assertThat(hasNull.containsKey("nickname")).isTrue();
        assertThat(hasNull.get("nickname")).isNull();

        // Java objects cannot distinguish these two via String:
        assertThat(template.findById("missing", Profile.class).nickname).isNull();
        assertThat(template.findById("null", Profile.class).nickname).isNull();
    }

    @Test
    void writesExplicitNullOnlyForConfiguredField() {
        template.save(new Profile("p-1"));

        Document raw = template.getCollection("profiles")
            .find(eq("_id", "p-1")).first();
        assertThat(raw).isNotNull();
        assertThat(raw.containsKey("nickname")).isFalse();
        assertThat(raw.containsKey("note")).isTrue();
        assertThat(raw.get("note")).isNull();
    }
}
```

For fixtures that must distinguish null from missing, inserting via the MongoDB driver directly as shown is the clearest approach: saving two POJOs with null properties would produce two documents missing the field if the converter skips nulls.

`@DataMongoTest` loads MongoDB infrastructure but **does not start a server automatically**. `@ServiceConnection` (Spring Boot 3.1+) receives connection details from Testcontainers. On earlier versions, use `@DynamicPropertySource` with `mongo.getReplicaSetUrl()` and `spring.data.mongodb.uri` matching your Spring Boot setup.

## 5. Testing `$set: null` vs. `$unset`

When document `p-1` already exists, these two operations yield different BSON outcomes:

```java
Query byId = Query.query(Criteria.where("_id").is("p-1"));

template.updateFirst(
    byId, new Update().set("nickname", null), Profile.class
);
Document setNull = template.getCollection("profiles")
    .find(eq("_id", "p-1")).first();
assertThat(setNull.containsKey("nickname")).isTrue();
assertThat(setNull.get("nickname")).isNull();

template.updateFirst(
    byId, new Update().unset("nickname"), Profile.class
);
Document removed = template.getCollection("profiles")
    .find(eq("_id", "p-1")).first();
assertThat(removed.containsKey("nickname")).isFalse();
```

This snippet extends a test method with `template` injected and fixture `p-1` already created. `Update.set(..., null)` sets the field to BSON Null; `Update.unset(...)` removes the field altogether. After both operations, the POJO read back still shows Java `null`, making raw BSON assertions essential.

Do not conflate expectations for `save(entity)` with `Update.set`/`Update.unset`: `save` serializes the entire entity per converter mapping rules, whereas update operators modify specific fields in the database.

## 6. Embedded Documents: Structure, Nested Paths, and Null

With `Profile.contact` (without reference annotations), data lives **inside the same document**:

```javascript
{
  _id: "p-contact",
  contact: { phone: "0901234567", postal_code: "700000" }
}
```

Next test example to place inside `ProfileTest`:

```java
@Test
void mapsEmbeddedDocumentAndNestedQuery() {
    Profile p = new Profile("p-contact");
    p.contact = new Contact();
    p.contact.phone = "0901234567";
    p.contact.postalCode = "700000";
    template.insert(p);

    Document raw = template.getCollection("profiles")
        .find(eq("_id", "p-contact")).first();
    assertThat(raw).isNotNull();
    assertThat(raw.get("contact")).isInstanceOf(Document.class);

    Document nested = raw.get("contact", Document.class);
    assertThat(nested.getString("phone")).isEqualTo("0901234567");
    assertThat(nested.getString("postal_code")).isEqualTo("700000");
    assertThat(nested.containsKey("postalCode")).isFalse();

    Query query = Query.query(
        Criteria.where("contact.postalCode").is("700000")
    );
    List<Profile> results = template.find(query, Profile.class);
    assertThat(results).hasSize(1);
    assertThat(results.get(0).contact.postalCode).isEqualTo("700000");
}
```

In a `MongoTemplate` query bound to entity `Profile`, `QueryMapper` maps the Java path `contact.postalCode` to BSON `contact.postal_code`. Conversely, when querying `MongoCollection<Document>` directly via the driver, you must use the exact BSON name `contact.postal_code`.

### 6.1. Distinct States of a Nested Field

| Raw BSON | Parent state | State of path `contact.phone` |
| --- | --- | --- |
| `{}` | No `contact` | Missing |
| `{contact: null}` | Parent is BSON Null | No nested key |
| `{contact: {}}` | Object exists but empty | Missing |
| `{contact: {phone: null}}` | Object exists | Explicit BSON Null |
| `{contact: {phone: ""}}` | Object exists | Empty string |
| `{contact: {phone: "090..."}}` | Object exists | Has value |

To find missing nested `phone`:

```java
Query phoneMissing = Query.query(
    Criteria.where("contact.phone").exists(false)
);
Query phoneExplicitlyNull = Query.query(
    Criteria.where("contact.phone").isNullValue()
);
```

`exists(false)` on `contact.phone` matches both documents lacking `contact` and documents that have `contact` without `phone`. If you want only cases where the parent exists and is an object, add conditions on the parent and its BSON type. A Java assertion `profile.contact == null` cannot prove whether the raw parent is missing or explicitly null.

### 6.2. Embedded Arrays and `$elemMatch`

For `List<Contact> contacts`, fixtures should cover: missing, null, `[]`, one valid element, one null element, and multiple objects whose attributes satisfy conditions across **different elements**. A query like:

```javascript
{
  "contacts.phone": "0901234567",
  "contacts.postal_code": "700000"
}
```

can match when the two conditions hold on two separate elements. When both must hold on the **same contact**, test with `$elemMatch`:

```javascript
{
  contacts: {
    $elemMatch: {
      phone: "0901234567",
      postal_code: "700000"
    }
  }
}
```

Do not treat a non-null POJO list as proof that the raw document stored an array instead of null or missing; verify against raw BSON.

## 7. How Do Embedded and Referenced Documents Differ?

| Aspect | Embedded `Contact` | `@DocumentReference` | `@DBRef` |
| --- | --- | --- | --- |
| Parent stores | Nested object directly | Pointer, defaulting to target's ID | DBRef value (`$ref`, `$id`) |
| Target document | No separate document | Lives in a separate collection | Lives in a separate collection |
| Read behavior | Nested BSON mapping | Spring Data resolves reference | Spring Data DBRef resolver |
| Save target when saving parent | Same document | **No auto-cascade** | **No auto-cascade** |
| When target is deleted | No foreign target | Pointer can become dangling | DBRef can become dangling |
| Key test focus | Nested structure | BSON pointer, resolution, dangling ref | DBRef BSON, lazy/eager resolution |

**Do not equate `@DocumentReference` with `@DBRef`**: their BSON representations differ, so switching annotations can require a data migration.

### 7.1. Model with `@DocumentReference`

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.DocumentReference;

@Document("customers")
class Customer {
    @Id public String id;
    public String name;

    public Customer() {}
    public Customer(String id, String name) {
        this.id = id;
        this.name = name;
    }
}

@Document("orders")
class SalesOrder {
    @Id public String id;

    @DocumentReference
    public Customer customer;

    public SalesOrder() {}
    public SalesOrder(String id, Customer customer) {
        this.id = id;
        this.customer = customer;
    }
}
```

With ID `"c-1"`, the `orders` document normally stores `customer: "c-1"`, not the entire customer object. Simple IDs are used here so strings resembling 24-hex-digit ObjectIds are not implicitly converted by drivers/converters.

### 7.2. Testing References and Cascade Boundaries

```java
@Test
void storesPointerAndResolvesReference() {
    Customer customer = template.insert(new Customer("c-1", "Lan"));
    template.insert(new SalesOrder("o-1", customer));

    Document raw = template.getCollection("orders")
        .find(eq("_id", "o-1")).first();
    assertThat(raw).isNotNull();
    assertThat(raw.get("customer")).isEqualTo("c-1");

    SalesOrder loaded = template.findById("o-1", SalesOrder.class);
    assertThat(loaded).isNotNull();
    assertThat(loaded.customer).isNotNull();
    assertThat(loaded.customer.name).isEqualTo("Lan");
}

@Test
void saveParentDoesNotCascadeInsertToTarget() {
    Customer unsaved = new Customer("c-unsaved", "Bình");
    template.insert(new SalesOrder("o-2", unsaved));

    Document raw = template.getCollection("orders")
        .find(eq("_id", "o-2")).first();
    assertThat(raw.get("customer")).isEqualTo("c-unsaved");
    assertThat(template.findById("c-unsaved", Customer.class)).isNull();
}
```

Both tests belong in a `@DataMongoTest` class with `MongoTemplate`, and cleanup must clear both `orders` and `customers` to prevent leakage from earlier tests. Save the target before saving the parent whenever business rules require valid references. A Java object carrying an ID in memory **does not automatically become a document in the target collection**.

### 7.3. Dangling References and Lazy Loading

Scenario to test:

1. Save `Customer` and a `SalesOrder` referencing that customer.
2. Delete the customer while keeping the order.
3. Read raw BSON of the order: the pointer remains.
4. Read the reference property via Spring Data and observe actual behavior for your version/resolver.

Avoid hardcoding a single expected outcome (e.g., always null) across all reference types and versions. Resolvers handle broken references differently. With `@DocumentReference(lazy = true)` or `@DBRef(lazy = true)`, `findById(...)` may not resolve the target yet; actually access the property. Debug helpers such as `toString()` can also unexpectedly trigger lazy loading.

### 7.4. DBRef

Example:

```java
@Document("legacy_orders")
class LegacyOrder {
    @Id public String id;

    @DBRef
    public Customer customer;
}
```

Raw BSON for `customer` is stored as a DBRef, equivalent to:

```javascript
{ _id: "legacy-1", customer: DBRef("customers", "c-1") }
```

Tests must verify the DBRef points to the right collection/ID and that the resolver loads `Customer`. There is no server-side foreign-key constraint and no automatic cascade save. For reference lists, pointing to one collection vs. multiple collections affects resolver behavior and query counts.

## 8. Indexes and Validation with Null/Missing Fields

### 8.1. Unique Indexes Can Fail on Null/Missing

A **single-field** unique index in MongoDB treats both missing and explicit null as a null index key. Consequently, multiple documents lacking an email can fail with duplicate key errors under `{ email: 1 }` with `unique: true`.

If the rule only requires non-duplicate string emails, use a **partial unique index**:

```javascript
db.profiles.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: { email: { $type: "string" } }
  }
)
```

Tests must verify three cases: multiple documents missing `email` are accepted, multiple documents with `email: null` are accepted (outside the partial filter), and two identical string emails are rejected. Note that `partialFilterExpression: { email: { $exists: true } }` **still includes explicit null**, so it is not equivalent to a string-only filter.

If uniqueness is scoped per tenant or case-insensitive, design compound indexes/collations and normalization accordingly. `@Indexed(unique = true)` only declares metadata; the index must actually be created in the test environment, as Spring Data MongoDB disables auto index creation by default.

### 8.2. Indexing Nested Paths and Schema Validation

MongoDB can index `contact.postal_code` and use that index for matching queries. Distinguish the Java property path (`contact.postalCode`) from the actual BSON field name when inspecting `getIndexes()` and `explain`. For arrays of embedded documents, indexes become multikey and require careful `$elemMatch` testing.

Entity annotations like `@Field` do not enforce key presence across legacy documents. When business logic requires mandatory fields or strict BSON types, configure MongoDB `$jsonSchema` validation or a dedicated migration, then test both accepted and rejected writes.

## 9. Recommended Test Matrix

| Category | Fixtures to include | Key assertions |
| --- | --- | --- |
| Scalar | missing, null, `""`, a normal value | `containsKey`, `isNull`/`isNullValue`, `exists` |
| POJO write/read | Null and non-null Java properties | `Field.Write`, raw BSON, and round-trip |
| Update | `set(null)`, `unset` | Key presence/absence on server |
| Nested object | missing parent, null parent, `{}`, null child, populated child | BSON paths, nested queries |
| Embedded list | missing, null, `[]`, multi-element list | Mapping, `$elemMatch` |
| Document reference | Existing target, unsaved target, deleted target | Raw pointer, resolution, no cascade |
| DBRef | Existing target, dangling, lazy | DBRef structure, resolution timing |
| Indexes | Null/missing, duplicate values, nested | Unique/partial indexes and query plans |

Unit tests with mocked repositories help verify business logic, yet **do not verify BSON semantics or reference resolution**. Those behaviors should be tested against real MongoDB via `@DataMongoTest` in a repeatable environment. Sharing an application context does not mean database changes roll back automatically: clean up owned collections between tests and avoid databases outside the test environment.

## 10. Common Errors and How to Investigate

| Symptom | Likely cause | How to check |
| --- | --- | --- |
| `isNull()` returns too many rows | Query matches missing fields too | Use `isNullValue()` when explicit null is needed |
| POJO has null yet BSON has no key | Converter skips nulls by default | Read raw document; consider `Write.ALWAYS` |
| After `$unset`, POJO still shows null | Java does not track missing-field state | Assert `containsKey` or `exists(false)` |
| Nested query matches nothing | Mismatch between Java property and `@Field` BSON name | Compare raw field paths |
| Array query gives false positives | Different predicates satisfied by different elements | Use `$elemMatch` when one element must match all predicates |
| Saving parent does not save new customer | References do not cascade automatically | Insert target separately and verify target collection |
| Reference fails when reading | Wrong ID, deleted target, faulty custom lookup | Inspect raw pointer and target document |
| Lazy reference fails only after getter | Resolution happens lazily | Intentionally access the property in tests |
| Unique index errors when email is missing | Missing/null both index as null keys | Design a partial index matching the business rule |

## 11. Practice Exercises

1. Insert five documents with `nickname` as: missing, null, empty string, `"Lan"`, and `"Bình"`. Write tests counting results for `isNull()`, `isNullValue()`, and `exists(false)`.
2. Save a `Profile` with `contact`, then refactor `contact` from an embedded object to a separate entity using `@DocumentReference`. Compare raw BSON before and after, and discuss migration requirements.
3. Create a `List<Contact>` with two elements where valid phone and postalCode sit on **two different elements**. Write an `$elemMatch` query and prove its result differs from separate dotted-path predicates.
4. Create a unique partial index on `email`. Test missing, explicit null, and duplicate strings; verify duplicate key errors occur only per the chosen rule.

## 12. Key Takeaways

- **BSON Null and missing are different**: `isNull()` matches both, `isNullValue()` matches explicit null only, and `exists(false)` matches missing only.
- **Java mapping can mask the difference**: use raw `Document.containsKey` to confirm actual field presence.
- **Embedded vs. referenced differ**: embedded lives in the same document; `@DBRef` and `@DocumentReference` store pointers without auto-cascading.
- **Test reads, writes, updates, indexes, and legacy data** on real MongoDB to expose bugs that mocks or Java getters conceal.

## References

- [MongoDB — Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/): null equality, BSON type null, and missing fields.
- [MongoDB — `$exists`](https://www.mongodb.com/docs/manual/reference/operator/query/exists/): checking field existence, including null values.
- [Spring Data MongoDB — `Criteria` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/Criteria.html): `isNull`, `isNullValue`, `exists`.
- [Spring Data MongoDB — `@Field` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/Field.html): `Field.Write.NON_NULL` and `ALWAYS`.
- [Spring Data MongoDB — Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): object mapping, embedded documents, and collections.
- [Spring Data MongoDB — Document References](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/document-references.html): `@DBRef`, `@DocumentReference`, and lazy loading.
- [MongoDB — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/): uniqueness with null/missing values.
- [MongoDB — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/): partial unique indexes.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): connecting to test databases.
