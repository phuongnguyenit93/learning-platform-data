# Experimenting with the Bind, Convert, Validate Chain and Reading BindingResult in Spring Framework

## 1. Goal: Seeing Every Stage of a Request

In Spring MVC, when an HTTP form is mapped into a Java object, beginners often oversimplify it as “Spring reads the fields and then runs `@Valid`”. In reality, you need to separate three activities and one place that collects the results:

~~~text
Form/query parameters (HTTP character strings)
        |
        v
1. BIND: determine target object and property path to assign
        |
        +---- 2. CONVERT: String -> Integer / LocalDate / custom type
        |             |
        |             +---- failure -> FieldError (bindingFailure=true)
        |
        v
3. VALIDATE: check @NotBlank, @Min, @Email, @Valid nested...
        |
        +---- violation -> FieldError / ObjectError (validation errors)
        |
        v
4. BindingResult: read binding + conversion + validation errors
        |
        +---- hasErrors(), getFieldErrors(), getGlobalErrors()
        +---- getSuppressedFields(), getErrorCount(), getFieldValue()
        |
        v
Controller decides 200/400 and exposes only safe data
~~~

**Exact point to remember:** *conversion is not necessarily a standalone “step that runs after bind”*. When `DataBinder#bind` applies a value to a property whose type is not `String`, Spring performs type conversion **inside the binding process**, through `ConversionService`, formatters, property editors, or related mechanisms. Afterward, `DataBinder#validate` is called separately in the direct programmatic example; in MVC, Spring handles validation for `@Valid`/`@Validated` at the appropriate point in the handler argument lifecycle.

Hands-on objectives:
1. Submit a real form and observe Spring assigning `String` values to the DTO.
2. Verify `"5"` converts to `Integer(5)` and `"2026-12-20"` converts to `LocalDate`.
3. Compare the input `"not-a-number"` with a valid number that violates `@Min(1)`.
4. Prove that **binding errors already exist before calling `validate()`** when using a `WebDataBinder` directly.
5. Confirm that validation subsequently adds errors to the **same `BindingResult`**.
6. Read nested paths such as `address.city` and `items[0].units`.
7. Inspect `getSuppressedFields()` when the user submits a field outside the allowlist.
8. Map results into a public error DTO **without leaking rejected values**.
9. Test both the raw binder layer and HTTP with JUnit 5 / MockMvc.
10. Know when Spring automatically throws `MethodArgumentNotValidException` and when the controller reads `BindingResult` inline.

This lesson uses **Java 17, Spring Boot 3.5.7, Spring Framework 6.2, Spring MVC Servlet, Jakarta Bean Validation**. Every snippet belonging to the runnable project has a file/package name; snippets labeled *illustrative* are only for explaining the API. The unit/integration test results stated at the end are **expectations based on the code**, not a claim that Maven was executed.

## 2. Two Classes of Errors: Type Conversion vs Validation

### 2.1. Conversion Failure

DTO:

~~~java
@NotNull
@Min(1)
private Integer quantity;
~~~

Request:

~~~text
quantity=abc
~~~

Spring knows the `quantity` property needs an `Integer`, but `"abc"` cannot be turned into an integer. This is a **binding/type conversion** error, typically having:
- `FieldError#getField()` equal to `"quantity"`.
- `FieldError#getCode()` equal to `"typeMismatch"`.
- `FieldError#isBindingFailure()` equal to `true`.

Some subsequent validation steps may report additional related errors or skip a property that has a binding error, depending on how the adapter/validator handles it; **do not assume the total error count is always exactly one**. What is stable to assert is that there is a corresponding conversion error and the value was not spuriously turned into a valid number.

### 2.2. Conversion Succeeds, but the Value Is Invalid

Request:

~~~text
quantity=0
~~~

`"0"` converts to `Integer(0)` successfully. Then `@Min(1)` detects that the value is below the threshold. The `FieldError` at this point typically has code `"Min"` and `isBindingFailure()==false`.

A strong test should demonstrate both cases:

| Input | Bind/convert | Validate | Expected error |
| --- | --- | --- | --- |
| `quantity=5` | Succeeds → `5` | `@Min(1)` passes | No error on quantity |
| `quantity=0` | Succeeds → `0` | `@Min(1)` fails | `Min` |
| `quantity=abc` | Cannot convert | May still validate other parts | `typeMismatch` |
| `quantity` omitted | Remains `null` | `@NotNull` fails | `NotNull` |
| `customerName=   ` | String bound successfully | `@NotBlank` fails | `NotBlank` |
| `deliveryDate=2026-12-20` | ISO date parsed successfully | `@NotNull` passes | No error |
| `deliveryDate=bad` | Date conversion fails | May have accompanying errors | `typeMismatch` |

### 2.3. Bean Validation Runs After a Target Exists

The `@Valid` annotation does not modify input data, does not automatically allow binding extra fields, and is not a converter. It requests validation according to the Jakarta provider. `@NotBlank`/`@Email`/`@Min` define constraints. Validation for nested objects requires cascading `@Valid`.

`BindingResult` is where Spring combines type conversion/binding errors and validator errors. It extends `Errors`; as a result, it provides detailed error-reading methods without needing to catch individual exceptions separately.

## 3. Key APIs Used in the Experiment

| API | Purpose |
| --- | --- |
| `DataBinder` | Binds property values onto a Java target, supporting conversion and validation |
| `WebDataBinder` | Web-binding variant, used in MVC `@InitBinder` |
| `MutablePropertyValues` | Supplies a set of input property paths for experimenting without HTTP |
| `ConversionService` | Converts strings and other sources to the target type |
| `DefaultFormattingConversionService` | ConversionService with default formatters/annotation formatting |
| `@DateTimeFormat(iso=ISO.DATE)` | Enables parsing ISO date strings from forms during binding |
| `@Valid` | Triggers validation and cascades to nested objects when supported |
| `DataBinder#addValidators` | Registers a Spring `Validator` on the binder |
| `DataBinder#bind` | Applies property values and performs type conversion |
| `DataBinder#validate` | Invokes registered validators and appends errors |
| `DataBinder#getBindingResult` | Retrieves current errors, target info, and suppressed fields |
| `BindingResult#hasErrors` | Whether any field/global error exists |
| `BindingResult#getErrorCount` | Total number of ObjectErrors/FieldErrors |
| `BindingResult#getFieldErrors` | List of field-bound errors |
| `BindingResult#getGlobalErrors` | Object-level errors not tied to a specific field |
| `FieldError#getField` | Field path, including nested/indexed segments if any |
| `FieldError#getCode` | Primary selected error code |
| `FieldError#isBindingFailure` | Distinguishes binding/conversion errors from validator errors |
| `BindingResult#getSuppressedFields` | Input fields excluded from binding |
| `BindingResult#getFieldValue` | Value for form rendering, which may be rejected input |
| `BindingResult#getModel` | Map containing target and BindingResult for MVC rendering |

**Safety warning:** `getFieldValue()`, `getRawFieldValue()`, `FieldError#getRejectedValue()`, and `BindingResult#getModel()` can expose user input, including private data. They are useful in server-side logic or controlled form rendering, and **should not be serialized verbatim into public error JSON**. Do not treat `getDefaultMessage()` as safe if a custom validator interpolates raw input into the message.

## 4. Hands-On Project Structure

Project runnable with Maven:

~~~text
pom.xml
src/main/java/com/example/bindinglab/
  BindingLabApplication.java
  OrderForm.java
  AddressForm.java
  ItemForm.java
  LabIssue.java
  LabReport.java
  OrderLabController.java
src/test/java/com/example/bindinglab/
  BinderLifecycleTest.java
  OrderLabControllerTest.java
~~~

### 4.1. `pom.xml`

~~~xml
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
    <artifactId>binding-conversion-validation-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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
</project>
~~~

`spring-boot-starter-web` provides Spring MVC; `spring-boot-starter-validation` brings in the Jakarta provider; `spring-boot-starter-test` includes JUnit Jupiter, MockMvc, JSONPath, and Hamcrest. The example does **not** need a database or special security filter registration because it is only a lab; a real product needs authentication/authorization and request size protection.

### 4.2. `BindingLabApplication.java`

~~~java
// src/main/java/com/example/bindinglab/BindingLabApplication.java
package com.example.bindinglab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BindingLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(BindingLabApplication.class, args);
    }
}
~~~

### 4.3. `OrderForm.java` — Top-Level Form

~~~java
// src/main/java/com/example/bindinglab/OrderForm.java
package com.example.bindinglab;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.format.annotation.DateTimeFormat;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;

public class OrderForm {

    @NotBlank
    private String customerName;

    @NotBlank
    @Email
    private String contactEmail;

    @NotNull
    @Min(1)
    private Integer quantity;

    @NotNull
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate deliveryDate;

    @Valid
    private AddressForm address = new AddressForm();

    @Valid
    private List<ItemForm> items = new ArrayList<>();

    public OrderForm() {}

    public String getCustomerName() { return customerName; }
    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }

    public String getContactEmail() { return contactEmail; }
    public void setContactEmail(String contactEmail) {
        this.contactEmail = contactEmail;
    }

    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }

    public LocalDate getDeliveryDate() { return deliveryDate; }
    public void setDeliveryDate(LocalDate deliveryDate) {
        this.deliveryDate = deliveryDate;
    }

    public AddressForm getAddress() { return address; }
    public void setAddress(AddressForm address) {
        this.address = address;
    }

    public List<ItemForm> getItems() { return items; }
    public void setItems(List<ItemForm> items) {
        this.items = items;
    }
}
~~~

The annotations on the DTO have distinct roles:
- `@NotBlank`: constrains the string to be non-null, non-empty, and not whitespace-only.
- `@Email`: constrains email format.
- `@NotNull`: required value; must be combined with `@Min` because `@Min` does not treat null as a violation.
- `@DateTimeFormat(iso=ISO.DATE)`: supports parsing dates from form strings (formatting/conversion), **not** a Bean Validation constraint.
- `@Valid` on address/items: requests cascade validation into the nested object and list elements.
- `Integer`/`LocalDate` preserve null when input cannot be converted, avoiding confusing a default primitive `int=0` with whether the client sent a value.

### 4.4. `AddressForm.java` — Nested Object

~~~java
// src/main/java/com/example/bindinglab/AddressForm.java
package com.example.bindinglab;

import jakarta.validation.constraints.NotBlank;

public class AddressForm {

    @NotBlank
    private String city;

    public AddressForm() {}

    public String getCity() { return city; }
    public void setCity(String city) {
        this.city = city;
    }
}
~~~

### 4.5. `ItemForm.java` — Constrained List Element

~~~java
// src/main/java/com/example/bindinglab/ItemForm.java
package com.example.bindinglab;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class ItemForm {

    @NotBlank
    private String sku;

    @NotNull
    @Min(1)
    private Integer units;

    public ItemForm() {}

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }

    public Integer getUnits() { return units; }
    public void setUnits(Integer units) {
        this.units = units;
    }
}
~~~

`items[0].units=2` requires:
1. Finding the `items` property.
2. Creating/accessing the element at index 0 (if the binder allows auto-grow).
3. Converting the string `"2"` to `Integer`.
4. Assigning the `units` property.
5. Cascading `@Valid` into `ItemForm` to check `@Min(1)`.

If `items[0].sku` is blank, `FieldError#getField()` will carry the corresponding path. The index is necessary information for the frontend to identify the failing row, though for dynamic Map keys containing emails/tokens you must have a policy to mask the key.

## 5. Designing a Public Response to Read BindingResult Without Data Leaks

### 5.1. `LabIssue.java`

~~~java
// src/main/java/com/example/bindinglab/LabIssue.java
package com.example.bindinglab;

public record LabIssue(
        String field,
        String code,
        String stage) {
}
~~~

`stage` is application-defined:
- `BIND_CONVERT`: error originating during binding or type conversion.
- `VALIDATE`: error from a constraint/custom validator.

This is **not** a field name automatically generated by Spring. It is derived from `FieldError#isBindingFailure()` to illustrate the pipeline.

### 5.2. `LabReport.java`

~~~java
// src/main/java/com/example/bindinglab/LabReport.java
package com.example.bindinglab;

import java.util.List;

public record LabReport(
        String status,
        long bindingErrorCount,
        long validationErrorCount,
        int suppressedFieldCount,
        List<LabIssue> issues) {
}
~~~

The report intentionally omits `rejectedValue`, raw error arguments, exception messages, the target object, and suppressed field names. In a real system, issue codes/messages can be translated via `MessageSource`, but this lab focuses on **observing the bind–convert–validate order and BindingResult errors**. Keeping the schema minimal avoids losing focus.

### 5.3. Why Must Suppressed Fields Be Distinguished?

When the binder configures:

~~~java
binder.setAllowedFields(
        "customerName", "contactEmail",
        "quantity", "deliveryDate",
        "address.city",
        "items[*].sku", "items[*].units");
~~~

and the client sends `adminApproved=true`, the field outside the allowlist is ignored. It can appear in `BindingResult#getSuppressedFields()` but **does not automatically create a `FieldError`**. Therefore `hasErrors()==false` does not mean the request sent no blocked fields.

In the demo, the controller returns 400 if `suppressedFieldCount>0`. Do not output the raw suppressed field name: with Map/indexed fields, the name can include client-controlled data.

## 6. Lab Controller: Placing @InitBinder and BindingResult Correctly

### 6.1. `OrderLabController.java`

~~~java
// src/main/java/com/example/bindinglab/OrderLabController.java
package com.example.bindinglab;

import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Comparator;
import java.util.List;
import java.util.Map;

@RestController
public class OrderLabController {

    @InitBinder("orderForm")
    void configure(WebDataBinder binder) {
        binder.setAllowedFields(
                "customerName",
                "contactEmail",
                "quantity",
                "deliveryDate",
                "address.city",
                "items[*].sku",
                "items[*].units");
        binder.setAutoGrowCollectionLimit(8);
    }

    @PostMapping(
            path = "/lab/orders",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> submit(
            @Valid @ModelAttribute("orderForm") OrderForm form,
            BindingResult errors) {

        long bindingErrors = errors.getFieldErrors().stream()
                .filter(FieldError::isBindingFailure)
                .count();
        long validationErrors =
                errors.getErrorCount() - bindingErrors;
        int suppressed = errors.getSuppressedFields().length;

        List<LabIssue> issues = errors.getAllErrors().stream()
                .map(OrderLabController::toPublicIssue)
                .sorted(Comparator.comparing(LabIssue::field)
                        .thenComparing(LabIssue::stage)
                        .thenComparing(LabIssue::code))
                .toList();

        if (errors.hasErrors() || suppressed > 0) {
            return ResponseEntity.badRequest()
                    .body(new LabReport(
                            "REJECTED",
                            bindingErrors,
                            validationErrors,
                            suppressed,
                            issues));
        }

        return ResponseEntity.ok(Map.of(
                "accepted", true,
                "itemCount", form.getItems().size()));
    }

    static LabIssue toPublicIssue(ObjectError error) {
        if (error instanceof FieldError field) {
            boolean binding = field.isBindingFailure();
            return new LabIssue(
                    safeField(field.getField()),
                    binding
                            ? "TYPE_MISMATCH"
                            : publicCode(field.getCode()),
                    binding ? "BIND_CONVERT" : "VALIDATE");
        }

        return new LabIssue(
                "",
                publicCode(error.getCode()),
                "VALIDATE");
    }

    private static String publicCode(String code) {
        if (code == null) {
            return "INVALID_VALUE";
        }

        return switch (code) {
            case "NotBlank", "NotNull" -> "REQUIRED";
            case "Email" -> "INVALID_EMAIL";
            case "Min" -> "BELOW_MIN";
            case "Max" -> "ABOVE_MAX";
            default -> "INVALID_VALUE";
        };
    }

    // Expose only field paths belonging to the lab contract.
    static String safeField(String raw) {
        if (raw == null) {
            return "";
        }

        if (raw.equals("customerName")
                || raw.equals("contactEmail")
                || raw.equals("quantity")
                || raw.equals("deliveryDate")
                || raw.equals("address.city")) {
            return raw;
        }

        for (int i = 0; i < 8; i++) {
            if (raw.equals("items[" + i + "].sku")
                    || raw.equals("items[" + i + "].units")) {
                return raw;
            }
        }

        return "";
    }
}
~~~

**Analyzing the handler lifecycle:**
1. Spring creates an `OrderForm` instance.
2. `WebDataBinder` applies allowed request properties, performing type conversion when needed.
3. `@Valid` causes Spring to run validation on `OrderForm` and nested objects.
4. Because `BindingResult` sits **immediately after** the `@Valid @ModelAttribute` parameter, the handler receives errors inline and decides the response itself.
5. `getFieldErrors()` and `isBindingFailure()` help classify conversion errors.
6. `getAllErrors()` includes both field and global/object errors.
7. `getSuppressedFields()` is read separately, because blocked fields do not necessarily contribute to `getErrorCount()`.
8. The response includes only allowlisted stage/code/field values and counts; **it does not return raw input, the target, or framework exceptions**.

With the current route having no `@Min` directly on a controller method parameter, Spring MVC uses standard object validation. If direct method constraints like `@Min` are added on `@RequestParam`, MVC 6.1+ can use built-in method validation and `HandlerMethodValidationException`; do not conflate that exception type with a `BindingResult` attached to an object argument.

**Do not place `BindingResult` far away from the validated argument.** Correct signature:

~~~java
public ResponseEntity<?> submit(
        @Valid @ModelAttribute("orderForm") OrderForm form,
        BindingResult errors) {
    // ...
}
~~~

If `BindingResult` is omitted, Spring typically throws `MethodArgumentNotValidException` when object validation fails and no other method-validation handler governs it. Placing `BindingResult` after another parameter can prevent Spring from treating it as the form's local errors.

## 7. Standalone Experiment Without HTTP: WebDataBinder

### 7.1. Stages We Invoke Explicitly

A direct experiment:

~~~java
OrderForm target = new OrderForm();
WebDataBinder binder =
        new WebDataBinder(target, "orderForm");

// Register Spring Validator, ConversionService, and binding policy.
binder.bind(propertyValues);    // BIND and CONVERT
BindingResult afterBind = binder.getBindingResult();
binder.validate();              // VALIDATE
BindingResult afterValidate = binder.getBindingResult();
~~~

This is an **illustrative method snippet**, not a standalone Java file. Both `afterBind`/`afterValidate` variables typically reference the same `BindingResult` into which the binder accumulates errors; if you need to compare states **before and after**, capture `getErrorCount()` or snapshot the error list at each point instead of expecting the `afterBind` object to “freeze” at the old state.

In the test below, a helper constructs a binder matching the controller's policy. `DefaultFormattingConversionService` provides default converters/formatters and handles the `@DateTimeFormat` annotation. The validator obtained from the Spring Boot context is registered via `addValidators`.

### 7.2. `BinderLifecycleTest.java`

~~~java
// src/test/java/com/example/bindinglab/BinderLifecycleTest.java
package com.example.bindinglab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.format.support.DefaultFormattingConversionService;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.Validator;
import org.springframework.web.bind.WebDataBinder;

import java.time.LocalDate;
import java.util.Arrays;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class BinderLifecycleTest {

    @Autowired
    Validator springValidator;

    private WebDataBinder newBinder(OrderForm target) {
        WebDataBinder binder =
                new WebDataBinder(target, "orderForm");

        binder.setConversionService(
                new DefaultFormattingConversionService());
        new OrderLabController().configure(binder);
        binder.addValidators(springValidator);

        return binder;
    }

    private MutablePropertyValues validValues() {
        MutablePropertyValues values =
                new MutablePropertyValues();

        values.add("customerName", "Lan");
        values.add("contactEmail", "lan@example.com");
        values.add("quantity", "2");
        values.add("deliveryDate", "2026-12-20");
        values.add("address.city", "Hanoi");
        values.add("items[0].sku", "PEN");
        values.add("items[0].units", "3");

        return values;
    }

    @Test
    void bindConvertsStringValuesBeforeValidation() {
        OrderForm target = new OrderForm();
        WebDataBinder binder = newBinder(target);

        binder.bind(validValues());
        BindingResult result = binder.getBindingResult();

        assertEquals(Integer.valueOf(2),
                target.getQuantity());
        assertEquals(LocalDate.of(2026, 12, 20),
                target.getDeliveryDate());
        assertEquals("Hanoi",
                target.getAddress().getCity());
        assertEquals(1, target.getItems().size());
        assertEquals(Integer.valueOf(3),
                target.getItems().get(0).getUnits());
        assertFalse(result.hasErrors());

        binder.validate();
        assertFalse(result.hasErrors());
    }

    @Test
    void conversionErrorExistsBeforeValidateAndIsPreserved()
            throws Exception {

        MutablePropertyValues values = validValues();
        values.add("quantity", "not-a-number");
        values.add("customerName", "   ");

        WebDataBinder binder = newBinder(new OrderForm());
        binder.bind(values);

        BindingResult result = binder.getBindingResult();
        FieldError conversion =
                result.getFieldError("quantity");

        assertNotNull(conversion);
        assertEquals("typeMismatch", conversion.getCode());
        assertTrue(conversion.isBindingFailure());

        // @NotBlank has NOT run yet when only bind() was called.
        assertFalse(result.hasFieldErrors("customerName"));
        int beforeValidation = result.getErrorCount();

        binder.validate();

        // After validate, the same BindingResult gains additional errors.
        assertTrue(result.getErrorCount() > beforeValidation);
        assertTrue(result.getFieldErrors("customerName").stream()
                .anyMatch(e -> "NotBlank".equals(e.getCode())));
        assertTrue(result.getFieldErrors("quantity").stream()
                .anyMatch(FieldError::isBindingFailure));
    }

    @Test
    void invalidDateIsAlsoBindingAndConversionFailure() {
        MutablePropertyValues values = validValues();
        values.add("deliveryDate", "not-a-date");

        WebDataBinder binder = newBinder(new OrderForm());
        binder.bind(values);

        assertTrue(binder.getBindingResult()
                .getFieldErrors("deliveryDate").stream()
                .anyMatch(FieldError::isBindingFailure));
    }

    @Test
    void nestedConstraintsKeepExactFieldPaths() {
        MutablePropertyValues values = validValues();
        values.add("address.city", "   ");
        values.add("items[0].units", "0");

        WebDataBinder binder = newBinder(new OrderForm());
        binder.bind(values);
        binder.validate();

        BindingResult result = binder.getBindingResult();

        assertTrue(result.getFieldErrors("address.city").stream()
                .anyMatch(e -> "NotBlank".equals(e.getCode())));
        assertTrue(result.getFieldErrors("items[0].units").stream()
                .anyMatch(e -> "Min".equals(e.getCode())));
    }

    @Test
    void suppressedInputDoesNotAutomaticallyCreateFieldError() {
        MutablePropertyValues values = validValues();
        values.add("adminApproved", "true");

        WebDataBinder binder = newBinder(new OrderForm());
        binder.bind(values);
        binder.validate();

        BindingResult result = binder.getBindingResult();
        Set<String> suppressed = Set.copyOf(Arrays.asList(
                result.getSuppressedFields()));

        assertEquals(Set.of("adminApproved"), suppressed);
        assertFalse(result.hasErrors());
    }

    @Test
    void publicIssueMappingIgnoresRawRejectedValue() {
        String sensitive = "CANARY_SECRET_VALUE";
        FieldError raw = new FieldError(
                "orderForm",
                "contactEmail",
                sensitive,
                false,
                new String[]{"Email"},
                null,
                "Unsafe message: " + sensitive);

        LabIssue issue = OrderLabController.toPublicIssue(raw);

        assertEquals("contactEmail", issue.field());
        assertEquals("INVALID_EMAIL", issue.code());
        assertEquals("VALIDATE", issue.stage());
        assertFalse(issue.toString().contains(sensitive));
    }
}
~~~

**The six test methods** in this class cover:
- Data has already been converted before `validate()`.
- Conversion errors exist in `BindingResult` **before** validation.
- Calling `validate()` appends Bean Validation errors to the **same result**.
- An invalid `@DateTimeFormat` produces an error during the binding stage.
- Nested validation preserves exact paths `address.city` and `items[0].units`.
- Suppressed fields are a separate group to inspect; they are not automatically treated as validation errors.
- The public mapper does not emit raw rejected values.

Note that `throws Exception` on one test is just to keep the signature simple; `binder.bind()` in normal flow records type conversion errors into `BindingResult` rather than forcing callers to catch a `ParseException` for every field.

### 7.3. Observed Results in Sequence

With input:

~~~text
customerName="   "
contactEmail="lan@example.com"
quantity="not-a-number"
deliveryDate="2026-12-20"
address.city="Hanoi"
items[0].sku="PEN"
items[0].units="3"
~~~

Logical observations:

| Point in time | What happened | Check |
| --- | --- | --- |
| Before `bind` | Object has unassigned fields | `target.getQuantity()==null` |
| After `bind` | Valid fields were assigned and converted | `deliveryDate` became `LocalDate` |
| After `bind` | `quantity` could not convert | Has `FieldError` `typeMismatch` and `isBindingFailure=true` |
| After `bind` | `customerName` was assigned whitespace string | No `NotBlank` error from validator yet |
| After `validate` | Bean Validation sees `customerName` is whitespace-only | Has `NotBlank` error |
| After `validate` | Prior binding errors are preserved | `quantity` still has binding failure |
| When reading response | Safe code/path/stage are selected | No rejected value |

The table does not promise a **fixed total error count** across all providers and configurations, because `@NotNull` constraints or custom validators may produce additional errors depending on the case. Tests are written against *stable properties* rather than relying on ordering/magic counts.

## 8. HTTP Experiments with MockMvc

### 8.1. Why Are Both Layers Needed?

Direct unit tests on `WebDataBinder` clearly show each individual call. But only integration tests through MVC verify:
- The parameter resolver creates `OrderForm` properly.
- `@InitBinder("orderForm")` is invoked with the right scope.
- Form parameters are converted via MVC's `ConversionService`.
- `@Valid` runs automatically.
- `BindingResult` is passed immediately after the form argument.
- The controller selects status 200/400 properly.
- JSON serialization does not leak sensitive data.

### 8.2. `OrderLabControllerTest.java`

~~~java
// src/test/java/com/example/bindinglab/OrderLabControllerTest.java
package com.example.bindinglab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.hasItems;
import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderLabControllerTest {

    @Autowired
    MockMvc mvc;

    private MockHttpServletRequestBuilder order(
            String name, String quantity, String deliveryDate,
            String city, String units) {

        return post("/lab/orders")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("customerName", name)
                .param("contactEmail", "lan@example.com")
                .param("quantity", quantity)
                .param("deliveryDate", deliveryDate)
                .param("address.city", city)
                .param("items[0].sku", "PEN")
                .param("items[0].units", units);
    }

    @Test
    void validInputIsBoundConvertedAndAccepted()
            throws Exception {

        mvc.perform(order(
                    "Lan", "2", "2026-12-20", "Hanoi", "3"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accepted")
                        .value(true))
                .andExpect(jsonPath("$.itemCount")
                        .value(1));
    }

    @Test
    void quantityParsingFailureIsMarkedBindConvert()
            throws Exception {

        mvc.perform(order(
                    "Lan", "CANARY_BAD_NUMBER",
                    "2026-12-20", "Hanoi", "3"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status")
                        .value("REJECTED"))
                .andExpect(jsonPath("$.bindingErrorCount")
                        .value(1))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("quantity")))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("TYPE_MISMATCH")))
                .andExpect(jsonPath("$.issues[*].stage",
                        hasItem("BIND_CONVERT")))
                .andExpect(content().string(not(
                        containsString("CANARY_BAD_NUMBER"))));
    }

    @Test
    void invalidDateAlsoTriggersBindingFailure()
            throws Exception {

        mvc.perform(order(
                    "Lan", "2", "not-a-date", "Hanoi", "3"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("deliveryDate")))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("TYPE_MISMATCH")));
    }

    @Test
    void validIntegerBelowMinimumIsValidationError()
            throws Exception {

        mvc.perform(order(
                    "Lan", "0", "2026-12-20", "Hanoi", "3"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.bindingErrorCount")
                        .value(0))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("quantity")))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("BELOW_MIN")))
                .andExpect(jsonPath("$.issues[*].stage",
                        hasItem("VALIDATE")));
    }

    @Test
    void nestedInvalidInputsKeepIndexedFieldPaths()
            throws Exception {

        mvc.perform(order(
                    "   ", "2", "2026-12-20", "  ", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[*].field",
                        hasItems(
                                "customerName",
                                "address.city",
                                "items[0].units")))
                .andExpect(jsonPath("$.issues[*].stage",
                        hasItem("VALIDATE")));
    }

    @Test
    void unwantedFormFieldIsSuppressedAndRejected()
            throws Exception {

        mvc.perform(order(
                    "Lan", "2", "2026-12-20", "Hanoi", "3")
                    .param("adminApproved", "CANARY_ADMIN_777"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.suppressedFieldCount")
                        .value(1))
                .andExpect(content().string(not(
                        containsString("CANARY_ADMIN_777"))))
                .andExpect(content().string(not(
                        containsString("adminApproved"))));
    }
}
~~~

**These are 6 integration test methods.** Combined with the 6 `BinderLifecycleTest` methods in section 7, the project has **12 expected JUnit tests**. The exercise focuses on observable framework behavior rather than asserting absolute total error counts in cases where validators might add extra issues.

Test both status 400 *and* the error codes/paths/stages; asserting only HTTP 400 could allow the API to return 400 for the wrong reason or discard useful metadata.

### 8.3. Running the Tests

~~~bash
mvn test
~~~

Run binder lifecycle tests alone:

~~~bash
mvn -Dtest=BinderLifecycleTest test
~~~

Run HTTP integration tests alone:

~~~bash
mvn -Dtest=OrderLabControllerTest test
~~~

**Expectation:** 12 tests PASS if source files, packages, and dependencies are placed properly. This is a static expectation from the illustrative code, **not a certification that Maven was executed**. When CI runs, take actual results from JUnit/Surefire reports, inspect stack traces, and compare actual field errors.

## 9. Trying with curl: Seeing the Difference Between Convert and Validate

Start the web server:

~~~bash
mvn spring-boot:run
~~~

### 9.1. Valid Case

~~~bash
curl -i -X POST http://localhost:8080/lab/orders \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "customerName=Lan" \
  --data-urlencode "contactEmail=lan@example.com" \
  --data-urlencode "quantity=2" \
  --data-urlencode "deliveryDate=2026-12-20" \
  --data-urlencode "address.city=Hanoi" \
  --data-urlencode "items[0].sku=PEN" \
  --data-urlencode "items[0].units=3"
~~~

Expected response:

~~~json
{"accepted":true,"itemCount":1}
~~~

The order of JSON object keys is not a contract. What is notable: quantity and date were converted into `Integer`/`LocalDate` before the controller ran, even though the HTTP form only sends text.

### 9.2. Type Mismatch

~~~bash
curl -i -X POST http://localhost:8080/lab/orders \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "customerName=Lan" \
  --data-urlencode "contactEmail=lan@example.com" \
  --data-urlencode "quantity=CANARY_BAD_NUMBER" \
  --data-urlencode "deliveryDate=2026-12-20" \
  --data-urlencode "address.city=Hanoi" \
  --data-urlencode "items[0].sku=PEN" \
  --data-urlencode "items[0].units=3"
~~~

Expected HTTP 400 response contains at least one issue:

~~~json
{
  "field": "quantity",
  "code": "TYPE_MISMATCH",
  "stage": "BIND_CONVERT"
}
~~~

This JSON snippet is **one issue extracted from `issues`**, not the entire response. `CANARY_BAD_NUMBER` must not appear in any field of the response.

### 9.3. Constraint Violation

Change to:

~~~text
quantity=0
~~~

Now conversion succeeds, but `@Min(1)` fails. HTTP 400 contains the issue:

~~~json
{
  "field": "quantity",
  "code": "BELOW_MIN",
  "stage": "VALIDATE"
}
~~~

This distinction lets the client tell “please enter a valid number” apart from “the number must be within the allowed range”, while avoiding dependence on the provider's English error text.

### 9.4. Unparseable Date

~~~text
deliveryDate=2026-19-77
~~~

`@DateTimeFormat(iso=ISO.DATE)` requires a corresponding valid date. The parser cannot construct a `LocalDate`, so a binding/conversion error occurs, typically with code `typeMismatch`. If an ISO date is valid syntactically but disallowed by business rules (e.g., must be after today), you need **a different constraint or service rule**—do not confuse a parse error with a business error.

### 9.5. Submitting an Out-of-Contract Field

~~~text
adminApproved=true
~~~

`@InitBinder` allowlisted the fields. Fields outside the list are suppressed; `BindingResult#getSuppressedFields()` contains that name, yet `hasErrors()` may remain false. The demo controller proactively returns HTTP 400 when `suppressedFieldCount>0`, and omits raw field names from the body. This is an application policy, not automatic 400 behavior for every suppressed field.

## 10. Reading BindingResult Deeply After Bind/Validate

### 10.1. Getting All Errors

~~~java
BindingResult result = binder.getBindingResult();

boolean hasErrors = result.hasErrors();
int total = result.getErrorCount();
int fieldCount = result.getFieldErrorCount();
int globalCount = result.getGlobalErrorCount();
~~~

The snippet above is **a snippet inside a method**, not a standalone Java file. `getErrorCount()` reflects registered `ObjectError`/`FieldError` instances and does not automatically include suppressed fields.

### 10.2. Distinguishing Field and Global Errors

~~~java
for (ObjectError error : result.getAllErrors()) {
    if (error instanceof FieldError field) {
        String path = field.getField();
        String code = field.getCode();
        boolean conversion = field.isBindingFailure();
        // Process internally only or map to a safe DTO.
    } else {
        // Object-level error, typically without a specific field path.
    }
}
~~~

Object-wide errors can appear when a class-level constraint checks multiple properties, such as `startDate <= endDate`. Calling only `getFieldErrors()` can drop global errors. Conversely, a specific form error may carry a nested path such as `items[0].units`.

### 10.3. `getCode()` vs `getCodes()`

A `FieldError` may hold:
- `getCode()` = `Min`.
- `getCodes()` = detailed list depending on `MessageCodesResolver`, e.g. `Min.orderForm.quantity`, `Min.quantity`, `Min.java.lang.Integer`, `Min`.

Use `getCodes()` so Spring `MessageSource` finds the best translation by precedence, but **do not expose all** codes in a public API: they can reveal internal object/class names. In the demo, `publicCode` maps `Min → BELOW_MIN` and `typeMismatch → TYPE_MISMATCH`.

### 10.4. `getFieldValue()` and Rejected Values

`BindingResult#getFieldValue("quantity")` can return the formatted value or the rejected input so the UI can repopulate the form. `FieldError#getRejectedValue()` can contain `CANARY_BAD_NUMBER` itself or other sensitive data. The lab only reads **safe metadata** such as `isBindingFailure`, `getCode`, and an allowlisted field path.

If the application is a server-side HTML form, deciding whether to “repopulate” input must account for passwords/tokens/PII and access permissions; do not use that same mechanism as a default JSON error API. Passwords/secrets should never be echoed back from the server.

### 10.5. `getModel()` and MVC View Rendering

`BindingResult#getModel()` builds a Map with the target object and the corresponding entry for BindingResult (keyed by convention `BindingResult.MODEL_KEY_PREFIX`). It is intended for form/view rendering, **not as an API error DTO**. Serializing this entire Map in a REST response can leak the entire model/target.

### 10.6. Snapshotting Errors Before/After Validate

Because `BindingResult` is an accumulating object, to observe the actual increase in errors:

~~~java
binder.bind(values);
int afterBind = binder.getBindingResult().getErrorCount();

binder.validate();
int afterValidate =
        binder.getBindingResult().getErrorCount();

System.out.println(afterBind);
System.out.println(afterValidate);
~~~

This is an **illustrative snippet**, without fixed stdout: error counts depend on the input and constraint provider. Do not store two `BindingResult` variables and assume one object is a pre-validation snapshot; store the count or copy an immutable list at that moment.

## 11. Important Differences in Spring MVC

### 11.1. `BindingResult` Immediately After `@Valid @ModelAttribute`

Correct:

~~~java
@PostMapping("/lab/orders")
public ResponseEntity<?> save(
        @Valid @ModelAttribute("orderForm") OrderForm form,
        BindingResult result) {
    // Controller decides the error response itself.
    return ResponseEntity.ok().build();
}
~~~

This is an **illustrative signature**, not to be added as a second endpoint in the existing runnable project. `BindingResult` sits immediately after the relevant form argument.

Without a local `BindingResult`, Spring MVC normally throws `MethodArgumentNotValidException` for object validation errors and the framework handles it via an exception resolver/`@ControllerAdvice`. For methods with direct `@Constraint` annotations on parameters/return values, built-in method validation from Spring 6.1 may apply; in that case `HandlerMethodValidationException` carries `ParameterValidationResult`s.

### 11.2. `@RequestBody` Takes a Different Conversion Path

~~~java
@PostMapping("/lab/json")
public void saveJson(@Valid @RequestBody OrderForm input) {
    // ...
}
~~~

This is also an **illustrative snippet**, not part of the runnable project. For JSON, Spring reads the body via `HttpMessageConverter`/Jackson. An input:

~~~json
{"quantity": "CANARY_BAD_NUMBER"}
~~~

may fail to deserialize into Integer and raise `HttpMessageNotReadableException` **before Bean Validation**. This is not the same kind of `typeMismatch` FieldError as a `@ModelAttribute` form. Once JSON has been deserialized into an object and fails constraints, `MethodArgumentNotValidException` may occur.

**Do not use `@InitBinder#setAllowedFields` as a whitelist for Jackson JSON**. Protect JSON using a dedicated request DTO, Jackson configuration, and service authorization.

### 11.3. Standalone `@RequestParam`/`@PathVariable`

When a controller receives:

~~~java
@GetMapping("/units")
public int units(@RequestParam int quantity) {
    return quantity;
}
~~~

`quantity=abc` can lead to `MethodArgumentTypeMismatchException` from the argument resolver, **not necessarily appearing in a form object's BindingResult**. Test the exact request-receiving path before writing an error handler.

### 11.4. `@Validated` for Groups and Method Validation

`@Validated(Create.class)` can select constraint groups when validating an argument; meanwhile, controller-class-level `@Validated` can route method validation to AOP. In Spring Framework 6.1+, when you want built-in MVC method validation, the documentation recommends omitting class-level `@Validated` on controllers if it was only there for method validation. Do not mix a command object's `BindingResult` with `ConstraintViolationException` from service/AOP and treat them as identical.

## 12. Property Binding Security in the Lab

The example uses a **separate form DTO** containing no `role`/`ownerId`/`adminApproved` and an explicit `setAllowedFields`. Benefits:
- Adding a new setter to an entity does not automatically open a form input.
- Unapproved paths are suppressed.
- Nested/indexed fields are permitted only per the allowlist.
- The controller can reject requests containing extra fields.

Notes:
1. `setAllowedFields` controls property binding; it does **not** perform authorization.
2. Constructor binding also has an input surface matching constructor args; adding a component to a record must be reviewed.
3. `setDeclarativeBinding(true)` can be used to lock down property binding when no allowed fields exist, but it **does not automatically allowlist constructor parameters**.
4. `setAutoGrowCollectionLimit(8)` bounds certain list auto-grow cases; it does not replace HTTP body size limits or JSON array limits.
5. Map keys can contain emails/tokens; never log/echo raw rejected/suppressed paths.
6. Validation only checks data validity; permission to modify an owner/status must be verified by the service.
7. `getSuppressedFields()` can reveal user-supplied paths, so the demo returns only the **count** of suppressed fields.

If multilingual messages must be exposed publicly, use `MessageSource` with allowlisted public error codes; do not treat an unvetted `FieldError#getDefaultMessage()` as always safe.

## 13. Extended Experiment: Custom Converters and Formatters

In the main example, Spring handles:
- `String → Integer` via built-in converters/editors.
- `String → LocalDate` via formatting/conversion supporting `@DateTimeFormat`.

If the application has domain-specific types like `Sku` or `Money`, you can register a `Converter<String,Sku>`:

~~~java
// Illustrative snippet (requires defining class Sku and registering it).
import org.springframework.core.convert.converter.Converter;

final class SkuConverter implements Converter<String, Sku> {
    @Override
    public Sku convert(String source) {
        return new Sku(source.strip().toUpperCase());
    }
}
~~~

This is **not a standalone project file**; `Sku` is a hypothetical domain type in the illustration. To actually use it, define `Sku` and register the converter with `ConversionService` or MVC `FormatterRegistry`. Test all of:
- Valid input converts as expected.
- Invalid input produces a binding failure rather than silently turning into another value.
- The converter must not be used for permission checks or fetching sensitive data.
- The validator checks constraints on the object **after conversion**.
- With `Formatter<T>`, test `parse`/`print` by `Locale` and round-trip behavior.

Do not try to turn a converter's `Exception#getMessage()` into public error text: it may contain raw input. Publishing the code `TYPE_MISMATCH` and a safe path is sufficient for the lab.

## 14. Common Error Table and Self-Diagnosis

| Symptom | Cause | Fix / Experiment |
| --- | --- | --- |
| Form quantity stays String | DTO declared wrong type or failed to bind | Check getters/setters and property name |
| `quantity=abc` returns status 500 | Wrong exception handler or converter threw outside pipeline | Test `BindingResult`/argument resolver and security logs |
| `quantity=0` has no `Min` error | Validation did not run or `@Valid`/validator is missing | Call `binder.validate()` or inspect MVC signature |
| `@DateTimeFormat` is ignored | Using a conversion service without formatting annotation support | Use `DefaultFormattingConversionService` or MVC config |
| `deliveryDate=bad` reports constraint instead of parse | Confusing type conversion with validator | Check `FieldError#isBindingFailure()` |
| Nested `address.city` not validated | Missing `@Valid` on address | Add cascade validation |
| Indexed `items[0].units` missing | List element not created / missing setter / not in allowed fields | Check auto-grow, field name, and allowlist |
| `result.hasErrors()` false despite unknown field sent | Suppressed field is not automatically a FieldError | Read `getSuppressedFields()` separately |
| Controller does not receive `BindingResult` | Placed in wrong position or using different method validation | Place immediately after the annotated model attribute |
| `getErrorCount()` unchanged after validate | DataBinder has no validator registered or input is valid | Check `addValidators` and test inputs |
| Index lost when rendering errors | Mapper shortened path to trailing field name | Keep nested/indexed path after allowlisting |
| JSON type error has no `FieldError` | Jackson deserialization failed before validation | Handle `HttpMessageNotReadableException` |
| Form type error has no public code | Returning raw Spring ObjectError | Map `typeMismatch→TYPE_MISMATCH` |
| `getDefaultMessage()` contains raw input | Unsafe custom validator or message interpolation | Select messages from a trusted catalog |
| Backend echoes entire form object | Serializing target/`getModel()` into error response | Use a dedicated public issue DTO |
| Binder unit test passes, HTTP fails | `@InitBinder`/MVC config differs from test setup | Add MockMvc integration tests |
| Duplicate errors on a field | Conversion + constraint or multiple constraints | Inspect stage/code separately; avoid brittle exact counts |
| Different locale gives different message | MessageSource resolves by request locale | Test stable codes/paths and localized messages |
| Model change opens new field | Mutable entity bound directly | Dedicated input DTO + allowlist + regression tests |

## 15. Sequential Self-Practice Exercises

1. Run the valid binder test and place breakpoints right before/after `binder.bind`. Inspect the runtime types of `quantity` and `deliveryDate`, not just the original string values.
2. Change quantity to `"abc"`. Read `getFieldError("quantity").getCode()` and `isBindingFailure()` **before `validate()`**.
3. Change quantity to `"0"`, compare before/after validate to prove conversion succeeded while `Min` failed.
4. Send `customerName="  "`. Prove the binder assigns the string while `@NotBlank` only reports an error after validation.
5. Send `deliveryDate="2026-13-40"` and a valid ISO date, comparing `LocalDate` vs binding failure.
6. Add `items[1].sku=""`, `items[1].units=0`; verify indexed paths and the auto-grow limit.
7. Add a class-level constraint to `OrderForm` to produce a global `ObjectError`; compare `getAllErrors()` and `getFieldErrors()`.
8. Add an out-of-allowlist field in an HTTP request; verify `getSuppressedFields()` and that the controller returns 400 even though `hasErrors()` can be false.
9. Remove `BindingResult` from the handler signature in a test branch, observe the exception MVC creates, then restore it.
10. Write a `@RequestBody` JSON endpoint and send `quantity="abc"` to distinguish Jackson deserialization errors from form typeMismatch.
11. Create a custom `Converter<String,Sku>`, testing successful parse, failed parse, and public error mapping.
12. Test `@DateTimeFormat` under `en-US` and `vi-VN`; when choosing ISO, the date wire format must remain stable per contract.
13. Put sensitive data into a mock `FieldError` and verify the public response does not contain that marker.
14. Compare `BindingResult#getModel()` with the public DTO: use getModel only for controlled view rendering, never return the raw target.
15. Add a security/authorization test ensuring the form cannot set `adminApproved` or `ownerId` on its own.

## 16. Checklist Before Taking the Pipeline to a Production API

- [ ] Dedicated input DTO, never bind directly to a JPA/domain entity.
- [ ] `@ModelAttribute` and `@RequestBody` tested as **two distinct pipelines**.
- [ ] Converters/formatters have dedicated tests for valid input, wrong types, boundaries, and Locale where applicable.
- [ ] `@Valid` and nested `@Valid` placed properly; `@NotNull` present where nullable types are required.
- [ ] When using `DataBinder` directly, call `bind` then `validate` and inspect `BindingResult`.
- [ ] In MVC, place `BindingResult` immediately after the validated form argument when handling locally.
- [ ] Test inputs `abc` vs `0` to distinguish `typeMismatch` and `Min`.
- [ ] Do not substitute `getErrorCount()` for `getSuppressedFields()`.
- [ ] Use `getAllErrors()` when both field and global violations are needed.
- [ ] Nested/indexed paths preserved accurately, while canonicalizing Map keys if sensitive.
- [ ] Never return rejected values, raw exception messages, target objects, `getModel()`, or full Spring errors.
- [ ] Public error codes are stable; messages are resolved from `MessageSource` when multilingual.
- [ ] Do not use validation as authorization; permission to modify objects/roles/owners lives in the service layer.
- [ ] Both binder unit tests and HTTP integration tests run in CI.
- [ ] Record actual test pass/fail counts from Maven/JUnit; do not treat expected descriptions as executed results.
- [ ] When upgrading Spring/Jakarta providers, re-run regression tests for binding order, conversion, validation, and exception mapping.

## 17. Summary and References

Three lines worth remembering:

~~~text
bind(values)   = resolve field + convert type + assign or record binding error
validate()     = check constraints on target + record validation error
BindingResult  = single place to read both error kinds plus suppressed fields
~~~

**The essence of the lesson:** an HTTP request does not jump straight from String to “valid/invalid”. Spring must locate the property, convert it to a Java type, and only then apply the corresponding constraints. `BindingResult` lets you inspect each discrepancy without guessing from a single exception message.

Official documentation:
- Spring Framework 6.2 — Data Binding: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html
- Spring Framework 6.2 — Java Bean Validation, Configuring a DataBinder: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 — @ModelAttribute: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 — @InitBinder: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework 6.2 — MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — MVC Type Conversion: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/typeconversion.html
- Spring Framework 6.2 — DataBinder Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html
- Spring Framework 6.2 — BindingResult Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html
- Spring Framework 6.2 — FieldError Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/FieldError.html
- Spring Framework 6.2 — DefaultFormattingConversionService Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/format/support/DefaultFormattingConversionService.html
- Spring Boot 3.5 — Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
