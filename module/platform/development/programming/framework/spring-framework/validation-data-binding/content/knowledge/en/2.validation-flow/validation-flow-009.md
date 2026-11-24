# Translating Error Codes into Localized Messages in Spring MVC

When Spring binding or validation fails, the application receives **structured error information** (error code, offending field, arguments, default message). End users need clear sentences in their own language, while the API can still keep a stable error code for machine processing. This translation typically flows through **`BindingResult` → `FieldError`/`ObjectError` → `MessageSource` + `Locale` → display message**.

## 1. Distinguishing Error Codes, Default Messages, and Localized Messages

| Component | Role | Example |
| --- | --- | --- |
| Error code | Technical key for message lookup; multiple codes may exist in priority order | `NotBlank.registrationRequest.email`, `NotBlank.email`, `NotBlank` |
| Error object | Holds object/field name, rejected value (if any), code list, arguments, default message | `FieldError`, `ObjectError` |
| `MessageSource` | Looks up keys in bundles such as `messages_vi.properties` and `messages_en.properties` | `Vui lòng nhập email.` |
| `Locale` | Specifies the request's language/region convention | `vi-VN`, `en-US` |
| Default message | Fallback if no code resolves; may come from the Bean Validation provider | `must not be blank` |

**Key takeaway:** Do not translate by comparing English strings, such as `if (message.equals("must not be blank"))`. Translate based on **error codes**; validator text can change across providers, languages, and versions.

`BindingResult` collects errors from two common sources:

- **Data binding/conversion:** request data cannot be converted to the target type. For example, a form submits `age=abc` while property `age` has type `Integer`; Spring creates an error with general code `typeMismatch`.
- **Validation:** data was populated onto the object but violates a constraint. For example, `@NotBlank` with `email=""` or `@Min(18)` with `age=16`.

`FieldError` describes a single field's error; `ObjectError` can describe an object-level error, such as a multi-field rule. Both implement `MessageSourceResolvable`, so they can be passed directly to `MessageSource.getMessage(error, locale)`.

## 2. How Does Spring Build the Error Code Lookup List?

For a `typeMismatch` error on field `age` belonging to a model attribute named `registrationForm`, `DefaultMessageCodesResolver` typically generates candidate codes ordered from most specific to most general:

1. `typeMismatch.registrationForm.age`
2. `typeMismatch.age`
3. `typeMismatch.java.lang.Integer` (depends on actual field type)
4. `typeMismatch`

For Bean Validation `@NotBlank` on `email`, candidates typically start with `NotBlank.registrationRequest.email`, followed by `NotBlank.email`, `NotBlank.java.lang.String`, and `NotBlank`. Object name, field name, field type, nested paths, and resolver configuration can alter the actual list. You can inspect the exact list via `error.getCodes()`.

`MessageSource` tries codes in order for the selected locale. Thus, a highly specific key conveys exact context, while a general key acts as a fallback across screens. For example:

~~~properties
# messages_vi.properties
typeMismatch.registrationForm.age=Tuổi phải là số nguyên hợp lệ.
typeMismatch=Giá trị nhập vào có kiểu không hợp lệ.
~~~

If the user enters `age=abc` and the error carries those codes, the first resolved message will be `Tuổi phải là số nguyên hợp lệ.`. When the specific key is not declared, Spring can fall back to `typeMismatch`. If no code is found, overloads accepting `MessageSourceResolvable` can use `defaultMessage`; if there is still no fallback, `NoSuchMessageException` may occur. Do not rely on automatically showing raw code names to users.

## 3. Declaring MessageSource and Language Resources

In a **Spring Boot 3.x / Spring Framework 6.x application with Java 17+**, place these files on the classpath:

~~~text
src/main/resources/
  messages.properties
  messages_vi.properties
  messages_en.properties
~~~

`messages.properties` also helps Spring Boot detect the basename and provides default messages. Minimal example contents:

~~~properties
# messages.properties: fallback, in English
NotBlank=This field is required.
NotNull=A value is required.
Min=The value is below the minimum.
typeMismatch=Invalid input type.
~~~

~~~properties
# messages_vi.properties
NotBlank.registrationRequest.email=Vui lòng nhập email.
NotNull.registrationRequest.age=Vui lòng nhập tuổi.
Min.registrationRequest.age=Bạn phải từ 18 tuổi trở lên.
typeMismatch.registrationForm.age=Tuổi phải là số nguyên hợp lệ.
NotBlank=Trường này không được để trống.
typeMismatch=Giá trị nhập vào không đúng kiểu.
~~~

~~~properties
# messages_en.properties
NotBlank.registrationRequest.email=Please enter your email.
NotNull.registrationRequest.age=Please enter your age.
Min.registrationRequest.age=You must be at least 18 years old.
typeMismatch.registrationForm.age=Age must be a valid integer.
NotBlank=This field is required.
typeMismatch=Invalid input type.
~~~

Each `key=value` line corresponds to an error code. When Spring looks up locale `vi-VN`, a Vietnamese bundle like `messages_vi.properties` can provide the value; with `en-US`, the corresponding English bundle is used. If no specific translation exists, the system can fall back to the base bundle or configured fallback behavior.

With Spring Boot, the default basename is `messages`; you can set it explicitly:

~~~properties
# application.properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
~~~

In a **Spring Framework project without Boot**, manually register a `MessageSource` bean, such as `ResourceBundleMessageSource` with basename `messages` and UTF-8. Do not add a duplicate bean of the same name in Boot when auto-configuration is already active.

Note: **translating messages from `BindingResult` with `MessageSource`** and **Bean Validation message interpolation** are two related but distinct mechanisms. `@NotBlank(message="{some.key}")` is interpolated by the validator according to Bean Validation configuration (typically `ValidationMessages.properties`; can integrate Spring `MessageSource`). The approach in this article reads codes from `FieldError.getCodes()` and invokes `MessageSource` when preparing output, giving explicit control over response locale.

## 4. REST API Example: One Error Code, Two Languages

The example below is code placed in a Spring Boot 3 project that already has `spring-boot-starter-web` and `spring-boot-starter-validation`. The classes/records can live in package `com.example.demo`; this is **Spring application code**, not a standalone program runnable solely with `javac` without dependencies.

~~~java
package com.example.demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.util.List;
import java.util.Locale;
import org.springframework.context.MessageSource;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

record RegistrationRequest(
        @NotBlank String email,
        @NotNull @Min(18) Integer age) {}

@RestController
class RegistrationController {
    @PostMapping("/registrations")
    ResponseEntity<Void> register(@Valid @RequestBody RegistrationRequest request) {
        // Process registration when input is valid.
        return ResponseEntity.noContent().build();
    }
}

record ValidationDetail(String field, String code, String message) {}
record ValidationResponse(String code, List<ValidationDetail> errors) {}

@RestControllerAdvice
class RegistrationValidationAdvice {
    private final MessageSource messageSource;

    RegistrationValidationAdvice(MessageSource messageSource) {
        this.messageSource = messageSource;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ValidationResponse> handle(
            MethodArgumentNotValidException exception, Locale locale) {

        List<ValidationDetail> details = exception.getBindingResult()
                .getAllErrors()
                .stream()
                .map(error -> new ValidationDetail(
                        error instanceof FieldError fieldError
                                ? fieldError.getField() : null,
                        error.getCode() == null ? "invalid" : error.getCode(),
                        messageSource.getMessage(error, locale)))
                .toList();

        return ResponseEntity.badRequest().body(
                new ValidationResponse("VALIDATION_FAILED", details));
    }
}
~~~

**Processing flow of the example:**

1. Spring/Jackson reads JSON into `RegistrationRequest`. `@Valid` triggers Bean Validation.
2. An empty field violates `@NotBlank`; age 16 violates `@Min(18)`. For this request body argument, Spring MVC raises `MethodArgumentNotValidException` containing `BindingResult`.
3. `@RestControllerAdvice` calls `getAllErrors()` so object-level `ObjectError`s are not missed. Each error is passed directly to `messageSource.getMessage(error, locale)`.
4. Spring MVC supplies the `Locale` argument via the configured locale resolution mechanism for the request. Under standard header-based configuration, `Accept-Language: vi-VN` selects Vietnamese and `Accept-Language: en-US` selects English.
5. The response still carries `VALIDATION_FAILED` and technical `code` values for the client; `message` is the human-readable text.

Send an illustrative request:

~~~http
POST /registrations HTTP/1.1
Content-Type: application/json
Accept-Language: vi-VN

{"email":"","age":16}
~~~

Expected response (error order may vary):

~~~json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {"field": "email", "code": "NotBlank", "message": "Vui lòng nhập email."},
    {"field": "age", "code": "Min", "message": "Bạn phải từ 18 tuổi trở lên."}
  ]
}
~~~

Change the header to `Accept-Language: en-US`, and the two corresponding messages become `Please enter your email.` and `You must be at least 18 years old.`. The API code `VALIDATION_FAILED`, codes `NotBlank`/`Min`, and field names remain stable per the example. `error.getCode()` returns a general default code; **this is not necessarily the first specific code** in `error.getCodes()`. If clients need even more stable error identifiers across multiple endpoints, design dedicated application codes and map them intentionally.

Do not assume every request error passes through `MethodArgumentNotValidException`. For example, malformed JSON or un-deserializable types usually go through `HttpMessageNotReadableException`; `@RequestParam` type conversion errors may produce `MethodArgumentTypeMismatchException`; method validation in newer Spring MVC cases may use `HandlerMethodValidationException`. Depending on the API, provide separate handlers and a unified locale/message policy for those error types.

## 5. HTML Forms: Reading Messages Directly from BindingResult

With `@ModelAttribute`, Spring can keep conversion/validation errors in `BindingResult` so the controller re-renders the form instead of throwing an exception. The method signature should have `BindingResult` **immediately after** the model parameter being validated:

~~~java
@PostMapping("/registration-form")
String submitForm(
        @Valid @ModelAttribute("registrationForm") RegistrationForm form,
        BindingResult result,
        Locale locale,
        Model model) {

    if (result.hasErrors()) {
        List<String> ageMessages = result.getFieldErrors("age").stream()
                .map(error -> messageSource.getMessage(error, locale))
                .toList();
        model.addAttribute("ageMessages", ageMessages);
        return "registration-form";
    }

    return "redirect:/registration/success";
}
~~~

This method snippet sits inside a controller that already has `MessageSource`, along with a `RegistrationForm` class having a bindable `age` property (e.g., getter/setter); add imports for `@Valid`, `@ModelAttribute`, `BindingResult`, `Locale`, `Model`, and `List` accordingly. This is an **integration illustration**, not a complete runnable controller or template on its own.

Suppose the `age` field is of type `Integer` and the user submits the string `abc`; the `typeMismatch` error will pass through the code chain in section 2. Calling `messageSource.getMessage(fieldError, locale)` lets you display a friendly message instead of a stack trace or technical type conversion error.

For forms, you can attach error lists to `Model` as above, or use the template engine's and Spring MVC's built-in error display support. If multiple errors on one field must be shown, keep the **list** instead of taking only the first error. For object-level errors, also read `result.getGlobalErrors()`. Templates must escape user-entered content; do not embed `rejectedValue` into messages in ways that expose sensitive data.

## 6. Locale Selection and Fallback Strategy

- Browsers typically send `Accept-Language`, such as `vi-VN,vi;q=0.9,en;q=0.8`. Spring MVC obtains the locale via `LocaleResolver`/i18n configuration and can inject `Locale` into handlers. Do not parse the header yourself with `split(",")` because `q` weights and locale matching rules matter.
- If the application lets users choose language by account, URL, or session, configure a consistent resolver/storage mechanism. The header is only one source of locale selection, not the sole source of truth.
- Maintain a base bundle with safe fallback messages. When adding new error codes, add translations for supported locales and test behavior when a key is missing. Avoid leaking `NoSuchMessageException`, class names, packages, paths, or rejected values into the UI.
- Error messages can accept parameters via `MessageSourceResolvable.getArguments()` and `MessageFormat` syntax such as `{0}`, `{1}`. To use arguments (such as character length limits), verify the actual arguments produced by that validator/binding error rather than assuming identical indices across all constraints. With `MessageFormat`, single quotes have special escaping rules.
- Locale affects **message language**; it should not alter API error codes, HTTP statuses, or business conditions. Language also does not replace date, number, currency formatting, or timezone handling when needed.

## 7. End-to-End Testing and Common Pitfalls

A meaningful test should run the application with complete `messages*.properties`, send the same invalid payload under different locales, and compare both **technical codes** and **messages**:

| Situation | Expectation |
| --- | --- |
| `email=""`, `age=16`, header `vi-VN` | HTTP 400, API keys unchanged, Vietnamese messages |
| Same payload, header `en-US` | HTTP 400, same fields/error codes, English messages |
| `age=abc` via **form binding** | `typeMismatch` mapped to a friendly message, no exception name shown |
| Missing field-specific key | Resolver uses general key or configured fallback |
| One global error and multiple field errors | Response/template does not drop object-level errors or multiple errors on the same field |
| Unsupported locale or missing bundle | Understandable fallback returned, no internal code leaked to client |

Common issues and how to avoid them:

1. **Using `error.getDefaultMessage()` as the final message:** that string may already be interpolated in another language, or be overly technical. Prefer `MessageSource.getMessage(error, locale)` with explicit keys; use default messages only as a controlled fallback.
2. **Looking up only `error.getCode()`:** easily misses object/field-specific keys. Pass the full `FieldError`/`ObjectError` to `MessageSource` so the full ordered code list is used.
3. **Declaring keys with the wrong object name:** `NotBlank.registrationForm.email` will not match `NotBlank.registrationRequest.email`. Log `getObjectName()`/`getCodes()` safely in development to verify actual keys.
4. **Confusing validation APIs with conversion:** `@NotBlank` cannot handle structurally invalid JSON payloads, and form `typeMismatch` errors can occur before constraint checks. Each error type needs an appropriate handling path.
5. **Missing base bundle or locale configuration:** Boot may not create `MessageSource` as expected if no matching bundle exists; the resolver may pick a locale different from the UI language. Check both configuration and request headers.
6. **Concatenating errors manually or hardcoding Vietnamese in the controller:** makes language changes hard, testing awkward, and reuse impossible. Put text in bundles; controllers only determine context and response structure.
7. **Returning raw rejected values or internal details:** error messages should be clear enough to fix input without leaking passwords, tokens, exceptions, class names, or query expressions.

**Guiding principle:** let Spring produce and retain error codes in `BindingResult`, use `MessageSource` to translate the **entire error object** with the request's `Locale`, define messages from specific → general in resource bundles, and output responses with stable technical codes and readable messages.
