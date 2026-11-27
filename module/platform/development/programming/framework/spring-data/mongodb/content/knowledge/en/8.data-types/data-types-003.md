# BigDecimal, Decimal128, and Explicit Storage Type Declarations

## 1. Lesson Objectives

In **Spring Data MongoDB**, Java objects are mapped to BSON documents and back via the mapping/conversion mechanism. For data such as **product prices, unit prices, discounts, tax amounts, and order totals**, choosing the wrong storage type can introduce rounding errors, incorrect comparisons, or hard-to-verify aggregation reports.

This lesson belongs to the **Data Types** chapter and continues using the **Mini Commerce** model, consisting of three collections: `products`, `customers`, and `orders`. We will use `BigDecimal` in Java, store it as BSON `Decimal128`, and inspect actual data in MongoDB. This knowledge supports upcoming sections on `MongoTemplate`, repositories, queries, aggregations, indexes, transactions, reactive access, testing, and performance diagnostics.

Upon completion, learners will be able to:

- Explain the differences among Java `BigDecimal`, BSON `Decimal128`, BSON `Double`, and BSON `String`.
- Declare `@Field(targetType = FieldType.DECIMAL128)` for monetary fields requiring explicit storage.
- Recognize changes in **default BigDecimal representation between Spring Data MongoDB 4.x and 5.x**.
- Store, read, filter, update, and aggregate Decimal128 fields via repositories or `MongoTemplate`.
- Verify actual BSON types using `$type`, `mongosh`, and integration tests.
- Design precision, scale, and rounding rules as well as a migration plan for data currently stored as strings.

**Prerequisites:** Basic Java, Spring Boot with `spring-boot-starter-data-mongodb`, a running MongoDB instance, and understanding of `@Document`, `@Id`, repositories, and `MongoTemplate`. Examples assume Java 17+ and a MongoDB version supporting Decimal128. You do not need to run transactions just to practice mapping a monetary field.

## 2. Why Shouldn't Currency Use `double`?

Java `double` uses IEEE 754 binary floating-point. Many decimal fractions such as `0.1` do not have an exact finite representation in binary. Therefore:

```java
System.out.println(0.1 + 0.2); // 0.30000000000000004
```

This may not matter in graphics or measurement calculations with acceptable tolerances, but for **money, taxes, or balance splits**, an exact and controlled rounding policy is required.

Java `BigDecimal` represents decimal values using an unscaled integer and a scale, making it suitable for exact decimal arithmetic within representable bounds. However, **BigDecimal is a Java type**, not a MongoDB BSON type name. When persisting, you must decide on the target BSON type.

| Type | Where It Lives | Characteristics | Risks / Usage Rules |
| --- | --- | --- | --- |
| `BigDecimal` | Java | Arbitrary decimal precision within Java limits, with `precision` and `scale` | Must choose rounding rules and a BSON storage type |
| `Decimal128` | MongoDB BSON / Java Driver (`org.bson.types.Decimal128`) | 128-bit decimal floating-point, up to **34 significant digits** | Cannot represent every BigDecimal value; must check bounds |
| `Double` | BSON | 64-bit binary floating-point | Do not use as the source of truth for exact monetary calculations |
| `String` | BSON | Character string, e.g., `"129900.00"` | Filtering, sorting, and comparisons usually have **lexicographical semantics**, not numeric |
| `Int64` or `Long` | BSON/Java | 64-bit integer | Can be used to store minor units if the value domain and unit are clearly defined |

**Example of storing minor units:** if system policy dictates all amounts are always counted in 100 VND units or cents, you can store integer `long` paired with an explicit unit. This lesson chooses `BigDecimal + Decimal128` because decimal values and direct MongoDB aggregations are needed.

## 3. BigDecimal, Precision, and Scale

Two commonly confused Java concepts:

- **Precision**: the total number of significant digits in the decimal coefficient.
- **Scale**: the number of digits to the right of the decimal point (can be negative in certain representations).

Example:

```java
BigDecimal value = new BigDecimal("129900.00");

System.out.println(value.precision()); // 8
System.out.println(value.scale());     // 2
```

In Mini Commerce, the example convention uses **2 decimal places** for clarity, whereas real products must set scale based on currency and business rules (for example, zero-decimal currencies, tax rules, or exchange rates).

Do not construct money from a `double` literal:

```java
// Recommended:
BigDecimal safe = new BigDecimal("0.10");
BigDecimal alsoSafe = BigDecimal.valueOf(0.1);

// Avoid: captures the exact binary representation of double.
BigDecimal unsafe = new BigDecimal(0.1);
```

`BigDecimal.valueOf(0.1)` uses the decimal string representation of `double` to build the object, behaving differently from `new BigDecimal(double)`. Still, in production APIs, passing/receiving **exact decimal strings** or validated structures is easier to control than going through `double`.

Enforce scale and rounding policies **before** writing:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

static BigDecimal money(String value) {
    BigDecimal amount = new BigDecimal(value);
    if (amount.signum() < 0) {
        throw new IllegalArgumentException("Amount must not be negative");
    }

    // Do not silently round numbers with more than 2 decimal places.
    return amount.setScale(2, RoundingMode.UNNECESSARY);
}
```

`RoundingMode.UNNECESSARY` throws `ArithmeticException` if rounding is required. If the system has tax/discount calculations that produce additional decimal places, define an explicit rounding step (such as `HALF_UP` or `HALF_EVEN`) per business requirements and apply it consistently.

When comparing values:

```java
BigDecimal a = new BigDecimal("129900.0");
BigDecimal b = new BigDecimal("129900.00");

System.out.println(a.compareTo(b) == 0); // true: same numeric value
System.out.println(a.equals(b));         // false: different scale
```

Price assertions in tests should use `compareTo` or normalize scale before using `equals`, depending on the data contract. Do not assume every arithmetic operation or every client preserves the original scale representation.

## 4. What Is Decimal128 and Where Are Its Limits?

MongoDB stores BSON Decimal128 per the IEEE 754 128-bit decimal floating-point standard. This BSON type supports:

- Up to **34 significant digits**;
- Decimal exponent range approximately **−6143 to +6144**;
- Special Decimal128 values (such as NaN and Infinity) at the driver/BSON level;
- Numeric comparisons and arithmetic in MongoDB with numeric rather than string semantics.

**Core limitation:** `BigDecimal` can represent a number that is too long or has a scale/exponent beyond Decimal128's capabilities. Thus, “using BigDecimal in Java” **does not guarantee every value fits in Decimal128**. Conversion can fail if the value cannot be represented accurately.

Example with MongoDB Java Driver:

```java
import java.math.BigDecimal;
import org.bson.types.Decimal128;

BigDecimal javaValue = new BigDecimal("129900.00");
Decimal128 bsonValue = new Decimal128(javaValue);

System.out.println(bsonValue.toString());           // 129900.00
System.out.println(bsonValue.bigDecimalValue());     // 129900.00
```

`Decimal128.bigDecimalValue()` is intended for finite numeric values convertible to BigDecimal. If reading external data containing NaN/Infinity, handle them separately; they are not valid monetary amounts. In Mini Commerce, validate that monetary values are finite, non-negative (if required by business rules), and within magnitude limits before writing.

### 4.1. Display Format Is Not Storage Type

The same numeric value can be displayed in different forms:

```javascript
// mongosh:
NumberDecimal("129900.00")
```

```json
{
  "price": { "$numberDecimal": "129900.00" }
}
```

- `NumberDecimal("...")` is syntax used in `mongosh`.
- `{"$numberDecimal": "..."}` is **MongoDB Extended JSON** representing the Decimal128 type.
- `"129900.00"` is simply a BSON String when the stored value is an actual string.
- `129900.00` in plain JSON does not indicate which BSON type will be stored; passing through a JSON client can trigger different type conversion rules.

Therefore, do not infer a data type from how a number appears in a UI. Verify using `$type` or fetch raw BSON directly in integration tests.

## 5. Differences Between Spring Data MongoDB 4.x and 5.x

This is the most important detail to watch out for when reading online tutorials:

| Spring Data MongoDB Line | Behavior/Configuration for `BigDecimal` |
| --- | --- |
| **4.x** (e.g., 4.5) | According to this version's documentation, the historical default storage format for `BigDecimal` is **String**, unless a target type or other converter is specified |
| **5.0 and later** | According to the migration guide, configuration infrastructure no longer defaults representations for `BigDecimal`/`BigInteger`; an **explicit representation configuration** is required when persisting these types |
| Both lines | `@Field(targetType = FieldType.DECIMAL128)` expresses the intent to store Decimal128 for **a single property** |

Do not state a blanket rule that “BigDecimal is always automatically Decimal128” or “BigDecimal is always automatically String” for all versions. In a real project, check which Spring Data MongoDB version is managed by your Spring Boot BOM, choose a consistent storage strategy, and confirm the BSON output with tests.

**Two different levels of configuration**:

1. **Property level**: use `@Field(targetType = FieldType.DECIMAL128)` (or `FieldType.STRING` when legacy string compatibility is needed).
2. **Global mapping level**: configure `MongoCustomConversions.BigDecimalRepresentation` for `BigDecimal` fields without annotations or when a shared default policy is desired.

On Spring Data MongoDB 5.x, explicitly define the representation in converter configuration per the migration guide, while still declaring `@Field(targetType = DECIMAL128)` on critical monetary fields so the BSON contract is visible right on the entity.

## 6. Declaring Explicit Storage Types with @Field

### 6.1. Product Example: Storing `price` as Decimal128

The `products` model in Mini Commerce has `price` as the current selling price. Use Java `BigDecimal` combined with the annotation:

```java
package com.example.minicommerce.domain;

import java.math.BigDecimal;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document(collection = "products")
public class Product {
    @Id
    private String id;

    private String sku;
    private String name;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal price;

    private int stock;

    public Product() {}

    public Product(String id, String sku, String name,
                   BigDecimal price, int stock) {
        this.id = id;
        this.sku = sku;
        this.name = name;
        this.price = price;
        this.stock = stock;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public BigDecimal getPrice() { return price; }
    public void setPrice(BigDecimal price) { this.price = price; }

    public int getStock() { return stock; }
    public void setStock(int stock) { this.stock = stock; }
}
```

Explanation:

- `@Document(collection = "products")`: maps the entity to the collection.
- `@Id`: maps the `id` property to `_id`.
- `price`: **Java uses BigDecimal**, expected BSON is **Decimal128** thanks to `@Field(targetType = FieldType.DECIMAL128)`.
- `stock`: integer inventory count; does not need Decimal128.

So the example does not depend on hexadecimal-string-to-ObjectId conversion, we use IDs like `"prod-001"`. If a project uses `ObjectId`, keep ID types and references consistent across collections.

### 6.2. Mapping Field Name and Storage Type Together

If the system convention specifies `unit_price` in BSON while Java uses `unitPrice`:

```java
@Field(name = "unit_price", targetType = FieldType.DECIMAL128)
private BigDecimal unitPrice;
```

`@Field` handles **both the stored name** and the **target type**. This matters when writing queries/updates because Spring Data mapping translates Java property names into their corresponding BSON names.

### 6.3. OrderLine: Freezing Price at Order Creation

`Product.price` may change during promotions. `OrderLine.unitPrice` must preserve the price locked at order placement; `lineTotal` equals `quantity × unitPrice`.

```java
import java.math.BigDecimal;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

public class OrderLine {
    private String productId;
    private String sku;
    private int quantity;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal unitPrice;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal lineTotal;

    // Constructor/getter/setter compatible with the project's mapping.
}
```

In `Order`, `totalAmount` should also be declared explicitly:

```java
@Document(collection = "orders")
public class Order {
    @Id
    private String id;

    private String customerId;
    private List<OrderLine> lines;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal totalAmount;

    // Status, timestamp fields, and constructor/getter/setter.
}
```

This snippet illustrates the core fields; import `List`, `BigDecimal`, `Id`, `Document`, `Field`, `FieldType` and complete the implementation when assembling real source code.

**Business rule:** the server loads `Product.price` from the database, normalizes scale per policy, and computes `lineTotal` and `totalAmount` using BigDecimal. Never trust prices or totals sent by the client. Transactions during order placement can ensure order creation and stock deduction are consistent, but transactions **do not automatically fix rounding errors or wrong numeric types**.

## 7. Configuring Representation at the Converter Level

`@Field(targetType = ...)` expresses the contract per property. With Spring Data MongoDB 5.x, the migration documentation requires configuring a default `BigDecimalRepresentation` when persisting `BigDecimal` values handled by default.

If the application **already extends** `AbstractMongoClientConfiguration`, configure it in that class:

```java
import org.springframework.data.mongodb.config.AbstractMongoClientConfiguration;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions.MongoConverterConfigurationAdapter;

// Place inside the class extending AbstractMongoClientConfiguration:
@Override
protected void configureConverters(
        MongoConverterConfigurationAdapter adapter) {
    adapter.bigDecimal(
        MongoCustomConversions.BigDecimalRepresentation.DECIMAL128);
}
```

Explanation:

- `BigDecimalRepresentation.DECIMAL128`: sets Decimal128 as the default representation in converter configuration.
- You can choose `BigDecimalRepresentation.STRING` to preserve legacy string formatting during compatibility/migration phases, though this involves trade-offs for numeric queries.
- If you want to support multiple formats and specify per field, consult `MongoCustomConversions.create(config -> config.bigDecimal(...))` for your version; the order of registered representations affects the default format.
- Do not add two overlapping `MongoCustomConversions` configurations or change the storage strategy without first evaluating existing data.

**Do not copy that override into an arbitrary `@Configuration` class**: `configureConverters(...)` is an extension point of `AbstractMongoClientConfiguration`. If you rely purely on Spring Boot auto-configuration, register a `MongoCustomConversions` bean according to your version's API or an appropriate customizer/conversion bean, then test the resulting mapping bean. Avoid manually building a second `MongoTemplate` solely to set Decimal128.

### 7.1. Example Global Configuration via MongoCustomConversions

In a Spring Boot application using auto-configuration (not extending the configuration class above), you can define a bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;

@Configuration
public class DecimalMappingConfiguration {
    @Bean
    MongoCustomConversions mongoCustomConversions() {
        return MongoCustomConversions.create(config ->
            config.bigDecimal(
                MongoCustomConversions.BigDecimalRepresentation.DECIMAL128));
    }
}
```

This example targets versions offering the `MongoCustomConversions.create(...)` factory method. If the project already registers other custom conversions (enums, encryption, value objects, etc.), **merge** the configuration using that version's API so important converters are not lost. Verify via integration tests that `MongoTemplate` actually uses the expected converter.

## 8. Verifying Actual BSON When Inserting via MongoTemplate

Declare the repository:

```java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductRepository
        extends MongoRepository<Product, String> {
}
```

Try inserting a product in a test environment:

```java
Product sample = new Product(
    "prod-001",
    "LAP-001",
    "Mini Mechanical Keyboard",
    new BigDecimal("129900.00"),
    20
);

mongoTemplate.insert(sample);
```

In `mongosh`:

```javascript
use mini_commerce

db.products.findOne(
  { _id: "prod-001" },
  { sku: 1, name: 1, price: 1, stock: 1 }
)

db.products.aggregate([
  { $match: { _id: "prod-001" } },
  { $project: { _id: 0, priceType: { $type: "$price" }, price: 1 } }
])
```

With a working configuration, `priceType` must be `"decimal"`. The `price` value may display as `Decimal128("129900.00")` or `NumberDecimal("129900.00")` depending on the tool. Use `$type` to verify accurately.

MongoDB Extended JSON can represent the document as:

```json
{
  "_id": "prod-001",
  "sku": "LAP-001",
  "name": "Mini Mechanical Keyboard",
  "price": { "$numberDecimal": "129900.00" },
  "stock": 20
}
```

When inspecting raw BSON with the MongoDB driver:

```java
import org.bson.Document;
import org.bson.types.Decimal128;

Document stored = mongoTemplate.getCollection("products")
    .find(new Document("_id", "prod-001"))
    .first();

if (stored == null) {
    throw new IllegalStateException("Sample product missing");
}

Object rawPrice = stored.get("price");
if (!(rawPrice instanceof Decimal128 decimal128)) {
    throw new IllegalStateException(
        "Expected BSON Decimal128 but found: " + rawPrice);
}

BigDecimal result = decimal128.bigDecimalValue();
System.out.println(result); // 129900.00
```

This is stronger evidence than just calling `repository.findById(...)`: a repository can **convert on read** from different BSON types, whereas raw BSON reveals the actual persisted type.

## 9. Querying and Updating with Decimal128

### 9.1. Filtering Prices with MongoTemplate

Example finding products priced from `100000.00` up to below `200000.00`:

```java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("price")
        .gte(new BigDecimal("100000.00"))
        .lt(new BigDecimal("200000.00"))
);

List<Product> found = mongoTemplate.find(query, Product.class);
```

When passing `Product.class`, Spring Data uses entity mapping metadata to convert the filter to the appropriate BSON type. Still test against real data, especially when the collection contains **a mix of String and Decimal128** from older versions.

Filtering directly in `mongosh` using Decimal128 values:

```javascript
db.products.find({
  price: {
    $gte: NumberDecimal("100000.00"),
    $lt: NumberDecimal("200000.00")
  }
})
```

**Do not use string** `"100000.00"` as the comparison threshold in raw MongoDB queries against a Decimal128 field. That is a different BSON type and the query may not yield expected results.

### 9.2. Updating Prices with the Right Type

```java
import org.springframework.data.mongodb.core.query.Update;

Query filter = Query.query(
    Criteria.where("_id").is("prod-001"));

Update change = new Update()
    .set("price", new BigDecimal("139900.00"));

mongoTemplate.updateFirst(filter, change, Product.class);
```

For updates via a mapped entity class, Spring Data can apply conversions based on `@Field`. Inspect the raw value after the update to confirm `price` remains `Decimal128`. Do not mix with raw driver writes inserting `double` or `String` into the same field.

In `mongosh`, when editing directly:

```javascript
db.products.updateOne(
  { _id: "prod-001" },
  { $set: { price: NumberDecimal("139900.00") } }
)
```

If updating price and inventory concurrently based on product version, consider optimistic locking or conditional updates. The Decimal128 type does not by itself prevent write conflicts.

### 9.3. Indexes and Sort Order

Example screen filtering active products by category and sorting by price:

```javascript
db.products.createIndex({ active: 1, category: 1, price: 1 })

db.products
  .find({
    active: true,
    category: "accessories",
    price: { $gte: NumberDecimal("100000.00") }
  })
  .sort({ price: 1 })
  .explain("executionStats")
```

Indexes must be evaluated using realistic query shapes. Compare `totalKeysExamined`, `totalDocsExamined`, and `nReturned`, rather than merely checking whether the sort output looks right. If `price` contains both String and Decimal128, index ordering and filtering by **BSON type** can produce unexpected behavior. Standardize data types before optimizing queries.

## 10. Aggregation with Decimal128 in Orders

The `orders` model contains embedded order lines. Suppose:

```json
{
  "_id": "order-001",
  "customerId": "customer-001",
  "status": "PLACED",
  "lines": [
    {
      "productId": "prod-001",
      "sku": "LAP-001",
      "quantity": 2,
      "unitPrice": { "$numberDecimal": "129900.00" },
      "lineTotal": { "$numberDecimal": "259800.00" }
    }
  ],
  "totalAmount": { "$numberDecimal": "259800.00" }
}
```

To aggregate revenue for `PLACED` orders in MongoDB:

```javascript
db.orders.aggregate([
  { $match: { status: "PLACED" } },
  {
    $group: {
      _id: null,
      orderCount: { $sum: 1 },
      revenue: { $sum: "$totalAmount" }
    }
  }
])
```

When all `totalAmount` values are stored as Decimal128, total revenue retains decimal semantics. Avoid computing revenue with `double` in Java or rounding in multiple places. If legacy String data exists, `$sum` will not work as expected on strings and may ignore non-numeric values; normalize before reporting.

Top-selling products report:

```javascript
db.orders.aggregate([
  { $match: { status: "PLACED" } },
  { $unwind: "$lines" },
  {
    $group: {
      _id: "$lines.productId",
      unitsSold: { $sum: "$lines.quantity" },
      revenue: { $sum: "$lines.lineTotal" }
    }
  },
  { $sort: { revenue: -1 } },
  { $limit: 10 }
])
```

With `MongoTemplate`, use `Aggregation.match`, `unwind`, `group`, `sort`, and `limit` correspondingly. When analyzing real financial data, explicitly define how cancelled orders, refunds, currencies, and settled transactions are handled; filtering only by `status = "PLACED"` is a simplified practice rule.

## 11. Legacy Data: Mixed String, Double, and Decimal128

A collection can accumulate multiple representations across upgrade cycles:

```javascript
// Three documents with nearly identical-looking display prices
{ _id: "p1", price: "129900.00" }
{ _id: "p2", price: 129900.0 }              // BSON Double
{ _id: "p3", price: NumberDecimal("129900.00") }
```

Visually, they appear to be the same number. In MongoDB, `price` carries three distinct **BSON types**, affecting comparisons, sorting, aggregation, and conversion.

### 11.1. Profiling BSON Types Before Fixing Data

```javascript
db.products.aggregate([
  {
    $group: {
      _id: { $type: "$price" },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
])
```

Possible results you might see:

| Group `_id` | Meaning |
| --- | --- |
| `"decimal"` | BSON Decimal128 |
| `"string"` | BSON String |
| `"double"` | BSON Double |
| `"missing"` | Document does not have the `price` field |
| `"null"` | Field exists as BSON Null |

Before migrating, determine the count in each group, anomalous values (empty strings, non-numeric characters, out-of-range values), and dependencies of other applications. Do not rush to change a field type if an older service still expects a string.

### 11.2. Checking Which Strings Can Convert to Decimal128

You can use `$convert` with `onError` and `onNull` to **detect malformed data without immediately writing**:

```javascript
db.products.aggregate([
  { $match: { price: { $type: "string" } } },
  {
    $project: {
      price: 1,
      convertedPrice: {
        $convert: {
          input: "$price",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  { $match: { convertedPrice: null } }
])
```

The pipeline returns documents whose strings fail to convert to Decimal128. Some syntactically valid values that exceed Decimal128 limits can still fail conversion. For monetary data, add range and scale checks aligned with business policy.

### 11.3. Safe Migration Process

1. **Inventory** data using `$type` and profile financial fields across `products` and `orders`, including `lines.unitPrice` and `lines.lineTotal`.
2. **Back up or ensure a tested rollback mechanism**. Identify which code reads/writes strings.
3. **Pre-validate**: numeric syntax, precision, scale, value bounds, documents missing fields, and Double data with lost precision.
4. **Test on staging data** with representative volume and distributions; reconcile revenue totals before/after under explicit conversion rules.
5. **Convert in batches** and monitor errors. For example, verified String fields can be converted using an aggregation pipeline update.
6. **Deploy compatible readers/writers** via a staged rollout, then switch all writers to Decimal128; avoid running code versions that write two different types simultaneously.
7. **Verify** `$type`, repositories, price-range queries, indexes, and aggregation reports post-migration. Only remove compatibility logic once data is uniform.

Example conversion operation **after verifying all strings in the target set are valid**, executed only in a controlled environment/batch:

```javascript
db.products.updateMany(
  { price: { $type: "string" } },
  [
    {
      $set: { price: { $toDecimal: "$price" } }
    }
  ]
)
```

**Warning:** `$toDecimal` can fail if a string is invalid or unconvertible. `updateMany` across many documents does not automatically make the entire operation an atomic transaction; you need backups, monitoring, and a batch/retry strategy. Do not run the example directly on production without an inventory and recovery plan.

For source data already stored as Double, original values may have been rounded before writing; converting to Decimal128 **does not recover lost precision**. Such cases require reconciliation against accounting/source-of-truth records rather than automated casting alone.

## 12. Testing Mapping and Financial Data

Tests checking only `product.getPrice().compareTo(expected) == 0` do not prove the **actual BSON** is Decimal128. Have at least one integration test against a real MongoDB instance or Testcontainers:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@SpringBootTest
class ProductDecimalMappingTest {
    @Autowired
    MongoTemplate mongoTemplate;

    @Test
    void storesDecimal128AndReadsBigDecimal() {
        String id = "decimal-mapping-test";
        var raw = mongoTemplate.getCollection("products");

        raw.deleteOne(new Document("_id", id));
        try {
            Product product = new Product(
                id, "DEC-TEST", "Test Product",
                new BigDecimal("129900.00"), 3);

            mongoTemplate.insert(product);

            Document bson = raw.find(new Document("_id", id)).first();
            assertNotNull(bson);
            assertInstanceOf(Decimal128.class, bson.get("price"));
            assertEquals(
                0,
                new BigDecimal("129900.00").compareTo(
                    ((Decimal128) bson.get("price")).bigDecimalValue()));

            Product loaded = mongoTemplate.findById(id, Product.class);
            assertNotNull(loaded);
            assertEquals(
                0,
                new BigDecimal("129900.00").compareTo(loaded.getPrice()));
        } finally {
            raw.deleteOne(new Document("_id", id));
        }
    }
}
```

The test snippet assumes `Product` from section 6 is imported from the right package, the Spring context has a reachable MongoDB, and the test collection is isolated. Only delete fixed-ID fixtures in a **dedicated test database**; do not copy cleanup logic like this into production.

### 12.1. Additional Tests to Include

| Case | What to Verify |
| --- | --- |
| `new BigDecimal("0.10")` | Stored as BSON Decimal128 and read back accurately |
| `new BigDecimal("129900.00")` | Accurate read/write; test scale per contract if needed |
| Input exceeding 2 decimal places | Rejected or rounded according to published policy |
| Number with more than 34 significant digits | Detected and reported as an error, not silently truncated |
| Negative numbers, null, price equal to 0 | Validated per business rules |
| `@Field(targetType = DECIMAL128)` | Actual BSON is Decimal128, not String/Double |
| Price-range query | Returns expected products; filter uses numeric values |
| `MongoTemplate.updateFirst` | BSON type remains Decimal128 after price update |
| `totalAmount` sum aggregation | Total is accurate across valid orders and contains no Strings |
| Legacy data containing String or Double | Explicit migration/compatibility tests exist |
| Concurrent price/stock updates | Appropriate concurrency/transaction mechanism, independent of Decimal128 choice |

If using `ReactiveMongoRepository` or `ReactiveMongoTemplate`, mapping still requires the right target type. Tests can use Reactor `StepVerifier`, yet must still inspect raw BSON in the database. Reactive access does not alter Decimal128 precision and does not automatically fix legacy data types.

## 13. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Price stored as string | Spring Data 4.x uses legacy default or representation is configured as STRING | Declare `@Field(targetType = DECIMAL128)`, review converters, and test BSON |
| Conversion fails after upgrading to 5.x | Appropriate `BigDecimalRepresentation` not registered | Configure representation explicitly per migration guide |
| Filter `price >= 100` misses data | Collection mixes String/Decimal128 or wrong threshold type passed | Profile `$type`, standardize BSON, and use Decimal128 thresholds |
| Aggregation sum is wrong | `$sum` encounters Strings/missing values or wrong status rules | Standardize data and filter by business status |
| Price drifts on read/write | Intermediate conversion through `double` or JSON client drops precision | Construct BigDecimal from strings, use Decimal128 in BSON, test end-to-end |
| Writing huge number fails | BigDecimal exceeds Decimal128 precision/exponent limits | Pre-validate, consider another storage model if requirements truly exceed limits |
| Comparing two BigDecimals with `equals` fails | Same numeric value but different scale | Normalize scale or use `compareTo` |
| Initial insert succeeds but update changes BSON type | Another write path uses raw driver/string/Double | Standardize all write paths and verify BSON after updates |
| `NumberDecimal(129900.00)` loses intended digits | Passed through JavaScript number before decimal construction | Use `NumberDecimal("129900.00")` with a string |
| Decimal128 reports are wrong across currencies | Currency units, FX rates, or rounding rules not separated | Explicitly design currency, scale, and conversion operations |

## 14. Applied Exercises

**Exercise 1 — Save Price with the Right Type.** Create `Product` with `price: BigDecimal`, annotated with `@Field(targetType = FieldType.DECIMAL128)`. Save product `LAP-001` priced at `129900.00` and verify `$type` returns `"decimal"`.

**Exercise 2 — Price-Range Query.** Insert three products priced at `99000.00`, `129900.00`, and `219900.00`. Use `MongoTemplate` to filter products in `[100000.00, 200000.00)`; verify only the `129900.00` product is selected. Check raw `mongosh` queries using `NumberDecimal("...")`.

**Exercise 3 — Orders and Aggregation.** Create an `Order` with two line items; have the server compute `lineTotal` and `totalAmount` with BigDecimal. Persist BSON Decimal128, then use `$sum` aggregation to compute revenue. Compare with the sum computed in Java.

**Exercise 4 — Upgrading Storage Types.** In a test database, create documents with `price` as String, Double, and Decimal128. Profile with `$type`, check conversion errors, migrate valid String data to Decimal128 in batches, and re-run queries/revenue totals. Describe precision-loss risks from Double.

**Exercise 5 — Framework Upgrade.** Check whether your project uses Spring Data MongoDB 4.x or 5.x; document the active `BigDecimalRepresentation` choice and update integration tests to catch BSON type regressions during upgrades.

Learners succeed when they can answer:

1. Why does `BigDecimal` in Java still require choosing a target BSON type?
2. When does `BigDecimal` exceed `Decimal128`'s limits?
3. At what levels do `@Field(targetType = FieldType.DECIMAL128)` and `MongoCustomConversions` configuration differ?
4. What changed in Spring Data MongoDB 5.x compared to 4.x regarding default representations?
5. Why can queries, indexes, and aggregations on `price` fail when BSON contains both String and Decimal128?
6. How should you test to confirm **actual storage type**, not just the Java value read back?

**Expected outcome:** learners can persist `BigDecimal` explicitly as Decimal128, verify actual BSON data, control precision/scale, and prepare safe migrations when legacy data uses different storage types. This forms a reliable foundation for designing queries, aggregations, indexes, transactions, reactive access, and financial data tests in Mini Commerce.

## References

- [Spring Data MongoDB 4.5 — Custom Conversions](https://docs.spring.io/spring-data/data-mongodb/reference/4.5/mongodb/mapping/custom-conversions.html): historical BigDecimal storage behavior and declaring `@Field(targetType = DECIMAL128)`.
- [Spring Data MongoDB 5.1 — Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html): explicit representations, `MongoCustomConversions`, and large number formatting.
- [Spring Data MongoDB — Migration Guide 4.x to 5.x](https://docs.spring.io/spring-data/mongodb/reference/migration-guide/migration-guide-4.x-to-5.x.html): changes to BigDecimal/BigInteger conversions when upgrading.
- [MongoDB — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/): characteristics of Decimal128 and other BSON types.
- [MongoDB — Decimal128 in mongosh](https://www.mongodb.com/docs/mongodb-shell/reference/data-types/): creating properly typed Decimal128 values in the shell.
