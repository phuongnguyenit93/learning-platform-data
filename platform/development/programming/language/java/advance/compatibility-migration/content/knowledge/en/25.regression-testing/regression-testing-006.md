# Testing Data Saved from the Previous Version

When upgrading a JDK, framework, or library in **Java Advance Compatibility Migration**, most development teams focus on whether the new code compiles, passes tests, and starts up. However, the system's data **does not start from scratch** after deployment: the database still contains records from years ago; the cache may hold values created by the old binary; the message broker still has pending events; object storage stores files/JSON/XML; and sessions and job checkpoints can survive across a rollout.

A new version may write and read data **created by itself** very well, yet fail to read data saved by the previous version. For example, changing the serializer or Java class name makes a serialized object no longer restorable; upgrading the ORM makes the entity mapping incompatible with an old state; migrating from `javax.*` to `jakarta.*` changes annotations/providers; and changing the charset/timezone/date-time format can skew decoded values even when the program does not throw an exception.

The lesson **Testing Data Saved from the Previous Version** belongs to the **Regression Testing** chapter. Its focus is on building a suite of **legacy data fixtures** (data samples originating from the old version), defining **read contracts and data semantics**, testing the new version on realistic snapshots stripped of sensitive information, and testing the compatibility directions needed for rolling deployment or rollback.

The goal is not to "read every byte with every version," but to answer a verifiable question: **which data is committed to being supported, how is it read/interpreted, for how long, and with what evidence before rollout?**

## 1. Why Does Persisting Data Make Migration Harder Than Compiling?

A test that only runs with new data typically has the lifecycle:

~~~text
New version -> Write new data -> Read with new version -> PASS
~~~

In practice, however, when upgrading a system:

~~~text
Old version --writes over months/years--> Long-lived data
                                                 |
                                                 v
                                         New version reads
                                                 |
                                     +-----------+-----------+
                                     |                       |
                         Correct interpretation     Failure/silent error
~~~

Simply changing the library/JDK can also impact:
- Encoding/decoding of JSON, XML, CSV, Java serialization, Avro, and Protobuf.
- Fully qualified class names, `serialVersionUID`, field types, or constructors during deserialization.
- Entity mappings, identifiers/sequences, Hibernate dialects, and JDBC driver behavior.
- Handling of `null`, missing fields, default values, and unknown enums.
- Timestamps/timezones, decimal precision, encoding, and normalization.
- Binary schemas, compressed formats, encryption metadata, and key rotation.
- Classloaders, module access, and runtime provider discovery.
- Java EE/Jakarta namespaces or JPA/JAXB/Validation implementations.
- Consumer compatibility when two versions of the application run simultaneously or when a rollback is required.

**Not all of the points above are JDK bugs.** Many issues are caused by framework/serializer/ORM changes during the migration wave; record the versions of all components to distinguish root causes.

## 2. Identifying What "Saved Data" Includes

Data exists across more layers than just database tables.

| Storage location | Examples | Common issues |
|---|---|---|
| Relational database | orders, invoices, audit logs tables | Schema/column types, defaults, ORM mapping |
| Document database | JSON/BSON documents | Missing/unknown fields, polymorphic types |
| Object storage | JSON/XML/CSV/Parquet, attachments | Charset, parser, format version |
| Cache | Redis keys, serialized objects | Serializer/class name and TTL |
| Message broker | Kafka topic, JMS queue, DLQ | Event/schema version, replay, consumer |
| Session store | HTTP sessions, distributed session | Java serialization, class identity |
| Search index | Documents/index metadata | Analyzer, mapping, reindex requirement |
| Job checkpoint | Cursor, offset, batch state | Resuming without skipping or reprocessing |
| Local files | Config snapshots, CSV exports | Default charset, line endings, date |
| Backup/archive | DB dumps, migration snapshots | Restorability with the new runtime |
| External partner payload | Previously sent files/batches/events | Backward wire compatibility |

Each source has a **different retention**. An API might only need to read events from the last 7 days, whereas tax reporting needs to read old records from many years ago. Do not put everything under the same "compatibility expiration" if the storage contracts differ.

### 2.1. Inventory by Producer, Reader, and Format

A suggested inventory table:

| Dataset/artifact | Previously written by | To be read by | Format/schema | Retention | Critical cases |
|---|---|---|---|---|---|
| `orders` DB | Service v1, old Hibernate | Service v2 | SQL schema v1–v3 | Multiple years | Price, status, timestamps |
| `order-events` | Producer v1 | Consumer v1/v2 | JSON v1, Avro v2 | Per topic policy | Replay, duplicate |
| `user-session` Redis | Web v1 | Web v2 | Serialized session | Hours/days | Login/session continuity |
| Object-store invoices | Batch v1 | Reporting v2 | CSV/XML | Per legal requirements | Charset, decimal |
| Batch checkpoint | Worker v1 | Worker v2 | JSON/properties | Until job completes | Resume/idempotency |

The **actual producer version** must be recorded, not just the tool name. Data may have been created by multiple releases with the same schema name but different mappings.

## 3. Defining the Compatibility Contract to Test

The term "backward compatible" can be interpreted in multiple ways. For stored data, it should be defined by **read/write direction**.

| Scenario | Question | Meaning |
|---|---|---|
| **New reader / old data** | Does V2 read and understand data created by V1? | Primary focus of this lesson |
| Old reader / new data | Can V1 read data created by V2? | Important for rollback/rolling deployment |
| New writer / old reader | Does V2 produce payloads that old consumers understand? | Needed when producers and consumers are upgraded independently |
| New reader / mixed data | Can V2 read records from multiple generations? | Needed for long-lived data stores |
| Rewritten old data / new reader | After backfill, does V2 read it correctly? | Needed for data migration |
| Rewritten data / rollback | On rollback, can V1 still read it? | Determines whether rollback is safe |
| Replay old event | Does V2 process old events and preserve idempotency? | DLQ, event sourcing, recovery |

**Read backward compatibility** does not automatically include **write backward compatibility**. A new version may understand old fields, yet as soon as it rewrites a record, the old version can no longer read it.

### 3.1. Building a Producer-Reader Matrix

For example, if V1, V2, and V3 exist:

| Data created by | Reader V1 | Reader V2 | Reader V3 |
|---|---|---|---|
| Writer V1 | Baseline | **Must PASS** | **Must PASS** if still within retention |
| Writer V2 | PASS when rollback is needed | Baseline V2 | **Must PASS** |
| Writer V3 | Usually not required if V1 is retired; check contract | PASS on V2 rollback | Baseline V3 |

Not every cell needs to PASS; **you must define which cells are part of the contract**. If there is a forward-only boundary, explicitly announce which release can no longer be rolled back and which data requires backup/transformation.

## 4. Key Rule: Sample Data Must Come from the Previous Version

A test like the following is not sufficient:

~~~java
// Wrong target: V2 both writes and reads its own same format.
byte[] bytes = new V2Serializer().write(new Order("ord-1"));
Order result = new V2Serializer().read(bytes);
assertEquals("ord-1", result.id());
~~~

It only tests V2's round-trip, **providing no evidence that V2 can read bytes from V1**.

The right approach:

~~~text
Pinned V1 application/serializer
           |
           v
Generate legacy fixture using controlled test data
           |
           v
Save bytes/files/DB snapshot + checksum + producer metadata
           |
           v
V2 application only reads (or migrates a copy of) that fixture
           |
           v
Assert business values + invariants + errors/edge cases
~~~

### 4.1. Reliable Fixture Sources

They can be obtained from:
1. **Actual old releases**: use the V1 test harness to write JSON/CSV/binary/DB rows with synthetic data.
2. **Staging snapshots built on the old schema**: preserve the original format and metadata.
3. **Anonymized and controlled copies of production data**: only when permitted by policy; create a representative subset, and do not put PII into Git.
4. **Sanitized historical events**: preserve schema headers and important keys without corrupting encoding.
5. **Pinned edge cases** that previously caused bugs: null, unknown enums, DST timestamps, records missing fields.
6. **Version-pinned database dumps**: restore into an isolated test environment.

Every fixture needs metadata:
- Producer application commit/release and JDK vendor/build.
- Serializer/ORM/library versions if they affect the format.
- Schema version (if any).
- How it was generated and whether the data is synthetic/sanitized.
- Hash/checksum and file format.
- Expected business interpretation.
- Retention/support policy of that dataset.

### 4.2. Do Not Automatically "Update Snapshots" with New Code

When a golden test fails, avoid running a command to regenerate fixtures with V2 and immediately committing them. Doing so can turn a **real regression** into a passing test because the expected data was altered to match the new implementation.

If the contract is intentionally changed:
- Keep historical fixtures to test readers that still must be supported.
- Record the decision/ticket for changing the contract.
- Add a new fixture/schema version.
- Update expected semantics through a review independent of the writer implementation.
- Remove old fixtures only when the support window expires and an explicit decision is made.

## 5. Fixture Structure in the Repository

Example layout:

~~~text
src/test/resources/
  legacy-data/
    README.md
    manifest.json
    json/
      v1-order-basic.json
      v1-order-missing-optional.json
      v1-order-unknown-field.json
      v1-order-unicode.json
    xml/
      v1-invoice.xml
    binary/
      v1-order.ser
    events/
      v1-order-created.json
      v1-order-cancelled.json
    sql/
      schema-v1.sql
      dataset-v1.sql
~~~

Example `manifest.json`:

~~~json
{
  "fixtureSet": "orders-legacy-2026-11",
  "producer": {
    "appVersion": "1.12.4",
    "jdk": "17",
    "serializer": "jackson-legacy-release",
    "schemaVersion": 1
  },
  "origin": "synthetic-data-generated-by-v1",
  "fixtures": [
    {
      "path": "json/v1-order-basic.json",
      "case": "basic-paid-order",
      "sha256": "REPLACE_WITH_ACTUAL_SHA256"
    },
    {
      "path": "binary/v1-order.ser",
      "case": "java-serialization-legacy-object",
      "sha256": "REPLACE_WITH_ACTUAL_SHA256"
    }
  ]
}
~~~

The manifest is a **test data management pattern**, not a mandatory standard. The SHA256 must be computed on the **actual file bytes**; do not put a dummy string in the official fixture suite.

### 5.1. Expected Results Are Business Semantics

For example, `v1-order-basic.json` contains:

~~~json
{
  "orderId": "00001234",
  "amount": "125.50",
  "currency": "VND",
  "createdAt": "2024-10-26T21:30:00+07:00",
  "status": "PAID",
  "legacyChannel": "BRANCH"
}
~~~

The invariants:
- Order ID must preserve **leading zeros**, not be coerced into the number 1234.
- Amount must be 125.50 in the contract unit; no incorrect rounding/scaling.
- Currency is VND, not silently switched to a new default.
- Timestamp accurately represents the **instant** and timezone/offset semantics.
- Status PAID still carries the meaning of paid, not mapped to a wrong new status.
- If `legacyChannel` is removed from the domain model, there must be a clear policy: ignore, map to a new field, or retain for audit.

**Do not just verify that the JSON parses.** You must assert that the data is interpreted correctly.

## 6. JUnit 5 Example: Reading JSON Created by V1

To test an old JSON file, use a frozen fixture. Example checking values that must be preserved without depending on new domain mapping:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.InputStream;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class LegacyOrderJsonTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void readsLegacyOrderWithoutChangingMeaning() throws Exception {
        try (InputStream in = getClass().getResourceAsStream(
                "/legacy-data/json/v1-order-basic.json")) {

            assertNotNull(in, "Missing immutable legacy fixture");
            JsonNode root = mapper.readTree(in);

            assertEquals("00001234", root.path("orderId").asText());
            assertEquals("VND", root.path("currency").asText());
            assertEquals("PAID", root.path("status").asText());

            BigDecimal amount =
                    new BigDecimal(root.path("amount").asText());
            assertEquals(0, amount.compareTo(new BigDecimal("125.50")));

            Instant actualInstant =
                    OffsetDateTime.parse(
                        root.path("createdAt").asText()
                    ).toInstant();
            assertEquals(
                    Instant.parse("2024-10-26T14:30:00Z"),
                    actualInstant
            );
        }
    }
}
~~~

This snippet requires JUnit 5 and Jackson Databind dependencies matching the build. This is a test that **reads and checks part of the JSON file's meaning**. In a real application, it must also run through the **actual V2 deserializer/mapper/business service** to verify the production read path, not just test a standalone JSON parser.

### 6.1. When Amount Scale Is Also Part of the Contract

`BigDecimal.compareTo` compares numerical value, whereas `BigDecimal.equals` also considers scale. If the billing system requires formatting with exactly two decimal places, assert them separately:

~~~java
BigDecimal amount = new BigDecimal("125.50");

assertEquals(0, amount.compareTo(new BigDecimal("125.5")));
assertEquals(2, amount.scale());
assertEquals("125.50", amount.toPlainString());
~~~

Do not convert amounts to `double` for testing currency; decimal values can be corrupted due to binary representation. If data is stored in minor units (cents/smallest unit), clearly document the conversion and rounding policy for each currency.

### 6.2. JSON Missing and Null Are Two Different States

For example:

~~~json
{
  "orderId": "ord-1",
  "discountCode": null
}
~~~

differs from:

~~~json
{
  "orderId": "ord-1"
}
~~~

in some contracts. Jackson `JsonNode` can distinguish:
- `root.has("discountCode")`: the field exists.
- `root.get("discountCode").isNull()`: the field has an explicit JSON null.
- `root.path("discountCode").isMissingNode()`: the field is absent.

When upgrading a mapper/framework, do not automatically treat missing and null as identical if they mean "not yet applied", "clear data", or "unchanged".

## 7. Testing the Production Read Path, Not Just the Parser Library

A parser-level test is necessary but insufficient. In an application, data passes through:

~~~text
Legacy bytes
    |
    v
Storage client / JDBC / Kafka consumer
    |
    v
Decoder / codec
    |
    v
DTO / Entity mapping
    |
    v
Validation / normalization
    |
    v
Business rules
    |
    v
API output / side effect / decision
~~~

If production uses Jackson mix-ins, custom serializers, a Spring MessageConverter, or a Hibernate AttributeConverter, a test using a standalone `new ObjectMapper()` may not reflect the real configuration.

To close the loop:
1. Create a test with the codec injected from the V2 application context.
2. Read the fixture through the code path that production uses.
3. Assert domain invariants and mappings.
4. If it is a message consumer, assert idempotency and state changes.
5. If it is a database, assert query/transaction semantics.
6. If it is a file, test charset, headers, and schema version.
7. Use contract/integration tests with real dependencies or replacements with controllable behavior.

### 7.1. Choosing the Appropriate Test Boundary

| Boundary | What it detects | What it misses |
|---|---|---|
| JsonNode/parser unit | JSON syntax, field representation | DTO mapping and business logic |
| DTO deserializer unit | Jackson annotations/converter behavior | Database/runtime services |
| Repository integration | JDBC/ORM mapping, SQL schema | End-to-end HTTP/message behavior |
| Consumer integration | Message headers, codec, business event mapping | Producer release compatibility if not replayed |
| End-to-end staging | Runtime, configuration, services, database | Rare edge cases if fixtures are missing |

Multiple boundaries should be used rather than placing all risk onto a single large, slow, hard-to-diagnose end-to-end suite.

## 8. Testing Java Native Serialization

Java serialization via `ObjectOutputStream`/`ObjectInputStream` is a special case: the object stream can contain class names, `serialVersionUID`, field descriptors, and the serialized object graph. When upgrading a JDK/framework or changing classes:
- Classes whose package/name was changed may no longer be loadable.
- Incompatible `serialVersionUID` can cause `InvalidClassException`.
- Added/removed/retyped fields affect deserialization.
- `readObject`, `readResolve`, `writeReplace`, or `Externalizable` logic changes.
- Proxies, inner classes, enums, and collection implementations have their own limitations.
- Classloader/module rules may prevent old streams from loading.

### 8.1. serialVersionUID and Class Identity

Example of a serializable model:

~~~java
package com.example.archive;

import java.io.Serializable;

public final class LegacyInvoice implements Serializable {
    private static final long serialVersionUID = 2L;

    private String invoiceId;
    private long amountMinor;

    public String getInvoiceId() {
        return invoiceId;
    }

    public long getAmountMinor() {
        return amountMinor;
    }
}
~~~

`serialVersionUID` helps check compatibility of a serializable class during deserialization, but **keeping the same UID does not guarantee preserving behavior** if field semantics or `readObject` changed. Likewise, changing the package changes the class name; merely keeping the new class's UID does not make `ObjectInputStream` automatically understand the old class.

Do not arbitrarily change `serialVersionUID` just to force the JVM to "accept" data without understanding the object graph.

### 8.2. Testing Reading Old Streams

An example test with a `v1-invoice.ser` fixture actually written by V1:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.example.archive.LegacyInvoice;
import java.io.InputStream;
import java.io.ObjectInputStream;
import org.junit.jupiter.api.Test;

class LegacySerializationTest {
    @Test
    void loadsV1InvoiceStream() throws Exception {
        try (InputStream raw = getClass().getResourceAsStream(
                "/legacy-data/binary/v1-invoice.ser")) {

            assertNotNull(raw, "Missing V1 serialized fixture");

            try (ObjectInputStream in = new ObjectInputStream(raw)) {
                Object value = in.readObject();

                assertInstanceOf(LegacyInvoice.class, value);
                LegacyInvoice invoice = (LegacyInvoice) value;
                assertEquals("INV-2024-001", invoice.getInvoiceId());
                assertEquals(12550L, invoice.getAmountMinor());
            }
        }
    }
}
~~~

The example illustrates JUnit 5 using `assertInstanceOf` from a version supporting that API. This test **only reads synthetic fixtures from a trusted source in the test repository**. Do not apply unchecked deserialization to data from the network or external sources.

### 8.3. Security Warning When Deserializing

**Native Java deserialization of untrusted data can be dangerous** and has been the source of many vulnerabilities. If the application currently reads object streams from caches/messages/external input:
- Prefer replacing it with a format that has an explicit schema and a safely designed reader.
- Set appropriate input size limits and type allowlists.
- Consider `ObjectInputFilter` (JEP 290 and subsequent runtime filtering mechanisms).
- Check whether the classpath contains dangerous gadget chains.
- Do not treat a single filter as proof of safety.
- Do not put binary fixtures obtained from untrusted sources into a test runner with high privileges.

Illustrative filter template for a stream **only** containing classes in a known package:

~~~java
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;maxrefs=500;maxbytes=1048576;"
      + "com.example.archive.*;java.base/*;!*"
);
in.setObjectInputFilter(filter);
~~~

This is an **illustrative** configuration, not a validated security allowlist for a specific object graph. Filter patterns, collections, arrays, and types must be designed/verified for the actual runtime, data, and threat model. If the application no longer needs Java serialization, removing this mechanism can be safer and easier to maintain than preserving compatibility indefinitely.

### 8.4. Do Not Mix Java Serialization with JSON Compatibility

`serialVersionUID` has no meaning for plain JSON, Avro, or Protobuf, unless the format/application code uses it explicitly. Conversely, a JSON DTO keeping the old field names does not help Java `ObjectInputStream` read a class whose package changed.

Each format needs its own **schema/identity/compatibility policy**.

## 9. Testing Old Database Records

The database is where old data lives longest and often has many legacy states:
- `NULL` was previously allowed, but new code assumes non-null.
- An old enum/string status no longer exists in the new Java enum.
- Decimal/float numbers have different rounding.
- Timestamps have timezones or lack timezones.
- A foreign key is missing from old data.
- A JSON column has an old schema.
- A column was renamed/dropped, but data has not been backfilled.
- New ORM mapping uses a different default constructor, records, or custom converter.
- New queries use joins/filters that drop old rows.

### 9.1. Testing on a Copy of Pinned Schema and Data

Workflow:

~~~text
Legacy schema + legacy rows (synthetic/sanitized)
                    |
                    v
Restore into an isolated test DB
                    |
                    v
Apply versioned migration scripts
                    |
                    v
New application repository/ORM reads
                    |
                    v
Assert data + business invariants
                    |
                    v
Optional: write/read/rollback compatibility checks
~~~

Do not test destructive migration scripts on a production database just to "see if it works". Use a copy with appropriate permissions, retention, and masking.

### 9.2. Example Schema Fixture

Suppose V1 had the table:

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(32) PRIMARY KEY,
    amount_minor BIGINT NOT NULL,
    currency VARCHAR(3) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    external_ref VARCHAR(64)
);

INSERT INTO orders
  (order_id, amount_minor, currency, status, created_at, external_ref)
VALUES
  ('00001234', 12550, 'VND', 'PAID',
   TIMESTAMP '2024-10-26 14:30:00', 'legacy-42'),
  ('00001235', 0, 'VND', 'CANCELLED',
   TIMESTAMP '2024-10-26 15:00:00', NULL);
~~~

This is an illustrative dataset. In a real system, a **TIMESTAMP without timezone** does not prove on its own that it is UTC; interpretation must follow the contract of the old producer/database session. If V1 wrote local time, V2 must have an appropriate conversion rule before treating the timestamp as an instant.

### 9.3. Testing Both Pre-Existing and Newly Written Records

In a test using an isolated DB:
1. Load the V1 schema and rows created by V1.
2. Apply the migrations that V2 will run.
3. Start the V2 repository/ORM.
4. Read old rows by ID and assert fields.
5. Write a new row using V2.
6. Query again using V2.
7. If rollback is still required, use the V1 reader to try reading **both old and new rows**.
8. Verify row counts, duplicate keys, constraints, and transaction behavior.
9. Evaluate behavior when V2 updates an old row and V1 reads it back.

Do not just test that "migration SQL ran without errors"; the new code can still misinterpret rows.

### 9.4. Example Repository Regression Test

Example Java/JDBC test reading legacy values after test setup has restored the schema/fixtures:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;

class LegacyOrdersJdbcTest {
    private final DataSource dataSource;

    LegacyOrdersJdbcTest(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Test
    void readsOldOrderWithoutLosingIdentifier() throws Exception {
        String sql =
                "SELECT order_id, amount_minor, currency, status "
              + "FROM orders WHERE order_id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {

            statement.setString(1, "00001234");

            try (ResultSet rs = statement.executeQuery()) {
                assertTrue(rs.next());
                assertEquals("00001234", rs.getString("order_id"));
                assertEquals(12550L, rs.getLong("amount_minor"));
                assertEquals("VND", rs.getString("currency"));
                assertEquals("PAID", rs.getString("status"));
                assertFalse(rs.next());
            }
        }
    }
}
~~~

This is a **test outline**; `DataSource` must be provided/injected by the test framework (for example, a Spring integration test or test fixture)—JUnit does not automatically constructor-inject it just by creating the class. Note that `javax.sql.DataSource` is a **Java SE JDBC API**, so it keeps that name when the application migrates to Jakarta EE. Do not replace it with a nonexistent `jakarta.sql.DataSource`.

### 9.5. Using a Real Database or a Sufficiently Representative Version

An in-memory database of a different engine may:
- Differ in SQL type/precision rules.
- Differ in timezone, collation, and ordering.
- Differ in transaction isolation/locking.
- Differ in JSONB/array types.
- Differ in index/dialect behavior.

For ORM/JDBC changes, testing with the **same database engine and a version close to production** (for example, an isolated container) is usually more valuable than testing only with H2 if production runs PostgreSQL/Oracle/MSSQL.

## 10. Schema Migration Using Expand–Migrate–Contract

When multiple versions coexist in a deployment, changing a schema directly via drop/rename can break the old version.

Model:

~~~text
EXPAND
  Add new columns/tables/indexes in a backward-compatible way
        |
        v
MIGRATE
  Backfill old data, change app readers/writers in a controlled manner
        |
        v
VERIFY
  Test historical data, mixed versions, invariants
        |
        v
CONTRACT
  Drop old schema only when no consumers and rollback window remain
~~~

### 10.1. Example: Adding a New Field Without Breaking Old Rows

Suppose V2 adds `completed_at`:

~~~sql
ALTER TABLE orders
    ADD COLUMN completed_at TIMESTAMP NULL;
~~~

V1 rows have `NULL` in the new column. V2 must handle them properly, for example:
- For orders that are already PAID, is there a policy to backfill the timestamp or not?
- Do not assume `completed_at` is always non-null immediately upon deployment.
- If NOT NULL is required, backfill and verification must complete before adding the constraint.
- If V1 still writes new rows during a rolling deployment, the backfill mechanism must handle **concurrently arriving rows**.

**Do not fabricate a dummy "2026-01-01" value for all history just to pass NOT NULL** if it corrupts reports, audits, or SLAs.

### 10.2. Testing Migrations in the Right Order

When using Flyway/Liquibase or a similar tool:
- Pin migration script versions.
- Restore the V1 snapshot and apply the exact migration sequence.
- Check idempotency at the level specified by the tool and the rollback policy.
- Assert row counts, keys, constraints, and data semantics.
- Check index creation/locking and downtime limits.
- Run V2 to read the data after migration.
- For mixed deployment, test V1/V2 reading/writing concurrently within the support window.

Do not infer from "Flyway applied successfully" that the business-level data is already correct.

## 11. JSON: Mapper/Framework Changes Can Change Meaning

JSON does not include Java class descriptors by default, but the application serializer can change:
- Property names due to naming strategy.
- Default visibility/field detection.
- Null inclusion or absent-field handling.
- Enum encoding: name/string/ordinal.
- Dates: numeric epoch, ISO-8601, timezone/offset.
- BigDecimal representation.
- Unknown properties: reject or ignore.
- Polymorphic type metadata.
- Custom annotations/mix-ins.
- Constructor/record support.
- Module registration such as `JavaTimeModule`.

### 11.1. Essential JSON Fixtures to Consider

| Scenario | Legacy fixture | Expected result |
|---|---|---|
| Optional field absent | No `discountCode` | Preserve V1 default semantics |
| Explicit null | `discountCode: null` | Not interpreted as empty string if meaning differs |
| Unknown field | Has a V1 field no longer in V2 | Ignore/log/reject per contract |
| Unknown enum | `status: "ON_HOLD_LEGACY"` | Safe mapping, no crash or wrong default |
| Large integer | ID `9007199254740993` as a number | No precision loss across JS/JSON bridge |
| Decimal | `"125.50"` or `125.50` | No rounding/scale change outside policy |
| Date/time | Non-UTC offset, DST day | Preserve instant/local meaning |
| Unicode | Vietnamese, emoji, combining marks | No mojibake/wrong normalization |
| Polymorphism | V1 type discriminator | Select safe, allowed subtype |
| Collection | Empty, null, duplicates | Mapping with correct semantics |
| Nested schema | Deep objects/arrays | No dropped/mixed fields |
| Old defaults | Field previously absent in V1 | New code does not synthesize wrong behavior |

### 11.2. Unknown Enums Should Have an Explicit Policy

For example, V1 previously wrote status `WAITING_APPROVAL` while V2 uses `PENDING_REVIEW`. You can:
- Intentionally map it using an adapter.
- Keep the legacy status and handle it as a distinct state.
- Reject it if the contract is no longer supported and a data migration precedes it.
- Route it to a dead-letter/reconciliation flow with an alert.

Do not use `catch (Exception) { return PAID; }` or automatically map every unknown status to a success state. This is a **data correctness** bug, not merely syntactic compatibility.

### 11.3. JSON Polymorphic Type Metadata

If V1 stores the Java class name in JSON, for example:

~~~json
{
  "@class": "com.example.legacy.payment.CardPayment",
  "amount": "125.50"
}
~~~

changing the package/class can break deserialization. Additionally, polymorphic type deserialization carries security risks if arbitrary types are allowed from untrusted data.

Approaches:
- Prefer a schema-owned stable discriminator, such as `type: "CARD"`, instead of internal class names.
- Use an explicit allowlist/subtype registry.
- Migrate old discriminators through a controlled adapter.
- Do not enable broad default typing just to "read all old data".
- Test negative cases and inputs outside the whitelist.

## 12. Charset and Unicode After Upgrading the JDK

Files/CSVs/text saved with the old JVM's default charset may be read differently when upgrading the JDK or changing OS/containers.

**JEP 400** standardizes the default charset to UTF-8 starting in JDK 18 under many common circumstances, with conditional exceptions/compatibility mechanisms. Therefore, code using `new String(bytes)` or `FileReader` without specifying a charset risks misinterpreting old data if a different charset was previously used.

### 12.1. Do Not Rely on the Default Charset for Long-Lived Formats

Avoid:

~~~java
String text = new String(bytes); // Depends on default charset
~~~

Replace with the charset according to the **format contract**:

~~~java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

byte[] bytes = Files.readAllBytes(Path.of("legacy-export.csv"));

String utf8Text = new String(bytes, StandardCharsets.UTF_8);

// If the legacy format actually uses Windows-1252:
// Charset legacy = Charset.forName("windows-1252");
// String legacyText = new String(bytes, legacy);
~~~

Do not arbitrarily choose UTF-8 when V1 data was actually written with another charset. Determine it from the producer version, header/BOM, format documentation, test fixtures, or verified original data.

### 12.2. Unicode Golden Fixtures

Consider data such as:
- Accented Vietnamese names: `Đặng Thị Ánh`.
- Emoji and surrogate pairs.
- Unicode combining marks (NFD) versus precomposed form (NFC).
- Data with BOM, CRLF/LF.
- Characters `€`, `£`, `\u0000` if the format permits.
- Long text and characters outside the Basic Multilingual Plane.

The goal is to preserve the **committed business value/representation**, not always to arbitrarily normalize strings. Unicode normalization can affect signatures/hashes, search, and equality.

## 13. Dates, Times, and Timezones

Temporal data is a prominent group of regressions:
- `java.util.Date` and `Calendar` versus `java.time`.
- `LocalDateTime` without a timezone.
- `Instant` representing a point in time.
- `OffsetDateTime` with a fixed offset.
- `ZonedDateTime` with region/timezone rules.
- Different JVM default timezones between local and container environments.
- tzdb updates across JDK releases.
- JDBC driver/ORM changes in how timestamps are bound.

### 13.1. The Same String Does Not Necessarily Mean the Same Instant

For example:

~~~text
2024-10-26T21:30:00+07:00
2024-10-26T14:30:00Z
~~~

are the same instant. If a record represents a **local appointment time**, you may need to preserve the local time and timezone region rather than just the instant. The contract must clearly state the field's semantics.

### 13.2. Testing Boundary Cases

- Ambiguous or non-existent times due to DST in regions with DST.
- Epoch 0 and timestamps before 1970.
- Offsets other than UTC.
- End-of-month boundaries, leap years.
- `LocalDate` as a calendar day versus a timestamp.
- SQL `TIMESTAMP WITHOUT TIME ZONE` versus `WITH TIME ZONE`.
- Cases where a new JDK/tzdb changes region rules.

A fixture created by V1 on an old JDK/OS and read on V2 with a new JDK helps detect timezone-default impacts that tests using data created by V2 itself miss.

## 14. Arithmetic, Currency, and Precision

Old data may contain:
- `DECIMAL(p,s)` in SQL.
- Decimal strings in JSON.
- `long` minor units.
- `double`/`float` for legacy metrics.
- Currency conversions with rounding policy.
- Large integers exceeding the JavaScript safe integer range.

### 14.1. Testing Both Values and Rounding Rules

If V1 wrote `125.50` but V2 turns it into `125.5`, the numeric values are equal, yet the format/scale may violate an invoice contract. If V2 uses `double` and improperly converts back to `BigDecimal`, rounding errors can appear at boundary values.

Fixtures should include:
- `0`, and negative numbers if permitted by the contract.
- Extremely large and extremely small numbers.
- Many decimal places.
- Rounding boundaries (e.g., halfway between two minor units).
- Currencies with zero or three decimal minor units.
- Sum of multiple line items equaling the invoice total per policy.

Do not alter old data just to achieve a new representation if business/invoice/audit contracts require preserving it as-is.

## 15. Avro, Protobuf, and Schema Evolution

For event streaming or storing binary data, schema-based formats typically support evolution, yet **not every schema change is safe**.

### 15.1. Avro

Avro uses a writer schema and a reader schema to decode according to schema resolution rules. When adding a field, old/new readability depends on defaults and compatibility rules of the schema registry or consumer.

Example Avro V1 schema:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "amountMinor", "type": "long" }
  ]
}
~~~

V2 adds an optional field with an explicit default:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "amountMinor", "type": "long" },
    {
      "name": "source",
      "type": ["null", "string"],
      "default": null
    }
  ]
}
~~~

Having a default can allow a V2 reader to read data from a V1 writer under the right resolution rules, but **it must be tested for real with the exact versions of the writer schema/reader schema and subject compatibility policy**. Do not conclude that all other schema changes are also safe.

### 15.2. Protobuf

Protobuf uses field numbers as identity. Key rules:
- Do not arbitrarily reuse a field number previously used for another meaning.
- When removing a field, use `reserved` for the number/name to avoid reuse.
- Be careful when changing wire types or numeric representations.
- Unknown fields may be preserved or lost depending on the runtime/language/transform path.
- Optional/presence semantics differ by syntax/version.
- New enum values require a consumer policy for handling unknown values.

Example:

~~~proto
syntax = "proto3";

message OrderCreated {
  string order_id = 1;
  int64 amount_minor = 2;
  string currency = 3;
}
~~~

If V2 adds field 4, keep 1–3 with their old semantics. Do not change `amount_minor = 2` to `amount_major = 2` merely because they share the same wire type; that breaks the business contract even though the decoder still parses it.

### 15.3. Schema Registry Checks Are Not Enough

A schema registry may report compatibility PASS at the schema level, yet you still need to check:
- Business semantic mappings.
- Actual defaults when a field is absent.
- Deployed consumers and schema IDs in message headers.
- Producer/consumer serialization configuration.
- Replaying old events from retention/DLQ.
- Idempotency, and exactly-once/at-least-once assumptions.
- Authentication/authorization and data masking.

**Schema-compatible does not mean behavior-compatible**.

## 16. Kafka/JMS, DLQ, and Event Replay

A V2 consumer might receive new events fine but fail when replaying a V1 event from 30 days ago. Tests should take a corpus of old events created by V1, including headers and payloads, and replay them into the V2 consumer in an isolated environment.

### 16.1. Things to Assert

- The consumer receives the right key, headers, schema ID, and partition semantics.
- The payload decodes without losing essential fields.
- Domain event mapping is correct.
- Old events are not processed twice during replay.
- No duplicate invoices/payments are created.
- Poison messages are routed to the DLQ with sufficient diagnostic information.
- Consumer lag does not grow unboundedly.
- Error/timeout/retry/backoff policy is controlled.
- Traces/metrics distinguish legacy event versions.

A replay that succeeds at the parser level yet creates two payment records is still a **critical regression**.

### 16.2. Testing Old Offsets/Checkpoints

Batch/stream processors may store:
- Kafka offsets.
- Last processed event ID.
- Serialized checkpoint state.
- Watermarks/windows.
- Retry queues/delayed jobs.

When upgrading a JDK/library, you must test **resuming from a V1 checkpoint**:
1. Create a checkpoint using V1.
2. Stop in a controlled manner.
3. Start V2 with that checkpoint.
4. Assert no skipped or duplicated business state transitions.
5. Test failure/restart at several transaction boundaries.

Do not only verify that the consumer runs from the latest offset; production may resume from a checkpoint that existed prior to the migration.

## 17. Cache and HTTP Sessions Between Two Versions

Cache data is often viewed as "disposable," yet not every cache is harmless to invalidate:
- User sessions.
- Checkout/cart state.
- Idempotency keys.
- Distributed locks.
- Rate-limit counters.
- Long-running job state.
- Reference data caches containing serializer-specific classes.

### 17.1. Transition Options

| Option | When appropriate | Risks/trade-offs |
|---|---|---|
| V2 can read V1 cache | Need to preserve session/state across rollout | Must support old codec/type identity |
| Versioned cache keys | Two versions run in parallel | Increases memory and cache misses |
| Intentional invalidation | Data can be safely regenerated | Cold-start thundering herd, logouts |
| Dual-read then rewrite | Gradually migrating the store | Race conditions, write amplification |
| External session schema independent of Java classes | Need long-term stability | Refactoring cost and format governance |

If choosing to invalidate sessions when migrating Java EE/Jakarta namespaces, evaluate UX, security, TTL, and logout policy. Do not assume a serialized session created by the old `javax.servlet` stack will automatically restore in the new `jakarta.servlet` stack.

### 17.2. Avoiding Mixed-Cache Poisoning

When V1/V2 write to the same key using two different formats, the app may succeed at times and fail at others. One option is using a versioned key prefix:

~~~text
orders:cache:v1:<orderId>
orders:cache:v2:<orderId>
~~~

However, consider:
- TTL and eviction.
- Cache hit ratio/cold start.
- Source of truth.
- Invalidations across both namespaces.
- Not duplicating sensitive data unnecessarily.

Key versioning does not solve semantic incompatibility in databases or event logs.

## 18. XML, JAXB, and the Jakarta Namespace

When migrating from Java EE/Jakarta EE 8 to Jakarta EE 9+, many enterprise APIs change their Java namespace from `javax.*` to `jakarta.*`. However, XML payload namespace URIs do not automatically change along with Java packages.

Distinguish between:
- Java `javax.xml.parsers.*` belonging to Java SE remains unchanged.
- JAXB `javax.xml.bind.*` of the old API has the Jakarta counterpart `jakarta.xml.bind.*`.
- The XML namespace URI in the payload is an external contract; it may remain unchanged.
- JAXB annotations/providers, schema generation, and default bindings may change when upgrading versions.

### 18.1. Testing a V1 XML Fixture

Suppose the file:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<invoice xmlns="urn:example:invoices:v1" id="INV-0001">
  <amount currency="VND">125.50</amount>
  <issuedAt>2024-10-26T21:30:00+07:00</issuedAt>
</invoice>
~~~

V2 using Jakarta XML Binding or a new XML parser must:
- Preserve and recognize `urn:example:invoices:v1` if the contract still supports it.
- Map amount with the right type/scale.
- Parse the timestamp according to the old semantics.
- Not automatically change the wire namespace URI just because Java imports changed from `javax.xml.bind` to `jakarta.xml.bind`.
- Block dangerous XML external entities/DTDs according to appropriate parser/security policy.

If V2 outputs XML in a new schema, add tests for old reader/new writer per the rollback contract if still required.

## 19. Encryption and Signed Data

When old data is encrypted or signed:
- The JVM/provider may change algorithm availability or defaults.
- Key aliases, keystore/truststore formats, and password policies may differ.
- GCM IV/tag length and required metadata may not have been stored consistently.
- Pre-signing encoding (charset, Unicode normalization, canonical JSON/XML) may change.
- Certificate chains/trust policies may change with JDK security updates.

### 19.1. Do Not Treat Decrypt Success as Sufficient

For encrypted archived data, test:
1. Restore synthetic ciphertext generated by V1 with a dedicated test key.
2. V2 decrypts using the **exact algorithm, IV, tag, and key metadata**.
3. Plaintext matches the golden value.
4. When ciphertext/tag is tampered with, verification fails.
5. Do not log sensitive plaintext/keys/IVs.
6. During key rotation, old data still has an approved decryption path.

If signature verification changes, test both valid old signatures and tampered inputs. **Do not disable validation to bypass a regression**; it may be a legitimate security change requiring a separate migration plan.

## 20. Testing Old-Data → New-Data Migration

Some changes cannot be handled by simply reading old data directly with new code; the data must be **transformed** first, for example:
- Splitting a `fullName` field into first/last name according to policy.
- Converting local datetimes into UTC instants along with timezone metadata.
- Converting decimal amounts into minor units.
- Changing status enums according to a business mapping table.
- Adding normalized lookups/indexes.
- Migrating document schemas or encryption envelopes.

A proper data migration needs:
- Clear script/version and source/target schemas.
- No lost records/no generated duplicates.
- Preserved invariants for total amounts, identity, and status.
- Idempotency or retry policy on re-execution.
- Progress metrics and checkpoints.
- An error/quarantine channel for records that cannot be mapped.
- A backup/rollback/forward-only policy.
- Audit/logs that do not leak sensitive data.

### 20.1. Invariants to Verify with Sanitized Real Data

| Invariant | Example |
|---|---|
| Count | Order count before/after does not decrease outside exclusion rules |
| Identity | `orderId` with leading zeros remains unchanged |
| Monetary sum | Total amount per currency remains unchanged |
| Referential integrity | Foreign keys/links remain valid |
| Status mapping | Every legacy enum maps to the right business state |
| Time | Instant/local date/zone match the contract |
| Ordering | Business event sequence is not inverted |
| Idempotency | Re-running migration does not duplicate records |
| Completeness | No record is dropped due to null/unknown values |
| Data privacy | Tokens/PII are not exposed in migration logs |

Simply taking a checksum of the entire table after migration may be unsuitable if the schema/format changed intentionally. In that case, use **semantic comparison** based on canonicalized business fields.

### 20.2. Do Not Silently "Fix" Legacy Data

A legacy record with an unusual status, negative amount, or invalid timestamp might be:
- Valid data under old rules.
- An accepted historical bug.
- Corruption requiring special handling.
- Incorrectly entered data needing reconciliation.

V2 should not automatically rewrite it to a new valid value without recording an audit/policy. Categorization and business decisions are needed, especially for finance, legal, access control, and transaction state.

## 21. Testing Forward/Backward Compatibility During Rolling Deployment

If V1/V2 run concurrently for a period of time:

~~~text
         Shared DB / cache / broker
                  ^
                  |
        +---------+---------+
        |                   |
    App V1                 App V2
    old writer            new writer
    old reader            new reader
~~~

Both versions can read and write to the same store; thus, testing "V2 reads V1 data" is only half the story.

The matrix needs:
- V1 reads records written by V1.
- V2 reads records written by V1.
- V2 reads records written by V2.
- **V1 reads records written by V2** when required by rollback/rolling deployment.
- V1 and V2 update the same record under realistic conditions.
- Race conditions, optimistic locking, and transaction/version columns.
- Cache keys, event formats, and consumer contracts.
- Schema migrations before/after deployment.

### 21.1. Expand–Migrate–Contract Also Applies to Formats

V1 does not yet know the `newStatus` field:
1. Expand phase: V2 adds an optional field; the V1 reader must tolerate it, or V2 does not write the new field for old readers.
2. Migrate phase: controlled backfill/mapping; both readers operate.
3. Contract phase: drop the old field only when no V1 readers remain and the rollback window has ended.

Do not change the meaning of a field still being used by V1 just because the database allows updating it.

### 21.2. Forward-Only Migration Requires an Explicit Decision

If V2 writes data that V1 cannot read and the business has accepted no direct rollback:
- Document the exact cutover point.
- Have a backup/snapshot beforehand.
- Have a recovery or roll-forward plan.
- Restrict canary/mixed deployments.
- Test failover and backup restore on staging.
- Do not claim "rollback is possible" merely because the old Docker image is still available.

## 22. Organizing the Test Pipeline with a Fixture and Runtime Matrix

A migration pipeline can be divided into:

~~~text
Stage 1: Compile + unit tests
      |
      v
Stage 2: Legacy fixture reader tests
      |
      v
Stage 3: DB migration from V1 snapshot
      |
      v
Stage 4: Message replay / cache-session tests
      |
      v
Stage 5: Cross-version read/write matrix
      |
      v
Stage 6: Production-like integration + canary
~~~

Each stage provides distinct evidence; you should not only have a "context loads" test.

### 22.1. Test Matrix by JDK and Application Version

| Reader | JDK | Input data | Tests that must pass |
|---|---|---|---|
| V1 | Supported baseline JDK | V1 fixtures | Control/baseline |
| V2 | Target JDK | V1 fixtures | **Mandatory** |
| V2 | Target JDK | V2 fixtures | New format regression |
| V2 | Target JDK | V0/V1 fixtures if still within retention | Historical compatibility |
| V1 | Baseline JDK | V2 data | If rollback/mixed deployment is supported |
| V2 | Target JDK | DB snapshot with migrations applied | Data migration correctness |

**Do not run an unsupported JDK/framework combination just to fill in the table**. If a cell is infeasible, document the reason, risks, and substitute an appropriate test/operational policy.

### 22.2. Running the Old Producer When New Fixtures Need to Be Generated

You can use V1's container/image or the V1 release Git tag in CI to generate **synthetic fixtures**. However:
- Pin image digests/tool versions.
- Separate output from expected golden data under review.
- Do not automatically overwrite approved fixtures.
- Use synthetic test identities and fake endpoints.
- Include checksums/provenance.
- Do not run legacy code with production credentials.

If the V1 build can no longer run on the new JDK, generate fixtures with the **supported baseline JDK**, then have V2/target JDK read them. That is the exact purpose of cross-version testing.

## 23. Controlling Sensitive Data in Fixtures

Using production snapshots can improve representativeness, but introduces major risks:
- PII, email addresses, physical addresses, phone numbers.
- Tokens, passwords, API keys.
- Payment identifiers, account numbers.
- Health/personal data, transaction histories.
- Internal hostnames/secrets in serialized object graphs.
- Business-sensitive documents.

Mitigations:
- Prefer **synthetic data generated by V1** when coverage is sufficient.
- If real samples are needed, use an approved masking/tokenization process.
- Ensure masking preserves the **format characteristics** under test: length, charset, null, cardinality, type, relationships.
- Use test-only keys for encrypted fixtures.
- Separate access permissions and retention.
- Do not commit raw production dumps to Git.
- Do not expose snapshots in public CI logs/artifacts.
- Record provenance and deletion policies.

**Hiding user names with an arbitrary string is not enough** if the dataset still contains embedded IDs/metadata capable of re-identification. Data governance must be addressed before saving fixtures.

## 24. Metrics and Evidence After Migration

Besides PASS/FAIL test results, you can record:
- Number of fixtures by producer/schema version.
- Number of fixtures successfully read.
- Rate/types of deserialization failures.
- Number of unmappable or quarantined records.
- Number of unsupported legacy statuses.
- Checksum/semantic invariant mismatches.
- Replay duplicate counts.
- Database migration progress/rows affected.
- Cache miss/session invalidation rates.
- Processing time for old data and resource usage.

If old data can be read but much more slowly, it can still be a significant regression. Separate **compatibility correctness tests** from **performance tests**, yet use the same representative corpus when appropriate.

### 24.1. The Difference Between Testing One Record and Testing the Full Dataset

A test on one JSON fixture is an initial signal. Real systems may contain:
- Multiple schema generations.
- Rare field combinations.
- Outliers.
- Records with historical duplicates or corruption.
- Data created at specific JDK patch versions.
- Backfills/partial migrations.

It is necessary to combine:
1. **Golden fixtures** for critical contracts.
2. **Property-based/parameterized tests** within schema bounds.
3. An approved **sanitized representative corpus**.
4. **Migration/integration tests** with a real database.
5. **Canary monitoring** after deployment.

Do not use a random sample lacking a coverage strategy and conclude that all old data is compatible.

## 25. Diagnosing Common Errors

| Symptom | Cause to check first | Resolution approach |
|---|---|---|
| `InvalidClassException` | `serialVersionUID` or serialized class incompatible | Compare V1/V2 class descriptors and contract |
| `ClassNotFoundException` when reading old stream | Class/package changed or missing dependency | Migrate data/adapter/versioned codec |
| `NoClassDefFoundError` during deserialization | Runtime missing old class/transitive dependency | Dependency graph or data migration |
| JSON parse passes but domain is wrong | Defaults, enum, timezone, amount mapping | Assert business invariants |
| Unknown enum exception | Data contains V1 status no longer present | Explicit mapping/legacy policy |
| Missing property becomes null | JSON/ORM binding changed | Schema migration and validation |
| Unicode mojibake | Old charset differs from UTF-8 | Read with the exact legacy encoding |
| Timestamp offset mismatch | Timezone/JDBC/ORM semantics changed | Test instant/local time separately |
| Numeric amount wrong | Double/scale/minor unit conversion | BigDecimal and rounding tests |
| Entity fails to load | JPA/Hibernate/Jakarta mapping mismatch | Provider, annotation, schema |
| Old DB snapshot migrated but missing rows | Wrong SQL filter/backfill | Counts/invariants and reconciliation |
| Cache session does not restore | Java serialization/classloader/format mismatch | Versioned schema/invalidation policy |
| Kafka replay creates duplicates | Different idempotency/offset/checkpoint | State transition and replay tests |
| Avro reader error | Writer/reader schema resolution/default mismatch | Schema compatibility matrix |
| Protobuf parses but wrong meaning | Reused field number or semantics | Schema history and contract tests |
| V2 reads V1 passes, rollback fails | V1 cannot read V2 data | Mixed-version tests, forward-only decision |
| Regression only in production | Test corpus lacks real data generations | Sanitized representative fixtures |
| File signature invalid | Bytes/charset/canonicalization changed | Signature policy and stable encoding |
| Old encrypted archive cannot open | Different key/provider/envelope metadata | Versioned decryption/test key fixtures |

### 25.1. Do Not Fix Every Error by Enabling Lenient Mode

Some workarounds easily make tests green but are dangerous:
- Ignoring all unknown types/statuses.
- Catching deserialization errors and returning a default object.
- Disabling signature/certificate checks.
- Changing amounts to `double` for "easy parsing".
- Assigning wrong timestamps to the current time.
- Disabling DB constraints without a migration.
- Using object deserialization from untrusted data.
- Automatically regenerating golden fixtures with V2.

If the contract permits a class of legacy data, write an **explicit adapter with logging, metrics, tests, and a lifecycle** instead of loosening the parser to the point where correctness is no longer controlled.

## 26. Practical Implementation Roadmap

### Step 1: Lock Down the Scope of Data to Retain

Identify all stores/formats/schema generations, retention, and owners. Classify cases that must be read directly, require data migration, can be invalidated, or have a forward-only cutover.

### Step 2: Capture a Baseline from V1

Generate/attach synthetic fixtures using V1 serializers/ORMs/producers; store bytes and checksums, producer metadata, and expected business values. If sanitized samples are needed, process them per data security policy.

### Step 3: Build the Compatibility Matrix

Determine whether V2-reads-V1 is mandatory; whether V1-reads-V2 is mandatory for rollback/rolling deployment; and whether older versions are still within the retention window.

### Step 4: Write Tests by Format

- JSON/XML/CSV fixtures.
- Native serialization if still in use.
- DB snapshots and SQL/JPA mapping.
- Avro/Protobuf writer-reader schemas.
- Event replay/DLQ/checkpoints.
- Cache/session persisted values.
- Encryption/signatures if applicable.

### Step 5: Run V2 on the Target Runtime

Pin the JDK vendor/build and framework/serializer/ORM versions. Run legacy reader tests on the exact V2 environment planned for deployment. Distinguish data bugs from classpath/JVM bugs.

### Step 6: Test Migration/Dual-Version Behavior

Restore the old database, apply scripts, and verify invariants; if running two versions in parallel, test V1/V2 reading/writing together; define the rollback window.

### Step 7: Evaluate Edge Cases and Security

Test null/missing, unknown enums, timezone/DST, decimals/encoding, serialized class names, oversized data, corrupted inputs, untrusted deserialization, and signature checks.

### Step 8: Canary and Real-World Observation

Monitor deserialization errors, invalid data counts, replay failures, cache/session issues, and business invariants by schema version; maintain the ability to roll back or roll forward as planned.

### Step 9: Manage the Data Compatibility Lifecycle

Retire the V1 adapter/reader only when:
- No V1 data remains within retention **or** the data has been migrated and fully verified.
- No consumers remain that need to read V1.
- The rollback window has ended or an alternative rollback strategy exists.
- Security/data owners approve.
- Golden fixtures/test coverage are archived or closed per policy.

## 27. Project Example: Upgrading the Orders Service from JDK 17 to 21

**Illustrative context:** An Orders service runs on JDK 17, Spring Boot 2.x, uses PostgreSQL and Redis, and publishes JSON events to Kafka. It is scheduled to upgrade to JDK 21, Spring Boot 3.x/Jakarta, and a new Hibernate major version.

### 27.1. Old Data That Must Be Supported

- PostgreSQL: rows from 2022 onward, with `NULL` in the discount column and old statuses.
- Redis: sessions/cache created by the V1 serializer, TTL of a few hours.
- Kafka: V1 events remaining in topics/DLQs within retention.
- Object store: JSON/XML invoices stored for many years.
- Batch: job checkpoints from V1 that may be restored after failover.

### 27.2. Proposed Test Suite

| Test | Fixture from V1 | Result to prove |
|---|---|---|
| LegacyOrderJsonTest | V1 JSON with amount/time/status | V2 reads the correct business values |
| LegacyInvoiceXmlTest | V1 XML invoice | Namespace/time/amount remain unchanged |
| LegacyOrdersDbTest | V1 PostgreSQL snapshot | ORM/JDBC reads correctly after migration |
| LegacySessionTest | Synthetic V1 Redis session | Restored or invalidated per policy |
| LegacyKafkaReplayTest | V1 event + headers | V2 consumer maps and processes idempotently |
| LegacyCheckpointTest | V1 checkpoint | V2 resumes without skipping/duplicating |
| OldReaderNewDataTest | V2 write under rollout | V1 can read if rollback is still required |
| SecurityNegativeTests | Tampered/unknown payload | Fail-safe, no arbitrary deserialization |

### 27.3. When a Test Fails

Suppose V1 JSON has `status="PENDING_SETTLEMENT"` whereas the V2 domain enum only has `PENDING`/`SETTLED`.

Workflow:
1. Determine what the V1 status used to mean.
2. Do not automatically map it to `SETTLED` just to make the test pass.
3. Coordinate with the business owner to determine the mapping.
4. Update the versioned adapter/migration.
5. Add fixtures and assertions for both valid and error statuses.
6. Check historical records and event replay.
7. Record a deadline if the adapter is only a temporary measure.
8. Re-run tests on the target JDK/framework.

### 27.4. If V1/V2 Run in Parallel

It may be necessary to:
- Expand the DB schema first.
- Have V2 dual-read legacy fields and new fields.
- Ensure the Kafka producer does not emit schemas that V1 consumers cannot understand.
- Use a versioned Redis cache/session strategy.
- Use canarying and metrics for legacy decoding.
- Lock in a forward-only milestone when rollback is no longer possible.

A test suite running only with V2 does not replace mixed-version testing.

## 28. Historical Data Testing Checklist

- [ ] All stores listed: DB, files, object store, broker, cache/session, and checkpoints.
- [ ] Producer versions, serializers, schema histories, and retention known.
- [ ] Fixtures **actually created by the previous version** are present; not regenerated by V2 when tests fail.
- [ ] Checksums/provenance and expected business interpretation recorded.
- [ ] Fixtures are synthetic or sanitized per policy, containing no secrets/PII.
- [ ] V2-read-V1 and, where needed, V1-read-V2 defined.
- [ ] Tests executed on the target JDK/framework/codec.
- [ ] Tested through the production reader/mapping path, not just a raw parser.
- [ ] Missing/null/unknown fields and legacy enums tested.
- [ ] Amount precision/scale/minor units and leading-zero identifiers tested.
- [ ] Charset/Unicode, ISO dates, timezones, and DST edge cases tested.
- [ ] If using Java serialization, `serialVersionUID`, class names, and security filters checked.
- [ ] Untrusted bytes are not deserialized using Java native serialization without controls.
- [ ] V1 DB snapshot restored in an isolated environment.
- [ ] Migrations, row counts, constraints, and domain invariants tested.
- [ ] A database engine sufficiently representative of production used.
- [ ] Avro/Protobuf writer-reader schemas or JSON/XML contracts tested.
- [ ] V1 events replayed and idempotency/DLQ/checkpoints checked.
- [ ] Cache/session compatibility or invalidation policy tested.
- [ ] Encryption/signatures verified and validation not bypassed.
- [ ] V2 data tested with V1 reader if required by rollback/rolling deployment.
- [ ] Alert thresholds defined for deserialization failures and business data mismatches.
- [ ] Approved canary, rollback, or forward-only migration plan in place.
- [ ] Owners assigned for legacy adapters and removal conditions defined after retention.
- [ ] Evidence saved when concluding compatibility; not just "tests green".

## 29. References

The following sources help cross-check APIs and compatibility rules for the actual versions in use:

- [Java Object Serialization Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/index.html): serialized class descriptors and compatibility.
- [OpenJDK JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290): ObjectInputFilter mechanism.
- [OpenJDK JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415): context filters for serialized data.
- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): default charset change starting in JDK 18.
- [Java Time API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/package-summary.html): `Instant`, `OffsetDateTime`, `LocalDateTime`.
- [Jackson Databind](https://github.com/FasterXML/jackson-databind): JSON serialization and polymorphic type handling.
- [Apache Avro Specification](https://avro.apache.org/docs/current/specification/): writer-reader schema resolution.
- [Protocol Buffers — Updating A Message Type](https://protobuf.dev/programming-guides/proto3/#updating): field numbers, unknown fields, and schema evolution.
- [Flyway Documentation](https://documentation.red-gate.com/fd): versioned DB migrations.
- [Liquibase Documentation](https://docs.liquibase.com/): database change tracking.
- [Testcontainers for Java](https://java.testcontainers.org/): testing with database/broker containers.
- [Jakarta EE Specifications](https://jakarta.ee/specifications/): API/ORM/XML binding migration.
- [PostgreSQL Data Types](https://www.postgresql.org/docs/current/datatype.html): date/time, numeric, and storage semantics when using PostgreSQL.

These links serve as directional references. When performing a migration, use the **documentation for the exact pinned JDK, framework, serializer, database, and schema registry versions**. Do not infer from a new release that the same behavior is guaranteed on an old release.

## 30. Conclusion

**Testing data saved from the previous version is a test of the system's ability to uphold contracts over time.** A new version successfully writing and reading its own data does not prove it understands historical data. Fixtures actually created by the old version—complete with provenance and expected business meanings—are required to properly test the **old writer → new reader** direction, as well as the reverse direction when rollback or rolling deployment requires it.

A solid workflow is **inventory data/retention → create and freeze V1 fixtures → define the compatibility matrix → test codecs, ORMs, schemas, events, caches, and checkpoints → verify domain invariants → test mixed-version/rollback → canary and monitor for data errors**. When those checks are integrated into the regression suite, the team can upgrade Java/Jakarta/frameworks without losing the ability to read information accumulated from previous versions and without trading away data integrity for a green build.
