# Distinguishing Java Serialization from JSON Conversion

## 1. Why Do We Need to Distinguish These Two Mechanisms?

In a Spring Boot application, data often needs to be converted for storage, network transmission, or exchange with other systems. Two common approaches are **Java Object Serialization** and **JSON serialization/deserialization**. Both may be broadly referred to as "serialization", yet they produce different data formats, serve different goals, and require different metadata when compiled into a GraalVM Native Image.

For example, an `order-service` has an `OrderSnapshot` object for temporarily storing state, as well as `OrderRequest` and `OrderResponse` used as REST API payloads.

- Java serialization converts a Java object graph into a byte stream according to the Java serialization protocol, typically via `ObjectOutputStream` and `ObjectInputStream`.
- JSON converts data into text following the JSON object/array/value structure, typically using Jackson in Spring Boot.

When running on the JVM, both mechanisms can work if configured properly. With **GraalVM Native Image**, Java serialization requires serialization metadata for the types in the object graph; JSON binding typically requires reflection/binding metadata for DTOs that the JSON library accesses dynamically. Registering the wrong kind of hint will not resolve the error.

After this lesson, you will be able to:

- Explain the differences in format, portability, versioning, and object graphs.
- Choose between Java serialization and JSON based on the application's purpose.
- Write examples for converting data using `ObjectOutputStream` and Jackson `ObjectMapper`.
- Understand the risks of deserializing untrusted data.
- Configure appropriate metadata for each mechanism when building a Spring Boot Native Image.

## 2. What Is Java Object Serialization?

Java Object Serialization is Java's mechanism for writing an object graph into a sequence of bytes and reconstructing the object graph from that byte sequence. The core APIs are located in the `java.io` package:

- `Serializable`: a marker interface for classes that can be serialized using the default mechanism.
- `ObjectOutputStream`: writes objects to an `OutputStream`.
- `ObjectInputStream`: reads and reconstructs objects from an `InputStream`.
- `serialVersionUID`: the version identifier of a class in the serialization protocol.

### 2.1. Declaring a Serializable Class

```java
package com.example.orders.snapshot;

import java.io.Serial;
import java.io.Serializable;

public final class OrderSnapshot implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    private final String orderId;
    private final long totalAmount;
    private transient String temporaryAccessToken;

    public OrderSnapshot(String orderId, long totalAmount) {
        this.orderId = orderId;
        this.totalAmount = totalAmount;
    }

    public String getOrderId() {
        return orderId;
    }

    public long getTotalAmount() {
        return totalAmount;
    }
}
```

`Serializable` does not require a class to have getters/setters or a no-arg constructor. By default, Java serialization persists the state of non-`static` and non-`transient` fields according to the rules of the serialization protocol.

A few key points to remember:

- `static` fields belong to the class and therefore are not saved as per-object state.
- `transient` marks a field not to be written by the default mechanism. During deserialization, that field receives its default value unless custom serialization restores it.
- `serialVersionUID` helps verify compatibility between the writing class and the reading class. If the UID does not match, an `InvalidClassException` may be thrown.
- If an object references other objects in the graph, those related types must also satisfy serialization rules; otherwise, writing may throw `NotSerializableException`.

### 2.2. Writing and Reading Objects

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;

OrderSnapshot snapshot = new OrderSnapshot("ORD-100", 250_000L);

byte[] bytes;
try (ByteArrayOutputStream buffer = new ByteArrayOutputStream();
     ObjectOutputStream output = new ObjectOutputStream(buffer)) {
    output.writeObject(snapshot);
    output.flush();
    bytes = buffer.toByteArray();
}

OrderSnapshot restored;
try (ByteArrayInputStream buffer = new ByteArrayInputStream(bytes);
     ObjectInputStream input = new ObjectInputStream(buffer)) {
    restored = (OrderSnapshot) input.readObject();
}

System.out.println(restored.getOrderId());
```

The result is a byte stream containing class information and object state according to the Java serialization protocol. It is not JSON and is not intended to be a language-independent exchange format.

### 2.3. Java Serialization Preserves the Object Graph

Java serialization can store reference relationships, shared objects, and reference cycles within the graph. For example, if two fields point to the same object, when read back, they can continue pointing to the same instance in the restored graph.

This differs from standard JSON: JSON represents a tree-like data structure composed of objects, arrays, and primitive values. JSON does not natively represent Java object identity or reference cycles. If an object graph has cycles, JSON libraries typically require special configuration, identity references, or conversion DTOs to avoid recursion errors.

## 3. What Is JSON and How Does Spring Boot Convert JSON?

JSON (*JavaScript Object Notation*) is a language-independent text format that represents data using objects, arrays, strings, numbers, booleans, and `null`. In Spring Boot, Jackson is typically used as the JSON mapper through HTTP message converters.

JSON describes **data**, not a complete Java object. When converting JSON back to Java, the mapper needs to know the target type and how to map fields/properties, constructors, or creators.

DTOs used for JSON do not need to implement `Serializable`. Jackson maps properties based on mapper configuration and metadata; it does not write objects using the Java serialization protocol.

### 3.1. DTOs Used for REST APIs

```java
package com.example.orders.api;

public record OrderRequest(String productCode, int quantity) {
}
```

```java
package com.example.orders.api;

public record OrderResponse(String orderId, long totalAmount) {
}
```

A Spring MVC controller can accept and return DTOs:

```java
package com.example.orders.api;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    @PostMapping
    OrderResponse create(@RequestBody OrderRequest request) {
        return new OrderResponse("ORD-100", request.quantity() * 125_000L);
    }
}
```

With standard Spring Boot configuration, Jackson is integrated via HTTP message converters. The controller does not need to call `ObjectOutputStream` or manually convert DTOs to bytes.

### 3.2. Direct Conversion Using Jackson `ObjectMapper`

When you need to convert JSON outside an HTTP controller, you can use `ObjectMapper`:

```java
package com.example.orders.api;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

public class OrderJsonCodec {

    private final ObjectMapper objectMapper;

    public OrderJsonCodec(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public String write(OrderResponse response) throws JsonProcessingException {
        return objectMapper.writeValueAsString(response);
    }

    public OrderResponse read(String json) throws JsonProcessingException {
        return objectMapper.readValue(json, OrderResponse.class);
    }
}
```

In Spring Boot, you should inject the application-configured `ObjectMapper` instead of arbitrarily creating `new ObjectMapper()` everywhere. The auto-configured mapper may already include modules, naming strategies, date/time support, and custom serializers/deserializers used by the application.

The resulting JSON is in text format, for example:

```json
{
  "orderId": "ORD-100",
  "totalAmount": 250000
}
```

Systems written in Java, JavaScript, Go, or Python can all read this data if they follow the same JSON structure and schema conventions.

## 4. Comparing Java Serialization and JSON

| Criterion | Java Object Serialization | JSON serialization/deserialization |
|---|---|---|
| Format | Binary stream following the Java protocol | JSON text |
| Goal | Persist/restore Java object graphs | Exchange data across different systems and languages |
| Java class coupling | High; data is tied to classes and the serialization contract | Lower; tied to data structure/schema |
| Object graph and identity | Supports shared references and cycles | Standard JSON is a tree; identity/cycles require custom conventions |
| Versioning | Uses `serialVersionUID` and serialization compatibility rules | Typically managed via schemas, optional fields, API versions, and unknown field rules |
| Fields | Saves field state per serialization rules, excluding `static`/`transient` and custom behavior | Maps properties per mapper configuration, annotations, and creators |
| Multi-language | Not a suitable exchange format for non-Java clients | Widely supported and language-independent |
| Human readability | Difficult, as it is a binary stream | Easier to inspect and debug |
| Key risks | Deserializing untrusted data can trigger gadget chains or dangerous behavior | Unsafe polymorphic typing configuration, oversized payloads, parser/resource exhaustion, and missing validation |
| Native Image hints | Serialization metadata for types in the object graph | Reflection/binding metadata for types Jackson needs to access; resource hints if reading JSON files from the classpath |

There is no universal rule that Java serialization is always faster or JSON is always smaller. Results depend on object graph size, data structure, serializer, compression settings, storage method, and workload. Benchmark if performance is a deciding factor.

## 5. Versioning and Data Compatibility

### 5.1. `serialVersionUID` in Java Serialization

When a class implements `Serializable`, Java uses `serialVersionUID` to identify the serialization version. If a stream was written by a class version with a different UID from the reading class, `ObjectInputStream` may throw `InvalidClassException`.

Declaring an explicit UID avoids unexpected changes in compiler-generated UIDs caused by certain class modifications. However, **keeping the UID unchanged does not automatically guarantee semantic compatibility**. If you change a field's meaning, data type, or how state is interpreted, the application still needs a migration strategy for old data.

For data that must be stored long-term or shared across multiple service versions, you should test the following scenarios:

- New class reading an old stream.
- Old class reading a new stream (if the system must support this direction).
- Fields added, removed, or renamed.
- Types within the object graph changed.
- Custom `readObject`, `writeObject`, `readResolve`, or `writeReplace` changed.

If data has a long lifespan, consider a format with explicit schema/versioning instead of relying entirely on Java class structure.

### 5.2. JSON Versioning

JSON does not provide built-in schemas or versioning. The application needs to design a contract, for example:

```json
{
  "schemaVersion": 2,
  "orderId": "ORD-100",
  "totalAmount": 250000,
  "currency": "VND"
}
```

When adding optional fields, older clients can ignore them if the mapper and contract allow it. When changing a field's type, changing its meaning, or removing a field still in use, an API compatibility and migration plan is needed.

Some practical rules:

- Use dedicated DTOs for APIs instead of serializing internal entities directly.
- Define required/optional fields and default values.
- Specify how unknown fields are handled to avoid accidentally losing data or masking contract errors.
- Use OpenAPI/JSON Schema or equivalent contract documentation when multiple clients integrate together.
- Test payloads from older client versions and payloads produced by newer server versions.

## 6. Security: Be Especially Careful with Java Deserialization

### 6.1. Do Not Deserialize Untrusted Data

`ObjectInputStream.readObject()` can instantiate objects and trigger logic during deserialization. Some libraries contain gadget chains that allow crafted serialized data to cause dangerous behavior in an application.

You should not accept raw Java serialization bytes directly from untrusted clients, should not expose public endpoints that call `readObject()` on arbitrary data, and should not treat `Serializable` as a security boundary.

If you must read serialized data from a controlled source, use `ObjectInputFilter` to restrict allowed classes, graph size, depth, and reference count appropriately for your use case. A minimal example for an object graph containing only `OrderSnapshot` and `String`:

```java
package com.example.orders.snapshot;

import java.io.IOException;
import java.io.InputStream;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

public final class OrderSnapshotReader {

    public OrderSnapshot read(InputStream source)
            throws IOException, ClassNotFoundException {
        try (ObjectInputStream input = new ObjectInputStream(source)) {
            input.setObjectInputFilter(info -> {
                if (info.depth() > 10 || info.references() > 100) {
                    return ObjectInputFilter.Status.REJECTED;
                }

                Class<?> type = info.serialClass();
                if (type == null) {
                    return ObjectInputFilter.Status.UNDECIDED;
                }

                if (type == OrderSnapshot.class || type == String.class) {
                    return ObjectInputFilter.Status.ALLOWED;
                }

                return ObjectInputFilter.Status.REJECTED;
            });

            return (OrderSnapshot) input.readObject();
        }
    }
}
```

This is an illustrative allowlist for a very small graph. When a graph contains collections, enums, or valid subtypes, you must add those exact types to the allowlist and set appropriate size limits. `UNDECIDED` does not mean every class is allowed; other filters or the default mechanism can still decide. For untrusted data, the safer choice is usually not to use Java native deserialization at all.

### 6.2. JSON Also Needs Input Controls

JSON is generally more suitable for public APIs because its data contract is transparent and it does not directly reconstruct arbitrary Java object graphs. Even so, JSON is not automatically safe:

- Limit request size, nesting depth, and element counts.
- Validate input data using Bean Validation or business rules.
- Do not enable broad polymorphic default typing for untrusted data.
- If polymorphic JSON is needed, use an explicit allowlist of subtypes and a clear contract.
- Prevent the JSON parser from consuming unbounded CPU/memory via large payloads or deeply nested structures.

## 7. Java Serialization in GraalVM Native Image

### 7.1. Why Are Serialization Hints Needed?

GraalVM Native Image analyzes reachable code and needs to know which types can be reconstructed via Java serialization. Receiving objects from a stream via `readObject()` can cause types to be used along dynamic paths that reachability analysis cannot fully infer from normal code.

Spring provides `RuntimeHints.serialization()` to declare types used in Java serialization. These hints belong to **serialization metadata**, not regular reflection hints.

### 7.2. Registering Serialized Types with `RuntimeHintsRegistrar`

```java
package com.example.orders.snapshot;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class OrderSerializationRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.serialization().registerType(OrderSnapshot.class);
    }
}
```

If the object graph contains additional serializable types such as `OrderLineSnapshot`, register those types when they are not inferred by the framework or another metadata mechanism:

```java
hints.serialization().registerType(OrderSnapshot.class);
hints.serialization().registerType(OrderLineSnapshot.class);
```

Registering the root type while omitting types inside the graph can cause a specific deserialization path to fail. Test with realistic object graphs, including nested objects and custom serialization where applicable.

### 7.3. Attaching Hints to the Owning Module

```java
package com.example.orders.snapshot;

import java.io.IOException;
import java.io.ObjectOutputStream;
import java.io.OutputStream;

import org.springframework.context.annotation.ImportRuntimeHints;
import org.springframework.stereotype.Component;

@Component
@ImportRuntimeHints(OrderSerializationRuntimeHints.class)
public class OrderSnapshotStore {

    public void save(OrderSnapshot snapshot, OutputStream destination)
            throws IOException {
        try (ObjectOutputStream output = new ObjectOutputStream(destination)) {
            output.writeObject(snapshot);
        }
    }
}
```

`@ImportRuntimeHints` associates the registrar with the component that uses Java serialization. If the snapshot module is not imported or the bean is excluded by configuration conditions during AOT, the corresponding hints will not necessarily be contributed through that component.

### 7.4. Testing Serialization Hints

```java
package com.example.orders.snapshot;

import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class OrderSerializationRuntimeHintsTests {

    @Test
    void registersOrderSnapshotSerialization() {
        RuntimeHints hints = new RuntimeHints();
        new OrderSerializationRuntimeHints().registerHints(
                hints, getClass().getClassLoader());

        assertThat(RuntimeHintsPredicates.serialization()
                .onType(OrderSnapshot.class))
                .accepts(hints);
    }
}
```

The predicate verifies that metadata has been registered. It does not prove that streams are compatible across all class versions or that every object graph can be read back. Round-trip tests and integration tests running on the native executable are needed.

## 8. JSON Binding in GraalVM Native Image

### 8.1. JSON Does Not Use Serialization Hints

When Jackson maps JSON into `OrderRequest` or converts `OrderResponse` into JSON, that is **data binding**. It may need to access constructors, accessors, fields, or annotation metadata via reflection.

Therefore, do not use:

```java
hints.serialization().registerType(OrderResponse.class);
```

to fix a Jackson error about a missing constructor/property in a native image. That API describes Java Object Serialization. For JSON binding, reflection/binding hints are needed.

### 8.2. Spring AOT Automatically Infers Many DTO Types

For Spring MVC/WebFlux controllers that declare explicit request/response types, Spring AOT and JSON integrations can analyze signatures to generate the required metadata. You should not manually register every DTO upfront.

However, if the application invokes `ObjectMapper` directly with types determined dynamically, or uses custom serializers/deserializers that AOT cannot observe, you must declare appropriate reflection hints.

### 8.3. Using `@RegisterReflectionForBinding`

Spring provides `@RegisterReflectionForBinding` to register reflection hints for data binding on the specified types:

```java
package com.example.orders.api;

import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding({OrderRequest.class, OrderResponse.class})
class OrderJsonRuntimeConfiguration {
}
```

This is a suitable choice when JSON types are used through a custom mapper or code paths that Spring AOT cannot infer on its own. Only add the DTOs that genuinely need binding metadata.

### 8.4. Using `RuntimeHintsRegistrar` When Fine-Grained Control Is Needed

If you need to register reflection for a specific type, you can use `RuntimeHintsRegistrar`:

```java
package com.example.orders.api;

import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class OrderJsonRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
                OrderResponse.class,
                MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS);
    }
}
```

Attach the registrar via `@ImportRuntimeHints` to the module owning the mapper. The exact metadata needed depends on how Jackson instantiates objects and reads/writes properties; the example above illustrates a DTO with public constructors and accessors. For records, private fields, custom creators, or specialized serializers, check the actual requirements and use `@RegisterReflectionForBinding` when appropriate.

### 8.5. JSON Resources Are Yet Another Kind of Hint

If the application reads a static JSON file from the classpath, such as `schemas/order-v2.json`, the issue may be a **resource hint**, not a serialization or reflection hint:

```java
hints.resources().registerPattern("schemas/order-v2.json");
```

Three needs to distinguish:

| Scenario | Metadata type |
|---|---|
| `ObjectInputStream.readObject()` reconstructs `OrderSnapshot` | Serialization hints |
| Jackson binds JSON into `OrderRequest` using reflection | Reflection/binding hints |
| Reading `schemas/order-v2.json` from the classpath | Resource hints |

### 8.6. JNI Is Not a Serialization Format

JNI (*Java Native Interface*) is a mechanism for Java to call native code or for native code to interact with Java. JNI does not dictate whether payloads must use Java serialization or JSON. A native library can receive `byte[]`, UTF-8 strings, or data structures following its own contract; the payload format still has to be defined independently.

In Native Image, JNI hints describe the Java classes/members that native code needs to access. They do not replace serialization hints for `ObjectInputStream`, reflection/binding hints for Jackson, or resource hints for JSON files. Included native libraries must also be compatible with the target image's operating system, CPU architecture, and ABI.

## 9. Testing the Two Mechanisms Independently

### 9.1. Java Serialization Round-Trip

```java
package com.example.orders.snapshot;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class OrderSnapshotSerializationTests {

    @Test
    void writesAndReadsOrderSnapshot() throws Exception {
        OrderSnapshot original = new OrderSnapshot("ORD-100", 250_000L);
        byte[] bytes;

        try (ByteArrayOutputStream buffer = new ByteArrayOutputStream();
             ObjectOutputStream output = new ObjectOutputStream(buffer)) {
            output.writeObject(original);
            bytes = buffer.toByteArray();
        }

        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            OrderSnapshot restored = (OrderSnapshot) input.readObject();
            assertThat(restored.getOrderId()).isEqualTo("ORD-100");
            assertThat(restored.getTotalAmount()).isEqualTo(250_000L);
        }
    }
}
```

This test verifies the Java serialization contract and the fields to be restored. If the class has custom `writeObject/readObject`, `readResolve`, `Externalizable`, or nested graphs, add corresponding test cases.

### 9.2. JSON Round-Trip

```java
package com.example.orders.api;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class OrderJsonCodecTests {

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void writesAndReadsOrderResponse() throws Exception {
        OrderResponse original = new OrderResponse("ORD-100", 250_000L);

        String json = objectMapper.writeValueAsString(original);
        OrderResponse restored = objectMapper.readValue(json, OrderResponse.class);

        assertThat(restored).isEqualTo(original);
    }
}
```

The test uses the Spring Boot-configured mapper, which verifies the application's actual Jackson modules and custom configuration. If custom Jackson modules or serializers are used, the test must run with the same runtime configuration.

### 9.3. Running Both Tests on the Native Executable

A passing JVM round-trip does not guarantee a passing native round-trip. You need to execute real flows on the native image:

- Write and read `OrderSnapshot` via Java serialization.
- Process JSON payloads via controllers or `ObjectMapper`.
- Verify custom serializers/deserializers, polymorphic types, and nested DTOs if present.
- Verify JSON/schema resources if the application loads them from the classpath.
- Verify compatibility with data persisted from previous application versions if upgrade support is required.

## 10. Choosing a Format by Use Case

| Use case | Typically suitable choice | Reason |
|---|---|---|
| Public REST API | JSON | Multi-language clients, easy to inspect and manage contracts |
| Messages across heterogeneous services | JSON or another schema-based format | Does not force consumers to use Java serialization |
| Short-lived internal cache across processes on the same Java version | Java serialization or another codec can be considered | Requires evaluating versioning, security, and performance |
| Persisting a Java object graph with identity/cycles | Java serialization can represent graphs, but safety and upgradability must be weighed | Preserves reference graphs; high class coupling |
| Long-term storage or multi-version integration | JSON with schema/versioning or a data format with an explicit schema | Easier migration and interoperability across versions/languages |
| Data originating from users or untrusted external systems | JSON with validation and parser limits | Avoids untrusted Java native deserialization |

These are general selection guidelines, not absolute rules. For large datasets or high-performance requirements, you may also need to benchmark Avro, Protobuf, or other codecs with explicit schemas.

## 11. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| `NotSerializableException` | A type in the object graph does not implement `Serializable` or is not handled by custom serialization | Inspect the entire graph, exclude unnecessary fields with `transient`, or use an appropriate DTO |
| `InvalidClassException` | `serialVersionUID` mismatch or class serialization contract changed | Check the UID, fields, and data migration strategy |
| Field resets to `null`/default value after deserialization | Field is `transient`, not written, or custom read logic does not restore it | Check the serialization contract and `readObject` |
| Java serialization fails on native image | Missing serialization metadata for one or more types in the graph | Use `hints.serialization().registerType(...)` and run native round-trip tests |
| Jackson reports missing constructor/property on native | Missing reflection/binding metadata or custom mapper not analyzed by AOT | Check `@RegisterReflectionForBinding` or reflection hints |
| JSON file not found on native | Resource was not retained in the executable | Register `hints.resources()` for the required classpath path |
| JSON round-trip differs from JVM result | Custom module/serializer or `ObjectMapper` configuration is not used consistently | Inject the Spring mapper, check configuration, and run native integration tests |
| JSON deserialization fails on subtypes | Polymorphic metadata/subtype not declared or not allowed | Use a subtype allowlist and appropriate hints; do not enable broad default typing |
| Deserializing untrusted data causes security risks | Java serialization without filters/allowlists or overly broad JSON polymorphic typing | Never accept untrusted Java serialized data; use filters and parser limits |

## 12. Hands-On Exercise: Same Data, Two Representations

**Context:** `order-service` stores an internal snapshot and exposes a REST API returning `OrderResponse`.

### Step 1 — Create the Models

Create `OrderSnapshot implements Serializable` with an explicit `serialVersionUID`. Create `OrderRequest` and `OrderResponse` as separate JSON DTOs. Do not reuse the same class for both internal persistence and APIs if the two contracts have different lifecycles.

### Step 2 — Try Java Serialization

Write the snapshot using `ObjectOutputStream`, read it back with `ObjectInputStream`, and verify the fields. Add tests for nested objects and `transient` fields if present.

### Step 3 — Try JSON

Inject `ObjectMapper` from Spring Boot, convert `OrderResponse` to JSON, and read it back. Verify field names, null handling, date/time formats, and unknown properties against the application contract.

### Step 4 — Configure Native Metadata

- Java serialization: register `OrderSnapshot` and types in its graph via `RuntimeHints.serialization()` if Spring AOT has not inferred the requirement.
- JSON: prefer metadata automatically inferred from controllers; for dynamic mappers, use `@RegisterReflectionForBinding` or reflection hints.
- JSON resources: register a separate resource pattern if reading schema/template files from the classpath.

### Step 5 — Build and Test Native

Build the native executable/container image. Run both the Java serialization round-trip and JSON round-trip on native. If one mechanism fails, identify the corresponding metadata type before adding hints.

### Result Sheet

| Item | Java serialization | JSON/Jackson |
|---|---|---|
| Model | `OrderSnapshot` | `OrderRequest`, `OrderResponse` |
| Format | Binary object stream | JSON text |
| API | `ObjectOutputStream` / `ObjectInputStream` | `ObjectMapper` / HTTP message converter |
| Versioning | `serialVersionUID` and serialization contract | Schema/API version and field rules |
| Native metadata | Serialization hints | Reflection/binding hints; resource hints if needed |
| JVM round-trip | _(PASS/FAIL)_ | _(PASS/FAIL)_ |
| Native round-trip | _(PASS/FAIL)_ | _(PASS/FAIL)_ |
| Security review | Input source, `ObjectInputFilter` | Validation, subtype allowlist, payload limits |

## 13. Key Takeaways

Java Object Serialization persists and restores Java object graphs as a binary stream; JSON represents data as text that can be exchanged across many languages and systems. Java serialization is tightly coupled to classes and the serialization contract, whereas JSON relies on application-managed schema/API contracts. The two mechanisms differ in versioning, security, and Native Image metadata.

For GraalVM Native Image, use **serialization hints** for `ObjectInputStream`/`ObjectOutputStream`; use **reflection/binding hints** for Jackson when AOT cannot infer types automatically; and use **resource hints** if the application reads JSON files from the classpath. Do not use `RuntimeHints.serialization()` to fix JSON binding errors. Always test both conversion paths on the native executable and never deserialize Java object streams from untrusted sources.

### Official References

- [Java SE — Object Serialization Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/serialization/)
- [Java SE — `ObjectInputFilter`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/ObjectInputFilter.html)
- [Spring Framework — Runtime Hints and AOT](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [Spring Framework — `SerializationHints` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aot/hint/SerializationHints.html)
- [Spring Framework — `RegisterReflectionForBinding` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aot/hint/annotation/RegisterReflectionForBinding.html)
- [Spring Boot — JSON Support](https://docs.spring.io/spring-boot/reference/features/json.html)
- [GraalVM Native Image — Serialization Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/)
