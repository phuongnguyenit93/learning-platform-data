# Converter<S, T> and the Single-Pair Conversion Contract in Spring Framework

## 1. Role and Contract

Spring Core defines the functional interface org.springframework.core.convert.converter.Converter<S, T> with a single method:

```java
@FunctionalInterface
public interface Converter<S, T> {
    T convert(S source);
}
```

S is the source type (*source*), T is the target type (*target*). An implementation describes a directional conversion rule from S to T. For example: String → Integer, String → OrderCode, UUID → CustomerId, or LegacyStatus → OrderStatus.

If you write Converter<String, OrderCode>, the contract states that convert receives a String and returns an OrderCode when successful. It does not automatically create the reverse OrderCode → String direction. If the application needs the reverse direction, a separate rule must be registered, such as Converter<OrderCode, String>, or a more suitable abstraction such as Formatter should be used when the problem is string parsing/printing.

**A Converter is not a ConversionService.** A Converter is a specific conversion rule. ConversionService is the unified entry point to check conversion capability and request conversion without the caller having to locate an implementation.

## 2. What Does “A Pair of Types” Mean?

```text
S (source type) --[Converter<S, T>]--> T (target type)

String           --[StringToOrderCode]--> OrderCode
UUID             --[UUIDToCustomerId]----> CustomerId
LegacyStatus     --[LegacyToStatus]------> OrderStatus
```

The contract has four points:

1. The input type is defined as S.
2. The successful result has type T.
3. The conversion direction is S → T; T → S does not exist by default.
4. The implementation defines its own rules for parsing, normalization, mapping, or rejecting values.

Generics help the compiler check compatibility at compile time. A Converter<String, OrderCode> cannot be mistakenly passed where a converter accepting UUID is required if generics are preserved properly. However, generics only check Java types and cannot prove that a specific value is valid at the business level: a string "??" is still a properly typed String, yet it may not be a valid order code.

### 2.1. Converter Is One-Way Only

Converter<String, OrderCode> answers the question “how do we create an OrderCode from a String?”. The following operations are separate rules:

- Printing an OrderCode into a display string.
- Parsing dates or numbers according to a locale.
- Converting a domain code to a legacy code.
- Converting a legacy code to a domain code.
- Converting through an intermediate type.

You should not assume a bidirectional converter just because data both enters and leaves the application. Input parsing and output representation may follow different rules.

### 2.2. Converter vs. Formatter

| Criterion | Converter<S, T> | Formatter<T> |
| --- | --- | --- |
| API | A single convert method | parse and print |
| Input | Any type S | String when parsing |
| Output | T | T when parsing; String when printing |
| Locale | Not passed to convert | Accepts Locale |
| Use case | Converting a pair of types | Locale-aware input/display |
| Example | String → OrderCode | String ↔ LocalDate |

Technical codes with fixed syntax usually suit Converter. Dates, decimals, or currencies entered/displayed across multiple locales usually suit Formatter.

## 3. Implementation Principles

A good converter needs to:

- **Validate the value domain:** reject content that cannot be represented by the target type.
- **Normalize intentionally:** trim whitespace or normalize uppercase/lowercase when required by the domain.
- **Avoid losing information:** do not strip characters or alter formatting outside the contract.
- **Report errors clearly:** invalid input must produce a diagnosable error.
- **Be stateless and thread-safe:** converters are typically reused concurrently across many requests.
- **Avoid side effects:** parsing a code should not write to a database, send emails, or mutate business state.

Null and empty strings need to be distinguished. DataBinder/ConversionService/MVC have their own policies when handling absent values; you should not turn every empty input into a default object to hide invalid data. If a use case requires optional input, define that at the boundary using appropriate types and validation.

### 3.1. Return null or Throw an Exception?

The clearest policy is usually to return T when valid and throw IllegalArgumentException when the value falls outside the domain accepted by the converter. When invoked through ConversionService, errors from a converter are typically wrapped in ConversionFailedException.

Only return null if null carries a well-defined meaning that the calling layer can clearly understand. Do not catch every parse error and return null, because the caller can hardly distinguish “no data” from “invalid data”.

## 4. Example: String to OrderCode

Suppose an order code has the format:

```text
ORD-000123
```

The converter will trim leading and trailing whitespace, convert the prefix to uppercase using Locale.ROOT, check for the ORD- prefix and exactly six digits, and then create an immutable value object.

### 4.1. Project Structure and Dependencies

The example uses Java 17, Spring Framework 6.2.6, with no web server or database required:

```text
converter-demo/
├── pom.xml
└── src/main/java/demo/
    ├── OrderCode.java
    ├── StringToOrderCode.java
    └── ConverterDemo.java
```

pom.xml:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>converter-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.6</version>
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
                <configuration>
                    <mainClass>demo.ConverterDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Dependency spring-context provides the Spring modules needed for the conversion example.

### 4.2. Value Object

File src/main/java/demo/OrderCode.java:

```java
package demo;

import java.util.Objects;

public record OrderCode(String value) {
    public OrderCode {
        Objects.requireNonNull(value, "value must not be null");
        if (!value.matches("ORD-[0-9]{6}")) {
            throw new IllegalArgumentException("Invalid OrderCode");
        }
    }

    @Override
    public String toString() {
        return value;
    }
}
```

A record keeps the data concise and immutable. The compact constructor protects the invariant even if the object is created through a path other than the converter.

### 4.3. Converter Implementation

File src/main/java/demo/StringToOrderCode.java:

```java
package demo;

import java.util.Locale;
import org.springframework.core.convert.converter.Converter;

public final class StringToOrderCode
        implements Converter<String, OrderCode> {

    @Override
    public OrderCode convert(String source) {
        if (source == null) {
            throw new IllegalArgumentException("Order code is required");
        }

        String normalized = source.trim().toUpperCase(Locale.ROOT);
        if (!normalized.matches("ORD-[0-9]{6}")) {
            throw new IllegalArgumentException("Invalid order code");
        }

        return new OrderCode(normalized);
    }
}
```

Locale.ROOT is appropriate when normalizing technical codes independently of user language. The converter only receives the String provided by the caller; it does not read the HTTP request itself.

### 4.4. Registering and Using ConversionService

File src/main/java/demo/ConverterDemo.java:

```java
package demo;

import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.GenericConversionService;

public final class ConverterDemo {

    public static void main(String[] args) {
        GenericConversionService registry =
                new GenericConversionService();

        registry.addConverter(new StringToOrderCode());

        ConversionService service = registry;

        System.out.println("can String -> OrderCode: " +
                service.canConvert(String.class, OrderCode.class));

        OrderCode code = service.convert(
                " ord-000123 ", OrderCode.class);

        System.out.println("converted: " + code);
        System.out.println("can OrderCode -> String: " +
                service.canConvert(OrderCode.class, String.class));
    }
}
```

Run from the converter-demo directory:

```bash
mvn -q clean compile exec:java
```

Stdout printed by the program:

```text
can String -> OrderCode: true
converted: ORD-000123
can OrderCode -> String: false
```

Explanation:

1. addConverter registers a String → OrderCode path.
2. canConvert checks whether the registry has a conversion path for the pair of types.
3. convert locates the matching converter, normalizes the string, and creates the value object.
4. OrderCode → String returns false because no reverse-direction rule has been registered.

canConvert only confirms that a type-level conversion path exists. It **does not test every value**. A malformed string can still cause convert to fail even when canConvert returns true.

## 5. When Input Is Invalid

Calling:

```java
service.convert("ORD-12", OrderCode.class);
```

is rejected by the converter because the code does not have six digits. When going through GenericConversionService, the error is typically wrapped by ConversionFailedException.

It can be handled as:

```java
try {
    service.convert("ORD-12", OrderCode.class);
} catch (org.springframework.core.convert.ConversionFailedException ex) {
    System.out.println("conversion failed");
}
```

If running only the snippet above, the program prints:

```text
conversion failed
```

In MVC, a conversion error can be recorded into binding/type mismatch errors. The controller or exception handler chooses the HTTP status and a stable message. Do not send stack traces to clients, and do not create a default OrderCode to mask invalid data.

## 6. How Do Generics S and T Help?

The declaration:

```java
Converter<String, OrderCode> parser = new StringToOrderCode();
```

helps the compiler know that the parser accepts String and returns OrderCode. Passing an Integer to convert is a compile-time error; the caller uses OrderCode directly without casting. If the API only had Object convert(Object), the caller would have to cast and many type errors would only appear at runtime.

Java generics undergo type erasure at runtime. For structures such as List<String> → List<OrderCode>, the raw type List.class is insufficient to describe the element type. Spring provides richer metadata such as TypeDescriptor and the GenericConverter SPI for those cases.

### 6.1. When Is Converter Enough?

Use Converter<S,T> when you have a concrete pair of types, the rule does not need a locale, and no complex field/generic metadata is needed. Examples include String → OrderCode, UUID → CustomerId, or Long → InvoiceNumber.

### 6.2. More General SPIs

| SPI | Purpose | Example |
| --- | --- | --- |
| Converter<S,T> | Single source/target pair | String → OrderCode |
| ConverterFactory<S,R> | One source to a family of target types sharing a base type | String → enum subtype |
| GenericConverter | Multiple type pairs, can use TypeDescriptor | Collection/map |
| ConditionalGenericConverter | Conditional generic converter | By type/annotation |

Do not use a complex SPI if a Converter expresses the contract sufficiently. Choose the API based on the amount of information actually needed.

## 7. Distinguishing the Components

| Component | Role | Typical API |
| --- | --- | --- |
| Converter<S,T> | A single type-conversion rule | T convert(S source) |
| ConversionService | Query and perform conversions | canConvert, convert |
| ConverterRegistry | Register/manage converters | addConverter |
| GenericConversionService | Conversion and registry implementation | Implements the interfaces above |
| DefaultConversionService | Service with built-in default converters | Ready to use and extend with custom converters |

Runtime flow:

```text
Configuration:
  ConverterRegistry.addConverter(StringToOrderCode)

At runtime:
  ConversionService.convert("ORD-000123", OrderCode.class)
                  |
                  v
       find matching converter
                  |
                  v
          StringToOrderCode.convert(source)
                  |
                  v
                OrderCode
```

The caller only depends on ConversionService; it does not need to know the concrete converter class. If a variable has static type ConversionService, it does not have the addConverter method. Register converters through the registry before passing the service to callers.

### 7.1. GenericConversionService

Use when you want an empty registry and register converters yourself:

```java
GenericConversionService service = new GenericConversionService();
service.addConverter(new StringToOrderCode());
```

Suitable for standalone examples, tests, or custom registries.

### 7.2. DefaultConversionService

Use when you want common converters built in:

```java
DefaultConversionService service = new DefaultConversionService();
service.addConverter(new StringToOrderCode());
```

Default converters cannot know every domain type of an application; custom converters must still be registered.

### 7.3. Registering in Spring MVC

Use WebMvcConfigurer.addFormatters(FormatterRegistry):

```java
@Configuration
class WebConversionConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToOrderCode());
    }
}
```

This is a configuration snippet requiring imports for Configuration, WebMvcConfigurer, FormatterRegistry, and the converter class. MVC can use this rule when binding query/path/form values to OrderCode in contexts that use ConversionService.

Do not assume a converter registered for MVC also replaces all JSON deserialization:
- @ModelAttribute uses MVC data binding.
- @RequestBody JSON typically goes through an HttpMessageConverter such as Jackson.
- Spring Boot configuration/property binding has its own integration path; configure the right subsystem.

## 8. Thread Safety, Null, and Side Effects

### 8.1. Thread Safety

Converters are typically registered once and used by many concurrent requests. Keep implementations stateless or use only immutable state. Do not store request data in fields and do not share mutable formatters such as SimpleDateFormat.

### 8.2. Null and Empty Strings

Distinguish null/absent, empty string, whitespace-only string, and syntactically invalid string. DataBinder/ConversionService/MVC may handle null/empty before invoking the converter. Do not collapse all of them into a single default code; that masks missing input. Null rules should be explicit at the boundary and consistent with validation.

### 8.3. Side Effects

A converter should be a lightweight, deterministic, and easily testable operation. If String → Customer requires querying a database, checking permissions, or making network calls, that usually belongs in an application service/use case rather than a pure converter because it introduces transactions, latency, and infrastructure failures.

## 9. Testing a Converter

You can test directly without a Spring context:

```java
@Test
void convertsNormalizedOrderCode() {
    OrderCode code = new StringToOrderCode().convert(" ord-000123 ");
    assertEquals("ORD-000123", code.value());
}

@Test
void rejectsInvalidOrderCode() {
    assertThrows(
        IllegalArgumentException.class,
        () -> new StringToOrderCode().convert("ORD-12")
    );
}
```

This is a JUnit 5 snippet, requiring test imports and dependencies. You should test the converter directly and then run integration tests to confirm the converter is registered in the right registry.

Cases to cover:
1. Valid canonical string.
2. Leading and trailing whitespace.
3. Lowercase prefix if policy permits.
4. Wrong or missing prefix.
5. Too few or too many digits.
6. Non-digit characters.
7. Empty/blank string.
8. No reverse direction when unregistered.
9. Register in MVC and bind a request.
10. Concurrent calls to confirm the converter holds no state.

Test canConvert and convert separately: the type path may exist while a specific value can still fail.

## 10. Common Pitfalls

| Pitfall | Consequence | How to Handle |
| --- | --- | --- |
| Assuming Converter automatically has a reverse direction | Registry has no T → S path | Register a reverse converter |
| Using Converter for locale-dependent formats | Parses regional formats incorrectly | Use Formatter |
| Believing canConvert=true means the input is valid | convert still throws an error | Validate actual values |
| Returning null for every error | Cannot distinguish missing from invalid | Define explicit null semantics |
| Converter with mutable state | Race condition | Stateless/thread-safe |
| Querying DB during parsing | Couples conversion to infrastructure | Move lookup to a service |
| Registering in the wrong registry | Subsystem does not see the converter | Register at the right extension point |
| Assuming an MVC converter handles JSON | Jackson still has its own configuration | Configure HttpMessageConverter |
| Overly broad GenericConverter | Matches unintended type pairs | Narrow scope or add conditions |
| Mixing conversion with validation | Hard to handle at the right layer | Converter converts types; validator/service checks rules |
| Using Object → String for everything | Representation is hard to control | Use converters for specific type pairs |

## 11. Choosing the Right SPI

- Converter<S,T>: one source type to one target type.
- Formatter<T>: locale-aware string parse/print.
- ConverterFactory<S,R>: one source to a family of target types sharing a base type.
- GenericConverter: multiple type pairs or when TypeDescriptor is needed.
- ConditionalGenericConverter: applied based on metadata conditions.

Choose based on the information the rule needs to know, not on the number of methods.

## 12. Self-Check

**1.** What does Converter<String, OrderCode> accept and return?  
Accepts String, returns OrderCode when successful.

**2.** Does the contract above automatically convert OrderCode to String?  
No. That is a different direction and requires its own rule.

**3.** Does canConvert(String.class, OrderCode.class) == true guarantee that the string "bad" can be converted?  
No. It only checks the type-level conversion path, not each individual value.

**4.** Should a technical code with a fixed syntax use Converter or Formatter?  
Usually Converter. Locale-dependent data should consider Formatter.

**5.** Should a Converter access the database to look up an entity?  
Usually no; lookup and authorization belong in a service/use case.

**6.** Does an MVC converter automatically handle JSON @RequestBody?  
Not by default. JSON typically goes through HttpMessageConverter/Jackson.

**7.** How do generics help despite Java type erasure?  
The compiler checks types at compile time. When runtime generic metadata is needed, use TypeDescriptor and more general SPIs.

## 13. Checklist for Adopting a Converter in a Project

1. Identify source type and target type; name by direction, e.g., StringToOrderCode.
2. Define parsing, normalization, and rejected input rules.
3. Protect invariants on the value object when needed.
4. Keep the converter stateless, thread-safe, and free of side effects.
5. Register in the right ConverterRegistry/FormatterRegistry or MVC extension point.
6. Invoke via ConversionService when an abstraction is needed.
7. Do not assume a reverse direction; register one separately if needed.
8. Test valid, invalid, boundary, blank, and registry integration cases.
9. Handle conversion errors in web/use-case layers without exposing stack traces.
10. Switch to another SPI when locale, generic metadata, target type family, or business lookup is needed.

**Remember:** Converter<S,T> is a **one-way contract for a single source–target type pair**. Generics describe the input/output types; the implementation handles concrete values; the registry and ConversionService let Spring find and invoke the right rule. Conversion, formatting, validation, and business logic are separate responsibilities.

## 14. Official References

- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): ConversionService, Converter, ConverterFactory, and registry.
- [Spring Javadoc — Converter (6.2.6)](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/core/convert/converter/Converter.html): convert(S source) contract.
- [Spring Javadoc — ConversionService (6.2.6)](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/core/convert/ConversionService.html): canConvert and convert.
- [Spring Javadoc — GenericConversionService (6.2.6)](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/core/convert/support/GenericConversionService.html): registry and dispatch.
- [Spring Javadoc — ConverterRegistry (6.2.6)](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/core/convert/converter/ConverterRegistry.html): registering converters and factories.
- [Spring MVC — Conversion and Formatting](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html): registering via WebMvcConfigurer.addFormatters.
