# @RegisterReflectionForBinding for Bound or Converted Data Types

When running a Spring Boot application on the JVM, libraries such as Spring MVC, Jackson, or binding mechanisms can use reflection to read constructors, fields, properties, getters/setters, and record components of a data type. With **GraalVM Native Image**, reflective accesses must be recognized and registered during the build phase. If a DTO is only used inside service or library code, Spring AOT may not fully infer which types must be retained.

**`@RegisterReflectionForBinding`** is a Spring Framework annotation used to register reflection hints for **data binding** or **reflection-based serialization** of specified data types. In the **Reflection** chapter of the **`SPRING_BOOT_NATIVE_IMAGE`** module, this lesson explains how to select DTOs, where to place the annotation, which members and nested types are registered, how to verify on the native executable, and when to use other hint mechanisms.

> **Version scope:** the annotation has been available since Spring Framework 6.0. In the Spring Framework 6.x line, the annotation is used on types or methods and requires specifying at least one target class via `value` or `classes`. Check the Javadoc for the exact Spring version your project uses.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why a DTO works well on the JVM but can lack reflection metadata in Native Image.
- Use `@RegisterReflectionForBinding` on a configuration class or Spring bean/method.
- Distinguish the `value` and `classes` attributes of the annotation.
- Understand hint coverage for constructors, fields, properties, record components, and transitively referenced types.
- Identify when to use the annotation for JSON, HTTP bodies, binding, or serialization.
- Distinguish binding hints from general reflection hints, resource hints, and converter configuration.
- Test to confirm the data types are actually accessible in the native executable.

## 2. Why Do Data Types Need Reflection Hints?

On the JVM, many frameworks can inspect class structure at runtime. For example, Jackson can read constructors or properties to deserialize JSON into objects; Spring can bind request data into DTOs; serialization libraries can read fields or record components.

Native Image performs **reachability analysis** at build time. It needs to know which constructors, fields, properties, or other components will be accessed via reflection. Components reached only indirectly via reflection may not be fully retained without appropriate metadata.

Example DTO:

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

If a binding library uses reflection to instantiate the object and assign properties, Native Image needs the corresponding hints. If the constructor or property access is not registered, errors may surface only when running the native executable, even though the exact same request succeeded on the JVM.

**Not every DTO needs to be registered manually with this annotation.** Spring Boot and framework integrations can automatically recognize many types from controller signatures, configuration properties, or known configurations. The annotation is useful when a data type is used in a place AOT cannot infer, such as a DTO passed to a serializer inside a service or client method body.

## 3. What Does the Annotation Do?

Package:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
~~~

The annotation registers appropriate reflection hints for each specified type. According to Spring Framework Javadoc, the handled component groups include:

- **Constructors:** constructors that may be needed to instantiate objects.
- **Fields:** fields participating in binding.
- **Properties:** Java properties read/written by the framework, typically involving getters/setters or property introspection.
- **Record components:** components of Java records.
- **Transitively used types:** types appearing in properties and record components of the registered type are also processed by the binding hints mechanism.

This scope is designed for **binding and reflection-based serialization**. It is not equivalent to opening full reflection on every method/private member of a class.

Spring recognizes the annotation during AOT processing and turns it into Runtime Hints. The Native Image build uses those aggregated hints to keep the necessary components. Do not assume each annotation always produces a separate `reflect-config.json` file; the output metadata format and location depend on the Spring/GraalVM version and build integration.

Configuration example:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding({OrderRequest.class, OrderResponse.class})
class OrderBindingHints {
}
~~~

When AOT processes this configuration class, Spring registers hints for `OrderRequest` and `OrderResponse` for binding purposes.

### `value` and `classes`

The two attributes are aliases of each other:

~~~java
@RegisterReflectionForBinding(OrderRequest.class)
~~~

Equivalent to:

~~~java
@RegisterReflectionForBinding(classes = OrderRequest.class)
~~~

Multiple types can be declared:

~~~java
@RegisterReflectionForBinding(
        classes = {OrderRequest.class, OrderResponse.class, CustomerDto.class})
~~~

Do not declare both `value` and `classes` for the same list. Pick one consistent style in your project.

## 4. Where Should the Annotation Be Placed?

Spring Framework allows using the annotation on a **type** or **method**. Typically, place it on a configuration class to centralize related DTOs, or on the bean/method actually using the data type to express its exact scope.

### 4.1. Placing on a Configuration Class

Suitable when multiple DTOs belong to the same API group or binding flow:

~~~java
package com.example.orders.config;

import com.example.orders.api.OrderRequest;
import com.example.orders.api.OrderResponse;
import com.example.orders.api.OrderLineDto;
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding({
        OrderRequest.class,
        OrderResponse.class,
        OrderLineDto.class
})
class OrderReflectionConfiguration {
}
~~~

The configuration class must be included in the `ApplicationContext` by Spring during AOT. If the class is not component-scanned, imported, or otherwise registered, simply placing the annotation on an unprocessed class will not produce hints.

### 4.2. Placing on a Spring Bean

Suitable when a service has a few data types needing binding/serialization:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.stereotype.Service;

@Service
@RegisterReflectionForBinding(PartnerResponse.class)
public class PartnerService {

    private final ObjectMapper objectMapper;

    public PartnerService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public PartnerResponse convert(String json) throws JsonProcessingException {
        // Example: convert JSON into PartnerResponse using a serializer.
        return objectMapper.readValue(json, PartnerResponse.class);
    }
}
~~~

Placing the annotation on the class ties hints to that bean, making it easy to find when investigating which service uses a DTO.

### 4.3. Placing on a Method

If only one method needs the data type, a method-level annotation clearly marks where it is used:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class PartnerClient {

    private final WebClient webClient;

    public PartnerClient(WebClient webClient) {
        this.webClient = webClient;
    }

    @RegisterReflectionForBinding(PartnerResponse.class)
    public Mono<PartnerResponse> fetchPartner() {
        return webClient.get()
                .uri("/partner")
                .retrieve()
                .bodyToMono(PartnerResponse.class);
    }
}
~~~

This example illustrates using a DTO inside a method body with `WebClient`. Spring AOT cannot always infer every type passed to a library API inside a method body. The annotation indicates the type requiring binding reflection hints.

A method-level annotation must be on a method belonging to a **Spring bean contributed to the context** so Spring's reflective processing picks it up. Do not put the annotation on an unmanaged helper class and expect AOT to discover it automatically.

### 4.4. Using on a Test Class

The annotation can also be placed on a test class using the Spring TestContext Framework to load an `ApplicationContext`:

~~~java
@SpringBootTest
@RegisterReflectionForBinding(OrderResponse.class)
class OrderNativeTests {

    @Test
    void shouldDeserializeOrder() {
        // Test binding/serialization with OrderResponse.
    }
}
~~~

This is useful when a test needs to bind a type that production configuration does not infer on its own. However, hints generated in a test context do not substitute for registering types required by the **production application context**. Place the annotation where appropriate for the artifact you need to test/release.

## 5. Nested Types and Record Components

Suppose a DTO contains other types:

~~~java
public record AddressDto(String city, String country) {
}

public record OrderLineDto(String sku, int quantity) {
}

public record CustomerDto(
        String customerId,
        AddressDto address) {
}

public record OrderResponse(
        String orderId,
        CustomerDto customer,
        List<OrderLineDto> lines) {
}
~~~

When registering `OrderResponse`, Spring's binding hints registrar handles record components and types transitively used within properties/record components. This reduces the need to manually list every nested type.

However, do not rely on assumptions about every generic type or every dynamic library access path. For collections, maps, polymorphic types, or serializers with custom rules, test with real data. If an implementation/subtype is selected by name or dynamic metadata and is not inferred by AOT, register the required types explicitly.

### Nested Types Do Not Mean Every Subtype Is Found Automatically

Example:

~~~java
public interface PaymentMethod {
}

public class CardPayment implements PaymentMethod {
    private String lastFourDigits;
}

public class BankTransfer implements PaymentMethod {
    private String bankCode;
}

public record PaymentDto(PaymentMethod method) {
}
~~~

If JSON contains a discriminator for the serializer to select `CardPayment` or `BankTransfer`, registering only `PaymentDto` should not be taken as proof that every subtype has been recognized. Check how Jackson or your serializer configures polymorphism and register the required subtypes:

~~~java
@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding({
        PaymentDto.class,
        CardPayment.class,
        BankTransfer.class
})
class PaymentBindingHints {
}
~~~

Registering subtypes does not configure polymorphic deserialization by itself. The serializer still needs appropriate type-info/allow-list configuration; hints only provide the reflection access required for Native Image.

## 6. Practical Example: JSON Used in WebClient

A common scenario is a DTO used in a service client that does not appear directly in a controller signature:

~~~java
public record InventoryItem(
        String sku,
        int availableQuantity) {
}
~~~

~~~java
@Component
public class InventoryClient {

    private final WebClient webClient;

    public InventoryClient(WebClient webClient) {
        this.webClient = webClient;
    }

    @RegisterReflectionForBinding(InventoryItem.class)
    public Mono<InventoryItem> getItem(String sku) {
        return webClient.get()
                .uri("/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryItem.class);
    }
}
~~~

`InventoryItem.class` is passed to the `WebClient` API inside the method. The annotation signals that the DTO needs binding/serialization hints. If the DTO has nested types needing handling, verify hints for those types or declare them additionally as required.

### Direct Jackson Example

~~~java
@Component
public class ImportService {

    private final ObjectMapper objectMapper;

    public ImportService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @RegisterReflectionForBinding(ImportRecord.class)
    public ImportRecord read(String json) throws JsonProcessingException {
        return objectMapper.readValue(json, ImportRecord.class);
    }
}
~~~

This is an example of reflection-based deserialization. If the serializer uses constructors, properties, or record metadata to instantiate the object, binding hints are the right kind of support to consider. Jackson configurations such as Java Time modules, naming strategies, custom serializers/deserializers, or polymorphic typing must still be configured separately.

## 7. Example with Spring MVC and Data Binding

A controller can accept a DTO directly:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @PostMapping
    public void create(@RequestBody OrderRequest request) {
        // ...
    }
}
~~~

Spring AOT and framework integrations can infer many types from controller mappings, handler methods, and analyzed configurations. Therefore, **do not automatically slap the annotation onto all request/response DTOs** when the framework already registers hints for them.

The annotation is more useful for indirectly used types, such as:

- A DTO passed to `ObjectMapper` inside a service.
- A type used in a `WebClient`/`RestClient` call inside a method body.
- A type used in a binding/serialization library that Spring AOT cannot see through bean/controller metadata.
- A test type used in Spring TestContext that is not in a signature automatically recognized by AOT.

If hints are registered yet the controller still fails, diagnose the actual cause: missing constructor/property reflection, missing resource, misconfigured Jackson, or an independent bug in request binding logic.

## 8. What Does the Annotation Not Do?

`@RegisterReflectionForBinding` only registers **reflection hints for binding/serialization** of the specified types. It does not:

1. Create beans or register DTOs as Spring components.
2. Add resources to the classpath or native executable.
3. Automatically configure Jackson modules, naming strategies, custom serializers/deserializers, or polymorphic type handling.
4. Register arbitrary methods for general reflective invocation.
5. Create JDK proxies or CGLIB proxies.
6. Create or register a `Converter` in Spring's `ConversionService`.
7. Fix parsing/validation logic or guarantee valid JSON.

For example, if the application needs to read `schemas/order.json` from the classpath, an appropriate **resource hint** is needed. A binding annotation on `OrderDto` does not add JSON schema files into the executable.

If a library calls an arbitrary method via reflection unrelated to property binding, consider general reflection hints via `RuntimeHintsRegistrar` or the `@RegisterReflection` annotation in supported Spring Framework versions. Choose member categories matching the actual operation.

If you want to convert a string into a custom data type, configure a converter:

~~~java
public class CurrencyCodeConverter implements Converter<String, CurrencyCode> {
    @Override
    public CurrencyCode convert(String source) {
        return CurrencyCode.of(source);
    }
}
~~~

`@RegisterReflectionForBinding` does not automatically register this converter into `ConversionService`. Only evaluate additional hints if the converter or a library it uses requires reflection for binding/serialization.

## 9. Comparison with Other Hint Mechanisms

| Mechanism | When to Use | Example |
|---|---|---|
| `@RegisterReflectionForBinding` | DTO needs reflection for binding or reflection-based serialization | Jackson deserializing `OrderDto` |
| `@RegisterReflection` (Spring Framework 6.2+) | Need to register general reflection member categories | Calling public methods or fields via reflection |
| `RuntimeHintsRegistrar` | Need programmatic, conditional, or library-level hint registration | Registering reflection/resources/proxies by logic |
| Resource hints | Need to keep files on the classpath | JSON schemas, templates, certificates, dictionaries |
| Proxy hints | Native Image needs to create proxies | JDK dynamic proxy for interfaces |
| JNI hints | Native code calls via JNI | Native library integration |

Resource hint example:

~~~java
public class AppRuntimeHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("schemas/*.json");
    }
}
~~~

Register the registrar using the Spring AOT mechanism appropriate for your project, such as `@ImportRuntimeHints(AppRuntimeHints.class)` on a configuration class. This is a separate mechanism and is unnecessary if you only need DTO binding registration and have no dynamic resources to keep.

## 10. Spring Framework Versions to Note

`@RegisterReflectionForBinding` has existed since **Spring Framework 6.0**. Spring Boot 3.x applications typically use Spring Framework 6.x, though you should check your project's actual resolved dependency version.

In Spring Framework 6.x:

- The annotation is used on types or methods.
- Specify types to register via `value` or `classes`.
- 6.x Javadoc requires specifying at least one target class.
- `value` is an alias for `classes`.

Therefore, in a Spring 6.x project, do not write the annotation with no arguments on a DTO assuming the DTO itself will automatically be registered. The clear compatible form is:

~~~java
@RegisterReflectionForBinding(CustomerDto.class)
@Configuration(proxyBeanMethods = false)
class CustomerBindingConfiguration {
}
~~~

Newer Spring Framework versions may extend attributes or target-type inference. Only use newer APIs like `classNames` if the Spring Framework version actually resolved by your application supports it. Check Javadoc for your exact version rather than copying configuration from a newer branch into a Spring 6.x project.

## 11. Verifying Whether the Annotation Took Effect

### Step 1: Confirm Dependency/Version

Check the actual Spring Framework dependency:

~~~bash
# Maven
./mvnw dependency:tree -Dincludes=org.springframework:spring-core

# Gradle
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

Ensure the project resolves a `spring-core` containing the annotation and compatible with the Spring Boot version in use. If the IDE cannot find the import, check dependency management before changing packages or creating a custom annotation.

### Step 2: Place the Annotation Where Spring AOT Can Discover It

Ensure the configuration class is imported/component-scanned or the bean/method is contributed to the `ApplicationContext`. An annotation on a class not processed by Spring will not contribute hints to the AOT output.

### Step 3: Run AOT/Native Build

With Maven (assuming native profile/plugin is configured):

~~~bash
./mvnw -Pnative package
~~~

With Gradle:

~~~bash
./gradlew processAot
./gradlew nativeCompile
~~~

Exact profile/goal/task names depend on project configuration. Read logs to confirm Spring AOT and Native Image actually executed.

### Step 4: Test the Binding Operation in Native

Do not just verify the build succeeded. Invoke the exact processing path needing the DTO:

- Deserialize JSON into the DTO.
- Serialize the DTO into JSON if the application returns objects.
- Test constructors, properties, nested DTOs, or record components.
- Test subtypes if the serializer uses polymorphism.
- Test separate resources if the serializer needs schemas/templates.

Native tests can catch issues early, though you should still run smoke/integration tests against the final application executable.

### Step 5: Diagnose Errors by Access Type

| Symptom | What to Check |
|---|---|
| Cannot instantiate DTO / constructor access blocked | Constructor hints and registered target types |
| Cannot read/write property | Field/property hints, getters/setters, and serializer configuration |
| Nested DTO fails | Whether types used in properties/record components were processed |
| Polymorphic subtype cannot be created | Subtype hints and discriminator/allow-list configuration |
| Schema/template file not found | Resource hints; the binding annotation does not register files |
| Converter not selected | `ConversionService` configuration, converter bean, and source/target types |
| Method reflection blocked unrelated to binding | General reflection hints / member categories |

Native Image error messages usually indicate the missing type or member. Use that information to narrow hints; do not register broad reflection across an entire package without justification.

## 12. Complete Practice Walkthrough

Suppose a service receives JSON from a partner system and converts it to `PartnerOrder`:

~~~java
public record PartnerAddress(String city, String country) {
}

public record PartnerLine(String sku, int quantity) {
}

public record PartnerOrder(
        String orderId,
        PartnerAddress address,
        List<PartnerLine> lines) {
}
~~~

Service:

~~~java
@Service
public class PartnerOrderService {

    private final ObjectMapper objectMapper;

    public PartnerOrderService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @RegisterReflectionForBinding(PartnerOrder.class)
    public PartnerOrder parse(String payload) throws JsonProcessingException {
        return objectMapper.readValue(payload, PartnerOrder.class);
    }
}
~~~

**Step 1:** Run JVM tests with a payload containing full `address` and `lines`, confirming data deserializes properly.

**Step 2:** Run the AOT/native build using configured Maven or Gradle. Verify the annotation on the Spring bean is processed.

**Step 3:** Run the native executable and execute the same parse operation. If `PartnerAddress` or `PartnerLine` is not recognized due to how the serializer handles generic types, register those types explicitly as well:

~~~java
@RegisterReflectionForBinding({
        PartnerOrder.class,
        PartnerAddress.class,
        PartnerLine.class
})
~~~

**Step 4:** If the payload has subtypes or custom serializers, inspect reflection metadata and Jackson configuration separately. The binding annotation does not solve polymorphism logic by itself.

**Step 5:** Try serializing `PartnerOrder` back to JSON and compare its structure against the partner system's contract. Hints only let Native Image permit access; they do not guarantee business-correct data conversion.

## 13. Common Design Mistakes

### Registering DTOs Not Processed in Context

A class carrying the annotation that Spring never pulls into AOT processing may produce no hints. Place the annotation on an imported or component-scanned configuration/bean.

### Over-Registering Too Many Types

Dumping an entire model package into one giant list can bloat the reflection surface and make metadata hard to maintain. Start from the types actually bound/serialized, then add nested types when evidenced.

### Confusing Resources with Reflection

A JSON file or template is not a DTO. Use resource hints for files and binding hints for Java types.

### Confusing Converters with Reflection

`Converter<S,T>` is conversion logic. The annotation does not register converters and does not fix converter selection errors. Only add reflection hints if the conversion implementation uses reflection-based binding.

### Assuming Hints Guarantee Full Serializer Compatibility

Jackson modules, custom serializers, polymorphic type handling, naming policies, and date/time formats still have their own rules. Only testing on the native executable verifies final behavior.

## 14. Self-Check Exercises

**Question 1.** What is `@RegisterReflectionForBinding` used to register?

**Hint:** reflection hints for data binding or reflection-based serialization of the specified types.

**Question 2.** Which components of a DTO can the annotation register?

**Hint:** constructors, fields, properties, record components, and types transitively used on properties/record components.

**Question 3.** How do `value` and `classes` differ?

**Hint:** they are aliases; choose one to specify the list of target classes.

**Question 4.** Why might a DTO used inside a `WebClient` method body need the annotation?

**Hint:** AOT may not infer types passed to a library API from code inside a method body; the annotation explicitly tells AOT which DTO needs binding hints.

**Question 5.** Does the annotation automatically include JSON schema files in the native executable?

**Hint:** no. Resource hints are required if files are read from the classpath and not automatically recognized by Native Image.

**Question 6.** Does the annotation automatically register a custom `Converter<String, CurrencyCode>`?

**Hint:** no. Converters must be configured in Spring; binding hints only address reflection for data types when needed.

**Question 7.** Can Spring Framework 6.x use the annotation without specifying a target class?

**Hint:** 6.x Javadoc requires specifying at least one target via `value` or `classes`. Check the API of your specific version before using Spring 7 syntax.

## 15. Project Adoption Checklist

- [ ] Identified exactly which DTOs/records undergo binding or reflection-based serialization.
- [ ] Checked Spring Boot/Spring Framework version and annotation package.
- [ ] Placed the annotation on a configuration class or Spring bean/method processed by AOT.
- [ ] For Spring Framework 6.x, specified target classes via `value` or `classes`.
- [ ] Identified nested types, collection elements, and subtypes actually used by the serializer.
- [ ] Avoided bulk-registering DTOs when the framework already infers hints.
- [ ] Used resource hints for schema/template files and general reflection hints for non-binding method access.
- [ ] Registered converters separately; did not treat the annotation as a `ConversionService` configuration mechanism.
- [ ] Ran JVM tests and AOT/native build.
- [ ] Ran native tests or the native executable with realistic payloads, including nested DTOs/records.
- [ ] Read diagnostics and added hints for exact missing types/members.

## 16. References

- [Spring Framework 6.2 Javadoc — RegisterReflectionForBinding](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/aot/hint/annotation/RegisterReflectionForBinding.html): targets, `value`/`classes`, constructor/field/property/record-component hints, and transitively used types.
- [Spring Framework Reference — Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html): how Spring AOT detects reflective usage, `@Reflective`, Runtime Hints, and reflection registration annotations.
- [Spring Framework 6.2 Javadoc — RegisterReflection](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/aot/hint/annotation/RegisterReflection.html): general reflection hints and member categories.

**Key takeaway:** `@RegisterReflectionForBinding` helps Spring AOT register the right group of reflection hints for DTOs or data types requiring binding/serialization. Place the annotation on a configuration or Spring bean processed by AOT, explicitly specify target classes on Spring 6.x, and test payloads on the native executable. Use resource hints, general reflection hints, and converter configuration for other needs; the binding annotation does not replace those mechanisms.
