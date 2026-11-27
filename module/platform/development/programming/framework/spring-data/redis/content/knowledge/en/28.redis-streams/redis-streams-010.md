# Mapping `MapRecord`, `ObjectRecord`, and Corresponding Serializers in Spring Data Redis Streams

> **Module:** Spring Data Redis  
> **Chapter:** Redis Streams  
> **Lesson:** How Spring Data Redis maps Redis Stream entries into `MapRecord` or `ObjectRecord`, the difference between `HashMapper` and `RedisSerializer`, and how to configure writers/readers so records stay compatible.

## 1. Redis Streams and the Record Concept

Redis Streams stores data as a log of entries added with `XADD`. Each entry contains a **Record ID** and a set of **field–value** pairs. Unlike Redis Pub/Sub, Stream entries are retained until deleted or trimmed per a retention policy.

Example in Redis CLI:

~~~redis
XADD events:orders * eventType order.created orderId o-101 amountMinor 125000
XRANGE events:orders - +
~~~

The response can look like:

~~~text
1) 1) "1794541200123-0"
   2) 1) "eventType"
      2) "order.created"
      3) "orderId"
      4) "o-101"
      5) "amountMinor"
      6) "125000"
~~~

Distinguish three components:

| Component | Example | Role |
|---|---|---|
| Stream key | `events:orders` | Redis key name with data type `stream` |
| Record ID | `1794541200123-0` | Entry identifier, used for cursors/ACK |
| Record body | `eventType=order.created`, `orderId=o-101` | Field–value pairs carrying business data |

Spring Data Redis expresses these as Java record objects, yet the Redis server **does not store Java objects directly**. In Redis, both `MapRecord` and `ObjectRecord` are ultimately represented as an entry with field names and values stored as bytes.

### 1.1. Overall Diagram

~~~mermaid
flowchart TD
    APP["Java Publisher"] --> CHOICE{"Record type"}
    CHOICE --> MAP["MapRecord: Map field/value"]
    CHOICE --> OBJ["ObjectRecord: Java object"]
    OBJ --> MAPPER["HashMapper.toHash"]
    MAPPER --> MAP
    MAP --> SERIAL["keySerializer + hashKeySerializer + hashValueSerializer"]
    SERIAL --> REDIS["Redis XADD"]
    REDIS --> READ["Redis XREAD / XREADGROUP"]
    READ --> DESERIAL["Deserialize MapRecord"]
    DESERIAL --> C1["Consumer handles Map directly"]
    DESERIAL --> FROM["HashMapper.fromHash"]
    FROM --> C2["Consumer handles ObjectRecord"]
~~~

**Two separate stages:** `HashMapper` converts **object ↔ Map**. `RedisSerializer` converts **Java values ↔ bytes**. Changing only one of the two stages does not guarantee the other direction remains compatible.

## 2. How Do `MapRecord` and `ObjectRecord` Differ?

Key API types in package `org.springframework.data.redis.connection.stream`:

- `Record<S, V>`: common interface holding stream key, record ID, and body.
- `MapRecord<S, HK, HV>`: body is `Map<HK, HV>`.
- `ObjectRecord<S, V>`: body is an object of type `V`.
- `StringRecord`: `MapRecord` specialization for Strings.
- `ByteRecord` and `ByteBufferRecord`: low-level byte record forms.
- `RecordId`: entry identifier, not a field inside the body.
- `StreamRecords`: utility factory for creating records.

| Aspect | `MapRecord` | `ObjectRecord` |
|---|---|---|
| Body in Java | `Map` | Domain/DTO object |
| Typical declaration | `MapRecord<String,String,String>` | `ObjectRecord<String,UserEvent>` |
| Needs object-to-field mapping? | No, body is already a Map | Yes, via mapper |
| Easy to control field names? | Yes, explicit | Depends on mapper/DTO |
| Easy across multiple languages? | Yes if byte contract is clear | Depends on mapping/type metadata |
| Readable with Redis CLI? | Yes, if serialization is readable | Yes, though fields and type metadata depend on mapper |
| Risk when renaming Java classes? | Usually lower | Can be high if class names are stored in records |
| Actual Redis type | `stream` | `stream` |

In generic `MapRecord<String,String,String>`, the type arguments mean **stream key type**, **field name type**, and **field value type**, respectively. In `ObjectRecord<String,UserEvent>`, they mean **stream key type** and **object body type**. Do not confuse the second generic parameter of `MapRecord` with the Redis key name.

### 2.1. Two Equivalent Representations at the Redis Layer

An application can define a `MapRecord` with fields itself:

~~~text
stream = events:orders
id = 1794541200123-0
body = {
  eventType: "order.created",
  orderId: "o-101"
}
~~~

Or supply a Java object and let `HashMapper` generate fields:

~~~text
ObjectRecord<String, OrderCreated>
    |
    +-- Mapper -> _class: com.example.OrderCreated
    +-- Mapper -> orderId: o-101
    +-- Mapper -> eventType: order.created
~~~

The second form is an example of a **mapping convention**: actual field names and metadata depend on the mapper, not a mandatory Redis rule.

## 3. Three Serializers You Must Understand When Using Redis Streams

Spring Data Redis documentation describes the serializer rules for Streams as follows:

| Entry component | `RedisTemplate` serializer | Example |
|---|---|---|
| `Record#getStream()` | `keySerializer` | `events:orders` |
| Field name | `hashKeySerializer` | `eventType` |
| Field value | `hashValueSerializer` | `order.created` |

Common pitfall: with `StreamOperations`, record fields and values **do not come directly from `valueSerializer` like a regular Redis String**. They go through `hashKeySerializer` and `hashValueSerializer`. This holds for `MapRecord` and for the body after `ObjectRecord` is converted to a Map by a mapper.

Example:

~~~java
RedisTemplate<String, String> template = new RedisTemplate<>();
template.setConnectionFactory(connectionFactory);

template.setKeySerializer(stringSerializer);
template.setValueSerializer(jsonSerializer);
template.setHashKeySerializer(stringSerializer);
template.setHashValueSerializer(stringSerializer);
template.afterPropertiesSet();
~~~

Suppose `jsonSerializer` is a serializer defined compatibly with generics/configuration elsewhere. In this example, setting a JSON `valueSerializer` **does not automatically turn every Stream field value into JSON**, because Streams use `hashValueSerializer`.

### 3.1. Byte-Level Flow

~~~text
MapRecord<String,String,String>
  stream = "events:orders"
  body = {"eventType": "order.created"}
            |
            v
  keySerializer("events:orders")
  hashKeySerializer("eventType")
  hashValueSerializer("order.created")
            |
            v
  Redis XADD: stream key bytes + field bytes + value bytes
            |
            v
  Redis XREAD returns bytes
            |
            v
  Reader deserializes with the same wire format
            |
            v
  MapRecord<String,String,String>
~~~

If the producer uses String serialization while the consumer uses JDK serialization for hash values, both sides can connect to the same Redis and see the same stream yet still fail to read records.

### 3.2. Common Serializers

| Serializer | Characteristics | Notes when used in streams |
|---|---|---|
| `StringRedisSerializer` | UTF-8 String | Good for text keys, field names, and field values |
| `JdkSerializationRedisSerializer` | Binary tied to Java serialization | Unsuitable as an open contract across services/languages |
| JSON serializer | Encodes each value as JSON | Requires consumers to share format and class/type policies |
| Byte-array/raw | Passes bytes with little or no extra encoding | Application takes full responsibility for decoding |
| Custom serializer | Serves a proprietary binary contract | Requires versioning, writer/reader alignment, and migration |

**Java generics do not replace serializers.** For instance, declaring `MapRecord<String,String,String>` does not magically turn JDK bytes into UTF-8 Strings.

### 3.3. Why Is `StringRedisTemplate` Easy to Use with `MapRecord`?

`StringRedisTemplate` is typically configured with String serializers for keys, values, hash keys, and hash values. It works well when every field/value in the Stream is already represented as text under an explicit schema.

If integers or decimals are needed, serialize them per contract (for example, monetary amounts in minor units formatted as Strings) and parse safely on read.

## 4. Writing `MapRecord` with `StringRedisTemplate`

In a Spring Boot app with the Redis starter and an appropriate `RedisConnectionFactory`:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
}
~~~

Example connection configuration:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Service creating a `MapRecord`:

~~~java
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    public static final String STREAM = "events:orders";

    private final StringRedisTemplate redis;

    public OrderEventPublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public RecordId publish(String orderId, long amountMinor) {
        Map<String, String> body = new LinkedHashMap<>();
        body.put("eventType", "order.created");
        body.put("schemaVersion", "1");
        body.put("orderId", orderId);
        body.put("amountMinor", Long.toString(amountMinor));
        body.put("occurredAt", Instant.now().toString());

        MapRecord<String, String, String> record =
                MapRecord.create(STREAM, body);

        return redis.opsForStream().add(record);
    }
}
~~~

**Steps:** `MapRecord.create(...)` builds the Java record; `opsForStream().add(...)` sends `XADD`; Redis returns `RecordId`. `schemaVersion` is an application-defined business field. Redis does not automatically assign schema versions.

### 4.1. Ways to Create `MapRecord`

~~~java
Map<String, String> fields =
        Map.of("eventType", "order.created",
               "orderId", "o-101");

MapRecord<String, String, String> first =
        MapRecord.create("events:orders", fields);

MapRecord<String, String, String> second =
        StreamRecords.<String, String, String>mapBacked(fields)
                .withStreamKey("events:orders");
~~~

Another option is `StreamRecords.string(fields).withStreamKey("events:orders")`, returning a `StringRecord`. Factories only **construct the record object**; nothing is saved to Redis until `add(...)` is called.

### 4.2. Reading `MapRecord`

~~~java
import java.util.List;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;

public class OrderEventReader {

    private final StringRedisTemplate redis;

    public OrderEventReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<MapRecord<String, String, String>> readBeginning() {
        List<MapRecord<String, String, String>> result =
                redis.opsForStream().read(
                        StreamReadOptions.empty().count(20),
                        StreamOffset.create(
                                OrderEventPublisher.STREAM,
                                ReadOffset.from("0-0")));

        return result == null ? List.of() : result;
    }
}
~~~

`ReadOffset.from("0-0")` works well for illustrating reading entries from the start. In continuous processing apps, manage offsets or consumer groups; otherwise you risk re-reading the same history repeatedly.

Using the records:

~~~java
for (MapRecord<String, String, String> record : records) {
    RecordId recordId = record.getId();
    String streamName = record.getStream();
    Map<String, String> body = record.getValue();

    String eventType = body.get("eventType");
    String orderId = body.get("orderId");
    long amountMinor = Long.parseLong(
            body.get("amountMinor"));

    // Validate, dispatch event, and process business logic.
}
~~~

Handle missing fields, unknown `schemaVersion` values, and invalid numbers. Successfully deserializing a `MapRecord` only confirms the bytes were readable, **not** that the data is valid for business logic.

### 4.3. Checking with Redis CLI

~~~bash
redis-cli TYPE events:orders
redis-cli XLEN events:orders
redis-cli XRANGE events:orders - + COUNT 10
~~~

`TYPE` returns `stream`, not `hash`. Even though Stream entries have field–value pairs, you cannot replace `XRANGE` with `HGETALL events:orders`; Redis will return a wrong-type error.

## 5. Manually Configuring `RedisTemplate` for Text Streams

`StringRedisTemplate` is not the only option. If you need a dedicated template for streams, configure **both the stream key and hash serializers** properly.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class TextStreamConfiguration {

    @Bean("textStreamTemplate")
    RedisTemplate<String, String> textStreamTemplate(
            RedisConnectionFactory connectionFactory) {

        StringRedisSerializer strings = new StringRedisSerializer();

        RedisTemplate<String, String> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(strings);
        template.setValueSerializer(strings);
        template.setHashKeySerializer(strings);
        template.setHashValueSerializer(strings);
        template.afterPropertiesSet();

        return template;
    }
}
~~~

Here `setValueSerializer(strings)` keeps other Redis operations consistent, while for Stream fields, the crucial ones are `hashKeySerializer` and `hashValueSerializer`.

When multiple `RedisTemplate` beans exist, inject the intended bean via `@Qualifier("textStreamTemplate")`. Declaring a new template does not automatically switch existing consumers or `RedisMessageListenerContainer` beans to the new serializer.

### 5.1. Common Pitfall: Changing Serializers After Data Already Exists

Example:

- Week 1: producer writes String field values in UTF-8.
- Week 2: code changes `hashValueSerializer` to JDK or JSON.
- The Redis Stream still holds old entries from Week 1.
- New consumers try to decode everything using Week 2's format.

The result can be deserialization failures or values differing from the original logic. **Changing a `RedisTemplate` serializer is a wire-format change**; it does not migrate historical data.

If a stream has long retention, plan for a new stream, multi-format readers, or explicit migration.

## 6. `ObjectRecord`: Representing the Body as a Java Object

Instead of manually building a Map, you can create an `ObjectRecord`:

~~~java
ObjectRecord<String, String> record =
        StreamRecords.newRecord()
                .in("events:simple")
                .ofObject("hello");

redisTemplate.opsForStream().add(record);

List<ObjectRecord<String, String>> result =
        redisTemplate.opsForStream().read(
                String.class,
                StreamOffset.fromStart("events:simple"));
~~~

Here `redisTemplate` is configured compatibly for stream/object mapping. Under Spring Data Redis's default mapping conventions, a simple value may be converted into fields:

~~~redis
XADD events:simple * _class java.lang.String _raw hello
~~~

`_class` and `_raw` are Spring convention metadata fields, **not** mandatory special fields required by Redis.

### 6.1. `ObjectRecord` with a Domain Object

Suppose a Java domain event:

~~~java
public class UserLoggedIn {

    private String username;
    private String device;

    public UserLoggedIn() {
    }

    public UserLoggedIn(String username, String device) {
        this.username = username;
        this.device = device;
    }

    public String getUsername() { return username; }
    public String getDevice() { return device; }

    public void setUsername(String username) {
        this.username = username;
    }

    public void setDevice(String device) {
        this.device = device;
    }
}
~~~

Sending and reading a typed record:

~~~java
ObjectRecord<String, UserLoggedIn> record =
        StreamRecords.newRecord()
                .in("events:user-logon")
                .ofObject(new UserLoggedIn("night", "mobile"));

RecordId id = redisTemplate.opsForStream().add(record);

List<ObjectRecord<String, UserLoggedIn>> messages =
        redisTemplate.opsForStream().read(
                UserLoggedIn.class,
                StreamOffset.fromStart("events:user-logon"));
~~~

The benefit is handlers avoid calling `Map.get("username")`, though this convenience relies on the mapper understanding the object properly.

A mapping might produce fields:

~~~text
_class   = com.example.UserLoggedIn
username = night
device   = mobile
~~~

Actual names and representations can vary by `HashMapper`/`RedisConverter`/version. Never assume `ObjectRecord` is written as a single JSON String.

## 7. `HashMapper`: A Separate Conversion Step

`HashMapper<T, HK, HV>` is the object ↔ Map contract.

~~~text
WRITE:
  UserLoggedIn
       |
       v
  HashMapper.toHash(object)
       |
       v
  Map<HK, HV>
       |
       v
  RedisSerializer (stream key, hash key, hash value)
       |
       v
  Redis XADD

READ:
  Redis XREAD
       |
       v
  RedisSerializer.deserialize
       |
       v
  Map<HK, HV>
       |
       v
  HashMapper.fromHash(map)
       |
       v
  UserLoggedIn
~~~

Spring Data Redis uses `ObjectHashMapper` as the default mapper for object records according to the Streams documentation. You can pass a custom mapper via `opsForStream(hashMapper)` when explicit conversion is required.

### 7.1. `ObjectHashMapper`

`ObjectHashMapper` combines Spring Data mapping rules and `RedisConverter` to turn object properties into hash fields and values. It commonly operates on `Map<byte[],byte[]>` at the conversion layer.

Points to understand:

- The mapper can store type metadata, such as `_class`.
- Nested properties can produce multiple path-based fields.
- Converters or custom conversions can alter the representation.
- Reading back into an object requires matching mapping context, constructors/setters, and converters.
- If the mapper produces `byte[]` while a serializer tries to treat values as `String`, the configuration can break.

**Do not pick a `StringRedisTemplate` just because the stream key is a `String` and assume `ObjectHashMapper` also emits `String` fields.** Verify the types produced by the mapper and the corresponding serializers in both directions.

### 7.2. `JacksonHashMapper`

`JacksonHashMapper` builds a Map from an object via Jackson, with hierarchical or flattened options. For example:

~~~json
{
  "username": "night",
  "address": {
    "city": "Hanoi",
    "country": "VN"
  }
}
~~~

Two mapping styles:

| Hierarchical | Flat |
|---|---|
| `username=night` | `username=night` |
| `address={"city":"Hanoi","country":"VN"}` | `address.city=Hanoi` |
| — | `address.country=VN` |

In flat mode, dots or brackets in field/path names can cause trouble, and flattened data may not always reconstruct the original object cleanly. Consider **reading back** before choosing flattening.

Constructor/factory APIs for Jackson hash mappers have evolved across Spring Data Redis/Jackson generations: older docs reference `Jackson2HashMapper` or constructors taking `boolean flatten`, while newer releases offer different `JacksonHashMapper` builders/factories. Check the exact Javadoc for your project's version before copying code.

### 7.3. Customizing the Mapper in `StreamOperations`

API shape per documentation:

~~~java
// A suitable HashMapper has been created and configured.
// It can be attached to StreamOperations when working with ObjectRecord.

redisTemplate.opsForStream(customHashMapper).add(objectRecord);
~~~

This illustrates the extension point; `customHashMapper` and `objectRecord` must have generics and formats compatible with the template in use.

If a consumer uses a different mapper from the producer, it may fail to read records even when both connect to the same `RedisTemplate` setup and stream key.

## 8. Reading `ObjectRecord` from `MapRecord`

When Redis returns an entry, Spring can deserialize it into a `MapRecord`. When a target class is requested, the mapping layer converts the record into a corresponding `ObjectRecord`.

~~~text
Redis bytes -> MapRecord
                   |
                   +--> Consumer handles Map itself
                   |
                   +--> HashMapper.fromHash
                                   |
                                   v
                             ObjectRecord
~~~

Thus a record written from an `ObjectRecord` can still be read as a `MapRecord` when bytes are decoded properly. The reverse is **not arbitrary**: a `MapRecord` containing a JSON `payload` field will not automatically turn into an arbitrary POJO via the default `ObjectHashMapper`.

Spring `StreamOperations` provides APIs mapping `MapRecord` → `ObjectRecord` for a target type, provided the target mapper understands the field representation produced by the writer.

### 8.1. `RecordId` Is Kept Separate

Every `MapRecord` or `ObjectRecord` has `getStream()` and `getId()`. When converting from a Map to an object, this metadata must remain available for offsets and ACKs.

~~~text
stream    = events:orders
recordId  = 1794541200123-0
body      = {orderId=o-101, eventType=order.created}
~~~

`recordId` is not inside `getValue()` unless the application explicitly writes another field to store a business ID. Distinguish Redis `RecordId` from a domain event's `eventId` used for deduplication.

## 9. Multi-Field `MapRecord` vs. Single-Field JSON

For polyglot systems, two common contracts both use `MapRecord`.

### 9.1. Multiple Independent Fields

~~~redis
XADD events:orders * eventType order.created schemaVersion 1 orderId o-101 amountMinor 125000
~~~

Pros: easy to inspect with CLI, explicit fields, straightforward with `StringRedisTemplate`.

Cons: must standardize number/date formatting and nested objects; consumers parse and validate fields themselves.

### 9.2. A Single Field Containing JSON

~~~redis
XADD events:orders * payload "{\"eventType\":\"order.created\",\"schemaVersion\":1,\"orderId\":\"o-101\",\"amountMinor\":125000}"
~~~

Pros: JSON schemas support nested objects/arrays, cross-language contracts, and clean versioning.

Cons: consumers need a JSON parser; Redis has no visibility into properties inside the `payload` field.

Java example:

~~~java
String json = objectMapper.writeValueAsString(eventDto);

RecordId id = stringRedisTemplate.opsForStream().add(
        "events:orders",
        Map.of(
                "contentType", "application/json",
                "payload", json));
~~~

`eventDto` is an application domain DTO; `objectMapper` is the corresponding Jackson mapper. The `add` call still writes a `MapRecord`; Jackson simply encodes the payload **before** passing it to `StringRedisTemplate`.

### 9.3. When to Choose Each Approach?

| Need | Recommended choice |
|---|---|
| Few fields, all text, multi-language consumers | Field–value `MapRecord` |
| Complex nested payload, needs schema contract | `MapRecord` containing JSON |
| Internal Java DTOs, controlled converters | `ObjectRecord` |
| Compact byte protocol, custom binary | `ByteRecord`/`MapRecord` with published binary contract |
| Long-lived stream, multiple reader versions | Contract with `schemaVersion` and backward compatibility |
| Consumers unaware of producer Java classes | Avoid depending on Java type metadata |

`ObjectRecord` **is not synonymous with JSON**; it is a Java representation that can emit multiple fields via a mapper.

## 10. Mapping in Consumer Groups and ACK

Redis Streams supports consumer groups. `XREADGROUP` distributes entries to consumers; Redis maintains a Pending Entries List (PEL) for delivered but unacknowledged entries.

Using `MapRecord` or `ObjectRecord` **does not change** the meaning of ACK: consumers must use the record ID to confirm after successful processing.

Example reading with `MapRecord`:

~~~java
import java.util.List;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.core.StreamReadOptions;

List<MapRecord<String, String, String>> records =
        stringRedisTemplate.opsForStream().read(
                Consumer.from("orders-group", "worker-1"),
                StreamReadOptions.empty().count(10),
                StreamOffset.create(
                        "events:orders",
                        ReadOffset.lastConsumed()));
~~~

The group must exist before reading. For each finished record:

~~~java
for (MapRecord<String, String, String> record : records) {
    handleOrderEvent(record.getValue());

    stringRedisTemplate.opsForStream()
            .acknowledge("orders-group", record);
}
~~~

`handleOrderEvent` is an application business method. Handle null lists, decoding errors, retries, and idempotency.

**Do not ACK before processing** if retries are required when handlers fail. ACKing does not delete stream contents; it removes the record from the group's pending list. Stream retention is managed separately via trimming such as `XTRIM`.

### 10.1. Object Mapping Errors and Pending Entries

If a listener reads `ObjectRecord` directly and fails to deserialize because metadata or a class is missing, the handler may never receive the record to process or ACK. The record can then remain pending and need an appropriate error-handling mechanism.

For events supporting multiple schema versions, one strategy is:

1. Read as controlled `MapRecord`/bytes.
2. Inspect `schemaVersion` and `eventType`.
3. Select the parser/mapper for that version.
4. Validate business data.
5. Execute idempotent side effects.
6. ACK once processing is confirmed complete.
7. For broken records, apply retries, quarantine/dead-lettering, or reconciliation per business policy.

Redis Streams can replay retained entries, yet **does not automatically guarantee exactly-once side effects**. A worker can finish processing and crash before ACK, causing the entry to be redelivered.

### 10.2. `ReadOffset` Must Be Understood Correctly

- `ReadOffset.from("0-0")`: starts reading from after the specified ID, commonly used when reading history.
- `ReadOffset.latest()`: reads new entries from the tail per specific semantics; gaps can occur between polls.
- `ReadOffset.lastConsumed()`: commonly used with consumer groups to continue from the consumed position.

Pending entries after a crash must be handled via an appropriate pending/reclaim mechanism rather than merely calling `lastConsumed()` and expecting all pending entries to redeliver automatically as new messages.

## 11. `StreamMessageListenerContainer` and Serializers

Spring Data Redis provides `StreamMessageListenerContainer` for imperative polling/dispatch, and `StreamReceiver` for reactive. Both still decode keys, fields, and values into records.

A `MapRecord` listener:

~~~java
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.stream.StreamListener;

public class OrderStreamListener
        implements StreamListener<
                String, MapRecord<String, String, String>> {

    @Override
    public void onMessage(
            MapRecord<String, String, String> message) {
        System.out.println("Stream: " + message.getStream());
        System.out.println("Id: " + message.getId());
        System.out.println("Body: " + message.getValue());
    }
}
~~~

Illustrative container:

~~~java
import java.time.Duration;

import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.stream.StreamMessageListenerContainer;
import org.springframework.data.redis.stream.StreamMessageListenerContainer
        .StreamMessageListenerContainerOptions;

StreamMessageListenerContainerOptions<
        String, MapRecord<String, String, String>> options =
        StreamMessageListenerContainerOptions.builder()
                .pollTimeout(Duration.ofMillis(100))
                .build();

StreamMessageListenerContainer<
        String, MapRecord<String, String, String>> container =
        StreamMessageListenerContainer.create(
                connectionFactory, options);

container.receive(
        StreamOffset.fromStart("events:orders"),
        new OrderStreamListener());

container.start();
~~~

This configuration snippet assumes an available `connectionFactory`; Spring applications should manage the container as a bean with appropriate lifecycle and error handlers.

### 11.1. Containers Do Not Automatically “Inherit” the Publisher's Serializers

A common mistake:

- The publisher sends `MapRecord` via `StringRedisTemplate` using UTF-8 String serialization.
- The listener container is built separately from `RedisConnectionFactory` with different default options/codecs.
- The container deserializes fields/values wrongly, even though `opsForStream().read(...)` via `StringRedisTemplate` works fine.

Configure matching serializers and mappers for **writers, direct readers, and listener containers alike**. Never infer that a container automatically uses another template bean's serializers just because they share the same `RedisConnectionFactory`.

### 11.2. `ObjectRecord` Listeners Need Matching Mappers

The listener container options API supports an object mapper:

~~~java
StreamMessageListenerContainerOptions<
        String, ObjectRecord<String, Object>> options =
        StreamMessageListenerContainerOptions.builder()
                .objectMapper(objectHashMapper)
                .build();
~~~

`objectHashMapper` is created with an appropriate conversion context. Especially when using `@TypeAlias`, the listener container may need a `RedisMappingContext` aware of domain types upfront to resolve aliases.

### 11.3. Reactive `StreamReceiver`

`StreamReceiver` uses a `ReactiveRedisConnectionFactory` and emits records via `Flux`. Differences in async execution, polling, and backpressure do not remove the requirement for **matching serializers and object mappers**.

If a reactive reader pauses polling and uses `ReadOffset.latest()`, entries arriving between polls risk being missed. Select offset strategies and group semantics per processing requirements. With consumer groups, ACK, pending state, and recovery still apply.

## 12. Type Metadata, `@TypeAlias`, and Renaming Java Classes

`ObjectHashMapper` can persist type info under `_class`. If stored data contains:

~~~text
_class = com.example.events.UserLoggedIn
~~~

and a later deployment renames it to:

~~~text
com.example.contract.UserLoggedIn
~~~

old records may fail to map back if the converter still expects the previous class name. Streams retain history, so refactoring Java packages can break older entries.

`@TypeAlias` can provide a more stable alias name where supported by mapping. However, consumers need a mapping context that already registered those types/aliases. Spring Data Redis notes that listener containers may not know those aliases unless initialized with a matching `initialEntitySet`.

Illustrative configuration sketch:

~~~java
import java.util.Set;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.convert.MappingRedisConverter;
import org.springframework.data.redis.core.convert.RedisConverter;
import org.springframework.data.redis.core.mapping.RedisMappingContext;
import org.springframework.data.redis.hash.ObjectHashMapper;

@Configuration
public class ObjectStreamMappingConfiguration {

    @Bean
    RedisMappingContext redisMappingContext() {
        RedisMappingContext context = new RedisMappingContext();
        context.setInitialEntitySet(Set.of(UserLoggedIn.class));
        return context;
    }

    @Bean
    RedisConverter redisConverter(RedisMappingContext context) {
        return new MappingRedisConverter(context);
    }

    @Bean
    ObjectHashMapper streamObjectHashMapper(RedisConverter converter) {
        return new ObjectHashMapper(converter);
    }
}
~~~

When Spring Boot already auto-configures mapping/converter beans for Redis Repositories, do not create duplicate beans without understanding the wiring. Config snippets are directional guidance to adapt to your project's packages, imports, and library version.

**A stable alias does not replace schema versioning.** Nor does it automatically handle renamed fields, changed types, or shifted data semantics.

## 13. Schema Evolution and Mapping Changes

A stream can hold records written by multiple producer versions. For example:

**Schema v1:**

~~~text
eventType = order.created
schemaVersion = 1
orderId = o-101
amountMinor = 125000
~~~

**Schema v2:**

~~~text
eventType = order.created
schemaVersion = 2
orderId = o-101
amountMinor = 125000
salesChannel = WEB
~~~

A `MapRecord` consumer can dispatch explicitly:

~~~java
Map<String, String> body = record.getValue();

int schemaVersion = Integer.parseInt(
        body.getOrDefault("schemaVersion", "0"));

switch (schemaVersion) {
    case 1 -> handleV1(body);
    case 2 -> handleV2(body);
    default -> handleUnsupported(body, record.getId());
}
~~~

The handler methods contain application logic. With `ObjectRecord`, if v2 changes the DTO or `HashMapper`, a single mapper may no longer read both v1 and v2. Consider reading raw `MapRecord` first and mapping by version, or keeping serializers/mappers backward-compatible with history.

### 13.1. Switching `ObjectHashMapper` to `JacksonHashMapper`

This can be a breaking change, not merely changing “how JSON is read”:

- Metadata `_class` vs. `@class` may differ.
- Nested properties may be stored under different paths.
- Returned value types may be bytes vs. objects/strings depending on the mapper.
- Older consumers may lack converters/aliases to read new data.

Mapping docs do not promise that different mappers emit identical wire formats. Therefore, plan versioning or migration if the Stream retains old data.

### 13.2. Do Not Let Java Classes Dictate Public Event Contracts

If a Stream is consumed by Python/Node/Go services, those consumers do not know how to instantiate `com.example.UserLoggedIn`. They only see fields and values. In polyglot architectures, prefer contracts like:

~~~json
{
  "eventType": "user.logged-in",
  "schemaVersion": 1,
  "eventId": "e-123",
  "userId": "u-101",
  "device": "mobile"
}
~~~

The publisher can serialize the DTO to JSON with Jackson upfront and write that JSON as a String field in a `MapRecord`. This decouples the event contract from Spring Data Redis type metadata.

## 14. Common Serialization Pitfalls

| Symptom | Likely cause to check | Resolution |
|---|---|---|
| Field names show unreadable bytes | `hashKeySerializer` is not String | Align with publisher |
| Stream key reads empty | Mismatched `keySerializer`, wrong Redis DB/endpoint | Verify raw keys and connection |
| Values have extra JSON quotes | Writer used JSON serializer, reader used String serializer | Use matching decoder |
| `ClassCastException` reading `MapRecord` | Hash value decoded into a different type than generic expects | Align serializer and data type |
| Cannot map into `ObjectRecord` | Reader `HashMapper` differs from writer mapper | Use the same conversion contract |
| Failure after renaming a Java class package | Type metadata holds old FQCN | Aliases, compatibility reader, or migration |
| Object mapping drops properties | Mismatched field names, constructors, or converters | Check mapping metadata |
| Flattened object fails round-trip read | Field/path name constraints or flat mapper limits | Choose hierarchical or explicit contract |
| Listener fails while manual read works | Container uses a different mapper/serializer | Inspect container options |
| Group pending never shrinks | Handler does not ACK or fails decoding | Inspect `XPENDING`, retry policy |
| Same event processed multiple times | Retries/reclaim or duplicate producer writes | Idempotency and business `eventId` |

### 14.1. Do Not Confuse a Redis Stream with a Redis Hash

Stream entries have field–value pairs similar to a Hash, yet the key type is `stream`. `opsForHash()` and `opsForStream()` are distinct APIs.

~~~bash
redis-cli TYPE events:orders
# stream

redis-cli XRANGE events:orders - + COUNT 5
# Read Stream entries

redis-cli HGETALL events:orders
# WRONGTYPE if the key is a stream
~~~

### 14.2. Do Not Confuse `RecordId` with Payload

`RecordId` is entry metadata, not a field automatically injected into `getValue()`. If a business `eventId` is needed for cross-stream deduplication, put a dedicated `eventId` field inside the body.

### 14.3. Do Not Confuse Changing `valueSerializer` with Changing `MapRecord` Body

Changing `RedisTemplate.setValueSerializer(...)` does not alter `StreamOperations` body serialization, because Stream fields use `hashValueSerializer`. Always check the right layer.

### 14.4. Do Not Confuse `ObjectRecord` with a JSON Document

`ObjectRecord` can emit multiple fields/values via `ObjectHashMapper`. If a single-field JSON payload is desired, encode JSON explicitly or configure an appropriate mapper. Using a Java object in the API does not guarantee the bytes in Redis are JSON.

## 15. Security and Replayability

A Redis Stream record may arrive from another producer, live for a long time, and get replayed. Therefore:

- Validate data and `schemaVersion` after deserialization.
- Accept only explicitly permitted DTOs/aliases.
- Restrict polymorphic type instantiation and native Java deserialization on untrusted data.
- Never log raw payloads containing PII/secrets.
- Bound JSON payload size and complexity.
- Use Redis ACLs/TLS and separate producer vs. consumer permissions.
- Design idempotent handlers because retries/reclaims can reprocess the same record.
- Only ACK when processing finishes or after an error-policy decision is durably recorded.

Redis Streams offers retention and consumer groups, yet does not guarantee exactly-once side effects merely from `XACK`. If processing succeeds and the process crashes before ACK, the event may be redelivered.

### 15.1. Stream Key TTL Is Not Per-Entry TTL

Calling `EXPIRE events:orders 3600` sets a TTL on the **entire Stream key**. When the key expires, all entries vanish. To bound entry counts or ages in a Stream, use retention and trimming (`XTRIM`, `MAXLEN`, `MINID` if supported by your Redis version). Never treat individual `MapRecord`/`ObjectRecord` entries as independent Redis keys with their own TTLs.

## 16. Layer-by-Layer Troubleshooting

A short checklist:

1. **Is the key the right Redis type?** Check `TYPE`, `XLEN`.
2. **Does the record exist?** Check `XRANGE`/`XREVRANGE`.
3. **Is the stream key decoded properly?** Check `keySerializer`.
4. **Are field names and values right?** Check `hashKeySerializer` and `hashValueSerializer`.
5. **`MapRecord` works while `ObjectRecord` fails?** Check `HashMapper`, converters, metadata, target class.
6. **Manual reads work while listener fails?** Check listener options, offset, group, and lifecycle.
7. **Handler duplicates or loses data?** Check ACK, pending, reclaim, idempotency, and retention.

Useful CLI commands in test environments:

~~~bash
redis-cli TYPE events:orders
redis-cli XLEN events:orders
redis-cli XRANGE events:orders - + COUNT 10
redis-cli XREVRANGE events:orders + - COUNT 10
redis-cli XINFO STREAM events:orders
redis-cli XINFO GROUPS events:orders
redis-cli XPENDING events:orders orders-group
~~~

`XINFO GROUPS` and `XPENDING` require a matching group. With binary serializers, Redis CLI may display escaped bytes—that does not necessarily mean corrupted data.

### 16.1. Metrics to Observe

- `XADD` and `XREADGROUP` rates.
- Stream length and average record size.
- Serializer/deserializer errors and unsupported `schemaVersion` counts.
- Pending entries, age, and reclaim counts.
- Handler latency and ACK failures.
- Duplicate messages caught by `eventId`.
- Redis latency, memory usage, and connection failures.

Do not use `recordId` or `eventId` as metric labels due to high cardinality; they belong in bounded structured logs and traces.

## 17. Usage Decision Matrix

| Use case | Record type to consider | Serialization |
|---|---|---|
| Simple cross-language events | `MapRecord` | UTF-8 String fields/values |
| Nested objects, versioned schema | `MapRecord` with JSON `payload` | UTF-8 String + JSON parser |
| Java-only workers using domain DTOs | `ObjectRecord` | Aligned `HashMapper` and hash serializers |
| Mapping nested objects into multiple fields | `ObjectRecord` + matching mapper | Choose hierarchical vs. flat carefully |
| Compact byte protocol, custom binary | `ByteRecord`/`MapRecord` | Versioned binary contract |
| Long-lived stream, multiple versions | Raw `MapRecord` → version dispatcher | Keep readers for old formats |

Question to ask before choosing: **Who will read the record, how long will it live, and are publishers/consumers deployed independently?** If services use different languages or upgrade on separate schedules, a Java-independent wire format usually matters more than saving a few lines in the publisher via `ObjectRecord`.

## 18. Frequently Asked Questions

**Are `MapRecord` and `ObjectRecord` two different Redis data types?**  
No. Both are stored as field–value Stream entries; they differ in Java representation and the object-mapping step.

**Are Stream field values written through `valueSerializer` or `hashValueSerializer`?**  
Through `RedisTemplate`'s `hashValueSerializer` in standard `StreamOperations`.

**Does `ObjectRecord` automatically convert objects to JSON?**  
Not by default. It can emit Map fields via `ObjectHashMapper`, along with type metadata.

**Can an `ObjectRecord` be read back as a `MapRecord`?**  
Yes, if the reader can deserialize the fields and values; in Redis, the body is still field–value pairs.

**Can a `MapRecord` automatically map into an arbitrary DTO?**  
No. The mapper must understand the exact format; a JSON `payload` field requires explicit parsing or mapping.

**Why does reading with `StringRedisTemplate` succeed while the listener container fails?**  
The container may be using different serializers/mappers from the template. Both paths must be configured consistently.

**Does renaming a Java class affect existing stream data?**  
It can, if `ObjectHashMapper` stored class-name type metadata. Aliases, compatibility readers, or migration are needed.

**Does ACK depend on `MapRecord` vs. `ObjectRecord`?**  
No. ACK uses the Redis Record ID and consumer group. What matters is ACKing only when processing policy permits.

**Can `StringRedisTemplate` write JSON?**  
Yes. Serialize the DTO to a JSON String first and write it into a `payload` field with `StringRedisTemplate`. JSON is parsed by consumers, not the Redis server.

**Do Redis Stream entries have individual TTLs?**  
Not in the sense of separate Redis keys. Expiring a stream key deletes the whole stream; entry retention uses trimming.

## 19. Summary

**`MapRecord` represents explicit field–value pairs; `ObjectRecord` represents a Java object and requires a `HashMapper` to convert to and from field–value pairs.** Both are stored as Redis Streams—there are not two distinct Stream types on the Redis side.

In Spring Data Redis Streams, remember the serializer mapping:

- `Record#getStream()` → **`keySerializer`**.
- Field names → **`hashKeySerializer`**.
- Field values → **`hashValueSerializer`**.

`RedisTemplate`'s `valueSerializer` is not the default serializer for Stream field values. With `ObjectRecord`, you must also keep `HashMapper`/`RedisConverter`/`@TypeAlias` aligned between writers and readers. When a stream retains long history, any change to serializers, mappers, or class metadata is a contract change requiring a versioning strategy.

For polyglot data and public contracts, a **`MapRecord` using UTF-8 Strings or a JSON payload with `schemaVersion`** is usually easier to evolve. For Java-only applications controlling all producers and consumers, **`ObjectRecord`** can be convenient once mapping and serialization are unified. Whichever type you pick, manage `RecordId`, ACKs, error handling, idempotency, and retention explicitly.

## References

- Spring Data Redis — [Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): records, serializers, object mapping, listeners, and consumer groups.
- Spring Data Redis — [StreamOperations API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/StreamOperations.html): adding, reading, mapping, and acknowledging records.
- Spring Data Redis — [MapRecord API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/connection/stream/MapRecord.html): `MapRecord` and serialization.
- Spring Data Redis — [StreamRecords API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/connection/stream/StreamRecords.html): record creation factories.
- Spring Data Redis — [Hash Mapping](https://docs.spring.io/spring-data/redis/reference/redis/hash-mappers.html): `ObjectHashMapper`, `JacksonHashMapper`, nested/flat mapping.
- Redis — [Streams](https://redis.io/docs/latest/develop/data-types/streams/): commands, entry IDs, consumer groups, and retention.
- Redis — [XADD](https://redis.io/docs/latest/commands/xadd/), [XREAD](https://redis.io/docs/latest/commands/xread/), [XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/), [XACK](https://redis.io/docs/latest/commands/xack/): core commands.
