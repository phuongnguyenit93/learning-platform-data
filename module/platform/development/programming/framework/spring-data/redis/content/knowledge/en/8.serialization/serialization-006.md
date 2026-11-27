# Type Information, Polymorphism, and Restricting Allowed Types on Deserialization

In Spring Data Redis, data is stored as bytes. Redis knows whether a key holds a String, Hash, List, Set, or another Redis structure, yet **Redis does not inherently know which Java class a JSON value belongs to**. Turning stored data back into Java objects is the responsibility of the serializer/deserializer.

This becomes especially important when an application:

- Stores multiple different Java classes under a common reference type such as `Object`, an interface, or an abstract class.
- Uses `RedisTemplate<String, Object>` and `GenericJackson2JsonRedisSerializer`.
- Caches an object containing a field with multiple forms (*polymorphic field*).
- Reads Redis data written by an older application version, another service, or an external component.
- Wants to control **which Java types are permitted to be instantiated when restoring data**, rather than accepting any class name present in a payload.

This topic connects three concepts: **type metadata**, **polymorphism**, and **type allowlisting**. The goal is to restore the exact data structure while preventing arbitrary payloads from dictating which Java class gets instantiated.

## 1. Three Layers of "Type" to Distinguish

A cache record passes through multiple layers:

~~~text
Java object
  NotificationEnvelope(eventId="evt-42",
                       payload=EmailPayload(...))
           |
           | Jackson serializer
           v
JSON bytes
  {"eventId":"evt-42",
   "payload":{"kind":"email","address":"a@example.com"}}
           |
           | Spring Data Redis connection
           v
Redis key: notification:evt-42
Redis TYPE: string
Redis value: byte sequence containing JSON
           |
           | Jackson deserializer + subtype resolution rules
           v
Java object
  NotificationEnvelope -> EmailPayload
~~~

| Layer | Question It Answers | Example |
|---|---|---|
| **Redis data type** | Which commands does Redis support on this key? | `TYPE notification:evt-42` returns `string` |
| **Java declared type** | Which type does code expect to receive? | `NotificationEnvelope`, `NotificationPayload`, `Object` |
| **Type info in payload** | When a field has multiple subclasses, which concrete class should be chosen? | `"kind":"email"` or `"@class":"com.example..."` |

Do not confuse Redis's `TYPE key` with Java class names. A Redis String can hold a JSON object, an integer, Java binary serialization, or other raw bytes. Similarly, using `opsForHash()` means operating on a Redis Hash, while using `Jackson2JsonRedisSerializer` merely determines how Java values are converted to JSON bytes.

### 1.1. Serialization and Deserialization Are Asymmetric When Type Info Is Lost

**Serialization** normally knows the concrete class of an object in memory:

~~~java
Object value = new EmailPayload("a@example.com", "Welcome");
// At serialization time, the JVM still knows value is an EmailPayload.
~~~

When deserializing, however, a plain JSON payload only contains properties:

~~~json
{
  "address": "a@example.com",
  "subject": "Welcome"
}
~~~

JSON has no built-in concept of "this is an EmailPayload." If code asks to read into `EmailPayload.class`, Jackson can map directly. If code asks to read into interface `NotificationPayload` or `Object`, it needs additional rules to decide which object type to instantiate.

Writing class names into JSON is not always required. Typically there are three approaches:

1. **Static target type:** the application already knows the concrete class when invoking the deserializer.
2. **Domain discriminator:** JSON has a field such as `kind` or `type`; a predefined set of subtypes is registered.
3. **Dynamic class metadata:** payload carries class information; the reader decides the Java type from metadata and must strictly restrict allowed types.

## 2. When Can You Avoid Type Metadata?

Start from the simple case: each cache key follows a single clear schema.

~~~java
public record ProductCache(
        String productId,
        String title,
        long priceInCents
) {}
~~~

JSON value:

~~~json
{
  "productId": "p-1001",
  "title": "Mechanical keyboard",
  "priceInCents": 12900
}
~~~

If the serializer is configured with the **concrete target type** `ProductCache.class`, it does not need to read an `@class` field from JSON to identify the root class.

Spring Data Redis example using Jackson 2 (suitable for the Spring Data Redis 3.x branch):

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class ProductCacheRedisConfig {

    @Bean("productCacheRedisTemplate")
    RedisTemplate<String, ProductCache> productCacheRedisTemplate(
            RedisConnectionFactory connectionFactory,
            ObjectMapper objectMapper) {

        RedisTemplate<String, ProductCache> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(
                new Jackson2JsonRedisSerializer<>(
                        objectMapper, ProductCache.class));
        return template;
    }
}
~~~

Using the template:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;

@Service
public class ProductCacheService {

    private final RedisTemplate<String, ProductCache> redis;

    public ProductCacheService(
            @Qualifier("productCacheRedisTemplate")
            RedisTemplate<String, ProductCache> redis) {
        this.redis = redis;
    }

    public void save(ProductCache product) {
        redis.opsForValue().set(
                "product-cache:" + product.productId(),
                product,
                Duration.ofMinutes(10));
    }

    public ProductCache find(String productId) {
        return redis.opsForValue().get("product-cache:" + productId);
    }
}
~~~

Note: the bean example uses the Spring-provided `ObjectMapper` to preserve shared JSON settings (modules, date/time policies, etc.). If the shared object mapper has global default typing enabled, this serializer may also be affected; to guarantee a purely static schema, control the mapper configuration or use a separate, explicitly configured mapper.

**Benefits of static typing:** readable payloads, minimal coupling to Java class names, easy package refactoring, and straightforward bounding of instantiable types at the read site.

**Limitation:** if a field inside the DTO is an interface or abstract class, you still must resolve polymorphism for **that field**. Specifying the concrete root class does not automatically answer which subclass the nested object belongs to.

## 3. Why Does Polymorphism Make Reading from Redis Harder?

Suppose a notification system supports two delivery channels:

~~~text
NotificationPayload (interface)
        |
        +-- EmailPayload
        |      address
        |      subject
        |
        +-- SmsPayload
               phoneNumber
               message
~~~

An envelope contains the interface field:

~~~java
record NotificationEnvelope(
        String eventId,
        NotificationPayload payload
) {}
~~~

When writing:

~~~java
new NotificationEnvelope(
        "evt-42",
        new EmailPayload("a@example.com", "Hello")
)
~~~

When reading, Jackson knows it must create `NotificationEnvelope`, yet the `payload` field is only declared as `NotificationPayload`. Without polymorphism configuration, an error typically occurs because an interface/abstract class cannot be instantiated, or subtype information is lost.

A brittle workaround is always reading into `Map<String, Object>` and manually casting:

~~~java
Object value = redis.opsForValue().get("notification:evt-42");
Map<?, ?> data = (Map<?, ?>) value;
~~~

This fails to restore `EmailPayload`, loses Java type checking, and forces every caller to interpret the Map structure manually. Choose an explicit cache data contract instead.

## 4. Safer Polymorphism with Stable Type Names (`Id.NAME`)

It is usually best to represent subtypes using a **predefined domain name**, such as `email` and `sms`, instead of recording full JVM class names.

Example declared in a single Java file:

~~~java
package com.example.app.cache;

import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

public final class NotificationTypes {
    private NotificationTypes() {}

    @JsonTypeInfo(
            use = JsonTypeInfo.Id.NAME,
            include = JsonTypeInfo.As.PROPERTY,
            property = "kind")
    @JsonSubTypes({
            @JsonSubTypes.Type(value = EmailPayload.class, name = "email"),
            @JsonSubTypes.Type(value = SmsPayload.class, name = "sms")
    })
    public sealed interface NotificationPayload
            permits EmailPayload, SmsPayload {}

    public record EmailPayload(
            String address,
            String subject) implements NotificationPayload {}

    public record SmsPayload(
            String phoneNumber,
            String message) implements NotificationPayload {}

    public record NotificationEnvelope(
            String eventId,
            NotificationPayload payload) {}
}
~~~

When the `payload` field is serialized according to its declared interface type, the JSON can take the form:

~~~json
{
  "eventId": "evt-42",
  "payload": {
    "kind": "email",
    "address": "a@example.com",
    "subject": "Hello"
  }
}
~~~

When reading, Jackson maps `kind=email` to `EmailPayload` and `kind=sms` to `SmsPayload`, via the subtype list registered by the application.

~~~text
JSON field "kind"
       |
       v
   [email] --------> EmailPayload
   [sms] ----------> SmsPayload
   [unknown] ------> error or designed compatibility policy
~~~

This is an **explicitly known list of subtypes**. A payload can request `kind=email`, yet cannot arbitrarily specify a new class name merely by altering the `kind` string unless the application has registered a matching mapping.

### 4.1. Combining with a Serializer Having a Concrete Root Type

~~~java
import com.example.app.cache.NotificationTypes.NotificationEnvelope;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;

Jackson2JsonRedisSerializer<NotificationEnvelope> serializer =
        new Jackson2JsonRedisSerializer<>(
                objectMapper, NotificationEnvelope.class);
~~~

Because `NotificationEnvelope` holds `NotificationPayload`, annotations on the interface help Jackson determine the subtype. When using `RedisTemplate<String, NotificationEnvelope>`, assign this serializer as the value serializer.

Two decisions stay separate:

- **Root class:** `NotificationEnvelope.class` is determined by the template/serializer.
- **Subtype:** `EmailPayload` or `SmsPayload` is determined by `kind` and the registered subtype mapping.

### 4.2. Why Are Aliases Better Than Class Names?

Suppose a class is moved and renamed from:

~~~text
com.example.app.notification.EmailPayload
~~~

to:

~~~text
com.example.app.cache.EmailNotificationPayload
~~~

If the payload stores `"kind":"email"`, the application can keep the `email` alias and update the mapping without modifying old data. If the payload stored the JVM class name directly, changing packages or renaming the class could break deserialization.

Aliases also make JSON easier to understand and decouple the storage schema from source-code organization details.

### 4.3. Variant: Registering Subtypes on `ObjectMapper`

Instead of `@JsonSubTypes`, you can register subtype names in Jackson configuration:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.jsontype.NamedType;

ObjectMapper mapper = new ObjectMapper();
mapper.registerSubtypes(
        new NamedType(NotificationTypes.EmailPayload.class, "email"),
        new NamedType(NotificationTypes.SmsPayload.class, "sms"));
~~~

With this approach, you still need `@JsonTypeInfo(use = Id.NAME, ...)` on the base type, a corresponding mix-in, or an equivalent typing rule. Calling `registerSubtypes` alone **does not automatically enable** discriminator emission/reading everywhere.

Whenever the subtype list changes, treat it as a cache contract change and test reading data stored by previous versions.

## 5. Jackson Type Identifier Forms

Jackson offers multiple ways to describe types in JSON when configured for polymorphism.

| `JsonTypeInfo.Id` | Type Identifier Content | Characteristics |
|---|---|---|
| `NAME` | Application-defined alias, e.g., `email` | Easy to control, relatively resilient to refactoring |
| `CLASS` | Fully qualified Java class name | Flexible yet coupled to packages/classes, larger risk surface |
| `MINIMAL_CLASS` | Class name relative to base type | Still coupled to package structure |
| `DEDUCTION` | Jackson infers subtype from property combinations | Easily ambiguous when subtypes share similar shapes |
| `NONE` | No type identifier included | Suitable only when target type is determined another way |

Alongside `Id`, how metadata is placed into JSON also matters:

- `As.PROPERTY`: places a property such as `kind` or `@class` inside the object.
- `As.WRAPPER_OBJECT`: uses an enclosing object with a key representing the type.
- `As.WRAPPER_ARRAY`: uses a two-element array of type identifier and payload.
- `As.EXTERNAL_PROPERTY`: places the discriminator outside the typed property in suitable contexts.

The actual JSON format varies by annotations, default typing, value kind, declared types, and Jackson version. Never assume every class is always written with `@class`.

## 6. `GenericJackson2JsonRedisSerializer` and Class Metadata

Spring Data Redis offers two common Jackson JSON options on branches supporting Jackson 2:

| Serializer | Typical Restoration Contract | Metadata Needs |
|---|---|---|
| `Jackson2JsonRedisSerializer<T>` | Known concrete target type `T` | Root metadata unnecessary; polymorphic fields still need rules |
| `GenericJackson2JsonRedisSerializer` | Values treated as `Object`/dynamic types | Typically requires type metadata to recover concrete classes |
| `StringRedisSerializer` | UTF-8 string | Does not build Java DTOs from JSON |
| `JdkSerializationRedisSerializer` | Java native object serialization | Carries class info via Java serialization; different security and compatibility risks than JSON |

With `RedisTemplate<String, Object>`, an application may store multiple classes across many keys. A generic JSON serializer typically uses type information to know which class to reconstruct.

Example of a payload carrying a class identifier:

~~~json
{
  "@class": "com.example.app.cache.EmailCacheValue",
  "address": "a@example.com",
  "subject": "Hello"
}
~~~

The `@class` marker only illustrates one common **class metadata convention**. Property name, placement of the type identifier, and whether a specific value carries metadata depend on Jackson configuration. Collection/array types may use different type metadata forms than regular beans.

### 6.1. Schema and Security Issues

Recording types as class names has two consequences:

1. **Source-code coupling:** changing packages, class names, constructors, or schemas can make old payloads unreadable.
2. **Controlling instantiated classes:** if a deserializer accepts arbitrary type identifiers, whoever can write payloads can influence code to load/instantiate unexpected Java types.

Redis sitting on an internal network is not a reason to unconditionally trust every payload. Data can arrive from another service, an operational tool, an old snapshot, a shared environment, an ACL misconfiguration, or a compromised component.

### 6.2. Default Typing Differs from Polymorphic Annotations

Jackson **default typing** automatically adds type metadata across broad object categories based on a global policy, typically targeting `Object`, interfaces, or non-final types.

This differs from placing `@JsonTypeInfo` on a specific interface:

~~~text
@JsonTypeInfo on NotificationPayload
    -> narrow scope, subtypes defined per model

ObjectMapper default typing
    -> broader scope across many values/types
    -> requires auditing policies for allowed types
~~~

Do not enable default typing on an application-wide `ObjectMapper` just to fix one Redis cache missing metadata. A shared mapper may serve HTTP APIs, logging, or other serializers, spreading the impact outside Redis.

## 7. `PolymorphicTypeValidator`: Restricting Allowed Types on Deserialization

When using Jackson 2 with class-based polymorphic type identifiers, `PolymorphicTypeValidator` participates in deciding whether a subtype is accepted. A common implementation is `BasicPolymorphicTypeValidator`.

Conceptual flow:

~~~text
Redis payload
     |
     v
Decode JSON
     |
     v
Is there a type id to restore?
     |
     +-- No ---> use static target type / known format
     |
     +-- Yes --> Resolve candidate subtype
                         |
                         v
                PolymorphicTypeValidator
                         |
                 +-------+--------+
                 |                |
               Allow            Deny
                 |                |
                 v                v
         Bind JSON to DTO    Deserialization error
~~~

The validator may evaluate base types, subtype names, and/or resolved subtypes depending on policy and how Jackson invokes it. **The allowlist must reflect types the application genuinely permits restoring**, not merely "anything on the classpath."

### 7.1. Example Restricting to a Dedicated DTO Package

The example below illustrates combining default typing with a validator when a system **must** use dynamic JSON class metadata. These APIs use Jackson 2 and Spring Data Redis 3.x.

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.jsontype.BasicPolymorphicTypeValidator;
import com.fasterxml.jackson.databind.jsontype.PolymorphicTypeValidator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class RestrictedJsonRedisConfig {

    @Bean("restrictedJsonRedisTemplate")
    RedisTemplate<String, Object> restrictedJsonRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        PolymorphicTypeValidator validator =
                BasicPolymorphicTypeValidator.builder()
                        .allowIfSubType("com.example.app.cache.dto.")
                        .build();

        ObjectMapper mapper = new ObjectMapper();

        mapper.activateDefaultTypingAsProperty(
                validator,
                ObjectMapper.DefaultTyping.NON_FINAL,
                "@class");

        GenericJackson2JsonRedisSerializer valueSerializer =
                new GenericJackson2JsonRedisSerializer(mapper);

        RedisTemplate<String, Object> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(valueSerializer);
        template.setHashKeySerializer(new StringRedisSerializer());
        template.setHashValueSerializer(valueSerializer);

        return template;
    }
}
~~~

**Meaning of the configuration:**

- `allowIfSubType("com.example.app.cache.dto.")` permits only subtypes whose names fall under that designated DTO namespace when the validator is asked to check a subtype. Pick a **specific** prefix ending with a package dot, containing only models safe for Redis data.
- `DefaultTyping.NON_FINAL` specifies the type scope receiving default type metadata per Jackson's policy; it does not guarantee every final class, collection, or root value shares the exact same metadata layout.
- `"@class"` is the property name for type metadata under this setting, not a business field.
- `GenericJackson2JsonRedisSerializer` uses the configured mapper to write/read JSON.
- The template configures both value and hash-value serializers; configuring the value serializer alone does not make Hashes adopt the same strategy automatically.

**Important limitations of the example:** a prefix-based validator only restricts subtypes to that namespace, yet does not guarantee every class inside that package is safe. Moreover, payloads with final root types, JDK container types, or special field types may not round-trip under `NON_FINAL` and such a narrow allowlist. Choose the default typing scope for your **actual DTO set**, register needed Jackson modules, and test restoring all supported shapes before deploying. Whenever design permits, **static typed serializers + `Id.NAME` aliases are easier to maintain**.

### 7.2. Exact Subtype Allowlisting

If only a few subtypes are allowed, prefer an explicit set, or use `@JsonSubTypes`/`registerSubtypes` with `Id.NAME` aliases.

A validator can restrict by exact class/hierarchy:

~~~java
BasicPolymorphicTypeValidator validator =
        BasicPolymorphicTypeValidator.builder()
                .allowIfSubType(EmailCacheValue.class)
                .allowIfSubType(SmsCacheValue.class)
                .build();
~~~

This is tighter than a broad package prefix, yet you still must consider the full object graph: a payload may hold collections or nested subtypes; under class-based default typing, those types may also need permission if Jackson requests metadata for them. Inspect actual supported data and avoid widening the allowlist with an overly broad prefix just to make errors go away.

### 7.3. Configurations to Avoid

Avoid choices such as:

~~~java
// Illustrating an overly broad policy: do not use for untrusted payloads.
BasicPolymorphicTypeValidator.builder()
        .allowIfSubType(Object.class)
        .build();
~~~

Or allowing every class name with an equivalently permissive validator. Such settings effectively defeat subtype validation.

In particular, never treat enabling a "convenient" default typing setting on `ObjectMapper` as a safe measure. Clearly identify which Java data types the application needs to restore, then choose a typing mechanism matching exactly that scope.

## 8. Type Restriction Is Not Just `PolymorphicTypeValidator`

Multiple independent layers of control each solve a different problem:

| Control Layer | What It Solves | What It Does Not Solve |
|---|---|---|
| Serializer `<T>` with concrete `T` | Fixes the root target type | Inner `Object`/interface fields unless configured |
| `@JsonTypeInfo(Id.NAME)` + explicit subtype set | Maps only aliases to registered subtypes | Business validation errors or oversized JSON |
| `PolymorphicTypeValidator` | Restricts class-based polymorphic resolution | Redis access rights, payload size, business validity |
| DTO/schema validator | Checks required fields, numeric bounds, valid states | Mitigating risks from overly broad class metadata |
| Redis ACL/TLS and network segmentation | Limits who can connect/write data | Turning syntactically valid payloads into valid business state |
| TTL and cache versioning | Bounds lifetimes, supports migrations | Blocking malicious subtypes |
| Payload size limits | Reduces risk of giant JSON or deep recursion | Replacing subtype allowlists |

If using **Java native serialization**, filter mechanisms and risks differ from Jackson JSON. Jackson's `PolymorphicTypeValidator` **does not filter** `JdkSerializationRedisSerializer` payloads. For untrusted data, avoid Java native serialization or apply Java serialization filtering policies designed properly for the JVM mechanism.

### 8.1. Do Not Expose Class Metadata as a Public API

Never allow HTTP clients to supply raw Java class names that the server passes verbatim into JSON type metadata or *reflection*. If an API lets users pick a notification type, accept finite domain values like `email` and `sms`, validate the input, and map them to permitted DTOs.

### 8.2. Do Not Use `Object.class` as a Default Escape Hatch

Declaring everything as `Object` forces serializers to guess or carry type metadata everywhere. If an application genuinely needs only three cache schemas, consider three specifically typed templates or an envelope with an explicit discriminator.

### 8.3. Do Not Rely on Package Names as the Sole Security Boundary

Restricting to `com.example.app.cache.dto.` only works if that namespace is tightly governed and holds no classes with undesirable behavior during instantiation/restoration. For sensitive data, exact subtype lists and immutable, data-only DTOs are far easier to verify.

## 9. Relationship Between RedisTemplate Serializers and Redis Structures

Spring Data Redis supports serializers at distinct positions:

~~~text
RedisTemplate<K,V>
    |
    +-- keySerializer        --> Redis key
    +-- valueSerializer      --> values for opsForValue/...
    +-- hashKeySerializer    --> Redis Hash field
    +-- hashValueSerializer  --> Redis Hash value
~~~

Example:

~~~java
RedisTemplate<String, ProductCache> template = new RedisTemplate<>();
template.setConnectionFactory(connectionFactory);

template.setKeySerializer(new StringRedisSerializer());
template.setValueSerializer(productJsonSerializer);

template.setHashKeySerializer(new StringRedisSerializer());
template.setHashValueSerializer(productJsonSerializer);
~~~

Using `StringRedisTemplate` with string values does not automatically turn JSON into `ProductCache`. Conversely, when using `RedisTemplate` with a JSON serializer, `TYPE key` still returns `string` because Redis treats the JSON value as a byte sequence.

With `opsForHash()`, the "type" of a Redis Hash field is still just byte values encoded by the hash-value serializer. Do not confuse DTO annotations with Redis automatically splitting Java properties into Hash fields.

### 9.1. Avoid Cross-Reading Keys with Incompatible Serializers

For instance, service A writes:

~~~text
key = cache:product:42
serializer = Jackson2JsonRedisSerializer<ProductCache>
~~~

Yet service B reads the same key with:

~~~text
serializer = GenericJackson2JsonRedisSerializer
~~~

Service B may not know the target type because A's JSON lacks the class metadata B expects. Results can be a `Map`, a missing type id error, or an unexpected object depending on serializer settings.

For keys shared across services, define a **data contract** covering key naming, serializer, encoding, schema, type identifiers, versioning, TTL, and legacy data handling. Do not expect two different JSON serializers to automatically understand each other.

### 9.2. Risks When Switching Serializers

If `JdkSerializationRedisSerializer` was previously used and you switch to a JSON serializer, existing binary data in Redis will fail JSON parsing. Switching between two JSON serializers can also alter type id formats.

An appropriate migration approach depends on the data's role:

- **TTL-bounded caches:** change the key prefix (e.g., `product-cache:v2:42`) and let old caches expire.
- **Clearable caches:** invalidate selectively by scope and let the application repopulate from the primary source.
- **Persistent/critical data:** use a versioned conversion plan, verifying reads before deleting legacy data.
- **Multi-version rolling deployments:** verify old and new versions can read coexisting data, or separate namespaces during transition.

## 10. Versioning and Forward/Backward Compatibility of Polymorphic Payloads

Stable type metadata alone does not guarantee old data stays readable. Field structures can also evolve.

Suppose the initial format is:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-42",
  "payload": {
    "kind": "email",
    "address": "a@example.com"
  }
}
~~~

A new version adds `subject` and renames `address` to `toAddress`. When reading legacy data, decide:

- Should missing fields be accepted with sensible defaults?
- Is `@JsonAlias("address")` needed to accept the old field name?
- Should unknown new fields be ignored or rejected?
- Is conversion from schema version 1 to 2 needed?
- Should legacy subtypes remain permitted during the rollout window?

**Do not change allowlists by expanding them indefinitely** just to preserve compatibility. It is better to maintain a time-bounded legacy subtype list or perform deliberate migrations.

### 10.1. Distinguishing `schemaVersion` from `kind`

These two fields mean different things:

~~~json
{
  "schemaVersion": 2,
  "payload": {
    "kind": "sms",
    "phoneNumber": "+84...",
    "message": "Your code"
  }
}
~~~

- `schemaVersion` indicates the data contract version.
- `kind` indicates the polymorphic variant to reconstruct.

Never overload a single `type` field to carry both schema version and Java class name; mixing responsibilities makes payloads difficult to migrate.

### 10.2. Renaming Classes and Refactoring Packages

With `Id.NAME` and stable aliases, renaming a Java class usually requires only updating the subtype mapping. With `Id.CLASS`, old payloads directly reference the old class name, so reading data after refactoring can throw `ClassNotFoundException`, `InvalidTypeIdException`, or a Spring Data Redis wrapped exception.

When Redis is only a cache, changing the namespace/key version can be simpler than keeping aliases compatible with old class names. When Redis holds data that must be preserved, explicitly include a conversion step.

## 11. Handling Deserialization Errors at Runtime

Common runtime situations:

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| Cannot instantiate interface | Missing discriminator or subtype mapping | Declare `@JsonTypeInfo` and valid subtypes |
| `InvalidTypeIdException` | Missing type id, invalid alias, disallowed class | Check schema/typing/validator; do not widen allowlist carelessly |
| `ClassNotFoundException` reading cache | Metadata references old class after refactor | Migration or cache versioning |
| Deserialized as `LinkedHashMap` instead of DTO | Target is `Object` without metadata identifying concrete type | Use typed serializer or explicit discriminator |
| Failed to parse JSON | Writer/reader serializer mismatch, corrupted value | Verify serializers and key provenance |
| `SerializationException` in Spring Data Redis | Underlying serialize/deserialize error wrapped by Spring | Inspect root cause, key/schema/serializer |
| Class type id rejected | Validator does not allow the subtype | Verify whether the subtype is actually permitted by contract |
| Deserialized successfully yet business data invalid | Missing validation or incompatible schema | Validate invariants, fields, versions, and size limits |

### 11.1. Strategy Based on Data Role

If Redis is a **temporary cache** and another database is the source of truth, a malformed value can be treated as a cache miss, evicted or re-versioned per policy, and reloaded from the primary source. Still, be cautious with cache deletion under concurrency: another request may have just written a valid value to that key.

If Redis is an **authoritative data source**, never catch all JSON errors and return `null` as though the key did not exist. Emit error signals, preserve needed diagnostic evidence, and recover data via an appropriate procedure.

A helpful rule of thumb:

~~~text
Optional cache:
  deserialization error -> metric/log -> fallback -> rebuild cache

Critical data:
  deserialization error -> controlled error reporting
                        -> identify cause and version
                        -> verifiable migration/recovery
~~~

### 11.2. Do Not Log Entire Untrusted Payloads

Type id errors can contain personal data or externally supplied content. Logs should record redacted key names, serializer/schema version, error codes, and exception types; never log entire JSON blobs, tokens, emails, or sensitive fields by default.

## 12. Choosing a Strategy for a Real-World System

Suppose an application manages three data groups:

~~~text
product-cache:<id>               => ProductCache
notification-cache:<event-id>     => NotificationEnvelope
legacy-mixed-cache:<key>          => Object (multiple Java types)
~~~

Decisions can be made per group:

| Data Group | Recommended Strategy | Rationale |
|---|---|---|
| ProductCache with single DTO | `Jackson2JsonRedisSerializer<ProductCache>` | No root class metadata needed |
| NotificationEnvelope holding an interface | Typed serializer + `@JsonTypeInfo(Id.NAME)` and subtype mapping | Explicit polymorphism, stable aliases |
| Legacy mixed cache needing multiple classes | Generic JSON serializer + narrow allowlist, migration plan | Controlled backward compatibility |
| Caches holding high volumes of simple strings | `StringRedisTemplate` | Avoids unnecessary type metadata |
| Untrusted data containing arbitrary JSON | Parse into server-controlled DTO/schema | Prevent input from choosing arbitrary Java classes |
| Legacy Java native serialization data | Analyze/filter/migrate separately | Not governed by Jackson validators |

Maintainable architectures usually constrain the scope of `Object` and use data-only, immutable DTOs where appropriate, with distinct schemas per key namespace.

### 12.1. Decision Tree

~~~mermaid
flowchart TD
    A[Read JSON from Redis] --> B{Know concrete root type upfront?}
    B -->|Yes| C[Typed JSON serializer]
    B -->|No| D{Can define schema/envelope?}
    D -->|Yes| E[Define DTO and NAME discriminator]
    D -->|No, legacy compatibility needed| F[Controlled generic JSON]
    C --> G{Has interface/abstract fields?}
    G -->|Yes| E
    G -->|No| H[Deserialize into known DTO]
    E --> I[Register allowed subtypes and aliases]
    F --> J[PolymorphicTypeValidator and narrow subtype list]
    I --> K[Validate schema/version and data]
    J --> K
    H --> K
    K --> L[Application uses object]
~~~

The "Controlled generic JSON" branch should be treated as an exception when data is genuinely dynamic or legacy data must be supported. Do not pick it merely to write fewer generic type declarations.

## 13. Nuanced Scenarios Worth Understanding Deeply

### 13.1. A Field Declared as `Object` Inside a DTO

~~~java
public record AuditEnvelope(String eventId, Object payload) {}
~~~

Even though the root serializer knows `AuditEnvelope.class`, Jackson still cannot tell which DTO `payload` should become without extra info.

You can replace `Object` with a sealed interface with explicit subtypes, read into a JSON tree (`JsonNode`) and parse based on a trusted discriminator, or design a versioned envelope. Do not turn on default typing for all classes just because one field was declared too broadly.

### 13.2. List of Subtypes

~~~java
public record BatchEnvelope(
        String batchId,
        java.util.List<NotificationTypes.NotificationPayload> items) {}
~~~

Even though `List` identifies the collection, each element still must be restored as `EmailPayload` or `SmsPayload`. Annotations on the interface identify the subtype for each element; do not assume List metadata alone distinguishes individual items.

### 13.3. Generic `List<T>` and Type Erasure

If you call `ObjectMapper.readValue(json, List.class)` directly, JSON object elements are typically read as `Map` because `List.class` does not carry `T`.

With JSON outside `RedisTemplate`, specify a `JavaType`:

~~~java
var type = objectMapper.getTypeFactory()
        .constructCollectionType(
                java.util.List.class,
                ProductCache.class);

java.util.List<ProductCache> products =
        objectMapper.readValue(jsonBytes, type);
~~~

Or use `TypeReference<List<ProductCache>>`. When configuring serializers in Spring Data Redis, ensure the target type/`JavaType` is preserved; passing only `List.class` is insufficient.

### 13.4. Date/Time Fields and Jackson Modules

DTOs containing `Instant`, `LocalDateTime`, or Java Time types may need `JavaTimeModule` or version-appropriate mapper configuration. Date parsing errors are **not necessarily subtype errors**. Never enable default typing to "fix" a serializer missing date-type support.

### 13.5. Null Values and Cache Abstraction

Spring Cache may represent null cache entries using its own serializer or wrapper. A manually constructed `ObjectMapper` might not be configured to understand the null marker expected by default serializers.

When using `GenericJackson2JsonRedisSerializer` with a custom mapper and Spring Cache integration, check the null-value serializer registration mechanism for your exact Spring Data Redis version. Never assume JSON `null`, an absent key, and a null-representing wrapper behave identically.

## 14. Illustrating How Invalid Data Should Be Rejected

Suppose the contract only supports:

~~~json
{"kind":"email","address":"a@example.com","subject":"Hello"}
~~~

and:

~~~json
{"kind":"sms","phoneNumber":"+84123456789","message":"Hi"}
~~~

If receiving:

~~~json
{"kind":"internal-job","command":"..."}
~~~

with `Id.NAME`, the application **must not attempt to look up a class named `internal-job`**. If the alias is unregistered, the deserializer should reject it or invoke a deliberate unknown-type handler; never resolve it via arbitrary reflection.

Similarly, if a class-based payload attempts to request:

~~~json
{
  "@class": "com.example.unknown.UnapprovedType",
  "data": "..."
}
~~~

a properly configured validator must reject that subtype. What you want is a clear read failure, not instantiating an arbitrary Java object and hoping business validation catches it later.

## 15. Common Misconceptions

### "Redis already knows the type, so JSON type info isn't needed"

Redis knows **Redis** data types (String/Hash/...), not Java DTOs or subtypes. `TYPE key` does not replace Java class metadata.

### "Every JSON payload needs `@class`"

False. With static target-type serializers and DTOs containing no polymorphic fields, `@class` is unnecessary. Even when polymorphism is needed, `Id.NAME` and finite aliases are usually better.

### "Using `GenericJackson2JsonRedisSerializer` is automatically safe"

No. Dynamic type resolution comes with responsibility to control allowed types and data sources. Mapper/validator configuration must fit your schema and Jackson version.

### "`@JsonSubTypes` allows every subtype of the interface"

No. The annotation declares specific subtypes; this is advantageous when the contract must accept only a finite set. Adding a new subtype requires intentionally updating the mapping or registration rules.

### "Allowlisting a class package is sufficient for all data"

No. A package prefix does not replace auditing classes for safety, schema validation, input checks, and payload size limits. Critical systems should usually use explicit subtype lists.

### "Changing a class's package does not affect Redis"

It can affect Redis if JSON stores fully qualified class names. With `Id.NAME`, keeping aliases stable reduces the impact.

### "If cache reads fail, enable validator permission for `Object.class`"

Widening object instantiation permissions to the extreme to work around a compatibility bug is a dangerous choice. Find the root cause—missing type id, wrong serializer, or schema change—and fix it within the supported data boundary.

## 16. Summary Through a Design Example

A clean design for a polymorphic Redis cache might look like:

~~~text
Key:
    notification:v2:evt-42

Serializer:
    Jackson2JsonRedisSerializer<NotificationEnvelope>

Payload:
    {
      "schemaVersion": 2,
      "eventId": "evt-42",
      "payload": {
        "kind": "email",
        "address": "a@example.com",
        "subject": "Hello"
      }
    }

Restoration:
    1. Read JSON from Redis.
    2. Root is known to be NotificationEnvelope.
    3. Read payload.kind.
    4. Select EmailPayload from declared mapping.
    5. Validate fields and schema version.
    6. Return properly typed Java object.
~~~

If requirements truly force reading heterogeneous Java types with no shared schema, narrow dynamic typing scope, enforce `PolymorphicTypeValidator`, restrict Redis write sources, and plan to migrate data toward structured schemas.

**Core principle:** only allow payloads to select among **application-approved data variants**, rather than letting payloads decide whichever Java class gets instantiated. Static target types, explicit subtype aliases, and bounded allowlists enable Spring Data Redis to restore data reliably while preserving contracts and trust boundaries as the application evolves.
