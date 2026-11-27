# Jackson with DTOs, Records, Enums, and Dynamically Accessed Members

In a Spring Boot application, Jackson typically converts JSON into DTOs when receiving requests and converts objects into JSON when returning responses or calling external services. To do that, Jackson must discover the type's structure: constructors, constructor parameters, fields, getters, setters, record components, enum constants, and methods marked with annotations. Some access paths are only performed **dynamically via reflection**.

On the JVM, these accesses usually work thanks to available class metadata. With **GraalVM Native Image**, reachability analysis occurs at build time; constructors, fields, or methods invoked by Jackson solely via reflection must be recognized and properly registered. Consequently, a DTO may deserialize fine from a JAR yet fail when running as a native executable.

This lesson belongs to the **Binding and JSON** chapter of the **`SPRING_BOOT_NATIVE_IMAGE`** module. It focuses on how Jackson works with POJOs, records, enums, nested DTOs, polymorphism, and dynamically accessed members; how Spring AOT infers reflection hints; and how to test real JSON behavior in a native application. This is an essential practical part of the module's objective: compiling Spring Boot with Spring AOT, handling reflection/resources, verifying compatibility, container packaging, and evaluating startup/memory.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why Jackson needs specific members when serializing and deserializing DTOs.
- Design DTOs as POJOs or Java records with clear constructors and properties.
- Map enums to stable JSON values using annotations.
- Understand `@JsonAnyGetter`, `@JsonAnySetter`, `@JsonCreator`, `@JsonValue`, and polymorphic type metadata.
- Identify non-obvious reflection accesses in custom serializers, mixins, and client libraries.
- Distinguish hints automatically inferred by Spring AOT from hints that must be registered explicitly.
- Test both JSON → object and object → JSON directions on the native executable.

## 2. How Does Jackson View a DTO?

Jackson builds a property model from the members it detects on a class:

| Member | Common Role |
|---|---|
| Constructor or factory method | Instantiates the object during deserialization |
| Constructor parameter | Receives JSON values to create an immutable object |
| Getter | Reads values during serialization |
| Setter | Assigns values during deserialization into a mutable object |
| Field | Can be used directly if visibility/configuration permits |
| Record component | Represents both the property and canonical constructor parameter |
| Enum constant / annotated method | Maps the enum to a JSON name or value |
| Method with `@JsonAnyGetter` / `@JsonAnySetter` | Reads/writes dynamic properties not declared as fixed fields |

Jackson can discover members via naming conventions, annotations, or visibility configuration. For example, `getCustomerId()` is normally treated as the getter for property `customerId`; `setCustomerId(String)` is the corresponding setter. If a class only has private fields without suitable constructors or properties, how Jackson accesses it depends on annotations and mapper configuration.

**Serialization** and **deserialization** go in two different directions:

- Serialize: Jackson reads values from getters, fields, or record components and writes them as JSON.
- Deserialize: Jackson reads JSON tokens, selects a constructor/factory method or instantiates the object, and assigns values via constructors, setters, or fields.

A class can succeed in serializing yet fail in deserializing, or vice versa. When testing Native Image, verify both directions if the application uses both.

## 3. POJO DTOs: Constructors, Getters, Setters, and Fields

The `com.fasterxml.jackson.*` imports in the POJO/record/enum examples below illustrate **Jackson 2** (commonly used with Spring Boot 3.x). With Jackson 3, the corresponding annotations live in the `tools.jackson.annotation` package; keep annotations, mappers, and modules aligned on the same major version.

A simple POJO can be recognized by Jackson using JavaBean conventions:

~~~java
package com.example.orders.api;

public class OrderRequest {

    private String customerId;
    private int quantity;

    public OrderRequest() {
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }
}
~~~

With this structure, Jackson typically invokes the no-arg constructor and calls setters to populate data. During serialization, Jackson reads getters to obtain values.

Input JSON:

~~~json
{
  "customerId": "C-100",
  "quantity": 3
}
~~~

The resulting object has `customerId = "C-100"` and `quantity = 3`.

### Renaming JSON Properties

If the external API uses different names from the Java names, use `@JsonProperty`:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public class OrderRequest {

    @JsonProperty("customer_id")
    private String customerId;

    @JsonProperty("item_count")
    private int quantity;

    public OrderRequest() {
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }
}
~~~

`@JsonProperty` can be placed on a field, getter, setter, or creator parameter. Place the annotation in one clear location to avoid duplicate property definitions or conflicts between fields and accessors.

### Accepting Old Names with Aliases

When an API is migrating from `customerId` to `customer_id`, you can accept both during the transition period:

~~~java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public class OrderRequest {
    @JsonProperty("customer_id")
    @JsonAlias("customerId")
    private String customerId;

    // Constructor, getters, and setters...
}
~~~

`@JsonAlias` mainly helps when **reading** alternative input names; the name written during serialization still follows the primary property name. This is useful for backward compatibility with older payloads.

### Specifying a Constructor Explicitly

For immutable DTOs without setters, use `@JsonCreator` and `@JsonProperty` to specify how the object is created:

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;

public class ImmutableOrder {

    private final String orderId;
    private final int quantity;

    @JsonCreator
    public ImmutableOrder(
            @JsonProperty("order_id") String orderId,
            @JsonProperty("quantity") int quantity) {
        this.orderId = orderId;
        this.quantity = quantity;
    }

    public String getOrderId() {
        return orderId;
    }

    public int getQuantity() {
        return quantity;
    }
}
~~~

Jackson must recognize the constructor and its parameters. In a native executable, if the instantiation path relies on reflection without being covered by hints, deserialization can fail as soon as a request arrives.

**Do not rely implicitly on constructor parameter names** if the build does not preserve parameter names or the mapper does not have the corresponding feature enabled. The `@JsonProperty` annotation makes the JSON contract explicit and less dependent on compiler flags.

## 4. Java Records: More Concise Immutable DTOs

A Java record declares data through record components:

~~~java
public record OrderRequest(
        String customerId,
        int quantity) {
}
~~~

Jackson supports records in modern versions. When deserializing, Jackson uses the canonical constructor and record components; when serializing, it reads the component values.

JSON:

~~~json
{
  "customerId": "C-100",
  "quantity": 3
}
~~~

Records do not need JavaBean-style getters and setters. Accessors are generated automatically matching the component names, such as `customerId()` and `quantity()`.

### Renaming Record Components in JSON

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public record OrderRequest(
        @JsonProperty("customer_id") String customerId,
        @JsonProperty("item_count") int quantity) {
}
~~~

Placing the annotation directly on the component lets Jackson map JSON names to canonical constructor parameters.

### Records with Nested DTOs

~~~java
public record AddressDto(String city, String country) {
}

public record CustomerDto(
        String customerId,
        AddressDto address) {
}

public record OrderLineDto(String sku, int quantity) {
}

public record OrderResponse(
        String orderId,
        CustomerDto customer,
        List<OrderLineDto> lines) {
}
~~~

When registering reflection hints for the outermost type, Spring binding hints can handle types used transitively in properties and record components. However, subtypes selected by a discriminator, dynamically loaded types, or members accessed via library-specific rules must be verified independently.

### Records Do Not Automatically Solve Every JSON Problem

Records are well suited for immutable DTOs, but keep in mind:

- Each component is part of the canonical constructor; payloads missing fields may yield default values or errors depending on type and configuration.
- Nested records must have their types properly recognized by Jackson.
- When using polymorphism, concrete subtypes still need to be configured and tested.
- Custom serializers/deserializers may access members in their own ways.
- A record component with a complex generic type does not eliminate the need to verify type information.

## 5. Enums: Java Names and JSON Values

By default, Jackson usually maps enums by constant name. For example:

~~~java
public enum OrderStatus {
    NEW,
    PROCESSING,
    COMPLETED,
    CANCELLED
}
~~~

The JSON might contain `"PROCESSING"`.

### Using `@JsonProperty` on Each Enum Constant

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public enum OrderStatus {
    @JsonProperty("new")
    NEW,

    @JsonProperty("in-progress")
    PROCESSING,

    @JsonProperty("done")
    COMPLETED,

    @JsonProperty("cancelled")
    CANCELLED
}
~~~

This is a readable approach when each constant maps to a fixed JSON string.

### Using `@JsonValue` When an Enum Has a Custom Code

~~~java
import com.fasterxml.jackson.annotation.JsonValue;

public enum PaymentState {
    PENDING("P"),
    APPROVED("A"),
    DECLINED("D");

    private final String code;

    PaymentState(String code) {
        this.code = code;
    }

    @JsonValue
    public String code() {
        return code;
    }
}
~~~

When serialized, `PaymentState.APPROVED` is written as `"A"` instead of `"APPROVED"`. To deserialize a code string back into an enum, you can define a factory method:

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum PaymentState {
    PENDING("P"),
    APPROVED("A"),
    DECLINED("D");

    private final String code;

    PaymentState(String code) {
        this.code = code;
    }

    @JsonValue
    public String code() {
        return code;
    }

    @JsonCreator
    public static PaymentState fromCode(String code) {
        for (PaymentState state : values()) {
            if (state.code.equals(code)) {
                return state;
            }
        }
        throw new IllegalArgumentException("Unknown payment state: " + code);
    }
}
~~~

Here, `@JsonValue` determines the output value, while `@JsonCreator` specifies how to parse the input value. Explicitly define how unknown codes, `null`, letter casing, and legacy data are handled according to the API contract.

### Enums and Native Image

Enums are usually simpler to handle than object types with many members, but do not assume every access path is static. If a serializer uses reflection to invoke a factory method, custom enum converter, or load subtypes by name, verify those members in the native build. Avoid registering broad reflection hints just because an enum is used in JSON; start with native tests and actual diagnostics.

## 6. Dynamically Accessed Members: `@JsonAnyGetter` and `@JsonAnySetter`

Some APIs allow objects to carry extra attributes unknown at compile time. Jackson provides `@JsonAnyGetter` and `@JsonAnySetter` to handle these extensible attributes.

~~~java
import com.fasterxml.jackson.annotation.JsonAnyGetter;
import com.fasterxml.jackson.annotation.JsonAnySetter;
import java.util.LinkedHashMap;
import java.util.Map;

public class PartnerPayload {

    private String partnerId;
    private final Map<String, Object> attributes = new LinkedHashMap<>();

    public String getPartnerId() {
        return partnerId;
    }

    public void setPartnerId(String partnerId) {
        this.partnerId = partnerId;
    }

    @JsonAnySetter
    public void addAttribute(String name, Object value) {
        attributes.put(name, value);
    }

    @JsonAnyGetter
    public Map<String, Object> attributes() {
        return attributes;
    }

    public String calculateSignature() {
        return partnerId + ":" + attributes.size();
    }
}
~~~

With the payload:

~~~json
{
  "partnerId": "P-42",
  "region": "apac",
  "priority": 2,
  "enabled": true
}
~~~

`partnerId` goes into the fixed property; the keys `region`, `priority`, and `enabled` are routed into the `attributes` map. When serializing, `@JsonAnyGetter` flattens the map entries to the same level as `partnerId`.

### Why Is This Dynamic Access?

Jackson invokes annotated methods to handle properties for which the class declares no individual getter or setter per key. Key names and value types are determined from JSON at runtime. In Native Image, ensure these methods and the map's backing types are properly accessible.

If `@RegisterReflectionForBinding(PartnerPayload.class)` is not enough for a particular method under a serializer configuration, read the diagnostics to identify the missing method. You can register an invocation hint for that exact method via `RuntimeHintsRegistrar`; avoid exposing all private methods in a package when only two annotated methods are needed.

### Do Not Use `Map<String, Object>` While Skipping Data Validation

`Object` can represent a string, number, boolean, nested map, or nested list. If business logic requires concrete types, validate and convert values after parsing, or define explicit DTOs for the known portion of the data. Reflection hints do not validate schemas and do not replace validation.

## 7. Nested DTOs, Collections, and Generic Types

JSON often contains nested objects or lists:

~~~java
public record OrderLine(
        String sku,
        int quantity,
        BigDecimal unitPrice) {
}

public record OrderRequest(
        String orderId,
        List<OrderLine> lines,
        Map<String, String> labels) {
}
~~~

Jackson can infer elements of `List<OrderLine>` and value types of `Map<String, String>` from generic signatures when compilation preserves the necessary metadata. However, if code passes `Object.class`, uses raw `List.class`, or constructs types by class name at runtime, generic information can be lost.

Example reading a list directly:

~~~java
List<OrderLine> lines = objectMapper.readValue(
        json,
        new TypeReference<List<OrderLine>>() {});
~~~

`TypeReference` retains the generic type so Jackson knows the element type is `OrderLine`. In the native executable, verify both the wrapper type and element types when generic types are constructed dynamically or via library APIs inside a method body.

In Jackson 3, the type-reference API serves a similar role, though exact packages and APIs depend on the module in use. Avoid mixing Jackson 2's `com.fasterxml.jackson.*` with Jackson 3's `tools.jackson.*` in the same mapper.

## 8. Polymorphic DTOs: Interfaces and Multiple Subtypes

A DTO may declare a property using an interface while JSON contains multiple implementations:

~~~java
public interface PaymentMethod {
}

public record CardPayment(String lastFourDigits) implements PaymentMethod {
}

public record BankTransfer(String bankCode) implements PaymentMethod {
}

public record PaymentRequest(String paymentId, PaymentMethod method) {
}
~~~

So Jackson knows which subtype corresponds to a discriminator, you can use `@JsonTypeInfo` and `@JsonSubTypes`:

~~~java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "kind")
@JsonSubTypes({
        @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
        @JsonSubTypes.Type(value = BankTransfer.class, name = "bank")
})
public interface PaymentMethod {
}
~~~

JSON:

~~~json
{
  "paymentId": "PAY-900",
  "method": {
    "kind": "card",
    "lastFourDigits": "4242"
  }
}
~~~

Native Image must retain the concrete subtypes and the constructors/properties Jackson requires. If AOT does not infer the subtypes from serializer configuration, register them explicitly, for example:

~~~java
@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding({
        PaymentRequest.class,
        CardPayment.class,
        BankTransfer.class
})
class PaymentJsonHints {
}
~~~

`@RegisterReflectionForBinding` provides reflection hints for binding types; it **does not configure discriminators**, does not validate allowed subtypes, and does not replace `@JsonTypeInfo`/`@JsonSubTypes`. For untrusted external data, allow only controlled subtypes; do not enable arbitrary class loading from user-supplied names.

## 9. Custom Serializers, Deserializers, and Mixins

Jackson can call a custom serializer/deserializer instead of introspecting a DTO itself. This is where dynamic access to other members often arises.

### Jackson 2 with Spring Boot 3.x

Spring Boot 3.x integrates Jackson 2 via `ObjectMapper`, `JsonSerializer`, and `JsonDeserializer`. Components can be registered with `@JsonComponent`:

~~~java
import java.io.IOException;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;
import org.springframework.boot.jackson.JsonComponent;

@JsonComponent
public class MoneyJsonComponent {

    public static class Serializer extends JsonSerializer<Money> {
        @Override
        public void serialize(
                Money value,
                JsonGenerator generator,
                SerializerProvider serializers) throws IOException {
            generator.writeString(value.currency() + " " + value.amount());
        }
    }
}
~~~

`@JsonComponent` lets Spring Boot discover and register serializers/deserializers via auto-configuration. If a custom component uses reflection to invoke fields/methods or access classes by name, evaluate separate hints.

### Jackson 3 with Spring Boot 4.x

Spring Boot 4.x defaults to Jackson 3; the API uses `tools.jackson.*` packages, the default mapper bean is `JsonMapper`, and Spring Boot provides `@JacksonComponent` along with `ValueSerializer`/`ValueDeserializer`:

~~~java
import tools.jackson.core.JsonGenerator;
import tools.jackson.databind.SerializationContext;
import tools.jackson.databind.ValueSerializer;
import org.springframework.boot.jackson.JacksonComponent;

@JacksonComponent
public class MoneyJsonComponent {

    public static class Serializer extends ValueSerializer<Money> {
        @Override
        public void serialize(
                Money value,
                JsonGenerator generator,
                SerializationContext context) {
            generator.writeString(value.currency() + " " + value.amount());
        }
    }
}
~~~

Spring Boot automatically registers `@JacksonComponent` beans in the ApplicationContext. Jackson 3's custom serializer syntax differs from Jackson 2; do not copy a Jackson 2 `JsonSerializer` class verbatim into a Jackson 3 project.

### Mixins

Mixins let you add Jackson annotations to classes the team cannot modify, such as classes from dependencies or third-party models. Spring Boot supports mixin discovery via dedicated annotations:

- Spring Boot 3.x / Jackson 2: `@JsonMixin`.
- Spring Boot 4.x / Jackson 3: `@JacksonMixin`.

Mixins change how Jackson sees properties, but they do not automatically guarantee that every member is retained by Native Image. If a mixin causes Jackson to access uninferred fields or constructors, register hints for the target type and test it.

## 10. Jackson 2 and Jackson 3: Avoid Mixing Packages

The Jackson version depends on Spring Boot and actual dependencies:

| Platform | Primary Mapper | Common Packages | Spring Boot Component Annotation |
|---|---|---|---|
| Spring Boot 3.x / Jackson 2 | `com.fasterxml.jackson.databind.ObjectMapper` | `com.fasterxml.jackson.*` | `@JsonComponent` |
| Spring Boot 4.x / Jackson 3 | `tools.jackson.databind.json.JsonMapper` | `tools.jackson.*` | `@JacksonComponent` |

Spring Boot 4.x currently favors Jackson 3. Current Spring Boot documentation describes Jackson 2 support as a migration compatibility path that will be removed in a future Spring Boot 4.x release. Therefore:

- Boot 3.x projects typically use Jackson 2's `ObjectMapper`.
- Boot 4.x projects should use `JsonMapper`/Jackson 3 as configured by default.
- Do not mix annotations, serializers, modules, or mappers from the two major versions.
- Check the dependency tree to confirm the actual mapper; do not guess from import names in an old file.

The `@JsonProperty`, `@JsonCreator`, `@JsonValue`, `@JsonAnyGetter`, and `@JsonAnySetter` examples in this lesson illustrate general binding patterns. When moving to Jackson 3, use the annotations from the project's Jackson 3 package set and verify the exact version API.

## 11. When Does Spring AOT Automatically Infer Hints for Jackson?

Spring AOT analyzes the ApplicationContext and known contracts. Some JSON types are inferred automatically by the framework:

- Parameter and return types of `@RestController` methods are normally inspected by Spring; if serialization/binding needs are detected, Spring can contribute reflection hints.
- `@ConfigurationProperties` has its own AOT mechanism for configuration binding.
- Popular libraries may ship Native Image-compatible reachability metadata.

However, when calling `WebClient`, `RestClient`, or `RestTemplate` directly inside a method body, the DTO type might not appear in any controller signature. In that case, Spring Boot recommends using `@RegisterReflectionForBinding` on the bean requiring the data type:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class PartnerClient {

    private final WebClient webClient;

    public PartnerClient(WebClient webClient) {
        this.webClient = webClient;
    }

    @RegisterReflectionForBinding(PartnerOrder.class)
    public Mono<PartnerOrder> getOrder(String id) {
        return webClient.get()
                .uri("/orders/{id}", id)
                .retrieve()
                .bodyToMono(PartnerOrder.class);
    }
}
~~~

The annotation tells Spring that reflection hints are needed for `PartnerOrder` and related binding types. It does not automatically register resources, JDK proxies, or custom serializer logic unrelated to binding.

### `@ConfigurationProperties` DTOs Are a Separate Case

Spring Boot AOT automatically generates reflection hints for recognized configuration properties. For a nested configuration property whose type is an external class (not an inner class), Spring Boot needs `@NestedConfigurationProperty` to recognize the nested structure. Where to place the annotation depends on the binding style:

- For mutable JavaBeans, place it on the nested field or corresponding getter.
- For constructor binding, place it on the corresponding field.
- For Java records, place it on the record component parameter.

This is a Spring Boot configuration binding annotation, **not a Jackson annotation**.

Do not use `@RegisterReflectionForBinding` as a default substitute for `@NestedConfigurationProperty` in `@ConfigurationProperties` configuration. Use the appropriate mechanism for each kind of binding.

## 12. Reflection Hints for Dynamically Accessed Members

When Jackson calls getters, setters, or constructors through introspection, binding hints for the DTO are usually the starting point. However, a custom module might invoke additional methods, for example:

~~~java
Method method = target.getClass().getDeclaredMethod("calculateSignature");
method.invoke(target);
~~~

This is a general reflection call, not merely property binding. If Spring AOT or a library has not contributed hints, register the needed member using `RuntimeHintsRegistrar`:

~~~java
import java.lang.reflect.Method;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.util.ReflectionUtils;

public class PartnerRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        Method method = ReflectionUtils.findMethod(
                PartnerPayload.class, "calculateSignature");
        if (method != null) {
            hints.reflection().registerMethod(method, ExecutableMode.INVOKE);
        }
    }
}
~~~

Register the registrar with `@ImportRuntimeHints(PartnerRuntimeHints.class)` on a bean or configuration processed by Spring AOT.

The example above only registers invocation for the located method. If a library needs access to constructors, fields, methods for introspection, or resources, choose the hint type matching that operation. **Do not register all declared members just to make the build pass** before understanding why the library needs them.

### Private Fields and Visibility

Jackson can be configured to inspect private fields, though this changes access scope. Before opening visibility broadly:

1. Prefer public constructors, getters/setters, or record components.
2. If the API mandates private fields, identify the exact fields to read/write.
3. Inspect `@JsonAutoDetect`, `@JsonProperty(access = ...)`, and mapper configuration.
4. Ensure reflection hints for the appropriate fields/accessors.
5. Run deserialization and serialization inside the native executable.

Avoid configuring global visibility so Jackson accesses every private field of every DTO; doing so makes JSON contracts harder to control and increases unnecessary metadata.

## 13. Testing JSON and Runtime Hints

### 13.1. Testing on the JVM

A basic test should verify both deserialization and serialization:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import tools.jackson.annotation.JsonProperty;
import tools.jackson.databind.json.JsonMapper;

record OrderDto(
        @JsonProperty("order_id") String orderId,
        String status) {
}

@SpringBootTest
class OrderJsonTests {

    @Autowired
    JsonMapper jsonMapper; // Jackson 3

    @Test
    void shouldReadAndWriteOrder() throws Exception {
        String json = """
                {
                  "order_id": "O-100",
                  "status": "processing"
                }
                """;

        OrderDto order = jsonMapper.readValue(json, OrderDto.class);
        assertThat(order.orderId()).isEqualTo("O-100");
        assertThat(order.status()).isEqualTo("processing");

        String written = jsonMapper.writeValueAsString(order);
        assertThat(written).contains("\"order_id\":\"O-100\"");
        assertThat(written).contains("\"status\":\"processing\"");
    }
}
~~~

For Jackson 2, inject `ObjectMapper` instead of `JsonMapper` and use Jackson 2 annotations/packages. This test verifies the JSON contract on the JVM; it **does not prove** that Native Image has sufficient metadata.

### 13.2. Native Tests or Integration Tests on the Executable

Run tests using the native profile configured in the project, or build the executable and invoke the real endpoints:

~~~bash
# Example Maven native profile already declared
./mvnw -Pnative native:compile

# Example Gradle native task already configured
./gradlew nativeCompile
~~~

Then run the binary and send payloads containing:

- POJOs with constructors/setters.
- Records with nested records/lists.
- Enums with custom JSON values.
- Dynamic properties via `@JsonAnySetter`.
- Polymorphic subtypes if the API has a discriminator.

Tests should verify the JSON response and parsed data state. Seeing a native build succeed is not enough; many reflection errors only surface when the specific code path executes.

### 13.3. Verifying Runtime Hints with Unit Tests

If the application has a custom `RuntimeHintsRegistrar`, use `RuntimeHintsPredicates` to verify the hint was registered:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

@Test
void shouldRegisterSignatureMethodHint() {
    RuntimeHints hints = new RuntimeHints();
    new PartnerRuntimeHints().registerHints(hints, getClass().getClassLoader());

    assertThat(RuntimeHintsPredicates.reflection()
            .onMethod(PartnerPayload.class, "calculateSignature")
            .invoke())
            .accepts(hints);
}
~~~

The snippet uses the Spring Framework 6.x predicate API. Newer Spring Framework versions may provide specialized methods such as `onMethodInvocation`; check your actual dependency Javadoc. This type of test verifies that the registrar contributes the hint, while native integration tests verify the entire pipeline and end-to-end behavior.

### 13.4. Using the GraalVM Tracing Agent When Needed

When a third-party library performs reflection, resource lookups, or proxying not inferred by AOT, the tracing agent can record operations that occurred during a JVM run. You must run tests or real interactions that exercise all relevant code branches.

The JSON files generated by the agent are only **observed evidence from that run**, not an automatic complete configuration for every environment. Review and remove entries belonging solely to test infrastructure before committing metadata to source.

## 14. Diagnosing Jackson Errors on Native Image

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Deserialization reports no suitable constructor found | Constructor/creator unrecognized by Jackson or missing reflection hint | Use an explicit constructor, `@JsonCreator`/`@JsonProperty`, and check hints |
| Record works on JVM but fails in native | Canonical constructor/record component metadata was not retained | Check binding hints for the record and nested types |
| Enum cannot read API value | JSON value differs from enum name or `@JsonCreator` does not handle that code | Use `@JsonProperty`, `@JsonValue`, or an explicit factory method |
| Getter/setter or private field cannot be accessed | Visibility or field hints are incorrect | Prefer public accessors; register exact members if needed |
| `@JsonAnyGetter`/`@JsonAnySetter` does not work | Specialized method or custom serializer needs invocation hints | Inspect the invoked method and register a narrow hint |
| Polymorphic subtype is not instantiated | Concrete subtype unrecognized/unregistered or wrong discriminator | Declare subtypes, reflection hints, and type metadata configuration |
| DTO used in WebClient/RestClient fails in native | AOT did not infer type from method body | Use `@RegisterReflectionForBinding` on the appropriate bean/method |
| Schema/template file not found | Resource was not packaged | Register resource hints; binding hints do not include files |
| Jackson module/serializer is not invoked | Module/component not registered in mapper | Check Spring component scan, `@JsonComponent`/`@JacksonComponent`, or module setup |

### Investigation Workflow

1. Reproduce the error with the smallest payload on the native executable.
2. Determine whether the error occurs during deserialization or serialization.
3. Identify the exact DTO, constructor, field, property, enum, or method being accessed.
4. Check whether the type appears in a controller signature or only inside a method body/client.
5. Inspect Spring AOT hints and metadata from dependencies.
6. Add the right kind of binding hint, reflection hint, or resource hint.
7. Rebuild native and re-run the exact payload that triggered the failure.

Do not add a huge reflection config file for the entire model package before identifying the missing member. Overly broad hints enlarge the reflection surface, mask design bugs, and make metadata hard to maintain.

## 15. Capstone Example: Calling a Partner with WebClient

Suppose a partner returns JSON:

~~~json
{
  "order_id": "O-901",
  "status": "in-progress",
  "customer": {
    "customer_id": "C-77"
  },
  "attributes": {
    "channel": "mobile",
    "campaign": "winter"
  }
}
~~~

The DTOs:

~~~java
public record CustomerDto(
        @JsonProperty("customer_id") String customerId) {
}

public enum OrderStatus {
    @JsonProperty("new")
    NEW,
    @JsonProperty("in-progress")
    PROCESSING,
    @JsonProperty("done")
    COMPLETED
}

public record PartnerOrder(
        @JsonProperty("order_id") String orderId,
        OrderStatus status,
        CustomerDto customer,
        Map<String, Object> attributes) {
}
~~~

Client:

~~~java
@Component
public class PartnerOrderClient {

    private final WebClient webClient;

    public PartnerOrderClient(WebClient webClient) {
        this.webClient = webClient;
    }

    @RegisterReflectionForBinding(PartnerOrder.class)
    public Mono<PartnerOrder> getOrder(String id) {
        return webClient.get()
                .uri("/orders/{id}", id)
                .retrieve()
                .bodyToMono(PartnerOrder.class);
    }
}
~~~

Spring AOT can handle nested types used on properties and record components of `PartnerOrder`. If a serializer or dynamic generic access needs additional subtypes, register those concrete types and test them. `attributes` is a dynamic map; if object values use custom types or custom deserializers, verify how Jackson constructs those values.

Verification workflow:

1. Run JVM tests with the payload above.
2. Build AOT/native using the project's Maven or Gradle setup.
3. Call the endpoint/service using the native executable.
4. Verify `orderId`, `status`, `customer.customerId`, and the `attributes` map.
5. Serialize the returned object and compare property names against the JSON contract.
6. If only native fails, read diagnostics to pinpoint which constructor, property, subtype, or method is missing hints.

## 16. Self-Check Exercises

**Question 1.** Which members does Jackson normally use to serialize a POJO?

**Hint:** getters, fields, or property accessors recognized by convention and mapper configuration.

**Question 2.** Which members does Jackson normally use to deserialize a mutable POJO?

**Hint:** a constructor to instantiate the object, followed by setters or field access to assign data.

**Question 3.** Why are records well suited for immutable DTOs?

**Hint:** records declare components and a canonical constructor explicitly; Jackson can use them for both serialization and deserialization.

**Question 4.** Which two directions do `@JsonValue` and `@JsonCreator` handle?

**Hint:** `@JsonValue` specifies the output value; `@JsonCreator` specifies how to construct the enum/object from an input value.

**Question 5.** When is `@JsonAnySetter` used?

**Hint:** when JSON contains dynamic keys not declared as fixed properties; the method receives the key name and value to store in an extensible structure.

**Question 6.** Why might `WebClient` need `@RegisterReflectionForBinding` even when controllers already work in native?

**Hint:** DTO types used inside a client method body may not appear in any controller signature for Spring AOT to infer automatically.

**Question 7.** If a JSON schema file is missing in the native executable, should you add `@RegisterReflectionForBinding` for the DTO?

**Hint:** no. DTOs need binding hints; schema files need resource hints.

**Question 8.** Does `@JsonTypeInfo` automatically register reflection hints for all subtypes?

**Hint:** the annotation configures Jackson polymorphic type handling; you still need to check concrete subtypes and Native Image metadata.

## 17. Pre-Release Checklist

- [ ] Identify the Jackson major version and packages in use; do not mix Jackson 2 and Jackson 3.
- [ ] POJO DTOs have explicit constructors/getters/setters.
- [ ] Record components and canonical constructors are tested with real payloads.
- [ ] Enum JSON values are stable and handle invalid values consistently.
- [ ] `@JsonAnyGetter`/`@JsonAnySetter` and dynamically accessed methods are tested.
- [ ] Nested DTOs, generic collections/maps, and polymorphic subtypes are verified.
- [ ] Custom serializers/deserializers/mixins/modules are registered properly for the Spring Boot/Jackson version.
- [ ] DTOs used in `WebClient`/`RestClient`/`RestTemplate` have binding hints when AOT cannot infer them automatically.
- [ ] Reflection hints and resource hints are kept distinct and registered for the right purpose.
- [ ] Both JVM tests and native tests/integration tests exist for serialization and deserialization.
- [ ] Edge payloads are tested: missing fields, `null`, unknown enums, empty nested objects, and dynamic keys.
- [ ] Native executable/container is tested in an environment matching deployment.

## 18. References

- [Spring Boot Reference — JSON](https://docs.spring.io/spring-boot/reference/features/json.html): Jackson 3, Jackson 2, custom serializers/deserializers, `@JacksonComponent`, and mixins.
- [Spring Boot Reference — Advanced Native Images Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html): binding hints, `@RegisterReflectionForBinding`, RuntimeHints, and testing hints.
- [Spring Boot 3.5 — Advanced Native Images Topics](https://docs.spring.io/spring-boot/3.5/reference/packaging/native-image/advanced-topics.html): nested configuration properties and AOT/native notes for Spring Boot 3.x.
- [Jackson 2 Javadoc — JsonProperty](https://www.javadoc.io/static/com.fasterxml.jackson.core/jackson-annotations/2.21/com/fasterxml.jackson/annotation/JsonProperty.html): logical property and enum mapping.
- [Jackson 3 Javadoc — MapperFeature](https://javadoc.io/doc/tools.jackson.core/jackson-databind/latest/tools/jackson/databind/MapperFeature.html): constructor/factory method parameter name detection and record properties.

**Remember:** Jackson does not merely read field names; it can invoke constructors, getters, setters, record accessors, enum factories, and dynamic methods to map JSON. Spring AOT infers many types from controllers and known configurations, but DTOs used inside clients or custom serializers may need explicit hints. Choose the right DTOs/members, distinguish binding from resources and general reflection, and verify both serialization and deserialization on the native executable.
