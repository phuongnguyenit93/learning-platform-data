# `reject` and `rejectValue`: Error Codes, Arguments, and Default Messages in Spring Framework

In Spring Framework, `Errors` is the interface for recording and querying errors on **an object being validated**. The two methods `reject(...)` and `rejectValue(...)` allow a validator to proactively add errors to an `Errors` instance without throwing an exception whenever data is invalid. They store **structured error information** so the application can look up messages, localize them, display them, and decide whether to proceed with business logic.

This article focuses on using both methods accurately, especially the three key components: **`errorCode`, `errorArgs`, and `defaultMessage`**. The examples use Java 17 and Spring Framework 6.x; the concepts also apply to Spring MVC through `BindingResult`.

## 1. Where `reject` and `rejectValue` Fit in the Validation Flow

`Errors` lives in the `org.springframework.validation` package. `BindingResult` is an interface that extends `Errors` while also providing binding-related information such as rejected values (`rejectedValue`), suppressed fields, and the error model for rendering views.

A common flow:

```text
HTTP request / Java object
             |
             v
    Data binding / conversion
             |
             v
       Target object
             |
             v
      Validator.validate(target, errors)
             |
      +------+------+
      |             |
      v             v
 errors.reject    errors.rejectValue
 (whole object)     (one field)
      |             |
      +------+------+
             v
  Errors / BindingResult stores ObjectError and FieldError
             |
             v
  Check hasErrors(), getAllErrors(), ...
             |
             v
  Translate messages with MessageSource when needed
             |
             v
  Form/API response or allow business logic to proceed
```

Distinguish two points in time: type-conversion errors from **data binding** may be recorded before the validator runs (for example, the string `"abc"` failing to convert to `int`); business errors are created by the validator using `reject`/`rejectValue`. A single `BindingResult` can hold both.

Calling `reject(...)` **does not modify** the target object; calling `rejectValue(...)` **does not auto-correct** the field value. These are error-recording operations—not binding, data mutation, throwing an HTTP exception, or sending an immediate response.

## 2. Differences Between `reject` and `rejectValue`

| Criterion | `errors.reject(...)` | `errors.rejectValue(...)` |
| --- | --- | --- |
| Scope | Error for the **entire object** (global/object error) | Error attached to **a field/path** on the object |
| Typical cases | Start date after end date; two conflicting fields; order not allowed | `age` out of range; invalid `email` format; invalid `lines[0].quantity` |
| Error object | `ObjectError` | `FieldError` (a subtype of `ObjectError`) |
| How to read | `getGlobalErrors()`, `getGlobalError()` | `getFieldErrors()`, `getFieldError("age")` |
| Has a field name? | No; attached to the object name | Yes; `FieldError.getField()` returns the path |
| Suggested codes | `order.invalidDateRange`, `booking.unavailable` | `quantity.range`, `email.invalid` |
| Arguments and fallback | Yes | Yes |

For example, checking the validity of a single property:

```java
if (form.getQuantity() <= 0) {
    errors.rejectValue(
        "quantity",
        "quantity.positive",
        "Quantity must be greater than 0"
    );
}
```

If the rule involves multiple properties:

```java
if (form.getStartDate().isAfter(form.getEndDate())) {
    errors.reject(
        "dateRange.invalid",
        "Start date must not be after end date"
    );
}
```

Both snippets above are **illustrations inside a validator**, assuming `form` has the corresponding getters and `errors` is a valid `Errors` instance. For cross-field errors, you can attach the error to one field so the UI highlights it, but `reject` more accurately expresses errors that belong to **the relationship between fields or the whole object**.

## 3. Exact API Overloads

`Errors` defines these method overloads:

```java
// Global error:
void reject(String errorCode);
void reject(String errorCode, String defaultMessage);
void reject(String errorCode, Object[] errorArgs, String defaultMessage);

// Field error:
void rejectValue(String field, String errorCode);
void rejectValue(String field, String errorCode, String defaultMessage);
void rejectValue(
    String field,
    String errorCode,
    Object[] errorArgs,
    String defaultMessage
);
```

These are **conceptual signatures** for learning the API, not standalone source code: in recent Spring versions, several parameters/overloads allow `null`, and some overloads have default implementations on the interface.

Meaning of each argument:

- `field`: name of the property being checked, e.g. `"quantity"`, `"address.city"`, `"lines[1].sku"`. The `reject` method has no `field` parameter.
- `errorCode`: code indicating the cause, e.g. `"quantity.range"`. Typically this is a **message key**, not text displayed directly.
- `errorArgs`: object array used to substitute placeholders such as `{0}` and `{1}` in message templates via `MessageFormat`. Pass `null` when no arguments are needed.
- `defaultMessage`: fallback text when no matching message key is found via `MessageSource`. You can pass `null` if the application does not need a fallback, though you must then handle lookup misses.
- `getObjectName()` on `Errors` returns the root object name that Spring attaches to the error metadata, e.g. `"bookingForm"`.

Fullest example of each kind:

```java
errors.reject(
    "booking.unavailable",
    new Object[] { "VIP" },
    "Package {0} is currently unavailable"
);

errors.rejectValue(
    "quantity",
    "quantity.range",
    new Object[] { 1, 10 },
    "Valid quantity is from {0} to {1}"
);
```

These two calls add errors without immediately consulting `MessageSource`. Selecting the language and substituting placeholders into strings usually happens during the **message resolution** step in the view/API layer or when calling `messageSource.getMessage(error, locale)`.

### 3.1. Why use error codes instead of writing Vietnamese text directly?

Suppose the code `quantity.range` is used for both Vietnamese and English:

```properties
# messages_vi.properties
quantity.range.bookingForm.quantity=Số lượng phải từ {0} đến {1}
quantity.range=Số lượng nằm ngoài giới hạn
```

```properties
# messages_en.properties
quantity.range.bookingForm.quantity=Quantity must be between {0} and {1}
quantity.range=Quantity is outside the allowed range
```

The snippets above are **example resource bundle contents**, not mandatory project configuration. When the basename is configured as `messages` with a compatible message resolver, the same `errorCode` yields results matching `Locale`. Do not put translated sentences into `errorCode`, because doing so makes it hard to categorize errors, translate, revise wording, and extend the code structure.

### 3.2. How should error codes be named?

It is best to choose codes that express specific, stable rules:

| Code | Corresponding rule |
| --- | --- |
| `required` or `field.required` | Required value |
| `quantity.range` | Allowed quantity range |
| `booking.unavailable` | Unsuitable booking status |
| `dateRange.invalid` | Conflicting date range |
| `email.duplicate` | Email already exists per application rules |
| `order.line.limit` | Order line count exceeds limit |

A validator can reuse the same code across multiple objects; `MessageCodesResolver` adds object/field context to pick a specific message. Do not rely on the string code automatically equating to an HTTP status or a published public API error code.

## 4. How Does Spring Expand `errorCode` into Message Codes?

When using a standard `BindingResult` implementation such as `BeanPropertyBindingResult`, Spring typically uses `DefaultMessageCodesResolver` to build a **list of candidate codes** from the initial `errorCode`.

For example, if the object name is `bookingForm` and you call:

```java
errors.reject("booking.unavailable", null, "Cannot make reservation");
```

The global error receives codes ordered from specific to general:

```text
booking.unavailable.bookingForm
booking.unavailable
```

If you call:

```java
errors.rejectValue(
    "quantity",
    "quantity.range",
    new Object[] { 1, 10 },
    "Valid quantity is from {0} to {1}"
);
```

And the `quantity` field has type `int`, the candidate codes are typically:

```text
quantity.range.bookingForm.quantity
quantity.range.quantity
quantity.range.int
quantity.range
```

Spring tries codes from **most specific to most general**, so `quantity.range.bookingForm.quantity` takes precedence over `quantity.range`. The exact type variant (`int` vs `java.lang.Integer`) depends on the declared Java field type; the example above assumes primitive `int`.

**For nested paths/indexed fields**, the code list can be longer. For instance, `lines[0].quantity` may include index-specific variants as well as index-less general variants (`lines.quantity`), allowing one message to apply to every row. The count, order, and formatting of codes change if a different `MessageCodesResolver` configuration is used; do not hardcode an assumption that every field error has exactly four codes.

Distinguish:

- `errorCode` is the string passed by the validator author, e.g. `quantity.range`.
- `ObjectError.getCodes()` or `FieldError.getCodes()` is the **array of candidate codes** stored by Spring for message lookup.
- `getCode()` returns a single representative code per the API and does not show the full precedence list. To inspect details or test fallback behavior, check `getCodes()`.
- `MessageSource` picks a message using the **candidate list and Locale**, rather than printing `errorCode` to the screen by default.

## 5. `errorArgs` and Argument Substitution

`errorArgs` is an `Object[]` corresponding to placeholders `{0}`, `{1}`, ... in the message string. Example:

```java
errors.rejectValue(
    "quantity",
    "quantity.range",
    new Object[] { 1, 10 },
    "Quantity must be from {0} to {1}"
);
```

The resolved message can be:

```text
Quantity must be from 1 to 10
```

If the resource bundle configures:

```properties
quantity.range.bookingForm.quantity=Quantity min {0}, max {1}
```

then for the same error, message lookup will prefer:

```text
Quantity min 1, max 10
```

**Arguments are passed positionally, not by name.** If you reverse the order to `new Object[] { 10, 1 }`, the displayed sentence will be wrong even though the error code itself is right.

### 5.1. Arguments containing translatable field labels

`errorArgs` can also contain an object implementing `MessageSourceResolvable` to interpolate **another message**, such as a field label. This is useful for sentences like `"Field 'Quantity' must be from 1 to 10"`.

```java
import org.springframework.context.support.DefaultMessageSourceResolvable;

Object quantityLabel = new DefaultMessageSourceResolvable(
    "label.bookingForm.quantity",
    "Quantity"
);

errors.rejectValue(
    "quantity",
    "quantity.range",
    new Object[] { quantityLabel, 1, 10 },
    "{0} must be from {1} to {2}"
);
```

This code snippet illustrates creating a resolvable argument. With `label.bookingForm.quantity=Quantity` and `quantity.range.bookingForm.quantity={0} must be from {1} to {2}`, `MessageSource` can produce a complete localized sentence. In a real project, the resolver configuration and placeholder construction must be consistent.

### 5.2. `MessageFormat` has its own rules

Placeholders use `java.text.MessageFormat` syntax. This implies:

1. `{0}` is the first argument, `{1}` is the second. Missing arguments prevent the complete sentence from formatting as expected.
2. Single quotes act as escape delimiters in `MessageFormat`: if a message contains an apostrophe/single quote, escape it properly (usually two single quotes `''` to output one `'`).
3. Locale-aware number/date formatting can be used inside patterns, but test it in practice instead of formatting numbers to strings yourself and assuming every locale matches.
4. Arguments may originate from the client. Do not use `errorArgs` to build unescaped HTML and embed it directly in a page; templates/views must escape output.

If you only have a static message without placeholders, use the shorter `reject("code", "Default")` or `rejectValue("field", "code", "Default")` overloads for readability.

## 6. The Actual Role of `defaultMessage`

When no matching code is found, `MessageSource` can use the `defaultMessage` stored inside `ObjectError`/`FieldError`.

Example:

```java
errors.rejectValue(
    "coupon",
    "coupon.unusable",
    new Object[] { "SAVE" },
    "Code {0} was not accepted"
);
```

If no matching key exists in the message source, the result after message resolution may be:

```text
Code SAVE was not accepted
```

**`getDefaultMessage()` is not the same as the resolved display message.** It typically returns the fallback pattern stored with the error, such as `"Code {0} was not accepted"`. To apply `Locale`, substitute arguments, and prioritize resource bundles, use `MessageSource.getMessage(error, locale)` (since `ObjectError` is a `MessageSourceResolvable`) or Spring MVC's corresponding error-rendering mechanism.

If neither a message key nor a fallback is available, message lookup may throw `NoSuchMessageException` (depending on the overload/configuration). Do not rely on Spring automatically displaying `errorCode` as a user-friendly sentence.

### 6.1. Fallbacks must not hide configuration mistakes

A valid fallback keeps the UI showing a message when a language file is missing; however, it does not prove that keys were properly translated. When localization is a product requirement, test both the default language and at least one secondary language to catch missing keys.

Never place sensitive information into `defaultMessage` (personal emails, tokens, exception traces, SQL), because the message can end up in responses/UI or logs if used carelessly.

## 7. Standalone Java 17 Example: Global Error, Field Error, Args, and Fallback

This example uses `BeanPropertyBindingResult` to create an error container for `BookingForm` and `StaticMessageSource` to simulate an in-memory resource bundle. No Spring MVC startup or web server is needed. This example focuses on **registering errors and resolving messages**, without HTTP binding or database writes.

Create the directory layout:

```text
errors-demo/
├── pom.xml
└── src/main/java/example/RejectDemo.java
```

`pom.xml` (Java 17, Spring Framework 6.2.10):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>errors-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
        <configuration>
          <mainClass>example.RejectDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

`src/main/java/example/RejectDemo.java`:

```java
package example;

import java.util.Locale;

import org.springframework.context.support.StaticMessageSource;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;

public class RejectDemo {

    public static class BookingForm {
        private int quantity = 0;
        private String coupon = "SAVE";

        public int getQuantity() { return quantity; }
        public void setQuantity(int quantity) { this.quantity = quantity; }

        public String getCoupon() { return coupon; }
        public void setCoupon(String coupon) { this.coupon = coupon; }
    }

    public static void main(String[] args) {
        BookingForm form = new BookingForm();
        BeanPropertyBindingResult errors =
            new BeanPropertyBindingResult(form, "bookingForm");

        errors.rejectValue(
            "quantity",
            "quantity.range",
            new Object[] { 1, 10 },
            "Số lượng phải từ {0} đến {1}"
        );

        errors.reject(
            "booking.unavailable",
            new Object[] { "VIP" },
            "Gói {0} không khả dụng"
        );

        errors.rejectValue(
            "coupon",
            "coupon.unusable",
            new Object[] { "SAVE" },
            "Mã {0} chưa được chấp nhận"
        );

        Locale vi = Locale.forLanguageTag("vi");
        StaticMessageSource messages = new StaticMessageSource();

        messages.addMessage(
            "quantity.range.bookingForm.quantity",
            vi,
            "Số lượng hợp lệ: từ {0} đến {1}"
        );
        messages.addMessage(
            "booking.unavailable.bookingForm",
            vi,
            "Gói {0} đã hết chỗ"
        );
        // Intentionally omit a message for coupon.unusable
        // to demonstrate that defaultMessage is used.

        FieldError quantity = errors.getFieldError("quantity");
        ObjectError booking = errors.getGlobalError();
        FieldError coupon = errors.getFieldError("coupon");

        System.out.println(quantity.getCodes()[0]);
        System.out.println(booking.getCodes()[0]);
        System.out.println(messages.getMessage(quantity, vi));
        System.out.println(messages.getMessage(booking, vi));
        System.out.println(messages.getMessage(coupon, vi));
        System.out.println(errors.getGlobalErrorCount());
        System.out.println(errors.getFieldErrorCount());
        System.out.println(errors.hasErrors());
    }
}
```

Run from the `errors-demo` directory:

```bash
mvn -q compile exec:java
```

Expected `stdout` (excluding Maven logs if your environment prints extra):

```text
quantity.range.bookingForm.quantity
booking.unavailable.bookingForm
Số lượng hợp lệ: từ 1 đến 10
Gói VIP đã hết chỗ
Mã SAVE chưa được chấp nhận
1
2
true
```

Explanation:

1. `getCodes()[0]` for the field prioritizes `quantity.range.bookingForm.quantity`; the global error prioritizes `booking.unavailable.bookingForm`.
2. `StaticMessageSource` finds both specific keys and substitutes the arguments at `{0}`, `{1}`.
3. There is no message for `coupon.unusable` or its variants; `defaultMessage` is used and `"SAVE"` is inserted into `{0}`.
4. There is **one global error** and **two field errors**; `hasErrors()` is `true`.
5. `rejectValue` does not change `BookingForm.quantity` from 0 to another number; the error is only stored in `BeanPropertyBindingResult`.
6. The demo uses a single public class `RejectDemo` with `BookingForm` as a nested class so all Java code fits in one properly named file; the `spring-context` Maven dependency pulls in the required Spring validation components.

In real applications, replace `StaticMessageSource` with a Spring-configured `MessageSource` backed by resource bundles; avoid creating or loading a new message source per request.

## 8. Writing a `Validator` Using Both Methods

A Spring Core validator uses the `org.springframework.validation.Validator` interface with `supports(Class<?>)` and `validate(Object, Errors)`. Example:

```java
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public class BookingValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return BookingForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        BookingForm form = (BookingForm) target;

        if (form.getQuantity() < 1 || form.getQuantity() > 10) {
            errors.rejectValue(
                "quantity",
                "quantity.range",
                new Object[] { 1, 10 },
                "Quantity must be from {0} to {1}"
            );
        }

        if ("VIP".equals(form.getPackageName())
                && form.isPromotionClosed()) {
            errors.reject(
                "booking.unavailable",
                new Object[] { "VIP" },
                "Package {0} cannot be booked right now"
            );
        }
    }
}
```

This is an **illustrative snippet requiring integration**: `BookingForm` in this validator needs `getPackageName()` and `isPromotionClosed()`, and must be defined in the right package/imports. It is not a drop-in continuation of the demo in Section 7. Object-wide rules use `reject`; the `quantity`-specific rule uses `rejectValue`.

Do not call `reject(...)` with an error code expecting it to create a `FieldError` automatically; and do not call `rejectValue(...)` with a nonexistent field name expecting Spring to silently ignore it. Accessing an invalid property path or mismatched target can cause property-access failures depending on the implementation.

### 8.1. Helper for required fields

Spring provides `ValidationUtils.rejectIfEmpty(...)` and `ValidationUtils.rejectIfEmptyOrWhitespace(...)` to avoid repeating blank-string checks:

```java
ValidationUtils.rejectIfEmptyOrWhitespace(
    errors,
    "customerName",
    "customerName.required",
    "Please enter customer name"
);
```

This helper lives in `org.springframework.validation.ValidationUtils`. It accepts the field name, code, and fallback, and registers a field error when the condition is met. Not every object type shares the same notion of "empty"; use the helper appropriately for the property being checked.

### 8.2. Nested paths must account for context

When reusing a child validator, you can temporarily push a path:

```java
errors.pushNestedPath("address");
try {
    errors.rejectValue(
        "city",
        "city.required",
        "City is required"
    );
} finally {
    errors.popNestedPath();
}
```

With an `Errors` implementation that supports nested paths, the field error will have the path `address.city`. Always use `finally` to restore the previous context. `reject(...)` still registers a global error on the root object; if you want to report an error specifically on a child object, consider `rejectValue` with the appropriate path rather than expecting `reject` to turn into a field error.

Per recent Javadoc, `rejectValue` with an empty/`null` field can refer to the current object itself and in some situations create a global error; for clarity of intent, applications should generally use `reject` for root-level errors and `rejectValue("field", ...)` for named fields.

## 9. Using with Spring MVC and `BindingResult`

In Spring MVC, a handler typically accepts `BindingResult` or `Errors` **immediately after** the bound/validated data parameter:

```java
@PostMapping("/bookings")
public String submit(
        @Validated @ModelAttribute("bookingForm") BookingForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return "booking/edit";
    }

    bookingService.save(form);
    return "redirect:/bookings";
}
```

This is integration code; it requires the corresponding controller, service, form model, and imports. `@Validated` triggers configured validation (such as a Spring `Validator` registered via `@InitBinder` or Jakarta Bean Validation). If the handler wants to add business errors after binding, it can call `result.reject(...)`/`result.rejectValue(...)` and then check `hasErrors()`. Example:

```java
if (!availabilityService.isAvailable(form)) {
    result.reject(
        "booking.unavailable",
        new Object[] { form.getPackageName() },
        "Package {0} is unavailable"
    );
}

if (result.hasErrors()) {
    return "booking/edit";
}
```

Practices to avoid:

- `BindingResult` must sit immediately after the parameter it describes, not at the end of the signature after other parameters.
- If a handler uses `@RequestBody`, reading JSON is not form-field property binding; however, validation errors and `BindingResult` can still be used in compatible handler configurations/forms.
- Never call a service to persist data before checking `result.hasErrors()` if errors could compromise business validity.
- When displaying messages, resolve/render errors by locale; `result.toString()` is meant for diagnostics, not user-friendly UI text.

### 9.1. Displaying global and field errors

With Spring MVC templates, the basic idea is:

```text
Global errors:
  "Package VIP is sold out" -> place at the top of the form

Field errors:
  "Valid quantity: from 1 to 10" -> place near the quantity input
  "Code SAVE was not accepted" -> place near the coupon input
```

In Thymeleaf with Spring integration, example error expressions are:

```html
<form th:object="\${bookingForm}" method="post">
  <div th:if="\${#fields.hasGlobalErrors()}"
       th:each="error : \${#fields.globalErrors()}"
       th:text="\${error}"></div>

  <label>Quantity</label>
  <input th:field="*{quantity}">
  <span th:if="\${#fields.hasErrors('quantity')}"
        th:errors="*{quantity}"></span>
</form>
```

This is a template fragment requiring Thymeleaf/Spring MVC configuration and a populated `bookingForm` object. Error values must be escaped by a proper template engine; avoid building HTML by concatenating client content.

### 9.2. Returning a JSON API response

In a REST API, errors can be mapped to JSON containing `code`, `field` (if applicable), the resolved `message`, and safe metadata. **Illustrative shape example**, not a Spring-generated contract:

```json
{
  "errors": [
    {
      "code": "quantity.range",
      "field": "quantity",
      "message": "Quantity must be from 1 to 10"
    },
    {
      "code": "booking.unavailable",
      "field": null,
      "message": "Package VIP is sold out"
    }
  ]
}
```

Usually you select a **stable public code** for clients rather than relying solely on translated text or internal strings like `quantity.range.bookingForm.quantity`. Never return the rejected value if it is a password, token, or sensitive data. For HTTP bind/validation errors, the exception handler layer can return HTTP 400 (depending on endpoint design); `reject` itself does not decide the status code.

## 10. Reading Back Error Details for Handling

`Errors` supports these methods:

```java
errors.hasErrors();
errors.getErrorCount();
errors.hasGlobalErrors();
errors.getGlobalErrorCount();
errors.getGlobalErrors();
errors.hasFieldErrors();
errors.getFieldErrorCount();
errors.getFieldErrors();
errors.getFieldError("quantity");
errors.getFieldErrors("quantity");
errors.getAllErrors();
```

Example iterating each group (code placed inside a handler/validator test with `Errors errors`):

```java
for (ObjectError global : errors.getGlobalErrors()) {
    System.out.println(global.getCodes()[0]);
}
for (FieldError field : errors.getFieldErrors()) {
    System.out.println(field.getField() + ": " + field.getCode());
}
```

`FieldError` provides `getField()`, `getRejectedValue()`, and `isBindingFailure()` (distinguishing a binding failure from a validation failure). Meanwhile, `ObjectError` provides `getObjectName()`, `getCodes()`, `getArguments()`, and `getDefaultMessage()`. Querying errors helps craft accurate responses, while avoiding logging raw sensitive input values.

**Counting errors**: `getErrorCount()` is the sum of field errors and global errors. A single field can have multiple errors (e.g., failing both a format rule and a business rule). `hasErrors()` indicates at least one error exists; it does not prove all binding/validation steps ran as intended.

## 11. Distinguishing Similar Error Patterns

| Scenario | What to use | Reason |
| --- | --- | --- |
| `quantity=0` when 1–10 is required | `rejectValue("quantity", "quantity.range", ...)` | Single property violates bounds |
| `startDate > endDate` | `reject("dateRange.invalid", ...)` | Rule involves two fields |
| `password` and `confirmPassword` mismatch | `reject("password.mismatch", ...)` or `rejectValue("confirmPassword", ...)` when UI needs field attachment | Design errors around the UX |
| `age=abc` when `age` is `int` | Framework-recorded binding/`typeMismatch` error | No need for validator to parse `String` to `int` |
| Blank `email` field | `ValidationUtils.rejectIfEmptyOrWhitespace(...)` or `rejectValue(...)` | Target is attaching error to the field |
| No message code found | `defaultMessage`, if present | Display fallback; does not discard the error |
| Property outside `allowedFields` | Binding configuration and check suppressed fields | Do not equate suppressed fields with `FieldError` |

## 12. Common Mistakes and How to Avoid Them

**1. Confusing error codes with message sentences.** `errors.reject("Invalid quantity")` merely creates an error code containing that string; it blocks clean i18n. Use `quantity.invalid` and place sentences in message bundles.

**2. Thinking `reject` creates a field error.** `reject("email.invalid")` is a global error even though the code contains `email`. To attach to the email input, use `rejectValue("email", "email.invalid")`.

**3. Specifying the wrong field name.** `rejectValue("customer.address", ...)` differs from `rejectValue("customer.address.city", ...)`. The field name must match the model property and nested context; otherwise property access may fail or attach the error in the wrong place.

**4. Passing the wrong count or order of arguments.** A message `"{0} is between {1}–{2}"` requires three arguments in exact order. The compiler does not cross-check resource bundle contents against `errorArgs`.

**5. Using `getDefaultMessage()` directly for display.** That string may still contain unresolved `{0}`, is not locale-aware, and bypasses message bundles. Use `MessageSource` or template integration.

**6. Providing no fallback and no message key.** When no message is found, the resolver can throw `NoSuchMessageException`. Maintain meaningful fallbacks and test bundles/locales.

**7. Forgetting an error may originate from binding.** A validator might see the default `0` even though the user entered invalid string `"abc"`. If a field already has a binding error, avoid overwriting its meaning with an out-of-context business error; inspect `BindingResult` first.

**8. Checking `hasErrors()` too early.** If you keep calling `rejectValue` after business processing has begun, the app may update data before noticing errors. Perform validation before side effects.

**9. Neglecting the nested-path stack.** When using `pushNestedPath` for child validators, missing `popNestedPath` attaches subsequent errors to the wrong path; use `try/finally`.

**10. Putting sensitive data into messages.** `errorArgs` and `defaultMessage` can reach responses or logs; include only safe data, or mask when necessary.

**11. Relying on a single overly specific code.** If you only define `quantity.range.bookingForm.quantity`, renaming the model attribute to `checkoutForm` breaks message lookup. Keep a general fallback such as `quantity.range` where appropriate.

**12. Using exceptions for every form error.** For normal validation, `reject`/`rejectValue` accumulates multiple errors so users can fix them in one go. Exceptions suit unrecoverable design failures; no need to throw an exception for every invalid field.

## 13. Self-Check with Three Scenarios

### Scenario A — Choosing the error type

`ReservationForm` has `attendees` and `maxCapacity`. If only `attendees = -1`, what do you call? If `attendees = 5` while only 3 seats remain, what do you call?

**Hint:** `rejectValue("attendees", "attendees.positive", ...)` suits a single-field bound. If the reservation capacity rule depends on the state/inventory of the entire booking, `reject("reservation.capacityExceeded", ...)` works well; if the UI needs the error attached right to the `attendees` field, `rejectValue` is also a reasonable choice.

### Scenario B — Explaining code precedence

A validator calls `rejectValue("quantity", "quantity.range", new Object[]{1,10}, "Invalid quantity")` on object name `bookingForm`. The resource bundle contains:

```properties
quantity.range.bookingForm.quantity=Quantity from {0} to {1}
quantity.range=Value out of range
```

**Answer:** with the default resolver and matching field type, the first specific code is chosen; the message is `"Quantity from 1 to 10"`. If the specific key is deleted and no higher-precedence key exists, the resolver uses `quantity.range`, returning `"Value out of range"`. The fallback pattern is used only when no matching code is found.

### Scenario C — Spotting the API bug

Given:

```java
errors.reject("age.invalid", "Invalid age");
System.out.println(errors.getFieldError("age") != null);
```

**Answer:** on an `Errors` instance with no prior field errors, the expression prints `false`, because `reject` adds a **global error**. Having `age` inside the error code does not cause Spring to create a `FieldError`.

## 14. Official References

- Spring Framework Reference — [Validation using Spring's Validator Interface](https://docs.spring.io/spring-framework/reference/core/validation/validator.html): implementing `Validator`, `Errors`, `ValidationUtils`, and nested validation.
- Spring Framework Javadoc — [`Errors`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/Errors.html): `reject`/`rejectValue` overloads, `errorArgs`, `defaultMessage`, global/field errors.
- Spring Framework Javadoc — [`DefaultMessageCodesResolver`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/DefaultMessageCodesResolver.html): message code expansion rules, lookup order for object/field and indexed paths.
- Spring Framework Javadoc — [`ObjectError`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/ObjectError.html), [`FieldError`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/FieldError.html): structured error details.
- Spring Framework Reference — [Spring MVC validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): combining `@Validated`/`@Valid` with `BindingResult`.
- Spring Framework Javadoc — [`MessageSource`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/MessageSource.html): resolving messages by code, arguments, and locale.
