# UUID Representation, Binary Data, and Driver Compatibility

## 1. Why Can the Same UUID Still Fail to Match a Query?

Suppose a Java service writes transaction ID `00112233-4455-6677-8899-aabbccddeeff` to MongoDB. A Python service has that exact same UUID string, yet its query returns no document even though the field name and collection are correct. A major reason is that the two services **encoded the UUID into BSON Binary using different conventions**.

A UUID is a logical 128-bit value. MongoDB can store this value as a 16-byte BSON Binary, but a binary field also carries a **binary subtype**; moreover, several older UUID conventions differ in **byte order**. Consequently, two values sharing the same UUID string do not necessarily produce identical BSON.

This lesson belongs to the **Data Types** chapter of the **SPRING_DATA_MONGODB** module. In Spring Data MongoDB, connecting, document mapping, operations via `MongoTemplate` or repositories, queries, indexes, testing, and performance diagnostics are all affected by actual BSON types. Understanding UUID representation prevents bugs when integrating multiple driver versions, polyglot services, and pre-existing data.

After this lesson, you will be able to:

1. Distinguish string UUIDs, Java `UUID`, and BSON Binary with subtypes.
2. Explain the meaning of subtype `0x03` (UUID legacy) and `0x04` (UUID standard).
3. Recognize the differences among `STANDARD`, `JAVA_LEGACY`, `C_SHARP_LEGACY`, and `PYTHON_LEGACY`.
4. Configure representation explicitly in the MongoDB Java driver and inspect the path through Spring Data MongoDB.
5. Design storage for `byte[]`, digests, and binary payloads, verify interoperability, and plan safe migrations.

## 2. Separating Three Layers: Logical UUID, Bytes, and BSON Binary

### 2.1. A UUID Is a 128-Bit Value

A UUID is commonly displayed as a 36-character string consisting of 32 hexadecimal digits and 4 hyphens:

```text
00112233-4455-6677-8899-aabbccddeeff
```

In Java:

```java
import java.util.UUID;

UUID eventId = UUID.fromString(
    "00112233-4455-6677-8899-aabbccddeeff"
);

System.out.println(eventId.toString());
// 00112233-4455-6677-8899-aabbccddeeff
```

Java `UUID` stores the value as two 64-bit halves. How the value formats as a string is distinct from the 16-byte ordering a driver uses when writing BSON. **UUID version** (such as v4 or v7) describes how the UUID is generated and structured; **UUID representation** here describes how a driver writes the 16 bytes and BSON subtype. These two concepts are not interchangeable.

### 2.2. BSON Binary Adds a Subtype

In BSON, a Binary value consists of raw bytes plus a subtype byte. Relevant subtypes include:

| Subtype | Common Name | Purpose |
| --- | --- | --- |
| `0x00` | Generic binary | Arbitrary byte data such as small images, signatures, hashes |
| `0x03` | UUID legacy | UUID storage format used by certain older drivers/conventions |
| `0x04` | UUID standard | 16-byte UUID in standard byte order |

A standard BSON Binary UUID requires **subtype `0x04` and exactly 16 bytes**. A BSON String `"00112233-..."` is a different data type even though its text describes the same UUID.

MongoDB matches binary values by exact BSON representation. When querying with a value whose subtype or byte order differs from what is stored, do not assume MongoDB will treat them as the same UUID.

### 2.3. Comparing Three Storage Approaches

```javascript
// Approach A: string. BSON String, not BSON Binary.
{ eventId: "00112233-4455-6677-8899-aabbccddeeff" }

// Approach B: standard UUID. In mongosh, UUID(...) creates Binary subtype 4.
{ eventId: UUID("00112233-4455-6677-8899-aabbccddeeff") }

// Approach C: legacy Binary. Requires the exact legacy bytes and subtype 3.
{ eventId: BinData(3, "<base64-of-16-legacy-bytes>") }
```

The angle-bracket text in Approach C is a **placeholder**, not valid runnable Base64. To query legacy values, you must extract the actual bytes and know how the legacy driver encoded them. You cannot simply change `3` to `4` and assume the UUID has been converted to standard format.

## 3. STANDARD and Legacy Representations

### 3.1. Same Logical UUID, Different Bytes

For comparison, take the value:

```text
00112233-4455-6677-8899-aabbccddeeff
```

Under standard UUID encoding, the 16 bytes (hexadecimal) are:

```text
00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff
```

Common representations in MongoDB drivers:

| Representation | BSON Subtype | Byte Order for Sample UUID |
| --- | --- | --- |
| `STANDARD` | `0x04` | `00 11 22 33 44 55 66 77 88 99 aa bb cc dd ee ff` |
| `PYTHON_LEGACY` | `0x03` | Keeps standard byte order, but uses legacy subtype |
| `JAVA_LEGACY` | `0x03` | `77 66 55 44 33 22 11 00 ff ee dd cc bb aa 99 88` |
| `C_SHARP_LEGACY` | `0x03` | `33 22 11 00 55 44 77 66 88 99 aa bb cc dd ee ff` |

In Java legacy, each 8-byte half is reversed; in C# legacy, the leading byte groups are reversed per older .NET conventions. Python legacy uses standard byte order while keeping subtype `0x03`. This shows why **subtype 3 alone is not enough to identify byte order**: you must know which representation the writer originally used.

### 3.2. Why Are There Multiple Legacy Variants?

Older drivers chose ecosystem-specific UUID mappings before BSON had a unified cross-language UUID convention. This causes situations where:

- Java legacy and C# legacy both write subtype `0x03` yet produce different bytes.
- Python legacy and standard share the same 16 bytes, yet differ in subtype and remain two distinct BSON values.
- Even within the Java driver, changing the representation configuration between service releases can cause new records to stop matching queries against older data.

**The recommended convention for new interoperable data is `STANDARD`.** Never change representation settings on a system containing legacy data without first auditing existing storage and read/write paths.

### 3.3. What Does UNSPECIFIED Mean?

Modern MongoDB Java driver releases provide `UuidRepresentation.UNSPECIFIED` to avoid silently choosing a UUID encoding that might conflict with existing data. When an encoding/decoding path encounters a Java `UUID`, lacking an explicit representation can cause codec errors or prevent values from converting to UUID as expected.

Do not assume «unconfigured» always means `STANDARD`: defaults depend on the driver, Spring Data, Spring Boot, custom codecs, and exact versions. Identify **which client is in use** and verify its representation, especially after upgrades.

## 4. Non-UUID Binary Data

UUID is only one specific use of BSON Binary. Many other values are stored as byte arrays:

| Data | Common Java Type | Appropriate BSON | Notes |
| --- | --- | --- | --- |
| Transaction UUID | `java.util.UUID` | Binary subtype 4 if standardized on STANDARD | Keep representation consistent across drivers |
| SHA-256 digest | `byte[32]` | Generic Binary `0x00` | 32 bytes is a digest, not a UUID |
| Digital signature | `byte[]` | Generic Binary `0x00` | Do not alter bytes or apply UUID conversion |
| Small file payload | `byte[]` | Generic Binary `0x00` | Mind document size and transport overhead |
| External string identifier | `String` | BSON String if contract specifies | Do not force into UUID |

MongoDB enforces a **16 MiB limit per BSON document**. For large files or streamable assets, use GridFS or an appropriate object storage system, keeping metadata and reference keys inside the document. Do not embed unboundedly large files into business documents.

### 4.1. Base64 Is a Text Representation

Base64 transports bytes over JSON or text interfaces. However, storing Base64 as a BSON String is not the same as storing BSON Binary:

```java
import java.util.Base64;

byte[] digest = new byte[] { 0x01, 0x02, 0x03, 0x04 };
String encoded = Base64.getEncoder().encodeToString(digest);
byte[] decoded = Base64.getDecoder().decode(encoded);
```

Base64 inflates text size relative to the original 4 bytes. BSON Binary stores payloads in binary bytes; Extended JSON uses Base64 **solely to represent** binary values during text exchange or inspection. A Base64 string by itself carries no subtype metadata unless accompanied by extra structure.

### 4.2. Do Not Assume Every 16-Byte Binary Is a UUID

A truncated 16-byte hash, a 16-byte random key, and a UUID are all 16 bytes long, yet carry **different meanings and contracts**. Your schema must specify clearly whether a field is a UUID or opaque bytes. Only decode as UUID when schema and representation confirm it.

## 5. Java Driver: Explicit UUID Encoding and Decoding

### 5.1. Using BsonBinary to Inspect Representations Yourself

Network-independent example demonstrating the MongoDB Java driver API:

```java
import java.util.UUID;
import org.bson.BsonBinary;
import org.bson.UuidRepresentation;

UUID id = UUID.fromString("00112233-4455-6677-8899-aabbccddeeff");

BsonBinary standard = new BsonBinary(id, UuidRepresentation.STANDARD);
BsonBinary javaLegacy = new BsonBinary(id, UuidRepresentation.JAVA_LEGACY);

System.out.println(standard.getType());   // 4  (subtype 0x04)
System.out.println(javaLegacy.getType()); // 3  (subtype 0x03)

UUID standardRead = standard.asUuid(UuidRepresentation.STANDARD);
UUID legacyRead = javaLegacy.asUuid(UuidRepresentation.JAVA_LEGACY);

System.out.println(standardRead.equals(id)); // true
System.out.println(legacyRead.equals(id));   // true
```

Both reads produce the same logical UUID because **each decoder was given the original encoding representation**. That does not mean the two BSON values are interchangeable in MongoDB queries.

You can also inspect raw bytes via `standard.getData()` and `javaLegacy.getData()`. When diagnosing issues, log both subtype and byte hex strings, since printing `UUID.toString()` alone hides storage differences.

### 5.2. Inspecting Subtype and Bytes in Java

```java
import java.util.HexFormat;
import org.bson.BsonBinary;

static String describeBinary(BsonBinary binary) {
    return "subtype=" + (binary.getType() & 0xff)
        + ", hex=" + HexFormat.of().formatHex(binary.getData());
}
```

Place this helper in a utility class in a Java 17+ project and call it on `standard` and `javaLegacy` above. With real data, avoid logging sensitive binary contents; sample safely when debugging.

### 5.3. Configuring MongoClientSettings

When initializing the MongoDB Java driver manually, specify the UUID representation explicitly:

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.UuidRepresentation;

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString("mongodb://localhost:27017"))
    .uuidRepresentation(UuidRepresentation.STANDARD)
    .build();

try (MongoClient client = MongoClients.create(settings)) {
    // Use client for read/write operations or integration tests.
}
```

The localhost URI is illustrative. In production, load URI, credentials, TLS, timeouts, and pool settings from secure application configuration. Do not open a new `MongoClient` per request; reuse the client and close it on application shutdown.

In systems already using subtype 3, identify which representation wrote the existing data before switching configuration to STANDARD. Changing client settings does not automatically convert existing documents.

## 6. Spring Data MongoDB: UUID Fields and Proper Usage

### 6.1. Example Document Containing UUID and Bytes

Suppose a service stores attachment metadata. `correlationId` is a UUID, `sha256` is a 32-byte digest, and `content` is a small binary payload:

```java
import java.util.UUID;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document("attachments")
public record Attachment(
    @MongoId(FieldType.STRING) String id,
    String tenantId,
    @Field("correlation_id") UUID correlationId,
    String contentType,
    byte[] sha256,
    byte[] content
) {}
```

Intended design:

| Java Property | BSON Field | Desired Type |
| --- | --- | --- |
| `id` | `_id` | String, via `@MongoId(FieldType.STRING)` |
| `tenantId` | `tenantId` | String |
| `correlationId` | `correlation_id` | Binary UUID subtype 4 |
| `contentType` | `contentType` | String |
| `sha256` | `sha256` | Generic Binary |
| `content` | `content` | Generic Binary |

**Condition:** Mapping `UUID` to subtype 4 depends on the converter/codec path and proper representation configuration. `@Field("correlation_id")` only renames the field; it **does not set UUID representation**. Verify actual BSON via integration tests, since custom conversions or codec registries can alter behavior.

### 6.2. Reading and Writing via MongoTemplate and Repositories

```java
import java.util.UUID;
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class AttachmentQueries {
    private final MongoTemplate template;

    public AttachmentQueries(MongoTemplate template) {
        this.template = template;
    }

    public List<Attachment> findByCorrelation(
        String tenantId, UUID correlationId
    ) {
        Query query = Query.query(
            Criteria.where("tenantId").is(tenantId)
                .and("correlationId").is(correlationId)
        );
        return template.find(query, Attachment.class);
    }
}
```

Spring Data translates `correlationId` to `correlation_id` using `Attachment.class` metadata. For UUID fields, verify that query values encode into the **exact same subtype and byte order** as persisted records. A query with the right field name but mismatched BSON value still returns an empty list.

Repository example:

```java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface AttachmentRepository
    extends MongoRepository<Attachment, String> {

    Optional<Attachment> findByTenantIdAndCorrelationId(
        String tenantId,
        UUID correlationId
    );
}
```

Do not pass `UUID.toString()` in place of a `UUID` parameter when the repository contract expects `UUID`; that mismatches the Java type and can produce an unintended query value. Direct driver queries using a BSON String are also not equivalent to UUID Binary.

### 6.3. Configuring UUID Representation in Spring Boot

If your Spring Boot application integrates MongoDB client configuration and supports `MongoClientSettingsBuilderCustomizer`, configure it explicitly:

```java
import org.bson.UuidRepresentation;
import org.springframework.boot.autoconfigure.mongo.MongoClientSettingsBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MongoUuidConfiguration {

    @Bean
    MongoClientSettingsBuilderCustomizer standardUuidRepresentation() {
        return builder ->
            builder.uuidRepresentation(UuidRepresentation.STANDARD);
    }
}
```

This snippet illustrates Spring Boot 3.x configuration style. Verify package names and auto-configuration mechanisms for your Boot version; if the application creates `MongoClient` or custom `MongoConverter` beans manually, confirm the customizer actually applies to the client used by `MongoTemplate`.

For **reactive** applications, verify that both the reactive MongoDB client and `ReactiveMongoTemplate` use the right configuration/codecs. Reactive vs. blocking execution does not change byte representation; the issue lies in how BSON values are encoded/decoded along the execution path.

### 6.4. Should You Write a Custom UUID Converter?

Do not rush to register a global `UUID → String` custom converter just to silence a codec error. That alters the BSON schema to String and can break existing queries, indexes, or data written by other services.

When customization is required for historical data, clarify:

- Which BSON type is being preserved or migrated toward.
- Which converter or codec Spring Data actually invokes.
- Whether equality queries, inserts, reads, and updates follow identical rules.
- Migration plans and interoperability with other applications.

If all systems agree to store UUIDs as standardized Strings, that is also a valid schema choice. What matters is that the **storage convention is intentional**, consistent, and tested.

## 7. Mongosh and Extended JSON: Inspecting Stored Data

### 7.1. Creating and Querying Standard UUIDs

In mongosh, for example:

```javascript
const uuidText = "00112233-4455-6677-8899-aabbccddeeff";

db.uuid_events.insertOne({
  source: "example",
  eventId: UUID(uuidText)
});

// Matches eventId with subtype 4 and exact bytes.
db.uuid_events.findOne({ eventId: UUID(uuidText) });

// Does not match a field containing UUID Binary.
db.uuid_events.findOne({ eventId: uuidText });
```

MongoDB does not coerce BSON String to UUID Binary during matching. Nor is there a default rule saying «any 36-character string is interpreted as a UUID».

### 7.2. Inspecting BSON Binary in Extended JSON

A Binary value can be represented in canonical Extended JSON as:

```json
{
  "eventId": {
    "$binary": {
      "base64": "ABEiM0RVZneImaq7zN3u/w==",
      "subType": "04"
    }
  }
}
```

The Base64 above corresponds to the standard 16 bytes of the sample UUID. For legacy binary, subtype may be `"03"` and the Base64 reflects the **actual bytes** of the legacy representation. Some tools render UUIDs in a friendlier shorthand rather than showing `$binary`, so use full type-preserving output when investigating.

In mongosh:

```javascript
const sample = db.uuid_events.findOne({ source: "example" });
printjson(sample);
print(EJSON.stringify(sample));
```

If shorthand output hides the subtype, export BSON using Extended JSON or inspect via the driver's `BsonBinary.getType()`/`getData()` APIs. Never plan a migration based solely on `UUID.toString()`.

### 7.3. $type Does Not Fully Identify Representation

```javascript
db.uuid_events.aggregate([
  { $project: { eventIdType: { $type: "$eventId" } } },
  { $limit: 20 }
]);
```

`$type` confirms the field is `binData`, yet **cannot distinguish** STANDARD from legacy variants, since all are BSON Binary. You must inspect both subtype and 16 bytes; for subtype 3, you also need to know which representation the legacy driver used.

## 8. Compatibility Across Java, Python, C#, and Driver Versions

### 8.1. Cross-Service Contracts

In systems with multiple languages or legacy applications, interface contracts should explicitly state:

| Contract Item | Example Choice |
| --- | --- |
| MongoDB field name | `correlation_id` |
| Logical type | 128-bit UUID |
| BSON type | Binary subtype `0x04` |
| Representation | STANDARD, standard byte order |
| API/JSON format | Canonical UUID string, lowercase with hyphens |
| Query rule | Parse API string to UUID, then encode as standard |
| Legacy data rule | Migration or controlled compatibility reader |

Java, PyMongo, and .NET/C# drivers all offer UUID representation settings, though APIs and defaults vary by version. During integration, configure **both writers and readers** to follow the same contract. Switching Java to STANDARD is not enough if a Python batch job still writes `PYTHON_LEGACY`.

### 8.2. Why Do Queries Miss Even with the Same UUID?

Consider three physical encodings:

```text
Java service A:   subtype 03 + Java legacy bytes
Python service B: subtype 03 + Python legacy bytes
New service C:    subtype 04 + standard bytes
```

All three applications may display the exact same UUID string, yet MongoDB equality queries only see physical BSON values. An index on `correlation_id` will not fix representation mismatches; it merely indexes whatever BSON values were written.

If a unique index exists on this field, **the same logical UUID can still appear under multiple physical representations**. A unique constraint on BSON values does not canonicalize UUIDs across subtypes or byte orders.

### 8.3. Driver Upgrades Can Expose Latent Bugs

When upgrading the Java driver or Spring Data MongoDB:

1. Audit legacy representation settings and where `MongoClient` is constructed.
2. Sample real documents, inspect subtypes/bytes, and identify original writers.
3. Add read/write tests covering existing legacy data, not only data written by the new driver.
4. Decide whether to maintain legacy compatibility temporarily or migrate to STANDARD.
5. Check inserts, `save`, query criteria, aggregations, event consumers, and batch jobs.

When a codec error surfaces after an upgrade, avoid fixing it by turning all UUIDs into API Strings or blindly rewriting all records immediately. First determine **which BSON type is stored** and whether the new write path uses different rules.

## 9. Migration Strategy from Legacy UUIDs to STANDARD

### 9.1. Inventory Before Writing Data

Suppose the `orders` collection stores `trackingUuid` in legacy format while new services want standard format. Before migrating, verify:

- Which collections contain the field, whether it appears in `_id`, and whether it is referenced elsewhere.
- The distribution of subtype `0x03`, `0x04`, and String values, and which systems produced them.
- For subtype 3, whether records were written by `JAVA_LEGACY`, `C_SHARP_LEGACY`, or `PYTHON_LEGACY`.
- Whether records share the same subtype while **mixing byte orders**.
- Which indexes, unique constraints, transactions, consumers, and rollback paths are affected.

Seeing subtype 3 and picking one decoder across the board can corrupt logical UUIDs written by a different driver.

### 9.2. Conversion Principle Preserving Logical Values

The proper transformation is:

```text
BSON Binary subtype 3 + legacy bytes
       |
       | Decode using the exact original legacy representation
       v
Logical UUID in application memory
       |
       | Encode using STANDARD
       v
BSON Binary subtype 4 + standard bytes
```

Java example converting **a value known** to be Java legacy:

```java
import java.util.UUID;
import org.bson.BsonBinary;
import org.bson.UuidRepresentation;

static BsonBinary convertJavaLegacyToStandard(BsonBinary oldValue) {
    if ((oldValue.getType() & 0xff) != 0x03) {
        throw new IllegalArgumentException("Expected UUID legacy subtype 3");
    }
    UUID logicalId = oldValue.asUuid(UuidRepresentation.JAVA_LEGACY);
    return new BsonBinary(logicalId, UuidRepresentation.STANDARD);
}
```

This example is only valid when the source data is confirmed to be `JAVA_LEGACY`. Do not run it blindly across all subtype 3 documents. A real migration must also handle missing fields, `null`, payloads shorter than 16 bytes, batching limits, verification checks, and rollback procedures.

### 9.3. `_id` Requires Special Planning

MongoDB does not allow updating an existing document's `_id` like a normal field. If a UUID lives in `_id` and needs its subtype/bytes changed, you cannot simply run:

```javascript
// Not a valid migration: _id is immutable.
db.orders.updateOne(
  { /* condition */ },
  { $set: { _id: UUID("00112233-4455-6677-8899-aabbccddeeff") } }
);
```

You must design a strategy to copy/insert documents under the new key, update references, manage unique indexes, and coordinate application cutover. Depending on system criticality, this may require a maintenance window, dual-write/sync logic, and reconciliation checks. Always rehearse on a copy of the data before running in production.

### 9.4. Suggested Controlled Rollout Process

| Phase | What Must Be Proven |
| --- | --- |
| 1. Survey | Subtypes/bytes and writer origins are known for every data segment |
| 2. Standardize | New contract uses subtype 4 STANDARD; clients are configured accordingly |
| 3. Pilot | Legacy reads yield accurate UUIDs; standard writes are queryable by new clients |
| 4. Migrate | Idempotent, handles conflicts, has checkpoints and record-count reconciliation |
| 5. Cutover | No legacy writers remain emitting old formats after cutover |
| 6. Monitor | Queries return complete results; indexes and unique constraints behave as expected |
| 7. Cleanup | Remove legacy read branches once data and consumers are fully aligned |

A successful migration proves both **logical data accuracy** and **query compatibility**, not merely that newly inserted records have subtype 4.

## 10. Indexes and Query Design with UUID Binary

Suppose `attachments` is queried by tenant and correlation ID:

```javascript
db.attachments.createIndex(
  { tenantId: 1, correlation_id: 1 },
  { name: "ix_attachments_tenant_correlation" }
);

db.attachments.find({
  tenantId: "tenant-a",
  correlation_id: UUID("00112233-4455-6677-8899-aabbccddeeff")
});
```

This compound index supports equality queries on both fields. However, it only works when query values use the matching BSON subtype and byte order. An index does not decode legacy UUIDs to match standard UUIDs.

If `correlation_id` must be unique per tenant, consider a unique compound index; before creating it, decide how historical records are handled. Do not rely solely on a unique index to prevent the same logical UUID from being stored under different representations.

Using random UUIDs as `_id` or index keys also affects write locality and index patterns. Evaluate performance on realistic workloads, especially for write-heavy systems using random UUIDs; do not misdiagnose index fragmentation or I/O overhead as a «broken UUID Binary».

To inspect index usage:

```javascript
db.attachments.find({
  tenantId: "tenant-a",
  correlation_id: UUID("00112233-4455-6677-8899-aabbccddeeff")
}).explain("executionStats");
```

Inspect `winningPlan`, `IXSCAN`/`COLLSCAN`, `totalKeysExamined`, `totalDocsExamined`, and `nReturned`. When a query uses the wrong representation, `nReturned = 0` does not mean the index is faulty; verify the **filter's BSON value** first.

## 11. Designing Compatibility Tests

### 11.1. Unit Tests for Byte Representation

Pure Java tests requiring no MongoDB connection:

```java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.HexFormat;
import java.util.UUID;
import org.bson.BsonBinary;
import org.bson.UuidRepresentation;
import org.junit.jupiter.api.Test;

class UuidRepresentationTest {

    @Test
    void standardUuidHasExpectedSubtypeAndBytes() {
        UUID uuid = UUID.fromString(
            "00112233-4455-6677-8899-aabbccddeeff"
        );
        BsonBinary binary = new BsonBinary(uuid, UuidRepresentation.STANDARD);

        assertEquals(4, binary.getType() & 0xff);
        assertArrayEquals(
            HexFormat.of().parseHex("00112233445566778899aabbccddeeff"),
            binary.getData()
        );
        assertEquals(uuid, binary.asUuid(UuidRepresentation.STANDARD));
    }
}
```

For legacy formats, add assertions specifying exact expected bytes for each representation. Tests asserting only `UUID.fromString(...).equals(result)` do not prove two drivers emit identical BSON bytes.

### 11.2. Integration Tests on Real MongoDB

With a suitable test environment (local MongoDB / Testcontainers), verify at least:

1. Java writes UUID STANDARD; mongosh reads Binary subtype 4 with standard 16 bytes.
2. Mongosh writes `UUID("...")`; Spring Data reads back the exact `UUID`.
3. `MongoTemplate` and repositories query successfully by `UUID`; plain string queries **are not** treated as equivalent.
4. `byte[]` holding digests or payloads round-trips byte-for-byte without being mistaken for a UUID.
5. Sample legacy records written by older drivers decode properly; new writes use the chosen convention.
6. Across application restarts, client/codec config remains accurate; driver upgrades do not alter fixture read behavior.

For polyglot integrations, maintain a **shared fixture** listing canonical UUID, subtype, 16-byte hex, and expected BSON query. Each client reads/writes the same fixture to catch discrepancies. You do not need to execute the entire suite while authoring this document; these serve as verification criteria during implementation.

### 11.3. Scenario Matrix to Anticipate

| Stored Data | Filter Sent to MongoDB | Matches? |
| --- | --- | --- |
| UUID standard subtype 4 | UUID standard subtype 4, same 16 bytes | Yes |
| UUID standard subtype 4 | BSON String containing canonical UUID | No |
| UUID standard subtype 4 | UUID Python legacy subtype 3, same bytes | No |
| UUID Java legacy subtype 3 | UUID C# legacy subtype 3, same logical UUID | Usually no, due to different byte order |
| UUID Java legacy subtype 3 | Java legacy, same 16 bytes and subtype | Yes |

In this table, «matches» means BSON equality, assuming the same collection, field path, and other filter predicates align.

## 12. Diagnosing Common Errors

| Symptom | Hypothesis | How to Verify |
| --- | --- | --- |
| Java throws codec error when saving UUID | Client/codec lacks an explicit representation | Check `MongoClientSettings`, Spring Boot customizers, custom converters |
| Java reads legacy UUID into wrong value | Wrong legacy representation | Inspect subtype + bytes; test decoding with original writer's mode |
| Mongosh query with UUID string finds nothing | Field stores Binary, filter sends BSON String | Use `UUID("...")` when stored data is subtype 4 |
| Two services have same UUID string but queries disagree | One service uses legacy, the other standard | Compare actual subtypes and bytes |
| Unique index allows two records with same logical UUID | Different physical BSON representations | Standardize representation before relying on unique constraint |
| `$type` returns `binData` for all rows yet queries miss | `$type` hides subtype/byte order | Inspect deeply via Extended JSON / `BsonBinary` |
| `byte[]` replaced by Base64 string | Converter/DTO altered schema | Check BSON type and test byte round-trips |
| References fail to match after migration | Keys and references have mismatched subtypes/types | Reconcile all referencing collections |
| UUID queries are slow | Missing index or poor query shape | Confirm query correctness first, then inspect with `explain` |

An effective diagnostic chain is writing down this trace:

```text
Expected logical UUID
    ↓
Active Java type / codec / UuidRepresentation
    ↓
Persisted BSON type + subtype + bytes
    ↓
Filter BSON type + subtype + bytes
    ↓
Equality query / results / explain
```

Checking each step separates **mapping** bugs from **driver compatibility** issues, **legacy data** drift, and **index/performance** bottlenecks.

## 13. Practice Exercises with Solutions

### Exercise 1 — Distinguishing Subtypes and Types

**Prompt.** A document stores `eventId` as UUID subtype 4. Why does the following query find nothing?

```javascript
db.uuid_events.find({
  eventId: "00112233-4455-6677-8899-aabbccddeeff"
});
```

**Solution.** The filter sends a BSON String, while the stored field is BSON Binary subtype 4. To query standard UUIDs properly:

```javascript
db.uuid_events.find({
  eventId: UUID("00112233-4455-6677-8899-aabbccddeeff")
});
```

### Exercise 2 — Why Don't Python Legacy and Standard Equal Each Other?

**Prompt.** Two drivers share the exact same 16 RFC UUID bytes, yet one uses `PYTHON_LEGACY` and the other uses `STANDARD`. Are equality queries guaranteed to match?

**Solution.** No. Python legacy uses subtype 3 while standard uses subtype 4. Identical payload bytes are insufficient because the BSON subtypes differ. To interoperate, migrate data to a unified representation or query using the actual stored representation during transition.

### Exercise 3 — Checking Java Legacy via Bytes

**Prompt.** Given UUID `00112233-4455-6677-8899-aabbccddeeff`, write a test proving Java legacy BSON differs from standard.

**Solution:**

```java
UUID id = UUID.fromString("00112233-4455-6677-8899-aabbccddeeff");
BsonBinary std = new BsonBinary(id, UuidRepresentation.STANDARD);
BsonBinary old = new BsonBinary(id, UuidRepresentation.JAVA_LEGACY);

System.out.println(std.getType() & 0xff); // 4
System.out.println(old.getType() & 0xff); // 3

System.out.println(HexFormat.of().formatHex(std.getData()));
// 00112233445566778899aabbccddeeff

System.out.println(HexFormat.of().formatHex(old.getData()));
// 7766554433221100ffeeddccbbaa9988
```

Types such as `UUID`, `BsonBinary`, `UuidRepresentation`, and `HexFormat` are imported as in the earlier examples.

### Exercise 4 — Choosing Storage Types for Two Different Fields

**Prompt.** An event has a UUID `eventId` and a SHA-256 `payloadDigest`. Should both be stored as BSON Binary subtype 4?

**Solution.** No. `eventId` uses subtype 4 when the contract specifies UUID STANDARD; `payloadDigest` is a 32-byte array and should be stored as Generic Binary subtype 0 or an agreed digest representation. Subtype 4 is not a catch-all label for arbitrary binary data.

### Exercise 5 — Planning a Representation Change

**Prompt.** A legacy Java service wrote `trackingUuid` with `JAVA_LEGACY`, and a new service uses `STANDARD`. Is it safe to simply change the `MongoClient` config and deploy?

**Solution.** It cannot be assumed safe. Audit legacy BSON, confirm subtype 3 and Java legacy byte order, write tests verifying decoding, design a migration converting via logical UUID to subtype 4, coordinate writers/readers, and verify indexes, unique constraints, and references. For `_id`, migration is harder because primary keys cannot be mutated in place.

## 14. Handoff Checklist and Key Takeaways

Before standardizing a UUID schema across services, verify:

| Checklist Item | Completion Criterion |
| --- | --- |
| New representation | `STANDARD` chosen, or explicit rationale for String storage documented |
| BSON storage format | String vs. Binary, subtype, and 16-byte order documented |
| MongoDB Java driver | Client/codec settings verified |
| Spring Data MongoDB | `MongoTemplate`, repositories, and actual mapping tested |
| Polyglot services | Shared UUID fixtures for read, write, and query |
| Legacy data | Original writers and each representation identified |
| Other binary fields | Digests, signatures, and files not confused with UUIDs |
| Data migration | Migration/rollback and references evaluated |
| Queries/indexes | BSON filters match stored data; evaluated with `explain` when needed |
| Testing | Round-trip tests, subtype/byte assertions, and integration tests exist |

**Rules to remember:**

1. Logical UUIDs are not identical to storage formats: BSON String, Binary subtype 3, and Binary subtype 4 are distinct representations.
2. `STANDARD` uses subtype `0x04` and standard bytes; legacy variants use subtype `0x03` and can differ in byte order.
3. Reading legacy data accurately requires knowing the original representation; subtype 3 alone does not distinguish `JAVA_LEGACY`, `C_SHARP_LEGACY`, or `PYTHON_LEGACY`.
4. Changing driver/Spring Data UUID configuration does not alter existing data. Queries must emit the exact BSON value matching stored fields.
5. Plain `byte[]` data has its own semantics and must not be treated as a UUID simply because it happens to be 16 bytes long.
6. For new cross-service data, favor the STANDARD contract, assert bytes/subtypes in tests, and plan migrations carefully before altering live systems.
