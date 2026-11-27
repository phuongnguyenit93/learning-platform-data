# Writing @ReadingConverter and @WritingConverter

## 1. When Does Spring Data MongoDB Need Custom Converters?

**Spring Data MongoDB** provides `MappingMongoConverter` to convert Java objects into BSON documents and reconstruct objects from data in MongoDB. For common types like `String`, `Integer`, `Long`, `Instant`, or entities with straightforward field mappings, default rules are usually sufficient. However, an application may need **a BSON representation that differs from the Java structure**.

For example, a domain model has a `Money` value object containing the amount in minor units and the currency code. When saving, we want MongoDB to receive a stable structure:

```javascript
{
  _id: "order-1001",
  total: {
    minorUnits: NumberLong("1999"),
    currency: "USD"
  }
}
```

In Java, the `Money` object can enforce invariant validation logic; in BSON, it is a `Document` containing two simple fields. If we need exact control over writing and reading this type, we can write two converters:

- **`@WritingConverter`:** converts Java `Money` to `org.bson.Document` for writing.
- **`@ReadingConverter`:** converts `org.bson.Document` read from MongoDB to Java `Money`.

This capability is useful for value objects, legacy data schemas, custom date/time formats, and fields requiring a dedicated storage representation. In this lesson, examples use Spring Data MongoDB with `MongoTemplate` and repositories; converter metadata also applies when an application uses `ReactiveMongoTemplate` or reactive repositories.

**Goal:** understand conversion directions, write and register converters properly, inspect actual BSON, test both directions, handle missing/wrong-type data, and know when not to use a custom converter.

## 2. Conversion Flow Between Java and MongoDB

```mermaid
flowchart LR
    A["Service: Order with Money total"] --> B["MongoRepository or MongoTemplate"]
    B --> C["MappingMongoConverter"]
    C -->|"@WritingConverter"| D["BSON Document"]
    D --> E[("MongoDB")]
    E --> F["BSON Document"]
    F -->|"@ReadingConverter"| G["MappingMongoConverter"]
    G --> H["Order containing Money"]
```

| Component | Role |
| --- | --- |
| `Converter<S, T>` | Spring interface for a conversion from source type `S` to target type `T`. |
| `@WritingConverter` | Marks a converter used on the **write path** according to Spring Data registration rules. |
| `@ReadingConverter` | Marks a converter used on the **read path** from the store. |
| `MongoCustomConversions` | Where custom converters are declared so the infrastructure knows about and registers them. |
| `MappingMongoConverter` | Component that uses mapping metadata, BSON types, and converters to read/write entities. |
| MongoDB Java driver | Sends/receives BSON; does not automatically understand Spring Data domain annotations when using raw BSON. |

The two annotations **do not automatically activate a converter just by being placed on a class**. Spring Data requires explicit converter registration. For example, placing `@Component` on a class should not be treated as proof that it participates in `MongoCustomConversions`.

### 2.1. How Spring Data Determines Conversion Direction

When one side is a type that the MongoDB driver/store can handle directly, Spring Data typically infers direction from the converter's generic type pair:

```java
// Write: domain object -> native store type.
Converter<Money, org.bson.Document>

// Read: native store type -> domain object.
Converter<org.bson.Document, Money>
```

However, if **both sides are native types**, such as `Converter<String, Long>`, the system cannot safely infer whether it is a reading or writing conversion. `@ReadingConverter` and `@WritingConverter` remove this ambiguity.

**Do not use overly broad converters** such as a rule that "every `String` becomes a `Long`" when only one property needs conversion. A converter registered with the wrong scope can cause unrelated fields to be converted unexpectedly.

## 3. Designing the Example: Money as a Value Object

To separate business logic from storage, use `Money` containing:

- `minorUnits`: a 64-bit integer of the smallest currency unit by system convention;
- `currency`: an ISO 4217 currency code, e.g., `USD`.

In the `USD` example, `1999` minor units correspond to **19.99 USD**. For other currencies, the number of decimal digits and minor units may differ; never assume every currency has two decimal places.

```java
package example.orders;

import java.util.Currency;
import java.util.Objects;

public record Money(long minorUnits, String currency) {

    public Money {
        Objects.requireNonNull(currency, "currency");
        Currency.getInstance(currency); // Rejects invalid currency codes.
    }
}
```

The example uses a Java record; `Money` does not carry `@Document` because it is a **value object inside an entity**, not a root document with its own collection.

Define the `Order` entity:

```java
package example.orders;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public class Order {

    @Id
    private String id;

    private Money total;

    public Order() {
    }

    public Order(String id, Money total) {
        this.id = id;
        this.total = total;
    }

    public String getId() {
        return id;
    }

    public Money getTotal() {
        return total;
    }
}
```

The converter classes in the following sections are placed in the same `example.orders` package or imported appropriately according to your actual project structure.

## 4. Writing @WritingConverter: Money → BSON Document

A writing converter implements `Converter<Money, Document>`:

```java
package example.orders;

import org.bson.Document;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class MoneyWriteConverter implements Converter<Money, Document> {

    @Override
    public Document convert(Money source) {
        return new Document("minorUnits", source.minorUnits())
            .append("currency", source.currency());
    }
}
```

Here:

1. `source` is the Java value object, not already-stored BSON.
2. `minorUnits` is a Java `long`; the driver can represent it as **BSON Int64**.
3. `currency` is a `String`, stored as **BSON String**.
4. The returned `Document` only describes the `total` value element. Spring Data continues mapping the `Order` entity and the parent `_id` field.

When saving:

```java
import org.springframework.data.mongodb.core.MongoTemplate;

Order order = new Order("order-1001", new Money(1999L, "USD"));
mongoTemplate.save(order);
```

Equivalent document in MongoDB:

```javascript
{
  _id: "order-1001",
  total: {
    minorUnits: NumberLong("1999"),
    currency: "USD"
  }
}
```

**Important point:** a converter defines **storage types and structure**, so renaming `minorUnits` to `amount` or changing `Long` to `String` is a data schema change. Once a schema is used by queries, indexes, aggregations, or other services, manage it as a data contract.

### 4.1. Why Not Write a Converter Directly to JSON?

MongoDB stores BSON, not "JSON strings" unless you intentionally put a `String` containing JSON content into a field. Writing `Converter<Money, String>` to store `"{\"amount\": ...}"` prevents MongoDB from querying `total.minorUnits` directly in the usual way. When the goal is storing a **queryable subdocument**, returning `Document` is more appropriate.

A converter to `String` can still be right for a simple value object carrying a single value (such as a formatted identifier), but that is a different decision from a two-part `Money` model.

## 5. Writing @ReadingConverter: BSON Document → Money

For reading, we implement the reverse conversion:

```java
package example.orders;

import org.bson.Document;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class MoneyReadConverter implements Converter<Document, Money> {

    @Override
    public Money convert(Document source) {
        Object value = source.get("minorUnits");
        long minorUnits;

        if (value instanceof Long number) {
            minorUnits = number;
        } else if (value instanceof Integer number) {
            // Allow legacy records with BSON Int32.
            minorUnits = number.longValue();
        } else {
            throw new IllegalArgumentException(
                "total.minorUnits must be BSON Int64 or Int32"
            );
        }

        String currency = source.getString("currency");
        if (currency == null) {
            throw new IllegalArgumentException(
                "total.currency must not be missing"
            );
        }

        return new Money(minorUnits, currency);
    }
}
```

The `Document` in this example comes from the MongoDB driver. When the field holds BSON Int64, Java normally receives `Long`; when the field is BSON Int32, Java receives `Integer`. Both can convert to `long` **without losing integer precision**. This converter **deliberately rejects `Double` and `String`** to avoid rounding or guessing the meaning of uncontracted data.

Calling `source.getString("currency")` also helps catch wrong-type data: if the field is not a String, the driver can report a type conversion error instead of silently using another value.

If the source document has the entire `total` field missing or set to BSON `null`, Spring Data may handle the property at the null level **without calling `convert(null)`**. Do not assume the converter always gets a chance to replace every null value with `Money(0, "USD")`. Missing money and zero money are two different business states.

### 5.1. Do Not Silently Turn Invalid Data into Valid Values

Dangerous example:

```java
// Avoid doing this with financial data:
long units = ((Number) source.get("minorUnits")).longValue();
```

If the field holds `Double(19.9)`, `longValue()` can truncate the fractional part and yield 19. Data read back looks valid but has actually been altered. A converter is a validation boundary, so check exact BSON types, ranges, units, and legacy compatibility rules.

## 6. Registering with MongoCustomConversions

The two converters above are only used by the mapping infrastructure once registered. In a **Spring Boot** application relying on MongoDB auto-configuration, you can declare a `MongoCustomConversions` bean:

```java
package example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;

@Configuration(proxyBeanMethods = false)
public class MongoConversionConfiguration {

    @Bean
    MongoCustomConversions mongoCustomConversions() {
        return MongoCustomConversions.create(adapter -> {
            adapter.registerConverter(new MoneyWriteConverter());
            adapter.registerConverter(new MoneyReadConverter());
        });
    }
}
```

Spring Boot picks up this bean in standard Spring Data MongoDB configuration; place the configuration within component scan scope or import it explicitly in tests.

**If your project already has its own `MongoCustomConversions`**, add these two converters to the existing configuration rather than accidentally creating a competing bean. And if you are customizing Java time, BigDecimal, or other converters, be sure to preserve that configuration.

### 6.1. Projects Configuring MongoDB Manually with AbstractMongoClientConfiguration

If you do not rely on Boot auto-configuration and instead extend `AbstractMongoClientConfiguration`, Spring Data provides a hook to add converters:

```java
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;

// Inside a class extending AbstractMongoClientConfiguration:
@Override
protected void configureConverters(
        MongoCustomConversions.MongoConverterConfigurationAdapter adapter) {
    adapter.registerConverter(new MoneyWriteConverter());
    adapter.registerConverter(new MoneyReadConverter());
}
```

This is **an alternative configuration approach**, not code to add alongside the bean above. A full `AbstractMongoClientConfiguration` setup also requires the database name and connection settings, which are outside the scope of this example.

### 6.2. What Dependencies Are Needed?

With Spring Boot, the standard synchronous starter is:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
```

The reactive branch typically uses:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb-reactive</artifactId>
</dependency>
```

The `Converter`, `@ReadingConverter`, and `@WritingConverter` types are provided by the corresponding Spring Data/Spring Framework ecosystem. Let Spring Boot dependency management handle compatible versions. You do not need to install a separate library just to use these two annotations.

## 7. Operating via Repositories and MongoTemplate

Once the conversion bean is recognized by Spring Data MongoDB, services simply save and read entities as usual:

```java
package example.orders;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository extends MongoRepository<Order, String> {
}
```

```java
package example.orders;

import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public Order createSample() {
        return repository.save(
            new Order("order-1001", new Money(1999L, "USD"))
        );
    }

    public Order load(String id) {
        return repository.findById(id)
            .orElseThrow(() ->
                new IllegalArgumentException("Order not found: " + id)
            );
    }
}
```

In a normal flow:

1. The service creates an `Order` containing `Money`.
2. The repository requests entity mapping.
3. `MoneyWriteConverter` converts `Money` into a subdocument.
4. The driver writes BSON to MongoDB.
5. On read, `MoneyReadConverter` reconstructs `Money` from the subdocument.

`MongoTemplate.save(order)` and `MongoTemplate.findById(id, Order.class)` use the same mapping infrastructure. Most business code never needs to invoke converters manually.

### 7.1. Querying by Actual Fields in BSON

Once a converter writes `total` as a `Document`, raw MongoDB queries can target the actual stored field names:

```javascript
db.orders.find({
  "total.currency": "USD",
  "total.minorUnits": { $gte: NumberLong("1000") }
});

db.orders.createIndex({
  "total.currency": 1,
  "total.minorUnits": 1
});
```

**Do not assume a typed query using `Criteria.where("total.minorUnits")` is always understood by Spring Data as a regular property path:** a custom converter can cause `Money` to be treated as a single converted value rather than a nested persistent entity whose subproperties the mapper traverses. When querying on the internal structure produced by a converter, verify the actual BSON filter, `explain` output, and index used; or use a standard embedded entity model if frequent querying on multiple subfields is needed.

A custom converter does not automatically create indexes, make queries faster, or replace document design.

## 8. Unit Testing Converters in Isolation

Before testing against MongoDB, verify the conversion rules as pure functions:

```java
package example.orders;

import static org.junit.jupiter.api.Assertions.*;

import org.bson.Document;
import org.junit.jupiter.api.Test;

class MoneyConverterUnitTest {

    private final MoneyWriteConverter writer = new MoneyWriteConverter();
    private final MoneyReadConverter reader = new MoneyReadConverter();

    @Test
    void writesAndReadsMoneyWithoutLosingMinorUnits() {
        Money original = new Money(9_007_199_254_740_993L, "USD");

        Document bson = writer.convert(original);

        assertEquals(
            9_007_199_254_740_993L,
            bson.getLong("minorUnits")
        );
        assertEquals("USD", bson.getString("currency"));

        Money restored = reader.convert(bson);
        assertEquals(original, restored);
    }

    @Test
    void supportsLegacyInt32WithoutRounding() {
        Document bson = new Document("minorUnits", 25)
            .append("currency", "USD");

        assertEquals(new Money(25L, "USD"), reader.convert(bson));
    }

    @Test
    void rejectsFloatingPointAndMissingCurrency() {
        Document fractional = new Document("minorUnits", 19.99)
            .append("currency", "USD");
        assertThrows(
            IllegalArgumentException.class,
            () -> reader.convert(fractional)
        );

        Document missingCurrency =
            new Document("minorUnits", 100L);
        assertThrows(
            IllegalArgumentException.class,
            () -> reader.convert(missingCurrency)
        );
    }
}
```

This test verifies the logic of both converters, but **does not prove Spring has registered them**, nor does it verify the actual BSON types after passing through the MongoDB driver. An integration test is still needed.

## 9. Integration Testing: Reading Back Raw BSON and Entities

The following example uses `MongoTemplate` to check three things:

- The conversion bean is loaded into the application context;
- `Money` is written as a subdocument with the right BSON types;
- Spring Data reads back the `Money` object with unchanged values.

```java
package example.orders;

import static com.mongodb.client.model.Filters.eq;
import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
@Import(MongoConversionConfiguration.class)
class MoneyMongoMappingTest {

    @Autowired
    MongoTemplate mongoTemplate;

    @Test
    void converterIsAppliedWhenWritingAndReading() {
        String id = "order-" + UUID.randomUUID();
        Money amount = new Money(9_007_199_254_740_993L, "USD");

        mongoTemplate.save(new Order(id, amount));

        Document raw = mongoTemplate.getCollection("orders")
            .find(eq("_id", id))
            .first();

        assertNotNull(raw);
        Document storedTotal = raw.get("total", Document.class);
        assertNotNull(storedTotal);
        assertEquals(
            amount.minorUnits(),
            storedTotal.getLong("minorUnits")
        );
        assertEquals(
            amount.currency(),
            storedTotal.getString("currency")
        );

        Order loaded = mongoTemplate.findById(id, Order.class);
        assertNotNull(loaded);
        assertEquals(amount, loaded.getTotal());
    }
}
```

**Environment note:** `@DataMongoTest` configures a Spring context focused on MongoDB, but does not by itself guarantee a MongoDB server is available. You can use Testcontainers MongoDB or a dedicated test instance. Test slice imports/annotations may differ across Spring Boot major versions; adjust according to your project's BOM.

If `loaded.getTotal()` passes while `storedTotal` has the wrong structure, the mapping might still be using default rules instead of your converter, or another converter might be taking precedence. **Raw BSON** is the decisive evidence to distinguish these two situations.

## 10. When Should You Not Use a Type-Wide Converter?

`MongoCustomConversions` registers by **source/target type pair**, giving it broad scope across the mapping context. If every `Money` in the application should be stored the same way, that scope makes sense. But if one field must store minor units while another must store a formatted string with a symbol, a type-wide converter can cause surprises.

| Need | Appropriate Choice |
| --- | --- |
| A value object always stored in one consistent BSON structure | `@WritingConverter` / `@ReadingConverter` registered in `MongoCustomConversions` |
| Only want to change the target BSON type for one property | `@Field(targetType = ...)` if supported by the target type |
| Only **one property** has a special conversion rule | Consider Spring Data property-specific value conversion or a separate domain type |
| Need JSON output different from BSON | DTOs and Jackson serialization/deserialization |
| Need conversion inside a server-side aggregation | MongoDB `$convert`, `$toString`, `$toDecimal`, etc. |
| Need standard subdocument mapping and deep queries across multiple fields | Consider an embedded value object mapped by Spring Data defaults |
| Need to query an independent collection | Separate entity/repository; converters do not create collections |

### 10.1. Distinguishing from @Field and @JsonSerialize

Spring Data's `@Field` controls how a property maps to BSON, such as renaming or specifying a target type. It is not a layer for arbitrary business transformations. Jackson's `@JsonSerialize` controls REST JSON output and **does not change the BSON that Spring Data stores**.

For example, when you simply need `BigDecimal` stored as Decimal128:

```java
import java.math.BigDecimal;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Field(targetType = FieldType.DECIMAL128)
private BigDecimal amount;
```

This is usually more concise than writing a global `BigDecimal -> Decimal128` converter. Default `BigDecimal` storage can vary across Spring Data MongoDB major versions; check the big-number representation configuration in the version you are using.

### 10.2. Distinguishing from MongoDB Driver Codecs

The MongoDB Java driver has `Codec` and `CodecRegistry` for driver-level conversion. Spring Data has `MappingMongoConverter` with entity metadata. If a service writes an `org.bson.Document` directly with the raw driver, it will not automatically invoke `MoneyWriteConverter` registered for Spring Data mapping. Do not assume that configuring a converter at the Spring Data layer applies to every BSON write in the application.

## 11. Common Errors and How to Diagnose Them

| Symptom | Likely Cause | Check |
| --- | --- | --- |
| Converter is never called | Not registered, bean not loaded, code uses raw driver path | Check `MongoCustomConversions` bean, test raw BSON, trace write path |
| Writes fine but read fails | Missing `@ReadingConverter` or actual schema differs from reader | Check types/fields with `$type` and raw `Document` |
| Reads old data fine but new data is wrong | Asymmetric writer and reader conventions | Run round-trip tests and inspect BSON |
| Money value gets truncated | Casting `Double` to `long` via `longValue` | Remove ambiguous casts; enforce units and BSON types |
| A converter affects unrelated properties | Overly broad converter registration or two native types | Narrow type pair, use directional annotations or property converter |
| Queries on subproperties return no results | MongoDB stores different field names; mapper treats value object as converted type | Inspect actual BSON, generated filter, indexes, and `explain` |
| Entity save/read passes but API payload loses precision | Jackson/JavaScript Number, HTTP contract | Test JSON round-trip and use safe formats for large numbers |
| New version fails to read old documents | Reader does not support legacy schema | Classify versions, migrate, and test legacy samples |
| Unit tests pass but integration fails | Converter not registered or MongoDB driver produces unexpected BSON | Test with Boot context and a real MongoDB instance |

A useful investigation workflow:

1. Check the Java field type and `Converter<S, T>` generic pair.
2. Verify correct imports of `org.springframework.data.convert.ReadingConverter` or `WritingConverter`.
3. Confirm the converter is registered in the `MongoCustomConversions` instance actually used by Boot/Spring Data.
4. Write a small sample and inspect raw BSON, including `Int32`/`Int64`/`Double`/`Decimal128` types when relevant.
5. Read back via repository/template; inspect the root conversion exception instead of swallowing it.
6. If queries/updates are involved, inspect actual BSON names and execution plans.

## 12. Legacy Data and Schema Version Design

Suppose the first version of the application stored:

```javascript
{
  _id: "order-old-001",
  total: {
    minorUnits: NumberInt("1999"),
    currency: "USD"
  }
}
```

The new writer always produces `Int64`, while the reader in section 5 still accepts legacy `Int32`. This is **intentional read compatibility**, safe because widening a signed 32-bit integer to 64-bit loses no value.

However, if the legacy version stored:

```javascript
{
  _id: "order-old-002",
  total: "19.99"
}
```

this is no longer a subdocument. `Converter<Document, Money>` cannot directly handle a BSON String in the `total` field. Adding a `Converter<String, Money>` reader is only safe if **the currency, scale, and origin of the string are known**. If `"19.99"` has no currency information, defaulting to USD could alter the meaning of the data; external metadata or a verified migration is required.

When changing schemas, you should:

1. Inventory existing data shapes (raw BSON, `$type`, null/missing);
2. Define source conventions and error-handling checks;
3. Create tests for each document version;
4. Deploy a compatible reader or migrate data in verifiable batches;
5. Switch the writer to the new format;
6. Monitor legacy record counts and remove the old read path only after migration completes.

Example checking BSON types of the `total` field:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: { $type: "$total" },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

If `string`, `object`, `null`, or `missing` appear, you must decide how the application treats each state. A converter should never silently turn missing or malformed data into a zero amount.

## 13. Reactive MongoDB and Operational Considerations

`ReactiveMongoTemplate` and `ReactiveMongoRepository` still use Spring Data MongoDB's mapping/conversion mechanism, except results are wrapped in `Mono` or `Flux`.

```java
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;

interface ReactiveOrderRepository
        extends ReactiveMongoRepository<Order, String> {
}
```

```java
import reactor.core.publisher.Mono;

Mono<Order> saved = reactiveRepository.save(
    new Order("order-reactive-1", new Money(1999L, "USD"))
);

Mono<Money> restored = reactiveRepository
    .findById("order-reactive-1")
    .map(Order::getTotal);
```

The snippet above assumes `reactiveRepository` is injected. Two separate publisher creations do not guarantee execution order; in an application you need to **chain the pipeline** so the load happens only after save:

```java
Mono<Money> savedAndRestored = reactiveRepository
    .save(new Order("order-reactive-1", new Money(1999L, "USD")))
    .flatMap(order -> reactiveRepository.findById(order.getId()))
    .map(Order::getTotal);
```

The `Money -> Document` and `Document -> Money` converters still run as synchronous in-memory conversion logic. **Do not place blocking I/O, HTTP calls, or database queries inside `convert()`**: mapping can occur on the reactive execution path, and blocking I/O in a converter undermines the non-blocking model.

Converters must also be **thread-safe** when registered as shared instances. Write pure conversion functions without storing mutable per-request state in converter fields. Avoid reading system clock or current user info to produce different BSON forms from the same input value; doing so makes tracing and testing much harder.

## 14. Practice Exercises

### Exercise 1 — Bidirectional Converter

Create a `PhoneNumber` value object with `countryCode` and `nationalNumber`. Write a `@WritingConverter` to store it as a two-field subdocument and a `@ReadingConverter` to read it back. Register the converters, save an entity via `MongoRepository`, and verify the raw BSON.

### Exercise 2 — Missing and Wrong-Type Data

With `MoneyReadConverter`, test these documents:

- `{minorUnits: NumberLong("100"), currency: "USD"}`;
- `{minorUnits: NumberInt("100"), currency: "USD"}`;
- `{minorUnits: 1.5, currency: "USD"}`;
- `{minorUnits: "100", currency: "USD"}`;
- `{minorUnits: NumberLong("100")}`.

Document which cases are valid, which ones the converter must reject, and why `Double` or String should not be blindly cast to an integer.

### Exercise 3 — Testing Registration

Create two tests: a direct unit test `writer.convert(reader.convert(...))` and an integration test via `MongoTemplate`. Temporarily remove the converters from `MongoCustomConversions` to observe how BSON differs; restore the configuration and keep the test verifying the intended write path.

### Exercise 4 — Queries and Indexes

Create an index on `total.currency` + `total.minorUnits` in MongoDB, find USD orders with at least 1,000 minor units. Compare the raw query with the query generated via `MongoTemplate`, and use `explain("executionStats")` to confirm index usage and field paths.

### Exercise 5 — Choosing the Minimal Solution

For the following three requirements, choose a custom converter, `@Field(targetType = ...)`, or a DTO:

1. Store `BigDecimal` as BSON Decimal128.
2. Store `PhoneNumber` as a normalized E.164 String.
3. Return monetary amounts as decimal strings in JSON while storing BSON Decimal128.

Explain the difference between **storage format**, **domain model**, and **wire/transport format**.

### Self-Check Questions

- How do `@ReadingConverter` and `@WritingConverter` differ in conversion direction?
- Why can having the annotation without registering in `MongoCustomConversions` still leave a converter unused?
- Why is `Converter<String, Long>` a case requiring extra care?
- Why must you inspect raw BSON instead of only comparing entities before and after `save`?
- When should you use `@Field(targetType = ...)` instead of a custom converter?
- Should a converter perform additional queries or read per-request data? Why or why not?

## Key Takeaways

In **Spring Data MongoDB**, **`@WritingConverter`** defines the conversion from a Java object to its BSON storage form, while **`@ReadingConverter`** defines reconstructing BSON data back into a Java object. Implement `Converter<S, T>` with the right type pair and **explicitly register it in `MongoCustomConversions`**. Converters give you control over data representation, but they also create a schema contract that requires management, testing, and migration. Keep converters small, pure, and safe against missing or wrong-type data, and verify with raw BSON and integration tests. When you only need to change a single BSON type for one field, prefer simpler mapping mechanisms; when you need to change JSON formatting, handle it at the DTO/serialization layer.

## References

- [Spring Data MongoDB — Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html)
- [Spring Data Commons — Custom Conversions and converter disambiguation](https://docs.spring.io/spring-data/mongodb/reference/data-commons/custom-conversions.html)
- [Spring Data MongoDB — MongoCustomConversions API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/convert/MongoCustomConversions.html)
