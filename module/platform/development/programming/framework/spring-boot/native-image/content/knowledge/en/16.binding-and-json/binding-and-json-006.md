# Polymorphic Deserialization and a Known Subtype Set

## 1. The Polymorphic Deserialization Problem

A JSON API may receive multiple object types that conform to a single contract. For example, a system receives `OrderCreated`, `PaymentRejected`, and `OrderCancelled` events; all are `DomainEvent`, yet each type has its own fields. When deserializing JSON into `DomainEvent`, the library must know **which concrete type is allowed to be instantiated** based on type discriminator information in the payload.

That is **polymorphic deserialization**: converting JSON into one of several subtypes of a base type (base class or interface). Jackson typically solves this with type metadata such as `@JsonTypeInfo`, `@JsonSubTypes`, `@JsonTypeName`, or via a Jackson Module registering the subtypes.

With Spring Boot Native Image, GraalVM performs reachability analysis at build time. Subtypes chosen from JSON strings at runtime are not necessarily inferred from the static call graph. Therefore, the application needs a **finite subtype set known before the build**, and must ensure reflection/binding metadata for those types is present in the native executable.

This lesson belongs to the **Binding and JSON** chapter of the **SPRING_BOOT_NATIVE_IMAGE** module. It focuses on:

- How Jackson determines a subtype from a type discriminator.
- Declaring subtypes via annotations or module registration.
- Why the subtype set must be known before building a Native Image.
- How Spring AOT contributes reflection hints for the base type, subtypes, and nested DTOs.
- Testing deserialization on both the JVM and the native executable.
- Controlling untrusted type IDs to avoid expanding the attack surface.

## 2. Base Types, Subtypes, and Type Discriminators

Suppose an API receives a business event. We have a base type:

```java
package com.example.events;

import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "eventType"
)
@JsonSubTypes({
    @JsonSubTypes.Type(
        value = OrderCreated.class,
        name = "order-created"
    ),
    @JsonSubTypes.Type(
        value = PaymentRejected.class,
        name = "payment-rejected"
    )
})
public abstract class DomainEvent {

    private String eventId;

    public String getEventId() {
        return eventId;
    }

    public void setEventId(String eventId) {
        this.eventId = eventId;
    }
}
```

First subtype:

```java
package com.example.events;

import java.math.BigDecimal;

public class OrderCreated extends DomainEvent {

    private String orderNumber;
    private BigDecimal total;

    public OrderCreated() {
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public void setOrderNumber(String orderNumber) {
        this.orderNumber = orderNumber;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public void setTotal(BigDecimal total) {
        this.total = total;
    }
}
```

Second subtype:

```java
package com.example.events;

public class PaymentRejected extends DomainEvent {

    private String paymentReference;
    private String reasonCode;

    public PaymentRejected() {
    }

    public String getPaymentReference() {
        return paymentReference;
    }

    public void setPaymentReference(String paymentReference) {
        this.paymentReference = paymentReference;
    }

    public String getReasonCode() {
        return reasonCode;
    }

    public void setReasonCode(String reasonCode) {
        this.reasonCode = reasonCode;
    }
}
```

Corresponding JSON payloads:

```json
{
  "eventType": "order-created",
  "eventId": "evt-1001",
  "orderNumber": "ORD-2026-001",
  "total": 125000.00
}
```

And:

```json
{
  "eventType": "payment-rejected",
  "eventId": "evt-1002",
  "paymentReference": "PAY-88",
  "reasonCode": "INSUFFICIENT_FUNDS"
}
```

`eventType` is the **type discriminator**. Jackson uses its value to pick a registered concrete class. The application deserializes through the base type:

```java
DomainEvent event = objectMapper.readValue(json, DomainEvent.class);
```

The result can be `OrderCreated` or `PaymentRejected`, depending on the discriminator. The base type must carry subtype metadata that Jackson can look up; otherwise, Jackson cannot automatically infer all implementations from JSON field names alone.

## 3. Ways to Declare a Subtype Set in Jackson

### 3.1. Using @JsonSubTypes and @JsonTypeInfo

The direct approach is declaring subtypes directly on the base type, as in the section 2 example. Advantages:

- The subtype list sits right next to the JSON contract.
- Type IDs have stable logical names, independent of Java package/class names.
- Readers can immediately see which payload types are supported.
- The subtype set can be processed by AOT alongside the base type.

When you want to declare the logical name on the subtype itself, you can use `@JsonTypeName`:

```java
import com.fasterxml.jackson.annotation.JsonTypeName;

@JsonTypeName("order-created")
public class OrderCreated extends DomainEvent {
    // Fields and accessors of the subtype.
}
```

If the name is already explicitly declared in `@JsonSubTypes.Type(name = "...")`, `@JsonTypeName` is usually unnecessary for the same mapping; it is useful when you want the subtype to carry its own logical name in scenarios where Jackson needs to look up the type name.

### 3.2. Registering Subtypes with a Jackson Module

When you do not want to annotate the base type, you can register subtypes with `NamedType` in a module:

```java
import com.example.events.DomainEvent;
import com.example.events.OrderCreated;
import com.example.events.PaymentRejected;
import com.fasterxml.jackson.databind.jsontype.NamedType;
import com.fasterxml.jackson.databind.module.SimpleModule;

SimpleModule eventModule = new SimpleModule("event-subtypes");
eventModule.registerSubtypes(
    new NamedType(OrderCreated.class, "order-created"),
    new NamedType(PaymentRejected.class, "payment-rejected")
);
```

In Spring Boot, you can provide the module as a bean so Jackson auto-configuration integrates it into the application-managed `ObjectMapper`:

```java
@Configuration(proxyBeanMethods = false)
class EventJacksonConfiguration {

    @Bean
    SimpleModule eventSubtypeModule() {
        SimpleModule module = new SimpleModule("event-subtypes");
        module.registerSubtypes(
            new NamedType(OrderCreated.class, "order-created"),
            new NamedType(PaymentRejected.class, "payment-rejected")
        );
        return module;
    }
}
```

The module example only illustrates subtype registration. How type IDs resolve also depends on `@JsonTypeInfo`/type resolver configuration on the base type and the Jackson version. Test both serialization and deserialization on the actual `ObjectMapper` configured by Spring Boot. Do not instantiate a standalone `new ObjectMapper()` in production if the application needs modules, naming strategies, date/time configuration, or custom serializers managed by Spring Boot.

### 3.3. Sealed Classes and Explicit Subtype Lists

Java sealed classes can restrict which classes are permitted to inherit:

```java
public sealed abstract class DomainEvent
    permits OrderCreated, PaymentRejected {
}

public final class OrderCreated extends DomainEvent {
}

public final class PaymentRejected extends DomainEvent {
}
```

This is a sealed variant of the abstract-class hierarchy from section 2; direct subtypes must be declared `final`, `sealed`, or `non-sealed` according to Java rules. A sealed hierarchy lets the compiler verify the subtype set, but **does not automatically replace Jackson's polymorphic configuration**. Jackson still needs to know how to map JSON type IDs to subtypes, such as via `@JsonTypeInfo` paired with `@JsonSubTypes` or module registration. Likewise, the native image still needs those types retained with appropriate metadata.

Whether using annotations, modules, or sealed hierarchies, the principle is: **the allowed subtype set must be explicit and stable at build time**.

## 4. Type IDs Are a Data Contract, Not Arbitrary Class Names

With `JsonTypeInfo.Id.NAME`, JSON uses logical names such as `order-created` and `payment-rejected`. This is generally the right choice for APIs because type IDs do not change when Java packages are refactored.

Avoid using `JsonTypeInfo.Id.CLASS` or enabling broad default typing for JSON arriving from untrusted clients. When a type ID represents a class name, a payload can ask Jackson to resolve a type by class name; if configuration is overly permissive, the risk of instantiating unexpected types and gadget chains increases.

Safety principles:

- Use logical type IDs with an allowlist.
- Register only subtypes the API genuinely accepts.
- Do not take a class name from a request and call `Class.forName` to deserialize.
- Do not enable global default typing for external data without strict validation policies.
- Control nested subtypes and fields typed as `Object`, interfaces, or base classes.
- Return a clear error when a type ID is invalid; do not silently fall back to an inappropriate default subtype.

Example JSON with a disallowed type ID:

```json
{
  "eventType": "admin-command",
  "eventId": "evt-1003",
  "command": "..."
}
```

If `admin-command` is not in the registered subtype list, the application should reject the payload according to API policy. Never automatically look up and load a class with the corresponding name.

### 4.1. Handling Unknown Type IDs

You can choose one of these behaviors depending on the contract:

| Policy | Behavior | When Appropriate |
| --- | --- | --- |
| Fail closed | Reject unknown type IDs | Business APIs needing a strict schema |
| Default subtype | Fall back to a defined default type | Only when the fallback type is genuinely safe and meaningful |
| Ignore/forward unknown | Keep payload as unclassified data | Event gateway systems forwarding payloads without instantiating subtypes |
| Versioned contract | Introduce new versions/types via API or schema versioning | When subtypes expand across product releases |

Jackson's `defaultImpl` can be used for a specific fallback contract, but should not be used to mask invalid type ID errors or turn every invalid payload into a generic object. If unknown data must be forwarded, consider an envelope model keeping the type and raw JSON separate instead of deserializing directly into an arbitrary subtype.

## 5. Why Does Native Image Need to Know Subtypes in Advance?

On a traditional JVM, Jackson can use reflection to discover constructors, getters/setters, fields, and annotations, and instantiate objects using runtime metadata. Native Image uses build-time reachability analysis; types referenced only through JSON strings may never appear in the static call graph.

For example, code only declares:

```java
DomainEvent event = objectMapper.readValue(payload, DomainEvent.class);
```

yet the payload might select `OrderCreated` or `PaymentRejected`. If GraalVM does not recognize these subtypes and the members Jackson needs to access, the binary may build cleanly yet fail deserialization when a request arrives.

Metadata that typically needs review:

- Base type and concrete subtypes.
- Constructors used by Jackson.
- Bound getters/setters or fields.
- Record canonical constructors, `@JsonCreator`, and constructor parameters.
- Nested DTOs, collection elements, map values, and generic types resolved at runtime.
- Custom serializers/deserializers, type resolvers, or modules if instantiated or loaded dynamically.

Spring AOT provides a reflection hints mechanism for binding. `@RegisterReflectionForBinding` is one way to declare types used in serialization/deserialization so Spring contributes the metadata needed for the native build.

## 6. Registering Reflection Hints for the Base Type and Each Subtype

With Spring Boot, you can declare them on a configuration class:

```java
import com.example.events.DomainEvent;
import com.example.events.OrderCreated;
import com.example.events.PaymentRejected;
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding({
    DomainEvent.class,
    OrderCreated.class,
    PaymentRejected.class
})
class EventBindingConfiguration {
}
```

Key points:

1. Register the base type that the controller/service uses to deserialize.
2. Register every concrete subtype that can appear in payloads.
3. Additionally register custom DTOs used in subtype properties if existing binding mechanisms do not recognize them.
4. If a subtype has a property typed as another interface or base type, identify and register the subtype set of that nested hierarchy.
5. Ensure the configuration class is discovered by Spring via component scanning or imported from another configuration.

Do not register only `DomainEvent.class` and assume every subtype will automatically be kept. Subtype lists might only appear in annotations or module registries; verify the Spring/Jackson AOT integration for your version and declare types explicitly when needed.

### 6.1. When to Use `RuntimeHintsRegistrar`?

If the type list is managed in a separate place or needs complex conditional registration, you can use `RuntimeHintsRegistrar`. However, for standard JSON binding, prefer `@RegisterReflectionForBinding` because it expresses the binding intent directly and lets Spring handle the associated metadata.

Illustrative example of an explicit registrar:

```java
import com.example.events.OrderCreated;
import com.example.events.PaymentRejected;
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

final class EventReflectionHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints, ClassLoader classLoader) {

        hints.reflection().registerType(
            OrderCreated.class,
            MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
            MemberCategory.INVOKE_PUBLIC_METHODS
        );

        hints.reflection().registerType(
            PaymentRejected.class,
            MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
            MemberCategory.INVOKE_PUBLIC_METHODS
        );
    }
}
```

Link it to Spring AOT using `@ImportRuntimeHints` on a discovered configuration:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(EventReflectionHints.class)
class NativeEventHintsConfiguration {
}
```

The registrar snippet above is an example for when the application knows Jackson only needs to invoke public constructors and public accessors. If a DTO uses private fields, private constructors, `@JsonCreator`, or custom access patterns, register the matching member categories or use `@RegisterReflectionForBinding` so Spring analyzes the binding. Do not copy member category lists without checking the actual model.

## 7. Nested DTOs, Collections, and Immutable Models

A subtype often contains other DTOs:

```java
public class OrderCreated extends DomainEvent {

    private CustomerSnapshot customer;
    private List<OrderLine> lines;

    public OrderCreated() {
    }

    public CustomerSnapshot getCustomer() {
        return customer;
    }

    public void setCustomer(CustomerSnapshot customer) {
        this.customer = customer;
    }

    public List<OrderLine> getLines() {
        return lines;
    }

    public void setLines(List<OrderLine> lines) {
        this.lines = lines;
    }
}
```

During deserialization, Jackson must instantiate `OrderCreated`, then bind `CustomerSnapshot` and each `OrderLine` element. If these types are used via reflection or dynamic binding paths, ensure they are recognized in AOT hints. `@RegisterReflectionForBinding` can register both the root types and specific binding models:

```java
@RegisterReflectionForBinding({
    DomainEvent.class,
    OrderCreated.class,
    PaymentRejected.class,
    CustomerSnapshot.class,
    OrderLine.class
})
```

### 7.1. Records and `@JsonCreator`

If the base type is designed as an interface rather than an abstract class, a subtype can be a Java record:

```java
public interface DomainEvent {
}

public record PaymentRejected(
    String paymentReference,
    String reasonCode
) implements DomainEvent {
}
```

A record cannot extend an abstract class because every record extends `java.lang.Record`; therefore, this example uses the interface variant of the hierarchy. Jackson needs to use the canonical constructor and component names for binding. Test record subtypes on your exact Jackson version, and register the record type in binding hints when needed.

For non-record immutable classes, you can use `@JsonCreator` and `@JsonProperty`:

```java
public final class PaymentRejected {

    private final String paymentReference;
    private final String reasonCode;

    @JsonCreator
    public PaymentRejected(
            @JsonProperty("paymentReference") String paymentReference,
            @JsonProperty("reasonCode") String reasonCode) {
        this.paymentReference = paymentReference;
        this.reasonCode = reasonCode;
    }

    public String getPaymentReference() {
        return paymentReference;
    }

    public String getReasonCode() {
        return reasonCode;
    }
}
```

Constructors and parameter metadata must match the Jackson configuration. If binding relies on a constructor invoked via reflection in native mode, verify hints grant the necessary access. Do not assume getters alone are sufficient for every immutable model.

## 8. Nested Polymorphism and Multi-Level Subtype Sets

A subtype may contain another polymorphic property. For example, `OrderCreated` has `List<PaymentMethod>` where each element can be `CardPayment` or `BankTransfer`. In that case there are two independent hierarchies:

```java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "methodType"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = BankTransfer.class, name = "bank-transfer")
})
public interface PaymentMethod {
}
```

Register `PaymentMethod` subtypes separately from the `DomainEvent` hierarchy. Payload example:

```json
{
  "eventType": "order-created",
  "eventId": "evt-2001",
  "paymentMethods": [
    {
      "methodType": "card",
      "lastFour": "4242"
    },
    {
      "methodType": "bank-transfer",
      "bankCode": "VCB"
    }
  ]
}
```

A subtype tracking table helps avoid omissions:

| Base type | Logical type id | Concrete subtype | Binding hint present? |
| --- | --- | --- | --- |
| DomainEvent | order-created | OrderCreated | Yes/Unverified |
| DomainEvent | payment-rejected | PaymentRejected | Yes/Unverified |
| PaymentMethod | card | CardPayment | Yes/Unverified |
| PaymentMethod | bank-transfer | BankTransfer | Yes/Unverified |

Each hierarchy must have its own type ID mapping, and subtypes must be retained in the native image. A subtype registered for one hierarchy does not automatically become a valid subtype of another hierarchy.

## 9. Custom Deserializers and Subtype Registration Modules

Some systems use a custom `JsonDeserializer` or `TypeIdResolver` to map type IDs. In that case, verify both parts:

- **Registry:** which type ID maps to which class? This list must be finite and known ahead of time so the classes are included in the native executable.
- **Deserializer/resolver:** which class does Jackson instantiate and invoke? If it is created as a Spring bean or Jackson module, prefer framework-supported registration; if instantiated reflectively, add appropriate hints.

Static registry example:

```java
Map<String, Class<? extends DomainEvent>> allowedTypes = Map.of(
    "order-created", OrderCreated.class,
    "payment-rejected", PaymentRejected.class
);
```

A resolver can look up this map, rather than concatenating a type ID string into a class name and calling `Class.forName`. When a custom deserializer has Spring dependencies, do not manually instantiate `new CustomDeserializer()` inside `ObjectMapper` if it needs beans or configuration from the `ApplicationContext`.

For Jackson modules registering subtypes with `NamedType`, ensure the module is managed by Spring Boot and actually applied to the mapper used by HTTP message converters. A unit test with a manually instantiated `ObjectMapper` may not reflect the application's real mapper.

## 10. Testing Polymorphic Binding on JVM and Native

### 10.1. Unit Testing Each Subtype

Test payloads for each logical type ID:

```java
@Test
void deserializesOrderCreated() throws Exception {
    String json = """
        {
          "eventType": "order-created",
          "eventId": "evt-1001",
          "orderNumber": "ORD-2026-001",
          "total": 125000.00
        }
        """;

    DomainEvent event =
        objectMapper.readValue(json, DomainEvent.class);

    assertInstanceOf(OrderCreated.class, event);
    assertEquals("evt-1001", event.getEventId());
}
```

```java
@Test
void deserializesPaymentRejected() throws Exception {
    String json = """
        {
          "eventType": "payment-rejected",
          "eventId": "evt-1002",
          "paymentReference": "PAY-88",
          "reasonCode": "INSUFFICIENT_FUNDS"
        }
        """;

    DomainEvent event =
        objectMapper.readValue(json, DomainEvent.class);

    assertInstanceOf(PaymentRejected.class, event);
    assertEquals("INSUFFICIENT_FUNDS",
        ((PaymentRejected) event).getReasonCode());
}
```

These tests must use the same mapper configuration as the application. If Spring Boot supplies modules or subtype registries via beans, obtain the mapper from the Spring test context or use `@JsonTest` with the appropriate configurations imported.

### 10.2. Testing Unknown Type IDs

Verify the policy for type IDs not in the allowlist:

```java
@Test
void rejectsUnknownEventType() {
    String json = """
        {
          "eventType": "admin-command",
          "eventId": "evt-unknown"
        }
        """;

    assertThrows(
        JsonProcessingException.class,
        () -> objectMapper.readValue(json, DomainEvent.class)
    );
}
```

The exact exception type may be wrapped by Spring MVC or the application. What matters is that invalid payloads are rejected per contract, never converted into an unintended subtype.

### 10.3. Verifying Through HTTP Message Converters

If an API accepts `@RequestBody DomainEvent`, test the endpoint end-to-end to verify that Spring Boot's Jackson mapper is configured properly:

```java
@RestController
@RequestMapping("/events")
class EventController {

    @PostMapping
    ResponseEntity<String> accept(@RequestBody DomainEvent event) {
        return ResponseEntity.ok(event.getClass().getSimpleName());
    }
}
```

Test both payloads over HTTP and confirm the right subtype is chosen. This test catches discrepancies between a unit test mapper and the mapper used by MVC.

### 10.4. Running on the Native Executable

Workflow:

1. Run the full unit/integration test suite on the JVM.
2. Enable Spring AOT and verify that registrars and binding hint annotations are discovered.
3. Build the GraalVM Native Image via Maven or Gradle according to project configuration.
4. Start the native executable and call the endpoint with payloads for **every subtype**.
5. Send payloads with nested polymorphism and immutable/record DTOs if the application uses them.
6. Send an unknown type ID to confirm the fail-closed policy.
7. Compare subtype classes, field values, HTTP statuses, and responses between JVM and native.

A successful build does not prove every subtype is registered. A single subtype may only fail when its specific payload arrives; therefore, tests must cover every type ID the API commits to supporting.

## 11. Common Errors and Troubleshooting

| Symptom | Cause to Check | Resolution |
| --- | --- | --- |
| `InvalidTypeIdException` | Type ID unmapped or misspelled | Check `@JsonSubTypes`, `@JsonTypeName`, or `NamedType` |
| Deserializes on JVM but fails in native | Subtype/constructor/accessor missing binding metadata | Register root type and concrete subtypes with binding hints |
| Base type retained yet subtype fails to instantiate | Subtype appears only in JSON or a dynamic registry | Declare the subtype set explicitly and ensure classes are present at build time |
| Subtype fields are null or missing data | Getter/setter, field visibility, creator, or JSON property mismatch | Check the Jackson model and member access hints |
| Record subtype fails on native | Canonical constructor or binding metadata not fully supported | Check Jackson/Spring versions, add binding hints, and run native tests |
| Nested subtype fails | Nested hierarchy lacks mapping or hints | List subtypes for each base type and test nested payloads |
| Custom deserializer is not called | Module not registered in Spring's mapper | Register module via Spring config and test HTTP converters |
| New type ID fails only after deployment | Native binary was built before the new subtype existed | Rebuild binary with the new subtype and metadata |
| Unknown type ID creates unintended default object | `defaultImpl` or custom fallback is too permissive | Pick a clear unknown-type policy, failing closed when appropriate |
| Reflection constructor error | Dynamically invoked constructor lacks hints | Register required constructor or use binding hints |
| Error occurs only at MVC endpoint | Test used a different mapper from production | Verify via Spring context / HTTP integration tests |

## 12. Process for Managing Subtype Sets During API Development

When adding a new subtype, follow this sequence:

1. Identify the base type and logical type ID.
2. Add the concrete subtype and verify schema/validation.
3. Update `@JsonSubTypes` or the Jackson module registry.
4. Update binding hints for the subtype and any nested DTOs if needed.
5. Add serialization/deserialization tests for the new type ID.
6. Add an unknown type ID test and verify backward compatibility.
7. Run Spring AOT, build native, and verify endpoints on the binary.
8. Release API schema/documentation alongside the subtype change.

The subtype set must be a **version-managed allowlist**. When a new subtype is added, rebuild the native executable and release the corresponding artifact. If requirements call for installing new plugins post-deployment without rebuilding, Native Image's closed-world model is ill-suited to that kind of arbitrary class loading; consider splitting plugins into separate services/processes or using a predefined extension mechanism.

## 13. Lab Exercise: Building an API Accepting Multiple Event Types

**Context:** the `POST /events` API accepts `DomainEvent`. There are two event types, `OrderCreated` and `PaymentRejected`; each subtype has its own fields.

**Steps:**

1. Create base type `DomainEvent` and declare `@JsonTypeInfo(use = Id.NAME, property = "eventType")`.
2. Register `OrderCreated` with ID `order-created`, and `PaymentRejected` with ID `payment-rejected`.
3. Create corresponding JSON payloads and test deserialization through the base type.
4. Add `@RegisterReflectionForBinding` for the base type and all subtypes; include nested DTOs if any.
5. If using a Jackson Module instead of `@JsonSubTypes`, provide the module via Spring configuration and test the real mapper.
6. Write an invalid type ID test to confirm the payload is rejected.
7. Run tests through an HTTP endpoint to verify the Spring MVC message converter.
8. Build the Native Image, send each payload to the executable, and compare subtype/field values against the JVM.
9. Add a new subtype, update registry/hints/tests, and rebuild the native image.
10. Document the supported type ID list and release process when subtypes change.

**Passing criteria:**

- Type discriminator is explicitly defined and independent of Java class names.
- Only subtypes in the allowlist are deserialized.
- Base type, concrete subtypes, and nested DTOs have appropriate binding metadata.
- Unit tests and HTTP integration tests pass on the JVM.
- The native executable deserializes every supported subtype.
- Unknown type IDs are handled according to API policy.
- Adding a new subtype entails updating the registry, hints, tests, and native artifact.

## 14. Summary

Polymorphic deserialization allows a JSON base type to be converted into multiple concrete subtypes via a type discriminator. With Jackson, the subtype set can be declared using `@JsonTypeInfo`/`@JsonSubTypes`, `@JsonTypeName`, or registered in a Module. With Spring Boot Native Image, subtypes and related binding types must be known before build time; use `@RegisterReflectionForBinding` or `RuntimeHintsRegistrar` when existing AOT mechanisms do not supply enough metadata.

Use logical type IDs with an allowlist, avoid dynamic class names from untrusted payloads, and test every subtype on the actual native executable. When subtypes change, update the registry, binding hints, and tests, then rebuild the binary. Explicit management of the subtype set keeps JSON contracts stable and enables GraalVM to accurately analyze the types the application can instantiate at runtime.
