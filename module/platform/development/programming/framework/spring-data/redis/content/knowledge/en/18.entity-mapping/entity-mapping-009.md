# MappingRedisConverter and RedisCustomConversions in Spring Data Redis

When using Spring Data Redis Repositories, developers work with Java entities instead of writing individual `HSET` or `HGETALL` commands or converting data to bytes manually. To make that possible, Spring Data Redis needs a mechanism to **map Java objects to Redis Hashes** and reconstruct objects from Hashes. `MappingRedisConverter` is the component that performs this work; `RedisCustomConversions` lets you customize how specific data types are converted.

The two components answer two different questions:

- **`MappingRedisConverter`:** Which fields and values in a Redis Hash represent an entity's properties, nested objects, and metadata? When reading the Hash, how is the entity reconstructed?
- **`RedisCustomConversions`:** If default mapping rules do not fit a value type like `Address`, `Money`, or an object with a custom binary format, which converters should be registered for writing and reading?

This lesson focuses on the **entity mapping** context with Redis Repositories. This differs from using `RedisTemplate.opsForValue()` directly with a serializer to store an entire object as a single Redis String value.

## 1. Redis Hash and Default Entity Mapping

Redis stores data using structures such as String, Hash, List, and Set. With Redis Repositories, an entity is typically stored as **one Redis Hash** with a key composed of the keyspace and id:

```text
Java Entity
    |
    v
Redis Repository / RedisKeyValueTemplate
    |
    v
MappingRedisConverter
    |
    v
RedisData: metadata + byte[] fields/values
    |
    v
RedisKeyValueAdapter
    |
    v
Redis Hash, e.g. customer-profiles:42
```

Entity example used in this lesson:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("customer-profiles")
public class CustomerProfile {

    @Id
    private String id;
    private String displayName;
    private Address address;

    protected CustomerProfile() {
        // For entity instantiation when reading data.
    }

    public CustomerProfile(String id, String displayName, Address address) {
        this.id = id;
        this.displayName = displayName;
        this.address = address;
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public Address getAddress() {
        return address;
    }
}
```

The nested value object can be declared as a Java record:

```java
public record Address(String city, String country) {
}
```

Suppose we save a profile:

```java
CustomerProfile customer = new CustomerProfile(
        "42",
        "Minh Anh",
        new Address("Da Nang", "Viet Nam")
);

customerRepository.save(customer);
```

With default rules, a human-readable view of the Redis data might look like this (actual values are sent as bytes):

```text
Redis key: customer-profiles:42
Redis type: hash

_class          = com.example.CustomerProfile
id              = 42
displayName     = Minh Anh
address.city    = Da Nang
address.country = Viet Nam
```

`@RedisHash("customer-profiles")` sets the **keyspace**; `@Id` designates the identifier. When using a repository, the Redis key name is typically `<keyspace>:<id>`. The `_class` field holds type information helping Spring Data recognize the object type, especially when mapping polymorphic types. This is mapping metadata, not a business field.

### Common Flattening Rules

`MappingRedisConverter` represents nested structures using property paths. For example:

| Java Property Type | Example | Field in Redis Hash |
|---|---|---|
| `String` | `name = "Mai"` | `name` |
| `int` | `age = 28` | `age` |
| Nested object | `address.city = "Hue"` | `address.city` |
| `List<String>` | `tags = ["vip", "new"]` | `tags.[0]`, `tags.[1]` |
| `Map<String, String>` | `flags["email"] = "ok"` | `flags.[email]` |
| List of objects | `addresses[0].city` | `addresses.[0].city` |

Field names and storage formats can differ when custom converters are registered. Map keys must be stably representable as path names; simple types like `String` or numbers are the usual choice. Complex nested cases need care because a Redis Hash is a flat structure, not a JSON document.

**Important operational note:** when re-saving an entity via a Redis Repository, Spring Data Redis may delete the old Hash content and recreate it from mapped properties. Fields you added manually to the same Hash outside the mapping model risk being lost on the next save. Do not treat a repository-managed Hash as a free-form store where multiple components arbitrarily write private fields.

## 2. What Does MappingRedisConverter Do?

`MappingRedisConverter` resides in the package:

```text
org.springframework.data.redis.core.convert.MappingRedisConverter
```

It is the default implementation of the `RedisConverter` interface. It relies on the following key components:

| Component | Role |
|---|---|
| `RedisMappingContext` | Describes entities, properties, ids, annotations, and mapping metadata |
| `MappingRedisConverter` | Converts entities into `RedisData` and back |
| `RedisData` | Intermediate data container holding keyspace/id/field-values and auxiliary info |
| `ConversionService` | Infrastructure for converting simple value types and registered converters |
| `RedisCustomConversions` | List of custom converters and read/write direction selection rules |
| `RedisTypeMapper` | Manages Java type metadata on write/read (e.g., the `_class` field) |
| `RedisKeyValueAdapter` | Interacts with Redis using actual commands and key/value structures |

Write flow:

```text
CustomerProfile
    |
    | 1. Read metadata from RedisMappingContext
    | 2. Determine id and keyspace
    | 3. Traverse properties
    | 4. Apply custom writing converter if present
    v
RedisData (byte[] hash fields/values)
    |
    v
RedisKeyValueAdapter --> writes Hash to Redis
```

Read flow:

```text
Redis Hash
    |
    v
RedisKeyValueAdapter --> RedisData
    |
    | 1. Determine entity type and metadata
    | 2. Read properties/fields by path
    | 3. Apply custom reading converter if present
    | 4. Instantiate entity and populate data
    v
CustomerProfile
```

At the API level, `MappingRedisConverter` has typical methods:

```java
void write(Object source, RedisData sink);
<R> R read(Class<R> type, RedisData source);
void setCustomConversions(CustomConversions conversions);
```

These signatures illustrate the API's intent. Normally the application calls `CrudRepository.save(...)` and `findById(...)`; the repository infrastructure invokes the converter underneath. There is no need to construct `RedisData` or call `write/read` manually in business logic.

## 3. What Limitation Does RedisCustomConversions Solve?

By default, `Address` is a composite object so its properties are split into `address.city` and `address.country`. Sometimes, however, the system wants to store it as **a single field**:

```text
Default:
address.city    = Da Nang
address.country = Viet Nam

With custom converter Address -> byte[]:
address = {"city":"Da Nang","country":"Viet Nam"}
```

In this case two conversion directions are needed:

- `@WritingConverter` + `Converter<Address, byte[]>`: converts `Address` into binary data for writing.
- `@ReadingConverter` + `Converter<byte[], Address>`: reads the field's bytes and reconstructs `Address`.

Both directions must agree on the format. If only the writing converter is declared, data saves successfully, yet reconstructing `Address` will not work as intended. If only the reading converter is declared, written data still follows the default structure, which differs from the format the reading converter expects.

`RedisCustomConversions` resides in the package:

```text
org.springframework.data.redis.core.convert.RedisCustomConversions
```

It is the configuration object holding the set of converters registered for Redis mapping. It can be instantiated with a list:

```java
new RedisCustomConversions(List.of(
    new AddressToBytesConverter(mapper),
    new BytesToAddressConverter(mapper)
));
```

It does not write data directly to Redis. Once wired into `MappingRedisConverter`, its rules are consulted as the converter processes each property.

### Why Are @WritingConverter and @ReadingConverter Needed?

Spring's Conversion Service can infer many conversions from the generic `Converter<S, T>`. However, general source/target types like `String`, `byte[]`, or `Map` can be used in multiple directions and contexts. `@WritingConverter` / `@ReadingConverter` explicitly state intent and prevent registering a conversion in an unintended direction.

They come from:

```java
import org.springframework.data.convert.WritingConverter;
import org.springframework.data.convert.ReadingConverter;
```

## 4. Full Example: Saving Address as a Binary JSON Field

The example below uses `Address` and `CustomerProfile` from the first section. Add the Spring Data Redis and Jackson libraries (versions managed by Spring Boot's BOM):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'com.fasterxml.jackson.core:jackson-databind'
}
```

### 4.1. Writing Converter

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class AddressToBytesConverter implements Converter<Address, byte[]> {

    private final ObjectMapper mapper;

    public AddressToBytesConverter(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public byte[] convert(Address source) {
        try {
            return mapper.writeValueAsBytes(source);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException("Cannot serialize Address", ex);
        }
    }
}
```

This converter only knows how to turn an `Address` into `byte[]`. It does not know what the Redis key name will be and does not call `HSET`. Placing the resulting value into the `address` field is the mapping mechanism's responsibility.

### 4.2. Reading Converter

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public final class BytesToAddressConverter implements Converter<byte[], Address> {

    private final ObjectMapper mapper;

    public BytesToAddressConverter(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public Address convert(byte[] source) {
        try {
            return mapper.readValue(source, Address.class);
        } catch (IOException ex) {
            throw new IllegalArgumentException("Cannot deserialize Address", ex);
        }
    }
}
```

When Redis returns bytes for the `address` field, the reading converter uses the exact JSON format produced by the writing converter. For the Java record `Address(String city, String country)`, Jackson in an appropriate environment can construct the record via its component constructor. If using other kinds of value objects, verify that instantiation is supported by your conversion library.

### 4.3. Registering RedisCustomConversions

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.convert.RedisCustomConversions;

@Configuration
public class RedisMappingConfiguration {

    @Bean("redisCustomConversions")
    public RedisCustomConversions redisCustomConversions(ObjectMapper mapper) {
        return new RedisCustomConversions(List.of(
                new AddressToBytesConverter(mapper),
                new BytesToAddressConverter(mapper)
        ));
    }
}
```

The example assumes the application already provides an `ObjectMapper` bean (e.g., via Spring Boot's JSON auto-configuration). If not, declare an `ObjectMapper` compatible with your data and Jackson version. You do not necessarily have to manually instantiate a new `MappingRedisConverter`: in standard Redis Repository configuration, the infrastructure picks up the `redisCustomConversions` bean to configure the repository's converter.

This configuration applies to **Redis Repository object-to-hash mapping**. It does not automatically change the serializer of a `RedisTemplate` used directly with `opsForValue()`.

### 4.4. Repository and Read/Write Operations

```java
import org.springframework.data.repository.CrudRepository;

public interface CustomerProfileRepository
        extends CrudRepository<CustomerProfile, String> {
}
```

Usage example in a service:

```java
import org.springframework.stereotype.Service;

@Service
public class CustomerProfileService {

    private final CustomerProfileRepository repository;

    public CustomerProfileService(CustomerProfileRepository repository) {
        this.repository = repository;
    }

    public CustomerProfile createExample() {
        CustomerProfile profile = new CustomerProfile(
                "42",
                "Minh Anh",
                new Address("Da Nang", "Viet Nam")
        );
        return repository.save(profile);
    }

    public CustomerProfile find(String id) {
        return repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Customer profile not found: " + id
                ));
    }
}
```

After saving, the Redis Hash looks conceptually like:

```text
Key: customer-profiles:42

_class       = com.example.CustomerProfile
id           = 42
displayName  = Minh Anh
address      = {"city":"Da Nang","country":"Viet Nam"}
```

There are no longer two fields `address.city` and `address.country` in the new representation because a custom converter replaced how `Address` is written. Even though the JSON example looks readable in Redis CLI, Redis still stores Hash values as byte sequences; another converter could produce binary data that is not human-readable text.

To inspect the data directly:

```redis
TYPE customer-profiles:42
# hash

HGETALL customer-profiles:42
# Field/value pairs of the saved entity

HGET customer-profiles:42 address
# {"city":"Da Nang","country":"Viet Nam"}
```

When calling `repository.findById("42")`, Redis Repository reads the Hash, the converter recognizes that the `address` field needs to be converted into `Address`, and then reconstructs `CustomerProfile`.

## 5. How Do Converters to `byte[]` and Converters to `Map<String, byte[]>` Differ?

Spring Data Redis supports two common custom mapping approaches:

| Conversion Type | Level of Control | Use Case |
|---|---|---|
| `Converter<ValueObject, byte[]>` | Stores a complex value as bytes in a single Hash field | JSON for an Address, binary encoding of Money, encrypted data |
| `Converter<byte[], ValueObject>` | Reconstructs a value object from a binary field | Reading data written by the corresponding converter |
| `Converter<EntityOrValue, Map<String, byte[]>>` | Explicitly produces a set of Hash fields/values | Specialized field formats, legacy schemas, custom flattening rules |
| `Converter<Map<String, byte[]>, EntityOrValue>` | Reconstructs an object from a field/value map | Reading a completely customized Hash format |

Example illustrating how to manually build fields for an `Address`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class AddressToMapConverter
        implements Converter<Address, Map<String, byte[]>> {

    @Override
    public Map<String, byte[]> convert(Address source) {
        return Map.of(
                "city_name", source.city().getBytes(StandardCharsets.UTF_8),
                "country_code", source.country().getBytes(StandardCharsets.UTF_8)
        );
    }
}
```

With a Map converter, the field names you provide become part of the storage schema; coordinate them consistently with the reading converter. The snippet above only illustrates the **writing direction**, so it does not replace the full converter pair in Section 4. Notably, custom Map converters have broader reach and carry risks of colliding field names or diverging from default mapping layouts; use them only when you genuinely need control over the Hash structure.

**Note on indexes:** custom conversions do not automatically alter how Spring Data Redis resolves secondary indexes. If an entity uses `@Indexed`, the index resolver still relies on metadata and its own rules. Do not assume a new Hash field written by a Map converter automatically becomes a secondary index queryable via the repository.

## 6. Distinguishing Mapping Converter, Serializer, and Type Mapper

These three concepts are often confused because all relate to data conversion:

| Concept | Scope | Example |
|---|---|---|
| `MappingRedisConverter` | Java entity ↔ Redis Hash structure | `CustomerProfile` ↔ `displayName`, `address`, `_class` fields |
| `RedisCustomConversions` | How a value type or Hash structure is encoded/decoded | `Address` ↔ JSON `byte[]` |
| `RedisSerializer` | How `RedisTemplate` encodes keys/values/hash keys/hash values at the Redis boundary | `StringRedisSerializer`, `GenericJackson2JsonRedisSerializer` |
| `RedisTypeMapper` | How an entity's Java type metadata is written and read | `_class` holding a class name or type alias |

Consider two usages:

```java
// Repository: maps entity to Redis Hash.
repository.save(profile);

// RedisTemplate: uses template's value serializer.
redisTemplate.opsForValue().set("customer:42", profile);
```

The second call is valid only if the template has a serializer configured for the object. It stores **a single value** under `opsForValue()` semantics; it does not automatically pass through repository-style object-to-hash mapping. Therefore, defining `RedisCustomConversions` will not suddenly make every `RedisTemplate` operation use the new mapping.

### Type Alias Also Differs from Custom Conversion

By default, type metadata may be the full class name:

```text
_class = com.example.CustomerProfile
```

You can use `@TypeAlias` to provide a short, stable name:

```java
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.redis.core.RedisHash;

@TypeAlias("customer-profile")
@RedisHash("customer-profiles")
public class CustomerProfile {
    // Fields as in previous example
}
```

Then `_class` can store `customer-profile` instead of the full Java class name. An alias configures **type metadata**; it does not determine whether `Address` is flattened or stored as JSON. To customize type metadata more deeply, Spring Data Redis supports `RedisTypeMapper` (typically via `DefaultRedisTypeMapper`/`TypeInformationMapper` and `MappingRedisConverter` configuration).

When changing an alias or type mapping strategy, evaluate compatibility for reading **existing data**. Do not arbitrarily drop metadata fields or change aliases if the application previously stored subtypes that must be distinguished.

## 7. Practical Configuration Considerations

### 7.1. Registering Converters with the Right Infrastructure

In a standard repository setup, a bean named `redisCustomConversions` is referenced by the Redis Repository infrastructure when creating `redisConverter`. If you manually configure `RedisKeyValueAdapter`, `RedisKeyValueTemplate`, or `MappingRedisConverter`, ensure the exact converter used by the adapter receives your custom conversions. **Simply declaring a class annotated with `@WritingConverter` is not enough to register it with Redis Repository.**

Example when manually constructing a converter in advanced configurations:

```java
MappingRedisConverter converter =
        new MappingRedisConverter(redisMappingContext);
converter.setCustomConversions(redisCustomConversions);
converter.afterPropertiesSet();
```

This illustrates setup when *you own the object lifecycle*. In applications managed by the Spring container, let beans be instantiated and initialized through standard lifecycle callbacks. Do not arbitrarily replace the entire default converter just to add two converters for a value object, because index, reference, and repository infrastructure features may rely on accompanying configuration.

### 7.2. Data Format Is a Long-Term Contract

Once the system starts writing `address` as JSON, old records may still use `address.city` and `address.country`. A reading converter that only knows how to parse JSON cannot automatically reconstruct old records in the new format. Before changing schemas, pick a strategy:

- Migrate all legacy data to the new schema via a controlled migration.
- Support reading both old and new schemas during a transition window.
- If it is short-TTL cache data that can be regenerated, let old cache entries expire and refresh deliberately.

Similarly, if replacing JSON with another binary format, version the payload and define how older versions are handled. A converter does not solve data compatibility on its own.

### 7.3. Mind Nulls, Corrupt Data, and Charsets

Converters must define how to handle empty bytes, malformed JSON, null data, and invalid properties. For text data, use an explicit charset such as `StandardCharsets.UTF_8`. If payloads originate from untrusted sources, avoid deserialization mechanisms that allow instantiating arbitrary disallowed Java classes. Restrict target types and validate inputs.

In our example, conversion failures throw `IllegalArgumentException` with the underlying cause. In production, you can use an exception better suited to the domain/serialization layer while logging context without leaking sensitive data.

### 7.4. Do Not Overlook Metadata and Indexes

Converters only handle data representation. Capabilities like `@Id`, `@Indexed`, `@Reference`, and `@TimeToLive` still have their own rules in Redis mapping and repositories:

- `@Id` defines identity, not an arbitrary JSON field.
- `@Indexed` requires matching metadata/index resolvers; renaming a field in a converter does not automatically update indexes.
- `@Reference` carries reference semantics to another object, not merely a nested POJO.
- `@TimeToLive` relates to Redis-managed key expiration; a TTL field's data is not equivalent to serializing an expiry duration into JSON.

When a custom converter targets an entire entity or Hash structure, pay close attention to metadata relied upon by the infrastructure. For typical scenarios, scoping custom converters to a value object is easier to control.

## 8. Common Errors and Root-Cause Troubleshooting

| Symptom | Causes to Check | Resolution |
|---|---|---|
| Saves successfully, but reading fails to build `Address` | Missing `Converter<byte[], Address>` registration or format mismatch | Provide compatible read/write pair; check `redisCustomConversions` bean |
| Hash still shows `address.city`, `address.country` | Writing converter was not applied | Verify converter registration and repository infrastructure |
| `ClassCastException` or type error on read | Bytes/Map do not match the source type expected by reading converter | Verify source/target types and actual schema |
| Some legacy records fail to read after changing converter | Storage schema changed | Migrate data or add compatible-read logic |
| Using `RedisTemplate.opsForValue()` yet custom converter doesn't run | Confusing `RedisTemplate` serializers with Repository mapping | Configure template serializer or use repository as intended |
| `@Indexed` query returns nothing despite Hash field existing | Indexing rules differ from custom converter fields | Check index metadata and index creation/rebuild strategy |
| Saving entity deletes fields added manually via CLI | Repository rewrites Hash from mapped properties | Avoid mixing manually managed fields into repository-owned Hashes |
| Changing `_class` breaks reading legacy data | Changed type alias or type mapper configuration | Maintain compatibility with stored type metadata |

To inspect Redis data, check basic information via CLI:

```redis
TYPE customer-profiles:42
HKEYS customer-profiles:42
HGETALL customer-profiles:42
TTL customer-profiles:42
```

Compare actual stored data against the read/write contract defined by your converters. Do not assume a converter failed to run just because you see binary data that doesn't look like plain text: `byte[]` might be JSON, compressed data, or another binary codec.

## 9. Practice Suggestions

**Practice 1 — Observe default mapping.** Create a `CustomerProfile` entity containing `Address` without registering any custom converters, save a record with `CrudRepository`, and inspect `HGETALL`. Note the `address.*` fields.

**Practice 2 — Change Address representation.** Register `AddressToBytesConverter` and `BytesToAddressConverter`, save a new record, and inspect `HGETALL`. Observe the single `address` field containing JSON. Read it back via the repository and verify `city`/`country` are restored.

**Practice 3 — Plan for legacy data.** Suppose 100,000 records exist in the `address.city`/`address.country` schema. Design a migration path so the new version can read data during a rolling multi-instance deployment and decide when old-schema support can be safely retired.

## 10. Conclusion

`MappingRedisConverter` is the central component converting between **Java entities** and **Redis Hashes** in Spring Data Redis Repositories. It relies on `RedisMappingContext` metadata, type rules, and converters to read and write properties, including nested objects.

`RedisCustomConversions` is the extension point for registering **custom representations for a data type**: you can store a value object as `byte[]` or explicitly produce Hash fields/values via `Map<String, byte[]>`. Always define both read and write directions, wire converters into the right repository infrastructure, and manage compatibility with existing stored data.

When configuring serialization and mapping, always distinguish **Redis Repository object-to-hash mapping**, **`RedisTemplate` serializers**, and **type metadata like `_class`**. They are related, not interchangeable.

## References

- [Spring Data Redis — Object-to-Hash Mapping](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/mapping.html): flattening rules, converting to `byte[]` and `Map<String, byte[]>`, type mapping.
- [Spring Data Redis API — MappingRedisConverter](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/convert/MappingRedisConverter.html): `read`, `write`, `setCustomConversions` APIs and converter lifecycle.
- [Spring Data Redis API — RedisCustomConversions](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/convert/RedisCustomConversions.html): how to instantiate and register custom converters.
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): scope of repository support, entities, and related mechanisms.
