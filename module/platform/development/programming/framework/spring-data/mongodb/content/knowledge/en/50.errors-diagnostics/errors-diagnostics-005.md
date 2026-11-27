# Constructor Mapping, _class, TypeAlias, and Missing Converters

## 1. The Problem: Document Exists, Yet Spring Cannot Read It

In a **Spring Data MongoDB** application, **MongoTemplate.find(...)**, **MongoRepository.findById(...)**, or the reactive equivalents can fail even though MongoDB returned a valid document. The culprit is not necessarily the query, connection, or index: **Spring may be unable to convert the BSON into the requested Java object**.

For example, the **invoices** collection contains a record:

~~~javascript
{
  _id: "INV-100",
  customer_id: "C-42",
  totalCents: NumberLong(120000),
  _class: "com.example.billing.Invoice"
}
~~~

Meanwhile, recent code changes renamed the **customerId** field, converted a POJO to a **record**, moved **Invoice** to a different package, or introduced a value object for **totalCents**. Such changes can cause mapping failures only when reading older data.

This **Errors and Diagnostics** topic covers four problem areas around **MappingMongoConverter**:

1. **Constructor mapping**: Spring cannot locate or invoke a constructor, or cannot bind parameters from the document.
2. **_class**: type metadata in BSON points to a renamed class, a class absent from the classpath, or lacks details to instantiate a subtype.
3. **@TypeAlias**: the alias stored in **_class** does not match or the mapping context has not registered that type.
4. **Missing or unused converter**: the Java type and actual stored BSON type lack an appropriate conversion path.

After this lesson, you will be able to distinguish **server/query** errors from **Java mapping** errors, inspect raw BSON to spot discrepancies, safely handle legacy data, and write regression tests to prevent recurrence.

## 2. Which Layers Does Data Pass Through?

When using Spring Data MongoDB, the read data path can be pictured as follows:

~~~mermaid
flowchart TB
    API["MongoRepository / MongoTemplate<br/>or reactive API"]
    Driver["MongoDB Java Driver<br/>decodes BSON"]
    Raw["org.bson.Document<br/>values from server"]
    Type["MongoTypeMapper<br/>reads _class / alias"]
    Conv["MappingMongoConverter<br/>conversion + entity metadata"]
    Ctor["Select constructor / factory<br/>bind parameters and properties"]
    Entity["Invoice / Payment / DTO<br/>Java object"]
    API --> Driver --> Raw --> Type --> Conv --> Ctor --> Entity
~~~

**MongoDB returning a Document successfully** only proves the server has the data and the driver decoded the BSON. From there, the mapper still has to resolve the target class, convert field values, and instantiate the Java object.

### Concepts Not to Confuse

| Concept | Purpose | Example |
| --- | --- | --- |
| **@Document** | Marks an entity mapped to a MongoDB collection | **@Document("invoices")** |
| **@Field** | Specifies the storage name or type of a **property** | **@Field("customer_id")** |
| **@Id / @MongoId** | Maps the Java identifier to the BSON **_id** field | **@Id String id** |
| **_class** | Type hint field typically written by Spring Data MongoDB to identify the Java type | **"com.example.billing.Invoice"** |
| **@TypeAlias** | Replaces the fully qualified class name in the type hint with an alias | **@TypeAlias("invoice-v1")** |
| **@PersistenceCreator** | Identifies the constructor or factory used when instantiating an entity | **@PersistenceCreator Invoice(...)** |
| **@ReadingConverter** | Defines conversion from stored data into a Java value | **Converter<String, TrackingCode>** |
| **@WritingConverter** | Defines conversion from a Java value before writing BSON | **Converter<TrackingCode, String>** |

**@Field** renames a data field; **@TypeAlias** changes how the object type itself is represented. Putting **@Field("_class")** on a business property is not how you fix MongoDB subtype resolution.

## 3. Identifying Error Categories from Exceptions

The messages below are **common symptom patterns**, not fixed strings across every Spring Data MongoDB version. Inspect the root exception and deepest **Caused by** line.

| Symptom | Likely Cause to Check | First Investigation Step |
| --- | --- | --- |
| **MappingInstantiationException** | Constructor threw an error, null/mismatched parameter, abstract class cannot be instantiated | Selected constructor, presence and types of BSON fields |
| **MappingException**, failed to bind constructor parameter | Parameter name missing from metadata, property name mismatch, missing **-parameters** | Constructor, property names, compiler flags |
| **ConverterNotFoundException** or conversion error | BSON is String/Document/Decimal128 while Java expects another type | Actual BSON type, reading converter, registration |
| **ClassNotFoundException** or unable to resolve type hint | **_class** points to a deleted/moved class, or alias unrecognized | BSON **_class**, mapping context, deployment/version |
| **CodecConfigurationException** | Direct driver path or BSON/POJO codec lacks support for the sent type | Is code bypassing MongoTemplate and MappingMongoConverter? |
| Reads into **Document/Map** instead of expected subtype | Missing or stripped type hint, overly broad declared type, unregistered type metadata | Declared type, **_class**, **@TypeAlias** |
| Fields become **null** or unexpected defaults | Stored field name differs from property, converter didn't run, legacy data missing field | Raw Document and **@Field** |

Do not fix mapping errors by wrapping calls in **try/catch** and returning **null**. That hides incompatible data and can cause business logic to overwrite fields or persist malformed documents.

## 4. Constructor Mapping: How Does Spring Instantiate Objects?

When converting BSON into an object, Spring Data must pick an instantiation mechanism. Exact rules vary by version and language, but common Java cases include:

- A constructor or static factory annotated with **@PersistenceCreator**: the mapper uses that selection.
- Only one constructor exists: that constructor is usually chosen.
- Java **record**: uses the record's canonical constructor when no special override exists.
- Multiple constructors without explicit annotation: a no-arg constructor may be preferred if present; other combinations easily become ambiguous.

**Constructor parameter names** must match **mapped Java properties**, and the mapper uses property metadata to find the corresponding BSON field names. On regular Java classes, parameter names must be preserved in bytecode (typically via the **-parameters** compiler flag or equivalent metadata). For records, component names are preserved natively.

### 4.1. Example of an Immutable Entity with an Explicit Constructor

~~~java
// Invoice.java
import java.util.Objects;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document("invoices")
public class Invoice {
    @Id
    private final String id;

    @Field("customer_id")
    private final String customerId;

    private final long totalCents;

    @PersistenceCreator
    public Invoice(String id, String customerId, long totalCents) {
        this.id = Objects.requireNonNull(id, "id");
        this.customerId =
            Objects.requireNonNull(customerId, "customerId");
        if (totalCents < 0) {
            throw new IllegalArgumentException("Negative invoice amount");
        }
        this.totalCents = totalCents;
    }

    public String getId() {
        return id;
    }

    public String getCustomerId() {
        return customerId;
    }

    public long getTotalCents() {
        return totalCents;
    }
}
~~~

For the sample document at the start of the lesson:

1. The mapper identifies **Invoice** as the target type.
2. Parameter **id** receives BSON **_id** via **@Id**.
3. Parameter **customerId** binds to Java property **customerId**, whose BSON name is **customer_id** via **@Field**.
4. Parameter **totalCents** receives the integer value from **totalCents**.
5. Spring invokes the constructor; if the constructor throws **IllegalArgumentException**, it is wrapped inside an instantiation-related exception.

**Common mistake:** renaming the constructor parameter to **customer_id** to match BSON directly is usually wrong, because Spring resolves via the **Java property name** and mapping metadata. Keep **customerId** in Java and declare the stored name via **@Field**.

### 4.2. When Constructor Parameter Names Are Stripped

For Java classes with a selected constructor, if parameter name metadata is absent from bytecode, the mapper may fail to bind arguments.

With Gradle Groovy DSL, one way to configure this is:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

With Maven, configure **maven-compiler-plugin** to enable **parameters** per your plugin version.

The **-parameters** flag exposes real parameter names in bytecode. It does **not** fix renamed properties, missing fields in documents, wrong BSON types, or constructors throwing validation exceptions.

### 4.3. Multiple Constructors and No-Args Constructors

Example prone to unexpected behavior:

~~~java
class Customer {
    private String id;
    private String displayName;

    Customer() {
        // Chosen in some cases when multiple constructors exist.
    }

    Customer(String id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }
}
~~~

If you expect Spring to always invoke the two-argument constructor to validate data, mark it explicitly with **@PersistenceCreator** or design the entity with only one suitable constructor. Never assume constructor validation runs if the mapper picks a different instantiation path and sets properties afterward.

### 4.4. Records and Missing Legacy Fields

~~~java
import java.util.Objects;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("profiles")
public record Profile(
    @Id String id,
    String fullName,
    String timezone
) {
    public Profile {
        Objects.requireNonNull(fullName, "fullName");
        if (timezone == null || timezone.isBlank()) {
            timezone = "UTC";
        }
    }
}
~~~

Records use the canonical constructor for materialization. This example deliberately supplies a default when **timezone** is absent in older documents. Yet if **fullName** is missing, the constructor throws: that signals data violating an invariant. Explicitly choose between **migrating data**, **intentional defaulting**, and **rejecting invalid records**.

Notably, placing **@Transient** on a property needed by a persistence constructor prevents the mapper from supplying BSON data for that parameter. Likewise, fields populated via SpEL, factory methods, or immutable constructors must be tested against your version's mapping rules.

## 5. The _class Field: How Spring Distinguishes Java Types

By default, **MappingMongoConverter** uses **DefaultMongoTypeMapper**, writing the fully qualified class name into the **_class** field of the root document. When a nested value is a complex type whose concrete subtype differs from its declared type, Spring may also write **_class** inside the nested document.

Conceptual example:

~~~javascript
{
  _id: "P-001",
  customerId: "C-42",
  source: {
    lastFour: "1234",
    _class: "com.example.payments.CardSource"
  },
  _class: "com.example.payments.Payment"
}
~~~

Suppose Java declares:

~~~java
interface PaymentSource {}

final class CardSource implements PaymentSource {
    String lastFour;
}

@Document("payments")
class Payment {
    @Id String id;
    String customerId;
    PaymentSource source;
}
~~~

Field **source** is declared as an **interface**. When reading, Spring needs to know whether to instantiate **CardSource** or another implementation. The type hint inside nested **source._class** solves this.

### 5.1. When a Document Lacks _class

If code calls **mongoTemplate.findById("INV-100", Invoice.class)**, then **Invoice.class** is already a concrete target type; a document without **_class** can still map cleanly if its fields align.

Harder cases occur when:

- A property is declared as an **interface**, **abstract class**, or supertype.
- BSON data provides no type hint to distinguish subtypes.
- No custom reading converter or custom type resolution exists to pick an implementation.

In that case, Spring may not know which subtype to instantiate, resulting in mapping failures or unexpected value types. Blindly stripping every **_class** field from stored data can break deserialization of polymorphic fields.

### 5.2. When _class Contains an Old Package or Class Name

Before refactoring:

~~~javascript
{ _class: "com.legacy.billing.Invoice", _id: "INV-100" }
~~~

After moving the class to **com.example.billing.Invoice**, older documents still retain the previous type hint string. A new deployment lacking the old class may fail to resolve **_class**. Remediation depends on live data:

1. **Keep temporary compatibility** while older writers still emit the old type, if architecture allows.
2. **Run a controlled _class migration** once all matching documents reliably belong to the new type and share compatible fields.
3. **Use @TypeAlias or a custom TypeInformationMapper** for stable long-term type identifiers; legacy documents must still be addressed.
4. **Test reading before and after migration** on samples covering all relevant subtypes.

**Adding or changing @TypeAlias in source code does not retroactively update already-stored _class values.** Similarly, renaming a collection does not rewrite nested type hints.

### 5.3. Do Not Disable _class as a Default Workaround

Spring Data lets you customize **DefaultMongoTypeMapper**, including suppressing type hints when appropriate. However, disabling type hints globally removes information required by polymorphic models and can break reading existing documents.

Consider disabling it only when data has a **rigid schema**, target types can always be inferred without **_class**, and you have tested nested entities, interfaces, projections, and legacy records. Never turn off **_class** merely to silence an error.

## 6. @TypeAlias: Stable Type Names and Diagnosing Missing Aliases

**@TypeAlias** tells Spring Data to store a short alias instead of the full Java class name inside **_class**:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("payments")
@TypeAlias("payment-v1")
public record Payment(
    @Id String id,
    PaymentSource source
) {}

interface PaymentSource {}

@TypeAlias("card-source-v1")
record CardSource(String lastFour) implements PaymentSource {}

@TypeAlias("bank-source-v1")
record BankSource(String bankCode) implements PaymentSource {}
~~~

A stored document looks like:

~~~javascript
{
  _id: "P-001",
  source: {
    lastFour: "1234",
    _class: "card-source-v1"
  },
  _class: "payment-v1"
}
~~~

Because aliases omit package names, package refactors are less likely to break newly written data. Still, **an alias is part of your persisted data format**: changing an existing class's alias arbitrarily causes old and new records to carry incompatible identifiers.

### 6.1. Alias Exists in BSON, Yet Mapper Does Not Recognize It

A common pitfall occurs when a class carries **@TypeAlias("card-source-v1")**, yet the **mapping context has not learned about that class** when reading the first document. An alias works only after target entity metadata has been registered.

Per Spring Data documentation, entity metadata is discovered either upon first save or via the **initial entity set**, typically populated by classpath scanning within configured packages.

Checks to run:

- **Is the class present in the runtime artifact?** Not trapped in a test module or excluded package.
- **Is the annotation on the concrete subtype?** Not mistakenly placed only on the parent interface.
- **Did the mapping context discover the subtype?** Check package scanning, initial entity list, or custom mapping configuration.
- **Are aliases unique?** Two classes sharing an alias create ambiguous resolution.
- **Are there multiple MongoTemplate/MongoConverter beans?** The alias might be registered in one context while the actual call uses a different converter.

Example when managing Spring Data MongoDB configuration manually via **AbstractMongoClientConfiguration**:

~~~java
import java.util.Set;
import org.springframework.data.mongodb.config.AbstractMongoClientConfiguration;

// Override placed inside a complete MongoDB configuration class
// where mongoClient() and remaining config are also provided.
@Override
protected Set<Class<?>> getInitialEntitySet() {
    return Set.of(
        Payment.class,
        CardSource.class,
        BankSource.class
    );
}
~~~

This is an **illustrative method snippet**, not a standalone runnable Java class. When using Spring Boot auto-configuration, verify that entity scanning is active rather than adding a manual config class that risks spinning up a second converter/context.

### 6.2. How to Choose an Alias

| Ways to Store _class | Advantages | Risks |
| --- | --- | --- |
| Fully qualified class name | Spring resolves classes directly while they remain unchanged | Renaming packages or classes breaks old records |
| Short, stable alias | Decoupled from package structure | Must ensure mapping context discovery, uniqueness, and migration tracking |
| Omit type hint | Smaller BSON for homogeneous schemas | Interfaces/subtypes may fail resolution |

Aliases should serve as stable identifiers, such as **payment-card-v1**. The **v1** suffix is a schema convention you maintain—Spring does not perform versioned migrations automatically.

## 7. Missing Converter: Java Type and BSON Type Do Not Match

Suppose the **trackingCode** field in **shipments** was previously stored as a string:

~~~javascript
{
  _id: "S-100",
  trackingCode: "VN-TRK-001"
}
~~~

Later, the app replaces **String trackingCode** with **TrackingCode trackingCode** to enforce formatting:

~~~java
public record TrackingCode(String value) {
    public TrackingCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Tracking code must not be blank"
            );
        }
    }
}
~~~

Without a **String -> TrackingCode** converter, old scalar String documents may fail to materialize into the value object. Conversely, registering a reading converter without a writing converter can cause new documents to be saved as nested structures, making application versions incompatible.

### 7.1. Declaring Reading and Writing Converters

~~~java
// TrackingCodeReadConverter.java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class TrackingCodeReadConverter
        implements Converter<String, TrackingCode> {

    @Override
    public TrackingCode convert(String source) {
        return new TrackingCode(source);
    }
}
~~~

~~~java
// TrackingCodeWriteConverter.java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class TrackingCodeWriteConverter
        implements Converter<TrackingCode, String> {

    @Override
    public String convert(TrackingCode source) {
        return source.value();
    }
}
~~~

**@ReadingConverter** and **@WritingConverter** specify conversion direction. This matters especially when both types can be represented directly by the driver, preventing Spring from guessing the wrong direction.

### 7.2. Registering Converters with MongoCustomConversions

~~~java
// MongoValueConversionConfig.java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;

@Configuration
public class MongoValueConversionConfig {

    @Bean
    MongoCustomConversions mongoCustomConversions() {
        return MongoCustomConversions.create(adapter -> {
            adapter.registerConverter(new TrackingCodeReadConverter());
            adapter.registerConverter(new TrackingCodeWriteConverter());
        });
    }
}
~~~

This example uses **MongoCustomConversions.create(...)** available in modern Spring Data MongoDB lines. On older versions, registration may pass a converter list to **MongoCustomConversions** or override the conversion hook; verify your exact version's API.

Converters **are not registered automatically just by existing on the classpath**. Under Spring Boot, confirm the **MongoCustomConversions** bean is actually wired into the converter auto-configuration. When instantiating **MappingMongoConverter** manually, pass your custom conversions into it and finish initialization according to its lifecycle API.

For reactive access, verify **ReactiveMongoTemplate** uses the converter with those registrations; attaching converters to a different template/client will not resolve errors on the active path.

### 7.3. Applying to the Entity and Testing Legacy Data

~~~java
// Shipment.java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("shipments")
public record Shipment(
    @Id String id,
    TrackingCode trackingCode
) {}
~~~

Expected behavior once properly registered:

| Direction | Input | Converted Output |
| --- | --- | --- |
| Read | BSON String **"VN-TRK-001"** | **new TrackingCode("VN-TRK-001")** |
| Write | **new TrackingCode("VN-TRK-002")** | BSON String **"VN-TRK-002"** |

Do not push conversion logic up into controllers when the issue is how a property is persisted and read from MongoDB. All read paths—repositories and `MongoTemplate`—must share consistent mapping rules.

### 7.4. Converters for Nested Documents

If legacy data looks like a nested document:

~~~javascript
{
  _id: "S-101",
  trackingCode: { prefix: "VN", number: "002" }
}
~~~

a **String -> TrackingCode** converter will not help. Options to evaluate:

- Write a **@ReadingConverter** from **Document -> TrackingCode** if a clean rule exists.
- Allow the model to map that document shape via constructor/property mapping.
- **Migrate** legacy data to a single uniform format.

Never write a converter with the wrong source signature just because an exception mentions a Java type name. Verify the **actual source BSON type** first.

### 7.5. Note on BigDecimal and Decimal128

Monetary fields may be persisted as **String** or **Decimal128** depending on Spring Data MongoDB version and config. To enforce Decimal128 explicitly:

~~~java
import java.math.BigDecimal;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

class ProductPrice {
    @Field(targetType = FieldType.DECIMAL128)
    BigDecimal amount;
}
~~~

Spring Data MongoDB 5.x documentation notes changes in default representation choices for large numbers. When upgrading versions, check **actual BSON output**, **@Field(targetType = ...)**, and **MongoCustomConversions** rather than assuming **BigDecimal** serializes identically across versions.

## 8. Step-by-Step Diagnostic Process for a Real Mapping Failure

Suppose **GET /shipments/S-100** returns HTTP 500 with a **TrackingCode**-related cause in logs. An effective workflow separates querying the document from materializing the object.

### Step 1 — Gather Minimal Context

Record (within your security policy):

- Collection name, target Java type, anonymized ID or reference key.
- Application and Spring Data MongoDB version, and whether errors started after a deploy or migration.
- Exception class, **Caused by** lines, and mentioned property, constructor, or converter names.
- Differences between readable documents and failing documents.

Never log full customer payloads, passwords, tokens, or sensitive fields just for diagnostics.

### Step 2 — Read Raw BSON, Bypassing Entity Materialization

Using **mongosh**:

~~~javascript
db.getSiblingDB("demo")
  .getCollection("shipments")
  .findOne({ _id: "S-100" });
~~~

Or in an integration test with **MongoTemplate**:

~~~java
import static com.mongodb.client.model.Filters.eq;
import org.bson.Document;

Document raw = mongoTemplate.getCollection("shipments")
    .find(eq("_id", "S-100"))
    .first();

if (raw == null) {
    throw new IllegalStateException("Test fixture was not found");
}
System.out.println("Tracking value BSON shape: "
    + (raw.get("trackingCode") == null
        ? "null"
        : raw.get("trackingCode").getClass().getName()));
~~~

This assumes **mongoTemplate** is injected in a test or service. To protect data, log only the **type name** and metadata, not sensitive field values.

**MongoTemplate.getCollection(...)** returns the driver collection API, letting you inspect documents without forcing the mapper to build **Shipment**. This separates "document missing" from "materialization failure."

### Step 3 — Compare Actual BSON Shape Against Java Properties

Examples:

| Raw BSON | Java Property | Diagnostic Direction |
| --- | --- | --- |
| **trackingCode: "VN-TRK-001"** | **TrackingCode** | Needs String -> TrackingCode reading converter or migration |
| **trackingCode: {prefix, number}** | **TrackingCode** | Map as subdocument or Document -> TrackingCode converter |
| **totalCents: "120000"** | **long** | Check legacy string data / numeric conversion; do not assume String auto-converts |
| **customer_id: "C-42"** | **customerId** | Missing **@Field("customer_id")** metadata |
| **source._class: "old.package.CardSource"** | **PaymentSource** | Needs type-hint compatibility or migration |
| Missing **source._class** | Interface **PaymentSource** | Needs explicit subtype resolution |
| Missing **fullName** | Non-null record component | Decide between intentional default or data cleanup |

### Step 4 — Materialize an Isolated Document

Once you have a raw BSON **Document**, test the active mapper directly:

~~~java
Shipment mapped =
    mongoTemplate.getConverter().read(Shipment.class, raw);
~~~

Reproducing the mapper failure on an isolated input produces far clearer stack traces and shape visibility than debugging the entire REST endpoint. Be sure to use the exact **MongoTemplate/MappingMongoConverter** the application runs, as a test-constructed converter can produce misleading results.

### Step 5 — Verify Metadata and Registration

For constructor errors:

1. How many constructors/factories does the entity have?
2. Which constructor was selected?
3. Is **@PersistenceCreator** placed on the intended one?
4. Does compiled Java bytecode retain parameter names?
5. Do parameter names match **Java property names**? Did **@Field** rename the stored field?
6. Do missing/null fields cause the constructor to throw?

For **_class/@TypeAlias** errors:

1. Does raw BSON contain **_class** at the root and on polymorphic nested fields?
2. Is the type hint an old class name or an alias?
3. Does the class still exist on the runtime artifact?
4. Was the alias registered in the mapping context before reading?
5. Are aliases unique and consistent across versions?

For custom converter errors:

1. Is the source BSON a **String**, **Document**, **Decimal128**, or another BSON type?
2. Is there a converter with the **exact source/target pair** and **right read/write direction**?
3. Is the converter registered with MongoCustomConversions?
4. Is Spring actually using that converter at runtime?
5. Can the converter throw on malformed input?

### Step 6 — Choose Code Fix vs. Data Fix

If old data represents a **still-supported legacy schema**, handle it with an appropriate constructor, **@Field**, compatibility converter, or type alias mapping. If the data is **no longer business-valid**, migrate it to the new schema with tests and rollback capability. If bad data resulted from a broken write path, fix the writer as well to prevent new malformed records.

Never mass-update **_class** or rewrite monetary formats in production before inventorying BSON variants, testing on a data copy, and checking other applications reading the same collection.

## 9. Diagnostic Scenarios from Common Refactors

### Scenario A — JavaBean to Record

Previously, **Customer** had a no-arg constructor and setters. After refactoring to a three-component record, legacy documents missing one field pass **null** into the canonical constructor and fail.

**Remediation:** identify required fields, supply sensible constructor defaults or migrate data; test both old and new documents. If missing data indicates an unrecoverable business error, preserve explicit failure instead of inventing placeholder values.

### Scenario B — Moving a Package After Persisting Data

The collection has **_class: "legacy.app.Order"**, while runtime only has **new.app.Order**. Some reads still succeed when callers pass a concrete target class and do not rely on type hints; polymorphic or supertype reads can fail.

**Remediation:** audit how entities are read, implement aliases or controlled migration, and test polymorphic paths. Do not assume one successful **findById(Order.class)** means nothing depends on type hints.

### Scenario C — Changing @TypeAlias in a New Release

Version A writes **_class: "card-v1"**; Version B only knows **@TypeAlias("card-v2")**. Existing documents do not rewrite themselves.

**Remediation:** version schemas intentionally, ensure readers recognize legacy aliases or migrate before retiring old aliases, and avoid running two deployments concurrently that emit incompatible aliases.

### Scenario D — Write Converter Exists, Read Converter Missing

The app writes **TrackingCode** as a String, yet reads need to reconstruct **TrackingCode**. Without **String -> TrackingCode**, successful writes do not prove reads will work.

**Remediation:** register both directions as needed, write real save-read tests, and test reading raw legacy BSON. If the Java type enforces invariants, enforce them in the reading converter as well.

### Scenario E — Converter Exists, Never Runs

The team wrote a valid **@ReadingConverter**, yet a manually constructed **MongoTemplate** bypasses the **MongoCustomConversions** bean containing it.

**Remediation:** verify which `MongoTemplate`, `MongoConverter`, and `MongoMappingContext` beans services inject and how auto-configuration wires them. Avoid creating standalone converters unnecessarily and test parity across repositories, `MongoTemplate`, and reactive templates.

### Scenario F — DTO Projection Mistaken for Entity Mapping

A repository returns a projection or DTO whose constructor/properties do not match the projected fields. Errors happen even when the underlying entity reads cleanly.

**Remediation:** identify whether failure occurs while materializing an **entity**, **projection**, or aggregation DTO. Check **$project** field aliases, constructor signatures, and property mapping rules. Do not alter the entity's **_class** when the bug is in a projection.

## 10. Writing Tests to Prevent Mapping Regressions

For type or alias bugs, the most effective tests include at least one **raw BSON fixture** matching the failing shape. Mocking repositories bypasses **MappingMongoConverter**, testing only service logic rather than mapping accuracy.

### 10.1. Isolated Converter Unit Tests

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class TrackingCodeConverterTest {

    @Test
    void convertsBothDirections() {
        TrackingCode value =
            new TrackingCodeReadConverter().convert("VN-TRK-001");

        assertEquals(new TrackingCode("VN-TRK-001"), value);
        assertEquals(
            "VN-TRK-001",
            new TrackingCodeWriteConverter().convert(value)
        );
    }

    @Test
    void rejectsInvalidLegacyValue() {
        assertThrows(
            IllegalArgumentException.class,
            () -> new TrackingCodeReadConverter().convert(" ")
        );
    }
}
~~~

This test needs no MongoDB. It validates converter logic, **not yet proving Spring registered the converter** or that entity mapping invokes it.

### 10.2. Integration Test Reading Raw BSON via MappingMongoConverter

Example using Spring Boot 3.x, **@DataMongoTest**, and a properly configured test MongoDB instance:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.UUID;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
@Import(MongoValueConversionConfig.class)
class ShipmentMappingIntegrationTest {

    @Autowired
    MongoTemplate mongoTemplate;

    @Test
    void readsLegacyTrackingCodeStoredAsString() {
        String id = "SHIP-" + UUID.randomUUID();
        Document raw = new Document("_id", id)
            .append("trackingCode", "VN-TRK-001");

        mongoTemplate.getCollection("shipments").insertOne(raw);

        Shipment shipment =
            mongoTemplate.findById(id, Shipment.class);

        assertNotNull(shipment);
        assertEquals(
            new TrackingCode("VN-TRK-001"),
            shipment.trackingCode()
        );
    }

    @Test
    void writingUsesStableBsonStringFormat() {
        String id = "SHIP-" + UUID.randomUUID();
        mongoTemplate.save(new Shipment(
            id, new TrackingCode("VN-TRK-002")
        ));

        Document raw = mongoTemplate.getCollection("shipments")
            .find(new Document("_id", id))
            .first();

        assertNotNull(raw);
        assertEquals("VN-TRK-002", raw.getString("trackingCode"));
    }
}
~~~

**Test note:** **@DataMongoTest** is a Spring test slice and does not automatically spin up a MongoDB server in all environments. Supply a test database via Testcontainers, a managed test instance, or the mechanism fitting your Boot version. **@Import** ensures the converter config is loaded in the slice; verify production auto-registration separately.

### 10.3. Testing Type Aliases and Constructors

For entities with subtypes, maintain fixtures simulating:

- Root document with full **_class**.
- Root document with an alias, e.g., **"payment-v1"**.
- Nested document with an alias, e.g., **"card-source-v1"**.
- Legacy document missing optional fields.
- Document carrying a pre-migration **_class**.
- Document with unexpected BSON types (e.g., String instead of number, or subdocument instead of scalar).

Run **read** tests against all these fixtures; testing only **save then find** on fresh records does not prove legacy data remains readable.

For immutable classes with constructor invariants, test both **valid conditions** and **missing/wrongly typed inputs**. If invariants must reject corrupt data, assert that an explicit error is thrown rather than expecting Spring to patch values silently.

### 10.4. When Do You Need Real MongoDB Tests?

| What You Want to Prove | Unit Test Enough? | Integration Test Needed? |
| --- | --- | --- |
| **TrackingCodeReadConverter.convert** returns expected output | Yes | Optional |
| **MongoCustomConversions** is picked up by Spring | Not yet | Helpful, recommended |
| **@Field** maps to the expected BSON field | Not if mocked | Yes |
| **@TypeAlias** resolves on first read right after startup | Not if mocked | Yes |
| **Invoice** instantiates from legacy BSON via real constructor | Not if mocked | Yes |
| Updates/aggregations return expected entities/projections | Not if mocked | Yes |
| Legacy data remains readable post-migration in compatible env | Not if mocked | Yes, using anonymized real fixtures |

## 11. Checklist for Production Incidents

1. **Locate the failing layer:** server/driver, mapping converter, constructor, projection, or post-read business logic.
2. **Capture root exception:** inspect **Caused by**, property, class, constructor, or converter source/target pair.
3. **Read raw BSON safely:** check field names, value types, **_id**, **_class**, and nested type hints without logging sensitive values.
4. **Compare schemas:** Java properties, **@Field**, nullability, record components, and constructor parameters.
5. **Verify Java metadata:** **@PersistenceCreator**, **-parameters** flag, static factories, and runtime classpath.
6. **Verify type hints:** old package/class names, renamed aliases, mapping context missing registered subtypes.
7. **Verify converters:** read/write signatures, direction annotations, registration, and the active `MongoConverter`.
8. **Fix at the right layer:** compatible mapping, exact converter pair, or data migration if warranted.
9. **Add regression fixtures:** store pre-fix BSON shapes, verify reads pass, verify writes emit the new schema, and test intentional malformed inputs.
10. **Roll out carefully:** assess impact on other running app versions, back up, batch-migrate, and monitor mapping errors after deploy.

### Self-Check Questions

**1. A repository finds a document yet throws MappingInstantiationException—is MongoDB definitely broken?** No. The driver may have decoded BSON fine, while **MappingMongoConverter** could not instantiate the Java object due to constructors, parameters, or bad data.

**2. Should you rename a Java constructor parameter to match the BSON field name to fix constructor mapping?** Usually no. The mapper binds against the **Java property**, while the BSON name is configured via **@Field** and mapping metadata.

**3. Why can documents without _class sometimes still be read?** Because the caller passed a concrete target Java type. For interface/abstract fields or polymorphic subtypes, missing type hints can cause failures.

**4. If @TypeAlias is present, will Spring always find the subtype on the first document read?** Not necessarily. The mapping context must already know the concrete subtype via entity scanning or the initial entity set.

**5. Is writing @ReadingConverter with @Component enough for MongoTemplate to use it?** Do not assume so. Custom converters must be registered into the **MongoCustomConversions** used by the active converter.

**6. Does saving and finding a newly written entity prove legacy BSON is readable?** No. You must write dedicated tests with raw fixtures holding legacy BSON shapes.

**7. Is disabling _class globally the best way to handle package renames?** No. That strips subtype metadata; evaluate polymorphic reads and plan compatibility or migration instead.

## Conclusion

**Constructor mapping, _class, @TypeAlias, and missing converter** errors arise when Java models, mapping metadata, and stored BSON drift apart. In Spring Data MongoDB, effective diagnosis starts by **reading the raw Document**, verifying the **target class and constructor**, checking **type hints/aliases**, and matching **source BSON types with read/write converters**. After fixing, test both new data and legacy fixtures through **MappingMongoConverter** and a real test MongoDB instance—especially when using records, immutable objects, polymorphism, or multiple app versions sharing a collection.

### References

- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html)
- [Spring Data MongoDB — Type Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/converters-type-mapping.html)
- [Spring Data MongoDB — Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html)
