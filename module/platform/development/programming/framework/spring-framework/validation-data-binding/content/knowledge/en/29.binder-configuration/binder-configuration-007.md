# Adding Per-Field Formatters with `addCustomFormatter` in Spring `DataBinder`

## 1. Scenario: Two Fields of the Same Type Using Different Formats

In a Spring MVC form, two properties can share the `LocalDate` type yet follow different input conventions:

- `deliveryDate`: users enter the date in Vietnamese `dd/MM/uuuu` format, e.g., `31/12/2026`.
- `invoiceDate`: the invoicing system uses ISO `uuuu-MM-dd` format, e.g., `2027-01-02`.

If you apply **one global formatter for all `LocalDate` values**, one of the fields will parse or format incorrectly. The solution is to configure a formatter **for the exact property name** using the overload:

~~~java
binder.addCustomFormatter(
        new LocalDatePatternFormatter("dd/MM/uuuu"),
        "deliveryDate");

binder.addCustomFormatter(
        new LocalDatePatternFormatter("uuuu-MM-dd"),
        "invoiceDate");
~~~

This snippet uses a custom formatter class (complete runnable source is in section 7). Both properties are `LocalDate`, yet they use **two distinct formatters** on the same `WebDataBinder`. That is the purpose of `addCustomFormatter(Formatter<?> formatter, String... fields)`: **per-field formatting**, not just per-type formatting.

Key concepts to grasp:

1. `Formatter<T>` provides `parse(String, Locale)` and `print(T, Locale)`.
2. `DataBinder#addCustomFormatter(...)` registers a formatter on the binder; `WebDataBinder` inherits this API.
3. The `fields` parameter specifies **target property paths**, not HTTP header names, model attribute names, or JSON field names.
4. `@InitBinder` is the common integration point for registering formatters on a controller's form/model attribute.
5. `BindingResult` records conversion errors when a user submits an invalid string.
6. A formatter handles **conversion/presentation only**; it does not replace Bean Validation, authorization checks, or bindable-field allowlists.

## 2. Three `addCustomFormatter` Overloads and Their Scopes

Spring Framework defines these overloads on `org.springframework.validation.DataBinder`:

~~~java
void addCustomFormatter(Formatter<?> formatter);

void addCustomFormatter(Formatter<?> formatter,
                        String... fields);

void addCustomFormatter(Formatter<?> formatter,
                        Class<?>... fieldTypes);
~~~

| Call | Scope | When to Use |
| --- | --- | --- |
| `addCustomFormatter(formatter)` | Applies to fields matching the generic type declared by `Formatter<T>`. | All `LocalDate` properties on **this binder** share the same convention. |
| **`addCustomFormatter(formatter, "deliveryDate")`** | Only the property paths listed in `fields` that match the formatter's supported type. | **Specific fields have special formats**. |
| `addCustomFormatter(formatter, "startDate", "endDate")` | Multiple explicitly named fields share one formatter. | Several fields share a pattern without affecting other fields. |
| `addCustomFormatter(formatter, LocalDate.class)` | Scoped by the passed **field type**, not a field name. | Apply by type, even when generic formatter type info is insufficient. |

**Overload caution:** the `String... fields` parameter differs from `Class<?>... fieldTypes`. These two calls mean very different things:

~~~java
// Applies only to the "deliveryDate" property:
binder.addCustomFormatter(formatter, "deliveryDate");

// Applies by LocalDate type:
binder.addCustomFormatter(formatter, LocalDate.class);
~~~

If you **omit the field list** with the varargs overload, the Javadoc notes it falls back to applying to fields matching the formatter's type. To avoid overload confusion and guarantee field-specific behavior, **always pass the target field names explicitly**. Do not equate `@InitBinder("orderForm")` with `addCustomFormatter(..., "deliveryDate")`:

- `@InitBinder("orderForm")` scopes **which model attribute/binder is configured**.
- `"deliveryDate"` scopes **which property inside that binder's target receives the formatter**.

### Internal Adapter Mechanism

The `DataBinder#addCustomFormatter` Javadoc notes that Spring registers an underlying **`PropertyEditor` adapter** for the formatter. Therefore, this is **per-binder customization**, not a call that adds the formatter to every `ConversionService` across the application.

In other words:

~~~text
HTTP parameter "deliveryDate" = "31/12/2026"
                |
                v
@ModelAttribute("orderForm")
                |
                v
WebDataBinder
  ├─ property path: deliveryDate
  ├─ target type: java.time.LocalDate
  ├─ field-specific FormatterPropertyEditorAdapter
  ├─ Formatter.parse("31/12/2026", locale)
  └─ setter / property write:
          orderForm.setDeliveryDate(LocalDate.of(2026,12,31))
                |
                v
BindingResult (success or conversion error)
                |
                v
@Valid / @Validated if requested
                |
                v
Controller
~~~

Do not assume every converter registered through Spring `ConversionService` takes precedence in the exact same way as a custom editor. When multiple configurations could compete (per-field editor, per-type formatter, `@DateTimeFormat`), **explicitly choose one formatting source per field and test it** on your Spring version.

## 3. Writing a Contract-Compliant `Formatter<LocalDate>`

`org.springframework.format.Formatter<T>` combines two responsibilities:

- **`parse(String text, Locale locale)`**: converts user-entered text into `T`.
- **`print(T object, Locale locale)`**: converts `T` into a string for display or form rendering.

For dates, Java provides `java.time.format.DateTimeFormatter`, which is **immutable** and thread-safe when used properly. Formatter authors should avoid unsynchronized shared `SimpleDateFormat` instances or mutable per-request state.

Pattern formatter example:

~~~java
public final class LocalDatePatternFormatter
        implements Formatter<LocalDate> {

    private final DateTimeFormatter delegate;

    public LocalDatePatternFormatter(String pattern) {
        this.delegate = DateTimeFormatter.ofPattern(pattern)
                .withResolverStyle(ResolverStyle.STRICT);
    }

    @Override
    public LocalDate parse(String text, Locale locale) {
        return LocalDate.parse(text, delegate);
    }

    @Override
    public String print(LocalDate object, Locale locale) {
        return delegate.format(object);
    }
}
~~~

This snippet requires imports for `Formatter`, `LocalDate`, `DateTimeFormatter`, `ResolverStyle`, and `Locale`; the full file is in section 7.

### Why `uuuu` Instead of `yyyy` with Strict Parsing?

In `DateTimeFormatter`, `u` is proleptic year, whereas `y` is year-of-era. With `ResolverStyle.STRICT`, using `yyyy` without an era can fail to resolve `LocalDate`. Safe patterns are:

- `dd/MM/uuuu` for `31/12/2026`.
- `uuuu-MM-dd` for `2027-01-02`.

`ResolverStyle.STRICT` rejects `31/02/2026`, `29/02/2025`, and other invalid calendar dates instead of silently adjusting them to another date.

In this example, the patterns contain **only digits and fixed separators**, so the formatter intentionally **does not vary by `Locale`**. If you need month names in text, locale-specific numerals, localized separators, or time zones, design the formatter to **honor `locale`** and test each locale. Do not accept a `Locale` parameter and ignore it unconsciously.

### Symmetric Parse/Print

A single `Formatter<T>` should satisfy:

~~~text
value = LocalDate.of(2026, 12, 31)
formatted = formatter.print(value, locale)  -> "31/12/2026"
parsed = formatter.parse(formatted, locale) -> 2026-12-31
~~~

This helps when an HTML form **re-renders** an existing value (`print`) and **receives** a form submission (`parse`). If `parse` and `print` are incompatible, a form may display one date format and fail to parse that exact format when the user saves.

For empty strings, whitespace, `null`, invalid values, or unexpected input, establish a clear policy:

- Let `@NotNull` check required fields after binding if a value is missing.
- For unparseable strings, report a conversion error via `BindingResult`; do not silently substitute a default date.
- If whitespace trimming is needed, make it an explicit part of the input contract and test it; the complete example enforces **exact pattern matching**.
- Never return `LocalDate.now()` on parse failure: that masks errors and corrupts business data.

## 4. Using `@InitBinder` to Attach Formatters to the Right Model Attribute

In Spring MVC, a controller can have:

~~~java
@InitBinder("orderForm")
void configureDates(WebDataBinder binder) {
    binder.setAllowedFields(
            "deliveryDate", "invoiceDate", "note");

    binder.addCustomFormatter(
            new LocalDatePatternFormatter("dd/MM/uuuu"),
            "deliveryDate");

    binder.addCustomFormatter(
            new LocalDatePatternFormatter("uuuu-MM-dd"),
            "invoiceDate");
}

@PostMapping("/orders/form")
ResponseEntity<String> save(
        @Valid @ModelAttribute("orderForm") OrderForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return ResponseEntity.badRequest().body("FORM_INVALID");
    }
    return ResponseEntity.ok("OK");
}
~~~

This is a controller snippet assuming imports and types `OrderForm` and `LocalDatePatternFormatter`; section 7 provides the complete source.

**Processing flow:**

1. Spring MVC receives form/query parameters for the model attribute named `orderForm`.
2. Instantiates/retrieves `OrderForm`, prepares `WebDataBinder`, and invokes `@InitBinder("orderForm")` to configure it.
3. The binder reads `deliveryDate` and `invoiceDate` and converts each `String` into `LocalDate` via its **per-field formatter**.
4. The binder assigns values to JavaBean properties, recording conversion failures in `BindingResult`.
5. If `@Valid` and a Bean Validation provider are present, Spring evaluates constraints on `OrderForm`.
6. Because `BindingResult` sits **immediately after** the form, the controller inspects errors and chooses the response.

**Security boundary:** `setAllowedFields(...)` defines which properties may be written by property binding; `addCustomFormatter(...)` **does not act as an allowlist**. Even if a formatter is registered only for `deliveryDate`, an attacker can still send `isAdmin=true` to another field if the model has a setter and no binding restrictions exist.

### Scope and Lifecycle of `@InitBinder`

`@InitBinder` in a controller normally applies only to that controller's binders. `@ControllerAdvice` can supply shared configuration across controllers. `@InitBinder("orderForm")` applies only to matching model attribute names, so if a handler uses `@ModelAttribute("order")`, configuration intended for `orderForm` **will not apply**.

For another request DTO that also has a `deliveryDate` field but uses a different binder, it does not automatically inherit this formatter. Configuring both the **right object name** and the **right property path** are essential checks.

**WebFlux:** `@InitBinder` and `WebDataBinder` are also used for model attributes in Spring WebFlux. However, WebFlux request parsing and argument resolution differ from Servlet MVC. If an app uses WebFlux, write `WebTestClient` tests specifically; do not assume `@RequestParam` in WebFlux reads `form-urlencoded` identically to Servlet MVC.

## 5. Comparing `addCustomFormatter` with Other Approaches

| Configuration Method | Typical Scope | When to Choose |
| --- | --- | --- |
| `binder.addCustomFormatter(formatter, "deliveryDate")` | Local to **one field** on the current binder. | One property uses a different convention than other fields of the same type. |
| `binder.addCustomFormatter(formatter)` | Local to all fields of a type on the current binder. | Fields of the same type in this form share a rule. |
| `binder.addCustomFormatter(formatter, LocalDate.class)` | Local by declared field type. | Specify the type explicitly rather than relying on generic formatter inference. |
| `@DateTimeFormat(pattern = "dd/MM/uuuu")` | Placed on a field/parameter. | Format is expressible with standard annotations without custom code. |
| `WebMvcConfigurer#addFormatters(FormatterRegistry)` | MVC application-wide converter/formatter. | Rules shared across multiple controllers. |
| `FormattingConversionService` | Service/application-level conversion/formatting. | Shared policies and annotation formatters. |
| `binder.registerCustomEditor(type, path, editor)` | `PropertyEditor` by type/path, older API. | Legacy editor integration; prefer `Formatter` first. |
| Jackson `@JsonFormat` or `ObjectMapper` | JSON bodies via `@RequestBody`. | JSON APIs, not HTTP form/query binding. |

When you only need a fixed pattern for a field, a simpler option can be:

~~~java
public class OrderForm {
    @DateTimeFormat(pattern = "dd/MM/uuuu")
    private LocalDate deliveryDate;

    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate invoiceDate;
}
~~~

This is a conceptual snippet omitting getters/setters and imports. For static formats, `@DateTimeFormat` is often concise and easy to maintain. **`addCustomFormatter` shines when you must select an implementation or formatting scope right at the binder** (e.g., special forms, per-controller policies, or shared formatting with custom logic). Do not add a custom formatter merely to duplicate what a standard annotation already solves.

### Why `addCustomFormatter` Does Not Change JSON

Suppose a client sends:

~~~http
POST /orders/json
Content-Type: application/json

{"deliveryDate":"31/12/2026","invoiceDate":"2027-01-02"}
~~~

`@RequestBody` normally uses `HttpMessageConverter`/Jackson to read JSON. Jackson **does not call `WebDataBinder`'s custom `Formatter` to parse JSON properties**. Without a Jackson custom deserializer/`@JsonFormat` on the `LocalDate` property, ISO JSON is handled by the Java Time module, while `31/12/2026` typically fails deserialization.

Conversely, the exact same strings in an `application/x-www-form-urlencoded` body are bound by `@ModelAttribute` through `WebDataBinder` as configured here. Do not treat `setAllowedFields`/`addCustomFormatter` as a general solution for Jackson JSON.

## 6. Conversion Errors: `BindingResult`, `FieldError`, and Validation

A formatter cannot parse `deliveryDate=31/02/2026`. During form binding, Spring typically turns that failure into a `FieldError` with a `typeMismatch` code.

~~~java
BindingResult result = binder.getBindingResult();

if (result.hasFieldErrors("deliveryDate")) {
    FieldError error = result.getFieldError("deliveryDate");

    System.out.println(error.getField());
    System.out.println(error.getCode());
}
~~~

This is an illustrative snippet assuming `binder` exists. In real code, when a `FieldError` exists, `getCode()` is usually `"typeMismatch"`, while `getCodes()` holds multiple codes for object/field/type message resolution. Do not treat exact exception messages from Java's `DateTimeFormatter` or Hibernate Validator as a stable API contract, as they can change.

### Binding and Validation Are Two Separate Steps

- **Binding/conversion:** `"31/12/2026"` becomes `LocalDate.of(2026,12,31)`; if parsing fails, a binding error is recorded.
- **Bean Validation:** `@NotNull` checks that the field is non-null after binding. `@Future` or class-level constraints check date rules, which are **value checks**, not parsing substitutes.
- **Business validation:** whether `deliveryDate` must not precede `invoiceDate`, or whether invoicing before delivery is allowed, depends on requirements; check via an appropriate service or custom validator.

Do not throw `ValidationException` or `IllegalStateException` from a formatter just for malformed input text. When parsing fails, throw `IllegalArgumentException` or a parser exception supported by Spring so the binder can create a field error. Never return an arbitrary fallback date to make the form appear valid.

### Differences Between Form Errors and JSON Errors

| Input | Pipeline | Typical Error |
| --- | --- | --- |
| `application/x-www-form-urlencoded` + `@ModelAttribute` | `WebDataBinder` and `Formatter` | `FieldError` with code `typeMismatch`; without a local `BindingResult`, MVC may throw `MethodArgumentNotValidException`. |
| `application/json` + `@RequestBody` | `HttpMessageConverter`/Jackson | `HttpMessageNotReadableException` when JSON fails deserialization, typically HTTP 400. |
| Form parses cleanly but fails `@NotNull`/`@Future` | Bean Validation | Field/object validation errors in `BindingResult`. |
| URL query with `@ModelAttribute` | Property binding by property names | Formatters registered on the binder apply similarly to form fields. |
| Standalone `@RequestParam LocalDate date` | Argument conversion | Do not assume a formatter registered **only for property `deliveryDate` on a model attribute** applies; use `@DateTimeFormat` or an argument-scoped formatter. |

**Avoid targeting mistakes:** `addCustomFormatter(...,"deliveryDate")` applies to a **binder property path**, not to every parameter named `deliveryDate` in any controller.

## 7. Runnable Example: Spring Boot 3.x + Java 17+ + MockMvc

Create a Maven project with Spring Boot **3.x**, Java 17+, and Jakarta Validation. Dependencies in `pom.xml` (versions managed by Spring Boot's parent/BOM):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Create files under `src/main/java/com/example/fieldformatter/` and `src/test/java/com/example/fieldformatter/`. Each public class matches its filename. No database is required.

### 7.1. File `FieldFormatterApplication.java`

~~~java
package com.example.fieldformatter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FieldFormatterApplication {

    public static void main(String[] args) {
        SpringApplication.run(FieldFormatterApplication.class, args);
    }
}
~~~

### 7.2. File `StrictLocalDateFormatter.java`

~~~java
package com.example.fieldformatter;

import org.springframework.format.Formatter;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

public final class StrictLocalDateFormatter
        implements Formatter<LocalDate> {

    private final DateTimeFormatter delegate;

    public StrictLocalDateFormatter(String pattern) {
        this.delegate = DateTimeFormatter.ofPattern(pattern)
                .withResolverStyle(ResolverStyle.STRICT);
    }

    @Override
    public LocalDate parse(String text, Locale locale) {
        return LocalDate.parse(text, delegate);
    }

    @Override
    public String print(LocalDate object, Locale locale) {
        return delegate.format(object);
    }
}
~~~

`DateTimeFormatter` is immutable and thread-safe; this formatter holds only a single `final` field. Because the pattern is numeric, the implementation does not depend on `Locale`. If you add localized month names, pass `locale` when constructing `DateTimeFormatter` or select an appropriate parser/formatter for the request locale.

### 7.3. File `OrderForm.java`

~~~java
package com.example.fieldformatter;

import jakarta.validation.constraints.NotNull;

import java.time.LocalDate;

public class OrderForm {

    @NotNull
    private LocalDate deliveryDate;

    @NotNull
    private LocalDate invoiceDate;

    private String note;

    public OrderForm() {
    }

    public LocalDate getDeliveryDate() {
        return deliveryDate;
    }

    public void setDeliveryDate(LocalDate deliveryDate) {
        this.deliveryDate = deliveryDate;
    }

    public LocalDate getInvoiceDate() {
        return invoiceDate;
    }

    public void setInvoiceDate(LocalDate invoiceDate) {
        this.invoiceDate = invoiceDate;
    }

    public String getNote() {
        return note;
    }

    public void setNote(String note) {
        this.note = note;
    }
}
~~~

Both fields are `LocalDate`, yet `@NotNull` checks only for null; it does not govern text input syntax. Parsing is performed by the formatters registered on the binder.

### 7.4. File `OrdersController.java`

~~~java
package com.example.fieldformatter;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDate;

@RestController
@RequestMapping("/orders")
public class OrdersController {

    @InitBinder("orderForm")
    void initOrderBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "deliveryDate", "invoiceDate", "note");

        binder.addCustomFormatter(
                new StrictLocalDateFormatter("dd/MM/uuuu"),
                "deliveryDate");

        binder.addCustomFormatter(
                new StrictLocalDateFormatter("uuuu-MM-dd"),
                "invoiceDate");
    }

    @PostMapping(path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<String> form(
            @Valid @ModelAttribute("orderForm") OrderForm form,
            BindingResult result) {

        if (result.hasErrors()
                || result.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest()
                    .body("FORM_INVALID");
        }

        return ResponseEntity.ok(
                "FORM:" + form.getDeliveryDate()
                + "|" + form.getInvoiceDate());
    }

    @GetMapping("/preview")
    public ResponseEntity<String> preview(
            @Valid @ModelAttribute("orderForm") OrderForm form,
            BindingResult result) {

        if (result.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body("PREVIEW_INVALID");
        }

        return ResponseEntity.ok(
                "PREVIEW:" + form.getDeliveryDate()
                + "|" + form.getInvoiceDate());
    }

    @PostMapping(path = "/json",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<String> json(
            @Valid @RequestBody OrderJson input) {

        return ResponseEntity.ok(
                "JSON:" + input.deliveryDate()
                + "|" + input.invoiceDate());
    }

    public record OrderJson(
            @NotNull LocalDate deliveryDate,
            @NotNull LocalDate invoiceDate) {
    }
}
~~~

**What happens at each endpoint?**

- `POST /orders/form`: Spring MVC binds form values into `OrderForm`; `@InitBinder("orderForm")` adds **two field-specific formatters**; `@Valid` checks `@NotNull`; the controller catches errors with `BindingResult`. The success body uses `LocalDate#toString()`, always printing ISO `uuuu-MM-dd` rather than the raw user input string.
- `GET /orders/preview`: query parameters bind to the same `orderForm` model attribute, so the formatters apply there too.
- `POST /orders/json`: Jackson reads JSON into the `OrderJson` record and **does not** use `WebDataBinder`'s two field-specific formatters. With Boot's default JSON Java Time support, ISO dates work while `31/12/2026` is normally rejected unless Jackson is configured.
- `setAllowedFields(...)` blocks properties outside the form contract. In practice, using dedicated request DTOs keeps model control safe; `@Valid` is not authorization.

### 7.5. File `StrictLocalDateFormatterTest.java` — Unit Testing Formatter and `DataBinder`

Create at `src/test/java/com/example/fieldformatter/StrictLocalDateFormatterTest.java`:

~~~java
package com.example.fieldformatter;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

import java.time.LocalDate;
import java.util.Locale;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class StrictLocalDateFormatterTest {

    private DataBinder newBinder(OrderForm target) {
        DataBinder binder = new DataBinder(target, "orderForm");

        binder.addCustomFormatter(
                new StrictLocalDateFormatter("dd/MM/uuuu"),
                "deliveryDate");

        binder.addCustomFormatter(
                new StrictLocalDateFormatter("uuuu-MM-dd"),
                "invoiceDate");

        return binder;
    }

    @Test
    void formatAndParseRoundTrip() {
        var formatter =
                new StrictLocalDateFormatter("dd/MM/uuuu");

        var date = LocalDate.of(2026, 12, 31);
        assertEquals("31/12/2026",
                formatter.print(date, Locale.ROOT));
        assertEquals(date,
                formatter.parse("31/12/2026", Locale.ROOT));
    }

    @Test
    void bindsTwoLocalDatesWithDifferentPatterns() {
        var target = new OrderForm();
        var binder = newBinder(target);

        binder.bind(new MutablePropertyValues(Map.of(
                "deliveryDate", "31/12/2026",
                "invoiceDate", "2027-01-02"
        )));

        assertFalse(binder.getBindingResult().hasErrors());
        assertEquals(LocalDate.of(2026, 12, 31),
                target.getDeliveryDate());
        assertEquals(LocalDate.of(2027, 1, 2),
                target.getInvoiceDate());
    }

    @Test
    void invalidDateIsFieldBindingError() {
        var target = new OrderForm();
        var binder = newBinder(target);

        binder.bind(new MutablePropertyValues(Map.of(
                "deliveryDate", "31/02/2026",
                "invoiceDate", "2027-01-02"
        )));

        assertTrue(binder.getBindingResult()
                .hasFieldErrors("deliveryDate"));
        assertEquals("typeMismatch",
                binder.getBindingResult()
                        .getFieldError("deliveryDate").getCode());
        assertEquals(LocalDate.of(2027, 1, 2),
                target.getInvoiceDate());
    }

    @Test
    void datePatternIsSpecificToEachField() {
        var target = new OrderForm();
        var binder = newBinder(target);

        // String uses deliveryDate's pattern
        // but is sent to invoiceDate.
        binder.bind(new MutablePropertyValues(Map.of(
                "invoiceDate", "31/12/2026"
        )));

        assertTrue(binder.getBindingResult()
                .hasFieldErrors("invoiceDate"));
        assertNull(target.getInvoiceDate());
    }

    @Test
    void strictParserRejectsInvalidLeapDay() {
        var formatter =
                new StrictLocalDateFormatter("dd/MM/uuuu");

        assertThrows(RuntimeException.class, () ->
                formatter.parse("29/02/2025", Locale.ROOT));
    }
}
~~~

These tests use `DataBinder` directly without starting a web server. They prove that the two `LocalDate` fields have distinct formatters, invalid dates are recorded in `BindingResult`, and `parse/print` are symmetric. `assertThrows(RuntimeException.class)` avoids coupling the test to a specific parser exception subclass; in this implementation, `LocalDate.parse` throws `DateTimeParseException` on invalid dates.

`DataBinder.bind(...)` **does not automatically run Bean Validation**; because the unit tests check conversion only, `@NotNull` is not the source of errors there. To test a validator, register a `Validator` on the binder and call `validate()`, or test an MVC endpoint with `@Valid` as shown next.

### 7.6. File `OrdersControllerTest.java` — 9 MockMvc Tests

Create at `src/test/java/com/example/fieldformatter/OrdersControllerTest.java`:

~~~java
package com.example.fieldformatter;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void bindsFormFieldsUsingTheirOwnPatterns() throws Exception {
        mvc.perform(post("/orders/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("deliveryDate", "31/12/2026")
                    .param("invoiceDate", "2027-01-02"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "FORM:2026-12-31|2027-01-02"));
    }

    @Test
    void canBindQueryToTheSameModelAttribute() throws Exception {
        mvc.perform(get("/orders/preview")
                    .param("deliveryDate", "31/12/2026")
                    .param("invoiceDate", "2027-01-02"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "PREVIEW:2026-12-31|2027-01-02"));
    }

    @Test
    void rejectsWrongPatternForDeliveryDate() throws Exception {
        mvc.perform(post("/orders/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("deliveryDate", "2026-12-31")
                    .param("invoiceDate", "2027-01-02"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("FORM_INVALID"));
    }

    @Test
    void rejectsWrongPatternForInvoiceDate() throws Exception {
        mvc.perform(post("/orders/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("deliveryDate", "31/12/2026")
                    .param("invoiceDate", "02/01/2027"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("FORM_INVALID"));
    }

    @Test
    void rejectsImpossibleDate() throws Exception {
        mvc.perform(post("/orders/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("deliveryDate", "31/02/2026")
                    .param("invoiceDate", "2027-01-02"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("FORM_INVALID"));
    }

    @Test
    void rejectsMissingRequiredField() throws Exception {
        mvc.perform(post("/orders/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("deliveryDate", "31/12/2026"))
                .andExpect(status().isBadRequest())
                .andExpect(content().string("FORM_INVALID"));
    }

    @Test
    void jsonIsoDatesDoNotNeedFieldFormatter() throws Exception {
        mvc.perform(post("/orders/json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "deliveryDate":"2026-12-31",
                              "invoiceDate":"2027-01-02"
                            }
                            """))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "JSON:2026-12-31|2027-01-02"));
    }

    @Test
    void jsonSlashDateIsNotChangedByFormFormatter()
            throws Exception {
        mvc.perform(post("/orders/json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "deliveryDate":"31/12/2026",
                              "invoiceDate":"2027-01-02"
                            }
                            """))
                .andExpect(status().isBadRequest());
    }

    @Test
    void endpointDeclaresItsInputMediaType() throws Exception {
        mvc.perform(post("/orders/form")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"deliveryDate\":\"2026-12-31\"}"))
                .andExpect(status().isUnsupportedMediaType());
    }
}
~~~

Run all tests in both files:

~~~bash
./mvnw test -Dtest=StrictLocalDateFormatterTest,OrdersControllerTest
~~~

On Windows, use `mvnw.cmd test -Dtest=StrictLocalDateFormatterTest,OrdersControllerTest`, or run `mvn test` if Maven is configured on the system.

With Spring Boot 3.x Web + Validation + Test as above, **14 tests are designed to pass** (5 unit tests and 9 MockMvc tests). Key scenarios:

| Scenario | Expected Result |
| --- | --- |
| Form `deliveryDate=31/12/2026`, `invoiceDate=2027-01-02` | HTTP 200, `FORM:2026-12-31\|2027-01-02`. |
| Matching query to `/orders/preview` | HTTP 200, `PREVIEW:2026-12-31\|2027-01-02`. |
| Form sends ISO for `deliveryDate` | HTTP 400 and body `FORM_INVALID`. |
| Form sends slash-date for `invoiceDate` | HTTP 400 and body `FORM_INVALID`. |
| Date `31/02/2026` | HTTP 400 due to parse failure. |
| Missing `invoiceDate` | HTTP 400 due to `@NotNull`. |
| JSON with two ISO dates | HTTP 200, `JSON:2026-12-31\|2027-01-02`. |
| JSON `deliveryDate` with slash-date | HTTP 400 in JSON decoder; does not go through field formatter. |
| Sending JSON to a form-only endpoint | HTTP 415. |

**Limitations:** these tests are designed for a Boot 3.x project with the exact dependencies above, without Spring Security or custom error handlers. If you add CSRF, custom `@ControllerAdvice`, alter `ObjectMapper`/validation config, or use a different Spring Boot version, re-verify HTTP statuses and schemas. Never hardcode Java/Spring parse error messages; assert only statuses/bodies controlled by the controller.

### 7.7. Trying with `curl`

After running `./mvnw spring-boot:run`:

~~~bash
curl -i -X POST "http://localhost:8080/orders/form" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "deliveryDate=31%2F12%2F2026&invoiceDate=2027-01-02"

curl -i "http://localhost:8080/orders/preview?deliveryDate=31%2F12%2F2026&invoiceDate=2027-01-02"

curl -i -X POST "http://localhost:8080/orders/json" \
  -H "Content-Type: application/json" \
  -d '{"deliveryDate":"2026-12-31","invoiceDate":"2027-01-02"}'
~~~

The commands above are for Unix shells. Slashes in dates are URL-encoded in the form/query to illustrate that HTTP parameter decoding occurs before the formatter runs. In PowerShell, use `curl.exe` and adjust quoting and line continuation for the shell. Successful responses print dates in ISO format via `LocalDate#toString()`.

## 8. Field Names and Property Paths: Configuring the Right Target

`fields` in `addCustomFormatter(formatter, String... fields)` are **property paths**. With nested classes:

~~~java
public class BookingForm {
    private DateRange dates;

    public DateRange getDates() { return dates; }
    public void setDates(DateRange dates) { this.dates = dates; }
}

public class DateRange {
    private LocalDate start;

    public LocalDate getStart() { return start; }
    public void setStart(LocalDate start) {
        this.start = start;
    }
}
~~~

These are two illustrative classes; place them in separate files or omit `public` if putting them in one file. If the form input sends `dates.start=31/12/2026`, the matching formatter path is:

~~~java
binder.addCustomFormatter(
        new StrictLocalDateFormatter("dd/MM/uuuu"),
        "dates.start");
~~~

**Do not write `"start"`** when the binder target is `BookingForm` and the property actually lives at `dates.start`. Nested property resolution also requires appropriate getters/setters and nested target objects; `DataBinder` auto-grow nested paths may be needed if `dates` starts as `null`.

For collection paths like `items[0].shipDate`, understand how Spring canonicalizes/indexes properties, bound collection sizes, and test thoroughly. Do not use arbitrary wildcard patterns in `fields` assuming they match every element: the underlying `registerCustomEditor(Class, String, PropertyEditor)` API operates on property paths, not the same pattern-matching semantics as `setAllowedFields`. When multiple elements share a formatter, prefer type/annotation-based formatting or an appropriate DTO structure.

### Why Not Rely Only on Java Parameter Names?

`@ModelAttribute("orderForm")` names the **model object**, whereas `"deliveryDate"` is the **property** name. If a handler has a standalone parameter `@RequestParam("deliveryDate") LocalDate date`, the model-attribute binder is not necessarily used to convert that argument. For single arguments, place `@DateTimeFormat(pattern="dd/MM/uuuu")` directly on the parameter or register a formatter scoped to argument resolution.

## 9. Locale, Format Errors, and Thread-Safety

`Formatter<T>` receives `Locale` to support user language and regional conventions. Currency formatter example:

~~~java
public final class MoneyFormatter implements Formatter<BigDecimal> {
    @Override
    public BigDecimal parse(String text, Locale locale)
            throws ParseException {
        // Parse number by locale with NumberFormat and check precision.
        throw new UnsupportedOperationException(
                "Illustrative skeleton only");
    }

    @Override
    public String print(BigDecimal amount, Locale locale) {
        // Locale-dependent: 1.234,56 or 1,234.56.
        throw new UnsupportedOperationException(
                "Illustrative skeleton only");
    }
}
~~~

This is **not a usable implementation**; it merely illustrates that a formatter is bidirectional and receives `Locale`. For real currency handling, parse carefully with `NumberFormat`, account for scale and currency symbols, and guard against unintended rounding. Do not copy this skeleton into production.

In our `StrictLocalDateFormatter` example, formatting is locale-independent because the format is a fixed protocol. If a form needs localized text like `01 Jan 2027`, build a locale-aware formatter. `DateTimeFormatter.ofPattern(pattern, locale)` lets you create a locale-specific formatter; use immutable configs or construct instances per call if handling dynamic locales.

**Thread-safety:** Controllers/binders can reuse formatter instances across concurrent requests. A formatter must be **stateless or immutable**—never store `Locale`, text being parsed, or a shared mutable `DateFormat` in fields. Immutable `DateTimeFormatter` is safe; a singleton `SimpleDateFormat` is not thread-safe across threads.

### How Should Errors Be Handled?

- Parse failure: let Spring populate `BindingResult`/`FieldError`; never fabricate a valid-looking value.
- Required fields: use `@NotNull`/Bean Validation where applicable.
- Never perform network calls or database queries inside a formatter: `parse/print` are synchronous APIs, and blocking work slows down argument binding—especially in Spring WebFlux.
- Do not echo raw user input or stack traces in error responses if they may contain sensitive data.

## 10. Common Pitfalls and Checklist

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| Both `LocalDate` fields parse with the same pattern | Formatter registered by type instead of per field. | Use the `addCustomFormatter(formatter, "fieldName")` overload. |
| Formatter does not apply | `@InitBinder` targets the wrong object name or wrong field path. | Align `@ModelAttribute("orderForm")` and `"deliveryDate"`. |
| Submitting `31/02/2026` produces no error | Default lenient parser or formatter silently adjusts the date. | Use strict date parsing and add invalid-date tests. |
| JSON `31/12/2026` fails to deserialize | Jackson does not use `WebDataBinder` field formatters. | Use ISO JSON or configure Jackson/`@JsonFormat` separately. |
| `@RequestParam LocalDate date` ignores the form formatter | Formatter is registered on a model attribute's property path. | Put `@DateTimeFormat` on the argument or use an appropriate formatter scope. |
| `getFieldError("deliveryDate")` shows `typeMismatch` | Input string could not be parsed into `LocalDate`. | Return form error / HTTP 400 instead of substituting a fake date. |
| `@NotNull` error missing when calling `DataBinder.bind` manually | Binding is separate from validation. | Register/call a validator or use `@Valid` in MVC. |
| Sensitive form field gets bound | Formatters are not allowlists. | Use a dedicated form DTO and `setAllowedFields(...)`. |
| Same formatter suffers race conditions | Shared mutable parser/state stored in fields. | Use immutable `DateTimeFormatter`; never share `SimpleDateFormat`. |
| Strict parser fails with `yyyy` | Year-of-era lacks era under strict resolving. | Use `uuuu` for ISO/proleptic years. |

### Pre-Deployment Checklist

- [ ] Identified the exact fields needing custom formatters instead of applying one to the entire type.
- [ ] `@InitBinder` matches the model attribute name; `fields` lists exact property paths.
- [ ] Formatter implements both `parse` and `print` symmetrically.
- [ ] Pattern, locale, and strictness contracts are clear; tested with both valid and invalid dates.
- [ ] `BindingResult` is placed immediately after `@ModelAttribute` when the controller handles errors.
- [ ] Bean Validation enforces required/range/business rules where needed; formatters are not treated as validators.
- [ ] Dedicated DTO and allowlist prevent mass assignment; never bind directly onto entities with server-only fields.
- [ ] Never assume a form formatter applies to JSON `@RequestBody` or arbitrary `@RequestParam` arguments.
- [ ] Tested another field of the **same type** to prove per-field isolation.
- [ ] Formatter is thread-safe, holds no request-specific mutable state, and performs no blocking I/O.
- [ ] Considered `@DateTimeFormat` first when the rule is simple enough not to need a custom formatter.

**Remember:** `addCustomFormatter(formatter, "deliveryDate")` customizes **conversion/formatting for one specific property on a binder**. It lets one model hold multiple `LocalDate` fields with different conventions. Align all three pieces—model attribute name, property path, and formatter type—then verify with `BindingResult` and tests.

## References

- Spring Framework Javadoc — `DataBinder#addCustomFormatter(Formatter, String...)` and overloads: https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework Reference — `@InitBinder` in MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework Reference — Spring Field Formatting (`Formatter<T>`, `Parser`, `Printer`): https://docs.spring.io/spring-framework/reference/core/validation/format.html
- Spring Framework Reference — MVC Data Binding and model security: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
- Spring Framework Reference — `@ModelAttribute` in controllers: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework Reference — `@InitBinder` in WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-initbinder.html
