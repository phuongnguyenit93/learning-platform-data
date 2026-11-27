# Custom Converters for Business Data Types in Spring Data MongoDB

## 1. Problem Statement: Right Data Type in Java, Wrong Storage Shape in MongoDB

Suppose an invoicing application has a business type **Money**. In Java, monetary amounts should not simply be **double**, because you must preserve exact decimal values, currency codes, and domain invariants.

An invoice:

~~~text
Invoice INV-100
  customer = C-17
  total = Money(19.90, USD)
~~~

When persisting to MongoDB, the development team wants a clear BSON structure:

~~~javascript
{
  _id: "INV-100",
  customerId: "C-17",
  total: {
    amount: NumberDecimal("19.90"),
    currency: "USD"
  }
}
~~~

However, Java domains often use complex or immutable types, external libraries, or field names that do not align with BSON. Leaving everything to default framework mapping may violate the desired data contract—for example, turning monetary values into strings, persisting internal fields, or decomposing a Java object in ways tightly coupled to class structure.

**Custom converters** in **Spring Data MongoDB** let you control how conversion occurs between **business types** and **BSON/MongoDB storage values**.

### Learning Objectives

After this lesson, you will be able to:

1. Understand the role of **MappingMongoConverter** and default mapping mechanics.
2. Distinguish between a **reading converter** and a **writing converter**.
3. Design a business value object and convert it to BSON using **Converter<S, T>**.
4. Register converters via **MongoCustomConversions** in Spring Boot/Spring Data.
5. Use **Decimal128** properly for currency amounts while avoiding **double** precision errors.
6. Query and index converted values, and understand the difference between entity properties and BSON fields.
7. Compare custom converters against **@Field(targetType)**, DTO mapping, and property-scoped converters.
8. Manage legacy data read failures, schema evolution, and migrations.
9. Avoid overly broad global converters, lossy formatting, conflicts, or executing business logic outside persistence scope.
10. Design unit/integration tests and measure conversion overhead at millions-of-documents scale.

## 2. Where Do Custom Converters Fit in the Data Flow?

A `save` or `find` operation through Spring Data:

~~~text
                         APPLICATION / DOMAIN
                     Invoice { total: Money }
                                |
                                v
                      MongoRepository / MongoTemplate
                                |
                                v
                       MappingMongoConverter
                         |           |
                 Mapping metadata    MongoCustomConversions
                 @Id, @Field, ...    custom read/write converters
                         |           |
                         +-----+-----+
                               |
                               v
                    org.bson.Document / BSON
                               |
                               v
                        MongoDB Java Driver
                               |
                               v
                    MongoDB collection: invoices
~~~

On read, the path reverses:

~~~text
BSON returned by MongoDB
      |
      v
MongoDB Driver
      |
      v
MappingMongoConverter + ReadingConverter
      |
      v
Invoice with Money value object
~~~

**MappingMongoConverter** performs Spring Data MongoDB's data mapping. **MongoCustomConversions** is the registry of conversion rules consulted by `MappingMongoConverter` whenever it encounters matching registered type pairs.

### 2.1. What Does Default Mapping Already Handle?

Before writing a custom converter, note that Spring Data MongoDB already handles many cases out of the box:

- Mapping Java objects to BSON documents based on field/property metadata.
- Converting common types: `String`, numeric primitives/wrappers, collections, maps, enums, and many supported date/time types.
- Applying **@Id**, **@Field**, **@Transient**, custom field names, and configured type metadata.
- Supporting constructors and records for immutable domain types in compatible versions.
- Converting property types supported by native MongoDB mapping and the Spring conversion service.

Thus, you do not need a custom converter for every Java record or class.

### 2.2. When Do You Truly Need a Custom Converter?

Good fits include:

| Value object | Java representation | Desired BSON representation |
|---|---|---|
| **Money** | `BigDecimal` + currency code | Embedded document with `Decimal128` and string. |
| **EmailAddress** | Self-validating type | A single canonical string. |
| **PhoneNumber** | Parsed number + country code | Normalized E.164 string. |
| **BusinessStatus** | Enum/domain code | Stable external code string. |
| **GeoCoordinate** | Lat/lon with invariants | Embedded point or schema-compliant GeoJSON. |
| **BookingPeriod** | Start/end with interval rules | Two timestamps with fixed names/formats. |
| **EncryptedValue** | Protected data value object | Ciphertext + key/version metadata per security design. |

The primary reason is **controlling the persistence contract**, not merely reducing lines of code.

### 2.3. Converters Do Not Replace Other Layers

Distinguish clearly:

~~~text
HTTP JSON serializer:
  Java object <-> JSON request/response

DTO/domain mapper:
  API DTO <-> business/domain object

Spring Data MongoDB converter:
  domain property/entity <-> BSON storage value
~~~

A custom MongoDB converter **does not automatically alter Jackson JSON APIs**, transform Kafka payloads, change another SQL database's schema, or migrate legacy documents.

### 2.4. Source and Target Type Direction Matters

Spring Data distinguishes **native MongoDB store types** from **domain types**. Pairs where both source and target are native store types can create ambiguity over conversion direction.

For example:

~~~text
String -> BigDecimal
BigDecimal -> String
~~~

Never register global conversions indiscriminately without understanding where they apply. Use **@ReadingConverter** or **@WritingConverter** to declare explicit intent and avoid skewing unrelated properties.

## 3. Define the BSON Data Contract Before Writing the Converter

A solid converter starts with an explicit **data contract**:

~~~text
Java type:
  Money { BigDecimal amount, String currencyCode }

BSON storage:
  total.amount   -> Decimal128
  total.currency -> string ISO currency code

Validation:
  currency is recognized and normalized
  amount is a decimal value within Decimal128 range
  no silent rounding or FX conversion
~~~

### 3.1. Why Not Use double for Money?

IEEE-754 binary floating-point `double` cannot represent all decimal fractions exactly:

~~~java
double value = 0.1 + 0.2;
System.out.println(value); // often prints 0.30000000000000004
~~~

In accounting and payments, **BigDecimal** is standard for representing monetary amounts in the domain. MongoDB provides **BSON Decimal128** for exact decimal representation within its supported precision and exponent range.

**BigDecimal does not have unlimited range when converted to Decimal128**: `Decimal128` has bounded precision and exponent limits. A converter must fail explicitly if a value cannot be represented, rather than silently converting to `double` or truncating digits.

### 3.2. Why Store the Currency?

~~~text
19.90 USD
19.90 EUR
19.90 JPY
~~~

These three numbers cannot be treated as equal monetary values. A `Money` object should hold **amount + currency**, and any cross-currency addition or comparison must follow explicit business rules.

**Converters must never look up live FX rates** during reads or writes: exchange rates fluctuate over time, breaking round-trip determinism and introducing side effects into database reads.

### 3.3. Two Common Monetary Storage Designs

**Design A — Decimal128 amount + currency:**

~~~javascript
total: {
  amount: NumberDecimal("19.90"),
  currency: "USD"
}
~~~

Advantage: preserves decimal values and supports MongoDB numeric comparison and aggregation operators within a single currency.

**Design B — minorUnits + currency:**

~~~javascript
total: {
  minorUnits: NumberLong("1990"),
  currency: "USD"
}
~~~

Advantage: integer arithmetic for amounts fitting within 64-bit integers. However, **not every currency uses two decimal places**; JPY, KWD, VND, and specific business rules have different minor-unit exponents. Scaling requires explicit validation/rounding policies and overflow protection.

Both models involve trade-offs. In this lesson, we choose **Decimal128 + ISO currency code** to illustrate custom converters transparently.

### 3.4. BSON Structure Dictates Queries and Indexes

When `total` is a subdocument with two fields:

~~~javascript
db.invoices.createIndex({
  tenantId: 1,
  "total.currency": 1,
  "total.amount": 1
});
~~~

You can filter invoices in the same currency and compare amounts numerically. If you store `amount` as a string instead, numeric range queries and sorting behave differently: **whether `"100"` sorts before or after `"20"` lexicographically is not equivalent to numeric comparison**.

Choose the storage format **before building an entire suite of queries and indexes**, rather than altering the converter after production data exists without a migration.

## 4. Creating an Immutable Business Type: Money

Examples use Java 17+ and Spring Data MongoDB with record/value-object support. Decouple the domain type from BSON details: **`Money` does not need to know about `Decimal128` or `Document`**.

~~~java
package com.example.billing.domain;

import java.math.BigDecimal;
import java.util.Currency;
import java.util.Locale;
import java.util.Objects;

public record Money(BigDecimal amount, String currencyCode) {

    public Money {
        Objects.requireNonNull(amount, "amount is required");
        Objects.requireNonNull(currencyCode, "currency is required");

        currencyCode = currencyCode.trim()
                .toUpperCase(Locale.ROOT);

        if (!currencyCode.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                    "Currency code must have three letters");
        }

        Currency.getInstance(currencyCode);
    }

    public static Money of(String decimal, String currency) {
        return new Money(new BigDecimal(decimal), currency);
    }
}
~~~

### 4.1. Why Keep the Value Object Independent of MongoDB?

The domain can write:

~~~java
Money price = Money.of("19.90", "usd");
Money tax = Money.of("1.99", "USD");
~~~

`Money` retains its business semantics even if the application later moves some data to SQL, event streams, or external APIs.

Rules such as **disallowing negative values**, **maximum scale of two decimal places**, or **tax rounding** depend on product and currency; avoid hardcoding them into this example class without a defined business contract. For JPY or KWD, a fixed scale of 2 would be wrong.

### 4.2. Currency Normalization Invariant

In the record compact constructor, the **`currencyCode`** parameter is normalized before the record field is assigned.

~~~text
Input:
  Money(19.90, "usd")

Domain:
  amount       = 19.90
  currencyCode = "USD"
~~~

Normalizing at the domain boundary lets the converter focus strictly on representation translation rather than altering business values arbitrarily.

### 4.3. BigDecimal.equals and Scale

~~~java
new BigDecimal("19.90").equals(
        new BigDecimal("19.9")
); // false: scale differs

new BigDecimal("19.90").compareTo(
        new BigDecimal("19.9")
); // 0: numerically equal
~~~

If the business considers both amounts equivalent, define a **normalization/equality policy**. This example preserves the `BigDecimal` representation so round-trips remain transparent, avoiding implicit `stripTrailingZeros` calls that silently alter scale.

## 5. Writing Converter: Money → BSON Document

The converter implements **org.springframework.core.convert.converter.Converter**, annotated with **@WritingConverter** so Spring Data knows to apply it during **writes**.

~~~java
package com.example.billing.persistence;

import com.example.billing.domain.Money;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

import java.util.Objects;

@WritingConverter
public final class MoneyWriteConverter
        implements Converter<Money, Document> {

    @Override
    public Document convert(Money source) {
        Objects.requireNonNull(source, "source");

        return new Document(
                "amount",
                new Decimal128(source.amount())
        ).append(
                "currency",
                source.currencyCode()
        );
    }
}
~~~

When invoked:

~~~java
Money money = Money.of("19.90", "USD");

Document stored = new MoneyWriteConverter().convert(money);
~~~

Expected BSON structure:

~~~javascript
{
  amount: NumberDecimal("19.90"),
  currency: "USD"
}
~~~

### 5.1. Decimal128 Is Not Unbounded BigDecimal

~~~java
new Decimal128(source.amount());
~~~

converts `BigDecimal` to **BSON Decimal128**, which has fixed precision and exponent limits. Values exceeding those bounds fail conversion.

Do **not** work around it with:

~~~java
// Avoid: may lose decimal precision.
double approximate = source.amount().doubleValue();
~~~

If the business genuinely requires precision beyond `Decimal128`, design a different persistence representation (such as a controlled decimal string or integer encoding) and re-evaluate numeric query and index requirements.

### 5.2. Why Should a Converter Be Pure?

A well-designed write converter:

- Does not call REST APIs or other databases.
- Does not fetch real-time exchange rates.
- Does not compute taxes.
- Does not use the current timestamp to synthesize currency amounts.
- Does not mutate the source `Money` object.
- Does not modify fields outside the value object's scope.

Ideally it is **deterministic**: the same `Money` and schema version always yield the same BSON representation.

### 5.3. Never Let a Converter Silently Alter Data

For instance, **19.999 USD** must not silently become **20.00 USD** simply because the converter prefers two decimal places. If rounding is required, perform it explicitly in the domain/application service under an approved rounding policy.

## 6. Reading Converter: BSON Document → Money

The read path converts the small MongoDB subdocument back into the domain value object.

~~~java
package com.example.billing.persistence;

import com.example.billing.domain.Money;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

import java.util.Objects;

@ReadingConverter
public final class MoneyReadConverter
        implements Converter<Document, Money> {

    @Override
    public Money convert(Document source) {
        Objects.requireNonNull(source, "source");

        Object rawAmount = source.get("amount");
        Object rawCurrency = source.get("currency");

        if (!(rawAmount instanceof Decimal128 decimal)) {
            throw new IllegalArgumentException(
                    "Expected BSON Decimal128 in total.amount");
        }

        if (!(rawCurrency instanceof String currency)) {
            throw new IllegalArgumentException(
                    "Expected string in total.currency");
        }

        return new Money(
                decimal.bigDecimalValue(),
                currency
        );
    }
}
~~~

### 6.1. Why Not Cast Directly?

Unchecked casting:

~~~java
Decimal128 amount =
        (Decimal128) source.get("amount");
~~~

throws an unhelpful **ClassCastException** if production holds an older document where `amount` was stored as a string or double.

Explicit type checks like the example above help distinguish:

- Missing fields.
- Unexpected BSON types.
- Legacy schema versions.
- Corrupted data or writes originating outside the application.

### 6.2. Null and Missing Fields

When the entire **total** property is null or absent, Spring mapping may handle it at the property level without invoking the converter for null. This is **different** from a subdocument containing:

~~~javascript
total: {
  currency: "USD"
}
~~~

Here, the subdocument is passed into the reader missing `amount`, so the reader should reject it, apply a controlled default, or invoke schema-version migration logic depending on the contract.

**Never silently turn a missing amount into 0** without an explicit business rule: that can turn corrupted data into an apparently valid invoice.

### 6.3. Round-Trip Contract

A custom converter property should satisfy:

~~~text
Money
  --write--> BSON Document
  --read---> Money
~~~

For valid values, no amount or currency information should be lost. Still, **object round-trip equivalence** and **byte-for-byte BSON equality** are distinct: field order, subtype, or scale representation may vary if permitted by schema policy.

### 6.4. Strict Converters and Backward Compatibility

The reader above is intentionally **strict**: it accepts only `Decimal128`. If the collection still contains legacy documents with string amounts, you need a **migration plan or a reader with a temporary compatibility window**. Avoid loosening a reader to accept arbitrary uncontrolled types permanently, as that can mask bugs in new writers.

## 7. Registering Money Converters with MongoCustomConversions

Annotating two classes is not enough if the application does not register them in the mapping registry.

In Spring Boot/Spring Data MongoDB:

~~~java
package com.example.billing.config;

import com.example.billing.persistence.MoneyReadConverter;
import com.example.billing.persistence.MoneyWriteConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;

import java.util.List;

@Configuration
public class MongoConversionConfiguration {

    @Bean
    MongoCustomConversions mongoCustomConversions() {
        return new MongoCustomConversions(
                List.of(
                        new MoneyWriteConverter(),
                        new MoneyReadConverter()
                )
        );
    }
}
~~~

When **MongoTemplate/MongoRepository** uses the `MappingMongoConverter` configured from this Spring context, `Money` is converted using the registered converters.

### 7.1. Relationship Between Annotations and the Registry

- **@WritingConverter** identifies the `Money` → `Document` direction.
- **@ReadingConverter** identifies the `Document` → `Money` direction.
- **MongoCustomConversions** registers the converter instances.
- **MappingMongoConverter** consults the registry whenever values require conversion.
- **MongoTemplate/MongoRepository** use that mapping converter across persistence operations.

Putting **@Component** on a converter or placing it on the classpath **does not guarantee** every Spring Data setup will automatically pick it up into `MongoCustomConversions`. Always register it explicitly according to your framework configuration.

### 7.2. If the Application Already Has MongoCustomConversions

Do not define a second bean that accidentally **drops existing active converters**. Consolidate the list in the existing configuration or use your Spring Data version's extension point.

When manually configuring **MongoMappingContext**, **MappingMongoConverter**, or **MongoTemplate**, verify that `MongoCustomConversions` is actually wired into the active converter instance; a bean sitting unused in the context has no effect.

### 7.3. Do Not Create a New Registry per Request

`MongoCustomConversions` is shared mapping configuration, not an object to instantiate on every `save` or `find`. Converters must be **stateless and thread-safe**, holding no request- or tenant-specific state.

### 7.4. Scope of Global Registration

Because `MoneyWriteConverter` is registered globally for the **Money → Document** type pair, every `Money` property processed by that mapping framework follows this rule.

If only one `Money` field requires a different storage format, consider a **property-scoped converter** or separate domain types with distinct meanings. Never register two competing global converters for the same `Money`/`Document` pair and rely on uncontrolled registration order.

### 7.5. Versions and Boot Auto-Configuration

Using **MongoCustomConversions(List<...>)** is standard across many Spring Data MongoDB versions, though APIs and extension points can shift across major releases. Verify the exact **Spring Boot and Spring Data MongoDB versions** in your project—especially if you build `MongoTemplate` or `MongoClient` manually instead of relying on Boot auto-configuration.

## 8. Using Money in Entities and MongoRepository

### 8.1. Invoice Entity

~~~java
package com.example.billing.persistence;

import com.example.billing.domain.Money;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

public class Invoice {
    // Full definition uses @Document on the class.
}
~~~

As a complete entity:

~~~java
package com.example.billing.persistence;

import com.example.billing.domain.Money;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "invoices")
public class Invoice {

    @Id
    private String id;

    private String tenantId;
    private String customerId;
    private Money total;

    protected Invoice() {
        // Constructor for the mapping framework.
    }

    public Invoice(
            String id,
            String tenantId,
            String customerId,
            Money total) {
        this.id = id;
        this.tenantId = tenantId;
        this.customerId = customerId;
        this.total = total;
    }

    public String getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getCustomerId() {
        return customerId;
    }

    public Money getTotal() {
        return total;
    }
}
~~~

In this entity, Spring Data handles `id`/`tenantId`/`customerId` via default mapping and uses the custom converter for **total**.

**Note on `id`:** with **@Id String**, Spring Data applies rules that convert ObjectId-compatible hex strings to `ObjectId` in typical configurations. If the business requires storing **_id** strictly as a BSON string, consider **@MongoId(FieldType.STRING)** (per version) or an explicit ID design, and inspect the raw stored BSON. Here, **INV-100** is not an ObjectId hex string.

### 8.2. Repository

~~~java
package com.example.billing.persistence;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface InvoiceRepository
        extends MongoRepository<Invoice, String> {
}
~~~

Saving:

~~~java
Invoice invoice = new Invoice(
        "INV-100",
        "tenant-a",
        "C-17",
        Money.of("19.90", "USD")
);

repository.save(invoice);
~~~

Reading:

~~~java
Invoice found = repository.findById("INV-100")
        .orElseThrow();

Money total = found.getTotal();
System.out.println(total.amount());       // 19.90
System.out.println(total.currencyCode()); // USD
~~~

There is no need to call `MoneyReadConverter` or `MoneyWriteConverter` manually from the service layer: **MappingMongoConverter** invokes them transparently during framework reads and writes.

### 8.3. Document Stored in MongoDB

Logically:

~~~javascript
{
  _id: "INV-100",
  tenantId: "tenant-a",
  customerId: "C-17",
  total: {
    amount: NumberDecimal("19.90"),
    currency: "USD"
  }
}
~~~

This is an **illustrative data shape**; depending on configuration, Spring Data may also store **_class** or type hints at the entity level. The custom `Money` converter returns a `Document` containing the two fields defined by the converter without injecting a Java class name inside every `Money` field.

### 8.4. Renaming the Property with @Field

If:

~~~java
@Field(name = "total_value")
private Money total;
~~~

then the field paths in MongoDB become **total_value.amount** and **total_value.currency**. The `Money` converter controls only the **internal** structure of the value, while entity mapping determines the field name holding that value.

When querying via `MongoTemplate` with domain property paths, `MappingMongoConverter`/`QueryMapper` can translate field names using metadata. With raw driver queries, you must use the exact BSON field names.

### 8.5. Immutable Objects and Constructor Mapping

The `Money` value object is an immutable record. **Invoice** can use mutable fields or constructor binding depending on the Spring Data version. Custom converters pair naturally with immutable value objects because on read they **construct a new `Money` instance** from BSON without needing setters on `Money`.

Never use reflection/`setAccessible` hacks to mutate a `Money` record after construction.

## 9. Querying and Indexing After Adding a Custom Converter

Converters govern how bytes are stored; the MongoDB query engine operates on **actual BSON**, with no knowledge of Java's `Money` domain type.

### 9.1. Filtering by Currency and Amount

In `mongosh`:

~~~javascript
db.invoices.find({
  tenantId: "tenant-a",
  "total.currency": "USD",
  "total.amount": {
    $gte: NumberDecimal("100.00")
  }
});
~~~

This performs a **numeric Decimal128** comparison within a specified currency.

### 9.2. Equivalent Query via MongoTemplate

~~~java
import com.example.billing.persistence.Invoice;
import org.bson.types.Decimal128;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

import java.math.BigDecimal;
import java.util.List;

public final class InvoiceSearch {
    private final MongoTemplate template;

    public InvoiceSearch(MongoTemplate template) {
        this.template = template;
    }

    public List<Invoice> findLargeUsdInvoices(String tenantId) {
        Query query = new Query(
                Criteria.where("tenantId").is(tenantId)
                        .and("total.currency").is("USD")
                        .and("total.amount").gte(
                                new Decimal128(
                                        new BigDecimal("100.00")
                                )
                        )
        );

        return template.find(query, Invoice.class);
    }
}
~~~

This example explicitly constructs a **Decimal128** in `Criteria` so the BSON comparison type is unmistakable. If your project uses property aliases, property value converters, or other conventions, verify **what BSON `QueryMapper` actually emits**.

### 9.3. Appropriate Index

~~~javascript
db.invoices.createIndex({
  tenantId: 1,
  "total.currency": 1,
  "total.amount": 1
});
~~~

For equality predicates on `tenantId` + `currency` followed by a range on `amount`, this compound index is a strong candidate. Still, do not assume optimality across different workloads without checking **`explain`**, index size, write overhead, and cardinality.

### 9.4. Never Compare Amounts Across Different Currencies Directly

~~~javascript
db.invoices.find({
  "total.amount": { $gte: NumberDecimal("100.00") }
});
~~~

A collection-wide query like this is valid BSON, yet **business-wise meaningless** if the data mixes USD, VND, JPY, and other currencies.

Instead:

- Constrain `currency` in the query predicate, or
- Convert amounts to a reporting currency using explicit exchange rates and timestamps in a dedicated pipeline or business process.

Never let a `Money` converter secretly convert currencies on write.

### 9.5. Exact Object Equality vs. Field Range Queries

If you write:

~~~java
Criteria.where("total").is(Money.of("19.90", "USD"));
~~~

Spring Data may invoke the custom converter for the entire query value depending on path and query mapping. However, **embedded BSON document equality** has strict structural and field-order semantics that differ from predicates on individual subfields.

When filtering by amount or currency, prefer explicit predicates on **total.amount** and **total.currency**—especially when the schema might later gain new fields such as **schemaVersion**.

### 9.6. MongoTemplate Updates vs. Raw Driver

Example update via Spring Data:

~~~java
import org.springframework.data.mongodb.core.query.Update;

Update update = new Update()
        .set("total", Money.of("29.90", "USD"));
~~~

Standard Spring Data update paths pass through the mapping converter/`UpdateMapper` to convert domain values. **By contrast**, calling the Java driver directly:

~~~java
mongoTemplate.getCollection("invoices")
        .updateOne(filter, rawUpdateBson);
~~~

uses the native driver API: a manually built raw BSON `Document` **does not automatically run through `Money` mapping rules the way saving an `Invoice` via a repository does**.

In larger codebases, standardize which operations go through Spring Data mapping and which use the raw driver—especially for bulk updates, aggregation pipelines, scripts, and migrations.

### 9.7. Aggregation on Converted Data Types

When storing `Decimal128`, MongoDB aggregations can compute:

~~~javascript
db.invoices.aggregate([
  {
    $match: {
      tenantId: "tenant-a",
      "total.currency": "USD"
    }
  },
  {
    $group: {
      _id: "$total.currency",
      totalAmount: {
        $sum: "$total.amount"
      },
      invoiceCount: {
        $sum: 1
      }
    }
  }
]);
~~~

An aggregation output has its own schema (**_id**, **totalAmount**, **invoiceCount**). The `Money` reading converter does not turn arbitrary aggregation output into an `Invoice`; map results into an appropriate DTO or projection instead.

If `amount` were stored as a `String`, **`$sum`** would not produce the expected numeric sum. That is another reason to get the BSON type right from the start.

### 9.8. Query Optimization After Conversion

Do not conclude a converter "made queries slow" simply because changing the data format invalidated an index. Separate:

1. **Serialization cost** inside the Java process.
2. **Document size and index key size** after conversion.
3. **MongoDB query plan** over BSON values.
4. **Network transfer**.
5. **Result materialization** from `Document` to domain objects.

Measure each layer independently when tuning large systems.

## 10. When @Field(targetType) Suffices Without a Custom Converter

If an entity simply has a **BigDecimal** field and the only goal is storing it as BSON `Decimal128`, a simpler option exists:

~~~java
import java.math.BigDecimal;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

public class ProductPrice {

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal amount;

    // Constructor, getters/setters...
}
~~~

In supported Spring Data MongoDB versions, **@Field(targetType = FieldType.DECIMAL128)** instructs the mapper to use that BSON type for the field.

### 10.1. When to Choose @Field(targetType)

Appropriate when:

- The domain type is already natively supported by Spring Data.
- You only need to specify the **store type**.
- You do not need to combine multiple properties into a custom BSON structure.
- There is no custom parsing/validation outside the domain object.

### 10.2. When to Choose a Custom Converter

Appropriate when:

- The domain uses custom value objects (`Money`, `EmailAddress`, etc.).
- Multiple properties must map into a single storage representation.
- You need a stable storage format distinct from default object mapping.
- You need custom legacy-reading logic or strict type/validation enforcement.

### 10.3. Comparison

| Scenario | Option to Consider |
|---|---|
| `BigDecimal` field → `Decimal128` | **@Field(targetType)** is usually enough. |
| `Money` (`amount` + `currency`) → embedded `Document` | **Custom read/write converter**. |
| REST DTO → entity | DTO mapper/service, not a Mongo converter. |
| JSON response `Money` → string | Jackson serializer, not a Mongo converter. |
| Single field needing special conversion | Property value converter where version-supported. |
| Updating all legacy MongoDB records | Data migration + compatibility reader. |
| Business transaction validation | Domain/service layer, not persistence converter. |

## 11. Converter for a Value Object Stored as a String

Not every value object needs a BSON subdocument.

For instance, **EmailAddress** encapsulates validation/normalization in the domain, yet MongoDB only needs a plain string:

~~~java
public record EmailAddress(String canonical) {
    public EmailAddress {
        if (canonical == null || canonical.isBlank()) {
            throw new IllegalArgumentException("Email is required");
        }
        canonical = canonical.trim();
        // Business validation policy belongs to this type/service.
    }
}
~~~

Writing converter:

~~~java
@WritingConverter
public final class EmailWriteConverter
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.canonical();
    }
}
~~~

Reading converter:

~~~java
@ReadingConverter
public final class EmailReadConverter
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

These classes assume the corresponding imports from **org.springframework.data.convert**, **org.springframework.core.convert.converter**, and the domain package. Register both converters in `MongoCustomConversions` just like the `Money` example.

### 11.1. Why Does String → EmailAddress Need @ReadingConverter?

**String** is a native MongoDB store type. When a converter accepts `String`, the framework needs to know it is used for **reading** from a BSON string into `EmailAddress` to prevent directional ambiguity.

This does **not** mean every `String` field becomes an `EmailAddress`: the target Java property type determines when the conversion applies.

### 11.2. Do Not Try to Convert Every String into a Value Object

A global **String → String** converter to "normalize all fields" is almost always dangerous because it can alter usernames, hashes, IDs, JSON payloads, and unrelated fields.

Keep validation and normalization inside **domain-specific types** or property-specific mapping to bound the blast radius.

### 11.3. Canonicalization Requires a Contract

For example, email case normalization is not simply lowercasing every character in all contexts; domain rules must account for local-part semantics, Unicode/IDN, and real-world policies.

Hence, the `EmailAddress` example only trims whitespace and does not claim to be a full production email parser/normalizer.

## 12. Custom Converter for Stable Business Status Codes

By default, Java enums may be stored using their constant names. If the application renames a constant in code, legacy documents become harder to read.

Suppose a domain requires stable persistence codes:

~~~text
OrderStatus in Java:
  NEW
  CONFIRMED
  CANCELLED

BSON:
  "N"
  "C"
  "X"
~~~

### 12.1. Enum Containing a Business Code

~~~java
package com.example.orders.domain;

public enum OrderStatus {
    NEW("N"),
    CONFIRMED("C"),
    CANCELLED("X");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        for (OrderStatus item : values()) {
            if (item.code.equals(code)) {
                return item;
            }
        }
        throw new IllegalArgumentException(
                "Unknown order status code: " + code
        );
    }
}
~~~

### 12.2. Writer and Reader

~~~java
@WritingConverter
public final class OrderStatusWriteConverter
        implements Converter<OrderStatus, String> {
    @Override
    public String convert(OrderStatus source) {
        return source.code();
    }
}
~~~

~~~java
@ReadingConverter
public final class OrderStatusReadConverter
        implements Converter<String, OrderStatus> {
    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.fromCode(source);
    }
}
~~~

Imports for **Converter**, **@ReadingConverter**, and **@WritingConverter** follow the `Money` example.

### 12.3. Renaming an Enum Constant Does Not Change Stored Data

Suppose Java later renames **CONFIRMED** to **APPROVED**, while the storage code remains **"C"**. The converter preserves backward compatibility as long as the code mapping stays stable:

~~~text
MongoDB "C"
    -> OrderStatus.APPROVED
~~~

That is the goal of a **stable persistent code**. However, never reuse code `"C"` for a different business state, or historical records will be misinterpreted.

### 12.4. Unknown Status: Fail Fast or UNKNOWN?

If the reading converter encounters **"Z"**, your strategies are:

- **Fail fast** and report incompatible data.
- Map to an explicit **UNKNOWN** state if the domain defines one cleanly.
- Quarantine and migrate unrecognized records.

Never silently treat `"Z"` as `NEW` or `CANCELLED` just to keep the application running, as that can trigger incorrect business actions.

## 13. Global Converters vs. Property-Specific Converters

Global custom converters work well when **every `Money` instance must share the same storage format**. Sometimes, however, the same Java type serves multiple distinct storage roles.

For example:

~~~text
Invoice.total:
  Money -> Document(amount Decimal128, currency)

AnalyticsSnapshot.totalNormalized:
  Money -> custom summary form
~~~

Registering two global converters for **Money → Document** creates conflicts and unpredictable selection unless disambiguated.

### 13.1. Property Value Converters

Some Spring Data versions support **PropertyValueConverter** and **@ValueConverter** to bind conversion to a specific property.

Concept:

~~~text
Global:
  Money -> standard BSON object

Field-specific:
  Only AnalyticsSnapshot.totalNormalized
    -> special persisted value format
~~~

The exact interfaces, context types, registries, and constructor signatures for property converters depend on the **Spring Data Commons/MongoDB version**. Check the documentation for your exact version when registering property-scoped converters rather than guessing APIs from another version's snippet.

### 13.2. When to Split into Separate Domain Types?

If two fields carry genuinely different business meanings, two distinct types are often cleaner:

~~~java
record Money(BigDecimal amount, String currencyCode) {}
record ReportingMoney(BigDecimal amount, String reportingCurrency) {}
~~~

This illustrates **type naming separation**, not a suggestion to recreate `Money` without validation. Separate types with distinct invariants make global conversions unambiguous.

### 13.3. @Field(targetType) Is Also Property-Scoped

If one **`BigDecimal amount`** field needs `Decimal128` while other `BigDecimal` fields keep default mapping, **@Field(targetType = FieldType.DECIMAL128)** is cleaner than a global `BigDecimal` → `Decimal128` converter.

Do not change the storage representation of **every `BigDecimal` across all collections** just to fix a single property.

## 14. Converters with Dates, Times, and UUIDs

Time-related business types require clear **timezone and precision policies**, not merely changing Java classes.

### 14.1. Instant and BSON Date

MongoDB BSON Date stores a timestamp as **milliseconds since the Unix epoch (UTC)**. Java **Instant** supports nanosecond precision.

When converting `Instant` to BSON Date, sub-millisecond precision is not preserved. If the domain requires nanosecond precision, design an explicit representation (e.g., storing fractional nanos alongside under a documented schema).

### 14.2. LocalDateTime Carries No Timezone

~~~java
LocalDateTime.of(2026, 11, 14, 9, 30)
~~~

does not represent a unique global instant. To persist it as a UTC timestamp, you must pair it with a **ZoneId** and explicit conversion rules.

A custom converter such as:

~~~text
LocalDateTime -> Date
~~~

that silently uses the server's **system default timezone** will produce different interpretations between development and production, or after deploying to a different cloud region.

### 14.3. Date-Only Domain Types

Birthdays, local booking dates, or delivery dates should often use **LocalDate** with an explicit storage policy, avoiding conversion into a `00:00` UTC `Date` that shifts by a day when read in another timezone.

Spring Data and the JDK already provide built-in time conversions, so avoid writing redundant custom converters before understanding default semantics.

### 14.4. UUID Representation

MongoDB BSON Binary has multiple historical subtypes/UUID representations. Do not arbitrarily write a **`UUID` ↔ `byte[]`** converter when the driver already provides `uuidRepresentation` configuration. When migrating from legacy UUID representations, verify the stored BSON subtype and byte/endian ordering.

A mismatched conversion can persist documents successfully while breaking subsequent ID lookups.

### 14.5. Timezone Conversion Is Not FX Conversion

Timezone handling in persistence must also be deterministic. Never use the current time to interpret a **historical `LocalDateTime`**. When scheduling data must preserve the business timezone, you can store both:

~~~javascript
{
  startsAtUtc: ISODate("2026-11-14T02:30:00Z"),
  zoneId: "Asia/Ho_Chi_Minh"
}
~~~

This illustrates storing both the instant and timezone identifier; the exact contract depends on application needs, DST semantics, and query patterns.

## 15. Nulls, Optional Fields, and Invalid Values

### 15.1. Three Cases to Distinguish

~~~javascript
// A: field missing
{ _id: "A" }

// B: explicit null
{ _id: "B", total: null }

// C: malformed subdocument
{ _id: "C", total: { currency: "USD" } }
~~~

If the domain requires `total` to be non-null:

- Cases A and B are **data contract violations** or legacy states requiring handling.
- Case C is a malformed representation; the reader should fail clearly.

A **`Document` → `Money`** converter only inspects Case C when invoked with a `Document`; Cases A and B may be handled at the property-mapping level without calling the converter.

### 15.2. Never Silently Supply Defaults

Avoid:

~~~java
// Avoid unless explicitly defined by the domain:
if (source.get("amount") == null) {
    return Money.of("0", "USD");
}
~~~

Silent defaults can corrupt financial reporting, tax calculations, or payment totals.

### 15.3. Where Should Validation Live?

| Rule | Appropriate Layer |
|---|---|
| Valid currency code | Domain `Money` constructor. |
| Non-negative amount for certain invoice types | Invoice business invariant / service. |
| BSON `amount` is `Decimal128` | Reading converter. |
| Query accesses only the authorized tenant | Authorization / service / repository query. |
| Currency conversion by historical FX rate | Business service with explicit timestamp/rate. |
| Legacy field migration | Migration job / compatibility reader. |
| HTTP JSON validation | API DTO / validation layer. |

A converter is not a **business transaction validator**. It should not check user permissions, verify account balances, or invoke external systems.

### 15.4. Exceptions Need Diagnostic Context—Without Leaks

When a reader encounters invalid data, report:

~~~text
Expected BSON Decimal128 at total.amount
~~~

Rather than:

~~~text
Failed
~~~

Yet avoid logging full invoices, addresses, or customer details. Log sanitized identifiers, collection name, field path, converter version, and error category in line with security policy.

### 15.5. Fail-Fast in Services with Legacy Data

In mixed-schema environments, failing fast can make older documents unreadable. You can instead:

1. Deploy a reader supporting both formats during the transition window.
2. Migrate legacy data in safe batches.
3. Track the remaining percentage of legacy documents.
4. Remove the compatibility reader only afterward.

Do not leave a tolerant reader enabled indefinitely; it can mask malformed new writes for years.

## 16. Schema Evolution: Changing a Converter Does Not Update Existing Documents

Suppose version 1 stored:

~~~javascript
{
  _id: "INV-OLD",
  total: {
    amount: "19.90",
    currency: "USD"
  }
}
~~~

Version 2 stores:

~~~javascript
{
  _id: "INV-NEW",
  total: {
    amount: NumberDecimal("19.90"),
    currency: "USD"
  }
}
~~~

**Changing `MoneyWriteConverter` in code does not migrate stored documents.** A strict new reader expecting `Decimal128` will fail on `INV-OLD`.

### 16.1. Why Mixed BSON Types Are Dangerous

~~~text
total.amount:
  some documents: BSON String
  others:         BSON Decimal128
~~~

Consequences:

- Numeric range queries like **`$gte: NumberDecimal("100.00")`** do not match string fields as intended.
- Sorting and aggregations behave inconsistently across BSON types.
- Indexes hold heterogeneous key types.
- Strict readers fail on legacy records.
- Older application instances may fail to read newly written records.

Converter rollouts must be managed as **schema migrations**, not mere Java refactors.

### 16.2. Expand → Migrate → Contract

~~~text
Phase 1 — Expand:
  Deploy compatible reader:
    Decimal128 -> Money
    known legacy String -> Money

Phase 2 — New writes:
  Writer emits only Decimal128.
  Monitor invalid/legacy records.

Phase 3 — Migrate:
  Batch convert old String values to Decimal128.
  Use idempotent conditional updates.

Phase 4 — Verify:
  Check remaining legacy types and business queries.

Phase 5 — Contract:
  Remove legacy reader after approval.
~~~

During rolling deployments with multiple running service versions, verify **bidirectional backward compatibility** before switching write formats.

### 16.3. Temporary Compatibility Reader

Replace the strict reader during the migration window with:

~~~java
@ReadingConverter
public final class CompatibleMoneyReadConverter
        implements Converter<Document, Money> {

    @Override
    public Money convert(Document source) {
        Object rawAmount = source.get("amount");
        Object rawCurrency = source.get("currency");

        if (!(rawCurrency instanceof String currency)) {
            throw new IllegalArgumentException(
                    "Invalid total.currency type");
        }

        if (rawAmount instanceof Decimal128 decimal) {
            return new Money(decimal.bigDecimalValue(), currency);
        }

        if (rawAmount instanceof String legacyAmount) {
            return new Money(
                    new BigDecimal(legacyAmount),
                    currency
            );
        }

        throw new IllegalArgumentException(
                "Unsupported total.amount type");
    }
}
~~~

This snippet assumes imports for `Money`, `Document`, `Decimal128`, `BigDecimal`, `Converter`, and `ReadingConverter`.

Accept only **surveyed and approved legacy types**. Do not accept arbitrary BSON `double` or `long` values that silently alter precision. Never register both the strict and compatible readers for the same **`Document` → `Money`** pair expecting the framework to pick predictably.

### 16.4. Counting Documents Still Using the Old Type

In `mongosh` with read permissions:

~~~javascript
db.invoices.countDocuments({
  "total.amount": { $type: "string" }
});
~~~

Check for malformed fields and documents missing `total` as well. Never run bulk production updates without change approval, backups, and I/O/replication capacity planning.

### 16.5. Conditional Migration

A batch worker processes records safely:

~~~text
Read legacy invoice and version
  -> parse String strictly to BigDecimal
  -> validate currency/amount
  -> convert to Decimal128
  -> update with condition on old value/version
  -> record success/failure/skip
  -> retry idempotently
~~~

Example conditional update on a verified document:

~~~javascript
db.invoices.updateOne(
  {
    _id: "INV-OLD",
    "total.amount": "19.90"
  },
  {
    $set: {
      "total.amount": NumberDecimal("19.90")
    }
  }
);
~~~

Filtering on the old value reduces the risk of overwriting concurrent updates. At large scale, migrations require cursors, batching, checkpoints, rate limits, error handling, and a rollback plan.

### 16.6. Schema Version Field

When representations become complex:

~~~javascript
total: {
  schemaVersion: 2,
  amount: NumberDecimal("19.90"),
  currency: "USD"
}
~~~

A version field helps readers dispatch across known formats, though writers, readers, indexes, queries, and migrations must all stay aligned. Earlier examples omitted `schemaVersion` to keep the structure simple.

### 16.7. Rolling Back a Binary Does Not Roll Back BSON

Once writers emit `Decimal128`, older application versions that only understand `String` can fail if you roll back the Java binary.

Plan release ordering carefully:

1. Roll out the compatible reader to all instances first.
2. Enable the new writer only after old readers are gone.
3. Run batched migration/backfill.
4. Verify data and downstream consumers.
5. Remove legacy format support once approved.

Account for consumers using the raw driver, aggregations/reporting, and scripts that bypass `MappingMongoConverter`.

## 17. _class, Type Hints, and Polymorphic Value Objects

Spring Data MongoDB may store **_class** type hints for mapped objects depending on configuration.

~~~javascript
{
  _id: "INV-100",
  _class: "com.example.billing.persistence.Invoice",
  total: {
    amount: NumberDecimal("19.90"),
    currency: "USD"
  }
}
~~~

### 17.1. Custom Converters Own Their Subdocument Schema

When **`MoneyWriteConverter`** manually builds and returns a `Document`, Spring Data no longer applies default field-by-field mapping to `Money` at that step.

~~~text
Default object mapping:
  inspect Money fields and annotations

Custom Money -> Document:
  converter explicitly emits amount and currency
~~~

This keeps the schema stable, while placing responsibility on you to update the converter whenever the persistence contract evolves.

### 17.2. Do Not Rely on Class Names as Business Type Codes

Fully qualified Java class names change during refactoring. Spring Data provides **@TypeAlias** and custom type mappers when needed, yet long-lived business schemas should consider an **explicit stable discriminator**.

For example:

~~~javascript
{
  kind: "CARD",
  version: 1,
  last4: "1234"
}
~~~

When reading **`PaymentMethod`**, the reader branches on **`kind`/`version`** with explicit validation rather than guessing the type from the presence of `last4` or coupling to a Java package name.

### 17.3. Polymorphism Has a Migration Contract

Changing **`kind: "CARD"`** to **`"CREDIT_CARD"`** also requires compatibility handling or migration. Never reuse a previously published discriminator code for a different semantic meaning.

## 18. Converters and Data Security

### 18.1. A Converter Is Not an Authorization Layer

~~~text
Who can read this invoice?
  -> authentication + tenant/owner authorization

How is Money persisted?
  -> MappingMongoConverter and custom converters
~~~

Custom converters must never inspect the authenticated principal to decide whether a record can be read: converters also run in batch/background jobs without request context and never replace query-level tenant scoping.

### 18.2. Never Roll Your Own Encryption

If a value object requires encryption, use vetted cryptography/KMS, authenticated encryption, key/nonce lifecycles, rotation, and recovery planning.

~~~text
Base64 encoding != encryption
XOR with a hardcoded key != secure encryption
String reversal != encryption
~~~

A Spring Data converter cannot turn a weak algorithm into a security control.

### 18.3. Log Conversion Errors Safely

Log fields such as:

~~~text
collection=invoices
field=total.amount
error=BSON_TYPE_MISMATCH
schemaVersion=unknown
traceId=...
~~~

Never log raw invoices, email addresses, account numbers, or BSON documents containing sensitive data. Use sanitized identifiers and correlation IDs per policy.

### 18.4. Pure Conversions and Intentional Exceptions

Converters that make network calls or depend on random clocks are difficult to retry, hard to test, and produce non-deterministic results. If encryption requires randomness or nonces, treat that as a carefully engineered exception—never sprinkle arbitrary side effects into persistence conversions.

## 19. Multi-Level Testing for Custom Converters

Because converters sit at the boundary between domain and BSON, tests must verify both **value round-trips** and **stored BSON**. Unit tests calling both converters directly do not prove the Spring context actually registered them.

### 19.1. Unit Test: Money → Document → Money

Example with JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.billing.domain.Money;
import com.example.billing.persistence.MoneyReadConverter;
import com.example.billing.persistence.MoneyWriteConverter;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

public class MoneyConverterTest {

    private final MoneyWriteConverter writer =
            new MoneyWriteConverter();
    private final MoneyReadConverter reader =
            new MoneyReadConverter();

    @Test
    void shouldRoundTripAmountAndCurrency() {
        Money original = Money.of("19.90", "usd");

        Document bson = writer.convert(original);
        Money restored = reader.convert(bson);

        assertEquals("USD", restored.currencyCode());
        assertEquals(0,
                original.amount().compareTo(restored.amount()));
        assertEquals(original, restored);
    }

    @Test
    void shouldStoreAmountAsDecimal128() {
        Document bson = writer.convert(
                Money.of("19.90", "USD"));

        assertInstanceOf(
                Decimal128.class,
                bson.get("amount"));
        assertEquals("USD", bson.getString("currency"));
    }

    @Test
    void shouldRejectUnsupportedBsonType() {
        Document legacy = new Document(
                "amount", "19.90")
                .append("currency", "USD");

        assertThrows(
                IllegalArgumentException.class,
                () -> reader.convert(legacy));
    }

    @Test
    void shouldKeepSmallDecimalExact() {
        Money money = new Money(
                new BigDecimal("0.00000001"), "USD");

        Money restored = reader.convert(writer.convert(money));

        assertEquals(0,
                new BigDecimal("0.00000001")
                        .compareTo(restored.amount()));
    }
}
~~~

These tests verify:

- Amounts do not pass through `double`.
- Currency codes are normalized.
- BSON type is strictly `Decimal128`.
- Strict reader rejects legacy `String`.
- Decimal values round-trip accurately.

**Note:** scale/equality policy must be confirmed per domain. Assertions using `compareTo()` check numeric equality, whereas `Object.equals()` on `Money` also reflects `BigDecimal` scale.

### 19.2. Recommended Negative Cases

| Input | Expected Behavior |
|---|---|
| Null amount | Rejected during domain construction. |
| Null/blank currency | Rejected during domain construction. |
| Invalid ISO currency code | Rejected during domain construction. |
| String BSON `amount` in strict reader | Conversion error. |
| Missing BSON `amount` | Conversion error. |
| Missing BSON `currency` | Conversion error. |
| Amount unrepresentable as `Decimal128` | Writer fails explicitly without silent rounding. |
| Null embedded `total` field | Handled by mapping/service null policy. |
| Unknown `schemaVersion` | Reject or apply explicit compatibility policy. |

Negative amounts or varying scales are not inherently invalid—they depend on defined business invariants. Avoid testing domain rules that do not exist.

### 19.3. Integration Test: Persisting and Loading via MongoTemplate

**@DataMongoTest** creates a Spring Data MongoDB test slice (per Spring Boot version). Configure an isolated MongoDB test instance (such as Testcontainers or a controlled test service).

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.billing.config.MongoConversionConfiguration;
import com.example.billing.domain.Money;
import com.example.billing.persistence.Invoice;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
@Import(MongoConversionConfiguration.class)
public class InvoiceMongoMappingTest {

    @Autowired
    private MongoTemplate template;

    @Test
    void shouldPersistAndLoadMoney() {
        Invoice invoice = new Invoice(
                "INV-TEST-100",
                "tenant-test",
                "C-TEST",
                Money.of("19.90", "USD")
        );

        template.save(invoice);

        Document raw = template.getCollection("invoices")
                .find(new Document("_id", "INV-TEST-100"))
                .first();

        assertNotNull(raw);

        Document total = raw.get("total", Document.class);
        assertNotNull(total);
        assertInstanceOf(
                Decimal128.class,
                total.get("amount"));

        Invoice restored = template.findById(
                "INV-TEST-100", Invoice.class);
        assertNotNull(restored);
        assertEquals(invoice.getTotal(), restored.getTotal());
    }
}
~~~

In this example, **raw `getCollection()`** is used intentionally to inspect the exact BSON stored in the database without passing through `MappingMongoConverter` on read.

### 19.4. Test Context Must Use the Right Registry

A test with converter classes on the classpath that forgets to import or configure **MongoCustomConversions** may not apply the converters used in production.

Check:

- Did the Spring context load `MongoConversionConfiguration`?
- Are there manually constructed `MongoTemplate`/`MappingMongoConverter` beans?
- Are multiple MongoDB connections/databases configured where only one registers the converters?
- Does the repository use the same mapping context?

If the test runs yet `amount` is stored as a string instead of `Decimal128`, investigate the **mapping configuration** rather than assuming the `MoneyWriteConverter` unit test guarantees integration behavior.

### 19.5. Testing Queries and Index Behavior

An integration test should:

1. Seed invoices with `19.90`, `100.00`, and `120.00` in USD.
2. Seed an invoice with `1.000` in VND.
3. Query for USD `amount >= 100.00`.
4. Assert only matching USD invoices are returned.
5. Inspect `explain` on a representative dataset to evaluate index usage.

Testing queries against nested BSON fields catches regressions where `amount` flips from `Decimal128` to `String`, which domain-only unit tests miss.

### 19.6. Testing Schema Migration

A migration integration test:

~~~text
Seed old BSON String amount.
Deploy compatibility reader.
Read old amount into Money.
Write back with new converter.
Check raw BSON amount is Decimal128.
Run business query.
Verify amount/currency values were preserved.
~~~

Never test only fresh writes; production typically holds years of historical data.

### 19.7. Testing Precision and Boundary Values

Test a range of amounts:

~~~text
0
0.01
19.90
-1.50 (if permitted by domain)
12345678901234567890.1234
0.00000000000000000001
value beyond Decimal128 precision/range
~~~

Out-of-range values must yield an explicit error or follow an intentional policy—never a silent fallback to `double`.

### 19.8. Testing Side Effects and Thread-Safety

If a converter holds mutable state such as:

~~~java
private String lastCurrency;
~~~

concurrent requests will corrupt one another. Shared converters must be **stateless**, especially when Spring services load records in parallel.

Unit tests can exercise concurrent calls against a single converter instance to catch shared mutable state—though you should **never add mutable state** just for testing.

## 20. Performance When Custom Conversions Apply to Many Documents

A query:

~~~text
Find 10,000 invoices
   -> map 10,000 BSON documents
   -> instantiate 10,000 Money objects
   -> create BigDecimal objects
~~~

Converter overhead is usually small relative to network and disk I/O for moderate queries, yet at high throughput or with many value objects per document, object allocations and GC pressure can become noticeable.

### 20.1. Avoid Expensive Parsing on Every Record

Never do this:

~~~text
Every MoneyReadConverter call:
  read configuration from disk
  open network connection
  compile regex and complex parser
  fetch exchange rate
~~~

Expensive lookups and business dependencies do not belong inside converters. Lightweight domain validation, BSON type checks, and primitive transformations are appropriate.

### 20.2. Use Projections to Avoid Materializing Unneeded Fields

If an API only needs invoice ID and status, there is no reason to deserialize `Money` and nested items across millions of documents:

~~~javascript
db.invoices.find(
  { tenantId: "tenant-a" },
  { _id: 1, status: 1 }
);
~~~

In Spring Data, use projections or DTO queries. This reduces network payload and object-mapping work. **Do not project `total.amount` while omitting `currency`** if the target DTO or domain still expects a complete `Money` value object.

### 20.3. Filter Before Materializing

~~~text
MongoDB $match / indexed query
    -> fewer BSON documents over network
    -> fewer Java objects and custom conversions
~~~

Custom converters do not replace proper index, filter, and sort design. Performing a full collection scan that streams millions of documents into Java only to filter in memory is far slower than pushing predicates down to MongoDB.

### 20.4. Measure Serialization Overhead Separately

When latency increases after adding a converter, isolate each component:

| Component | How to Investigate |
|---|---|
| Database query time | `explain` and MongoDB metrics. |
| Network transfer | Bytes returned, RTT, routing. |
| Mapping converter CPU | Java profiler / JFR. |
| Object allocations / GC | JFR, allocation and GC metrics. |
| Index / data size | `$collStats`, `$indexStats`. |
| Application request latency | Traces / Micrometer. |

Do not prematurely optimize converters with mutable object pools when the real bottleneck is a `COLLSCAN` query.

### 20.5. Bulk Writes and Converters

Spring Data bulk operations have API-specific mapping behavior. Some raw or BSON-oriented bulk operations bypass the entity conversion pipeline.

Before shipping bulk ingestion to production:

- Inspect stored BSON types on sample documents.
- Confirm `amount` and `currency` representations match expectations.
- Ensure records do not bypass required domain validation.
- Test error handling, retries, and idempotency.

### 20.6. Reactive MongoDB

In **ReactiveMongoTemplate/ReactiveMongoRepository** applications, custom conversion remains synchronous data mapping—**never block reactive threads** with network or filesystem I/O inside a converter.

A synchronous, stateless, I/O-free converter works cleanly in reactive pipelines. If conversion genuinely requires async I/O, perform that step in the reactive business pipeline rather than turning `convert()` into a blocking operation.

### 20.7. Index Footprint of Representations

`Money` stored as an embedded `Document`:

~~~javascript
{ amount: NumberDecimal("19.90"), currency: "USD" }
~~~

has a different storage footprint from:

~~~javascript
{ minorUnits: NumberLong("1990"), currency: "USD" }
~~~

and from:

~~~javascript
{ amount: "19.90 USD" }
~~~

Choose the representation for correctness and query semantics first, then benchmark actual index bytes, compression, and write cost. Never switch representations merely to shave a few bytes off a sample document if it breaks numeric queries.

## 21. Common Pitfalls and How to Diagnose Them

### 21.1. Writing a Converter but Forgetting to Register It

Symptom:

~~~text
Unit test MoneyWriteConverter succeeds
MongoRepository.save() stores an unexpected structure
~~~

Likely cause: **MongoCustomConversions is not wired into the `MappingMongoConverter` actually in use**.

How to verify:

1. Check whether the configuration class is component-scanned or imported.
2. Check if multiple custom `MongoTemplate` or client beans exist.
3. Confirm both converters are registered in `MongoCustomConversions`.
4. Add an integration test verifying raw BSON readback.

### 21.2. Declaring Only @WritingConverter

If the writer emits:

~~~javascript
total: {
  amount: NumberDecimal("19.90"),
  currency: "USD"
}
~~~

without a matching reader, Spring Data may fall back to default object mapping or fail depending on domain types and constructors. Always design **both directions** explicitly for custom formats.

### 21.3. Declaring Only @ReadingConverter

The reader handles `Document` → `Money` properly, while the default writer persists `amount` using default mapping. Newly written records then diverge from older records.

**Never test only the read path** and assume the persistence contract is complete.

### 21.4. Mixing BigDecimal, Decimal128, double, and String

MongoDB supports multiple numeric and string types, so a `Money` schema must specify the exact accepted type.

~~~text
amount: NumberDecimal("19.90")  -> intended
amount: "19.90"                 -> legacy string
amount: 19.9                    -> floating double representation
amount: NumberLong("1990")      -> maybe minorUnits, not 19.90
~~~

Printed output may look similar while **semantics differ completely**. Never blindly read `NumberLong(1990)` as `1990.00 USD` if legacy data actually encoded `1990` minor units.

### 21.5. Calling BigDecimal.doubleValue() Inside the Writer

~~~java
// Anti-pattern: loss of decimal precision.
new Document("amount", money.amount().doubleValue());
~~~

When the schema specifies `Decimal128`, use **`new Decimal128(BigDecimal)`** with explicit validation and failure handling.

### 21.6. Embedding FX or Tax Rules Inside a Converter

~~~text
On read:
  fetch current FX rate
  convert USD to VND
~~~

Reading the same document today and next week would return different monetary amounts. Currency conversion is a business operation requiring explicit **rate, timestamp, and source**, not persistence conversion.

### 21.7. Registering Two Converters for the Same Type Pair

~~~text
Money -> Document, implementation A
Money -> Document, implementation B
~~~

Without clear disambiguation or property scoping, selection becomes unpredictable and error-prone. Use one canonical persistence contract or property-specific converters where supported.

### 21.8. Reading Request Context from ThreadLocal Inside a Converter

~~~text
MoneyWriteConverter reads currentTenant from ThreadLocal
~~~

Background jobs, async tasks, and reactive pipelines often lack that thread context. Never inject `tenantId` or ownership via `ThreadLocal` in a converter; the entity/service must pass verified metadata explicitly.

### 21.9. Omitting @ReadingConverter/@WritingConverter

When source or target involves native BSON or simple types, Spring Data may struggle to determine conversion direction. Explicit annotations clarify intent and prevent unintended side-effect conversions.

### 21.10. Using the Raw Driver and Expecting Custom Converters to Run

~~~java
mongoTemplate.getCollection("invoices")
        .insertOne(rawDocument);
~~~

Here you pass a raw BSON `Document` straight to the MongoDB driver. **`MoneyWriteConverter` does not automatically transform `rawDocument`.** When a codebase mixes repositories and raw driver calls, enforce strict shared conventions for BSON types.

### 21.11. Forgetting BSON Field Names Changed via @Field

If the entity declares:

~~~java
@Field(name = "total_value")
private Money total;
~~~

raw MongoDB queries must target **total_value.amount**, not **total.amount**. Spring Data mapped paths translate through `QueryMapper`, whereas raw scripts and queries run against actual stored names.

### 21.12. Forgetting Migration When Updating a Converter

Deploying a new writer does not update legacy records. Production may hold both `String` and `Decimal128` simultaneously. Plan rollouts, legacy readers, and data migrations.

### 21.13. Treating Missing Fields as Zero

A missing `total.amount` may indicate data corruption or an incomplete business state. Returning `0` without a domain rule distorts revenue and audit trails.

### 21.14. Projecting Without Currency

~~~javascript
db.invoices.find(
  {},
  { "total.amount": 1 }
);
~~~

If mapped back into a full `Invoice` with `Money`, the missing `currency` causes the reader to fail constructing the value object. Use an appropriate DTO or projection rather than forcing an incomplete subdocument into `Money`.

### 21.15. Using toString() to Persist Domain Values

~~~java
money.toString()
~~~

produces output like **`Money[amount=19.90, currencyCode=USD]`**, which is not a stable storage schema. `toString()` is for debugging, not persistence contracts.

### 21.16. Locale-Dependent Number Formatting

~~~text
"1,234.56"
"1.234,56"
~~~

These are display conventions. Stored BSON amounts must never depend on server locale. Use `Decimal128` or an explicit canonical decimal representation.

### 21.17. Silently Altering BigDecimal Scale

If a converter calls `stripTrailingZeros()` or arbitrary `setScale()` rounding, round-trips alter representation; for domains requiring exact scale, that is a breaking change.

### 21.18. Ignoring Decimal128 Out-of-Range Values

`BigDecimal` can hold values beyond `Decimal128` limits. If the writer throws an exception in production, the service must return a controlled error and never report the save as successful.

### 21.19. _class and Package Refactoring

Never assume a fully qualified Java class name is an immutable business identifier. Use type aliases or explicit stable discriminator codes for polymorphism.

### 21.20. Slow Converters Due to Network or I/O

A database read returning 10,000 documents invokes the converter 10,000 times. Network calls inside `convert()` multiply latency and violate threading assumptions. Keep converters local, fast, and deterministic.

### 21.21. Testing Only Happy-Path Values

Testing only **`19.90 USD`** misses:

- Very large and very small amounts.
- Precision boundaries.
- Unusual currency codes.
- Missing or null fields.
- Legacy records.
- Range queries and sorts.
- Value objects nested inside collections or lists.

### 21.22. Confusing Converters with JSON Serializers

Spring Data converters may store the desired BSON in MongoDB while Jackson still serializes `Money` as a JSON object in REST responses. To customize the HTTP JSON contract, configure Jackson serializers or DTO mapping separately.

### 21.23. Changing Index Field Types Without Re-Evaluating Queries

Switching `amount` from `String` to `Decimal128` changes range comparison behavior and leaves mixed types in old indexes. Migrate data, inspect `explain`, and verify index behavior rather than tweaking index hints blindly.

### 21.24. Neglecting Backups and Rollback Planning

Before migrating millions of invoices, establish backups, recovery procedures, and audit logging. Rolling back application code never automatically undoes a committed BSON migration.

## 22. Decision Table for Value Object Persistence Design

| Question | If Yes | Direction to Consider |
|---|---|---|
| Does the Java type map naturally already? | Yes | Prefer default mapping. |
| Only need `BigDecimal` → `Decimal128` on one field? | Yes | `@Field(targetType)`. |
| Need a specific multi-field BSON layout for a value object? | Yes | Bidirectional custom converters. |
| Only one property needs a format different from other properties of the same type? | Yes | `PropertyValueConverter` / version-specific support. |
| Only the HTTP API needs a different output format? | Yes | DTO / Jackson serializer. |
| Does legacy data exist in an older format? | Yes | Compatibility reader + migration. |
| Does conversion depend on FX rates, secrets, or current time? | Yes | Separate business/crypto workflow, not a pure converter. |
| Need numeric sorting or filtering in MongoDB? | Yes | Choose an appropriate BSON numeric type. |
| Need stable enum persistence codes? | Yes | Domain code converter or explicit mapping. |
| Need polymorphism? | Yes | Migratable discriminator + version schema. |
| Only need to rename a property? | Yes | `@Field(name=...)`. |
| Need to reshape the entire collection's schema? | Yes | Data migration and coordinated release. |

### 22.1. Converter Design Workflow

~~~text
Identify business invariant
          |
          v
Define Java domain type
          |
          v
Choose BSON contract + example document
          |
          v
Check built-in mapping / @Field support
          |
          v
If needed, implement WritingConverter
          |
          v
Implement ReadingConverter + error policy
          |
          v
Register in MongoCustomConversions
          |
          v
Unit round-trip + integration raw BSON
          |
          v
Query/index compatibility test
          |
          v
Migration/rollout plan if stored data exists
          |
          v
Monitor conversion failures and performance
~~~

### 22.2. Decisions That Must Be Documented

For every custom converter, document:

- Domain type and structure.
- BSON storage types, fields, and sample document.
- Null, missing, and malformed field policies.
- Numeric precision and rounding policy.
- Schema version and backward compatibility rules.
- Read/write directions and registration scope.
- Query and index semantics.
- Migration and rollback strategy.
- Error handling and observability.
- Data contract owner.

Even a short converter without a documented data contract can cause lingering failures when multiple microservices share the same collection.

## 23. Lab: Practicing on a Test MongoDB Database

Practice strictly against an **isolated test database**. These steps let you inspect stored schemas without touching production.

### 23.1. Setup

1. Create a Spring Boot project with the **`spring-boot-starter-data-mongodb`** dependency matching your Boot version.
2. Use Java 17+ for the `Money` record example.
3. Connect to an authorized test MongoDB instance.
4. Create `Money`, `MoneyWriteConverter`, and `MoneyReadConverter`.
5. Register the `MongoCustomConversions` bean.
6. Create the `Invoice` entity and `InvoiceRepository`.

Never hardcode production credentials. Use appropriate application configuration or secret injection.

### 23.2. Save an Invoice

~~~java
repository.save(new Invoice(
        "INV-LAB-001",
        "tenant-lab",
        "customer-lab",
        Money.of("125.75", "USD")
));
~~~

### 23.3. Inspect Raw BSON in mongosh

~~~javascript
use billing_lab

db.invoices.findOne({ _id: "INV-LAB-001" });
~~~

Expected **`total`** shape:

~~~javascript
{
  amount: NumberDecimal("125.75"),
  currency: "USD"
}
~~~

Entity mapping may also store `_class` depending on configuration. If `amount` appears as a `String`, inspect the registry, domain converter, and `MongoTemplate` configuration.

### 23.4. Read Back the Domain Object

~~~java
Invoice invoice = repository
        .findById("INV-LAB-001")
        .orElseThrow();

System.out.println(invoice.getTotal().amount());
System.out.println(invoice.getTotal().currencyCode());
~~~

Expected output: amount equal to `125.75` and currency `USD`.

### 23.5. Add Another Amount for Querying

~~~java
repository.save(new Invoice(
        "INV-LAB-002",
        "tenant-lab",
        "customer-lab",
        Money.of("300.00", "USD")
));
~~~

Run:

~~~javascript
db.invoices.find({
  tenantId: "tenant-lab",
  "total.currency": "USD",
  "total.amount": { $gte: NumberDecimal("200.00") }
});
~~~

Expected result: returns `INV-LAB-002`, not `INV-LAB-001`.

### 23.6. Test Legacy Data in the Test Database

~~~javascript
db.invoices.insertOne({
  _id: "INV-LAB-LEGACY",
  tenantId: "tenant-lab",
  customerId: "customer-lab",
  total: {
    amount: "19.90",
    currency: "USD"
  }
});
~~~

The strict reader in this lesson rejects the string `amount`. This lets you observe the **schema migration problem** directly and test a compatibility reader in an isolated environment.

### 23.7. Observe Integration Test Layers

Keep this distinction clear:

~~~text
repository.findById(...)
  -> BSON converted to Invoice/Money

mongoTemplate.getCollection("invoices").find(...)
  -> raw BSON Document via MongoDB driver
~~~

These two calls return different Java types because they traverse different mapping layers.

### 23.8. Verify Index Behavior

~~~javascript
db.invoices.createIndex({
  tenantId: 1,
  "total.currency": 1,
  "total.amount": 1
});

db.invoices.find({
  tenantId: "tenant-lab",
  "total.currency": "USD",
  "total.amount": { $gte: NumberDecimal("100.00") }
}).explain("executionStats");
~~~

With only a few lab documents, the planner may still choose `COLLSCAN`. **Never treat tiny lab execution times as production benchmarks.**

### 23.9. Cleanup

When finished, clean up **only the test database you own** according to environment policy. Never run `dropDatabase` on production or someone else's shared database.

## 24. Practice Exercises

### Exercise 1 — Redraw the Conversion Pipeline

Draw the flow **Invoice → MongoRepository → MappingMongoConverter → MoneyWriteConverter → Document → MongoDB**, along with the corresponding read path. Explain at which step the application domain type becomes BSON.

### Exercise 2 — Value Object Design

Write a record **`Money(BigDecimal amount, String currencyCode)`**. Normalize `currencyCode` and reject nulls. Discuss why `double` should not be used.

### Exercise 3 — BSON Contract

Define the exact BSON document for `Money` `19.90 USD`. Explicitly specify that `amount` must be **Decimal128** (not `String` or `double`) and `currency` is an ISO code.

### Exercise 4 — WritingConverter

Write **`Converter<Money, Document>`** with `@WritingConverter`. Convert `amount` to `Decimal128` and `currencyCode` to `String`.

### Exercise 5 — ReadingConverter

Write **`Converter<Document, Money>`** with `@ReadingConverter`. The reader must reject documents where `amount` is not `Decimal128` or `currency` is not `String`.

### Exercise 6 — MongoCustomConversions

Create a `@Configuration` bean registering both `Money` converters. Explain why simply placing annotations on the converter classes does not guarantee the registry includes them.

### Exercise 7 — Invoice Entity

Write an `Invoice` entity with **id, tenantId, customerId, Money total** and use `MongoRepository`. Explain how the `total` field is stored.

### Exercise 8 — Inspect Raw BSON

After `repository.save(invoice)`, use the raw driver collection or `mongosh` to inspect **total.amount**. How can you prove the database actually stored BSON `Decimal128`?

### Exercise 9 — @Field(targetType)

An entity only has a **`BigDecimal amount`** field and needs to store `Decimal128`. Write a solution using **`@Field(targetType = FieldType.DECIMAL128)`** and explain when a custom converter is unnecessary.

### Exercise 10 — Numeric Queries

Write a `MongoTemplate` `Query` fetching invoices for `tenant-a`, currency `USD`, and `amount >= 100.00`. Explain why the predicate must constrain `currency`.

### Exercise 11 — Compound Index

Design an index supporting the query in Exercise 10. Run `explain` on representative data and identify the `keys`/`docs` examined metrics to watch.

### Exercise 12 — Numeric Aggregation

Write an aggregation summing USD invoice amounts per tenant. Why must USD, EUR, and VND never be summed together without conversion?

### Exercise 13 — Legacy Strings

Some legacy documents contain **`total.amount: "19.90"`**. What happens with this lesson's strict reader? Propose a phased migration to avoid a breaking rollout.

### Exercise 14 — Compatibility Reader

Write a reader that accepts **`Decimal128`** and valid **decimal strings**, while rejecting `double` and unknown types. Test it with malformed inputs.

### Exercise 15 — Conditional Migration Update

Design an `updateOne` that converts string `amount` to `Decimal128` only if the document still holds the old value. Why does filtering on the old value help prevent concurrent overwrites?

### Exercise 16 — Versioned Schema

Add **`schemaVersion: 2`** to `total`. What changes are needed in the writer, reader, legacy migration, and any queries using embedded document equality?

### Exercise 17 — Enum Status Codes

Write a **`PaymentState`** enum with stable codes: `NEW="N"`, `PAID="P"`, `FAILED="F"`. Build reading and writing converters between the enum and BSON `String`.

### Exercise 18 — Unknown Enum Codes

The reader encounters code **`"Z"`**, which is absent from the enum. Compare fail-fast vs. `UNKNOWN`. When can a fallback strategy hide business errors?

### Exercise 19 — EmailAddress

Build an `EmailAddress` domain type with appropriate validation and `EmailAddress` ↔ `String` converters. Why is `@ReadingConverter` needed to clarify the `String` → `EmailAddress` direction?

### Exercise 20 — Two Properties of the Same Java Type

Two `Money` fields require different storage formats. Would you use a global converter, a property-specific converter, or separate domain types? Justify based on business meaning.

### Exercise 21 — Round-Trip Test

Write a JUnit test:

~~~text
Money("19.90","USD")
    -> write()
    -> Document with Decimal128
    -> read()
    -> equal Money
~~~

Verify amount, currency, and BSON type—not just string output.

### Exercise 22 — Null and Missing Fields

Evaluate three documents:

~~~javascript
{ _id: "A" }
{ _id: "B", total: null }
{ _id: "C", total: { currency: "USD" } }
~~~

In which case(s) is the converter invoked? What domain policy should apply when `total` is mandatory?

### Exercise 23 — Decimal128 Overflow

A `BigDecimal` has greater precision/range than `Decimal128` supports. When the writer cannot represent it, how should you handle it? Why must you never fall back to `double`?

### Exercise 24 — Mixed BSON Queries

A collection has `amount` stored as both `String` and `Decimal128`. What happens during numeric range queries? Describe a test that catches this bug.

### Exercise 25 — JSON Differing from BSON

An API wants to return:

~~~json
{"total":"19.90 USD"}
~~~

while MongoDB stores an embedded document. Should you use a MongoDB converter or a DTO/Jackson serializer for JSON output? Explain.

### Exercise 26 — Java String _id

With `@Id String`, how can a string formatted like an `ObjectId` hex differ from `"INV-100"`? When do you need `@MongoId(FieldType.STRING)`?

### Exercise 27 — Polymorphic Payment Method

Design BSON formats for `CardPayment` and `BankTransfer` with stable **`kind`** and **`schemaVersion`** fields. Propose how the reader handles an unknown `kind`.

### Exercise 28 — LocalDateTime and Timezones

If a converter uses the system default timezone to write `LocalDateTime` as a BSON Date, what can break when deploying to another region? Propose a representation with explicit zone/UTC semantics.

### Exercise 29 — Legacy UUIDs

A database stores UUIDs using an older binary representation. Why can a custom `UUID` ↔ `byte[]` converter that ignores subtype/representation break lookups?

### Exercise 30 — Raw Driver Bypass

A batch job executes **`mongoTemplate.getCollection().insertOne(rawDocument)`**. Should you expect `MoneyWriteConverter` to run automatically? Design a convention keeping batch and repository writes aligned on the same BSON contract.

### Exercise 31 — Partial Projection

A projection selects only **`total.amount`** and attempts to map into `Invoice` with `Money`. What can go wrong when `currency` is missing? Propose an appropriate DTO or projection.

### Exercise 32 — Property Rename

The entity changes **`total`** to **`@Field("total_value")`**. Write the matching MongoDB query and contrast raw BSON paths with Java property paths.

### Exercise 33 — Conversion Performance

A `find` returns 500,000 invoices. Which costs belong to MongoDB query execution, network transfer, Java mapping, `BigDecimal` allocation, and GC? Design a measurement plan per layer.

### Exercise 34 — Reactive Conversion

A reactive service places a REST call to fetch FX rates inside `Converter.convert()`. Why is this blocking and hard to retry? Propose separating it into the business workflow.

### Exercise 35 — Security Boundaries

The `Money` converter normalizes currencies. Is that enough to stop tenant A from reading tenant B's invoices? What controls must be added at the service, query, and API layers?

### Exercise 36 — Integration Test

Write a Spring Data MongoDB integration test that saves an `Invoice` via `MongoTemplate`, reads the raw `Document` via `getCollection`, asserts `total.amount` is `Decimal128`, and calls `findById` to verify round-trip behavior.

### Exercise 37 — Rollback

A new app version writes `Decimal128`, while the previous version only reads `String`. Outline a deployment sequence and rollback plan that keeps older instances from failing.

### Exercise 38 — Converter Registration Conflict

Two different `MongoCustomConversions` beans are created by separate configuration modules. How do you ensure all required converters are registered on the active `MappingMongoConverter`?

### Exercise 39 — Format Changes and Indexes

A service changes `amount` from string to `Decimal128`. Beyond converter unit tests, which queries, indexes, and aggregations must be evaluated?

### Exercise 40 — Write a Persistence Design Note

Draft a persistence design note for a business value object of your choice (`Money`, `PhoneNumber`, `BookingPeriod`) covering:

~~~text
Domain invariants and Java type
Raw BSON format with types
Reading/Writing conversion
Spring registration scope
Query and index requirements
Null/invalid/legacy handling
Migration and rollback plan
Unit + integration tests
Performance and security concerns
~~~

A strong design must demonstrate **accurate bidirectional reads and writes, meaningful BSON-level queries, and zero breakage of existing data**.

## 25. Review Questions

1. What role does **MappingMongoConverter** play between `MongoRepository` and the MongoDB Driver?
2. What is **MongoCustomConversions**?
3. When is default object mapping sufficient without a custom converter?
4. Distinguish a writing converter from a reading converter.
5. Why are **@WritingConverter** and **@ReadingConverter** important when a converter involves native/simple types?
6. How does **`org.bson.Document`** differ from an **`@Document`** entity?
7. Why does `Money` typically use `BigDecimal` rather than `double`?
8. Does BSON `Decimal128` have precision and exponent limits?
9. Why should a domain `Money` type include `currencyCode`?
10. What are the trade-offs between `Decimal128`+currency and `minorUnits`+currency?
11. Why should you avoid storing `"19.90 USD"` as a string if numeric range queries are needed?
12. Which BSON fields does this lesson's `MoneyWriteConverter` produce?
13. What does `MoneyReadConverter` do if `amount` is a `String` in strict mode?
14. Through what mechanism are converters wired into `MongoTemplate` and `MongoRepository`?
15. Does simply adding `@Component` to a converter guarantee `MongoCustomConversions` picks it up?
16. What happens if an app defines a custom `MongoTemplate` that does not use the configured registry?
17. What is the difference between **@Field(targetType=DECIMAL128)** and a custom `Money` converter?
18. When should you use property-specific conversion instead of global conversion?
19. Why shouldn't you register multiple converters for the same `Money` → `Document` pair without a selection rule?
20. When `@Field` renames `total` to `total_value`, what is the raw BSON query path?
21. Why doesn't a `Money` converter automatically change REST API JSON serialization?
22. Why must queries on `total.amount` account for `currency`?
23. Why do embedded BSON equality and predicates on nested fields have different semantics?
24. True or false: MongoDB's **`$sum`** aggregation operates on BSON numeric amounts rather than Java `Money` objects directly.
25. Does a raw MongoDB Java Driver `insertOne` automatically invoke Spring converters?
26. What must you verify when using Spring Data `Update.set` with a domain value?
27. Which invariants should the domain constructor validate?
28. Should a converter fetch live FX rates or current timestamps when persisting money?
29. Why should converters remain stateless and thread-safe?
30. How do null `total`, missing `total`, and malformed `total` differ?
31. Should a reader silently replace a missing `amount` with zero?
32. Why must data migration accompany writer/reader changes?
33. What risks does Expand → Migrate → Contract mitigate?
34. How do mixed BSON `String` and `Decimal128` values affect queries and indexes?
35. When rolling out a new writer, why might older application instances fail to read newly written data?
36. How does a `schemaVersion` field help manage conversion evolution?
37. How does a stable type discriminator differ from Java's `_class` name?
38. Why does a local date-time require a timezone policy when persisted as BSON Date?
39. Does MongoDB BSON Date preserve nanosecond precision like `Instant`?
40. Why must UUID binary representation be explicitly specified during migrations?
41. How should an integration test verify raw BSON types?
42. Does a passing converter unit test prove the Spring context registered the converter properly?
43. Why test `Decimal128` boundaries, malformed fields, and legacy formats?
44. How can a projection omitting `currency` cause the `Money` reader to fail?
45. Is a converter the right place to enforce tenant authorization?
46. Should a reactive converter make blocking REST calls?
47. Which metrics separate DB query cost from Java conversion cost?
48. Why evaluate index/storage overhead when changing the `Money` representation?
49. When must backups and schema rollback plans be considered?
50. Beyond converter code, what else makes up a reliable persistence contract?

## 26. Custom Converter Implementation Checklist

### 26.1. Domain Design

- [ ] The domain type represents a meaningful business concept rather than an unnecessary wrapper.
- [ ] Invariants are clearly documented and validated.
- [ ] Numeric precision, scale, and currency policies are defined upfront.
- [ ] The domain type has no dependency on BSON/driver classes without compelling justification.
- [ ] Immutable values are never silently mutated inside converters.

### 26.2. Storage Schema Design

- [ ] Sample BSON document and explicit **data types** for every field are documented.
- [ ] Naming conventions and versioning policy are defined.
- [ ] Policies for null, missing, and malformed fields are clear.
- [ ] Query, sort, and index requirements are validated against actual BSON types.
- [ ] Strings are not used in place of numeric types when arithmetic or range queries are needed.
- [ ] Built-in mapping and `@Field(targetType)` were evaluated first.

### 26.3. Converter Implementation

- [ ] `WritingConverter` emits the exact intended store type.
- [ ] `ReadingConverter` builds the domain type cleanly and rejects unknown types per policy.
- [ ] No silent rounding or lossy conversions.
- [ ] No I/O, network calls, or FX calculations inside `convert()`.
- [ ] No mutable shared state or request-context dependencies.
- [ ] Directional annotations are applied where needed.
- [ ] Registration scope is clear with no competing duplicate converters.

### 26.4. Spring Configuration

- [ ] `MongoCustomConversions` is created and registered properly.
- [ ] `MappingMongoConverter` actually uses that registry.
- [ ] `MongoTemplate` and `MongoRepository` use the intended mapping context.
- [ ] If multiple connections/templates exist, each template has been verified.
- [ ] Configuration matches the Spring Boot and Spring Data versions.

### 26.5. Testing

- [ ] Unit round-trip and BSON type tests.
- [ ] Negative tests for null, missing, malformed, and legacy inputs.
- [ ] `BigDecimal` boundary and precision tests.
- [ ] Integration tests saving and loading through `MongoTemplate` or repositories.
- [ ] Raw BSON readback confirming the stored representation.
- [ ] Query, index, and aggregation tests verifying BSON semantics.
- [ ] Projection and nested-value tests where applicable.
- [ ] Tests covering legacy data and mixed application versions during migrations.

### 26.6. Production Deployment

- [ ] Existing stored data types have been surveyed.
- [ ] Release ordering and a backward-compatible reader are in place.
- [ ] Migration is idempotent with progress tracking.
- [ ] Backups, recovery, and rollback plans are prepared.
- [ ] Consumers reading raw BSON directly have been notified.
- [ ] Logging never exposes sensitive data.
- [ ] Conversion failures and latency are monitored.
- [ ] Index, storage, and write impacts have been evaluated.

## 27. Summary

Custom converters are a key Spring Data MongoDB tool whenever a system models **business value objects** that need an explicit persistence format distinct from or stricter than default mapping.

### 27.1. Three Layers of Responsibility

~~~text
Domain Money
  -> preserves business meaning:
     amount, currency, invariants

MoneyWriteConverter / MoneyReadConverter
  -> preserves storage contract:
     Decimal128, String, field structure

MongoRepository / MongoTemplate + MappingMongoConverter
  -> integrates persistence lifecycle:
     save, read, query mapping
~~~

Never conflate:

- Business conversions (such as FX or tax) with persistence conversion.
- REST/JSON serialization with BSON mapping.
- Object conversion with data migration.
- Numeric storage formats with UI currency formatting.
- Field-level serialization with authorization.

### 27.2. Complete Implementation Workflow

~~~text
              Design domain value object
                        |
                        v
                  Define BSON schema
                        |
              +---------+----------+
              |                    |
              v                    v
       Default/@Field enough?   Custom format needed?
              |                    |
              v                    v
      Use simple mapping     Write/Read converters
              |                    |
              +---------+----------+
                        |
                        v
               MongoCustomConversions
                        |
                        v
               Spring Data MongoDB
                        |
                        v
          Unit + integration + raw BSON tests
                        |
                        v
        Query/index and backward compatibility
                        |
                        v
           Versioned rollout/migration if needed
                        |
                        v
               Production monitoring
~~~

### 27.3. Principles to Remember

1. **Default mapping first; custom converters when an explicit requirement demands one.**
2. **Define the BSON contract before writing the converter**: field names, store types, schema versions, and null handling.
3. **Reading and writing are two distinct directions**; never assume one implies the other.
4. **Register explicitly via `MongoCustomConversions`** and verify `MongoTemplate`/`MongoRepository` actually use it.
5. **`BigDecimal` → `Decimal128`** preserves numeric semantics far better than `double` or `String` for currency values, subject to bounded precision limits.
6. **Never convert currencies or silently round inside a converter** unless explicitly mandated by the domain.
7. **Queries and indexes operate on stored BSON**, not Java types alone.
8. **`@Field(targetType)`** often suffices when you only need a `BigDecimal` field stored as `Decimal128`.
9. **Global converters have broad scope**; when only a single field needs a special format, evaluate property-specific conversions or separate domain types.
10. **Legacy data does not migrate automatically** when code changes; use Expand → Migrate → Contract and plan rollbacks carefully.
11. **Verify raw stored BSON in integration tests**, not just converter unit tests.
12. **Keep converters stateless, predictable, and free of blocking I/O**, especially in reactive or high-throughput services.
13. **Do not rely on `_class` or package names as long-term business schemas.**
14. **Performance profiling must separate database time, network latency, and Java object mapping.**
15. **Data security and tenant authorization sit outside the converter** and must be enforced via service, query, and database policies.

### Official Version-Specific References

- [Spring Data MongoDB — Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html) — how to register converters and supported conversion types.
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html) — object mapping, metadata, constructors, and type hints.
- [Spring Data MongoDB — Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping.html) — overview of mapping support.
- [Spring Data Commons — Custom Conversions](https://docs.spring.io/spring-data/commons/reference/custom-conversions.html) — conversion direction and registry mechanics.
- [Spring Data MongoDB — Property Converters](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/property-converters.html) — property-scoped conversions where supported by version.
- [MongoDB BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/) — `Decimal128`, `String`, `Date`, `Binary`, and other BSON types.
- [MongoDB Decimal128](https://www.mongodb.com/docs/manual/reference/bson-types/#decimal128-bson-data-type) — decimal limits and characteristics.
- [MongoDB Indexes](https://www.mongodb.com/docs/manual/indexes/) — selecting BSON field paths and indexes.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — raw driver APIs and BSON mapping.
- [Spring Boot Data Access](https://docs.spring.io/spring-boot/reference/data/nosql.html) — auto-configuration and MongoDB integration.

**Conclusion:** A custom converter is only as good as its ability to translate a **well-defined domain value** into a **clear, stable, and testable BSON contract**. Writing a few lines of `Converter<Money, Document>` is just the start; long-term reliability rests on proper registration, accurate `Decimal128` storage, compatible queries and indexes, support for legacy records, and disciplined schema migration.
