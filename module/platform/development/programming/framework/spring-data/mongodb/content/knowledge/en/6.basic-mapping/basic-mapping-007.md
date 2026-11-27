# Distinguishing Spring Data MongoDB Metadata from JPA Annotations

When moving from Spring Data JPA to **Spring Data MongoDB**, many Java classes look quite similar: both have an `id` property, an annotation marking the entity, fields renamed on save, and repositories for querying. However, the two technologies use **different data models and mappers**. JPA annotations describe tables, columns, relationships, and entity lifecycles in a relational database; Spring Data MongoDB metadata describes **collections, BSON documents, nested fields, and document references**.

If you only swap `JpaRepository` for `MongoRepository` while keeping `@Entity`, `@Table`, `@Column`, or `@ManyToOne`, the application may store data in an unintended structure, use the wrong `_id` type, lose indexes, or overwrite fields. This lesson helps you read metadata accurately, pick the right annotations, and inspect actual BSON when using `MongoTemplate` or repositories.

After this lesson, you will be able to:

- Distinguish annotations in `org.springframework.data.*` from `jakarta.persistence.*` (or `javax.persistence.*` in older JPA projects).
- Map classes, `_id`, BSON fields, nested objects, references, indexes, and versions in Spring Data MongoDB.
- Understand why JPA concepts like `@GeneratedValue`, `@JoinColumn`, `@OneToMany`, and dirty checking do not apply equivalently to MongoDB.
- Configure auditing, converters, storage types, and transactions when needed.
- Inspect documents with `mongosh` to verify that metadata actually took effect.

## 1. Two Metadata Systems Solving Two Data Models

With **JPA**, an entity typically corresponds to a relational table. Annotations such as `@Entity`, `@Table`, `@Column`, `@ManyToOne`, and `@JoinColumn` instruct the JPA provider (e.g., Hibernate) to map objects into rows, columns, and inter-table relationships. JPA also maintains a *persistence context* and change tracking (*dirty checking*) for managed entities.

With **Spring Data MongoDB**, `MappingMongoConverter` converts Java objects to BSON and back. The target is usually a document in a collection; child objects can be stored **embedded** inside the document, or as references to documents in another collection. The main annotations reside in `org.springframework.data.annotation` and `org.springframework.data.mongodb.core.mapping`.

| Aspect | Spring Data JPA | Spring Data MongoDB |
| --- | --- | --- |
| Storage unit | Row in a table | BSON document in a collection |
| Storage type declaration | `@Entity`, optional `@Table` | `@Document(collection = "...")` |
| Identifier key | `jakarta.persistence.Id`; can use `@GeneratedValue` | `org.springframework.data.annotation.Id` or `@MongoId` mapped to `_id` |
| Renaming stored property | `@Column(name = "...")` | `@Field("...")` |
| Relationships | `@ManyToOne`, `@OneToMany`, `@JoinColumn`, SQL joins/FKs | Embedded objects; `@DBRef` or `@DocumentReference`; or manual ID storage |
| Indexes | `@Table(indexes = ...)`, RDBMS DDL/migrations | `@Indexed`, `@CompoundIndex`, index creation in MongoDB |
| Version | `jakarta.persistence.Version` | `org.springframework.data.annotation.Version` |
| Change tracking | Managed entities have dirty checking in persistence context | Loaded objects are not auto-saved when properties change; explicit `save`/update is required |
| Querying | JPQL, SQL, Criteria API | JSON/BSON queries, `Criteria`, `Query`, aggregation pipelines |
| Transactions | Usually tied to an RDBMS/JPA transaction manager | Requires configuring a MongoDB transaction manager and supporting MongoDB topology for multi-document transactions |

**Note:** identical annotation names do not make them equivalent. For example, `jakarta.persistence.Id` and `org.springframework.data.annotation.Id` are two annotations from different packages; check exact `import` statements in code. There is no automatic, complete conversion step from JPA metadata to MongoDB metadata.

## 2. How Does `@Document` Differ from `@Entity` and `@Table`?

### 2.1. A Typical JPA Entity

Here is a class for JPA, illustrating the `catalog_items` table:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "catalog_items")
public class CatalogItemJpa {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @Version
    private Long version;
}
```

`@Entity` marks a JPA-managed entity, `@Table` specifies the table name, and `@Column` specifies the column name. `@GeneratedValue(strategy = IDENTITY)` requires a key-generation mechanism suited to the RDBMS and JPA provider. You cannot carry these annotations verbatim into a MongoDB class and expect them to have the same meaning.

### 2.2. Corresponding MongoDB Document

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document(collection = "catalog_items")
public class CatalogItem {
    @Id
    private ObjectId id;

    private String sku;

    @Field("display_name")
    private String displayName;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal price;

    @Version
    private Long version;

    private List<Variant> variants = new ArrayList<>();

    protected CatalogItem() { } // For data mapping

    public CatalogItem(String sku, String displayName, BigDecimal price) {
        this.sku = sku;
        this.displayName = displayName;
        this.price = price;
    }

    public ObjectId getId() { return id; }
    public String getSku() { return sku; }
    public String getDisplayName() { return displayName; }

    public static class Variant {
        private String color;
        private int stock;

        protected Variant() { }

        public Variant(String color, int stock) {
            this.color = color;
            this.stock = stock;
        }
    }
}
```

When saved with Spring Data MongoDB, the corresponding BSON structure might be:

```javascript
{
  _id: ObjectId("665f1f2a4b6c7d8e9f001234"),
  sku: "PEN-101",
  display_name: "Blue ballpoint pen",
  price: NumberDecimal("12500.00"),
  version: NumberLong(0),
  variants: [
    { color: "blue", stock: 25 },
    { color: "black", stock: 10 }
  ],
  _class: "com.example.catalog.CatalogItem"
}
```

This is an **illustration**: `_id` values and class names depend on the application; `_class` usually appears under default mapping settings, though it can be altered via type aliases or converter configuration. The BSON types of numbers and version also depend on metadata and how data is generated. The key takeaway is that `displayName` became `display_name`, `id` became `_id`, and `variants` became an **array of embedded documents**, requiring no secondary table.

`@Document` lets you specify the collection and carry MongoDB metadata. In some cases Spring Data MongoDB still maps classes without `@Document` by convention, but declaring it explicitly helps clarify structure, avoids unintended collection names, and aids index/metadata management.

## 3. Renaming Fields: `@Field` Differs from `@Column`

Renaming a Java property when storing in BSON:

```java
import org.springframework.data.mongodb.core.mapping.Field;

@Field("display_name")
private String displayName;
```

In the MongoDB document, the field name is `display_name`. When writing queries via `MongoTemplate` with an **entity type**, you normally use the Java property path so Spring Data maps it:

```java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("displayName").is("Blue ballpoint pen")
);
CatalogItem item = mongoTemplate.findOne(
    query, CatalogItem.class
);
```

Because the query carries `CatalogItem.class`, mapping translates `displayName` to `display_name` at the MongoDB layer. However, when using `mongosh` or the MongoDB Java Driver directly, you must write the **actual BSON name**:

```javascript
db.catalog_items.findOne({ display_name: "Blue ballpoint pen" });
```

For nested fields, continue using dot notation matching the stored structure, e.g., `"variants.color"`. If you change `@Field` metadata while having hand-written JSON queries, pipelines, or other scripts, verify they still access the right field.

**Difference in constraints:** JPA's `@Column(nullable = false, length = 80, unique = true)` can relate to DDL and RDBMS constraints. MongoDB's `@Field` primarily describes **storage name/type**, without turning JPA-style nullable/length/unique options into validation rules. To enforce constraints at the database level, design **MongoDB JSON Schema validation**, unique indexes, or appropriate checks; business validation is also needed at the API layer.

## 4. Identifiers: `@Id`, `@MongoId`, and `@GeneratedValue`

MongoDB requires every stored document to have a unique `_id` within the collection. Default identifiers are commonly generated as BSON `ObjectId`, though `_id` can use any valid BSON type (except arrays) by design. Common mapping options:

| Java declaration | Meaning in Spring Data MongoDB |
| --- | --- |
| `@Id ObjectId id` | Maps to BSON `_id` as ObjectId, convenient for technical IDs |
| `@Id String id` | Converts valid strings into ObjectId when applicable; verify actual BSON type |
| `@MongoId String id` | Keeps String ID as declared; does not aggressively coerce 24-char hex strings to ObjectId like `@Id String` |
| `@MongoId(FieldType.OBJECT_ID) String id` | Requests conversion strategy to BSON ObjectId when convertible |
| `@Id UUID id` | Requires attention to UUID representation/codec so read and write data stay consistent |

Example keeping a business code like `"SKU-001"` as a string:

```java
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "inventory")
public class InventoryItem {
    @MongoId
    private String id;

    private int available;

    protected InventoryItem() { }

    public InventoryItem(String id, int available) {
        this.id = id;
        this.available = available;
    }
}
```

In the application, assign `id` explicitly when creating `InventoryItem` if using an application-supplied business key. MongoDB example:

```javascript
{
  _id: "SKU-001",
  available: 12
}
```

**Do not use JPA's `@GeneratedValue` for MongoDB.** MongoDB does not have `IDENTITY` key-generation strategies or database sequences in the JPA sense. If using ObjectId, Spring Data/the driver can generate it; if UUID, ULID, or business codes are required, design an explicit ID-generation strategy ensuring uniqueness and consistent storage types.

### 4.1. Two Identical-Looking Strings Can Have Different BSON Types

```javascript
const text = "665f1f2a4b6c7d8e9f001234";

db.ids_demo.insertOne({ _id: ObjectId(text), kind: "objectId" });
db.ids_demo.insertOne({ _id: text, kind: "string" });

db.ids_demo.findOne({ _id: ObjectId(text) }); // Document "objectId"
db.ids_demo.findOne({ _id: text });           // Document "string"
```

Both documents coexist because MongoDB distinguishes BSON ObjectId from BSON String. This is a common conversion bug when Java uses `String id` while a `mongosh` script queries with a different type.

### 4.2. Repositories Use the Matching ID Type

```java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogItemRepository
        extends MongoRepository<CatalogItem, ObjectId> {
}
```

`MongoRepository<CatalogItem, ObjectId>` corresponds to `@Id ObjectId id` in the `CatalogItem` class above. Do not mechanically copy `JpaRepository<Entity, Long>` to MongoDB if `_id` has changed type.

## 5. Embedded Objects and Relationships: No Automatic `@ManyToOne`

In JPA, many-to-one relationships typically use `@ManyToOne` and `@JoinColumn`; one-to-many relationships may use `@OneToMany`, `@JoinTable`, or `@ElementCollection`. The JPA provider decides how to load and write tables and relationships from metadata.

In MongoDB, choose document boundaries based on **data read/written together**, lifecycle, and size:

### 5.1. Embedding Nested Objects Directly

```java
@Document(collection = "orders")
public class Order {
    @Id
    private ObjectId id;

    private List<OrderLine> lines;
    private ShippingAddress shippingAddressSnapshot;
}

public class OrderLine {
    private String sku;
    private int quantity;
    private long unitPriceMinor;
}

public class ShippingAddress {
    private String city;
    private String street;
}
```

This is a **structural outline** (running it requires appropriate imports, constructors, and getters). Spring Data MongoDB can map `OrderLine` and `ShippingAddress` into subdocuments right inside `orders` **without** JPA's `@Embeddable` / `@Embedded`. Every single-document update in MongoDB executes atomically, including nested fields within that document.

```javascript
{
  _id: ObjectId("665f1f2a4b6c7d8e9f001234"),
  lines: [{ sku: "BK-101", quantity: 2, unitPriceMinor: 129000 }],
  shippingAddressSnapshot: { city: "Hanoi", street: "Sample Street" }
}
```

Do not embed unbounded arrays: a single BSON document has a **16 MiB** limit. For comments, event histories, or records with independent lifecycles, consider a separate collection and ID references.

### 5.2. Application-Managed ID References

For example, storing `customerId` on `Order`:

```java
@Document(collection = "orders")
public class Order {
    @Id
    private ObjectId id;

    private ObjectId customerId;
    private List<OrderLine> lines;
}
```

MongoDB does not automatically create a foreign key from `customerId` to the `customers` collection. The application can call the Customer repository or use an aggregation with `$lookup` when needed. This is often a simple and transparent way to link independent aggregates.

### 5.3. `@DBRef` and `@DocumentReference`

Spring Data MongoDB also supports reference metadata:

```java
import org.springframework.data.mongodb.core.mapping.DocumentReference;

@DocumentReference
private Customer customer;
```

In common default usage, `@DocumentReference` stores the target document's ID and uses mapping metadata to resolve the entity. `@DBRef` uses the BSON DBRef structure; the two mechanisms differ in **stored data format** and resolution behavior. Neither creates relational foreign keys, nor do they perform JPA-style cascade insert/update/delete by default.

If choosing lazy references, account for queries issued upon property access, proxy configuration, and access outside active processing contexts. For data frequently read alongside an aggregate, embedding or storing a snapshot may make more sense. Do not treat `@DocumentReference` as a drop-in recreation of Hibernate's `@ManyToOne`.

### 5.4. JPA Annotations That Should Not Be Carried Over Verbatim to MongoDB

| JPA Annotation | Why Redesigning for MongoDB Is Needed |
| --- | --- |
| `@ManyToOne` / `@OneToMany` | Does not generate JPA joins/cascades; choose embedding, ID references, `@DBRef`, or `@DocumentReference` |
| `@JoinColumn` / `@JoinTable` | Does not create foreign key columns or join tables; design BSON fields and indexes for queries |
| `@Embedded` / `@Embeddable` | MongoDB maps ordinary objects into nested documents by mapping rules; no need for those two JPA annotations |
| `@ElementCollection` | Arrays/lists of values are typically stored directly as BSON arrays if the design fits |
| `@Enumerated` | Choose Spring Data enum representation and conversion; do not rely on JPA metadata |
| `@Lob` | Choose Binary, String, or GridFS storage by need; no direct JPA LOB mapping equivalent |

## 6. Indexes: `@Indexed`, `@CompoundIndex` Differ from JPA DDL

JPA can declare indexes inside `@Table(indexes = ...)`, with the JPA provider or migrations managing relational DDL. With MongoDB, use Spring Data mapping annotations or manage indexes via migrations/scripts:

```java
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "catalog_items")
@CompoundIndex(
    name = "uniq_tenant_sku",
    def = "{ 'tenantId': 1, 'sku': 1 }",
    unique = true
)
public class CatalogItem {
    @Id
    private ObjectId id;
    private String tenantId;
    private String sku;

    @Indexed
    private String category;
}
```

This is an **independent index metadata example**, separate from the `CatalogItem` class in section 2; do not create two classes with the same name in the same project. The compound index allows the same `sku` across different tenants while preventing duplicate `(tenantId, sku)` *when the unique index actually exists and is enforced*.

**Important difference:** an index annotation **does not mean** the index exists in the database. In modern Spring Data MongoDB versions, automatic index creation is usually **disabled by default**; if you want to use it, enable the corresponding setting, or explicitly create/manage indexes via migrations and `IndexOperations`. In production, controlled index management is generally preferred to avoid unexpected DDL operations at application startup.

Check actual indexes:

```javascript
db.catalog_items.getIndexes();
db.catalog_items.find({
  tenantId: "vn",
  sku: "PEN-101"
}).explain("executionStats");
```

With `explain`, examine `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, and documents returned to evaluate the query. A unique index guarantees uniqueness per the index definition; it **does not automatically verify** cross-collection relationships or every business rule.

## 7. Version and Auditing: Similar Purpose, Different Metadata

### 7.1. Optimistic Locking with Spring Data `@Version`

```java
import org.springframework.data.annotation.Version;

@Version
private Long version;
```

When saving an entity with `@Version` through Spring Data MongoDB's version-aware `save` mechanism, the version is checked and incremented appropriately. If two requests read the same old version and then save, the later request can receive `OptimisticLockingFailureException` instead of silently overwriting. An **acknowledged write concern** is needed to detect update failures reliably.

JPA also has `@Version`, but it is **`jakarta.persistence.Version`** and tied to the JPA provider's persistence context/SQL updates. With MongoDB, import `org.springframework.data.annotation.Version`.

**Do not assume every custom update checks the version.** If a `MongoTemplate` update filters only by `_id` or a `mongosh` script writes directly, include the version condition in the query when needed and check the result. Some Spring Data APIs may increment the version automatically on update, but auto-incrementing **is not the same** as matching the version held by the client.

Conditional version-check example:

```java
Query query = Query.query(
    Criteria.where("_id").is(itemId)
        .and("version").is(expectedVersion)
);
Update update = new Update()
    .set("displayName", "New blue ballpoint pen")
    .inc("version", 1);

long changed = mongoTemplate
    .updateFirst(query, update, CatalogItem.class)
    .getModifiedCount();

if (changed == 0) {
    throw new IllegalStateException(
        "Document does not exist or version has changed"
    );
}
```

This is a *compare-and-set* pattern for one document; the example assumes `itemId` and `expectedVersion` were already obtained from existing data. When implementing custom version-increment logic, ensure no two write paths apply conflicting versioning policies.

### 7.2. Auditing with `@CreatedDate` and `@LastModifiedDate`

Spring Data supports storing creation/modification timestamps via auditing metadata:

```java
import java.time.Instant;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;

@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant updatedAt;
```

Configuration for the synchronous stack:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.config.EnableMongoAuditing;

@Configuration
@EnableMongoAuditing
public class MongoAuditingConfig {
}
```

`@CreatedDate`/`@LastModifiedDate` metadata only takes effect when auditing is enabled and writes pass through supported mechanisms. `mongosh` scripts or direct driver commands do not trigger Spring Data auditing. On the reactive stack, use the corresponding reactive auditing setup (such as `@EnableReactiveMongoAuditing`) and reactive repositories/templates.

JPA typically uses `@PrePersist`/`@PreUpdate` or library-specific auditing for similar work. JPA lifecycle callbacks are not Spring Data MongoDB callbacks; if you need hooks during conversion/saving, look into specialized `EntityCallback`s such as `BeforeConvertCallback`, `BeforeSaveCallback`, or `AfterSaveCallback`.

## 8. `@Transient`, Type Aliases, Constructors, and Converters

### 8.1. Fields Used Only for Computation

Mark a property not to be stored in BSON:

```java
import org.springframework.data.annotation.Transient;

@Transient
private String displayLabel;
```

This is `org.springframework.data.annotation.Transient`. JPA has `jakarta.persistence.Transient` with the same name; when working with MongoDB, use Spring Data metadata to express intent explicitly. If an unpersisted field is still needed when constructing an object, consider the constructor and what data can actually be restored from the database.

### 8.2. Distinguishing `_class` from JPA Inheritance Tables

Spring Data MongoDB often writes type metadata such as `_class` to restore polymorphic types. You can use:

```java
import org.springframework.data.annotation.TypeAlias;

@TypeAlias("catalogItem")
@Document(collection = "catalog_items")
public class CatalogItem {
    // Document properties
}
```

This is an independent metadata example, not a second class of the same name in the project. `@TypeAlias` shortens the type discriminator value under suitable mapping configurations; when reading data containing only the alias, ensure the mapping context knows that entity type. This mechanism differs from JPA's `@Inheritance` and `@DiscriminatorColumn`.

### 8.3. Constructors and BSON Type Conversions

When Spring Data reconstructs objects from documents, it follows Spring Data's constructor-selection and property-population rules. For immutable types or multiple constructors, use `org.springframework.data.annotation.PersistenceCreator` to clarify object creation.

For complex conversions, use `MongoCustomConversions` together with Spring `Converter`, `@ReadingConverter`, or `@WritingConverter` as needed. Do not copy `jakarta.persistence.Convert` and JPA's `AttributeConverter` expecting MongoDB to process them like Hibernate.

Example choosing decimal storage:

```java
import java.math.BigDecimal;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Field(targetType = FieldType.DECIMAL128)
private BigDecimal price;
```

When querying/writing prices, pick a clear monetary model, such as minor-unit integers or BSON Decimal128 per business precision needs. Do not assume JPA's `@Column(precision = ..., scale = ...)` configures BSON Decimal128.

## 9. Queries and Lifecycle: `JpaRepository` Differs from `MongoRepository`

Similar method names like `save`, `findById`, and `deleteById` can make both repositories appear to behave identically. In practice:

- JPA has a persistence context; mutating a managed entity inside a transaction can be flushed via dirty checking.
- A MongoDB repository reads objects from BSON; **mutating Java properties does not auto-persist**. You must call `save` or an explicit update API.
- `save` in MongoDB can insert a new document or replace an existing one depending on ID/version state; when intending to update a single field, consider `MongoTemplate.updateFirst` with an appropriate filter.
- MongoDB does not enable multi-document transactions automatically like JPA. If a workflow needs atomic multi-document commits, configure `MongoTransactionManager` and use a supporting MongoDB deployment (typically a replica set or sharded cluster).
- Spring Data JPA's `@Query` normally contains JPQL/SQL; Spring Data MongoDB's `@Query` uses MongoDB JSON query strings. Keeping a JPA query string will not produce an equivalent MongoDB query.

### 9.1. Derived Queries and `MongoTemplate`

```java
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogItemRepository
        extends MongoRepository<CatalogItem, ObjectId> {
    List<CatalogItem> findByDisplayName(String displayName);
}
```

Method names are still written using the **Java property** `displayName`, while the BSON field can be `display_name` via `@Field`. With `MongoTemplate`:

```java
Query query = Query.query(
    Criteria.where("displayName").is("Blue ballpoint pen")
);
List<CatalogItem> items =
    mongoTemplate.find(query, CatalogItem.class);
```

When translating to `mongosh`, the field name to use is `display_name`. For complex queries, Spring Data MongoDB supports `Criteria`, aggregation pipelines, indexes, projections, and reactive access; it is a document-database API, not a wrapper over JPQL.

### 9.2. Multi-Document Transaction Example

If an operation must modify two documents in MongoDB atomically, use Spring transaction management with `MongoTransactionManager`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
class MongoTransactionConfig {
    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
```

This example only introduces the infrastructure; business methods need `@Transactional`, must be invoked through a Spring proxy, and must use MongoDB operations participating in the same session/transaction. Single-document operations are already atomic; multi-document transactions should be considered when invariants genuinely span multiple documents.

## 10. Checklist for Migrating from a JPA Entity

Suppose you receive an existing entity and need to adapt it for Spring Data MongoDB. Check in order:

1. **Imports:** are `jakarta.persistence.*` or `javax.persistence.*` still used to describe mapping? Choose Spring Data MongoDB annotations matching the BSON design.
2. **Collection:** is `@Document` declared with an appropriate collection name? Is a class without `@Document` relying on an unintended naming convention?
3. **ID:** have you decided on the `_id` BSON type, ID generation strategy, and repository generic type? Check `@Id String` with hex strings or pick `@MongoId` when pinning the type.
4. **Field naming:** has `@Column(name)` been replaced with `@Field` where needed? Do queries, indexes, and raw MongoDB scripts use the right BSON names?
5. **Relationships:** have `@ManyToOne`/`@OneToMany` been redesigned as nested documents or references? Have you identified which data must be updated together?
6. **Indexes/constraints:** do unique indexes actually exist? Are validators protecting types, lengths, or business values?
7. **Version/auditing:** are you importing Spring Data's `@Version`, `@CreatedDate`, and `@LastModifiedDate`? Is auditing configured?
8. **Converters/enums:** do special types have consistent BSON representations (UUID, BigDecimal, Instant, enum, binary)?
9. **Writes and transactions:** is code relying on JPA dirty checking/cascading/transactions? Do MongoDB write paths protect invariants and concurrent conflicts?
10. **Verification on real data:** after trial insert/read/update operations, does BSON have the expected `_id`, field names, field types, nested structures, and indexes?

### Inspecting with `mongosh`

On a test database, inspect the document actually written by the application:

```javascript
use spring_data_training

db.catalog_items.findOne(
  { sku: "PEN-101" },
  {
    _id: 1,
    sku: 1,
    display_name: 1,
    price: 1,
    version: 1,
    variants: 1,
    _class: 1
  }
);

db.catalog_items.getIndexes();
```

In MongoDB Compass, open the collection and check the **BSON types** of `_id`, `price`, and the `variants` structure. If you see `displayName` in BSON instead of `display_name`, re-check the `@Field` import, the entity class being saved, and the actual write path (Spring Data MongoDB vs. direct driver).

To inspect BSON types via aggregation:

```javascript
db.catalog_items.aggregate([
  { $match: { sku: "PEN-101" } },
  {
    $project: {
      _id: 0,
      idType: { $type: "$_id" },
      priceType: { $type: "$price" },
      hasVariants: { $isArray: "$variants" }
    }
  }
]);
```

This is a read query; it modifies no data. Empty results may simply mean no document with the sample SKU exists yet. Replace the filter with an actual SKU present in your test database.

## 11. Common Errors and How to Find the Root Cause

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| Entity saves to wrong collection name | Forgot `@Document(collection = ...)` or wrote via another path | Check annotations, repository/template domain class, database, and actual collection |
| BSON has `displayName` instead of `display_name` | Still using JPA `@Column` or wrong `@Field` import | Use `org.springframework.data.mongodb.core.mapping.Field`, re-read BSON |
| Lookup by valid ID returns nothing | Java/BSON ID mismatch between String and ObjectId | Inspect `_id` in `mongosh` and `@Id`/`@MongoId` metadata |
| Expecting `@GeneratedValue` to auto-generate keys like RDBMS | JPA annotation does not control ObjectId generation | Choose ObjectId or a dedicated application ID strategy |
| `@ManyToOne` relationship does not auto-load | MongoDB lacks equivalent JPA relationship mapping | Design ID references, `@DocumentReference`/`@DBRef`, or embed |
| Marked `@Indexed(unique=true)` yet duplicates still exist | Index wasn't created or has different scope/filter | Check `getIndexes()`, migration plan, and index build errors |
| Java object mutated but MongoDB unchanged | Expecting JPA dirty checking | Call `repository.save` or a conditional update |
| Two requests overwrite each other | Missing version check or overly broad update query | Use `@Version`, compare-and-set, check `modifiedCount` |
| `@CreatedDate` stays null | Auditing not enabled or write bypassed Spring Data | Enable appropriate `@EnableMongoAuditing`, verify write path |
| Saved `BigDecimal` has unexpected BSON type | Storage type not specified or converter/driver configured differently | Use `@Field(targetType = FieldType.DECIMAL128)` and inspect `$type` |

## 12. Practice Exercises

**Exercise 1 — Fix imports.** Given a JPA class with `@Entity`, `@Table(name = "products")`, `@Id Long id`, `@GeneratedValue`, `@Column(name = "display_name")`, and `@Version`. Rewrite it as a MongoDB document using `ObjectId` and `@Field`, and declare the repository with the proper generic types. Explain each change.

**Exercise 2 — Verify String/ObjectId.** Create two documents whose `_id` values share the same 24-character hex string but have different BSON types. Write two `mongosh` queries to locate each document accurately. Explain the behavior when an entity uses `@Id String` versus `@MongoId String`.

**Exercise 3 — Embed or reference?** Design an `Order` with `OrderLine[]`, `customerId`, and `shippingAddressSnapshot`. Explain why order lines and the frozen shipping address can be embedded, whereas `Customer` usually has an independent lifecycle. Write an example BSON document.

**Exercise 4 — Real index or metadata only?** Declare a unique compound index for `tenantId` + `sku` on the product document; write the `getIndexes()` check command and describe how to verify duplicate data is rejected. Explain why you should not rely on the annotation alone in production.

**Exercise 5 — Concurrent writes.** Two requests simultaneously read version `2` of a `CatalogItem` and change the product name to different values. Explain the outcome when using repository `save` with Spring Data `@Version`, versus the risk of using `MongoTemplate.updateFirst` filtering only by `_id`.

**Exercise 6 — Auditing and converters.** Add `createdAt`, `updatedAt`, and `price` as BSON Decimal128. Configure auditing, save a sample document via repository, and use `mongosh` to verify timestamps and the `$type` of `price`.

### Takeaways

**Spring Data MongoDB** metadata describes how Java objects map to **BSON documents**; **JPA** annotations describe entities in a relational model with distinct mechanisms like foreign keys, a persistence context, and dirty checking. Same-named annotations such as `@Id` or `@Version` must be imported from the proper package. In MongoDB, deliberately design `_id`, BSON fields, embedded/referenced data, indexes, auditing, and update paths; always verify actual documents and indexes using `mongosh` or Compass.
