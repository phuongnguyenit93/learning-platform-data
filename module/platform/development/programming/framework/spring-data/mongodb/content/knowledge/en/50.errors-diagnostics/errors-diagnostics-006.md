# Numeric, UUID, or Date/Time Mismatches Between Java and BSON

In **Spring Data MongoDB**, reading or writing a document passes through several layers: the entity's Java types, **MappingMongoConverter**, the MongoDB Java Driver/BSON codecs, and the actual BSON types stored in the collection. An **amount** field may be a **String** in older documents and **Decimal128** in newer ones; **customerId** may be a binary subtype 3 UUID, subtype 4 UUID, or string; **createdAt** may be a BSON Date or an ISO 8601 text string. Looking only at rendered JSON is rarely enough to tell them apart.

These mismatches can cause read conversion failures, precision loss, missing query results, or unexpected timezone shifts. This lesson in the **Errors and Diagnostics** chapter focuses on verifying **actual BSON types**, comparing them against your Java model, and fixing root causes across **MongoTemplate**, **MongoRepository**, aggregations, and reactive access.

## 1. Objectives and Diagnostic Model

After this lesson, you will be able to:

1. Distinguish **BSON int32, int64, double, Decimal128, and string** and select appropriate Java types.
2. Diagnose **STANDARD/subtype 4** UUIDs, **legacy/subtype 3** UUIDs, and string-encoded UUIDs.
3. Explain differences among **Instant, LocalDateTime, OffsetDateTime, ZonedDateTime**, BSON Date, and BSON Timestamp.
4. Inspect raw data via **mongosh**, **$type**, and **RawBsonDocument** before changing converters.
5. Design **round-trip** tests and safe, repeatable legacy data migrations.

~~~mermaid
flowchart TD
    A["MongoDB read / write / query error"] --> B["Identify failing field, _id, and document"]
    B --> C["Inspect raw BSON: $type, raw document, binary subtype"]
    C --> D["Compare entity types and MappingMongoConverter"]
    D --> E["Check Java Driver config and versions"]
    E --> F{"Which mismatch?"}
    F -- "Numeric" --> G["Precision / range / Decimal128 / String"]
    F -- "UUID" --> H["Subtype 3/4 / byte order / representation"]
    F -- "Date/Time" --> I["BSON Date / epoch ms / timezone"]
    G --> J["Fix mapping or run controlled migration"]
    H --> J
    I --> J
    J --> K["Test round-trip + queries + legacy data"]
~~~

**First rule:** never force Java casts or change global settings the moment an error appears. First measure how many documents deviate from the schema, which application version wrote them, and what the raw BSON actually is. A tweak that "reads one document" can silently misdecode others.

## 2. Recognizing Symptoms Before Changing Code

| Symptom | Cause to Inspect | Quick Verification |
| --- | --- | --- |
| Reading **amount** into **BigDecimal** fails | Data is an invalid string, double, or incompatible converter | **$type**, raw BSON, **BigDecimalRepresentation** rules |
| Monetary totals or counts drift after processing | Double rounding, int32/int64 overflow, lossy conversion | Source type, large values, boundaries, and Java arithmetic |
| **findByCustomerId(UUID)** returns empty | UUID stored as subtype 3 while queried as subtype 4, or stored as string | Inspect **binary subtype** and **UuidRepresentation** config |
| Driver throws UUID codec error | UUID representation unset, or legacy byte order mismatch | Check `MongoClientSettings`/connection URI |
| Read timestamps are off by 7 hours | `LocalDateTime` interpreted as UTC vs. runtime timezone | BSON Date UTC, JVM default zone, active converters |
| Same record loses nanoseconds | BSON Date stores only **milliseconds** | Compare **Instant** before and after round-trip |
| Date-range filter misses documents | Query sends string instead of BSON Date, or wrong timezone bounds | Stored data type and **[start, end)** in business timezone |
| TTL index does not expire documents | Time field is string, long, or TTL index misconfigured | Field **$type** and index definition |

Exact exception names vary by driver, converter, and call path. You may encounter **MappingException**, **ConversionFailedException**, **CodecConfigurationException**, driver errors, or silent empty query results. Record the **message, nested cause, field, versions, and BSON type** in diagnostic notes rather than guessing solely from an exception class name.

## 3. Numeric Types: Java and BSON Are Not One-to-One

MongoDB supports multiple numeric types with distinct bounds:

| BSON | **$type** Alias | Common Java Type | Risks |
| --- | --- | --- | --- |
| **Int32** | **int** | **int / Integer** | Holds only -2³¹ to 2³¹ − 1 |
| **Int64** | **long** | **long / Long** | ±2⁶³ limit; handle overflow |
| **Double** | **double** | **double / Double** | IEEE 754; many decimal fractions are imprecise |
| **Decimal128** | **decimal** | **BigDecimal** or **Decimal128** | Up to 34 significant digits and exponent limits; not every `BigDecimal` fits |
| **String** | **string** | **String** | Non-numeric; lexicographical comparison differs from numeric |

**Example:** displaying as **12.30**, documents might store:

~~~javascript
db.payments.insertMany([
  { _id: "n-int",    amount: NumberInt("12") },
  { _id: "n-long",   amount: NumberLong("12") },
  { _id: "n-double", amount: 12.30 },
  { _id: "n-dec",    amount: NumberDecimal("12.30") },
  { _id: "n-string", amount: "12.30" }
]);
~~~

In **mongosh**, use **NumberInt**, **NumberLong**, and **NumberDecimal** constructors to control types instead of trusting relaxed JSON display. **Canonical Extended JSON** preserves explicit markers such as **$numberInt**, **$numberLong**, **$numberDouble**, and **$numberDecimal**.

### 3.1. Relationships Among Numeric Types in Queries

MongoDB **treats numeric types as comparable across many numeric comparisons**: for example, a comparison with 12 can match int32, int64, double, or decimal values representing the same numeric value. Thus, you should not claim that every query from a **Long** will completely miss an **Int32**.

However, comparisons between **numeric** and **String** obey BSON type bracketing; numeric queries **do not automatically coerce** `"12.30"` into Decimal128. Results are also affected by Double precision and how the driver/mapping converter encodes query parameters.

~~~javascript
// Match only documents with a numeric BSON type.
db.payments.find({ amount: { $type: "number" } });

// Match only documents with decimal128.
db.payments.find({ amount: { $type: "decimal" } });

// Inspect records mistakenly stored as strings.
db.payments.find({ amount: { $type: "string" } });
~~~

When summing in aggregations, verify input and output types. Mixing **double**, **decimal**, **long**, and string data can produce unexpected conversion behaviors; test boundary values and business rounding rules.

### 3.2. BigDecimal, Decimal128, and Spring Data Configuration

**BigDecimal** is a Java decimal type with wide precision, whereas **Decimal128** is a bounded BSON type. Historically, many Spring Data MongoDB versions defaulted to storing `BigDecimal` as **String**; starting in **Spring Data MongoDB 5.0**, default representation selection must be configured explicitly. Never guess current behavior from the Java field type alone.

One option for monetary fields is storing as **Decimal128**:

~~~java
import java.math.BigDecimal;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document("invoices")
public class Invoice {
    @Id
    private String id;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal amount;

    protected Invoice() {}

    public Invoice(String id, BigDecimal amount) {
        this.id = id;
        this.amount = amount;
    }

    public String getId() { return id; }
    public BigDecimal getAmount() { return amount; }
}
~~~

In applications with many **BigDecimal** fields, inspect **MongoCustomConversions** and configure **BigDecimalRepresentation** per your Spring Data version so the default storage format is intentional. **@Field(targetType = FieldType.DECIMAL128)** sets the BSON representation for an individual property. Always inspect actual written BSON, not just annotations.

For currency, two common strategies are:

- **Decimal128** if you need decimal arithmetic/queries inside MongoDB and values fit within precision/exponent limits.
- **Long integer minor units** (e.g., cents) when currency granularity is fixed; guard scale and overflow during multiplication/division.

**Double** is unsuitable when exact decimal representation is required for financial reconciliation. Likewise, never call **doubleValue()** on a `BigDecimal` and expect exact digits to survive.

Notably, **BigDecimal.equals** checks **scale**, whereas **compareTo** compares numeric value:

~~~java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("12.30");
BigDecimal b = new BigDecimal("12.3");

assert !a.equals(b);       // different scales
assert a.compareTo(b) == 0; // numerically equal
~~~

In round-trip tests, state clear expectations: **numeric value** or **display scale**. If the system requires a fixed scale, enforce scale/rounding prior to persistence and verify it; MongoDB does not enforce accounting rules for you.

### 3.3. Overflow and Dangerous Casts

~~~java
long total = 3_000_000_000L;

// Silent data corruption via narrowing cast:
int unsafe = (int) total;

// Throws ArithmeticException if out of range:
int checked = Math.toIntExact(total);
~~~

**int**, **long**, **BigInteger**, and **BigDecimal** are distinct contracts. Never fix a mapping error by switching fields to **int** if values can exceed 32-bit bounds. Use **Math.addExact / multiplyExact / toIntExact** in Java logic to catch overflows, and test boundary values in MongoDB updates/aggregations. A converter that silently truncates fractions or overflows `int` corrupts data without throwing.

## 4. UUID: Same Display Text, Different BSON Binary

A **Java UUID** is 128 bits, yet MongoDB has several historical binary representations:

| Representation | BSON | Characteristics |
| --- | --- | --- |
| **STANDARD** | Binary subtype **4** | Recommended format for new UUID data |
| **JAVA_LEGACY** | Binary subtype **3** | Byte order compatible with legacy Java driver writes |
| **CSHARP_LEGACY / PYTHON_LEGACY** | Binary subtype **3** | Also subtype 3, but byte ordering differs from Java legacy |
| **UUID String** | BSON **string** | Incompatible type with Binary subtype 3 or 4 |

Two UUIDs that render identically at the application layer can map to different BSON bytes. When querying a UUID, the driver must **encode the query parameter using the representation matching stored data**; querying with subtype 4 against subtype 3 documents may find nothing.

### 4.1. Configuring UUID Representation Explicitly

With the synchronous MongoDB Java driver:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.UuidRepresentation;

public final class MongoClientFactory {
    public static MongoClient create(String connectionUri) {
        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(connectionUri))
            .uuidRepresentation(UuidRepresentation.STANDARD)
            .build();
        return MongoClients.create(settings);
    }
}
~~~

With **Spring Boot** auto-configuration on versions supporting the property:

~~~properties
spring.data.mongodb.uuid-representation=standard
~~~

If you define a custom **MongoClient** bean, verify that **MongoTemplate**, repositories, and tests use that configured client; the property above may not apply to manually constructed clients. Also check whether legacy drivers or other services write **JAVA_LEGACY**.

**Do not blindly flip a whole system to STANDARD** when legacy UUID data exists. Changing the setting alters how queries/writes serialize and how values decode; subtype 3 records may become unreadable or unqueryable. Safe conversion requires verifying the origin and byte order of **each dataset**, normalizing to subtype 4, testing with known-value UUIDs, and coordinating reader/writer rollouts.

### 4.2. Diagnosing UUIDs with Raw BSON

The **$type** operator returns **binData** for both subtype 3 and subtype 4, so inspect the subtype using Java raw BSON or Canonical Extended JSON (**$binary.subType**).

~~~javascript
// Check whether data is stored as binary or string.
db.payments.aggregate([
  {
    $group: {
      _id: { $type: "$customerId" },
      count: { $sum: 1 }
    }
  }
]);

// Inspect a few documents in mongosh.
db.payments.find({}, { customerId: 1 }).limit(5);
~~~

To determine the exact binary subtype without letting a client decode the UUID into a Java object, use **RawBsonDocument**:

~~~java
import com.mongodb.client.model.Filters;
import org.bson.BsonType;
import org.bson.RawBsonDocument;
import org.springframework.data.mongodb.core.MongoTemplate;

public final class RawUuidProbe {
    public static void inspect(MongoTemplate template, String paymentId) {
        RawBsonDocument raw = template.getCollection("payments")
            .withDocumentClass(RawBsonDocument.class)
            .find(Filters.eq("_id", paymentId))
            .first();

        if (raw == null) {
            throw new IllegalArgumentException("Document not found");
        }

        if (raw.containsKey("customerId")
                && raw.get("customerId").getBsonType() == BsonType.BINARY) {
            int subtype = Byte.toUnsignedInt(
                raw.getBinary("customerId").getType()
            );
            System.out.println("customerId subtype = " + subtype);
        } else {
            System.out.println("customerId is not BSON Binary");
        }
    }
}
~~~

In production logs, prefer recording **BSON type and subtype** rather than printing full UUIDs or customer data unnecessarily. **RawBsonDocument** is a diagnostic inspection tool—not a reason to abandon converters and handle raw bytes manually everywhere.

## 5. Date/Time: BSON Date, UTC, Precision, and Timezones

**BSON Date** stores **milliseconds** since the Unix epoch and represents an **absolute instant in time**. It **does not store a ZoneId, origin timezone, or user offset**. Do not confuse it with the BSON **Timestamp** type, which is intended for MongoDB internals like the oplog.

| Java / BSON | Meaning | Common Pitfall |
| --- | --- | --- |
| **java.time.Instant** | A point on the UTC timeline | Loses sub-millisecond precision when stored as BSON Date |
| **java.util.Date** | An instant in epoch milliseconds | String formatting changes with the formatter's timezone |
| **LocalDateTime** | Local date-time **without** a timezone | Cannot determine a unique instant without a zone convention |
| **OffsetDateTime** | Date-time with fixed offset | Preserving the original offset requires storing extra metadata; converter behavior varies |
| **ZonedDateTime** | Date-time with ZoneId and zone rules | Storing only as BSON Date loses the original ZoneId |
| **BSON Date** | Epoch milliseconds, UTC datetime | Distinct from ISO String, Long epoch, and BSON Timestamp |
| **BSON String** | Text, e.g., "2026-11-20T08:00:00Z" | Not treated as a Date by date filters or TTL indexes |

**Timezone example:** **2026-11-20 08:00 in Asia/Ho_Chi_Minh** corresponds to **2026-11-20T01:00:00Z**. If code mistakenly treats 08:00 as UTC, the stored instant shifts by **7 hours**.

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

LocalDateTime local = LocalDateTime.of(2026, 11, 20, 8, 0);
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
Instant correct = local.atZone(vietnam).toInstant();

assert correct.equals(Instant.parse("2026-11-20T01:00:00Z"));
~~~

### 5.1. Verifying LocalDateTime Codec Behavior

Spring Data MongoDB may use **Spring Data JSR-310 converters** for local types or **native Java Driver Java Time codecs**, depending on version and configuration:

- Spring Data converters for **LocalDateTime** may use **ZoneId.systemDefault()**.
- Native driver Java Time codecs configured by Spring Data use **ZoneOffset.UTC** for corresponding local types.

If a developer laptop runs in **Asia/Ho_Chi_Minh** while CI/containers run in **UTC**, the same **LocalDateTime** can produce different BSON Dates under certain converter setups. Therefore, fields representing **event timestamps** should use **Instant** and UTC conventions; fields representing **local wall-clock schedules** must store the zone or define explicit conversions.

**Do not force everything to UTC datetime if business logic requires preserving local wall-clock time.** For instance, "opens daily at 09:00 in Hanoi" is a calendar/zone rule, not a single fixed `Instant`.

### 5.2. Millisecond Precision

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

Instant before = Instant.parse("2026-11-20T01:02:03.123456789Z");
Instant expectedAfterBsonDate = before.truncatedTo(ChronoUnit.MILLIS);

assert expectedAfterBsonDate.equals(
    Instant.parse("2026-11-20T01:02:03.123Z")
);
~~~

BSON Date does not store nanoseconds; if a system requires microsecond or nanosecond fidelity, use an explicit convention (such as an extra field or epoch microseconds in a `Long`) and test accordingly. **Never** assert exact nanosecond equality on a Java `Instant` round-tripped through BSON Date and conclude the converter is broken.

### 5.3. Querying by Calendar Day: Use Half-Open Intervals

For "find transactions occurring on **2026-11-20** in Vietnam time," compute start and end boundaries **in the business timezone**, then convert to `Instant`:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Date;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate day = LocalDate.of(2026, 11, 20);

Instant from = day.atStartOfDay(zone).toInstant();
Instant to = day.plusDays(1).atStartOfDay(zone).toInstant();

Query q = Query.query(
    Criteria.where("paidAt")
        .gte(Date.from(from))
        .lt(Date.from(to))
);
~~~

This snippet illustrates a query method body, not a standalone Java file. The **[from, to)** predicate avoids fragile "23:59:59.999" arithmetic and remains exact across daylight saving transitions in other timezones. When an entity declares `Instant paidAt`, Spring Data can also map `Instant` query parameters directly; using `Date.from` here makes passing a BSON Date explicit.

Never pass a string like **"2026-11-20"** to **Criteria.gte** on a BSON Date field and expect the server to parse it. Likewise, TTL indexes require a **BSON Date** field (or an array containing Dates per MongoDB rules) and will not expire ISO strings.

## 6. Inventorying Live Data Using `$type`

Before modifying Java classes, measure the BSON type distribution in the collection. Example on **payments**:

~~~javascript
db.payments.aggregate([
  {
    $project: {
      amountType: { $type: "$amount" },
      customerIdType: { $type: "$customerId" },
      paidAtType: { $type: "$paidAt" }
    }
  },
  {
    $group: {
      _id: {
        amount: "$amountType",
        customerId: "$customerIdType",
        paidAt: "$paidAtType"
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
~~~

Aggregation **$type** returns **"missing"** for absent fields and **"null"** for explicit `null`. **"binData"** does not differentiate UUID subtypes, so use raw BSON or Canonical Extended JSON to inspect UUID formats further.

Sample each problematic group:

~~~javascript
db.payments.find(
  { amount: { $type: "string" } },
  { _id: 1, amount: 1 }
).limit(20);

db.payments.find(
  { paidAt: { $type: "string" } },
  { _id: 1, paidAt: 1 }
).limit(20);

db.payments.find(
  { customerId: { $type: "binData" } },
  { _id: 1, customerId: 1 }
).limit(20);
~~~

Inspect only small representative samples and store anonymized identifiers during production investigations. On multi-million-document collections, schedule inventory aggregations during low-load windows, monitor resources, and run **explain** if scans are expensive. Counting by **$type** still reads documents unless an index strategy supports it.

### 6.1. Checking Whether Strings Are Safely Convertible

For legacy String amounts, first run a **read-only** pipeline with **$convert** and **onError** without mutating data:

~~~javascript
db.payments.aggregate([
  { $match: { amount: { $type: "string" } } },
  {
    $project: {
      amount: 1,
      candidate: {
        $convert: {
          input: "$amount",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  { $match: { candidate: null } },
  { $limit: 20 }
]);
~~~

This example lists **strings that cannot be parsed as Decimal128**; it writes nothing. **$convert** can convert several BSON types, yet conversion does not resolve business ambiguities in malformed data. Allow conversion only for formats approved by the data owner (e.g., `.` decimal separator, no currency symbols, no typos).

## 7. Diagnosing Raw BSON with MongoTemplate

Sometimes **MappingMongoConverter** converts a value into a Java type before you notice the mismatch. To inspect raw BSON independently of entity mapping, use **RawBsonDocument**:

~~~java
import com.mongodb.client.model.Filters;
import org.bson.BsonType;
import org.bson.RawBsonDocument;
import org.springframework.data.mongodb.core.MongoTemplate;

public class PaymentBsonDiagnostics {
    public static void inspect(MongoTemplate template, String id) {
        RawBsonDocument raw = template.getCollection("payments")
            .withDocumentClass(RawBsonDocument.class)
            .find(Filters.eq("_id", id))
            .first();

        if (raw == null) {
            throw new IllegalStateException("Payment not found");
        }

        for (String field : new String[]{"amount", "customerId", "paidAt"}) {
            if (!raw.containsKey(field)) {
                System.out.println(field + ": MISSING");
                continue;
            }
            BsonType type = raw.get(field).getBsonType();
            System.out.println(field + ": " + type);
            if (type == BsonType.BINARY) {
                int subtype = Byte.toUnsignedInt(
                    raw.getBinary(field).getType()
                );
                System.out.println("  subtype=" + subtype);
            }
        }
    }
}
~~~

Do not assume default **Document.toJson()** always reveals differences between Int32, Int64, Date, or binary subtypes. Use **Canonical Extended JSON** or **RawBsonDocument** for accurate diagnostics. Log only types and subtypes; avoid logging sensitive values.

**Separate the three layers while debugging:**

| Layer | Question |
| --- | --- |
| MongoDB Server / BSON | What actual type and subtype does the field hold? Are mixed types present? |
| MongoDB Java Driver | Which UUID representation do codecs use? Can they read/write that BSON type? |
| Spring Data mapping | What Java type is declared? Are there **@Field(targetType)** annotations, custom converters, or renamed fields? |

If a repository fails while reading a document, temporarily inspect the raw document by **_id** via `MongoTemplate` to verify exact types. Resist writing a "catch-all" converter before classifying the data; overly permissive converters hide corrupt records or lose precision.

## 8. Designing Explicit Entities and Storage Contracts

A consistent example for the **payments** collection:

~~~java
package example.payments;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document("payments")
public class Payment {
    @Id
    private String id;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal amount;

    private UUID customerId;
    private Instant paidAt;

    protected Payment() {}

    public Payment(
            String id, BigDecimal amount,
            UUID customerId, Instant paidAt) {
        this.id = id;
        this.amount = amount;
        this.customerId = customerId;
        this.paidAt = paidAt;
    }

    public String getId() { return id; }
    public BigDecimal getAmount() { return amount; }
    public UUID getCustomerId() { return customerId; }
    public Instant getPaidAt() { return paidAt; }
}
~~~

Contract for this example:

- **amount:** Decimal128 per mapping definition; application validates precision/scale and valid bounds before saving.
- **customerId:** BSON Binary subtype **4**, with all writers and readers configured for **UuidRepresentation.STANDARD**.
- **paidAt:** BSON Date representing a **UTC instant** at millisecond precision; never use `LocalDateTime` for a global point in time.
- **_id:** application-defined String, never mixed with Binary UUID or ObjectId.

Never swap entity types in production immediately if the collection holds legacy formats: existing records can fail to deserialize post-deploy. Plan an **expand–migrate–contract** rollout or bounded compatibility converters during the transition.

## 9. Testing Round-Trip Behavior and Actual BSON Types

Unit tests for normalization helpers, converters, or currency math are necessary, yet cannot verify that the driver actually wrote **Decimal128**, UUID subtype 4, and BSON Date. Use **@DataMongoTest + real MongoDB** to test round-trips and inspect raw BSON.

Example for **Spring Boot 3.x / Spring Data MongoDB 4.x, Testcontainers 1.x**; adjust packages and config if targeting another major version:

~~~java
package example.payments;

import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;
import org.bson.BsonType;
import org.bson.RawBsonDocument;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import com.mongodb.client.model.Filters;

@DataMongoTest(
    properties = "spring.data.mongodb.uuid-representation=standard"
)
@Testcontainers
class PaymentBsonContractTest {

    @Container
    static final MongoDBContainer mongo = new MongoDBContainer(
        DockerImageName.parse("mongo:7.0")
    );

    @DynamicPropertySource
    static void mongoProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri", mongo::getReplicaSetUrl);
    }

    @Autowired MongoTemplate template;

    @Test
    void mustPersistAmountUuidAndInstantUsingExpectedBsonTypes() {
        UUID customerId = UUID.fromString(
            "dcd8f7fe-8760-4fc3-a412-0f110da69911"
        );
        Instant paidAt = Instant.parse(
            "2026-11-20T01:02:03.123456789Z"
        );

        Payment sample = new Payment(
            "payment-type-contract-01",
            new BigDecimal("12.30"),
            customerId,
            paidAt
        );
        template.remove(
            org.springframework.data.mongodb.core.query.Query.query(
                org.springframework.data.mongodb.core.query.Criteria
                    .where("_id").is(sample.getId())
            ),
            Payment.class
        );
        template.insert(sample);

        RawBsonDocument raw = template.getCollection("payments")
            .withDocumentClass(RawBsonDocument.class)
            .find(Filters.eq("_id", sample.getId()))
            .first();
        assertNotNull(raw);
        assertEquals(
            BsonType.DECIMAL128,
            raw.get("amount").getBsonType()
        );
        assertEquals(
            BsonType.BINARY,
            raw.get("customerId").getBsonType()
        );
        assertEquals(
            4,
            Byte.toUnsignedInt(raw.getBinary("customerId").getType())
        );
        assertEquals(
            BsonType.DATE_TIME,
            raw.get("paidAt").getBsonType()
        );

        Payment reloaded = template.findById(sample.getId(), Payment.class);
        assertNotNull(reloaded);
        assertEquals(0, sample.getAmount().compareTo(reloaded.getAmount()));
        assertEquals(customerId, reloaded.getCustomerId());
        assertEquals(
            paidAt.truncatedTo(ChronoUnit.MILLIS),
            reloaded.getPaidAt()
        );
    }
}
~~~

**What this test proves:** it verifies byte-level BSON types on disk and Java values after reverse mapping. Use a **MongoDB version close to production**, confirm the **MongoClient** bean's UUID settings and Spring Data version; if a global `BigDecimal` converter changes, this test catches the drift early.

With **ReactiveMongoTemplate**, apply the same checks while subscribing to publishers and awaiting completion, e.g., via **StepVerifier**. A reactive operation that is only constructed without subscribing has not written anything.

Additional tests to include:

| Scenario | What to Prove |
| --- | --- |
| **BigDecimal("0.1")**, negative numbers, boundary values | Not routed through `Double` causing precision errors |
| Numbers exceeding `Decimal128` limits | Explicit failure rather than silently saving rounded values |
| Stored standard UUID | Querying by **Java UUID** finds the exact document |
| Legacy subtype 3 UUID | Migration/compatibility path respects source byte order |
| BSON Date with nanosecond input | Round-trip matches down to millisecond precision |
| Calendar day in business timezone | **[start, end)** query captures first/last boundary records |
| `amount`, `customerId`, or `paidAt` stored as string | Flags contract violation instead of silently accepting |
| Missing/null fields and historical data | Consistent default, rejection, or migration behavior |

## 10. Fixing Legacy Data: Inventory, Test, Then Migrate

Safe procedure for an active collection:

1. **Lock down the target contract** for every field: BSON type, precision/scale, UUID representation, timezone, and query/index support.
2. **Inventory first** using **$type**, inspect UUID subtypes, and count documents in each group.
3. **Quarantine unconvertible values**; never guess amounts from dirty strings or instants from zoneless timestamps.
4. **Build and test migration scripts** on a copy of the data; log per-batch results and checkpoints for safe re-runs.
5. **Use conditional updates** matching current type/version so concurrent application writes are not overwritten.
6. **Expand readers/writers** or run a compatibility mode during transition, and contract the schema only after reconciliation finishes.
7. **Reconcile afterward:** verify counts, business totals, queries, indexes, and round-trip tests; prepare a recovery plan.

### 10.1. String Amounts

For strings verified to contain valid numbers, MongoDB can use **$convert** in an update pipeline to migrate to `Decimal128`. Before writing, run an inventory pipeline as in Section 6.1 on a data copy; verify precision, invalid separators, and **onError/onNull** handling.

Never run **$toDecimal** blindly and ignore conversion failures: a single invalid document can abort a batch. **$convert** with explicit `onError` can flag bad records or retain old values, but never mark an unconverted document as migrated.

### 10.2. Legacy UUIDs

There is no single universal expression that converts **BinData subtype 3** into subtype 4 accurately for every writer. You must know whether original records were written using **JAVA_LEGACY**, **CSHARP_LEGACY**, or **PYTHON_LEGACY** and decode the logical UUID using the matching codec before re-writing as `STANDARD`. Never overwrite subtype 3's type byte to 4 directly without accounting for byte order.

When multiple applications share a collection, coordinate reader/writer rollouts to prevent creating newly mixed data. Pass fixed known-value UUIDs through every migration step to catch byte-order errors immediately.

### 10.3. String or Long Timestamps

Determine the exact meaning of source data first:

- Strings with **Z** or explicit offset: parse directly to an instant.
- Local strings lacking offset/zone: select **ZoneId from the data source**; never guess the server's timezone.
- Long epochs: verify whether units are **seconds, milliseconds, or microseconds** before converting. Treating seconds as milliseconds produces wildly wrong dates.

**$dateFromString** can parse formatted text, provided you supply **format/timezone** for offset-less strings and handle **onError/onNull**. Never drop original fields before validating results on a test copy.

## 11. Debugging Empty Results When No Exception Is Thrown

A classic silent type bug in queries:

~~~java
// Wrong for a collection storing paidAt as BSON Date:
Query wrong = Query.query(
    Criteria.where("paidAt").gte("2026-11-20T00:00:00Z")
);

// Right when comparing against an absolute instant:
Query correct = Query.query(
    Criteria.where("paidAt").gte(
        java.util.Date.from(
            java.time.Instant.parse("2026-11-20T00:00:00Z")
        )
    )
);
~~~

When calling **MongoTemplate.find(query, Entity.class)**, mapping may convert query values using property types, converters, and metadata. The snippet above highlights why you must **know the exact BSON sent to the server**, especially when querying through lower-level APIs, **Document**, raw drivers, or mixed-type collections. Confirm with command monitoring or tests to inspect the actual BSON query and test in `mongosh` against sample documents.

Another example: **customerId** is stored as Binary subtype 3, while a repository method **findByCustomerId(UUID)** runs after switching settings to `STANDARD`. If queries return nothing, compare the database field's binary subtype with the driver's encoded query parameter subtype. Never change UUIDs to **toString()** simply because queries start returning some records; that introduces yet another schema variant.

For monetary queries, verify BSON types and scales in sums and comparisons. A rounded `Double` **cannot recover lost decimal digits merely by casting to Decimal128**; recovering accurate values requires upstream business sources or independent reconciliation.

## 12. Hands-on Diagnostic Exercise

**Scenario:** the `payments` collection contains three generations of records:

- Version A stored **amount** as String, **customerId** as Java legacy UUID, and **paidAt** as a local datetime string.
- Version B stored **amount** as Double, UUID as String, and **paidAt** as BSON Date.
- Version C uses the new contract: **Decimal128**, STANDARD subtype 4 UUID, and **Instant/BSON Date**.

Tasks:

1. Run a **$type** aggregation to count numeric, string, and date groups, broken down by application version if metadata exists.
2. Sample raw BSON, inspect **customerId** subtypes, and distinguish binary UUIDs from strings.
3. Check whether amount values fit within `Decimal128` limits and identify `Double` precision loss; flag records that cannot be automatically recovered accurately.
4. Write a **MongoTemplate** test asserting Contract C: **amount** is `Decimal128`, **customerId** is Binary subtype 4, and **paidAt** is BSON Date.
5. Determine the valid **ZoneId** for Version A from its data source; test day boundaries and compare `Instant` before and after conversion.
6. Design a checkpointed batch migration with conditional updates, and verify all three groups are queryable from Java afterward.

**Passing Criteria:** every conclusion is backed by **actual BSON types and business rules**, covered by round-trip tests; ambiguous or precision-lost records are flagged for review instead of fabricated.

## 13. Troubleshooting Checklist

- [ ] Identify sample document, field name, failing code path, and nested exceptions.
- [ ] Inventory **$type**: int/long/double/decimal/string, binData/string, date/string/long/missing.
- [ ] For UUIDs, inspect **subtype 3 vs. 4** and the legacy writer's byte order.
- [ ] For numbers, verify range, precision, scale, overflow, and Spring Data `BigDecimal` converter version behavior.
- [ ] For dates/times, confirm epoch unit, UTC instant vs. local wall time with `ZoneId`.
- [ ] Confirm **MongoClientSettings.uuidRepresentation** and Spring Data Java Time converter settings.
- [ ] Read raw BSON or Canonical Extended JSON so mapping layers do not mask stored types.
- [ ] Write round-trip tests inspecting persisted BSON, including null/missing and boundary cases.
- [ ] Test migrations on copied data with batch limits, checkpoints, idempotency, and reconciliation.
- [ ] Never drop legacy formats in production while old writers remain active or without a recovery plan.

## 14. References

1. [MongoDB Manual — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/): distinguishing Int32, Int64, Double, Decimal128, Binary, Date, and Timestamp.
2. [MongoDB Manual — Comparison/Sort Order](https://www.mongodb.com/docs/manual/reference/bson-type-comparison-order/): comparison behavior across BSON types and numeric comparisons.
3. [MongoDB Manual — Type Bracketing](https://www.mongodb.com/docs/manual/reference/mql/query-predicates/type-bracketing/): query matching by BSON type.
4. [Spring Data MongoDB — Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html): `BigDecimalRepresentation`, Java Time converters, and `targetType`.
5. [MongoDB Java Driver — Upgrade Driver Versions](https://www.mongodb.com/docs/drivers/java/sync/current/reference/upgrade/): default UUID representation changes and subtype decoding.
6. [Spring Boot — Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): MongoDB UUID configuration properties.
7. [MongoDB Manual — $convert](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/): validating numeric/date conversions and error handling.
8. [MongoDB Java Driver — Extended JSON](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/document-data-format-extended-json/): Canonical vs. Relaxed Extended JSON for inspecting types.

**Technical Takeaway:** when Java and BSON diverge, the right fix starts by **verifying actual stored types**, then standardizing **numeric / UUID / date-time** contracts, aligning driver and converter configuration, and proving correctness with **raw BSON + round-trip + query** tests. Changing entities or global settings before inventorying legacy data easily turns a visible conversion failure into silent data corruption.
