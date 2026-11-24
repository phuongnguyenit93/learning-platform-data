# Annotation-Based Conversion on Fields or Parameters in Spring

## 1. Core Idea: Same Java Type, Different Formatting

An application can have multiple properties of the same Java type that are parsed or formatted using different text rules. For example, one `LocalDate` is entered as ISO `yyyy-MM-dd`; another `LocalDate` is entered as `dd/MM/yyyy`; two `BigDecimal` values can represent a percentage and a monetary amount respectively; two method parameters both have type `String`, yet one must be parsed into a date while the other stays as-is.

Looking only at the `String → LocalDate` or `String → BigDecimal` type pair, `ConversionService` does not know which formatting contract a particular property carries. **`TypeDescriptor`** and **annotation-driven formatting** add field or method parameter metadata to the conversion decision.

Common annotations include:

- **@DateTimeFormat**: date/time formatting on a field or method parameter.
- **@NumberFormat**: number formatting on a field or method parameter.
- **@DurationFormat**: `Duration` formatting in Spring versions that support it.
- Custom annotations paired with **AnnotationFormatterFactory**: define custom parsers/printers.

An annotation does not execute by itself as a standalone parse command. It is read by the formatting infrastructure inside **FormattingConversionService** via `TypeDescriptor` metadata. When a binder or application performs conversion with that descriptor, Spring can select the parser/printer associated with the annotation.

## 2. TypeDescriptor Is the Bridge Between Annotations and Conversion

The two conversion calls below do not carry the same level of metadata:

~~~java
service.convert("29/02/2024", String.class, LocalDate.class);
~~~

~~~java
TypeDescriptor source = TypeDescriptor.valueOf(String.class);
TypeDescriptor target = new TypeDescriptor(dateField);

service.convert("29/02/2024", source, target);
~~~

The second approach passes a descriptor for a specific field, enabling Spring to read `@DateTimeFormat` on that field. This is why this lesson belongs under **Advanced Conversion**: conversion decisions depend not only on source/target types, but also on metadata declared at the site where the value is used.

`TypeDescriptor` can carry:
- The underlying Java type.
- Generic types, component types, and container key/value types.
- Annotations present on a field, method parameter, or property.
- The declaration context of the descriptor.

Example reading field metadata:

~~~java
Field field = BookingForm.class.getDeclaredField("travelDate");
TypeDescriptor descriptor = new TypeDescriptor(field);
~~~

For a method parameter, you can construct a `MethodParameter` and pass it to `TypeDescriptor`:

~~~java
Method method = SearchController.class.getMethod("search", LocalDate.class);
MethodParameter parameter = new MethodParameter(method, 0);
TypeDescriptor descriptor = new TypeDescriptor(parameter);
~~~

These are metadata-retrieval examples; corresponding classes, imports, and methods are required. Do not use `TypeDescriptor.valueOf(LocalDate.class)` when field/parameter annotations are needed, because a descriptor created solely from `Class` has no knowledge of which field/parameter carried the annotation.

## 3. Built-In Annotations in Spring

### 3.1. @DateTimeFormat

`@DateTimeFormat` can be placed on a **field** or **method parameter**. It supports `java.util.Date`, `Calendar`, `Long` in timestamp contexts, and Spring-supported `java.time` types.

~~~java
@DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
private LocalDate departureDate;

@DateTimeFormat(pattern = "dd/MM/yyyy")
private LocalDate localDate;

@DateTimeFormat(style = "M-")
private LocalDate mediumDate;
~~~

- **iso** uses a chosen standard ISO format, such as `ISO.DATE`.
- **pattern** uses a specific pattern; an explicit choice when the API contract dictates a format.
- **style** relies on Locale-based formatting and can vary across Java/Locale environments; avoid it when a stable wire format contract is required.
- **fallbackPatterns** allows declaring fallback patterns when legacy data or multiple input formats must be supported.
- The `style`, `iso`, and `pattern` attributes are mutually exclusive per the annotation contract; choose one approach per annotation instance.

For `java.util.Date`, the time zone affects the meaning of the instant. For `java.time.LocalDate`, the type stores neither time nor time zone; choose the domain type matching a calendar date versus an actual instant.

Spring documentation warns that style-based parsing depends on Locale and runtime patterns, which can change when running on newer JDKs (especially JDK 20+). If the format is part of a system contract, prefer ISO or an explicit pattern controlled by the application.

### 3.2. @NumberFormat

`@NumberFormat` supports `Number` types such as `BigDecimal`, `Integer`, and other compatible numeric types.

~~~java
@NumberFormat(pattern = "#,##0.00")
private BigDecimal amount;

@NumberFormat(style = NumberFormat.Style.CURRENCY)
private BigDecimal total;
~~~

- **pattern** describes a concrete number pattern following `NumberFormat` rules.
- **style** offers `NUMBER`, `PERCENT`, and `CURRENCY` options.
- Parsing/printing behavior can depend on Locale; web applications should align Locale and how clients send numbers.
- Display formatting does not automatically become a business rule such as ensuring `amount` is greater than 0 or within budget.

For instance, `"1,234.50"` and `"1.234,50"` can mean different things depending on Locale. If receiving data from integration APIs, specify an explicit format rather than arbitrarily replacing dots/commas with ad-hoc string manipulation.

### 3.3. Other Annotations and Support Scope

Depending on the Spring version, other formatting annotations such as **@DurationFormat** are also supported. Check the Javadoc for your exact application version before using them. Validation annotations like `@Min`, `@NotNull`, or `@Pattern` are not formatting annotations: they check constraints, not create parsers/printers.

| Group | Example | Responsibility |
| --- | --- | --- |
| Format annotation | @DateTimeFormat, @NumberFormat | Guides parsing/printing based on metadata |
| Validation annotation | @NotNull, @Min, @Pattern | Checks whether a value satisfies constraints |
| JSON mapping annotation | @JsonProperty | Maps property names when Jackson reads/writes JSON |
| Binding annotation | @ModelAttribute, @BindParam | Defines how data is received and bound in Spring MVC |

## 4. Mechanism Behind the Scenes: AnnotationFormatterFactory

Spring defines the interface:

~~~java
public interface AnnotationFormatterFactory<A extends Annotation> {
    Set<Class<?>> getFieldTypes();
    Printer<?> getPrinter(A annotation, Class<?> fieldType);
    Parser<?> getParser(A annotation, Class<?> fieldType);
}
~~~

The three methods have distinct roles:

- **getFieldTypes()**: returns the set of field types permitted to use this annotation.
- **getPrinter(annotation, fieldType)**: provides a formatter to print a Java value as a string.
- **getParser(annotation, fieldType)**: provides a parser to convert an input string into a Java value.

Spring uses the annotation found in `TypeDescriptor` to query the factory and obtain the appropriate parser/printer. This interface is useful when formatting depends on an application-defined annotation or when extending annotation-based formatting.

A **Formatter<T>** combines both `Printer<T>` and `Parser<T>` roles:

~~~java
public interface Formatter<T> extends Printer<T>, Parser<T> {}
~~~

`Parser<T>.parse(String text, Locale locale)` converts text into an object. `Printer<T>.print(T object, Locale locale)` converts an object into text.

### Distinguishing AnnotationFormatterFactory from ConditionalGenericConverter

| Mechanism | When to Use | Primary Metadata |
| --- | --- | --- |
| AnnotationFormatterFactory | An annotation controls parsing/printing for a field or parameter | Annotation + field type |
| ConditionalGenericConverter | Converter needs advanced selection conditions based on descriptors | Source/target TypeDescriptor |
| Converter<S,T> | Converts one simple type pair without annotation context | Source and target types |
| Formatter<T> | Formats one type according to Locale | Value + Locale |

Do not create an `AnnotationFormatterFactory` if `@DateTimeFormat` or `@NumberFormat` already meets the need. Write a custom factory only when a rule has reusable value and needs to be tied explicitly to a custom annotation.

## 5. Custom Annotation Formatter Example

Suppose an application has a **@TrimmedUppercase** annotation so certain `String` fields are parsed by stripping leading/trailing whitespace and uppercasing using `Locale.ROOT`. This is a technical example; real systems should consider which fields are allowed to be transformed since display names may need to preserve lowercase letters.

Annotation:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.FIELD, ElementType.PARAMETER})
public @interface TrimmedUppercase {
}
~~~

Formatter:

~~~java
public final class UppercaseFormatter implements Formatter<String> {

    @Override
    public String parse(String text, Locale locale) {
        return text == null ? null : text.strip().toUpperCase(Locale.ROOT);
    }

    @Override
    public String print(String object, Locale locale) {
        return object == null ? "" : object;
    }
}
~~~

Factory:

~~~java
public final class TrimmedUppercaseAnnotationFormatterFactory
        implements AnnotationFormatterFactory<TrimmedUppercase> {

    @Override
    public Set<Class<?>> getFieldTypes() {
        return Set.of(String.class);
    }

    @Override
    public Printer<?> getPrinter(
            TrimmedUppercase annotation, Class<?> fieldType) {
        return new UppercaseFormatter();
    }

    @Override
    public Parser<?> getParser(
            TrimmedUppercase annotation, Class<?> fieldType) {
        return new UppercaseFormatter();
    }
}
~~~

Register in `FormattingConversionService`:

~~~java
DefaultFormattingConversionService service =
        new DefaultFormattingConversionService();

service.addFormatterForFieldAnnotation(
        new TrimmedUppercaseAnnotationFormatterFactory());
~~~

Then use on the model:

~~~java
public final class CustomerForm {
    @TrimmedUppercase
    private String customerCode;

    public String getCustomerCode() { return customerCode; }
    public void setCustomerCode(String customerCode) {
        this.customerCode = customerCode;
    }
}
~~~

When conversion uses the descriptor of the `customerCode` field, Spring can activate the corresponding factory. If only `String.class` and `String.class` are passed, the field's annotation metadata is absent; the factory cannot be expected to be chosen by field annotation.

## 6. Complete Java 17+ Example: Fields and Method Parameters

This Maven example uses **Java 17** and **Spring Framework 6.2.15**. It demonstrates:
1. `@DateTimeFormat` on a `LocalDate` field.
2. `@NumberFormat` on a `BigDecimal` field.
3. `@DateTimeFormat` on a method parameter.
4. Conversion using `TypeDescriptor` extracted from the exact field/parameter.
5. Same target type with an unannotated descriptor does not automatically inherit field formatting.

Structure:

~~~text
annotation-formatting-demo/
├── pom.xml
└── src/main/java/demo/AnnotationFormattingDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>annotation-formatting-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.15</version>
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
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/AnnotationFormattingDemo.java**:

~~~java
package demo;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Locale;

import org.springframework.core.MethodParameter;
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.TypeDescriptor;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.format.annotation.NumberFormat;
import org.springframework.format.support.DefaultFormattingConversionService;

public final class AnnotationFormattingDemo {

    public static final class BookingForm {
        @DateTimeFormat(pattern = "dd/MM/yyyy")
        private LocalDate travelDate;

        @NumberFormat(pattern = "#,##0.00")
        private BigDecimal amount;

        public LocalDate getTravelDate() { return travelDate; }
        public void setTravelDate(LocalDate travelDate) {
            this.travelDate = travelDate;
        }
        public BigDecimal getAmount() { return amount; }
        public void setAmount(BigDecimal amount) {
            this.amount = amount;
        }
    }

    public static final class SearchParameters {
        public void search(
                @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
                LocalDate date) {
            // Only the method signature is needed to create MethodParameter.
        }
    }

    public static void main(String[] args) throws Exception {
        Locale.setDefault(Locale.US);
        ConversionService service = new DefaultFormattingConversionService();

        Field dateField = BookingForm.class.getDeclaredField("travelDate");
        TypeDescriptor dateTarget = new TypeDescriptor(dateField);

        LocalDate date = (LocalDate) service.convert(
                "29/02/2024",
                TypeDescriptor.valueOf(String.class),
                dateTarget);
        System.out.println("FIELD_DATE=" + date);

        Field amountField = BookingForm.class.getDeclaredField("amount");
        TypeDescriptor amountTarget = new TypeDescriptor(amountField);

        BigDecimal amount = (BigDecimal) service.convert(
                "1,234.50",
                TypeDescriptor.valueOf(String.class),
                amountTarget);
        System.out.println("FIELD_AMOUNT=" + amount.toPlainString());

        Method method = SearchParameters.class.getMethod(
                "search", LocalDate.class);
        MethodParameter parameter = new MethodParameter(method, 0);
        TypeDescriptor parameterTarget = new TypeDescriptor(parameter);

        LocalDate queryDate = (LocalDate) service.convert(
                "2024-03-01",
                TypeDescriptor.valueOf(String.class),
                parameterTarget);
        System.out.println("PARAMETER_DATE=" + queryDate);

        boolean supported = service.canConvert(
                TypeDescriptor.valueOf(String.class), dateTarget);
        System.out.println("ANNOTATED_PAIR_SUPPORTED=" + supported);
    }
}
~~~

In the directory containing `pom.xml`, run:

~~~bash
mvn -q compile exec:java
~~~

Expected output:

~~~text
FIELD_DATE=2024-02-29
FIELD_AMOUNT=1234.50
PARAMETER_DATE=2024-03-01
ANNOTATED_PAIR_SUPPORTED=true
~~~

**Key points to note:**
- `dateTarget` is constructed from a field with `@DateTimeFormat(pattern = "dd/MM/yyyy")`, so the date string uses that format.
- `amountTarget` carries `@NumberFormat(pattern = "#,##0.00")`; formatting/parsing depends on Locale. The demo sets `Locale.US` so numeric output is deterministic.
- `parameterTarget` is constructed from a `MethodParameter` with `@DateTimeFormat(iso = ISO.DATE)`, so it uses the ISO date format.
- `canConvert` with `TypeDescriptor` can select a conversion path based on annotation metadata, yet still does not verify that a specific string is a valid date. The actual `convert` call can still throw a conversion exception if the string is malformed.

## 7. Using Annotations with Spring MVC

In Spring MVC, `@DateTimeFormat` and `@NumberFormat` are commonly applied directly on model fields or parameters:

~~~java
public final class ReportFilter {
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate fromDate;

    @NumberFormat(pattern = "#,##0.00")
    private BigDecimal minimumAmount;

    // Getters/setters...
}
~~~

Controller accepting the model attribute:

~~~java
@GetMapping("/reports")
public String reports(
        @Valid @ModelAttribute("filter") ReportFilter filter,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "report-filter";
    }
    return "reports";
}
~~~

This is an integration snippet in an MVC application with DTOs, views, imports, and a validation provider; it is not a standalone program. Spring MVC registers default formatters and supports formatting annotations on fields/parameters. If using custom MVC configuration, ensure the corresponding formatter/conversion service remains registered.

Shared formatters or converters can be added via `WebMvcConfigurer`:

~~~java
@Configuration
public class WebConfiguration implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        // registry.addFormatter(...);
        // registry.addFormatterForFieldAnnotation(...);
        // registry.addConverter(...);
    }
}
~~~

The snippet above is an extension point; add beans, formatters, and imports per your actual application. Do not create a standalone `FormattingConversionService` and assume Spring MVC will automatically use it unless registered in MVC configuration.

**JSON scope:** `@RequestBody` JSON normally goes through Jackson/`HttpMessageConverter`. `@DateTimeFormat` is a formatting annotation for Spring's conversion/formatting; it does not replace `@JsonFormat` or `@JsonProperty` when Jackson formats/reads JSON. If an endpoint supports both query/form and JSON, test each branch separately.

## 8. Limitations and Diagnostics

### 8.1. Annotation Absent from Descriptor

If you use:

~~~java
TypeDescriptor target = TypeDescriptor.valueOf(LocalDate.class);
~~~

the descriptor only knows the target is `LocalDate` and carries no `@DateTimeFormat` from a specific field. For annotation-driven formatting, build the descriptor from a `Field` or `MethodParameter`.

### 8.2. Both Source and Target Descriptors Matter

Annotations typically reside on the target field/parameter descriptor when parsing input. With custom converters, source metadata can also participate in conditions. Identify exactly where the annotation is declared and which descriptor is passed during `convert`.

### 8.3. canConvert Does Not Guarantee Successful Parsing

`canConvert(String.class, LocalDate.class)` can reflect a general converter for the type pair; when using the `TypeDescriptor` overload, annotations can influence converter selection. Even so, `convert("31/02/2024", ...)` can still fail. A syntactically well-formed date can also be invalid under domain rules.

### 8.4. Locale and Timezone

`@NumberFormat` can depend on Locale; `@DateTimeFormat(style=...)` also depends on runtime Locale/style. With `java.util.Date`, time zones affect representation. Do not use `LocalDate` for data requiring a global instant; do not use `Date` when only a calendar date is needed. Specify data types and formats explicitly at API boundaries.

### 8.5. Wrong or Incompatible Patterns

Date/time patterns follow Spring/JDK formatting rules. Do not confuse `MM` (month) with `mm` (minute), or `yyyy` with other year symbols in `DateTimeFormatter`. Test leap years, nonexistent dates, time zones, empty values, and invalid formats.

### 8.6. Formatting Annotations Are Not Validators

`@DateTimeFormat(pattern = "dd/MM/yyyy")` assists with pattern-based parsing/printing, not confirming a date falls within a business range. `@NumberFormat` does not enforce min/max bounds. Use Bean Validation or dedicated business validators.

## 9. Common Mistakes

1. **Using TypeDescriptor.valueOf(...) and expecting field annotations to apply.** That descriptor carries no field metadata; create it from `Field` or `MethodParameter`.
2. **Treating the annotation as a converter.** Annotations declare metadata; `FormattingConversionService` and formatter factories actually read it.
3. **Using @DateTimeFormat to control Jackson JSON.** JSON is normally handled by `HttpMessageConverter`/Jackson; configure JSON mapping separately.
4. **Enabling style formats and expecting identical behavior across Locales/JDKs.** Style depends on runtime/Locale; use ISO or fixed patterns for stable contracts.
5. **Using loose date patterns or mixing up symbols.** Check `MM`/`mm`, leap days, and invalid formats.
6. **Not specifying Locale for numbers.** Strings with commas/dots can carry different meanings across Locales.
7. **Applying an annotation formatter factory to unsupported types.** `getFieldTypes()` must declare matching types; the factory must return compatible parsers/printers.
8. **Assuming canConvert guarantees valid values.** Concrete values must still be parsed; handle `ConversionException`.
9. **Using formatters for business validation.** Conversion and validation must stay separated.
10. **Registering a formatter without MVC using that service.** Verify the application's actual `FormatterRegistry`/`WebMvcConfigurer`.

## 10. Testing Checklist

| Test Case | Expected |
| --- | --- |
| LocalDate field with ISO.DATE, input 2024-02-29 | Parses successfully |
| LocalDate field with pattern dd/MM/yyyy, input 29/02/2024 | Parses successfully |
| Same pattern field, input 31/02/2024 | Conversion failure |
| Method parameter with @DateTimeFormat ISO.DATE | Uses ISO date format |
| BigDecimal field with @NumberFormat | Parses per pattern and configured Locale |
| TypeDescriptor built only from LocalDate.class | Lacks specific field annotations |
| Custom annotation formatter registered | Factory is evaluated when descriptor has annotation |
| Value parses successfully yet violates @Min/date logic | Conversion succeeds, validation fails |
| @RequestBody JSON | Verify Jackson mechanism separately |
| Query/form @ModelAttribute | Verify Spring WebDataBinder and BindingResult |

## 11. Official References

- [Spring Field Formatting – Annotation-driven Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html): Formatter, TypeDescriptor, and AnnotationFormatterFactory.
- [AnnotationFormatterFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/AnnotationFormatterFactory.html): getFieldTypes/getParser/getPrinter contract.
- [@DateTimeFormat Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/annotation/DateTimeFormat.html): field/parameter targets, ISO/pattern/style/fallback, and timezone notes.
- [@NumberFormat Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/format/annotation/NumberFormat.html): formatting Numbers by style or pattern.
- [TypeDescriptor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/convert/TypeDescriptor.html): field/parameter/generic metadata.
- [Spring MVC Type Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html): default formatters and registering formatters via WebMvcConfigurer.

**Rule to remember:** annotations on fields or method parameters participate in conversion only when their metadata is captured in `TypeDescriptor` and a formatting service with the matching factory/formatter is used. Obtain descriptors from the right context, specify Locale/formats explicitly, perform actual conversion, and check validation separately.