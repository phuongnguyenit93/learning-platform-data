# ConversionService and Spring Type Conversion Integration

Spring Framework provides a centralized type conversion system through **ConversionService**. Instead of having each component write its own logic to convert Strings to numbers, enums, domain types, or collections, an application can register converters once and share them across many places.

ConversionService is integrated into many Spring components such as SpEL, DataBinder, Spring MVC, and the configuration binding mechanism. As a result, the same conversion rules can be applied consistently when reading data, setting properties, binding requests, or evaluating expressions.

It is important to distinguish **conversion** from **formatting**. Conversion transforms a value from a source type to a target type; formatting typically converts between data types and text representations in a locale-aware manner, such as dates or currencies.

## 1. What is ConversionService?

### 1.1. Role of ConversionService

ConversionService is the central abstraction for checking and performing conversions between Java types.

For example:

- String to Integer or Long.
- String to enum.
- Number to another numeric type.
- String to an application-defined identifier type.
- Collection with source elements to a collection with target elements, when an appropriate converter exists.
- Object to a target type according to registered rules.

Instead of calling a separate utility function in each place, Spring components can ask ConversionService to perform conversion under the same policy.

### 1.2. Main Interface

Commonly used methods of ConversionService include:

~~~java
public interface ConversionService {

    boolean canConvert(
            Class<?> sourceType,
            Class<?> targetType
    );

    <T> T convert(
            Object source,
            Class<T> targetType
    );

    boolean canConvert(
            TypeDescriptor sourceType,
            TypeDescriptor targetType
    );

    Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType
    );
}
~~~

The two groups of overloads serve different needs:

- Use Class when you only need to know the source and target types at the class level.
- Use TypeDescriptor when more detailed metadata is needed, such as generic element types or annotations on a field/parameter.

Example of checking conversion capability:

~~~java
ConversionService conversionService =
        new DefaultConversionService();

boolean supported =
        conversionService.canConvert(String.class, Integer.class);
~~~

Performing conversion:

~~~java
Integer quantity =
        conversionService.convert("42", Integer.class);
~~~

If no suitable converter exists or the data cannot be converted, the convert operation may throw ConversionException or a specific subtype. canConvert checks whether support exists beforehand, but it does not guarantee every runtime value is valid. For example, String can be converted to Integer in terms of type, yet the string "abc" still cannot be parsed into a number.

### 1.3. ConversionService and ConverterRegistry

ConversionService provides the API to query and perform conversions. Converter registration is managed via ConverterRegistry.

Common implementations such as DefaultConversionService and GenericConversionService implement both roles: providing conversion capabilities and allowing converter registration.

From a design standpoint, consuming components usually only need to depend on the ConversionService interface. Application configuration keeps a reference to ConverterRegistry or a concrete implementation to register converters.

## 2. Commonly Used Implementations

### 2.1. GenericConversionService

GenericConversionService is the foundational implementation that manages a set of converters and resolves the appropriate converter for a source/target type pair.

An application can create an instance and register converters:

~~~java
GenericConversionService conversionService =
        new GenericConversionService();

conversionService.addConverter(
        String.class,
        CustomerCode.class,
        CustomerCode::new
);
~~~

After registration, the ConversionService interface can be used to convert:

~~~java
CustomerCode code =
        conversionService.convert("C-100", CustomerCode.class);
~~~

GenericConversionService is suitable when the application wants full control over which converters are registered. If common built-in converters are needed, DefaultConversionService is usually more convenient.

### 2.2. DefaultConversionService

DefaultConversionService provides standard converters commonly used for Java types and collections. It is a common choice for applications needing Spring's default set of converters.

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

Integer count =
        conversionService.convert("25", Integer.class);

Boolean enabled =
        conversionService.convert("true", Boolean.class);
~~~

DefaultConversionService also implements ConverterRegistry, so additional converters can be registered:

~~~java
conversionService.addConverter(
        String.class,
        CustomerCode.class,
        CustomerCode::new
);
~~~

If an application needs multiple shared conversion rules, configure a ConversionService at the composition root and pass this interface to the components that need it.

### 2.3. FormattingConversionService

FormattingConversionService extends the conversion system to support Formatters and formatting annotations. It fits scenarios that require locale-aware conversion between strings and data types.

For example, dates can have multiple representations depending on locale. A Formatter can parse an input string into LocalDate and print LocalDate to a string according to a configured format.

DefaultFormattingConversionService provides default formatting configuration along with common converters. It is a common foundation in web data binding.

### 2.4. Choosing an Implementation

| Implementation | Primary Purpose | When to Use |
|---|---|---|
| GenericConversionService | Foundational conversion engine | Want to register the converter set yourself |
| DefaultConversionService | ConversionService with standard converters | Need common type conversions |
| FormattingConversionService | Conversion combined with Formatter | Need locale-aware and annotation-based formatting |
| DefaultFormattingConversionService | Formatting service with default configuration | Need common conversion and formatting |

Do not create multiple separate ConversionServices with different rules if the business logic requires consistent conversion. Clearly define the scope: application-wide, web layer, or a specific SpEL context.

## 3. Registering Custom Converters

### 3.1. Converter<S, T>

Converter is a simple way to define conversion from one source type to one target type:

~~~java
public interface Converter<S, T> {
    T convert(S source);
}
~~~

Example of creating an identifier type:

~~~java
public record CustomerCode(String value) {
    public CustomerCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Customer code is required"
            );
        }
    }
}
~~~

Registering a converter from String to CustomerCode:

~~~java
Converter<String, CustomerCode> customerCodeConverter =
        CustomerCode::new;

DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(customerCodeConverter);
~~~

Usage:

~~~java
CustomerCode code =
        conversionService.convert("C-100", CustomerCode.class);
~~~

A converter should focus on a single type pair and have deterministic behavior. If input data is invalid, throw an appropriate error instead of silently creating an invalid object.

### 3.2. ConverterFactory<S, R>

ConverterFactory is suitable when one source type can be converted to a family of target types sharing a common supertype or interface.

A typical example is converting String to enums:

~~~java
public class StringToEnumConverterFactory
        implements ConverterFactory<String, Enum> {

    @Override
    public <T extends Enum> Converter<String, T> getConverter(
            Class<T> targetType) {

        return source -> (T) Enum.valueOf(
                targetType,
                source.trim().toUpperCase(Locale.ROOT)
        );
    }
}
~~~

Registering the factory:

~~~java
conversionService.addConverterFactory(
        new StringToEnumConverterFactory()
);
~~~

Then you can convert a String to the corresponding target enum if the constant name is valid.

For example:

~~~java
OrderStatus status =
        conversionService.convert("paid", OrderStatus.class);
~~~

In the example, uppercase normalization is performed using Locale.ROOT to avoid depending on the machine's default locale. Choose a normalization policy appropriate for the domain; not every enum should ignore case or whitespace.

### 3.3. GenericConverter

GenericConverter is suitable when you need to support multiple source/target type pairs or need more detailed type information.

This interface provides a set of ConvertiblePairs and a convert method receiving the source along with TypeDescriptors for both sides:

~~~java
public interface GenericConverter {

    Set<ConvertiblePair> getConvertibleTypes();

    Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType
    );
}
~~~

Example of a converter declaring support for a type pair:

~~~java
public Set<ConvertiblePair> getConvertibleTypes() {
    return Set.of(
            new ConvertiblePair(String.class, CustomerCode.class)
    );
}
~~~

GenericConverter is useful when conversion rules depend on generic types, metadata, or multiple target types. For a simple single pair, Converter is usually more readable and requires less code.

### 3.4. ConditionalGenericConverter

ConditionalGenericConverter adds a condition to decide whether a converter applies to a specific pair of TypeDescriptors.

This is useful when the same type pair has multiple rules, yet only certain fields or annotations should use that converter.

Structural example:

~~~java
public class CustomConditionalConverter
        implements ConditionalGenericConverter {

    @Override
    public Set<ConvertiblePair> getConvertibleTypes() {
        return Set.of(
                new ConvertiblePair(String.class, CustomerCode.class)
        );
    }

    @Override
    public boolean matches(
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {
        return targetType.hasAnnotation(SpecialCode.class);
    }

    @Override
    public Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {
        return new CustomerCode(source.toString());
    }
}
~~~

This snippet illustrates using target metadata to select a converter. In a real application, the annotation must be placed on metadata visible to TypeDescriptor, and the converter must check for null, malformed data, and invariants of the target type.

## 4. TypeDescriptor and Generic Types

### 4.1. Why Class Is Not Enough

Java generics undergo type erasure at runtime. The following two fields both have raw type List, yet different element types:

~~~java
List<String> names;
List<Integer> quantities;
~~~

Looking only at List.class, ConversionService does not know whether elements should be converted to String or Integer.

TypeDescriptor preserves additional metadata about collection types, element types, annotations, and declaration sources when available.

### 4.2. Creating a TypeDescriptor

You can obtain a descriptor from a field or method parameter:

~~~java
Field field = Report.class.getDeclaredField("quantities");

TypeDescriptor sourceType =
        new TypeDescriptor(field);
~~~

You can create a descriptor for a collection with a specific element type:

~~~java
TypeDescriptor stringListType =
        TypeDescriptor.collection(
                List.class,
                TypeDescriptor.valueOf(String.class)
        );
~~~

And a descriptor for the target type:

~~~java
TypeDescriptor integerListType =
        TypeDescriptor.collection(
                List.class,
                TypeDescriptor.valueOf(Integer.class)
        );
~~~

Use the convert overload accepting TypeDescriptor when you want ConversionService to know the element types as well:

~~~java
Object converted = conversionService.convert(
        List.of("10", "20"),
        stringListType,
        integerListType
);
~~~

Collection conversion capability depends on registered converters and source/target metadata. TypeDescriptor supplies the information for converters to process properly, but it does not create an unsupported conversion rule on its own.

### 4.3. Annotations on TypeDescriptor

TypeDescriptor can carry annotations from a field or parameter. A Formatter or ConditionalGenericConverter can use that metadata to choose how to process the value.

For example, a field with a date-formatting annotation may need to be parsed using a specific pattern. Reading annotations from TypeDescriptor allows the converter/formatter to apply rules based on the declaration site rather than hard-coding property names.

Do not use annotations to store sensitive data or authorization policies. Metadata only assists with selecting conversion/formatting; access permissions must still be checked at the appropriate layer.

## 5. Checking and Performing Conversion

### 5.1. Using canConvert Before convert

You can check a type pair:

~~~java
if (conversionService.canConvert(String.class, Integer.class)) {
    Integer value =
            conversionService.convert("42", Integer.class);
}
~~~

canConvert answers whether the service has a conversion path for the source/target types. It does not pre-validate every concrete value.

For example, String to Integer may be supported, yet a non-numeric string will still fail during convert.

### 5.2. Handling ConversionException

When data comes from users, handle conversion errors explicitly:

~~~java
try {
    Integer quantity =
            conversionService.convert(input, Integer.class);
} catch (ConversionException ex) {
    throw new IllegalArgumentException(
            "Quantity must be a valid integer",
            ex
    );
}
~~~

Do not catch the exception and return 0 if 0 is not a valid fallback in business terms. Preserve the cause so internal logs can identify which converter or input data caused the failure.

### 5.3. Null and Primitive Target Types

Reference types can represent null, whereas primitives such as int and boolean cannot. When the source is null or conversion cannot produce a primitive value, the operation may fail.

If a field can be missing, consider using wrapper types such as Integer or Boolean, or validate required fields before converting. Do not automatically treat null as 0 or false unless the domain defines it that way.

## 6. Integrating ConversionService with SpEL

### 6.1. SpEL Uses TypeConverter

SpEL uses the EvaluationContext's TypeConverter to convert values when needed, for example:

- Assigning values to a property with a target type.
- Converting arguments to invoke a method.
- Converting arguments when invoking a constructor.
- Converting results to the type requested by the caller in getValue.

StandardTypeConverter is the adapter connecting SpEL to Spring's ConversionService system.

### 6.2. Using the Default ConversionService

StandardEvaluationContext has a default TypeConverter based on Spring's standard conversion mechanism. For common types, no additional configuration may be required.

Example of a method requiring Long:

~~~java
public String findCustomer(Long id) {
    return "Customer-" + id;
}
~~~

Expression passing String:

~~~java
#service.findCustomer('42')
~~~

If the default converter supports String to Long, SpEL can convert the argument before invoking the method.

### 6.3. Attaching a Custom ConversionService to SpEL

When an application has domain-specific converters, create a StandardTypeConverter from that ConversionService:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        CustomerCode.class,
        CustomerCode::new
);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeConverter(
        new StandardTypeConverter(conversionService)
);

context.setVariable("customerService", customerService);
~~~

If a method accepts CustomerCode:

~~~java
public String lookup(CustomerCode code) {
    return code.value();
}
~~~

Expression:

~~~java
#customerService.lookup('C-100')
~~~

SpEL uses the context's TypeConverter to convert the String into CustomerCode before calling the method.

### 6.4. Conversion During setValue

ConversionService can also be used when assigning a value to a property with a target type:

~~~java
parser.parseExpression("quantity")
        .setValue(context, "25");
~~~

If the quantity property is Integer and TypeConverter supports String to Integer, SpEL can convert the value before writing it.

This depends on the property being writable and the PropertyAccessor supporting the set operation. A read-only property cannot be updated simply because a matching converter exists.

### 6.5. Conversion of getValue Results

You can request a result type:

~~~java
Integer quantity = parser
        .parseExpression("'25'")
        .getValue(context, Integer.class);
~~~

In this case, SpEL asks TypeConverter to convert the String result to Integer if needed.

This is conversion on the result side, distinct from argument conversion prior to a method call. When debugging, separate the two stages to know which step failed.

## 7. Integrating with Spring MVC and DataBinder

### 7.1. DataBinder

DataBinder uses conversion and binding mechanisms to populate input data into properties of a target object. When request or form data is bound to a DTO, Spring needs to convert string values to the corresponding property types.

Example DTO:

~~~java
public class SearchForm {

    private Integer pageSize;

    public Integer getPageSize() {
        return pageSize;
    }

    public void setPageSize(Integer pageSize) {
        this.pageSize = pageSize;
    }
}
~~~

Text data "20" can be converted to Integer when the binder has a suitable ConversionService.

DataBinder also manages binding errors and BindingResult, allowing the application to report errors per field rather than letting conversion exceptions propagate outward.

### 7.2. Configuring ConversionService for a Binder

You can provide a ConversionService to DataBinder:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

DataBinder binder = new DataBinder(new SearchForm());
binder.setConversionService(conversionService);
~~~

The binder then uses this service when converting data into properties.

In a real web application, Spring MVC manages binders and conversion services according to MVC configuration. Avoid creating a new DataBinder per field when the framework already provides standard binding mechanisms.

### 7.3. Spring MVC and WebMvcConfigurer

You can register converters or formatters for Spring MVC via WebMvcConfigurer:

~~~java
@Configuration
public class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
                String.class,
                CustomerCode.class,
                CustomerCode::new
        );
    }
}
~~~

FormatterRegistry allows registering appropriate Converters, ConverterFactories, GenericConverters, and Formatters.

Converters registered here can be used when binding request parameters, path variables, and other web data according to MVC mechanisms.

Avoid registering overly broad converters, such as String to Object or a converter that alters the semantics of many types. A narrow converter for a specific domain type is easier to control.

## 8. Integrating with Spring Boot and Application Configuration

### 8.1. Using an Application-Managed ConversionService

An application can declare a ConversionService bean for dependent components to share:

~~~java
@Configuration
public class ConversionConfiguration {

    @Bean
    public ConversionService conversionService() {
        DefaultConversionService service =
                new DefaultConversionService();

        service.addConverter(
                String.class,
                CustomerCode.class,
                CustomerCode::new
        );

        return service;
    }
}
~~~

The bean name and how Spring Boot or Spring MVC selects a ConversionService may depend on the application type and existing configuration. When integrating for MVC, WebMvcConfigurer.addFormatters is the explicit extension point; when using in SpEL, pass the service into the EvaluationContext's StandardTypeConverter.

Do not assume an arbitrary ConversionService bean always replaces every internal service of all subsystems. Check the exact integration point your application uses.

### 8.2. Configuration Binding

Spring Boot uses conversion when binding configuration to Java types. For example, strings in properties or YAML can be converted into Duration, DataSize, enums, or application types if a matching converter exists.

Example configuration:

~~~yaml
app:
  retry-count: 3
  timeout: 5s
~~~

Configuration DTO:

~~~java
@ConfigurationProperties(prefix = "app")
public class AppProperties {

    private int retryCount;
    private Duration timeout;

    // getters and setters
}
~~~

Spring converts configuration values to property types according to the conversion service and converters configured for binding.

For custom types, register converters at the extension point appropriate for the configuration binding mechanism of the Spring Boot version in use. Do not confuse MVC converters with all configuration properties converters if their registration scopes differ.

## 9. ConversionService and Formatter

### 9.1. Conversion Differs from Formatting

Conversion focuses on transforming a value from one type to another. Formatting focuses on representing data as text and parsing text back, typically in a locale-dependent way.

For example:

- String "42" to Integer 42: conversion.
- LocalDate to "12/11/2026" by locale: formatting.
- String in a date pattern to LocalDate: parsing via Formatter.

Formatter has two primary operations:

~~~java
public interface Formatter<T> extends Printer<T>, Parser<T> {
}
~~~

Printer produces a string from an object; Parser reads a string into an object according to a Locale.

### 9.2. Registering a Formatter

Example formatter for LocalDate:

~~~java
public class IsoDateFormatter implements Formatter<LocalDate> {

    @Override
    public LocalDate parse(
            String text,
            Locale locale) {
        return LocalDate.parse(text);
    }

    @Override
    public String print(
            LocalDate object,
            Locale locale) {
        return object.toString();
    }
}
~~~

Registration:

~~~java
DefaultFormattingConversionService service =
        new DefaultFormattingConversionService();

service.addFormatter(new IsoDateFormatter());
~~~

This formatter uses LocalDate's ISO format. If the application needs locale-specific formatting or configured patterns, use an appropriate formatter and test across multiple locales.

### 9.3. Annotation Formatting

Spring supports formatting annotations to attach formatting metadata to fields or parameters. TypeDescriptor can carry these annotations so FormattingConversionService selects the appropriate formatter.

For example, in a web application, a date-formatting annotation can determine how a request parameter is parsed into LocalDate. Formatter selection depends on metadata and formatter registry configuration.

Do not use Formatter for every conversion. For domain types that do not require locale-aware text representation, Converter is usually simpler.

## 10. Designing Good Converters

A converter should have a clear scope and predictable behavior:

- Only convert the source/target type pair it genuinely understands.
- Check malformed data and report meaningful errors.
- Do not access databases or make network calls inside convert.
- Do not mutate state or perform side effects.
- Do not return fake values such as 0, false, or empty objects to hide errors.
- Handle null according to the contract of ConversionService and the target type.
- Use TypeDescriptor when rules depend on generics or annotations.
- Avoid registering overly broad converters that conflict with standard converters.

Converters should be lightweight and pure. If creating a domain object requires a database lookup, perform it in the service/application layer and pass the validated object where needed.

### 10.1. Avoiding Ambiguous Converters

If there are multiple converters for the same type pair or multiple indirect conversion paths, outcomes can become hard to predict. Keep the converter set lean and avoid registering two competing rules for the same purpose.

For distinct domain concepts, create separate target types and specific converters rather than a single String-to-Object converter.

### 10.2. Configure Before Use

ConversionService is often shared across multiple components. Complete converter registration during configuration before serving concurrent requests or evaluating expressions.

Avoid modifying the registry arbitrarily while multiple threads are using the service. If the converter set must change, manage the configuration lifecycle explicitly.

## 11. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| canConvert returns false | No converter for the type pair | Register an appropriate converter or change the input type |
| canConvert is true but convert fails | Runtime value is malformed | Validate data and handle ConversionException |
| Collection converts elements incorrectly | Only raw Class used, missing generic metadata | Use TypeDescriptor when needed |
| Converter is not used by MVC | Registered in the wrong scope or extension point | Check WebMvcConfigurer and MVC configuration |
| SpEL does not use custom converter | Context still uses a different default TypeConverter | Attach StandardTypeConverter with the intended ConversionService |
| Property does not update | Property is read-only or accessor does not support write | Check setter and PropertyAccessor |
| Date string parsed with wrong locale | Inappropriate converter/formatter used | Register Formatter and test locales |
| Multiple converters compete | Registered rules are too broad or overlapping | Narrow type pairs and inspect the registry |
| Invalid data replaced with defaults | Converter hides errors | Throw a conversion error and handle it at the appropriate layer |

## 12. Complete Example: One Converter Used in Java and SpEL

Create a domain type:

~~~java
public record CustomerCode(String value) {
    public CustomerCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Customer code is required"
            );
        }
    }
}
~~~

Create ConversionService:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        CustomerCode.class,
        CustomerCode::new
);
~~~

Use directly in Java:

~~~java
CustomerCode code =
        conversionService.convert("C-100", CustomerCode.class);
~~~

Use in SpEL:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeConverter(
        new StandardTypeConverter(conversionService)
);

context.setVariable("customerService", customerService);

CustomerCode result = parser
        .parseExpression(
                "#customerService.find('C-100')"
        )
        .getValue(context, CustomerCode.class);
~~~

If the find method accepts CustomerCode, SpEL can use TypeConverter to convert the String argument to the domain type before calling it. If the method returns CustomerCode, the result type is already correct and requires no further conversion.

This example illustrates reusing the same conversion rule in both Java and SpEL.

## 13. Testing ConversionService

You should test type support, valid values, and invalid data:

~~~java
DefaultConversionService service =
        new DefaultConversionService();

assertTrue(
        service.canConvert(String.class, Integer.class)
);

assertEquals(
        Integer.valueOf(42),
        service.convert("42", Integer.class)
);
~~~

Testing a custom converter:

~~~java
service.addConverter(
        String.class,
        CustomerCode.class,
        CustomerCode::new
);

assertEquals(
        new CustomerCode("C-100"),
        service.convert("C-100", CustomerCode.class)
);
~~~

And testing invalid data:

~~~java
assertThrows(
        IllegalArgumentException.class,
        () -> service.convert(" ", CustomerCode.class)
);
~~~

Depending on the converter and how exceptions are wrapped, verify the actual exception returned by the public API. Avoid writing tests that depend on internal framework messages if those messages are not part of the application contract.

For SpEL integration, specifically test:

- Method arguments needing type conversion.
- Constructor arguments needing type conversion.
- Assigning properties using setValue.
- getValue with a target type different from the result type.
- Generic collections with elements needing conversion.
- Custom converters and converter failure cases.

For Spring MVC, add tests for request parameter binding and BindingResult to ensure errors are attached to the right fields.

## 14. Summary

ConversionService is Spring's shared type conversion abstraction. It supports checking conversion capability, performing conversions, and integrating custom converters.

- **DefaultConversionService** provides common converters.
- **GenericConversionService** is the foundation for managing converters.
- **Converter**, **ConverterFactory**, **GenericConverter**, and **ConditionalGenericConverter** address different registration needs.
- **TypeDescriptor** preserves generic and annotation metadata when Class alone is insufficient.
- **StandardTypeConverter** connects ConversionService to SpEL.
- Spring MVC, DataBinder, and configuration binding use conversion in their respective binding workflows.
- **Formatter** handles text parsing/printing and often requires locale; it complements conversion rather than replacing all converters.

Register specific, lightweight converters with deterministic behavior; configure the service before use; test malformed data and real integration points. When the same conversion rules are needed in Java, SpEL, and Spring binding, configure the proper ConversionService at each scope so behavior stays consistent and easy to control.