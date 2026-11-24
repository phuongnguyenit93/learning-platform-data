# Registering Local Editors with `registerCustomEditor` in Spring Framework

## 1. Problem and Objectives

Spring MVC and Spring WebFlux can bind HTTP form/query parameters onto JavaBeans via `@ModelAttribute`. Most inputs arrive as strings, whereas the target object may contain `LocalDate`, `Date`, `Integer`, `String`, lists, or custom domain types. `DataBinder` must convert strings to property types before assigning values via setters or the appropriate binding mechanism.

Example form submission:

~~~text
title=  Java Workshop
startDate=25/12/2026
endDate=2026-12-31
coupon=  vip10
tags[0]=spring
approved=true
~~~

The target object has `String title`, `LocalDate startDate`, `LocalDate endDate`, `String coupon`, `List<String> tags`, and `boolean approved`. We want to trim `title`, parse the two dates using **two different formats**, uppercase `coupon`, and prevent the client from updating `approved`.

Spring comes with `ConversionService`, `Converter`, `Formatter`, and many default editors. When you want a custom JavaBeans rule scoped to a binder, use **`registerCustomEditor`**:

~~~java
@InitBinder("eventForm")
void configure(WebDataBinder binder) {
    binder.registerCustomEditor(
            LocalDate.class, "startDate",
            new StrictLocalDateEditor("dd/MM/uuuu"));
}
~~~

This is an **illustrative method** placed inside a controller, not a complete Java file. It tells the binder named `eventForm` to apply `StrictLocalDateEditor` to the `startDate` property of type `LocalDate`.

**Learning outcomes:** after this lesson, you will know how to distinguish type-level vs. property-path registration, implement `PropertyEditorSupport`, register editors via `@InitBinder`, read conversion errors with `BindingResult`, protect inputs with an allowlist, and choose `Formatter`/`Converter` when traditional editors are not appropriate.

## 2. What Is a `PropertyEditor`?

### 2.1. The JavaBeans API

`java.beans.PropertyEditor` is the JavaBeans interface for text ↔ object transformations. Spring's `BeanWrapper`/`DataBinder` supports editors when populating properties. `java.beans.PropertyEditorSupport` provides a convenient base class: override only the methods you need rather than implementing the entire interface.

| Method | Purpose |
| --- | --- |
| `setAsText(String text)` | Parses incoming text and calls `setValue(...)` to store the result |
| `setValue(Object value)` | Sets the internal Java value |
| `getValue()` | Reads the editor's Java value |
| `getAsText()` | Converts the current Java value back to text for appropriate JavaBeans rendering paths |

Example editor that uppercases coupon codes:

~~~java
import java.beans.PropertyEditorSupport;
import java.util.Locale;

public final class CouponCodeEditor extends PropertyEditorSupport {
    @Override
    public void setAsText(String text) {
        setValue(text == null
                ? ""
                : text.strip().toUpperCase(Locale.ROOT));
    }

    @Override
    public String getAsText() {
        Object value = getValue();
        return value == null ? "" : value.toString();
    }
}
~~~

Given `"  vip10  "`, the editor sets the value `"VIP10"`. `Locale.ROOT` keeps technical-code uppercasing consistent across machines.

**An editor only normalizes syntax.** It does not verify whether the coupon exists, is expired, belongs to the current user, or is eligible to apply. Those rules belong in validation or service/domain logic.

### 2.2. Statefulness and Thread Safety

`PropertyEditorSupport` holds internal state (`value`). Consequently, an editor instance **must not be assumed thread-safe by default**. Avoid placing a mutable editor in a `static final` field and sharing it across request binders.

The safe approach with `@InitBinder` is creating a fresh editor for each binder. In particular, `SimpleDateFormat` (when writing editors for `java.util.Date`) is also mutable and not thread-safe across threads. Java Time's `DateTimeFormatter` is immutable and reusable; however, the `PropertyEditorSupport` instance itself is still stateful, so create a new one per binder.

### 2.3. Two Separate Stages

~~~text
HTTP text "25/12/2026"
       |
       v
PropertyEditor / Converter / Formatter
       |
       v
LocalDate.of(2026, 12, 25)
       |
       v
Jakarta Bean Validation / Spring Validator
       |
       v
Valid or constraint violation
~~~

Invalid date syntax produces a **type conversion/binding error**. A date that parses cleanly but violates a business rule produces a **validation error** when a relevant validator actually runs.

## 3. Two Overloads of `registerCustomEditor`

Spring's `PropertyEditorRegistry` provides two overloads:

~~~java
// Abbreviated API signatures; do not redeclare in your app.
void registerCustomEditor(Class<?> requiredType,
                          PropertyEditor editor);

void registerCustomEditor(Class<?> requiredType,
                          String propertyPath,
                          PropertyEditor editor);
~~~

### 3.1. Registering by Type

~~~java
binder.registerCustomEditor(
        String.class, new StringTrimmerEditor(true));
~~~

Every `String` property in the binder's scope is trimmed unless a property has a more specific editor. `StringTrimmerEditor(true)` trims whitespace and turns strings that become empty into `null`. Because `@NotBlank` rejects `null`, whitespace-only fields are caught when Bean Validation runs.

Use this when every `String` input on **that binder** follows the same trimming policy. Do not apply it blindly to passwords, digitally signed strings, or text where whitespace must be preserved.

### 3.2. Registering by Type and Property

~~~java
binder.registerCustomEditor(
        String.class, "coupon", new CouponCodeEditor());
~~~

For `coupon`, the property-specific editor takes precedence over the general `StringTrimmerEditor`. Result: `title` is trimmed, while `coupon` is both trimmed and uppercased. That is the **difference between type-scope and property-scope** inside a single binder.

Similarly, same type `LocalDate` but different formats:

~~~java
binder.registerCustomEditor(
        LocalDate.class, "startDate",
        new StrictLocalDateEditor("dd/MM/uuuu"));
binder.registerCustomEditor(
        LocalDate.class, "endDate",
        new StrictLocalDateEditor("uuuu-MM-dd"));
~~~

If you register a `LocalDate.class` editor without a path, both dates risk being forced into the same format. When a contract has field-specific formats, the overload with `propertyPath` is the clear choice.

### 3.3. Decision Table

| Requirement | Registration Call | Scope |
| --- | --- | --- |
| Trim every `String` property in the form | `registerCustomEditor(String.class, editor)` | By type |
| Uppercase only `coupon` | `registerCustomEditor(String.class, "coupon", editor)` | By property |
| Parse all `java.util.Date` with one pattern | `registerCustomEditor(Date.class, editor)` | By type |
| Parse only `startDate` as day/month/year | `registerCustomEditor(LocalDate.class, "startDate", editor)` | By property |
| Parse `address.city` in a nested object | `registerCustomEditor(String.class, "address.city", editor)` | By nested path |
| Parse `items[n].quantity` | `registerCustomEditor(Integer.class, "items.quantity", editor)` | By canonical list-element path |

`propertyPath` is **relative to the binder's target object**, not a URI, URL path, or full name prefixed with the model attribute name. For an `eventForm` binder, use `"startDate"`, not `"eventForm.startDate"`.

### 3.4. One Editor per Path

The `PropertyEditorRegistry` Javadoc notes that only **one custom editor can be registered for a given property path**. For collections/arrays, an editor can apply to **the whole collection** or **each element** depending on `requiredType`. Do not register both a collection-level editor and an element-level editor on the same property path expecting Spring to chain two conversions.

Spring's documentation uses the path `"items.quantity"` for actual fields like `items[0].quantity` and `items[1].quantity`. Keep `requiredType` accurate (`Integer.class` when the property is `Integer`), match the DTO structure, and test with the exact field names requests send.

## 4. Local Scope: `@InitBinder` on a Controller

### 4.1. Local to Controller and Attribute Name

~~~java
@RestController
class FormController {

    @InitBinder("eventForm")
    void init(WebDataBinder binder) {
        binder.registerCustomEditor(
                String.class, new StringTrimmerEditor(true));
    }
}
~~~

This is a configuration example without a handler yet. Spring calls `@InitBinder` when initializing matching binders in **that controller**. `"eventForm"` is the object name, e.g., specified via `@ModelAttribute("eventForm")`. If the controller has other attributes with different formatting needs, avoid putting type-wide editors in an unrestricted `@InitBinder` unintentionally.

Use multiple names when the same rule applies to multiple forms:

~~~java
@InitBinder({"eventForm", "reminderForm"})
void initTwo(WebDataBinder binder) {
    binder.registerCustomEditor(
            String.class, new StringTrimmerEditor(true));
}
~~~

The two examples above are independent options, not instructions to place two methods modifying the same binder. Multiple `@InitBinder` methods running in overlapping scopes can make configuration hard to follow; give each hook a clear responsibility.

### 4.2. `@ControllerAdvice` Scope

~~~java
@ControllerAdvice(assignableTypes = EventController.class)
class EventBindingAdvice {

    @InitBinder
    void shared(WebDataBinder binder) {
        binder.registerCustomEditor(
                String.class, new StringTrimmerEditor(true));
    }
}
~~~

This configuration applies to controllers selected by the advice. `@ControllerAdvice` can be narrowed via `assignableTypes`, `basePackageClasses`, `basePackages`, or `annotations`. We do not add this advice to the runnable project in section 6 because we want to test the difference between a controller with a local editor and one without it.

In WebFlux annotated controllers, `@InitBinder` methods from `@ControllerAdvice` apply before local `@InitBinder` methods on the controller. Avoid relying on two places overriding the same editor by implicit ordering; instead define clear shared and field-specific policies.

### 4.3. Do Not Perform Asynchronous Work in the Hook

`@InitBinder` typically takes `WebDataBinder` and returns `void`. It is a **synchronous** configuration hook; do not return `Mono<Void>` from `@InitBinder` expecting Spring to subscribe to register editors. Never perform database or blocking HTTP calls inside `setAsText(...)`.

Spring WebFlux reads form bodies under a reactive contract, yet binder formatting/conversion logic should be fast and run cleanly during request processing. Business validation requiring external I/O should move to a reactive service after parsing/binding.

## 5. Building `StrictLocalDateEditor` Properly

### 5.1. Strict Parsing

To parse `25/12/2026` with `dd/MM/uuuu`, use `DateTimeFormatter` and `ResolverStyle.STRICT`:

~~~java
import java.beans.PropertyEditorSupport;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;

public final class StrictLocalDateEditor extends PropertyEditorSupport {

    private final DateTimeFormatter formatter;

    public StrictLocalDateEditor(String pattern) {
        formatter = DateTimeFormatter.ofPattern(pattern)
                .withResolverStyle(ResolverStyle.STRICT);
    }

    @Override
    public void setAsText(String text) {
        if (text == null || text.isBlank()) {
            setValue(null);
            return;
        }
        setValue(LocalDate.parse(text.strip(), formatter));
    }

    @Override
    public String getAsText() {
        LocalDate date = (LocalDate) getValue();
        return date == null ? "" : date.format(formatter);
    }
}
~~~

In strict parsing, `uuuu` (proleptic year) works better than `yyyy` (year-of-era) when the pattern has no era field. `LocalDate.parse` throws `DateTimeParseException` on invalid dates. Through the binder, this error is typically translated into a `FieldError` with a `typeMismatch` code.

| Input with pattern `dd/MM/uuuu` | Result |
| --- | --- |
| `25/12/2026` | `LocalDate.of(2026, 12, 25)` |
| ` 25/12/2026 ` | Valid due to `strip()` |
| `2026-12-25` | Format error |
| `31/02/2026` | Non-existent date error |
| Empty string | `null`; `@NotNull` can catch it when validation runs |

`getAsText()` describes JavaBeans text rendering; it **does not alter Jackson's JSON format** when a `@RestController` returns an object. JSON formatting must be configured via the corresponding serializer/deserializer mechanism.

### 5.2. Compared with `CustomDateEditor`

Spring provides `org.springframework.beans.propertyeditors.CustomDateEditor` for `java.util.Date`, for example:

~~~java
@InitBinder
void initLegacyDate(WebDataBinder binder) {
    SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd");
    format.setLenient(false);
    binder.registerCustomEditor(
            java.util.Date.class,
            new CustomDateEditor(format, false));
}
~~~

This is an illustrative method requiring imports for `SimpleDateFormat`, `CustomDateEditor`, and `WebDataBinder`. `CustomDateEditor` is not for `java.time.LocalDate`. `SimpleDateFormat` is mutable, so create a new instance inside the init method; never share a singleton across requests.

For Java Time, newer applications usually prefer `@DateTimeFormat` or a `Formatter<LocalDate>` when simple formatting suffices. This lesson uses `PropertyEditorSupport` to illustrate the exact behavior of `registerCustomEditor`.

## 6. Runnable Example: Java 17, Spring Boot 3.5.7, WebFlux

This project uses Spring WebFlux to exercise URL-encoded forms and `@InitBinder`, alongside testing `WebDataBinder` directly in unit tests. The editor registration APIs are shared by both MVC and WebFlux.

### 6.1. Project Structure

~~~text
pom.xml
src/main/java/com/example/localeditor/
  LocalEditorApplication.java
  EventForm.java
  StrictLocalDateEditor.java
  CouponCodeEditor.java
  EventController.java
  RawEventController.java
src/test/java/com/example/localeditor/
  EventControllerTest.java
  EventBinderTest.java
~~~

### 6.2. Maven Dependencies

~~~xml
<!-- pom.xml -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>local-editor-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
</project>
~~~

`spring-boot-starter-webflux` ensures the app runs on the reactive stack when the Servlet MVC starter is not included. `spring-boot-starter-validation` provides the Jakarta Validation provider; `spring-boot-starter-test` provides JUnit 5 and WebFlux test utilities. No database is needed.

### 6.3. Spring Boot Application

~~~java
// src/main/java/com/example/localeditor/LocalEditorApplication.java
package com.example.localeditor;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LocalEditorApplication {

    public static void main(String[] args) {
        SpringApplication.run(LocalEditorApplication.class, args);
    }
}
~~~

### 6.4. Form Object

~~~java
// src/main/java/com/example/localeditor/EventForm.java
package com.example.localeditor;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;

public class EventForm {

    @NotBlank(message = "Title must not be blank")
    private String title;

    @NotNull(message = "Start date is required")
    private LocalDate startDate;

    @NotNull(message = "End date is required")
    private LocalDate endDate;

    private String coupon = "";

    @Size(max = 3, message = "At most 3 tags")
    private List<@NotBlank String> tags = new ArrayList<>();

    // Present solely to demonstrate mass-assignment risk.
    private boolean approved;

    public EventForm() {}

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }

    public LocalDate getStartDate() { return startDate; }
    public void setStartDate(LocalDate startDate) {
        this.startDate = startDate;
    }

    public LocalDate getEndDate() { return endDate; }
    public void setEndDate(LocalDate endDate) {
        this.endDate = endDate;
    }

    public String getCoupon() { return coupon; }
    public void setCoupon(String coupon) { this.coupon = coupon; }

    public List<String> getTags() { return tags; }
    public void setTags(List<String> tags) { this.tags = tags; }

    public boolean isApproved() { return approved; }
    public void setApproved(boolean approved) {
        this.approved = approved;
    }
}
~~~

This class has a no-arg constructor and getters/setters to keep property binding straightforward. `@Valid` checks the field constraints after binding. `approved` is included only to test that `approved=true` is blocked by `allowedFields`; in a real application, omit such a property from public input DTOs.

### 6.5. Two Editors as Java Files

~~~java
// src/main/java/com/example/localeditor/StrictLocalDateEditor.java
package com.example.localeditor;

import java.beans.PropertyEditorSupport;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;

public final class StrictLocalDateEditor extends PropertyEditorSupport {
    private final DateTimeFormatter formatter;

    public StrictLocalDateEditor(String pattern) {
        this.formatter = DateTimeFormatter.ofPattern(pattern)
                .withResolverStyle(ResolverStyle.STRICT);
    }

    @Override
    public void setAsText(String text) {
        if (text == null || text.isBlank()) {
            setValue(null);
            return;
        }
        setValue(LocalDate.parse(text.strip(), formatter));
    }

    @Override
    public String getAsText() {
        LocalDate value = (LocalDate) getValue();
        return value == null ? "" : value.format(formatter);
    }
}
~~~

~~~java
// src/main/java/com/example/localeditor/CouponCodeEditor.java
package com.example.localeditor;

import java.beans.PropertyEditorSupport;
import java.util.Locale;

public final class CouponCodeEditor extends PropertyEditorSupport {

    @Override
    public void setAsText(String text) {
        setValue(text == null
                ? ""
                : text.strip().toUpperCase(Locale.ROOT));
    }

    @Override
    public String getAsText() {
        Object value = getValue();
        return value == null ? "" : value.toString();
    }
}
~~~

These files compile once Spring dependencies are resolved by Maven for the application. Never reuse a `CouponCodeEditor` or `StrictLocalDateEditor` instance across requests.

### 6.6. Controller Registering Local Editors

~~~java
// src/main/java/com/example/localeditor/EventController.java
package com.example.localeditor;

import jakarta.validation.Valid;
import org.springframework.beans.propertyeditors.StringTrimmerEditor;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/events")
public class EventController {

    @InitBinder("eventForm")
    void configureBinder(WebDataBinder binder) {
        binder.setAllowedFields(
                "title", "startDate", "endDate", "coupon", "tags[*]");
        binder.setAutoGrowCollectionLimit(6);

        // By type: every String property in the binder.
        binder.registerCustomEditor(
                String.class, new StringTrimmerEditor(true));

        // By property path: only coupon.
        binder.registerCustomEditor(
                String.class, "coupon", new CouponCodeEditor());

        binder.registerCustomEditor(
                LocalDate.class, "startDate",
                new StrictLocalDateEditor("dd/MM/uuuu"));
        binder.registerCustomEditor(
                LocalDate.class, "endDate",
                new StrictLocalDateEditor("uuuu-MM-dd"));
    }

    @PostMapping(consumes =
            MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<ResponseEntity<Map<String, Object>>> create(
            @Valid @ModelAttribute("eventForm") EventForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            List<String> fields = errors.getFieldErrors().stream()
                    .map(FieldError::getField)
                    .distinct()
                    .sorted()
                    .toList();

            return Mono.just(ResponseEntity.badRequest()
                    .body(Map.of("invalidFields", fields)));
        }

        Map<String, Object> body = Map.of(
                "title", form.getTitle(),
                "startDate", form.getStartDate().toString(),
                "endDate", form.getEndDate().toString(),
                "coupon", form.getCoupon() == null
                        ? "" : form.getCoupon(),
                "tags", form.getTags(),
                "approved", form.isApproved());

        return Mono.just(ResponseEntity.ok(body));
    }

    @PostMapping(path = "/strict", consumes =
            MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<String> createStrict(
            @Valid @ModelAttribute("eventForm") EventForm form) {
        return Mono.just("accepted:" + form.getTitle());
    }
}
~~~

**Effects of `@InitBinder("eventForm")`**:
1. Spring WebFlux creates a binder for the model attribute with object name `eventForm` and invokes `configureBinder`.
2. `setAllowedFields` permits property binding only for five field patterns; `approved` is suppressed even if sent by the client.
3. `StringTrimmerEditor(true)` applies to regular `String` properties; `CouponCodeEditor` has a dedicated path and uppercases `coupon`.
4. The two `StrictLocalDateEditor` instances apply distinct formats rather than one shared rule for all `LocalDate` fields.
5. Spring binds form/query parameters, and then `@Valid` invokes Bean Validation.
6. `BindingResult` immediately after the model attribute lets the handler return clean, safe error details. The `/events/strict` endpoint has no `BindingResult`, so an invalid form typically throws `WebExchangeBindException` and returns HTTP 400.

`Mono.just(...)` is the WebFlux handler return type; it does not imply `@InitBinder` runs asynchronously. The `@InitBinder` hook simply registers editors on the current binder.

### 6.7. Second Controller Proving Local Scope

~~~java
// src/main/java/com/example/localeditor/RawEventController.java
package com.example.localeditor;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class RawEventController {

    @PostMapping(path = "/raw-events", consumes =
            MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Map<String, String> raw(
            @ModelAttribute("eventForm") EventForm form) {
        return Map.of("title", form.getTitle());
    }
}
~~~

It uses the same `@ModelAttribute("eventForm")` yet **is not in `EventController`**, so it does not receive the other controller's local `@InitBinder`. For `title="  Java Workshop  "`, the text keeps leading/trailing spaces since no global editor interferes. `@Valid` is absent, so the two missing dates do not cause a Bean Validation error on this endpoint.

### 6.8. Running with `curl`

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -i -X POST http://localhost:8080/events \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "title=  Java Workshop  " \
  --data-urlencode "startDate=25/12/2026" \
  --data-urlencode "endDate=2026-12-31" \
  --data-urlencode "coupon=  vip10  " \
  --data-urlencode "tags[0]=spring" \
  --data-urlencode "approved=true"
~~~

Expected JSON output (key order not guaranteed):

~~~json
{
  "title": "Java Workshop",
  "startDate": "2026-12-25",
  "endDate": "2026-12-31",
  "coupon": "VIP10",
  "tags": ["spring"],
  "approved": false
}
~~~

The `\` line continuations suit Linux/macOS/Git Bash shells. In PowerShell, use PowerShell line-continuation syntax or a single-line `curl.exe` command.

## 7. Testing Editor Registration

### 7.1. HTTP Integration Tests with `WebTestClient`

~~~java
// src/test/java/com/example/localeditor/EventControllerTest.java
package com.example.localeditor;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@AutoConfigureWebTestClient
@SpringBootTest
class EventControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void fieldAndTypeEditorsWorkTogether() {
        client.post()
                .uri("/events")
                .body(BodyInserters.fromFormData(
                        "title", "  Java Workshop  ")
                        .with("startDate", "25/12/2026")
                        .with("endDate", "2026-12-31")
                        .with("coupon", "  vip10  ")
                        .with("tags[0]", "spring")
                        .with("approved", "true"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title").isEqualTo("Java Workshop")
                .jsonPath("$.startDate").isEqualTo("2026-12-25")
                .jsonPath("$.endDate").isEqualTo("2026-12-31")
                .jsonPath("$.coupon").isEqualTo("VIP10")
                .jsonPath("$.tags[0]").isEqualTo("spring")
                .jsonPath("$.approved").isEqualTo(false);
    }

    @Test
    void invalidDateIsBindingError() {
        client.post()
                .uri("/events")
                .body(BodyInserters.fromFormData(
                        "title", "Java Workshop")
                        .with("startDate", "31/02/2026")
                        .with("endDate", "2026-12-31"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.invalidFields[0]")
                .isEqualTo("startDate");
    }

    @Test
    void blankTitleIsValidationError() {
        client.post()
                .uri("/events")
                .body(BodyInserters.fromFormData("title", "   ")
                        .with("startDate", "25/12/2026")
                        .with("endDate", "2026-12-31"))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.invalidFields[0]")
                .isEqualTo("title");
    }

    @Test
    void localEditorDoesNotLeakToOtherController() {
        client.post()
                .uri("/raw-events")
                .body(BodyInserters.fromFormData(
                        "title", "  Java Workshop  "))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title")
                .isEqualTo("  Java Workshop  ");
    }

    @Test
    void strictHandlerReturns400ForInvalidForm() {
        client.post()
                .uri("/events/strict")
                .body(BodyInserters.fromFormData("title", " ")
                        .with("startDate", "25/12/2026")
                        .with("endDate", "2026-12-31"))
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

The test suite verifies:
- Distinction between type-wide and field-specific editors.
- Non-existent dates trigger errors on the right field.
- Whitespace-only strings become `null` via the editor and are caught by `@NotBlank`.
- Local editors do not leak to another controller even with the same model attribute name.
- An endpoint without `BindingResult` returns HTTP 400 when Bean Validation fails.

### 7.2. Direct Unit Tests with `WebDataBinder`

~~~java
// src/test/java/com/example/localeditor/EventBinderTest.java
package com.example.localeditor;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.web.bind.WebDataBinder;

import java.time.LocalDate;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class EventBinderTest {

    private WebDataBinder configured(EventForm form) {
        WebDataBinder binder = new WebDataBinder(form, "eventForm");
        new EventController().configureBinder(binder);
        return binder;
    }

    @Test
    void typeAndPathSpecificConversion() {
        EventForm form = new EventForm();
        WebDataBinder binder = configured(form);

        binder.bind(new MutablePropertyValues(Map.of(
                "title", "  Java Workshop  ",
                "startDate", "25/12/2026",
                "endDate", "2026-12-31",
                "coupon", "  vip10  ",
                "approved", "true"
        )));

        assertFalse(binder.getBindingResult().hasErrors());
        assertEquals("Java Workshop", form.getTitle());
        assertEquals(LocalDate.of(2026, 12, 25),
                form.getStartDate());
        assertEquals(LocalDate.of(2026, 12, 31),
                form.getEndDate());
        assertEquals("VIP10", form.getCoupon());
        assertFalse(form.isApproved());
        assertArrayEquals(new String[]{"approved"},
                binder.getBindingResult().getSuppressedFields());
    }

    @Test
    void twoDatePathsHaveDifferentPatterns() {
        EventForm form = new EventForm();
        WebDataBinder binder = configured(form);

        binder.bind(new MutablePropertyValues(Map.of(
                "title", "Java",
                "startDate", "2026-12-25",
                "endDate", "25/12/2026"
        )));

        assertNotNull(binder.getBindingResult()
                .getFieldError("startDate"));
        assertNotNull(binder.getBindingResult()
                .getFieldError("endDate"));
    }

    @Test
    void bindingDoesNotAutomaticallyValidateAnnotations() {
        EventForm form = new EventForm();
        WebDataBinder binder = configured(form);

        binder.bind(new MutablePropertyValues(Map.of(
                "title", "    ",
                "startDate", "25/12/2026",
                "endDate", "2026-12-31"
        )));

        assertNull(form.getTitle());
        assertFalse(binder.getBindingResult().hasErrors());
        // The test does not configure a Bean Validation provider or call validate().
    }
}
~~~

Run command:

~~~bash
mvn test
~~~

**Expected result:** 8 tests PASS (5 HTTP-level tests, 3 binder tests). This is expected based on the APIs and configuration shown, **not an executed runtime log**. To run only `EventBinderTest`:

~~~bash
mvn -Dtest=EventBinderTest test
~~~

Specifically, the final test shows that **editors perform only conversion**; `@NotBlank` did not run because the binder was created manually without attaching a validator or calling `validate()`.

## 8. `BindingResult` and Error Messages

When an editor parses text, three distinct outcomes can occur:

~~~text
startDate=31/02/2026
  -> DateTimeParseException
  -> BindingResult: conversion error, typically typeMismatch

title="   "
  -> StringTrimmerEditor(true) -> null
  -> @NotBlank (if validation runs) -> NotBlank error

approved=true
  -> Not in setAllowedFields
  -> getSuppressedFields() contains "approved"
  -> Does not necessarily produce a FieldError
~~~

`FieldError#getField()` gives the property name such as `startDate`; `getCode()` may be `typeMismatch` or a constraint name; `getDefaultMessage()` is a potentially locale-dependent message. **Never return `getRejectedValue()` directly in an API response** if forms may contain tokens or personal data.

In WebFlux, an object-only `@Valid @ModelAttribute` without an immediately following `BindingResult` typically produces `WebExchangeBindException` and 400. If the handler has direct method constraints such as `@RequestParam @Min(1)`, Spring Framework 6.1+ may handle it via method validation and throw `HandlerMethodValidationException`. Do not lump every 400 error into a single exception branch.

If parsing fails and the editor throws an exception that aborts the app outside the binder, check the exception type thrown by `setAsText`: parse exceptions like `IllegalArgumentException` or `DateTimeParseException` are standard signals for the binding infrastructure to record a conversion error. Never swallow the error and assign a fake date, which could falsely mark the form valid.

## 9. Collections, Nested Paths, and `requiredType`

For a form with `List<Item> items`:

~~~text
items[0].quantity=2
items[1].quantity=5
~~~

Spring's `PropertyEditorRegistry` documents how to register an editor for every index of a nested property using its canonical path:

~~~java
binder.registerCustomEditor(
        Integer.class,
        "items.quantity",
        new QuantityEditor());
~~~

`QuantityEditor` here is an **illustrative name** requiring an implementation before compiling. You do not need to register `items[0].quantity` and `items[1].quantity` separately. Path lookup strips indices to locate the editor for the corresponding property.

Illustrative DTO example:

~~~java
public class Item {
    private Integer quantity;

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

A custom editor for `Integer.class`, if used to parse quantities, must handle format, bounds, and conversion errors properly. With `List<Item>`, the target structure, item constructors, setters, and auto-grow settings must align. `registerCustomEditor` **does not automatically instantiate arbitrary nested objects** if Spring cannot construct an element.

In particular, an editor for **the entire collection** and an editor for **each element** have different semantics. Per the API, `requiredType` decides whether the editor applies to the collection or the elements at that path; do not register both on the same property path expecting the pipeline to invoke them sequentially.

## 10. Security and Blast Radius

### 10.1. An Editor Is Not an Allowlist

`CouponCodeEditor` normalizes coupon codes, yet has no authority over which fields clients can modify. If a form has `approved`, `roles`, `account.ownerId`, or `paymentStatus`, avoid exposing them on input DTOs. At the binder level:

~~~java
binder.setAllowedFields(
        "title", "startDate", "endDate", "coupon", "tags[*]");
~~~

Only allowlisted property paths undergo property binding. Blocked fields appear in `BindingResult#getSuppressedFields()`; they are not automatically constraint violations.

Recommendations:
1. Use small, web-dedicated input DTOs.
2. Specify an `allowedFields` allowlist whenever property-binding an object with multiple setters.
3. Bound collection indices/nesting depth and HTTP body sizes.
4. Validate types and formats after binding.
5. Check authorization and ownership in the service layer, never trusting field names sent by the client.

### 10.2. JSON `@RequestBody` Takes a Different Path

~~~http
POST /api/events HTTP/1.1
Content-Type: application/json

{"startDate":"25/12/2026","coupon":"vip10"}
~~~

With `@RequestBody` JSON, Jackson/`HttpMessageReader` deserializes the payload instead of using a form property-name binder like `@ModelAttribute`. **`registerCustomEditor` does not configure a Jackson deserializer**, and `setAllowedFields` does not filter JSON properties like a form. If JSON needs custom date formats or coupon uppercasing, configure a JSON DTO/Jackson or a dedicated mapping service.

### 10.3. Local Does Not Mean Thread-Local

Local `@InitBinder` means **scoped to a controller/model attribute**, not a global editor or an application-managed per-thread field. Controllers are typically singletons; editor state should be instantiated fresh per binder, never stored in shared fields. On WebFlux's event loop, never block inside an editor.

### 10.4. Do Not Forget Constructor Binding

Spring Framework 6.1+ supports constructor binding for model attributes. `allowedFields` primarily governs **property binding**; it does not automatically turn constructor parameters into suppressed fields. For records and immutable DTOs, inspect constructor paths, parameter names, conversion, and input policies separately. Always test an editor against the exact binder mechanism used rather than assuming property-binding tests cover constructor binding.

## 11. When to Use `Formatter` or `Converter`?

| Choice | Strength | Best Suited When |
| --- | --- | --- |
| `PropertyEditor` via `registerCustomEditor` | Local by type/path, JavaBeans support | Legacy editors, one form with special rules |
| `Converter<S,T>` | Type-safe API, typically stateless | General type conversion via `ConversionService` |
| `Formatter<T>` | Bidirectional parse/print and `Locale`-aware | Dates, numbers, currency, and UI rendering |
| `@DateTimeFormat` | Concise annotation on Java Time fields | Common date/time formats |
| Jackson deserializer | Controls JSON input | `@RequestBody`, JSON APIs |

In MVC, you can register global formatters via `WebMvcConfigurer#addFormatters`. In WebFlux, use `WebFluxConfigurer#addFormatters`. When only one specific field needs a parser, the `registerCustomEditor(type, path, editor)` overload is quite straightforward.

`PropertyEditor` is stateful and lacks a `Locale` parameter in `setAsText`; `Formatter<T>` receives `Locale` in both `parse` and `print`, making i18n easier. Do not assume converters, formatters, and editors run sequentially in a chain: the conversion service picks the path matching your configuration and registered editors.

## 12. Common Mistakes

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| `registerCustomEditor` does not run | `@InitBinder` does not match model object name | Match `@InitBinder("eventForm")` with `@ModelAttribute("eventForm")` |
| Date editor for `startDate` does not run | `propertyPath` was prefixed with `eventForm.` | Use the relative path `startDate` |
| `endDate` mistakenly uses `startDate`'s format | Registered only by type `LocalDate.class` | Use the path overload |
| General `String` editor strips important whitespace | Type-wide `StringTrimmerEditor` is too broad | Scope to specific fields or omit trimming for that data |
| Invalid dates are still accepted | Non-strict parser | Use `ResolverStyle.STRICT` and test `31/02` |
| `CustomDateEditor` fails to handle `LocalDate` | Confusing `java.util.Date` with Java Time | Pick an editor for the right type |
| Values leak across requests | Shared mutable editor / `SimpleDateFormat` | Instantiate a new editor per binder |
| Conversion fails without constraint code | Editor raises type mismatch before validation | Inspect `BindingResult#getFieldErrors()` |
| `@NotBlank` never runs | Bound manually without calling a validator | Use `@Valid` or configure and invoke `binder.validate()` |
| JSON bypasses the editor | Jackson deserializes `@RequestBody` | Use a proper JSON deserializer/DTO |
| Client can modify `approved` | Missing allowlist / dedicated DTO | `setAllowedFields` + authorization |
| High list index causes errors/resource exhaustion | Auto-grow and missing input limits | `setAutoGrowCollectionLimit`, body limits, and field-count limits |
| Another controller also gets the editor | `@ControllerAdvice`/global converter too broad | Narrow scope and test the other controller |
| Editor performs blocking I/O | Abusing conversion for business logic | Move to a reactive service |
| Two editors on one property don't chain as expected | Only one editor per path; lookup favors path-specific | Combine normalization if needed and test the path |
| `getAsText()` does not change JSON output | JSON serialization does not use JavaBeans editors | Configure Jackson separately |

## 13. Self-Practice Exercises

1. Write a `PhoneNumberEditor` for `contact.phone` that only normalizes separator characters; use Bean Validation for validity checks.
2. Create three `LocalDate` fields of the same type with different formats; register a type-wide editor and field-specific editors, then write tests proving precedence.
3. Use a `List<Item>` form, submit `items[0].quantity` and `items[1].quantity`, and register an editor on path `items.quantity`.
4. Replace `StrictLocalDateEditor` with `@DateTimeFormat(pattern="dd/MM/uuuu")` and compare the code and scope.
5. Move a shared editor into `@ControllerAdvice(assignableTypes=...)` and test controllers inside and outside that scope.
6. Send JSON `startDate=25/12/2026`, observe why the binder editor does not apply, and configure Jackson appropriately.
7. Test `approved=true`, `tags[99999]`, and missing `startDate`, distinguishing suppression, conversion, auto-grow, and validation.
8. Write a concurrent-request test verifying that a stateful `PropertyEditorSupport` instance is never shared.
9. Add a constraint ensuring "`endDate` is not before `startDate`" using a Spring `Validator` or custom Jakarta constraint—**not** inside the date-parsing editor.

## 14. Checklist and References

- [ ] Use `registerCustomEditor(type, editor)` when an entire type shares a rule, and the `propertyPath` overload when a specific field needs its own rule.
- [ ] Match `@InitBinder` name with `@ModelAttribute`, and keep paths relative to the target bean.
- [ ] Instantiate a new stateful editor per binder; never share mutable `SimpleDateFormat` instances.
- [ ] Distinguish parse/`typeMismatch` errors from Bean Validation/constraint errors.
- [ ] Place `BindingResult` immediately after non-reactive `@ModelAttribute` when handling errors in the controller.
- [ ] Use minimal input DTOs, allowlists, and separate authorization checks.
- [ ] Test WebFlux forms with `WebTestClient` and binders with `WebDataBinder`; do not use `MockMvc` for WebFlux.
- [ ] Do not expect editors to change Jackson JSON serialization.
- [ ] For shared conversion and locale handling, prefer `Converter`/`Formatter`/`ConversionService`.

**Official documentation:**
- Spring Framework 6.2, `@InitBinder` in MVC: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework 6.2, `@InitBinder` in WebFlux: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-initbinder.html
- Spring Framework 6.2, `PropertyEditor` and Data Binding: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html
- Spring Framework 6.2, `PropertyEditorRegistry` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/beans/PropertyEditorRegistry.html
- Spring Framework 6.2, `DataBinder` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.2, WebFlux model attribute: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/modelattrib-method-args.html
- Spring Boot 3.5 testing: https://docs.spring.io/spring-boot/3.5/reference/testing/index.html
