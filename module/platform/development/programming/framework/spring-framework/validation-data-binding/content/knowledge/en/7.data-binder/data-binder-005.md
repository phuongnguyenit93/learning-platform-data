# Registering a Local Editor or Formatter with DataBinder in Spring Framework

## 1. Why Register a Local Converter?

When data flows from a form or request parameter into a Java object, `DataBinder` must know how to turn the external representation into the property's type. A `LocalDate` field might accept the string `31/12/2026` on booking form A, while form B accepts `2026-12-31`. If the same conversion rule is applied across the entire application, a change made for form A could accidentally break form B.

**Local registration** means attaching a conversion rule to **one specific DataBinder**, and if needed only to **one specific property path**. This is the right tool when input formats are specific to a single form, model attribute, or controller, while the rest of the application keeps its general rules.

For example: `travelDate=31/12/2026` needs to become `LocalDate.of(2026, 12, 31)`. Spring can use:

- **`PropertyEditor`** (JavaBeans mechanism): you register an editor object and define how to parse text, e.g., `setAsText(...)`.
- **`Formatter<T>`** (Spring Formatting): you define `parse(String, Locale)` and `print(T, Locale)` for a specific type. The `DataBinder.addCustomFormatter(...)` API can register a formatter directly on a binder.

Both approaches serve **type conversion/formatting**. They do not decide whether data is valid under business rules, do not invoke `Validator` automatically, and do not grant permission to modify sensitive fields.

## 2. Where Editors and Formatters Sit in the Binding Flow

~~~text
HTTP form/query parameters or PropertyValues
                 |
                 v
     WebDataBinder / DataBinder
                 |
        find target property
                 |
        conversion needed?
          /             \
         v               v
  PropertyEditor    Formatter / ConversionService
       \                  /
        v                v
            Java object
                 |
          BindingResult
      (conversion errors if any)
                 |
     validation if triggered
                 |
      handle errors or proceed
~~~

With manual `DataBinder` usage:

1. Create the target object and `new DataBinder(target, "objectName")`.
2. **Register editors/formatters before binding**.
3. If needed, configure `setAllowedFields(...)`, `setConversionService(...)`, `setValidator(...)`.
4. Call `binder.bind(propertyValues)` to update properties and record conversion errors.
5. Call `binder.validate()` **only when** you need to run registered Spring `Validator` instances.
6. Read `binder.getBindingResult()` to inspect errors.

In Spring MVC, `WebDataBinder` extends this mechanism and is typically created to handle model attributes. An `@InitBinder` method lets you configure the binder **before Spring performs binding**. Both `registerCustomEditor(...)` and `addCustomFormatter(...)` are binder configuration; you do not need to call `bind()` inside `@InitBinder`.

Common point of confusion: `@RequestBody` JSON is primarily deserialized via `HttpMessageConverter` (usually Jackson). An editor registered on `WebDataBinder` **is not** the JSON converter Jackson uses when reading the request body. You must identify which mechanism processes the input before choosing how to customize it.

## 3. Registering a PropertyEditor for a Type or a Single Field

### 3.1. What Is PropertyEditor?

`java.beans.PropertyEditor` is the JavaBeans contract for converting a text-represented value into an object and back. In practice, Spring commonly uses `java.beans.PropertyEditorSupport` as a base class for implementing your own editor.

Key methods:

- `setAsText(String text)`: called to convert the input string into the target value; internally it usually calls `setValue(convertedValue)`.
- `getAsText()`: returns a string representation of the value held by the editor, useful when re-rendering a form.
- `getValue()`, `setValue(...)`: holds the current value of an **editor instance**.

Example editor converting a `dd/MM/uuuu` date string to `LocalDate` with strict parsing:

~~~java
import java.beans.PropertyEditorSupport;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;

public final class DayMonthYearEditor extends PropertyEditorSupport {
    private static final DateTimeFormatter FORMAT =
            DateTimeFormatter.ofPattern("dd/MM/uuuu")
                    .withResolverStyle(ResolverStyle.STRICT);

    @Override
    public void setAsText(String text) {
        setValue(LocalDate.parse(text, FORMAT));
    }

    @Override
    public String getAsText() {
        LocalDate date = (LocalDate) getValue();
        return date == null ? "" : FORMAT.format(date);
    }
}
~~~

This is a standalone Java class (requires `DayMonthYearEditor.java`) using Java 17+; the editor code itself has no Spring dependency. When encountering `31/02/2027`, `LocalDate.parse(...)` rejects the invalid calendar date. During a normal `DataBinder.bind(...)` call, Spring turns the editor's failure into a binding error on the corresponding field, readable via `BindingResult`.

**Do not blindly use `DateTimeFormatter.ofPattern("dd/MM/yyyy").withResolverStyle(STRICT)` without understanding “year-of-era”**: with strict parsing, `uuuu` is the proleptic year, which is clearer in this example. `DateTimeFormatter` is immutable and safe to share; with `SimpleDateFormat` you must be careful because it is mutable and not thread-safe.

### 3.2. Overloads of registerCustomEditor

~~~java
// Applies to matching LocalDate properties on this binder:
binder.registerCustomEditor(
        LocalDate.class, new DayMonthYearEditor());

// Applies only to the "travelDate" path on this binder:
binder.registerCustomEditor(
        LocalDate.class, "travelDate", new DayMonthYearEditor());
~~~

The two snippets above are **illustrative code**, where `binder` is a previously created `DataBinder` or `WebDataBinder`; the complete runnable code is in section 6.

| Registration | Effect | When to Use |
| --- | --- | --- |
| `registerCustomEditor(LocalDate.class, editor)` | Type-based editor in the **current binder**, used for matching fields | All date fields on that form follow the same pattern |
| `registerCustomEditor(LocalDate.class, "travelDate", editor)` | Editor only for the `travelDate` path on the **current binder** | One field has a distinct input format |
| `registerCustomEditor(String.class, "externalCode", editor)` | Customizes text handling for the named field | Field-specific text rule without altering all `String` fields |

The property path must match the **Java property name**, not the UI display label. For nested objects, it can be `customer.birthDate`; for collections, the path can include an index like `items[0].deliveryDate` depending on the structure and binder settings. The name `travelDate` does not automatically apply to another field simply because it shares the same type.

If you register a type-based editor for `LocalDate.class` and the form has both `travelDate` and `cancelDate`, both can use the same rule. If only one field accepts `dd/MM/uuuu`, choose the variant **with a property path**.

### 3.3. Lifecycle and Thread Safety

`PropertyEditorSupport` stores state through `setValue(...)`. You should not share **the same mutable editor instance** across multiple requests or threads. In `@InitBinder`, create a new editor when configuring the binder for that request:

~~~java
@InitBinder("travelForm")
void initialize(WebDataBinder binder) {
    binder.registerCustomEditor(
            LocalDate.class, "travelDate", new DayMonthYearEditor());
}
~~~

This snippet belongs inside a Spring MVC controller, not a standalone application. Spring creates the binder for the binding context; creating a fresh editor matches that lifecycle. **Never declare a mutable editor as a singleton and use it directly across all requests**.

When multiple controllers need the same logic, you can package the registration code into a `PropertyEditorRegistrar` and call `registrar.registerCustomEditors(binder)` in the relevant `@InitBinder` methods. The registrar should instantiate new editors on each registration call; code reuse is in *how registration is done*, not in sharing a single mutable editor.

## 4. Registering a Local Formatter<T>

### 4.1. Formatter Separates parse and print

`org.springframework.format.Formatter<T>` is an interface combining `Parser<T>` and `Printer<T>`:

~~~java
public interface Formatter<T> {
    String print(T object, Locale locale);
    T parse(String text, Locale locale) throws ParseException;
}
~~~

This is a **simplified conceptual description** of the two methods a `Formatter<T>` class must implement; in the Spring API, `Formatter<T>` extends `Printer<T>` and `Parser<T>`.

- `parse(...)`: converts user-supplied text into type `T`.
- `print(...)`: converts a value of type `T` into a display string.
- `Locale`: enables formatting dates, currency, or numbers by region. Request locale selection and formatting rules should be clearly defined to avoid swapped day/month errors.

Example formatter for `LocalDate` using the pattern `dd.MM.uuuu`:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;
import org.springframework.format.Formatter;

public final class DotDateFormatter implements Formatter<LocalDate> {

    private DateTimeFormatter format(Locale locale) {
        return DateTimeFormatter.ofPattern("dd.MM.uuuu", locale)
                .withResolverStyle(ResolverStyle.STRICT);
    }

    @Override
    public LocalDate parse(String text, Locale locale) {
        return LocalDate.parse(text, format(locale));
    }

    @Override
    public String print(LocalDate value, Locale locale) {
        return format(locale).format(value);
    }
}
~~~

Both methods are strongly typed, making them easy to reuse and test. `DotDateFormatter` holds no current value or per-request variables, so this design can be safely reused; locale data is passed into each call. In real projects, consider how formatting applies to both parsing and printing, blank fields, and validation rules.

### 4.2. addCustomFormatter and Scope of Application

~~~java
// One format for all matching LocalDate properties on the binder:
binder.addCustomFormatter(new DotDateFormatter());

// Restrict the formatter to one or a few property paths:
binder.addCustomFormatter(
        new DotDateFormatter(), "travelDate");

binder.addCustomFormatter(
        new DotDateFormatter(), "travelDate", "returnDate");
~~~

`DataBinder.addCustomFormatter(...)` accepts a concrete formatter, infers the target type from `Formatter<T>`, and uses an underlying `PropertyEditor` adapter to register it in the binder's registry. This allows **using a Formatter locally without having to add it to the global registry**. `Formatter` has overloads by **field types** as well as by **field names**; when you want to restrict precisely to one property, use the overload taking `String... fields`.

Note on generic types: `class DotDateFormatter implements Formatter<LocalDate>` lets Spring recognize the `LocalDate` type. An overly generic or type-erased formatter may require the overload specifying `Class<?>... fieldTypes`.

### 4.3. When to Prefer Formatter?

| Criterion | PropertyEditor | Formatter |
| --- | --- | --- |
| API | JavaBeans `PropertyEditor`, usually extending `PropertyEditorSupport` | Spring `Formatter<T>` |
| Types | Accepts/holds `Object`, often needs casting | Generic `T` clearly specifies the type |
| Direction | `setAsText/getAsText` with instance state | `parse/print` |
| Locale | Handled manually if needed | `Locale` is a built-in parameter |
| State | `PropertyEditorSupport` is mutable | Easy to write stateless and thread-safe |
| Local use | `registerCustomEditor` | `addCustomFormatter` |
| Shared use | Possible via per-binder registrar; watch editor lifecycle | Can register in shared `FormattingConversionService` |

In modern Spring applications, **Formatter** is generally more convenient for user-facing data needing parse/print, especially numbers, dates, currency, and locales. **PropertyEditor** remains useful for integrating JavaBeans APIs, existing editors, or custom conversions already in a codebase. **Converter<S,T>** is better suited when you primarily need one-way, locale-independent type conversion.

## 5. Local by Binder, by Field, by Controller: Three Different Levels

“Local” has multiple layers of scope. Distinguishing them accurately prevents unintended side effects:

| Configuration | Typical Scope |
| --- | --- |
| `new DataBinder(target)` then `registerCustomEditor/addCustomFormatter` | Only that `DataBinder` instance |
| Overload with `"travelDate"` | Only that field/path **on the binder** |
| `@InitBinder` inside a `@Controller` | Binders initialized for that controller's binding |
| `@InitBinder("travelForm")` in a controller | Further narrowed to the `travelForm` model attribute name |
| `@InitBinder` in `@ControllerAdvice` | Can apply across multiple controllers per advice scope |
| `WebMvcConfigurer.addFormatters(FormatterRegistry)` | Shared conversion/formatting registration across Spring MVC |

The two axes — “**which context the binder belongs to**” and “**which field in the binder is customized**” — are independent. For example, `@InitBinder("travelForm")` with `addCustomFormatter(formatter, "travelDate")` means the rule is configured for the binder of model attribute `travelForm` and only for the `travelDate` field of that object.

Illustrative controller code:

~~~java
// Snippet; assumes TravelForm, DotDateFormatter, and service already exist.
@Controller
@RequestMapping("/travel")
class TravelController {

    @InitBinder("travelForm")
    void bindTravelForm(WebDataBinder binder) {
        binder.setAllowedFields("travelerName", "travelDate");
        binder.addCustomFormatter(new DotDateFormatter(), "travelDate");
    }

    @PostMapping("/booking")
    String submit(
            @Valid @ModelAttribute("travelForm") TravelForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "booking-form";
        }

        travelService.book(form);
        return "redirect:/travel/success";
    }
}
~~~

This snippet only illustrates how to write it **inside a controller**; compiling requires imports, `TravelForm`, `travelService`, view templates, and MVC configuration. `BindingResult` must appear **immediately after** the model attribute it represents. `setAllowedFields` is a separate policy to restrict properties permitted for property binding; editors/formatters do **not** act as allowlists or permission checks.

If the same application has multiple forms requiring different `LocalDate` formats, registering in each controller's `@InitBinder` or per model attribute is usually more sensible than altering global `WebMvcConfigurer.addFormatters(...)`.

## 6. Runnable Java 17+ Example: Editors and Formatters Registered per DataBinder

This example runs **without a web server** and uses `org.springframework.validation.DataBinder` directly. Two completely independent `TravelForm` instances demonstrate that registering on the first binder does not become a global setting for the second binder. An invalid-date case illustrates a type conversion error recorded in `BindingResult`.

Structure:

~~~text
local-binding-demo/
├── pom.xml
└── src/main/java/LocalBindingDemo.java
~~~

### 6.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>local-binding-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.13</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` pulls in the Spring modules needed for `DataBinder`, `Formatter`, and `BindingResult` via Maven transitive dependencies. In a real Spring Boot application, use the dependency management of the Boot version your project selects.

### 6.2. src/main/java/LocalBindingDemo.java

~~~java
import java.beans.PropertyEditorSupport;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.format.Formatter;
import org.springframework.validation.DataBinder;

public class LocalBindingDemo {

    public static final class TravelForm {
        private LocalDate travelDate;

        public LocalDate getTravelDate() {
            return travelDate;
        }

        public void setTravelDate(LocalDate travelDate) {
            this.travelDate = travelDate;
        }
    }

    public static final class SlashDateEditor
            extends PropertyEditorSupport {

        private static final DateTimeFormatter DATE_FORMAT =
                DateTimeFormatter.ofPattern("dd/MM/uuuu")
                        .withResolverStyle(ResolverStyle.STRICT);

        @Override
        public void setAsText(String text) {
            setValue(LocalDate.parse(text, DATE_FORMAT));
        }

        @Override
        public String getAsText() {
            LocalDate value = (LocalDate) getValue();
            return value == null ? "" : DATE_FORMAT.format(value);
        }
    }

    public static final class DotDateFormatter
            implements Formatter<LocalDate> {

        private DateTimeFormatter dateFormat(Locale locale) {
            return DateTimeFormatter.ofPattern("dd.MM.uuuu", locale)
                    .withResolverStyle(ResolverStyle.STRICT);
        }

        @Override
        public LocalDate parse(String text, Locale locale) {
            return LocalDate.parse(text, dateFormat(locale));
        }

        @Override
        public String print(LocalDate value, Locale locale) {
            return dateFormat(locale).format(value);
        }
    }

    private static MutablePropertyValues input(String rawDate) {
        MutablePropertyValues values = new MutablePropertyValues();
        values.add("travelDate", rawDate);
        return values;
    }

    public static void main(String[] args) {
        TravelForm editorForm = new TravelForm();
        DataBinder editorBinder = new DataBinder(editorForm, "editorForm");
        editorBinder.registerCustomEditor(
                LocalDate.class, "travelDate", new SlashDateEditor());

        editorBinder.bind(input("31/12/2026"));
        System.out.println("editor.date=" + editorForm.getTravelDate());
        System.out.println("editor.errors="
                + editorBinder.getBindingResult().hasErrors());

        TravelForm formatterForm = new TravelForm();
        DataBinder formatterBinder =
                new DataBinder(formatterForm, "formatterForm");
        DotDateFormatter formatter = new DotDateFormatter();
        formatterBinder.addCustomFormatter(formatter, "travelDate");

        LocaleContextHolder.setLocale(Locale.GERMANY);
        try {
            formatterBinder.bind(input("01.01.2027"));
            System.out.println("formatter.date="
                    + formatterForm.getTravelDate());
            System.out.println("formatter.text="
                    + formatter.print(
                            formatterForm.getTravelDate(),
                            Locale.GERMANY));
            System.out.println("formatter.errors="
                    + formatterBinder.getBindingResult().hasErrors());

            TravelForm invalidForm = new TravelForm();
            DataBinder invalidBinder =
                    new DataBinder(invalidForm, "invalidForm");
            invalidBinder.addCustomFormatter(
                    new DotDateFormatter(), "travelDate");
            invalidBinder.bind(input("31.02.2027"));

            System.out.println("invalid.date="
                    + invalidForm.getTravelDate());
            System.out.println("invalid.fieldError="
                    + invalidBinder.getBindingResult()
                            .hasFieldErrors("travelDate"));
        } finally {
            LocaleContextHolder.resetLocaleContext();
        }
    }
}
~~~

Run from the directory containing `pom.xml` with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=LocalBindingDemo
~~~

Program `System.out` output (excluding Maven environment logs):

~~~text
editor.date=2026-12-31
editor.errors=false
formatter.date=2027-01-01
formatter.text=01.01.2027
formatter.errors=false
invalid.date=null
invalid.fieldError=true
~~~

**Why does it produce this output?**

1. `editorBinder` has a field-specific editor on `travelDate` that accepts `31/12/2026` and converts it to `LocalDate` at the end of 2026. `LocalDate.toString()` outputs ISO `2026-12-31`. There are no binding errors.
2. `formatterBinder` is a **different instance**. It receives its own dot-separated formatter `01.01.2027` and parses it into the first day of 2027. Calling `formatter.print(...)` formats the value back to `01.01.2027`.
3. `invalidBinder` receives `31.02.2027`. February 31 does not exist; the formatter throws a parse error, and binding records an error on the `travelDate` field. The property remains `null`, and `hasFieldErrors("travelDate")` returns `true`.
4. `LocaleContextHolder` is set to `Locale.GERMANY` to establish an explicit locale in an example without a request. In Spring MVC, `LocaleResolver` and request context normally determine the locale used by formatters. When setting locale manually in a standalone execution flow, use `try/finally` to avoid leaking locale context.
5. Formatter/editor registration occurs **only on each individual binder**, without touching global conversion settings. Reusing the `DotDateFormatter` class does not automatically make other binders aware of it.

In production applications, test blank inputs, invalid dates, different locales, leap days, and time zones if converting to `Instant` or `ZonedDateTime`; `LocalDate` **carries no time zone**.

## 7. Local Registration in Spring MVC: Practical Flow

When handling a form, Spring MVC typically follows this sequence:

~~~text
Create/retrieve model attribute "travelForm"
                 |
       create WebDataBinder
                 |
  invoke matching @InitBinder in controller
       /                 \
   addCustomFormatter   registerCustomEditor
       \                 /
          bind field
                 |
       record errors in BindingResult
                 |
  @Valid/@Validated if enabled
                 |
     controller receives form + BindingResult
~~~

Condensed example for a form:

~~~java
@Controller
class BookingController {

    @InitBinder("travelForm")
    void configure(WebDataBinder binder) {
        binder.addCustomFormatter(
                new DotDateFormatter(), "travelDate");
    }

    @PostMapping("/book")
    String create(
            @Valid @ModelAttribute("travelForm") TravelForm form,
            BindingResult result) {

        if (result.hasErrors()) {
            return "booking-form";
        }

        bookingService.create(form);
        return "redirect:/book/success";
    }
}
~~~

This is an **illustrative snippet inside a controller**, not a standalone program. It assumes `TravelForm`, `DotDateFormatter`, `bookingService`, templates, and Spring MVC imports are already present.

- `@InitBinder("travelForm")` targets the binder for the model attribute named `travelForm`.
- `binder.addCustomFormatter(..., "travelDate")` changes parse/print rules only for the `travelDate` field on the configured binder.
- Failures to convert text to `LocalDate` are found via `BindingResult`.
- `@Valid` or `@Validated` triggers the appropriate validation step if the application has a corresponding validator/Bean Validation provider; registering a formatter **does not call validate automatically**.
- `bookingService` is where business logic lives. Do not let an editor call a repository or mutate domain state.

If the input is JSON `@RequestBody` with a non-standard date value, check Jackson configuration and JSON annotations like `@JsonFormat`. Do not expect a form-binding editor to alter Jackson's deserialization mechanism.

## 8. When to Use @DateTimeFormat or a Shared ConversionService?

Not every situation requires writing your own `PropertyEditor` or `Formatter`.

### 8.1. Using Annotations for Common Formats

For a date field in a model receiving form parameters, you can use:

~~~java
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;

public class TravelForm {

    @DateTimeFormat(pattern = "dd/MM/uuuu")
    private LocalDate travelDate;

    public LocalDate getTravelDate() {
        return travelDate;
    }

    public void setTravelDate(LocalDate travelDate) {
        this.travelDate = travelDate;
    }
}
~~~

This is a separate `TravelForm.java` class used in a Spring MVC context with formatting enabled. `@DateTimeFormat` is usually more concise if the requirement is simply a standard date format without complex logic. If data arrives via `@RequestBody` JSON, `@DateTimeFormat` is not Jackson's primary contract; configure JSON independently.

### 8.2. Using FormatterRegistry When the Whole Application Shares One Rule

~~~java
@Configuration
class MvcFormattingConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new DotDateFormatter());
    }
}
~~~

This snippet is an illustrative configuration needing imports for `Configuration`, `WebMvcConfigurer`, `FormatterRegistry`, and `DotDateFormatter`. It registers the formatter in MVC's shared registry, **different** from local registration in `@InitBinder`. Only use it when the desired format applies broadly and you have checked its impact on other controllers, query parameters, and forms. When multiple fields have different requirements, registering per field on the binder is more appropriate.

### 8.3. Do Not Confuse Formatter with Converter

- `Converter<String, LocalDate>` only solves converting a string into an object for a type pair; suitable when rules are locale-independent or reverse printing for forms is unnecessary.
- `Formatter<LocalDate>` covers parse, print, and locale; suitable when you need to display and re-accept user input in the same format.
- `PropertyEditorSupport` holds state and operates via the JavaBeans mechanism; prefer fresh editors per binder and mind thread safety.
- `ConversionService` centralizes shared converters/formatters. `DataBinder.setConversionService(...)` lets you configure a conversion service on a binder, which is a different choice from `addCustomFormatter(...)` registering an adapter directly on the binder.
- `@DateTimeFormat` and `@NumberFormat` integrate with Spring's formatting infrastructure on applicable fields.

Do not register multiple different formatters/editors for **the same field and same type** and assume an invariant priority order across configurations. Choose one clear source of rules, write tests for that field, and do not rely on accidental registration order.

## 9. Conversion Errors, Validation, and Error Display

An input error like `31.02.2027` does not mean the date violated a checked business rule. It failed **at type conversion**. Spring stores the corresponding `FieldError` in `BindingResult` during binding.

In a form controller:

~~~java
if (result.hasFieldErrors("travelDate")) {
    FieldError error = result.getFieldError("travelDate");
    String code = error != null ? error.getCode() : "unknown";
    // Record an appropriate UI message per application policy.
}
~~~

This snippet assumes `BindingResult result` already exists and `org.springframework.validation.FieldError` is imported. The error code may be a variant of `typeMismatch` expanded with object/field names; do not hard-code exact full code strings without checking the `MessageCodesResolver` configuration.

With manual `DataBinder`:

~~~java
binder.bind(values);                       // Convert types, record binding errors.
binder.validate();                         // Run validator if configured.
BindingResult result = binder.getBindingResult();
boolean wrongDate = result.hasFieldErrors("travelDate");
~~~

This illustrative snippet assumes `binder` and `values` already exist. If no validator was added, `validate()` has no business validation rules to apply. A `Formatter` does not replace Bean Validation or a Spring `Validator`. Account for the case where a validator inspects a field that remained `null` due to a conversion error so you avoid reporting duplicate errors for the same root cause.

For UI forms, Spring can use editors/formatters to re-print converted values; however, rejected input values can be retained in `BindingResult` so users see what they entered. Do not assume every `FieldError.getRejectedValue()` is safe to log or render directly into HTML without escaping.

## 10. Pitfalls to Avoid with Local Registration

1. **Registering after `bind(...)`.** At that point data conversion has already occurred; register before the binding step.
2. **Confusing the target type.** Spring's `CustomDateEditor` is for `java.util.Date`, not `java.time.LocalDate`. For Java Time, use an appropriate Formatter/Converter, `@DateTimeFormat`, or a custom editor targeting the right type.
3. **Using a mutable editor as a singleton.** `PropertyEditorSupport` holds a value; create a new editor instance per binder and never share across requests.
4. **Omitting the field path when only one field needs it.** A type-based overload affects all properties of that type on the binder.
5. **Confusing field name with display label.** The name in `registerCustomEditor(..., "travelDate", ...)` is the property path on the Java object.
6. **Changing global rules to solve an isolated case.** `WebMvcConfigurer.addFormatters` has broad impact; use `@InitBinder` or a dedicated DataBinder when local scope is intended.
7. **Assuming editors handle all JSON.** `@RequestBody` is typically deserialized by Jackson; WebDataBinder configuration does not change JSON parsing into models.
8. **Failing to handle blank inputs or invalid formats.** Clearly decide whether an empty string becomes `null` or an error, and combine with `@NotNull` when a value is required.
9. **Accepting nonexistent dates.** Use strict parsers (`ResolverStyle.STRICT` or `SimpleDateFormat.setLenient(false)`); test leap days.
10. **Confusing conversion with business rules.** Editors/formatters only construct Java values; conditions like “departure date must be after today” belong to validation or domain logic.
11. **Ignoring Locale.** A formatter using a comma as a decimal separator in one region differs from a dot in another; machine-submitted forms should use a consistent format.
12. **Forgetting to restrict bound properties.** Editors/formatters are not access control. Prefer DTOs and restrict property-bindable fields when needed.
13. **Not testing local scope.** Test both the customized form and other forms to ensure special formatting does not leak elsewhere.
14. **Using formatters that hold mutable request data.** Shared formatters should be stateless/thread-safe; pass context such as locale via parameters or the appropriate Spring context.

## 11. Comprehension Exercises

1. There are two fields `travelDate` and `birthday` of type `LocalDate`. Only `travelDate` accepts `dd.MM.uuuu`. Which `registerCustomEditor`/`addCustomFormatter` overload should you use?
2. Why should an editor extending `PropertyEditorSupport` not be a singleton bean shared across all requests?
3. Does `@InitBinder("travelForm")` affect every controller? How is the scope by model attribute name determined?
4. If an API uses `@RequestBody` JSON, does registering an editor in `@InitBinder` change how Jackson parses `LocalDate`?
5. When `travelDate=31.02.2027`, does the error occur during binding or in the business validator? What information should you read from `BindingResult`?
6. When every controller must format currency by locale in the same way, should you consider per-controller `@InitBinder` or a shared `FormatterRegistry`?
7. When you need to block the `admin` field from requests, is a `Formatter` sufficient? What must enforce data modification permissions?

Try changing `01.01.2027` to `01/01/2027` on the binder with `DotDateFormatter` to observe the error, then switch to `SlashDateEditor` **on that exact same binder** and explain why the outcome changes. You will clearly see **“whichever binder receives the registration is the one affected”** and **“only the selected field receives the local rule”**.

## References

- Spring Framework 6.2 — `@InitBinder` in Spring MVC: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework — Data Binding and PropertyEditor: https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html
- Spring Framework — Field Formatting / Formatter SPI: https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring Framework 6.2 — MVC Type Conversion: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/conversion.html
- `DataBinder` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.2.13 release: https://spring.io/blog/2025/11/13/spring-framework-6-2-13-available-now
