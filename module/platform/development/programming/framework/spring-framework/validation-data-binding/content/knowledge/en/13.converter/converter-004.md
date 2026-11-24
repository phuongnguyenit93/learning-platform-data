# Writing a Converter from String to a Business Value Type in Spring Framework

> **Topic:** Spring Framework – validation-data-binding. **Group:** Converter. Examples use Java 17 and Spring Framework 6.2.x.

## 1. Problem and Goal

Data arriving from HTTP queries, forms, headers, or configuration is typically text. Inside an application, we want to use types with business meaning instead of passing loose strings around. For instance, a client sends the code `prd-a123`, while the controller wants to receive a `ProductCode` value object.

If every controller or service trims, uppercases, parses, and validates the format itself, conversion rules get duplicated and can diverge. A Spring `Converter` lets you encapsulate the conversion between two types, register it once, and reuse it in `ConversionService`, `DataBinder`, and Spring MVC.

Goals:
- Understand `Converter<S,T>` and how to implement a strongly typed converter.
- Create a value object representing a domain concept.
- Normalize strings, reject invalid data, and preserve invariants.
- Register the converter into `ConverterRegistry`/`FormatterRegistry`.
- Use conversion in JavaBeans, `DataBinder`, and MVC parameters.
- Distinguish conversion from validation, database lookups, and Jackson JSON deserialization.

**Key boundary:** a converter turns a representation into a target type. It does not prove that the entity exists, that the caller has permission, or that the action is allowed by business rules.

## 2. Converter SPI

Spring defines the interface:

```java
package org.springframework.core.convert.converter;

public interface Converter<S, T> {
    T convert(S source);
}
```

`S` is the source type, `T` is the target type. For this article, the conversion is `String -> ProductCode`.

```java
public final class StringToProductCodeConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        // Parse and normalize source.
    }
}
```

Spring uses generic types to identify the right converter in the registry. A converter should be small, focused on one conversion, stateless, and free of dependencies on controllers or repositories.

If conversion is impossible, the implementation can throw an exception to report conversion failure. Avoid catching all errors and returning `null`: that turns “client sent an invalid value” into “no value provided” and delays error detection to another layer.

## 3. Creating the ProductCode Value Object

Example convention: a normalized product code has the form `PRD-XXXX`, where `XXXX` consists of four uppercase letters or digits. Input is trimmed and uppercased using a neutral locale.

| Input | Result |
| --- | --- |
| `"prd-a123"` | `ProductCode("PRD-A123")` |
| `" PRD-b9x2 "` | `ProductCode("PRD-B9X2")` |
| `"PRD-12"` | Rejected due to wrong length |
| `"ABC-A123"` | Rejected due to wrong prefix |
| Empty string | Rejected |

```java
package demo;

public record ProductCode(String value) {

    public ProductCode {
        if (value == null || !value.matches("PRD-[A-Z0-9]{4}")) {
            throw new IllegalArgumentException(
                    "Invalid product code: " + value);
        }
    }

    @Override
    public String toString() {
        return value;
    }
}
```

The record provides the `value()` accessor, equality, and value-based hash code. The compact constructor protects the internal invariant, even when other code invokes the constructor directly without going through the converter.

**Separation of concerns:** the converter interprets the external representation (trim, uppercase, parse); the value object guarantees every instance is valid. Normalization rules must be an explicit domain decision. If a code is case-sensitive, you must not arbitrarily uppercase it.

## 4. Writing StringToProductCodeConverter

```java
package demo;

import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class StringToProductCodeConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        if (source == null) {
            throw new IllegalArgumentException(
                    "Product code must not be null");
        }

        String normalized = source.trim().toUpperCase(Locale.ROOT);
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(
                    "Product code must not be blank");
        }

        return new ProductCode(normalized);
    }
}
```

Explanation:
1. Generics explicitly declare source and target; no manual `instanceof` check is needed.
2. `trim()` strips leading/trailing whitespace.
3. `toUpperCase(Locale.ROOT)` avoids relying on the runtime machine's default locale.
4. Empty strings are rejected.
5. Constructing `ProductCode` ensures the invariant undergoes final verification.

In normal conversion flows, `ConversionService` handles `null` values separately and the converter does not necessarily receive null. Checking null here makes the implementation safer when invoked directly. Do not use a converter to look up products in a database: a converter should convert representations, while lookup belongs to the application service/domain layer.

## 5. ConversionService and ConverterRegistry

Core components:

| API | Role |
| --- | --- |
| `Converter<S,T>` | SPI implementing a typed conversion |
| `ConversionService` | API for checking and performing conversions at runtime |
| `ConverterRegistry` | Registers converters into the system |
| `GenericConversionService` | General registry implementation |
| `DefaultConversionService` | Conversion service with many default converters |
| `FormatterRegistry` | Registry supporting both converters and formatters |

Manual registration:

```java
import org.springframework.core.convert.support.DefaultConversionService;

DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToProductCodeConverter());

ProductCode code = service.convert("prd-a123", ProductCode.class);
System.out.println(code);
```

Output:

```text
PRD-A123
```

You can check conversion capability:

```java
boolean supported =
        service.canConvert(String.class, ProductCode.class);
```

`canConvert` answers whether the registry has a conversion path between the pair of types. It does not prove a specific string is valid: a converter may exist while `convert("invalid", ProductCode.class)` still fails.

The conversion service is typically configured during application context startup and reused. Converters should be stateless so they can be used safely across many requests.

## 6. Runnable Java 17 Example with Maven

Project structure:

```text
product-code-converter/
  pom.xml
  src/main/java/demo/ProductCode.java
  src/main/java/demo/StringToProductCodeConverter.java
  src/main/java/demo/ConverterDemo.java
```

### pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>product-code-converter</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-core</artifactId>
            <version>6.2.14</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### ConverterDemo.java

Save `ProductCode` and `StringToProductCodeConverter` in the files shown in the structure above. Main file:

```java
package demo;

import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.DefaultConversionService;

public final class ConverterDemo {

    public static void main(String[] args) {
        DefaultConversionService registry =
                new DefaultConversionService();
        registry.addConverter(new StringToProductCodeConverter());

        ConversionService service = registry;

        System.out.println("canConvert="
                + service.canConvert(String.class, ProductCode.class));

        ProductCode first =
                service.convert("prd-a123", ProductCode.class);
        ProductCode second =
                service.convert(" PRD-b9x2 ", ProductCode.class);

        System.out.println("first=" + first);
        System.out.println("second=" + second);
    }
}
```

Run in the directory containing `pom.xml` with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ConverterDemo
```

Stdout:

```text
canConvert=true
first=PRD-A123
second=PRD-B9X2
```

This is a complete Java program with Maven dependencies; running `javac ConverterDemo.java` alone without Spring on the classpath will not compile. The example requires no Spring MVC, servlet container, or database.

## 7. Using a Converter in BeanWrapper

Spring uses the conversion service when binding properties. DTO:

```java
package demo;

public class ProductSearch {
    private ProductCode code;

    public ProductCode getCode() {
        return code;
    }

    public void setCode(ProductCode code) {
        this.code = code;
    }
}
```

Using `BeanWrapper`:

```java
import org.springframework.beans.BeanWrapper;
import org.springframework.beans.BeanWrapperImpl;

ProductSearch target = new ProductSearch();
BeanWrapper wrapper = new BeanWrapperImpl(target);
wrapper.setConversionService(conversionService);

wrapper.setPropertyValue("code", "prd-a123");
System.out.println(target.getCode());
```

Output:

```text
PRD-A123
```

Processing flow: the wrapper receives property path `code` and the input string; the conversion service locates `Converter<String, ProductCode>`; the converter builds the normalized object; the setter receives the target type. The snippet assumes `conversionService` was already created and registered as in section 6.

If conversion fails, `BeanWrapper` reports a property access/type mismatch error; the field must not be considered assigned successfully. Successful conversion also does not prove the product code exists or is allowed for sale.

## 8. Using a Converter Through DataBinder

`DataBinder` also uses the property access and conversion system:

```java
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

ProductSearch target = new ProductSearch();
DataBinder binder = new DataBinder(target, "productSearch");
binder.setConversionService(conversionService);

MutablePropertyValues values = new MutablePropertyValues();
values.add("code", "prd-a123");

binder.bind(values);

if (binder.getBindingResult().hasErrors()) {
    // Handle binding errors.
} else {
    System.out.println(target.getCode());
}
```

This is a manual binding example; required imports and dependent variables must exist in the same context. `bind` uses the conversion service and then assigns properties. `BindingResult` stores binding errors.

`bind` does not automatically trigger all validation annotations. With manual `DataBinder`, if you want to run Bean Validation you must configure a validator and call `validate`; in Spring MVC, `@Valid`/`@Validated` can trigger validation through the framework lifecycle.

## 9. Registering a Converter in Spring MVC

The common approach is to implement `WebMvcConfigurer` and add the converter to `FormatterRegistry`:

```java
package demo.web;

import demo.StringToProductCodeConverter;
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToProductCodeConverter());
    }
}
```

The controller can receive the value object directly:

```java
package demo.web;

import demo.ProductCode;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {

    @GetMapping("/products")
    public String find(@RequestParam ProductCode code) {
        return "Selected product: " + code;
    }
}
```

Request:

```http
GET /products?code=prd-a123
```

Response body:

```text
Selected product: PRD-A123
```

Once the converter is registered in the MVC registry, Spring performs conversion for argument/binding flows that use the conversion service, such as matching query parameters, path variables, and form properties. The controller does not need to invoke the converter manually in each method.

**Do not confuse with `@RequestBody` JSON:** JSON normally goes through `HttpMessageConverter` (such as Jackson), using a separate deserialization pipeline. A converter registered via `FormatterRegistry` does not automatically become a Jackson deserializer for every JSON property. For JSON, you may need a Jackson creator, custom deserializer, or appropriate module; test JSON endpoints separately.

## 10. Converter vs. Formatter

| Criterion | Converter | Formatter |
| --- | --- | --- |
| Interface | `Converter<S,T>` | `Formatter<T>` |
| Direction | One-way from source to target | Parses from String and prints to String |
| Purpose | General type conversion | UI-oriented data formatting, potentially locale-dependent |
| Example | `String -> ProductCode` | Dates or decimals displayed per locale |
| When suitable | Stable parse/conversion rules | Need both parsing and formatted display |

`Formatter<T>` combines `Parser<T>` and `Printer<T>`. If you only need to turn a string into a value object and have no requirement to print it back according to a locale, `Converter` is usually more direct. For locale-specific currencies or dates/times, `Formatter` may be appropriate.

Both converters and formatters can be registered through `FormatterRegistry`. Do not implement a formatter just to replace a simple converter when the corresponding print/parse functionality is unnecessary.

## 11. Conversion vs. Validation and Business Rules

| Layer | Question | Example |
| --- | --- | --- |
| Converter | Which target type does the string represent? | `"prd-a123"` → `ProductCode("PRD-A123")` |
| Value object | Does the instance satisfy internal invariants? | Valid prefix and code length |
| Bean Validation | Does the DTO satisfy declared constraints? | `@NotNull`, `@Valid`, custom constraint |
| Service/domain | Is the value permitted in the use case? | Product exists and is active |
| Repository/database | Is the stored state valid? | FK, unique, transaction |

Do not put repository lookups into a converter. A code can convert cleanly yet not exist. Checking existence requires a repository/service; checking permissions or selling policies requires the domain/application service.

Likewise, a converter does not replace Bean Validation. `"PRD-A123"` may convert successfully while other values still violate constraints on the DTO or business logic.

## 12. Handling Conversion Errors

A converter can throw an exception if the source is invalid. Through `ConversionService`, the error may be wrapped in a conversion exception type; in property binding/MVC, it may be represented as a binding/type mismatch depending on the pipeline.

Principles:
1. Do not return `null` to hide errors.
2. Error messages should state input conditions without leaking internal details.
3. Distinguish malformed input from “product not found”.
4. With MVC, standardize responses via `BindingResult` or `@ControllerAdvice` according to the API contract.
5. Do not catch generic `RuntimeException` and label every failure “invalid code”; that can mask bugs/infrastructure failures.

Illustrative unit test:

```java
assertEquals(
        new ProductCode("PRD-A123"),
        converter.convert("prd-a123"));

assertThrows(
        IllegalArgumentException.class,
        () -> converter.convert("bad"));
```

This is a JUnit snippet with an already-initialized `converter` variable. Alongside unit tests, you should also test that the converter is registered in the service and works with actual MVC requests.

## 13. Ways to Register and Organize Multiple Converters

In MVC, use `WebMvcConfigurer#addFormatters`:

```java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addConverter(new StringToProductCodeConverter());
}
```

This is the method body inside a class implementing `WebMvcConfigurer`. In standalone applications, add the converter to `DefaultConversionService` or a managed registry.

If you have many value objects, you can register multiple converters:

```java
@Configuration
class ConversionConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToProductCodeConverter());
        registry.addConverter(new StringToOrderIdConverter());
        registry.addConverter(new StringToCustomerCodeConverter());
    }
}
```

The two additional converters in the example require their own implementations. You can split configuration by domain when the list grows large; avoid putting complex parsing logic inside configuration classes.

`ConversionService` is normally reused across the application context; converters should be stateless and hold no per-request mutable state. Do not create a new registry for every request.

## 14. When Do You Need GenericConverter, ConverterFactory, or PropertyEditor?

| Component | When appropriate |
| --- | --- |
| `Converter<S,T>` | One clear source/target pair |
| `ConverterFactory<S,R>` | One source type converting to a family of related target subtypes |
| `GenericConverter` | Multiple source/target types, metadata, or complex matching conditions |
| `PropertyEditor` | Legacy mechanism tied to JavaBeans/property binding; often stateful |
| `ConversionService` | API executing registered converters |
| Custom validator | Checks constraints on objects, not meant for type conversion |

Start with `Converter` for simple cases. Only choose `GenericConverter` or `ConverterFactory` if requirements truly call for extensibility; a more complex abstraction does not make rules more accurate on its own.

## 15. Extending to Currencies, Dates/Times, and Identifiers

### Identifiers

For `ProductCode`, define:
- Should it trim?
- Is case significant?
- Which prefixes, separators, and lengths are accepted?
- Are Unicode characters allowed?
- Is the normalized value used in equality/indexing?

Every adapter creating this type must follow the same invariant.

### Currencies

Do not parse currency strings without defining locale and currency. `"1,234.50"` can mean something different from `"1.234,50"`. If locale-aware parsing/printing is needed, consider `Formatter`; use `BigDecimal` instead of `double` to preserve decimal precision. Monetary types should carry an explicit currency when business rules must distinguish them.

### Dates and Times

ISO strings can be parsed with a converter if the contract is fixed. If locale-, timezone-, or UI-format-specific parsing/printing is needed, a formatter is usually appropriate. Do not assume a date-time string without an offset always represents the same instant across all systems.

## 16. Common Pitfalls

**1. Returning the wrong target type.** Generic `Converter<String, ProductCode>` must return `ProductCode`, not a string.

**2. Inconsistent normalization.** Whitespace and letter casing can turn the same code into two different keys.

**3. Catching errors and returning null.** Causes invalid data to be interpreted as absent data.

**4. Querying the database inside a converter.** Couples type conversion to infrastructure and business context.

**5. Using the default locale.** Technical code normalization should use `Locale.ROOT` when appropriate.

**6. Treating successful conversion as successful validation.** A well-formatted code is not guaranteed to exist or be permitted.

**7. Assuming an MVC converter automatically handles JSON.** `@RequestBody` usually goes through Jackson/message converters; configure separately if needed.

**8. Creating a ConversionService per request.** Configure once and reuse.

**9. Converter holding mutable request state.** Can fail when shared across threads; keep implementations stateless.

**10. Testing only the converter directly.** You also need to verify the registry, `DataBinder`, and MVC endpoints.

## 17. Test Matrix

| Test case | Expected result |
| --- | --- |
| `"prd-a123"` | `PRD-A123` |
| `" PRD-b9x2 "` | `PRD-B9X2` |
| Empty or whitespace-only string | Conversion failure |
| `"PRD-12"` | Rejected due to wrong length |
| `"ABC-A123"` | Rejected due to wrong prefix |
| `canConvert(String, ProductCode)` after registration | true |
| `convert` on valid code | Normalized value object |
| `BeanWrapper` writing string to `ProductCode` property | Setter receives properly typed object |
| MVC `@RequestParam ProductCode` | Valid request is converted |
| MVC invalid input | Binding/conversion error per API contract |
| `@RequestBody` JSON | Test Jackson/deserializer separately |

Divide tests into three layers:
1. **Unit tests:** parsing/normalization rules and invariants.
2. **ConversionService/DataBinder tests:** verify registry and property binding use the converter.
3. **MVC integration tests:** verify query/form/path arguments, error responses, and exception handling.

## 18. Adoption Checklist

1. Identify source type and target type; prefer a domain-named value object.
2. Protect invariants in the value object's constructor/factory.
3. Decide normalization and conversion errors explicitly.
4. Implement a small, stateless `Converter<S,T>`.
5. Register into the appropriate `ConverterRegistry` or `FormatterRegistry`.
6. Verify through `ConversionService` and `DataBinder`/MVC.
7. Keep conversion separate from validation, business rules, and persistence.
8. Test valid input, malformed input, empty strings, whitespace, and null.
9. Test JSON deserialization separately if endpoints use `@RequestBody`.
10. Keep the converter lightweight, with no database queries and no authorization checks.

**Remember:** `Converter<String, ProductCode>` turns a representation into a business value type. `ConversionService` locates and runs the converter; `FormatterRegistry`/`WebMvcConfigurer` integrates it with web binding. Conversion answers “which type does this string represent?”, while validation and service/domain logic answer “is that value valid and allowed to be used?”.

## Official References

- [Spring Framework Reference – Spring Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): ConversionService, Converter SPI, and ConverterRegistry.
- [Spring Framework Reference – Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html): Converter, Formatter, locale, and FormatterRegistry.
- [Spring Framework Reference – Spring MVC Type Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html): registering converters/formatters via WebMvcConfigurer.
- [Spring Framework 6.2.14 Javadoc – Converter](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/converter/Converter.html): typed conversion interface.
- [Spring Framework 6.2.14 Javadoc – ConverterRegistry](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/core/convert/converter/ConverterRegistry.html): converter registration API.
