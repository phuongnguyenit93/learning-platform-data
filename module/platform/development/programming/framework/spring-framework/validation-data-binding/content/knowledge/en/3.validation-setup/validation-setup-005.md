# Declaring ConversionService and a Shared Converter Set in Spring Framework

In Spring Framework, **`ConversionService` is the unified entry point for converting a value from one Java type to another**. Rather than having every controller, service, or binder write its own `Integer.parseInt(...)`, enum conversion, or custom business code parsing, the application can declare `Converter` instances and register them into a `ConversionService`. Any component that actually uses that service shares the same conversion rules.

This lesson focuses on **how to declare and organize a shared converter set**, choosing the right registration point in the Spring container, Spring MVC, and Spring Boot, as well as verifying behavior. Running example throughout: an order code arrives as the string `" ord-2026-007 "` and is normalized into an `OrderCode` type with value `"ORD-2026-007"`.

## 1. What Problem Does ConversionService Solve?

In data ingestion flows, values often originate as strings: query parameters `?code=...`, path variables, form fields, or configuration properties. Business code, meanwhile, wants to work with meaningful types: `LocalDate`, `UUID`, enums, or `OrderCode`. Spring needs a conversion mechanism to bridge these two worlds.

General flow for Spring MVC:

~~~text
HTTP query/path/form (String)
          |
          v
  Spring MVC argument binding
          |
          v
  MVC ConversionService
          |
          v
 Converter<String, OrderCode>
          |
          v
   OrderCode (domain type)
          |
          v
      Controller
~~~

For direct access in Java, a service can call `conversionService.convert(rawValue, OrderCode.class)`. This gives conversion rules **a single place of definition** that can be reused across multiple input boundaries.

However, distinguish carefully:

- **Conversion** changes types or interprets values, such as `String -> OrderCode`.
- **Validation** checks whether an object satisfies rules, such as `@NotNull` or a business constraint.
- **Formatting** converts text in a `Locale`-aware way for displaying or parsing values (dates, currencies, numbers).
- **JSON deserialization** of `@RequestBody` is usually handled by Jackson/`HttpMessageConverter`. Registering a `Converter<String, OrderCode>` in MVC does not mean Jackson will automatically use it to read JSON bodies.

A converter may reject malformed strings by throwing an exception, but **not every** validation rule, authorization check, or database state check belongs inside a converter.

## 2. APIs to Distinguish

| API | Role | When typically used |
| --- | --- | --- |
| `Converter<S,T>` | Conversion rule with a fixed source/target type pair | `String -> OrderCode`, `String -> CustomerId` |
| `ConverterFactory<S,R>` | Creates converters for a target type hierarchy | Multiple subtypes of a common supertype |
| `GenericConverter` | Handles multiple type pairs, with `TypeDescriptor` metadata | Conversions needing element/annotation metadata |
| `ConditionalGenericConverter` | Applies only when specific metadata conditions hold | Conversion depending on target type traits |
| `ConversionService` | **Consumes** rules: `canConvert(...)` and `convert(...)` | Controller infrastructure, services, binders |
| `ConverterRegistry` | **Registers** rules via `addConverter(...)` | During application configuration |
| `ConfigurableConversionService` | Combines conversion and registration capabilities | When configuring and using the same instance |
| `Formatter<T>` / `FormatterRegistry` | Locale-aware parse/print; registers formatters and converters | Forms, dates, numbers, currencies |
| `FormatterRegistrar` | Groups related formatter and converter registrations | Configuring a cohesive rule set |

By design, **`ConversionService` is the usage interface**, whereas **`ConverterRegistry` is the configuration interface**. Do not look for `addConverter(...)` on a variable typed only as `ConversionService`, because that method belongs to the registry.

Notable implementations:

- `GenericConversionService`: general-purpose conversion foundation allowing converter registration; a fresh instance does not automatically contain all standard converters.
- `DefaultConversionService`: extends `GenericConversionService` and **pre-registers default converters** for many numeric, enum, collection, string, and common types.
- `FormattingConversionService`: adds support for registering/applying field formatters; suitable for forms and locale-dependent display.
- `DefaultFormattingConversionService`: configures default formatters alongside conversion capabilities.
- Spring Boot's `ApplicationConversionService`: expands the converter set useful for application configuration; should not be assumed to be the exact instance MVC is using.

A `ConversionService` is normally created during application startup and shared across threads. **Converters must not hold per-request mutable state**; if locale-sensitive formatting is needed, use `Formatter` rather than storing a request locale in a global field.

## 3. "Sharing" Has Two Levels

### 3.1. Sharing Converter Definitions

A domain rule set like `String -> OrderCode` should be **defined once** in converter classes. A centralized registration helper can then add those converters to **any appropriate registry**.

~~~text
           DomainConverters.register(registry)
                         |
             +-----------+-----------+
             |                       |
             v                       v
    domainConversionService   Spring MVC FormatterRegistry
    (used in Java code)        (query/path/form binding)
             |                       |
             +-----------+-----------+
                         |
             same OrderCode rule
~~~

The two registries in the diagram may be **two distinct instances**. "Sharing converters" means sharing the definitions and rule set, **not** that the framework automatically shares one registry across every subsystem.

### 3.2. Sharing the Same Instance When Needed

You can create a `ConversionService` bean, inject it into services within the same `ApplicationContext`, and use it via `convert(...)`. The Spring core container also supports a bean with the **exact name `conversionService`** to apply when converting bean properties. However, naming a bean this way **does not automatically guarantee** that Spring MVC, Spring Boot `@ConfigurationProperties`, and Jackson JSON all use that single instance.

In Spring Boot, prefer a dedicated name like `domainConversionService` when you only need conversion for business code. Only configure a bean named `conversionService` when you intentionally want to affect container/configuration conversion and have evaluated early initialization order and default converters that must be retained.

## 4. Complete Example: One Converter Set, Two Usage Sites

This example uses **Java 17+, Spring Boot 3.3.x / Spring Framework 6.x**, and Gradle. Plugin versions are pinned below so the example has a concrete configuration; real projects should use the project's managed version set.

Create `settings.gradle`:

~~~groovy
rootProject.name = 'conversion-shared-demo'
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    sourceCompatibility = JavaVersion.VERSION_17
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 4.1. Bootstrapping the Application

Create `src/main/java/com/example/conversion/ConversionDemoApplication.java`:

~~~java
package com.example.conversion;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConversionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConversionDemoApplication.class, args);
    }
}
~~~

### 4.2. Target Type with Its Own Invariant

Create `src/main/java/com/example/conversion/OrderCode.java`:

~~~java
package com.example.conversion;

import java.util.regex.Pattern;

public record OrderCode(String value) {
    private static final Pattern FORMAT =
            Pattern.compile("ORD-[0-9]{4}-[0-9]{3}");

    public OrderCode {
        if (value == null || !FORMAT.matcher(value).matches()) {
            throw new IllegalArgumentException(
                    "Order code must match ORD-yyyy-nnn");
        }
    }
}
~~~

`OrderCode` is a value object. The constructor checks format so anywhere this object is created must preserve the invariant. Uppercasing and trimming whitespace belong to the converter; rules about whether an order **actually exists** must be handled in a service/repository, not here.

### 4.3. Writing Pure, Stateless Converters

Create `src/main/java/com/example/conversion/StringToOrderCodeConverter.java`:

~~~java
package com.example.conversion;

import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class StringToOrderCodeConverter
        implements Converter<String, OrderCode> {

    @Override
    public OrderCode convert(String source) {
        String normalized = source.strip().toUpperCase(Locale.ROOT);
        return new OrderCode(normalized);
    }
}
~~~

Create `src/main/java/com/example/conversion/OrderCodeToStringConverter.java`:

~~~java
package com.example.conversion;

import org.springframework.core.convert.converter.Converter;

public final class OrderCodeToStringConverter
        implements Converter<OrderCode, String> {

    @Override
    public String convert(OrderCode source) {
        return source.value();
    }
}
~~~

Both conversion directions are declared separately. Using `Locale.ROOT` ensures technical code normalization does not depend on the host machine's default locale. The `OrderCode` constructor throws `IllegalArgumentException` on malformed strings; when invoked via `ConversionService`, Spring typically wraps this conversion failure in `ConversionFailedException`.

A `Converter<S,T>` normally receives a non-null source; for `null`, `ConversionService` has separate null-handling rules. Therefore, do not use a converter to enforce required fields; requiredness belongs to the corresponding binding/validation step.

### 4.4. Registering the Shared Converter Set

Create `src/main/java/com/example/conversion/DomainConverters.java`:

~~~java
package com.example.conversion;

import org.springframework.core.convert.converter.ConverterRegistry;

public final class DomainConverters {
    private DomainConverters() {}

    public static void register(ConverterRegistry registry) {
        registry.addConverter(new StringToOrderCodeConverter());
        registry.addConverter(new OrderCodeToStringConverter());
    }
}
~~~

The converter set is now managed at **a single registration point**. If adding `StringToCustomerIdConverter`, you only need to add it to `register(...)` and test the contexts that invoke this method. This is also the place to catch conflicts when multiple converters share the same type pair.

Create `src/main/java/com/example/conversion/ConversionConfiguration.java`:

~~~java
package com.example.conversion;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.DefaultConversionService;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class ConversionConfiguration implements WebMvcConfigurer {

    @Bean("domainConversionService")
    public ConversionService domainConversionService() {
        DefaultConversionService service = new DefaultConversionService();
        DomainConverters.register(service);
        return service;
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        DomainConverters.register(registry);
    }
}
~~~

Note the two registration sites:

1. `domainConversionService()` creates a `DefaultConversionService` pre-populated with basic converters, then adds the domain set. Beans wanting direct conversion inject this bean with `@Qualifier("domainConversionService")`.
2. `addFormatters(...)` adds **the exact same rule set** to the conversion/formatting registry managed by Spring MVC. Because `FormatterRegistry extends ConverterRegistry`, `register(...)` works directly. Spring MVC retains the default formatters/converters configured by the infrastructure.

Spring Boot MVC can also auto-register beans implementing `Converter`/`GenericConverter`/`Formatter`. This example intentionally uses `DomainConverters.register(...)` and **does not annotate individual converters with `@Component`**, keeping registration explicit and avoiding duplicates. In a real application, choose one consistent strategy.

### 4.5. Using `ConversionService` Directly in a Service

Create `src/main/java/com/example/conversion/OrderCodeParser.java`:

~~~java
package com.example.conversion;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.convert.ConversionService;
import org.springframework.stereotype.Service;

@Service
public class OrderCodeParser {
    private final ConversionService conversionService;

    public OrderCodeParser(
            @Qualifier("domainConversionService")
            ConversionService conversionService) {
        this.conversionService = conversionService;
    }

    public OrderCode parse(String raw) {
        return conversionService.convert(raw, OrderCode.class);
    }
}
~~~

This bean always uses the exact instance where the rule set was registered. If the project has multiple `ConversionService` beans, `@Qualifier` selects accurately. With `@Qualifier("domainConversionService")`, the program does not rely on guessing which bean is `@Primary`.

You can check beforehand using `conversionService.canConvert(String.class, OrderCode.class)`. A `true` result only proves a type conversion path exists; **it does not prove every input string is valid**. Converting a specific value can still throw an error.

### 4.6. Applying Automatically During Request Binding in Spring MVC

Create `src/main/java/com/example/conversion/OrderController.java`:

~~~java
package com.example.conversion;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

    public record CheckResponse(String status, String code) {}

    @GetMapping("/check")
    public CheckResponse check(@RequestParam("code") OrderCode code) {
        return new CheckResponse("accepted", code.value());
    }
}
~~~

The parameter `code` has type `OrderCode`, even though the HTTP query data is a string. MVC invokes the converter registered via `addFormatters(...)` **before entering** the controller body.

If the project has a Gradle Wrapper, run from the root directory:

~~~bash
./gradlew bootRun
~~~

On Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Send a valid request:

~~~bash
curl --get --data-urlencode "code= ord-2026-007 " http://localhost:8080/orders/check
~~~

Expect HTTP `200 OK`; JSON has `status = "accepted"` and `code = "ORD-2026-007"`. Do not depend on JSON property ordering.

Invalid request:

~~~bash
curl --get --data-urlencode "code=wrong-code" http://localhost:8080/orders/check
~~~

Expect HTTP `400 Bad Request` under default MVC configuration, because the invalid string cannot be converted to `OrderCode`. The controller is not invoked. The exact error body depends on exception handlers and Spring Boot configuration; the example does not define a fixed error JSON format.

To convert in the reverse direction from a Java service, `conversionService.convert(new OrderCode("ORD-2026-007"), String.class)` returns `"ORD-2026-007"` via `OrderCodeToStringConverter`.

## 5. Choosing the Right Registration Point per Subsystem

A Spring Boot application may have **multiple conversion services**. The following table distinguishes target scopes and common configuration approaches:

| Need | Registration point / method | What to remember |
| --- | --- | --- |
| Type conversion from arbitrary Java code | Dedicated-name `ConversionService` bean, e.g., `domainConversionService` | Inject the right bean; do not create a new service per call |
| Binding query/path/form in Spring MVC | `WebMvcConfigurer.addFormatters(FormatterRegistry)` | No need to replace the entire MVC configuration |
| Converting bean properties via Spring core container | Bean with special name `conversionService` | Can have broad impact; retain default converters and evaluate startup order |
| Binding `@ConfigurationProperties` in Spring Boot | `@ConfigurationPropertiesBinding` on a converter bean or property binder conversion service | Converters used for configuration may be initialized very early |
| `Locale`-dependent parse/print | `Formatter<T>` in `FormatterRegistry` | A plain `Converter` does not receive a `Locale` parameter |
| JSON `@RequestBody` | Jackson deserializer / `@JsonCreator` / appropriate `ObjectMapper` configuration | MVC's `ConversionService` does not replace Jackson automatically |
| Data violating business rules | Validation/service/domain | Successful type conversion does not guarantee business validity |

### 5.1. If You Actually Need a `conversionService` Bean for Spring Core

In a Spring application that does not need a separate name, you can declare:

~~~java
@Bean("conversionService")
public ConversionService conversionService() {
    DefaultConversionService service = new DefaultConversionService();
    DomainConverters.register(service);
    return service;
}
~~~

This is an **alternative** to the `domainConversionService` bean in the example above, not a second bean to add alongside it. The name `conversionService` has special meaning to the core container. In Spring Boot, inspect its impact on property binding; a bean used for configuration conversion may be requested very early. Avoid letting the factory depend on databases, HTTP clients, or late-initialized beans.

Also avoid creating `new GenericConversionService()` and adding only domain converters if the application still expects default conversions: that instance starts without the default converter set provided by `DefaultConversionService`.

### 5.2. If You Need `@ConfigurationPropertiesBinding` in Spring Boot

A converter used to bind configuration properties must be registered with the appropriate binder mechanism, for example as a factory method inside a `@Configuration` class:

~~~java
@Bean
@ConfigurationPropertiesBinding
public static Converter<String, OrderCode> orderCodePropertyConverter() {
    return new StringToOrderCodeConverter();
}
~~~

This snippet requires importing `org.springframework.boot.context.properties.ConfigurationPropertiesBinding` and `org.springframework.context.annotation.Bean`; it illustrates **registration specifically for property binding**, not a standalone Java file. Declaring `static @Bean` reduces the risk of instantiating the `@Configuration` class too early. If you combine this approach with automatic converter bean registration in MVC, check whether the same rule gets registered twice.

Example in `application.yaml`:

~~~yaml
orders:
  default-code: ord-2026-007
~~~

A `@ConfigurationProperties(prefix = "orders")` class containing a field of type `OrderCode defaultCode` can use the converter registered through the property binder mechanism. This is a different scenario from MVC `@RequestParam`.

### 5.3. Formatter and Converter Do Not Substitute for Each Other in Every Problem

`Converter<String, OrderCode>` fits technical identifiers with a single locale-independent normalization rule. However, if users enter dates like `31/12/2026` or numbers with regional separators, parsing/printing requires `Locale`. In those cases, use `Formatter<T>` with `parse(String, Locale)` and `print(T, Locale)` or use built-in formatters with annotations like `@DateTimeFormat` and `@NumberFormat`.

When grouping multiple formatters into a reusable bundle, `FormatterRegistrar.registerFormatters(FormatterRegistry)` is the right structure; `FormatterRegistry` also allows registering converters. Do not write an application-wide `String -> String` converter solely to trim whitespace from all inputs, as it can alter data that other APIs need preserved verbatim.

## 6. Converter Selection Mechanism and Key Limitations

When calling `convert(source, TargetType.class)`, Spring looks up a converter matching the source/target types; for complex cases, Spring uses `TypeDescriptor` to retain collection/element type and annotation metadata. Built-in converters can convert collections if an element converter exists.

For example, calling `convert(value, List.class)` alone does not pass full target element information `OrderCode`. When converting a collection with a specific element type, use the `convert(Object source, TypeDescriptor sourceType, TypeDescriptor targetType)` form, such as:

~~~java
List<String> source = List.of("ord-2026-007");
TypeDescriptor inputType = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(String.class));
TypeDescriptor outputType = TypeDescriptor.collection(
        List.class, TypeDescriptor.valueOf(OrderCode.class));

@SuppressWarnings("unchecked")
List<OrderCode> result = (List<OrderCode>)
        conversionService.convert(source, inputType, outputType);
~~~

This snippet assumes `conversionService` is already available and `java.util.List` and `org.springframework.core.convert.TypeDescriptor` are imported; it illustrates `TypeDescriptor` usage, not a standalone program. When using `DefaultConversionService` with a `String -> OrderCode` element converter, collection conversion can reuse that element converter.

**Principles for selecting and designing converters:**

1. Converters should have sufficiently specific type pairs; avoid overly broad custom converters like `Object -> String` that easily conflict with default converters.
2. Registering duplicate type pairs can cause a newer converter to replace an older one or change resolution outcomes; do not rely on unmanaged registration order.
3. `canConvert(...)` checks type-level capability, not whether a given input value is valid.
4. Converters must be fast and deterministic—never perform DB queries, network calls, or mutate business state during binding.
5. Document normalization policy clearly: whether whitespace is trimmed, case is changed, and how Unicode data is accepted. Normalizing technical codes may be right, whereas applying the same rule to passwords or free text can be wrong.
6. Converters/formatters are typically accessed concurrently; avoid mutable state, shared unsynchronized `SimpleDateFormat`, or storing locale in fields.
7. Configure once at startup; do not add/remove converters while requests are in flight. Use `@Qualifier` if multiple `ConversionService` beans exist in the context and explicit selection is needed.

## 7. Testing: Pure Converters and MVC Flows

Good tests should prove both **correct conversion rules** and **registration into the right conversion service**. For example, with the `spring-boot-starter-test` dependency above, create `src/test/java/com/example/conversion/ConversionIntegrationTest.java`:

~~~java
package com.example.conversion;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ConversionIntegrationTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    @Qualifier("domainConversionService")
    private ConversionService conversionService;

    @Test
    void domainRegistryUsesOurConverter() {
        assertTrue(conversionService.canConvert(
                String.class, OrderCode.class));
        assertEquals(
                new OrderCode("ORD-2026-007"),
                conversionService.convert(" ord-2026-007 ", OrderCode.class));
        assertEquals(
                "ORD-2026-007",
                conversionService.convert(
                        new OrderCode("ORD-2026-007"), String.class));

        assertThrows(ConversionFailedException.class,
                () -> conversionService.convert(
                        "wrong-code", OrderCode.class));
    }

    @Test
    void mvcUsesTheSameRuleForRequestParameters() throws Exception {
        mvc.perform(get("/orders/check")
                .param("code", " ord-2026-007 "))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value("ORD-2026-007"));
    }

    @Test
    void mvcRejectsUnconvertibleValue() throws Exception {
        mvc.perform(get("/orders/check")
                .param("code", "wrong-code"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

The three tests prove the domain registry supports both directions, invalid inputs are rejected, and Spring MVC actually uses the configured converter. In real environments, add cases for `null`/missing query parameters, whitespace, lowercase, boundary values, different locales (if formatters exist), and errors when multiple converters collide on the same type pair.

The tests above **do not test JSON `@RequestBody` or `@ConfigurationProperties`**, as those are two separate conversion paths requiring their own tests when used.

## 8. Common Mistakes and How to Fix Them

| Symptom | Possible cause | How to check/fix |
| --- | --- | --- |
| `ConversionService.convert(...)` reports no converter found | Not registered or wrong instance injected | Check bean/`@Qualifier` and `canConvert(...)` |
| Java service converts fine, but `@RequestParam OrderCode` fails | Added only to domain service, not MVC | Register via `WebMvcConfigurer.addFormatters(...)` |
| MVC works, but `@ConfigurationProperties` fails to bind | Boot binder uses a separate conversion mechanism | Register properly with `@ConfigurationPropertiesBinding` or configure binder |
| `@RequestBody` JSON does not use MVC converter | Jackson deserialization is a separate pipeline | Configure Jackson if JSON type conversion is actually needed |
| Common number/date types suddenly fail to convert | Replaced default service with empty registry or broad override | Use `DefaultConversionService`/appropriate formatter service, keep defaults |
| Malformed value record causes controller error | Converter throws exception during binding | Design consistent HTTP 400 responses, never leak stack traces via API |
| Blank string gets converted to null and slips past logic | Confusing conversion with requiredness validation | Check required/`@NotNull`/validation at boundaries |
| Different behavior between unit test and HTTP | Unit test constructs service manually while MVC lacks converter | Add integration tests with application context/MockMvc |
| Results vary by locale or thread | Converter has mutable state or relies carelessly on default locale | Use `Locale.ROOT` for technical codes or `Formatter` for locale-sensitive values |
| Boot configuration produces early initialization warnings | `conversionService`/property binding converter bean depends on late beans | Minimize dependencies; use `static @Bean` for `@ConfigurationPropertiesBinding` when appropriate |

## 9. Project Application Checklist

- Define **source type, target type, and normalization rules**; prefer one small converter per type pair.
- Centralize domain converter registration in one place like `DomainConverters.register(...)`, with tests catching duplicates/conflicts.
- Use `DefaultConversionService` when a standalone service still needs default conversions; avoid accidentally emptying the registry.
- Register in the right scope: Java service, MVC, property binder, or JSON. The same rule may need to be added to multiple registries.
- Keep converters stateless and thread-safe; never mix DB lookups, access checks, or transactions into conversion.
- Keep validation and error contracts separate; successful conversion is only the first step toward validity.
- Test both the converter directly and actual binding paths; cover invalid input, null, locales, request types, and HTTP outputs.

**Conclusion:** `ConversionService` provides a consistent type-conversion API; `ConverterRegistry` and `FormatterRegistry` are where rules are added; a shared converter set ensures processing paths **apply the same data interpretation**. What matters in Spring is not only writing the converter correctly, but also **registering it into the exact service that the processing pipeline uses**.

### References

- Spring Framework — Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation/convert.html
- Spring Framework — Field Formatting: https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring Framework — MVC Type Conversion: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html
- Spring Boot — MVC Conversion Service: https://docs.spring.io/spring-boot/reference/web/servlet.html
- Spring Boot — Externalized Configuration, Properties Conversion: https://docs.spring.io/spring-boot/reference/features/external-config.html
