# Registering, Replacing, or Removing Converters in Spring ConversionService

Spring Framework provides **`ConversionService`** to convert a value from a source type to a target type—for example, `String` to `Integer`, `String` to an enum, or a text code to an application value object. When you need to extend conversion logic, you register a **`Converter<S, T>`**, `ConverterFactory<S, R>`, or `GenericConverter` into the registry used by `ConversionService`.

The important point is distinguishing two roles:

- **`ConversionService`** is the consumer API for converters: asking whether conversion is supported and performing conversions.
- **`ConverterRegistry`** is the configuration SPI: registering converters and removing converters by source/target type pair.
- **`ConfigurableConversionService`** combines both roles, so it can both convert and modify the registry.
- In Spring MVC, `WebMvcConfigurer.addFormatters(FormatterRegistry)` is the standard extension point to register converters/formatters for the application's binders.

Not every object typed as `ConversionService` exposes an API to add/remove converters. Nor should you arbitrarily mutate a shared framework service, because other controllers and binders may depend on the converters already registered.

## 1. What Does ConversionService Do?

A `ConversionService` provides two groups of methods:

```java
boolean canConvert(Class<?> sourceType, Class<?> targetType);

<T> T convert(Object source, Class<T> targetType);

boolean canConvert(
        TypeDescriptor sourceType, TypeDescriptor targetType);

Object convert(
        Object source,
        TypeDescriptor sourceType,
        TypeDescriptor targetType);
```

The two overloads accepting `TypeDescriptor` allow Spring to inspect additional type metadata such as generic element types and field annotations. For example, converting `List<String>` to `List<Integer>` requires knowing the collection's element type, not merely that both outer values are `List`.

Usage example:

```java
ConversionService service = ...;

boolean supported =
        service.canConvert(String.class, Integer.class);

Integer quantity = service.convert("42", Integer.class);
```

If no matching conversion path exists, `convert(...)` may throw `ConversionFailedException` or a related conversion exception. `canConvert(...)` helps check capability beforehand, yet does not guarantee a concrete value will always parse: for instance, `String` in general can convert to `Integer`, whereas `"abc"` is not a valid integer.

When `source == null`, `ConversionService` typically returns `null` per the general API contract without invoking a custom converter for a null source value. If you need to represent an "absent" value as a special object, design that explicitly in the caller or in an appropriate converter/formatter; do not assume a converter will receive `null`.

## 2. ConversionService and ConverterRegistry Are Two Different Roles

Relationship diagram:

```text
             ConverterRegistry
         (register / remove converters)
                    ▲
                    │
       ConfigurableConversionService
                    │
          ┌─────────┴──────────┐
          │                    │
 ConversionService         ConverterRegistry
 (canConvert/convert)   (add/remove converter)
```

Key interfaces:

| API | Primary responsibility |
| --- | --- |
| `ConversionService` | `canConvert(...)` and `convert(...)` |
| `ConverterRegistry` | `addConverter(...)`, `addConverterFactory(...)`, and `removeConvertible(...)` |
| `ConfigurableConversionService` | Combines `ConversionService` and `ConverterRegistry` |
| `Converter<S, T>` | A strongly typed converter from `S` to `T` |
| `ConverterFactory<S, R>` | Creates converters from one source type to a family of target types sharing a root type `R` |
| `GenericConverter` | Flexible conversion based on a set of `ConvertiblePair` and `TypeDescriptor` |
| `ConditionalConverter` | Allows a converter to check additional type/descriptor conditions before applying |

`ConversionService` **does not declare** converter registration/removal operations. If a variable only has this interface type:

```java
ConversionService service = ...;
// service.addConverter(...); // Does not compile.
```

configuration methods cannot be called through that variable. You need a reference to the appropriate registry type:

```java
ConfigurableConversionService configurable = ...;
configurable.addConverter(myConverter);
```

Or use a `ConverterRegistry` variable if the code only needs registration operations and does not need to convert directly.

## 3. Registering Converters: Common Approaches

`ConverterRegistry` provides commonly used overloads:

```java
registry.addConverter(new StringToCodeConverter());

registry.addConverter(
        String.class,
        Code.class,
        source -> Code.of(source.trim()));

registry.addConverter(new SomeGenericConverter());

registry.addConverterFactory(new StringToEnumConverterFactory());
```

### 3.1. Converter<S, T>

Use when the source and target type pair is clear:

```java
public final class StringToCodeConverter
        implements Converter<String, Code> {

    @Override
    public Code convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("Code must not be blank");
        }
        return Code.of(source.trim().toUpperCase(Locale.ROOT));
    }
}
```

This is an example converter. With `Converter<S,T>`, Spring infers the type pair from the generic type arguments; the converter must declare concrete enough generics so the registry can resolve `S` and `T`. A raw `Converter` class or unresolvable generic types may be rejected upon registration.

### 3.2. Registering Explicit Source/Target Pairs

You can register a converter by specifying both classes:

```java
registry.addConverter(
        String.class,
        CustomerId.class,
        source -> CustomerId.from(source.trim()));
```

This approach is useful when you want to reuse a lambda/conversion logic or when the converter's generic types cannot be conveniently inferred. Ensure the conversion function accepts the declared source type and returns the declared target type.

### 3.3. ConverterFactory

Use when targets belong to a family of types sharing a common root. For example, a converter factory creating converters from `String` to each enum type:

```java
public final class StringToEnumFactory
        implements ConverterFactory<String, Enum> {

    @Override
    public <T extends Enum> Converter<String, T> getConverter(
            Class<T> targetType) {
        return source -> Enum.valueOf(
                targetType, source.trim().toUpperCase(Locale.ROOT));
    }
}
```

This is a condensed conceptual example; in production code, handle empty inputs, invalid enum names, and generic type safety. Spring already includes default converters for many common types, so do not register extra ones just to duplicate built-in capabilities.

### 3.4. GenericConverter

Use when you need to support multiple type pairs or read source/target `TypeDescriptor`s, such as annotations, generic collection elements, or field metadata. A `GenericConverter` declares a set of `ConvertiblePair` in `getConvertibleTypes()` and implements the logic in `convert(...)`.

If the logic is simply `String` to a value object, `Converter<String, Target>` is usually easier to understand and test. Only use `GenericConverter` when you genuinely need metadata flexibility or multiple type pairs.

## 4. Replacing an Existing Converter

`ConverterRegistry` does not have a dedicated method named `replaceConverter(...)`. Replacing a converter is typically done by **removing the old source/target pair and then registering the new converter**:

```java
registry.removeConvertible(String.class, CustomerId.class);
registry.addConverter(new StringToCustomerIdConverter());
```

`removeConvertible(sourceType, targetType)` removes the converters registered for the **specified source/target type pair** from that registry. After removing, register the new converter for the same pair.

This is not "finding a converter object by name and deleting only that object." The API removes by type pair, so check the impact on other conversions using that exact pair, including converters registered by default configuration if that pair is in the registry.

**Do not routinely remove and re-add on a global service shared by concurrent requests** while the application is running. The registry may be shared; runtime mutations must be synchronized and intentional. It is safer to configure the complete converter set at application startup, or create a dedicated service for a specific business scope.

### Replacement Can Remove Default Converters

A `DefaultFormattingConversionService` includes many built-in converters and formatters. Calling:

```java
registry.removeConvertible(String.class, Integer.class);
```

on that registry can remove the default `String → Integer` conversion path used by many form fields. Only remove pairs that you own or are responsible for managing. When you need a custom rule for one field, consider a field-level formatter/annotation or a narrowly scoped binder instead of altering application-wide rules.

### Does Adding Another Converter for the Same Pair Always Replace?

Do not rely ambiguously on registration order to replace system converters. When multiple converters exist for overlapping type pairs, selection can depend on how the registry manages specific converters and type-matching conditions. If controlled replacement is needed, the readable approach is to create a cleanly configured separate registry, or remove the exact pair and add the desired converter before the service starts being used.

## 5. Removing a Converter

To remove the converter for a pair:

```java
configurable.removeConvertible(String.class, CustomerId.class);
```

After removal, verify:

```java
boolean canConvert =
        configurable.canConvert(String.class, CustomerId.class);
```

However, `canConvert` may still return `true` if the registry still has another converter, a general-purpose converter, or a default conversion path that can handle that pair. Therefore, **do not rely solely on this boolean to prove which exact converter instance was removed**. Testing with a representative input confirms actual behavior; for conditional converters, test both matching and non-matching inputs.

`removeConvertible` accepts only a type pair, not a bean name, qualifier, id, or converter object. Nor does it automatically remove converters from other registries. If the same converter class is registered in multiple services, each registry has its own lifecycle/configuration.

## 6. Common Implementations

| Implementation | Role and notable details |
| --- | --- |
| `GenericConversionService` | Core implementation of `ConfigurableConversionService`; manages the registry, converter lookup, and caches matching results |
| `DefaultConversionService` | Extends configuration with common converters for standard Java types |
| `FormattingConversionService` | Combines ConversionService with `FormatterRegistry` to support both converters and formatters |
| `DefaultFormattingConversionService` | FormattingConversionService pre-configured with commonly used default converters/formatters |
| `ConversionServiceFactoryBean` | FactoryBean that creates/exposes a ConversionService from configured converters |
| `FormattingConversionServiceFactoryBean` | FactoryBean that configures a FormattingConversionService with converters/formatters/registrars |

`DefaultConversionService` and `DefaultFormattingConversionService` serve well as the foundation in many applications. A service with default configuration is usually preferable to creating an empty `GenericConversionService`, because in an empty service common conversions such as numbers, enums, or collections will be unavailable until manually registered.

For static default-setup helpers (such as `DefaultConversionService.addDefaultConverters(registry)`), check the API of the exact Spring version in use. These helpers add a set of default converters to a registry you supply; they should not be thought of as automatically initializing or managing a Spring bean for the entire application.

## 7. Runnable Java 17+ Example: Registering, Replacing, and Removing

This example uses Spring Framework 6.2.x without Spring Boot or an HTTP server. We create a converter from `String` to value object `TicketCode`, test conversion, remove the registered converter, and then register a new converter for the same pair.

### 7.1. Project Structure

```text
conversion-registry-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/ConversionRegistryDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'conversion-registry-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'example.ConversionRegistryDemo'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Use JDK 17+ and a compatible Gradle version, with Maven Central connectivity to download dependencies on the first run. `spring-context` pulls in the modules needed for `core.convert` and `format`.

### 7.2. Complete Source Code

**`src/main/java/example/ConversionRegistryDemo.java`**

```java
package example;

import org.springframework.core.convert.converter.Converter;
import org.springframework.core.convert.support.ConfigurableConversionService;
import org.springframework.format.support.DefaultFormattingConversionService;

import java.util.Locale;

public class ConversionRegistryDemo {

    public static final class TicketCode {
        private final String value;

        private TicketCode(String value) {
            this.value = value;
        }

        public static TicketCode of(String value) {
            return new TicketCode(value);
        }

        public String value() {
            return value;
        }

        @Override
        public String toString() {
            return "TicketCode[value=" + value + "]";
        }
    }

    public static final class PlainTicketCodeConverter
            implements Converter<String, TicketCode> {
        @Override
        public TicketCode convert(String source) {
            return TicketCode.of(
                    source.trim().toUpperCase(Locale.ROOT));
        }
    }

    public static final class PrefixedTicketCodeConverter
            implements Converter<String, TicketCode> {
        @Override
        public TicketCode convert(String source) {
            return TicketCode.of(
                    "NEW-" + source.trim().toUpperCase(Locale.ROOT));
        }
    }

    public static void main(String[] args) {
        ConfigurableConversionService service =
                new DefaultFormattingConversionService();

        service.addConverter(new PlainTicketCodeConverter());

        TicketCode first =
                service.convert(" ab-12 ", TicketCode.class);
        System.out.println("registered=" + first);

        service.removeConvertible(String.class, TicketCode.class);
        System.out.println("afterRemove="
                + service.canConvert(String.class, TicketCode.class));

        service.addConverter(new PrefixedTicketCodeConverter());
        TicketCode replaced =
                service.convert(" ab-12 ", TicketCode.class);
        System.out.println("afterRegister=" + replaced);

        service.removeConvertible(String.class, TicketCode.class);
        System.out.println("removedAgain="
                + service.canConvert(String.class, TicketCode.class));
    }
}
```

Design note for `TicketCode`: the constructor taking `String` is private and there is no static `valueOf(String)`; consequently, the example does not accidentally create an automatic String → TicketCode conversion path via the object-to-object mechanism. The registry requires the registered custom converter.

### 7.3. Running the Program

From the project directory:

```bash
gradle -q run
```

If the project has a Gradle wrapper, use `./gradlew -q run` on macOS/Linux or `gradlew.bat -q run` on Windows.

**Expected stdout:**

```text
registered=TicketCode[value=AB-12]
afterRemove=false
afterRegister=TicketCode[value=NEW-AB-12]
removedAgain=false
```

Explanation:

1. `addConverter(new PlainTicketCodeConverter())` registers the `String → TicketCode` converter.
2. `convert(" ab-12 ", TicketCode.class)` runs the first converter, trims, uppercases, and builds `TicketCode[value=AB-12]`.
3. `removeConvertible(String.class, TicketCode.class)` removes the conversion path for this pair. Because `TicketCode` has no constructor/static factory taking String, there is no default fallback conversion; `canConvert` returns `false`.
4. `addConverter(new PrefixedTicketCodeConverter())` re-registers that pair with the new rule, producing the `NEW-` prefix.
5. Removing it again leaves the service without a converter for the tested pair.

The example creates a fresh `DefaultFormattingConversionService` inside `main`; it does not modify any shared static system service. This is a simple lifecycle demonstrating configuration before use.

## 8. Registering Converters in a Spring MVC Application

In Spring MVC, the common extension point is `WebMvcConfigurer.addFormatters(FormatterRegistry registry)`:

```java
@Configuration
public class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToCustomerIdConverter());
    }
}
```

`FormatterRegistry` extends `ConverterRegistry`, so it can register converters while also supporting `Formatter`, parsers/printers, and annotation formatter factories. This is the way to integrate converters into the formatting/conversion system managed by MVC; there is no need to instantiate a separate `ConversionService` and replace the framework's own just to add a converter.

An example converter:

```java
public final class StringToCustomerIdConverter
        implements Converter<String, CustomerId> {

    @Override
    public CustomerId convert(String source) {
        return CustomerId.from(source.trim());
    }
}
```

This is an **integration illustration snippet**, requiring the `CustomerId` class, package/imports, configuration scan, and appropriate Spring MVC dependencies. Once registered, Spring can use the converter when binding properties or controller arguments with target type `CustomerId`, provided the source/target metadata matches.

### When Many Related Converters/Formatters Are Needed

You can use `FormatterRegistrar` to group configuration:

```java
public final class CustomerFormattingRegistrar
        implements FormatterRegistrar {

    @Override
    public void registerFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToCustomerIdConverter());
        registry.addFormatterForFieldType(
                CustomerCode.class, new CustomerCodeFormatter());
    }
}
```

With a registrar, a domain's set of rules can be attached to the registry at a single configuration point. This snippet assumes `CustomerCodeFormatter` implements `Formatter<CustomerCode>` and the domain types are declared.

**Replacing or removing in MVC:** `addFormatters` is called during application configuration; it is not a place to mutate the shared registry per request. If you want to omit a converter, it is best to build the final registry directly during configuration rather than registering a converter and removing it during request handling. If you truly must modify the registry, understand the service scope and affected type pairs clearly.

## 9. How Does DataBinder Use ConversionService?

`DataBinder` can use a `ConversionService` to convert data before writing properties. You can configure an individual binder:

```java
DataBinder binder = new DataBinder(target, "form");
binder.setConversionService(conversionService);
binder.bind(propertyValues);
```

This snippet is illustrative, requiring `target`, `propertyValues`, and appropriate imports. `setConversionService(...)` sets the ConversionService for the binder; it does not add or remove converters in the registry. To change converters, configure the registry backing the service.

An MVC example:

```java
@InitBinder("customerForm")
void initCustomerBinder(WebDataBinder binder) {
    binder.setConversionService(applicationConversionService);
}
```

This is a **per-binder configuration option**, not a pattern that is always needed. If MVC already has a shared formatting conversion service with converters registered via `WebMvcConfigurer`, you normally do not need to manually swap the conversion service for each model attribute. Configuring a separate binder service can accidentally drop default formatters/converters if the passed service lacks those configurations.

**`ConversionService` and `PropertyEditor` can coexist.** Spring has a modern conversion system while still supporting JavaBeans `PropertyEditor` for certain binding needs. When both are configured, understand how the binder prioritizes the appropriate mechanism for a property/value instead of assuming a custom converter is always invoked.

## 10. How Do Converter, Formatter, and PropertyEditor Differ?

| Component | Purpose | Example |
| --- | --- | --- |
| `Converter<S,T>` | General-purpose, strongly typed type-conversion logic | `String → CustomerId` |
| `ConverterFactory<S,R>` | Creates converters for a family of target types | `String → Enum subclass` |
| `GenericConverter` | Supports multiple type pairs, reads TypeDescriptor | `Collection<?> → Collection<?>` |
| `Formatter<T>` | Parses and prints values for client environments, with Locale | `String ↔ LocalDate` |
| `PropertyEditor` | Legacy JavaBeans API, typically bound to a property/binder | `StringTrimmerEditor` |

Use `Converter` when you only need type conversion. Use `Formatter` when you need **display parsing/printing**, especially for dates, numbers, and locales. Use `PropertyEditor` when integrating legacy code or needing a property-level editor; do not build new editors just to replace modern converters when a converter/formatter SPI fits better.

For dates/currencies, annotations such as `@DateTimeFormat` or `@NumberFormat` can select rules per field without registering an overly broad global converter. For many related formatters, `FormatterRegistrar` helps group configuration.

## 11. Scope, Thread Safety, and Lifecycle Management

Spring designs `ConversionService` to typically be configured at application startup and shared across threads. Consequently, converters/formatters registered in a shared service must also be carefully designed:

- Make converters stateless, or ensure any mutable state is safely managed across threads.
- Avoid calling `addConverter`/`removeConvertible` per request; mutating a shared registry can affect other requests.
- If one controller needs special rules, consider a separate binder/conversion service or a field-specific converter rather than altering application-wide rules.
- Do not mutate the instance returned by a global service bean after the application is running without synchronization and change-control plans.
- Clearly track which converters are Spring defaults and which are owned by business modules; this matters when removing by pair.

Also ensure converters handle empty and malformed inputs according to contract. A converter throwing `IllegalArgumentException` on invalid input can produce a conversion error during binding; applications should display field-level errors rather than leaking internal exceptions directly to clients.

## 12. Common Errors When Registering, Replacing, or Removing Converters

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Calling `addConverter` fails to compile | Variable is typed only as `ConversionService` | Use `ConverterRegistry` or `ConfigurableConversionService` |
| `canConvert` returns false after registration | Wrong source/target type or unresolvable generic converter | Check registered generic types/type pair |
| `canConvert` is true yet `convert` fails | Actual input is invalid and converter throws exception | Test representative data and validate input |
| Default conversions fail after removing a converter | `removeConvertible` removed a pair used by a default converter | Only remove application-owned pairs or use a separate service |
| Converter does not run in MVC | Not registered in MVC registry or binder uses a different service | Use `WebMvcConfigurer.addFormatters`, check scope |
| Added a second converter yet result is unexpected | Multiple converters/conversion paths can match | Configure registry explicitly, test pairs and actual metadata |
| Using `Converter` for locale-aware date parsing | Converter does not receive Locale like Formatter | Use `Formatter<T>` or `@DateTimeFormat` |
| Mutating registry per request causes flaky errors | Shared service, mutable registry modified during use | Register at startup, avoid runtime mutation |
| `removeConvertible` does not make `canConvert` false | Another converter or fallback still supports the pair | Check the entire registry/conversion paths, not just one converter |
| Custom service loses String → Number, enum, collection | Replaced default service with an empty registry lacking basic converters | Use `DefaultConversionService`/`DefaultFormattingConversionService` as the base when appropriate |
| Wrong data type produces generic exception | Conversion errors not handled at binding layer | Inspect `BindingResult`, return errors per field and input contract |

### Debugging Tips

When a converter is not invoked:

1. Print/log the exact source and target classes at the binding site.
2. Call `canConvert(sourceType, targetType)` on **the exact service the binder uses**.
3. Confirm the converter was registered in the right registry and before binding begins.
4. Inspect conditional converters (if implementing `ConditionalConverter`) and `TypeDescriptor` metadata.
5. Check whether the binder has another service set via `setConversionService(...)`.
6. Run a direct unit test for the converter, a test for the service, and then an MVC integration test.

Do not simply check one bean named `conversionService` in the context and conclude every binder is using that exact instance; MVC configuration or local binders may select a different service.

## 13. Practice Exercises

Create two converters for `String → TicketCode`:

- Converter A trims and uppercases.
- Converter B adds prefix `NEW-` after normalization.

Answer:

1. Why can a variable of type `ConversionService` not call `addConverter`?
2. Does `removeConvertible` accept a converter instance or a type pair?
3. Why can removing the `String → Integer` converter on a default service affect other binders?
4. When should you use `Formatter` instead of `Converter`?
5. Why should you not mutate a shared registry during each request?
6. If `canConvert` returns true yet concrete data causes `convert` to throw an exception, is that a contradiction?

**Answer guide:** (1) `ConversionService` only declares read/convert APIs, while registration belongs to `ConverterRegistry`. (2) A `sourceType/targetType` pair. (3) The registry may hold Spring's default converter for that pair; removing it affects the shared conversion path. (4) When display parsing/printing and Locale are needed. (5) The service is typically shared across many requests/threads. (6) No: convertibility for a type pair does not guarantee every source value is valid.

## 14. Key Takeaways and Official Documentation

- **`ConversionService`** is used for `canConvert` and `convert`.
- **`ConverterRegistry`** is used for `addConverter`, `addConverterFactory`, and `removeConvertible`.
- **`ConfigurableConversionService`** supports both roles.
- To replace a converter for a pair, normally remove that pair and add the new converter; the remove API works by **source/target types**, not instance name.
- **`DefaultConversionService`** and **`DefaultFormattingConversionService`** provide the common converter/formatter baseline; do not drop them accidentally when swapping services.
- In Spring MVC, **`WebMvcConfigurer.addFormatters(FormatterRegistry)`** is the standard way to configure global converters/formatters for MVC.
- `DataBinder.setConversionService` only attaches a service to the binder; it does not add converters to the service.
- Register during application configuration, prefer stateless/thread-safe converters, and check the impact of removal on default converters.

Official sources:

- [Spring Framework — Core Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): `ConversionService`, `ConverterRegistry`, converters, and implementations.
- [Spring Framework — Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html): `Formatter`, `FormatterRegistry`, and `FormatterRegistrar`.
- [Spring Framework — MVC Type Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html): registering converters/formatters with `WebMvcConfigurer.addFormatters`.
- [Spring Framework — ConfigurableConversionService Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/core/convert/support/ConfigurableConversionService.html): service configuration API.
- [Spring Framework — ConverterRegistry Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/core/convert/converter/ConverterRegistry.html): `addConverter`, `addConverterFactory`, and `removeConvertible`.
