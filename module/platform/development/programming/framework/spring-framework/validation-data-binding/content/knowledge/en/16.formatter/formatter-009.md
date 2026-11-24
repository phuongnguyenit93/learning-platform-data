# FormatterRegistrar and Shared Formatting Rule Groups in Spring Framework

## 1. Problem and Role of FormatterRegistrar

In a Spring application, multiple controllers, forms, and `DataBinder` instances may need the same parse/print rules. For example, a sales module might have:

- `OrderCode`: order code, format `ORD-0001`.
- `InvoiceReference`: invoice code, format `INV-0001`.
- `DepartmentCode`: department code, format `DPT-SAL`.

If each controller creates its own formatter or converter, rules are easily duplicated, diverge across screens, and become hard to maintain when changes happen. Spring provides `FormatterRegistrar` to **register a group of related converters and formatters into a single `FormatterRegistry`**.

The interface belongs to `org.springframework.format`:

```java
public interface FormatterRegistrar {
    void registerFormatters(FormatterRegistry registry);
}
```

Meaning of the contract:

- An implementation gathers related rules for a domain group or a family of data types.
- `registerFormatters(...)` receives a registry supplied by Spring configuration.
- The registrar registers `Formatter`, `Printer`, `Parser`, or `Converter` instances through the registry.
- A registrar does not parse data directly and does not replace `Formatter` or `Converter`.
- Implementing `FormatterRegistrar` **does not automatically make Spring discover and run the registrar**. The application must invoke it in a configuration hook or declare it with the corresponding `FormattingConversionService` setup.

You can visualize it as:

```text
Application configuration
        |
        v
BillingFormatterRegistrar
        |
        +--> OrderCodeFormatter
        |
        +--> InvoiceReferenceFormatter
        |
        +--> StringToDepartmentCode
        |
        v
FormatterRegistry
        |
        v
FormattingConversionService
        |
        +--> DataBinder / Spring MVC
        +--> ConversionService callers
```

**`FormatterRegistrar` is the point for organizing and registering rules.** The registry manages the rules; `FormattingConversionService` executes conversion/formatting at runtime.

## 2. Related Interfaces and Classes

| Component | Role | Representative API |
| --- | --- | --- |
| `Formatter<T>` | Parse `String` to `T` and print `T` to `String` by `Locale` | `parse(text, locale)`, `print(object, locale)` |
| `Printer<T>` | Print object into a string | `print(object, locale)` |
| `Parser<T>` | Parse string into an object | `parse(text, locale)` |
| `Converter<S,T>` | Directed conversion for a pair of types | `convert(source)` |
| `ConverterRegistry` | Register converters | `addConverter(...)` |
| `FormatterRegistry` | Register formatters, printers/parsers, and converters | `addFormatter(...)`, `addParser(...)`, `addConverter(...)` |
| `FormatterRegistrar` | Group related registration calls | `registerFormatters(registry)` |
| `FormattingConversionService` | Registry and service used to parse/print/convert | `addFormatter(...)`, `convert(...)` |
| `DefaultFormattingConversionService` | Common implementation with default formatting rules | instantiate then add custom rules |

Key relationship: **`FormatterRegistry` extends `ConverterRegistry`**. Thus, a registrar can register both formatters and converters through the same `FormatterRegistry` parameter.

A registrar is not a new registry, not a separate `ConversionService`, and not a formatter itself. It is an adapter/configuration object for grouping registration statements.

### 2.1. Why not register directly in each controller?

Centralized registration helps:

- Use a uniform format across multiple controllers and forms.
- Group formatters by domain, such as billing, inventory, or customer.
- Reuse one configuration for MVC or a standalone `FormattingConversionService`.
- Test the registered rule set easily.
- Prevent one controller from creating a formatter that differs from another controller's.

`FormatterRegistrar` fits when there are **multiple related rules** or when registering a `Printer`/`Parser` for a specific field type. If there is only a single simple formatter, calling `registry.addFormatter(...)` directly in configuration is completely valid.

## 3. What Kinds of Rules Does FormatterRegistry Accept?

`FormatterRegistry` provides these API groups:

| API | Purpose |
| --- | --- |
| `addFormatter(formatter)` | Register a `Formatter` for type `T` declared via generics |
| `addFormatterForFieldType(fieldType, formatter)` | Register a formatter for a specified field type |
| `addFormatterForFieldType(fieldType, printer, parser)` | Register a `Printer`/`Parser` pair |
| `addFormatterForFieldAnnotation(factory)` | Register a formatter driven by a field annotation |
| `addPrinter(printer)` | Register the print direction |
| `addParser(parser)` | Register the parse direction |
| `addConverter(converter)` | Register a `Converter` |
| `addConverterFactory(factory)` | Register a `ConverterFactory` |
| `addGenericConverter(converter)` | Register a `GenericConverter` |

API selection depends on the contract:

- `Formatter` has both parse and print.
- `Printer`/`Parser` provide one direction; they can be registered as a pair.
- Field-type formatters apply to a specific field type.
- `AnnotationFormatterFactory` ties formatting to annotations like `@DateTimeFormat` or custom domain annotations.
- Converters can be registered because `FormatterRegistry` extends `ConverterRegistry`.

### 3.1. addFormatter and addFormatterForFieldType

`addFormatter(formatter)` infers type `T` from the generic parameter of `Formatter<T>`. This is convenient when the formatter clearly declares its type:

```java
registry.addFormatter(new OrderCodeFormatter());
```

`addFormatterForFieldType` allows specifying the field type explicitly:

```java
registry.addFormatterForFieldType(
        OrderCode.class, new OrderCodeFormatter());
```

The second approach is useful when registering a formatter under a specific field type, such as when the field type is an interface/base type distinct from the generic type declared on `Printer`/`Formatter`. The registry may perform coercion when declared and field types do not match directly; confirm the exact type relationship and test the intended behavior.

### 3.2. Registering annotation formatters

If formatting is decided by an annotation on each field rather than a global rule for the whole type, implement `AnnotationFormatterFactory<A>` and register it:

```java
registry.addFormatterForFieldAnnotation(
        new ReferenceFormatAnnotationFormatterFactory());
```

This is an illustrative snippet; the factory must implement `getFieldTypes()`, `getPrinter(annotation, fieldType)`, and `getParser(annotation, fieldType)`. Supported field types and the annotation must be clearly defined. `FormatterRegistrar` is often where one or more such factories are bundled with other formatters/converters.

## 4. A Registrar Registering Multiple Related Rules

For example, the Billing module needs two formatters and one converter:

| Type | Rule | Direction |
| --- | --- | --- |
| `OrderCode` | `ORD-` plus four digits | `String ↔ OrderCode` |
| `InvoiceReference` | `INV-` plus four digits | `String ↔ InvoiceReference` |
| `DepartmentCode` | `DPT-` plus three letters | `String → DepartmentCode` |

The two formatters handle parse/print. The `DepartmentCode` converter only needs to convert input strings into the value object; do not assume it provides a reverse print direction.

The registrar bundles the three rules:

```java
public final class BillingFormatterRegistrar
        implements FormatterRegistrar {

    @Override
    public void registerFormatters(FormatterRegistry registry) {
        registry.addFormatterForFieldType(
                OrderCode.class, new OrderCodeFormatter());
        registry.addFormatterForFieldType(
                InvoiceReference.class,
                new InvoiceReferenceFormatter());
        registry.addConverter(new StringToDepartmentCode());
    }
}
```

This is a snippet; the formatter/value-object/converter classes are defined in the full example section. When billing rules expand, add related registrations inside the registrar instead of repeating them across controllers.

**Do not turn one registrar into a dumping ground for unrelated formats.** Split into `DateTimeFormatterRegistrar`, `BillingFormatterRegistrar`, and `CustomerFormatterRegistrar` so each group has a clear scope of responsibility.

## 5. Complete Example with Java 17 and Spring Framework 6.2.6

The example below runs standalone without Spring Boot, a web server, or a database. It creates a `DefaultFormattingConversionService`, invokes the registrar, and performs parse/print.

### 5.1. Project structure

```text
formatter-registrar-demo/
├── pom.xml
└── src/main/java/demo/FormatterRegistrarDemo.java
```

### 5.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>formatter-registrar-demo</artifactId>
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
                    <mainClass>demo.FormatterRegistrarDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` provides the formatting/conversion infrastructure along with transitive Spring modules. The example uses only Java 17 and Spring; no test framework is used.

### 5.3. Complete source code

File `src/main/java/demo/FormatterRegistrarDemo.java`:

```java
package demo;

import java.text.ParseException;
import java.util.Locale;
import java.util.Set;

import org.springframework.core.convert.converter.Converter;
import org.springframework.format.Formatter;
import org.springframework.format.FormatterRegistrar;
import org.springframework.format.FormatterRegistry;
import org.springframework.format.support.DefaultFormattingConversionService;

public final class FormatterRegistrarDemo {

    public record OrderCode(String value) {
        public OrderCode {
            if (value == null || !value.matches("ORD-[0-9]{4}")) {
                throw new IllegalArgumentException("Invalid order code");
            }
        }

        @Override
        public String toString() {
            return value;
        }
    }

    public record InvoiceReference(String value) {
        public InvoiceReference {
            if (value == null || !value.matches("INV-[0-9]{4}")) {
                throw new IllegalArgumentException("Invalid invoice reference");
            }
        }

        @Override
        public String toString() {
            return value;
        }
    }

    public record DepartmentCode(String value) {
        public DepartmentCode {
            if (value == null || !value.matches("DPT-[A-Z]{3}")) {
                throw new IllegalArgumentException("Invalid department code");
            }
        }

        @Override
        public String toString() {
            return value;
        }
    }

    public static final class OrderCodeFormatter
            implements Formatter<OrderCode> {

        @Override
        public OrderCode parse(String text, Locale locale)
                throws ParseException {
            String normalized = text == null
                    ? ""
                    : text.trim().toUpperCase(Locale.ROOT);

            if (!normalized.matches("ORD-[0-9]{4}")) {
                throw new ParseException("Expected ORD- followed by 4 digits", 0);
            }
            return new OrderCode(normalized);
        }

        @Override
        public String print(OrderCode object, Locale locale) {
            return object.value();
        }
    }

    public static final class InvoiceReferenceFormatter
            implements Formatter<InvoiceReference> {

        @Override
        public InvoiceReference parse(String text, Locale locale)
                throws ParseException {
            String normalized = text == null
                    ? ""
                    : text.trim().toUpperCase(Locale.ROOT);

            if (!normalized.matches("INV-[0-9]{4}")) {
                throw new ParseException("Expected INV- followed by 4 digits", 0);
            }
            return new InvoiceReference(normalized);
        }

        @Override
        public String print(InvoiceReference object, Locale locale) {
            return object.value();
        }
    }

    public static final class StringToDepartmentCode
            implements Converter<String, DepartmentCode> {

        @Override
        public DepartmentCode convert(String source) {
            if (source == null) {
                throw new IllegalArgumentException("Department code is required");
            }

            String normalized = source.trim().toUpperCase(Locale.ROOT);
            return new DepartmentCode(normalized);
        }
    }

    public static final class BillingFormatterRegistrar
            implements FormatterRegistrar {

        @Override
        public void registerFormatters(FormatterRegistry registry) {
            registry.addFormatterForFieldType(
                    OrderCode.class, new OrderCodeFormatter());
            registry.addFormatterForFieldType(
                    InvoiceReference.class,
                    new InvoiceReferenceFormatter());
            registry.addConverter(new StringToDepartmentCode());
        }
    }

    public static void main(String[] args) {
        DefaultFormattingConversionService service =
                new DefaultFormattingConversionService();

        new BillingFormatterRegistrar().registerFormatters(service);

        OrderCode order = service.convert(
                " ord-0042 ", OrderCode.class);
        InvoiceReference invoice = service.convert(
                " inv-0098 ", InvoiceReference.class);
        DepartmentCode department = service.convert(
                " dpt-sal ", DepartmentCode.class);

        String printedOrder = service.convert(order, String.class);
        String printedInvoice = service.convert(invoice, String.class);

        System.out.println("order=" + order);
        System.out.println("order.print=" + printedOrder);
        System.out.println("invoice=" + invoice);
        System.out.println("invoice.print=" + printedInvoice);
        System.out.println("department=" + department);
    }
}
```

Key points to note:

1. Each record guards its value object's format via constructor invariants.
2. Formatters implement both parse and print, receiving `Locale` even though these technical codes are locale-independent.
3. `Converter<String, DepartmentCode>` handles only `String → DepartmentCode`.
4. `BillingFormatterRegistrar` receives `FormatterRegistry` and registers three rules.
5. `DefaultFormattingConversionService` has both default converters/formatters and acts as the registry; the example invokes the registrar directly so the registration moment is obvious.
6. Classes are nested in one file to keep the Maven example compact; in real applications, they can be split into separate files/domain packages.

### 5.4. Running and stdout

In the `formatter-registrar-demo` directory, with JDK 17+ and Maven:

```bash
mvn -q clean compile exec:java
```

Stdout printed by the program:

```text
order=ORD-0042
order.print=ORD-0042
invoice=INV-0098
invoice.print=INV-0098
department=DPT-SAL
```

Explanation:

- The formatters are bound by the registry to `OrderCode` and `InvoiceReference`; `String` can be parsed into objects and objects can be printed into `String`.
- The `DepartmentCode` converter only creates objects when reading strings; the example does not test `DepartmentCode → String` with that converter.
- Output order follows the `println` statements, not the order in which the registry stores formatters.
- `Locale` is still passed into `Formatter`, while technical code formatting is fixed using `Locale.ROOT` so it does not vary by user machine.

If you change the inputs to `ord-XX42` or `inv-9`, the corresponding converter/formatter rejects them. `canConvert` tells you a type conversion path exists, not that every individual value's content is valid.

## 6. Registering a Registrar in Spring MVC

In Spring MVC, `WebMvcConfigurer` provides the `addFormatters(FormatterRegistry)` extension point. This is where registrars are typically called so all controllers share the MVC registry.

```java
@Configuration
public class WebFormattingConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        new BillingFormatterRegistrar().registerFormatters(registry);
    }
}
```

This snippet requires importing `Configuration`, `WebMvcConfigurer`, and `FormatterRegistry`; `BillingFormatterRegistrar` is the implementation from the previous section. In typical Spring Boot MVC apps, declare a `WebMvcConfigurer` bean and do not enable `@EnableWebMvc` unless intentionally replacing Boot's MVC auto-configuration.

Once registered, the types can be used in:
- Query parameters and path variables bound to controller parameters.
- Form objects received via `@ModelAttribute`.
- `WebDataBinder` in contexts using MVC's `FormattingConversionService`.

Controller example (illustrative snippet):

```java
@GetMapping("/orders/{code}")
public String order(@PathVariable OrderCode code) {
    return "Order code: " + code;
}

@PostMapping("/invoices")
public String createInvoice(
        @Valid @ModelAttribute("form") InvoiceForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "invoices/form";
    }
    return "redirect:/invoices/success";
}
```

`InvoiceForm` must have a property/constructor accepting `InvoiceReference` along with matching imports/validation. Binding succeeds only when field names and conversion paths align. `BindingResult` is placed immediately after the form so the controller can handle errors.

**Do not infer that registering a `FormatterRegistrar` in MVC automatically configures every JSON body.** `@RequestBody` JSON is normally decoded by `HttpMessageConverter`/Jackson with its own configuration. If JSON contains a string code that must map to a value object, check Jackson deserializer/constructor configuration or an appropriate JSON adapter.

## 7. Using FormatterRegistrar with XML Configuration

Spring provides `FormattingConversionServiceFactoryBean` to create a formatting conversion service in XML configuration. The factory bean supports sets of formatters, converters, and formatter registrars.

Configuration example (illustrative XML snippet, assuming `BillingFormatterRegistrar` has a default constructor):

```xml
<bean id="conversionService"
      class="org.springframework.format.support.FormattingConversionServiceFactoryBean">
    <property name="formatterRegistrars">
        <set>
            <bean class="demo.BillingFormatterRegistrar"/>
        </set>
    </property>
</bean>
```

In the MVC XML namespace, you can wire this service into annotation-driven configuration via the `conversion-service` attribute. Bean names and packages must match actual classes. Do not declare multiple competing conversion services simultaneously without clarity on which subsystem uses which bean.

With Java configuration, `WebMvcConfigurer.addFormatters` is generally clearer and cleaner for modern MVC applications. The XML factory bean remains useful in XML-configured applications or when building a dedicated `FormattingConversionService` to inject into `DataBinder`/SpEL or another subsystem.

## 8. Date/Time Rule Groups: DateTimeFormatterRegistrar

Spring includes a built-in registrar for Java Time: `org.springframework.format.datetime.standard.DateTimeFormatterRegistrar`. It configures formatters and converters for `LocalDate`, `LocalTime`, `LocalDateTime`, `ZonedDateTime`, and other supported temporal types.

Example using global ISO format in MVC:

```java
@Configuration
public class DateTimeWebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        DateTimeFormatterRegistrar registrar =
                new DateTimeFormatterRegistrar();
        registrar.setUseIsoFormat(true);
        registrar.registerFormatters(registry);
    }
}
```

The `setUseIsoFormat(true)` API instructs the registrar to register corresponding ISO formats instead of default styles. Additionally, the registrar allows configuring individual `DateFormatter`, `TimeFormatter`, `DateTimeFormatter`, or `FormatStyle` per group. If a specific `DateTimeFormatter` is set, style/ISO settings for that type may be overridden/ignored per the registrar's setter contract.

Another registrar is `DateFormatterRegistrar` in `org.springframework.format.datetime`, primarily supporting `java.util.Date`, `Calendar`, and `long` in legacy contexts. It registers `DateFormatter` and required date converters. For new code using `java.time`, `DateTimeFormatterRegistrar` is normally preferred.

### 8.1. Why do date/time types need a dedicated registration group?

Date/time handling involves multiple types and policies:
- `LocalDate` has only a date, no time zone.
- `LocalDateTime` has date and time but no offset/zone.
- `OffsetDateTime` has a UTC offset.
- `ZonedDateTime` carries a time zone.
- `Instant` represents a point on the UTC timeline.

A registrar can configure a consistent group of rules rather than letting each controller invent formatters. However, choose formats to match the communication contract: HTML date/time inputs submit fixed browser-standard formats; text inputs may be influenced by locale/request. ISO formats generally fit machine-readable representations, while localized styles suit user-facing forms when explicitly defined.

## 9. FormatterRegistrar and AnnotationFormatterFactory

These two SPIs have distinct responsibilities and can often be used together:

| Component | Triggered By | Role |
| --- | --- | --- |
| `FormatterRegistrar` | Configuration registration step | Bundle multiple rules and register them into `FormatterRegistry` |
| `AnnotationFormatterFactory` | Annotation on field/parameter | Create `Printer`/`Parser` from annotation metadata |
| `Formatter<T>` | Registered type `T` and formatter | Parse/print values |
| `FormatterRegistry` | Registered type/annotation/Converter pair | Look up and manage rules |

For example, an application has `@MoneyFormat(currency="VND")` on a `BigDecimal` field. An `AnnotationFormatterFactory` can supply a parser/printer based on the `currency` attribute. `BillingFormatterRegistrar` can register that factory alongside `OrderCode` formatter and `DepartmentCode` converter.

Thus, the registrar organizes the group of rules, while the factory resolves the specific formatter from the annotation. There is no need to create an annotation formatter factory if a single fixed rule applies to all fields of a type.

## 10. Multiple Registrars and Registration Conflicts

A system may have several groups:

```text
WebMvcConfigurer.addFormatters(registry)
        |
        +--> DateTimeFormatterRegistrar
        |
        +--> BillingFormatterRegistrar
        |
        +--> CustomerFormatterRegistrar
        |
        +--> Annotation Formatter Factories
        |
        +--> Custom Converters
```

Each registrar should have a clear scope. Several guidelines:

- Do not register two competing formatters for the same field type unless an explicit override is intended.
- Be careful when registering a single `Formatter` via both generic inference and `addFormatterForFieldType` under different types.
- `Converter` and `Formatter` can both create a `String → T` path; avoid leaving two rules for the same pair with differing parse logic without tests.
- For annotation-driven formatters, clearly define priority annotations and the field types each factory supports.
- Register at configuration/startup time; never add or remove rules per request.
- Never share mutable state inside a `Formatter`/`Converter` when multiple requests run concurrently.

The invocation order of registrars can affect how a registry handles overlapping rules. Do not depend on order implicitly; design to avoid conflicts and test lookup outcomes.

## 11. When to Use a Registrar and When to Call the Registry Directly?

| Scenario | Appropriate Approach |
| --- | --- |
| Only one simple formatter | Call `registry.addFormatter(...)` directly |
| Multiple formatters in the same domain group | Create a `FormatterRegistrar` |
| Formatters for multiple date/time types | Use `DateTimeFormatterRegistrar` or a dedicated registrar |
| Need to group both converters and formatters | `FormatterRegistrar`, because the registry is also a `ConverterRegistry` |
| Need annotation-driven formatters | `AnnotationFormatterFactory`, registered via registry/registrar |
| Need very narrow rules for one controller | Binder/controller configuration when suitable, avoiding unnecessary global scope |
| Shared across all of MVC | `WebMvcConfigurer.addFormatters(...)` calling the registrar |
| Using XML `FormattingConversionServiceFactoryBean` | Add the registrar to `formatterRegistrars` |

Having a `Formatter` does not mandate creating a `Registrar`. A registrar is valuable when it makes grouped configuration clearer, reusable, and easier to test. For a single isolated rule, adding a registrar class only introduces unnecessary indirection.

## 12. Common Errors and Diagnostics

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Formatter is not called | Registrar was not registered/invoked | Check `WebMvcConfigurer` or factory bean |
| Registry cannot find format for type | Field type or generic mismatch | Use `addFormatterForFieldType` and verify target type |
| Value parses properly but prints unexpectedly | Bidirectional formatter rules are inconsistent | Test parse/print and define a canonical representation |
| MVC works but JSON fails | JSON goes through `HttpMessageConverter`/Jackson | Configure Jackson separately |
| Dates/times shift with locale | Locale-dependent format used when client contract didn't expect it | Pick ISO/fixed format or design locale-awareness explicitly |
| Two formatters for the same type conflict | Duplicate rules or unclear override | Remove redundant rules and test the registry |
| String converter called instead of formatter | Multiple conversion paths for the same source/target | Audit Converter/Formatter pairs and registration order |
| Registrar causes side effects per request | `registerFormatters` called outside lifecycle | Register only while configuring the registry |
| Formatter is not thread-safe | Shared mutable formatter object | Use immutable/thread-safe implementations |
| Field annotation is not applied | Factory unregistered or annotation/type unsupported | Check factory, retention, and `getFieldTypes` |
| Standalone `DataBinder` ignores MVC registry | Binder constructed independently | Set the right `ConversionService` on the binder |
| `canConvert` is true yet a specific value fails | Type path exists, data is invalid | Inspect `ConversionFailedException`/`BindingResult` |

## 13. Testing the Registrar and Registered Rules

Test across three layers:

**Unit test each Formatter/Converter**
- Parse canonical input.
- Parse input with surrounding whitespace.
- Print objects into canonical strings.
- Reject invalid, empty, or wrong-prefix data.
- For locale-dependent formatters, test multiple locales.

**Integration test the registrar**
- Create a `DefaultFormattingConversionService`.
- Call `registrar.registerFormatters(service)`.
- Use `service.canConvert(...)` to verify conversion paths.
- Use `service.convert(...)` to verify parse and print.
- Verify one-way converters do not automatically gain reverse conversion.

**Integration test MVC**
- Send request parameters/path variables/forms to controllers.
- Confirm the binder uses the configured registry.
- Test `@ModelAttribute` and `BindingResult` when conversion fails.
- Test JSON `@RequestBody` separately if endpoints use Jackson.

Simple logic tests can call the service directly in `main` or JUnit. Do not merely verify that `registerFormatters` executed; verify the actual lookup outcomes in the registry that runtime code uses.

## 14. Self-Check Questions

**Question 1.** Is `FormatterRegistrar` responsible for parsing a string into an object?

No. The registrar registers formatters/converters; `Formatter` or `Converter` handles values.

**Question 2.** What parameter type does `registerFormatters` accept?

`FormatterRegistry`.

**Question 3.** Can `FormatterRegistry` register a `Converter`?

Yes. `FormatterRegistry` extends `ConverterRegistry`.

**Question 4.** When should you create a `FormatterRegistrar`?

When you want to group and reuse a set of related formatters/converters or need registration logic more complex than a single `addFormatter` call.

**Question 5.** Does implementing `FormatterRegistrar` make Spring invoke the registrar automatically?

No. You must wire the registrar into `WebMvcConfigurer`, `FormattingConversionServiceFactoryBean`, or the appropriate configuration point.

**Question 6.** What is `DateTimeFormatterRegistrar` used for?

Registering the group of formatters/converters for Java Time types and configuring ISO/style/formatters as needed.

**Question 7.** Does an MVC registrar automatically configure Jackson JSON?

Not by default. JSON requests/responses normally have their own `HttpMessageConverter`/Jackson mechanism.

## 15. Implementation Checklist

1. Group formatters/converters by a clear module or domain.
2. Define parse/print rules, `Locale` usage, and canonical representations for each type.
3. Use `Formatter` for types needing bidirectional `String ↔ T`; `Converter` for appropriate conversion rules.
4. Implement `FormatterRegistrar` and register via `FormatterRegistry`.
5. Invoke the registrar in MVC config or `FormattingConversionServiceFactoryBean`; do not just define a bean and assume it runs itself.
6. Avoid duplicate formatter/converter pairs with conflicting rules.
7. Keep formatters/converters stateless and thread-safe.
8. Test directly, through `ConversionService`/`FormattingConversionService`, and through MVC.
9. Check binding errors, empty input, locales, and nested types.
10. Configure Jackson separately if JSON needs custom formatting.

**Remember:** `FormatterRegistrar` is the place that bundles formatter and converter registrations into `FormatterRegistry`. It standardizes shared rules across forms/controllers and can register either date/time groups or domain groups. Runtime conversion is still performed by `FormattingConversionService`/`ConversionService`; each `Formatter`/`Converter` remains responsible for processing values according to its own contract.

## 16. Official Documentation

- [Spring Framework — Spring Field Formatting](https://docs.spring.io/spring-framework/reference/core/validation/format.html): `Formatter`, `FormatterRegistry`, `FormatterRegistrar`, and annotation-driven formatting.
- [Spring Framework — MVC Conversion and Formatting](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/conversion.html): registering formatters/converters via `WebMvcConfigurer` and `DateTimeFormatterRegistrar`.
- [Spring Javadoc — FormatterRegistrar 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/FormatterRegistrar.html): `registerFormatters(FormatterRegistry)` contract.
- [Spring Javadoc — FormatterRegistry 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/FormatterRegistry.html): `addFormatter`, `addParser`, `addPrinter`, `addFormatterForFieldType`, and annotations.
- [Spring Javadoc — FormattingConversionService 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/support/FormattingConversionService.html): registry/service implementation.
- [Spring Javadoc — DateTimeFormatterRegistrar 6.2.14](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/format/datetime/standard/DateTimeFormatterRegistrar.html): configuring Java Time formatters and `registerFormatters`.
