# Boot configuration changes, data types, and UUID representation

Upgrading **Spring Boot** or **Spring Data MongoDB** is not just changing a version number in a build file. An application may connect successfully yet ignore renamed properties, write monetary fields using a different BSON type than before, or fail to find documents because the **UUID representation** changed. These silent errors are more dangerous than startup failures: they surface late and leave old and new data incompatible.

In the **SPRING_DATA_MONGODB** module, the **Versions and Upgrades** chapter focuses on a concrete scenario: migrating an application from **Spring Boot 3.5 / Spring Data MongoDB 4.x** to **Spring Boot 4.x / Spring Data MongoDB 5.x**. This article explains changes in **MongoDB configuration**, **Java/BSON types**, **BigDecimal**, and **UUID subtype 3 vs. subtype 4**, then shows how to verify behavior through **MongoTemplate**, repositories, legacy data, and a real MongoDB instance.

**Guiding principle:** upgrading the framework and changing data formats are **two separate changes**. Lock in the existing encoding/decoding behavior while upgrading the framework, measure, and test; if you want to standardize the schema, run a planned migration afterward.

## 1. What will you learn?

After this lesson, you will be able to:

1. Cross-reference key MongoDB properties between **Boot 3.5** and **Boot 4.x**.
2. Distinguish configuration belonging to the **MongoDB Java Driver** from configuration belonging to **Spring Data MongoDB**.
3. Choose how to store **BigDecimal/BigInteger** explicitly and inspect **BSON String vs. Decimal128**.
4. Explain why the same **Java UUID** can become **Binary subtype 3** or **subtype 4**, and how to preserve compatibility with stored data.
5. Check changes affecting **Instant, LocalDateTime, integers, Double, String, _id**, custom converters, and repository queries.
6. Design an upgrade with a baseline, round-trip tests, reconciliation, rollout, and a rollback path.

## 2. First, separate the four version layers

| Layer | Example | Impact on upgrade |
| --- | --- | --- |
| **Spring Boot** | 3.5 → 4.x | Property binding, auto-configuration, starter/test packages, lifecycle, and Actuator |
| **Spring Data MongoDB** | 4.x → 5.x | MappingMongoConverter, repositories, custom conversions setup, certain APIs/defaults |
| **MongoDB Java Driver** | Driver selected by Boot/Spring Data BOM | BSON codecs, UuidRepresentation, TLS, connection pool, wire protocol, and supported Java versions |
| **MongoDB Server + FCV** | Current cluster version/FCV | Query/aggregation operators, indexes, transactions, and permitted server features |

**Spring Data MongoDB 5.x requires MongoDB Java Driver 5.6 or later** and no longer supports the 4.x driver generation. This is a requirement from the Spring Data 5.x migration guide; even when picking the right Boot BOM, inspect the dependency tree to catch any dependency pinning an incompatible driver.

Each layer can vary independently. For example, **Spring Boot upgrades cleanly** yet an application-defined custom **MongoClient** still sets **UuidRepresentation.JAVA_LEGACY**, or another service writes UUIDs using STANDARD. What you must verify is **the configuration and BSON actually used**, not just a green build message.

~~~mermaid
flowchart TD
    A["Upgrade Spring Boot / Spring Data MongoDB"] --> B["Cross-check properties and auto-configuration"]
    B --> C["Verify actual MongoClient, driver, converters"]
    C --> D["Inventory legacy BSON data"]
    D --> E{"Change representation now?"}
    E -- "No" --> F["Lock representation compatible with old data"]
    E -- "Yes" --> G["Design separate migration + transitional reader/writer"]
    F --> H["Repository + integration + round-trip tests"]
    G --> H
    H --> I["Reconciliation, rollout, monitoring, and recovery"]
~~~

## 3. MongoDB properties renamed in Boot 4

Spring Boot 4 separates **MongoDB client configuration properties** more clearly from **Spring Data properties**. Most connection properties formerly under **spring.data.mongodb** move to **spring.mongodb**; properties tied specifically to repositories, converters, or mapping remain under **spring.data.mongodb**.

| Purpose | Boot 3.5 | Boot 4.x | Things to watch |
| --- | --- | --- | --- |
| Connection URI | **spring.data.mongodb.uri** | **spring.mongodb.uri** | Check every profile, environment variable, and test |
| Database | **spring.data.mongodb.database** | **spring.mongodb.database** | Do not assume URI and separate database property always share precedence |
| Host/port | **spring.data.mongodb.host / port** | **spring.mongodb.host / port** | Only needed when not using a full URI |
| Username/password | **spring.data.mongodb.username / password** | **spring.mongodb.username / password** | Never commit secrets to the repository |
| Authentication database | **spring.data.mongodb.authentication-database** | **spring.mongodb.authentication-database** | Must be right when auth DB differs from app DB |
| Replica set name | **spring.data.mongodb.replica-set-name** | **spring.mongodb.replica-set-name** | Match actual topology |
| TLS/SSL | **spring.data.mongodb.ssl.enabled / bundle** | **spring.mongodb.ssl.enabled / bundle** | Never disable certificate verification to mask config issues |
| UUID | **spring.data.mongodb.uuid-representation** | **spring.mongodb.representation.uuid** | Critical whenever collections store UUIDs |
| Auto index creation from mapping | **spring.data.mongodb.auto-index-creation** | **Unchanged** | Do not enable automatically just because of an upgrade |
| Field naming strategy | **spring.data.mongodb.field-naming-strategy** | **Unchanged** | Changing strategy alters BSON field names |
| GridFS bucket/database | **spring.data.mongodb.gridfs.bucket / database** | **Unchanged** | Review if using GridFS |
| Repository type | **spring.data.mongodb.repositories.type** | **Unchanged** | Sync/reactive depends on classpath and config |
| BigDecimal representation | No equivalent property in the new Boot 4 style | **spring.data.mongodb.representation.big-decimal** | Explicitly choose **string** or **decimal128** |
| MongoDB health indicator | **management.health.mongo.enabled** | **management.health.mongodb.enabled** | Check Actuator and dashboards |
| MongoDB command/pool metrics | **management.metrics.mongo.command.enabled** and **management.metrics.mongo.connectionpool.enabled** | **management.metrics.mongodb.command.enabled** and **management.metrics.mongodb.connectionpool.enabled** | Check metrics, alerts, and dashboards after rename |

This mapping applies to the **Boot 3.5 → Boot 4.x** transition, not as a retroactive rule for every historical Boot release. When moving to a specific minor/patch release, check that version's **Common Application Properties** documentation. Do not assume Boot will automatically bind old property names to new ones via compatibility fallbacks.

### 3.1. Before and after application.yml examples

**Boot 3.5**, application currently using Java legacy UUIDs:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://localhost:27017/billing
      uuid-representation: java-legacy
      auto-index-creation: false

management:
  health:
    mongo:
      enabled: true
~~~

**Boot 4.x**, initial phase **preserving current BSON formats**:

~~~yaml
spring:
  mongodb:
    uri: mongodb://localhost:27017/billing
    representation:
      uuid: java-legacy
  data:
    mongodb:
      representation:
        big-decimal: string
      auto-index-creation: false

management:
  health:
    mongodb:
      enabled: true
~~~

These values are **local environment examples**. In production, use managed secrets/connection settings; never hardcode credentials. **uuid: java-legacy** is only appropriate if you verified legacy writers used Java legacy; **big-decimal: string** only preserves the old format when existing BigDecimal data is BSON String.

If a collection has stored UUID subtype 4 and Decimal128 from the start, a more fitting Boot 4 config is:

~~~yaml
spring:
  mongodb:
    representation:
      uuid: standard
  data:
    mongodb:
      representation:
        big-decimal: decimal128
~~~

**Never flip both settings at once on an uninventoried legacy database**. Both options affect the BSON written and the BSON of query parameters after the framework upgrade.

### 3.2. Verify how MongoClient is actually created

**Spring Boot auto-configuration** applies MongoDB properties to the auto-configured **MongoClientSettings/MongoClient**. If your application defines a custom **MongoClient bean**, custom **MongoDatabaseFactory**, or custom **MappingMongoConverter**, some properties from application.yml may be ignored or overridden.

Check common cases:

1. Which MongoClient does the sync **MongoTemplate** use? Are there multiple MongoClients for different databases?
2. Which MongoClient does reactive **ReactiveMongoTemplate** use? Does it share the same UUID policy or converters as sync?
3. Are there any **MongoClientSettingsBuilderCustomizer**, **AbstractMongoClientConfiguration**, **MongoCustomConversions**, or custom codec registries?
4. Do the URIs in application.yml, environment variables, Helm charts, ConfigMaps, and runtime arguments match?
5. In tests, do **@DynamicPropertySource**, service connections, or test profiles override the URI differently from production?

Do not conclude UUID configuration is right just because the property appears in YAML. Write tests that save and read using the exact bean injected into services/repositories.

## 4. BigDecimal, BigInteger, and String vs. Decimal128

**Java BigDecimal** does not uniquely determine a MongoDB BSON type. In earlier Spring Data MongoDB generations, BigDecimal/BigInteger were often mapped to **BSON String**. Starting with **Spring Data MongoDB 5.0**, support configuration classes **no longer silently choose a default representation** for these two types; applications must configure one explicitly if they use them.

| Java | Stored BSON | Query implications |
| --- | --- | --- |
| **BigDecimal("12.30")** → String | **"12.30"** | String comparisons use lexicographical order, unlike numeric comparison |
| **BigDecimal("12.30")** → Decimal128 | **NumberDecimal("12.30")** | Supports MongoDB numeric comparisons and arithmetic operators |
| **Double** | BSON Double | Risks binary floating-point rounding errors for money |
| **Long** | BSON Int64 | Suitable for integers or minor currency units within range |

**Example:** if string values **"100"** and **"20"** are sorted ascending as strings, **"100"** can come before **"20"**; with Decimal128, numeric order is **20 then 100**. Changing the default converter can alter queries, sorting, aggregations, and indexes even though the entity field remains **BigDecimal**.

### 4.1. Keeping BSON String during the initial framework upgrade

If the goal of the deployment is to **upgrade Boot/Spring Data first**, you can configure:

~~~properties
spring.data.mongodb.representation.big-decimal=string
~~~

This keeps compatibility with existing String data and is **not a long-term recommendation for every monetary field**. Once the framework is stabilized, you can plan migrating fields that need numeric queries to **Decimal128** and evaluate index/query impacts.

### 4.2. Using Decimal128 intentionally

For a specific field:

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
    private BigDecimal total;

    protected Invoice() {}

    public Invoice(String id, BigDecimal total) {
        this.id = id;
        this.total = total;
    }

    public String getId() { return id; }
    public BigDecimal getTotal() { return total; }
}
~~~

**@Field(targetType = FieldType.DECIMAL128)** explicitly declares the desired BSON type for this property. If an app needs another default across many fields, Spring Data 5 also lets you configure **BigDecimalRepresentation** via **MongoCustomConversions**; align that choice with Boot properties and avoid creating two conflicting mechanisms.

**Decimal128 has precision/exponent limits** (34 significant digits). **Java BigDecimal** can represent values outside those bounds. Do not convert every BigDecimal to Decimal128 without checking extreme values and rounding policies. Never route through Double during migration if exact decimal precision matters.

### 4.3. Inventory BSON types before changing anything

~~~javascript
db.invoices.aggregate([
  { $group: { _id: { $type: "$total" }, count: { $sum: 1 } } },
  { $sort: { count: -1 } }
]);

db.invoices.find(
  { total: { $type: "string" } },
  { _id: 1, total: 1 }
).limit(5);

db.invoices.find(
  { total: { $type: "decimal" } },
  { _id: 1, total: 1 }
).limit(5);
~~~

**$type** distinguishes String, Decimal128, Double, Int32, Int64, null, and missing at the data level. It does not fix business errors by itself. If BSON Double was stored earlier, converting to Decimal128 **cannot recover** precision already lost when the Double was written.

## 5. UUID representation: subtype 3 and subtype 4

UUID in Java is **java.util.UUID**, whereas MongoDB can store UUIDs as **BSON Binary**, **BSON String**, or a custom structure. For BSON Binary, both the subtype and byte order must be clearly defined:

| Representation | BSON binary subtype | Encoding |
| --- | --- | --- |
| **STANDARD** | **4** | Standard byte order, cross-language compatible |
| **JAVA_LEGACY** | **3** | Legacy Java driver-specific byte order |
| **CSHARP_LEGACY** | **3** | Legacy C#-specific byte order |
| **PYTHON_LEGACY** | **3** | Legacy Python byte order |
| **UNSPECIFIED** | No format selected | Driver may refuse to encode Java UUIDs, forcing explicit config |
| UUID stored as String | BSON String | Does not match any Binary subtype |

**Subtype 3 alone is not enough to infer the logical UUID:** across Java/C#/Python legacy encodings, bytes inside subtype 3 are ordered differently. Flipping raw bytes to subtype 4 without decoding using the right legacy representation can corrupt IDs.

### 5.1. Impact of changing the configuration

Suppose a service stored **customerId** using **JAVA_LEGACY/subtype 3**. After upgrading, you set **uuid: standard**. A repository call:

~~~java
// Repository:
// Optional<Customer> findByCustomerId(UUID customerId);

UUID id = UUID.fromString(
    "00112233-4455-6677-8899-aabbccddeeff"
);
repository.findByCustomerId(id);
~~~

With **STANDARD**, the UUID parameter serializes to **Binary subtype 4**. Legacy data stored as subtype 3 will not match, returning **Optional.empty()** even though the record exists. Some read paths for legacy data may also throw codec/conversion exceptions. Do not "fix" this by converting UUIDs with **toString()** across repositories: that produces **BSON String** and mixes data formats further.

**Safe choice during framework upgrade:** retain the representation verified from existing data (for example **spring.mongodb.representation.uuid=java-legacy**), verify operation, and plan the move to STANDARD in an independent rollout. If the database already contains multiple representations, build a targeted read/migration strategy instead of expecting one property to cover all variants.

### 5.2. Configuring the Java driver when creating a client manually

If the application manages **MongoClient** directly, verify the driver-level setting:

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.UuidRepresentation;

public final class MongoClientFactory {
    private MongoClientFactory() {}

    public static MongoClient createLegacyClient(String uri) {
        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .uuidRepresentation(UuidRepresentation.JAVA_LEGACY)
            .build();
        return MongoClients.create(settings);
    }
}
~~~

This example uses **JAVA_LEGACY** only for a **compatibility phase**. An application writing only new data that has standardized on STANDARD should set **UuidRepresentation.STANDARD**. When Boot auto-configures **MongoClient**, prefer the property matching your Boot version; when declaring a client manually, ensure **MongoTemplate**, repositories, and **ReactiveMongoTemplate** all use a client with the right policy.

### 5.3. Inspecting actual subtypes with raw BSON

In **mongosh**, first check how many documents have Binary values:

~~~javascript
db.customers.aggregate([
  {
    $group: {
      _id: { $type: "$customerId" },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
~~~

**$type = binData** does not distinguish subtype 3 from subtype 4. With the Java driver, use **RawBsonDocument** to read without entity mapping:

~~~java
import com.mongodb.client.model.Filters;
import org.bson.BsonType;
import org.bson.RawBsonDocument;
import org.springframework.data.mongodb.core.MongoTemplate;

public class UuidBsonProbe {
    public static int subtype(MongoTemplate template, String documentId) {
        RawBsonDocument raw = template.getCollection("customers")
            .withDocumentClass(RawBsonDocument.class)
            .find(Filters.eq("_id", documentId))
            .first();

        if (raw == null) {
            throw new IllegalStateException("Missing document");
        }
        if (!raw.containsKey("customerId")
                || raw.get("customerId").getBsonType() != BsonType.BINARY) {
            throw new IllegalStateException("customerId is not binary");
        }

        return Byte.toUnsignedInt(raw.getBinary("customerId").getType());
    }
}
~~~

If a UUID is used **as _id** of the document, remember queries on _id are also subject to representation. In this example _id is **String** so diagnostics are unaffected by UUID lookup mismatches on the key.

### 5.4. Converting a legacy UUID to standard properly

Once you are **certain** the data came from a Java legacy writer, you can illustrate the *in-memory* conversion:

~~~java
import java.util.UUID;
import org.bson.BsonBinary;
import org.bson.UuidRepresentation;

public class UuidMigrationExample {
    public static BsonBinary migrateJavaLegacy(BsonBinary oldValue) {
        if (Byte.toUnsignedInt(oldValue.getType()) != 3) {
            throw new IllegalArgumentException("Expected legacy subtype 3");
        }

        UUID logicalUuid = oldValue.asUuid(UuidRepresentation.JAVA_LEGACY);
        return new BsonBinary(logicalUuid, UuidRepresentation.STANDARD);
    }
}
~~~

This conversion **has not written anything to MongoDB yet**. In a real migration, read documents in batches, persist checkpoints, apply conditional updates matching **_id + old BSON value** to avoid overwriting concurrent writers, and verify that the same logical UUID is recovered after writing subtype 4. Never run this against C# or Python legacy values without verifying the source byte order.

## 6. Temporal, numeric, and _id types also need regression tests

UUID and BigDecimal are two hot spots when upgrading to Spring Data 5, but **BSON types** in general must be preserved:

| Java/annotation | Common BSON type | What to verify |
| --- | --- | --- |
| **Instant** | BSON Date (epoch milliseconds) | UTC and millisecond precision; do not assume nanosecond storage |
| **LocalDateTime** | BSON Date via converter or chosen strategy | Uses UTC or **ZoneId.systemDefault()**? Do values shift time zones? |
| **OffsetDateTime/ZonedDateTime** | Depends on application converters | BSON Date does not natively preserve original offset/ZoneId |
| **Integer** | Int32 | Boundary values, conversion when old data is Int64/String |
| **Long** | Int64 | Overflow and seconds vs. milliseconds convention if storing timestamps |
| **Double** | Double | Potential decimal precision loss |
| **BigDecimal** | String or Decimal128 | Configured representation and query requirements |
| **@Id String** | String or ObjectId depending on mapping/conversion | Rules for converting ObjectId-shaped strings; test legacy data |
| **@MongoId** | Based on declared type/FieldType | Understand differences from legacy @Id and _id rules |

### 6.1. Instant vs. LocalDateTime

**Instant** represents an absolute point in time. **LocalDateTime** only holds date and time **without** a time zone. With a converter relying on **system default timezone**, CI running in UTC and a server running in **Asia/Ho_Chi_Minh** can write two different BSON Dates from the same LocalDateTime value.

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

LocalDateTime local = LocalDateTime.of(2026, 11, 20, 8, 0);
Instant expected = local
    .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
    .toInstant();

assert expected.equals(Instant.parse("2026-11-20T01:00:00Z"));
~~~

During a framework upgrade, check the choice of **Spring Data JSR-310 converters** vs. **native Java Time codecs**. UTC vs. system-timezone rules differ by configuration. For event creation/modification timestamps, prefer **Instant** and UTC conventions; if local wall-clock time or original ZoneId must be retained, store them explicitly.

### 6.2. @Id, @MongoId, and key representation changes

A Java **String** key is sometimes converted by Spring Data into an **ObjectId** if the string is a valid ObjectId hex representation and the mapping uses **@Id**. Upgrading converters or switching to **@MongoId** can cause the same string to be sent in filters as a different BSON type. Consequently, **findById**, updates, or deletes return empty even though the document exists.

Before altering annotations or converters, inspect the BSON type of **_id**; never alter schema mappings blindly to silence an exception. If a collection already mixes ObjectId and String, establish explicit migration/transitional read rules instead of guessing from string format.

## 7. Pre-upgrade inventory workflow

### 7.1. Compile a configuration inventory

Record the following details for the **actually running application**:

| Group | Evidence to record |
| --- | --- |
| Runtime | Boot, Spring Data MongoDB, Java driver, JDK, BOM, and dependency tree |
| MongoDB | Server version, FCV, topology, actual URI/database (secrets masked) |
| Boot | MongoDB property values in active profiles, env vars, and overrides |
| Client | Auto-configured MongoClient vs. custom bean, UUID representation, codec registry |
| Mapping | MappingMongoConverter, MongoCustomConversions, **@Field/@Id/@MongoId**, Java Time strategy |
| Schema | BSON types of monetary fields, UUIDs, date/time fields, and _id on existing data |
| Read/write paths | Services, jobs, and batch writers still on older versions |
| Queries | Repository methods, Criteria, aggregations, and indexes sensitive to BSON types |

**Note:** record connection strings only with passwords masked; never print secrets in upgrade reports.

### 7.2. Raw BSON statistics from MongoDB

For an **orders** collection:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      amountType: { $type: "$amount" },
      customerIdType: { $type: "$customerId" },
      createdAtType: { $type: "$createdAt" },
      idType: { $type: "$_id" }
    }
  },
  {
    $group: {
      _id: {
        amount: "$amountType",
        uuid: "$customerIdType",
        time: "$createdAtType",
        id: "$idType"
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
~~~

In the aggregation, **$type** reveals mixes of **string, decimal, double, long, date, binData, null, and missing**. For UUID **binData**, add subtype checks on raw BSON. On large production datasets, schedule execution carefully to avoid unexpected load spikes.

Inspect a few representative documents using Canonical Extended JSON or **RawBsonDocument** to confirm, instead of relying on Java objects already transformed by converters.

## 8. Write tests before changing versions

A test that only checks "the application starts" is not enough. You need at least three groups:

1. **BSON contract tests:** write using the application's actual **MongoTemplate/repositories** and verify the persisted BSON types.
2. **Read compatibility tests:** read unmigrated legacy documents under the new config; query by UUID, BigDecimal, and timestamps against old data.
3. **Integration tests:** run critical services, indexes/queries/transactions, or reactive flows against a real MongoDB instance, including error paths.

### 8.1. Sample entity and Boot 4 test

Example entity:

~~~java
package example.upgrade;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document("upgrade_probes")
public class UpgradeProbe {
    @Id
    private String id;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal amount;

    private UUID customerId;
    private Instant occurredAt;

    protected UpgradeProbe() {}

    public UpgradeProbe(
            String id, BigDecimal amount,
            UUID customerId, Instant occurredAt) {
        this.id = id;
        this.amount = amount;
        this.customerId = customerId;
        this.occurredAt = occurredAt;
    }

    public String getId() { return id; }
    public BigDecimal getAmount() { return amount; }
    public UUID getCustomerId() { return customerId; }
    public Instant getOccurredAt() { return occurredAt; }
}
~~~

In **Spring Boot 4.0**, **@DataMongoTest** lives in package **org.springframework.boot.data.mongodb.test.autoconfigure**; in Boot 3.x, the usual package was **org.springframework.boot.test.autoconfigure.data.mongo**. That is one concrete import migration example when updating starter/test infrastructure.

~~~java
package example.upgrade;

import static org.junit.jupiter.api.Assertions.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;
import com.mongodb.client.model.Filters;
import org.bson.BsonType;
import org.bson.RawBsonDocument;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.mongodb.test.autoconfigure.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest(properties = {
    "spring.mongodb.representation.uuid=standard",
    "spring.data.mongodb.representation.big-decimal=decimal128"
})
class UpgradeProbeBsonContractTest {

    @Autowired MongoTemplate template;

    @Test
    void writesExpectedBsonAndReadsSameLogicalValues() {
        UUID uuid = UUID.fromString(
            "00112233-4455-6677-8899-aabbccddeeff"
        );
        Instant moment = Instant.parse(
            "2026-11-20T01:02:03.123456789Z"
        );
        String id = "upgrade-contract-01";

        template.remove(
            org.springframework.data.mongodb.core.query.Query.query(
                org.springframework.data.mongodb.core.query.Criteria
                    .where("_id").is(id)
            ),
            UpgradeProbe.class
        );
        template.insert(new UpgradeProbe(
            id, new BigDecimal("12.30"), uuid, moment
        ));

        RawBsonDocument raw = template.getCollection("upgrade_probes")
            .withDocumentClass(RawBsonDocument.class)
            .find(Filters.eq("_id", id))
            .first();
        assertNotNull(raw);
        assertEquals(BsonType.DECIMAL128, raw.get("amount").getBsonType());
        assertEquals(BsonType.BINARY, raw.get("customerId").getBsonType());
        assertEquals(4, Byte.toUnsignedInt(
            raw.getBinary("customerId").getType()
        ));
        assertEquals(BsonType.DATE_TIME, raw.get("occurredAt").getBsonType());

        UpgradeProbe readBack = template.findById(id, UpgradeProbe.class);
        assertNotNull(readBack);
        assertEquals(0, new BigDecimal("12.30")
            .compareTo(readBack.getAmount()));
        assertEquals(uuid, readBack.getCustomerId());
        assertEquals(moment.truncatedTo(ChronoUnit.MILLIS),
            readBack.getOccurredAt());
    }
}
~~~

**Run prerequisites:** this test requires a real MongoDB instance from **Testcontainers** or a dedicated test database, with Boot 4's **spring.mongodb.uri** pointing to the right endpoint. **@DataMongoTest** configures only the test slice and does not automatically start a server in every setup. Do not share the **upgrade_probes** collection with production or parallel test suites without isolation.

This test verifies **STANDARD/subtype 4**. To verify a framework upgrade that **preserves Java legacy data**, run a similar test with **uuid=java-legacy**, expecting subtype **3**; more importantly, the legacy fixture must be written by the old version or via **BsonBinary(UUID, JAVA_LEGACY)**, then read back by the new application. That catches migration bugs that testing only freshly written data misses.

### 8.2. Minimum regression matrix

| Case | Required evidence |
| --- | --- |
| Boot 3.5 reading/writing legacy BSON | Capture baseline BSON types and query results |
| Boot 4 configured for legacy data | Reads same documents, queries legacy UUIDs, writes expected subtype/format |
| Boot 4 STANDARD on migrated data | UUID subtype 4, queries and round-trips succeed |
| Legacy String BigDecimal | Readable in compatibility mode; sorting/querying matches legacy data rules |
| New Decimal128 BigDecimal | BSON decimal, no unintended rounding; numeric aggregations work |
| LocalDateTime across time zones | No instant shift outside business rules |
| Long/Integer/_id | Boundary values and key BSON types remain as expected |
| Reactive repository/MongoTemplate | Publishers are subscribed and perform real reads/writes, not just Mono/Flux creation |
| Indexes, transactions, aggregations | Run properly on target topology and server/FCV |

Never claim "compatible" based solely on unit tests with mocked repositories, because mocks do not serialize UUID parameters or read real BSON.

## 9. Phased, reversible upgrade plan

**Phase A — Survey and lock the contract**

1. Record actual versions of Boot, Spring Data, driver, server, and FCV.
2. Inventory each sensitive field: BSON type, UUID subtype, time zone, indexes, and boundary values.
3. Identify whether other services, batch jobs, or apps still write the legacy format.
4. Save test fixtures containing old-version data, especially Java legacy UUIDs and String amounts.

**Phase B — Upgrade the framework, preserve old BSON**

1. Update properties to the Boot 4 namespace; set UUID and BigDecimal **to match existing data**.
2. Check the BOM, starters, and changed APIs/imports; never force driver 4.x alongside Spring Data 5.x.
3. Verify the active MongoClient, SSL/auth, mapping converters, and index migrations.
4. Run unit, repository, integration, round-trip, and real legacy-data read tests in staging.

**Phase C — Migrate data if adopting a new target format**

1. Only after deployment is stable, design a migration from UUID subtype 3 to subtype 4 or BigDecimal String to Decimal128.
2. Dry-run on a data copy; identify unconvertible records, retry strategies, and rollback plans.
3. Migrate in batches, persist checkpoints **after each batch succeeds**, and use conditional updates matching old BSON values.
4. Coordinate writers to prevent mixed formats during the cutover; then switch system-wide config to STANDARD/DECIMAL128.
5. Reconcile document counts, BSON types, logical UUIDs, monetary totals, and queries.

**Phase D — Lock in the new schema**

Only remove legacy compatibility converters/readers once no old data or old writers remain. Add BSON contract tests in CI so future upgrades do not accidentally reintroduce subtype 3 or String storage.

**Rollback note:** once new data has been written as subtype 4 or Decimal128, rolling back the application artifact to an older version can cause the old version to misread those records. Recovery plans must account for both **the application and the BSON schema**, not just redeploying the old JAR.

## 10. Mistakes that cause silent errors

| Practice | Why it is unsafe | Do this instead |
| --- | --- | --- |
| Bump version and run only a connection smoke test | Does not check queries, codecs, or old data | Run round-trip and query tests on legacy BSON fixtures |
| Set **uuid=standard** when legacy subtype 3 exists | Query parameters use a different binary subtype and stop matching | Keep legacy representation during framework upgrade; migrate separately |
| Change binary subtype byte 3 to 4 directly | Legacy byte order differs | Decode using the original representation, re-encode as STANDARD |
| Set **big-decimal=decimal128** with unmigrated Strings | Can alter query/sort results and newly written types | Analyze schema first, then migrate under control |
| Switch **@Id** to **@MongoId** without checking BSON _id | Lookup keys can switch between String and ObjectId | Test existing _id fixtures and define target key types explicitly |
| Rely on server host time zone for LocalDateTime | Dev/CI/prod hosts can have different time zones | Standardize on Instant/ZoneId and consistent converters |
| Edit application.yml while ignoring custom MongoClient | Custom beans may ignore new properties | Verify the actual client, codecs, and converters invoked |
| Enable auto-index-creation out of habit | Can alter startup overhead and production indexes | Manage index migrations separately and measure impact |
| Skip updating Actuator dashboards | Renamed health/metrics cause silent alert gaps | Update config, metric queries, and test observability |

### Real-world failure pattern: old data disappears from queries

Before upgrading, the **customers** collection held **customerId** as BSON Binary subtype 3, written under Java legacy. After upgrading, the service reports "customer not found," yet mongosh still shows the document.

Right troubleshooting sequence:

1. Check **$type** for customerId; inspect raw subtype and identify which writer created the data.
2. Confirm how the current service's MongoClient encodes UUIDs; test with a fixed UUID.
3. If existing data is JAVA_LEGACY, update Boot 4 config to **spring.mongodb.representation.uuid=java-legacy** to restore compatibility first.
4. Add regression tests reading/writing the same UUID before and after the framework upgrade.
5. If moving to STANDARD, schedule a separate migration and coordinate readers/writers.

This is a **BSON representation/codec** issue, not a missing-document or index corruption bug. Dropping and rebuilding indexes will not turn subtype 3 into subtype 4.

## 11. Pre-merge or pre-deploy checklist

- [ ] Cross-checked **Boot 3.5 → Boot 4.x** MongoDB properties, health/metrics, and profile overrides.
- [ ] Confirmed **Spring Data MongoDB 5.x / Java Driver 5.6+** alignment with the BOM.
- [ ] Inspected the actual MongoClient, especially any custom beans, sync/reactive clients, and codec registries.
- [ ] Inventoried **BSON String/Decimal128/Double**, UUID subtype **3/4**, BSON Date, null/missing, and _id.
- [ ] Configured UUID representation **explicitly** to match current data.
- [ ] Configured BigDecimalRepresentation **explicitly**; no implicit String-to-Decimal128 shift.
- [ ] Ran repository/integration tests reading data **written by the old version**, not just newly written data.
- [ ] Verified queries/aggregations/indexes/transactions and zoned time behavior.
- [ ] If schema changed, prepared batched migration with checkpoints, safe conditional writes, and reconciliation.
- [ ] Prepared a rollout/rollback plan tied to the **BSON schema**, alerts, and updated health/metrics.

## 12. Hands-on exercise

**Context:** a payment service running Spring Boot 3.5 stores **amount** as String, **customerId** with **JAVA_LEGACY**, and **createdAt** as BSON Date. The team wants to move to Boot 4, then migrate amount to Decimal128 and UUID to STANDARD.

**Requirements:**

1. Write a property mapping across both Boot versions covering Mongo URI, UUID representation, BigDecimal representation, and auto-index-creation.
2. Create two test documents: one legacy-shaped and one standard-shaped. Use raw BSON to verify **amount** and **customerId** in each.
3. Verify the Boot 4 app configured with **java-legacy/string** reads the legacy document and queries by UUID successfully.
4. Write a test for the new schema with **decimal128/standard**, verifying subtype 4 and round-trip behavior.
5. Explain why changing properties in application.yml **does not** automatically migrate existing BSON, and why you cannot just overwrite the subtype byte directly.
6. Design a batched migration with checkpoints, concurrent writer handling, rollback, and reconciliation.

**Completion criteria:** test outputs prove actual BSON types, read-back Java values, and query behavior, alongside an upgrade plan decoupled from data migration. Every representation decision is backed by evidence from stored data.

## 13. Official references

1. [Spring Boot — 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): MongoDB property namespace move, UUID/BigDecimal changes, Actuator, and modules.
2. [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): verifying property names on the old version.
3. [Spring Boot 4.0 — Common Application Properties](https://docs.spring.io/spring-boot/4.0/appendix/application-properties/): verifying property names and defaults on the target version.
4. [Spring Data MongoDB — Migration Guide 4.x to 5.x](https://docs.spring.io/spring-data/mongodb/reference/migration-guide/migration-guide-4.x-to-5.x.html): driver requirements, UUID, and BigDecimal changes.
5. [Spring Data MongoDB — Custom Conversions](https://docs.spring.io/spring-data/data-mongo/reference/5.0/mongodb/mapping/custom-conversions.html): BigDecimalRepresentation, converters, Java Time, and targetType.
6. [MongoDB — BSON Binary UUID Specification](https://github.com/mongodb/specifications/blob/master/source/bson-binary-uuid/uuid.md): subtypes 3/4, byte order, and UNSPECIFIED mode.
7. [MongoDB Java Driver — BsonBinary API](https://mongodb.github.io/mongo-java-driver/5.7/apidocs/bson/org/bson/BsonBinary.html): converting UUIDs with explicit representations.
8. [MongoDB Manual — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/): Decimal128, Binary, Date, Int32/Int64, and other types.
9. [Spring Boot 4.0 — DataMongoTest API](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/data/mongodb/test/autoconfigure/DataMongoTest.html): test slice and package in Boot 4.

**Remember:** the safe goal of the initial upgrade is **same BSON data, same logical UUIDs, same query results** after switching the framework. If you want to move from String to Decimal128 or legacy UUID to STANDARD, treat that as a **separate, tested, and reconciled data migration**.
