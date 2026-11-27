# SerializationHints for Java Serialization

Java provides an **Object Serialization** mechanism to convert an object graph into a byte stream and restore it into objects using `ObjectOutputStream` and `ObjectInputStream`. This mechanism relies on class metadata, serializable fields, inheritance hierarchies, and hooks such as `writeObject` or `readResolve`. On the JVM, the class loader and JVM reflection can handle many dynamic operations. When compiling a Spring Boot application into a GraalVM Native Image, classes participating in Java serialization must be detected or have metadata declared before the executable is built.

Spring provides `SerializationHints` within the `RuntimeHints` system to describe types that require serialization support. This lesson focuses on **Java serialization**, how to declare hints via `RuntimeHintsRegistrar`, how to test object graphs on the native executable, and key limitations to keep in mind. Java serialization is a distinct mechanism and is not synonymous with Jackson JSON serialization.

## 1. What Is Java Serialization?

Java serialization is Java's standard mechanism for writing object state to a byte stream and reading it back into objects. A class typically participates in this mechanism by implementing the marker interface `java.io.Serializable`:

~~~java
import java.io.Serial;
import java.io.Serializable;

public final class CustomerSnapshot implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    private final String customerId;
    private final String displayName;

    public CustomerSnapshot(String customerId, String displayName) {
        this.customerId = customerId;
        this.displayName = displayName;
    }

    public String getCustomerId() {
        return customerId;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

`Serializable` has no methods to implement. It marks objects of that type as eligible for Java serialization, provided all state to be serialized satisfies the mechanism's rules.

Two key classes:

- `ObjectOutputStream` writes an object graph to an `OutputStream` via `writeObject(...)`.
- `ObjectInputStream` reads a byte stream and restores objects via `readObject()`.

Example processing flow:

~~~mermaid
flowchart LR
    A["Object graph"] --> B["ObjectOutputStream.writeObject"]
    B --> C["Serialized byte stream"]
    C --> D["ObjectInputStream.readObject"]
    D --> E["New object graph"]
~~~

The restored object is a new instance in the reading process. It is not the same instance as the original object. Java serialization tracks references within the stream to preserve shared object relationships and handle reference cycles.

## 2. Object Graphs and Classes That Must Be Supported

When `writeObject(root)` is called, Java serialization can traverse objects referenced from the root. Therefore, metadata must be evaluated across the **actual object graph**, not just the outermost object's class.

Example:

~~~java
package com.example.nativeimage;

import java.io.Serial;
import java.io.Serializable;
import java.math.BigDecimal;
import java.util.List;

public final class OrderSnapshot implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    private final String orderId;
    private final CustomerSnapshot customer;
    private final List<OrderLineSnapshot> lines;
    private final BigDecimal total;

    public OrderSnapshot(
            String orderId,
            CustomerSnapshot customer,
            List<OrderLineSnapshot> lines,
            BigDecimal total) {
        this.orderId = orderId;
        this.customer = customer;
        this.lines = List.copyOf(lines);
        this.total = total;
    }

    public String getOrderId() {
        return orderId;
    }

    public CustomerSnapshot getCustomer() {
        return customer;
    }

    public List<OrderLineSnapshot> getLines() {
        return lines;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

~~~java
package com.example.nativeimage;

import java.io.Serial;
import java.io.Serializable;

public final class OrderLineSnapshot implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    private final String sku;
    private final int quantity;

    public OrderLineSnapshot(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }
}
~~~

In the object graph above, the application types to pay attention to include:

- `OrderSnapshot`: the root type passed into the stream.
- `CustomerSnapshot`: a type referenced by a field of the root.
- `OrderLineSnapshot`: the element type inside a collection.
- Other types that may appear as runtime subtypes, such as implementations of an interface or classes selected by configuration.

`String`, `BigDecimal`, and standard JDK collections have corresponding serialization support in the JDK/GraalVM. For application classes or library classes introduced by the application into the object graph, explicitly identify the required serialization metadata. Do not assume that registering the root type automatically covers every concrete type the program may write or read.

### Polymorphic types must be considered

If a field is declared as an interface or abstract class, the actual object may be one of several implementations:

~~~java
public interface PaymentDetails extends Serializable {
}

public final class CardPaymentDetails implements PaymentDetails {
    // Card payment state.
}

public final class BankTransferDetails implements PaymentDetails {
    // Bank transfer state.
}
~~~

If both `CardPaymentDetails` and `BankTransferDetails` can appear in the stream, register the concrete types that need to be supported. A field's declared type is not necessarily the runtime type written to the stream.

## 3. Why Does Native Image Need SerializationHints?

GraalVM Native Image performs reachability analysis under a closed-world assumption. For a direct call like `new CustomerSnapshot(...)`, the analyzer can see the used type from the code. However, Java serialization performs many operations driven by metadata and object reconstruction mechanisms, including:

- Resolving class descriptors in the stream.
- Instantiating objects and restoring state without going through the `Serializable` class's regular constructor.
- Handling fields, inheritance, and concrete classes appearing in the object graph.
- Invoking serialization hooks defined by classes.
- Handling classes identified from the stream rather than from an explicit constructor call.

Therefore, having a class in a dependency or used on a normal code path **does not guarantee** that every Java serialization path for that class is preserved properly in the native executable.

Spring AOT provides `RuntimeHints` to declare required runtime capabilities. The serialization section is accessed via:

~~~java
hints.serialization()
~~~

`SerializationHints` describes the types that must participate in Java serialization so Spring AOT can forward appropriate information to Native Image metadata.

**Do not confuse SerializationHints with reflection hints.** Reflection hints describe the ability to access classes/members via reflection. Serialization hints describe classes needing support for the Java object serialization mechanism. An application may need both if it serializes objects with `ObjectOutputStream` while also accessing certain members independently via reflection.

## 4. Declaring SerializationHints with RuntimeHintsRegistrar

Spring provides the `RuntimeHintsRegistrar` interface for libraries or applications to contribute runtime hints. For the types in the example, you can register them as follows:

~~~java
package com.example.nativeimage;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

final class OrderSerializationHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.serialization().registerType(OrderSnapshot.class);
        hints.serialization().registerType(CustomerSnapshot.class);
        hints.serialization().registerType(OrderLineSnapshot.class);
    }
}
~~~

Register the registrar with the Spring context:

~~~java
package com.example.nativeimage;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(OrderSerializationHints.class)
class NativeSerializationConfiguration {
}
~~~

When Spring AOT processes the configuration, `@ImportRuntimeHints` allows Spring to discover the registrar and collect the hints it contributes.

Key points to remember:

1. Use `hints.serialization().registerType(...)` for each application type needing Java serialization support.
2. Register the root type, referenced types, and any concrete subtypes that may appear.
3. Place the registrar in a package discovered by Spring component/configuration scanning, or import the configuration explicitly.
4. Hints must be contributed during the AOT phase before native compilation.
5. After changing hints, rerun the AOT/native build to produce a new binary.

Detailed APIs may vary by Spring Framework/Spring Boot version. The example above uses the modern Spring AOT API with `RuntimeHints.serialization()`; check your actual dependency version if the IDE does not recognize a method.

### Registering does not mean objects are created at build time

The registrar only describes capabilities needed for the native runtime. Calling `registerType` does not instantiate an `OrderSnapshot`, read a database, or serialize payloads during the build phase. Real objects are still created and serialized/deserialized when the application runs.

## 5. Serializing and Deserializing an Object Graph

The following example illustrates an in-memory round trip. In a real application, the byte stream may come from files, messages, or a storage system; the serialization mechanism does not depend on where bytes are stored.

~~~java
package com.example.nativeimage;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.math.BigDecimal;
import java.util.List;

public final class OrderSnapshotCodec {

    public byte[] serialize(OrderSnapshot snapshot) throws IOException {
        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             ObjectOutputStream output = new ObjectOutputStream(bytes)) {
            output.writeObject(snapshot);
            output.flush();
            return bytes.toByteArray();
        }
    }

    public OrderSnapshot deserialize(byte[] bytes)
            throws IOException, ClassNotFoundException {
        try (ByteArrayInputStream inputBytes = new ByteArrayInputStream(bytes);
             ObjectInputStream input = new ObjectInputStream(inputBytes)) {
            Object value = input.readObject();
            return OrderSnapshot.class.cast(value);
        }
    }

    public static void main(String[] args) throws Exception {
        CustomerSnapshot customer =
                new CustomerSnapshot("C-100", "Lan");

        OrderSnapshot original = new OrderSnapshot(
                "O-2026-001",
                customer,
                List.of(new OrderLineSnapshot("SKU-01", 2)),
                new BigDecimal("125000.00")
        );

        OrderSnapshotCodec codec = new OrderSnapshotCodec();
        byte[] bytes = codec.serialize(original);
        OrderSnapshot restored = codec.deserialize(bytes);

        System.out.println("orderId=" + restored.getOrderId());
        System.out.println("customer=" + restored.getCustomer().getDisplayName());
        System.out.println("lines=" + restored.getLines().size());
        System.out.println("sameInstance=" + (original == restored));
    }
}
~~~

Expected output:

~~~text
orderId=O-2026-001
customer=Lan
lines=1
sameInstance=false
~~~

The example requires `CustomerSnapshot`, `OrderLineSnapshot`, and `OrderSnapshot` in the same package as declared above. The codec can be extracted into a Spring bean or called from a service; bean organization does not change serialization metadata requirements.

### Why must both write and read paths be tested?

- **Serialize:** confirms that the types in the graph can be written to the stream.
- **Deserialize:** confirms that the runtime can read class descriptors and restore the corresponding types.
- **Round trip:** confirms that critical data is preserved accurately after restoration.
- **Legacy payloads:** confirms that the application can read streams produced by earlier versions if business requirements demand backward compatibility.

A test that only calls `writeObject` does not prove `readObject` works in native mode. Test both directions on the native executable itself.

## 6. Java Serialization Rules That Affect Data

### serialVersionUID

`serialVersionUID` is a class's version identifier in Java serialization. If not explicitly declared, the JVM computes a default value from the class structure. Changing the class can alter the computed value and make older streams incompatible.

Declare it explicitly on `Serializable` classes whose data needs long-term persistence:

~~~java
@Serial
private static final long serialVersionUID = 1L;
~~~

Declaring the same number does not automatically make all schema changes safe. Design compatibility rules, test legacy data, and handle added/removed fields appropriately.

### transient and static

- Fields marked `transient` are not written by default serialization.
- `static` fields belong to the class rather than instance state, so they are not serialized as instance fields.
- During deserialization, `transient` fields may receive default values or be restored in a custom `readObject`.

Example:

~~~java
public final class SessionSnapshot implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    private final String sessionId;
    private transient String temporaryCache;

    public SessionSnapshot(String sessionId, String temporaryCache) {
        this.sessionId = sessionId;
        this.temporaryCache = temporaryCache;
    }
}
~~~

Do not serialize passwords, tokens, secret keys, or sensitive data simply because a class is serializable. Using `transient` can exclude a field from default serialization, but it is no substitute for proper secrets management design.

### Custom serialization hooks

A class can customize serialization/deserialization using special methods such as:

- `private void writeObject(ObjectOutputStream out)`
- `private void readObject(ObjectInputStream in)`
- `Object writeReplace()`
- `Object readResolve()`

These methods must follow Java serialization signatures and rules. They can transform written data, validate state, or substitute objects after reading. When using custom hooks, test them with the native executable, especially if the hooks invoke helper classes, reflection, or dynamic resources.

`Externalizable` is a different mechanism requiring the class to manage `writeExternal` and `readExternal` directly; it has its own constructor rules. If the application uses `Externalizable`, verify the required classes and constructors for your Java API and Native Image version rather than assuming it behaves identically to standard `Serializable`.

## 7. Which Types Must Be Registered?

There is no single "registering only the root type is enough" rule for every object graph. Build the list from actual payloads:

| Data type | Needs consideration? | Notes |
| --- | --- | --- |
| Root class passed to `writeObject` | Yes | Entry point of the object graph |
| Class referenced from a field | Yes | May be serialized recursively |
| Concrete subtype of interface/abstract field | Yes | Runtime type may differ from declared type |
| Class inside a collection | Yes | Register each application type appearing as an element |
| Application enum | Yes if part of the graph | Inspect actual payloads and required metadata |
| JDK serializable classes | Check per JDK/GraalVM support | Do not mechanically register all JDK classes |
| Third-party library class | Yes if part of the graph | Prefer library-supplied metadata; supplement if missing |
| Class used only for JSON/Jackson | Does not need `SerializationHints` just for JSON | Use binding/reflection mechanisms suited for that serializer |

If the application has multiple payload types, create one registrar per business group or module so hint lists remain reviewable and testable.

### When the object graph evolves

Suppose a later version adds a `paymentDetails` field that can hold `CardPaymentDetails` or `BankTransferDetails`. Update hints for the new concrete types and test payloads containing both variants. Otherwise, the JVM may work while native fails only on the new payment type.

Do not broadly register every class in a package when unnecessary. An intentional list clarifies data scope and limits redundant metadata.

## 8. Distinguishing Java Serialization from JSON Serialization

Both mechanisms convert data into a storable or transmittable form, yet they have different goals and metadata:

| Aspect | Java Object Serialization | JSON serialization (e.g., Jackson) |
| --- | --- | --- |
| Typical API | `ObjectOutputStream` / `ObjectInputStream` | `ObjectMapper` |
| Marker interface | Commonly uses `Serializable` | Not required |
| Data format | Java serialization stream, coupled to class descriptors | JSON text |
| Cross-language compatibility | Limited, tightly coupled to the Java ecosystem | Broad, supported across many languages |
| Native Image metadata | `SerializationHints` for Java serialization | Reflection/binding hints or Jackson integration metadata |
| Human readability | Inconvenient | Readable and debuggable with JSON tools |
| Risk when deserializing untrusted data | Particularly sensitive due to object hooks and gadget chains | Still needs validation, though it does not perform arbitrary Java object reconstruction in the same way |

`SerializationHints` is **not** the way to register DTOs for every serializer. If a REST endpoint returns `OrderSnapshot` as JSON via Jackson, check Spring AOT/Jackson integration and appropriate binding hints. Only when the application writes `OrderSnapshot` via `ObjectOutputStream` is it a Java serialization scenario requiring `SerializationHints`.

For new APIs, prefer data formats with schemas and broad interoperability such as JSON or Protocol Buffers when there is no legacy Java serialization compatibility requirement. Java serialization is typically appropriate when maintaining an existing Java stream contract with controlled data sources.

## 9. Safe Deserialization

Java serialization carries significant security risks if an application reads streams from untrusted sources. Deserialization can instantiate objects and invoke custom hooks; certain classes on the classpath can form gadget chains. Native Image **does not eliminate this risk**.

Minimum principles:

- Never deserialize arbitrary byte streams from users or unauthenticated sources.
- Authenticate data sources and protect payload integrity.
- Use `ObjectInputFilter` to restrict allowed classes, object graph depth, reference counts, and stream size.
- Allow only the data types that are genuinely required.
- Limit payload size and processing time.
- Avoid Java serialization for public data exchange without strong compatibility justification.

Example filter illustrating stream depth, reference count, and byte limits:

~~~java
ObjectInputFilter filter = info -> {
    if (info.depth() > 20
            || info.references() > 1_000
            || info.streamBytes() > 1_000_000) {
        return ObjectInputFilter.Status.REJECTED;
    }
    return ObjectInputFilter.Status.UNDECIDED;
};

try (ObjectInputStream input = new ObjectInputStream(source)) {
    input.setObjectInputFilter(filter);
    Object value = input.readObject();
}
~~~

This filter sets **resource limits** only; an `UNDECIDED` result is not a class allow-list. In production systems, add a class allow-list policy matching the permitted object graph, or use an application-wide filter factory/policy. Do not copy the limit-only filter above and assume it blocks dangerous classes.

## 10. Testing SerializationHints Before Building Native

Three layers of testing are valuable.

### Verifying that Spring AOT discovers the registrar

Ensure the configuration containing `@ImportRuntimeHints` is imported or discovered by component scanning in the application context. If the registrar lives in a library module, verify that module's auto-configuration/import mechanism.

### Round-trip tests on the JVM

Create representative payloads covering all supported subtypes and nested types. Write the object to a byte stream, read it back, and compare key business fields. Include payloads generated by earlier versions if migration support is required.

### Testing on the native executable

Build the native image from the same source and run the exact test cases inside the native binary. Do not stop at checking that the native executable starts or that the health endpoint returns UP. Serialize/deserialize branches may only be triggered when receiving messages or processing rare data types.

Test checklist:

| Scenario | What to verify |
| --- | --- |
| Serialize root object | Stream is written without error |
| Deserialize fresh stream | Root type and fields are restored accurately |
| Nested objects | Referenced classes are restored |
| Collections | Elements and concrete types are supported |
| Polymorphic fields | Every possible implementation works |
| Custom hooks | `writeObject`/`readObject`/`writeReplace`/`readResolve` execute properly |
| Legacy streams | `serialVersionUID` and compatibility rules behave as expected |
| Malformed/untrusted input | Filter rejects oversized streams or disallowed types |

If tests only run on the JVM, they do not verify Native Image metadata. Include at least one round-trip integration test in the native testing workflow.

## 11. Common Troubleshooting

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| JVM serializes cleanly, native throws serialization error | Type is not registered in serialization metadata | Inspect object graph and registrar |
| Serialization works, yet deserialization fails | Missing metadata for a class in the stream or incompatible custom hook/constructor | Test the read path separately; check root exception and concrete types |
| Root class registered, yet nested field fails | Only root was registered; referenced type was missed | Register all custom types that can appear in the graph |
| One specific subtype fails | Polymorphic field has an unregistered concrete type | Add hint for that implementation and test payload |
| Legacy payload cannot be read | `serialVersionUID`/schema changed or custom `readObject` does not handle older versions | Define compatibility policy and test legacy stream fixtures |
| `transient` value lost after deserialization | Default serialization behavior | Restore intentionally in `readObject` if truly required |
| Native runs, yet data is wrong | Custom hooks, `readResolve`, or state restoration logic | Compare objects before/after round trip in native |
| Deserializing untrusted input poses risk | No proper allow-list/filter | Add `ObjectInputFilter` and restrict data sources |

### Investigation workflow

1. Reproduce the failure with the smallest possible payload.
2. Determine whether the failure occurs in `writeObject` or `readObject`.
3. Identify the exact class in the object graph at the failure point.
4. Check whether that class is registered in `RuntimeHints.serialization()`.
5. Check whether the registrar is discovered by Spring AOT.
6. Rebuild the native executable and re-run the exact payload.
7. If the error persists, inspect custom serialization hooks, class hierarchy, `serialVersionUID`, and JDK/GraalVM version differences.

Do not add reflection hints indiscriminately when the failure lies in Java serialization metadata. First identify which mechanism is being invoked.

## 12. Hands-on Exercise: Registering an Object Graph for the Native Executable

Create a `com.example.nativeimage` package with the following classes:

- `CustomerSnapshot` implementing `Serializable`.
- `OrderLineSnapshot` implementing `Serializable`.
- `OrderSnapshot` implementing `Serializable` and referencing the two types above.
- `OrderSerializationHints` implementing `RuntimeHintsRegistrar`.
- `NativeSerializationConfiguration` importing the registrar with `@ImportRuntimeHints`.

Tasks:

1. Write a codec using `ObjectOutputStream` and `ObjectInputStream`.
2. Create a payload with a customer, multiple order lines, and several JDK serializable values.
3. Register the three application classes via `hints.serialization().registerType(...)`.
4. Run the round-trip test on the JVM.
5. Build the native executable using the configured Maven or Gradle Native Build Tools.
6. Run the same round-trip test on the native executable.
7. Add a new subtype to the object graph, update hints, and verify the tests.
8. Attempt to read an older payload after modifying a class; document `serialVersionUID` compatibility rules.
9. If the application accepts streams from external sources, add an `ObjectInputFilter` with an appropriate allow-list and resource limits.

### Self-Check Questions

1. Does `Serializable` have any methods to implement? What is the role of a marker interface?
2. Why is registering only the root type not guaranteed to suffice for the entire object graph?
3. How does `SerializationHints` differ from reflection hints?
4. Why does Spring AOT need to know classes used by Java serialization before native compilation?
5. When should you use `RuntimeHintsRegistrar` and `@ImportRuntimeHints`?
6. How does `serialVersionUID` affect reading legacy streams?
7. Why does Java serialization from untrusted sources require `ObjectInputFilter`?
8. If an application only uses Jackson to return JSON, should every DTO be registered via `SerializationHints`? Why or why not?

**Passing criteria:** can explain Java object serialization and object graphs; accurately registers all required types with `RuntimeHints.serialization()`; distinguishes `SerializationHints` from reflection/Jackson hints; tests both serialization and deserialization on the native executable; and manages `serialVersionUID` while protecting deserialization inputs per security policy.
