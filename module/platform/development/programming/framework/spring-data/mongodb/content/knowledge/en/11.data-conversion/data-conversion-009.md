# Round-Trip Testing with Legacy Version Data

> **Chapter:** Data Conversion  
> **Module:** `SPRING_DATA_MONGODB`

An application can read and write MongoDB reliably in its current version yet still fail when opening documents stored years earlier. For example: an older version stored monetary amounts as strings like `"129.50"`; the new version uses BSON `Decimal128`. If tests only create a new object, call `save()`, and call `findById()`, both operations go through the same new conversion rules and can **miss** the fact that legacy data is no longer readable.

Therefore, **round-trip testing** must be paired with **backward-compatibility testing using legacy version data** (*legacy fixture / golden data*). We verify three questions: can legacy data still be read accurately, do new objects write in the target format, and does written data read back with identical semantics?

This lesson belongs to the `SPRING_DATA_MONGODB` module: using Spring Data MongoDB to connect, map documents, and operate via `MongoTemplate` or repositories. These test results also form a baseline before modifying queries, aggregations, indexes, transactions, reactive access, or performance diagnostics in a system with live data.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **object** round-trip, **BSON** round-trip, and **legacy data compatibility** testing.
2. Build MongoDB fixtures containing the exact BSON types written by earlier deployments, without accidentally regenerating fixtures through current converters.
3. Implement `@ReadingConverter` and `@WritingConverter` when storage types change; register converters on `MappingMongoConverter`.
4. Verify **semantic** equivalence instead of always comparing raw documents verbatim with `equals`.
5. Spot risks of losing fields on `save`, altering `_id`/`_class`, time shifts, numeric type mismatches, query/index incompatibilities, and unsafe migration retries.

## 2. Exact Definitions of Test Types

Let:

- `R₂`: read operation converting BSON into the version 2 Java model.
- `W₂`: write operation converting the Java model into version 2 BSON.
- `L₁`: BSON actually written by version 1.
- `x`: a valid object of the current model.
- `≈`: equivalence under the **business contract**, ignoring accepted differences such as metadata fields, field order, and sub-millisecond precision.

Verify the following relationships:

```text
(A) New object round-trip:
    R₂(W₂(x)) ≈ x

(B) Reading legacy version data:
    R₂(L₁) = expected business state

(C) Converting legacy data to the new write format:
    R₂(W₂(R₂(L₁))) ≈ R₂(L₁)

(D) Repeated canonical writes (when required):
    W₂(R₂(W₂(R₂(L₁)))) ≈ W₂(R₂(L₁))
```

**Do not demand** `W₂(R₂(L₁)) == L₁` byte-for-byte or across every field: the new version may normalize BSON types, reorder fields, add `_class`, drop legacy fields, or rename fields. The goal is preserving **meaning** while knowing which format changes are intentional.

| Check | Input | What It Catches |
| --- | --- | --- |
| New round-trip | Java object built with new model | Read/write converter bugs and precision issues in the new version |
| Legacy read | Unaltered BSON from legacy system | Inability to read old types, wrong defaults, or dropped fields |
| Legacy → canonical → read | Legacy BSON re-saved by new writer | Wrong BSON type conversion, rounded values, or semantic loss |
| Query compatibility | Old and new documents in same collection | Divergent `find`, sort, index, or aggregation results |
| Full persistence test | Real MongoDB / isolated test instance | Behavior of `save`, IDs, callbacks, auditing, optimistic locking, codecs/driver |

A thorough test suite combines in-memory converter tests with MongoDB integration tests; the two layers complement each other.

## 3. Running Scenario: From String Amounts to Decimal128

Suppose the older invoice system stored:

```javascript
// v1: legacy storage format.
{
  _id: "INV-2024-001",
  status: "PAID",
  total: "129.50",                  // BSON String
  paid_at: ISODate("2024-06-01T02:30:00.123Z"),
  legacy_note: "import-batch-07"    // old field absent from new model
}
```

The new version wants to store `total` as **BSON Decimal128**, keep `_id` stable, continue storing `paid_at` as BSON Date, and use an immutable Java model:

```javascript
// v2: target format.
{
  _id: "INV-2024-001",
  status: "PAID",
  total: NumberDecimal("129.50"),  // BSON Decimal128
  paid_at: ISODate("2024-06-01T02:30:00.123Z")
}
```

The two documents **differ in BSON type** yet share the exact same business meaning: an invoice paid for 129.50 currency units at `2024-06-01T02:30:00.123Z`. The testing objective is ensuring the new version understands v1 data and writes the v2 convention.

### 3.1. Why Choose Decimal128?

Using `double` for money can introduce floating-point errors. When business rules support decimal values, `Decimal128` offers well-defined decimal precision; integer minor units are another valid option depending on the domain. **Pick one unified contract** per field.

For `BigDecimal`, default mapping behavior to BSON can vary across Spring Data MongoDB versions; never rely on the assumption that "the framework always stores BigDecimal as Decimal128." In this example, we **register converters explicitly** to control the target BSON value.

### 3.2. Deciding on Legacy Fields Before Writing Tests

The `legacy_note` field illustrates a separate issue from amount conversion: should old information be preserved when the new application overwrites an invoice?

- If unneeded, it can be migrated or removed **deliberately** during migration.
- If retention is mandatory, include it in the model/write path or use targeted updates instead of full-document replacement.
- Without a business decision, **never consider field loss a "successful round-trip"** just because the monetary amount matched.

Test contracts should clearly separate **data that must be preserved**, **data that may be normalized**, and **data permitted to be dropped**.

## 4. Current Java Model

We use a `Money` value object to keep conversion rules explicit and avoid string-parsing money across services.

File `Money.java`:

```java
package com.example.invoice;

import java.math.BigDecimal;
import java.util.Objects;

public record Money(BigDecimal value) {
    public Money {
        Objects.requireNonNull(value, "value");
    }
}
```

File `Invoice.java`:

```java
package com.example.invoice;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "invoices")
public record Invoice(
    @Id String id,
    String status,
    @Field("total") Money total,
    @Field("paid_at") Instant paidAt
) {}
```

Here `Money` represents an amount whose unit/currency follows the lesson's convention. Production systems need an explicit `currency` or unit field to avoid adding incompatible currencies. Systems must also enforce bounds, `scale`, and sign rules per business policy; those rules should never be inferred ad hoc from BSON formatting.

The identifier `"INV-2024-001"` is not a 24-character hex string, so Spring Data will not confuse it with a valid ObjectId string. For IDs that can resemble ObjectIds, explicitly verify existing `_id` BSON types and `@Id` conversion behavior.

## 5. Legacy Read, New Read, and Canonical Write Converters

Create **two reading converters** to support `total` as both BSON String and Decimal128, plus **one writing converter** for v2.

### 5.1. Reading Amounts from Legacy BSON String

File `LegacyMoneyReadConverter.java`:

```java
package com.example.invoice;

import java.math.BigDecimal;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class LegacyMoneyReadConverter
        implements Converter<String, Money> {

    @Override
    public Money convert(String source) {
        return new Money(new BigDecimal(source));
    }
}
```

`BigDecimal(String)` preserves the exact decimal value of strings like `"129.50"`. Malformed values (`"N/A"`, currency symbols, inconsistent commas) raise errors requiring an explicit policy: fail fast, log to a migration error list, or use a source-normalized parser. Never silently return `BigDecimal.ZERO` for unreadable data.

### 5.2. Reading New BSON Decimal128

File `DecimalMoneyReadConverter.java`:

```java
package com.example.invoice;

import org.bson.types.Decimal128;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class DecimalMoneyReadConverter
        implements Converter<Decimal128, Money> {

    @Override
    public Money convert(Decimal128 source) {
        return new Money(source.bigDecimalValue());
    }
}
```

Not every Decimal128 value converts to a finite `BigDecimal` this way: NaN/Infinity require dedicated handling rules. When the system only accepts finite monetary amounts, let invalid values fail in tests rather than silently transforming them into another number.

### 5.3. Writing in v2 Format

File `MoneyWriteConverter.java`:

```java
package com.example.invoice;

import org.bson.types.Decimal128;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class MoneyWriteConverter
        implements Converter<Money, Decimal128> {

    @Override
    public Decimal128 convert(Money source) {
        return new Decimal128(source.value());
    }
}
```

If `BigDecimal` has precision or an exponent exceeding Decimal128's range, instantiating `Decimal128` can fail. That is why boundary tests and pre-save precision validation are necessary.

### 5.4. Registering Converters Properly

`@ReadingConverter` and `@WritingConverter` declare **conversion direction**, yet converter classes **are not automatically registered by Spring Data via component scan alone**. Register instances in `MongoCustomConversions`:

```java
package com.example.invoice;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;

@Configuration(proxyBeanMethods = false)
public class MoneyMongoConversionConfig {

    @Bean
    MongoCustomConversions mongoCustomConversions() {
        return MongoCustomConversions.create(adapter -> {
            adapter.registerConverter(new LegacyMoneyReadConverter());
            adapter.registerConverter(new DecimalMoneyReadConverter());
            adapter.registerConverter(new MoneyWriteConverter());
        });
    }
}
```

In standard Spring Boot applications using auto-configured MongoDB, the `MongoCustomConversions` bean is used by Spring Data/Boot when building `MappingMongoConverter`. If the project already declares custom conversions, mapping converters, or `MongoTemplate` beans, **merge** these converters into the existing configuration and verify the active template uses them. Do not create competing beans that drop other converters.

Another approach in pure Spring Data configuration is registering via `AbstractMongoClientConfiguration.configureConverters(...)`. Verify exact APIs and auto-configuration strategy against your project's dependency versions.

## 6. In-Memory Testing with MappingMongoConverter

This is a cheap, fast test loop valuable for catching basic mapping mistakes. It invokes `MongoConverter.read(...)` and `write(...)` directly on `org.bson.Document`, **without calling a MongoDB server**. Below is an example using a Spring Boot Test slice to obtain the application's actual converter.

### 6.1. Creating Legacy Fixtures with Exact BSON Types

In Java:

```java
package com.example.invoice;

import java.time.Instant;
import java.util.Date;
import org.bson.Document;

public final class LegacyInvoiceFixtures {
    private LegacyInvoiceFixtures() {}

    public static Document invoiceV1() {
        return new Document("_id", "INV-2024-001")
            .append("status", "PAID")
            .append("total", "129.50")
            .append(
                "paid_at",
                Date.from(Instant.parse("2024-06-01T02:30:00.123Z"))
            )
            .append("legacy_note", "import-batch-07");
    }
}
```

In this fixture, `total` is genuinely a Java String so the driver stores a BSON String, and `paid_at` is `java.util.Date` so it encodes as BSON Date. Fixtures **must not be built using `Invoice` and v2 converters**, as doing so bypasses the very legacy format under test.

In real projects, gather representative samples from documents written by the legacy application (with sensitive data anonymized), storing them alongside their schema version and why each sample exists. Never build fixtures purely from memory about the old system.

### 6.2. Verifying Three Properties: Legacy Read, Canonical Write, Re-Read

```java
package com.example.invoice;

import java.math.BigDecimal;
import java.time.Instant;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
@Import(MoneyMongoConversionConfig.class)
class InvoiceConverterCompatibilityTest {

    @Autowired
    MongoTemplate template;

    @Test
    void readsLegacyAndWritesCanonicalDecimal128() {
        Document legacy = LegacyInvoiceFixtures.invoiceV1();

        Invoice restored = template.getConverter()
            .read(Invoice.class, legacy);

        assertThat(restored.id()).isEqualTo("INV-2024-001");
        assertThat(restored.status()).isEqualTo("PAID");
        assertThat(restored.total().value())
            .isEqualByComparingTo(new BigDecimal("129.50"));
        assertThat(restored.paidAt()).isEqualTo(
            Instant.parse("2024-06-01T02:30:00.123Z"));

        Document canonical = new Document();
        template.getConverter().write(restored, canonical);

        assertThat(canonical.get("total"))
            .isInstanceOf(Decimal128.class);
        assertThat(canonical.get("legacy_note")).isNull();
        assertThat(canonical.get("paid_at"))
            .isInstanceOf(java.util.Date.class);

        Invoice secondRead = template.getConverter()
            .read(Invoice.class, canonical);
        assertThat(secondRead).isEqualTo(restored);
    }
}
```

In this sample, the absence of `legacy_note` in canonical is merely an **observation of the example model**; it is not a general license for a system to drop legacy fields. If `legacy_note` must be preserved, update the model or update path and adjust assertions accordingly.

To run `@DataMongoTest`, the project needs matching test dependencies and a configured MongoDB test instance when the context requires connectivity. While the `read`/`write` calls on the converter do not hit a live server, the Spring test context may still bootstrap MongoDB infrastructure. In-memory tests **do not** verify persistence behavior or `save` lifecycle callbacks.

### 6.3. Testing Semantic Round-Trip Rather Than Raw Shape

For v1 data:

- `legacy.get("total")` is `String`.
- `canonical.get("total")` must be `Decimal128`.
- `restored.total().value()` and the re-read value must be numerically equal.
- `_id` and `paid_at` must carry the exact same identifier and timestamp.

Comparing two `Document` instances with `equals` will intentionally fail because `String("129.50")` differs from `Decimal128("129.50")`. Tests should assert **defined semantics**. For `BigDecimal`, use `compareTo` / AssertJ `isEqualByComparingTo` when business rules treat `129.5` and `129.50` as equal; if invoice scale matters, assert scale as well.

## 7. Integration Testing: Seeding Legacy Data via Driver, Reading via Spring Data

This step is critical because unit/converter tests do not exercise the full path through the server, BSON codecs, transactions, callbacks, and `save` mechanics.

### 7.1. Seeding via Driver API Instead of Repository

The current repository writes in the **v2 convention**. To simulate data truly saved before an upgrade, insert fixtures with the MongoDB Java driver:

```java
package com.example.invoice;

import org.bson.Document;
import org.bson.types.Decimal128;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;

import java.math.BigDecimal;

import static org.assertj.core.api.Assertions.assertThat;

@DataMongoTest
@Import(MoneyMongoConversionConfig.class)
class InvoiceDatabaseCompatibilityTest {

    @Autowired
    MongoTemplate template;

    @Test
    void canReadLegacyFromMongoAndPersistInNewFormat() {
        var collection = template.getCollection("invoices");
        Document legacy = LegacyInvoiceFixtures.invoiceV1();
        collection.insertOne(legacy);

        // Read through the application's real access path:
        Invoice current = template.findById(
            "INV-2024-001", Invoice.class);

        assertThat(current).isNotNull();
        assertThat(current.total().value())
            .isEqualByComparingTo(new BigDecimal("129.50"));

        // In an isolated TEST database: save re-persists as v2 entity.
        template.save(current);

        Document stored = collection.find(
            new Document("_id", "INV-2024-001")).first();

        assertThat(stored).isNotNull();
        assertThat(stored.get("total"))
            .isInstanceOf(Decimal128.class);
        assertThat(stored.get("_id"))
            .isEqualTo("INV-2024-001");

        Invoice loadedAgain = template.findById(
            "INV-2024-001", Invoice.class);
        assertThat(loadedAgain).isEqualTo(current);
    }
}
```

**Run this test against a dedicated test MongoDB**, such as a Testcontainers instance wired into the Spring test context, never against a live database. In a full suite, use unique identifiers and cleanup so independent runs do not collide.

`template.save(current)` on an existing document replaces the document with the new model's representation. Because `Invoice` does not map `legacy_note`, that field risks **disappearing** after `save`. That behavior must be verified explicitly; this test focuses on converting `total` and does not assert that dropping old fields is safe.

### 7.2. When Unknown Fields Must Be Preserved

When policy requires keeping `legacy_note` or fields written by other services, one approach is updating **only the target field**:

```java
import org.bson.types.Decimal128;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public void normalizeTotalField(
        MongoTemplate template, String invoiceId,
        String legacyTotal) {
    Decimal128 newTotal = new Decimal128(
        new java.math.BigDecimal(legacyTotal));

    template.updateFirst(
        Query.query(Criteria.where("_id").is(invoiceId)),
        new Update().set("total", newTotal),
        "invoices"
    );
}
```

Place this illustrative method in an appropriate service/utility class. In real systems, passing `legacyTotal` from outside must be guarded against the latest database state to avoid **overwriting a concurrently updated value**. Use value/version matching conditions, concurrency control, transactions, or a sequential migration worker as required.

This method updates only `total` while leaving other document fields intact, though it **bypasses certain callbacks and full-entity mapping** compared to `save`. Therefore test the exact update path chosen.

### 7.3. Repositories Can Verify the Same Contract

If you have:

```java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface InvoiceRepository
        extends MongoRepository<Invoice, String> {}
```

you can test both `repository.findById("INV-2024-001")` and `repository.save(invoice)`. Repositories and `MongoTemplate` share mapping infrastructure, yet query derivation, callbacks, optimistic locking, and update behavior must be verified along the access path **the application actually uses**.

## 8. Asymmetric Changes to Decide Upfront

Not every difference is a bug. What matters is classifying them:

| Transformation | When Acceptable? | Required Tests |
| --- | --- | --- |
| `"129.50"` (String) → `Decimal128("129.50")` | Decided to standardize monetary type | Target BSON has right type; numeric value unchanged |
| `Instant` nanosecond → BSON Date millisecond | Millisecond resolution is acceptable | Compare after normalization/truncation; do not assert nanoseconds |
| `@Id String` ↔ BSON ObjectId | Legacy IDs genuinely follow ObjectId convention | Test `_id` type and ID lookup queries for both forms |
| Missing legacy `status` → default value | Business default is confirmed | Assert missing data and explicit `null` separately |
| Legacy enum `PENDING_APPROVAL` renamed to `WAITING` | Compatibility mapping is defined | Every legacy enum value and unknown values |
| Old FQCN `_class` → new alias | Reader can resolve both old and new data | Load root/nested subtypes, including after restart |
| `legacy_note` dropped | Policy permits removal | Assert intentionally rather than dropping silently |
| Old `LocalDateTime` → new `Instant` | Source timezone of legacy data is known | Test offsets, DST, and ambiguous values |

### 8.1. Numbers and Precision

Suppose v1 used `double` or multi-digit strings. Converting to `Decimal128` cannot recover digits already lost when v1 stored binary floating-point values. Tests must assert expected values based on **what was actually stored**, not assume historical rounding errors can be undone.

When widening `int` to `long`, test values beyond the 32-bit range on v2 writes as well as reading legacy BSON `Int32`. For money, avoid auto-converting malformed strings to `0`.

### 8.2. Time

BSON Date stores UTC epoch milliseconds. If v1 stored `paid_at` as BSON Date, `Instant` mapping preserves the exact instant at millisecond resolution. If v1 stored a local time string without a timezone, you cannot convert it to an accurate instant without knowing the source region/timezone.

Special note for `LocalDateTime`: Spring Data's default converters for local types may use the host's default timezone, whereas the driver's Java Time codecs follow UTC rules. Switching codec/converter settings can make **the same BSON Date be interpreted differently**. Run tests across different timezones or at minimum lock down the conversion convention in code.

### 8.3. Null, Missing Fields, and Deprecated Fields

In BSON, these three states can carry distinct business meanings:

```javascript
// Field omitted:
{ _id: "A" }

// Field present with BSON null:
{ _id: "B", discountCode: null }

// Field holds empty string:
{ _id: "C", discountCode: "" }
```

Never collapse all three cases before knowing their business meaning. For Java primitives such as `long`, missing values may default or fail depending on mapping/constructor behavior; using wrapper `Long` or a validated value object surfaces missing data much more clearly. Test missing, `null`, empty, and wrong-type cases.

### 8.4. `_class` and Inheritance

If legacy documents hold `_class: "com.old.package.InvoiceEvent"` while the new Java package changed, new aliases or class mappings **do not automatically guarantee** resolving every old type hint string. Tests need root and nested fixtures with real type hints; if converters/migrations or old-class compatibility are needed, plan for them explicitly.

## 9. Versioned Fixture Matrix

Instead of testing a single "happy-path" document, build a fixture suite with documented origins and expectations:

| Fixture | Legacy BSON | Expectation in New Version |
| --- | --- | --- |
| `invoice-v1-string-total` | `total` as String, `paid_at` as Date | Reads into `Money`, re-writes as Decimal128 |
| `invoice-v2-decimal-total` | `total` as Decimal128 | Read/write leaves value unchanged |
| `invoice-v1-missing-status` | Missing `status` | Handled per defined default/validation |
| `invoice-v1-invalid-total` | `total: "N/A"` | Error detected and diagnosed; never turned into 0 |
| `invoice-v1-unknown-field` | Has `legacy_note` | Preserved or dropped per agreed policy |
| `invoice-v1-old-class` | `_class` is old FQCN | Mapped properly or verifiable migration exists |
| `invoice-v1-timezone` | Local date-time string, no offset | Converted only when source zone is known; never guessed |
| `invoice-v2-extreme-amount` | Value near Decimal128 limits | Explicit exact handling or rejection rule |

Store fixtures alongside test code as explicitly typed Extended JSON (`$numberDecimal`, `$date`, `$oid`, etc.) or construct them with `Document`/Java BSON types as shown. Production samples must be anonymized, stripped of secrets, and free of personal data.

**Golden fixtures must remain immutable per version:** if a test verifies v1 remains readable, never modify the v1 fixture to match the v2 converter just to make the test pass. When formats evolve, **add** new fixtures and expectations; preserve historical fixtures as long as they stay within support scope.

## 10. Migration: Read Both Shapes, Write One Shape

A safer upgrade strategy is **a multi-version compatible reader with a single-format writer**.

```text
During transition

             ┌── BSON v1 (String total) ──┐
MongoDB ─────┤                             ├── Reader v2 ──> Invoice
             └── BSON v2 (Decimal128) ────┘                     │
                                                               ▼
                                                      Writer v2
                                                               │
                                                               ▼
                                                      BSON v2 (Decimal128)
```

Recommended rollout steps:

1. **Inventory legacy data:** BSON types, null/missing, `_class`, IDs, timestamps, and value distributions.
2. **Lock down canonical contract:** field names, BSON types, semantics, scale, and invalid-data policy.
3. **Deploy reader supporting both v1 and v2:** validate with golden fixtures and integration tests.
4. **Deploy writer v2:** ensure all new records are created in the new format.
5. **Batch migration:** when normalizing old data, use checkpointed processes with logging and safe re-run behavior.
6. **Reconcile:** compare document counts, valid total sums, parse errors, remaining legacy records, and business queries.
7. **Retire legacy support:** remove v1 converters only after eligible data is migrated and old app versions are shut down.

When multiple instances run concurrently during rolling deployments, consider **writer v2 and reader v1 coexisting**. "New app reads old data" does not imply "old app reads new data." If bidirectional safety is required, design rollout order, dual-write/feature flags, or retain the old format during transition.

### 10.1. Surveying BSON Types Before Migration

```javascript
db.invoices.aggregate([
  {
    $group: {
      _id: { $type: "$total" },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

Counting `string`, `decimal`, `null`, `missing`, and other types shows which data needs migration. Also track invalid values and schema version fields if present.

### 10.2. Previewing Convertibility with a Read-Only Aggregation

```javascript
db.invoices.aggregate([
  { $match: { total: { $type: "string" } } },
  {
    $project: {
      total: 1,
      candidateDecimal: {
        $convert: {
          input: "$total",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  { $limit: 50 }
]);
```

This is a **read-only pipeline** for exploration; if `candidateDecimal` becomes null for a non-null string, inspect why parsing failed. In real migrations, never ignore failed records because they skew financial totals.

### 10.3. Safe Re-Execution (Idempotency)

A migration converting strings to Decimal128 should target only documents where `total` is String and report modified counts. Running it again after completion should match 0 documents; it must never double-scale amounts or alter already-migrated records.

For updates running concurrently with live traffic, design CAS/`@Version` conditions, locking, or sequencing strategies. Transactions can help when multi-document consistency is required, though they cannot fix a parser misunderstanding legacy formats.

## 11. Testing Queries and Aggregations After Changing BSON Types

A system might read every individual invoice properly yet **produce wrong reports** while the collection mixes String and Decimal128. For example:

```javascript
db.invoices.find({
  total: { $gte: NumberDecimal("100.00") }
})
```

Never assume numeric queries compare string `"129.50"` as the number 129.50. MongoDB compares by BSON type and type-bracketing rules, and string sorting is lexicographical. A Decimal128 query can miss documents still storing Strings.

Required checks:

- **Filter:** do an old invoice and a new invoice with the same amount appear together in query results?
- **Sort:** is ascending/descending ordering of totals accurate when mixed types exist?
- **Aggregation:** do `$sum` and numeric operators skip or skew legacy records?
- **Index:** do indexes still serve filter/range queries after the type change? Do indexes need rebuilding or redesigning?
- **Query mapping:** are Java criteria using the `Money` value object converted to the right BSON type by custom converters?

During mixed-format phases, you may temporarily normalize inside aggregations with error handling or explicitly scope which queries read legacy data. Never present aggregate reports as exact while unconvertible documents remain unreconciled.

Run `explain("executionStats")` on representative queries after migration, monitoring `totalDocsExamined`, `totalKeysExamined`, and returned counts. Backward-compatible converters solve object mapping, not database-side query optimization or aggregation logic.

## 12. Compatibility with Repositories, Reactive Access, and Transactions

`MongoRepository` and `MongoTemplate` usually share the ApplicationContext's mapping metadata and custom conversions. Thus conversion issues affect both, though not every operation path executes identically: partial updates, aggregation result mapping, raw driver calls, and query projections can take distinct paths.

### 12.1. Raw Driver Does Not Run Spring Converters Automatically

The call:

```java
template.getCollection("invoices")
    .insertOne(LegacyInvoiceFixtures.invoiceV1());
```

goes through the MongoDB Java driver to write BSON and **does not** invoke `MoneyWriteConverter`, because the input is `Document`. That is exactly what you want when seeding legacy fixtures. Conversely:

```java
template.insert(new Invoice(
    "INV-NEW-001",
    "PAID",
    new Money(new java.math.BigDecimal("129.50")),
    java.time.Instant.parse("2026-11-20T02:00:00Z")
));
```

goes through Spring Data mapping, so `MoneyWriteConverter` must output Decimal128. Test both write paths separately.

### 12.2. Reactive Access

If the project uses `ReactiveMongoTemplate`/`ReactiveMongoRepository`, BSON compatibility rules are unchanged. Reactive tests must register the same conversion strategy and confirm publishers are actually subscribed (e.g., using `StepVerifier`):

```java
// Assuming ReactiveMongoTemplate reactiveTemplate,
// Invoice fixture per the design above, and test connection:
StepVerifier.create(
    reactiveTemplate.findById("INV-2024-001", Invoice.class)
)
    .assertNext(invoice -> {
        assertThat(invoice.total().value())
            .isEqualByComparingTo("129.50");
    })
    .verifyComplete();
```

This is an **illustrative test body**: import `reactor.test.StepVerifier` and AssertJ, wire the reactive template in test configuration, and seed v1 BSON beforehand via the sync or reactive driver. Reactive APIs do not make v1 data compatible unless converters are registered.

### 12.3. Transactions and Optimistic Locking

If an entity uses `@Version`, calling `save` after reading a legacy document interacts with how the legacy version field was stored or omitted, version increments, and `OptimisticLockingFailureException`. Migration tests must exercise real concurrency rather than assuming read-then-save is always safe.

Multi-document transactions require a suitable MongoDB deployment and Spring Data configuration; transactions **do not** fix conversion mismatches between BSON String and Decimal128. When migration only updates one field per document, single-document atomicity and appropriate write predicates are usually the foundation before considering heavier transactions.

## 13. Common Pitfalls

| Symptom | Possible Cause | How to Verify/Fix |
| --- | --- | --- |
| New `save→findById` tests always pass, prod fails on old data | Legacy BSON never seeded | Build golden fixtures via BSON/driver and assert legacy reads |
| Reads amounts fine yet `total >= 100` filter fails | Collection mixes String/Decimal128 | Check `$type`, queries, sorts, aggregations, and migration |
| `@ReadingConverter` never executes | Instance not registered or template uses different converter | Check `MongoCustomConversions` and actual `MongoTemplate` bean |
| Reading converter runs yet writes old type | Missing `@WritingConverter` or unstandardized writer | Inspect raw BSON after write/save |
| Test fails because `129.5 != 129.50` | `BigDecimal.equals` compares scale too | Pick numeric/scale comparison matching business policy |
| Time shifts on another server | Legacy local time lacks zone or converter uses system default | Lock down `ZoneId`; test timezones and source data |
| Reading v1 then calling `save` loses `legacy_note` | `save` replaces document with new entity representation | Use partial updates or retain field per contract |
| Changing ID from string to ObjectId breaks lookups | Mismatched `_id` BSON types | Inspect raw BSON, ID converters, and both fixture types |
| Package rename prevents old `_class` resolution | Old class name/alias no longer exists | Test root/nested polymorphism, migrate, or support in reader |
| Re-running migration alters numbers | Missing type filter/idempotency | Filter by BSON type/version, checkpoint, and reconcile |
| Converter test passes yet real save fails | Codecs, callbacks, indexes, schema validators, or transactions untested | Add isolated MongoDB instance tests |

## 14. Workflow Before Upgrading Spring Data MongoDB

1. **Snapshot current and legacy data contracts:** collections, fields, BSON types, IDs, `_class`, versions, null/missing, and monetary/time rules.
2. **Build immutable golden fixtures:** include at least one standard record, one boundary record, one invalid/missing-field record, and one legacy record with fields absent from the new model.
3. **Write business assertions:** which values must hold strictly, which formatting differences are normalized, and when inputs must be rejected.
4. **Unit test pure converters:** `read(v1)`, `write(v2)`, `read(write(read(v1)))`, and canonical idempotency.
5. **Integration test against database:** seed via driver, read via `MongoTemplate` and repository, save/update, then inspect raw BSON and business queries.
6. **Measure operational compatibility:** queries/filters/sorts/aggregations/indexes, reactive paths, callbacks, auditing, and concurrency within real scope.
7. **Plan rolling deployment:** how must old and new readers/writers coexist?
8. **Execute controlled migration:** backup, checkpoints, value reconciliation, error counts, and rollback plan.
9. **Retire legacy support only once verified:** no documents remain needing old converters, or an approved retention policy is in place.

## 15. Practice Exercise

A payment application is upgrading across three versions:

- **V1:** `total` is String `"250000"`, `paidAt` is local datetime string `"2023-05-12 09:00:00"`, missing `currency`.
- **V2:** `totalMinor` is `Long`; `paidAt` is BSON Date; `currency = "VND"` added.
- **V3:** `total` is Decimal128 in major currency units; `paidAt` remains BSON Date; business rules require retaining currency.

Propose a test matrix answering:

1. Can V1's local datetime string be converted to `Instant` if the zone is unknown?
2. Converting `250000` from VND minor/whole units to major decimal units requires what division/multiplication rule, and who confirms it?
3. Which fixtures must remain untouched to prove V3 reads V1/V2 data?
4. When writing canonical V3, what must the BSON types and currency look like?
5. If V2 runs alongside V3 during a rolling deployment, can V2 read records just created by V3?
6. When summing revenue, could records still in V1 format be missed?

**Suggested approach:** never guess V1's timezone without reliable context; document currency-unit conversion rules before coding; keep V1/V2 fixtures in their original BSON and write readers handling each shape; use one verified canonical writer; verify whether older apps must read new data during rolling deployment. Reconcile totals before and after migration using unified currency rules.

## 16. References

- Spring Data MongoDB — [Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html): `@ReadingConverter`, `@WritingConverter`, registering converters, and BSON types.
- Spring Data MongoDB — [Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): `MappingMongoConverter` and domain ↔ BSON mapping rules.
- Spring Data MongoDB — [Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `save`/replace/update behavior, `@Version`, and write operations.
- MongoDB — [BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/): String, Decimal128, Date, and other BSON types.
- MongoDB — [`$type`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/type/): auditing actual field types.

## Key Takeaways

Testing `read(write(x))` on the new model is necessary yet **not sufficient**. To safeguard real data across upgrades, test **`read_v2(legacyBson)`**, **`read_v2(write_v2(read_v2(legacyBson)))`**, and MongoDB persistence/query behavior. Use properly typed BSON golden fixtures, define business equivalence explicitly, register reading and writing converters explicitly, watch for fields lost on `save`, and reconcile after migrations. For Spring Data MongoDB systems with long-lived historical data, this is a vital safety net before refactoring mappings and deploying new versions.
