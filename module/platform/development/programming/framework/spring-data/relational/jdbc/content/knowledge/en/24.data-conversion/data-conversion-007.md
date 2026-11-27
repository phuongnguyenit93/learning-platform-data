# Converting JSON, UUIDs, or Driver-Specific Types

In **Spring Data Relational JDBC**, entity data is mapped to values that the JDBC driver can write and read. Common types such as strings, numbers, booleans, and dates/times generally already have default conversions. However, real-world applications also encounter JSON/JSONB, UUIDs, database-specific enums, or objects provided by the JDBC driver.

To handle these types, Spring Data JDBC uses **custom conversions**. A reading converter translates a JDBC value into a Java domain type; a writing converter translates a Java type into a value the JDBC driver can bind into a SQL statement. With some drivers, converting to String or byte[] alone is not enough: you must specify a JDBC type or construct the exact driver-specific object.

This lesson uses PostgreSQL as the primary example because its driver provides PGobject to represent types such as jsonb and custom enums. The principles apply to other databases as well, though Java/driver wrappers and JDBC types should be adapted to the actual driver.

## 1. Conversion Flow in Spring Data JDBC

When writing an aggregate, Spring Data JDBC reads the entity's mapping metadata, converts each property into a JDBC value, and binds it to the statement. When reading, it receives values from the ResultSet, converts them back to Java property types, and constructs the object.

```text
Writing data
Domain object
    │
    ▼
Mapping metadata
    │
    ▼
Writing converter
    │
    ▼
JDBC value / driver-specific object
    │
    ▼
PreparedStatement ─────► Database

Reading data
Database ─────► ResultSet
                  │
                  ▼
             JDBC value / driver object
                  │
                  ▼
             Reading converter
                  │
                  ▼
             Domain object
```

For example, a Java property of type EventPayload can be stored in a PostgreSQL jsonb column. Spring Data JDBC needs to know:

- When writing, how to serialize EventPayload into JSON and pass it to the driver as a JSONB value.
- When reading, how to extract the JSON content from the object returned by the driver and deserialize it into EventPayload.

Custom converters handle type conversion. They do not create columns, add constraints, or alter schemas. The database schema must still be managed via migrations/DDL.

## 2. Reading Converters and Writing Converters

Spring Data uses two annotations to specify the conversion direction:

| Annotation | Direction | Example |
| --- | --- | --- |
| `@WritingConverter` | Java domain type → JDBC/driver type | EventPayload → PGobject |
| `@ReadingConverter` | JDBC/driver type → Java domain type | PGobject → EventPayload |

Explicitly declaring the direction is especially important when both types are simple, such as String and UUID. Without the annotation, Spring may struggle to determine whether the converter is for reading or writing.

General example:

```java
@WritingConverter
public class DomainValueWritingConverter
        implements Converter<DomainValue, String> {

    @Override
    public String convert(DomainValue source) {
        return source.value();
    }
}

@ReadingConverter
public class DomainValueReadingConverter
        implements Converter<String, DomainValue> {

    @Override
    public DomainValue convert(String source) {
        return new DomainValue(source);
    }
}
```

Spring Core's Converter<S, T> describes converting from S to T. Converters should focus on data conversion; business validation, authorization, and transaction logic belong in the domain/service layer.

## 3. Registering Custom Conversions with Spring Data JDBC

A standard approach is extending AbstractJdbcConfiguration and overriding userConverters():

```java
import java.util.List;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;

@Configuration
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    private final ObjectMapper objectMapper;

    public JdbcConfiguration(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    protected List<?> userConverters() {
        return List.of(
                new EventPayloadWritingConverter(objectMapper),
                new EventPayloadReadingConverter(objectMapper)
        );
    }
}
```

Spring Data JDBC uses these converters to build JdbcCustomConversions and integrate with the mapping converter. In a Spring Boot application, ObjectMapper is typically pre-configured when Jackson is on the classpath; if a project configures the JDBC infrastructure manually, ensure there is only one consistent mapping/conversion configuration.

If the project already has a class extending AbstractJdbcConfiguration, add the converters to the existing userConverters(). Avoid creating multiple competing configurations defining mapping contexts/conversions. You also do not need to create a custom repository implementation solely to register converters.

## 4. Converting JSON/JSONB with PostgreSQL

PostgreSQL has two common JSON column types:

- json: stores JSON text and preserves the input representation.
- jsonb: stores parsed binary data, supporting JSONB operators and indexing more efficiently across many queries.

JDBC does not define a single universal standard Java type for JSON. The PostgreSQL JDBC driver provides org.postgresql.util.PGobject to represent PostgreSQL-specific data types. For a jsonb column, you can create a PGobject with type jsonb and value set to the JSON string.

### 4.1. Domain Type and Schema

A domain data type:

```java
import java.util.Map;

public record EventPayload(
        String eventType,
        Map<String, Object> attributes
) {}
```

Entity:

```java
import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("event_record")
public record EventRecord(
        @Id Long id,
        UUID correlationId,
        EventPayload payload
) {}
```

PostgreSQL DDL:

```sql
CREATE TABLE event_record (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    correlation_id UUID NOT NULL,
    payload JSONB NOT NULL
);
```

EventPayload is an application-specific Java type; payload is a JSONB column. correlation_id uses PostgreSQL's native UUID type.

### 4.2. JSONB Writing Converter

The converter serializes the domain object into JSON and wraps it in a PGobject:

```java
import java.sql.JDBCType;
import java.sql.SQLException;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.postgresql.util.PGobject;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;
import org.springframework.data.jdbc.core.mapping.JdbcValue;

@WritingConverter
public class EventPayloadWritingConverter
        implements Converter<EventPayload, JdbcValue> {

    private final ObjectMapper objectMapper;

    public EventPayloadWritingConverter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public JdbcValue convert(EventPayload source) {
        try {
            PGobject json = new PGobject();
            json.setType("jsonb");
            json.setValue(objectMapper.writeValueAsString(source));

            return JdbcValue.of(json, JDBCType.OTHER);
        } catch (JsonProcessingException | SQLException ex) {
            throw new IllegalArgumentException(
                    "Cannot serialize EventPayload as PostgreSQL jsonb",
                    ex
            );
        }
    }
}
```

The converter uses two parts:

- PGobject sets the PostgreSQL type to jsonb and holds the serialized JSON string.
- JdbcValue.of(value, JDBCType.OTHER) provides both the value and JDBC type so Spring binds the proper parameter type. OTHER is commonly used for database-specific types; verify with your actual driver/dialect if the driver expects a different binding approach.

PGobject.setValue can throw SQLException; Jackson can throw serialization errors. The example wraps errors into an unchecked exception so the write fails explicitly. Never silently return empty JSON or null when serialization fails, as that can cause data loss.

### 4.3. JSONB Reading Converter

The PostgreSQL JDBC driver normally returns a PGobject when reading a JSON/JSONB column via getObject. The reading converter extracts the content and deserializes it:

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.postgresql.util.PGobject;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class EventPayloadReadingConverter
        implements Converter<PGobject, EventPayload> {

    private final ObjectMapper objectMapper;

    public EventPayloadReadingConverter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public EventPayload convert(PGobject source) {
        String json = source.getValue();
        if (json == null) {
            return null;
        }

        try {
            return objectMapper.readValue(json, EventPayload.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                    "Cannot deserialize PostgreSQL jsonb as EventPayload",
                    ex
            );
        }
    }
}
```

Reading and writing converters must be registered together so mapping works in both directions. If database data is invalid JSON or no longer matches the current domain schema, deserialization failures should surface clearly so the team can address migration/compatibility.

### 4.4. Saving and Reading via Repository

Repository:

```java
import org.springframework.data.repository.CrudRepository;

public interface EventRecordRepository
        extends CrudRepository<EventRecord, Long> {
}
```

Writing:

```java
EventPayload payload = new EventPayload(
        "ORDER_CONFIRMED",
        Map.of("source", "checkout", "priority", 2)
);

EventRecord event = new EventRecord(
        null,
        UUID.randomUUID(),
        payload
);

EventRecord saved = repository.save(event);
```

Reading:

```java
EventRecord loaded = repository.findById(saved.id())
        .orElseThrow();

String eventType = loaded.payload().eventType();
```

The repository continues to work with entities and aggregates as usual. Converters handle the EventPayload ↔ PGobject translation; services do not need to serialize JSON manually on every repository call.

### 4.5. Querying JSONB Attributes

PostgreSQL provides operators for querying JSONB. Example:

```sql
SELECT id, correlation_id, payload
FROM event_record
WHERE payload ->> 'eventType' = 'ORDER_CONFIRMED';
```

Or querying nested attributes:

```sql
SELECT id
FROM event_record
WHERE payload -> 'attributes' ->> 'source' = 'checkout';
```

When using Spring Data JDBC @Query, the SQL must follow PostgreSQL syntax and the result mapping must return columns compatible with the entity/DTO. A converter only translates the JSONB column type; it does not generate JSON predicates or turn JSON attributes into query method properties.

If a JSON attribute is frequently filtered or sorted on, consider an expression index or a dedicated relational column. Do not shove all structured relational data into JSON merely to avoid declaring entities.

## 5. UUID: Native Type or String Representation?

UUIDs can be stored in several ways:

| Database Representation | Example Column Type | Java Representation |
| --- | --- | --- |
| Native UUID | PostgreSQL UUID | java.util.UUID |
| Hyphenated string | CHAR(36) or VARCHAR(36) | UUID ↔ String |
| 16 binary bytes | BINARY(16) or matching binary type | UUID ↔ byte[] |

### 5.1. PostgreSQL Native UUID

PostgreSQL has a uuid type, and the PostgreSQL JDBC driver supports converting between this type and java.util.UUID. With a compatible driver, custom converters are typically unnecessary:

```sql
CREATE TABLE api_request (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE
);
```

Entity:

```java
@Table("api_request")
public record ApiRequest(
        @Id Long id,
        UUID requestId
) {}
```

Prefer the native UUID type if the database supports it and the application has no special compatibility constraints. This avoids defining custom string formats or byte ordering.

### 5.2. UUID Stored as VARCHAR(36)

If an existing schema stores UUIDs as strings, you can use converters:

```java
import java.util.UUID;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class UuidWritingConverter
        implements Converter<UUID, String> {

    @Override
    public String convert(UUID source) {
        return source.toString();
    }
}
```

Reading converter:

```java
import java.util.UUID;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class UuidReadingConverter
        implements Converter<String, UUID> {

    @Override
    public UUID convert(String source) {
        return UUID.fromString(source);
    }
}
```

Schema:

```sql
CREATE TABLE api_request (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    request_id VARCHAR(36) NOT NULL UNIQUE
);
```

Register both converters in userConverters(). Do not register this string converter if another property uses native UUID and the driver already supports it properly. A global UUID ↔ String converter affects every mapped UUID property, so only use it when the application's schema uniformly stores UUIDs as strings.

If you only need to apply it to one property or a specific UUID kind, create a domain wrapper such as ExternalRequestId and write converters for that wrapper. This avoids changing the mapping of every UUID in the application.

### 5.3. UUID Stored as BINARY(16)

Some schemas store UUIDs as 16 bytes to save space compared to 36-character strings. In that case, you must agree on how the two 64-bit parts of a UUID are converted to bytes:

```java
import java.nio.ByteBuffer;
import java.util.UUID;

public final class UuidBytes {

    private UuidBytes() {
    }

    public static byte[] toBytes(UUID uuid) {
        return ByteBuffer.allocate(16)
                .putLong(uuid.getMostSignificantBits())
                .putLong(uuid.getLeastSignificantBits())
                .array();
    }

    public static UUID fromBytes(byte[] bytes) {
        if (bytes.length != 16) {
            throw new IllegalArgumentException(
                    "A UUID must contain exactly 16 bytes");
        }

        ByteBuffer buffer = ByteBuffer.wrap(bytes);
        return new UUID(buffer.getLong(), buffer.getLong());
    }
}
```

You can wrap these helpers in @WritingConverter and @ReadingConverter. If forcing the JDBC type on write is necessary:

```java
import java.sql.JDBCType;
import java.util.UUID;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;
import org.springframework.data.jdbc.core.mapping.JdbcValue;

@WritingConverter
public class UuidBinaryWritingConverter
        implements Converter<UUID, JdbcValue> {

    @Override
    public JdbcValue convert(UUID source) {
        return JdbcValue.of(
                UuidBytes.toBytes(source),
                JDBCType.BINARY
        );
    }
}
```

Reading can use a byte[] → UUID converter:

```java
import java.util.UUID;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class UuidBinaryReadingConverter
        implements Converter<byte[], UUID> {

    @Override
    public UUID convert(byte[] source) {
        return UuidBytes.fromBytes(source);
    }
}
```

Byte ordering must be consistent across all applications writing/reading the same column. Some legacy systems use a different byte order or swap byte groups; you cannot inspect a 16-byte column and simply assume it uses the ByteBuffer convention above. Before converting schemas, verify actual data with known UUIDs.

## 6. PostgreSQL Custom Enum Types

PostgreSQL allows defining enum types in the schema:

```sql
CREATE TYPE order_state AS ENUM (
    'DRAFT',
    'CONFIRMED',
    'CANCELLED'
);

CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    state order_state NOT NULL
);
```

In Java:

```java
public enum OrderState {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
```

The PostgreSQL JDBC driver can represent database enums via PGobject. Writing converter:

```java
import java.sql.JDBCType;
import java.sql.SQLException;

import org.postgresql.util.PGobject;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;
import org.springframework.data.jdbc.core.mapping.JdbcValue;

@WritingConverter
public class OrderStateWritingConverter
        implements Converter<OrderState, JdbcValue> {

    @Override
    public JdbcValue convert(OrderState source) {
        try {
            PGobject value = new PGobject();
            value.setType("order_state");
            value.setValue(source.name());
            return JdbcValue.of(value, JDBCType.OTHER);
        } catch (SQLException ex) {
            throw new IllegalArgumentException(
                    "Cannot convert OrderState to PostgreSQL enum",
                    ex
            );
        }
    }
}
```

Reading converter:

```java
import org.postgresql.util.PGobject;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class OrderStateReadingConverter
        implements Converter<PGobject, OrderState> {

    @Override
    public OrderState convert(PGobject source) {
        return OrderState.valueOf(source.getValue());
    }
}
```

The type name order_state must match the enum type in the schema. If the database enum is renamed or literals change, converters and stored data must be updated synchronously through migrations. For simple enums stored as VARCHAR, an Enum ↔ String converter is often simpler and avoids PGobject.

## 7. JdbcValue: Specifying the JDBC Type When the Driver Needs It

Sometimes a converter produces the right Java value, yet the driver still needs an explicit JDBC type for binding. Spring Data JDBC provides JdbcValue to carry both the value and java.sql.JDBCType:

```java
import java.sql.JDBCType;
import org.springframework.data.jdbc.core.mapping.JdbcValue;

JdbcValue value = JdbcValue.of(
        "550e8400-e29b-41d4-a716-446655440000",
        JDBCType.VARCHAR
);
```

Example UUID → JdbcValue converter:

```java
import java.sql.JDBCType;
import java.util.UUID;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;
import org.springframework.data.jdbc.core.mapping.JdbcValue;

@WritingConverter
public class UuidAsVarcharConverter
        implements Converter<UUID, JdbcValue> {

    @Override
    public JdbcValue convert(UUID source) {
        return JdbcValue.of(source.toString(), JDBCType.VARCHAR);
    }
}
```

Distinguish:

- **Java target type** indicates which object the converter returns.
- **JDBC type** indicates which JDBC parameter type to use when binding.
- **Driver-specific object** such as PGobject can carry additional database-specific type information.

JdbcValue does not magically turn a string into JSONB or a byte array into a native UUID. The inner value must still be compatible with the driver and column type. Use the JDBC type matching the schema, such as VARCHAR, BINARY, or OTHER; do not pick OTHER for every property out of habit.

## 8. Driver-Specific Types in Other Databases

Each JDBC driver may have its own wrappers for database types outside standard JDBC:

| Database/Driver | Potential Specialized Types | Approach |
| --- | --- | --- |
| PostgreSQL | PGobject for JSON/JSONB and certain custom types | Read/write converters with PGobject, optionally combined with JdbcValue |
| PostgreSQL | Native UUID | Prefer java.util.UUID if supported by driver/version |
| MySQL | BINARY(16) UUID or JSON | Choose byte[]/String or driver-appropriate wrappers |
| SQL Server | uniqueidentifier | Verify the Java driver's corresponding UUID mapping |
| Oracle | RAW(16), STRUCT, object types | Use appropriate JDBC/Oracle driver types and converters or custom DAOs |

Do not leak driver-specific classes such as PGobject into the domain model. The domain should represent data with business meaning (EventPayload, UUID, OrderState); adapters/converters handle communicating with the driver. This keeps the domain less coupled to PostgreSQL or a specific driver.

For types such as SQL ARRAY, STRUCT, or object types requiring a Connection to construct, a plain converter is not always sufficient. You may need JdbcTemplate, ConnectionCallback, a custom DAO, or a specialized mapping mechanism with access to the JDBC connection. Never fabricate fake java.sql.Array instances or retain connection-bound JDBC objects beyond the connection lifecycle.

## 9. Testing Converters and Round-Trip Persistence

A converter may be correct when invoked directly yet still bind the wrong JDBC type or prove incompatible with the schema/driver. Test at both levels:

### 9.1. Unit Testing the Converter

Example verifying JSON serialization/deserialization:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.postgresql.util.PGobject;
import org.springframework.data.jdbc.core.mapping.JdbcValue;

class EventPayloadConverterTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void convertsPayloadToJsonbAndBack() throws Exception {
        EventPayload original = new EventPayload(
                "ORDER_CONFIRMED",
                Map.of("source", "checkout")
        );

        EventPayloadWritingConverter writer =
                new EventPayloadWritingConverter(mapper);
        EventPayloadReadingConverter reader =
                new EventPayloadReadingConverter(mapper);

        JdbcValue jdbcValue = writer.convert(original);
        PGobject json = (PGobject) jdbcValue.getValue();

        assertThat(json.getType()).isEqualTo("jsonb");
        assertThat(reader.convert(json)).isEqualTo(original);
    }
}
```

This test demonstrates round-trip behavior across both converters without hitting a real database. Depending on your JdbcValue version, use the matching accessor to retrieve the wrapped value.

### 9.2. Integration Testing Against the Target Database

For PostgreSQL native JSONB/UUID, run integration tests against PostgreSQL with the application's actual driver and migrations. Tests can:

1. Create an EventRecord with payload and UUID.
2. Call repository save.
3. Read back via findById.
4. Compare the UUID and payload fields.
5. Run a JSONB query to confirm the actual column type.
6. Test invalid JSON or a removed enum literal to confirm errors surface cleanly.

H2 or other databases do not fully emulate PostgreSQL's PGobject, JSONB operators, enum types, and JDBC type OTHER. Testing with an alternative database is helpful for general logic, but does not replace integration tests against the real driver when using specialized types.

### 9.3. Inspecting the Schema with SQL

PostgreSQL:

```sql
SELECT
    id,
    correlation_id,
    payload,
    pg_typeof(payload) AS payload_type
FROM event_record
ORDER BY id DESC;
```

The pg_typeof(payload) output confirms the column is jsonb as expected. For UUID:

```sql
SELECT
    request_id,
    pg_typeof(request_id) AS request_id_type
FROM api_request;
```

Verify both DDL and data; a string shaped like a UUID does not mean the column uses the native UUID type.

## 10. Schema Management and Data Compatibility

Custom converters are part of the contract between the Java model and database schema. When changing data representations, coordinate migrations:

- Migrating UUID from VARCHAR(36) to native UUID requires migrating data and updating the corresponding converters.
- Changing JSON schemas requires maintaining backward compatibility with old data or writing transformation migrations.
- Renaming PostgreSQL enums/types or literals requires updating converters and stored rows.
- Switching json to jsonb may require reviewing indexes, constraints, operators, and how the application queries them.
- Moving UUID from string to BINARY(16) requires consistent byte ordering across all writing/reading applications.

Never change converters in code while ignoring existing data. If a new converter cannot read old data, the application may fail as soon as it loads an aggregate.

## 11. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Can't convert ... or converter not found | Converter not registered or direction unclear | Register in userConverters() and mark reading/writing |
| PostgreSQL rejects JSON bind | Driver receives String as VARCHAR instead of JSONB | Use PGobject with type jsonb, optionally combined with JdbcValue and JDBCType.OTHER |
| Reading JSONB returns PGobject but property still fails | Missing PGobject → domain type converter | Register reading converter |
| JSON written as doubly-quoted string | Serialized JSON twice or bound string with wrong type | Serialize once and bind as JSONB |
| UUID fails to map | Driver/schema uses a different representation than the Java type | Check column type and driver; add matching converter |
| Binary UUID reads back a different value | Inconsistent byte ordering | Verify the 16-byte convention across all systems |
| PostgreSQL enum reports type mismatch | PGobject.setType() mismatches schema enum name or wrong JDBC type | Check type name, literals, and JDBCType.OTHER |
| Converter is not used | Wrong configuration registration or multiple mapping configurations | Inspect AbstractJdbcConfiguration and runtime wiring |
| H2 tests pass while PostgreSQL fails | H2 lacks corresponding type/driver behavior | Integration test on real PostgreSQL |
| Old data fails to deserialize | Domain JSON or enum changed without migration | Preserve compatibility or migrate data |

When debugging, check in order: Java property type, converter source/target, converter direction, list of registered converters, JDBC type, driver version, actual column type, and root exception. Never change String to Object just to hide a mapping error.

## 12. Converter Design Principles

1. **Keep the domain independent of the driver.** The domain uses UUID, Java records/value objects, and Java enums; only converters know about PGobject or vendor wrappers.
2. **Define both directions.** When both writing and reading are needed, implement matching writing and reading converters.
3. **Mark direction clearly.** Use @WritingConverter and @ReadingConverter whenever ambiguity is possible.
4. **Specify JDBC type when needed.** Use JdbcValue when the driver requires an explicit bind type.
5. **Never swallow data errors.** Malformed JSON or invalid enums must produce clear, traceable errors.
6. **Keep converters single-purpose.** Do not query repositories or call services from a converter.
7. **Migrate alongside converters.** Representation changes must include a plan for existing data.
8. **Test with the real driver.** Especially for JSONB, enums, binary UUIDs, and vendor-specific types.
9. **Use JSON only for appropriate data.** Fields requiring joins, constraints, or frequent filtering likely belong in separate relational columns.

## 13. Practice Exercises

**Exercise 1 — JSONB Round-Trip.** Create EventPayload, two converters using PGobject, register via userConverters(), and save/load EventRecord on PostgreSQL. Compare the object before and after reading.

**Exercise 2 — JSON Query.** Write a PostgreSQL query filtering on payload ->> 'eventType'. Verify the payload reading converter still works when the query returns entities.

**Exercise 3 — Native UUID.** Store java.util.UUID in a PostgreSQL UUID column. Confirm direct driver support and check pg_typeof.

**Exercise 4 — String UUID.** Create a schema using VARCHAR(36), register reading/writing converters, and test round-trip values.

**Exercise 5 — Binary UUID.** Convert a UUID to 16 bytes using a defined convention. Write/read BINARY(16) and verify the exact same UUID is restored accurately.

**Exercise 6 — PostgreSQL Enum.** Create an order_state type, write OrderState ↔ PGobject converters, then attempt to write a non-existent literal to observe the constraint/type error.

**Exercise 7 — Migration Test.** Change the JSON schema or UUID representation. Write a data migration and test reading data created both before and after the migration.

### References

- [Spring Data Relational — Custom Conversions](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html#jdbc.custom-conversions): registering reading/writing converters and JDBC-specific values.
- [Spring Data JDBC — AbstractJdbcConfiguration API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/config/AbstractJdbcConfiguration.html): the userConverters() extension point and JDBC infrastructure.
- [PostgreSQL JDBC — Advanced Data Types](https://jdbc.postgresql.org/documentation/server-prepare/): how PostgreSQL JDBC handles driver-specific data types and objects.
- [PostgreSQL — JSON Types](https://www.postgresql.org/docs/current/datatype-json.html): differences between json and jsonb, operators, and storage.
- [PostgreSQL — UUID Type](https://www.postgresql.org/docs/current/datatype-uuid.html): native UUID data type.
