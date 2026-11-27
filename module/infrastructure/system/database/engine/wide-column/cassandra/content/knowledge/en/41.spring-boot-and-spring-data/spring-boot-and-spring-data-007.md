# Mapping Collections/UDTs, Enums, Temporal Types, and Custom Converters with Spring Boot and Spring Data Cassandra

## 1. Why Must Cassandra Mapping Be Designed Intentionally?

In the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module, Apache Cassandra is a **distributed wide-column** DBMS: **partition keys** govern data distribution, tables are built around query patterns, **replication factor (RF)** and **consistency level (CL)** govern read/write guarantees, and repair, compaction, and error handling directly impact Java applications.

**Spring Boot** configures the Java Driver, while **Spring Data Cassandra** maps Java objects to CQL columns via `MappingCassandraConverter`, `CassandraTemplate`, and repositories. Reading/writing an object successfully **does not mean** the CQL model is optimal, updates are atomic, or every type conversion is lossless.

For basic types like `UUID`, `String`, and `long`, mapping is straightforward. Once you introduce:

- `List<E>`, `Set<E>`, `Map<K,V>` with their own collection/tombstone/frozen rules;
- nested **UDTs** (*user-defined types*), sometimes inside collections;
- Java **enums** that may be renamed or extended after older data is already stored;
- `Instant`, `LocalDate`, `LocalTime`, timezones, and timestamp precision;
- **custom converters** for value objects, stable codes, or specialized storage formats;

you must define the **CQL schema ⇄ Java type ⇄ wire representation ⇄ business contract** explicitly.

### Lesson Objectives

After this lesson, you will be able to:

1. Pick the right CQL types for `List/Set/Map` and map them to Java, understanding `frozen` and collection bounds.
2. Define `CREATE TYPE` alongside `@UserDefinedType`, `@Frozen`, and `@Column` for nested objects.
3. Distinguish default text enum mapping, ordinal mapping, and **stable code + converter** mapping.
4. Map temporal concepts safely: instants, calendar dates, times of day, timezones, and precision.
5. Register `@ReadingConverter` and `@WritingConverter` via `CassandraCustomConversions`; distinguish **global type converters** from **per-property converters**.
6. Run round-trip and schema compatibility tests before applying migrations.
7. Recognize when to use CQL/Java Driver directly instead of repository `save(...)`.

This lesson belongs to the **Spring Boot and Spring Data** chapter; examples use modern Spring Data Cassandra APIs with Java Driver 4.x. **Never assume Spring Boot, Spring Data, Java Driver, and Cassandra Server share the same version numbers or mutual compatibility.** Verify the version matrix before shipping code to a real project.

## 2. CQL Type to Java Type Reference Table

| CQL Type | Common Java Type | What to Verify |
| --- | --- | --- |
| `uuid` | `UUID` | Partition keys/IDs generated consistently; no malformed strings |
| `text` / `varchar` | `String` | Encoding, enum codes, app-level length validation |
| `int`, `bigint` | `Integer`, `Long` | Avoid type/range mismatches |
| `decimal` | `BigDecimal` | Precision/scale per business contract |
| `list<text>` | `List<String>` | Ordered; append/prepend may not be idempotent |
| `set<text>` | `Set<String>` | Unique elements; do not rely on iteration order |
| `map<text,text>` | `Map<String,String>` | Updated per key; bound collection size |
| `frozen<postal_address>` | `@Frozen PostalAddress` | Frozen UDT treated as a single value |
| `list<frozen<postal_address>>` | `List<@Frozen PostalAddress>` | UDTs inside collections must follow frozen rules |
| `timestamp` | `Instant` | Absolute point in time; CQL precision is milliseconds |
| `date` | `LocalDate` | Calendar date with no offset/timezone |
| `time` | `LocalTime` | Time of day with no date or timezone |
| `duration` | Driver duration type like `CqlDuration` | Months/days/nanoseconds do not map 1:1 to `java.time.Duration` |
| `text` for timezone | `String` or `ZoneId` value object with converter | Store zone IDs like `Asia/Ho_Chi_Minh`, not just fixed offsets |

**These correspondences are type-selection guidelines**, not a blanket promise of automatic mapping across every version/annotation combination. When dealing with nested UDTs, custom types, or special fields, verify support in your active Spring Data/driver versions and write round-trip tests.

### Mapping Does Not Replace Partition Key Design

Example profile lookup table keyed by `customer_id`:

```sql
SELECT customer_id, status_code, joined_at
FROM commerce.customer_profiles_by_id
WHERE customer_id = ?;
```

Spring repository `findById(customerId)` fits because the partition key is supplied. Yet listing profiles by `city` cannot be solved by adding a Java getter or `@Column`; you need a query-driven table, an appropriate index, or a denormalization pipeline.

## 3. Spring Boot + Spring Data Cassandra Setup

### 3.1. Choosing Dependencies

With Maven and matching Spring Boot dependency management:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-cassandra</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

With Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-cassandra")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

These snippets assume the project uses the matching **Spring Boot plugin/parent or BOM** to manage versions. Never inject extra `java-driver-core` artifacts of another group/version or bump Spring Data Cassandra outside the support matrix, as it can cause `NoSuchMethodError`, `ClassNotFoundException`, or runtime mapping errors.

Spring Data Cassandra **differs from Spring Data JPA**: there are no joins, no JPA persistence context, and no automatic multi-table ACID transactions. Repositories provide a convenient abstraction without changing Cassandra semantics.

### 3.2. Connection Configuration

Example `application.yml`:

```yaml
spring:
  cassandra:
    keyspace-name: commerce
    contact-points:
      - cassandra-node-1:9042
      - cassandra-node-2:9042
    local-datacenter: dc1
    schema-action: NONE
```

Configuration must match the **actual datacenter name**, native protocol endpoints, auth/TLS, and deployed Cassandra Server. For production Spring Boot:

- Supply credentials via a secret manager or access-restricted config.
- Enable TLS, verifying trust material, hostnames, and certificate policies.
- Use a **least-privilege** application role, never superuser.
- **Never enable automatic schema create/drop in production** as a substitute for version-controlled DDL in Git; `schema-action: NONE` is the safe approach for this lesson.
- Use the Boot/Spring Data-managed `CqlSession`, `CassandraTemplate`, or `CassandraRepository`; never create a new session per HTTP request.

These properties illustrate modern Spring Boot. If a project uses an older Boot release or custom Driver config, **verify property names against the running version** before copying.

## 4. End-to-End CQL Schema: Collections, UDTs, Enums, and Temporal Types

This lesson uses a **customer profile** example read and written by `customer_id`. On a lab cluster with datacenter `dc1` and at least three nodes:

```sql
CREATE KEYSPACE IF NOT EXISTS commerce
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TYPE IF NOT EXISTS commerce.postal_address (
    street text,
    city text,
    postal_code text
);

CREATE TABLE IF NOT EXISTS commerce.customer_profiles_by_id (
    customer_id uuid PRIMARY KEY,
    interests set<text>,
    recent_codes list<text>,
    preferences map<text, text>,
    shipping_address frozen<commerce.postal_address>,
    backup_addresses list<frozen<commerce.postal_address>>,
    status_code text,
    joined_at timestamp,
    date_of_birth date,
    preferred_contact_time time,
    timezone_id text
);
```

**Creation order:** keyspace → UDT → table depending on the UDT. In CQL, `postal_address` belongs to keyspace `commerce`; keep the keyspace consistent when referencing UDTs and defining entities.

**RF=3 is a conditional example**, unsuitable for a single-node cluster. In practice, match RF/CL to your topology and check `nodetool status` / schema agreement; never deploy to production merely because `CREATE ... IF NOT EXISTS` returned no error. `IF NOT EXISTS` can mask an existing table with a **different schema than expected**.

Understanding the fields:

- `interests`: set of interests, deduplicated.
- `recent_codes`: ordered sequence of codes; if unbounded, change the model because collections in one partition/cell have practical limits.
- `preferences`: small key/value map; not a dumping ground for huge JSON blobs.
- `shipping_address`: fixed nested object stored as a **frozen UDT**.
- `backup_addresses`: list of frozen UDTs.
- `status_code`: stable status code mapped from a Java enum via a converter.
- `joined_at`: absolute instant in time.
- `date_of_birth`: calendar date.
- `preferred_contact_time`: time of day in the business-specified timezone.
- `timezone_id`: IANA zone name used to interpret local time.

## 5. Mapping Entities and UDTs with Annotations

### 5.1. Defining the UDT Class

Spring Data Cassandra supports `@UserDefinedType`:

```java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.UserDefinedType;

@UserDefinedType("postal_address")
public class PostalAddress {

    private String street;
    private String city;

    @Column("postal_code")
    private String postalCode;

    public PostalAddress() { }

    public PostalAddress(String street, String city, String postalCode) {
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
    }

    public String getStreet() { return street; }
    public void setStreet(String street) { this.street = street; }

    public String getCity() { return city; }
    public void setCity(String city) { this.city = city; }

    public String getPostalCode() { return postalCode; }
    public void setPostalCode(String postalCode) {
        this.postalCode = postalCode;
    }
}
```

Key points:

- `@UserDefinedType("postal_address")` maps the Java class to the CQL UDT named `postal_address`.
- `@Column("postal_code")` is critical when the Java field is `postalCode` while CQL uses `postal_code`.
- A no-arg constructor and getters/setters are a simple learning style. Modern Spring Data also supports constructor binding, records, and immutable objects under specific conditions; **do not mix immutable patterns with setters without checking version behavior**.
- For mapped UDTs, `MappingCassandraConverter` needs an accurate UDT metadata/resolver and keyspace. Hand-built beans lacking a mapping context or user type resolver may behave differently from Spring Boot auto-config.

### 5.2. Entity Containing Collections, UDTs, and Temporal Types

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.CassandraType;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.Frozen;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("customer_profiles_by_id")
public class CustomerProfile {

    @PrimaryKey("customer_id")
    private UUID customerId;

    @Column("interests")
    @CassandraType(
        type = CassandraType.Name.SET,
        typeArguments = CassandraType.Name.TEXT)
    private Set<String> interests;

    @Column("recent_codes")
    private List<String> recentCodes;

    @Column("preferences")
    private Map<String, String> preferences;

    @Column("shipping_address")
    @Frozen
    private PostalAddress shippingAddress;

    @Column("backup_addresses")
    private List<@Frozen PostalAddress> backupAddresses;

    @Column("status_code")
    private CustomerStatus statusCode;

    @Column("joined_at")
    private Instant joinedAt;

    @Column("date_of_birth")
    private LocalDate dateOfBirth;

    @Column("preferred_contact_time")
    @CassandraType(type = CassandraType.Name.TIME)
    private LocalTime preferredContactTime;

    @Column("timezone_id")
    private String timezoneId;

    public CustomerProfile() { }

    // Full getters/setters are required in real application code.
}
```

Here `@CassandraType` on `interests` shows how to declare `set<text>` explicitly, while `List<String>` and `Map<String,String>` show mapping normally inferred from generic types. Verify against the actual schema rather than assuming property names convert to snake_case as desired: use `@Column` whenever column names differ.

`CustomerStatus` is an enum defined in Section 9. When assembling standalone snippets, **add the enum/converter classes** and getters/setters before compiling; the blocks above are domain model excerpts, not a complete standalone source file.

### 5.3. When Is `@CassandraType` Required?

Spring Data usually infers types from Java declarations, yet this annotation is helpful when:

- You need a **different CQL type than the default** for a Java type.
- A collection needs explicit `LIST/SET/MAP` and element/key/value types.
- You use raw `UdtValue` instead of a `@UserDefinedType` class.
- An enum must be stored numerically for a legacy schema.
- Code generators or schema validation need exact CQL type metadata.

Example map with text keys and values:

```java
@CassandraType(
    type = CassandraType.Name.MAP,
    typeArguments = {
        CassandraType.Name.TEXT,
        CassandraType.Name.TEXT
    })
private Map<String, String> preferences;
```

Never use annotations to "fix" a mismatched schema: `Map<String,String>` cannot magically map safely to `map<uuid,decimal>` just by changing `typeArguments` while Java still holds strings. **CQL DDL and Java generic types must agree.**

## 6. Collection Mapping: `List`, `Set`, `Map`, and Update Semantics

Cassandra collections work well when **element counts are small and realistically bounded** within a partition. Never treat them as unbounded child tables or RDBMS 1-to-many join substitutes.

| CQL / Java | Semantics | Risks |
| --- | --- | --- |
| `list<text>` ↔ `List<String>` | Element order matters | Append/prepend/index mutations, concurrency, size/reading entire list |
| `set<text>` ↔ `Set<String>` | Unique by value, no business ordering | Do not depend on iteration order; deletes/tombstones and updates |
| `map<text,text>` ↔ `Map<String,String>` | Key-value lookup inside a collection | Too many keys, frequent updates/deletes, tombstones |
| `frozen<list<text>>` ↔ `@Frozen List<String>` (mapping-dependent) | Entire collection stored as a single value | Individual element updates differ from non-frozen |
| `list<frozen<postal_address>>` | Each UDT element is frozen | Object elements; nested updates are constrained |

### 6.1. Updating Directly via CQL to Preserve Element Semantics

Examples updating sets, maps, and lists:

```sql
-- Add a value to a set (deduplicated element semantics).
UPDATE commerce.customer_profiles_by_id
SET interests = interests + {'java'}
WHERE customer_id = ?;

-- Update a single key in a map.
UPDATE commerce.customer_profiles_by_id
SET preferences['language'] = 'vi'
WHERE customer_id = ?;

-- Append an element to a list; not idempotent by default on retry.
UPDATE commerce.customer_profiles_by_id
SET recent_codes = recent_codes + ['WELCOME10']
WHERE customer_id = ?;
```

**Key points to remember:**

- `Set` avoids duplicate values at the data type/write level, yet **this does not provide exactly-once guarantees** for other side effects.
- Per-key `Map` updates differ from replacing the **entire map**; multiple writers updating independent keys are safer than overwriting the whole object.
- A `List` append that hits a request timeout **must not be retried blindly**: the same element can be appended twice.
- With Spring Data repository `save(entity)`, never assume it generates fine-grained `SET col[key] = ...` or element-append statements. When per-element CQL semantics and write efficiency matter, use **`CqlTemplate` or explicit driver statements** and verify exact semantics.
- Element updates/deletions can create tombstones; monitor retention/compaction and bound collection size.

### 6.2. `null`, Empty, and Absent Are Not Automatically Equivalent

In Java applications, you may encounter:

```text
null
Collections.emptySet()
Collections.emptyList()
Collections.emptyMap()
```

For persistence:

- **Missing column/value** may be materialized by the Java mapper as `null`.
- An empty collection is not always stored/rehydrated by Cassandra identically to an empty heap object; behavior depends on type, version, write mode, and converter.
- Setting a property to `null` and calling `save` can trigger deletes/tombstones or be skipped depending on API/mapping null-handling. **Never guess**: inspect emitted CQL and run integration round-trips.
- Cassandra collections **do not support arbitrary `null` elements** like Java collections; validate lists/sets/maps before writing.
- Never overload `null` to distinguish multiple business states without explicit columns/schema.

If an API must distinguish "property omitted" from "delete property", use an explicit PATCH contract and dedicated mutations; never pass a partial DTO to repository `save` hoping Spring infers intent.

### 6.3. Collection Limits and the Wide-Column Model

Suppose one customer has a million orders: **never** store all order IDs inside a single `List<UUID>` on a profile row. Build a query-driven table instead:

```sql
CREATE TABLE commerce.orders_by_customer (
    customer_id uuid,
    created_at timestamp,
    order_id uuid,
    status text,
    PRIMARY KEY ((customer_id), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

Clustering columns let you read within the `customer_id` partition and paginate cleanly; if partitions grow too large, consider **time/key bucketing**. Reserve collections for **small preference lists and compact attributes**, never unbounded histories.

## 7. UDTs: Structured Values, Not Relational Tables

`postal_address` is a **user-defined type** scoped to the keyspace, holding `street`, `city`, and `postal_code`. A UDT has no primary key of its own like an independent table.

### 7.1. `frozen` and Mutation Limits

```sql
shipping_address frozen<postal_address>
```

With `frozen<postal_address>`, Cassandra treats the structure as a **single value**; to change one field, the app normally supplies the full updated UDT rather than updating individual subfields directly.

Example CQL replacing the whole UDT:

```sql
UPDATE commerce.customer_profiles_by_id
SET shipping_address = {
    street: '12 Nguyen Hue',
    city: 'Ho Chi Minh City',
    postal_code: '700000'
}
WHERE customer_id = ?;
```

This illustrates named-field UDT literal syntax. Verify UDT/frozen types and CQL syntax for your version. Replacing a frozen UDT can cause **lost updates** if two requests read the same snapshot, modify different fields, and overwrite the whole object.

If business logic requires updating subfields independently, consider a **non-frozen** UDT where supported by your Cassandra version or separate top-level columns. **You cannot remove `frozen` from an existing schema just by deleting a Java annotation**; changing CQL types requires a controlled migration.

### 7.2. Nested UDTs Inside Collections

```sql
backup_addresses list<frozen<postal_address>>
```

UDTs inside lists must satisfy element frozen rules. Spring Data expresses this as:

```java
@Column("backup_addresses")
private List<@Frozen PostalAddress> backupAddresses;
```

Verify support for type-use annotations in your **actual Spring Data/driver versions**. If an older stack lacks support for this annotation style, configure types explicitly, use `UdtValue` with prepared statements, or adjust the model — never mutate wire types casually.

### 7.3. Adding a Field to a UDT

```sql
ALTER TYPE commerce.postal_address
ADD country_code text;
```

After migration:

1. Wait for schema agreement; old and new schemas must remain compatible during rolling deploys.
2. Add the Java field `@Column("country_code") private String countryCode`.
3. Expect older UDT values to yield `null` for the new field, or backfill if business rules require it.
4. Test writes from older app versions: a client unaware of the new field **can rewrite a frozen UDT without that field**.
5. Never treat "mapping succeeded" as proof that all existing records have the new field backfilled.
6. Avoid renaming/dropping UDT fields while old clients still run, and plan breaking changes with a separate migration.

**UDTs shared across tables:** one `ALTER TYPE` can impact multiple tables; audit all affected tables, apps, and backup/restore plans before altering.

## 8. Enums: Text by Default, Not Safe Under Renames

Suppose we have an enum:

```java
public enum CustomerStatus {
    ACTIVE,
    PAUSED,
    CLOSED
}
```

By default, Spring Data Cassandra typically maps enums to **CQL `text`** using the enum constant's name. That is usually far safer to inspect than ordinals:

| Storage Form | CQL Example | Pros | Risks |
| --- | --- | --- | --- |
| Enum name | `'ACTIVE'` | Readable, stable if constant names stay fixed | Renaming `ACTIVE` → `ENABLED` breaks mapping of existing rows |
| Ordinal / int | `0`, `1`, `2` | Compact, sometimes found in legacy schemas | Inserting or reordering constants shifts numeric meanings |
| **Stable code** | `'A'`, `'P'`, `'C'` | Storage contract decoupled from Java names | Requires converters and independent code governance |
| Plain business code text | `String statusCode` | No converter needed | Loses domain type-safety without validation |

### 8.1. Why You Should Not Rely on Enum Ordinals

```java
// Example showing numeric annotation exists; NOT recommended for new designs.
@CassandraType(type = CassandraType.Name.INT)
private CustomerStatus statusCode;
```

Suppose the original enum is:

```java
enum CustomerStatus { ACTIVE, PAUSED, CLOSED } // ordinals 0, 1, 2
```

A developer prepends `PENDING`:

```java
enum CustomerStatus { PENDING, ACTIVE, PAUSED, CLOSED }
```

If ordinals are stored, `1`—which originally meant `PAUSED`—is now read as `ACTIVE`. This causes **silent data corruption**, far harder to catch than an exception. Therefore, **never use ordinals as a persistent storage format** for long-lived data without strict legacy constraints and compatibility safeguards.

### 8.2. Adding a New Enum Code Requires a Rollout Strategy

If old Java instances do not recognize code `'H'` yet new instances write `'H'`, old readers will throw on read. Follow this sequence:

1. **Expand readers**: deploy code that understands the new code without writing it yet.
2. Confirm all readers, workers, and batch jobs have compatible logic.
3. **Enable writers**: begin emitting the new code, feature-flagged if needed.
4. Monitor conversion errors and stored code distributions.
5. Remove legacy code paths only after data and all consumers have migrated.

Never make a converter silently turn **any unknown code into `ACTIVE`**: that masks data corruption and rollout bugs. Depending on contract, use an explicit `UNKNOWN` value, quarantine, or fail fast with metrics.

## 9. Custom Converters for Stable Enum Codes

Create an enum with immutable codes:

```java
public enum CustomerStatus {
    ACTIVE("A"),
    PAUSED("P"),
    CLOSED("C");

    private final String code;

    CustomerStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static CustomerStatus fromCode(String code) {
        for (CustomerStatus value : values()) {
            if (value.code.equals(code)) {
                return value;
            }
        }
        throw new IllegalArgumentException(
            "Unknown customer status code: " + code);
    }
}
```

In CQL, `status_code text` stores `'A'`, `'P'`, or `'C'`, **decoupled** from Java enum constant names. Example converter pair:

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class CustomerStatusWriteConverter
        implements Converter<CustomerStatus, String> {

    @Override
    public String convert(CustomerStatus source) {
        return source.code();
    }
}
```

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public final class CustomerStatusReadConverter
        implements Converter<String, CustomerStatus> {

    @Override
    public CustomerStatus convert(String source) {
        return CustomerStatus.fromCode(source);
    }
}
```

Key points:

- `@WritingConverter` converts **Java domain → Cassandra-storable type**.
- `@ReadingConverter` converts **Cassandra-read type → Java domain**.
- Both directions are needed for round-trips. Having only a write converter breaks enum reads or violates the contract.
- The `String → CustomerStatus` mapping applies to **every property of type `CustomerStatus`** handled by that mapping context, not just one field.
- Converters **are not always picked up automatically via classpath scanning**; register them explicitly with the mapping infrastructure.
- Inside converters, validate `null`/unknown codes per contract without logging sensitive data. You may define an `UNKNOWN` enum constant if the domain permits it, provided unsupported codes are never misclassified as valid statuses.

### 9.1. Registering via `CassandraCustomConversions`

Example for corresponding Spring Data Cassandra 4.x+:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.convert.CassandraCustomConversions;

@Configuration(proxyBeanMethods = false)
public class CassandraMappingConfiguration {

    @Bean
    CassandraCustomConversions cassandraCustomConversions() {
        return CassandraCustomConversions.create(registry -> {
            registry.registerConverter(new CustomerStatusWriteConverter());
            registry.registerConverter(new CustomerStatusReadConverter());
        });
    }
}
```

If the application **extends `AbstractCassandraConfiguration`**, you may override `customConversions()` rather than declaring a duplicate bean. If Spring Boot auto-configures Cassandra mapping, verify the `CassandraCustomConversions` bean is picked up by the **active `MappingCassandraConverter`** and not shadowed by a second config. Exact `create(...)`/registration APIs depend on the Spring Data version; on older stacks, use the constructor/registration supported by that release.

**Never register a global `Converter<String,String>` to normalize statuses**: it can unintentionally alter **every `text` column**. When only one property needs special conversion, use a per-property converter.

### 9.2. Unit Testing Converters Independently

```java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class CustomerStatusConversionTest {

    private final CustomerStatusWriteConverter writer =
        new CustomerStatusWriteConverter();
    private final CustomerStatusReadConverter reader =
        new CustomerStatusReadConverter();

    @Test
    void roundTripStableCode() {
        assertEquals("A", writer.convert(CustomerStatus.ACTIVE));
        assertEquals(CustomerStatus.ACTIVE, reader.convert("A"));
        assertEquals(CustomerStatus.PAUSED, reader.convert("P"));
    }

    @Test
    void rejectUnknownCode() {
        assertThrows(
            IllegalArgumentException.class,
            () -> reader.convert("UNSUPPORTED"));
    }
}
```

This is a **converter unit test**; it does not prove `CassandraTemplate`/repositories actually invoke the converter or that the CQL column type matches. Add integration tests reading/writing real Cassandra.

## 10. Per-Property Converters: Avoiding Global Type Side Effects

Sometimes two Java `String` fields need different formats (one uppercased, one preserved), or the same value object uses two wire formats in different tables.

In Spring Data Cassandra versions supporting **property-based conversions**, use `@ValueConverter` with a `PropertyValueConverter`/`CassandraValueConverter`. Conceptual example:

```java
// Illustrative per-property annotation; import from your active
// Spring Data Commons/Cassandra version and implement the matching converter.
@ValueConverter(NormalizedLanguageCodeConverter.class)
@Column("language_code")
private String languageCode;
```

`NormalizedLanguageCodeConverter` is an **application-defined placeholder class**; the snippet is incomplete without its implementation. The goal is scoping conversion strictly to **`languageCode`** rather than affecting every `String` across all Cassandra entities.

### 10.1. Choosing Global vs. Per-Property

| Mechanism | When Appropriate | Risks |
| --- | --- | --- |
| `CassandraCustomConversions` + `@ReadingConverter/@WritingConverter` | Same domain type always shares one wire format | Broad scope affects every property of that type |
| `@ValueConverter`/`PropertyValueConverter` | One column has bespoke conversion rules | Version-dependent; requires context/registration tests |
| `@CassandraType` | Selecting the CQL type for a property | Does not perform specialized business encodings |
| Explicit `CqlSession` + driver codec | Need lower-level CQL/wire protocol control | Bypasses part of Spring mapping; manual map/validate |
| Domain DTO → entity mapping outside Spring Data | Need clean separation of API/domain from persistence | Extra mapping code, clearer boundaries |

**Never perform network I/O or call external services inside a converter.** Mappers run on persistence reads/writes and must stay deterministic, fast, and thread-safe. If sensitive fields require encryption, use a key-managed converter/codec rather than rolling custom crypto, and measure overhead.

## 11. Temporal Types: `Instant`, `LocalDate`, `LocalTime`, `ZoneId`

The most common temporal bug is confusing an **absolute instant** with a **local date/time**.

| Business Intent | CQL | Java | Explanation |
| --- | --- | --- | --- |
| Customer registered at an instant | `timestamp` | `Instant` | Point on the UTC timeline |
| Date of birth | `date` | `LocalDate` | Calendar date without timezone or time |
| Notify at 09:30 | `time` | `LocalTime` | Time of day; cannot determine an instant alone |
| Customer-selected timezone | `text` | `String` storing IANA `ZoneId` | Combined with date/time to resolve an instant |
| Exact 30-minute wait window | Often `bigint` millis or matching type | `Duration` | Fixed elapsed span; do not assume CQL `duration` matches 1:1 |
| "One month" recurrence cycle | CQL `duration` or custom model | `Period` / business rule | "1 month" has no fixed second count |

### 11.1. `timestamp` Stores an Instant, Not the Original Timezone

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant stored = Instant.parse("2026-11-21T02:30:00Z");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime local = stored.atZone(zone);
// local corresponds to 09:30 in Asia/Ho_Chi_Minh.
```

CQL `timestamp` stores an instant; it does not remember "which timezone the user chose". For local display, store a **separate zone ID or apply a fixed policy**.

**Why avoid `LocalDateTime` for absolute instants?** It lacks an offset/timezone; `2026-11-21T09:30` can mean different instants across regions. Legacy converters in some stacks can depend on the **system-default timezone** when bridging via `java.util.Date`. For event/audit/purchase timestamps, prefer `Instant` and test across differing JVM timezones.

### 11.2. Precision of CQL `timestamp`

CQL `timestamp` has **millisecond precision**. `Instant` supports nanoseconds, so round-trips truncate sub-millisecond digits.

```java
import java.time.Instant;

Instant source = Instant.parse("2026-11-21T02:30:00.123456789Z");
Instant expected = Instant.ofEpochMilli(source.toEpochMilli());

// expected has .123 seconds, not .123456789.
```

If business logic requires micro/nanosecond precision, never silently store into `timestamp` expecting lossless round-trips: use a dedicated storage representation (e.g., epoch nanoseconds with overflow and precision rules analyzed) or another appropriate type.

### 11.3. CQL `date` and Birthdays

`LocalDate.of(1998, 4, 12)` maps naturally to CQL `date`. Never convert it to an `Instant` at UTC midnight when only a **calendar date** is meant, because another user timezone shifts that instant to a **different calendar day**.

```java
import java.time.LocalDate;

LocalDate birthday = LocalDate.of(1998, 4, 12);
```

### 11.4. CQL `time` Holds Nano-of-Day, No Timezone

```java
import java.time.LocalTime;

LocalTime contactHour = LocalTime.of(9, 30);
long nanoOfDay = contactHour.toNanoOfDay();
```

CQL `time` represents a time of day, not an instant comparable directly against `Instant.now()`. To fire a 09:30 notification in the user's timezone, combine:

1. The scheduled `LocalDate`.
2. The `LocalTime` 09:30.
3. A valid IANA `ZoneId` (e.g., `Asia/Ho_Chi_Minh`).
4. Explicit policy for **non-existent or ambiguous (repeated) hours** on DST transition days.
5. Resolve to an `Instant` only when scheduling execution.

**Never store timezones solely as fixed offsets like `+07:00`** for long-term schedules in regions with DST or legislative timezone changes.

### 11.5. CQL `duration` Is Not Pure Java `Duration`

Cassandra `duration` stores **months, days, and nanoseconds**, whereas `java.time.Duration` measures exact seconds/nanoseconds and `Period` models calendar units.

- "One month" has no fixed number of seconds.
- Adding `1 month` to the 31st differs from adding 30 days.
- If using the driver's `CqlDuration`, verify serialization/mapping and business interpretation.
- For request timeouts, `java.time.Duration` belongs in **application config**, not necessarily a CQL `duration` column.

## 12. Custom Converters for Temporal Value Objects: When Needed and When Not

Spring Data Cassandra already supports common `java.time` types; do not write custom `Instant ↔ String` converters when the column is `timestamp` and the driver already maps it cleanly.

However, a legacy schema might use `bigint` to store **epoch milliseconds**. If the domain wraps `Instant` in a value object representing observation time:

```java
import java.time.Instant;

public record ObservedAt(Instant value) {
    public ObservedAt {
        if (value == null) {
            throw new IllegalArgumentException("ObservedAt is required");
        }
    }
}
```

Convert `ObservedAt ↔ Long` as epoch millis:

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class ObservedAtWriteConverter
        implements Converter<ObservedAt, Long> {

    @Override
    public Long convert(ObservedAt source) {
        return source.value().toEpochMilli();
    }
}
```

```java
import java.time.Instant;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public final class ObservedAtReadConverter
        implements Converter<Long, ObservedAt> {

    @Override
    public ObservedAt convert(Long source) {
        return new ObservedAt(Instant.ofEpochMilli(source));
    }
}
```

Register both converters in the **same `CassandraCustomConversions`** from Section 9 if desired. On the entity, the property must map to a **`bigint`** column, and all applications must agree the integer represents epoch **milliseconds**, not seconds. If the schema uses `timestamp`, never force this converter onto it without a CQL migration.

**Note on Java `record`:** `record` requires supporting JDK baselines. On older stacks, use an immutable class with constructor/getters. Verify Spring Data mapping/constructor handling whenever using value objects or records in the domain model.

## 13. Repository, Template, and Direct CQL: Choosing by Semantics

### 13.1. Repository for Primary-Key Entity Reads/Writes

```java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface CustomerProfileRepository
        extends CassandraRepository<CustomerProfile, UUID> {
}
```

Used from a service:

```java
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class CustomerProfileService {

    private final CustomerProfileRepository repository;

    public CustomerProfileService(CustomerProfileRepository repository) {
        this.repository = repository;
    }

    public CustomerProfile load(UUID customerId) {
        return repository.findById(customerId)
            .orElseThrow(() ->
                new IllegalArgumentException("Profile not found"));
    }

    public CustomerProfile save(CustomerProfile profile) {
        return repository.save(profile);
    }
}
```

Repositories apply mapping metadata and custom conversions, yet:

- `save` is not a JPA-style ACID transaction.
- Never assume `save` updates only the changed element in a collection or UDT.
- Never assume an entity with UDTs/lists can be read/written whole without watching latency and row size.
- If the Spring Data model mismatches CQL, fix the model/DDL rather than blaming converters.
- When multiple writers update the same frozen UDT/collection concurrently, handle versioning/contention and choose appropriate conditional CQL mutations.

### 13.2. `CassandraTemplate` for Mapped Operations with Extra Flexibility

Spring Boot can inject `CassandraTemplate`:

```java
import java.util.UUID;
import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProfileTemplateService {

    private final CassandraTemplate template;

    public ProfileTemplateService(CassandraTemplate template) {
        this.template = template;
    }

    public CustomerProfile load(UUID id) {
        return template.selectOneById(id, CustomerProfile.class);
    }

    public CustomerProfile insert(CustomerProfile profile) {
        return template.insert(profile);
    }
}
```

Verify exact `insert(...)` overloads and return types on your Spring Data version before adopting. These snippets illustrate abstraction and mapping choices; they **do not replace integration tests verifying emitted CQL**.

### 13.3. When Element-Level CQL Updates Are Needed

To update one map key without replacing the entire map, use the Spring Boot-managed `CqlSession`:

```java
import java.util.UUID;
import org.springframework.stereotype.Service;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

@Service
public class ProfilePreferencesWriter {

    private final CqlSession session;
    private final PreparedStatement updateLanguage;

    public ProfilePreferencesWriter(CqlSession session) {
        this.session = session;
        this.updateLanguage = session.prepare(
            "UPDATE commerce.customer_profiles_by_id " +
            "SET preferences['language'] = ? " +
            "WHERE customer_id = ?");
    }

    public void setLanguage(UUID customerId, String language) {
        session.execute(updateLanguage.bind(language, customerId));
    }
}
```

**Important note:** when using **`CqlSession` directly**, `CassandraCustomConversions` does not automatically convert domain objects. Bound arguments must match types the driver understands (here simple `String`/`UUID`). To bind a `CustomerStatus` domain enum directly, convert it to its stable code or use a driver codec — never assume Spring converters run automatically on the raw driver.

**Never concatenate untrusted input into column/table names or CQL literals.** Use prepared/bound statements for values. For complex collection/UDT mutations with concurrent writers, test semantics and idempotency before enabling retries.

## 14. Collection/UDT Mapping and Cluster Performance

An app can compile cleanly and map without errors yet still degrade production:

### 14.1. Large Collections Inflate I/O and Tombstones

With one partition per customer, a profile holding tens of thousands of keys in `preferences` makes every full entity load expensive in memory and network. Frequent element updates/deletions generate tombstones, impacting reads depending on compaction/TTL/repair and access patterns.

Measure:

- **p95/p99** element/field counts, not just averages.
- Bytes per profile, row/cell counts, JVM heap/GC, and page sizes for multi-row queries.
- Frequency of full collection replacements vs. per-element updates.
- Tombstone volume from delete/update paths.
- RF/CL, coordinator read/write latencies, and disk/compaction metrics.

### 14.2. Frozen UDTs Increase Lost-Update Risk

If two workers:

1. Read the same old `shipping_address`.
2. Worker A changes `city` and writes the whole UDT.
3. Worker B changes `postal_code` on the stale snapshot and writes the whole UDT.

the final state keeps only the last writer's version by timestamp; the first update is overwritten. **Never use `@Frozen` merely for mapping convenience** when concurrent field-level updates are required.

### 14.3. Do Not Confuse CQL Collections with Unbounded Domain Aggregates

A domain `Customer` having an unbounded `List<Order>` should not be mapped to `list<frozen<order>>` in one CQL column. In Cassandra, model an `orders_by_customer` table with clustering columns, bounded partition sizes, and clean pagination.

## 15. Migration Workflows for Schema or Conversion Changes

### 15.1. Adding a New Enum State

Suppose you need a new state `SUSPENDED("S")`:

1. Expand the enum and converter so readers recognize `"S"` **without writing it yet**.
2. Run integration tests containing both old and new codes.
3. Deploy all readers, workers, batch jobs, and dependent services.
4. Enable writers to emit `"S"`, behind a feature flag if appropriate.
5. Watch conversion errors, unknown codes, and business metrics.
6. Retain legacy aliases/handling while historical data still exists; never delete old interpretations prematurely.

If changing an already-stored stable code (e.g., `"A"` to `"ACTIVE"`), implement **dual-readers/dual-writers or a data migration** explicitly; never change the converter in one step assuming CQL values updated themselves.

### 15.2. Migrating from Enum Ordinals to Text

Migrating a legacy `status_code int` column to `status_code text`:

- Never just swap `@CassandraType` or Java converters without changing the CQL column type.
- Consider adding `status_code_v2 text` or a v2 table following expand–migrate–contract.
- New readers understand both old and new columns during transition; writers emit stable text codes.
- Backfill by partition key with checkpoints, bounded concurrency, and idempotency.
- Only after reconciliation and retiring all old code, drop the legacy column/path via reviewed migration.

### 15.3. Changing UDT Fields

Adding `country_code` to `postal_address` also requires care:

- Shared UDTs may affect multiple tables.
- Old apps rewriting frozen UDTs can wipe out the new field.
- Wait for schema agreement before new code references the field.
- Existing rows read `null` for the new field; avoid injecting misleading business defaults.
- Changing CQL types or frozen semantics may require a new column/table instead of in-place `ALTER`.

### 15.4. Standardizing Timezone/Precision

If an old column stored `LocalDateTime` and the team wants `Instant`:

1. Identify the timezone the historical data **actually represents**. Never guess UTC.
2. Check records falling inside DST gaps or overlaps.
3. Backfill with an explicit policy for ambiguous timestamps.
4. Preserve original values/audit trails for verification.
5. Deploy readers/writers in order and test across differing container/JVM timezones.
6. Avoid combining Cassandra Server upgrades, CL changes, and temporal migrations simultaneously when separable.

**Version control tracks DDL history; custom converters live in application code.** To support safe app rollbacks, the older app version **must still understand the wire format** written by the newer version.

## 16. Testing Mapping: Converter Unit Tests Are Not Enough

### 16.1. Unit Layer

Test in isolation:

- Enum `CustomerStatus ↔ String` round-trips.
- Unknown codes follow the defined policy.
- `ObservedAt ↔ Long` at 0, pre-epoch, bounds, and millisecond precision.
- Null/empty/invalid inputs per contract.
- Converters are thread-safe with no shared mutable state.

### 16.2. Integration Layer Against Real Cassandra

Use a test cluster/container close to the production version with matching CQL migrations; **never** mock `CassandraTemplate` alone and declare mapping verified.

Minimum test cases:

| Case | Input | Verify on Read-Back |
| --- | --- | --- |
| `Set<String>` | Two distinct interests | No duplicates; never assume order |
| `List<String>` | Two recent codes | Preserves order; test append behavior |
| `Map<String,String>` | `language=vi` | Updating one key preserves other keys |
| Frozen UDT | Street/city/postalCode | Full round-trip |
| List of frozen UDTs | Two addresses | Nested types accurate and mapped |
| Stable-code enum | `ACTIVE` | Cassandra stores `"A"`, Java reads `ACTIVE` |
| Unknown enum | `"X"` written via raw CQL | Reader fails or quarantines per policy |
| `Instant` | With nanoseconds | Compare at millisecond precision |
| `LocalDate` | Birthday | No off-by-one day shift across timezones |
| `LocalTime` | 09:30 | No fabricated offset or date |
| Null vs. empty | Null/empty set/list/map | Observe actual behavior; never guess |
| Legacy migration | Nullable new column | Old/new apps interoperate per plan |

### 16.3. Integration Test Skeleton

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Optional;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class CustomerProfileMappingIntegrationTest {

    @Autowired
    CustomerProfileRepository repository;

    @Test
    void canReadWrittenProfile() {
        UUID id = UUID.randomUUID();

        CustomerProfile profile = new CustomerProfile();
        // Set customerId, interests, recentCodes, preferences,
        // shippingAddress, statusCode, joinedAt, dateOfBirth,
        // preferredContactTime, and timezoneId via setters.
        // Requires schema migrations and a running test Cassandra.

        // Illustrative intent only:
        // repository.save(profile);
        // Optional<CustomerProfile> loaded = repository.findById(id);
        // assertTrue(loaded.isPresent());
        // assertEquals(CustomerStatus.ACTIVE, loaded.get().getStatusCode());
    }
}
```

This is a **test skeleton**; save/read lines are intentionally commented out because `CustomerProfile` above omits full getters/setters and no live test cluster is assumed. In your project, add setters, populate `id`, run CQL migrations in the test environment, and **uncomment assertions** to verify real round-trips. Never run unit/integration tests against production clusters.

### 16.4. Cross-Check with CQL Independent of the Java Mapper

If an integration test writes and reads through the same mapper, symmetrical bugs cancel out silently. Inspect raw CQL via `cqlsh` or Java Driver `Row`:

```sql
SELECT customer_id, interests, recent_codes, preferences,
       shipping_address, backup_addresses,
       status_code, joined_at, date_of_birth,
       preferred_contact_time, timezone_id
FROM commerce.customer_profiles_by_id
WHERE customer_id = ?;
```

Verify raw `status_code='A'`, `timestamp` precision, UDT field names, list ordering, and collection contents. In automated tests, bind `?` using a prepared statement; `?` above is a bind marker, **not a literal to paste directly into `cqlsh`**.

## 17. Common Errors and Investigation Workflow

| Symptom | Possible Causes | Remediation |
| --- | --- | --- |
| `MappingException` mapping a field | Java/CQL type mismatch, missing annotation, unregistered converter | Check schema, entity, and custom conversions |
| `Unknown type` / UDT not found | `CREATE TYPE` not run, wrong keyspace, pending schema agreement | Run migrations in order; check metadata |
| UDT or nested field reads as `null` | New CQL field, mismatched `@Column`, old data | Inspect raw UDT, nullability, and app versions |
| `InvalidQuery` on frozen | Trying to UPDATE a subfield of a frozen UDT/collection | Replace the entire frozen value or redesign |
| New enum crashes old app | Old reader does not know new code | Expand readers first; feature-flag writer |
| Enum ordinal changed meaning | Constants inserted/reordered | Migrate to stable text codes |
| `CustomerStatus` writes enum name instead of code | Converter not picked up by mapping infrastructure | Check `CassandraCustomConversions` bean/overrides |
| `LocalDateTime` shifts hours across envs | Default JVM timezone / `Date` conversion | Use `Instant` for timestamps; test timezones |
| `Instant` loses micro/nanoseconds | CQL `timestamp` has millisecond precision | Normalize or redesign storage per requirements |
| `LocalDate` shifts by a day | Wrong conversion via instant/zone | Store CQL `date`; verify converter |
| Collection update loses other keys/elements | Repo `save` overwrites whole collection or concurrency | Element-level CQL mutations, CAS, or redesign |
| List gets duplicate appends after timeout | Non-idempotent retry | Request IDs/idempotency; no blind retries |
| Direct `CqlSession` bind fails on enum | Spring converters do not run on raw driver | Bind stable `String` code or explicit codec |
| Memory/latency spikes loading profiles | Huge collections/UDTs, full entity reads | Bound collections; create query-driven tables |
| Tests pass yet production fails | RF/DC/schema/data/version mismatch | Integration test on prod-like cluster; schema diff |

### 17.1. Layer-by-Layer Error Triage

```text
App startup / missing class?
  -> Spring Boot/Spring Data/Driver versions, dependency graph.

CQL unknown keyspace/type/table?
  -> Schema migration, keyspace, UDT resolver, schema agreement.

Class maps, wrong field name?
  -> @Column, @UserDefinedType, @Frozen, @CassandraType.

Read/write conversion fails?
  -> @ReadingConverter/@WritingConverter, registration, unknown enum code.

Data silently altered in meaning?
  -> Enum ordinals, timezone conversions, timestamp precision, null/empty.

Timeout / Unavailable?
  -> Cassandra RF/CL, hot partitions, I/O, compaction, tombstones, retries.

Collection update loses data?
  -> Whole-value overwrites, concurrency, mutation semantics, read-modify-write.
```

Never raise timeouts or lower CL to mask mapping errors; conversely, never write a new converter when the real fault is insufficient replicas or an unapplied schema migration.

## 18. Runbook for Deploying a Mapping Change to Production

### Phase A — Before Coding/Merging

1. Lock down expected CQL types/schemas, Java properties, and frozen/non-frozen choices.
2. Verify collections are bounded rather than modeling unbounded 1-to-many relationships.
3. Lock down stable enum codes, unknown-value handling, and backward compatibility.
4. Lock down temporal semantics: instants, local dates, local times, zone IDs, precision, and DST.
5. Write converters with bidirectional unit tests and raw-CQL integration tests.
6. Verify Spring Boot/Spring Data/Driver/Server compatibility; never rely on untested `latest`.
7. Commit CQL migrations to Git with IDs/checksums; never let the app auto-alter production schemas.

### Phase B — Staging

- Apply keyspace/UDT/table/column migrations in order and wait for schema agreement.
- Run collection/UDT, enum code, and temporal round-trips across multiple JVM timezones.
- Test old and new app versions running side by side in a rolling deploy.
- Simulate timeouts/retries on list appends and frozen UDT updates to catch non-idempotent paths.
- Read pre-migration records; verify null/unknown/new fields.
- Measure p95/p99, row/partition sizes, tombstones, GC/heap, compaction, and disk.

### Phase C — Rollout

- Deploy **readers supporting the new schema/codes first** before writers emit the new format.
- Enable writers via feature flag/canary where appropriate.
- Watch mapping/conversion exceptions, unknown codes, latency, and data correctness.
- For backfills, run partition-keyed jobs with checkpoints, bounded concurrency, and reconciliation.
- Avoid changing partition keys, RF, compaction strategies, and mappings simultaneously without dedicated plans.

### Phase D — Completion

- Verify all services, workers, and batch jobs support the new wire format.
- Diff live schema against Git migrations and cluster state.
- Verify old and new records read accurately with consistent converters and temporal policies.
- Document rollback criteria: **can the previous version still read newly written data?**
- Contract/drop legacy fields/formats only after full cutover and verified restorable backups.

## 19. Scenario Exercises

A Spring Boot service persists Cassandra profiles using the schema in this lesson, with `CustomerProfile` and UDT `PostalAddress`.

### Exercise 1 — Collections

A developer wants to store a customer's entire 2-million-order history in `List<UUID> orders` on each profile so an API can paginate chronologically.

1. Why is this unsuitable for Cassandra?
2. How would you redesign the table to query by customer ID and time?
3. Does setting a driver page size fix the problem if everything stays in one collection?
4. Why is retrying a list append after `WriteTimeout` risky?

**Hint:** use an `orders_by_customer` table with matching partition/clustering keys, possibly bucketed. Page size does not fix a huge collection; list appends can duplicate on retry.

### Exercise 2 — Frozen UDT

Two workers read the same frozen `shipping_address`. Worker A updates `city`, Worker B updates `postal_code`, and both save.

1. Why can one update be lost?
2. Is there a CQL syntax to update a single subfield of a **frozen UDT** like a non-frozen map?
3. If concurrent independent field updates are required, how should the model change?

**Hint:** frozen is a single value replacing the whole object; consider non-frozen UDTs if version/use case allows, separate columns, or CAS/versioning/concurrency policies.

### Exercise 3 — Enum Ordinals

A legacy table uses `status_code int`; the old enum was `ACTIVE, PAUSED, CLOSED`. A new release prepends `PENDING`.

1. How does the meaning of stored value `1` change?
2. Why might unit tests for the new converter still pass while historical data is misread?
3. Propose a migration sequence to stable text codes.

**Hint:** tests must include raw historical CQL data; expand readers, add a new column, backfill, then switch writers rather than editing only the Java enum.

### Exercise 4 — Temporal Types

CQL `timestamp` holds `2026-11-21T02:30:00.123Z`. Java displays this in `Asia/Ho_Chi_Minh`, and the user sets "remind me at 09:30 every day".

1. Why can't both requirements use the same `Instant`?
2. Which Java/CQL types fit the event occurrence time vs. the daily reminder time?
3. How much precision survives when an `Instant` with nanoseconds round-trips through CQL `timestamp`?
4. For timezones with DST, what extra business rule is needed?

**Hint:** the event occurrence uses `Instant`; the daily schedule uses `LocalTime + ZoneId` with rules for skipped or repeated hours. CQL `timestamp` has millisecond precision.

### Exercise 5 — Converter Not Running

`CustomerStatusWriteConverter` was written, yet raw CQL still shows `'ACTIVE'` instead of `'A'`.

1. Does the converter need explicit registration?
2. How do you prove `MappingCassandraConverter` actually uses it?
3. If code writes directly through `CqlSession`, do Spring converters run automatically?
4. What must integration tests check?

**Hint:** register via `CassandraCustomConversions` / context override; write/read through repository/Template and verify via raw CQL; lower-level `CqlSession` does not invoke Spring converters automatically.

### Exercise 6 — Backward-Compatible Migration

A team adds `country_code` to a frozen UDT and deploys the new Java writer ahead of older readers.

1. What failures can old readers hit?
2. What can old apps rewriting the frozen UDT do to the new field?
3. Propose a safe release order and rollback test.

**Hint:** expand readers before writers, wait for schema agreement, handle nullable legacy data, guard against frozen whole-value rewrites, and contract last.

## 20. Final Lesson Checklist

- [ ] Selected appropriate CQL `list/set/map` types and bounded collection sizes for the workload.
- [ ] Avoided collections for unbounded 1-to-many histories; modeled tables with partition/clustering keys instead.
- [ ] Entity `@Table`, `@PrimaryKey`, and `@Column` match DDL.
- [ ] UDTs have `@UserDefinedType` with consistent keyspace/type names.
- [ ] `@Frozen` matches CQL, especially for UDTs inside lists/maps/sets.
- [ ] Distinguished element-level CQL updates from whole-collection/UDT overwrites via repositories.
- [ ] Tested null, empty, tombstone, and concurrent write behavior with integration tests.
- [ ] Avoided new ordinal-mapped enums unless strictly justified by legacy constraints with a migration plan.
- [ ] Stable-code enums have read/write converters, an unknown-code policy, and tests for old/new codes.
- [ ] Converters are registered with the active `CassandraCustomConversions`/context.
- [ ] Distinguished global converters from per-property converters, avoiding accidental type-wide side effects.
- [ ] Did not confuse `@CassandraType` with business converters; Java and CQL types align.
- [ ] Used `Instant` for event `timestamp`s; never assumed `timestamp` preserves user timezones without another column.
- [ ] Accounted for Cassandra `timestamp` millisecond precision in round-trip equality checks.
- [ ] Used `LocalDate`/`LocalTime` for calendar `date`/`time` without arbitrary offsets.
- [ ] Stored IANA `ZoneId` when local time depends on timezone and defined DST transition rules.
- [ ] Did not assume CQL `duration` equals `java.time.Duration`.
- [ ] Verified Spring Boot/Spring Data/Java Driver/Cassandra Server/JDK version compatibility.
- [ ] Managed production schemas via Git migrations; never auto-recreate/drop on app startup.
- [ ] Passed converter unit tests and repository/Template/raw-CQL integration tests.
- [ ] Tested old/new apps running together during expand–migrate–contract.
- [ ] Measured performance/GC/tombstones and mapping errors under realistic load, not just compilation.

## 21. Official References

The following documents describe mapping, converters, and Spring Boot/Spring Data Cassandra configuration. Match the **exact version used by your project** rather than applying new-doc APIs to pinned legacy releases:

- [Spring Data Cassandra — Mapping](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html): `MappingCassandraConverter`, `@Table`, `@Column`, `@CassandraType`, `@UserDefinedType`, and `@Frozen`.
- [Spring Data Cassandra — Custom Conversions](https://docs.spring.io/spring-data/cassandra/reference/cassandra/converters.html): `@ReadingConverter`, `@WritingConverter`, and `CassandraCustomConversions` registration.
- [Spring Data Cassandra — Property-based Converters](https://docs.spring.io/spring-data/cassandra/reference/cassandra/property-converters.html): per-property conversion and `@ValueConverter` where version-supported.
- [Spring Data Cassandra — CassandraType Javadoc](https://docs.spring.io/spring-data/cassandra/reference/api/java/org/springframework/data/cassandra/core/mapping/CassandraType.html): `type`, `typeArguments`, and `userTypeName`.
- [Spring Boot — Working with NoSQL Technologies / Cassandra](https://docs.spring.io/spring-boot/reference/data/nosql.html): starter, `spring.cassandra.*`, `CqlSession`, and `CassandraTemplate`.

**Conclusion:** Mapping collections, UDTs, enums, temporal types, and custom converters in Spring Data Cassandra is **part of your distributed data contract**, not mere annotations to make Java compile. `List/Set/Map` must be bounded and updated with proper semantics; `frozen` UDTs require awareness of whole-value replacement and concurrent writes; enums need **stable codes** for long-lived data; temporal types must separate **Instant, LocalDate, LocalTime, and ZoneId**; and converters must be registered bidirectionally and verified with raw CQL. Only when the **CQL schema, Java mapping, migration workflow, and integration tests** align are repositories and services trustworthy in Cassandra production.
