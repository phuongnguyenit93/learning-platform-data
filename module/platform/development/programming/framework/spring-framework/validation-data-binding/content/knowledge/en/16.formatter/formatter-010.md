# ParseException, IllegalArgumentException, and Binding Error Results in Spring Formatter

When a form submits a string to assign to a property with a concrete Java type, the **Formatter** must parse that string into the target value. If the string is malformed, the formatter must report a clear error. The **Parser<T>.parse(String, Locale)** contract allows two primary ways: throwing **java.text.ParseException** or **IllegalArgumentException**. When the formatter is used through Spring's `ConversionService` and `DataBinder`, the parse failure passes through the conversion layer and typically appears in **BindingResult** as a **FieldError** with code **typeMismatch**.

Keep three conceptual layers distinct:

1. **Parse error in the Formatter:** the parser cannot construct the target value from the string.
2. **Conversion error in Spring:** `ConversionService` receives the failure from the formatter and represents it as a conversion-mechanism exception.
3. **Binding error in DataBinder:** the binder records the error in `BindingResult` for the controller or view to handle.

A `ParseException` does not automatically mean HTTP 400, nor does `IllegalArgumentException` mean the request bypassed `BindingResult`. Exact behavior depends on the execution path: calling `Formatter` directly, calling `ConversionService`, binding with `DataBinder`, or resolving method arguments in Spring MVC.

## 1. The Formatter and Parser Contracts

Spring defines `Formatter<T>` combining two capabilities: **Printer<T>** to format an object into a string and **Parser<T>** to parse a string into an object.

~~~java
public interface Printer<T> {
    String print(T object, Locale locale);
}

public interface Parser<T> {
    T parse(String text, Locale locale)
            throws ParseException, IllegalArgumentException;
}

public interface Formatter<T> extends Printer<T>, Parser<T> {
}
~~~

This is an abbreviated version illustrating the contract; in the real API, the interfaces belong to package **org.springframework.format**.

- **print(...)** is used when the application needs to display an object's value according to locale.
- **parse(...)** is used when the application receives a string and needs to produce a value of type `T`.
- **Locale** enables handling dates, numbers, and currencies by language/region. For technical codes with fixed formats, locale may have no effect.
- When parsing fails, the contract allows throwing **ParseException** (commonly when using `java.text` parsing APIs) or **IllegalArgumentException** (when the value cannot be accepted by the parser's rules).

Example date value:

~~~text
Input: 2026-11-02
Output: LocalDate(2026-11-02)
~~~

If the input is **02/31/2026** while the formatter only accepts ISO `yyyy-MM-dd`, the parser cannot produce a valid `LocalDate`. This is a data error at parse time, not a bean setter error or database error.

### ParseException is a checked exception

**java.text.ParseException** extends **Exception**, making it a checked exception. A method declaring it must handle it with try/catch or declare `throws`. Because `Parser.parse(...)` already allows throwing `ParseException`, a `Formatter` implementation may declare:

~~~java
@Override
public LocalDate parse(String text, Locale locale) throws ParseException {
    // parse input or throw ParseException if format is invalid
}
~~~

This illustrates the signature, not a complete implementation.

### IllegalArgumentException is an unchecked exception

**IllegalArgumentException** extends **RuntimeException**. A parser can throw it directly when input is unsuitable:

~~~java
if (text == null || text.isBlank()) {
    throw new IllegalArgumentException("Date is required");
}
~~~

Callers do not need to declare `throws`. However, use exceptions appropriately: invalid input is an expected scenario, so the message should state the expected format or condition clearly. Never use a generic `IllegalArgumentException` to mask programming bugs unrelated to input data.

## 2. Choosing ParseException or IllegalArgumentException?

Both are valid under the `Parser` contract; the choice usually depends on the parsing library used by the formatter and how you want to represent the cause.

| Scenario | Appropriate Error Type | Why |
| --- | --- | --- |
| Using `java.text` APIs like `DateFormat.parse(...)` and parsing fails | **ParseException** | Source API already defines checked parse failure |
| Using `DateTimeFormatter`/`LocalDate.parse(...)` and catching `DateTimeParseException` | Let runtime exception propagate or wrap as **IllegalArgumentException** per parser contract | Java Time uses runtime exceptions for parse errors |
| Empty/blank value disallowed by formatter rules | **IllegalArgumentException** is often clearer | Violates an input precondition defined by the formatter |
| Input contains illegal characters or invalid syntax | **ParseException** or **IllegalArgumentException** | Depends on parsing API and implementation convention |
| Formatter configuration error, e.g. invalid pattern at initialization | Must not become a user binding error | Configuration/startup bug, should fail fast early |

There is no rule that `ParseException` is always "better" or `IllegalArgumentException` is always "worse." What matters is that the implementation honors the contract, preserves the cause for diagnostics, and never conflates data errors with configuration errors.

### Example when using Java Time

**DateTimeFormatter** is immutable and thread-safe. `LocalDate.parse(...)` can throw **DateTimeParseException**. You can wrap it into `ParseException` to keep a checked-exception style:

~~~java
try {
    return LocalDate.parse(text, DateTimeFormatter.ISO_LOCAL_DATE);
}
catch (DateTimeParseException ex) {
    ParseException failure = new ParseException(
            "Expected ISO date yyyy-MM-dd", Math.max(ex.getErrorIndex(), 0));
    failure.initCause(ex);
    throw failure;
}
~~~

You can also use `IllegalArgumentException`:

~~~java
try {
    return LocalDate.parse(text, DateTimeFormatter.ISO_LOCAL_DATE);
}
catch (DateTimeParseException ex) {
    throw new IllegalArgumentException(
            "Expected ISO date yyyy-MM-dd", ex);
}
~~~

The two snippets show two ways of representing the same parse failure. Do not throw both in the same flow; pick one convention for your formatter so callers can handle and test it consistently.

## 3. How Does Spring Turn Parse Failures into Conversion Errors?

In applications, `Formatter` is typically registered with **FormattingConversionService**. Spring uses adapters to invoke `Parser`/`Printer` through **ConversionService**. During conversion:

~~~text
Input string
     |
     v
ConversionService selects matching Formatter/Parser
     |
     v
Formatter.parse(text, locale)
     |
     +-- Success --> object of type T
     |
     +-- ParseException or IllegalArgumentException
                     |
                     v
           conversion error is propagated
           as a Spring exception
~~~

In standard conversion flows, Spring represents converter/parser failures through its conversion exception hierarchy, commonly **ConversionFailedException** wrapping the root cause. The parser adapter converts checked `ParseException` into a runtime exception to travel through `ConversionService`; `IllegalArgumentException` is likewise carried in the cause chain or wrapped according to conversion context.

Key things to remember:

- **ParseException** is an exception at the parser boundary.
- **ConversionFailedException** is a conversion failure inside `ConversionService`.
- **TypeMismatchException** can occur when `DataBinder` uses a type converter and cannot assign the value to the target property.
- Layers may nest exceptions; when logging/debugging, inspect the root cause rather than only the outermost exception class name.

Do not write code that depends on a fixed cause-chain nesting depth if the application allows swapping conversion services or formatters. Rely on exception types and the error API of the layer your code is handling.

## 4. How Does DataBinder Record Errors?

**DataBinder** applies property values to a target object. If a string cannot be converted to the target property's type, the binder does not treat it as a valid object and call the service; it records an error in **BindingResult**. Common default error codes:

| Binding Error Code | Meaning |
| --- | --- |
| **required** | Required field missing per required fields configuration |
| **typeMismatch** | Value could not be converted to the target property's type |
| **methodInvocation** | Error invoking setter/property accessor |

When a `Formatter` throws `ParseException` or `IllegalArgumentException` while converting a string to the target type, the binder typically records **typeMismatch** for that field. The controller can inspect:

~~~java
BindingResult result = binder.getBindingResult();
FieldError error = result.getFieldError("startDate");

if (error != null) {
    String code = error.getCode();
    Object rejected = error.getRejectedValue();
    boolean bindingFailure = error.isBindingFailure();
}
~~~

This snippet illustrates **org.springframework.validation.BindingResult** and **FieldError**. Important properties:

- **getCode()**: primary error code, typically `typeMismatch`.
- **getCodes()**: array of codes used by `MessageCodesResolver` to resolve messages by object/field/type.
- **getRejectedValue()**: the rejected input value, if preserved.
- **isBindingFailure()**: distinguishes conversion/binding failures from regular field validation errors.
- **getField()**: name of the offending property.

**`BindingResult` does not contain only parse failures.** It can hold `typeMismatch`, `required`, property access errors, and validation errors added afterward. Do not assume every `FieldError` originated from a `Formatter`.

### What value does the target property hold after an error?

If the target field already held a value initially, when conversion fails Spring generally does not assign a new value to that field. The previous value may remain on the object. The UI can display the rejected value from `BindingResult` and preserve what the user typed.

For example:

~~~text
Before bind: startDate = 2026-11-01
Request:     startDate = 2026-02-30
After bind:  startDate may still be 2026-11-01
BindingResult: FieldError(startDate, code=typeMismatch,
                          rejectedValue="2026-02-30")
~~~

This behavior is critical: **the target object does not reflect all user-submitted content if a field failed to bind**. Always check `BindingResult` before passing the target to a service or saving to a database. Never read the old value and assume the new request was accepted.

## 5. Complete Java 17 Example: Two Formatters, Two Exception Types, Same Binding Code

The program below uses **Spring Framework 6.2.10**, Java 17+, and Maven, requiring no Spring Boot or HTTP server. It registers two Formatters for two distinct target types:

1. **LocalDateFormatter**: uses Java Time; on parse failure, wraps `DateTimeParseException` into checked `ParseException`.
2. **ReferenceCodeFormatter**: throws `IllegalArgumentException` when input is blank or contains invalid characters.

Then `DataBinder` binds string values onto a JavaBean. One valid field is populated; two malformed fields produce `FieldError` entries with code `typeMismatch`.

Structure:

~~~text
formatter-binding-errors/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── FormatterBindingErrorsDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>formatter-binding-errors</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.10</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/FormatterBindingErrorsDemo.java**:

~~~java
package demo;

import java.text.ParseException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Locale;
import java.util.Map;

import org.springframework.format.Formatter;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

public final class FormatterBindingErrorsDemo {

    public static void main(String[] args) {
        DefaultFormattingConversionService conversions =
                new DefaultFormattingConversionService();

        conversions.addFormatter(new LocalDateFormatter());
        conversions.addFormatter(new ReferenceCodeFormatter());

        BookingForm form = new BookingForm();
        form.setStartDate(LocalDate.of(2026, 11, 1));

        DataBinder binder = new DataBinder(form, "bookingForm");
        binder.setConversionService(conversions);
        binder.setAllowedFields("startDate", "referenceCode", "endDate");

        binder.bind(new MutablePropertyValues(Map.of(
                "startDate", "2026-02-30",
                "referenceCode", "INV @ 17",
                "endDate", "2026-11-15"
        )));

        BindingResult result = binder.getBindingResult();

        printFieldResult("startDate", result, form);
        printFieldResult("referenceCode", result, form);
        printFieldResult("endDate", result, form);

        System.out.println("hasErrors = " + result.hasErrors());
        System.out.println("errorCount = " + result.getErrorCount());
    }

    private static void printFieldResult(
            String field, BindingResult result, BookingForm form) {

        FieldError error = result.getFieldError(field);
        String code = (error == null ? "none" : error.getCode());
        String rejected = (error == null
                ? "none" : String.valueOf(error.getRejectedValue()));

        System.out.println(field + ".code = " + code);
        System.out.println(field + ".rejected = " + rejected);
    }

    public static final class LocalDateFormatter
            implements Formatter<LocalDate> {

        private static final DateTimeFormatter FORMAT =
                DateTimeFormatter.ISO_LOCAL_DATE;

        @Override
        public LocalDate parse(String text, Locale locale)
                throws ParseException {

            try {
                return LocalDate.parse(text, FORMAT);
            }
            catch (DateTimeParseException ex) {
                ParseException failure = new ParseException(
                        "Expected ISO date yyyy-MM-dd",
                        Math.max(ex.getErrorIndex(), 0));
                failure.initCause(ex);
                throw failure;
            }
        }

        @Override
        public String print(LocalDate value, Locale locale) {
            return FORMAT.format(value);
        }
    }

    public record ReferenceCode(String value) {
    }

    public static final class ReferenceCodeFormatter
            implements Formatter<ReferenceCode> {

        @Override
        public ReferenceCode parse(String text, Locale locale) {
            if (text == null || text.isBlank()) {
                throw new IllegalArgumentException(
                        "Reference code must not be blank");
            }

            String normalized = text.trim().toUpperCase(Locale.ROOT);
            if (!normalized.matches("[A-Z0-9-]+")) {
                throw new IllegalArgumentException(
                        "Reference code accepts only A-Z, 0-9 and hyphen");
            }

            return new ReferenceCode(normalized);
        }

        @Override
        public String print(ReferenceCode value, Locale locale) {
            return value.value();
        }
    }

    public static final class BookingForm {
        private LocalDate startDate;
        private ReferenceCode referenceCode;
        private LocalDate endDate;

        public LocalDate getStartDate() {
            return startDate;
        }

        public void setStartDate(LocalDate startDate) {
            this.startDate = startDate;
        }

        public ReferenceCode getReferenceCode() {
            return referenceCode;
        }

        public void setReferenceCode(ReferenceCode referenceCode) {
            this.referenceCode = referenceCode;
        }

        public LocalDate getEndDate() {
            return endDate;
        }

        public void setEndDate(LocalDate endDate) {
            this.endDate = endDate;
        }
    }
}
~~~

Run in the directory containing `pom.xml` with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.FormatterBindingErrorsDemo
~~~

**Expected stdout lines from the program**:

~~~text
startDate.code = typeMismatch
startDate.rejected = 2026-02-30
referenceCode.code = typeMismatch
referenceCode.rejected = INV @ 17
endDate.code = none
endDate.rejected = none
hasErrors = true
errorCount = 2
~~~

Explanation:

- **startDate**: the string has `yyyy-MM-dd` shape, yet February 30 does not exist. `LocalDateFormatter` catches `DateTimeParseException` from Java Time and converts it into `ParseException` per the `Parser` contract. Spring's conversion adapter catches the parse failure and `DataBinder` records `typeMismatch`.
- **referenceCode**: the value contains `@` and internal spaces, failing the allowed regex. `ReferenceCodeFormatter` throws `IllegalArgumentException`; `DataBinder` likewise records `typeMismatch` for the field.
- **endDate**: valid value; the formatter builds `LocalDate`, the setter receives the value, and no `FieldError` is created.
- **startDate** held `2026-11-01` before binding. After the conversion error, the old value may remain; the rejected value is saved in `FieldError` to redisplay the invalid input.
- Two fields failed in total, so **hasErrors = true** and **errorCount = 2**.

This output demonstrates that **`ParseException` and `IllegalArgumentException` have different origins yet both can become a `typeMismatch` error during property binding**. No controller is needed to observe this; `DataBinder` alone suffices.

## 6. Why Is a Parse Failure Not Always `typeMismatch`?

Look at the exact layer making the call:

| Invocation | What You Observe |
| --- | --- |
| Calling **formatter.parse(...)** directly | `ParseException` or `IllegalArgumentException` from the implementation itself |
| Calling **conversionService.convert(...)** directly | Conversion service exception, typically **ConversionFailedException**, wrapping the parse cause inside |
| Calling **DataBinder.bind(...)** | `BindingResult` contains a `FieldError`, typically coded **typeMismatch** |
| Controller **@ModelAttribute** with `BindingResult` | Controller can inspect field errors without throwing a method-argument exception |
| Controller without a matching `BindingResult` | Spring MVC handles it via the corresponding exception/response path; the controller does not proceed by default |
| Malformed **@RequestBody JSON** | `HttpMessageConverter`/Jackson may throw **HttpMessageNotReadableException** before property-binding `Formatter`/`BindingResult` is ever invoked |

### Is the `typeMismatch` error code an exception type?

No. **typeMismatch** is an error code recorded in `FieldError`/`MessageCodesResolver`. It is a key for message lookup, not an exception class name. The cause chain may contain `ParseException`, `IllegalArgumentException`, `ConversionFailedException`, or `TypeMismatchException` depending on the API and catch site.

**FieldError.isBindingFailure()** is normally `true` for binding/conversion errors. That distinguishes them from regular validation errors added after binding, such as **@NotBlank** or **@Email**.

### Why not handle `ParseException` directly in controllers?

Controllers receive the result of binding and should not need to know which parsing library a formatter uses internally. For property binding, checking **BindingResult** and displaying field-level errors is much cleaner. When invoking `Formatter` or `ConversionService` manually inside a service, the caller can catch the exception matching that API.

## 7. Displaying Error Messages: Keep Error Codes, Never Expose Stack Traces

In Spring, `BindingResult` holds error codes; **MessageSource** can resolve codes and field context into user messages. Example **messages_vi.properties** file:

~~~properties
typeMismatch.bookingForm.startDate=Ngày bắt đầu phải theo định dạng yyyy-MM-dd và là ngày tồn tại.
typeMismatch.bookingForm.referenceCode=Mã tham chiếu chỉ được chứa chữ A-Z, số và dấu gạch nối.
typeMismatch=Giá trị nhập không đúng định dạng.
~~~

These are illustrative keys; exact codes depend on **MessageCodesResolver**, object name, field name, and property type. By default, Spring generates codes in decreasing specificity, for example:

~~~text
typeMismatch.bookingForm.startDate
typeMismatch.startDate
typeMismatch.java.time.LocalDate
typeMismatch
~~~

In a controller/view, you can render the localized message:

~~~java
String message = messageSource.getMessage(fieldError, locale);
~~~

This illustrative snippet requires **MessageSource**, **FieldError**, **Locale**, and proper bean injection. Never return raw stack traces or technical messages containing internal class names to users.

### Rejected values and data protection

Rejected values are useful for redisplaying what the user entered. However, not every value is safe to echo into HTML or logs:

- Encode output appropriately for HTML/JSON context to prevent XSS.
- Do not log sensitive data such as tokens, passwords, or unnecessary personal data.
- Bound field/input size before retaining or redisplaying rejected values.
- Do not expose raw exception messages from parsing libraries in APIs if they reveal internal structure.

A friendly message states the expected format and specific field without any stack trace.

## 8. Integrating Formatters in Spring MVC

Register shared formatters for MVC binders via **WebMvcConfigurer.addFormatters(...)**:

~~~java
@Configuration
class WebFormattingConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new FormatterBinding.LocalDateFormatter());
        registry.addFormatter(new FormatterBinding.ReferenceCodeFormatter());
    }
}
~~~

This is a configuration example in an MVC application that already defines the formatters; class names are illustrative and should be adjusted to real packages. Registering in the MVC registry ensures binders apply the same rules when converting request parameters/form strings into Java types.

A handler with **@ModelAttribute** can declare `BindingResult` immediately after the parameter:

~~~java
@PostMapping("/bookings")
String create(
        @ModelAttribute("bookingForm") BookingForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return "booking-form";
    }

    bookingService.create(form);
    return "redirect:/bookings/success";
}
~~~

This is an illustrative controller snippet; import Spring MVC annotations, `BindingResult`, and the corresponding service/views. **`BindingResult` must immediately follow the model attribute** whose errors it receives.

Without a matching `BindingResult`/`Errors`, validation errors on a model attribute are typically turned into exceptions such as **MethodArgumentNotValidException** in the corresponding object validation cases; for method signatures with direct constraints or method validation, the exception path may differ. Verify the exact parameter type, annotations, and Spring MVC version.

### Difference from `@RequestBody`

With **@RequestBody**, JSON is read by an **HttpMessageConverter** (typically Jackson) before entering the controller. Malformed JSON or deserialization failures can become **HttpMessageNotReadableException**; that is not necessarily a `Formatter` error in `DataBinder`.

To format `LocalDate` in JSON, you normally configure Jackson's Java Time module or custom serializers/deserializers. Formatters registered through MVC's `ConversionService` primarily serve type conversion/formatting for request parameters, path variables, and property binding along the corresponding Spring MVC paths; do not assume Jackson calls them automatically.

## 9. Defining Thread-Safe and Deterministic Formatters

A formatter may be registered in a `ConversionService` shared across many requests. Implementations should be **stateless** or use thread-safe components.

**DateTimeFormatter** is immutable and thread-safe, suitable for `static final` fields. Conversely, classes like **SimpleDateFormat** are not thread-safe; if you must use them, create a fresh instance per `parse`/`print` or synchronize properly. Never keep a shared mutable `SimpleDateFormat` in a field of a singleton formatter.

Avoid these mistakes:

- Mutating shared locale or pattern per request by writing to a field.
- Swallowing `ParseException` and returning a default date such as today.
- Returning `null` for a malformed string to avoid binding errors, causing invalid input to look optional.
- Turning every exception into one generic message regardless of field/pattern.
- Using a formatter to query a database or check permissions.
- Catching `IllegalArgumentException` too broadly and hiding programming bugs unrelated to input.

A good formatter has clear parse rules, deterministic print output, informative errors, and zero per-request state.

## 10. Distinguishing Parse, Binding, and Validation Errors

| Scenario | Detecting Layer | Example | Typical Outcome |
| --- | --- | --- | --- |
| Syntactically invalid string | Formatter/Parser | `2026-02-30` | `ParseException` or `IllegalArgumentException` |
| Conversion failure | ConversionService | Formatter cannot build `LocalDate` | `ConversionFailedException`/parse cause |
| Property cannot be assigned | DataBinder | String cannot convert to field type | `FieldError`, typically code `typeMismatch` |
| Missing configured field | DataBinder | Required field absent | `FieldError`, code `required` |
| Bound value violates constraint | Bean Validation | Blank string with `@NotBlank` | `FieldError` with constraint code |
| Business rule violation | Service/domain | Booking date outside allowed window | Application-defined exception/domain error |
| Unreadable JSON | HttpMessageConverter/Jackson | Broken JSON body | `HttpMessageNotReadableException` |

For instance, `"2026-11-31"` may fail in the `Formatter` because that calendar day does not exist. `"2026-11-30"` parses successfully, yet if a business rule requires end dates not to exceed the registration cutoff, the service can still reject it. Do not push all those rules into the `Formatter`.

## 11. Test Strategy to Identify Which Exception Occurred

A test suite should verify each layer separately:

1. **Formatter unit test:** call `parse` directly with valid, malformed, and blank input; verify exception type and cause.
2. **ConversionService test:** register the formatter, call `convert`; verify the conversion exception wraps the parse failure properly.
3. **DataBinder test:** bind invalid input; confirm the target does not receive the invalid value and `FieldError` has code `typeMismatch`.
4. **MVC MockMvc test:** submit an invalid form request; confirm the view/response receives `BindingResult` and does not invoke the persistence service.
5. **Message test:** confirm code `typeMismatch` resolves to a locale-appropriate message.
6. **Thread-safety test if needed:** run concurrently many times and verify the formatter's results do not drift from shared state.

Conceptual assertion example:

~~~java
assertThat(result.getFieldError("startDate")).isNotNull();
assertThat(result.getFieldError("startDate").getCode())
        .isEqualTo("typeMismatch");
assertThat(result.getFieldError("startDate").isBindingFailure())
        .isTrue();
~~~

This test snippet uses AssertJ/JUnit in a project with test dependencies. It does not prove the root cause is `ParseException`; to verify that, inspect the conversion error's cause chain or test the formatter directly.

Avoid asserting against the entirety of Spring's default messages, as messages can vary by version/locale/`MessageSource`. Prefer checking error codes, field names, rejected values, and controller behavior.

## 12. Practical Checklist

When facing **ParseException, IllegalArgumentException, and binding error results**, determine:

- Which parser is the formatter calling? Does that API throw checked `ParseException` or a runtime exception?
- Does the formatter preserve the cause when translating exception types?
- Is the failure happening in a direct `parse` call, `ConversionService`, or `DataBinder`?
- If through `DataBinder`, what `FieldError` is created? Code `typeMismatch` or another code?
- Does the controller place `BindingResult` in the right position to handle errors itself, or does Spring take the exception path?
- Could the target object still hold an old value after a field failed to bind?
- Has `MessageSource` resolved the error code into a safe, locale-appropriate message?
- Is the formatter thread-safe and free from swallowing invalid data?
- Is the data path a form/`@ModelAttribute` or JSON/`@RequestBody`?

**Remember:** Parser exceptions explain why a string could not be parsed; `ConversionService` integrates the error into Spring's conversion model; `DataBinder` turns that error into inspectable, displayable binding info. Keeping the three layers clearly separated ensures consistent error handling without confusing parse failures with validation or business logic.

## Official Documentation

- [Spring Framework — Formatter SPI and parse/print](https://docs.spring.io/spring-framework/reference/core/validation/format.html)
- [Spring Framework 6.2 API — Parser<T>](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/format/Parser.html)
- [Spring Framework 6.2 API — Formatter<T>](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/format/Formatter.html)
- [Spring Framework 6.2 API — ConversionService](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/convert/ConversionService.html)
- [Spring Framework 6.2 API — DataBinder](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 API — BindingResult](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/validation/BindingResult.html)
